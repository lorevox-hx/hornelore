"""WO-TRAVEL-DOC-LORI-MODAL-01 — Mark Twain acceptance gate.

This file is intentionally an opt-in acceptance test until the Travel Doc
Lori modal implementation lands. It gives Claude/Codex a concrete fake
narrator/trip/photo workflow to satisfy without touching Chris or any real
narrator data.

Run after the modal build exists:

    HORNELORE_RUN_MODAL_ACCEPTANCE=1 \
      pytest tests/test_travel_doc_lori_modal_mark_twain.py

Expected service API for the modal build:

    api.services.travel_doc_lori_modal.build_modal_scope(...)
    api.services.travel_doc_lori_modal.answer_modal_direct_question(...)
    api.services.travel_doc_lori_modal.capture_modal_answer(...)

The tests lock the product rule: Travel Doc stays open, Lori runs in a
Travel-Doc-scoped modal, approved photo context is used, unapproved dates stay
hidden, and modal answers become reviewable Travel Doc story-note candidates.
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

_RUN = os.getenv("HORNELORE_RUN_MODAL_ACCEPTANCE", "0").strip() in {
    "1", "true", "yes", "on",
}


def _insert_person(con: sqlite3.Connection, person_id: str, name: str) -> None:
    con.execute(
        "INSERT INTO people (id, display_name, date_of_birth, created_at, updated_at) "
        "VALUES (?, ?, '1835-11-30', '2026-07-10', '2026-07-10')",
        (person_id, name),
    )


def _insert_photo(con: sqlite3.Connection, photo_id: str, person_id: str) -> None:
    """Insert a fake photo row using whatever Ph1 columns exist in the DB.

    Ph1 should already provide date_source/taken_at_filename_guess and Lori
    approval flags. This helper still builds the INSERT from PRAGMA so the
    failure points are readable if the schema drifts.
    """
    cols = {r[1] for r in con.execute("PRAGMA table_info(photos)")}
    values = {
        "id": photo_id,
        "narrator_id": person_id,
        "image_path": "/tmp/mark-twain-modal-test.jpg",
        "file_hash": "hash-mark-twain-modal-test",
        "narrator_ready": 1,
        "date_value": None,
        "date_precision": "unknown",
        "date_source": "filename_guess",
        "taken_at_filename_guess": "2026-05-14",
        "location_label": "Munich area",
        "location_source": "unknown",
        "date_approved_for_lori": 0,
        "location_approved_for_lori": 0,
        # Raw GPS must never be surfaced to Lori. These values are fake.
        "latitude": 48.137154,
        "longitude": 11.576124,
    }
    used = [c for c in values if c in cols]
    con.execute(
        "INSERT INTO photos (" + ", ".join(used) + ") VALUES (" +
        ", ".join(["?"] * len(used)) + ")",
        [values[c] for c in used],
    )


@unittest.skipUnless(
    _RUN,
    "pending Travel Doc Lori modal build; set HORNELORE_RUN_MODAL_ACCEPTANCE=1",
)
class MarkTwainTravelDocLoriModalAcceptance(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.person_id = str(uuid.uuid4())
        self.conv_id = "mark_twain_modal_test_conv"
        self.turn_id = "mark_twain_modal_test_turn_001"

        con = sqlite3.connect(str(self.db_path))
        _insert_person(con, self.person_id, "Mark Twain Modal Test")
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id,
            "Mark Twain Test Trip — Bavaria Photo Modal",
            start_date="2026-05-14",
            end_date="2026-05-14",
        )
        self.region_id = trip_repository.region_create(
            self.trip_id, "Germany / Bavaria")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Munich Natural History Museum")

        self.photo_id = "mark_twain_modal_photo"
        con = sqlite3.connect(str(self.db_path))
        _insert_photo(con, self.photo_id, self.person_id)
        con.commit()
        con.close()

        self.photo_link_id = trip_repository.photo_link_upsert(
            self.trip_id,
            self.photo_id,
            trip_region_id=self.region_id,
            trip_stop_id=self.stop_id,
            assignment_method="operator",
        )
        trip_repository.photo_link_update(
            self.photo_link_id,
            caption="Outside a natural history museum in Munich",
            caption_approved_for_lori=True,
            operator_context_note="Men nearby were wearing lederhosen during a local holiday.",
            operator_context_approved_for_lori=True,
        )

    def tearDown(self) -> None:
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _modal(self):
        from api.services import travel_doc_lori_modal as modal  # noqa: E402
        return modal

    def _scope(self):
        return self._modal().build_modal_scope(
            person_id=self.person_id,
            active_trip_id=self.trip_id,
            active_trip_region_id=self.region_id,
            active_trip_stop_id=self.stop_id,
            active_photo_link_id=self.photo_link_id,
            conv_id=self.conv_id,
            selected_kind="photo",
        )

    def test_modal_scope_is_photo_scoped_and_travel_doc_owned(self):
        scope = self._scope()
        self.assertEqual(scope["source_surface"], "travel_doc_modal")
        self.assertEqual(scope["person_id"], self.person_id)
        self.assertEqual(scope["active_trip_id"], self.trip_id)
        self.assertEqual(scope["active_trip_region_id"], self.region_id)
        self.assertEqual(scope["active_trip_stop_id"], self.stop_id)
        self.assertEqual(scope["active_photo_link_id"], self.photo_link_id)
        self.assertEqual(scope["selected_kind"], "photo")
        self.assertNotIn("travels_shelf_open", scope)
        self.assertNotIn("activeTripId", scope)

    def test_date_question_hides_unapproved_filename_guess(self):
        answer = self._modal().answer_modal_direct_question(
            self.person_id, self._scope(), "what date was that taken")
        self.assertIn("approved taken date", answer)
        self.assertIn("Travel Doc can store", answer)
        self.assertNotIn("2026-05-14", answer)  # filename guess is not approved
        for forbidden in ("uploaded_at", "file_saved_at", "file_modified_at",
                          "48.137", "11.576", "I can see"):
            self.assertNotIn(forbidden, answer)

    def test_date_question_uses_approved_taken_date_after_operator_approval(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "UPDATE photos SET date_value='2026-05-14', date_source='operator_confirmed', "
            "date_approved_for_lori=1 WHERE id=?",
            (self.photo_id,),
        )
        con.commit(); con.close()

        answer = self._modal().answer_modal_direct_question(
            self.person_id, self._scope(), "what date was that taken")
        self.assertIn("May 14, 2026", answer)
        self.assertNotIn("uploaded_at", answer)
        self.assertNotIn("file_saved_at", answer)
        self.assertNotIn("file_modified_at", answer)

    def test_tell_me_about_photo_uses_only_approved_caption_and_context(self):
        answer = self._modal().answer_modal_direct_question(
            self.person_id, self._scope(), "can you tell me about the photo")
        self.assertIn("natural history museum in Munich", answer)
        self.assertIn("lederhosen", answer.lower())
        for forbidden in ("I can see", "the photo shows", "48.137", "11.576", "2026-05-14"):
            self.assertNotIn(forbidden, answer)

    def test_modal_capture_creates_reviewable_photo_linked_story_note(self):
        out = self._modal().capture_modal_answer(
            person_id=self.person_id,
            scope=self._scope(),
            narrator_text=(
                "This was outside a natural history museum in Munich, and I "
                "remember men in lederhosen nearby."
            ),
            previous_lori_text="What do you remember about this photo?",
            conv_id=self.conv_id,
            turn_id=self.turn_id,
        )
        self.assertTrue(out.get("captured"), out)

        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        cols = {r[1] for r in con.execute("PRAGMA table_info(trip_location_notes)")}
        self.assertIn("source_surface", cols)
        self.assertIn("source_turn_ref", cols)
        self.assertIn("photo_link_id", cols)
        row = con.execute(
            "SELECT * FROM trip_location_notes WHERE trip_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (self.trip_id,),
        ).fetchone()
        con.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["source_type"], "lori")
        self.assertEqual(row["source_surface"], "travel_doc_modal")
        self.assertEqual(row["source_turn_ref"], "modal_turn:%s:%s" % (self.conv_id, self.turn_id))
        self.assertEqual(row["photo_link_id"], self.photo_link_id)
        self.assertEqual(row["trip_region_id"], self.region_id)
        self.assertEqual(row["trip_stop_id"], self.stop_id)
        self.assertEqual(row["include_in_memoir"], 0)
        self.assertEqual(row["include_in_interview_context"], 0)
        self.assertIn("natural history museum", row["note_text"])

    def test_travel_documenter_js_uses_modal_not_travels_shelf_for_talk_button(self):
        js = (_REPO_ROOT / "ui" / "js" / "travel-documenter.js").read_text(
            encoding="utf-8")
        self.assertIn("travel_doc_modal", js)
        self.assertIn("modalLori", js)
        self.assertNotIn("window.lvTravelsOpenTripById(st.trip.id)", js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
