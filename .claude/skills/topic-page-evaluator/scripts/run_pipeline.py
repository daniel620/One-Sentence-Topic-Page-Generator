#!/usr/bin/env python3
"""Run the topic page generator pipeline live and collect artifacts.

Requires: ANTHROPIC_API_KEY and TAVILY_API_KEY in .env or environment.

Captures:
  - Wall-clock time
  - Exit code
  - Output HTML path
  - Run artifacts (hypothesis.json, evidence_graph.json, etc.)
  - Pipeline phases and their durations (from summary.json)

Output: JSON to stdout with results.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def find_latest_run(runs_dir: Path) -> Path | None:
    """Find the most recent run directory by modification time."""
    if not runs_dir.exists():
        return None
    dirs = [d for d in runs_dir.glob("*") if d.is_dir() and (d / "summary.json").exists()]
    if not dirs:
        return None
    # Sort by modification time (newest first), not alphabetical — avoids
    # picking a stale directory when multiple runs exist.
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[0]


def run_pipeline(sentence: str, project_root: Path, output_dir: Path | None = None) -> dict[str, Any]:
    """Run generate.py with the given sentence and collect results."""
    # Check for API keys
    env_file = project_root / ".env"
    has_keys = False
    if env_file.exists():
        env_text = env_file.read_text(encoding="utf-8")
        has_keys = "ANTHROPIC_API_KEY" in env_text and "TAVILY_API_KEY" in env_text

    if not has_keys:
        return {
            "error": "API keys not found",
            "detail": "Set ANTHROPIC_API_KEY and TAVILY_API_KEY in .env",
            "score": 0.0,
        }

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            ["python", "scripts/generate.py", sentence],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except subprocess.TimeoutExpired:
        return {
            "error": "Pipeline timed out after 300s",
            "wall_time_s": 300.0,
            "score": 0.0,
        }

    wall_time = round(time.monotonic() - start_time, 1)
    success = result.returncode == 0

    # Find output artifacts
    runs_dir = project_root / "runs"
    latest_run = find_latest_run(runs_dir)

    artifacts: dict[str, Any] = {}
    if latest_run:
        for artifact_name in [
            "hypothesis.json", "evidence_graph.json", "product_critic.json",
            "ia_plan.json", "topic_page.json", "qa_report.json",
            "page_critic.json", "summary.json",
        ]:
            artifact_path = latest_run / artifact_name
            if artifact_path.exists():
                try:
                    artifacts[artifact_name] = json.loads(artifact_path.read_text(encoding="utf-8"))
                except Exception:
                    artifacts[artifact_name] = {"error": "Failed to parse"}

    # Find output HTML
    output_html = None
    output_dir_path = project_root / "output"
    if output_dir_path.exists():
        html_files = sorted(output_dir_path.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if html_files:
            output_html = str(html_files[0])

    # Extract pipeline phases from summary
    phases: dict[str, float] = {}
    if "summary.json" in artifacts:
        summary = artifacts["summary.json"]
        if isinstance(summary, dict):
            for key, value in summary.items():
                if key.endswith("_duration_s") or key.endswith("_time"):
                    phases[key] = float(value)

    # Evidence stats
    evidence_stats = {}
    if "evidence_graph.json" in artifacts:
        eg = artifacts["evidence_graph.json"]
        if isinstance(eg, dict):
            sources = eg.get("sources", [])
            claims = eg.get("claims", [])
            evidence_stats["source_count"] = len(sources)
            evidence_stats["claim_count"] = len(claims)
            evidence_stats["public_claims"] = sum(
                1 for c in claims if c.get("public_claim_eligible", False)
            )
            evidence_stats["contradictions"] = len(eg.get("contradictions", []))
            # Count source roles
            roles = {}
            for s in sources:
                role = s.get("final_source_role", "unknown")
                roles[role] = roles.get(role, 0) + 1
            evidence_stats["source_roles"] = roles

    return {
        "dimension": "live_pipeline",
        "success": success,
        "wall_time_s": wall_time,
        "exit_code": result.returncode,
        "sentence": sentence,
        "output_html": output_html,
        "run_dir": str(latest_run) if latest_run else None,
        "artifacts_available": list(artifacts.keys()),
        "phases": phases,
        "evidence_stats": evidence_stats,
        "stdout_tail": result.stdout[-2000:] if result.stdout else "",
        "stderr_tail": result.stderr[-2000:] if result.stderr else "",
        "score": 0.0,  # Score assigned by LLM judge after reviewing output
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Run pipeline live and collect artifacts")
    p.add_argument("--sentence", required=True, help="Event sentence to generate a page for")
    p.add_argument("--project-root", default=".", help="Project root directory")
    p.add_argument("--output-dir", help="Directory to copy output to (optional)")
    args = p.parse_args()

    root = Path(args.project_root).resolve()
    results = run_pipeline(args.sentence, root)
    print(json.dumps(results, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
