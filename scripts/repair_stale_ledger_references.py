#!/usr/bin/env python3
"""The narrow portability repair: remove nine stale `turn_extraction_ledger` rows.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-14.

**THIS SCRIPT WRITES TO THE AUTHORITATIVE LAPTOP DATABASE** when given `--apply`.
It is the only script in this investigation that does. Default is a dry run.

SCOPE — PORTABILITY, NOT CURATION. The laptop Christopher package exports,
restores into a clean root and re-exports `EQUIVALENT` at 533 records. Its one
defect is that nine exported `turn_extraction_ledger` rows carry
`turnrow:<turns.id>` references to turns the package does not contain. That is the
portability fault and the whole of it.

**Deliberately NOT done here** — these are Phase 7 clean-data decisions and gating
portability on them would answer a question portability does not ask:

  * no ownership materialised on any session;
  * no `trip_turn_links` removed or altered;
  * no NULL-owner session curated;
  * no facts salvaged into trips or photos;
  * no judgement on whether development conversations belong in the clean world.

`DirectOrExclusiveInbound` keeps Christopher's conversational rows in the package
and stays exactly as it is. Worth recording: he has **zero directly-owned
sessions**, so that mechanism is load-bearing for a real family narrator rather
than a synthetic edge case.

SAFETY
  * dry run by default; `--apply` required to write;
  * every one of the nine is verified by id AND `narrator_id` AND `turn_key` AND
    `session_id` against the investigation evidence — any difference refuses;
  * the complete original rows, the database path and its SHA-256 are written to a
    recovery artifact BEFORE the transaction opens;
  * one transaction, `rowcount` must be exactly 9, anything else rolls back;
  * after commit, every surviving ledger row is compared against a pre-write
    fingerprint, so a stray change cannot pass unnoticed.

STOP THE STACK FIRST. A running server holds connections to this database; a write
can block or hit `database is locked`. Chris starts and stops the stack (CLAUDE.md).

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code python3 scripts/repair_stale_ledger_references.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3          # dry run
    PYTHONPATH=server/code python3 scripts/repair_stale_ledger_references.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3 --apply
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.getcwd(), "server", "code"))
try:
    from api.services import narrator_data_inventory as inv
except Exception:                                             # pragma: no cover
    inv = None

CHRIS = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2"

#: Measured 2026-09-13 by inspect_dangling_turn_origins.py and confirmed by
#: christopher_closure_preflight.py. id -> (turn_key, session_id).
EXPECTED: Dict[int, Any] = {
    7:  ("turnrow:1455", "switch_ms81wxvv_pxxh"),
    8:  ("turnrow:1461", "switch_ms81wxvv_pxxh"),
    9:  ("turnrow:1467", "switch_ms81wxvv_pxxh"),
    10: ("turnrow:1471", "switch_ms81wxvv_pxxh"),
    11: ("turnrow:1477", "switch_ms81wxvv_pxxh"),
    17: ("turnrow:1515", "switch_ms8xrcuw_adlz"),
    18: ("turnrow:1517", "switch_ms8xrcuw_adlz"),
    19: ("turnrow:1529", "switch_ms8xrcuw_adlz"),
    28: ("turnrow:1579", "switch_msaedccx_fkm1"),
}
EXPECT_RECORDS_BEFORE = 533
EXPECT_RECORDS_AFTER = 524
EXPECT_FILES = 214


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(con) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for r in con.execute("SELECT * FROM turn_extraction_ledger ORDER BY id"):
        out[r["id"]] = hashlib.sha256(
            repr(tuple(r[k] for k in r.keys())).encode("utf-8")).hexdigest()[:16]
    return out


def lane_counts(con, pid: str) -> Dict[str, int]:
    if inv is None:
        return {}
    live = {r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    out: Dict[str, int] = {}
    for lane in inv.DB_LANES:
        if isinstance(lane.owner, inv.Installation) or lane.table not in live:
            continue
        try:
            out[lane.table] = con.execute(
                f'SELECT COUNT(*) c FROM "{lane.table}" '
                f'WHERE {inv.owner_predicate(lane.table)}', {"pid": pid}
            ).fetchone()["c"]
        except sqlite3.Error:
            pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--apply", action="store_true", help="actually write")
    ap.add_argument("--narrator", default=CHRIS)
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2

    mode = "APPLY — THIS WILL WRITE" if args.apply else "DRY RUN — no write"
    print(f"{mode}\ndatabase: {db}")
    digest_before = sha256_file(db)
    print(f"sha256 before: {digest_before}")
    if inv is None:
        print("\nWARNING: narrator_data_inventory not importable — record counts will")
        print("be skipped. Re-run with PYTHONPATH=server/code for the full check.\n")

    # ── preflight, read-only ─────────────────────────────────────────
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cols = [r["name"] for r in con.execute(
            "PRAGMA table_info(turn_extraction_ledger)")]
        rows = {r["id"]: {k: r[k] for k in r.keys()} for r in con.execute(
            f"SELECT * FROM turn_extraction_ledger WHERE id IN "
            f"({','.join('?' * len(EXPECTED))})", list(EXPECTED))}
        fp_before = fingerprint(con)
        total_before = len(fp_before)
        counts_before = lane_counts(con, args.narrator)
        records_before = sum(counts_before.values()) if counts_before else None
    finally:
        con.close()

    problems: List[str] = []
    for rid, (key, sess) in EXPECTED.items():
        r = rows.get(rid)
        if r is None:
            problems.append(f"id {rid}: MISSING")
            continue
        if r.get("turn_key") != key:
            problems.append(f"id {rid}: turn_key {r.get('turn_key')!r} != {key!r}")
        if r.get("narrator_id") != args.narrator:
            problems.append(f"id {rid}: narrator_id {r.get('narrator_id')!r} is not the narrator")
        if "session_id" in cols and r.get("session_id") != sess:
            problems.append(f"id {rid}: session_id {r.get('session_id')!r} != {sess!r}")

    print(f"\nledger rows total: {total_before}   targets found: {len(rows)}/9")
    if records_before is not None:
        print(f"Christopher records now: {records_before} "
              f"(expected {EXPECT_RECORDS_BEFORE})")
        if records_before != EXPECT_RECORDS_BEFORE:
            problems.append(f"record count {records_before} != expected "
                            f"{EXPECT_RECORDS_BEFORE} — the database moved since the "
                            f"investigation; re-verify before writing")

    print("\nTARGET ROWS")
    for rid in sorted(EXPECTED):
        r = rows.get(rid)
        print(f"  id={rid:<4} {r.get('turn_key') if r else '<MISSING>':<16} "
              f"session={r.get('session_id') if r else '-'}")

    if problems:
        print("\nREFUSED — evidence does not match:")
        for p in problems:
            print(f"  · {p}")
        print("\nNothing written.")
        return 1
    print("\npreflight OK — all nine match the investigation evidence")

    # ── recovery artifact, BEFORE any write ──────────────────────────
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"ledger-repair-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    recovery = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "db": str(db), "sha256_before": digest_before,
        "narrator": args.narrator,
        "purpose": "recovery record for the nine stale turn_extraction_ledger rows "
                   "removed by the portability repair; re-insert these verbatim to undo",
        "ledger_columns": cols,
        "rows": [rows[r] for r in sorted(rows)],
        "records_before": records_before,
        "reinsert_sql": (
            f"INSERT INTO turn_extraction_ledger ({','.join(cols)}) VALUES "
            f"({','.join('?' * len(cols))});"),
    }
    (outdir / "recovery.json").write_text(
        json.dumps(recovery, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"recovery record written: {outdir / 'recovery.json'}")

    if not args.apply:
        print("\nDRY RUN — would delete exactly these 9 rows in one transaction.")
        print(f"Expected after: {EXPECT_RECORDS_AFTER} records / {EXPECT_FILES} files.")
        print("Re-run with --apply (stack stopped) to perform it.")
        return 0

    # ── the write ────────────────────────────────────────────────────
    print("\nAPPLYING…")
    w = sqlite3.connect(db.as_posix(), timeout=30.0)
    w.row_factory = sqlite3.Row
    try:
        w.execute("BEGIN IMMEDIATE;")
        cur = w.execute(
            f"DELETE FROM turn_extraction_ledger WHERE id IN "
            f"({','.join('?' * len(EXPECTED))})", list(EXPECTED))
        n = cur.rowcount
        if n != 9:
            w.rollback()
            print(f"ROLLED BACK — deleted {n} rows, expected exactly 9. Nothing changed.")
            return 1
        fp_after = fingerprint(w)
        gone = set(fp_before) - set(fp_after)
        changed = [i for i in fp_after if fp_before.get(i) != fp_after[i]]
        if gone != set(EXPECTED):
            w.rollback()
            print(f"ROLLED BACK — rows removed {sorted(gone)} != targets. Nothing changed.")
            return 1
        if changed:
            w.rollback()
            print(f"ROLLED BACK — other ledger rows changed: {changed}. Nothing changed.")
            return 1
        w.commit()
        print(f"committed — {n} rows deleted, {len(fp_after)} ledger rows remain, "
              f"no other row altered")
    except sqlite3.OperationalError as e:
        try:
            w.rollback()
        except Exception:
            pass
        print(f"REFUSED — {e}\nIs the stack still running? Stop it and retry.")
        return 1
    finally:
        w.close()

    # ── post-write verification ──────────────────────────────────────
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        left = con.execute(
            f"SELECT COUNT(*) FROM turn_extraction_ledger WHERE id IN "
            f"({','.join('?' * len(EXPECTED))})", list(EXPECTED)).fetchone()[0]
        counts_after = lane_counts(con, args.narrator)
        records_after = sum(counts_after.values()) if counts_after else None
    finally:
        con.close()
    digest_after = sha256_file(db)

    print(f"\nPOST-WRITE")
    print(f"  target rows remaining : {left}   (must be 0)")
    print(f"  sha256 after          : {digest_after}")
    if records_after is not None:
        delta = records_after - (records_before or 0)
        print(f"  Christopher records   : {records_before} -> {records_after} ({delta:+d})")
        if records_after == EXPECT_RECORDS_AFTER:
            print(f"  MATCHES the expected {EXPECT_RECORDS_AFTER}")
        else:
            print(f"  *** {records_after} != expected {EXPECT_RECORDS_AFTER} — explain "
                  f"this before exporting; do not accept it silently ***")

    (outdir / "result.json").write_text(json.dumps({
        "applied": True, "deleted": sorted(EXPECTED),
        "sha256_before": digest_before, "sha256_after": digest_after,
        "records_before": records_before, "records_after": records_after,
        "expected_records_after": EXPECT_RECORDS_AFTER,
    }, indent=2), encoding="utf-8")

    print(f"\nresult written: {outdir / 'result.json'}")
    print("\nNEXT: restart the stack, then re-export Christopher and run the")
    print("clean-root restore / no-interaction re-export / semantic compare.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
