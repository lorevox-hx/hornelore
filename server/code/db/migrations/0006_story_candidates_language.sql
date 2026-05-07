-- WO-ML-03B (Phase 3 of the multilingual project, 2026-05-07) — language
-- column on story_candidates. Each preserved narrator turn now records
-- the ISO-639-1 language code detected by the STT engine (WhisperSTT
-- bubbles `info.language` from faster-whisper into each chunk's
-- response per Phase 1A; FE TranscriptGuard threads the value through
-- the chat WS payload to chat_ws.py to story_preservation.preserve_turn).
--
-- Default null preserves byte-stable behavior for existing rows + any
-- callers that omit the kwarg. Web Speech (the legacy STT engine) does
-- not emit language, so legacy-path rows continue to land with
-- language=null. Whisper-engine rows carry "en", "es", "fr", etc.
--
-- Idempotent under SQLite: ALTER TABLE ADD COLUMN is safe to re-run
-- only when the column doesn't exist. The migration runner tracks
-- applied filenames in schema_migrations, so this file executes
-- exactly once per fresh DB.

BEGIN;

-- ISO-639-1 language code detected by the STT engine, OR null when
-- the engine is Web Speech / typed input / unknown. NOT validated at
-- write time — chat_ws.py normalizes upstream (lowercase, trim).
ALTER TABLE story_candidates ADD COLUMN language TEXT;

-- Optional: language-detection probability from the STT engine.
-- Whisper-large-v3 reports language_probability in (0.0, 1.0]; null on
-- non-Whisper paths. Used by Phase 4 safety / extraction code that
-- gates on confident-language detections.
ALTER TABLE story_candidates ADD COLUMN language_probability REAL;

-- Index for "find Spanish narrator stories" / "list rows in language X"
-- queries that the operator review surface and Phase 4 memoir export
-- will issue. Lightweight: most rows will have a small set of language
-- values, so this index stays compact.
CREATE INDEX IF NOT EXISTS idx_story_candidates_language
    ON story_candidates(language);

COMMIT;
