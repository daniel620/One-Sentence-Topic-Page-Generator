# DESIGN.md — LLM-as-Judge Rubric

Evaluate DESIGN.md on these dimensions. Assign a 1-10 score per sub-dimension
with a specific, actionable justification.

Also read BRIEF.md for context on what the brief asks for in the design document.

## 1. Completeness (weight: 0.30)

**What to evaluate**: Does DESIGN.md cover everything BRIEF.md asks for?

BRIEF.md explicitly asks DESIGN.md to cover:
- Product decisions: what belongs on a topic page, how shape adapts to event type, what was left out
- System architecture: pipeline structure, LLM vs deterministic boundaries, why those boundaries
- Prompt & data contract: how fuzzy input becomes structured data, schema, how you keep LLM output conformant
- Information sourcing: how real-world info is pulled, search API, citations, freshness, conflicting sources, cost/latency
- Failure modes: hallucination, ambiguous input, off-topic, adversarial input, what's defended vs acknowledged
- What you'd do with another week: concrete, prioritized

| Score | Description |
|-------|-------------|
| 9-10 | Every section is present and substantive. No hand-waving. The reader understands not just what was built but why every major decision was made. |
| 7-8 | All sections present. Most are substantive. 1-2 sections could use more depth. |
| 5-6 | Most sections present. 2-3 are thin or hand-wavy. Key decisions are described but not defended. |
| 3-4 | Multiple sections missing or very thin. More list than narrative. |
| 1-2 | Missing most sections. No design rationale — just describes what the code does. |

## 2. Clarity & Defensibility (weight: 0.30)

**What to evaluate**: Are decisions explained with rationale, not just described?

| Score | Description |
|-------|-------------|
| 9-10 | Every major decision comes with a "why." Tradeoffs are explicitly weighed. The reader could argue with the choices because they understand the reasoning. Concrete examples (code snippets, diagrams, before/after) illustrate key points. |
| 7-8 | Most decisions have rationale. A few choices are presented as obvious when they're not. Good use of examples. |
| 5-6 | Decisions are listed but not defended. "We chose X" without "because Y" or "the alternative Z would have...". |
| 3-4 | Vague claims without support. "The system is robust" without saying how. |
| 1-2 | No design thinking visible. Just describes what the code does. |

**Key checks**:
- LLM vs deterministic boundary is justified, not just stated
- Prompt design choices have reasoning ("we use system prompts for X because Y")
- Visual/UX choices are connected to product principles
- Architecture diagrams explain the flow, not just decorate
- Alternatives considered are mentioned where relevant

## 3. Honesty (weight: 0.25)

**What to evaluate**: Does the document acknowledge what doesn't work and what's limited?

| Score | Description |
|-------|-------------|
| 9-10 | Limitations are specific, measurable, and prioritized. Failure modes are characterized with real examples. The "what I'd do next" section is honest about what's a quick fix vs what needs fundamental rethinking. |
| 7-8 | Limitations acknowledged with concrete detail. Most failure modes are described. Next steps are prioritized. |
| 5-6 | Limitations mentioned but vague ("could be improved"). Failure modes are generic. Next steps are a wishlist without priority. |
| 3-4 | Only cosmetic limitations acknowledged. Real weaknesses are unmentioned. |
| 1-2 | No limitations acknowledged. Everything is presented as working perfectly. |

**Key checks**:
- Evidence acquisition limitations are specific (e.g., "60-80% block rate" not "some pages don't load")
- Hallucination risk is honestly assessed
- Cost/latency is quantified, not hand-waved
- Generalization is tested and results reported (not just "it should work")
- Next steps are ordered by impact, not by ease

## 4. Consistency with Implementation (weight: 0.15)

**What to evaluate**: Does the code actually do what DESIGN.md says it does?

| Score | Description |
|-------|-------------|
| 9-10 | DESIGN.md accurately describes the current implementation. Architecture diagrams match the code. Claimed capabilities are verifiable in the codebase. |
| 7-8 | Minor discrepancies between DESIGN.md and code. Architecture is mostly accurate. One or two claims don't check out. |
| 5-6 | Several discrepancies. DESIGN.md describes an idealized version that differs from what's implemented. |
| 3-4 | DESIGN.md is significantly out of date or describes a planned system that isn't built. |
| 1-2 | DESIGN.md and code describe different systems. |

**Key checks**:
- Architecture diagram module names match actual files
- LLM call inventory matches actual calls in the code
- Claimed capabilities (e.g., "Product Critic can trigger re-search") are implemented
- "Current limitations" section matches actual known issues
- Confidence band thresholds match the code

## Scoring summary

```
Design score = sum(sub_score * weight)
```
