#!/usr/bin/env python3
"""One-time repair: a DRAFT of migration 0063 was applied to a persistent root.

What happened (2026-09-24): the working root applied 0063_life_record.sql at
2026-09-24 00:09 UTC while Batch B-1 was still being edited with the stack up.
The file changed afterwards (composite keys → single-column ids) and was
committed at 4918a7e. The runner tracks FILENAMES, so it never re-applied the
final file, and the first real Life Record Save failed with
`table lr_revisions has no column named id`. 0063 itself is NOT edited: this
repairs the database that received the draft.

With the stack STOPPED, in this order:
  0. NOTHING TO DO? If the live lr_* schema already equals a freshly migrated
     root, exit 0 without a backup and without touching anything. A second
     run is therefore a no-op, not a repeat.
  P. PREFLIGHT (read-only): PRAGMA integrity_check must be "ok"; NO migration
     may be pending; schema_migrations must hold exactly one 0063 row.
  1. back the database up (WAL checkpointed into the copy first);
  2. refuse unless all 14 lr_* tables are EMPTY (nothing can be lost);
  3. + 4. ONE transaction: drop exactly those 14 tables, delete exactly the
     0063 row, then recompute the pending set INSIDE the transaction and
     roll everything back unless it is exactly ["0063_life_record.sql"];
  5. apply it with the normal runner (only 0063 can be pending now);
  6. compare every lr_* table and index with the fresh root, and check that
     lr_revisions is keyed on `id`;
  7. PRAGMA integrity_check and foreign_key_check.
A refusal at 0, P, 2 or 3-4 changes nothing. A failure after COMMIT names
the backup to restore from.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/repair_draft_0063.py /mnt/c/lorevox_data/db/lorevox.sqlite3
"""
import contextlib
import io
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

from db.migrations_runner import (  # noqa: E402  the runner's OWN notion of "pending"
    _MIGRATIONS_DIR, _applied_filenames, _iter_migration_files, run_pending_migrations)

TARGET = "0063_life_record.sql"
LR = ["lr_story_refs", "lr_stories", "lr_acceptances", "lr_assertions", "lr_sources",
      "lr_event_participants", "lr_relationships", "lr_events", "lr_names", "lr_animals",
      "lr_places", "lr_revisions", "lr_people", "lr_record"]


def pending(con):
    done = _applied_filenames(con)
    return [p.name for p in _iter_migration_files(_MIGRATIONS_DIR) if p.name not in done]


def lr_schema(path):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {(t, n): sql for t, n, sql in con.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE tbl_name LIKE 'lr\\_%' ESCAPE '\\'")}
    finally:
        con.close()


def fresh_lr_schema():
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
        from api import db as _db
        _db.DB_PATH = Path(d) / "fresh.sqlite3"
        _db.init_db()
        return lr_schema(_db.DB_PATH)


def main():
    db = Path(sys.argv[1])
    if not db.is_file():
        sys.exit(f"no database file at {db}")
    fresh = fresh_lr_schema()

    # 0. nothing to do?
    if lr_schema(db) == fresh:
        print(f"0. nothing to repair — the live lr_* schema already equals a fresh root "
              f"({len(fresh)} objects). No backup made, nothing changed.")
        return

    # P. preflight, read-only
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        ic = ro.execute("PRAGMA integrity_check").fetchall()
        if ic != [("ok",)]:
            sys.exit(f"P. REFUSED — integrity_check is not ok BEFORE the repair: {ic[:3]}. Nothing changed.")
        before = pending(ro)
        if before:
            sys.exit(f"P. REFUSED — migrations are already pending {before}; this repair applies "
                     f"only {TARGET}. Start the stack once (or investigate) first. Nothing changed.")
        n0063 = ro.execute("SELECT count(*) FROM schema_migrations WHERE filename = ?", (TARGET,)).fetchone()[0]
        if n0063 != 1:
            sys.exit(f"P. REFUSED — expected exactly one {TARGET} row in schema_migrations, found {n0063}. "
                     f"Nothing changed.")
    finally:
        ro.close()
    print("P. preflight   integrity ok; no pending migrations; one 0063 row")

    # 1. backup (the WAL is checkpointed into the main file first)
    con = sqlite3.connect(str(db))
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = db.with_name(db.name + f".pre-0063-repair-{stamp}.bak")
    shutil.copy2(db, backup)
    print(f"1. backup      {backup}")

    con = sqlite3.connect(str(db))
    # 2. refuse unless empty
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in LR}
    if any(counts.values()):
        con.close()
        sys.exit(f"2. REFUSED — not all lr_* tables are empty, nothing changed: {counts}")
    print("2. empty       all 14 lr_* tables hold 0 rows")

    # 3 + 4. one transaction; the pending set is proven BEFORE it commits
    con.execute("BEGIN")
    for t in LR:
        con.execute(f"DROP TABLE {t}")
    n = con.execute("DELETE FROM schema_migrations WHERE filename = ?", (TARGET,)).rowcount
    now_pending = pending(con)
    if n != 1 or now_pending != [TARGET]:
        con.execute("ROLLBACK")
        con.close()
        sys.exit(f"3-4. REFUSED — deleted {n} tracking row(s); pending would be {now_pending}, "
                 f"not exactly [{TARGET}]. Rolled back; nothing changed.")
    con.execute("COMMIT")
    print(f"3-4. dropped   14 tables; {TARGET} row removed; pending is exactly [{TARGET}]")

    # 5. the normal runner
    applied = run_pending_migrations(con)
    con.close()
    print(f"5. applied     {applied}")
    if applied != [TARGET]:
        sys.exit(f"5. UNEXPECTED — applied {applied}. Restore from {backup}")

    # 6. compare with the fresh root
    live = lr_schema(db)
    if live != fresh:
        diff = sorted(set(live.items()) ^ set(fresh.items()))
        sys.exit(f"6. MISMATCH vs a fresh root: {diff[:4]} … Restore from {backup}")
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    pk = [r[1] for r in ro.execute("PRAGMA table_info(lr_revisions)") if r[5]]
    print(f"6. schema      {len(live)} lr_* objects identical to a fresh root; lr_revisions pk={pk}")
    if pk != ["id"]:
        ro.close()
        sys.exit(f"6. lr_revisions is not keyed on id: {pk}. Restore from {backup}")

    # 7. integrity
    ic = ro.execute("PRAGMA integrity_check").fetchall()
    fk = ro.execute("PRAGMA foreign_key_check").fetchall()
    left = pending(ro)
    ro.close()
    print(f"7. integrity   {ic[0][0]}; foreign_key_check: {len(fk)} problem(s); pending now: {left}")
    if ic != [("ok",)] or fk or left:
        sys.exit(f"7. PROBLEM: {ic[:3]} {fk[:3]} {left}. Restore from {backup}")
    print("REPAIRED — start the stack; the next browser Save exercises the final 0063.")


if __name__ == "__main__":
    main()
