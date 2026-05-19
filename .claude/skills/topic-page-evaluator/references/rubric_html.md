# HTML Output — LLM-as-Judge Rubric

Evaluate each generated HTML page on these dimensions. Assign a 1-10 score
per sub-dimension with a specific, actionable justification.

## 1. Editorial Quality (weight: 0.30)

**What to evaluate**: Does the page read like a real editorial product?

| Score | Description |
|-------|-------------|
| 9-10 | Crisp, confident editorial voice. Headline is concrete and compelling. Deck adds real context. Summary is tight and informative. No fluff, no clickbait. |
| 7-8 | Solid editorial framing. Headline is factual if not especially memorable. Deck and summary are clear. Minor wordiness or vagueness. |
| 5-6 | Serviceable but flat. Headline is generic. Deck is optional-feeling. Summary restates the obvious. |
| 3-4 | Reads like a template fill. Generic phrasing. No editorial point of view. |
| 1-2 | Incoherent, contradictory, or clearly fabricated content. |

**Key checks**:
- Headline is ≤12 words and substantive (not "Event Update" or "What Happened")
- Deck adds information beyond the headline, not just restating it
- Summary answers "what happened, why it matters, what changed" in 2-3 sentences
- Key facts are the 3-5 most important things, not random trivia
- No fabricated-sounding details (check against source list)

## 2. Visual Design (weight: 0.25)

**What to evaluate**: Does the page feel like a designed product?

| Score | Description |
|-------|-------------|
| 9-10 | Clear visual hierarchy. Typography creates rhythm. Color use is intentional. Spacing is comfortable. Above-the-fold is immediately orienting. |
| 7-8 | Competent layout. Sections are distinguishable. Typography is clean. Some visual monotony or minor spacing issues. |
| 5-6 | Functional but plain. Sections blur together. Typography is browser-default feeling. Little visual distinction between content types. |
| 3-4 | Layout is confusing. Inconsistent spacing. Hard to scan. |
| 1-2 | Broken layout, unreadable text, missing CSS. |

**Key checks**:
- Hero variant fits the event type (delta for tech launch, live for live event, schedule for upcoming)
- Theme CSS is appropriate for the event tone
- Key facts strip is scannable at a glance
- Sections have visual separation (rules, spacing, or color blocks)
- Sources footer is compact and scannable
- Page looks intentional at 880px width (the shell max-width)

## 3. Event-Fit (weight: 0.25)

**What to evaluate**: Does the page shape match the event type?

| Score | Description |
|-------|-------------|
| 9-10 | Page components directly answer the core reader questions for this event type. A reader of this event type would immediately find what they need. |
| 7-8 | Required components are present and relevant. Most core questions are answered. One component feels slightly forced. |
| 5-6 | Required components exist but feel generic. Core questions are partially answered. |
| 3-4 | Wrong components for the event type, or key questions unanswered. |
| 1-2 | Components are random or clearly wrong for the event type. |

**Core reader questions per event type**:
- **tech_launch**: what changed? who's affected? rollout status? what to do?
- **live_event / cultural_event**: when? where? who's performing? how to watch?
- **sports_tournament**: when? where? who's playing? how to follow?
- **disaster**: where impacted? what's status? what should people do?

## 4. Reader Usefulness (weight: 0.20)

**What to evaluate**: After 30 seconds, would a reader feel informed?

| Score | Description |
|-------|-------------|
| 9-10 | Reader gets the full picture above the fold. Key facts are what they'd actually want to know. Action items are genuinely useful. Uncertainty is explained honestly. |
| 7-8 | Reader gets the main point quickly. Some scrolling needed for details. Action items are reasonable if generic. |
| 5-6 | Reader has to work to extract the story. Key facts are not the most important ones. Action items feel like filler. |
| 3-4 | Reader leaves confused or misinformed. Important info is buried. No clear takeaway. |
| 1-2 | Page is actively misleading or useless. |

**Key checks**:
- Above-the-fold (hero + key facts) tells the full story without scrolling
- Action items are concrete and useful (not "Stay tuned for updates")
- Uncertainty box is present when contradictions exist and explains them clearly
- Source list lets reader verify claims if they want to go deeper
- No obvious reader question goes unanswered (e.g., "how do I watch?" for a live event)

## 5. Evidence Grounding (weight: 0.15)

**This dimension replaces the old Trust & Citation bonus/penalty.** It measures
whether the page's factual claims are backed by the EvidenceGraph claim cards.

**Method**: Cross-check every specific factual claim (numbers, dates, named
entities, status statements) on the page against the EvidenceGraph. See
`references/fact_checking.md` for the full methodology.

| Score | Description |
|-------|-------------|
| 9-10 | ≥90% of factual claims have corresponding claim_cards with full_text_verified or reputable_snippet grade. Zero invented numbers. |
| 7-8 | ≥75% claims grounded. 1-2 minor claims without cards. |
| 5-6 | ≥50% claims grounded. Several unsupported numbers or dates. |
| 3-4 | <50% claims grounded. Page relies heavily on unsupported assertions. |
| 1-2 | Most claims are ungrounded. Page is essentially fabricated. |

**Key checks**:
- Every number in a stat_grid or comparison_table has a claim_id
- Hyper-specific numbers (3+ significant figures) are verified against claim cards
- Dates, entity names, and metric values match their claim card values
- Unsupported claims (no claim card) are editorial framing, not presented as facts

## 6. Trust & Citation Quality (weight: 0.10)

**Positive signals** (+0.1 each, max +0.5):
- Official sources are marked with visual distinction (e.g., ★)
- Citations include publisher names that a reader would recognize
- Multiple independent sources for the same key fact
- Confidence banner is data-driven, not generic
- Uncertainty is presented with specific conflicting claims, not vague hedging

**Negative signals** (-0.2 each, max -1.0):
- Key numeric claim has no visible citation
- Citation points to an irrelevant or low-authority source
- Confidence banner fires on a page with strong evidence (false alarm)
- No confidence banner on a page with clearly thin evidence (missed alarm)

## Scoring summary

```
Editorial score = sum(sub_score * weight) for dimensions 1-6
```
Note: the weights now sum to 1.25 (was 1.0 + bonus). Normalize by dividing by 1.25.
