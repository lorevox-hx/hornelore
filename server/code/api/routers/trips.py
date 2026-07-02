"""Trips router — WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 1+2 (2026-07-02).

Endpoints (ALL gated behind ``HORNELORE_TRIPS=1``, default OFF -> 404,
mirroring the operator_eval_harness posture):

    POST  /api/trips/import-itinerary   {person_id, itinerary}
    POST  /api/trips/import-csv         {person_id, title, csv_text, ...}
    GET   /api/trips?person_id=
    GET   /api/trips/{trip_id}/tree
    POST  /api/trips/{trip_id}/cluster-photos   {narrator_id?}
    GET   /api/trips/{trip_id}/photo-links?max_confidence=
    PATCH /api/trips/photo-links/{link_id}
    GET   /api/trips/{trip_id}/memoir-preview
    PATCH /api/trips/stops/{stop_id}          (operator date/GPS correction)
    DELETE /api/trips/{trip_id}
    GET   /api/trips/{trip_id}/export-docx    (Part I/II/III + photo appendix)

Operator-side surface. Nothing here reaches the narrator directly —
the interview lane consumes trips later via location notes (LOCKED
boundary: include_in_memoir=0 by default; operator context never
becomes narrator memory without promotion).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import trip_import, trip_photo_clustering, trip_repository

logger = logging.getLogger("code.api.routers.trips")

router = APIRouter(prefix="/api/trips", tags=["trips"])


# ── Gate ──────────────────────────────────────────────────────────────────

def _trips_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_TRIPS=1`."""
    return os.getenv("HORNELORE_TRIPS", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_trips_enabled() -> None:
    if not _trips_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# ── Request models ────────────────────────────────────────────────────────

class ImportItineraryRequest(BaseModel):
    person_id: str
    itinerary: Dict[str, Any]


class ImportCsvRequest(BaseModel):
    person_id: str
    title: str
    csv_text: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None


class ClusterPhotosRequest(BaseModel):
    narrator_id: Optional[str] = None  # defaults to the trip's person_id


class StopPatch(BaseModel):
    location_name: Optional[str] = None
    stop_type: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    thematic_tags: Optional[List[str]] = None
    clear_dates: bool = False


class PhotoLinkPatch(BaseModel):
    trip_stop_id: Optional[str] = None
    include_in_memoir: Optional[bool] = None
    caption: Optional[str] = None
    narrator_caption: Optional[str] = None
    confirm: bool = False


# ── Photo source read (photos table from the Photo Intake lane) ──────────

def _photos_for_narrator(narrator_id: str) -> List[Dict[str, Any]]:
    """Read the narrator's photos with whatever EXIF signal they carry.
    Excludes soft-deleted rows. Missing date AND GPS rows are still
    returned — the clusterer flags them for operator review instead of
    silently dropping them."""
    from .. import db as _db
    con = sqlite3.connect(str(_db.DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, date_value, latitude, longitude FROM photos "
            "WHERE narrator_id = ? AND deleted_at IS NULL",
            (narrator_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def _flat_stops(trip_id: str) -> List[Dict[str, Any]]:
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        return []
    out: List[Dict[str, Any]] = []

    def _walk(stop: Dict[str, Any]) -> None:
        out.append(stop)
        for child in stop.get("children", []):
            _walk(child)

    for region in tree.get("regions", []):
        for s in region.get("stops", []):
            _walk(s)
    return out


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/import-itinerary")
def import_itinerary(req: ImportItineraryRequest) -> Dict[str, Any]:
    _require_trips_enabled()
    try:
        trip_id = trip_import.import_itinerary(req.person_id, req.itinerary)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info(
        "[trips][import] itinerary imported trip=%s person=%s",
        trip_id, req.person_id,
    )
    return {"trip_id": trip_id, "tree": trip_repository.trip_tree(trip_id)}


@router.post("/import-csv")
def import_csv(req: ImportCsvRequest) -> Dict[str, Any]:
    _require_trips_enabled()
    try:
        trip_id = trip_import.import_csv(
            person_id=req.person_id,
            csv_text=req.csv_text,
            title=req.title,
            start_date=req.start_date,
            end_date=req.end_date,
            summary=req.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info(
        "[trips][import] csv imported trip=%s person=%s",
        trip_id, req.person_id,
    )
    return {"trip_id": trip_id, "tree": trip_repository.trip_tree(trip_id)}


@router.get("")
def list_trips(person_id: Optional[str] = None) -> Dict[str, Any]:
    _require_trips_enabled()
    return {"trips": trip_repository.trip_list(person_id)}


@router.get("/{trip_id}/tree")
def get_trip_tree(trip_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        raise HTTPException(status_code=404, detail="trip not found")
    return tree


@router.post("/{trip_id}/cluster-photos")
def cluster_photos(trip_id: str, req: ClusterPhotosRequest) -> Dict[str, Any]:
    _require_trips_enabled()
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    narrator_id = req.narrator_id or trip.get("person_id")
    photos = _photos_for_narrator(str(narrator_id))
    stops = _flat_stops(trip_id)
    assignments = trip_photo_clustering.cluster_photos_to_stops(photos, stops)
    written = 0
    skipped_operator = 0
    review = 0
    for a in assignments:
        if not a.get("photo_id"):
            continue
        link_id = trip_repository.photo_link_upsert(
            trip_id=trip_id,
            photo_id=str(a["photo_id"]),
            trip_region_id=a.get("trip_region_id"),
            trip_stop_id=a.get("trip_stop_id"),
            taken_at=a.get("taken_at"),
            latitude=a.get("latitude"),
            longitude=a.get("longitude"),
            assignment_method=str(a.get("assignment_method") or "exif_time"),
            cluster_confidence=a.get("confidence"),
        )
        if link_id:
            written += 1
        if a.get("needs_review"):
            review += 1
    logger.info(
        "[trips][cluster] trip=%s narrator=%s photos=%d written=%d "
        "needs_review=%d",
        trip_id, narrator_id, len(photos), written, review,
    )
    return {
        "trip_id": trip_id,
        "photos_considered": len(photos),
        "links_written": written,
        "needs_review": review,
        "review_threshold": trip_photo_clustering.REVIEW_THRESHOLD,
        "skipped_operator_confirmed": skipped_operator,
    }


@router.get("/{trip_id}/photo-links")
def list_photo_links(
    trip_id: str,
    max_confidence: Optional[float] = None,
) -> Dict[str, Any]:
    _require_trips_enabled()
    links = trip_repository.photo_links_list(trip_id, max_confidence)
    return {"trip_id": trip_id, "count": len(links), "photo_links": links}


@router.patch("/photo-links/{link_id}")
def patch_photo_link(link_id: str, req: PhotoLinkPatch) -> Dict[str, Any]:
    _require_trips_enabled()
    ok = trip_repository.photo_link_update(
        link_id,
        trip_stop_id=req.trip_stop_id,
        include_in_memoir=req.include_in_memoir,
        caption=req.caption,
        narrator_caption=req.narrator_caption,
        confirm=req.confirm,
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="link not found or nothing to update",
        )
    return {"ok": True, "link_id": link_id}


@router.get("/{trip_id}/memoir-preview")
def memoir_preview(trip_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    preview = trip_repository.trip_memoir_preview(trip_id)
    if not preview:
        raise HTTPException(status_code=404, detail="trip not found")
    return preview


@router.patch("/stops/{stop_id}")
def patch_stop(stop_id: str, req: StopPatch) -> Dict[str, Any]:
    """Operator correction surface — tightening a stop's dates/GPS is
    how clustering confidence improves on real photo sets. Re-run
    cluster-photos after corrections; operator-confirmed links are
    preserved."""
    _require_trips_enabled()
    ok = trip_repository.stop_update(
        stop_id,
        location_name=req.location_name,
        stop_type=req.stop_type,
        date_start=req.date_start,
        date_end=req.date_end,
        latitude=req.latitude,
        longitude=req.longitude,
        title=req.title,
        notes=req.notes,
        thematic_tags=req.thematic_tags,
        clear_dates=req.clear_dates,
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="stop not found or nothing to update",
        )
    return {"ok": True, "stop_id": stop_id}


@router.delete("/{trip_id}")
def delete_trip(trip_id: str) -> Dict[str, Any]:
    """Delete a trip and all rows under it (regions/stops/themes/photo
    links cascade). Photos themselves are never touched — the links
    are joins, not ownership."""
    _require_trips_enabled()
    ok = trip_repository.trip_delete(trip_id)
    if not ok:
        raise HTTPException(status_code=404, detail="trip not found")
    logger.info("[trips][delete] trip=%s", trip_id)
    return {"ok": True, "trip_id": trip_id}


@router.get("/{trip_id}/export-docx")
def export_docx(trip_id: str):
    """Standalone trip memoir DOCX — deterministic Part I/II/III render
    of the same canonical rows the preview shows, with the clustered
    photo appendix embedded (include_in_memoir=1 links only)."""
    _require_trips_enabled()
    preview = trip_repository.trip_memoir_preview(trip_id)
    if not preview:
        raise HTTPException(status_code=404, detail="trip not found")
    from ..services.trip_memoir_docx import build_trip_docx
    photo_rows = trip_repository.photo_links_with_photo_paths(
        trip_id, memoir_only=True,
    )
    try:
        docx_bytes = build_trip_docx(preview, photo_rows)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    import io
    from fastapi.responses import StreamingResponse
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_"
        for c in (preview.get("title") or "trip")
    )[:60].strip("_") or "trip"
    filename = f"lorevox_trip_memoir_{safe}.docx"
    logger.info(
        "[trips][docx] export trip=%s photos=%d", trip_id, len(photo_rows),
    )
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type=(
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
