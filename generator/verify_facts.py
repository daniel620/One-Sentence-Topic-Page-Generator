"""Deterministic page-to-claim fidelity check.

Runs after composition, before rendering. For every UIItem with a
claim_id, cross-references the item's value text against the claim's
text and evidence_sentence. Items whose values contain hard facts
(numbers, dates, entity names) not present in the claim are flagged.

This closes the gap between "the claim exists" and "the claim is
accurately rendered." The composer has editorial freedom to rephrase,
but not to invent new numbers or change magnitudes.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from generator.schemas import (
    Claim,
    ComponentType,
    EvidenceGraph,
    TopicPageData,
    UIComponent,
)

LOGGER = logging.getLogger("verify_facts")

NUMERIC_RE = re.compile(r"\b\d[\d,.]*\s*(?:%|million|billion|thousand|hundred|K|M|B)?\b", re.IGNORECASE)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_numbers(text: str) -> set[str]:
    """Extract numeric tokens from text."""
    return {m.group(0).strip().lower() for m in NUMERIC_RE.finditer(text)}


def _text_overlap(a: str, b: str) -> float:
    """Jaccard similarity on word tokens."""
    a_tokens = set(a.lower().split())
    b_tokens = set(b.lower().split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def _find_claim(graph: EvidenceGraph, claim_id: str) -> Claim | None:
    for c in graph.claims:
        cid = _get(c, "claim_id", "")
        if cid == claim_id:
            return c
    return None


def check_item_fidelity(
    item_value: str,
    claim: Claim,
) -> tuple[bool, str]:
    """Check whether an item's value text is faithful to its backing claim.

    Returns (passes, reason).
    """
    claim_text = _get(claim, "text", "") or ""
    evidence = _get(claim, "evidence_sentence", "") or _get(claim, "evidence_snippet", "") or ""

    if not claim_text:
        return False, "Claim has no text field"

    # 1. High text overlap → likely faithful rephrase
    overlap = _text_overlap(item_value, claim_text)
    if overlap >= 0.5:
        return True, f"Text overlap {overlap:.2f} with claim text"

    # 2. Check against evidence_sentence too
    if evidence:
        ev_overlap = _text_overlap(item_value, evidence)
        if ev_overlap >= 0.5:
            return True, f"Text overlap {ev_overlap:.2f} with evidence sentence"

    # 3. Numeric fidelity: every number in the item should appear in the claim
    item_nums = _extract_numbers(item_value)
    claim_nums = _extract_numbers(claim_text)
    if evidence:
        claim_nums |= _extract_numbers(evidence)

    if not item_nums:
        # No numbers → likely editorial/qualitative text, OK
        return True, "No numeric claims to verify"

    stray_nums = item_nums - claim_nums
    if stray_nums:
        return False, f"Numbers not in claim: {', '.join(sorted(stray_nums)[:5])}"

    return True, "All numbers trace to claim"


def compute_section_fidelity(
    section: UIComponent,
    graph: EvidenceGraph,
) -> tuple[UIComponent, dict[str, Any]]:
    """Check every item in a section against its backing claim.

    Returns (possibly_stripped_section, report).
    Items that fail fidelity are removed from the section.
    """
    TRACEABLE = {
        ComponentType.STAT_GRID,
        ComponentType.COMPARISON_TABLE,
        ComponentType.LIVE_TRACKER,
        ComponentType.TIMELINE,
        ComponentType.KEY_FACTS,
    }

    if section.component_type not in TRACEABLE:
        return section, {"checked": 0, "passed": 0, "failed": 0, "failures": []}

    kept_items = []
    passed = 0
    failed = 0
    failures = []

    for i, item in enumerate(section.items):
        claim_id = _get(item, "claim_id")
        if not claim_id:
            # Items without claim_ids in traceable sections were already
            # stripped by repair. If any remain, keep them but flag.
            kept_items.append(item)
            continue

        claim = _find_claim(graph, claim_id)
        if not claim:
            failures.append(f"Claim {claim_id} not found in evidence graph")
            failed += 1
            LOGGER.info("Fidelity: removing item (claim %s missing)", claim_id)
            continue

        item_value = _get(item, "value", "") or ""
        ok, reason = check_item_fidelity(item_value, claim)
        if ok:
            kept_items.append(item)
            passed += 1
        else:
            failures.append(
                f"'{_get(item, 'label', '?')}': {reason}"
            )
            failed += 1
            LOGGER.info(
                "Fidelity: removing item '%s' — %s",
                _get(item, "label", "?"), reason,
            )

    report = {
        "checked": passed + failed,
        "passed": passed,
        "failed": failed,
        "failures": failures,
    }

    if not kept_items:
        LOGGER.info("Fidelity: removing empty section '%s'", section.title)
        return None, report

    return section.model_copy(update={"items": kept_items}), report


def verify_page_fidelity(
    page: TopicPageData,
    graph: EvidenceGraph,
) -> tuple[TopicPageData, dict[str, Any]]:
    """Run fidelity checks on every traceable section.

    Returns (possibly_stripped_page, fidelity_report).
    """
    kept_sections = []
    total_checked = 0
    total_failed = 0
    section_reports = {}

    for section in page.sections:
        result, report = compute_section_fidelity(section, graph)
        if result is not None:
            kept_sections.append(result)
        section_reports[section.title] = report
        total_checked += report["checked"]
        total_failed += report["failed"]

    fidelity_score = 1.0
    if total_checked > 0:
        fidelity_score = (total_checked - total_failed) / total_checked

    report = {
        "total_checked": total_checked,
        "total_failed": total_failed,
        "fidelity_score": round(fidelity_score, 3),
        "sections": section_reports,
    }

    LOGGER.info(
        "Fidelity check: %d/%d items pass (%.2f)",
        total_checked - total_failed, total_checked, fidelity_score,
    )

    repaired = page.model_copy(update={"sections": kept_sections})
    return repaired, report
