-- WO-TRAVEL-DOC-SOURCES-01 — trip_sources: non-photo source documents
-- (PDFs, tickets, hotel confirmations, itineraries, pasted notes, links)
-- attached to a trip/region/stop. Deliberately SEPARATE from the photo
-- pipeline (trip_photo_links). include_in_memoir defaults OFF.
BEGIN;

CREATE TABLE IF NOT EXISTS trip_sources (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_region_id TEXT REFERENCES trip_regions(id) ON DELETE SET NULL,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    source_type TEXT NOT NULL DEFAULT 'other'
        CHECK (source_type IN ('itinerary', 'receipt', 'hotel', 'ticket',
                               'note', 'map', 'link', 'other')),
    title TEXT,
    filename TEXT,
    mime_type TEXT,
    storage_path TEXT,
    pasted_text TEXT,
    link_url TEXT,
    source_date TEXT,
    summary TEXT,
    include_in_memoir INTEGER NOT NULL DEFAULT 0,
    ord INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trip_sources_trip ON trip_sources(trip_id, ord);
CREATE INDEX IF NOT EXISTS idx_trip_sources_region ON trip_sources(trip_region_id, ord);
CREATE INDEX IF NOT EXISTS idx_trip_sources_stop ON trip_sources(trip_stop_id, ord);

COMMIT;
