#!/usr/bin/env python3
"""
Remove orphaned interview_sessions rows that block narrator restore.

WHY THIS EXISTS
    narrator_package.py restore verifies references with

        for table in inserted:   # only the tables this job wrote;
                                 # pre-existing damage is not ours to judge
            bad += con.execute(f'PRAGMA foreign_key_check("{table}")').fetchall()

    (narrator_package.py:1392-1393). The comment states the right rule; the
    code does not implement it. The pragma is TABLE-scoped, not ROW-scoped, so
    pre-existing orphan rows in a table the package also writes fail the job --
    pre-existing damage judged after all.

    Found 2026-09-15: six `harness-test-gate7p2-*` rows in interview_sessions,
    pointing at people rows that no longer existed, refused all three family
    packages. They had survived a full narrator erasure precisely because they
    belonged to no narrator. Every family package writes interview_sessions, so
    nothing could be restored until they were gone.

    Filed as BUG-RESTORE-FK-GATE-TABLE-SCOPED-NOT-ROW-SCOPED-01. This script is
    the operational workaround, not the fix. A root carrying LEGITIMATE orphaned
    data needs the gate corrected, not the data deleted -- which is why this
    refuses anything that is not recognisable test residue.

WHAT IT DELETES
    interview_sessions rows whose person_id has no row in people. Nothing else.

    It refuses if any such row's person_id does not look like test-harness
    residue, and it refuses if PRAGMA foreign_key_check blames an
    interview_sessions row this script cannot account for -- in either case
    there is damage it does not understand and a human should look.

DEFAULT IS READ-ONLY. Pass --apply to delete; the database is copied first.

USAGE
    cd /mnt/c/Users/chris/hornelore
    source /mnt/c/lorevox_packages/laptop-rebuild-session.env
    .venv/bin/python scripts/clear_orphan_interview_sessions.py --db "$DB"
    .venv/bin/python scripts/clear_orphan_interview_sessions.py --db "$DB" --apply

Exit codes:  0 = clean / nothing to do   1 = refused   2 = DB unreachable
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HARNESS_PREFIXES = ("harness-test-",)

ORPHAN_PREDICATE = (
    "person_id IS NOT NULL AND person_id NOT IN (SELECT id FROM people)"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="ABSOLUTE path to the SQLite file")
    ap.add_argument("--apply", action="store_true",
                    help="actually delete; without this the script only reports")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        print(f"STOP: no database at {db}")
        return 2

    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row

    fk = [tuple(r) for r in con.execute("PRAGMA foreign_key_check").fetchall()]
    print(f"--- whole-database foreign_key_check: {len(fk)} violation(s)")
    for row in fk:
        print(f"      {row}")

    orphans = con.execute(
        f"SELECT rowid AS rid, * FROM interview_sessions "
        f"WHERE {ORPHAN_PREDICATE} ORDER BY rowid"
    ).fetchall()

    print(f"\n--- orphaned interview_sessions rows: {len(orphans)}")
    for r in orphans:
        d = dict(r)
        print(f"      rowid={d['rid']}  person_id={d.get('person_id')!r}  "
              f"created_at={d.get('created_at')!r}  state={d.get('state')!r}")

    if not orphans:
        print("\nNothing to do. The blocker is not orphaned interview_sessions.")
        con.close()
        return 0

    unexpected = [dict(r)["person_id"] for r in orphans
                  if not str(dict(r)["person_id"]).startswith(HARNESS_PREFIXES)]
    if unexpected:
        print("\nSTOP: these orphaned person_ids are NOT test-harness residue:")
        for p in sorted(set(unexpected)):
            print(f"      {p!r}")
        print("      A human should look at these before anything is deleted.")
        con.close()
        return 1

    fk_rowids = {r[1] for r in fk if r[0] == "interview_sessions"}
    our_rowids = {dict(r)["rid"] for r in orphans}
    if not fk_rowids <= our_rowids:
        print(f"\nSTOP: foreign_key_check blames interview_sessions rowids "
              f"{sorted(fk_rowids - our_rowids)}, which are not orphaned by person_id. "
              f"This script does not understand that damage.")
        con.close()
        return 1

    if not args.apply:
        print(f"\nREAD-ONLY. {len(orphans)} row(s) would be deleted. "
              f"Re-run with --apply to delete them.")
        con.close()
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.with_name(f"{db.name}.orphanfix-{stamp}.bak")
    con.close()
    shutil.copy2(db, backup)
    print(f"\n--- database copied to {backup}")

    con = sqlite3.connect(str(db), isolation_level=None)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("BEGIN IMMEDIATE")
    try:
        cur = con.execute(f"DELETE FROM interview_sessions WHERE {ORPHAN_PREDICATE}")
        deleted = cur.rowcount
        if deleted != len(orphans):
            raise ValueError(f"deleted {deleted}, surveyed {len(orphans)} -- "
                             f"the table changed under us")
        con.execute("COMMIT")
    except Exception as exc:  # noqa: BLE001
        con.execute("ROLLBACK")
        print(f"STOP: rolled back, nothing deleted: {exc}")
        con.close()
        return 1

    print(f"--- deleted {deleted} row(s)")

    after = [tuple(r) for r in con.execute("PRAGMA foreign_key_check").fetchall()]
    print(f"--- whole-database foreign_key_check now: {len(after)} violation(s)")
    for row in after:
        print(f"      {row}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
