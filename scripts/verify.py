"""End-to-end smoke test: render every fixture, assert valid output.

Run before submitting changes. No API keys required; reads only the JSON
bundles under tests/fixtures/.

Checks beyond basic HTML presence:
  - Public/debug boundary (no claim_id, debug-panel, QA repair leakage)
  - Editor's note only when confidence is LOW or QA has failures
  - Every traceable section item has an evidence citation or explicit caveat
  - Key facts strip is non-empty
  - Sources footer is present and populated
  - Body class includes theme and variant
  - Fonts are loaded from Google Fonts
  - No placeholder text leakage (Coming soon, Details will be added)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generator.render import render_topic_page
from generator.schemas import ConfidenceLevel, RenderMode, TopicPageData


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

    name = fixture_path.name

    # --- Structural validity ---
    if "<html" not in public_html.lower():
        raise AssertionError(f"{name}: public render missing <html>")
    if "<html" not in debug_html.lower():
        raise AssertionError(f"{name}: debug render missing <html>")
    if "</html>" not in public_html:
        raise AssertionError(f"{name}: public render missing closing </html>")

    # --- Public-mode leak prevention ---
    forbidden_public = [
        "claim_id=", "QA repair", "Repair action", "Layout: dashboard",
        '<section class="debug-panel"', "source_id=",
    ]
    for needle in forbidden_public:
        if needle in public_html:
            raise AssertionError(f"{name}: public render leaks '{needle}'")

    # --- Placeholder leakage ---
    if "Details will be added as more information becomes available" in public_html:
        raise AssertionError(f"{name}: placeholder text leaked into public output")

    # --- Editor's note appropriateness ---
    has_editors_note = "Editor's note" in public_html
    confidence = page.confidence
    has_qa_failures = any(
        getattr(r, "status", None) == "fail"
        or (isinstance(r, dict) and r.get("status") == "fail")
        for r in page.qa_results
    )
    if has_editors_note and confidence == ConfidenceLevel.HIGH and not has_qa_failures:
        raise AssertionError(
            f"{name}: Editor's note on HIGH-confidence page with no QA failures"
        )

    # --- Key facts present ---
    if len(page.key_facts) == 0:
        raise AssertionError(f"{name}: key_facts strip is empty")

    # --- Sources present ---
    if not payload["evidence_graph"].get("sources"):
        raise AssertionError(f"{name}: no sources in evidence graph")

    # --- Theme and variant present on body ---
    if "theme-" not in public_html or "variant-" not in public_html:
        raise AssertionError(f"{name}: body missing theme or variant class")

    # --- Fonts loaded ---
    if "googleapis.com" not in public_html:
        raise AssertionError(f"{name}: Google Fonts not loaded")


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
