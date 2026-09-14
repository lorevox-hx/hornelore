#!/usr/bin/env python3
"""READ ONLY. What is ACTUALLY in Christopher's export closure right now, and what
would the repair change?

WO-LOREVOX-PORTABLE-NARRATOR-01, 2026-09-14. The final preflight before the source
write. Not another investigation.

THE DEFECT THIS EXISTS TO CORRECT. The Christopher repair plan asserted:

    "A session left NULL stays out of the package by construction."

**That is false under the shipped declaration.** `sessions` is owned by
`DirectOrExclusiveInbound`, so a NULL-owner session that one of Christopher's owned
`trip_turn_links` reaches EXCLUSIVELY is his by derivation, and its `turns` follow
through `Parent("conv_id","sessions","conv_id")`. That is the §36.5 ownership-closure
fix, in production. Two consequences the plan got wrong:

  * the 533-record baseline ALREADY contains 9 derived sessions and 100 turns, so
    materialising `person_id` on a session already in closure changes its provenance,
    NOT the record count. The plan's 578/597/654 figures are unsound;
  * leaving a development session NULL does NOT keep it out. `tdlab_9538…` (1 trip
    link) and `switch_mseorb11_acy7` (4) may be in the package regardless of what we
    decide about their ownership.

NOTHING HERE IS RECONSTRUCTED. The closure is computed by importing the shipped
declaration and running `inv.select_sql(...)` / `inv.owner_predicate(...)` verbatim.
A hand-written approximation of the predicate could not settle a question about the
predicate.

**OPENS THE DATABASE STRICTLY READ-ONLY.** SELECTs only. No ownership repair, no
delete, no export.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code python3 scripts/christopher_closure_preflight.py \\
        --db /mnt/c/hornelore_data/db/hornelore.sqlite3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set

sys.path.insert(0, os.path.join(os.getcwd(), "server", "code"))
try:
    from api.services import narrator_data_inventory as inv
except Exception as e:                                        # pragma: no cover
    sys.exit(f"cannot import narrator_data_inventory ({e})\n"
             f"run with: PYTHONPATH=server/code python3 {sys.argv[0]} ...")

CHRIS = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2"

CANONICAL = {"switch_mrb7cut9_04pi", "switch_ms8z59ie_xakt", "switch_msaiqgs2_a1mu"}
REJECTED_CANDIDATES = {"switch_mseorb11_acy7",
                       "tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3",
                       "switch_mre0txvh_tb7w", "switch_mrkpipjr_twr7"}
DANGLING = {"switch_ms81wxvv_pxxh", "switch_ms8xrcuw_adlz", "switch_msaedccx_fkm1"}
VERIFY = ["switch_mrb7cut9_04pi", "switch_ms8z59ie_xakt", "switch_msaiqgs2_a1mu",
          "switch_mseorb11_acy7", "tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3"]
DANGLING_LEDGER_TURNS = [1455, 1461, 1467, 1471, 1477, 1515, 1517, 1529, 1579]


def ro(db: Path):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _has(con, t):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (t,)).fetchone())


def _cat(cid: str) -> str:
    if cid in CANONICAL:
        return "CANONICAL (keep)"
    if cid in DANGLING:
        return "DANGLING-REFERENCE session"
    if cid in REJECTED_CANDIDATES:
        return "REJECTED candidate (not keeping)"
    return "development/test residue"


def lane_counts(con, pid: str, live: Set[str]) -> Dict[str, int]:
    """Exactly what the preflight sums: owner_predicate per narrator-owned lane."""
    out: Dict[str, int] = {}
    for lane in inv.DB_LANES:
        if isinstance(lane.owner, inv.Installation) or lane.table not in live:
            continue
        try:
            sql = (f'SELECT COUNT(*) c FROM "{lane.table}" '
                   f'WHERE {inv.owner_predicate(lane.table)}')
            out[lane.table] = con.execute(sql, {"pid": pid}).fetchone()["c"]
        except sqlite3.Error:
            pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True)
    ap.add_argument("--narrator", default=CHRIS)
    ap.add_argument("--out", default=".runtime/two_origin/reports")
    args = ap.parse_args(argv)

    db = Path(args.db)
    if not db.is_file():
        print(f"database not found: {db}", file=sys.stderr)
        return 2
    pid = args.narrator

    con = ro(db)
    try:
        live = {r["name"] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}

        # ── the ACTUAL closure, from the shipped predicate ────────────
        closure = [r["conv_id"] for r in con.execute(inv.select_sql("sessions"),
                                                     {"pid": pid})]
        direct = {r["conv_id"] for r in con.execute(
            "SELECT conv_id FROM sessions WHERE person_id = ?", (pid,))}
        derived = [c for c in closure if c not in direct]

        counts = lane_counts(con, pid, live)
        records_now = sum(counts.values())

        # ── per derived session: what pulls it in ────────────────────
        rows: List[Dict[str, Any]] = []
        for cid in sorted(set(closure) | set(VERIFY)):
            in_closure = cid in closure
            links = con.execute(
                "SELECT l.id, l.trip_id, l.trip_day_id, l.placement_source, "
                "       l.placement_status, t.person_id AS trip_owner, t.title AS trip_title "
                "  FROM trip_turn_links l LEFT JOIN trips t ON t.id = l.trip_id "
                " WHERE l.conv_id = ?", (cid,)).fetchall() if _has(con, "trip_turn_links") else []
            mine = [l for l in links if l["trip_owner"] == pid]
            others = sorted({l["trip_owner"] for l in links
                             if l["trip_owner"] and l["trip_owner"] != pid})
            n_turns = con.execute("SELECT COUNT(*) FROM turns WHERE conv_id=?",
                                  (cid,)).fetchone()[0]
            sess = con.execute("SELECT person_id, person_id_source FROM sessions "
                               "WHERE conv_id=?", (cid,)).fetchone()
            rows.append({
                "conv_id": cid,
                "category": _cat(cid),
                "in_closure_now": in_closure,
                "person_id": sess["person_id"] if sess else None,
                "person_id_source": sess["person_id_source"] if sess else None,
                "admitted_by": ("direct person_id" if cid in direct
                                else "DERIVED via trip_turn_links" if in_closure
                                else "not admitted"),
                "turns": n_turns,
                "christopher_trip_links": [
                    {"link_id": l["id"], "trip_id": l["trip_id"],
                     "trip_title": l["trip_title"],
                     "trip_day_id": l["trip_day_id"],
                     "placement_source": l["placement_source"],
                     "placement_status": l["placement_status"]} for l in mine],
                "other_narrators_linking": others,
            })

        # ── the write set ────────────────────────────────────────────
        # 1. ownership to materialise: canonical sessions, whatever their route in
        materialise = [r for r in rows if r["conv_id"] in CANONICAL]
        # 2. stale ledger rows
        stale_ledger = []
        if _has(con, "turn_extraction_ledger"):
            marks = ",".join("?" * len(DANGLING_LEDGER_TURNS))
            stale_ledger = [dict(r) for r in con.execute(
                f"SELECT id, narrator_id, turn_key, session_id FROM "
                f"turn_extraction_ledger WHERE turn_key IN ({marks})",
                [f"turnrow:{i}" for i in DANGLING_LEDGER_TURNS])]
        # 3. links that drag unwanted sessions in
        draggers = [r for r in rows
                    if r["in_closure_now"] and r["conv_id"] not in CANONICAL
                    and r["admitted_by"].startswith("DERIVED")
                    and r["christopher_trip_links"]]
        # 4. what "only the 3 canonical survive" would actually cost
        already_in = [c for c in CANONICAL if c in closure]
        not_in = [c for c in CANONICAL if c not in closure]
        add_turns = sum(r["turns"] for r in rows if r["conv_id"] in not_in)
        expected = records_now + len(not_in) + add_turns
    finally:
        con.close()

    out = {
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "read_only": True, "db": str(db), "narrator": pid,
        "corrects": "the repair plan's claim that a NULL-owner session stays out of "
                    "the package by construction — DirectOrExclusiveInbound admits it "
                    "when a Christopher-owned trip_turn_link reaches it exclusively",
        "records_now": records_now, "lane_counts": counts,
        "sessions_in_closure": len(closure), "directly_owned": len(direct),
        "derived_into_closure": len(derived),
        "sessions": rows,
        "write_set": {
            "materialise_ownership": [r["conv_id"] for r in materialise],
            "stale_ledger_rows": stale_ledger,
            "links_dragging_unwanted_sessions": [
                {"conv_id": r["conv_id"], "category": r["category"],
                 "links": r["christopher_trip_links"]} for r in draggers],
        },
        "expected_after_canonical_only": expected,
    }
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.out) / f"christopher-closure-preflight-{ts}"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "report.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"READ-ONLY closure preflight — {db}")
    print("Closure computed from the SHIPPED declaration, not a reconstruction.\n")
    print(f"  records in closure now : {records_now}   "
          f"(the preflight's figure; 533 was measured 2026-09-12)")
    print(f"  sessions in closure    : {len(closure)}  "
          f"(direct {len(direct)}, DERIVED {len(derived)})")
    print(f"  turns in closure       : {counts.get('turns')}")

    print("\n" + "=" * 76)
    print("EVERY SESSION IN CLOSURE, AND WHAT ADMITS IT")
    print("=" * 76)
    for r in sorted(rows, key=lambda x: (not x["in_closure_now"], x["category"])):
        mark = "" if r["in_closure_now"] else "   [NOT IN CLOSURE]"
        print(f"\n  {r['conv_id']}{mark}")
        print(f"    {r['category']}   turns={r['turns']}")
        print(f"    admitted by: {r['admitted_by']}   "
              f"person_id={r['person_id']!r} src={r['person_id_source']!r}")
        for l in r["christopher_trip_links"]:
            print(f"      link {l['link_id'][:8]}  trip={str(l['trip_id'])[:8]} "
                  f"'{l['trip_title']}'  day={str(l['trip_day_id'])[:8] if l['trip_day_id'] else None}  "
                  f"{l['placement_source']}/{l['placement_status']}")
        if r["other_narrators_linking"]:
            print(f"      *** also linked by: {r['other_narrators_linking']} "
                  f"-> NOT exclusive, closure would refuse ***")

    print("\n" + "=" * 76)
    print("THE WRITE SET FOR THE REAL REPAIR")
    print("=" * 76)
    print("\n1. OWNERSHIP TO MATERIALISE (the 3 canonical sessions)")
    for r in materialise:
        already = "already in closure (provenance change only)" if r["in_closure_now"] \
            else f"NOT in closure — materialising ADDS it +{r['turns']} turns"
        print(f"   {r['conv_id']:<40} {already}")

    print(f"\n2. STALE EXTRACTION-LEDGER ROWS TO REMOVE ({len(stale_ledger)})")
    for l in stale_ledger:
        print(f"   id={l['id']:<5} {l['turn_key']:<16} session={l.get('session_id')}")

    print(f"\n3. LINKS DRAGGING UNWANTED SESSIONS INTO THE PACKAGE ({len(draggers)})")
    if not draggers:
        print("   none — every derived session in closure is one we are keeping")
    for r in draggers:
        print(f"   {r['conv_id']}  ({r['category']}, {r['turns']} turns)")
        for l in r["christopher_trip_links"]:
            print(f"      link {l['link_id']}  trip '{l['trip_title']}'  "
                  f"{l['placement_source']}/{l['placement_status']}")
        print("      DECIDE: is this link genuine travel provenance (then the session")
        print("              must stay, and it is family data after all), or")
        print("              development provenance (then the link is removed and the")
        print("              session leaves closure with it)?")
        print("      NOTE: removing the link also removes a narrator-owned row that")
        print("            currently travels. That is a data decision, not cleanup.")

    print("\n4. RECORD-COUNT EXPECTATION — 'only the 3 canonical survive'")
    print(f"   canonical already in closure : {already_in}")
    print(f"   canonical NOT yet in closure : {not_in}  (+{add_turns} turns)")
    print(f"   records now                  : {records_now}")
    print(f"   expected after ownership materialisation only : {expected}")
    print("   (the plan's 578 assumed all three were absent; measure, do not adopt)")
    print("   Removing links or ledger rows moves this DOWN — recompute after deciding 3.")
    print("\n   Nothing written, deleted, repaired or exported.")
    print(f"\nwritten: {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
