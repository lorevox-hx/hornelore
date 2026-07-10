"""Travel Doc Lori modal — WO-TRAVEL-DOC-LORI-MODAL-02 service contract.

The OPERATOR trip-memoir conversation surface. LAW 3: imports the trip
data layer + capture only — never chat_ws, prompt_composer, extract, the
Lori runtime, runtime71, or Travels-shelf state. The modal owns its own
explicit scope.

Provenance rule (locked 2026-07-09): draft context may be used ONLY with
draft phrasing ("The draft photo context suggests…"); operator-approved
context speaks as fact ("The approved photo context says…"). Never
"I can see" / "the photo shows". Raw GPS and upload/save/modified dates
never reach an answer.

WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01 (2026-07-09): public/web
context rows (trip_public_context) join the evidence set under the same
certainty rule — approved rows speak as "The approved Travel Doc
context says…", unapproved rows as "The public context suggests…".
Public context is public background, never personal memory.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Tuple

from . import trip_repository
from . import trip_story_capture

SOURCE_SURFACE = "travel_doc_modal"

_DATE_Q_RX = re.compile(
    r"(?i)(what date was|when was) (that|this|it|the photo|the picture) taken")
_ABOUT_Q_RX = re.compile(
    r"(?i)(can you )?tell me about (the|that|this) (photo|picture)|"
    r"what (can you tell me|do you know) about (this|the|that|my) photo")


def _fmt_date(iso: str) -> str:
    """2026-05-14 → May 14, 2026 (falls back to the raw value)."""
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
        return "%s %d, %d" % (d.strftime("%B"), d.day, d.year)
    except Exception:
        return str(iso)


def _packet_from_link(l: Dict[str, Any]) -> Dict[str, Any]:
    """Approved/draft evidence packet built from ONE photo-link row (the
    photo_links_list JOIN shape). Shared by the modal and the travelogue
    builder so the approved-vs-draft semantics live in one place. NEVER
    includes raw GPS or upload/save/modified timestamps."""
    out: Dict[str, Any] = {
        "photo_link_id": l.get("id"), "approved_caption": None,
        "approved_context": None, "narrator_caption": None,
        "approved_taken_date": None, "draft_context": None,
        "filename_guess": None, "approved_place": None,
        "draft_date": None, "draft_place": None, "gps_present": False,
    }
    ncap = (l.get("narrator_caption") or "").strip()
    ocap = (l.get("caption") or "").strip()
    note = (l.get("operator_context_note") or "").strip()
    if ncap:
        out["narrator_caption"] = ncap
    if ocap and l.get("caption_approved_for_lori"):
        out["approved_caption"] = ocap
    elif ocap:
        out["draft_context"] = ocap          # unapproved caption = draft
    if note and l.get("operator_context_approved_for_lori"):
        out["approved_context"] = note
    elif note and not out["draft_context"]:
        out["draft_context"] = note
    if (l.get("photo_date_value")
            and l.get("photo_date_approved_for_lori")):
        out["approved_taken_date"] = l["photo_date_value"]
    elif l.get("photo_date_value"):
        out["draft_date"] = l["photo_date_value"]   # EXIF/unapproved
    out["filename_guess"] = l.get("photo_taken_at_filename_guess")
    out["gps_present"] = bool(l.get("photo_gps_present"))
    if not out.get("draft_date") and out["filename_guess"]:
        out["draft_date"] = out["filename_guess"]
    if (l.get("photo_location_label")
            and l.get("photo_location_approved_for_lori")):
        out["approved_place"] = l["photo_location_label"]
    elif l.get("photo_location_label"):
        out["draft_place"] = l["photo_location_label"]
    return out


def _photo_packet(trip_id: str, photo_link_id: Optional[str]) -> Dict[str, Any]:
    """Approved/draft context for the anchored photo. NEVER includes raw
    GPS or upload/save/modified timestamps."""
    if not photo_link_id:
        return _packet_from_link({})
    for l in trip_repository.photo_links_list(trip_id):
        if l.get("id") == photo_link_id:
            return _packet_from_link(l)
    # Link id not found in this trip — keep the requested id in the
    # packet (legacy behavior) so callers don't misreport 'no photo
    # anchored' for a merely-unresolvable link.
    out = _packet_from_link({})
    out["photo_link_id"] = photo_link_id
    return out


def _public_context_for_scope(
    scope: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    """(approved, draft) public-context summaries that apply to the
    modal's current scope: photo-scoped rows for the anchored photo,
    stop-scoped rows for the active stop, region-scoped rows for the
    active region, and trip-wide rows (no narrower scope) always."""
    trip_id = scope.get("active_trip_id")
    if not trip_id:
        return [], []
    try:
        rows = trip_repository.public_context_list(trip_id)
    except Exception:
        return [], []
    link_id = scope.get("active_photo_link_id")
    stop_id = scope.get("active_trip_stop_id")
    region_id = scope.get("active_trip_region_id")
    approved: List[str] = []
    draft: List[str] = []
    for r in rows:
        r_link = r.get("photo_link_id")
        r_stop = r.get("trip_stop_id")
        r_region = r.get("trip_region_id")
        if r_link:
            match = bool(link_id) and r_link == link_id
        elif r_stop:
            match = bool(stop_id) and r_stop == stop_id
        elif r_region:
            match = bool(region_id) and r_region == region_id
        else:
            match = True  # trip-wide public context
        if not match:
            continue
        summary = (r.get("result_summary") or "").strip()
        if not summary:
            continue
        if r.get("approved_for_lori"):
            approved.append(summary)
        else:
            draft.append(summary)
    return approved, draft


def _public_context_tail(scope: Dict[str, Any]) -> str:
    """Provenance-worded public-context sentences (leading space) or ''.
    Approved wording is fact-shaped; draft wording stays suggestive."""
    approved, draft = _public_context_for_scope(scope)
    bits: List[str] = []
    if approved:
        bits.append("The approved Travel Doc context says: "
                    + " — ".join(approved))
    if draft:
        bits.append("The public context suggests "
                    + "; ".join(d.rstrip(".") for d in draft)
                    + " — that's public background, not confirmed for "
                    "this trip yet")
    if not bits:
        return ""
    return " " + " ".join(
        b if b.endswith((".", "!", "?")) else b + "." for b in bits)


def build_modal_scope(
    person_id: str,
    active_trip_id: str,
    active_trip_region_id: Optional[str] = None,
    active_trip_stop_id: Optional[str] = None,
    active_photo_link_id: Optional[str] = None,
    conv_id: Optional[str] = None,
    selected_kind: str = "trip",
) -> Optional[Dict[str, Any]]:
    """Explicit modal scope. No runtime71, no shelf keys, no raw GPS."""
    trip = trip_repository.trip_get(active_trip_id)
    if not trip or trip.get("person_id") != person_id:
        return None
    label = trip.get("title") or "a trip"
    if selected_kind == "stop" and active_trip_stop_id:
        s = trip_repository.stop_get(active_trip_stop_id)
        if s:
            label = s.get("location_name") or s.get("title") or label
    return {
        "source_surface": SOURCE_SURFACE,
        "person_id": person_id,
        "conv_id": conv_id,
        "active_trip_id": active_trip_id,
        "active_trip_region_id": active_trip_region_id,
        "active_trip_stop_id": active_trip_stop_id,
        "active_photo_link_id": active_photo_link_id,
        "selected_kind": selected_kind,
        "selected_label": label,
        "photo_context": _photo_packet(active_trip_id, active_photo_link_id),
    }


def answer_modal_direct_question(
    person_id: str,
    scope: Optional[Dict[str, Any]],
    narrator_text: Optional[str],
) -> Optional[str]:
    """Deterministic, workspace-aware answers for direct photo/date
    questions. Returns None when the turn isn't one of those (the LLM
    path handles it)."""
    sc = scope or {}
    if sc.get("person_id") != person_id:
        return None
    text = str(narrator_text or "")
    pkt = sc.get("photo_context") or {}
    if not pkt.get("photo_link_id") and sc.get("active_photo_link_id"):
        pkt = _photo_packet(sc.get("active_trip_id"),
                            sc.get("active_photo_link_id"))
    if _DATE_Q_RX.search(text):
        if pkt.get("approved_taken_date"):
            return ("The approved taken date for this photo is "
                    + _fmt_date(pkt["approved_taken_date"]) + ".")
        if pkt.get("draft_date"):
            return ("The file data suggests " + _fmt_date(pkt["draft_date"])
                    + ", but that isn't confirmed yet — the Travel Doc can "
                    "store it as the taken date if that matches your memory.")
        return ("I don't have a taken date for this photo in the approved "
                "trip record yet. The Travel Doc can store one if you "
                "confirm it.")
    if _ABOUT_Q_RX.search(text):
        # Public/web context for this scope — approved rows speak as
        # fact, draft rows stay suggestive (evidence-rich doctrine).
        pub_tail = _public_context_tail(sc)
        bits: List[str] = []
        if pkt.get("approved_caption"):
            bits.append(pkt["approved_caption"])
        if pkt.get("approved_context"):
            bits.append(pkt["approved_context"])
        if bits:
            return ("The approved photo context says: "
                    + " — ".join(bits) + pub_tail
                    + " What do you remember about that moment?")
        if pkt.get("narrator_caption"):
            return ("Your own caption on this photo says: "
                    + pkt["narrator_caption"] + pub_tail
                    + " What else do you remember?")
        # POLICY 2026-07-10 (two-surface rule): Travel Doc is the
        # operator memoir workspace — EVIDENCE-RICH, provenance-labeled,
        # never hidden. Compose everything available; expose lanes that
        # haven't run yet instead of pleading no-context. Certainty (not
        # privacy) is the constraint: suggestive wording before
        # confirmation, approved wording after.
        draft_bits: List[str] = []
        if pkt.get("draft_context"):
            draft_bits.append("the draft photo context suggests "
                              + pkt["draft_context"].rstrip("."))
        if pkt.get("draft_date"):
            draft_bits.append("the photo data suggests it was taken "
                              + _fmt_date(pkt["draft_date"]))
        if pkt.get("draft_place"):
            draft_bits.append("the location note appears to point to "
                              + pkt["draft_place"].rstrip("."))
        missing: List[str] = []
        if pkt.get("gps_present") and not (pkt.get("draft_place")
                                           or pkt.get("approved_place")):
            missing.append("GPS coordinates are recorded, but place "
                           "extraction hasn't run yet")
        if not pkt.get("draft_context"):
            missing.append("no image or OCR draft has been added yet")
        if draft_bits:
            joined = draft_bits[0]
            if len(draft_bits) > 1:
                joined += ", and " + ", and ".join(draft_bits[1:])
            tail = (" (" + "; ".join(missing) + ")") if missing else ""
            return (joined[0].upper() + joined[1:] + "."
                    + tail + pub_tail + " Does that match your memory?")
        if pub_tail:
            return (pub_tail.strip()
                    + " Does that match anything you remember?")
        if missing:
            return ("I don't have drafted context for this photo yet — "
                    + "; ".join(missing)
                    + ". The Travel Doc can capture what you remember "
                    "either way — what stands out from that moment?")
        if not pkt.get("photo_link_id"):
            return ("No photo is anchored right now — open 'Talk with "
                    "Lori about this photo' on a photo card and I can "
                    "use its approved context.")
        return ("I don't know that from the approved trip record yet — "
                "the Travel Doc can store a caption or context note if "
                "you add one.")
    return None


def capture_modal_answer(
    person_id: str,
    scope: Optional[Dict[str, Any]],
    narrator_text: Optional[str],
    previous_lori_text: Optional[str] = None,
    conv_id: Optional[str] = None,
    turn_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Thin wrapper over the landed modal capture path — explicit scope
    only, provenance stamped, both promotion flags OFF."""
    return trip_story_capture.capture_modal_turn(
        person_id, scope or {}, narrator_text,
        previous_lori_text=previous_lori_text,
        conv_id=conv_id or (scope or {}).get("conv_id"),
        turn_id=turn_id,
    )


__all__ = ["build_modal_scope", "answer_modal_direct_question",
           "capture_modal_answer", "SOURCE_SURFACE"]
