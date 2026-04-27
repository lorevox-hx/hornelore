#!/usr/bin/env python3
"""WO-EVAL-CANON-REBUILD-01 — canon-grounded eval runner.

Minimal sibling of run_question_bank_extraction_eval.py that targets
data/qa/canon_grounded_cases.json. Reuses score_case + phase helpers
from the master runner so scoring stays apples-to-apples with r5a.

Why a separate runner:
  - Keeps the 104-case master corpus untouched as the r4i/r5a
    regression guard.
  - Canon-grounded cases are authored strictly from ui/templates/*.json
    + Chris's 2026-04-20 corrections. They test whether the extractor
    can pull facts that are provably true in canon, as opposed to
    the older test cases where some narratorReplies were Claude-
    invented.

Usage:
  python scripts/run_canon_grounded_eval.py --tag cg01 \
      --api http://localhost:8000

Output (auto-tagged):
  docs/reports/canon_grounded_<tag>.json
  docs/reports/canon_grounded_<tag>.console.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = REPO_ROOT / "data" / "qa" / "canon_grounded_cases.json"
REPORT_DIR = REPO_ROOT / "docs" / "reports"

# Import score_case + helpers from the master runner so scoring is
# byte-stable with r5a.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
try:
    from run_question_bank_extraction_eval import (  # type: ignore
        score_case,
        _phase_to_era,
        _phase_to_spine_phase,
        _confidence_stats,
    )
except Exception as e:  # pragma: no cover
    print(f"FATAL: could not import master scorer: {e}")
    sys.exit(2)

# Live-mode person_id map (mirrors master runner's NARRATOR_PERSON_IDS).
NARRATOR_PERSON_IDS = {
    "janice-josephine-horne": "93479171-0b97-4072-bcf0-d44c7f9078ba",
    "kent-james-horne":       "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
    "christopher-todd-horne": "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
}


def load_cases() -> List[Dict[str, Any]]:
    if not CASES_PATH.exists():
        sys.exit(f"cases file not found: {CASES_PATH}")
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


def run_live(cases: List[Dict[str, Any]], api_base: str) -> List[Dict[str, Any]]:
    try:
        import requests  # type: ignore
    except ImportError:
        sys.exit("ERROR: 'requests' required for live mode. pip install requests")

    endpoint = f"{api_base.rstrip('/')}/api/extract-fields"
    results: List[Dict[str, Any]] = []

    for case in cases:
        person_id = NARRATOR_PERSON_IDS.get(case["narratorId"])
        if not person_id:
            print(f"  SKIP {case['id']}: no person_id for {case['narratorId']}")
            continue

        narrator_reply = case.get("narratorReply", "")
        extract_prio = case.get("extractPriority") or []

        era  = case.get("currentEra")  or _phase_to_era(case.get("phase", ""))
        pss  = case.get("currentPass") or "pass1"
        mode = case.get("currentMode") or "open"

        payload = {
            "person_id":           person_id,
            "session_id":          f"cg_eval_{case['id']}",
            "answer":              narrator_reply,
            "current_section":     case.get("subTopic"),
            "current_target_path": extract_prio[0] if extract_prio else None,
            "current_target_paths": list(extract_prio) if extract_prio else None,
            "current_phase":       _phase_to_spine_phase(case.get("phase", "")),
            "current_era":         era,
            "current_pass":        pss,
            "current_mode":        mode,
        }

        try:
            t0 = time.time()
            resp = requests.post(endpoint, json=payload, timeout=90)
            elapsed = time.time() - t0

            if resp.status_code == 200:
                data = resp.json()
                extracted_items = data.get("items", [])
                method = data.get("method", "unknown")
            else:
                extracted_items = []
                method = f"http_{resp.status_code}"
                print(f"  WARN {case['id']}: HTTP {resp.status_code}")
        except Exception as ex:
            extracted_items = []
            method = f"error_{type(ex).__name__}"
            elapsed = 0.0
            print(f"  ERROR {case['id']}: {ex}")

        result = score_case(case, extracted_items)
        result["case_id"]               = case["id"]
        result["narratorId"]            = case["narratorId"]
        result["phase"]                 = case["phase"]
        result["subTopic"]              = case["subTopic"]
        result["expectedBehavior"]      = case.get("expectedBehavior", "")
        result["currentExtractorExpected"] = case.get("currentExtractorExpected", True)
        result["mode"]                  = "live"
        result["method"]                = method
        result["elapsed_ms"]            = round(elapsed * 1000)
        result["extracted_count"]       = len(extracted_items)
        result["current_era"]           = era
        result["current_pass"]          = pss
        result["current_mode"]          = mode
        result["confidence_stats"]      = _confidence_stats(extracted_items)

        # Compact raw items for console readability.
        compact = []
        for item in extracted_items:
            val = item.get("value", "")
            if isinstance(val, str) and len(val) > 100:
                val = val[:100] + "…"
            compact.append({
                "fieldPath":  item.get("fieldPath", ""),
                "value":      val,
                "confidence": item.get("confidence"),
            })
        result["raw_items"] = compact

        status = "PASS" if result.get("pass") else "FAIL"
        print(f"  {status} {case['id']} ({case['narratorId'].split('-')[0]}) "
              f"score={result.get('overall_score', 0):.2f} "
              f"items={len(extracted_items)}  [{elapsed*1000:.0f}ms]")

        results.append(result)

    return results


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("pass"))
    failed = total - passed

    by_narrator: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0})
    by_category: Dict[str, int] = defaultdict(int)
    mnw_violations: List[Dict[str, Any]] = []
    misses: List[Dict[str, Any]] = []

    for r in results:
        n = r.get("narratorId", "?")
        by_narrator[n]["total"] += 1
        if r.get("pass"):
            by_narrator[n]["pass"] += 1
        for cat in r.get("failure_categories", []) or []:
            by_category[cat] += 1
        if r.get("tz_scores", {}).get("must_not_write", {}).get("violated", 0) > 0:
            mnw_violations.append({
                "case_id":    r.get("case_id"),
                "narratorId": r.get("narratorId"),
                "violated":   r["tz_scores"]["must_not_write"]["violated"],
            })
        if not r.get("pass"):
            misses.append({
                "case_id":           r.get("case_id"),
                "narratorId":        r.get("narratorId"),
                "subTopic":          r.get("subTopic"),
                "score":             round(r.get("overall_score", 0), 2),
                "failure_categories": r.get("failure_categories", []),
            })

    return {
        "total":           total,
        "pass_count":      passed,
        "fail_count":      failed,
        "pass_pct":        round(100 * passed / total, 1) if total else 0.0,
        "by_narrator":     dict(by_narrator),
        "by_category":     dict(by_category),
        "mnw_violations":  mnw_violations,
        "misses":          misses,
    }


def render_console(summary: Dict[str, Any], results: List[Dict[str, Any]], tag: str) -> str:
    lines: List[str] = []
    lines.append(f"CANON-GROUNDED EVAL — tag={tag}")
    lines.append(f"Generated: {dt.datetime.utcnow().isoformat()}Z")
    lines.append("")
    lines.append(f"Total cases: {summary['total']}")
    lines.append(f"Pass:        {summary['pass_count']} ({summary['pass_pct']}%)")
    lines.append(f"Fail:        {summary['fail_count']}")
    lines.append("")
    lines.append("By narrator:")
    for nar, stats in sorted(summary["by_narrator"].items()):
        lines.append(f"  {nar:<28} {stats['pass']:>2}/{stats['total']:<2}")
    lines.append("")
    if summary["mnw_violations"]:
        lines.append(f"must_not_write violations: {len(summary['mnw_violations'])}")
        for v in summary["mnw_violations"]:
            lines.append(f"  {v['case_id']} ({v['narratorId']}) — violated={v['violated']}")
        lines.append("")
    else:
        lines.append("must_not_write violations: 0")
        lines.append("")
    if summary["by_category"]:
        lines.append("Failure categories:")
        for cat, n in sorted(summary["by_category"].items(), key=lambda kv: -kv[1]):
            lines.append(f"  {cat:<28} {n}")
        lines.append("")
    if summary["misses"]:
        lines.append("Named misses:")
        for m in summary["misses"]:
            cats = ",".join(m["failure_categories"]) or "—"
            lines.append(f"  {m['case_id']} ({m['narratorId']}) "
                         f"score={m['score']} sub={m['subTopic']}  [{cats}]")
        lines.append("")
    else:
        lines.append("Named misses: none")
        lines.append("")

    # Per-case compact log.
    lines.append("PER-CASE:")
    for r in results:
        status = "PASS" if r.get("pass") else "FAIL"
        lines.append(f"  [{status}] {r.get('case_id')} "
                     f"({r.get('narratorId','?').split('-')[0]}) "
                     f"score={r.get('overall_score',0):.2f} "
                     f"items={r.get('extracted_count',0)} "
                     f"[{r.get('elapsed_ms',0)}ms]")
        for item in r.get("raw_items", []):
            lines.append(f"      → {item['fieldPath']:<40} = {item['value']!r}"
                         f"  (c={item.get('confidence')})")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tag", default="cg01", help="report suffix (e.g. cg01, cg02)")
    ap.add_argument("--api", default="http://localhost:8000", help="API base URL")
    ap.add_argument("--out-dir", default=None, help="override report dir")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases()
    print(f"[cg-eval] loaded {len(cases)} cases from {CASES_PATH.name}")
    print(f"[cg-eval] tag={args.tag}  api={args.api}")
    print("")

    results = run_live(cases, args.api)
    summary = build_summary(results)

    report = {
        "_tag":       args.tag,
        "_generated": dt.datetime.utcnow().isoformat() + "Z",
        "_cases_file": str(CASES_PATH.relative_to(REPO_ROOT)),
        "_api":        args.api,
        "summary":     summary,
        "results":     results,
    }

    json_path    = out_dir / f"canon_grounded_{args.tag}.json"
    console_path = out_dir / f"canon_grounded_{args.tag}.console.txt"

    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    console_path.write_text(render_console(summary, results, args.tag), encoding="utf-8")

    print("")
    print(f"[cg-eval] wrote {json_path.relative_to(REPO_ROOT)}")
    print(f"[cg-eval] wrote {console_path.relative_to(REPO_ROOT)}")
    print("")
    print(f"TOPLINE: {summary['pass_count']}/{summary['total']} "
          f"({summary['pass_pct']}%)")
    print(f"  must_not_write violations: {len(summary['mnw_violations'])}")
    for nar, stats in sorted(summary["by_narrator"].items()):
        print(f"  {nar:<28} {stats['pass']}/{stats['total']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
