"""Trip story capture — WO-TRIP-LORI-ANSWER-CAPTURE-01 Step 1.

The REVERSE flow of trip_interview_context:

    trip_interview_context   Travel Doc  ->  Lori prompt context (read)
    trip_story_capture       Lori/narrator conversation  ->  Travel Doc
                             candidate note (write, review-only)

When Lori asks a trip-scoped question and the narrator answers meaningfully,
this service SAVES that answer as a CANDIDATE ``trip_location_notes`` row so
the operator can review it in Travel Doc. It is candidate material only:

    include_in_memoir            = 0   (never auto-promoted to the memoir)
    include_in_interview_context = 0   (never auto-fed back to Lori)

STEP 1 IS THE SERVICE + TESTS ONLY. Nothing here is wired into chat_ws yet
(that is a later step, with separate approval). This module:
  - takes EXPLICIT inputs (nothing pulled from globals / runtime71),
  - does NOT mutate runtime71, dispatch prompts, or run extraction,
  - never writes final memoir prose,
  - never infers image content / uses raw image vision,
  - never auto-promotes a note.

LAW 3: imports ONLY the trip data layer (trip_repository) + stdlib. It does
NOT import chat_ws, prompt_composer, extract, the Lori runtime, or any UI.
A build-gated isolation test enforces this.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from . import trip_repository

# ── Tunables ────────────────────────────────────────────────────────────────
_MIN_MEANINGFUL_WORDS = 3      # shorter than this = an acknowledgment, skip
_MAX_NOTE_CHARS = 4000         # generous cap; we store faithfully, don't rewrite
_MAX_TITLE_CHARS = 80          # clipped question snippet, operator-review context

# Prompt "kind" labels that indicate the previous Lori turn was about the trip.
_TRIP_SCOPED_KINDS = {
    "trip", "trip_scoped", "trip_narration", "trip_story", "trip_question",
    "travels", "travels_shelf", "photo", "photo_elicit", "trip_photo",
}

# Normalized replies that are never worth capturing on their own.
_TRIVIAL_PHRASES = {
    "yes", "no", "okay", "ok", "maybe", "sure", "yeah", "yep", "yup",
    "nope", "nah", "right", "correct", "true", "false", "fine", "huh",
    "i guess", "i dont know", "i do not know", "idk", "dunno", "not sure",
    "uh huh", "uhhuh", "mhm", "mmhmm", "mm hmm", "no idea", "nothing",
    "i dont remember", "i do not remember", "cant remember", "cannot remember",
}


# ── Text helpers ────────────────────────────────────────────────────────────
def _normalize(text: Optional[str]) -> str:
    """Lowercase, strip punctuation/quotes, collapse whitespace — for the
    trivial-reply check only. The stored note keeps the original text."""
    s = str(text or "").lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^\w\s']", " ", s)     # drop punctuation but keep apostrophes
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _light_clean(text: Optional[str]) -> str:
    """Faithful light cleanup for the stored note: collapse whitespace and
    strip surrounding quotes/space. Explicitly does NOT rewrite, summarize,
    or paraphrase — the operator reviews the narrator's own words."""
    s = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip().strip('"“”').strip()
    if len(s) > _MAX_NOTE_CHARS:
        s = s[:_MAX_NOTE_CHARS].rstrip() + " …"
    return s


def _is_trivial(narrator_text: str) -> bool:
    norm = _normalize(narrator_text).replace("'", "")
    if not norm:
        return True
    if norm in _TRIVIAL_PHRASES:
        return True
    if len(norm.split()) < _MIN_MEANINGFUL_WORDS:
        return True
    return False


# Narrator turns that are QUESTIONS to Lori, info requests, or meta-comments
# about the conversation are not memoir material — skip them (review 2026-07-09).
_LORI_DIRECTED_RX = re.compile(
    r"(?i)\b("
    r"can you|could you|would you|will you|do you know|you tell me|"
    r"tell me about|you know of|you know anything|you know about|"
    r"you explain|explain that|explain it|explain what|"
    r"what (is|was|are|were) (that|it|those|these|this)|"
    r"i asked you|you a question|answer (my|the) question|"
    r"you did ?n.?t answer|did you answer|"
    r"that.?s not what i (asked|meant|said)|not what i (asked|meant|said)|"
    r"i already (asked|told you)"
    r")\b"
)
_QUESTION_OPENERS = (
    "what", "who", "where", "when", "why", "how", "which", "can", "could",
    "would", "will", "do", "does", "did", "is", "are", "was", "were",
)


def _is_question_or_meta(narrator_text: str) -> bool:
    """True when the turn is mainly a question to Lori / a request for facts /
    a meta-correction about the conversation — not story material. Conservative:
    declarative narration (starts with a subject, no '?', no Lori-directed
    phrase) is never flagged, so real memories still capture."""
    raw = str(narrator_text or "").strip()
    if not raw:
        return False
    if raw.endswith("?"):                       # a direct question
        return True
    if _LORI_DIRECTED_RX.search(raw):           # request / meta-comment to Lori
        return True
    low = raw.lower()
    # question-word opener that also addresses Lori ("what did you say ...")
    first = re.split(r"\W+", low, 1)[0]
    if first in _QUESTION_OPENERS and re.search(r"\byou\b", low):
        return True
    return False


def _title_from_question(previous_lori_text: Optional[str]) -> Optional[str]:
    """A short label so the operator can see WHAT Lori asked. Not sanitized
    into the answer — this is display metadata for the review pile."""
    q = re.sub(r"\s+", " ", str(previous_lori_text or "")).strip()
    if not q:
        return None
    if len(q) > _MAX_TITLE_CHARS:
        q = q[:_MAX_TITLE_CHARS].rstrip() + "…"
    return q


# ── Trip-scope detection ────────────────────────────────────────────────────
def _collect_place_names(tree: Optional[Dict[str, Any]]) -> List[str]:
    """Region + stop names (lowercased) for the text heuristic."""
    names: List[str] = []
    if not tree:
        return names

    def _walk_stops(stops: List[Dict[str, Any]]) -> None:
        for s in stops:
            nm = s.get("location_name") or s.get("title")
            if nm:
                names.append(str(nm).lower())
            _walk_stops(s.get("children", []) or [])

    for r in tree.get("regions", []) or []:
        if r.get("title"):
            names.append(str(r["title"]).lower())
        _walk_stops(r.get("stops", []) or [])
    return names


def _mentions_a_place(text: Optional[str], place_names: List[str]) -> bool:
    if not text:
        return False
    low = str(text).lower()
    for nm in place_names:
        nm = nm.strip()
        if len(nm) < 3:
            continue
        if re.search(r"\b" + re.escape(nm) + r"\b", low):
            return True
    return False


def _is_trip_scoped(
    previous_prompt_kind: Optional[str],
    previous_lori_text: Optional[str],
    photo_scoped: bool,
    trip: Dict[str, Any],
    place_names: List[str],
) -> bool:
    """Deterministic: prior turn is trip-scoped if ANY of —
      - a VALID photo-based question (the photo link belongs to THIS trip —
        caller validates before passing photo_scoped=True), OR
      - previous_prompt_kind is a known trip-scoped kind, OR
      - the previous Lori text names the trip title or a region/stop.
    No evidence of trip scope => not trip-scoped (conservative)."""
    if photo_scoped:
        return True
    if previous_prompt_kind and str(previous_prompt_kind).strip().lower() in _TRIP_SCOPED_KINDS:
        return True
    title = str(trip.get("title") or "").lower()
    if title and len(title) >= 3 and previous_lori_text \
            and re.search(r"\b" + re.escape(title) + r"\b", str(previous_lori_text).lower()):
        return True
    if _mentions_a_place(previous_lori_text, place_names):
        return True
    return False


# ── Scope resolution ────────────────────────────────────────────────────────
def _resolve_scope(
    active_trip_id: str,
    active_trip_region_id: Optional[str],
    active_trip_stop_id: Optional[str],
    photo_link_id: Optional[str],
) -> Dict[str, Optional[str]]:
    """Return {scope, trip_region_id, trip_stop_id, source_ref_photo} using
    only ids that VALIDLY belong to this trip. Invalid ids are dropped to a
    broader scope rather than attached (never write a cross-trip FK)."""
    region_id: Optional[str] = None
    stop_id: Optional[str] = None
    source_ref_photo: Optional[str] = None

    # Photo scope (if the answer came from clicking a photo).
    if photo_link_id:
        link = trip_repository.photo_link_get(photo_link_id)
        if link and link.get("trip_id") == active_trip_id:
            source_ref_photo = "photo_link:" + str(photo_link_id)
            if link.get("trip_stop_id"):
                stop_id = link.get("trip_stop_id")
            if link.get("trip_region_id"):
                region_id = link.get("trip_region_id")

    # Explicit stop (validated to belong to the trip).
    if not stop_id and active_trip_stop_id:
        stop = trip_repository.stop_get(active_trip_stop_id)
        if stop and stop.get("trip_id") == active_trip_id:
            stop_id = active_trip_stop_id
            if not region_id and stop.get("trip_region_id"):
                region_id = stop.get("trip_region_id")

    # Explicit region (validated to belong to the trip).
    if not region_id and active_trip_region_id:
        if trip_repository.region_trip_id(active_trip_region_id) == active_trip_id:
            region_id = active_trip_region_id

    scope = "stop" if stop_id else ("region" if region_id else "trip")
    return {
        "scope": scope,
        "trip_region_id": region_id,
        "trip_stop_id": stop_id,
        "source_ref_photo": source_ref_photo,
    }


def _dedupe_existing(trip_id: str, source_ref: Optional[str]) -> Optional[str]:
    """If a lori-sourced note with the same source_ref already exists for this
    trip, return its id (so the caller can skip a duplicate insert)."""
    if not source_ref:
        return None
    for n in trip_repository.location_notes_list(trip_id):
        if n.get("source_type") == "lori" and n.get("source_ref") == source_ref:
            return n.get("id")
    return None


def _result(captured: bool, reason: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "captured": captured,
        "reason": reason,
        "note_id": None,
        "trip_id": None,
        "trip_region_id": None,
        "trip_stop_id": None,
        "source_ref": None,
        "scope": None,
    }
    out.update(extra)
    return out


# ── Public entry ────────────────────────────────────────────────────────────
def capture_trip_story_answer(
    person_id: Optional[str],
    active_trip_id: Optional[str],
    narrator_text: Optional[str],
    previous_lori_text: Optional[str] = None,
    previous_prompt_kind: Optional[str] = None,
    active_trip_region_id: Optional[str] = None,
    active_trip_stop_id: Optional[str] = None,
    photo_link_id: Optional[str] = None,
    conv_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Save a narrator's trip-scoped answer as a CANDIDATE trip_location_notes
    row (review-only), or explain why it was skipped.

    Returns a result dict — see _result(). ``captured`` is True only when a row
    was written (or an identical row already existed, reason='duplicate').

    This function is READ-then-WRITE on the trip data layer only. It never
    touches Lori runtime, prompts, extraction, memoir prose, or image pixels.
    """
    # 1. Gates that need no DB.
    if not active_trip_id:
        return _result(False, "no_active_trip")
    if not person_id:
        return _result(False, "no_person")

    # 2. Trip ownership.
    trip = trip_repository.trip_get(active_trip_id)
    if not trip:
        return _result(False, "trip_not_found")
    if trip.get("person_id") != person_id:
        return _result(False, "trip_not_owned")

    # 3. Prior Lori turn must have been trip-scoped. A photo link only counts
    #    as trip-scope evidence if it EXISTS and belongs to THIS trip — a link
    #    from another trip must not scope the turn on its own.
    photo_valid = False
    if photo_link_id:
        _link = trip_repository.photo_link_get(photo_link_id)
        photo_valid = bool(_link and _link.get("trip_id") == active_trip_id)
    tree = trip_repository.trip_tree(active_trip_id)
    place_names = _collect_place_names(tree)
    if not _is_trip_scoped(previous_prompt_kind, previous_lori_text,
                           photo_valid, trip, place_names):
        return _result(False, "not_trip_scoped")

    # 4. Skip trivial acknowledgments.
    if _is_trivial(narrator_text or ""):
        return _result(False, "trivial_reply")

    # 4b. Skip questions to Lori / info requests / meta-comments — not memoir.
    if _is_question_or_meta(narrator_text or ""):
        return _result(False, "direct_question_or_command")

    # 5. Resolve scope (validated ids only) + source_ref.
    scope = _resolve_scope(active_trip_id, active_trip_region_id,
                           active_trip_stop_id, photo_link_id)
    source_ref = scope["source_ref_photo"]
    if not source_ref:
        if turn_id:
            source_ref = "turn:" + str(turn_id)
        elif conv_id:
            source_ref = "conv:" + str(conv_id)

    # 6. Duplicate guard — ONLY on a strong per-answer identity (turn id or
    #    photo link). conv:<id> is shared by every turn in a conversation, so
    #    deduping on it would collapse all later answers into the first one.
    dedupe_ref = source_ref if (source_ref and (
        source_ref.startswith("turn:") or
        source_ref.startswith("photo_link:"))) else None
    existing = _dedupe_existing(active_trip_id, dedupe_ref)
    if existing:
        return _result(
            True, "duplicate",
            note_id=existing, trip_id=active_trip_id,
            trip_region_id=scope["trip_region_id"],
            trip_stop_id=scope["trip_stop_id"],
            source_ref=source_ref, scope=scope["scope"],
        )

    # 7. Write the candidate note — both promotion flags OFF.
    note_id = trip_repository.location_note_create(
        trip_id=active_trip_id,
        note_text=_light_clean(narrator_text),
        note_title=_title_from_question(previous_lori_text),
        trip_region_id=scope["trip_region_id"],
        trip_stop_id=scope["trip_stop_id"],
        source_type="lori",
        source_ref=source_ref,
        include_in_memoir=False,
        include_in_interview_context=False,
    )

    return _result(
        True, "meaningful_trip_answer",
        note_id=note_id, trip_id=active_trip_id,
        trip_region_id=scope["trip_region_id"],
        trip_stop_id=scope["trip_stop_id"],
        source_ref=source_ref, scope=scope["scope"],
    )


# ── Step 2 chat-turn gate (default-OFF flag; used by chat_ws) ────────────────

_FLAG = "HORNELORE_TRIP_STORY_CAPTURE"


def capture_enabled() -> bool:
    """Default-OFF. When off, chat_ws must not capture anything (byte-stable)."""
    return os.getenv(_FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def _capture_for_turn_impl(
    person_id: Optional[str],
    runtime71: Optional[Dict[str, Any]],
    narrator_text: Optional[str],
    previous_lori_text: Optional[str] = None,
    previous_prompt_kind: Optional[str] = None,
    photo_link_id: Optional[str] = None,
    conv_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Gate + capture for a single narrator chat turn. Safe to call every turn.

    Gates the flag + Travels-shelf-open here; everything else (active trip,
    ownership, trip-scope, trivial, scope validation, dedupe) is delegated to
    capture_trip_story_answer. Reads scope ids from runtime71.

    NON-FATAL by contract: any internal error returns an ``error`` result
    instead of raising, so a caller can wrap-or-not and the chat turn is never
    put at risk. Returns the same result shape as capture_trip_story_answer,
    plus ``flag_off`` / ``shelf_closed`` / ``error`` skip reasons.
    """
    try:
        if not capture_enabled():
            return _result(False, "flag_off")
        rt = runtime71 or {}
        if not rt.get("travels_shelf_open"):
            return _result(False, "shelf_closed")
        return capture_trip_story_answer(
            person_id=person_id,
            active_trip_id=rt.get("active_trip_id"),
            narrator_text=narrator_text,
            previous_lori_text=previous_lori_text,
            previous_prompt_kind=previous_prompt_kind,
            active_trip_region_id=rt.get("active_trip_region_id"),
            active_trip_stop_id=rt.get("active_trip_stop_id"),
            photo_link_id=photo_link_id or rt.get("active_photo_link_id"),
            conv_id=conv_id,
            turn_id=turn_id,
        )
    except Exception as exc:  # never let capture break the chat turn
        return _result(False, "error", error=str(exc))


# ── Last-status snapshot for operator visibility (Bug Panel / logs) ──────────
_LAST_STATUS: Dict[str, Any] = {
    "flag_on": False, "captured": None, "reason": None,
    "scope": None, "note_id": None,
}


def capture_for_turn(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Public gate — delegates to the impl and records a bounded last-status
    snapshot so an operator surface can show what the last capture did. Never
    raises (the impl is already non-fatal)."""
    res = _capture_for_turn_impl(*args, **kwargs)
    try:
        _LAST_STATUS.update({
            "flag_on": capture_enabled(),
            "captured": res.get("captured"),
            "reason": res.get("reason"),
            "scope": res.get("scope"),
            "note_id": res.get("note_id"),
        })
    except Exception:
        pass
    return res


def capture_status() -> Dict[str, Any]:
    """Read-only status for the Bug Panel: flag state + last capture result."""
    return {"flag_on": capture_enabled(), "last": dict(_LAST_STATUS)}
