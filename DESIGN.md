# DESIGN

## 1. Product decisions

### What belongs on a topic page?

I treated a topic page as a **live briefing surface**, not an article. That means the page should answer four editor and reader jobs quickly:

1. **What happened / what is happening?**
2. **Why does it matter?**
3. **What should I watch next?**
4. **Where is the information coming from?**

That led to a page shape with:

- a strong hero summary,
- a compact key-facts block,
- a timeline,
- event-specific watch items,
- key entities,
- editorial coverage angles,
- a small FAQ, and
- explicit source links.

### How the page adapts by event type

The prototype keeps one shared structural spine so the frontend stays reliable, but it adapts the **language and emphasis** by event type:

- **Tech / product launch** pages emphasize rollout, pricing, supply, compatibility, and launch software.
- **Culture / entertainment** pages emphasize schedule, fan momentum, performance framing, and live-event dynamics.
- **Sports** pages emphasize venue, format, contenders, operations, and pre-tournament logistics.

In code, the renderer swaps labels like the watch-section heading by event type. In the data layer, the examples show how the same schema can still feel purpose-fit because the content blocks change meaningfully.

### What I intentionally left out

- No live ticker or persistence layer.
- No user accounts or editorial CMS.
- No client-side JavaScript application shell.
- No image pipeline.
- No automatic claim-level citation footnotes in body copy.

Those are all reasonable next steps, but for a take-home I prioritized a page that is:

- directly openable,
- visually coherent,
- debuggable,
- and realistic about the split between structured generation and deterministic rendering.

## 2. System architecture

The system is a small pipeline with deliberately separate responsibilities:

1. **Input capture**: accept a one-sentence prompt.
2. **Research acquisition**:
   - if the sentence matches a bundled example, load cached research data;
   - otherwise search the web and fetch source pages.
3. **LLM structured synthesis**: ask the model for JSON matching a strict schema.
4. **Validation**: reject payloads that do not satisfy required fields and arrays.
5. **Deterministic rendering**: transform validated JSON into static HTML.

### Why this split?

The main design choice is to **not ask the LLM to write HTML directly**.

Instead:

- the LLM handles ambiguity, summarization, prioritization, and type inference;
- deterministic code handles layout, styling, escaping, and file output.

That boundary makes the system easier to test and safer to evolve. If the page design changes, I only update the renderer. If the schema changes, I can validate it centrally.

## 3. Prompt and data contract

The prompt asks the model to do three jobs only:

1. infer the event type,
2. stay grounded in supplied sources,
3. return only JSON that matches the schema.

### Schema

The enforced shape is intentionally compact but expressive:

```json
{
  "slug": "string",
  "inputSentence": "string",
  "eventType": "string",
  "pageTitle": "string",
  "kicker": "string",
  "heroSummary": "string",
  "whatChanged": "string",
  "whyItMatters": "string",
  "lastUpdated": "string",
  "statusLabel": "string",
  "keyFacts": [{ "label": "string", "value": "string" }],
  "timeline": [{ "date": "string", "title": "string", "description": "string" }],
  "watchItems": [{ "title": "string", "description": "string" }],
  "entities": [{ "name": "string", "role": "string", "detail": "string" }],
  "coverageAngles": [{ "title": "string", "description": "string" }],
  "faq": [{ "question": "string", "answer": "string" }],
  "sources": [{ "label": "string", "url": "string", "note": "string" }]
}
```

### Why this schema?

- It is rigid enough that the frontend can render without branching chaos.
- It is flexible enough to survive three different event types.
- It avoids the `Map<string, any>` trap.
- It gives editors a page that feels structured instead of essay-shaped.

### How conformance is enforced

- The OpenAI request uses `response_format: json_schema` with `strict: true`.
- Local validation checks required top-level fields and requires every major section to be non-empty.
- The HTML renderer only consumes validated data.

## 4. Information sourcing

### How the prototype sources information

For brand-new prompts, the generator is designed to:

1. perform a simple web search,
2. fetch the top result pages,
3. strip them into plain text,
4. hand the resulting dossier to the LLM.

In this repo, I also committed **cached example research bundles** so the sample pages can be regenerated without needing live network access.

### Why this approach?

For a take-home, the goal was a defensible online/offline split:

- **online mode** demonstrates how the product should behave for a new prompt,
- **cached examples** guarantee the repo still works when opened by reviewers with no keys or no internet.

### Citations, freshness, and conflicts

- Each page surfaces explicit source links in a dedicated source section.
- The prompt instructs the model to prefer official sources when sources conflict.
- The page includes a `lastUpdated` research snapshot label.
- In a production version, I would attach claim-level citations instead of page-level source lists.

### Cost and latency tradeoff

This prototype favors simplicity over raw speed:

- a small number of search results,
- raw HTML fetches,
- one structured LLM call,
- and a deterministic render pass.

That is slower than a heavily optimized production system, but it is easy to inspect and debug.

## 5. Failure modes

### Hallucinations

Defense implemented:

- only source-backed context is passed into the synthesis step,
- the prompt explicitly prefers official sources,
- the output must match a schema.

Still unsolved:

- body text is not claim-cited at sentence granularity,
- the model can still overstate uncertainty if the input sources are thin.

### Ambiguous prompts

Current behavior:

- bundled examples resolve immediately if the prompt matches a known sentence,
- otherwise the LLM must infer the event type from the source dossier.

A stronger production path would add an explicit clarification step when the input describes multiple plausible events.

### Bad or adversarial prompts

Current defenses are modest:

- the renderer escapes HTML,
- schema validation rejects malformed outputs,
- uncached prompts require explicit API-key setup rather than arbitrary script execution.

Still missing:

- a proper prompt-safety layer,
- source-domain allow/deny policies,
- a stronger ambiguity detector,
- and per-field confidence scoring.

### Network failures

This sandbox did not have open internet access during implementation, which is why the repo includes cached example bundles. The live path should fail loudly with a useful error instead of silently producing stale or fabricated content.

## 6. What I would do with another week

In priority order:

1. **Add claim-level citations** so readers can see exactly which source backs each fact block or timeline item.
2. **Introduce a research ranker** that boosts official and primary sources before the LLM sees them.
3. **Add ambiguity handling** that asks for a clarifying sentence when the initial prompt is underspecified.
4. **Track confidence and freshness** per section so the page can visually distinguish confirmed facts from softer analysis.
5. **Expand page types** with richer layouts for elections, disasters, and earnings releases.
6. **Add screenshot-based regression tests** to keep the directly openable HTML visually stable.
7. **Support incremental regeneration** so editors can refresh only the timeline or source section instead of rebuilding the full page every time.

## 7. Stack choice

I chose a zero-dependency Node.js implementation because it is a good fit for the assignment constraints:

- it is easy to run locally,
- easy to inspect,
- easy to generate static files with,
- and small enough that the architectural decisions remain visible instead of being hidden by framework code.

If this were becoming a real product, I would likely keep the structured generation pipeline but move the renderer into a component-based frontend with richer editorial controls.
