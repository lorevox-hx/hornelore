-- 0024_trip_location_notes_source_surface.sql
-- WO-TRAVEL-DOC-LORI-MODAL-01 (2026-07-09). Which Lori surface captured
-- a candidate note: NULL/legacy = narrator shelf; 'travel_doc_modal' =
-- the operator Travel Doc modal. Provenance only — flags stay 0.
ALTER TABLE trip_location_notes ADD COLUMN source_surface TEXT;
