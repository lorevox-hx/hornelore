-- WO-ARCHIVE-AUDIO-01 — Memory archive session + turn tracking.
--
-- The filesystem at DATA_DIR/memory/archive/people/<pid>/sessions/<conv_id>/
-- is the source of truth for transcript content and audio blobs.  These
-- tables are a fast index into the filesystem: they let the router answer
-- "which conv_ids does narrator X have archived?" without walking the
-- tree, and they record per-turn metadata that isn't cheap to re-derive
-- from jsonl on every read.
--
-- Archive session_id = conv_id.  The unique index enforces one archive
-- row per (person_id, conv_id).

BEGIN;

------------------------------------------------------------
-- memory_archive_sessions
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory_archive_sessions (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
    conv_id TEXT NOT NULL,
    archive_dir TEXT NOT NULL,           -- relative to DATA_DIR
    audio_enabled INTEGER NOT NULL DEFAULT 0,
    video_enabled INTEGER NOT NULL DEFAULT 0,
    session_style TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_archive_sessions_conv
    ON memory_archive_sessions(person_id, conv_id);

CREATE INDEX IF NOT EXISTS idx_memory_archive_sessions_person
    ON memory_archive_sessions(person_id);

------------------------------------------------------------
-- memory_archive_turns
------------------------------------------------------------
-- One row per appended transcript turn (both narrator and Lori).
-- Mirrors the transcript.jsonl append so the router can query "how
-- many confirmed narrator turns for conv_id X?" without re-parsing
-- the file.  audio_ref is ALWAYS null for role='lori' / 'assistant'
-- (enforced by router, constrained here by CHECK).
CREATE TABLE IF NOT EXISTS memory_archive_turns (
    id TEXT PRIMARY KEY,                 -- turn_id (client-provided or UUID)
    person_id TEXT NOT NULL,
    conv_id TEXT NOT NULL,
    seq INTEGER NOT NULL,                -- monotonically increasing within conv_id
    role TEXT NOT NULL,                  -- 'narrator' | 'user' | 'lori' | 'assistant'
    content TEXT NOT NULL DEFAULT '',
    audio_ref TEXT,                      -- 'audio/<turn_id>.webm' or NULL
    confirmed INTEGER NOT NULL DEFAULT 0,
    meta_json TEXT NOT NULL DEFAULT '{}',
    ts TEXT NOT NULL,

    CHECK (role IN ('narrator','user','lori','assistant')),
    CHECK (
        audio_ref IS NULL
        OR role IN ('narrator','user')
    )
);

CREATE INDEX IF NOT EXISTS idx_memory_archive_turns_conv
    ON memory_archive_turns(person_id, conv_id, seq);

CREATE INDEX IF NOT EXISTS idx_memory_archive_turns_turn
    ON memory_archive_turns(id);

COMMIT;
