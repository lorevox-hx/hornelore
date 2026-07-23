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
from .evidence_text import sanitize_for_prompt

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
    GPS or upload/save/modified timestamps.

    Preflight review-follow-up (2026-07-11): when a photo_link_id
    is passed but does not resolve to a link in THIS trip, the
    packet's ``photo_link_id`` is NULL — the earlier fallback
    preserved a cross-trip / unknown id which then flowed straight
    through _photo_context_rows_for_scope() as a raw
    trip_photo_context lookup key. Cross-trip leak surface closed."""
    if not photo_link_id:
        return _packet_from_link({})
    for l in trip_repository.photo_links_list(trip_id):
        if l.get("id") == photo_link_id:
            return _packet_from_link(l)
    # Link id not resolvable in this trip — fall back to the empty
    # packet AND drop the requested id so downstream evidence lookups
    # don't run against a foreign / unknown link.
    return _packet_from_link({})


def _public_context_for_scope(
    scope: Dict[str, Any],
) -> Tuple[List[str], List[str]]:
    """(approved, draft) public-context summaries that apply to the
    modal's current scope: photo-scoped rows for the anchored photo,
    stop-scoped rows for the active stop, region-scoped rows for the
    active region, and trip-wide rows (no narrower scope) always.

    Preflight review-follow-up (2026-07-11):
      * Rejected rows are always skipped (parity with photo_context).
      * Photo-scoped rows with source_type='place_context' are handled
        by the dedicated place_from_context lane in
        _photo_context_rows_for_scope() — exclude them here so a
        place-context row can never appear TWICE in one modal answer
        (once as "The approved place context says…" and again as
        "The approved Travel Doc context says…")."""
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
        # Skip rejected rows (preflight: trip_public_context.rejected).
        if r.get("rejected"):
            continue
        r_link = r.get("photo_link_id")
        r_stop = r.get("trip_stop_id")
        r_region = r.get("trip_region_id")
        # Photo-scoped place_context is owned by the dedicated
        # place_from_context lane; do not duplicate it here.
        if (r_link and r_link == link_id
                and r.get("source_type") == "place_context"):
            continue
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
        summary = sanitize_for_prompt(r.get("result_summary"))
        if not summary:
            continue
        if r.get("approved_for_lori"):
            approved.append(summary)
        else:
            draft.append(summary)
    return approved, draft


# What Lori SAYS of a public-context row. The stored summary can be ~500 chars
# of encyclopedia article; read aloud to an older narrator that is a wall of
# text. The operator still sees the full row in the evidence panel — this trims
# only the spoken form to a short lead (first sentence, capped), which is all a
# place hint should be ("The German Hunting and Fishing Museum in Munich.").
_SPOKEN_CONTEXT_CHARS = 160


def _spoken_context_trim(text: str) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= _SPOKEN_CONTEXT_CHARS:
        return t
    # Prefer the FIRST sentence — for a place lookup that is the place itself
    # ("The German Hunting and Fishing Museum in Munich."), and the rest is
    # encyclopedia history the narrator does not need read aloud. Accept a
    # first sentence up to a bit over budget; otherwise cap at a word boundary.
    m = re.search(r"[.!?](?:\s|$)", t)
    if m and 12 <= m.end() <= _SPOKEN_CONTEXT_CHARS + 60:
        return t[:m.end()].strip()
    head = t[:_SPOKEN_CONTEXT_CHARS]
    sp = head.rfind(" ")
    return (head[:sp] if sp >= 60 else head).strip() + "\u2026"


def _public_context_tail(scope: Dict[str, Any]) -> str:
    """Provenance-worded public-context sentences (leading space) or ''.
    Approved wording is fact-shaped; draft wording stays suggestive."""
    approved, draft = _public_context_for_scope(scope)
    approved = [_spoken_context_trim(a) for a in approved]
    draft = [_spoken_context_trim(d) for d in draft]
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
    active_trip_day_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Explicit modal scope. No runtime71, no shelf keys, no raw GPS.

    WO-TRAVEL-DOC-UI-LAB-02: ``active_trip_day_id`` (day-scoped modal)
    is kept only when it resolves to a day of THIS trip — a cross-trip
    or unknown day id is dropped to None, never trusted."""
    trip = trip_repository.trip_get(active_trip_id)
    if not trip or trip.get("person_id") != person_id:
        return None
    label = trip.get("title") or "a trip"
    if selected_kind == "stop" and active_trip_stop_id:
        s = trip_repository.stop_get(active_trip_stop_id)
        if s:
            label = s.get("location_name") or s.get("title") or label
    day_id: Optional[str] = None
    if active_trip_day_id:
        try:
            _day = trip_repository.trip_day_get(active_trip_day_id)
        except Exception:
            _day = None
        if _day and _day.get("trip_id") == active_trip_id:
            day_id = active_trip_day_id
    # Preflight review-follow-up (2026-07-11): validate the photo link
    # belongs to THIS trip. A cross-trip / unknown id must be dropped
    # so downstream evidence lookups don't run against a foreign link
    # (which would leak another trip's OCR / observation / place
    # context into the modal answer).
    link_id: Optional[str] = None
    if active_photo_link_id:
        try:
            _link = trip_repository.photo_link_get(active_photo_link_id)
        except Exception:
            _link = None
        if _link and _link.get("trip_id") == active_trip_id:
            link_id = active_photo_link_id
    return {
        "source_surface": SOURCE_SURFACE,
        "person_id": person_id,
        "conv_id": conv_id,
        "active_trip_id": active_trip_id,
        "active_trip_region_id": active_trip_region_id,
        "active_trip_stop_id": active_trip_stop_id,
        "active_photo_link_id": link_id,
        "active_trip_day_id": day_id,
        "selected_kind": selected_kind,
        "selected_label": label,
        "photo_context": _photo_packet(active_trip_id, link_id),
    }


def _photo_context_rows_for_scope(
    scope: Dict[str, Any],
) -> Dict[str, List[str]]:
    """OCR / vision / draft-observation evidence for the anchored photo,
    split approved vs draft. Rejected rows are skipped. Place evidence
    from trip_public_context.source_type='place_context' is folded in
    under approved_place / draft_place buckets. Preflight 2026-07-11:
    added draft_observation + place_from_context lanes."""
    out: Dict[str, List[str]] = {
        "approved_ocr": [], "draft_ocr": [],
        "approved_vision": [], "draft_vision": [],
        # WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11):
        # local-LLM draft observation lane, separate from vision so the
        # modal can use the locked "photo observation" wording (Chris
        # spec) rather than the older "image context" wording.
        "approved_observation": [], "draft_observation": [],
        # place_from_context evidence — sourced from
        # trip_public_context.source_type='place_context' (which was
        # already an allowed value in migration 0026). Split like the
        # rest: approved rows speak as fact, drafts as suggestion.
        "approved_place_context": [], "draft_place_context": [],
    }
    link_id = (scope or {}).get("active_photo_link_id")
    if not link_id:
        return out
    try:
        rows = trip_repository.photo_context_list_for_link(link_id)
    except Exception:
        return out
    for r in rows:
        if r.get("rejected"):
            continue
        summ = sanitize_for_prompt(r.get("result_summary"))
        if not summ:
            continue
        approved = bool(r.get("approved_for_lori"))
        ct = r.get("context_type")
        if ct == "ocr_text":
            out["approved_ocr" if approved else "draft_ocr"].append(summ)
        elif ct == "vision_description":
            out["approved_vision" if approved else "draft_vision"].append(summ)
        elif ct == "draft_observation":
            key = "approved_observation" if approved else "draft_observation"
            out[key].append(summ)

    # place_from_context evidence lives in trip_public_context. Pull the
    # subset filtered to this photo link (repository already ships a
    # photo-scoped list; we filter to source_type='place_context'). If
    # the accessor is missing (older repo pin), fail soft.
    try:
        place_rows = trip_repository.public_context_list_for_link(link_id) \
            if hasattr(trip_repository, "public_context_list_for_link") \
            else []
    except Exception:
        place_rows = []
    for pr in place_rows or []:
        pr = pr or {}
        if pr.get("source_type") != "place_context":
            continue
        # Preflight review-follow-up (2026-07-11): skip rejected rows
        # (trip_public_context.rejected added by migration 0032).
        if pr.get("rejected"):
            continue
        summ = sanitize_for_prompt(pr.get("result_summary"))
        if not summ:
            continue
        approved = bool(pr.get("approved_for_lori"))
        key = ("approved_place_context" if approved
               else "draft_place_context")
        out[key].append(summ)
    return out


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
        pc = _photo_context_rows_for_scope(sc)
        # ── Approved tier: caption/context, then OCR, then vision ──
        approved_sentences: List[str] = []
        cap_ctx: List[str] = []
        if pkt.get("approved_caption"):
            cap_ctx.append(pkt["approved_caption"])
        if pkt.get("approved_context"):
            cap_ctx.append(pkt["approved_context"])
        if cap_ctx:
            approved_sentences.append(
                "The approved photo context says: " + " — ".join(cap_ctx))
        for t in pc["approved_ocr"]:
            approved_sentences.append(
                "The approved OCR text says: " + t.rstrip("."))
        for t in pc["approved_vision"]:
            approved_sentences.append(
                "The approved image-context note says: "
                + _spoken_context_trim(t).rstrip("."))
        # WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11):
        # locked wording — "The approved photo observation says…" for
        # local-LLM-drafted observations that the operator has
        # promoted; "The approved place context says…" for
        # place_from_context evidence promoted from
        # trip_public_context. Approved rows always speak as fact.
        for t in pc["approved_observation"]:
            approved_sentences.append(
                "The approved photo observation says: "
                + _spoken_context_trim(t).rstrip("."))
        for t in pc["approved_place_context"]:
            approved_sentences.append(
                "The approved place context says: "
                + _spoken_context_trim(t).rstrip("."))
        if approved_sentences:
            body = " ".join(
                s if s.endswith((".", "!", "?")) else s + "."
                for s in approved_sentences)
            return (body + pub_tail
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
        for t in pc["draft_ocr"]:
            draft_bits.append("the OCR draft appears to read '"
                              + t.rstrip(".") + "'")
        for t in pc["draft_vision"]:
            draft_bits.append("the draft image context suggests "
                              + _spoken_context_trim(t).rstrip("."))
        # WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11):
        # locked wording — "The draft photo observation suggests…" for
        # local-LLM-drafted observations that haven't been approved
        # yet; "The place context suggests…" for place_from_context
        # drafts. Draft rows always stay suggestive (never fact).
        for t in pc["draft_observation"]:
            draft_bits.append("the draft photo observation suggests "
                              + _spoken_context_trim(t).rstrip("."))
        for t in pc["draft_place_context"]:
            draft_bits.append("the place context suggests "
                              + _spoken_context_trim(t).rstrip("."))
        if pkt.get("draft_context"):
            draft_bits.append("the draft photo context suggests "
                              + _spoken_context_trim(
                                  pkt["draft_context"]).rstrip("."))
        if pkt.get("draft_date"):
            draft_bits.append("the photo data suggests it was taken "
                              + _fmt_date(pkt["draft_date"]))
        if pkt.get("draft_place"):
            draft_bits.append("the location note appears to point to "
                              + pkt["draft_place"].rstrip("."))
        missing: List[str] = []
        # WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11):
        # never expose raw GPS OR the word "coordinates" / "GPS" to
        # the modal answer. Keep an observability hint that a place
        # inference lane hasn't run — but phrased against the
        # place_from_context lane, not against the raw location fix.
        # Suppress once ANY place lane has produced evidence (photo
        # link's draft_place / approved_place from location_label OR
        # a place_from_context row on either approval side).
        has_any_place = bool(
            pkt.get("draft_place") or pkt.get("approved_place")
            or pc["draft_place_context"] or pc["approved_place_context"])
        if pkt.get("gps_present") and not has_any_place:
            missing.append("a place inference from context hasn't run "
                           "for this photo yet")
        if not (pkt.get("draft_context") or pc["draft_ocr"]
                or pc["approved_ocr"] or pc["draft_vision"]
                or pc["approved_vision"]):
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


_ACK_EXCERPT_WORDS = 25

_DAY_CAPTURE_FOLLOW_UP = ("Anything else from that day — where you "
                          "stayed, or what you ate?")


def compose_day_capture_ack(
    day: Optional[Dict[str, Any]],
    capture_result: Optional[Dict[str, Any]],
    narrator_text: Optional[str],
) -> Optional[str]:
    """Deterministic Day Capture acknowledgment (WO-TRAVEL-DOC-UI-LAB-02
    items 6+7). When a day-scoped modal turn was a meaningful memory and
    the capture path saved it, reply from the day + the narrator's OWN
    words instead of routing to the LLM — this kills the anchor-echo
    garbage path for day captures by construction.

    Shape (locked): 'Got it — I saved that as a Day {N} travel note:
    "{first ~25 words of the narrator's own wording}…" {ONE fixed,
    warm, fact-oriented follow-up}.' Never "I can see", never invents
    facts — only the narrator's words plus the day number/date.

    Returns None unless: day row present, capture actually wrote (or
    deduped to) a note, and there is narrator text to restate."""
    if not day or not isinstance(day, dict):
        return None
    res = capture_result or {}
    if not res.get("captured"):
        return None
    if res.get("reason") not in ("meaningful_trip_answer", "duplicate"):
        return None
    text = re.sub(r"\s+", " ", str(narrator_text or "")).strip()
    text = text.strip('"\u201c\u201d').strip()
    if not text:
        return None
    words = text.split(" ")
    excerpt = " ".join(words[:_ACK_EXCERPT_WORDS])
    excerpt = excerpt.rstrip(".,;:!?").rstrip()
    if not excerpt:
        return None
    ellipsis = "\u2026" if len(words) > _ACK_EXCERPT_WORDS else ""
    try:
        day_no = int(day.get("day_index"))
    except (TypeError, ValueError):
        return None
    date_bit = ""
    if day.get("date"):
        date_bit = " (" + _fmt_date(day["date"]) + ")"
    return ("Got it — I saved that as a Day %d%s travel note: \"%s%s\" %s"
            % (day_no, date_bit, excerpt, ellipsis, _DAY_CAPTURE_FOLLOW_UP))


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
           "capture_modal_answer", "compose_day_capture_ack",
           "SOURCE_SURFACE"]
