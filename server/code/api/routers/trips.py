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
    POST  /api/trips/stops/{stop_id}/photos   (Phase C2 — upload AT a stop)
    POST  /api/trips/{trip_id}/photos         (Travels shelf — trip-level drop)
    POST  /api/trips/{trip_id}/regions/{region_id}/photos (region-level drop)
    GET   /api/trips/{trip_id}/date-confirmations  (Phase 4 recognition offers)
    GET   /api/trips/{trip_id}/narrator-photo-links (narrator-ready only)
    DELETE /api/trips/{trip_id}
    GET   /api/trips/{trip_id}/export-docx    (Part I/II/III + photo appendix)
    GET   /api/trips/{trip_id}/travelogue-preview (evidence-rich outline)
    POST  /api/trips/{trip_id}/public-context  (web/public evidence, DRAFT)
    GET   /api/trips/{trip_id}/public-context
    PATCH /api/trips/public-context/{context_id}
    DELETE /api/trips/public-context/{context_id}
    POST  /api/trips/photo-links/{link_id}/reverse-geocode
    POST  /api/trips                          (create empty trip — Phase A builder)
    PATCH /api/trips/{trip_id}                (edit title/dates/summary)
    POST  /api/trips/{trip_id}/regions
    POST  /api/trips/{trip_id}/regions/{region_id}/stops
    POST  /api/trips/{trip_id}/themes
    PATCH /api/trips/regions/{region_id}
    DELETE /api/trips/regions/{region_id}     (stops cascade)
    DELETE /api/trips/stops/{stop_id}         (children re-parent to top level)
    DELETE /api/trips/themes/{theme_id}
    POST  /api/trips/{trip_id}/regions/reorder      {ordered_ids}
    POST  /api/trips/{trip_id}/stops/reorder        {region_id, parent?, ordered_ids}
    POST  /api/trips/{trip_id}/stops/{stop_id}/move {region_id, parent?, before?/after?}
    GET   /api/trips/{trip_id}/location-notes  [?region_id=&stop_id=] (story layer)
    POST  /api/trips/{trip_id}/location-notes  {note_text, scope, source_type, flags}
    PATCH /api/trips/location-notes/{note_id}
    DELETE /api/trips/location-notes/{note_id}
    GET   /api/trips/{trip_id}/sources  [?region_id=&stop_id=&day_id=]  (documents lane)
    POST  /api/trips/{trip_id}/sources         {source_type, pasted_text|link_url}
    POST  /api/trips/{trip_id}/sources/upload  (multipart file[s])
    PATCH /api/trips/sources/{source_id}
    DELETE /api/trips/sources/{source_id}
    GET   /api/trips/{trip_id}/days/reconcile-preview   (read-only date diff)
    POST  /api/trips/{trip_id}/days/reconcile  {add_missing, mark_out_of_range}

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
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from ..services import (
    trip_import,
    trip_photo_clustering,
    trip_repository,
    trip_timeline_bridge,
)

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


def _validate_stop_type(stop_type: Optional[str]) -> None:
    """WO-TRIP-LANE-AUDIT-FIXPACK-01 (H1): reject an off-enum
    stop_type at the API boundary with a clean 422 instead of
    letting the DB CHECK raise an unhandled 500."""
    if stop_type is not None and stop_type not in trip_repository.STOP_TYPES:
        raise HTTPException(
            status_code=422,
            detail="invalid stop_type %r; expected one of %s"
            % (stop_type, ", ".join(trip_repository.STOP_TYPES)),
        )


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


class TripCreate(BaseModel):
    person_id: str
    title: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None


class TripPatch(BaseModel):
    title: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None
    clear_start_date: bool = False
    clear_end_date: bool = False
    clear_summary: bool = False


class RegionCreate(BaseModel):
    title: str
    country_or_area: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None
    base_address: Optional[str] = None
    ord: Optional[int] = None


class RegionPatch(BaseModel):
    title: Optional[str] = None
    country_or_area: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    summary: Optional[str] = None
    base_address: Optional[str] = None
    ord: Optional[int] = None
    clear_country_or_area: bool = False
    clear_start_date: bool = False
    clear_end_date: bool = False
    clear_summary: bool = False
    clear_base_address: bool = False


class StopCreate(BaseModel):
    location_name: str
    stop_type: str = "sight"
    parent_trip_stop_id: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    thematic_tags: Optional[List[str]] = None
    ord: Optional[int] = None


class ThemeCreate(BaseModel):
    title: str
    tag: Optional[str] = None
    description: Optional[str] = None


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
    clear_start_date: bool = False
    clear_end_date: bool = False
    clear_notes: bool = False
    ord: Optional[int] = None
    parent_trip_stop_id: Optional[str] = None
    clear_parent: bool = False


class PhotoLinkPatch(BaseModel):
    trip_stop_id: Optional[str] = None
    include_in_memoir: Optional[bool] = None
    caption: Optional[str] = None
    narrator_caption: Optional[str] = None
    confirm: bool = False
    # WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Ph5 — approval-gated
    # photo context (defaults keep pre-Ph5 payloads byte-stable).
    caption_approved_for_lori: Optional[bool] = None
    operator_context_note: Optional[str] = None
    clear_operator_context_note: bool = False
    operator_context_approved_for_lori: Optional[bool] = None


class RegionsReorder(BaseModel):
    ordered_ids: List[str]


class StopsReorder(BaseModel):
    region_id: str
    parent_trip_stop_id: Optional[str] = None
    ordered_ids: List[str]


class StopMove(BaseModel):
    region_id: str
    parent_trip_stop_id: Optional[str] = None
    before_stop_id: Optional[str] = None
    after_stop_id: Optional[str] = None


class LocationNoteCreate(BaseModel):
    note_text: str
    note_title: Optional[str] = None
    trip_region_id: Optional[str] = None
    trip_stop_id: Optional[str] = None
    trip_day_id: Optional[str] = None
    source_type: str = "operator"
    source_ref: Optional[str] = None
    include_in_memoir: bool = False
    include_in_interview_context: bool = False
    target_language: str = "en"


class LocationNotePatch(BaseModel):
    note_title: Optional[str] = None
    note_text: Optional[str] = None
    source_type: Optional[str] = None
    source_ref: Optional[str] = None
    include_in_memoir: Optional[bool] = None
    include_in_interview_context: Optional[bool] = None
    ord: Optional[int] = None
    clear_title: bool = False


class SourceCreate(BaseModel):
    source_type: str = "other"
    title: Optional[str] = None
    trip_region_id: Optional[str] = None
    trip_stop_id: Optional[str] = None
    # WO-TRAVEL-DOC-UI-LAB-03: true day-scoped sources (migration 0029).
    # A day source needs NO stop/region — the day card is a scope of its
    # own; when stop/region are ALSO given they are validated as usual.
    trip_day_id: Optional[str] = None
    pasted_text: Optional[str] = None
    link_url: Optional[str] = None
    source_date: Optional[str] = None
    summary: Optional[str] = None
    include_in_memoir: bool = False


class SourcePatch(BaseModel):
    source_type: Optional[str] = None
    title: Optional[str] = None
    pasted_text: Optional[str] = None
    link_url: Optional[str] = None
    source_date: Optional[str] = None
    summary: Optional[str] = None
    include_in_memoir: Optional[bool] = None
    ord: Optional[int] = None
    # WO-TRAVEL-DOC-UI-LAB-03: attach/move to a day card; clear_day
    # detaches (NULLs trip_day_id ONLY — never deletes the source).
    trip_day_id: Optional[str] = None
    clear_day: bool = False


# ── Photo source read (photos table from the Photo Intake lane) ──────────

def _photos_for_narrator(narrator_id: str) -> List[Dict[str, Any]]:
    """Read the narrator's photos with whatever EXIF signal they carry.
    Excludes soft-deleted rows. Missing date AND GPS rows are still
    returned — the clusterer flags them for operator review instead of
    silently dropping them."""
    from .. import db as _db
    con = sqlite3.connect(str(_db.DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000;")  # BUG-DBLOCK hygiene
    try:
        try:
            rows = con.execute(
                "SELECT id, date_value, latitude, longitude, metadata_trust "
                "FROM photos WHERE narrator_id = ? AND deleted_at IS NULL",
                (narrator_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            # Pre-0016 DB — no trust column yet; clusterer treats
            # missing trust as trusted (legacy behavior).
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
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
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
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"trip_id": trip_id, "tree": trip_repository.trip_tree(trip_id)}


@router.get("")
def list_trips(person_id: Optional[str] = None) -> Dict[str, Any]:
    _require_trips_enabled()
    return {"trips": trip_repository.trip_list(person_id)}


@router.get("/capture-status")
def trip_capture_status() -> Dict[str, Any]:
    """WO-TRIP-LORI-ANSWER-CAPTURE-01 Phase 5 — operator visibility for the
    trip story-capture flag + last result. Read-only, no narrator content
    (only flag + skip/capture reason + scope + note id)."""
    _require_trips_enabled()
    from ..services import trip_story_capture as _tsc
    return _tsc.capture_status()


@router.get("/{trip_id}/tree")
def get_trip_tree(trip_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        raise HTTPException(status_code=404, detail="trip not found")
    return tree


async def _ingest_uploads_to_trip(
    trip: Dict[str, Any],
    stop: Optional[Dict[str, Any]],
    files: "List[UploadFile]",
    uploaded_by_user_id: str,
    narrator_ready: str,
    caption: str,
    sidecar_json: str,
    uploaded_from_surface: str = "",
    region_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Shared upload core for stop-scoped, region-scoped, AND trip-level
    photo drops.

    Phase C2 semantics (stop-scoped): operator-truth link; EXIF is a
    CROSS-CHECK, not an authority — GPS >200 km from the stop or a
    trusted datetime outside the trip window ±3 days flags a
    non-blocking mismatch (placement kept, method=operator, confidence
    0.45 → surfaces in the review queue).

    Travels-shelf semantics (WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01
    §3.6 REV 9): when uploaded_from_surface="travels_shelf" the photo
    metadata is stamped needs_operator_review=1 +
    review_reason="narrator_uploaded" so the narrator keeps flowing
    while the operator still gets a queue item.
    """
    import tempfile as _tempfile
    from pathlib import Path as _Path

    try:
        from ...services.photo_intake.ingest import ingest_photo_file
    except ImportError:
        # Offline test env roots sys.path at server/code (top-level
        # package is `api`, not `code`) — absolute import works there.
        from services.photo_intake.ingest import ingest_photo_file  # type: ignore
    from ..services.trip_photo_clustering import _haversine_km, _parse_dt

    person_id = str(trip.get("person_id") or "")
    ready_flag = str(narrator_ready).strip().lower() not in ("0", "false", "no", "")
    surface = (uploaded_from_surface or "").strip()
    extra_meta: Dict[str, Any] = {}
    if surface:
        extra_meta["uploaded_from_surface"] = surface
    if surface == "travels_shelf":
        extra_meta["needs_operator_review"] = 1
        extra_meta["review_reason"] = "narrator_uploaded"

    results: List[Dict[str, Any]] = []
    for up in files:
        tmp_fd, tmp_path = _tempfile.mkstemp(prefix="trip_photo_", suffix=".bin")
        try:
            with os.fdopen(tmp_fd, "wb") as out:
                while True:
                    chunk = await up.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
            ing = ingest_photo_file(
                narrator_id=person_id,
                tmp_path=tmp_path,
                original_filename=up.filename or "upload.bin",
                uploaded_by_user_id=uploaded_by_user_id,
                narrator_ready=ready_flag,
                sidecar_json=sidecar_json or None,
                trip_start_date=trip.get("start_date"),
                extra_metadata=extra_meta or None,
            )
        except Exception as exc:
            logger.warning("[trips][photo-upload] ingest failed file=%s: %s",
                           up.filename, exc)
            results.append({"filename": up.filename, "error": str(exc)})
            continue
        finally:
            try:
                if _Path(tmp_path).exists():
                    _Path(tmp_path).unlink()
            except OSError:
                pass

        photo = ing["photo"]

        # ---- EXIF cross-check (§3.2: cross-check, not authority) ----
        mismatch: Dict[str, Any] = {}
        exif_lat, exif_lng = ing.get("exif_latitude"), ing.get("exif_longitude")
        if (stop is not None
                and exif_lat is not None and exif_lng is not None
                and stop.get("latitude") is not None
                and stop.get("longitude") is not None):
            km = _haversine_km(exif_lat, exif_lng,
                               stop["latitude"], stop["longitude"])
            if km is not None and km > 200.0:
                mismatch["gps_km_from_stop"] = round(km, 1)
        if ing.get("metadata_trust") in ("full", "time_only"):
            cap = _parse_dt(ing.get("exif_captured_at"))
            t_start = _parse_dt(trip.get("start_date"))
            t_end = _parse_dt(trip.get("end_date")) or t_start
            if cap and t_start and t_end:
                pad = 3  # days
                if ((t_start - cap).days > pad) or ((cap - t_end).days > pad):
                    mismatch["date_outside_trip_window"] = str(
                        ing.get("exif_captured_at"))[:10]

        # ---- link ----------------------------------------------------
        # BUG-TRIP-LEVEL-UPLOAD-OPERATOR-CONFIRMS-UNPLACED-PHOTO-01
        # (review 2026-07-05): trip-level uploads (stop=None) must NOT
        # be stamped operator/confirmed — that made an UNPLACED photo
        # immune to later cluster-photos placement ("operator truth
        # wins" skip). Only a deliberate stop placement is operator
        # truth; a trip-level drop stays cluster-placeable.
        if stop is not None:
            _method = "operator"
            _confidence = 0.45 if mismatch else 1.0
            _confirm = not mismatch
        elif region_id:
            _method = "region_upload"  # dropped at region; cluster may refine
            _confidence = 0.3
            _confirm = False
        else:
            _method = "trip_upload"
            _confidence = 0.3  # review-queue range; re-cluster may place
            _confirm = False
        link_id = trip_repository.photo_link_upsert(
            trip_id=trip["id"],
            photo_id=photo["id"],
            trip_region_id=((stop or {}).get("trip_region_id")
                            if stop is not None else region_id),
            trip_stop_id=(stop or {}).get("id"),
            taken_at=ing.get("exif_captured_at"),
            latitude=exif_lat,
            longitude=exif_lng,
            assignment_method=_method,
            cluster_confidence=_confidence,
        )
        # Upsert preserves prior operator placements — force this one
        # only when a stop was explicitly chosen: fresh operator intent.
        if stop is not None or caption:
            trip_repository.photo_link_update(
                link_id,
                trip_stop_id=(stop or {}).get("id") if stop is not None else None,
                caption=(caption or None),
                confirm=_confirm,
            )
        logger.info(
            "[trips][photo-upload] photo=%s trip=%s stop=%s trust=%s dup=%s "
            "mismatch=%s surface=%s",
            photo["id"], trip["id"], (stop or {}).get("id") or "none",
            ing.get("metadata_trust"), ing.get("duplicate"),
            mismatch or "none", surface or "operator-tab",
        )
        results.append({
            "filename": up.filename,
            "photo_id": photo["id"],
            "link_id": link_id,
            "duplicate": bool(ing.get("duplicate")),
            "metadata_trust": ing.get("metadata_trust"),
            "trust_reasons": ing.get("trust_reasons") or [],
            "mismatch": mismatch or None,
        })

    return {
        "stop_id": (stop or {}).get("id"),
        "trip_id": trip["id"],
        "uploaded": sum(1 for r in results if r.get("photo_id") and not r.get("duplicate")),
        "duplicates": sum(1 for r in results if r.get("duplicate")),
        "mismatches": sum(1 for r in results if r.get("mismatch")),
        "errors": sum(1 for r in results if r.get("error")),
        "results": results,
    }


@router.post("/stops/{stop_id}/photos")
async def upload_photos_at_stop(
    stop_id: str,
    files: List[UploadFile] = File(...),
    uploaded_by_user_id: str = Form("operator"),
    narrator_ready: str = Form("true"),
    caption: str = Form(""),
    sidecar_json: str = Form(""),
    uploaded_from_surface: str = Form(""),
):
    """Phase C2 — upload photos directly AT a stop (Czechia → Prague 1).
    See _ingest_uploads_to_trip for semantics."""
    _require_trips_enabled()
    stop = trip_repository.stop_get(stop_id)
    if not stop:
        raise HTTPException(status_code=404, detail="stop not found")
    trip = trip_repository.trip_get(stop["trip_id"])
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    return await _ingest_uploads_to_trip(
        trip, stop, files, uploaded_by_user_id, narrator_ready,
        caption, sidecar_json, uploaded_from_surface,
    )


@router.post("/{trip_id}/regions/{region_id}/photos")
async def upload_photos_at_region(
    trip_id: str,
    region_id: str,
    files: List[UploadFile] = File(...),
    uploaded_by_user_id: str = Form("operator"),
    narrator_ready: str = Form("true"),
    caption: str = Form(""),
    sidecar_json: str = Form(""),
    uploaded_from_surface: str = Form(""),
):
    """Region-level photo drop (WO-TRAVEL-DOC-SOURCES/PHOTOS): links land
    with trip_region_id set + trip_stop_id NULL, method=trip_upload so a
    later cluster run can still place them onto a specific stop."""
    _require_trips_enabled()
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    if trip_repository.region_trip_id(region_id) != trip_id:
        raise HTTPException(status_code=404, detail="region not in this trip")
    out = await _ingest_uploads_to_trip(
        trip, None, files, uploaded_by_user_id, narrator_ready,
        caption, sidecar_json, uploaded_from_surface, region_id=region_id,
    )
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return out


@router.post("/{trip_id}/photos")
async def upload_photos_to_trip(
    trip_id: str,
    files: List[UploadFile] = File(...),
    uploaded_by_user_id: str = Form("operator"),
    narrator_ready: str = Form("true"),
    caption: str = Form(""),
    sidecar_json: str = Form(""),
    uploaded_from_surface: str = Form(""),
):
    """Travels-shelf Phase 1 — trip-level photo drop (no stop chosen).
    Links land with trip_stop_id NULL; the operator (or a later cluster
    run) places them. Date-window cross-check still applies; GPS check
    is skipped (no stop anchor)."""
    _require_trips_enabled()
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    return await _ingest_uploads_to_trip(
        trip, None, files, uploaded_by_user_id, narrator_ready,
        caption, sidecar_json, uploaded_from_surface,
    )


@router.post("/{trip_id}/cluster-photos")
def cluster_photos(trip_id: str, req: ClusterPhotosRequest) -> Dict[str, Any]:
    _require_trips_enabled()
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    # Review 2026-07-09 (BUG-TRIP-CLUSTER-FOREIGN-NARRATOR-01): a
    # request could pass ANY narrator_id and pull that narrator's photos
    # into THIS trip. The trip's owner is the only legal photo source.
    if req.narrator_id and str(req.narrator_id) != str(trip.get("person_id")):
        raise HTTPException(
            status_code=400,
            detail="narrator_id does not own this trip")
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


@router.get("/{trip_id}/narrator-photo-links")
def list_narrator_photo_links(trip_id: str) -> Dict[str, Any]:
    """Narrator-safe photo links for the Travels shelf strip —
    narrator_ready=1 + not deleted only (BUG-TRAVELS-PHOTO-STRIP-
    LEAKS-NON-NARRATOR-READY-PHOTOS-01). Operator surfaces keep the
    unfiltered /photo-links."""
    _require_trips_enabled()
    links = trip_repository.narrator_photo_links(trip_id)
    return {"trip_id": trip_id, "count": len(links), "photo_links": links}


@router.patch("/photo-links/{link_id}")
def patch_photo_link(link_id: str, req: PhotoLinkPatch) -> Dict[str, Any]:
    _require_trips_enabled()
    # BUG-TRIP-PHOTO-LINK-REGION-STOP-DESYNC-01 (review 2026-07-05):
    # moving a photo to a stop in ANOTHER region left the link with the
    # old trip_region_id. Resolve the target stop's region and update
    # both together; also 404 on a bogus stop id.
    region_id = None
    if req.trip_stop_id:
        _target = trip_repository.stop_get(req.trip_stop_id)
        if not _target:
            raise HTTPException(status_code=404, detail="stop not found")
        # BUG-TRIP-PHOTO-LINK-CROSS-TRIP-STOP-ASSIGNMENT-01 (review
        # 2026-07-05): the target stop must belong to the SAME trip as
        # the link — otherwise a bad request could point a Trip A link
        # at a Trip B stop/region.
        _link = trip_repository.photo_link_get(link_id)
        if not _link:
            raise HTTPException(status_code=404, detail="link not found")
        if _target.get("trip_id") != _link.get("trip_id"):
            raise HTTPException(status_code=400,
                                detail="stop belongs to another trip")
        region_id = _target.get("trip_region_id")
    ok = trip_repository.photo_link_update(
        link_id,
        trip_stop_id=req.trip_stop_id,
        include_in_memoir=req.include_in_memoir,
        caption=req.caption,
        narrator_caption=req.narrator_caption,
        confirm=req.confirm,
        trip_region_id=region_id,
        caption_approved_for_lori=req.caption_approved_for_lori,
        operator_context_note=req.operator_context_note,
        clear_operator_context_note=req.clear_operator_context_note,
        operator_context_approved_for_lori=req.operator_context_approved_for_lori,
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="link not found or nothing to update",
        )
    return {"ok": True, "link_id": link_id}


@router.get("/{trip_id}/date-confirmations")
def trip_date_confirmations(trip_id: str) -> Dict[str, Any]:
    """Phase 4 (WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01 §3.4) —
    recognition-over-recall material: for each stop with linked photos
    whose dates are TRUSTED (metadata_trust full/time_only ONLY —
    suspect scan dates must never become fake memories), return the
    stop name + representative photo date + count. The FE offers ONE
    of these as a confirmation ("Your pictures from Munich are from
    around May 22nd — does that sound right?") and never re-offers
    (shrug ledger client-side)."""
    _require_trips_enabled()
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    from .. import db as _db
    con = sqlite3.connect(str(_db.DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000;")
    try:
        try:
            rows = con.execute(
                """SELECT s.id AS stop_id,
                          s.location_name AS stop_name,
                          MIN(COALESCE(l.taken_at, p.date_value)) AS date,
                          COUNT(*) AS photo_count
                   FROM trip_photo_links l
                   JOIN photos p ON p.id = l.photo_id
                   JOIN trip_stops s ON s.id = l.trip_stop_id
                   WHERE l.trip_id = ?
                     AND p.metadata_trust IN ('full', 'time_only')
                     AND p.narrator_ready = 1
                     AND p.deleted_at IS NULL
                     AND COALESCE(l.taken_at, p.date_value) IS NOT NULL
                   GROUP BY s.id
                   ORDER BY date""",
                (trip_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []  # pre-0016 DB — no trust column, offer nothing
    finally:
        con.close()
    return {
        "trip_id": trip_id,
        "confirmations": [
            {"stop_id": r["stop_id"],
             "stop_name": r["stop_name"],
             "date": str(r["date"])[:10],
             "photo_count": r["photo_count"]}
            for r in rows if r["stop_name"]
        ],
    }


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
    # BUG-TRIP-STOP-PARENT-VALIDATION-01 (review 2026-07-05): reparent
    # must validate — parent exists, same trip, same region, not self,
    # and not a descendant of this stop (cycle protection).
    if req.parent_trip_stop_id:
        if req.parent_trip_stop_id == stop_id:
            raise HTTPException(status_code=400,
                                detail="a stop cannot be its own parent")
        _child = trip_repository.stop_get(stop_id)
        _parent = trip_repository.stop_get(req.parent_trip_stop_id)
        if not _child:
            raise HTTPException(status_code=404, detail="stop not found")
        if not _parent:
            raise HTTPException(status_code=404, detail="parent stop not found")
        if _parent.get("trip_id") != _child.get("trip_id"):
            raise HTTPException(status_code=400,
                                detail="parent stop belongs to another trip")
        if _parent.get("trip_region_id") != _child.get("trip_region_id"):
            raise HTTPException(status_code=400,
                                detail="parent stop belongs to another region")
        # Cycle walk: climb the parent chain from the proposed parent;
        # if we reach this stop, the reparent would create a loop.
        _cursor = _parent
        _hops = 0
        while _cursor and _cursor.get("parent_trip_stop_id") and _hops < 50:
            if _cursor["parent_trip_stop_id"] == stop_id:
                raise HTTPException(
                    status_code=400,
                    detail="reparent would create a cycle "
                           "(parent is a descendant of this stop)")
            _cursor = trip_repository.stop_get(_cursor["parent_trip_stop_id"])
            _hops += 1
    _validate_stop_type(req.stop_type)
    try:
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
            clear_start_date=req.clear_start_date,
            clear_end_date=req.clear_end_date,
            clear_notes=req.clear_notes,
            ord_=req.ord,
            parent_trip_stop_id=req.parent_trip_stop_id,
            clear_parent=req.clear_parent,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400,
                            detail="invalid stop update: %s" % exc)
    if not ok:
        raise HTTPException(
            status_code=404, detail="stop not found or nothing to update",
        )
    _tid = trip_repository.stop_trip_id(stop_id)
    if _tid:
        trip_timeline_bridge.sync_trip_to_life_record(_tid)
    return {"ok": True, "stop_id": stop_id}


@router.post("")
def create_trip(req: TripCreate) -> Dict[str, Any]:
    """Phase A builder: create an empty trip from a form (no more
    import-only creation)."""
    _require_trips_enabled()
    if not (req.title or "").strip():
        raise HTTPException(status_code=422, detail="trip needs a title")
    trip_id = trip_repository.trip_create(
        person_id=req.person_id,
        title=req.title.strip(),
        start_date=req.start_date,
        end_date=req.end_date,
        summary=req.summary,
        source_document="builder",
    )
    logger.info("[trips][builder] trip created trip=%s person=%s",
                trip_id, req.person_id)
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"trip_id": trip_id, "tree": trip_repository.trip_tree(trip_id)}


@router.patch("/{trip_id}")
def patch_trip(trip_id: str, req: TripPatch) -> Dict[str, Any]:
    """Operator edit of trip-level fields (title/dates/summary). Regions,
    stops, and photos are edited through their own endpoints."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    ok = trip_repository.trip_update(
        trip_id,
        title=req.title,
        start_date=req.start_date,
        end_date=req.end_date,
        summary=req.summary,
        clear_start_date=req.clear_start_date,
        clear_end_date=req.clear_end_date,
        clear_summary=req.clear_summary,
    )
    if not ok:
        raise HTTPException(
            status_code=400, detail="nothing to update")
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"ok": True, "trip_id": trip_id,
            "tree": trip_repository.trip_tree(trip_id)}


@router.post("/{trip_id}/regions")
def create_region(trip_id: str, req: RegionCreate) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    tree = trip_repository.trip_tree(trip_id)
    next_ord = req.ord if req.ord is not None else len(tree.get("regions", []))
    region_id = trip_repository.region_create(
        trip_id=trip_id,
        title=req.title,
        ord_=next_ord,
        country_or_area=req.country_or_area,
        start_date=req.start_date,
        end_date=req.end_date,
        summary=req.summary,
        base_address=req.base_address,
    )
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"region_id": region_id, "tree": trip_repository.trip_tree(trip_id)}


@router.post("/{trip_id}/regions/{region_id}/stops")
def create_stop(trip_id: str, region_id: str, req: StopCreate) -> Dict[str, Any]:
    _require_trips_enabled()
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        raise HTTPException(status_code=404, detail="trip not found")
    region = next((r for r in tree.get("regions", []) if r["id"] == region_id), None)
    if not region:
        raise HTTPException(status_code=404, detail="region not found in this trip")
    # BUG-TRIP-STOP-PARENT-VALIDATION-01 (review 2026-07-05): parent
    # must exist, belong to THIS trip and THIS region, and cannot be
    # the child itself. (Descendant-cycle check matters once reparent
    # UI exists — creation can't cycle since the child is new.)
    if req.parent_trip_stop_id:
        _parent = trip_repository.stop_get(req.parent_trip_stop_id)
        if not _parent:
            raise HTTPException(status_code=404, detail="parent stop not found")
        if _parent.get("trip_id") != trip_id:
            raise HTTPException(status_code=400,
                                detail="parent stop belongs to another trip")
        if _parent.get("trip_region_id") != region_id:
            raise HTTPException(status_code=400,
                                detail="parent stop belongs to another region")
    if req.ord is not None:
        next_ord = req.ord
    elif req.parent_trip_stop_id:
        # Child/day-trip: append within the parent's sibling group, NOT the
        # region's top-level count (which would collide on ord).
        next_ord = len(trip_repository.sibling_stop_ids(
            trip_id, region_id, req.parent_trip_stop_id))
    else:
        next_ord = len(region.get("stops", []))
    _validate_stop_type(req.stop_type)
    try:
        stop_id = trip_repository.stop_create(
            trip_id=trip_id,
            trip_region_id=region_id,
            location_name=req.location_name,
            stop_type=req.stop_type or "sight",
            ord_=next_ord,
            parent_trip_stop_id=req.parent_trip_stop_id,
            date_start=req.date_start,
            date_end=req.date_end,
            latitude=req.latitude,
            longitude=req.longitude,
            title=req.title,
            notes=req.notes,
            thematic_tags=req.thematic_tags,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400,
                            detail="invalid stop: %s" % exc)
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"stop_id": stop_id, "tree": trip_repository.trip_tree(trip_id)}


@router.post("/{trip_id}/themes")
def create_theme(trip_id: str, req: ThemeCreate) -> Dict[str, Any]:
    _require_trips_enabled()
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        raise HTTPException(status_code=404, detail="trip not found")
    import re as _re
    tag = (req.tag or "").strip() or _re.sub(
        r"[^a-z0-9]+", "_", req.title.lower(),
    ).strip("_") or "theme"
    theme_id = trip_repository.theme_create(
        trip_id=trip_id,
        title=req.title,
        tag=tag,
        ord_=len(tree.get("themes", [])),
        description=req.description,
    )
    return {"theme_id": theme_id, "tree": trip_repository.trip_tree(trip_id)}


@router.patch("/regions/{region_id}")
def patch_region(region_id: str, req: RegionPatch) -> Dict[str, Any]:
    _require_trips_enabled()
    _tid = trip_repository.region_trip_id(region_id)
    ok = trip_repository.region_update(
        region_id,
        title=req.title,
        country_or_area=req.country_or_area,
        start_date=req.start_date,
        end_date=req.end_date,
        summary=req.summary,
        base_address=req.base_address,
        ord_=req.ord,
        clear_country_or_area=req.clear_country_or_area,
        clear_start_date=req.clear_start_date,
        clear_end_date=req.clear_end_date,
        clear_summary=req.clear_summary,
        clear_base_address=req.clear_base_address,
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="region not found or nothing to update",
        )
    if _tid:
        trip_timeline_bridge.sync_trip_to_life_record(_tid)
    return {"ok": True, "region_id": region_id}


@router.delete("/regions/{region_id}")
def delete_region(region_id: str, force: bool = False) -> Dict[str, Any]:
    _require_trips_enabled()
    _tid = trip_repository.region_trip_id(region_id)
    # WO-TRIP-LANE-AUDIT-FIXPACK-02 (M1): refuse (409) when the region
    # still has stops unless the operator passes ?force=true, so a
    # region delete never silently destroys stop content.
    try:
        deleted = trip_repository.region_delete(region_id, force=force)
    except trip_repository.RegionNotEmptyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="region not found")
    if _tid:
        trip_timeline_bridge.sync_trip_to_life_record(_tid)
    return {"ok": True, "region_id": region_id}


@router.delete("/stops/{stop_id}")
def delete_stop(stop_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    stop = trip_repository.stop_get(stop_id)
    if not stop:
        raise HTTPException(status_code=404, detail="stop not found")
    _tid = stop.get("trip_id")
    _region = stop.get("trip_region_id")
    # Children of this stop get promoted to top level (FK SET NULL). Capture
    # them BEFORE the delete so we can renumber the region's top-level group
    # afterward and stop their old child ords from colliding.
    child_ids = trip_repository.stop_child_ids(stop_id)
    _parent = stop.get("parent_trip_stop_id") or None
    if not trip_repository.stop_delete(stop_id):
        raise HTTPException(status_code=404, detail="stop not found")
    if _tid and _region:
        # Renumber unconditionally (live-test finding 2026-07-07: deleting a
        # CHILDLESS stop left an ord gap — Salzburg:0, Graz:2 — because the
        # renumber only ran on child promotion). Close the gap in the group
        # the stop left; when children were promoted, the top-level group is
        # the one that changed, so renumber that too.
        if _parent:
            sib = trip_repository.sibling_stop_ids(_tid, _region, _parent)
            trip_repository.stops_reorder(_tid, _region, _parent, sib)
        if child_ids or not _parent:
            top_ids = trip_repository.sibling_stop_ids(_tid, _region, None)
            trip_repository.stops_reorder(_tid, _region, None, top_ids)
    if _tid:
        trip_timeline_bridge.sync_trip_to_life_record(_tid)
    return {"ok": True, "stop_id": stop_id}


@router.post("/{trip_id}/regions/reorder")
def reorder_regions(trip_id: str, req: RegionsReorder) -> Dict[str, Any]:
    """Set the operator's route order for a trip's regions. ``ordered_ids``
    must be exactly the trip's region ids (a full permutation) — this keeps
    ord a clean 0..n with no gaps or duplicates. Returns the updated tree."""
    _require_trips_enabled()
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        raise HTTPException(status_code=404, detail="trip not found")
    current = {r["id"] for r in tree.get("regions", [])}
    proposed = list(req.ordered_ids or [])
    if len(set(proposed)) != len(proposed):
        raise HTTPException(status_code=400,
                            detail="ordered_ids contains duplicates")
    if set(proposed) != current:
        raise HTTPException(
            status_code=400,
            detail="ordered_ids must be exactly this trip's region ids")
    updated = trip_repository.regions_reorder(trip_id, proposed)
    if updated != len(proposed):
        raise HTTPException(status_code=400,
                            detail="reorder touched an unexpected row count")
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"ok": True, "tree": trip_repository.trip_tree(trip_id)}


@router.post("/{trip_id}/stops/reorder")
def reorder_stops(trip_id: str, req: StopsReorder) -> Dict[str, Any]:
    """Reorder ONE sibling group of stops. Siblings = same trip + same
    region + same parent (parent_trip_stop_id null = top-level stops).
    ``ordered_ids`` must be exactly that group's current members. Returns
    the updated tree."""
    _require_trips_enabled()
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        raise HTTPException(status_code=404, detail="trip not found")
    region = next((r for r in tree.get("regions", [])
                   if r["id"] == req.region_id), None)
    if not region:
        raise HTTPException(status_code=404, detail="region not found in this trip")
    if req.parent_trip_stop_id:
        parent = trip_repository.stop_get(req.parent_trip_stop_id)
        if not parent:
            raise HTTPException(status_code=404, detail="parent stop not found")
        if parent.get("trip_id") != trip_id or \
                parent.get("trip_region_id") != req.region_id:
            raise HTTPException(status_code=400,
                                detail="parent stop is not in this region")
    current = set(trip_repository.sibling_stop_ids(
        trip_id, req.region_id, req.parent_trip_stop_id or None))
    proposed = list(req.ordered_ids or [])
    if len(set(proposed)) != len(proposed):
        raise HTTPException(status_code=400,
                            detail="ordered_ids contains duplicates")
    if set(proposed) != current:
        raise HTTPException(
            status_code=400,
            detail="ordered_ids must be exactly this sibling group's stops")
    updated = trip_repository.stops_reorder(
        trip_id, req.region_id, req.parent_trip_stop_id or None, proposed)
    if updated != len(proposed):
        raise HTTPException(status_code=400,
                            detail="reorder touched an unexpected row count")
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"ok": True, "tree": trip_repository.trip_tree(trip_id)}


@router.post("/{trip_id}/stops/{stop_id}/move")
def move_stop(trip_id: str, stop_id: str, req: StopMove) -> Dict[str, Any]:
    """Move a stop to a target region/parent and position it before or
    after a sibling (or append if neither resolves). Validates ownership,
    parent placement, and cycle protection, then renumbers the target
    sibling group atomically. Returns the updated tree."""
    _require_trips_enabled()
    stop = trip_repository.stop_get(stop_id)
    if not stop or stop.get("trip_id") != trip_id:
        raise HTTPException(status_code=404, detail="stop not found in this trip")
    if trip_repository.region_trip_id(req.region_id) != trip_id:
        raise HTTPException(status_code=404,
                            detail="target region not found in this trip")
    # Parent placement + cycle protection (mirrors patch_stop reparent).
    if req.parent_trip_stop_id:
        if req.parent_trip_stop_id == stop_id:
            raise HTTPException(status_code=400,
                                detail="a stop cannot be its own parent")
        parent = trip_repository.stop_get(req.parent_trip_stop_id)
        if not parent:
            raise HTTPException(status_code=404, detail="parent stop not found")
        if parent.get("trip_id") != trip_id:
            raise HTTPException(status_code=400,
                                detail="parent stop belongs to another trip")
        if parent.get("trip_region_id") != req.region_id:
            raise HTTPException(status_code=400,
                                detail="parent stop is not in the target region")
        cursor = parent
        hops = 0
        while cursor and cursor.get("parent_trip_stop_id") and hops < 50:
            if cursor["parent_trip_stop_id"] == stop_id:
                raise HTTPException(
                    status_code=400,
                    detail="move would create a cycle "
                           "(parent is a descendant of this stop)")
            cursor = trip_repository.stop_get(cursor["parent_trip_stop_id"])
            hops += 1
    # Positional sibling refs, if given, must live in the target group.
    for ref in (req.before_stop_id, req.after_stop_id):
        if not ref:
            continue
        ref_stop = trip_repository.stop_get(ref)
        if not ref_stop or ref_stop.get("trip_id") != trip_id or \
                ref_stop.get("trip_region_id") != req.region_id or \
                (ref_stop.get("parent_trip_stop_id") or None) != \
                (req.parent_trip_stop_id or None):
            raise HTTPException(
                status_code=400,
                detail="before/after stop is not in the target sibling group")
    ok = trip_repository.stop_move(
        trip_id=trip_id,
        stop_id=stop_id,
        region_id=req.region_id,
        parent_trip_stop_id=req.parent_trip_stop_id or None,
        before_stop_id=req.before_stop_id,
        after_stop_id=req.after_stop_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="stop not found")
    trip_timeline_bridge.sync_trip_to_life_record(trip_id)
    return {"ok": True, "tree": trip_repository.trip_tree(trip_id)}


@router.delete("/themes/{theme_id}")
def delete_theme(theme_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.theme_delete(theme_id):
        raise HTTPException(status_code=404, detail="theme not found")
    return {"ok": True, "theme_id": theme_id}


@router.delete("/{trip_id}")
def delete_trip(trip_id: str) -> Dict[str, Any]:
    """Delete a trip and all rows under it (regions/stops/themes/photo
    links cascade). Photos themselves are never touched — the links
    are joins, not ownership."""
    _require_trips_enabled()
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        raise HTTPException(status_code=404, detail="trip not found")
    # Phase B: remove the trip's timeline event BEFORE the row goes —
    # the life record must not keep a ghost of a deleted trip.
    trip_timeline_bridge.remove_trip_from_life_record(trip)
    ok = trip_repository.trip_delete(trip_id)
    if not ok:
        raise HTTPException(status_code=404, detail="trip not found")
    logger.info("[trips][delete] trip=%s", trip_id)
    return {"ok": True, "trip_id": trip_id}


_LOCATION_NOTE_SOURCE_TYPES = ("operator", "lori", "external", "draft")


@router.get("/{trip_id}/location-notes")
def list_location_notes(trip_id: str, region_id: Optional[str] = None,
                        stop_id: Optional[str] = None) -> Dict[str, Any]:
    """Story-layer notes for a trip, optionally scoped. stop_id -> that
    stop's notes; region_id (no stop) -> that region's own notes (stop is
    null); neither -> trip-level notes (both scopes null)."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    notes = trip_repository.location_notes_list(trip_id)
    if stop_id:
        notes = [n for n in notes if n.get("trip_stop_id") == stop_id]
    elif region_id:
        notes = [n for n in notes
                 if n.get("trip_region_id") == region_id and not n.get("trip_stop_id")]
    return {"notes": notes}


@router.post("/{trip_id}/location-notes")
def create_location_note(trip_id: str, req: LocationNoteCreate) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    if not (req.note_text or "").strip():
        raise HTTPException(status_code=422, detail="note needs text")
    if req.source_type not in _LOCATION_NOTE_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="invalid source_type")
    _validate_source_scope(trip_id, req.trip_region_id, req.trip_stop_id)
    if req.trip_day_id:
        _day = trip_repository.trip_day_get(req.trip_day_id)
        if not _day or _day.get("trip_id") != trip_id:
            raise HTTPException(status_code=400,
                                detail="day not in this trip")
    note_id = trip_repository.location_note_create(
        trip_id=trip_id,
        note_text=req.note_text,
        note_title=req.note_title,
        trip_region_id=req.trip_region_id,
        trip_stop_id=req.trip_stop_id,
        trip_day_id=req.trip_day_id,
        source_type=req.source_type,
        source_ref=req.source_ref,
        include_in_memoir=req.include_in_memoir,
        include_in_interview_context=req.include_in_interview_context,
        target_language=req.target_language or "en",
    )
    return {"note_id": note_id, "note": trip_repository.location_note_get(note_id)}


@router.patch("/location-notes/{note_id}")
def patch_location_note(note_id: str, req: LocationNotePatch) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.location_note_get(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    if req.source_type is not None and \
            req.source_type not in _LOCATION_NOTE_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="invalid source_type")
    ok = trip_repository.location_note_update(
        note_id,
        note_title=req.note_title,
        note_text=req.note_text,
        source_type=req.source_type,
        source_ref=req.source_ref,
        include_in_memoir=req.include_in_memoir,
        include_in_interview_context=req.include_in_interview_context,
        ord_=req.ord,
        clear_title=req.clear_title,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="nothing to update")
    return {"ok": True, "note": trip_repository.location_note_get(note_id)}


@router.delete("/location-notes/{note_id}")
def delete_location_note(note_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.location_note_delete(note_id):
        raise HTTPException(status_code=404, detail="note not found")
    return {"ok": True, "note_id": note_id}


_TRIP_SOURCE_TYPES = ("itinerary", "receipt", "hotel", "ticket",
                      "note", "map", "link", "other")


def _validate_source_scope(trip_id: str, region_id, stop_id) -> None:
    """Scope validation shared by notes + sources. If a stop is given the
    stop must belong to the trip AND (when a region is also given) to that
    region — no cross-region stop/region pairs."""
    if stop_id:
        stop = trip_repository.stop_get(stop_id)
        if not stop or stop.get("trip_id") != trip_id:
            raise HTTPException(status_code=400, detail="stop not in this trip")
        if region_id and stop.get("trip_region_id") != region_id:
            raise HTTPException(status_code=400,
                                detail="stop is not in that region")
    elif region_id and trip_repository.region_trip_id(region_id) != trip_id:
        raise HTTPException(status_code=400, detail="region not in this trip")


def _validate_source_day(trip_id: str, day_id) -> None:
    """WO-TRAVEL-DOC-UI-LAB-03 — a day-scoped source's day card must
    belong to the same trip (same posture as the day-scoped notes)."""
    if not day_id:
        return
    day = trip_repository.trip_day_get(day_id)
    if not day or day.get("trip_id") != trip_id:
        raise HTTPException(status_code=400, detail="day not in this trip")


@router.get("/{trip_id}/sources")
def list_sources(trip_id: str, region_id: Optional[str] = None,
                 stop_id: Optional[str] = None,
                 day_id: Optional[str] = None) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    rows = trip_repository.sources_list(trip_id, day_id=day_id)
    if stop_id:
        rows = [s for s in rows if s.get("trip_stop_id") == stop_id]
    elif region_id:
        rows = [s for s in rows
                if s.get("trip_region_id") == region_id and not s.get("trip_stop_id")]
    return {"sources": rows}


@router.post("/{trip_id}/sources")
def create_source(trip_id: str, req: SourceCreate) -> Dict[str, Any]:
    """Create a non-file source (pasted text / link / metadata note)."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    if req.source_type not in _TRIP_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="invalid source_type")
    if not (req.pasted_text or req.link_url or req.title or req.summary):
        raise HTTPException(status_code=422,
                            detail="source needs text, a link, or a title")
    _validate_source_scope(trip_id, req.trip_region_id, req.trip_stop_id)
    _validate_source_day(trip_id, getattr(req, "trip_day_id", None))
    sid = trip_repository.source_create(
        trip_id=trip_id,
        source_type=req.source_type,
        title=req.title,
        trip_region_id=req.trip_region_id,
        trip_stop_id=req.trip_stop_id,
        trip_day_id=getattr(req, "trip_day_id", None),
        pasted_text=req.pasted_text,
        link_url=req.link_url,
        source_date=req.source_date,
        summary=req.summary,
        include_in_memoir=req.include_in_memoir,
    )
    return {"source_id": sid, "source": trip_repository.source_get(sid)}


@router.post("/{trip_id}/sources/upload")
async def upload_source(
    trip_id: str,
    files: List[UploadFile] = File(...),
    source_type: str = Form("other"),
    trip_region_id: str = Form(""),
    trip_stop_id: str = Form(""),
    trip_day_id: str = Form(""),
    title: str = Form(""),
):
    """Upload one or more source documents (PDF, ticket, receipt, ...).
    Stored under DATA_DIR/trip_sources/<id>/ — NOT the photo pipeline."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    st_type = source_type if source_type in _TRIP_SOURCE_TYPES else "other"
    region = trip_region_id or None
    stop = trip_stop_id or None
    day = trip_day_id or None
    _validate_source_scope(trip_id, region, stop)
    _validate_source_day(trip_id, day)
    data_dir = os.getenv("DATA_DIR", "data")
    created: List[str] = []
    for f in files:
        sid = str(uuid.uuid4())
        safe = os.path.basename((getattr(f, "filename", None) or "file"))
        dest_dir = os.path.join(data_dir, "trip_sources", sid)
        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, safe)
        data = await f.read()
        with open(path, "wb") as out:
            out.write(data)
        trip_repository.source_create(
            trip_id=trip_id, source_type=st_type, title=title or safe,
            trip_region_id=region, trip_stop_id=stop, trip_day_id=day,
            filename=safe,
            mime_type=getattr(f, "content_type", None), storage_path=path,
            source_id=sid,
        )
        created.append(sid)
    return {"source_ids": created,
            "sources": trip_repository.sources_list(trip_id)}


@router.patch("/sources/{source_id}")
def patch_source(source_id: str, req: SourcePatch) -> Dict[str, Any]:
    _require_trips_enabled()
    src_row = trip_repository.source_get(source_id)
    if not src_row:
        raise HTTPException(status_code=404, detail="source not found")
    if req.source_type is not None and req.source_type not in _TRIP_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="invalid source_type")
    req_day = getattr(req, "trip_day_id", None)
    if req_day:
        _validate_source_day(src_row["trip_id"], req_day)
    ok = trip_repository.source_update(
        source_id,
        source_type=req.source_type,
        title=req.title,
        pasted_text=req.pasted_text,
        link_url=req.link_url,
        source_date=req.source_date,
        summary=req.summary,
        include_in_memoir=req.include_in_memoir,
        ord_=req.ord,
        trip_day_id=req_day,
        clear_day=bool(getattr(req, "clear_day", False)),
    )
    if not ok:
        raise HTTPException(status_code=400, detail="nothing to update")
    return {"ok": True, "source": trip_repository.source_get(source_id)}


@router.delete("/sources/{source_id}")
def delete_source(source_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    src_row = trip_repository.source_get(source_id)
    if not src_row:
        raise HTTPException(status_code=404, detail="source not found")
    if not trip_repository.source_delete(source_id):
        raise HTTPException(status_code=404, detail="source not found")
    # Best-effort: remove the stored file (row is the authority; a leftover
    # blob is harmless but we clean up).
    sp = src_row.get("storage_path")
    if sp:
        try:
            os.remove(sp)
        except OSError:
            pass
    return {"ok": True, "source_id": source_id}


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


# ── Public context + travelogue (WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01) ─
#
# Travel Doc mode is EVIDENCE-RICH (locked doctrine 2026-07-10): the
# local stack MAY use web/public context (holidays, site background,
# food context, reverse-geocoded broad places). Boundary: private
# memoir archives never leave the local stack; public context is
# labeled public/draft until the operator confirms it, and is never
# presented as personal memory. approved_for_lori / include_in_memoir
# default OFF — nothing is approved by silence.

_PUBLIC_CONTEXT_SOURCE_TYPES = (
    "public_web_context", "reverse_geocode", "calendar_context",
    "food_context", "place_context",
)


class PublicContextCreate(BaseModel):
    result_summary: str
    source_type: str = "public_web_context"
    trip_region_id: Optional[str] = None
    trip_stop_id: Optional[str] = None
    photo_link_id: Optional[str] = None
    query: Optional[str] = None
    source_url: Optional[str] = None
    confidence: str = "draft"
    notes: Optional[str] = None


class PublicContextPatch(BaseModel):
    result_summary: Optional[str] = None
    notes: Optional[str] = None
    source_url: Optional[str] = None
    query: Optional[str] = None
    approved_for_lori: Optional[bool] = None
    include_in_memoir: Optional[bool] = None


# WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1/2 request models.
class PhotoContextPatch(BaseModel):
    result_summary: Optional[str] = None
    raw_text: Optional[str] = None
    approved_for_lori: Optional[bool] = None
    include_in_memoir: Optional[bool] = None
    rejected: Optional[bool] = None


# WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11).
# Operator-entry payload for the two manual draft lanes: local-LLM /
# operator-typed draft observation, and place-from-context inference
# rooted in already-reviewable evidence (never raw GPS).
class DraftObservationCreate(BaseModel):
    result_summary: str
    raw_text: Optional[str] = None
    engine: Optional[str] = None   # e.g. "operator_local" | "local_llm"
    model_name: Optional[str] = None


class PlaceFromContextCreate(BaseModel):
    result_summary: str
    notes: Optional[str] = None
    # Where the operator sourced the inference (any subset of:
    # ocr, public_context, operator_place_label, trip_labels,
    # broad_place_notes). Recorded in notes for provenance; never
    # accepts raw GPS or narrator/memoir text.
    evidence_sources: Optional[List[str]] = None


class PublicLookupRequest(BaseModel):
    query: Optional[str] = None
    url: Optional[str] = None
    source_type: str = "place_context"
    trip_region_id: Optional[str] = None
    trip_stop_id: Optional[str] = None
    trip_day_id: Optional[str] = None
    photo_link_id: Optional[str] = None
    reason: Optional[str] = None


def _validate_photo_link_scope(trip_id: str, photo_link_id) -> None:
    """A photo-scoped public-context row must point at a link in THIS
    trip (same posture as the cross-trip stop checks)."""
    if not photo_link_id:
        return
    link = trip_repository.photo_link_get(photo_link_id)
    if not link:
        raise HTTPException(status_code=404, detail="photo link not found")
    if link.get("trip_id") != trip_id:
        raise HTTPException(status_code=400,
                            detail="photo link belongs to another trip")


@router.post("/{trip_id}/public-context")
def create_public_context(trip_id: str, req: PublicContextCreate) -> Dict[str, Any]:
    """Store one public/web lookup result as DRAFT evidence. The operator
    (or a local tool) enters it; nothing is approved by silence."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    if not (req.result_summary or "").strip():
        raise HTTPException(status_code=422,
                            detail="public context needs a result_summary")
    if req.source_type not in _PUBLIC_CONTEXT_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="invalid source_type")
    _validate_source_scope(trip_id, req.trip_region_id, req.trip_stop_id)
    _validate_photo_link_scope(trip_id, req.photo_link_id)
    cid = trip_repository.public_context_create(
        trip_id=trip_id,
        result_summary=req.result_summary.strip(),
        source_type=req.source_type,
        trip_region_id=req.trip_region_id,
        trip_stop_id=req.trip_stop_id,
        photo_link_id=req.photo_link_id,
        query=req.query,
        source_url=req.source_url,
        confidence=req.confidence or "draft",
        notes=req.notes,
    )
    logger.info("[trips][public-context] created ctx=%s trip=%s type=%s",
                cid, trip_id, req.source_type)
    return {"context_id": cid,
            "context": trip_repository.public_context_get(cid)}


@router.get("/{trip_id}/public-context")
def list_public_context(
    trip_id: str,
    region_id: Optional[str] = None,
    stop_id: Optional[str] = None,
    photo_link_id: Optional[str] = None,
) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    rows = trip_repository.public_context_list(trip_id)
    if photo_link_id:
        rows = [r for r in rows if r.get("photo_link_id") == photo_link_id]
    elif stop_id:
        rows = [r for r in rows if r.get("trip_stop_id") == stop_id]
    elif region_id:
        rows = [r for r in rows
                if r.get("trip_region_id") == region_id
                and not r.get("trip_stop_id")]
    return {"trip_id": trip_id, "count": len(rows), "public_context": rows}


@router.patch("/public-context/{context_id}")
def patch_public_context(context_id: str, req: PublicContextPatch) -> Dict[str, Any]:
    """Approve / edit / include a public-context row. Editing the
    result_summary revokes approval unless the same request re-approves
    (approval refers to the text the operator reviewed)."""
    _require_trips_enabled()
    if not trip_repository.public_context_get(context_id):
        raise HTTPException(status_code=404, detail="public context not found")
    ok = trip_repository.public_context_update(
        context_id,
        result_summary=req.result_summary,
        notes=req.notes,
        source_url=req.source_url,
        query=req.query,
        approved_for_lori=req.approved_for_lori,
        include_in_memoir=req.include_in_memoir,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="nothing to update")
    return {"ok": True,
            "context": trip_repository.public_context_get(context_id)}


@router.delete("/public-context/{context_id}")
def delete_public_context(context_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.public_context_delete(context_id):
        raise HTTPException(status_code=404, detail="public context not found")
    return {"ok": True, "context_id": context_id}


@router.get("/{trip_id}/travelogue-preview")
def travelogue_preview(trip_id: str) -> Dict[str, Any]:
    """Evidence-rich travelogue outline — structured blocks + labeled
    evidence anchors + per-block llm_prompt. NO prose generation here;
    read-only walk of canonical rows (see travelogue_builder)."""
    _require_trips_enabled()
    from ..services import travelogue_builder
    outline = travelogue_builder.build_travelogue_outline(trip_id)
    if not outline:
        raise HTTPException(status_code=404, detail="trip not found")
    return outline


def _resolve_reverse_geocode(lat: float, lng: float) -> Optional[str]:
    """Pluggable LOCAL reverse-geocode resolver. Default: no provider →
    None (the endpoint reports that honestly; nothing is stored, nothing
    is faked). When HORNELORE_GEOCODE_CMD is set it is treated as a
    shell command template — `{lat}`/`{lng}` placeholders are
    substituted (or the coordinates are appended as two arguments) and
    stdout is used as the broad place label. This is an operator-side
    local tool hook, never a cloud LLM."""
    cmd = os.getenv("HORNELORE_GEOCODE_CMD", "").strip()
    if not cmd:
        return None
    import subprocess
    if "{lat}" in cmd or "{lng}" in cmd:
        full = cmd.replace("{lat}", str(lat)).replace("{lng}", str(lng))
    else:
        full = "%s %s %s" % (cmd, lat, lng)
    try:
        out = subprocess.run(full, shell=True, capture_output=True,
                             text=True, timeout=20)
        label = (out.stdout or "").strip()
        return label or None
    except Exception as exc:
        logger.warning("[trips][reverse-geocode] resolver failed: %s", exc)
        return None


@router.post("/photo-links/{link_id}/reverse-geocode")
def reverse_geocode_photo_link(link_id: str) -> Dict[str, Any]:
    """Resolve a linked photo's private GPS into a broad place label and
    store it as DRAFT public context (source_type='reverse_geocode').
    Raw coordinates stay server-side — only the label is stored, and
    never returned when no provider is configured. Honest posture: no
    provider = clear message, never fake results."""
    _require_trips_enabled()
    link = trip_repository.photo_link_get(link_id)
    if not link:
        raise HTTPException(status_code=404, detail="link not found")
    lat, lng = trip_repository.photo_raw_gps(str(link.get("photo_id") or ""))
    if lat is None or lng is None:
        lat, lng = link.get("latitude"), link.get("longitude")
    if lat is None or lng is None:
        return {"status": "no_gps",
                "message": "this photo has no GPS coordinates recorded"}
    label = _resolve_reverse_geocode(float(lat), float(lng))
    if label is None:
        return {"status": "no_provider",
                "message": "place-name extraction hasn't run — no geocode "
                           "provider configured (set HORNELORE_GEOCODE_CMD "
                           "to a local resolver command)"}
    cid = trip_repository.public_context_create(
        trip_id=link["trip_id"],
        result_summary=label,
        source_type="reverse_geocode",
        trip_region_id=link.get("trip_region_id"),
        trip_stop_id=link.get("trip_stop_id"),
        photo_link_id=link_id,
        query="reverse_geocode:photo_link:%s" % link_id,
        confidence="draft",
    )
    logger.info("[trips][reverse-geocode] stored ctx=%s link=%s", cid, link_id)
    return {"status": "stored", "context_id": cid, "result_summary": label}


# ── Photo evidence: OCR / vision / photo-context ────────────────────────
#     WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1. Operator-triggered draft
#     extraction. Master gates (HORNELORE_PHOTO_OCR / HORNELORE_PHOTO_
#     VISION) default OFF; a disabled feature returns a clear status, never
#     a fake row. approved_for_lori / include_in_memoir default OFF — the
#     approval ladder is the only way evidence becomes usable/memoir.

@router.post("/photo-links/{link_id}/ocr")
def run_photo_ocr(link_id: str) -> Dict[str, Any]:
    """Run the configured local OCR provider on a linked photo and store
    the result as DRAFT trip_photo_context (context_type='ocr_text')."""
    _require_trips_enabled()
    from ..services import travel_doc_photo_ocr
    if not travel_doc_photo_ocr.ocr_enabled():
        return {"status": "disabled",
                "message": "OCR is off (set HORNELORE_PHOTO_OCR=1 and "
                           "HORNELORE_OCR_PROVIDER)"}
    info = trip_repository.photo_file_for_link(link_id)
    if not info:
        raise HTTPException(status_code=404, detail="photo link not found")
    res = travel_doc_photo_ocr.run_ocr(info.get("image_path") or "")
    if not res.get("ok"):
        return {"status": "unavailable", "engine": res.get("engine"),
                "message": res.get("error")}
    cid = trip_repository.photo_context_create(
        trip_id=info["trip_id"], photo_link_id=link_id,
        context_type="ocr_text", result_summary=res["summary"],
        photo_id=info.get("photo_id"), raw_text=res.get("raw_text"),
        confidence="draft", engine=res.get("engine"),
        source_ref="ocr:photo_link:%s" % link_id)
    logger.info("[trips][photo-ocr] stored ctx=%s link=%s engine=%s",
                cid, link_id, res.get("engine"))
    return {"status": "stored", "context_id": cid,
            "context": trip_repository.photo_context_get(cid)}


@router.post("/photo-links/{link_id}/vision-context")
def run_photo_vision(link_id: str) -> Dict[str, Any]:
    """Run the configured local vision provider (command-only in this
    phase) and store the result as DRAFT trip_photo_context."""
    _require_trips_enabled()
    from ..services import travel_doc_photo_vision
    if not travel_doc_photo_vision.vision_enabled():
        return {"status": "disabled",
                "message": "image-context (vision) is off (set "
                           "HORNELORE_PHOTO_VISION=1 and a local "
                           "HORNELORE_VISION_CMD)"}
    info = trip_repository.photo_file_for_link(link_id)
    if not info:
        raise HTTPException(status_code=404, detail="photo link not found")
    res = travel_doc_photo_vision.run_vision(info.get("image_path") or "")
    if not res.get("ok"):
        return {"status": "unavailable", "engine": res.get("engine"),
                "message": res.get("error")}
    cid = trip_repository.photo_context_create(
        trip_id=info["trip_id"], photo_link_id=link_id,
        context_type="vision_description", result_summary=res["summary"],
        photo_id=info.get("photo_id"), raw_text=res.get("raw_text"),
        confidence="draft", engine=res.get("engine"),
        model_name=res.get("model"),
        source_ref="vision:photo_link:%s" % link_id)
    return {"status": "stored", "context_id": cid,
            "context": trip_repository.photo_context_get(cid)}


# ── WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11) ──────────────
#     Two manual operator-entry lanes on top of the OCR/vision engines:
#
#     * draft observation      — local-LLM / operator draft of what the
#                                photo shows. Stored as
#                                trip_photo_context(context_type=
#                                'draft_observation'), approved_for_lori=0,
#                                include_in_memoir=0, rejected=0. Rejects
#                                empty summary. NOT a provider call —
#                                operator or LLM has already produced the
#                                text. Approval ladder identical to OCR.
#     * place from context     — operator's place inference rooted in
#                                already-reviewable evidence (OCR /
#                                public context / operator labels / trip
#                                structure / broad place notes). Stored
#                                as trip_public_context(source_type=
#                                'place_context'), approved_for_lori=0.
#                                NEVER accepts raw GPS or memoir text.

@router.post("/photo-links/{link_id}/draft-observation")
def create_draft_observation(link_id: str,
                             req: DraftObservationCreate) -> Dict[str, Any]:
    """Store an operator-supplied (or local-LLM-drafted) photo observation
    as a DRAFT trip_photo_context row. Nothing moves up by silence:
    approved_for_lori=0, include_in_memoir=0, rejected=0."""
    _require_trips_enabled()
    summary = (req.result_summary or "").strip()
    if not summary:
        raise HTTPException(status_code=422,
                            detail="result_summary is required")
    info = trip_repository.photo_file_for_link(link_id)
    if not info:
        raise HTTPException(status_code=404, detail="photo link not found")
    engine = (req.engine or "operator_local").strip() or "operator_local"
    cid = trip_repository.photo_context_create(
        trip_id=info["trip_id"], photo_link_id=link_id,
        context_type="draft_observation", result_summary=summary,
        photo_id=info.get("photo_id"), raw_text=req.raw_text,
        confidence="draft", engine=engine,
        model_name=req.model_name,
        source_ref="observation:photo_link:%s" % link_id)
    logger.info(
        "[trips][draft-observation] stored ctx=%s link=%s engine=%s",
        cid, link_id, engine)
    return {"status": "stored", "context_id": cid,
            "context": trip_repository.photo_context_get(cid)}


@router.post("/photo-links/{link_id}/place-from-context")
def create_place_from_context(link_id: str,
                              req: PlaceFromContextCreate) -> Dict[str, Any]:
    """Store an operator-supplied place inference (rooted in the photo's
    already-reviewable evidence — OCR, public context, operator place
    labels, trip/day/stop/region labels, or broad place notes) as a
    DRAFT trip_public_context row (source_type='place_context').
    NEVER accepts raw GPS or memoir text. Approval ladder identical to
    other public-context rows: approved_for_lori=0 until the operator
    approves it."""
    _require_trips_enabled()
    summary = (req.result_summary or "").strip()
    if not summary:
        raise HTTPException(status_code=422,
                            detail="result_summary is required")
    info = trip_repository.photo_file_for_link(link_id)
    if not info:
        raise HTTPException(status_code=404, detail="photo link not found")
    # Provenance: record which evidence sources the operator says they
    # used. Whitelist keeps arbitrary strings from leaking through.
    _ALLOWED_SRC = {
        "ocr", "public_context", "operator_place_label",
        "trip_labels", "broad_place_notes", "local_llm_draft",
    }
    sources = sorted({s for s in (req.evidence_sources or [])
                      if isinstance(s, str) and s in _ALLOWED_SRC})
    note_bits: List[str] = ["source=place_from_context"]
    if sources:
        note_bits.append("evidence=" + ",".join(sources))
    if req.notes:
        # Notes are operator-authored context, safe to include, but pass
        # them through the same sanitizer that OCR/public results ride.
        # Length-cap defensively so a runaway note can't bloat the row.
        note_bits.append("note=" + (req.notes or "").strip()[:800])
    cid = trip_repository.public_context_create(
        trip_id=info["trip_id"], result_summary=summary,
        source_type="place_context",
        photo_link_id=link_id,
        query=None, source_url=None, confidence="draft",
        notes=";".join(note_bits))
    logger.info(
        "[trips][place-from-context] stored ctx=%s link=%s sources=%s",
        cid, link_id, ",".join(sources) or "-")
    return {"status": "stored", "context_id": cid,
            "context": trip_repository.public_context_get(cid)}


@router.get("/photo-links/{link_id}/photo-context")
def list_photo_context(link_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.photo_link_get(link_id):
        raise HTTPException(status_code=404, detail="photo link not found")
    rows = trip_repository.photo_context_list_for_link(link_id)
    return {"link_id": link_id, "count": len(rows), "photo_context": rows}


@router.patch("/photo-context/{context_id}")
def patch_photo_context(context_id: str,
                        req: PhotoContextPatch) -> Dict[str, Any]:
    """Approve / edit / include / reject a photo-context row. Editing
    result_summary or raw_text revokes approval unless re-approved in the
    same request; include_in_memoir requires the row to be approved."""
    _require_trips_enabled()
    existing = trip_repository.photo_context_get(context_id)
    if not existing:
        raise HTTPException(status_code=404, detail="photo context not found")
    if req.include_in_memoir:
        if req.approved_for_lori is not None:
            effective_approved = req.approved_for_lori
        elif req.result_summary is not None or req.raw_text is not None:
            effective_approved = False   # edit revokes approval
        else:
            effective_approved = bool(existing.get("approved_for_lori"))
        if not effective_approved:
            raise HTTPException(
                status_code=400,
                detail="include_in_memoir requires approved_for_lori")
    ok = trip_repository.photo_context_update(
        context_id,
        result_summary=req.result_summary, raw_text=req.raw_text,
        approved_for_lori=req.approved_for_lori,
        include_in_memoir=req.include_in_memoir, rejected=req.rejected)
    if not ok:
        raise HTTPException(status_code=400, detail="nothing to update")
    return {"ok": True,
            "context": trip_repository.photo_context_get(context_id)}


@router.delete("/photo-context/{context_id}")
def delete_photo_context(context_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    if not trip_repository.photo_context_delete(context_id):
        raise HTTPException(status_code=404, detail="photo context not found")
    return {"ok": True, "context_id": context_id}


# ── Public lookup → draft public_context ────────────────────────────────
#     WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 2. Sends ONLY a public query
#     or URL (never GPS / person_id / memoir / unapproved private notes).

def _build_photo_lookup_query(link_id: str, trip_id: str) -> Optional[str]:
    """Assemble a SAFE public query from a photo's public cues ONLY:
    approved OCR text, the reviewable place label, the year, plus the
    stop/region/day label if the photo is anchored to trip structure.

    NEVER include: raw GPS, person_id, memoir text, private notes,
    unapproved photo captions, unapproved public context, narrator-only
    material, or anything else that could leak private life-story
    content to a public lookup provider.

    WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11) tightening:
      * OCR: only approved rows are eligible (was: first non-rejected
        row of any approval state — draft OCR could reach the lookup)
      * Stop / region / day labels added — safe structural context
        already reviewable in the operator surface
      * Explicit approved-caption inclusion (photo_link caption_approved
        _for_lori=1) — narrator/operator captions never bleed through
        unless promoted
    Returns None when only unsafe evidence is available (nothing to
    query on)."""
    cues: List[str] = []

    # OCR: approved rows only. Captions in trip_photo_context ride the
    # same approval_for_lori ladder; the lookup should never fire on
    # draft OCR (that's the whole point of the draft/approved split).
    for r in trip_repository.photo_context_list_for_link(link_id):
        if (r.get("rejected")
                or r.get("context_type") != "ocr_text"
                or not bool(r.get("approved_for_lori"))):
            continue
        summ = (r.get("result_summary") or "").strip()
        if summ:
            cues.append(summ)
            break

    # Photo link fields (place label, year, approved caption + note)
    link_row: Optional[Dict[str, Any]] = None
    for l in trip_repository.photo_links_list(trip_id):
        if l.get("id") == link_id:
            link_row = l
            break
    if link_row:
        place = (link_row.get("photo_location_label") or "").strip()
        if place:
            cues.append(place)
        dv = str(link_row.get("photo_date_value") or "")
        if len(dv) >= 4 and dv[:4].isdigit():
            cues.append(dv[:4])
        # Approved caption (narrator or operator caption promoted for
        # Lori) — safe to include in the query. Unapproved captions
        # NEVER reach here.
        cap = (link_row.get("caption") or "").strip()
        if cap and bool(link_row.get("caption_approved_for_lori")):
            cues.append(cap)
        note = (link_row.get("operator_context_note") or "").strip()
        if note and bool(link_row.get("operator_context_approved_for_lori")):
            cues.append(note)
        # Stop label (photo is anchored to a stop → include the stop
        # name for context)
        stop_id = link_row.get("trip_stop_id")
        if stop_id:
            try:
                stop = trip_repository.stop_get(stop_id)
                # trip_stops uses `location_name` for the display name.
                stop_name = ""
                if stop:
                    stop_name = ((stop.get("location_name")
                                  or stop.get("name") or "").strip())
                if stop_name:
                    cues.append(stop_name)
                # Region title walks up from the stop. trip_regions uses
                # `title` (not `name`) for the display label.
                rid = stop.get("trip_region_id") if stop else None
                if rid and hasattr(trip_repository, "region_get"):
                    reg = trip_repository.region_get(rid)
                    reg_title = ""
                    if reg:
                        reg_title = ((reg.get("title")
                                      or reg.get("name") or "").strip())
                    if reg_title:
                        cues.append(reg_title)
            except Exception:
                pass
        # Day label (photo is anchored to a trip day → include the day
        # label or date if available)
        day_id = link_row.get("trip_day_id")
        if day_id:
            try:
                day = trip_repository.day_get(day_id) \
                    if hasattr(trip_repository, "day_get") else None
                if day:
                    lbl = (day.get("label") or "").strip()
                    if lbl:
                        cues.append(lbl)
                    d = (day.get("date") or "").strip()
                    if len(d) >= 4 and d[:4].isdigit():
                        cues.append(d[:4])
            except Exception:
                pass

    # Deduplicate while preserving order (a place label + region name
    # may collide; the year may already be in the caption).
    seen: set = set()
    deduped: List[str] = []
    for c in cues:
        k = c.lower()
        if k in seen:
            continue
        seen.add(k)
        deduped.append(c)

    q = " ".join(deduped).strip()
    return q or None


@router.post("/{trip_id}/public-context/lookup")
def public_context_lookup(trip_id: str,
                          req: PublicLookupRequest) -> Dict[str, Any]:
    _require_trips_enabled()
    from ..services import travel_doc_public_lookup
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    if not travel_doc_public_lookup.lookup_enabled():
        return {"status": "disabled",
                "message": "public lookup is off (set "
                           "HORNELORE_PUBLIC_LOOKUP=1 and a provider)"}
    if not ((req.query or "").strip() or (req.url or "").strip()):
        raise HTTPException(status_code=422, detail="need a query or url")
    if req.source_type not in _PUBLIC_CONTEXT_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="invalid source_type")
    _validate_source_scope(trip_id, req.trip_region_id, req.trip_stop_id)
    _validate_photo_link_scope(trip_id, req.photo_link_id)
    res = travel_doc_public_lookup.run_lookup(query=req.query, url=req.url)
    if not res.get("ok"):
        return {"status": "unavailable", "provider": res.get("provider"),
                "message": res.get("error")}
    cid = trip_repository.public_context_create(
        trip_id=trip_id, result_summary=res["summary"],
        source_type=req.source_type, trip_region_id=req.trip_region_id,
        trip_stop_id=req.trip_stop_id, photo_link_id=req.photo_link_id,
        query=(req.query or ("url:" + (req.url or ""))),
        source_url=res.get("source_url") or req.url, confidence="draft",
        notes="provider=%s" % res.get("provider"))
    logger.info("[trips][public-lookup] stored ctx=%s trip=%s provider=%s",
                cid, trip_id, res.get("provider"))
    return {"status": "stored", "context_id": cid,
            "context": trip_repository.public_context_get(cid)}


@router.post("/photo-links/{link_id}/lookup-context")
def photo_lookup_context(link_id: str,
                         req: PublicLookupRequest) -> Dict[str, Any]:
    """Convenience lookup for a photo card: build a SAFE public query from
    the photo's public cues (or use the operator's typed query/url) and
    store the result as draft public_context scoped to this photo."""
    _require_trips_enabled()
    from ..services import travel_doc_public_lookup
    if not travel_doc_public_lookup.lookup_enabled():
        return {"status": "disabled",
                "message": "public lookup is off (set "
                           "HORNELORE_PUBLIC_LOOKUP=1 and a provider)"}
    info = trip_repository.photo_file_for_link(link_id)
    if not info:
        raise HTTPException(status_code=404, detail="photo link not found")
    # An operator-typed query is intentional and sent as-is; otherwise
    # build a query from PUBLIC photo cues only (never GPS/person/memoir).
    query = ((req.query or "").strip()
             or _build_photo_lookup_query(link_id, info["trip_id"]))
    if not (query or (req.url or "").strip()):
        return {"status": "no_cues",
                "message": "no public OCR/place/date cues to look up yet — "
                           "run OCR first or type a query"}
    res = travel_doc_public_lookup.run_lookup(query=query, url=req.url)
    if not res.get("ok"):
        return {"status": "unavailable", "provider": res.get("provider"),
                "message": res.get("error")}
    stype = (req.source_type if req.source_type in _PUBLIC_CONTEXT_SOURCE_TYPES
             else "place_context")
    cid = trip_repository.public_context_create(
        trip_id=info["trip_id"], result_summary=res["summary"],
        source_type=stype, photo_link_id=link_id,
        query=(query or ("url:" + (req.url or ""))),
        source_url=res.get("source_url") or req.url, confidence="draft",
        notes="provider=%s;photo_lookup" % res.get("provider"))
    return {"status": "stored", "context_id": cid, "query_used": query,
            "context": trip_repository.public_context_get(cid)}


# ── Trip days (WO-TRAVEL-DOC-UI-LAB-01 — Trip Calendar layer) ──────────────
#
#     GET   /api/trips/{trip_id}/days
#     POST  /api/trips/{trip_id}/days/generate-from-dates
#     PATCH /api/trips/days/{day_id}
#
#     POST  /api/trips/{trip_id}/days/{day_id}/photos/link
#     POST  /api/trips/{trip_id}/days/{day_id}/photos/unlink
#
# Day rows power the Trip Calendar day cards + day-detail inspector in
# the (removable) Travel Doc UI Lab. WO-TRAVEL-DOC-UI-LAB-02: day-scoped
# photo attach/detach + day-scoped notes (LocationNoteCreate.trip_day_id)
# landed with migration 0028 — the lab's "Add photos" / "Add note"
# buttons now stay in-lab instead of deep-linking away.


class TripDayPatch(BaseModel):
    title: Optional[str] = None
    main_location: Optional[str] = None
    lodging_base: Optional[str] = None
    trip_region_id: Optional[str] = None
    trip_stop_id: Optional[str] = None
    morning_notes: Optional[str] = None
    afternoon_notes: Optional[str] = None
    evening_notes: Optional[str] = None
    places_visited: Optional[List[str]] = None
    meals: Optional[List[str]] = None
    clear_title: bool = False
    clear_main_location: bool = False
    clear_lodging_base: bool = False
    clear_morning_notes: bool = False
    clear_afternoon_notes: bool = False
    clear_evening_notes: bool = False
    clear_region: bool = False
    clear_stop: bool = False


@router.get("/{trip_id}/days")
def list_trip_days(trip_id: str) -> Dict[str, Any]:
    """Day rows for a trip with honest per-day evidence counts merged in
    (photos by taken-date match; notes/sources/public-context only via
    the day's linked stop/region scope — see trip_day_counts)."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    days = trip_repository.trip_days_list(trip_id)
    counts = trip_repository.trip_day_counts(trip_id)
    for d in days:
        d["counts"] = counts.get(str(d["id"]), {
            "photos": 0, "notes": 0, "sources": 0, "public_context": 0,
        })
    return {"trip_id": trip_id, "count": len(days), "days": days}


@router.post("/{trip_id}/days/generate-from-dates")
def generate_trip_days(trip_id: str) -> Dict[str, Any]:
    """Generate one day row per date in the trip window (inclusive),
    skipping dates that already exist — idempotent, never overwrites
    operator edits. 422 when the trip has no usable start/end dates."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    try:
        result = trip_repository.trip_days_generate(trip_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info("[trips][days] generated trip=%s created=%d total=%d",
                trip_id, result["created"], result["total"])
    return {"trip_id": trip_id, "created": result["created"],
            "total": result["total"],
            "days": trip_repository.trip_days_list(trip_id)}


class TripDaysReconcileReq(BaseModel):
    add_missing: bool = False
    mark_out_of_range: bool = False


@router.get("/{trip_id}/days/reconcile-preview")
def reconcile_preview_trip_days(trip_id: str) -> Dict[str, Any]:
    """WO-TRAVEL-DOC-UI-LAB-03 — READ-ONLY diff between the trip's
    start/end window and its existing day rows: missing in-range dates,
    out-of-range day cards (kept, never deleted), duplicate/invalid
    dates. No writes."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    return trip_repository.trip_days_reconcile_preview(trip_id)


@router.post("/{trip_id}/days/reconcile")
def reconcile_trip_days(trip_id: str,
                        req: TripDaysReconcileReq) -> Dict[str, Any]:
    """WO-TRAVEL-DOC-UI-LAB-03 — apply reconcile actions. add_missing
    creates ONLY missing in-range days (existing/operator-edited rows
    are never overwritten); mark_out_of_range stamps reconcile_status =
    'out_of_range_acknowledged' on out-of-range day cards. NOTHING is
    deleted — out-of-range cards are kept to protect operator notes."""
    _require_trips_enabled()
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    try:
        out = trip_repository.trip_days_reconcile(
            trip_id,
            add_missing=bool(getattr(req, "add_missing", False)),
            mark_out_of_range=bool(getattr(req, "mark_out_of_range",
                                           False)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info("[trips][days] reconcile trip=%s added=%d marked=%d "
                "reactivated=%d", trip_id, out["added"],
                out["marked_out_of_range"], out["reactivated"])
    out["days"] = trip_repository.trip_days_list(trip_id)
    return out


@router.patch("/days/{day_id}")
def patch_trip_day(day_id: str, req: TripDayPatch) -> Dict[str, Any]:
    """Edit one day card. Region/stop links are validated against the
    day's own trip (same cross-trip posture as _validate_source_scope)."""
    _require_trips_enabled()
    day = trip_repository.trip_day_get(day_id)
    if not day:
        raise HTTPException(status_code=404, detail="day not found")
    _validate_source_scope(day["trip_id"], req.trip_region_id,
                           req.trip_stop_id)
    # When a stop is linked, keep the region consistent with the stop's
    # own region (mirrors the photo-link region/stop desync rule).
    region_id = req.trip_region_id
    if req.trip_stop_id:
        _stop = trip_repository.stop_get(req.trip_stop_id)
        if _stop and not region_id:
            region_id = _stop.get("trip_region_id")
    ok = trip_repository.trip_day_update(
        day_id,
        title=req.title,
        main_location=req.main_location,
        lodging_base=req.lodging_base,
        trip_region_id=region_id,
        trip_stop_id=req.trip_stop_id,
        morning_notes=req.morning_notes,
        afternoon_notes=req.afternoon_notes,
        evening_notes=req.evening_notes,
        places_visited=req.places_visited,
        meals=req.meals,
        clear_title=req.clear_title,
        clear_main_location=req.clear_main_location,
        clear_lodging_base=req.clear_lodging_base,
        clear_morning_notes=req.clear_morning_notes,
        clear_afternoon_notes=req.clear_afternoon_notes,
        clear_evening_notes=req.clear_evening_notes,
        clear_region=req.clear_region,
        clear_stop=req.clear_stop,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="nothing to update")
    return {"ok": True, "day": trip_repository.trip_day_get(day_id)}


class TripDayPhotoLinksReq(BaseModel):
    photo_link_ids: List[str] = []


def _require_day_in_trip(trip_id: str, day_id: str) -> Dict[str, Any]:
    if not trip_repository.trip_get(trip_id):
        raise HTTPException(status_code=404, detail="trip not found")
    day = trip_repository.trip_day_get(day_id)
    if not day or day.get("trip_id") != trip_id:
        raise HTTPException(status_code=404, detail="day not in this trip")
    return day


@router.post("/{trip_id}/days/{day_id}/photos/link")
def link_day_photos(trip_id: str, day_id: str,
                    req: TripDayPhotoLinksReq) -> Dict[str, Any]:
    """Attach existing trip photo links to a day card (0028). Links must
    belong to this trip; the day must belong to this trip. Attached
    photos count on their day first (see trip_day_counts)."""
    _require_trips_enabled()
    _require_day_in_trip(trip_id, day_id)
    ids = list(req.photo_link_ids or [])
    if not ids:
        raise HTTPException(status_code=422, detail="no photo_link_ids")
    try:
        updated = trip_repository.photo_links_set_day(ids, day_id, trip_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("[trips][days] photo-link trip=%s day=%s n=%d",
                trip_id, day_id, updated)
    return {"ok": True, "updated": updated, "trip_day_id": day_id}


@router.post("/{trip_id}/days/{day_id}/photos/unlink")
def unlink_day_photos(trip_id: str, day_id: str,
                      req: TripDayPhotoLinksReq) -> Dict[str, Any]:
    """Detach photo links from a day card (trip_day_id -> NULL). The
    photos keep their trip link; counts fall back to date match."""
    _require_trips_enabled()
    _require_day_in_trip(trip_id, day_id)
    ids = list(req.photo_link_ids or [])
    if not ids:
        raise HTTPException(status_code=422, detail="no photo_link_ids")
    try:
        updated = trip_repository.photo_links_set_day(ids, None, trip_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    logger.info("[trips][days] photo-unlink trip=%s day=%s n=%d",
                trip_id, day_id, updated)
    return {"ok": True, "updated": updated, "trip_day_id": None}
