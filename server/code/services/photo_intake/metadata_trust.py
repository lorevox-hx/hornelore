"""Metadata-trust classification — WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C1.

Photos arrive with wildly different metadata trust depending on how they
were captured and how they traveled to this machine (three provenance
classes locked 2026-07-05):

  P1 scanned film     — EXIF datetime is the SCAN date (wrong decade),
                        no GPS, no camera identity. Everything real is
                        in the narrator's memory.
  P2 digital camera   — datetime present but suspect (clock drift,
                        timezone never set), GPS almost never.
  P3 modern phone     — rich EXIF+GPS at capture, but the EXPORT path
                        decides what survives: Google Takeout keeps it
                        (sometimes in sidecar JSON), email/messaging
                        shares strip it entirely.

Trust is a PER-FILE property detected here and recorded at intake —
never assumed from the upload surface. Consumers:
  - trip photo clustering: suspect_scan / none dates are EXCLUDED from
    the time score (a scan date would confidently mis-cluster).
  - intake UI: trust badge ("date looks like a scan date" etc.).
  - Lori photo elicitation (Phase C3): untrusted photos get the
    ungrounded warm open — never invented context.

Pure stdlib. No DB, no network, no PIL — operates on the dict shape
`extract_exif` already returns. LAW 3-style isolation by construction.

Trust levels (ordered roughly by usefulness to clustering):
  full         — parseable capture datetime AND GPS. Both signals usable.
  time_only    — datetime, no GPS, camera identity present. Time usable.
  gps_only     — GPS, no parseable datetime. GPS usable.
  suspect_scan — datetime present but it smells like a scanner / photo-
                 manager write, not a capture time. Time NOT usable.
  none         — no datetime, no GPS. Placement is manual + memory.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("code.services.photo_intake.metadata_trust")

TRUST_LEVELS = ("full", "time_only", "gps_only", "suspect_scan", "none")

# Software / Make strings that indicate the datetime was written by a
# scanner or a photo manager rather than a camera at capture time.
# Matched case-insensitively against EXIF Software + Make. Kept
# deliberately conservative — a phone photo lightly edited in an app
# still carries GPS, and GPS presence clears scan suspicion before
# these patterns are ever consulted (scanned prints have no GPS).
_SCANNER_SOFTWARE_RX = re.compile(
    r"(?:"
    r"epson\s*scan|vuescan|silverfast|canoscan|scangear|hp\s*scan|"
    r"scansnap|image\s*capture|naps2|xsane|brother\s*(?:iprint&?)?scan|"
    r"perfection\s*v\d|fastfoto"
    r")",
    re.IGNORECASE,
)
_PHOTO_MANAGER_RX = re.compile(
    r"(?:picasa|google\s*photos?|photoscape|photoshop\s*elements|"
    r"lightroom|shotwell|digikam)",
    re.IGNORECASE,
)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[: len("2026-01-01 00:00:00")]
                                     if fmt.endswith("%S") else s[:10], fmt)
        except ValueError:
            continue
    return None


def classify_metadata_trust(
    exif: Optional[Dict[str, Any]],
    *,
    upload_dt: Optional[str] = None,
    trip_start_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Classify how much the file's metadata can be trusted.

    ``exif``            — the dict `extract_exif` returns (or None).
    ``upload_dt``       — ISO datetime of the upload (defaults to now).
                          Used for the scan-date recency check.
    ``trip_start_date`` — optional trip context (stop-scoped upload /
                          cluster time). When the trip is >1 year old
                          but the EXIF datetime is within 30 days of
                          upload, the datetime is a scan/export date,
                          not a capture date.

    Returns {"trust": <level>, "reasons": [str, ...]}. Never raises.
    """
    reasons: list = []
    exif = exif or {}
    raw = exif.get("raw_exif") or {}
    gps = exif.get("gps") or {}

    captured_at = exif.get("captured_at")
    has_time = bool(captured_at)
    has_gps = gps.get("latitude") is not None and gps.get("longitude") is not None

    if not has_time and not has_gps:
        reasons.append("no_exif_keys" if not raw else "no_datetime_no_gps")
        return {"trust": "none", "reasons": reasons}

    if has_gps and not has_time:
        reasons.append("gps_without_datetime")
        return {"trust": "gps_only", "reasons": reasons}

    # From here: has_time is True.
    if has_gps:
        # GPS effectively clears scan suspicion — scanned prints don't
        # carry coordinates, and a capture pipeline that preserved GPS
        # almost certainly preserved the capture datetime with it.
        return {"trust": "full", "reasons": ["datetime_and_gps"]}

    # --- datetime present, no GPS: the suspect zone -------------------
    software = str(raw.get("Software") or "")
    make = str(raw.get("Make") or "")
    model = str(raw.get("Model") or "")

    if _SCANNER_SOFTWARE_RX.search(software) or _SCANNER_SOFTWARE_RX.search(make):
        reasons.append(f"scanner_software:{(software or make).strip()[:40]}")
        return {"trust": "suspect_scan", "reasons": reasons}

    if not make.strip() and not model.strip():
        # A real camera stamps Make/Model alongside the datetime; a
        # scanner or a stripping re-encode usually doesn't.
        reasons.append("datetime_without_camera_identity")
        return {"trust": "suspect_scan", "reasons": reasons}

    # Recency-vs-trip check (only meaningful with trip context): EXIF
    # says "last month" but the trip was years ago → scan/export date.
    if trip_start_date:
        cap = _parse_dt(captured_at)
        up = _parse_dt(upload_dt) or datetime.now(timezone.utc).replace(tzinfo=None)
        trip = _parse_dt(trip_start_date)
        if cap and trip and (up - trip).days > 365 and abs((up - cap).days) <= 30:
            reasons.append("capture_date_near_upload_but_trip_is_old")
            return {"trust": "suspect_scan", "reasons": reasons}

    if _PHOTO_MANAGER_RX.search(software):
        # Photo-manager rewrite: datetime often survives correctly but
        # was round-tripped. Downgrade note only — still time_only.
        reasons.append(f"photo_manager_rewrite:{software.strip()[:40]}")

    reasons.append("datetime_no_gps")
    return {"trust": "time_only", "reasons": reasons}


# ---------------------------------------------------------------------------
# Google Takeout sidecar JSON
# ---------------------------------------------------------------------------

def parse_takeout_sidecar(text: Optional[str]) -> Dict[str, Any]:
    """Best-effort parse of a Google Takeout supplemental-metadata JSON.

    Returns {"captured_at": "YYYY-MM-DD HH:MM:SS"|None,
             "latitude": float|None, "longitude": float|None}.
    Google writes geoData 0.0/0.0 when it has no location — treated as
    absent. Never raises; malformed input returns the empty shape.
    """
    out: Dict[str, Any] = {"captured_at": None, "latitude": None, "longitude": None}
    if not text:
        return out
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return out
        taken = data.get("photoTakenTime") or {}
        ts = taken.get("timestamp")
        if ts is not None:
            try:
                dt = datetime.fromtimestamp(int(str(ts)), tz=timezone.utc)
                out["captured_at"] = dt.strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OverflowError, OSError):
                pass
        geo = data.get("geoData") or {}
        lat, lng = geo.get("latitude"), geo.get("longitude")
        try:
            lat = float(lat) if lat is not None else None
            lng = float(lng) if lng is not None else None
        except (TypeError, ValueError):
            lat = lng = None
        # 0.0/0.0 is Google's "no location", not the Gulf of Guinea.
        if lat is not None and lng is not None and not (lat == 0.0 and lng == 0.0):
            out["latitude"], out["longitude"] = lat, lng
    except (json.JSONDecodeError, TypeError):
        log.info("[metadata-trust] sidecar JSON unparseable — ignored")
    return out


__all__ = ["classify_metadata_trust", "parse_takeout_sidecar", "TRUST_LEVELS"]
