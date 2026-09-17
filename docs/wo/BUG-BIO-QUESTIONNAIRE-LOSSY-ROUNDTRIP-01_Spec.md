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

---

# §D · The contract already exists in this codebase. Port it; do not design it.

**Added 2026-09-17 after reading `interview_projections`.** §C describes a
contract as though it needed inventing. It does not. Hornelore solved this exact
problem once already, in a different lane, and wrote down its reasoning. The
questionnaire lane should adopt that vocabulary and those semantics rather than
grow a second, differently-shaped model for the same job.

## D.1 · `merge_projection_fields` — the server side, already built

`server/code/api/db.py:6914-7060`, from `WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01`
commit 1. Its own docstring states the problem this bug spec exists for:

> **WHY A WHOLE-DOCUMENT PUT COULD NOT BE MADE SAFE BY GUARDING IT.** The
> browser envelope is not a superset of the server one. The server writes keys
> the browser has never seen — `projection_writer.apply_correction` rewrites
> `fields` mid-turn. Replacing the document destroys those keys even when the
> replacement is fresh, non-empty and authorised. **Only a per-field write can
> leave a key the writer does not know about intact.**

Signature:

```python
merge_projection_fields(person_id, mutations=None, removals=None,
                        source=..., base_version=None, base_fields=None,
                        pending_suggestions=None, extra_keys=None)
```

| requirement §C asks for | how the projection lane already meets it |
|---|---|
| mutation envelope, absence = untouched | `mutations`; *"`pending_suggestions` replaces that array when supplied and leaves it untouched when omitted — the same 'absent means leave alone' rule the field mutations follow"* |
| deletion explicit, never `null`-as-delete | `removals: List[str]`, a separate parameter |
| stale writes refused | returns `conflict: True` + `conflicting_paths`, rolls back, **changes nothing**, and the caller *"must NOT retry"* |
| safe compare-and-write | `BEGIN IMMEDIATE` **before** the SELECT, with the reasoning recorded: without it *"two concurrent requests could both pass the per-path comparison before either wrote"* |
| server-authored keys survive | *"Any server-authored key not named above is carried through untouched — that is the whole point of this function"* |
| "empty" defined rather than inferred | `projection_envelope_is_empty()` (`db.py:6898`), which excludes `syncLog` because *"a payload that carries nothing but its own audit trail is still empty"* |

**Concurrency is PER PATH, and that was a deliberate rejection of the simpler
design.** From the same docstring, recording a supervisor review of 2026-08-17:

> **WHY A GLOBAL VERSION IS NOT ENOUGH EITHER.** `base_version` proves only that
> SOMETHING changed, not WHAT. Rebasing a dirty path onto a newer record and
> retrying is safe when the server touched *different* paths and silently
> destructive when it touched the *same* one — the conflict is delayed, not
> resolved.

And, for a caller that cannot show its working:

> `base_fields=None` means the caller cannot demonstrate what it was editing
> from. A version mismatch is then treated as contesting EVERY path, because
> **unprovable is not the same as safe.**

## D.2 · `hydrated` — the browser side, already built

`ui/js/projection-sync.js`. The sync state carries `hydrated`, `baseVersion`,
`dirty`, a per-path `base` map, and a held `conflicts` list. The comment on
`hydrated` describes the questionnaire lane's defect precisely:

> **WRITES ARE BLOCKED WHILE false**, which is what stops a localStorage draft
> silently repopulating a server that merely failed to answer. A confirmed-empty
> server is `hydrated=true` and is allowed to stay empty.

That sentence draws the distinction §D.3 shows the questionnaire lane does not
make: **a server that answered "empty" is not the same as a server that did not
answer.** On `dirty`: *"Only these are sent — the write is field-level, so
server-authored keys we have never seen survive it."*

## D.3 · FOURTH MECHANISM — localStorage can become authority

Distinct from §A (a narrower form replacing a wider record) and §B (a primitive
that permits replacement). This one needs no bug in either: it is the ordinary
load path.

`_restoreQuestionnaire(pid)` (`bio-builder-core.js:293-331`) calls
`_restoreQuestionnaireFromBackend(pid)` **fire-and-forget, not awaited**, then
synchronously reads `localStorage` and returns it. `bb.questionnaire` is
therefore the local draft for the whole in-flight window, and three paths leave
it there permanently:

1. **The fetch fails.** `.catch` (`:405-407`) logs and does nothing else. The
   local copy remains in memory; the next save PUTs it over the database.
2. **The server answers "empty".** The guard at `:377` is
   `Object.keys(q).length > 0`, so an empty response is ignored and the local
   draft survives. The comment calls this *"backend authority rule."* It is the
   inverse: **local wins whenever the server says empty** — exactly the case
   `projection-sync.js` singles out as needing the opposite treatment.
3. **A PUT fails.** `_persistDrafts` (`:145-155`) fires the PUT with `.catch()`
   and then writes `localStorage` **unconditionally**. A failed write leaves
   content on disk the database never received, which becomes "truth" on the
   next load.

**It survives a full database rebuild.** The key is
`lorevox_qq_draft_<person_id>` and narrator ids are preserved verbatim through
export and restore (§17's identity guarantee). The laptop's database was erased
and rebuilt on 2026-09-15; any draft in that browser profile predates the
rebuild and would still hydrate first.

**Operational consequence, before any restore:** capture the drafts, restore the
database, clear the stale drafts, and only then open the UI. Restoring first and
opening the Bio Builder can put the damaged version straight back.

**The rule this establishes, and it is absolute:**

> **localStorage is a draft and a cache. It is never authority.** It may recover
> unsaved work. It may never become narrator truth because the authoritative
> server failed to answer.

## D.4 · The `version` trap

| table | what `version` means |
|---|---|
| `interview_projections` | **the revision counter** — `next_version = stored_version + 1` |
| `bio_builder_questionnaires` | **the schema version** — every client hard-codes `1` or `DRAFT_SCHEMA_VERSION` |

Same column name, opposite meanings, adjacent tables. Porting the projection
code without renaming would produce a concurrency check that **looks correct and
verifies nothing**, because a stale client sends the same value a fresh one
does. The questionnaire's schema version must be renamed or separated before any
revision semantics are attached to that word.

## D.5 · What the projection lane does NOT have

**History.** No archive table, no prior-revision recovery. Per-path concurrency
prevents a bad write; it cannot undo one. That is the one layer genuinely new to
this work, it is the reason Janice's loss was recoverable only by luck, and it
should be applied to **both** lanes rather than only the questionnaire.

## D.6 · Recommendations withdrawn

- **Mine (§C, earlier draft):** "refuse a write that drops more than a small
  number of populated leaves." A threshold cannot separate a legitimate
  forty-field edit from one deleted `notableLifeEvents`. Withdrawn in favour of
  the invariant.
- **The independent review's, withdrawn by its own author 2026-09-17:** a new
  single integer `revision` as the primary concurrency mechanism, and a fresh
  bespoke mutation envelope. Both are superseded by D.1 — this codebase already
  chose `base_version` + `base_fields` *and recorded why the simpler design is
  insufficient*. A second envelope shape for the same job is how one system
  acquires two mental models.

## D.7 · The boundary with Lori's read path — one flag connects them

Recorded here because the two lanes interlock at exactly one place, and the
persistence work gates the other.

**`bio_facts` is empty for all three family narrators, and always has been.**
Measured 2026-09-17 against the live root and the pre-erasure preservation copy:
Janice, Kent and Christopher each have **0 rows** in both. The 74-narrator
pre-erasure database held **495** rows, overwhelmingly `operator_entered`, all
belonging to development and test narrators. **Nothing was lost in the rebuild** —
`bio_facts` is properly declared portable (`narrator_data_inventory.py:215`,
`CLASS_DERIVED`); it was simply never populated for the family.

`profiles.profile_json` for all three carries exactly `basics`, `kinship`,
`pets`. The questionnaire writer's `profile_patch` has never run for them.

So everything Hornelore holds about these three lives in the
`bio_builder_questionnaires` blob and in `graph_persons` — **not in the layer a
truth/authority model would read.**

The bridge is `HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE`. At `0` — today's
setting — questionnaire content never reaches `bio_facts` or `profile_json`.
Turning it on is what makes operator-entered biography available to a canonical
read path.

> **HARD INTERLOCK: `BIO_FACTS_WRITE` must not be set to 1 while the write path
> can still delete.** The fan-out would propagate a reduced document into the
> truth layer as well as the blob, converting a recoverable single-store loss
> into a multi-store one. The persistence repair is a precondition of the
> read-path work, not a parallel track.

Note also that **`bio_questionnaire_view` disqualifies itself as a source for
Lori**: it builds nine sections and silently omits grandparents, marriage,
familyTraditions, pets, technology, earlyMemories, laterYears, hobbies and
additionalNotes. It is a UI projection, and a lossy one.

---

# §E · What the 2026-09-17 port did, and what is still exposed

**Janice is restored.** Ten values back, verified by reading SQLite directly:
9,114 bytes, 16 sections, `integrity_check ok`. The damaged row is preserved in
`lorevox_packages/safety-capture-20260917-140942/` and in
`hornelore.sqlite3.pre-qq-restore-20260917-142517.bak`. Kent and Christopher were
captured at the same time; they had never been snapshotted before.

**The browser held the damaged copy independently of the database.** A
7,046-byte `lorevox_qq_draft_93479171…` at origin `http://localhost:8082`, leaf
sets identical to the damaged row, missing the same ten values. Had the database
been restored and the UI opened, it would have gone straight back. Captured to
`safety-capture-.../browser_localstorage_localhost8082.json` and cleared. This is
§D.3 demonstrated rather than argued.

*(Origin matters: `127.0.0.1:8082` and `localhost:8082` are separate stores. The
first capture read the wrong one and showed no drafts at all.)*

## Landed

| | |
|---|---|
| `0058_questionnaire_revisions.sql` | `revision` column (NOT `version` — §D.4) and the history table, with `changed_paths` / `removed_paths` / `previous_values` so *"which write removed `parents[0].notableLifeEvents`?"* is a query |
| `services/questionnaire_persistence.py` | `merge_questionnaire`, `merge_whole_document`, `replace_questionnaire`, `reset_questionnaire`, `read_for_edit` — the `merge_projection_fields` contract, per-path concurrency, `BEGIN IMMEDIATE`, archive inside the same transaction |
| `routers/questionnaire.py` | PUT routed through `merge_whole_document`; conflict → **409** with `conflicting_paths`; `base_revision`/`base_fields` accepted and optional; `revision` returned on GET |
| `db.upsert_questionnaire` | **refused by default.** Raises unless `allow_destructive_replace=True`. The door is shut, not labelled |
| `narrator_data_inventory` | the history lane declared — erasable, not portable |
| `test_questionnaire_persistence_integrity.py` | 16 tests, real temporary SQLite, read back through SQLite |
| `test_questionnaire_route_fanout.py` | patch target moved; docstring now states what it cannot see and why that mattered |

**The key property, in one line:** `merge_whole_document` flattens an incoming
document to its populated leaves and applies them as mutations with **no
removals**, so a key the caller omitted is untouched rather than deleted — which
makes every existing whole-document PUT non-destructive **with no client change
at all**.

### The cost of that default, made observable

Because `flatten_document` drops `""` / `None` / `[]` / `{}`, a legacy
whole-document client **cannot clear a populated field** — its blank means
*untouched*. That is the right default: it is precisely what stops a six-field
form deleting five stored ones. But left alone it trades silent deletion for a
silent lie — the operator empties a box, sees "Saved", and the old value
survives.

So the blank is **detected and reported, never acted on**. `merge_whole_document`
returns `ignored_blank_paths`, and the PUT response carries it beside the new
`revision`, so no client can truthfully report the operation as fully saved when
it was not. The UI can then ask *"you cleared Josie's occupation — delete it?"*
and send a real `removals`.

Pinned from both sides in one test, same field, opposite outcomes: a legacy PUT
of `""` preserves the value and reports the path; an explicit `removals` actually
removes it and lands in history with `previous_values` intact. Blanks over
*unpopulated* fields are not reported — otherwise every empty box on a
sixteen-section form would be noise.

**The invariant is unchanged: only an explicit removal can delete stored
narrator information.** What changed is that the temporary limitation is now
visible and testable rather than silent.

The regression test is the real shape: a six-field minimal-intake `parents` form
saved over an eleven-field stored record, asserting all ten values survive.

## The WSL gate: two failures, one inherited and one introduced

Seven suites, `.venv`, 2026-09-17: **176 passed, 2 failed.** They are not the same
kind of thing and the record should not say "two tests failed".

**INHERITED — `test_narrator_package_export::…::test_exporter_source_names_no_table_and_no_narrator`.**
Not caused by this work. The test forbids narrator identity anywhere in
`narrator_package.py`'s source, and a comment added by **`d46b730`** reads *"the
first real Christopher merge rehearsal did not"*. It has been red since that
commit, which means **the seven-suite gate has not been continuously green since
`d46b730`** and nobody ran it in between. Fixed by rewriting the comment without
the name, not by weakening the test: a real family member's name in product
source on a public repository is precisely what it exists to stop, and a comment
is still source.

**INTRODUCED — `test_narrator_merge::ClosureIntegrity::test_remap_targets_cover_every_narrator_owned_integer_surrogate`.**
Genuinely this commit's. `bio_builder_questionnaire_revisions` is narrator-owned
with an `INTEGER PRIMARY KEY` and was absent from `REMAP_TARGETS`. The test did
exactly its job.

### And it surfaced a classification error worth more than the failure

Chasing it showed the new lane was the **only `Direct`-owned, `portable="no"`
lane in the entire declaration** — a combination the model had no other instance
of. That is a symptom, not a style problem, and the fix was not to register the
table and move on.

The inventory had already decided this case. **`identity_change_log`** is the
same shape — `Direct(person_id)`, an audit of changes to the narrator's own
record, carrying `field_path`, `old_value`, `new_value`, `source` — and is
declared **`CLASS_AUTHORITATIVE`, `portable="yes"`, erasable**. Questionnaire
history is that table's twin for the questionnaire, and it had been classified
the opposite way.

The reasoning that produced the error was that *"revision 7 was superseded by
`ui_save` at 14:02"* is a fact about a machine rather than about the narrator.
Two things were wrong with it. It invented an unprecedented combination; and it
would mean **a narrator can be carried to a new installation complete except for
the recovery trail that exists to protect this exact table** — portability
silently downgrading safety. The prior contents of a narrator's biography are
still their biography.

Now: `CLASS_AUTHORITATIVE`, `portable="yes"`, erasable, `Direct(person_id)`,
registered in `REMAP_TARGETS` with an established-and-empty closure. The remap
entry is **load-bearing rather than precautionary** now that the lane travels:
two origins can genuinely present the same AUTOINCREMENT id for different
revisions of different documents. `identity_change_log` needs no such entry only
because it keys on a TEXT id.

## Still exposed — not fixed by this port

1. **Positional array identity.** `parents[0].x` is by position. Insert, remove
   or reorder and indices shift. Needs stable per-entry ids
   (`parents/<entry-id>/x`) plus a data migration, deliberately not bundled with
   the loss fix. Recorded in the service docstring.
2. **The client half.** `_getQuestionnaireBlob` still turns a failure into `{}`;
   `_restoreQuestionnaire` still hydrates localStorage synchronously ahead of the
   server; `_persistDrafts` still writes localStorage after a fire-and-forget PUT.
   The server can no longer be *destroyed* by these, but the browser can still
   show and submit a stale view. Needs the `hydrated` state machine and drafts
   stored as `{base_revision, mutations, removals}` rather than as a replacement
   document.
3. **The template import** still replaces a live narrator from a stale template,
   and writes `/api/person/{id}/profile` wholesale first. **Neutralise before the
   UI is opened on any of the three.**
4. **Resets** still PUT `{}` through the ordinary route rather than calling
   `reset_questionnaire`.
5. **The adversarial matrix** — the acceptance this bug actually deserves: one
   rich synthetic narrator attacked through every writer (stale draft, timeout,
   confirmed-empty, concurrent same-path and different-path, template import,
   `_saveBBAnswer`, identity rescue, narrator switch, explicit delete, explicit
   reset), reading SQLite after each, then mutation-testing the guards by
   reintroducing whole-document assignment, dropping `BEGIN IMMEDIATE`, treating
   failed reads as empty, and ignoring `base_fields`. Every mutation must break
   the suite.

**`HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE` stays at 0** until at least 2 and 3
are closed (§D.7).
