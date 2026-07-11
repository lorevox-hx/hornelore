------------------------------------------------------------
-- 0031_trip_photo_context_draft_observation.sql
-- WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11)
--
-- Extend trip_photo_context.context_type CHECK to include
-- 'draft_observation' — the local-LLM-drafted image observation lane
-- that stays UNTIL an operator approves it. Same approval ladder as
-- OCR / vision:
--   * confidence DEFAULT 'draft'
--   * approved_for_lori DEFAULT 0
--   * include_in_memoir DEFAULT 0
--   * rejected          DEFAULT 0
-- Editing result_summary/raw_text revokes approved_for_lori (enforced
-- in the repository, same as OCR/vision).
--
-- SQLite doesn't support ALTER TABLE ... DROP/ADD CHECK, so we rebuild
-- the table using the standard copy-drop-rename pattern, preserving
-- every row + all four indexes from 0030.
--
-- Migration is idempotent under schema_migrations tracking; safe to
-- re-run because the rebuild body is wrapped in a transaction and the
-- new table shape is compared implicitly (schema_migrations skips
-- already-applied filenames).
------------------------------------------------------------

BEGIN;

CREATE TABLE IF NOT EXISTS trip_photo_context__new (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    photo_link_id TEXT NOT NULL
        REFERENCES trip_photo_links(id) ON DELETE CASCADE,
    photo_id TEXT,
    context_type TEXT NOT NULL CHECK (context_type IN (
        'ocr_text', 'vision_description', 'filename_context',
        'operator_photo_context', 'draft_observation')),
    result_summary TEXT NOT NULL,
    raw_text TEXT,
    confidence TEXT NOT NULL DEFAULT 'draft',
    engine TEXT,
    model_name TEXT,
    source_ref TEXT,
    approved_for_lori INTEGER NOT NULL DEFAULT 0,
    include_in_memoir INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO trip_photo_context__new (
    id, trip_id, photo_link_id, photo_id, context_type, result_summary,
    raw_text, confidence, engine, model_name, source_ref,
    approved_for_lori, include_in_memoir, rejected, created_at, updated_at
)
SELECT
    id, trip_id, photo_link_id, photo_id, context_type, result_summary,
    raw_text, confidence, engine, model_name, source_ref,
    approved_for_lori, include_in_memoir, rejected, created_at, updated_at
FROM trip_photo_context;

DROP TABLE trip_photo_context;
ALTER TABLE trip_photo_context__new RENAME TO trip_photo_context;

CREATE INDEX IF NOT EXISTS idx_trip_photo_context_trip
    ON trip_photo_context(trip_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_context_link
    ON trip_photo_context(photo_link_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_context_approved
    ON trip_photo_context(photo_link_id, approved_for_lori);

COMMIT;
