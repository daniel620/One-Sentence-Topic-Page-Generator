# DESIGN.md — Hot-Event Topic Page Generator

> An honest design document, written against the brief's rubric. It
> describes the actual decisions, the things I deliberately left out,
> the failure modes I defended against, and the things I'd do with
> another week.

## 1. Product decisions

### What is a "topic page"?

I treated "what is a topic page" as the central product question, not a
schema-shape question. The brief intentionally under-specifies it — that
is the test.

The answer I committed to:

> **A topic page is a one-minute orientation surface, not an article and
> not a search-results summary.** Its job is to let a reader become
> conversationally fluent in under a minute. In order, the page must
> answer: *what happened, why it matters, what changed, what is the
> current status, what is still uncertain, what to do next, and where
> the critical claims came from.*

That definition produced six design rules that the rest of the system
follows:

1. **Editorial, not debug.** Public pages never expose `claim_id`,
   numeric source scores, QA gate names, repair-action enum values, or
   layout/event-type pills. Those are internal. Debug mode (an opt-in
   render flag) re-adds them for engineers.
2. **Event-fit, not template-fit.** The page shape changes by event
   type. A tech launch reads as a *delta report*; a live event reads as
   a *now/next guide*; a sports tournament reads as a *match-center*; a
   disaster reads as an *alert surface*. Same data contract, different
   recipe.
3. **Strong above-the-fold.** A typographic hero, a single editorial
   deck line, a dateline, and a 3-5 cell at-a-glance strip with the
   facts a reader most needs in the first ten seconds.
4. **Trust without theatre.** Inline citations are `[Publisher · Date]`
   with `★` for official sources. Numeric source scores stay internal —
   they inform ordering, not what the reader sees.
5. **Freshness or honesty.** If the system isn't confident, the page
   surfaces an editor's note with humanized language (`"claim-to-source
   traceability"`, not `"factuality gate failed"`). If the system *is*
   confident, no warning banner is rendered at all — a fix for a real
   bug in the previous iteration where high-confidence pages were
   warning users anyway.
6. **Deterministic presentation.** The LLM decides structure and copy;
   code owns layout, components, and CSS. The renderer is a pure
   function of `TopicPageData`.

### How the page shape adapts to event type

The single point of variation between event types is the
[`PageRecipe`](generator/page_layout.py) table. A recipe selects:

- the **hero variant** (`delta`, `live`, `schedule`, `alert`),
- the **CSS theme** (`editorial`, `live-dark`, `stadium`, `alert`),
- the **canonical section order**, and
- the **pinned-top sections** (e.g. live tracker for in-progress events).

A specific entry like `(TECH_LAUNCH, CONCLUDED)` produces the editorial
theme with a serif headline, a comparison table at the top, a stat grid
of rollout numbers next, and an action list last. `(LIVE_EVENT, LIVE)`
flips to a dark broadcast-room theme with a pinned live tracker.

Recipes fall back to a per-event-type default if the LLM picks an
unusual `(event_type, status)` combination. That fallback is intentional
— the page should still render correctly when the world is messy.

### What I intentionally left out

- **Image/hero photography.** Real editorial sites lead with images.
  Adding them well requires copyright-clean sourcing and image
  classification. With another week I'd add a "hero image" slot fed by
  Unsplash/Wikimedia with explicit licensing, but a polished
  typographic hero clears the visual bar without it.
- **Live in-page polling.** No JavaScript, no auto-refresh. The page is
  a snapshot with an explicit `as_of` dateline. Re-running the
  generator is the refresh model.
- **Multi-tenant theming / brand customization.** One palette per
  theme is enough to demo event-fit; brand chroming is product, not
  prototype.
- **Print and email variants.** Possible follow-ups but not part of
  the core demo.
- **A REST API.** Out of scope; the brief calls for committed HTML.

## 2. System architecture

```
one sentence
   ├─► Stage 1A (LLM)        — classify event + propose search queries
   ├─► Stage 2  (deterministic) — Tavily search → fetch → claim extraction
   │                              → EvidenceGraph
   ├─► Stage 1B (LLM)        — read evidence, pick IA + layout + confidence
   ├─► Stage 3  (LLM)        — write TopicPageData (structured editorial copy)
   ├─► QA loop  (deterministic) — factuality + freshness + event_fit gates
   │                               bounded resynthesis ≤2 iterations
   └─► Renderer (deterministic) — Jinja2 → HTML, public or debug mode
```

The LLM/deterministic boundary is the most important architectural
choice. **Three of seven steps are LLM**: classifying the event,
planning IA, and writing copy. **Four are deterministic**: searching the
web, scoring sources, running QA gates, and rendering. That boundary is
defensible because:

- The deterministic parts are testable, reproducible, and cheap.
  `pytest` runs every gate in under two seconds with no API calls.
- The LLM is asked to do things LLMs are good at — language, framing,
  classification — and is asked to do them under a typed schema with
  `instructor`, so it can't return a malformed page.
- The renderer is **completely** out of the LLM's reach. If the LLM
  hallucinates a non-existent component type, the schema validator
  rejects the output before it touches HTML.

### Why this stack

| Choice | Why |
|---|---|
| Anthropic Claude (Sonnet) | Reliable structured outputs via `instructor`; long-context for ingesting full evidence packs; cheap enough to run the QA repair loop twice. |
| Tavily | Single-call ranked search with snippets, no scraping infra. Good enough for ≤20 sources per event. |
| Pydantic v2 | The data contract is the system's spine. `instructor` enforces it on every LLM call. |
| Jinja2 | Deterministic, debuggable, no JS runtime. Pure templates are easy to review and change in a code review. |

What I considered and rejected:

- **LangChain / LangGraph / LlamaIndex** — would add abstractions
  without solving a real problem. The pipeline is six clearly-bounded
  steps; a graph framework just adds nouns.
- **React + Tailwind + shadcn** — wouldn't materially improve a
  read-only HTML artifact and would add a build step the reviewers
  don't need. The Jinja templates already use Tailwind-style design
  primitives (custom-property palette + utility-shaped components).
  The renderer is intentionally pluggable; a future React-based
  artifact builder could consume the same `TopicPageData`.
- **Firecrawl / Trafilatura** for full-text extraction — currently we
  truncate to a 2k-char body for cost; with another week I'd swap in
  Trafilatura for richer per-source claim extraction.

## 3. Prompt & data contract

The data contract is in [`generator/schemas.py`](generator/schemas.py).
It has four layers, intentionally:

1. **Evidence layer** — `Source` (with `source_type`, `authority_score`,
   `freshness_score`), the discriminated-union `Claim` family
   (`MetricClaim`, `StatusClaim`, `ScheduleClaim`, `DateClaim`,
   `LocationClaim`, `EntityClaim`), `Contradiction`, and the
   `EvidenceGraph` that contains them all.
2. **Editorial layer** — `KeyFact`, `UIItem`, `UIComponent`, plus
   `Entity` and `TimelineEvent`. This is what the renderer reads.
3. **Stage I/O layer** — `EventHypothesis`, `EvidenceAwareIA`, and the
   top-level `TopicPageData`.
4. **QA layer** — `QAGateResult`, `QARepairAction`.

Every LLM call is wrapped in `instructor` and constrained to a single
Pydantic model. The component registry (`ComponentRegistry`) is the
*only* source of valid component types, and three model-level validators
reject unknown component values at the seams (in `UIComponent`, in
`EvidenceAwareIA.required_components`, and in
`TopicPageData.sections`). The result: if Stage 3 invents a component,
`instructor` retries until it doesn't, and if it can't, the call fails
loud rather than rendering something broken.

The `EvidenceGraph` is the cross-stage backbone. `TopicPageData.sections`
holds editorial content; the `claim_id` on each `UIItem` and `KeyFact`
points back to a claim, which points to sources. The renderer follows
those links to produce inline citations. Public mode never displays the
claim_id itself — only the resolved publisher + date.

### How LLM output stays conformant

Three lines of defense, in increasing strictness:

1. **System prompt** — explicitly lists the allowed component types,
   forbids HTML/CSS, and tells the LLM to use `null` when uncertain
   rather than fabricate.
2. **`instructor` round-trip** — every LLM call passes
   `response_model=<PydanticModel>` and retries with the validation
   error message in-context if the parse fails.
3. **QA gates** — even a well-formed page can have unsupported claims,
   stale sources, or missing required components. The gates flag those
   issues and trigger a bounded revision loop.

## 4. Information sourcing

### How we fetch

`Stage 2` is pure Python:

1. For each of the 3-6 search intents from Stage 1A, call Tavily's
   `search(...)` with `search_depth="advanced"` and `max_results=5`.
2. Deduplicate results by URL, preferring higher Tavily relevance scores.
3. For each surviving result, fetch the URL with `httpx`, strip
   `<script>`/`<style>`/tags, and keep the first ~2k characters of
   readable text.
4. Run rule-based claim extraction (metrics, dates, locations,
   entities) against that text.
5. Score every source: `authority_score` from publisher type,
   `freshness_score` from publish date vs today, `relevance_score`
   from keyword overlap with the event sentence. `overall_score` is a
   weighted blend.
6. Run a small contradiction detector across numeric claims with the
   same unit and date claims for the same event.

The result is an `EvidenceGraph` that contains everything downstream
needs.

### Citations

Editorial inline citations are constructed in
[`generator/renderer.py`](generator/renderer.py) by following
`UIItem.claim_id → Claim → Source` and picking the **best** source
(official first, then by `overall_score`). The reader sees the
publisher name and date, optionally a `★` for official sources, and a
`+N more` chip if multiple sources back the same claim. The full
linked source list sits in a compact footer.

Publisher names and source types come from a hostname allowlist in
[`generator/utils.py`](generator/utils.py) (`KNOWN_PUBLISHERS`). When
Tavily doesn't return a publisher field (it often doesn't), we derive
one from the URL. The same table classifies official vs reputable_media
vs social vs unknown, which then feeds authority scoring.

The three committed demo pages are rendered from fixtures that were
produced by **real live pipeline runs** against Tavily and Anthropic
(see `scripts/refresh_fixture.py`). The cited URLs are the actual URLs
Tavily returned; a reviewer can click any of them in a browser.

### Freshness

The `freshness_gate` enforces a status-dependent threshold:

| Status | Max source age |
|---|---|
| `LIVE` | 3 days |
| `DEVELOPING` | 7 days |
| `UPCOMING` / `SCHEDULED` | 14 days |
| `CONCLUDED` | 90 days |

If a stale source slips past the gate for a strict status, the gate
fails and Stage 3 is re-run with a `STALE_SOURCE` repair action.

### Conflict handling

If `detect_contradictions` finds two sources with materially different
numeric or date claims for the same topic, the renderer surfaces them
in an editorial "What we can't reconcile yet" notice (not a "QA gate
fired" debug card). Reader sees both claims and the publishers behind
each, and we deliberately *don't* try to pick a winner.

### Cost / latency budget

A real run is roughly:

- Stage 1A: ~1.5s, ~1500 tokens out.
- Stage 2: ~3-6s (Tavily latency + parallel URL fetches).
- Stage 1B: ~2s, ~1200 tokens out.
- Stage 3: ~6-10s, ~2500 tokens out, with one revision adding another ~6s.

For a take-home, sub-30s end-to-end is acceptable. For production I'd
add: Stage 2 → Stage 1B → Stage 3 in a streaming pipeline so the page
HTML can render with progressive enhancement as evidence arrives.

## 5. Failure modes

### Hallucination

The single biggest risk. Defenses, in order of priority:

- **System prompt** is explicit about not fabricating metrics or dates
  unless they're in the EvidenceGraph.
- **Allowed-URL list** is injected into the Stage 3 prompt so the LLM
  can't invent a source.
- **`factuality_gate`** scans every numeric/date/status item without a
  `claim_id` and flags it; bounded revision asks Stage 3 to either
  attach a real `claim_id` or drop the specificity. With more
  engineering time I'd also string-match the LLM-written copy against
  the actual `Claim.text` and reject claims that drift too far.

### Ambiguous or off-topic input

Stage 1A returns 3-5 explicit `unknowns` rather than guessing.
Stage 1B's `confidence_summary` and Stage 3's `summary` are required
to flag low-evidence cases. If `confidence == LOW`, the renderer shows
an editor's note instead of pretending certainty.

### Adversarial input

Schema-level: `extra="forbid"` everywhere, plus the component registry
validator, prevents the LLM (or a malicious patch) from injecting
unknown component types or unexpected fields. URL fields are typed as
`HttpUrl`, so a non-URL value is rejected at parse time.

Content-level: the renderer uses Jinja `autoescape=True` for HTML and
XML, so any user-controlled string is escaped before it lands in the
DOM.

What I deliberately did **not** defend against: jailbreaks aimed at
extracting the system prompt. That's a separate problem and the system
prompts here aren't sensitive.

### Failure-mode tradeoffs I accepted

- **No image asset pipeline** means a few event types (cultural events
  especially) feel less visually rich than a magazine-style hub.
- **Tavily snippets** are short, so the rule-based claim extractor
  catches less nuance than a full-page reader extractor would.
- **2-iteration QA cap** means a stubbornly broken page can still ship
  with visible "editor's note" — better than spinning forever, but
  weaker than asking a human reviewer.

## 6. What I'd do with another week

In priority order, with effort estimates:

1. **Better evidence extraction** (~2 days). Swap the 2k-char HTML
   strip for [Trafilatura](https://trafilatura.readthedocs.io/) +
   structured front-matter extraction (byline, publish date, byline).
   Then run a *second*, schema-constrained LLM pass per source to
   extract `Claim`s with the actual evidence sentence, not regex-window
   noise.
2. **Hero imagery via Wikimedia / Unsplash** (~1 day). For
   `live_event` and `sports_tournament` pages especially, an image
   above the hero materially changes the editorial feel. Needs an
   explicit license check and a fallback.
3. **A persistent index** (~0.5 day). Cache evidence by sentence-slug
   so a re-run only re-fetches sources past their freshness threshold;
   makes the live pipeline noticeably cheaper.
4. **Inline source quality strip** (~0.5 day). A small visual hint
   when a section relies heavily on weaker sources — a quiet "1 of 3
   sources is social media" line, not a percentage score.
5. **A React/Tailwind artifact renderer** alongside the Jinja one
   (~2 days). The renderer is already pluggable —
   `TopicPageData` + `PageRecipe` is the data contract. A second
   renderer would let us produce both a self-contained HTML file (for
   CMS embedding) and a polished SPA route (for our own pages) from
   the same data.
6. **Editor-in-the-loop hook** (~1 day). One human-review step
   between Stage 3 and render: a Markdown export of the page that an
   editor can tweak, plus a UI that re-renders on save. This is what
   would make the system actually shippable to a newsroom.
7. **A "disaster" demo** to round out the event-type set (~1 day).
   The recipe and theme already exist; only a real fixture and prompt
   tuning are missing.
8. **Stricter Stage-3 hallucination guard** (~1 day). Stronger
   string-similarity check between the LLM's `UIItem.value` and the
   `Claim.text` it points at. Flag drift, ask for a rewrite.

---

If you stopped reading the rubric and wanted one paragraph: the system
treats the topic page as a *one-minute orientation surface*, not an
article. The LLM does what LLMs are good at — classification and copy —
under a typed schema. Code owns search, scoring, QA, layout, and
presentation. Public output is editorial; internal trace lives behind
a debug flag. The page shape adapts per event type via a small,
explicit recipe table. Everything that matters is testable without an
API key.
