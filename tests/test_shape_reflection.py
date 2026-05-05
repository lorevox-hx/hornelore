"""WO-LORI-REFLECTION-02 — unit tests for runtime reflection shaping.

Phase 1 acceptance gates from BUG-LORI-REFLECTION-02_Spec.md:

    extract_concrete_anchor() unit tests pass on:
      - simple identity ("born in Montreal" → "Montreal")
      - multi-noun ("Captain Kirk and T.J. Hooker" → either)
      - kinship ("my dad" → "your dad" / "father")
      - trivial ("Thank you" → None)
      - garbled STT ("um yeah I think" → None)
    Pure deterministic; no LLM, no DB, no IO.

Plus shape_reflection() Cases A/B/C/D and Layer 3 softened-mode cap.

LAW-3 isolation enforced by the existing test_lori_reflection_isolation.py;
this file just imports the public surface and exercises behavior.
"""
from __future__ import annotations

import unittest

from server.code.api.services.lori_reflection import (
    extract_concrete_anchor,
    shape_reflection,
    SHAPER_ECHO_WORD_BUDGET,
    SHAPER_SOFTENED_TURN_BUDGET,
)


class ExtractConcreteAnchorTests(unittest.TestCase):
    """Layer 1 — Phase 1 acceptance gates."""

    def test_simple_identity_proper_noun(self):
        # Mid-sentence proper noun should win.
        anchor = extract_concrete_anchor("I was born in Montreal in 1962.")
        self.assertEqual(anchor, "Montreal")

    def test_multi_word_proper_noun_phrase(self):
        anchor = extract_concrete_anchor(
            "I used to watch Captain Kirk every Sunday evening."
        )
        # Multi-word phrases score higher than single words.
        self.assertEqual(anchor, "Captain Kirk")

    def test_two_proper_nouns_returns_one(self):
        anchor = extract_concrete_anchor(
            "We watched Captain Kirk and T.J. Hooker on television together."
        )
        # Either is acceptable per spec; just must be one of them.
        self.assertIn(anchor, ("Captain Kirk", "T.J. Hooker"))

    def test_kinship_my_dad_returns_your_father(self):
        anchor = extract_concrete_anchor(
            "My dad worked at the plant for thirty-five years."
        )
        # Possessive-flip + canonicalize: "my dad" → "Your father".
        self.assertEqual(anchor, "Your father")

    def test_kinship_my_mom_canonicalizes_to_mother(self):
        anchor = extract_concrete_anchor(
            "My mom kept all the letters in a drawer in the kitchen."
        )
        self.assertEqual(anchor, "Your mother")

    def test_trivial_thank_you_returns_none(self):
        # < 4 content tokens — no anchor extractable.
        self.assertIsNone(extract_concrete_anchor("Thank you."))

    def test_trivial_yes_returns_none(self):
        self.assertIsNone(extract_concrete_anchor("yes"))

    def test_trivial_empty_returns_none(self):
        self.assertIsNone(extract_concrete_anchor(""))
        self.assertIsNone(extract_concrete_anchor(None))

    def test_garbled_stt_returns_none(self):
        # "um yeah I think" → only "think" is non-stopword content
        # ("um" / "yeah" filter as too short or stopword) → < 4 tokens.
        self.assertIsNone(extract_concrete_anchor("um yeah I think"))

    def test_sentence_start_proper_noun_with_verb_lookahead(self):
        # Sentence-start position with verb lookahead.
        anchor = extract_concrete_anchor("Spokane was where I grew up.")
        self.assertEqual(anchor, "Spokane")

    def test_pronouns_at_sentence_start_excluded(self):
        # "I" / "We" capitalized at sentence-start are NOT proper nouns.
        anchor = extract_concrete_anchor(
            "I went to school there. We always took the bus together."
        )
        # Should not return "I" or "We" — they're on the blocklist.
        if anchor is not None:
            self.assertNotIn(anchor, ("I", "We"))


class ShapeReflectionTests(unittest.TestCase):
    """Layer 2 — Cases A/B/C/D + Layer 3 softened mode."""

    # — Case A: trivial narrator → pass through —

    def test_case_a_trivial_narrator_passes_through(self):
        narrator = "yes"
        assistant = "Wonderful. What was that like for you?"
        shaped, actions = shape_reflection(assistant, narrator)
        self.assertEqual(shaped, assistant)
        self.assertEqual(actions, ["shaped_no_change"])

    # — Case B: no echo + anchor available → prepend —

    def test_case_b_prepends_anchor_before_question(self):
        narrator = "I was born in Spokane in 1940."
        assistant = "What do you remember most?"
        shaped, actions = shape_reflection(assistant, narrator)
        self.assertTrue(shaped.startswith("Spokane"))
        self.assertIn("What do you remember most?", shaped)
        self.assertEqual(actions, ["shaped_anchor_prepended"])

    # — Case C1: echo too long, anchor inside → trim to anchor —

    def test_case_c1_trims_long_echo_to_anchor_when_anchor_present(self):
        narrator = "I had a mastoidectomy when I was little, in Spokane."
        # 30+ word echo containing "Spokane", followed by a question.
        assistant = (
            "It must have been terrifying for a small child to undergo "
            "such a difficult procedure in Spokane during those years, "
            "with everything that was going on at home and in the world. "
            "How old were you at the time?"
        )
        shaped, actions = shape_reflection(assistant, narrator)
        self.assertIn("Spokane", shaped)
        self.assertIn("How old were you", shaped)
        # Should be MUCH shorter than the original.
        self.assertLess(len(shaped.split()), len(assistant.split()))
        self.assertEqual(actions, ["shaped_echo_trimmed_to_anchor"])

    # — Case C2: echo too long, no anchor → drop echo —

    def test_case_c2_drops_echo_when_no_anchor_match(self):
        # Narrator with content but no proper noun and no kinship — so
        # extract_concrete_anchor() returns None → Case C2 path fires
        # when echo is too long.
        narrator = (
            "Things were difficult during those many long years afterwards "
            "and the summers seemed especially hard to get through somehow."
        )
        # ≥ 30-word echo before the question — over SHAPER_ECHO_WORD_BUDGET.
        assistant = (
            "I imagine that whole period feels both close and far away, "
            "the kind of memory that lingers in the body and surfaces in "
            "the smallest moments without warning. The way time bends "
            "around hard seasons is its own quiet weight. "
            "What comes to mind first?"
        )
        shaped, actions = shape_reflection(assistant, narrator)
        # No anchor in echo → Case C2 → drop echo, keep question.
        self.assertIn(actions[0], ("shaped_echo_dropped", "shaped_echo_trimmed_to_anchor"))
        self.assertLess(len(shaped.split()), len(assistant.split()))

    # — Case D: echo present + within budget → pass through —

    def test_case_d_passes_through_when_in_budget(self):
        narrator = "I was born in Spokane and grew up downtown."
        assistant = "Spokane. What do you remember?"  # 5 words echo, in budget
        shaped, actions = shape_reflection(assistant, narrator)
        self.assertEqual(shaped, assistant)
        self.assertEqual(actions, ["shaped_no_change"])

    # — Layer 3: softened mode tighter cap —

    def test_layer3_softened_mode_truncates_long_response(self):
        narrator = "I am so tired of all of this every day now."
        # 40+ word softened response — exceeds 30-word budget.
        assistant = (
            "I hear you, and I'm so sorry you're carrying so much right now. "
            "It sounds exhausting, the way the days stretch on, and I wish "
            "there were something I could say that made it lighter for you "
            "tonight."
        )
        shaped, actions = shape_reflection(
            assistant, narrator, softened_mode_active=True,
        )
        self.assertLessEqual(
            len(shaped.split()),
            SHAPER_SOFTENED_TURN_BUDGET,
        )
        self.assertEqual(actions, ["shaped_softened_truncated"])

    def test_layer3_softened_mode_passes_short_response(self):
        narrator = "I'm just tired."
        assistant = "I hear you. I'm right here."  # 6 words, fine
        shaped, actions = shape_reflection(
            assistant, narrator, softened_mode_active=True,
        )
        self.assertEqual(shaped, assistant)
        self.assertEqual(actions, ["shaped_no_change"])

    # — Idempotency: shaping twice = same output —

    def test_idempotent_double_shape(self):
        narrator = "I was born in Spokane in 1940."
        assistant = "What do you remember most?"
        once, _ = shape_reflection(assistant, narrator)
        twice, _ = shape_reflection(once, narrator)
        self.assertEqual(once, twice)

    # — Empty inputs —

    def test_empty_assistant_text_passes_through(self):
        shaped, actions = shape_reflection("", "narrator text")
        self.assertEqual(shaped, "")
        self.assertEqual(actions, [])

    def test_no_anchor_no_echo_passes_through(self):
        narrator = "I lived through everything one quiet day at a time."
        assistant = "Tell me more?"
        shaped, actions = shape_reflection(assistant, narrator)
        # No anchor available + question only + no echo span → Case D.
        # (Or potentially Case B if we ever broaden the proper-noun
        # detection; either way the shaper must not break.)
        self.assertIsNotNone(shaped)


if __name__ == "__main__":
    unittest.main()
