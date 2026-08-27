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
COMPOSER_TESTS = "tests.test_profile_seed_composer_section"


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
    Mutation(
        "C1", "a sparse onboarding runtime activates identity mode — Lori "
              "asks a narrator she has known for months for their name",
        COMPOSER,
        "        if not identity_complete and profile_seed_onboarding_active(runtime71):\n            identity_complete = True",
        "        if False and profile_seed_onboarding_active(runtime71):\n            identity_complete = True",
        COMPOSER_TESTS),
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
    Mutation(
        "C4", "an unknown topic id renders something instead of nothing",
        COMPOSER,
        "    if definition is None:\n        return \"\"",
        "    if definition is None:\n        return \"PROFILE SEED — ONE QUESTION.\"",
        COMPOSER_TESTS),
    Mutation(
        "C5", "an idle plan still renders the section",
        COMPOSER,
        '    state = runtime71.get(PROFILE_SEED_ONBOARDING_KEY)\n    if not isinstance(state, dict):\n        return ""\n\n    action = state.get("action")',
        '    state = runtime71.get(PROFILE_SEED_ONBOARDING_KEY)\n    if not isinstance(state, dict):\n        return ""\n\n    action = state.get("action") or "present"',
        COMPOSER_TESTS),

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


def _run_tests(tests: str, env: dict) -> Tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", *tests.split()],
        cwd=REPO, env=env, capture_output=True, text=True, timeout=900)
    tail = (proc.stderr.strip().splitlines() or [""])[-1]
    return proc.returncode, tail


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
        code, tail = _run_tests(tests, env)
        mark = "green" if code == 0 else "RED  "
        print(f"  {mark}  {tests}")
        if code != 0:
            print(f"         -> {tail}")
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
