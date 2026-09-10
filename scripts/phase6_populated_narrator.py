#!/usr/bin/env python3
"""Phase 6 — create the POPULATED synthetic conversational narrator.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv-gpu/bin/python \
        scripts/phase6_populated_narrator.py --check
    PYTHONPATH=server/code .venv-gpu/bin/python \
        scripts/phase6_populated_narrator.py --create

WHY A SECOND TEST NARRATOR. `Guard Lab Test Narrator` stays exactly as it
is — the INSTRUMENTATION narrator, deliberately empty, used to prove the
control plane works. It is the wrong narrator for judging Lori.

Both lean turns on 2026-09-07 were confounded by that emptiness: Profile
Seed sat at 0/10, the session banner read `Narrator record incomplete`,
and Lori asked "What was your name during that time?" and then "What was
your mother's maiden name?" — two identity questions in two turns. Any
conversational verdict drawn from those measures the empty record, not
the lean configuration.

WHAT THIS SCRIPT REFUSES TO ASSUME
==================================

It does not hope the profile is "full enough", and it does not settle for
the topic predicate either. **It runs the shipped decision.**

`profile_seed_turn.plan_turn` is what actually decides whether Lori raises
an onboarding question on a turn, and the deciding line is:

    profile_seed_turn.py:620   if state.get("status") != _seed.STATUS_ACTIVE:
                                   return TurnPlan(IDLE)

So `--check` resolves the narrator through the shipped resolver
(`profile_seed.resolve_effective`, line 899 — read-only, no version bump)
and feeds that state to the shipped `plan_turn`. **`IDLE` is the pass
condition.** Ten green topic rows with a status this gate still reads as
`active` would reproduce the exact confound the narrator exists to remove,
and only the second check would catch it.

VERIFIED BEFORE WRITING, NOT ASSUMED
====================================

  * `has_value(False) -> True` — `profile_seed.py:512`, `isinstance(value,
    bool)` returns True before the numeric and string branches. So
    `military.served: False` is an ANSWER ("I did not serve"), not a gap.
    The whole military topic depends on this and it was worth reading.
  * `parents_work` has `profile_paths=()` DELIBERATELY (line 282): a
    `parents` list of bare names is not evidence about their work.
    `_parents_have_work()` (line 643) requires an `occupation` / `work` /
    `job` key on an entry, so every parent below carries one.
  * `life_stage` reads `community.retirementStatus` ONLY (line 367) — a
    date of birth is arithmetic, not an answer.
  * `childhood_home` reads no birthplace path (line 254) — `placeOfBirth`
    does not answer where someone grew up.
  * `_load_profile_root` (line 543) unwraps `blob["profile"]` when that
    key holds a mapping, otherwise treats the blob as flat.
    `db.ensure_profile` inserts a flat `"{}"` (db.py:2917), so a fresh
    narrator is flat — but `--create` REFUSES on a pre-existing wrapped
    blob rather than writing keys the reader would never look at.
  * `db.update_profile_json` merges at the TOP LEVEL only (db.py:2934,
    `merged.update(...)`), so each top-level key below replaces rather
    than deep-merges. That is what we want for a fresh narrator.

IT MUST WRITE TO THE DATABASE THE SERVER IS SERVING
===================================================

**This script created Ada in the wrong database on its first run**, and
the failure was silent in the worst way: every check passed. Ten topics
answered, `plan_turn` IDLE, `PASS` — all true, and all about a narrator
the running product could not see. `GET /api/people/<id>` returned 404.

`db.py:58` resolves `DATA_DIR` from the process environment, defaulting
to a repo-relative `data/`, and `db.py:62` defaults `DB_NAME` to
`lorevox.sqlite3`. The SERVER runs with `.env` loaded
(`DATA_DIR=/mnt/c/hornelore_data`, `DB_NAME=hornelore.sqlite3`); this
script ran with neither set, so `init_db()` cheerfully CREATED a second,
empty database inside the repo and populated it.

Two corrections, both here:

  * `_load_env()` reads the same two keys out of `.env` before `api.db`
    is imported — which is what `guard_lab_live_acceptance._db_path()`
    already does, and its docstring says why: "resolved exactly as the
    server resolves it". **`.env` WINS over an exported value**, because
    `scripts/common.sh:26-29` sources it under `set -a`. *(This bullet
    said the opposite — "a process-supplied value still wins, matching
    the server's own precedence" — until 2026-09-09, and the wrong
    sentence is what made the failure below look impossible.)*
  * `--create` REFUSES when the resolved database file does not already
    exist. **That guard is necessary and NOT sufficient, proven
    2026-09-09.** A stale `/home/chris/lorevox_data/db/lorevox.sqlite3`
    left in a WSL profile already existed, so the refusal passed and
    Ada was created in a database nothing serves — a second time, by a
    different route. Existence was never the property worth checking.
    **The only check that caught it both times was asking the running
    product:** `GET /api/operator/guard-lab/narrators` returned
    `count: 0` while the script printed PASS.

The resolved path is PRINTED on every run, so the destination is visible
rather than assumed.

SAFETY
======
  * `testing_only=True`, passed to `create_person` (db.py:2457) — the only
    place it can be set, never granted afterwards, and no write partner
    exists to convert a real narrator later (db.py:2852).
  * Wholly synthetic. No Horne-family material and no real narrator's
    biography. Kent, Janice, Walt, John and Del are untouched.
  * `--create` performs the only writes. `--check` is read-only.
  * A second `--create` finds the existing narrator by name and
    re-verifies instead of creating a sibling.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))


def _load_env() -> None:
    """Resolve the database the SERVER serves. Call BEFORE importing db.

    `api.db` reads `DATA_DIR` and `DB_NAME` at import time (db.py:58,62),
    so setting them afterwards has no effect at all — the module-level
    `DB_PATH` is already bound.

    ── CORRECTED 2026-09-09 ──────────────────────────────────────────
    This function used to skip any key already present in the
    environment, and its docstring said an exported value winning "is
    the server's own precedence." **That was false, and the false
    comment is what made the resulting failure look impossible.**

    `scripts/common.sh:26-29` sources `.env` under `set -a`, which
    OVERWRITES an exported value. The server therefore takes `.env`;
    this script took the shell. On 2026-09-09 a WSL profile carrying a
    stale `DATA_DIR=/home/chris/lorevox_data` and
    `DB_NAME=lorevox.sqlite3` silently won, and Ada was created in a
    database nothing serves — while `.env`, three lines away, named the
    right one. Measured from three sources that all agreed:

        shell env    /home/chris/lorevox_data   lorevox.sqlite3
        .env         /mnt/c/hornelore_data      hornelore.sqlite3
        api.log      /mnt/c/hornelore_data/db/hornelore.sqlite3

    `.env` now wins, matching `common.sh`. When it overrides an exported
    value the difference is PRINTED rather than applied quietly — a
    silent correction of this would have been just as hard to see as the
    silent failure was.

    THE OLD GUARD DID NOT SAVE US, and it is worth being precise about
    why. `--create` refuses when the resolved database does not exist,
    on the reasoning that being about to create one proves you are
    pointing where the product does not read. That reasoning holds only
    when no stale database is lying around. One was, so the refusal
    passed and the write landed in it. Existence was never the property
    worth checking; agreement with `.env` is.
    """
    env = REPO_ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        for key in ("DATA_DIR", "DB_NAME"):
            if not line.startswith(f"{key}="):
                continue
            value = line.split("=", 1)[1].strip()
            previous = os.environ.get(key)
            if previous is not None and previous != value:
                print(
                    f"  {key}: .env value {value!r} overrides the exported "
                    f"{previous!r}\n"
                    f"    (scripts/common.sh:26-29 sources .env under "
                    f"`set -a`, so this is what the server resolves)",
                    file=sys.stderr,
                )
            os.environ[key] = value

DISPLAY_NAME = "Ada Pruitt"
"""Deliberately an ordinary name, not a `ZZ …` marker.

THE TRADEOFF, STATED RATHER THAN HIDDEN. Other probe narrators are named
`ZZ COHORT …` so an operator scanning the list cannot mistake one for
family. That convention is right for harness narrators nobody talks to.
It is wrong HERE: the display name reaches Lori's context and her
greeting, and a narrator called `ZZ PHASE6 SYNTH` would confound the very
thing Phase 6 measures — how Lori speaks to a person.

The boundary is carried by `testing_only=True`, which is what the gate
actually reads. If Chris prefers the visible marker over conversational
realism, change this one constant; the tradeoff is his to make.
"""

#: An ordinary life, coherent across eras, with enough relationships,
#: places and work that a follow-up question has somewhere to go — and
#: enough UNSAID around the edges that Lori has something to ask about.
#: Every value is invented.
PROFILE = {
    "personal": {
        "firstName": "Ada",
        "lastName": "Pruitt",
        "maidenName": "Bellandi",
        "dateOfBirth": "1948-03-17",
        "placeOfBirth": "Barre, Vermont",
        # childhood_home — NOT satisfied by placeOfBirth (line 254).
        "childhoodHome": "Barre, Vermont — a duplex on Currier Street",
        # heritage
        "culture": "Italian on her father's side, Scots-Irish on her "
                   "mother's; the Bellandis came over to cut granite",
        "ethnicity": "Italian-American",
    },
    # siblings — `siblingCount` is an int; has_value(2) is True, and
    # has_value(0) would be too, so "only child" would also count.
    "family": {"siblingCount": 2},
    "siblings": [
        {"firstName": "Dennis", "relation": "brother", "birthDate": "1945"},
        {"firstName": "Claire", "relation": "sister", "birthDate": "1952"},
    ],
    # parents_work — every entry carries an occupation, because the list
    # alone proves nothing (line 282).
    "parents": [
        {"firstName": "Emil", "lastName": "Bellandi", "relation": "father",
         "occupation": "granite cutter at the Rock of Ages quarry"},
        {"firstName": "Ruth", "lastName": "Bellandi", "relation": "mother",
         "occupation": "secretary at the elementary school"},
    ],
    # education
    "education": {
        "highestLevel": "Two years at Vermont Technical College",
        "schooling": "Spaulding High School, Barre",
        "careerProgression": "dental assistant, then hygienist, then "
                             "office manager",
    },
    # military — False is an answer here, not an absence. See the
    # has_value note above.
    "military": {"served": False},
    # career
    "basics": {
        "career": "Dental hygienist, later office manager for a "
                  "two-dentist practice in Montpelier",
        "occupation": "retired dental office manager",
    },
    # partner
    "marriage": {"status": "married"},
    "spouse": {
        "firstName": "Warren", "lastName": "Pruitt",
        "occupation": "lineman for the electric co-op",
        "dateOfBirth": "1946-11-02",
    },
    # children
    "children": [
        {"firstName": "Nadia", "birthDate": "1972"},
        {"firstName": "Beth", "birthDate": "1975"},
    ],
    # life_stage — the ONLY path this topic reads (line 367).
    "community": {
        "retirementStatus": "retired since 2011",
        "role": "volunteers at the historical society",
    },
    "currentResidence": "Montpelier, Vermont",
}


def _find_existing(db):
    for person in db.list_testing_only_people(limit=200):
        if (person.get("display_name") or "").strip() == DISPLAY_NAME:
            return person
    return None


def _refuse_on_wrapped_blob(db, person_id) -> None:
    """`_load_profile_root` would read the wrapper, not our keys."""
    from collections.abc import Mapping
    blob = (db.get_profile(person_id) or {}).get("profile_json") or {}
    if isinstance(blob, Mapping) and isinstance(blob.get("profile"), Mapping):
        raise SystemExit(
            f"REFUSING: {person_id} already has a WRAPPED profile blob "
            f"(a top-level 'profile' key). `_load_profile_root` "
            f"(profile_seed.py:559) would read inside that wrapper, so a "
            f"top-level write would be invisible to every topic check. "
            f"Resolve the shape by hand before rerunning."
        )


def _report(db, person_id) -> int:
    """Two checks: the topic predicate, then the SHIPPED decision."""
    from api.services import profile_seed as seed
    from api.services import profile_seed_turn as seed_turn

    con = db._connect()
    try:
        snap = seed.load_snapshot(con, person_id)
        rows = [(t.topic_id, seed.topic_has_evidence(t, snap))
                for t in seed.TOPIC_REGISTRY]
        resolved = seed.resolve_effective(con, person_id, now=db._now_iso())
    finally:
        con.close()

    for topic_id, answered in rows:
        print(f"  {'answered' if answered else 'OPEN    '}  {topic_id}")
    open_topics = [tid for tid, ok in rows if not ok]
    print()

    if open_topics:
        print(f"FAIL — {len(open_topics)} of {len(rows)} topics OPEN: "
              f"{', '.join(open_topics)}")
        print("Lori would be pulled into intake on those, and the baseline "
              "would measure the gap instead of the configuration.")
        return 1
    print(f"All {len(rows)} Profile Seed topics answered "
          f"[profile_seed.topic_has_evidence].")

    # ── THE DECISION THAT ACTUALLY MATTERS ───────────────────────────
    if resolved is None:
        print("FAIL — no onboarding row (HISTORICAL narrator). "
              "`plan_turn` returns IDLE here for the wrong reason: not "
              "'nothing to ask' but 'this narrator is not enrolled'.")
        return 1
    state, _changed = resolved
    plan = seed_turn.plan_turn(state=state.as_dict(), history=[],
                               narrator_text="", eligible=True)
    print(f"Resolved status: {state.status}   "
          f"active_topic: {state.active_topic_id}")
    print(f"plan_turn action: {plan.action}   "
          f"[profile_seed_turn.py:620 reads status]")
    if plan.action != seed_turn.IDLE:
        print(f"\nFAIL — the shipped gate does NOT read IDLE. Lori will "
              f"raise onboarding on the first turn.")
        return 1
    print("\nPASS — the shipped onboarding gate is IDLE. Lori has nothing "
          "to ask as intake, so what she does ask is hers.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create/verify the Phase 6 populated synthetic narrator.")
    parser.add_argument("--create", action="store_true",
                        help="create and populate (the only writes)")
    parser.add_argument("--check", action="store_true",
                        help="verify Profile Seed coverage, read only")
    parser.add_argument(
        "--sibling", action="store_true",
        help="with --create: make ANOTHER narrator from the same frozen "
             "profile even though one already exists. Same display name, "
             "same profile, new person id. Phase 6 crossover arms each "
             "need a narrator with no prior turns, and the capture "
             "refuses more than ten traced turns per narrator per run "
             "— so every arm gets its own Ada. Track it by id.")
    args = parser.parse_args()
    if not (args.create or args.check):
        parser.error("pass --create or --check")
    if args.sibling and not args.create:
        parser.error("--sibling only means something with --create")

    _load_env()                      # BEFORE the import. See the docstring.
    from api import db

    print(f"Database: {db.DB_PATH}")
    if not Path(db.DB_PATH).is_file():
        print(
            f"\nREFUSING: that database does not exist yet.\n"
            f"  Writing would CREATE a second, empty database and populate "
            f"it, and every check in this script would then pass about a "
            f"narrator the running product cannot see. That is exactly what "
            f"happened on the first run.\n"
            f"  Expected the live database named by .env "
            f"(DATA_DIR/db/DB_NAME). Check DATA_DIR and DB_NAME before "
            f"rerunning.", file=sys.stderr)
        return 2
    print()

    existing = _find_existing(db)

    if args.check:
        if not existing:
            print(f"No testing-only narrator named {DISPLAY_NAME!r}. "
                  f"Run with --create.")
            return 1
        print(f"{DISPLAY_NAME}  {existing['id']}\n")
        return _report(db, existing["id"])

    if existing and not args.sibling:
        person_id = existing["id"]
        print(f"Already exists: {person_id} — re-verifying rather than "
              f"creating a sibling. (Pass --sibling to make another.)\n")
    else:
        if existing:
            print(f"Sibling requested: {existing['id']} already exists and "
                  f"is left untouched; creating a second {DISPLAY_NAME!r} "
                  f"from the same frozen profile.\n")
        person = db.create_person(
            display_name=DISPLAY_NAME,
            role="subject",
            date_of_birth=PROFILE["personal"]["dateOfBirth"],
            place_of_birth=PROFILE["personal"]["placeOfBirth"],
            narrator_type="live",
            current_residence=PROFILE["currentResidence"],
            # THE BOUNDARY. Set here, at creation, and nowhere else.
            # These three identity anchors are also what
            # `identity_anchors_complete` (profile_seed.py:490) requires
            # before the walk may leave `pending` — without them the
            # status would read `pending` and IDLE would be true for the
            # wrong reason.
            testing_only=True,
        )
        person_id = person["id"]
        print(f"Created {DISPLAY_NAME}  {person_id}  testing_only=True\n")

    _refuse_on_wrapped_blob(db, person_id)
    db.update_profile_json(person_id, PROFILE, merge=True,
                           reason="phase6-populated-synthetic-narrator")
    print("Profile written.\n")
    return _report(db, person_id)


if __name__ == "__main__":
    sys.exit(main())
