-- 0060 — what a person decided about each proposal.
--
-- WO-03B, steps 1–2. Ruled 2026-09-20: declines live in their own table
-- (option B), because the 0059 provenance table is EXCLUSIVELY about
-- values actually stored in the questionnaire, and a declined proposal
-- is a different kind of record — it documents a refusal, not the origin
-- of an answer.
--
-- ── ONE DEVIATION FROM THE APPROVED SHAPE, stated up front ──────────
--
-- The ruling approved a `declined_suggestions` table. This is
-- `suggestion_reviews` with a `verdict` column, recording BOTH outcomes.
--
-- The reason is a constraint in 0059 that is correct and must stay: an
-- `ai_suggested` provenance row CANNOT carry `turn_evidence` — the CHECK
-- forbids it, because an accepted machine suggestion is not narrator
-- testimony even when the suggestion cited a turn. So when a proposal
-- with `turn_evidence='verified'` is accepted, that verdict has nowhere
-- to go in the provenance row. Without this table it would be discarded
-- at the exact moment it becomes part of the record.
--
-- Recording acceptances here keeps the proposal's own evidence verdict,
-- its repeat count and its claimed turn — the full state of what a
-- person was looking at when they said yes. Declines were always going
-- to need that; acceptances turn out to need it for the same reason.
-- One table with a verdict, rather than two tables with identical
-- columns, and the decline-suppression query simply filters on it.
--
-- Everything the ruling required of the declines table holds here
-- unchanged. If the deviation is not accepted, the accepted rows can be
-- dropped and the table renamed; nothing else depends on the name.
--
-- ── THE FOUR REQUIREMENTS, and where each is met ────────────────────
--
-- 1. Match on narrator, stable entry id, field and value, with a
--    canonical value form before hashing. The primary key is exactly
--    that. `entry_id` not ordinal — after an insertion or reorder,
--    `parents[1]` is a different person, and a suppression keyed on the
--    ordinal would silence a proposal about the wrong relative. The
--    canonical form (NFC, trimmed, whitespace-collapsed, casefolded) is
--    computed by ONE function in answer_provenance.py and used by both
--    the write here and the re-proposal check, so they cannot drift.
--
-- 2. Record durably BEFORE removing from the visible queue. The decline
--    operation inserts here and rewrites the queue in one transaction.
--    A decline that vanished from the queue without a record would
--    re-offer itself on the next extraction — the nagging this table
--    exists to stop.
--
-- 3. Identical suppressed, materially different still reviewable. The
--    propose path checks the canonical hash before appending. Same hash
--    and verdict='declined' → not queued, and the attempt is counted so
--    "Lori keeps trying to tell you X" stays observable. A different
--    value → queued. A person who declined "6th grade" is still asked
--    about "7th grade".
--
-- 4. Exports and erasure. FK cascade, plus an AUTHORITATIVE, portable
--    lane in narrator_data_inventory — a narrator restored elsewhere
--    without their declines would be re-asked everything they had
--    already refused. And 4b: the row keeps `proposed_value` and
--    `field_path` verbatim, so what was declined is readable without
--    depending on an opaque hash.
--
-- ── NOT A BIOGRAPHICAL FACT ─────────────────────────────────────────
--
-- A declined row records that a proposal was refused. It does NOT
-- record that the opposite is true: declining "born in Duluth" does not
-- establish where they were born. Nothing may read this table as a
-- source of negative facts. Stated because this is exactly the kind of
-- record a later feature would be tempted to mine.
--
-- An accepted row records that a person accepted a machine's proposal.
-- The answer it produced carries `origin='ai_suggested'` in 0059 and
-- never `operator_direct` — "Lori proposed it and a person agreed" is a
-- weaker fact than "a person said it", and rewriting would launder the
-- first into the second.
--
-- ── UNRESOLVED DESTINATIONS (ruling C4) ─────────────────────────────
--
-- A proposal aimed at a repeatable section with no entry named cannot
-- be keyed on an entry. It is resolved by a person at review; the accept
-- operation refuses one that still has no entry. A decline of an
-- unresolved proposal is stored with entry_id='' and
-- destination_unresolved=1, and suppresses ONLY future proposals that
-- are also unresolved with the same (section, field, value) — never the
-- same value proposed for a named entry, because those are different
-- claims about different people.

CREATE TABLE IF NOT EXISTS suggestion_reviews (
    person_id       TEXT NOT NULL,
    section         TEXT NOT NULL,
    entry_id        TEXT NOT NULL DEFAULT '',
    field           TEXT NOT NULL,
    value_hash      TEXT NOT NULL,              -- sha256 of the canonical form

    verdict         TEXT NOT NULL,              -- accepted | declined

    -- What was reviewed, verbatim. Requirement 4b: readable without the
    -- hash. `field_path` is the dotted path as proposed, which for an
    -- unresolved destination is the only locator there is.
    suggestion_id   TEXT,
    field_path      TEXT NOT NULL,
    proposed_value  TEXT NOT NULL,
    proposed_at     TEXT,
    source_turn_id  TEXT,
    turn_evidence   TEXT NOT NULL DEFAULT 'absent',
    repeats         INTEGER NOT NULL DEFAULT 1,
    destination_unresolved INTEGER NOT NULL DEFAULT 0,

    reviewed_at     TEXT NOT NULL,
    -- Unverified, as everywhere: there is no operator authentication.
    -- It records who the caller SAID was reviewing.
    reviewed_by     TEXT NOT NULL DEFAULT '',

    -- A declined value proposed again is not queued; it is counted here,
    -- so persistence on the model's part stays observable.
    reproposals     INTEGER NOT NULL DEFAULT 0,
    last_reproposed_at TEXT,

    PRIMARY KEY (person_id, section, entry_id, field, value_hash),
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE,

    CHECK (verdict IN ('accepted', 'declined')),
    CHECK (turn_evidence IN ('verified', 'unverified', 'absent'))
);

CREATE INDEX IF NOT EXISTS idx_suggestion_reviews_person
    ON suggestion_reviews(person_id, verdict);
