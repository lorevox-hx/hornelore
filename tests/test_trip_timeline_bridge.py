"""WO-TRIP-IMPORT-AND-CLUSTER-01 Phase B — trip → life-record bridge.

Era derivation from DOB + start_date, timeline_events projection
(kind="trip"), bio suggestion upsert, ghost-event removal on delete.
Temp DB via db.init_db() (full schema), DB_PATH patched.
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
from api.lv_eras import era_id_from_age  # noqa: E402
from api.services import trip_repository, trip_timeline_bridge  # noqa: E402


class _BridgeCase(unittest.TestCase):
    DOB = "1962-12-24"

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)
        self._original = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.person_id = str(uuid.uuid4())
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, created_at, "
            "updated_at) VALUES (?, 'Bridge Test', ?, '2026-07-05', '2026-07-05');",
            (self.person_id, self.DOB),
        )
        con.commit()
        con.close()

    def tearDown(self):
        _db.DB_PATH = self._original
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def _trip(self, start="2026-05-22", end="2026-06-13"):
        return trip_repository.trip_create(
            person_id=self.person_id, title="Bridge Trip",
            start_date=start, end_date=end,
        )

    def test_sync_writes_era_event_and_suggestion(self):
        trip_id = self._trip()
        r = trip_repository.region_create(trip_id, "R1")
        trip_repository.stop_create(trip_id, r, "Prague")
        out = trip_timeline_bridge.sync_trip_to_life_record(trip_id)

        # Era matches the canonical age math (63-year-old narrator).
        expected_era = era_id_from_age(63.4)
        self.assertEqual(out["era_id"], expected_era)

        # Timeline event exists, kind=trip, carries the trip link.
        events = _db.list_timeline_events(self.person_id)
        trip_events = [e for e in events if e.get("kind") == "trip"]
        self.assertEqual(len(trip_events), 1)
        ev = trip_events[0]
        self.assertEqual(ev["title"], "Bridge Trip")
        self.assertEqual(ev["date"], "2026-05-22")
        self.assertIn("1 region", ev["body"])
        self.assertEqual(ev["meta"].get("trip_id"), trip_id)
        self.assertEqual(ev["meta"].get("era_id"), expected_era)

        # Trip meta carries era + event link (visible projection).
        trip = trip_repository.trip_get(trip_id)
        self.assertEqual(trip["meta_json"].get("era_id"), expected_era)
        self.assertEqual(trip["meta_json"].get("timeline_event_id"), ev["id"])

        # Bio suggestion row, status=suggested (never auto-promoted).
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM trip_bio_suggestions WHERE trip_id=?;", (trip_id,),
        ).fetchall()
        con.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "suggested")
        self.assertIn("Bridge Trip", rows[0]["suggested_value"])

    def test_resync_is_idempotent_one_event(self):
        trip_id = self._trip()
        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        events = [e for e in _db.list_timeline_events(self.person_id)
                  if e.get("kind") == "trip"]
        self.assertEqual(len(events), 1)
        # Only one bio suggestion too.
        con = sqlite3.connect(str(self.db_path))
        n = con.execute(
            "SELECT COUNT(*) FROM trip_bio_suggestions WHERE trip_id=?;",
            (trip_id,),
        ).fetchone()[0]
        con.close()
        self.assertEqual(n, 1)

    def test_missing_dob_era_none_event_still_written(self):
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE people SET date_of_birth='' WHERE id=?;",
                    (self.person_id,))
        con.commit()
        con.close()
        trip_id = self._trip()
        out = trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        self.assertIsNone(out["era_id"])
        self.assertIsNotNone(out["timeline_event_id"])

    def test_no_dates_no_event_no_crash(self):
        trip_id = self._trip(start=None, end=None)
        out = trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        self.assertIsNone(out["timeline_event_id"])
        self.assertNotIn("error", out)

    def test_delete_removes_ghost_event(self):
        trip_id = self._trip()
        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        trip = trip_repository.trip_get(trip_id)
        trip_timeline_bridge.remove_trip_from_life_record(trip)
        trip_repository.trip_delete(trip_id)
        events = [e for e in _db.list_timeline_events(self.person_id)
                  if e.get("kind") == "trip"]
        self.assertEqual(events, [])
        # Suggestion rows cascade with the trip.
        con = sqlite3.connect(str(self.db_path))
        n = con.execute("SELECT COUNT(*) FROM trip_bio_suggestions;").fetchone()[0]
        con.close()
        self.assertEqual(n, 0)

    def test_meta_merge_preserves_other_keys(self):
        # Review fix 2026-07-05: sync uses atomic trip_meta_merge, so
        # unrelated meta keys written by other surfaces must survive.
        trip_id = self._trip()
        trip_repository.trip_meta_merge(trip_id, {"operator_note": "keep me"})
        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        trip = trip_repository.trip_get(trip_id)
        self.assertEqual(trip["meta_json"].get("operator_note"), "keep me")
        self.assertIsNotNone(trip["meta_json"].get("timeline_event_id"))
        self.assertIsNotNone(trip["meta_json"].get("era_id"))

    def test_meta_merge_missing_trip_returns_false(self):
        self.assertFalse(
            trip_repository.trip_meta_merge("no-such-trip", {"k": "v"}))

    def test_child_era_derivation(self):
        # Narrator born 2000, trip at age 8 → early school years.
        con = sqlite3.connect(str(self.db_path))
        con.execute("UPDATE people SET date_of_birth='2000-01-01' WHERE id=?;",
                    (self.person_id,))
        con.commit()
        con.close()
        trip_id = self._trip(start="2008-06-01", end="2008-06-10")
        out = trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        self.assertEqual(out["era_id"], era_id_from_age(8))


class AccordionProjectionTest(_BridgeCase):
    """The trip must appear in the chronology accordion payload (the
    room's left column) — the visible half of the timeline integration."""

    def test_trip_appears_in_accordion(self):
        import types
        # Minimal fastapi stub so the router module imports offline
        # (same approach as tests/test_extract_affect_name_guard.py).
        if "fastapi" not in sys.modules:
            stub = types.ModuleType("fastapi")

            class _APIRouter:
                def __init__(self, *a, **k):
                    pass

                def _deco(self, *a, **k):
                    def wrap(f):
                        return f
                    return wrap
                get = post = patch = delete = put = _deco

            class _HTTPException(Exception):
                def __init__(self, status_code=0, detail=""):
                    self.status_code, self.detail = status_code, detail

            stub.APIRouter = _APIRouter
            stub.HTTPException = _HTTPException
            stub.Query = lambda default=None, **k: default
            sys.modules["fastapi"] = stub

        trip_id = self._trip()
        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        from api.routers.chronology_accordion import (
            build_chronology_accordion_payload,
        )
        payload = build_chronology_accordion_payload(
            person_id=self.person_id,
            profile={"basics": {"dob": self.DOB}},
            questionnaire=None,
            promoted_rows=[],
            narrator_display_name="Bridge Test",
        )
        hits = []
        for dec in payload.get("decades", []):
            for yr in dec.get("years", []):
                for it in yr.get("items", []):
                    if it.get("event_kind") == "trip":
                        hits.append((yr.get("year"), it.get("label")))
        self.assertEqual(hits, [(2026, "Trip — Bridge Trip")])

    def test_trip_item_carries_photo_strip(self):
        import types
        if "fastapi" not in sys.modules:
            stub = types.ModuleType("fastapi")

            class _APIRouter:
                def __init__(self, *a, **k):
                    pass

                def _deco(self, *a, **k):
                    def wrap(f):
                        return f
                    return wrap
                get = post = patch = delete = put = _deco

            stub.APIRouter = _APIRouter
            stub.HTTPException = type("HTTPException", (Exception,), {})
            stub.Query = lambda default=None, **k: default
            sys.modules["fastapi"] = stub

        trip_id = self._trip()
        r = trip_repository.region_create(trip_id, "R1")
        stop_id = trip_repository.stop_create(trip_id, r, "Rovinj")
        # Seed a photo + memoir-included link.
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "date_value, narrator_ready) VALUES ('ph-strip', ?, "
            "'/tmp/p.jpg', 'h-strip', '2026-05-28', 1);", (self.person_id,),
        )
        # Unvetted photo (narrator_ready=0) must NOT reach the
        # narrator-visible accordion strip (BUG-238 class).
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "date_value, narrator_ready) VALUES ('ph-unvetted', ?, "
            "'/tmp/u.jpg', 'h-unvetted', '2026-05-29', 0);",
            (self.person_id,),
        )
        con.commit()
        con.close()
        link_id = trip_repository.photo_link_upsert(
            trip_id, "ph-strip", trip_stop_id=stop_id,
            taken_at="2026-05-28 16:30:00",
        )
        trip_repository.photo_link_update(link_id, caption="Rovinj harbor")
        trip_repository.photo_link_upsert(
            trip_id, "ph-unvetted", trip_stop_id=stop_id,
            taken_at="2026-05-29 10:00:00",
        )
        from api.routers.chronology_accordion import (
            build_chronology_accordion_payload,
        )
        payload = build_chronology_accordion_payload(
            person_id=self.person_id,
            profile={"basics": {"dob": self.DOB}},
            questionnaire=None, promoted_rows=[],
            narrator_display_name="Bridge Test",
        )
        photos = None
        for dec in payload.get("decades", []):
            for yr in dec.get("years", []):
                for it in yr.get("items", []):
                    if it.get("event_kind") == "trip":
                        photos = it.get("photos")
        self.assertIsNotNone(photos)
        self.assertEqual(len(photos), 1)
        self.assertEqual(photos[0]["photo_id"], "ph-strip")
        self.assertEqual(photos[0]["caption"], "Rovinj harbor")
        self.assertEqual(photos[0]["stop_name"], "Rovinj")
        self.assertIn("2026-05-28", photos[0]["taken_at"])


    def _add_photo(self, pid, ready=1):
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "narrator_ready) VALUES (?, ?, ?, ?, ?)",
            (pid, self.person_id, "/tmp/" + pid + ".jpg", "h-" + pid, ready))
        con.commit()
        con.close()

    def test_projection_stats_in_timeline_meta(self):
        # WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01 — narrator-safe card fields.
        trip_id = self._trip()
        r = trip_repository.region_create(trip_id, "R1")
        stop = trip_repository.stop_create(trip_id, r, "Prague")
        self._add_photo("pn1", ready=1)   # narrator-ready
        self._add_photo("pn2", ready=1)   # narrator-ready
        self._add_photo("pu1", ready=0)   # NOT narrator-ready (must not count)
        l1 = trip_repository.photo_link_upsert(
            trip_id, "pn1", trip_region_id=r, trip_stop_id=stop,
            assignment_method="operator")
        trip_repository.photo_link_upsert(
            trip_id, "pn2", trip_region_id=r, trip_stop_id=stop,
            assignment_method="operator")
        trip_repository.photo_link_upsert(
            trip_id, "pu1", trip_region_id=r, trip_stop_id=stop,
            assignment_method="operator")
        trip_repository.photo_link_update(l1, include_in_memoir=True)
        # 3 notes, 1 promoted to memoir.
        trip_repository.location_note_create(
            trip_id, "note a", trip_region_id=r, include_in_memoir=True)
        trip_repository.location_note_create(trip_id, "note b", trip_region_id=r)
        trip_repository.location_note_create(trip_id, "note c", trip_stop_id=stop)

        trip_timeline_bridge.sync_trip_to_life_record(trip_id)
        ev = [e for e in _db.list_timeline_events(self.person_id)
              if e.get("kind") == "trip"][0]
        m = ev["meta"]
        # Only the 2 narrator-ready photos count; pu1 excluded.
        self.assertEqual(m.get("narrator_ready_photo_count"), 2)
        # Cover is a narrator-ready photo, never the unready one.
        self.assertIn(m.get("cover_photo_id"), ("pn1", "pn2"))
        self.assertNotEqual(m.get("cover_photo_id"), "pu1")
        # Notes: 3 total, 1 promoted.
        self.assertEqual(m.get("story_note_count"), 3)
        self.assertEqual(m.get("promoted_story_note_count"), 1)
        self.assertIn("memoir_photo_count", m)
        # No operator provenance leaked into the card meta.
        for banned in ("confidence", "assignment_method", "cluster_confidence",
                       "image_path", "storage_path"):
            self.assertNotIn(banned, m)


if __name__ == "__main__":
    unittest.main()
