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
    GET   /api/trips/{trip_id}/date-confirmations  (Phase 4 recognition offers)
    GET   /api/trips/{trip_id}/narrator-photo-links (narrator-ready only)
    DELETE /api/trips/{trip_id}
    GET   /api/trips/{trip_id}/export-docx    (Part I/II/III + photo appendix)
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
) -> Dict[str, Any]:
    """Shared upload core for stop-scoped AND trip-level photo drops.

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
        else:
            _method = "trip_upload"
            _confidence = 0.3  # review-queue range; re-cluster may place
            _confirm = False
        link_id = trip_repository.photo_link_upsert(
            trip_id=trip["id"],
            photo_id=photo["id"],
            trip_region_id=(stop or {}).get("trip_region_id"),
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
def delete_region(region_id: str) -> Dict[str, Any]:
    _require_trips_enabled()
    _tid = trip_repository.region_trip_id(region_id)
    if not trip_repository.region_delete(region_id):
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
