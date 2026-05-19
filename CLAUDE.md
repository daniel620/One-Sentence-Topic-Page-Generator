# CLAUDE.md — Working memory for this project

> Read first: `BRIEF.md` (the take-home brief), then `DESIGN.md` (current
> design rationale), then this file. Everything else in the repo is the
> current implementation and is open to refactoring or replacement.

## What we're building

A system that takes **one sentence about a real, currently-unfolding event**
and produces a **publishable, reader-facing hot-event topic page** as a
single self-contained HTML file.

A topic page is **not** an article, **not** a search-results summary, and
**not** a debug dashboard. It's a **one-minute orientation surface** that
answers, in order:

1. What happened / is happening now?
2. Why does it matter?
3. What changed?
4. What is the current status?
5. What is still uncertain?
6. What should the reader do next?
7. Where did the critical claims come from?

## Source of truth

- `BRIEF.md` — the take-home assignment. Immutable; do not change it.
- `DESIGN.md` — current public design rationale. Keep it accurate when
  architecture changes.
- `generator/schemas.py` — Pydantic data contract.
- `generator/prompts.py` — all LLM prompts (never inlined elsewhere).
- `generator/page_layout.py` — `(event_type, status) → PageRecipe` table.
- `templates/page.html.j2` + `templates/themes/` + `templates/heroes/` +
  `templates/components/` — deterministic render surface.

## Product principles

1. **Editorial, not debug.** Public mode never shows `claim_id`,
   `source_id`, source scores, QA gate names, repair-action enum values,
   or layout/event-type pills. Those are internal; debug mode opt-in.
2. **Event-fit, not template-fit.** Page shape adapts per event type via
   the recipe table.
3. **Strong above-the-fold.** Hero + deck + dateline + 3-5 key facts.
4. **Trust without theatre.** Citations look like `[Publisher · Date]`,
   not claim IDs and scores.
5. **Freshness or honesty.** Editor's note when confidence is genuinely
   low; nothing when confidence is high.
6. **Deterministic rendering.** LLM owns content; code owns layout.
7. **Unified claim model, not discriminator hierarchy.** Single `Claim` class
   with `claim_attributes` dict for type-specific data. Six typed subclasses
   collapsed into one.

## Architecture (current)

```
sentence
  ├─► Stage 1A (LLM)            EventHypothesis
  ├─► Stage 2  (mixed)          SEARCH → EXTRACT → GRADE → EvidenceGraph
  │     AI source curator + AI claim extractor + deterministic contradiction
  │     pre-filter + AI contradiction reviewer (only pre-filter survivors)
  ├─► Evidence Gate (deterministic)  counts claims/sources/topics (may loop back)
  ├─► Stage 1B (LLM)            EvidenceAwareIA
  ├─► Stage 3  (LLM)            Grounded page composer (degraded mode if thin evidence)
  ├─► QA gates (deterministic)  factuality + freshness + event_fit
  ├─► Repair (deterministic)    strips bad items from TopicPageData (no LLM retry)
  ├─► Fidelity check (deterministic)  cross-references page vs claim texts
  ├─► Renderer (deterministic)  Jinja2 → HTML
  └─► Page Gate (LLM on structured summary)  final verdict (enforced)
```

LLM calls: Stage 1A, AI source curator (batch), AI claim extractors (per-source,
parallel), AI contradiction reviewer (batch, only pre-filter survivors),
Evidence Gate enrichment (only when thin), Stage 1B, Stage 3, Page Gate.
Deterministic: Tavily search, source scoring, source filtering, evidence grading,
claim merging, contradiction detection + pre-filter, Evidence Gate primary,
QA gates, repair, fidelity check, rendering, public/debug boundaries.

## Coding conventions

- Python 3.11+, type hints, Pydantic v2.
- All prompts in `generator/prompts.py`. All models in `generator/schemas.py`.
- `instructor` wraps Anthropic for structured output.
- Renderer is pure: `render_topic_page(data, mode=...) -> str`.
- Every Jinja field access `{% if %}`-guarded; macros use `with context`.
- Component templates never reference `claim_id` directly — they call
  the `cite(item)` macro which respects `is_public`/`is_debug`.
- Templates must be safe to render with partial data.
- Do not commit `.env`, API keys, tokens. `.env.example` lists names only.

## How to run

```bash
pip install -r requirements.txt

# Render from saved fixtures (no API keys)
python scripts/generate.py --use-fixtures "<sentence>"

# Render live (needs ANTHROPIC_API_KEY + TAVILY_API_KEY in .env)
python scripts/generate.py "<sentence>"

# Debug render
python scripts/generate.py --use-fixtures --debug "<sentence>"

# Smoke test (all fixtures, both modes)
python scripts/verify.py

# Unit tests
pytest tests/
```

## Tests

- `tests/test_schemas.py` — claim type validation, EvidenceGraph rules
- `tests/test_registry.py` — component registry guards
- `tests/test_event_type_requirements.py` — per-event-type required
  components; prompt structure
- `tests/test_research.py` — source scoring + claim extraction
- `tests/test_qa_gates.py` — factuality/freshness/event_fit + revision loop
- `tests/test_renderer.py` — public-mode invariants (no leakage) + debug
  invariants (trace appears)

## Done last session

- Removed `schemas.py.backup`, `ResearchEvidence`, `EvidencePoint`,
  `ComponentEvidenceBucket`, `RawResearch` (pipeline now passes
  `EvidenceGraph` directly through stages).
- New `RenderMode` enum (`public` / `debug`).
- New `PageRecipe` table in `generator/page_layout.py`.
- New visual system: four themes (editorial, live-dark, stadium,
  alert), four hero variants (delta, live, schedule, alert).
- Inline editorial citations replace claim-ID/score badges.
- Confidence banner only fires when there is real risk.
- Fixtures rewritten with rich editorial content per event type.
- Tests rewritten to assert public/debug invariants.

## Known limitations / things I'd do next

- Source extraction still uses the 2k-char regex pass. A real reader
  extractor (Trafilatura) + an LLM claim pass per source would improve
  evidence quality materially.
- No image hero. Wikimedia/Unsplash with licensing checks would help
  cultural-event and sports-tournament pages especially.
- No disaster-type demo fixture; the recipe + theme exist but lack
  real content.
- No caching layer; live runs re-fetch every source each time.
- See `DESIGN.md § 6` for the prioritized backlog.
