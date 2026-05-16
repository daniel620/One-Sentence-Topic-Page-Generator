"""Utilities for research layer: extraction, scoring, contradiction detection."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
from anthropic import Anthropic

from generator.schemas import (
    Claim,
    ClaimType,
    Contradiction,
    ConfidenceLevel,
    DateClaim,
    DisplayPolicy,
    EntityClaim,
    LocationClaim,
    MetricClaim,
    ResolutionPolicy,
    ScheduleClaim,
    Source,
    SourceType,
    StatusClaim,
)

LOGGER = logging.getLogger("research_utils")

METRIC_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(%|x|ms|s|minutes?|hours?|days?|weeks?|billion|million|thousand|K|M|B|GB|MB|USD|EUR|£|\$)(?:\b|(?=[^a-zA-Z]))",
    re.IGNORECASE,
)

DATE_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b",
    re.IGNORECASE,
)

LOCATION_PATTERN = re.compile(
    r"\b(City|City of|in|at|at the|located in|venue|location|stadium)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
)

TIME_PATTERN = re.compile(
    r"\b([0-1]?[0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?\s*(?:AM|PM|am|pm)?\b"
)

ENTITY_PATTERN = re.compile(
    r"\b(Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.|Chief|President|CEO|Founder|Created by|Founded by|Developed by|Announced by|Hosted by|Performed by)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b"
)


# Known publishers / source types keyed by URL hostname suffix.
# The match is "endswith the key after stripping leading 'www.'". Keep this
# small and explicit; if a hostname isn't listed, we fall back to a generic
# name derived from the apex domain.
KNOWN_PUBLISHERS: dict[str, tuple[str, SourceType]] = {
    # Official organisations and primary sources
    "openai.com": ("OpenAI", SourceType.OFFICIAL),
    "anthropic.com": ("Anthropic", SourceType.OFFICIAL),
    "fifa.com": ("FIFA", SourceType.OFFICIAL),
    "eurovision.tv": ("Eurovision.tv (EBU)", SourceType.OFFICIAL),
    "eurovision.com": ("Eurovision (official)", SourceType.OFFICIAL),
    "olympics.com": ("Olympics", SourceType.OFFICIAL),
    "uefa.com": ("UEFA", SourceType.OFFICIAL),
    "concacaf.com": ("CONCACAF", SourceType.OFFICIAL),
    "wien.info": ("vienna.info (City of Vienna)", SourceType.OFFICIAL),
    "ebu.ch": ("European Broadcasting Union", SourceType.OFFICIAL),
    # Primary data / reference
    "wikipedia.org": ("Wikipedia", SourceType.PRIMARY_DATA),
    # Reputable media (international)
    "bbc.com": ("BBC", SourceType.REPUTABLE_MEDIA),
    "bbc.co.uk": ("BBC", SourceType.REPUTABLE_MEDIA),
    "reuters.com": ("Reuters", SourceType.REPUTABLE_MEDIA),
    "apnews.com": ("Associated Press", SourceType.REPUTABLE_MEDIA),
    "theguardian.com": ("The Guardian", SourceType.REPUTABLE_MEDIA),
    "nytimes.com": ("The New York Times", SourceType.REPUTABLE_MEDIA),
    "washingtonpost.com": ("The Washington Post", SourceType.REPUTABLE_MEDIA),
    "ft.com": ("Financial Times", SourceType.REPUTABLE_MEDIA),
    "wsj.com": ("The Wall Street Journal", SourceType.REPUTABLE_MEDIA),
    "economist.com": ("The Economist", SourceType.REPUTABLE_MEDIA),
    "npr.org": ("NPR", SourceType.REPUTABLE_MEDIA),
    "aljazeera.com": ("Al Jazeera", SourceType.REPUTABLE_MEDIA),
    "cnn.com": ("CNN", SourceType.REPUTABLE_MEDIA),
    "cnbc.com": ("CNBC", SourceType.REPUTABLE_MEDIA),
    "espn.com": ("ESPN", SourceType.REPUTABLE_MEDIA),
    "theathletic.com": ("The Athletic", SourceType.REPUTABLE_MEDIA),
    "skysports.com": ("Sky Sports", SourceType.REPUTABLE_MEDIA),
    "theverge.com": ("The Verge", SourceType.REPUTABLE_MEDIA),
    "techcrunch.com": ("TechCrunch", SourceType.REPUTABLE_MEDIA),
    "arstechnica.com": ("Ars Technica", SourceType.REPUTABLE_MEDIA),
    "wired.com": ("WIRED", SourceType.REPUTABLE_MEDIA),
    "engadget.com": ("Engadget", SourceType.REPUTABLE_MEDIA),
    "axios.com": ("Axios", SourceType.REPUTABLE_MEDIA),
    "bloomberg.com": ("Bloomberg", SourceType.REPUTABLE_MEDIA),
    "venturebeat.com": ("VentureBeat", SourceType.REPUTABLE_MEDIA),
    "theinformation.com": ("The Information", SourceType.REPUTABLE_MEDIA),
    "platformer.news": ("Platformer", SourceType.REPUTABLE_MEDIA),
    "semafor.com": ("Semafor", SourceType.REPUTABLE_MEDIA),
    "mashable.com": ("Mashable", SourceType.REPUTABLE_MEDIA),
    "yahoo.com": ("Yahoo Sports", SourceType.REPUTABLE_MEDIA),
    "sports.yahoo.com": ("Yahoo Sports", SourceType.REPUTABLE_MEDIA),
    "hitc.com": ("HITC", SourceType.LOCAL_MEDIA),
    "bundesliga.com": ("Bundesliga", SourceType.LOCAL_MEDIA),
    "der.orf.at": ("ORF", SourceType.OFFICIAL),
    "orf.at": ("ORF", SourceType.REPUTABLE_MEDIA),
    "eurovisionworld.com": ("EurovisionWorld", SourceType.REPUTABLE_MEDIA),
    "escxtra.com": ("ESCXTRA", SourceType.REPUTABLE_MEDIA),
    # Social / community
    "twitter.com": ("X (Twitter)", SourceType.SOCIAL),
    "x.com": ("X (Twitter)", SourceType.SOCIAL),
    "facebook.com": ("Facebook", SourceType.SOCIAL),
    "instagram.com": ("Instagram", SourceType.SOCIAL),
    "tiktok.com": ("TikTok", SourceType.SOCIAL),
    "reddit.com": ("Reddit", SourceType.SOCIAL),
    "youtube.com": ("YouTube", SourceType.SOCIAL),
    "youtu.be": ("YouTube", SourceType.SOCIAL),
    "substack.com": ("Substack", SourceType.SOCIAL),
    # Aggregators / weak
    "news.google.com": ("Google News", SourceType.AGGREGATOR),
    "flipboard.com": ("Flipboard", SourceType.AGGREGATOR),
    "polymarket.com": ("Polymarket", SourceType.AGGREGATOR),
}


def _normalize_hostname(url: str) -> str:
    """Return the hostname of `url` with a leading 'www.' stripped."""
    from urllib.parse import urlparse

    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def publisher_from_url(url: str | None, fallback: str | None = None) -> str | None:
    """Best-effort publisher name from a URL hostname.

    Returns the known publisher name when the hostname matches an entry in
    `KNOWN_PUBLISHERS`. Otherwise returns a titlecased version of the
    second-level domain, e.g. `pulse2.com` → "Pulse2". Returns `fallback`
    or None if the URL has no parseable host.
    """
    host = _normalize_hostname(url or "")
    if not host:
        return fallback
    for suffix, (name, _) in KNOWN_PUBLISHERS.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    # Generic fallback: take the second-level domain, titlecase it.
    parts = host.split(".")
    if len(parts) >= 2:
        return parts[-2].title()
    return fallback


def infer_source_type(publisher: str | None, url: str | None) -> SourceType:
    """Infer `SourceType` for a source. URL hostname wins over publisher name."""
    host = _normalize_hostname(url or "")
    for suffix, (_, source_type) in KNOWN_PUBLISHERS.items():
        if host and (host == suffix or host.endswith("." + suffix)):
            return source_type

    if host and (".gov" in host or ".gov." in host or host.endswith(".gov")):
        return SourceType.OFFICIAL
    if "official" in (publisher or "").lower():
        return SourceType.OFFICIAL
    return SourceType.UNKNOWN


def calculate_freshness_score(published_at: datetime | str | None, reference_date: datetime | None = None) -> float:
    """Calculate freshness score (1.0 = fresh, 0.0 = very old)."""
    if not published_at:
        return 0.5

    ref_date = reference_date or datetime.now(timezone.utc)

    # Parse published_at if string
    if isinstance(published_at, str):
        try:
            # Try ISO format
            pub_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            try:
                # Try alternate parsing
                pub_date = datetime.strptime(published_at.split("T")[0], "%Y-%m-%d")
                pub_date = pub_date.replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                return 0.5
    else:
        pub_date = published_at

    # Ensure both are timezone-aware
    if ref_date.tzinfo is None:
        ref_date = ref_date.replace(tzinfo=timezone.utc)
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)

    days_old = (ref_date - pub_date).days

    if days_old <= 1:
        return 1.0
    elif days_old <= 7:
        return 0.9
    elif days_old <= 30:
        return 0.7
    elif days_old <= 90:
        return 0.5
    elif days_old <= 365:
        return 0.3
    else:
        return 0.1


def calculate_relevance_score(content: str | None, event_keywords: list[str] | None = None) -> float:
    """Calculate relevance score based on content and keywords."""
    if not content or not event_keywords:
        return 0.5

    content_lower = content.lower()
    keyword_matches = sum(1 for kw in event_keywords if kw.lower() in content_lower)

    # Score based on keyword density
    if not event_keywords:
        return 0.5
    score = min(1.0, keyword_matches / len(event_keywords))
    return max(0.3, score)


def create_source(
    url: str,
    title: str,
    publisher: str | None = None,
    published_at: datetime | str | None = None,
    content: str | None = None,
    event_keywords: list[str] | None = None,
) -> Source:
    """Create a Source object with auto-calculated scores."""
    from generator.schemas import calculate_source_authority_score

    # Prefer hostname-derived source type and publisher when Tavily didn't
    # supply them; that's the common case in practice.
    source_type = infer_source_type(publisher, url)
    if not publisher:
        publisher = publisher_from_url(url)
    auth_score = calculate_source_authority_score(source_type)

    # Parse published_at if string
    parsed_published_at = None
    if isinstance(published_at, str):
        try:
            parsed_published_at = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            try:
                parsed_published_at = datetime.strptime(published_at.split("T")[0], "%Y-%m-%d")
                parsed_published_at = parsed_published_at.replace(tzinfo=timezone.utc)
            except (ValueError, IndexError):
                parsed_published_at = None
    elif isinstance(published_at, datetime):
        parsed_published_at = published_at

    freshness = calculate_freshness_score(parsed_published_at)
    relevance = calculate_relevance_score(content, event_keywords or [])

    # Generate source_id from URL
    source_id = f"src_{hash(url) % 100000:05d}"

    return Source(
        source_id=source_id,
        url=url,
        title=title[:500],
        publisher=publisher[:120] if publisher else None,
        published_at=parsed_published_at,
        source_type=source_type,
        authority_score=auth_score,
        freshness_score=freshness,
        relevance_score=relevance,
        bias_or_limitation=None,
    )


def extract_metric_claims(
    content: str,
    source_id: str,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
) -> list[MetricClaim]:
    """Extract metric claims using regex patterns."""
    claims: list[MetricClaim] = []
    seen_values: set[str] = set()

    for match in METRIC_PATTERN.finditer(content):
        value = match.group(1)
        unit = match.group(2)

        # Deduplicate
        claim_key = f"{value}_{unit}"
        if claim_key in seen_values:
            continue
        seen_values.add(claim_key)

        # Extract surrounding sentence
        start = max(0, match.start() - 100)
        end = min(len(content), match.end() + 100)
        snippet = content[start:end].strip()

        claim_id = f"metric_{hash(claim_key) % 10000:04d}"
        claims.append(
            MetricClaim(
                claim_id=claim_id,
                text=f"{value} {unit}",
                claim_type=ClaimType.METRIC,
                value=value,
                unit=unit,
                source_ids=[source_id],
                confidence=confidence,
                freshness="fresh",
                evidence_snippet=snippet[:300],
            )
        )

    return claims


def extract_date_claims(
    content: str,
    source_id: str,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
) -> list[DateClaim]:
    """Extract date claims using regex patterns."""
    claims: list[DateClaim] = []
    seen_dates: set[str] = set()

    for match in DATE_PATTERN.finditer(content):
        date_str = match.group(0)

        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)

        # Try to parse date
        try:
            # Try various date formats
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%B %d", "%b %d", "%Y-%m-%d", "%m/%d/%Y"]:
                try:
                    parsed = datetime.strptime(date_str.rstrip(","), fmt)
                    # If year is missing, assume current or next year context
                    if parsed.year == 1900:
                        parsed = parsed.replace(year=2026)
                    date_value = parsed.replace(tzinfo=timezone.utc)

                    claim_id = f"date_{hash(date_str) % 10000:04d}"
                    claims.append(
                        DateClaim(
                            claim_id=claim_id,
                            text=date_str,
                            claim_type=ClaimType.DATE,
                            source_ids=[source_id],
                            confidence=confidence,
                            freshness="fresh",
                            date_value=date_value,
                        )
                    )
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    return claims


def extract_location_claims(
    content: str,
    source_id: str,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
) -> list[LocationClaim]:
    """Extract location claims using regex patterns."""
    claims: list[LocationClaim] = []
    seen_locations: set[str] = set()

    for match in LOCATION_PATTERN.finditer(content):
        location = match.group(2)

        if location in seen_locations:
            continue
        seen_locations.add(location)

        claim_id = f"loc_{hash(location) % 10000:04d}"
        claims.append(
            LocationClaim(
                claim_id=claim_id,
                text=location,
                claim_type=ClaimType.LOCATION,
                source_ids=[source_id],
                confidence=confidence,
                freshness="fresh",
                location=location[:200],
            )
        )

    return claims


def extract_entity_claims(
    content: str,
    source_id: str,
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
) -> list[EntityClaim]:
    """Extract entity claims using regex patterns."""
    claims: list[EntityClaim] = []
    seen_entities: set[str] = set()

    for match in ENTITY_PATTERN.finditer(content):
        role = match.group(1)
        entity_name = match.group(2)

        entity_key = f"{entity_name}_{role}"
        if entity_key in seen_entities:
            continue
        seen_entities.add(entity_key)

        claim_id = f"ent_{hash(entity_key) % 10000:04d}"
        claims.append(
            EntityClaim(
                claim_id=claim_id,
                text=f"{entity_name} ({role})",
                claim_type=ClaimType.ENTITY,
                source_ids=[source_id],
                confidence=confidence,
                freshness="fresh",
                entity_name=entity_name[:160],
                entity_role=role[:200],
            )
        )

    return claims


def extract_deterministic_claims(
    url: str,
    title: str,
    content: str,
    source_id: str,
) -> list[Claim]:
    """Extract all deterministic claims from content."""
    claims: list[Claim] = []

    # Extract metric claims
    claims.extend(extract_metric_claims(content, source_id, ConfidenceLevel.HIGH))

    # Extract date claims
    claims.extend(extract_date_claims(content, source_id, ConfidenceLevel.HIGH))

    # Extract location claims
    claims.extend(extract_location_claims(content, source_id, ConfidenceLevel.MEDIUM))

    # Extract entity claims
    claims.extend(extract_entity_claims(content, source_id, ConfidenceLevel.MEDIUM))

    return claims


def extract_semantic_claim_with_llm(
    client: Anthropic,
    content: str,
    source_id: str,
    claim_type: ClaimType = ClaimType.STATUS,
) -> Claim | None:
    """Use constrained LLM to extract a semantic claim from content."""
    try:
        # Build a simple status claim based on content
        # For now, we'll use a simple heuristic
        sentences = [s.strip() for s in content.split(".") if s.strip()]
        if not sentences:
            return None

        # Take the first sentence with meaningful content
        main_sentence = sentences[0]
        if len(main_sentence) < 10:
            main_sentence = sentences[1] if len(sentences) > 1 else main_sentence

        claim_id = f"status_{hash(main_sentence) % 10000:04d}"
        return StatusClaim(
            claim_id=claim_id,
            text=main_sentence[:500],
            claim_type=ClaimType.STATUS,
            source_ids=[source_id],
            confidence=ConfidenceLevel.MEDIUM,
            freshness="fresh",
            status=main_sentence[:120],
        )
    except Exception as e:
        LOGGER.debug(f"Failed to extract semantic claim: {e}")
        return None


def detect_contradictions(claims: list[Claim]) -> list[Contradiction]:
    """Detect contradictions between claims."""
    contradictions: list[Contradiction] = []

    # Group claims by type and rough topic
    metric_claims: dict[str, list[MetricClaim]] = {}
    date_claims: dict[str, list[DateClaim]] = {}

    for claim in claims:
        if isinstance(claim, MetricClaim):
            # Group by unit
            unit_key = claim.unit
            if unit_key not in metric_claims:
                metric_claims[unit_key] = []
            metric_claims[unit_key].append(claim)

        elif isinstance(claim, DateClaim):
            # Group by claim text (rough grouping)
            text_key = claim.text[:50]
            if text_key not in date_claims:
                date_claims[text_key] = []
            date_claims[text_key].append(claim)

    # Check for metric contradictions (same unit, different values)
    for unit, unit_claims in metric_claims.items():
        if len(unit_claims) > 1:
            # Check if values differ significantly
            values = [float(c.value) for c in unit_claims if c.value.replace(".", "").isdigit()]
            if len(set(values)) > 1:
                max_val = max(values)
                min_val = min(values)
                if max_val / min_val > 1.1:  # More than 10% difference
                    claim_a = unit_claims[0]
                    claim_b = unit_claims[1]
                    contradictions.append(
                        Contradiction(
                            topic=f"{unit} measurement",
                            claim_a=f"{claim_a.value} {claim_a.unit}",
                            sources_a=claim_a.source_ids,
                            claim_b=f"{claim_b.value} {claim_b.unit}",
                            sources_b=claim_b.source_ids,
                            resolution=ResolutionPolicy.PREFER_NEWER if claim_a.freshness == "fresh" else ResolutionPolicy.UNRESOLVED,
                            display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
                        )
                    )

    # Check for date contradictions (same event, different dates)
    # This is simpler - just flag if we have multiple conflicting dates
    if len(date_claims) > 1:
        claim_list = []
        for group in date_claims.values():
            claim_list.extend(group)
        if len(claim_list) > 1:
            # Check for significant date differences
            dates = [c.date_value for c in claim_list if c.date_value]
            if len(set(dates)) > 1:
                # Flag as potential contradiction
                claim_a = claim_list[0]
                claim_b = claim_list[1]
                contradictions.append(
                    Contradiction(
                        topic="Event date",
                        claim_a=claim_a.text,
                        sources_a=claim_a.source_ids,
                        claim_b=claim_b.text,
                        sources_b=claim_b.source_ids,
                        resolution=ResolutionPolicy.PREFER_OFFICIAL,
                        display_policy=DisplayPolicy.SHOW_UNCERTAINTY_BOX,
                    )
                )

    return contradictions


def fetch_and_extract_content(url: str, timeout: int = 10) -> tuple[str, str] | tuple[None, None]:
    """Fetch a URL and extract readable text content and title.
    
    Returns:
        (content, title) or (None, None) if fetch fails
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, follow_redirects=True)
            response.raise_for_status()

        # Extract title from HTML
        title_match = re.search(r"<title>(.*?)</title>", response.text, re.IGNORECASE)
        title = title_match.group(1) if title_match else ""

        # Simple text extraction: remove script/style tags, extract text
        html = response.text
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r"<[^>]+>", " ", html)  # Remove all HTML tags
        text = " ".join(html.split())  # Normalize whitespace

        # Limit to first 2000 chars to avoid token explosion
        text = text[:2000]

        return text, title
    except Exception as e:
        LOGGER.debug(f"Failed to fetch {url}: {e}")
        return None, None
