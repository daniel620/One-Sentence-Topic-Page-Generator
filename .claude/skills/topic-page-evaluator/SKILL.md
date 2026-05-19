---
name: topic-page-evaluator
description: Evaluate the One-Sentence Topic Page Generator from three dimensions — output HTML quality, project code health, and DESIGN.md completeness. Use this skill whenever the user asks to evaluate, assess, review, or judge the project, the generated pages, the codebase, or the design document. Also use when the user wants a quality report, a score, or actionable feedback on the generator. This is the project's built-in evaluation framework — the "source of truth judge."
---

# Topic Page Generator — Evaluation Framework

## What this skill does

Evaluates the hot-event topic page generator across three dimensions, producing
a scored report with specific, actionable feedback. The evaluation combines
**deterministic scripts** (fast, objective) with **LLM-as-judge rubrics**
(subjective dimensions requiring taste and judgment).

## When evaluation differs from testing

Tests verify correctness ("does the code work?"). Evaluation judges quality
("is the output good, and does the system make defensible tradeoffs?").
This skill does both, but its primary value is the qualitative judgment
that tests can't provide.

## Three evaluation dimensions

### 1. HTML Output Quality
The generated topic pages. Evaluated per-page and aggregated.
- Structural validity (valid HTML5, responsive meta, accessibility basics)
- Public/debug boundary (no internal IDs, scores, or enum values in public mode)
- Content completeness (hero, key facts, body sections, sources footer)
- Citation quality (publisher + date, official sources marked, no dead links)
- Editorial quality (headline ≤12 words, deck clarity, factual tone, no fabrication)
- Visual design (theme coherence, typography, information hierarchy, density)
- Event-fit (components match event type, core reader questions answered)
- Reader usefulness (can a reader orient in 30 seconds?)

### 2. Code Quality
The generator codebase. Evaluated holistically.
- Architecture clarity (separation of concerns, pipeline debuggability)
- Schema design (typed unions vs escape hatches, Pydantic contracts)
- Prompt engineering (structured outputs, schema enforcement, no inlining)
- Test coverage (what's tested, what isn't, test quality)
- Code organization (file structure, naming, type hints)
- Error handling (graceful degradation, artifact persistence on failure)
- Observability (run artifacts, logging, debug mode)

### 3. DESIGN.md Quality
The design rationale document.
- Completeness (covers all sections BRIEF.md asks for)
- Clarity (decisions explained with rationale, not just described)
- Honesty (limitations acknowledged, failures characterized)
- Consistency (matches the actual implementation)
- Prioritization (next steps are concrete and ordered, not hand-wavy)

## How to run the evaluation

### Quick eval (terminal summary only)
```
Evaluate the topic page generator.
```

### Full eval with live pipeline (recommended)
```
Evaluate the topic page generator with live pipeline.
```

### Scoped eval
```
Evaluate only the HTML outputs.
Evaluate only the code.
Evaluate only DESIGN.md.
```

## Evaluation process

### Step 1: Run deterministic checks

Run the bundled scripts in parallel. They produce JSON results with pass/fail
and scores for objectively checkable dimensions.

```bash
# HTML structural checks (fast, no API keys)
python .claude/skills/topic-page-evaluator/scripts/evaluate_html.py \
  --output-dir output/ \
  --public

# Code health checks (tests + structure)
python .claude/skills/topic-page-evaluator/scripts/evaluate_code.py \
  --project-root .

# DESIGN.md completeness checks
python .claude/skills/topic-page-evaluator/scripts/evaluate_design.py \
  --design-path DESIGN.md

# Deliverable completeness (BRIEF.md requirements)
python .claude/skills/topic-page-evaluator/scripts/evaluate_deliverables.py \
  --project-root .

# Event-type coverage (5 types, custom examples, taxonomy flexibility)
python .claude/skills/topic-page-evaluator/scripts/evaluate_coverage.py \
  --output-dir output/
```

If the user asks for **live pipeline evaluation**, run all three standard test sentences:

```bash
python .claude/skills/topic-page-evaluator/scripts/run_pipeline.py \
  --sentence "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026." \
  --output-dir /tmp/eval-pipeline/tech_launch

python .claude/skills/topic-page-evaluator/scripts/run_pipeline.py \
  --sentence "The WHO declared an Ebola outbreak in the DRC and Uganda a Public Health Emergency of International Concern on May 16, 2026." \
  --output-dir /tmp/eval-pipeline/disaster

python .claude/skills/topic-page-evaluator/scripts/run_pipeline.py \
  --sentence "The UAE left OPEC on May 1, 2026, ending six decades of membership in the oil cartel." \
  --output-dir /tmp/eval-pipeline/geopolitical
```

The three sentences above cover a tech launch, a disaster, and a geopolitical/economic event
(the last tests taxonomy flexibility since it falls outside the 5 standard event types).

For generalization testing, run with a holdout sentence NOT in the fixtures or standard set:

```bash
python .claude/skills/topic-page-evaluator/scripts/run_pipeline.py \
  --sentence "<a different real event sentence>" \
  --output-dir /tmp/eval-pipeline-generalization/
```

### Step 2: Internet fact-checking (critical for output HTML)

**This is the most important step for HTML quality evaluation.** The
evaluation skill's unique value over unit tests is verifying that the
generated pages contain true facts, not just well-formatted claims.

For each output HTML page:

1. Extract the key factual claims — dates, numbers, named entities, status statements
2. Search the internet (WebSearch or WebFetch) to verify each claim
3. Try to access the specific URLs the page cites as sources
4. Classify each claim: ✓ verified, ? unverifiable, ✗ contradicted

Pay special attention to:
- **Hyper-specific numbers** (52.5%, 1,050,000) — these are hallucination signatures
- **Cited URLs that return 403/404** — the page may cite guessed URLs
- **Duration calculations** — LLMs frequently miscount calendar spans
- **Named entities and their roles** — verify against official sources

Record the verification rate (verified / total claims) per page. This is
the single most important quality metric.

### Step 3: LLM-as-judge evaluation

After deterministic checks, apply judgment to the dimensions that need it.
Read the relevant rubric from `references/` before each evaluation pass.

**For each HTML output file:**
1. Read the file
2. Read `references/rubric_html.md`
3. Evaluate editorial quality, visual design, event-fit, and reader usefulness
4. Assign a score (1-10) for each sub-dimension with a 1-2 sentence justification

**For the codebase:**
1. Read key files (schemas.py, prompts.py, the orchestrator, the renderer)
2. Read `references/rubric_code.md`
3. Evaluate architecture, prompts, schema design, error handling
4. Assign scores with justifications

**For DESIGN.md:**
1. Read DESIGN.md and BRIEF.md
2. Read `references/rubric_design.md`
3. Evaluate completeness, clarity, honesty, consistency with actual code
4. Assign scores with justifications

### Step 3: Aggregate and report

Run the aggregation script to merge deterministic + LLM results:

```bash
python .claude/skills/topic-page-evaluator/scripts/aggregate_report.py \
  --html-results /tmp/eval-html.json \
  --code-results /tmp/eval-code.json \
  --design-results /tmp/eval-design.json \
  --pipeline-results /tmp/eval-pipeline/results.json \
  --output evaluation-report.md
```

Then present the terminal summary to the user: overall scores, top 3 findings,
top 3 recommendations.

### Step 4: Save the report

Save `evaluation-report.md` to the project root. This becomes the baseline for
the next evaluation run — comparing scores shows whether changes helped or hurt.

## What "beyond BRIEF.md" means in practice

BRIEF.md's evaluation dimensions (product judgment, system design, prompt craft,
data modeling, visual sense, engineering tradeoffs) are the starting point.
This skill additionally evaluates:

| Beyond BRIEF.md | Why it matters |
|---|---|
| **Generalization** | Do the three demos work only because they have accessible pages? What happens with a holdout event? |
| **Evidence acquisition yield** | What % of URLs produce extractable text? How many claims per source? This is the real bottleneck. |
| **Self-awareness** | Do the Product Critic and Page Critic make accurate verdicts? Does LOW confidence correlate with actually-bad pages? |
| **Cost/latency profile** | How many LLM calls per page? Wall time? Token usage? Are parallel calls actually parallel? |
| **Degradation behavior** | When evidence is thin, does the page degrade gracefully (shorter, more caveats) or collapse? |
| **Regressions** | Did the last change improve or worsen scores? The report is diffable. |
| **Pipeline observability** | Are run artifacts complete and inspectable? Can you debug a failed run from what's saved? |

## Interpreting scores

Scores are 1-10 per sub-dimension, weighted into dimension scores, then into
an overall. But the numbers are less important than the **findings and
recommendations**. A 7/10 with three specific fixes is more valuable than a
9/10 with no feedback.

| Band | Meaning |
|---|---|
| 9-10 | Near production quality. Minor polish only. |
| 7-8 | Solid. Specific improvements identified. |
| 5-6 | Functional but has clear weaknesses. Prioritize fixes. |
| 3-4 | Significant issues. Not ready for review. |
| 1-2 | Fundamentally broken dimension. |

## Important notes

- **The evaluation itself uses LLM judgment.** Different runs may produce
  slightly different scores for subjective dimensions. Focus on the findings,
  not the exact number.
- **Live pipeline evaluation needs API keys.** ANTHROPIC_API_KEY and
  TAVILY_API_KEY must be set in `.env`. If absent, skip live evaluation
  and note it in the report.
- **The pre-built HTMLs may be stale.** Always prefer live pipeline evaluation
  when keys are available. Fall back to pre-built HTML evaluation with a
  staleness warning in the report.
- **Compare against DESIGN.md claims.** The design doc says the system does X.
  The evaluation checks whether X is actually true. Gaps between DESIGN.md
  and reality are important findings.
- **Save reports for trend analysis.** Each evaluation run produces a dated
  report. Over time, you can see whether scores are trending up or down.
