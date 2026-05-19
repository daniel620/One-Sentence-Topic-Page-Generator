"""AI-native evidence curation — the semantic editorial judgment layer.

Three components, each a small schema-constrained LLM call:

  1. **AI source curator** — classifies every source as public_claim_source,
     supporting_context, background_only, debug_only, reject, or needs_review.
  2. **AI claim extractor** — reads one article's clean text and extracts
     typed Claim objects with claim_topic, evidence_sentence, and
     public_claim_eligible flag.
  3. **AI contradiction reviewer** — reviews candidate contradictions and
     classifies each as real_uncertainty, scope_difference, extraction_noise,
     or debug_only.

The AI layer sits inside Stage 2, between deterministic source scoring
and the EvidenceGraph construction. The code (schemas, validation,
rendering, QA gates, public/debug boundaries) remains deterministic.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from typing import Any

import anthropic
import instructor

from generator.schemas import (
    AISourceAssessment,
    AISourceRole,
    Claim,
    Claim,
    Source,
)

from generator.prompts import (
    MODEL_NAME,
    build_ai_claim_extraction_messages,
    build_ai_source_curation_messages,
)

LOGGER = logging.getLogger("ai_curation")


def _build_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for ai_curation")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


def _source_preview(source: Source) -> str:
    """One-line summary for the curator: publisher, domain, title."""
    pub = source.publisher or "unknown"
    title = source.title[:120] if source.title else ""
    return f"[{source.source_type.value}] {pub} — {title}"


# ---------------------------------------------------------------------------
# 1. AI source curator
# ---------------------------------------------------------------------------

def run_ai_source_curation(
    sources: list[Source],
    event_sentence: str,
    today: date | None = None,
    client: Any | None = None,
) -> list[AISourceAssessment]:
    """Classify every source's suitability for supporting public claims.

    The LLM sees the source title, publisher, URL path, source_type, and the
    event sentence. It returns a role for each source.
    """
    if not sources:
        return []

    llm = client or _build_client()
    current_date = today or date.today()

    messages = build_ai_source_curation_messages(sources, event_sentence, current_date)

    result = llm.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        messages=messages,
        response_model=list[AISourceAssessment],
    )
    assessments = list(result)

    for assessment in assessments:
        LOGGER.info(
            "AI curator: %s → %s (%s)",
            assessment.source_id, assessment.role.value, assessment.reason[:80],
        )
    return assessments


def _deterministic_role(source: Source) -> AISourceRole:
    """Map deterministic source_type to an AI-equivalent role for merge logic."""
    deterministic_map = {
        "official": AISourceRole.PUBLIC_CLAIM,
        "primary_data": AISourceRole.PUBLIC_CLAIM,
        "reputable_media": AISourceRole.PUBLIC_CLAIM,
        "local_media": AISourceRole.SUPPORTING,
        "social": AISourceRole.BACKGROUND,
        "aggregator": AISourceRole.DEBUG,
        "unknown": AISourceRole.DEBUG,
    }
    return deterministic_map.get(source.source_type.value, AISourceRole.DEBUG)


def _stricter_role(a: AISourceRole, b: AISourceRole) -> AISourceRole:
    """Return the stricter (more restrictive) of two roles.

    Uses the rank: PUBLIC_CLAIM < SUPPORTING < BACKGROUND < NEEDS_REVIEW < DEBUG < REJECT.
    """
    rank = {
        AISourceRole.PUBLIC_CLAIM: 0,
        AISourceRole.SUPPORTING: 1,
        AISourceRole.BACKGROUND: 2,
        AISourceRole.NEEDS_REVIEW: 3,
        AISourceRole.DEBUG: 4,
        AISourceRole.REJECT: 5,
    }
    return a if rank.get(a, 5) >= rank.get(b, 5) else b


def merge_source_roles(
    sources: list[Source],
    ai_assessments: list[AISourceAssessment],
) -> None:
    """Merge AI and deterministic roles, writing final_source_role on each source.

    Side-by-side model (option C): both run independently, stricter wins for
    public rendering. Disagreements are visible via ai_source_role vs.
    final_source_role in debug mode.

    Special case (user requirement #4): when deterministic says PUBLIC_CLAIM
    (official/primary/reputable) but AI says REJECT, downgrade to NEEDS_REVIEW
    instead of REJECT. The source can't support public claims until reviewed,
    but isn't silently discarded.
    """
    ai_map = {a.source_id: a for a in ai_assessments}

    for source in sources:
        det_role = _deterministic_role(source)
        ai_assessment = ai_map.get(source.source_id)
        ai_role = ai_assessment.role if ai_assessment else AISourceRole.BACKGROUND
        source.ai_source_role = ai_role

        # Special case: deterministic says strong, AI says reject → needs_review
        if (
            det_role == AISourceRole.PUBLIC_CLAIM
            and ai_role == AISourceRole.REJECT
        ):
            source.final_source_role = AISourceRole.NEEDS_REVIEW
            source.curation_reason = (
                f"AI rejected ({ai_assessment.reason[:80] if ai_assessment else 'no reason'}) "
                f"but deterministic says {det_role.value} — needs human review"
            )
            continue

        # Special case: deterministic says DEBUG (unknown domain, not in
        # KNOWN_PUBLISHERS) but AI has read the content and says it's usable.
        # Trust the AI — it has more information than the domain table.
        if (
            det_role == AISourceRole.DEBUG
            and ai_role in (AISourceRole.PUBLIC_CLAIM, AISourceRole.SUPPORTING)
        ):
            source.final_source_role = ai_role
            source.curation_reason = (
                f"AI says {ai_role.value} despite unknown domain — "
                f"trusting AI content assessment"
            )
            continue

        final = _stricter_role(det_role, ai_role)
        source.final_source_role = final
        if ai_assessment and ai_role != det_role:
            source.curation_reason = (
                f"disagreement: AI={ai_role.value}, det={det_role.value} → {final.value} "
                f"({ai_assessment.reason[:80]})"
            )
        elif ai_assessment:
            source.curation_reason = f"AI: {ai_assessment.reason[:160]}"


# ---------------------------------------------------------------------------
# 2. AI claim extractor
# ---------------------------------------------------------------------------

def run_ai_claim_extraction(
    article_text: str,
    source_id: str,
    event_sentence: str,
    today: date | None = None,
    client: Any | None = None,
) -> list[Claim]:
    """Extract typed claims from one article's clean text.

    The LLM reads the article body (from trafilatura) and returns typed
    Claim objects. Regex is NOT used. Claims are marked public_claim_eligible
    based on whether the evidence_sentence is a close match to the source text.
    """
    if not article_text or len(article_text.strip()) < 40:
        return []

    llm = client or _build_client()
    current_date = today or date.today()

    # Truncate to a reasonable window — the LLM shouldn't need the full article.
    text = article_text[:4000]

    messages = build_ai_claim_extraction_messages(text, source_id, event_sentence, current_date)

    try:
        result = llm.messages.create(
            model=MODEL_NAME,
            max_tokens=2000,
            messages=messages,
            response_model=list[Claim],
        )
    except Exception as exc:
        LOGGER.warning("AI claim extraction failed for %s: %s", source_id, exc)
        return []

    claims = list(result)
    # Ensure globally unique claim_ids by prefixing with source_id.
    for i, claim in enumerate(claims):
        claim.claim_id = f"{source_id}_{i:03d}"
    # Verify evidence_sentence appears in source text (fuzzy check).
    for claim in claims:
        evidence = getattr(claim, "evidence_sentence", "") or ""
        if evidence and len(evidence) > 20:
            # Check: does a 30-char window of evidence appear in the article?
            window = evidence[10:40].strip()
            if window and window not in article_text:
                claim.public_claim_eligible = False
                LOGGER.info(
                    "Claim %s: evidence_sentence not verified in source → debug-only",
                    claim.claim_id,
                )

    LOGGER.info(
        "AI claim extractor for %s: %d claims (%d public-eligible)",
        source_id, len(claims), sum(1 for c in claims if c.public_claim_eligible),
    )
    return claims


# ---------------------------------------------------------------------------
# 3. NOTE: AI contradiction reviewer moved to generator.contradictions
# ---------------------------------------------------------------------------
