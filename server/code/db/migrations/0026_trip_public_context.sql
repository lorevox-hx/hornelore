------------------------------------------------------------
-- 0026_trip_public_context.sql
-- WO-TRAVEL-DOC-EVIDENCE-RICH-TRAVELOGUE-01 (2026-07-09)
--
-- Public/web-derived context for the OPERATOR Travel Doc workspace
-- (holidays, local events, museum background, food context, reverse-
-- geocoded broad place names). Doctrine (locked 2026-07-10): Travel
-- Doc mode is evidence-rich and MAY use local web/public context; the
-- boundary is that private memoir archives never leave the local
-- stack, and public context is labeled as public/draft until the
-- operator confirms it — never presented as personal memory.
--
-- approved_for_lori / include_in_memoir DEFAULT 0 — nothing is
-- approved by silence. Raw GPS is never stored here; reverse_geocode
-- rows carry only the resolved broad place label.
------------------------------------------------------------

CREATE TABLE IF NOT EXISTS trip_public_context (
    id TEXT PRIMARY KEY,
    trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    trip_region_id TEXT,
    trip_stop_id TEXT,
    photo_link_id TEXT,
    query TEXT,
    source_type TEXT CHECK (source_type IN (
        'public_web_context', 'reverse_geocode', 'calendar_context',
        'food_context', 'place_context')),
    source_url TEXT,
    result_summary TEXT NOT NULL,
    confidence TEXT DEFAULT 'draft',
    notes TEXT,
    approved_for_lori INTEGER NOT NULL DEFAULT 0,
    include_in_memoir INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trip_public_context_trip
    ON trip_public_context(trip_id);
