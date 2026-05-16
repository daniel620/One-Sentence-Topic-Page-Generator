from __future__ import annotations

import os
from datetime import date
from typing import Any

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
)


def _build_instructor_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for stage1_understand")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


class Stage1A:
    """Stage 1A: Generate preliminary hypothesis without evidence."""

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
        return result


class Stage1B:
    """Stage 1B: Generate evidence-aware IA planning."""

    def __init__(self, client: Any | None = None):
        self.client = client or _build_instructor_client()

    def run(
        self,
        hypothesis: EventHypothesis,
        evidence_graph: EvidenceGraph,
        today: date | None = None,
    ) -> EvidenceAwareIA:
        current_date = today or date.today()
        messages = build_stage1b_messages(hypothesis, evidence_graph, current_date)

        result = self.client.messages.create(
            model=MODEL_NAME,
            max_tokens=1500,
            messages=messages,
            response_model=EvidenceAwareIA,
        )
        return result


def understand_event(
    sentence: str,
    today: date | None = None,
    client: Any | None = None,
) -> EventContext:
    """Legacy function for backward compatibility. Returns EventContext from hypothesis."""
    clean_sentence = sentence.strip()
    if not clean_sentence:
        raise ValueError("Input sentence must not be empty")

    current_date = today or date.today()
    llm_client = client or _build_instructor_client()

    stage1a = Stage1A(llm_client)
    hypothesis = stage1a.run(clean_sentence, current_date)

    # Convert EventHypothesis to EventContext for backward compatibility.
    return EventContext(
        event_type=hypothesis.preliminary_event_type,
        status=EventStatus.DEVELOPING,
        confidence="medium",
        primary_entity=clean_sentence[:160],
        event_sentence=clean_sentence,
        search_queries=hypothesis.search_intents,
        layout_style=None,
        planned_components=None,
    )


def plan_event_ia(
    hypothesis: EventHypothesis,
    evidence_graph: EvidenceGraph,
    today: date | None = None,
    client: Any | None = None,
) -> EvidenceAwareIA:
    """Legacy helper for Stage 1B planning."""
    current_date = today or date.today()
    llm_client = client or _build_instructor_client()
    stage1b = Stage1B(llm_client)
    return stage1b.run(hypothesis, evidence_graph, current_date)
