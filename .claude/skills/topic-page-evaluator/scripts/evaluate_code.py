#!/usr/bin/env python3
"""Deterministic code health checks — no LLM calls, no API keys.

Evaluates:
  - Test presence and coverage
  - Prompt centralization (all prompts in prompts.py)
  - Schema centralization (all models in schemas.py)
  - Type hint coverage
  - File organization
  - Code size and complexity signals

Output: JSON to stdout with scores and findings.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _count_lines(filepath: Path) -> int:
    try:
        return len(filepath.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def _has_type_hints(filepath: Path) -> tuple[int, int]:
    """Count functions with and without return type annotations."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return 0, 0
    # Find function definitions
    funcs = re.findall(r"^\s*def\s+\w+\s*\([^)]*\)", text, re.MULTILINE)
    annotated = re.findall(
        r"^\s*def\s+\w+\s*\([^)]*\)\s*->\s*\w", text, re.MULTILINE
    )
    return len(annotated), len(funcs)


def check_prompt_centralization(project_root: Path) -> dict[str, Any]:
    """Verify all LLM prompts live in prompts.py — none inlined elsewhere."""
    prompt_file = project_root / "generator" / "prompts.py"
    if not prompt_file.exists():
        return {"score": 0.0, "findings": [{"severity": "error", "detail": "generator/prompts.py not found"}]}

    findings = []
    # Files that should NOT contain prompt-like strings
    forbidden_files = [
        "generator/classify.py", "generator/research.py", "generator/compose.py",
        "generator/plan.py", "generator/critic.py", "generator/curate.py",
        "generator/orchestrator.py", "generator/quality.py", "generator/render.py",
        "generator/extraction.py", "generator/evidence.py", "generator/sources.py",
    ]

    prompt_indicators = [
        "You are a", "Your job is to", "system_prompt", "SYSTEM_PROMPT",
        "You classify", "You plan", "You evaluate",
    ]

    inlined_count = 0
    for rel_path in forbidden_files:
        fpath = project_root / rel_path
        if not fpath.exists():
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except Exception:
            continue
        for indicator in prompt_indicators:
            if indicator in text:
                # Check if it's importing from prompts or defining a local constant
                if "from generator.prompts import" in text or "from generator import prompts" in text:
                    continue
                # Allow the prompts.py file itself
                if "prompts.py" in str(fpath):
                    continue
                # Count distinct inlined prompts
                inlined_count += 1
                findings.append({
                    "severity": "warning",
                    "check": "prompt_centralization",
                    "detail": f"{rel_path} may contain inlined prompt: found '{indicator}'",
                })
                break  # One finding per file is enough

    score = 1.0 if inlined_count == 0 else max(0.5, 1.0 - 0.1 * inlined_count)
    return {"score": score, "inlined_prompt_indicators": inlined_count, "findings": findings}


def check_schema_centralization(project_root: Path) -> dict[str, Any]:
    """Verify models use Pydantic, not dict escape hatches."""
    schema_file = project_root / "generator" / "schemas.py"
    findings = []
    if not schema_file.exists():
        return {"score": 0.0, "findings": [{"severity": "error", "detail": "generator/schemas.py not found"}]}

    text = schema_file.read_text(encoding="utf-8")

    # Count Pydantic models
    model_count = len(re.findall(r"class\s+\w+\(BaseModel\)", text))
    # Count enums
    enum_count = len(re.findall(r"class\s+\w+\(str,\s*Enum\)", text))
    # Check for dict escape hatches
    dict_annotations = len(re.findall(r":\s*dict\b", text))
    # Count Discriminator usage (good — typed unions)
    discriminator_count = len(re.findall(r"Discriminator", text))

    score = 1.0
    if dict_annotations > 10:
        findings.append({"severity": "warning", "detail": f"High dict annotation count ({dict_annotations}) — consider typed models"})
        score -= 0.1

    return {
        "score": min(1.0, max(0.0, score)),
        "pydantic_models": model_count,
        "enums": enum_count,
        "discriminators": discriminator_count,
        "dict_annotations": dict_annotations,
        "findings": findings,
    }


def check_test_coverage(project_root: Path) -> dict[str, Any]:
    """Run pytest and report coverage."""
    findings = []
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=short"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        combined = result.stdout + result.stderr
        passed = result.returncode == 0
        # Parse test counts — pytest uses "X passed" format
        passed_match = re.findall(r"(\d+)\s+passed", combined)
        passed_count = int(passed_match[-1]) if passed_match else 0
        failed_match = re.findall(r"(\d+)\s+failed", combined)
        failed_count = int(failed_match[-1]) if failed_match else 0

        score = 1.0 if passed else max(0.3, passed_count / max(1, passed_count + failed_count))

        if not passed:
            findings.append({
                "severity": "error",
                "detail": f"Tests failed: {failed_count} failed, {passed_count} passed",
            })
    except subprocess.TimeoutExpired:
        passed_count, failed_count = 0, 0
        score = 0.0
        findings.append({"severity": "error", "detail": "pytest timed out"})
    except FileNotFoundError:
        passed_count, failed_count = 0, 0
        score = 0.0
        findings.append({"severity": "error", "detail": "pytest not found — install pytest"})

    return {
        "score": round(score, 3),
        "tests_passed": passed_count,
        "tests_failed": failed_count,
        "findings": findings,
    }


def check_type_hints(project_root: Path) -> dict[str, Any]:
    """Check type hint coverage across generator modules."""
    gen_dir = project_root / "generator"
    py_files = sorted(gen_dir.glob("*.py"))
    results = {}
    total_funcs = 0
    total_annotated = 0
    for f in py_files:
        annotated, total = _has_type_hints(f)
        if total > 0:
            results[f.name] = round(annotated / total, 2)
        total_funcs += total
        total_annotated += annotated

    coverage = round(total_annotated / max(1, total_funcs), 2)
    findings = []
    weak_files = [name for name, ratio in results.items() if ratio < 0.5]
    if weak_files:
        findings.append({
            "severity": "info",
            "detail": f"Low type hint coverage (<50%): {', '.join(weak_files)}",
        })

    return {
        "score": coverage,
        "total_functions": total_funcs,
        "annotated_functions": total_annotated,
        "by_file": results,
        "findings": findings,
    }


def check_file_organization(project_root: Path) -> dict[str, Any]:
    """Check that key architectural boundaries are respected."""
    findings = []
    checks_passed = 0
    checks_total = 5

    gen_dir = project_root / "generator"

    # Check 1: prompts.py exists and is substantial
    prompt_file = gen_dir / "prompts.py"
    if prompt_file.exists() and _count_lines(prompt_file) > 100:
        checks_passed += 1
    else:
        findings.append({"severity": "error", "detail": "prompts.py missing or too small"})

    # Check 2: schemas.py exists and is substantial
    schema_file = gen_dir / "schemas.py"
    if schema_file.exists() and _count_lines(schema_file) > 200:
        checks_passed += 1
    else:
        findings.append({"severity": "error", "detail": "schemas.py missing or too small"})

    # Check 3: render.py is a pure function (no LLM calls)
    render_file = gen_dir / "render.py"
    if render_file.exists():
        text = render_file.read_text(encoding="utf-8")
        if "instructor" not in text and "anthropic" not in text.lower() and "openai" not in text.lower():
            checks_passed += 1
        else:
            findings.append({"severity": "warning", "detail": "render.py may contain LLM calls — should be pure"})
    else:
        findings.append({"severity": "error", "detail": "render.py not found"})

    # Check 4: templates directory exists with components
    templates_dir = project_root / "templates"
    if templates_dir.exists():
        components = list((templates_dir / "components").glob("*.html.j2"))
        if len(components) >= 5:
            checks_passed += 1
        else:
            findings.append({"severity": "warning", "detail": f"Only {len(components)} component templates found"})
    else:
        findings.append({"severity": "error", "detail": "templates/ directory not found"})

    # Check 5: tests directory with multiple test files
    tests_dir = project_root / "tests"
    if tests_dir.exists():
        test_files = list(tests_dir.glob("test_*.py"))
        if len(test_files) >= 4:
            checks_passed += 1
        else:
            findings.append({"severity": "warning", "detail": f"Only {len(test_files)} test files found"})

    return {
        "score": round(checks_passed / checks_total, 2),
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "findings": findings,
    }


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Deterministic code health checks")
    p.add_argument("--project-root", default=".", help="Project root directory")
    args = p.parse_args()

    root = Path(args.project_root).resolve()

    results: dict[str, Any] = {
        "dimension": "code_quality",
        "checks": {},
        "aggregate_score": 0.0,
    }

    checks = {
        "prompt_centralization": check_prompt_centralization(root),
        "schema_centralization": check_schema_centralization(root),
        "test_coverage": check_test_coverage(root),
        "type_hints": check_type_hints(root),
        "file_organization": check_file_organization(root),
    }

    scores = []
    for name, result in checks.items():
        results["checks"][name] = result
        scores.append(result.get("score", 0.0))

    results["aggregate_score"] = round(sum(scores) / len(scores), 3) if scores else 0.0
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
