"""Generate one topic page HTML from one sentence.

Two paths:

  python scripts/generate.py --use-fixtures "<sentence>"
      Looks up a saved fixture and renders it. No API keys required.
      Use this for reviewers and CI smoke tests.

  python scripts/generate.py "<sentence>"
      Runs the live pipeline: Stage 1A (LLM) → Tavily search → Stage 1B (LLM)
      → Stage 3 (LLM) → QA → render. Needs ANTHROPIC_API_KEY and
      TAVILY_API_KEY in .env (gitignored).

The output HTML is self-contained and opens directly in a browser.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator.renderer import render_topic_page
from generator.schemas import RenderMode, TopicPageData


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")[:80] or "topic-page"


# When --use-fixtures is set, we match the input sentence to a known
# saved evidence + page bundle. Keep this list small and explicit; it's
# only for reviewer reproducibility.
FIXTURE_BY_KEYWORD: dict[str, str] = {
    "gpt-5.5": "tech_launch_gpt55.json",
    "chatgpt": "tech_launch_gpt55.json",
    "eurovision": "live_event_eurovision.json",
    "vienna": "live_event_eurovision.json",
    "world cup": "sports_tournament_worldcup.json",
    "estadio azteca": "sports_tournament_worldcup.json",
    "fifa": "sports_tournament_worldcup.json",
}


def fixture_path_from_sentence(sentence: str) -> Path:
    lowered = sentence.lower()
    fixture_dir = ROOT / "tests" / "fixtures"
    for keyword, filename in FIXTURE_BY_KEYWORD.items():
        if keyword in lowered:
            return fixture_dir / filename
    available = ", ".join(sorted(set(FIXTURE_BY_KEYWORD.values())))
    raise ValueError(
        "No fixture mapping found for that sentence. Try one matching one of: "
        f"{available}. To run the live pipeline, drop --use-fixtures and "
        "set ANTHROPIC_API_KEY + TAVILY_API_KEY in .env."
    )


def topic_page_from_fixture(fixture_path: Path) -> TopicPageData:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return TopicPageData.model_validate(
        {
            **payload["topic_page"],
            "evidence_graph_ref": payload["evidence_graph"],
        }
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
        help="Render from a saved fixture instead of running the live pipeline.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Render with debug trace UI (claim IDs, QA gate names, recipe).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "output"),
        help="Directory to write generated HTML files.",
    )
    args = parser.parse_args()

    if args.use_fixtures:
        page = topic_page_from_fixture(fixture_path_from_sentence(args.sentence))
    else:
        from generator.pipeline import run_pipeline  # imported lazily so --use-fixtures doesn't require API keys
        page = run_pipeline(args.sentence)

    mode = RenderMode.DEBUG if args.debug else RenderMode.PUBLIC
    html = render_topic_page(page, mode=mode)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".debug.html" if args.debug else ".html"
    output_path = output_dir / f"{slugify(args.sentence)}{suffix}"
    output_path.write_text(html, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
