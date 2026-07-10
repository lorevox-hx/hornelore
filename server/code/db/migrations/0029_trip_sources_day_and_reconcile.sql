------------------------------------------------------------
-- 0029_trip_sources_day_and_reconcile.sql
-- WO-TRAVEL-DOC-UI-LAB-03 (2026-07-10)
--
-- Closes the two deferred UI Lab gaps:
--   * trip_sources.trip_day_id — true day-scoped sources. A source
--     attached to a day counts on THAT day first; un-day-linked
--     sources keep the stop/region-scope fallback. ON DELETE SET NULL:
--     removing a day card never deletes the source row.
--   * trip_days.reconcile_status — lightweight date-range reconcile
--     marker. 'active' (default) or 'out_of_range_acknowledged' when
--     the operator reviews a day card that sits outside the current
--     trip start/end dates. Out-of-range day cards are NEVER deleted
--     (they are kept to protect operator notes); this column only
--     records that the operator has seen them.
--
-- Operator-side surface only. Nothing here reaches the narrator.
------------------------------------------------------------

ALTER TABLE trip_sources
    ADD COLUMN trip_day_id TEXT REFERENCES trip_days(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_trip_sources_day
    ON trip_sources(trip_day_id);

ALTER TABLE trip_days
    ADD COLUMN reconcile_status TEXT NOT NULL DEFAULT 'active';
