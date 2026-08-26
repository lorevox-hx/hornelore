-- 0051 — the ten-topic Profile Seed walk gets a durable server owner.
--
-- WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 1 (2026-08-26).
--
-- WHAT THIS TABLE IS FOR. Until now the only thing standing between a
-- narrator and being asked the same ten questions forever was
-- `state.session.currentPass`, a value that lives in browser memory.
-- Phase 0 measured the consequences and they are not subtle: no file
-- under `server/code/api` assigns a pass, `db.py` never persists one,
-- and the thing that actually ends the onboarding is a chronology
-- cache -- so the same narrator is `pass1` on one device and `pass2a`
-- on another, and clearing a cache reverses the result.
--
-- This table is that missing owner. One row per ENROLLED narrator.
--
-- WHAT IT DELIBERATELY DOES NOT DO.
--
--   * It creates NO ROWS for people who already exist. A narrator with
--     a missing row is HISTORICAL / NOT ENROLLED -- which is a settled
--     state, not an invitation to start a questionnaire on somebody who
--     has been talking to Lori for months. Work order decision 3. There
--     is deliberately no `INSERT ... SELECT FROM people` below, and its
--     absence is the feature.
--
--   * It stores NO NARRATOR PROSE. Work order decision 8. `topic_state_json`
--     holds ten topic ids mapped to one of four dispositions and nothing
--     else -- no answer text, no refusal wording, no paraphrase. The
--     narrator's biography stays in the truth stores that already own it
--     (`profiles`, `bio_facts`, `interview_projections`). If a future
--     reader wants to know WHAT the narrator said about their siblings,
--     the answer is "ask the truth store", and that is the correct
--     answer.
--
--   * It carries no narrator_type. Decision 2: live, reference, and any
--     future type follow the same rule. A column here would be an
--     invitation to gate on it.
--
-- ON DELETE CASCADE, AND WHY IT MATTERS THAT IT IS A REAL ONE. The
-- extended person-scoped delete list in `db.py` exists for tables the
-- FK cascade cannot reach. This table is not one of them: it has a
-- genuine FK to `people(id)`, `PRAGMA foreign_keys=ON` is set in
-- `_connect()`, and `hard_delete_person` deletes the people row inside
-- its transaction. So this belongs in the ORDINARY inventory and the
-- cascade does the work. Putting it in the extended list as well would
-- be a second deletion path for a table that already has a working
-- one.
--
-- `version` IS THE CONCURRENCY CONTRACT. It is compared and incremented
-- inside one `BEGIN IMMEDIATE` transaction, exactly as
-- `story_candidate_apply_review` does for operator review. A stale
-- write is a 409 that changes nothing. It starts at 1 so that "the
-- version I read" is never 0-vs-missing ambiguous.

CREATE TABLE IF NOT EXISTS profile_seed_onboarding (
    person_id        TEXT PRIMARY KEY
                       REFERENCES people(id) ON DELETE CASCADE,

    -- pending   — enrolled, identity anchors not yet complete. The walk
    --             must not start before Lori knows the narrator's name.
    -- active    — anchors complete, topics remain.
    -- paused    — the operator or narrator asked to stop for now.
    -- completed — TERMINAL. Nothing re-opens it, so finishing the walk
    --             once means finishing it once.
    status           TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'active',
                                         'paused', 'completed')),

    -- {topic_id: 'unanswered'|'known'|'addressed'|'declined'}. Validated
    -- as JSON at the storage layer so a malformed write cannot become a
    -- resolver crash on every subsequent turn.
    topic_state_json TEXT NOT NULL DEFAULT '{}'
                       CHECK (json_valid(topic_state_json)),

    -- The one topic Lori may ask about this turn. NULL when pending,
    -- paused or completed. Membership in the canonical registry is
    -- enforced by the service; SQLite is not given a hand-copied list
    -- to drift from.
    active_topic_id  TEXT,

    -- Monotonic. See the note above.
    version          INTEGER NOT NULL DEFAULT 1
                       CHECK (version >= 1),

    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,

    -- Set exactly once, when the last remaining topic resolves. A
    -- second completion must not move it, or "when did this narrator
    -- finish onboarding" stops being answerable.
    completed_at     TEXT
);

-- The operator progress surface lists by status; the resolver reads by
-- person_id, which the primary key already covers.
CREATE INDEX IF NOT EXISTS idx_profile_seed_onboarding_status
    ON profile_seed_onboarding(status, updated_at);
