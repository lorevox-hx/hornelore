#!/usr/bin/env python3
"""WO-TRIP-NARRATOR-BRIDGE-01 acceptance check (read-only).

    ./scripts/wo_narrator_bridge_acceptance.py preflight
    ./scripts/wo_narrator_bridge_acceptance.py capture   # before the walkthrough
    ./scripts/wo_narrator_bridge_acceptance.py verify    # after it, and again
                                                         # after the restart

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
PHOTO_QUESTION = re.compile(
    r"\b(?:can you (?:see|access|read|view)|do(?:es)? (?:this trip |you )?"
    r"have)\b.{0,40}\bphoto"
    r"|\bwhat photos?\b.{0,40}\b(?:do you have|have you got|are there)\b",
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

    # -- D: the story candidate, once, review-only
    new_notes = [k for k in now["notes"] if k not in old["notes"]]
    lori_notes = [k for k in new_notes if now["notes"][k]["src"] == "lori"]
    if not lori_notes:
        skip("no new lori story candidate -- step 3 not done, or the lane "
             "declined the turn (check /api/trips/capture-status)")
    else:
        check(len(lori_notes) == 1,
              "the story was captured once, not twice (%d)" % len(lori_notes))
        refs = [now["notes"][k]["ref"] for k in lori_notes]
        check(len(set(refs)) == len(refs),
              "no two candidates share a source turn")
        for k in lori_notes:
            n = now["notes"][k]
            check(n["memoir"] == 0 and n["ctx"] == 0 and n["hidden"] == 0,
                  "candidate %s is review-only: memoir=%d context=%d "
                  "hidden=%d" % (k[:8], n["memoir"], n["ctx"], n["hidden"]))
            if n["day"]:
                check(n["day"] == now["selected_day_id"]
                      and n["day"] in now["day_ids"],
                      "candidate %s sits on the durable selected day" % k[:8])
            else:
                check(now["selected_day_id"] is None
                      or now["live_state"] != "active",
                      "candidate %s has no day, and no valid durable day "
                      "existed to give it" % k[:8])

    # -- B: the photo answer
    rows = live_conversations()
    asked = [k for k in fresh
             if PHOTO_QUESTION.search(rows.get(k, {}).get("narrator_said")
                                      or "")]
    if not asked:
        skip("the photo question was not asked -- step 4 not done")
    else:
        approved, withheld = approved_and_unapproved_text()
        inv = now["photo_inventory"]
        for k in asked:
            ans = rows[k].get("lori_said") or ""
            out("      (answer %s, %d chars, sha %s)"
                % (k[:8], len(ans), h(ans)))
            hits = [p for p in VISUAL_CLAIMS
                    if re.search(p, ans, re.I)]
            check(not hits,
                  "answer %s makes no visual claim (%d matched pattern(s))"
                  % (k[:8], len(hits)))
            check(bool(ans.strip()) and not ans.strip().endswith("?"),
                  "answer %s does not answer the question with a question"
                  % k[:8])
            check(says_count(ans, inv.get("attached", 0)),
                  "answer %s states the real photo count (%d attached)"
                  % (k[:8], inv.get("attached", 0)))
            leaked = [c for c in withheld if c and c.lower() in ans.lower()]
            check(not leaked,
                  "answer %s quotes no unapproved caption (%d of %d withheld "
                  "captions appear)" % (k[:8], len(leaked), len(withheld)))
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
        return 0
    out("RESULT: PASS -- WO-TRIP-NARRATOR-BRIDGE-01 acceptance met.")
    return 0


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("preflight", "capture", "verify"):
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
    rc = do_capture(g, now) if mode == "capture" else do_verify(g, now)
    flush(mode)
    return rc


if __name__ == "__main__":
    sys.exit(main())
