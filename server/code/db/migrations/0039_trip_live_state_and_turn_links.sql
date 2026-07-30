------------------------------------------------------------
-- 0039_trip_live_state_and_turn_links.sql
-- WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 -- 2026-07-30
--
-- THE GAP THIS CLOSES
-- -------------------
-- Two subsystems were each individually working and were not joined.
-- The Lori interview runtime persists turns, writes archive events and
-- (since Gate 7 Phase 2) requests field extraction. The travel document
-- system holds trips, generated trip_days, photo links and day cards.
-- Nothing recorded WHICH TRIP AND WHICH DAY a conversation belonged to.
--
-- Before this migration the only answer to "which trip is Lori working
-- on" was ``runtime71.active_trip_id`` -- a value the browser computed
-- and sent along with each turn. That is a client-side session fact. It
-- does not survive a page reload, it does not survive a server restart,
-- and it cannot be read by anything that is not the browser that set
-- it. A timeline built on it would be a timeline that forgets.
--
-- WHAT IS ADDED, AND WHY EACH PIECE IS SHAPED THE WAY IT IS
-- ---------------------------------------------------------
-- 1. trips.live_state -- the deliberate trip lifecycle.
--
--    The existing trips.status column is NOT this and is deliberately
--    left alone. status is the AUTHORING state of the trip document
--    ('draft' -> 'in_progress' -> 'memoir_ready'): how far along the
--    write-up is. live_state is the LIVED state of the journey
--    ('planning' -> 'active' -> 'completed' -> 'archived'): where the
--    narrator physically is in relation to it. A trip can be lived and
--    finished ('completed') while its write-up has not started
--    ('draft'), and a long-finished trip can be re-opened for memoir
--    work without becoming a journey the narrator is currently on.
--    Folding both meanings into one column would make "am I travelling
--    right now" unanswerable, so they stay separate.
--
--    The work order is explicit that active must not be inferred from
--    today's date: "Do not infer active only from today's date. The
--    operator should be able to start and finish the trip
--    deliberately." A stored column is what makes that possible. A date
--    comparison would silently activate every trip whose window happens
--    to contain today, including historical trips being written up.
--
-- 2. ux_trips_one_live_active_per_person -- a PARTIAL unique index.
--
--    A narrator is on at most one trip at a time. This is enforced by
--    the database rather than by application discipline, because the
--    question the whole slice depends on -- "where should this
--    conversation go" -- must have exactly one answer. The index is
--    partial (WHERE live_state = 'active') so any number of trips may
--    sit in planning, completed or archived at once.
--
-- 3. trips.active_trip_day_id -- the selected day, stored.
--
--    The work order requires that the modal "remember the selected trip
--    and day when closed and reopened", and the acceptance run requires
--    the link to survive a restart. Selection therefore lives on the
--    trip row, not in browser memory. ON DELETE SET NULL so removing a
--    day card clears the selection rather than orphaning it.
--
-- 4. trip_turn_links -- the durable turn-to-trip/day placement record.
--
--    A LINK TABLE, NOT A SECOND CONVERSATION STORE. The work order:
--    "Do not add a second conversation store. Do not copy turn text
--    into a trip table." This table holds row ids and placement
--    metadata. It holds no narrative content of any kind, and the
--    timeline reads the turn text back out of `turns` through these
--    ids. There is exactly one conversation store and it is `turns`.
--
--    IDEMPOTENCY. UNIQUE on assistant_turn_row_id: a persisted turn is
--    placed on exactly one trip day, and re-running the completed-turn
--    hook for a turn that is already placed is a no-op decided by the
--    database, not by an in-process guard. This mirrors migration 0038:
--    the key is a committed row, never a hash of the narrator's words.
--    The same assistant row id is what Gate 7 Phase 2 already uses for
--    its extraction key ('turnrow:<turns.id>'), so a turn's extraction
--    record and its trip placement are anchored to the same fact.
--
--    trip_day_id IS NULLABLE ON PURPOSE. The work order: "A failure to
--    link the trip should not lose the conversation. It should leave an
--    observable reconciliation item." A row with a trip_id and a NULL
--    trip_day_id at placement_status='needs_day' IS that item -- the
--    conversation is known to belong to the trip, the day could not be
--    resolved, and the timeline can show it as unplaced instead of
--    dropping it on the floor.
--
--    placement_source records HOW the day was chosen, and the interface
--    is required to distinguish a suggestion from an operator's choice
--    ("Suggested day" vs "Confirmed day"). Source and status are two
--    separate columns because they answer two separate questions: where
--    the placement came from, and whether a human has accepted it.
--
-- PRIVACY
-- -------
-- Identifiers, timestamps and classifications only. No narrative text,
-- no transcript, no extracted values. Same rule as 0038.
--
-- THIS TABLE IS NOT TRUTH
-- -----------------------
-- Placing a conversation on a trip day says where it happened. It does
-- not assert a biographical fact, does not write family truth, and does
-- not touch a correction projection. Both boundaries Gate 7 proved to
-- be deliberate stay exactly where they are.
------------------------------------------------------------

BEGIN;

-- 1 + 3. Trip lifecycle and remembered day selection.
ALTER TABLE trips ADD COLUMN live_state TEXT NOT NULL DEFAULT 'planning'
    CHECK (live_state IN ('planning', 'active', 'completed', 'archived'));

ALTER TABLE trips ADD COLUMN active_trip_day_id TEXT
    REFERENCES trip_days(id) ON DELETE SET NULL;

-- 2. At most one active trip per narrator. Enforced, not assumed.
CREATE UNIQUE INDEX IF NOT EXISTS ux_trips_one_live_active_per_person
    ON trips(person_id) WHERE live_state = 'active';

-- 4. The placement record.
CREATE TABLE IF NOT EXISTS trip_turn_links (
    id                     TEXT PRIMARY KEY,

    trip_id                TEXT NOT NULL
                               REFERENCES trips(id) ON DELETE CASCADE,

    -- Nullable: see "trip_day_id IS NULLABLE ON PURPOSE" above.
    trip_day_id            TEXT
                               REFERENCES trip_days(id) ON DELETE SET NULL,

    -- Correlation back to the conversation these rows live in.
    conv_id                TEXT NOT NULL DEFAULT '',

    -- The persisted rows in `turns`. The assistant row is the
    -- idempotency anchor; the user row is recorded so the timeline can
    -- show what the narrator said without a second lookup strategy.
    user_turn_row_id       INTEGER,
    assistant_turn_row_id  INTEGER NOT NULL,

    -- When the moment happened, for chronological ordering inside a
    -- day. Sourced from the persisted turn's own timestamp.
    captured_at            TEXT NOT NULL DEFAULT '',

    -- How the day was chosen.
    placement_source       TEXT NOT NULL DEFAULT 'active_trip_day'
        CHECK (placement_source IN (
            'active_trip_day', 'operator_selected',
            'timestamp_suggested', 'later_reconciled'
        )),

    -- Whether a human has accepted it. 'needs_day' is the observable
    -- reconciliation item, not an error state to be swept up.
    placement_status       TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (placement_status IN (
            'suggested', 'confirmed', 'needs_day', 'rejected'
        )),

    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

-- The idempotency mechanism itself. One persisted turn, one placement.
CREATE UNIQUE INDEX IF NOT EXISTS ux_trip_turn_links_assistant_row
    ON trip_turn_links(assistant_turn_row_id);

CREATE INDEX IF NOT EXISTS idx_trip_turn_links_trip
    ON trip_turn_links(trip_id);

CREATE INDEX IF NOT EXISTS idx_trip_turn_links_day
    ON trip_turn_links(trip_day_id);

CREATE INDEX IF NOT EXISTS idx_trip_turn_links_conv
    ON trip_turn_links(conv_id);

COMMIT;
