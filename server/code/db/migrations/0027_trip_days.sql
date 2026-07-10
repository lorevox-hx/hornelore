------------------------------------------------------------
-- 0027_trip_days.sql
-- WO-TRAVEL-DOC-UI-LAB-01 (2026-07-10)
--
-- Day-by-day trip layer for the Trip Calendar redesign (Travel Doc
-- UI Lab). One row per calendar date inside a trip's start/end
-- window, generated idempotently from the trip dates and editable by
-- the operator. Region/stop links are best-effort conveniences —
-- the itinerary tree (trips -> trip_regions -> trip_stops) remains
-- the route authority.
--
-- Operator-side surface only. Nothing here reaches the narrator.
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trip_days (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    day_index INTEGER NOT NULL,
    date TEXT NOT NULL,
    title TEXT,
    main_location TEXT,
    lodging_base TEXT,
    trip_region_id TEXT REFERENCES trip_regions(id) ON DELETE SET NULL,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    morning_notes TEXT,
    afternoon_notes TEXT,
    evening_notes TEXT,
    places_visited_json TEXT NOT NULL DEFAULT '[]',
    meals_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trip_id, date)
);
CREATE INDEX IF NOT EXISTS idx_trip_days_trip ON trip_days(trip_id);
