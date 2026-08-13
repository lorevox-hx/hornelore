"""WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C1 — metadata trust.

Pure-module tests for classify_metadata_trust + parse_takeout_sidecar,
plus the clustering consumer (suspect_scan / none dates must NOT
contribute a time score — a scan date would confidently mis-cluster
decades-old prints onto yesterday's stop).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from services.photo_intake.metadata_trust import (  # noqa: E402
    TRUST_LEVELS,
    classify_metadata_trust,
    parse_takeout_sidecar,
)
from api.services import trip_photo_clustering  # noqa: E402


def _exif(captured_at=None, lat=None, lng=None, raw=None):
    gps = {"latitude": lat, "longitude": lng,
           "source": "exif_gps" if lat is not None else "unknown",
           "present_unparseable": False}
    return {
        "captured_at": captured_at,
        "captured_at_precision": "day" if captured_at else "unknown",
        "gps": gps,
        "orientation": None,
        "raw_exif": raw or {},
    }


class ClassifyTrustTest(unittest.TestCase):
    def test_pristine_phone_photo_is_full(self):
        out = classify_metadata_trust(_exif(
            "2026-05-28 16:30:00", 45.08, 13.63,
            raw={"Make": "Google", "Model": "Pixel 8",
                 "DateTimeOriginal": "2026:05:28 16:30:00"},
        ))
        self.assertEqual(out["trust"], "full")

    def test_stripped_share_is_none(self):
        # Email/messaging share: zero EXIF survives (Melanie iPhone class).
        out = classify_metadata_trust(_exif())
        self.assertEqual(out["trust"], "none")
        self.assertIn("no_exif_keys", out["reasons"])

    def test_scanner_software_is_suspect_scan(self):
        out = classify_metadata_trust(_exif(
            "2026-06-30 10:00:00",
            raw={"Software": "EPSON Scan 2", "DateTime": "2026:06:30 10:00:00"},
        ))
        self.assertEqual(out["trust"], "suspect_scan")
        self.assertTrue(any(r.startswith("scanner_software") for r in out["reasons"]))

    def test_datetime_without_camera_identity_is_suspect_scan(self):
        # P1 scanned film: datetime present, no Make/Model, no GPS.
        out = classify_metadata_trust(_exif(
            "2026-06-30 10:00:00",
            raw={"DateTime": "2026:06:30 10:00:00"},
        ))
        self.assertEqual(out["trust"], "suspect_scan")
        self.assertIn("datetime_without_camera_identity", out["reasons"])

    def test_digital_camera_no_gps_is_time_only(self):
        # P2 class: real camera identity, datetime, no GPS.
        out = classify_metadata_trust(_exif(
            "2009-07-14 12:00:00",
            raw={"Make": "Canon", "Model": "PowerShot SD1100",
                 "DateTimeOriginal": "2009:07:14 12:00:00"},
        ))
        self.assertEqual(out["trust"], "time_only")

    def test_gps_without_datetime_is_gps_only(self):
        out = classify_metadata_trust(_exif(None, 50.08, 14.42,
                                            raw={"GPSInfo": "present"}))
        self.assertEqual(out["trust"], "gps_only")

    def test_gps_clears_scan_suspicion(self):
        # GPS present → full even with no camera identity (a pipeline
        # that preserved GPS preserved the capture time with it).
        out = classify_metadata_trust(_exif(
            "2026-05-28 16:30:00", 45.08, 13.63, raw={"DateTime": "x"}))
        self.assertEqual(out["trust"], "full")

    def test_recent_date_on_old_trip_is_suspect_scan(self):
        # Trip context check: EXIF says last week, trip was 2019.
        out = classify_metadata_trust(
            _exif("2026-07-01 09:00:00",
                  raw={"Make": "Canon", "Model": "PowerShot",
                       "DateTime": "2026:07:01 09:00:00"}),
            upload_dt="2026-07-05 12:00:00",
            trip_start_date="2019-06-01",
        )
        self.assertEqual(out["trust"], "suspect_scan")
        self.assertIn("capture_date_near_upload_but_trip_is_old", out["reasons"])

    def test_old_date_on_old_trip_stays_time_only(self):
        # Same trip context but the date is plausibly the capture date.
        out = classify_metadata_trust(
            _exif("2019-06-05 09:00:00",
                  raw={"Make": "Canon", "Model": "PowerShot",
                       "DateTime": "2019:06:05 09:00:00"}),
            upload_dt="2026-07-05 12:00:00",
            trip_start_date="2019-06-01",
        )
        self.assertEqual(out["trust"], "time_only")

    def test_photo_manager_rewrite_noted_but_time_only(self):
        out = classify_metadata_trust(_exif(
            "2015-08-01 10:00:00",
            raw={"Make": "Apple", "Model": "iPhone 6",
                 "Software": "Picasa"},
        ))
        self.assertEqual(out["trust"], "time_only")
        self.assertTrue(any(r.startswith("photo_manager_rewrite")
                            for r in out["reasons"]))

    def test_never_raises_on_garbage(self):
        for bad in (None, {}, {"gps": None}, {"raw_exif": None},
                    {"captured_at": 123, "gps": {"latitude": "x"}}):
            out = classify_metadata_trust(bad)  # type: ignore[arg-type]
            self.assertIn(out["trust"], TRUST_LEVELS)


class TakeoutSidecarTest(unittest.TestCase):
    def test_full_sidecar_parses(self):
        text = json.dumps({
            "photoTakenTime": {"timestamp": "1748442600"},
            "geoData": {"latitude": 50.0875, "longitude": 14.4213},
        })
        out = parse_takeout_sidecar(text)
        self.assertEqual(out["captured_at"], "2025-05-28 14:30:00")
        self.assertAlmostEqual(out["latitude"], 50.0875)

    def test_zero_geo_is_absent(self):
        text = json.dumps({
            "photoTakenTime": {"timestamp": "1748442600"},
            "geoData": {"latitude": 0.0, "longitude": 0.0},
        })
        out = parse_takeout_sidecar(text)
        self.assertIsNone(out["latitude"])
        self.assertIsNotNone(out["captured_at"])

    def test_malformed_inputs_return_empty_shape(self):
        for bad in (None, "", "not json", "[1,2]", json.dumps({"photoTakenTime": {"timestamp": "abc"}})):
            out = parse_takeout_sidecar(bad)
            self.assertEqual(
                out, {"captured_at": None, "latitude": None, "longitude": None})


class ClusteringConsumesTrustTest(unittest.TestCase):
    STOP = {"id": "s1", "trip_region_id": "r1", "date_start": "2026-05-27",
            "date_end": "2026-05-30", "latitude": 50.0875, "longitude": 14.4213}

    def test_suspect_scan_date_gets_no_time_score(self):
        # In-window date but suspect_scan → treated as dateless: no GPS
        # either, so the photo must land in review, never confidently
        # on the stop via its scan date.
        photo = {"id": "p1", "date_value": "2026-05-28",
                 "metadata_trust": "suspect_scan"}
        out = trip_photo_clustering.cluster_photos_to_stops([photo], [self.STOP])
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0]["needs_review"])

    def test_trusted_date_still_scores(self):
        photo = {"id": "p2", "date_value": "2026-05-28",
                 "metadata_trust": "time_only"}
        out = trip_photo_clustering.cluster_photos_to_stops([photo], [self.STOP])
        self.assertEqual(out[0]["trip_stop_id"], "s1")
        self.assertFalse(out[0]["needs_review"])

    def test_missing_trust_fails_closed_and_lands_in_review(self):
        """REWRITTEN 2026-08-13. Was
        ``test_missing_trust_is_legacy_trusted``, asserting that a photo
        with no ``metadata_trust`` still clustered onto the stop by date
        -- 'Pre-0016 rows carry no trust, behavior must not change.'

        Commit `741243c` (WO-TRIP-LANE-AUDIT-FIXPACK-02, M3)
        deliberately reversed that. `_TRUSTED_DATE_LEVELS` is now an
        allowlist of `full` and `time_only`, and its comment names this
        exact case: an ABSENT metadata_trust key 'must fail CLOSED so a
        scan/unknown date can never confidently mis-cluster a
        decades-old print onto yesterday's stop.' The test was never
        updated, so it has been red ever since -- a stale assertion
        arguing with a dated safety ruling, which is worse than no test,
        because a permanently red suite stops being read.

        The ruling is kept and the test now asserts it. The cost is
        real and worth stating: a genuine pre-0016 row no longer
        clusters by its date and always lands in review. That is the
        safe direction -- review is recoverable, a scanned print filed
        onto the wrong day of the wrong trip is not.
        """
        photo = {"id": "p3", "date_value": "2026-05-28"}
        out = trip_photo_clustering.cluster_photos_to_stops([photo], [self.STOP])
        self.assertIsNone(out[0]["trip_stop_id"],
                          "an untrusted date was used for confident placement")
        self.assertTrue(out[0]["needs_review"])

    def test_the_allowlist_is_what_makes_that_true(self):
        """Non-vacuity: the same photo WITH trust does cluster, so the
        test above is about the trust value and not about the fixture
        being unplaceable for some other reason."""
        photo = {"id": "p3b", "date_value": "2026-05-28",
                 "metadata_trust": "full"}
        out = trip_photo_clustering.cluster_photos_to_stops([photo], [self.STOP])
        self.assertEqual(out[0]["trip_stop_id"], "s1")
        self.assertFalse(out[0]["needs_review"])

    def test_suspect_scan_with_gps_still_uses_gps(self):
        # Hypothetical: scan-suspect date but GPS present (edge) — GPS
        # signal remains usable, only the date is quarantined.
        photo = {"id": "p4", "date_value": "2026-05-28",
                 "latitude": 50.0876, "longitude": 14.4215,
                 "metadata_trust": "suspect_scan"}
        out = trip_photo_clustering.cluster_photos_to_stops([photo], [self.STOP])
        self.assertEqual(out[0]["trip_stop_id"], "s1")
        self.assertEqual(out[0]["assignment_method"], "exif_gps")


if __name__ == "__main__":
    unittest.main()
