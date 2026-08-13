------------------------------------------------------------
-- 0043_trip_photo_day_placements.sql
-- WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 -- 2026-08-12
--
-- WHAT THIS ADDS
-- --------------
-- One table, trip_photo_day_placements, plus two indexes, plus a
-- backfill of one placement row per existing non-null
-- trip_photo_links.trip_day_id. Nothing is dropped. Nothing is
-- nulled. trip_photo_links keeps its trip_day_id column and every
-- other column exactly as it is.
--
-- WHY IT IS NEEDED
-- ----------------
-- trip_photo_links carries TWO relationships in one row: that a
-- photograph belongs to a trip (correctly unique on trip_id,
-- photo_id) and that it sits on one day (a single nullable
-- trip_day_id, migration 0028). Conflating them is what makes a
-- second day impossible -- the UI can only offer "Move to this day",
-- because setting a day overwrites the previous one.
--
-- The operator's actual need is the album shape every mature photo
-- library uses: one stored asset, one membership, many placements.
-- A day already holds many photographs; what was missing was one
-- photograph on several days. Separating placement into its own
-- table is the only way to express that -- Travel Document Doctrine
-- 1.12 said so when it declined the feature, calling it "a schema
-- change disguised as a button". This is that schema change, made
-- deliberately, and 1.12 is superseded by dated ruling in Phase 4.
--
-- THIS MIGRATION CHANGES NO BEHAVIOUR
-- -----------------------------------
-- It is purely additive. After it runs, the placement table mirrors
-- the scalar column exactly, and every reader in the tree still
-- reads the scalar. Phase 1 code then teaches the single scalar
-- writer (trip_repository.photo_links_set_day) to maintain both
-- representations in one transaction, and switches the deletion-
-- safety tally to read placements. No route, no UI, no projection
-- and no export is touched until Phase 2.
--
-- WHY ord AND placement_method ARE NOT COSMETIC
-- ---------------------------------------------
-- A day can hold many placements, so their order is the operator's
-- to decide and has to be storable; the (trip_day_id, ord, id) index
-- makes reading a day's placements in that order a single indexed
-- scan. placement_method records HOW a placement came to exist.
-- Backfilled rows are stamped 'backfill' rather than 'operator'
-- because no operator placed them here -- they are the migration's
-- reading of a column that could only hold one day. That distinction
-- is worth keeping: it is the difference between what a human chose
-- and what a schema change inferred.
--
-- THE UNIQUE PAIR IS THE POINT
-- ----------------------------
-- UNIQUE(photo_link_id, trip_day_id) blocks the nonsense case -- the
-- same photograph twice on one day -- while permitting it on any
-- number of different days. It also makes concurrent duplicate adds
-- a constraint violation the repository can name, rather than a race
-- that silently doubles a row.
--
-- FOREIGN KEYS AND WHAT SQLITE CANNOT SAY
-- ---------------------------------------
-- Both parents cascade: losing a trip photo link or a day removes
-- its placements, which is correct -- a placement is meaningless
-- without both ends. What SQLite CANNOT express with two independent
-- foreign keys is that the day and the link must belong to the SAME
-- trip. Nothing here prevents a placement whose day sits in trip A
-- and whose link sits in trip B. That rule is enforced in the
-- repository, inside the write transaction, and is tested there.
-- This comment exists so the next reader does not mistake the two
-- FOREIGN KEY lines for a guarantee they do not give.
--
-- METHOD
-- ------
-- CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS + an
-- INSERT ... SELECT guarded by NOT EXISTS. The runner records applied
-- filenames in schema_migrations and skips them afterwards, but the
-- guards mean a second execution of this file would still be a
-- no-op rather than a duplicate-key failure. No table rebuild, so
-- the foreign_keys toggle that 0034/0040 needed does not apply.
--
-- id format matches the rest of the tree: lower(hex(randomblob(16)))
-- produces the same 32-hex-character shape as Python's uuid4().hex.
-- Timestamps use the repository's own format (%Y-%m-%dT%H:%M:%SZ) so
-- backfilled rows sort alongside rows written by _now().
------------------------------------------------------------

BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS trip_photo_day_placements (
    id TEXT PRIMARY KEY,
    photo_link_id TEXT NOT NULL
        REFERENCES trip_photo_links(id) ON DELETE CASCADE,
    trip_day_id TEXT NOT NULL
        REFERENCES trip_days(id) ON DELETE CASCADE,
    placement_note TEXT,
    ord INTEGER NOT NULL DEFAULT 0,
    placement_method TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(photo_link_id, trip_day_id)
);

CREATE INDEX IF NOT EXISTS idx_trip_photo_day_placements_day_ord
    ON trip_photo_day_placements(trip_day_id, ord, id);

CREATE INDEX IF NOT EXISTS idx_trip_photo_day_placements_link
    ON trip_photo_day_placements(photo_link_id);

-- Backfill: exactly one placement per non-null legacy scalar.
--
-- The NOT EXISTS guard makes this idempotent against the UNIQUE pair,
-- so re-running the file cannot duplicate a placement.
--
-- The join to trip_days is deliberate and is NOT merely defensive:
-- trip_photo_links.trip_day_id is declared ON DELETE SET NULL, so a
-- dangling day id should not exist -- but a database that has been
-- restored, hand-edited, or written while foreign keys were off can
-- carry one. Backfilling it would create a placement pointing at a
-- day that is not there, and the FK on the new table would reject
-- the row and fail the whole migration. Selecting through trip_days
-- means such a row is skipped rather than fatal, and the Phase 1
-- migration test asserts the resulting count so a skip is visible
-- rather than silent.
--
-- d.trip_id = l.trip_id is the cross-trip rule SQLite cannot declare.
-- A link and day from different trips is corruption; it is excluded
-- here rather than propagated into the new table.
INSERT INTO trip_photo_day_placements
    (id, photo_link_id, trip_day_id, placement_note, ord,
     placement_method, created_at, updated_at)
SELECT
    lower(hex(randomblob(16))),
    l.id,
    l.trip_day_id,
    NULL,
    COALESCE(l.ord, 0),
    'backfill',
    COALESCE(l.created_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    COALESCE(l.updated_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
  FROM trip_photo_links l
  JOIN trip_days d
    ON d.id = l.trip_day_id
   AND d.trip_id = l.trip_id
 WHERE l.trip_day_id IS NOT NULL
   AND NOT EXISTS (
        SELECT 1 FROM trip_photo_day_placements p
         WHERE p.photo_link_id = l.id
           AND p.trip_day_id = l.trip_day_id
   );

COMMIT;

PRAGMA foreign_key_check;
