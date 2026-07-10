------------------------------------------------------------
-- 0028_trip_day_links.sql
-- WO-TRAVEL-DOC-UI-LAB-02 (2026-07-10)
--
-- Day-level linking for the Trip Calendar (Travel Doc UI Lab):
--   * trip_photo_links.trip_day_id — operator attaches photos to a
--     specific day card. Day-linked photos count on THEIR day first;
--     unlinked photos keep the best-effort taken-date match.
--   * trip_location_notes.trip_day_id — day-scoped story notes,
--     including Lori day-capture notes from the day-scoped modal.
--
-- Operator-side surface only. Nothing here reaches the narrator.
------------------------------------------------------------

ALTER TABLE trip_photo_links
    ADD COLUMN trip_day_id TEXT REFERENCES trip_days(id) ON DELETE SET NULL;

ALTER TABLE trip_location_notes
    ADD COLUMN trip_day_id TEXT REFERENCES trip_days(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_trip_photo_links_day
    ON trip_photo_links(trip_day_id);
CREATE INDEX IF NOT EXISTS idx_trip_location_notes_day
    ON trip_location_notes(trip_day_id);
