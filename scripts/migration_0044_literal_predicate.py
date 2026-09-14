#!/usr/bin/env python3
"""READ ONLY. Run migration 0044's LITERAL predicates, and test the rowid claim
without the circularity that invalidated the first attempt.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

WHAT IS ALREADY PROVEN, AND HOW (so this script does not re-argue it)

  * The runner is exonerated. `migrations_runner.py:72-89` runs the whole file
    through `executescript`, re-raises on failure leaving no tracking row, and
    records the filename only after success. `applied_at` proves the script did not
    RAISE; it proves nothing about whether an UPDATE matched a row.

  * CONDITION A IS PROVEN FROM CODE, not from timestamps.
    `ensure_interview_session` (db.py:3333-3338) is `INSERT OR IGNORE` with no
    upsert clause. It CANNOT fill a NULL `person_id` on an existing row, so whatever
    `person_id` a row carries was supplied at INSERT time; and `started_at` is
    `_now_iso()` evaluated at that same insert, so for `plan_id='chat_ws'` rows
    `started_at` IS the physical insertion time. The three conversations' rows are
    `chat_ws`, carry Christopher, and are dated 2026-07-30..08-01 -- before 0044 ran
    on 2026-08-17. The qualifying evidence existed.

WHAT THE FIRST ATTEMPT GOT WRONG, RECORDED SO IT IS NOT REPEATED

  `migration_0044_verdict.py` computed the "pre-0044" rowid watermark as
  `MAX(rowid) WHERE started_at <= applied_at`. That is CIRCULAR: a row inserted late
  bearing an old `started_at` satisfies the WHERE and RAISES THE WATERMARK ITSELF,
  concealing precisely the case the test existed to detect. Its
  "INSERTED AFTER 0044: False" lines are not evidence and are withdrawn.

  The non-circular form is ORDER CONSISTENCY: if a table was written in chronological
  order, `rowid` and the timestamp rise together. A row inserted late carrying an old
  date appears as an INVERSION. This script counts inversions instead of assuming
  monotonicity, and reports what that can and cannot support.

WHAT THIS SCRIPT DOES

  1. Runs 0044's pass 1, 2 and 3 predicates VERBATIM as SELECTs -- the same SQL, the
     same NULL semantics, the same COUNT(DISTINCT) guard, no TRIM added, no
     "improvement". A reconstructed approximation cannot prove anything about the
     statement that actually ran.
  2. Reports whether the three named conversations, and all currently attributable
     rows, satisfy that literal predicate TODAY.
  3. Counts rowid/timestamp inversions in `interview_sessions` and `sessions`.
  4. Reports the `sessions` rows' own rowid neighbourhood -- because 0044 could only
     fill a `sessions` row that EXISTED when it ran, and that is the one part of
     condition A still open.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/migration_0044_literal_predicate.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

NAMED = ["switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"]

# ── 0044's three passes, transcribed verbatim from the migration file ────
# Only `UPDATE sessions SET ... WHERE` becomes `SELECT conv_id FROM sessions WHERE`.
# Every other character of the predicate is the migration's own.
PASS1 = """
SELECT conv_id FROM sessions
 WHERE person_id IS NULL
   AND (
        SELECT COUNT(DISTINCT isx.person_id)
          FROM interview_sessions isx
         WHERE isx.id = sessions.conv_id
   ) = 1
"""
PASS2 = """
SELECT conv_id FROM sessions
 WHERE person_id IS NULL
   AND (
        SELECT COUNT(DISTINCT mas.person_id)
          FROM memory_archive_sessions mas
         WHERE mas.conv_id = sessions.conv_id
   ) = 1
"""
PASS3 = """
SELECT conv_id FROM sessions
 WHERE person_id IS NULL
   AND (
        SELECT COUNT(DISTINCT json_extract(t.meta_json, '$.person_id'))
          FROM turns t
         WHERE t.conv_id = sessions.conv_id
           AND json_extract(t.meta_json, '$.person_id') IS NOT NULL
   ) = 1
"""
# What pass 1 WOULD have written, verbatim.
PASS1_VALUE = """
SELECT s.conv_id,
       (SELECT MIN(isx.person_id) FROM interview_sessions isx
         WHERE isx.id = s.conv_id) AS would_write
  FROM sessions s WHERE s.conv_id = ?
"""


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def inversions(con, table: str, tscol: str) -> Dict[str, Any]:
    """Rows whose timestamp is EARLIER than a row with a LOWER rowid.

    Zero inversions is consistent with a table written in chronological order and
    never back-filled with old-dated rows. It is not proof -- a single late insert
    dated after every existing row is invisible to this -- but a LATE insert carrying
    an OLD date, the scenario at issue, necessarily shows up here.
    """
    rows = [(r["rowid"], r[tscol]) for r in con.execute(
        f'SELECT rowid, "{tscol}" FROM "{table}" ORDER BY rowid')]
    worst: List[Dict[str, Any]] = []
    hi = ""
    n = 0
    for rid, ts in rows:
        t = ts or ""
        if t and hi and t < hi:
            n += 1
            if len(worst) < 12:
                worst.append({"rowid": rid, tscol: t, "exceeded_by_earlier_max": hi})
        if t > hi:
            hi = t
    return {"rows": len(rows), "inversions": n, "examples": worst}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--conv-ids", default="")
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    named = [c.strip() for c in args.conv_ids.split(",") if c.strip()] or list(NAMED)
    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2

    con = ro(db)
    out: Dict[str, Any] = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "withdrawn": ("migration_0044_verdict.py's rowid watermark was circular "
                      "(MAX(rowid) WHERE started_at <= applied_at); its "
                      "'INSERTED AFTER 0044' lines are not evidence."),
    }
    try:
        p1 = {r["conv_id"] for r in con.execute(PASS1)}
        p2 = {r["conv_id"] for r in con.execute(PASS2)}
        p3 = {r["conv_id"] for r in con.execute(PASS3)}
        out["literal_pass_matches_today"] = {
            "pass1_interview_sessions": len(p1),
            "pass2_memory_archive_sessions": len(p2),
            "pass3_turns_meta_json": len(p3),
            "union": len(p1 | p2 | p3),
        }
        out["named"] = []
        for cid in named:
            v = con.execute(PASS1_VALUE, (cid,)).fetchone()
            out["named"].append({
                "conv_id": cid,
                "satisfies_literal_pass1": cid in p1,
                "satisfies_literal_pass2": cid in p2,
                "satisfies_literal_pass3": cid in p3,
                "pass1_would_write": (v["would_write"] if v else None),
            })

        # sessions rowid neighbourhood — was the sessions row there in August?
        srows = []
        for cid in named:
            r = con.execute(
                "SELECT rowid, conv_id, updated_at FROM sessions WHERE conv_id=?",
                (cid,)).fetchone()
            if r is None:
                srows.append({"conv_id": cid, "session": None})
                continue
            nb = con.execute(
                "SELECT MIN(updated_at) a, MAX(updated_at) b FROM sessions "
                "WHERE rowid BETWEEN ? AND ?",
                (max(1, r["rowid"] - 5), r["rowid"] + 5)).fetchone()
            srows.append({"conv_id": cid, "rowid": r["rowid"],
                          "updated_at": r["updated_at"],
                          "rowid_neighbourhood_updated_at": [nb["a"], nb["b"]]})
        out["named_sessions_rowids"] = srows
        out["sessions_max_rowid"] = con.execute(
            "SELECT MAX(rowid) FROM sessions").fetchone()[0]
        out["interview_sessions_max_rowid"] = con.execute(
            "SELECT MAX(rowid) FROM interview_sessions").fetchone()[0]

        out["order_consistency"] = {
            "interview_sessions.started_at": inversions(
                con, "interview_sessions", "started_at"),
            "sessions.updated_at": inversions(con, "sessions", "updated_at"),
        }
    finally:
        con.close()

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"0044-literal-predicate-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY literal-predicate check against {db}\n")
    print("WITHDRAWN: " + out["withdrawn"] + "\n")

    print("0044's LITERAL predicates, run verbatim as SELECTs, TODAY")
    for k, v in out["literal_pass_matches_today"].items():
        print(f"  {k:<34} {v}")
    print("  (these are rows the migration WOULD match if it ran now)")

    print("\nTHE THREE NAMED CONVERSATIONS")
    for r in out["named"]:
        print(f"  {r['conv_id']}")
        print(f"      literal pass1={r['satisfies_literal_pass1']}  "
              f"pass2={r['satisfies_literal_pass2']}  pass3={r['satisfies_literal_pass3']}")
        print(f"      pass 1 would write: {r['pass1_would_write']}")

    print("\nSESSIONS ROWIDS — was the sessions row present when 0044 ran?")
    print(f"  sessions max rowid={out['sessions_max_rowid']}  "
          f"interview_sessions max rowid={out['interview_sessions_max_rowid']}")
    for r in out["named_sessions_rowids"]:
        if r.get("session", 1) is None:
            print(f"  {r['conv_id']}  NO SESSIONS ROW")
            continue
        print(f"  {r['conv_id']}  rowid={r['rowid']}  updated_at={r['updated_at']}")
        print(f"      rowid neighbours updated_at: {r['rowid_neighbourhood_updated_at']}")

    print("\nORDER CONSISTENCY (the non-circular test)")
    for k, v in out["order_consistency"].items():
        print(f"  {k}: rows={v['rows']}  inversions={v['inversions']}")
        for e in v["examples"][:6]:
            print(f"      {e}")
    print("\n  READING. Zero inversions is consistent with a table written in")
    print("  chronological order and never back-filled with old-dated rows. It does")
    print("  NOT prove the database was never rebuilt — a wholesale rebuild that")
    print("  preserved order would also show zero. It DOES rule out the specific")
    print("  scenario at issue: individual late inserts carrying old timestamps.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
