from __future__ import annotations

import logging
import os
import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

import anthropic
import instructor

from generator.prompts import (
    MODEL_NAME,
    build_stage1a_messages,
    build_stage1b_messages,
)
from generator.schemas import (
    EvidenceAwareIA,
    EvidenceGraph,
    EventContext,
    EventHypothesis,
    EventStatus,
    EventType,
)

LOGGER = logging.getLogger("classify")


# Map event types to official domains for targeted search queries.
# The LLM prompt also asks for these, but we guarantee at least one
# official-source query deterministically as a safety net.
OFFICIAL_DOMAIN_HINTS: dict[EventType, list[str]] = {
    EventType.SPORTS_TOURNAMENT: [
        "fifa.com", "olympics.com", "uefa.com", "concacaf.com",
        "mlb.com", "nba.com", "nfl.com", "premierleague.com", "wimbledon.com",
    ],
    EventType.TECH_LAUNCH: [
        "openai.com", "anthropic.com", "apple.com", "google.com",
        "microsoft.com", "meta.com", "amazon.com",
    ],
    EventType.LIVE_EVENT: [
        "eurovision.com", "eurovision.tv", "ebu.ch",
    ],
    EventType.CULTURAL_EVENT: [
        "eurovision.com", "eurovision.tv", "grammy.com", "oscars.org",
    ],
    EventType.DISASTER: [
        "fema.gov", "usgs.gov", "noaa.gov", "redcross.org",
        "who.int", "cdc.gov",
    ],
    EventType.ECONOMIC_EVENT: [
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com",
        "imf.org", "worldbank.org", "federalreserve.gov",
    ],
}


def _extract_entity_from_sentence(sentence: str, event_type: EventType) -> str | None:
    """Extract a likely primary entity name from the sentence.

    Used to build targeted official-source queries. Simple heuristic:
    look for capitalized proper nouns near the event type keywords.
    """
    # Simple extraction: the first 2-3 capitalized words that aren't at sentence start
    words = sentence.split()
    proper_nouns = [
        w for w in words
        if w[0].isupper() and w.lower() not in {
            "the", "a", "an", "in", "at", "on", "from", "to", "of", "for",
            "is", "are", "was", "were", "has", "have", "will", "may", "june",
            "july", "may", "january", "february", "march", "april", "august",
            "september", "october", "november", "december",
        }
    ]
    if proper_nouns:
        return " ".join(proper_nouns[:3])
    return None


def _build_official_query(
    sentence: str,
    event_type: EventType,
) -> str | None:
    """Build a site:-targeted query for the likely official source."""
    domains = OFFICIAL_DOMAIN_HINTS.get(event_type, [])
    if not domains:
        return None

    entity = _extract_entity_from_sentence(sentence, event_type)
    if not entity:
        return None

    site_clause = " OR ".join(f"site:{d}" for d in domains[:3])
    return f"{site_clause} {entity} official"


def _ensure_official_query(
    queries: list[str],
    sentence: str,
    event_type: EventType,
) -> list[str]:
    """Guarantee at least one official-source query exists.

    If the LLM-returned queries already contain a site: query, keep them.
    Otherwise, prepend a deterministically-built official query.
    """
    has_official = any("site:" in q.lower() for q in queries)
    if has_official:
        return queries

    official_query = _build_official_query(sentence, event_type)
    if official_query:
        LOGGER.info("Adding official-source query: %s", official_query)
        return [official_query] + queries
    return queries


def _build_instructor_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for classify")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


class Stage1A:
    """Stage 1A: Generate preliminary hypothesis without evidence.

    The LLM produces search intents. We also deterministically guarantee
    at least one official-source-targeted query to improve evidence quality.
    """

    def __init__(self, client: Any | None = None):
        self.client = client or _build_instructor_client()

    def run(
        self,
        sentence: str,
        today: date | None = None,
    ) -> EventHypothesis:
        clean_sentence = sentence.strip()
        if not clean_sentence:
            raise ValueError("Input sentence must not be empty")

        current_date = today or date.today()
        messages = build_stage1a_messages(clean_sentence, current_date)

        result = self.client.messages.create(
            model=MODEL_NAME,
            max_tokens=1500,
            messages=messages,
            response_model=EventHypothesis,
        )

        # Safety net: guarantee an official-source query
        result.search_intents = _ensure_official_query(
            list(result.search_intents),
            clean_sentence,
            result.preliminary_event_type,
        )

        return result