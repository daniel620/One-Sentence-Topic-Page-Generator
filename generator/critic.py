"""Evidence Gate and Page Gate — quality evaluation agents.

Evidence Gate: evaluates evidence sufficiency after research.
  (formerly Product Critic — same logic, clearer name)
Page Gate: evaluates final page quality from structured data.
  (formerly Page Critic — now receives a compact summary, not raw HTML)

The key architectural fix: Page Gate receives a ~800-token structured
summary instead of ~8000 tokens of HTML+CSS. This fixes the max_tokens
bug that made the old Page Critic dead code.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import anthropic
import instructor
from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField

from generator.prompts import (
    MODEL_NAME,
    build_product_critic_messages,
    build_page_critic_messages,
)
from generator.schemas import EvidenceGraph, TopicPageData

LOGGER = logging.getLogger("gates")


# ---------------------------------------------------------------------------
# Evidence Gate (formerly Product Critic)
# ---------------------------------------------------------------------------

def _count_public_claims(graph: EvidenceGraph, min_grade: str | None = None) -> int:
    """Count public-eligible claims, optionally filtered by minimum evidence grade."""
    grades = ["full_text_verified", "official_snippet", "reputable_snippet", "multi_sourced", "weak_snippet"]
    if min_grade:
        min_idx = grades.index(min_grade) if min_grade in grades else len(grades)
        allowed = set(grades[:min_idx + 1])
    else:
        allowed = set(grades)
    return sum(
        1 for c in graph.claims
        if getattr(c, "public_claim_eligible", False)
        and getattr(c, "evidence_grade", None)
        and (getattr(c.evidence_grade, "value", str(c.evidence_grade)) in allowed)
    )


def _count_official_sources(graph: EvidenceGraph) -> int:
    return sum(
        1 for s in graph.sources
        if getattr(s.source_type, "value", str(s.source_type)) in ("official", "primary_data")
    )


def _count_covered_topics(graph: EvidenceGraph) -> int:
    """Count distinct claim_topics with at least one verified claim."""
    topics: set[str] = set()
    for c in graph.claims:
        if not getattr(c, "public_claim_eligible", False):
            continue
        grade = getattr(c, "evidence_grade", None)
        grade_val = getattr(grade, "value", str(grade)) if grade else ""
        if grade_val not in ("full_text_verified", "official_snippet", "reputable_snippet"):
            continue
        topic = getattr(c, "claim_topic", None)
        if topic:
            topics.add(getattr(topic, "value", str(topic)))
    return len(topics)


def _deterministic_evidence_decision(graph: EvidenceGraph, event_type: str) -> dict[str, Any]:
    """Rule-based evidence sufficiency check. No LLM call.

    Uses the same criteria as the Product Critic prompt, applied deterministically.
    """
    public_verified = _count_public_claims(graph, "reputable_snippet")
    official_sources = _count_official_sources(graph)
    covered_topics = _count_covered_topics(graph)
    total_public = sum(1 for c in graph.claims if getattr(c, "public_claim_eligible", False))
    source_count = len(graph.sources)

    caveats: list[str] = []
    new_queries: list[str] = []

    if official_sources == 0:
        caveats.append("No official/primary sources found")
    if public_verified < 3:
        caveats.append(f"Only {public_verified} verified public claims")
    if covered_topics < 2:
        caveats.append(f"Only {covered_topics} topics covered by verified claims")

    if total_public < 2:
        return {
            "decision": "not_acceptable",
            "reasoning": f"Only {total_public} public-eligible claims — insufficient to build a page.",
            "new_queries": [],
            "caveats": caveats,
        }

    if public_verified < 3 or covered_topics < 2:
        return {
            "decision": "evidence_limited",
            "reasoning": f"{public_verified} verified claims covering {covered_topics} topics. Evidence is thin.",
            "new_queries": [],
            "caveats": caveats,
        }

    if official_sources == 0:
        return {
            "decision": "editor_review",
            "reasoning": f"{public_verified} verified claims but no official sources.",
            "new_queries": [],
            "caveats": caveats,
        }

    if public_verified >= 5 and official_sources >= 1 and covered_topics >= 3:
        return {
            "decision": "publishable",
            "reasoning": f"{public_verified} verified claims, {official_sources} official sources, {covered_topics} topics covered.",
            "new_queries": [],
            "caveats": [],
        }

    return {
        "decision": "editor_review",
        "reasoning": f"Borderline: {public_verified} verified claims, {official_sources} official sources.",
        "new_queries": [],
        "caveats": caveats,
    }


def run_evidence_gate(
    graph: EvidenceGraph,
    event_type: str,
    sentence: str,
    today: date,
    run_ai: bool = True,
) -> dict[str, Any]:
    """Evaluate evidence sufficiency after research.

    Uses deterministic rules as the primary check. Optionally enriches
    with an LLM call for search query suggestions when evidence is thin.
    """
    # Always run deterministic check first
    result = _deterministic_evidence_decision(graph, event_type)

    if not run_ai or result["decision"] == "publishable":
        return result

    # For non-publishable results, optionally ask LLM for targeted search queries
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return result

    try:
        client = instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))
        messages = build_product_critic_messages(graph, event_type, sentence, today)

        class GateOutput(PydanticBaseModel):
            model_config = {"extra": "forbid"}
            decision: str = PydanticField(default="publishable")
            reasoning: str = PydanticField(default="")
            new_queries: list[str] = PydanticField(default_factory=list)
            caveats: list[str] = PydanticField(default_factory=list)

        llm_result = client.messages.create(
            model=MODEL_NAME, max_tokens=600,
            messages=messages, response_model=GateOutput,
        )
        # Use LLM's search queries but keep deterministic decision as floor
        new_queries = list(llm_result.new_queries or [])[:6]
        llm_caveats = list(llm_result.caveats or [])[:5]
        return {
            "decision": result["decision"],
            "reasoning": llm_result.reasoning or result["reasoning"],
            "new_queries": new_queries,
            "caveats": list(set(result["caveats"] + llm_caveats)),
        }
    except Exception as exc:
        LOGGER.warning("Evidence Gate LLM enrichment failed: %s", exc)
        return result


# Backward-compatible alias — used by orchestrator
run_product_critic = run_evidence_gate


# ---------------------------------------------------------------------------
# Page Gate (formerly Page Critic)
# ---------------------------------------------------------------------------

def _build_page_summary(
    page: TopicPageData,
    evidence_graph: EvidenceGraph,
    qa_report: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact structured summary for the Page Gate LLM review.

    This replaces the old approach of sending the full rendered HTML
    (~8000 tokens of CSS + content). The summary is ~800 tokens and
    contains everything the LLM needs to judge page quality.
    """
    sections_summary = []
    for s in page.sections:
        claim_count = sum(1 for i in s.items if getattr(i, "claim_id", None))
        sections_summary.append({
            "type": s.component_type.value if hasattr(s.component_type, "value") else str(s.component_type),
            "title": s.title,
            "item_count": len(s.items),
            "items_with_claims": claim_count,
        })

    sources_by_type: dict[str, int] = {}
    for src in evidence_graph.sources:
        st = getattr(src.source_type, "value", str(src.source_type))
        sources_by_type[st] = sources_by_type.get(st, 0) + 1

    contradictions_shown = sum(
        1 for c in evidence_graph.contradictions
        if getattr(c, "ai_resolution", None)
        and str(getattr(c.ai_resolution, "value", c.ai_resolution)) == "real_uncertainty"
    )

    return {
        "headline": page.headline,
        "event_type": page.event_type.value if hasattr(page.event_type, "value") else str(page.event_type),
        "confidence": page.confidence.value if hasattr(page.confidence, "value") else str(page.confidence),
        "section_count": len(page.sections),
        "total_items": sum(len(s.items) for s in page.sections),
        "sections": sections_summary,
        "qa_passed": qa_report.get("passed", False),
        "qa_score": qa_report.get("confidence_score", 0),
        "qa_failed_gates": qa_report.get("failed_gates", []),
        "items_repaired": qa_report.get("items_repaired", 0),
        "source_count": len(evidence_graph.sources),
        "sources_by_type": sources_by_type,
        "public_claim_count": sum(
            1 for c in evidence_graph.claims
            if getattr(c, "public_claim_eligible", False)
        ),
        "contradictions_shown": contradictions_shown,
        "contradiction_topics": [
            c.topic for c in evidence_graph.contradictions
            if getattr(c, "ai_resolution", None)
            and str(getattr(c.ai_resolution, "value", c.ai_resolution)) == "real_uncertainty"
        ],
    }


def run_page_gate(
    page: TopicPageData,
    evidence_graph: EvidenceGraph,
    qa_report: dict[str, Any],
    run_ai: bool = True,
) -> dict[str, str]:
    """Evaluate final page quality from structured data.

    Receives a compact page summary (~800 tokens) instead of raw HTML.
    This fixes the max_tokens exhaustion that made the old Page Critic
    dead code (all 9 calls across 3 runs failed silently).
    """
    if not run_ai:
        return {"decision": "editor_review", "reasoning": "AI gate disabled."}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"decision": "editor_review", "reasoning": "No API key."}

    summary = _build_page_summary(page, evidence_graph, qa_report)

    client = instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))
    messages = build_page_critic_messages(summary)

    class PageGateOutput(PydanticBaseModel):
        model_config = {"extra": "forbid"}
        decision: str = PydanticField(default="editor_review")
        reasoning: str = PydanticField(default="", max_length=600)

    try:
        # max_tokens=2000 is generous for a 2-field response. The old 500
        # caused instructor's retry loop (500→1000→1500) to exhaust all
        # attempts because each retry embeds the previous partial output
        # in the conversation, making the required output longer. A single
        # generous limit prevents any retry at all.
        result = client.messages.create(
            model=MODEL_NAME, max_tokens=2000,
            messages=messages, response_model=PageGateOutput,
        )
        return {
            "decision": result.decision,
            "reasoning": result.reasoning or "",
        }
    except Exception as exc:
        LOGGER.warning("Page Gate failed: %s", exc)
        return {"decision": "editor_review", "reasoning": f"Gate unavailable: {exc}"}


# Backward-compatible alias
run_page_critic = run_page_gate
