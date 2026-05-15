# System Design: Hot Event Topic Page Generator

## Architecture Overview

One-sentence input → 3-stage pipeline → static HTML output

```
INPUT
  │
  ▼
Stage 1: UNDERSTAND + PLAN IA [LLM]
  Classify event type, infer status, generate search queries,
  and plan layout/components.
  Output: EventContext
  │
  ▼
Stage 2: RESEARCH + EVIDENCE PACK [Deterministic]
  Parallel Tavily search, dedupe, extract evidence snippets,
  bucket evidence by planned components.
  Output: RawResearch
  │
  ▼
Stage 3: SYNTHESIZE PAGE DATA [LLM]
  Produce TopicPageData with schema-valid sections[] and grounded claims.
  Output: TopicPageData
  │
  ▼
RENDER [Deterministic]
  dynamic_topic_page.html + component partials
  Output: static .html file
```

## Product Definition

The product answer is: **a topic page is a decision and navigation surface**, not an article summary.
Users should leave with:

1. What changed or what is happening now.
2. What to do next.
3. Where each critical claim came from.

## Why We Switched to Generative UI

Fixed event-type templates looked polished but did not generalize well beyond known categories.
The new design keeps deterministic rendering while letting IA vary by event context.

Old contract:
- `event_type -> hardcoded template`

New contract:
- `event intent + evidence -> sections[] -> dynamic renderer`

This preserves intentional LLM/deterministic boundaries while improving product generalization.

## Schema Strategy

Key tension: we need flexibility without collapsing into `Map<string, any>`.

Resolution:
- Typed base fields for survivability (`headline`, `summary`, `sources`, `evidence_points`)
- Typed UI composition model:
  - `layout_style`
  - `planned_components` in Stage 1
  - `sections: list[UIComponent]` in Stage 3
  - `UIItem` leaves room for links/details without untyped payloads

Representative model shape:

```python
class TopicPageData(BaseModel):
    event_type: EventType
    status: EventStatus
    confidence: ConfidenceLevel
    headline: str
    summary: str
    key_entities: list[Entity]
    timeline: list[TimelineEvent]
    sources: list[Source]
    evidence_points: list[EvidencePoint]
    layout_style: LayoutStyle
    sections: list[UIComponent]
```

## Prompt Strategy

Two LLM calls with non-overlapping responsibilities:

### Stage 1 prompt
- Produces `EventContext` including:
  - event_type/status/confidence
  - search_queries
  - layout_style
  - planned_components
- This separates intent planning from synthesis.

### Stage 3 prompt
- Produces `TopicPageData` with:
  - grounded `evidence_points`
  - componentized `sections[]`
  - no unsupported numeric claims
- Forced to cite only URLs present in research payload.

## Deterministic Research Layer

Stage 2 does not call LLM.

It performs:
1. Parallel web search.
2. Dedupe and score ordering.
3. Sentence-level extraction for metric/date/action evidence.
4. `component_evidence` bucketing aligned to Stage 1 planned components.

This creates a compact, structured handoff so Stage 3 is less likely to lose hard facts.

## Rendering Design

Renderer uses one dynamic shell template:
- `templates/dynamic_topic_page.html.j2`

And typed component partials:
- `components/stat_grid.html.j2`
- `components/comparison_table.html.j2`
- `components/live_tracker.html.j2`
- `components/action_list.html.j2`
- `components/timeline_component.html.j2`
- `components/entity_list.html.j2`
- `components/source_list.html.j2`

The render loop is deterministic: iterate `sections`, select partial by `component_type`, inject typed `UIItem`s.

## Failure Modes

| Scenario | Handling |
|---|---|
| LLM outputs invalid JSON | instructor retries with validation feedback |
| Sparse or low-quality search results | confidence lowered, summary states limits |
| Unsupported hard numbers | Stage 3 prompt disallows numeric claims without evidence snippets |
| Conflicting sources | summary is instructed to surface uncertainty instead of guessing |
| Unknown event shape | component planning still yields generic actionable layout via typed components |

## Tradeoffs

Accepted:
- More complex schema and templates than fixed pages.
- Slightly higher synthesis complexity due to section composition.

Gained:
- Better generalization to events outside 3 starter categories.
- Stronger product fit through dynamic IA.
- Claim-level traceability and deterministic rendering guarantees.

