# Take-Home Challenge: Needs Analysis

## Evaluation Dimensions (Equal Weight)
1. **Product judgment** — Define what belongs on a topic page, defend decisions
2. **System & Agent design** — Debuggable pipeline, intentional LLM vs deterministic boundary
3. **Prompt engineering** — NOT one-shot. Structured outputs, schema enforcement, bad input handling
4. **Data modeling** — Schema survives 3 event types; not too rigid, not Map<string,any>
5. **Visual & UX sense** — Real product feel, not wireframe. Information hierarchy matters.
6. **Engineering tradeoffs** — Clean code + DESIGN.md articulates WHY, not just WHAT

## Key Signals From The Brief
- "Not just ask the LLM for the whole page in one shot" → multi-stage pipeline required
- "Map<string,any> escape hatch" explicitly called out as bad → typed schema required
- "Intentional boundary between LLM reasoning and deterministic code" → pipeline not agent
- "Please don't ship raw divs" → visual quality is a real bar
- "DESIGN.md separates strong candidates from average ones" → reasoning > implementation

## Our Answers To The Key Product Questions

### What is a topic page?
Not an article summary. A "knowledge graph entry point" for someone who just heard about
an event and needs to be conversationally fluent in 60 seconds.

It answers: What happened? Why does it matter? Who/what is involved? What's next?
It does NOT attempt to be: a comprehensive news feed, a replacement for reading the source.

### How does shape adapt to event type?
| Event Type | Visual Center | Why |
|---|---|---|
| tech_launch | Spec comparison cards + who's affected | Tech readers ask "what changes for me?" |
| live_event | Current status + schedule progress | Cultural readers ask "what's happening now?" |
| sports_tournament | Opening match + bracket nav | Sports readers ask "how do I follow this?" |

### What we intentionally left out
- Real-time auto-refresh (would require hosting, out of scope)
- User accounts / personalization
- Comments / social features
- Mobile app
- More than 5 event types (keep schema manageable for demo)

## Three Example Events
1. GPT-5.5 Instant → tech_launch, status: concluded (released May 5 2026)
2. Eurovision 2026 Vienna → live_event, status: live (Grand Final May 16 2026)
3. FIFA World Cup 2026 → sports_tournament, status: upcoming (starts June 11 2026)
