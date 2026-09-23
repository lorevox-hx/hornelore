# WO-BIOGRAPHICAL-MODEL-01 — one biographical model

**Design for approval. Nothing implemented, no data changed.**

Supersedes nothing yet. Evidence base:
[`docs/BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md`](../BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md)
(63 questionnaires measured) and
[`BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md`](BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md),
which is corrected **independently of this work order** and must not wait for it.

---

## Mission alignment

A narrator's life is recorded once and must be usable everywhere — by the
operator entering it, by Lori in conversation, and by the memoir. Today the
same fact has up to four names and lives in one of two stores that each hold
half the population. That is not untidiness; it is why a narrator's own
children were invisible to the system deciding what to ask her about.

## Non-regression requirements

This WO MUST NOT:

- reduce narrator dignity
- introduce new `must_not_write` violations or system-tone outputs
- regress the CURRENT locked baseline without explicit justification (name
  the baseline and its scorer; a pass-count delta across a scorer change
  measures the scorer)
- expand operator surfaces into narrator UI
- add detectors that duplicate existing signals
- **lose a single stored value.** 63 questionnaires and 62 bio-fact records
  exist. Every migration step is additive and reversible until the final one.

## Lori impact (Tier 3)

Response length, questions per turn (≤1), tone and pacing: **unchanged by
design.** This work order changes where facts live, not how Lori speaks. The
one intended behavioural change is that she stops asking for facts already
recorded — which is the locked principle, not a new feature.

## Narrator dignity check

- **Operator seeds known structure; Lori reflects what is there.** The
  measured failure — Profile Seed would ask a narrator whether she has
  children while three sons sit in her record — is a direct breach. This WO
  exists to close it.
- **No interrogation loop.** Nothing here adds a "next field to ask"
  mechanism. More fields available to an operator is not more questions put
  to a narrator.
- **Mechanical truth must visibly project.** The death-status defect is the
  reference case: stored in three places, reaching no narrator-facing
  surface.

## Flags / gating (Tier 5)

Every stage is flag-gated and default-off. No stage changes behaviour until
its flag is turned on, and each can be turned off again without data loss.
Names proposed in §7.

---

## 1. The finding that determines the design

| | questionnaire only | `bio_facts` only | both |
|---|---:|---:|---:|
| test population (`hornelore_data`) | **43** | **45** | 17 |
| production (`lorevox_data`) | 3 | 0 | 0 |

**Neither store holds the population.** Declaring the questionnaire
authoritative strands 45 narrators; declaring `bio_facts` authoritative
strands 46. The 17 with both are where two truths already exist for one
person.

So the question is not *which store wins*. It is: **one model, and both
existing stores migrate into it.**

Two further measured facts shape it:

- **Profile Seed cannot read the questionnaire at all** — the string
  `questionnaire` does not occur in `profile_seed.py`. It reads 25
  `profile_json` paths and 25 `bio_facts` keys.
- **`load_facts` traverses the questionnaire generically**, with no
  allowlist. So the questionnaire → Lori path is cheap to extend, while the
  questionnaire → Profile Seed path does not exist.

## 2. Design principles

These decide disagreements later in the document.

1. **One fact, one home.** Every biographical fact has exactly one
   authoritative location. Everything else is derived and may be rebuilt
   from it at any time. Two stores that can disagree is the defect.
2. **A person is a record, not a name in a section.** Identity is a stable
   id. Names, relationships and status attach to the person.
3. **Derived is computed, never stored twice.** Counts, indexes and
   projections are recomputed, not written into a second table that drifts.
4. **Omission is never deletion.** Already enforced in
   `merge_whole_document` and now in the graph; the same rule governs every
   new path.
5. **Unknown is a value.** Blank stays blank. Nothing infers an answer from
   an absent one — the `military.served` defect in miniature.
6. **The full text a person typed is authoritative; every decomposition is
   secondary** and is recorded only when supplied, never derived by parsing.

## 3. The model

### 3.1 People

A single `people[]` collection holds every human in the record — **the
narrator included**, distinguished only by `isNarrator`. This ends the
narrator/relative asymmetry by construction rather than by adding four
fields to one section.

```
people[]
  id                 stable; today's `_entryId` becomes this
  isNarrator         bool
  name
    full             AS ENTERED — authoritative, never parsed
    given[]          optional, supplied not derived   (handles two middle names)
    family           optional, the complete surname   (handles "la Plante Horne")
    prefix[] suffix[]
    birthFamily      maiden/birth surname — available to the NARRATOR too
    forms[]          spelling variants of the same name ("la Plante"/"Laplante")
    alsoKnownAs[]    different names, with `use` (birth, married, nickname)
    pronunciation    optional spoken form; never alters the written name
  birth  { date: EDTF, place }
  death  { status: living|deceased|unknown, date: EDTF, place }
  attributes { occupation, birthOrder, ... }
  notes[]            narrative, signposted not inlined
```

`forms[]` and `alsoKnownAs[]` are deliberately different, per GEDCOM X: a
spelling variant of one name is not a second name. **Neither ever mints a new
person id.**

`death.status` answers the review's correction directly: the status belongs
to the person it describes, carrying that person's identity. There is no
unqualified `deceased` key anywhere.

### 3.2 Relationships

```
relationships[]
  from, to           person ids
  type               parent | child | sibling | spouse | partner | grandparent | ...
  subtype            biological | adoptive | step | half | foster | ...
  period             { start: EDTF, end: EDTF }   — a marriage that ended
  attributes         { howMet, marriagePlace, ... }
```

This makes explicit what the questionnaire cannot currently say: **which
parents a child has** (the review's point), co-parents, a spouse referenced
by identity rather than by the free-text `spouseReference`, and relationships
that changed over time.

`graph_persons` / `graph_relationships` then become a **projection** of this,
not a parallel store maintained by a sync that can delete.

### 3.3 Dates

One representation: an **EDTF Level 1** string. `1939-08-30`, `1939-08`,
`1939`, `1939?` (uncertain), `1939~` (approximate), `1920/1935` (interval),
empty (unknown). One field name — `date` — everywhere; the
`dateOfBirth`/`birthDate` split disappears.

### 3.4 Life content

The remaining sections keep their current character and stop carrying people:

`residences[] · education[] · work[] · military[] · unions[] · pets[] ·
travel[] · traditions[] · memories · faith · health · technology ·
laterYears · hobbies · notes`

Plus a narrator-only `identity` block for self-description:
`pronouns · heritage[] · languagesAtHome[] · faithRaisedIn · faithCurrent ·
currentResidence · nameOrigin`. These are §10-A of the audit — the gaps the
test population proves people answer — and they are **optional and
self-described**. Census definitions inform what the field *means*; nothing
inherits census wording.

`military` gains an explicit tri-state `status: served|did not serve|unknown`
alongside the repeatable postings, replacing the orphan boolean.

## 4. Crosswalk (first draft)

One row per concept. Full version to be generated as a committed
machine-readable mapping in Stage 0 — this is the shape and the decided rows.

| concept | questionnaire today | Operator Intake | `profile_json` | `bio_schema` | proposed home | reaches Lori today |
|---|---|---|---|---|---|---|
| narrator name | `personal.fullName` | `personal.fullName` | `personal.fullName`, `basics.fullname` | `full_legal_name` | `people[isNarrator].name` | yes |
| narrator birth date | `personal.dateOfBirth` | `personal.dateOfBirth` | `personal.dateOfBirth`, `basics.dob` | `birth_date` | `people[].birth.date` | yes |
| relative birth date | `parents[].birthDate` | — | `parents[].dateOfBirth` | `mother_birth_year` | `people[].birth.date` | yes |
| **relative living/deceased** | `parents[].deceased` | — | `kinship[].deceased` | **none** | `people[].death.status` | **NO** — BUG-LORI-UNAWARE-OF-DEATH-01 |
| maiden / birth surname | `parents[].maidenName` (relatives only) | — | `parents[].maidenName` | `mother_maiden_name` | `people[].name.birthFamily` (all) | yes |
| pronouns | **none** | `personal.pronouns` | `personal.pronouns` | — | `identity.pronouns` | no |
| current residence | **none** | `personal.currentResidence` | `personal.currentResidence` | `current_residence` | `identity.currentResidence` | no |
| heritage / ancestry | `grandparents[].ancestry` | `faith.ethnicityHeritage` | `personal.culture` | `ethnicity_heritage` | `identity.heritage[]` | partial |
| languages at home | **none** | `faith.languagesAtHome` | `personal.languagesAtHome` | `languages_spoken_home` | `identity.languagesAtHome[]` | no |
| faith raised / current | `faith.raisedIn`, `faith.denomination` | `faith.religionRaised`, `faith.currentFaith` | `personal.faithRaised`, `personal.currentFaith` | `religion_raised`, `current_faith` | `identity.faithRaisedIn`, `identity.faithCurrent` | partial |
| highest education | `education.schooling` (prose) | `education.highestLevel` | `education.highestLevel` | `highest_education_level` | `education[].level` | partial |
| career | `education.careerProgression` | `education.primaryCareer` | `basics.career` | `primary_career` | `work[]` | partial |
| military served | orphan `military.served` | `military.served` | `military.served` | `military_served` | `military.status` | via fact only |
| marriage year | `marriage[].marriageDate` (unused) | — | `spouses[].yearMarried` | `marriage_year` | `relationships[type=spouse].period.start` | partial |
| children | `children[]` | `children[]` | `children[]` | `children_count`, `children_named` | `people[]` + `relationships[]`; counts **derived** | yes |
| living situation | **none** (`today` orphan) | `today.livingSituation` | `today.livingSituation` | — | `identity.currentResidence` / `health` | no |

**Ambiguous rows needing your decision** are marked in Stage 0's output, not
resolved here: whether `grandparents[].culturalBackground` is the same
concept as `identity.heritage[]`; whether `hobbies.travel` and the `travel[]`
section are one thing; whether `today.healthConsiderations` belongs to
`health`.

## 5. What this does and does not fix

**Fixes, by construction:** narrator/relative name asymmetry · no maiden name
for the narrator · two middle names · compound surnames · spelling variants
splitting identity · children with no stated parents · `spouseReference` as
free text · the same person duplicated across sections · `dateOfBirth` vs
`birthDate` · singular/plural section pairs · the orphan `military.served` ·
status belonging to a person.

**Does not fix on its own:**

- **Profile Seed's blindness.** It reads 25 `profile_json` paths and 25
  `bio_facts` keys. Stage 3 points it at the derived index; until then, a
  richer document changes nothing for it.
- **Whether a value survives prompt assembly.** `load_facts` traverses
  generically, but `STORY_FIELDS` are signposted rather than inlined and no
  measurement yet establishes that every value reaches every turn. A
  delivered-prompt measurement is owed and is **not** part of this WO.
- **Memoir, story candidates, Life Map.** Unexamined. Named in the audit §8.

## 6. Migration — additive, reversible, no big bang

Nothing is deleted until the final stage, and every stage is readable by the
previous code.

- **Stage 0 — write the mapping, change nothing.** The crosswalk as a
  committed machine-readable file, plus a test that every stored key in all
  63 questionnaires and all 62 bio-fact records maps to exactly one concept.
  **Unmapped keys fail the test.** This is where the ambiguous rows get
  decided by a person.
- **Stage 1 — `people[]` and `relationships[]` alongside.** Derived from the
  existing sections; both written; reads prefer the new. `_entryId` becomes
  the person id, so the ids already minted this week carry over. The old
  sections remain intact and authoritative until Stage 4.
- **Stage 2 — one write path.** Operator Intake and Bio Builder become two
  views over the same document. The fourth vocabulary disappears here.
- **Stage 3 — `bio_facts` becomes derived.** Recomputed from the document;
  the 45 `bio_facts`-only narrators are migrated into it **once**, with a
  refusal on any value that cannot be mapped. Profile Seed then reads the
  index and can finally see a questionnaire answer.
- **Stage 4 — retire the legacy section shapes.** Only after Stages 1–3 have
  run against all 63 records with byte-comparable exports before and after.

**Acceptance for every stage:** export each affected narrator before and
after and compare `EQUIVALENT`. The portable-narrator round trip already
exists and is the natural harness — it is what proved the family packages.

## 7. Flags

`HORNELORE_BIO_MODEL_PEOPLE` (Stage 1 read/write) ·
`HORNELORE_BIO_MODEL_SINGLE_WRITE` (Stage 2) ·
`HORNELORE_BIO_FACTS_DERIVED` (Stage 3). All default `0`. Stage 4 removes
code rather than flipping a flag.

Note the existing pair: `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ` is currently
`0` on both machines to match the data. Stage 3 is what finally makes `READ=1`
correct rather than harmful, because the index would then be derived from the
document rather than a separate half-populated store.

## 8. Explicitly not proposed

Adopting FHIR, GEDCOM X or EDTF as frameworks — only their decided questions.
A larger form. Any new prompt or interview behaviour. Any change to Lori's
voice. Migrating or editing a family record outside a flag-gated,
round-trip-verified stage. Adding a field because a standard contains one.

## 9. Open questions for Chris

1. **Is the person model the right target**, or should this be the smaller
   change — fix names, dates and the missing fields in place, and accept that
   a child still cannot state who their parents are?
2. **Stage 3 is the load-bearing one.** Deriving `bio_facts` from the
   document means Operator Intake stops writing canonical truth directly. Is
   that acceptable, given intake is the fast path for a new narrator?
3. **The 17 narrators with both stores** will have conflicts. Should Stage 0
   surface them for adjudication, or should the questionnaire win by rule?
4. **Pronunciation** — worth a field, or over-building? It matters for a
   spoken product and for `la Plante`, and it is the one item here with no
   supporting evidence in the stored data.
