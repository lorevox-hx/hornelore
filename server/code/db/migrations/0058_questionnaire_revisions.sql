-- 0058 — questionnaire revision history + a real revision counter.
--
-- WO-QUESTIONNAIRE-PERSISTENCE-INTEGRITY-01, block 1.
-- Filed from BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01 §B–§D.
--
-- ── WHY THIS EXISTS ───────────────────────────────────────────────────
--
-- `upsert_questionnaire` is a blind whole-document replace:
--
--     ON CONFLICT(person_id) DO UPDATE SET
--         questionnaire_json = excluded.questionnaire_json
--
-- Primary key person_id. One row per narrator. No merge, no concurrency
-- check, no history. Whatever any of its callers sends becomes the whole
-- record.
--
-- On 2026-09-15 one ordinary Bio Builder save deleted ten populated values
-- from a real narrator's two parents, including several hundred words of
-- hand-typed family history. The save added nothing: a leaf diff against a
-- snapshot taken an hour earlier read LOST 10, CHANGED 0, ADDED 0. It was
-- recoverable ONLY because an operator had taken that snapshot by hand an
-- hour before, for unrelated reasons. There was no other copy at full
-- length, and the browser's own draft had already been reduced to match.
--
-- History is the layer that makes the next one recoverable by design
-- rather than by luck. It is deliberately separate from the write-time
-- protections: concurrency and merge prevent a bad write, and neither can
-- undo one that a caller was entitled to make.
--
-- ── WHY A NEW COLUMN RATHER THAN REUSING `version` ────────────────────
--
-- `bio_builder_questionnaires.version` ALREADY EXISTS and is a SCHEMA
-- version. Every client hard-codes it: the FE sends DRAFT_SCHEMA_VERSION,
-- the PUT model defaults `version: int = 1`, and it is passed straight
-- through to the writer. A stale client therefore sends exactly the value
-- a fresh one sends, so attaching optimistic concurrency to that column
-- would produce a check that LOOKS correct and verifies nothing.
--
-- The trap is real and adjacent: on `interview_projections`, `version` IS
-- the revision counter (`next_version = stored_version + 1`,
-- db.py merge_projection_fields). Same column name, opposite meanings, two
-- tables. Hence `revision`, named so it cannot be confused with either.
--
-- ── WHY THIS SHAPE OF HISTORY ─────────────────────────────────────────
--
-- The row stores the document as it was BEFORE the write that superseded
-- it, plus who superseded it and how. That ordering matters: an archive
-- written after the fact cannot prove what was replaced, and the operator
-- question when something goes wrong is always "what did it look like
-- before, and which caller changed it".
--
-- `write_kind` exists so the destructive operations stay distinguishable
-- from ordinary edits in the record itself. A reset is allowed to empty a
-- questionnaire; an ordinary save is not. If the two are indistinguishable
-- afterwards, the history cannot answer whether an empty record was
-- intended.
--
-- ── OWNERSHIP ─────────────────────────────────────────────────────────
--
-- Narrator-owned and erasable: erasing a narrator must not leave their
-- biography behind in a history table. Declared CLASS_INSTALLATION /
-- portable "no" in narrator_data_inventory, because this is local recovery
-- bookkeeping rather than narrator content that should travel in a
-- package — the package already carries the CURRENT questionnaire, and a
-- restored narrator starts a fresh history on the installation that
-- receives them. The FK cascade is what makes erasure correct without the
-- erasure path needing to know this table exists.

ALTER TABLE bio_builder_questionnaires
    ADD COLUMN revision INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS bio_builder_questionnaire_revisions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id            TEXT    NOT NULL,

    -- The revision this row's content WAS. The write that superseded it
    -- produced revision + 1.
    revision             INTEGER NOT NULL,

    -- The document as it stood BEFORE the superseding write.
    questionnaire_json   TEXT    NOT NULL,

    -- What that superseded content had recorded about itself.
    source               TEXT    NOT NULL DEFAULT 'unknown',
    schema_version       INTEGER NOT NULL DEFAULT 1,
    content_updated_at   TEXT,

    -- What replaced it.
    superseded_at        TEXT    NOT NULL,
    superseded_by_source TEXT    NOT NULL DEFAULT 'unknown',

    -- 'merge'   — ordinary preservation-oriented update
    -- 'replace' — explicit whole-document replacement, authorised
    -- 'reset'   — deliberate emptying
    -- 'legacy'  — a pre-contract whole-document PUT, recorded as such
    write_kind           TEXT    NOT NULL DEFAULT 'merge',

    -- WHAT THE SUPERSEDING WRITE CLAIMED TO CHANGE, and what those paths
    -- held beforehand. The prior document above is enough to RECOVER from;
    -- these three are what make the question answerable as a query:
    --
    --     "which write removed parents[0].notableLifeEvents, and when?"
    --
    -- rather than as a diff hunt across archived documents. `changed_paths`
    -- and `removed_paths` are JSON arrays; `previous_values` maps each of
    -- those paths to the value it held before. Null on a replace or reset,
    -- where the answer is "all of it" and the prior document says so.
    changed_paths        TEXT,
    removed_paths        TEXT,
    previous_values      TEXT,

    FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bbq_revisions_person
    ON bio_builder_questionnaire_revisions(person_id, revision DESC);

CREATE INDEX IF NOT EXISTS idx_bbq_revisions_superseded_at
    ON bio_builder_questionnaire_revisions(superseded_at);
