#!/usr/bin/env python3
"""WO-13 Phase 8 — Kent dry run harness (host-executable).

This script is meant to be run ON THE HORNELORE HOST, against a snapshot
of the real lorevox DB. It drives the full A-plan sequence end-to-end
without requiring the FastAPI server to be running:

    1. audit        print schema state + Kent's legacy blob + any FT rows
    2. snapshot     copy the live DB to a disposable working file
    3. backfill     ft_backfill_from_profile_json(person_id)
    4. queue        list current needs_verify rows for Kent
    5. approve      ft_update_row(row, status='approved' [, qualification=...])
    6. reject       ft_update_row(row, status='rejected')
    7. promote      ft_promote_all_approved(person_id, reviewer)
    8. read-profile run build_profile_from_promoted + dump the hybrid read
                    in both flag states (OFF and ON), diff them
    9. run-all      backfill -> approve-all -> promote -> read-profile
                    and write a machine-readable trace file
   10. trace        dump a JSON trace of whatever state the DB is in right now

Safety defaults:
    * ALL subcommands default to working against a SNAPSHOT copy of the DB,
      NOT the live file. Pass --live to opt into writing to the real thing.
    * The snapshot is created on first use at
        ./kent_dry_run_snapshot.sqlite3
      and reused on subsequent calls unless --fresh-snapshot is given.
    * The script NEVER deletes the live DB. It only copies from it.

USAGE (from the hornelore project root):

    # one-shot dry run against a disposable copy, with a trace file:
    python wo13_phase8_proof/run_kent_dry_run.py run-all --person-id <KENT_ID>

    # walk it interactively instead:
    python wo13_phase8_proof/run_kent_dry_run.py audit   --person-id <KENT_ID>
    python wo13_phase8_proof/run_kent_dry_run.py backfill --person-id <KENT_ID>
    python wo13_phase8_proof/run_kent_dry_run.py queue    --person-id <KENT_ID>
    python wo13_phase8_proof/run_kent_dry_run.py approve <row_id>
    python wo13_phase8_proof/run_kent_dry_run.py promote  --person-id <KENT_ID>
    python wo13_phase8_proof/run_kent_dry_run.py read-profile --person-id <KENT_ID>

Flag handling:
    The profile read seam reads HORNELORE_TRUTH_V2_PROFILE at call time.
    This script flips it in os.environ for the read-profile step and
    restores whatever was there before. It does not touch the live server.

Requires:
    * Python 3.9+
    * The hornelore project on disk (this script imports server.code.api.db)
    * No extra dependencies beyond the project's own venv
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────
# Path plumbing
# ──────────────────────────────────────────────────────────────────────
# The script lives at:
#   <hornelore>/wo13_phase8_proof/run_kent_dry_run.py
# and needs to import:
#   <hornelore>/server/code/api/db.py
# Add <hornelore> and <hornelore>/server/code to sys.path so the module's
# own `from .api import db` style still resolves.

HERE = Path(__file__).resolve().parent
HORNELORE_ROOT = HERE.parent

CANDIDATE_IMPORT_ROOTS = [
    HORNELORE_ROOT,
    HORNELORE_ROOT / "server",
    HORNELORE_ROOT / "server" / "code",
]
for p in CANDIDATE_IMPORT_ROOTS:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))


# ──────────────────────────────────────────────────────────────────────
# DB path resolution
# ──────────────────────────────────────────────────────────────────────
# db.py reads DATA_DIR + DB_NAME at module import time. We have to set
# these BEFORE importing db, otherwise we'd be pointed at whatever the
# default is (typically ./data/db/lorevox.sqlite3).
DEFAULT_LIVE_DB = HORNELORE_ROOT / "data" / "db" / "lorevox.sqlite3"
# db.py hard-codes a 'db' subdir under DATA_DIR, so put the default
# snapshot inside a db/ folder up front to avoid the auto-relocate path.
DEFAULT_SNAPSHOT = HERE / "kent_dry_run_data" / "db" / "kent_dry_run_snapshot.sqlite3"
DEFAULT_TRACE = HERE / "kent_dry_run_trace.json"


def _bind_db_path(db_file: Path) -> None:
    """Point db.py at an arbitrary sqlite file by setting DATA_DIR + DB_NAME.

    db.py resolves DB_PATH = DATA_DIR/db/DB_NAME, so we set DATA_DIR to
    the parent of `db/<file>` and DB_NAME to the file's basename.
    Creates the parent directory tree if it doesn't already exist.
    """
    db_file = db_file.resolve()
    db_dir = db_file.parent           # .../db
    data_dir = db_dir.parent          # .../
    db_dir.mkdir(parents=True, exist_ok=True)
    if db_dir.name != "db":
        # db.py hard-codes a 'db' subdir. Give it one.
        data_dir = db_dir
        db_dir = data_dir / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        dest = db_dir / db_file.name
        if dest != db_file:
            if db_file.exists():
                shutil.copy2(db_file, dest)
            db_file = dest
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ["DB_NAME"] = db_file.name


def _ensure_snapshot(live_db: Path, snapshot: Path, fresh: bool) -> Path:
    """Return a path guaranteed to be a working copy of the live DB."""
    if not live_db.exists():
        raise SystemExit(
            f"[kent-dry-run] live DB not found: {live_db}\n"
            f"   pass --live-db to point at the real file."
        )
    if fresh and snapshot.exists():
        snapshot.unlink()
    if not snapshot.exists():
        print(f"[kent-dry-run] snapshot: copying {live_db}  →  {snapshot}")
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live_db, snapshot)
        # copy sqlite's WAL/SHM files too if present, to preserve state
        for ext in ("-wal", "-shm"):
            s = Path(str(live_db) + ext)
            if s.exists():
                shutil.copy2(s, Path(str(snapshot) + ext))
    else:
        print(f"[kent-dry-run] snapshot: reusing {snapshot} "
              f"(pass --fresh-snapshot to recopy)")
    return snapshot


# ──────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────
def _ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _print_header(title: str) -> None:
    bar = "─" * 64
    print()
    print(bar)
    print("  " + title)
    print(bar)


def _pretty(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str, sort_keys=True)


def _diff_keys(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Very small structural diff for two profile_json dicts."""
    out: Dict[str, Any] = {"added_top_keys": [], "removed_top_keys": [],
                           "changed_top_keys": [], "same_top_keys": []}
    keys = sorted(set(a.keys()) | set(b.keys()))
    for k in keys:
        if k in a and k not in b:
            out["removed_top_keys"].append(k)
        elif k not in a and k in b:
            out["added_top_keys"].append(k)
        elif a[k] == b[k]:
            out["same_top_keys"].append(k)
        else:
            out["changed_top_keys"].append(k)
    if isinstance(a.get("basics"), dict) and isinstance(b.get("basics"), dict):
        ba, bb = a["basics"], b["basics"]
        bkeys = sorted(set(ba.keys()) | set(bb.keys()))
        basic_diff = {}
        for k in bkeys:
            if ba.get(k) != bb.get(k):
                basic_diff[k] = {"off": ba.get(k), "on": bb.get(k)}
        out["basics_diff"] = basic_diff
    return out


# ──────────────────────────────────────────────────────────────────────
# Subcommand implementations
# ──────────────────────────────────────────────────────────────────────
def _import_db():
    """Deferred import so DATA_DIR / DB_NAME can be set first."""
    try:
        from api import db as _db   # when hornelore/server/code is on path
        return _db
    except ModuleNotFoundError:
        pass
    try:
        from server.code.api import db as _db
        return _db
    except ModuleNotFoundError:
        pass
    raise SystemExit(
        "[kent-dry-run] could not import db module.\n"
        "   run this script from the hornelore project root and make sure\n"
        "   server/code/api/db.py exists."
    )


def cmd_audit(args) -> int:
    db = _import_db()
    db.init_db()
    _print_header(f"AUDIT  person_id={args.person_id}")
    # 1. DB file
    from api import db as dbmod  # re-resolve to get DB_PATH
    print(f"  DB file : {dbmod.DB_PATH}")
    print(f"  flag    : HORNELORE_TRUTH_V2_PROFILE="
          f"{os.environ.get('HORNELORE_TRUTH_V2_PROFILE', '(unset)')}")

    # 2. schema presence
    con = sqlite3.connect(str(dbmod.DB_PATH))
    con.row_factory = sqlite3.Row
    tables = {r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    for t in ("family_truth_notes", "family_truth_rows",
              "family_truth_promoted"):
        print(f"  schema  : {t} {'PRESENT' if t in tables else 'MISSING'}")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(people)").fetchall()}
    print(f"  schema  : people.narrator_type "
          f"{'PRESENT' if 'narrator_type' in cols else 'MISSING'}")
    con.close()

    # 3. Kent exists?
    person = db.get_person(args.person_id)
    if not person:
        print(f"  person  : NOT FOUND in people table")
        print(f"            double-check that --person-id is right.")
        return 2
    print(f"  person  : id={person.get('id')}  "
          f"name={person.get('display_name')!r}  "
          f"narrator_type={person.get('narrator_type', '(legacy)')}")

    # 4. legacy profile_json basics
    prof = db.get_profile(args.person_id) or {"profile_json": {}}
    basics = (prof.get("profile_json") or {}).get("basics") or {}
    print()
    print("  LEGACY basics (the 5 protected fields will drive backfill):")
    for bkey in ("fullname", "preferred", "dob", "pob", "birthOrder"):
        val = basics.get(bkey) or "(empty)"
        print(f"    basics.{bkey:12} = {val!r}")
    print()
    print("  LEGACY kinship rows :", len(prof.get("profile_json", {}).get("kinship", []) or []))
    print("  LEGACY pets rows    :", len(prof.get("profile_json", {}).get("pets", []) or []))

    # 5. FT state for this person
    rows = db.ft_list_rows(person_id=args.person_id, limit=10_000)
    by_status: Dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    promoted = db.ft_list_promoted(person_id=args.person_id, limit=10_000)
    print()
    print(f"  FT rows     : {len(rows)} total  {by_status}")
    print(f"  FT promoted : {len(promoted)} rows")
    return 0


def cmd_backfill(args) -> int:
    db = _import_db()
    _print_header(f"BACKFILL  person_id={args.person_id}")
    res = db.ft_backfill_from_profile_json(args.person_id)
    print(_pretty(res))
    if res.get("reference_refused"):
        print("  [!] reference narrator — backfill refused (this is correct)")
        return 3
    if res.get("error"):
        print(f"  [!] error: {res['error']}")
        return 4
    return 0


def cmd_queue(args) -> int:
    db = _import_db()
    _print_header(f"REVIEW QUEUE  person_id={args.person_id}")
    statuses = args.status.split(",") if args.status else None
    rows = db.ft_list_rows(
        person_id=args.person_id, status=statuses, limit=10_000
    )
    if not rows:
        print("  (queue is empty)")
        return 0
    for r in rows:
        qual = ""
        prov = r.get("provenance") or {}
        if prov.get("qualification"):
            qual = f"  qual={prov['qualification']!r}"
        protected = ""
        if prov.get("identity_conflict"):
            protected = "  [PROTECTED]"
        print(f"  row={r['id']}")
        print(f"     subject={r.get('subject_name')!r}  field={r.get('field')!r}"
              f"  status={r.get('status')}{protected}")
        print(f"     source_says={r.get('source_says')!r}{qual}")
        print(f"     method={r.get('extraction_method')}  "
              f"confidence={r.get('confidence')}  "
              f"created={r.get('created_at')}")
        print()
    return 0


def cmd_approve(args) -> int:
    db = _import_db()
    _print_header(f"APPROVE  row_id={args.row_id}")
    kwargs: Dict[str, Any] = {
        "row_id": args.row_id,
        "status": "approve_q" if args.qualification else "approve",
        "reviewer": args.reviewer or "kent-dry-run",
    }
    if args.qualification:
        kwargs["qualification"] = args.qualification
    if args.approved_value is not None:
        # Operator-corrected value. This is the field that turns a dry
        # run into a real review: legacy said X, the narrator says Y.
        kwargs["approved_value"] = args.approved_value
    res = db.ft_update_row(**kwargs)
    print(_pretty(res))
    return 0 if res else 5


def cmd_reject(args) -> int:
    db = _import_db()
    _print_header(f"REJECT  row_id={args.row_id}")
    res = db.ft_update_row(
        row_id=args.row_id, status="reject",
        reviewer=args.reviewer or "kent-dry-run",
    )
    print(_pretty(res))
    return 0 if res else 5


def cmd_promote(args) -> int:
    db = _import_db()
    _print_header(f"PROMOTE  person_id={args.person_id}")
    res = db.ft_promote_all_approved(
        person_id=args.person_id,
        reviewer=args.reviewer or "kent-dry-run",
    )
    print(_pretty(res))
    return 0


def _read_profile_both_flags(db, person_id: str) -> Dict[str, Any]:
    """Read the hybrid profile once with the flag OFF and once with it ON.

    Returns a dict with both profile shapes and a structural diff. The
    caller of this function is responsible for printing the output.
    This function is pure: it does NOT mutate any rows and it restores
    whatever HORNELORE_TRUTH_V2_PROFILE was set to on entry.
    """
    prev_flag = os.environ.get("HORNELORE_TRUTH_V2_PROFILE")
    try:
        # Flag OFF = raw legacy profile_json
        os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
        legacy = db.get_profile(person_id) or {}
        legacy_profile = copy.deepcopy(legacy.get("profile_json") or {})

        # Flag ON = build_profile_from_promoted hybrid read
        os.environ["HORNELORE_TRUTH_V2_PROFILE"] = "1"
        promoted = copy.deepcopy(db.build_profile_from_promoted(person_id))
    finally:
        if prev_flag is None:
            os.environ.pop("HORNELORE_TRUTH_V2_PROFILE", None)
        else:
            os.environ["HORNELORE_TRUTH_V2_PROFILE"] = prev_flag

    return {
        "flag_off": legacy_profile,
        "flag_on":  promoted,
        "diff":     _diff_keys(legacy_profile, promoted),
    }


def cmd_read_profile(args) -> int:
    db = _import_db()
    _print_header(f"READ PROFILE (both flag states)  person_id={args.person_id}")
    out = _read_profile_both_flags(db, args.person_id)

    print("── flag OFF (legacy passthrough) ──")
    basics_off = out["flag_off"].get("basics", {})
    for k in sorted(basics_off):
        print(f"    basics.{k:20} = {basics_off[k]!r}")
    print(f"    kinship rows = {len(out['flag_off'].get('kinship', []) or [])}")
    print(f"    pets    rows = {len(out['flag_off'].get('pets', []) or [])}")

    print()
    print("── flag ON  (promoted-truth hybrid) ──")
    basics_on = out["flag_on"].get("basics", {})
    for k in sorted(basics_on):
        print(f"    basics.{k:20} = {basics_on[k]!r}")
    print(f"    kinship rows = {len(out['flag_on'].get('kinship', []) or [])}")
    print(f"    pets    rows = {len(out['flag_on'].get('pets', []) or [])}")
    if out["flag_on"].get("basics", {}).get("_qualifications"):
        print(f"    basics._qualifications = "
              f"{out['flag_on']['basics']['_qualifications']}")
    if out["flag_on"].get("basics", {}).get("truth"):
        print(f"    basics.truth = "
              f"{out['flag_on']['basics']['truth']}")

    print()
    print("── diff ──")
    print(_pretty(out["diff"]))
    return 0


def cmd_run_all(args) -> int:
    """Full dry run: backfill → approve everything → promote → read-profile
    → write trace file. Intended for use against the snapshot, never live."""
    db = _import_db()
    trace: Dict[str, Any] = {
        "generated_at": _ts(),
        "person_id": args.person_id,
        "db_file": os.environ.get("DB_NAME"),
        "steps": [],
    }

    def step(name: str, payload: Dict[str, Any]) -> None:
        print()
        _print_header(f"STEP — {name}")
        print(_pretty(payload))
        trace["steps"].append({"step": name, "at": _ts(), "payload": payload})

    # 0. audit
    person = db.get_person(args.person_id)
    if not person:
        print(f"[kent-dry-run] person_id {args.person_id} not found — stopping.")
        return 2
    step("audit.person", {"id": person.get("id"),
                          "display_name": person.get("display_name"),
                          "narrator_type": person.get("narrator_type", "(legacy)")})

    pre_prof = db.get_profile(args.person_id) or {"profile_json": {}}
    step("audit.legacy_basics",
         dict((pre_prof.get("profile_json") or {}).get("basics") or {}))

    # 1. backfill
    step("backfill", db.ft_backfill_from_profile_json(args.person_id))

    # 2. list review queue
    rows = db.ft_list_rows(person_id=args.person_id, limit=10_000)
    step("queue.listed", {"count": len(rows),
                          "rows": [{"row_id": r["id"],
                                    "field": r["field"],
                                    "status": r["status"],
                                    "source_says": r["source_says"]}
                                   for r in rows]})

    # 3. approve all needs_verify rows
    approved_ids: List[str] = []
    for r in rows:
        if r["status"] == "needs_verify":
            db.ft_update_row(row_id=r["id"], status="approve",
                             reviewer="kent-dry-run:run-all")
            approved_ids.append(r["id"])
    step("queue.approved_all",
         {"approved_count": len(approved_ids), "row_ids": approved_ids})

    # 4. promote
    promote_res = db.ft_promote_all_approved(
        person_id=args.person_id, reviewer="kent-dry-run:run-all")
    step("promote.all_approved", promote_res)

    # 5. read-profile under both flag states
    both = _read_profile_both_flags(db, args.person_id)
    step("read_profile.diff", both["diff"])
    trace["read_profile"] = both

    # 6. FT totals after the run
    rows_after = db.ft_list_rows(person_id=args.person_id, limit=10_000)
    by_status: Dict[str, int] = {}
    for r in rows_after:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    promoted = db.ft_list_promoted(person_id=args.person_id, limit=10_000)
    step("summary", {"ft_rows_total": len(rows_after),
                     "ft_rows_by_status": by_status,
                     "ft_promoted_total": len(promoted)})

    # 7. write trace file
    args.trace_path.parent.mkdir(parents=True, exist_ok=True)
    args.trace_path.write_text(_pretty(trace))
    print()
    print(f"[kent-dry-run] trace written: {args.trace_path}")
    return 0


def cmd_trace(args) -> int:
    """Dump a minimal state snapshot without mutating anything."""
    db = _import_db()
    rows = db.ft_list_rows(person_id=args.person_id, limit=10_000)
    promoted = db.ft_list_promoted(person_id=args.person_id, limit=10_000)
    both = _read_profile_both_flags(db, args.person_id)
    trace = {
        "generated_at": _ts(),
        "person_id": args.person_id,
        "ft_rows": rows,
        "ft_promoted": promoted,
        "read_profile": both,
    }
    args.trace_path.parent.mkdir(parents=True, exist_ok=True)
    args.trace_path.write_text(_pretty(trace))
    print(f"[kent-dry-run] trace written: {args.trace_path}")
    return 0


# ──────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_kent_dry_run.py",
        description="WO-13 Phase 8 Kent dry run harness (host-side).",
    )
    p.add_argument("--live-db", type=Path, default=DEFAULT_LIVE_DB,
                   help=f"Path to the live DB (default: {DEFAULT_LIVE_DB})")
    p.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT,
                   help=f"Path to the working snapshot "
                        f"(default: {DEFAULT_SNAPSHOT})")
    p.add_argument("--live", action="store_true",
                   help="DANGEROUS: operate directly on --live-db instead "
                        "of a snapshot. You must also pass --i-understand.")
    p.add_argument("--i-understand", action="store_true",
                   help="Required together with --live.")
    p.add_argument("--fresh-snapshot", action="store_true",
                   help="Delete the existing snapshot and recopy from "
                        "--live-db before running.")
    p.add_argument("--trace-path", type=Path, default=DEFAULT_TRACE,
                   help=f"Trace file path (default: {DEFAULT_TRACE})")

    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("audit",        help="Print schema + person state")
    s.add_argument("--person-id", required=True)
    s.set_defaults(func=cmd_audit)

    s = sub.add_parser("backfill",     help="ft_backfill_from_profile_json")
    s.add_argument("--person-id", required=True)
    s.set_defaults(func=cmd_backfill)

    s = sub.add_parser("queue",        help="List review queue")
    s.add_argument("--person-id", required=True)
    s.add_argument("--status", default=None,
                   help="Comma-separated list: needs_verify,approved,...")
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("approve",      help="Approve one row")
    s.add_argument("row_id")
    s.add_argument("--approved-value", default=None,
                   help="If set, stores the reviewer's corrected value on "
                        "the row. This is what promoted truth will actually "
                        "carry, overriding source_says.")
    s.add_argument("--qualification", default=None,
                   help="If set, status becomes 'approve_q' with this text.")
    s.add_argument("--reviewer", default=None)
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("reject",       help="Reject one row")
    s.add_argument("row_id")
    s.add_argument("--reviewer", default=None)
    s.set_defaults(func=cmd_reject)

    s = sub.add_parser("promote",      help="ft_promote_all_approved for one person")
    s.add_argument("--person-id", required=True)
    s.add_argument("--reviewer", default=None)
    s.set_defaults(func=cmd_promote)

    s = sub.add_parser("read-profile", help="Read the profile under flag OFF and ON")
    s.add_argument("--person-id", required=True)
    s.set_defaults(func=cmd_read_profile)

    s = sub.add_parser("run-all",      help="Full dry run + trace file")
    s.add_argument("--person-id", required=True)
    s.set_defaults(func=cmd_run_all)

    s = sub.add_parser("trace",        help="Dump a state snapshot")
    s.add_argument("--person-id", required=True)
    s.set_defaults(func=cmd_trace)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)

    # Resolve which DB file to point db.py at
    if args.live:
        if not args.i_understand:
            print("[kent-dry-run] --live requires --i-understand. Refusing.")
            return 10
        target_db = args.live_db
        print(f"[kent-dry-run] *** LIVE MODE *** — writing to {target_db}")
    else:
        target_db = _ensure_snapshot(args.live_db, args.snapshot,
                                     fresh=args.fresh_snapshot)
    _bind_db_path(target_db)

    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
