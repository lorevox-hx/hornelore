"""The ordinary new narrator does not reach the ten-topic walk.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 0 (2026-08-26).

**THIS PHASE CHANGES NO BEHAVIOUR.** This file demonstrates the defect
instead of describing it, and it is written so that it will tell us when
the defect is gone.

── WHY `expectedFailure` AND NOT A RED TEST ──────────────────────────

The work order asks for "a failing ordinary-intake reachability test".
A plainly failing test would leave the suite red from today until the
lane closes, and a permanently red suite trains everyone to stop reading
it — after which the next real regression is invisible. That trade is a
bad one and it is avoidable.

`@unittest.expectedFailure` records the same fact executably and does
two things a red test cannot:

  * the suite stays honest — `OK (expected failures=N)`, no noise to
    tune out, and nothing to "fix" by muting;
  * **it reports when the defect is repaired.** When a later phase makes
    the walk reachable, this test starts passing, and unittest reports an
    unexpected success as a FAILURE. The test actively announces the fix
    rather than sitting there quietly succeeding.

So: the expected failures below are the defect. If they ever pass, read
the message on `test_the_ordinary_narrator_reaches_the_walk` — it says
what to do next.

── THE RACE, DRIVEN RATHER THAN ASSERTED FROM PROSE ──────────────────

Every step below is executed against the real product code:

  1. ordinary intake requires name, DOB and birthplace;
  2. those three anchors alone make `build_chronology_accordion_payload`
     return `seed_ready: True` with a full seven-era spine — measured
     here, not assumed;
  3. a ready chronology is what promotes the browser `pass1 -> pass2a`
     (the eight promotion sites are pinned in
     `tests/test_profile_seed_reachability_map.py`);
  4. the composer emits the walk ONLY for `current_pass == "pass1"` and
     not identity mode — both arms driven below.

Nothing here is wrong on its own. The skip is what the four correct
behaviours compose into.

Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_profile_seed_ordinary_intake_reachability
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db  # noqa: E402
from api import prompt_composer as _pc  # noqa: E402
from api.routers import chronology_accordion as _ca  # noqa: E402

#: The first topic's marker. Present iff the walk was emitted.
_WALK_MARKER = "1. CHILDHOOD HOME"

#: What `ui/js/narrator-intake.js` requires and `POST /api/people/intake`
#: writes. The three anchors are the whole input to the race.
_INTAKE = {
    "display_name": "Verlie Ostrander",
    "date_of_birth": "1936-11-08",
    "place_of_birth": "Devils Lake, North Dakota",
}


class _Base(unittest.TestCase):
    def setUp(self):
        self.data_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_tmp.cleanup)
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(Path(self.data_tmp.name).resolve())
        self.addCleanup(self._restore_data_dir)

        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.addCleanup(self._restore_db)

        self.pid = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, place_of_birth,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (self.pid, _INTAKE["display_name"], _INTAKE["date_of_birth"],
             _INTAKE["place_of_birth"], "2026-08-26", "2026-08-26"))
        con.commit()
        con.close()

    def _restore_data_dir(self):
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir

    def _restore_db(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── the two halves of the race, as helpers ──────────────────────
    def _chronology(self):
        """What the ordinary narrator's chronology looks like after intake."""
        profile = {"basics": {"fullname": _INTAKE["display_name"],
                              "dob": _INTAKE["date_of_birth"],
                              "pob": _INTAKE["place_of_birth"]}}
        return _ca.build_chronology_accordion_payload(
            person_id=self.pid, profile=profile, questionnaire={},
            promoted_rows=[])

    def _walk_emitted(self, *, current_pass, identity_complete=True):
        prompt = _pc.compose_system_prompt(
            "conv-" + uuid.uuid4().hex[:8],
            runtime71={
                "current_pass": current_pass,
                "identity_complete": identity_complete,
                "assistant_role": "interviewer",
                "speaker_name": _INTAKE["display_name"].split()[0],
                "dob": _INTAKE["date_of_birth"],
                "pob": _INTAKE["place_of_birth"],
            })
        return _WALK_MARKER in prompt


# ── Step 2: the anchors make the chronology ready ───────────────────────

class IntakeAnchorsAloneMakeChronologyReadyTests(_Base):
    """The first half of the race, measured.

    This is the step that is easy to state and easy to get wrong: the
    claim is not that intake *eventually* leads to a chronology, but that
    the three required fields are already sufficient, with no interview
    turn, no promoted rows and no questionnaire.
    """

    def test_the_three_anchors_are_enough(self):
        p = self._chronology()
        self.assertTrue(p["seed_ready"],
                        "intake's own required fields did not produce a ready "
                        "chronology; the race described in the work order "
                        "would not start here")
        self.assertEqual(p["birth_year"], 1936)

    def test_a_full_era_spine_is_derived(self):
        p = self._chronology()
        self.assertEqual(len(p["periods"]), 7,
                         "a partial spine would weaken the claim that "
                         "chronology is READY before the first turn")

    def test_without_a_birthplace_and_dob_it_is_not_ready(self):
        """The contrast case. A narrator lacking the anchors gets
        `no_dob`, which is the branch a testing-only narrator lands in —
        and that narrator is excluded from the walk by identity mode
        instead. Two different exclusions, one outcome."""
        p = _ca.build_chronology_accordion_payload(
            person_id=self.pid, profile={"basics": {}}, questionnaire={},
            promoted_rows=[])
        self.assertFalse(p["seed_ready"])
        self.assertEqual(p.get("reason"), "no_dob")


# ── Step 4: the composer's two exclusions ───────────────────────────────

class TheComposerGateHasTwoExclusionsTests(_Base):
    """Both arms driven through the real composer.

    Neither is a bug. Together they leave no ordinary path in.
    """

    def test_pass1_with_identity_complete_DOES_emit_the_walk(self):
        """The walk is not broken — it works exactly where it is gated.

        Asserted first and deliberately: the defect is reachability, and
        claiming the walk is broken would send a later phase to repair
        something that is fine.
        """
        self.assertTrue(self._walk_emitted(current_pass="pass1"))

    def test_pass2a_excludes_it(self):
        """Chronology readiness closes the gate."""
        self.assertFalse(self._walk_emitted(current_pass="pass2a"))

    def test_identity_mode_excludes_it_even_in_pass1(self):
        """And the narrator WITHOUT the anchors is excluded here."""
        self.assertFalse(
            self._walk_emitted(current_pass="pass1", identity_complete=False))


# ── The defect itself ───────────────────────────────────────────────────

class TheOrdinaryNarratorSkipsTheWalkTests(_Base):
    """THE REACHABILITY DEFECT, executable.

    Read the `expectedFailure` note at the top of this file before
    changing anything here.
    """

    def _pass_after_ordinary_intake(self) -> str:
        """The pass an ordinary narrator's browser holds at their first
        normal turn.

        The promotion happens in the browser, so this models it from the
        server-visible fact that drives it — a ready chronology — rather
        than by importing client code. The eight promotion sites are
        pinned separately in `test_profile_seed_reachability_map.py`; if
        this model and those sites ever disagree, that file fails.
        """
        return "pass2a" if self._chronology()["seed_ready"] else "pass1"

    def test_the_ordinary_narrator_is_promoted_before_their_first_turn(self):
        """Not an expected failure — this part is simply true today."""
        self.assertEqual(self._pass_after_ordinary_intake(), "pass2a")

    @unittest.expectedFailure
    def test_the_ordinary_narrator_reaches_the_walk(self):
        """**THE DEFECT.** Expected to fail until the lane closes.

        IF THIS TEST STARTS PASSING, the reachability work has landed.
        unittest will report the unexpected success as a failure — that
        is intentional, and it is the signal to:

          1. remove the `@unittest.expectedFailure` decorator;
          2. move this test into the acceptance set for the phase that
             fixed it;
          3. record in the work order WHICH change made it pass, because
             "it passes now" without a named cause is how a fix gets
             credited to the wrong commit.

        Do not delete it and do not weaken it.
        """
        self.assertTrue(
            self._walk_emitted(current_pass=self._pass_after_ordinary_intake()),
            "an ordinary new narrator did not reach the ten-topic Profile "
            "Seed walk")

    @unittest.expectedFailure
    def test_a_testing_only_narrator_reaches_it_either(self):
        """The other creation path, excluded for the other reason.

        Without the three anchors the narrator is in identity mode, and
        identity mode mutually excludes the walk. Recorded so that a fix
        aimed only at the promotion does not leave this path skipping.
        """
        self.assertTrue(
            self._walk_emitted(current_pass="pass1", identity_complete=False),
            "a testing-only narrator did not reach the walk either")

    def test_the_two_exclusions_are_genuinely_different(self):
        """Not an expected failure — this is the shape of the problem.

        One narrator is excluded for having ENOUGH information, the
        other for having too little. A single-gate fix that only moves
        the promotion will not close both, which is why the work order
        asks for server-owned progress rather than a gate tweak.
        """
        ordinary_pass = self._pass_after_ordinary_intake()
        self.assertEqual(ordinary_pass, "pass2a")
        self.assertFalse(self._walk_emitted(current_pass=ordinary_pass))
        self.assertFalse(
            self._walk_emitted(current_pass="pass1", identity_complete=False))
        # …and the walk itself is fine in the state nobody reaches.
        self.assertTrue(self._walk_emitted(current_pass="pass1"))
