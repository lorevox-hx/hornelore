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
from .evidence_text import sanitize_for_prompt

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


def _link_belongs_to_trip(link_id: str, trip_id: str) -> bool:
    """Does this photo link actually sit on this trip? Read-only.

    The active photo id arrives from the browser alongside the rest of
    the modal scope, and every other field in that object is now
    shape-checked at the request boundary. Shape is not ownership: a
    well-formed id from a different trip, or from a link deleted three
    screens ago, is still a string of the right kind. Lori saying "the
    one you have selected" about a photo on somebody else's trip is a
    cross-trip statement, so the id is confirmed against the trip before
    it is allowed to mean anything."""
    try:
        row = trip_repository.photo_link_get(link_id)
    except Exception:
        return False
    return bool(row and row.get("trip_id") == trip_id)


def build_trip_interview_context(
    person_id: str,
    active_trip_id: str,
    active_trip_stop_id: Optional[str] = None,
    active_photo_link_id: Optional[str] = None,
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
    # WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden notes NEVER surface
    # here regardless of include_in_interview_context — the repository
    # list read excludes them by default, and the explicit skip below
    # is belt-and-braces on this narrator-facing surface.
    notes: List[Dict[str, Any]] = []
    for n in trip_repository.location_notes_list(active_trip_id):
        if n.get("hidden"):
            continue
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
    #
    # WO-TRIP-NARRATOR-BRIDGE-01: caption_total and context_total count
    # EVERY approved item, while the lists below stop at _MAX_CAPTIONS.
    # They are not the same number and must not be derived from each
    # other: len(captions) is how much was sent, the totals are how much
    # exists. Reporting len() as the total would have Lori say "I have
    # ten captions" on a trip with forty, which is a quiet lie told by a
    # display limit.
    captions: List[Dict[str, Any]] = []
    photo_context: List[Dict[str, Any]] = []
    caption_total = 0
    context_total = 0
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
        if cap:
            caption_total += 1
            if len(captions) < _MAX_CAPTIONS:
                captions.append({"where": where, "caption": _clip(cap)})
        note = (l.get("operator_context_note") or "").strip()
        if note and l.get("operator_context_approved_for_lori"):
            context_total += 1
            if len(photo_context) < _MAX_CAPTIONS:
                photo_context.append({"where": where, "context": _clip(note)})

        # WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Part E: approved OCR/vision only.
        # Draft and rejected photo-context rows NEVER reach narrator-facing
        # Lori; approved rows surface as "the approved Travel Doc notes"
        # (rendered under the locked never-"I can see" phrasing rule).
        try:
            for pcr in trip_repository.photo_context_list_for_link(
                    l.get("id")):
                if not pcr.get("approved_for_lori") or pcr.get("rejected"):
                    continue
                summ = sanitize_for_prompt(pcr.get("result_summary"))
                if not summ:
                    continue
                # Build the item FIRST, then count it. Counting before
                # the context_type check would count a row of some third
                # type that is never rendered, and Lori would report a
                # note she does not actually have.
                if pcr.get("context_type") == "ocr_text":
                    item = "the text on one photo reads: " + _clip(summ)
                elif pcr.get("context_type") == "vision_description":
                    item = _clip(summ)
                else:
                    continue
                context_total += 1
                if len(photo_context) < _MAX_CAPTIONS:
                    photo_context.append({"where": where, "context": item})
        except Exception:
            pass

    # WO-TRIP-NARRATOR-BRIDGE-01 — the inventory Lori was missing.
    #
    # The live failure: the narrator asked "can you see any of the photos
    # I added to my trip?" and Lori produced a continuation question,
    # because every photo fact in this context is derived from
    # narrator_photo_links, and on that trip it returned nothing. Two
    # photos were attached. Both were placed on days. Neither had been
    # cleared, so the narrator-safe read was empty and the context said
    # nothing about photos at all -- not "none", which would at least
    # have been answerable, but nothing. With no fact to stand on, the
    # model fell back on interview boilerplate. That is the dodge.
    #
    # These four numbers are the smallest set that lets an honest answer
    # be composed, and they are deliberately NOT one number:
    #   attached          -- exists on the trip, regardless of clearance
    #   on_a_day          -- has a placement on the timeline
    #   cleared_for_lori  -- an operator marked the photo narrator-ready
    #   approved captions / context -- text she may actually quote
    # "Attached" and "usable by me" are different facts about the same
    # photo and the narrator can see the first with their own eyes, so
    # collapsing them would have Lori contradict what is on the screen.
    #
    # Counts only. Nothing here carries a caption, a filename, a path, a
    # coordinate, a confidence value or an operator's words.
    inv = trip_repository.trip_photo_inventory(active_trip_id)
    ctx: Dict[str, Any] = {
        "trip_id": active_trip_id,
        "title": trip.get("title"),
        "date_span": _date_span(trip.get("start_date"), trip.get("end_date")),
        "route": route,
        "active": active,
        "notes": notes,
        "photo_captions": captions,
        "photo_context": photo_context,
        "photos": {
            # WO-TRIP-NARRATOR-BRIDGE-01 names this key photo_count and
            # defines it as "narrator-ready, nondeleted, nonhidden trip
            # photo links". Kept under its spec name so it is findable,
            # but bound to ATTACHED, not to narrator-ready. On the trip
            # that raised the question both photos were attached and
            # neither was narrator-ready, so the literal definition
            # yields zero -- Lori would tell a man that his trip has no
            # photos while he is looking at two of them. The three
            # counts below say what he actually needs to know: they are
            # here, they are placed, nobody has handed them to me.
            "photo_count": int(inv.get("attached") or 0),
            "attached": int(inv.get("attached") or 0),
            "on_a_day": int(inv.get("on_a_day") or 0),
            "cleared_for_lori": int(inv.get("cleared_for_lori") or 0),
            "approved_caption_count": caption_total,
            "approved_context_count": context_total,
            # The browser sends the selected link id. It is not trusted:
            # a selection that does not belong to THIS trip reads as no
            # selection at all, so a stale or forged id can never make
            # Lori say the narrator is looking at something they are not.
            "active_photo_selected": bool(
                active_photo_link_id
                and _link_belongs_to_trip(active_photo_link_id,
                                          active_trip_id)),
        },
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
    ph = ctx.get("photos") or {}
    if ph:
        # The deterministic answer below handles the direct question. This
        # line exists for every OTHER turn, where the narrator mentions a
        # photo in passing and the model must not invent having seen one.
        # It states the counts and then closes the door in the same breath,
        # because a bare count is an invitation to describe what is in them.
        att = int(ph.get("attached") or 0)
        bits = ["Photos attached to this trip: %d" % att]
        if att:
            bits.append("placed on a day: %d" % int(ph.get("on_a_day") or 0))
            bits.append("cleared for you to use: %d"
                        % int(ph.get("cleared_for_lori") or 0))
            bits.append("with an approved caption: %d"
                        % int(ph.get("approved_caption_count") or 0))
            bits.append("with approved context: %d"
                        % int(ph.get("approved_context_count") or 0))
        lines.append(
            "; ".join(bits) + ". You do NOT look at images. You may use only "
            "the approved captions and notes quoted here. Never say or imply "
            "that you can see, view or look at a photo. If asked whether you "
            "can see them, say plainly that photos are attached and that you "
            "work from approved captions and notes instead."
        )
        if ph.get("active_photo_selected"):
            lines.append("The narrator has one photo selected right now.")
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


def context_enabled() -> bool:
    """Public name for the same gate the turn path reads.

    WO-TRIP-NARRATOR-BRIDGE-01 section A: the preflight has to report
    whether this behaviour is live IN THE SERVING PROCESS, and the only
    honest way to answer that is to call the function the turn calls. A
    readout that re-reads os.environ on its own would agree with the
    shell it was launched from rather than with the server, which is how
    the first Gate 7 live run was voided."""
    return _flag_on()


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
        person_id, trip_id,
        active_trip_stop_id=rt.get("active_trip_stop_id"),
        active_photo_link_id=rt.get("active_photo_link_id"))
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


# WO-TRIP-NARRATOR-BRIDGE-01 — the capability question.
#
# LIVE FAILURE, 2026-07-30. The narrator typed, verbatim:
#     can you see any of the photos I added to my trip?
# and Lori replied:
#     Would you like to continue telling me about your experiences
#     during the Bismarck Trip?
# Nothing in _TRIP_KNOWLEDGE_RX matches that sentence. Every photo
# pattern above is SINGULAR and about CONTENT -- "tell me about the
# photo", "what date was that taken". A plural question about whether
# she can reach them at all had no pattern, so the deterministic path
# never ran and the model produced boilerplate.
#
# Two shapes, kept apart because they read differently:
#
# GROUP A, capability aimed at Lori: a modal or auxiliary, "you", a
# reaching verb, then a photo word. The [^?.!]{0,40} gaps let the real
# sentence through ("can you SEE any of the PHOTOS I added to my trip")
# without letting the match run across a sentence boundary into an
# unrelated clause.
#
# GROUP B, inventory: "what photos", "how many photos", "are there any
# photos", "does this trip have photos". These ask what EXISTS rather
# than what she can do, and they arrive without a capability verb.
#
# WHAT IT MUST NOT MATCH is ordinary narrative that happens to mention
# photographs -- "I took photos of the gravesite that day", "Melanie
# showed me pictures of the school". Neither carries "you" plus a
# reaching verb, and neither is an inventory question, so both fall
# through to the interview as they should. Requiring the second person
# is what keeps this classifier from eating the memoir.
_PHOTO_WORD = r"(?:photo|photos|photograph|photographs|picture|pictures|image|images|snapshot|snapshots)"

_PHOTO_CAPABILITY_RX = re.compile(
    r"(?i)("
    # Group A — "can you see / view / read / access / open / pull up …"
    r"\b(?:can|could|do|does|are|will|would)\s+you\b"
    r"[^?.!]{0,40}?"
    r"\b(?:see|seen|seeing|view|viewing|read|reading|access|look|looking|"
    r"open|opened|pull\s+up|bring\s+up|use|using|have|got|remember|"
    r"recall|find)\b"
    r"[^?.!]{0,40}?"
    r"\b" + _PHOTO_WORD + r"\b"
    r"|"
    # Group B — inventory: what exists on the trip
    r"\bwhat\s+" + _PHOTO_WORD + r"\b|"
    r"\bhow\s+many\s+" + _PHOTO_WORD + r"\b|"
    r"\b(?:are|is)\s+there\s+(?:any\s+|some\s+)?" + _PHOTO_WORD + r"\b|"
    r"\b(?:does|did|do)\s+(?:this|the|my)\s+(?:trip|journey)\s+have\s+"
    r"(?:any\s+)?" + _PHOTO_WORD + r"\b"
    r")"
)


def is_photo_capability_question(text: Optional[str]) -> bool:
    """True when the narrator is asking whether Lori can reach the trip
    photos, or what photos the trip has. Deterministic; second-person or
    inventory phrasing required, so ordinary narrative about taking
    photographs is not swallowed."""
    return bool(_PHOTO_CAPABILITY_RX.search(str(text or "")))


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


_COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six",
                "seven", "eight", "nine", "ten")


def _count_word(n: int) -> str:
    """Small counts read as words in speech. Nine photos, not 9 photos."""
    n = int(n or 0)
    return _COUNT_WORDS[n] if 0 <= n < len(_COUNT_WORDS) else str(n)


def compose_photo_capability_answer(ctx: Dict[str, Any]) -> str:
    """WO-TRIP-NARRATOR-BRIDGE-01. Answer "can you see my photos?" honestly,
    from counts and approved words only.

    THE RULE THIS EXISTS TO KEEP: Lori never claims image vision. She may say
    what is attached, what is placed on a day, and what approved words someone
    has written about a photo. She may not say or imply that she looked at
    one. The failure this replaces was a dodge -- continuation boilerplate in
    answer to a direct question -- and the tempting fix, letting the model
    improvise, trades a dodge for a claim she cannot back.

    Four states, and they are genuinely different answers, which is why this
    is not one sentence with a number substituted in:

      nothing attached
          say so, and offer to receive them.
      attached, none cleared for her
          say they are here, say plainly that she has not been given them,
          and ask him to tell her what is in them. This is the live Bismarck
          state: two attached, both on days, zero cleared. Answering that
          with "yes, I can see two photos" would be a lie about the only
          thing he actually asked.
      attached and cleared, with approved captions or notes
          quote the approved words. That text is the ONLY photo content she
          is ever allowed to speak, and quoting it is not the same as
          looking -- so the sentence that introduces it says where it came
          from.
      attached and cleared, but nobody has written anything
          say the clearance exists and the words do not, because "cleared
          with nothing on it" and "not cleared" are different situations for
          the operator to fix and he is also the operator.

    "Cleared" is deliberately plain English. narrator_ready is a column name;
    saying it to the narrator would be asking a man to debug his own memoir
    in the middle of telling it.
    """
    photos = ctx.get("photos") or {}
    attached = int(photos.get("attached") or 0)
    on_a_day = int(photos.get("on_a_day") or 0)
    cleared = int(photos.get("cleared_for_lori") or 0)
    caps = [c.get("caption") for c in (ctx.get("photo_captions") or [])
            if c.get("caption")]
    notes = [p.get("context") for p in (ctx.get("photo_context") or [])
             if p.get("context")]
    title = _safe(ctx.get("title") or "this trip")

    parts: List[str] = []

    if attached <= 0:
        return (
            "There aren\u2019t any photos attached to " + title + " yet. "
            "I don\u2019t look at pictures in any case \u2014 what reaches me is "
            "the captions and notes someone writes about a photo and approves "
            "for me to use. Add some when you\u2019re ready, and tell me what\u2019s "
            "in them, and I\u2019ll hold on to them with you."
        )

    noun = "photo" if attached == 1 else "photos"
    lead = ("There " + ("is " if attached == 1 else "are ")
            + _count_word(attached) + " " + noun + " attached to " + title)
    if attached and on_a_day >= attached:
        # "they are both placed on a day" would imply ONE shared day; the
        # live pair sits on day 1 and day 2. Each, not both.
        lead += (", and " + ("it\u2019s placed on a day"
                             if attached == 1
                             else "each of them is placed on a day"))
    elif on_a_day > 0:
        lead += (", " + _count_word(on_a_day) + " of them placed on a day")
    parts.append(lead + ".")

    if photos.get("active_photo_selected"):
        parts.append("You have one of them open in front of you right now.")

    parts.append(
        "I should be straight with you about what that means for me, though: "
        "I don\u2019t look at the images themselves. What I can work from is the "
        "captions and notes that have been written about a photo and approved "
        "for me."
    )

    if caps or notes:
        quoted = [_safe(q) for q in (caps[:2] + notes[:1]) if _safe(q)]
        parts.append("Here\u2019s what I have in writing: "
                     + "; ".join(quoted) + ".")
        parts.append("Tell me about the others \u2014 what were you looking at?")
        return " ".join(parts)

    if cleared <= 0:
        parts.append(
            ("That one hasn\u2019t" if attached == 1 else "None of them have")
            + " been cleared for me yet, so there\u2019s nothing written down "
            "on my side about " + ("it" if attached == 1 else "them") + "."
        )
    else:
        parts.append(
            "They\u2019re cleared for me, but no one has written a caption or a "
            "note on them yet, so I have no words to work from."
        )
    parts.append(
        "Describe " + ("it" if attached == 1 else "them")
        + " to me instead \u2014 what\u2019s in the picture, and what was happening "
        "when it was taken?"
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
    # The capability question is NOT a trip-knowledge question -- none of
    # the _TRIP_KNOWLEDGE_RX patterns match "can you see any of the photos
    # I added to my trip?". Without this second clause the composer below
    # is unreachable and the live dodge stands.
    if not (is_trip_knowledge_question(narrator_text)
            or is_photo_capability_question(narrator_text)):
        return None
    ctx = build_trip_interview_context(
        person_id, trip_id,
        active_trip_stop_id=rt.get("active_trip_stop_id"),
        active_photo_link_id=rt.get("active_photo_link_id"))
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
    # Checked AFTER the two singular branches above so shipped
    # behaviour for "tell me about this photo" is untouched, and
    # BEFORE the general answer because a capability question that
    # also trips _TRIP_KNOWLEDGE_RX is still a capability question.
    if is_photo_capability_question(text):
        return compose_photo_capability_answer(ctx)
    return compose_direct_answer(ctx)
