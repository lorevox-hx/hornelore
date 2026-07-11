"""Unit tests for WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 2 — EXIF
spacetime clustering. Pure functions, no DB."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.trip_photo_clustering import (  # noqa: E402
    REVIEW_THRESHOLD,
    cluster_photos_to_stops,
    score_photo_against_stop,
)

# Spring 2026-shaped stops
PULA = {
    "id": "s-pula", "trip_region_id": "r-istria",
    "date_start": "2026-05-26", "date_end": "2026-05-30",
    "latitude": 44.8666, "longitude": 13.8496,
}
MIRANO = {
    "id": "s-mirano", "trip_region_id": "r-veneto",
    "date_start": "2026-05-30", "date_end": "2026-06-08",
    "latitude": 45.4950, "longitude": 12.1090,
}
PRAGUE = {
    "id": "s-prague", "trip_region_id": "r-czechia",
    "date_start": "2026-05-22", "date_end": "2026-05-24",
    "latitude": 50.0755, "longitude": 14.4378,
}
STOPS = [PRAGUE, PULA, MIRANO]


class ScoreTest(unittest.TestCase):
    def test_in_window_near_gps_high_confidence(self):
        photo = {
            "id": "p1", "taken_at": "2026-05-27 14:02:11",
            "latitude": 44.87, "longitude": 13.85,
            "metadata_trust": "full",
        }
        conf, method = score_photo_against_stop(photo, PULA)
        self.assertGreaterEqual(conf, 0.9)
        self.assertEqual(method, "exif_gps")

    def test_exif_native_datetime_format(self):
        photo = {
            "id": "p2", "taken_at": "2026:05:27 09:00:00",
            "latitude": 44.87, "longitude": 13.85,
            "metadata_trust": "full",
        }
        conf, _ = score_photo_against_stop(photo, PULA)
        self.assertGreaterEqual(conf, 0.9)

    def test_out_of_window_far_gps_low(self):
        photo = {
            "id": "p3", "taken_at": "2026-06-20 10:00:00",
            "latitude": 35.6, "longitude": 139.7,  # Tokyo
            "metadata_trust": "full",
        }
        conf, _ = score_photo_against_stop(photo, PULA)
        self.assertLess(conf, 0.3)

    def test_time_only_capped(self):
        photo = {"id": "p4", "taken_at": "2026-05-27 12:00:00",
                 "metadata_trust": "time_only"}
        conf, method = score_photo_against_stop(photo, PULA)
        self.assertEqual(method, "exif_time")
        self.assertLessEqual(conf, 0.8)
        self.assertGreaterEqual(conf, 0.79)

    def test_gps_only_capped(self):
        photo = {"id": "p5", "latitude": 44.867, "longitude": 13.85}
        conf, method = score_photo_against_stop(photo, PULA)
        self.assertEqual(method, "exif_gps")
        self.assertLessEqual(conf, 0.7)


class ClusterTest(unittest.TestCase):
    def test_photos_route_to_correct_stops(self):
        photos = [
            {"id": "prague-day", "taken_at": "2026-05-23 11:00:00",
             "latitude": 50.08, "longitude": 14.43,
             "metadata_trust": "full"},
            {"id": "pula-day", "taken_at": "2026-05-28 16:30:00",
             "latitude": 44.87, "longitude": 13.84,
             "metadata_trust": "full"},
            {"id": "mirano-day", "taken_at": "2026-06-02 09:15:00",
             "latitude": 45.49, "longitude": 12.11,
             "metadata_trust": "full"},
        ]
        out = cluster_photos_to_stops(photos, STOPS)
        assigned = {a["photo_id"]: a["trip_stop_id"] for a in out}
        self.assertEqual(assigned["prague-day"], "s-prague")
        self.assertEqual(assigned["pula-day"], "s-pula")
        self.assertEqual(assigned["mirano-day"], "s-mirano")
        for a in out:
            self.assertFalse(a["needs_review"], a)

    def test_date_value_fallback_key(self):
        # photos-table rows carry date_value, not taken_at
        photos = [{"id": "dv", "date_value": "2026-05-23",
                   "latitude": 50.08, "longitude": 14.43,
                   "metadata_trust": "full"}]
        out = cluster_photos_to_stops(photos, STOPS)
        self.assertEqual(out[0]["trip_stop_id"], "s-prague")

    def test_no_signal_photo_flagged_unassigned(self):
        photos = [{"id": "blank"}]
        out = cluster_photos_to_stops(photos, STOPS)
        self.assertIsNone(out[0]["trip_stop_id"])
        self.assertTrue(out[0]["needs_review"])
        self.assertEqual(out[0]["confidence"], 0.0)

    def test_ambiguous_photo_needs_review(self):
        # Weeks after the trip, no GPS — weak time decay only.
        photos = [{"id": "late", "taken_at": "2026-07-20 12:00:00",
                   "metadata_trust": "time_only"}]
        out = cluster_photos_to_stops(photos, STOPS)
        self.assertTrue(out[0]["needs_review"])
        self.assertLess(out[0]["confidence"], REVIEW_THRESHOLD)

    def test_empty_inputs(self):
        self.assertEqual(cluster_photos_to_stops([], STOPS), [])
        out = cluster_photos_to_stops(
            [{"id": "x", "taken_at": "2026-05-23",
              "metadata_trust": "time_only"}], [],
        )
        self.assertIsNone(out[0]["trip_stop_id"])
        self.assertTrue(out[0]["needs_review"])


if __name__ == "__main__":
    unittest.main()
