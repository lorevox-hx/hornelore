# WO-LIFE-RECORD-01 — the life record, and its contract with Hornelore

**Revision 3 · 2026-09-22 · DESIGN ONLY — nothing implemented, no data changed.**

**Revision 3 removes implementation ambiguity; it does not reopen the
design.** Five contracts settled in place: who owns the narrator's actual
words (§2.6) · how places and events cross the domain boundary (§2.7) · what
rejects a write (§3.10 — per path, not per revision) · a bounded selection
rule for required facts (§9.1) · and the acceptance scope for memoir
attribution (§9.2). The concept catalog is specified in full at
[`docs/specs/LIFE-RECORD-CONCEPT-CATALOG-v1.md`](../specs/LIFE-RECORD-CONCEPT-CATALOG-v1.md).

**It also corrects a framing error both earlier revisions carried.** They
treated the event model as the source of Hornelore's chronology. **Hornelore
already has a chronological spine — the narrator's DOB anchors a life-span
scaffold and the seven eras are built forward from it.** §2A replaces the
"event spine" with four temporal layers and a DOB contract; the open question
in §12 is reframed accordingly. Three validator defects found by external
review are fixed and now carry mutations (§10).

Supersedes `WO-BIOGRAPHICAL-MODEL-01_Spec.md` (a migration plan) and
`WO-LIFE-RECORD-MODEL-01_Spec.md` (a model without a questionnaire), and
merges the independent parallel proposal of the same date.

**Revision 2 is a rewrite, not a patch.** Revision 1 designed a biographical
model in isolation. The repository review
([part 1](../REPO-REVIEW-2026-09-22.md) ·
[part 2](../REPO-REVIEW-2026-09-22-PART-2.md)) showed the model was the easy
half: the hard problem is the **contract between that model and the rest of
the product**. Section 2 is new and is now the centre of the document.

Evidence: [field audit](../BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md) ·
[death defect](BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md) · both review parts.
Design rules are verified by
[`scripts/design/validate_life_record_design.py`](../../scripts/design/validate_life_record_design.py)
— 17 rules, 8 situations, 9 refusals.

---

## Mission alignment

The narrator is the author of their own story. This record holds a life —
people, places, what happened, and what the narrator made of it — in a shape
Lori can speak from honestly, an operator can fill without interrogating
anyone, and a memoir can draw on without misrepresenting who said what.

## Non-regression requirements

MUST NOT: reduce narrator dignity · introduce `must_not_write` violations or
system-tone outputs · regress the CURRENT locked baseline without naming the
baseline and its scorer · expand operator surfaces into narrator UI · add
detectors duplicating existing signals · **turn more structure into more
questions** · lose a narrator's own words · **bypass an existing review gate
by arriving through a new door**.

## Lori impact (Tier 3) · dignity check

Response length, questions per turn (≤1), tone, pacing: unchanged. Intended
changes only: she knows who is alive, uses people's actual names, and stops
asking for what is recorded. Against the locked principles — **operator
seeds, Lori reflects**; **mechanical truth must visibly project**; **no
interrogation loop** (§8.1).

---

## 1. Corrections carried forward

Stated first so no superseded claim survives into implementation.

| earlier claim | corrected |
|---|---|
| "Travel writes biography" | **False.** `trip_bio_suggestions` is a dead stub — hardcoded `field_key="travel.trip"`, not a real key, blocked by an FK to `bio_fields`, read by nothing |
| "`bio_schema` is an asking vocabulary, not a rival store" | **Both.** It defines the `field_key`s `bio_facts` uses *and* carries `narrative_value` / `life_stage_range` / `asking_anchors` |
| "Eight stores of biographical truth" | **Wrong framing.** They have different authorities — §2.1 classifies them |
| "Adding a questionnaire field automatically reaches Lori" | **False at the prompt boundary.** `saved_biography` has `drop_order 35` and is shed under budget |
| "Conflict surfacing would be new" | Partly exists — `biography_conflicts`, and "the questionnaire WINS on conflict with `profile_json`" |
| "Counts must be derived" | **Wrong.** A stated count is a sourced assertion (§5) |
| Person identity shared across narrators | **Narrator-scoped** (§6) |

---

## 2. The contract — the actual hard problem

### 2A The temporal architecture — Hornelore already has a spine

**Revision 3 corrects a framing error that ran through both earlier
revisions.** They treated the event model as though it had to *provide*
Hornelore's chronology. It does not. **The narrator's date of birth already
anchors a life-span scaffold, and the seven-era framework is built forward
from it** — the repository review found that without DOB there is no spine at
all. Replacing that with an "event spine" would displace something the
product already does well, and would tempt every part of a life into becoming
an event.

So there is no event spine in this design. There are **four temporal layers**,
and the occurrence model is the second, not the first.

| layer | what it is | who owns it |
|---|---|---|
| **1 · life-span scaffold** | DOB → endpoint. The existing framework | resolved at render, never stored |
| **2 · occurrences and periods** | weddings, moves, deaths; residences, jobs, service | the life record (§3.5) |
| **3 · reviewed chronology / Life Map** | what an operator confirmed belongs where | `story_projection`, unchanged |
| **4 · stories and meaning** | memories, reflections, lessons | `story_candidates` + curation (§2.6) |

Layer 2 never competes with layer 1, but it is **not contained by it**.
*(Corrected 2026-09-22 — this said layer 2 lives "inside" layer 1, which is
wrong and would have been built.)* **A parent's birth, a grandparent's war
service and family history all precede the narrator's own birth, and they
belong in the biography.** What layer 1 anchors is *the narrator's* life
span, not the bounds of what may be recorded. An occurrence whose subject is
someone else may fall anywhere; an occurrence is placed on the narrator's
scaffold only when it belongs to the narrator's life, and even then only by
promotion.

Layer 3 is reached only by promotion (§2.5). Layer 4 may reference any of the
others, several, or none — and referring to a fact never turns a story into
one.

#### The DOB contract

> **The narrator's accepted birth-date assertion is the structural start
> anchor for the life-span scaffold. `person.birth.date` is one semantic
> concept applicable to any person; UI sections and legacy paths bind
> subjects to that concept. The narrator's instance carries the additional
> role of supplying the life-span start. The current date supplies the
> dynamic endpoint for a living narrator; a known death date supplies it for
> a deceased one. Approximate or missing dates remain approximate or
> missing. No date is invented to make the scaffold work.**

Consequences, each with an executable check:

- **A pointer, not a copy.** `person.birthEventRef` names the canonical birth
  occurrence; the date lives on the occurrence (§3.8). The resolver walks
  `narrator_person_id → birthEventRef → date` rather than searching events.
  A parent, child or sibling uses the identical structure.
- **The role is not a second field.** There is no `narrator_dob`. The
  narrator's DOB is the same concept as their sibling's, with one extra
  projection: *when subject == narrator, supplies `life_span.start`*.
- **The shipped span has NO end, and this design keeps it that way for a
  living narrator.** *(Corrected 2026-09-22 against the code — checkpoint
  §3.3b. This bullet said the endpoint was "computed at render". It is not:
  `later_years` is `ageEnd: null` (`lv-eras.js:95`), `chronology_accordion.py`
  never calls `date.today()`, and "Today" is a separate bucket that
  birth-year arithmetic never produces (`:136-152`). The design was
  describing a feature the product does not have.)* So: a living narrator's
  span is **open** — decision **D5** in the checkpoint — and nothing is ever
  written as an endpoint.
- **What this design ADDS is truncation at a known death date, and only
  that.** Today `dateOfDeath` is an anchor and truncates nothing
  (`chronology_accordion.py:564`, `:591`, `:604`). **Deceased with a known
  date** will end there. **Deceased with an unknown date** ends nowhere and
  is *marked* — the span is not falsely extended, which is the
  death-awareness defect in its temporal form.
- **Where the scaffold reads DOB from is `profile_json`, not the
  questionnaire.** `chronology_accordion.py:1022` reads `basics["dob"]`; the
  questionnaire's `personal.dateOfBirth` is only a Lane B anchor (`:599-605`)
  and never enters the span. The two can disagree today and the eras follow
  the profile. Under this design the scaffold reads the **accepted birth
  assertion** through `birthEventRef`, and `profile_json` becomes a
  projection of it — one source, not two.
- **Age arithmetic is the shipped `life_spine.validator.compute_age`**
  (`validator.py:110-130`, month/day comparison), not a new function — the
  product already has a correct one and a deliberately year-only one
  (`age_arithmetic.py:141`). The design adds a third only to bound a coarse
  date honestly, by calling the same function at the year's two extremes.
- **No DOB, no spine.** A missing birth date yields an unavailable scaffold,
  never a default.
- **Uncertainty propagates, it does not stop at storage.** *"Around 1945"*
  stays `1945~`. An age derived from an approximate birth renders as
  *"about 20"*, never *"20 years, 3 months"*.
- **Conflicting DOBs are one concept with disagreeing assertions** — never
  two people and never two fields. The scaffold reads the assertion named by
  an **explicit, recorded acceptance decision** (`acceptedAssertionId`), and
  the competing one is retained. **It must never infer acceptance from a
  status name.** `operator_entered` and `narrator_corrected` describe how a
  value arrived and which write policy admitted it; neither says whose
  account was accepted, and ordering by them would let an operator's typo
  outrank the narrator correcting it. **Two live assertions and no recorded
  decision means the scaffold is UNRESOLVED** — which is reported, not
  guessed around.
- **Ages are calendar arithmetic, not year subtraction.** Born 30 August
  1939, on 12 June 1971 she is **31**, not 32. Where month and day are not
  known on both sides the honest answer is *"31 or 32"*.
- **Calendar chronology is not narrative placement.** Knowing the DOB tells
  you the narrator was 32 in 1971. It does not tell you which chapter of
  their life they think 1971 belongs to. An era is still never derived — now
  explicitly not from an age either.

### 2B Where the data physically lives — open, and measured

**SQLite stays.** Nothing found argues otherwise: the person–relationship–
event model is ordinary relational work, foreign keys enforce the references
this design depends on, and a document store would not resolve a single one
of the measured problems — competing authorities, 146-against-118 field
drift, undelivered suggestions. **Those are contract problems, and an engine
cannot have an opinion about them.** MongoDB appears nowhere in this
repository and this is not a reason to introduce it.

**What is genuinely open is one database or one per narrator**, and the
record needs correcting before that is decided:

- **No per-narrator-database decision exists in this repository.** No
  `docs/decisions/` entry, no work order, no design note.
- **Today there is one shared database.** `db.py:77` computes a single
  module-level `DB_PATH = DATA_DIR / "db" / "lorevox.sqlite3"`; `_connect()`
  opens that one file; all narrators are rows in it.

So adopting per-narrator databases would be **a new and large migration**,
not the preservation of an earlier choice. Measured cost:

| | |
|---:|---|
| **30** | `sqlite3.connect` call sites outside `db.py` — `trips.py` ×2, `import_repository`, `import_provenance`, `narrator_merge_apply` ×5, the package exporter, the inspector |
| **79** | `DbLane` entries whose ownership model is *a discriminator column* (`person_id` / `narrator_id`) on rows in one database |
| **1** | import-time constant that would have to become request-scoped routing |

**And one finding that is an architectural conflict rather than a cost.**
`narrator_data_inventory.py:339` declares `media_archive_items` as
`CLASS_SHARED_ROW`: *"rows WITH person_id are the narrator's; rows without
are shared/family or unassigned — reported, never packaged."* **A photograph
of Kent and Janice together belongs to no single narrator.** Under one
database per narrator it has no home — and in a family memoir system shared
media is the normal case, not an edge case. Per-narrator databases need an
answer for shared rows before anything else; "put it in both" creates two
authorities over one photograph, which is the failure this whole redesign is
about.

**What per-narrator isolation would genuinely buy** is real and should not be
dismissed: every cross-narrator defect fixed this month — the switch-flush
write, the graph id collision, the projection written on switch — is the
class that physical isolation makes impossible rather than merely forbidden.
That is a serious argument. It is also an argument for a **routing and
scoping contract**, which can be had without splitting the file.

**Deferred, explicitly, and not quietly promoted.** The life-record work does
not depend on the answer: it needs correct `DbLane` registration and a
narrator-scoped write path, both of which are required either way.

### 2.1 Every store classified

Not eight equivalent truths. Four different *kinds* of thing, and collapsing
them is how a simplification erases meaning.

| store | kind | owns | may write | reads |
|---|---|---|---|---|
| **life record** (new) | **source of record** | people, places, events, relationships, stories, narrator assertions | the one writer (§3.10) | — |
| `bio_facts` | **projection + asking index** | nothing | derived rebuild only | life record |
| `bio_fields` / `bio_schema` | **concept catalog** | concept definitions and asking metadata | code, versioned | — |
| `profile_json` | **legacy projection** | nothing after migration | derived | life record |
| `family_truth_rows/_notes/_promoted` | **review ledger** | operator approval decisions | operator only, gated | extraction candidates |
| `interview_projections` | **runtime projection** | conversation-time field state | correction path only | life record + turns |
| `story_candidates` | **source of record** | the narrator's verbatim words | preservation path | — |
| `graph_persons` / `_relationships` | **projection** | nothing | derived rebuild only | life record |
| `trip_*` (14 tables) | **source of record, its own domain** | itineraries, days, stops, photo and turn links | the trip domain | shares refs (§2.3) |
| `rag_*` | **installation** | two fixed documents | out of band | — |

**Two source-of-record domains, not one.** The life record owns biography.
The trip domain owns itineraries. `story_candidates` owns the narrator's
verbatim words. Everything else is a projection, a ledger, or a catalog.

### 2.2 One concept catalog, checked by producers *and* consumers

The measured failure: extraction holds **146** paths *(this said 141 until
2026-09-22 — the catalog's script counts 146 two independent ways, and a
number quoted from one document into another is how this repository keeps
getting them wrong)*, the questionnaire **118**, and `suggestion_review.py:144`
records the result — *"20 of 30
queued suggestions point at undefined destinations… because `extract.py`'s
`EXTRACTABLE_FIELDS` has drifted from the questionnaire."* Components grew
their own lists of what may be recorded. **That is how this system became a
mess, and a new schema with cleaner names would do it again.**

So the catalog is a **versioned definition, not a store of answers**, and
every participant is checked against it at build or boot:

- the questionnaire (what an operator may enter)
- **extraction** — `EXTRACTABLE_FIELDS`, `_FIELD_ALIASES`,
  `_DIRECT_FIELD_PATH_MAP`, turnscope roots, negation-guard sets
- Profile Seed's topic predicates
- Lori's renderer
- the memoir's fact lane
- the import transform

Per concept the catalog carries: id · type · subject kind · cardinality ·
**asking metadata** (`narrative_value`, `life_stage_range`,
`asking_anchors`) · storage location · Profile Seed predicate · Lori
rendering rule · legacy aliases · portable representation.

**Asking metadata is product behaviour, not storage detail.** It moves into
the catalog intact. `bio_facts` keeps its flat `field_key` shape as the
**asking index** — it is what Stage 8 queries for gaps — but flat keys no
longer dictate how a life is stored. An FK to `bio_fields` remains, so
renames are migrations, not edits.

**Fail closed.** `questionnaire_schema.py` already raises `SchemaUnavailable`
on a count mismatch. The catalog inherits that: a producer naming a concept
the catalog does not define fails the build, rather than filling a review
queue with undeliverable suggestions.

### 2.3 Trips — a view, not an absorption

Trips own a hierarchy of regions, stops, days, themes, notes, photo links and
turn links, with their own lifecycle. **The life record must not become a
second travel database.**

- The questionnaire's travel topic is a **view into the trip domain**, not a
  parallel `trips[]` table.
- They connect through **shared references**: a trip stop names a `place`; a
  trip participant names a `person`; a trip may reference an `event`.
- `trip_turn_links` keeps its declared limit — *"THIS TABLE IS NOT TRUTH"*.
- The dead `trip_bio_suggestions` stub is wired properly through the review
  gate **or deleted**. It is not inherited.

The one thing the life record does give the trip domain: **a places entity
with a date model**, replacing five parallel free-text location shapes and
bare-TEXT dates with no precision.

### 2.4 Two different conflict decisions

The review's sharpest correction, and revision 1 conflated them.

| question | who answers | rule |
|---|---|---|
| **May this candidate automatically overwrite a record?** | `bio_fact_router` policy, kept as-is | no prior row → `needs_verify`; prior `approved`/`document_sourced` → log, do not write; prior `extracted_needs_verify` → write `conflicted`, link `conflict_with` |
| **Whose account is ultimately accepted?** | a person, through the review ledger | **no automatic ordering.** An operator's entry does not permanently outrank the narrator correcting it later |

Treating the first as if it answered the second would make a typo outrank its
subject. The write-authority ladder governs **automatic writes only**. Final
acceptance is a human decision, recorded with provenance, and a narrator
correction is first-class evidence — never blocked because an operator typed
something first.

### 2.5 Review gates are not bypassed by a new door

Chronology deliberately admits **promoted truth only**, through a three-field
questionnaire gate (`dateOfBirth`, `placeOfBirth`, `dateOfDeath`), *"so
unreviewed answers never leak into the sidebar as verified anchors."*

A first-class event model makes chronology **possible** — a marriage date is
currently invisible to the Life Map. It must not make it **automatic**. An
event reaches the Life Map by the same promotion it would have needed before.

Likewise inherited unchanged: an era is **never** derived from a year;
unplaced is never Today; `placement_source` is recorded, never inferred;
`story_projection` remains the single placement authority.

### 2.6 Who owns the narrator's actual words

Revision 2 said the life record owns stories *and* that `story_candidates`
owns verbatim words. Both are true only under an exact rule, or we build two
authorities over the same sentence.

**A story is one of two things, never both, and the kind decides who owns the
text.**

| | **captured** | **authored** |
|---|---|---|
| how it arose | the narrator said it; the preservation lane caught it | someone typed it — a message to grandchildren, a tradition, an operator's note |
| who owns the words | `story_candidates` | the life record |
| the life record stores | a **reference** to the candidate, plus curation: title, refs, kind, placement | the text itself |
| `body` | **read through the reference** — not copied | stored here |
| editable | **never** | yes |
| provenance to Lori and the memoir | the narrator's own words | **not a recollection** — §9 |

So the life record never holds a second copy of anything the narrator said.
Curation — what a story is about, what it is called, where it belongs — is
editable; **the recording is not**.

**A correction never rewrites the recording — and who is correcting decides
what the correction is.** *(Corrected 2026-09-22. This said a correction
"creates a new authored story", which would relabel the most important kind
of correction there is.)*

| who corrects | what it is | origin |
|---|---|---|
| **the narrator, aloud** — *"no, it was 1940"* | a **new captured telling**, with its own candidate | `captured` |
| **an operator, editing curation** — title, refs, placement | a change to the curation record; **the words are untouched** | not a story at all |
| **an operator, writing an editorial note** | a new story in the operator's words | `authored` |

If the narrator says a name wrong and later corrects it, both tellings
survive, because two tellings are two things they said (§3.6). The later one
carries `supersedes` and is what Lori reads first; the original remains, and
nothing text-dedupes them. **A narrator's spoken correction is never marked
operator-authored.**

A story whose `kind` is `captured` with no resolving candidate is refused, as
is one that is `captured` and carries its own `body`.

### 2.7 Places and events across the domain boundary

"Shared references" is not yet a contract. Four rules make it one.

**Reference, do not replace.** A trip gains a nullable `place_id`; its
existing `location_name` / `base_address` / `main_location` text **stays**.
The reference carries identity; the text stays the trip's own label. A null
reference means the trip behaves exactly as it does today, so adoption is
incremental and nothing is rewritten on migration.

**A correction changes the shared record, never the trip's words.** Fixing a
place's name, coordinates or dates updates the place record that everything
references. It does **not** cascade into `trip_stops.location_name`. An
operator may relabel a stop; the system may not do it for them. The same for
events: a corrected date shows everywhere the event is read, and edits no
trip's own note.

**A referenced record cannot be hard-deleted — it is merged.** Merging place
A into B rewrites references and records the merge with both original labels.
The alternative, a dangling `place_id`, is the untyped-anchor defect the
event model exists to end (`trip_stops.timeline_event_id` has no FK today).

**Export closure.** A portable package must carry every place and event any
included trip references. The package validator computes the closure and
**refuses** to export a trip whose referenced place is absent, rather than
producing a package that imports with holes. Places and events each need a
`DbLane` entry (§3.11) or they silently fail to export *and* to erase.

---

## 3. The model

Seven entity types, closed by design. Verified by the design validator.

### 3.1 Biography

```
biography
  schema_version · narrator_id · narrator_person_id
  people[] places[] events[] relationships[] stories[] animals[]
```

`narrator_person_id` is a pointer, so two narrators is impossible.

### 3.2 Person

```
person
  id · names[] (§4) · preferredNameRef
  lifeStatus   deceased | explicitly_living | unknown   ← on the person
  birthEventRef?  deathEventRef?    ← POINTERS, not dates (§2A, §3.8)
  occupations[] · attributes[] · storyRefs[]
```

**`bio_schema` has no key for living or deceased at all** — so the death
defect is one fault in two places, and the catalog gains the concept.

### 3.3 Place · 3.4 Animal

Places are shared and referenced — absorbing `trip_stops.location_name`,
`trip_regions.base_address`, `trip_days.main_location`,
`photos.location_label`, `media_archive_items.location_label`. Animals are
their own entity, not people.

### 3.5 Event — things that happened

```
event
  id · type (birth · death · union · separation · move · education · work ·
              service · arrival · loss · milestone · other)
  date (§5) · place · participants[{person, role}] · attributes[] · storyRefs[]
```

Events replace four untyped anchors: `trip_stops.timeline_event_id` (no FK),
`trips.meta_json.timeline_event_id`, `media_archive_links.link_target`,
`media_attachments.entity_id`.

**Reaching the Life Map still requires promotion (§2.5).**

### 3.6 Story — first-class

```
story
  id · kind (memory · reflection · lesson · anecdote · description ·
             message · tradition)
  origin  captured | authored                        ← decides who owns the words (§2.6)
  candidateRef   (iff captured — body is read through it, never copied)
  body           (iff authored)
  title · when? · source · supersedes?
  peopleRefs[] placeRefs[] eventRefs[] animalRefs[]   — many, or none
```

A story may belong to nothing in particular. An interpretation —
*"I think my father's silence came from the war"* — references the father and
asserts nothing about him. `personal.notes` was retired precisely because
*"that is where information goes to be unfindable"*.

Verbatim, exactly once, **never text-deduped** — two tellings are two things
the narrator said.

### 3.7 Relationship

```
relationship
  id · subjectPersonId · otherPersonId          "subject is <kind> of other"
  kind · describedAs (required when kind=other) · qualifiers[]
  narratorLabel · period{start,end} · basis (stated | derived_from_event)
  derivedFromEventId (iff derived) · storyRefs[] · assertion
```

Endpoints must resolve inside this biography. Only one direction is stored.
No control preselects a kind or qualifier. A derived relationship is edited
through its event. Deleting a person requires an explicit decision about
their relationships.

### 3.8 Birth and death — one home

Date and place live on the **Event**. `lifeStatus` lives on the **Person**,
because a status is not an occurrence: "explicitly living" has no event,
"deceased, date unknown" has no date.

The person carries `birthEventRef` and `deathEventRef` — **pointers, not
dates**. That is not a second copy; it is what lets the life-span resolver
reach the narrator's DOB in two hops instead of scanning every event, and it
gives every other person the identical structure. `person.birth` /
`person.death` remain derived accessors. A death event implies deceased;
nothing infers the reverse.

### 3.9 Assertion

```
{ value · source · recordedAt · status · id · supersedes? · conflictWith? }
```

Statuses reuse the existing vocabulary — `needs_verify` ·
`operator_entered` · `conflicted` · `rejected` · `empty` — extended with
`narrator_corrected` and `superseded`. Automatic-write policy per §2.4;
final acceptance human, recorded.

### 3.10 The writer

```
applyChanges(biographyId, baseRevision, changes[]) -> newRevision | Conflict
change = { op: set|add|remove, path, value?, expectedPrevious }
```

**Conflict is decided per path, not per revision.** Revision 2 left this
ambiguous by requiring `baseRevision` *and* promising that edits to different
fields both succeed. Only one of those can govern. The decision:

> **The write is rejected if and only if some path in the change set has a
> current value different from its `expectedPrevious`.**

An intervening edit to an *unrelated* path does not reject — which is the
behaviour the product needs, because the questionnaire already saves one card
at a time and `merge_whole_document` already applies mutations with no
implicit removals. A stale `baseRevision` alone is not a conflict.

- `expectedPrevious` is **required** on every `set` and `remove` — including
  the absent case, written explicitly. Without it a blind overwrite would
  ride in under a fresh revision.
- `add` names the new element's id, which must not already exist.
- `baseRevision` is still required, recorded on the resulting revision, and
  returned in a Conflict so the client can show what moved. It is audit and
  reporting, **not** the rejection test.
- A Conflict names every offending path with its current value, and **writes
  nothing** — all-or-nothing stands.
- Unknown paths preserved. `remove` explicit and separate from `set`.
- **No write on GET, render, section change or narrator switch.**

### 3.11 The portable package

**The shipped package format is unchanged and remains the authority:** BagIt
with SHA-256, zipped as `.lorevox.zip`, records serialized as **one JSONL
file per table**, selected by `DbLane`. *(Clarified 2026-09-22 — this section
named a `biography.json` beside "the shipped format, unchanged", which cannot
both be primary.)* `biography.json` is a **derived, additional export view**:
the resolved life record assembled from those JSONL tables for a reader that
is not Hornelore. **The importer never reads it.** Restore and merge consume
the per-table JSONL exactly as today; a package with a stale or absent
`biography.json` restores identically. Its presence and version are declared
in the manifest so a consumer can tell which schema produced it.

**RESTORE AND MIGRATE ARE DIFFERENT OPERATIONS, and revision 3 conflated
them.** This section said *"ids package-scoped; import maps them through a
reviewable ledger"*, which silently redefined an operation the product
already has. `narrator_package.py:7` states its meaning:

> *"RESTORE has one meaning: restore this narrator AS this narrator — every
> id verbatim, nothing overwritten, nothing merged, nothing remapped."*

| | what it does | ids |
|---|---|---|
| **restore** | puts a narrator back as themselves | **verbatim**, never remapped |
| **merge** | folds one narrator's package into an existing record | already a separate path with its own rules |
| **migrate** (new) | brings an older package into the redesigned schema | mapped through a reviewable ledger (§11) |

The ledger in §11 belongs to **migrate only**. Restore keeps its meaning
exactly, and the redesign may not quietly widen it — a family's restore path
is the last line of defence, and an operation that sometimes remaps ids is
not the operation they were promised.

**Every new table needs a `DbLane` entry in `narrator_data_inventory.py` or
it silently fails to export or erase.** A gate in the design validator, not
a note.

---

## 4. Names · 5. Dates · 6. Scope · 7. Counts

**Names** — one model for everyone: `fullText` as supplied and never parsed ·
`givenParts[]` (zero, one or several) · `family` as the complete surname ·
`prefixes[]`/`suffixes[]` · `birthFamily` for everyone · `variants[]`
(written forms of one name) · `alsoKnownAs[]` with `use` · `pronunciation` ·
`originStory`. Parts are supplied, never split. Identity is `person.id`.

**Dates** — `text` as typed is primary; `value` optionally EDTF Level 1
(`1939-08-30 · 1939-08 · 1939 · 1939? · 1939~ · 1920/1935`); `precision`
explicit. *"around 1945"* never becomes a birthday. One date model replaces
the three in the product today, two of which have no precision at all.

**Scope** — person ids are **narrator-scoped**. The same human in two
biographies is two records; linking them is a later, explicit, reviewed
operation, never a name match.

**Counts** — "six siblings stated, two identified" keeps both. Neither
overwrites the other. Same for children, grandchildren, marriages. Yes/no
facts have four states: yes · no · unanswered · unknown.

---

## 8. The questionnaire

### 8.1 Operating rules

Every field optional. Any order. "Not known" recordable. No completion
target. Repeatable entries uncapped. Saving one card writes only the paths
explicitly edited. Opening, switching sections or changing narrator **writes
nothing**. A suggestion is a draft until accepted. Sensitive attributes are
self-described free text.

### 8.2 The eleven topics

1. **The narrator** — name editor · preferred name · birth date/time/place ·
   birth order (as stated) · pronouns · current home
2. **Family of origin and caregivers** — people + relationships · life status
   each · occupations · reported sibling count · heritage story
3. **Partners, unions and children** — people + relationships with periods ·
   unions (date, place, proposal, ceremony) · children linked to *their*
   parents · reported counts
4. **Wider people and animals** — friends, chosen family, mentors, carers ·
   animals
5. **Homes and places** — residences with periods, childhood/current flags
6. **Learning and work** — education entries · highest attainment (explicit) ·
   work entries · first job · retirement
7. **Service and community** — military **yes/no/unanswered** + postings ·
   community roles
8. **Heritage, languages and beliefs** — heritages · languages · faith raised
   and now · practices · traditions
9. **Experiences and interests** — **a view into the trip domain (§2.3)** ·
   interests · milestones
10. **Life today** — living situation · routines · caregiving · health
    reflections · goals
11. **Memories, lessons and legacy** — stories · messages · lessons ·
    unfinished dreams

Themes in 11 follow life-review practice (Haight; Beechem; a content-validated
autobiographical instrument). Oral-history practice supplies the rest: an
open-ended guide rather than a script, a prepared interviewer, and a
narrator's right to refuse a subject — which Profile Seed's `declined` already
honours.

---

## 9. Delivery — what Lori and the memoir actually get

Revision 1 asserted a trace the product does not perform. Corrected.

### 9.1 Lori

Three obligations, because storage is not delivery.

**1 · Required facts — bounded by construction.** "The people in the
conversation" is not yet a rule; a narrator with forty relatives cannot have
their family permanently undroppable. Two parts, both small:

- **Constant** (`TRIM_NEVER`, always): the narrator's preferred name, and
  their own life status. One or two lines. Never varies with family size.
- **Turn-scoped** (`TRIM_NEVER` for this turn only): people **mentioned** in
  the current turn or the previous *W* turns, resolved to records, **capped
  at N**, one short line each — name, relation to the narrator, life status.

Selection is **by mention, never by closeness**. Not "her children", not
"immediate family" — only who is actually being talked about. Ties break by
most recent mention. Over the cap, the oldest mentions fall to retrieval.

`W` and `N` are stated constants with a stated character ceiling, and the
ceiling is an acceptance test (§10), not an intention: a narrator with sixty
people on record must produce a required-facts block under that ceiling.

**Life status rides with mention, always.** Whenever a person appears in the
turn-scoped block they carry their status, because the death defect is
exactly Lori speaking of someone in the present tense while the record knows
otherwise. A capped block that drops a mentioned person drops them entirely —
it never keeps the name and sheds the status.

**2 · Retrieved facts.** Everything else is fetched on demand, as stories
already are. The prompt carries a signpost — *there are more people on
record* — not the corpus. The system answers; **the narrator is never asked
for what is recorded**.

**3 · Attribution.** *"Facts are not recollections"* — a form-entered fact
may be asked about, never narrated as the narrator's memory.

And the rule this design adopts verbatim: a section *"may be droppable
because its SOURCE is durable, never because the person could be made to say
it again."*

### 9.2 The memoir

**There is no memoir writer.** Three lanes: operator prose (*"not
evidence"*), verbatim captured stories, trip notes. The questionnaire is not
read by the memoir server path at all.

So a biographical fact enters the memoir by **exactly one route**: the
operator uses it while authoring a section, and it is rendered **as an
operator-authored statement**. It is never presented as the narrator's
recollection, and this design adds no automatic path from the record to the
memoir. Anything claiming otherwise must name which lane it touches.

**The acceptance test is scoped to match.** It verifies attribution
**wherever biographical material actually reaches a memoir** — and asserts
nothing about coverage. A stored fact that appears in no memoir is the normal
case, not a failure. Testing that every fact appears would be inventing the
automatic writer this section declines to build.

---

## 10. Acceptance

- **The trace**, per fact: value, precision and **who said it** unchanged
  from the questionnaire, through storage, the resolved view, Profile Seed's
  judgement, the **final assembled prompt under a realistic budget**, and —
  where it appears at all — the memoir, attributed correctly.
- **Required facts fit the ceiling at sixty people on record**, and the
  turn-scoped block selects by mention, not by closeness. A mentioned person
  never appears without their life status.
- Retrieved facts are demonstrably retrieved, not assumed inlined.
- No producer names a concept the catalog does not define (build-time).
- A new narrator can be created with no legacy rows.
- Narrator and relative share one name structure; two middle names and a
  compound surname round-trip; a spelling correction creates no second
  person.
- Six-stated/two-identified survives; **zero stated is an answer, not an
  empty list**. Empty children ≠ no children.
- A deceased parent, an explicitly living spouse and an unknown relative
  produce correct context; death is never raised unprompted.
- A known parent occupation closes *parents' work*; a name alone does not.
- An event reaches the Life Map only through promotion; no era from a year;
  **no era from an age either**; unplaced never becomes Today.
- **The narrator's DOB anchors the span and a relative's does not.** A living
  narrator's endpoint moves with the date and is never stored; a deceased
  narrator with no known death date gets **no endpoint at all**; a missing
  DOB yields no scaffold rather than a default; an approximate DOB stays
  approximate and derived ages render as *"about N"*.
- A conflicting DOB is **one concept with two assertions** — the scaffold
  reads the accepted one and the other survives; a correction supersedes and
  moves the scaffold.
- **A captured story is never edited and never copied**; a correction
  supersedes the curation and both tellings survive.
- **A place correction changes every reader and no trip's own words**; a
  referenced place cannot be hard-deleted, only merged; export refuses a trip
  whose referenced place is outside the package.
- Trips keep their hierarchy; the questionnaire view does not duplicate it.
- Every new table has a `DbLane` entry; export and erase both prove it.
- **Two edits to different paths both succeed; two to the same path reject
  the second, naming the path and its current value, and write nothing.**
- Memoir attribution is checked wherever biographical material appears —
  **coverage is not asserted** (§9.2).

---

## 11. Import

**This section is MIGRATE, not restore (§3.11).** Restore keeps ids verbatim.

1. Validate the packages; identify which are real people.
2. **Show the delta, don't ask for a choice.** The packages are older than
   the live record; produce the exact difference first.
3. **A ledger, not a refusal**: `mapped_exactly` · `mapped_with_review` ·
   `preserved_as_legacy` · `conflict` · `unresolved`. Unmappable bytes kept
   and flagged. **No silent omission.**
4. Import into a clean destination; synthetic first, then a clone, then real.
5. Synthetic narrators live in a separate root; never rely on a name or role
   string to decide what may be deleted.
6. Packages stay untouched.

---

## 12. Open decisions

1. **The occurrence layer's scope.** *(Reframed in revision 3 — the previous
   question, "is the event spine worth its cost", was built on the error
   §2A corrects.)* Hornelore already has a DOB-anchored life-span spine;
   preserve it. The decision is whether canonical typed occurrences and
   periods should provide the temporal relationship layer **beneath** that
   scaffold, or whether that layer should initially be a **derived
   projection** over the existing domain records. Either way it must never
   become a competing life-span timeline or bypass Life Map promotion.

   | option | effect |
   |---|---|
   | scaffold + section-specific records (today) | keeps the timeline, keeps the drift: `parents.birthDate`, `children.dateOfBirth`, jobs, homes and trips stay separate representations |
   | replace the scaffold with a universal event spine | **rejected** — displaces what works and makes everything an event |
   | **scaffold + canonical occurrences/periods** | the recommendation: one representation of what happened, stories independent, promotion separate |
   | scaffold + derived occurrence index only | lower-change migration path; does not by itself remove the multiple representations that caused the drift |
2. **Does the eleven-topic form read like something you'd fill in?**
3. **Sensitive attributes** — heritage and faith are ordinary for a memoir;
   health and orientation need a deliberate decision.
4. **`trip_bio_suggestions`** — wire it through review, or delete it?
5. **Build order — settled.** The contract in §2 is the risk, not the model.
   The concept catalog and its fail-closed checks come first, because their
   absence is what produced the present drift. Specification:
   [`LIFE-RECORD-CONCEPT-CATALOG-v1.md`](../specs/LIFE-RECORD-CONCEPT-CATALOG-v1.md).

6. **One database or one per narrator** — §2B, with the measured cost and the
   shared-row conflict. SQLite either way. Does not block this work.

7. **Packages are checksummed, not encrypted.** BagIt's SHA-256 proves a bag
   has not changed; it protects **integrity, not confidentiality**. A
   `.lorevox.zip` holds a family's recordings, transcripts and biography in
   the clear, and this design says nothing about encryption at rest or in
   transit, nor about who may open one. That is a gap in the current product,
   not something this redesign introduces — but the redesign should not
   inherit it silently.

8. **Browser-only drafts cannot be exported by a server-side exporter.** The
   questionnaire writes drafts to `localStorage`, and this session's own
   repair work turned on exactly that boundary. An export that silently
   omits unsaved operator work is a package that looks complete and is not.
   Either drafts reach the server before an export is considered valid, or
   the manifest must declare them as knowingly excluded.

**Still genuinely open, and needing Chris rather than more design:** 1, 2, 3,
4, 6 and 7. None blocks the catalog.
