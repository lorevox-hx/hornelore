------------------------------------------------------------
-- 0048_story_candidate_turn_provenance_integrity.sql
-- WO-LORI-CONVERSATION-TO-LIFE-MAP-MEMOIR-01, Commit 2 (2026-08-19)
--
-- Migration 0047 added `source_user_turn_row_id` and
-- `completed_assistant_turn_row_id` and described them as references to
-- committed rows. They are plain INTEGERs: SQLite cannot add a REFERENCES
-- clause to an existing table without a full rebuild, and 0047 is pushed
-- and must not be rewritten.
--
-- The gap that leaves is specific and worth naming. `turns` rows are
-- deleted by cascade whenever their session goes (see the FK on
-- `turns.conv_id`), and a hard-deleted narrator takes their sessions with
-- them. Without integrity, a story candidate could be left holding an id
-- that points at nothing -- or, far worse, at a row id SQLite has since
-- reissued to a completely different conversation. A dangling id looks
-- exactly like a real one, and a WRONG provenance record is more harmful
-- than an absent one, because nothing downstream can tell it is wrong.
--
-- ── WHY TRIGGERS AND NOT A TABLE REBUILD ────────────────────────────
--
-- A rebuild of `story_candidates` would rewrite every preserved narrator
-- transcript in the database to add a constraint. Preservation is the one
-- thing in this system that must never be risked for tidiness, and the
-- behaviour a FK would give (`ON DELETE SET NULL`) is expressible exactly
-- as a trigger without touching a single stored word.
--
-- ── WHAT THE TRIGGERS DO, AND DELIBERATELY DO NOT DO ────────────────
--
-- On deleting a turn: NULL the matching provenance column, and NOTHING
-- else. The story candidate itself SURVIVES. This is the whole point --
-- the narrator said those words, and losing the record of a conversation
-- must not delete the story that came out of it. The story simply becomes
-- unlinked again, which is an honest state it already knows how to be in.
--
-- The two columns are cleared INDEPENDENTLY, matching the rule that they
-- are two different facts. Deleting Lori's row costs the extraction join
-- and leaves the narrator-row provenance intact; deleting the narrator's
-- row costs the source pointer and leaves the join key intact. Neither is
-- derived from the other here, as nowhere else.
--
-- Review state, placement, era candidates and the transcript are never
-- touched by these triggers. Deleting a turn is not a review decision.
------------------------------------------------------------

DROP TRIGGER IF EXISTS trg_turns_delete_clears_story_source_user;
CREATE TRIGGER trg_turns_delete_clears_story_source_user
AFTER DELETE ON turns
FOR EACH ROW
WHEN OLD.id IS NOT NULL
BEGIN
    UPDATE story_candidates
       SET source_user_turn_row_id = NULL
     WHERE source_user_turn_row_id = OLD.id;
END;

DROP TRIGGER IF EXISTS trg_turns_delete_clears_story_completed_assistant;
CREATE TRIGGER trg_turns_delete_clears_story_completed_assistant
AFTER DELETE ON turns
FOR EACH ROW
WHEN OLD.id IS NOT NULL
BEGIN
    UPDATE story_candidates
       SET completed_assistant_turn_row_id = NULL
     WHERE completed_assistant_turn_row_id = OLD.id;
END;

-- Existing rows need no repair: 0047 left every historical candidate NULL
-- and nothing could have been bound before this migration ran, so there
-- is no dangling id in the database to clean up. Stated rather than
-- assumed, because "no backfill needed" is a claim about data and this
-- one was checked: 75 candidates, all NULL on both columns.
