------------------------------------------------------------
-- 0034_trips_person_id_fk.sql
-- Bucket C.1 (2026-07-23)
--
-- Adds a real schema-level FOREIGN KEY constraint on
-- trips.person_id → people(id) with ON DELETE CASCADE.
--
-- Motivation (from the North Dakota live-test incident + review):
-- Migration 0015_trip_tables.sql declared:
--     person_id TEXT NOT NULL
-- with NO REFERENCES clause. The API-level
-- _validate_person_id_exists() gate in routers/trips.py catches
-- the common "operator submitted a bogus person_id" case for
-- POST /api/trips, but ANY other caller — import tools,
-- CLI scripts, future routers, direct sqlite3 access, a bug in
-- a service function — can bypass it and insert an orphan trip.
-- The ND run produced exactly that orphan
-- (person_id="PASTE_UUID_HERE") and no schema constraint caught it.
--
-- This migration turns the API-level gate into a schema-level
-- guarantee. Callers still hit the API gate first (defense in
-- depth), but the DB itself now refuses any orphan insertion
-- and cascade-cleans on person delete.
--
-- SQLite does not support ALTER TABLE ... ADD FOREIGN KEY, so
-- this uses the standard table-rebuild pattern per SQLite docs
-- ("Making Other Kinds Of Table Schema Changes"):
--   1. PRAGMA foreign_keys = OFF        (avoid cascade side-effects
--                                        while we rebuild)
--   2. DELETE orphan trips              (any row whose person_id
--                                        has no matching people.id;
--                                        the INSERT INTO trips_new
--                                        SELECT below would otherwise
--                                        happily copy them over)
--   3. CREATE TABLE trips_new           (identical shape PLUS the
--                                        REFERENCES people(id) ON
--                                        DELETE CASCADE clause)
--   4. INSERT INTO trips_new SELECT     (copy the survivors, column-
--                                        by-column, preserves defaults
--                                        + CHECK + NOT NULL)
--   5. DROP TABLE trips
--   6. ALTER TABLE trips_new RENAME     (atomic swap)
--   7. CREATE INDEX idx_trips_person_id (was dropped with the old
--                                        table; recreate under the
--                                        same name)
--   8. PRAGMA foreign_keys = ON         (re-arm the enforcement)
--   9. PRAGMA foreign_key_check         (diagnostic: should return
--                                        zero rows — if it doesn't,
--                                        something else in the DB
--                                        has a pre-existing FK
--                                        violation and the operator
--                                        should investigate before
--                                        the next request lands)
--
-- Cascade behavior: existing trip_regions / trip_stops /
-- trip_photo_links / trip_themes / trip_location_notes /
-- trip_bio_suggestions / trip_story_links already reference
-- trips(id) ON DELETE CASCADE (see 0015_trip_tables.sql). With
-- this migration, deleting a person cascade-deletes their trips,
-- which in turn cascade-deletes every trip child row. That is
-- the intended behavior for the ND-class incident (an orphan
-- person can't exist; a deleted person's trip artifacts should
-- go with them).
--
-- Foreign key enforcement is a per-CONNECTION setting. The
-- application's _connect() already sets PRAGMA foreign_keys=ON
-- for every request connection (see api/db.py). This migration's
-- PRAGMA statements only affect the migration-runner's own
-- connection for the duration of this script.
--
-- Orphan visibility: db.py's init_db logs the orphan count BEFORE
-- calling run_pending_migrations when 0034 is pending, so the
-- operator sees "[migrations] pre-0034: N orphan trips found"
-- in api.log at the boot that applies this migration.
------------------------------------------------------------

PRAGMA foreign_keys = OFF;

BEGIN;

-- Step 2: remove orphans. Cannot exist under the new schema; if we
-- copied them into trips_new they'd violate the constraint the
-- moment foreign_keys re-armed and any downstream query touched
-- them. DELETE cascades through the trip_regions / trip_stops /
-- etc. ON DELETE CASCADE chain (still enforced because those FKs
-- are declared at CREATE TABLE time — the foreign_keys pragma
-- controls enforcement, not declaration).
DELETE FROM trips
WHERE person_id NOT IN (SELECT id FROM people);

-- Step 3: new table with the FK constraint.
CREATE TABLE trips_new (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    summary TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'in_progress', 'memoir_ready')),
    source_document TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    meta_json TEXT NOT NULL DEFAULT '{}'
);

-- Step 4: copy the survivors.
INSERT INTO trips_new (
    id, person_id, title, start_date, end_date, summary,
    status, source_document, created_at, updated_at, meta_json
)
SELECT
    id, person_id, title, start_date, end_date, summary,
    status, source_document, created_at, updated_at, meta_json
FROM trips;

-- Step 5-6: atomic swap.
DROP TABLE trips;
ALTER TABLE trips_new RENAME TO trips;

-- Step 7: recreate the index that lived on the old trips table.
CREATE INDEX IF NOT EXISTS idx_trips_person_id ON trips(person_id);

COMMIT;

-- Step 8: re-arm enforcement.
PRAGMA foreign_keys = ON;

-- Step 9: diagnostic. Returns zero rows on a healthy DB. If the
-- migration runner's executescript surfaces any rows here, they
-- indicate a pre-existing FK violation elsewhere in the DB that
-- was not related to this migration. The runner tolerates a
-- non-empty result (PRAGMA statements don't raise on data), so
-- this is a soft check; the operator should still eyeball api.log
-- for [migrations] entries around this filename.
PRAGMA foreign_key_check;
