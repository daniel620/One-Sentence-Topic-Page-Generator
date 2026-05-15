from __future__ import annotations

import os
from datetime import date
from typing import Any

import anthropic
import instructor

from generator.prompts import MODEL_NAME, build_stage3_messages
from generator.schemas import EventContext, RawResearch, TopicPageData


def _build_instructor_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for stage3_synthesize")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


def synthesize_topic_page(
    context: EventContext,
    research: RawResearch,
    today: date | None = None,
    client: Any | None = None,
) -> TopicPageData:
    current_date = today or date.today()
    llm_client = client or _build_instructor_client()
    messages = build_stage3_messages(context, research, current_date)

    result = llm_client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        messages=messages,
        response_model=TopicPageData,
    )
    return TopicPageData.model_validate(
        {
            **result.model_dump(mode="json"),
            "event_type": context.event_type,
            "status": context.status,
        }
    )
