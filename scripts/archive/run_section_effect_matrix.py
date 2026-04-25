#!/usr/bin/env python3
"""
run_section_effect_matrix.py — WO-EX-SECTION-EFFECT-01 Phase 3 (#95)

Diagnostic-only causal matrix over 2–3 stubborn dual-answer-defensible cases.
For each case, 6 variants × 4 runs = 24 extractions. 3 cases → 72 extractions.
Zero impact on the 104-case master; zero touch to extract.py. Rides on top
of the live eval harness by rebuilding the payload per variant and re-using
`score_case` from run_question_bank_extraction_eval.py for apples-to-apples
scoring.

Variant table (per WO §4):

    V1  baseline                     (reproduce r5e1 / r5h behavior; anchor)
    V2  era shifted +1 tier          (hold target, vary era)
    V3  pass: pass1 → pass2a          (hold target+era, vary pass)
    V4  mode: open → recognition     (hold target+era+pass, vary mode)
    V5  strip ALL stage context      (anchor for "how much does the prior do?")
    V6  strip target_path only       (hold section+era+pass+mode, drop target)

Output artifacts (under docs/reports/):

    section_effect_matrix_<tag>_<case>_<variant>_run<N>.json   # per-run raw
    section_effect_matrix_<tag>_summary.json                   # consolidated
    section_effect_matrix_<tag>_summary.console.txt            # human readout

The `_CAUSAL.md` readout (§9 of the WO) is authored by the human from the
console + summary JSON — this script produces evidence, not the decision.

Usage:
    ./scripts/run_section_effect_matrix.py --tag se_r5h_20260423 \\
        [--cases case_008,case_018,case_082] \\
        [--variants V1,V2,V3,V4,V5,V6] \\
        [--runs 4] \\
        [--api http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Import master-eval internals (read-only re-use) ─────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

# NOTE: the master module has side effects only inside main(); importing it
# module-level is safe and only costs ~tens of ms.
import run_question_bank_extraction_eval as master_eval  # noqa: E402

CASES_PATH = REPO_ROOT / "data" / "qa" / "question_bank_extraction_cases.json"
REPORT_DIR = REPO_ROOT / "docs" / "reports"

# ── Config ──────────────────────────────────────────────────────────────────

# Default pack from WO §3. case_009 excluded on purpose; case_082 is the
# multi-value control. case_008 / 018 are tier-1.
DEFAULT_CASES: List[str] = ["case_008", "case_018", "case_082"]

DEFAULT_VARIANTS: List[str] = ["V1", "V2", "V3", "V4", "V5", "V6"]

# NARRATOR_PERSON_IDS is function-local in run_question_bank_extraction_eval;
# mirror it here rather than reach inside. If the master drifts, update both.
NARRATOR_PERSON_IDS: Dict[str, str] = {
    "janice-josephine-horne":   "93479171-0b97-4072-bcf0-d44c7f9078ba",
    "kent-james-horne":         "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
    "christopher-todd-horne":   "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
}

# Life-map era ladder (ui/js/life-map.js). Indexed for ±1 shift.
ERA_LADDER: List[str] = [
    "early_childhood",
    "school_years",
    "adolescence",
    "early_adulthood",
    "midlife",
    "later_life",
]


def _shift_era(era: Optional[str], step: int = +1) -> Optional[str]:
    """Shift an era by step on the ladder, clamping at the ends.

    WO §4 V2 asks for era shifted ±1 tier. We default to +1; if the baseline
    is already `later_life`, fall back to -1 so V2 always differs from V1.
    """
    if era is None or era not in ERA_LADDER:
        # If baseline era is unknown, V2 is indistinguishable from V1;
        # return the first ladder entry so V2 still differs.
        return ERA_LADDER[0]
    idx = ERA_LADDER.index(era)
    shifted = idx + step
    if 0 <= shifted < len(ERA_LADDER):
        return ERA_LADDER[shifted]
    # At an edge — try the opposite direction.
    shifted = idx - step
    if 0 <= shifted < len(ERA_LADDER):
        return ERA_LADDER[shifted]
    return era  # degenerate (ladder of length 1); keep baseline


# ── Variant payload construction ────────────────────────────────────────────


def _base_payload(case: dict) -> Dict[str, Any]:
    """Reproduce the exact payload run_live() would build for this case."""
    narrator_reply = case.get("narratorReply") or case.get("answer", "")
    extract_prio = case.get("extractPriority") or case.get("extract_priority")
    case_era = case.get("currentEra") or master_eval._phase_to_era(
        case.get("phase", "")
    )
    case_pass = case.get("currentPass") or "pass1"
    case_mode = case.get("currentMode") or "open"

    return {
        "person_id":           NARRATOR_PERSON_IDS.get(case["narratorId"]),
        "session_id":          f"se_matrix_{case['id']}",
        "answer":              narrator_reply,
        "current_section":     case.get("subTopic"),
        "current_target_path": extract_prio[0] if extract_prio else None,
        "current_target_paths": list(extract_prio) if extract_prio else None,
        "current_phase":       master_eval._phase_to_spine_phase(
                                   case.get("phase", "")),
        "current_era":         case_era,
        "current_pass":        case_pass,
        "current_mode":        case_mode,
    }


def _variant_payload(case: dict, variant: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build the payload for a given variant, returning (payload, stage_snapshot).

    stage_snapshot is the five-field summary (section/target/era/pass/mode)
    recorded verbatim in the per-run JSON so the matrix table can show exactly
    what went down the wire.
    """
    payload = _base_payload(case)

    if variant == "V1":
        pass  # baseline
    elif variant == "V2":
        payload["current_era"] = _shift_era(payload["current_era"], +1)
    elif variant == "V3":
        payload["current_pass"] = "pass2a"
    elif variant == "V4":
        payload["current_mode"] = "recognition"
    elif variant == "V5":
        # Strip ALL stage context. The payload still ships person_id, answer,
        # and session_id so the extractor can run; everything else that was
        # added by SECTION-EFFECT Phase 2 goes to None.
        for k in ("current_section", "current_target_path",
                  "current_target_paths", "current_phase",
                  "current_era", "current_pass", "current_mode"):
            payload[k] = None
    elif variant == "V6":
        # Strip target_path only — keep section/era/pass/mode baseline.
        payload["current_target_path"] = None
        payload["current_target_paths"] = None
    else:
        raise ValueError(f"unknown variant: {variant}")

    stage_snapshot = {
        "section":     payload["current_section"],
        "target_path": payload["current_target_path"],
        "era":         payload["current_era"],
        "pass":        payload["current_pass"],
        "mode":        payload["current_mode"],
    }
    return payload, stage_snapshot


# ── Single extraction call ──────────────────────────────────────────────────


def _post_extraction(
    api_base: str,
    payload: Dict[str, Any],
    timeout_s: int = 90,
) -> Tuple[List[dict], str, int]:
    """POST /api/extract-fields, return (items, method, elapsed_ms)."""
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' package required. pip install requests",
              file=sys.stderr)
        sys.exit(1)
    endpoint = f"{api_base.rstrip('/')}/api/extract-fields"
    t0 = time.time()
    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout_s)
        elapsed_ms = round((time.time() - t0) * 1000)
        if resp.status_code == 200:
            data = resp.json()
            return (data.get("items", []) or []), data.get("method", "unknown"), elapsed_ms
        else:
            return [], f"http_{resp.status_code}", elapsed_ms
    except Exception as e:
        elapsed_ms = round((time.time() - t0) * 1000)
        return [], f"error_{type(e).__name__}", elapsed_ms


def _winning_via_set(score_result: Dict[str, Any]) -> List[str]:
    """Pull the set of `winning_via` markers from score_case's truth zones.

    This is the `pass@alt` signal — if any truth zone entry was credited via
    alt_defensible_path / alt_defensible_value / alt_defensible_path_and_value,
    that's evidence the scorer's alt-credit policy fired.
    """
    out = set()
    tz_details = score_result.get("truth_zone_details") or {}
    # tz_details may be {fieldPath: {zone:..., winning_via:...}} or similar;
    # we scan for any nested `winning_via` string.
    def _walk(node):
        if isinstance(node, dict):
            wv = node.get("winning_via")
            if isinstance(wv, str):
                out.add(wv)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
    _walk(tz_details)
    return sorted(out)


# ── Per-(case,variant) stability consolidation ──────────────────────────────


def _consolidate_slot(per_run: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Condense N runs of a single (case, variant) slot into a stability row."""
    if not per_run:
        return {
            "runs_completed": 0,
            "path_set": [],
            "path_set_n_runs": 0,
            "emission_counts": [],
            "emission_count_median": None,
            "methods": [],
            "method_modal": None,
            "scores": [],
            "score_median": None,
            "pass_count": 0,
            "passed_any_run": False,
            "shape_change_across_runs": False,
            "pass_at_alt": False,
            "winning_via_any": [],
            "errors": [],
        }
    path_set_per_run: List[frozenset] = []
    emission_counts: List[int] = []
    methods: List[str] = []
    scores: List[float] = []
    passed: List[bool] = []
    winning_via_all: set = set()
    errors: List[str] = []

    for run in per_run:
        items = run.get("items", []) or []
        paths = frozenset(
            it.get("fieldPath", "")
            for it in items
            if it.get("fieldPath")
        )
        path_set_per_run.append(paths)
        emission_counts.append(len(items))
        m = run.get("method") or "?"
        methods.append(m)
        if m.startswith("error_") or m.startswith("http_"):
            errors.append(m)
        sc = run.get("score_result") or {}
        scores.append(float(sc.get("overall_score") or 0.0))
        passed.append(bool(sc.get("pass")))
        for wv in run.get("winning_via") or []:
            winning_via_all.add(wv)

    # Union of paths across runs (the "emitted (4-run union)" column in the WO readout).
    union_paths = sorted(set().union(*path_set_per_run)) if path_set_per_run else []
    # shape_change: True if any two runs differ in path set
    shape_change = len({frozenset(ps) for ps in path_set_per_run}) > 1

    # Modal method (most-common); ties broken alphabetically for determinism
    if methods:
        counter = Counter(methods)
        top = counter.most_common()
        top.sort(key=lambda kv: (-kv[1], kv[0]))
        method_modal = top[0][0]
    else:
        method_modal = None

    pass_at_alt = any(
        wv in {"alt_defensible_path",
               "alt_defensible_value",
               "alt_defensible_path_and_value"}
        for wv in winning_via_all
    )

    return {
        "runs_completed":         len(per_run),
        "path_set":               union_paths,
        "path_set_n_runs":        len(path_set_per_run),
        "emission_counts":        emission_counts,
        "emission_count_median":  (statistics.median(emission_counts)
                                    if emission_counts else None),
        "methods":                methods,
        "method_modal":           method_modal,
        "scores":                 [round(s, 3) for s in scores],
        "score_median":           round(statistics.median(scores), 3)
                                    if scores else None,
        "pass_count":             sum(1 for p in passed if p),
        "passed_any_run":         any(passed),
        "shape_change_across_runs": shape_change,
        "pass_at_alt":            pass_at_alt,
        "winning_via_any":        sorted(winning_via_all),
        "errors":                 errors,
    }


# ── Cross-variant comparison (evidence for Q1/Q2/Q3) ────────────────────────


def _compare_variants(slots: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """For a single case, compare each variant's path-set union to V1.

    Yields per-variant: added, removed, same_count, emission_count_delta,
    method_changed, plus Q1/Q2/Q3 signed-count evidence lines.
    """
    v1 = slots.get("V1")
    if v1 is None:
        return {"note": "V1 missing — cannot compare"}
    v1_paths = set(v1.get("path_set") or [])
    v1_count = v1.get("emission_count_median")
    v1_method = v1.get("method_modal")

    per_variant_diff: Dict[str, Any] = {}
    for vname, slot in slots.items():
        paths = set(slot.get("path_set") or [])
        added = sorted(paths - v1_paths)
        removed = sorted(v1_paths - paths)
        ec = slot.get("emission_count_median")
        delta = None
        if ec is not None and v1_count is not None:
            delta = ec - v1_count
        per_variant_diff[vname] = {
            "added_paths":            added,
            "removed_paths":          removed,
            "path_set_same":          (not added and not removed),
            "emission_count_delta":   delta,
            "method_changed":         (slot.get("method_modal") != v1_method),
        }

    # Attribution evidence — raw counts only; the human calls YES/NO/IND.
    def _diff_size(vname: str) -> int:
        d = per_variant_diff.get(vname, {})
        return len(d.get("added_paths", [])) + len(d.get("removed_paths", []))

    q1_diffs = {v: _diff_size(v) for v in ("V2", "V3", "V4") if v in slots}
    q2_diff = _diff_size("V6") if "V6" in slots else None
    q3_diff = _diff_size("V5") if "V5" in slots else None

    return {
        "per_variant_vs_v1": per_variant_diff,
        "q1_path_diff_counts": q1_diffs,            # evidence for Q1
        "q2_path_diff_count":  q2_diff,             # evidence for Q2
        "q3_path_diff_count":  q3_diff,             # evidence for Q3
    }


# ── Main ────────────────────────────────────────────────────────────────────


def _load_cases_by_id(wanted: List[str]) -> Dict[str, dict]:
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    all_cases = payload.get("cases") if isinstance(payload, dict) else payload
    by_id = {c["id"]: c for c in all_cases if c.get("id") in wanted}
    missing = set(wanted) - set(by_id.keys())
    if missing:
        print(f"ERROR: cases not found in {CASES_PATH.name}: "
              f"{sorted(missing)}", file=sys.stderr)
        sys.exit(1)
    return by_id


def _write_per_run(
    tag: str,
    case_id: str,
    variant: str,
    run_idx: int,
    blob: Dict[str, Any],
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = (REPORT_DIR /
            f"section_effect_matrix_{tag}_{case_id}_{variant}_run{run_idx}.json")
    path.write_text(json.dumps(blob, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")
    return path


def _render_console(
    tag: str,
    summary: Dict[str, Any],
) -> str:
    lines: List[str] = []
    w = lines.append
    w("=" * 78)
    w(f"  SECTION-EFFECT Phase 3 matrix — tag={tag}")
    w("=" * 78)
    meta = summary.get("meta", {})
    w(f"  cases    : {', '.join(meta.get('cases', []))}")
    w(f"  variants : {', '.join(meta.get('variants', []))}")
    w(f"  runs/cell: {meta.get('runs_per_cell')}")
    w(f"  total    : {meta.get('total_extractions_planned')} planned, "
      f"{meta.get('total_extractions_attempted')} attempted, "
      f"{meta.get('total_errors')} errors")
    w(f"  api_base : {meta.get('api_base')}")
    w("")

    # Per-case slot tables + Q1/Q2/Q3 counts
    for case_id in meta.get("cases", []):
        case_block = summary["per_case"].get(case_id) or {}
        w(f"  ── {case_id}  ({case_block.get('narrator_id')}"
          f" / phase={case_block.get('phase')}"
          f" / subTopic={case_block.get('sub_topic')}"
          f" / baseline_era={case_block.get('baseline_era')}) ──")
        w(f"    {'var':<4}{'era':<18}{'pass':<8}{'mode':<14}"
          f"{'paths':<6}{'emit':<6}{'method':<16}{'pass':<6}{'shape':<6}"
          f"{'@alt':<6}")
        slots = case_block.get("slots", {})
        for v in meta.get("variants", []):
            slot = slots.get(v) or {}
            stage = slot.get("stage") or {}
            nruns = slot.get("runs_completed", 0)
            pcount = slot.get("pass_count", 0)
            pn = f"{pcount}/{nruns}"
            sm = slot.get("score_median")
            w(f"    {v:<4}"
              f"{(stage.get('era') or '—'):<18}"
              f"{(stage.get('pass') or '—'):<8}"
              f"{(stage.get('mode') or '—'):<14}"
              f"{len(slot.get('path_set') or []):<6}"
              f"{(slot.get('emission_count_median') or 0):<6}"
              f"{(slot.get('method_modal') or '?')[:14]:<16}"
              f"{pn:<6}"
              f"{('chg' if slot.get('shape_change_across_runs') else '·'):<6}"
              f"{('Y' if slot.get('pass_at_alt') else '·'):<6}")
        w("")
        cmp = case_block.get("compare_vs_v1") or {}
        w(f"    Path-diff vs V1 (adds + removes, union over runs):")
        q1 = cmp.get("q1_path_diff_counts") or {}
        w(f"      Q1 target-held, era/pass/mode vary : "
          + "  ".join(f"V{k[-1]}={v}" for k, v in q1.items()))
        w(f"      Q2 section-held, target stripped    : V6={cmp.get('q2_path_diff_count')}")
        w(f"      Q3 stage stripped entirely          : V5={cmp.get('q3_path_diff_count')}")
        w("")

    # Smoke-test line — V1 scores vs r5h/r5j master baseline (if available).
    # The matrix can't read the master JSON by itself; author the CAUSAL.md
    # section manually with side-by-side numbers.
    w("  NOTE: script emits evidence only. Author Q1/Q2/Q3 YES/NO/IND + decision")
    w("        (ADOPT/PARK/ITERATE/ESCALATE) in docs/reports/")
    w("        WO-EX-SECTION-EFFECT-01_CAUSAL.md using this summary + the")
    w(f"        JSON at section_effect_matrix_{tag}_summary.json.")
    w("=" * 78)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="WO-EX-SECTION-EFFECT-01 Phase 3 causal matrix (#95)"
    )
    parser.add_argument("--tag", required=True,
                        help="Suffix for output files, e.g. se_r5h_20260423")
    parser.add_argument("--cases", default=",".join(DEFAULT_CASES),
                        help="Comma-separated case IDs "
                             f"(default: {','.join(DEFAULT_CASES)})")
    parser.add_argument("--variants", default=",".join(DEFAULT_VARIANTS),
                        help="Comma-separated variants "
                             f"(default: {','.join(DEFAULT_VARIANTS)})")
    parser.add_argument("--runs", type=int, default=4,
                        help="Runs per (case, variant) cell (default: 4)")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="API base URL (default: http://localhost:8000)")
    parser.add_argument("--timeout", type=int, default=90,
                        help="Per-request timeout in seconds (default: 90)")
    args = parser.parse_args()

    cases_wanted = [c.strip() for c in args.cases.split(",") if c.strip()]
    variants_wanted = [v.strip() for v in args.variants.split(",") if v.strip()]
    unknown_variants = [v for v in variants_wanted if v not in DEFAULT_VARIANTS]
    if unknown_variants:
        print(f"ERROR: unknown variants {unknown_variants}; "
              f"allowed: {DEFAULT_VARIANTS}", file=sys.stderr)
        sys.exit(1)

    cases_by_id = _load_cases_by_id(cases_wanted)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    total_planned = len(cases_wanted) * len(variants_wanted) * args.runs
    total_attempted = 0
    total_errors = 0

    print(f"─── SECTION-EFFECT Phase 3 matrix ───")
    print(f"    tag       : {args.tag}")
    print(f"    cases     : {cases_wanted}")
    print(f"    variants  : {variants_wanted}")
    print(f"    runs/cell : {args.runs}")
    print(f"    total     : {total_planned} extractions planned")
    print(f"    api_base  : {args.api}")
    print()

    per_case_block: Dict[str, Any] = {}

    for case_id in cases_wanted:
        case = cases_by_id[case_id]
        case_block: Dict[str, Any] = {
            "narrator_id":  case.get("narratorId"),
            "phase":        case.get("phase"),
            "sub_topic":    case.get("subTopic"),
            "extract_priority": case.get("extractPriority"),
            "baseline_era": master_eval._phase_to_era(case.get("phase", "")),
            "slots":        {},
        }

        for variant in variants_wanted:
            print(f"  {case_id}  {variant}  ", end="", flush=True)
            payload, stage_snapshot = _variant_payload(case, variant)

            per_run_blobs: List[Dict[str, Any]] = []
            for run_idx in range(1, args.runs + 1):
                items, method, elapsed_ms = _post_extraction(
                    args.api, payload, timeout_s=args.timeout
                )
                total_attempted += 1
                if method.startswith("error_") or method.startswith("http_"):
                    total_errors += 1

                # Score with the master scorer for apples-to-apples vs master
                # eval. Pass case + extracted items; score_case returns the
                # per-field / truth-zone detail block. We keep the full block
                # so the winning_via set can be reconstructed downstream.
                score_result = master_eval.score_case(case, items)

                # Compact raw items (value-trimmed) to keep JSON lean
                compact_items = []
                for it in items:
                    val = it.get("value", "")
                    if isinstance(val, str) and len(val) > 140:
                        val = val[:140] + "…"
                    compact_items.append({
                        "fieldPath":  it.get("fieldPath", ""),
                        "value":      val,
                        "confidence": it.get("confidence"),
                    })

                winning_via = _winning_via_set(score_result)

                blob = {
                    "case_id":       case_id,
                    "variant":       variant,
                    "run":           run_idx,
                    "tag":           args.tag,
                    "stage":         stage_snapshot,
                    "payload_echo": {
                        k: payload.get(k) for k in (
                            "current_section", "current_target_path",
                            "current_target_paths", "current_phase",
                            "current_era", "current_pass", "current_mode",
                        )
                    },
                    "method":        method,
                    "elapsed_ms":    elapsed_ms,
                    "items":         compact_items,
                    "score_result": {
                        "pass":          bool(score_result.get("pass")),
                        "overall_score": round(
                            float(score_result.get("overall_score") or 0.0), 3),
                        "v2_score":      round(
                            float(score_result.get("v2_score") or 0.0), 3),
                        "failure_categories":
                            score_result.get("failure_categories") or [],
                        "truth_zone_scores":
                            score_result.get("truth_zone_scores") or {},
                        "must_not_write_violations":
                            score_result.get("must_not_write_violations") or [],
                    },
                    "winning_via":   winning_via,
                }
                per_run_blobs.append(blob)
                _write_per_run(args.tag, case_id, variant, run_idx, blob)
                print(f"r{run_idx}:{'P' if blob['score_result']['pass'] else 'F'}"
                      f"({blob['score_result']['overall_score']})",
                      end=" ", flush=True)
            print()

            # Slot stability
            slot_stats = _consolidate_slot(per_run_blobs)
            slot_stats["stage"] = stage_snapshot
            case_block["slots"][variant] = slot_stats

        # Cross-variant comparison (Q1/Q2/Q3 evidence counts)
        case_block["compare_vs_v1"] = _compare_variants(case_block["slots"])
        per_case_block[case_id] = case_block

    # ── Write consolidated summary ───────────────────────────────────────────
    summary = {
        "_wo":       "WO-EX-SECTION-EFFECT-01 Phase 3 (#95)",
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "meta": {
            "tag":                        args.tag,
            "cases":                      cases_wanted,
            "variants":                   variants_wanted,
            "runs_per_cell":              args.runs,
            "total_extractions_planned":  total_planned,
            "total_extractions_attempted": total_attempted,
            "total_errors":               total_errors,
            "api_base":                   args.api,
            "cases_path":                 str(CASES_PATH),
        },
        "per_case":  per_case_block,
    }

    summary_path = REPORT_DIR / f"section_effect_matrix_{args.tag}_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    console_text = _render_console(args.tag, summary)
    console_path = REPORT_DIR / f"section_effect_matrix_{args.tag}_summary.console.txt"
    console_path.write_text(console_text, encoding="utf-8")

    print()
    print(console_text)
    print(f"Summary JSON    → {summary_path}")
    print(f"Summary console → {console_path}")

    # Exit nonzero if ANY errors — catches stack hiccups that would otherwise
    # silently corrupt the matrix
    if total_errors > 0:
        print(f"\nWARN: {total_errors} extractions errored. Re-run affected slots.",
              file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
