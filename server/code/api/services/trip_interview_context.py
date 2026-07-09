"""Trip interview context — WO-TRIP-INTERVIEW-CONTEXT-01.

READ-ONLY assembly of a compact, SAFE trip context block for a narrator
with an actively-open trip. Step 2 IS wired: chat_ws appends
``context_block_for_turn(...)`` to Lori's system prompt behind the
default-off flag ``HORNELORE_TRIP_INTERVIEW_CONTEXT`` (see below). This
module stays READ-ONLY — it never writes, dispatches, or mutates
runtime/session state; prompt_composer is untouched.

LAW 3: this module imports ONLY the trip data layer (trip_repository). It
does NOT import chat_ws, prompt_composer, extract, the Lori runtime, or any
UI. It is pure read:
  - no writes, no runtime71 mutation, no prompt dispatch, no extraction,
    no memory writes, no Travel Doc state writes.

Hard exclusions (never in the output):
  - operator-only provenance (confidence, assignment_method, source_type,
    meta_json, storage paths, ords)
  - non-narrator-ready photos (uses narrator_photo_links only)
  - raw source documents / raw source text — trip_sources has no
    interview-approval flag yet (only include_in_memoir), so NOTHING from
    sources is surfaced here. A dedicated flag must be added first.
  - notes NOT flagged include_in_interview_context=1
  - operator captions NOT flagged caption_approved_for_lori=1
    (narrator_caption — the narrator's OWN words from a photo-elicit
    session — is allowed by construction; WO-TRIP-PHOTO-CONTEXT-
    ENRICHMENT-FOR-LORI-01 Ph5)
  - operator context notes NOT flagged operator_context_approved_for_lori=1
  - any image/pixel interpretation
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from . import trip_repository

_MAX_NOTES = 8
_MAX_CAPTIONS = 10
_CLIP_WORDS = 40   # keep each note/caption compact
_MAX_CHARS = 240   # hard cap per sanitized value

_SYSTEM_RX = re.compile(r"(?i)\bsystem\s*:")


def _safe(text: Optional[str], words: int = _CLIP_WORDS) -> str:
    """Prompt-safety sanitizer for operator/narrator-entered text that will
    eventually sit inside Lori's system prompt (same spirit as the Travels
    shelf _promptSafe): neutralize bracket/directive characters, collapse
    newlines, and clip length so a note or caption can never smuggle an
    instruction into the prompt."""
    s = str(text or "")
    s = s.replace("[", "(").replace("]", ")")   # can't open a [SYSTEM: ...]
    s = s.replace("\r", " ").replace("\n", " ")
    s = _SYSTEM_RX.sub("system-", s)             # neutralize directive shape
    s = re.sub(r"\s+", " ", s).strip()
    parts = s.split(" ")
    if len(parts) > words:
        s = " ".join(parts[:words]) + " …"
    if len(s) > _MAX_CHARS:
        s = s[:_MAX_CHARS].rstrip() + " …"
    return s


# Back-compat alias (structured fields are sanitized too).
_clip = _safe


def _date_span(a: Optional[str], b: Optional[str]) -> str:
    return " to ".join([x for x in (a, b) if x])


def build_trip_interview_context(
    person_id: str,
    active_trip_id: str,
    active_trip_stop_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Return a compact, narrator-safe context dict for an open trip, or
    None when the trip is missing or not owned by ``person_id``.

    The dict carries structured fields plus a ready-to-inject ``text``
    rendering. Callers (Step 2) decide whether/when to use it — this
    function never dispatches anything."""
    if not person_id or not active_trip_id:
        return None
    trip = trip_repository.trip_get(active_trip_id)
    if not trip or trip.get("person_id") != person_id:
        return None
    tree = trip_repository.trip_tree(active_trip_id)
    if not tree:
        return None

    region_name: Dict[str, Optional[str]] = {}
    stop_name: Dict[str, Optional[str]] = {}
    stop_region: Dict[str, Optional[str]] = {}
    route: List[Dict[str, Any]] = []

    for r in tree.get("regions", []):
        region_name[r["id"]] = r.get("title")
        rstops: List[str] = []

        def _collect(slist: List[Dict[str, Any]], region=r, acc=rstops) -> None:
            for s in slist:
                stop_region[s["id"]] = region.get("title")
                nm = s.get("location_name") or s.get("title")
                stop_name[s["id"]] = nm
                if nm:
                    acc.append(nm)
                _collect(s.get("children", []), region, acc)

        _collect(r.get("stops", []))
        route.append({"region": r.get("title"), "stops": list(rstops)})

    active: Optional[Dict[str, Any]] = None
    if active_trip_stop_id and active_trip_stop_id in stop_name:
        active = {
            "kind": "stop",
            "name": stop_name[active_trip_stop_id],
            "region": stop_region.get(active_trip_stop_id),
        }

    # Notes: ONLY include_in_interview_context=1.
    notes: List[Dict[str, Any]] = []
    for n in trip_repository.location_notes_list(active_trip_id):
        if not n.get("include_in_interview_context"):
            continue
        sid, rid = n.get("trip_stop_id"), n.get("trip_region_id")
        scope = (stop_name.get(sid) if sid
                 else (region_name.get(rid) if rid else "the trip"))
        notes.append({
            "scope": scope,
            "title": n.get("note_title"),
            "text": _clip(n.get("note_text")),
        })
        if len(notes) >= _MAX_NOTES:
            break

    # Photo captions — WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Ph5.
    # narrator-ready links only, AND:
    #   - narrator_caption: allowed by construction (narrator's own words)
    #   - operator caption: ONLY when caption_approved_for_lori=1
    #     (review 2026-07-09 closed the gate — narrator_ready alone no
    #     longer surfaces operator text to Lori)
    # Approved operator context notes ride along as photo_context.
    captions: List[Dict[str, Any]] = []
    photo_context: List[Dict[str, Any]] = []
    for l in trip_repository.narrator_photo_links(active_trip_id):
        sid, rid = l.get("trip_stop_id"), l.get("trip_region_id")
        where = (stop_name.get(sid) if sid
                 else (region_name.get(rid) if rid else None))
        ncap = (l.get("narrator_caption") or "").strip()
        ocap = (l.get("caption") or "").strip()
        if ncap:
            cap = ncap
        elif ocap and l.get("caption_approved_for_lori"):
            cap = ocap
        else:
            cap = ""
        if cap and len(captions) < _MAX_CAPTIONS:
            captions.append({"where": where, "caption": _clip(cap)})
        note = (l.get("operator_context_note") or "").strip()
        if (note and l.get("operator_context_approved_for_lori")
                and len(photo_context) < _MAX_CAPTIONS):
            photo_context.append({"where": where, "context": _clip(note)})

    ctx: Dict[str, Any] = {
        "trip_id": active_trip_id,
        "title": trip.get("title"),
        "date_span": _date_span(trip.get("start_date"), trip.get("end_date")),
        "route": route,
        "active": active,
        "notes": notes,
        "photo_captions": captions,
        "photo_context": photo_context,
    }
    ctx["text"] = _to_prompt_text(ctx)
    return ctx


def _to_prompt_text(ctx: Dict[str, Any]) -> str:
    """Compact, mechanical-truth-only rendering. NO order claims — the
    route is entry order, not journey order, so it is labelled as such."""
    lines: List[str] = []
    span = ctx.get("date_span")
    lines.append(
        "Trip on record: '" + _safe(ctx.get("title") or "a trip") + "'"
        + ((" (" + _safe(span) + ")") if span else "") + "."
    )
    places: List[str] = []
    for r in ctx.get("route", []):
        seg = _safe(r.get("region"))
        if r.get("stops"):
            stops = ", ".join(_safe(s) for s in r["stops"])
            seg = (seg + " (" + stops + ")").strip()
        if seg:
            places.append(seg)
    if places:
        lines.append(
            "Places on the Travel Doc route board: " + "; ".join(places) + ". "
            "Do not claim the narrator personally confirmed this order unless "
            "they have said so."
        )
    active = ctx.get("active")
    if active:
        lines.append(
            "Currently looking at: " + _safe(active.get("name"))
            + ((" in " + _safe(active["region"])) if active.get("region") else "")
            + "."
        )
    for n in ctx.get("notes", []):
        title = (_safe(n.get("title")) + ": ") if n.get("title") else ""
        lines.append("Note (" + _safe(n.get("scope")) + "): " + title +
                     _safe(n.get("text")))
    for c in ctx.get("photo_captions", []):
        where = (" (" + _safe(c["where"]) + ")") if c.get("where") else ""
        lines.append("Photo caption" + where + ": " + _safe(c.get("caption")))
    for pc in ctx.get("photo_context", []):
        where = (" (" + _safe(pc["where"]) + ")") if pc.get("where") else ""
        # Locked phrasing rule: Lori speaks from "the approved text/
        # notes", never "I can see".
        lines.append("Approved photo context" + where + ": "
                     + _safe(pc.get("context")))
    return "\n".join(lines)


# ── Step 2 turn gate (default-OFF flag; used by chat_ws) ────────────────────

_FLAG = "HORNELORE_TRIP_INTERVIEW_CONTEXT"

_BLOCK_HEADER = (
    "\n\n[TRIP CONTEXT — the narrator has this trip open on the Travels "
    "shelf. The facts below are what you know about this trip.\n"
    "IF THE NARRATOR ASKS WHAT YOU KNOW OR REMEMBER ABOUT THE TRIP (e.g. "
    "'what do you know about my trip', 'what can you tell me about it', "
    "'tell me about my trip'): ANSWER THEM DIRECTLY AND WARMLY using ONLY "
    "these facts — say the trip's name and dates and name a few of the "
    "places on record — then invite them to begin wherever they like. Do "
    "NOT deflect, do NOT say 'where would you like to continue', and do NOT "
    "answer a direct question with another question.\n"
    "OTHERWISE, use these facts to ask ONE warm, grounded question in PAST "
    "TENSE. Reference only what is below; do not invent places, people, or "
    "events; do not claim you saw any photo.]\n"
)


def _flag_on() -> bool:
    return os.getenv(_FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def context_block_for_turn(
    person_id: Optional[str],
    runtime71: Optional[Dict[str, Any]],
) -> str:
    """Gate + render for a chat turn. Returns a prompt-ready block string, or
    "" when the gates are not met. READ-ONLY and safe to call every turn.

    Gates: default-OFF flag HORNELORE_TRIP_INTERVIEW_CONTEXT on, AND
    runtime71.active_trip_id present, AND Travels shelf open, AND the trip is
    owned by ``person_id`` (checked inside build_trip_interview_context).
    """
    if not _flag_on():
        return ""
    rt = runtime71 or {}
    trip_id = rt.get("active_trip_id")
    if not (person_id and trip_id and rt.get("travels_shelf_open")):
        return ""
    ctx = build_trip_interview_context(
        person_id, trip_id, active_trip_stop_id=rt.get("active_trip_stop_id"))
    if not ctx or not ctx.get("text"):
        return ""
    return _BLOCK_HEADER + ctx["text"]


# ── Direct trip-knowledge answer (WO-TRIP-LORI-REAL-BETA-USABILITY-01 Ph1) ──
# When a trip is open+owned and the narrator asks what Lori knows/remembers
# about the trip, answer DIRECTLY from approved trip context instead of
# deflecting. Deterministic (no LLM) — chat_ws routes this through the same
# dispatch path as lori_meta_question. Read-only; never invents route order,
# never surfaces raw sources or operator provenance, never claims image vision.

_TRIP_KNOWLEDGE_RX = re.compile(
    r"(?i)("
    r"what do you (know|remember) about (my|this|the) (trip|journey)|"
    r"what can you tell me about (my|this|the) (trip|journey|it)|"
    r"what can you tell me about it\b|"
    r"tell me about (my|this|the) (trip|journey)|"
    r"what do you know about (my|this|the) (trip|journey)|"
    r"what places do you know|"
    r"what do you know about \w[\w' -]* on (this|the|my) trip|"
    r"do you know (anything |much )?about (my|this|the) trip|"
    r"what do you know about (this|the|my) photo|"
    # BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01 (live 2026-07-09): these two
    # produced continuation boilerplate instead of an answer.
    r"what date was (that|this|it|the photo) taken|"
    r"when was (that|this|it|the photo) taken|"
    r"can you tell me about (the|that|this) photo|"
    r"tell me about (the|that|this) photo"
    r")"
)

# Direct photo/date fact questions get an HONEST answer, never deflection.
_PHOTO_FACT_RX = re.compile(
    r"(?i)(what date was|when was) (that|this|it|the photo) taken")
_PHOTO_ABOUT_RX = re.compile(
    r"(?i)(can you )?tell me about (the|that|this) photo|"
    r"what do you know about (this|the|my) photo")

_UNKNOWN_FACT_ANSWER = (
    "I don't know that from the approved trip record yet — but you might. "
    "What do you remember about that moment?"
)


def is_trip_knowledge_question(text: Optional[str]) -> bool:
    """True when the narrator is asking what Lori knows/remembers about the
    trip (or a place on it, or a photo). Deterministic; conservative."""
    return bool(_TRIP_KNOWLEDGE_RX.search(str(text or "")))


# Display-only spelling fixups for place labels (NEVER mutates the DB — the
# operator's stored value is untouched; this only cleans what Lori says aloud).
_DISPLAY_PLACE_FIXUPS = (
    (re.compile(r"(?i)\bbraveria\b"), "Bavaria"),
)


def _normalize_place_label(label: str) -> str:
    out = str(label or "")
    for rx, repl in _DISPLAY_PLACE_FIXUPS:
        out = rx.sub(repl, out)
    return out


def compose_direct_answer(ctx: Dict[str, Any]) -> str:
    """A warm, grounded answer built ONLY from approved trip context. Names
    the trip + dates + a few places on record, optionally one approved note.
    No route-order claims, no raw sources, no image content."""
    parts: List[str] = []
    title = _safe(ctx.get("title") or "your trip")
    span = ctx.get("date_span")
    lead = "I know this trip is recorded as " + title
    if span:
        lead += ", from " + _safe(span)
    parts.append(lead + ".")

    # De-duplicated place list. Region titles already name their stops
    # ("Czechia — Prague"), so a stop is skipped when its name is already
    # inside an added place (either direction). No route-order is implied —
    # this is a set of places, not a sequence.
    place_names: List[str] = []

    def _add_place(nm: Optional[str]) -> None:
        nm = _normalize_place_label(_safe(nm))
        if not nm:
            return
        low = nm.lower()
        for existing in place_names:
            el = existing.lower()
            if low in el or el in low:      # substring either way = same place
                return
        place_names.append(nm)

    for r in ctx.get("route", []) or []:
        _add_place(r.get("region"))
        for st in (r.get("stops") or []):
            _add_place(st)
    place_names = place_names[:8]
    if place_names:
        parts.append("The places on record include " + ", ".join(place_names) + ".")

    notes = ctx.get("notes") or []
    if notes:
        first = _safe(notes[0].get("text"))
        if first:
            parts.append("One thing you've shared is: " + first)

    parts.append(
        "I only know what is in the approved trip record so far — not the full "
        "story yet. Where would you like to start?"
    )
    return " ".join(parts)


def direct_answer_for_turn(
    person_id: Optional[str],
    runtime71: Optional[Dict[str, Any]],
    narrator_text: Optional[str],
) -> Optional[str]:
    """Gate + compose a direct trip-knowledge answer, or None. Gates: flag on,
    active trip open on the shelf, trip owned by person_id, AND the turn is a
    trip-knowledge question. Read-only and safe to call every turn."""
    if not _flag_on():
        return None
    rt = runtime71 or {}
    trip_id = rt.get("active_trip_id")
    if not (person_id and trip_id and rt.get("travels_shelf_open")):
        return None
    if not is_trip_knowledge_question(narrator_text):
        return None
    ctx = build_trip_interview_context(
        person_id, trip_id, active_trip_stop_id=rt.get("active_trip_stop_id"))
    if not ctx:
        return None
    # BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01: date-taken and about-the-
    # photo questions answer from APPROVED context or admit unknown —
    # never continuation boilerplate. (Per-photo approved dates reach
    # this surface in Ph7; until then captions are the approved photo
    # context we can honestly offer.)
    text = str(narrator_text or "")
    if _PHOTO_FACT_RX.search(text):
        return _UNKNOWN_FACT_ANSWER
    if _PHOTO_ABOUT_RX.search(text):
        caps = ctx.get("photo_captions") or []
        pctx = ctx.get("photo_context") or []
        if caps or pctx:
            bits = [c.get("caption") for c in caps[:2] if c.get("caption")]
            bits += [p.get("context") for p in pctx[:1] if p.get("context")]
            return ("The approved notes on the trip photos say: "
                    + "; ".join(bits) +
                    ". What do you remember about that moment?")
        return _UNKNOWN_FACT_ANSWER
    return compose_direct_answer(ctx)
