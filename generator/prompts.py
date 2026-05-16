"""All LLM prompts live here.

Stages:
  - Stage 1A: classify event + propose search intents (no IA decisions).
  - Stage 1B: read EvidenceGraph, propose IA + layout + confidence.
  - Stage 3:  produce structured TopicPageData with editorial copy.

The system prompts are conservative — they reinforce the schema, the
component registry, and the no-fabrication rule. The user prompts give
the LLM the exact JSON it needs to ground its output.
"""
from __future__ import annotations

import json
from datetime import date

from generator.schemas import (
    COMPONENT_REGISTRY,
    EvidenceAwareIA,
    EvidenceGraph,
    EventHypothesis,
    QARepairAction,
)

MODEL_NAME = "claude-sonnet-4-5"
COMPONENT_REGISTRY_TEXT = ", ".join(c.value for c in COMPONENT_REGISTRY.component_types)


STAGE1A_SYSTEM_PROMPT = """You classify a one-sentence event for a newsroom topic-page generator.

Your job is to:
- pick the event type from: tech_launch, live_event, sports_tournament, cultural_event, disaster
- describe the freshness need (e.g. "live, sub-hour"; "this week"; "historical OK")
- propose 3-6 concrete search queries an editor would actually run
- list which source types are needed (official, primary_data, reputable_media, etc.)
- list 3-5 unknowns we'd need to resolve before publishing

Do NOT propose layouts, components, or page structure here. That comes after we have evidence.
Prefer precision over creativity. If uncertain, flag more unknowns rather than guessing.
"""


STAGE1B_SYSTEM_PROMPT = """You plan information architecture for a topic page, AFTER reading evidence.

Inputs:
- the original hypothesis (event type, search intents, unknowns)
- an EvidenceGraph with sources, claims, and any contradictions

You return EvidenceAwareIA:
- final_event_type — confirm or revise from the hypothesis
- event_status     — infer from the claims: live, upcoming, scheduled, concluded, developing
- page_thesis      — 1-2 sentence statement of what this page should answer
- required_components — choose only from this registry: {component_registry}
- layout_style     — hero_focus | dashboard | timeline_first
- confidence_summary — 1-2 sentences on evidence quality

Rules:
- Include uncertainty_box whenever contradictions exist.
- Prefer stat_grid/comparison_table when metric claims exist.
- Prefer timeline when schedule/date claims exist.
- Always include action_list for next steps.
- Never invent component types, HTML, or CSS.
""".format(component_registry=COMPONENT_REGISTRY_TEXT)


STAGE3_SYSTEM_PROMPT = """You write the editorial body of a hot-event topic page as structured JSON.

Output schema: TopicPageData.
Allowed component types: {component_registry}.

Editorial requirements:
- headline: 12 words or fewer; concrete, specific, no clickbait.
- deck: one editorial sentence under the headline that adds *new* information beyond the headline.
- summary: 2-3 sentence lead that answers "what happened, why it matters, what changed".
- urgency_label: short chip text matching status (e.g. "Live now", "Rolled out", "Kickoff in 12 days"). Omit if not useful.
- as_of_label: short "as of <date or time>" string for the dateline. Use today's date if no better signal exists.
- key_facts: 3-5 high-signal at-a-glance facts (label + short value). For tech launches favor what changed; for live/sports events favor schedule/venue/how-to-watch; for disasters favor location/impact.
- timeline: ordered events from earliest to latest.
- sections: 3-6 UIComponent blocks. Each one must include items grounded in the EvidenceGraph.

Evidence rules:
- Only use URLs from the EvidenceGraph sources.
- Every numeric, date, schedule, status, or named-entity item MUST carry a claim_id that resolves to EvidenceGraph.claims[].claim_id.
- Do not fabricate metrics or dates that aren't in the graph.
- If contradictions exist, add an uncertainty_box section.
- If sources are weak or stale, keep confidence low and say so in the summary — don't bluff.

No HTML, no CSS, no Markdown, no commentary outside the JSON.

Terseness rules (apply ruthlessly):
- summary: max 3 short sentences (~80 words total).
- deck: one sentence, max 22 words.
- Each section: at most 5 items.
- Each item.value: max ~20 words. item.detail: max ~25 words.
- Prefer fewer richer items over many thin ones.
- If you'd otherwise repeat a fact between sections, pick the better location and drop the dup.
""".format(component_registry=COMPONENT_REGISTRY_TEXT)


def _truncate_json(model_json: str, max_chars: int) -> str:
    return model_json if len(model_json) <= max_chars else model_json[:max_chars]


def build_stage1a_messages(sentence: str, today: date) -> list[dict[str, str]]:
    user = (
        "Today's date is {today}.\n"
        "Input event sentence:\n  {sentence}\n\n"
        "Return EventHypothesis with:\n"
        "  - preliminary_event_type\n"
        "  - freshness_need\n"
        "  - search_intents (3-6 concrete queries)\n"
        "  - required_source_types\n"
        "  - unknowns (3-5)\n"
        "Do NOT include layout, components, or final IA fields.\n"
    ).format(today=today.isoformat(), sentence=sentence.strip())
    return [
        {"role": "system", "content": STAGE1A_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def build_stage1b_messages(
    hypothesis: EventHypothesis,
    evidence_graph: EvidenceGraph,
    today: date,
    max_graph_chars: int = 12000,
) -> list[dict[str, str]]:
    graph_json = _truncate_json(
        json.dumps(evidence_graph.model_dump(mode="json"), ensure_ascii=False, default=str),
        max_graph_chars,
    )
    hyp_json = json.dumps(hypothesis.model_dump(mode="json"), ensure_ascii=False)

    user = (
        "Today's date is {today}.\n"
        "Hypothesis JSON:\n{hypothesis}\n\n"
        "EvidenceGraph JSON (truncated if needed):\n{graph}\n\n"
        "Return EvidenceAwareIA with:\n"
        "  - final_event_type\n"
        "  - event_status\n"
        "  - page_thesis\n"
        "  - required_components (registry only: {registry})\n"
        "  - layout_style (hero_focus | dashboard | timeline_first)\n"
        "  - confidence_summary\n"
        "If contradictions exist, include uncertainty_box in required_components.\n"
    ).format(
        today=today.isoformat(),
        hypothesis=hyp_json,
        graph=graph_json,
        registry=COMPONENT_REGISTRY_TEXT,
    )
    return [
        {"role": "system", "content": STAGE1B_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _build_stage3_user_prompt(
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    today: date,
    max_research_chars: int,
) -> str:
    graph_json = _truncate_json(
        json.dumps(evidence_graph.model_dump(mode="json"), ensure_ascii=False, default=str),
        max_research_chars,
    )
    ia_json = _truncate_json(
        json.dumps(ia.model_dump(mode="json"), ensure_ascii=False),
        max_research_chars,
    )
    allowed_urls = sorted({str(s.url) for s in evidence_graph.sources})
    allowed_text = "\n".join(f"- {u}" for u in allowed_urls) or "- (none)"

    return (
        "Today's date is {today}.\n"
        "EvidenceAwareIA JSON:\n{ia}\n\n"
        "EvidenceGraph JSON:\n{graph}\n\n"
        "Allowed source URLs:\n{urls}\n\n"
        "Produce TopicPageData JSON. Include:\n"
        "  - headline (≤12 words)\n"
        "  - deck (one editorial sentence)\n"
        "  - summary (2-3 sentences)\n"
        "  - urgency_label, as_of_label\n"
        "  - key_facts (3-5)\n"
        "  - key_entities (≥1)\n"
        "  - timeline (≥1, earliest to latest)\n"
        "  - sections (3-6, only registry component types, every factual item carries a claim_id)\n"
        "Use null when uncertain; never fabricate.\n"
    ).format(today=today.isoformat(), ia=ia_json, graph=graph_json, urls=allowed_text)


def build_stage3_messages(
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    today: date,
    max_research_chars: int = 12000,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
        {"role": "user", "content": _build_stage3_user_prompt(evidence_graph, ia, today, max_research_chars)},
    ]


def build_stage3_revision_messages(
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    today: date,
    repair_actions: list[QARepairAction],
    failed_items: list[str] | None = None,
    max_research_chars: int = 12000,
) -> list[dict[str, str]]:
    base = _build_stage3_user_prompt(evidence_graph, ia, today, max_research_chars)
    actions_text = "\n".join(f"- {a.value}" for a in repair_actions) or "- none"
    items_text = "\n".join(f"- {i}" for i in (failed_items or [])) or "- none"

    revision = (
        "\nThe previous synthesis failed QA.\n"
        "Repair actions to address:\n{actions}\n\n"
        "Failed items:\n{items}\n\n"
        "Regenerate only the affected sections. Preserve grounded facts that already pass.\n"
        "If a required component is missing, add it using existing EvidenceGraph claims.\n"
        "If a claim is unsupported, replace it with a traceable one or drop the specificity.\n"
    ).format(actions=actions_text, items=items_text)

    return [
        {"role": "system", "content": STAGE3_SYSTEM_PROMPT},
        {"role": "user", "content": base + revision},
    ]


# Backward-compatible alias kept because some tests / scripts may import it.
def build_stage1_messages(sentence: str, today: date) -> list[dict[str, str]]:
    return build_stage1a_messages(sentence, today)
