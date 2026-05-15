from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator.pipeline import run_pipeline
from generator.renderer import render_topic_page
from generator.schemas import EventContext, RawResearch, TopicPageData


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")[:80] or "topic-page"


def fixture_path_from_sentence(sentence: str) -> Path:
    lowered = sentence.lower()
    fixture_dir = ROOT / "tests" / "fixtures"
    if "gpt-5.5" in lowered or "chatgpt" in lowered:
        return fixture_dir / "tech_launch_gpt55.json"
    if "eurovision" in lowered or "vienna" in lowered:
        return fixture_dir / "live_event_eurovision.json"
    if "world cup" in lowered or "estadio azteca" in lowered:
        return fixture_dir / "sports_tournament_worldcup.json"
    raise ValueError("No fixture mapping found for sentence. Use a known sample input.")


def run_with_fixture(sentence: str, fixture_path: Path) -> TopicPageData:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture_context = EventContext.model_validate(payload["event_context"])
    fixture_research = RawResearch.model_validate(payload["raw_research"])
    fixture_page = TopicPageData.model_validate(payload["topic_page"])
    fixture_today = date.fromisoformat(payload["today"])

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

    return run_pipeline(
        sentence=sentence,
        today=fixture_today,
        stage1_func=stage1,
        stage2_func=stage2,
        stage3_func=stage3,
    )


def main() -> None:
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Generate a hot-event topic page from one sentence."
    )
    parser.add_argument("sentence", help="One-sentence event description")
    parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Generate from local fixtures instead of live APIs.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "output"),
        help="Directory to write generated HTML files.",
    )
    args = parser.parse_args()

    if args.use_fixtures:
        fixture_path = fixture_path_from_sentence(args.sentence)
        topic_page = run_with_fixture(args.sentence, fixture_path)
    else:
        topic_page = run_pipeline(args.sentence)

    html = render_topic_page(topic_page)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slugify(args.sentence)}.html"
    output_path.write_text(html, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
