"""Classify the queued suggestions that WO-04 made actionable.

PRINTS BY DEFAULT. INSERTS NOTHING WITHOUT --apply.

WHY THIS EXISTS
---------------
Adding `military`, `residence`, `travel` and `faith` flips WO-03B's
destination guard for every queued proposal aimed at them. Kent's
`military.branch = "Nike Ajax Nike Hercules missile site"` was "cannot
be added" and is now one entry-pick from his family's record.

The structural guard in `suggestion_flags.requires_correction` already
refuses those, with no flag needed. This script adds the RECORD — what
was flagged, why, and when — so a reviewer sees a reason rather than a
bare refusal.

WHAT IT DOES NOT DO
-------------------
It does not accept, decline, migrate, rewrite or delete anything. A flag
makes acceptance require an explicit correction; it resolves nothing.

TWO KINDS OF REASON, AND THEY ARE NOT EQUIVALENT
------------------------------------------------
`queued_before_home` is a FACT about timing — this was proposed before
the questionnaire had a place for it. It asserts nothing about the
content and needs no judgement, so it is applied to every affected row.

The other three are the reconciliation's OPINION that a value does not
match its field. They are proposed here for a person to confirm or
correct, which is why the default run prints and stops. Treat them as a
review set, not as nine established false facts — a reassignment being
a "significant event" is arguable, and the reviewer should see the
value and decide.

Usage, from WSL:

    python3 scripts/seed_suggestion_flags.py
    python3 scripts/seed_suggestion_flags.py --apply
    python3 scripts/seed_suggestion_flags.py --apply --only queued_before_home
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

DB = os.environ.get("HORNELORE_DB", "/mnt/c/hornelore_data/db/hornelore.sqlite3")
G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

# The reconciliation's review set: (fieldPath, value-substring) -> reason.
# Matched on the value too, so a DIFFERENT value at the same path is not
# swept up by an opinion formed about this one.
PROPOSED = {
    ("military.branch", "Nike Ajax"): (
        "value_not_a_field",
        "An installation and a missile system, not a branch of service. "
        "WO-04 added military.unit for the unit and military.location for "
        "where; branch is Army/Navy/RAF."),
    ("military.rank", "assigned to go up"): (
        "value_not_a_field",
        "A training episode, not a rank. military.notableEvents fits it."),
    ("military.yearsOfService", "in Germany"): (
        "value_not_a_field",
        "A place in a years field. The path is retired; military.location "
        "is where."),
    ("community.organization", "32nd Artillery"): (
        "misclassified_section",
        "A military unit filed as a community organisation. WO-04 added "
        "military.unit."),
    ("education.notes", "tests and medical exams"): (
        "misclassified_section",
        "Military induction, not education."),
    ("residence.period", "mostly"): (
        "model_uncertainty",
        "Not a period. Residence dates are now two fields and an unknown "
        "date stays blank."),
    ("residence.period", "temporal context implies"): (
        "model_uncertainty",
        "The model describing what it does not know, stored as a value."),
    ("family.marriageDate", "temporal context implies"): (
        "model_uncertainty",
        "The model describing what it does not know, stored as a date."),
    ("travel.purpose", "ate our first"): (
        "value_not_a_field",
        "Something that happened on the trip, not a purpose. WO-04 added "
        "travel.whatHappened."),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually insert the flags (default: print only)")
    ap.add_argument("--only", choices=("queued_before_home", "opinions"),
                    help="restrict to timing facts, or to the review set")
    ap.add_argument("--by", default="", help="who is recording these")
    args = ap.parse_args()

    from api.services import questionnaire_schema as qs
    from api.services.suggestion_review import split_destination
    from api.services import suggestion_flags as flags

    con = sqlite3.connect(DB if args.apply else f"file:{DB}?mode=ro", uri=not args.apply)
    con.row_factory = sqlite3.Row

    planned = []
    preexisting = []
    for r in con.execute("""SELECT p.id, p.display_name n, ip.projection_json j
                            FROM interview_projections ip
                            JOIN people p ON p.id = ip.person_id
                            ORDER BY p.display_name"""):
        for s in (json.loads(r["j"] or "{}") or {}).get("pendingSuggestions") or []:
            if not isinstance(s, dict):
                continue
            fp = str(s.get("fieldPath") or "")
            val = "" if s.get("value") is None else str(s.get("value"))
            sec, fld, _rep = split_destination(fp)

            reason = note = None
            for (p_path, frag), (rsn, nte) in PROPOSED.items():
                if fp == p_path and frag.lower() in val.lower():
                    reason, note = rsn, nte
                    break
            if reason is None and "destination_undefined" not in s and qs.is_defined(sec, fld):
                # A FACT, not a judgement — but only for the destinations
                # WO-04 created. `queued_before_home` means exactly what
                # it says, and saying it about a field that existed all
                # along would be a false record in a table whose whole
                # purpose is accurate ones.
                if sec in flags.SECTIONS_ADDED_BY_WO04:
                    reason, note = "queued_before_home", (
                        "Proposed before the questionnaire had a place for it; "
                        "nobody chose this destination.")
                else:
                    # Legacy rows at destinations that ALREADY EXISTED.
                    # Not in WO-04's scope, and reported separately below
                    # rather than swept under a reason that does not fit.
                    preexisting.append((r["id"], r["n"], s, fp, val))
                    continue
            if reason is None:
                continue
            if args.only == "queued_before_home" and reason != "queued_before_home":
                continue
            if args.only == "opinions" and reason == "queued_before_home":
                continue
            planned.append((r["id"], r["n"], s, reason, note, fp, val))

    print(f"\n{'='*74}\n  WO-04 — suggestion flags\n{'='*74}\n")
    if not planned:
        print("  Nothing to flag.\n")
        con.close()
        return 0

    facts = [p for p in planned if p[3] == "queued_before_home"]
    opinions = [p for p in planned if p[3] != "queued_before_home"]

    if facts:
        print(f"  A FACT about timing — no judgement, safe to apply ({len(facts)}):\n")
        for _pid, n, _s, _r, _note, fp, val in facts:
            print(f"    [{n.split()[0]:<11}] {fp:<26} {val[:44]!r}")
    if opinions:
        print(f"\n  {Y}THE RECONCILIATION'S OPINION — read each before applying "
              f"({len(opinions)}):{X}\n")
        for _pid, n, _s, r, note, fp, val in opinions:
            print(f"    [{n.split()[0]:<11}] {fp}")
            print(f"        value : {val[:100]!r}")
            print(f"        reason: {r}")
            print(f"        why   : {note}\n")

    if preexisting:
        print(f"\n  {R}NOT IN WO-04's SCOPE — and these are the unprotected ones "
              f"({len(preexisting)}):{X}\n")
        print("    These were queued at destinations that ALREADY EXISTED, so they")
        print("    are acceptable TODAY — before WO-04, and still after it. The")
        print("    structural guard covers only the four sections WO-04 created, and")
        print("    the ruling scoped `queued_before_home` to those. Calling these")
        print("    'queued before home' would be a false record.\n")
        for _pid, n, _s, fp, val in preexisting:
            print(f"    [{n.split()[0]:<11}] {fp:<26} {val[:52]!r}")
        print(f"\n    {Y}Three of these look plainly wrong and are one click from a")
        print(f"    family record. They need a decision this script must not make.{X}\n")

    if not args.apply:
        print(f"  {Y}Nothing was written.{X}")
        print("    --apply                              record all of the above")
        print("    --apply --only queued_before_home    record just the timing facts")
        print("    --apply --only opinions              record just the review set\n")
        con.close()
        return 0

    con.execute("BEGIN IMMEDIATE")
    try:
        for pid, _n, s, reason, note, _fp, _val in planned:
            flags.record_flag(con, pid, s, reason, source_note=note or "",
                              flagged_by=args.by)
        con.commit()
    except Exception:
        con.rollback()
        raise
    n = con.execute("SELECT COUNT(*) FROM suggestion_flags WHERE disposition IS NULL").fetchone()[0]
    con.close()
    print(f"  {G}Recorded {len(planned)} flags. {n} undisposed in total.{X}")
    print("  No suggestion was accepted, declined, moved or deleted.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
