"""Pure renderer: `TopicPageData` → HTML.

This module makes three product-critical decisions, in order:

1. **Public vs. debug mode.** Public is the default and never exposes
   internal trace fields (claim IDs, source IDs, QA gate names, repair
   actions, layout/event-type metadata pills). Debug mode re-adds them at
   the bottom of the page for engineers reviewing the pipeline.

2. **Layout recipe.** Each `(event_type, status)` maps to a `PageRecipe`
   in `generator.page_layout`, which picks the hero variant, the CSS
   theme, and the canonical section order. The LLM provides content; the
   recipe owns presentation.

3. **Editorial citations.** Inline `<cite>` chips show *publisher · date*,
   not `claim_id` and a numeric score. The full source list lives in a
   compact footer.

The renderer is a pure function. No LLM calls, no hidden mutation, no
network. Anything weird in the output is in the data or the template.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel

from generator.page_layout import PageRecipe, get_recipe
from generator.schemas import (
    ComponentType,
    ConfidenceLevel,
    EvidenceGraph,
    KeyFact,
    RenderMode,
    Source,
    TopicPageData,
    UIComponent,
    UIItem,
)

TEMPLATE_NAME = "page.html.j2"

COMPONENT_TEMPLATE_BY_TYPE: dict[ComponentType, str] = {
    ComponentType.STAT_GRID: "components/stat_grid.html.j2",
    ComponentType.KEY_FACTS: "components/key_facts.html.j2",
    ComponentType.COMPARISON_TABLE: "components/comparison_table.html.j2",
    ComponentType.LIVE_TRACKER: "components/live_tracker.html.j2",
    ComponentType.ACTION_LIST: "components/action_list.html.j2",
    ComponentType.TIMELINE: "components/timeline.html.j2",
    ComponentType.ENTITY_LIST: "components/entity_list.html.j2",
    ComponentType.SOURCE_LIST: "components/source_list.html.j2",
    ComponentType.UNCERTAINTY_BOX: "components/uncertainty_box.html.j2",
    ComponentType.CONFIDENCE_BANNER: "components/confidence_banner.html.j2",
}


# ---------------------------------------------------------------------------
# Lookup builders
# ---------------------------------------------------------------------------

def _serialize(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def _source_view(source: Source) -> dict[str, Any]:
    """Editorial view of a `Source` — what the template renders inline."""

    publisher = source.publisher or _domain_from_url(str(source.url))
    return {
        "source_id": source.source_id,
        "url": str(source.url),
        "title": source.title,
        "publisher": publisher,
        "publisher_short": _short_publisher(publisher),
        "published_at": _format_short_date(source.published_at),
        "published_iso": source.published_at.isoformat() if source.published_at else None,
        "source_type": source.source_type.value,
        "is_official": source.source_type.value == "official",
        "overall_score": round(source.overall_score, 3),
    }


def _domain_from_url(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.replace("www.", "")
    except Exception:
        return url


def _short_publisher(publisher: str) -> str:
    """Trim publisher names so they fit in inline citations."""
    if not publisher:
        return ""
    return publisher if len(publisher) <= 28 else publisher[:25].rstrip() + "…"


def _format_short_date(dt: datetime | None) -> str | None:
    if not dt:
        return None
    return dt.strftime("%b %-d, %Y") if hasattr(dt, "strftime") else None


def _build_source_lookup(graph: EvidenceGraph) -> dict[str, dict[str, Any]]:
    return {source.source_id: _source_view(source) for source in graph.sources}


def _claim_citation_sources(
    claim: Any, source_lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    sources = [source_lookup[sid] for sid in getattr(claim, "source_ids", []) if sid in source_lookup]
    # Editorial citation: official sources first, then by overall_score desc.
    sources.sort(key=lambda s: (not s["is_official"], -s["overall_score"]))
    return sources[:3]


def _build_claim_lookup(
    graph: EvidenceGraph, source_lookup: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    claim_lookup: dict[str, dict[str, Any]] = {}
    for claim in graph.claims:
        sources = _claim_citation_sources(claim, source_lookup)
        claim_lookup[claim.claim_id] = {
            "claim_id": claim.claim_id,
            "text": claim.text,
            "claim_type": getattr(claim.claim_type, "value", claim.claim_type),
            "confidence": getattr(claim.confidence, "value", claim.confidence),
            "sources": sources,
            "best_source": sources[0] if sources else None,
        }
    return claim_lookup


# ---------------------------------------------------------------------------
# QA banners (public + debug differ)
# ---------------------------------------------------------------------------

def _qa_summary(page: TopicPageData) -> dict[str, Any]:
    failed_gates: list[str] = []
    repair_actions: list[str] = []
    scores: list[float] = []
    for result in page.qa_results:
        if isinstance(result, BaseModel):
            data = result.model_dump(mode="json")
        else:
            data = dict(result)
        scores.append(float(data.get("confidence_score", 0.0)))
        if data.get("status") == "fail":
            failed_gates.append(str(data.get("gate_name", "")))
        for action in data.get("repair_actions", []):
            value = getattr(action, "value", action)
            if value not in repair_actions:
                repair_actions.append(str(value))
    avg_score = round(sum(scores) / len(scores), 3) if scores else 1.0
    return {
        "failed_gates": failed_gates,
        "repair_actions": repair_actions,
        "average_score": avg_score,
    }


def _build_confidence_banner(page: TopicPageData) -> UIComponent | None:
    """Show a confidence warning only when there is *real* risk.

    Public-mode rule: render only when at least one QA gate failed OR
    confidence is explicitly LOW. We never render a "Confidence warning"
    for a high-confidence page just because we have no QA data attached.
    """
    summary = _qa_summary(page)
    if page.confidence == ConfidenceLevel.HIGH and not summary["failed_gates"]:
        return None
    if page.confidence == ConfidenceLevel.MEDIUM and not summary["failed_gates"]:
        return None
    if not summary["failed_gates"] and page.confidence != ConfidenceLevel.LOW:
        return None

    items: list[UIItem] = []
    if summary["failed_gates"]:
        items.append(
            UIItem(
                label="What we couldn't confirm",
                value=_humanize_failed_gates(summary["failed_gates"]),
                detail=(
                    "Our automated checks flagged this before publish. "
                    "Treat specific numbers and dates as provisional."
                ),
            )
        )
    if page.confidence == ConfidenceLevel.LOW:
        # Check if sources are actually weak or if LOW is from QA gate failures.
        source_counts = _count_source_quality(page)
        official = source_counts.get("official", 0) + source_counts.get("primary_data", 0)
        reputable = source_counts.get("reputable_media", 0) + source_counts.get("local_media", 0)
        reason = "Low — "
        if official < 3:
            reason += "limited primary-source coverage"
        elif reputable < 2:
            reason += "limited independent reporting"
        else:
            reason += "some claims need stronger grounding"
        items.append(
            UIItem(
                label="Confidence",
                value=reason,
                detail="Cross-check the linked sources before re-publishing.",
            )
        )
    if not items:
        items.append(
            UIItem(
                label="Heads up",
                value="Some facts on this page are still developing.",
                detail="Refer to the sources at the bottom for the latest.",
            )
        )

    return UIComponent(
        component_type=ComponentType.CONFIDENCE_BANNER,
        title="Editor's note",
        summary="This page surfaces what is solid, and flags what isn't.",
        items=items,
    )


def _count_source_quality(page: TopicPageData) -> dict[str, int]:
    """Count sources by source_type in the full evidence graph."""
    counts: dict[str, int] = {}
    graph = page.evidence_graph_ref
    if graph:
        for src in graph.sources:
            t = getattr(getattr(src, "source_type", None), "value", "unknown")
            counts[t] = counts.get(t, 0) + 1
    return counts


def _humanize_failed_gates(failed_gates: list[str]) -> str:
    labels = {
        "factuality": "claim-to-source traceability",
        "freshness": "source freshness",
        "event_fit": "required page sections",
    }
    parts = [labels.get(g, g) for g in failed_gates if g]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def _build_uncertainty_box(
    graph: EvidenceGraph, source_lookup: dict[str, dict[str, Any]]
) -> UIComponent | None:
    # Only show contradictions the AI reviewer classified as real uncertainty.
    # Unreviewed contradictions (no ai_resolution) are shown as a fallback.
    public_contradictions = [
        c for c in graph.contradictions
        if not getattr(c, "ai_resolution", None)
        or str(c.ai_resolution.value) == "real_uncertainty"
    ]
    if not public_contradictions:
        return None
    items: list[UIItem] = []
    for contradiction in public_contradictions:
        sources_a = ", ".join(
            source_lookup[sid]["publisher_short"]
            for sid in contradiction.sources_a
            if sid in source_lookup
        )
        sources_b = ", ".join(
            source_lookup[sid]["publisher_short"]
            for sid in contradiction.sources_b
            if sid in source_lookup
        )
        detail_pieces = []
        if sources_a:
            detail_pieces.append(f"Reported by {sources_a}.")
        if sources_b:
            detail_pieces.append(f"Counter: {sources_b}.")
        items.append(
            UIItem(
                label=contradiction.topic,
                value=f"{contradiction.claim_a} — vs — {contradiction.claim_b}",
                detail=" ".join(detail_pieces) or None,
            )
        )
    return UIComponent(
        component_type=ComponentType.UNCERTAINTY_BOX,
        title="What we can't reconcile yet",
        summary="Two reputable sources disagree. We're keeping both visible until one settles.",
        items=items,
    )


# ---------------------------------------------------------------------------
# Section ordering by recipe
# ---------------------------------------------------------------------------

def _is_placeholder_section(section: UIComponent) -> bool:
    """True when every item in the section is a repair-generated placeholder."""
    return all(
        getattr(item, "label", "") == "Coming soon"
        for item in section.items
    )


def _split_and_order_sections(
    page: TopicPageData, recipe: PageRecipe
) -> tuple[list[UIComponent], list[UIComponent], list[UIComponent]]:
    """Return (pinned_top, body, uncertainty_and_followups) ordered by recipe."""

    pinned: list[UIComponent] = []
    body: list[UIComponent] = []
    uncertainty: list[UIComponent] = []

    for section in page.sections:
        if section.component_type == ComponentType.UNCERTAINTY_BOX:
            uncertainty.append(section)
            continue
        if section.component_type == ComponentType.CONFIDENCE_BANNER:
            # Banner is built by the renderer; drop any stage-3 attempt to inject one.
            continue
        if section.component_type in recipe.pinned_top:
            pinned.append(section)
        else:
            body.append(section)

    body.sort(key=lambda s: recipe.order_key(s.component_type))
    return pinned, body, uncertainty


# ---------------------------------------------------------------------------
# Filters for templates
# ---------------------------------------------------------------------------

def _format_date_label(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %-d, %Y")
    return str(value)


def _split_by_separator(value: str | None, separator: str) -> list[str]:
    if not value:
        return []
    return [piece.strip() for piece in value.split(separator) if piece.strip()]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def render_topic_page(
    data: TopicPageData,
    template_dir: Path | None = None,
    mode: RenderMode | str = RenderMode.PUBLIC,
) -> str:
    if isinstance(mode, str):
        mode = RenderMode(mode)
    is_debug = mode == RenderMode.DEBUG

    if template_dir is None:
        template_dir = Path(__file__).resolve().parent.parent / "templates"

    recipe = get_recipe(data.event_type, data.status)

    graph = data.evidence_graph_ref
    source_lookup = _build_source_lookup(graph) if graph else {}
    claim_lookup = _build_claim_lookup(graph, source_lookup) if graph else {}

    confidence_banner = _build_confidence_banner(data)
    pinned_sections, body_sections, uncertainty_sections = _split_and_order_sections(data, recipe)

    # In public mode, suppress repair-generated placeholder sections
    # where every item is "Coming soon". These are useful debug signals
    # but look unfinished on a published page.
    if not is_debug:
        pinned_sections = [s for s in pinned_sections if not _is_placeholder_section(s)]
        body_sections = [s for s in body_sections if not _is_placeholder_section(s)]

    if graph and not uncertainty_sections:
        derived_uncertainty = _build_uncertainty_box(graph, source_lookup)
        if derived_uncertainty:
            uncertainty_sections = [derived_uncertainty]

    sources_for_footer = sorted(
        source_lookup.values(),
        key=lambda s: (not s["is_official"], -s["overall_score"]),
    )

    # In public mode, drop social-media and aggregator sources from the
    # footer — they don't meet editorial citation standards.
    if not is_debug:
        sources_for_footer = [
            s for s in sources_for_footer
            if s.get("source_type") not in ("social", "aggregator")
        ]

    key_facts = _resolve_key_facts(data.key_facts, claim_lookup)

    qa_summary = _qa_summary(data)

    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["short_date"] = _format_date_label
    env.filters["split_sep"] = _split_by_separator

    # Debug: summarise source roles and contradictions.
    source_roles = {}
    public_claims = 0
    if graph:
        for src in graph.sources:
            role = getattr(getattr(src, "final_source_role", None), "value", "unknown")
            source_roles[role] = source_roles.get(role, 0) + 1
        public_claims = sum(1 for c in graph.claims if getattr(c, "public_claim_eligible", False))
    source_roles_summary = ", ".join(f"{k}:{v}" for k, v in sorted(source_roles.items()))

    contradictions_debug = []
    if graph and is_debug:
        for c in graph.contradictions:
            ai_res = getattr(c, "ai_resolution", None)
            contradictions_debug.append({
                "topic": c.topic,
                "claim_a": c.claim_a,
                "claim_b": c.claim_b,
                "resolution": ai_res.value if ai_res else "unreviewed",
            })

    template = env.get_template(TEMPLATE_NAME)

    return template.render(
        page=data,
        recipe=recipe,
        mode=mode.value,
        is_debug=is_debug,
        is_public=not is_debug,
        component_template_by_type=COMPONENT_TEMPLATE_BY_TYPE,
        generated_at=datetime.now(timezone.utc).strftime("%b %-d, %Y · %H:%M UTC"),
        evidence_graph_ref=graph,
        source_lookup_by_id=source_lookup,
        claim_lookup_by_id=claim_lookup,
        sources_for_footer=sources_for_footer,
        key_facts=key_facts,
        confidence_banner=confidence_banner,
        pinned_sections=pinned_sections,
        body_sections=body_sections,
        uncertainty_sections=uncertainty_sections,
        qa_summary=qa_summary,
        source_roles_summary=source_roles_summary,
        public_claims_count=public_claims,
        contradictions_debug=contradictions_debug,
    )


def _resolve_key_facts(
    key_facts: list[KeyFact], claim_lookup: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for fact in key_facts:
        claim = claim_lookup.get(fact.claim_id) if fact.claim_id else None
        best_source = claim["best_source"] if claim and claim.get("best_source") else None
        resolved.append(
            {
                "label": fact.label,
                "value": fact.value,
                "hint": fact.hint,
                "claim_id": fact.claim_id,
                "best_source": best_source,
            }
        )
    return resolved
