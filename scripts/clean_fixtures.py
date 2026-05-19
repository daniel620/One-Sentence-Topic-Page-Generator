"""Apply source filter + recalculate QA on all fixtures.

Idempotent. Run after fixtures are regenerated from live pipeline or
after any schema change that affects source roles.
"""
import json, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generator.schemas import Source, EvidenceGraph, EvidenceAwareIA, TopicPageData


def _should_keep_source(source: Source, admitted: dict[str, int]) -> bool:
    """Same logic as the source filter in stage2_research."""
    max_by_type = {
        "social": 2, "aggregator": 1, "unknown": 2,
        "official": 20, "primary_data": 20, "reputable_media": 20, "local_media": 8,
    }
    if source.authority_score < 0.5:
        return False
    if admitted.get(source.source_type.value, 0) >= max_by_type.get(source.source_type.value, 8):
        return False
    return True
from generator.contradictions import detect_contradictions
from generator.quality import QARunner


def main():
    for fp in sorted(Path("tests/fixtures").glob("*.json")):
        fx = json.loads(fp.read_text(encoding="utf-8"))
        g = fx.get("evidence_graph", {})

        # Filter sources
        admitted, kept_src, kept_cls = {}, [], []
        for s_data in g.get("sources", []):
            src = Source.model_validate(s_data)
            if _should_keep_source(src, admitted):
                kept_src.append(s_data)
                admitted[src.source_type.value] = admitted.get(src.source_type.value, 0) + 1

        # Filter claims to only those with surviving sources
        kept_sids = {s["source_id"] for s in kept_src}
        for c in g.get("claims", []):
            new_sids = [sid for sid in c.get("source_ids", []) if sid in kept_sids]
            if new_sids:
                c["source_ids"] = new_sids
                kept_cls.append(c)

        g["sources"], g["claims"] = kept_src, kept_cls

        # Re-detect contradictions
        from generator.schemas import Claim
        objs = []
        for c in kept_cls:
            try:
                objs.append(Claim.model_validate(c))
            except Exception:
                pass
        g["contradictions"] = [x.model_dump(mode="json") for x in detect_contradictions(objs)]

        if "topic_page" in fx:
            fx["topic_page"]["evidence_graph_ref"] = g

        # Recalculate QA
        graph = EvidenceGraph.model_validate(g)
        p = fx["topic_page"]
        ia = EvidenceAwareIA(
            final_event_type=p["event_type"],
            event_status=p["status"],
            page_thesis=p.get("summary", "")[:300],
            required_components=[s["component_type"] for s in p.get("sections", [])],
            layout_style=p.get("layout_style", "hero_focus"),
            confidence_summary="",
        )
        page = TopicPageData.model_validate({**p, "evidence_graph_ref": graph})
        result = QARunner(date.today()).run(page, graph, ia)
        p["qa_results"] = [g.model_dump(mode="json") for g in result["gate_results"]]
        p["confidence"] = result["confidence_level"].value

        fp.write_text(json.dumps(fx, indent=2, ensure_ascii=False, default=str))

        st = {}
        for s in kept_src:
            st[s["source_type"]] = st.get(s["source_type"], 0) + 1
        print(f"{fp.name}: {len(kept_src)} src {dict(sorted(st.items()))} / "
              f"{len(kept_cls)} claims / {len(g['contradictions'])} contradictions / "
              f"{p['confidence']} ({result['confidence_score']:.2f})")
        for gq in result["gate_results"]:
            nf = len(gq.failed_items)
            print(f"  {gq.gate_name}: {gq.status} ({gq.confidence_score:.2f})"
                  f"{f' {nf} failures' if nf else ''}")


if __name__ == "__main__":
    main()
