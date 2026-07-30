------------------------------------------------------------
-- 0038_turn_extraction_ledger.sql
-- WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7) -- 2026-07-30
--
-- THE DEFECT THIS TABLE EXISTS TO CLOSE
-- -------------------------------------
-- Gate 7 Phase 1 measured five truth-write stages per narrator turn and
-- found exactly one real defect: extract_fields_called = 0 on every
-- chat_ws turn. /api/extract-fields had no internal Python caller --
-- only ui/js/interview.js posted to it -- so a WebSocket-driven turn
-- never requested field extraction and nothing downstream could fire.
--
-- Phase 2 connects the completed turn to extraction through one shared
-- application service. A completed turn can arrive more than once:
-- socket reconnect, client retry, an operator replay through the
-- harness. Without a persisted claim the same turn would extract twice
-- and produce duplicate proposals.
--
-- WHY A TABLE AND NOT AN IN-MEMORY SET
-- ------------------------------------
-- An in-process guard dies with the worker. A reconnect after a restart
-- would re-extract, and a crash mid-extraction would leave no trace
-- that the work had ever been attempted. The UNIQUE INDEX below is the
-- actual idempotency mechanism: the claim is an INSERT that either wins
-- or raises IntegrityError. A row left at outcome=started is a recorded
-- in-flight attempt, which is the point -- extraction that vanishes on
-- process shutdown still leaves its state behind.
--
-- THE KEY IS THE PERSISTED TURN, NOT THE TEXT
-- -------------------------------------------
-- turn_key is derived from the assistant row actually committed by
-- persist_turn_transaction (turnrow:<turns.id>), never from a hash of
-- the narrator's words. Two turns that legitimately say the same thing
-- are two turns. A replay of one committed turn is one turn.
--
-- PRIVACY
-- -------
-- This table stores identifiers, counts, and classifications only. No
-- narrative text, no extracted values, no field paths. Gate 7 Step 5:
-- "Do not log raw private narrative text unless existing privacy policy
-- explicitly permits it." The same rule binds what is persisted here.
--
-- THIS TABLE IS NOT TRUTH
-- -----------------------
-- It records that extraction was requested for a turn and how that
-- request ended. It is not a proposal, not a family-truth row, and not
-- a projection. The review boundary Phase 1 proved to be deliberate is
-- untouched: family truth stays operator-gated, projections stay
-- correction-gated.
------------------------------------------------------------

BEGIN;

CREATE TABLE IF NOT EXISTS turn_extraction_ledger (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Identity of the narrator whose turn this was. Scoping every
    -- lookup by narrator_id keeps the ledger narrator-isolated for the
    -- same reason story_candidates is (WO-GOLFBALL-HARNESS-02).
    narrator_id  TEXT NOT NULL,

    -- The stable key. Format: 'turnrow:<turns.id>' for a persisted
    -- chat_ws turn. Any future producer MUST derive this from a
    -- committed row, not from request text.
    turn_key     TEXT NOT NULL,

    -- Correlation only -- the client-supplied turn id that the probe,
    -- the harness, and api.log already use. Not the idempotency key:
    -- a client may retry with a fresh turn_id for the same saved turn.
    turn_id      TEXT NOT NULL DEFAULT '',
    session_id   TEXT NOT NULL DEFAULT '',
    turn_mode    TEXT NOT NULL DEFAULT '',

    -- Which caller drove this: 'chat_ws' | 'http' | 'harness_replay'.
    source       TEXT NOT NULL DEFAULT '',

    -- One of: started | succeeded | noop | failed.
    -- 'duplicate' is never stored -- it is what the CLAIM returns when
    -- this row already exists, so it describes the second attempt, not
    -- the first. Storing it would overwrite the real outcome.
    outcome      TEXT NOT NULL DEFAULT 'started',

    item_count   INTEGER NOT NULL DEFAULT 0,
    method       TEXT NOT NULL DEFAULT '',

    -- Exception class name only. Never a message, never a traceback --
    -- an extractor message can quote the narrator back.
    error_class  TEXT NOT NULL DEFAULT '',

    duration_ms  INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

-- The idempotency mechanism itself. Not advisory.
CREATE UNIQUE INDEX IF NOT EXISTS ux_turn_extraction_ledger_key
    ON turn_extraction_ledger(narrator_id, turn_key);

CREATE INDEX IF NOT EXISTS idx_turn_extraction_ledger_turn_id
    ON turn_extraction_ledger(turn_id);

CREATE INDEX IF NOT EXISTS idx_turn_extraction_ledger_outcome
    ON turn_extraction_ledger(outcome, created_at);

COMMIT;
