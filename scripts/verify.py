from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator.pipeline import run_pipeline
from generator.renderer import render_topic_page
from generator.schemas import EventContext, RawResearch, TopicPageData


def verify_fixture(fixture_path: Path) -> None:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    sentence = payload["input_sentence"]
    fixture_today = date.fromisoformat(payload["today"])
    fixture_context = EventContext.model_validate(payload["event_context"])
    fixture_research = RawResearch.model_validate(payload["raw_research"])
    fixture_page = TopicPageData.model_validate(payload["topic_page"])

    def stage1(_: str, __: date | None = None) -> EventContext:
        return fixture_context

    def stage2(_: EventContext) -> RawResearch:
        return fixture_research

    def stage3(
        _: EventContext,
        __: RawResearch,
        ___: date | None = None,
    ) -> TopicPageData:
        return fixture_page

    result = run_pipeline(
        sentence=sentence,
        today=fixture_today,
        stage1_func=stage1,
        stage2_func=stage2,
        stage3_func=stage3,
    )
    html = render_topic_page(result)
    if "<html" not in html.lower():
        raise AssertionError(f"Fixture {fixture_path.name} did not render valid HTML")


def main() -> None:
    fixture_dir = ROOT / "tests" / "fixtures"
    fixture_files = sorted(fixture_dir.glob("*.json"))
    if not fixture_files:
        raise RuntimeError("No fixtures found under tests/fixtures")

    for fixture_path in fixture_files:
        verify_fixture(fixture_path)
        print(f"OK: {fixture_path.name}")
    print(f"Verification passed for {len(fixture_files)} fixture(s).")


if __name__ == "__main__":
    main()
