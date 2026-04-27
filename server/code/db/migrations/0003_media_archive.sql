-- WO-MEDIA-ARCHIVE-01 — Phase 1 schema for the Document Archive lane.
--
-- Four tables: items + people + family_lines + links. Soft-delete on items.
-- Locked enums on document_type, date_precision, link_type, text_status.
-- Mirrors the Photo Intake conventions (provenance, soft-delete) but lives
-- on a separate table family so PDFs / scans / handwritten notes never
-- collide with photo-shaped metadata.
--
-- Product rule (locked, see WO-MEDIA-ARCHIVE-01_Spec.md §0):
--   Preserve first. Tag second. Transcribe / OCR third.
--   Extract candidates only after that. NEVER auto-promote to truth.

BEGIN;

------------------------------------------------------------
-- media_archive_items
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_archive_items (
    id TEXT PRIMARY KEY,

    -- Optional narrator + family-line scope. Nullable because some
    -- documents (a town history) belong to a family line but no single
    -- narrator; some (a generic letterhead scan) belong to neither yet.
    person_id TEXT,
    family_line TEXT,

    title TEXT NOT NULL,
    description TEXT,

    -- Locked enum mirrored in services/media_archive/types.py
    document_type TEXT NOT NULL DEFAULT 'unknown'
        CHECK (document_type IN (
            'genealogy_document',
            'handwritten_note',
            'letter',
            'certificate',
            'newspaper_clipping',
            'school_record',
            'military_record',
            'legal_record',
            'photo_scan_contact_sheet',
            'pdf_document',
            'typed_notes',
            'book_excerpt',
            'unknown'
        )),
    -- 'uploaded_file' is the v1 source. Future: 'scanner_watchfolder',
    -- 'email_import', 'cloud_sync', etc.
    source_kind TEXT NOT NULL DEFAULT 'uploaded_file',

    -- File-on-disk metadata. original_filename is what the operator
    -- saw at upload time (preserved for forensic audit), mime_type is
    -- what the server detected.
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_ext TEXT,
    file_size_bytes INTEGER,

    -- Where the original lives. Synthesized URLs (media_url + thumbnail_url)
    -- are filled at response time by _attach_archive_urls helper, mirroring
    -- the photos table convention (BUG-PHOTO-NULL-URLS).
    storage_path TEXT NOT NULL,
    media_url TEXT,
    thumbnail_url TEXT,

    -- Page count for PDFs. NULL if not detected (poppler missing).
    page_count INTEGER,

    -- Three independent status axes for text content lifecycle:
    text_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (text_status IN (
            'not_started',
            'image_only_needs_ocr',
            'manual_partial',
            'manual_complete',
            'ocr_partial',
            'ocr_complete',
            'mixed'
        )),
    transcription_status TEXT NOT NULL DEFAULT 'not_started'
        CHECK (transcription_status IN (
            'not_started','manual','ocr','mixed','complete'
        )),
    extraction_status TEXT NOT NULL DEFAULT 'none'
        CHECK (extraction_status IN (
            'none','candidates_pending','candidates_reviewed','complete'
        )),

    -- Text payload. ocr_text reserved for future WO-MEDIA-OCR-01;
    -- manual_transcription is what the operator types in the modal.
    -- summary is operator-authored description of the document's
    -- content (different from `description` which is source attribution).
    manual_transcription TEXT,
    ocr_text TEXT,
    summary TEXT,
    operator_notes TEXT,

    -- When/where the document is FROM (not when it was uploaded).
    date_value TEXT,
    date_precision TEXT NOT NULL DEFAULT 'unknown'
        CHECK (date_precision IN ('exact','month','year','decade','unknown')),
    location_label TEXT,
    location_source TEXT NOT NULL DEFAULT 'unknown',

    -- Optional anchors into Life Map / Timeline / Memoir surfaces.
    -- Items can attach to a year (timeline), an era (life_map_era),
    -- or a sub-section (life_map_section). All independent — a Shong
    -- genealogy outline might attach to era=ancestry + section=Shong
    -- line + no specific year (it spans many).
    timeline_year INTEGER,
    life_map_era TEXT,
    life_map_section TEXT,

    -- Authority flags. archive_only=1 means "preserve as evidence,
    -- don't surface to candidate review." candidate_ready=1 means
    -- "operator has reviewed, this is ready for WO-MEDIA-ARCHIVE-
    -- CANDIDATES-01 to harvest." needs_review surfaces items the
    -- operator should look at again.
    archive_only INTEGER NOT NULL DEFAULT 1
        CHECK (archive_only IN (0,1)),
    candidate_ready INTEGER NOT NULL DEFAULT 0
        CHECK (candidate_ready IN (0,1)),
    needs_review INTEGER NOT NULL DEFAULT 0
        CHECK (needs_review IN (0,1)),

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
CREATE INDEX IF NOT EXISTS idx_media_archive_timeline_year
    ON media_archive_items(timeline_year) WHERE deleted_at IS NULL;

------------------------------------------------------------
-- media_archive_people  (join table)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_archive_people (
    id TEXT PRIMARY KEY,
    archive_item_id TEXT NOT NULL,
    person_id TEXT,                        -- optional link to people row
    person_label TEXT NOT NULL,            -- always present, free-text
    role TEXT,                             -- e.g. 'subject','author','witness','relative'
    confidence TEXT NOT NULL DEFAULT 'curator_tagged',

    created_at TEXT NOT NULL,

    FOREIGN KEY (archive_item_id) REFERENCES media_archive_items(id)
);

CREATE INDEX IF NOT EXISTS idx_media_archive_people_item
    ON media_archive_people(archive_item_id);
CREATE INDEX IF NOT EXISTS idx_media_archive_people_person
    ON media_archive_people(person_id);

------------------------------------------------------------
-- media_archive_family_lines  (join table)
------------------------------------------------------------
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
CREATE INDEX IF NOT EXISTS idx_media_archive_family_lines_family
    ON media_archive_family_lines(family_line);

------------------------------------------------------------
-- media_archive_links
------------------------------------------------------------
-- Generic link table — an archive item can attach to a Life Map era,
-- a timeline year, a memoir section, a family-tree person, a Bio
-- Builder candidate, a Kawa segment, or just be tagged with a free
-- source note. link_target shape depends on link_type (year as int
-- string, era as enum string, person_id as UUID, etc.).
CREATE TABLE IF NOT EXISTS media_archive_links (
    id TEXT PRIMARY KEY,
    archive_item_id TEXT NOT NULL,

    link_type TEXT NOT NULL
        CHECK (link_type IN (
            'life_map_era',
            'timeline_year',
            'memoir_section',
            'family_tree_person',
            'bio_builder_candidate',
            'kawa_segment',
            'source_note'
        )),
    link_target TEXT NOT NULL,
    label TEXT,                            -- optional human-readable label

    created_at TEXT NOT NULL,

    FOREIGN KEY (archive_item_id) REFERENCES media_archive_items(id)
);

CREATE INDEX IF NOT EXISTS idx_media_archive_links_item
    ON media_archive_links(archive_item_id);
CREATE INDEX IF NOT EXISTS idx_media_archive_links_type_target
    ON media_archive_links(link_type, link_target);

COMMIT;
