from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from generator.prompts import build_stage1a_messages, build_stage1b_messages, build_stage3_messages
from generator.schemas import (
    EventHypothesis,
    EventStatus,
    EventType,
    EvidenceAwareIA,
    EvidenceGraph,
    EVENT_TYPE_REQUIREMENTS,
    LayoutStyle,
    SourceType,
)


FIXTURE_DIR = Path("tests/fixtures")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_stage1a_prompt_only_requests_hypothesis() -> None:
    messages = build_stage1a_messages("GPT-5.5 release", date(2026, 5, 15))
    joined = "\n".join(message["content"] for message in messages)

    assert "EventHypothesis" in joined
    assert "EventContext" not in joined
    assert "Return EventHypothesis" in joined
    assert "search_intents" in joined


def test_stage1b_prompt_uses_evidence_graph_and_uncertainty() -> None:
    payload = load_fixture("tech_launch_gpt55.json")
    graph = EvidenceGraph.model_validate(payload["evidence_graph"])
    hypothesis = EventHypothesis(
        preliminary_event_type=EventType.TECH_LAUNCH,
        freshness_need="Recent data within 24 hours",
        search_intents=["GPT-5.5 Instant default", "OpenAI rollout"],
        required_source_types=[],
        unknowns=["pricing"],
    )
    messages = build_stage1b_messages(hypothesis, graph, date(2026, 5, 15))
    joined = "\n".join(message["content"] for message in messages)

    assert "EvidenceGraph" in joined
    assert "uncertainty_box" in joined
    assert "layout_style" in joined
    assert "final_event_type" in joined
    assert "mandatory components" in joined.lower()  # injected from EVENT_TYPE_REQUIREMENTS


def test_stage3_prompt_requires_claim_traceability() -> None:
    payload = load_fixture("tech_launch_gpt55.json")
    graph = EvidenceGraph.model_validate(payload["evidence_graph"])
    ia = EvidenceAwareIA(
        final_event_type=EventType.TECH_LAUNCH,
        event_status=EventStatus.CONCLUDED,
        page_thesis="Explain what changed and why it matters.",
        required_components=list(EVENT_TYPE_REQUIREMENTS[EventType.TECH_LAUNCH].required_components),
        layout_style=LayoutStyle.DASHBOARD,
        confidence_summary="Strong official and media coverage.",
    )
    messages = build_stage3_messages(graph, ia, date(2026, 5, 15))
    joined = "\n".join(message["content"] for message in messages)

    assert "claim_id" in joined
    assert "claim cards" in joined.lower()  # composer prompt uses claim cards, not raw EvidenceGraph
    assert "compose" in joined.lower()      # system prompt says "compose", not "write"


def test_tech_launch_fixture_has_evidence_and_official_source() -> None:
    payload = load_fixture("tech_launch_gpt55.json")
    graph = EvidenceGraph.model_validate(payload["evidence_graph"])
    # Real evidence: at least a few sources, at least a few claims.
    assert len(graph.sources) >= 5
    assert len(graph.claims) >= 5
    # The brief asks for grounded pages — at least one source should be official.
    assert any(s.source_type == SourceType.OFFICIAL for s in graph.sources)


def test_live_event_fixture_has_evidence_and_official_source() -> None:
    payload = load_fixture("live_event_eurovision.json")
    graph = EvidenceGraph.model_validate(payload["evidence_graph"])
    assert len(graph.sources) >= 5
    assert len(graph.claims) >= 5
    assert any(s.source_type == SourceType.OFFICIAL for s in graph.sources)


def test_sports_tournament_fixture_has_evidence_and_official_source() -> None:
    payload = load_fixture("sports_tournament_worldcup.json")
    graph = EvidenceGraph.model_validate(payload["evidence_graph"])
    assert len(graph.sources) >= 5
    assert len(graph.claims) >= 5
    assert any(s.source_type == SourceType.OFFICIAL for s in graph.sources)
