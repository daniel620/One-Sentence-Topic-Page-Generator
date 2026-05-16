# One-Sentence Topic Page Generator

Type **one sentence** about a real, currently-unfolding event. Get back a
publishable HTML topic page — a one-minute orientation surface that
answers *what happened, why it matters, what changed, what's the current
status, what's still uncertain, what to do next, and where the critical
claims came from.*

The pages are deliberately not the same template with different words
swapped. The renderer picks a **per-event-type layout recipe**: a tech
launch reads as a delta report, a live event reads as a now/next guide,
a sports tournament reads as a match-center.

## Run it

```bash
# 1. install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. render from saved fixtures (no API keys needed — recommended for reviewers)
python scripts/generate.py --use-fixtures \
  "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026."
python scripts/generate.py --use-fixtures \
  "Eurovision 2026 is being held in Vienna from May 12 to May 16."
python scripts/generate.py --use-fixtures \
  "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026."

# Output: output/<slug>.html — self-contained, opens directly in a browser.

# 3. (optional) render from the live pipeline against the open web
cp .env.example .env
# fill in ANTHROPIC_API_KEY and TAVILY_API_KEY
python scripts/generate.py "Your one-sentence event here."

# 3b. (optional) save a live run as a new fixture
python scripts/refresh_fixture.py \
  --sentence "Your one-sentence event here." \
  --fixture tests/fixtures/my_event.json

# 4. debug mode — exposes claim IDs, QA gate trace, layout recipe
python scripts/generate.py --use-fixtures --debug \
  "Eurovision 2026 is being held in Vienna from May 12 to May 16."
```

## Pre-built examples

Open these HTML files directly in any browser — no server needed.

- [`output/openai-rolled-out-gpt-5-5-instant-as-the-default-model-in-chatgpt-in-may-2026.html`](output/openai-rolled-out-gpt-5-5-instant-as-the-default-model-in-chatgpt-in-may-2026.html) — tech launch (delta report)
- [`output/eurovision-2026-is-being-held-in-vienna-from-may-12-to-may-16.html`](output/eurovision-2026-is-being-held-in-vienna-from-may-12-to-may-16.html) — live cultural event (now/next guide)
- [`output/the-2026-fifa-world-cup-kicks-off-at-estadio-azteca-on-june-11-2026.html`](output/the-2026-fifa-world-cup-kicks-off-at-estadio-azteca-on-june-11-2026.html) — sports tournament (match-center / scheduled)

## Architecture in one diagram

```
one sentence
   │
   ├─► Stage 1A (LLM, instructor)   →  EventHypothesis
   │                                   classify + propose search queries
   │
   ├─► Stage 2  (deterministic)     →  Tavily search → reader text →
   │                                   regex claim extraction → EvidenceGraph
   │
   ├─► Stage 1B (LLM, instructor)   →  EvidenceAwareIA
   │                                   final event type, status, components, layout
   │
   ├─► Stage 3  (LLM, instructor)   →  TopicPageData
   │                                   structured editorial content
   │
   ├─► QA loop  (deterministic)     →  factuality + freshness + event_fit
   │                                   bounded resynthesis if any gate fails
   │
   └─► Renderer (deterministic)     →  Jinja2 → standalone HTML
                                       public mode by default; debug mode opt-in
```

Only Stage 1A, Stage 1B, and Stage 3 call an LLM. Everything else is
reproducible from the data — and the renderer is a pure function of
`TopicPageData`, so design changes don't require regenerating evidence.

Full design rationale is in [`DESIGN.md`](DESIGN.md).

## Project layout

```
generator/
  schemas.py          # Pydantic data contract (the single source of truth)
  prompts.py          # all LLM prompts; never inlined elsewhere
  stage1_understand.py# Stage 1A (hypothesis) + Stage 1B (evidence-aware IA)
  stage2_research.py  # Tavily search + EvidenceGraph construction
  stage3_synthesize.py# LLM call that fills TopicPageData
  qa_gates.py         # deterministic factuality/freshness/event_fit gates
  page_layout.py      # per-(event_type, status) PageRecipe table
  renderer.py         # pure function: TopicPageData → HTML
  utils.py            # source scoring + regex claim extraction
templates/
  page.html.j2        # top-level shell
  themes/             # theme CSS bundles (editorial, live-dark, stadium, alert)
  heroes/             # hero variants (delta, live, schedule, alert)
  components/         # one Jinja partial per registry component type
scripts/
  generate.py         # generate one page; --use-fixtures or live
  verify.py           # render every fixture and check public-mode invariants
tests/                # unit tests; fixtures used by generate/verify
output/               # committed pre-built HTML examples
```

## Testing

```bash
pytest tests/          # 81 tests across schemas, registry, research, QA, renderer
python scripts/verify.py  # smoke-test renders every fixture in both modes
```

## What's intentionally out of scope

- Hosting, deployment, Docker — the brief asks for committed HTML and we
  ship committed HTML.
- Auth / persistence — not needed for a topic page artifact.
- Image fetching / hero imagery — possible follow-up, not required.

## Environment variables

Used only when running the live pipeline (not for `--use-fixtures`):

```
ANTHROPIC_API_KEY    # for Stage 1A, Stage 1B, Stage 3 LLM calls
TAVILY_API_KEY       # for Stage 2 web search
```

Place them in `.env` (gitignored). `.env.example` lists the names only.

Never commit `.env` or any keys.
