-- 0022_trip_photo_links_lori_approval.sql
-- WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 Phase 5 (2026-07-09).
--
-- Approval-gated photo context for Lori. Locked rule: Lori may use ONLY
-- approved context — an operator-entered caption must NOT reach her
-- prompt just because the photo is narrator_ready (review finding
-- 2026-07-09: trip_interview_context surfaced `caption` with no
-- per-caption gate). narrator_caption (the narrator's OWN words from a
-- photo-elicit session) stays allowed by construction and needs no flag.
--
-- All approval flags DEFAULT 0 — nothing is approved by silence.

ALTER TABLE trip_photo_links ADD COLUMN caption_approved_for_lori INTEGER NOT NULL DEFAULT 0;
ALTER TABLE trip_photo_links ADD COLUMN operator_context_note TEXT;
ALTER TABLE trip_photo_links ADD COLUMN operator_context_approved_for_lori INTEGER NOT NULL DEFAULT 0;
