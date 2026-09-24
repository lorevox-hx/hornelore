-- 0063 — the canonical Life Record (WO-HORNELORE-INTEGRATED-LIFE-RECORD-01, Batch B-1).
--
-- ── WHAT THIS IS ──────────────────────────────────────────────────────
--
-- The ONE source of record for a narrator's biography: people, names,
-- places, occurrences, relationships, animals, story references, and the
-- assertions + acceptance decisions that give every value its provenance.
-- Design: docs/wo/WO-LIFE-RECORD-01_Spec.md §3; decisions D1–D13.
--
-- Written ONLY by services/life_record/writer.py (Batch B-2). Everything
-- else that holds biography — profile_json, bio_facts, graph_* — is a
-- projection of this (§2.1). Nothing here is written on GET, render,
-- section change or narrator switch (§3.10).
--
-- ── SHAPE, AND THE ONE RULE THAT DECIDES IT ───────────────────────────
--
-- ONE FACT, ONE HOME. Entity tables hold IDENTITY and STRUCTURE only: ids,
-- event types, participants, relationship endpoints and kind, name forms.
-- Every VALUE-BEARING fact — an event's date, a person's life status,
-- pronouns, a reported count, an occupation — lives ONLY in lr_assertions,
-- with its provenance, and competing values of one proposition coexist
-- there until lr_acceptances records a human decision (§2.4, §3.9). The
-- "current" value is DERIVED when the record is assembled, never stored a
-- second time.
--
-- ── IDENTITY ──────────────────────────────────────────────────────────
--
-- The narrator's own person IS people.id: lr_record.narrator_person_id must
-- equal narrator_id, so a record can never have two narrators (§3.1) and
-- the existing stable narrator id is retained, not re-minted. Every other
-- person gets a server-issued TEXT id. Names are attributes of a person,
-- never the key; a new name never mints a person (§4).
--
-- ── NARRATOR ISOLATION AND ERASURE ────────────────────────────────────
--
-- Shared SQLite (D8). Every table carries narrator_id REFERENCES people(id)
-- ON DELETE CASCADE, so erasing a narrator removes their whole record
-- through the same cascade the graph tables already use. Each table also
-- has a DbLane in narrator_data_inventory.py (§3.11 gate).
--
-- Between lr_* tables the foreign keys are NO ACTION, checked at the end of
-- each statement: a narrator-wide cascade removes everything together, but
-- deleting ONE person while a relationship, participation or name still
-- names them fails — deleting a person requires an explicit decision about
-- what refers to them (§3.7). Pointers that would form a cycle
-- (person → birth event → participant → person) or point back into their
-- own table (supersedes, conflict links) are plain columns; the writer
-- enforces them (B-3) and the exporter checks them as COLUMN_ONLY_REFERENCES.
--
-- Every table has ONE TEXT primary key, and natural keys are UNIQUE
-- constraints, never composite primary keys: the merge collision hunt
-- (narrator_merge; tests/test_narrator_merge.py ClosureIntegrity) can only
-- prove coverage of single-column keys.

CREATE TABLE IF NOT EXISTS lr_record (
    narrator_id         TEXT PRIMARY KEY REFERENCES people(id) ON DELETE CASCADE,
    narrator_person_id  TEXT NOT NULL,
    revision            INTEGER NOT NULL DEFAULT 0,
    schema_version      INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK (narrator_person_id = narrator_id)
);

CREATE TABLE IF NOT EXISTS lr_people (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    -- POINTERS, not dates (§3.8). Must resolve to that person's OWN birth /
    -- death event — enforced by the writer (B-3), not by a FK (cycle).
    birth_event_id      TEXT,
    death_event_id      TEXT,
    preferred_name_id   TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lr_people_narrator ON lr_people(narrator_id);

-- Names (§4): fullText as supplied and never parsed; parts only as supplied.
-- A former name belongs to the same person and carries its own `use`,
-- which says whether it may be spoken at all (Chris, 2026-09-23: storing a
-- former name never authorises disclosing it; Batch D enforces `use`).
CREATE TABLE IF NOT EXISTS lr_names (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    person_id           TEXT NOT NULL REFERENCES lr_people(id),
    kind                TEXT NOT NULL DEFAULT 'current'
                        CHECK (kind IN ('current', 'former', 'variant', 'also_known_as')),
    full_text           TEXT NOT NULL CHECK (length(trim(full_text)) > 0),
    given_parts_json    TEXT,                 -- JSON list, supplied not split
    family              TEXT,                 -- the complete surname
    birth_family        TEXT,
    prefixes_json       TEXT,
    suffixes_json       TEXT,
    use                 TEXT CHECK (use IS NULL OR use IN
                            ('everyday', 'formal', 'historical_only', 'do_not_use')),
    period_json         TEXT,                 -- {start,end} dates, optional
    pronunciation       TEXT,
    origin_story        TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lr_names_person ON lr_names(person_id);

-- Places are shared and referenced, never text-rewritten; a referenced
-- place is merged, not hard-deleted (§2.7).
CREATE TABLE IF NOT EXISTS lr_places (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    label               TEXT NOT NULL CHECK (length(trim(label)) > 0),
    parts_json          TEXT,
    merged_into_id      TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lr_places_narrator ON lr_places(narrator_id);

-- Occurrences (D7: canonical, BENEATH the DOB + seven-era scaffold). The
-- date is an assertion, not a column. Reaching the Life Map still needs
-- promotion (§2.5); nothing here places anything.
CREATE TABLE IF NOT EXISTS lr_events (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    type                TEXT NOT NULL CHECK (type IN
                            ('birth', 'death', 'union', 'separation', 'move',
                             'education', 'work', 'service', 'arrival', 'loss',
                             'milestone', 'other')),
    place_id            TEXT REFERENCES lr_places(id),
    attributes_json     TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lr_events_narrator ON lr_events(narrator_id);

CREATE TABLE IF NOT EXISTS lr_event_participants (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    event_id            TEXT NOT NULL REFERENCES lr_events(id),
    person_id           TEXT NOT NULL REFERENCES lr_people(id),
    role                TEXT NOT NULL CHECK (length(trim(role)) > 0),
    UNIQUE (event_id, person_id, role)
);
CREATE INDEX IF NOT EXISTS idx_lr_participants_person ON lr_event_participants(person_id);

-- Relationships (§3.7): "subject is <kind> of other", one direction stored,
-- endpoints inside this record. No preselected kind; `other` needs a
-- description. A derived relationship is edited through its event.
CREATE TABLE IF NOT EXISTS lr_relationships (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    subject_person_id   TEXT NOT NULL REFERENCES lr_people(id),
    other_person_id     TEXT NOT NULL REFERENCES lr_people(id),
    kind                TEXT NOT NULL CHECK (kind IN
                            ('parent_of', 'child_of', 'sibling_of', 'spouse_of',
                             'partner_of', 'grandparent_of', 'caregiver_of',
                             'chosen_family_of', 'friend_of', 'mentor_of', 'other')),
    described_as        TEXT,
    qualifiers_json     TEXT,
    narrator_label      TEXT,
    period_json         TEXT,
    basis               TEXT NOT NULL DEFAULT 'stated'
                        CHECK (basis IN ('stated', 'derived_from_event')),
    derived_from_event_id TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK (subject_person_id <> other_person_id),
    CHECK (kind <> 'other' OR length(trim(coalesce(described_as, ''))) > 0),
    CHECK ((basis = 'derived_from_event') = (derived_from_event_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_lr_rel_narrator ON lr_relationships(narrator_id);

-- Animals are their own entity, not people (D1f).
CREATE TABLE IF NOT EXISTS lr_animals (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    name                TEXT,
    species             TEXT,
    attributes_json     TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- Stories (§2.6): CAPTURED stories are a reference to the narrator's
-- preserved words and never carry a copy; AUTHORED stories hold their own
-- text. Never both.
CREATE TABLE IF NOT EXISTS lr_stories (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    origin              TEXT NOT NULL CHECK (origin IN ('captured', 'authored')),
    candidate_id        TEXT REFERENCES story_candidates(id),
    body                TEXT,
    kind                TEXT NOT NULL CHECK (kind IN
                            ('memory', 'reflection', 'lesson', 'anecdote',
                             'description', 'message', 'tradition')),
    title               TEXT,
    when_json           TEXT,
    supersedes_id       TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    CHECK ((origin = 'captured' AND candidate_id IS NOT NULL AND body IS NULL)
        OR (origin = 'authored' AND candidate_id IS NULL AND body IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS lr_story_refs (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    story_id            TEXT NOT NULL REFERENCES lr_stories(id),
    target_type         TEXT NOT NULL CHECK (target_type IN ('person', 'place', 'event', 'animal')),
    target_id           TEXT NOT NULL,
    UNIQUE (story_id, target_type, target_id)
);

-- Sources: where evidence came from. A source is not a verdict.
CREATE TABLE IF NOT EXISTS lr_sources (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    kind                TEXT NOT NULL CHECK (kind IN
                            ('narrator_said', 'operator_entered', 'document',
                             'extracted', 'imported', 'migrated')),
    ref_json            TEXT,                 -- e.g. {"turn_id":…} or {"candidate_id":…}
    description         TEXT,
    created_at          TEXT NOT NULL
);

-- Assertions (§3.9): every value-bearing fact. RECORDED_BY is who put it in
-- the record; ASSERTED_BY is whose claim it is — an operator typing what the
-- narrator said records it, the narrator asserts it. PROVENANCE IS NOT TRUTH:
-- nothing here, including status, decides which account is accepted.
CREATE TABLE IF NOT EXISTS lr_assertions (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    subject_type        TEXT NOT NULL CHECK (subject_type IN
                            ('person', 'event', 'place', 'animal', 'relationship')),
    subject_id          TEXT NOT NULL,
    concept_id          TEXT NOT NULL,        -- a concept in the ONE catalog
    context_key         TEXT NOT NULL DEFAULT '',   -- proposition qualifier (period…)
    value_json          TEXT NOT NULL,
    source              TEXT NOT NULL CHECK (source IN
                            ('operator', 'narrator_stated', 'extracted', 'imported',
                             'document', 'migrated')),
    source_id           TEXT REFERENCES lr_sources(id),
    recorded_by         TEXT NOT NULL CHECK (length(trim(recorded_by)) > 0),
    asserted_by         TEXT NOT NULL CHECK (length(trim(asserted_by)) > 0),
    recorded_at         TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN
                            ('empty', 'needs_verify', 'operator_entered', 'conflicted',
                             'rejected', 'narrator_corrected', 'superseded')),
    supersedes_id       TEXT,
    superseded_by_id    TEXT,
    conflict_with_id    TEXT,
    CHECK (status <> 'superseded' OR superseded_by_id IS NOT NULL),
    CHECK (status <> 'conflicted' OR conflict_with_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_lr_assertions_proposition
    ON lr_assertions(narrator_id, subject_type, subject_id, concept_id, context_key);

-- Acceptance (§2.4): the explicit HUMAN decision of which account of one
-- proposition is accepted. Absent row = not adjudicated; competing accounts
-- stay linked until someone decides. No automatic ordering, ever.
CREATE TABLE IF NOT EXISTS lr_acceptances (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    subject_type        TEXT NOT NULL,
    subject_id          TEXT NOT NULL,
    concept_id          TEXT NOT NULL,
    context_key         TEXT NOT NULL DEFAULT '',
    accepted_assertion_id TEXT NOT NULL REFERENCES lr_assertions(id),
    decided_by          TEXT NOT NULL CHECK (length(trim(decided_by)) > 0),
    decided_at          TEXT NOT NULL,
    UNIQUE (narrator_id, subject_type, subject_id, concept_id, context_key)
);

-- Revisions: the audit of every write. base_revision is recorded, never the
-- rejection test (§3.10 — conflict is decided per path).
CREATE TABLE IF NOT EXISTS lr_revisions (
    id                  TEXT PRIMARY KEY,
    narrator_id         TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    revision            INTEGER NOT NULL,
    base_revision       INTEGER,
    changes_json        TEXT NOT NULL,        -- the applied change set, with previous values
    actor               TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    created_at          TEXT NOT NULL,
    UNIQUE (narrator_id, revision)
);
