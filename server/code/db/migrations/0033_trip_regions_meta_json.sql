------------------------------------------------------------
-- 0033_trip_regions_meta_json.sql
-- WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight review-follow-up round 2
-- (2026-07-11)
--
-- Adds `meta_json` to trip_regions so trip_narration_capture's
-- `_stamp_region_meta()` (fixed in the same commit to do
-- read-merge-write instead of wholesale overwrite) can actually
-- persist. Before this migration + code fix, `_stamp_region_meta`
-- targeted a phantom column; every call silently no-op'd inside the
-- outer try/except, and any future co-writer to trip_regions.meta_json
-- would still lose data the moment the column landed alongside a
-- wholesale UPDATE.
--
-- trip_stops.meta_json already exists (0015_trip_tables.sql:67).
-- Mirroring the same shape here: TEXT NOT NULL DEFAULT '{}'.
------------------------------------------------------------

BEGIN;

ALTER TABLE trip_regions
    ADD COLUMN meta_json TEXT NOT NULL DEFAULT '{}';

COMMIT;
