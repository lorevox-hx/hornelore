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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Stub function signatures (Phase 1A Commit 2 fills these in) ───────────

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
    returns control to the LLM path. Phase 1A Commit 2 fills in the
    body."""
    raise RuntimeError(
        "story preservation service not implemented until "
        "WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 2"
    )


def update_placement(
    candidate_id: str,
    *,
    age_bucket: Optional[str] = None,
    era_candidates: Optional[List[str]] = None,
    estimated_year_low: Optional[int] = None,
    estimated_year_high: Optional[int] = None,
    confidence: Optional[str] = None,
    scene_anchors: Optional[List[str]] = None,
) -> None:
    """Update placement metadata after Lori asks the bucket question
    and the narrator answers. Does NOT touch extraction-side fields."""
    raise RuntimeError(
        "story preservation service not implemented until "
        "WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 2"
    )


def get_unreviewed(
    narrator_id: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Read accessor for the operator review queue (LAW 4). Returns
    unreviewed candidates ordered by `created_at DESC`. Does NOT touch
    extracted_fields beyond passing them through."""
    raise RuntimeError(
        "story preservation service not implemented until "
        "WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 2"
    )


def get_candidate(candidate_id: str) -> Optional[Dict[str, Any]]:
    """Single-row read for the operator review detail view."""
    raise RuntimeError(
        "story preservation service not implemented until "
        "WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 2"
    )


__all__ = [
    "preserve_turn",
    "update_placement",
    "get_unreviewed",
    "get_candidate",
]
