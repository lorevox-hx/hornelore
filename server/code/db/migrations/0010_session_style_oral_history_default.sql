-- WO-LORI-ORAL-HISTORY-DEFAULT-01 (2026-06-14)
--
-- Change the column default of memory_archive_sessions.session_style
-- from '' to 'oral_history'. The free-text column has no enum
-- constraint so no value-set extension is required.
--
-- WHAT THIS DOES:
--   - New sessions created via raw SQL (no app-level INSERT) will now
--     default to 'oral_history' if session_style is omitted from the
--     INSERT statement.
--   - The application-level default ALSO flips in memory_archive.py
--     (dataclass `session_style: str = "oral_history"`); that is the
--     primary path. This migration mirrors it at the schema level so
--     archeology + operator tooling read the same truth.
--
-- WHAT THIS DOES NOT DO:
--   - Existing rows are preserved unchanged. Their session_style values
--     stay whatever they were at the time of creation. Per WO §6
--     ("Existing sessions are not retroactively modified.")
--   - No new style enum / CHECK constraint is added. session_style
--     remains TEXT NOT NULL DEFAULT 'oral_history'. Operators can
--     write any string; the FE picker + session-style-router validate
--     the accepted set client-side.
--
-- WHY THE TABLE-REBUILD PATTERN:
--   SQLite < 3.35 does not support ALTER TABLE ... ALTER COLUMN ...
--   SET DEFAULT. The portable approach is to rename the existing
--   table, create a new one with the new default, copy rows over,
--   then drop the renamed original. This is atomic inside a single
--   transaction. Indexes (none on session_style today) and foreign
--   keys (none on this table) require no special handling here.

BEGIN TRANSACTION;

ALTER TABLE memory_archive_sessions
    RENAME TO memory_archive_sessions__pre_0010;

CREATE TABLE memory_archive_sessions (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
    conv_id TEXT NOT NULL,
    archive_dir TEXT NOT NULL,           -- relative to DATA_DIR
    audio_enabled INTEGER NOT NULL DEFAULT 0,
    video_enabled INTEGER NOT NULL DEFAULT 0,
    session_style TEXT NOT NULL DEFAULT 'oral_history',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO memory_archive_sessions (
    id, person_id, conv_id, archive_dir,
    audio_enabled, video_enabled, session_style,
    created_at, updated_at
)
SELECT
    id, person_id, conv_id, archive_dir,
    audio_enabled, video_enabled, session_style,
    created_at, updated_at
FROM memory_archive_sessions__pre_0010;

DROP TABLE memory_archive_sessions__pre_0010;

COMMIT;
