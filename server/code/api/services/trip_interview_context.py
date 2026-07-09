"""Trip interview context — WO-TRIP-INTERVIEW-CONTEXT-01 Step 1.

READ-ONLY assembly of a compact, SAFE trip context block for a narrator
with an actively-open trip. STEP 1 IS THE SERVICE + TESTS ONLY — nothing
here is wired into chat_ws / prompt_composer yet (that is Step 2, behind a
default-off flag, with separate approval).

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
  - any image/pixel interpretation
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import trip_repository

_MAX_NOTES = 8
_MAX_CAPTIONS = 10
_CLIP_WORDS = 40  # keep each note/caption compact


def _clip(text: Optional[str], n: int = _CLIP_WORDS) -> str:
    words = str(text or "").split()
    if not words:
        return ""
    return " ".join(words[:n]) + (" …" if len(words) > n else "")


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

    # Photo captions: narrator-ready links only, only those WITH a caption.
    captions: List[Dict[str, Any]] = []
    for l in trip_repository.narrator_photo_links(active_trip_id):
        cap = (l.get("narrator_caption") or l.get("caption") or "").strip()
        if not cap:
            continue
        sid, rid = l.get("trip_stop_id"), l.get("trip_region_id")
        where = (stop_name.get(sid) if sid
                 else (region_name.get(rid) if rid else None))
        captions.append({"where": where, "caption": _clip(cap)})
        if len(captions) >= _MAX_CAPTIONS:
            break

    ctx: Dict[str, Any] = {
        "trip_id": active_trip_id,
        "title": trip.get("title"),
        "date_span": _date_span(trip.get("start_date"), trip.get("end_date")),
        "route": route,
        "active": active,
        "notes": notes,
        "photo_captions": captions,
    }
    ctx["text"] = _to_prompt_text(ctx)
    return ctx


def _to_prompt_text(ctx: Dict[str, Any]) -> str:
    """Compact, mechanical-truth-only rendering. NO order claims — the
    route is entry order, not journey order, so it is labelled as such."""
    lines: List[str] = []
    span = ctx.get("date_span")
    lines.append(
        "Trip on record: '" + str(ctx.get("title") or "a trip") + "'"
        + ((" (" + span + ")") if span else "") + "."
    )
    places: List[str] = []
    for r in ctx.get("route", []):
        seg = str(r.get("region") or "")
        if r.get("stops"):
            seg = (seg + " (" + ", ".join(r["stops"]) + ")").strip()
        if seg:
            places.append(seg)
    if places:
        lines.append(
            "Places on record (NOT in journey order): " + "; ".join(places) + "."
        )
    active = ctx.get("active")
    if active:
        lines.append(
            "Currently looking at: " + str(active.get("name"))
            + ((" in " + active["region"]) if active.get("region") else "") + "."
        )
    for n in ctx.get("notes", []):
        title = (str(n.get("title")) + ": ") if n.get("title") else ""
        lines.append("Note (" + str(n.get("scope")) + "): " + title + str(n.get("text")))
    for c in ctx.get("photo_captions", []):
        where = (" (" + str(c["where"]) + ")") if c.get("where") else ""
        lines.append("Photo caption" + where + ": " + str(c.get("caption")))
    return "\n".join(lines)
