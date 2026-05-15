from __future__ import annotations

import os
from datetime import date
from typing import Any

import anthropic
import instructor

from generator.prompts import MODEL_NAME, build_stage1_messages
from generator.schemas import EventContext


def _build_instructor_client() -> Any:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is required for stage1_understand")
    return instructor.from_anthropic(anthropic.Anthropic(api_key=api_key))


def understand_event(
    sentence: str,
    today: date | None = None,
    client: Any | None = None,
) -> EventContext:
    clean_sentence = sentence.strip()
    if not clean_sentence:
        raise ValueError("Input sentence must not be empty")

    current_date = today or date.today()
    llm_client = client or _build_instructor_client()
    messages = build_stage1_messages(clean_sentence, current_date)

    result = llm_client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        messages=messages,
        response_model=EventContext,
    )
    if not result.event_sentence:
        result.event_sentence = clean_sentence
    return result
