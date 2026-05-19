# Internet Fact-Checking Methodology

## The Wikipedia staleness problem

This system generates pages about **currently-unfolding events**. Wikipedia is
a trailing indicator — it may take days to weeks for breaking news to appear.
"Not on Wikipedia" does NOT mean "false" for events from the past 2-4 weeks.

## Three-tier verification

### Tier 1: Official/primary sources (highest weight)
The event organizer's own domain. These are authoritative for claims about
the event itself.
- Sports: FIFA.com, UEFA.com, NBA.com, olympics.com
- Tech: openai.com, apple.com, blog.google
- Culture: eurovision.com, official festival sites
- Government: weather.gov, usgs.gov (earthquakes), reliefweb.int
- **If the page cites an official source and the URL is accessible, the claim
  is verified.**

### Tier 2: Reputable news media (good for recent events)
Established outlets with bylines, datelines, and editorial standards.
- Reuters, AP, BBC, NYT, Guardian, TechCrunch, The Verge, ESPN, Sky Sports
- **If 2+ independent reputable outlets report the same fact, the claim is
  verified even if Wikipedia doesn't have it yet.**

### Tier 3: Wikipedia (good for established facts, bad for breaking)
- Excellent for: historical context, tournament formats, venue capacities
- Unreliable for: events from the past 1-2 weeks, very specific numbers

## The "hyper-specific number" heuristic

Claims like "52.5% reduction," "1,050,000 tokens," or "$5.00 per 1M tokens"
with 3+ significant figures are **hallucination signatures** when:
1. They can't be found in any accessible source, AND
2. They're cited to URLs that return errors

Real editorial pages use round numbers or ranges ("about half," "over 1M,"
"around $5") unless quoting a specific official announcement. A page that
mixes vague source attributions with hyper-specific numbers is likely
fabricating the specifics.

## URL accessibility check

For every source URL cited in a generated page:
1. Try to fetch it
2. If 403/404: the page may be citing a guessed URL, not a verified one
3. The EvidenceGraph should only contain URLs that were actually fetched
   during evidence acquisition — check whether the claim cards support the
   specific numbers in the page

## The "claim card cross-check"

The most reliable verification method for this system:

1. Read the output page and note every specific factual claim (number, date, name)
2. Read the EvidenceGraph from the run artifacts
3. For each claim: does a claim_card with that exact value exist?
4. If the page says "52.5%" but no claim card has 52.5 → the composer invented it
5. If a claim card has it but the source URL is dead → evidence acquisition gap

This checks the pipeline internally without needing perfect internet access.

## Calibration

| Verification result | Meaning | Action |
|---------------------|---------|--------|
| ✓ Verified (Tier 1-3) | Claim confirmed by accessible source | No action |
| ? Unverifiable, recent | Claim about very recent event, no source accessible yet | Flag as "unconfirmed" not "false" |
| ? Unverifiable, specific | Hyper-specific claim with no source | Flag as "likely hallucinated" |
| ✗ Contradicted | Source says different value | Factual error — fix |
