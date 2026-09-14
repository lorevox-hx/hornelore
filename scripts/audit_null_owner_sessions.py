#!/usr/bin/env python3
"""READ ONLY. Chronology of the three named sessions, and the blast radius across ALL
NULL-owner sessions, judged ONLY by the three sources migration 0044 accepted.

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-13.

WHY. `inspect_residue_session_provenance.py` settled ownership for three sessions:
each has exactly one `interview_sessions` row naming Christopher, unambiguous, the
strongest link 0044 accepts — and `sessions.person_id` is still NULL. This script
answers the two questions that follow, and nothing else.

  1. CHRONOLOGY — for each named session: every timestamp on the `sessions` row, the
     full `interview_sessions` row that names it, and first/last turn times. Plus
     whatever `schema_migrations` records about 0044. Classify:

       A  session (and its interview_sessions row) predate 0044   -> the backfill
          had the evidence and did not take effect: a migration question.
       B  the interview_sessions row was created AFTER 0044 ran    -> 0044 was
          correct at the time; the evidence arrived later and nothing re-ran.
       C  chronology cannot be proved from this database           -> say so.

     B is not a migration defect. It is the same fact from a different angle: a
     one-shot backfill cannot see evidence written after it runs, and nothing
     re-evaluates ownership afterwards.

  2. BLAST RADIUS — every NULL-owner session on the installation, bucketed by what
     the three ACCEPTED sources say. 912 of 1016 sessions are ownerless here, so the
     three Christopher sessions must not be assumed representative in either
     direction: they may be three of hundreds, or three of three.

WHAT IS NOT EVIDENCE, and is not consulted: archive-directory proximity, timestamp
adjacency, "the only narrator active that day", narrator prose, and the
`turn_extraction_ledger` itself (circular — those rows are the symptom).

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only. Writes only its report.

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/audit_null_owner_sessions.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

NAMED = ["switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"]


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _cols(con, t):
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _has(con, t):
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


# ── the three accepted sources, one conv_id at a time ────────────────────
def accepted_owner(con, cid: str, caps: Dict[str, bool]) -> Dict[str, Any]:
    """Exactly 0044's three passes, with its COUNT(DISTINCT)=1 guard."""
    out: Dict[str, Any] = {}
    if caps["is"]:
        rows = con.execute(
            "SELECT DISTINCT person_id FROM interview_sessions WHERE id=? "
            "AND person_id IS NOT NULL AND person_id<>''", (cid,)).fetchall()
        out["pass1"] = [r[0] for r in rows]
    else:
        out["pass1"] = []
    if caps["mas"]:
        rows = con.execute(
            "SELECT DISTINCT person_id FROM memory_archive_sessions WHERE conv_id=? "
            "AND person_id IS NOT NULL AND person_id<>''", (cid,)).fetchall()
        out["pass2"] = [r[0] for r in rows]
    else:
        out["pass2"] = []
    if caps["meta"]:
        rows = con.execute(
            "SELECT DISTINCT json_extract(meta_json,'$.person_id') AS p FROM turns "
            "WHERE conv_id=? AND json_extract(meta_json,'$.person_id') IS NOT NULL",
            (cid,)).fetchall()
        out["pass3"] = [r["p"] for r in rows if r["p"]]
    else:
        out["pass3"] = []

    unambiguous = {k: v[0] for k, v in out.items() if len(v) == 1}
    all_named = {o for v in out.values() for o in v}
    out["sources_with_exactly_one_owner"] = sorted(unambiguous)
    out["distinct_owners_across_sources"] = sorted(all_named)
    if not all_named:
        out["verdict"] = "no_accepted_evidence"
        out["owner"] = None
    elif len(all_named) == 1 and unambiguous:
        out["owner"] = next(iter(all_named))
        out["verdict"] = ("confirmed_by_multiple_sources"
                          if len(unambiguous) > 1 else "single_source_unique")
    else:
        out["owner"] = None
        out["verdict"] = "ambiguous_or_conflicting"
    return out


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
    }
    try:
        caps = {
            "is": _has(con, "interview_sessions") and
                  {"id", "person_id"} <= set(_cols(con, "interview_sessions")),
            "mas": _has(con, "memory_archive_sessions") and
                   {"conv_id", "person_id"} <= set(_cols(con, "memory_archive_sessions")),
            "meta": _has(con, "turns") and "meta_json" in _cols(con, "turns"),
        }
        out["accepted_sources_available"] = caps

        # ── 1. migration record ──────────────────────────────────────
        mig: Dict[str, Any] = {"table_present": _has(con, "schema_migrations")}
        if mig["table_present"]:
            mcols = _cols(con, "schema_migrations")
            mig["columns"] = mcols
            mig["carries_a_timestamp"] = any(
                c for c in mcols if "at" in c.lower() or "time" in c.lower()
                or "date" in c.lower())
            rows = con.execute("SELECT * FROM schema_migrations").fetchall()
            mig["rows_mentioning_0044"] = [
                {k: r[k] for k in r.keys()}
                for r in rows if any("0044" in str(r[k]) for k in r.keys())]
            mig["total_rows"] = len(rows)
        out["migration_0044_record"] = mig

        # ── 1b. chronology of the named sessions ─────────────────────
        scols = _cols(con, "sessions")
        icols = _cols(con, "interview_sessions") if caps["is"] else []
        chron: List[Dict[str, Any]] = []
        for cid in named:
            rec: Dict[str, Any] = {"conv_id": cid}
            s = con.execute("SELECT * FROM sessions WHERE conv_id=?", (cid,)).fetchone()
            rec["session"] = ({k: s[k] for k in s.keys()
                               if k != "payload_json"} if s is not None else None)
            if caps["is"]:
                irows = con.execute(
                    "SELECT * FROM interview_sessions WHERE id=?", (cid,)).fetchall()
                rec["interview_sessions_rows"] = [
                    {k: r[k] for k in r.keys()} for r in irows]
            t = con.execute(
                "SELECT MIN(ts) a, MAX(ts) b, COUNT(*) n FROM turns WHERE conv_id=?",
                (cid,)).fetchone()
            rec["first_turn_ts"], rec["last_turn_ts"], rec["turns"] = t["a"], t["b"], t["n"]
            chron.append(rec)
        out["chronology"] = chron

        # ── 2. blast radius over every NULL-owner session ────────────
        nulls = [r["conv_id"] for r in con.execute(
            "SELECT conv_id FROM sessions WHERE person_id IS NULL OR person_id=''")]
        out["sessions_total"] = con.execute(
            "SELECT COUNT(*) FROM sessions").fetchone()[0]
        out["sessions_null_owner"] = len(nulls)

        buckets = Counter()
        by_narrator = defaultdict(Counter)
        per_source = Counter()
        examples = defaultdict(list)
        ambiguous_rows: List[Dict[str, Any]] = []
        for cid in nulls:
            a = accepted_owner(con, cid, caps)
            buckets[a["verdict"]] += 1
            for s in a["sources_with_exactly_one_owner"]:
                per_source[s] += 1
            if a["owner"]:
                by_narrator[a["owner"]][a["verdict"]] += 1
            if a["verdict"] == "ambiguous_or_conflicting" and len(ambiguous_rows) < 25:
                ambiguous_rows.append({"conv_id": cid,
                                       "owners": a["distinct_owners_across_sources"]})
            if len(examples[a["verdict"]]) < 5:
                examples[a["verdict"]].append(cid)
        out["blast_radius"] = {
            "verdict_counts": dict(buckets),
            "sessions_with_a_unique_accepted_owner":
                buckets["single_source_unique"] + buckets["confirmed_by_multiple_sources"],
            "per_source_unique_owner_counts": dict(per_source),
            "by_narrator": {k: dict(v) for k, v in sorted(
                by_narrator.items(), key=lambda kv: -sum(kv[1].values()))},
            "examples": {k: v for k, v in examples.items()},
            "ambiguous_examples": ambiguous_rows,
        }
    finally:
        con.close()

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"null-owner-audit-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    # ── console ──────────────────────────────────────────────────────
    print(f"READ-ONLY audit of {db}")
    print(f"accepted sources available: {out['accepted_sources_available']}\n")

    m = out["migration_0044_record"]
    print("MIGRATION 0044 RECORD")
    if not m["table_present"]:
        print("  schema_migrations absent — chronology cannot be proved from this DB")
    else:
        print(f"  columns: {m['columns']}")
        print(f"  carries a timestamp: {m['carries_a_timestamp']}")
        print(f"  rows mentioning 0044: {m['rows_mentioning_0044']}")
        if not m["carries_a_timestamp"]:
            print("  -> filenames only. When 0044 RAN cannot be read from the database;")
            print("     say so rather than inferring it from adjacent data.")

    print("\nCHRONOLOGY OF THE NAMED SESSIONS")
    for c in out["chronology"]:
        s = c["session"] or {}
        print("=" * 74)
        print(f"  {c['conv_id']}   turns={c['turns']}")
        print(f"    session row      : { {k: v for k, v in s.items() if k in ('person_id','person_id_source','title','updated_at','created_at')} }")
        print(f"    first/last turn  : {c['first_turn_ts']}  ..  {c['last_turn_ts']}")
        for ir in c.get("interview_sessions_rows", []) or [{"<none>": None}]:
            print(f"    interview_session: {ir}")

    b = out["blast_radius"]
    print("\n" + "=" * 74)
    print("BLAST RADIUS — every NULL-owner session, by ACCEPTED evidence only")
    print("=" * 74)
    print(f"  sessions total            : {out['sessions_total']}")
    print(f"  NULL-owner sessions       : {out['sessions_null_owner']}")
    print(f"  with a UNIQUE accepted owner: {b['sessions_with_a_unique_accepted_owner']}")
    for k, v in sorted(b["verdict_counts"].items(), key=lambda kv: -kv[1]):
        print(f"      {k:<34} {v}")
    print(f"  per-source unique-owner counts: {b['per_source_unique_owner_counts']}")
    print("\n  BY NARRATOR (sessions a repair would attribute)")
    for pid, counts in b["by_narrator"].items():
        print(f"      {pid}  {dict(counts)}  total={sum(counts.values())}")
    if b["ambiguous_examples"]:
        print("\n  AMBIGUOUS / CONFLICTING (must stay NULL; 0044 was right to decline)")
        for r in b["ambiguous_examples"]:
            print(f"      {r['conv_id']}  owners={r['owners']}")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
