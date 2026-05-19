#!/usr/bin/env python3
"""Deterministic DESIGN.md completeness checks — no LLM calls.

Evaluates:
  - Presence of required sections (per BRIEF.md)
  - Word count and depth
  - Concrete examples vs hand-waving
  - Honest limitation acknowledgment

Output: JSON to stdout with scores and findings.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_SECTIONS = [
    ("product_decisions", r"(?i)(product\s+decision|what\s+belongs\s+on\s+a\s+topic\s+page|page\s+shape|what\s+we'?re\s+building|product\s+principle)"),
    ("system_architecture", r"(?i)(system\s+architecture|architecture\s+\(|pipeline\s+structure|how\s+the\s+generation|generation\s+pipeline)"),
    ("prompt_data_contract", r"(?i)(prompt.*(?:data\s+contract|schema)|data\s+contract|schema\s+contract|structured\s+(?:output|data)|stage.*(?:system|user)\s+prompt)"),
    ("information_sourcing", r"(?i)(information\s+sourcing|how.*pull\s+real|web\s+search|evidence\s+acquisition|search.*extract)"),
    ("failure_modes", r"(?i)(failure\s+mode|what\s+happens\s+when|hallucinat|limitation|known\s+limitation|current\s+limitation)"),
    ("next_steps", r"(?i)(what\s+(?:you'?d|to)\s+do\s+(?:with\s+another\s+week|next)|prioriti[zs]ed|backlog|improve\s+next)"),
    ("visual_ux_rationale", r"(?i)(visual.*(?:ux|sense|design|system)|theme|typography|hero|layout|rendering|renderer|template)"),
    ("evaluation_awareness", r"(?i)(evaluat|how\s+we'?ll\s+evaluate|what.*look\s+for|judgment|taste)"),
]


def evaluate_design(design_path: Path) -> dict[str, Any]:
    if not design_path.exists():
        return {"error": f"File not found: {design_path}", "aggregate_score": 0.0}

    text = design_path.read_text(encoding="utf-8")
    word_count = len(text.split())
    line_count = len(text.splitlines())
    findings: list[dict[str, Any]] = []

    # --- Check required sections ---
    sections_found = 0
    sections_missing = []
    for name, pattern in REQUIRED_SECTIONS:
        if re.search(pattern, text):
            sections_found += 1
        else:
            sections_missing.append(name)

    section_score = sections_found / len(REQUIRED_SECTIONS)

    if sections_missing:
        findings.append({
            "severity": "warning",
            "check": "required_sections",
            "detail": f"Missing sections: {', '.join(sections_missing)}",
        })

    # --- Check word count (substantial but not bloated) ---
    if word_count < 1000:
        findings.append({"severity": "warning", "check": "depth", "detail": f"DESIGN.md is short ({word_count} words) — may lack depth"})
    elif word_count > 15000:
        findings.append({"severity": "info", "check": "depth", "detail": f"DESIGN.md is very long ({word_count} words) — consider conciseness"})

    # --- Check for concrete examples (code snippets, diagrams, specific decisions) ---
    code_blocks = len(re.findall(r"```", text)) // 2
    has_ascii_diagram = bool(re.search(r"[├└│─┌┐┘]", text))
    has_table = bool(re.search(r"\|.*\|.*\|", text))

    if code_blocks < 2:
        findings.append({"severity": "info", "check": "concreteness", "detail": "Few code examples — consider adding schema snippets or prompt excerpts"})

    # --- Check for honest limitations ---
    limitation_phrases = [
        "not work", "doesn't work", "does not generalize", "bottleneck",
        "known limitation", "current limitation", "honest assessment",
        "limitation", "not yet", "does not", "is not", "cannot",
    ]
    limitation_mentions = sum(1 for phrase in limitation_phrases if phrase.lower() in text.lower())
    if limitation_mentions < 3:
        findings.append({"severity": "warning", "check": "honesty", "detail": "Few limitation acknowledgments — does the system really have no weaknesses?"})

    # --- Check for prioritized next steps ---
    has_prioritized = bool(re.search(r"(?i)(prioriti[zs]ed|#1|#2|1\.|2\.|first.*then|next.*then)", text))
    if not has_prioritized:
        findings.append({"severity": "info", "check": "prioritization", "detail": "Next steps don't appear to be explicitly prioritized"})

    return {
        "dimension": "design_md",
        "word_count": word_count,
        "line_count": line_count,
        "sections_found": sections_found,
        "sections_total": len(REQUIRED_SECTIONS),
        "section_score": round(section_score, 3),
        "code_blocks": code_blocks,
        "has_ascii_diagram": has_ascii_diagram,
        "has_table": has_table,
        "limitation_mentions": limitation_mentions,
        "aggregate_score": round(section_score, 3),
        "findings": findings,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Deterministic DESIGN.md checks")
    p.add_argument("--design-path", default="DESIGN.md", help="Path to DESIGN.md")
    args = p.parse_args()

    results = evaluate_design(Path(args.design_path))
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
