"""Trip memoir DOCX builder — WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 4.

Deterministic dual-axis render per WO-TRIP-MEMOIR-01 (no LLM
authoring): Part I walks regions -> nested stops in order, Part II
walks themes with their matching stops, Part III embeds the clustered
photo appendix (include_in_memoir=1 links joined to photos.image_path).

python-docx is imported lazily and guarded — callers get a clear
RuntimeError when it isn't installed (the memoir_export router uses
the same posture with a 503).
"""
from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("code.api.services.trip_memoir_docx")


def build_trip_docx(
    preview: Dict[str, Any],
    photo_rows: Optional[List[Dict[str, Any]]] = None,
) -> bytes:
    """Render the memoir-preview dict (trip_repository.trip_memoir_preview
    shape) + joined photo rows into DOCX bytes."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "python-docx is not installed on this server. "
            "Install with: pip install python-docx"
        ) from exc

    doc = Document()

    def _story_notes(notes, indent=0.0):
        # Promoted story notes (include_in_memoir=1). Empty stays empty —
        # no invented prose.
        for note in notes or []:
            t = (note.get("note_title") or "").strip()
            body = (note.get("note_text") or "").strip()
            if t:
                h = doc.add_paragraph()
                r = h.add_run(t); r.bold = True; r.font.size = Pt(10)
                if indent:
                    h.paragraph_format.left_indent = Inches(indent)
            if body:
                pn = doc.add_paragraph(body)
                pn.runs[0].font.size = Pt(10)
                if indent:
                    pn.paragraph_format.left_indent = Inches(indent)

    title = preview.get("title") or "Trip Memoir"
    dr = preview.get("date_range") or {}
    doc.add_heading(str(title), level=0)
    date_line = " — ".join(
        [d for d in (dr.get("start"), dr.get("end")) if d]
    )
    if date_line:
        p = doc.add_paragraph(date_line)
        p.runs[0].font.size = Pt(11)
    if preview.get("summary"):
        doc.add_paragraph(str(preview["summary"]))
    _story_notes(preview.get("story_notes"))

    # ── Part I — The Journey in Order ────────────────────────────────
    doc.add_heading("Part I — The Journey in Order", level=1)

    def _stop_paragraph(stop: Dict[str, Any], depth: int) -> None:
        name = stop.get("title") or stop.get("location_name") or ""
        bits = [str(name)]
        ds, de = stop.get("date_start"), stop.get("date_end")
        if ds and de and ds != de:
            bits.append(f"({ds} – {de})")
        elif ds:
            bits.append(f"({ds})")
        stype = stop.get("stop_type")
        if stype and stype not in ("sight",):
            bits.append(f"[{stype}]")
        n_photos = stop.get("photo_count") or 0
        if n_photos:
            bits.append(f"· {n_photos} photo{'s' if n_photos != 1 else ''}")
        style = "List Bullet" if depth == 0 else "List Bullet 2"
        doc.add_paragraph(" ".join(bits), style=style)
        if stop.get("notes"):
            note = doc.add_paragraph(str(stop["notes"]))
            note.paragraph_format.left_indent = Inches(0.5 + 0.25 * depth)
            note.runs[0].font.size = Pt(10)
        _story_notes(stop.get("story_notes"), indent=0.5 + 0.25 * depth)
        for child in stop.get("day_trips", []):
            _stop_paragraph(child, depth + 1)

    for i, region in enumerate(preview.get("part_one_journey_in_order", []), 1):
        heading_bits = [f"{i}. {region.get('region') or ''}"]
        rdr = region.get("date_range") or {}
        if rdr.get("start"):
            heading_bits.append(f"({rdr.get('start')} – {rdr.get('end') or ''})")
        doc.add_heading(" ".join(heading_bits), level=2)
        if region.get("base_address"):
            doc.add_paragraph(f"Base: {region['base_address']}")
        if region.get("summary"):
            doc.add_paragraph(str(region["summary"]))
        _story_notes(region.get("story_notes"))
        for stop in region.get("stops", []):
            _stop_paragraph(stop, 0)

    # ── Part II — Themes That Ran Through the Trip ───────────────────
    doc.add_heading("Part II — Themes That Ran Through the Trip", level=1)
    themes = preview.get("part_two_themes", [])
    if not themes:
        doc.add_paragraph("(No themes recorded for this trip yet.)")
    for theme in themes:
        doc.add_heading(str(theme.get("theme") or ""), level=2)
        if theme.get("description"):
            doc.add_paragraph(str(theme["description"]))
        stops = theme.get("stops") or []
        if stops:
            doc.add_paragraph(
                "Across: " + ", ".join(str(s) for s in stops)
            )

    # ── Part III — Photo Appendix ────────────────────────────────────
    doc.add_heading("Part III — Photo Appendix", level=1)
    appendix = preview.get("part_three_photo_appendix") or {}
    doc.add_paragraph(
        f"Photos assigned to stops: {appendix.get('assigned_photos', 0)} · "
        f"awaiting assignment: {appendix.get('unassigned_photos', 0)}"
    )
    embedded = 0
    skipped = 0
    # Group photos under their stop instead of a single flat list. Rows with
    # no stop fall under "Unplaced".
    _groups: Dict[str, List[Dict[str, Any]]] = {}
    _order: List[str] = []
    for row in photo_rows or []:
        key = str(row.get("stop_location_name") or "Unplaced")
        if key not in _groups:
            _groups[key] = []
            _order.append(key)
        _groups[key].append(row)
    for key in _order:
        doc.add_heading(key, level=2)
        for row in _groups[key]:
            path = row.get("photo_image_path")
            if not path or not os.path.isfile(str(path)):
                skipped += 1
                continue
            try:
                doc.add_picture(str(path), width=Inches(4.5))
                caption = (
                    row.get("narrator_caption")
                    or row.get("caption")
                    or row.get("photo_description")
                    or ""
                )
                when = row.get("taken_at") or row.get("photo_date_value") or ""
                cap_bits = [b for b in (str(caption).strip(), str(when).strip()) if b]
                if cap_bits:
                    cp = doc.add_paragraph(" — ".join(cap_bits))
                    cp.runs[0].font.size = Pt(9)
                embedded += 1
            except Exception as exc:
                skipped += 1
                logger.warning(
                    "[trip-docx] photo embed failed path=%s: %s", path, exc,
                )
    if photo_rows is not None:
        doc.add_paragraph(
            f"({embedded} photo{'s' if embedded != 1 else ''} embedded"
            + (f"; {skipped} unavailable" if skipped else "")
            + ")"
        )

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
