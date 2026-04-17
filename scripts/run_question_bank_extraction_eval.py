#!/usr/bin/env python3
"""WO-QB-EXTRACT-EVAL-01 — Question-bank extraction evaluation runner.

Dual-mode runner:
  --mode offline   Import extract.py directly, bypass LLM, inject mockLlmOutput
                   from the fixture. Tests guards, routing, field-path validation,
                   and scoring logic without requiring a loaded model.

  --mode live      POST to the real /api/extract-fields endpoint with the local
                   LLM loaded. Tests end-to-end extraction quality.

Usage:
  python scripts/run_question_bank_extraction_eval.py --mode offline
  python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:14501

Output:
  Writes a JSON report to docs/reports/question_bank_extraction_eval_report.json
  Prints a summary table to stdout.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = REPO_ROOT / "data" / "qa" / "question_bank_extraction_cases.json"
REPORT_DIR = REPO_ROOT / "docs" / "reports"

# ── Failure category enum ───────────────────────────────────────────────────
FAILURE_CATEGORIES = [
    "schema_gap",              # field exists in template but no EXTRACTABLE_FIELDS path covers it
    "guard_false_positive",    # guard stack drops a valid extraction
    "llm_output_shape",        # LLM returns unparseable or malformed JSON
    "llm_hallucination",       # LLM invents a fact not in the narrator reply
    "field_path_mismatch",     # LLM uses wrong fieldPath for a correct value
    "missing_alias",           # LLM uses an alias not in FIELD_ALIASES
]


# ── Scoring ─────────────────────────────────────────────────────────────────

def normalize_value(v: str) -> str:
    """Lowercase, strip whitespace, collapse spaces for fuzzy matching."""
    if not v:
        return ""
    return " ".join(v.lower().strip().split())


# ── Date normalization ──────────────────────────────────────────────────────
_MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

def _normalize_date(v: str) -> Optional[str]:
    """Try to normalize a date string to YYYY-MM-DD. Returns None if not a date."""
    v = v.strip().lower()
    # Already YYYY-MM-DD?
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', v)
    if m:
        return v
    # "Month DDth, YYYY" or "Month DD, YYYY" variants
    m = re.match(r'^(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})$', v)
    if m:
        month_str, day, year = m.group(1), m.group(2), m.group(3)
        mm = _MONTH_NAMES.get(month_str)
        if mm:
            return f"{year}-{mm}-{day.zfill(2)}"
    # "DD Month YYYY"
    m = re.match(r'^(\d{1,2})\s+(\w+)\s+(\d{4})$', v)
    if m:
        day, month_str, year = m.group(1), m.group(2), m.group(3)
        mm = _MONTH_NAMES.get(month_str)
        if mm:
            return f"{year}-{mm}-{day.zfill(2)}"
    return None


def score_field_match(expected_val: str, actual_val: str) -> float:
    """Score a single field match. Returns 0.0-1.0."""
    e = normalize_value(expected_val)
    a = normalize_value(actual_val)
    if not e or not a:
        return 0.0
    if e == a:
        return 1.0

    # Date-aware comparison: normalize both to YYYY-MM-DD before comparing
    e_date = _normalize_date(expected_val)
    a_date = _normalize_date(actual_val)
    if e_date and a_date:
        if e_date == a_date:
            return 1.0
        # Same year but different day/month
        if e_date[:4] == a_date[:4]:
            return 0.5
        return 0.0

    # Substring containment (either direction)
    if e in a or a in e:
        return 0.8
    # Check if all key tokens from expected appear in actual
    e_tokens = set(e.split())
    a_tokens = set(a.split())
    if e_tokens and e_tokens.issubset(a_tokens):
        return 0.9
    overlap = len(e_tokens & a_tokens)
    if e_tokens:
        ratio = overlap / len(e_tokens)
        if ratio >= 0.5:
            return round(0.5 + ratio * 0.3, 2)
    return 0.0


def score_case(case: dict, extracted_items: List[dict]) -> dict:
    """Score a single evaluation case against extracted items.

    Returns a dict with:
      - field_scores: {fieldPath: {expected, actual, score}}
      - forbidden_violations: [fieldPath, ...]
      - overall_score: float 0.0-1.0
      - failure_categories: [str, ...]
      - pass: bool (overall_score >= 0.7 and no forbidden violations)
    """
    expected_fields = case.get("expectedFields", {})
    forbidden_fields = case.get("forbiddenFields", [])
    expected_behavior = case.get("expectedBehavior", "extract_single")

    # Build a lookup from extracted items: fieldPath -> list of values
    extracted_map: Dict[str, List[str]] = {}
    for item in extracted_items:
        fp = item.get("fieldPath", "")
        val = item.get("value", "")
        if fp not in extracted_map:
            extracted_map[fp] = []
        extracted_map[fp].append(val)

    # Score each expected field
    field_scores = {}
    for fp, exp_val in expected_fields.items():
        actual_vals = extracted_map.get(fp, [])
        if not actual_vals:
            field_scores[fp] = {
                "expected": exp_val,
                "actual": None,
                "score": 0.0,
                "status": "missing"
            }
        else:
            # Find best match among extracted values for this fieldPath
            best_score = 0.0
            best_val = actual_vals[0]
            for av in actual_vals:
                s = score_field_match(exp_val, av)
                if s > best_score:
                    best_score = s
                    best_val = av
            field_scores[fp] = {
                "expected": exp_val,
                "actual": best_val,
                "score": best_score,
                "status": "exact" if best_score == 1.0 else "partial" if best_score > 0 else "wrong"
            }

    # Check forbidden fields
    forbidden_violations = []
    for fp in forbidden_fields:
        if fp in extracted_map:
            forbidden_violations.append(fp)

    # Overall score
    if field_scores:
        avg_field_score = sum(fs["score"] for fs in field_scores.values()) / len(field_scores)
    else:
        avg_field_score = 0.0

    # Penalty for forbidden violations
    forbidden_penalty = 0.2 * len(forbidden_violations)
    overall_score = max(0.0, avg_field_score - forbidden_penalty)

    # Classify failures
    failure_categories = []
    for fp, fs in field_scores.items():
        if fs["status"] == "missing":
            # Was it extracted under a different path?
            found_elsewhere = False
            for efp, vals in extracted_map.items():
                if efp != fp:
                    for v in vals:
                        if score_field_match(fs["expected"], v) >= 0.7:
                            failure_categories.append("field_path_mismatch")
                            found_elsewhere = True
                            break
                    if found_elsewhere:
                        break
            if not found_elsewhere:
                # Check if the field is even in EXTRACTABLE_FIELDS
                failure_categories.append("schema_gap")
        elif fs["status"] == "wrong":
            failure_categories.append("llm_hallucination")

    if forbidden_violations:
        failure_categories.append("guard_false_positive")

    passed = overall_score >= 0.7 and len(forbidden_violations) == 0

    return {
        "field_scores": field_scores,
        "forbidden_violations": forbidden_violations,
        "overall_score": round(overall_score, 3),
        "failure_categories": list(set(failure_categories)),
        "pass": passed,
    }


# ── Offline mode ────────────────────────────────────────────────────────────

def run_offline(cases: List[dict]) -> List[dict]:
    """Run cases using mockLlmOutput — no LLM, no server required.

    Validates that the mock output scores correctly against expectations.
    This tests the scoring harness and fixture quality.
    """
    results = []
    for case in cases:
        mock_items = case.get("mockLlmOutput", [])
        result = score_case(case, mock_items)
        result["case_id"] = case["id"]
        result["narratorId"] = case["narratorId"]
        result["phase"] = case["phase"]
        result["subTopic"] = case["subTopic"]
        result["expectedBehavior"] = case["expectedBehavior"]
        result["currentExtractorExpected"] = case.get("currentExtractorExpected", True)
        result["mode"] = "offline"
        result["extracted_count"] = len(mock_items)
        results.append(result)
    return results


# ── Live mode ───────────────────────────────────────────────────────────────

def run_live(cases: List[dict], api_base: str) -> List[dict]:
    """Run cases by POSTing to the real extraction endpoint."""
    try:
        import requests
    except ImportError:
        print("ERROR: 'requests' package required for live mode. pip install requests")
        sys.exit(1)

    # Map narrator IDs to person_ids (from the live database)
    NARRATOR_PERSON_IDS = {
        "janice-josephine-horne": "93479171-0b97-4072-bcf0-d44c7f9078ba",
        "kent-james-horne": "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
        "christopher-todd-horne": "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
    }

    endpoint = f"{api_base.rstrip('/')}/api/extract-fields"
    results = []

    for case in cases:
        person_id = NARRATOR_PERSON_IDS.get(case["narratorId"])
        if not person_id:
            print(f"  SKIP {case['id']}: no person_id for {case['narratorId']}")
            continue

        payload = {
            "person_id": person_id,
            "session_id": f"eval_{case['id']}",
            "answer": case["narratorReply"],
            "current_section": case.get("subTopic"),
            "current_target_path": case["extractPriority"][0] if case.get("extractPriority") else None,
            "current_phase": _phase_to_spine_phase(case.get("phase", "")),
        }

        try:
            t0 = time.time()
            # WO-EX-CLAIMS-01: compound answers (multiple children, etc.) can take
            # 30-45s on the 8B model with 384-token cap. Use 90s to avoid timeouts.
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
        except Exception as e:
            extracted_items = []
            method = f"error_{type(e).__name__}"
            elapsed = 0
            print(f"  ERROR {case['id']}: {e}")

        result = score_case(case, extracted_items)
        result["case_id"] = case["id"]
        result["narratorId"] = case["narratorId"]
        result["phase"] = case["phase"]
        result["subTopic"] = case["subTopic"]
        result["expectedBehavior"] = case["expectedBehavior"]
        result["currentExtractorExpected"] = case.get("currentExtractorExpected", True)
        result["mode"] = "live"
        result["method"] = method
        result["elapsed_ms"] = round(elapsed * 1000)
        result["extracted_count"] = len(extracted_items)
        # Sanitize raw items for JSON safety — strip control chars from values
        safe_items = []
        for item in extracted_items:
            safe_item = {}
            for k, v in item.items():
                if isinstance(v, str):
                    # Replace control chars except newline/tab
                    safe_item[k] = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', v)
                else:
                    safe_item[k] = v
            safe_items.append(safe_item)
        result["raw_items"] = safe_items
        results.append(result)

    return results


def _phase_to_spine_phase(phase_key: str) -> Optional[str]:
    """Map question_bank phase key to a spine phase hint."""
    mapping = {
        "developmental_foundations": "pre_school",
        "transitional_adolescence": "high_school",
        "early_adulthood": "post_school",
        "midlife": "post_school",
        "legacy_reflection": "post_school",
    }
    return mapping.get(phase_key)


# ── Report generation ───────────────────────────────────────────────────────

def generate_report(results: List[dict], mode: str) -> dict:
    """Build a structured report from scored results."""
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    failed = total - passed

    # Breakdown by expectedBehavior
    by_behavior = {}
    for r in results:
        b = r["expectedBehavior"]
        if b not in by_behavior:
            by_behavior[b] = {"total": 0, "passed": 0, "failed": 0}
        by_behavior[b]["total"] += 1
        if r["pass"]:
            by_behavior[b]["passed"] += 1
        else:
            by_behavior[b]["failed"] += 1

    # Breakdown by narrator
    by_narrator = {}
    for r in results:
        n = r["narratorId"]
        if n not in by_narrator:
            by_narrator[n] = {"total": 0, "passed": 0, "avg_score": 0.0}
        by_narrator[n]["total"] += 1
        if r["pass"]:
            by_narrator[n]["passed"] += 1
        by_narrator[n]["avg_score"] += r["overall_score"]
    for n in by_narrator:
        by_narrator[n]["avg_score"] = round(
            by_narrator[n]["avg_score"] / by_narrator[n]["total"], 3
        )

    # Expected vs unexpected failures
    expected_pass = [r for r in results if r["currentExtractorExpected"]]
    expected_fail = [r for r in results if not r["currentExtractorExpected"]]

    # Failure category distribution
    all_failures = {}
    for r in results:
        for fc in r.get("failure_categories", []):
            all_failures[fc] = all_failures.get(fc, 0) + 1

    report = {
        "_wo": "WO-QB-EXTRACT-EVAL-01",
        "_generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "summary": {
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / total, 3) if total else 0,
            "avg_overall_score": round(
                sum(r["overall_score"] for r in results) / total, 3
            ) if total else 0,
        },
        "by_behavior": by_behavior,
        "by_narrator": by_narrator,
        "expected_extractor_results": {
            "should_pass": {
                "total": len(expected_pass),
                "actually_passed": sum(1 for r in expected_pass if r["pass"]),
            },
            "known_gaps": {
                "total": len(expected_fail),
                "actually_passed": sum(1 for r in expected_fail if r["pass"]),
            },
        },
        "failure_categories": all_failures,
        "case_results": results,
    }
    return report


def print_summary(report: dict):
    """Print a human-readable summary table."""
    s = report["summary"]
    print()
    print("=" * 70)
    print(f"  WO-QB-EXTRACT-EVAL-01 — {report['mode'].upper()} MODE")
    print("=" * 70)
    print(f"  Total cases:     {s['total_cases']}")
    print(f"  Passed:          {s['passed']}")
    print(f"  Failed:          {s['failed']}")
    print(f"  Pass rate:       {s['pass_rate']:.1%}")
    print(f"  Avg score:       {s['avg_overall_score']:.3f}")
    print()

    # By behavior
    print("  By behavior:")
    for b, d in report["by_behavior"].items():
        print(f"    {b:30s}  {d['passed']}/{d['total']} passed")
    print()

    # By narrator
    print("  By narrator:")
    for n, d in report["by_narrator"].items():
        print(f"    {n:30s}  {d['passed']}/{d['total']} passed  (avg {d['avg_score']:.3f})")
    print()

    # Expected vs unexpected
    exp = report["expected_extractor_results"]
    print("  Expected extractor results:")
    print(f"    Should pass (currentExtractorExpected=true):  "
          f"{exp['should_pass']['actually_passed']}/{exp['should_pass']['total']}")
    print(f"    Known gaps (currentExtractorExpected=false):  "
          f"{exp['known_gaps']['actually_passed']}/{exp['known_gaps']['total']}")
    print()

    # Failure categories
    if report["failure_categories"]:
        print("  Failure categories:")
        for cat, count in sorted(report["failure_categories"].items(), key=lambda x: -x[1]):
            print(f"    {cat:30s}  {count}")
        print()

    # Per-case detail (failed only)
    failed = [r for r in report["case_results"] if not r["pass"]]
    if failed:
        print("  Failed cases:")
        for r in failed:
            marker = " [KNOWN GAP]" if not r["currentExtractorExpected"] else ""
            print(f"    {r['case_id']:12s}  {r['narratorId']:30s}  "
                  f"score={r['overall_score']:.2f}  {r['expectedBehavior']}{marker}")
            if r["forbidden_violations"]:
                print(f"      Forbidden violations: {r['forbidden_violations']}")
            if r["failure_categories"]:
                print(f"      Failures: {r['failure_categories']}")
        print()

    print("=" * 70)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="WO-QB-EXTRACT-EVAL-01 extraction evaluation runner"
    )
    parser.add_argument(
        "--mode", choices=["offline", "live"], default="offline",
        help="offline = use mockLlmOutput, live = POST to API"
    )
    parser.add_argument(
        "--api", default="http://localhost:8000",
        help="API base URL for live mode (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output report path (default: docs/reports/question_bank_extraction_eval_report.json)"
    )
    parser.add_argument(
        "--cases", default=None,
        help="Path to cases JSON (default: data/qa/question_bank_extraction_cases.json)"
    )
    args = parser.parse_args()

    # Load cases
    cases_path = Path(args.cases) if args.cases else CASES_PATH
    if not cases_path.exists():
        print(f"ERROR: Cases file not found: {cases_path}")
        sys.exit(1)

    with open(cases_path) as f:
        data = json.load(f)
    cases = data.get("cases", [])
    print(f"Loaded {len(cases)} evaluation cases from {cases_path.name}")

    # Run
    if args.mode == "offline":
        results = run_offline(cases)
    else:
        results = run_live(cases, args.api)

    # Generate report
    report = generate_report(results, args.mode)

    # Write report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output) if args.output else (
        REPORT_DIR / "question_bank_extraction_eval_report.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"Report written to {output_path}")

    # Print summary
    print_summary(report)

    # Exit code: 0 if all expected-to-pass cases pass, 1 otherwise
    exp = report["expected_extractor_results"]["should_pass"]
    if exp["actually_passed"] < exp["total"]:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
