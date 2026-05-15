# One-Sentence Topic Page Generator

A lightweight generator that turns a one-sentence event description into a polished, directly openable HTML topic page.

## What is in this repo?

- `dist/` contains three built topic pages that can be opened directly in a browser.
- `src/generate.mjs` is the CLI entry point.
- `data/examples/` contains cached research bundles for the three committed example pages.
- `DESIGN.md` explains the product and system choices behind the prototype.

## Included example outputs

These are already built and committed:

- `dist/nintendo-switch-2-launch.html`
- `dist/eurovision-2025-basel.html`
- `dist/fifa-world-cup-2026.html`

## Quick start

This project intentionally uses only built-in Node.js APIs, so there is no dependency install step.

```bash
npm test
npm run generate:examples
```

Then open any file in `dist/` directly in your browser.

## Generate a bundled example from its sentence

```bash
node src/generate.mjs \
  --input "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026." \
  --output ./dist/fifa-world-cup-2026.html
```

If the input sentence matches one of the cached examples, the generator uses the checked-in research bundle and renders deterministic HTML.

## Generate a new page from a brand-new sentence

1. Copy `.env.example` to `.env`.
2. Set `OPENAI_API_KEY`.
3. Make sure the machine running the generator has open internet access.
4. Run the CLI with a new sentence:

```bash
node src/generate.mjs \
  --input "Nintendo Switch 2 launches worldwide on June 5, 2025." \
  --output ./dist/switch-2.html
```

For uncached inputs, the prototype:

1. searches the open web,
2. fetches the top result pages,
3. asks the LLM for schema-conformant topic-page JSON, and
4. renders the final HTML deterministically.

## Environment variables

See `.env.example`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | For brand-new prompts | LLM structured synthesis |
| `OPENAI_MODEL` | Optional | Defaults to `gpt-4.1-mini` |
| `SEARCH_ENDPOINT` | Optional | Defaults to DuckDuckGo HTML search |
| `SEARCH_RESULT_LIMIT` | Optional | Number of pages to research |
| `FETCH_TIMEOUT_MS` | Optional | Per-page fetch timeout |

## Validation

```bash
npm test
npm run generate:examples
```

The tests cover fixture lookup and core HTML rendering. The generated sample pages in `dist/` are the manual verification artifacts that can be opened without any setup.
