"""Renderer tests.

Two invariants matter most:
  - Public mode never leaks internal trace UI (claim IDs, score numbers,
    QA gate names, layout/event-type pills, debug panel).
  - Debug mode does expose them for engineers reviewing the pipeline.

We also assert event-fit behavior: a high-confidence page without QA
failures must NOT render the editor's-note banner, and a contradiction in
the EvidenceGraph must surface an uncertainty notice.
"""
from __future__ import annotations

from datetime import datetime, timezone

from generator.render import render_topic_page
from generator.schemas import (
    Claim,
    ClaimType,
    ComponentType,
    ConfidenceLevel,
    Contradiction,
    DisplayPolicy,
    EvidenceGraph,
    EventStatus,
    EventType,
    KeyFact,
    QARepairAction,
    QAGateResult,
    RenderMode,
    ResolutionPolicy,
    Source,
    SourceType,
    TopicPageData,
    UIComponent,
    UIItem,
    Entity,
    TimelineEvent,
)


def _build_basic_page(
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    qa_results: list[QAGateResult] | None = None,
    contradictions: list[Contradiction] | None = None,
) -> TopicPageData:
    source = Source(
        source_id="src_official",
        url="https://example.com/official",
        title="Official Source",
        publisher="Official Press",
        source_type=SourceType.OFFICIAL,
        published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
    )
    metric_claim = Claim(
        claim_id="metric_speed",
        text="3x faster",
        claim_type=ClaimType.METRIC,
        source_ids=["src_official"],
        claim_attributes={
            "value": "3",
            "unit": "× faster",
            "evidence_snippet": "Benchmarks show 3x faster output.",
        },
    )
    status_claim = Claim(
        claim_id="status_live",
        text="Now default",
        claim_type=ClaimType.STATUS,
        source_ids=["src_official"],
        claim_attributes={"status": "default"},
    )
    graph = EvidenceGraph(
        event_hypothesis="Test event",
        sources=[source],
        claims=[metric_claim, status_claim],
        contradictions=contradictions or [],
        last_updated=datetime(2026, 5, 15, tzinfo=timezone.utc),
    )
    return TopicPageData(
        event_type=EventType.TECH_LAUNCH,
        status=EventStatus.CONCLUDED,
        confidence=confidence,
        headline="Test launch headline",
        deck="Test deck explaining the change in editorial voice.",
        summary="Test summary describing what happened and why it matters.",
        urgency_label="Rolled out",
        as_of_label="As of May 15, 2026",
        key_facts=[
            KeyFact(label="Switched on", value="May 5, 2026", claim_id="status_live"),
            KeyFact(label="Speed gain", value="3× faster", claim_id="metric_speed"),
            KeyFact(label="Scope", value="Consumer plans"),
        ],
        key_entities=[Entity(name="ExampleCo", role="Provider")],
        timeline=[TimelineEvent(date_label="May 5, 2026", title="Default switch")],
        sections=[
            UIComponent(
                component_type=ComponentType.COMPARISON_TABLE,
                title="What changed",
                items=[
                    UIItem(label="Latency", value="3× faster", claim_id="metric_speed"),
                ],
            ),
            UIComponent(
                component_type=ComponentType.STAT_GRID,
                title="Rollout",
                items=[UIItem(label="Status", value="Now default", claim_id="status_live")],
            ),
            UIComponent(
                component_type=ComponentType.ACTION_LIST,
                title="What to do",
                items=[UIItem(label="Read the post", value="See the announcement")],
            ),
        ],
        evidence_graph_ref=graph,
        qa_results=qa_results or [
            QAGateResult(gate_name="factuality", status="pass", confidence_score=1.0),
            QAGateResult(gate_name="freshness", status="pass", confidence_score=1.0),
            QAGateResult(gate_name="event_fit", status="pass", confidence_score=1.0),
        ],
    )


# ---------------------------------------------------------------------------
# Public-mode invariants
# ---------------------------------------------------------------------------

def test_public_render_hides_internal_trace_ui() -> None:
    page = _build_basic_page()
    html = render_topic_page(page, mode=RenderMode.PUBLIC)

    # No claim IDs anywhere in the public DOM.
    assert "metric_speed" not in html
    assert "claim_id=" not in html
    # No QA gate names.
    assert "factuality" not in html
    assert "Repair action" not in html
    # No layout / event-type pills.
    assert "Layout:" not in html
    assert "Type: tech_launch" not in html
    # No debug panel element rendered (CSS rule may exist; the section must not).
    assert '<section class="debug-panel"' not in html
    assert "Render mode: debug" not in html


def test_public_render_shows_editorial_citation() -> None:
    page = _build_basic_page()
    html = render_topic_page(page, mode=RenderMode.PUBLIC)
    # Editorial citation: publisher name appears (with date) — not a numeric score.
    assert "Official Press" in html
    assert "May 10, 2026" in html
    # No raw score numbers.
    assert "Score 0." not in html
    assert "Score 1." not in html


def test_public_render_high_confidence_no_warning_banner() -> None:
    """Bug from earlier audit: confidence warning fired even on HIGH pages."""
    page = _build_basic_page(confidence=ConfidenceLevel.HIGH)
    html = render_topic_page(page, mode=RenderMode.PUBLIC)
    assert "Editor's note" not in html
    assert "Heads up" not in html


def test_public_render_low_confidence_does_show_editor_note() -> None:
    page = _build_basic_page(
        confidence=ConfidenceLevel.LOW,
        qa_results=[
            QAGateResult(
                gate_name="factuality",
                status="fail",
                failed_items=["one item"],
                repair_actions=[QARepairAction.MISSING_CLAIM_ID],
                confidence_score=0.3,
                remediation_suggestions=["fix it"],
            ),
        ],
    )
    html = render_topic_page(page, mode=RenderMode.PUBLIC)
    assert "Editor's note" in html
    # Still no internal jargon — the banner uses humanized labels.
    assert "missing_claim_id" not in html
    assert "factuality" not in html


def test_public_render_surfaces_contradictions_editorially() -> None:
    page = _build_basic_page(
        contradictions=[
            Contradiction(
                topic="Rollout timing",
                claim_a="Switched on May 5",
                sources_a=["src_official"],
                claim_b="Switched on May 8",
                sources_b=["src_official"],
                resolution=ResolutionPolicy.UNRESOLVED,
                display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
            )
        ],
    )
    html = render_topic_page(page, mode=RenderMode.PUBLIC)
    assert "Rollout timing" in html
    assert "Switched on May 5" in html
    assert "Switched on May 8" in html


def test_public_render_uses_event_specific_theme() -> None:
    page = _build_basic_page()
    html = render_topic_page(page, mode=RenderMode.PUBLIC)
    # Tech launches resolve to the editorial theme.
    assert "theme-editorial" in html
    assert "variant-delta" in html
    assert "event-tech_launch" in html


# ---------------------------------------------------------------------------
# Debug-mode invariants
# ---------------------------------------------------------------------------

def test_debug_render_exposes_claim_ids_and_qa_trace() -> None:
    page = _build_basic_page()
    html = render_topic_page(page, mode=RenderMode.DEBUG)

    assert "metric_speed" in html
    assert "debug-panel" in html
    assert "Render mode: debug" in html


def test_debug_render_string_mode_accepted() -> None:
    page = _build_basic_page()
    html = render_topic_page(page, mode="debug")
    assert "debug-panel" in html
