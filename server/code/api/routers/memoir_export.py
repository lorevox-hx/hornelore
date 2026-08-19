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

import hashlib
import io
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import flags

logger = logging.getLogger("memoir_export")

try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False

router = APIRouter(prefix="/api/memoir", tags=["memoir-export"])


# ── Flag gate ─────────────────────────────────────────────────────────────────

def _require_enabled() -> None:
    """WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: raise 404 when
    HORNELORE_MEMOIR_EXPORT_ENABLED is off. Mirrors the trips/photos
    posture — a disabled surface does not advertise itself."""
    if not flags.memoir_export_enabled():
        raise HTTPException(status_code=404, detail="Not found")


# ── Request models ─────────────────────────────────────────────────────────────

class MemoirSection(BaseModel):
    """A single named section with zero or more thread items.

    `sources` (2026-08-19) carries one opaque provenance digest per item,
    parallel to `items`. It is set only by the server's captured-story
    harvest, is never rendered into the visible document, and never
    contains a narrator id -- see `_story_source_digest`. Client sections
    simply leave it empty.
    """
    id: str
    label: str
    items: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class AttachedPhoto(BaseModel):
    """A photo attached to a memoir section (Media Builder — Task 4).

    WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5.2): the
    client no longer holds file-path authority. ``file_path`` is kept
    ONLY for wire-compat with old clients that still send it — the
    server never reads it (not for logging, validation, or rendering).
    The on-disk location is resolved server-side from ``media_id``
    through the media table (see _resolve_media_photo_path)."""
    media_id: str
    section_key: str
    file_path: Optional[str] = None   # IGNORED — wire-compat only, never read
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
    # WO-MEMOIR-STORY-CANDIDATES-WIRE-01 (2026-07-06): when person_id
    # is present, the server harvests operator-cleared captured
    # stories (story_candidates with review_status promoted or
    # memoir_only) and appends them as era-grouped sections in the
    # narrator's OWN words. Absent person_id = byte-stable with every
    # pre-wire caller. include_captured_stories=False opts out.
    person_id: Optional[str] = Field(default=None)
    include_captured_stories: bool = Field(default=True)
    # WO-MEMOIR-TRIP-STORY-LANE-01 (2026-07-27): approved Travel Doc
    # trip stories (trip_location_notes.include_in_memoir=1) join the
    # narrator memoir as their own clearly-sourced sections. This is a
    # DB read. It NEVER writes a travel_doc_modal turn into the
    # life-story archive -- the two-surface rule of 2026-07-09 holds
    # (see tests/test_modal_archive_boundary.py). Opt out per request.
    include_trip_stories: bool = Field(default=True)
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


# ── WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5.3) ──────────────
# Server-side media authority. The client supplies only media_id; the
# on-disk path comes from the media table (db.get_media_item — the same
# authority /api/media/upload writes and /api/media/file/{id} serves
# from) and must stay contained within the configured media root.

# Mirrors _ALLOWED_MIME_PREFIXES in routers/media.py (the upload-side
# allowlist). Kept local so importing this module never drags in the
# media router's FastAPI machinery.
_IMAGE_MIME_PREFIXES = (
    "image/jpeg", "image/png", "image/webp", "image/heic",
    "image/heif", "image/gif", "image/bmp", "image/tiff",
)


def _media_root() -> Path:
    """Resolve the configured media root: MEDIA_DIR env when set, else
    the established DATA_DIR/media fallback (the same location
    routers/media.py stores uploads under). Read at call time so tests
    can point it at a tempdir via the environment."""
    raw = (os.environ.get("MEDIA_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    data_dir = Path(os.environ.get("DATA_DIR", "data")).expanduser()
    return (data_dir / "media").resolve()


def _resolve_media_photo_path(photo: AttachedPhoto, person_id: Optional[str]) -> Path:
    """Resolve an attached photo's on-disk path SERVER-SIDE from its
    media_id. The client-supplied file_path is never consulted.

    Containment contract (fail-loud 422, never silent skip):
      - media row must exist;
      - when the request carries person_id, the row must belong to it;
      - stored MIME must be image-compatible;
      - relative stored filenames join to the media root; absolute ones
        are accepted only when they resolve inside the media root;
      - Path.resolve(strict=True) — so symlinks are flattened and a
        symlink escaping the root is rejected by the containment check;
      - must be a regular file.
    Only the path returned here may reach doc.add_picture()."""
    from .. import db as _db

    item = _db.get_media_item(photo.media_id)
    if item is None:
        raise HTTPException(
            status_code=422,
            detail=f"unknown media_id '{photo.media_id}' — not in media table",
        )

    if person_id and item.get("person_id") != person_id:
        raise HTTPException(
            status_code=422,
            detail=(
                f"media '{photo.media_id}' does not belong to person "
                f"'{person_id}'"
            ),
        )

    mime = (item.get("mime") or "").strip().lower()
    if not any(mime.startswith(p) for p in _IMAGE_MIME_PREFIXES):
        raise HTTPException(
            status_code=422,
            detail=f"media '{photo.media_id}' has non-image mime '{mime}'",
        )

    root = _media_root()
    stored = (item.get("filename") or "").strip()
    if not stored:
        raise HTTPException(
            status_code=422,
            detail=f"media '{photo.media_id}' has no stored filename",
        )

    candidate = Path(stored)
    if not candidate.is_absolute():
        candidate = root / candidate

    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"media '{photo.media_id}' file missing on disk: {exc}",
        )

    try:
        resolved.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"media '{photo.media_id}' resolves outside the media root"
            ),
        )

    if not resolved.is_file():
        raise HTTPException(
            status_code=422,
            detail=f"media '{photo.media_id}' is not a regular file",
        )

    return resolved


def _resolve_attached_photos(req: MemoirExportRequest) -> Dict[str, Path]:
    """Resolve every attached photo up-front, before any rendering.
    Returns media_id → contained server-resolved path. Raises 422 on
    the first authority/containment failure."""
    resolved: Dict[str, Path] = {}
    for photo in req.attached_photos:
        resolved[photo.media_id] = _resolve_media_photo_path(photo, req.person_id)
    return resolved


def _add_photo_to_doc(doc: Any, photo: AttachedPhoto, resolved: Optional[Path]) -> None:
    """
    Insert photo inline in the document.

    WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01: ``resolved`` is the
    server-resolved, root-contained path from _resolve_media_photo_path
    — the ONLY path that ever reaches doc.add_picture(). photo.file_path
    is never read. A correctly-authorized but corrupt/unsupported image
    still skips gracefully with a warning (never reads another path).
    """
    if resolved is None:
        # Defensive: photo without a resolved entry never renders.
        logger.warning(
            "[memoir-docx] no resolved path for media %s — skipping",
            photo.media_id,
        )
        return
    try:
        doc.add_picture(str(resolved), width=Inches(3.5))
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
        logger.warning("[memoir-docx] Could not add photo %s: %s — skipping", photo.media_id, exc)


# ── DOCX builders ──────────────────────────────────────────────────────────────

def _stamp_source_provenance(doc, req: "MemoirExportRequest") -> None:
    """Record which captured stories this document was built from.

    WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01 Commit 3 (2026-08-19).

    The audit found exported memoirs completely flat: once written, no
    paragraph could be traced back to the story, turn or conversation it
    came from, so nothing downstream could detect a duplicate or repair a
    mistake. Provenance now travels with the artifact.

    It is written to the document's `comments` core property -- metadata,
    not a page -- so a family reading the memoir never sees it. The values
    are opaque digests, never narrator ids; an operator matches a section
    to its source by digesting the candidate id again.

    Never raises: a memoir must not fail to export over its own metadata.
    """
    try:
        digests = []
        for sec in (req.sections or []):
            for d in (getattr(sec, "sources", None) or []):
                if d and d not in digests:
                    digests.append(str(d))
        if not digests:
            return
        doc.core_properties.comments = (
            "lorevox-story-sources: " + ",".join(digests))
    except Exception as exc:  # pragma: no cover - metadata is best effort
        logger.warning("[memoir-docx] provenance stamp skipped: %s", exc)


def _build_threads_docx(
    req: MemoirExportRequest,
    *,
    render_lang: str = "en",
    resolved_photos: Optional[Dict[str, Path]] = None,
) -> bytes:
    """Build DOCX for threads state: grouped sections with bullet items.

    `render_lang` controls only the chrome (title / subtitle / photos
    heading / arc-roles label). Section content has already been
    translated upstream by _translate_request_content when needed.
    `resolved_photos` maps media_id → server-resolved contained path
    (WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01).
    """
    resolved_photos = resolved_photos or {}
    doc = Document()
    _stamp_source_provenance(doc, req)

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
            _add_photo_to_doc(doc, photo, resolved_photos.get(photo.media_id))

        for item in sec.items:
            p = doc.add_paragraph(style="List Bullet")
            p.add_run(item)

        doc.add_paragraph()  # spacer between sections

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _build_draft_docx(
    req: MemoirExportRequest,
    *,
    render_lang: str = "en",
    resolved_photos: Optional[Dict[str, Path]] = None,
) -> bytes:
    """Build DOCX for draft state: prose paragraphs, optionally with arc headings.

    `render_lang` controls chrome only; prose content is already
    translated upstream when needed (see _translate_request_content).
    `resolved_photos` maps media_id → server-resolved contained path
    (WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01)."""
    resolved_photos = resolved_photos or {}
    doc = Document()
    _stamp_source_provenance(doc, req)

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
            _add_photo_to_doc(doc, photo, resolved_photos.get(photo.media_id))
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── WO-ML-04 Phase 4B — bilingual builder ────────────────────────────────────

def _build_threads_docx_bilingual(
    req: MemoirExportRequest,
    translated: MemoirExportRequest,
    *,
    resolved_photos: Optional[Dict[str, Path]] = None,
) -> bytes:
    """Build DOCX with English + Spanish content interleaved per
    section. The narrator's section in source language renders first,
    immediately followed by the translation as a quoted block. A
    bilingual reader can follow either side; a Spanish-only reader
    skips the English block.

    `req` is the original (source) request; `translated` is the
    translated copy produced by _translate_request_content.
    """
    resolved_photos = resolved_photos or {}
    doc = Document()
    _stamp_source_provenance(doc, req)

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
            _add_photo_to_doc(doc, photo, resolved_photos.get(photo.media_id))

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
    *,
    resolved_photos: Optional[Dict[str, Path]] = None,
) -> bytes:
    """Bilingual variant of _build_draft_docx. Source paragraph,
    then translated paragraph in italic, repeated for each prose
    paragraph the narrator wrote."""
    resolved_photos = resolved_photos or {}
    doc = Document()
    _stamp_source_provenance(doc, req)

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
            _add_photo_to_doc(doc, photo, resolved_photos.get(photo.media_id))
            doc.add_paragraph()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── Route ─────────────────────────────────────────────────────────────────────

# ── WO-MEMOIR-STORY-CANDIDATES-WIRE-01: captured-story harvest ────────────

_MEMOIR_ERA_ORDER = [
    "earliest_years", "early_school_years", "adolescence",
    "coming_of_age", "building_years", "later_years", "today",
]


#: Section ids this server OWNS. A client may send operator-authored
#: sections freely -- that is the editing surface doing its job -- but it
#: may not send one wearing a reserved id, because the memoir would then
#: contain a chapter of "captured stories" that no review ever cleared,
#: indistinguishable in the finished document from ones that were.
_RESERVED_STORY_SECTION_PREFIX = "captured_stories"


def _story_source_digest(candidate_id: str) -> str:
    """A stable, non-identifying marker for one captured story.

    A raw narrator UUID must not appear in a document a family reads, and
    a memoir with no provenance at all cannot be traced back to the turn
    it came from -- the audit found exported prose was completely flat.
    A short digest of the candidate id is stable across exports, reveals
    nothing on its face, and lets an operator match a paragraph to its
    source by digesting the id again.
    """
    return hashlib.sha256(
        f"story:{candidate_id}".encode("utf-8")).hexdigest()[:12]


def _captured_story_sections(person_id: str) -> Tuple[List[MemoirSection], str]:
    """Harvest reviewed story candidates into era-grouped memoir sections.

    Rewritten 2026-08-19 (WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01
    Commit 3). Returns `(sections, status)` where status is "read" or the
    projection's own failure verdict, because the caller must be able to
    tell an empty narrator from an unreadable one -- see the export route.

    VERBATIM narrator transcripts. The whole point of the preservation
    lane is the narrator's own words: no summarising, no rewriting.

    ── WHAT CHANGED, AND WHY IT MATTERED ───────────────────────────────

    This function used to read `story_candidate_list_for_memoir` and then
    interpret `era_candidates[0]` itself:

        era = eras[0] if eras else "_unplaced"

    That is a second, independent reading of placement, and it disagreed
    with the canonical one. `story_projection` had already decided that
    an era candidate nobody confirmed is NOT a placement; the memoir filed
    the story under it anyway. A machine guess became a chapter heading
    in a document a family keeps, with nothing on the page to say it was
    a guess.

    Placement now comes from `story_projection.memoir_projection`, which
    is the same service the Life Map, the chronology and Lori read. An
    unplaced story -- including one with a year but no era -- goes to
    "More stories", and no era is ever derived for it.

    EACH ELIGIBLE CANDIDATE APPEARS EXACTLY ONCE, keyed by candidate id.
    Deliberately NOT deduplicated by text: two tellings of the same
    memory are two things the narrator said, and collapsing them would be
    the system deciding which of a person's own words to discard.
    """
    try:
        from ..services import story_projection as _sp
        projection = _sp.memoir_projection(person_id)
    except Exception as exc:
        logger.warning("[memoir-docx] story harvest failed: %s", exc)
        return [], "unavailable"
    if not projection.available:
        return [], projection.status
    if not projection.items:
        return [], "read"

    try:
        from ..lv_eras import era_id_to_warm_label as _warm
    except Exception:
        _warm = lambda e: e  # noqa: E731

    seen: set = set()
    by_era: Dict[str, List[Dict[str, Any]]] = {}
    for row in projection.items:
        cid = row.get("id")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        era = row.get("era") or "_unplaced"
        by_era.setdefault(era, []).append(row)

    def _section(era_key: str, label: str, rows: List[Dict[str, Any]]):
        return MemoirSection(
            id=f"{_RESERVED_STORY_SECTION_PREFIX}_{era_key}",
            label=label,
            items=[r["transcript"] for r in rows],
            sources=[_story_source_digest(r["id"]) for r in rows],
        )

    sections: List[MemoirSection] = []
    ordered = [e for e in _MEMOIR_ERA_ORDER if e in by_era]
    ordered += [e for e in by_era
                if e not in _MEMOIR_ERA_ORDER and e != "_unplaced"]
    for era in ordered:
        try:
            label = "In their own words — " + str(_warm(era))
        except Exception:
            label = "In their own words"
        sections.append(_section(era, label, by_era[era]))
    if "_unplaced" in by_era:
        sections.append(_section(
            "more", "In their own words — More stories", by_era["_unplaced"]))
    return sections, "read"


def _trip_story_sections(person_id: str) -> List[MemoirSection]:
    """Harvest APPROVED Travel Doc trip stories into memoir sections.

    WO-MEMOIR-TRIP-STORY-LANE-01 (2026-07-27). Travel Doc modal turns
    are captured to trip_location_notes (source_surface=
    travel_doc_modal) and are deliberately NEVER written to the
    narrator's life-story archive -- that boundary is the two-surface
    rule of 2026-07-09, locked by tests/test_modal_archive_boundary.py.
    Rebuilding an archive bridge would resurrect
    BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01, where operator workspace
    chatter came back to the narrator as their own life.

    This lane is the sanctioned way trip material reaches the memoir:
    a DB read, gated on the operator's explicit include_in_memoir=1,
    rendered as its own clearly-sourced section. It performs no archive
    write of any kind. Notes the operator has not promoted never appear;
    hidden=1 rows are already excluded by location_notes_list. The trip
    DOCX export path is untouched.

    Never raises -- memoir export must not fail because trip rows are
    unreadable."""
    # Trips are a default-OFF surface. If the operator has not enabled
    # them, trip material does not appear in the memoir either.
    if os.getenv("HORNELORE_TRIPS", "0").strip().lower() not in (
        "1", "true", "yes", "on",
    ):
        return []
    try:
        from ..services import trip_repository as _tr
        trips = _tr.trip_list(person_id)
    except Exception as exc:
        logger.warning("[memoir-docx] trip harvest failed: %s", exc)
        return []
    if not trips:
        return []

    def _order(t: Dict[str, Any]):
        """Dated trips in chronological order, undated ones after."""
        start = (t.get("start_date") or "").strip()
        return (0, start) if start else (1, (t.get("created_at") or ""))

    sections: List[MemoirSection] = []
    for trip in sorted(trips, key=_order):
        trip_id = trip.get("id")
        if not trip_id:
            continue
        try:
            notes = _tr.location_notes_list(trip_id)
        except Exception as exc:
            logger.warning(
                "[memoir-docx] trip notes unreadable trip=%s: %s",
                trip_id, exc)
            continue
        items: List[str] = []
        for n in notes:
            if not n.get("include_in_memoir"):
                continue          # unapproved never reaches the memoir
            text = (n.get("note_text") or "").strip()
            if not text:
                continue
            title = (n.get("note_title") or "").strip()
            items.append(f"{title} \u2014 {text}" if title else text)
        if not items:
            continue
        label = "From your travels \u2014 " + (
            (trip.get("title") or "").strip() or "A trip")
        sections.append(MemoirSection(
            id=f"trip_stories_{trip_id}", label=label, items=items))
    return sections


# WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5.5): strict
# filename sanitizer, mirroring the trips.py export_docx allowlist.
# ASCII letters/digits/underscore/hyphen/dot only — everything else
# (quotes, CR/LF, slashes, backslashes, control chars, non-ASCII)
# becomes '_'. Deterministic fallback when nothing survives.
def _safe_filename_component(raw: Optional[str], *, fallback: str, max_len: int = 80) -> str:
    cleaned = "".join(
        c if (c.isascii() and (c.isalnum() or c in "-_.")) else "_"
        for c in (raw or "")
    )[:max_len].strip("_.")
    return cleaned or fallback


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

    WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5):
      - gated behind HORNELORE_MEMOIR_EXPORT_ENABLED (404 when off);
      - person_id must exist in people (422 otherwise);
      - attached photos resolve server-side via the media table and
        must stay contained in the media root (422 on any failure);
      - Content-Disposition filename is allowlist-sanitized.
    """
    _require_enabled()

    if not _DOCX_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="python-docx is not installed on this server. Install with: pip install python-docx",
        )

    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5.4): a
    # supplied person_id must name a real narrator before it can scope
    # captured-story harvest or media ownership checks.
    if req.person_id:
        from .. import db as _db
        if not _db.get_person(req.person_id):
            raise HTTPException(
                status_code=422,
                detail=f"person_id '{req.person_id}' not found in people",
            )

    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5.3):
    # resolve every attached photo through the media authority BEFORE
    # rendering. Containment/authority failures are loud 422s; only the
    # server-resolved paths below ever reach doc.add_picture().
    resolved_photos = _resolve_attached_photos(req)

    target_lang = _normalize_target_lang(req)

    # WO-MEMOIR-STORY-CANDIDATES-WIRE-01: append operator-cleared
    # captured stories (verbatim) as era-grouped sections. Only fires
    # when the caller supplies person_id; pre-wire callers byte-stable.
    if req.person_id and req.include_captured_stories:
        # ── RESERVED IDS ARE THE SERVER'S ───────────────────────────────
        #
        # 2026-08-19. Client sections are operator-authored prose and are
        # legitimate -- the editing surface is supposed to send them. But
        # a client section wearing a `captured_stories*` id would appear
        # in the finished document as reviewed narrator evidence, beside
        # and indistinguishable from the real thing, and could also
        # duplicate a server section by colliding with its id (the
        # bilingual builder keys sections by id, last one wins).
        #
        # So the reserved namespace is stripped from the client payload
        # before the server's own sections are appended. Nothing else the
        # client sent is touched.
        _client_sections = [
            s for s in (req.sections or [])
            if not str(getattr(s, "id", "") or "").startswith(
                _RESERVED_STORY_SECTION_PREFIX)
        ]
        _spoofed = len(req.sections or []) - len(_client_sections)
        if _spoofed:
            logger.warning(
                "[memoir-docx] dropped %d client section(s) using the "
                "reserved %r id namespace — captured stories are "
                "server-harvested and review-gated",
                _spoofed, _RESERVED_STORY_SECTION_PREFIX)

        _story_sections, _story_status = _captured_story_sections(req.person_id)

        # ── AN UNREADABLE LANE MUST NOT LOOK LIKE AN EMPTY ONE ──────────
        #
        # The harvest used to swallow every failure into `return []`, so
        # a database outage produced a memoir missing every approved
        # story, logged at WARNING and otherwise indistinguishable from a
        # complete document. A family cannot tell that a chapter is
        # absent; they simply never see it.
        if _story_status != "read":
            raise HTTPException(
                status_code=503,
                detail=("reviewed stories could not be read — export "
                        "refused rather than produce a memoir that looks "
                        "complete"))

        if _spoofed or _story_sections:
            req = req.model_copy(update={
                "sections": _client_sections + _story_sections,
            }) if hasattr(req, "model_copy") else req
            if not hasattr(req, "model_copy"):
                req.sections = _client_sections + _story_sections
        if _story_sections:
            logger.info(
                "[memoir-docx] captured stories appended: %d section(s), "
                "%d stor%s",
                len(_story_sections),
                sum(len(s.items) for s in _story_sections),
                "y" if sum(len(s.items) for s in _story_sections) == 1 else "ies",
            )

    # WO-MEMOIR-TRIP-STORY-LANE-01: append APPROVED Travel Doc trip
    # stories as their own sections. DB read only -- this adds no
    # archive write, and no travel_doc_modal turn enters the narrator's
    # life-story archive as a result of it.
    if req.person_id and req.include_trip_stories:
        _trip_sections = _trip_story_sections(req.person_id)
        if _trip_sections:
            req = req.model_copy(update={
                "sections": list(req.sections) + _trip_sections,
            }) if hasattr(req, "model_copy") else req
            if not hasattr(req, "model_copy"):
                req.sections = list(req.sections) + _trip_sections
            logger.info(
                "[memoir-docx] trip stories appended: %d section(s), "
                "%d note(s)",
                len(_trip_sections),
                sum(len(s.items) for s in _trip_sections),
            )

    logger.info(
        "[memoir-docx] export narrator=%s state=%s src=%s tgt=%s sections=%d photos=%d prose_len=%d",
        req.narrator_name, req.memoir_state, req.source_language, target_lang,
        len(req.sections), len(req.attached_photos),
        len(req.prose or ""),
    )

    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 (Phase 5.5):
    # allowlist-sanitize BOTH client-supplied filename components so no
    # CR/LF/quote/slash/control char can reach the header.
    safe_name = _safe_filename_component(
        (req.narrator_name or "").strip().lower().replace(" ", "_"),
        fallback="memoir",
    )
    safe_state = _safe_filename_component(req.memoir_state, fallback="threads", max_len=20)
    # Filename suffix carries language so re-exports don't overwrite
    # each other when the operator iterates en → es → bilingual.
    lang_suffix = "" if target_lang == "en" else f"_{target_lang}"
    filename = f"lorevox_memoir_{safe_name}_{safe_state}{lang_suffix}.docx"

    # Dispatch by target language.
    if target_lang == "en":
        # Pre-Phase-4B path. Byte-stable.
        if req.memoir_state == "draft":
            docx_bytes = _build_draft_docx(
                req, render_lang="en", resolved_photos=resolved_photos)
        else:
            docx_bytes = _build_threads_docx(
                req, render_lang="en", resolved_photos=resolved_photos)
    elif target_lang == "es":
        # Translate first, then render with Spanish chrome.
        translated = _translate_request_content(req, "es")
        if req.memoir_state == "draft":
            docx_bytes = _build_draft_docx(
                translated, render_lang="es", resolved_photos=resolved_photos)
        else:
            docx_bytes = _build_threads_docx(
                translated, render_lang="es", resolved_photos=resolved_photos)
    else:  # bilingual
        # Translate to Spanish; render with both languages interleaved.
        # Source language defaults to 'en' for the v1 scope; future
        # work can extend bilingual to other source languages.
        translated = _translate_request_content(req, "es")
        if req.memoir_state == "draft":
            docx_bytes = _build_draft_docx_bilingual(
                req, translated, resolved_photos=resolved_photos)
        else:
            docx_bytes = _build_threads_docx_bilingual(
                req, translated, resolved_photos=resolved_photos)

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
