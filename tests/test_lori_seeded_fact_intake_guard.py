"""
BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01
======================================

Tests for the seeded-fact intake-question post-LLM safety net in
`services.lori_response_guards`.

Mable Earliest from the 2026-06-17 full-family harness:
  "You were born in Albany, Georgia, in 1942?"
  with seeded place_of_birth='Albany, Georgia', birth_year='1942'.

The narrator is asked to confirm a fact the operator already entered.
The fix:
  1. Prompt-side directive (DO NOT ASK FOR SEEDED FACTS) is primary
  2. Post-LLM detect+repair is the safety net here
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from server.code.api.services.lori_response_guards import (
    apply_response_guards,
    detect_seeded_fact_intake,
    repair_seeded_fact_intake,
)


class DetectSeededFactIntakeTest(unittest.TestCase):
    def test_mable_were_you_born_in_albany_with_seeded_pob_fires(self):
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        text = "You were born in Albany, Georgia, in 1942?"
        self.assertEqual(detect_seeded_fact_intake(text, seeded), "place_of_birth")

    def test_john_do_you_live_in_las_vegas_with_seeded_residence_fires(self):
        seeded = {"current_residence": "Las Vegas, New Mexico"}
        text = "Do you currently live in Las Vegas, New Mexico?"
        self.assertEqual(
            detect_seeded_fact_intake(text, seeded),
            "current_residence",
        )

    def test_john_do_you_work_at_pecos_schools_with_seeded_work_fires(self):
        seeded = {"current_work": "Pecos Schools"}
        text = "Do you currently work at Pecos Schools?"
        self.assertEqual(
            detect_seeded_fact_intake(text, seeded),
            "current_work",
        )

    def test_is_your_mother_alive_with_seeded_parent_fires(self):
        seeded = {"parent_alive": "mother alive at 99"}
        text = "Is your mother still alive?"
        self.assertEqual(detect_seeded_fact_intake(text, seeded), "parent_alive")

    def test_no_seeded_facts_returns_none(self):
        text = "You were born in Albany, Georgia, in 1942?"
        self.assertIsNone(detect_seeded_fact_intake(text, None))
        self.assertIsNone(detect_seeded_fact_intake(text, {}))

    def test_lived_experience_question_does_not_fire(self):
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        text = "What do you remember about Albany when you were little?"
        self.assertIsNone(detect_seeded_fact_intake(text, seeded))

    def test_seeded_field_empty_does_not_fire(self):
        seeded = {"place_of_birth": ""}  # field exists but empty
        text = "You were born in Albany, Georgia?"
        self.assertIsNone(detect_seeded_fact_intake(text, seeded))


class RepairSeededFactIntakeTest(unittest.TestCase):
    def test_pob_rewrites_to_lived_experience(self):
        seeded = {"place_of_birth": "Albany, Georgia"}
        out = repair_seeded_fact_intake("place_of_birth", seeded)
        self.assertIn("Albany, Georgia", out)
        self.assertIn("remember", out.lower())

    def test_residence_rewrites_to_lived_experience(self):
        seeded = {"current_residence": "Las Vegas, New Mexico"}
        out = repair_seeded_fact_intake("current_residence", seeded)
        self.assertIn("Las Vegas, New Mexico", out)

    def test_current_work_rewrites_to_lived_experience(self):
        seeded = {"current_work": "Pecos Schools"}
        out = repair_seeded_fact_intake("current_work", seeded)
        self.assertIn("Pecos Schools", out)

    def test_spanish_target_language(self):
        seeded = {"place_of_birth": "Lima"}
        out = repair_seeded_fact_intake(
            "place_of_birth", seeded, target_language="es",
        )
        self.assertIn("Lima", out)
        self.assertIn("recuerdas", out.lower())


class ApplyResponseGuardsIntegrationTest(unittest.TestCase):
    def test_mable_seeded_intake_repaired(self):
        seeded = {"place_of_birth": "Albany, Georgia", "birth_year": "1942"}
        text = "You were born in Albany, Georgia, in 1942?"
        out, fired = apply_response_guards(
            text, narrator_text="I was born in Albany.", seeded_facts=seeded,
        )
        self.assertIn("seeded_fact_intake", fired)
        # Rewritten to lived-experience question
        self.assertNotIn("Were you born", out)
        self.assertIn("Albany", out)

    def test_no_seeded_facts_passes_through_intake_question(self):
        # Without seeded_facts, the guard doesn't fire — the LLM is
        # treated as authoritative (no intake-question detection).
        text = "You were born in Albany, Georgia, in 1942?"
        out, fired = apply_response_guards(
            text, narrator_text="I was born here.",
        )
        self.assertNotIn("seeded_fact_intake", fired)
        self.assertEqual(out, text)

    def test_lived_experience_question_passes_through(self):
        seeded = {"place_of_birth": "Albany, Georgia"}
        text = "What do you remember about Albany when you were little?"
        out, fired = apply_response_guards(
            text, narrator_text="I was born here.", seeded_facts=seeded,
        )
        self.assertNotIn("seeded_fact_intake", fired)
        self.assertEqual(out, text)


if __name__ == "__main__":
    unittest.main()
