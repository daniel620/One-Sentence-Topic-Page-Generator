"""End-to-end smoke test: render every fixture, assert valid HTML.

Run before submitting changes. No API keys required; reads only the JSON
bundles under tests/fixtures/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator.renderer import render_topic_page
from generator.schemas import RenderMode, TopicPageData


def verify_fixture(fixture_path: Path) -> None:
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    page = TopicPageData.model_validate(
        {
            **payload["topic_page"],
            "evidence_graph_ref": payload["evidence_graph"],
        }
    )

    public_html = render_topic_page(page, mode=RenderMode.PUBLIC)
    debug_html = render_topic_page(page, mode=RenderMode.DEBUG)

    if "<html" not in public_html.lower():
        raise AssertionError(f"{fixture_path.name}: public render produced invalid HTML")
    if "<html" not in debug_html.lower():
        raise AssertionError(f"{fixture_path.name}: debug render produced invalid HTML")

    # Public mode must not leak internal trace strings.
    forbidden_public = ["claim_id=", "QA repair", "Repair action", "Layout: dashboard"]
    for needle in forbidden_public:
        if needle in public_html:
            raise AssertionError(
                f"{fixture_path.name}: public render leaks internal '{needle}'"
            )


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
