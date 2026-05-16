"""Stage 3: synthesize a `TopicPageData` from `EvidenceGraph` + `EvidenceAwareIA`.

This is the only stage where the LLM writes editorial copy. We constrain it
with `instructor`'s structured output mode against `TopicPageData`, and we
inject IA decisions (event_type, status, layout_style) post-hoc so the LLM
doesn't have to re-pick them.

When QA fails, the pipeline re-enters here with `repair_actions` and
`failed_items`, and we swap to a focused revision prompt.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import anthropic
import instructor

from generator.prompts import (
    MODEL_NAME,
    build_stage3_messages,
    build_stage3_revision_messages,
)
from generator.schemas import EvidenceAwareIA, EvidenceGraph, QARepairAction, TopicPageData


def _build_instructor_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for stage3_synthesize")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


def synthesize_topic_page(
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    today: date | None = None,
    client: Any | None = None,
    repair_actions: list[QARepairAction] | None = None,
    failed_items: list[str] | None = None,
) -> TopicPageData:
    current_date = today or date.today()
    llm_client = client or _build_instructor_client()

    if repair_actions:
        messages = build_stage3_revision_messages(
            evidence_graph, ia, current_date,
            repair_actions=repair_actions, failed_items=failed_items,
        )
    else:
        messages = build_stage3_messages(evidence_graph, ia, current_date)

    result = llm_client.messages.create(
        model=MODEL_NAME,
        max_tokens=8000,
        messages=messages,
        response_model=TopicPageData,
    )

    return TopicPageData.model_validate(
        {
            **result.model_dump(mode="json"),
            "event_type": ia.final_event_type,
            "status": ia.event_status,
            "layout_style": ia.layout_style,
            "evidence_graph_ref": evidence_graph.model_dump(mode="json"),
            "last_updated": evidence_graph.last_updated,
        }
    )
