"""Pipeline orchestrator.

End-to-end:
    sentence
       ├─► Stage 1A:  hypothesize event type + search intents       (LLM)
       ├─► Stage 2:   Tavily search → claim extraction              (deterministic)
       │              returns an EvidenceGraph
       ├─► Stage 1B:  evidence-aware IA / layout plan               (LLM)
       ├─► Stage 3:   structured TopicPageData                      (LLM)
       └─► QA loop:   factuality + freshness + event_fit             (deterministic)
                     bounded resynthesis (max_qa_iterations)
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Callable

from pydantic import BaseModel

from generator.qa_gates import QARunner, confidence_level_from_score
from generator.schemas import (
    EvidenceAwareIA,
    EvidenceGraph,
    EventContext,
    EventHypothesis,
    EventStatus,
    QARepairAction,
    QAGateResult,
    TopicPageData,
)
from generator.stage1_understand import Stage1A, Stage1B
from generator.stage2_research import run_research
from generator.stage3_synthesize import synthesize_topic_page

LOGGER = logging.getLogger("topic_pipeline")

Stage2Fn = Callable[[EventContext], EvidenceGraph]
Stage3Fn = Callable[..., TopicPageData]
QARunnerFn = Callable[[TopicPageData, EvidenceGraph, EvidenceAwareIA, date | None], dict[str, Any]]


def _to_serializable(payload: Any) -> Any:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json")
    return payload


def log_stage(stage_name: str, payload: Any) -> None:
    LOGGER.info(
        "%s output:\n%s",
        stage_name,
        json.dumps(_to_serializable(payload), ensure_ascii=False, indent=2, default=str),
    )


def _normalize_qa(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        summary = dict(result)
    elif isinstance(result, BaseModel):
        summary = result.model_dump(mode="json")
    else:
        summary = {
            "gate_results": getattr(result, "gate_results", []),
            "passed": getattr(result, "passed", False),
            "confidence_score": getattr(result, "confidence_score", 0.0),
            "repair_actions": getattr(result, "repair_actions", []),
            "failed_gates": getattr(result, "failed_gates", []),
        }

    normalized_gates: list[QAGateResult] = []
    for gr in summary.get("gate_results", []):
        if isinstance(gr, QAGateResult):
            normalized_gates.append(gr)
        elif isinstance(gr, BaseModel):
            normalized_gates.append(QAGateResult.model_validate(gr.model_dump(mode="json")))
        else:
            normalized_gates.append(QAGateResult.model_validate(gr))
    summary["gate_results"] = normalized_gates

    normalized_actions: list[QARepairAction] = []
    for action in summary.get("repair_actions", []):
        normalized_actions.append(
            action if isinstance(action, QARepairAction) else QARepairAction(action)
        )
    summary["repair_actions"] = normalized_actions
    return summary


def _apply_qa_metadata(page: TopicPageData, qa_summary: dict[str, Any]) -> None:
    page.qa_results = qa_summary.get("gate_results", [])
    qa_conf = confidence_level_from_score(float(qa_summary.get("confidence_score", 0.0)))
    rank = {"low": 0, "medium": 1, "high": 2}
    page.confidence = min(page.confidence, qa_conf, key=lambda lvl: rank[lvl.value])


def _call_stage3(
    stage3_func: Stage3Fn,
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    current_date: date,
    repair_actions: list[QARepairAction] | None = None,
    failed_items: list[str] | None = None,
) -> TopicPageData:
    import inspect

    try:
        sig = inspect.signature(stage3_func)
        accepts = "repair_actions" in sig.parameters or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        accepts = False

    if repair_actions and accepts:
        return stage3_func(
            evidence_graph,
            ia,
            current_date,
            repair_actions=repair_actions,
            failed_items=failed_items,
        )
    return stage3_func(evidence_graph, ia, current_date)


def _call_qa(
    qa_runner: Any,
    page: TopicPageData,
    evidence_graph: EvidenceGraph,
    ia: EvidenceAwareIA,
    current_date: date,
) -> dict[str, Any]:
    if hasattr(qa_runner, "run"):
        return _normalize_qa(qa_runner.run(page, evidence_graph, ia, current_date))
    return _normalize_qa(qa_runner(page, evidence_graph, ia, current_date))


def run_pipeline(
    sentence: str,
    today: date | None = None,
    stage1a: Any | None = None,
    stage1b: Any | None = None,
    stage2_func: Stage2Fn | None = None,
    stage3_func: Stage3Fn = synthesize_topic_page,
    qa_runner: Any | None = None,
    max_qa_iterations: int = 2,
) -> TopicPageData:
    """Run the full generator pipeline against live APIs (default) or stubs.

    Stubs are useful for tests / fixtures: pass in your own callables and
    they replace the corresponding stage. `stage2_func` should return an
    EvidenceGraph directly (Stage 2 is deterministic).
    """
    current_date = today or date.today()
    stage1a = stage1a or Stage1A()
    stage1b = stage1b or Stage1B()
    stage2 = stage2_func or run_research

    hypothesis: EventHypothesis = stage1a.run(sentence, current_date)
    log_stage("stage1a_hypothesis", hypothesis)

    event_context = EventContext(
        event_type=hypothesis.preliminary_event_type,
        status=EventStatus.DEVELOPING,
        confidence="medium",
        primary_entity=sentence[:160],
        event_sentence=sentence,
        search_queries=hypothesis.search_intents,
    )

    evidence_graph = stage2(event_context)
    log_stage("stage2_research", evidence_graph)

    ia = stage1b.run(hypothesis, evidence_graph, current_date)
    log_stage("stage1b_ia", ia)

    page = _call_stage3(stage3_func, evidence_graph, ia, current_date)
    log_stage("stage3_synthesize", page)

    active_qa = qa_runner or QARunner(current_date)
    attempts = 0

    while True:
        qa_summary = _call_qa(active_qa, page, evidence_graph, ia, current_date)
        _apply_qa_metadata(page, qa_summary)
        log_stage(
            f"qa_iteration_{attempts + 1}",
            {
                "passed": qa_summary.get("passed", False),
                "confidence_score": qa_summary.get("confidence_score", 0.0),
                "failed_gates": qa_summary.get("failed_gates", []),
                "repair_actions": [a.value for a in qa_summary.get("repair_actions", [])],
            },
        )

        if qa_summary.get("passed", False) or attempts >= max_qa_iterations:
            if not qa_summary.get("passed", False):
                page.confidence = confidence_level_from_score(
                    float(qa_summary.get("confidence_score", 0.0))
                )
            return page

        attempts += 1
        repair_actions = list(qa_summary.get("repair_actions", []))
        failed_items = [
            item
            for gate in qa_summary.get("gate_results", [])
            for item in getattr(gate, "failed_items", [])
        ]
        page = _call_stage3(
            stage3_func,
            evidence_graph,
            ia,
            current_date,
            repair_actions=repair_actions,
            failed_items=failed_items,
        )
        log_stage(f"stage3_revision_{attempts}", page)
