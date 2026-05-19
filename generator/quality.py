"""QA gates that can change the page before it is rendered.

Three gates:
  - factuality: every factual section item ties back to an EvidenceGraph claim.
  - freshness:  sources are recent enough for the event's status.
  - event_fit:  the page contains the required components for its event type.

If any gate fails the pipeline asks Stage 3 to revise the page, bounded by
`max_qa_iterations` in `generator.pipeline`.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from datetime import date, datetime, timezone
from typing import Any

from generator.schemas import (
    COMPONENT_REGISTRY,
    ComponentType,
    ConfidenceLevel,
    EvidenceAwareIA,
    EvidenceGraph,
    EventStatus,
    EVENT_TYPE_REQUIREMENTS,
    QARepairAction,
    QAGateResult,
    TopicPageData,
)

NUMERIC_PATTERN = re.compile(r"\d")
NUMERIC_VALUE_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)*")
DATE_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:,?\s+\d{4})?"
    r"|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b",
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r"\b([0-1]?[0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?\s*(?:AM|PM|am|pm)?\b")
STATUS_TERMS = {
    "live", "upcoming", "scheduled", "concluded", "developing", "ongoing",
    "final", "postponed", "delayed", "released", "launched", "rollout",
}
STRICT_STATUSES = {
    EventStatus.LIVE,
    EventStatus.UPCOMING,
    EventStatus.SCHEDULED,
    EventStatus.DEVELOPING,
}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_list(value: Any) -> list[Any]:
    return [] if value is None else list(value)


def _normalize_component_type(value: Any) -> ComponentType | None:
    try:
        return COMPONENT_REGISTRY.validate_component_type(value)
    except ValueError:
        return None


def _text_from_item(item: Any) -> str:
    parts = [str(_get(item, "label", "") or ""), str(_get(item, "value", "") or ""), str(_get(item, "detail", "") or "")]
    return " ".join(p for p in parts if p).strip()


def _item_claim_id(item: Any) -> str | None:
    claim_id = _get(item, "claim_id")
    return str(claim_id) if claim_id else None


def _is_numeric_like(text: str) -> bool:
    return bool(NUMERIC_PATTERN.search(text))


def _is_date_or_time_like(text: str) -> bool:
    return bool(DATE_PATTERN.search(text) or TIME_PATTERN.search(text))


def _is_status_like(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in STATUS_TERMS)


def _extract_numeric_values(text: str) -> set[str]:
    """Extract complete numeric tokens (integers and decimals) from text."""
    return {m.group(0) for m in NUMERIC_VALUE_PATTERN.finditer(text)}


def _needs_traceability(section_type: ComponentType | None, item: Any) -> bool:
    text = _text_from_item(item)
    value = str(_get(item, "value", "") or "")
    if _item_claim_id(item):
        return False
    if section_type in {
        ComponentType.STAT_GRID,
        ComponentType.COMPARISON_TABLE,
        ComponentType.LIVE_TRACKER,
        ComponentType.TIMELINE,
        ComponentType.KEY_FACTS,
    }:
        return True
    # Action lists, entity lists, and source lists are editorial guidance,
    # not factual claim surfaces. Numbers in action items are link labels.
    if section_type in {
        ComponentType.ACTION_LIST,
        ComponentType.ENTITY_LIST,
        ComponentType.SOURCE_LIST,
    }:
        return False
    return bool(_is_numeric_like(value) or _is_date_or_time_like(text) or _is_status_like(text))


def _find_claim(evidence_graph: EvidenceGraph, claim_id: str) -> Any | None:
    for claim in evidence_graph.claims:
        if claim.claim_id == claim_id:
            return claim
    return None


def _dedupe(actions: list[QARepairAction]) -> list[QARepairAction]:
    return list(OrderedDict.fromkeys(actions))


def confidence_level_from_score(score: float) -> ConfidenceLevel:
    if score >= 0.85:
        return ConfidenceLevel.HIGH
    if score >= 0.6:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def factuality_gate(
    page: TopicPageData, evidence_graph: EvidenceGraph, _today: date | None = None
) -> QAGateResult:
    failure_items: list[str] = []
    repair_actions: list[QARepairAction] = []
    remediation: list[str] = []

    contradiction_deduction = 0.0
    claim_id_deduction = 0.0
    weak_source_deduction = 0.0
    unsupported_deduction = 0.0

    source_ids = {s.source_id for s in evidence_graph.sources}

    for error in evidence_graph.validate_claim_sources():
        failure_items.append(error)
        repair_actions.append(QARepairAction.WEAK_SOURCE)
        remediation.append("Fix claim source references so every claim points to an actual source.")
        weak_source_deduction = min(weak_source_deduction + 0.15, 0.3)

    for contradiction in evidence_graph.contradictions:
        # Skip contradictions the AI reviewer classified as scope/noise/debug.
        ai_res = getattr(contradiction, "ai_resolution", None)
        if ai_res and str(ai_res.value) not in ("real_uncertainty",):
            continue
        failure_items.append(
            f"Contradiction on {contradiction.topic}: {contradiction.claim_a} vs {contradiction.claim_b}"
        )
        repair_actions.append(QARepairAction.CONFLICTING_CLAIM)
        remediation.append("Add an uncertainty box or remove the conflicting claim from sections.")
        contradiction_deduction = min(contradiction_deduction + 0.25, 0.4)

    for s_idx, section in enumerate(_as_list(page.sections)):
        s_type = _normalize_component_type(_get(section, "component_type"))
        for i_idx, item in enumerate(_as_list(_get(section, "items", []))):
            claim_id = _item_claim_id(item)
            item_text = _text_from_item(item)
            if claim_id:
                claim = _find_claim(evidence_graph, claim_id)
                if claim is None:
                    failure_items.append(
                        f"Section {s_idx} item {i_idx}: claim_id {claim_id} missing from EvidenceGraph"
                    )
                    repair_actions.append(QARepairAction.MISSING_CLAIM_ID)
                    remediation.append(f"Attach a real claim_id to '{item_text}' or remove it.")
                    claim_id_deduction = min(claim_id_deduction + 0.25, 0.4)
                    continue

                ct_value = getattr(getattr(claim, "claim_type", None), "value", claim.claim_type)
                if ct_value == "metric":
                    attrs = getattr(claim, "claim_attributes", {}) or {}
                    snippet = str(
                        attrs.get("evidence_snippet", "") or
                        getattr(claim, "evidence_snippet", "") or ""
                    ).strip()
                    claim_sources = list(getattr(claim, "source_ids", []))
                    if not claim_sources or not snippet:
                        failure_items.append(
                            f"Section {s_idx} item {i_idx}: metric claim {claim_id} lacks source_ids or evidence_snippet"
                        )
                        repair_actions.append(QARepairAction.UNSUPPORTED_NUMERIC_CLAIM)
                        remediation.append("Restore metric claim support.")
                        unsupported_deduction = min(unsupported_deduction + 0.2, 0.4)
                    if any(sid not in source_ids for sid in claim_sources):
                        failure_items.append(
                            f"Section {s_idx} item {i_idx}: metric claim {claim_id} references missing source"
                        )
                        repair_actions.append(QARepairAction.WEAK_SOURCE)
                        remediation.append("Point the metric claim at an existing source.")
                        weak_source_deduction = min(weak_source_deduction + 0.1, 0.3)

                # Improvement 2: cross-reference item value numbers against claim text / evidence
                item_val = str(_get(item, "value", "") or "")
                item_nums = _extract_numeric_values(item_val)
                if item_nums:
                    claim_text = (getattr(claim, "text", "") or "") + " " + (getattr(claim, "evidence_sentence", "") or "")
                    claim_nums = _extract_numeric_values(claim_text)
                    stray_nums = item_nums - claim_nums
                    if stray_nums:
                        failure_items.append(
                            f"Section {s_idx} item {i_idx}: value '{item_val}' has numbers "
                            f"{', '.join(sorted(stray_nums)[:5])} not found in claim {claim.claim_id} text or evidence"
                        )
                        repair_actions.append(QARepairAction.UNSUPPORTED_NUMERIC_CLAIM)
                        remediation.append("Ensure item values match claim text or evidence sentence.")
                        unsupported_deduction = min(unsupported_deduction + 0.2, 0.4)

                if _is_numeric_like(item_text) and ct_value not in {"metric", "date", "schedule", "status", "entity", "location", "action"}:
                    failure_items.append(
                        f"Section {s_idx} item {i_idx}: numeric fact '{item_text}' is not backed by a numeric claim"
                    )
                    repair_actions.append(QARepairAction.UNSUPPORTED_NUMERIC_CLAIM)
                    remediation.append("Replace with a supported claim.")
                    unsupported_deduction = min(unsupported_deduction + 0.2, 0.4)

            elif _needs_traceability(s_type, item):
                penalty = 0.2 if _is_numeric_like(item_text) else 0.15
                failure_items.append(
                    f"Section {s_idx} item {i_idx}: {'numeric' if _is_numeric_like(item_text) else 'traceable'} fact '{item_text}' has no claim_id"
                )
                repair_actions.append(QARepairAction.MISSING_CLAIM_ID)
                remediation.append("Add a claim_id from the claim cards.")
                claim_id_deduction = min(claim_id_deduction + penalty, 0.4)

    # Improvement 3: scan ALL items for numbers not appearing in ANY claim
    all_claim_nums: set[str] = set()
    for claim in evidence_graph.claims:
        all_claim_nums |= _extract_numeric_values(
            (getattr(claim, "text", "") or "") + " " + (getattr(claim, "evidence_sentence", "") or "")
        )
    for s_idx, section in enumerate(_as_list(page.sections)):
        for i_idx, item in enumerate(_as_list(_get(section, "items", []))):
            item_val = str(_get(item, "value", "") or "")
            item_nums = _extract_numeric_values(item_val)
            if not item_nums:
                continue
            unmatched = item_nums - all_claim_nums
            if unmatched:
                failure_items.append(
                    f"Section {s_idx} item {i_idx}: numeric value(s) "
                    f"{', '.join(sorted(unmatched)[:5])} "
                    f"in '{item_val}' not found in ANY claim in evidence graph"
                )
                repair_actions.append(QARepairAction.UNSUPPORTED_NUMERIC_CLAIM)
                remediation.append("Remove unsupported numbers or add matching claims to evidence graph.")
                unsupported_deduction = min(unsupported_deduction + 0.2, 0.4)

    score = 1.0 - contradiction_deduction - claim_id_deduction - weak_source_deduction - unsupported_deduction
    score = max(0.25, min(1.0, score))

    return QAGateResult(
        gate_name="factuality",
        status="fail" if failure_items else "pass",
        failed_items=failure_items[:20],
        repair_actions=_dedupe(repair_actions)[:20],
        confidence_score=score,
        remediation_suggestions=remediation[:10],
    )


def _freshness_threshold_days(event_status: EventStatus) -> int:
    if event_status == EventStatus.LIVE:
        return 3
    if event_status in {EventStatus.UPCOMING, EventStatus.SCHEDULED}:
        return 14
    if event_status == EventStatus.DEVELOPING:
        return 7
    return 90


def freshness_gate(
    page: TopicPageData, evidence_graph: EvidenceGraph, today: date | None = None
) -> QAGateResult:
    current_date = today or date.today()
    current_dt = datetime.combine(current_date, datetime.min.time(), tzinfo=timezone.utc)
    threshold = _freshness_threshold_days(page.status)
    strict = page.status in STRICT_STATUSES

    failure_items: list[str] = []
    repair_actions: list[QARepairAction] = []
    remediation: list[str] = []
    score = 1.0

    if evidence_graph.last_updated is None:
        score -= 0.15 if strict else 0.05
        remediation.append("Populate evidence_graph.last_updated for clearer freshness tracking.")
        if strict:
            failure_items.append("Time-sensitive event is missing evidence_graph.last_updated")
            repair_actions.append(QARepairAction.STALE_SOURCE)

    weak: list[str] = []
    stale: list[str] = []
    for source in evidence_graph.sources:
        if source.authority_score < 0.7 or source.source_type.value in {"social", "aggregator", "unknown"}:
            weak.append(source.source_id)
        if source.published_at is not None:
            pub = source.published_at
            pub = pub.replace(tzinfo=timezone.utc) if pub.tzinfo is None else pub.astimezone(timezone.utc)
            if (current_dt - pub).days > threshold:
                stale.append(source.source_id)
        else:
            score -= 0.03

    if weak:
        score -= min(0.2, 0.05 * len(weak))
        repair_actions.append(QARepairAction.WEAK_SOURCE)
        remediation.append("Prefer stronger sources or annotate the limitation of weaker ones.")

    if stale:
        score -= min(0.35, 0.08 * len(stale))
        repair_actions.append(QARepairAction.STALE_SOURCE)
        remediation.append("Replace stale sources with fresher coverage or lower the specificity of the page.")
        if strict:
            failure_items.append(
                f"Freshness threshold exceeded for sources: {', '.join(stale[:5])}"
            )

    return QAGateResult(
        gate_name="freshness",
        status="fail" if failure_items else "pass",
        failed_items=failure_items[:20],
        repair_actions=_dedupe(repair_actions)[:20],
        confidence_score=max(0.0, min(1.0, score)),
        remediation_suggestions=remediation[:10],
    )


def event_fit_gate(
    page: TopicPageData, _evidence_graph: EvidenceGraph, ia: EvidenceAwareIA
) -> QAGateResult:
    requirement = EVENT_TYPE_REQUIREMENTS[ia.final_event_type]
    required = list(requirement.required_components)
    sections = _as_list(page.sections)
    present: dict[ComponentType, list[Any]] = {}

    failure_items: list[str] = []
    repair_actions: list[QARepairAction] = []
    remediation: list[str] = []
    score = 1.0

    for s_idx, section in enumerate(sections):
        ct = _normalize_component_type(_get(section, "component_type"))
        if ct is None:
            failure_items.append(
                f"Section {s_idx} has undefined component type {_get(section, 'component_type')!r}"
            )
            repair_actions.append(QARepairAction.UNDEFINED_COMPONENT)
            remediation.append("Use a registry-backed component type only.")
            score -= 0.15
            continue
        present.setdefault(ct, []).append(section)
        if not _as_list(_get(section, "items", [])):
            failure_items.append(f"Section {s_idx} ({ct.value}) is empty")
            repair_actions.append(QARepairAction.MISSING_REQUIRED_COMPONENT)
            remediation.append("Populate each required component with concrete items.")
            score -= 0.15

    for req_component in required:
        if not present.get(req_component):
            failure_items.append(f"Required component missing: {req_component.value}")
            repair_actions.append(QARepairAction.MISSING_REQUIRED_COMPONENT)
            remediation.append(
                f"Add a non-empty {req_component.value} section for the "
                f"{ia.final_event_type.value} page."
            )
            score -= 0.25

    return QAGateResult(
        gate_name="event_fit",
        status="fail" if failure_items else "pass",
        failed_items=failure_items[:20],
        repair_actions=_dedupe(repair_actions)[:20],
        confidence_score=max(0.0, min(1.0, score)),
        remediation_suggestions=remediation[:10],
    )


class QARunner:
    def __init__(self, today: date | None = None):
        self.today = today

    def run(
        self,
        page: TopicPageData,
        evidence_graph: EvidenceGraph,
        ia: EvidenceAwareIA,
        today: date | None = None,
    ) -> dict[str, Any]:
        current_date = today or self.today or date.today()
        gates = [
            factuality_gate(page, evidence_graph, current_date),
            freshness_gate(page, evidence_graph, current_date),
            event_fit_gate(page, evidence_graph, ia),
        ]
        score = round(sum(g.confidence_score for g in gates) / max(1, len(gates)), 3)
        return {
            "gate_results": gates,
            "passed": all(g.status == "pass" for g in gates),
            "confidence_score": score,
            "confidence_level": confidence_level_from_score(score),
            "repair_actions": _dedupe([a for g in gates for a in g.repair_actions]),
            "failed_gates": [g.gate_name for g in gates if g.status == "fail"],
        }
