from __future__ import annotations

import json
from datetime import date

from generator.schemas import EventContext, RawResearch

MODEL_NAME = "claude-sonnet-4-20250514"

STAGE1_SYSTEM_PROMPT = """You are an event understanding model for a newsroom topic-page generator.
Your job is to classify the event, infer status, create search queries, and plan information architecture.

Rules:
- Return valid JSON for the EventContext schema.
- event_type must be one of: tech_launch, live_event, sports_tournament.
- status must be one of: live, upcoming, concluded, developing.
- search_queries must contain 3-5 concrete web search queries.
- planned_components must contain 3-6 unique component types.
- layout_style must match page intent:
  - hero_focus: single most important action/upshot
  - dashboard: multi-signal comparison and decision support
  - timeline_first: progression and upcoming checkpoints
- Component planning should fit event jobs-to-be-done:
  - tech_launch: comparison_table + stat_grid + action_list
  - live_event: live_tracker + timeline + action_list
  - sports_tournament: timeline + action_list + stat_grid
- Prefer precision over creativity.
- If uncertain, lower confidence rather than guessing.
"""

STAGE3_SYSTEM_PROMPT = """You synthesize researched evidence into a typed TopicPageData schema.

Rules:
- Return valid JSON for the TopicPageData schema only.
- Use null when uncertain; never fabricate data.
- headline must be 12 words or fewer.
- Provide 2-3 sentence summary.
- Sources must only use URLs that appear in the provided research payload.
- evidence_points must contain concrete, evidence-backed facts with source_url citations.
- Do not output numeric claims unless supported by evidence_pack snippets.
- sections must be componentized UI blocks aligned to EventContext.planned_components.
- Each section must include useful items, not placeholders.
- If evidence is thin or conflicting, lower confidence and reflect uncertainty in summary.
"""


def build_stage1_messages(sentence: str, today: date) -> list[dict[str, str]]:
    user_prompt = (
        "Today's date is {today}.\n"
        "Input event sentence:\n"
        "{sentence}\n\n"
        "Return EventContext with:\n"
        "- event_type\n"
        "- status\n"
        "- confidence\n"
        "- primary_entity\n"
        "- event_sentence (copy from input)\n"
        "- search_queries (3-5)\n"
        "- layout_style\n"
        "- planned_components (3-6)\n"
    ).format(today=today.isoformat(), sentence=sentence.strip())

    return [
        {"role": "system", "content": STAGE1_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_stage3_messages(
    context: EventContext,
    research: RawResearch,
    today: date,
    max_research_chars: int = 12000,
) -> list[dict[str, str]]:
    research_json = json.dumps(research.model_dump(mode="json"), ensure_ascii=False)
    if len(research_json) > max_research_chars:
        research_json = research_json[:max_research_chars]

    context_json = json.dumps(context.model_dump(mode="json"), ensure_ascii=False)
    evidence_pack_json = json.dumps(
        [item.model_dump(mode="json") for item in research.evidence_pack],
        ensure_ascii=False,
    )
    component_evidence_json = json.dumps(
        [item.model_dump(mode="json") for item in research.component_evidence],
        ensure_ascii=False,
    )
    allowed_urls = sorted({str(item.url) for item in research.results})
    allowed_urls_text = "\n".join(f"- {url}" for url in allowed_urls)

    user_prompt = (
        "Today's date is {today}.\n"
        "Event context JSON:\n{context}\n\n"
        "Research JSON (truncated if needed):\n{research}\n\n"
        "Deterministic evidence pack JSON:\n{evidence_pack}\n\n"
        "Component evidence buckets JSON:\n{component_evidence}\n\n"
        "Allowed source URLs:\n{allowed_urls}\n\n"
        "Produce TopicPageData.\n"
        "Base fields (headline, summary, timeline, key_entities, sources) must be populated.\n"
        "Set layout_style to match EventContext.layout_style.\n"
        "Create 3-6 sections with section types anchored in EventContext.planned_components.\n"
        "Add 3-8 evidence_points where every claim is traceable to one source_url.\n"
        "Ensure sections are action-oriented and purpose-fit for this event.\n"
        "Use null when uncertain, never fabricate data.\n"
        "If there are no strong sources, keep confidence low and explain limits in summary.\n"
    ).format(
        today=today.isoformat(),
        context=context_json,
        research=research_json,
        evidence_pack=evidence_pack_json,
        component_evidence=component_evidence_json,
        allowed_urls=allowed_urls_text or "- (none)",
    )

    return [
        {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
