------------------------------------------------------------
-- 0036_trip_evidence_hidden.sql
-- WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01 Phase 1 (2026-07-24)
--
-- Reversible hidden state for the three operator-deletable evidence
-- lanes. Operator "delete" on a location note or source is no longer
-- a physical DELETE — the row is stamped hidden=1 / hidden_at=<now>
-- and every consumer (travelogue builder, Draft Assistant, narrator
-- interview context, memoir preview/DOCX, default list endpoints)
-- excludes hidden rows. Restore = PATCH hidden:false (hidden_at is
-- cleared). Physical purge survives ONLY behind an explicit
-- ?purge=true&confirm_id=<exact row id> double-confirmation.
--
-- Tables:
--   * trip_location_notes — story-layer notes (operator / lori /
--     external / draft provenance). Hiding preserves the promotion
--     flags (include_in_memoir / include_in_interview_context) so a
--     restore returns the row to exactly its prior standing.
--   * trip_sources        — documents lane (files / pasted text /
--     links). Hiding never touches storage_path; the stored file is
--     removed only on an explicit purge.
--   * trip_photo_links    — photo joins. No DELETE endpoint exists
--     for links, but PATCH hidden:true lets the operator retire a
--     link from every consumer without losing the placement or the
--     caption/approval work; PATCH hidden:false restores it.
--
-- trip_story_links and trip_bio_suggestions are intentionally NOT
-- altered: neither has an operator delete endpoint (bio suggestions
-- are replaced wholesale by the timeline-bridge sync; story links
-- have no router surface), so there is nothing to make reversible.
--
-- trip_public_context / trip_photo_context already carry `rejected`
-- (0030/0032) — their DELETE endpoints are repurposed in this same
-- WO to set rejected=1 instead of deleting.
--
-- Default 0 — existing rows keep their current visibility.
------------------------------------------------------------

BEGIN;

ALTER TABLE trip_location_notes
    ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE trip_location_notes
    ADD COLUMN hidden_at TEXT;

ALTER TABLE trip_sources
    ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE trip_sources
    ADD COLUMN hidden_at TEXT;

ALTER TABLE trip_photo_links
    ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
ALTER TABLE trip_photo_links
    ADD COLUMN hidden_at TEXT;

CREATE INDEX IF NOT EXISTS idx_trip_location_notes_hidden
    ON trip_location_notes(trip_id, hidden);
CREATE INDEX IF NOT EXISTS idx_trip_sources_hidden
    ON trip_sources(trip_id, hidden);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_hidden
    ON trip_photo_links(trip_id, hidden);

COMMIT;
