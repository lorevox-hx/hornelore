# WO-04 — a home for every kind of life-history information

Design, 2026-09-20. **Nothing implemented.** Written from a full review of
every consumer of `SECTIONS` (client and server), the extractor's
validation and grouping paths, and the live database. Exact field
definitions and migration behaviour are below, per the ruling; the
decisions it encodes are the six ruled on 2026-09-20 plus the two
corrections.

Two acceptance boundaries, kept separate:

  A. SCHEMA AND DESTINATIONS — the new sections exist, persist, hydrate,
     render, edit, are proposed to by the extractor, and are chosen by
     entry in review. The anti-drift check runs in the normal suite.

  B. EXTRACTION INTEGRITY — the flagged values are shown to a person with
     their source and the reason they were flagged, and nothing is
     migrated, accepted, declined or deleted without that person.

---

## What the review found that the reconciliation did not

**1. The live database has no collisions — and no data.** No narrator's
`questionnaire_json` has a `military`, `faith`, `residence` or `travel`
key. No `profile_json` carries military or faith content. No `bio_facts`
row touches any of these topics. So there is **nothing to migrate**, and
the four sections start empty for everyone.

**2. But there IS a dead vocabulary for two of them.**
`bio_questionnaire_writer._apply_military` (:351) and `_apply_faith`
(:431), and `bio_questionnaire_view._military_section` (:505) and
`_faith_section` (:538), already exist — for a flat-dict intake shape
that no narrator ever populated. They are guarded by
`isinstance(section, Mapping)`, so **a repeatable (list) military section
makes them silent no-ops**: no error, no bio_facts, nothing. With the
fanout flag at 0 they never run today, but they are a trap for the day
it flips. They must be retired or rewritten in this work, not left.

**3. Adding a section flips the guard for the 20 automatically.**
`_destination_undefined` and the review surface both check the live
`SECTIONS`. The moment `military.branch` becomes a real field, Kent's
queued `military.branch = "Nike Ajax Nike Hercules missile site"` stops
being "cannot be added" and becomes actionable — one entry pick and one
click from his archive. **The schema work therefore cannot ship without
the review-set mechanism in the same commit.** This is the single most
important coupling in the work order.

**4. The extractor cannot tell two postings apart.** `_validate_item`
(extract.py:4465) strips every `[n]` index, so it always emits
`military.branch`, never `military[0].branch`. Then
`_group_repeatable_items` (:7491) groups by `.firstName` — a posting, a
home or a trip has none, so `len(name_items) <= 1` and **every item in
the answer collapses into `{section}_0`**. Two residences described in
one turn arrive as two `residence.place` proposals with no way to know
they are different homes. Acceptable for now — the review surface keeps
both outstanding (rule C2) and a person assigns each to an entry — but
the extractor will never propose a second entry on its own. Recorded;
fixing it is extraction work, boundary B.

**5. The extractor's own repeatable metadata is inconsistent.**
`residence.*` says `repeatable: "residences"` (plural — would never match
a section called `residence`). `military.deploymentLocation` and
`.significantEvent` are repeatable, `military.branch/rank/yearsOfService/
notes` are not. `faith.*` has no repeatable flag. `travel.significantTrip`
is flat while its siblings are repeatable. These have to be made
consistent with the sections defined below or the grouping code sorts
one posting's fields into two buckets.

**6. Eight places hardcode section lists and silently skip a new one.**
Ranked by damage if missed (full map in the appendix):

   1. `questionnaire_schema._EXPECT_ABSENT` lists `military.branch` and
      `residence.place` — adding them RAISES `SchemaUnavailable`
      process-wide. Loud, at least.
   2. `suggestion-review.js:53 REPEATABLE` is a hand copy of the server
      list — out of sync, the operator gets no entry picker and every
      accept 422s with no way forward.
   3. `suggestion-review.js:122 _entriesFor` labels entries by
      `relation, firstName, lastName, name, side, description` — every
      posting, home and trip renders as "(unnamed entry)".
   4. `bio-builder-core.js:711` and `_extractQuestionnaireCandidates`
      hardcode six sections — no candidates, no rehydration.
   5. `projection-map.js` `FIELD_MAP`/`REPEATABLE_TEMPLATES` — invisible
      to era-driven questioning and completeness.
   6. `session-loop.js:1016` would corrupt an array section into an
      object if the chat walk were ever extended to it.
   7. `interview.js:346,699` and `bio-builder-qc-pipeline.js:252` —
      no interview questions, no duplicate QC.
   8. `profile_seed.py` has no `residence`/`travel`/`faith` topic —
      Lori re-asks what she already knows.

---

## Exact field definitions

Conventions honoured, because tests enforce them: every `select` has
`""` as its first option (BUG-…-DEFAULT-AS-ASSERTION-01, asserted at
`test_bio_builder_save_sequences.js:588`); every repeatable section has
at least one `text`/`textarea` field (`:993`); the `id:` line keeps 4–6
space indentation (`test_single_questionnaire.js:47`); dates use
`inputHelper: "normalizeDob"` so an unknown date stays **blank** rather
than becoming explanatory text (ruling, decision 1).

### `military` — repeatable, `repeatLabel: "posting"`

    id                 label                          type      helper
    branch             Branch of service              text
    unit               Unit                           text      e.g. 32nd Artillery Brigade
    rank               Rank held                      text      during this posting
    serviceStart       Started                        text      normalizeDob  "YYYY-MM-DD or year; leave blank if unknown"
    serviceEnd         Ended                          text      normalizeDob
    location           Where stationed                text      normalizePlace
    role               Duties / role                  text      e.g. document courier
    notableEvents      Notable events / experiences   textarea
    notes              Additional notes               textarea

Why `branch` is `text`, not a `select`: a select would have refused
"Nike Ajax Nike Hercules missile site" at the form, which is attractive,
but this is a family archive and not every family's service was in one
country's five branches. The refusal belongs in extraction integrity
(boundary B), not in the form. ⚠ Flagged for the decision: a select with
`Other` is a defensible alternative.

Why `serviceStart`/`serviceEnd` rather than one `servicePeriod`: one
free-text period field is exactly where "temporal context implies short
stay, exact dates unknown" lands. Two normalised date fields cannot hold
that sentence.

Why `unit` exists: Kent's "32nd Artillery Brigade" is a unit, currently
misfiled as a community organisation. It needs a field that IS what it
is.

### `residence` — repeatable, `repeatLabel: "home"`

    id                 label                          type      helper
    place              Place                          text      normalizePlace  city, town or address
    periodStart        Moved in                       text      normalizeDob
    periodEnd          Moved out                      text      normalizeDob
    homeType           Type of home                   text      house, farm, apartment, base housing…
    memories           Memories of this home          textarea

Kept deliberately small. `hobbies.travel` is NOT reused for this — a
home and a trip are different facts.

### `travel` — repeatable, `repeatLabel: "trip"`

    id                 label                          type      helper / options
    destination        Destination                    text      normalizePlace
    year               When                           text      normalizeDateSafe  year or date; blank if unknown
    purpose            Purpose                        select    ["", "Vacation", "Work", "Family", "Military", "Pilgrimage", "Other"]
    companions         Who went                       text
    whatHappened       What happened on the trip      textarea
    notes              Additional notes               textarea

Three distinct things the ruling asked to keep apart: **where**
(`destination`), **why** (`purpose`, a closed list because "ate our first
Germany meal" is not a purpose), and **what happened** (`whatHappened`).
`hobbies.travel` stays as the existing free-text field; it is not
removed, and nothing maps into it.

### `faith` — FLAT, optional, label "Faith & Beliefs"

    id                 label                          type      helper
    denomination       Denomination or tradition      text      "Optional — leave blank if you'd rather not say"
    raisedIn           Raised in                      text      optional
    communityRole      Role in a faith community      text      choir, deacon, usher…
    significantMoments Significant moments            textarea
    notes              Additional notes               textarea

Every field optional; the section hint says so in the first sentence.
**Nothing infers a denomination from indirect context** — that is an
extraction rule for boundary B, recorded here so the form and the
extractor agree. Not placed under `technology` ("Technology & Beliefs").

⚠ Flagged, not decided: `technology`'s label "Technology & Beliefs" now
names a second home for beliefs. Renaming it to "Technology" is a
one-word change and a separate decision.

### Two additions to existing sections (corrections 1 and the marriage case)

    education.gradeLevel   Highest grade completed   text   "e.g. 8th grade, high school diploma"
        Placed AFTER `schooling`. Per correction 1: a grade level and a
        schooling history are different kinds of information. The
        existing "6th grade" suggestion is NOT rewritten to this path;
        it stays where it is until a person reviews it.

    marriage.marriagePlace   Where                   text   normalizePlace
        Placed AFTER `marriageDate`. Gives "Cathedral of the Holy Spirit"
        a field that is what it is, rather than prose in `weddingDetails`.
        ⚠ Not ruled on; proposed because the alternative is lossy.

### Retired extractor destination

    personal.notes   — removed from EXTRACTABLE_FIELDS (decision 4).
        ZZ's historical accepted value at that path is preserved as-is;
        its provenance row stays; nothing rewrites it. The queued
        Christopher suggestion "spent a lot of time with grandparents"
        stays queued and is flagged (below) for a person to re-home
        under `grandparents[].memorableStories` with the entry chosen.

Resulting counts, for the invariants: **20 sections, 11 repeatable,
118 fields** (91 + 9 + 5 + 6 + 5 + 1 + 1). These replace
`_EXPECT_SECTIONS/_REPEATABLE/_FIELDS` and are re-measured, not assumed,
by the test that reads the file.

---

## Migration behaviour for existing records

**Questionnaires: none.** No stored document has these keys. A section
absent from a document renders empty; `getSectionData` returns `null`;
`_sectionFillCount` returns 0. The first save that adds an entry writes
`military: [{...}]` through the ordinary `_write` path, which handles a
new top-level array key with no special casing (`_set` pads; verified).

**Provenance and reviews: none.** Both tables key on `section` as a
string and `identify_path` is section-agnostic (verified). New sections
get rows the ordinary way.

**The 20 pending suggestions: intact, and flagged — never moved.**
Per the ruling, none is migrated, accepted, declined or deleted. But
per finding 3 above, leaving them *unmarked* is itself a change in
behaviour: the destination appearing makes them one click from the
biography. So this work adds a review set:

    CREATE TABLE suggestion_flags (
      person_id       TEXT NOT NULL,
      section         TEXT NOT NULL,
      entry_id        TEXT NOT NULL DEFAULT '',
      field           TEXT NOT NULL,
      value_hash      TEXT NOT NULL,          -- same canonical form as 0060
      field_path      TEXT NOT NULL,          -- verbatim, for legacy rows with no id
      proposed_value  TEXT NOT NULL,          -- verbatim
      reason          TEXT NOT NULL,          -- see codes below
      source_note     TEXT,                   -- where the evidence is, if known
      flagged_at      TEXT NOT NULL,
      flagged_by      TEXT NOT NULL DEFAULT '',
      PRIMARY KEY (person_id, section, entry_id, field, value_hash),
      FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
    );

Reason codes, from the reconciliation's review set:

    value_not_a_<field>     the value is not the kind of thing the field
                            holds (a place in a years field, an
                            installation in a branch field)
    model_uncertainty       the model's own hedging stored as a value
                            ("temporal context implies…")
    misclassified_section   right kind of fact, wrong section (a military
                            unit filed under community)
    queued_before_home      queued before its destination existed; review
                            with care (applied automatically to every
                            legacy row whose destination this work creates)

The review surface adds a third group — **"Needs review"** — above
"Cannot be added": card shows the proposal, the reason in plain words,
the source note, and offers **Decline**, **Re-home** (choose a different
destination and entry), or **Accept anyway** behind a confirmation that
repeats the reason. Accept is never one click for a flagged row.

**Seeding the flags is a reviewed step, not an automatic one.** This
work produces the proposed list — the nine values and their reason codes
from the reconciliation, plus `queued_before_home` for all twenty —
as a script that PRINTS what it would insert and inserts nothing until
run with `--apply` after a person has read the list. The
`queued_before_home` flag needs no judgement and can be applied to all
twenty; the nine specific reasons are the reconciliation's opinion and a
person confirms each.

**Extractor vocabulary: cleaned in the same commit.** `residence.*` →
`repeatable: "residence"`; all `military.*` → `repeatable: "military"`;
all `travel.*` → `repeatable: "travel"`; `faith.*` flat;
`military.yearsOfService` replaced by `military.serviceStart` and
`military.serviceEnd`; `military.unit` added; `travel.whatHappened`
added; `personal.notes` removed; `family.marriageDate` and
`family.marriagePlace` re-pointed to `marriage.marriageDate` and
`marriage.marriagePlace`. Labels updated to match the form.

---

## The anti-drift check — decision 5, refined

One test, in the normal suite, reading the schema from the file that
renders the form (`questionnaire_schema.load_schema`, already built and
self-validating). It checks THREE things, not string equality:

1. **Canonical destination.** For each `EXTRACTABLE_FIELDS` key, the
   `(section, field)` after `split_destination` must be defined by the
   questionnaire — or be listed in `NON_QUESTIONNAIRE_DESTINATIONS` with
   an owner (see 3).

2. **Repeatable agreement.** If the questionnaire section is repeatable,
   the extractor entry must carry `repeatable: "<same section id>"`; if
   the section is flat, it must not. This is the check that would have
   caught `"residences"` and the half-repeatable military entries.

3. **Explicit owners for anything else.** A set in `extract.py`:

       NON_QUESTIONNAIRE_DESTINATIONS = {
           # path: (owner, where the information goes instead)
       }

   Empty after this work if the decisions hold. Any extractor path that
   is neither defined nor listed here fails the test, naming the path.
   Each entry is itself tested: the owner string must be non-empty and
   the path must NOT be questionnaire-defined (an entry that becomes
   defined must be removed — the allowlist cannot rot).

4. **A burn-down list, so adoption does not block on the other 57.**
   `EXTRACTABLE_FIELDS` has ~100 paths the form does not define. This
   work resolves 43 (military 6, residence 4, travel 4, faith 5,
   marriage 3, `family.children.*` 8 and `family.spouse.*` 11 as pure
   renames to `children.*`/`spouse.*`, `education.gradeLevel`,
   `personal.notes`). The remaining ~57 — `community.*` (9),
   `greatGrandparents.*` (11), `health.*` (6), parent/sibling/grandparent
   extras (14), `family.grandchildren.*`/`priorPartners.*` (7),
   `laterYears.*` (3), `personal.nameStory`, `cultural.*`, `hobbies.notes`,
   `education.notes/readingAbility/training` — go in a `KNOWN_DRIFT`
   dict with a one-line disposition each. The test is red only for a
   path in neither set. `KNOWN_DRIFT` shrinks; it may not grow without a
   disposition.

⚠ The `family.children.*` and `family.spouse.*` renames are pure
vocabulary but not trivial: the extractor's field names differ from the
form's (`dateOfBirth` vs `birthDate`, `notes` vs `narrative`). Listed as
in-scope because the test forces a disposition; each field pair needs a
line in the same commit.

What the check cannot catch, stated so nobody relies on it: a value that
does not match its own field. That is boundary B.

---

## Boundary B — extraction integrity, scoped

Separate work order, coordinated with A. This document only fixes its
scope so the two cannot be confused:

- the `suggestion_flags` table and "Needs review" group (built in A,
  because A's schema change makes them necessary)
- `_validate_item` gains type-shape checks for date-like fields: a value
  containing "unknown", "implies", "context", "approximately" in a field
  with `normalizeDob` is rejected with reason `model_uncertainty` and
  logged, never queued
- `_group_repeatable_items` learns non-person grouping keys (`place`,
  `destination`, `unit`) so two homes in one answer are two groups
- the denomination rule: `faith.denomination` is proposed only from an
  explicit statement, never from a church name, a wedding venue, or a
  holiday
- the nine specific flagged values get their reasons confirmed or
  corrected by a person, and each gets a disposition

None of the twenty is touched by B either. B changes what the extractor
will do NEXT time.

---

## Everything that changes in the schema commit

Listed so the commit can be checked against it. From the consumer map;
the appendix has line numbers.

    ui/js/bio-builder-questionnaire.js      SECTIONS: 4 new sections, 2 new fields
    ui/js/suggestion-review.js              REPEATABLE (:53) — derive from server or import;
                                            _entriesFor (:122) — add branch, unit, place,
                                            destination, year, periodStart as label fields;
                                            third group "Needs review"
    ui/js/bio-builder-core.js               :711 hardcoded list — derive from SECTIONS
    ui/js/projection-map.js                 REPEATABLE_TEMPLATES + FIELD_MAP entries
    ui/js/interview.js                      :346, :699 — extend or document exclusion
    ui/js/bio-builder-qc-pipeline.js        :252 — n/a for non-person sections; comment
    ui/js/session-loop.js                   :1016 — guard against writing into an array
    server/.../questionnaire_schema.py      _EXPECT_* re-measured; _EXPECT_ABSENT rows
                                            for military/residence removed; docstring
    server/.../suggestion_review.py         REPEATABLE_SECTIONS += military, residence, travel
    server/.../routers/extract.py           EXTRACTABLE_FIELDS vocabulary per above;
                                            NON_QUESTIONNAIRE_DESTINATIONS; KNOWN_DRIFT
    server/.../bio_questionnaire_writer.py  _apply_military, _apply_faith retired
                                            (dead vocabulary; would silently no-op)
    server/.../bio_questionnaire_view.py    _military_section, _faith_section retired
                                            (emit a flat shape under a now-list key)
    server/.../profile_seed.py              TopicDefinition for residence, travel, faith
    server/.../prompt_composer.py           :1488 reads military as dict — guard or adapt
    server/code/db/migrations/0061          suggestion_flags
    server/.../narrator_data_inventory.py   suggestion_flags lane (AUTHORITATIVE, portable)
    tests/test_suggestion_review.py         :828-830, :843-844 re-measured
    tests/test_suggestion_queue_persistence.py  :392-398
    tests/test_bio_builder_save_sequences.js    :667-674 (16 → 20)
    tests/test_single_questionnaire.js          :59 (16 → 20)
    tests/test_extractor_vocabulary.py      NEW — the anti-drift check
    scripts/seed_suggestion_flags.py        NEW — prints; --apply only after review

---

## What this work order does NOT do

- Touch any of the 20 pending suggestions beyond flagging them, and the
  flags are inserted only after a person reads the list.
- Rewrite `education.gradeLevel = "6th grade"` to the new field
  (correction 1).
- Treat the nine as established false facts (correction 2). They are a
  review set with reasons; a person decides.
- Fix `_group_repeatable_items` or `_validate_item` (boundary B).
- Enable the bio_facts fanout. The retired appliers are removed so the
  flag cannot be flipped onto a silent no-op; array-aware appliers are
  the fanout work's problem.
- Rename "Technology & Beliefs" (flagged).

## Decisions still open

1. `military.branch`: free text (proposed) or select-with-Other?
2. `marriage.marriagePlace`: add it (proposed), or leave the place in
   `weddingDetails` prose?
3. "Technology & Beliefs" → "Technology"?
4. Confirm the `suggestion_flags` shape and the four reason codes.
5. Confirm that `queued_before_home` may be applied to all twenty
   without per-row review, since it states a fact rather than a
   judgement.

---

## Appendix — consumer map, file:line

Client, generic (no change): `bio-builder-questionnaire.js` :1136
`_renderQuestionnaireTab`, :1164 `_renderSectionDetail`, :1089
`_sectionFillCount`, :1493 `_saveSection`, :1814 `_addRepeatEntry`, :157
`getSectionData`, :1778 `_afterConfirmedSave`; `bio-builder.js` :96, :729,
:807. `_saveSection` mints `_entryId` at :1687 for any section with
content; `_addRepeatEntry` matches by id at :1814 and never mints.

Client, hardcoded: `bio-builder-questionnaire.js` :921
`_extractQuestionnaireCandidates` (six `if sectionId ===` branches), :788
`_hydrateQuestionnaireFromProfile` (personal/parents/siblings only);
`bio-builder-core.js` :711; `session-loop.js` :438, :1016, :1053;
`bio-builder-qc-pipeline.js` :252; `interview.js` :346, :699;
`projection-map.js` :46 `FIELD_MAP` (25 paths, 6 sections), :291
`REPEATABLE_TEMPLATES` (3), :378 `getWriteMode` falls through to
`suggest_only`; `suggestion-review.js` :53, :110, :122.

Server: `questionnaire_persistence.py` :219 `flatten_document`, :177
`_set` — generic, verified. `answer_provenance.py` `identify_path` —
generic, verified. `bio_questionnaire_writer.py` :351, :431, dispatch
:520-618 hand-written, no registry. `bio_questionnaire_view.py` :505,
:538, assembled :620-641 (note `"spouses"` vs `"spouse"`, pre-existing
drift). `prompt_composer.py` :1361-1368, :1488-1498 (`isinstance(military,
dict)`), :3289. `profile_seed.py` :310-322 (military topic;
`servicePeriod` vs `yearsOfService` pre-existing drift). `extract.py`
:198 `EXTRACTABLE_FIELDS`, :301-304, :330-335, :338-342, :365-368
(quoted in the reconciliation), :428 `PROTECTED_IDENTITY_FIELDS`, :452
`FRAGILE_FIELD_EXACT`, :472 `FRAGILE_FIELD_PREFIXES` (none reference
these sections), :4444 `_validate_item`, :4465 index strip, :7476
`_group_repeatable_items`, :7491 `.firstName` grouping.

Templates: `ui/templates/*.json` enumerate sections but the loader was
retired 2026-09-17; documentation-only.

Tests that break on a new section: `test_bio_builder_save_sequences.js`
:588 (select first option), :667-674, :993; `test_single_questionnaire.js`
:47, :59; `test_suggestion_review.py` :828-844, :870; 
`test_suggestion_queue_persistence.py` :392; `test_bb_questionnaire_meta.js`
:36 (do not move the `SECTIONS` declaration or the Phase-2 banner).
