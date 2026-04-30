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

from fastapi import APIRouter, HTTPException, Query

from ..services import story_preservation

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


__all__ = ["router"]
