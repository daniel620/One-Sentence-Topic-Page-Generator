---
name: project-conventions
description: >
  Load for any task in this project. Provides essential context about
  what this project is, who it's for, and what success looks like.
---

## What This Project Is

A pipeline that takes one sentence describing a real-world event and generates
a standalone HTML topic page. The page serves someone who just heard about the
event and needs to become conversationally fluent in 60 seconds.

Three event categories are in scope: tech launches, live cultural events,
and sports tournaments. Each category represents a fundamentally different
user need and should feel purpose-built, not templated.

## Who Will Judge This

This is a take-home interview project. The evaluators are product-minded
engineers who weight these qualities equally:

- Product judgment: does the page feel designed for this specific event,
  or does it feel like a template with swapped content?
- System design: is the boundary between LLM reasoning and deterministic
  code intentional and defensible?
- Prompt craft: is structured output enforced, not hoped for?
- Data modeling: does the schema survive three very different event types
  without collapsing into untyped key-value pairs?
- Visual quality: does it look like a real product a user would trust?
- Engineering clarity: can the next person understand why decisions were made?

## What "Done" Looks Like

Three HTML files that open directly in a browser with no build step.
Each page should make a strong case that the system understood not just
the facts of the event, but what kind of page this event deserves.

The DESIGN.md should read like a design review, not a readme.
Every significant decision should include the alternative that was rejected
and why.

## The One Rule

Never fabricate information. If the research didn't surface it,
use null and let the template handle the absence gracefully.