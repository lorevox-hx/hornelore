-- 0061 — suggestions that must not be accepted unchanged.
--
-- WO-04, protection layer. Lands BEFORE any new questionnaire section,
-- because the risk it guards is created by those sections existing.
--
-- ── THE RISK, STATED EXACTLY ────────────────────────────────────────
--
-- Acceptance is gated on whether the questionnaire defines the
-- destination (WO-03B). That guard reads the live schema. So the moment
-- `military` becomes a real section, Kent's queued proposal
--
--     military.branch = "Nike Ajax Nike Hercules missile site"
--
-- stops being "cannot be added" and becomes one entry-pick and one
-- click from his family's permanent record. The value is an
-- installation and a missile system; it is not a branch of service.
--
-- Expanding the biography must not make an old extraction mistake
-- EASIER to turn into a permanent family record. That is the acceptance
-- criterion for the whole work order, and this table is how it is met.
--
-- ── WHY A SERVER TABLE AND NOT A UI STATE ───────────────────────────
--
-- The review surface can hide an Accept button. That is presentation.
-- A flag that lives only in the browser is not protection: the accept
-- endpoint would still honour the request, and the endpoint is what
-- writes the biography. So the check runs in `suggestion_review.accept`
-- INSIDE the write transaction, next to the destination check it
-- extends.
--
-- ── IDENTITY: suggestion_id FIRST, CANONICAL TUPLE AS FALLBACK ──────
--
-- A proposal queued through the WO-03B append route carries a
-- server-minted `suggestion_id`. That is the identity to use: it is
-- unambiguous and it survives the value being edited.
--
-- The 29 rows queued before that route existed have no id. They are
-- identified by the same canonical tuple `suggestion_reviews` uses —
-- (person_id, section, entry_id, field, value_hash) over the NFC /
-- trimmed / whitespace-collapsed / casefolded value. That fallback is
-- documented rather than implicit because it is weaker in one specific
-- way: two different proposals of the same value to the same
-- destination are indistinguishable. For a flag that is acceptable —
-- both deserve the same protection — and it is NOT acceptable for the
-- disposition record, which is why dispositions are written to
-- `suggestion_reviews` keyed the same way and carry the suggestion_id
-- when one exists.
--
-- `suggestion_id` is therefore NULLABLE and indexed, not the primary
-- key: a legacy row has none, and the tuple must still be unique.
--
-- ── WHAT A FLAG DOES NOT MEAN ───────────────────────────────────────
--
-- A flag is not a verdict that the value is false. `queued_before_home`
-- states a FACT about timing and implies nothing about content. The
-- other three record why a reviewer should look, not what they should
-- conclude. Nothing reads this table as evidence about the world.
--
-- A flagged suggestion is never auto-declined, auto-accepted, migrated
-- or deleted. It stays in the queue until a person acts on it.

CREATE TABLE IF NOT EXISTS suggestion_flags (
    person_id       TEXT NOT NULL,

    -- Canonical destination, same decomposition as 0060.
    section         TEXT NOT NULL,
    entry_id        TEXT NOT NULL DEFAULT '',
    field           TEXT NOT NULL,
    value_hash      TEXT NOT NULL,

    -- Preferred identity. NULL only for rows queued before the
    -- server-owned append route existed (before 2026-09-20).
    suggestion_id   TEXT,

    -- Readable without the hash, per the 0060 precedent.
    field_path      TEXT NOT NULL,
    proposed_value  TEXT NOT NULL,

    -- queued_before_home    the destination did not exist when this was
    --                       queued. A fact about timing, not content.
    -- value_not_a_field     the value is not the kind of thing the field
    --                       holds (a place in a years field).
    -- model_uncertainty     the model's own hedging stored as a value.
    -- misclassified_section right kind of fact, wrong section.
    reason          TEXT NOT NULL,

    -- Where the evidence is, when known. Free text; may be empty.
    source_note     TEXT NOT NULL DEFAULT '',

    flagged_at      TEXT NOT NULL,
    flagged_by      TEXT NOT NULL DEFAULT '',

    -- Set when a person has acted. A flag with a disposition no longer
    -- blocks; the disposition itself is recorded in suggestion_reviews.
    -- 'corrected' | 're-homed' | 'declined'
    disposition     TEXT,
    disposed_at     TEXT,

    PRIMARY KEY (person_id, section, entry_id, field, value_hash),
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE,

    CHECK (reason IN ('queued_before_home', 'value_not_a_field',
                      'model_uncertainty', 'misclassified_section')),
    CHECK (disposition IS NULL OR disposition IN ('corrected', 're-homed', 'declined'))
);

CREATE INDEX IF NOT EXISTS idx_suggestion_flags_person
    ON suggestion_flags(person_id, disposition);

CREATE INDEX IF NOT EXISTS idx_suggestion_flags_sid
    ON suggestion_flags(suggestion_id);

-- ── the accepted answer's own record of being corrected ─────────────
--
-- When a person accepts a flagged suggestion they must supply a
-- corrected value or a different destination (WO-04 requirement 3). The
-- ORIGINAL proposal has to survive that, or the record loses the fact
-- that a machine proposed something else and a person fixed it.
--
-- `suggestion_reviews` already stores `proposed_value` verbatim. This
-- adds what the person put in its place, so the pair reads:
-- "Lori proposed A, a person entered B instead, and here is why A was
-- flagged."
ALTER TABLE suggestion_reviews
    ADD COLUMN corrected_value TEXT;

ALTER TABLE suggestion_reviews
    ADD COLUMN correction_reason TEXT;
