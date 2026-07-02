------------------------------------------------------------
-- 0015_trip_tables.sql
-- WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 1 (2026-07-02)
-- Hierarchical trip schema per WO-TRIP-MEMOIR-01 (LOCKED):
--   trips -> trip_regions -> trip_stops (nested) -> trip_photo_links
--   + trip_themes / trip_location_notes / trip_bio_suggestions
--   + trip_story_links
-- Deviation from parent spec: trip_photo_links.photo_id references
-- photos(id) (the live photo authority table with EXIF datetime+GPS),
-- not media(id).
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trips (
    id TEXT PRIMARY KEY,
    person_id TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_trips_person_id ON trips(person_id);

CREATE TABLE IF NOT EXISTS trip_regions (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    country_or_area TEXT,
    start_date TEXT,
    end_date TEXT,
    summary TEXT,
    base_address TEXT,
    theme_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_regions_trip_id ON trip_regions(trip_id, ord);

CREATE TABLE IF NOT EXISTS trip_stops (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_region_id TEXT NOT NULL REFERENCES trip_regions(id) ON DELETE CASCADE,
    parent_trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    ord INTEGER NOT NULL DEFAULT 0,
    stop_type TEXT NOT NULL DEFAULT 'sight'
        CHECK (stop_type IN (
            'base', 'day_trip', 'transit', 'lodging',
            'meal', 'disruption', 'sight', 'memory_anchor'
        )),
    date_start TEXT,
    date_end TEXT,
    location_name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    title TEXT,
    notes TEXT,
    thematic_tags_json TEXT NOT NULL DEFAULT '[]',
    timeline_event_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    meta_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_trip_stops_trip_id ON trip_stops(trip_id, ord);
CREATE INDEX IF NOT EXISTS idx_trip_stops_region_id ON trip_stops(trip_region_id, ord);
CREATE INDEX IF NOT EXISTS idx_trip_stops_parent ON trip_stops(parent_trip_stop_id);

CREATE TABLE IF NOT EXISTS trip_themes (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    description TEXT,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_themes_trip_id ON trip_themes(trip_id, ord);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_themes_trip_tag ON trip_themes(trip_id, tag);

CREATE TABLE IF NOT EXISTS trip_photo_links (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_region_id TEXT REFERENCES trip_regions(id) ON DELETE SET NULL,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    photo_id TEXT NOT NULL,
    ord INTEGER NOT NULL DEFAULT 0,
    taken_at TEXT,
    latitude REAL,
    longitude REAL,
    assignment_method TEXT NOT NULL DEFAULT 'exif_time'
        CHECK (assignment_method IN (
            'manual', 'exif_time', 'exif_gps', 'album', 'csv', 'operator'
        )),
    cluster_confidence REAL,
    caption TEXT,
    narrator_caption TEXT,
    include_in_memoir INTEGER NOT NULL DEFAULT 1,
    thematic_tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_trip_id ON trip_photo_links(trip_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_stop_id ON trip_photo_links(trip_stop_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_confidence ON trip_photo_links(trip_id, cluster_confidence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_photo_links_trip_photo ON trip_photo_links(trip_id, photo_id);

CREATE TABLE IF NOT EXISTS trip_location_notes (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_region_id TEXT REFERENCES trip_regions(id) ON DELETE SET NULL,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    location_name TEXT,
    question TEXT,
    answer TEXT,
    source_type TEXT NOT NULL DEFAULT 'operator'
        CHECK (source_type IN ('operator', 'lori', 'external')),
    include_in_interview_context INTEGER NOT NULL DEFAULT 1,
    include_in_memoir INTEGER NOT NULL DEFAULT 0,
    target_language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_location_notes_trip_id ON trip_location_notes(trip_id);

CREATE TABLE IF NOT EXISTS trip_bio_suggestions (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    person_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    suggested_value TEXT,
    source_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'suggested'
        CHECK (status IN ('suggested', 'promoted', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_bio_suggestions_trip ON trip_bio_suggestions(trip_id, status);

CREATE TABLE IF NOT EXISTS trip_story_links (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    story_candidate_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'suggested'
        CHECK (status IN ('suggested', 'confirmed', 'rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_story_links_trip ON trip_story_links(trip_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_story_links_pair ON trip_story_links(trip_id, story_candidate_id);
