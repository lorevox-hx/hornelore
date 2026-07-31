"""WO-TRIP-NARRATOR-BRIDGE-01 — the acceptance harness's own judgment.

The harness decides whether Lori claimed to see a photograph, whether
she answered a question with a question, and whether she stated the
right count. Those decisions are regexes, and a regex that is slightly
wrong does not fail loudly -- it passes a bad answer and prints PASS.
So the grader is graded here, against the exact wording the work order
supplies on both sides: Chris's question in the form he typed it, the
answer shapes the work order calls correct, and the visual claims it
names as disqualifying.

The script imports requests, which is not installed in every checkout
(the accepted WO-02 harness has the same dependency). A minimal stub
stands in, because nothing in this file makes a request: only the pure
helpers are under test, and the stub is installed under a guard so a
machine that has the real library keeps it.
"""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "wo_narrator_bridge_acceptance.py"

if "requests" not in sys.modules:
    try:
        import requests  # noqa: F401
    except Exception:
        _stub = types.ModuleType("requests")

        class _RequestException(Exception):
            pass

        _stub.RequestException = _RequestException
        _stub.get = lambda *a, **k: (_ for _ in ()).throw(
            _RequestException("stubbed"))
        sys.modules["requests"] = _stub


def _load():
    spec = importlib.util.spec_from_file_location(
        "wo_narrator_bridge_acceptance", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(_SCRIPT.exists(), "harness not in this checkout")
class HarnessJudgmentTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def _visual(self, text):
        import re
        return [p for p in self.m.VISUAL_CLAIMS if re.search(p, text, re.I)]

    # -- the question -----------------------------------------------------

    def test_it_recognises_the_question_chris_actually_asked(self):
        self.assertTrue(self.m.PHOTO_QUESTION.search(
            "can you see any of the photos I added to my trip?"))

    def test_it_recognises_the_variants_the_work_order_names(self):
        for q in (
            "can you see the photos?",
            "can you see any of my trip photos?",
            "can you access the photos I added?",
            "can you read or view my trip photos?",
            "does this trip have photos?",
            "what photos do you have for this trip?",
            "do you have any information about the photos?",
        ):
            self.assertTrue(self.m.PHOTO_QUESTION.search(q), q)

    def test_it_does_not_grade_an_ordinary_trip_story_as_the_question(self):
        """A false positive here is worse than a miss: the harness would
        run the photo-answer checks against a story about a gravesite
        and fail a turn that was never the photo turn."""
        for s in (
            "I had a chance to visit my moms parents gravesite, my old "
            "elementary school, the two middle schools I attended and high "
            "school and junior college. The outsides anyway. With my wife "
            "Melanie.",
            "We took a lot of pictures that day.",
            "I want to add some photos later.",
        ):
            self.assertFalse(self.m.PHOTO_QUESTION.search(s), s)

    # -- the answer -------------------------------------------------------

    def test_the_work_orders_correct_answers_are_graded_correct(self):
        for ans in (
            "I can tell that five photos are attached to the Bismarck "
            "Trip. I do not directly inspect the image pixels here, but I "
            "can use captions and photo notes that have been approved for "
            "me.",
            "I can tell that photos are attached, but I do not have an "
            "approved caption or description for them yet.",
        ):
            self.assertEqual(self._visual(ans), [], ans[:40])

    def test_lori_saying_she_does_not_look_is_not_a_visual_claim(self):
        """The shipped answer says 'I don't look at the images
        themselves'. A pattern that fires on the denial would make the
        honest answer the failing one."""
        ans = ("There are two photos attached to the Bismarck Trip, and "
               "each of them is placed on a day. I should be straight with "
               "you about what that means for me, though: I don’t look at "
               "the images themselves. What I can work from is the captions "
               "and notes that have been written about a photo and approved "
               "for me.")
        self.assertEqual(self._visual(ans), [])
        self.assertTrue(self.m.says_count(ans, 2))

    def test_a_claim_to_have_seen_the_picture_is_caught(self):
        for bad in (
            "I can see the church in the second photo.",
            "The image shows a low brick building.",
            "The photo shows your mother's headstone.",
            "In the picture you are standing by the car.",
            "I looked at them and they are lovely.",
            "From what I can see, it was a bright day.",
            "I can view the ones you attached.",
        ):
            self.assertTrue(self._visual(bad), bad)

    # -- the count --------------------------------------------------------

    def test_a_count_written_as_a_word_counts(self):
        """Lori spells counts out. A digit-only check would fail every
        correct answer she gives."""
        self.assertTrue(self.m.says_count("There are two photos attached.", 2))
        self.assertTrue(self.m.says_count("There is one photo attached.", 1))
        self.assertTrue(self.m.says_count("2 photos are attached.", 2))

    def test_the_wrong_count_is_not_accepted(self):
        self.assertFalse(self.m.says_count("There are two photos.", 5))
        self.assertFalse(self.m.says_count("There are two photos.", 0))

    def test_a_count_word_hiding_inside_another_word_does_not_count(self):
        self.assertFalse(self.m.says_count("Someone wrote a caption.", 1))
        self.assertFalse(self.m.says_count("It was a tenuous claim.", 10))

    # -- the verdict ------------------------------------------------------

    def test_skip_never_becomes_fail(self):
        """The rule the earlier harness broke: a step the operator has
        not performed is unproven, not broken."""
        self.m.PASS[0] = self.m.FAIL[0] = self.m.SKIP[0] = 0
        del self.m.LINES[:]
        self.m.check(True, "a thing that held")
        self.m.skip("a thing nobody did")
        self.assertEqual((self.m.PASS[0], self.m.FAIL[0], self.m.SKIP[0]),
                         (1, 0, 1))
        self.assertTrue(any(l.startswith("SKIP") for l in self.m.LINES))
        self.assertFalse(any(l.startswith("FAIL") for l in self.m.LINES))

    def test_the_required_gate_names_are_the_work_orders_names(self):
        self.assertEqual(
            list(self.m.REQUIRED_GATES),
            ["trip_interview_context_enabled",
             "trip_story_capture_enabled",
             "trip_shelf_turn_link_enabled"])

    def test_it_hashes_rather_than_quoting(self):
        h = self.m.h("my moms parents gravesite")
        self.assertEqual(len(h), 16)
        self.assertNotIn("gravesite", h)


if __name__ == "__main__":
    unittest.main()
