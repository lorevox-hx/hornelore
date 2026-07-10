"""WO-TRIP-LANE-AUDIT-FIXPACK-01 (C1) — narrator_photo_links() must
return a narrator-safe allowlist, never SELECT l.*.

Locks the leak class the audit found: raw GPS lat/lon and un-approved
operator caption / operator_context_note reaching the Travels shelf
(narrator-visible) via SELECT l.*. Same offline temp-DB fixture pattern
as tests/test_trip_interview_context.py.
"""
from __future__ import annotations

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


def _add_photo(con, pid, narrator_id, ready, lat=None, lon=None):
    con.execute(
        "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
        "narrator_ready, latitude, longitude) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pid, narrator_id, "/tmp/" + pid + ".jpg", "hash-" + pid, ready,
         lat, lon),
    )


class NarratorPhotoLinksSafeTest(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(
            suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())

        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "created_at, updated_at) VALUES (?, 'P', '1962-12-24', "
            "'2026-07-08', '2026-07-08');", (self.person_id,))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026", start_date="2026-05-22",
            end_date="2026-06-13")
        self.region_id = trip_repository.region_create(
            self.trip_id, "Germany")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Munich")

        con = sqlite3.connect(str(self.db_path))
        # Ready photo carries raw GPS on the LINK row too (upsert copies
        # EXIF coords in) — this is exactly what must not project.
        _add_photo(con, "p_ready", self.person_id, 1, lat=48.137, lon=11.575)
        _add_photo(con, "p_unready", self.person_id, 0)
        con.commit()
        con.close()

        self.link_id = trip_repository.photo_link_upsert(
            self.trip_id, "p_ready", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, latitude=48.137, longitude=11.575,
            assignment_method="exif_gps")

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _set_link(self, **cols):
        con = sqlite3.connect(str(self.db_path))
        sets = ", ".join(k + " = ?" for k in cols)
        con.execute("UPDATE trip_photo_links SET " + sets + " WHERE id = ?",
                    (*cols.values(), self.link_id))
        con.commit()
        con.close()

    def _one(self):
        rows = trip_repository.narrator_photo_links(self.trip_id)
        self.assertEqual(len(rows), 1)
        return rows[0]

    # --- raw GPS never projected ---------------------------------------
    def test_no_latitude_key(self):
        self.assertNotIn("latitude", self._one())

    def test_no_longitude_key(self):
        self.assertNotIn("longitude", self._one())

    def test_gps_present_boolean_only(self):
        self._set_link(latitude=48.137, longitude=11.575)
        row = self._one()
        self.assertIn("gps_present", row)
        self.assertEqual(row["gps_present"], 1)
        self.assertNotIn("latitude", row)
        self.assertNotIn("longitude", row)

    # --- operator caption gated on approval ----------------------------
    def test_ungated_operator_caption_does_not_reach_narrator(self):
        self._set_link(caption="OPERATOR_ONLY_NOTE",
                       caption_approved_for_lori=0)
        row = self._one()
        self.assertIsNone(row["caption"])
        # The raw operator caption column must not leak under any key.
        self.assertNotIn("OPERATOR_ONLY_NOTE", str(row.values()))

    def test_approved_operator_caption_reaches_narrator(self):
        self._set_link(caption="the train station in Munich",
                       caption_approved_for_lori=1)
        self.assertEqual(self._one()["caption"], "the train station in Munich")

    def test_narrator_caption_preferred_over_approved_operator(self):
        self._set_link(caption="operator words",
                       caption_approved_for_lori=1,
                       narrator_caption="my own words")
        self.assertEqual(self._one()["caption"], "my own words")

    def test_narrator_caption_used_when_operator_unapproved(self):
        self._set_link(caption="operator words",
                       caption_approved_for_lori=0,
                       narrator_caption="my own words")
        self.assertEqual(self._one()["caption"], "my own words")

    # --- operator_context_note gated on approval -----------------------
    def test_operator_context_note_hidden_when_unapproved(self):
        self._set_link(operator_context_note="OPERATOR_CONTEXT",
                       operator_context_approved_for_lori=0)
        row = self._one()
        self.assertIsNone(row["operator_context_note"])
        self.assertNotIn("OPERATOR_CONTEXT", str(row.values()))

    def test_operator_context_note_shown_when_approved(self):
        self._set_link(operator_context_note="approved context",
                       operator_context_approved_for_lori=1)
        self.assertEqual(self._one()["operator_context_note"],
                         "approved context")

    # --- existing narrator_ready gating preserved ----------------------
    def test_non_narrator_ready_photo_excluded(self):
        # The unready photo's link must never appear even with an
        # approved caption.
        lu = trip_repository.photo_link_upsert(
            self.trip_id, "p_unready", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, assignment_method="exif_time")
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE trip_photo_links SET caption=?, "
                    "caption_approved_for_lori=1 WHERE id=?",
                    ("SECRET_UNREADY", lu))
        con.commit()
        con.close()
        rows = trip_repository.narrator_photo_links(self.trip_id)
        # Only the ready link surfaces.
        self.assertEqual({r["photo_id"] for r in rows}, {"p_ready"})

    # --- shelf-required fields still present ---------------------------
    def test_shelf_fields_present(self):
        row = self._one()
        for key in ("id", "photo_id", "trip_stop_id", "caption"):
            self.assertIn(key, row)


if __name__ == "__main__":
    unittest.main()
