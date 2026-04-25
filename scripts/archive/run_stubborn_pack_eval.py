#!/usr/bin/env python3
"""
run_stubborn_pack_eval.py — WO-EX-STUBBORN-PACK-EVAL-01

Diagnostic eval wrapper for cases that aren't moving on the 104-case master.

Runs a 15-case "stubborn pack" 3x for stability measurement, attributes
[VRAM-GUARD] Truncating input events from .runtime/logs/api.log to individual
cases, and produces a stability report with three buckets:

  - stable_pass   : passes in all N runs
  - stable_fail   : fails in all N runs
  - unstable      : flips between pass/fail across runs

Per-case tracking:
  - pass/score per run
  - failure_category per run (primary: llm_hallucination, schema_gap,
    field_path_mismatch, noise_leakage)
  - method per run (llm | rules | hybrid | rules_fallback | fallback | error_*)
  - extracted_count per run
  - truncated per run (VRAM-GUARD hit attributed from api.log delta)
  - shape_change flag (did the set of fieldPaths change across runs?)

Pairs with the 104-case master eval as the decision gate. The master eval is
NOT run by this script — it is run separately via the standard command in
CLAUDE.md. Optionally pass --master <path-to-master-report.json> to include
master topline numbers in the stability console readout.

The 15-case pack:
  Hard frontier (9)     : 075, 080, 081, 082, 083, 084, 085, 086, 087
  Structural misses (6) : 008, 009, 017, 018, 053, 088

Usage:
    ./scripts/run_stubborn_pack_eval.py --tag r4j \\
        [--runs 3] \\
        [--api http://localhost:8000] \\
        [--master docs/reports/master_loop01_r4j.json]

Outputs (under docs/reports/):
    stubborn_pack_<tag>_run1.json   (per-run eval report, standard schema)
    stubborn_pack_<tag>_run2.json
    stubborn_pack_<tag>_run3.json
    stubborn_pack_<tag>_stability.json       (cross-run consolidation)
    stubborn_pack_<tag>_stability.console.txt (human-readable readout)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Config ──────────────────────────────────────────────────────────────────

STUBBORN_CASES: List[str] = [
    # Hard frontier — dense_truth / mixed_narrative that have been 0/0 for R4
    "case_075",
    "case_080",
    "case_081",
    "case_082",
    "case_083",
    "case_084",
    "case_085",
    "case_086",
    "case_087",
    # Structural misses — contract cases stuck on schema/routing/entity bugs
    "case_008",
    "case_009",
    "case_017",
    "case_018",
    "case_053",
    "case_088",
]

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_SCRIPT = REPO_ROOT / "scripts" / "run_question_bank_extraction_eval.py"
API_LOG = REPO_ROOT / ".runtime" / "logs" / "api.log"
REPORT_DIR = REPO_ROOT / "docs" / "reports"

# Log markers
ATTEMPT_MARKER = "[extract] Attempting LLM extraction for person="
VRAM_GUARD_MARKER = "[VRAM-GUARD] Truncating"


# ── api.log delta parsing ───────────────────────────────────────────────────


def _snapshot_log_offset(log_path: Path) -> int:
    """Byte offset of the end of the log file, or 0 if it doesn't exist."""
    if not log_path.exists():
        return 0
    try:
        return log_path.stat().st_size
    except OSError:
        return 0


def _read_log_delta(log_path: Path, start_offset: int) -> str:
    """Read everything in api.log from start_offset to EOF, best-effort."""
    if not log_path.exists():
        return ""
    try:
        with open(log_path, "rb") as f:
            f.seek(start_offset)
            raw = f.read()
        return raw.decode("utf-8", errors="replace")
    except OSError as e:
        print(f"  WARN: could not read {log_path}: {e}")
        return ""


def _attribute_truncation_events(
    log_delta: str,
    case_ids_in_order: List[str],
) -> Dict[str, bool]:
    """
    Split the log delta on ATTEMPT_MARKER. Each resulting chunk (after the first
    preamble) corresponds to one extraction attempt. Attempts are in source-file
    order, same as the eval iterates, so we can zip them with case_ids_in_order.

    A chunk is flagged 'truncated' if it contains VRAM_GUARD_MARKER. Note some
    cases may not trigger an LLM attempt at all (rules-only early outs would
    skip the marker) — those cases get an assumed False.

    Returns {case_id: bool}. Missing cases default to False in the caller.
    """
    attribution: Dict[str, bool] = {}
    if not log_delta or not case_ids_in_order:
        return attribution

    # The first element is whatever came before the first marker — discard it.
    chunks = log_delta.split(ATTEMPT_MARKER)
    if len(chunks) <= 1:
        return attribution

    extraction_chunks = chunks[1:]  # one per attempt in chronological order
    # If we got FEWER attempts than cases, we can still attribute the first N
    # cases we have chunks for. If we got MORE attempts than cases, something
    # else ran extractions concurrently — we take only the first len(cases).
    for idx, case_id in enumerate(case_ids_in_order):
        if idx >= len(extraction_chunks):
            break
        chunk = extraction_chunks[idx]
        attribution[case_id] = VRAM_GUARD_MARKER in chunk

    return attribution


# ── Per-run eval invocation ─────────────────────────────────────────────────


def _run_single_eval(
    tag: str,
    run_idx: int,
    api_base: str,
) -> Tuple[Path, Dict[str, bool]]:
    """
    Invoke the master eval script filtered to the stubborn pack.
    Returns (report_path, {case_id: truncated_bool}).
    """
    output_path = REPORT_DIR / f"stubborn_pack_{tag}_run{run_idx}.json"
    case_ids_arg = ",".join(STUBBORN_CASES)

    # Snapshot log BEFORE the eval starts so the delta captures only this run.
    pre_offset = _snapshot_log_offset(API_LOG)

    cmd = [
        sys.executable,
        str(EVAL_SCRIPT),
        "--mode",
        "live",
        "--api",
        api_base,
        "--output",
        str(output_path),
        "--case-ids",
        case_ids_arg,
    ]

    print(f"\n─── run {run_idx} ─── {len(STUBBORN_CASES)} cases → {output_path.name}")
    print(f"    pre-log offset: {pre_offset:,} bytes")
    t0 = time.time()
    # Don't check=True — the eval script exits 1 whenever expected-to-pass
    # cases didn't pass, which is normal for stubborn-pack runs. We care about
    # the report file, not the exit code.
    try:
        subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    except Exception as e:
        print(f"    ERROR: eval subprocess raised: {e}")
        return output_path, {}
    elapsed = time.time() - t0
    print(f"    elapsed: {elapsed:.1f}s")

    # Read api.log delta and attribute VRAM-GUARD events.
    log_delta = _read_log_delta(API_LOG, pre_offset)
    # The eval iterates cases in source-file order, which is the order they
    # appear in question_bank_extraction_cases.json — NOT the order in which
    # we passed them on the command line. Reconstruct that order from the
    # report we just wrote.
    case_ids_in_order = _load_case_order_from_report(output_path)
    truncation_map = _attribute_truncation_events(log_delta, case_ids_in_order)
    if truncation_map:
        truncated_ids = sorted(k for k, v in truncation_map.items() if v)
        print(f"    VRAM-GUARD hits: {len(truncated_ids)} "
              f"({', '.join(truncated_ids) if truncated_ids else 'none'})")
    else:
        print(f"    VRAM-GUARD hits: (no attribution; log delta empty or "
              f"missing markers)")

    return output_path, truncation_map


def _load_case_order_from_report(report_path: Path) -> List[str]:
    """Extract case_id order from a just-written eval report."""
    if not report_path.exists():
        return []
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"    WARN: could not read report {report_path.name}: {e}")
        return []
    return [r["case_id"] for r in report.get("case_results", [])]


# ── Per-run result extraction ───────────────────────────────────────────────


def _extract_case_result(case_result: dict) -> dict:
    """Pull just the fields we care about for stability analysis.

    Schema note: the eval report uses `failure_categories` (list of strings)
    and `overall_score` (float 0-1). Be defensive — accept older/alternate
    keys (`failures`, `score`) if present.
    """
    failures = (
        case_result.get("failure_categories")
        or case_result.get("failures")
        or []
    )
    primary_failure = failures[0] if failures else None
    score = case_result.get("overall_score")
    if score is None:
        score = case_result.get("score", 0.0)
    raw_items = case_result.get("raw_items", []) or []
    field_paths = sorted({it.get("fieldPath", "") for it in raw_items if it.get("fieldPath")})
    return {
        "case_id": case_result.get("case_id"),
        "pass": bool(case_result.get("pass")),
        "score": round(float(score), 3),
        "failures": list(failures),
        "primary_failure": primary_failure,
        "method": case_result.get("method"),
        "extracted_count": case_result.get("extracted_count", 0),
        "field_paths": field_paths,
    }


def _load_run_results(report_path: Path) -> Dict[str, dict]:
    """Return {case_id: extracted_result_dict}."""
    if not report_path.exists():
        return {}
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"WARN: could not load {report_path}: {e}")
        return {}
    out: Dict[str, dict] = {}
    for cr in report.get("case_results", []):
        extracted = _extract_case_result(cr)
        cid = extracted["case_id"]
        if cid:
            out[cid] = extracted
    return out


# ── Cross-run consolidation ─────────────────────────────────────────────────


def _consolidate(
    per_run_results: List[Dict[str, dict]],
    per_run_truncation: List[Dict[str, bool]],
) -> dict:
    """
    Build the stability block. Expects parallel lists: one per run.

    Schema (per case):
      case_id, pass_count, scores, primary_failures, methods, extracted_counts,
      truncated_any, truncated_all, field_paths_identical, field_paths_changes,
      bucket (stable_pass | stable_fail | unstable)
    """
    n_runs = len(per_run_results)
    per_case: Dict[str, dict] = {}

    for cid in STUBBORN_CASES:
        runs = []
        for run_idx in range(n_runs):
            r = per_run_results[run_idx].get(cid)
            trunc = per_run_truncation[run_idx].get(cid, False)
            if r is None:
                # Case didn't appear in this run's report — skip this run but
                # record it as missing rather than crash.
                runs.append({
                    "missing": True,
                    "pass": False,
                    "score": None,
                    "primary_failure": None,
                    "method": None,
                    "extracted_count": None,
                    "field_paths": [],
                    "truncated": trunc,
                })
                continue
            runs.append({
                "missing": False,
                "pass": r["pass"],
                "score": r["score"],
                "primary_failure": r["primary_failure"],
                "method": r["method"],
                "extracted_count": r["extracted_count"],
                "field_paths": r["field_paths"],
                "truncated": trunc,
            })

        # Consolidated flags
        present_runs = [r for r in runs if not r["missing"]]
        pass_count = sum(1 for r in present_runs if r["pass"])
        fail_count = len(present_runs) - pass_count

        if not present_runs:
            bucket = "missing"
        elif pass_count == len(present_runs):
            bucket = "stable_pass"
        elif pass_count == 0:
            bucket = "stable_fail"
        else:
            bucket = "unstable"

        # Field-path stability across runs (only from present runs)
        path_sets = [tuple(r["field_paths"]) for r in present_runs]
        fp_identical = len(set(path_sets)) == 1 if path_sets else True
        fp_changes = len(set(path_sets)) - 1 if path_sets else 0

        # Primary-failure churn
        fails = [r["primary_failure"] for r in present_runs]
        unique_fails = sorted(set(f for f in fails if f is not None))
        fail_category_changed = len(unique_fails) > 1

        # Score improvement flag: did score strictly increase across the run seq?
        scores = [r["score"] for r in present_runs if r["score"] is not None]
        score_improved = len(scores) >= 2 and scores[-1] > scores[0]

        truncated_flags = [r["truncated"] for r in runs]
        truncated_any = any(truncated_flags)
        truncated_all = all(truncated_flags) if truncated_flags else False

        per_case[cid] = {
            "case_id": cid,
            "bucket": bucket,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "total_runs": len(present_runs),
            "field_paths_identical": fp_identical,
            "field_paths_change_count": fp_changes,
            "fail_category_changed": fail_category_changed,
            "unique_primary_failures": unique_fails,
            "score_improved_across_runs": score_improved,
            "truncated_any": truncated_any,
            "truncated_all": truncated_all,
            "runs": runs,
        }

    # Bucket summary
    buckets = {"stable_pass": [], "stable_fail": [], "unstable": [], "missing": []}
    for cid, info in per_case.items():
        buckets[info["bucket"]].append(cid)

    truncated_any_count = sum(1 for v in per_case.values() if v["truncated_any"])
    category_changed_count = sum(1 for v in per_case.values() if v["fail_category_changed"])
    score_improved_count = sum(1 for v in per_case.values() if v["score_improved_across_runs"])
    shape_changed_count = sum(1 for v in per_case.values() if not v["field_paths_identical"])

    return {
        "n_runs": n_runs,
        "per_case": per_case,
        "buckets": buckets,
        "counts": {
            "stable_pass": len(buckets["stable_pass"]),
            "stable_fail": len(buckets["stable_fail"]),
            "unstable": len(buckets["unstable"]),
            "missing": len(buckets["missing"]),
            "truncated_any": truncated_any_count,
            "fail_category_changed": category_changed_count,
            "score_improved_across_runs": score_improved_count,
            "field_shape_changed_across_runs": shape_changed_count,
        },
    }


# ── Console readout ─────────────────────────────────────────────────────────


def _format_master_block(master_report_path: Optional[Path]) -> List[str]:
    """Pull a tiny topline summary from a 104-case master report, if given."""
    if not master_report_path:
        return [
            "  MASTER (decision gate): not supplied — rerun wrapper with",
            "  --master docs/reports/master_loop01_<tag>.json to inline it.",
        ]
    if not master_report_path.exists():
        return [f"  MASTER: supplied path does not exist: {master_report_path}"]
    try:
        with open(master_report_path, "r", encoding="utf-8") as f:
            m = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return [f"  MASTER: could not read {master_report_path.name}: {e}"]
    s = m.get("summary", {})
    contract = m.get("contract_subset", {})
    v2b = m.get("v2_baseline", {})
    truth = m.get("truth_zone_summary", {})
    exp = m.get("expected_extractor_results", {})
    fail_cats = m.get("failure_categories", {}) or {}
    lines = [
        f"  MASTER (decision gate): {master_report_path.name}",
        f"    Total:              {s.get('passed', '?')}/{s.get('total_cases', '?')}"
        f"   avg {s.get('avg_overall_score', '?')}",
        f"    v3 contract subset: {contract.get('passed_v3', '?')}/{contract.get('total', '?')}",
        f"    v2 contract subset: {contract.get('passed_v2', '?')}/{contract.get('total', '?')}",
        f"    v2-compat (all):    {v2b.get('total_v2_passed', '?')}/{s.get('total_cases', '?')}"
        f"   rate={v2b.get('total_v2_rate', '?')}",
        f"    must_not_write violations:  {truth.get('must_not_write_violation_rate', '?')}",
        f"    Should-pass:  {exp.get('should_pass', {}).get('actually_passed', '?')}/"
        f"{exp.get('should_pass', {}).get('total', '?')}",
        f"    Known-gap:    {exp.get('known_gaps', {}).get('actually_passed', '?')}/"
        f"{exp.get('known_gaps', {}).get('total', '?')}",
        f"    Failure cats: "
        + (", ".join(f"{k}={v}" for k, v in fail_cats.items()) if fail_cats else "(none)"),
    ]
    return lines


def _format_stability_console(
    tag: str,
    stability: dict,
    master_report_path: Optional[Path],
) -> str:
    lines: List[str] = []
    lines.append("=" * 78)
    lines.append(f"  WO-EX-STUBBORN-PACK-EVAL-01 — tag={tag}  "
                 f"runs={stability['n_runs']}  "
                 f"cases={len(STUBBORN_CASES)}")
    lines.append("=" * 78)
    lines.append("")

    # Master gate
    lines.extend(_format_master_block(master_report_path))
    lines.append("")

    # Bucket counts
    c = stability["counts"]
    lines.append("  STUBBORN-PACK STABILITY:")
    lines.append(f"    stable_pass : {c['stable_pass']:>2} / {len(STUBBORN_CASES)}")
    lines.append(f"    stable_fail : {c['stable_fail']:>2} / {len(STUBBORN_CASES)}")
    lines.append(f"    unstable    : {c['unstable']:>2} / {len(STUBBORN_CASES)}")
    if c["missing"]:
        lines.append(f"    missing     : {c['missing']:>2} / {len(STUBBORN_CASES)}")
    lines.append("")
    lines.append(f"    truncated (any run)          : {c['truncated_any']}")
    lines.append(f"    failure-category changed     : {c['fail_category_changed']}")
    lines.append(f"    field-path shape changed     : {c['field_shape_changed_across_runs']}")
    lines.append(f"    score improved across runs   : {c['score_improved_across_runs']}")
    lines.append("")

    # Per-bucket case lists
    b = stability["buckets"]
    lines.append("  BUCKETS:")
    if b["stable_pass"]:
        lines.append(f"    stable_pass  : {', '.join(sorted(b['stable_pass']))}")
    else:
        lines.append(f"    stable_pass  : (none)")
    if b["stable_fail"]:
        lines.append(f"    stable_fail  : {', '.join(sorted(b['stable_fail']))}")
    else:
        lines.append(f"    stable_fail  : (none)")
    if b["unstable"]:
        lines.append(f"    unstable     : {', '.join(sorted(b['unstable']))}")
    else:
        lines.append(f"    unstable     : (none)")
    lines.append("")

    # Per-case detail
    lines.append("  PER-CASE:")
    lines.append(
        f"    {'case':<12}{'bucket':<14}{'p/t':<6}{'scores':<22}"
        f"{'primary_failure(s)':<30}{'method':<18}{'trunc':<6}{'shape':<6}"
    )
    for cid in STUBBORN_CASES:
        info = stability["per_case"].get(cid)
        if not info:
            continue
        score_strs = [
            str(r["score"]) if r["score"] is not None else "—"
            for r in info["runs"]
        ]
        scores_col = "/".join(score_strs)
        fails_col = ",".join(info["unique_primary_failures"]) or "—"
        method_col = "/".join(
            sorted({r["method"] or "?" for r in info["runs"]})
        )
        pt_col = f"{info['pass_count']}/{info['total_runs']}"
        trunc_col = "Y" if info["truncated_any"] else "·"
        shape_col = "chg" if not info["field_paths_identical"] else "·"
        lines.append(
            f"    {cid:<12}{info['bucket']:<14}{pt_col:<6}{scores_col:<22}"
            f"{fails_col[:28]:<30}{method_col[:16]:<18}{trunc_col:<6}{shape_col:<6}"
        )
    lines.append("")

    # Flip audit (unstable + shape-changed highlights)
    flips = sorted(b.get("unstable", []))
    if flips:
        lines.append("  FLIPS TO AUDIT:")
        for cid in flips:
            info = stability["per_case"][cid]
            per_run_strs = []
            for idx, r in enumerate(info["runs"], 1):
                tag_parts = []
                tag_parts.append("P" if r["pass"] else "F")
                if r["truncated"]:
                    tag_parts.append("T")
                per_run_strs.append(
                    f"r{idx}={''.join(tag_parts)}:{r['score']}"
                    f" m={r['method'] or '?'} n={r['extracted_count']}"
                )
            lines.append(f"    {cid}  " + "  ".join(per_run_strs))
        lines.append("")

    lines.append("=" * 78)
    return "\n".join(lines) + "\n"


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="WO-EX-STUBBORN-PACK-EVAL-01 — 15-case stability wrapper"
    )
    parser.add_argument(
        "--tag",
        required=True,
        help="Suffix for output files, e.g. r4j (→ stubborn_pack_r4j_*.json)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="Number of times to run the pack (default: 3)",
    )
    parser.add_argument(
        "--api",
        default="http://localhost:8000",
        help="API base URL for live mode (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--master",
        default=None,
        help="Optional path to a 104-case master report JSON to inline in the "
             "stability console readout (for the full audit block).",
    )
    args = parser.parse_args()

    # Preflight
    if not EVAL_SCRIPT.exists():
        print(f"ERROR: eval script not found: {EVAL_SCRIPT}")
        sys.exit(1)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not API_LOG.exists():
        print(f"WARN: {API_LOG} not found — truncation attribution will be empty")

    # Per-run eval passes
    per_run_reports: List[Path] = []
    per_run_truncation: List[Dict[str, bool]] = []
    for run_idx in range(1, args.runs + 1):
        report_path, trunc_map = _run_single_eval(args.tag, run_idx, args.api)
        per_run_reports.append(report_path)
        per_run_truncation.append(trunc_map)

    # Load all runs & consolidate
    per_run_results = [_load_run_results(p) for p in per_run_reports]
    stability = _consolidate(per_run_results, per_run_truncation)

    # Write stability artifacts
    stability_json_path = REPORT_DIR / f"stubborn_pack_{args.tag}_stability.json"
    stability_console_path = REPORT_DIR / f"stubborn_pack_{args.tag}_stability.console.txt"

    full_stability = {
        "tag": args.tag,
        "runs": args.runs,
        "stubborn_cases": STUBBORN_CASES,
        "per_run_reports": [p.name for p in per_run_reports],
        "stability": stability,
    }

    with open(stability_json_path, "w", encoding="utf-8") as f:
        json.dump(full_stability, f, indent=2, ensure_ascii=False, default=str)

    master_path = Path(args.master).resolve() if args.master else None
    console_text = _format_stability_console(args.tag, stability, master_path)
    stability_console_path.write_text(console_text, encoding="utf-8")

    # Echo to stdout so it shows up in the terminal too
    print()
    print(console_text)
    print(f"Stability JSON    → {stability_json_path}")
    print(f"Stability console → {stability_console_path}")


if __name__ == "__main__":
    main()
