"""Phase 6 Intervention 2 — a completed walk never sees the legacy list.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_phase6_completed_walk_suppression

THE DEFECT, MEASURED
====================

Run 3 (Ada Pruitt, 2026-09-08, ten turns under Lean, after Intervention
1 removed IDENTITY MODE): all ten prompts still carried

    PROFILE SEED QUESTIONS (ask in this order, skipping what you
    already know):
      1. CHILDHOOD HOME - ...
      5. EDUCATION - How far did they go in school - did they go to
         college?

and Lori asked on turn 8: "How far did you go in school - did you attend
college?" — Ada's schooling being on file (Spaulding High School; two
years at Vermont Technical College). Recitation, not a model decision.

THE CHAIN, each link read:

  Ada's walk is COMPLETED, so `plan_turn` returns IDLE — correct;
  `onboarding_payload()` returns None for IDLE — correct;
  `attach_onboarding()` then STRIPS the reserved keys — also correct,
      so no stale question survives;
  but the composer's suppression at `prompt_composer.py:5115` keys on
      `profile_seed_onboarding_active()`, which is payload-derived.

With the payload gone, a COMPLETED narrator and a HISTORICAL narrator
with no onboarding row are indistinguishable at that branch, and the
completed one falls into the `current_pass == "pass1"` legacy path.

THE INVARIANT: once a narrator has completed Profile Seed, no browser
pass, stale client value or IDLE plan may resurrect Profile Seed
questions. Historical narrators keep the legacy path unchanged.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from api import prompt_composer as pc                      # noqa: E402
from api.services import profile_seed_runtime as psr       # noqa: E402
from api.services import profile_seed_turn as pst          # noqa: E402


COMPLETED = {"person_id": "ada", "enrolled": True, "status": "completed",
             "identity_complete": True, "active_topic_id": None,
             "known_topics": [], "remaining_topics": [], "version": 3}

ACTIVE = {"person_id": "new", "enrolled": True, "status": "active",
          "identity_complete": False, "active_topic_id": "childhood_home",
          "known_topics": [], "remaining_topics": ["childhood_home"],
          "version": 1}


def _browser_runtime(**over):
    rt = {"current_pass": "pass1", "effective_pass": "pass1",
          "identity_complete": True, "identity_phase": "complete",
          "dob": "1948-03-17", "pob": "Barre, Vermont"}
    rt.update(over)
    return rt


class A_CompletedIdleBrowserPass1(unittest.TestCase):
    """Ada's exact shape."""

    def setUp(self):
        self.plan = pst.plan_turn(state=dict(COMPLETED), history=[],
                                  narrator_text="We used to drive up to "
                                                "Groton Pond.", eligible=True)
        rt = psr.attach_onboarding(_browser_runtime(), self.plan, COMPLETED)
        self.rt = psr.attach_seed_status(rt, COMPLETED)

    def test_the_plan_is_idle_and_carries_no_payload(self):
        self.assertEqual(self.plan.action, pst.IDLE)
        self.assertIsNone(psr.onboarding_payload(self.plan, COMPLETED))
        self.assertNotIn(pc.PROFILE_SEED_ONBOARDING_KEY, self.rt)

    def test_the_completed_status_survives_the_idle_strip(self):
        """`attach_onboarding` clears reserved keys; status is restamped."""
        self.assertEqual(self.rt[pc.PROFILE_SEED_STATUS_KEY], "completed")

    def test_the_walk_reads_as_completed(self):
        self.assertTrue(pc.profile_seed_walk_completed(self.rt))

    def test_completed_is_not_disguised_as_an_active_walk(self):
        """`attested` means a live plan. It must stay false here.

        Reusing attestation to suppress the block would have worked and
        would have lied to every other consumer that reads it as
        "onboarding is running".
        """
        self.assertFalse(self.rt.get(pc.PROFILE_SEED_SERVER_ATTESTED_KEY))
        self.assertFalse(pc.profile_seed_onboarding_active(self.rt))


class B_StaleClientValuesCannotResurrectIt(unittest.TestCase):
    """No browser pass may bring the questionnaire back."""

    def test_every_browser_pass_still_reads_completed(self):
        for pass_name in ("pass1", "pass2a", "pass3", "identity", "", None):
            with self.subTest(pass_name=pass_name):
                rt = psr.attach_seed_status(
                    _browser_runtime(current_pass=pass_name,
                                     effective_pass=pass_name),
                    COMPLETED)
                self.assertTrue(pc.profile_seed_walk_completed(rt))

    def test_a_client_supplied_status_is_stripped_before_resolution(self):
        """Only the server may say a walk is complete."""
        forged = _browser_runtime()
        forged[pc.PROFILE_SEED_STATUS_KEY] = "completed"
        cleaned = psr.sanitize_client_runtime(forged)
        self.assertNotIn(pc.PROFILE_SEED_STATUS_KEY, cleaned)
        self.assertFalse(pc.profile_seed_walk_completed(cleaned))

    def test_the_status_key_is_reserved(self):
        self.assertIn(pc.PROFILE_SEED_STATUS_KEY,
                      pc.PROFILE_SEED_RESERVED_RUNTIME_KEYS)


class C_HistoricalNarratorKeepsTheLegacyPath(unittest.TestCase):
    """No row means no key — and the legacy block must still render."""

    def test_no_resolved_state_leaves_no_status_key(self):
        rt = psr.attach_seed_status(_browser_runtime(), None)
        self.assertNotIn(pc.PROFILE_SEED_STATUS_KEY, rt)
        self.assertFalse(pc.profile_seed_walk_completed(rt))

    def test_a_historical_runtime_is_byte_identical(self):
        browser = _browser_runtime()
        self.assertEqual(psr.attach_seed_status(browser, None), browser)

    def test_a_stale_status_key_is_removed_when_state_is_gone(self):
        stale = _browser_runtime()
        stale[pc.PROFILE_SEED_STATUS_KEY] = "completed"
        self.assertNotIn(pc.PROFILE_SEED_STATUS_KEY,
                         psr.attach_seed_status(stale, None))


class D_ActiveWalkIsUnchanged(unittest.TestCase):
    """Server-owned onboarding keeps working exactly as before."""

    def setUp(self):
        self.plan = pst.plan_turn(state=dict(ACTIVE), history=[],
                                  narrator_text="Hello.", eligible=True)
        rt = psr.attach_onboarding(_browser_runtime(), self.plan, ACTIVE)
        self.rt = psr.attach_seed_status(rt, ACTIVE)

    def test_the_payload_still_attaches_and_attests(self):
        self.assertIn(self.plan.action, (pst.PRESENT, pst.HOLD))
        self.assertIn(pc.PROFILE_SEED_ONBOARDING_KEY, self.rt)
        self.assertTrue(self.rt[pc.PROFILE_SEED_SERVER_ATTESTED_KEY])
        self.assertTrue(pc.profile_seed_onboarding_active(self.rt))

    def test_an_active_walk_is_not_completed(self):
        self.assertEqual(self.rt[pc.PROFILE_SEED_STATUS_KEY], "active")
        self.assertFalse(pc.profile_seed_walk_completed(self.rt))

    def test_paused_and_pending_are_not_completed_either(self):
        for status in ("pending", "paused", "active"):
            with self.subTest(status=status):
                state = dict(ACTIVE, status=status)
                rt = psr.attach_seed_status(_browser_runtime(), state)
                self.assertFalse(pc.profile_seed_walk_completed(rt))


class E_TheSuppressionBranchItself(unittest.TestCase):
    """The production expression at prompt_composer.py:5115.

    Reproduced from the source rather than described, so a mutation to
    either predicate fails here.
    """

    def _renders_legacy(self, rt):
        """True when the composer would fall into the pass1 branch."""
        if pc.profile_seed_onboarding_active(rt):
            return False
        if pc.profile_seed_walk_completed(rt):
            return False
        return (rt.get("current_pass") == "pass1")

    def test_completed_narrator_gets_no_legacy_questionnaire(self):
        rt = psr.attach_seed_status(_browser_runtime(), COMPLETED)
        self.assertFalse(
            self._renders_legacy(rt),
            "a narrator who finished the walk was asked the ten "
            "questions again")

    def test_historical_narrator_still_gets_it(self):
        rt = psr.attach_seed_status(_browser_runtime(), None)
        self.assertTrue(
            self._renders_legacy(rt),
            "historical narrators must keep the legacy path")

    def test_active_walk_is_suppressed_by_the_payload_as_before(self):
        plan = pst.plan_turn(state=dict(ACTIVE), history=[],
                             narrator_text="Hello.", eligible=True)
        rt = psr.attach_seed_status(
            psr.attach_onboarding(_browser_runtime(), plan, ACTIVE), ACTIVE)
        self.assertFalse(self._renders_legacy(rt))


if __name__ == "__main__":
    unittest.main()
