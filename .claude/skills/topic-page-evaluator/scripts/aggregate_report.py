#!/usr/bin/env python3
"""Aggregate deterministic + LLM evaluation results into a final report.

Reads JSON results from individual evaluation scripts and produces:
  1. A Markdown report file (evaluation-report.md)
  2. A terminal summary

The LLM-as-judge scores are passed via --llm-scores JSON string.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _band(score: float) -> str:
    if score >= 9:
        return "Excellent"
    if score >= 7:
        return "Good"
    if score >= 5:
        return "Fair"
    if score >= 3:
        return "Weak"
    return "Poor"


def _status_emoji(score: float) -> str:
    if score >= 7:
        return "PASS"
    if score >= 5:
        return "WARN"
    return "FAIL"


def generate_report(
    html_results: dict | None = None,
    code_results: dict | None = None,
    design_results: dict | None = None,
    pipeline_results: dict | None = None,
    llm_scores: dict | None = None,
) -> str:
    """Generate a Markdown evaluation report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []

    lines.append("# Topic Page Generator — Evaluation Report")
    lines.append(f"**Date**: {now}")
    lines.append("")

    # --- Overall scores ---
    scores: dict[str, float] = {}
    if html_results and "aggregate_score" in html_results:
        scores["HTML Output"] = html_results["aggregate_score"] * 10
    if code_results and "aggregate_score" in code_results:
        scores["Code Quality"] = code_results["aggregate_score"] * 10
    if design_results and "aggregate_score" in design_results:
        scores["DESIGN.md"] = design_results["aggregate_score"] * 10
    if pipeline_results and not pipeline_results.get("error"):
        scores["Live Pipeline"] = pipeline_results.get("score", 0) * 10

    if llm_scores:
        for key, val in llm_scores.items():
            scores[f"LLM: {key}"] = val

    if scores:
        overall = round(sum(scores.values()) / len(scores), 1)
        lines.append("## Overall")
        lines.append("")
        lines.append("| Dimension | Score | Status |")
        lines.append("|-----------|-------|--------|")
        for name, score in scores.items():
            lines.append(f"| {name} | {score:.1f}/10 | {_status_emoji(score)} |")
        lines.append(f"| **Overall** | **{overall:.1f}/10** | **{_status_emoji(overall)}** |")
        lines.append("")

    # --- HTML Output ---
    if html_results:
        lines.append("## HTML Output Evaluation")
        lines.append("")
        lines.append(f"**Aggregate score**: {html_results.get('aggregate_score', 0):.2f} ({_band(html_results.get('aggregate_score', 0) * 10)})")
        lines.append(f"**Files evaluated**: {html_results.get('files_evaluated', 0)}")
        lines.append(f"**Mode**: {html_results.get('mode', 'unknown')}")
        lines.append("")

        for fr in html_results.get("file_results", []):
            lines.append(f"### {fr.get('file', 'unknown')}")
            lines.append(f"- Score: {fr.get('score', 0):.2f}")
            lines.append(f"- Checks: {fr.get('checks_passed', 0)}/{fr.get('checks_total', 0)} passed")
            lines.append(f"- Errors: {fr.get('errors', 0)}, Warnings: {fr.get('warnings', 0)}")
            lines.append(f"- Headline: _{fr.get('headline', '')[:120]}_")
            lines.append(f"- Citations: {fr.get('cite_count', 0)} inline")
            lines.append(f"- Confidence banner: {'Yes' if fr.get('has_confidence_banner') else 'No'}")
            lines.append("")

        # Findings
        all_findings = html_results.get("all_findings", [])
        if all_findings:
            errors = [f for f in all_findings if f.get("severity") == "error"]
            warnings = [f for f in all_findings if f.get("severity") == "warning"]
            infos = [f for f in all_findings if f.get("severity") == "info"]

            if errors:
                lines.append("#### Errors")
                for f in errors:
                    lines.append(f"- **{f.get('check', '')}**: {f.get('detail', '')}")
                lines.append("")
            if warnings:
                lines.append("#### Warnings")
                for f in warnings:
                    lines.append(f"- **{f.get('check', '')}**: {f.get('detail', '')}")
                lines.append("")

    # --- Code Quality ---
    if code_results:
        lines.append("## Code Quality Evaluation")
        lines.append("")
        lines.append(f"**Aggregate score**: {code_results.get('aggregate_score', 0):.2f}")
        lines.append("")

        for check_name, check_data in code_results.get("checks", {}).items():
            score = check_data.get("score", 0)
            lines.append(f"- **{check_name}**: {score:.2f}")
            for f in check_data.get("findings", []):
                lines.append(f"  - {f.get('severity', '').upper()}: {f.get('detail', '')}")
            # Extra detail for specific checks
            if check_name == "type_hints":
                lines.append(f"  - {check_data.get('annotated_functions', 0)}/{check_data.get('total_functions', 0)} functions annotated")
            if check_name == "test_coverage":
                lines.append(f"  - {check_data.get('tests_passed', 0)} passed, {check_data.get('tests_failed', 0)} failed")
            if check_name == "schema_centralization":
                lines.append(f"  - {check_data.get('pydantic_models', 0)} Pydantic models, {check_data.get('enums', 0)} enums, {check_data.get('discriminators', 0)} discriminators")
        lines.append("")

    # --- DESIGN.md ---
    if design_results:
        lines.append("## DESIGN.md Evaluation")
        lines.append("")
        lines.append(f"**Aggregate score**: {design_results.get('aggregate_score', 0):.2f}")
        lines.append(f"**Words**: {design_results.get('word_count', 0)}, **Lines**: {design_results.get('line_count', 0)}")
        lines.append(f"**Sections found**: {design_results.get('sections_found', 0)}/{design_results.get('sections_total', 0)}")
        lines.append(f"**Code blocks**: {design_results.get('code_blocks', 0)}")
        lines.append(f"**Limitation mentions**: {design_results.get('limitation_mentions', 0)}")
        lines.append("")

        for f in design_results.get("findings", []):
            lines.append(f"- {f.get('severity', '').upper()}: {f.get('detail', '')}")
        lines.append("")

    # --- Live Pipeline ---
    if pipeline_results:
        lines.append("## Live Pipeline Evaluation")
        lines.append("")
        if pipeline_results.get("error"):
            lines.append(f"**Error**: {pipeline_results['error']}")
            lines.append(f"**Detail**: {pipeline_results.get('detail', '')}")
        else:
            lines.append(f"**Success**: {pipeline_results.get('success')}")
            lines.append(f"**Wall time**: {pipeline_results.get('wall_time_s', 0):.1f}s")
            lines.append(f"**Sentence**: {pipeline_results.get('sentence', '')}")
            lines.append(f"**Output HTML**: {pipeline_results.get('output_html', 'none')}")
            lines.append(f"**Run artifacts**: {', '.join(pipeline_results.get('artifacts_available', []))}")
            lines.append("")

            es = pipeline_results.get("evidence_stats", {})
            if es:
                lines.append("**Evidence stats**:")
                lines.append(f"- Sources: {es.get('source_count', 0)}")
                lines.append(f"- Claims: {es.get('claim_count', 0)} ({es.get('public_claims', 0)} public-eligible)")
                lines.append(f"- Contradictions: {es.get('contradictions', 0)}")
                lines.append(f"- Source roles: {es.get('source_roles', {})}")
                lines.append("")

            phases = pipeline_results.get("phases", {})
            if phases:
                lines.append("**Phase durations**:")
                for phase, duration in sorted(phases.items()):
                    lines.append(f"- {phase}: {duration}s")
                lines.append("")

    # --- Recommendations ---
    lines.append("## Top Recommendations")
    lines.append("")
    lines.append("> Replace this section with the LLM judge's top 3-5 recommendations after running the full evaluation.")
    lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append(f"Generated by topic-page-evaluator at {now}")

    return "\n".join(lines)


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Aggregate evaluation results into a report")
    p.add_argument("--html-results", help="Path to HTML evaluation JSON")
    p.add_argument("--code-results", help="Path to code evaluation JSON")
    p.add_argument("--design-results", help="Path to DESIGN.md evaluation JSON")
    p.add_argument("--pipeline-results", help="Path to pipeline run JSON")
    p.add_argument("--llm-scores", help='JSON string of LLM-as-judge scores, e.g. \'{"Editorial": 8.5}\'')
    p.add_argument("--output", default="evaluation-report.md", help="Output Markdown file path")
    args = p.parse_args()

    html = None
    code = None
    design = None
    pipeline = None
    llm = None

    if args.html_results:
        try:
            html = json.loads(Path(args.html_results).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: Could not read HTML results: {exc}", file=sys.stderr)

    if args.code_results:
        try:
            code = json.loads(Path(args.code_results).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: Could not read code results: {exc}", file=sys.stderr)

    if args.design_results:
        try:
            design = json.loads(Path(args.design_results).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: Could not read design results: {exc}", file=sys.stderr)

    if args.pipeline_results:
        try:
            pipeline = json.loads(Path(args.pipeline_results).read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: Could not read pipeline results: {exc}", file=sys.stderr)

    if args.llm_scores:
        try:
            llm = json.loads(args.llm_scores)
        except Exception as exc:
            print(f"Warning: Could not parse LLM scores: {exc}", file=sys.stderr)

    report = generate_report(html, code, design, pipeline, llm)

    output_path = Path(args.output)
    output_path.write_text(report, encoding="utf-8")
    print(f"Report saved to {output_path}")
    print()
    print("--- Terminal Summary ---")
    # Print a short terminal summary
    if html:
        print(f"HTML Output:  {html.get('aggregate_score', 0) * 10:.1f}/10")
    if code:
        print(f"Code Quality: {code.get('aggregate_score', 0) * 10:.1f}/10")
    if design:
        print(f"DESIGN.md:    {design.get('aggregate_score', 0) * 10:.1f}/10")
    if pipeline:
        if pipeline.get("error"):
            print(f"Pipeline:     SKIPPED ({pipeline.get('error')})")
        else:
            print(f"Pipeline:     {'SUCCESS' if pipeline.get('success') else 'FAILED'} ({pipeline.get('wall_time_s', 0):.1f}s)")


if __name__ == "__main__":
    main()
