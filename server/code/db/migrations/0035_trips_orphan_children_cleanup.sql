------------------------------------------------------------
-- 0035_trips_orphan_children_cleanup.sql
-- Bucket C.1 (2026-07-23, rev 2 companion migration)
--
-- Companion / safety-net for 0034_trips_person_id_fk.sql.
--
-- Background: the first cut of 0034 (banked before this fix) did
-- its orphan-trip DELETE with foreign_keys enforcement OFF, which
-- SKIPS the declared ON DELETE CASCADE actions on every trip
-- child table. Any DB that applied that buggy rev has trip-child
-- rows (regions, stops, days, photo_links, notes, sources,
-- themes, bio_suggestions, story_links, public_context,
-- photo_context) still pointing at trip ids that no longer exist
-- in trips.
--
-- 0034 rev 2 (in this same commit) fixes the ordering so future
-- clean installs never enter that stranded-child state. This
-- migration cleans up any DB that DID enter it, and is a no-op
-- on every DB that got the correct rev of 0034 first.
--
-- Behavior:
--   * Runs with foreign_keys enforcement ON so the DELETEs
--     themselves cascade correctly for any inter-child references
--     (e.g. trip_stops.trip_region_id → trip_regions(id) ON DELETE
--     CASCADE will also fire, though those child rows are already
--     targeted by a later DELETE in this file).
--   * Each DELETE is a WHERE trip_id NOT IN (SELECT id FROM trips)
--     — idempotent, safe to re-run, no-op on a clean DB.
--   * Order: parents-first is not required (each DELETE stands
--     alone), but we walk table-by-table for readability.
--
-- Every child table listed here declares
--   trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE
-- in its CREATE TABLE. Enumerated from a grep of the migrations
-- directory (0015, 0018, 0019, 0020, 0026, 0027, 0030, 0031).
------------------------------------------------------------

PRAGMA foreign_keys = ON;

BEGIN;

-- Parents-of-parents first (trip_regions has trip_stops as child).
DELETE FROM trip_regions
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_stops
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_photo_links
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_location_notes
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_sources
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_themes
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_bio_suggestions
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_story_links
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_days
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_public_context
WHERE trip_id NOT IN (SELECT id FROM trips);

DELETE FROM trip_photo_context
WHERE trip_id NOT IN (SELECT id FROM trips);

COMMIT;

-- Diagnostic. Returns zero rows on a healthy DB. Any surviving
-- violation here means either (a) a new trip-child table landed
-- after 0035 was written and needs to be added, or (b) a non-
-- trip FK violation exists elsewhere in the DB.
PRAGMA foreign_key_check;
