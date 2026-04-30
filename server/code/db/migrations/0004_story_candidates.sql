-- WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 1 — story_candidates table.
--
-- LAW 3 [INFRASTRUCTURE]: every preserved narrator turn that meets the
-- story-trigger criteria gets a row here. The Path 1 (preservation)
-- write goes through this table; Path 2 (extraction) writes back via
-- extracted_fields/extraction_status. Operator review (LAW 4
-- STRUCTURAL) reads/updates the review_* columns.
--
-- Schema mirrors WO-LORI-STORY-CAPTURE-01_Spec.md §4 with one number
-- correction: the WO referenced 0042 because the example file path was
-- written before the migrations dir was actually surveyed; the live
-- runner sequences 0001 → 0002 → 0003 already, so this lands as 0004.
--
-- Idempotent: CREATE TABLE IF NOT EXISTS so re-running migration is a
-- no-op. Migration runner tracks applied filenames in schema_migrations
-- so this file only executes once per fresh DB anyway.

BEGIN;

CREATE TABLE IF NOT EXISTS story_candidates (
    -- Identity
    id                  TEXT PRIMARY KEY,           -- UUID
    narrator_id         TEXT NOT NULL,
    session_id          TEXT,
    conversation_id     TEXT,
    turn_id             TEXT,                       -- existing transcript turn FK
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Preservation payload (Path 1) — must be populated by every insert
    transcript          TEXT NOT NULL,              -- raw narrator text
    audio_clip_path     TEXT,                       -- relative to DATA_DIR; null OK if STT-only
    audio_duration_sec  REAL,
    word_count          INTEGER,
    trigger_reason      TEXT NOT NULL,              -- 'full_threshold' | 'borderline_scene_anchor' | 'manual'
    scene_anchor_count  INTEGER NOT NULL DEFAULT 0,

    -- Approximate placement (filled by Lori turn or operator review)
    era_candidates      TEXT NOT NULL DEFAULT '[]', -- JSON array of era_id strings
    age_bucket          TEXT,                       -- "very_little" | "in_school" | ...
    estimated_year_low  INTEGER,                    -- from DOB arithmetic
    estimated_year_high INTEGER,
    confidence          TEXT NOT NULL DEFAULT 'low', -- 'low' | 'medium' | 'high'

    -- Scene anchors (preserved even if extraction fails)
    scene_anchors       TEXT NOT NULL DEFAULT '[]', -- JSON array of strings

    -- Extraction outcome (Path 2 — may be empty if extraction failed)
    extraction_status   TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'partial' | 'complete' | 'failed'
    extracted_fields    TEXT NOT NULL DEFAULT '{}',       -- JSON of field_path -> value

    -- HITL review (LAW 4)
    review_status       TEXT NOT NULL DEFAULT 'unreviewed', -- 'unreviewed' | 'in_review' | 'promoted' | 'discarded' | 'memoir_only'
    review_notes        TEXT,
    reviewed_at         TEXT,
    reviewed_by         TEXT
);

CREATE INDEX IF NOT EXISTS idx_story_candidates_narrator
    ON story_candidates(narrator_id);

CREATE INDEX IF NOT EXISTS idx_story_candidates_review
    ON story_candidates(review_status);

CREATE INDEX IF NOT EXISTS idx_story_candidates_created
    ON story_candidates(created_at DESC);

COMMIT;
