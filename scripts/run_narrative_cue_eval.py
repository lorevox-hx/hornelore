#!/usr/bin/env python3
"""WO-NARRATIVE-CUE-LIBRARY-01 Phase 3 — Eval harness for measured
library tuning.

Purpose
-------
Walk the locked eval pack (data/qa/lori_narrative_cue_eval.json) under
one or two library configurations and produce a per-case report plus
(when run in baseline-vs-candidate mode) a side-by-side diff with
regression detection.

This harness is the loop that lets you tune the library JSON with
EVIDENCE instead of guesses. Want to add 'sky' as a journey_arrival
trigger? Make a candidate library file with that change, run this
harness in --baseline X --candidate Y mode, and read the diff:

  - Which cases newly pass (did the patch help?)
  - Which cases newly fail (regression? must be fixed before the
    candidate gets adopted)
  - Per-cue-type delta (where is the patch concentrated?)
  - Per-miss-class shift (Class A "trigger gap" vs Class B "tie-break
    by library order")

The detector code stays unchanged. All movement comes from the library
JSON.

Typical use
-----------
Baseline only (just bank a fresh report against the current library):

    python3 scripts/run_narrative_cue_eval.py \\
      --output docs/reports/narrative_cue_eval_baseline.json

Baseline vs candidate (the real loop):

    python3 scripts/run_narrative_cue_eval.py \\
      --candidate data/lori/narrative_cue_library.candidate_class_a.json \\
      --tag class_a_v1 \\
      --output-dir docs/reports/

Stability check (run baseline twice, fail on any diff):

    python3 scripts/run_narrative_cue_eval.py --stability-check

Exit codes:
  0 = report generated successfully
  1 = stability-check found a diff (detector is non-deterministic — bug)
  2 = candidate caused regressions AND --strict was passed
  3 = bad inputs / library load failure / eval pack missing
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add server/code to import path so api.services.* resolves.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.narrative_cue_detector import (  # noqa: E402
    CueDetection,
    NarrativeCueLibrary,
    build_library_from_path,
    detect_cues,
)


_DEFAULT_LIBRARY = _REPO_ROOT / "data" / "lori" / "narrative_cue_library.v1.seed.json"
_DEFAULT_EVAL_PACK = _REPO_ROOT / "data" / "qa" / "lori_narrative_cue_eval.json"
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "docs" / "reports"


# ── Per-case record ───────────────────────────────────────────────────────

def _case_to_record(
    case: Dict[str, Any],
    detection: CueDetection,
) -> Dict[str, Any]:
    """Convert a single (case, detection) pair into a stable record."""
    case_id = case.get("id", "?")
    expected = case.get("expected_cue_type")
    section = case.get("current_section")

    top = detection.top_cue
    actual_cue_type = top.cue_type if top else None
    ok = (actual_cue_type == expected)

    # Top 3 cues for diagnostics (full library if we have <3)
    top3 = []
    for c in detection.cues[:3]:
        top3.append({
            "cue_type": c.cue_type,
            "score": c.score,
            "triggers": list(c.trigger_matches),
        })

    # Miss classification:
    #   none   = pass
    #   class_a = no cue matched at all (library trigger gap)
    #   class_b = wrong cue won; expected cue is in the ranked list at
    #             same or lower score (tie-break by library order favored
    #             a different cue)
    #   class_c = wrong cue won; expected cue is NOT in the ranked list
    #             at all (library covers expected but not for this text)
    miss_class = "none"
    if not ok:
        if not detection.cues:
            miss_class = "class_a"
        else:
            expected_in_ranked = any(c.cue_type == expected for c in detection.cues)
            if expected_in_ranked:
                miss_class = "class_b"
            else:
                miss_class = "class_c"

    return {
        "id": case_id,
        "expected": expected,
        "actual": actual_cue_type,
        "actual_score": top.score if top else 0,
        "actual_triggers": list(top.trigger_matches) if top else [],
        "ok": ok,
        "miss_class": miss_class,
        "top3": top3,
        "section": section,
        "user_text": case.get("user_text", "")[:160],
    }


# ── Run one library config ────────────────────────────────────────────────

def _run_one(
    library: NarrativeCueLibrary,
    library_path: str,
    cases: List[Dict[str, Any]],
    config_name: str,
) -> Dict[str, Any]:
    """Walk every case under the given library. Return a structured report."""
    records: List[Dict[str, Any]] = []
    for case in cases:
        user_text = case.get("user_text", "")
        section = case.get("current_section")
        if not user_text:
            continue
        det = detect_cues(user_text, current_section=section, library=library)
        records.append(_case_to_record(case, det))

    total = len(records)
    hits = sum(1 for r in records if r["ok"])
    pass_rate = (hits / total * 100.0) if total else 0.0

    # Per-cue-type breakdown
    per_cue: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "hits": 0})
    for r in records:
        ex = r["expected"]
        if ex:
            per_cue[ex]["total"] += 1
            if r["ok"]:
                per_cue[ex]["hits"] += 1

    # Miss class distribution
    miss_class_counts = Counter(r["miss_class"] for r in records if not r["ok"])

    return {
        "config_name": config_name,
        "library_path": str(library_path),
        "library_version": library.version,
        "library_description": library.description,
        "cue_type_count": len(library.cue_defs),
        "summary": {
            "total": total,
            "hits": hits,
            "misses": total - hits,
            "pass_rate_pct": round(pass_rate, 1),
        },
        "per_cue_type": dict(per_cue),
        "miss_class_distribution": dict(miss_class_counts),
        "records": records,
    }


# ── Diff baseline vs candidate ────────────────────────────────────────────

def _build_diff(baseline: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Side-by-side baseline vs candidate. Surfaces:
      - newly_passed: cases that failed in baseline, pass in candidate
      - newly_failed: cases that passed in baseline, fail in candidate (REGRESSIONS)
      - score_only_changes: same ok/fail bucket but different cue type / score
      - per_cue_type_delta: hits delta per cue type
      - miss_class_delta: how miss class distribution shifted
    """
    base_by_id = {r["id"]: r for r in baseline["records"]}
    cand_by_id = {r["id"]: r for r in candidate["records"]}

    common_ids = sorted(set(base_by_id) & set(cand_by_id))

    newly_passed = []
    newly_failed = []
    score_only_changes = []

    for cid in common_ids:
        b = base_by_id[cid]
        c = cand_by_id[cid]
        if b["ok"] == c["ok"]:
            # Same bucket — record only if the actual cue/score shifted
            if b["actual"] != c["actual"] or b["actual_score"] != c["actual_score"]:
                score_only_changes.append({
                    "id": cid,
                    "expected": b["expected"],
                    "baseline": {"actual": b["actual"], "score": b["actual_score"]},
                    "candidate": {"actual": c["actual"], "score": c["actual_score"]},
                    "ok": b["ok"],
                })
        elif not b["ok"] and c["ok"]:
            newly_passed.append({
                "id": cid,
                "expected": b["expected"],
                "baseline_actual": b["actual"],
                "baseline_miss_class": b["miss_class"],
                "candidate_score": c["actual_score"],
                "candidate_triggers": c["actual_triggers"],
                "user_text": b["user_text"],
            })
        elif b["ok"] and not c["ok"]:
            newly_failed.append({
                "id": cid,
                "expected": b["expected"],
                "candidate_actual": c["actual"],
                "candidate_miss_class": c["miss_class"],
                "baseline_score": b["actual_score"],
                "baseline_triggers": b["actual_triggers"],
                "user_text": b["user_text"],
            })

    # Per-cue-type delta (signed)
    per_cue_delta: Dict[str, Dict[str, int]] = {}
    all_cue_types = set(baseline["per_cue_type"]) | set(candidate["per_cue_type"])
    for ct in sorted(all_cue_types):
        b_hits = baseline["per_cue_type"].get(ct, {}).get("hits", 0)
        c_hits = candidate["per_cue_type"].get(ct, {}).get("hits", 0)
        per_cue_delta[ct] = {
            "baseline_hits": b_hits,
            "candidate_hits": c_hits,
            "delta": c_hits - b_hits,
        }

    # Miss-class delta
    miss_class_delta: Dict[str, Dict[str, int]] = {}
    all_miss_classes = set(baseline["miss_class_distribution"]) | set(candidate["miss_class_distribution"])
    for mc in sorted(all_miss_classes):
        b_n = baseline["miss_class_distribution"].get(mc, 0)
        c_n = candidate["miss_class_distribution"].get(mc, 0)
        miss_class_delta[mc] = {
            "baseline": b_n,
            "candidate": c_n,
            "delta": c_n - b_n,
        }

    base_pass = baseline["summary"]["pass_rate_pct"]
    cand_pass = candidate["summary"]["pass_rate_pct"]

    verdict = (
        "GREEN — candidate improves and zero regressions"
        if (cand_pass > base_pass and not newly_failed)
        else "AMBER — candidate has regressions; review newly_failed before adopting"
        if newly_failed
        else "AMBER — candidate is byte-equivalent or worse; do not adopt"
        if cand_pass <= base_pass
        else "GREEN — candidate improves"
    )

    return {
        "baseline": {
            "config": baseline["config_name"],
            "library_path": baseline["library_path"],
            "pass_rate_pct": base_pass,
            "hits": baseline["summary"]["hits"],
            "total": baseline["summary"]["total"],
        },
        "candidate": {
            "config": candidate["config_name"],
            "library_path": candidate["library_path"],
            "pass_rate_pct": cand_pass,
            "hits": candidate["summary"]["hits"],
            "total": candidate["summary"]["total"],
        },
        "delta_pct": round(cand_pass - base_pass, 1),
        "newly_passed": newly_passed,
        "newly_failed": newly_failed,
        "score_only_changes": score_only_changes,
        "per_cue_type_delta": per_cue_delta,
        "miss_class_delta": miss_class_delta,
        "verdict": verdict,
    }


# ── Console renderers ─────────────────────────────────────────────────────

def _render_baseline_console(report: Dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "=" * 78,
        f"  Narrative Cue Detector Eval — {report['config_name']}",
        "=" * 78,
        f"  Library:           {report['library_path']}",
        f"  Library version:   {report['library_version']}",
        f"  Cue types loaded:  {report['cue_type_count']}",
        "",
        f"  Total cases:       {s['total']}",
        f"  Hits:              {s['hits']}",
        f"  Misses:            {s['misses']}",
        f"  Pass rate:         {s['pass_rate_pct']}%",
        "",
        "  Per-cue-type pass rate:",
    ]
    for ct, d in sorted(report["per_cue_type"].items()):
        rate = (d["hits"] / d["total"] * 100.0) if d["total"] else 0.0
        lines.append(f"    {ct:25s}  {d['hits']}/{d['total']:<3d}  ({rate:.0f}%)")
    lines += [
        "",
        "  Miss-class distribution:",
    ]
    if report["miss_class_distribution"]:
        for mc, n in sorted(report["miss_class_distribution"].items()):
            lines.append(f"    {mc:12s}  {n}")
    else:
        lines.append("    (no misses)")

    misses = [r for r in report["records"] if not r["ok"]]
    if misses:
        lines += [
            "",
            f"  Misses ({len(misses)} cases):",
        ]
        for m in misses:
            lines.append(
                f"    [{m['id']}]  expected={m['expected']}  "
                f"actual={m['actual']}  score={m['actual_score']}  "
                f"miss_class={m['miss_class']}"
            )
    lines.append("=" * 78)
    return "\n".join(lines)


def _render_diff_console(diff: Dict[str, Any]) -> str:
    lines = [
        "=" * 78,
        "  Narrative Cue Detector Eval — BASELINE vs CANDIDATE",
        "=" * 78,
        f"  Baseline:   {diff['baseline']['config']}  →  "
        f"{diff['baseline']['hits']}/{diff['baseline']['total']}  "
        f"({diff['baseline']['pass_rate_pct']}%)",
        f"  Candidate:  {diff['candidate']['config']}  →  "
        f"{diff['candidate']['hits']}/{diff['candidate']['total']}  "
        f"({diff['candidate']['pass_rate_pct']}%)",
        f"  Delta:      {diff['delta_pct']:+.1f} pp",
        "",
        f"  Verdict:    {diff['verdict']}",
        "",
    ]

    if diff["newly_passed"]:
        lines.append(f"  Newly PASSED ({len(diff['newly_passed'])} cases):")
        for n in diff["newly_passed"]:
            lines.append(
                f"    + [{n['id']}]  expected={n['expected']}  "
                f"baseline_actual={n['baseline_actual']}  "
                f"candidate_triggers={n['candidate_triggers']}"
            )
        lines.append("")

    if diff["newly_failed"]:
        lines.append(f"  Newly FAILED — REGRESSIONS ({len(diff['newly_failed'])}):")
        for n in diff["newly_failed"]:
            lines.append(
                f"    - [{n['id']}]  expected={n['expected']}  "
                f"candidate_actual={n['candidate_actual']}  "
                f"baseline_triggers={n['baseline_triggers']}"
            )
        lines.append("")

    if diff["score_only_changes"]:
        lines.append(
            f"  Score / cue shifts (same ok bucket — {len(diff['score_only_changes'])}):"
        )
        for s in diff["score_only_changes"][:10]:
            lines.append(
                f"    ~ [{s['id']}]  base={s['baseline']['actual']}/{s['baseline']['score']}  "
                f"→ cand={s['candidate']['actual']}/{s['candidate']['score']}  ok={s['ok']}"
            )
        if len(diff["score_only_changes"]) > 10:
            lines.append(f"    ... ({len(diff['score_only_changes']) - 10} more)")
        lines.append("")

    lines.append("  Per-cue-type delta:")
    for ct, d in diff["per_cue_type_delta"].items():
        if d["delta"] != 0:
            sign = "+" if d["delta"] > 0 else ""
            lines.append(
                f"    {ct:25s}  base={d['baseline_hits']:>2d}  "
                f"cand={d['candidate_hits']:>2d}  delta={sign}{d['delta']}"
            )
    lines.append("")
    lines.append("  Miss-class delta:")
    for mc, d in diff["miss_class_delta"].items():
        sign = "+" if d["delta"] > 0 else ""
        lines.append(
            f"    {mc:12s}  base={d['baseline']:>2d}  cand={d['candidate']:>2d}  delta={sign}{d['delta']}"
        )
    lines.append("=" * 78)
    return "\n".join(lines)


# ── Stability check ───────────────────────────────────────────────────────

def _stability_check(library_path: str, eval_pack: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Run baseline twice. Confirm byte-identical output. Detector is
    documented as deterministic — this catches future regressions in
    that contract."""
    lib = build_library_from_path(library_path)
    a = _run_one(lib, library_path, eval_pack, config_name="stability_a")
    b = _run_one(lib, library_path, eval_pack, config_name="stability_b")

    # Strip the config_name (which differs by design) and compare records.
    a_records = json.dumps(a["records"], sort_keys=True)
    b_records = json.dumps(b["records"], sort_keys=True)
    if a_records == b_records:
        return True, "stability OK — two runs produced byte-identical case records"
    return False, "STABILITY FAIL — two runs of the same library produced different records"


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--baseline", type=str, default=str(_DEFAULT_LIBRARY),
                   help=f"Baseline library JSON (default: {_DEFAULT_LIBRARY})")
    p.add_argument("--candidate", type=str, default=None,
                   help="Optional candidate library JSON for baseline-vs-candidate diff")
    p.add_argument("--cases", type=str, default=str(_DEFAULT_EVAL_PACK),
                   help=f"Eval pack JSON (default: {_DEFAULT_EVAL_PACK})")
    p.add_argument("--output", type=str, default=None,
                   help="Output JSON path (single-config mode)")
    p.add_argument("--output-dir", type=str, default=str(_DEFAULT_OUTPUT_DIR),
                   help="Output directory (diff mode writes _baseline / _candidate / _diff)")
    p.add_argument("--tag", type=str, default=None,
                   help="Tag suffix for output filenames (diff mode)")
    p.add_argument("--strict", action="store_true",
                   help="In diff mode, exit 2 if candidate has any regressions")
    p.add_argument("--stability-check", action="store_true",
                   help="Run baseline library twice; exit 1 on any diff")
    args = p.parse_args()

    # Load eval pack
    cases_path = Path(args.cases)
    if not cases_path.is_file():
        print(f"ERROR: eval pack not found at {cases_path}", file=sys.stderr)
        return 3
    try:
        with cases_path.open(encoding="utf-8") as f:
            pack = json.load(f)
        cases = pack.get("cases", [])
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: failed to load eval pack: {exc}", file=sys.stderr)
        return 3
    if not cases:
        print(f"ERROR: eval pack has no cases at {cases_path}", file=sys.stderr)
        return 3

    # Stability check mode
    if args.stability_check:
        ok, msg = _stability_check(args.baseline, cases)
        print(msg)
        return 0 if ok else 1

    # Load baseline
    try:
        baseline_lib = build_library_from_path(args.baseline)
    except (ValueError, OSError) as exc:
        print(f"ERROR: failed to load baseline library: {exc}", file=sys.stderr)
        return 3
    baseline_report = _run_one(
        baseline_lib, args.baseline, cases,
        config_name=Path(args.baseline).stem,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    baseline_report["generated_at"] = timestamp
    baseline_report["eval_pack"] = str(cases_path)

    # Single-config mode
    if not args.candidate:
        out = args.output or str(_DEFAULT_OUTPUT_DIR / "narrative_cue_eval_baseline.json")
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(baseline_report, f, indent=2, sort_keys=False)
        console_path = out_path.with_suffix(".console.txt")
        with console_path.open("w", encoding="utf-8") as f:
            f.write(_render_baseline_console(baseline_report))
        print(_render_baseline_console(baseline_report))
        print(f"\nReport JSON:    {out_path}")
        print(f"Report console: {console_path}")
        return 0

    # Diff mode: load candidate, compare
    try:
        candidate_lib = build_library_from_path(args.candidate)
    except (ValueError, OSError) as exc:
        print(f"ERROR: failed to load candidate library: {exc}", file=sys.stderr)
        return 3
    candidate_report = _run_one(
        candidate_lib, args.candidate, cases,
        config_name=Path(args.candidate).stem,
    )
    candidate_report["generated_at"] = timestamp
    candidate_report["eval_pack"] = str(cases_path)

    diff = _build_diff(baseline_report, candidate_report)
    diff["generated_at"] = timestamp

    # Write all three artifacts
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = args.tag or "diff"
    base_out = out_dir / f"narrative_cue_eval_{tag}_baseline.json"
    cand_out = out_dir / f"narrative_cue_eval_{tag}_candidate.json"
    diff_out = out_dir / f"narrative_cue_eval_{tag}_diff.json"
    diff_console = out_dir / f"narrative_cue_eval_{tag}_diff.console.txt"

    with base_out.open("w", encoding="utf-8") as f:
        json.dump(baseline_report, f, indent=2, sort_keys=False)
    with cand_out.open("w", encoding="utf-8") as f:
        json.dump(candidate_report, f, indent=2, sort_keys=False)
    with diff_out.open("w", encoding="utf-8") as f:
        json.dump(diff, f, indent=2, sort_keys=False)
    with diff_console.open("w", encoding="utf-8") as f:
        f.write(_render_diff_console(diff))

    print(_render_diff_console(diff))
    print()
    print(f"Baseline:   {base_out}")
    print(f"Candidate:  {cand_out}")
    print(f"Diff JSON:  {diff_out}")
    print(f"Diff cons:  {diff_console}")

    if args.strict and diff["newly_failed"]:
        print(f"\nSTRICT MODE: candidate caused {len(diff['newly_failed'])} regressions. Exiting 2.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
