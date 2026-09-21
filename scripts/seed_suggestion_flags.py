"""Classify the queued suggestions that WO-04 made actionable.

PRINTS BY DEFAULT. INSERTS NOTHING WITHOUT --apply.

WHY THIS EXISTS
---------------
Adding `military`, `residence`, `travel` and `faith` flips WO-03B's
destination guard for every queued proposal aimed at them. Kent's
`military.branch = "Nike Ajax Nike Hercules missile site"` was "cannot
be added" and is now one entry-pick from his family's record.

The structural tiers in `suggestion_flags.requires_review` already
refuse those, with no flag needed. This script adds the RECORD — what
was flagged, why, and when — so a reviewer sees a reason rather than a
bare refusal.

WHAT IT DOES NOT DO
-------------------
It does not accept, decline, migrate, rewrite or delete anything. It
writes to ONE table, `suggestion_flags`, and to no other. No suggestion
is altered; no biographical answer is touched; no review record is
created. A flag makes acceptance require an explicit correction; it
resolves nothing.

Running it twice records the same flags, not duplicates — the primary
key is the canonical tuple and the ON CONFLICT re-states the same
reason. `--verify-idempotent` proves that on a throwaway copy of the
database, changing nothing real.

WHAT IT NO LONGER HAS TO CARRY
------------------------------
The first version of this script reported a third group — legacy
proposals at destinations that ALREADY EXISTED, including
`personal.fullName = "kind of scared"` — under the heading "NOT IN
WO-04's SCOPE", because the structural guard covered only the four new
sections and `queued_before_home` would have been a false record about
them.

They are in scope now. `requires_review` refuses every legacy proposal,
at the ACKNOWLEDGE level for these: a person must say they have read it
before it can become permanent. That requirement is DERIVED from the
proposal's own shape, so it needs no row here, cannot be forgotten by a
classifier that did not run, and cannot be cleared by deleting a flag.
They are still listed below, because a reviewer should see them — but
as protected rows needing a look, not as an exposure.

THREE KINDS OF ENTRY, AND THEY ARE NOT EQUIVALENT
--------------------------------------------------
`queued_before_home` is a FACT about timing — this was proposed before
the questionnaire had a place for it. It asserts nothing about the
content and needs no judgement, so it is applied to every affected row.

The other three reasons are the reconciliation's OPINION that a value
does not match its field. They are proposed here for a person to
confirm or correct, which is why the default run prints and stops.
Treat them as a review set, not as twelve established false facts — a
reassignment being a "significant event" is arguable, and the reviewer
should see the value and decide.

Everything else legacy is covered structurally and appears under
"ALREADY PROTECTED", with nothing written for it.

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

    # ── legacy rows at destinations that already existed ─────────────
    #
    # These are covered structurally at the ACKNOWLEDGE level whether or
    # not a flag is recorded. They are named here because acknowledging
    # is not the right outcome for them: a person should not be able to
    # confirm "kind of scared" as a full name by ticking a box. A
    # recorded flag raises them to CORRECT.
    #
    # Only the ones that look plainly wrong. The other eight legacy rows
    # at pre-existing destinations get no flag, because there is nothing
    # wrong with them that anyone has identified — "old" is not a fault.
    ("personal.fullName", "kind of scared"): (
        "value_not_a_field",
        "An emotional state captured as a legal name. One acceptance from "
        "becoming what the Memoir, Timeline and Life Map all call him."),
    ("education.schooling", "induction physical"): (
        "misclassified_section",
        "A military induction filed as schooling. WO-04 added "
        "military.notableEvents."),
    ("personal.preferredName", "Christopher Todd Horne"): (
        "value_not_a_field",
        "A full formal name in the field for what someone is CALLED. "
        "Arguable — if he does go by all three names this is right, which "
        "is why it is in the review set and not applied by default."),
}


def _fingerprint(con) -> dict:
    """Everything this script must NOT change, reduced to hashes.

    Not a spot check of a few rows: the whole of every table a mistake
    could reach. If applying flags rewrites one suggestion, one
    questionnaire answer, one provenance row or one review, a hash
    moves and the comparison says which.
    """
    import hashlib
    out = {}
    for name, sql in (
        ("suggestions", "SELECT person_id, projection_json FROM interview_projections "
                        "ORDER BY person_id"),
        ("answers", "SELECT person_id, questionnaire_json FROM bio_builder_questionnaires "
                    "ORDER BY person_id"),
        ("provenance", "SELECT * FROM bio_builder_answer_provenance "
                       "ORDER BY person_id, section, entry_id, field"),
        ("reviews", "SELECT * FROM suggestion_reviews "
                    "ORDER BY person_id, section, entry_id, field, value_hash"),
    ):
        h = hashlib.sha256()
        try:
            for row in con.execute(sql):
                h.update(repr(tuple(row)).encode("utf-8"))
        except sqlite3.Error as e:
            out[name] = f"unreadable: {e}"
            continue
        out[name] = h.hexdigest()[:16]
    out["flag_rows"] = con.execute("SELECT COUNT(*) FROM suggestion_flags").fetchone()[0]
    return out


def _verify_idempotent(args) -> int:
    """Prove on a COPY that applying twice is the same as applying once,
    and that nothing outside `suggestion_flags` moves at all.

    The real database is opened read-only, copied, and never written.
    """
    import shutil
    import tempfile

    src = Path(DB)
    if not src.exists():
        print(f"{R}  No database at {DB}{X}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="flagverify_")) / "copy.sqlite3"
    # CONSISTENT snapshot via SQLite's online backup API. Copying the
    # database and its -wal separately can capture a torn state while the
    # stack is running, and a rehearsal against a torn copy proves
    # nothing. See `backfill_suggestion_ids.snapshot`.
    sys.path.insert(0, str(REPO / "scripts"))
    from backfill_suggestion_ids import snapshot
    snapshot(src, tmp)

    print(f"\n{'='*74}\n  IDEMPOTENCY CHECK — on a copy, at {tmp}\n{'='*74}\n")

    class _A:
        apply, only, by = True, args.only, args.by or "idempotency-check"

    con = sqlite3.connect(tmp)
    con.row_factory = sqlite3.Row
    before = _fingerprint(con)
    con.close()

    counts, states = [], []
    for run in (1, 2):
        n = _apply_to(tmp, _A)
        con = sqlite3.connect(tmp)
        con.row_factory = sqlite3.Row
        # SELECT *, deliberately. An earlier version listed columns and
        # so quietly excluded `flagged_at`, which DID move on every run.
        # A check that names the columns it compares is a check that can
        # be made to pass by shortening the list.
        rows = con.execute(
            "SELECT * FROM suggestion_flags "
            "ORDER BY person_id, section, field, value_hash").fetchall()
        states.append([tuple(r) for r in rows])
        counts.append(len(rows))
        after = _fingerprint(con)
        con.close()
        print(f"  run {run}: planned {n}, {len(rows)} flag rows in the table")

    ok = True
    print()
    if counts[0] == counts[1]:
        print(f"  {G}PASS{X}  row count unchanged by the second run "
              f"({counts[0]} both times)")
    else:
        ok = False
        print(f"  {R}FAIL{X}  row count changed: {counts[0]} -> {counts[1]}")

    if states[0] == states[1]:
        print(f"  {G}PASS{X}  every flag identical after the second run "
              f"(every column, including flagged_at)")
    else:
        ok = False
        print(f"  {R}FAIL{X}  flag contents changed between runs")
        for a, b in zip(states[0], states[1]):
            if a != b:
                print(f"           {a}\n        -> {b}")

    for key in ("suggestions", "answers", "provenance", "reviews"):
        if before[key] == after[key]:
            print(f"  {G}PASS{X}  {key:<12} untouched  ({before[key]})")
        else:
            ok = False
            print(f"  {R}FAIL{X}  {key:<12} REWRITTEN  {before[key]} -> {after[key]}")

    print(f"\n  The real database at {DB}\n  was opened read-only and never written.\n")
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return 0 if ok else 1


def _apply_to(db_path, args) -> int:
    """One apply pass against an explicit database path. Used by the
    idempotency check so both runs go through the same code the real
    `--apply` would."""
    global DB
    keep, DB = DB, str(db_path)
    try:
        return main(_count_only=True, _args=args)
    finally:
        DB = keep


def main(_count_only: bool = False, _args=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually insert the flags (default: print only)")
    ap.add_argument("--only", choices=("queued_before_home", "opinions"),
                    help="restrict to timing facts, or to the review set")
    ap.add_argument("--by", default="", help="who is recording these")
    ap.add_argument("--verify-idempotent", action="store_true",
                    help="copy the database, apply twice to the COPY, and "
                         "report what changed. Touches nothing real.")
    # `_args` is how the idempotency check re-enters without re-reading
    # sys.argv, which still carries --verify-idempotent and would
    # recurse forever.
    args = _args if _args is not None else ap.parse_args()
    if getattr(args, "verify_idempotent", False):
        return _verify_idempotent(args)

    from api.services import questionnaire_schema as qs
    from api.services.suggestion_review import split_destination
    from api.services import suggestion_flags as flags

    con = sqlite3.connect(DB if args.apply else f"file:{DB}?mode=ro", uri=not args.apply)
    con.row_factory = sqlite3.Row

    planned = []
    preexisting = []
    undefined = []
    seen = modern = 0
    for r in con.execute("""SELECT p.id, p.display_name n, ip.projection_json j
                            FROM interview_projections ip
                            JOIN people p ON p.id = ip.person_id
                            ORDER BY p.display_name"""):
        for s in (json.loads(r["j"] or "{}") or {}).get("pendingSuggestions") or []:
            if not isinstance(s, dict):
                continue
            seen += 1
            fp = str(s.get("fieldPath") or "")
            val = "" if s.get("value") is None else str(s.get("value"))
            sec, fld, _rep = split_destination(fp)

            reason = note = None
            for (p_path, frag), (rsn, nte) in PROPOSED.items():
                if fp == p_path and frag.lower() in val.lower():
                    reason, note = rsn, nte
                    break
            if reason is None and "destination_undefined" not in s \
                    and not qs.is_defined(sec, fld):
                # Legacy, and the questionnaire STILL has no such field
                # even after WO-04. Refused by `DestinationUndefined`
                # before either tier is consulted — a stronger refusal
                # than both, and one no flag can weaken. Listed so the
                # dry run accounts for every queued row rather than
                # dropping the ones it has nothing to say about.
                undefined.append((r["id"], r["n"], s, fp, val))
                continue
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
                    # Protected at the ACKNOWLEDGE level by a structural
                    # tier that needs no row here. Listed, not flagged —
                    # writing "queued before home" about a field that
                    # existed all along would still be a false record.
                    preexisting.append((r["id"], r["n"], s, fp, val))
                    continue
            if reason is None:
                # Proposed through the WO-03B route: `destination_undefined`
                # was written when it was queued, so the destination was
                # checked by the code that exists today. Ordinary.
                if "destination_undefined" in s:
                    modern += 1
                continue
            if args.only == "queued_before_home" and reason != "queued_before_home":
                continue
            if args.only == "opinions" and reason == "queued_before_home":
                continue
            planned.append((r["id"], r["n"], s, reason, note, fp, val))

    if _count_only:
        # The idempotency check's path: apply silently, report how many
        # were planned. Same `record_flag` calls, same transaction shape
        # as `--apply`, so what it proves is what `--apply` would do.
        con.execute("BEGIN IMMEDIATE")
        try:
            for pid, _n, s, reason, note, _fp, _val in planned:
                flags.record_flag(con, pid, s, reason, source_note=note or "",
                                  flagged_by=args.by)
            con.commit()
        except Exception:
            con.rollback()
            raise
        con.close()
        return len(planned)

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
        print(f"\n  {G}ALREADY PROTECTED — nothing is written for these "
              f"({len(preexisting)}):{X}\n")
        print("    Queued at destinations that ALREADY EXISTED, so `queued_before_home`")
        print("    would be a false record. They are covered anyway: every legacy")
        print("    proposal now requires an explicit acknowledgement before it can be")
        print("    accepted, derived from the proposal's own shape. No row here, and")
        print("    nothing asserted about the values — only that nobody has read them.\n")
        for _pid, n, _s, fp, val in preexisting:
            print(f"    [{n.split()[0]:<11}] {fp:<26} {val[:52]!r}")

    if undefined:
        print(f"\n  {G}NO SUCH FIELD — refused before any tier is consulted "
              f"({len(undefined)}):{X}\n")
        print("    Legacy, and the questionnaire still has no home for them even")
        print("    after WO-04. `DestinationUndefined` refuses these outright, which")
        print("    is stronger than either tier and cannot be cleared by a flag, an")
        print("    acknowledgement or a correction. Listed for the accounting.\n")
        for _pid, n, _s, fp, val in undefined:
            print(f"    [{n.split()[0]:<11}] {fp:<26} {val[:52]!r}")

    # Every queued row must appear in exactly one group. A script that
    # silently drops rows is how the eleven went unnoticed in the first
    # place, so the arithmetic is printed rather than trusted.
    accounted = len(planned) + len(preexisting) + len(undefined) + modern
    print(f"\n  {'-'*70}")
    print(f"  {len(planned):>3}  flags to record   ({len(planned) - len(opinions)} "
          f"timing facts, {len(opinions)} opinions)")
    print(f"  {len(preexisting):>3}  covered structurally — no row needed")
    print(f"  {len(undefined):>3}  no such field — refused outright")
    print(f"  {modern:>3}  modern: destination checked when it was queued")
    print(f"  {'-'*70}")
    if accounted == seen:
        print(f"  {G}{seen} queued, {seen} accounted for.{X} "
              f"{seen - modern} of them legacy, and every one of those now "
              f"requires\n      a deliberate act before it can become a family "
              f"record.\n")
    else:
        print(f"  {R}{seen - accounted} of {seen} queued suggestions fell into NO "
              f"group.{X}\n      That is a bug in this script, not a finding.\n")

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
