-- WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — interview_threads table.
--
-- Persistent thread bank for unresolved story doors. When a narrator
-- mentions multiple anchors in one turn, Lori gently follows ONE and
-- silently banks the rest for later surfacing. Per WO §3 thread bank.
--
-- ─────────────────────────────────────────────────────────────────
-- SCHEMA
-- ─────────────────────────────────────────────────────────────────
--
-- The CREATE TABLE statement also lives in api/db.py init_db() so
-- the schema is built on cold-start without depending on a migrations
-- runner. This file is the authoritative documentation of the table
-- shape; init_db() mirrors it.
--
-- Column intent:
--   id                  uuid primary key
--   session_id          fk to interview_sessions(id) — DEFERRABLE-style
--                       FK is enforced at write time via ensure_session
--   tenant_id           per universal pivot strategy — operator's
--                       tenant; "default" for legacy / single-tenant
--                       installations
--   thread_anchor       the narrator-named entity / phrase the thread
--                       is about ("grandmother", "the train ride")
--   source_turn_index   which narrator turn introduced it (0-indexed)
--   source_excerpt      1-2 sentence quote from source turn (≤ 240
--                       chars) for the surfacing template
--   introduced_at       ISO timestamp at write
--   status              'open' | 'surfaced' | 'resolved' | 'declined'
--   surfaced_at         ISO timestamp when Lori surfaced it, NULL
--                       while open
--   resolved_at         ISO timestamp when narrator substantively
--                       engaged, NULL otherwise
--   category            'person' | 'place' | 'event' | 'object' |
--                       'time_period' — coarse classification from
--                       NER + heuristic
--
-- Indexes:
--   idx_threads_session_status  — most common query: open threads
--                                  for current session
--   idx_threads_introduced_at   — for age-based surfacing (oldest
--                                  open thread wins ties)

CREATE TABLE IF NOT EXISTS interview_threads (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    tenant_id           TEXT DEFAULT 'default',
    thread_anchor       TEXT NOT NULL,
    source_turn_index   INTEGER DEFAULT 0,
    source_excerpt      TEXT DEFAULT '',
    introduced_at       TEXT NOT NULL,
    status              TEXT DEFAULT 'open',
    surfaced_at         TEXT,
    resolved_at         TEXT,
    category            TEXT DEFAULT '',
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_threads_session_status
    ON interview_threads(session_id, status);

CREATE INDEX IF NOT EXISTS idx_threads_introduced_at
    ON interview_threads(introduced_at);

-- Vocabulary note: status enum values are documented above. SQLite
-- has no native ENUM constraint; the api.services.thread_bank module
-- is the authoritative enum source. A future tightening could add a
-- CHECK constraint; out of scope for v1 to avoid backfill complexity.

-- No-op SELECT so the migrations runner records this file as applied
-- without altering schema (the CREATE TABLE above is idempotent).
SELECT 'WO-LORI-STORY-FIRST-PHASE-1-01 interview_threads schema landed.' AS note;
