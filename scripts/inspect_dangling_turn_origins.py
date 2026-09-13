#!/usr/bin/env python3
"""READ ONLY. What are these turns and conversations in the SOURCE database?

WO-LOREVOX-PORTABLE-NARRATOR-01, the bounded laptop question opened 2026-09-12.

The laptop's Christopher package carries nine `turn_extraction_ledger` rows whose
`turnrow:<turns.id>` keys name turns the package does not contain. The package itself
cannot say why — see `scripts/dangling_turn_reference_report.py`, which states exactly
what a zip can and cannot prove. This script asks the ONE question that settles it,
against the live source database, and writes nothing.

**IT OPENS THE DATABASE STRICTLY READ-ONLY** (`file:...?mode=ro`), runs only SELECTs,
and never imports the erasure or export paths. Running it cannot alter a narrator.

It answers, per referenced turn id and per conversation:

  A. turns and sessions exist and are Christopher-owned  -> ownership/export closure defect
  B. they exist as NULL-owner residue reachable ONLY from Christopher-owned rows
                                                          -> a DirectOrExclusiveInbound case
                                                             may be justified (§36.5 pattern)
  C. the turns no longer exist, the ledger rows remain    -> stale derived ledger state;
                                                             DO NOT widen ownership
  D. they belong to another narrator, or are ambiguously shared
                                                          -> the exporter must keep refusing;
                                                             a ledger row cannot justify
                                                             pulling those turns in

**This script does not choose among A-D.** It prints the evidence each one needs.

USAGE (on the laptop, stack may be running -- this is read-only)

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python scripts/inspect_dangling_turn_origins.py \\
        --db /mnt/c/hornelore_data/db/lorevox.sqlite3 \\
        --narrator a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2

Defaults cover the nine turn ids and three conversations the package named; override with
--turn-ids / --conv-ids, or point --report at a dangling report.json to read them from it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

#: Measured from the laptop's Christopher package (`a2f360689b58`), 2026-09-12.
DEFAULT_TURN_IDS = [1455, 1461, 1467, 1471, 1477, 1515, 1517, 1529, 1579]
DEFAULT_CONV_IDS = ["switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"]


def ro(db: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _cols(con, table) -> List[str]:
    return [r["name"] for r in con.execute(f'PRAGMA table_info("{table}")')]


def _has(con, table) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _preview(text: Any, n: int = 90) -> str:
    """Bounded preview. Narrator words are not spilled wholesale into a report that may
    be pasted around; enough to recognise the turn, no more."""
    s = "" if text is None else str(text)
    return (s[:n] + f"...(+{len(s) - n})") if len(s) > n else s


def inspect(con, narrator: str, turn_ids: List[int], conv_ids: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "narrator": narrator,
        "turns": [], "conversations": [], "notes": [],
    }

    sess_cols = _cols(con, "sessions") if _has(con, "sessions") else []
    has_src = "person_id_source" in sess_cols

    # ── per referenced turn id ───────────────────────────────────────
    for tid in turn_ids:
        row = con.execute("SELECT * FROM turns WHERE id=?", (tid,)).fetchone()
        rec: Dict[str, Any] = {"turn_id": tid, "turn_exists": row is not None}
        if row is not None:
            rec.update({
                "conv_id": row["conv_id"], "role": row["role"], "ts": row["ts"],
                "content_preview": _preview(row["content"]),
                "content_chars": len(str(row["content"] or "")),
            })
            s = con.execute("SELECT * FROM sessions WHERE conv_id=?", (row["conv_id"],)).fetchone()
            rec["session_exists"] = s is not None
            if s is not None:
                rec["session_person_id"] = s["person_id"]
                rec["session_person_id_is_null_or_blank"] = s["person_id"] in (None, "")
                rec["directly_owned_by_this_narrator"] = (s["person_id"] == narrator)
                if has_src:
                    rec["session_person_id_source"] = s["person_id_source"]
        # the ledger row that named it, as it stands in the LIVE database
        if _has(con, "turn_extraction_ledger"):
            led = con.execute(
                "SELECT * FROM turn_extraction_ledger WHERE turn_key=?", (f"turnrow:{tid}",)).fetchall()
            rec["ledger_rows_now"] = [
                {k: l[k] for k in l.keys() if k in
                 ("id", "narrator_id", "turn_key", "turn_id", "conv_id", "status", "state", "created_at")}
                for l in led]
        if _has(con, "turn_extraction_results"):
            res = con.execute(
                "SELECT id, narrator_id, ledger_id FROM turn_extraction_results WHERE turn_key=?",
                (f"turnrow:{tid}",)).fetchall()
            rec["result_rows_now"] = [dict(r) for r in res]
        # anything else that still points at this turn
        others: Dict[str, Any] = {}
        if _has(con, "story_candidates"):
            sc = _cols(con, "story_candidates")
            for c in ("source_user_turn_row_id", "completed_assistant_turn_row_id"):
                if c in sc:
                    n = con.execute(
                        f'SELECT COUNT(*) FROM story_candidates WHERE "{c}"=?', (tid,)).fetchone()[0]
                    if n:
                        others[f"story_candidates.{c}"] = n
        if _has(con, "trip_turn_links"):
            n = con.execute("SELECT COUNT(*) FROM trip_turn_links "
                            "WHERE user_turn_row_id=? OR assistant_turn_row_id=?",
                            (tid, tid)).fetchone()[0]
            if n:
                others["trip_turn_links"] = n
        if _has(con, "bio_facts"):
            n = con.execute("SELECT COUNT(*) FROM bio_facts WHERE source LIKE ?",
                            (f'%turnrow:{tid}"%',)).fetchone()[0]
            if n:
                others["bio_facts.source"] = n
        rec["still_referenced_by"] = others
        out["turns"].append(rec)

    # ── per conversation the ledger rows named ───────────────────────
    # The ledger rows carry these conv_ids. If the turns were deleted but the session
    # survives, or the session is NULL-owner residue, the conversation row says far more
    # than the turn ids alone.
    for cid in conv_ids:
        s = con.execute("SELECT * FROM sessions WHERE conv_id=?", (cid,)).fetchone()
        rec: Dict[str, Any] = {"conv_id": cid, "session_exists": s is not None}
        if s is not None:
            rec["person_id"] = s["person_id"]
            rec["person_id_is_null_or_blank"] = s["person_id"] in (None, "")
            rec["directly_owned_by_this_narrator"] = (s["person_id"] == narrator)
            if has_src:
                rec["person_id_source"] = s["person_id_source"]
            for k in ("title", "updated_at", "created_at"):
                if k in sess_cols:
                    rec[k] = s[k]
        rec["turns_now_in_this_conversation"] = con.execute(
            "SELECT COUNT(*) FROM turns WHERE conv_id=?", (cid,)).fetchone()[0]
        rec["turn_id_range"] = [r for r in con.execute(
            "SELECT MIN(id), MAX(id) FROM turns WHERE conv_id=?", (cid,)).fetchone()]

        # EXCLUSIVITY — the §36.5 question. Which narrators reach this conversation
        # through their own owned rows? If exactly one, a DirectOrExclusiveInbound case
        # may be justified; if more than one, it is ambiguous and must stay refused.
        reachers = set()
        if _has(con, "trip_turn_links") and _has(con, "trips"):
            for r in con.execute(
                "SELECT DISTINCT t.person_id FROM trip_turn_links l "
                "JOIN trips t ON t.id = l.trip_id WHERE l.conv_id=?", (cid,)):
                if r[0]:
                    reachers.add(r[0])
        if _has(con, "memory_archive_sessions"):
            for r in con.execute(
                "SELECT DISTINCT person_id FROM memory_archive_sessions WHERE conv_id=?", (cid,)):
                if r[0]:
                    reachers.add(r[0])
        if _has(con, "turn_extraction_ledger"):
            lc = _cols(con, "turn_extraction_ledger")
            if "conv_id" in lc:
                for r in con.execute(
                    "SELECT DISTINCT narrator_id FROM turn_extraction_ledger WHERE conv_id=?", (cid,)):
                    if r[0]:
                        reachers.add(r[0])
        rec["narrators_reaching_this_conversation"] = sorted(reachers)
        rec["exclusively_reached_by_this_narrator"] = (reachers == {narrator})
        out["conversations"].append(rec)

    # ── the reading, stated as options rather than a conclusion ──────
    exists = [t for t in out["turns"] if t["turn_exists"]]
    out["summary"] = {
        "turn_ids_checked": len(turn_ids),
        "turns_that_exist": len(exists),
        "turns_that_do_not_exist": len(turn_ids) - len(exists),
        "turns_directly_owned_by_this_narrator":
            sum(1 for t in exists if t.get("directly_owned_by_this_narrator")),
        "turns_in_null_owner_sessions":
            sum(1 for t in exists if t.get("session_person_id_is_null_or_blank")),
        "turns_in_another_narrators_session":
            sum(1 for t in exists if t.get("session_exists")
                and not t.get("session_person_id_is_null_or_blank")
                and not t.get("directly_owned_by_this_narrator")),
    }
    s = out["summary"]
    if s["turns_that_exist"] == 0:
        out["reading"] = ("C — the turns do not exist in this database while the ledger rows "
                          "remain: stale derived ledger state. DO NOT widen ownership.")
    elif s["turns_directly_owned_by_this_narrator"] == s["turns_that_exist"]:
        out["reading"] = ("A — the turns exist and are directly owned by this narrator, so the "
                          "export omitted rows it should have carried: an ownership/export "
                          "closure defect in Portable Narrator.")
    elif s["turns_in_another_narrators_session"]:
        out["reading"] = ("D — at least one referenced turn belongs to another narrator. The "
                          "exporter must keep refusing; a ledger row cannot justify pulling "
                          "another narrator's turn into this package.")
    elif s["turns_in_null_owner_sessions"]:
        out["reading"] = ("B (candidate) — the turns sit in NULL-owner residue sessions. Check "
                          "`exclusively_reached_by_this_narrator` per conversation: exclusive "
                          "reach may justify another DirectOrExclusiveInbound case (§36.5); "
                          "shared reach must stay refused.")
    else:
        out["reading"] = "MIXED — read the per-turn rows; do not summarise this into one cause."
    out["reminder"] = ("This script reports evidence. A reference pointing outside the "
                       "narrator-owned closure is never by itself a reason to widen ownership.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="source database (opened READ-ONLY)")
    ap.add_argument("--narrator", required=True)
    ap.add_argument("--turn-ids", default="", help="comma-separated; defaults to the nine measured ids")
    ap.add_argument("--conv-ids", default="", help="comma-separated; defaults to the three measured ids")
    ap.add_argument("--report", default="", help="a dangling report.json to read ids from instead")
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    turn_ids, conv_ids = list(DEFAULT_TURN_IDS), list(DEFAULT_CONV_IDS)
    if args.report:
        rep = json.loads(Path(args.report).read_text(encoding="utf-8"))
        turn_ids = sorted({r["parsed_turns_id"] for r in rep.get("rows", [])}) or turn_ids
        conv_ids = sorted({r["conv_or_session_on_ledger_row"] for r in rep.get("rows", [])
                           if r.get("conv_or_session_on_ledger_row")}) or conv_ids
    if args.turn_ids:
        turn_ids = [int(x) for x in args.turn_ids.split(",") if x.strip()]
    if args.conv_ids:
        conv_ids = [x.strip() for x in args.conv_ids.split(",") if x.strip()]

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2
    con = ro(db)
    try:
        rep = inspect(con, args.narrator, turn_ids, conv_ids)
    finally:
        con.close()

    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"dangling-origins-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str),
                                        encoding="utf-8")

    print(f"READ-ONLY inspection of {db}")
    print(f"narrator {rep['narrator']}\n")
    print("TURNS")
    for t in rep["turns"]:
        if not t["turn_exists"]:
            print(f"  {t['turn_id']:>6}  DOES NOT EXIST   ledger rows now: {len(t.get('ledger_rows_now') or [])}")
            continue
        print(f"  {t['turn_id']:>6}  exists  conv={t.get('conv_id')}  role={t.get('role')}  "
              f"owner={t.get('session_person_id')!r}  ours={t.get('directly_owned_by_this_narrator')}")
        print(f"          {t.get('content_preview','')}")
    print("\nCONVERSATIONS")
    for c in rep["conversations"]:
        if not c["session_exists"]:
            print(f"  {c['conv_id']}  SESSION DOES NOT EXIST  turns now: {c['turns_now_in_this_conversation']}")
            continue
        print(f"  {c['conv_id']}  person_id={c.get('person_id')!r}  ours={c.get('directly_owned_by_this_narrator')}  "
              f"turns now={c['turns_now_in_this_conversation']} {c['turn_id_range']}")
        print(f"      reached by: {c['narrators_reaching_this_conversation']}  "
              f"exclusive to us: {c['exclusively_reached_by_this_narrator']}")
    print(f"\nSUMMARY  {json.dumps(rep['summary'])}")
    print(f"\nREADING  {rep['reading']}")
    print(f"\n{rep['reminder']}")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
