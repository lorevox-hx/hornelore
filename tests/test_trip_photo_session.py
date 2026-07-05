"""WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C3 — trip-scoped photo
sessions.

Selector allowlist (trip/stop-linked photos only), session trip-scope
persistence (migration 0017 + pre-0017 fallback), and stop-name prompt
grounding ("This one's from Prague" only from operator placement —
never invented).
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

import types  # noqa: E402

if "pydantic" not in sys.modules:
    try:
        import pydantic  # noqa: F401
    except ImportError:
        pstub = types.ModuleType("pydantic")
        pstub.BaseModel = type("BaseModel", (), {})
        pstub.Field = lambda default=None, **k: default
        pstub.field_validator = lambda *a, **k: (lambda f: f)
        pstub.validator = lambda *a, **k: (lambda f: f)
        pstub.ConfigDict = dict
        sys.modules["pydantic"] = pstub

from api import db as _db  # noqa: E402
from api.services import trip_repository  # noqa: E402
from services.photo_elicit.selector import select_next_photo  # noqa: E402
from services.photo_elicit.template_prompt import build_photo_prompt  # noqa: E402
from services.photos import repository as photo_repo  # noqa: E402


class _TripSessionCase(unittest.TestCase):
    def setUp(self):
        self._tmpdb = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmpdb.close()
        self.db_path = Path(self._tmpdb.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, created_at, updated_at) "
            "VALUES (?, 'Session Test', '2026-07-05', '2026-07-05');",
            (self.person_id,),
        )
        # Three narrator-ready photos: two linked to the trip, one not.
        for pid in ("ph-a", "ph-b", "ph-other"):
            con.execute(
                "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
                "narrator_ready) VALUES (?, ?, ?, ?, 1);",
                (pid, self.person_id, f"/tmp/{pid}.jpg", f"h-{pid}"),
            )
        con.commit()
        con.close()

        self.trip_id = trip_repository.trip_create(
            person_id=self.person_id, title="Spring 2026",
            start_date="2026-05-22", end_date="2026-06-13",
        )
        self.region_id = trip_repository.region_create(self.trip_id, "Czechia")
        self.stop_prague = trip_repository.stop_create(
            self.trip_id, self.region_id, "Prague")
        self.stop_brno = trip_repository.stop_create(
            self.trip_id, self.region_id, "Brno")
        trip_repository.photo_link_upsert(
            self.trip_id, "ph-a", trip_stop_id=self.stop_prague,
            assignment_method="operator", cluster_confidence=1.0)
        trip_repository.photo_link_upsert(
            self.trip_id, "ph-b", trip_stop_id=self.stop_brno,
            assignment_method="operator", cluster_confidence=1.0)

    def tearDown(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _linked_ids(self, stop_id=None):
        links = trip_repository.photo_links_list(self.trip_id)
        return [l["photo_id"] for l in links
                if stop_id is None or l.get("trip_stop_id") == stop_id]


class SelectorAllowlistTest(_TripSessionCase):
    def test_trip_scope_excludes_unlinked_photos(self):
        allowed = self._linked_ids()
        seen = set()
        # Selector prefers unshown; drain by recording shows.
        session = photo_repo.create_photo_session(self.person_id)
        for _ in range(3):
            pick = select_next_photo(self.person_id, photo_repo,
                                     photo_ids=allowed)
            if pick is None:
                break
            seen.add(pick["id"])
            photo_repo.record_photo_show(
                photo_session_id=session["id"], photo_id=pick["id"],
                prompt_text="t")
        self.assertEqual(seen, {"ph-a", "ph-b"})
        self.assertNotIn("ph-other", seen)

    def test_stop_scope_narrows_to_one(self):
        allowed = self._linked_ids(stop_id=self.stop_prague)
        pick = select_next_photo(self.person_id, photo_repo,
                                 photo_ids=allowed)
        self.assertEqual(pick["id"], "ph-a")

    def test_none_allowlist_is_legacy_behavior(self):
        pick = select_next_photo(self.person_id, photo_repo, photo_ids=None)
        self.assertIsNotNone(pick)  # all narrator-ready photos eligible

    def test_empty_allowlist_returns_none(self):
        pick = select_next_photo(self.person_id, photo_repo, photo_ids=[])
        self.assertIsNone(pick)


class SessionTripScopeTest(_TripSessionCase):
    def test_session_persists_trip_scope(self):
        row = photo_repo.create_photo_session(
            self.person_id, trip_id=self.trip_id,
            trip_stop_id=self.stop_prague)
        fetched = photo_repo.get_photo_session(row["id"])
        self.assertEqual(fetched.get("trip_id"), self.trip_id)
        self.assertEqual(fetched.get("trip_stop_id"), self.stop_prague)

    def test_unscoped_session_unchanged(self):
        row = photo_repo.create_photo_session(self.person_id)
        fetched = photo_repo.get_photo_session(row["id"])
        self.assertFalse(fetched.get("trip_id"))

    def test_pre_0017_db_falls_back_unscoped(self):
        # Drop the 0017 columns by recreating the table without them.
        con = sqlite3.connect(str(self.db_path))
        con.executescript(
            "DROP TABLE photo_sessions;"
            "CREATE TABLE photo_sessions ("
            " id TEXT PRIMARY KEY, narrator_id TEXT NOT NULL,"
            " session_id TEXT, started_at TEXT, ended_at TEXT,"
            " created_at TEXT);"
        )
        con.commit()
        con.close()
        row = photo_repo.create_photo_session(
            self.person_id, trip_id=self.trip_id)
        self.assertIsNotNone(row["id"])  # created, just unscoped


class PromptGroundingTest(_TripSessionCase):
    def test_stop_name_grounds_prompt(self):
        # What show_next composes for a trip-scoped, located photo: the
        # operator-placed stop name feeds "place".
        prompt = build_photo_prompt({
            "people": ["Melanie"],
            "place": "Prague",
            "date": None,
        })
        self.assertIn("Prague", prompt)

    def test_ungrounded_photo_gets_warm_open_no_invention(self):
        # No people/place/date → zero tier: warm open, no fake context.
        prompt = build_photo_prompt({"people": [], "place": None, "date": None})
        self.assertNotIn("Prague", prompt)
        self.assertNotIn("shows", prompt)
        self.assertTrue(len(prompt) > 10)


if __name__ == "__main__":
    unittest.main()
