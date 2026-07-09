-- 0021_trip_photo_links_region_upload.sql
-- Review 2026-07-08: region-level photo drops need their own
-- assignment_method 'region_upload' so the audit trail distinguishes a
-- deliberate region drop from a generic trip_upload. Still
-- cluster-placeable to a stop later. SQLite can't alter a CHECK, so
-- rebuild the table with the extended enum (same copy-forward pattern as
-- 0018). Preserves all existing rows.

CREATE TABLE trip_photo_links_new (
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
            'manual', 'exif_time', 'exif_gps', 'album', 'csv', 'operator',
            'trip_upload', 'region_upload'
        )),
    cluster_confidence REAL,
    caption TEXT,
    narrator_caption TEXT,
    include_in_memoir INTEGER NOT NULL DEFAULT 1,
    thematic_tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO trip_photo_links_new SELECT * FROM trip_photo_links;
DROP TABLE trip_photo_links;
ALTER TABLE trip_photo_links_new RENAME TO trip_photo_links;

CREATE INDEX IF NOT EXISTS idx_trip_photo_links_trip_id ON trip_photo_links(trip_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_stop_id ON trip_photo_links(trip_stop_id);
CREATE INDEX IF NOT EXISTS idx_trip_photo_links_confidence ON trip_photo_links(trip_id, cluster_confidence);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trip_photo_links_trip_photo ON trip_photo_links(trip_id, photo_id);
