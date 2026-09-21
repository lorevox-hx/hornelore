"""Give the 29 pre-cutover queue entries a stable identity.

PRINTS BY DEFAULT. WRITES NOTHING WITHOUT --apply.

WHY THEY HAVE NO ID
-------------------
`suggestion_id` is minted in exactly one place — `append_suggestion_route`
in `routers/projection.py`:

    sid = "sg_" + uuid.uuid4().hex[:16]

That route is WO-03B, and it landed on 2026-09-20. Everything queued
before it was written by the client, which PUT the whole
`pendingSuggestions` array; identity was never part of the shape. All 29
survivors carry exactly five keys — fieldPath, value, confidence, turnId,
ts — and no id.

The consequence is not cosmetic. `find_suggestion` matches on

    s.get("suggestion_id") == suggestion_id

and the route's path parameter is always a non-empty string, so a
key-less entry can never match. `accept()` and `decline()` both raise
`SuggestionNotFound`. The thirty legacy proposals are not merely
unreviewed — they are UNREVIEWABLE. The expanded legacy guard is real,
but nothing can reach it, and nothing can decline them either.

WHAT THIS ASSIGNS, AND WHAT IT REFUSES TO TOUCH
------------------------------------------------
Added, only where the key is absent:

  suggestion_id           deterministic; see below
  turn_evidence           the MEASURED verdict of `verify_turn` on the
                          turn the entry already cites — not a guess
  destination_unresolved  true for a repeatable section

NEVER touched: fieldPath, value, confidence, turnId, ts, array order,
or any key already present.

NEVER ADDED: `destination_undefined`. This is the sharpest edge in the
whole operation. `suggestion_flags._is_unchecked_legacy` is

    return "destination_undefined" not in suggestion

and it is the sole basis of BOTH structural review tiers. Writing that
key onto these entries would silently remove the acknowledge/correct
requirement from all thirty and turn
`personal.fullName = "kind of scared"` back into a one-click write. The
operation asserts this rather than trusting itself: `_verify` re-reads
every entry afterwards and fails if the key appeared.

WHY `turn_evidence` IS SET RATHER THAN LEFT ABSENT
---------------------------------------------------
The review surface infers a badge when the key is missing:

    var ev = s.turn_evidence || (s.suggestion_id ? "absent" : "pre-cutover");

Today these rows read "older suggestion". The moment they have an id and
no `turn_evidence`, that same line reads "absent" — "No conversation was
cited. This is something Lori worked out." That is FALSE: all 29 cite a
turn. Giving them an id must not change what the archive claims about
where they came from.

So the verdict is measured with the same `verify_turn` the live route
uses. On this database all 29 come back `unverified` — they cite ids of
the form `turn-1777339141496`, client millisecond stamps, while real
turn ids are integers. The surface then says "could not confirm source
… treat as Lori's inference", which is the truthful reading and is the
amber badge rather than the muted one.

WHY `destination_unresolved` IS SET
------------------------------------
The surface compensates for missing ids when deciding to draw the entry
picker:

    var unresolved = !!s.destination_unresolved || (d.repeatable && !sid);

Giving a repeatable-section entry an id removes that compensation. The
picker would disappear, Accept would light up, the server would raise
`SuggestionUnresolved`, and the 422 lands in a branch whose message is
"Choose which entry this belongs to" — with no control to choose with.
Twelve of the 29 are in repeatable sections. They get the key
explicitly.

IDENTITY: DETERMINISTIC, AND UNIQUE BY CONSTRUCTION
-----------------------------------------------------
    sg_ + sha256(person_id | index | fieldPath | value | ts)[:16]

Same shape as the minted ids, so nothing downstream can tell them apart.

The INDEX is in the hash on purpose. There are no duplicate proposals in
this queue today — verified, no (narrator, fieldPath, value) repeats and
no narrator with the same fieldPath twice — but identity must not depend
on that staying true. Two byte-identical entries at different positions
are two proposals a person queued twice, and they must get two ids.
Hashing content alone would collapse them, and `_write_queue_without`
removes EVERY entry matching an id, so one decline would silently delete
both.

Re-running is safe because an entry that already has an id is skipped
entirely — idempotence comes from the skip, not from the derivation.

Collisions are not assumed away. Every proposed id is checked against
every other proposed id, every id already in any queue, and every id
recorded in `suggestion_reviews` and `suggestion_flags`. One collision
refuses the whole operation.

Usage, from WSL:

    python3 scripts/backfill_suggestion_ids.py
    python3 scripts/backfill_suggestion_ids.py --verify-on-copy
    python3 scripts/backfill_suggestion_ids.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))

DB = os.environ.get("HORNELORE_DB", "/mnt/c/hornelore_data/db/hornelore.sqlite3")
G, R, Y, X = "\033[32m", "\033[31m", "\033[33m", "\033[0m"

# The five keys a pre-cutover entry carries. Every one must survive the
# operation byte-identical; `_verify` proves it.
FOSSIL_KEYS = ("fieldPath", "value", "confidence", "turnId", "ts")

# Never written by this operation. See the module docstring.
FORBIDDEN = ("destination_undefined",)


def derive_id(person_id: str, index: int, entry: dict) -> str:
    """Stable, position-aware identity. See "IDENTITY" above."""
    raw = "\x1f".join((
        str(person_id), str(index),
        str(entry.get("fieldPath") or ""),
        "" if entry.get("value") is None else str(entry.get("value")),
        str(entry.get("ts") or ""),
    ))
    return "sg_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _plan(con):
    """What would change, without changing it."""
    from api.services.answer_provenance import verify_turn
    from api.services.suggestion_review import split_destination, REPEATABLE_SECTIONS

    plan, taken = [], set()

    # Every id already spoken for, anywhere.
    for r in con.execute("SELECT projection_json FROM interview_projections"):
        for s in (json.loads(r[0] or "{}") or {}).get("pendingSuggestions") or []:
            if isinstance(s, dict) and s.get("suggestion_id"):
                taken.add(s["suggestion_id"])
    for tbl in ("suggestion_reviews", "suggestion_flags"):
        try:
            for r in con.execute(
                    f"SELECT suggestion_id FROM {tbl} WHERE suggestion_id IS NOT NULL"):
                taken.add(r[0])
        except sqlite3.Error:
            pass

    proposed = {}
    for r in con.execute("""SELECT p.id pid, p.display_name n, ip.projection_json j,
                                   ip.version v
                            FROM interview_projections ip
                            JOIN people p ON p.id = ip.person_id
                            ORDER BY p.display_name"""):
        pending = (json.loads(r["j"] or "{}") or {}).get("pendingSuggestions") or []
        for i, s in enumerate(pending):
            if not isinstance(s, dict) or s.get("suggestion_id"):
                continue
            sid = derive_id(r["pid"], i, s)
            if sid in taken or sid in proposed:
                raise SystemExit(
                    f"{R}COLLISION{X}: {sid} is already in use. Nothing was "
                    f"written. This needs a person to look at it.")
            proposed[sid] = True

            sec, _fld, _rep = split_destination(str(s.get("fieldPath") or ""))
            adds = {"suggestion_id": sid}
            if "turn_evidence" not in s:
                adds["turn_evidence"] = verify_turn(con, r["pid"], s.get("turnId"))
            if "destination_unresolved" not in s and sec in REPEATABLE_SECTIONS:
                adds["destination_unresolved"] = True
            plan.append({"pid": r["pid"], "name": r["n"].split()[0], "index": i,
                         # The version the plan was computed against. Checked
                         # under the lock before anything is written.
                         "version": int(r["v"] or 0),
                         "entry": s, "adds": adds})
    return plan


def snapshot(src: Path, dest: Path) -> None:
    """A CONSISTENT copy, via SQLite's online backup API.

    `shutil.copy2` of the database plus its -wal and -shm was what this
    used, and an outside review was right about it:

        Those files can change between copies.

    The stack is running. Three separate file copies of a live WAL
    database can capture a torn state — a main file from one moment and
    a WAL from another — and a rehearsal against a torn copy proves
    nothing about the real thing. `Connection.backup()` holds a read
    transaction for the duration and produces a single consistent file,
    with no -wal to copy at all.
    """
    src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    dst_con = sqlite3.connect(dest)
    try:
        src_con.backup(dst_con)
    finally:
        dst_con.close()
        src_con.close()


def _apply(con, plan, source: str) -> None:
    """One transaction. Rewrites `pendingSuggestions` in place, preserving
    order and every existing key.

    `version` is bumped so a client holding the old version gets a
    conflict rather than quietly overwriting the new ids.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    by_person = {}
    for p in plan:
        by_person.setdefault(p["pid"], []).append(p)

    con.execute("BEGIN IMMEDIATE")
    try:
        for pid, items in by_person.items():
            row = con.execute(
                "SELECT projection_json, version FROM interview_projections "
                "WHERE person_id=?", (pid,)).fetchone()
            env = json.loads(row["projection_json"] or "{}") or {}
            pending = env.get("pendingSuggestions") or []
            # THE WHOLE ENTRY, AND THE VERSION. Not a sample of it.
            #
            # This compared id, fieldPath and ts only. Outside review:
            #
            #     A value or turn citation changed between planning and
            #     application could therefore receive metadata calculated
            #     for the earlier entry. The later verification could
            #     detect a mismatch after the transaction has committed.
            #
            # Correct, and the consequence is specific: `turn_evidence`
            # and `destination_unresolved` are computed from the entry
            # seen at PLAN time. If the value moved, those are answers to
            # a question about a different proposal, and the id — derived
            # from the value — would no longer match its own row.
            #
            # So the version is checked first (cheap, catches any change
            # at all) and then every key of every planned entry. Either
            # mismatch aborts the whole transaction before any write.
            if int(row["version"]) != items[0]["version"]:
                raise RuntimeError(
                    f"projection for {pid} moved from version "
                    f"{items[0]['version']} to {row['version']} between the "
                    f"plan and the lock — nothing written")
            for p in items:
                if p["index"] >= len(pending):
                    raise RuntimeError(
                        f"queue for {pid} shrank below index {p['index']} "
                        f"— nothing written")
                s = pending[p["index"]]
                if not isinstance(s, dict) or s.get("suggestion_id"):
                    raise RuntimeError(
                        f"entry {p['index']} for {pid} is no longer an "
                        f"un-identified proposal — nothing written")
                if json.dumps(s, sort_keys=True) != json.dumps(p["entry"], sort_keys=True):
                    raise RuntimeError(
                        f"entry {p['index']} for {pid} changed between the plan "
                        f"and the lock — nothing written")
                for k, v in p["adds"].items():
                    s[k] = v
            env["pendingSuggestions"] = pending
            con.execute(
                "UPDATE interview_projections SET projection_json=?, version=?, "
                "source=?, updated_at=? WHERE person_id=?",
                (json.dumps(env, ensure_ascii=False), int(row["version"]) + 1,
                 source, now, pid))
        con.commit()
    except Exception:
        con.rollback()
        raise


def _verify(con, plan) -> bool:
    """Re-read and prove the four promises."""
    ok = True
    byid = {}
    for r in con.execute("SELECT person_id, projection_json FROM interview_projections"):
        for i, s in enumerate((json.loads(r[1] or "{}") or {}).get("pendingSuggestions") or []):
            if isinstance(s, dict):
                byid[(r[0], i)] = s

    missing = forbidden = mutated = 0
    for p in plan:
        s = byid.get((p["pid"], p["index"]))
        if s is None or s.get("suggestion_id") != p["adds"]["suggestion_id"]:
            missing += 1
            continue
        for k in FORBIDDEN:
            if k in s:
                forbidden += 1
        for k in FOSSIL_KEYS:
            if s.get(k) != p["entry"].get(k):
                mutated += 1

    def say(good, msg):
        nonlocal ok
        if not good:
            ok = False
        print(f"  {G}PASS{X}  {msg}" if good else f"  {R}FAIL{X}  {msg}")

    say(missing == 0, f"every planned entry carries its id ({len(plan)} of {len(plan)})")
    say(forbidden == 0, "destination_undefined was NOT written — the legacy guard stands")
    say(mutated == 0, "fieldPath / value / confidence / turnId / ts unchanged on every entry")

    ids = [s.get("suggestion_id") for s in byid.values() if s.get("suggestion_id")]
    say(len(ids) == len(set(ids)), f"every id in every queue is unique ({len(ids)} ids)")
    return ok


def _fingerprint(con) -> dict:
    """Everything this operation must not touch."""
    out = {}
    for name, sql in (
        ("answers", "SELECT person_id, questionnaire_json, revision FROM "
                    "bio_builder_questionnaires ORDER BY person_id"),
        ("provenance", "SELECT * FROM bio_builder_answer_provenance "
                       "ORDER BY person_id, section, entry_id, field"),
        ("reviews", "SELECT * FROM suggestion_reviews "
                    "ORDER BY person_id, section, entry_id, field, value_hash"),
        ("flags", "SELECT * FROM suggestion_flags "
                  "ORDER BY person_id, section, field, value_hash"),
    ):
        h = hashlib.sha256()
        try:
            for row in con.execute(sql):
                h.update(repr(tuple(row)).encode("utf-8"))
        except sqlite3.Error as e:
            out[name] = f"unreadable: {e}"
            continue
        out[name] = h.hexdigest()[:16]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: print only)")
    ap.add_argument("--verify-on-copy", action="store_true",
                    help="copy the database, apply TWICE to the copy, verify. "
                         "Touches nothing real.")
    ap.add_argument("--db", default=None, help="override the database path")
    ap.add_argument("--source", default="suggestion_id_backfill")
    args = ap.parse_args()

    global DB
    if args.db:
        DB = args.db
    if args.verify_on_copy:
        return _verify_on_copy(args)

    con = sqlite3.connect(DB if args.apply else f"file:{DB}?mode=ro", uri=not args.apply)
    con.row_factory = sqlite3.Row
    plan = _plan(con)

    print(f"\n{'='*74}\n  Pre-cutover suggestion identity\n{'='*74}\n")
    if not plan:
        print("  Every queued suggestion already has an id. Nothing to do.\n")
        con.close()
        return 0

    print(f"  {len(plan)} entries would be given a stable id.\n")
    print(f"  {'narrator':<12} {'#':>2}  {'fieldPath':<28} {'new id':<20} also adds")
    print("  " + "-"*94)
    for p in plan:
        extra = ", ".join(f"{k}={v!r}" for k, v in p["adds"].items() if k != "suggestion_id")
        print(f"  {p['name']:<12} {p['index']:>2}  "
              f"{str(p['entry'].get('fieldPath'))[:27]:<28} "
              f"{p['adds']['suggestion_id']:<20} {extra}")

    print(f"\n  Preserved untouched on every entry: {', '.join(FOSSIL_KEYS)}, and array order.")
    print(f"  {Y}Never written: {', '.join(FORBIDDEN)}{X} — it is the basis of the "
          f"legacy guard.\n")

    if not args.apply:
        print(f"  {Y}Nothing was written.{X}")
        print("    --verify-on-copy   rehearse on a copy and check the promises")
        print("    --apply            write to the database above\n")
        con.close()
        return 0

    before = _fingerprint(con)
    _apply(con, plan, args.source)
    ok = _verify(con, plan)
    after = _fingerprint(con)
    for k in before:
        same = before[k] == after[k]
        if not same:
            ok = False
        print(f"  {G}PASS{X}  {k:<11} untouched" if same
              else f"  {R}FAIL{X}  {k:<11} CHANGED {before[k]} -> {after[k]}")
    con.close()
    print(f"\n  {G if ok else R}{'Done.' if ok else 'PROBLEM — read the failures above.'}{X}\n")
    return 0 if ok else 1


def _verify_on_copy(args) -> int:
    import shutil
    import tempfile
    src = Path(DB)
    if not src.exists():
        print(f"{R}  No database at {DB}{X}")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="idbackfill_")) / "copy.sqlite3"
    snapshot(src, tmp)

    print(f"\n{'='*74}\n  REHEARSAL — on a copy, at {tmp}\n{'='*74}\n")
    con = sqlite3.connect(tmp)
    con.row_factory = sqlite3.Row
    before = _fingerprint(con)
    plan = _plan(con)
    print(f"  run 1: {len(plan)} entries to identify")
    _apply(con, plan, args.source)
    ok = _verify(con, plan)

    plan2 = _plan(con)
    print(f"\n  run 2: {len(plan2)} entries to identify "
          f"{'(nothing left — idempotent)' if not plan2 else ''}")
    if plan2:
        ok = False
        print(f"  {R}FAIL{X}  a second run still finds work — not idempotent")
    else:
        print(f"  {G}PASS{X}  re-running is a no-op")

    after = _fingerprint(con)
    for k in before:
        same = before[k] == after[k]
        if not same:
            ok = False
        print(f"  {G}PASS{X}  {k:<11} untouched  ({before[k]})" if same
              else f"  {R}FAIL{X}  {k:<11} CHANGED  {before[k]} -> {after[k]}")
    con.close()
    print(f"\n  The real database was opened read-only and never written.")
    print(f"  {G if ok else R}{'Rehearsal clean.' if ok else 'Rehearsal FAILED.'}{X}\n")
    shutil.rmtree(tmp.parent, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
