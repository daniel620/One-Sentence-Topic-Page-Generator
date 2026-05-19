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
    EVENT_TYPE_REQUIREMENTS,
    EventType,
    EvidenceAwareIA,
    EvidenceGraph,
    EventHypothesis,
    QARepairAction,
)

MODEL_NAME = "claude-sonnet-4-5"
COMPONENT_REGISTRY_TEXT = ", ".join(c.value for c in COMPONENT_REGISTRY.component_types)


def _required_components_text(event_type: EventType) -> str:
    requirement = EVENT_TYPE_REQUIREMENTS.get(event_type)
    if not requirement:
        return "- action_list, stat_grid"
    return "\n".join(f"- {c.value}" for c in requirement.required_components)


STAGE1A_SYSTEM_PROMPT = """You classify a one-sentence event for a newsroom topic-page generator.

Your job is to:
- pick the event type from: tech_launch, live_event, sports_tournament, cultural_event, disaster, economic_event
- describe the freshness need (e.g. "live, sub-hour"; "this week"; "historical OK")
- propose 3-6 concrete search queries an editor would actually run
- list which source types are needed (official, primary_data, reputable_media, etc.)
- list 3-5 unknowns we'd need to resolve before publishing

CRITICAL: At least one search query MUST target the official/primary source for this event type:
- sports_tournament → "site:fifa.com OR site:olympics.com {event} announcement"
- tech_launch → "site:{company}.com {product} official announcement"
- cultural_event / live_event → "site:eurovision.com OR site:{organizer}.com {event} official"
- disaster → "site:fema.gov OR site:usgs.gov OR site:noaa.gov {event}"
- economic_event → "site:reuters.com OR site:bloomberg.com {event} economic impact"

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


STAGE3_SYSTEM_PROMPT = """You are a page composer, not a freeform article writer.

You receive a deck of verified claim cards. Each card has:
  - claim_id, claim_type, claim_topic
  - text: what the claim states (use this as the factual value)
  - an evidence sentence from the source
  - a best source (publisher + url)

Your job: compose these cards into a structured TopicPageData page.

You may exercise editorial judgment when writing:
  - headline (12 words max, concrete, no clickbait)
  - deck (one editorial sentence adding context beyond the headline)
  - summary (2-3 sentences answering what happened, why it matters, what changed)
  - urgency_label, as_of_label
  - key_facts (3-5 at-a-glance items — pick the most important cards)
  - section titles, section summaries, UIItem labels, UIItem detail text
  - action_list guidance and link_urls
  - timeline ordering
  - which claims to include in which sections (editorial selection and grouping)

You MUST NOT invent hard facts. For every factual assertion (a number, a
date, a location, an entity name, a schedule time, a status statement),
the value must come from a claim card. Set item.claim_id to the card's ID.

Do not calculate or derive new numbers from claim cards (e.g., computing a
duration from two dates, averaging values, or applying percentages). If a
specific number is not directly stated in a claim card, do not use it.

If a section has no suitable claim cards, make it shorter or omit it.
If claim cards are scarce, the page should be concise — don't pad.
If contradictions exist, add an uncertainty_box section.

Allowed component types: {component_registry}.

Terseness:
- summary: max 3 sentences. deck: max 22 words.
- Each section: max 5 items. Each item.value: max 25 words.
- Prefer fewer richer items over many thin ones.

No HTML, CSS, Markdown, or commentary outside the JSON.
""".format(component_registry=COMPONENT_REGISTRY_TEXT)


def _truncate_json(model_json: str, max_chars: int) -> str:
    return model_json if len(model_json) <= max_chars else model_json[:max_chars]


def _format_claim_cards(graph: EvidenceGraph) -> str:
    """Format public-eligible claims as a compact, scannable card list.

    Each card: [claim_id] claim_type.claim_topic — claim_text
               Evidence: <exact evidence sentence>
               Source: publisher · url
    """
    lines: list[str] = []
    public_claims = [c for c in graph.claims if getattr(c, "public_claim_eligible", False)]
    if not public_claims:
        # Fall back to all claims — better than an empty deck.
        public_claims = list(graph.claims)

    for claim in public_claims:
        ct = getattr(claim.claim_type, "value", str(claim.claim_type))
        topic = getattr(getattr(claim, "claim_topic", None), "value", "") or ""
        topic_str = f".{topic}" if topic else ""
        cid = claim.claim_id
        text = claim.text[:140]

        evidence = (getattr(claim, "evidence_sentence", "") or "")[:200]
        ev_line = f"  Evidence: \"{evidence}\"" if evidence else "  Evidence: (none)"

        # Find best source
        best_src = None
        if hasattr(graph, "get_source_by_id") and claim.source_ids:
            best_src = graph.get_source_by_id(claim.source_ids[0])
        src_line = ""
        if best_src:
            pub = best_src.publisher or "unknown"
            url = str(best_src.url)[:80]
            official = " ★" if getattr(best_src.source_type, "value", "") == "official" else ""
            src_line = f"  Source: {pub}{official} · {url}"

        lines.append(f"[{cid}] {ct}{topic_str} — {text}")
        if evidence:
            lines.append(ev_line)
        if src_line:
            lines.append(src_line)
        lines.append("")  # blank line separator

    return "\n".join(lines) if lines else "(no claim cards available — use the source list for context)"


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

    etype = hypothesis.preliminary_event_type
    required_text = _required_components_text(etype)

    user = (
        "Today's date is {today}.\n"
        "Hypothesis JSON:\n{hypothesis}\n\n"
        "EvidenceGraph JSON (truncated):\n{graph}\n\n"
        "For a {etype} page, you MUST include these mandatory components:\n"
        "{required}\n\n"
        "Return EvidenceAwareIA:\n"
        "  - final_event_type (confirm or revise)\n"
        "  - event_status\n"
        "  - page_thesis\n"
        "  - required_components (include all mandatory ones above + others from registry: {registry})\n"
        "  - layout_style\n"
        "  - confidence_summary\n"
        "If contradictions exist, include uncertainty_box.\n"
    ).format(
        today=today.isoformat(),
        etype=etype.value,
        required=required_text,
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
    claim_cards = _format_claim_cards(evidence_graph)
    claim_count = sum(1 for c in evidence_graph.claims if getattr(c, "public_claim_eligible", False)) or len(evidence_graph.claims)

    ia_json = _truncate_json(
        json.dumps(ia.model_dump(mode="json"), ensure_ascii=False),
        max_research_chars,
    )
    allowed_urls = sorted({str(s.url) for s in evidence_graph.sources})
    allowed_text = "\n".join(f"- {u}" for u in allowed_urls) or "- (none)"

    required = _required_components_text(ia.final_event_type)

    return (
        "Today: {today}\n"
        "Event type: {etype} | Status: {status}\n"
        "Page thesis: {thesis}\n\n"
        "CLAIM CARDS ({count} available — use these for every factual item):\n"
        "{cards}\n\n"
        "Allowed source URLs:\n{urls}\n\n"
        "MANDATORY sections for {etype}:\n{required}\n\n"
        "Compose TopicPageData from these claim cards.\n"
        "- headline, deck, summary: editorial framing — write freely.\n"
        "- key_facts: pick 3-5 most important cards. Set item.claim_id.\n"
        "- key_entities: list main organisations, people, things.\n"
        "- timeline: order schedule/date cards earliest to latest.\n"
        "- sections: one non-empty block per mandatory component. "
        "Every factual item.value MUST match a claim card's text. Set item.claim_id.\n"
        "For stat_grid/comparison_table: each item is a card. "
        "For action_list: link_urls may be editorial. "
        "For entity_list: names come from cards.\n"
        "If a mandatory section has no suitable cards, make it short (1 item). "
        "Never omit a mandatory section.\n"
        "NEVER invent a statistic, date, location, entity name, or schedule time.\n"
    ).format(
        today=today.isoformat(),
        etype=ia.final_event_type.value,
        status=ia.event_status.value,
        thesis=ia.page_thesis[:300],
        count=claim_count,
        cards=claim_cards,
        urls=allowed_text,
        required=required,
    )


def build_stage3_messages(
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    today: date,
    max_research_chars: int = 12000,
    *,
    page_mode: str = "full",
) -> list[dict[str, str]]:
    system = STAGE3_SYSTEM_PROMPT
    if page_mode == "degraded":
        system += (
            "\n\nDEGRADED MODE: Evidence is limited for this page. "
            "Be conservative with hard facts. Do NOT put unverified numbers in "
            "key_facts or stat_grid. Prefer timeline, entity_list, and action_list. "
            "Add qualifiers like 'Reported by [source]' to metric claims. "
            "Keep the page shorter and more cautious than usual. "
            "It is better to omit a weakly-sourced stat than to publish it."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _build_stage3_user_prompt(evidence_graph, ia, today, max_research_chars)},
    ]


# Backward-compatible alias kept because some tests / scripts may import it.
def build_stage1_messages(sentence: str, today: date) -> list[dict[str, str]]:
    return build_stage1a_messages(sentence, today)


# ============================================================================
# AI curation prompts
# ============================================================================

AI_SOURCE_CURATOR_SYSTEM = """You evaluate web sources for a newsroom topic-page generator. Your job is to decide whether each source is trustworthy and relevant enough to support public factual claims.

For each source you receive a summary line with: [source_type] publisher — title · URL path

Roles you can assign:
- public_claim_source  — strong enough to anchor public factual claims. Official, primary data, or well-known reputable media directly covering the event.
- supporting_context   — useful for context/background but not strong enough to be the sole source for a claim. Specialist blogs, local press, analysis pieces.
- background_only      — general reference, aggregation, or tangential coverage. Keep as background, don't cite publicly.
- debug_only           — social media, low-authority aggregator, SEO blog, user-generated content. Useful for understanding sentiment or finding leads, but never cite.
- reject               — irrelevant, spam, or content farm. Should not influence the page at all.
- needs_review         — unclear from the available information. The source might be useful but something looks off (thin content, wrong topic, no author). Flag for human review.

When in doubt, downgrade. A source that is miscategorised as public_claim_source is worse than one that is incorrectly classified as background_only."""


def build_ai_source_curation_messages(
    sources: list, event_sentence: str, today: date
) -> list[dict[str, str]]:
    source_lines = []
    for s in sources:
        url_path = ""
        try:
            from urllib.parse import urlparse
            url_path = urlparse(str(s.url)).path[:100] or "/"
        except Exception:
            url_path = "/"
        src_id = getattr(s, "source_id", "")
        pub = getattr(s, "publisher", "") or "unknown"
        st = getattr(getattr(s, "source_type", None), "value", "unknown")
        title = (getattr(s, "title", "") or "")[:120]
        source_lines.append(f"{src_id}: [{st}] {pub} — {title} · {url_path}")

    source_text = "\n".join(source_lines)

    user = (
        f"Today: {today.isoformat()}\n"
        f"Event: {event_sentence.strip()}\n\n"
        f"Sources ({len(sources)}):\n{source_text}\n\n"
        "Return one AISourceAssessment per source. Assign the most restrictive "
        "role you are confident about. Explain each rejection/downgrade briefly.\n"
    )
    return [
        {"role": "system", "content": AI_SOURCE_CURATOR_SYSTEM},
        {"role": "user", "content": user},
    ]


AI_CLAIM_EXTRACTOR_SYSTEM = """Extract factual claims from a news article about a current event. Return structured Claim objects.

Allowed claim types: metric, status, schedule, date, quote, location, entity, impact, action.

For each claim you MUST provide:
- claim_id: a unique short id like "c001", "c002"
- text: a concise ~1-sentence statement of the claim
- claim_type: one of the allowed types above
- claim_topic: pick from this list:
  event_schedule, venue, participants, pricing, capabilities, rollout_status,
  safety, metrics, controversy, history, how_to_watch, ticketing, other
- evidence_sentence: the EXACT sentence from the article that contains this claim. Copy it verbatim — do not paraphrase.
- public_claim_eligible: true if the evidence sentence is clearly stated in the article with a specific source or attribution, false if it is vague, inferential, or without supporting detail.
- confidence: high if multiple sources or explicit numbers, medium if stated but thin, low if inferential.
- source_ids: array containing only the source_id provided.

Rules:
- Do NOT fabricate claims. Only extract what is actually stated.
- Each evidence_sentence must be an exact quote from the article text.
- Prefer specific claims (numbers, dates, named entities) over vague statements.
- Skip claims that are purely opinion, speculation without attribution, or meta-commentary about the publication itself.
- Return 0-8 claims. Quality over quantity."""


def build_ai_claim_extraction_messages(
    article_text: str,
    source_id: str,
    event_sentence: str,
    today: date,
) -> list[dict[str, str]]:
    user = (
        f"Today: {today.isoformat()}\n"
        f"Event: {event_sentence.strip()}\n"
        f"This source's ID is: {source_id}\n\n"
        f"Article text:\n{article_text[:4000]}\n\n"
        "Extract all factual claims from this article about the event. "
        "Copy exact evidence sentences. Do not fabricate.\n"
    )
    return [
        {"role": "system", "content": AI_CLAIM_EXTRACTOR_SYSTEM},
        {"role": "user", "content": user},
    ]


AI_CONTRADICTION_REVIEWER_SYSTEM = """Review candidate factual contradictions for a newsroom topic page.

For each candidate, decide whether it represents:
- real_uncertainty — genuinely conflicting claims from different credible sources about the same specific fact. This should appear on the public page as an editorially meaningful uncertainty.
- scope_difference — the two numbers/dates refer to different things (different metrics, different timeframes, different aspects of the event). NOT a contradiction.
- extraction_noise — at least one side is clearly extraction garbage (irrelevant number, nav text, SEO boilerplate, wrong unit). Drop completely.
- debug_only — the conflict is minor, technical, or only would confuse readers without adding useful context. Keep for internal review but not on the public page.

Default to scope_difference or extraction_noise unless you are certain the claims genuinely conflict about the same specific fact in a way that would change reader understanding."""


# ============================================================================
# Product Critic prompt
# ============================================================================

PRODUCT_CRITIC_SYSTEM = """You are a Product Critic for a newsroom topic-page generator. Evaluate whether the evidence collected can support a useful, trustworthy page.

Evidence grades (from strongest to weakest):
- full_text_verified: claim backed by full article text extraction
- official_snippet: from an official/primary source, snippet only
- reputable_snippet: from reputable media, snippet only
- weak_snippet: from unknown/social/aggregator — never use for public claims

Decide one of:
- **publishable**: ≥1 official/primary source, ≥5 public-eligible claims with grade ≥ official_snippet, ≥3 core reader questions answered. Build the page.
- **editor_review**: Good evidence but one gap — no official source, or key fact relies on weak-snippet evidence backed by multiple independent sources. Build but flag for editor review.
- **evidence_limited**: Thin evidence. <5 verified claims, or most claims are snippet-grade, or only 1-2 core questions answered. Build with a prominent evidence-quality caveat explaining what's weak and why.
- **not_acceptable**: Critical flaw. <2 public-eligible claims, or all claims from one weak domain, or zero claims with evidence_sentence, or claims don't answer ANY core reader question.

If evidence_limited or not_acceptable and the event implies an organizing body (sports→FIFA, cultural contest→organizer, tech→company, disaster→government), generate 1-2 domain-targeted search queries to find the official source. Derive the domain from the event sentence — do NOT hardcode.

Event-type core reader questions:
- sports_tournament: when? where? who's playing? how to follow?
- tech_launch: what changed? who's affected? rollout status? what to do?
- live_event / cultural_event: when? where? who's performing? how to watch?
- disaster: where impacted? what's the status? what should people do?

Official/primary sources are critical. A page with 0 official sources should NEVER be publishable. If official sources are missing, generate a targeted search query including the primary entity name from the sentence plus domain hints (e.g., the event organizer's likely domain based on the event type)."""


def build_product_critic_messages(
    graph,
    event_type: str,
    sentence: str,
    today,
) -> list[dict[str, str]]:
    sources = graph.sources
    claims = graph.claims

    source_summary = []
    roles = {}
    for s in sources:
        r = getattr(getattr(s, "final_source_role", None), "value", "unknown")
        roles[r] = roles.get(r, 0) + 1
    source_summary.append(f"Source roles: {roles}")
    source_summary.append(f"Total sources: {len(sources)}")

    claim_summary = []
    claim_topics = {}
    verified = 0
    for c in claims:
        if getattr(c, "public_claim_eligible", False):
            t = getattr(getattr(c, "claim_topic", None), "value", "other")
            claim_topics[t] = claim_topics.get(t, 0) + 1
            if getattr(c, "evidence_sentence", ""):
                verified += 1
    public_count = sum(1 for c in claims if getattr(c, "public_claim_eligible", False))
    claim_summary.append(f"Public-eligible claims: {public_count}")
    claim_summary.append(f"Verified evidence sentences: {verified}")
    claim_summary.append(f"Claim topics: {claim_topics}")
    # Evidence grade breakdown
    grades = {}
    for c in claims:
        if getattr(c, "public_claim_eligible", False):
            g = getattr(getattr(c, "evidence_grade", None), "value", "weak_snippet")
            grades[g] = grades.get(g, 0) + 1
    claim_summary.append(f"Evidence grades: {grades}")

    contradictions = getattr(graph, "contradictions", [])
    real_unc = sum(1 for c in contradictions if getattr(c, "ai_resolution", None) and str(getattr(c, "ai_resolution").value) == "real_uncertainty")

    user = (
        f"Event type: {event_type}\n"
        f"Sentence: {sentence.strip()}\n"
        f"Today: {today.isoformat()}\n\n"
        f"Evidence:\n"
        f"  {chr(10).join(source_summary)}\n"
        f"  {chr(10).join(claim_summary)}\n"
        f"  Real uncertainties: {real_unc}\n\n"
        "Decide: proceed, re_search, weaken, or draft_only.\n"
        "If re_search, provide 2-3 targeted search queries for the missing evidence.\n"
        "If weaken, list specific caveats (what exactly is weak).\n"
    )
    return [
        {"role": "system", "content": PRODUCT_CRITIC_SYSTEM},
        {"role": "user", "content": user},
    ]


# ============================================================================
# Page Critic prompt — final acceptance review after rendering
# ============================================================================

PAGE_CRITIC_SYSTEM = """You are a Page Gate for a newsroom topic-page generator. You review a structured page summary and decide whether the page is ready for readers.

You receive a JSON-like summary with: headline, event type, confidence level, section breakdown (type, item count, items with claim citations), QA results, source counts by type, and contradiction information.

Decide:
- **publishable**: The page answers core reader questions, has credible sources, handles uncertainty honestly, and has no critical structural issues. Ready for light editorial review.
- **editor_review**: The page is generally sound but has one or more issues: thin sourcing in a key section, many QA-repaired items, or a confidence/evidence mismatch.
- **not_acceptable**: Critical flaw: confidence says HIGH but most items were repaired, or contradictions are shown that shouldn't be, or source profile is entirely social/unknown.

Evaluate:
1. Does the page structure fit the event type?
2. Are sections adequately populated with traceable claims?
3. Is the source profile credible (official + reputable_media dominant)?
4. Does the confidence level match the actual evidence quality?
5. If items were repaired (stripped), is the remaining content still useful?
6. Are any contradictions shown genuinely editorial and useful to a reader?

Be specific. If not publishable, say exactly what needs attention."""


def build_page_critic_messages(
    summary: dict,
) -> list[dict[str, str]]:
    import json
    user = (
        f"Page summary for review:\n{json.dumps(summary, indent=2, default=str)}\n\n"
        "Evaluate this page. Is it publishable, editor_review, or not_acceptable?\n"
        "Be specific about what needs attention if not publishable.\n"
    )
    return [
        {"role": "system", "content": PAGE_CRITIC_SYSTEM},
        {"role": "user", "content": user},
    ]


def build_ai_contradiction_review_messages(
    contradictions: list, today: date
) -> list[dict[str, str]]:
    items = []
    for i, c in enumerate(contradictions):
        items.append(
            f"#{i}: topic={c.topic} | "
            f"A='{c.claim_a}' (src: {','.join(c.sources_a)}) | "
            f"B='{c.claim_b}' (src: {','.join(c.sources_b)})"
        )
    cand_text = "\n".join(items)

    user = (
        f"Today: {today.isoformat()}\n\n"
        f"Candidate contradictions ({len(contradictions)}):\n{cand_text}\n\n"
        "Return one AIContradictionReview per candidate. "
        "Default to scope_difference or extraction_noise unless genuinely conflicting "
        "about the same fact in a reader-meaningful way.\n"
    )
    return [
        {"role": "system", "content": AI_CONTRADICTION_REVIEWER_SYSTEM},
        {"role": "user", "content": user},
    ]
