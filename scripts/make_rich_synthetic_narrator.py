#!/usr/bin/env python3
"""A synthetic narrator with a MATURE biography. Fictional throughout.

    cd /mnt/c/Users/chris/hornelore
    .venv-gpu/bin/python scripts/make_rich_synthetic_narrator.py --create
    .venv-gpu/bin/python scripts/make_rich_synthetic_narrator.py --inspect

WHY THIS EXISTS
===============
`ZZ WALKTHROUGH 20260917` holds 1,444 bytes. Its turns ran at 7,285-7,541
of 8,192 tokens with every section kept and nothing shed. The turn of
Chris's that actually failed ran at 8,187 with `memory_context` dropped
and FOUR conversation turns gone.

So ZZ establishes that retrieval works when there is room. It cannot
establish that it works when there is not, and the note already in
`questionnaire_for_lori.py` says what happens when that distinction is
ignored:

    yesterday's walkthrough against a 1,287-byte synthetic record
    passed and told us nothing.

This fixture exists so the answering claims are tested against the
condition that broke: a substantial biography competing with
instructions and conversation for a fixed budget.

WHAT IT DELIBERATELY DOES NOT CONTAIN
=====================================
Life Map content. Measured 2026-09-21: `life_map` appears zero times in
`prompt_composer.py` and zero times in the chat_ws prompt path. The
Life Map contributes the selected ERA LABEL through runtime71 and
nothing else — both surfaces read the same projections, and only one of
them is in the prompt. Loading the fixture with Life Map material would
simulate budget pressure that does not exist.

WHAT IT EXERCISES, AND WHY EACH PIECE IS THERE
==============================================
  SIBLINGS, POPULATED      "and my dad and siblings" was answered about
                           the father alone. ZZ has no siblings section,
                           so the failure could not be reproduced there.
  LONG notableLifeEvents   Asked for notable life events, Lori returned
                           an occupation. Long prose lives in the
                           on-demand detail block; the compact block
                           carries the short facts. This fixture makes
                           the two separable.
  MANY RELATIVES           Retrieval has to CHOOSE. With four entries it
                           can succeed by accident.
  MIXED PROVENANCE         "Did I tell you that, or is it in my
                           biography?" is only a real question when the
                           answer differs by field. Written through the
                           operator-entry and narrator-answer routes, so
                           the provenance is genuine rather than a value
                           typed into a column.
  NO SEEDED CONVERSATION   Pronoun and source follow-ups are tested by
                           HAVING the conversation, in order. A seeded
                           transcript would prove the seeding worked.

WRITTEN THROUGH THE REAL ROUTES
===============================
`POST /api/people` for the narrator, `PUT /api/bio-builder/questionnaire`
for the bulk, then the operator-entry and narrator-answer routes for the
fields whose provenance matters. No direct database writes: the live DB
is held by the running stack, and a fixture built by a path the product
does not use would prove the fixture, not the product.

`testing_only=True`, so the Guard Lab gate can reach it and no real
narrator is involved. It touches nobody else's record.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"

# ── The invented family ──────────────────────────────────────────────
# ONE definition, in `tests/harness/rich_narrator.py`. It is imported
# rather than duplicated here: a fixture with two copies stays equal
# exactly until the first change, and this repository has already paid
# for that with a renderer/predicate pair and a baseline inventory
# beside its registry.
# Loaded BY PATH, not by package name. `tests/harness/` has no
# `__init__.py`, so `from harness.rich_narrator import ...` depends on
# namespace-package resolution and on nothing else called `harness`
# appearing earlier on sys.path. It failed exactly that way on the first
# run. The file is at a known location relative to this script; loading
# it directly removes the guesswork.
import importlib.util as _ilu
import os as _os

_FIXTURE = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "tests", "harness", "rich_narrator.py")
if not _os.path.isfile(_FIXTURE):
    raise SystemExit("fixture not found: %s" % _FIXTURE)
_spec = _ilu.spec_from_file_location("rich_narrator", _FIXTURE)
_fix = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fix)

DISPLAY_NAME = _fix.DISPLAY_NAME
QUESTIONNAIRE = _fix.QUESTIONNAIRE
PROVENANCE = _fix.PROVENANCE


def _post(path, payload):
    req = urllib.request.Request(
        API + path, method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def _put(path, payload):
    req = urllib.request.Request(
        API + path, method="PUT",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def _get(path):
    with urllib.request.urlopen(API + path, timeout=30) as r:
        return json.loads(r.read().decode() or "{}")


def _find_existing():
    try:
        people = _get("/api/people?limit=200")
    except Exception:
        return None
    rows = people.get("people") if isinstance(people, dict) else people
    for p in (rows or []):
        if str(p.get("display_name", "")).strip() == DISPLAY_NAME:
            return p.get("id")
    return None


def cmd_create(args):
    existing = _find_existing()
    if existing and not args.recreate:
        print("Already exists: %s" % existing)
        print("Nothing written. Pass --recreate to build a second one.")
        return 0

    person = _post("/api/people", {
        "display_name": DISPLAY_NAME,
        "date_of_birth": "1951-04-02",
        "place_of_birth": "Hallow Bridge",
        "narrator_type": "live",
        "testing_only": True,
    })
    pid = (person.get("person") or person).get("id")
    print("created narrator:", pid)

    _put("/api/bio-builder/questionnaire",
         {"person_id": pid, "questionnaire": QUESTIONNAIRE,
          "source": "ui_save"})
    print("wrote questionnaire: %d bytes" % len(json.dumps(QUESTIONNAIRE)))

    for section, field, value, who in PROVENANCE:
        route = ("/api/bio-builder/questionnaire/answer" if who == "operator"
                 else "/api/bio-builder/questionnaire/narrator-answer")
        body = {"person_id": pid, "questionnaire": QUESTIONNAIRE,
                "sections": [section], "source": "ui_save"}
        if who == "narrator":
            body["original_text"] = value
        try:
            _post(route, body)
            print("  provenance %-9s %s.%s" % (who, section, field))
        except urllib.error.HTTPError as e:
            print("  provenance %-9s %s.%s FAILED %s: %s"
                  % (who, section, field, e.code,
                     e.read().decode()[:160]))

    cmd_inspect(args)
    return 0


def cmd_inspect(args):
    pid = _find_existing()
    if not pid:
        print("not found: %r" % DISPLAY_NAME)
        return 2
    q = _get("/api/bio-builder/questionnaire?person_id=%s" % pid)
    blob = json.dumps(q.get("questionnaire") or {})
    print("\n=== %s ===" % DISPLAY_NAME)
    print("  person_id       :", pid)
    print("  questionnaire   : %d bytes  (ZZ WALKTHROUGH = 1,444)" % len(blob))
    for sec, val in (q.get("questionnaire") or {}).items():
        n = len(val) if isinstance(val, list) else 1
        print("    %-16s %d entr%s  %d bytes"
              % (sec, n, "y" if n == 1 else "ies", len(json.dumps(val))))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--create", action="store_true")
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--recreate", action="store_true",
                    help="build another even if one exists")
    ap.add_argument("--api", default=API)
    args = ap.parse_args()
    globals()["API"] = args.api
    if args.create:
        return cmd_create(args)
    if args.inspect:
        return cmd_inspect(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
