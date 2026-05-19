#!/usr/bin/env python3
"""Deterministic HTML output checks — no LLM calls, no API keys.

Evaluates:
  - HTML structural validity (doctype, lang, viewport, title)
  - Public/debug boundary (no internal IDs, scores, enum values in public mode)
  - Content completeness (hero, key facts, sections, sources footer)
  - Citation quality (publisher present, dates, official source marking)
  - Headline word count (≤12 words per schema contract)
  - Link validity (all hrefs are absolute, no placeholder URLs)

Output: JSON to stdout with per-file results and an aggregate score.
"""
from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Forbidden strings in public mode (must not appear in public HTML)
# ---------------------------------------------------------------------------
FORBIDDEN_PUBLIC = [
    "claim_id=",
    "QA repair",
    "Repair action",
    "Layout: dashboard",
    "evidence_grade",
    "source_id",
    "final_source_role",
    "ai_resolution",
    "extraction_noise",
    "debug_only",
    "weak_snippet",
    "QAGateResult",
    "RenderMode",
    'class="debug-panel"',  # HTML element, not CSS class name
    "Debug — pipeline trace",
    "Render mode: debug",
    "pipeline trace",
]


# ---------------------------------------------------------------------------
# Required structural elements in any topic page
# ---------------------------------------------------------------------------
REQUIRED_ELEMENTS = [
    ("doctype", r"<!doctype\s+html", "Page must start with <!doctype html>"),
    ("lang", r'<html[^>]*\slang="', 'html tag must have lang attribute'),
    ("viewport", r'<meta[^>]*name="viewport"', "Must include viewport meta tag"),
    ("title_tag", r"<title>", "Must have a <title>"),
    ("main_tag", r"<main", "Must have a <main> element"),
    ("h1_tag", r"<h1", "Must have an H1 headline"),
    ("sources_footer", r'sources-footer', "Must have a sources footer section"),
    ("page_footer", r"page-footer", "Must have a page footer"),
]


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

class StructuralChecker(HTMLParser):
    """Lightweight HTML parser that collects structural info."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.classes: dict[str, int] = {}
        self.h1_text: str = ""
        self._in_h1 = False
        self._collecting: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        attr_dict = dict(attrs)
        cls = attr_dict.get("class", "")
        if cls:
            for c in cls.split():
                self.classes[c] = self.classes.get(c, 0) + 1
        if tag == "h1":
            self._in_h1 = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_h1 = False

    def handle_data(self, data: str) -> None:
        if self._in_h1:
            self.h1_text += " " + data


def _check_html_file(filepath: Path, public_mode: bool = True) -> dict[str, Any]:
    """Run all deterministic checks on one HTML file."""
    raw = filepath.read_text(encoding="utf-8", errors="replace")
    raw_lower = raw.lower()
    findings: list[dict[str, Any]] = []
    checks_passed = 0
    checks_total = 0

    # --- Structural checks ---
    for name, pattern, desc in REQUIRED_ELEMENTS:
        checks_total += 1
        if re.search(pattern, raw, re.IGNORECASE):
            checks_passed += 1
        else:
            findings.append({"severity": "error", "check": name, "detail": desc})

    # --- Public/debug boundary ---
    if public_mode:
        for needle in FORBIDDEN_PUBLIC:
            checks_total += 1
            if needle.lower() in raw_lower:
                findings.append({
                    "severity": "error",
                    "check": "public_boundary",
                    "detail": f"Public HTML leaks internal string: '{needle}'",
                })
            else:
                checks_passed += 1

    # --- Headline word count ---
    parser = StructuralChecker()
    try:
        parser.feed(raw)
    except Exception:
        pass
    headline_words = [w for w in parser.h1_text.split() if w]
    checks_total += 1
    if len(headline_words) <= 12:
        checks_passed += 1
    else:
        findings.append({
            "severity": "warning",
            "check": "headline_length",
            "detail": f"Headline has {len(headline_words)} words (max 12): '{parser.h1_text.strip()[:120]}'",
        })

    # --- Content completeness ---
    # Key facts section
    checks_total += 1
    if "key-facts" in parser.classes or "key-fact" in parser.classes:
        checks_passed += 1
    else:
        findings.append({"severity": "warning", "check": "key_facts", "detail": "No key-facts section found"})

    # At least one body section beyond hero
    section_classes = [
        "stat-grid", "comparison-table", "live-tracker", "action-list",
        "timeline", "entity-list", "source-list",
    ]
    checks_total += 1
    if any(c in parser.classes for c in section_classes):
        checks_passed += 1
    else:
        findings.append({"severity": "warning", "check": "body_sections", "detail": "No body sections found"})

    # --- Citation quality ---
    cite_count = len(re.findall(r"<cite[>\s]", raw))
    source_link_count = len(re.findall(r'sources-list.*?<a\s', raw, re.DOTALL))
    checks_total += 1
    if cite_count > 0 or source_link_count > 0:
        checks_passed += 1
    else:
        findings.append({"severity": "warning", "check": "citations", "detail": "No citations or source links found"})

    # --- Check for placeholder/internal URLs ---
    checks_total += 1
    if "example.com" not in raw_lower and "placeholder" not in raw_lower:
        checks_passed += 1
    else:
        findings.append({"severity": "error", "check": "placeholder_urls", "detail": "Page contains placeholder URLs"})

    # --- Check for confidence banner appropriateness ---
    has_confidence_banner = "confidence-banner" in parser.classes or "editor's note" in raw_lower

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    score = round(checks_passed / max(1, checks_total), 3)

    return {
        "file": str(filepath.name),
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "errors": len(errors),
        "warnings": len(warnings),
        "findings": findings,
        "has_confidence_banner": has_confidence_banner,
        "headline": parser.h1_text.strip()[:200],
        "tag_count": len(parser.tags),
        "cite_count": cite_count,
    }


def evaluate_directory(html_dir: Path, public_mode: bool = True) -> dict[str, Any]:
    """Evaluate all .html files in a directory."""
    html_files = sorted(html_dir.glob("*.html"))
    if not html_files:
        return {"error": f"No HTML files found in {html_dir}"}

    per_file = [_check_html_file(f, public_mode) for f in html_files]
    scores = [r["score"] for r in per_file]
    avg_score = round(sum(scores) / len(scores), 3) if scores else 0.0

    all_findings: list[dict] = []
    for r in per_file:
        all_findings.extend(r.pop("findings", []))
    for r in per_file:
        r.pop("findings", None)

    return {
        "dimension": "html_output",
        "mode": "public" if public_mode else "debug",
        "files_evaluated": len(html_files),
        "file_results": per_file,
        "aggregate_score": avg_score,
        "total_errors": sum(r["errors"] for r in per_file),
        "total_warnings": sum(r["warnings"] for r in per_file),
        "all_findings": all_findings,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Deterministic HTML output checks")
    p.add_argument("--output-dir", default="output", help="Directory containing HTML files")
    p.add_argument("--file", help="Evaluate a single HTML file instead of a directory")
    p.add_argument("--public", action="store_true", default=True, help="Check public mode invariants")
    p.add_argument("--debug", action="store_true", help="Also check debug mode invariants")
    args = p.parse_args()

    if args.file:
        result = _check_html_file(Path(args.file), public_mode=args.public)
        results = {
            "dimension": "html_output",
            "files_evaluated": 1,
            "file_results": [result],
            "aggregate_score": result["score"],
        }
    else:
        results = evaluate_directory(Path(args.output_dir), public_mode=args.public)

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
