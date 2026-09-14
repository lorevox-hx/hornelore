#!/usr/bin/env python3
"""READ ONLY. What structural evidence, if any, ties a residue session to a narrator?

WO-LOREVOX-PORTABLE-NARRATOR-01, the bounded laptop question opened 2026-09-12 and
narrowed 2026-09-13.

`scripts/inspect_dangling_turn_origins.py` established the shape: the nine
`turn_extraction_ledger` rows in Christopher's laptop package name turns that exist,
in sessions whose `person_id` is NULL, owned by nobody. It could not say WHY those
sessions are ownerless, and that is the question that decides the fix.

THE DECISION THIS SCRIPT SERVES — and it is not "is there any hint of a link":

  Migration 0044 added `sessions.person_id` and backfilled it from THREE RECORDED
  LINKS, strongest first, each guarded by COUNT(DISTINCT ...) = 1 so ambiguity stays
  NULL:

      pass 1   interview_sessions.id = sessions.conv_id
      pass 2   memory_archive_sessions(person_id, conv_id)
      pass 3   turns.meta_json -> '$.person_id'

  0044 ALSO states what it refuses, and the list is binding on this script:

      "Nothing is attributed by timestamp adjacency, by 'the only narrator active
       that day', by ARCHIVE-DIRECTORY PROXIMITY, or by anything read out of
       narrator prose. Expect many historical rows to stay NULL. That is the
       correct outcome."

  So the on-disk `memory/archive/people/<person_id>/sessions/<conv_id>/` layout is
  NOT evidence here. It is reported below because its absence from the record would
  be conspicuous, and because a future reader will find it and wonder — but it is
  reported under `refused_by_0044`, never counted toward attribution. Neither is the
  assistant text saying "Chris", or a trip being discussed in the prose.

  Two readings follow, and they call for opposite work:

    RECORDED LINK PRESENT   a 0044 source holds an unambiguous narrator for this
                            conv_id, and the row is still NULL -> the backfill did
                            not take effect for it. A deliberate migration/repair
                            question, not an ownership-declaration question.

    NO RECORDED LINK        no 0044 source knows this conv_id at all -> the session
                            is genuinely unowned legacy residue. DO NOT widen
                            ownership. The ledger rows that name its turns are stale
                            derived references, and the fix belongs to how THOSE
                            travel, not to who owns the session.

  The `turn_extraction_ledger` is deliberately EXCLUDED from attribution evidence:
  those are the very rows whose dangling references opened the question, so using
  them to justify pulling the sessions in would be circular. They are reported, and
  reported separately, under `circular_not_evidence`.

**OPENS THE DATABASE STRICTLY READ-ONLY** (`file:...?mode=ro`), runs only SELECTs,
imports neither the export nor the erasure path, and writes only its own report.

USAGE

    cd /mnt/c/Users/chris/hornelore
    python3 scripts/inspect_residue_session_provenance.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3 \\
        --narrator a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2

Defaults cover the three conversations the package named; override with --conv-ids.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_CONV_IDS = ["switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"]

#: Columns whose NAME marks them a conversation reference. Matched case-insensitively
#: against every live table via PRAGMA — never a hand-written table list.
_CONV_COLUMN_NAMES = {"conv_id", "conversation_id", "session_id", "session_key"}
#: Free-text / JSON columns worth a LIKE scan for the literal conv_id.
_BLOB_COLUMN_HINTS = ("meta_json", "payload_json", "source", "details_json",
                      "context_json", "data_json", "notes")
#: Ownership-ish columns, reported wherever a referencing row carries one.
_OWNER_COLUMN_NAMES = ("person_id", "narrator_id", "owner_id", "subject_person_id")


def ro(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tables(con) -> List[str]:
    return [r["name"] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]


def _cols(con, t) -> List[str]:
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{t}")')]


def _has(con, t) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone())


def _owner_cols(cols) -> List[str]:
    return [c for c in _OWNER_COLUMN_NAMES if c in cols]


# ── the three 0044 sources, asked exactly as 0044 asked them ──────────────
def _pass1(con, cid) -> Dict[str, Any]:
    """interview_sessions.id = sessions.conv_id — the strongest recorded link."""
    if not _has(con, "interview_sessions"):
        return {"source_table_present": False}
    cols = _cols(con, "interview_sessions")
    if "person_id" not in cols or "id" not in cols:
        return {"source_table_present": True, "usable": False, "columns": cols}
    rows = con.execute(
        "SELECT * FROM interview_sessions WHERE id=?", (cid,)).fetchall()
    owners = sorted({r["person_id"] for r in rows if r["person_id"]})
    return {"source_table_present": True, "usable": True,
            "rows_for_this_conv_id": len(rows),
            "distinct_owners": owners,
            "unambiguous": len(owners) == 1,
            "would_0044_have_filled": len(owners) == 1,
            "owner": owners[0] if len(owners) == 1 else None}


def _pass2(con, cid) -> Dict[str, Any]:
    """memory_archive_sessions(person_id, conv_id) — an explicit recorded pair."""
    if not _has(con, "memory_archive_sessions"):
        return {"source_table_present": False}
    cols = _cols(con, "memory_archive_sessions")
    if "person_id" not in cols or "conv_id" not in cols:
        return {"source_table_present": True, "usable": False, "columns": cols}
    rows = con.execute(
        "SELECT * FROM memory_archive_sessions WHERE conv_id=?", (cid,)).fetchall()
    owners = sorted({r["person_id"] for r in rows if r["person_id"]})
    return {"source_table_present": True, "usable": True,
            "rows_for_this_conv_id": len(rows),
            "distinct_owners": owners,
            "unambiguous": len(owners) == 1,
            "would_0044_have_filled": len(owners) == 1,
            "owner": owners[0] if len(owners) == 1 else None}


def _pass3(con, cid) -> Dict[str, Any]:
    """turns.meta_json -> '$.person_id' — durable per-turn metadata."""
    if not _has(con, "turns") or "meta_json" not in _cols(con, "turns"):
        return {"source_table_present": _has(con, "turns"), "usable": False}
    rows = con.execute(
        "SELECT DISTINCT json_extract(meta_json,'$.person_id') AS p "
        "FROM turns WHERE conv_id=? AND json_extract(meta_json,'$.person_id') IS NOT NULL",
        (cid,)).fetchall()
    owners = sorted({r["p"] for r in rows if r["p"]})
    n_with = con.execute(
        "SELECT COUNT(*) FROM turns WHERE conv_id=? "
        "AND json_extract(meta_json,'$.person_id') IS NOT NULL", (cid,)).fetchone()[0]
    n_all = con.execute("SELECT COUNT(*) FROM turns WHERE conv_id=?", (cid,)).fetchone()[0]
    return {"source_table_present": True, "usable": True,
            "turns_total": n_all, "turns_carrying_person_id": n_with,
            "distinct_owners": owners,
            "unambiguous": len(owners) == 1,
            "would_0044_have_filled": len(owners) == 1,
            "owner": owners[0] if len(owners) == 1 else None}


def inspect_conv(con, narrator: str, cid: str, data_dir: Path | None) -> Dict[str, Any]:
    rec: Dict[str, Any] = {"conv_id": cid}

    # ── 1. complete session metadata, every column ────────────────────
    s = con.execute("SELECT * FROM sessions WHERE conv_id=?", (cid,)).fetchone()
    rec["session_exists"] = s is not None
    rec["session"] = {k: s[k] for k in s.keys()} if s is not None else None
    if s is not None and "payload_json" in s.keys():
        # payload can be large; report shape not contents
        pj = s["payload_json"]
        rec["session"]["payload_json"] = f"<{len(pj or '')} bytes>"
        try:
            rec["session_payload_keys"] = sorted(json.loads(pj or "{}").keys())
        except Exception:
            rec["session_payload_keys"] = None

    # ── 2. every turn in the session ──────────────────────────────────
    tcols = _cols(con, "turns")
    sel = [c for c in ("id", "conv_id", "role", "ts", "anchor_id") if c in tcols]
    rec["turns"] = [
        {k: r[k] for k in sel} for r in con.execute(
            f'SELECT {",".join(sel)} FROM turns WHERE conv_id=? ORDER BY id', (cid,))]
    rec["turn_count"] = len(rec["turns"])

    # ── 3+4. every structural reference to this conv_id, and its owner ─
    refs: Dict[str, Any] = {}
    for t in _tables(con):
        if t in ("sqlite_sequence",):
            continue
        cols = _cols(con, t)
        named = [c for c in cols if c.lower() in _CONV_COLUMN_NAMES]
        for c in named:
            try:
                rows = con.execute(
                    f'SELECT * FROM "{t}" WHERE "{c}"=?', (cid,)).fetchall()
            except sqlite3.Error:
                continue
            if not rows:
                continue
            ocols = _owner_cols(cols)
            owners: Dict[str, List[Any]] = {}
            for oc in ocols:
                owners[oc] = sorted({r[oc] for r in rows if r[oc] is not None})
            refs[f"{t}.{c}"] = {"rows": len(rows), "owner_columns": owners}
        # free-text / JSON columns that may embed the id
        for c in cols:
            if c.lower() in _BLOB_COLUMN_HINTS:
                try:
                    n = con.execute(
                        f'SELECT COUNT(*) FROM "{t}" WHERE "{c}" LIKE ?',
                        (f"%{cid}%",)).fetchone()[0]
                except sqlite3.Error:
                    continue
                if n:
                    ocols = _owner_cols(cols)
                    owners = {}
                    for oc in ocols:
                        owners[oc] = sorted({r[0] for r in con.execute(
                            f'SELECT DISTINCT "{oc}" FROM "{t}" WHERE "{c}" LIKE ?',
                            (f"%{cid}%",)) if r[0] is not None})
                    refs[f"{t}.{c} (LIKE)"] = {"rows": n, "owner_columns": owners}
    rec["structural_references"] = refs

    # ── the 0044 sources ──────────────────────────────────────────────
    rec["recorded_links_0044"] = {
        "pass1_interview_sessions": _pass1(con, cid),
        "pass2_memory_archive_sessions": _pass2(con, cid),
        "pass3_turns_meta_json": _pass3(con, cid),
    }
    filled = [k for k, v in rec["recorded_links_0044"].items()
              if v.get("would_0044_have_filled")]
    owners = sorted({v["owner"] for v in rec["recorded_links_0044"].values()
                     if v.get("owner")})
    rec["recorded_link_present"] = bool(filled)
    rec["recorded_link_sources"] = filled
    rec["recorded_link_owners"] = owners
    rec["recorded_link_names_this_narrator"] = owners == [narrator]

    # ── circular: the ledger, reported and excluded ───────────────────
    # NOTE the earlier probe printed `reached by: []` for these conversations.
    # That was a FALSE NEGATIVE: its ledger reacher query is guarded by
    # `if "conv_id" in ledger columns`, and turn_extraction_ledger has no conv_id
    # column -- it keys on `turnrow:<turns.id>`. The ledger reach is computed here
    # THROUGH the turns, which is how it actually points.
    circ: Dict[str, Any] = {}
    if _has(con, "turn_extraction_ledger"):
        lcols = _cols(con, "turn_extraction_ledger")
        tids = [t["id"] for t in rec["turns"]]
        if tids:
            marks = ",".join("?" * len(tids))
            keys = [f"turnrow:{i}" for i in tids]
            rows = con.execute(
                f'SELECT * FROM turn_extraction_ledger WHERE turn_key IN ({marks})',
                keys).fetchall()
            circ["ledger_rows_naming_turns_in_this_conversation"] = [
                {k: r[k] for k in r.keys() if k in
                 ("id", "narrator_id", "turn_key", "turn_id", "status", "state",
                  "outcome", "created_at", "updated_at")}
                for r in rows]
            circ["distinct_narrators_on_those_ledger_rows"] = sorted(
                {r["narrator_id"] for r in rows if "narrator_id" in lcols and r["narrator_id"]})
    if _has(con, "turn_extraction_results"):
        rcols = _cols(con, "turn_extraction_results")
        if "turn_key" in rcols:
            tids = [t["id"] for t in rec["turns"]]
            if tids:
                marks = ",".join("?" * len(tids))
                keys = [f"turnrow:{i}" for i in tids]
                rows = con.execute(
                    f'SELECT * FROM turn_extraction_results WHERE turn_key IN ({marks})',
                    keys).fetchall()
                circ["result_rows"] = len(rows)
                circ["distinct_narrators_on_result_rows"] = sorted(
                    {r["narrator_id"] for r in rows
                     if "narrator_id" in rcols and r["narrator_id"]})
    rec["circular_not_evidence"] = circ

    # ── refused by 0044: reported, never counted ──────────────────────
    ref: Dict[str, Any] = {"_why": "0044 refuses attribution by archive-directory "
                                   "proximity, timestamp adjacency, or narrator prose. "
                                   "Reported so the record is complete; NOT evidence."}
    if data_dir:
        for pid_dir in (data_dir / "memory" / "archive" / "people").glob("*"):
            d = pid_dir / "sessions" / cid
            if d.is_dir():
                ref.setdefault("archive_directories", []).append({
                    "person_id": pid_dir.name,
                    "path": str(d.relative_to(data_dir)),
                    "files": sorted(p.name for p in d.iterdir() if p.is_file()),
                })
    rec["refused_by_0044"] = ref
    return rec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="source database (opened READ-ONLY)")
    ap.add_argument("--narrator", required=True)
    ap.add_argument("--conv-ids", default="")
    ap.add_argument("--data-dir", default="", help="DATA_DIR, for the refused-signal record")
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    conv_ids = ([c.strip() for c in args.conv_ids.split(",") if c.strip()]
                or list(DEFAULT_CONV_IDS))
    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2
    data_dir = Path(args.data_dir) if args.data_dir else db.parent.parent
    if not (data_dir / "memory").is_dir():
        data_dir = None

    con = ro(db)
    try:
        out: Dict[str, Any] = {
            "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "read_only": True, "db": str(db), "narrator": args.narrator,
            "data_dir_for_refused_signal": str(data_dir) if data_dir else None,
            "conversations": [inspect_conv(con, args.narrator, c, data_dir)
                              for c in conv_ids],
        }
        if _has(con, "schema_migrations"):
            mcols = _cols(con, "schema_migrations")
            out["migration_0044"] = [
                {k: r[k] for k in r.keys()} for r in con.execute(
                    "SELECT * FROM schema_migrations WHERE "
                    + (" name LIKE '%0044%'" if "name" in mcols else " 1=0"))]
        out["sessions_without_owner_total"] = con.execute(
            "SELECT COUNT(*) FROM sessions WHERE person_id IS NULL OR person_id=''"
        ).fetchone()[0]
        out["sessions_total"] = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    finally:
        con.close()

    # ── verdict per conversation ──────────────────────────────────────
    for c in out["conversations"]:
        if c["recorded_link_present"] and c["recorded_link_names_this_narrator"]:
            c["reading"] = ("RECORDED LINK PRESENT and names this narrator, yet person_id "
                            "is NULL -> the 0044 backfill did not take effect for this row. "
                            "A deliberate migration/repair question. Do NOT infer ownership "
                            "at export time to paper over it.")
        elif c["recorded_link_present"]:
            c["reading"] = ("RECORDED LINK PRESENT but it names someone else, or more than "
                            "one narrator -> ambiguity. 0044 correctly left it NULL and the "
                            "exporter must keep refusing.")
        else:
            c["reading"] = ("NO RECORDED LINK in any 0044 source -> genuinely unowned legacy "
                            "residue. DO NOT widen ownership. The ledger rows naming its turns "
                            "are stale derived references; the fix belongs to how those travel.")

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"residue-provenance-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY provenance inspection of {db}")
    print(f"narrator {args.narrator}")
    print(f"sessions without owner: {out['sessions_without_owner_total']} "
          f"of {out['sessions_total']}\n")
    for c in out["conversations"]:
        print("=" * 74)
        print(f"{c['conv_id']}   turns={c['turn_count']}   "
              f"person_id={(c['session'] or {}).get('person_id')!r}   "
              f"person_id_source={(c['session'] or {}).get('person_id_source')!r}")
        print("=" * 74)
        print("  0044 RECORDED LINKS (the only attribution evidence that counts)")
        for k, v in c["recorded_links_0044"].items():
            if not v.get("source_table_present"):
                print(f"    {k:<32} table absent")
            elif not v.get("usable"):
                print(f"    {k:<32} unusable columns")
            else:
                print(f"    {k:<32} rows={v.get('rows_for_this_conv_id', v.get('turns_carrying_person_id'))}"
                      f"  owners={v.get('distinct_owners')}"
                      f"  would_have_filled={v.get('would_0044_have_filled')}")
        print(f"    -> recorded link present: {c['recorded_link_present']}"
              f"   names this narrator: {c['recorded_link_names_this_narrator']}")

        print("\n  STRUCTURAL REFERENCES to this conv_id")
        if not c["structural_references"]:
            print("    none")
        for k, v in sorted(c["structural_references"].items()):
            print(f"    {k:<44} rows={v['rows']}  owners={v['owner_columns'] or '-'}")

        circ = c["circular_not_evidence"]
        led = circ.get("ledger_rows_naming_turns_in_this_conversation") or []
        print(f"\n  CIRCULAR, NOT EVIDENCE — extraction ledger rows naming these turns: {len(led)}"
              f"  narrators={circ.get('distinct_narrators_on_those_ledger_rows')}")

        arch = c["refused_by_0044"].get("archive_directories") or []
        print(f"  REFUSED BY 0044 — archive directories naming this conv: {len(arch)}"
              + (f"  under person_id={[a['person_id'] for a in arch]}" if arch else ""))

        print(f"\n  READING: {c['reading']}")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
