# DESIGN.md — Design rationale for the topic page generator

Current as of the May 2026 iteration. This describes what IS, not what WAS.

## 1. Product principles

1. **Editorial, not debug.** Public mode never shows `claim_id`, `source_id`,
   source scores, QA gate names, repair-action enum values, or layout/event-type
   pills. Those are internal; debug mode opt-in.
2. **Event-fit, not template-fit.** Page shape adapts per event type via the
   recipe table in `generator/page_layout.py`.
3. **Strong above-the-fold.** Hero + deck + dateline + 3-5 key facts.
4. **Trust without theatre.** Inline citations are `Publisher · Date`
   with star for official sources. Numeric scores are internal.
5. **Honesty proportional to evidence quality.** Pages with solid evidence
   and clean QA show no confidence banner. Pages with genuine gaps show a
   specific, useful editor's note. The banner never fires on a HIGH-
   confidence page just because QA data is absent.
6. **Deterministic rendering.** The LLM produces structured data. Code
   owns layout, components, CSS, and public/debug boundaries.

## 2. Architecture (current, May 2026)

```
one sentence
   |
   +-- classify (LLM)              -> EventHypothesis
   |     event type, freshness need, 3-6 search queries (incl. official source)
   |
   +-- research (mixed)            -> EvidenceGraph
   |     +-- SEARCH: Tavily search -> up to 20 candidate URLs
   |     +-- Source scoring (deterministic: hostname table + authority/freshness)
   |     +-- Source quality filter (authority floor + per-type caps)
   |     +-- AI source curator (LLM, batch)
   |     |     public_claim_source / supporting_context / background_only /
   |     |     debug_only / reject / needs_review
   |     +-- Dual-path extraction: trafilatura (primary) + Tavily Extract (fallback)
   |     +-- AI claim extractor (LLM, per-source, parallel) -> unified Claim objects
   |     |     with claim_attributes dict for type-specific data
   |     +-- GRADE: full_text_verified | official_snippet | reputable_snippet | multi_sourced | weak_snippet
   |     +-- Claim merging (topic + word-overlap across sources)
   |     +-- Contradiction detection (deterministic)
   |     +-- Contradiction pre-filter (deterministic: auto scope_difference
   |     |     when claims have different topics or types)
   |     +-- AI contradiction reviewer (LLM, batch — only for pre-filter survivors)
   |     +-- public_evidence_view filtered by grade + source role
   |
   +-- Evidence Gate (deterministic by default) -> publishable | editor_review |
   |     evidence_limited | not_acceptable | re_search (loops to research)
   |     Uses numeric thresholds: claim count, official sources, topic coverage.
   |     LLM enrichment only for search query suggestions when evidence is thin.
   |
   +-- plan (LLM)                   -> EvidenceAwareIA
   |     final event type, event status, page thesis, mandatory components,
   |     layout style, confidence summary
   |
   +-- compose (LLM)                -> TopicPageData
   |     Grounded page composer — receives claim cards, composes sections.
   |     Editorial framing is free; hard facts must come from cards.
   |     Degraded mode when evidence is limited: conservative with stats,
   |     prefer timeline/entity/action over stat_grid, add qualifiers.
   |
   +-- QA gates (deterministic)     -> factuality + freshness + event_fit
   |     Simple unweighted average. Confidence bands: >=0.85 HIGH, >=0.60 MEDIUM,
   |     <0.60 LOW. Respects AI contradiction review verdicts (only
   |     real_uncertainty contradictions deduct from factuality).
   |
   +-- Repair (deterministic)       -> strips conflicting, unsupported, and
   |     untraceable items directly from TopicPageData. No LLM re-composition.
   |     Fills missing required components with placeholders.
   |     Recalculates confidence based on how many items were removed.
   |
   +-- Fidelity check (deterministic) -> cross-references page UIItem values
   |     against claim texts. Numeric values not present in the claim are
   |     flagged. Items below threshold are stripped. No LLM call.
   |
   +-- Render (deterministic)       -> Jinja2 -> standalone HTML
   |     Public mode: editorial citations, no claim_ids, no debug panel.
   |     Debug mode: full trace including AI source roles, claim_ids,
   |     contradiction verdicts, QA gate details.
   |
   +-- Page Gate (LLM on structured summary) -> publishable | editor_review |
         not_acceptable. Receives ~800-token structured page summary (not raw
         HTML). Verdict enforced: not_acceptable sets run status to DRAFT.
```

### Orchestration (`generator/orchestrator.py`)

```
sentence -> EditorialRun.execute()
   +-- Phase 1: classify (understand the event)
   +-- Phase 2: research (evidence) <----+
   |     +-- Evidence Gate --------------+ (re-search up to 3 rounds)
   +-- Phase 3: plan + compose (page from claim cards)
   |     Degraded mode when evidence is limited
   +-- Phase 4: QA + deterministic repair + fidelity check
   |     (no LLM re-composition — bad content stripped, not retried)
   +-- Phase 5: render -> HTML
   +-- Phase 6: Page Gate on structured summary -> final verdict (enforced)
```

### Key modules

| Module | Role |
|---|---|
| `generator/classify.py` | Stage 1A: LLM event classification + search queries |
| `generator/research.py` | Evidence supply chain: search, fetch, extract, grade |
| `generator/curate.py` | AI source curation + claim extraction |
| `generator/contradictions.py` | Contradiction detection, pre-filter, AI review |
| `generator/critic.py` | Evidence Gate (deterministic) + Page Gate (LLM on summary) |
| `generator/plan.py` | Stage 1B: LLM information architecture planning |
| `generator/compose.py` | Stage 3: LLM page composition from claim cards |
| `generator/quality.py` | QA gates: factuality, freshness, event_fit |
| `generator/repair.py` | Deterministic page repair (strips bad content) |
| `generator/verify_facts.py` | Page-to-claim fidelity cross-reference |
| `generator/render.py` | Pure renderer: TopicPageData -> HTML |
| `generator/schemas.py` | Pydantic data contract (unified Claim model) |
| `generator/prompts.py` | All LLM prompts (never inlined elsewhere) |
| `generator/page_layout.py` | (event_type, status) -> PageRecipe table |

### Entry point

`generator/orchestrator.run_pipeline(sentence) -> TopicPageData` is the single
entry point, exported from `generator/__init__.py`.

### Artifacts

Every run writes to `runs/<timestamp>/`:
`hypothesis.json`, `evidence_graph.json`, `product_critic.json`,
`ia_plan.json`, `topic_page.json`, `qa_report.json`, `repair_summary.json`,
`fidelity_report.json`, `page_critic.json`, `page.html`, `summary.json`.

## 3. Data contract

### Why a unified Claim model instead of typed subclasses

The original design used a Pydantic discriminator hierarchy: `MetricClaim`, `DateClaim`,
`StatusClaim`, `ScheduleClaim`, `LocationClaim`, `EntityClaim` — each with typed fields
(`MetricClaim.value`, `DateClaim.date_value`, etc.).

This was replaced with a single `Claim` model where type-specific data lives in
`claim_attributes: dict[str, Any]`. The tradeoff:

**What we gained:**
- Schema reduced from 7 classes to 1 (~60% less code)
- Adding a new claim attribute is a one-line change (add a key to the dict)
- No discriminator overhead at serialization boundaries
- The composer, renderer, QA gates, and repair module all treat claims uniformly

**What we gave up:**
- No compile-time validation that a `metric` claim has `value` and `unit`
- String-key access (`claim_attributes.get("value")`) can silently return `None` if the key is misspelled

**Why this is defensible for this project's scale:**
The type-specific fields are consumed in exactly two places — contradiction detection
(`contradictions.py`) and unsupported-claim eviction (`repair.py`). Both use `.get()`
with defaults. Every other consumer (composer, renderer, QA, fidelity, Page Gate)
treats claims uniformly through `claim_id`, `text`, `evidence_sentence`, and `source_ids`.
A TypedDict or `Literal` key constraint would add complexity for two consumers.
For a production system with more claim types, we'd add a `ClaimAttributes` TypedDict
per claim type.

### Core enums

```python
class EventType(str, Enum):
    TECH_LAUNCH = "tech_launch"
    LIVE_EVENT = "live_event"
    SPORTS_TOURNAMENT = "sports_tournament"
    CULTURAL_EVENT = "cultural_event"
    DISASTER = "disaster"
    ECONOMIC_EVENT = "economic_event"

class EventStatus(str, Enum):
    LIVE = "live"           UPCOMING = "upcoming"
    CONCLUDED = "concluded" DEVELOPING = "developing"
    SCHEDULED = "scheduled"

class ComponentType(str, Enum):
    KEY_FACTS = "key_facts"           STAT_GRID = "stat_grid"
    COMPARISON_TABLE = "comparison_table"  LIVE_TRACKER = "live_tracker"
    ACTION_LIST = "action_list"       TIMELINE = "timeline"
    ENTITY_LIST = "entity_list"       SOURCE_LIST = "source_list"
    UNCERTAINTY_BOX = "uncertainty_box"  CONFIDENCE_BANNER = "confidence_banner"

class EvidenceGrade(str, Enum):
    FULL_TEXT_VERIFIED = "full_text_verified"
    OFFICIAL_SNIPPET = "official_snippet"
    REPUTABLE_SNIPPET = "reputable_snippet"
    MULTI_SOURCED = "multi_sourced"
    WEAK_SNIPPET = "weak_snippet"
```

### Claim

```python
class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=500)
    claim_type: ClaimType
    claim_topic: ClaimTopic = ClaimTopic.OTHER
    source_ids: list[str] = Field(min_length=1, max_length=20)
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    freshness: str = Field(default="fresh", max_length=20)
    evidence_sentence: str = Field(default="", max_length=600)
    public_claim_eligible: bool = False
    evidence_grade: EvidenceGrade = EvidenceGrade.WEAK_SNIPPET
    claim_attributes: dict[str, Any] = Field(default_factory=dict)
    # Keys by claim_type:
    #   metric: value, unit, direction, evidence_snippet
    #   date: date_value (ISO str)
    #   schedule: event_datetime (ISO str), timezone, event_name
    #   location: location
    #   entity: entity_name, entity_role
    #   status: status, observed_at (ISO str), source_evidence
```

### EvidenceGraph

```python
class EvidenceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_hypothesis: str = Field(min_length=1, max_length=300)
    sources: list[Source] = Field(default_factory=list, max_length=30)
    claims: list[Claim] = Field(default_factory=list, max_length=120)
    contradictions: list[Contradiction] = Field(default_factory=list, max_length=10)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=5)
    last_updated: datetime | None = None
```

### TopicPageData

```python
class TopicPageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: EventType
    status: EventStatus
    confidence: ConfidenceLevel
    headline: str = Field(min_length=1, max_length=120)  # ≤12 words enforced
    deck: str | None = Field(default=None, max_length=240)
    summary: str = Field(min_length=1, max_length=1000)
    key_facts: list[KeyFact] = Field(default_factory=list, max_length=6)
    key_entities: list[Entity] = Field(default_factory=list, min_length=1)
    timeline: list[TimelineEvent] = Field(default_factory=list, min_length=1)
    layout_style: LayoutStyle = LayoutStyle.HERO_FOCUS
    sections: list[UIComponent] = Field(default_factory=list, min_length=1, max_length=10)
    evidence_graph_ref: EvidenceGraph | None = None  # stripped in public render
    qa_results: list[QAGateResult] = Field(default_factory=list, max_length=5)
    last_updated: datetime | None = None
```

### UIComponent and UIItem

```python
class UIComponent(BaseModel):
    component_type: ComponentType
    title: str = Field(min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=260)
    items: list[UIItem] = Field(default_factory=list, min_length=1, max_length=24)

class UIItem(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=260)
    detail: str | None = Field(default=None, max_length=500)
    link_url: HttpUrl | None = None
    claim_id: str | None = Field(default=None, max_length=100)
    # claim_id links this item to a Claim in EvidenceGraph.
    # Stripped in public render; used for citations and traceability.
```

### Provider choices and rationale

| Component | Provider | Why |
|---|---|---|
| LLM (all calls) | Anthropic (Claude Sonnet 4.5) via `instructor` | Structured output enforcement with Pydantic response_model on every call. Chosen over OpenAI for stronger schema adherence in constrained generation mode. |
| Web search | Tavily Search API | Returns structured results with title, URL, content snippet, and published_date. `search_depth="advanced"` for higher recall on niche event topics. |
| Content extraction (primary) | trafilatura | Best-in-class open-source article text extraction. Handles most news sites and blogs. Falls back to regex HTML stripping for JS-heavy pages. |
| Content extraction (fallback) | Tavily Extract API | Server-side headless browser extraction for pages where httpx+trafilatura fails (JS-rendered, paywalled, bot-blocked). |
| Structured output | `instructor` + Pydantic v2 | Every LLM call returns a typed Pydantic model. No raw strings parsed; no regex on LLM output. |
| HTML rendering | Jinja2 | Template engine with auto-escaping. Separates editorial data from presentation. Chosen for simplicity and Python ecosystem fit. |

## 4. Quality control

### Three-layer defense

1. **Evidence Gate** (after research): counts claims, sources, topics.
   Blocks or downgrades when evidence is thin. Loops back for re-search.

2. **QA + Repair** (after composition): gates check factuality (claim traceability,
   contradictions), freshness (source recency), event_fit (required components).
   Repair strips bad items deterministically — no LLM re-composition.

3. **Fidelity + Page Gate** (before/after render): fidelity check cross-references
   page values against claim texts. Page Gate reviews structured page summary
   (~800 tokens, not raw HTML) and its verdict is enforced.

### Contradiction handling

Three-stage pipeline:
1. **Detect**: compare numeric/date claims for conflicts (>10% difference)
2. **Pre-filter** (deterministic): auto-classify as scope_difference when
   claims have different claim_topic or claim_type
3. **AI review** (LLM): only for claims that pass the pre-filter

Only `real_uncertainty` contradictions appear in public uncertainty boxes.

## 5. Rendering

Pure function: `render_topic_page(page, mode="public") -> str`.

- `(event_type, status)` maps to a `PageRecipe` (hero variant, CSS theme, section order)
- Four themes: editorial, live-dark, stadium, alert
- Four hero variants: delta, live, schedule, alert
- Inline citations: `Publisher · Date` with star for official sources
- Confidence banner only when there is genuine risk (QA failures or LOW confidence)
- `claim_attributes` dict values are never rendered — only base Claim fields

## 6. Provider choices and rationale

| Component | Provider | Why this over alternatives |
|---|---|---|
| LLM | Anthropic Claude Sonnet 4.5 via `instructor` | `instructor` enforces Pydantic `response_model` on every call — no raw strings, no regex parsing of LLM output. Chosen over OpenAI because `instructor` with Anthropic provides stronger schema adherence in constrained generation mode. Sonnet 4.5 offers the best latency/capability ratio for this pipeline's 10+ calls. |
| Web search | Tavily Search API | Returns structured results (title, URL, content snippet, published_date) without requiring HTML parsing. `search_depth="advanced"` improves recall for niche topics. Chosen over Brave/SerpAPI because Tavily's Extract API provides a complementary server-side headless browser for pages our httpx client can't reach. |
| Content extraction (primary) | trafilatura | Best-in-class open-source article text extraction. Handles most news sites and blogs. Comparable to newspaper3k but faster and more maintainable. |
| Content extraction (fallback) | Tavily Extract API | Server-side headless browser extraction for JS-rendered, paywalled, or bot-blocked pages where httpx+trafilatura fails. Using the same provider for search and extraction simplifies API key management. |
| Structured output | `instructor` + Pydantic v2 | Every LLM call returns a typed Pydantic model. The alternative (asking for JSON and parsing it) requires prompt-level format instructions and fragile regex extraction of malformed JSON. `instructor` handles retries, validation, and error recovery. |
| HTML rendering | Jinja2 | Template engine with auto-escaping, template inheritance, and `{% include %}` for component reuse. Chosen over React/Next.js because the output is a single self-contained HTML file with no JavaScript dependency — it opens directly in a browser with no build step. |

## 7. Cost and latency

### LLM call budget

| # | Stage | Model | max_tokens | Parallel? |
|---|---|---|---|---|
| 1 | Stage 1A (classify) | Sonnet 4.5 | 1,500 | Serial |
| 2 | AI Source Curator (batch) | Sonnet 4.5 | 2,000 | Serial |
| 3 | AI Claim Extraction | Sonnet 4.5 | 2,000 | **Parallel** (up to 12 workers) |
| 4 | AI Contradiction Reviewer | Sonnet 4.5 | 1,000 | Serial (only when contradictions exist) |
| 5 | Evidence Gate enrichment | Sonnet 4.5 | 600 | Serial (only when evidence is thin) |
| 6 | Stage 1B (plan) | Sonnet 4.5 | 1,500 | Serial |
| 7 | Stage 3 (compose) | Sonnet 4.5 | 8,000 | Serial (largest single call) |
| 8 | Page Gate | Sonnet 4.5 | 2000 | Serial |

**Typical run (10 public sources): 16 LLM calls** — 10 parallel claim extractions + 6 serial calls.
Stage 3 (compose) at 8,000 max_tokens dominates the token budget.

### API call budget

| API | Calls per run | Notes |
|---|---|---|
| Tavily Search | 4-7 | 3-6 search queries + optional official-source enrichment |
| Tavily Extract | 1 | Batch call for all public-eligible URLs |
| HTTP fetch (trafilatura) | 5-20 | One per candidate source, run in parallel |

### Latency

| Phase | Dominant cost | Estimate |
|---|---|---|
| Classify (LLM) | 1 serial call | ~2s |
| Search (Tavily) | 4-7 parallel calls | ~0.5s |
| Source curation (LLM) | 1 serial call | ~2s |
| Content fetch (HTTP) | 5-20 parallel requests | ~1s |
| Claim extraction (LLM) | 10 parallel calls (max 12 workers) | ~2s |
| Contradiction review (LLM) | 1 serial call | ~1s |
| Plan + Compose (LLM) | 2 serial calls | ~4s |
| QA + Repair + Fidelity (code) | Deterministic | ~0.2s |
| Render (code) | Jinja2 | ~0.1s |
| Page Gate (LLM) | 1 serial call | ~1s |
| **Total** | | **~15-18 seconds** |

With up to 3 research rounds (when Evidence Gate triggers re-search), worst-case latency is ~25-30 seconds.

### Caching

**No caching layer exists.** Every run re-fetches all sources and re-runs all LLM calls.
Artifacts are persisted to `runs/<timestamp>/` for debugging but never read back.
Adding a cache keyed on `(sentence, today)` would reduce repeat-run latency to ~0.5s
(render only) and is the highest-impact latency optimization.

## 8. Failure modes and defenses

### What happens when the LLM hallucinates?

The system has **seven layers of defense** against hallucinated claims reaching the reader:

| # | Defense | Type | What it catches |
|---|---|---|---|
| 1 | Evidence sentence window check (`curate.py:232-239`) | STRUCTURAL | Fabricated evidence_sentence with no 30-char match in source text → claim downgraded to debug-only |
| 2 | Sliding-window verification (`research.py:335-353`) | HEURISTIC | 40-char window with generic-phrase skip in source content |
| 3 | Unsupported metric eviction (`repair.py:70-90`) | STRUCTURAL | Metric claims with no evidence_snippet or source_ids → stripped from page |
| 4 | Contradiction-side eviction (`repair.py:42-67`) | STRUCTURAL | Both sides of real_uncertainty contradictions → stripped from page |
| 5 | Item-to-claim numeric fidelity (`verify_facts.py:59-98`) | STRUCTURAL | Page values containing numbers not in the claim → stripped |
| 6 | QA factuality gate (`quality.py:140-277`) | STRUCTURAL | 7 structural checks including global numeric scan across entire evidence graph |
| 7 | Page Gate final review (`critic.py:255-300`) | PROMPT-BASED | LLM reviews structured page summary for obvious defects |

**What slips through:** A hallucinated claim where the LLM (a) invents a plausible number,
(b) constructs an evidence_sentence whose 30-char window appears in source text, and
(c) includes source_ids. This passes gates 1-2. If no other source reports a conflicting
number, gate 4 doesn't fire. If the composer uses the exact hallucinated number, gate 5
passes. Gate 6 checks structural validity (claim_id resolves, metric has snippet) but
not numerical accuracy. **The system validates chain-of-custody, not ground truth.**
This is the fundamental limitation of any system that can't independently verify facts.

### What happens with ambiguous, off-topic, or adversarial input?

| Input | Behavior |
|---|---|
| Empty string | Rejected by `classify.py:141-143` (`ValueError`) |
| "banana" | LLM classifies as some EventType, generates search queries containing "banana." Tavily returns no relevant results. Evidence Gate returns `not_acceptable` (<2 public claims). Page is rendered in degraded mode with a confidence caveat. |
| "tell me a joke" | Same path as "banana" — LLM may classify as CULTURAL_EVENT. Search results are irrelevant. Evidence Gate blocks. |
| Off-topic essay (500 words) | Stage 1A prompt is designed for single sentences. The LLM may extract partial event signals or fail to produce structured output. Not defended against — acknowledged limitation. |
| Sentence about a fictional event ("Hogwarts wins Quidditch World Cup 2026") | Tavily returns no credible sources. Evidence Gate returns `not_acceptable`. Page rendered in degraded mode. |
| Sentence with contradictory information ("Earthquake in Tokyo kills 500 people, government says no casualties") | Both claims extracted. Contradiction detection fires. AI reviewer classifies as `real_uncertainty`. Both sides stripped by repair. Uncertainty box shows the conflict editorially. |

**What's defended:** Empty input (rejected), nonsense input (Evidence Gate blocks), fictional events (no credible sources → `not_acceptable`), internal contradictions (detected and surfaced editorially).

**What's not defended:** Very long input (no truncation), sentences designed to manipulate event classification (e.g., injecting "disaster" keywords), prompt injection via the input sentence flowing into LLM context. These are acknowledged limitations.

### Known failure modes summary

1. **Hallucinated claim with plausible evidence** — can pass all structural gates
2. **Evidence acquisition for novel/unfamiliar domains** — 3/4 holdout events get 0 public claims
3. **Source concentration** — single source can dominate claim pool (8/12 claims from one outlet)
4. **No prompt-injection defense** — the input sentence flows directly into LLM context
5. **No input length limit** — very long inputs may break Stage 1A classification
6. **The 40-char window is a heuristic** — an LLM that knows the check can construct compliant fabrications (though this requires adversarial knowledge of the code)

## 9. What I'd do with another week

The system works for events with accessible official pages. That's the ceiling.
Every improvement below pushes that ceiling higher or makes the system safer
to operate. Ordered by impact, not by ease.

### 1. Solve the evidence acquisition bottleneck

This is the single issue that separates the three demo events from everything
else. 60-80% of URLs return blocked responses across diverse event types.
Until this is solved, the system only works well for events covered by
press releases, Wikipedia, and open-access news.

The fix isn't one thing — it's a layered strategy: rotating user agents,
headless browser fallback for blocked pages, respect for robots.txt, RSS
feed ingestion for news sites, and a persistent cache keyed on URL + fetch
date so re-runs don't re-hit the same walls. Each layer improves the yield
for a different class of blocked content. Together they could move the
system from "works for 3/10 events" to "works for 7/10."

### 2. Add an editor-in-the-loop step

The system should not publish autonomously. The minimum viable shipping path
is a Markdown export of the composed page that a human editor can review and
edit, with the page re-rendering on save. This one change converts the
system from "AI generates pages" to "AI drafts pages, humans approve them"
— which is the difference between a prototype and something a newsroom would
actually use.

The editor review surface should show: the original sentence, the evidence
graph summary, any fidelity warnings, and the composed page content. The
editor can edit any field, remove claims, or reject the page entirely.

### 3. Build the trust and transparency layer

Right now the confidence banner is binary and vague. A reader-facing trust
layer would show: which claims are backed by official sources vs news media,
whether contradictory claims exist and why they're unresolved, and a source
quality summary that's editorial ("6 of 12 claims from official sources")
rather than internal ("authority_score mean 0.73").

This also means fixing the "coming soon" placeholder problem — degraded
pages should be gracefully shorter, not dotted with visibly machine-generated
empty sections. A thin page with honest caveats is better than a padded page
with placeholder text.

### 4. Expand the event taxonomy thoughtfully

The UAE-OPEC example proved the taxonomy needs to grow beyond 6 types. But
adding types one by one is a losing strategy — you'll always be one behind.
The right approach is to study a few dozen real news events and identify the
dimensions that actually drive page shape differences (temporal urgency,
data density, entity complexity, emotional register) rather than guessing
from domain labels. The recipe table should be driven by these dimensions,
not by an ever-growing enum.

### 5. Make the system testable and observable

No E2E tests exist that exercise the full pipeline with recorded API
responses. No integration tests verify that a fidelity warning actually
prevents a hallucinated number from reaching the page. Adding these would
make the system safe to refactor — right now, the only way to know if a
change breaks something is to run the live pipeline and read the output.

Observability is equally thin: there's no dashboard showing evidence yield
by event type, no alert when the official-source discovery fallback fires,
no way to compare two runs of the same sentence side by side. These are the
tools that would let someone operate this system in production.

### 6. Reorganize the codebase by concern

The current flat `generator/` directory with 17 files was the right call for
prototyping — zero friction to create a new module and wire it in. But it now
obscures the architecture. `quality.py`, `repair.py`, `verify_facts.py`, and
`contradictions.py` are really one QA subsystem. `research.py` and `curate.py`
are one evidence pipeline. `utils.py` is a junk drawer.

The right shape is probably package-by-concern, five packages mirroring the
pipeline phases:

```
generator/
  schemas.py, prompts.py          # cross-cutting: data contract + LLM surface
  understanding/                  # classify.py, plan.py — figure out the event
  evidence/                       # research.py, curate.py, extraction, publishers — get the facts
  composition/                    # compose.py — write the page
  quality/                        # gates, repair, fidelity, contradictions — verify
  rendering/                      # render.py, page_layout.py, themes, heroes — present
```

This isn't just aesthetic. The current structure makes it hard to see which
modules are allowed to import which others. Packages enforce the dependency
direction: `evidence → schemas`, `composition → evidence`, `quality → schemas`.
The rendering package should import nothing from the pipeline — it's a pure
function of `TopicPageData`.

This is deferred because while refactoring is mechanically straightforward,
doing it without E2E safety tests (see #5) risks breaking the pipeline subtly.

### What I wouldn't spend time on

- **More themes or hero variants.** Four themes × four heroes already covers
  the event-type space. Visual polish matters but diminishing returns kick in
  fast after the first few.
- **A React/Tailwind renderer.** The Jinja2 renderer produces self-contained
  HTML that opens in any browser. A JS framework adds a build step without
  adding reader value for a static page.
- **Multi-language support.** Important for production but orthogonal to the
  core challenge of generating trustworthy pages from evidence.
- **API or hosting.** The brief is clear: committed HTML files. Deployment
  infrastructure is a separate problem.

## 10. Changes from previous version

- Removed ClaimUnion discriminator hierarchy (6 typed subclasses -> unified Claim)
- Replaced LLM Product Critic with deterministic Evidence Gate
- Replaced LLM Page Critic (on raw HTML) with Page Gate (on structured summary)
- Removed LLM revision loop; added deterministic repair + fidelity check
- Added contradiction pre-filter (deterministic, catches scope differences)
- Added official-source search query generation
- Added degraded page mode for thin evidence
- Fixed dead-code Tavily snippet fallback
- Wired source quality filter into main pipeline
- AI curator now wins for unknown-domain sources
- Added Google Fonts loading, metadata tags, accessibility styles
- Added 12 repair tests + 6 orchestrator E2E tests
- Added provider rationale and cost/latency analysis

## 11. Custom example inputs and what they revealed

### 11.1 Ebola PHEIC declaration

**Input:** "The WHO declared an Ebola outbreak in the DRC and Uganda a Public Health Emergency of International Concern on May 16, 2026."

Chosen to fill the disaster event type gap — the original three examples (tech launch, cultural event, sports tournament) left no coverage for the `alert` theme and `alert` hero variant that were built into the recipe table but had no demo fixture. This input also tests the system against a developing health emergency with specific locations (DRC, Uganda), a precise timeline (May 16, 2026), and strong official sources (WHO, CDC) that should produce high-confidence evidence. The PHEIC framing exercises the system's ability to handle authoritative institutional announcements alongside rapidly evolving case counts and response measures.

### 11.2 UAE leaves OPEC

**Input:** "The UAE left OPEC on May 1, 2026, ending six decades of membership in the oil cartel."

Chosen because it tests a geopolitical/economic event that does not fit neatly into the original five event types (live_event, tech_launch, sports_tournament, cultural_event, disaster). The event is concluded (May 1), involves economic data (oil production, market impact), and has diverse news coverage across CNBC, BBC, Al Jazeera, and NYT. This input directly prompted the addition of `economic_event` as a sixth EventType, with required components (stat_grid, comparison_table, timeline, action_list) and official-domain hints (reuters.com, bloomberg.com, ft.com, wsj.com, imf.org, worldbank.org).

### 11.3 What these revealed

The disaster event type works well — the alert theme and hero produce a visually distinct page appropriate for a health emergency, and official sources (WHO situation reports) provide high-grade evidence that flows naturally into the page structure.

The UAE-OPEC example proved the taxonomy needed to expand. The original 5 types had no home for a geopolitical/economic event. Adding `economic_event` as a sixth type — with its own recipe, required components, and official-domain hints — closed this gap. The UAE-OPEC page now correctly classifies as `economic_event` with the editorial theme and delta hero variant. A dedicated economic theme (data-dense, chart-oriented) would further improve the visual fit.
