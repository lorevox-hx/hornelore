------------------------------------------------------------
-- 0046_story_review_authority.sql
-- WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit A (2026-08-17)
--
-- Captured stories have been preserved since migration 0004 and reviewed
-- by nobody: `story_candidate_update_review` exists, is transactional and
-- validated, and has zero production callers. Every row in the live
-- database is `unreviewed`. The operator surface is read-only and the
-- only list accessor filters to `unreviewed`, so a row that WAS acted on
-- would vanish from the one place it could be seen.
--
-- This migration adds the three columns a server-authoritative review
-- needs, and nothing else. It does not touch the preserved transcript,
-- it does not reclassify a single existing row, and it adds no state.
--
-- ── placement_source ────────────────────────────────────────────────
-- WHERE a story's date placement came from. Four values:
--
--   unknown         no placement, or a placement whose origin is not
--                   recorded. THE DEFAULT, and the honest answer for
--                   every row that predates this column.
--   narrator_stated the narrator said when it happened.
--   operator_set    a human reviewer placed it.
--   dob_derived     computed from the date of birth by age arithmetic.
--
-- EXISTING ROWS ALL BECOME `unknown`, and that is deliberate. The
-- temptation is to infer: rows with `confidence='high'` look stated,
-- rows with a year range look derived. **Confidence is not provenance.**
-- It is a measure of how sure the capture heuristic was, set at insert
-- time by `preserve_turn` from the trigger reason alone -- it says
-- nothing about who decided when the story happened. Inferring
-- provenance from it would manufacture exactly the claim this column
-- exists to make honest.
--
-- Measured on the live database at the time of writing: 75 candidates,
-- all `unreviewed`, all `confidence='low'`, none carrying a year or an
-- era. There is nothing to infer FROM even if inferring were allowed.
--
-- The chronology lane's existing rule -- `stated` when a year is present
-- AND confidence is high, `derived` otherwise -- is precisely the
-- heuristic this column replaces. It could only ever have produced
-- `derived`, because nothing sets confidence above `medium`.
--
-- ── review_version ──────────────────────────────────────────────────
-- Monotonically increasing, starting at 1. Every review mutation must
-- carry the version it observed; the write compares and increments
-- inside one transaction and refuses a stale one with 409.
--
-- Two operators on one candidate is not hypothetical here: the Bug Panel
-- refetches on window focus, so the same person with two tabs open is
-- the ordinary case. Without this, the second save silently overwrites
-- the first and neither operator is told.
--
-- ── updated_at ──────────────────────────────────────────────────────
-- Distinct from `reviewed_at`, which records the last REVIEW decision.
-- `updated_at` moves on any mutation, including a placement edit that
-- leaves the review status alone.
--
-- IDEMPOTENT by the runner's schema_migrations contract; the UPDATEs are
-- additionally guarded so re-running the body changes nothing.
------------------------------------------------------------

BEGIN;

ALTER TABLE story_candidates ADD COLUMN placement_source TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE story_candidates ADD COLUMN review_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE story_candidates ADD COLUMN updated_at TEXT;

-- Seed `updated_at` from what each row already knows about itself. This
-- is a display and ordering convenience, not a claim about when the row
-- was last touched -- `reviewed_at` is preferred where a review actually
-- happened, `created_at` otherwise.
UPDATE story_candidates
   SET updated_at = COALESCE(reviewed_at, created_at)
 WHERE updated_at IS NULL;

-- Defensive: the ALTER default covers every existing row, but a partially
-- applied migration or a hand-edited row could leave a blank. A blank
-- placement_source would read as a missing answer rather than as the
-- honest `unknown`.
UPDATE story_candidates
   SET placement_source = 'unknown'
 WHERE placement_source IS NULL OR TRIM(placement_source) = '';

UPDATE story_candidates
   SET review_version = 1
 WHERE review_version IS NULL OR review_version < 1;

-- The operator surface filters by status and scopes to one narrator.
CREATE INDEX IF NOT EXISTS idx_story_candidates_narrator_status
    ON story_candidates(narrator_id, review_status, created_at);

COMMIT;
