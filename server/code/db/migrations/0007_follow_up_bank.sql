-- WO-LORI-WITNESS-FOLLOWUP-BANK-01 (2026-05-10) — patience layer
--
-- Per-session bank of unanswered story-doors that Lori has noticed
-- but not yet asked about. Implements Chris's locked principle:
-- "Each turn opens a new door. Lori can bank follow-up questions.
-- After a chapter is told, Lori goes to the bank for unanswered
-- followups as part of her active listener skills."
--
-- Schema rules:
--  - One row per banked question (NOT per session — many rows per session)
--  - Priority ordering follows the locked hierarchy:
--      1 = fragile name/correction (highest urgency to confirm)
--      2 = communication / logistics
--      3 = role transition mechanism
--      4 = relationship / personality
--      5 = daily life / off-duty texture
--      6 = emotional / reflection (only if narrator invited)
--  - asked_at_turn = NULL until Lori asks the question
--  - answered = 0/1, set when narrator addresses the topic in
--    a later turn (matched by triggering_anchor substring)
--  - why_it_matters carries operator-readable context so the bank
--    isn't a pile of prompts but a memory of open story doors
--
-- Indexes optimize:
--   - per-session unanswered lookup (bank_get_unanswered)
--   - per-session priority-ordered selection (bank_select_to_flush)

CREATE TABLE IF NOT EXISTS follow_up_bank (
    id TEXT PRIMARY KEY,                  -- uuid v4 string
    session_id TEXT NOT NULL,             -- conv_id
    person_id TEXT,                       -- narrator (may be null in WS-only flows)
    intent TEXT NOT NULL,                 -- 'fragile_name_confirm' / 'communication_logistics' / etc.
    question_en TEXT NOT NULL,            -- the literal question Lori would ask
    triggering_anchor TEXT NOT NULL,      -- narrator-text anchor that surfaced this door (e.g. 'Landstuhl Air Force Hospital')
    why_it_matters TEXT NOT NULL,         -- operator-readable rationale
    priority INTEGER NOT NULL DEFAULT 5,  -- 1 = critical fragile-name; 6 = optional
    triggering_turn_index INTEGER NOT NULL DEFAULT 0,  -- which turn opened this door
    asked_at_turn INTEGER,                -- NULL until Lori asks; populated when bank-flush fires
    answered INTEGER NOT NULL DEFAULT 0,  -- 0 = open, 1 = narrator addressed it
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_followup_bank_session
    ON follow_up_bank(session_id);

CREATE INDEX IF NOT EXISTS idx_followup_bank_unanswered
    ON follow_up_bank(session_id, answered, asked_at_turn);

CREATE INDEX IF NOT EXISTS idx_followup_bank_priority
    ON follow_up_bank(session_id, priority, triggering_turn_index DESC);
