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

# Quick render from saved fixtures (no API keys needed)
python scripts/generate.py --use-fixtures "<sentence>"

# Debug mode — exposes claim IDs, QA trace, AI curation metadata
python scripts/generate.py --use-fixtures --debug "<sentence>"

# Inspect a run's artifacts
ls runs/<timestamp>/  # hypothesis, evidence_graph, evidence_gate, page_gate, HTML, etc.
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
   │
   ├─► classify (LLM) — event type + search queries
   │     6 types: tech_launch, sports_tournament, cultural_event,
   │     live_event, disaster, economic_event
   │
   ├─► research (mixed) — SEARCH → EXTRACT → GRADE → CURATE
   │     ├─ Tavily search → 20 candidate URLs
   │     ├─ Dual-path extraction: trafilatura (primary) + Tavily Extract (fallback)
   │     ├─ AI source curator (LLM) — role per source
   │     ├─ AI claim extractor (LLM, per-source, parallel) — typed claims
   │     ├─ Evidence grading — full_text_verified | official_snippet |
   │     │   reputable_snippet | multi_sourced | weak_snippet
   │     ├─ AI contradiction reviewer (LLM)
   │     └─ Dynamic official-source discovery fallback
   │
   ├─► Evidence Gate (LLM) — evidence sufficiency check
   │     publishable | editor_review | evidence_limited |
   │     not_acceptable | re_search (loops to research, ≤3 rounds)
   │
   ├─► plan (LLM) — information architecture from evidence
   ├─► compose (LLM) — TopicPageData from claim cards
   │     Full mode (strong evidence) or degraded mode (thin evidence)
   │
   ├─► QA + repair (deterministic)
   │     Factuality, freshness, event-fit, fidelity gates
   │     Repair: strips unsupported claims, conflicting sides, empty sections
   │     Bounded resynthesis (≤2 rounds)
   │
   ├─► Page Gate (LLM) — final acceptance from structured summary
   │
   └─► render (deterministic) — Jinja2 → standalone HTML
         Public mode (editorial) or debug mode (full trace)
```

## Project layout

```
generator/
  schemas.py          # Pydantic data contract (6 event types, 5 evidence grades)
  prompts.py          # All LLM prompts — classify, curate, plan, compose, critics
  orchestrator.py     # EditorialRun — stateful 6-phase workflow, artifact persistence
  classify.py         # Stage 1: event type + search query generation
  research.py         # Stage 2: Tavily search → extract → grade → curate
  curate.py           # AI source curator + AI claim extractor + AI contradiction reviewer
  critic.py           # Evidence Gate + Page Gate
  plan.py             # Stage 3: evidence-aware information architecture
  compose.py          # Stage 4: claim-card-grounded page composition
  quality.py          # QA gates: factuality, freshness, event-fit, fidelity
  repair.py           # Deterministic repair: strip unsupported claims, conflicting sides
  verify_facts.py     # Cross-reference page values against claim card values
  contradictions.py   # Contradiction detection and pre-filtering
  page_layout.py      # (event_type, status) → PageRecipe table
  render.py           # Pure function: TopicPageData → HTML (public or debug)
  utils.py            # trafilatura extraction, source scoring, KNOWN_PUBLISHERS
templates/            # Jinja2 — 4 themes, 4 hero variants, 10 components
scripts/
  run_editorial.py    # Full editorial workflow entry point
  generate.py         # Render saved fixtures (no API keys needed)
  verify.py           # Smoke-test all fixtures in public + debug modes
tests/
  test_schemas.py, test_qa_gates.py, test_renderer.py,
  test_orchestrator.py, test_repair.py, test_research.py,
  test_event_type_requirements.py, test_registry.py
  fixtures/           # 3 saved EvidenceGraph + TopicPageData bundles
runs/                 # Timestamped artifact directories per EditorialRun
output/               # 5 committed pre-built HTML examples
```

## Testing

```bash
pytest tests/               # 95 tests
python scripts/verify.py    # Smoke-test all fixtures in public + debug modes
```

## Environment variables

Set in `.env` (gitignored). `.env.example` lists the names only.

```
ANTHROPIC_API_KEY    # All LLM calls (classify, curate, plan, compose, critics)
TAVILY_API_KEY       # Search + Extract (Tavily search and content extraction)
```
