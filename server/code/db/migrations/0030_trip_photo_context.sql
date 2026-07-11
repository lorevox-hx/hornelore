------------------------------------------------------------
-- 0030_trip_photo_context.sql
-- WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1 (2026-07-10)
--
-- Draft evidence extracted FROM a photo (OCR text off a sign/menu/
-- ticket/museum label, or an optional image-context description), stored
-- for the OPERATOR Travel Doc workspace. This is a dedicated table, NOT
-- an overload of trip_photo_links.operator_context_note.
--
-- Approval ladder (locked): raw evidence -> draft -> approved_for_lori
-- -> include_in_memoir. Nothing moves up by silence:
--   * approved_for_lori DEFAULT 0
--   * include_in_memoir DEFAULT 0
--   * rejected          DEFAULT 0
-- Editing result_summary/raw_text revokes approved_for_lori (enforced in
-- the repository, mirroring public_context / photo_link caption
-- semantics). Rejected rows are never read by Lori.
--
-- FK: photo_link_id -> trip_photo_links(id) ON DELETE CASCADE, so
-- deleting a photo link removes its extracted context (no orphans).
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trip_photo_context (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    photo_link_id TEXT NOT NULL
        REFERENCES trip_photo_links(id) ON DELETE CASCADE,
    photo_id TEXT,
    context_type TEXT NOT NULL CHECK (context_type IN (
        'ocr_text', 'vision_description', 'filename_context',
        'operator_photo_context')),
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

CREATE INDEX IF NOT EXISTS idx_trip_photo_context_trip
    ON trip_photo_context(trip_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_context_link
    ON trip_photo_context(photo_link_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_context_approved
    ON trip_photo_context(photo_link_id, approved_for_lori);
