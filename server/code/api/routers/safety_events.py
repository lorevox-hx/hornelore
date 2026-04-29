"""WO-LORI-SAFETY-INTEGRATION-01 Phase 3 — operator notification surface.

Four endpoints, all operator-only — Bug Panel consumes them. There is
no narrator-side route or UI surface for any of these:

  GET  /api/operator/safety-events       — list recent events (filterable)
  GET  /api/operator/safety-events/count — unacked badge count (cheap poll)
  GET  /api/operator/safety-events/digest — by-category + by-narrator counts
  POST /api/operator/safety-events/{id}/acknowledge — dismiss banner

Per WO-LORI-SAFETY-INTEGRATION-01 spec:
  - Never narrator-visible.
  - No severity scores. No clinical risk ranks. No longitudinal trends.
  - Operator gets: category + matched phrase + 200-char excerpt + time.
  - That's enough context to decide "check on the narrator" or "it's a
    REFLECTIVE past-tense mention, no action needed."

Backend gate (Phase 3a): every endpoint short-circuits to 404 unless
`HORNELORE_OPERATOR_SAFETY_EVENTS=1` is set in the server env. This
prevents drive-by external probing — the route doesn't even advertise
itself when disabled. Production / parent-session-ready operators set
the flag in `.env` after they've wired up the Bug Panel banner UI
(Phase 3b).

When Lorevox adopts these endpoints they'll get fronted with proper
operator-tab auth in addition to (or in place of) this env gate. For
local single-operator Hornelore, the env gate is the right boundary.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..db import (
    acknowledge_safety_event,
    count_unacked_safety_events,
    list_safety_events,
    safety_events_digest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/operator/safety-events", tags=["operator", "safety"])


class AckRequest(BaseModel):
    acknowledged_by: Optional[str] = None


def _operator_safety_enabled() -> bool:
    """Backend gate: every endpoint is 404 unless this env flag is on.
    Default-OFF so the route doesn't advertise itself; operator opts in
    by setting `HORNELORE_OPERATOR_SAFETY_EVENTS=1` in .env after Phase 3b
    Bug Panel UI is wired."""
    return os.getenv("HORNELORE_OPERATOR_SAFETY_EVENTS", "0").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _require_operator_safety_enabled() -> None:
    """Raise 404 (not 403) when the backend gate is off so an external
    probe can't distinguish 'endpoint exists but you can't have it' from
    'endpoint doesn't exist'."""
    if not _operator_safety_enabled():
        raise HTTPException(status_code=404, detail="Not found")


def _sanitize_event(row: dict) -> dict:
    """Belt-and-suspenders excerpt clamp at the route boundary. The DB
    layer already truncates `turn_excerpt` to 200 chars on insert, but
    enforce here too so the operator surface contract holds even if a
    future writer bypasses the DB helper. Trailing ellipsis on truncate
    so the operator can see the row was cut."""
    out = dict(row or {})
    excerpt = str(out.get("turn_excerpt") or "")
    if len(excerpt) > 200:
        out["turn_excerpt"] = excerpt[:200].rstrip() + "…"
    return out


@router.get("")
def list_events(
    person_id: Optional[str] = Query(None, description="Filter to one narrator"),
    since: Optional[str] = Query(None, description="ISO datetime; only events after this"),
    unacked_only: bool = Query(False, description="Hide already-acknowledged events"),
    limit: int = Query(50, ge=1, le=200, description="Max rows (1-200, default 50)"),
):
    """Return recent safety events for the operator review surface.

    Events come back most-recent-first. Each row carries:
      id, session_id, person_id, category, matched_phrase, turn_excerpt,
      created_at, acknowledged_at, acknowledged_by.
    """
    _require_operator_safety_enabled()
    events = list_safety_events(
        person_id=person_id,
        since_iso=since,
        unacked_only=unacked_only,
        limit=limit,
    )
    events = [_sanitize_event(e) for e in events]
    return {"events": events, "count": len(events)}


@router.get("/count")
def count_unacked(
    person_id: Optional[str] = Query(None, description="Filter to one narrator"),
):
    """Lightweight badge count for Bug Panel polling. Returns just the
    unacked-event count so the UI can decide whether to re-fetch the
    full event list."""
    _require_operator_safety_enabled()
    n = count_unacked_safety_events(person_id=person_id)
    return {"unacknowledged": n}


@router.get("/digest")
def get_digest(
    since: Optional[str] = Query(None, description="ISO datetime; only events after this"),
    person_id: Optional[str] = Query(None, description="Filter to one narrator"),
):
    """Between-session digest — per-category and per-narrator counts.

    Operator uses this for "since last login" awareness without scrolling
    the full event list. NO scores, NO severity, NO trends — just counts.
    """
    _require_operator_safety_enabled()
    # Between-session operator-awareness snapshot only.
    # Do not expose time-series trends, clinical scores, severity ranks,
    # diagnostic labels, or longitudinal risk profiles. Operator cares
    # about "did anything fire that I haven't seen?" — counts answer that.
    return safety_events_digest(since_iso=since, person_id=person_id)


@router.post("/{event_id}/acknowledge")
def ack_event(event_id: str, body: Optional[AckRequest] = None):
    """Mark a safety event as seen-by-operator. Idempotent — re-ack on
    a previously-acked event returns success but doesn't update the
    timestamp (preserves first-ack record)."""
    _require_operator_safety_enabled()
    acknowledged_by = (body.acknowledged_by if body else None) or "operator"
    ok = acknowledge_safety_event(event_id, acknowledged_by=acknowledged_by)
    if not ok:
        # Already acked OR id doesn't exist — both return 200 with a flag
        # so the UI doesn't have to distinguish. The front-end behavior
        # is the same: remove the banner.
        return {"event_id": event_id, "acknowledged": False, "reason": "already_acked_or_missing"}
    return {"event_id": event_id, "acknowledged": True}
