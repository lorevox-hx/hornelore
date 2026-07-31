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


# ---------------------------------------------------------------------
# Which note is the story?
#
# Both the Travels shelf and the Travel Doc modal write
# source_type='lori' rows into trip_location_notes. The harness used to
# take "every new Lori note in the window" and grade it as the shelf
# story, which on 2026-07-31 graded a modal Day 1 note -- correctly day-
# scoped -- as a placement defect, and reported FAIL on a run that had
# proved nothing about the thing it named. These tests pin the
# correlation instead of the count.

STORY = ("I had a chance to visit my mom's parents' gravesite, my old "
         "elementary school, the two middle schools I attended, my high "
         "school and junior college—the outsides anyway—with my wife "
         "Melanie.")
MODAL_TEXT = "hi, i went to bismarck to do some work"
TRIP = "9538cd88-5c8b-4da4-b2a9-2a03f8db32a3"
DAY1 = "day-1-11111111"
DAY2 = "day-2-22222222"


def _conv(link_id, said, day=None, src="travels_shelf_trip",
          st="needs_day", u=100, a=101):
    return {"kind": "conversation", "link_id": link_id, "trip_day_id": day,
            "conv_id": "switch_test", "placement_source": src,
            "placement_status": st, "user_turn_row_id": u,
            "assistant_turn_row_id": a, "narrator_said": said,
            "lori_said": "That sounds like a full day."}


def _note(nid, text, surface=None, ref="turn:t-1", day=None):
    return {"id": nid, "source_type": "lori", "source_ref": ref,
            "source_surface": surface, "created_at": "2026-07-31T02:00:00Z",
            "trip_day_id": day, "include_in_memoir": 0,
            "include_in_interview_context": 0, "hidden": 0,
            "note_text": text}


@unittest.skipUnless(_SCRIPT.exists(), "harness not in this checkout")
class CandidateCorrelationTest(unittest.TestCase):
    """do_verify against a canned API. No network, no database."""

    def setUp(self):
        self.m = _load()
        self.live_state = "completed"
        self.selected_day = None
        self.convs = []
        self.notes = []
        self._tmp = None

    def tearDown(self):
        import os
        for p in (self._tmp, getattr(self, "_acc", None)):
            if p and os.path.exists(p):
                os.unlink(p)

    # -- the canned API -------------------------------------------------

    def _install(self):
        import json
        import tempfile
        m = self.m

        # The walkthrough always produces at least two shelf turns (the
        # story and the photo question), and do_verify checks for that.
        # Every fixture therefore carries a second, deliberately
        # non-story turn: without it these tests would fail on a check
        # about conversation COUNT while claiming to be about candidate
        # correlation, and the failure would point at the wrong thing.
        # Read at CALL time, not install time. RestartVerifyTest mutates
        # self.convs between the accepted verify and the restart check --
        # a list snapshotted here would never see the change, and four
        # tests would report a passing restart on a world that had been
        # altered underneath them.
        def convs():
            return list(self.convs) + [
                _conv("f11e5000-ffff", "It was good to be back there again.",
                      u=102, a=103)]

        def fake_get(path):
            if "/calendar" in path:
                return {"live_state": self.live_state,
                        "selected_day_id": self.selected_day,
                        "days": [{"id": DAY1}, {"id": DAY2}],
                        "preserved": []}
            if "/timeline/unplaced" in path:
                return {"items": [c for c in convs()
                                  if not c["trip_day_id"]]}
            if "/timeline" in path:
                did = path.split("/days/")[1].split("/")[0]
                return {"items": [c for c in convs()
                                  if c["trip_day_id"] == did]}
            if "/location-notes" in path:
                return {"notes": list(self.notes)}
            if "/photo-inventory" in path:
                return {"attached": 2, "on_a_day": 2, "cleared_for_lori": 0}
            if "/capture-status" in path:
                return {"last": {"reason": "meaningful_trip_answer"}}
            if "/family-truth/rows" in path:
                return {"rows": []}
            if "/photo-links" in path:
                return {"photo_links": []}
            raise AssertionError("unstubbed path: " + path)

        m.get = fake_get
        m.PASS[0] = m.FAIL[0] = m.SKIP[0] = 0
        del m.LINES[:]

        fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8")
        self._tmp = fh.name
        json.dump({"live_state": self.live_state,
                   "selected_day_id": self.selected_day,
                   "day_ids": [DAY1, DAY2], "convs": {}, "notes": {},
                   "photo_inventory": {"attached": 2},
                   "family_truth_rows": 0}, fh)
        fh.close()
        m.STATE = self._tmp

        # The accepted record must go somewhere writable. Left at the
        # module default it targets Chris's repo, which is how the first
        # run of this class failed: PermissionError on /mnt/c.
        acc = tempfile.NamedTemporaryFile(suffix=".json", delete=False,
                                          mode="w", encoding="utf-8")
        acc.close()
        self._acc = acc.name
        m.ACCEPTED = self._acc

    def _run(self):
        m = self.m
        self._install()
        gates = dict((k, True) for k in m.REQUIRED_GATES)
        rc = m.do_verify(gates, m.snapshot())
        return rc, "\n".join(m.LINES), m.PASS[0], m.FAIL[0], m.SKIP[0]

    # -- the tests ------------------------------------------------------

    def test_an_unrelated_modal_note_does_not_fail_the_shelf_story(self):
        """The 2026-07-31 shape, both notes present. The shelf story is
        graded; the modal note is named and ignored."""
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("shelf-01", STORY),
                      _note("09d6f7e4-bbbb", MODAL_TEXT,
                            surface="travel_doc_modal",
                            ref="modal_turn:conv:t-9", day=DAY1)]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 0, log)
        self.assertIn("shelf-01", log)
        self.assertIn("no inferred day", log)
        self.assertNotIn("FAIL", log)

    def test_a_modal_note_alone_is_not_graded_as_the_story(self):
        """Only a modal note exists. The story step is unproven, not
        broken -- and specifically not a candidate-day FAIL, which is
        what the harness reported on 2026-07-31."""
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("09d6f7e4-bbbb", MODAL_TEXT,
                            surface="travel_doc_modal",
                            ref="modal_turn:conv:t-9", day=DAY1)]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 0, log)
        self.assertEqual(rc, 3, "an unproven run must not exit 0")
        self.assertIn("no new shelf story candidate", log)
        self.assertNotIn("durable selected day", log)

    def test_a_modal_note_is_recognised_by_its_ref_without_a_surface(self):
        """A pre-0024 row has no source_surface. The modal_turn: prefix
        still marks it, so it must still not be graded as the story."""
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("09d6f7e4-bbbb", MODAL_TEXT, surface=None,
                            ref="modal_turn:conv:t-9", day=DAY1)]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 0, log)
        self.assertEqual(rc, 3)
        self.assertIn("no new shelf story candidate", log)

    def test_a_shelf_note_that_matches_no_turn_is_not_graded(self):
        """Present but unattributable is not evidence, and not a defect
        either. It must never be silently accepted as the story."""
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("shelf-01", "something else entirely, said "
                                        "on some other day")]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 0, log)
        self.assertEqual(rc, 3)
        self.assertIn("matched no new shelf turn", log)

    def test_a_completed_trip_candidate_must_not_carry_a_day(self):
        """The product rule. A completed trip has no durable day, so an
        inferred one is a manufactured fact and must fail."""
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("shelf-01", STORY, day=DAY1)]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 1, log)
        self.assertEqual(rc, 1)
        self.assertIn("no inferred day", log)

    def test_an_active_trip_candidate_must_carry_the_durable_day(self):
        """The inverse. When the database really does hold a selected
        day, the candidate is expected to be on it."""
        self.live_state = "active"
        self.selected_day = DAY1
        self.convs = [_conv("c75350cd-aaaa", STORY, day=DAY1,
                            src="active_trip_day", st="confirmed")]
        self.notes = [_note("shelf-01", STORY, day=DAY1)]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 0, log)
        self.assertIn("carries the durable selected day", log)

    def test_an_active_trip_candidate_on_the_wrong_day_fails(self):
        self.live_state = "active"
        self.selected_day = DAY1
        self.convs = [_conv("c75350cd-aaaa", STORY, day=DAY1,
                            src="active_trip_day", st="confirmed")]
        self.notes = [_note("shelf-01", STORY, day=DAY2)]
        rc, log, p, f, s = self._run()
        self.assertEqual(f, 1, log)

    def test_two_candidates_from_one_turn_are_caught(self):
        """The duplicate-capture check still bites, now stated over
        turns rather than over the raw count of new notes."""
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("shelf-01", STORY, ref="turn:t-1"),
                      _note("shelf-02", STORY, ref="turn:t-2")]
        rc, log, p, f, s = self._run()
        self.assertGreaterEqual(f, 1, log)
        self.assertIn("captured once, not twice", log)

    def test_it_still_prints_no_narrative_text(self):
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("shelf-01", STORY),
                      _note("09d6f7e4-bbbb", MODAL_TEXT,
                            surface="travel_doc_modal",
                            ref="modal_turn:conv:t-9", day=DAY1)]
        rc, log, p, f, s = self._run()
        for fragment in ("gravesite", "Melanie", "elementary", "bismarck",
                         "Bismarck"):
            self.assertNotIn(fragment, log, fragment)


@unittest.skipUnless(_SCRIPT.exists(), "harness not in this checkout")
class RestartVerifyTest(CandidateCorrelationTest):
    """The persistence check, against the ids the first verify accepted.

    Re-running `verify` after a restart proves rows survived. It cannot
    prove they are the SAME rows: its baseline predates the walkthrough
    and knows nothing of what the walkthrough made. So a clean verify
    writes down what it accepted, and this mode checks that.
    """

    def _accept_then(self, mutate=None):
        """Run a clean verify -- which writes the accepted record through
        the REAL writer -- then optionally change the world, then run
        restart-verify against it.

        Deliberately not reimplementing the writer's inputs here. A test
        that recomputed what do_verify accepted would be asserting
        against its own copy of the logic, and would keep passing after
        the two drifted apart."""
        import os
        import tempfile
        m = self.m
        rc1, log1, p1, f1, s1 = self._run()
        self.assertEqual(f1, 0, "the accepted run must be clean:\n" + log1)
        self.assertTrue(os.path.exists(m.ACCEPTED),
                        "a clean verify must write the accepted record")
        if mutate:
            mutate()
        m.PASS[0] = m.FAIL[0] = m.SKIP[0] = 0
        del m.LINES[:]
        gates = dict((k, True) for k in m.REQUIRED_GATES)
        rc2 = m.do_restart_verify(gates, m.snapshot())
        log2 = "\n".join(m.LINES)
        try:
            os.unlink(m.ACCEPTED)
        except OSError:
            pass
        return rc2, log2, m.FAIL[0]

    def _base(self):
        self.convs = [_conv("c75350cd-aaaa", STORY)]
        self.notes = [_note("shelf-01", STORY)]

    def test_an_untouched_restart_passes(self):
        self._base()
        rc, log, f = self._accept_then()
        self.assertEqual(f, 0, log)
        self.assertEqual(rc, 0)
        self.assertIn("transcript is byte-identical", log)
        self.assertIn("survived a real restart", log)

    def test_a_vanished_conversation_fails(self):
        self._base()

        def drop():
            self.convs = []
        rc, log, f = self._accept_then(drop)
        self.assertGreaterEqual(f, 1, log)
        self.assertEqual(rc, 1)

    def test_a_changed_transcript_fails(self):
        """The transcript is what a family reads. If a restart can
        change it, nothing else here matters."""
        self._base()

        def edit():
            self.convs = [_conv("c75350cd-aaaa", STORY + " And then we left.")]
        rc, log, f = self._accept_then(edit)
        self.assertGreaterEqual(f, 1, log)

    def test_a_duplicated_conversation_fails(self):
        """A replayed hook ADDS a row rather than changing one, so the
        per-link checks cannot see it. Only the totals can."""
        self._base()

        def dupe():
            self.convs = self.convs + [
                _conv("dddddddd-dupe", STORY, u=200, a=201)]
        rc, log, f = self._accept_then(dupe)
        self.assertGreaterEqual(f, 1, log)
        self.assertIn("no conversation was duplicated", log)

    def test_a_moved_placement_fails(self):
        self._base()

        def moved():
            self.convs = [_conv("c75350cd-aaaa", STORY, day=DAY1,
                                src="active_trip_day", st="confirmed")]
        rc, log, f = self._accept_then(moved)
        self.assertGreaterEqual(f, 1, log)

    def test_a_vanished_candidate_fails(self):
        self._base()

        def drop():
            self.notes = []
        rc, log, f = self._accept_then(drop)
        self.assertGreaterEqual(f, 1, log)

    def test_a_candidate_promoted_during_the_restart_fails(self):
        """Review-only is not a one-time property. A restart that
        silently promoted a candidate into the memoir is exactly the
        thing this whole lane exists to prevent."""
        self._base()

        def promote():
            n = _note("shelf-01", STORY)
            n["include_in_memoir"] = 1
            self.notes = [n]
        rc, log, f = self._accept_then(promote)
        self.assertGreaterEqual(f, 1, log)

    def test_a_duplicated_candidate_fails(self):
        self._base()

        def dupe():
            self.notes = self.notes + [
                _note("shelf-02", STORY, ref="turn:t-2")]
        rc, log, f = self._accept_then(dupe)
        self.assertGreaterEqual(f, 1, log)
        self.assertIn("no story candidate was duplicated", log)

    def test_it_refuses_to_run_without_an_accepted_record(self):
        """A restart check with nothing to check against must not look
        like a pass."""
        self._base()
        self._install()
        self.m.ACCEPTED = "/nonexistent/accepted.json"
        gates = dict((k, True) for k in self.m.REQUIRED_GATES)
        rc = self.m.do_restart_verify(gates, self.m.snapshot())
        self.assertEqual(rc, 2)

    def test_it_still_prints_no_narrative_text(self):
        self._base()
        rc, log, f = self._accept_then()
        for fragment in ("gravesite", "Melanie", "elementary"):
            self.assertNotIn(fragment, log, fragment)


@unittest.skipUnless(_SCRIPT.exists(), "harness not in this checkout")
class TurnCorrelationHelperTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.m = _load()

    def test_a_light_cleaned_note_matches_the_turn_it_came_from(self):
        """trip_story_capture._light_clean collapses runs of spaces and
        strips wrapping quotes. The match must survive that."""
        self.assertTrue(self.m.same_turn(
            "I went   to Bismarck for work.",
            '"I went to Bismarck   for work."'))

    def test_a_different_sentence_does_not_match(self):
        self.assertFalse(self.m.same_turn(
            "I went to Bismarck for work.",
            "I visited my grandmother's grave."))

    def test_a_short_note_never_prefix_matches_a_long_turn(self):
        """Otherwise 'yes' would correlate to every turn on the trip."""
        self.assertFalse(self.m.same_turn("yes …", "yes, and then we drove "
                                          "out to the cemetery " * 20))

    def test_a_truncated_long_note_still_matches_its_turn(self):
        turn = ("We drove out past the old grain elevator and I told her "
                "about the winters. " * 40)
        note = turn[:4000].rstrip() + " …"
        self.assertTrue(self.m.same_turn(note, turn))

    def test_empty_never_matches(self):
        self.assertFalse(self.m.same_turn("", "anything"))
        self.assertFalse(self.m.same_turn("anything", ""))

    def test_modal_notes_are_recognised_by_either_mark(self):
        self.assertTrue(self.m.is_modal({"surface": "travel_doc_modal",
                                         "ref": "turn:t-1"}))
        self.assertTrue(self.m.is_modal({"surface": None,
                                         "ref": "modal_turn:c:t"}))
        self.assertFalse(self.m.is_modal({"surface": None,
                                          "ref": "turn:t-1"}))
        self.assertFalse(self.m.is_modal({"surface": None, "ref": None}))


if __name__ == "__main__":
    unittest.main()
