#!/usr/bin/env python3
"""READ ONLY. Why do sessions that satisfy 0044 pass 1 still have person_id NULL?

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

WHAT THE RUNNER ALREADY SETTLES (server/code/db/migrations_runner.py:72-89):

    con.executescript(sql)
    con.execute("INSERT INTO schema_migrations(filename) VALUES (?);", ...)
    con.commit()

  * `executescript` runs the WHOLE file; the file's own BEGIN/COMMIT is accepted.
  * Any exception re-raises and leaves NO tracking row, so the next boot retries.
  * Therefore PARTIAL application cannot produce a recorded migration.
  * Therefore `applied_at` proves the script did not RAISE. It proves NOTHING about
    whether any UPDATE matched a row. A backfill that selected zero rows and one
    that repaired a thousand record the identical success.

So 0044 ran to completion on 2026-08-17 03:06:39 and its passes matched nothing for
these rows. This script asks why, using only what the database can answer.

THE DECISIVE TEST — `rowid` monotonicity. SQLite assigns rowids in increasing order
as rows are inserted. If the `interview_sessions` rows for these conversations carry
rowids in the range of rows created LONG AFTER 2026-08-17, then they were inserted
after 0044 ran and their July `started_at` values were written late from historical
data. In that case 0044 was CORRECT at the time -- the evidence did not yet exist --
and the defect is that a one-shot backfill has no second pass, not that it failed.

If instead their rowids sit among genuinely July-era rows, the evidence WAS present
and pass 1 did not match it, which is a different and more serious finding.

SECOND TEST — did 0044 pass 1 EVER fill anything? `person_id_source` is NULL for
rows 0044 recovered, 'legacy_payload_json' for rows 0045 filled, and 'explicit' for
live writers since 2026-08-16 (db.py:1786). If NO owned session has a NULL source,
0044's backfill filled nothing at all on this installation.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/migration_0044_verdict.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict

NAMED = ["switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"]


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


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
        "runner_facts": {
            "file": "server/code/db/migrations_runner.py",
            "executes": "con.executescript(whole file)",
            "on_failure": "re-raises, no tracking row, retried next boot",
            "partial_application_possible": False,
            "applied_at_proves": "the script did not raise",
            "applied_at_does_not_prove": "that any UPDATE matched a row",
        },
    }
    try:
        m = con.execute("SELECT * FROM schema_migrations WHERE filename LIKE '%0044%'"
                        ).fetchone()
        out["migration_0044"] = {k: m[k] for k in m.keys()} if m else None
        m45 = con.execute("SELECT * FROM schema_migrations WHERE filename LIKE '%0045%'"
                          ).fetchone()
        out["migration_0045"] = {k: m45[k] for k in m45.keys()} if m45 else None
        applied_at = (m["applied_at"] if m else "")
        cut = applied_at.replace(" ", "T")

        # ── TEST 2: did 0044's backfill ever fill anything? ───────────
        src = Counter()
        for r in con.execute(
                "SELECT person_id_source AS s, COUNT(*) n FROM sessions "
                "WHERE person_id IS NOT NULL AND TRIM(person_id)<>'' "
                "GROUP BY person_id_source"):
            src[r["s"]] = r["n"]
        out["owned_sessions_by_person_id_source"] = {str(k): v for k, v in src.items()}
        out["owned_sessions_total"] = sum(src.values())
        out["rows_with_null_source"] = src.get(None, 0)
        out["interpretation_of_null_source"] = (
            "0044-recovered OR an explicit live write from before 0045 added the "
            "column. 0045's header says these two are indistinguishable today and "
            "declines to invent a marker for them.")

        # ── TEST 1: rowid forensics on interview_sessions ─────────────
        tot = con.execute("SELECT COUNT(*) FROM interview_sessions").fetchone()[0]
        mx = con.execute("SELECT MAX(rowid) FROM interview_sessions").fetchone()[0]
        out["interview_sessions_total"] = tot
        out["interview_sessions_max_rowid"] = mx

        # the highest rowid whose started_at is at or before 0044 ran; rows above
        # this watermark were inserted later.
        wm = con.execute(
            "SELECT MAX(rowid) FROM interview_sessions WHERE started_at <= ?",
            (cut,)).fetchone()[0]
        out["highest_rowid_started_before_0044"] = wm

        named_rows = []
        for cid in named:
            r = con.execute(
                "SELECT rowid, id, person_id, plan_id, started_at, updated_at, turn_count "
                "FROM interview_sessions WHERE id=?", (cid,)).fetchone()
            if r is None:
                named_rows.append({"conv_id": cid, "interview_session": None})
                continue
            rec = {k: r[k] for k in r.keys()}
            rec["conv_id"] = cid
            # how many interview_sessions rows were inserted before this one, and
            # what is the started_at of its rowid neighbours? A row inserted late
            # sits among late rows regardless of the timestamp it carries.
            nb = con.execute(
                "SELECT MIN(started_at) a, MAX(started_at) b FROM interview_sessions "
                "WHERE rowid BETWEEN ? AND ?", (max(1, r["rowid"] - 5),
                                                r["rowid"] + 5)).fetchone()
            rec["rowid_neighbourhood_started_at"] = [nb["a"], nb["b"]]
            rec["inserted_after_0044_by_rowid"] = (
                wm is not None and r["rowid"] > wm)
            named_rows.append(rec)
        out["named_interview_sessions"] = named_rows

        # ── would pass 1 have filled ANY row it did not? ──────────────
        # sessions still NULL whose interview_sessions row is unambiguous AND whose
        # interview row predates 0044 by rowid: these are the rows pass 1 should
        # have caught at the time.
        q = con.execute(
            "SELECT s.conv_id, i.rowid AS irowid, i.person_id, i.started_at "
            "  FROM sessions s JOIN interview_sessions i ON i.id = s.conv_id "
            " WHERE (s.person_id IS NULL OR TRIM(s.person_id)='') "
            "   AND i.person_id IS NOT NULL AND TRIM(i.person_id)<>'' "
            "   AND (SELECT COUNT(DISTINCT x.person_id) FROM interview_sessions x "
            "         WHERE x.id = s.conv_id) = 1").fetchall()
        pre = [dict(r) for r in q if wm is not None and r["irowid"] <= wm]
        post = [dict(r) for r in q if wm is None or r["irowid"] > wm]
        out["pass1_candidates_still_null"] = {
            "total": len(q),
            "interview_row_predates_0044_by_rowid": len(pre),
            "interview_row_inserted_after_0044_by_rowid": len(post),
            "examples_pre": pre[:10],
            "examples_post": post[:10],
        }
    finally:
        con.close()

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"migration-0044-verdict-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY 0044 verdict against {db}\n")
    print("RUNNER (read, not inferred)")
    for k, v in out["runner_facts"].items():
        print(f"  {k:<32} {v}")
    print(f"\n0044 {out['migration_0044']}")
    print(f"0045 {out['migration_0045']}")

    print("\nTEST 2 — did 0044's backfill fill anything?")
    print(f"  owned sessions: {out['owned_sessions_total']}")
    for k, v in out["owned_sessions_by_person_id_source"].items():
        print(f"      person_id_source={k:<22} {v}")
    if out["rows_with_null_source"] == 0:
        print("  *** NO owned session has a NULL source: 0044's backfill filled NOTHING")
        print("      on this installation, and no explicit write predates 0045. ***")
    else:
        print(f"  {out['rows_with_null_source']} rows have a NULL source — "
              f"0044-recovered or a pre-0045 explicit write (indistinguishable).")

    print("\nTEST 1 — rowid forensics on interview_sessions")
    print(f"  rows={out['interview_sessions_total']}  max rowid={out['interview_sessions_max_rowid']}")
    print(f"  highest rowid whose started_at <= 0044 applied: "
          f"{out['highest_rowid_started_before_0044']}")
    for r in out["named_interview_sessions"]:
        if not r.get("id"):
            print(f"  {r['conv_id']}  NO interview_sessions ROW")
            continue
        print(f"  {r['conv_id']}")
        print(f"      rowid={r['rowid']}  started_at={r['started_at']}  "
              f"turn_count={r['turn_count']}  plan={r['plan_id']}")
        print(f"      rowid neighbours started_at: {r['rowid_neighbourhood_started_at']}")
        print(f"      INSERTED AFTER 0044 (by rowid): {r['inserted_after_0044_by_rowid']}")

    p = out["pass1_candidates_still_null"]
    print("\nPASS-1 CANDIDATES STILL NULL")
    print(f"  total                                  : {p['total']}")
    print(f"  interview row predates 0044 (by rowid) : "
          f"{p['interview_row_predates_0044_by_rowid']}   <- 0044 SHOULD have filled these")
    print(f"  interview row inserted after 0044      : "
          f"{p['interview_row_inserted_after_0044_by_rowid']}   <- 0044 could not see these")

    print("\nVERDICT INPUT")
    if p["interview_row_predates_0044_by_rowid"] == 0:
        print("  Every still-NULL pass-1 candidate's evidence arrived AFTER 0044 ran.")
        print("  0044 was correct at the time. The defect is structural: a one-shot")
        print("  backfill has no second pass, and nothing re-evaluates ownership.")
    else:
        print("  Some evidence predates 0044 and was not used. That is a migration")
        print("  defect, not merely a missing second pass. Read the examples above.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
