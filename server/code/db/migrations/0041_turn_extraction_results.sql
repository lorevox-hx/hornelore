------------------------------------------------------------
-- 0041_turn_extraction_results.sql
-- WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2 -- 2026-07-31
--
-- WHAT THIS ADDS, AND WHY IT IS NOT A COLUMN ON THE LEDGER
-- --------------------------------------------------------
-- Phase 2 makes the backend the sole automatic extractor and sends the
-- result to the browser, which still owns projection, Shadow Review,
-- repeatable-section grouping and fragile-fact clarification. A result
-- that exists only inside a WebSocket frame is a result the narrator
-- loses by closing the tab, and the work order is explicit: "Do not
-- mark a result delivered merely because ws.send() did not raise."
--
-- So the result has to be durable BEFORE it is offered. The obvious
-- place is turn_extraction_ledger, and that is the wrong place.
--
-- The ledger answers "did extraction run for this turn, and what
-- happened". It is written once at 'started', closed once at a terminal
-- outcome, and never touched again; its UNIQUE (narrator_id, turn_key)
-- IS the idempotency mechanism that decides who runs. This table
-- answers a different question -- "has the browser applied this result
-- yet" -- and it is written repeatedly along a delivery lifecycle:
-- stored, delivered, applied. Putting a mutable delivery cursor on the
-- row that arbitrates claims means a delivery update and a claim share
-- one row, and it would make the ledger's own history editable long
-- after the attempt it records has finished.
--
-- 0038 states the ledger's storage rule directly -- "'duplicate' is
-- never stored ... Storing it would overwrite the real outcome" -- and
-- that care is the same care being taken here. Two lifecycles, two
-- tables. The link is ledger_id.
--
-- WHAT IT DOES NOT STORE
-- ----------------------
-- No narrator prose. `items` and `clarification_required` carry the
-- structured extraction output that /api/extract-fields already returns
-- to the browser today -- field paths, values, confidences -- which is
-- exactly what the browser must have to project a field, and nothing
-- more. There is no transcript column, no assistant text, no prompt.
--
-- ONLY RESULTS THERE IS SOMETHING TO DO WITH
-- -------------------------------------------
-- A row is written only when an extraction produced items to apply. A
-- noop or a failure has nothing for the browser to project, so it is
-- reported as a fire-and-forget event and leaves no row. That keeps the
-- meaning of this table exactly one thing: work the browser still owes.
--
-- IDENTITY IS BOUND AT CLAIM TIME, NOT AT DELIVERY TIME
-- -----------------------------------------------------
-- narrator_id and session_id are stored on the row rather than read
-- from "whoever is active now" when the result is finally applied. The
-- work order's requirement 4 is the reason: an operator can switch from
-- Chris to another narrator while an extraction is still running, and a
-- result that learned its owner at delivery time would attach Chris's
-- biography to whoever happened to be on screen. A late result stays
-- pending until its own narrator is active again.
------------------------------------------------------------

BEGIN;

CREATE TABLE IF NOT EXISTS turn_extraction_results (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,

    -- The claim this result belongs to. ON DELETE CASCADE because a
    -- result whose ledger row is gone describes an attempt that no
    -- longer exists.
    ledger_id      INTEGER
                       REFERENCES turn_extraction_ledger(id) ON DELETE CASCADE,

    -- The durable identity, all four bound when the claim was created.
    -- turn_key is the same 'turnrow:<turns.id>' the ledger uses and is
    -- the ONLY dedup key the browser may apply by -- never elapsed
    -- time, never input text, never "the last extraction was recent".
    narrator_id    TEXT NOT NULL,
    turn_key       TEXT NOT NULL,
    turn_id        TEXT NOT NULL DEFAULT '',
    session_id     TEXT NOT NULL DEFAULT '',

    -- What the extraction concluded. 'succeeded' is the only value that
    -- may modify projection or review state; the others exist so the
    -- browser can tell "nothing found" from "never ran".
    status         TEXT NOT NULL DEFAULT 'succeeded'
        CHECK (status IN ('succeeded', 'noop', 'failed')),
    method         TEXT NOT NULL DEFAULT '',

    -- Structured extractor output only -- the same shape
    -- /api/extract-fields returns today. JSON arrays.
    items                 TEXT NOT NULL DEFAULT '[]',
    clarification_required TEXT NOT NULL DEFAULT '[]',
    item_count     INTEGER NOT NULL DEFAULT 0,

    -- The delivery lifecycle. delivered_at means "we put it on a
    -- socket"; applied_at means "the browser said it applied it".
    -- They are separate on purpose: a send that did not raise is not
    -- evidence that anything was applied, and only applied_at retires
    -- the obligation.
    created_at     TEXT NOT NULL,
    delivered_at   TEXT,
    applied_at     TEXT
);

-- One result per completed turn. The same key the ledger claims on, so
-- a replayed turn cannot produce a second result to apply.
CREATE UNIQUE INDEX IF NOT EXISTS ux_turn_extraction_results_key
    ON turn_extraction_results(narrator_id, turn_key);

-- The catch-up read: everything this narrator has not applied yet,
-- oldest first.
CREATE INDEX IF NOT EXISTS idx_turn_extraction_results_pending
    ON turn_extraction_results(narrator_id, applied_at, created_at);

CREATE INDEX IF NOT EXISTS idx_turn_extraction_results_session
    ON turn_extraction_results(session_id);

COMMIT;
