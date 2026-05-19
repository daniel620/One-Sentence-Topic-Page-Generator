"""Run the live pipeline for one sentence and save the result as a fixture.

This is the script we use to refresh `tests/fixtures/*.json` from real
Tavily + Anthropic runs. It saves both the rendered `topic_page` and the
backing `evidence_graph` so a reviewer can rebuild the HTML without
re-paying for the LLM/search calls.

Usage:
    python scripts/refresh_fixture.py \
        --sentence "Eurovision 2026 ..." \
        --fixture tests/fixtures/live_event_eurovision.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator.orchestrator import run_pipeline


def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Refresh a fixture from a live pipeline run.")
    parser.add_argument("--sentence", required=True)
    parser.add_argument("--fixture", required=True, help="Path to fixture JSON to write.")
    parser.add_argument("--today", default=None, help="Override today's date (ISO).")
    args = parser.parse_args()

    today = date.fromisoformat(args.today) if args.today else date.today()
    page = run_pipeline(args.sentence, today=today)

    fixture_path = Path(args.fixture)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)

    page_json = page.model_dump(mode="json", exclude={"evidence_graph_ref"})
    graph_json = page.evidence_graph_ref.model_dump(mode="json") if page.evidence_graph_ref else None

    payload = {
        "input_sentence": args.sentence,
        "today": today.isoformat(),
        "evidence_graph": graph_json,
        "topic_page": page_json,
    }
    fixture_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    print(f"Wrote {fixture_path}")


if __name__ == "__main__":
    main()
