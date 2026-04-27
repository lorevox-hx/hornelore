"""
WO-EX-FAILURE-PACK-01 — cluster-JSON sidecar for master eval output (#141).

Given a `report` dict produced by run_question_bank_extraction_eval.generate_report,
build a compact failure-cluster view grouped by:

    failure_category × narrator × phase × score-bucket

Plus hallucination-prefix rollup and must_not_write breakout. Mirrors the
hand-rolled FAILING_CASES_r5h_RUNDOWN.md doc 1:1 so the two artifacts stay
in sync.

Byte-stable wrt master report JSON — this writes a second file only.
No scoring logic here, pure aggregation.

Exports:
    build_failure_pack(report, eval_tag=None) -> dict
    render_failure_pack_console(pack) -> str
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


_SCORE_BUCKETS = [
    ("0.00",      lambda s: s == 0.0),
    ("0.01-0.24", lambda s: 0.0 < s < 0.25),
    ("0.25-0.49", lambda s: 0.25 <= s < 0.50),
    ("0.50-0.69", lambda s: 0.50 <= s < 0.70),
    ("0.70+",     lambda s: s >= 0.70),
]


def _prefix_of(field_path: str) -> str:
    """Return the top-level segment of a dotted field path."""
    if not field_path:
        return "(unknown)"
    return field_path.split(".", 1)[0]


def build_failure_pack(report: Dict[str, Any], eval_tag: Optional[str] = None) -> Dict[str, Any]:
    """Build a failure-cluster view of a master eval report.

    Input: the dict returned by generate_report() — must contain `case_results`,
    `failure_categories`, `invalid_field_path_hallucinations`,
    `must_not_write_violations`, and `summary`.

    Output: a self-contained dict, ready to json.dump.
    """
    results: List[dict] = report.get("case_results", []) or []
    summary = report.get("summary", {}) or {}
    failed_results = [r for r in results if not r.get("pass")]

    # ── failure_categories ────────────────────────────────────────────────────
    # report["failure_categories"] is already a {cat: count} dict. Attach the
    # list of case_ids per category so the pack is self-contained.
    cat_cases: Dict[str, List[str]] = {}
    for r in failed_results:
        for fc in r.get("failure_categories", []) or []:
            cat_cases.setdefault(fc, []).append(r["case_id"])
    failure_categories = {
        cat: {"count": len(cases), "cases": sorted(cases)}
        for cat, cases in sorted(cat_cases.items(), key=lambda x: -len(x[1]))
    }

    # ── by_narrator (failures only) ──────────────────────────────────────────
    by_narrator: Dict[str, Dict[str, Any]] = {}
    for r in failed_results:
        nid = r.get("narratorId") or "(unknown)"
        b = by_narrator.setdefault(nid, {"failed": 0, "cases": []})
        b["failed"] += 1
        b["cases"].append(r["case_id"])
    for v in by_narrator.values():
        v["cases"].sort()

    # ── by_phase (failures only) ─────────────────────────────────────────────
    by_phase: Dict[str, Dict[str, Any]] = {}
    for r in failed_results:
        ph = r.get("phase") or "(unknown)"
        b = by_phase.setdefault(ph, {"failed": 0, "cases": []})
        b["failed"] += 1
        b["cases"].append(r["case_id"])
    for v in by_phase.values():
        v["cases"].sort()

    # ── by_era (failures only) ───────────────────────────────────────────────
    by_era: Dict[str, Dict[str, Any]] = {}
    for r in failed_results:
        era = r.get("current_era") or "(unknown)"
        b = by_era.setdefault(era, {"failed": 0, "cases": []})
        b["failed"] += 1
        b["cases"].append(r["case_id"])
    for v in by_era.values():
        v["cases"].sort()

    # ── by_score_bucket (failures only) ──────────────────────────────────────
    by_score_bucket: Dict[str, Dict[str, Any]] = {
        label: {"count": 0, "cases": []} for label, _ in _SCORE_BUCKETS
    }
    for r in failed_results:
        s = float(r.get("overall_score") or 0.0)
        for label, pred in _SCORE_BUCKETS:
            if pred(s):
                by_score_bucket[label]["count"] += 1
                by_score_bucket[label]["cases"].append(r["case_id"])
                break
    for v in by_score_bucket.values():
        v["cases"].sort()

    # ── hallucination_prefix_rollup ──────────────────────────────────────────
    # Source: report["invalid_field_path_hallucinations"] — already aggregated
    # per case, with top-5 offenders each. We re-fold to prefix (e.g. "parents",
    # "greatGrandparents") and count cases touching each prefix.
    ifph = report.get("invalid_field_path_hallucinations", []) or []
    prefix_cases: Dict[str, set] = {}
    prefix_offender_total: Dict[str, int] = {}
    for entry in ifph:
        cid = entry.get("case_id")
        for off in entry.get("offenders", []) or []:
            p = _prefix_of(off)
            prefix_cases.setdefault(p, set()).add(cid)
            prefix_offender_total[p] = prefix_offender_total.get(p, 0) + 1
    halluc_prefix = {
        p: {
            "offenders":  prefix_offender_total[p],
            "case_count": len(prefix_cases[p]),
            "cases":      sorted(prefix_cases[p]),
        }
        for p in sorted(prefix_cases.keys(),
                        key=lambda k: -prefix_offender_total[k])
    }

    # ── must_not_write breakout ──────────────────────────────────────────────
    mnw_src = report.get("must_not_write_violations", []) or []
    mnw_by_case: Dict[str, List[str]] = {}
    for entry in mnw_src:
        cid = entry.get("case_id")
        fp = entry.get("fieldPath")
        if cid and fp:
            mnw_by_case.setdefault(cid, []).append(fp)
    must_not_write = {
        "count": len(mnw_by_case),
        "cases": [
            {"case_id": cid, "offenders": sorted(set(fps))}
            for cid, fps in sorted(mnw_by_case.items())
        ],
    }

    # ── cross_axis_highlights — biggest cell in each of two grids ────────────
    # narrator × phase and category × narrator. Useful for "where is the fire?"
    nar_phase: Dict[tuple, int] = {}
    for r in failed_results:
        nar_phase[(r.get("narratorId"), r.get("phase"))] = \
            nar_phase.get((r.get("narratorId"), r.get("phase")), 0) + 1
    cat_nar: Dict[tuple, int] = {}
    for r in failed_results:
        for fc in r.get("failure_categories", []) or []:
            cat_nar[(fc, r.get("narratorId"))] = \
                cat_nar.get((fc, r.get("narratorId")), 0) + 1
    highlights = []
    if nar_phase:
        (nid, ph), cnt = max(nar_phase.items(), key=lambda kv: kv[1])
        highlights.append({
            "axis": "narrator×phase",
            "row": f"{nid}×{ph}",
            "failed": cnt,
        })
    if cat_nar:
        (fc, nid), cnt = max(cat_nar.items(), key=lambda kv: kv[1])
        highlights.append({
            "axis": "category×narrator",
            "row": f"{fc}×{nid}",
            "failed": cnt,
        })

    pack = {
        "_wo": "WO-EX-FAILURE-PACK-01",
        "eval_tag": eval_tag,
        "generated_from": {
            "_wo": report.get("_wo"),
            "_generated": report.get("_generated"),
            "mode": report.get("mode"),
        },
        "total_cases": summary.get("total_cases"),
        "passed": summary.get("passed"),
        "failed": summary.get("failed"),
        "failure_categories": failure_categories,
        "by_narrator": by_narrator,
        "by_phase": by_phase,
        "by_era": by_era,
        "by_score_bucket": by_score_bucket,
        "hallucination_prefix_rollup": halluc_prefix,
        "must_not_write": must_not_write,
        "cross_axis_highlights": highlights,
    }
    return pack


def render_failure_pack_console(pack: Dict[str, Any]) -> str:
    """Render a human-readable ~50-line summary of the failure pack."""
    lines: List[str] = []
    w = lines.append

    tag = pack.get("eval_tag") or "(untagged)"
    w("=" * 78)
    w(f"  FAILURE PACK — eval_tag={tag}")
    w("=" * 78)
    w(f"  total: {pack.get('total_cases')}   "
      f"passed: {pack.get('passed')}   failed: {pack.get('failed')}")
    w("")

    w("  Failure categories:")
    for cat, d in pack.get("failure_categories", {}).items():
        w(f"    {cat:<32} {d['count']:>3}   [{', '.join(d['cases'][:6])}"
          f"{'...' if len(d['cases']) > 6 else ''}]")
    w("")

    w("  By narrator (failures):")
    for nid, d in sorted(pack.get("by_narrator", {}).items(),
                         key=lambda x: -x[1]["failed"]):
        w(f"    {nid:<32} {d['failed']:>3}")
    w("")

    w("  By phase (failures):")
    for ph, d in sorted(pack.get("by_phase", {}).items(),
                        key=lambda x: -x[1]["failed"]):
        w(f"    {ph:<32} {d['failed']:>3}")
    w("")

    w("  By era (failures):")
    for era, d in sorted(pack.get("by_era", {}).items(),
                         key=lambda x: -x[1]["failed"]):
        w(f"    {era:<32} {d['failed']:>3}")
    w("")

    w("  By score bucket (failures):")
    for label, _ in _SCORE_BUCKETS:
        d = pack.get("by_score_bucket", {}).get(label, {"count": 0, "cases": []})
        w(f"    {label:<10} {d['count']:>3}")
    w("")

    w("  Hallucination prefix rollup:")
    for p, d in pack.get("hallucination_prefix_rollup", {}).items():
        w(f"    {p:<24} offenders={d['offenders']:>3}  "
          f"cases={d['case_count']:>2}")
    w("")

    mnw = pack.get("must_not_write", {})
    w(f"  must_not_write violations: {mnw.get('count', 0)}")
    for entry in mnw.get("cases", []):
        offs = ", ".join(entry["offenders"])
        w(f"    {entry['case_id']:<14} {offs}")
    w("")

    hl = pack.get("cross_axis_highlights", []) or []
    if hl:
        w("  Cross-axis highlights (biggest cell per grid):")
        for h in hl:
            w(f"    {h['axis']:<24} {h['row']:<60} failed={h['failed']}")
        w("")

    w("=" * 78)
    return "\n".join(lines) + "\n"
