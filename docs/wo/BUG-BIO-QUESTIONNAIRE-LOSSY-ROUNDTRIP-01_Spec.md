# BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01

**Status: OPEN — filed 2026-09-15. Do NOT fix inside the portability or
Phase 7 lanes.** Belongs to the post-portability Bio Persistence work.

## ⚠ STATUS 2026-09-17 — THE SCOPE OF THIS BUG WAS WRONG, TWICE

**Read §A and §B below before acting on anything above them.** What was filed
2026-09-15 as a projection defect in one read path is a **data-integrity flaw in
the questionnaire persistence contract**, reachable by at least seven callers,
and it has already destroyed real family history on the laptop.

The escalation, in order:

1. **Filed 2026-09-15** as a `bio_questionnaire_view` projection defect —
   five fields on `spouses`/`children` lost through GET→edit→PUT.
2. **Narrowed 2026-09-15** by the flag-dependency note below: the projection
   runs only under `HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1`, so "the laptop
   is not affected." **That narrowing was wrong** — correct about the read
   path, wrong about the conclusion, because it never asked how the WRITE path
   builds its document. §A.
3. **Widened 2026-09-17**, after the loss, by an audit of every writer. The
   projection is one of several ways to reach a persistence primitive that
   permits silent destructive replacement. §B.

**Independent review, 2026-09-17, agreed and sharpened it further:** the
dangerous primitive is `upsert_questionnaire`, which means *"replace everything
we know about this narrator with whatever JSON this caller happens to hold"*
while several callers use it believing it means *"save the change I just
made."* Those are different operations and the server cannot tell them apart.
That review's proposed contract is recorded in §C and is the intended fix.

**Do not treat the two UI repairs of 2026-09-17 as closing this bug.** They
close two callers. The primitive is unchanged.

---

## ⚠ Flag dependency — TRUE, AND IT WAS NOT THE WHOLE PICTURE

*(This section is preserved exactly as written on 2026-09-15 because its
reasoning was sound and its conclusion was still wrong — the failure was one of
scope, not of analysis, and §A names how. Every factual claim in it still
holds.)*

**The PROJECTION described in this spec's Evidence section fires only when
`HORNELORE_QUESTIONNAIRE_BIO_FACTS_READ=1`.**
Established 2026-09-15 by reading the full path, laptop session:

- `db.get_questionnaire()` (`db.py:6787`) routes through `bio_questionnaire_view`
  — the lossy projection this spec describes — **only** under that flag. With the
  flag at its default `0`, GET returns the **verbatim JSON blob** from
  `bio_builder_questionnaires` (`db.py:6806-6827`).
- PUT under `HORNELORE_QUESTIONNAIRE_LEGACY_BLOB_WRITE=1` (default) writes that
  same blob back verbatim (`routers/questionnaire.py:171-178`). The writer's
  fan-out into `profile_json` — the other half of the silent-loss path — runs only
  under `HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE=1`.
- So at the defaults (`READ=0`, `WRITE=0`, `LEGACY=1`) the round trip is one JSON
  document in and the same document out. **Nothing is projected, nothing is
  reduced, nothing is lost** — including sections the view does not model at all
  (grandparents, marriage, pets, traditions, `spouse.narrative`,
  `spouse.relationshipType`).

**The laptop is at the defaults** (`.env:182-184`, verified 2026-09-15) and so
**Bio Builder entry on the laptop is NOT blocked by this bug.** The evidence
above was taken with the read flag on, on a disposable root — the intended
future read path, not the laptop's current one.

**What the defaults cost instead:** entered data lands in the blob only, not in
`bio_facts` / `profile_json`, so Lori does not see it in conversation until the
write fan-out is turned on. That is a separate rollout decision with its own
gate (`.env.example:461-464`) and is not this bug.

*(`HANDOFF.md` and the checklist said this bug was "live and directly in the
way" of the Bio Builder work from 2026-09-15 until this note. That was true of
the desktop's intended configuration and false of the laptop's actual one; the
distinction was not drawn, and it would have sent the next session into a fix
before entering any data.)*

## Mission alignment

The narrator is the author of their own story. A spouse's maiden name and a
child's birthplace are not incidental metadata — they are the family record the
system exists to preserve. A save that quietly removes them is the failure this
project cares about most, and it is worse than a crash because nothing tells
anyone it happened.

## Non-regression requirements

This BUG's eventual fix MUST NOT:

- reduce narrator dignity
- introduce new must_not_write violations or system-tone outputs
- regress the CURRENT locked baseline without explicit justification
- expand operator surfaces into narrator UI
- add detectors that duplicate existing signals

## Summary

`bio_questionnaire_view` does not round-trip every field that
`bio_questionnaire_writer` accepts and stores for `spouses` and `children`
entries. Because Bio Builder rebuilds each repeatable entry from the rendered
view and then PUTs the whole questionnaire back, a later save can **erase**
fields that were stored correctly.

## Evidence (verified_by_execution, 2026-09-15, disposable root)

A rich spouse and two rich children were PUT to
`/api/bio-builder/questionnaire` for a synthetic narrator
(`952baf78-3c40-4fa7-b0c8-8df801140e17`, "Daniel Robert Mercer").

**Stored correctly** — direct read of the database, not the API:

```sql
SELECT json_extract(profile_json,'$.spouses'),
       json_extract(profile_json,'$.children')
FROM profiles WHERE person_id='952baf78-…';
```

returned spouse `maidenName: "Reynolds"`, `birthPlace: "Pueblo, Colorado"`,
`notes: "Known as Patty. Married Daniel on 14 June 1981."`, and both children
with `relation` (`Son` / `Daughter`) and `birthPlace` (`Albuquerque, New
Mexico` / `Santa Fe, New Mexico`).

**Absent from the canonical GET view** — the same five fields do not appear in
`GET /api/bio-builder/questionnaire`. `spouses` projects down to first/middle/
last name, `yearMarried`, `status`, `birthDate`; `children` to name plus
`dateOfBirth`.

**Not a blanket rule, which is what makes it a defect rather than a design.**
`parents` round-trips every field including `maidenName`, `birthPlace`,
`occupation`, `notableLifeEvents` and `notes`; `siblings` round-trips
`relation`, `birthDate` and `notes`. The writer's own allowlist
(`bio_questionnaire_writer.py:278-284`) explicitly accepts `relation`,
`birthPlace`, `maidenName` and `notes` for these array sections — so the write
side and the read side disagree about the same shape.

## The silent-loss path

1. Rich spouse/child data is stored in `profiles.profile_json` (correct).
2. Bio Builder GETs the questionnaire and renders it — five fields are already
   missing from what it received.
3. The operator opens the section and saves. Bio Builder rebuilds each
   repeatable entry **from the fields present in the DOM**, so the rebuilt
   object cannot contain what the view never sent.
4. `_persistDrafts()` PUTs the whole questionnaire.
5. The writer assigns the reduced arrays into `profile_patch` and merges them
   into `profile_json`.

The stored rich array is replaced by the reduced one. No error, no warning, and
the operator's own act of reviewing the record is what destroys it.

## Acceptance

Deliberately small:

1. PUT a spouse and a child carrying every field the writer's allowlist
   accepts.
2. GET returns **every** supported field.
3. Perform a no-op Bio Builder save of those sections.
4. Read `profiles.profile_json` directly — the objects are equivalent to step 1.

Step 4 must read the database, not the API. A test that checks the API against
the API cannot see this class of defect at all, which is why it survived until
a direct SQL read was taken.

## The invariant this establishes

**Anything the canonical questionnaire writer accepts must survive the
canonical read → edit → save round trip, unless the schema explicitly declares
it non-persistent.**

That is the first concrete invariant for Bio Persistence Integrity, and it
generalizes past this bug: any surface that rebuilds an object from a rendered
view and writes it back inherits the read path's omissions as deletions.

## Scope notes

Two adjacent observations from the same session, recorded so they are not
rediscovered as bugs. Neither is part of this defect:

- The questionnaire has **no field** for grandchildren, dated residences,
  hobbies, pets, favourite things, or life events. Those belong to Life Map
  timeline events and story candidates, not here.
- `people.display_name` carries the narrator's warm/preferred name while the
  full legal name lives in the bio lane as `full_legal_name`. That split is
  correct and deliberate.

---

# §A · Second mechanism — flag-independent, and it fired on real data

**Verified by execution 2026-09-17 against the live laptop root**
(`/mnt/c/hornelore_data`, `READ=0 WRITE=0 LEGACY_BLOB_WRITE=1` — the exact
configuration the note above declared safe).

A Bio Builder save on **2026-09-15 13:18** destroyed **ten populated values**
from Janice `93479171`. Leaf-level diff against a snapshot taken 12:07 the same
day: **LOST 10, CHANGED 0, ADDED 0.** The save contributed nothing; it was
purely subtractive. Blob 9,114 → 7,332 bytes.

| entry | fields deleted |
|---|---|
| `parents[0]` Josephine "Josie" Zarr | `birthDate` `birthPlace` `deceased` `notableLifeEvents` `notes` |
| `parents[1]` Peter "Pete" Zarr | `birthDate` `birthPlace` `deceased` `notableLifeEvents` `notes` |

`notableLifeEvents` on those two entries held several hundred words of
hand-typed family history — Josie playing organ for silent movies and her
years at Mount Marty; Pete delivered at home by Mrs. Steve Dodenheffer, the
Garrison Dam finishing crew, the birth certificate lost when the ND Capitol
burned. **There was no other copy at full length.** Christopher's
`grandparents` entries for the same two people carry condensed paraphrases,
and `graph_persons` carries only the structured fields.

**Mechanism — no projection involved.** `_saveSection`
(`bio-builder-questionnaire.js`) rebuilt each repeatable entry as
`var obj = {}` and filled it *only* from `section.fields`, then assigned that
over the stored entry. `MINIMAL_SECTIONS.parents` declares **6** fields;
`FULL_SECTIONS.parents` declares **11**. Minimal intake is the **default**
(`intakeMinimalEnabled()` returns `true` when unset). 5 undeclared fields ×
2 parents = exactly the 10 values lost.

So the spec's own invariant —

> *any surface that rebuilds an object from a rendered view and writes it back
> inherits the read path's omissions as deletions*

— was violated through the **front end's own section list**, with
`bio_questionnaire_view` never in the call path. The invariant was right and
its stated scope was too narrow: *the read path* is not the only source of
omissions. **Any narrower representation of the narrator will do.**

**Related hazard found in the same function:** `existing` was read as a bare
property, but `_migrateRemovedSectionsToLegacy` relocates six section ids
(`grandparents`, `auntsUncles`, `childhoodPlaces`, `schools`, `trips`,
`memoryNotes`) into `_legacyRemovedSections` and deletes the originals. For
those, the bare read returned nothing, `existing` collapsed to one empty entry,
and a save would have written **one** row over however many were rendered.

**Repaired 2026-09-17** in `_saveSection` and in `operator-intake.js`
`_readSectionFromForm`: start from the stored entry, let rendered fields
overwrite only themselves, and read through `getSectionData`. **These two
repairs close two callers and change nothing about the primitive.**

---

# §B · Root cause — the persistence primitive permits silent replacement

`db.upsert_questionnaire` (`server/code/api/db.py:6832-6862`):

```sql
INSERT INTO bio_builder_questionnaires (...)
ON CONFLICT(person_id) DO UPDATE SET
    questionnaire_json = excluded.questionnaire_json, ...
```

Primary key `person_id`. **One row per narrator. Blind whole-document replace.
No merge, no revision check, no history.** Whatever any caller sends becomes
the entire record. `put_questionnaire_route`
(`routers/questionnaire.py:99-201`) adds no protection — its only 409 is for
the both-flags-off misconfiguration.

### Every writer, audited 2026-09-17

| # | caller | sends | status |
|---|---|---|---|
| 1 | `_saveSection` — Bio Builder | rebuilt section + whole blob | **repaired** |
| 2 | `_readSectionFromForm` — Operator Intake | rebuilt section + whole blob | **repaired** |
| 3 | `lv80PreloadIntoExisting` — JSON/template import | **whole questionnaire built from a template file** | **OPEN — critical** |
| 4 | `_saveBBAnswer` — session-loop, during conversation | whole blob from a cache that returns `{}` on any failure | **OPEN — high** |
| 5 | `_persistDrafts` — bio-builder-core | whole in-memory blob | **OPEN** |
| 6 | `bb_reset_utility` / `bb_deep_reset` | `questionnaire: {}` | deliberate wipes, wrong endpoint |
| 7 | `_overwriteBbPersonal` — BUG-227 rescue | whole blob, personal overwritten | **OPEN — low** |

### 3 · The template importer replaces what it claims to update

Settings → **"JSON Import / Update"** → file → **Import / Update JSON**
(`hornelore1.0.html:4238-4246`, `lv80OperatorImportJson` at `:10526`).
`lv80ImportNarratorTemplate` matches a template to a live narrator by the
template's own `fullName`/`preferredName` against `display_name`, then
`lv80PreloadIntoExisting` PUTs `_buildQuestionnaire(tpl)` **wholesale** — and
PUTs `/api/person/{id}/profile` with `{basics, kinship, pets}` wholesale
immediately before it.

| template in `ui/templates/` | preferredName | fullName | live display_name | matches |
|---|---|---|---|---|
| `janice-josephine-horne.json` | `Janice` | Janice Josephine Horne | **Janice** | **yes** |
| `kent-james-horne.json` | `Kent` | Kent James Horne | **Kent** | **yes** |
| `christopher-todd-horne.json` | Chris | **Christopher Todd Horne** | Christopher Todd Horne | **yes** |

**All three authoritative narrators match their own stale template.** The files
are dated 2026-05-04; Janice's is 10,732 bytes against her live 9,114, so it is
*different* content, not a superset. The UI text reads *"If the narrator
exists, update them."* It does not update. It replaces.

Phase 7 removed the boot-time auto-seeding of these same three templates and
documented at length why it must not return (`hornelore1.0.html:10145-10178`).
It left the manual path that does the same thing on demand.

### 4 · A read failure becomes a write of `{}`

`_getQuestionnaireBlob` (`session-loop.js:641-677`) returns `{}` on non-OK
status, on `person_id` mismatch, on a 3-second timeout, and on any throw.
`_saveBBAnswer` (`:1016-1050`) then does:

```js
if (!blob[sectionId] || typeof blob[sectionId] !== "object") blob[sectionId] = {};
blob[sectionId][fieldId] = normalized;
// ... PUT blob
```

**A three-second network hiccup during a conversation replaces the entire
questionnaire with one section containing one field.** Three semantically
different states — loaded-and-empty, loaded-with-data, and failed-to-load — are
collapsed into one value, and the third is the one that destroys data. This is
a correctness defect, not a hardening opportunity.

---

# §C · The contract this bug now requires

From the independent review of 2026-09-17, adopted as the intended fix.
**The heuristic previously proposed here — refuse a write that drops "more than
a small number" of populated leaves — is WITHDRAWN.** A legitimate edit may
churn forty fields; an illegitimate one may delete a single irreplaceable
`notableLifeEvents`. A threshold cannot separate them. The invariant can:

> **An ordinary questionnaire update may add or modify information. It may not
> silently remove information. Removal requires an explicitly different
> operation.**

Three independent protections, none sufficient alone:

| layer | protects against | note |
|---|---|---|
| **revision history** | unrecoverability | first-class, not an incidental copy: prior JSON, `person_id`, timestamp, source, revision id — recovery *and* forensics on which caller did it |
| **destructive-write guard** | accidental deletion | split `PUT` into merge/patch (cannot delete), explicit replace (archives, authorised, diff reported), explicit reset |
| **revision / optimistic concurrency** | stale-client overwrite | the case neither other layer catches: two clients read rev 41, one saves 42, the other later saves its 41 — same leaf count, so no shrink to detect |

**Implementation traps, from the code rather than from the design:**

- **`version` is already taken and does not mean revision.**
  `QuestionnairePutRequest.version: int = 1` and the `version` column are a
  *schema* version; every client hard-codes `1` or `DRAFT_SCHEMA_VERSION`, so a
  stale client sends the same value a fresh one does. Concurrency needs a **new
  column**. `updated_at` is already returned by GET and can serve as an interim
  ETag with no migration.
- **The merge must be server-side against the stored document, and clients must
  send a patch rather than a document.** Under `READ=1` the GET returns a
  nine-section projection that omits grandparents, marriage, familyTraditions,
  pets, technology, earlyMemories, laterYears, hobbies and additionalNotes
  entirely — so any client-side merge reproduces this bug through the merge
  path itself.
- **Resets must use the destructive endpoint**, not a bypass flag on the
  ordinary save, so the architectural rule stays testable: *no normal workflow
  can erase questionnaire information by sending a smaller representation of
  the narrator.*
- **`/api/person/{id}/profile` has the same wholesale-replace shape** and the
  template importer writes it too. Any audit of `upsert_questionnaire` callers
  must cover the profile endpoint as well.

## Revised acceptance

Supersedes the four-step acceptance above, which tested one path.

1. Build a synthetic narrator whose questionnaire carries **every** section and,
   within each, every field any writer's allowlist accepts.
2. Exercise **each** persistence path independently — Bio Builder (minimal and
   full intake), Operator Intake, `_persistDrafts`, `_saveBBAnswer` including
   its read-failure branch, `_overwriteBbPersonal`, template import, and each
   reset.
3. After every operation, compare all leaves the operation did not target
   against the starting document. **Untouched data must be identical.**
4. Prove the read-failure branch cannot write: force the GET to fail and assert
   that **no PUT is issued**.
5. Prove staleness is refused: read rev *n*, write rev *n+1* from a second
   client, then attempt the rev-*n* write and assert **409**.
6. Read the database directly, never the API. *A test that checks the API
   against the API cannot see this class of defect at all* — which is why it
   survived until a direct SQL read was taken.
