#!/usr/bin/env python3
"""READ ONLY. Was the fixed ownership writer actually RUNNING when Del's session was
created, or merely present in the working tree?

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

WHY THIS IS NOT OBVIOUS. Del's session `switch_mswiby0y_2kws` was created
2026-08-17T00:41 UTC and has no owner. The classifier called that an active writer
defect. It is not, unless the corrected code was live at the time.

FROM THIS LAPTOP'S REFLOG (.git/logs/HEAD, UTC epochs):

    2026-08-16 13:49   fea94bc  feat(narrator-authority): one server-owned answer
                                for projection, sessions and chronology
    2026-08-16 13:50   8875c04  docs(narrator-authority): reconcile ...
    2026-08-17 00:41   <-- Del's session
    2026-08-17 00:47   bc27e7c  feat(travel): connect document workflow ...
    2026-08-17 03:06   <-- migration 0044 applied

  So the fix was IN THE TREE about eleven hours before Del's session. Chris starts
  and stops the stack by hand and a cold boot takes ~4 minutes, so a commit landing
  in the tree says nothing about what the running uvicorn process had imported.

THE NON-CIRCULAR TEST. Do not reason from Del's own NULL owner -- that is the thing
being explained. Reason from OTHER rows:

  `person_id_source` is stamped 'explicit' by `ensure_session`/`upsert_session`
  (db.py:1786) and ONLY by the fixed writer. 0045 stamps 'legacy_payload_json'.
  0044-recovered rows carry NULL. So THE EARLIEST 'explicit' ROW IS THE EARLIEST
  MOMENT THE FIXED WRITER IS PROVEN TO HAVE BEEN RUNNING.

    earliest 'explicit' EARLIER than Del  -> the fixed writer was live; Del is a
                                            genuine defect and its writer must be
                                            traced.
    earliest 'explicit' LATER than Del    -> no evidence the fixed writer had been
                                            deployed yet; Del is historical residue
                                            from the old path, NOT a live defect.

  Supporting, weaker: every session created in the window between the commit and
  Del. If all of them are ownerless too, that is a deployment gap rather than one
  anomalous row.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/del_deployment_chronology.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict

FIX_COMMIT_UTC = "2026-08-16T13:49:33"     # fea94bc, from this laptop's reflog
DEL_CONV = "switch_mswiby0y_2kws"
M0044_UTC = "2026-08-17T03:06:39"


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--conv-id", default=DEL_CONV)
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2

    con = ro(db)
    out: Dict[str, Any] = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db),
        "reflog_fix_commit_utc": FIX_COMMIT_UTC,
        "migration_0044_utc": M0044_UTC,
        "note": ("DB timestamps are UTC (_now_iso uses datetime.now(timezone.utc); "
                 "SQLite CURRENT_TIMESTAMP is UTC), so these are directly comparable "
                 "with the reflog's UTC epochs."),
    }
    try:
        # Del's own row
        d = con.execute(
            "SELECT conv_id, person_id, person_id_source, updated_at FROM sessions "
            "WHERE conv_id=?", (args.conv_id,)).fetchone()
        t = con.execute("SELECT MIN(ts) a, MAX(ts) b, COUNT(*) n FROM turns "
                        "WHERE conv_id=?", (args.conv_id,)).fetchone()
        out["del_session"] = (dict(d) if d else None)
        out["del_turns"] = {"first": t["a"], "last": t["b"], "count": t["n"]}
        del_first = t["a"] or ""

        # THE TEST — earliest row the fixed writer is proven to have stamped
        e = con.execute(
            "SELECT s.conv_id, s.updated_at, "
            "       (SELECT MIN(ts) FROM turns WHERE conv_id=s.conv_id) AS first_turn "
            "  FROM sessions s WHERE s.person_id_source='explicit' "
            " ORDER BY COALESCE((SELECT MIN(ts) FROM turns WHERE conv_id=s.conv_id), "
            "                   s.updated_at) ASC LIMIT 5").fetchall()
        out["earliest_explicit_rows"] = [dict(r) for r in e]
        earliest = (e[0]["first_turn"] or e[0]["updated_at"]) if e else None
        out["earliest_explicit_stamp"] = earliest
        out["fixed_writer_proven_live_before_del"] = bool(
            earliest and del_first and earliest < del_first)

        # supporting: every session in the commit -> Del window
        w = con.execute(
            "SELECT s.conv_id, s.person_id, s.person_id_source, "
            "       (SELECT MIN(ts) FROM turns WHERE conv_id=s.conv_id) AS first_turn "
            "  FROM sessions s "
            " WHERE COALESCE((SELECT MIN(ts) FROM turns WHERE conv_id=s.conv_id), "
            "                s.updated_at) BETWEEN ? AND ? "
            " ORDER BY first_turn", (FIX_COMMIT_UTC, M0044_UTC)).fetchall()
        out["sessions_between_fix_commit_and_0044"] = [dict(r) for r in w]
        owned = [r for r in w if r["person_id"]]
        out["window_summary"] = {"total": len(w), "with_owner": len(owned),
                                 "ownerless": len(w) - len(owned)}
    finally:
        con.close()

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"del-deployment-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY Del deployment chronology against {db}\n")
    print(f"  fix commit in tree (reflog, UTC): {FIX_COMMIT_UTC}")
    print(f"  Del session first turn (UTC)    : {out['del_turns']['first']}")
    print(f"  0044 applied (UTC)              : {M0044_UTC}")
    print(f"  Del row: {out['del_session']}")

    print("\nTHE TEST — earliest row the FIXED writer is proven to have stamped")
    if not out["earliest_explicit_rows"]:
        print("  no 'explicit' rows at all — the fixed writer is not proven to have")
        print("  run at any point on this installation.")
    for r in out["earliest_explicit_rows"]:
        print(f"      {r['conv_id']:<34} first_turn={r['first_turn']}  "
              f"updated_at={r['updated_at']}")
    print(f"  earliest explicit stamp: {out['earliest_explicit_stamp']}")

    print("\nSESSIONS BETWEEN THE FIX COMMIT AND 0044")
    s = out["window_summary"]
    print(f"  total={s['total']}  with_owner={s['with_owner']}  ownerless={s['ownerless']}")
    for r in out["sessions_between_fix_commit_and_0044"][:20]:
        print(f"      {r['first_turn']}  {r['conv_id']:<34} "
              f"owner={'yes' if r['person_id'] else 'NO'}  src={r['person_id_source']}")

    print("\nVERDICT")
    if out["fixed_writer_proven_live_before_del"]:
        print("  The fixed writer is PROVEN to have been running before Del's session.")
        print("  Del is therefore a genuine writer defect — trace its exact path.")
    else:
        print("  The fixed writer is NOT proven to have been running before Del's")
        print("  session. Del is historical residue from the old path, and must NOT")
        print("  be reported as an active writer regression. The classifier's")
        print("  'ACTIVE WRITER DEFECT INDICATED' line is withdrawn on this evidence.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
