#!/usr/bin/env python3
"""WO-02 acceptance check (read-only).

    ./scripts/wo02_acceptance.py capture         # before Stage A
    ./scripts/wo02_acceptance.py checkpoint      # after Stage A, before Stage B
    ./scripts/wo02_acceptance.py verify          # after Stage B + restart
    ./scripts/wo02_acceptance.py plan            # what Stage B should do (read-only)
    ./scripts/wo02_acceptance.py restore-verify  # after restoring to Day 1

The execution plan (docs/wo/HORNELORE_CORRECTED_EXECUTION_PLAN_2026-08-01.md)
requires all four. Until 2026-08-12 only `capture` and `verify` existed, so
the prescribed acceptance could not be completed and Gate 3 could not
receive a truthful verdict. Unknown modes have always been rejected with
exit 2 -- they were never silently treated as `verify`.

Each mode measures against the state the PREVIOUS one wrote:

    capture  -> baseline        (WO-02_ACCEPTANCE_state.json)
    checkpoint -> Stage A held, and writes the Stage B baseline
                                (WO-02_ACCEPTANCE_checkpoint.json)
    verify   -> Stage B held against checkpoint, and everything survived
                the restart

STAGE A'S RESULTS ARE DERIVED, NOT RE-PERFORMED (2026-08-13).
`verify` reads BOTH state files and works out what Stage A did by
comparing them: the day-text fields it changed, the notes it edited, the
notes it created, the captions it rewrote, and the placements it
destroyed and kept. It then asserts each of those results still exists
exactly once and still holds its checkpoint value.

That is persistence. The previous version diffed the checkpoint against
NOW and called any difference "edits survived the restart", which is
change, and which graded backwards in both directions: an operator who
restarted and correctly touched nothing was told the steps were not
done, while one who edited something unrelated afterwards was told they
had passed. It also under-reported -- the live 2026-08-13 run announced
only `Stage A edits landed (note)` although day text and a caption had
also been edited, because a day-text field that was EMPTY at capture is
a new row rather than a changed one, and because a caption edited before
the photograph was removed from that day leaves no row on that day to
carry the new hash. Captions are therefore read from the LINK.

The practical consequence: a checkpoint already written needs no rerun,
and `verify` requires no second edit and no second quick note.
    restore-verify -> the restore put the ORIGINAL rows back, created no
                duplicates, and undid nothing it should not have

PHOTOGRAPHS ARE ON A SET OF DAYS, NOT ON A DAY (2026-08-13).
WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 gave placements their own table, so
one photograph may sit on several days of a trip. Every photo assertion
here compares SETS. The snapshot field is `days: [...]`, sorted so two
runs of the same state are byte-identical, with `pids` carrying the
placement id per day for the occasions when a single occurrence has to
be named.

That changed three questions, not just their spelling:

  * "was it removed from a day" is `the set shrank`, not `the scalar
    became null`. The old test could not see two days becoming one, and
    it fired FALSELY on a photograph that gained a second day, because
    the server derives that scalar and returns null once there are
    several.
  * "is it back where it was" is set equality. Comparing one scalar to
    another would fail a photograph correctly restored to Day 1 while
    still on Day 3, and pass one restored to the wrong one of its two.
  * "was it moved" is now three separate walkthrough operations —
    **Add to this day**, **Remove from this day**, and **Move**, which
    names the day it moves from. A set that grew is an Add; one that
    shrank is a Remove; one that changed without changing size is a
    Move. Reporting all three as "moved" would let a walkthrough that
    added a day read as a successful move.

A state file captured before that date carries the old scalar `day`. It
is still readable — see `days_of()` — and every mode that loads one says
out loud that it is HISTORICAL evidence about the single-day product,
not current acceptance evidence.

OPERATOR ATTESTATIONS. Two acceptance requirements are browser-only and a
read-only API snapshot cannot observe them: the dirty-navigation guard
appearing and preserving unsaved typing, and the modal retaining a usable
selected-day state across close/reopen. Record them explicitly:

    ./scripts/wo02_acceptance.py checkpoint --attest dirty-guard
    ./scripts/wo02_acceptance.py verify --attest modal-reopen

They are reported as ATTEST, never as PASS, and are counted separately.
An attestation is the operator's word, not machine evidence, and the
readout says so. Gate 3 is not complete without both.

Reads the API only. Never edits data. Never starts, stops or restarts
any service -- the operator owns the stack.

Auto-writes its readout to
    docs/reports/WO-02_ACCEPTANCE_<mode>.console.txt
next to the other console readouts, so nothing has to be copied out of
the terminal (no shell `| tee` -- that silently produces 0-byte files
under WSL pipe buffering).

Prints no narrative text. Transcripts, captions and notes are compared
as short hashes, so no trip content lands in the terminal or the file.
"""

import hashlib
import json
import os
import sys

import requests

API = "http://127.0.0.1:8000"
TRIP = "9538cd88-5c8b-4da4-b2a9-2a03f8db32a3"
REPO = "/mnt/c/Users/chris/hornelore"
STATE = os.path.join(REPO, "docs/reports/WO-02_ACCEPTANCE_state.json")
STATE_CP = os.path.join(REPO, "docs/reports/WO-02_ACCEPTANCE_checkpoint.json")
CONSOLE = os.path.join(REPO, "docs/reports/WO-02_ACCEPTANCE_%s.console.txt")

# The two browser-only requirements. Keys are what the operator passes to
# --attest; the text is what the readout records on their behalf.
ATTESTABLE = {
    "dirty-guard": ("the dirty-navigation guard appeared and the unsaved "
                    "typing was preserved"),
    "modal-reopen": ("closing and reopening the modal left a usable "
                     "selected-day state"),
}

LINES = []
PASS = [0]
FAIL = [0]
SKIP = [0]
ATTEST = [0]


def _reset():
    """Clear module counters. Only the tests call this — one process runs
    exactly one mode in real use."""
    del LINES[:]
    PASS[0] = FAIL[0] = SKIP[0] = ATTEST[0] = 0


def out(msg=""):
    print(msg)
    LINES.append(msg)


def flush(mode):
    path = CONSOLE % mode
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(LINES) + "\n")
    print("")
    print("console readout: %s" % path)


def check(ok, msg):
    """A real assertion: the behaviour was exercised and must hold."""
    if ok:
        PASS[0] += 1
        out("PASS  " + msg)
    else:
        FAIL[0] += 1
        out("FAIL  " + msg)


def skip(msg, step=None, environmental=False):
    """The operator did not exercise this step. Not a defect.

    ADDED 2026-08-13, `step` and `environmental`. A SKIP is the harness
    saying *you did not do this*, and that is only fair when the
    walkthrough asked for it. Two of them — moving a conversation and
    adding a Stage B quick note — were being reported against
    instructions that had stopped mentioning either, so following the
    printed walkthrough exactly could not reach PASS.

    Every skip waiting on a STAGE B action therefore names the
    walkthrough step it wants. `environmental=True` means the skip is
    not a Stage B step — either a fact about the environment (no
    checkpoint, no count lane served) or a different stage's business
    (Stage A's own edits, an attestation).
    `WalkthroughCoversEverySkipTest` walks this module's AST and fails
    the build on a skip that does neither, which is what stops the
    instructions and the checks drifting apart again.
    """
    if step is None and not environmental:
        raise AssertionError(
            "skip() must name a walkthrough step or declare itself "
            "environmental: %r" % msg)
    if step is not None and step not in STAGE_B_STEP_KEYS:
        raise AssertionError("unknown walkthrough step %r" % step)
    SKIP[0] += 1
    out("SKIP  " + msg)


def attest(msg):
    """The operator's word for something the API cannot see.

    Deliberately NOT counted as a PASS. A snapshot cannot observe a
    dirty-navigation guard or a modal's selected-day state, and printing
    an operator claim as machine evidence is how a harness starts lying.
    """
    ATTEST[0] += 1
    out("ATTEST " + msg + "  [operator-attested, not machine-verified]")


def record_attestations(state, attests, mode, now_iso):
    """Fold --attest keys into the state file so later modes can see them."""
    book = dict(state.get("attestations") or {})
    for key in attests:
        book[key] = {"mode": mode, "at": now_iso}
        attest(ATTESTABLE[key])
    state["attestations"] = book
    return book


def get(path):
    r = requests.get(API + path, timeout=30)
    r.raise_for_status()
    return r.json()


def h(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


def snapshot():
    cal = get("/api/trips/%s/calendar" % TRIP)
    snap = {"days": [], "counts": {}, "photo_links": {}, "turns": {},
            "items": {}}

    for d in cal.get("days") or []:
        did = d.get("id")
        snap["days"].append({"id": did,
                             "n": d.get("day_index"),
                             "date": d.get("date")})
        snap["counts"][did] = dict(
            (k, v) for k, v in d.items() if str(k).endswith("_count"))

        tl = get("/api/trips/%s/days/%s/timeline" % (TRIP, did))
        rows = []
        for it in tl.get("items") or []:
            kind = it.get("kind")
            if kind == "photo":
                # The PLACEMENT id joins the row, beside the link id it
                # shares with every other occurrence of the same
                # photograph. Without it a day's timeline row for a
                # photograph on three days is indistinguishable from
                # the other two, and "this occurrence moved" cannot be
                # said at all.
                rows.append(["photo", it.get("link_id"),
                             it.get("placement_id"), h(it.get("caption"))])
            elif kind == "note":
                rows.append(["note", it.get("note_id"),
                             h(it.get("title")) + h(it.get("text"))])
            elif kind == "source":
                rows.append(["source", it.get("source_id"),
                             h(it.get("title")) + h(it.get("summary"))])
            elif kind == "day_text":
                rows.append(["day_text", it.get("id"), h(it.get("text"))])
            elif kind == "conversation":
                lid = it.get("link_id")
                rows.append(["conversation", lid, ""])
                snap["turns"][str(lid)] = {
                    "day": did,
                    "u": it.get("user_turn_row_id"),
                    "a": it.get("assistant_turn_row_id"),
                    "nh": h(it.get("narrator_said")),
                    "lh": h(it.get("lori_said")),
                    "src": it.get("placement_source"),
                    "st": it.get("placement_status"),
                }
        snap["items"][did] = rows

    pl = get("/api/trips/%s/photo-links?include_hidden=1" % TRIP)
    for link in pl.get("photo_links") or []:
        snap["photo_links"][str(link.get("id"))] = {
            # ── `days`, not `day` (2026-08-13) ────────────────────────
            #
            # This field was the scalar `link.get("trip_day_id")`. Under
            # WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 the server DERIVES
            # that scalar and returns null when a photograph is on
            # SEVERAL days, so a snapshot built from it would record the
            # most deliberately placed photographs in the trip as being
            # on no day at all — and `restore-verify` would then
            # "confirm" that state had been restored.
            #
            # SORTED, so a snapshot is comparable: the set is the fact,
            # its order is not. Two runs that placed the same photograph
            # on the same two days must produce byte-identical state
            # files or the whole capture/verify model stops working.
            "days": sorted(str(d) for d in (link.get("trip_day_ids") or [])),
            # Placement ids, keyed by day, so a REMOVED occurrence can
            # be named. Recorded alongside rather than instead of
            # `days`: ids are stable within a run and meaningless
            # across a restore, while the day set is the thing the
            # operator would recognise.
            "pids": dict(
                (str(p.get("trip_day_id")), str(p.get("id")))
                for p in (link.get("day_placements") or [])
                if p.get("trip_day_id")),
            "ch": h(link.get("caption")),
            "approved": int(link.get("caption_approved_for_lori") or 0),
        }
    return snap


def days_of(entry):
    """The day set of a photo-link snapshot entry, tolerating the OLD
    scalar shape.

    A state file captured before 2026-08-13 carries `day`, not `days`.
    Rather than refuse it — which would throw away a genuine
    pre-migration capture an operator may still want to compare against
    — it is read as the one-day set it was. `do_verify` says out loud
    that such a file is historical; see `_snapshot_is_legacy`.
    """
    if "days" in entry:
        return sorted(str(d) for d in (entry.get("days") or []))
    legacy = entry.get("day")
    return [str(legacy)] if legacy else []


def pids_of(entry):
    """{day_id: placement_id} for a photo-link snapshot entry.

    Empty for a pre-2026-08-13 snapshot, which carried no placement ids
    at all. Callers therefore treat a missing id as "cannot tell" rather
    than as "changed" — a historical baseline must not manufacture
    failures about a field it never recorded.
    """
    return dict(entry.get("pids") or {})


def is_set_format(entry):
    """True for a snapshot entry written on or after 2026-08-13.

    The presence of `days` is what distinguishes a CURRENT entry from a
    historical scalar one, and the distinction decides whether a missing
    placement id is unknowable or malformed.
    """
    return isinstance(entry, dict) and "days" in entry


def missing_pids(entry):
    """Days a CURRENT entry lists without a placement id.

    CORRECTED 2026-08-13 after review. The id checks used to skip any
    day whose id was absent on either side, on the reasoning that the
    pre-migration state files record no ids at all. That exemption was
    right for HISTORICAL entries and wrong for current ones: a
    set-format entry claiming a photograph is on `d1` while recording no
    placement row for `d1` is malformed, and silently passing it is how
    a snapshot that lost its ids reports success.

    Historical entries are exempt here and warned about once, by
    warn_if_legacy, rather than producing a failure per day.
    """
    if not is_set_format(entry):
        return []
    pids = pids_of(entry)
    return [d for d in (entry.get("days") or []) if not pids.get(d)]


def duplicate_pids(entry):
    """One placement id claimed by two different days.

    Impossible in the database — a placement row has one day — so seeing
    it in a snapshot means the reader collapsed two rows into one, and
    every per-day identity check downstream is then comparing a value
    that does not mean what it says.
    """
    if not is_set_format(entry):
        return []
    seen, dup = {}, []
    for d, pid in sorted(pids_of(entry).items()):
        if not pid:
            continue
        if pid in seen:
            dup.append((seen[pid], d, pid))
        else:
            seen[pid] = d
    return dup


def rekeyed_days(before, after, days):
    """Days present in BOTH snapshots whose placement id changed or went.

    ADDED 2026-08-13 after review. The set assertions compare day NAMES,
    which cannot tell "this placement was preserved" from "this
    placement was destroyed and an identical-looking one was created in
    its place". Broken code that deleted every placement on a link and
    re-created the survivors would satisfy every day-set check in this
    file while having preserved nothing — and the operator's ordering,
    and anything later keyed on a placement id, would be silently gone.

    TIGHTENED the same day, after a second review. This read

        if b.get(d) and a.get(d) and b[d] != a[d]

    which passes silently when EITHER id disappears — so a surviving day
    that lost its placement row read as "preserved". The comparison is
    now direct, so `id -> None` is a change like any other. The
    historical exemption is applied by format rather than by
    truthiness: it holds only when a side is not in set format.
    """
    bad = []
    if not (is_set_format(before) and is_set_format(after)):
        return bad          # historical: identity was never recorded
    b, a = pids_of(before), pids_of(after)
    for d in days:
        if b.get(d) != a.get(d):
            bad.append((d, b.get(d) or "(none)", a.get(d) or "(none)"))
    return bad


def _rows_by_identity(snap):
    """{(day, kind, id): hash} for every timeline row in a snapshot.

    The hash is the LAST element, which is the one thing every row shape
    has in common: a photo row is
    ``[kind, link_id, placement_id, hash]`` and the others are
    ``[kind, id, hash]``.
    """
    out = {}
    for did, rows in (snap.get("items") or {}).items():
        for r in rows:
            if len(r) < 3:
                continue
            out[(str(did), str(r[0]), str(r[1]))] = r[-1]
    return out


def stage_a_changeset(base, cp):
    """Exactly what Stage A did, DERIVED from the two whole snapshots.

    ADDED 2026-08-13. `verify` used to look for a difference between the
    checkpoint and now, and call any difference "edits survived the
    restart". That is not persistence — it is change. An operator who
    restarted the stack and changed nothing (which is what the
    walkthrough asks for) got SKIP; an operator who edited something
    unrelated got PASS. The instrument rewarded the wrong behaviour in
    both directions.

    Persistence is: the values Stage A produced are STILL THERE and
    STILL THE SAME. That needs the Stage A change set, and deriving it
    from `capture` versus `checkpoint` means the checkpoint already
    written on 2026-08-13 — 10 PASS, 0 FAIL, 1 ATTEST — remains usable
    without a rerun. No new metadata is required of it.

    The live run also showed WHY row-diffing alone was not enough. It
    reported only `Stage A edits landed (note)` although day text and a
    photo caption had also been edited:

      * the Afternoon field was EMPTY at capture, so no `day_text` row
        existed to compare against — it is a NEW row, not a changed one;
      * the caption edit was followed by Remove from this day, so by
        checkpoint time the photo row was gone from that day's timeline
        entirely. A caption lives on the LINK, and that is where it has
        to be read.
    """
    b, c = _rows_by_identity(base), _rows_by_identity(cp)
    out = {"day_text": [], "notes": [], "new_notes": [], "captions": [],
           "removed_placements": [], "surviving_placements": []}

    for key, hsh in sorted(c.items()):
        did, kind, ident = key
        if kind == "day_text":
            if b.get(key) != hsh:
                out["day_text"].append({"day": did, "id": ident, "h": hsh})
        elif kind == "note":
            if key not in b:
                out["new_notes"].append({"day": did, "id": ident, "h": hsh})
            elif b[key] != hsh:
                out["notes"].append({"day": did, "id": ident, "h": hsh})

    base_links = base.get("photo_links") or {}
    for lid, v in sorted((cp.get("photo_links") or {}).items()):
        was = base_links.get(lid)
        if was is not None and was.get("ch") != v.get("ch"):
            out["captions"].append({"link": lid, "ch": v.get("ch"),
                                    "approved": v.get("approved")})
        b_pids, c_pids = pids_of(was or {}), pids_of(v)
        for d, pid in sorted(b_pids.items()):
            if d not in c_pids:
                out["removed_placements"].append(
                    {"link": lid, "day": d, "pid": pid})
        for d, pid in sorted(c_pids.items()):
            out["surviving_placements"].append(
                {"link": lid, "day": d, "pid": pid})
    return out


_COUNT_LANES = (("conversation", "conversation_count"),
                ("photo", "photo_count"),
                ("note", "note_count"),
                ("source", "source_count"))


def check_count_contract(snap, label):
    """The calendar's counts against the timeline rows they describe.

    CORRECTED 2026-08-13. The old check asked only whether the count
    dictionary had CHANGED, which cannot tell a count that followed the
    content from one that drifted away from it — a rail reporting three
    photographs on a day holding one is "changed" and wrong.

    The contract, per day:

        conversation_count == conversation rows
        photo_count        == photo rows (explicit placements)
        note_count         == note rows
        source_count       == source rows
        item_count         == the sum of those four

    ``day_text`` rows are DELIBERATELY outside item_count — the day's
    own typed fields are the day, not things attached to it — so the
    last assertion is written as `rows minus day_text`, which states the
    exclusion rather than assuming it.
    """
    for d in snap.get("days") or []:
        did = str(d.get("id"))
        rows = (snap.get("items") or {}).get(did) or []
        kinds = {}
        for r in rows:
            kinds[str(r[0])] = kinds.get(str(r[0]), 0) + 1
        counts = (snap.get("counts") or {}).get(did) or {}
        # A day whose count block carries none of the lanes this contract
        # knows is UNVERIFIED, and must say so. Asserting only the keys
        # that happen to be present means an unrecognised block passes
        # every check by having nothing to check -- which is how the old
        # synthetic `row_count` fixture kept the rail assertions green
        # for months without ever exercising them.
        known = [k for _kind, k in _COUNT_LANES] + ["item_count"]
        if not any(k in counts for k in known):
            skip("day %s served no recognised count lane (%s) -- its rail "
                 "arithmetic was not checked"
                 % (did[:8], ", ".join(sorted(counts)) or "empty"),
                 environmental=True)
            continue
        for kind, key in _COUNT_LANES:
            if key not in counts:
                continue
            check(int(counts[key] or 0) == kinds.get(kind, 0),
                  "%s day %s: %s (%s) matches its %s row(s) (%d)"
                  % (label, did[:8], key, counts[key], kind,
                     kinds.get(kind, 0)))
        if "item_count" in counts:
            component_sum = sum(int(counts.get(k, 0) or 0)
                                for _kind, k in _COUNT_LANES)
            check(int(counts["item_count"] or 0) == component_sum,
                  "%s day %s: item_count (%s) is the sum of its four lanes "
                  "(%d)" % (label, did[:8], counts["item_count"],
                            component_sum))
            without_day_text = len(rows) - kinds.get("day_text", 0)
            check(int(counts["item_count"] or 0) == without_day_text,
                  "%s day %s: item_count excludes the %d day_text row(s) "
                  "(%s vs %d rows)"
                  % (label, did[:8], kinds.get("day_text", 0),
                     counts["item_count"], len(rows)))


def photo_count_of(snap, day_id):
    counts = (snap.get("counts") or {}).get(str(day_id)) or {}
    if "photo_count" not in counts:
        return None
    return int(counts["photo_count"] or 0)


def id_health(entry, label):
    """Malformed-id problems on one entry, as readable strings."""
    problems = ["%s lists day %s with no placement id" % (label, d)
                for d in missing_pids(entry)]
    problems += ["%s gives days %s and %s the same placement id %s"
                 % (label, x, y, pid) for x, y, pid in duplicate_pids(entry)]
    return problems


def _snapshot_is_legacy(snap):
    """True when the state file predates set semantics."""
    for entry in (snap.get("photo_links") or {}).values():
        if "days" not in entry:
            return True
    return False



def warn_if_legacy(old, mode):
    """Say out loud when the baseline predates set semantics.

    Requirement 9 of Phase 4: pre-migration scalar capture evidence is
    HISTORICAL, not current acceptance evidence. It is still read —
    throwing it away would destroy a real capture somebody took — but a
    run that silently compared today's multi-day product against a
    single-day baseline would produce a verdict about a product that no
    longer exists, and print it in the same format as a real one.
    """
    if not _snapshot_is_legacy(old):
        return False
    out("HISTORICAL BASELINE. This state file was captured before "
        "2026-08-13 and")
    out("records one day per photograph (`day`), not the placement set "
        "(`days`).")
    out("It is read as a one-day set so the comparison can run, but this "
        "%s is" % mode)
    out("evidence about the SINGLE-DAY product. Re-run 'capture' for "
        "current acceptance.")
    out("")
    return True


def do_capture(now):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(now, fh, indent=1)

    out("=== WO-02 BASELINE ===")
    out("")
    busiest, busiest_n = None, -1
    for d in now["days"]:
        kinds = {}
        for row in now["items"][d["id"]]:
            kinds[row[0]] = kinds.get(row[0], 0) + 1
        total = sum(kinds.values())
        if total > busiest_n:
            busiest, busiest_n = d, total
        detail = ", ".join("%s x%d" % (k, v) for k, v in sorted(kinds.items()))
        out("Day %-3s %-12s %s" % (d["n"], d["date"], detail or "empty"))

    approved = sum(1 for v in now["photo_links"].values() if v["approved"])
    out("")
    out("photo links: %d    conversations: %d    approved captions: %d"
        % (len(now["photo_links"]), len(now["turns"]), approved))
    if busiest:
        out("")
        out(">>> Do the walkthrough on Day %s (%s) -- %d rows."
            % (busiest["n"], busiest["date"], busiest_n))
    out("")
    out("baseline state: %s" % STATE)
    return 0


def _verdict(pass_label):
    out("")
    out("=== %d passed, %d failed, %d not exercised, %d attested ==="
        % (PASS[0], FAIL[0], SKIP[0], ATTEST[0]))
    if FAIL[0]:
        out("RESULT: FAIL -- a check that was exercised did not hold.")
        return 1
    if SKIP[0]:
        out("RESULT: INCOMPLETE -- nothing is broken, but the steps above")
        out("        were not performed, so those behaviours are still")
        out("        unproven. Redo that part of the walkthrough and re-run.")
        return 0
    out("RESULT: " + pass_label)
    return 0


def do_checkpoint(now, attests, now_iso):
    """After Stage A, before Stage B.

    Two jobs, and they are separate on purpose: prove what Stage A was
    supposed to do, and write the baseline Stage B will be measured
    against. Without this second baseline, `verify` cannot tell a Stage B
    move from a Stage A one — which is why the plan asks for four modes
    and not two.
    """
    if not os.path.exists(STATE):
        out("No baseline at %s -- run 'capture' first." % STATE)
        return 2
    with open(STATE, encoding="utf-8") as fh:
        old = json.load(fh)

    out("=== WO-02 CHECKPOINT (Stage A) ===")
    out("")
    warn_if_legacy(old, "checkpoint")

    # Stage A must not have touched a transcript.
    for lid, was in old["turns"].items():
        cur = now["turns"].get(lid)
        if not cur:
            check(False, "conversation %s vanished during Stage A" % lid[:8])
            continue
        check(cur["nh"] == was["nh"] and cur["lh"] == was["lh"],
              "conversation %s transcript byte-identical" % lid[:8])

    # An edit must never grant Lori approval.
    gained = [k for k, v in now["photo_links"].items()
              if v["approved"]
              and not old["photo_links"].get(k, {}).get("approved", 0)]
    check(not gained,
          "no caption edit granted Lori approval (n=%d)" % len(gained))

    # ── Remove from THIS day takes one occurrence ─────────────────────
    #
    # This asked whether the scalar had become null: `v["day"] is None
    # and old day is not None`. Under set semantics that is the wrong
    # question twice over. It cannot see a photograph going from two
    # days to one — the interesting case, and the one the operator is
    # most likely to get wrong — and it FIRES SPURIOUSLY on a
    # photograph that gained a second day, because the derived scalar
    # goes from a day to null when the set grows past one.
    #
    # The question now is whether the day SET shrank, and the assertion
    # is that everything else survived: the other placements, the trip
    # link, and the count of links.
    shrunk, grew = [], []
    for k, v in now["photo_links"].items():
        before = days_of(old["photo_links"].get(k) or {})
        after = days_of(v)
        if len(after) < len(before):
            shrunk.append((k, before, after))
        elif len(after) > len(before):
            grew.append((k, before, after))
    vanished = [k for k in old["photo_links"] if k not in now["photo_links"]]
    check(not vanished,
          "no photo link disappeared during Stage A (n=%d)" % len(vanished))
    if not shrunk:
        skip("no photo was removed from a day -- Stage A step not done",
              environmental=True)
    else:
        check(len(now["photo_links"]) == len(old["photo_links"]),
              "removing a photo from a day created no second link (%d -> %d)"
              % (len(old["photo_links"]), len(now["photo_links"])))
        # THE PROPERTY THAT MATTERS UNDER MANY-TO-MANY: removing one
        # occurrence must leave every other one alone. Under the old
        # scalar this could not even be expressed — there was only ever
        # one placement to lose.
        for k, before, after in shrunk:
            lost = [d for d in before if d not in after]
            kept = [d for d in before if d in after]
            # Worded to be TRUE ON BOTH BRANCHES. check() prints one
            # message whatever the outcome, and this read "lost exactly
            # one day, not 1" on the passing branch -- a sentence that
            # contradicts itself and its own data. State the
            # measurement, then the expectation.
            check(len(lost) == 1,
                  "photo %s lost %d day(s); exactly one was expected "
                  "(%s -> %s)" % (k[:8], len(lost), before, after))
            check(sorted(after) == sorted(kept),
                  "photo %s kept every other placement (%s)" % (k[:8], kept))
            for problem in (id_health(old["photo_links"].get(k) or {},
                                      "photo %s before" % k[:8])
                            + id_health(now["photo_links"][k],
                                        "photo %s after" % k[:8])):
                check(False, problem)
            # IDENTITY, not just the day name. Without this, code that
            # deleted every placement and re-created the survivors would
            # pass the line above having preserved nothing.
            rekeyed = rekeyed_days(old["photo_links"].get(k) or {},
                                   now["photo_links"][k], kept)
            check(not rekeyed,
                  "photo %s kept the SAME placement row on each surviving "
                  "day (%d rewritten)" % (k[:8], len(rekeyed)))
            # And the day that went really went: its id is gone.
            gone = pids_of(old["photo_links"].get(k) or {})
            still = pids_of(now["photo_links"][k])
            for d in lost:
                if gone.get(d):
                    check(gone[d] not in still.values(),
                          "photo %s: the removed day's placement row is "
                          "gone, not re-pointed" % k[:8])
        out("      (removed from a day: %s)"
            % ", ".join("%s %s->%s" % (k[:8], b, a) for k, b, a in shrunk))
    if grew:
        out("      (also gained a day, which is Add and not a defect: %s)"
            % ", ".join("%s %s->%s" % (k[:8], b, a) for k, b, a in grew))

    # Edited rows / added note — the identities Stage B and the restore
    # will be measured against.
    edited, new_notes = [], []
    for did, rows in now["items"].items():
        was = dict((tuple(r[:2]), tuple(r))
                   for r in [tuple(x) for x in old["items"].get(did, [])])
        old_ids = set(tuple(x[:2]) for x in old["items"].get(did, []))
        for r in rows:
            key = tuple(r[:2])
            if key in was and tuple(r) != was[key]:
                edited.append(r[0])
            if r[0] == "note" and key not in old_ids:
                new_notes.append(r[1])
    if not edited:
        skip("no row text changed -- Stage A edit steps not done",
             environmental=True)
    else:
        check(True, "Stage A edits landed (%s)" % ", ".join(sorted(set(edited))))
    if not new_notes:
        skip("no note was added -- Stage A quick-capture step not done",
             environmental=True)
    else:
        check(len(new_notes) == 1,
              "quick capture wrote the note exactly once (n=%d)"
              % len(new_notes))

    now = dict(now)
    # `removed_placements` and not `removed_photo_links`: what Stage A
    # removed is an OCCURRENCE, and the link it belongs to is still
    # there — often still on other days. Recording the link id alone
    # would name a row that did not go anywhere.
    now["stage_a"] = {"removed_placements":
                      [{"link": k, "before": b, "after": a}
                       for k, b, a in shrunk],
                      "new_notes": new_notes,
                      "edited_kinds": sorted(set(edited))}
    record_attestations(now, attests, "checkpoint", now_iso)
    with open(STATE_CP, "w", encoding="utf-8") as fh:
        json.dump(now, fh, indent=1)

    out("")
    print_stage_b_walkthrough()
    out("")
    out("checkpoint state: %s" % STATE_CP)
    return _verdict("PASS -- Stage A held.")


#: Stage B, in the order it has to be done. Held as data rather than
#: printed inline so a test can assert that every operation the harness
#: CLASSIFIES is an operation the operator was actually asked to
#: perform. The two used to drift: `verify` could report "no Move was
#: performed" about a step no walkthrough had ever mentioned, and the
#: operator had no way to know which of a dozen gestures the instrument
#: was waiting for.
#
# CORRECTED 2026-08-13 after review, in three ways that together make
# the printed walkthrough ACHIEVABLE. It was not:
#
#   * two operator actions `verify` still checks for -- moving a
#     conversation, and adding a Stage B quick note -- had dropped out
#     of the instructions entirely, so following them exactly always
#     produced SKIP and never PASS;
#   * step 1 told the operator to add ONE photograph to TWO days, and
#     the Add assertion demanded exactly one fresh placement, so
#     obeying the instructions produced a FAIL;
#   * every step reused "a photograph", but Add, Remove and Move are
#     classified from the checkpoint-to-final day SET. One photograph
#     added to two days and then removed from one of them has a net set
#     that GREW, so it reads as an Add and the Remove is unprovable.
#     Each net operation needs its own photograph.
#
# Hence photo A / B / C / D below, and `plan` mode, which reads the
# checkpoint and names the actual links and days rather than leaving
# the operator to work out which photograph can play which part.
#
# ORDER MATTERS, AND IT IS THE ORDER PRINTED (corrected 2026-08-13).
# The date-suggestion step comes FIRST because a photograph already on
# a day is not offered as that day's suggestion — so any step that puts
# A on its first day destroys the affordance the suggestion step needs.
STAGE_B_STEPS = [
    ("date_suggestion", "Photo A -- accept the date suggestion FIRST",
     "On photo A's first day, find A under 'Taken on this date' and "
     "press Add to this day. Do this BEFORE anything else touches that "
     "day: a photograph already on a day is not suggested for it, so "
     "any other route would consume this step's own affordance. A "
     "suggestion is not a placement until you accept it."),
    ("add_several", "Photo D -- several photographs at once",
     "Select the photographs the plan calls D together and add them to "
     "the day it names. If any of them fail, the panel must say how "
     "many landed; the ones that did not stay selected so Add can be "
     "pressed again."),
    ("add_two_days", "Photo A -- confirm it is on two days",
     "Photo A must now be on BOTH of its days, and still be one "
     "photograph rather than two. If the batch above did not give it "
     "the second day, add it now. It must end up on two days, not move "
     "from one to the other -- this is the whole point of the work "
     "order."),
    ("remove", "Photo B -- remove one placement",
     "Take the photograph the plan calls B and press Remove from this "
     "day on the day named. Its trip membership, its caption and its "
     "approvals must all survive; only that one placement goes."),
    ("move", "Photo C -- move one placement",
     "Use Move... on the photograph the plan calls C, from the day it "
     "is on to a day it is NOT on. Moving is a separate gesture from "
     "Add and names the day it moves from."),
    ("caption", "A shared caption",
     "Edit the caption of photo A, from one of its two days. The other "
     "day must show the same caption -- a caption belongs to the "
     "photograph, not to a placement -- and it must stay withheld from "
     "Lori."),
    ("conversation_move", "Move the conversation",
     "Drag or send the existing conversation to a different day. Its "
     "transcript must not change, and the placement must record itself "
     "as an operator's confirmed choice rather than a guess."),
    ("quick_note", "One Stage B quick note",
     "Add exactly one quick note, on any day. One, so that 'the note "
     "Stage B created' names something unambiguous."),
]

STAGE_B_STEP_KEYS = tuple(k for k, _t, _d in STAGE_B_STEPS)


def print_stage_b_walkthrough(plan=None):
    out(">>> STAGE A IS RECORDED. NOW DO STAGE B, IN THIS ORDER:")
    out("")
    if plan is not None:
        print_plan_assignments(plan)
        out("")
    for i, (_key, title, detail) in enumerate(STAGE_B_STEPS, 1):
        out("  %d. %s" % (i, title))
        for line in _wrap(detail, 66):
            out("     " + line)
    out("")
    out("  While doing all of the above, at least once: type into a day's")
    out("  fields WITHOUT saving, then press a photo control (Add to this")
    out("  day, Remove from this day, or Move...). It must refuse, keep")
    out("  what you typed, and show Save / Cancel. That is the")
    out("  dirty-guard attestation.")
    out("")
    out(">>> THEN, IN THIS ORDER:")
    out("")
    out("  a. Stop the stack, start it again, and hard-reload the page.")
    out("  b. Re-open the trip and a day modal, close it, and re-open it.")
    out("     It must come back on a usable day. That is the")
    out("     modal-reopen attestation.")
    out("  c. ./scripts/wo02_acceptance.py verify --attest modal-reopen")
    out("  d. Restore the trip by hand to how it was before Stage A.")
    out("  e. ./scripts/wo02_acceptance.py restore-verify")
    out("")
    out("  Stage A's results are proved by comparing the capture and the")
    out("  checkpoint, so `verify` needs NO further edit and NO second")
    out("  quick note. Leaving Stage A's work untouched is the pass.")


def build_stage_b_plan(cp):
    """Which photograph plays which part, derived from the checkpoint.

    ADDED 2026-08-13 after review. Add, Remove and Move are classified
    from the checkpoint-to-final day SET, so they are only independently
    observable if they happen to DIFFERENT photographs — one photograph
    added to two days and then removed from one has a set that grew, and
    the Remove cannot be seen at all.

    Returns {"ok": bool, "problems": [...], "a"/"b"/"c"/"d": ...}. It
    reads and writes nothing: the operator finds out the fixture cannot
    prove something BEFORE changing any data, not after.
    """
    days = [{"id": str(d.get("id")), "n": d.get("n")}
            for d in (cp.get("days") or []) if d.get("id")]
    links = cp.get("photo_links") or {}
    plan = {"ok": False, "problems": [], "days": days,
            "a": None, "b": None, "c": None, "d": []}

    if len(days) < 2:
        plan["problems"].append(
            "the trip has %d day(s); Add-to-two-days and Move both need "
            "at least two" % len(days))
        return plan

    unplaced, placed = [], []
    for lid in sorted(links):
        (placed if days_of(links[lid]) else unplaced).append(lid)

    taken = set()

    # A: an unplaced photograph, so its two new days are unambiguous.
    for lid in unplaced:
        plan["a"] = {"link": lid, "days": [days[0], days[1]]}
        taken.add(lid)
        break
    if plan["a"] is None:
        plan["problems"].append(
            "no photograph is unplaced at the checkpoint, so none can "
            "cleanly gain two days (photo A)")

    # B: remove one placement. Any placed photograph will do.
    for lid in placed:
        if lid in taken:
            continue
        plan["b"] = {"link": lid, "day": _day_by_id(days,
                                                    days_of(links[lid])[0])}
        taken.add(lid)
        break
    if plan["b"] is None:
        plan["problems"].append(
            "no spare placed photograph to remove a placement from "
            "(photo B)")

    # C: move one placement to a day it is not on.
    for lid in placed:
        if lid in taken:
            continue
        on = days_of(links[lid])
        elsewhere = [d for d in days if d["id"] not in on]
        if not elsewhere:
            continue
        plan["c"] = {"link": lid, "from": _day_by_id(days, on[0]),
                     "to": elsewhere[0]}
        taken.add(lid)
        break
    if plan["c"] is None:
        plan["problems"].append(
            "no spare photograph that is on one day and off another, so "
            "a Move cannot be told apart from an Add (photo C)")

    # D: the multi-photograph add.
    #
    # A may be IN this batch. Selecting A and a spare together and
    # adding them to one day gives A its first day and the spare its
    # only one -- two independently observable Adds from one gesture --
    # so a trip with a single spare can still demonstrate "several
    # photographs at once". Requiring D to be wholly disjoint from A
    # would have declared the live Bismarck fixture unusable over a
    # photograph it did not actually need.
    spares = [lid for lid in sorted(links) if lid not in taken]
    if len(spares) >= 2:
        plan["d"] = spares[:3]
        plan["d_day"] = days[0]
        plan["d_includes_a"] = False
    elif len(spares) == 1 and plan["a"]:
        # ── THE BATCH GOES TO A's SECOND DAY, NOT ITS FIRST ───────────
        #
        # CORRECTED 2026-08-13 after review. The batch used to be sent
        # to A's FIRST day, and A's first day is the one the operator is
        # supposed to reach through "Taken on this date". A photograph
        # already on a day is not offered as that day's suggestion, so
        # the batch consumed the very affordance the next step needed —
        # and on the live fixture A is precisely the Day 1 suggestion,
        # because Stage A removed it from Day 1 and its date still
        # matches.
        #
        # So: A reaches its first day through the suggestion control,
        # and the batch gives it its second. Two different days, two
        # different controls, and neither destroys the other.
        plan["d"] = [plan["a"]["link"], spares[0]]
        plan["d_day"] = plan["a"]["days"][1]
        plan["d_includes_a"] = True
    else:
        plan["d"] = spares
        plan["d_day"] = None
        plan["d_includes_a"] = False
        plan["problems"].append(
            "only %d photograph(s) are free for a multi-select Add, and "
            "'several photographs at once' needs two (photo D). Add "
            "another photograph to the trip first."
            % (len(spares) + (1 if plan["a"] else 0)))

    # ── THE DATE SUGGESTION IS AN ASSIGNMENT, NOT A HINT ──────────────
    #
    # ADDED 2026-08-13 after review. Every step that affects placement
    # classification named its photograph; this one said "find a
    # photograph under 'Taken on this date'" and left the operator to
    # pick, which is how it ended up colliding with the batch.
    #
    # A reaches its FIRST day through this control. That is a real
    # ordering constraint and the printed walkthrough states it: the
    # suggestion has to be taken before anything else puts A on that
    # day, because a photograph already on a day is not suggested for
    # it.
    #
    # WHAT THIS CANNOT KNOW, AND SAYS SO. The snapshot records a photo
    # link's days, placement ids, caption hash and approval flag. It
    # does NOT record `taken_at`, so nothing here can prove A will
    # actually appear under "Taken on this date" for that day. It is
    # published as an operator PRECONDITION to confirm, never as a
    # derived fact.
    if plan["a"]:
        plan["suggestion"] = {"link": plan["a"]["link"],
                              "day": plan["a"]["days"][0]}
        plan["a_second_via"] = "batch" if plan.get("d_includes_a") else "direct"
    else:
        plan["suggestion"] = None
        plan["a_second_via"] = None

    plan["ok"] = not plan["problems"]
    return plan


def _day_by_id(days, day_id):
    for d in days:
        if d["id"] == str(day_id):
            return d
    return {"id": str(day_id), "n": "?"}


def _day_label(d):
    return "Day %s (%s)" % (d.get("n"), str(d.get("id"))[:8])


def print_plan_assignments(plan):
    if not plan.get("ok"):
        out("  !! THIS TRIP CANNOT PROVE STAGE B AS WRITTEN:")
        for p in plan.get("problems") or []:
            for line in _wrap("- " + p, 64):
                out("     " + line)
        out("")
        out("  Fix the fixture before changing any data. Adding an")
        out("  unplaced photograph to the trip is usually enough.")
        return
    out("  YOUR ASSIGNMENTS FOR THIS TRIP, IN THIS ORDER:")
    a, b, c, sug = plan["a"], plan["b"], plan["c"], plan["suggestion"]
    out("   1 suggestion  %s   'Taken on this date' -> Add, on %s"
        % (sug["link"][:8], _day_label(sug["day"])))
    out("   2 photo D     %s   select together, add to %s"
        % (", ".join(l[:8] for l in plan["d"]),
           _day_label(plan["d_day"]) if plan.get("d_day") else "one day"))
    if plan.get("a_second_via") == "batch":
        out("                 (photo A is in that batch, and that is how")
        out("                  it gets its SECOND day)")
    out("   3 photo A     %s   must now be on %s and %s%s"
        % (a["link"][:8], _day_label(a["days"][0]), _day_label(a["days"][1]),
           "" if plan.get("a_second_via") == "batch"
           else " -- add the second day directly"))
    out("   4 photo B     %s   remove from %s"
        % (b["link"][:8], _day_label(b["day"])))
    out("   5 photo C     %s   move %s -> %s"
        % (c["link"][:8], _day_label(c["from"]), _day_label(c["to"])))
    out("   6 caption     %s   edit from one of its two days"
        % a["link"][:8])
    out("   7 conversation           move it to another day")
    out("   8 quick note              exactly one, any day")
    out("")
    out("  THE ORDER IS NOT A SUGGESTION. Photo A reaches its first day")
    out("  through the 'Taken on this date' control, and a photograph")
    out("  already on a day is not offered as that day's suggestion --")
    out("  so anything that places A there first destroys step 1.")
    out("")
    out("  PRECONDITION YOU MUST CONFIRM ON SCREEN:")
    out("     photo %s appears under 'Taken on this date' on %s."
        % (sug["link"][:8], _day_label(sug["day"])))
    out("     This harness records a photograph's days, placement rows,")
    out("     caption and approvals -- it does NOT record taken_at, so")
    out("     it cannot know which day suggests which photograph. If")
    out("     that photograph is not offered there, STOP and say so")
    out("     rather than substituting another route.")
    out("")
    out("  Each net operation belongs to its OWN photograph. Add,")
    out("  Remove and Move are read from the day set at the end, so a")
    out("  photograph that both gained and lost a day proves neither.")


def do_plan(now):
    """Read-only: what Stage B should do, given the checkpoint."""
    out("=== WO-02 STAGE B PLAN ===")
    out("")
    if not os.path.exists(STATE_CP):
        out("No checkpoint at %s." % STATE_CP)
        out("Run `checkpoint` after Stage A first.")
        return 2
    with open(STATE_CP, encoding="utf-8") as fh:
        cp = json.load(fh)
    warn_if_legacy(cp, "plan")
    plan = build_stage_b_plan(cp)
    print_stage_b_walkthrough(plan)
    out("")
    out("Read-only. Nothing was written; the checkpoint is untouched.")
    return 0 if plan["ok"] else 2


def _wrap(text, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def do_restore_verify(now, attests, now_iso):
    """After the photo and conversation are put back on Day 1.

    The restore is the strongest identity test in the whole gate: if the
    product were re-creating rows rather than moving them, a round trip
    is where the duplicate finally shows.
    """
    if not os.path.exists(STATE):
        out("No baseline at %s -- run 'capture' first." % STATE)
        return 2
    with open(STATE, encoding="utf-8") as fh:
        old = json.load(fh)
    _legacy_baseline = old
    cp = None
    if os.path.exists(STATE_CP):
        with open(STATE_CP, encoding="utf-8") as fh:
            cp = json.load(fh)

    out("=== WO-02 RESTORE-VERIFY ===")
    out("")
    warn_if_legacy(_legacy_baseline, "restore-verify")

    # ── The complete original placement SET is back ───────────────────
    #
    # This compared one scalar to one scalar: `cur["day"] == was["day"]`.
    # The Phase 0 map flagged that as becoming WRONG rather than merely
    # incomplete under many-to-many, and it is wrong in both directions.
    # A photograph restored to Day 1 while still on Day 3 has a null
    # derived scalar and would FAIL a check that should pass; a
    # photograph restored to the wrong ONE of its two days has a null
    # scalar either way and would PASS a check that should fail.
    #
    # Set equality is the honest question, and it is stricter: it
    # catches a day that came back, a day that did not, and a day that
    # was never there.
    wrong = []
    for k, was in old["photo_links"].items():
        cur = now["photo_links"].get(k)
        if cur is None:
            check(False, "photo link %s no longer exists" % k[:8])
            continue
        before, after = days_of(was), days_of(cur)
        if before != after:
            wrong.append((k, before, after))
    check(not wrong,
          "every photograph is back on its complete original day set "
          "(%d wrong)" % len(wrong))
    if wrong:
        for k, before, after in wrong[:10]:
            out("      photo %s: wanted %s, got %s" % (k[:8], before, after))
    check(len(now["photo_links"]) == len(old["photo_links"]),
          "the round trip created no duplicate photo link (%d -> %d)"
          % (len(old["photo_links"]), len(now["photo_links"])))

    # And it deleted nothing it was not asked to. Total placements are
    # counted across every link, so a restore that put one photograph
    # back by taking a day off another would be caught here even though
    # both links still exist and both still have days.
    want_total = sum(len(days_of(v)) for v in old["photo_links"].values())
    got_total = sum(len(days_of(v)) for v in now["photo_links"].values())
    check(want_total == got_total,
          "the trip holds the same number of placements as before "
          "(%d -> %d)" % (want_total, got_total))

    # PLACEMENT IDS ARE DELIBERATELY NOT COMPARED HERE.
    #
    # Restoring means the operator put the photograph back on the day.
    # Nothing in the product promises that doing so reuses the deleted
    # placement row — it creates a new one, which is the correct
    # behaviour for a row whose `created_at` records when this placement
    # was made. Demanding id equality would fail a perfectly correct
    # restore, and demanding it of a product that never promised it is
    # how a harness starts dictating implementation.
    #
    # The DAY SET is the promise, and it is asserted above. Identity is
    # asserted where the product does promise it: on the placements an
    # operation did NOT name (see do_checkpoint and do_verify).
    reused = 0
    for k, was in old["photo_links"].items():
        cur = now["photo_links"].get(k) or {}
        b, a = pids_of(was), pids_of(cur)
        reused += sum(1 for d in a if b.get(d) and b[d] == a[d])
    if reused:
        out("      (%d restored placement(s) happen to reuse their original "
            "row id; not required)" % reused)

    for lid, was in old["turns"].items():
        cur = now["turns"].get(lid)
        if not cur:
            check(False, "conversation %s no longer exists" % lid[:8])
            continue
        check(cur["day"] == was["day"],
              "conversation %s is back on its original day" % lid[:8])
        check(cur["u"] == was["u"] and cur["a"] == was["a"],
              "conversation %s still points at the same turn rows" % lid[:8])
        check(cur["nh"] == was["nh"] and cur["lh"] == was["lh"],
              "conversation %s transcript byte-identical end to end" % lid[:8])
    check(len(now["turns"]) == len(old["turns"]),
          "the round trip created no duplicate conversation link (%d -> %d)"
          % (len(old["turns"]), len(now["turns"])))

    # Approval is still off unless it was explicitly granted.
    gained = [k for k, v in now["photo_links"].items()
              if v["approved"]
              and not old["photo_links"].get(k, {}).get("approved", 0)]
    check(not gained,
          "caption approval is still off (n=%d newly approved)" % len(gained))

    # The Stage A note survived the whole round trip, exactly once.
    if cp and (cp.get("stage_a") or {}).get("new_notes"):
        want = set((cp["stage_a"]["new_notes"]))
        seen = [r[1] for rows in now["items"].values() for r in rows
                if r[0] == "note" and r[1] in want]
        check(len(seen) == len(want),
              "the Stage A note still exists exactly once (%d of %d)"
              % (len(seen), len(want)))
    else:
        skip("no Stage A note recorded -- run checkpoint before restoring",
             environmental=True)

    # ── Rail counts agree with the rows now on each day ───────────────
    #
    # CORRECTED 2026-08-13. This summed EVERY key ending in `_count` and
    # compared the total against every timeline row. Both halves are
    # wrong on a real calendar day, and they were wrong in opposite
    # directions, which is why the arithmetic looked plausible:
    #
    #   * `item_count` is itself the sum of the four component lanes, so
    #     summing all five double-counts the day;
    #   * `day_text` rows are DELIBERATELY excluded from `item_count`,
    #     so `len(rows)` is larger than any count claims to be.
    #
    # Against Chris's live Day 1 — one conversation, no photographs,
    # three notes, three day-text fields — the old check computed 8 on
    # the left and 7 on the right and would have failed a correct
    # calendar. It never fired because the fixtures fed it a synthetic
    # `row_count` no calendar has ever served.
    check_count_contract(now, "restore")

    if attests:
        state = dict(cp or old)
        record_attestations(state, attests, "restore-verify", now_iso)
        target = STATE_CP if cp else STATE
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=1)

    book = ((cp or old).get("attestations") or {})
    missing = [k for k in ATTESTABLE if k not in book]
    if missing:
        out("")
        for k in missing:
            skip("not attested: %s (pass --attest %s on the run where you "
                 "saw it)" % (ATTESTABLE[k], k), environmental=True)

    return _verdict("PASS -- WO-02 acceptance met, Gate 3 complete.")


def do_verify(now, attests=None, now_iso=None):
    # ── STAGE B IS MEASURED AGAINST THE CHECKPOINT ────────────────────
    #
    # CORRECTED 2026-08-13 after review. This loaded STATE — the
    # `capture` baseline — and compared Stage B against the world as it
    # was BEFORE Stage A. Every Stage A edit therefore looked like Stage
    # B evidence: a photograph the operator removed from a day in Stage
    # A was reported here as a Stage B "Remove from this day", a note
    # added in Stage A satisfied "quick capture created a note", and a
    # walkthrough where Stage B was never performed at all could report
    # PASS on the strength of Stage A alone.
    #
    # That contradicted the harness's own stated design, four lines from
    # the top of this file: "Each mode measures against the state the
    # PREVIOUS one wrote". `checkpoint` writes STATE_CP for exactly this
    # reason, and `verify` was the one mode not reading it.
    #
    # STATE remains the authority for `restore-verify`, which asks
    # whether the ORIGINAL world came back — a question about capture,
    # not about the checkpoint.
    if not os.path.exists(STATE_CP):
        out("=== WO-02 VERIFY ===")
        out("")
        out("No checkpoint at %s." % STATE_CP)
        out("")
        out("Stage B is measured against the state 'checkpoint' wrote, not "
            "against the")
        out("original capture. Without it this run could only compare Stage "
            "A + Stage B")
        out("together against the beginning, and would report Stage A's work "
            "as Stage B's.")
        out("")
        out("Run:  ./scripts/wo02_acceptance.py checkpoint    (after Stage "
            "A, before Stage B)")
        out("      ./scripts/wo02_acceptance.py verify        (after Stage "
            "B + restart)")
        return 2

    with open(STATE_CP, encoding="utf-8") as fh:
        old = json.load(fh)

    out("=== WO-02 VERIFY ===")
    out("")
    out("(measured against the checkpoint: %s)" % os.path.basename(STATE_CP))
    warn_if_legacy(old, "verify")

    # point 7 -- a move never rewrites a transcript
    for lid, was in old["turns"].items():
        cur = now["turns"].get(lid)
        if not cur:
            check(False, "conversation %s vanished" % lid[:8])
            continue
        check(cur["nh"] == was["nh"] and cur["lh"] == was["lh"],
              "conversation %s transcript byte-identical" % lid[:8])
        check(cur["u"] == was["u"] and cur["a"] == was["a"],
              "conversation %s still points at the same turn rows" % lid[:8])

    moved_conv = [k for k, v in now["turns"].items()
                  if k in old["turns"] and v["day"] != old["turns"][k]["day"]]
    if not moved_conv:
        skip("no conversation was moved -- Stage B step 'Move the conversation' not done", step="conversation_move")
    else:
        out("      (%d conversation move(s) seen)" % len(moved_conv))
        for k in moved_conv:
            check(now["turns"][k]["st"] == "confirmed"
                  and now["turns"][k]["src"] == "operator_selected",
                  "moved conversation %s recorded as confirmed operator "
                  "placement" % k[:8])

    # point 3 -- an edit never silently grants Lori approval
    gained = [k for k, v in now["photo_links"].items()
              if v["approved"]
              and not old["photo_links"].get(k, {}).get("approved", 0)]
    check(not gained,
          "no caption edit granted Lori approval (n=%d)" % len(gained))

    # ── point 6 -- Add, Move and Remove are now three different things ─
    #
    # This asked whether one scalar differed from another and called any
    # difference a "move". Under set semantics that conflates the three
    # operations the interface now offers, and the operator did one of
    # them deliberately: a set that GREW is an Add, one that SHRANK is a
    # Remove from this day, and one that changed while staying the same
    # size is a Move. Reporting all three as "moved" would make a
    # walkthrough that added a second day read as a successful move.
    # ── A LINK THAT VANISHED IS DATA LOSS, NOT A SKIPPED STEP ─────────
    #
    # ADDED 2026-08-13 after review. The classification loop below skips
    # anything absent from `old`, and the unrelated-link sweep iterates
    # `now` — so a photo link DELETED during Stage B appeared in
    # neither. It contributed no Add, no Remove, no Move, and the run
    # reported SKIP / INCOMPLETE: the harness's quietest possible
    # answer for its loudest possible failure.
    #
    # Checked before the classification so the readout leads with it.
    vanished = [k for k in old["photo_links"]
                if k not in now["photo_links"]]
    check(not vanished,
          "no photo link disappeared during Stage B (n=%d%s)"
          % (len(vanished),
             ": " + ", ".join(k[:8] for k in vanished[:5]) if vanished
             else ""))

    # New trip memberships are reported on their own line and take no
    # part in the Add/Remove/Move classification below — a link that did
    # not exist at the checkpoint has no `before` to compare against, so
    # counting it as an Add would satisfy a walkthrough step nobody
    # performed.
    fresh_links = [k for k in now["photo_links"]
                   if k not in old["photo_links"]]
    if fresh_links:
        out("      (%d new trip membership(s) since the checkpoint: %s)"
            % (len(fresh_links), ", ".join(k[:8] for k in fresh_links[:5])))
    check(len(now["photo_links"]) == len(old["photo_links"]),
          "Stage B created no second trip link (%d -> %d)"
          % (len(old["photo_links"]), len(now["photo_links"])))

    added, dropped, moved_photo = [], [], []
    for k, v in now["photo_links"].items():
        if k not in old["photo_links"]:
            continue
        before, after = days_of(old["photo_links"][k]), days_of(v)
        if before == after:
            continue
        if len(after) > len(before):
            added.append((k, before, after))
        elif len(after) < len(before):
            dropped.append((k, before, after))
        else:
            moved_photo.append((k, before, after))

    if not (added or dropped or moved_photo):
        skip("no photo placement changed -- the Add, Remove and Move "
             "steps were all skipped", step="add_two_days")
    for label, rows, rule, step_key in (
            ("Add", added,
             "adding a day kept every day it already had", "add_two_days"),
            ("Remove from this day", dropped,
             "removing a day kept every other day", "remove"),
            ("Move", moved_photo,
             "moving changed the day and kept the count", "move")):
        if not rows:
            skip("no %s was performed -- that Stage B step not done"
                 % label, step=step_key)
            continue
        out("      (%d %s operation(s) seen)" % (len(rows), label))
        for k, before, after in rows:
            if label == "Add":
                ok = all(d in after for d in before)
            elif label == "Remove from this day":
                ok = all(d in before for d in after)
            else:
                ok = len(before) == len(after) and before != after
            check(ok, "%s on photo %s: %s (%s -> %s)"
                  % (label, k[:8], rule, before, after))

            # ── PLACEMENT IDENTITY ────────────────────────────────────
            #
            # The day-set assertion above proves the right DAYS are
            # there. It cannot tell a preserved placement from a
            # destroyed-and-recreated one, and every operation here is
            # supposed to leave the placements it did not name alone.
            kept = [d for d in before if d in after]
            rekeyed = rekeyed_days(old["photo_links"][k],
                                   now["photo_links"][k], kept)
            check(not rekeyed,
                  "%s on photo %s left every untouched placement's row "
                  "alone (%d rewritten: %s)"
                  % (label, k[:8], len(rekeyed),
                     ", ".join("%s %s->%s" % r for r in rekeyed[:3])))

            # Malformed ids, on both sides. A current entry that lists a
            # day without a placement row, or gives two days one row, is
            # not evidence about anything — every identity check above
            # and below is reading a value that does not mean what it
            # says.
            for problem in (id_health(old["photo_links"][k],
                                      "photo %s before" % k[:8])
                            + id_health(now["photo_links"][k],
                                        "photo %s after" % k[:8])):
                check(False, problem)

            b_ids, a_ids = (pids_of(old["photo_links"][k]),
                            pids_of(now["photo_links"][k]))
            fresh = [d for d in after if d not in before]
            # GUARDED ON FORMAT, NOT ON TRUTHINESS. `b_ids` is empty for
            # a photograph that had NO placements, so `if b_ids` skipped
            # the whole check for an Add from zero days — the commonest
            # Add there is.
            current = (is_set_format(old["photo_links"][k])
                       and is_set_format(now["photo_links"][k]))
            if label == "Add" and current:
                # ── ONE ADD MAY PLACE A PHOTOGRAPH ON SEVERAL DAYS ────
                #
                # CORRECTED 2026-08-13 after review. This asserted
                # `len(fresh) == 1`, which is the single-day product's
                # rule wearing set-shaped clothes — and it directly
                # contradicted the walkthrough's own first instruction,
                # *add one photograph to two days*. An operator who
                # followed the printed steps produced a FAIL.
                #
                # The real invariants are that every new day got its OWN
                # new row, and that nothing already there was disturbed.
                # `PLACEMENT_BATCH_MAX` caps a REQUEST, not how many
                # days a photograph may occupy between two snapshots.
                check(len(fresh) >= 1,
                      "Add on photo %s placed it on %d new day(s) (%s)"
                      % (k[:8], len(fresh), ", ".join(d[:8] for d in fresh)))
                new_ids = [a_ids.get(d) for d in fresh]
                check(all(new_ids),
                      "Add on photo %s recorded a placement row for every "
                      "new day (%d of %d)"
                      % (k[:8], len([i for i in new_ids if i]), len(fresh)))
                check(len(set(i for i in new_ids if i)) == len([i for i in new_ids if i]),
                      "Add on photo %s gave each new day its OWN placement "
                      "row (%d row(s) for %d day(s))"
                      % (k[:8], len(set(i for i in new_ids if i)), len(fresh)))
                check(not [i for i in new_ids if i and i in b_ids.values()],
                      "Add on photo %s created NEW placement rows rather "
                      "than re-pointing existing ones" % k[:8])
                check(len(set(fresh)) == len(fresh),
                      "Add on photo %s lists each new day once" % k[:8])
                kept_ids = [b_ids.get(d) for d in kept if b_ids.get(d)]
                check(all(a_ids.get(d) == b_ids.get(d) for d in kept),
                      "Add on photo %s preserved all %d placement row(s) it "
                      "already had" % (k[:8], len(kept_ids)))
            if label == "Move" and current:
                src = [d for d in before if d not in after]
                for d in src:
                    if b_ids.get(d):
                        check(b_ids[d] not in a_ids.values(),
                              "Move on photo %s removed the named source "
                              "placement" % k[:8])
                for d in fresh:
                    check(bool(a_ids.get(d)),
                          "Move on photo %s recorded a placement row for the "
                          "destination day %s" % (k[:8], d))
                    check(a_ids.get(d) not in b_ids.values(),
                          "Move on photo %s created the destination "
                          "placement" % k[:8])

    # [The per-label "%s created no second trip link" check stood here
    # and was removed 2026-08-13. It asked the same question up to three
    # times in one run — once per operation kind — and the answer never
    # depended on the label. It is now asserted once, unconditionally,
    # above the classification, where it also covers the case no label
    # could reach: a link that vanished entirely.]

    # EVERY OTHER PHOTOGRAPH's placements are untouched. The per-link
    # checks above only look at links that changed; this is the one that
    # notices an operation on one photograph disturbing a different one.
    touched = set(k for k, _b, _a in added + dropped + moved_photo)
    disturbed = []
    for k, v in now["photo_links"].items():
        if k in touched or k not in old["photo_links"]:
            continue
        both = [d for d in days_of(old["photo_links"][k]) if d in days_of(v)]
        disturbed.extend(
            (k, r) for r in rekeyed_days(old["photo_links"][k], v, both))
    check(not disturbed,
          "no unrelated photograph's placement rows were rewritten (%d)"
          % len(disturbed))

    # ── STAGE A PERSISTENCE, points 2/4/5/10 ──────────────────────────
    #
    # CORRECTED 2026-08-13 after the live Stage A run. This used to diff
    # the checkpoint against NOW and call any difference "edits persisted
    # across the restart". That measured change, not persistence, and got
    # both directions wrong: an operator who restarted and correctly
    # touched nothing was told SKIP, while one who edited something
    # unrelated after the checkpoint was told PASS.
    #
    # It was also imprecise about what Stage A did. The live checkpoint
    # reported `Stage A edits landed (note)` although day text and a
    # photo caption had ALSO been edited — see stage_a_changeset() for
    # why each was invisible to a row diff.
    #
    # So the change set is derived from the two whole snapshots, and
    # every result it names is asserted to still exist EXACTLY ONCE and
    # still hold its checkpoint value. An unchanged value is the pass.
    base = None
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as fh:
            base = json.load(fh)
    if base is None:
        skip("no capture baseline at %s -- Stage A persistence cannot be "
             "derived" % os.path.basename(STATE), environmental=True)
        changes = {"day_text": [], "notes": [], "new_notes": [],
                   "captions": [], "removed_placements": [],
                   "surviving_placements": []}
    else:
        changes = stage_a_changeset(base, old)

    now_rows = _rows_by_identity(now)
    now_counts = {}
    for did, rows in (now.get("items") or {}).items():
        for r in rows:
            k = (str(did), str(r[0]), str(r[1]))
            now_counts[k] = now_counts.get(k, 0) + 1

    def _still_there(record, kind, label):
        key = (record["day"], kind, record["id"])
        seen = now_counts.get(key, 0)
        check(seen == 1,
              "%s %s on day %s survived the restart exactly once (found %d)"
              % (label, record["id"][:8], record["day"][:8], seen))
        if seen:
            check(now_rows.get(key) == record["h"],
                  "%s %s still holds its checkpoint value"
                  % (label, record["id"][:8]))

    stage_a_total = (len(changes["day_text"]) + len(changes["notes"])
                     + len(changes["new_notes"]) + len(changes["captions"]))
    if not stage_a_total:
        skip("capture and checkpoint are identical -- Stage A recorded no "
             "edits, so there is nothing to prove persisted",
             environmental=True)
    else:
        out("      (Stage A wrote: %d day-text field(s), %d note edit(s), "
            "%d new note(s), %d caption(s))"
            % (len(changes["day_text"]), len(changes["notes"]),
               len(changes["new_notes"]), len(changes["captions"])))

    for rec in changes["day_text"]:
        _still_there(rec, "day_text", "day text")
    for rec in changes["notes"]:
        _still_there(rec, "note", "edited note")
    for rec in changes["new_notes"]:
        _still_there(rec, "note", "quick-capture note")

    for rec in changes["captions"]:
        cur = now["photo_links"].get(rec["link"])
        check(cur is not None,
              "captioned photo %s still has its trip membership"
              % rec["link"][:8])
        if cur is not None:
            check(cur.get("ch") == rec["ch"],
                  "photo %s still holds its Stage A caption on every day "
                  "it appears" % rec["link"][:8])
            # A caption belongs to the LINK, so consistency across days is
            # structural rather than something the operator maintains --
            # which is exactly why it must be asserted rather than assumed.
            check(not cur.get("approved"),
                  "photo %s caption is still withheld from Lori"
                  % rec["link"][:8])

    # Placements Stage B DELIBERATELY changed are exempt from the Stage A
    # persistence assertion and are proved by the classification loop
    # above instead. Without this exemption the harness would demand that
    # a photograph stay where Stage A left it while the walkthrough asks
    # the operator to move it — a contradiction the instrument would
    # report as a product failure.
    stage_b_touched = set(k for k, _b, _a in added + dropped + moved_photo)
    live_pids = set()
    for v in now["photo_links"].values():
        live_pids.update(pids_of(v).values())
    for rec in changes["removed_placements"]:
        # The ROW IDENTITY is asserted unconditionally, with no Stage B
        # exemption, because a destroyed placement id reappearing is
        # never legitimate: it means an id was reused, and every
        # identity comparison in this harness is then reading a value
        # that does not mean what it says. Re-adding the photograph to
        # that day in Stage B is fine and must produce a NEW row.
        if rec["pid"] is not None:
            check(rec["pid"] not in live_pids,
                  "the placement row Stage A destroyed on photo %s was not "
                  "resurrected (%s)"
                  % (rec["link"][:8], str(rec["pid"])[:8]))
        # Whether the photograph is still OFF that day is exempt when
        # Stage B deliberately put it back -- that is an Add, and the
        # classification above proves it.
        if rec["link"] in stage_b_touched:
            continue
        cur = now["photo_links"].get(rec["link"]) or {}
        check(rec["day"] not in days_of(cur),
              "photo %s is still off day %s after the restart"
              % (rec["link"][:8], rec["day"][:8]))
    for rec in changes["surviving_placements"]:
        if rec["link"] in stage_b_touched or rec["pid"] is None:
            continue
        cur = now["photo_links"].get(rec["link"]) or {}
        check(pids_of(cur).get(rec["day"]) == rec["pid"],
              "photo %s kept placement row %s on day %s across the restart"
              % (rec["link"][:8], str(rec["pid"])[:8], rec["day"][:8]))

    # Stage B's own quick capture, which is a different question from
    # whether Stage A's note survived.
    new_notes = []
    for did, rows in now["items"].items():
        old_ids = set(tuple(x[:2]) for x in old["items"].get(did, []))
        for r in rows:
            if r[0] == "note" and tuple(r[:2]) not in old_ids:
                new_notes.append(r[1])
    if not new_notes:
        skip("no note was added during Stage B", step="quick_note")
    else:
        check(True, "Stage B quick capture created a note (n=%d)"
              % len(new_notes))

    # ── point 8 -- the rail counts ────────────────────────────────────
    #
    # CORRECTED 2026-08-13. This asked only whether the count dictionary
    # had CHANGED, which cannot distinguish a count that followed the
    # content from one that drifted away from it, and it skipped
    # entirely unless a Move or a note happened — so an Add or a Remove,
    # the two operations most likely to move a photo count, activated no
    # verification at all.
    #
    # Two assertions now. The contract is internal consistency, checked
    # unconditionally because a rail that disagrees with its own rows is
    # wrong whether or not this walkthrough touched it. The delta is the
    # placement arithmetic, checked against what actually happened.
    check_count_contract(now, "verify")

    expected_delta = {}
    for k, v in now["photo_links"].items():
        if k not in old["photo_links"]:
            continue
        before, after = days_of(old["photo_links"][k]), days_of(v)
        for d in after:
            if d not in before:
                expected_delta[d] = expected_delta.get(d, 0) + 1
        for d in before:
            if d not in after:
                expected_delta[d] = expected_delta.get(d, 0) - 1

    if not (added or dropped or moved_photo or moved_conv or new_notes):
        skip("nothing was added, removed or moved -- the rail counts had "
             "nothing to follow", step="add_two_days")
    else:
        unmeasurable = []
        for d in sorted(set(list(now.get("counts") or {})
                            + list(old.get("counts") or {}))):
            was, is_ = photo_count_of(old, d), photo_count_of(now, d)
            if was is None or is_ is None:
                unmeasurable.append(d)
                continue
            want = expected_delta.get(d, 0)
            check(is_ - was == want,
                  "day %s photo_count moved by %+d, as its placements did "
                  "(%d -> %d)" % (d[:8], want, was, is_))
        if unmeasurable:
            skip("%d day(s) served no photo_count -- their arithmetic could "
                 "not be checked" % len(unmeasurable), environmental=True)

    # Attestations are recorded HERE, before the verdict is computed.
    #
    # CORRECTED 2026-08-12 after review. This handling used to sit in
    # main(), at the call site AFTER `rc = do_verify(now)` had already
    # returned -- and do_verify returns _verdict(), which prints the
    # summary. So `verify --attest modal-reopen` saved the attestation
    # correctly and restore-verify could see it, but the run reported
    # "0 attested" and printed its ATTEST line BELOW the verdict that
    # was supposed to count it. checkpoint and restore-verify were
    # always right; verify was the odd one out precisely because it is
    # the only mode that owns no state file of its own, so its
    # attestation folds into the checkpoint and I put that at the call
    # site instead of inside the function. An instrument that
    # under-reports its own evidence is the same species of fault as a
    # green test over a wrong product, so all three modes now record
    # before they judge.
    if attests:
        # The existence branch that used to guard this is gone: since
        # 2026-08-13 verify REFUSES to run without a checkpoint, so by
        # the time control reaches here the file is present. Re-reading
        # it rather than writing `old` back is deliberate — `old` is the
        # comparison baseline and this function must not be able to
        # rewrite the thing it was judged against.
        with open(STATE_CP, encoding="utf-8") as fh:
            st = json.load(fh)
        record_attestations(st, attests, "verify", now_iso)
        with open(STATE_CP, "w", encoding="utf-8") as fh:
            json.dump(st, fh, indent=1)

    return _verdict("PASS -- Stage B held and survived the restart.\n"
                    "        Now restore Day 1 and run restore-verify.")


def main():
    argv = sys.argv[1:]
    mode = (argv[0] if argv else "").strip().lower()
    modes = ("capture", "checkpoint", "verify", "restore-verify", "plan")
    if mode not in modes:
        print(__doc__)
        return 2

    attests = []
    rest = argv[1:]
    i = 0
    while i < len(rest):
        if rest[i] == "--attest" and i + 1 < len(rest):
            key = rest[i + 1].strip().lower()
            if key not in ATTESTABLE:
                print("Unknown attestation %r. Known: %s"
                      % (key, ", ".join(sorted(ATTESTABLE))))
                return 2
            attests.append(key)
            i += 2
            continue
        print("Unrecognised argument %r" % rest[i])
        print(__doc__)
        return 2

    # `plan` reads the checkpoint file and nothing else. It must work
    # with the stack DOWN, because its whole purpose is telling the
    # operator whether the fixture can prove Stage B before they touch
    # any data -- and demanding a running API to answer that would make
    # it useless at exactly the moment it is wanted.
    if mode == "plan":
        rc = do_plan(None)
        flush(mode)
        return rc

    try:
        now = snapshot()
    except requests.RequestException as exc:
        print("Could not reach the API at %s -- is the stack up?" % API)
        print("  %s" % exc)
        return 2

    now_iso = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    if mode == "capture":
        rc = do_capture(now)
    elif mode == "checkpoint":
        rc = do_checkpoint(now, attests, now_iso)
    elif mode == "restore-verify":
        rc = do_restore_verify(now, attests, now_iso)
    else:
        # Attestation handling lives INSIDE do_verify (see the comment
        # there): doing it here, after the call, put it after the verdict
        # the summary is computed from.
        rc = do_verify(now, attests, now_iso)
    flush(mode)
    return rc


if __name__ == "__main__":
    sys.exit(main())
