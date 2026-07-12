------------------------------------------------------------
-- 0032_trip_public_context_rejected.sql
-- WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight review-follow-up
-- (2026-07-11)
--
-- Adds a `rejected` flag to trip_public_context so bad public lookups
-- and stale place inferences can be hidden from the modal + narrator-
-- facing surfaces WITHOUT deleting the row (matches the Travel Doc
-- Lab's "hide, don't delete" posture and the trip_photo_context
-- ladder from 0030). Default 0 — existing rows keep their current
-- behavior.
--
-- Downstream (in this same commit):
--   * public_context_update(rejected=...) supported in the repo
--   * PublicContextPatch.rejected accepted in the router
--   * _public_context_for_scope() skips rejected rows (modal)
--   * trip_interview_context skips rejected rows (narrator surface)
--   * Travel Doc Lab shows Reject / Hide on public evidence rows
------------------------------------------------------------

BEGIN;

ALTER TABLE trip_public_context
    ADD COLUMN rejected INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_trip_public_context_rejected
    ON trip_public_context(trip_id, rejected);

COMMIT;
