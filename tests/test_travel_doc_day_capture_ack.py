"""WO-TRAVEL-DOC-UI-LAB-02 items 6+7 — Day Capture mode composer tests.

Live evidence (transcript_tdlab, 2026-07-10): the narrator gave a rich
Day-1 memory (United flight canceled in Santa Fe, lost a day, voucher +
motel) and Lori replied with anchor-echo garbage ("From Santa Fe to
Munich to lost — Santa Fe. ..."). Day Capture kills that path by
construction: a day-scoped meaningful modal turn is captured (with
trip_day_id) and acknowledged DETERMINISTICALLY from the day + the
narrator's OWN words — never the LLM, never "I can see", never an
invented fact.

Coverage:
  * day-scoped meaningful turn -> capture writes trip_day_id AND the
    composed ack contains "Day {N}", the narrator's words, and exactly
    ONE question mark (the fixed follow-up);
  * question turns still route to answer_modal_direct_question and are
    NOT captured / NOT acked;
  * non-day modal turns capture unchanged (trip_day_id NULL, no ack);
  * cross-trip / unknown day ids are dropped, never written.

Offline sqlite fixture pattern (same as the Mark Twain gate). Capture
flag HORNELORE_TRIP_STORY_CAPTURE is forced ON per test via env.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from api.services import travel_doc_lori_modal as modal  # noqa: E402

# The exact live-transcript memory (Chris's review, Day 1 of the trip).
UNITED_FLIGHT_MEMORY = (
    "Our United flight out of Santa Fe got canceled, so we lost a whole "
    "day. The airline gave us a voucher and we spent the night in a "
    "motel near the airport before we could fly on to Munich."
)


class _DayCaptureCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3",
                                                  delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self._orig_flag = os.environ.get("HORNELORE_TRIP_STORY_CAPTURE")
        os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = "1"

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'Day Capture Test', "
            "'1962-12-24', '2026-07-10', '2026-07-10')",
            (self.person_id,))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id, "Santa Fe to Munich",
            start_date="2026-05-14", end_date="2026-05-18")
        trip_repository.trip_days_generate(self.trip_id)
        self.days = trip_repository.trip_days_list(self.trip_id)
        self.day1 = self.days[0]

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_TRIP_STORY_CAPTURE", None)
        else:
            os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = self._orig_flag
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _scope(self, day_id=None):
        return modal.build_modal_scope(
            person_id=self.person_id,
            active_trip_id=self.trip_id,
            conv_id="tdlab_conv",
            selected_kind="day" if day_id else "trip",
            active_trip_day_id=day_id,
        )

    def _capture(self, text, day_id=None, turn_id="tdlab_t1"):
        return modal.capture_modal_answer(
            person_id=self.person_id,
            scope=self._scope(day_id),
            narrator_text=text,
            previous_lori_text="Tell me about that day.",
            conv_id="tdlab_conv",
            turn_id=turn_id,
        )


class DayScopedCaptureTest(_DayCaptureCase):
    def test_united_flight_memory_captures_with_trip_day_id(self):
        res = self._capture(UNITED_FLIGHT_MEMORY, day_id=self.day1["id"])
        self.assertTrue(res["captured"], res)
        self.assertEqual(res["reason"], "meaningful_trip_answer")
        self.assertEqual(res["trip_day_id"], self.day1["id"])
        note = trip_repository.location_note_get(res["note_id"])
        self.assertEqual(note["trip_day_id"], self.day1["id"])
        self.assertEqual(note["source_surface"], "travel_doc_modal")
        self.assertEqual(note["include_in_memoir"], 0)
        self.assertEqual(note["include_in_interview_context"], 0)
        self.assertIn("United flight", note["note_text"])

    def test_ack_contains_day_number_narrator_words_one_question(self):
        res = self._capture(UNITED_FLIGHT_MEMORY, day_id=self.day1["id"])
        ack = modal.compose_day_capture_ack(
            self.day1, res, UNITED_FLIGHT_MEMORY)
        self.assertIsNotNone(ack)
        self.assertIn("Day 1", ack)
        self.assertTrue(ack.startswith("Got it — I saved that as a Day 1"))
        # The narrator's OWN wording, verbatim.
        self.assertIn("Our United flight out of Santa Fe got canceled",
                      ack)
        # Exactly ONE follow-up question, and it is the fixed one.
        self.assertEqual(ack.count("?"), 1)
        self.assertIn("Anything else from that day", ack)
        self.assertIn("where you stayed, or what you ate?", ack)
        # Provenance rules hold: no vision claims, no invented facts.
        self.assertNotIn("I can see", ack)
        # No anchor-echo shape ("From X to Y to Z — X.").
        self.assertNotIn("From Santa Fe to Munich to lost", ack)

    def test_ack_excerpt_caps_at_about_25_words_with_ellipsis(self):
        res = self._capture(UNITED_FLIGHT_MEMORY, day_id=self.day1["id"])
        ack = modal.compose_day_capture_ack(
            self.day1, res, UNITED_FLIGHT_MEMORY)
        start = ack.index('"') + 1
        end = ack.index('"', start)
        quoted = ack[start:end]
        self.assertLessEqual(len(quoted.rstrip("…").split()), 25)
        self.assertTrue(quoted.endswith("…"),
                        "long memory must be visibly truncated")

    def test_short_memory_gets_no_ellipsis(self):
        text = "We lost a whole day in Santa Fe after the flight was canceled."
        res = self._capture(text, day_id=self.day1["id"])
        ack = modal.compose_day_capture_ack(self.day1, res, text)
        self.assertIn('"We lost a whole day in Santa Fe after the flight '
                      'was canceled"', ack)
        self.assertNotIn("…", ack)

    def test_duplicate_capture_still_acks(self):
        self._capture(UNITED_FLIGHT_MEMORY, day_id=self.day1["id"],
                      turn_id="t_dup")
        res2 = self._capture(UNITED_FLIGHT_MEMORY, day_id=self.day1["id"],
                             turn_id="t_dup")
        self.assertEqual(res2["reason"], "duplicate")
        ack = modal.compose_day_capture_ack(
            self.day1, res2, UNITED_FLIGHT_MEMORY)
        self.assertIsNotNone(ack)
        self.assertIn("Day 1", ack)


class QuestionTurnsStillRouteTest(_DayCaptureCase):
    def test_question_turn_is_not_captured(self):
        res = self._capture("what date was that taken",
                            day_id=self.day1["id"])
        self.assertFalse(res["captured"])
        self.assertEqual(res["reason"], "direct_question_or_command")
        # And the ack composer refuses it — question turns belong to
        # answer_modal_direct_question / the LLM path.
        self.assertIsNone(modal.compose_day_capture_ack(
            self.day1, res, "what date was that taken"))

    def test_direct_question_answered_deterministically(self):
        answer = modal.answer_modal_direct_question(
            self.person_id, self._scope(self.day1["id"]),
            "what date was that taken")
        self.assertIsNotNone(answer)
        self.assertIn("taken date", answer)

    def test_trivial_turn_not_captured_not_acked(self):
        res = self._capture("yes", day_id=self.day1["id"])
        self.assertFalse(res["captured"])
        self.assertIsNone(modal.compose_day_capture_ack(
            self.day1, res, "yes"))


class NonDayModalTurnsUnchangedTest(_DayCaptureCase):
    def test_capture_without_day_scope_writes_null_day(self):
        res = self._capture(UNITED_FLIGHT_MEMORY, day_id=None)
        self.assertTrue(res["captured"], res)
        self.assertIsNone(res.get("trip_day_id"))
        note = trip_repository.location_note_get(res["note_id"])
        self.assertIsNone(note["trip_day_id"])

    def test_ack_requires_a_day_row(self):
        res = self._capture(UNITED_FLIGHT_MEMORY, day_id=None)
        self.assertIsNone(modal.compose_day_capture_ack(
            None, res, UNITED_FLIGHT_MEMORY))

    def test_cross_trip_day_id_is_dropped_not_written(self):
        other_trip = trip_repository.trip_create(
            self.person_id, "Other Trip",
            start_date="2026-06-01", end_date="2026-06-02")
        trip_repository.trip_days_generate(other_trip)
        foreign_day = trip_repository.trip_days_list(other_trip)[0]
        scope = self._scope(foreign_day["id"])
        # build_modal_scope already refuses the cross-trip day.
        self.assertIsNone(scope["active_trip_day_id"])
        res = modal.capture_modal_answer(
            person_id=self.person_id, scope=scope,
            narrator_text=UNITED_FLIGHT_MEMORY,
            conv_id="tdlab_conv", turn_id="t_cross")
        self.assertTrue(res["captured"])
        note = trip_repository.location_note_get(res["note_id"])
        self.assertIsNone(note["trip_day_id"])

    def test_scope_carries_validated_day_id(self):
        scope = self._scope(self.day1["id"])
        self.assertEqual(scope["active_trip_day_id"], self.day1["id"])
        self.assertEqual(scope["source_surface"], "travel_doc_modal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
