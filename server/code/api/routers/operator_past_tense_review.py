"""WO-LORI-SAFETY-LLM-CLASSIFIER-01 (2026-06-14) — operator past-tense
flag review surface.

One read-only endpoint, operator-only (Bug Panel consumes it; no
narrator-side route, never linked from the chat UI):

  GET /api/operator/past-tense-flags
      Lists segment_flags rows where sensitive_category =
      "past_tense_ideation_acknowledged" across all sessions,
      newest-first. Optional ?limit= (default 50, hard max 200).
      Returns JSON: {"items": [...], "count": N, "fetched_at": ISO8601}

The shape is intentionally minimal — the operator review pattern
(decision = no_action / follow_up_outside_session /
convert_to_active_concern) is documented in the WO spec but ships in
a future iteration once the operator has lived with the read-only
view and told us what state transitions are actually useful. Mirror
of operator_story_review.py Phase 1B posture.

Backend gate: endpoint short-circuits to 404 unless
`HORNELORE_OPERATOR_PAST_TENSE_REVIEW=1` is set in the server env.
Default-OFF so the route doesn't advertise itself to outside probes
(same posture as operator_story_review and operator_eval_harness).

Why this exists (the WO context):
The classifier's past_tense_acknowledge route writes a segment_flag
with category="past_tense_ideation_acknowledged" when the narrator
discloses past-tense memoir ideation ("After Mom died in '78, there
was a year I didn't want to go on"). 988 is NOT dispatched — the
narrator is describing a completed past period, not present crisis.
Lori emits a brief deterministic acknowledgment and the chapter
continues. But the operator should still SEE that disclosure landed,
so they can check in with the narrator outside the session if they
choose. This endpoint is the operator's read window.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from .. import db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator", tags=["operator", "past-tense-review"])


# ── Backend gate ───────────────────────────────────────────────────────────

def _operator_past_tense_review_enabled() -> bool:
    """Default-OFF gate. Enable with HORNELORE_OPERATOR_PAST_TENSE_REVIEW=1."""
    return os.getenv("HORNELORE_OPERATOR_PAST_TENSE_REVIEW", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_enabled() -> None:
    """Raise 404 (not 403) when off — external probes can't tell
    'endpoint exists but disabled' from 'endpoint doesn't exist'.
    Same posture as operator_story_review + operator_eval_harness."""
    if not _operator_past_tense_review_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# ── Helpers ────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _shape_for_operator(row: Dict[str, Any]) -> Dict[str, Any]:
    """Trim raw DB row to what the operator panel actually renders.
    Avoid shipping any free-text narrator content here — the flag is
    metadata-only; the operator can drill into the session transcript
    through a different surface if they need the actual turn text."""
    return {
        "id": row.get("id"),
        "session_id": row.get("session_id"),
        "sensitive_category": row.get("sensitive_category"),
        "created_at": row.get("created_at"),
    }


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.get("/past-tense-flags")
def list_past_tense_flags(
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """List past_tense_ideation_acknowledged segment_flags newest-first."""
    _require_enabled()
    try:
        rows = db.get_segment_flags_by_category(
            sensitive_category="past_tense_ideation_acknowledged",
            limit=limit,
        )
    except Exception as exc:
        logger.warning("[operator-past-tense] db query failed: %s", exc)
        raise HTTPException(status_code=500, detail="db_query_failed")

    items = [_shape_for_operator(r) for r in rows]
    return {
        "items": items,
        "count": len(items),
        "fetched_at": _now_iso(),
    }
