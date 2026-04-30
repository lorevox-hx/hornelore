"""WO-LORI-STORY-CAPTURE-01 Phase 1A — story preservation service (Path 1).

═══════════════════════════════════════════════════════════════════════
  LAW 3 [INFRASTRUCTURE]: Preservation is guaranteed; extraction is
  best-effort. The code path for preservation does NOT call the
  extractor. The extractor does NOT block preservation.

  This module is the embodiment of that rule. It must:
    1. depend only on filesystem + sqlite + pre-existing STT output
    2. import zero modules from the extraction stack
       (server.code.api.routers.extract, server.code.api.routers.llm_*,
       any prompt_composer / few-shot / extractor helper)
    3. complete its writes synchronously; the chat_ws turn handler
       awaits this BEFORE firing extraction (which may fail freely)

  The build gate that enforces this rule lives in
  `tests/test_story_preservation_isolation.py`. That test parses this
  file's AST, follows imports transitively, and FAILS THE BUILD if
  any reachable module is in the extraction-stack subgraph.

  If a future patch needs extraction-side data inside preservation,
  the answer is NOT to import it here. The answer is:
    * extraction writes back to story_candidates.extracted_fields
      via a separate accessor in db.py
    * preservation reads its own row from story_candidates if it
      needs anything

  See WO-LORI-STORY-CAPTURE-01_Spec.md §0.5 (golfball architecture):
  this service is the WINDINGS layer. The cover (extraction, prompt)
  never reaches in to overwrite the windings.
═══════════════════════════════════════════════════════════════════════

Phase 1A Commit 1 lands this module as a STUB. Function signatures are
declared with `RuntimeError` bodies (per ChatGPT review pass 2 — louder
than NotImplementedError if anything calls them during startup).

Phase 1A Commit 2 fills in the bodies. The build gate (isolation test)
is in place from Commit 1 forward, so any future commit that adds an
extraction import to this file will fail CI before it can land.
"""
from __future__ import annotations

# DELIBERATE IMPORT POLICY — read this before adding any import below.
# Allowed: stdlib, sqlite3, pathlib, uuid, json, logging, typing, time,
#          datetime, hashlib, re, os.
# Allowed (project): nothing inside `server.code.api.routers` other than
#                    audio archive helpers IF needed in Commit 2 (TBD;
#                    review against the LAW 3 build gate when it's
#                    added).
# Forbidden: anything in the extraction stack — extract.py, prompt_composer,
#            llm_*, any few-shot or extraction helper module.
#
# The isolation test enumerates the forbidden list and walks imports
# transitively. If you find yourself wanting to add a forbidden import
# here, stop and re-read §0.5 of the WO. Path 1 cannot reach into
# Path 2.

import logging
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

# Allowed project-internal imports:
#   - server.code.api.db (sibling module — accessor functions only;
#     does NOT route through extract.py)
#   - server.code.api.services.age_arithmetic (sibling — pure functions)
# Both are checked by the LAW 3 isolation test transitively. db.py
# imports many things including extract via OTHER routers, BUT the
# specific accessors we call (story_candidate_*) live in db.py itself
# and don't reach into extraction. The isolation test walks the full
# transitive graph from THIS file; if it ever turns red because a db.py
# module-level import pulls extraction in, the build fails before
# preservation can be coupled.
from .. import db as _db
from . import age_arithmetic

logger = logging.getLogger(__name__)


# ── Path 1 entry point ────────────────────────────────────────────────────

def preserve_turn(
    narrator_id: str,
    transcript: str,
    *,
    audio_clip_path: Optional[str] = None,
    audio_duration_sec: Optional[float] = None,
    word_count: Optional[int] = None,
    trigger_reason: str,
    scene_anchor_count: int = 0,
    session_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> str:
    """Path 1 entry point. Persists a story_candidate row. Returns the
    new candidate id. Synchronous — must complete before the caller
    returns control to the LLM path.

    LAW 3: this function MUST succeed even if extraction is unavailable.
    It depends only on the local sqlite DB (and a fresh UUID). It does
    NOT call the extractor, the LLM, the prompt composer, or any
    extraction-stack module."""
    if not narrator_id:
        raise ValueError("narrator_id required")
    if not transcript or not transcript.strip():
        raise ValueError("transcript must be a non-empty string")

    # WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 3b — idempotency.
    # chat_ws may re-fire preservation on reconnect/retry; if the
    # narrator already has a candidate for this turn_id, return the
    # existing id instead of writing a duplicate. Application-level
    # check (no UNIQUE constraint on the schema yet) — the chat path
    # is single-event-loop per session so a race here is extremely
    # unlikely. If it ever becomes a real concern, promote to a
    # UNIQUE INDEX in a follow-up migration.
    if turn_id:
        existing = _db.story_candidate_get_by_turn(narrator_id, turn_id)
        if existing is not None:
            existing_id = existing.get("id")
            logger.info(
                "[preserve] dedupe-skip narrator=%s turn_id=%s existing=%s",
                narrator_id, turn_id, existing_id,
            )
            return existing_id  # type: ignore[return-value]

    candidate_id = str(uuid.uuid4())

    # Compute word_count if not provided. Cheap, robust to STT noise
    # because we only need an order-of-magnitude signal.
    if word_count is None:
        word_count = len(transcript.split())

    # The initial confidence floor is determined by the trigger that
    # got us here. full_threshold turns are 'medium' (long, anchored
    # narrative). borderline_scene_anchor turns are 'low' (short but
    # anchor-rich). manual triggers also default to 'low' until an
    # operator says otherwise.
    initial_confidence = "medium" if trigger_reason == "full_threshold" else "low"

    try:
        _db.story_candidate_insert(
            candidate_id=candidate_id,
            narrator_id=narrator_id,
            transcript=transcript,
            audio_clip_path=audio_clip_path,
            audio_duration_sec=audio_duration_sec,
            word_count=int(word_count) if word_count is not None else None,
            trigger_reason=trigger_reason,
            scene_anchor_count=int(scene_anchor_count or 0),
            session_id=session_id,
            conversation_id=conversation_id,
            turn_id=turn_id,
            era_candidates=[],
            age_bucket=None,
            estimated_year_low=None,
            estimated_year_high=None,
            confidence=initial_confidence,
            scene_anchors=[],
        )
    except Exception:
        logger.exception(
            "[preserve][CRITICAL] story preservation insert failed for "
            "narrator=%s trigger=%s — LAW 3 violation surface",
            narrator_id, trigger_reason,
        )
        raise

    logger.info(
        "[preserve] candidate_id=%s narrator=%s trigger=%s words=%s anchors=%s",
        candidate_id, narrator_id, trigger_reason,
        word_count, scene_anchor_count,
    )
    return candidate_id


# ── Placement update (after the bucket question) ──────────────────────────

def update_placement(
    candidate_id: str,
    *,
    age_bucket: Optional[str] = None,
    era_candidates: Optional[List[str]] = None,
    estimated_year_low: Optional[int] = None,
    estimated_year_high: Optional[int] = None,
    confidence: Optional[str] = None,
    scene_anchors: Optional[List[str]] = None,
    narrator_dob: Optional[date] = None,
) -> None:
    """Update placement metadata after Lori asks the bucket question
    and the narrator answers.

    If `narrator_dob` is supplied AND `age_bucket` is, the year range
    is computed via age_arithmetic and overrides any caller-supplied
    estimated_year_*. era_candidates is similarly auto-populated from
    the bucket if the caller didn't pass one explicitly.

    Does NOT touch extraction-side or review-side columns."""
    if not candidate_id:
        raise ValueError("candidate_id required")

    # Auto-derive year range and era_candidates from DOB + bucket if
    # the caller gave us those inputs. Caller-supplied values win when
    # explicitly passed.
    norm_bucket = age_arithmetic.normalize_bucket(age_bucket)

    if norm_bucket and narrator_dob is not None:
        derived_low, derived_high = age_arithmetic.estimate_year_from_age_bucket(
            narrator_dob, norm_bucket
        )
        if estimated_year_low is None and derived_low is not None:
            estimated_year_low = derived_low
        if estimated_year_high is None and derived_high is not None:
            estimated_year_high = derived_high

    if norm_bucket and era_candidates is None:
        derived_eras = age_arithmetic.bucket_to_era_candidates(norm_bucket)
        if derived_eras:
            era_candidates = derived_eras

    _db.story_candidate_update_placement(
        candidate_id,
        age_bucket=norm_bucket,
        era_candidates=era_candidates,
        estimated_year_low=estimated_year_low,
        estimated_year_high=estimated_year_high,
        confidence=confidence,
        scene_anchors=scene_anchors,
    )


# ── Read accessors (operator review surface) ──────────────────────────────

def get_unreviewed(
    narrator_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Read accessor for the operator review queue (LAW 4). Returns
    unreviewed candidates ordered by `created_at DESC`. Does NOT touch
    extracted_fields beyond passing them through. Optional narrator_id
    filter."""
    return _db.story_candidate_list_unreviewed(narrator_id=narrator_id, limit=limit)


def get_candidate(candidate_id: str) -> Optional[Dict[str, Any]]:
    """Single-row read for the operator review detail view. Returns
    None if not found."""
    if not candidate_id:
        return None
    return _db.story_candidate_get(candidate_id)


__all__ = [
    "preserve_turn",
    "update_placement",
    "get_unreviewed",
    "get_candidate",
]
