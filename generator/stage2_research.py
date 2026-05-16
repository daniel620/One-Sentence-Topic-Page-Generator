"""Stage 2: deterministic research → `EvidenceGraph`.

1. Tavily search for each query from Stage 1A.
2. Deduplicate results by URL, prefer higher Tavily scores.
3. Fetch each URL and extract readable text + title.
4. Run rule-based claim extraction (`generator.utils.extract_deterministic_claims`).
5. Score each source's authority, freshness, and relevance.
6. Detect contradictions between numeric/date claims.
7. Return an `EvidenceGraph` for Stage 1B / Stage 3 / QA to consume.

No LLM calls happen here — every step is reproducible and testable.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from tavily import TavilyClient

from generator.schemas import (
    Claim,
    EvidenceGraph,
    EventContext,
    ResearchResult,
    Source,
)
from generator.utils import (
    create_source,
    detect_contradictions,
    extract_deterministic_claims,
    fetch_and_extract_content,
)

LOGGER = logging.getLogger("stage2_research")


def _build_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY is required for stage2_research")
    return TavilyClient(api_key=api_key)


def _search_query(client: Any, query: str, max_results: int) -> list[ResearchResult]:
    response = client.search(
        query=query,
        max_results=max_results,
        include_raw_content=False,
        include_answer=False,
        search_depth="advanced",
    )
    raw = response.get("results", []) if isinstance(response, dict) else []
    parsed: list[ResearchResult] = []
    for item in raw:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        content = (item.get("content") or "").strip()
        if not title or not url or not content:
            continue
        parsed.append(
            ResearchResult(
                query=query,
                title=title,
                url=url,
                content=content,
                source_name=item.get("source") or item.get("domain"),
                published_date=item.get("published_date"),
                score=item.get("score"),
            )
        )
    return parsed


def _dedupe_by_url(results: list[ResearchResult]) -> list[ResearchResult]:
    by_url: dict[str, ResearchResult] = {}
    for item in results:
        url = str(item.url)
        current = by_url.get(url)
        if current is None or (item.score or 0) > (current.score or 0):
            by_url[url] = item
    return sorted(
        by_url.values(),
        key=lambda r: (r.score is not None, r.score or 0),
        reverse=True,
    )


def _build_evidence_graph(
    results: list[ResearchResult], context: EventContext
) -> EvidenceGraph:
    sources: list[Source] = []
    claims: list[Claim] = []
    event_keywords = context.event_sentence.lower().split() if context.event_sentence else []

    for result in _dedupe_by_url(results)[:20]:
        source = create_source(
            url=str(result.url),
            title=result.title,
            publisher=result.source_name,
            published_at=result.published_date,
            content=result.content,
            event_keywords=event_keywords,
        )
        sources.append(source)

        content, _ = fetch_and_extract_content(str(result.url))
        if not content:
            continue

        for new_claim in extract_deterministic_claims(
            url=str(result.url),
            title=result.title,
            content=content,
            source_id=source.source_id,
        ):
            existing = next(
                (
                    c for c in claims
                    if c.text.lower() == new_claim.text.lower() and c.claim_type == new_claim.claim_type
                ),
                None,
            )
            if existing is None:
                claims.append(new_claim)
            elif source.source_id not in existing.source_ids:
                existing.source_ids.append(source.source_id)

    valid_source_ids = {s.source_id for s in sources}
    for claim in claims:
        claim.source_ids = [sid for sid in claim.source_ids if sid in valid_source_ids]
    claims = [c for c in claims if c.source_ids]

    return EvidenceGraph(
        event_hypothesis=context.event_sentence or context.primary_entity,
        sources=sources,
        claims=claims,
        contradictions=detect_contradictions(claims),
        unresolved_questions=[],
        last_updated=datetime.now(timezone.utc),
    )


def run_research(
    context: EventContext,
    tavily_client: Any | None = None,
    max_results_per_query: int = 5,
) -> EvidenceGraph:
    """Search the open web, build and return an `EvidenceGraph`."""
    client = tavily_client or _build_tavily_client()

    with ThreadPoolExecutor(max_workers=len(context.search_queries) or 1) as executor:
        batches = list(
            executor.map(
                lambda q: _search_query(client, q, max_results_per_query),
                context.search_queries,
            )
        )

    all_results: list[ResearchResult] = []
    for batch in batches:
        all_results.extend(batch)

    graph = _build_evidence_graph(all_results, context)
    LOGGER.info(
        "Built EvidenceGraph: %d sources, %d claims, %d contradictions",
        len(graph.sources), len(graph.claims), len(graph.contradictions),
    )
    return graph
