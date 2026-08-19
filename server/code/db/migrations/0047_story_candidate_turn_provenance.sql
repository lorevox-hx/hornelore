------------------------------------------------------------
-- 0047_story_candidate_turn_provenance.sql
-- WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit 1 (2026-08-19)
--
-- A preserved story has never been connectable to the turn it came from.
--
-- `story_candidates.turn_id` (migration 0004) is annotated
-- `-- existing transcript turn FK`. It is not one, and cannot be: it
-- holds the CLIENT-supplied `params.turn_id`, and the `turns` table has
-- no `turn_id` column at all -- only an autoincrement `id`. Measured on
-- the live database before this migration: 22 of 75 candidates have it
-- NULL or empty, and 0 of 75 can be joined to anything by it.
--
-- The consequence is the gap this work order exists to close.
-- `turn_extraction_results` already stores real extraction output,
-- durably and narrator-scoped, keyed on `turnrow:<turns.id>` -- a good
-- key derived from a committed row. But nothing bridges it to a story.
-- Measured: the 6 sessions holding extraction results contain 0 story
-- candidates, and 0 candidates join a result by any key. In 75 captures
-- and 7 extractions the two halves of the pipeline have never met.
--
-- ── TWO ROWS, NOT ONE ───────────────────────────────────────────────
--
-- A completed turn commits TWO rows in `turns`: the narrator's and
-- Lori's. They are different facts and this migration keeps them apart.
--
--   source_user_turn_row_id
--       `turns.id` of the NARRATOR's row -- the words the story was
--       preserved from. This is the provenance a reader wants: "which
--       sentence did this story come from".
--
--   completed_assistant_turn_row_id
--       `turns.id` of LORI's row for the same completed turn. This is
--       the identity extraction uses: `persist_turn_transaction` returns
--       the assistant row id, and `turn_extraction_results.turn_key` is
--       built as `turnrow:<that id>`. It is the join key, and nothing
--       else.
--
-- COLLAPSING THESE WOULD BE A DATA-INTEGRITY BUG, and so would deriving
-- one from the other. They are commonly adjacent integers today, but
-- adjacency is an artefact of one transaction's insert order, not a
-- contract: a floor-buffer turn, a retry, or any future writer between
-- them breaks it. Both ids are recorded because both are known at
-- commit time; neither is ever computed from the other.
--
-- ── WHAT THIS DOES NOT DO ───────────────────────────────────────────
--
-- No UNIQUE constraint. Nothing in the product contract says one turn
-- may produce at most one preserved record -- a single narrator answer
-- can legitimately yield more than one piece of evidence, and a
-- constraint asserting otherwise would start refusing captures, which
-- is the one thing preservation may never do (LAW 3).
--
-- These columns carry PROVENANCE ONLY. They approve nothing, place
-- nothing and promote nothing. `review_status`, `placement_source`,
-- `era_candidates` and the estimated years are untouched here and are
-- untouched by the code that fills these in. Linking a story to its
-- turn tells you where it came from; it does not make it true.
--
-- Existing rows are left NULL. No historical value is guessed at: the
-- only durable link available for the 75 existing candidates would have
-- to come from prose similarity, timestamp proximity or a "nearest
-- turn" heuristic, and a provenance record invented by a heuristic is
-- worse than an absent one -- it looks authoritative and cannot be
-- distinguished later from a real link.
------------------------------------------------------------

ALTER TABLE story_candidates ADD COLUMN source_user_turn_row_id INTEGER;
ALTER TABLE story_candidates ADD COLUMN completed_assistant_turn_row_id INTEGER;

-- Provenance lookups run narrator-first, matching every other read on
-- this table. Neither index is unique, deliberately (see above).
CREATE INDEX IF NOT EXISTS idx_story_candidates_source_user_turn
    ON story_candidates(narrator_id, source_user_turn_row_id);

CREATE INDEX IF NOT EXISTS idx_story_candidates_completed_assistant_turn
    ON story_candidates(narrator_id, completed_assistant_turn_row_id);
