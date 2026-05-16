# Take-Home Challenge: One-Sentence Topic Page Generator

## Context

When a hot event breaks — a product launch, an earthquake, a celebrity scandal, a championship game — newsrooms and content teams want to publish a **dedicated topic page** within minutes. A topic page isn't a single article; it's a structured surface that aggregates context, timeline, key entities, related coverage, and live updates around an event.

Building these pages by hand doesn't scale. We want a system where an editor types **one sentence** describing the event, and the system produces a publishable topic page.

## Your Challenge

Build a system that takes a **one-sentence event description** as input and generates a **hot-event topic page** as output.

Example inputs your system should handle:

1. `"OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026."`
2. `"Eurovision 2026 is being held in Vienna from May 12 to May 16."`
3. `"The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026."`

These are **real, currently-unfolding or imminent events** — you can (and should) research them on the open web. Your system will need to fetch and reason over real, fresh information; producing a page from the model's parametric memory alone is not the assignment, and stale information is a visible failure.

The three examples span very different categories (AI / tech rollout, a major cultural event happening this week, a global sports tournament weeks away). A good system should produce pages that feel **purpose-fit to the event type**, not the same template with the words swapped. You are also welcome to swap in your own one-sentence inputs as long as they are **real events that are currently happening or scheduled in the near future** — pick whatever you find most interesting to build for.

The "shape" of a topic page is **deliberately not specified** — figuring out what a topic page should contain (and how it should adapt to different event types) is part of what we're evaluating.

## What "Done" Looks Like

You'll deliver three things:

### 1. Built, openable topic pages in the repo

- **The built HTML for at least one topic page committed to the repo** — we'll open the file directly in a browser. No hosting or deployment is required.
- The source code behind it (clear `README` with how to run the generator locally and produce a new page from a new one-sentence input).
- Two more example outputs from inputs of your choice — also committed as built HTML alongside the first. We strongly suggest the three examples span different event categories so we can see how your system generalizes.

### 2. A design document (`DESIGN.md`)

This is the part that **separates strong candidates from average ones**. Cover at least:

- **Product decisions**: How did you decide what belongs on a topic page? How does the page shape adapt (or not) to event type? What did you intentionally leave out?
- **System architecture**: How is the generation pipeline structured? Where do LLM calls sit, and where does deterministic code sit? Why those boundaries?
- **Prompt & data contract**: How do you go from a fuzzy one-sentence input to structured data that the frontend can render reliably? Show the schema and explain how you keep LLM output conformant.
- **Information sourcing**: How does your system actually pull real-world information about the event — web search API, scraping, an agent tool-use loop, something else? How do you handle citations, freshness, conflicting sources, and the cost / latency of doing this online?
- **Failure modes**: What happens when the LLM hallucinates? When the input is ambiguous, off-topic, or adversarial? What did you actually defend against vs. acknowledge as a known limitation?
- **What you'd do with another week**: Concrete, prioritized — not hand-wavy.

## Tech Stack

**Open.** Use whatever frontend framework, language, and LLM provider you're most productive in. We do not give bonus points for a particular stack — we give bonus points for the stack being a *defensible choice* given your design.

You will need to bring your own:

- **LLM API access** (OpenAI, Anthropic, Google, open-source models — your call), and
- **A way for the system to fetch live information from the open web** (a search API such as Brave / SerpAPI / Tavily, a research API like Perplexity, scraping, an agent tool-use loop, or any combination).

Document which providers / approaches you chose and why.

**API keys**: use your own — **do not commit any keys, tokens, or secrets to the repo**. Use a `.env` file (gitignored) and include a `.env.example` listing the variable names we'd need to set if we re-ran the generator ourselves.

## How We'll Evaluate

We weight these roughly equally:

| Dimension | What we look for |
|---|---|
| **Product judgment** | Did you treat "what is a topic page" as a real product question? Are your decisions defensible? |
| **System & Agent design** | Clear separation of responsibilities. Pipeline is debuggable, observable, and the boundary between LLM reasoning and deterministic code is intentional. |
| **Prompt engineering & LLM craft** | Structured outputs, schema enforcement, graceful handling of ambiguous/bad inputs. Not just "ask the LLM for the whole page in one shot." |
| **Data modeling** | A schema that survives contact with three very different event types without becoming either too rigid or a `Map<string, any>` escape hatch. |
| **Visual & UX sense** | Does the page look and feel like a real product, not a wireframe? Information hierarchy, visual rhythm, typography, density, responsive behavior, empty / loading / error states — we're looking for **taste and judgment**, not pixel-perfect polish. This is a meaningful part of the bar; please don't ship raw `<div>`s. |
| **Engineering tradeoffs & code clarity** | Code is clean enough for the next person to extend. The `DESIGN.md` shows you can articulate *why* you chose what you chose, and which tradeoffs you knowingly accepted. |

## What We Care Less About

So you don't waste time on the wrong things:

- **Hosting & deployment.** You don't need to deploy anything anywhere. Committing the built HTML files to the repo is all we need — no Docker, no CI, no hosting, no monitoring.
- **Auth, accounts, persistence.** Skip them entirely unless you have a specific reason.
- **Scope.** We'd much rather see one polished, real example with a thoughtful design doc than five half-finished scenarios.

## Logistics

- **Time budget**: We expect this to take roughly **one week of evening / weekend effort**. If you find yourself wanting to spend more, stop and write the rest in `DESIGN.md` as "what I'd do next."
- **Submission**: Email us back with **either** a link to a public Git repo (GitHub / GitLab) **or** a zip file of the repo if you'd prefer not to publish it online. Either way, the repo must contain the source code, `DESIGN.md`, and the **built HTML output** for your three example pages — we'll open those HTML files directly to view them, no other setup on our side.
- **Before you send**: double-check that **no API keys, tokens, `.env` files, or other credentials** are in the repo or zip. This applies to git history too — a `git log -p` or a quick search across the archive for `sk-`, `API_KEY`, etc. before you hit send is a good idea.
- **Questions during the challenge**: If something is genuinely blocking you, email us. But note: **the ambiguity in this brief is intentional**. We want to see the judgment calls you make. "I assumed X because Y" in your `DESIGN.md` is a perfectly good answer to most questions.

## One Last Thing

There is no reference solution. Two strong candidates will likely build very different systems and we will be happy with both. What we want to see is **a thinker** — someone who can take an underspecified prompt, define the problem, defend their definition, and ship something coherent against it.

Good luck — we're looking forward to reading your `DESIGN.md`.