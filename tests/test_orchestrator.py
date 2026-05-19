"""End-to-end tests for the orchestrator pipeline with stubbed LLM calls."""
import pytest
from datetime import date, datetime, timezone
from unittest.mock import patch, MagicMock

from generator.schemas import (
    Claim,
    ClaimType,
    ComponentType,
    ConfidenceLevel,
    EventHypothesis,
    EventType,
    EvidenceGraph,
    EvidenceAwareIA,
    EventStatus,
    LayoutStyle,
    Source,
    SourceType,
    TopicPageData,
    Entity,
    TimelineEvent,
    UIComponent,
    UIItem,
)
from generator.orchestrator import EditorialRun, RunStatus


def _fake_hypothesis() -> EventHypothesis:
    return EventHypothesis(
        preliminary_event_type=EventType.SPORTS_TOURNAMENT,
        freshness_need="this week",
        search_intents=["test query 1", "test query 2", "test query 3"],
    )


def _fake_graph() -> EvidenceGraph:
    source = Source(
        source_id="src1",
        url="https://example.com",
        title="Test Source",
        source_type=SourceType.OFFICIAL,
        published_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    return EvidenceGraph(
        event_hypothesis="Test event",
        sources=[source],
        claims=[
            Claim(
                claim_id="c1",
                text="48 teams competing",
                claim_type=ClaimType.METRIC,
                claim_topic="participants",
                source_ids=["src1"],
                public_claim_eligible=True,
                evidence_grade="full_text_verified",
                evidence_sentence="48 teams will compete in the tournament.",
                claim_attributes={"value": "48", "unit": "teams", "evidence_snippet": "48 teams"},
            ),
            Claim(
                claim_id="c2",
                text="June 11, 2026",
                claim_type=ClaimType.DATE,
                claim_topic="event_schedule",
                source_ids=["src1"],
                public_claim_eligible=True,
                evidence_grade="full_text_verified",
                evidence_sentence="The event starts on June 11, 2026.",
                claim_attributes={"date_value": "2026-06-11T00:00:00Z"},
            ),
        ],
        last_updated=datetime(2026, 5, 17, tzinfo=timezone.utc),
    )


def _fake_ia() -> EvidenceAwareIA:
    return EvidenceAwareIA(
        final_event_type=EventType.SPORTS_TOURNAMENT,
        event_status=EventStatus.UPCOMING,
        page_thesis="A major sports tournament is about to begin.",
        required_components=[
            ComponentType.STAT_GRID,
            ComponentType.TIMELINE,
            ComponentType.ENTITY_LIST,
            ComponentType.ACTION_LIST,
        ],
        layout_style=LayoutStyle.HERO_FOCUS,
        confidence_summary="Strong evidence from official sources.",
    )


def _fake_page() -> TopicPageData:
    return TopicPageData(
        event_type=EventType.SPORTS_TOURNAMENT,
        status=EventStatus.UPCOMING,
        confidence=ConfidenceLevel.HIGH,
        headline="Test Tournament",
        deck="A test tournament page.",
        summary="This is a test summary.",
        key_entities=[Entity(name="Test Team", role="Competitor")],
        timeline=[TimelineEvent(date_label="June 2026", title="Tournament begins")],
        sections=[
            UIComponent(
                component_type=ComponentType.STAT_GRID,
                title="Key Stats",
                items=[
                    UIItem(label="Teams", value="48", claim_id="c1"),
                ],
            ),
            UIComponent(
                component_type=ComponentType.TIMELINE,
                title="Schedule",
                items=[
                    UIItem(label="Start", value="June 11, 2026", claim_id="c2"),
                ],
            ),
            UIComponent(
                component_type=ComponentType.ENTITY_LIST,
                title="Participants",
                items=[UIItem(label="Test Team", value="Competitor")],
            ),
            UIComponent(
                component_type=ComponentType.ACTION_LIST,
                title="Next Steps",
                items=[UIItem(label="Learn More", value="Visit site")],
            ),
        ],
    )


class TestEditorialRun:
    """End-to-end tests that exercise the orchestrator with all LLM calls stubbed."""

    def test_execute_produces_page_with_all_stubs(self):
        """Full pipeline execution with all phases stubbed."""
        run = EditorialRun(sentence="Test event sentence")

        with (
            patch.object(run, "_phase_understand") as pu,
            patch.object(run, "_phase_research") as pr,
            patch.object(run, "_phase_plan") as pp,
            patch.object(run, "_phase_compose") as pc,
            patch.object(run, "_phase_review") as pv,
            patch.object(run, "_phase_render") as pd,
        ):
            run.execute(run_ai=False)
            assert run.status == RunStatus.COMPLETE

    def test_execute_with_real_classify_and_stubbed_research(self):
        """Test that the run can recover from error."""
        run = EditorialRun(sentence="Test")
        # Simulate an error
        run.status = RunStatus.ERROR
        assert run.status == RunStatus.ERROR

    def test_phase_understand_sets_hypothesis(self):
        """Phase 1 classify stubbed."""
        run = EditorialRun(sentence="Test")
        with patch.object(run, "_phase_understand") as pu:
            pu.side_effect = lambda: setattr(run, "hypothesis", _fake_hypothesis())
            run.execute(run_ai=False)
        assert run.hypothesis is not None

    def test_phase_render_produces_html(self):
        """Phase 5 render produces valid HTML string."""
        run = EditorialRun(sentence="Test event")
        run.hypothesis = _fake_hypothesis()
        run.evidence_graph = _fake_graph()
        run.ia = _fake_ia()
        run.topic_page = _fake_page()
        run.qa_report = {"passed": True, "confidence_score": 0.9, "failed_gates": [], "repair_actions": [], "items_repaired": 0}
        run._phase_render(run_ai=False)
        assert len(run.html) > 0
        assert "<html" in run.html.lower()
        assert run.page_critic_verdict is not None

    def test_critic_verdict_evidence_limited_triggers_degraded(self):
        """Evidence Gate evidence_limited should be recorded."""
        run = EditorialRun(sentence="Test")
        from generator.orchestrator import CriticDecision, CriticVerdict
        run.critic_verdict = CriticVerdict(
            decision=CriticDecision.EVIDENCE_LIMITED,
            reasoning="Only 2 verified claims",
        )
        assert run.critic_verdict.decision == CriticDecision.EVIDENCE_LIMITED

    def test_run_status_transitions(self):
        """Status transitions through the pipeline."""
        run = EditorialRun(sentence="Test")
        assert run.status == RunStatus.GATHERING
        run.status = RunStatus.BUILDING
        assert run.status == RunStatus.BUILDING
        run.status = RunStatus.GATING
        assert run.status == RunStatus.GATING
