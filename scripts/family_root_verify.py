#!/usr/bin/env python3
"""Verify a multi-narrator Lorevox root. READ ONLY — opens the database, writes nothing.

WO-LOREVOX-PORTABLE-NARRATOR-01 — the family-root acceptance check.

Answers the questions sequential restore has to survive, against the real destination
rather than against a restore's own bookkeeping:

  * the narrators present, by UUID — and with `--expect`, that they are EXACTLY the ones
    named, failing on a missing or an unexpected extra one. Without `--expect` the tool
    reports what it finds and asserts nothing about who should be there, which is a
    weaker claim and is stated as such;
  * per-narrator row ownership and counts, through the SAME ownership declaration the
    exporter uses — not a hand-written WHERE clause that could disagree with it;
  * NO cross-narrator leakage: every row in a directly-owned lane belongs to one of the
    narrators present;
  * `PRAGMA foreign_key_check` clean;
  * the SEMANTIC reference closure clean — the one SQLite cannot check, since no
    migration declares `REFERENCES turns` and a root can be SQL-valid and still broken;
  * every restore job `complete`.

USAGE
    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/family_root_verify.py \\
        --data-dir /mnt/c/lorevox_family \\
        --db /mnt/c/lorevox_family/db/lorevox.sqlite3
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

_SERVER_CODE = str(Path(__file__).resolve().parents[1] / "server" / "code")
if _SERVER_CODE not in sys.path:
    sys.path.insert(0, _SERVER_CODE)

from api.services import narrator_data_inventory as inv   # noqa: E402
from api.services import narrator_merge as merge          # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--expect", action="append", default=[], metavar="UUID",
                    help="a narrator that MUST be present; repeatable. When given, the "
                         "set must match exactly — a missing narrator and an unexpected "
                         "extra one both fail. Omit to report without asserting.")
    ap.add_argument("--expect-rows", action="append", default=[], metavar="UUID=N",
                    help="assert a narrator's owned row count; repeatable")
    a = ap.parse_args(argv)
    root, db_path = Path(a.data_dir), Path(a.db)

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)   # read-only, enforced
    con.row_factory = sqlite3.Row
    problems = []
    try:
        present = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

        print("── narrators ──────────────────────────────────────────────")
        people = con.execute(
            "SELECT id, display_name, COALESCE(testing_only,0) AS testing "
            "FROM people ORDER BY display_name").fetchall()
        for p in people:
            print(f"  {p['id']}  {p['display_name']!r}"
                  f"{'  [testing_only]' if p['testing'] else ''}")
        ids = [p["id"] for p in people]
        print(f"  total: {len(ids)}")
        if a.expect:
            want, got = set(a.expect), set(ids)
            for missing in sorted(want - got):
                problems.append(f"expected narrator {missing} is NOT in this root")
            for extra in sorted(got - want):
                problems.append(f"unexpected narrator {extra} is in this root")
            print(f"  --expect: {len(want)} named, "
                  f"{'MATCHES' if want == got else 'DOES NOT MATCH'}")
        else:
            print("  (no --expect given: reporting who is here, asserting nothing "
                  "about who should be)")

        print("\n── per-narrator ownership, via the declaration ─────────────")
        owned = [t for t in inv.narrator_owned_tables() if t in present]
        totals = {}
        per_table = {}
        for pid in ids:
            n = 0
            tables = {}
            for table in owned:
                try:
                    sql = f'SELECT COUNT(*) FROM "{table}" WHERE {inv.owner_predicate(table)}'
                    c = con.execute(sql, {"pid": pid}).fetchone()[0]
                except sqlite3.Error as exc:
                    problems.append(f"{table} unqueryable for {pid}: {exc}")
                    continue
                if c:
                    tables[table] = c
                    n += c
            totals[pid] = n
            per_table[pid] = tables
            print(f"  {pid}  {n} rows across {len(tables)} tables")
        for spec in a.expect_rows:
            pid, _, want = spec.partition("=")
            if not want.isdigit():
                problems.append(f"--expect-rows {spec!r} is not UUID=N")
                continue
            actual = totals.get(pid)
            if actual != int(want):
                problems.append(f"{pid} owns {actual} rows, expected {want}")
            else:
                print(f"  --expect-rows: {pid} = {want} ✓")

        print("\n── cross-narrator leakage ─────────────────────────────────")
        # every row in a DIRECTLY owned lane must belong to one of the narrators here
        leaks = 0
        for table in owned:
            lane = inv.lane(table)
            col = getattr(lane.owner, "column", None)
            if not col or not isinstance(lane.owner, inv.Direct):
                continue
            try:
                rows = con.execute(
                    f'SELECT DISTINCT "{col}" AS owner FROM "{table}"').fetchall()
            except sqlite3.Error:
                continue
            for r in rows:
                if r["owner"] is not None and r["owner"] not in ids:
                    leaks += 1
                    problems.append(f"{table}.{col} = {r['owner']!r} belongs to nobody here")
        print(f"  orphaned owners found: {leaks}")

        print("\n── SQLite foreign keys ────────────────────────────────────")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        print(f"  violations: {len(fk)}")
        for row in fk[:10]:
            problems.append(f"foreign_key_check: {tuple(row)}")

        print("\n── semantic reference closure (what SQLite cannot see) ─────")
        readback = {}
        for parent in merge.CLOSURE_ESTABLISHED:
            wanted = {parent.split(".")[0]} | {s.table for s in merge.reference_sites(parent)}
            for t in wanted:
                if t in readback or t not in present:
                    continue
                readback[t] = [dict(r) for r in con.execute(f'SELECT * FROM "{t}"')]
        dangling = merge.validate_semantic_references(readback)
        print(f"  dangling references: {len(dangling)}")
        for d in dangling[:10]:
            problems.append(f"dangling: {d}")

        print("\n── restore jobs ───────────────────────────────────────────")
        if "narrator_package_jobs" in present:
            for j in con.execute(
                    "SELECT id, kind, state, narrator_id, package_id "
                    "FROM narrator_package_jobs ORDER BY created_at").fetchall():
                print(f"  {j['state']:<10} {j['kind']:<8} {j['narrator_id']} "
                      f"pkg={j['package_id']}")
                if j["state"] != "complete":
                    problems.append(f"job {j['id']} is {j['state']}, not complete")
        if "narrator_merge_jobs" in present:
            n = con.execute("SELECT COUNT(*) FROM narrator_merge_jobs").fetchone()[0]
            print(f"  merge jobs: {n}")
    finally:
        con.close()

    print("\n── files on disk ──────────────────────────────────────────")
    total = 0
    for pid in ids:
        n = sum(1 for p in root.rglob("*") if p.is_file() and pid in str(p))
        total += n
        print(f"  {pid}  {n} files under a path naming this narrator")
    allf = sum(1 for p in root.rglob("*")
               if p.is_file() and not p.name.startswith(db_path.name))
    print(f"  payload files total: {allf}  (narrator-named: {total}, "
          f"remainder is lane-keyed, e.g. import_staging / agent transcripts)")

    print("\n══ VERDICT ════════════════════════════════════════════════")
    if problems:
        print(f"  {len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"    - {p}")
        return 1
    print("  CLEAN — narrators isolated, references intact, jobs complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
