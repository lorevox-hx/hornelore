"""
Lorevox Memoir Export Router
=============================
Provides server-side DOCX export for memoir content.

Endpoints:
  POST  /api/memoir/export-docx  — accept memoir JSON, return .docx file

Design rules:
  - Export reflects exactly what the user sees (threads or draft).
  - Scaffold placeholder content is never exported.
  - Meaning sections (Turning Points, Hard Moments, etc.) become DOCX headings.
  - Structural sections (Family & Relationships, Work, etc.) become secondary headings.
  - Draft state is rendered as plain prose paragraphs with section headers.
  - Threads state is rendered as grouped bullet lists per section.
  - Media Builder: attached_photos inlines images after section headings (graceful skip on error).

WO-ML-04 / Phase 4B (2026-05-07) — bilingual memoir export:
  - target_language="en" (default): English-only output, byte-stable
    with pre-Phase-4B callers.
  - target_language="es": Spanish-only output. Each section's items +
    prose pass through services.translation.translate_text() before
    rendering. Title + subtitle render with their Spanish equivalents.
    On translation failure, the affected section falls back to its
    English source text so the caller always gets a usable docx.
  - target_language="bilingual": both languages in the same document.
    Rendered as paired blocks per section (English first, Spanish
    immediately below) so a bilingual reader can follow either side.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger("memoir_export")

try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

router = APIRouter(prefix="/api/memoir", tags=["memoir-export"])


# ── Request models ─────────────────────────────────────────────────────────────

class MemoirSection(BaseModel):
    """A single named section with zero or more thread items."""
    id: str
    label: str
    items: List[str] = Field(default_factory=list)


class AttachedPhoto(BaseModel):
    """A photo attached to a memoir section (Media Builder — Task 4)."""
    media_id: str
    section_key: str
    file_path: str          # absolute server-local path; python-docx reads this directly
    description: str = ""
    taken_at: str = ""


class MemoirExportRequest(BaseModel):
    """
    Shape sent by the frontend's memoirExportDOCX() function.
    memoir_state: "threads" | "draft"
    narrator_name: display name for the document title
    sections: populated sections only (empty sections are pre-filtered by the caller)
    prose: flat prose string for draft state (paragraphs joined by \\n\\n)
    arc_roles: which narrative arc parts are present (display only, optional)
    attached_photos: photos to inline at their section (empty list = no change in behavior)

    WO-ML-04 / Phase 4B (2026-05-07) — bilingual memoir export:
      source_language: ISO-639-1 code of the source content. Default
        "en". Used as the source for translation calls; also informs
        the chrome (subtitle wording) when target_language matches.
      target_language: ISO-639-1 code OR "bilingual". Default "en".
        - "en" → no translation, English-only output (byte-stable
          with pre-Phase-4B callers).
        - "es" → translate every section item + prose to Spanish
          via services.translation.translate_text() before render.
        - "bilingual" → render English + Spanish side-by-side.
    """
    narrator_name: str = Field(default="Narrator")
    memoir_state: str = Field(default="threads")
    sections: List[MemoirSection] = Field(default_factory=list)
    prose: Optional[str] = Field(default=None)
    arc_roles: List[str] = Field(default_factory=list)
    attached_photos: List[AttachedPhoto] = Field(default_factory=list)
    source_language: str = Field(default="en")
    target_language: str = Field(default="en")


# ── Helpers ────────────────────────────────────────────────────────────────────

# Colour constants for the Lorevox brand tone (dark warm palette)
# Guarded: RGBColor only exists when python-docx is installed.
if _DOCX_AVAILABLE:
    _DARK_BROWN = RGBColor(0x3B, 0x2A, 0x1A)   # heading primary
    _WARM_GREY  = RGBColor(0x5A, 0x55, 0x50)   # heading secondary
    _GOLD       = RGBColor(0xAA, 0x88, 0x44)   # accent line / arc label
else:
    _DARK_BROWN = _WARM_GREY = _GOLD = None


def _photos_for_section(req: MemoirExportRequest, section_key: str) -> List[AttachedPhoto]:
    """Return all photos attached to a given memoir section key."""
    return [p for p in req.attached_photos if p.section_key == section_key]


# ── WO-ML-04 / Phase 4B helpers ───────────────────────────────────────────────

# Title + subtitle translations for the docx chrome. The narrator's
# memoir CONTENT is translated by the LLM service; this dict handles
# the deterministic boilerplate so we don't burn LLM tokens on
# four-word strings that are stable across every memoir.
_CHROME_STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "threads_title":    "Story Threads — {narrator}",
        "threads_subtitle": "Building Blocks Collected",
        "draft_title":      "Memoir Draft — {narrator}",
        "draft_subtitle":   "Your Words, Taking Shape",
        "story_arc_label":  "Story arc: {roles}",
        "photos_heading":   "Photos",
    },
    "es": {
        "threads_title":    "Hilos de Historia — {narrator}",
        "threads_subtitle": "Piezas Recogidas",
        "draft_title":      "Borrador de Memorias — {narrator}",
        "draft_subtitle":   "Tus Palabras, Tomando Forma",
        "story_arc_label":  "Arco narrativo: {roles}",
        "photos_heading":   "Fotos",
    },
}


def _chrome(target_lang: str, key: str) -> str:
    """Return a chrome string in the requested language, falling back
    to English when the target language has no entry. Stays
    byte-stable when target_lang == 'en'."""
    table = _CHROME_STRINGS.get(target_lang) or _CHROME_STRINGS["en"]
    if key in table:
        return table[key]
    return _CHROME_STRINGS["en"].get(key, "")


def _normalize_target_lang(req: MemoirExportRequest) -> str:
    """Return one of: 'en' (default, byte-stable) | 'es' | 'bilingual'.
    Coerces unknown values to 'en' so a malformed request still
    produces an English memoir rather than crashing."""
    raw = (req.target_language or "en").strip().lower()
    if raw in ("en", "es", "bilingual"):
        return raw
    logger.warning(
        "[memoir-docx][lang] unsupported target_language=%r — defaulting to 'en'",
        req.target_language,
    )
    return "en"


def _translate_request_content(
    req: MemoirExportRequest,
    target_lang: str,
) -> MemoirExportRequest:
    """Build a new MemoirExportRequest with all narrator content
    translated to `target_lang`. Section labels, item bullets, and
    prose paragraphs all pass through services.translation. Photo
    metadata and arc_roles are NOT translated (stable identifiers /
    operator-side labels).

    On translation failure for any single field, that field falls
    back to its English source — so the docx always renders.

    Used for target_lang='es' export. NOT used for 'bilingual' (that
    path renders both source + translated content side-by-side and
    handles its own translation calls inline).
    """
    # Lazy import — translation service hits the LLM and pulls in
    # urllib network paths; keep memoir export importable in
    # contexts where the LLM stack isn't available (eg unit tests).
    from ..services import translation as _translation

    source_lang = (req.source_language or "en").strip().lower() or "en"

    def _t(text: Optional[str]) -> str:
        if not text:
            return text or ""
        try:
            return _translation.translate_text(
                text,
                source_lang=source_lang,
                target_lang=target_lang,
                narrator_name=req.narrator_name or None,
            )
        except Exception as exc:
            logger.warning(
                "[memoir-docx][translate] failed text_len=%d err=%s — passing through",
                len(text), exc,
            )
            return text

    translated_sections: List[MemoirSection] = []
    for sec in req.sections:
        translated_sections.append(MemoirSection(
            id=sec.id,
            label=_t(sec.label),
            items=[_t(item) for item in (sec.items or [])],
        ))

    translated_prose: Optional[str] = None
    if req.prose:
        # Translate paragraph-by-paragraph so the cache hits on
        # individual paragraphs (a memoir reuses paragraphs across
        # exports more often than the whole prose blob).
        paragraphs = req.prose.split("\n\n")
        out_paragraphs = [_t(p) if p.strip() else p for p in paragraphs]
        translated_prose = "\n\n".join(out_paragraphs)

    return MemoirExportRequest(
        narrator_name=req.narrator_name,
        memoir_state=req.memoir_state,
        sections=translated_sections,
        prose=translated_prose,
        arc_roles=req.arc_roles,
        attached_photos=req.attached_photos,
        source_language=req.source_language,
        target_language=target_lang,
    )


def _add_photo_to_doc(doc: Any, photo: AttachedPhoto) -> None:
    """
    Insert photo inline in the document.
    Gracefully skips on any error (corrupt file, format unsupported, missing file).
    """
    try:
        path = Path(photo.file_path)
        if not path.exists():
            logger.warning("[memoir-docx] Photo not found on disk: %s — skipping", path)
            return
        doc.add_picture(str(path), width=Inches(3.5))
        # Caption paragraph
        caption_parts = []
        if photo.description:
            caption_parts.append(photo.description)
        if photo.taken_at:
            caption_parts.append(photo.taken_at)
        if caption_parts:
            cap = doc.add_paragraph(" — ".join(caption_parts))
            if cap.runs:
                cap.runs[0].font.size = Pt(9)
                cap.runs[0].font.italic = True
                cap.runs[0].font.color.rgb = _WARM_GREY
    except Exception as exc:
        logger.warning("[memoir-docx] Could not add photo %s: %s — skipping", photo.file_path, exc)


# ── DOCX builders ──────────────────────────────────────────────────────────────

def _build_threads_docx(req: MemoirExportRequest, *, render_lang: str = "en") -> bytes:
    """Build DOCX for threads state: grouped sections with bullet items.

    `render_lang` controls only the chrome (title / subtitle / photos
    heading / arc-roles label). Section content has already been
    translated upstream by _translate_request_content when needed.
    """
    doc = Document()

    # Title
    title_text = _chrome(render_lang, "threads_title").format(narrator=req.narrator_name)
    title = doc.add_heading(title_text, level=0)
    title.runs[0].font.color.rgb = _DARK_BROWN

    # Subtitle
    sub = doc.add_paragraph(_chrome(render_lang, "threads_subtitle"))
    sub.runs[0].font.italic = True
    sub.runs[0].font.color.rgb = _WARM_GREY

    # Arc coverage line (if available) — arc_roles themselves are
    # operator-side labels (display-only), not translated.
    if req.arc_roles:
        arc_line = doc.add_paragraph()
        arc_label = _chrome(render_lang, "story_arc_label").format(
            roles=' · '.join(req.arc_roles),
        )
        arc_run = arc_line.add_run(arc_label)
        arc_run.font.size = Pt(10)
        arc_run.font.color.rgb = _GOLD

    doc.add_paragraph()  # spacer

    # Sections
    for sec in req.sections:
        if not sec.items:
            continue  # skip empty — export truth rule
        h = doc.add_heading(sec.label, level=2)
        h.runs[0].font.color.rgb = _DARK_BROWN

        # Inline photos for this section (Media Builder)
        for photo in _photos_for_section(req, sec.id):
            _add_photo_to_doc(doc, photo)

        for item in sec.items:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)

        doc.add_paragraph()  # spacer between sections

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_draft_docx(req: MemoirExportRequest, *, render_lang: str = "en") -> bytes:
    """Build DOCX for draft state: prose paragraphs, optionally with arc headings.

    `render_lang` controls chrome only; prose content is already
    translated upstream when needed (see _translate_request_content)."""
    doc = Document()

    title_text = _chrome(render_lang, "draft_title").format(narrator=req.narrator_name)
    title = doc.add_heading(title_text, level=0)
    title.runs[0].font.color.rgb = _DARK_BROWN

    sub = doc.add_paragraph(_chrome(render_lang, "draft_subtitle"))
    sub.runs[0].font.italic = True
    sub.runs[0].font.color.rgb = _WARM_GREY

    doc.add_paragraph()  # spacer

    # Build a map of section_key → photos for quick lookup in arc-label detection
    # We use section keys stored on the photo; for draft, we try to match arc labels
    # to memoir section ids (best-effort — draft state doesn't have structured sections).
    section_photos_by_key: dict = {}
    for photo in req.attached_photos:
        section_photos_by_key.setdefault(photo.section_key, []).append(photo)

    if req.prose:
        paragraphs = [p.strip() for p in req.prose.split("\n\n") if p.strip()]
        for para_text in paragraphs:
            lines = para_text.split("\n")
            # Detect arc label marker: "-- Label --"
            if lines and lines[0].strip().startswith("--") and lines[0].strip().endswith("--"):
                label = lines[0].strip().strip("-").strip()
                h = doc.add_heading(label, level=2)
                h.runs[0].font.color.rgb = _DARK_BROWN
                body = "\n".join(lines[1:]).strip()
                if body:
                    doc.add_paragraph(body)
            else:
                doc.add_paragraph(para_text)
            doc.add_paragraph()  # spacer

    # Append photo section at end of draft (no per-section matching in pure prose)
    # Only include photos not already displayed via section matching
    if req.attached_photos:
        doc.add_page_break()
        ph = doc.add_heading(_chrome(render_lang, "photos_heading"), level=1)
        ph.runs[0].font.color.rgb = _DARK_BROWN
        for photo in req.attached_photos:
            _add_photo_to_doc(doc, photo)
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── WO-ML-04 Phase 4B — bilingual builder ────────────────────────────────────

def _build_threads_docx_bilingual(
    req: MemoirExportRequest,
    translated: MemoirExportRequest,
) -> bytes:
    """Build DOCX with English + Spanish content interleaved per
    section. The narrator's section in source language renders first,
    immediately followed by the translation as a quoted block. A
    bilingual reader can follow either side; a Spanish-only reader
    skips the English block.

    `req` is the original (source) request; `translated` is the
    translated copy produced by _translate_request_content.
    """
    doc = Document()

    # Bilingual title pairs — render both languages stacked.
    src_lang = (req.source_language or "en").strip().lower() or "en"
    tgt_lang = (translated.target_language or "es").strip().lower() or "es"

    src_title = _chrome(src_lang, "threads_title").format(narrator=req.narrator_name)
    tgt_title = _chrome(tgt_lang, "threads_title").format(narrator=req.narrator_name)
    title = doc.add_heading(src_title, level=0)
    title.runs[0].font.color.rgb = _DARK_BROWN
    sub_title = doc.add_heading(tgt_title, level=1)
    sub_title.runs[0].font.color.rgb = _WARM_GREY

    src_sub = doc.add_paragraph(_chrome(src_lang, "threads_subtitle"))
    src_sub.runs[0].font.italic = True
    src_sub.runs[0].font.color.rgb = _WARM_GREY
    tgt_sub = doc.add_paragraph(_chrome(tgt_lang, "threads_subtitle"))
    tgt_sub.runs[0].font.italic = True
    tgt_sub.runs[0].font.color.rgb = _GOLD

    if req.arc_roles:
        arc_line = doc.add_paragraph()
        arc_label = _chrome(src_lang, "story_arc_label").format(
            roles=' · '.join(req.arc_roles),
        )
        arc_run = arc_line.add_run(arc_label)
        arc_run.font.size = Pt(10)
        arc_run.font.color.rgb = _GOLD

    doc.add_paragraph()  # spacer

    # Section-by-section: render source items, then translated items
    # in italic. Photos render between source and translation so the
    # spatial relationship reads naturally regardless of which language
    # the reader follows.
    src_sections_by_id = {s.id: s for s in req.sections}
    for tsec in translated.sections:
        ssec = src_sections_by_id.get(tsec.id)
        if ssec is None or not ssec.items:
            continue

        # Header pair: source label as H2, translated label as H3
        h = doc.add_heading(ssec.label, level=2)
        h.runs[0].font.color.rgb = _DARK_BROWN
        if tsec.label and tsec.label.strip() and tsec.label != ssec.label:
            h2 = doc.add_heading(tsec.label, level=3)
            h2.runs[0].font.color.rgb = _WARM_GREY
            h2.runs[0].font.italic = True

        # Inline photos for this section
        for photo in _photos_for_section(req, ssec.id):
            _add_photo_to_doc(doc, photo)

        # Source items (English)
        for item in ssec.items:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)

        # Translated items immediately below — italic so the eye can
        # tell which is which without flipping pages.
        for item in tsec.items or []:
            p = doc.add_paragraph(style="List Bullet")
            r = p.add_run(item)
            r.font.italic = True
            r.font.color.rgb = _WARM_GREY

        doc.add_paragraph()  # spacer between sections

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_draft_docx_bilingual(
    req: MemoirExportRequest,
    translated: MemoirExportRequest,
) -> bytes:
    """Bilingual variant of _build_draft_docx. Source paragraph,
    then translated paragraph in italic, repeated for each prose
    paragraph the narrator wrote."""
    doc = Document()

    src_lang = (req.source_language or "en").strip().lower() or "en"
    tgt_lang = (translated.target_language or "es").strip().lower() or "es"

    src_title = _chrome(src_lang, "draft_title").format(narrator=req.narrator_name)
    tgt_title = _chrome(tgt_lang, "draft_title").format(narrator=req.narrator_name)
    title = doc.add_heading(src_title, level=0)
    title.runs[0].font.color.rgb = _DARK_BROWN
    sub_title = doc.add_heading(tgt_title, level=1)
    sub_title.runs[0].font.color.rgb = _WARM_GREY

    src_sub = doc.add_paragraph(_chrome(src_lang, "draft_subtitle"))
    src_sub.runs[0].font.italic = True
    src_sub.runs[0].font.color.rgb = _WARM_GREY
    tgt_sub = doc.add_paragraph(_chrome(tgt_lang, "draft_subtitle"))
    tgt_sub.runs[0].font.italic = True
    tgt_sub.runs[0].font.color.rgb = _GOLD

    doc.add_paragraph()  # spacer

    src_paragraphs = (req.prose or "").split("\n\n") if req.prose else []
    tgt_paragraphs = (translated.prose or "").split("\n\n") if translated.prose else []

    # Pair source + translated paragraphs index-aligned. If the
    # translation pass produced a different paragraph count (rare —
    # paragraph-by-paragraph translation preserves count), pad the
    # shorter list with empty strings.
    n = max(len(src_paragraphs), len(tgt_paragraphs))
    for i in range(n):
        s = src_paragraphs[i] if i < len(src_paragraphs) else ""
        t = tgt_paragraphs[i] if i < len(tgt_paragraphs) else ""
        if not s and not t:
            continue
        s_lines = s.split("\n") if s else []
        # Detect arc-label marker on the source side, mirror to translation
        if s_lines and s_lines[0].strip().startswith("--") and s_lines[0].strip().endswith("--"):
            label = s_lines[0].strip().strip("-").strip()
            h = doc.add_heading(label, level=2)
            h.runs[0].font.color.rgb = _DARK_BROWN
            body = "\n".join(s_lines[1:]).strip()
            if body:
                doc.add_paragraph(body)
            if t:
                tp = doc.add_paragraph(t)
                if tp.runs:
                    tp.runs[0].font.italic = True
                    tp.runs[0].font.color.rgb = _WARM_GREY
        else:
            if s:
                doc.add_paragraph(s)
            if t:
                tp = doc.add_paragraph(t)
                if tp.runs:
                    tp.runs[0].font.italic = True
                    tp.runs[0].font.color.rgb = _WARM_GREY
        doc.add_paragraph()  # spacer

    if req.attached_photos:
        doc.add_page_break()
        ph = doc.add_heading(
            _chrome(src_lang, "photos_heading") + " · " + _chrome(tgt_lang, "photos_heading"),
            level=1,
        )
        ph.runs[0].font.color.rgb = _DARK_BROWN
        for photo in req.attached_photos:
            _add_photo_to_doc(doc, photo)
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/export-docx")
def api_memoir_export_docx(req: MemoirExportRequest):
    """
    Accept memoir content JSON, return a DOCX file as a streaming download.
    Called by memoirExportDOCX() in hornelore1.0.html.

    WO-ML-04 / Phase 4B (2026-05-07): the route now dispatches by
    target_language. 'en' (default) is byte-stable. 'es' translates
    every section item + prose paragraph via services.translation
    before rendering. 'bilingual' renders English + Spanish
    interleaved per section / paragraph.
    """
    if not _DOCX_AVAILABLE:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="python-docx is not installed on this server. Install with: pip install python-docx",
        )

    target_lang = _normalize_target_lang(req)
    logger.info(
        "[memoir-docx] export narrator=%s state=%s src=%s tgt=%s sections=%d photos=%d prose_len=%d",
        req.narrator_name, req.memoir_state, req.source_language, target_lang,
        len(req.sections), len(req.attached_photos),
        len(req.prose or ""),
    )

    safe_name = (
        req.narrator_name.strip().lower()
        .replace(" ", "_")
        .replace("/", "_")
    )[:40] or "narrator"
    # Filename suffix carries language so re-exports don't overwrite
    # each other when the operator iterates en → es → bilingual.
    lang_suffix = "" if target_lang == "en" else f"_{target_lang}"
    filename = f"lorevox_memoir_{safe_name}_{req.memoir_state}{lang_suffix}.docx"

    # Dispatch by target language.
    if target_lang == "en":
        # Pre-Phase-4B path. Byte-stable.
        if req.memoir_state == "draft":
            docx_bytes = _build_draft_docx(req, render_lang="en")
        else:
            docx_bytes = _build_threads_docx(req, render_lang="en")
    elif target_lang == "es":
        # Translate first, then render with Spanish chrome.
        translated = _translate_request_content(req, "es")
        if req.memoir_state == "draft":
            docx_bytes = _build_draft_docx(translated, render_lang="es")
        else:
            docx_bytes = _build_threads_docx(translated, render_lang="es")
    else:  # bilingual
        # Translate to Spanish; render with both languages interleaved.
        # Source language defaults to 'en' for the v1 scope; future
        # work can extend bilingual to other source languages.
        translated = _translate_request_content(req, "es")
        if req.memoir_state == "draft":
            docx_bytes = _build_draft_docx_bilingual(req, translated)
        else:
            docx_bytes = _build_threads_docx_bilingual(req, translated)

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
