"""WO-TRIP-INTERVIEW-CONTEXT-01 Step 1 — isolated context service.

Read-only assembly of a compact, narrator-safe trip context block. No
wiring into chat_ws/prompt_composer in Step 1.
"""
from __future__ import annotations

import ast
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
from api.services import trip_interview_context as tic  # noqa: E402


def _add_photo(con, pid, narrator_id, ready):
    con.execute(
        "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
        "narrator_ready) VALUES (?, ?, ?, ?, ?)",
        (pid, narrator_id, "/tmp/" + pid + ".jpg", "hash-" + pid, ready),
    )


class _ContextCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        self.other_person = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        for pid in (self.person_id, self.other_person):
            con.execute(
                "INSERT INTO people (id, display_name, date_of_birth, "
                "created_at, updated_at) VALUES (?, 'P', '1962-12-24', "
                "'2026-07-08', '2026-07-08');", (pid,))
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            self.person_id, "Spring 2026", start_date="2026-05-22",
            end_date="2026-06-13")
        self.region_id = trip_repository.region_create(self.trip_id, "Germany")
        self.stop_id = trip_repository.stop_create(
            self.trip_id, self.region_id, "Munich")

        # Notes: interview-flagged, memoir-only, and neither.
        trip_repository.location_note_create(
            self.trip_id, "Germany was the first leg", note_title="Arrival",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_interview_context=True)
        trip_repository.location_note_create(
            self.trip_id, "memoir only note",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_memoir=True, include_in_interview_context=False)
        trip_repository.location_note_create(
            self.trip_id, "private unpromoted note",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id)

        # A source (must never surface).
        trip_repository.source_create(
            self.trip_id, source_type="hotel",
            title="Hotel booking", pasted_text="SECRET_SOURCE_TEXT",
            trip_region_id=self.region_id, trip_stop_id=self.stop_id,
            include_in_memoir=True)

        # Photos: one narrator-ready (with caption), one not (with caption).
        con = sqlite3.connect(str(self.db_path))
        _add_photo(con, "p_ready", self.person_id, 1)
        _add_photo(con, "p_unready", self.person_id, 0)
        con.commit()
        con.close()
        lr = trip_repository.photo_link_upsert(
            self.trip_id, "p_ready", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, assignment_method="operator")
        lu = trip_repository.photo_link_upsert(
            self.trip_id, "p_unready", trip_region_id=self.region_id,
            trip_stop_id=self.stop_id, assignment_method="operator")
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE trip_photo_links SET caption=? WHERE id=?",
                    ("the train station in Munich", lr))
        con.execute("UPDATE trip_photo_links SET caption=? WHERE id=?",
                    ("SECRET_UNREADY_CAPTION", lu))
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _ctx(self, stop=None):
        return tic.build_trip_interview_context(
            self.person_id, self.trip_id, active_trip_stop_id=stop)

    # 1
    def test_returns_title_dates_route(self):
        c = self._ctx()
        self.assertEqual(c["title"], "Spring 2026")
        self.assertEqual(c["date_span"], "2026-05-22 to 2026-06-13")
        self.assertEqual(c["route"][0]["region"], "Germany")
        self.assertIn("Munich", c["route"][0]["stops"])

    # 2
    def test_rejects_trip_not_owned(self):
        self.assertIsNone(tic.build_trip_interview_context(
            self.other_person, self.trip_id))
        self.assertIsNone(tic.build_trip_interview_context(
            self.person_id, "no-such-trip"))

    # 3 + 4
    def test_only_interview_flagged_notes(self):
        c = self._ctx()
        texts = " ".join(n["text"] for n in c["notes"])
        self.assertIn("Germany was the first leg", texts)
        self.assertNotIn("memoir only note", texts)       # memoir-only excluded
        self.assertNotIn("private unpromoted note", texts)  # neither excluded

    # 5
    def test_includes_narrator_ready_caption(self):
        c = self._ctx()
        joined = c["text"] + " " + " ".join(x["caption"] for x in c["photo_captions"])
        self.assertIn("the train station in Munich", joined)

    # 6
    def test_excludes_non_narrator_ready_caption(self):
        c = self._ctx()
        self.assertNotIn("SECRET_UNREADY_CAPTION", c["text"])
        for x in c["photo_captions"]:
            self.assertNotIn("SECRET_UNREADY_CAPTION", x["caption"])

    # 7
    def test_no_raw_source_text(self):
        c = self._ctx()
        self.assertNotIn("SECRET_SOURCE_TEXT", c["text"])
        self.assertNotIn("sources", c)  # sources not surfaced at all

    # 8
    def test_output_is_compact(self):
        c = self._ctx()
        self.assertLessEqual(len(c["notes"]), tic._MAX_NOTES)
        self.assertLessEqual(len(c["photo_captions"]), tic._MAX_CAPTIONS)
        self.assertIsInstance(c["text"], str)
        self.assertLess(len(c["text"]), 4000)  # small for a small trip

    def test_active_stop_surfaced(self):
        c = self._ctx(stop=self.stop_id)
        self.assertEqual(c["active"]["name"], "Munich")
        self.assertIn("Currently looking at: Munich", c["text"])

    # 9
    def test_law3_isolation(self):
        p = _SERVER_CODE / "api" / "services" / "trip_interview_context.py"
        tree = ast.parse(p.read_text(encoding="utf-8"))
        forbidden = ("chat_ws", "prompt_composer", "extract", "memory_echo",
                     "llm_interview", "llm_api", "safety")
        mods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mods.append(node.module or "")
                mods += [(node.module or "") + "." + a.name for a in node.names]
        for m in mods:
            for bad in forbidden:
                self.assertNotIn(bad, m, "forbidden import: " + m)


if __name__ == "__main__":
    unittest.main()
