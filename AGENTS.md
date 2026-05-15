# Project: Hot Event Topic Page Generator

## What This Is
3-stage pipeline: one sentence → web research → static HTML topic page.
This is a take-home interview project. Quality and defensibility of decisions matter.

## Architecture Rules (Do Not Deviate)
- LLM calls: ONLY in stage1_understand.py and stage3_synthesize.py
- Deterministic code: stage2_research.py (Tavily API calls), renderer.py (Jinja2)
- ALL prompt strings live in prompts.py — never inline prompts elsewhere
- ALL Pydantic models live in schemas.py — never define models inline
- renderer.py is a pure function: TopicPageData → str, zero LLM calls

## Key Files
- schemas.py → single source of truth for all data shapes
- prompts.py → all LLM prompt templates
- DESIGN.md → architectural decisions, consult before making design choices
- ANALYSIS.md → evaluation criteria and our product answers

## How To Verify Your Work
```bash
python scripts/verify.py          # runs full pipeline with fixtures, no real API calls
python scripts/generate.py "..."  # runs real pipeline, writes to output/
```
Always run verify.py after any change. Fix errors before proceeding.

## Code Standards
- Type hints on all functions
- Every LLM call uses instructor library for structured output
- Every template field access wrapped in {% if %} guard
- Log each stage output with log_stage() for debuggability
- requirements.txt must stay updated

## Output Requirements
- Three HTML files in output/ directory
- Each is a single self-contained file (no external CSS/JS dependencies)
- Must open correctly with `open output/filename.html` in browser
- Visual quality: real product feel, clear information hierarchy, not a wireframe

## LLM Call Pattern
```python
# Always use this pattern:
result = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=2000,
    messages=[...],
    response_model=SomePydanticModel,  # instructor handles validation + retry
)
```

## Environment
- Python 3.11+, use uv for package management
- Keys in .env file, loaded with python-dotenv
- Never hardcode API keys
