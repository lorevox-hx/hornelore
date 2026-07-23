------------------------------------------------------------
-- 0034_trips_person_id_fk.sql
-- Bucket C.1 (2026-07-23, rev 3 — cascade-safe two-phase structure)
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
-- CRITICAL ORDERING (rev 3, 2026-07-23):
-- The orphan DELETE must run while foreign_keys enforcement is ON,
-- otherwise the CASCADE actions on trip_regions / trip_stops /
-- trip_photo_links / trip_days / trip_location_notes / trip_sources
-- / trip_themes / trip_bio_suggestions / trip_story_links /
-- trip_public_context / trip_photo_context DO NOT FIRE, and the
-- orphan trip's children are left stranded pointing at trip ids
-- that no longer exist. The rev 1 version of this migration did the
-- DELETE with FKs OFF (assuming — incorrectly — that CASCADE was
-- controlled by declaration not enforcement); rev 3 splits into
-- two BEGIN IMMEDIATE transactions so the DELETE runs with
-- enforcement on and the rebuild runs with enforcement off, with
-- the PRAGMA toggle happening outside any transaction (SQLite
-- documents PRAGMA foreign_keys as a no-op inside BEGIN).
--
-- SQLite does not support ALTER TABLE ... ADD FOREIGN KEY, so
-- this uses the standard table-rebuild pattern per SQLite docs
-- ("Making Other Kinds Of Table Schema Changes"), split into two
-- phases:
--
--   Phase 1 — cascade-safe orphan removal:
--     0. PRAGMA foreign_keys = ON      (defensive — the runner's
--                                       connection already sets ON
--                                       per api/db.py _connect)
--     1. BEGIN IMMEDIATE               (writer position from open;
--                                       matches the trip_days_generate
--                                       pattern; ends the possibility
--                                       of the deferred-to-writer
--                                       upgrade race)
--     2. DELETE FROM trips WHERE       (NOT EXISTS is more defensive
--        NOT EXISTS(SELECT 1 FROM       than NOT IN — the latter can
--        people WHERE people.id =       fail to filter correctly if a
--        trips.person_id)               NULL sneaks into the subquery;
--                                       people.id is PK/NOT NULL so
--                                       NOT IN is safe here, but the
--                                       stricter shape is future-proof)
--                                       Cascade fires on every child
--                                       table with ON DELETE CASCADE.
--     3. COMMIT
--
--   Phase 2 — safe table rebuild:
--     4. PRAGMA foreign_keys = OFF     (SAFE now: no orphans remain,
--                                       and the DROP+RENAME swap
--                                       below needs enforcement off
--                                       to avoid tripping FK checks
--                                       during the transient state)
--     5. BEGIN IMMEDIATE
--     6. CREATE TABLE trips_new        (identical shape PLUS the
--                                       REFERENCES people(id) ON
--                                       DELETE CASCADE clause)
--     7. INSERT INTO trips_new SELECT  (copy the survivors)
--     8. DROP TABLE trips
--     9. ALTER TABLE trips_new RENAME  (atomic swap)
--    10. CREATE INDEX idx_trips_...    (was dropped with the old
--                                       table; recreate under the
--                                       same name)
--    11. COMMIT
--    12. PRAGMA foreign_keys = ON      (re-arm enforcement for any
--                                       subsequent statement on this
--                                       connection)
--    13. PRAGMA foreign_key_check      (diagnostic: should return
--                                       zero rows)
--
-- Foreign key enforcement is a per-CONNECTION setting. The
-- application's _connect() already sets PRAGMA foreign_keys=ON
-- for every request connection. This migration's PRAGMA statements
-- only affect the migration-runner's own connection for the
-- duration of this script.
--
-- Note on PRAGMA + transactions: PRAGMA foreign_keys is a no-op
-- inside a transaction ("foreign key constraint enforcement may
-- only be enabled or disabled when there is no pending BEGIN or
-- SAVEPOINT"). Every PRAGMA below is OUTSIDE BEGIN/COMMIT.
--
-- Orphan visibility: db.py's init_db logs the orphan count BEFORE
-- calling run_pending_migrations when 0034 is pending, so the
-- operator sees "[migrations] pre-0034: N orphan trip(s) found"
-- in api.log at the boot that applies this migration.
--
-- Companion migration 0035_trips_orphan_children_cleanup.sql
-- handles the case where the rev 1 (buggy) version ran with
-- FKs OFF and left children stranded — 0035 is idempotent and
-- a no-op on any DB that got the correct rev 3 first.
------------------------------------------------------------

-- Phase 1: delete orphan trips while cascades are active.
PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

DELETE FROM trips
WHERE NOT EXISTS (
    SELECT 1
    FROM people
    WHERE people.id = trips.person_id
);

COMMIT;

-- Phase 2: safe to disable enforcement now for the parent-table
-- rebuild. No orphans remain to trip the new FK constraint on
-- INSERT INTO trips_new.
PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

CREATE TABLE trips_new (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL
        REFERENCES people(id) ON DELETE CASCADE,
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

INSERT INTO trips_new (
    id, person_id, title, start_date, end_date, summary,
    status, source_document, created_at, updated_at, meta_json
)
SELECT
    id, person_id, title, start_date, end_date, summary,
    status, source_document, created_at, updated_at, meta_json
FROM trips;

DROP TABLE trips;
ALTER TABLE trips_new RENAME TO trips;

CREATE INDEX IF NOT EXISTS idx_trips_person_id ON trips(person_id);

COMMIT;

-- Re-arm FK enforcement for any subsequent statement.
PRAGMA foreign_keys = ON;

-- Diagnostic. Returns zero rows on a healthy DB. If 0035 runs
-- immediately after this, it'll also sweep any leftover children
-- from the rev 1 buggy state.
PRAGMA foreign_key_check;
