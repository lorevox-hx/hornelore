-- WO-LORI-PHOTO-SHARED-01 — Phase 1 schema for the shared photo authority layer.
--
-- Six tables, locked enums, provenance columns on every authoring surface,
-- STT-safety columns on photo_memories (WO-STT-LIVE-02 integration),
-- soft-delete on photos, no dangling `shown` outcome possible after
-- POST /sessions/{id}/end (enforced by repository + test, not schema).

BEGIN;

------------------------------------------------------------
-- photos
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    narrator_id TEXT NOT NULL,

    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    media_url TEXT,
    thumbnail_url TEXT,

    file_hash TEXT NOT NULL UNIQUE,

    description TEXT,

    date_value TEXT,
    date_precision TEXT NOT NULL DEFAULT 'unknown'
        CHECK (date_precision IN ('exact', 'month', 'year', 'decade', 'unknown')),

    location_label TEXT,
    location_source TEXT NOT NULL DEFAULT 'unknown'
        CHECK (location_source IN (
            'exif_gps',
            'typed_address',
            'spoken_place',
            'description_geocode',
            'unknown'
        )),

    latitude REAL,
    longitude REAL,

    narrator_ready INTEGER NOT NULL DEFAULT 0,
    needs_confirmation INTEGER NOT NULL DEFAULT 1,

    -- Provenance columns (authoritative; metadata_json is non-authoritative)
    uploaded_by_user_id TEXT,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_edited_by_user_id TEXT,
    last_edited_at TEXT,
    deleted_at TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photos_narrator_id
    ON photos(narrator_id);
CREATE INDEX IF NOT EXISTS idx_photos_narrator_ready
    ON photos(narrator_id, narrator_ready);
CREATE INDEX IF NOT EXISTS idx_photos_date
    ON photos(date_value, date_precision);
CREATE INDEX IF NOT EXISTS idx_photos_uploaded_by
    ON photos(uploaded_by_user_id);
CREATE INDEX IF NOT EXISTS idx_photos_deleted_at
    ON photos(deleted_at);

------------------------------------------------------------
-- photo_people
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_people (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    person_id TEXT,
    person_label TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_actor_id TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_people_photo_id
    ON photo_people(photo_id);

------------------------------------------------------------
-- photo_events
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_events (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    event_id TEXT,
    event_label TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_actor_id TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_events_photo_id
    ON photo_events(photo_id);

------------------------------------------------------------
-- photo_sessions
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_sessions (
    id TEXT PRIMARY KEY,
    narrator_id TEXT NOT NULL,
    session_id TEXT,

    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photo_sessions_narrator_id
    ON photo_sessions(narrator_id);
CREATE INDEX IF NOT EXISTS idx_photo_sessions_open
    ON photo_sessions(narrator_id, ended_at);

------------------------------------------------------------
-- photo_session_shows
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_session_shows (
    id TEXT PRIMARY KEY,
    photo_session_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,

    shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    outcome TEXT NOT NULL DEFAULT 'shown'
        CHECK (outcome IN (
            'shown',
            'story_captured',
            'zero_recall',
            'distress_abort',
            'skipped',
            'technical_abort'
        )),

    prompt_text TEXT,
    followup_text TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_session_id) REFERENCES photo_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_session_shows_session_id
    ON photo_session_shows(photo_session_id);
CREATE INDEX IF NOT EXISTS idx_photo_session_shows_photo_id
    ON photo_session_shows(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_session_shows_outcome
    ON photo_session_shows(photo_id, outcome, shown_at);

------------------------------------------------------------
-- photo_memories
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_memories (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    photo_session_show_id TEXT NOT NULL,

    transcript TEXT NOT NULL DEFAULT '',

    memory_type TEXT NOT NULL DEFAULT 'episodic_story'
        CHECK (memory_type IN (
            'episodic_story',
            'emotional_flash',
            'general_mood',
            'zero_recall',
            'distress_abort'
        )),

    -- STT transcript safety (integrates with WO-STT-LIVE-02)
    transcript_source TEXT,
    transcript_confidence REAL,
    transcript_guard_flags TEXT,
    finalized_at TEXT,

    -- Provenance
    source_type TEXT NOT NULL DEFAULT 'narrator_story',
    source_authority TEXT NOT NULL DEFAULT 'narrator',
    source_actor_id TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
    FOREIGN KEY(photo_session_show_id) REFERENCES photo_session_shows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_memories_photo_id
    ON photo_memories(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_memories_show_id
    ON photo_memories(photo_session_show_id);

COMMIT;
