#!/usr/bin/env python3
"""Read-only: does a live database's schema match what the code builds?

WHY (2026-09-24). A draft of migration 0063 was applied to a persistent root,
the file changed afterwards, and the filename-tracked runner never noticed:
tests passed on fresh databases while the live root carried the old schema,
and the first browser Save failed with a 503. This compares every table and
index in a live database against a database freshly built by the product's
own init_db (every migration + every _ensure block) and prints each object
whose definition differs or is missing. It opens the live file READ-ONLY.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/check_schema_drift.py /mnt/c/lorevox_data/db/lorevox.sqlite3

Exit 0 = no drift; 1 = drift found (listed).
"""
import contextlib
import io
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))


def objects(path, ro=True):
    con = sqlite3.connect(f"file:{path}?mode=ro" if ro else str(path), uri=ro)
    try:
        rows = con.execute("SELECT type, name, sql FROM sqlite_master "
                           "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()
    finally:
        con.close()
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"--[^\n]*", "", s)).strip()  # noqa: E731
    return {(t, n): norm(s) for t, n, s in rows}


def main():
    live_path = Path(sys.argv[1])
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
        from api import db as _db
        _db.DB_PATH = Path(d) / "fresh.sqlite3"
        _db.init_db()
        fresh = objects(_db.DB_PATH)
    live = objects(live_path)
    missing = sorted(k for k in fresh if k not in live)
    differ = sorted(k for k in fresh if k in live and fresh[k] != live[k])
    extra = sorted(k for k in live if k not in fresh)
    for label, keys in (("DIFFERS from the code", differ), ("MISSING in the live db", missing),
                        ("only in the live db (retired or unowned)", extra)):
        for k in keys:
            print(f"{label:42} {k[0]:6} {k[1]}")
    print(f"\n{len(fresh)} objects built by the code; {len(differ)} differ, {len(missing)} missing, "
          f"{len(extra)} only-live")
    sys.exit(1 if (differ or missing) else 0)


if __name__ == "__main__":
    main()
