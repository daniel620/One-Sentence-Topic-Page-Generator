#!/usr/bin/env python3
"""Deliverable completeness check against BRIEF.md requirements.

Checks:
  - 3+ committed HTML outputs exist in output/
  - At least 2 are from custom-chosen inputs (not the 3 brief examples)
  - The 3 examples span different event categories
  - DESIGN.md exists and is substantive
  - README.md has run instructions
  - All 5 event types have at least a fixture or generalization probe

Output: JSON to stdout.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# The 3 example sentences from BRIEF.md — any output matching these is NOT
# "of your choice."
BRIEF_SENTENCES = [
    "openai rolled out gpt-5.5 instant",
    "eurovision 2026 is being held in vienna",
    "the 2026 fifa world cup kicks off at estadio azteca",
]

ALL_EVENT_TYPES = [
    "tech_launch",
    "live_event",
    "sports_tournament",
    "cultural_event",
    "disaster",
]


def _extract_keywords(html_path: Path) -> str:
    """Extract a normalized slug from the HTML filename."""
    name = html_path.stem
    # Remove trailing suffixes
    name = re.sub(r"\.(debug|public)$", "", name)
    return name.lower()


def _classify_filename(filename: str) -> str | None:
    """Guess event type from filename keywords."""
    mapping = {
        "openai": "tech_launch",
        "gpt": "tech_launch",
        "chatgpt": "tech_launch",
        "eurovision": "cultural_event",
        "world-cup": "sports_tournament",
        "fifa": "sports_tournament",
        "wimbledon": "sports_tournament",
        "earthquake": "disaster",
        "wwdc": "tech_launch",
        "apple": "tech_launch",
        "tesla": "tech_launch",
        "glastonbury": "cultural_event",
        "nba": "sports_tournament",
        "oscar": "cultural_event",
        "hurricane": "disaster",
        "wildfire": "disaster",
        "flood": "disaster",
    }
    lower = filename.lower()
    for keyword, event_type in mapping.items():
        if keyword in lower:
            return event_type
    return None


def check_deliverables(project_root: Path) -> dict[str, Any]:
    findings: list[dict] = []
    checks_passed = 0
    checks_total = 0

    output_dir = project_root / "output"
    html_files = sorted(output_dir.glob("*.html")) if output_dir.exists() else []

    # --- Check 1: At least 3 HTML outputs ---
    checks_total += 1
    if len(html_files) >= 3:
        checks_passed += 1
    else:
        findings.append({
            "severity": "error",
            "check": "html_count",
            "detail": f"Only {len(html_files)} HTML outputs — need at least 3",
        })

    # --- Check 2: At least 2 custom-chosen inputs ---
    custom_count = 0
    brief_count = 0
    for f in html_files:
        slug = _extract_keywords(f)
        is_brief = any(bs in slug for bs in [
            "openai", "gpt-5-5", "chatgpt",
            "eurovision", "vienna",
            "world-cup", "fifa", "estadio-azteca",
        ])
        if is_brief:
            brief_count += 1
        else:
            custom_count += 1

    checks_total += 1
    if custom_count >= 2:
        checks_passed += 1
    else:
        findings.append({
            "severity": "error",
            "check": "custom_examples",
            "detail": f"Only {custom_count} custom-chosen examples — need at least 2. "
                       f"Current outputs are all from the brief's example inputs.",
        })

    # --- Check 3: Span at least 3 different event categories ---
    event_types_found: set[str] = set()
    for f in html_files:
        et = _classify_filename(f.name)
        if et:
            event_types_found.add(et)
        else:
            # Try reading the HTML title
            try:
                text = f.read_text(encoding="utf-8")[:2000]
                for et in ALL_EVENT_TYPES:
                    if et in text.lower():
                        event_types_found.add(et)
                        break
            except Exception:
                pass

    checks_total += 1
    if len(event_types_found) >= 3:
        checks_passed += 1
    else:
        findings.append({
            "severity": "warning",
            "check": "event_type_diversity",
            "detail": f"Only {len(event_types_found)} event types covered: {event_types_found}. "
                       f"Need at least 3 different categories.",
        })

    # --- Check 4: Missing event types ---
    missing_types = set(ALL_EVENT_TYPES) - event_types_found
    if missing_types:
        findings.append({
            "severity": "warning",
            "check": "missing_event_types",
            "detail": f"No output for event types: {missing_types}. "
                       f"Consider adding a disaster-type example.",
        })

    # --- Check 5: DESIGN.md exists and is substantive ---
    design_path = project_root / "DESIGN.md"
    checks_total += 1
    if design_path.exists() and design_path.stat().st_size > 2000:
        checks_passed += 1
    else:
        findings.append({
            "severity": "error",
            "check": "design_md",
            "detail": "DESIGN.md missing or too short (<2000 bytes)",
        })

    # --- Check 6: README has run instructions ---
    readme_path = project_root / "README.md"
    checks_total += 1
    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8").lower()
        has_install = any(phrase in readme_text for phrase in [
            "pip install", "pip3 install", "install -r requirements",
            "python -m pip", "poetry install",
        ])
        has_run = any(phrase in readme_text for phrase in [
            "python scripts/generate", "python -m", "generate.py",
            "how to run", "run the generator",
        ])
        if has_install and has_run:
            checks_passed += 1
        else:
            findings.append({
                "severity": "warning",
                "check": "readme",
                "detail": f"README.md missing install or run instructions "
                           f"(has_install={has_install}, has_run={has_run})",
            })
    else:
        findings.append({
            "severity": "error",
            "check": "readme",
            "detail": "README.md not found",
        })

    # --- Check 7: .env.example exists ---
    env_example = project_root / ".env.example"
    checks_total += 1
    if env_example.exists():
        text = env_example.read_text(encoding="utf-8")
        if "ANTHROPIC_API_KEY" in text and "TAVILY_API_KEY" in text:
            checks_passed += 1
        else:
            findings.append({
                "severity": "warning",
                "check": "env_example",
                "detail": ".env.example missing required key names",
            })
    else:
        findings.append({
            "severity": "error",
            "check": "env_example",
            "detail": ".env.example not found",
        })

    # --- Check 8: No API keys committed ---
    checks_total += 1
    # Quick scan of git-tracked files for common key patterns
    import subprocess
    try:
        result = subprocess.run(
            ["git", "log", "-p", "--all", "--", "."],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )
        committed = result.stdout + result.stderr
        key_leaks = []
        for pattern in ["sk-ant-api", "sk-or-", "sk-proj-", "tvly-", "ANTHROPIC_API_KEY=sk", "TAVILY_API_KEY=tvly"]:
            if pattern in committed:
                key_leaks.append(pattern[:20])
        if not key_leaks:
            checks_passed += 1
        else:
            findings.append({
                "severity": "error",
                "check": "no_api_keys",
                "detail": f"API keys found in git history! Patterns: {key_leaks}",
            })
    except Exception as exc:
        # Skip if git not available
        checks_total -= 1
        findings.append({
            "severity": "info",
            "check": "no_api_keys",
            "detail": f"Could not scan git history: {exc}",
        })

    score = round(checks_passed / max(1, checks_total), 3)

    return {
        "dimension": "deliverables",
        "score": score,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "html_files_found": len(html_files),
        "custom_examples": custom_count,
        "brief_examples": brief_count,
        "event_types_covered": sorted(event_types_found),
        "missing_event_types": sorted(missing_types),
        "findings": findings,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Check BRIEF.md deliverable completeness")
    p.add_argument("--project-root", default=".", help="Project root directory")
    args = p.parse_args()

    results = check_deliverables(Path(args.project_root).resolve())
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
