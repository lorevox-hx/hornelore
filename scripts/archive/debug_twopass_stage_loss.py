#!/usr/bin/env python3
"""WO-EX-TWOPASS-01 — Stage-loss debugger.

Two-step process:
  Step 1: Run 6 cases against API in single-pass mode (flag OFF).
  Step 2: Run same 6 cases against API in two-pass mode (flag ON + debug ON).
          The API writes stage artifacts to docs/reports/twopass_debug_artifacts.jsonl.

Then this script reads both result sets + the debug artifacts file and
produces the fact-loss ledger showing where each expected fact is lost.

Usage:
  # Step 1: API running with HORNELORE_TWOPASS_EXTRACT=0
  python scripts/debug_twopass_stage_loss.py --step single-pass

  # Step 2: Flip to HORNELORE_TWOPASS_EXTRACT=1 + HORNELORE_TWOPASS_DEBUG=1, restart API
  python scripts/debug_twopass_stage_loss.py --step two-pass

  # Step 3: Analyze (no API needed)
  python scripts/debug_twopass_stage_loss.py --step analyze
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

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_PATH = REPO_ROOT / "data" / "qa" / "question_bank_extraction_cases.json"
REPORT_DIR = REPO_ROOT / "docs" / "reports"
SP_RESULTS_PATH = REPORT_DIR / "twopass_debug_singlepass.json"
TP_RESULTS_PATH = REPORT_DIR / "twopass_debug_twopass.json"
ARTIFACTS_PATH = REPORT_DIR / "twopass_debug_artifacts.jsonl"

# ── Debug case selection ─────────────────────────────────────────────────────
DEBUG_CASE_IDS = [
    "case_006",   # extract_multiple regression — retirement + career
    "case_010",   # extract_multiple regression — pet (name + species)
    "case_020",   # extract_single regression — early career
    "case_059",   # extract_compound regression — career progression
    "case_038",   # clarify_before_write — healthy, no extraction expected
    "case_003",   # CONTROL — passes in both single-pass and two-pass
]

NARRATOR_PERSON_IDS = {
    "janice-josephine-horne": "93479171-0b97-4072-bcf0-d44c7f9078ba",
    "kent-james-horne": "4aa0cc2b-1f27-433a-9152-203bb1f69a55",
    "christopher-todd-horne": "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2",
}


def load_debug_cases() -> List[dict]:
    with open(CASES_PATH) as f:
        data = json.load(f)
    all_cases = data if isinstance(data, list) else data.get("cases", data.get("evaluationCases", []))
    return [c for c in all_cases if c["id"] in DEBUG_CASE_IDS]


def normalize_value(v: str) -> str:
    if not v:
        return ""
    return " ".join(v.lower().strip().split())


def value_match(expected: str, actual: str, threshold: float = 0.4) -> bool:
    """Check if key tokens from expected appear in actual."""
    exp_tokens = set(normalize_value(expected).split())
    act_tokens = set(normalize_value(actual).split())
    # Remove stopwords
    stopwords = {"the", "a", "an", "in", "at", "on", "of", "to", "was", "were",
                 "is", "my", "i", "he", "she", "we", "by", "for", "and", "or",
                 "that", "this", "had", "has", "been", "from", "with"}
    exp_tokens -= stopwords
    act_tokens -= stopwords
    if not exp_tokens:
        return False
    overlap = len(exp_tokens & act_tokens) / len(exp_tokens)
    return overlap >= threshold


# ── API runner ───────────────────────────────────────────────────────────────

def run_cases_via_api(cases: List[dict], api_base: str = "http://localhost:8000") -> List[dict]:
    import requests

    results = []
    for case in cases:
        person_id = NARRATOR_PERSON_IDS.get(case["narratorId"])
        payload = {
            "person_id": person_id,
            "session_id": f"debug_{case['id']}",
            "answer": case["narratorReply"],
            "current_section": case.get("subTopic"),
            "current_target_path": case["extractPriority"][0] if case.get("extractPriority") else None,
        }

        try:
            t0 = time.time()
            resp = requests.post(f"{api_base}/api/extract-fields", json=payload, timeout=90)
            elapsed = time.time() - t0
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                method = data.get("method", "unknown")
                raw = data.get("raw_llm_output", "")
            else:
                items, method, raw = [], f"http_{resp.status_code}", ""
                print(f"  WARN {case['id']}: HTTP {resp.status_code}")
        except Exception as e:
            items, method, raw, elapsed = [], f"error_{type(e).__name__}", str(e), 0
            print(f"  ERROR {case['id']}: {e}")

        results.append({
            "case_id": case["id"],
            "narrator": case["narratorId"],
            "behavior": case["expectedBehavior"],
            "answer": case["narratorReply"],
            "section": case.get("subTopic"),
            "expected_fields": case.get("expectedFields", {}),
            "extracted_items": items,
            "method": method,
            "raw_output": raw,
            "elapsed_ms": round(elapsed * 1000),
        })
        print(f"  {case['id']}: {len(items)} items, method={method}, {round(elapsed*1000)}ms")

    return results


# ── Step 1: Single-pass ──────────────────────────────────────────────────────

def step_single_pass():
    print("=" * 70)
    print("  STEP 1: Running 6 debug cases in SINGLE-PASS mode")
    print("  (HORNELORE_TWOPASS_EXTRACT must be 0 / absent)")
    print("=" * 70)

    cases = load_debug_cases()
    print(f"Loaded {len(cases)} cases: {[c['id'] for c in cases]}")

    results = run_cases_via_api(cases)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(SP_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSingle-pass results saved to: {SP_RESULTS_PATH}")
    print("\nNext: flip HORNELORE_TWOPASS_EXTRACT=1 and HORNELORE_TWOPASS_DEBUG=1 in .env,")
    print("restart API, then run: python scripts/debug_twopass_stage_loss.py --step two-pass")


# ── Step 2: Two-pass ─────────────────────────────────────────────────────────

def step_two_pass():
    print("=" * 70)
    print("  STEP 2: Running 6 debug cases in TWO-PASS mode")
    print("  (HORNELORE_TWOPASS_EXTRACT=1 and HORNELORE_TWOPASS_DEBUG=1)")
    print("=" * 70)

    # Clear previous debug artifacts
    if ARTIFACTS_PATH.exists():
        ARTIFACTS_PATH.unlink()
        print(f"Cleared previous artifacts: {ARTIFACTS_PATH}")

    cases = load_debug_cases()
    print(f"Loaded {len(cases)} cases: {[c['id'] for c in cases]}")

    results = run_cases_via_api(cases)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(TP_RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nTwo-pass results saved to: {TP_RESULTS_PATH}")

    if ARTIFACTS_PATH.exists():
        with open(ARTIFACTS_PATH) as f:
            artifact_count = sum(1 for _ in f)
        print(f"Debug artifacts: {artifact_count} records in {ARTIFACTS_PATH}")
    else:
        print("WARNING: No debug artifacts file found! Is HORNELORE_TWOPASS_DEBUG=1?")

    print("\nNext: restore HORNELORE_TWOPASS_EXTRACT=0, restart API,")
    print("then run: python scripts/debug_twopass_stage_loss.py --step analyze")


# ── Step 3: Analyze ──────────────────────────────────────────────────────────

def step_analyze():
    print("=" * 70)
    print("  STEP 3: Analyzing stage-loss across both pipelines")
    print("=" * 70)

    # Load results
    if not SP_RESULTS_PATH.exists():
        print(f"ERROR: Missing {SP_RESULTS_PATH} — run --step single-pass first")
        sys.exit(1)
    if not TP_RESULTS_PATH.exists():
        print(f"ERROR: Missing {TP_RESULTS_PATH} — run --step two-pass first")
        sys.exit(1)

    with open(SP_RESULTS_PATH) as f:
        sp_results = json.load(f)
    with open(TP_RESULTS_PATH) as f:
        tp_results = json.load(f)

    # Load debug artifacts
    artifacts = []
    if ARTIFACTS_PATH.exists():
        with open(ARTIFACTS_PATH) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        artifacts.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    print(f"Loaded: {len(sp_results)} SP results, {len(tp_results)} TP results, {len(artifacts)} debug artifacts")

    # Match artifacts to cases by answer text (order should match)
    # Build artifact lookup by answer prefix
    artifact_by_answer = {}
    for art in artifacts:
        ans = art.get("input", {}).get("answer", "")[:80]
        artifact_by_answer[ans] = art

    # ── Build ledger ─────────────────────────────────────────────────────
    all_ledger = []

    for i, tp_r in enumerate(tp_results):
        case_id = tp_r["case_id"]
        sp_r = next((r for r in sp_results if r["case_id"] == case_id), None)
        expected = tp_r.get("expected_fields", {})
        ans_prefix = tp_r["answer"][:80]
        art = artifact_by_answer.get(ans_prefix)

        case_ledger = {
            "case_id": case_id,
            "behavior": tp_r["behavior"],
            "narrator": tp_r["narrator"],
            "answer_preview": tp_r["answer"][:120],
            "expected_field_count": len(expected),
            "sp_item_count": len(sp_r["extracted_items"]) if sp_r else 0,
            "tp_item_count": len(tp_r["extracted_items"]),
            "artifact_found": art is not None,
            "pass1": {},
            "pass2a": {},
            "pass2b": {},
            "merge": {},
            "facts": [],
        }

        if art:
            p1 = art.get("pass1", {})
            case_ledger["pass1"] = {
                "token_cap": p1.get("token_cap"),
                "raw_length": p1.get("raw_output_length"),
                "looks_truncated": p1.get("looks_truncated"),
                "span_count": p1.get("span_count"),
                "spans": p1.get("spans", []),
                "type_distribution": p1.get("type_distribution", {}),
                "raw_output_preview": (p1.get("raw_output", ""))[:300],
            }
            p2a = art.get("pass2a_rules", {})
            case_ledger["pass2a"] = {
                "classified_count": p2a.get("classified_count"),
                "classified_items": p2a.get("classified_items", []),
                "unresolved_count": p2a.get("unresolved_count"),
                "unresolved_spans": p2a.get("unresolved_spans", []),
            }
            p2b = art.get("pass2b_llm", {})
            case_ledger["pass2b"] = {
                "classified_count": p2b.get("classified_count"),
                "classified_items": p2b.get("classified_items", []),
            }
            merge = art.get("merge", {})
            case_ledger["merge"] = {
                "total_items": merge.get("total_items"),
                "items": merge.get("items", []),
            }

        # ── Per-fact ledger ──────────────────────────────────────────────
        for fp, exp_val in expected.items():
            fact = {
                "field_path": fp,
                "expected_value": exp_val,
                "fate": "unknown",
                "detail": "",
                "sp_found": False,
            }

            # Check single-pass
            if sp_r:
                sp_items = sp_r.get("extracted_items", [])
                fact["sp_found"] = any(
                    i.get("fieldPath") == fp and value_match(exp_val, i.get("value", ""))
                    for i in sp_items
                )
                if not fact["sp_found"]:
                    # Check if value found under wrong path
                    fact["sp_found_wrong_path"] = any(
                        value_match(exp_val, i.get("value", ""))
                        for i in sp_items
                    )

            if not art:
                fact["fate"] = "no_artifact"
                fact["detail"] = "No debug artifact — cannot trace"
                case_ledger["facts"].append(fact)
                continue

            spans = art.get("pass1", {}).get("spans", [])

            # Did any Pass 1 span capture relevant content?
            matching_spans = [
                s for s in spans
                if value_match(exp_val, s.get("text", ""), threshold=0.3)
            ]

            if not matching_spans and not spans:
                fact["fate"] = "pass1_no_spans"
                fact["detail"] = "Pass 1 returned no spans at all"
                case_ledger["facts"].append(fact)
                continue

            if not matching_spans:
                fact["fate"] = "pass1_missed"
                fact["detail"] = f"Pass 1 tagged {len(spans)} spans but none contain key tokens from expected value"
                case_ledger["facts"].append(fact)
                continue

            # Span was tagged — check rules
            rule_items = art.get("pass2a_rules", {}).get("classified_items", [])
            rule_found = any(
                i.get("fieldPath") == fp and value_match(exp_val, i.get("value", ""))
                for i in rule_items
            )

            if rule_found:
                # Check final
                tp_items = tp_r.get("extracted_items", [])
                final_found = any(
                    i.get("fieldPath") == fp and value_match(exp_val, i.get("value", ""))
                    for i in tp_items
                )
                if final_found:
                    fact["fate"] = "survived"
                    fact["detail"] = "Extracted correctly via rules"
                else:
                    fact["fate"] = "stripped_downstream"
                    fact["detail"] = "Rule-classified correctly but lost in downstream filters"
                case_ledger["facts"].append(fact)
                continue

            # Check if rules put it under wrong path
            rule_wrong = any(value_match(exp_val, i.get("value", "")) for i in rule_items)
            if rule_wrong:
                fact["fate"] = "rule_wrong_path"
                wrong_paths = [i.get("fieldPath") for i in rule_items if value_match(exp_val, i.get("value", ""))]
                fact["detail"] = f"Rules mapped to {wrong_paths} instead of {fp}"
                case_ledger["facts"].append(fact)
                continue

            # Check unresolved → Pass 2B
            unresolved = art.get("pass2a_rules", {}).get("unresolved_spans", [])
            in_unresolved = any(
                value_match(exp_val, s.get("text", ""), threshold=0.3)
                for s in unresolved
            )

            if in_unresolved:
                llm_items = art.get("pass2b_llm", {}).get("classified_items", [])
                llm_found = any(
                    i.get("fieldPath") == fp and value_match(exp_val, i.get("value", ""))
                    for i in llm_items
                )
                if llm_found:
                    tp_items = tp_r.get("extracted_items", [])
                    final_found = any(
                        i.get("fieldPath") == fp and value_match(exp_val, i.get("value", ""))
                        for i in tp_items
                    )
                    if final_found:
                        fact["fate"] = "survived"
                        fact["detail"] = "Extracted correctly via Pass 2B LLM"
                    else:
                        fact["fate"] = "stripped_downstream"
                        fact["detail"] = "Pass 2B classified correctly but lost downstream"
                elif any(value_match(exp_val, i.get("value", "")) for i in llm_items):
                    wrong_paths = [i.get("fieldPath") for i in llm_items if value_match(exp_val, i.get("value", ""))]
                    fact["fate"] = "pass2b_wrong_path"
                    fact["detail"] = f"Pass 2B mapped to {wrong_paths} instead of {fp}"
                elif not llm_items:
                    fact["fate"] = "pass2b_empty"
                    fact["detail"] = "Pass 2B returned no items at all"
                else:
                    fact["fate"] = "pass2b_missed"
                    fact["detail"] = "Pass 2B classified other spans but missed this one"
            else:
                fact["fate"] = "rule_skipped_not_unresolved"
                fact["detail"] = "Span in Pass 1 but neither rule-consumed nor in unresolved list (likely negated skip or type mismatch)"

            case_ledger["facts"].append(fact)

        # Check for hallucinated items in two-pass output
        tp_items = tp_r.get("extracted_items", [])
        for item in tp_items:
            ifp = item.get("fieldPath", "")
            ival = item.get("value", "")
            is_expected = any(
                ifp == efp and value_match(ev, ival)
                for efp, ev in expected.items()
            )
            if not is_expected and expected:
                case_ledger["facts"].append({
                    "field_path": ifp,
                    "expected_value": None,
                    "fate": "hallucinated",
                    "detail": f"Two-pass output '{ival}' at {ifp} — not expected",
                    "sp_found": False,
                })

        all_ledger.append(case_ledger)

    # ── Print summary table ──────────────────────────────────────────────
    print()
    print("=" * 120)
    print("  TWO-PASS STAGE-LOSS DEBUG — SUMMARY TABLE")
    print("=" * 120)
    header = f"{'case':<10} {'expect':>6} {'p1_spans':>8} {'rule':>5} {'p2b':>5} {'final_tp':>8} {'final_sp':>8} {'survived':>8} {'dominant loss':<30}"
    print(header)
    print("-" * 120)

    for cl in all_ledger:
        cid = cl["case_id"]
        exp = cl["expected_field_count"]
        p1s = cl["pass1"].get("span_count", "?")
        rul = cl["pass2a"].get("classified_count", "?")
        p2b = cl["pass2b"].get("classified_count", "?")
        ftp = cl["tp_item_count"]
        fsp = cl["sp_item_count"]

        facts = cl["facts"]
        survived = sum(1 for f in facts if f["fate"] == "survived")

        # Dominant loss
        loss_fates = {}
        for f in facts:
            if f["fate"] not in ("survived", "hallucinated", "unknown", "no_artifact"):
                loss_fates[f["fate"]] = loss_fates.get(f["fate"], 0) + 1
        if not loss_fates and survived == exp:
            dominant = "NONE (all survived)"
        elif loss_fates:
            dominant = max(loss_fates, key=loss_fates.get)
        else:
            dominant = "?" if exp == 0 else "unknown"

        print(f"{cid:<10} {exp:>6} {str(p1s):>8} {str(rul):>5} {str(p2b):>5} {ftp:>8} {fsp:>8} {survived:>8} {dominant:<30}")

    # ── Print detailed per-fact ledger ────────────────────────────────────
    print()
    print("=" * 120)
    print("  DETAILED FACT-LOSS LEDGER")
    print("=" * 120)

    for cl in all_ledger:
        cid = cl["case_id"]
        print(f"\n--- {cid} ({cl['behavior']}) [{cl['narrator']}] ---")
        print(f"  Answer: \"{cl['answer_preview']}...\"")
        p1 = cl["pass1"]
        if p1:
            print(f"  Pass 1: {p1.get('span_count','?')} spans, cap={p1.get('token_cap','?')}, "
                  f"truncated={p1.get('looks_truncated','?')}, raw_len={p1.get('raw_length','?')}")
            if p1.get("raw_output_preview"):
                print(f"  Pass 1 raw: {p1['raw_output_preview'][:200]}")
            if p1.get("spans"):
                for s in p1["spans"]:
                    print(f"    span: type={s.get('type')}, text=\"{s.get('text','')[:60]}\", "
                          f"flags={s.get('flags',[])}{ ', role=' + s['role'] if s.get('role') else ''}")
        p2a = cl["pass2a"]
        if p2a:
            print(f"  Pass 2A: {p2a.get('classified_count','?')} rule items, "
                  f"{p2a.get('unresolved_count','?')} unresolved")
        p2b = cl["pass2b"]
        if p2b:
            print(f"  Pass 2B: {p2b.get('classified_count','?')} LLM items")

        print(f"  Final TP: {cl['tp_item_count']} items | Final SP: {cl['sp_item_count']} items")
        print()
        print(f"  {'Fact':<40} {'Fate':<28} {'SP?':<5} Detail")
        print(f"  {'-'*40} {'-'*28} {'-'*5} {'-'*45}")
        for fact in cl["facts"]:
            fp = fact["field_path"]
            if len(fp) > 38:
                fp = fp[:35] + "..."
            fate = fact["fate"]
            sp = "yes" if fact.get("sp_found") else "no"
            detail = fact.get("detail", "")[:50]
            print(f"  {fp:<40} {fate:<28} {sp:<5} {detail}")

    # ── Aggregate fate distribution ──────────────────────────────────────
    print()
    print("=" * 70)
    print("  AGGREGATE FATE DISTRIBUTION")
    print("=" * 70)
    all_fates = {}
    for cl in all_ledger:
        for f in cl["facts"]:
            fate = f["fate"]
            all_fates[fate] = all_fates.get(fate, 0) + 1
    for fate, count in sorted(all_fates.items(), key=lambda x: -x[1]):
        print(f"  {fate:<35} {count}")

    # ── Hypothesis check ─────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  HYPOTHESIS CHECK")
    print("=" * 70)

    p1_losses = sum(1 for cl in all_ledger for f in cl["facts"]
                     if f["fate"] in ("pass1_missed", "pass1_no_spans"))
    p2_losses = sum(1 for cl in all_ledger for f in cl["facts"]
                     if f["fate"] in ("pass2b_missed", "pass2b_empty", "pass2b_wrong_path",
                                       "rule_wrong_path", "rule_skipped_not_unresolved"))
    downstream_losses = sum(1 for cl in all_ledger for f in cl["facts"]
                            if f["fate"] == "stripped_downstream")
    survived = sum(1 for cl in all_ledger for f in cl["facts"]
                    if f["fate"] == "survived")
    total_expected = sum(cl["expected_field_count"] for cl in all_ledger)

    print(f"  Total expected facts:      {total_expected}")
    print(f"  Survived:                  {survived}")
    print(f"  Lost in Pass 1:            {p1_losses}  ← Hypothesis A (token starvation / under-tagging)")
    print(f"  Lost in Pass 2 (rules+LLM):{p2_losses}  ← Hypothesis B (semantic loss / misclassification)")
    print(f"  Stripped downstream:       {downstream_losses}  ← Hypothesis C (filter stripping)")
    print()

    if p1_losses > p2_losses and p1_losses > downstream_losses:
        print("  → DOMINANT: Hypothesis A — Pass 1 under-tagging/starvation")
        print("    Recommended: WO-EX-TWOPASS-V2A (fix Pass 1 token budget + span design)")
    elif p2_losses > p1_losses and p2_losses > downstream_losses:
        print("  → DOMINANT: Hypothesis B — Pass 2 misclassification")
        print("    Recommended: WO-EX-CONSTRAINED-PASS2-01 (enum-constrained decoding)")
    elif downstream_losses > p1_losses and downstream_losses > p2_losses:
        print("  → DOMINANT: Hypothesis C — Downstream filter stripping")
        print("    Recommended: WO-EX-TWOPASS-FILTER-FIX-01 (fix validator interactions)")
    else:
        print("  → No single dominant loss stage — losses spread across pipeline")
        print("    Recommended: simplify before retrying")

    # ── Save full report ─────────────────────────────────────────────────
    report_path = REPORT_DIR / "twopass_stage_loss_report.json"
    with open(report_path, "w") as f:
        json.dump(all_ledger, f, indent=2, default=str)
    print(f"\n  Full report saved to: {report_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Two-pass stage-loss debugger")
    parser.add_argument("--step", required=True,
                        choices=["single-pass", "two-pass", "analyze"],
                        help="Which step to run")
    parser.add_argument("--api", default="http://localhost:8000",
                        help="API base URL")
    args = parser.parse_args()

    if args.step == "single-pass":
        step_single_pass()
    elif args.step == "two-pass":
        step_two_pass()
    elif args.step == "analyze":
        step_analyze()


if __name__ == "__main__":
    main()
