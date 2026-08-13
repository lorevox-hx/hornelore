#!/usr/bin/env python3
"""WO-02 acceptance check (read-only).

    ./scripts/wo02_acceptance.py capture         # before Stage A
    ./scripts/wo02_acceptance.py checkpoint      # after Stage A, before Stage B
    ./scripts/wo02_acceptance.py verify          # after Stage B + restart
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


def skip(msg):
    """The operator did not exercise this step. Not a defect."""
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
        skip("no photo was removed from a day -- Stage A step not done")
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
            check(len(lost) == 1,
                  "photo %s lost exactly one day, not %d (%s -> %s)"
                  % (k[:8], len(lost), before, after))
            check(sorted(after) == sorted(kept),
                  "photo %s kept every other placement (%s)" % (k[:8], kept))
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
        skip("no row text changed -- Stage A edit steps not done")
    else:
        check(True, "Stage A edits landed (%s)" % ", ".join(sorted(set(edited))))
    if not new_notes:
        skip("no note was added -- Stage A quick-capture step not done")
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
    out(">>> Stage A recorded. Do Stage B, then restart, then run verify.")
    out("")
    out("checkpoint state: %s" % STATE_CP)
    return _verdict("PASS -- Stage A held.")


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
        skip("no Stage A note recorded -- run checkpoint before restoring")

    # Rail counts agree with the rows now on each day.
    disagree = []
    for d in now["days"]:
        did = d["id"]
        rows = now["items"].get(did) or []
        counts = now["counts"].get(did) or {}
        if sum(counts.values()) != len(rows):
            disagree.append(d["n"])
    check(not disagree,
          "rail counts agree with the timeline rows on every day "
          "(%d disagree)" % len(disagree))

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
                 "saw it)" % (ATTESTABLE[k], k))

    return _verdict("PASS -- WO-02 acceptance met, Gate 3 complete.")


def do_verify(now, attests=None, now_iso=None):
    if not os.path.exists(STATE):
        out("No baseline at %s -- run 'capture' first." % STATE)
        return 2

    with open(STATE, encoding="utf-8") as fh:
        old = json.load(fh)

    out("=== WO-02 VERIFY ===")
    out("")
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
        skip("no conversation was moved -- walkthrough step 7 not done")
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
        skip("no photo placement changed -- walkthrough steps 6/6a/6b "
             "not done")
    for label, rows, rule in (
            ("Add", added,
             "adding a day kept every day it already had"),
            ("Remove from this day", dropped,
             "removing a day kept every other day"),
            ("Move", moved_photo,
             "moving changed the day and kept the count")):
        if not rows:
            skip("no %s was performed -- that walkthrough step not done"
                 % label)
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
        check(len(now["photo_links"]) == len(old["photo_links"]),
              "%s created no second trip link (%d -> %d)"
              % (label, len(old["photo_links"]), len(now["photo_links"])))

    # points 2/4/5 -- edits survived the operator's restart
    edited = []
    for did, rows in now["items"].items():
        was = dict((tuple(r[:2]), tuple(r))
                   for r in [tuple(x) for x in old["items"].get(did, [])])
        for r in rows:
            key = tuple(r[:2])
            if key in was and tuple(r) != was[key]:
                edited.append(r[0])
    if not edited:
        skip("no row text changed -- walkthrough steps 2/4/5 not done")
    else:
        check(True, "text edits persisted across the restart (%s)"
              % ", ".join(sorted(set(edited))))

    # point 10 -- quick capture wrote a real note row
    new_notes = []
    for did, rows in now["items"].items():
        old_ids = set(tuple(x[:2]) for x in old["items"].get(did, []))
        for r in rows:
            if r[0] == "note" and tuple(r[:2]) not in old_ids:
                new_notes.append(r[1])
    if not new_notes:
        skip("no note was added -- walkthrough step 10 not done")
    else:
        check(True, "quick capture created a note (n=%d)" % len(new_notes))

    # point 8 -- rail counts followed the content
    changed = [d for d in now["counts"]
               if now["counts"][d] != old["counts"].get(d)]
    if not (moved_conv or moved_photo or new_notes):
        skip("nothing moved or was added -- rail counts had nothing to "
             "follow")
    else:
        check(bool(changed),
              "day counts changed on %d day(s)" % len(changed))

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
        if os.path.exists(STATE_CP):
            with open(STATE_CP, encoding="utf-8") as fh:
                st = json.load(fh)
            record_attestations(st, attests, "verify", now_iso)
            with open(STATE_CP, "w", encoding="utf-8") as fh:
                json.dump(st, fh, indent=1)
        else:
            out("(--attest ignored: no checkpoint state to record it in)")

    return _verdict("PASS -- Stage B held and survived the restart.\n"
                    "        Now restore Day 1 and run restore-verify.")


def main():
    argv = sys.argv[1:]
    mode = (argv[0] if argv else "").strip().lower()
    modes = ("capture", "checkpoint", "verify", "restore-verify")
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
