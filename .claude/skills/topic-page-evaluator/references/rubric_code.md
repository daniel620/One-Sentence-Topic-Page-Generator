# Code Quality — LLM-as-Judge Rubric

Evaluate the generator codebase on these dimensions. Assign a 1-10 score
per sub-dimension with a specific, actionable justification.

Read the key source files before scoring: schemas.py, prompts.py,
orchestrator.py, render.py, quality.py, and at least 2-3 other modules.

## 1. Architecture Clarity (weight: 0.30)

**What to evaluate**: Is the separation of responsibilities clear and intentional?

| Score | Description |
|-------|-------------|
| 9-10 | Every module has a single, clear responsibility. LLM/deterministic boundary is crisp. Pipeline is debuggable at every stage. The architecture diagram in DESIGN.md matches the code. |
| 7-8 | Clear separation with minor boundary violations. One or two modules have slightly overlapping responsibilities. Mostly debuggable. |
| 5-6 | Responsibilities are somewhat blurred. LLM calls and deterministic logic occasionally mixed. Hard to trace a single claim through the pipeline. |
| 3-4 | Significant architectural confusion. Tight coupling between stages. Pipeline is opaque. |
| 1-2 | No clear architecture. Monolithic scripts. LLM calls scattered everywhere. |

**Key checks**:
- All LLM calls go through instructor (or documented provider)
- Prompts are centralized in prompts.py, not inlined in pipeline modules
- The renderer is pure: no LLM calls, no network, no mutation
- The orchestrator is the only module that sequences pipeline stages
- Run artifacts are written at each stage for debuggability
- The public/debug boundary is enforced in exactly one place (renderer)

## 2. Schema & Data Contract (weight: 0.25)

**What to evaluate**: Is the data model well-designed for this problem?

| Score | Description |
|-------|-------------|
| 9-10 | Rich typed model hierarchy. Discriminated unions where appropriate. Validation at boundaries. No `dict` or `Any` escape hatches in the public contract. The schema survives contact with diverse event types. |
| 7-8 | Good use of Pydantic. Most fields are typed. A few `dict` annotations in internal code. Validation covers the important invariants. |
| 5-6 | Basic Pydantic usage. Several `dict` or `Any` annotations. Validation is spotty. Schema is rigid for some event types and loose for others. |
| 3-4 | Minimal schema. Heavy reliance on dicts. Little validation. |
| 1-2 | No schema. Raw dicts everywhere. |

**Key checks**:
- Discriminated unions for claim types (not a single Claim with optional everything)
- Enums for controlled vocabularies (event type, status, claim topic, source role)
- Field validators for business rules (headline length, unique IDs, valid references)
- `extra="forbid"` on public-facing models
- Schema captures event-type-specific needs without becoming a `Map<string, any>`

## 3. Prompt Engineering (weight: 0.25)

**What to evaluate**: Are the prompts well-crafted for reliable structured output?

| Score | Description |
|-------|-------------|
| 9-10 | Prompts are precise, constrained, and well-structured. System prompts define role and rules. User prompts provide grounded data. Temperature and tool choice are intentional. The prompts produce conformant output reliably. |
| 7-8 | Solid prompts with clear instructions. Minor ambiguities or missing constraints. Generally reliable output. |
| 5-6 | Prompts are functional but loose. Some ambiguity about what the LLM should vs shouldn't do. Occasional schema violations. |
| 3-4 | Prompts are vague or overbroad. LLM has too much freedom. Frequent schema non-conformance. |
| 1-2 | Single-shot "generate the whole page" prompts. No structure. |

**Key checks**:
- System prompts define role, rules, and constraints
- User prompts provide the exact data the LLM needs to ground its output
- Stage 3 (composer) receives claim cards with evidence sentences — not asked to research
- Prompts explicitly forbid fabrication ("NEVER invent a statistic, date, location...")
- Revision prompts carry forward previous failures as specific repair actions
- No prompt asks the LLM to generate HTML, CSS, or visual layout

## 4. Error Handling & Robustness (weight: 0.20)

**What to evaluate**: Does the system fail gracefully?

| Score | Description |
|-------|-------------|
| 9-10 | Every failure mode documented in DESIGN.md has a corresponding code path. Artifacts saved on failure. Critics can trigger re-search or revision loops. Timeouts and API errors are caught. |
| 7-8 | Most known failures handled. Artifacts saved on most paths. Some edge cases not covered. |
| 5-6 | Basic try/except blocks. Failures lose intermediate state. No retry or loop-back on evidence gaps. |
| 3-4 | Errors crash the pipeline with no saved state. |
| 1-2 | No error handling. |

**Key checks**:
- Product Critic can trigger re-search when evidence is insufficient
- QA failures trigger bounded revision (not infinite loop)
- Run artifacts persist even when the pipeline fails
- API timeouts are caught and reported, not silently hung
- The system can produce partial output (evidence_limited page) rather than nothing

## Scoring summary

```
Code score = sum(sub_score * weight)
```
