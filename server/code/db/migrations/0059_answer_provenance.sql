-- 0059 — where each questionnaire answer came from.
--
-- WO-03A (WO-BIOGRAPHY-CONFIRMATION-MODEL-01, phase A).
-- Approved 2026-09-20 after four corrections and one measured finding.
--
-- ── WHY THIS EXISTS ───────────────────────────────────────────────────
--
-- The stored questionnaire records WHAT a narrator's biography says and
-- nothing about WHO SAID IT. A value typed by an operator, a value the
-- narrator spoke in chat, and a value Lori inferred and wrote in are
-- byte-identical once stored. So a reader — the prompt composer, the
-- Timeline, the Life Map, the Memoir — has no way to tell testimony from
-- guesswork, and the safest thing it can do is distrust all of it
-- equally. That is the defect: presence in the questionnaire was being
-- read as confirmation, and it never was.
--
-- The operating rule, stated by Chris:
--
--   Lori must not be able to mark her own suggestions as human-confirmed
--   merely by writing them into the questionnaire.
--
-- Which is why this is enforced at the SERVER WRITE BOUNDARY and not in
-- the browser, and why the classification comes from WHICH ENDPOINT was
-- called rather than from anything the client declares about itself.
--
-- ── WHAT `operator_direct` DOES NOT MEAN ──────────────────────────────
--
-- It means THIS APPLICATION OPERATION WAS INVOKED: a write arrived on
-- the Bio Builder form's own endpoint rather than on the shared PUT that
-- Lori's writers share. That is a fact about the call.
--
-- It does NOT establish the real-world identity of whoever invoked it.
-- There is no operator authentication on this route. The endpoint
-- separation solves one specific problem — stopping Lori's existing
-- writers from acquiring the operator's authority through a shared
-- route — and it is not a substitute for authentication or
-- authorization, which do not exist here yet.
--
-- `actor_id` is the sharpest case and is called out on its own below:
-- it is an UNVERIFIED CLAIM, recorded as given. Unlike `turn_evidence`,
-- which carries its own verdict, nothing checks it. A consumer that
-- renders it as "Chris entered this" is asserting more than the record
-- supports; the record supports "a write arrived on the human-entry
-- route claiming to be Chris".
--
-- This distinction must survive into any product claim made about
-- provenance. "A person entered this" and "this arrived through the
-- route a person's form uses" are different sentences, and a family
-- archive is exactly the context where the difference matters.
--
-- ── WHY ABSENCE IS A STATE, AND THERE IS NO BACKFILL ──────────────────
--
-- NO ROW MEANS UNKNOWN. Janice's 100 values, Kent's 86 and Christopher's
-- 130 get zero rows and keep them. Inventing provenance for an existing
-- value would be the system asserting something nobody told it — the
-- exact failure this table exists to end. Unknown is the truth about
-- them, and it is recoverable: the next time a person enters one of those
-- answers deliberately, it gains a real row.
--
-- ── WHY IT IS KEYED BY ENTRY ID RATHER THAN BY PATH ───────────────────
--
-- This is what WO-02 was for. `flatten_document` produces positional
-- paths — `parents[0].occupation` — so inserting a relative at the head
-- renames every path after it. Provenance keyed on those strings would
-- re-point on a reorder, and a correction made against one person would
-- silently attach to another. `_entryId` names the person; the ordinal
-- names a slot that person happens to occupy today.
--
-- Flat sections carry entry_id = '' rather than NULL, because NULL is not
-- comparable and this is half of a primary key.
--
-- ── WHY origin IS PERMANENT AND CONFIRMATION IS ADDITIVE ──────────────
--
-- An accepted suggestion does NOT become `operator_direct`. It stays
-- `ai_suggested` and gains `confirmed_via` / `confirmed_at`. The record
-- therefore always shows that Lori proposed it and that a person agreed,
-- which is a different and weaker fact than a person having said it
-- unprompted. Rewriting `origin` on acceptance would launder the first
-- into the second, and after a few rounds nothing would remember which
-- was which.
--
-- "Confirmed" here means accepted into the biography. It does not mean
-- historically infallible, and no consumer should render it as proof.
--
-- ── WHY THE CITED TURN IS KEPT EVEN WHEN IT FAILS TO VERIFY ───────────
--
-- Measured on the live database 2026-09-20, read-only:
--
--     memory_archive_turns          0 rows — never populated, not once
--     turns                     1,487 rows
--     sessions.person_id        exists (0045), write-once, conflict-raising
--     turns attributable           19 of 1,487
--
-- The first revision of this design verified narrator turns against
-- `memory_archive_turns`. That table has never held a live chat turn, so
-- as designed it could not have verified anything. The working check is
-- the join through `sessions.person_id`, with two further conditions:
-- the turn must be a user row, and it must not be a system directive.
--
-- The directive clause is not padding. A composed instruction is stored
-- with role='user' — live row 2634 on a real narrator's session reads
-- `[SYSTEM: The narrator has been quiet...]` with
-- meta_json.origin='system_directive'. Cite that as narrator testimony
-- and the system records its own stage direction as something a person
-- said.
--
-- Coverage is thin and this table does not pretend otherwise: 1,468 of
-- 1,487 existing turns predate the ownership column or came through the
-- REST chat path, which still mints ownerless sessions (api.py:799-800 —
-- recorded as a separate defect, deliberately not fixed here). A citation
-- to one of those FAILS verification. That is the correct answer.
--
-- Hence three states, and hence `source_turn_id` survives a failure:
--
--     verified    the join and both clauses passed
--     unverified  an id was cited and did not verify
--     absent      no id was cited
--
-- Nulling the id on failure would erase the difference between "nobody
-- cited anything" and "somebody cited something that did not check out",
-- and the second is the one worth investigating. Only `verified` may be
-- read as evidence.
--
-- ── OWNERSHIP ─────────────────────────────────────────────────────────
--
-- Narrator-owned, erasable, and PORTABLE — unlike the revision history in
-- 0058. Where an answer came from travels with the answer: a narrator
-- restored onto another installation whose biography arrives stripped of
-- its provenance would arrive as 100 unattributed assertions, which is
-- the state this work order exists to end. Declared AUTHORITATIVE in
-- narrator_data_inventory. The FK cascade is what makes erasure correct
-- without the erasure path needing to know this table exists.

CREATE TABLE IF NOT EXISTS bio_builder_answer_provenance (
    person_id       TEXT NOT NULL,

    -- Section id as the questionnaire names it ('parents', 'basics'),
    -- the entry within it, and the field on that entry. Together these
    -- identify an answer WITHOUT depending on its position.
    section         TEXT NOT NULL,
    entry_id        TEXT NOT NULL DEFAULT '',
    field           TEXT NOT NULL,

    -- operator_direct — a person typed it into the Bio Builder form
    -- narrator_direct — the narrator said it, through the narrator route
    -- ai_suggested    — Lori proposed it
    --
    -- Permanent. An acceptance adds the confirmation columns below and
    -- never rewrites this one.
    origin          TEXT NOT NULL,
    origin_at       TEXT NOT NULL,

    -- Who the caller SAID was operating the form / which narrator spoke.
    -- Free text, recorded as given; '' when the caller did not say, never
    -- guessed.
    --
    -- UNVERIFIED BY CONSTRUCTION. There is no operator authentication on
    -- these routes, so nothing checks this value — it is the one field
    -- here that carries a claim with no verdict attached, and a reader
    -- must not treat it as an identity. See the note above.
    actor_id        TEXT NOT NULL DEFAULT '',

    -- The CLAIMED turn, kept in all three evidence states, and a separate
    -- column saying whether it stood up to the ownership and directive
    -- checks. See the note above on why a failure does not null the id.
    source_turn_id  TEXT,
    turn_evidence   TEXT NOT NULL DEFAULT 'absent',

    -- The narrator's own words, before any normalisation. The stored
    -- answer may be a tidied form; a consumer comparing the two can see
    -- which it is holding. There is deliberately no `normalized` flag —
    -- a derived boolean that can disagree with the data it describes is
    -- worse than the comparison it replaces.
    original_text   TEXT,

    -- Set only when this answer began as a suggestion.
    proposed_by     TEXT,
    confirmed_via   TEXT,
    confirmed_at    TEXT,

    -- The revision of bio_builder_questionnaires this row was written
    -- alongside. Provenance and answer commit in one transaction, so this
    -- always names a revision that exists.
    revision        INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (person_id, section, entry_id, field),
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE,

    CHECK (origin IN ('operator_direct','narrator_direct','ai_suggested')),
    CHECK (turn_evidence IN ('verified','unverified','absent')),
    -- Only a narrator statement can carry turn evidence. An operator
    -- entry or a machine suggestion citing a chat turn would be claiming
    -- support it does not have, and the constraint refuses it rather than
    -- leaving it to every reader to notice.
    CHECK (turn_evidence = 'absent' OR origin = 'narrator_direct')
);

CREATE INDEX IF NOT EXISTS idx_bbq_provenance_person
    ON bio_builder_answer_provenance(person_id, section);

CREATE INDEX IF NOT EXISTS idx_bbq_provenance_origin
    ON bio_builder_answer_provenance(person_id, origin);

-- ── the superseded provenance, archived with the superseded value ─────
--
-- The table above names the CURRENT provenance of the CURRENT value, so a
-- correction overwrites it. History belongs where correction history
-- already lives: 0058 stores `previous_values` per path and is written by
-- `_archive` inside the same transaction as the write it describes.
--
-- The pair always describes the same moment — what the value was, and
-- where it came from. Keeping them in separate tables with separate
-- timing is how they would drift.
--
-- Additive, no backfill. Every row already written reads '{}' , which is
-- correct: those writes had no provenance to supersede.
ALTER TABLE bio_builder_questionnaire_revisions
    ADD COLUMN previous_provenance TEXT NOT NULL DEFAULT '{}';
