------------------------------------------------------------
-- 0042_trip_days_include_in_memoir.sql
-- WO-TRAVEL-DOC-CLOSEOUT-01 -- day-timeline lane -- 2026-08-06
--
-- WHAT THIS ADDS
-- --------------
-- One column: trip_days.include_in_memoir INTEGER NOT NULL DEFAULT 0.
-- Nothing else about the table changes. No rebuild, no index change,
-- no row rewritten.
--
-- WHY IT IS NEEDED, WITH THE EVIDENCE
-- -----------------------------------
-- The travel document exported on 2026-08-06 (Bismarck Trip,
-- 9538cd88) came out with Part I -- "The Journey in Order" -- empty,
-- while the day cards held "Santa Fe to Bismarck", "Downtown
-- Bismarck" and "Radisson Hotel on Main Street". A transitive read of
-- trip_memoir_preview()'s call graph showed why: it reaches trips,
-- trip_regions, trip_stops, trip_themes, trip_location_notes,
-- trip_sources, trip_photo_links and photos -- and NEVER trip_days.
-- Part I was not empty because there was nothing to say. It was
-- empty because it was reading the wrong table.
--
-- The reason that could not simply be fixed by teaching the exporter
-- to read trip_days is this column's absence. Every other lane into
-- the document is approval-gated on purpose: a story note needs
-- include_in_memoir, a source needs include_in_memoir, a photo link
-- needs include_in_memoir. trip_days had no such column -- not set
-- to zero, ABSENT -- so "unapproved" was never a reachable state for
-- day writing. There was no gate because there was no reader.
--
-- Wiring the reader up without a gate would have meant that typing a
-- reminder into a day card silently published it to a family
-- document. Chris ruled for the gate: one approval for the whole day
-- ("Include this day in the travel document"), not one per field.
--
-- DEFAULT 0 IS THE LOAD-BEARING PART
-- ----------------------------------
-- Every existing day row -- including the six on the Bismarck trip
-- and every day of every other trip -- becomes explicitly NOT
-- included. Nothing that has ever been typed into a day card appears
-- in a document because of this migration. A day enters the document
-- only after a human ticks it, afterwards. New days created by
-- trip_days_generate / trip_days_reconcile inherit the same default
-- and are likewise out until ticked.
--
-- WHAT THIS DOES NOT APPROVE
-- --------------------------
-- Ticking a day approves the day card's OWN operator-authored text:
-- title, main_location, lodging_base, morning/afternoon/evening
-- notes, places_visited_json, meals_json. It does NOT approve
-- anything merely attached to that day. Notes and sources keep their
-- own include_in_memoir. Photo links keep theirs. Lori conversations
-- (trip_turn_links) are not approvable at all from here and never
-- enter the document -- they have to become an approved story note
-- first. That boundary is enforced in trip_repository.day_projection,
-- which reads the day row and the already-approval-filtered note,
-- source and photo lanes, and deliberately does NOT call
-- trip_day_timeline_items(): that function is the OPERATOR view and
-- merges unapproved captions, machine descriptions and raw
-- conversation turns.
--
-- METHOD
-- ------
-- Plain ALTER TABLE ADD COLUMN. SQLite supports adding a NOT NULL
-- column when a non-null DEFAULT is supplied, and existing rows take
-- the default, which is exactly the semantics wanted here. No table
-- rebuild is needed because no constraint is being altered, so the
-- foreign_keys toggle that 0034/0040 required does not apply.
------------------------------------------------------------

BEGIN IMMEDIATE;

ALTER TABLE trip_days
    ADD COLUMN include_in_memoir INTEGER NOT NULL DEFAULT 0;

COMMIT;

PRAGMA foreign_key_check;
