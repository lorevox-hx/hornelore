"""Operator-side travelogue drafting assistant.

WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01.

Turns the material the operator has already gathered for a scope — the
scope's summary, its operator-approved photo evidence anchors, its
location notes, and selected sources — into a first-draft travelogue
paragraph the operator can edit and then explicitly promote.

LAW 3 (operator boundary): this module imports ONLY trip_repository,
travelogue_builder, evidence_text, and llm_interview. It never imports or
touches chat_ws / prompt_composer / extract / runtime71 / activeTripId /
tripStyle / the narrator transcript. It runs no extraction and writes no
narrator memory. `draft_section()` returns text only — it never persists.
Kept drafts are written by the caller as a trip_location_notes
source_type='draft' row (both promotion flags OFF).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from . import trip_repository
from . import travelogue_builder
from .evidence_text import sanitize_for_prompt
from .. import llm_interview

# Stale save-sentinel that leaked into some region summaries; never feed it
# to the model as if it were real evidence.
_SENTINEL_RX = re.compile(r"^\s*MODSAVE-\d+\s*$", re.IGNORECASE)

_MAX_NOTE_CHARS = 600
_MAX_SOURCE_CHARS = 800


def _clean(text: Optional[str]) -> str:
    t = (text or "").strip()
    if not t or _SENTINEL_RX.match(t):
        return ""
    return t


def _resolve_scope(
    trip_id: str, region_id: Optional[str], stop_id: Optional[str]
) -> Optional[Dict[str, Any]]:
    """Return {kind, id, name, summary} for the requested scope, or None if
    the scope row does not belong to this trip. Trip-level when both are
    None."""
    if stop_id:
        stop = trip_repository.stop_get(stop_id)
        if not stop or stop.get("trip_id") != trip_id:
            return None
        name = _clean(stop.get("location_name")) or _clean(stop.get("title")) \
            or "this stop"
        return {"kind": "stop", "id": stop_id, "name": name,
                "summary": _clean(stop.get("notes")),
                "region_id": stop.get("trip_region_id")}
    if region_id:
        region = trip_repository.region_get(region_id)
        if not region or region.get("trip_id") != trip_id:
            return None
        return {"kind": "region", "id": region_id,
                "name": _clean(region.get("title")) or "this region",
                "summary": _clean(region.get("summary")), "region_id": region_id}
    trip = trip_repository.trip_get(trip_id)
    if not trip:
        return None
    return {"kind": "trip", "id": trip_id,
            "name": _clean(trip.get("title")) or "this trip",
            "summary": _clean(trip.get("summary")), "region_id": None}


def _scope_anchors(trip_id: str, scope: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Evidence anchors for the scope, reusing the travelogue builder's
    assembly. The builder already: filters rejected public context, keeps
    unpromoted notes out of the block, excludes raw GPS, and labels
    machine-guess evidence '(draft)'. We keep BOTH approved and draft
    anchors — draft ones stay flagged so the prompt writes them
    suggestively, per the builder's no-invention posture. MODSAVE sentinels
    are dropped. Returns [{label, value, draft: bool}] deduped."""
    outline = travelogue_builder.build_travelogue_outline(trip_id)
    if not outline:
        return []
    blocks = outline.get("blocks") or []

    def _in_scope(b: Dict[str, Any]) -> bool:
        if scope["kind"] == "trip":
            return True
        if scope["kind"] == "region":
            return b.get("region_id") == scope["id"]
        return b.get("stop_id") == scope["id"]

    anchors: List[Dict[str, Any]] = []
    seen = set()
    for b in blocks:
        if not _in_scope(b):
            continue
        for a in (b.get("prose_anchors") or []):
            label = a.get("label") or ""
            value = _clean(a.get("value"))
            if not value:
                continue
            key = (label, value)
            if key in seen:
                continue
            seen.add(key)
            anchors.append({"label": label, "value": value,
                            "draft": "(draft" in label})
    return anchors


def _region_stop_ids(trip_id: str, region_id: str) -> set:
    """Stop ids belonging to a region (so a region scope can pick up notes/
    sources attached to its stops, but not stops from other regions)."""
    tree = trip_repository.trip_tree(trip_id)
    if not tree:
        return set()
    out = set()
    for r in (tree.get("regions") or []):
        if r.get("id") != region_id:
            continue
        for s in (r.get("stops") or []):
            if s.get("id"):
                out.add(s["id"])
    return out


def _in_scope(row: Dict[str, Any], scope: Dict[str, Any],
              region_stop_ids: set) -> bool:
    if scope["kind"] == "trip":
        return True
    if scope["kind"] == "stop":
        return row.get("trip_stop_id") == scope["id"]
    # region scope: direct region rows OR rows on one of the region's stops
    return (row.get("trip_region_id") == scope["id"]
            or (row.get("trip_stop_id") in region_stop_ids))


def _scope_notes(
    trip_id: str, scope: Dict[str, Any], include_note_ids: Optional[List[str]],
    region_stop_ids: set,
) -> List[Dict[str, str]]:
    """Notes for the scope. Promoted notes (include_in_memoir=1) are included
    by default; UNPROMOTED notes (raw Lori/modal captures) are absent UNLESS
    explicitly named in include_note_ids. Mirrors the travelogue builder,
    which keeps unpromoted notes in intake_review, out of the block."""
    rows = trip_repository.location_notes_list(trip_id)
    want = set(include_note_ids or [])
    out: List[Dict[str, str]] = []
    for n in rows:
        if not _in_scope(n, scope, region_stop_ids):
            continue
        promoted = bool(n.get("include_in_memoir"))
        selected = n.get("id") in want
        if not (promoted or selected):
            continue
        text = _clean(n.get("note_text")) or _clean(n.get("answer")) \
            or _clean(n.get("location_name"))
        if not text:
            continue
        out.append({
            "id": n.get("id"),
            "source_type": n.get("source_type") or "note",
            "promoted": promoted,
            "text": text[:_MAX_NOTE_CHARS],
        })
    return out


def _scope_sources(
    trip_id: str, scope: Dict[str, Any], include_source_ids: Optional[List[str]],
    region_stop_ids: set,
) -> List[Dict[str, str]]:
    rows = trip_repository.sources_list(trip_id)
    want = set(include_source_ids or [])
    out: List[Dict[str, str]] = []
    for s in rows:
        if not _in_scope(s, scope, region_stop_ids):
            continue
        promoted = bool(s.get("include_in_memoir"))
        selected = s.get("id") in want
        if not (promoted or selected):
            continue
        body = _clean(s.get("summary")) or _clean(s.get("pasted_text"))
        title = _clean(s.get("title"))
        if not (body or title):
            continue
        out.append({
            "id": s.get("id"),
            "title": title,
            "text": body[:_MAX_SOURCE_CHARS],
        })
    return out


def assemble_context(
    trip_id: str,
    *,
    region_id: Optional[str] = None,
    stop_id: Optional[str] = None,
    include_note_ids: Optional[List[str]] = None,
    include_source_ids: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Read-only preview of exactly what would be sent to the model. Returns
    None if the scope doesn't belong to the trip."""
    scope = _resolve_scope(trip_id, region_id, stop_id)
    if scope is None:
        return None
    region_stop_ids = (_region_stop_ids(trip_id, scope["id"])
                       if scope["kind"] == "region" else set())
    anchors = _scope_anchors(trip_id, scope)
    notes = _scope_notes(trip_id, scope, include_note_ids, region_stop_ids)
    sources = _scope_sources(trip_id, scope, include_source_ids, region_stop_ids)
    has_material = bool(scope.get("summary") or anchors or notes or sources)
    draft_anchor_count = sum(1 for a in anchors if a.get("draft"))
    return {
        "scope": {"kind": scope["kind"], "id": scope["id"],
                  "name": scope["name"]},
        "summary": scope.get("summary") or "",
        "anchors": anchors,
        "draft_anchor_count": draft_anchor_count,
        "notes": notes,
        "sources": sources,
        "has_material": has_material,
    }


def _evidence_text(ctx: Dict[str, Any]) -> str:
    parts: List[str] = []
    if ctx.get("summary"):
        parts.append("Operator summary: " + ctx["summary"])
    approved = [a for a in ctx.get("anchors", []) if not a.get("draft")]
    draft = [a for a in ctx.get("anchors", []) if a.get("draft")]
    if approved:
        parts.append("Approved evidence (may be stated plainly):")
        for a in approved:
            parts.append("- %s: %s" % (a["label"], a["value"]))
    if draft:
        parts.append("Draft evidence (UNCONFIRMED — write suggestively, "
                     "never as fact):")
        for a in draft:
            parts.append("- %s: %s" % (a["label"], a["value"]))
    if ctx.get("notes"):
        parts.append("Operator notes:")
        for n in ctx["notes"]:
            parts.append("- (%s) %s" % (n["source_type"], n["text"]))
    if ctx.get("sources"):
        parts.append("Sources:")
        for s in ctx["sources"]:
            head = (s["title"] + ": ") if s["title"] else ""
            parts.append("- %s%s" % (head, s["text"]))
    # Generous cap: this is a full scope evidence bundle, not a single field.
    return sanitize_for_prompt("\n".join(parts), max_chars=6000)


def draft_section(
    trip_id: str,
    *,
    region_id: Optional[str] = None,
    stop_id: Optional[str] = None,
    instruction: str = "",
    include_note_ids: Optional[List[str]] = None,
    include_source_ids: Optional[List[str]] = None,
    preview_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """Assemble operator-approved context for the scope and (unless
    preview_only) draft a travelogue paragraph from it. Returns None if the
    scope doesn't belong to the trip. NEVER persists — the caller decides
    whether to keep the draft as a source_type='draft' location note."""
    ctx = assemble_context(
        trip_id, region_id=region_id, stop_id=stop_id,
        include_note_ids=include_note_ids,
        include_source_ids=include_source_ids)
    if ctx is None:
        return None

    result: Dict[str, Any] = {"context_preview": ctx, "draft": None,
                              "status": "ok"}
    if preview_only:
        result["status"] = "preview"
        return result
    if not ctx["has_material"]:
        result["status"] = "no_material"
        return result

    instr = (instruction or "").strip() \
        or "Draft a warm, accurate travelogue paragraph from this evidence."
    draft = llm_interview.draft_travel_section(
        scope_title=ctx["scope"]["name"],
        instruction=instr,
        evidence_text=_evidence_text(ctx))
    if not draft:
        result["status"] = "llm_unavailable"
        return result
    result["draft"] = draft.strip()
    return result
