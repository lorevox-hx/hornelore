"""WO-LORI-WITNESS-FOLLOWUP-BANK-01 — operator surface.

Read-only Bug Panel endpoints for inspecting the per-session follow-up
bank. Operator can:

  - List unanswered banked questions per session
  - List ALL banked questions (asked + answered + open) for forensics
  - Mark a banked question as answered (e.g. when narrator addresses
    the topic in a later turn but Lori didn't auto-flush)
  - Fire one banked question on demand (operator-click flush)

Gated behind HORNELORE_OPERATOR_FOLLOWUP_BANK env flag (default off →
404). Mirrors the existing operator_eval_harness / operator_story_review
posture so the surface doesn't advertise itself.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/operator/followup-bank", tags=["operator-followup-bank"])


def _enabled() -> bool:
    return os.getenv("HORNELORE_OPERATOR_FOLLOWUP_BANK", "0") in ("1", "true", "True")


def _gate_or_404() -> None:
    if not _enabled():
        raise HTTPException(
            status_code=404,
            detail="follow-up bank operator surface disabled (set HORNELORE_OPERATOR_FOLLOWUP_BANK=1)",
        )


class MarkAnsweredRequest(BaseModel):
    banked_id: str
    answered: bool = True


@router.get("/session/{session_id}/unanswered")
def get_unanswered(session_id: str) -> Dict[str, Any]:
    """Return all unanswered, not-yet-asked banked questions for a
    session, ordered by priority (1 first)."""
    _gate_or_404()
    try:
        from ..db import followup_bank_get_unanswered
        rows = followup_bank_get_unanswered(session_id)
    except Exception as exc:
        logger.warning("[operator-followup-bank] unanswered read failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"db read failed: {exc}")
    return {
        "session_id": session_id,
        "count": len(rows),
        "questions": rows,
    }


@router.get("/session/{session_id}/all")
def get_all(session_id: str) -> Dict[str, Any]:
    """Return ALL banked questions for a session (asked, answered, open).
    Useful for forensics — what doors did Lori see this session?"""
    _gate_or_404()
    try:
        from ..db import followup_bank_get_all
        rows = followup_bank_get_all(session_id)
    except Exception as exc:
        logger.warning("[operator-followup-bank] all read failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"db read failed: {exc}")
    open_n = sum(1 for r in rows if not r.get("answered") and r.get("asked_at_turn") is None)
    asked_n = sum(1 for r in rows if r.get("asked_at_turn") is not None)
    answered_n = sum(1 for r in rows if r.get("answered"))
    return {
        "session_id": session_id,
        "count": len(rows),
        "open": open_n,
        "asked": asked_n,
        "answered": answered_n,
        "questions": rows,
    }


@router.post("/mark-answered")
def mark_answered(req: MarkAnsweredRequest) -> Dict[str, Any]:
    """Flip answered flag on a banked question. Operator UI calls this
    when a narrator addresses the topic in a later turn but Lori did
    not auto-flush. Idempotent — re-marking is fine."""
    _gate_or_404()
    try:
        from ..db import followup_bank_mark_answered, followup_bank_get_by_id
        followup_bank_mark_answered(req.banked_id, answered=req.answered)
        updated = followup_bank_get_by_id(req.banked_id)
    except Exception as exc:
        logger.warning("[operator-followup-bank] mark-answered failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"db write failed: {exc}")
    if updated is None:
        raise HTTPException(status_code=404, detail=f"banked id {req.banked_id} not found")
    logger.info(
        "[operator-followup-bank] marked answered=%s id=%s session=%s",
        req.answered, req.banked_id, updated.get("session_id"),
    )
    return {"ok": True, "question": updated}


@router.get("/summary")
def summary(limit: int = Query(default=20, ge=1, le=200)) -> Dict[str, Any]:
    """Top-level summary across recent sessions. Lightweight read for
    Bug Panel widget; returns top N sessions by unanswered count."""
    _gate_or_404()
    try:
        from ..db import init_db, _connect
        init_db()
        con = _connect()
        try:
            cur = con.execute(
                "SELECT session_id, "
                "       SUM(CASE WHEN answered=0 AND asked_at_turn IS NULL THEN 1 ELSE 0 END) AS open_count, "
                "       SUM(CASE WHEN asked_at_turn IS NOT NULL THEN 1 ELSE 0 END) AS asked_count, "
                "       SUM(CASE WHEN answered=1 THEN 1 ELSE 0 END) AS answered_count, "
                "       MAX(updated_at) AS last_updated "
                "FROM follow_up_bank "
                "GROUP BY session_id "
                "ORDER BY open_count DESC, last_updated DESC "
                "LIMIT ?;",
                (int(limit),),
            )
            rows = [
                {
                    "session_id": r[0],
                    "open": int(r[1] or 0),
                    "asked": int(r[2] or 0),
                    "answered": int(r[3] or 0),
                    "last_updated": r[4],
                }
                for r in cur.fetchall()
            ]
        finally:
            con.close()
    except Exception as exc:
        logger.warning("[operator-followup-bank] summary read failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"db read failed: {exc}")
    return {"sessions": rows, "count": len(rows)}
