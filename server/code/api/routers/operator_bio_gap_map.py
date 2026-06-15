"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase F dashboard router.

Operator-only bio gap map endpoints. The Bug Panel surface
(bug-panel-bio-gap-map.js) consumes these. Per WO §Bio gap map, this
is the operator's situational-awareness surface for what the memoir
is missing.

ENDPOINTS:

  GET /api/operator/bio-gap-map/summary?narrator_id=N1
      One-shot rollup: completeness + recently_asked + suggested_asks
      (top 20) + conflicts + creep telemetry. The dashboard refreshes
      this on a polling timer.

  GET /api/operator/bio-gap-map/recently-asked?narrator_id=N1&limit=20
      The narrator's anchored-ask history, newest first. Each entry
      carries the matched_anchor + outcome classification.

  GET /api/operator/bio-gap-map/suggested-asks?narrator_id=N1
      Full list of high-value empty fields without current chapter
      anchor (summary endpoint caps at 20).

  GET /api/operator/bio-gap-map/conflicts?narrator_id=N1
      Conflicted bio_facts pairs grouped by field_key for operator
      review.

  GET /api/operator/bio-gap-map/telemetry?narrator_id=N1
      Creep telemetry rollup with warning classification (green /
      amber / red) per WO §Defense 1 thresholds.

BACKEND GATE: every endpoint short-circuits to 404 unless
HORNELORE_OPERATOR_BIO_GAP_MAP=1 is set in the server env. Default-OFF
mirrors operator_eval_harness + operator_story_review + operator_bio_editor.

LAW 3 INFRASTRUCTURE: imports stdlib + fastapi + ..services.bio_gap_map
only. No extract.py or chat_ws.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

from ..services import bio_gap_map


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/bio-gap-map",
                   tags=["operator", "bio-gap-map"])


# ─────────────────────────────────────────────────────────────────────
# Backend gate
# ─────────────────────────────────────────────────────────────────────


def _enabled() -> bool:
    """Default-OFF gate. Enable with HORNELORE_OPERATOR_BIO_GAP_MAP=1."""
    return os.environ.get(
        "HORNELORE_OPERATOR_BIO_GAP_MAP", "0",
    ).strip().lower() in ("1", "true", "yes", "on")


def _require_enabled() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=404,
            detail="bio gap map surface disabled",
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────


@router.get("/summary")
def get_summary(
    narrator_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    """One-shot dashboard rollup. Bundles all five sections so the FE
    makes one round trip per refresh."""
    _require_enabled()
    try:
        summary = bio_gap_map.full_summary(narrator_id)
        summary["fetched_at"] = _now_iso()
        return summary
    except Exception as exc:
        logger.exception("[bio_gap_map] summary failed")
        raise HTTPException(
            status_code=500, detail=f"summary failed: {exc}",
        )


@router.get("/recently-asked")
def get_recently_asked(
    narrator_id: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
) -> Dict[str, Any]:
    """Narrator's anchored-ask history, newest first."""
    _require_enabled()
    try:
        items = bio_gap_map.recently_asked(narrator_id, limit=limit)
        return {
            "narrator_id": narrator_id,
            "items": [i.to_dict() for i in items],
            "count": len(items),
            "fetched_at": _now_iso(),
        }
    except Exception as exc:
        logger.exception("[bio_gap_map] recently_asked failed")
        raise HTTPException(
            status_code=500, detail=f"recently_asked failed: {exc}",
        )


@router.get("/suggested-asks")
def get_suggested_asks(
    narrator_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    """Full list of high-value gaps without current chapter anchor."""
    _require_enabled()
    try:
        items = bio_gap_map.suggested_asks(narrator_id)
        return {
            "narrator_id": narrator_id,
            "items": [i.to_dict() for i in items],
            "count": len(items),
            "fetched_at": _now_iso(),
        }
    except Exception as exc:
        logger.exception("[bio_gap_map] suggested_asks failed")
        raise HTTPException(
            status_code=500, detail=f"suggested_asks failed: {exc}",
        )


@router.get("/conflicts")
def get_conflicts(
    narrator_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    """Conflicted bio_facts pairs grouped by field_key."""
    _require_enabled()
    try:
        items = bio_gap_map.list_conflicts(narrator_id)
        return {
            "narrator_id": narrator_id,
            "items": [i.to_dict() for i in items],
            "count": len(items),
            "fetched_at": _now_iso(),
        }
    except Exception as exc:
        logger.exception("[bio_gap_map] conflicts failed")
        raise HTTPException(
            status_code=500, detail=f"conflicts failed: {exc}",
        )


@router.get("/telemetry")
def get_telemetry(
    narrator_id: str = Query(..., min_length=1),
    window: int = Query(5, ge=1, le=50),
) -> Dict[str, Any]:
    """Defense 1 creep telemetry rollup with warning classification."""
    _require_enabled()
    try:
        telemetry = bio_gap_map.creep_telemetry_rollup(
            narrator_id, window=window,
        )
        telemetry["fetched_at"] = _now_iso()
        return telemetry
    except Exception as exc:
        logger.exception("[bio_gap_map] telemetry failed")
        raise HTTPException(
            status_code=500, detail=f"telemetry failed: {exc}",
        )


__all__ = ["router"]
