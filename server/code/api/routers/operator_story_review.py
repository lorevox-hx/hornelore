"""WO-LORI-STORY-CAPTURE-01 Phase 1B — minimal operator story-candidate review surface.

One endpoint, operator-only (Bug Panel consumes it; no narrator-side
route, no UI surface):

  GET /api/operator/story-candidates
      Lists unreviewed story_candidate rows newest-first. Optional
      ?narrator_id= filter. Optional ?limit= (default 50, hard max 200).
      Returns JSON: {"items": [...], "count": N, "fetched_at": ISO8601}

This is **read-only** by design (Phase 1B). Promote / refine / discard
actions land in Phase 3 once the operator has lived with the list and
told us what state-transitions actually need to exist.

Backend gate: endpoint short-circuits to 404 unless
`HORNELORE_OPERATOR_STORY_REVIEW=1` is set in the server env. Mirror
of operator_eval_harness.py — default-OFF so the route doesn't
advertise itself to outside probes.

LAW 4 STRUCTURAL: this is the parent-session blocker piece. Operators
need to be able to SEE captured story candidates before parent
sessions begin generating them in volume. A stack with
HORNELORE_STORY_CAPTURE=1 but no review surface is an invisible
preservation lane — the data is there but operators can't audit it.

Architectural note: this router calls into
`api.services.story_preservation.get_unreviewed()` which itself calls
`api.db.story_candidate_list_unreviewed()`. No extraction-stack
imports anywhere on the path — LAW 3 INFRASTRUCTURE preserved.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from .. import db as _db
from ..services import story_preservation, story_projection

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator", tags=["operator", "story-review"])


# ── Backend gate ───────────────────────────────────────────────────────────

def _operator_story_review_enabled() -> bool:
    """Default-OFF gate. Enable with `HORNELORE_OPERATOR_STORY_REVIEW=1`."""
    return os.getenv("HORNELORE_OPERATOR_STORY_REVIEW", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    """Raise 404 (not 403) when the gate is off so an external probe
    can't distinguish 'endpoint exists but you can't have it' from
    'endpoint doesn't exist'. Same posture as operator_eval_harness."""
    if not _operator_story_review_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _shape_for_operator(row: Dict[str, Any]) -> Dict[str, Any]:
    """Trim the raw row down to what the Bug Panel actually renders.
    Avoids shipping a 50KB transcript across the wire when only the
    first 200 chars are surfaced. Operator can drill into a single
    candidate later (Phase 3) for the full body."""
    transcript = row.get("transcript") or ""
    return {
        "id": row.get("id"),
        "narrator_id": row.get("narrator_id"),
        "trigger_reason": row.get("trigger_reason"),
        "scene_anchor_count": row.get("scene_anchor_count"),
        "word_count": row.get("word_count"),
        "confidence": row.get("confidence"),
        "era_candidates": row.get("era_candidates") or [],
        "age_bucket": row.get("age_bucket"),
        "estimated_year_low": row.get("estimated_year_low"),
        "estimated_year_high": row.get("estimated_year_high"),
        "transcript_preview": transcript[:200],
        "transcript_truncated": len(transcript) > 200,
        "extraction_status": row.get("extraction_status"),
        "review_status": row.get("review_status"),
        # Phase 3: the operator cannot review what it cannot address.
        # `review_version` is the optimistic-concurrency token every
        # mutation must echo back.
        "review_version": int(row.get("review_version") or 1),
        "placement_source": row.get("placement_source") or "unknown",
        "review_notes": row.get("review_notes"),
        "reviewed_by": row.get("reviewed_by"),
        "reviewed_at": row.get("reviewed_at"),
        "updated_at": row.get("updated_at"),
        "session_id": row.get("session_id"),
        "conversation_id": row.get("conversation_id"),
        "created_at": row.get("created_at"),
    }


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.get("/story-candidates")
def list_story_candidates(
    narrator_id: Optional[str] = Query(
        None,
        description="Filter to a single narrator. Omit for all narrators.",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Max rows to return. Hard-capped at 200 to keep payload manageable.",
    ),
) -> Dict[str, Any]:
    """Operator review queue — unreviewed story candidates newest-first.

    Phase 1B is intentionally minimal: list-only, no detail view, no
    actions. Bug Panel renders this; narrator-side never sees it.
    """
    _require_enabled()

    # Normalize narrator filter (treat empty/whitespace as "no filter").
    norm_narrator = (narrator_id or "").strip() or None

    try:
        rows = story_preservation.get_unreviewed(
            narrator_id=norm_narrator, limit=limit,
        )
    except Exception:
        # Loud-but-safe: log the full exception and return an empty
        # list so the Bug Panel renders gracefully even if the DB is
        # wedged. The operator will see the error in api.log.
        logger.exception(
            "[operator-story-review] get_unreviewed failed "
            "(narrator=%s limit=%s) — returning empty list",
            norm_narrator, limit,
        )
        rows = []

    items = [_shape_for_operator(r) for r in rows]
    return {
        "items": items,
        "count": len(items),
        "narrator_filter": norm_narrator,
        "limit": limit,
        "fetched_at": _now_iso(),
    }


# ── Phase 3: narrator-scoped review ────────────────────────────────────────
#
# WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit A (2026-08-17).
#
# The Phase 1B route above is kept exactly as it was: it is the
# unreviewed-only queue, it is what the Bug Panel has been calling, and
# breaking it to build the review surface would be gratuitous. The routes
# below are additive.
#
# All three share `_require_enabled()`, so the whole review surface is
# behind the one existing flag and answers 404 -- not 403 -- when it is off.


class StoryReviewAction(BaseModel):
    """One atomic review action.

    `narrator_id` and `review_version` are REQUIRED and are not
    conveniences. The narrator is part of the WHERE clause so a review can
    never land on another narrator's candidate; the version is the
    compare-and-write token, so two operators cannot silently overwrite
    each other. Omitting either would make the endpoint weaker than the
    accessor beneath it.
    """

    narrator_id: str = Field(..., min_length=1)
    review_version: int = Field(..., ge=1)
    review_status: Optional[str] = None
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    era_candidates: Optional[List[str]] = None
    estimated_year_low: Optional[int] = None
    estimated_year_high: Optional[int] = None
    placement_source: Optional[str] = None
    confidence: Optional[str] = None
    clear_year_range: bool = False


@router.get("/story-candidates/review")
def api_story_review_list(
    narrator_id: str = Query(..., min_length=1, description="Required narrator scope"),
    status: Optional[str] = Query(
        None, description="Comma-separated review statuses; omit for all"),
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    """The review list: narrator-scoped, status-filterable, with counts.

    `narrator_id` is REQUIRED here, unlike the Phase 1B queue. A review
    surface with no narrator is a cross-narrator read, and the counts
    below would be meaningless without a scope.
    """
    _require_enabled()
    wanted = [s.strip() for s in (status or "").split(",") if s.strip()]
    try:
        rows = _db.story_candidate_list_for_review(
            narrator_id, statuses=wanted or None, limit=limit,
        )
        counts = _db.story_candidate_status_counts(narrator_id)
        projection = story_projection.project_stories(narrator_id)
    except Exception:
        logger.exception(
            "[operator-story-review] review list failed (narrator=%s)", narrator_id)
        raise HTTPException(status_code=503, detail="story review unavailable")
    return {
        "items": [_shape_for_operator(r) for r in rows],
        "count": len(rows),
        "narrator_id": narrator_id,
        "status_filter": wanted,
        "counts": counts,
        # The canonical projection's own totals travel with the list, so
        # the operator surface and the Life Map cannot disagree about how
        # many stories are approved.
        "projection": {
            "status": projection.status,
            "counts": projection.counts,
        },
        "limit": limit,
        "fetched_at": _now_iso(),
    }


@router.get("/story-candidates/{candidate_id}")
def api_story_candidate_detail(
    candidate_id: str,
    narrator_id: str = Query(..., min_length=1),
) -> Dict[str, Any]:
    """Full candidate detail, including the preserved transcript.

    The transcript is served in full here and nowhere else -- the list
    routes carry a 200-character preview so a review queue does not ship
    fifty 50KB bodies.

    NO FILESYSTEM OR AUDIO STORAGE PATHS. `audio_clip_path` is a path on
    the operator's disk under DATA_DIR; the presence of audio is a fact
    the reviewer needs, the location of the file is not, and putting it on
    the wire would leak the archive layout to anything that can reach the
    browser.
    """
    _require_enabled()
    try:
        row = _db.story_candidate_get_for_narrator(candidate_id, narrator_id)
    except Exception:
        logger.exception("[operator-story-review] detail failed (%s)", candidate_id)
        raise HTTPException(status_code=503, detail="story review unavailable")
    if not row:
        raise HTTPException(status_code=404, detail="story candidate not found")
    shaped = _shape_for_operator(row)
    shaped["transcript"] = row.get("transcript") or ""
    shaped["scene_anchors"] = row.get("scene_anchors") or []
    shaped["extracted_fields"] = row.get("extracted_fields") or {}
    shaped["audio_present"] = bool(
        (row.get("audio_clip_path") or "").strip()
    )
    shaped["audio_duration_sec"] = row.get("audio_duration_sec")
    return {"item": shaped, "fetched_at": _now_iso()}


@router.patch("/story-candidates/{candidate_id}")
def api_story_review_apply(
    candidate_id: str,
    action: StoryReviewAction = Body(...),
) -> Dict[str, Any]:
    """Apply one review action atomically.

    409 on a stale `review_version`, carrying the CURRENT record so the
    operator surface can show what changed **without discarding the edit
    the operator just typed**. That is the difference between a conflict
    an operator can resolve and one that costs them their work.

    404 when the candidate is not this narrator's -- deliberately the same
    answer as "no such candidate", so supplying another narrator's id
    confirms nothing about it.
    """
    _require_enabled()
    try:
        row = _db.story_candidate_review_apply(
            candidate_id,
            action.narrator_id,
            action.review_version,
            review_status=action.review_status,
            review_notes=action.review_notes,
            reviewed_by=action.reviewed_by,
            era_candidates=action.era_candidates,
            estimated_year_low=action.estimated_year_low,
            estimated_year_high=action.estimated_year_high,
            placement_source=action.placement_source,
            confidence=action.confidence,
            clear_year_range=action.clear_year_range,
        )
    except _db.StoryCandidateNotFound:
        raise HTTPException(status_code=404, detail="story candidate not found")
    except _db.StoryReviewConflict as exc:
        raise HTTPException(status_code=409, detail={
            "error": "stale_review_version",
            "message": str(exc),
            "expected_version": exc.expected,
            "actual_version": exc.actual,
            "current": _shape_for_operator(exc.current),
        })
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("[operator-story-review] review apply failed (%s)", candidate_id)
        raise HTTPException(status_code=503, detail="story review unavailable")

    projection = story_projection.project_stories(action.narrator_id)
    return {
        "item": _shape_for_operator(row),
        "counts": _db.story_candidate_status_counts(action.narrator_id),
        "projection": {
            "status": projection.status,
            "counts": projection.counts,
        },
        "applied_at": _now_iso(),
    }


__all__ = ["router"]
