"""Run the full editorial workflow for one sentence.

Usage:
    python scripts/run_editorial.py "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026."
    python scripts/run_editorial.py "Eurovision 2026 is being held in Vienna from May 12 to May 16." --output output/
    python scripts/run_editorial.py "..." --debug  # render in debug mode

This replaces the old `refresh_fixture.py` as the canonical entry point.
Artifacts are saved to runs/<timestamp>/ and the final HTML to output/.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from datetime import date
from generator.orchestrator import EditorialRun
from generator.render import render_topic_page
from generator.schemas import RenderMode


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")[:80] or "topic-page"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the editorial workflow for one sentence.")
    parser.add_argument("sentence", help="One-sentence event description")
    parser.add_argument("--output-dir", default=str(ROOT / "output"), help="HTML output directory")
    parser.add_argument("--runs-dir", default=str(ROOT / "runs"), help="Artifact directory")
    parser.add_argument("--debug", action="store_true", help="Render with debug trace")
    parser.add_argument("--today", default=None, help="Override today's date (YYYY-MM-DD)")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()

    run = EditorialRun(sentence=args.sentence, today=today)
    run.execute(run_ai=True)

    if run.status.value == "error":
        print(f"ERROR — pipeline failed: {run.caveats}")
        run_dir = run.save_artifacts(args.runs_dir)
        print(f"Artifacts saved for debugging: {run_dir}")
        sys.exit(1)
    elif run.status.value == "draft":
        print("DRAFT ONLY — evidence insufficient for public page.")
        if run.caveats:
            for c in run.caveats:
                print(f"  - {c}")
    elif run.topic_page:
        # Render in the requested mode
        mode = RenderMode.DEBUG if args.debug else RenderMode.PUBLIC
        html = render_topic_page(run.topic_page, mode=mode)

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = ".debug.html" if args.debug else ".html"
        output_path = output_dir / f"{slugify(args.sentence)}{suffix}"
        output_path.write_text(html, encoding="utf-8")
        print(output_path)

    run_dir = run.save_artifacts(args.runs_dir)
    print(f"Artifacts: {run_dir}")
    print(f"Status: {run.status.value}")
    if run.topic_page:
        print(f"Confidence: {run.topic_page.confidence.value}")
        print(f"QA passed: {run.qa_report.get('passed', False)} (score {run.qa_report.get('confidence_score', 0):.2f})")
        print(f"Sources: {len(run.evidence_graph.sources)} | Claims: {len(run.evidence_graph.claims)}")
    if run.critic_verdict:
        print(f"Critic: {run.critic_verdict.decision.value} — {run.critic_verdict.reasoning[:120]}")


if __name__ == "__main__":
    main()
