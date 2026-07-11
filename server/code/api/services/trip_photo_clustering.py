"""EXIF spacetime photo clustering — assign photos to trip stops.

WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 2 (2026-07-02).

Pure functions: no DB, no network, no LLM. The caller (routers/trips.py)
reads ``photos`` rows (which already carry EXIF ``date_value`` +
``latitude``/``longitude`` from the Photo Intake lane) and trip stops,
and persists the returned assignments via trip_repository.

Scoring (locked in the WO spec):
- time score: photo timestamp inside the stop's [date_start, date_end]
  window = 1.0; within one day of the window = 0.7; else 1/(1+days_out).
  Stops without dates score 0.0 on time.
- GPS score by haversine distance to the stop's lat/lng:
  <2 km 1.0 / <10 km 0.8 / <50 km 0.5 / <200 km 0.2 / else 0.05.
- combined: both signals -> 0.6*time + 0.4*gps; time-only capped at
  0.8; GPS-only capped at 0.7.
- ``assignment_method`` = 'exif_gps' when GPS contributed, else
  'exif_time'.
- confidence < REVIEW_THRESHOLD (0.50) -> needs operator review.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

REVIEW_THRESHOLD = 0.50


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    v = str(value).strip().replace("Z", "")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S",  # EXIF native
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(v, fmt)
        except ValueError:
            continue
    return None


def _haversine_km(
    lat1: float, lon1: float, lat2: float, lon2: float,
) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _time_score(
    taken: Optional[datetime],
    start: Optional[datetime],
    end: Optional[datetime],
) -> Optional[float]:
    if taken is None:
        return None
    if start is None and end is None:
        return 0.0
    window_start = start or end
    window_end = (end or start) + timedelta(days=1)  # date-only end is inclusive
    if window_start <= taken < window_end:
        return 1.0
    if window_start - timedelta(days=1) <= taken < window_end + timedelta(days=1):
        return 0.7
    if taken < window_start:
        days_out = (window_start - taken).total_seconds() / 86400.0
    else:
        days_out = (taken - window_end).total_seconds() / 86400.0
    return 1.0 / (1.0 + max(0.0, days_out))


def _gps_score(
    photo_lat: Optional[float], photo_lng: Optional[float],
    stop_lat: Optional[float], stop_lng: Optional[float],
) -> Optional[float]:
    if photo_lat is None or photo_lng is None:
        return None
    if stop_lat is None or stop_lng is None:
        return None
    km = _haversine_km(photo_lat, photo_lng, stop_lat, stop_lng)
    if km < 2.0:
        return 1.0
    if km < 10.0:
        return 0.8
    if km < 50.0:
        return 0.5
    if km < 200.0:
        return 0.2
    return 0.05


_UNTRUSTED_DATE_LEVELS = frozenset({"suspect_scan", "none"})
# WO-TRIP-LANE-AUDIT-FIXPACK-02 (M3): only these two trust levels carry a
# capture datetime we can trust for time scoring. Everything else —
# suspect_scan/none (untrusted), gps_only (no datetime), 'unknown'
# (legacy / intake-off row, provenance unknown), or an ABSENT
# metadata_trust key (a caller that failed to project the column) — must
# fail CLOSED so a scan/unknown date can never confidently mis-cluster a
# decades-old print onto yesterday's stop.
_TRUSTED_DATE_LEVELS = frozenset({"full", "time_only"})


def _photo_taken_dt(photo: Dict[str, Any]) -> Optional[str]:
    """Photo datetime usable for time scoring — Phase C1 quarantine,
    hardened by FIXPACK-02 (M3) to fail closed on missing/unknown trust
    rather than only blocking the explicit suspect_scan/none denylist."""
    if str(photo.get("metadata_trust") or "") not in _TRUSTED_DATE_LEVELS:
        return None
    return photo.get("taken_at") or photo.get("date_value")


def score_photo_against_stop(
    photo: Dict[str, Any],
    stop: Dict[str, Any],
) -> Tuple[float, str]:
    """Return (confidence, assignment_method) for one photo x stop."""
    taken = _parse_dt(_photo_taken_dt(photo))
    t = _time_score(
        taken,
        _parse_dt(stop.get("date_start")),
        _parse_dt(stop.get("date_end")),
    )
    g = _gps_score(
        photo.get("latitude"), photo.get("longitude"),
        stop.get("latitude"), stop.get("longitude"),
    )
    if t is not None and g is not None:
        return (0.6 * t + 0.4 * g, "exif_gps")
    if t is not None:
        return (min(t, 1.0) * 0.8, "exif_time")
    if g is not None:
        return (min(g, 1.0) * 0.7, "exif_gps")
    return (0.0, "exif_time")


def cluster_photos_to_stops(
    photos: List[Dict[str, Any]],
    stops: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Assign each photo to its best-scoring stop.

    ``photos``: dicts with ``id`` + (``taken_at`` | ``date_value``) +
    optional ``latitude``/``longitude``.
    ``stops``: dicts with ``id``, ``trip_region_id``, optional dates +
    lat/lng.

    Returns one assignment dict per photo:
    ``{photo_id, trip_stop_id|None, trip_region_id|None, confidence,
    assignment_method, needs_review, taken_at, latitude, longitude}``.
    Photos with no usable signal (no timestamp AND no GPS) return
    ``trip_stop_id=None`` with confidence 0.0 (always review).
    """
    results: List[Dict[str, Any]] = []
    for photo in photos or []:
        best_stop: Optional[Dict[str, Any]] = None
        best_conf = -1.0
        best_method = "exif_time"
        for stop in stops or []:
            conf, method = score_photo_against_stop(photo, stop)
            if conf > best_conf:
                best_conf, best_method, best_stop = conf, method, stop
        has_signal = bool(
            _parse_dt(_photo_taken_dt(photo))
            or (photo.get("latitude") is not None
                and photo.get("longitude") is not None)
        )
        if best_stop is None or best_conf <= 0.0 or not has_signal:
            results.append({
                "photo_id": photo.get("id"),
                "trip_stop_id": None,
                "trip_region_id": None,
                "confidence": 0.0,
                "assignment_method": "exif_time",
                "needs_review": True,
                "taken_at": photo.get("taken_at") or photo.get("date_value"),
                "latitude": photo.get("latitude"),
                "longitude": photo.get("longitude"),
            })
            continue
        results.append({
            "photo_id": photo.get("id"),
            "trip_stop_id": best_stop.get("id"),
            "trip_region_id": best_stop.get("trip_region_id"),
            "confidence": round(best_conf, 3),
            "assignment_method": best_method,
            "needs_review": best_conf < REVIEW_THRESHOLD,
            "taken_at": photo.get("taken_at") or photo.get("date_value"),
            "latitude": photo.get("latitude"),
            "longitude": photo.get("longitude"),
        })
    return results
