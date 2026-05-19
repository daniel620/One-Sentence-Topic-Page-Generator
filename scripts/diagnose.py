"""Pipeline quality diagnostic — traces intermediate outputs.

Usage: python scripts/diagnose.py tests/fixtures/sports_tournament_worldcup.json
"""
import json, sys
from pathlib import Path

fp = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/sports_tournament_worldcup.json")
fx = json.loads(fp.read_text(encoding="utf-8"))
g = fx["evidence_graph"]; p = fx["topic_page"]

print(f"=== {fp.name} ===")

# Source curation
print("\n--- SOURCE CURATION ---")
roles = {}
for s in g["sources"]:
    r = s.get("final_source_role", "none")
    roles[r] = roles.get(r, 0) + 1
    if r in ("public_claim_source",):
        print(f"  [{r}] {s.get('publisher','?')} ({s.get('source_type','?')} auth={s.get('authority_score',0):.2f}) — {s.get('url','')[:80]}")
print(f"Role breakdown: {roles}")

# Claims
print("\n--- CLAIMS ---")
pub = [c for c in g["claims"] if c.get("public_claim_eligible")]
print(f"Total: {len(g['claims'])} | Public-eligible: {len(pub)}")
print(f"With evidence: {sum(1 for c in g['claims'] if len(c.get('evidence_sentence',''))>20)}")
print(f"With topic: {sum(1 for c in g['claims'] if c.get('claim_topic'))}")
print("First 5 public claims:")
for c in pub[:5]:
    ev = (c.get("evidence_sentence", "") or "")[:100]
    print(f"  [{c.get('claim_type','?')}] {c.get('text','')[:100]}")
    print(f"    evidence: {ev}")
    print(f"    sources: {c.get('source_ids',[])}")

# Contradictions
print("\n--- CONTRADICTIONS ---")
for c in g.get("contradictions", []):
    print(f"  [{c.get('ai_resolution','unreviewed')}] {c['topic']}: {c['claim_a']} vs {c['claim_b']}")

# Page composition
print("\n--- PAGE COMPOSITION ---")
print(f"Headline: {p.get('headline')}")
print(f"Deck: {p.get('deck','')}")
print(f"Confidence: {p.get('confidence')}")
for s in p["sections"]:
    items = s.get("items", [])
    cids = sum(1 for i in items if i.get("claim_id"))
    print(f"  {s['component_type']}: {len(items)} items, {cids} claim_ids")
    for i in items:
        if not i.get("claim_id"):
            v = i.get("value", "")[:60]
            if any(c.isdigit() for c in v) or any(w in v.lower() for w in ["date", "time", "venue", "stadium", "team", "match"]):
                print(f"    MISSING: {i.get('label','')}: {v}")

# QA
print("\n--- QA ---")
for q in p.get("qa_results", []):
    nf = len(q.get("failed_items", []))
    print(f"  {q['gate_name']}: {q['status']} ({q['confidence_score']:.2f}) {nf} failures")
    for fi in q.get("failed_items", [])[:3]:
        print(f"    - {fi[:150]}")
