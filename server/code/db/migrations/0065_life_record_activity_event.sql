-- migration: foreign_keys=off
--
-- 0065 — Life Record: admit the `activity` event type (C-4D, 2026-09-25).
--
-- C-4C mapped `activity` → event.activity.period at the catalog / model level
-- (life_record/store.py EVENT_DATE_CONCEPT). This makes `activity` a valid
-- persisted lr_events.type. Nothing else about the table changes: same columns,
-- same order, same defaults, same constraints, same index. No UI (C-4G owns the
-- activity editor).
--
-- SQLite cannot alter a CHECK constraint, so the table is rebuilt. lr_events is
-- referenced by lr_event_participants(event_id), so this file is RUNNER-MANAGED
-- with the directive on its first line: the runner switches foreign keys off
-- OUTSIDE its transaction, runs this file inside ONE transaction together with
-- its schema_migrations row, refuses (rolling everything back) if any new
-- foreign-key violation appears, and restores foreign keys afterwards
-- (db/migrations_runner.py; tests/test_migrations_runner.py). Hence no BEGIN,
-- COMMIT or PRAGMA here.
--
-- IMMUTABLE once any persistent database has applied it (CLAUDE.md, 2026-09-24).
-- A later correction is a NEW migration number.

-- A table left by an interrupted DEVELOPMENT run cannot survive a failed run of
-- this file (the runner rolls the whole file back), but clearing it keeps the
-- rebuild idempotent against a hand-run copy.
DROP TABLE IF EXISTS lr_events_c4d_new;

CREATE TABLE lr_events_c4d_new (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    type                TEXT NOT NULL CHECK (type IN
                            ('birth', 'death', 'union', 'separation', 'move',
                             'education', 'work', 'service', 'activity', 'arrival',
                             'loss', 'milestone', 'other')),
    place_id            TEXT REFERENCES lr_places(id),
    attributes_json     TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

INSERT INTO lr_events_c4d_new (id, narrator_id, type, place_id, attributes_json, created_at, updated_at)
    SELECT id, narrator_id, type, place_id, attributes_json, created_at, updated_at FROM lr_events;

DROP TABLE lr_events;
ALTER TABLE lr_events_c4d_new RENAME TO lr_events;

CREATE INDEX IF NOT EXISTS idx_lr_events_narrator ON lr_events(narrator_id);
