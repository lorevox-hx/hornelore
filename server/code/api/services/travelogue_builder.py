"""Travelogue outline builder — WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01.

Pure READ-ONLY service that assembles the OPERATOR Travel Doc's
evidence-rich travelogue outline from canonical rows. It produces
STRUCTURE + labeled evidence anchors, NOT prose: each block carries a
`llm_prompt` string that instructs a (later, operator-triggered, LOCAL)
LLM pass to shape prose FROM the anchors — this module never calls an
LLM, never touches the web, and never writes.

LAW-3 posture: imports trip_repository (data) plus the packet helper
from travel_doc_lori_modal (shared approved/draft semantics) ONLY —
never chat_ws, prompt_composer, extract, runtime71, or shelf state.

Evidence rules (locked):
- Taken dates come ONLY from photo date_value / taken_at / the filename
  guess. Upload/save/modified timestamps are NEVER taken dates and are
  never read here.
- Raw GPS never enters the outline; `raw_gps_available` is a boolean.
- Draft evidence is labeled "(draft)" and flips the block's
  needs_review flag; approved evidence is labeled approved.
- Promoted notes (include_in_memoir=1) render inside their block;
  unpromoted notes (Lori modal sandbox captures included) are listed in
  a separate `intake_review` section. NO auto-promotion.
- Public/web context is labeled public context, never personal memory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import trip_repository
from .travel_doc_lori_modal import _packet_from_link

_ITINERARY_TYPES = ("base", "lodging", "transit")
_DISCOVERY_TYPES = ("sight", "meal", "day_trip")
_CODA_TYPES = ("memory_anchor",)

_BLOCK_NAMES = {
    "region_chapter": "Region Chapter",
    "itinerary_tile": "Itinerary Tile",
    "discovery_tile": "Discovery Tile",
    "sensory_coda": "Sensory Coda",
}

_NO_INVENTION_RULE = (
    "Write from ONLY the labeled evidence anchors above. You may shape "
    "the prose warmly, but you may NOT invent personal facts, names, "
    "dates, feelings, or events that are not in the anchors. Evidence "
    "labeled (draft) must stay suggestive — 'the photo data suggests…', "
    "'the public context suggests…' — never certain; approved evidence "
    "may speak plainly ('the approved Travel Doc context says…'). "
    "Public context is public background, never personal memory. Never "
    "say 'I can see'. Upload, save, or modified timestamps are never "
    "taken dates."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _photo_evidence(link: Dict[str, Any]) -> Dict[str, Any]:
    """Extended photo evidence packet for one photo link. Reuses the
    modal's approved/draft packet semantics; adds identity + review
    metadata the travelogue needs. Never raw lat/lon — only the
    `raw_gps_available` boolean."""
    pkt = _packet_from_link(link)
    pkt.update({
        "photo_id": link.get("photo_id"),
        "thumbnail_path": ("/api/photos/%s/thumb" % link.get("photo_id"))
        if link.get("photo_id") else None,
        "date_source": link.get("photo_date_source"),
        "caption": link.get("caption"),
        "operator_context_note": link.get("operator_context_note"),
        "include_in_memoir": bool(link.get("include_in_memoir")),
        "narrator_ready": bool(link.get("photo_narrator_ready")),
        "raw_gps_available": bool(link.get("photo_gps_present")),
    })
    return pkt


def _photo_anchors(pkt: Dict[str, Any]) -> (List[Dict[str, str]]):
    """Labeled evidence anchors for one photo packet."""
    anchors: List[Dict[str, str]] = []
    if pkt.get("approved_taken_date"):
        anchors.append({"label": "approved taken date",
                        "value": str(pkt["approved_taken_date"])})
    elif pkt.get("draft_date"):
        if pkt.get("date_source") == "exif":
            label = "EXIF date (draft)"
        elif pkt.get("draft_date") == pkt.get("filename_guess"):
            label = "filename date guess (draft)"
        else:
            label = "file date (draft)"
        anchors.append({"label": label, "value": str(pkt["draft_date"])})
    if pkt.get("approved_place"):
        anchors.append({"label": "approved place",
                        "value": str(pkt["approved_place"])})
    elif pkt.get("draft_place"):
        anchors.append({"label": "place label (draft)",
                        "value": str(pkt["draft_place"])})
    if pkt.get("narrator_caption"):
        anchors.append({"label": "narrator memory (caption)",
                        "value": str(pkt["narrator_caption"])})
    if pkt.get("approved_caption"):
        anchors.append({"label": "approved caption",
                        "value": str(pkt["approved_caption"])})
    if pkt.get("approved_context"):
        anchors.append({"label": "approved operator note",
                        "value": str(pkt["approved_context"])})
    if pkt.get("draft_context"):
        anchors.append({"label": "photo context (draft)",
                        "value": str(pkt["draft_context"])})
    if pkt.get("raw_gps_available"):
        anchors.append({"label": "GPS (private)",
                        "value": "coordinates recorded — not shown; "
                                 "reverse geocode available"})
    return anchors


def _photo_badges(pkt: Dict[str, Any]) -> List[str]:
    badges: List[str] = []
    if pkt.get("approved_taken_date") or pkt.get("approved_place") \
            or pkt.get("approved_caption") or pkt.get("approved_context"):
        badges.append("approved")
    if pkt.get("date_source") == "exif":
        badges.append("EXIF")
    if pkt.get("draft_date") and pkt.get("draft_date") == pkt.get("filename_guess"):
        badges.append("filename")
    if pkt.get("draft_date") or pkt.get("draft_place") \
            or pkt.get("draft_context"):
        badges.append("draft")
    if pkt.get("narrator_caption"):
        badges.append("narrator memory")
    if pkt.get("operator_context_note"):
        badges.append("operator note")
    if pkt.get("raw_gps_available"):
        badges.append("GPS")
    return badges


def _note_entry(n: Dict[str, Any]) -> Dict[str, Any]:
    surface = n.get("source_surface")
    if surface == "travel_doc_modal":
        badge = "Lori modal capture"
    elif n.get("source_type") == "lori":
        badge = "Lori capture"
    elif n.get("source_type") == "operator":
        badge = "operator note"
    else:
        badge = str(n.get("source_type") or "note")
    return {
        "note_id": n.get("id"),
        "note_title": n.get("note_title"),
        "note_text": n.get("note_text"),
        "source_type": n.get("source_type"),
        "source_surface": surface,
        "photo_link_id": n.get("photo_link_id"),
        "badge": badge,
        "promoted": bool(n.get("include_in_memoir")),
    }


def _pub_entry(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "context_id": r.get("id"),
        "source_type": r.get("source_type"),
        "source_url": r.get("source_url"),
        "result_summary": r.get("result_summary"),
        "approved_for_lori": bool(r.get("approved_for_lori")),
        "include_in_memoir": bool(r.get("include_in_memoir")),
        "badge": ("approved public context" if r.get("approved_for_lori")
                  else "public context (draft)"),
    }


def _pub_anchor(r: Dict[str, Any]) -> Dict[str, str]:
    kind = str(r.get("source_type") or "public context").replace("_", " ")
    if r.get("approved_for_lori"):
        label = "approved public context (%s)" % kind
    else:
        label = "public context (draft, %s)" % kind
    return {"label": label, "value": str(r.get("result_summary") or "")}


def _note_anchor(n: Dict[str, Any]) -> Dict[str, str]:
    if n.get("source_surface") == "travel_doc_modal" \
            or n.get("source_type") == "lori":
        label = "narrator memory (promoted Lori capture)"
    else:
        label = "operator note (promoted)"
    return {"label": label, "value": str(n.get("note_text") or "")}


def _finish_block(block: Dict[str, Any]) -> Dict[str, Any]:
    """Compute needs_review + llm_prompt from the assembled anchors."""
    anchors = block.get("prose_anchors") or []
    badges = block.get("provenance_badges") or []
    block["needs_review"] = any(
        "(draft" in (a.get("label") or "") for a in anchors
    ) or ("draft" in badges)
    name = _BLOCK_NAMES.get(block.get("block_type"), "block")
    lines = ["- %s: %s" % (a.get("label"), a.get("value")) for a in anchors]
    block["llm_prompt"] = (
        "Write a %s titled '%s' using ONLY these evidence anchors:\n%s\n%s"
        % (name, block.get("title") or "", "\n".join(lines) or "- (none)",
           _NO_INVENTION_RULE)
    )
    return block


def _dedupe_badges(badges: List[str]) -> List[str]:
    seen: List[str] = []
    for b in badges:
        if b and b not in seen:
            seen.append(b)
    return seen


def build_travelogue_outline(trip_id: str) -> Optional[Dict[str, Any]]:
    """Structured travelogue draft outline: TRIP OVERVIEW + ordered
    blocks (Region Chapter / Itinerary Tile / Discovery Tile / Sensory
    Coda) + intake_review section for unpromoted sandbox notes. Returns
    None when the trip doesn't exist. Read-only; no LLM; no web."""
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        return None

    links = trip_repository.photo_links_list(trip_id)
    notes = trip_repository.location_notes_list(trip_id)
    pub_rows = trip_repository.public_context_list(trip_id)

    # ── group evidence by scope ─────────────────────────────────────────
    links_by_stop: Dict[str, List[Dict[str, Any]]] = {}
    links_by_region: Dict[str, List[Dict[str, Any]]] = {}
    link_stop: Dict[str, Optional[str]] = {}
    for l in links:
        link_stop[l.get("id")] = l.get("trip_stop_id")
        if l.get("trip_stop_id"):
            links_by_stop.setdefault(l["trip_stop_id"], []).append(l)
        elif l.get("trip_region_id"):
            links_by_region.setdefault(l["trip_region_id"], []).append(l)

    promoted_by_stop: Dict[str, List[Dict[str, Any]]] = {}
    promoted_by_region: Dict[str, List[Dict[str, Any]]] = {}
    promoted_floating: List[Dict[str, Any]] = []
    intake_notes: List[Dict[str, Any]] = []
    for n in notes:
        if n.get("include_in_memoir"):
            if n.get("trip_stop_id"):
                promoted_by_stop.setdefault(
                    n["trip_stop_id"], []).append(n)
            elif n.get("trip_region_id"):
                promoted_by_region.setdefault(
                    n["trip_region_id"], []).append(n)
            else:
                promoted_floating.append(n)
        else:
            # Unpromoted notes (Lori modal sandbox captures included)
            # NEVER render inside blocks — they queue for review.
            intake_notes.append(n)

    pub_by_photo_link: Dict[str, List[Dict[str, Any]]] = {}
    pub_by_stop: Dict[str, List[Dict[str, Any]]] = {}
    pub_by_region: Dict[str, List[Dict[str, Any]]] = {}
    pub_trip: List[Dict[str, Any]] = []
    for r in pub_rows:
        # Preflight review-follow-up (2026-07-11): rejected public rows
        # never enter the travelogue (hide-not-delete parity with
        # trip_photo_context).
        if r.get("rejected"):
            continue
        if r.get("photo_link_id"):
            pub_by_photo_link.setdefault(
                r["photo_link_id"], []).append(r)
            # A photo-scoped row also reaches its stop's block below via
            # the photo packet lookup.
        elif r.get("trip_stop_id"):
            pub_by_stop.setdefault(r["trip_stop_id"], []).append(r)
        elif r.get("trip_region_id"):
            pub_by_region.setdefault(r["trip_region_id"], []).append(r)
        else:
            pub_trip.append(r)

    def _pub_for_stop(stop_id: str) -> List[Dict[str, Any]]:
        rows = list(pub_by_stop.get(stop_id, []))
        for l in links_by_stop.get(stop_id, []):
            rows.extend(pub_by_photo_link.get(l.get("id"), []))
        return rows

    # ── flatten stops in tree (route) order ─────────────────────────────
    all_stops: List[Dict[str, Any]] = []

    def _walk(stop: Dict[str, Any], region: Dict[str, Any]) -> None:
        stop["_region_id"] = region.get("id")
        all_stops.append(stop)
        for c in stop.get("children", []):
            _walk(c, region)

    for region in tree.get("regions", []):
        for s in region.get("stops", []):
            _walk(s, region)

    blocks: List[Dict[str, Any]] = []

    # ── per-region blocks ───────────────────────────────────────────────
    for region in tree.get("regions", []):
        region_stops = [s for s in all_stops
                        if s.get("_region_id") == region.get("id")]

        # REGION CHAPTER
        anchors: List[Dict[str, str]] = []
        badges: List[str] = []
        if region.get("start_date") or region.get("end_date"):
            anchors.append({
                "label": "region dates (operator)",
                "value": " to ".join(
                    [d for d in (region.get("start_date"),
                                 region.get("end_date")) if d]),
            })
        if region.get("country_or_area"):
            anchors.append({"label": "country or area (operator)",
                            "value": str(region["country_or_area"])})
        if region.get("base_address"):
            anchors.append({"label": "base / lodging (operator)",
                            "value": str(region["base_address"])})
        if region.get("summary"):
            anchors.append({"label": "operator summary",
                            "value": str(region["summary"])})
            badges.append("operator note")
        region_notes = promoted_by_region.get(region.get("id"), [])
        for n in region_notes:
            anchors.append(_note_anchor(n))
            badges.append(_note_entry(n)["badge"])
        region_pub = pub_by_region.get(region.get("id"), [])
        for r in region_pub:
            anchors.append(_pub_anchor(r))
            badges.append(_pub_entry(r)["badge"])
        region_links = list(links_by_region.get(region.get("id"), []))
        blocks.append(_finish_block({
            "block_type": "region_chapter",
            "title": region.get("title") or "Region",
            "region_id": region.get("id"),
            "date_start": region.get("start_date"),
            "date_end": region.get("end_date"),
            "summary": region.get("summary"),
            "prose_anchors": anchors,
            "provenance_badges": _dedupe_badges(badges),
            "photo_link_ids": [l.get("id") for l in region_links],
            "photos": [_photo_evidence(l) for l in region_links[:3]],
            "note_ids": [n.get("id") for n in region_notes],
            "notes": [_note_entry(n) for n in region_notes],
            "public_context": [_pub_entry(r) for r in region_pub],
        }))

        # ITINERARY TILE — base / lodging / transit stops of this region
        it_stops = [s for s in region_stops
                    if (s.get("stop_type") or "") in _ITINERARY_TYPES]
        if it_stops:
            anchors = []
            badges = []
            stop_entries: List[Dict[str, Any]] = []
            note_ids: List[str] = []
            link_ids: List[str] = []
            for s in it_stops:
                span = " to ".join([d for d in (s.get("date_start"),
                                                s.get("date_end")) if d])
                anchors.append({
                    "label": "%s stop (operator)" % (s.get("stop_type")),
                    "value": (s.get("location_name") or s.get("title")
                              or "stop") + ((" — " + span) if span else ""),
                })
                if s.get("notes"):
                    anchors.append({"label": "operator note",
                                    "value": str(s["notes"])})
                    badges.append("operator note")
                s_notes = promoted_by_stop.get(s.get("id"), [])
                for n in s_notes:
                    anchors.append(_note_anchor(n))
                    badges.append(_note_entry(n)["badge"])
                    note_ids.append(n.get("id"))
                s_links = links_by_stop.get(s.get("id"), [])
                link_ids.extend([l.get("id") for l in s_links])
                for r in _pub_for_stop(s.get("id")):
                    anchors.append(_pub_anchor(r))
                    badges.append(_pub_entry(r)["badge"])
                stop_entries.append({
                    "stop_id": s.get("id"),
                    "location_name": s.get("location_name"),
                    "stop_type": s.get("stop_type"),
                    "date_start": s.get("date_start"),
                    "date_end": s.get("date_end"),
                    "notes": s.get("notes"),
                    "promoted_notes": [
                        _note_entry(n) for n in s_notes],
                    "photo_link_ids": [l.get("id") for l in s_links],
                    "public_context": [
                        _pub_entry(r) for r in _pub_for_stop(s.get("id"))],
                })
            blocks.append(_finish_block({
                "block_type": "itinerary_tile",
                "title": "%s — getting there and staying" % (
                    region.get("title") or "Region"),
                "region_id": region.get("id"),
                "stops": stop_entries,
                "prose_anchors": anchors,
                "provenance_badges": _dedupe_badges(badges),
                "photo_link_ids": link_ids,
                "note_ids": note_ids,
                "public_context": [],
            }))

        # DISCOVERY TILE — one per sight/meal/day_trip stop (route order)
        for s in region_stops:
            if (s.get("stop_type") or "") not in _DISCOVERY_TYPES:
                continue
            anchors = []
            badges = []
            span = " to ".join([d for d in (s.get("date_start"),
                                            s.get("date_end")) if d])
            anchors.append({
                "label": "place (operator)",
                "value": (s.get("location_name") or s.get("title")
                          or "stop") + ((" — " + span) if span else ""),
            })
            if s.get("notes"):
                anchors.append({"label": "operator note",
                                "value": str(s["notes"])})
                badges.append("operator note")
            s_links = links_by_stop.get(s.get("id"), [])
            packets = [_photo_evidence(l) for l in s_links[:3]]
            for pkt in packets:
                anchors.extend(_photo_anchors(pkt))
                badges.extend(_photo_badges(pkt))
            s_notes = promoted_by_stop.get(s.get("id"), [])
            for n in s_notes:
                anchors.append(_note_anchor(n))
                badges.append(_note_entry(n)["badge"])
            s_pub = _pub_for_stop(s.get("id"))
            for r in s_pub:
                anchors.append(_pub_anchor(r))
                badges.append(_pub_entry(r)["badge"])
            blocks.append(_finish_block({
                "block_type": "discovery_tile",
                "title": s.get("location_name") or s.get("title") or "Stop",
                "region_id": region.get("id"),
                "stop_id": s.get("id"),
                "stop_type": s.get("stop_type"),
                "date_start": s.get("date_start"),
                "date_end": s.get("date_end"),
                "prose_anchors": anchors,
                "provenance_badges": _dedupe_badges(badges),
                "photo_link_ids": [l.get("id") for l in s_links],
                "photos": packets,
                "note_ids": [n.get("id") for n in s_notes],
                "notes": [_note_entry(n) for n in s_notes],
                "public_context": [_pub_entry(r) for r in s_pub],
            }))

    # ── SENSORY CODA — memory anchors + floating promoted notes ─────────
    coda_stops = [s for s in all_stops
                  if (s.get("stop_type") or "") in _CODA_TYPES]
    anchors = []
    badges = []
    coda_note_ids: List[str] = []
    coda_link_ids: List[str] = []
    coda_stop_entries: List[Dict[str, Any]] = []
    for s in coda_stops:
        anchors.append({
            "label": "memory anchor (operator)",
            "value": (s.get("location_name") or s.get("title") or "moment")
            + ((" — " + str(s.get("notes"))) if s.get("notes") else ""),
        })
        s_notes = promoted_by_stop.get(s.get("id"), [])
        for n in s_notes:
            anchors.append(_note_anchor(n))
            badges.append(_note_entry(n)["badge"])
            coda_note_ids.append(n.get("id"))
        s_links = links_by_stop.get(s.get("id"), [])
        coda_link_ids.extend([l.get("id") for l in s_links])
        coda_stop_entries.append({
            "stop_id": s.get("id"),
            "location_name": s.get("location_name"),
            "notes": s.get("notes"),
            "promoted_notes": [_note_entry(n) for n in s_notes],
            "photo_link_ids": [l.get("id") for l in s_links],
        })
    for n in promoted_floating:
        anchors.append(_note_anchor(n))
        badges.append(_note_entry(n)["badge"])
        coda_note_ids.append(n.get("id"))
    blocks.append(_finish_block({
        "block_type": "sensory_coda",
        "title": "What stayed with you",
        "memory_anchor_stops": coda_stop_entries,
        "floating_notes": [_note_entry(n) for n in promoted_floating],
        "prose_anchors": anchors,
        "provenance_badges": _dedupe_badges(badges),
        "photo_link_ids": coda_link_ids,
        "note_ids": coda_note_ids,
        "public_context": [],
    }))

    # ── overview + intake ───────────────────────────────────────────────
    approved_evidence = 0
    draft_evidence = 0
    for l in links:
        pkt = _packet_from_link(l)
        approved_evidence += sum(1 for k in (
            "approved_taken_date", "approved_place", "approved_caption",
            "approved_context") if pkt.get(k))
        draft_evidence += sum(1 for k in (
            "draft_date", "draft_place", "draft_context") if pkt.get(k))
    for r in pub_rows:
        if r.get("approved_for_lori"):
            approved_evidence += 1
        else:
            draft_evidence += 1

    sandbox_notes = [n for n in intake_notes
                     if n.get("source_surface") == "travel_doc_modal"]

    overview = {
        "title": tree.get("title"),
        "date_span": {"start": tree.get("start_date"),
                      "end": tree.get("end_date")},
        "summary": tree.get("summary"),
        "region_count": len(tree.get("regions", [])),
        "stop_count": len(all_stops),
        "photo_count": len(links),
        "approved_evidence_count": approved_evidence,
        "draft_evidence_count": draft_evidence,
        "sandbox_note_count": len(sandbox_notes),
        "public_context_count": len(pub_rows),
        "public_context": [_pub_entry(r) for r in pub_trip],
    }

    return {
        "trip_id": trip_id,
        "generated_at": _now_iso(),
        "overview": overview,
        "blocks": blocks,
        "intake_review": {
            "count": len(intake_notes),
            "notes": [_note_entry(n) for n in intake_notes],
        },
    }


__all__ = ["build_travelogue_outline"]
