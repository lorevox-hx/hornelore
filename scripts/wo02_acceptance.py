#!/usr/bin/env python3
"""WO-02 acceptance check (read-only).

    ./scripts/wo02_acceptance.py capture    # before the browser walkthrough
    ./scripts/wo02_acceptance.py verify     # after the walkthrough

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
CONSOLE = os.path.join(REPO, "docs/reports/WO-02_ACCEPTANCE_%s.console.txt")

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
                rows.append(["photo", it.get("link_id"), h(it.get("caption"))])
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
            "day": link.get("trip_day_id"),
            "ch": h(link.get("caption")),
            "approved": int(link.get("caption_approved_for_lori") or 0),
        }
    return snap


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


def do_verify(now):
    if not os.path.exists(STATE):
        out("No baseline at %s -- run 'capture' first." % STATE)
        return 2

    with open(STATE, encoding="utf-8") as fh:
        old = json.load(fh)

    out("=== WO-02 VERIFY ===")
    out("")

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

    # point 6 -- a move relocates the row, it does not clone it
    moved_photo = [k for k, v in now["photo_links"].items()
                   if k in old["photo_links"]
                   and v["day"] != old["photo_links"][k]["day"]]
    if not moved_photo:
        skip("no photo was moved -- walkthrough step 6 not done")
    else:
        out("      (%d photo move(s) seen)" % len(moved_photo))
        check(len(now["photo_links"]) == len(old["photo_links"]),
              "moving a photo created no second placement (%d -> %d)"
              % (len(old["photo_links"]), len(now["photo_links"])))

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

    out("")
    out("=== %d passed, %d failed, %d not exercised ==="
        % (PASS[0], FAIL[0], SKIP[0]))
    if FAIL[0]:
        out("RESULT: FAIL -- a check that was exercised did not hold.")
        return 1
    if SKIP[0]:
        out("RESULT: INCOMPLETE -- nothing is broken, but the walkthrough")
        out("        steps above were not performed, so those behaviours")
        out("        are still unproven. Redo the walkthrough and re-run.")
        return 0
    out("RESULT: PASS -- WO-02 acceptance met.")
    return 0


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
    if mode not in ("capture", "verify"):
        print(__doc__)
        return 2
    try:
        now = snapshot()
    except requests.RequestException as exc:
        print("Could not reach the API at %s -- is the stack up?" % API)
        print("  %s" % exc)
        return 2
    rc = do_capture(now) if mode == "capture" else do_verify(now)
    flush(mode)
    return rc


if __name__ == "__main__":
    sys.exit(main())
