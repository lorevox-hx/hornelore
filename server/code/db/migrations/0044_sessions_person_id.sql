------------------------------------------------------------
-- 0044_sessions_person_id.sql
-- WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 commit 2 (2026-08-16)
--
-- `sessions` has carried no narrator ownership since it was created.
-- The table is (conv_id PK, title, updated_at, payload_json), and
-- `payload_json` is literally '{}' -- two bytes -- on every recent row.
-- Measured during the L2 partial run on 2026-08-16: 56 of 56 rows.
--
-- The consequence is not cosmetic. `get_narrator_state_snapshot`
-- computes `user_turn_count` by joining turns -> sessions on
-- json_extract(payload_json,'$.active_person_id'), so the count is
-- STRUCTURALLY always 0, and the UI -- which gates its "welcome back"
-- resume prompt on that number -- treats every returning narrator as
-- brand new. Four sessions created during L2 itself could not be
-- attributed to anyone, including the agent that created them.
--
-- NULLABLE, deliberately. All existing rows legitimately have no known
-- owner. NOT NULL would require inventing one, and inventing ownership
-- is precisely what this lane exists to stop.
--
-- NO SQLITE FOREIGN KEY, but an ENFORCED DELETION POLICY. SQLite cannot
-- add a REFERENCES clause by ALTER; the house precedent for retrofitting
-- one is the two-phase table REBUILD in 0034_trips_person_id_fk.sql, and
-- rebuilding `sessions` rewrites the parent of the entire chat corpus.
-- That is not a trade this migration makes.
--
-- The behaviour a CASCADE would have given is therefore implemented
-- where deletion actually happens, and is testable there:
--   * `sessions` joins _EXTENDED_PERSON_SCOPED_TABLES, so
--     hard_delete_person removes a narrator's sessions explicitly, and
--     `turns` follows through its EXISTING
--     `FOREIGN KEY(conv_id) REFERENCES sessions(conv_id) ON DELETE
--     CASCADE`.
--   * person_delete_inventory counts them, so the operator sees them
--     before confirming.
--   * db.session_ownership_residue() reports what a delete could NOT
--     reach — the ownerless rows — instead of leaving them silent.
-- The gap that remains is exactly the unowned historical rows, and it is
-- reported rather than inferred away.
--
-- The index matches the house idx_<table>_<cols> shape and the
-- idx_media_person_created composite pattern, and it directly serves
-- list_sessions' `ORDER BY updated_at DESC`.
--
-- BACKFILL: RECORDED LINKS ONLY, in descending order of proof strength.
-- Three sources, each a STORED FACT about this exact conv_id rather than
-- an inference about it:
--
--   1. interview_sessions.id = sessions.conv_id
--      The strongest link and the one that reconciles the two session
--      systems. `chat_ws` calls ensure_interview_session(conv_id,
--      person_id) for the SAME conv_id whose sessions row it leaves
--      ownerless -- the narrator was already being written down, one
--      table over, under the identical key.
--
--   2. memory_archive_sessions(person_id, conv_id)
--      An explicit pair recorded when the archive was created.
--
--   3. turns.meta_json -> '$.person_id'
--      Durable per-turn metadata, where a writer happened to record it.
--
-- Each pass fills only rows still NULL, so a weaker source never
-- overrides a stronger one. Every pass carries a COUNT(DISTINCT ...) = 1
-- guard: where a source knows exactly one narrator we adopt it; where it
-- knows two, we DECLINE rather than pick. Ambiguity stays NULL.
--
-- Nothing is attributed by timestamp adjacency, by "the only narrator
-- active that day", by archive-directory proximity, or by anything read
-- out of narrator prose. Expect many historical rows to stay NULL.
-- That is the correct outcome, and db.count_sessions_without_owner()
-- exists so the remainder is reported as a number instead of improved
-- by cleverness.
------------------------------------------------------------

BEGIN;

ALTER TABLE sessions ADD COLUMN person_id TEXT;

CREATE INDEX IF NOT EXISTS idx_sessions_person_updated
    ON sessions(person_id, updated_at);

-- Pass 1 — interview_sessions, keyed on the identical id.
UPDATE sessions
   SET person_id = (
        SELECT MIN(isx.person_id)
          FROM interview_sessions isx
         WHERE isx.id = sessions.conv_id
   )
 WHERE person_id IS NULL
   AND (
        SELECT COUNT(DISTINCT isx.person_id)
          FROM interview_sessions isx
         WHERE isx.id = sessions.conv_id
   ) = 1;

-- Pass 2 — memory archive pairs.
UPDATE sessions
   SET person_id = (
        SELECT MIN(mas.person_id)
          FROM memory_archive_sessions mas
         WHERE mas.conv_id = sessions.conv_id
   )
 WHERE person_id IS NULL
   AND (
        SELECT COUNT(DISTINCT mas.person_id)
          FROM memory_archive_sessions mas
         WHERE mas.conv_id = sessions.conv_id
   ) = 1;

-- Pass 3 — durable turn metadata, where a writer recorded it.
UPDATE sessions
   SET person_id = (
        SELECT MIN(json_extract(t.meta_json, '$.person_id'))
          FROM turns t
         WHERE t.conv_id = sessions.conv_id
           AND json_extract(t.meta_json, '$.person_id') IS NOT NULL
   )
 WHERE person_id IS NULL
   AND (
        SELECT COUNT(DISTINCT json_extract(t.meta_json, '$.person_id'))
          FROM turns t
         WHERE t.conv_id = sessions.conv_id
           AND json_extract(t.meta_json, '$.person_id') IS NOT NULL
   ) = 1;

COMMIT;
