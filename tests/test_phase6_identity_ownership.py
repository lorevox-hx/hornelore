"""Phase 6 Intervention 1 — server-resolved identity outranks the browser.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_phase6_identity_ownership

THE DEFECT, MEASURED RATHER THAN REASONED
=========================================

Phase 6 Baseline 2 (Ada Pruitt, 2026-09-07, ten turns under Lean): every
one of the ten prompts contained BOTH

    KNOWN IDENTITY FACTS:
    - Name: Ada Pruitt
    - Date of birth: 1948-03-17
    - Place of birth: Barre, Vermont

and

    IDENTITY MODE: Lori is gently gathering who the narrator is.
    Still needed: name, date of birth...

with `effective_pass='identity'` while `current_pass='pass1'`. Lori asked
for a known identity fact on 10 of 10 turns. She was obeying the prompt.

THE CHAIN, each link read:

  `app.js:5341` `hasIdentityBasics74()` needs name AND dob AND pob from
      `state.profile.basics`;
  `session-loop.js:298-301` populates `basics.fullname`/`preferred` only
      when the narrator SAYS their name this session;
  `app.js:3034-3036` ships that verdict as `identity_complete` /
      `identity_phase` / `effective_pass`;
  `prompt_composer.py:4418`
      `identity_mode = (effective_pass == "identity") or (not
      identity_complete)` — both disjuncts True for Ada;
  `chat_ws` had the server's resolved state in `_ps_state` the whole
      time and did not use it to correct those fields.

Ada's Profile Seed walk is COMPLETED, so its plan is IDLE and no
onboarding payload is attached — which is why the composer had nothing
attested to prefer over the browser. IDLE must not mean "trust stale
browser identity state"; that is case C below.

WHAT IS NOT TESTED HERE, DELIBERATELY. The IDENTITY MODE collection
branch is untouched: a genuinely new narrator must still walk name ->
DOB -> birthplace. Case B pins that.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from api.services import profile_seed_runtime as psr      # noqa: E402


def _browser_runtime(**over):
    """What the BROWSER sends for a narrator who has not said their name.

    Not invented: these are the values measured in every Baseline 2
    trace for Ada — a narrator with DOB and POB in `basics` but no
    `fullname`/`preferred`.
    """
    rt = {
        "identity_complete": False,
        "identity_phase": "incomplete",
        "effective_pass": "identity",
        "current_pass": "pass1",
        "speaker_name": None,
        "dob": "1948-03-17",
        "pob": "Barre, Vermont",
    }
    rt.update(over)
    return rt


#: A completed walk, as `ResolvedState.as_dict()` renders it.
COMPLETE_STATE = {
    "person_id": "ada", "enrolled": True, "status": "completed",
    "identity_complete": True, "active_topic_id": None,
    "remaining_topics": [], "version": 3,
}

#: A narrator still being onboarded.
INCOMPLETE_STATE = {
    "person_id": "new", "enrolled": True, "status": "active",
    "identity_complete": False, "active_topic_id": "childhood_home",
    "remaining_topics": ["childhood_home"], "version": 1,
}


class A_ServerCompleteOverridesStaleBrowser(unittest.TestCase):
    """Server says complete, browser falsely says incomplete/identity."""

    def setUp(self):
        self.out = psr.apply_server_identity(_browser_runtime(),
                                             COMPLETE_STATE)

    def test_identity_complete_becomes_true(self):
        self.assertTrue(self.out["identity_complete"])

    def test_identity_phase_resolves_to_complete(self):
        self.assertEqual(self.out["identity_phase"], "complete")

    def test_stale_identity_pass_cannot_keep_identity_mode_alive(self):
        """The first disjunct of prompt_composer.py:4418.

        Correcting `identity_complete` alone would fix nothing — an
        `effective_pass` of "identity" re-activates identity mode by
        itself.
        """
        self.assertNotEqual(self.out["effective_pass"], "identity")

    def test_the_real_interview_pass_is_preserved_not_invented(self):
        """`current_pass` was 'pass1' throughout Baseline 2."""
        self.assertEqual(self.out["effective_pass"], "pass1")

    def test_known_identity_facts_are_untouched(self):
        for key in ("dob", "pob"):
            self.assertEqual(self.out[key], _browser_runtime()[key])

    def test_the_composer_predicate_now_reads_false(self):
        """The production expression, reproduced from prompt_composer:4418."""
        identity_mode = ((self.out.get("effective_pass") == "identity")
                         or (not self.out.get("identity_complete")))
        self.assertFalse(
            identity_mode,
            "IDENTITY MODE would still render for a narrator whose "
            "identity the server has resolved as complete")

    def test_the_input_runtime_is_not_mutated(self):
        original = _browser_runtime()
        psr.apply_server_identity(original, COMPLETE_STATE)
        self.assertFalse(original["identity_complete"],
                         "runtime71 is threaded through several consumers; "
                         "this must return a new dict")


class B_IncompleteNarratorIsUntouched(unittest.TestCase):
    """A genuinely new narrator must still be onboarded, unchanged."""

    def test_server_incomplete_leaves_every_identity_field_alone(self):
        browser = _browser_runtime()
        out = psr.apply_server_identity(browser, INCOMPLETE_STATE)
        for key in ("identity_complete", "identity_phase", "effective_pass"):
            self.assertEqual(out[key], browser[key])

    def test_the_composer_predicate_still_activates_identity_mode(self):
        out = psr.apply_server_identity(_browser_runtime(), INCOMPLETE_STATE)
        identity_mode = ((out.get("effective_pass") == "identity")
                         or (not out.get("identity_complete")))
        self.assertTrue(identity_mode, "onboarding regressed")

    def test_no_resolved_state_at_all_changes_nothing(self):
        browser = _browser_runtime()
        for state in (None, {}, "not-a-mapping"):
            out = psr.apply_server_identity(browser, state)
            self.assertEqual(out["identity_complete"], False)
            self.assertEqual(out["effective_pass"], "identity")

    def test_a_historical_narrator_with_no_row_is_untouched(self):
        """`resolve_effective` returns None for an unenrolled narrator."""
        out = psr.apply_server_identity(_browser_runtime(), None)
        self.assertEqual(out["identity_phase"], "incomplete")


class C_CompletedWalkPlanningIdle(unittest.TestCase):
    """Ada's exact shape: completed walk, IDLE plan, no attested payload.

    A completed walk plans IDLE and `attach_onboarding` adds nothing, so
    before this fix the composer had no server evidence to prefer and
    fell through to the browser. IDLE must not mean "trust the browser".
    """

    def test_idle_plan_still_gets_the_server_override(self):
        from api.services import profile_seed_turn as pst
        plan = pst.plan_turn(state=dict(COMPLETE_STATE), history=[],
                             narrator_text="My brother Dennis walked me "
                                           "to school.", eligible=True)
        self.assertEqual(plan.action, pst.IDLE,
                         "a completed walk must plan IDLE")

        # attach_onboarding contributes nothing on IDLE ...
        attached = psr.attach_onboarding(_browser_runtime(), plan,
                                         COMPLETE_STATE)
        self.assertIsNone(
            psr.onboarding_payload(plan, COMPLETE_STATE),
            "IDLE attaches no payload — which is why the composer had "
            "nothing attested to prefer")

        # ... and the override still fires.
        out = psr.apply_server_identity(attached, COMPLETE_STATE)
        identity_mode = ((out.get("effective_pass") == "identity")
                         or (not out.get("identity_complete")))
        self.assertFalse(identity_mode)


class D_TheComposerRendersNoIdentityMode(unittest.TestCase):
    """Production boundary: the real composer, not the predicate alone."""

    def test_identity_mode_directive_is_absent_for_a_resolved_narrator(self):
        try:
            from api import prompt_composer
        except Exception as exc:                            # pragma: no cover
            self.skipTest(f"prompt_composer did not import: {exc}")

        corrected = psr.apply_server_identity(_browser_runtime(),
                                              COMPLETE_STATE)
        # The identity block must still carry the facts ...
        facts = prompt_composer._known_identity_facts_block({
            "speaker_name": "", "dob": corrected["dob"],
            "pob": corrected["pob"],
            "profile_seed": {"preferred_name": "Ada Pruitt"},
        })
        self.assertIn("- Name: Ada Pruitt", facts)
        self.assertIn("- Date of birth: 1948-03-17", facts)
        self.assertIn("- Place of birth: Barre, Vermont", facts)
        # ... while the collection directive is gone.
        self.assertNotIn("IDENTITY MODE", facts)
        self.assertNotIn("Still needed", facts)


if __name__ == "__main__":
    unittest.main()
