-- 0025 (WO-TRAVEL-DOC-LORI-MODAL-02): dedicated modal provenance columns
-- required by the Mark Twain acceptance gate. source_ref keeps the legacy
-- combined form; these are first-class for queries/joins.
ALTER TABLE trip_location_notes ADD COLUMN source_turn_ref TEXT;
ALTER TABLE trip_location_notes ADD COLUMN photo_link_id TEXT;
