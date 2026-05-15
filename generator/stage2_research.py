from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from tavily import TavilyClient

from generator.schemas import (
    ComponentEvidenceBucket,
    ComponentType,
    EventContext,
    RawResearch,
    ResearchEvidence,
    ResearchResult,
)


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
    raw_items = response.get("results", [])
    parsed: list[ResearchResult] = []
    for item in raw_items:
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


METRIC_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s?(?:%|x|ms|s|minutes?|hours?|days?|weeks?)\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s+\d{4})?|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
ACTION_PATTERN = re.compile(
    r"\b(launch|release|rollout|kickoff|opens|start|watch|tickets?|broadcast|stream)\b",
    re.IGNORECASE,
)


def _split_sentences(content: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", content) if item.strip()]


def _first_sentence_matching(content: str, pattern: re.Pattern[str]) -> str | None:
    for sentence in _split_sentences(content):
        if pattern.search(sentence):
            return sentence
    return None


def _build_evidence_pack(results: list[ResearchResult]) -> list[ResearchEvidence]:
    evidence: list[ResearchEvidence] = []
    seen_pairs: set[tuple[str, str]] = set()

    for item in results:
        candidates: list[tuple[str, str]] = []
        metric_sentence = _first_sentence_matching(item.content, METRIC_PATTERN)
        if metric_sentence:
            candidates.append(("metric", metric_sentence))
        date_sentence = _first_sentence_matching(item.content, DATE_PATTERN)
        if date_sentence:
            candidates.append(("date", date_sentence))
        action_sentence = _first_sentence_matching(item.content, ACTION_PATTERN)
        if action_sentence:
            candidates.append(("action", action_sentence))
        if not candidates:
            sentences = _split_sentences(item.content)
            if sentences:
                candidates.append(("general", sentences[0]))

        for signal_type, sentence in candidates:
            pair = (str(item.url), sentence)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            evidence.append(
                ResearchEvidence(
                    label=item.query[:100],
                    signal_type=signal_type,
                    snippet=sentence[:500],
                    source_url=item.url,
                    source_title=item.title,
                    source_publisher=item.source_name,
                    published_at=item.published_date,
                )
            )
            if len(evidence) >= 12:
                return evidence

    return evidence


def _infer_component_for_query(query: str) -> ComponentType:
    lowered = query.lower()
    if any(token in lowered for token in ("compare", "versus", "benchmark", "changed")):
        return ComponentType.COMPARISON_TABLE
    if any(token in lowered for token in ("watch", "follow", "how to", "tickets", "broadcast", "stream")):
        return ComponentType.ACTION_LIST
    if any(token in lowered for token in ("schedule", "dates", "timeline", "next", "checkpoint")):
        return ComponentType.TIMELINE
    if any(token in lowered for token in ("status", "live", "now", "developing")):
        return ComponentType.LIVE_TRACKER
    return ComponentType.STAT_GRID


def _build_component_evidence(
    context: EventContext,
    evidence_pack: list[ResearchEvidence],
) -> list[ComponentEvidenceBucket]:
    component_to_evidence: dict[ComponentType, list[ResearchEvidence]] = {
        component: [] for component in context.planned_components
    }
    fallback_component = context.planned_components[0]

    for evidence in evidence_pack:
        query_component = _infer_component_for_query(evidence.label)
        target = query_component if query_component in component_to_evidence else fallback_component
        bucket = component_to_evidence[target]
        if len(bucket) < 6:
            bucket.append(evidence)

    for component in context.planned_components:
        if component_to_evidence[component]:
            continue
        component_to_evidence[component] = evidence_pack[:2]

    return [
        ComponentEvidenceBucket(component_type=component, evidence=evidence_list)
        for component, evidence_list in component_to_evidence.items()
        if evidence_list
    ]


def run_research(
    context: EventContext,
    tavily_client: Any | None = None,
    max_results_per_query: int = 5,
) -> RawResearch:
    client = tavily_client or _build_tavily_client()
    with ThreadPoolExecutor(max_workers=len(context.search_queries)) as executor:
        batches = list(
            executor.map(
                lambda query: _search_query(client, query, max_results_per_query),
                context.search_queries,
            )
        )

    deduped: dict[str, ResearchResult] = {}
    for batch in batches:
        for item in batch:
            url_key = str(item.url)
            current = deduped.get(url_key)
            if current is None:
                deduped[url_key] = item
                continue
            if (item.score or 0) > (current.score or 0):
                deduped[url_key] = item

    results = sorted(
        deduped.values(),
        key=lambda item: (item.score is not None, item.score or 0),
        reverse=True,
    )
    evidence_pack = _build_evidence_pack(results)
    component_evidence = _build_component_evidence(context, evidence_pack)

    return RawResearch(
        event_type=context.event_type,
        status=context.status,
        collected_at=datetime.now(timezone.utc).isoformat(),
        results=results,
        evidence_pack=evidence_pack,
        component_evidence=component_evidence,
    )
