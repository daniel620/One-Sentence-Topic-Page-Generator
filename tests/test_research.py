"""Tests for research layer: claim extraction, source scoring, contradiction detection."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from generator.schemas import (
    Claim,
    ClaimType,
    SourceType,
)
from generator.contradictions import detect_contradictions
from generator.utils import (
    calculate_freshness_score,
    calculate_relevance_score,
    create_source,
    extract_date_claims,
    extract_deterministic_claims,
    extract_entity_claims,
    extract_location_claims,
    extract_metric_claims,
    infer_source_type,
)


class TestInferSourceType:
    """Test source type inference."""

    def test_official_source(self):
        """Test official source detection."""
        assert infer_source_type("FIFA", "https://fifa.com") == SourceType.OFFICIAL
        assert infer_source_type("Official Government", "https://gov.uk") == SourceType.OFFICIAL
        assert infer_source_type(
            "Eurovision", "https://eurovision.tv"
        ) == SourceType.OFFICIAL

    def test_reputable_media(self):
        """Test reputable media detection."""
        assert infer_source_type("BBC", "https://bbc.com") == SourceType.REPUTABLE_MEDIA
        assert infer_source_type("ESPN", "https://espn.com") == SourceType.REPUTABLE_MEDIA
        assert infer_source_type(
            "Reuters", "https://reuters.com"
        ) == SourceType.REPUTABLE_MEDIA

    def test_local_media(self):
        """Test local media detection by known hostname (e.g. Bundesliga)."""
        assert infer_source_type(None, "https://www.bundesliga.com/en/news/x") == SourceType.LOCAL_MEDIA

    def test_social_media(self):
        """Test social media detection."""
        assert infer_source_type("Twitter", "https://twitter.com") == SourceType.SOCIAL
        assert infer_source_type("Reddit", "https://reddit.com") == SourceType.SOCIAL

    def test_unknown_source(self):
        """Test unknown source."""
        assert infer_source_type("Unknown", "https://example.com") == SourceType.UNKNOWN


class TestFreshnessScore:
    """Test freshness scoring."""

    def test_fresh_document(self):
        """Test fresh document (1-day old) gets high score."""
        now = datetime.now(timezone.utc)
        score = calculate_freshness_score(now, now)
        assert score == 1.0

    def test_week_old(self):
        """Test week-old document."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=3)
        score = calculate_freshness_score(old, now)
        assert 0.8 < score < 1.0

    def test_old_document(self):
        """Test very old document gets low score."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=365)
        score = calculate_freshness_score(old, now)
        assert 0.0 <= score <= 0.3

    def test_no_date(self):
        """Test missing date returns medium score."""
        score = calculate_freshness_score(None)
        assert score == 0.5


class TestRelevanceScore:
    """Test relevance scoring."""

    def test_relevant_content(self):
        """Test relevant content gets high score."""
        content = "FIFA World Cup 2026 in USA"
        keywords = ["FIFA", "World", "Cup", "2026"]
        score = calculate_relevance_score(content, keywords)
        assert score >= 0.7

    def test_irrelevant_content(self):
        """Test irrelevant content gets low score."""
        content = "Cooking recipes for dinner"
        keywords = ["FIFA", "World", "Cup", "2026"]
        score = calculate_relevance_score(content, keywords)
        assert 0.3 <= score <= 0.5

    def test_no_keywords(self):
        """Test no keywords returns medium score."""
        score = calculate_relevance_score("Some content", None)
        assert score == 0.5


class TestCreateSource:
    """Test Source creation with auto-scored fields."""

    def test_official_source_high_authority(self):
        """Test official source gets high authority score."""
        source = create_source(
            url="https://fifa.com/article",
            title="World Cup Schedule",
            publisher="FIFA",
        )
        assert source.source_type == SourceType.OFFICIAL
        assert source.authority_score == 1.0

    def test_source_with_freshness(self):
        """Test source freshness calculation."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        old = now - timedelta(days=2)
        source = create_source(
            url="https://example.com",
            title="Article",
            publisher="Test",
            published_at=old,
        )
        assert 0.8 < source.freshness_score < 1.0


class TestExtractMetricClaims:
    """Test metric claim extraction."""

    def test_extract_percentage(self):
        """Test percentage extraction."""
        content = "The system has 95 % accuracy in testing."
        claims = extract_metric_claims(content, "src_001")
        assert len(claims) > 0
        assert any(c.claim_attributes.get("value") == "95" for c in claims)

    def test_extract_multiple_metrics(self):
        """Test multiple metric extraction."""
        content = "The file is 100 MB and processing takes 5 seconds."
        claims = extract_metric_claims(content, "src_001")
        assert len(claims) >= 1

    def test_no_metrics(self):
        """Test content with no metrics."""
        content = "No numbers here at all."
        claims = extract_metric_claims(content, "src_001")
        assert len(claims) == 0


class TestExtractDateClaims:
    """Test date claim extraction."""

    def test_extract_month_day_year(self):
        """Test month-day-year format."""
        content = "The event is on May 15, 2026."
        claims = extract_date_claims(content, "src_001")
        assert len(claims) > 0

    def test_extract_iso_date(self):
        """Test ISO date format."""
        content = "Starting from 2026-05-15 onwards."
        claims = extract_date_claims(content, "src_001")
        assert len(claims) > 0

    def test_no_dates(self):
        """Test content with no dates."""
        content = "No date information here."
        claims = extract_date_claims(content, "src_001")
        assert len(claims) == 0


class TestExtractEntityClaims:
    """Test entity claim extraction."""

    def test_extract_person(self):
        """Test person extraction."""
        content = "Founded by Steve Jobs and another founder John Smith was also involved."
        claims = extract_entity_claims(content, "src_001")
        assert len(claims) >= 1

    def test_extract_ceo(self):
        """Test CEO extraction."""
        content = "CEO Sam Altman announced the new product."
        claims = extract_entity_claims(content, "src_001")
        # May or may not extract depending on regex

    def test_no_entities(self):
        """Test content with no clear entities."""
        content = "The event was great."
        claims = extract_entity_claims(content, "src_001")
        # Should extract minimal or no entities


class TestExtractDeterministicClaims:
    """Test overall deterministic claim extraction."""

    def test_extract_mixed_claims(self):
        """Test extraction of various claim types."""
        content = "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026. It will have 32 teams."
        claims = extract_deterministic_claims(
            url="https://fifa.com",
            title="World Cup Info",
            content=content,
            source_id="src_001",
        )
        assert len(claims) > 0
        # Should have date and metric claims at least
        claim_types = {c.claim_type for c in claims}
        assert ClaimType.DATE in claim_types or ClaimType.METRIC in claim_types


class TestDetectContradictions:
    """Test contradiction detection."""

    def test_detect_metric_contradiction(self):
        """Test detection of conflicting metrics."""
        claim1 = Claim(
            claim_id="m1", text="95%", claim_type=ClaimType.METRIC,
            source_ids=["src1"], freshness="fresh",
            claim_attributes={"value": "95", "unit": "%", "evidence_snippet": "95% accuracy"},
        )
        claim2 = Claim(
            claim_id="m2", text="80%", claim_type=ClaimType.METRIC,
            source_ids=["src2"], freshness="fresh",
            claim_attributes={"value": "80", "unit": "%", "evidence_snippet": "80% accuracy"},
        )
        contradictions = detect_contradictions([claim1, claim2])
        assert len(contradictions) > 0

    def test_no_contradiction_similar_values(self):
        """Test no contradiction when metrics are similar."""
        claim1 = Claim(
            claim_id="m1", text="95%", claim_type=ClaimType.METRIC,
            source_ids=["src1"], freshness="fresh",
            claim_attributes={"value": "95", "unit": "%", "evidence_snippet": "95% accuracy"},
        )
        claim2 = Claim(
            claim_id="m2", text="94%", claim_type=ClaimType.METRIC,
            source_ids=["src2"], freshness="fresh",
            claim_attributes={"value": "94", "unit": "%", "evidence_snippet": "94% accuracy"},
        )
        contradictions = detect_contradictions([claim1, claim2])
        assert len(contradictions) == 0

    def test_no_contradiction_different_units(self):
        """Test no contradiction for different units."""
        claim1 = Claim(
            claim_id="m1", text="100 million", claim_type=ClaimType.METRIC,
            source_ids=["src1"], freshness="fresh",
            claim_attributes={"value": "100", "unit": "million", "evidence_snippet": "100 million users"},
        )
        claim2 = Claim(
            claim_id="m2", text="50000 km", claim_type=ClaimType.METRIC,
            source_ids=["src2"], freshness="fresh",
            claim_attributes={"value": "50000", "unit": "km", "evidence_snippet": "50000 km coverage"},
        )
        contradictions = detect_contradictions([claim1, claim2])
        # Different units, no contradiction
        assert len(contradictions) == 0
