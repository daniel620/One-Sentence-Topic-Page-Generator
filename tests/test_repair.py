"""Tests for deterministic page repair."""
import pytest
from datetime import datetime, timezone

from generator.schemas import (
    Claim,
    ClaimType,
    ComponentType,
    ConfidenceLevel,
    Contradiction,
    DisplayPolicy,
    EvidenceGraph,
    EventType,
    EventStatus,
    ResolutionPolicy,
    Source,
    SourceType,
    TopicPageData,
    UIComponent,
    UIItem,
    Entity,
    TimelineEvent,
    AIContradictionResolution,
)
from generator.repair import (
    repair_page,
    strip_conflicting_items,
    strip_missing_claim_items,
    compute_confidence,
)


def _make_graph(*, with_contradiction: bool = False) -> EvidenceGraph:
    source = Source(
        source_id="src1",
        url="https://example.com",
        title="Test Source",
        source_type=SourceType.OFFICIAL,
    )
    claim = Claim(
        claim_id="c1",
        text="40% faster",
        claim_type=ClaimType.METRIC,
        source_ids=["src1"],
        claim_attributes={
            "value": "40",
            "unit": "percent",
            "evidence_snippet": "Benchmark shows 40% faster.",
        },
    )
    contradictions = []
    if with_contradiction:
        contradictions.append(Contradiction(
            topic="speed measurement",
            claim_a="40% faster",
            sources_a=["src1"],
            claim_b="20% faster",
            sources_b=["src2"],
            resolution=ResolutionPolicy.UNRESOLVED,
            display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
            ai_resolution=AIContradictionResolution.REAL_UNCERTAINTY,
            ai_resolution_reason="Genuine conflict",
        ))
    return EvidenceGraph(
        event_hypothesis="Test event",
        sources=[source],
        claims=[claim],
        contradictions=contradictions,
    )


def _make_page(confidence: str = "high") -> TopicPageData:
    return TopicPageData(
        event_type=EventType.TECH_LAUNCH,
        status=EventStatus.CONCLUDED,
        confidence=ConfidenceLevel(confidence),
        headline="Test Page",
        summary="Test summary.",
        key_entities=[Entity(name="Test", role="Subject")],
        timeline=[TimelineEvent(date_label="Today", title="Test event")],
        sections=[
            UIComponent(
                component_type=ComponentType.STAT_GRID,
                title="Key Metrics",
                items=[UIItem(label="Speed", value="40% faster", claim_id="c1")],
            ),
            UIComponent(
                component_type=ComponentType.ACTION_LIST,
                title="Next Steps",
                items=[UIItem(label="Learn More", value="Visit docs")],
            ),
        ],
    )


class TestStripConflictingItems:
    def test_strips_item_backed_by_contradiction(self):
        graph = _make_graph(with_contradiction=True)
        page = _make_page()
        sections = list(page.sections)

        result, removed = strip_conflicting_items(sections, {"c1"})
        assert removed == 1
        assert len(result) == 1  # stat_grid removed (empty), action_list kept
        assert result[0].component_type == ComponentType.ACTION_LIST

    def test_no_change_when_no_conflicts(self):
        sections = list(_make_page().sections)
        result, removed = strip_conflicting_items(sections, set())
        assert removed == 0
        assert len(result) == 2


class TestStripMissingClaimItems:
    def test_strips_item_without_claim_id_in_stat_grid(self):
        page = _make_page()
        # Add an item without claim_id to the stat_grid
        page.sections[0].items.append(UIItem(label="No Claim", value="42%"))
        sections = list(page.sections)

        result, removed = strip_missing_claim_items(sections)
        assert removed == 1

    def test_keeps_items_with_claim_ids(self):
        sections = list(_make_page().sections)
        result, removed = strip_missing_claim_items(sections)
        assert removed == 0
        assert len(result) == 2

    def test_leaves_action_list_alone(self):
        """Action lists are editorial, not traceable — items without claim_ids are OK."""
        sections = [
            UIComponent(
                component_type=ComponentType.ACTION_LIST,
                title="Actions",
                items=[UIItem(label="Do X", value="Go here")],
            ),
        ]
        result, removed = strip_missing_claim_items(sections)
        assert removed == 0


class TestComputeConfidence:
    def test_no_removals_keeps_high(self):
        conf = compute_confidence(
            [_make_page().sections[0]], items_removed=0, original_qa_score=0.9,
        )
        assert conf == ConfidenceLevel.HIGH

    def test_many_removals_drops_to_low(self):
        conf = compute_confidence(
            [_make_page().sections[0]], items_removed=5, original_qa_score=0.7,
        )
        assert conf == ConfidenceLevel.LOW

    def test_few_removals_stays_medium(self):
        conf = compute_confidence(
            [_make_page().sections[0]], items_removed=2, original_qa_score=0.7,
        )
        assert conf == ConfidenceLevel.MEDIUM


class TestRepairPage:
    def test_repair_preserves_clean_page(self):
        graph = _make_graph()
        page = _make_page()
        repaired, summary = repair_page(page, graph, qa_score=0.9)
        assert summary["items_removed"] == 0
        assert len(repaired.sections) == 2

    def test_repair_strips_conflicting_items(self):
        graph = _make_graph(with_contradiction=True)
        page = _make_page()
        repaired, summary = repair_page(page, graph, qa_score=0.7)
        assert summary["items_removed"] >= 1

    def test_repair_drops_confidence_when_items_removed(self):
        graph = _make_graph(with_contradiction=True)
        page = _make_page()
        page.confidence = ConfidenceLevel.HIGH
        repaired, summary = repair_page(page, graph, qa_score=0.7)
        if summary["items_removed"] > 0:
            assert repaired.confidence != ConfidenceLevel.HIGH

    def test_repair_fills_missing_required_component(self):
        graph = _make_graph()
        page = _make_page()
        repaired, summary = repair_page(
            page, graph, qa_score=0.9,
            required_components=[ComponentType.TIMELINE],
        )
        present = {s.component_type for s in repaired.sections}
        assert ComponentType.TIMELINE in present
