"""Evidence-aware information architecture planner.

Reads the EvidenceGraph and proposes: final event type, event status,
page thesis, mandatory components, layout style, and confidence summary.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import anthropic
import instructor

from generator.prompts import (
    MODEL_NAME,
    build_stage1b_messages,
)
from generator.schemas import (
    EvidenceAwareIA,
    EvidenceGraph,
    EventHypothesis,
)


def _build_instructor_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for plan")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


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


def plan_event_ia(
    hypothesis: EventHypothesis,
    evidence_graph: EvidenceGraph,
    today: date | None = None,
    client: Any | None = None,
) -> EvidenceAwareIA:
    current_date = today or date.today()
    llm_client = client or _build_instructor_client()
    plan_agent = Stage1B(llm_client)
    return plan_agent.run(hypothesis, evidence_graph, current_date)
