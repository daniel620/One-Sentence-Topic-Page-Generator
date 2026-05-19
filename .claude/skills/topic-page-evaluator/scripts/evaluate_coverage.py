#!/usr/bin/env python3
"""Event-type coverage check for output HTML files.

Checks:
  - All 5 standard event types have at least 1 output file
  - The two custom example sentences are present in output/
  - At least one example tests a non-standard event type

Output: JSON to stdout.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# The 5 standard event types the generator recognizes
STANDARD_EVENT_TYPES = [
    "tech_launch",
    "live_event",
    "sports_tournament",
    "cultural_event",
    "disaster",
]

# Keywords that map filenames to standard event types
FILENAME_TYPE_MAP: dict[str, str] = {
    "openai": "tech_launch",
    "gpt": "tech_launch",
    "chatgpt": "tech_launch",
    "eurovision": "cultural_event",
    "world-cup": "sports_tournament",
    "fifa": "sports_tournament",
    "ebola": "disaster",
    "outbreak": "disaster",
    "earthquake": "disaster",
    "hurricane": "disaster",
    "wildfire": "disaster",
    "flood": "disaster",
    "wwdc": "tech_launch",
    "apple": "tech_launch",
    "tesla": "tech_launch",
    "glastonbury": "cultural_event",
    "nba": "sports_tournament",
    "oscar": "cultural_event",
    "wimbledon": "sports_tournament",
}

# The two custom example sentences to check for (key substrings from filenames)
CUSTOM_EXAMPLE_KEYWORDS = [
    "ebola",           # "The WHO declared an Ebola outbreak..."
    "opec",            # "The UAE left OPEC..."
]


def _classify_filename(filename: str) -> str | None:
    """Guess event type from filename keywords."""
    lower = filename.lower()
    for keyword, event_type in FILENAME_TYPE_MAP.items():
        if keyword in lower:
            return event_type
    return None


def check_coverage(output_dir: Path) -> dict[str, Any]:
    findings: list[dict] = []
    checks_passed = 0
    checks_total = 0

    html_files = sorted(output_dir.glob("*.html")) if output_dir.exists() else []

    if not html_files:
        return {
            "dimension": "coverage",
            "score": 0.0,
            "checks_passed": 0,
            "checks_total": 0,
            "html_files_found": 0,
            "event_types_covered": [],
            "missing_event_types": list(STANDARD_EVENT_TYPES),
            "custom_examples_found": [],
            "custom_examples_missing": list(CUSTOM_EXAMPLE_KEYWORDS),
            "has_non_standard_type": False,
            "findings": [{"severity": "error", "check": "no_files", "detail": "No HTML files found in output/"}],
        }

    # --- Check 1: All 5 event types have at least 1 output ---
    event_types_found: set[str] = set()
    for f in html_files:
        et = _classify_filename(f.name)
        if et:
            event_types_found.add(et)

    checks_total += 1
    missing_types = set(STANDARD_EVENT_TYPES) - event_types_found
    if not missing_types:
        checks_passed += 1
    else:
        findings.append({
            "severity": "error",
            "check": "event_type_coverage",
            "detail": f"Missing output for event types: {sorted(missing_types)}. "
                       f"All 5 standard event types must have at least 1 output file.",
        })

    # --- Check 2: The two custom examples are present ---
    custom_found: list[str] = []
    custom_missing: list[str] = []
    for kw in CUSTOM_EXAMPLE_KEYWORDS:
        matched = [f.name for f in html_files if kw in f.name.lower()]
        if matched:
            custom_found.append(kw)
        else:
            custom_missing.append(kw)

    checks_total += 1
    if not custom_missing:
        checks_passed += 1
    else:
        findings.append({
            "severity": "error",
            "check": "custom_examples",
            "detail": f"Missing output for custom examples with keywords: {custom_missing}. "
                       f"Expected outputs derived from the two custom test sentences.",
        })

    # --- Check 3: At least one example tests a non-standard event type ---
    non_standard_count = 0
    for f in html_files:
        et = _classify_filename(f.name)
        if et is None:
            non_standard_count += 1

    checks_total += 1
    if non_standard_count >= 1:
        checks_passed += 1
    else:
        findings.append({
            "severity": "warning",
            "check": "non_standard_type",
            "detail": "No examples test a non-standard event type. "
                       "At least one output should fall outside the 5 standard "
                       "taxonomy types (e.g., geopolitical, economic, legal).",
        })

    # --- Report non-standard files for transparency ---
    non_standard_files = [
        f.name for f in html_files if _classify_filename(f.name) is None
    ]

    score = round(checks_passed / max(1, checks_total), 3)

    return {
        "dimension": "coverage",
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "html_files_found": len(html_files),
        "event_types_covered": sorted(event_types_found),
        "missing_event_types": sorted(missing_types),
        "custom_examples_found": custom_found,
        "custom_examples_missing": custom_missing,
        "has_non_standard_type": non_standard_count >= 1,
        "non_standard_files": non_standard_files,
        "findings": findings,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Check event-type coverage of output HTML files")
    p.add_argument("--output-dir", default="output", help="Directory containing HTML output files")
    args = p.parse_args()

    results = check_coverage(Path(args.output_dir))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
