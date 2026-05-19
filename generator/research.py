"""Stage 2: search → source curation → claim extraction → EvidenceGraph.

Now includes the AI-native evidence layer alongside deterministic scoring:

  1. Tavily search (deterministic)
  2. Source creation + deterministic scoring (deterministic)
  3. AI source curator — classifies each source's role (LLM)
  4. Merge roles: stricter of AI + deterministic wins
  5. AI claim extractor — per-source typed extraction from trafilatura text (LLM)
  6. Regex fallback — for non-public sources, debug-only (deterministic)
  7. Contradiction detection (deterministic)
  8. AI contradiction reviewer — classifies each as real/scope/noise/debug (LLM)

The result is an EvidenceGraph with: AI-classified source roles,
AI-extracted claims with evidence_sentence verification, and AI-reviewed
contradictions. Stage 1B and Stage 3 receive the public_evidence_view.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from tavily import TavilyClient

from generator.contradictions import detect_contradictions, review_all_contradictions
from generator.curate import (
    merge_source_roles,
    run_ai_claim_extraction,
    run_ai_source_curation,
)
from generator.schemas import (
    AISourceRole,
    Claim,
    EvidenceGrade,
    EvidenceGraph,
    EventContext,
    ResearchResult,
    Source,
    SourceType,
)
from generator.utils import (
    create_source,
    extract_deterministic_claims,
    fetch_and_extract_content,
)

LOGGER = logging.getLogger("stage2_research")


def _should_keep_source(source: Source, admitted: dict[str, int]) -> bool:
    """Deterministic quality filter: authority floor + per-type caps."""
    max_by_type = {
        "social": 2, "aggregator": 1, "unknown": 2,
        "official": 20, "primary_data": 20, "reputable_media": 20, "local_media": 8,
    }
    if source.authority_score < 0.5:
        return False
    if admitted.get(source.source_type.value, 0) >= max_by_type.get(source.source_type.value, 8):
        return False
    return True


def _build_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is required for stage2_research")
    return TavilyClient(api_key=api_key)


def _search_query(client: Any, query: str, max_results: int) -> list[ResearchResult]:
    response = client.search(
        query=query, max_results=max_results,
        include_raw_content=False, include_answer=False, search_depth="advanced",
    )
    raw = response.get("results", []) if isinstance(response, dict) else []
    parsed: list[ResearchResult] = []
    for item in raw:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        content = (item.get("content") or "").strip()
        if not title or not url or not content:
            continue
        parsed.append(ResearchResult(
            query=query, title=title, url=url, content=content,
            source_name=item.get("source") or item.get("domain"),
            published_date=item.get("published_date"), score=item.get("score"),
        ))
    return parsed


def _dedupe_by_url(results: list[ResearchResult]) -> list[ResearchResult]:
    by_url: dict[str, ResearchResult] = {}
    for item in results:
        url = str(item.url)
        current = by_url.get(url)
        if current is None or (item.score or 0) > (current.score or 0):
            by_url[url] = item
    return sorted(by_url.values(), key=lambda r: (r.score is not None, r.score or 0), reverse=True)


def _build_evidence_graph(
    results: list[ResearchResult],
    context: EventContext,
    run_ai: bool = True,
) -> EvidenceGraph:
    """Build an EvidenceGraph with AI-curated sources and claims.

    When `run_ai` is True (the default), the three AI curation steps run:
    source curation, per-source claim extraction on public-eligible sources,
    and contradiction review. Set to False for tests/fixtures that don't
    need LLM calls.
    """
    event_keywords = context.event_sentence.lower().split() if context.event_sentence else []
    deduped = _dedupe_by_url(results)

    # --- Build candidate sources + deterministic scoring ---
    candidates: list[Source] = []
    for result in deduped[:20]:
        source = create_source(
            url=str(result.url), title=result.title,
            publisher=result.source_name,
            published_at=result.published_date,
            content=result.content, event_keywords=event_keywords,
        )
        candidates.append(source)

    # Filter by authority floor + per-type caps.
    admitted_counts: dict[str, int] = {}
    filtered: list[Source] = []
    for s in candidates:
        if _should_keep_source(s, admitted_counts):
            filtered.append(s)
            admitted_counts[s.source_type.value] = admitted_counts.get(s.source_type.value, 0) + 1
    candidates = filtered
    LOGGER.info("Source filter: %d → %d candidates", len(deduped[:20]), len(candidates))

    # Sort by overall_score so best sources get claim extraction budget.
    candidates.sort(key=lambda s: s.overall_score, reverse=True)

    # --- Pre-fetch via Tavily Extract for sources where trafilatura will likely fail ---
    # This batch call uses Tavily's server-side extraction (headless browser) as a
    # fallback when our httpx+trafilatura can't get article text.
    tavily_extracted: dict[str, str] = {}
    if run_ai:
        public_candidates = [s for s in candidates if s.authority_score >= 0.5]
        urls_to_extract = [str(s.url) for s in public_candidates]
        if urls_to_extract:
            try:
                client = _build_tavily_client()
                extract_result = client.extract(urls_to_extract)
                for item in (extract_result.get("results", []) if isinstance(extract_result, dict) else []):
                    raw = item.get("raw_content") or item.get("content") or ""
                    if raw and len(raw.strip()) >= 200:
                        tavily_extracted[item.get("url", "")] = raw
                LOGGER.info("Tavily Extract: got content for %d/%d URLs", len(tavily_extracted), len(urls_to_extract))
            except Exception as exc:
                LOGGER.warning("Tavily Extract failed: %s — will rely on httpx+trafilatura only", exc)

    # --- AI source curator ---
    if run_ai and candidates:
        ai_assessments = run_ai_source_curation(
            candidates, context.event_sentence or "",
        )
        merge_source_roles(candidates, ai_assessments)
    else:
        # No AI: all sources get default roles based on source_type.
        for s in candidates:
            _set_default_role(s)

    # --- Extract claims ---
    claims: list[Claim] = []
    public_sources = [s for s in candidates if _is_public_eligible(s)]
    debug_sources = [s for s in candidates if not _is_public_eligible(s)]

    # AI claim extraction on public-eligible sources (in parallel).
    if run_ai and public_sources:
        with ThreadPoolExecutor(max_workers=min(len(public_sources), 12)) as executor:
            futures = {
                executor.submit(
                    _extract_claims_for_source, s, context, run_ai, tavily_extracted, deduped,
                ): s for s in public_sources
            }
            for future in futures:
                try:
                    for claim in future.result():
                        claims = _merge_claim(claims, claim)
                except Exception as exc:
                    LOGGER.warning("Claim extraction failed: %s", exc)

    # Regex fallback for non-public sources — debug-only, never public_claim_eligible.
    if debug_sources:
        for source in debug_sources:
            content, _, _ = fetch_and_extract_content(str(source.url))
            text_for_extraction = content or next(
                (r.content for r in deduped if str(r.url) == str(source.url)), ""
            )
            if not text_for_extraction:
                continue
            for claim in extract_deterministic_claims(
                url=str(source.url), title=source.title,
                content=text_for_extraction, source_id=source.source_id,
                event_keywords=event_keywords, is_clean_text=False,
            ):
                claim.public_claim_eligible = False
                claim.evidence_grade = EvidenceGrade.WEAK_SNIPPET
                claims = _merge_claim(claims, claim)

    # Clean orphaned source references.
    valid_source_ids = {s.source_id for s in candidates}
    for claim in claims:
        claim.source_ids = [sid for sid in claim.source_ids if sid in valid_source_ids]
    claims = [c for c in claims if c.source_ids]

    # --- Contradiction detection + deterministic pre-filter + AI review ---
    contradictions = detect_contradictions(
        [c for c in claims if c.public_claim_eligible]
    )
    if contradictions:
        review_all_contradictions(contradictions, claims, run_ai=run_ai)

    graph = EvidenceGraph(
        event_hypothesis=context.event_sentence or context.primary_entity,
        sources=candidates,
        claims=claims,
        contradictions=contradictions,
        unresolved_questions=[],
        last_updated=datetime.now(timezone.utc),
    )
    LOGGER.info(
        "EvidenceGraph: %d sources (%d public), %d claims (%d public), %d contradictions (%d public)",
        len(graph.sources), sum(1 for s in graph.sources if _is_public_eligible(s)),
        len(graph.claims), sum(1 for c in graph.claims if c.public_claim_eligible),
        len(graph.contradictions),
        sum(1 for c in graph.contradictions if getattr(c, "ai_resolution", None) and str(c.ai_resolution.value) == "real_uncertainty"),
    )
    return graph


def _set_default_role(source: Source) -> None:
    """Fallback when AI curation is disabled."""
    det_map = {
        "official": AISourceRole.PUBLIC_CLAIM,
        "primary_data": AISourceRole.PUBLIC_CLAIM,
        "reputable_media": AISourceRole.PUBLIC_CLAIM,
        "local_media": AISourceRole.SUPPORTING,
        "social": AISourceRole.BACKGROUND,
        "aggregator": AISourceRole.DEBUG,
        "unknown": AISourceRole.DEBUG,
    }
    role = det_map.get(source.source_type.value, AISourceRole.DEBUG)
    source.ai_source_role = role
    source.final_source_role = role
    source.curation_reason = "no AI curator (deterministic-only)"


def _is_public_eligible(source: Source) -> bool:
    if not source.final_source_role:
        return False
    return source.final_source_role.value in ("public_claim_source",)


def _extract_claims_for_source(
    source: Source, context: EventContext, run_ai: bool,
    tavily_extracted: dict[str, str] | None = None,
    search_results: list[ResearchResult] | None = None,
) -> list[Claim]:
    content, _, is_full = fetch_and_extract_content(str(source.url))
    if not content and tavily_extracted:
        # Fall back to Tavily Extract (server-side headless browser).
        content = tavily_extracted.get(str(source.url), "")
        is_full = bool(content and len(content.strip()) >= 200)
    if not content and search_results:
        # Last resort: Tavily search snippet (weak, never public).
        content = next(
            (r.content for r in search_results if str(r.url) == str(source.url)), ""
        )
        is_full = False
    if not content:
        return []

    if run_ai:
        claims = list(run_ai_claim_extraction(
            content, source.source_id, context.event_sentence or "",
        ))
        # Grade evidence quality — verify evidence_sentence against content.
        for claim in claims:
            claim.evidence_grade = _grade_evidence(source, is_full, claim, content)
            # Evidence tiers for public eligibility:
            # Tier 1 (public-ready): full_text_verified, official_snippet — can anchor any fact.
            # Tier 2 (public with caution): reputable_snippet — can support context/background
            #   but should not be the sole source for a headline key fact. Public-eligible
            #   if authority ≥ 0.7; lower → weak_snippet.
            # Tier 3 (never public): weak_snippet — debug trace only.
            if claim.evidence_grade == EvidenceGrade.WEAK_SNIPPET:
                claim.public_claim_eligible = False
            elif claim.evidence_grade == EvidenceGrade.REPUTABLE_SNIPPET:
                # Accept reputable snippets only when the source is clearly credible.
                if source.authority_score < 0.7:
                    claim.public_claim_eligible = False
        return claims
    else:
        event_kw = context.event_sentence.lower().split() if context.event_sentence else []
        return list(extract_deterministic_claims(
            url=str(source.url), title=source.title,
            content=content, source_id=source.source_id,
            event_keywords=event_kw, is_clean_text=True,
        ))


def _grade_evidence(source: Source, is_full_text: bool, claim: Claim | None = None, content: str = "") -> EvidenceGrade:
    """Assign an evidence grade based on source authority, extraction quality,
    and whether the claim's evidence_sentence is actually verifiable in the
    extracted text."""
    if is_full_text and source.authority_score >= 0.7:
        # Full text extracted — but verify the evidence sentence is real.
        if claim and content:
            ev = getattr(claim, "evidence_sentence", "") or ""
            if _evidence_in_content(ev, content):
                return EvidenceGrade.FULL_TEXT_VERIFIED
            # Evidence sentence not found in content — downgrade.
            return EvidenceGrade.REPUTABLE_SNIPPET
        return EvidenceGrade.FULL_TEXT_VERIFIED
    if source.source_type.value in ("official", "primary_data"):
        return EvidenceGrade.OFFICIAL_SNIPPET
    if source.source_type.value in ("reputable_media",):
        return EvidenceGrade.REPUTABLE_SNIPPET
    if source.authority_score >= 0.7:
        return EvidenceGrade.OFFICIAL_SNIPPET
    return EvidenceGrade.WEAK_SNIPPET


def _evidence_in_content(evidence: str, content: str) -> bool:
    """Check that a meaningful substring of evidence appears in the content.

    Uses a 40-char sliding window — stricter than the old 30-char check,
    and skips windows that are just generic phrases.
    """
    if not evidence or len(evidence) < 30:
        return False
    for start in range(0, len(evidence) - 40, 10):
        window = evidence[start:start + 40].strip()
        if len(window) < 30:
            continue
        # Skip generic/common phrases.
        generic_starts = ("The ", "This ", "It is ", "There ", "These ", "Those ")
        if any(window.startswith(g) for g in generic_starts):
            continue
        if window in content:
            return True
    return False


def _merge_claim(claims: list[Claim], new_claim: Claim) -> list[Claim]:
    # Merge if same type AND (same topic or high text similarity).
    new_topic = getattr(new_claim, "claim_topic", None)
    for existing in claims:
        if existing.claim_type != new_claim.claim_type:
            continue
        existing_topic = getattr(existing, "claim_topic", None)
        same_topic = (new_topic and existing_topic and new_topic == existing_topic)
        # Check for high word overlap — same fact, different phrasing.
        new_words = set(new_claim.text.lower().split())
        old_words = set(existing.text.lower().split())
        overlap = len(new_words & old_words) / max(1, len(new_words | old_words))
        if overlap > 0.4 or same_topic or new_claim.text.lower() == existing.text.lower():
            if new_claim.source_ids and new_claim.source_ids[0] not in existing.source_ids:
                existing.source_ids.extend(new_claim.source_ids[:1])
            return claims
    claims.append(new_claim)
    return claims


def _has_public_official_source(graph: EvidenceGraph) -> bool:
    """Check if the graph has at least one official source with public_claim role."""
    for source in graph.sources:
        if (source.source_type == SourceType.OFFICIAL
                and source.final_source_role == AISourceRole.PUBLIC_CLAIM):
            return True
    return False


def _enrich_with_official_sources(
    graph: EvidenceGraph,
    client: TavilyClient,
    context: EventContext,
    run_ai: bool = True,
) -> None:
    """If the graph has no official/public-claim sources, discover them via a
    targeted search for '[primary entity] official website'.

    This runs after the primary evidence graph is built. It adds 2-3 sources
    from the discovery query plus their extracted claims, without re-running
    the full pipeline on existing sources.
    """
    if _has_public_official_source(graph):
        return

    entity = (context.primary_entity or "").strip()[:100]
    if not entity:
        return

    discovery_query = f"{entity} official website"
    try:
        response = client.search(
            query=discovery_query, max_results=5,
            include_raw_content=False, include_answer=False,
            search_depth="advanced",
        )
    except Exception as exc:
        LOGGER.warning("Official source discovery search failed: %s", exc)
        return

    raw = response.get("results", []) if isinstance(response, dict) else []
    if not raw:
        return

    # Build ResearchResult objects from discovery results.
    discovery_results: list[ResearchResult] = []
    for item in raw:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        content = (item.get("content") or "").strip()
        if not title or not url or not content:
            continue
        discovery_results.append(ResearchResult(
            query=discovery_query, title=title, url=url, content=content,
            source_name=item.get("source") or item.get("domain"),
            published_date=item.get("published_date"), score=item.get("score"),
        ))

    if not discovery_results:
        return

    # Dedupe against sources already in the graph.
    existing_urls = {str(s.url) for s in graph.sources}
    discovery_results = [r for r in discovery_results if str(r.url) not in existing_urls]
    if not discovery_results:
        return

    # Take the top 2-3 results.
    discovery_results = discovery_results[:3]

    # Create Source objects with deterministic scoring.
    event_keywords = (context.event_sentence or "").lower().split()
    new_sources: list[Source] = []
    for result in discovery_results:
        source = create_source(
            url=str(result.url), title=result.title,
            publisher=result.source_name,
            published_at=result.published_date,
            content=result.content, event_keywords=event_keywords,
        )
        if source.authority_score >= 0.7:
            new_sources.append(source)

    if not new_sources:
        return

    # Assign default roles (no AI curator call — these are targeted
    # discovery results whose authority is determined by hostname match).
    for s in new_sources:
        _set_default_role(s)

    existing_claim_ids = {c.claim_id for c in graph.claims}

    # Add new sources to the graph.
    graph.sources.extend(new_sources)

    # Extract claims for each discovery source.
    for source in new_sources:
        try:
            claims = _extract_claims_for_source(
                source, context, run_ai=run_ai,
                search_results=discovery_results,
            )
            for claim in claims:
                if claim.claim_id not in existing_claim_ids:
                    graph.claims.append(claim)
                    existing_claim_ids.add(claim.claim_id)
        except Exception as exc:
            LOGGER.debug("Claim extraction for discovery source %s failed: %s", source.url, exc)

    LOGGER.info(
        "Discovery: added %d official sources, %d claims",
        len(new_sources),
        sum(1 for c in graph.claims if c.claim_id in existing_claim_ids),
    )


def run_research(
    context: EventContext,
    tavily_client: Any | None = None,
    max_results_per_query: int = 5,
    run_ai: bool = True,
) -> EvidenceGraph:
    """Search the open web, build an AI-curated EvidenceGraph."""
    client = tavily_client or _build_tavily_client()

    with ThreadPoolExecutor(max_workers=len(context.search_queries) or 1) as executor:
        batches = list(executor.map(
            lambda q: _search_query(client, q, max_results_per_query),
            context.search_queries,
        ))

    all_results: list[ResearchResult] = []
    for batch in batches:
        all_results.extend(batch)

    graph = _build_evidence_graph(all_results, context, run_ai=run_ai)

    # Enrich with official sources if the initial search found none.
    _enrich_with_official_sources(graph, client, context, run_ai=run_ai)

    LOGGER.info(
        "EvidenceGraph: %d sources, %d claims, %d contradictions",
        len(graph.sources), len(graph.claims), len(graph.contradictions),
    )
    return graph
