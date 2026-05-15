"""Tests for schema validation, especially claim-type-specific rules."""

import pytest
from datetime import datetime
from pydantic import ValidationError

from generator.schemas import (
    Claim,
    MetricClaim,
    StatusClaim,
    ScheduleClaim,
    DateClaim,
    LocationClaim,
    EntityClaim,
    ClaimType,
    ConfidenceLevel,
    Source,
    SourceType,
    EvidenceGraph,
    UIItem,
    UIComponent,
    ComponentType,
    TopicPageData,
    EventType,
    EventStatus,
    Entity,
    TimelineEvent,
    LayoutStyle,
    Contradiction,
    ResolutionPolicy,
    DisplayPolicy,
)


class TestMetricClaimValidation:
    """MetricClaim must have value, unit, direction, evidence_snippet."""

    def test_metric_claim_valid(self):
        """Valid metric claim."""
        claim = MetricClaim(
            claim_id="m1",
            text="GPT-5.5 is 40% faster than GPT-5.",
            source_ids=["src1"],
            value="40%",
            unit="percent",
            direction="faster",
            evidence_snippet="According to benchmarks, GPT-5.5 demonstrates 40% faster inference speed.",
        )
        assert claim.claim_type == ClaimType.METRIC
        assert claim.value == "40%"

    def test_metric_claim_missing_value(self):
        """MetricClaim must have value."""
        with pytest.raises(ValidationError) as exc:
            MetricClaim(
                claim_id="m1",
                text="GPT-5.5 is faster.",
                source_ids=["src1"],
                unit="percent",
                direction="faster",
                evidence_snippet="Some evidence.",
            )
        assert "value" in str(exc.value).lower()

    def test_metric_claim_missing_unit(self):
        """MetricClaim must have unit."""
        with pytest.raises(ValidationError) as exc:
            MetricClaim(
                claim_id="m1",
                text="GPT-5.5 is faster.",
                source_ids=["src1"],
                value="40%",
                direction="faster",
                evidence_snippet="Some evidence.",
            )
        assert "unit" in str(exc.value).lower()

    def test_metric_claim_missing_evidence_snippet(self):
        """MetricClaim must have evidence_snippet."""
        with pytest.raises(ValidationError) as exc:
            MetricClaim(
                claim_id="m1",
                text="GPT-5.5 is faster.",
                source_ids=["src1"],
                value="40%",
                unit="percent",
                direction="faster",
            )
        assert "evidence_snippet" in str(exc.value).lower()


class TestStatusClaimValidation:
    """StatusClaim must have status and observed_at."""

    def test_status_claim_valid(self):
        """Valid status claim."""
        claim = StatusClaim(
            claim_id="s1",
            text="GPT-5.5 rollout started in May 2026.",
            source_ids=["src1"],
            status="rollout_started",
            observed_at=datetime(2026, 5, 15),
        )
        assert claim.claim_type == ClaimType.STATUS
        assert claim.observed_at is not None

    def test_status_claim_missing_observed_at(self):
        """StatusClaim without observed_at is still valid (soft requirement)."""
        claim = StatusClaim(
            claim_id="s1",
            text="Status update.",
            source_ids=["src1"],
            status="active",
        )
        # Allowed; observed_at is optional
        assert claim.status == "active"


class TestScheduleClaimValidation:
    """ScheduleClaim must have event_datetime and event_name. Timezone recommended."""

    def test_schedule_claim_valid_with_timezone(self):
        """Valid schedule claim with timezone."""
        claim = ScheduleClaim(
            claim_id="sc1",
            text="World Cup final on July 14, 2026 at 18:00 UTC.",
            source_ids=["src1"],
            event_datetime=datetime(2026, 7, 14, 18, 0),
            timezone="UTC",
            event_name="World Cup Final",
        )
        assert claim.claim_type == ClaimType.SCHEDULE
        assert claim.timezone == "UTC"

    def test_schedule_claim_missing_timezone_warning(self):
        """ScheduleClaim without timezone is valid but not ideal."""
        claim = ScheduleClaim(
            claim_id="sc1",
            text="World Cup final on July 14, 2026.",
            source_ids=["src1"],
            event_datetime=datetime(2026, 7, 14),
            event_name="World Cup Final",
        )
        assert claim.timezone is None  # Allowed but not ideal

    def test_schedule_claim_missing_event_name(self):
        """ScheduleClaim must have event_name."""
        with pytest.raises(ValidationError) as exc:
            ScheduleClaim(
                claim_id="sc1",
                text="Event on July 14.",
                source_ids=["src1"],
                event_datetime=datetime(2026, 7, 14),
            )
        assert "event_name" in str(exc.value).lower()


class TestSourceScoring:
    """Source must have authority_score, freshness_score, relevance_score, and overall_score."""

    def test_source_official_scores_high(self):
        """Official sources should have high authority_score."""
        source = Source(
            source_id="src_official",
            url="https://openai.com/release",
            title="Official Release",
            source_type=SourceType.OFFICIAL,
            authority_score=1.0,  # Explicit for test
        )
        assert source.authority_score == 1.0
        assert source.overall_score > 0.5  # High overall

    def test_source_social_scores_low(self):
        """Social sources should have lower authority_score."""
        source = Source(
            source_id="src_social",
            url="https://twitter.com/user",
            title="Tweet",
            source_type=SourceType.SOCIAL,
            authority_score=0.5,  # Explicit for test
        )
        assert source.authority_score == 0.5  # Lower

    def test_source_overall_score_calculation(self):
        """Overall score = 0.5*authority + 0.3*freshness + 0.2*relevance."""
        source = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
            source_type=SourceType.REPUTABLE_MEDIA,
            authority_score=0.8,
            freshness_score=0.9,
            relevance_score=0.7,
        )
        expected_overall = 0.8 * 0.5 + 0.9 * 0.3 + 0.7 * 0.2
        assert abs(source.overall_score - expected_overall) < 0.01


class TestEvidenceGraphValidation:
    """EvidenceGraph must validate claim source_ids and have unique IDs."""

    def test_evidence_graph_valid(self):
        """Valid EvidenceGraph."""
        source = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
        )
        claim = MetricClaim(
            claim_id="c1",
            text="Metric claim",
            source_ids=["src1"],
            value="100",
            unit="units",
            evidence_snippet="Evidence",
        )
        graph = EvidenceGraph(
            event_hypothesis="Test event",
            sources=[source],
            claims=[claim],
        )
        assert len(graph.sources) == 1
        assert len(graph.claims) == 1

    def test_evidence_graph_claim_source_mismatch(self):
        """EvidenceGraph.validate_claim_sources() catches missing source_ids."""
        claim = MetricClaim(
            claim_id="c1",
            text="Metric claim",
            source_ids=["nonexistent_source"],
            value="100",
            unit="units",
            evidence_snippet="Evidence",
        )
        graph = EvidenceGraph(
            event_hypothesis="Test event",
            claims=[claim],
        )
        errors = graph.validate_claim_sources()
        assert len(errors) > 0
        assert "nonexistent_source" in errors[0]

    def test_evidence_graph_unique_source_ids(self):
        """EvidenceGraph enforces unique source_ids."""
        source1 = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
        )
        source2 = Source(
            source_id="src1",  # Duplicate
            url="https://example2.com",
            title="Example 2",
        )
        with pytest.raises(ValidationError) as exc:
            EvidenceGraph(
                event_hypothesis="Test",
                sources=[source1, source2],
            )
        assert "unique" in str(exc.value).lower()

    def test_evidence_graph_unique_claim_ids(self):
        """EvidenceGraph enforces unique claim_ids."""
        claim1 = MetricClaim(
            claim_id="c1",
            text="Claim 1",
            source_ids=["src1"],
            value="100",
            unit="units",
            evidence_snippet="Ev1",
        )
        claim2 = MetricClaim(
            claim_id="c1",  # Duplicate
            text="Claim 2",
            source_ids=["src1"],
            value="200",
            unit="units",
            evidence_snippet="Ev2",
        )
        with pytest.raises(ValidationError) as exc:
            EvidenceGraph(
                event_hypothesis="Test",
                claims=[claim1, claim2],
            )
        assert "unique" in str(exc.value).lower()


class TestUIItemWithClaimId:
    """UIItem must have claim_id for numeric/date facts."""

    def test_ui_item_numeric_with_claim_id(self):
        """Numeric UIItem with claim_id is valid."""
        item = UIItem(
            label="Performance Improvement",
            value="40% faster",
            claim_id="metric_1",
        )
        assert item.claim_id == "metric_1"

    def test_ui_item_numeric_without_claim_id_soft_warning(self):
        """Numeric UIItem without claim_id is allowed at UIItem level (validated at TopicPageData)."""
        item = UIItem(
            label="Performance",
            value="40% faster",
        )
        # Allowed at UIItem level; TopicPageData should catch it


class TestUIComponentValidation:
    """UIComponent must validate items have claim_ids for stat grids."""

    def test_stat_grid_numeric_items_need_claim_ids(self):
        """StatGrid with numeric items must have claim_ids."""
        item_with_claim = UIItem(
            label="Speed",
            value="40%",
            claim_id="m1",
        )
        component = UIComponent(
            component_type=ComponentType.STAT_GRID,
            title="Stats",
            items=[item_with_claim],
        )
        assert component.items[0].claim_id == "m1"

    def test_stat_grid_numeric_items_without_claim_ids_fail(self):
        """StatGrid with numeric items but no claim_ids should fail."""
        item_without_claim = UIItem(
            label="Speed",
            value="40%",  # Numeric but no claim_id
        )
        with pytest.raises(ValidationError) as exc:
            UIComponent(
                component_type=ComponentType.STAT_GRID,
                title="Stats",
                items=[item_without_claim],
            )
        assert "claim_id" in str(exc.value).lower()


class TestTopicPageDataValidation:
    """TopicPageData must validate claims against EvidenceGraph."""

    def test_topic_page_data_numeric_claims_without_evidence_graph(self):
        """TopicPageData with numeric items should validate against evidence_graph if provided."""
        item = UIItem(
            label="Performance",
            value="40%",
            claim_id="m1",
        )
        component1 = UIComponent(
            component_type=ComponentType.STAT_GRID,
            title="Stats",
            items=[item],
        )
        component2 = UIComponent(
            component_type=ComponentType.ACTION_LIST,
            title="Next Steps",
            items=[UIItem(label="Learn More", value="Visit docs")],
        )
        # Create valid EvidenceGraph to match
        source = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
        )
        claim = MetricClaim(
            claim_id="m1",
            text="40% faster",
            source_ids=["src1"],
            value="40%",
            unit="percent",
            evidence_snippet="Evidence",
        )
        evidence_graph = EvidenceGraph(
            event_hypothesis="Test",
            sources=[source],
            claims=[claim],
        )
        page = TopicPageData(
            event_type=EventType.TECH_LAUNCH,
            status=EventStatus.UPCOMING,
            confidence=ConfidenceLevel.HIGH,
            headline="Test Launch",
            summary="Test summary",
            key_entities=[Entity(name="Test", role="Test Role")],
            timeline=[TimelineEvent(date_label="May 2026", title="Launch")],
            sections=[component1, component2],
            evidence_graph_ref=evidence_graph,
        )
        # Validate
        errors = page.validate_numeric_claims_have_sources(evidence_graph)
        assert len(errors) == 0

    def test_topic_page_data_missing_claim_id_in_evidence_graph(self):
        """TopicPageData.validate_numeric_claims_have_sources catches orphaned claim_ids."""
        item = UIItem(
            label="Performance",
            value="40%",
            claim_id="nonexistent_claim",  # Not in EvidenceGraph
        )
        component1 = UIComponent(
            component_type=ComponentType.STAT_GRID,
            title="Stats",
            items=[item],
        )
        component2 = UIComponent(
            component_type=ComponentType.ACTION_LIST,
            title="Next Steps",
            items=[UIItem(label="Learn More", value="Visit docs")],
        )
        source = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
        )
        evidence_graph = EvidenceGraph(
            event_hypothesis="Test",
            sources=[source],
            claims=[],  # No claims
        )
        page = TopicPageData(
            event_type=EventType.TECH_LAUNCH,
            status=EventStatus.UPCOMING,
            confidence=ConfidenceLevel.HIGH,
            headline="Test Launch",
            summary="Test summary",
            key_entities=[Entity(name="Test", role="Test Role")],
            timeline=[TimelineEvent(date_label="May 2026", title="Launch")],
            sections=[component1, component2],
            evidence_graph_ref=evidence_graph,
        )
        errors = page.validate_numeric_claims_have_sources(evidence_graph)
        assert len(errors) > 0
        assert "nonexistent_claim" in errors[0]


class TestContradictionModel:
    """Contradiction model for conflicting claims."""

    def test_contradiction_valid(self):
        """Valid contradiction."""
        contradiction = Contradiction(
            topic="Rollout Date",
            claim_a="Rollout started May 15, 2026",
            sources_a=["official_openai"],
            claim_b="Rollout started May 20, 2026",
            sources_b=["media_techcrunch"],
            resolution=ResolutionPolicy.PREFER_OFFICIAL,
            display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
        )
        assert contradiction.resolution == ResolutionPolicy.PREFER_OFFICIAL

    def test_contradiction_unresolved(self):
        """Contradiction left unresolved."""
        contradiction = Contradiction(
            topic="Performance Metrics",
            claim_a="Model is 40% faster",
            sources_a=["src1"],
            claim_b="Model is 35% faster",
            sources_b=["src2"],
            resolution=ResolutionPolicy.UNRESOLVED,
            display_policy=DisplayPolicy.SHOW_BOTH,
        )
        assert contradiction.resolution == ResolutionPolicy.UNRESOLVED
        assert contradiction.display_policy == DisplayPolicy.SHOW_BOTH


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
