-- 0023_photos_date_review_lori_approval.sql
-- WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Phase 1 (2026-07-09).
--
-- Reviewable photo date/place metadata + Lori approval flags.
--   date_source: where the canonical date_value came from —
--     exif | filename_guess | operator_confirmed | missing | unknown
--     ('unknown' = row predates this migration).
--   taken_at_filename_guess: date parsed from the FILENAME (PXL_/IMG_
--     shapes). LOW CONFIDENCE — display only, NEVER auto-fills
--     date_value, never reaches Lori without explicit approval.
--   *_approved_for_lori: DEFAULT 0 — nothing is approved by silence.
--     Raw GPS (photos.latitude/longitude) stays private and is NEVER
--     exposed to Lori regardless of these flags; location approval
--     covers the operator-entered broad location_label only.

ALTER TABLE photos ADD COLUMN date_source TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE photos ADD COLUMN taken_at_filename_guess TEXT;
ALTER TABLE photos ADD COLUMN date_approved_for_lori INTEGER NOT NULL DEFAULT 0;
ALTER TABLE photos ADD COLUMN location_approved_for_lori INTEGER NOT NULL DEFAULT 0;
