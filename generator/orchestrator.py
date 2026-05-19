"""Editorial orchestrator — evidence-quality feedback loop with deterministic repair.

Architecture (updated):
  Input → classify → research → Evidence Gate → plan → compose → QA + repair → Page Gate → render

Key change from the old pipeline: QA failures are repaired deterministically
(not via LLM re-composition), and the Page Gate reviews structured data
(not raw HTML). Each phase runs once; there are no revision loops.

Usage:
    run = EditorialRun(sentence="The 2026 FIFA World Cup kicks off...")
    run.execute()
    run.save_artifacts("runs/")
    print(run.html)  # final rendered page
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from generator.classify import Stage1A
from generator.compose import synthesize_topic_page
from generator.critic import run_evidence_gate, run_page_gate
from generator.plan import Stage1B
from generator.quality import QARunner, confidence_level_from_score
from generator.render import render_topic_page
from generator.repair import repair_page
from generator.research import run_research
from generator.verify_facts import verify_page_fidelity
from generator.schemas import (
    EvidenceAwareIA, EvidenceGraph, EventContext,
    EventHypothesis, EventStatus, RenderMode, TopicPageData,
)

LOGGER = logging.getLogger("editorial_orchestrator")


class CriticDecision(str, Enum):
    PUBLISHABLE = "publishable"
    EDITOR_REVIEW = "editor_review"
    EVIDENCE_LIMITED = "evidence_limited"
    NOT_ACCEPTABLE = "not_acceptable"
    RE_SEARCH = "re_search"  # triggers targeted re-search, then re-evaluate


class RunStatus(str, Enum):
    GATHERING = "gathering"
    ENRICHING = "enriching"
    BUILDING = "building"
    GATING = "gating"
    COMPLETE = "complete"
    DRAFT = "draft"
    ERROR = "error"


@dataclass
class CriticVerdict:
    decision: CriticDecision
    reasoning: str = ""
    new_queries: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)


@dataclass
class EditorialRun:
    """Stateful editorial workflow with deterministic repair.

    No revision loops. Each phase runs once. QA failures are repaired
    by stripping problematic content, not by asking the LLM to try again.
    """

    sentence: str
    today: date = field(default_factory=date.today)
    status: RunStatus = RunStatus.GATHERING

    # Phase outputs
    hypothesis: EventHypothesis | None = None
    evidence_graph: EvidenceGraph | None = None
    critic_verdict: CriticVerdict | None = None
    ia: EvidenceAwareIA | None = None
    topic_page: TopicPageData | None = None
    qa_report: dict[str, Any] = field(default_factory=dict)
    repair_summary: dict[str, int] = field(default_factory=dict)
    fidelity_report: dict[str, Any] = field(default_factory=dict)
    html: str = ""
    page_critic_verdict: dict[str, str] = field(default_factory=dict)

    # State tracking
    search_round: int = 0
    caveats: list[str] = field(default_factory=list)
    max_search_rounds: int = 3

    def execute(self, run_ai: bool = True) -> None:
        """Run the full editorial workflow."""
        try:
            self._phase_understand()
            self._phase_research(run_ai=run_ai)
            self._phase_plan(run_ai=run_ai)
            self._phase_compose(run_ai=run_ai)
            self._phase_review()
            self._phase_render(run_ai=run_ai)
            self.status = RunStatus.COMPLETE
        except Exception as exc:
            LOGGER.exception("Editorial run failed: %s", exc)
            self.status = RunStatus.ERROR

    def _phase_understand(self) -> None:
        stage1a = Stage1A()
        self.hypothesis = stage1a.run(self.sentence, self.today)
        LOGGER.info("Phase 1: hypothesis — %s", self.hypothesis.preliminary_event_type.value)

    def _phase_research(self, run_ai: bool = True) -> None:
        while self.search_round < self.max_search_rounds:
            context = EventContext(
                event_type=self.hypothesis.preliminary_event_type,
                status=EventStatus.DEVELOPING,
                confidence="medium",
                primary_entity=self.sentence[:160],
                event_sentence=self.sentence,
                search_queries=self.hypothesis.search_intents,
            )
            self.evidence_graph = run_research(context, run_ai=run_ai)
            LOGGER.info(
                "Phase 2 (round %d): %d sources, %d claims",
                self.search_round + 1,
                len(self.evidence_graph.sources),
                len(self.evidence_graph.claims),
            )

            # Product Critic: is this evidence sufficient?
            result = run_evidence_gate(
                self.evidence_graph,
                self.hypothesis.preliminary_event_type.value,
                self.sentence,
                self.today,
                run_ai=run_ai,
            )
            self.critic_verdict = CriticVerdict(
                decision=CriticDecision(result.get("decision", "publishable")),
                reasoning=result.get("reasoning", ""),
                new_queries=list(result.get("new_queries", [])),
                caveats=list(result.get("caveats", [])),
            )
            LOGGER.info(
                "Product Critic: %s — %s",
                self.critic_verdict.decision.value,
                self.critic_verdict.reasoning[:120],
            )

            if self.critic_verdict.decision == CriticDecision.PUBLISHABLE:
                break
            elif self.critic_verdict.decision == CriticDecision.EDITOR_REVIEW:
                self.caveats.extend(self.critic_verdict.caveats)
                break
            elif self.critic_verdict.decision == CriticDecision.EVIDENCE_LIMITED:
                self.caveats.extend(self.critic_verdict.caveats)
                self.caveats.append("Evidence is limited — page will carry a quality caveat.")
                break
            elif self.critic_verdict.decision == CriticDecision.RE_SEARCH:
                new_queries = self.critic_verdict.new_queries
                if not new_queries:
                    break
                self.hypothesis.search_intents = new_queries[:6]
                self.search_round += 1
                LOGGER.info("Re-searching with targeted queries: %s", new_queries)
                continue
            elif self.critic_verdict.decision == CriticDecision.NOT_ACCEPTABLE:
                self.status = RunStatus.DRAFT
                self.caveats = [f"Evidence not acceptable: {self.critic_verdict.reasoning}"]
                return
        else:
            # Max search rounds exhausted.
            self.caveats.append("Evidence may be thin after multiple search rounds.")

    def _phase_plan(self, run_ai: bool = True) -> None:
        self.status = RunStatus.BUILDING
        stage1b = Stage1B()
        self.ia = stage1b.run(self.hypothesis, self.evidence_graph, self.today)
        LOGGER.info("Phase 3: IA plan — %s / %s", self.ia.final_event_type.value, self.ia.event_status.value)

    def _phase_compose(self, run_ai: bool = True) -> None:
        public_graph = self.evidence_graph.public_evidence_view
        # Use degraded mode when evidence is limited
        page_mode = "full"
        if self.critic_verdict and self.critic_verdict.decision in (
            CriticDecision.EVIDENCE_LIMITED, CriticDecision.NOT_ACCEPTABLE,
        ):
            page_mode = "degraded"
            LOGGER.info("Phase 4: using degraded page mode (verdict: %s)", self.critic_verdict.decision.value)
        self.topic_page = synthesize_topic_page(public_graph, self.ia, self.today, page_mode=page_mode)
        self.topic_page.evidence_graph_ref = self.evidence_graph
        LOGGER.info("Phase 4: composed — %d sections", len(self.topic_page.sections))

    def _phase_review(self) -> None:
        """Run QA gates, apply deterministic repairs, verify.

        This replaces the old revision loop. Instead of asking the LLM to
        re-compose the page with repair hints, we directly strip problematic
        content from the page data. No LLM call, no loop.
        """
        self.status = RunStatus.GATING
        qa_runner = QARunner(self.today)

        # First QA pass
        result = qa_runner.run(self.topic_page, self.evidence_graph, self.ia, self.today)
        LOGGER.info(
            "Phase 5: QA initial — %s (%.2f) gates=%s",
            "PASS" if result["passed"] else "FAIL",
            result["confidence_score"],
            result["failed_gates"],
        )

        # Apply deterministic repairs
        self.topic_page, self.repair_summary = repair_page(
            self.topic_page,
            self.evidence_graph,
            qa_score=result["confidence_score"],
            required_components=self.ia.required_components,
        )

        # Verify after repair
        result = qa_runner.run(self.topic_page, self.evidence_graph, self.ia, self.today)
        self.topic_page.qa_results = result["gate_results"]

        qa_conf = confidence_level_from_score(result["confidence_score"])
        self.qa_report = {
            "passed": result["passed"],
            "confidence_score": result["confidence_score"],
            "confidence_level": qa_conf.value,
            "failed_gates": result["failed_gates"],
            "repair_actions": [a.value for a in result["repair_actions"]],
            "items_repaired": self.repair_summary.get("items_removed", 0),
        }
        LOGGER.info(
            "Phase 5: QA final — %s (%.2f) gates=%s repaired=%d",
            "PASS" if result["passed"] else "FAIL",
            result["confidence_score"],
            result["failed_gates"],
            self.repair_summary.get("items_removed", 0),
        )

        # Fidelity check: cross-reference page values against claim texts.
        self.topic_page, self.fidelity_report = verify_page_fidelity(
            self.topic_page, self.evidence_graph,
        )
        LOGGER.info(
            "Phase 5: Fidelity — %d/%d items pass (%.2f)",
            self.fidelity_report.get("total_checked", 0) - self.fidelity_report.get("total_failed", 0),
            self.fidelity_report.get("total_checked", 1),
            self.fidelity_report.get("fidelity_score", 1.0),
        )

    def _phase_render(self, run_ai: bool = True) -> None:
        self.html = render_topic_page(self.topic_page, mode=RenderMode.PUBLIC)
        LOGGER.info("Phase 6: rendered — %d bytes", len(self.html))

        # Page Gate: final acceptance review on structured data (not HTML).
        self.page_critic_verdict = run_page_gate(
            self.topic_page,
            self.evidence_graph,
            self.qa_report,
            run_ai=run_ai,
        )
        decision = self.page_critic_verdict.get("decision", "?")
        LOGGER.info(
            "Page Gate: %s — %s",
            decision,
            self.page_critic_verdict.get("reasoning", "")[:120],
        )

        # Enforce Page Gate verdict.
        if decision == "not_acceptable":
            LOGGER.warning(
                "Page Gate rejected page: %s",
                self.page_critic_verdict.get("reasoning", ""),
            )
            if self.status != RunStatus.ERROR:
                self.status = RunStatus.DRAFT
            self.caveats.append(
                f"Page Gate: not_acceptable — {self.page_critic_verdict.get('reasoning', '')[:200]}"
            )
        elif decision == "editor_review":
            self.caveats.append("Page Gate: editor_review — page needs human review before publish.")

    def save_artifacts(self, base_dir: str | Path = "runs") -> Path:
        """Persist all intermediate artifacts to a timestamped directory."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_dir = Path(base_dir) / ts
        run_dir.mkdir(parents=True, exist_ok=True)

        def _write(name: str, obj: Any) -> None:
            path = run_dir / name
            if hasattr(obj, "model_dump"):
                path.write_text(json.dumps(obj.model_dump(mode="json"), indent=2, ensure_ascii=False, default=str))
            elif isinstance(obj, (dict, list)):
                path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
            else:
                path.write_text(str(obj))

        if self.hypothesis:
            _write("hypothesis.json", self.hypothesis)
        if self.evidence_graph:
            _write("evidence_graph.json", self.evidence_graph)
        if self.critic_verdict:
            _write("product_critic.json", {
                "decision": self.critic_verdict.decision.value,
                "reasoning": self.critic_verdict.reasoning,
                "new_queries": self.critic_verdict.new_queries,
                "caveats": self.critic_verdict.caveats,
            })
        if self.ia:
            _write("ia_plan.json", self.ia)
        if self.topic_page:
            page_data = self.topic_page.model_dump(mode="json", exclude={"evidence_graph_ref"})
            _write("topic_page.json", page_data)
        if self.qa_report:
            _write("qa_report.json", self.qa_report)
        if self.repair_summary:
            _write("repair_summary.json", self.repair_summary)
        if self.fidelity_report:
            _write("fidelity_report.json", self.fidelity_report)
        if self.html:
            (run_dir / "page.html").write_text(self.html)

        # Top-level summary
        summary = {
            "sentence": self.sentence,
            "status": self.status.value,
            "confidence": self.topic_page.confidence.value if self.topic_page else "unknown",
            "search_rounds": self.search_round + 1,
            "qa_passed": self.qa_report.get("passed", False),
            "qa_score": self.qa_report.get("confidence_score", 0),
        }
        _write("summary.json", summary)

        # Save page critic verdict
        if hasattr(self, "page_critic_verdict") and self.page_critic_verdict:
            _write("page_critic.json", self.page_critic_verdict)

        LOGGER.info("Artifacts saved to %s", run_dir)
        return run_dir


# ---------------------------------------------------------------------------
# Convenience entry point — drop-in replacement for the old pipeline.run_pipeline
# ---------------------------------------------------------------------------

def run_pipeline(sentence: str, today: date | None = None) -> TopicPageData:
    """Run the full editorial workflow and return a TopicPageData.

    This is the primary entry point. It uses the new orchestrator with
    deterministic repair, Evidence Gate, Page Gate on structured data,
    and fidelity checking. No LLM revision loops.
    """
    run = EditorialRun(sentence=sentence, today=today or date.today())
    run.execute()
    return run.topic_page
