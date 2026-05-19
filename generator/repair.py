"""Deterministic page repair — strips problematic content before render.

When QA finds problems, this module fixes them directly on the
TopicPageData. No LLM re-composition. No "please try again." Each
repair strategy is a pure function that removes or modifies the
specific problematic content.

This is the key architectural difference between "quality signals"
and "quality enforcement." The old approach flagged problems and
hoped the LLM would fix them. This approach removes the problems.
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from generator.schemas import (
    ComponentType,
    ConfidenceLevel,
    EvidenceGraph,
    QARepairAction,
    TopicPageData,
    UIComponent,
    UIItem,
)

LOGGER = logging.getLogger("repair")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _item_claim_id(item: Any) -> str | None:
    cid = _get(item, "claim_id")
    return str(cid) if cid else None


def _collect_contradiction_claim_ids(
    evidence_graph: EvidenceGraph,
) -> set[str]:
    """Find all claim IDs involved in real_uncertainty contradictions.

    These are claim pairs that the AI reviewer (or pre-filter) confirmed
    as genuinely conflicting. We strip BOTH sides from the page.
    """
    conflicted: set[str] = set()
    for c in evidence_graph.contradictions:
        ai_res = getattr(c, "ai_resolution", None)
        if ai_res is None:
            continue
        res_value = ai_res.value if hasattr(ai_res, "value") else str(ai_res)
        if res_value != "real_uncertainty":
            continue
        # Find claim IDs that back each side of the contradiction
        for claim in evidence_graph.claims:
            cid = getattr(claim, "claim_id", "")
            sources = list(getattr(claim, "source_ids", []))
            # Match by source_id overlap with contradiction sources
            if any(s in c.sources_a for s in sources):
                conflicted.add(cid)
            if any(s in c.sources_b for s in sources):
                conflicted.add(cid)
    return conflicted


def _collect_unsupported_metric_claim_ids(
    evidence_graph: EvidenceGraph,
) -> set[str]:
    """Find metric claims that lack evidence_sentence or source_ids."""
    unsupported: set[str] = set()
    for claim in evidence_graph.claims:
        ct = getattr(claim, "claim_type", None)
        ct_value = ct.value if hasattr(ct, "value") else str(ct) if ct else ""
        if ct_value != "metric":
            continue
        # Check evidence from both claim_attributes and top-level fields
        attrs = getattr(claim, "claim_attributes", {}) or {}
        snippet = str(
            attrs.get("evidence_snippet", "") or
            getattr(claim, "evidence_snippet", "") or
            getattr(claim, "evidence_sentence", "") or ""
        ).strip()
        claim_sources = list(getattr(claim, "source_ids", []))
        if not claim_sources or not snippet:
            unsupported.add(getattr(claim, "claim_id", ""))
    return unsupported


def strip_conflicting_items(
    sections: list[UIComponent],
    conflicted_claim_ids: set[str],
) -> tuple[list[UIComponent], int]:
    """Remove items backed by conflicting claims from all sections."""
    removed = 0
    result: list[UIComponent] = []
    for section in sections:
        kept_items: list[UIItem] = []
        for item in section.items:
            cid = _item_claim_id(item)
            if cid and cid in conflicted_claim_ids:
                LOGGER.info("Repair: removing conflicting item '%s' (claim %s)", _get(item, "label", "?"), cid)
                removed += 1
                continue
            kept_items.append(item)
        if kept_items:
            new_section = section.model_copy(update={"items": kept_items})
            result.append(new_section)
        else:
            LOGGER.info("Repair: removing empty section '%s' after conflict strip", section.title)
    return result, removed


def strip_unsupported_items(
    sections: list[UIComponent],
    unsupported_claim_ids: set[str],
) -> tuple[list[UIComponent], int]:
    """Remove items backed by unsupported metric claims."""
    removed = 0
    result: list[UIComponent] = []
    for section in sections:
        kept_items: list[UIItem] = []
        for item in section.items:
            cid = _item_claim_id(item)
            if cid and cid in unsupported_claim_ids:
                LOGGER.info("Repair: removing unsupported item '%s' (claim %s)", _get(item, "label", "?"), cid)
                removed += 1
                continue
            kept_items.append(item)
        if kept_items:
            result.append(section.model_copy(update={"items": kept_items}))
        else:
            LOGGER.info("Repair: removing empty section '%s' after unsupported strip", section.title)
    return result, removed


def strip_missing_claim_items(
    sections: list[UIComponent],
) -> tuple[list[UIComponent], int]:
    """Remove items in traceable sections that have no claim_id.

    Traceable sections: stat_grid, comparison_table, live_tracker,
    timeline, key_facts. These contain factual claims that must be
    traceable to the evidence graph.
    """
    TRACEABLE = {
        ComponentType.STAT_GRID,
        ComponentType.COMPARISON_TABLE,
        ComponentType.LIVE_TRACKER,
        ComponentType.TIMELINE,
        ComponentType.KEY_FACTS,
    }
    removed = 0
    result: list[UIComponent] = []
    for section in sections:
        if section.component_type not in TRACEABLE:
            result.append(section)
            continue
        kept_items: list[UIItem] = []
        for item in section.items:
            cid = _item_claim_id(item)
            if not cid:
                LOGGER.info("Repair: removing untraceable item '%s' from %s", _get(item, "label", "?"), section.component_type.value)
                removed += 1
                continue
            kept_items.append(item)
        if kept_items:
            result.append(section.model_copy(update={"items": kept_items}))
        else:
            LOGGER.info("Repair: removing empty section '%s' after traceability strip", section.title)
    return result, removed


def fill_missing_required_components(
    sections: list[UIComponent],
    required_components: list[ComponentType],
) -> list[UIComponent]:
    """Add placeholder sections for missing required components."""
    present = {s.component_type for s in sections}
    result = list(sections)
    for req in required_components:
        if req not in present:
            LOGGER.info("Repair: adding placeholder for missing required component '%s'", req.value)
            result.append(UIComponent(
                component_type=req,
                title=_placeholder_title(req),
                summary="Details will be added as more information becomes available.",
                items=[UIItem(
                    label="Coming soon",
                    value="Information is still being gathered and verified.",
                    detail="Check back for updates or refer to the sources below.",
                )],
            ))
    return result


def _placeholder_title(ct: ComponentType) -> str:
    titles = {
        ComponentType.STAT_GRID: "Key Metrics",
        ComponentType.COMPARISON_TABLE: "Comparison",
        ComponentType.LIVE_TRACKER: "Current Status",
        ComponentType.ACTION_LIST: "What You Can Do",
        ComponentType.TIMELINE: "Timeline",
        ComponentType.ENTITY_LIST: "Key Participants",
        ComponentType.KEY_FACTS: "At a Glance",
    }
    return titles.get(ct, ct.value.replace("_", " ").title())


def compute_confidence(
    sections: list[UIComponent],
    items_removed: int,
    original_qa_score: float,
) -> ConfidenceLevel:
    """Recalculate confidence after repairs.

    Removing items is a sign of weak evidence. A page that had many
    items stripped should not claim high confidence.
    """
    total_items = sum(len(s.items) for s in sections)
    if total_items == 0:
        return ConfidenceLevel.LOW
    if items_removed >= 5 or original_qa_score < 0.5:
        return ConfidenceLevel.LOW
    if items_removed >= 2 or original_qa_score < 0.7:
        return ConfidenceLevel.MEDIUM
    if original_qa_score >= 0.85:
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.MEDIUM


def repair_page(
    page: TopicPageData,
    evidence_graph: EvidenceGraph,
    qa_score: float,
    required_components: list[ComponentType] | None = None,
) -> tuple[TopicPageData, dict[str, int]]:
    """Apply all deterministic repairs to a page.

    Returns (repaired_page, repair_summary).
    repair_summary tracks what was changed for logging/debugging.

    The repairs are applied in order:
      1. Strip items backed by conflicting claims
      2. Strip items backed by unsupported metric claims
      3. Strip items missing claim_ids in traceable sections
      4. Fill missing required components with placeholders
      5. Recalculate confidence
    """
    total_removed = 0
    sections = [s for s in page.sections]  # shallow copy

    # 1. Conflicting claims
    conflicted = _collect_contradiction_claim_ids(evidence_graph)
    if conflicted:
        sections, n = strip_conflicting_items(sections, conflicted)
        total_removed += n

    # 2. Unsupported metric claims
    unsupported = _collect_unsupported_metric_claim_ids(evidence_graph)
    if unsupported:
        sections, n = strip_unsupported_items(sections, unsupported)
        total_removed += n

    # 3. Missing claim_ids in traceable sections
    sections, n = strip_missing_claim_items(sections)
    total_removed += n

    # 4. Fill missing required components
    if required_components:
        sections = fill_missing_required_components(sections, required_components)

    # 5. Recalculate confidence
    new_confidence = compute_confidence(sections, total_removed, qa_score)

    # Build repaired page
    repaired = page.model_copy(update={
        "sections": sections,
        "confidence": new_confidence,
    })

    summary = {
        "items_removed": total_removed,
        "conflicted_claims_stripped": len(conflicted),
        "unsupported_stripped": len(unsupported),
        "confidence_before": page.confidence.value,
        "confidence_after": new_confidence.value,
    }

    LOGGER.info(
        "Repair: removed %d items, confidence %s → %s",
        total_removed, page.confidence.value, new_confidence.value,
    )
    return repaired, summary
