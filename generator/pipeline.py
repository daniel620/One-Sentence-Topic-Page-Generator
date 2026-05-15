from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel

from generator.schemas import EventContext, RawResearch, TopicPageData
from generator.stage1_understand import understand_event
from generator.stage2_research import run_research
from generator.stage3_synthesize import synthesize_topic_page

Stage1Fn = Callable[[str, date | None], EventContext]
Stage2Fn = Callable[[EventContext], RawResearch]
Stage3Fn = Callable[[EventContext, RawResearch, date | None], TopicPageData]

LOGGER = logging.getLogger("topic_pipeline")


def _to_serializable(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    return payload


def log_stage(stage_name: str, payload: Any) -> None:
    LOGGER.info(
        "%s output:\n%s",
        stage_name,
        json.dumps(_to_serializable(payload), ensure_ascii=False, indent=2),
    )


def run_pipeline(
    sentence: str,
    today: date | None = None,
    stage1_func: Stage1Fn = understand_event,
    stage2_func: Stage2Fn = run_research,
    stage3_func: Stage3Fn = synthesize_topic_page,
) -> TopicPageData:
    current_date = today or date.today()

    event_context = stage1_func(sentence, current_date)
    log_stage("stage1_understand", event_context)

    raw_research = stage2_func(event_context)
    log_stage("stage2_research", raw_research)

    topic_page_data = stage3_func(event_context, raw_research, current_date)
    log_stage("stage3_synthesize", topic_page_data)

    return topic_page_data
