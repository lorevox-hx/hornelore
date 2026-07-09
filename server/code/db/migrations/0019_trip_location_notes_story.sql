-- WO-TRAVEL-DOC-STORY-LAYER-01 — trip_location_notes becomes the story
-- backbone. The 0015 table was a dead scaffold (no accessors, no reads,
-- guaranteed empty), shaped as question/answer. Recreate it as a real
-- multi-note story layer: many notes per place, provenance, and the two
-- promotion flags default OFF (operator must explicitly promote a note
-- into the memoir or the interview context — nothing from Lori/drafts/
-- sources enters either automatically).
BEGIN;

DROP TABLE IF EXISTS trip_location_notes;

CREATE TABLE trip_location_notes (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    -- Scope: both null = trip-level; region set = region-level;
    -- stop set = stop-level. (A stop note may also carry its region id.)
    trip_region_id TEXT REFERENCES trip_regions(id) ON DELETE SET NULL,
    trip_stop_id TEXT REFERENCES trip_stops(id) ON DELETE SET NULL,
    note_title TEXT,
    note_text TEXT,
    source_type TEXT NOT NULL DEFAULT 'operator'
        CHECK (source_type IN ('operator', 'lori', 'external', 'draft')),
    source_ref TEXT,            -- optional link to a source/doc/photo/turn
    include_in_memoir INTEGER NOT NULL DEFAULT 0,
    include_in_interview_context INTEGER NOT NULL DEFAULT 0,
    target_language TEXT NOT NULL DEFAULT 'en',
    ord INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trip_location_notes_trip
    ON trip_location_notes(trip_id, ord);
CREATE INDEX IF NOT EXISTS idx_trip_location_notes_region
    ON trip_location_notes(trip_region_id, ord);
CREATE INDEX IF NOT EXISTS idx_trip_location_notes_stop
    ON trip_location_notes(trip_stop_id, ord);

COMMIT;
