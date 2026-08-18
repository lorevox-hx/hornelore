------------------------------------------------------------
-- 0045_sessions_legacy_payload_owner.sql
-- WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part C (2026-08-17)
--
-- 0044 recovered session ownership from three RECORDED LINKS:
-- interview_sessions, memory_archive_sessions, and durable turn
-- metadata. It deliberately did NOT read `payload_json`, because at the
-- time the measured content of that column was two bytes -- '{}' -- on
-- 56 of 56 recent rows, and a column that is empty on every row it was
-- measured against is not evidence.
--
-- It is not empty on every row. `upsert_session` has always accepted a
-- narrator inside the payload under either of two historical keys, and
-- `get_session_owner` / `list_sessions` / `session_ownership_residue`
-- all still read those keys, precisely because rows written that way
-- exist. This migration finishes the job 0044 started: where a session
-- has no explicit owner and its payload carries ONE structured,
-- unambiguous, existing narrator id, that id becomes the recorded
-- owner.
--
-- WHAT IS READ, AND NOTHING ELSE
--   payload_json.person_id
--   payload_json.active_person_id
-- Two structured fields. Not narrator prose, not a display name, not a
-- title, not a timestamp, not directory proximity, not "the only
-- narrator active that day", not UI history. If the answer is not in one
-- of those two keys as a bare id, this migration does not have one.
--
-- FIVE CONDITIONS, ALL REQUIRED
--   1. The row has no explicit owner (`person_id` NULL or blank).
--      An existing explicit owner is NEVER overwritten.
--   2. `payload_json` is valid JSON. Junk in that column yields no
--      candidate rather than an error; the row stays NULL and is
--      counted, not repaired.
--   3. Exactly one narrator id is established. Where both keys are
--      present they must AGREE; where they disagree the row stays NULL,
--      because two structured fields contradicting each other is
--      information and picking one is a silent resolution of it.
--   4. That id exists in `people`. A pointer to a narrator who is not
--      there is not ownership; it is a dangling string, and it is
--      reported as one.
--   5. It does not contradict a stronger recorded link, and no stronger
--      link is itself ambiguous. `payload_json` is the WEAKEST of the
--      four sources -- it is browser-supplied state that happened to be
--      persisted, where the other three are server-side records of a
--      relationship. So it yields to all of them. Where a stronger
--      source names exactly one narrator, 0044 has already written it
--      and condition 1 excludes the row; the guard is kept anyway so
--      this file is correct on its own terms rather than only in
--      sequence.
--
-- IDEMPOTENT. Every UPDATE is gated on `person_id IS NULL OR blank`, so
-- a second run selects nothing. The added column uses the runner's
-- one-file-one-transaction contract; re-running the file after a
-- successful apply is prevented by `schema_migrations`, and re-running
-- the UPDATE alone is a no-op.
--
-- `payload_json` IS NOT REWRITTEN, NOT TRIMMED AND NOT ERASED. The
-- legacy keys stay readable forever. Ownership is promoted out of the
-- payload into a column; it is not moved.
--
-- PROVENANCE IS RECORDED AT THE MOMENT IT IS KNOWN, per the rule this
-- repository earned in WO-SYSTEM-DIRECTIVE-PERSISTENCE-01: *when the
-- producer knows provenance, transmit it; never reconstruct it later
-- from prose.* This migration is the producer, so it adds
-- `person_id_source` and stamps 'legacy_payload_json' on exactly the
-- rows it fills.
--
-- It does NOT retro-stamp anything else. Rows 0044 recovered, and rows
-- a live writer owned explicitly, are indistinguishable from each other
-- today, and inventing a marker for them after the fact would be the
-- reconstruction the rule forbids. They stay NULL, and
-- `session_ownership_residue()` reports that honestly as
-- `owner_source_unrecorded` rather than folding them into either
-- category.
------------------------------------------------------------

BEGIN;

-- Nullable, like `person_id` itself. NULL means "provenance was not
-- captured", which is the truthful answer for every row that predates
-- this column.
ALTER TABLE sessions ADD COLUMN person_id_source TEXT;

-- The candidate set, computed once. A TEMP view keeps the five
-- conditions readable instead of repeating a 12-line CASE four times in
-- one WHERE clause; it is dropped at the end of the file.
DROP VIEW IF EXISTS _m0045_legacy_owner_candidates;

CREATE TEMP VIEW _m0045_legacy_owner_candidates AS
SELECT
    s.conv_id AS conv_id,

    -- Condition 3, first half: the id itself. `person_id` is preferred
    -- when both are present, but condition 3's agreement check below
    -- means the preference only ever chooses between equal values.
    CASE
      WHEN TRIM(COALESCE(json_extract(s.payload_json, '$.person_id'), '')) <> ''
        THEN TRIM(COALESCE(json_extract(s.payload_json, '$.person_id'), ''))
      ELSE TRIM(COALESCE(json_extract(s.payload_json, '$.active_person_id'), ''))
    END AS legacy_id,

    -- Condition 3, second half: both present and unequal.
    CASE
      WHEN TRIM(COALESCE(json_extract(s.payload_json, '$.person_id'), '')) <> ''
       AND TRIM(COALESCE(json_extract(s.payload_json, '$.active_person_id'), '')) <> ''
       AND TRIM(COALESCE(json_extract(s.payload_json, '$.person_id'), ''))
        <> TRIM(COALESCE(json_extract(s.payload_json, '$.active_person_id'), ''))
        THEN 1
      ELSE 0
    END AS fields_disagree,

    -- Condition 5: how many DIFFERENT narrators the three stronger
    -- sources name for this conv_id, and which one when there is
    -- exactly one.
    (
      SELECT COUNT(DISTINCT x.pid) FROM (
          SELECT isx.person_id AS pid
            FROM interview_sessions isx
           WHERE isx.id = s.conv_id
             AND isx.person_id IS NOT NULL
             AND TRIM(isx.person_id) <> ''
          UNION
          SELECT mas.person_id
            FROM memory_archive_sessions mas
           WHERE mas.conv_id = s.conv_id
             AND mas.person_id IS NOT NULL
             AND TRIM(mas.person_id) <> ''
          UNION
          SELECT json_extract(t.meta_json, '$.person_id')
            FROM turns t
           WHERE t.conv_id = s.conv_id
             AND json_valid(t.meta_json)
             AND json_extract(t.meta_json, '$.person_id') IS NOT NULL
             AND TRIM(json_extract(t.meta_json, '$.person_id')) <> ''
      ) x
    ) AS stronger_count,

    (
      SELECT MIN(x.pid) FROM (
          SELECT isx.person_id AS pid
            FROM interview_sessions isx
           WHERE isx.id = s.conv_id
             AND isx.person_id IS NOT NULL
             AND TRIM(isx.person_id) <> ''
          UNION
          SELECT mas.person_id
            FROM memory_archive_sessions mas
           WHERE mas.conv_id = s.conv_id
             AND mas.person_id IS NOT NULL
             AND TRIM(mas.person_id) <> ''
          UNION
          SELECT json_extract(t.meta_json, '$.person_id')
            FROM turns t
           WHERE t.conv_id = s.conv_id
             AND json_valid(t.meta_json)
             AND json_extract(t.meta_json, '$.person_id') IS NOT NULL
             AND TRIM(json_extract(t.meta_json, '$.person_id')) <> ''
      ) x
    ) AS stronger_id

  FROM sessions s
 -- Condition 1 and condition 2.
 WHERE (s.person_id IS NULL OR TRIM(s.person_id) = '')
   AND json_valid(s.payload_json);

UPDATE sessions
   SET person_id = (
        SELECT c.legacy_id
          FROM _m0045_legacy_owner_candidates c
         WHERE c.conv_id = sessions.conv_id
   ),
       person_id_source = 'legacy_payload_json'
 WHERE (person_id IS NULL OR TRIM(person_id) = '')
   AND EXISTS (
        SELECT 1
          FROM _m0045_legacy_owner_candidates c
         WHERE c.conv_id = sessions.conv_id
           -- Condition 3.
           AND c.fields_disagree = 0
           AND c.legacy_id <> ''
           -- Condition 4.
           AND EXISTS (SELECT 1 FROM people p WHERE p.id = c.legacy_id)
           -- Condition 5.
           AND c.stronger_count <= 1
           AND (c.stronger_count = 0 OR c.stronger_id = c.legacy_id)
   );

DROP VIEW IF EXISTS _m0045_legacy_owner_candidates;

COMMIT;
