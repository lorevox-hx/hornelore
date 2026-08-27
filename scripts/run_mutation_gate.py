#!/usr/bin/env python3
"""Reproducible mutation gate. Every mutation is checked in, not reported.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 (2026-08-26).

── WHY THIS EXISTS ───────────────────────────────────────────────────

Mutation results were being REPORTED in commit messages and run from a
throwaway script in /tmp. A reviewer could verify the unit tests and
could not reproduce the mutation evidence — which makes the strongest
claim in those messages the one nobody else can check. That is exactly
backwards.

Every mutation lives in `MUTATIONS` below: the exact anchor, the exact
replacement, and the test module that must fail. Run it and get the
same answer I got.

── HOW TO RUN ────────────────────────────────────────────────────────

    cd /mnt/c/Users/chris/hornelore
    PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONPATH=server/code \\
        python3 scripts/run_mutation_gate.py

    # one mutation, by id
    ... python3 scripts/run_mutation_gate.py --only M10

Exit 0 iff EVERY mutation was caught. Exit 1 if any survived, if an
anchor no longer matches, or if a mutation fails to compile.

── WHAT COUNTS AS CAUGHT ─────────────────────────────────────────────

A non-zero unittest exit **that is not a SyntaxError**. A mutation
caught by a syntax error proves nothing about the tests: it proves
Python can read. An earlier round of this lane mistook two such results
for evidence, so the runner classifies them separately and treats them
as NOT caught.

── THE TWO PRECONDITIONS, AND WHY THEY ARE THE POINT ─────────────────

"Non-zero exit means caught" is only true if the suite was GREEN
BEFORE the mutation. Without that, this script would happily report
22/22 against a suite that was already failing — every mutation
"caught" by a failure that had nothing to do with it, and the strongest
claim in the report would be the emptiest.

So, before any mutation is applied:

  1. **The tree is clean — every `git status --porcelain` entry,
     untracked included.** Not merely the mutation targets: an edited
     TEST file introduces failures the runner would credit to a
     mutation, and an UNTRACKED file can do the same without appearing
     in any diff (`sitecustomize.py` is imported by every Python
     process; so is a stray `conftest.py` or a shadowing module).
  2. **Every unique selected test command runs once against the
     unmodified baseline.** A red baseline REFUSES the gate, and says
     which command failed.

Both are skippable only with an explicit `--allow-dirty`, which exists
for proving the runner itself and is not the acceptance gate.

── SAFETY, AND WHY THERE IS A JOURNAL ────────────────────────────────

Each mutation is applied to a file, run, and restored in a `finally`.

**A `finally` does not run if the process is killed.** That is not
theoretical: the first run of this script was killed by a harness
timeout partway through mutation `P3`, and it left
`services/profile_seed.py` mutated on disk — a live auto-enrolment of
historical narrators, sitting silently in the working tree. It was
caught because `git status` was checked immediately afterwards. It
would not have announced itself.

Two mitigations, because one is not enough:

  * **the clean-tree refusal** above — the runner will not start
    against an unclean tree, so `git checkout` is always a clean
    recovery;
  * **the journal** — before applying anything the runner writes
    `.runtime/mutation_gate.json` holding the mutation id, the target
    and the ORIGINAL bytes. It is removed on clean completion. If it
    exists at startup, the runner refuses to run and prints the exact
    restore command, so an interrupted run is loud rather than silent.

Run this on a clean tree, and if it is interrupted, run it again — it
will tell you what to put back.
"""
from __future__ import annotations

import argparse
import json
import re
import py_compile
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent
TURN = "server/code/api/services/profile_seed_turn.py"
SEED = "server/code/api/services/profile_seed.py"
DB = "server/code/api/db.py"
COMPOSER = "server/code/api/prompt_composer.py"

REDUCER_TESTS = "tests.test_profile_seed_turn_reducer"
AUTHORITY_TESTS = "tests.test_profile_seed_server_authority"
COVERAGE_TESTS = "tests.test_profile_seed_enrollment_coverage"
REFUSAL_TESTS = "tests.test_narrator_refusal_characterization"
POLICY = "server/code/api/services/prompt_section_policy.py"

# -- THE STEP 4 BASELINE IS THREE MODULES, NOT ONE, 2026-08-26 ---------
#
# It was `tests.test_profile_seed_composer_section` alone, and that is
# why the gate reported green while two ESTABLISHED prompt-preservation
# tests were red at `c99eb5f`: registering `profile_seed_onboarding`
# broke the completeness inventories in `test_prompt_section_policy` and
# `test_prompt_sections`, and the gate never ran them, so nothing in the
# Step 4 evidence could see it.
#
# A gate scoped to the suite written alongside the feature only ever
# asks "did I break my own new tests". The sections a new section has to
# coexist with are exactly where a regression lands.
COMPOSER_TESTS = ("tests.test_profile_seed_composer_section "
                  "tests.test_prompt_section_policy "
                  "tests.test_prompt_sections")


@dataclass(frozen=True)
class Mutation:
    id: str
    #: What defective behaviour this reintroduces, in one line.
    what: str
    target: str
    old: str
    new: str
    tests: str
    #: True when this mutation is a design the lane ACTUALLY CARRIED
    #: before a review caught it. Those are the ones that matter most.
    was_real: bool = False


MUTATIONS: Tuple[Mutation, ...] = (
    Mutation(
        "M1", "the first presentation advances its own question",
        TURN,
        "    if outstanding is None:\n        # FIRST PRESENTATION.",
        "    if False and outstanding is None:\n        # FIRST PRESENTATION.",
        REDUCER_TESTS, was_real=True),
    Mutation(
        "M2", "an acknowledgement re-stamps `presented`, so Lori re-asks "
              "the question she is acknowledging",
        TURN,
        "        if self.action not in (PRESENT, RE_PRESENT):\n            return {}",
        "        if self.action not in (PRESENT, RE_PRESENT, ACKNOWLEDGE):\n            return {}",
        REDUCER_TESTS, was_real=True),
    Mutation(
        "M3", "staleness compares topic instead of the (topic, version) tuple",
        TURN,
        "    if outstanding.tuple != (active, version):",
        "    if outstanding.topic_id != active:",
        REDUCER_TESTS, was_real=True),
    Mutation(
        "M3b", "consumption compares topic instead of the tuple",
        TURN,
        "        if event.tuple in consumed:",
        "        if event.topic_id in {t for t, _ in consumed}:",
        REDUCER_TESTS, was_real=True),
    Mutation(
        "M4", "recovery disabled — the machine repeats instead of retrying",
        TURN,
        "    last = latest_response(history)\n    if last is None:",
        "    last = None\n    if last is None:",
        REDUCER_TESTS, was_real=True),
    Mutation(
        "M5", "a deferral writes a response event, closing a question the "
              "narrator is still working on",
        TURN,
        "    if outcome == STATIONARY:",
        "    if False and outcome == STATIONARY:",
        REDUCER_TESTS),
    Mutation(
        "M6", "forgetting classified as declined — a narrator's memory loss "
              "recorded as a refusal to speak",
        TURN,
        "    if _refusal.is_topic_refusal(text):\n        return DECLINED",
        "    if _refusal.is_topic_refusal(text) or 'remember' in text.lower():\n        return DECLINED",
        REDUCER_TESTS),
    Mutation(
        "M7", "a malformed version is accepted",
        TURN,
        "        return raw if raw >= 1 else None",
        "        return raw",
        REDUCER_TESTS),
    Mutation(
        "M8", "a version conflict forces the stored disposition anyway",
        TURN,
        "    except _seed.VersionConflict:\n        return RecoveryOutcome(CONFLICT_RESOLVED, resolve_fn(person_id),",
        "    except _seed.VersionConflict:\n        apply_fn(person_id, expected_version=last.version,\n                 action=last.disposition, topic_id=last.topic_id)\n        return RecoveryOutcome(CONFLICT_RESOLVED, resolve_fn(person_id),",
        REDUCER_TESTS),
    Mutation(
        "M10", "one-for-one consumption — a response consumes only ONE "
               "presentation, so an earlier identical one reappears as "
               "outstanding and an answered question is asked again",
        TURN,
        "        if event.tuple in consumed:\n            # Earlier than the response",
        "        if event.tuple in consumed:\n            consumed.discard(event.tuple)\n            # Earlier than the response",
        REDUCER_TESTS, was_real=True),

    # ── Phase 2 step 4: the composer section ────────────────────────
    # C1 ("a sparse onboarding runtime activates identity mode") was
    # RETIRED 2026-08-26. Its anchor was the `identity_complete = True`
    # inference, which review required be withdrawn; C8 reintroduces
    # exactly that defect against the current code and is the live
    # version of this check.
    Mutation(
        "C2", "the legacy ten-question list renders alongside the canonical "
              "one — two topic orders in one prompt",
        COMPOSER,
        "            if profile_seed_onboarding_active(runtime71):\n                pass\n            elif current_pass == \"pass1\":",
        "            if False:\n                pass\n            elif current_pass == \"pass1\":",
        COMPOSER_TESTS),
    # C3 first read `("present","re_present")` -> `(...,"acknowledge")`.
    # That was a NO-OP: `acknowledge` returns above that line, so the
    # mutation tested nothing and "survived" for the emptiest possible
    # reason. It now routes acknowledge through the asking path, which
    # is the defect it was meant to reproduce.
    Mutation(
        "C3", "an ACKNOWLEDGE turn asks a question anyway",
        COMPOSER,
        '    action = state.get("action")\n    if action == "acknowledge":',
        '    action = state.get("action")\n    if action == "acknowledge":\n        action = "present"\n    if False:',
        COMPOSER_TESTS),
    # C4 ("an unknown topic id renders something") was RETIRED
    # 2026-08-26. Topic validation moved into `_validated_onboarding_plan`
    # so the renderer and the suppression gate cannot disagree, and C6
    # mutates that single check — which now reproduces BOTH halves of
    # the defect: rendering nothing while still suppressing.
    # C5 was described as "an idle plan still renders" and did not
    # mutate the idle action at all — it turned a MISSING action into
    # `present`, and was caught by a malformed-state fixture. Renamed to
    # what it does; C5b is the real idle mutation.
    Mutation(
        "C5", "an unrecognised or missing action is treated as renderable",
        COMPOSER,
        '    if state.get("action") not in ("present", "re_present", "acknowledge"):\n        return None',
        '    if False and state.get("action") not in ("present", "re_present", "acknowledge"):\n        return None',
        COMPOSER_TESTS),
    Mutation(
        "C5b", "an IDLE plan with a valid topic renders the section",
        COMPOSER,
        '    if state.get("action") not in ("present", "re_present", "acknowledge"):\n        return None',
        '    if state.get("action") not in ("present", "re_present", "acknowledge", "idle"):\n        return None',
        COMPOSER_TESTS),
    # C10 ("completes_walk read by truthiness") is RETIRED 2026-08-26.
    # The VALIDATOR now rejects a non-Boolean `completes_walk` outright
    # (C11), so the renderer's `is True` is unobservable defence in
    # depth: loosening it changes nothing a test can see, and the
    # mutation could never be caught. A mutation that cannot fail is
    # not evidence, and keeping it would make the gate red forever for
    # the wrong reason. The renderer keeps `is True` anyway — cheap, and
    # correct on its own terms — but the guard that DOES the work, and
    # is measured, is C11.
    Mutation(
        "C11", "the validator accepts a non-Boolean completes_walk",
        COMPOSER,
        '    completes = state.get("completes_walk")\n    if completes is not None and not isinstance(completes, bool):\n        return None',
        '    completes = state.get("completes_walk")\n    if False and completes is not None and not isinstance(completes, bool):\n        return None',
        COMPOSER_TESTS),
    Mutation(
        "C12", "the acknowledgement makes an AUTHORITATIVE completion claim "
               "before the versioned apply — a conflict then leaves the "
               "narrator told they were finished and asked again",
        COMPOSER,
        '                "  - Respond warmly and say that you feel you now have a "\n                "good sense of their story and are ready to hear it "\n                "properly.")',
        '                "  - This was the LAST thing you needed. Tell them the "\n                "walk is complete.")',
        COMPOSER_TESTS, was_real=True),
    Mutation(
        "C13", "the ASKING turn reintroduces the last-topic state claim, "
               "which missing/empty/non-list `remaining_topics` all satisfy "
               "by filtering to zero",
        COMPOSER,
        '    lines.append(f"ASK ONLY THIS: {definition.question}")',
        '    lines.append(f"ASK ONLY THIS: {definition.question}")\n'
        '    if len([t for t in (state.get("remaining_topics") or [])\n'
        '            if _topic_def(t) is not None]) <= 1:\n'
        '        lines.append("  - This is the last topic still open.")',
        COMPOSER_TESTS, was_real=True),
    Mutation(
        "C14", "THE HALF-FIX: the last-topic LINE is gone but the `remaining` "
               "count that existed only to produce it is left behind, ready "
               "for the next person who wants a heads-up to misuse",
        COMPOSER,
        '    known = [t for t in (state.get("known_topics") or [])\n'
        '             if _topic_def(t) is not None]',
        '    known = [t for t in (state.get("known_topics") or [])\n'
        '             if _topic_def(t) is not None]\n'
        '    remaining = len([t for t in (state.get("remaining_topics") or [])\n'
        '                     if _topic_def(t) is not None])',
        COMPOSER_TESTS),
    Mutation(
        "C15", "`known_topics` validation is weakened back to a truthiness "
               "check, so a dict iterates its KEYS and Lori is told a topic "
               "is already settled that nothing established",
        COMPOSER,
        '        if not isinstance(known, list):\n            return None\n        if any(not isinstance(t, str) for t in known):\n            return None',
        '        if False:\n            return None',
        COMPOSER_TESTS, was_real=True),
    Mutation(
        "C16", "the onboarding section becomes DROPPABLE, so a tight budget "
               "silently drops the question and Lori stops asking mid-walk",
        POLICY,
        '    _p("profile_seed_onboarding", "lori-onboarding",\n       "profile_seed_onboarding_active", TRIM_NEVER, SOURCE_SERVER_DB,\n       TIER_WORKFLOW, True, 0,',
        '    _p("profile_seed_onboarding", "lori-onboarding",\n       "profile_seed_onboarding_active", TRIM_DROP_WHOLE, SOURCE_SERVER_DB,\n       TIER_WORKFLOW, False, 35,',
        COMPOSER_TESTS),
    Mutation(
        "C9", "the soft closing line never reaches the acknowledgement turn",
        COMPOSER,
        '        if state.get("completes_walk") is True:',
        '        if False and state.get("completes_walk") is True:',
        COMPOSER_TESTS),
    Mutation(
        "T1", "apostrophes are not folded — \"I\'ll come back to that\" "
              "closes the topic instead of leaving it open",
        TURN,
        '    deapostrophised = _APOSTROPHES.sub("", (text or "").lower())',
        '    deapostrophised = (text or "").lower()',
        REDUCER_TESTS, was_real=True),
    Mutation(
        "T2", "the last answer does not complete the walk",
        TURN,
        "    completes = remaining == [outstanding.topic_id]",
        "    completes = False",
        REDUCER_TESTS),
    Mutation(
        "R2", "curly apostrophes hide a refusal from extraction and from "
              "Profile Seed",
        "server/code/api/services/narrator_refusal.py",
        '    lowered = _CURLY_APOSTROPHES.sub("\'", text.lower())',
        "    lowered = text.lower()",
        REFUSAL_TESTS, was_real=True),
    Mutation(
        "C6", "malformed onboarding state suppresses the legacy pass "
              "directive — working instructions vanish and nothing "
              "replaces them",
        COMPOSER,
        "    from .services.profile_seed import is_known_topic\n    if not is_known_topic(state.get(\"topic_id\")):\n        return None",
        "    from .services.profile_seed import is_known_topic\n    if False and not is_known_topic(state.get(\"topic_id\")):\n        return None",
        COMPOSER_TESTS, was_real=True),
    Mutation(
        "C7", "the composer keeps a second hand-written topic order",
        COMPOSER,
        "    for number, topic_def in enumerate(TOPIC_REGISTRY, 1):",
        "    TOPIC_REGISTRY = TOPIC_REGISTRY[:1]\n    for number, topic_def in enumerate(TOPIC_REGISTRY, 1):",
        COMPOSER_TESTS, was_real=True),
    Mutation(
        "C8", "identity_complete inferred from an onboarding payload again",
        COMPOSER,
        "        identity_complete = bool(runtime71.get(\"identity_complete\", False))",
        "        identity_complete = bool(runtime71.get(\"identity_complete\", False)) or profile_seed_onboarding_active(runtime71)",
        COMPOSER_TESTS, was_real=True),

    # ── Phase 1 guards, kept runnable from one place ────────────────
    Mutation(
        "P1", "zero and False are not evidence",
        SEED,
        "    if isinstance(value, (int, float)):\n        return True",
        "    if isinstance(value, (int, float)):\n        return bool(value)",
        AUTHORITY_TESTS),
    Mutation(
        "P2", "birthplace answers childhood home",
        SEED,
        '        profile_paths=("personal.childhoodHome", "basics.childhoodHome",\n                       "personal.childhoodGeography"),',
        '        profile_paths=("personal.childhoodHome", "basics.childhoodHome",\n                       "personal.childhoodGeography", "personal.placeOfBirth"),',
        AUTHORITY_TESTS),
    Mutation(
        "P3", "a historical narrator is auto-enrolled",
        SEED,
        "    row = read_row(con, person_id)\n    if row is None:\n        return None\n\n    stored_state",
        "    row = read_row(con, person_id)\n    if row is None:\n        enroll(con, person_id, now)\n        row = read_row(con, person_id)\n\n    stored_state",
        AUTHORITY_TESTS),
    Mutation(
        "P4", "a stale PATCH is accepted",
        DB,
        "        if state.version != expected:",
        "        if False and state.version != expected:",
        AUTHORITY_TESTS),
    Mutation(
        "P5", "`completed` is not terminal",
        SEED,
        "    if stored_status == STATUS_COMPLETED:\n        # Terminal.",
        "    if False and stored_status == STATUS_COMPLETED:\n        # Terminal.",
        AUTHORITY_TESTS),
    Mutation(
        "P6", "enrollment moved after the commit",
        DB,
        "        _profile_seed.enroll(con, pid, now)\n        con.commit()",
        "        con.commit()\n        _profile_seed.enroll(con, pid, now)\n        con.commit()",
        COVERAGE_TESTS + " " + AUTHORITY_TESTS),
    Mutation(
        "P7", "a client may declare `known` or `completed`",
        DB,
        '    valid_actions = ("addressed", "declined", "pause", "resume")',
        '    valid_actions = ("addressed", "declined", "pause", "resume", "known", "completed")',
        AUTHORITY_TESTS),
    # P8/P9 wrap a WHOLE statement in try/except. An earlier version
    # inserted only the `try:` line and was "caught" by a SyntaxError,
    # which proves Python can parse and nothing about the tests. The
    # runner now classifies that as BROKEN rather than CAUGHT, and these
    # two are written to compile.
    Mutation(
        "P8", "the bio_facts read suppresses sqlite errors, so a storage "
              "fault becomes ten unanswered topics",
        SEED,
        '    rows = con.execute(\n'
        '        "SELECT field_key, value FROM bio_facts "\n'
        '        f"WHERE narrator_id=? AND status IN ({placeholders}) "  # noqa: S608\n'
        '        "ORDER BY last_updated ASC;",\n'
        '        (person_id, *EVIDENCE_BIO_STATUSES),\n'
        '    ).fetchall()',
        '    try:\n'
        '        rows = con.execute(\n'
        '            "SELECT field_key, value FROM bio_facts "\n'
        '            f"WHERE narrator_id=? AND status IN ({placeholders}) "  # noqa: S608\n'
        '            "ORDER BY last_updated ASC;",\n'
        '            (person_id, *EVIDENCE_BIO_STATUSES),\n'
        '        ).fetchall()\n'
        '    except sqlite3.Error:\n'
        '        return out',
        AUTHORITY_TESTS),
    Mutation(
        "P9", "`read_row` suppresses sqlite errors, so a storage fault "
              "becomes a historical narrator",
        SEED,
        '    return con.execute(\n'
        '        f"SELECT person_id, status, topic_state_json, active_topic_id, "  # noqa: S608\n'
        '        f"version, created_at, updated_at, completed_at "\n'
        '        f"FROM {TABLE} WHERE person_id=?;",\n'
        '        (person_id,),\n'
        '    ).fetchone()',
        '    try:\n'
        '        return con.execute(\n'
        '            f"SELECT person_id, status, topic_state_json, active_topic_id, "  # noqa: S608\n'
        '            f"version, created_at, updated_at, completed_at "\n'
        '            f"FROM {TABLE} WHERE person_id=?;",\n'
        '            (person_id,),\n'
        '        ).fetchone()\n'
        '    except sqlite3.Error:\n'
        '        return None',
        AUTHORITY_TESTS),
    Mutation(
        "P10", "a nonexistent person is reported as a historical narrator",
        DB,
        "        if not _profile_seed.person_exists(con, person_id):\n            con.rollback()\n            raise _profile_seed.PersonNotFound(person_id)\n        state = _profile_seed.reconcile",
        "        state = _profile_seed.reconcile",
        AUTHORITY_TESTS),
    Mutation(
        "R1", "a refusal pattern is dropped",
        "server/code/api/services/narrator_refusal.py",
        '    re.compile(r"rather not (?:get into|talk about|discuss|say|share|go there)", re.IGNORECASE),\n',
        "",
        REFUSAL_TESTS),
)

CAUGHT, MISSED, BROKEN = "CAUGHT", "MISSED", "BROKEN"

#: Written before a mutation is applied, removed after it is restored.
#: Its survival means a run was killed mid-mutation.
JOURNAL = REPO / ".runtime" / "mutation_gate.json"


def _journal_write(mutation: "Mutation", original: str) -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps({
        "mutation_id": mutation.id,
        "target": mutation.target,
        "what": mutation.what,
        "original": original,
    }), encoding="utf-8")


def _journal_clear() -> None:
    try:
        JOURNAL.unlink()
    except FileNotFoundError:
        pass


def _journal_check() -> int:
    """Refuse to run, loudly, if a previous run was killed mid-mutation."""
    if not JOURNAL.exists():
        return 0
    try:
        record = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except Exception:
        record = {}
    target = record.get("target", "(unknown)")
    print("REFUSING TO RUN — a previous run was interrupted while mutation "
          f"{record.get('mutation_id', '?')} was applied.")
    print(f"    target : {target}")
    print(f"    what   : {record.get('what', '(unknown)')}")
    print()
    path = REPO / target if target != "(unknown)" else None
    if path and path.exists() and record.get("original") is not None:
        if path.read_text(encoding="utf-8") == record["original"]:
            print("The file already matches the saved original — nothing to "
                  "restore. Delete the journal and re-run:")
            print(f"    rm {JOURNAL.relative_to(REPO)}")
            return 1
        print("THE MUTATION IS STILL ON DISK. Restore it with:")
        print(f"    git checkout -- {target}")
        print(f"    rm {JOURNAL.relative_to(REPO)}")
        print("\n(or use --restore to write the saved original back)")
    return 1


def _journal_restore() -> int:
    if not JOURNAL.exists():
        print("no journal — nothing to restore")
        return 0
    record = json.loads(JOURNAL.read_text(encoding="utf-8"))
    path = REPO / record["target"]
    path.write_text(record["original"], encoding="utf-8")
    _journal_clear()
    print(f"restored {record['target']} from the journal "
          f"(mutation {record['mutation_id']})")
    return 0


def _unclean_paths() -> List[str]:
    """EVERY `git status --porcelain` entry, untracked included.

    NOT just the mutation targets. A modified TEST file is the more
    dangerous case than a modified target: it introduces failures the
    runner would credit to a mutation, so every mutation reports CAUGHT
    for a reason that has nothing to do with the mutation.

    ── UNTRACKED FILES COUNT TOO, corrected 2026-08-26 ─────────────────

    *(This function skipped `??` entries, and its docstring asserted
    that "a new file cannot change what an existing test does". That is
    not universally true, and the counter-example is ordinary rather
    than exotic: an untracked `sitecustomize.py` is imported
    automatically by every Python process that starts. So is a stray
    `conftest.py`, an `__init__.py` that turns a directory into a
    package, or any module earlier on `sys.path` than the one a test
    means to import. Each changes what a test measures while appearing
    in no diff.)*

    For an acceptance gate the bar is "the tree is what the commit
    says", and that includes files the commit does not mention.
    `--allow-dirty` remains the development escape hatch.
    """
    out = subprocess.run(["git", "status", "--porcelain"], cwd=REPO,
                         capture_output=True, text=True).stdout
    unclean = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        # Renames arrive as "old -> new"; the new path is what matters.
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        unclean.append(f"{line[:2].strip() or '??'} {path}")
    return sorted(unclean)


_RAN_RE = re.compile(r"^Ran (\d+) tests?", re.MULTILINE)
_SKIP_RE = re.compile(r"skipped=(\d+)")


def _run_tests(tests: str, env: dict) -> Tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *tests.split()],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    tail = (proc.stderr.strip().splitlines() or [""])[-1]
    return proc.returncode, tail


def _counts(tests: str, env: dict) -> Tuple[int, int, int, str]:
    """Return (exit, ran, skipped, tail).

    RAN AND SKIPPED ARE REPORTED, not merely the exit code. "Exit zero"
    calls an all-skipped baseline green, which is the same class of
    false assurance as a mutation caught by a SyntaxError — and this
    lane has already shipped one suite where 35 tests were skipped on a
    capable interpreter and the run said OK.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *tests.split()],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    out = proc.stderr
    ran_m, skip_m = _RAN_RE.search(out), _SKIP_RE.search(out)
    ran = int(ran_m.group(1)) if ran_m else -1
    skipped = int(skip_m.group(1)) if skip_m else 0
    tail = (out.strip().splitlines() or [""])[-1]
    return proc.returncode, ran, skipped, tail


def _baseline_green(selected: List["Mutation"], env: dict) -> bool:
    """Every unique selected test command must PASS unmutated.

    This is what makes a later non-zero exit mean something. A mutation
    cannot be "caught" by a suite that was already failing, and without
    this check the runner cannot tell the two apart.
    """
    commands = sorted({m.tests for m in selected})
    print(f"baseline — {len(commands)} unique test command(s), unmutated:")
    ok = True
    for tests in commands:
        code, ran, skipped, tail = _counts(tests, env)
        mark = "green" if code == 0 else "RED  "
        detail = f"{ran} ran"
        if skipped:
            detail += f", {skipped} SKIPPED"
        print(f"  {mark}  {detail:22}  {tests}")
        if code != 0:
            print(f"         -> {tail}")
            ok = False
        elif ran <= 0:
            print("         -> baseline ran NO tests; 'exit zero' here "
                  "means nothing")
            ok = False
        elif skipped and skipped >= ran:
            print("         -> every baseline test skipped; a mutation "
                  "cannot be caught by a suite that does not run")
            ok = False
    if not ok:
        print("\nREFUSING THE GATE — a baseline is red. Every mutation would "
              "report CAUGHT for a failure that has nothing to do with it.")
    print()
    return ok


def run_one(mutation: Mutation, env: dict) -> Tuple[str, str]:
    path = REPO / mutation.target
    original = path.read_text(encoding="utf-8")
    if mutation.old not in original:
        return BROKEN, "anchor not found — the code moved under this mutation"
    _journal_write(mutation, original)
    path.write_text(original.replace(mutation.old, mutation.new, 1),
                    encoding="utf-8")
    try:
        try:
            py_compile.compile(str(path), cfile=tempfile.mktemp(), doraise=True)
        except Exception as exc:
            return BROKEN, f"mutation does not compile: {exc}"
        code, tail = _run_tests(mutation.tests, env)
        if code == 0:
            return MISSED, tail
        if "SyntaxError" in tail or "IndentationError" in tail:
            # Not evidence. Python failing to parse says nothing about
            # whether the tests would have noticed the behaviour change.
            return BROKEN, "caught only by a syntax error — not evidence"
        return CAUGHT, tail
    finally:
        path.write_text(original, encoding="utf-8")
        _journal_clear()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", action="append", default=[],
                    help="run only these mutation ids")
    ap.add_argument("--restore", action="store_true",
                    help="write the journal's saved original back after an "
                         "interrupted run")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="run against a modified tree. For proving the "
                         "runner itself before the code is committed; NOT "
                         "for the acceptance gate.")
    args = ap.parse_args()

    if args.restore:
        return _journal_restore()
    if _journal_check():
        return 1

    dirty = _unclean_paths()
    if dirty and not args.allow_dirty:
        print("REFUSING TO RUN — the working tree is not clean. A modified "
              "TEST file would make every mutation report CAUGHT for a "
              "failure that has nothing to do with it; an UNTRACKED file can "
              "do the same (sitecustomize.py, conftest.py, a shadowing "
              "module); and a crash mid-run would restore the wrong bytes:")
        for name in dirty:
            print("   ", name)
        print("\nCommit first, or pass --allow-dirty if you are deliberately "
              "testing the runner.")
        return 1
    if dirty:
        print("WARNING: --allow-dirty. The tree is modified, so CAUGHT may "
              "mean 'the suite was already failing' and an interrupted run "
              "restores the WORKING copy, not HEAD:")
        for name in dirty:
            print("   ", name)
        print()

    import os
    env = dict(os.environ)
    env.setdefault("PYTHONPYCACHEPREFIX", "/tmp/pyc")
    env["PYTHONPATH"] = "server/code"

    selected = [m for m in MUTATIONS if not args.only or m.id in args.only]
    if not selected:
        print("no mutations matched --only")
        return 1

    if not _baseline_green(selected, env):
        return 1

    results = []
    width = max(len(m.id) for m in selected)
    for mutation in selected:
        status, detail = run_one(mutation, env)
        results.append((status, mutation))
        mark = {CAUGHT: "CAUGHT ", MISSED: "MISSED!", BROKEN: "BROKEN "}[status]
        star = " *" if mutation.was_real else "  "
        print(f"{mark}{star} {mutation.id:<{width}}  {mutation.what}")
        if status != CAUGHT:
            print(f"          -> {detail}")

    caught = sum(1 for s, _ in results if s == CAUGHT)
    real = sum(1 for s, m in results if s == CAUGHT and m.was_real)
    print(f"\n{caught}/{len(selected)} caught behaviourally "
          f"({real} of them designs this lane actually carried, marked *)")
    return 0 if caught == len(selected) else 1


if __name__ == "__main__":
    sys.exit(main())
