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
    _expand_anchor_over_compound,
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


_CURLY = "\u2019"  # U+2019 RIGHT SINGLE QUOTATION MARK


class OmittedApostropheKinshipAnchorTest(unittest.TestCase):
    """BUG-PERSON-ANCHOR-OMITTED-APOSTROPHE-01, reflection side.
    WO-LEAN-LORI-RUNTIME-01 Phase 1B, 2026-08-04.

    The same defect `story_trigger` had, in the module that decides what
    Lori echoes back. "my dad's shop" and the curly form both produced
    an anchor; "my dads shop" produced none, so Lori lost her grip on
    the one concrete thing the narrator had just said.

    The suffix deliberately sits OUTSIDE the `noun` capture group. If it
    were inside, the anchor for "my dads shop" would be "dads" and the
    possessive flip would have Lori open with "Your dads." -- which is
    a worse failure than the one being fixed, because it is audible.
    """

    PAIRS = [
        ("my dad's shop was on the corner", "my dads shop was on the corner"),
        ("my mom's kitchen was warm", "my moms kitchen was warm"),
        ("my grandmother's farm was north", "my grandmothers farm was north"),
        ("my brother's truck broke down", "my brothers truck broke down"),
    ]

    def test_all_three_forms_find_the_same_anchor(self):
        for straight, omitted in self.PAIRS:
            curly = straight.replace("'", _CURLY)
            with self.subTest(text=omitted):
                a = extract_concrete_anchor(straight)
                b = extract_concrete_anchor(curly)
                c = extract_concrete_anchor(omitted)
                self.assertTrue(a, f"no anchor for straight: {straight}")
                self.assertEqual(a, b, "curly disagrees with straight")
                self.assertEqual(a, c, "omitted disagrees with straight")

    def test_the_anchor_never_carries_the_possessive_suffix(self):
        """The audible failure. Lori must say "Your dad", never
        "Your dads" or "Your dad's"."""
        for _straight, omitted in self.PAIRS:
            with self.subTest(text=omitted):
                anchor = (extract_concrete_anchor(omitted) or "").lower()
                self.assertTrue(anchor)
                self.assertFalse(anchor.endswith("s'"), anchor)
                self.assertFalse(anchor.endswith(_CURLY + "s"), anchor)
                self.assertFalse(anchor.endswith("'s"), anchor)
                for bad in ("dads", "moms", "grandmothers", "brothers"):
                    self.assertNotIn(bad, anchor, f"suffix leaked: {anchor}")

    def test_non_kinship_words_still_produce_no_kinship_anchor(self):
        for t in ("my mask was itchy", "my maps were old",
                  "my popsicle melted"):
            with self.subTest(text=t):
                a = (extract_concrete_anchor(t) or "").lower()
                for kin in ("dad", "mom", "father", "mother"):
                    self.assertNotIn(kin, a)


class CompoundNameTrimmingTest(unittest.TestCase):
    """LLR-21 — WO-LEAN-LORI-RUNTIME-01 Phase 1E, 2026-08-04.

    LIVE EVIDENCE, 2026-08-04 13:26:
        actions=shaped_echo_trimmed_to_anchor before_words=52
        "Peter Zarr and Josie Zarr are laid to rest there"
          -> "Peter Zarr. are laid to rest there."

    Two failures in one line, and the second is much the worse. Broken
    grammar is embarrassing. Silently deleting a grandmother from a
    reply about her own grave is the thing this system exists not to do.

    Case C1 assumed the anchor was a self-contained opener. It is not:
    "Peter Zarr" is half of a compound subject, so cutting there both
    dropped Josie and stranded the verb.
    """

    NARRATOR = ("My grandparents Peter Zarr and Josie Zarr are buried in "
                "the cemetery outside Mandan.")
    LONG_TAIL = ("are laid to rest there in the little cemetery outside of "
                 "town where the family plot has been since the eighteen "
                 "nineties")

    def test_the_second_person_is_not_dropped(self):
        """The one that matters. Josie must survive."""
        text = f"Peter Zarr and Josie Zarr {self.LONG_TAIL}. What do you remember about visiting?"
        shaped, actions = shape_reflection(text, self.NARRATOR)
        self.assertIn("shaped_echo_trimmed_to_anchor", actions)
        self.assertIn("Josie", shaped, f"Josie was dropped: {shaped!r}")
        self.assertIn("Peter", shaped)

    def test_no_headless_clause_is_emitted(self):
        """The verbatim broken shape must not be producible."""
        text = f"Peter Zarr and Josie Zarr {self.LONG_TAIL} and nobody has moved it since."
        shaped, _ = shape_reflection(text, self.NARRATOR)
        self.assertNotRegex(
            shaped, r"\.\s+(are|were|is|was|and|has|have)\b",
            f"a sentence begins with a verb: {shaped!r}")

    def test_the_question_still_survives_the_trim(self):
        text = f"Peter Zarr and Josie Zarr {self.LONG_TAIL}. What do you remember about visiting?"
        shaped, _ = shape_reflection(text, self.NARRATOR)
        self.assertIn("What do you remember about visiting?", shaped)

    def test_a_single_name_is_unaffected(self):
        """The repair must not reach turns that were never broken."""
        text = ("Peter Zarr is laid to rest there in the little cemetery "
                "outside of town where the plot has been since the "
                "eighteen nineties. What do you remember about it?")
        shaped, actions = shape_reflection(text, self.NARRATOR)
        self.assertEqual(["shaped_no_change"], actions)
        self.assertEqual(text, shaped)


class ExpandAnchorOverCompoundTest(unittest.TestCase):
    """The expander in isolation, including what it must REFUSE to do."""

    def test_it_grows_forward_across_the_conjunction(self):
        self.assertEqual(
            "Peter Zarr and Josie Zarr",
            _expand_anchor_over_compound(
                "Peter Zarr", "Peter Zarr and Josie Zarr are laid to rest"))

    def test_it_grows_backward_when_the_anchor_is_the_second_conjunct(self):
        self.assertEqual(
            "Peter and Josie Zarr",
            _expand_anchor_over_compound(
                "Josie Zarr", "Peter and Josie Zarr are laid to rest"))

    def test_it_stops_at_the_verb(self):
        """The first cut used re.IGNORECASE, which makes [A-Z] match
        lowercase, so the "capitalised run" swallowed the verb and
        produced "Peter Zarr and Josie Zarr are laid." -- Josie rescued,
        sentence still broken. The anchor is located case-insensitively
        but the compound is matched case-SENSITIVELY."""
        got = _expand_anchor_over_compound(
            "Peter Zarr", "Peter Zarr and Josie Zarr are laid to rest")
        for verb in (" are", " were", " laid", " is"):
            self.assertNotIn(verb, got, f"ran past the subject: {got!r}")

    def test_it_does_not_expand_across_a_lowercase_continuation(self):
        """"Peter Zarr and his brother" is not a compound of two names."""
        self.assertEqual(
            "Peter Zarr",
            _expand_anchor_over_compound(
                "Peter Zarr", "Peter Zarr and his brother went west"))

    def test_it_leaves_ordinary_nouns_alone(self):
        self.assertEqual(
            "the barn",
            _expand_anchor_over_compound(
                "the barn", "the barn and the milking shed burned down"))

    def test_an_absent_anchor_is_returned_unchanged(self):
        self.assertEqual(
            "Peter Zarr",
            _expand_anchor_over_compound("Peter Zarr", "a different sentence"))


if __name__ == "__main__":
    unittest.main()
