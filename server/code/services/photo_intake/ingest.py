"""Shared photo-ingest core — WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C2.

One function that takes a file already streamed to a temp path and runs
the full intake pipeline: dedupe (sha256) → archive store → EXIF →
Takeout-sidecar fill → metadata-trust classification → photos row.

Extracted so the stop-scoped trip upload (routers/trips.py) and any
future upload surface share ONE pipeline. The original single/batch
endpoint in routers/photos.py predates this module and keeps its own
inline copy of the same steps — consolidating that surface onto this
function is a docs-noted cleanup, deliberately not done in the same
commit that adds a new caller (regression isolation).

Never narrator-facing. Callers own the temp-file cleanup.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .dedupe import sha256_file
from .exif import extract_exif
from .metadata_trust import classify_metadata_trust, parse_takeout_sidecar
from .storage import store_photo_file
from ..photos import repository as photo_repo

log = logging.getLogger("code.services.photo_intake.ingest")


def ingest_photo_file(
    *,
    narrator_id: str,
    tmp_path: str,
    original_filename: str,
    uploaded_by_user_id: str,
    narrator_ready: bool = False,
    description: Optional[str] = None,
    sidecar_json: Optional[str] = None,
    trip_start_date: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest one photo file. Returns::

        {
          "photo": <photos row dict>,
          "duplicate": bool,          # True → existing row returned, no write
          "metadata_trust": str,      # full|time_only|gps_only|suspect_scan|none
          "trust_reasons": [str],
          "exif_captured_at": str|None,
          "exif_latitude": float|None,
          "exif_longitude": float|None,
        }

    Raises on storage/DB failure — callers translate to HTTP.
    """
    file_hash = sha256_file(tmp_path)
    existing = photo_repo.find_photo_by_hash(narrator_id, file_hash)
    if existing is not None:
        meta = existing.get("metadata_json") or {}
        if not isinstance(meta, dict):
            meta = {}
        return {
            "photo": existing,
            "duplicate": True,
            "metadata_trust": (existing.get("metadata_trust")
                               or meta.get("metadata_trust") or "unknown"),
            "trust_reasons": meta.get("trust_reasons") or [],
            "exif_captured_at": existing.get("date_value"),
            "exif_latitude": existing.get("latitude"),
            "exif_longitude": existing.get("longitude"),
        }

    stored = store_photo_file(
        narrator_id=narrator_id,
        source_path=tmp_path,
        original_filename=original_filename,
    )

    exif = extract_exif(stored["image_path"])

    # Takeout sidecar fills only what the image's own EXIF lost.
    sidecar = parse_takeout_sidecar(sidecar_json) if sidecar_json else None
    if sidecar:
        if not exif.get("captured_at") and sidecar.get("captured_at"):
            exif = dict(exif)
            exif["captured_at"] = sidecar["captured_at"]
            exif["captured_at_precision"] = "exact"
        gps_now = exif.get("gps") or {}
        if gps_now.get("latitude") is None and sidecar.get("latitude") is not None:
            exif = dict(exif)
            exif["gps"] = {
                "latitude": sidecar["latitude"],
                "longitude": sidecar["longitude"],
                "source": "exif_gps",
                "present_unparseable": False,
            }

    trust = classify_metadata_trust(exif, trip_start_date=trip_start_date)
    gps = exif.get("gps") or {}
    suspect = trust.get("trust") == "suspect_scan"

    date_value = None if suspect else exif.get("captured_at")
    date_precision = (
        "unknown" if (suspect or not exif.get("captured_at"))
        else (exif.get("captured_at_precision") or "exact")
    )
    lat = gps.get("latitude")
    lng = gps.get("longitude")

    row = photo_repo.create_photo(
        photo_id=stored["photo_id"],
        narrator_id=narrator_id,
        uploaded_by_user_id=uploaded_by_user_id,
        file_hash=stored["file_hash"],
        image_path=stored["image_path"],
        thumbnail_path=stored.get("thumbnail_path"),
        description=description,
        date_value=date_value,
        date_precision=date_precision,
        location_label=None,
        location_source="exif_gps" if lat is not None else "unknown",
        latitude=lat,
        longitude=lng,
        narrator_ready=narrator_ready,
        needs_confirmation=lat is None,
        metadata={
            "exif": exif.get("raw_exif") or {},
            "exif_orientation": exif.get("orientation"),
            "exif_captured_at": exif.get("captured_at"),
            "exif_gps": gps,
            "metadata_trust": trust.get("trust"),
            "trust_reasons": trust.get("reasons") or [],
            "sidecar_used": bool(sidecar),
            **(extra_metadata or {}),
        },
    )
    try:
        photo_repo.set_metadata_trust(row["id"], trust.get("trust"))
    except Exception as exc:  # pre-0016 DB — metadata_json still has it
        log.info("[ingest] trust column write skipped: %s", exc)

    log.info(
        "[ingest] photo=%s narrator=%s trust=%s exif_date=%s gps=%s",
        row["id"], narrator_id, trust.get("trust"),
        exif.get("captured_at") or "none",
        "yes" if lat is not None else "no",
    )
    return {
        "photo": row,
        "duplicate": False,
        "metadata_trust": trust.get("trust"),
        "trust_reasons": trust.get("reasons") or [],
        "exif_captured_at": exif.get("captured_at"),
        "exif_latitude": lat,
        "exif_longitude": lng,
    }


__all__ = ["ingest_photo_file"]
