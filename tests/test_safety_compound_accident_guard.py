"""
BUG-SAFETY-CHILD-ABUSE-FALSE-POSITIVE-DEATH-CAR-01
==================================================

Tests for the accident-death context guard in safety._check_compound_child_abuse.

The compound child_abuse trigger uses (parent_role + harm_verb) at confidence
0.70 even without an age signal. Before the guard, ordinary biographical
oral-history content was firing child_abuse:

  "John's father died when John was a teenager. He was changing a tire
   and was hit by a car."
   → perpetrator='father', harm_verb='hit' → child_abuse 0.70 → operator notify

  "I was born in Las Vegas. My father Eliseo was a sheep rancher."
   → perpetrator='father', harm_verb=? → child_abuse 0.70 (Stefi false-pos)

The guard suppresses the compound trigger when biographical accident /
death narration dominates. Real abuse triggers (raped, molested, beat me,
hit me, forced me, etc. — first-person direct-object harm) are unaffected
because those fire via _SIMPLE_TRIGGERS not the compound path.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

import unittest

from server.code.api.safety import (
    _check_compound_child_abuse,
    _normalise,
    detect_crisis,
    scan_answer,
)


# ── WO-LEAN-LORI-RUNTIME-01 Phase 3B ──────────────────────────────────
# This suite tests the ACTIVE deterministic safety layer, which as of
# 2026-08-04 is not the default: `HORNELORE_SAFETY_STATE` defaults to
# "parked" and `safety.scan_answer()` returns None for every caller.
#
# Opting in explicitly, rather than relaxing the assertions, is the point
# of parking rather than deleting: reactivation must land on suites that
# still hold the feature to its original contract. Restored afterwards so
# the parked default is what every other module sees, and set on
# os.environ (not just locally) because parts of this suite run in a
# subprocess that inherits it.
_SAVED_SAFETY_STATE = None


def setUpModule():  # noqa: N802
    import os
    global _SAVED_SAFETY_STATE
    _SAVED_SAFETY_STATE = os.environ.get("HORNELORE_SAFETY_STATE")
    os.environ["HORNELORE_SAFETY_STATE"] = "active"


def tearDownModule():  # noqa: N802
    import os
    if _SAVED_SAFETY_STATE is None:
        os.environ.pop("HORNELORE_SAFETY_STATE", None)
    else:
        os.environ["HORNELORE_SAFETY_STATE"] = _SAVED_SAFETY_STATE


def _check(text: str):
    """Convenience: normalise and run the compound check."""
    return _check_compound_child_abuse(_normalise(text))


class AccidentDeathSuppressesCompoundTest(unittest.TestCase):
    """The biographical accident/death guard must suppress child_abuse."""

    def test_john_adolescence_father_died_changing_tire(self):
        """
        Reference case from full-family run 2026-06-17:
        BUG-SAFETY-CHILD-ABUSE-FALSE-POSITIVE-DEATH-CAR-01.
        Before the guard, this produced child_abuse=0.70 + operator notify.
        """
        text = (
            "When I was a teenager, my father died. He was changing a tire "
            "and was hit by a car. I also traveled in Europe as a teenager."
        )
        result = scan_answer(text)
        if result is not None:
            self.assertNotEqual(
                result.category, "child_abuse",
                f"child_abuse should be suppressed, got {result!r}",
            )

    def test_third_person_father_died_hit_by_car(self):
        """
        Operator-directive third-person variant (the bad Chrome harness
        sent these as 'John's father died... was hit by a car'). Same
        underlying biographical accident — still must not fire child_abuse.
        """
        text = (
            "John's father died when John was a teenager while changing "
            "a tire and being hit by a car."
        )
        result = scan_answer(text)
        if result is not None:
            self.assertNotEqual(result.category, "child_abuse")

    def test_stefi_innocent_family_biography(self):
        """
        Stefi (Crypto-Jewish New Mexico) excerpt — pure biographical
        text mentioning father and mother. Before guard, the full chapter
        somewhere produced child_abuse=0.70 [compound trigger] on this
        narrator. The guard suppresses any compound mis-fire on this
        class of innocent family-history text.
        """
        text = (
            "I was born in Las Vegas, New Mexico, on the twenty-third of "
            "May, 1944. My father Eliseo was a sheep rancher in San Miguel "
            "County, third generation on the land. My mother Aurelia was "
            "from Mora. My grandmother died in 1985, peacefully."
        )
        result = scan_answer(text)
        if result is not None:
            self.assertNotEqual(result.category, "child_abuse")

    def test_grandfather_died_medical(self):
        """Medical death of grandparent — biographical, not abuse."""
        text = "My grandfather died of cancer when I was twelve."
        self.assertIsNone(_check(text))

    def test_mother_killed_in_accident(self):
        """Parent killed in accident — biographical, not abuse."""
        text = "My mother was killed by a drunk driver in 1978."
        self.assertIsNone(_check(text))

    def test_mechanical_accident_only(self):
        """Mechanical accident context alone is sufficient to suppress."""
        text = "Dad was under the truck fixing the brake when it slipped."
        self.assertIsNone(_check(text))


class TruePositiveAbuseStillFiresTest(unittest.TestCase):
    """Real abuse content MUST still fire. The guard must not weaken safety."""

    def test_first_person_raped_still_triggers(self):
        """First-person rape disclosure → suicidal_ideation/sexual_abuse pattern."""
        text = "I was raped when I was 12."
        result = scan_answer(text)
        self.assertIsNotNone(result)
        self.assertTrue(result.triggered)
        # Simple trigger 'i was raped' fires sexual_abuse @ 0.95
        self.assertEqual(result.category, "sexual_abuse")

    def test_molested_by_uncle_at_age_8_still_triggers(self):
        """Classic compound child_abuse case must still fire."""
        text = "My uncle molested me when I was 8 years old."
        result = scan_answer(text)
        self.assertIsNotNone(result)
        self.assertTrue(result.triggered)
        # 'molested' fires the simple sexual_abuse trigger @ 0.90
        # Even if compound suppressed by future false-positive guard
        # additions, the simple trigger keeps abuse detection working.
        self.assertIn(result.category, ("sexual_abuse", "child_abuse"))

    def test_stepfather_hit_me_growing_up_still_triggers(self):
        """Growing-up + perpetrator + harm = real child_abuse case."""
        text = "My stepfather hit me when I was growing up."
        # 'hit me' fires simple trigger physical_abuse @ 0.78
        result = scan_answer(text)
        self.assertIsNotNone(result)
        self.assertTrue(result.triggered)

    def test_compound_child_abuse_no_death_context_still_fires(self):
        """Compound check with perp+harm but NO death/accident context fires."""
        # 'My father hurt me' — perp + harm, no accident-death context
        text = "My father hurt me when I was little."
        result = _check(text)
        self.assertIsNotNone(result, "compound trigger should fire without accident context")
        self.assertEqual(result[0], "child_abuse")


class SuicidalIdeationUnaffectedTest(unittest.TestCase):
    """Acute self-harm patterns must continue to route correctly."""

    def test_kill_myself_still_acute(self):
        result = scan_answer("I want to kill myself.")
        self.assertIsNotNone(result)
        self.assertTrue(result.triggered)
        self.assertEqual(result.category, "suicidal_ideation")

    def test_kill_myself_with_father_died_context_still_fires(self):
        """
        Acute ideation must still fire even when biographical accident
        context is present (compound child_abuse is suppressed but
        unrelated simple triggers must not be).
        """
        text = (
            "My father died in a car accident when I was a teenager. "
            "Sometimes I think about killing myself."
        )
        result = scan_answer(text)
        self.assertIsNotNone(result)
        self.assertTrue(result.triggered)
        self.assertEqual(result.category, "suicidal_ideation")


if __name__ == "__main__":
    unittest.main()
