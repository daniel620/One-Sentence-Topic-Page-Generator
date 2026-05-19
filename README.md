# One-Sentence Topic Page Generator

Type **one sentence** about a real, currently-unfolding event. Get back a
**self-contained HTML topic page** — a one-minute orientation surface.

The system is an **agentic editorial workflow with hard safety contracts**.
It researches the open web, extracts and grades evidence, critiques
sufficiency, and composes a grounded page. It is designed for
**editor-assisted** use — not fully autonomous publishing.

## Status

Classification and search query generation generalize across event types.
Evidence acquisition (web page fetching) does not yet generalize reliably —
60-80% of URLs return blocked responses. Five demo events across tech, sports, culture, disaster, and economic categories
are committed. Events with accessible official pages (OpenAI, WHO, FIFA) produce
stronger evidence graphs than those relying on news media alone.

See [`DESIGN.md`](DESIGN.md) for the full architecture, evidence policy,
and honest limitation assessment.

## Run it

```bash
# install
pip install -r requirements.txt

# Full editorial workflow — search, extract, grade, compose, critique, render
python scripts/run_editorial.py "Your one-sentence event here."

# Render from saved fixtures (no API keys needed)
python scripts/generate.py --use-fixtures "<sentence>"

# Debug mode — exposes claim IDs, QA trace, AI curation metadata
python scripts/generate.py --use-fixtures --debug "<sentence>"

# Inspect a run's artifacts
ls runs/<timestamp>/  # hypothesis, evidence_graph, product_critic, page_critic, HTML, etc.
```

## Pre-built examples

| Page | Event Type | Input |
|------|-----------|-------|
| [OpenAI GPT-5.5](output/openai-rolled-out-gpt-5-5-instant-as-the-default-model-in-chatgpt-in-may-2026.html) | tech_launch | "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026." |
| [Eurovision 2026](output/eurovision-2026-is-being-held-in-vienna-from-may-12-to-may-16.html) | cultural_event | "Eurovision 2026 is being held in Vienna from May 12 to May 16." |
| [FIFA World Cup 2026](output/the-2026-fifa-world-cup-kicks-off-at-estadio-azteca-on-june-11-2026.html) | sports_tournament | "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026." |
| [Ebola PHEIC](output/the-who-declared-an-ebola-outbreak-in-the-drc-and-uganda-a-public-health-emergen.html) | disaster | "The WHO declared an Ebola outbreak in the DRC and Uganda a Public Health Emergency of International Concern on May 16, 2026." |
| [UAE Leaves OPEC](output/the-uae-left-opec-on-may-1-2026-ending-six-decades-of-membership-in-the-oil-cart.html) | economic_event | "The UAE left OPEC on May 1, 2026, ending six decades of membership in the oil cartel." |

Open any file directly in a browser — no server needed.

## Architecture

```
one sentence
   ├─► Stage 1A (LLM) — classify event, generate search queries
   │
   ├─► Stage 2 (mixed) — SEARCH → EXTRACT → GRADE
   │     ├─ Tavily search → 20 candidate URLs
   │     ├─ Dual-path extraction: trafilatura + Tavily Extract fallback
   │     ├─ AI source curator (LLM) — classify each source's role
   │     ├─ AI claim extractor (LLM, per-source, parallel) — typed claims
   │     ├─ Evidence grading — full_text_verified / official_snippet /
   │     │   reputable_snippet / weak_snippet
   │     └─ AI contradiction reviewer (LLM)
   │
   ├─► Product Critic (LLM) — evaluate evidence sufficiency
   │     publishable | editor_review | evidence_limited | not_acceptable | re_search
   │
   ├─► Stage 1B (LLM) — plan information architecture
   ├─► Stage 3 (LLM) — compose page from claim cards
   ├─► QA gates (deterministic) — factuality, freshness, event-fit
   ├─► Page Critic (LLM) — evaluate final reader-facing quality
   └─► Renderer (deterministic) — Jinja2 → standalone HTML
```

## Project layout

```
generator/
  schemas.py          # Pydantic data contract
  prompts.py          # all LLM prompts (AI curation, critics, composers)
  orchestrator.py     # EditorialRun — stateful workflow, artifact persistence
  ai_curation.py      # AI source curator, claim extractor, contradiction reviewer
  stage1_understand.py# Stage 1A (hypothesis) + Stage 1B (IA planning)
  stage2_research.py  # Search → Extract → Grade — the evidence layer
  stage3_synthesize.py# Grounded page composer
  qa_gates.py         # Factuality, freshness, event-fit gates
  page_layout.py      # (event_type, status) → PageRecipe table
  renderer.py         # pure function: TopicPageData → HTML
  utils.py            # trafilatura extraction, source scoring, publisher DB
templates/            # Jinja2 — themes, heroes, components
scripts/
  run_editorial.py    # Full editorial workflow entry point
  generate.py         # Render from fixtures (no API), with --debug mode
  clean_fixtures.py   # Post-hoc source filter + QA recalc
  probe_generalization.py  # Test classification on diverse inputs
  verify.py           # Smoke-test all fixtures in both modes
runs/                 # Timestamped artifact directories per run
output/               # Committed pre-built HTML examples
```

## Testing

```bash
pytest tests/               # 96 tests
python scripts/verify.py    # Smoke-test fixtures in public + debug modes
python scripts/probe_generalization.py  # Test classification on 5 diverse inputs
```

## Environment variables

Set in `.env` (gitignored). `.env.example` lists the names only.

```
ANTHROPIC_API_KEY    # All LLM calls (Stages 1-3, AI curation, critics)
TAVILY_API_KEY       # Search + Extract (Tavily search and content extraction)
```
