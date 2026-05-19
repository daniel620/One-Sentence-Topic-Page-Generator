"""Tests for schema validation with unified Claim model."""
import pytest
from datetime import datetime
from pydantic import ValidationError

from generator.schemas import (
    Claim,
    ClaimType,
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
    Contradiction,
    ResolutionPolicy,
    DisplayPolicy,
    ConfidenceLevel,
)


class TestClaimModel:
    """Unified Claim model — type-specific data in claim_attributes."""

    def test_metric_claim(self):
        claim = Claim(
            claim_id="m1",
            text="GPT-5.5 is 40% faster than GPT-5.",
            claim_type=ClaimType.METRIC,
            source_ids=["src1"],
            claim_attributes={
                "value": "40%",
                "unit": "percent",
                "direction": "faster",
                "evidence_snippet": "According to benchmarks, GPT-5.5 demonstrates 40% faster inference speed.",
            },
        )
        assert claim.claim_type == ClaimType.METRIC
        assert claim.claim_attributes["value"] == "40%"
        assert claim.claim_attributes["unit"] == "percent"

    def test_status_claim(self):
        claim = Claim(
            claim_id="s1",
            text="GPT-5.5 rollout started in May 2026.",
            claim_type=ClaimType.STATUS,
            source_ids=["src1"],
            claim_attributes={
                "status": "rollout_started",
                "observed_at": "2026-05-15T00:00:00",
            },
        )
        assert claim.claim_type == ClaimType.STATUS
        assert claim.claim_attributes["status"] == "rollout_started"

    def test_date_claim(self):
        claim = Claim(
            claim_id="d1",
            text="June 11, 2026",
            claim_type=ClaimType.DATE,
            source_ids=["src1"],
            claim_attributes={"date_value": "2026-06-11T00:00:00+00:00"},
        )
        assert claim.claim_type == ClaimType.DATE

    def test_location_claim(self):
        claim = Claim(
            claim_id="l1",
            text="Vienna",
            claim_type=ClaimType.LOCATION,
            source_ids=["src1"],
            claim_attributes={"location": "Vienna, Austria"},
        )
        assert claim.claim_attributes["location"] == "Vienna, Austria"

    def test_entity_claim(self):
        claim = Claim(
            claim_id="e1",
            text="DARA (Winner)",
            claim_type=ClaimType.ENTITY,
            source_ids=["src1"],
            claim_attributes={
                "entity_name": "DARA",
                "entity_role": "Winner",
            },
        )
        assert claim.claim_attributes["entity_name"] == "DARA"

    def test_claim_defaults(self):
        claim = Claim(
            claim_id="c1",
            text="Default test",
            claim_type=ClaimType.STATUS,
            source_ids=["src1"],
        )
        assert claim.public_claim_eligible is False
        assert claim.claim_topic.value == "other"
        assert claim.claim_attributes == {}

    def test_claim_attributes_preserved_roundtrip(self):
        attrs = {"value": "48", "unit": "teams", "evidence_snippet": "48 teams will compete"}
        claim = Claim(
            claim_id="c1",
            text="48 teams",
            claim_type=ClaimType.METRIC,
            source_ids=["src1"],
            claim_attributes=attrs,
        )
        dumped = claim.model_dump(mode="json")
        reloaded = Claim.model_validate(dumped)
        assert reloaded.claim_attributes == attrs


class TestSourceScoring:
    """Source must have authority_score, freshness_score, relevance_score, and overall_score."""

    def test_source_official_scores_high(self):
        source = Source(
            source_id="src_official",
            url="https://openai.com/release",
            title="Official Release",
            source_type=SourceType.OFFICIAL,
            authority_score=1.0,
        )
        assert source.authority_score == 1.0
        assert source.overall_score > 0.5

    def test_source_social_scores_low(self):
        source = Source(
            source_id="src_social",
            url="https://twitter.com/user",
            title="Tweet",
            source_type=SourceType.SOCIAL,
            authority_score=0.5,
        )
        assert source.authority_score == 0.5

    def test_source_overall_score_calculation(self):
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
        source = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
        )
        claim = Claim(
            claim_id="c1",
            text="Metric claim",
            claim_type=ClaimType.METRIC,
            source_ids=["src1"],
            claim_attributes={"value": "100", "unit": "units", "evidence_snippet": "Evidence"},
        )
        graph = EvidenceGraph(
            event_hypothesis="Test event",
            sources=[source],
            claims=[claim],
        )
        assert len(graph.sources) == 1
        assert len(graph.claims) == 1

    def test_evidence_graph_claim_source_mismatch(self):
        claim = Claim(
            claim_id="c1",
            text="Metric claim",
            claim_type=ClaimType.METRIC,
            source_ids=["nonexistent_source"],
            claim_attributes={"value": "100", "unit": "units", "evidence_snippet": "Evidence"},
        )
        graph = EvidenceGraph(
            event_hypothesis="Test event",
            claims=[claim],
        )
        errors = graph.validate_claim_sources()
        assert len(errors) > 0
        assert "nonexistent_source" in errors[0]

    def test_evidence_graph_unique_source_ids(self):
        source1 = Source(
            source_id="src1",
            url="https://example.com",
            title="Example",
        )
        source2 = Source(
            source_id="src1",
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
        claim1 = Claim(
            claim_id="c1",
            text="Claim 1",
            claim_type=ClaimType.METRIC,
            source_ids=["src1"],
            claim_attributes={"value": "100", "unit": "units", "evidence_snippet": "Ev1"},
        )
        claim2 = Claim(
            claim_id="c1",
            text="Claim 2",
            claim_type=ClaimType.METRIC,
            source_ids=["src1"],
            claim_attributes={"value": "200", "unit": "units", "evidence_snippet": "Ev2"},
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
        item = UIItem(
            label="Performance Improvement",
            value="40% faster",
            claim_id="metric_1",
        )
        assert item.claim_id == "metric_1"

    def test_ui_item_numeric_without_claim_id(self):
        item = UIItem(label="Performance", value="40% faster")
        assert item.claim_id is None


class TestUIComponentValidation:
    """UIComponent must validate items have claim_ids for stat grids."""

    def test_stat_grid_numeric_items_need_claim_ids(self):
        item_with_claim = UIItem(label="Speed", value="40%", claim_id="m1")
        component = UIComponent(
            component_type=ComponentType.STAT_GRID,
            title="Stats",
            items=[item_with_claim],
        )
        assert component.items[0].claim_id == "m1"

    def test_stat_grid_numeric_items_without_claim_ids(self):
        item_without_claim = UIItem(label="Speed", value="40%")
        component = UIComponent(
            component_type=ComponentType.STAT_GRID,
            title="Stats",
            items=[item_without_claim],
        )
        assert component.items[0].claim_id is None


class TestTopicPageDataValidation:
    """TopicPageData must validate claims against EvidenceGraph."""

    def test_topic_page_data_numeric_claims_valid(self):
        item = UIItem(label="Performance", value="40%", claim_id="m1")
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
        claim = Claim(
            claim_id="m1",
            text="40% faster",
            claim_type=ClaimType.METRIC,
            source_ids=["src1"],
            claim_attributes={"value": "40%", "unit": "percent", "evidence_snippet": "Evidence"},
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
        errors = page.validate_numeric_claims_have_sources(evidence_graph)
        assert len(errors) == 0

    def test_topic_page_data_missing_claim_id_in_evidence_graph(self):
        item = UIItem(label="Performance", value="40%", claim_id="nonexistent_claim")
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
            claims=[],
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
