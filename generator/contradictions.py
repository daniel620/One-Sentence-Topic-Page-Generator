"""Contradiction detection and review — deterministic + AI.

Three layers, in order:
  1. **Deterministic detection** — numeric/date comparison across claims
     (moved from utils.py). Low precision, high recall.
  2. **Deterministic pre-filter** — before AI review, auto-classify as
     scope_difference when claims have different topics or types.
     Catches the "48 teams vs 32 teams" false positive.
  3. **AI contradiction reviewer** — only sees candidates that pass the
     pre-filter. Classifies as real_uncertainty, scope_difference,
     extraction_noise, or debug_only.

Only real_uncertainty contradictions appear on the public page.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import anthropic
import instructor

from generator.prompts import (
    MODEL_NAME,
    build_ai_contradiction_review_messages,
)
from generator.schemas import (
    AIContradictionResolution,
    AIContradictionReview,
    Claim,
    ClaimType,
    Contradiction,
    DisplayPolicy,
    ResolutionPolicy,
)

LOGGER = logging.getLogger("contradictions")


# ---------------------------------------------------------------------------
# 1. Deterministic detection
# ---------------------------------------------------------------------------

def detect_contradictions(claims: list[Claim]) -> list[Contradiction]:
    """Find candidate contradictions by comparing numeric and date claims.

    Low precision, high recall. The pre-filter and AI reviewer remove
    false positives downstream.
    """
    contradictions: list[Contradiction] = []

    metric_claims: dict[str, list[Claim]] = {}
    date_claims: dict[str, list[Claim]] = {}

    for claim in claims:
        ct = claim.claim_type
        ct_val = ct.value if hasattr(ct, "value") else str(ct)
        if ct_val == "metric":
            unit = claim.claim_attributes.get("unit", "?")
            metric_claims.setdefault(unit, []).append(claim)
        elif ct_val == "date":
            text_key = claim.text[:50]
            date_claims.setdefault(text_key, []).append(claim)

    for unit, unit_claims in metric_claims.items():
        if len(unit_claims) <= 1:
            continue
        numeric_values = [
            float(c.claim_attributes.get("value", "0"))
            for c in unit_claims
            if c.claim_attributes.get("value", "").replace(".", "").replace("-", "").isdigit()
        ]
        if len(set(numeric_values)) <= 1:
            continue
        max_val = max(numeric_values)
        min_val = min(numeric_values)
        if max_val / max(min_val, 0.001) <= 1.1:
            continue
        claim_a = next(c for c in unit_claims if float(c.claim_attributes.get("value", "0")) == min_val)
        claim_b = next(c for c in unit_claims if float(c.claim_attributes.get("value", "0")) == max_val)
        va = claim_a.claim_attributes.get("value", "?")
        ua = claim_a.claim_attributes.get("unit", "?")
        vb = claim_b.claim_attributes.get("value", "?")
        ub = claim_b.claim_attributes.get("unit", "?")
        contradictions.append(Contradiction(
            topic=f"{unit} measurement",
            claim_a=f"{va} {ua}",
            sources_a=claim_a.source_ids,
            claim_b=f"{vb} {ub}",
            sources_b=claim_b.source_ids,
            resolution=(
                ResolutionPolicy.PREFER_NEWER
                if claim_a.freshness == "fresh"
                else ResolutionPolicy.UNRESOLVED
            ),
            display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
        ))

    all_date_claims: list[Claim] = []
    for group in date_claims.values():
        all_date_claims.extend(group)
    if len(all_date_claims) > 1:
        dates = [
            c.claim_attributes.get("date_value")
            for c in all_date_claims
            if c.claim_attributes.get("date_value")
        ]
        if len(set(dates)) > 1:
            claim_a = all_date_claims[0]
            claim_b = all_date_claims[1]
            contradictions.append(Contradiction(
                topic="Event date",
                claim_a=claim_a.text,
                sources_a=claim_a.source_ids,
                claim_b=claim_b.text,
                sources_b=claim_b.source_ids,
                resolution=ResolutionPolicy.PREFER_OFFICIAL,
                display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
            ))

    return contradictions


# ---------------------------------------------------------------------------
# 2. Deterministic pre-filter
# ---------------------------------------------------------------------------

def _find_claim_for_contradiction(
    claims: list[Claim], source_ids: list[str], claim_text: str,
) -> Claim | None:
    """Find the claim object that best matches a contradiction side."""
    # First: exact source_id prefix match (claim_id starts with source_id_NNN)
    for c in claims:
        cid = getattr(c, "claim_id", "")
        for sid in source_ids:
            if cid.startswith(sid):
                return c
    # Second: text similarity
    text_lower = claim_text.lower().strip()
    for c in claims:
        c_text = getattr(c, "text", "").lower().strip()
        if text_lower in c_text or c_text in text_lower:
            return c
    return None


def pre_filter_contradictions(
    contradictions: list[Contradiction],
    claims: list[Claim],
) -> tuple[list[Contradiction], dict[int, AIContradictionReview], list[int]]:
    """Auto-resolve contradictions that are clearly scope differences.

    Returns (needs_ai_review, pre_resolved, original_indices).
    pre_resolved maps original contradiction index → resolution.
    original_indices[i] is the full-list index for needs_ai[i].
    """
    needs_ai: list[Contradiction] = []
    pre_resolved: dict[int, AIContradictionReview] = {}
    original_indices: list[int] = []

    for i, c in enumerate(contradictions):
        claim_a = _find_claim_for_contradiction(claims, c.sources_a, c.claim_a)
        claim_b = _find_claim_for_contradiction(claims, c.sources_b, c.claim_b)

        if claim_a is None or claim_b is None:
            needs_ai.append(c)
            continue

        topic_a = getattr(claim_a, "claim_topic", None)
        topic_b = getattr(claim_b, "claim_topic", None)
        type_a = getattr(claim_a, "claim_type", None)
        type_b = getattr(claim_b, "claim_type", None)

        # Different topics → they're about different things. Not a contradiction.
        if (
            topic_a is not None and topic_b is not None
            and topic_a != topic_b
        ):
            ta = topic_a.value if hasattr(topic_a, "value") else str(topic_a)
            tb = topic_b.value if hasattr(topic_b, "value") else str(topic_b)
            pre_resolved[i] = AIContradictionReview(
                contradiction_index=i,
                resolution=AIContradictionResolution.SCOPE_DIFFERENCE,
                reason=(
                    f"Different claim topics: {ta} vs {tb} — "
                    f"these refer to different aspects of the event"
                ),
            )
            LOGGER.info(
                "Pre-filter: contradiction #%d → scope_difference (topic: %s vs %s)",
                i, ta, tb,
            )
            continue

        # Different types → likely measuring different things.
        if type_a is not None and type_b is not None and type_a != type_b:
            ta = type_a.value if hasattr(type_a, "value") else str(type_a)
            tb = type_b.value if hasattr(type_b, "value") else str(type_b)
            # Both metric → could still be a real contradiction (e.g. two
            # sources report different attendance numbers). Let AI decide.
            if ta == "metric" and tb == "metric":
                needs_ai.append(c)
                continue
            pre_resolved[i] = AIContradictionReview(
                contradiction_index=i,
                resolution=AIContradictionResolution.SCOPE_DIFFERENCE,
                reason=(
                    f"Different claim types: {ta} vs {tb} — "
                    f"these measure different things"
                ),
            )
            LOGGER.info(
                "Pre-filter: contradiction #%d → scope_difference (type: %s vs %s)",
                i, ta, tb,
            )
            continue

        needs_ai.append(c)
        original_indices.append(i)

    LOGGER.info(
        "Pre-filter: %d contradictions → %d to AI, %d pre-resolved as scope_difference",
        len(contradictions), len(needs_ai), len(pre_resolved),
    )
    return needs_ai, pre_resolved, original_indices


# ---------------------------------------------------------------------------
# 3. AI contradiction reviewer
# ---------------------------------------------------------------------------

def _build_client() -> Any:
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


def run_ai_contradiction_review(
    contradictions: list[Contradiction],
    today: date | None = None,
    client: Any | None = None,
) -> list[AIContradictionReview]:
    """Review candidate contradictions with AI.

    Only candidates that pass the deterministic pre-filter reach this
    function. The AI classifies each as real_uncertainty, scope_difference,
    extraction_noise, or debug_only.
    """
    if not contradictions:
        return []

    llm = client or _build_client()
    current_date = today or date.today()

    messages = build_ai_contradiction_review_messages(contradictions, current_date)

    try:
        result = llm.messages.create(
            model=MODEL_NAME,
            max_tokens=1000,
            messages=messages,
            response_model=list[AIContradictionReview],
        )
    except Exception as exc:
        LOGGER.warning("AI contradiction review failed: %s", exc)
        return [
            AIContradictionReview(
                contradiction_index=i,
                resolution=AIContradictionResolution.DEBUG_ONLY,
                reason=f"AI review failed: {exc}",
            )
            for i in range(len(contradictions))
        ]

    reviews = list(result)
    for review in reviews:
        LOGGER.info(
            "AI contradiction review: #%d → %s (%s)",
            review.contradiction_index,
            review.resolution.value,
            review.reason[:80],
        )
    return reviews


def apply_contradiction_reviews(
    contradictions: list[Contradiction],
    reviews: list[AIContradictionReview],
) -> None:
    """Write AI verdicts onto each Contradiction.

    Only applies to contradictions whose ai_resolution is not already set
    (by the deterministic pre-filter). Pre-resolved contradictions are
    immutable — the AI cannot override a deterministic scope_difference.
    """
    review_map: dict[int, AIContradictionReview] = {
        r.contradiction_index: r for r in reviews
    }
    for i, contradiction in enumerate(contradictions):
        if contradiction.ai_resolution is not None:
            continue  # Pre-filter already set this
        review = review_map.get(i)
        if review:
            contradiction.ai_resolution = review.resolution
            contradiction.ai_resolution_reason = review.reason
        else:
            contradiction.ai_resolution = AIContradictionResolution.DEBUG_ONLY
            contradiction.ai_resolution_reason = "No review available"


# ---------------------------------------------------------------------------
# 4. Unified entry point
# ---------------------------------------------------------------------------

def review_all_contradictions(
    contradictions: list[Contradiction],
    claims: list[Claim],
    today: date | None = None,
    client: Any | None = None,
    *,
    run_ai: bool = True,
) -> None:
    """Full contradiction review pipeline: pre-filter → AI review → apply.

    Modifies contradictions in place. After this call, each contradiction
    has ai_resolution and ai_resolution_reason set.

    The deterministic pre-filter always runs. AI review only runs when
    run_ai=True and there are candidates that passed the pre-filter.
    """
    if not contradictions:
        return

    # Step 1: deterministic pre-filter (always runs)
    needs_ai, pre_resolved, original_indices = pre_filter_contradictions(
        contradictions, claims,
    )

    # Step 2: apply pre-resolved verdicts immediately
    for i, review in pre_resolved.items():
        if i < len(contradictions):
            contradictions[i].ai_resolution = review.resolution
            contradictions[i].ai_resolution_reason = review.reason

    # Step 3: AI review for remaining candidates (only when enabled)
    if needs_ai and run_ai:
        ai_reviews = run_ai_contradiction_review(needs_ai, today=today, client=client)
        # Remap sublist indices to original full-list indices.
        # ai_reviews use indices relative to needs_ai (0..len(needs_ai)-1).
        # We must map them to the original contradictions list positions.
        index_map: dict[int, int] = {
            sub_idx: full_idx
            for sub_idx, full_idx in enumerate(original_indices)
        }
        for review in ai_reviews:
            full_idx = index_map.get(review.contradiction_index)
            if full_idx is not None and full_idx < len(contradictions):
                review.contradiction_index = full_idx
        apply_contradiction_reviews(contradictions, ai_reviews)
    elif needs_ai:
        # No AI: default remaining to debug_only
        for i, c in enumerate(contradictions):
            if c.ai_resolution is None:
                c.ai_resolution = AIContradictionResolution.DEBUG_ONLY
                c.ai_resolution_reason = "AI review disabled"
