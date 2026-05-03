"""WO-LORI-SESSION-AWARENESS-01 Phase 1c — Peek-at-Memoir read accessor.

═══════════════════════════════════════════════════════════════════════
  WHAT THIS IS
═══════════════════════════════════════════════════════════════════════

A single read accessor that pulls promoted truth + recent session
transcript + (future) memoir-section data into one structured dict
for use by the memory_echo composer.

Today, compose_memory_echo (prompt_composer.py:1191) reads from
runtime71 only — the UI is responsible for threading data into the
runtime payload. This works for profile fields the UI knows about
but doesn't surface the promoted_truth pipeline's results or
session-transcript context.

Phase 1c gives memory_echo a server-side accessor that pulls from
the canonical stores directly. The composer can opt in via runtime71
carrying a "peek_data" key (or by upstream code calling
build_peek_at_memoir() and merging the result).

═══════════════════════════════════════════════════════════════════════
  SAFETY: PHASE 5c FILTER APPLIED HERE
═══════════════════════════════════════════════════════════════════════

The recent-transcript portion is piped through
safety.filter_safety_flagged_turns() before being returned. Any
session turn carrying a sensitive segment_flag is dropped. This
satisfies WO-LORI-SAFETY-INTEGRATION-01 Phase 5c: distress is not
biography; safety-routed turns must not appear in "what I'm beginning
to understand about you" memory_echo summaries.

The filter is applied INSIDE this accessor (not in the caller) so
forgetting to filter is impossible — every consumer of
build_peek_at_memoir gets the safety-filtered transcript by
construction.

═══════════════════════════════════════════════════════════════════════
  WHAT IT IS NOT
═══════════════════════════════════════════════════════════════════════

  - NOT an LLM call. Pure DB reads + filter.
  - NOT a writer. Read-only accessor.
  - NOT a composer. Returns structured dict; compose_memory_echo
    formats it for narrator-facing surface.
  - NOT a cache. Each call hits the DB. If cache is needed later,
    add at the caller layer with a known TTL.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("lorevox.peek_at_memoir")


def build_peek_at_memoir(
    person_id: str,
    session_id: Optional[str] = None,
    transcript_limit: int = 20,
    promoted_limit: int = 200,
) -> Dict[str, Any]:
    """Read accessor for memory_echo. Returns structured dict combining:
      - promoted_truth: list of dicts from family_truth_promoted (most
        recent first, capped at promoted_limit)
      - recent_turns: filtered list from archive.read_transcript
        (capped at transcript_limit, sensitive turns dropped via
        safety.filter_safety_flagged_turns); empty when session_id
        is None
      - person_id, session_id (echoed for caller context)
      - sources_available: dict tracking which underlying sources
        produced data — useful for the composer's footer
        ("Based on: profile, session notes, …")
      - errors: list of strings; non-fatal source failures are
        captured here instead of raising. The composer can render
        the rest even if one source went down.

    Defensive: any underlying read that raises is caught + logged +
    captured as an entry in errors[]. The accessor never raises;
    callers always get a valid dict.

    Pure stdlib + lazy imports of db / archive / safety modules.
    LAW 3 — does NOT import from extract / prompt_composer /
    chat_ws / llm_api.
    """
    result: Dict[str, Any] = {
        "person_id": person_id,
        "session_id": session_id,
        "promoted_truth": [],
        "recent_turns": [],
        "sources_available": {
            "promoted_truth": False,
            "session_transcript": False,
        },
        "errors": [],
    }

    if not person_id or not str(person_id).strip():
        result["errors"].append("empty_person_id")
        return result

    # ── Promoted truth read ──
    try:
        from .. import db as _db
        promoted = _db.ft_list_promoted(person_id, limit=promoted_limit, offset=0)
        if promoted:
            result["promoted_truth"] = promoted
            result["sources_available"]["promoted_truth"] = True
    except Exception as exc:
        msg = f"promoted_truth_read_failed: {type(exc).__name__}: {exc}"
        logger.warning("[peek_at_memoir] %s person_id=%s", msg, person_id)
        result["errors"].append(msg)

    # ── Session transcript read (only if session_id given) ──
    if session_id:
        try:
            from .. import archive as _archive
            from ..safety import filter_safety_flagged_turns as _filter_sensitive
            raw_turns = _archive.read_transcript(person_id=person_id, session_id=session_id)
            # Apply Phase 5c safety filter — drops any turn marked sensitive.
            filtered = _filter_sensitive(raw_turns or [])
            # Cap to most recent transcript_limit; transcripts are
            # append-only so most-recent = tail of list.
            if filtered:
                result["recent_turns"] = filtered[-transcript_limit:]
                result["sources_available"]["session_transcript"] = True
        except Exception as exc:
            msg = f"session_transcript_read_failed: {type(exc).__name__}: {exc}"
            logger.warning(
                "[peek_at_memoir] %s person_id=%s session_id=%s",
                msg, person_id, session_id,
            )
            result["errors"].append(msg)

    return result


def summarize_for_runtime(peek_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compress the full Peek-at-Memoir payload into a smaller dict
    suitable for inclusion in runtime71 (the runtime payload threaded
    through chat_ws → compose_system_prompt → compose_memory_echo).

    The full payload may contain hundreds of promoted-truth rows + a
    full session transcript; runtime71 should stay compact. This
    helper extracts:
      - top-N promoted facts grouped by subject (narrator-facing
        surface format: "subject + field + approved_value")
      - the most recent ~5 narrator turns (just user-role, just
        text content) for echo grounding

    Returns a dict shaped for direct merge into runtime71. Keys:
      promoted_facts, recent_user_turns, sources_used.
    """
    out: Dict[str, Any] = {
        "promoted_facts": [],
        "recent_user_turns": [],
        "sources_used": [],
    }
    if not isinstance(peek_data, dict):
        return out

    # Promoted facts — group by subject_name, keep most recent per (subject, field)
    promoted = peek_data.get("promoted_truth") or []
    seen_keys: set = set()
    for row in promoted:
        if not isinstance(row, dict):
            continue
        subject = (row.get("subject_name") or "self").strip() or "self"
        field = (row.get("field") or "").strip()
        approved = (row.get("approved_value") or "").strip()
        if not field or not approved:
            continue
        key = (subject, field)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out["promoted_facts"].append({
            "subject": subject,
            "field": field,
            "value": approved,
        })

    # Recent user turns — last ~5 user-role text events
    recent = peek_data.get("recent_turns") or []
    user_turns: List[str] = []
    for turn in reversed(recent):  # walk newest first
        if not isinstance(turn, dict):
            continue
        if turn.get("role") != "user":
            continue
        text = (turn.get("content") or turn.get("text") or "").strip()
        if not text:
            continue
        user_turns.append(text)
        if len(user_turns) >= 5:
            break
    # Reverse back to chronological order for the runtime field
    out["recent_user_turns"] = list(reversed(user_turns))

    # Sources used — for the composer footer
    sources = peek_data.get("sources_available") or {}
    if sources.get("promoted_truth"):
        out["sources_used"].append("promoted truth")
    if sources.get("session_transcript"):
        out["sources_used"].append("session transcript")

    return out


__all__ = [
    "build_peek_at_memoir",
    "summarize_for_runtime",
]
