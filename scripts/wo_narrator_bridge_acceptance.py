#!/usr/bin/env python3
"""WO-TRIP-NARRATOR-BRIDGE-01 acceptance check (read-only).

    ./scripts/wo_narrator_bridge_acceptance.py preflight
    ./scripts/wo_narrator_bridge_acceptance.py capture   # before the walkthrough
    ./scripts/wo_narrator_bridge_acceptance.py verify    # after it
    ./scripts/wo_narrator_bridge_acceptance.py restart-verify   # after the
                                                         # operator restarts

`verify` compares the trip against the pre-walkthrough baseline and, when
it finds nothing wrong, writes down the ids it accepted. `restart-verify`
checks THOSE ids. Re-running verify after a restart proves the rows
survived; it cannot prove they are the same rows, because its baseline
predates the walkthrough and knows nothing of what the walkthrough made.

Reads the API only. Never edits data. Never starts, stops or restarts
any service -- the operator owns the stack.

Auto-writes its readout to
    docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_<mode>.console.txt
from inside Python. Not through a shell pipe: `| tee` silently produces
0-byte files under WSL pipe buffering, which is how an earlier run
banked an empty report.

PRINTS NO NARRATIVE TEXT. It reads Lori's answer and the narrator's
words, because the work order asks whether an answer was direct and
whether it claimed to see a picture, and those questions cannot be
answered without looking. What comes out is verdicts and short SHA-256
prefixes. No transcript, caption, note or day text reaches the terminal
or the file.

The gate readout is booleans only. It asks the SERVER which behaviours
are live, not the shell this script was launched from -- a flag set in
a terminal that never reached the process is exactly how the first
Gate 7 live run was voided.

Three-way verdict. FAIL is reserved for a check that was exercised and
did not hold. A step the operator has not performed yet is SKIP and the
run ends INCOMPLETE: the harness must never manufacture the evidence it
is verifying.

Exit codes, distinct on purpose:

    0  PASS         every exercised check held, nothing was skipped
    1  FAIL         a check was exercised and did not hold
    2  usage / API   bad mode, unreachable stack, missing baseline,
                     required gates off
    3  INCOMPLETE   nothing broke, but steps were not performed

INCOMPLETE returned 0 until 2026-07-31, which made a half-run
indistinguishable from a pass to anything reading the exit status.
"""

import hashlib
import json
import os
import re
import sys

import requests

API = "http://127.0.0.1:8000"
TRIP = "9538cd88-5c8b-4da4-b2a9-2a03f8db32a3"
PERSON = "a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2"
REPO = "/mnt/c/Users/chris/hornelore"
STATE = os.path.join(REPO, "docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_state.json")

# What the first verify ACCEPTED. Separate from STATE on purpose: STATE is
# the before picture and is overwritten by the next capture, while this is
# the evidence the restart is checked against and must survive it.
#
# Written only by a verify that had zero failures, because a restart check
# against a run that was already wrong proves the wrongness persisted.
ACCEPTED = os.path.join(
    REPO, "docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_accepted.json")
CONSOLE = os.path.join(
    REPO, "docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_%s.console.txt")

REQUIRED_GATES = (
    "trip_interview_context_enabled",
    "trip_story_capture_enabled",
    "trip_shelf_turn_link_enabled",
)

# Section E: "the response does not contain 'I can see', 'the image
# shows', or equivalent visual claims". Matched on the answer only, and
# reported as a count of hits, never as the sentence that hit.
VISUAL_CLAIMS = (
    r"\bi can see\b", r"\bi see\b(?! what you mean)", r"\bi\'?m looking at\b",
    r"\bi looked at\b", r"\bthe image shows\b", r"\bthe photo shows\b",
    r"\bthe picture shows\b", r"\bin the (?:image|photo|picture)\b",
    r"\bi can make out\b", r"\byou can see\b.{0,20}\bin (?:it|the photo)\b",
    r"\bi viewed\b", r"\bi can view\b", r"\bfrom what i can see\b",
)

# The exact wording from the work order, plus the variants it names.
# Two shapes, because the noun does not always follow the verb: "can you
# see ... photos" and "what photos do you have". One pattern that only
# looked forward from the verb missed the second, which is a variant the
# work order lists by name.
#
# Deliberately narrow. A false positive is worse than a miss here: it
# would run the photo-answer checks against the gravesite story and fail
# a turn that was never the photo turn. Merely saying the word photo is
# not asking this question.
# WIDENED 2026-08-01 after a live false negative. The operator asked
# "how many pictures can you see from this trip" and this pattern did not
# match, so a check that the PRODUCT passed was reported as not exercised.
# Two separate gaps, both in the harness and neither in the product:
#
#   * only the literal word "photo" was accepted -- "picture" was not;
#   * the verb phrase had to come BEFORE the media word, so
#     "<media> can you see" could not match while "can you see <media>"
#     could.
#
# Widened to a media-word alternation and to either order. Deliberately
# still requires an interrogative cue, so ordinary narration that merely
# mentions a photograph is not mistaken for the question.
_MEDIA = r"(?:photo(?:graph)?|picture|image|pic)s?"
_ASK = r"(?:can you (?:see|access|read|view)|do(?:es)? (?:this trip |you )?have|how many|what|which|are there|have you got)"

PHOTO_QUESTION = re.compile(
    # verb/interrogative first:  "can you see any photos", "what photos do you have"
    r"\b" + _ASK + r"\b.{0,40}\b" + _MEDIA + r"\b"
    # media first:               "how many pictures can you see"
    r"|\b" + _MEDIA + r"\b.{0,40}\b(?:can you (?:see|access|read|view)"
    r"|do you have|have you got|are there)\b",
    re.I | re.S)

NUM_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven",
             "eight", "nine", "ten", "eleven", "twelve")

LINES = []
PASS = [0]
FAIL = [0]
SKIP = [0]


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
    """The behaviour was exercised and must hold."""
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


def get(path):
    r = requests.get(API + path, timeout=30)
    r.raise_for_status()
    return r.json()


def h(s):
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------- turn correlation

# The story candidate has to be tied to the TURN THAT CAUSED IT, and the
# two tables do not share a key. trip_turn_links is keyed on committed
# `turns` row ids; a captured note carries source_ref='turn:<turn_id>',
# where turn_id is the chat_ws turn identifier and not a row id. Nothing
# joins them.
#
# What does join them is the narrator's own sentence. The note stores
# trip_story_capture._light_clean(narrator_text) and the timeline reads
# the same turn back out of `turns`, so normalising both the same way
# identifies the exact turn. This mirrors that cleaner: collapse all
# whitespace, strip wrapping quotes, casefold. It compares; it never
# prints.
#
# The alternative -- "the one new Lori note" -- is what produced the
# 2026-07-31 ambiguous FAIL: a Travel Doc modal note written in the same
# window was graded as the shelf story candidate, and correctly having a
# Day 1 was reported as the defect.

_MODAL_SURFACE = "travel_doc_modal"
_TRUNCATION_MARK = " …"          # _light_clean's >4000-char suffix


def corr(s):
    """A comparable form of a narrator turn. Not for display."""
    s = str(s or "").replace("’", "'")
    s = re.sub(r"\s+", " ", s).strip()
    return s.strip('"“”').strip().casefold()


def same_turn(note_text, turn_text):
    """Did this note come from this turn?

    Equality after normalising, with one allowance: _light_clean caps
    the stored note at 4000 characters and marks the cut, so a long turn
    is a prefix rather than a match. A short note is never allowed to
    prefix-match a long turn -- that would let 'yes' match everything."""
    n, t = corr(note_text), corr(turn_text)
    if not n or not t:
        return False
    if n == t:
        return True
    if n.endswith(_TRUNCATION_MARK.strip()):
        head = n.rstrip(_TRUNCATION_MARK.strip() + " ").strip()
        return len(head) >= 200 and t.startswith(head)
    return False


def is_modal(note):
    """Two independent marks, because either alone can be absent.

    source_surface is NULL on rows written before migration 0024 added
    the column; source_ref's 'modal_turn:' prefix is written by
    trip_story_capture for every modal capture regardless."""
    return (str(note.get("surface") or "") == _MODAL_SURFACE
            or str(note.get("ref") or "").startswith("modal_turn:"))


def says_count(text, n):
    """Does the answer state this number, as a digit or as a word?

    Lori writes counts as words ("there are two photos attached"), so a
    digit-only check would fail a correct answer. Word-boundaried on
    both spellings; 'one' must not match 'someone'."""
    low = (text or "").lower()
    if re.search(r"\b%d\b" % int(n), low):
        return True
    if 0 <= int(n) < len(NUM_WORDS):
        return bool(re.search(r"\b%s\b" % NUM_WORDS[int(n)], low))
    return False


# ---------------------------------------------------------------- gates

def gates():
    """Booleans only. Straight from the process that serves the turn."""
    try:
        g = get("/api/trips/runtime-gates")
    except requests.RequestException:
        return None
    return dict((k, bool(v)) for k, v in g.items())


def print_gates(g):
    out("--- runtime gates (this server process) ---")
    out("trips_enabled=%s" % str(bool(g.get("trips_enabled"))).lower())
    for k in REQUIRED_GATES:
        out("%s=%s" % (k, str(bool(g.get(k))).lower()))
    out("")


# ------------------------------------------------------------ snapshot

def snapshot():
    """Everything the work order asks about, as ids, counts and hashes."""
    cal = get("/api/trips/%s/calendar" % TRIP)
    snap = {
        "live_state": cal.get("live_state"),
        "selected_day_id": cal.get("selected_day_id"),
        "day_ids": [d.get("id") for d in (cal.get("days") or [])]
                   + [d.get("id") for d in (cal.get("preserved") or [])],
        "convs": {},
        "notes": {},
        "photo_inventory": get("/api/trips/%s/photo-inventory" % TRIP),
        "family_truth_rows": 0,
    }

    def add_convs(items):
        for it in items or []:
            if it.get("kind") != "conversation":
                continue
            snap["convs"][str(it.get("link_id"))] = {
                "day": it.get("trip_day_id"),
                "src": it.get("placement_source"),
                "st": it.get("placement_status"),
                "u": it.get("user_turn_row_id"),
                "a": it.get("assistant_turn_row_id"),
                "nh": h(it.get("narrator_said")),
                "lh": h(it.get("lori_said")),
                # Kept out of the snapshot file: raw text is used live in
                # verify and never written down.
            }

    for did in list(snap["day_ids"]):
        if not did:
            continue
        add_convs(get("/api/trips/%s/days/%s/timeline"
                      % (TRIP, did)).get("items"))
    add_convs(get("/api/trips/%s/timeline/unplaced" % TRIP).get("items"))

    for n in get("/api/trips/%s/location-notes?include_hidden=1"
                 % TRIP).get("notes") or []:
        snap["notes"][str(n.get("id"))] = {
            "src": n.get("source_type"),
            "ref": n.get("source_ref"),
            # Which surface wrote it. The Travels shelf and the Travel
            # Doc modal both write source_type='lori' into this table,
            # so without this the two are indistinguishable and a modal
            # note can be graded as a shelf story. .get() rather than
            # [] because a pre-0024 database has no such column.
            "surface": n.get("source_surface"),
            "created": n.get("created_at"),
            "day": n.get("trip_day_id"),
            "memoir": int(n.get("include_in_memoir") or 0),
            "ctx": int(n.get("include_in_interview_context") or 0),
            "hidden": int(n.get("hidden") or 0),
            "th": h(n.get("note_text")),
        }

    try:
        ft = get("/api/family-truth/rows?person_id=%s&limit=5000" % PERSON)
        rows = ft.get("rows") if isinstance(ft, dict) else ft
        snap["family_truth_rows"] = len(rows or [])
    except requests.RequestException:
        snap["family_truth_rows"] = -1
    return snap


# ── BUG-DETERMINISTIC-TURN-ARCHIVE-MISSING-01 ────────────────────────
# Four-way outcome for the photo question, and the reason it exists.
#
# On 2026-08-01 this harness reported SKIP -- "the photo question was
# not asked" -- on a session where Chris HAD asked it and Lori HAD
# answered correctly in the browser. The harness was looking only at
# completed TRIP CONVERSATION LINKS, and the deterministic meta_question
# branch never created one (it discarded the persisted row id). So a
# real product defect appeared as an operator who had skipped a step,
# and I argued with the harness for two rounds instead of believing it.
#
# A check that can only say "found" or "not found" cannot tell those
# apart. This one reads three independent sources and reports which:
#
#   absent          the question is in no fresh user turn        -> SKIP
#   unanswered      user turn exists, no assistant turn          -> FAIL
#   archive_missing answered in `turns`, absent from the archive -> FAIL
#   present         in both -> run the count and visual-claim checks
#
# Still read-only. /api/session/turns and /api/memory-archive/session
# are both GETs.
def session_turn_evidence(conv_ids):
    """Raw turns and archive rows per session id. Never printed."""
    out = {}
    for cid in conv_ids:
        if not cid:
            continue
        turns, archive = [], []
        try:
            turns = get("/api/session/turns?conv_id=%s" % cid).get("turns") or []
        except Exception:
            turns = []
        try:
            archive = (get("/api/memory-archive/session/%s?person_id=%s"
                           % (cid, PERSON)).get("turns") or [])
        except Exception:
            # A 404 here means no archive directory for the session --
            # which is itself the archive_missing signal, not an error.
            archive = []
        out[cid] = {"turns": turns, "archive": archive}
    return out


def classify_photo_question(evidence):
    """absent | unanswered | archive_missing | present, plus the pair."""
    for cid, ev in (evidence or {}).items():
        rows = ev.get("turns") or []
        for i, row in enumerate(rows):
            if str(row.get("role") or "").lower() != "user":
                continue
            if not PHOTO_QUESTION.search(str(row.get("content") or "")):
                continue
            # The question is here. Is the next turn Lori answering it?
            nxt = rows[i + 1] if i + 1 < len(rows) else None
            if not nxt or str(nxt.get("role") or "").lower() != "assistant":
                return "unanswered", cid, str(row.get("content") or ""), ""
            answer = str(nxt.get("content") or "")
            # And did that answer reach the exported archive?
            in_archive = any(
                str(a.get("role") or "").lower() == "assistant"
                and str(a.get("content") or "").strip() == answer.strip()
                for a in (ev.get("archive") or []))
            if not in_archive:
                return "archive_missing", cid, str(row.get("content") or ""), answer
            return "present", cid, str(row.get("content") or ""), answer
    return "absent", "", "", ""


def live_conversations():
    """The same conversation rows, with the text still attached.

    verify needs the words to answer 'was it direct' and 'did it claim
    to see'. They are read here, used in memory, and never stored or
    printed."""
    cal = get("/api/trips/%s/calendar" % TRIP)
    ids = [d.get("id") for d in (cal.get("days") or [])]
    ids += [d.get("id") for d in (cal.get("preserved") or [])]
    rows = {}
    for did in ids:
        if did:
            for it in get("/api/trips/%s/days/%s/timeline"
                          % (TRIP, did)).get("items") or []:
                if it.get("kind") == "conversation":
                    rows[str(it.get("link_id"))] = it
    for it in get("/api/trips/%s/timeline/unplaced" % TRIP).get("items") or []:
        if it.get("kind") == "conversation":
            rows[str(it.get("link_id"))] = it
    return rows


def live_notes():
    """The same note rows, with the text still attached.

    verify needs the words to answer 'which turn did this note come
    from', for the same reason live_conversations() needs them. Read
    here, compared in memory, never stored and never printed."""
    rows = {}
    for n in get("/api/trips/%s/location-notes?include_hidden=1"
                 % TRIP).get("notes") or []:
        rows[str(n.get("id"))] = n
    return rows


def approved_and_unapproved_text():
    """Two buckets of photo words: what Lori may quote, and what she may
    not. Used only for containment tests against her answer."""
    approved, withheld = [], []
    for link in get("/api/trips/%s/photo-links?include_hidden=1"
                    % TRIP).get("photo_links") or []:
        cap = (link.get("caption") or "").strip()
        if not cap:
            continue
        if int(link.get("caption_approved_for_lori") or 0):
            approved.append(cap)
        else:
            withheld.append(cap)
    return approved, withheld


# ------------------------------------------------------------- capture

def do_capture(g, now):
    print_gates(g)
    missing = [k for k in REQUIRED_GATES if not g.get(k)]
    if missing:
        out("The walkthrough cannot prove anything with these off:")
        for k in missing:
            out("    %s" % k)
        out("Set them, restart the stack the way you normally do, and run")
        out("capture again. Nothing was written.")
        return 2

    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w", encoding="utf-8") as fh:
        json.dump(now, fh, indent=1)

    inv = now["photo_inventory"]
    out("=== WO-TRIP-NARRATOR-BRIDGE-01 BASELINE ===")
    out("")
    out("trip live_state:      %s" % now["live_state"])
    out("durable selected day: %s"
        % (now["selected_day_id"] or "none -- Priority 2 territory"))
    out("conversations on trip: %d   (%d with no day)"
        % (len(now["convs"]),
           sum(1 for v in now["convs"].values() if not v["day"])))
    out("lori story candidates: %d"
        % sum(1 for v in now["notes"].values() if v["src"] == "lori"))
    out("photos attached: %d   on a day: %d   cleared for Lori: %d"
        % (inv.get("attached", 0), inv.get("on_a_day", 0),
           inv.get("cleared_for_lori", 0)))
    out("family truth rows: %s"
        % ("unreadable" if now["family_truth_rows"] < 0
           else now["family_truth_rows"]))
    out("")
    out("Now do the narrator walkthrough:")
    out("  1. Open Chris.")
    out("  2. Open Bismarck Trip from Travels.")
    out("  3. Tell the gravesite / schools / Melanie story.")
    out("  4. Ask: can you see any of the photos I added to my trip?")
    out("  5. Close the narrator session normally.")
    out("Then run verify. Then restart the way you normally do, and run")
    out("verify again -- the second run is the persistence check.")
    out("")
    out("baseline state: %s" % STATE)
    return 0


# -------------------------------------------------------------- verify

def do_verify(g, now):
    print_gates(g)
    for k in REQUIRED_GATES:
        check(bool(g.get(k)), "gate %s was on for this run" % k)

    if not os.path.exists(STATE):
        out("No baseline at %s -- run 'capture' first." % STATE)
        return 2
    with open(STATE, encoding="utf-8") as fh:
        old = json.load(fh)

    out("")
    out("=== WO-TRIP-NARRATOR-BRIDGE-01 VERIFY ===")
    out("")

    fresh = [k for k in now["convs"] if k not in old["convs"]]

    # -- C: the shelf must not promote a finished trip back to live
    check(now["live_state"] == old["live_state"],
          "trip live_state unchanged by the narrator session (%s)"
          % now["live_state"])

    # -- E: both interactions persisted, and each is on the trip once
    if not fresh:
        skip("no new trip conversation -- the walkthrough was not done "
             "(or nothing reached the trip)")
    else:
        out("      (%d new trip conversation(s))" % len(fresh))
        check(len(fresh) >= 2,
              "both completed narrator interactions persisted (%d)"
              % len(fresh))
        turns = [now["convs"][k]["a"] for k in fresh]
        check(len(set(turns)) == len(turns),
              "each assistant turn is linked to the trip exactly once")

        # -- C: placement obeys the priority rules, or it is Needs a day
        for k in fresh:
            v = now["convs"][k]
            if v["day"]:
                ok = (v["day"] in now["day_ids"]
                      and v["src"] == "active_trip_day"
                      and v["st"] == "confirmed")
                check(ok, "conversation %s placed on a real day of this trip "
                          "as a confirmed durable placement" % k[:8])
            else:
                ok = (v["src"] == "travels_shelf_trip"
                      and v["st"] == "needs_day")
                check(ok, "conversation %s recorded as Needs a day from the "
                          "Travels shelf (%s/%s)" % (k[:8], v["src"], v["st"]))

        # -- E: nothing already on the trip was rewritten
        moved = [k for k in old["convs"]
                 if k in now["convs"]
                 and (now["convs"][k]["nh"] != old["convs"][k]["nh"]
                      or now["convs"][k]["lh"] != old["convs"][k]["lh"])]
        check(not moved,
              "no existing transcript changed (n=%d)" % len(moved))

    # -- D: the story candidate, once, review-only, correlated
    #
    # Graded against THE SHELF STORY TURN, not against every new Lori
    # note in the window. Both surfaces write source_type='lori' into
    # trip_location_notes, so a Travel Doc modal note opened during the
    # same window used to be picked up as the shelf story -- and a modal
    # note is correctly day-scoped, so the harness reported a correct
    # row as a placement defect. An unrelated modal note is now named
    # and ignored, which is the only honest thing to do with it: it is
    # not this run's evidence and it is not this run's failure.
    rows = live_conversations()
    notes_live = live_notes()
    new_notes = [k for k in now["notes"] if k not in old["notes"]]
    new_lori = [k for k in new_notes if now["notes"][k]["src"] == "lori"]

    modal_new = [k for k in new_lori if is_modal(now["notes"][k])]
    if modal_new:
        out("      (%d new Travel Doc modal note(s) -- another surface, "
            "not this run's evidence: %s)"
            % (len(modal_new), ", ".join(k[:8] for k in modal_new)))

    shelf_new = [k for k in new_lori if not is_modal(now["notes"][k])]

    # Correlate by the narrator's own sentence: the note stores a light
    # clean of the turn, the timeline reads the turn back out of `turns`.
    story = []
    for k in shelf_new:
        text = (notes_live.get(k) or {}).get("note_text")
        src = [c for c in fresh
               if same_turn(text, rows.get(c, {}).get("narrator_said"))]
        if src:
            story.append((k, src))

    if not fresh:
        skip("no shelf conversation to correlate a story candidate to -- "
             "the walkthrough was not done")
    elif not shelf_new:
        skip("no new shelf story candidate -- step 3 not done, or the lane "
             "declined the turn (check /api/trips/capture-status)")
    elif not story:
        # Present but unattributable. Not a pass and not a placement
        # failure: nothing here shows it came from the graded turn.
        skip("%d new shelf candidate(s) matched no new shelf turn -- not "
             "correlated, so not graded (%s)"
             % (len(shelf_new), ", ".join(k[:8] for k in shelf_new)))
    else:
        for k, src in story:
            check(len(src) == 1,
                  "candidate %s traces to exactly one shelf turn (%d)"
                  % (k[:8], len(src)))
        turns_covered = [c for _, src in story for c in src]
        check(len(set(turns_covered)) == len(turns_covered),
              "the story was captured once, not twice (%d candidate(s) "
              "over %d turn(s))" % (len(story), len(set(turns_covered))))
        refs = [now["notes"][k]["ref"] for k, _ in story]
        check(len(set(refs)) == len(refs),
              "no two candidates share a source turn")

        for k, src in story:
            n = now["notes"][k]
            conv = rows.get(src[0], {})
            out("      (candidate %s <- shelf turn %s, %s/%s)"
                % (k[:8], src[0][:8], conv.get("placement_source"),
                   conv.get("placement_status")))
            check(n["memoir"] == 0 and n["ctx"] == 0 and n["hidden"] == 0,
                  "candidate %s is review-only: memoir=%d context=%d "
                  "hidden=%d" % (k[:8], n["memoir"], n["ctx"], n["hidden"]))

            # The day rule, stated as the product rule rather than as a
            # single assertion whose failure message reads like a claim
            # that it held. A durable day exists only while the narrator
            # is genuinely living in this trip; a completed trip opened
            # from the shelf must get NULL, never an inferred day.
            durable = (now["selected_day_id"]
                       if (now["live_state"] == "active"
                           and now["selected_day_id"] in now["day_ids"])
                       else None)
            if durable:
                check(n["day"] == durable,
                      "candidate %s carries the durable selected day "
                      "(day=%s expected=%s)"
                      % (k[:8], (n["day"] or "none")[:8], durable[:8]))
            else:
                check(not n["day"],
                      "candidate %s has no inferred day, because this trip "
                      "has no durable selected day (live_state=%s day=%s)"
                      % (k[:8], now["live_state"], (n["day"] or "none")[:8]))

    # -- B: the photo answer ----------------------------------------
    # Four-way, not two. See classify_photo_question() for why: on
    # 2026-08-01 a two-way check reported SKIP on a session where the
    # question WAS asked and answered, because the answer never became a
    # trip conversation link. "Not found here" and "did not happen" are
    # different facts and must not share an outcome.
    _sessions = sorted({(rows.get(k) or {}).get("session_id")
                        or (rows.get(k) or {}).get("conv_id")
                        for k in fresh} - {None, ""})
    _verdict, _cid, _q, _a = "absent", "", "", ""
    try:
        _verdict, _cid, _q, _a = classify_photo_question(
            session_turn_evidence(_sessions))
    except Exception as _cls_exc:
        out("      (photo-question classification failed: %s)"
            % _cls_exc.__class__.__name__)

    if _verdict == "absent":
        skip("the photo question was not asked -- step 4 not done")
        for k in fresh:
            said = rows.get(k, {}).get("narrator_said")
            out("      (conv %s: narrator_said %s, %d word(s), match=%s)"
                % (k[:8],
                   "absent" if said is None else
                   ("empty" if not str(said).strip() else "present"),
                   len(str(said or "").split()),
                   bool(said and PHOTO_QUESTION.search(str(said)))))
        out("      (sessions inspected: %d)" % len(_sessions))
    elif _verdict == "unanswered":
        check(False,
              "the photo question was asked but Lori never answered it "
              "(session %s: a user turn with no assistant turn after it)"
              % _cid[:12])
    elif _verdict == "archive_missing":
        # THE 2026-08-01 DEFECT, named. Answered in `turns`, absent from
        # the exported archive -- so the browser showed it and the
        # transcript did not.
        check(False,
              "photo_question_archive_missing: Lori answered (%d chars, "
              "sha %s) but the reply is NOT in the exported archive "
              "transcript for session %s" % (len(_a), h(_a), _cid[:12]))
    else:
        approved, withheld = approved_and_unapproved_text()
        inv = now["photo_inventory"]
        out("      (answer in session %s, %d chars, sha %s -- present in "
            "both `turns` and the archive)" % (_cid[:12], len(_a), h(_a)))
        hits = [pat for pat in VISUAL_CLAIMS if re.search(pat, _a, re.I)]
        check(not hits,
              "the answer makes no visual claim (%d matched pattern(s))"
              % len(hits))
        check(bool(_a.strip()) and not _a.strip().endswith("?"),
              "the answer does not answer the question with a question")
        check(says_count(_a, inv.get("attached", 0)),
              "the answer states the real photo count (%d attached)"
              % inv.get("attached", 0))
        leaked = [c for c in withheld if c and c.lower() in _a.lower()]
        check(not leaked,
              "the answer quotes no unapproved caption (%d of %d withheld "
              "captions appear)" % (len(leaked), len(withheld)))
        if approved:
            out("      (%d approved caption(s) were available to quote)"
                % len(approved))

    # -- E: the capture lane logged something it can name
    try:
        st = get("/api/trips/capture-status")
        reason = str(((st.get("last") or {}).get("reason")) or "")
        if not reason:
            skip("the capture lane has no last result to report")
        else:
            check(reason != "error",
                  "capture lane reported a named reason, not a generic "
                  "error (%s)" % reason)
    except requests.RequestException:
        skip("capture-status unreadable")

    # -- E: no family truth was written
    if now["family_truth_rows"] < 0 or old["family_truth_rows"] < 0:
        skip("family truth row count unreadable -- not proven")
    else:
        check(now["family_truth_rows"] == old["family_truth_rows"],
              "no family truth was written (%d -> %d)"
              % (old["family_truth_rows"], now["family_truth_rows"]))

    # -- record what this run accepted, for the restart check
    if not FAIL[0]:
        out("")
        if _write_accepted(now, fresh, story):
            out("accepted record: %s" % ACCEPTED)
            out("(restart the way you normally do, then run restart-verify)")

    out("")
    out("=== %d passed, %d failed, %d not exercised ==="
        % (PASS[0], FAIL[0], SKIP[0]))
    if FAIL[0]:
        out("RESULT: FAIL -- a check that was exercised did not hold.")
        return 1
    if SKIP[0]:
        out("RESULT: INCOMPLETE -- nothing is broken, but the steps above")
        out("        were not performed, so those behaviours are still")
        out("        unproven. Redo the walkthrough and re-run.")
        # Exit 3, not 0. An unproven run is not a successful one, and a
        # shell that reads `&&` cannot tell the difference between "the
        # acceptance passed" and "half of it never ran" if both are 0.
        return 3
    out("RESULT: PASS -- WO-TRIP-NARRATOR-BRIDGE-01 acceptance met.")
    return 0


# -------------------------------------------------- restart-verify

def _write_accepted(now, fresh, story):
    """Freeze what this verify accepted, so the restart has something to
    be checked AGAINST rather than merely re-run.

    Re-running verify after a restart does prove the rows survived, but
    it cannot prove they are the SAME rows: it compares against the
    pre-walkthrough baseline, which knows nothing about what the
    walkthrough produced. 'No duplicate appeared' and 'the identical
    link id is still there' are different claims, and the work order
    asks for the second one."""
    rec = {
        "live_state": now["live_state"],
        "trip_conversations_total": len(now["convs"]),
        "lori_notes_total": sum(1 for v in now["notes"].values()
                                if v["src"] == "lori"),
        "convs": dict((k, now["convs"][k]) for k in fresh),
        "candidates": dict(
            (k, {"note": now["notes"][k], "turns": src})
            for k, src in story),
    }
    # Bookkeeping must never void a verdict. Every check has already run
    # and held by the time this is called; an unwritable path is a fact
    # about the disk, not about the trip, and turning it into a traceback
    # would throw away a good run's evidence at the last step.
    try:
        os.makedirs(os.path.dirname(ACCEPTED), exist_ok=True)
        with open(ACCEPTED, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, indent=1)
        return True
    except OSError as exc:
        out("      (could not write the accepted record: %s -- the restart "
            "check will have nothing to compare against)"
            % exc.__class__.__name__)
        return False


def do_restart_verify(g, now):
    """The persistence check, against the ids the first verify accepted."""
    print_gates(g)
    for k in REQUIRED_GATES:
        check(bool(g.get(k)), "gate %s is still on after the restart" % k)

    if not os.path.exists(ACCEPTED):
        out("No accepted record at %s" % ACCEPTED)
        out("Run the walkthrough and 'verify' first; a verify with no")
        out("failures writes the record this mode checks against.")
        return 2
    with open(ACCEPTED, encoding="utf-8") as fh:
        acc = json.load(fh)

    out("")
    out("=== WO-TRIP-NARRATOR-BRIDGE-01 RESTART-VERIFY ===")
    out("")

    check(now["live_state"] == acc["live_state"],
          "trip live_state survived the restart (%s)" % now["live_state"])

    if not acc["convs"]:
        skip("the accepted run linked no conversation -- nothing to "
             "re-check")
    for k, was in acc["convs"].items():
        v = now["convs"].get(k)
        if v is None:
            check(False, "conversation %s is still on the trip after the "
                         "restart" % k[:8])
            continue
        check(True, "conversation %s is still on the trip" % k[:8])
        check(v["u"] == was["u"] and v["a"] == was["a"],
              "conversation %s still points at the same turn rows "
              "(u=%s a=%s)" % (k[:8], v["u"], v["a"]))
        # The transcript is the thing a family reads. If a restart can
        # change it, nothing else here matters.
        check(v["nh"] == was["nh"] and v["lh"] == was["lh"],
              "conversation %s transcript is byte-identical" % k[:8])
        check(v["src"] == was["src"] and v["st"] == was["st"]
              and v["day"] == was["day"],
              "conversation %s placement unchanged (%s/%s day=%s)"
              % (k[:8], v["src"], v["st"], (v["day"] or "none")))

    # Duplicates. A replayed hook would add a row, not change one, so the
    # per-link checks above cannot see it -- only the totals can.
    check(len(now["convs"]) == acc["trip_conversations_total"],
          "no conversation was duplicated by the restart (%d -> %d)"
          % (acc["trip_conversations_total"], len(now["convs"])))
    arows = [v["a"] for v in now["convs"].values()]
    check(len(set(arows)) == len(arows),
          "each assistant turn is still linked exactly once")

    lori_now = sum(1 for v in now["notes"].values() if v["src"] == "lori")
    check(lori_now == acc["lori_notes_total"],
          "no story candidate was duplicated by the restart (%d -> %d)"
          % (acc["lori_notes_total"], lori_now))

    if not acc["candidates"]:
        skip("the accepted run captured no story candidate -- nothing to "
             "re-check")
    for k, was in acc["candidates"].items():
        n = now["notes"].get(k)
        if n is None:
            check(False, "candidate %s still exists after the restart"
                  % k[:8])
            continue
        check(True, "candidate %s still exists" % k[:8])
        w = was["note"]
        check(n["day"] == w["day"],
              "candidate %s still sits where it did (day=%s)"
              % (k[:8], (n["day"] or "none")))
        check(n["memoir"] == 0 and n["ctx"] == 0 and n["hidden"] == 0,
              "candidate %s is still review-only: memoir=%d context=%d "
              "hidden=%d" % (k[:8], n["memoir"], n["ctx"], n["hidden"]))
        check(n["th"] == w["th"],
              "candidate %s text is byte-identical" % k[:8])

    out("")
    out("=== %d passed, %d failed, %d not exercised ==="
        % (PASS[0], FAIL[0], SKIP[0]))
    if FAIL[0]:
        out("RESULT: FAIL -- the restart did not preserve the evidence.")
        return 1
    if SKIP[0]:
        out("RESULT: INCOMPLETE -- what was recorded survived, but the")
        out("        accepted run did not exercise everything.")
        return 3
    out("RESULT: PASS -- the evidence survived a real restart.")
    return 0


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("preflight", "capture", "verify", "restart-verify"):
        print(__doc__)
        return 2
    g = gates()
    if g is None:
        print("Could not reach the API at %s -- is the stack up?" % API)
        return 2
    if mode == "preflight":
        print_gates(g)
        missing = [k for k in REQUIRED_GATES if not g.get(k)]
        for k in REQUIRED_GATES:
            check(bool(g.get(k)), "gate %s is on" % k)
        out("")
        if missing:
            out("RESULT: FAIL -- the acceptance run needs all three on.")
            out("        Set them in .env, then restart the stack the way")
            out("        you normally do. This script will not touch it.")
        else:
            out("RESULT: PASS -- the process is ready for the walkthrough.")
        flush(mode)
        return 1 if missing else 0
    try:
        now = snapshot()
    except requests.RequestException as exc:
        print("Could not read the trip from %s" % API)
        print("  %s" % exc)
        return 2
    if mode == "capture":
        rc = do_capture(g, now)
    elif mode == "restart-verify":
        rc = do_restart_verify(g, now)
    else:
        rc = do_verify(g, now)
    flush(mode)
    return rc


if __name__ == "__main__":
    sys.exit(main())
