"""Trip memoir DOCX builder — WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 4.

Deterministic dual-axis render per WO-TRIP-MEMOIR-01 (no LLM
authoring): Part I walks regions -> nested stops in order, Part II
walks themes with their matching stops, Part III embeds the clustered
photo appendix (include_in_memoir=1 links joined to photos.image_path).

python-docx is imported lazily and guarded — callers get a clear
RuntimeError when it isn't installed (the memoir_export router uses
the same posture with a 503).

WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden evidence (notes / sources
/ photo links stamped hidden=1) is excluded UPSTREAM — the preview
dict (trip_repository.trip_memoir_preview) and the photo rows
(photo_links_with_photo_paths) this builder renders are assembled from
hide-aware repository reads, so a hidden row never reaches this
module regardless of its include_in_memoir flag.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("code.api.services.trip_memoir_docx")


# WO-TRAVEL-DOC-CLOSEOUT-01 — `_safe_caption` MOVED, not deleted.
#
# It lived here and chose the caption for the document. The browser
# preview had no equivalent, so the operator reviewed a count while the
# family received captions. The rule now lives beside the grouping, in
# `trip_repository._safe_photo_caption`, and BOTH consumers read the one
# projection that applies it.
#
# Deliberately not left here as a second copy. Two implementations of
# "which caption is safe to print" would drift, and the direction they
# drift in is unapproved text reaching a family document -- which has
# already happened once on this path.


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

    def _sources(srcs, indent=0.0):
        # Promoted sources (include_in_memoir=1) as a compact Sources block.
        for s in srcs or []:
            label = (s.get("title") or s.get("filename") or
                     s.get("source_type") or "Source").strip()
            h = doc.add_paragraph()
            r = h.add_run("Source — " + label); r.bold = True; r.font.size = Pt(9)
            if indent:
                h.paragraph_format.left_indent = Inches(indent)
            detail = (s.get("summary") or s.get("pasted_text") or
                      s.get("link_url") or "").strip()
            if detail:
                pn = doc.add_paragraph(detail)
                pn.runs[0].font.size = Pt(9)
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
    _sources(preview.get("sources"))

    # ONE projection for the whole appendix -- grouping, captions, file
    # availability and the per-stop counts. Built once, here, so Part I's
    # "· N photos" and Part III's sections cannot disagree, and so the
    # browser preview (which reads the same projection out of
    # `trip_memoir_preview`) shows the operator exactly what the document
    # will contain.
    from .trip_repository import photo_appendix_projection as _proj_fn
    appendix_proj = _proj_fn(rows=list(photo_rows or []))
    _approved_by_stop: Dict[str, int] = appendix_proj.get(
        "approved_by_stop", {})

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
        # Phase closeout: the APPROVED count for this stop, not the trip
        # tree's `photo_count`. That field counts every link on the stop
        # -- unapproved, hidden, and links whose photograph has been
        # soft-deleted -- so a stop could read "· 3 photos" in a document
        # that contains one of them. Derived from `photo_rows`, which is
        # the export set, so the line cannot disagree with the appendix.
        n_photos = _approved_by_stop.get(stop.get("id"), 0)
        if n_photos:
            bits.append(f"· {n_photos} photo{'s' if n_photos != 1 else ''}")
        style = "List Bullet" if depth == 0 else "List Bullet 2"
        doc.add_paragraph(" ".join(bits), style=style)
        if stop.get("notes"):
            note = doc.add_paragraph(str(stop["notes"]))
            note.paragraph_format.left_indent = Inches(0.5 + 0.25 * depth)
            note.runs[0].font.size = Pt(10)
        _story_notes(stop.get("story_notes"), indent=0.5 + 0.25 * depth)
        _sources(stop.get("sources"), indent=0.5 + 0.25 * depth)
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
        _sources(region.get("sources"))
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
    # ── WO-TRAVEL-DOC-CLOSEOUT-01: the document contradicted itself ──
    #
    # This printed "Photos assigned to stops: N · awaiting assignment: M"
    # and then, at the foot of the same section, "(1 photo embedded)".
    # `assigned_photos` is the trip tree's own tally of EVERY link on a
    # stop -- unapproved ones, links whose photograph has since been
    # soft-deleted, and links hidden from review. The appendix embeds
    # only memoir-approved, visible, undeleted photographs. So the
    # section opened with 4 and closed with 1, in the artefact a family
    # reads as the record.
    #
    # The opening line now counts the rows the appendix was actually
    # given. `photo_rows` IS the export set -- `photo_links_with_photo_
    # paths(trip_id, memoir_only=True)` -- so it cannot drift from what
    # follows it.
    #
    # The all-link inventory is not printed at all. It is a workspace
    # number, useful to an operator deciding what to approve, and
    # meaningless to a reader holding the finished document.
    # ── WO-TRAVEL-DOC-CLOSEOUT-01: ONE projection, two consumers ─────
    #
    # This used to group rows itself, keyed by
    # `str(stop_location_name or region_title or "Unplaced")` -- DISPLAY
    # TEXT. Two stops both called "Hotel", or a stop and a region
    # sharing a name, collapsed into one appendix section, so the
    # photographs of two different places silently became one. Keys are
    # stop/region IDs now, and the grouping happens once, in the
    # repository, where the preview reads it too.
    #
    # It also chose its own caption and resolved its own file
    # availability, which is why the preview could promise photographs
    # the document did not contain.
    doc.add_paragraph(
        f"Approved photos in appendix: {appendix_proj.get('approved', 0)}")
    embedded = 0
    skipped = 0
    for group in appendix_proj.get("groups", []):
        doc.add_heading(str(group.get("label") or "Unplaced"), level=2)
        for ph in group.get("photos", []):
            path = ph.get("image_path")
            if not ph.get("available") or not path:
                skipped += 1
                continue
            try:
                doc.add_picture(str(path), width=Inches(4.5))
                cap_bits = [b for b in (str(ph.get("caption") or "").strip(),
                                        str(ph.get("taken_at") or "").strip())
                            if b]
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
        # After file access, because until every path has been tried we
        # do not know how many photographs the document actually holds.
        # A missing file is reported rather than quietly dropped: the
        # reader should not have to count pictures to notice.
        doc.add_paragraph(
            f"({embedded} photo{'s' if embedded != 1 else ''} embedded"
            + (f"; {skipped} unavailable" if skipped else "")
            + ")"
        )

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
