#!/usr/bin/env python3
"""Re-score a stored eval report's extractor outputs against a case bank.

WHY. A pass-count delta across a case-bank change measures the bank and the
extractor together (CLAUDE.md, "Extractor lane"). Re-scoring the SAME stored
outputs against two banks separates them: whatever moves is bank movement,
because the outputs did not change.

HOW IT STAYS HONEST.
  * It imports `score_case` from the runner and calls it unchanged. The
    runner file is not edited — its hash IS `scorer_version`.
  * It re-scores from the report's `raw_items`. Those values are capped at
    100 characters by the runner, so a re-score CAN differ from the live
    score on a long value (measured: b1-768 case_073, a 151-char story).
    So bank movement is never computed as "live score vs re-score". Both
    banks are applied to the SAME stored items, and only their difference is
    attributed to the bank. Cases whose re-score under the original bank does
    not reproduce the live result are listed by name, never hidden.

Usage:
    cd /mnt/c/Users/chris/hornelore
    python3 scripts/eval/rescore_stored_outputs.py \
        --report docs/reports/master_loop01_r6-batchA-b1-768.json \
        --bank  data/qa/question_bank_extraction_cases.json \
        --bank2 data/qa/question_bank_extraction_cases_v2.json
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "scripts" / "archive" / "run_question_bank_extraction_eval.py"


def _runner():
    spec = importlib.util.spec_from_file_location("qb_eval_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def rescore(report: dict, cases: dict, score_case) -> dict:
    out = {}
    for r in report["case_results"]:
        case = cases.get(r["case_id"])
        if case is None:
            continue
        s = score_case(case, r.get("raw_items") or [])
        out[r["case_id"]] = {
            "pass": bool(s["pass"]),
            "overall_score": round(float(s["overall_score"]), 6),
            "v2_pass": bool(s.get("v2_pass")),
            "must_hit": s["truth_zone_scores"]["must_extract"]["hit"],
            "must_total": s["truth_zone_scores"]["must_extract"]["total"],
            "mnw_violated": s["truth_zone_scores"]["must_not_write"]["violated"],
            "contract": case.get("caseType", "contract") == "contract",
        }
    return out


def summarise(scored: dict) -> dict:
    n = len(scored)
    contract = [v for v in scored.values() if v["contract"]]
    return {
        "cases": n,
        "pass": sum(v["pass"] for v in scored.values()),
        "v3_contract": sum(v["pass"] for v in contract),
        "v2_contract": sum(v["v2_pass"] for v in contract),
        "contract_cases": len(contract),
        "must_recall": round(sum(v["must_hit"] for v in scored.values())
                             / max(1, sum(v["must_total"] for v in scored.values())), 4),
        "mnw_violations": sum(v["mnw_violated"] for v in scored.values()),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", required=True)
    ap.add_argument("--bank", required=True, help="the bank the report was produced with")
    ap.add_argument("--bank2", help="a second bank; per-case movement is reported")
    ap.add_argument("--json", help="write per-case results here")
    a = ap.parse_args()

    report = json.loads(Path(a.report).read_text(encoding="utf-8"))
    runner = _runner()
    meta = report.get("run_metadata") or {}
    print(f"report       {a.report}")
    print(f"  produced   scorer={meta.get('scorer_version')} bank={meta.get('case_bank_version')}")

    def load(p):
        p = Path(p)
        return p, {c["id"]: c for c in json.loads(p.read_text(encoding="utf-8"))["cases"]}

    p1, bank1 = load(a.bank)
    s1 = rescore(report, bank1, runner.score_case)
    print(f"bank         scorer={_hash(RUNNER)} bank={_hash(p1)} ({p1.name})")

    stored = {r["case_id"]: r for r in report["case_results"]}
    drift = [cid for cid, v in s1.items()
             if v["pass"] != bool(stored[cid]["pass"])
             or abs(v["overall_score"] - float(stored[cid]["overall_score"])) > 1e-6]
    if meta.get("case_bank_version") and meta["case_bank_version"] != _hash(p1):
        print("  WARNING: --bank is not the bank this report was produced with")
    print(f"reproduces   {len(s1) - len(drift)}/{len(s1)} stored live results"
          + (f"; NOT reproduced (100-char value cap): {drift}" if drift else ""))
    print("summary      " + json.dumps(summarise(s1)))
    out = {"bank": s1, "not_reproduced": drift}

    if a.bank2:
        p2, bank2 = load(a.bank2)
        s2 = rescore(report, bank2, runner.score_case)
        print(f"bank2        bank={_hash(p2)} ({p2.name})")
        print("summary2     " + json.dumps(summarise(s2)))
        moved = sorted(cid for cid in s1 if cid in s2 and (
            s1[cid]["pass"] != s2[cid]["pass"]
            or abs(s1[cid]["overall_score"] - s2[cid]["overall_score"]) > 1e-6))
        print(f"bank moved   {len(moved)} case(s) — same outputs, different bank:")
        for cid in moved:
            print(f"    {cid}  pass {s1[cid]['pass']}->{s2[cid]['pass']}  "
                  f"score {s1[cid]['overall_score']:.3f}->{s2[cid]['overall_score']:.3f}  "
                  f"must {s1[cid]['must_hit']}/{s1[cid]['must_total']}->"
                  f"{s2[cid]['must_hit']}/{s2[cid]['must_total']}  "
                  f"mnw {s1[cid]['mnw_violated']}->{s2[cid]['mnw_violated']}")
        out.update(bank2=s2, bank_moved=moved)

    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1, sort_keys=True), encoding="utf-8")
        print(f"wrote        {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
