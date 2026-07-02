"""Unit tests for WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 1 — trip schema,
itinerary/CSV import, tree read-back, photo links, memoir preview.

Offline: temp sqlite DB built from migration 0015, db.DB_PATH patched
per test (same pattern as tests/test_story_preservation.py).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import trip_import, trip_repository  # noqa: E402

_FIXTURE = _REPO_ROOT / "fixtures" / "trips" / "trip_2019_france_italy_fixture.json"


class _TempDbCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        self._tmp.close()
        self.db_path = Path(self._tmp.name)
        migration_sql = (
            _REPO_ROOT / "server" / "code" / "db" / "migrations"
            / "0015_trip_tables.sql"
        ).read_text(encoding="utf-8")
        con = sqlite3.connect(str(self.db_path))
        con.executescript(migration_sql)
        # Minimal photos table (migration 0001 subset) for clustering wiring.
        con.executescript(
            """CREATE TABLE IF NOT EXISTS photos (
                id TEXT PRIMARY KEY,
                narrator_id TEXT NOT NULL,
                image_path TEXT NOT NULL DEFAULT '',
                file_hash TEXT NOT NULL DEFAULT '',
                description TEXT,
                date_value TEXT,
                latitude REAL,
                longitude REAL,
                deleted_at TEXT
            );"""
        )
        con.commit()
        con.close()
        from api import db as _db
        self._db = _db
        self._original_db_path = _db.DB_PATH
        _db.DB_PATH = self.db_path

    def tearDown(self):
        self._db.DB_PATH = self._original_db_path
        try:
            self.db_path.unlink()
        except OSError:
            pass


class ItineraryImportTest(_TempDbCase):
    def _import_fixture(self) -> str:
        itinerary = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        return trip_import.import_itinerary("person-test-1", itinerary)

    def test_fixture_imports_full_tree(self):
        trip_id = self._import_fixture()
        tree = trip_repository.trip_tree(trip_id)
        self.assertIsNotNone(tree)
        self.assertEqual(
            tree["title"], "2019 France / Italy: Paris, Aix-en-Provence, Rome",
        )
        self.assertEqual(tree["start_date"], "2019-05-26")
        self.assertEqual(tree["end_date"], "2019-07-02")
        self.assertEqual(len(tree["regions"]), 3)
        titles = [r["title"] for r in tree["regions"]]
        self.assertEqual(
            titles, ["Paris base", "Aix-en-Provence base", "Rome close and return"],
        )
        paris = tree["regions"][0]
        self.assertEqual(paris["base_address"], "41 Rue de Reuilly, Paris")
        self.assertEqual(len(paris["stops"]), 7)
        total_stops = sum(len(r["stops"]) for r in tree["regions"])
        self.assertEqual(total_stops, 12)

    def test_region_ordering_preserved(self):
        trip_id = self._import_fixture()
        tree = trip_repository.trip_tree(trip_id)
        ords = [r["ord"] for r in tree["regions"]]
        self.assertEqual(ords, sorted(ords))

    def test_trip_list_by_person(self):
        self._import_fixture()
        trips = trip_repository.trip_list("person-test-1")
        self.assertEqual(len(trips), 1)
        self.assertEqual(trip_repository.trip_list("nobody"), [])

    def test_dict_stops_with_nesting_and_themes(self):
        itinerary = {
            "title": "Spring 2026 mini",
            "date_range": {"start": "2026-05-22", "end": "2026-06-13"},
            "regions": [{
                "title": "Italy — Veneto",
                "base_address": "Mirano",
                "stops": [{
                    "location_name": "Mirano",
                    "stop_type": "base",
                    "date_start": "2026-05-30",
                    "date_end": "2026-06-08",
                    "latitude": 45.495,
                    "longitude": 12.109,
                    "thematic_tags": ["venetian_villas"],
                    "day_trips": [
                        {"location_name": "Padua", "stop_type": "day_trip",
                         "thematic_tags": ["venetian_villas"]},
                        {"location_name": "Cittadella", "stop_type": "day_trip",
                         "thematic_tags": ["medieval_walled_towns"]},
                    ],
                }],
            }],
            "themes": [
                {"title": "Venetian villas", "tag": "venetian_villas"},
                {"title": "Medieval walled towns", "tag": "medieval_walled_towns"},
            ],
        }
        trip_id = trip_import.import_itinerary("person-test-2", itinerary)
        tree = trip_repository.trip_tree(trip_id)
        base = tree["regions"][0]["stops"][0]
        self.assertEqual(base["stop_type"], "base")
        self.assertEqual(len(base["children"]), 2)
        self.assertEqual(base["children"][0]["location_name"], "Padua")
        self.assertEqual(len(tree["themes"]), 2)

    def test_missing_title_rejected(self):
        with self.assertRaises(ValueError):
            trip_import.import_itinerary("p", {"regions": []})


class CsvImportTest(_TempDbCase):
    CSV = (
        "region,location,stop_type,date_start,date_end,lat,lng,parent,title,notes,themes\n"
        "Croatia (Istria),Pula,base,2026-05-26,2026-05-30,44.8666,13.8496,,,Base on the coast,roman_archaeology\n"
        "Croatia (Istria),Rovinj,day_trip,2026-05-28,,45.0812,13.6387,Pula,,,\n"
        "Italy,Mirano,base,2026-05-30,2026-06-08,45.495,12.109,,,,\n"
        "Italy,Venice,transit,2026-06-08,,45.4408,12.3155,Mirano,,Departure,travel_disruptions\n"
    )

    def test_csv_round_trip(self):
        trip_id = trip_import.import_csv(
            "person-csv", self.CSV, title="Spring 2026 CSV",
            start_date="2026-05-22", end_date="2026-06-13",
        )
        tree = trip_repository.trip_tree(trip_id)
        self.assertEqual(len(tree["regions"]), 2)
        istria = tree["regions"][0]
        self.assertEqual(istria["title"], "Croatia (Istria)")
        self.assertEqual(len(istria["stops"]), 1)  # Rovinj nests under Pula
        pula = istria["stops"][0]
        self.assertEqual(pula["location_name"], "Pula")
        self.assertEqual(pula["children"][0]["location_name"], "Rovinj")
        self.assertAlmostEqual(pula["latitude"], 44.8666, places=3)
        self.assertEqual(pula["thematic_tags_json"], ["roman_archaeology"])

    def test_csv_missing_columns_rejected(self):
        with self.assertRaises(ValueError):
            trip_import.import_csv("p", "a,b\n1,2\n", title="x")


class PhotoLinkTest(_TempDbCase):
    def _mini_trip(self) -> str:
        return trip_import.import_itinerary("person-photo", {
            "title": "Mini",
            "date_range": {"start": "2019-05-26", "end": "2019-06-15"},
            "regions": [{"title": "Paris", "stops": ["Louvre"]}],
        })

    def test_upsert_then_operator_confirm_wins(self):
        trip_id = self._mini_trip()
        link_id = trip_repository.photo_link_upsert(
            trip_id, "photo-1", assignment_method="exif_time",
            cluster_confidence=0.4,
        )
        # Operator confirms
        ok = trip_repository.photo_link_update(link_id, confirm=True)
        self.assertTrue(ok)
        # Re-clustering tries to overwrite — must be refused
        same_id = trip_repository.photo_link_upsert(
            trip_id, "photo-1", assignment_method="exif_gps",
            cluster_confidence=0.2,
        )
        self.assertEqual(same_id, link_id)
        links = trip_repository.photo_links_list(trip_id)
        self.assertEqual(links[0]["assignment_method"], "operator")
        self.assertEqual(links[0]["cluster_confidence"], 1.0)

    def test_review_queue_filter(self):
        trip_id = self._mini_trip()
        trip_repository.photo_link_upsert(
            trip_id, "p-low", cluster_confidence=0.3,
        )
        trip_repository.photo_link_upsert(
            trip_id, "p-high", cluster_confidence=0.9,
        )
        low = trip_repository.photo_links_list(trip_id, max_confidence=0.5)
        self.assertEqual([l["photo_id"] for l in low], ["p-low"])


class MemoirPreviewTest(_TempDbCase):
    def test_dual_axis_preview(self):
        itinerary = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        itinerary["themes"] = [
            {"title": "Paris museums", "tag": "paris_museums"},
        ]
        trip_id = trip_import.import_itinerary("person-m", itinerary)
        preview = trip_repository.trip_memoir_preview(trip_id)
        self.assertEqual(len(preview["part_one_journey_in_order"]), 3)
        self.assertEqual(
            preview["part_one_journey_in_order"][0]["region"], "Paris base",
        )
        self.assertEqual(len(preview["part_two_themes"]), 1)
        self.assertIn("part_three_photo_appendix", preview)

    def test_preview_missing_trip_none(self):
        self.assertIsNone(trip_repository.trip_memoir_preview("nope"))


class StopUpdateTest(_TempDbCase):
    def _trip_with_stop(self):
        trip_id = trip_import.import_itinerary("person-su", {
            "title": "Edit test",
            "date_range": {"start": "2026-05-22", "end": "2026-06-13"},
            "regions": [{"title": "R1", "stops": ["Prague"]}],
        })
        tree = trip_repository.trip_tree(trip_id)
        return trip_id, tree["regions"][0]["stops"][0]["id"]

    def test_date_and_gps_correction(self):
        trip_id, stop_id = self._trip_with_stop()
        ok = trip_repository.stop_update(
            stop_id, date_start="2026-05-23", date_end="2026-05-25",
            latitude=50.0755, longitude=14.4378,
        )
        self.assertTrue(ok)
        tree = trip_repository.trip_tree(trip_id)
        stop = tree["regions"][0]["stops"][0]
        self.assertEqual(stop["date_start"], "2026-05-23")
        self.assertAlmostEqual(stop["latitude"], 50.0755, places=3)

    def test_clear_dates(self):
        trip_id, stop_id = self._trip_with_stop()
        trip_repository.stop_update(stop_id, date_start="2026-05-23")
        trip_repository.stop_update(stop_id, clear_dates=True)
        tree = trip_repository.trip_tree(trip_id)
        self.assertIsNone(tree["regions"][0]["stops"][0]["date_start"])

    def test_no_fields_returns_false(self):
        _, stop_id = self._trip_with_stop()
        self.assertFalse(trip_repository.stop_update(stop_id))


class TripDeleteTest(_TempDbCase):
    def test_delete_cascades(self):
        trip_id = trip_import.import_itinerary("person-del", {
            "title": "Delete me",
            "date_range": {"start": "2026-05-22", "end": "2026-06-13"},
            "regions": [{"title": "R1", "stops": ["Prague", "Pula"]}],
            "themes": [{"title": "T", "tag": "t"}],
        })
        trip_repository.photo_link_upsert(trip_id, "photo-x")
        self.assertTrue(trip_repository.trip_delete(trip_id))
        self.assertIsNone(trip_repository.trip_get(trip_id))
        # cascade check: no orphan links
        self.assertEqual(trip_repository.photo_links_list(trip_id), [])
        # deleting again -> False
        self.assertFalse(trip_repository.trip_delete(trip_id))


class PhotoPathJoinTest(_TempDbCase):
    def _seed_photo(self, pid, path, desc=None):
        import sqlite3 as _s
        con = _s.connect(str(self.db_path))
        con.execute(
            "INSERT INTO photos (id, narrator_id, image_path, file_hash, "
            "date_value) VALUES (?, 'n1', ?, ?, '2026-05-23')",
            (pid, path, "hash-" + pid),
        )
        if desc:
            con.execute(
                "UPDATE photos SET image_path = image_path WHERE id = ?",
                (pid,),
            )
        con.commit()
        con.close()

    def test_join_and_memoir_filter(self):
        trip_id = trip_import.import_itinerary("person-pp", {
            "title": "Join test",
            "date_range": {"start": "2026-05-22", "end": "2026-06-13"},
            "regions": [{"title": "R1", "stops": ["Prague"]}],
        })
        self._seed_photo("ph-in", "/tmp/in.jpg")
        self._seed_photo("ph-out", "/tmp/out.jpg")
        link_in = trip_repository.photo_link_upsert(trip_id, "ph-in")
        link_out = trip_repository.photo_link_upsert(trip_id, "ph-out")
        trip_repository.photo_link_update(link_out, include_in_memoir=False)
        rows = trip_repository.photo_links_with_photo_paths(trip_id)
        self.assertEqual([r["photo_id"] for r in rows], ["ph-in"])
        self.assertEqual(rows[0]["photo_image_path"], "/tmp/in.jpg")
        all_rows = trip_repository.photo_links_with_photo_paths(
            trip_id, memoir_only=False,
        )
        self.assertEqual(len(all_rows), 2)


try:
    import docx as _docx_probe  # noqa: F401
    _HAS_DOCX = True
except Exception:
    _HAS_DOCX = False


@unittest.skipUnless(_HAS_DOCX, "python-docx not installed in this env")
class TripDocxTest(_TempDbCase):
    def test_docx_builds_from_fixture(self):
        from api.services.trip_memoir_docx import build_trip_docx
        itinerary = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        itinerary["themes"] = [{"title": "Paris museums", "tag": "pm"}]
        trip_id = trip_import.import_itinerary("person-dx", itinerary)
        preview = trip_repository.trip_memoir_preview(trip_id)
        blob = build_trip_docx(preview, photo_rows=[])
        self.assertGreater(len(blob), 5000)
        self.assertEqual(blob[:2], b"PK")  # docx = zip container


if __name__ == "__main__":
    unittest.main()
