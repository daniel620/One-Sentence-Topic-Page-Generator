from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from generator.quality import QARunner, event_fit_gate, factuality_gate, freshness_gate
from generator.schemas import (
    Claim,
    ClaimType,
    ComponentType,
    ConfidenceLevel,
    Contradiction,
    DisplayPolicy,
    EventHypothesis,
    EvidenceAwareIA,
    EvidenceGraph,
    EventStatus,
    EventType,
    LayoutStyle,
    QARepairAction,
    QAGateResult,
    ResolutionPolicy,
    Source,
    SourceType,
    TopicPageData,
    UIComponent,
    UIItem,
    Entity,
    TimelineEvent,
)


def _base_graph(*, include_contradiction: bool = False) -> EvidenceGraph:
    source = Source(
        source_id="src1",
        url="https://example.com/source",
        title="Source",
        source_type=SourceType.OFFICIAL,
        published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    metric_claim = Claim(
        claim_id="m1",
        text="40% faster",
        claim_type=ClaimType.METRIC,
        source_ids=["src1"],
        claim_attributes={
            "value": "40",
            "unit": "percent",
            "evidence_snippet": "Benchmark shows 40% faster output.",
        },
    )
    status_claim = Claim(
        claim_id="s1",
        text="Rollout is live",
        claim_type=ClaimType.STATUS,
        source_ids=["src1"],
        claim_attributes={"status": "live"},
    )
    contradictions = []
    if include_contradiction:
        contradictions = [
            Contradiction(
                topic="Rollout timing",
                claim_a="Rollout started May 10",
                sources_a=["src1"],
                claim_b="Rollout started May 12",
                sources_b=["src2"],
                resolution=ResolutionPolicy.UNRESOLVED,
                display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
            )
        ]
    return EvidenceGraph(
        event_hypothesis="Test event",
        sources=[source],
        claims=[metric_claim, status_claim],
        contradictions=contradictions,
        last_updated=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )


def _page(
    *,
    event_type: EventType = EventType.TECH_LAUNCH,
    status: EventStatus = EventStatus.UPCOMING,
    sections: list[UIComponent] | None = None,
) -> TopicPageData:
    sections = sections or [
        UIComponent(
            component_type=ComponentType.STAT_GRID,
            title="Key metrics",
            items=[UIItem(label="Speed", value="40% faster", claim_id="m1")],
        ),
        UIComponent(
            component_type=ComponentType.ACTION_LIST,
            title="What to do",
            items=[UIItem(label="Read more", value="Review the launch notes")],
        ),
    ]
    return TopicPageData(
        event_type=event_type,
        status=status,
        confidence=ConfidenceLevel.HIGH,
        headline="Test headline",
        summary="Test summary",
        key_entities=[Entity(name="Test", role="Topic")],
        timeline=[TimelineEvent(date_label="May 2026", title="Launch")],
        sections=sections,
    )


def test_missing_claim_id_fails_factuality_gate() -> None:
    graph = _base_graph()
    page = _page(
        sections=[
            UIComponent(
                component_type=ComponentType.STAT_GRID,
                title="Key metrics",
                items=[UIItem(label="Speed", value="40% faster")],
            ),
            UIComponent(
                component_type=ComponentType.ACTION_LIST,
                title="What to do",
                items=[UIItem(label="Read more", value="Review the launch notes")],
            ),
        ]
    )
    result = factuality_gate(page, graph, datetime(2026, 5, 15, tzinfo=timezone.utc).date())

    assert result.status == "fail"
    assert QARepairAction.MISSING_CLAIM_ID in result.repair_actions


def test_weak_source_lowers_confidence() -> None:
    source = Source(
        source_id="src1",
        url="https://example.com/source",
        title="Source",
        source_type=SourceType.UNKNOWN,
        authority_score=0.3,
        published_at=datetime(2026, 4, 20, tzinfo=timezone.utc),
    )
    graph = EvidenceGraph(
        event_hypothesis="Test event",
        sources=[source],
        claims=[],
        last_updated=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    page = _page(status=EventStatus.CONCLUDED)
    result = freshness_gate(page, graph, datetime(2026, 5, 15, tzinfo=timezone.utc).date())

    assert result.confidence_score < 1.0
    assert QARepairAction.WEAK_SOURCE in result.repair_actions


def test_stale_source_fails_for_live_event() -> None:
    source = Source(
        source_id="src1",
        url="https://example.com/source",
        title="Source",
        source_type=SourceType.OFFICIAL,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    graph = EvidenceGraph(
        event_hypothesis="Test event",
        sources=[source],
        claims=[],
        last_updated=None,
    )
    page = _page(status=EventStatus.LIVE)
    result = freshness_gate(page, graph, datetime(2026, 5, 15, tzinfo=timezone.utc).date())

    assert result.status == "fail"
    assert QARepairAction.STALE_SOURCE in result.repair_actions


def test_conflicting_claim_surfaces_repair_actions() -> None:
    graph = _base_graph(include_contradiction=True)
    page = _page()
    result = factuality_gate(page, graph, datetime(2026, 5, 15, tzinfo=timezone.utc).date())

    assert result.status == "fail"
    assert QARepairAction.CONFLICTING_CLAIM in result.repair_actions


def test_missing_required_component_and_undefined_component_detected() -> None:
    graph = _base_graph()
    ia = EvidenceAwareIA(
        final_event_type=EventType.SPORTS_TOURNAMENT,
        event_status=EventStatus.UPCOMING,
        page_thesis="Test thesis",
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ],
        layout_style=LayoutStyle.DASHBOARD,
        confidence_summary="Test.",
    )
    page = SimpleNamespace(
        event_type=EventType.SPORTS_TOURNAMENT,
        status=EventStatus.UPCOMING,
        sections=[
            SimpleNamespace(component_type="undefined_widget", items=[SimpleNamespace(label="x", value="y")]),
            UIComponent(
                component_type=ComponentType.STAT_GRID,
                title="Stats",
                items=[UIItem(label="Wins", value="12", claim_id="m1")],
            ),
        ],
    )

    result = event_fit_gate(page, graph, ia)

    assert result.status == "fail"
    assert QARepairAction.UNDEFINED_COMPONENT in result.repair_actions
    assert QARepairAction.MISSING_REQUIRED_COMPONENT in result.repair_actions

