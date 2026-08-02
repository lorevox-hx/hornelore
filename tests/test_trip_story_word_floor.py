"""Trip-story capture: the meaningful-word floor, raised 3 -> 6.

PRODUCT DECISION, Chris, 2026-08-01. A turn shorter than six words is a
fragment or an acknowledgment, not a memory worth putting in front of an
operator for Travel Doc review.

WHICH LIMIT THIS IS, BECAUSE THREE WERE CONFUSED FOR EACH OTHER
---------------------------------------------------------------
The discussion that produced this change conflated three different
numbers living in two modules. Naming them here so the next reader does
not repeat it:

  trip_story_capture._MIN_MEANINGFUL_WORDS      3 -> 6   THIS ONE.
      A FLOOR on trip-story candidates.

  trip_story_capture._MAX_COMMAND_WORDS         6        A CEILING.
      A turn LONGER than this cannot be a conversation command such as
      "say that again". Same number, opposite direction, unrelated
      purpose. Raising the floor to 6 makes them equal, which is a
      coincidence and not a relationship -- a test below pins that
      changing one does not change the other.

  story_trigger.STORY_TRIGGER_RICH_SHORT_MIN_WORDS  15   DIFFERENT
      MODULE. Governs LIFE-STORY capture, not trip-story capture. I
      spent two rounds discussing this one while Chris was asking about
      the first.

WHAT MUST NOT BREAK
-------------------
The floor is a length rule and nothing else. It must not start rejecting
a real memory because of the WORDS it contains -- particularly narration
containing "stop", "back" or "continue", which the command classifier
looks for. Those cases are here as explicit regression tests, because
that is the plausible way a length change turns into a content change.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_trip_story_word_floor
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SERVER = _REPO / "server" / "code"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from api.services import trip_story_capture as tsc   # noqa: E402


def _words(t: str) -> int:
    return len(t.split())


class TheFloorIsSixTest(unittest.TestCase):

    def test_the_constant_is_six(self):
        self.assertEqual(6, tsc._MIN_MEANINGFUL_WORDS)

    def test_one_to_five_words_are_rejected(self):
        """The whole point of the change: fragments stay out of review."""
        for text in ("yes",
                     "okay sure",
                     "that was nice",
                     "we went to Bismarck",
                     "I liked the trip"):
            with self.subTest(text=text, words=_words(text)):
                self.assertLessEqual(_words(text), 5, "fixture drifted")
                self.assertTrue(
                    tsc._is_trivial(text),
                    f"{_words(text)}-word fragment was NOT rejected")

    def test_exactly_six_words_is_accepted(self):
        """The boundary itself, in both directions -- an off-by-one here
        would silently move the product decision by one word."""
        six = "We buried my father in Mandan"
        self.assertEqual(6, _words(six))
        self.assertFalse(tsc._is_trivial(six))

        five = "We buried my father today"
        self.assertEqual(5, _words(five))
        self.assertTrue(tsc._is_trivial(five))

    def test_real_memories_above_the_floor_are_accepted(self):
        for text in (
            "i went to visit my moms parents gravesite in Bismarck.",
            "there is an image of me at the gravesite, one of the "
            "lewis and clark interpretive center north of Bismarck",
            "I met my wife at a dance in Spokane in 1984.",
        ):
            with self.subTest(words=_words(text)):
                self.assertGreaterEqual(_words(text), 6, "fixture drifted")
                self.assertFalse(tsc._is_trivial(text))

    def test_the_august_1_bismarck_turns_are_unaffected(self):
        """Measured, not assumed. Both real turns from the session that
        prompted this change stay above the floor."""
        gravesite = "i went to visit my moms parents gravesite in Bismarck."
        images = ("there is an image of me at the gravesite, one of the "
                  "lewis and clark interpretive center north of Bismarck "
                  "and of the ground as we flew into the airport")
        self.assertEqual(10, _words(gravesite))
        self.assertEqual(30, _words(images))
        self.assertFalse(tsc._is_trivial(gravesite))
        self.assertFalse(tsc._is_trivial(images))


class LengthOnlyNotContentTest(unittest.TestCase):
    """A floor is a length rule. It must not become a content rule."""

    def test_narration_containing_stop_back_or_continue_still_captures(self):
        """These words are what the COMMAND classifier looks for. A real
        memory that happens to contain one must still be captured -- this
        is the plausible way a length change turns into a content change,
        so it is tested rather than reasoned about."""
        for text in (
            "We had to stop the car outside Mandan because of the snow.",
            "I walked back to the house where my grandmother lived.",
            "We could not continue the drive until the storm passed.",
            "My father told me to stop and look at the river.",
        ):
            with self.subTest(text=text[:40]):
                self.assertGreaterEqual(_words(text), 6)
                self.assertFalse(
                    tsc._is_trivial(text),
                    "a real memory was rejected because of a word it "
                    "contains, not its length")

    def test_short_commands_are_still_excluded(self):
        """They were already excluded by their own classifier; the floor
        must not be what is holding them out, or removing the floor later
        would let them through."""
        for text in ("say that again", "go back", "stop", "continue",
                     "repeat that please"):
            with self.subTest(text=text):
                self.assertTrue(tsc._is_trivial(text))

    def test_questions_to_lori_are_still_excluded(self):
        """Excluded by the Lori-directed classifier, not by length --
        which matters, because these are long enough to clear the floor."""
        for text in ("can you tell me about the lewis and clark center",
                     "how many pictures can you see from this trip",
                     "what do you mean by that exactly"):
            with self.subTest(words=_words(text)):
                self.assertGreaterEqual(_words(text), 6,
                                        "fixture is below the floor, so "
                                        "this proves nothing about the "
                                        "question classifier")
                # `_is_question_or_meta` is the real name. My first cut
                # invented `_is_lori_directed` from the regex constant
                # `_LORI_DIRECTED_RX` and asserted against a function that
                # does not exist -- an AttributeError, not a finding.
                self.assertTrue(
                    tsc._is_question_or_meta(text),
                    "a question long enough to clear the floor was not "
                    "caught by the question classifier")


class ShortQuestionsReportTheRightReasonTest(unittest.TestCase):
    """The reordering, pinned. Chris's ruling 2026-08-01.

    Raising the floor to 6 made "Can you explain that?" (4 words) hit the
    trivial check before the question check, so the operator's log called
    a question a fragment. The candidate outcome was identical either
    way -- what changed was the reason, and the reason is what an
    operator reads when working out what happened.

    Both directions are asserted. A test that only proved the question
    case would pass on code that had deleted the trivial check entirely.
    """

    def _reason(self, text):
        """The reason `capture_turn` records, via the classifier order."""
        if tsc._is_conversation_command(text):
            return "conversation_command"
        if tsc._is_question_or_meta(text):
            return "direct_question_or_command"
        if tsc._is_trivial(text):
            return "trivial_reply"
        return "captured"

    def test_a_short_question_reports_direct_question_not_trivial(self):
        for text in ("can you explain that?",
                     "what do you mean?",
                     "can you tell me?"):
            with self.subTest(text=text, words=_words(text)):
                self.assertLess(_words(text), 6,
                                "fixture is above the floor, so it would "
                                "reach the question check anyway and this "
                                "proves nothing about the ordering")
                self.assertEqual("direct_question_or_command",
                                 self._reason(text))

    def test_a_short_NON_question_still_reports_trivial_reply(self):
        """The other direction. Without this, deleting the trivial check
        would make the test above pass."""
        for text in ("yes", "okay sure", "that was nice", "I liked it"):
            with self.subTest(text=text, words=_words(text)):
                self.assertLess(_words(text), 6)
                self.assertEqual("trivial_reply", self._reason(text))

    def test_conversation_controls_still_win_over_both(self):
        """The control check was already first, for the same reason. The
        reordering below it must not have displaced it."""
        for text in ("say that again", "go back", "stop"):
            with self.subTest(text=text):
                self.assertEqual("conversation_command", self._reason(text))

    def test_the_question_check_precedes_the_trivial_check_in_source(self):
        """Read from the source, because the behaviour above could also
        be produced by a coincidence of the classifiers rather than by
        the order. This asserts the order itself."""
        import inspect
        # The function is `capture_trip_story_answer`. My first cut
        # guessed `capture_turn` from the module name and asserted
        # against a function that does not exist -- an
        # AttributeError, not a finding. Third time today I have
        # invented a symbol instead of reading one.
        src = inspect.getsource(tsc.capture_trip_story_answer)
        code = "\n".join(l for l in src.splitlines()
                         if not l.lstrip().startswith("#"))
        i_q = code.index('_result(False, "direct_question_or_command")')
        i_t = code.index('_result(False, "trivial_reply")')
        i_c = code.index('_result(False, "conversation_command")')
        self.assertLess(i_c, i_q, "conversation controls must stay first")
        self.assertLess(i_q, i_t,
                        "the question check must precede the word floor")


class TheTwoSixesAreUnrelatedTest(unittest.TestCase):
    """_MIN_MEANINGFUL_WORDS and _MAX_COMMAND_WORDS are now both 6.

    That is a coincidence. One is a floor on memories, the other a
    ceiling on commands. Pinned so a future edit does not treat them as
    one setting and change both by moving one.
    """

    def test_they_are_separate_constants(self):
        self.assertEqual(6, tsc._MIN_MEANINGFUL_WORDS)
        self.assertEqual(6, tsc._MAX_COMMAND_WORDS)
        self.assertIsNot(
            tsc.__dict__["_MIN_MEANINGFUL_WORDS"].__class__,
            type(None))

    def test_the_command_ceiling_still_works_at_its_own_boundary(self):
        """A seven-word turn is too long to be a command, regardless of
        what the memory floor is set to."""
        seven = "say that again about the whole trip"
        self.assertEqual(7, _words(seven))
        self.assertFalse(tsc._is_conversation_command(seven))

    def test_the_life_story_trigger_is_a_different_module(self):
        """story_trigger governs life-story capture and is untouched by
        this change. Asserted so nobody 'fixes' one by editing the
        other -- which is what I did for two rounds in discussion."""
        from api.services import story_trigger as st
        self.assertNotEqual(tsc._MIN_MEANINGFUL_WORDS,
                            st._rich_short_min_words())


if __name__ == "__main__":
    unittest.main(verbosity=2)
