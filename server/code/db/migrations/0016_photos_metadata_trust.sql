-- 0016_photos_metadata_trust.sql
-- WO-TRIP-PHOTO-STOP-UPLOAD-AND-ELICIT-01 Phase C1 (2026-07-05).
--
-- Per-file metadata trust, detected at intake from EXIF shape:
--   full | time_only | gps_only | suspect_scan | none | unknown
-- 'unknown' = row predates this migration or intake flag was off.
-- Reasons live in metadata_json.trust_reasons (non-authoritative).
--
-- Consumers: trip photo clustering (suspect_scan/none dates excluded
-- from the time score so scan dates can't confidently mis-cluster),
-- intake UI trust badge, Lori photo elicitation grounding (Phase C3).

ALTER TABLE photos ADD COLUMN metadata_trust TEXT NOT NULL DEFAULT 'unknown';
