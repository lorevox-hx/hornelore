"""
BUG-LORI-META-RESPONSE-LEAK-01
==================================

Tests for the meta-response leak guard in
`services.lori_response_guards.detect_meta_response_leak` and
`repair_meta_response_leak`.

Reference case from 2026-06-17 full-family harness — Richard Earliest:

  "Here is a response that follows the rules and guidelines:
   "You mentioned Magee Hospital where you were born, your parents, and the
   Catholic Church, where you attended Mass and served as an altar boy. You
   also talked about your family's neighborhood in Oakland, near the river,
   and your father's work at Jones and Laughlin. What do you remember about
   your daily life in Oakland, particularly during your early years, around
   the time you started school?"
   This response reflects the narrator's mentions of Magee Hospital, the
   Catholic Church, and Oakland, and asks a follow-up question..."

The guard should:
  1. Detect the leak
  2. Recover the quoted draft (the actual reflective response)
  3. Strip the preamble + postamble
  4. Return the recovered draft as final_text
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
    detect_meta_response_leak,
    repair_meta_response_leak,
)


class DetectMetaResponseLeakTest(unittest.TestCase):
    def test_here_is_a_response_that_follows_fires(self):
        text = (
            "Here is a response that follows the rules and guidelines:\n"
            "\"You mentioned Magee Hospital where you were born...\""
        )
        self.assertTrue(detect_meta_response_leak(text))

    def test_this_response_reflects_postamble_fires(self):
        text = (
            "You mentioned Magee Hospital. What do you remember?\n\n"
            "This response reflects the narrator's mentions of Magee Hospital."
        )
        self.assertTrue(detect_meta_response_leak(text))

    def test_what_a_rich_evocative_narrative_fires(self):
        text = (
            "What a rich and evocative narrative! Let me capture a few key points."
        )
        self.assertTrue(detect_meta_response_leak(text))

    def test_im_so_grateful_to_be_listening_fires(self):
        text = (
            "Mount Olive AME. What a rich and evocative narrative! "
            "I'm so grateful to be listening to your story."
        )
        self.assertTrue(detect_meta_response_leak(text))

    def test_normal_response_does_not_fire(self):
        text = (
            "Magee Hospital and Oakland near the river. "
            "What do you remember about Sunday mornings back then?"
        )
        self.assertFalse(detect_meta_response_leak(text))

    def test_natural_use_of_response_word_does_not_fire(self):
        # Should not false-fire on the word "response" used naturally
        text = "I notice your response to that question was thoughtful. Tell me more."
        self.assertFalse(detect_meta_response_leak(text))


class RepairMetaResponseLeakTest(unittest.TestCase):
    def test_recovers_quoted_draft_when_present(self):
        text = (
            "Here is a response that follows the rules and guidelines:\n"
            "\"You mentioned Magee Hospital where you were born and the "
            "Catholic Church. What was a typical Sunday morning like?\"\n"
            "This response reflects the narrator's mentions of Magee Hospital."
        )
        repaired = repair_meta_response_leak(text)
        # The recovered draft should be the quoted real-response
        self.assertIn("Magee Hospital where you were born", repaired)
        self.assertIn("Sunday morning", repaired)
        # And NOT contain the preamble or postamble
        self.assertNotIn("Here is a response", repaired)
        self.assertNotIn("This response reflects", repaired)

    def test_strips_preamble_without_quoted_draft(self):
        text = (
            "Here is a response that follows the rules:\n"
            "Magee Hospital and Oakland. What does Sunday morning bring?"
        )
        repaired = repair_meta_response_leak(text)
        self.assertNotIn("Here is a response", repaired)
        self.assertIn("Magee Hospital", repaired)

    def test_returns_continuation_when_only_meta(self):
        text = "This response invites further reflection on the narrator's history."
        repaired = repair_meta_response_leak(text)
        # Falls back to a deterministic continuation
        self.assertIsNotNone(repaired)
        self.assertGreater(len(repaired), 0)

    def test_spanish_target_language_returns_spanish_continuation(self):
        text = "This response reflects the narrator's history."
        repaired = repair_meta_response_leak(text, target_language="es")
        self.assertIn("Cuéntame", repaired)


class ApplyResponseGuardsIntegrationTest(unittest.TestCase):
    def test_richard_earliest_real_failure_recovery(self):
        """Exact Richard Earliest text from 2026-06-17 full-family run."""
        leaked = (
            "Here is a response that follows the rules and guidelines:\n\n"
            "\"You mentioned Magee Hospital where you were born, your parents, "
            "and the Catholic Church, where you attended Mass and served as an "
            "altar boy. You also talked about your family's neighborhood in "
            "Oakland, near the river, and your father's work at Jones and Laughlin. "
            "What do you remember about your daily life in Oakland, particularly "
            "during your early years, around the time you started school?\"\n\n"
            "This response reflects the narrator's mentions of Magee Hospital, "
            "the Catholic Church, and Oakland, and asks a follow-up question "
            "that invites the narrator to share more about their daily life "
            "during this period."
        )
        text, fired = apply_response_guards(
            leaked,
            narrator_text="I was born at Magee Hospital in 1952. We lived in Oakland.",
        )
        self.assertIn("meta_response_leak", fired)
        # Recovered text should be the quoted reflective draft
        self.assertIn("Magee Hospital", text)
        self.assertNotIn("Here is a response", text)
        self.assertNotIn("This response reflects", text)

    def test_clean_response_passes_through_unchanged(self):
        text = "Magee Hospital and Oakland. What does Sunday morning bring?"
        out, fired = apply_response_guards(
            text, narrator_text="I was born at Magee Hospital."
        )
        self.assertEqual(out, text)
        self.assertEqual(fired, [])

    def test_meta_leak_then_dangling_determiner_both_fire(self):
        text = (
            "Here is a response that follows the rules:\n"
            "\"Tell me more about the.\""
        )
        out, fired = apply_response_guards(text, narrator_text="I was born here.")
        # Meta-leak fires first; recovered draft has dangling determiner so
        # dangling-determiner also fires.
        self.assertIn("meta_response_leak", fired)
        self.assertIn("dangling_determiner", fired)


if __name__ == "__main__":
    unittest.main()
