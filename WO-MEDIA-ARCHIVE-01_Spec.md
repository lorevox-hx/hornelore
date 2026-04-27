# WO-MEDIA-ARCHIVE-01 — Scanner + Document Archive Intake

**Spec authored:** 2026-04-26
**Status:** READY TO BUILD (next session)
**Estimated effort:** ~4–6 hours single pass
**Owner:** Claude (build), Chris (live verify with Shong PDF)

---

## 0. Why this is a separate lane (not a Photo Intake extension)

The current Photo Intake lane is correctly photo-specific: it accepts image files, generates thumbnails, stores photo-shaped metadata, handles `narrator_ready` flags, and is designed around Lori showing photos to a narrator and asking what they remember.

Documents are a different problem. A file like `outline of the shong family.pdf` (18-page scanned genealogy outline by Charlotte Graichen of Valley City, North Dakota) needs to be:

- **Preserved as evidence** — original file, no destructive conversion
- **Tagged** with narrator/family-line/document-type/date/location/people
- **Manually transcribed** when handwriting/OCR isn't ready yet
- **Optionally promoted** to Bio Builder candidate review later (NEVER automatically)

These are curator-side concerns, not narrator-side. Photos remain for memory prompts. Media Archive becomes the source-preservation lane.

**Product rule (locked):**

```
Preserve first.
Tag second.
Transcribe / OCR third.
Extract candidates only after that.
Promote truth NEVER happens automatically.
```

A scanned document existing in the archive must NOT silently become promoted truth. It can later support Family Tree, Life Map ancestry, Timeline migration events, Memoir ancestry chapters, Kawa origin material, and Lori interview prompts — but every step from "archive item exists" → "appears in narrator's truth surface" requires explicit operator review.

---

## 1. Scope (LOCKED)

### IN scope for WO-MEDIA-ARCHIVE-01

1. New Document Archive curator page (`ui/media-archive.html`)
2. Upload PDFs + scanned image files
3. Store original file unchanged on disk
4. Generate preview thumbnail where possible (image extensions only in v1; PDFs get a generic icon, first-page thumbnail in v2)
5. Pick narrator and/or family line
6. Tag with title, description, document type, date, place, people, family lines
7. Manual transcription / operator notes fields
8. Mark `archive_only` or `candidate_ready`
9. List saved archive items (filtered by narrator / family line / type)
10. Open item detail modal with full-resolution preview + edit
11. Link item to Life Map era + section + timeline year/date
12. Soft-delete items (preserve disk file for forensic restore)

### OUT of scope (explicitly deferred)

1. Automatic handwriting recognition
2. Full OCR pipeline (deferred to `WO-MEDIA-OCR-01`)
3. Automatic family-tree import
4. Automatic truth promotion
5. Multi-narrator sharing
6. Photo-session narrator prompt flow (this isn't a photo)
7. Editing people/events extracted FROM the document (deferred to `WO-MEDIA-ARCHIVE-CANDIDATES-01`)
8. Scanner watch-folder import (deferred to `WO-MEDIA-WATCHFOLDER-01`)

---

## 2. Data model

### Table: `media_archive_items`

```sql
CREATE TABLE IF NOT EXISTS media_archive_items (
  id TEXT PRIMARY KEY,

  person_id TEXT,
  family_line TEXT,

  title TEXT NOT NULL,
  description TEXT,

  document_type TEXT NOT NULL DEFAULT 'unknown',
  source_kind TEXT NOT NULL DEFAULT 'uploaded_file',

  original_filename TEXT NOT NULL,
  mime_type TEXT NOT NULL,
  file_ext TEXT,
  file_size_bytes INTEGER,

  storage_path TEXT NOT NULL,
  media_url TEXT,
  thumbnail_url TEXT,

  page_count INTEGER,
  text_status TEXT NOT NULL DEFAULT 'not_started',
  transcription_status TEXT NOT NULL DEFAULT 'not_started',
  extraction_status TEXT NOT NULL DEFAULT 'none',

  manual_transcription TEXT,
  ocr_text TEXT,
  summary TEXT,
  operator_notes TEXT,

  date_value TEXT,
  date_precision TEXT NOT NULL DEFAULT 'unknown'
    CHECK (date_precision IN ('exact','month','year','decade','unknown')),
  location_label TEXT,
  location_source TEXT NOT NULL DEFAULT 'unknown',

  timeline_year INTEGER,
  life_map_era TEXT,
  life_map_section TEXT,

  archive_only INTEGER NOT NULL DEFAULT 1,
  candidate_ready INTEGER NOT NULL DEFAULT 0,
  needs_review INTEGER NOT NULL DEFAULT 0,

  uploaded_by_user_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_media_archive_person
  ON media_archive_items(person_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_media_archive_family_line
  ON media_archive_items(family_line) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_media_archive_type
  ON media_archive_items(document_type) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_media_archive_candidate_ready
  ON media_archive_items(candidate_ready) WHERE deleted_at IS NULL;
```

### Table: `media_archive_people` (join table)

```sql
CREATE TABLE IF NOT EXISTS media_archive_people (
  id TEXT PRIMARY KEY,
  archive_item_id TEXT NOT NULL,
  person_id TEXT,
  person_label TEXT NOT NULL,
  role TEXT,
  confidence TEXT NOT NULL DEFAULT 'curator_tagged',
  created_at TEXT NOT NULL,
  FOREIGN KEY (archive_item_id) REFERENCES media_archive_items(id)
);

CREATE INDEX IF NOT EXISTS idx_media_archive_people_item
  ON media_archive_people(archive_item_id);
```

### Table: `media_archive_family_lines` (join table)

```sql
CREATE TABLE IF NOT EXISTS media_archive_family_lines (
  id TEXT PRIMARY KEY,
  archive_item_id TEXT NOT NULL,
  family_line TEXT NOT NULL,
  confidence TEXT NOT NULL DEFAULT 'curator_tagged',
  created_at TEXT NOT NULL,
  FOREIGN KEY (archive_item_id) REFERENCES media_archive_items(id)
);

CREATE INDEX IF NOT EXISTS idx_media_archive_family_lines_item
  ON media_archive_family_lines(archive_item_id);
```

### Table: `media_archive_links`

```sql
CREATE TABLE IF NOT EXISTS media_archive_links (
  id TEXT PRIMARY KEY,
  archive_item_id TEXT NOT NULL,
  link_type TEXT NOT NULL
    CHECK (link_type IN (
      'life_map_era','timeline_year','memoir_section',
      'family_tree_person','bio_builder_candidate',
      'kawa_segment','source_note'
    )),
  link_target TEXT NOT NULL,
  label TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (archive_item_id) REFERENCES media_archive_items(id)
);

CREATE INDEX IF NOT EXISTS idx_media_archive_links_item
  ON media_archive_links(archive_item_id);
CREATE INDEX IF NOT EXISTS idx_media_archive_links_type_target
  ON media_archive_links(link_type, link_target);
```

### Document type enum (UI + backend validation)

```
genealogy_document
handwritten_note
letter
certificate
newspaper_clipping
school_record
military_record
legal_record
photo_scan_contact_sheet
pdf_document
typed_notes
book_excerpt
unknown
```

### Text status enum

```
not_started        — uploaded but no transcription/OCR work
image_only_needs_ocr  — known to be image-only PDF or scan
manual_partial     — operator has typed some but not all
manual_complete    — operator has fully transcribed
ocr_partial        — automatic OCR ran, some text extracted
ocr_complete       — automatic OCR ran, all text extracted
mixed              — combination of OCR + manual
```

---

## 3. Storage layout

```
DATA_DIR/
  media/
    archive/
      people/
        <person_id>/
          documents/
            <archive_item_id>/
              original.pdf            (or .jpg, .png, .tiff, .txt, .md)
              thumb.jpg               (when generatable)
              meta.json               (mirror of DB row for forensic recovery)
      family_lines/
        shong/
          <archive_item_id>/
            original.pdf
            thumb.jpg
            meta.json
      unassigned/
        <archive_item_id>/
            original.pdf
            ...
```

**Critical rules:**
- Originals are NEVER modified. No re-encoding, no compression, no metadata stripping.
- Thumbnail generation is best-effort. Failure does not block upload.
- `meta.json` mirrors the DB row at upload time for disaster recovery (DB corrupt → reconstruct from filesystem).
- Do NOT store under `photos/` — that's Photo Intake's lane and the conventions differ.

---

## 4. API surface

### Health
```
GET /api/media-archive/health
```
Response: `{"ok": true, "enabled": true, "storage_root": ".../media/archive"}`. Always 200; reports `enabled=false` when `HORNELORE_MEDIA_ARCHIVE_ENABLED` is off.

### Upload (multipart)
```
POST /api/media-archive
```
Form fields:
| Field | Required | Notes |
|---|---|---|
| `file` | yes | The actual file (PDF/JPG/PNG/TIFF/WEBP/TXT/MD) |
| `title` | yes | Human-readable title |
| `document_type` | yes | One of the enum |
| `person_id` | optional | Pick a narrator |
| `family_line` | optional | Free-text family line label (e.g. "Shong") |
| `description` | optional | What it is + source attribution |
| `date_value` | optional | YYYY / YYYY-MM / YYYY-MM-DD |
| `date_precision` | optional | enum |
| `location_label` | optional | Free-text place |
| `location_source` | optional | enum |
| `timeline_year` | optional | INT for Timeline anchor |
| `life_map_era` | optional | Life Map anchor |
| `life_map_section` | optional | Life Map sub-anchor |
| `archive_only` | optional, default true | "Don't promote to candidates" |
| `candidate_ready` | optional, default false | "Operator says this is ready for candidate review" |
| `people` | optional JSON | `[{person_label, person_id?, role?}]` |
| `family_lines` | optional JSON | `[{family_line}]` |
| `operator_notes` | optional | Internal curator notes |
| `manual_transcription` | optional | Operator-typed text |
| `uploaded_by_user_id` | optional | Curator id |

Response:
```json
{
  "ok": true,
  "item": {
    "id": "...",
    "title": "Outline of the Shong Family",
    "document_type": "genealogy_document",
    "media_url": "/api/media-archive/{id}/file",
    "thumbnail_url": "/api/media-archive/{id}/thumb",
    "page_count": 18,
    "text_status": "image_only_needs_ocr"
  }
}
```

### List
```
GET /api/media-archive?person_id=<id>
GET /api/media-archive?family_line=Shong
GET /api/media-archive?document_type=genealogy_document
GET /api/media-archive?include_deleted=true
```
All filters are optional + composable. Default excludes soft-deleted.

### Detail
```
GET /api/media-archive/{id}
```
Returns the full row including people + family_lines + links arrays.

### Patch
```
PATCH /api/media-archive/{id}
```
Body: same fields as upload (all optional except `last_edited_by_user_id`). Replace-all semantics for `people`/`family_lines` arrays (matches WO-PHOTO-PEOPLE-EDIT-01 pattern).

### Soft delete
```
DELETE /api/media-archive/{id}?actor_id=<id>
```
Sets `deleted_at`. File stays on disk.

### File serving
```
GET /api/media-archive/{id}/file       — original
GET /api/media-archive/{id}/thumb      — preview thumbnail (or fallback)
```
Pattern matches `/api/photos/{id}/image` + `/thumb` from BUG-PHOTO-NULL-URLS.

---

## 5. UI spec

### Page: `ui/media-archive.html`

Layout (mirror Photo Intake's two-card grid):

**Header**
- Title: "Media Archive"
- Subtitle: "Upload scanned documents, handwritten notes, letters, records, and genealogy sources."

**Left panel: Add Archive Item**
- File picker / drag-drop zone
- Narrator dropdown (`maNarrator`)
- Family line input (`maFamilyLine`, text)
- Document type dropdown (`maDocumentType`, enum)
- Title (`maTitle`, required)
- Description (`maDescription`, multiline)
- Date row: `maDateValue` + `maDatePrecision`
- Location row: `maLocationLabel` + `maLocationSource`
- Timeline year (`maTimelineYear`, int)
- Life Map era + section (`maLifeMapEra`, `maLifeMapSection`)
- People tags list (`maPeopleList` + `maAddPersonBtn`)
- Family line tags list (`maFamilyLinesList` + `maAddFamilyLineBtn`)
- Manual transcription (`maManualTranscription`, large textarea)
- Operator notes (`maOperatorNotes`, multiline)
- Checkboxes: `maArchiveOnly` (default true), `maCandidateReady` (default false)
- Save / Reset buttons (`maSaveBtn`, `maResetBtn`)
- Status (`maStatus`)

**Right panel: Saved Archive Items**
- Per-row card: thumbnail/file-icon + title + type pill + date · location + family line pill + text status pill + candidate-ready pill
- "Open / Edit" button per row
- List + status (`maList`, `maListStatus`)

### Detail/edit modal

Same layout as Photo Intake's view/edit modal:
- Full preview (image inline; PDF first-page render or generic icon)
- Open Original button (downloads / opens the full file)
- All metadata fields editable
- People + family_lines + links editable
- Buttons: Save Changes / Open Original / Mark Candidate Ready / Archive Only / Delete

### Operator launcher

Add to `ui/hornelore1.0.html` Operator/Media surface:

```html
<button class="lv-operator-card" onclick="window.open('media-archive.html', '_blank', 'noopener')">
  <span class="lv-operator-card-icon">📄</span>
  <span class="lv-operator-card-title">Document Archive</span>
  <span class="lv-operator-card-sub">Upload scanned documents, handwritten notes, genealogy files, and family records.</span>
</button>
```

---

## 6. Acceptance tests

### Test 1 — Upload scanned genealogy PDF (the Shong fixture)

**Setup:** `outline of the shong family.pdf` available in browser.

**Steps:**
1. Operator → Document Archive → upload page opens
2. Pick narrator (Christopher Todd Horne) — or leave blank
3. Drop PDF → file picker shows it
4. Title: "Outline of the Shong Family"
5. Document type: `genealogy_document`
6. Family line: "Shong"
7. Description: "Scanned genealogy outline compiled by Charlotte Graichen, Valley City, North Dakota."
8. Save

**Expected:**
- Status: "Saved." (green)
- Item appears in Saved Archive Items list
- `page_count` = 18 (auto-detected from PDF if poppler available)
- `text_status` = "image_only_needs_ocr" (or "not_started" if PDF page-count detection isn't wired)
- `archive_only` = true
- `candidate_ready` = false

### Test 2 — Preserve original

**Steps:** click "Open Original" in detail modal.

**Expected:**
- The original PDF opens (not a re-encoded copy)
- File exists at `DATA_DIR/media/archive/people/{pid}/documents/{item_id}/original.pdf`
- File size matches the source upload (no destructive conversion)

### Test 3 — Manual metadata round-trip

**Steps:**
1. Open detail modal
2. Add: family_line=Shong, description=full source attribution, location=Valley City North Dakota
3. Save Changes
4. Hard refresh page
5. Reopen modal

**Expected:** all metadata persisted.

### Test 4 — Manual transcription

**Steps:**
1. Detail modal → paste a short transcription from page 1 or 2 of the Shong PDF
2. Save
3. Hard refresh

**Expected:**
- `manual_transcription` field saves
- `text_status` flips to `manual_partial` (or stays `not_started` if transcription is short and the auto-promotion rule isn't wired)
- Round-trip verified

### Test 5 — Life Map / Timeline link

**Steps:** set `life_map_era=ancestry`, `life_map_section=Shong family line`, save.

**Expected:**
- Item displays a link pill in the saved list
- No automatic truth promotion
- DB row in `media_archive_links` table

### Test 6 — Non-photo file accepted by Media Archive (and rejected by Photo Intake)

**Steps:**
1. Try to upload the same Shong PDF via Photo Intake
2. Try to upload it via Media Archive

**Expected:**
- Photo Intake rejects (415 Unsupported Media Type — only image/* MIMEs allowed)
- Media Archive accepts

### Test 7 — Soft delete

**Steps:** delete item from detail modal.

**Expected:**
- Item disappears from default list
- DB row remains with `deleted_at` set
- File remains on disk
- `?include_deleted=true` brings it back

### Test 8 — Candidate-ready toggle does NOT auto-extract

**Steps:** toggle `candidate_ready` to true, save.

**Expected:**
- Item shows "Candidate Ready" pill
- NO write to Bio Builder questionnaire
- NO write to family_truth tables
- Item is just flagged for future review

### Smoke commands

```bash
cd /mnt/c/Users/chris/hornelore

curl -s http://localhost:8000/api/media-archive/health | jq
# Expected: {"ok":true,"enabled":true,"storage_root":"..."}

curl -s "http://localhost:8000/api/media-archive?family_line=Shong" | jq
# Expected: {"ok":true,"items":[{...Shong PDF row...}]}
```

---

## 7. Boris execution pack

### READ

Read these files first to absorb conventions before writing new code:

```
ui/photo-intake.html
ui/js/photo-intake.js
ui/css/photo-intake.css
ui/photo-timeline.html
ui/js/app.js
ui/hornelore1.0.html
server/code/api/main.py
server/code/api/routers/photos.py
server/code/services/photos/repository.py
server/code/services/photo_intake/storage.py
server/code/services/photo_intake/thumbnail.py
server/code/api/db.py
server/code/db/migrations/0001_lori_photo_shared.sql
server/code/db/migrations_runner.py
server/code/api/flags.py
```

### PLAN

**DO:** implement Media Archive lane in parallel to Photo Intake.
**DO NOT:** reuse `/api/photos` for PDFs/documents.
**DO NOT:** write extracted facts into Bio Builder questionnaire.
**DO NOT:** promote any source material as truth.
**DO NOT:** auto-launch OCR / handwriting recognition (deferred to WO-MEDIA-OCR-01).

Phase order:

1. **Phase 1 — DB migration:** new SQL file `server/code/db/migrations/0002_media_archive.sql` with the four tables + indexes.
2. **Phase 2 — Repository layer:** `server/code/services/media_archive/repository.py` with create/list/get/patch/soft_delete + replace_people + replace_family_lines + replace_links.
3. **Phase 3 — Storage layer:** `server/code/services/media_archive/storage.py` (file save, MIME validation, dir layout, meta.json mirror).
4. **Phase 4 — Thumbnail layer:** `server/code/services/media_archive/thumbnail.py` (Pillow for image inputs; PDF first-page if poppler available; null otherwise — never block upload).
5. **Phase 5 — Text probe:** `server/code/services/media_archive/text_probe.py` (PDF page-count detection if PyPDF2/pdfplumber present; otherwise leave page_count=null).
6. **Phase 6 — API router:** `server/code/api/routers/media_archive.py` with all 7 endpoints (health, POST, GET list, GET detail, PATCH, DELETE, file/thumb serving).
7. **Phase 7 — Flag + main wiring:** `flags.media_archive_enabled()` + `main.py` includes router.
8. **Phase 8 — UI page:** `ui/media-archive.html` + `ui/js/media-archive.js` + `ui/css/media-archive.css`.
9. **Phase 9 — Operator launcher + health checks:** add card to `hornelore1.0.html`; add `/api/media-archive/health` + page-reachable + launcher-exists checks to `ui-health-check.js` (use `http://localhost:8000` for API, `http://localhost:8082` for UI).

### PATCH

Implement each phase as its own logical commit — separate code from docs per CLAUDE.md.

Required new files:
```
server/code/db/migrations/0002_media_archive.sql
server/code/services/media_archive/__init__.py
server/code/services/media_archive/repository.py
server/code/services/media_archive/storage.py
server/code/services/media_archive/thumbnail.py
server/code/services/media_archive/text_probe.py
server/code/services/media_archive/types.py
server/code/api/routers/media_archive.py
ui/media-archive.html
ui/js/media-archive.js
ui/css/media-archive.css
```

Required modifications:
```
server/code/api/main.py            (router include + flag check)
server/code/api/flags.py           (add media_archive_enabled())
ui/hornelore1.0.html               (Operator/Media launcher card)
ui/js/ui-health-check.js           (3 new checks)
.env                               (HORNELORE_MEDIA_ARCHIVE_ENABLED=1)
docs/PHOTO-SYSTEM-TEST-PLAN.md     (cross-reference: PDF goes to Media Archive)
README.md                          (status block update)
HANDOFF.md                         (Media Archive section)
```

### TEST

Pre-flight (before stack restart):
```bash
cd /mnt/c/Users/chris/hornelore

python -m py_compile server/code/api/routers/media_archive.py
python -m py_compile server/code/services/media_archive/repository.py
python -m py_compile server/code/services/media_archive/storage.py
python -m py_compile server/code/services/media_archive/thumbnail.py
python -m py_compile server/code/services/media_archive/text_probe.py
node -c ui/js/media-archive.js
```

Post-cycle (after `.env` flag flip + stack restart):
```bash
curl -s http://localhost:8000/api/media-archive/health | jq
# Expected: {"ok":true,"enabled":true,"storage_root":"/mnt/c/hornelore_data/media/archive"}
```

Browser smoke (the 8 acceptance tests above, in order). Especially Test 1 (Shong PDF upload) and Test 2 (preserve original).

### REPORT

Format the close-out:

```markdown
WO-MEDIA-ARCHIVE-01 REPORT

Files changed:
- ...

Backend:
- health PASS/FAIL
- upload PASS/FAIL
- list PASS/FAIL
- detail PASS/FAIL
- patch PASS/FAIL
- delete PASS/FAIL
- file serve PASS/FAIL
- thumb serve PASS/FAIL

UI:
- launcher PASS/FAIL
- archive page PASS/FAIL
- upload form PASS/FAIL
- saved list PASS/FAIL
- modal PASS/FAIL
- people/family-line tagging PASS/FAIL

Smoke (Shong PDF):
- upload PASS/FAIL
- title/type/family_line tag PASS/FAIL
- page count detection PASS/FAIL
- metadata persistence PASS/FAIL
- manual transcription PASS/FAIL
- archive-only no extraction PASS/FAIL
- soft delete PASS/FAIL

Known deferred:
- OCR (WO-MEDIA-OCR-01)
- Handwriting recognition
- Candidate generation (WO-MEDIA-ARCHIVE-CANDIDATES-01)
- Visual Life Map archive cards
- Scanner watch-folder import (WO-MEDIA-WATCHFOLDER-01)
```

---

## 8. Commit message template

```
WO-MEDIA-ARCHIVE-01: scanner/document archive intake lane

Adds a separate Media Archive lane for scanned documents, PDFs,
handwritten notes, genealogy outlines, letters, records, and clippings.

This intentionally does not reuse Photo Intake. Photo Intake remains for
images shown to narrators. Media Archive preserves source documents as
evidence first, with optional transcription and candidate-readiness
later.

Backend:
- Add media_archive tables for archive items, people tags, family-line
  tags, and source links.
- Add repository / storage / thumbnail / text-probe service layer.
- Add /api/media-archive router with health, upload, list, detail,
  patch, soft-delete, file serve, thumb serve.
- Store originals unchanged under DATA_DIR/media/archive/.
- Support PDF, scanned image files, text, and markdown.
- Mirror DB row to meta.json on disk for forensic recovery.
- No automatic truth promotion and no automatic Bio Builder writes.

UI:
- Add media-archive.html curator page with the same visual style as
  Photo Intake.
- Drag/drop upload, narrator/family-line tagging, document type,
  date/location, Life Map/timeline fields, manual transcription,
  operator notes, archive-only and candidate-ready toggles.
- Saved archive list with type/date/family-line/text-status pills.
- Detail/edit modal with full preview, all-fields editing, replace-all
  people/family-line semantics matching WO-PHOTO-PEOPLE-EDIT-01.
- Document Archive launcher in Operator/Media surface.
- 3 new UI health checks (route reachable, page reachable,
  launcher-exists).

Smoke target:
- Upload outline of the shong family.pdf as genealogy_document.
- Tag family_line=Shong.
- Preserve original 18-page scanned PDF.
- Save manual transcription/notes.
- Confirm hard-refresh persistence.
- Confirm no extraction or promotion occurs automatically.

Deferred (separate WOs):
- OCR              -> WO-MEDIA-OCR-01
- Candidate gen    -> WO-MEDIA-ARCHIVE-CANDIDATES-01
- Watch folder     -> WO-MEDIA-WATCHFOLDER-01
- Handwriting      -> later, post-OCR

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

---

## 9. Long-term shape this WO locks in

```
Photo Intake     = memory prompts (narrator-facing)
Media Archive    = source preservation (curator-facing)
Bio Builder      = candidate review (curator-facing, gated)
Life Map / Memoir / Kawa = downstream surfaces after review
```

The four lanes don't auto-flow into each other. Every transition is an explicit operator action. This is what protects narrator-facing surfaces from raw scanned ancestor data, and protects family truth from accidental promotion of a curator's typed-but-unverified note.

---

## Revision history

| Date | What changed |
|---|---|
| 2026-04-26 | Initial spec authored from Chris's detailed requirements + visualschedulebot-pattern conventions. Build is the next session. |
