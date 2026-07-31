------------------------------------------------------------
-- 0040_trip_turn_links_shelf_placement_source.sql
-- WO-TRIP-NARRATOR-BRIDGE-01 Priority 2 -- 2026-07-31
--
-- WHAT THIS ADDS
-- --------------
-- One word to one CHECK constraint: 'travels_shelf_trip' becomes a
-- legal value of trip_turn_links.placement_source. Nothing else about
-- the table changes. Every column, type, default, foreign key, index
-- and row is carried across unchanged, and 0039 is left exactly as it
-- was written.
--
-- WHY IT IS NEEDED, WITH THE EVIDENCE
-- -----------------------------------
-- 0039 wrote the placement vocabulary into the schema:
--
--     CHECK (placement_source IN ('active_trip_day',
--            'operator_selected', 'timestamp_suggested',
--            'later_reconciled'))
--
-- Priority 2 places a turn on a COMPLETED trip the narrator has open
-- on the Travels shelf. That is a fifth way a placement can come to
-- exist, and it has to be nameable, because the four existing words
-- all assert something untrue about it: 'active_trip_day' would say
-- the database knew he was living in that trip, 'operator_selected'
-- would say a human chose the day, 'timestamp_suggested' would say a
-- clock did, and 'later_reconciled' would say somebody went back and
-- sorted it out. A shelf placement is none of those. It is: he had the
-- trip open and he was telling it.
--
-- Adding the word to the Python whitelist alone was not enough, and
-- the way it failed is the reason this file exists rather than a
-- comment. trip_turn_link_claim() inserts and treats sqlite3
-- IntegrityError as the idempotency signal -- one persisted turn, one
-- placement, decided by the UNIQUE index on assistant_turn_row_id. A
-- CHECK violation is also an IntegrityError. So the rejected INSERT
-- came back as outcome='duplicate': the API told the caller the turn
-- was ALREADY PLACED when in fact no row had been written and none
-- ever would be. PlacementOutcome.linked returns True for 'duplicate'
-- -- it means "a link row now exists for this turn" -- so the lie
-- would have propagated into the completed-turn log as a success while
-- the conversation stayed attached to nothing. That is the exact
-- failure this whole work order is trying to end, reproduced one layer
-- lower down. Six tests in tests/test_trip_placement.py caught it.
--
-- The claim function is being taught to tell the two apart in the same
-- change, by re-reading for the row instead of trusting the exception
-- class. This migration removes the reason the constraint fires; that
-- fix removes the reason a future one would be silent.
--
-- WHAT IS DELIBERATELY NOT DONE HERE
-- ----------------------------------
-- No existing row is rewritten. Nothing already placed as
-- 'active_trip_day' is reinterpreted as a shelf placement in
-- hindsight; this file's only DML is the straight copy. No column is
-- added, dropped, widened or renamed. placement_status is untouched --
-- the shelf path lands on the 'needs_day' value 0039 already defined
-- for exactly this situation, and never invents a day.
--
-- METHOD -- the SQLite 12-step rebuild, same shape as 0034
-- --------------------------------------------------------
-- SQLite cannot alter a CHECK constraint in place, so the table is
-- rebuilt. PRAGMA foreign_keys is toggled OUTSIDE any transaction
-- because it is documented as a no-op inside one. The toggle is safe
-- here for a reason worth stating: nothing in the schema references
-- trip_turn_links, so the DROP has no children to orphan, and the
-- table's own two outbound references (trips, trip_days) are carried
-- over row-for-row from data that already satisfied them.
------------------------------------------------------------

PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

CREATE TABLE trip_turn_links_new (
    id                     TEXT PRIMARY KEY,

    trip_id                TEXT NOT NULL
                               REFERENCES trips(id) ON DELETE CASCADE,

    trip_day_id            TEXT
                               REFERENCES trip_days(id) ON DELETE SET NULL,

    conv_id                TEXT NOT NULL DEFAULT '',

    user_turn_row_id       INTEGER,
    assistant_turn_row_id  INTEGER NOT NULL,

    captured_at            TEXT NOT NULL DEFAULT '',

    -- How the placement came to exist. 'travels_shelf_trip' is the
    -- addition: the narrator had a finished trip open on the Travels
    -- shelf and told a story into it. It never carries a day.
    placement_source       TEXT NOT NULL DEFAULT 'active_trip_day'
        CHECK (placement_source IN (
            'active_trip_day', 'travels_shelf_trip', 'operator_selected',
            'timestamp_suggested', 'later_reconciled'
        )),

    placement_status       TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (placement_status IN (
            'suggested', 'confirmed', 'needs_day', 'rejected'
        )),

    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

INSERT INTO trip_turn_links_new (
    id, trip_id, trip_day_id, conv_id, user_turn_row_id,
    assistant_turn_row_id, captured_at, placement_source,
    placement_status, created_at, updated_at)
SELECT
    id, trip_id, trip_day_id, conv_id, user_turn_row_id,
    assistant_turn_row_id, captured_at, placement_source,
    placement_status, created_at, updated_at
FROM trip_turn_links;

DROP TABLE trip_turn_links;
ALTER TABLE trip_turn_links_new RENAME TO trip_turn_links;

-- The idempotency mechanism itself, restored by name. A rebuild drops
-- the old indexes with the old table; if this one did not come back,
-- the same assistant turn could be placed twice and nothing would say
-- so.
CREATE UNIQUE INDEX IF NOT EXISTS ux_trip_turn_links_assistant_row
    ON trip_turn_links(assistant_turn_row_id);

CREATE INDEX IF NOT EXISTS idx_trip_turn_links_trip
    ON trip_turn_links(trip_id);

CREATE INDEX IF NOT EXISTS idx_trip_turn_links_day
    ON trip_turn_links(trip_day_id);

CREATE INDEX IF NOT EXISTS idx_trip_turn_links_conv
    ON trip_turn_links(conv_id);

COMMIT;

PRAGMA foreign_keys = ON;

PRAGMA foreign_key_check;
