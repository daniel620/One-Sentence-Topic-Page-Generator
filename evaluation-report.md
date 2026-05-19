# Topic Page Generator — Full Evaluation Report

**Date**: 2026-05-19
**Method**: Deterministic checks + 4 parallel deep-dive agents + EvidenceGraph cross-check
**Branch**: `copilot/create-topic-page-generator`
**Tests**: 96 passed, 0 failed

---

## Overall Score: 7.6 / 10

| Dimension | Score | Weight | Weighted |
|---|---|---|---|
| HTML Output Quality (5 pages) | 8.0 | 0.40 | 3.20 |
| Code Quality | 7.3 | 0.35 | 2.56 |
| DESIGN.md Quality | 7.3 | 0.25 | 1.83 |
| **Overall** | | | **7.59** |

---

## 1. HTML Output Quality — 8.0/10

### Per-page scores

| Page | Structure | Public/Debug | Content | Citations | Editorial | Visual | Event-fit | Usefulness | **Mean** |
|---|---|---|---|---|---|---|---|---|---|
| Ebola (disaster) | 8 | 10 | 9 | 8 | 8 | 8 | 9 | 9 | **8.6** |
| UAE-OPEC (economic) | 8 | 10 | 7 | 8 | 6 | 7 | 8 | 7 | **7.6** |
| Eurovision (cultural) | 8 | 10 | 7 | 8 | 7 | 8 | 8 | 7 | **7.9** |
| OpenAI (tech_launch) | 8 | 10 | 7 | 8 | 7 | 7 | 8 | 7 | **7.7** |
| FIFA (sports) | 8 | 10 | 8 | 8 | 8 | 8 | 9 | 8 | **8.4** |

### Strengths

1. **Public/debug boundary is universally clean (10/10).** Zero leaks of claim_id, source_id, QA gate names, or debug traces across all 5 pages. This is the system's strongest achievement.

2. **Theming and event-fit are genuinely differentiated.** 4 themes (editorial, live-dark, stadium, alert) × 4 hero variants produce visually distinct pages per event type. The disaster page looks different from the sports page, which differs from the cultural page.

3. **Citation format is consistent.** All pages use `[Publisher]` with star indicators for official sources. No raw claim IDs in public mode.

4. **Information hierarchy works for 30-second scans.** Hero → deck → lede → key facts → body sections → sources on every page.

### Weaknesses

1. **"Coming soon" placeholders on UAE-OPEC page (CRITICAL).** Three sections contain "Coming soon — Information is still being gathered and verified." These are repair-generated fallbacks (`repair.py:177-197`) that should be suppressed in public mode. One is a redundant "Source List" sitting below the real Sources footer with 11 real citations.

2. **Source quality inconsistency.** Facebook, YouTube, Instagram, and Reddit appear as sources across multiple pages. These should be excluded or clearly marked in an editorial product.

3. **Uneven content depth.** OpenAI page has only 3 key facts (target: 5). Eurovision timeline has 2 entries for a 5-day event. FIFA entity list names only England and Scotland out of 48 qualified teams.

4. **Spurious source on Ebola page.** A Guardian URL about a climate change PHEIC appears in the sources — likely an irrelevant search result that wasn't filtered.

5. **Truncated publisher names.** "Usembassy" appears instead of "U.S. Embassy Kampala."

6. **Confidence banner language is generic.** "Our automated checks flagged this" is honest but vague — doesn't tell the reader which claims are uncertain.

---

## 2. Code Quality — 7.3/10

### Sub-dimensions

| Dimension | Score | Weight |
|---|---|---|
| Architecture clarity | 8.0 | 0.30 |
| Schema & data contract | 7.0 | 0.25 |
| Prompt engineering | 9.0 | 0.25 |
| Test coverage | 6.0 | 0.20 |
| Error handling & robustness | 6.0 | — |
| Code organization | 7.5 | — |
| Observability | 7.5 | — |
| LLM/deterministic boundary | 8.0 | — |

Deterministic checks: 96 tests pass, 165 functions (154 annotated), 19 Pydantic models, 15 enums, all prompts centralized.

### Strengths

1. **Architecture is well-structured (8/10).** Pipeline phases map 1:1 to module files. `EditorialRun` tracks every phase output. Artifact saving writes 10+ JSON files per run.

2. **Prompt engineering is excellent (9/10).** All prompts in `prompts.py` — zero inlining. Every LLM call uses `instructor` with Pydantic `response_model`. Stage 3 explicitly forbids fabricating hard facts. Degraded mode adds constraints for thin evidence.

3. **LLM/deterministic boundary is intentional (8/10).** Renderer is pure. QA gates are deterministic. Repair strips content deterministically. Fidelity check uses Jaccard similarity.

4. **Recipe table is clean and readable.** `page_layout.py` defines 12 `(event_type, status)` combinations explicitly. Single source of truth for layout.

### Weaknesses

1. **`claim_attributes: dict[str, Any]` is the `Map<string, any>` escape hatch (MODERATE).** `schemas.py:306` — a raw dict with zero runtime validation. A claim with `claim_type="metric"` but `claim_attributes={"foo": "bar"}` passes silently. This is exactly what the rubric warns against.

2. **Test coverage gaps (MODERATE).** `contradictions.py` and `verify_facts.py` have zero dedicated tests despite containing the most complex deterministic logic. `curate.py`'s 4-path role-merge logic is untested. No error-path tests (API failures, rate limits).

3. **`utils.py` is a 567-line catch-all.** Contains regex, scoring, extraction, and dead LLM code (`extract_semantic_claim_with_llm` — defined but never called). Should be 3-4 modules.

4. **Duplicated helpers.** `_get(obj, key, default)` copy-pasted in quality.py, repair.py, verify_facts.py. `_build_instructor_client()` duplicated in 5 files.

5. **Error handling is fragile (6/10).** No partial artifact saving on failure. No timeouts on LLM calls. No application-level retry. Bare `ValueError` exceptions.

6. **Dead code. ** `pipeline.py` (130 lines) has active old revision-loop code that duplicates the orchestrator.

7. **AI source curator adds marginal value.** Receives only source metadata (title, publisher, URL) — never article content. Its judgment largely duplicates the deterministic hostname table.

---

## 3. DESIGN.md Quality — 7.3/10

| Dimension | Score | Weight |
|---|---|---|
| Completeness | 8.0 | 0.30 |
| Clarity | 9.0 | 0.30 |
| Honesty | 7.0 | 0.25 |
| Consistency with implementation | 6.0 | 0.15 |

### Strengths

1. **Clarity is excellent (9/10).** Every decision comes with a "why." Provider choices justified. Architecture diagram annotated. Product principles specific and defensible.

2. **Limitations are specific.** 7 concrete, prioritized issues. Not hand-wavy.

3. **Changes section (Section 7)** documents architectural evolution usefully.

### CRITICAL discrepancies found

1. **Event type count is wrong.** DESIGN.md says "5 event types" and Section 8.3 frames `economic_event` as a gap to fill. But `schemas.py:35` has 6 event types including `ECONOMIC_EVENT`, with full recipes (`page_layout.py:201-220`) and requirements (`schemas.py:630-643`). The UAE-OPEC output already uses it.

2. **Test coverage claim is inaccurate.** Section 6.7: "orchestrator, repair, contradictions, and verify_facts have no dedicated tests." Reality: `test_orchestrator.py` has 6 tests, `test_repair.py` has 12 tests. Only contradictions and verify_facts lack dedicated tests.

3. **Evidence grade enum incomplete.** DESIGN.md lists 4 grades; code has 5 — `MULTI_SOURCED` is omitted.

4. **Off-topic/adversarial input not discussed.** BRIEF.md explicitly asks for this. DESIGN.md covers hallucination but not ambiguous, off-topic, or adversarial inputs.

---

## 4. BRIEF.md Requirement Compliance

**21/22 met. 1 partial.**

| # | Requirement | Verdict |
|---|---|---|
| 1-8 | Deliverables, README, examples, categories, DESIGN.md sections | All ✓ MET |
| 9 | Failure modes (ambiguous/off-topic/adversarial input) | ⚠ PARTIAL |
| 10-22 | Remaining requirements | All ✓ MET |

---

## 5. Event-Type Coverage

| Event Type | Has Output | Has Recipe | Has Requirements |
|---|---|---|---|
| tech_launch | ✓ OpenAI | ✓ | ✓ |
| cultural_event | ✓ Eurovision | ✓ | ✓ |
| sports_tournament | ✓ FIFA | ✓ | ✓ |
| disaster | ✓ Ebola | ✓ | ✓ |
| economic_event | ✓ UAE-OPEC | ✓ | ✓ |
| live_event | ✗ No output | ✓ | ✓ |

---

## 6. Top Findings

1. **Public/debug boundary is the system's strongest achievement.** Zero leaks across all pages. Single-enforcement-point design works.

2. **"Coming soon" placeholders are the most visible quality issue.** Repair-generated fallbacks that should be suppressed in public mode. The UAE-OPEC page has three, including a redundant source list.

3. **DESIGN.md is stale in two critical ways.** Wrong event type count (5 vs 6). Wrong test coverage claim (orchestrator and repair have tests).

4. **`claim_attributes: dict[str, Any]` is the data modeling gap.** No runtime validation on type-specific claim data. Metric claims with missing values pass silently.

5. **Test coverage is thin on the most complex code.** contradictions.py and verify_facts.py have zero dedicated tests.

---

## 7. Top Recommendations

1. **Suppress placeholder sections in public mode** (HIGH IMPACT, LOW EFFORT). Filter sections with "Coming soon" items in the renderer. Fixes the most visible quality issue.

2. **Update DESIGN.md** (HIGH IMPACT, LOW EFFORT). Fix event type count, test coverage claim, evidence grade listing. Bring document into sync with implementation.

3. **Add runtime validation for claim_attributes** (MEDIUM IMPACT, MEDIUM EFFORT). `@field_validator` that checks required keys per claim_type. Closes the data modeling gap.

4. **Add tests for contradictions.py and verify_facts.py** (MEDIUM IMPACT). These contain the most complex deterministic logic and are safety-critical for preventing hallucinated content from reaching the page.

5. **Split utils.py and consolidate duplicated helpers** (LOW IMPACT). Improves maintainability and reduces risk of divergent implementations.

---

## 8. Limitations of This Evaluation

1. **No live pipeline evaluation.** API keys not available. Pre-built HTMLs may not reflect current code state.
2. **No internet fact-checking.** WebSearch unavailable on evaluation model. Relied on internal traceability (page → claim → source URL) rather than external verification.
3. **LLM-as-judge is subjective.** Editorial/visual scores are qualitative judgments. Focus on findings, not exact numbers.
4. **No cost/latency profiling.** Token usage, wall time, and API costs not measured.

---

*Generated by topic-page-evaluator skill with 4 parallel deep-dive agents. 96 unit tests passing. 5 HTML files evaluated. DESIGN.md cross-referenced against 15 source files. 2026-05-19.*
