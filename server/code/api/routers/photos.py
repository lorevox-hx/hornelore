"""WO-LORI-PHOTO-SHARED-01 — Phase 1 photo authority layer router.

All endpoints are gated behind ``HORNELORE_PHOTO_ENABLED``. When the flag
is off, every handler returns 404 so the surface is invisible to the UI
unless the operator opts in. The flag is checked per-request rather than
at router-mount time so toggling via ``.env`` + stack restart is enough —
no code edits required.

The router is the thin seam between HTTP and the services layer:

  router            HTTP/multipart parsing, provenance stamping, shape
    │               validation (empty-transcript-allowed-only-for-… etc.)
    ▼
  services.photos.repository      (SQLite writes / reads)
  services.photo_intake.storage   (file + thumbnail on disk)
  services.photo_intake.dedupe    (sha256 short-circuit)
  services.photo_elicit.selector  (hard cooldowns)
  services.photo_elicit.template_prompt (three-tier text)

extract.py is NEVER imported — photo_memory extraction arrives in
Phase 2 (WO-LORI-PHOTO-ELICIT-01) and lives in its own module.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import flags
from ...services.photos import repository as photo_repo
from ...services.photos.models import (
    DATE_PRECISIONS,
    LOCATION_SOURCES,
    MEMORY_TYPES,
    TRANSCRIPT_SOURCES,
)
from ...services.photos.confidence import needs_confirmation_for_location
from ...services.photos.provenance import make_provenance
from ...services.photo_intake.dedupe import sha256_file
from ...services.photo_intake.exif import extract_exif
from ...services.photo_intake.storage import store_photo_file
from ...services.photo_intake.geocode_real import reverse_geocode
from ...services.photo_intake.plus_code import short_local_code
from ...services.photo_intake.description_template import build_description
from ...services.photo_elicit.selector import select_next_photo
from ...services.photo_elicit.template_prompt import build_photo_prompt


log = logging.getLogger("lorevox.photos")


# P2.2 (code review 2026-04-26): loud startup check for Pillow.
# Pillow is required for thumbnail generation + EXIF auto-fill, but
# both modules fail-soft on missing PIL (catch ImportError, log at
# WARN, return None / empty-shape). The combination produces a system
# that LOOKS like it's working — uploads succeed, no errors in
# api.log — but silently emits broken thumbnails and empty EXIF
# metadata. This bit us 2026-04-25 night and ate ~90 minutes of
# diagnosis time.
#
# This module-load check runs once at server boot and ensures the
# operator sees a clear ERROR line at startup if Pillow isn't where
# we need it. The check is intentionally NOT a fail-fast import —
# we want the rest of the photo surface (upload, list, patch,
# delete) to keep working even if thumbnails + EXIF are unavailable.
def _startup_pillow_check() -> None:
    try:
        from PIL import Image  # type: ignore
        version = getattr(Image, "__version__", None)
        if version is None:
            try:
                from PIL import __version__ as version  # type: ignore
            except Exception:
                version = "unknown"
        log.info("[photos][startup] Pillow available: version=%s", version)
    except ImportError:
        log.error(
            "[photos][startup] PILLOW NOT INSTALLED in this Python environment. "
            "Thumbnails + EXIF auto-fill will silently produce no output. "
            "Fix: `.venv-gpu/bin/pip install Pillow` then restart uvicorn. "
            "See docs/PILLOW-VENV-INSTALL.md for the full diagnosis."
        )
    except Exception as exc:
        # Anything else is also worth logging loudly — Pillow installed
        # but mis-configured is a real failure mode worth surfacing.
        log.error(
            "[photos][startup] Pillow import errored unexpectedly: %s. "
            "Thumbnails + EXIF auto-fill may not work. "
            "See docs/PILLOW-VENV-INSTALL.md.",
            exc,
        )


_startup_pillow_check()


router = APIRouter(prefix="/api/photos", tags=["photos"])


# ---------------------------------------------------------------------------
# Flag gate
# ---------------------------------------------------------------------------


def _require_enabled() -> None:
    """Raise 404 when HORNELORE_PHOTO_ENABLED is off."""

    if not flags.photo_enabled():
        raise HTTPException(status_code=404, detail="photo surface disabled")


# ---------------------------------------------------------------------------
# Pydantic payloads for the JSON endpoints
# ---------------------------------------------------------------------------


class _PhotoPatch(BaseModel):
    description: Optional[str] = None
    date_value: Optional[str] = None
    date_precision: Optional[str] = None
    location_label: Optional[str] = None
    location_source: Optional[str] = None
    narrator_ready: Optional[bool] = None
    needs_confirmation: Optional[bool] = None
    last_edited_by_user_id: str = Field(..., min_length=1)


class _SessionCreate(BaseModel):
    narrator_id: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class _MemoryCreate(BaseModel):
    transcript: str = ""
    memory_type: str
    transcript_source: Optional[str] = None
    transcript_confidence: Optional[float] = None
    transcript_guard_flags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_ALLOWED_IMAGE_MIME_PREFIXES = (
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/gif",
)

_EMPTY_TRANSCRIPT_ALLOWED_FOR = {"zero_recall", "distress_abort"}

# Show-outcome policy (spec §13).
_MEMORY_TYPE_TO_SHOW_OUTCOME = {
    "zero_recall": "zero_recall",
    "distress_abort": "distress_abort",
}


def _truthy_form(raw: Optional[str]) -> Optional[bool]:
    if raw is None:
        return None
    return str(raw).strip().lower() in ("1", "true", "yes", "on", "t", "y")


def _parse_json_list(raw: Optional[str]) -> List[Dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json for people/events")
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="people/events must be a JSON array")
    out: List[Dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(item)
    return out


def _validate_enum(name: str, value: Optional[str], allowed: tuple) -> None:
    if value is None:
        return
    if value not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"{name}='{value}' not in {list(allowed)}",
        )


def _photo_with_relations(photo_id: str) -> Optional[Dict[str, Any]]:
    photo = photo_repo.get_photo(photo_id)
    return photo


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health")
def photos_health() -> Dict[str, Any]:
    # Intentionally NOT gated — lets the stack verify the flag state without
    # giving up any data. Returns enabled=True/False so the UI can decide
    # whether to render the photo surface at all.
    return {"ok": True, "enabled": flags.photo_enabled()}


# ---------------------------------------------------------------------------
# POST /api/photos/preview   (Review File Info — read EXIF + geocode, no DB write)
# ---------------------------------------------------------------------------


@router.post("/preview")
async def preview_photo(
    file: UploadFile = File(...),
) -> JSONResponse:
    """Read EXIF + reverse-geocode a photo WITHOUT saving it.

    Mirrors the visualschedulebot "Review File Info" flow: pick file,
    click Review, server returns prefilled values for the curator to
    review/edit before committing via the regular POST /api/photos.

    Gated by the same flag as the rest of the photo surface
    (HORNELORE_PHOTO_ENABLED). EXIF extraction always runs (no flag);
    reverse-geocode + Plus Code only run when GPS is present in EXIF.

    Returns:
        {
          "captured_at": "YYYY-MM-DD" | None,
          "captured_at_precision": "exact" | "unknown",
          "captured_dt_full": "YYYY-MM-DD HH:MM:SS" | None,
          "gps": {"latitude": float|None, "longitude": float|None, "source": "exif_gps"|"unknown"},
          "plus_code": "RWRJ+2V" | None,
          "address": {city, state, state_abbrev, country, country_code, address_line, provider},
          "description": "This image is from ..." | "",
          "raw_exif_keys": int,    # hint for the UI ("48 EXIF tags found")
        }

    Never writes to disk or DB. The temp file is created in /tmp and
    deleted before returning.
    """
    _require_enabled()

    mime = (file.content_type or "").lower()
    if mime and not any(mime.startswith(p) for p in _ALLOWED_IMAGE_MIME_PREFIXES):
        raise HTTPException(
            status_code=415, detail=f"unsupported media type: {mime}"
        )

    # Stream upload to a temp file so EXIF reader has a real path.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="photo_preview_", suffix=".bin")
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                out.write(chunk)

        exif = extract_exif(tmp_path)
    finally:
        try:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except OSError:
            pass

    # Pull EXIF DateTimeOriginal in full ISO form for time-of-day display.
    raw_exif = exif.get("raw_exif") or {}
    captured_dt_full = None
    for tag_name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        candidate = raw_exif.get(tag_name)
        if candidate:
            # EXIF format "YYYY:MM:DD HH:MM:SS" -> "YYYY-MM-DD HH:MM:SS"
            try:
                s = str(candidate).strip()
                date_part, _, time_part = s.partition(" ")
                date_norm = date_part.replace(":", "-")
                if time_part:
                    captured_dt_full = f"{date_norm} {time_part}"
                else:
                    captured_dt_full = date_norm
                break
            except Exception:
                continue

    gps = exif.get("gps") or {}
    lat = gps.get("latitude")
    lng = gps.get("longitude")

    # Reverse-geocode + Plus Code (only when GPS present)
    address: Dict[str, Any] = {
        "city": None, "state": None, "state_abbrev": None,
        "country": None, "country_code": None,
        "address_line": None, "provider": None,
    }
    plus_code: Optional[str] = None
    if lat is not None and lng is not None:
        try:
            geo = reverse_geocode(lat, lng)
            address = {k: v for k, v in geo.items() if k != "raw"}
        except Exception as exc:
            log.info("[photos][preview] reverse_geocode failed: %s", exc)
        try:
            plus_code = short_local_code(lat, lng)
        except Exception as exc:
            log.info("[photos][preview] plus_code failed: %s", exc)

    # Build the auto-description sentence
    description = ""
    try:
        description = build_description(
            captured_at=exif.get("captured_at"),
            captured_dt_full=captured_dt_full,
            plus_code=plus_code,
            city=address.get("city"),
            state_abbrev=address.get("state_abbrev") or address.get("state"),
            country=address.get("country"),
        )
    except Exception as exc:
        log.info("[photos][preview] build_description failed: %s", exc)

    log.info(
        "[photos][preview] file=%s exif_keys=%d gps=%s plus_code=%s city=%s",
        file.filename or "(unnamed)",
        len(raw_exif),
        f"({lat:.4f},{lng:.4f})" if lat is not None and lng is not None else "none",
        plus_code or "none",
        address.get("city") or "none",
    )

    return JSONResponse(
        status_code=200,
        content={
            "captured_at": exif.get("captured_at"),
            "captured_at_precision": exif.get("captured_at_precision"),
            "captured_dt_full": captured_dt_full,
            "gps": {
                "latitude": lat,
                "longitude": lng,
                "source": gps.get("source") or "unknown",
            },
            "plus_code": plus_code,
            "address": address,
            "description": description,
            "raw_exif_keys": len(raw_exif),
        },
    )


# ---------------------------------------------------------------------------
# POST /api/photos   (multipart upload)
# ---------------------------------------------------------------------------


@router.post("")
async def upload_photo(
    file: UploadFile = File(...),
    narrator_id: str = Form(...),
    uploaded_by_user_id: str = Form(...),
    description: Optional[str] = Form(None),
    date_value: Optional[str] = Form(None),
    date_precision: Optional[str] = Form(None),
    location_label: Optional[str] = Form(None),
    location_source: Optional[str] = Form(None),
    narrator_ready: Optional[str] = Form(None),
    people: Optional[str] = Form(None),   # JSON array of {person_label, person_id?}
    events: Optional[str] = Form(None),   # JSON array of {event_label,  event_id?}
) -> JSONResponse:
    _require_enabled()

    _validate_enum("date_precision", date_precision, DATE_PRECISIONS)
    _validate_enum("location_source", location_source, LOCATION_SOURCES)

    mime = (file.content_type or "").lower()
    if mime and not any(mime.startswith(p) for p in _ALLOWED_IMAGE_MIME_PREFIXES):
        raise HTTPException(status_code=415, detail=f"unsupported media type: {mime}")

    ready_flag = _truthy_form(narrator_ready) or False
    people_rows = _parse_json_list(people)
    event_rows = _parse_json_list(events)

    # Stream upload to a temp file so the hash + move semantics in
    # store_photo_file stay identical across call sites.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="photo_upload_", suffix=".bin")
    try:
        with os.fdopen(tmp_fd, "wb") as out:
            while True:
                chunk = await file.read(65536)
                if not chunk:
                    break
                out.write(chunk)

        # Dedup check BEFORE we move bytes into the archive — so dup uploads
        # don't litter the archive tree with orphan copies.
        file_hash = sha256_file(tmp_path)
        existing = photo_repo.find_photo_by_hash(narrator_id, file_hash)
        if existing is not None:
            return JSONResponse(
                status_code=409,
                content={
                    "error": "duplicate_file",
                    "photo": existing,
                },
            )

        original_filename = file.filename or "upload.bin"
        photo_id = uuid.uuid4().hex
        stored = store_photo_file(
            narrator_id=narrator_id,
            source_path=tmp_path,
            original_filename=original_filename,
            photo_id=photo_id,
        )
    finally:
        # If store_photo_file moved the tmp file, unlink is a no-op; if it
        # failed before the move, we still clean up.
        try:
            if Path(tmp_path).exists():
                Path(tmp_path).unlink()
        except OSError:
            pass

    # Provenance is stamped on every authoring row by the services layer;
    # the ``photos`` row records the uploader directly via
    # ``uploaded_by_user_id``, so no separate provenance dict is needed
    # at row-insert time.
    _ = make_provenance(
        source_type="curator_input",
        source_authority="curator",
        source_actor_id=uploaded_by_user_id,
    )

    derived_needs_confirmation = needs_confirmation_for_location(location_source)

    # ---- WO-LORI-PHOTO-INTAKE-01 Phase 2: EXIF auto-fill -------------
    # When HORNELORE_PHOTO_INTAKE=1, read EXIF from the stored image and
    # use it ONLY to fill date / GPS fields the curator left blank.
    # Curator-supplied values always win. The raw EXIF tag map is stamped
    # into metadata_json regardless (forensic trail, non-authoritative).
    effective_date_value = date_value
    effective_date_precision = date_precision or "unknown"
    effective_location_source = location_source or "unknown"
    effective_latitude: Optional[float] = None
    effective_longitude: Optional[float] = None
    metadata_payload: Optional[Dict[str, Any]] = None
    exif_used = []  # for log

    if flags.photo_intake_enabled():
        exif = extract_exif(stored["image_path"])

        # Date: only fill if curator left date_value blank.
        if not (date_value and date_value.strip()):
            if exif.get("captured_at"):
                effective_date_value = exif["captured_at"]
                # Only override precision when curator left it default.
                if effective_date_precision in (None, "", "unknown"):
                    effective_date_precision = exif.get("captured_at_precision") or "day"
                exif_used.append("date")

        # GPS: only fill when curator did not specify a location_source
        # (i.e. left it as 'unknown'). exif_gps is high-confidence per
        # spec §7, so needs_confirmation flips to False.
        gps = exif.get("gps") or {}
        gps_lat = gps.get("latitude")
        gps_lng = gps.get("longitude")
        if (
            gps_lat is not None
            and gps_lng is not None
            and (effective_location_source in (None, "", "unknown"))
        ):
            effective_latitude = gps_lat
            effective_longitude = gps_lng
            effective_location_source = "exif_gps"
            derived_needs_confirmation = False
            exif_used.append("gps")

        # Always preserve the raw tag map for forensic review, even when
        # nothing was auto-filled (curator may have typed values that
        # disagree with EXIF — the conflict detector in Phase 2 full
        # release will surface that).
        metadata_payload = {
            "exif": exif.get("raw_exif") or {},
            "exif_orientation": exif.get("orientation"),
            "exif_captured_at": exif.get("captured_at"),
            "exif_gps": gps,
        }

        if exif_used:
            log.info(
                "[photos][exif] auto-filled %s for photo_id=%s narrator=%s",
                ",".join(exif_used),
                stored["photo_id"],
                narrator_id,
            )

    # Normalise empty Optional enum fields back to the repository defaults.
    row = photo_repo.create_photo(
        photo_id=stored["photo_id"],
        narrator_id=narrator_id,
        uploaded_by_user_id=uploaded_by_user_id,
        file_hash=stored["file_hash"],
        image_path=stored["image_path"],
        thumbnail_path=stored.get("thumbnail_path"),
        description=description,
        date_value=effective_date_value,
        date_precision=(effective_date_precision or "unknown"),
        location_label=location_label,
        location_source=(effective_location_source or "unknown"),
        latitude=effective_latitude,
        longitude=effective_longitude,
        narrator_ready=ready_flag,
        needs_confirmation=derived_needs_confirmation,
        metadata=metadata_payload,
    )

    # Attach curator-provided people / events (best-effort — each row
    # carries its own provenance stamp).
    for p in people_rows:
        label = (p.get("person_label") or "").strip()
        if not label:
            continue
        photo_repo.add_photo_person(
            photo_id=row["id"],
            person_label=label,
            person_id=p.get("person_id"),
            provenance=make_provenance(
                source_type="curator_input",
                source_authority="curator",
                source_actor_id=uploaded_by_user_id,
            ),
        )
    for e in event_rows:
        label = (e.get("event_label") or "").strip()
        if not label:
            continue
        photo_repo.add_photo_event(
            photo_id=row["id"],
            event_label=label,
            event_id=e.get("event_id"),
            provenance=make_provenance(
                source_type="curator_input",
                source_authority="curator",
                source_actor_id=uploaded_by_user_id,
            ),
        )

    full = _photo_with_relations(row["id"]) or row
    return JSONResponse(status_code=201, content=full)


# ---------------------------------------------------------------------------
# GET /api/photos
# ---------------------------------------------------------------------------


@router.get("")
def list_photos(
    narrator_id: str = Query(...),
    narrator_ready: Optional[bool] = Query(None),
) -> Dict[str, Any]:
    _require_enabled()
    rows = photo_repo.list_photos(
        narrator_id=narrator_id,
        narrator_ready=narrator_ready,
        deleted=False,
    )
    return {"photos": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# GET /api/photos/{photo_id}
# ---------------------------------------------------------------------------


@router.get("/{photo_id}")
def get_photo(photo_id: str) -> Dict[str, Any]:
    _require_enabled()
    row = photo_repo.get_photo(photo_id)
    if row is None:
        raise HTTPException(status_code=404, detail="photo not found")
    return row


# ---------------------------------------------------------------------------
# PATCH /api/photos/{photo_id}
# ---------------------------------------------------------------------------


@router.patch("/{photo_id}")
def patch_photo(photo_id: str, body: _PhotoPatch) -> Dict[str, Any]:
    _require_enabled()

    payload = body.model_dump(exclude_unset=True)
    actor = payload.pop("last_edited_by_user_id", None)
    if not actor:
        raise HTTPException(status_code=400, detail="last_edited_by_user_id required")

    _validate_enum("date_precision", payload.get("date_precision"), DATE_PRECISIONS)
    _validate_enum("location_source", payload.get("location_source"), LOCATION_SOURCES)

    # Auto-derive needs_confirmation from location_source iff the caller
    # didn't explicitly set it in this PATCH payload.
    if (
        "needs_confirmation" not in payload
        and "location_source" in payload
    ):
        payload["needs_confirmation"] = needs_confirmation_for_location(
            payload.get("location_source")
        )

    if not payload:
        # Nothing to update — still stamp last_edited_at via the repository
        # by passing an empty patch, but that would be a no-op; return the
        # current row unchanged instead.
        row = photo_repo.get_photo(photo_id)
        if row is None:
            raise HTTPException(status_code=404, detail="photo not found")
        return row

    updated = photo_repo.patch_photo(
        photo_id=photo_id,
        patch=payload,
        actor_id=actor,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="photo not found")
    return updated


# ---------------------------------------------------------------------------
# DELETE /api/photos/{photo_id}   (soft-delete)
# ---------------------------------------------------------------------------


@router.delete("/{photo_id}")
def delete_photo(
    photo_id: str,
    actor_id: str = Query(..., alias="actor_id"),
) -> Dict[str, Any]:
    _require_enabled()
    ok = photo_repo.soft_delete_photo(photo_id=photo_id, actor_id=actor_id)
    if not ok:
        raise HTTPException(status_code=404, detail="photo not found")
    current = photo_repo.get_photo(photo_id, deleted=True)
    return {"ok": True, "photo": current}


# ---------------------------------------------------------------------------
# POST /api/photos/sessions
# ---------------------------------------------------------------------------


@router.post("/sessions")
def create_photo_session(body: _SessionCreate) -> JSONResponse:
    _require_enabled()
    row = photo_repo.create_photo_session(
        narrator_id=body.narrator_id,
        session_id=body.session_id,
    )
    return JSONResponse(status_code=201, content=row)


# ---------------------------------------------------------------------------
# POST /api/photos/sessions/{id}/show-next
# ---------------------------------------------------------------------------


@router.post("/sessions/{photo_session_id}/show-next")
def show_next(photo_session_id: str) -> Dict[str, Any]:
    _require_enabled()

    session = photo_repo.get_photo_session(photo_session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="photo session not found")
    if session.get("ended_at"):
        raise HTTPException(status_code=409, detail="photo session already ended")

    picked = select_next_photo(
        narrator_id=session["narrator_id"],
        repository=photo_repo,
    )
    if picked is None:
        return {"photo": None, "show_id": None, "prompt_text": None}

    # Enrich the photo dict with people labels BEFORE prompt rendering so
    # the "This photo shows X and Y" tier has real names to join.
    enriched = photo_repo.get_photo(picked["id"]) or picked
    prompt_text = build_photo_prompt(
        {
            "people": [p.get("person_label") for p in enriched.get("people", []) if p.get("person_label")],
            "place": enriched.get("location_label"),
            "date": enriched.get("date_value"),
        }
    )

    show_row = photo_repo.record_photo_show(
        photo_session_id=photo_session_id,
        photo_id=enriched["id"],
        prompt_text=prompt_text,
    )

    return {
        "photo": enriched,
        "show_id": show_row["id"],
        "prompt_text": prompt_text,
    }


# ---------------------------------------------------------------------------
# POST /api/photos/shows/{show_id}/memory
# ---------------------------------------------------------------------------


@router.post("/shows/{show_id}/memory")
def create_memory(show_id: str, body: _MemoryCreate) -> JSONResponse:
    _require_enabled()

    show = photo_repo.get_photo_show(show_id)
    if show is None:
        raise HTTPException(status_code=404, detail="photo show not found")

    if body.memory_type not in MEMORY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"memory_type must be one of {list(MEMORY_TYPES)}",
        )
    if body.transcript_source is not None:
        _validate_enum("transcript_source", body.transcript_source, TRANSCRIPT_SOURCES)

    transcript = body.transcript or ""
    stripped = transcript.strip()
    if not stripped and body.memory_type not in _EMPTY_TRANSCRIPT_ALLOWED_FOR:
        raise HTTPException(
            status_code=400,
            detail=(
                "empty transcript only allowed for memory_type in "
                f"{sorted(_EMPTY_TRANSCRIPT_ALLOWED_FOR)}"
            ),
        )

    # Resolve the narrator via the parent session (show rows don't carry
    # narrator_id themselves — they reference photo_sessions.id).
    parent_session = photo_repo.get_photo_session(show["photo_session_id"])
    actor = (parent_session or {}).get("narrator_id") or "narrator"
    memory_prov = make_provenance(
        source_type="narrator_story",
        source_authority="narrator",
        source_actor_id=actor,
    )

    memory_row = photo_repo.create_photo_memory(
        photo_id=show["photo_id"],
        photo_session_show_id=show_id,
        transcript=transcript,
        memory_type=body.memory_type,
        transcript_source=body.transcript_source,
        transcript_confidence=body.transcript_confidence,
        transcript_guard_flags=body.transcript_guard_flags,
        provenance=memory_prov,
    )

    # Map memory_type → show outcome per spec §13.
    outcome = _MEMORY_TYPE_TO_SHOW_OUTCOME.get(body.memory_type, "story_captured")
    photo_repo.update_photo_show_outcome(show_id=show_id, outcome=outcome)

    return JSONResponse(
        status_code=201,
        content={"memory": memory_row, "show_outcome": outcome},
    )


# ---------------------------------------------------------------------------
# POST /api/photos/sessions/{id}/end
# ---------------------------------------------------------------------------


@router.post("/sessions/{photo_session_id}/end")
def end_photo_session(photo_session_id: str) -> Dict[str, Any]:
    _require_enabled()
    result = photo_repo.end_photo_session(photo_session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="photo session not found")
    return result
