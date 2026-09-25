# WO-HORNELORE-INTEGRATED-LIFE-RECORD-01 — Checkpoint 1

**2026-09-22 · the §8 first response.** Review and plan only.
**No live data was changed. No git command was run. No product-code migration
has begun.** Every claim below carries a file:line or is marked `inferred` /
`unverified`, per the standing rule that a claim about what code does must cite
the line that reads the value.

Numbered to match §8 of the work order.

---

## 1. What exists now

### 1.1 The database state, as found

*(Corrected: an earlier draft of this section said the brief claimed the working
database was clear of real people. Nobody claimed that — Chris said the
narrators **can** be removed once the stack is up, and they have not been yet.
The data below is what matters; the misreading was mine.)*

Read-only query, `DATA_DIR=/mnt/c/lorevox_data` (the root the server uses,
`.env`):

| root | file | people |
|---|---|---|
| `lorevox_data` (**server root**) | `db/lorevox.sqlite3` 2 MB | **3** — `ZZ RICH FIXTURE` (synthetic), **`Christopher Todd Horne`**, **`Janice`** (UUID `93479171…`, identical to `Janice Josephine Horne` in `hornelore_data`; her real record, not a copy) |
| `hornelore_data` | `db/hornelore.sqlite3` 20 MB | 109 — the real three plus ~100 test narrators |
| `hornelore_data` | two `backup_real_pre_0035_*` | 100 each |

Kent is not in the working root; Janice and Chris are. **§0's data boundary
stays in force for this root until that changes.** Nothing in this checkpoint
touched any of these files.

### 1.1a §0A cleanup — DONE 2026-09-22, by Chris, through the product's own route

**Authorized by the revised work order §0A; executed by Chris against the
running stack; verified read-only afterwards from the sandbox.**

**Target and route.** Working root `DATA_DIR=/mnt/c/lorevox_data`. The UI's
Delete button sends `?mode=soft` (`app.js:4504`) — a 10-minute-undo flag that
leaves rows in place (`db.py:6002-6024`). Removal therefore used the same
route's hard mode, `DELETE /api/people/{id}?mode=hard` (`people.py:247-281`),
which runs `hard_delete_person` (`db.py:6117`) and the saved filesystem erasure
plan. No UI control sends hard; no SQL was run by hand.

**Preview before deletion** (`GET /api/people/{id}/delete-inventory`): all
counts narrator-scoped; `media_archive_items` 0 for all three — no shared or
unassigned material in the path. Nothing ambiguous.

**Removed — all three HTTP 200, `status: hard_deleted`, `erasure_complete:
true`, `failed: []`, `historical_residue: []`:**

| id | display name | DB rows | files | paths |
|---|---|---|---|---|
| `42d4ed90-f5da-474c-ac34-0fbfa3aaebbe` | ZZ RICH FIXTURE 20260921 | 20 | 6 | `memory/archive/people/…` |
| `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2` | Christopher Todd Horne | 148 (27 photos, 47 sessions, 3 stories, 2 trips) | 232 | archive, `stories-captured/…`, photos, one `import_staging/…` |
| `93479171-0b97-4072-bcf0-d44c7f9078ba` | Janice | 4 | 21 | archive, photos, three `bot_tests/switch_*` transcripts |

**Verified afterwards, read-only:** `people` 0 (`include_deleted=true` also
0); `bio_builder_questionnaires`, `graph_persons`, `graph_relationships`,
`story_candidates`, `interview_projections`, `family_truth_rows/_promoted`,
`profiles`, `trips`, `photos`, `bio_facts`, `media_archive_items` — **all 0**.
Per-narrator directories `memory/archive/people`, `memory/archive/photos`,
`stories-captured`, `import_staging` — all empty. 80 tables, 10 non-empty,
all installation or audit.

**Intentionally retained, as the response declared:** `narrator_delete_audit`
(3) and `narrator_erasure_jobs` (3) — ids, counts, paths, no narrator speech.
`sessions` (8) all have `person_id NULL` — unattributed conversations, owned
by no narrator, correctly untouched. `bio_fields` (84) is the asking schema
seed, installation-owned.

**Retained but NOT declared by the response — a small gap to note, not act
on:** `narrator_package_jobs` (3) and `narrator_package_export_jobs` (2) still
carry the removed `narrator_id`s, plus `package_path`, `counts_json` and
`file_manifest_json` from the September 21 restore and the exports. They are
job metadata, not narrator content; but the erasure response's
`intentionally_retained` list does not name them, and the product's own
standard is that retention is reported rather than silent. Filed for Batch E.

**Not touched:** `hornelore_data/db/hornelore.sqlite3`, its two July backups,
and the three USB packages.

**Browser drafts — DONE.** Chris ran the DevTools clear on the Lorevox tab
(keys `lorevox_qq_draft_<pid>`, `lorevox_proj_draft_<pid>`,
`lorevox_offline_profile_<pid>`, `lv_trip_confirm_offered_<pid>` for each
removed id, plus `lorevox_draft_pids`, `lv_active_person_v55`,
`lorevox_offline_people`); returned `'drafts cleared'`. The same console
showed a clean blank start — `[startup] Enforced blank startup state — no
active narrator` — with no stale narrator remembered. **§0A is complete, all
five steps.**

**Consequence for the plan:** the working root is now the isolated destination
Batches B, C and E need. All subsequent design and implementation use fresh
fictional narrators here. Task #4 (re-export and compare) and #5 (Janice's
values) are moot for this root and are closed as superseded by §0A.

### 1.2 What the four pushed design commits did — and did not — do

`b1e64ac · 8140802 · efc2237 · 637ab95`: **twelve added files, zero product-code
changes.** Nine documents and three design scripts. The life record, the
catalog, the single writer, the DOB resolver — all designed, none implemented.
The design validator is a coherence check over authored examples; §7 of the
work order is right that it is not integration evidence.

### 1.3 Repair A — what was in the local tree at the start of the review

> **Historical.** This section records the state *before* Batch R: 25 checks,
> a NUL in the module, no explicit removal, no restore gate. **The current
> state is §5A** — 46 checks, both files clean text, every protection
> mutated. Kept as found rather than rewritten.

The uncommitted change is `ui/js/bio-builder-graph.js` (48,595 bytes) and
`tests/test_bb_graph_partial_view_preservation.js` (26,064 bytes). HEAD's blob
`5a977dc8` is packed and GitHub raw timed out twice from the sandbox, so
**the byte-level diff is pending the read-only `git diff` Chris was asked to
save to `.runtime/repairA-graph.diff`**. What follows is from reading the full
local file, running the test, and the author's record of the change; it is not
a review of the diff and is labelled accordingly.

**Reproduced:** `node tests/test_bb_graph_partial_view_preservation.js` →
**25 of 25 pass**, exit 0, Node v22.23.2 + jsdom 27, in the sandbox. Twenty-five
`check(` calls, twenty-five lines printed.

**What the local module does** (`verified_by_read`, agent-traced):

| behaviour | where |
|---|---|
| `_clearBySource` removed; tombstone comment explains the trade | `bio-builder-graph.js:627-646` |
| `syncFromQuestionnaire` is pure upsert | `:405-413` states the accepted consequence: *"a stale node survives until an explicit removal"* |
| id resolution: entry-id match → adopt unclaimed name-derived id → mint distinct id from name+entryId | `:211` |
| per-sync claim set `_syncClaimedIds` | `:377` |
| `_graphRestoreGen` generation guard, stamped `:859`, checked at point of use `:867-874`, bumped on switch `:1046` | |
| `restoreFromBackend` **merges into** memory, does not replace | `:880-897`, `:903-920` |

**Defect found in the local file:** a literal NUL byte at offset 9569, line 211
— `name + "\x00" + opts.entryId`. It parses (`node --check` ok) but `grep`
and `git diff` treat the file as binary. Must become an escape or a visible
separator before commit. **Consequence:** the minted id for same-name entries
depends on this separator; changing it changes those ids. No same-name pair is
known to exist in the working root, but that is `unverified`.

---

## 2. What the finished product will do

### 2.1 One page

An operator opens a narrator and sees one record: the people in their life,
where they lived, what happened and when, and what they have said about it.
They fill in whatever they know, in any order, and stop whenever they like.
Nothing is required, nothing is capped, nothing is deleted by leaving it out,
and nothing is saved by looking at it. A name is kept as typed. A birth date is
one idea whether it belongs to the narrator, their mother or their grandchild;
an approximate date stays approximate all the way to the sentence Lori says.

The narrator's accepted birth date anchors the seven-era life span the product
already has. Their own history may reach back before it. Occurrences —
weddings, moves, service, work — connect people, places and dates without
becoming a second timeline, and none of them appears on the Life Map until an
operator confirms where it belongs.

Lori knows who is alive. She uses people's actual names, never asks for what is
already recorded, and can fetch what she needs without the narrator having to
say it again. A fact typed by an operator is something she may ask about, never
something she narrates as the narrator's memory.

The memoir keeps its three lanes. A narrator's words are stored once, by the
lane that caught them, and are never edited. A package holds everything the
narrator owns and everything it references, restores into a clean installation
as the same person with the same ids, and says out loud what it left out.

### 2.2 Three journeys

**J1 — a new narrator, nothing known.** Operator creates a person. Record has
one person, no events, no scaffold (no DOB → no spine, not a default). Operator
enters a preferred name and "born around 1945". Person gains `birthEventRef` →
a birth occurrence with `text: "around 1945", value: "1945~",
precision: approximate`. The span resolves with `precision: approximate`; ages
render as *"about N"*. Lori's constant required block is one line. Nothing
else exists and nothing has been guessed.

**J2 — a family record with corrections and a conflicting DOB.** Operator
enters the narrator's DOB as 1939-08-30; extraction later proposes 1938 from a
chat turn. One birth occurrence, two date assertions, `conflicted` and
cross-linked; **no `acceptedAssertionId` yet, so the scaffold reports
unresolved** rather than picking one. Operator reviews and accepts A1. Later
the narrator says aloud "I was born in 1940" — that is a **captured** telling
with its own candidate; the operator accepts A3, which supersedes A1 without
deleting it, and the scaffold moves. Meanwhile the operator saves a card that
names only the mother; the father, entered last week, is untouched, because a
partial view is not a deletion. Mentioning the father in conversation puts his
name, relation and **life status** into Lori's turn-scoped block; he is
deceased, and Lori does not use the present tense.

**J3 — export and isolated restore.** Operator exports the narrator. The
inventory selects every lane with a `DbLane`; the closure check refuses if a
trip references a place the package would not carry; the manifest declares
unsaved browser drafts and unassigned media as knowingly excluded. Restore into
an empty root: same ids, byte-identical narrator words, re-export compares
`EQUIVALENT`. **Migrate** is a different button with a different ledger.

### 2.3 The four kinds of thing (and where each stands)

| kind | examples | status today |
|---|---|---|
| **authoritative record** | people, `story_candidates` (verbatim words), trip hierarchy, the new life record | people/trips/candidates **working**; life record **designed** |
| **explicit human approval ledger** | `family_truth_*`, `story_projection` placement, identity change-log, the new `acceptedAssertionId` | existing ledgers **working**; acceptance-id **designed** |
| **rebuildable projection** | `graph_persons/_relationships`, `bio_facts`, `profile_json`, `interview_projections` | graph **broken** (§4); `bio_facts` read path **off** (`READ=0`); others working |
| **source recording** | audio, transcripts, media archive | working; unassigned media **cannot be assigned after upload** (`media_archive.py:408-432`, no `person_id` in PATCH) |
| **installation-owned** | concept catalog (to be), prompts, RAG's two documents, `bio_schema` | catalog **not decided / not built** |

---

## 3. Code-backed map — readers, writers, authority, risk

### 3.1 The graph (Repair A's subject)

| | finding | cite |
|---|---|---|
| server write | **unconditional full replace**: `DELETE … WHERE narrator_id=?` ×2 then plain INSERTs; no `ON CONFLICT`, no version, no expected-previous | `db.py:7958-7959`, `:7963-8002` |
| endpoints | GET/PUT full graph, plus four single-record/delete routes with **zero UI callers** | `relationships.py:81-153`; `api.js:101-106` |
| tables | created imperatively in `_ensure_phase_q1_tables`, **no migration file** | `db.py:7648`, called `:1335` |
| `source` column | `TEXT NOT NULL DEFAULT 'manual'`, no CHECK; values written: `manual`, `questionnaire`, `profile` | `db.py:7667`, `:7695` |
| `created_at` | reset on every save — client omits it, server defaults to now | `db.py:7979`; payload `:783-820` |
| readers | **none on the server.** Not Lori, not Profile Seed, not memoir. The export packages it as `CLASS_DERIVED`; the UI reads it back for itself | grep of accessors; `narrator_data_inventory.py:307-308` |
| tests | the new JS suite only; **no endpoint test** exists | `tests/` grep |
| removal | `removePerson`/`removeRelationship` exported, **no caller anywhere in `ui/`** | `:253`, `:352`, `:1097`, `:1102` |

**The composite risk:** `fullSync` (`:1028`) never awaits `restoreFromBackend`.
A `persistToBackend` that fires while a restore is in flight PUTs whatever is
in memory, and the server replaces the stored graph with it. `_graphRestoreGen`
stops narrator-A data landing in narrator-B; it does **not** stop this. Two
tabs, or a save before hydration, silently truncates the graph.

**And the graph is a dead end.** Nothing consumes it. That is the strongest
argument in this whole review for the life record: the product's only
relationship model is a write-only projection that the design's §2.1 already
classifies as rebuildable. Hardening it is a stopgap; replacing it is the plan.

### 3.2 Writes that fire without an operator save gesture

Ranked by the reviewing agent; every line is the write itself.

| # | writer | write site | trigger | why it matters |
|---|---|---|---|---|
| 1 | `_overwriteBbPersonal` | `session-loop.js:749` PUT, `source: bug227_identity_rescue` | a **heuristic on narrator chat text** (`_hasIdentitySignal`, `:290`) | the only browser path that **overwrites** non-empty `fullName / dateOfBirth / placeOfBirth`, no confirmation, no undo. **Correction, 2026-09-22: DORMANT BY DEFAULT.** It is reached only inside the legacy questionnaire-first walk, which runs only when `localStorage.lv_qf_live_ownership === "1"` (`session-loop.js:123-132`); otherwise the style is routed to warm storytelling. Ranking it first as a *live* writer overstated it. It remains a plausible mechanism for Janice's record **only for the period when that walk was live** (`inferred`, unverified). See D6 |
| 2 | `_syncIdentityToBB` | `bio-builder-core.js:452` via `:1259` | five chat-handler sites in `app.js` | fill-empty-only, but Lori writing `source: ui_save` rows; `questionnaire.py:152` names this function as the reason the route writes no provenance |
| 3 | `_syncPrefillIfBlank` / `_syncDirectTrustedWrite` | `projection-sync.js:435`, `:514` → `_triggerBBPersist()` with **no opts** | extraction prefill | whole-document PUT per prefill; `navigationOnly` absent by construction. Reachability of the `_syncDirectTrustedWrite` hydration path is `unverified` |
| 4 | `resetForNarrator → _persistProjection` | `projection-sync.js:800 → :869` PATCH | **narrator switch away** | **closes the open trace**: this is the `interview_projections` row written on switch. Guarded (hydrated, dirty-only, OCC) and deliberately kept per its header `:747-766`; but `db.py:7152` bumps `version` on byte-identical content |
| 5 | `saveProfile` | `app.js:4663`, auto at `:6385`, `:6455` | end of identity capture | fail-closed on `profileHydration==="server"`, but `update_profile_json` replaces `basics/kinship/pets` wholesale (`db.py:2984`) |
| 6 | `apply_correction` | `projection_writer.py:471 → db.py:7152` | mid-turn, `chat_ws.py:5147` | narrator speech triggers a server write, no operator |
| 7 | `append_projection_suggestion` duplicate path | `db.py:7265` | duplicate suggestion | version churn on unchanged content |
| 8 | `ensure_profile` | `db.py:2946` `INSERT OR IGNORE` | **a GET** — `profiles.py:52`, `chronology_accordion.py:1317` | harmless `{}` row, but literally a load-triggered INSERT |

The two switch-time questionnaire writers (`_resetNarratorScopedState`,
`_personChanged`) are **confirmed draft-only** under `navigationOnly`
(`bio-builder-core.js:647-657`). The single real questionnaire writer is
`questionnaire_persistence._write` (`:559`), reached only through
`merge_whole_document` — OCC, archive, no implicit removals.

### 3.3 Chronology — three findings that correct the design

**(a) The scaffold reads DOB from `profile_json`, not the questionnaire.**
`chronology_accordion.py:1022` `dob = basics.get("dob")`, where `basics` is
`profile_json` (or `build_profile_from_promoted` when `truth_v2_enabled`,
`:1319-1331`). The questionnaire's `personal.dateOfBirth` is only a **Lane B
anchor** (`:599-605`) — it never enters the span arithmetic. So the
questionnaire DOB and the profile DOB can disagree, and the eras follow the
profile. `people`, `bio_facts`, `interview_projections` are **not** read.

**(b) The span has no end at all — not `today()`, not death.** `later_years`
is `ageEnd: null` (`lv-eras.js:95-96`); `chronology_accordion.py:126` leaves
`end_year None`; there is **no `date.today()` anywhere in the file**. "Today"
is a separate bucket appended at `:136-152`, *"never one that birth-year
arithmetic produces."* `dateOfDeath` enters only as an anchor (`:564`, `:591`,
`:604`) and **truncates nothing**. The only `deceased` flag in the system is on
`graph_persons` (`db.py:7665`), which chronology never reads.

> **Design correction.** `WO-LIFE-RECORD-01` §2A says the living narrator's
> endpoint is "computed at render". The product does no such thing — it leaves
> the span open. The contract must be restated as: *the existing scaffold is
> open-ended; this design ADDS truncation at a known death date, and must
> decide whether a living narrator's end stays open (current behaviour) or
> becomes a computed present. It does not "preserve" a computed endpoint that
> does not exist.*

**(c) Age arithmetic already exists twice, and one copy is right.**
`life_spine/validator.py:110-130` `compute_age()` does correct calendar
arithmetic (month/day comparison, July-1 midpoint for year-only).
`age_arithmetic.py:141-142` deliberately subtracts years, with a documented
rationale (`:119-122`). `lv_eras.py:443` subtracts years for era lookup.

> **Design correction.** The validator's `age_at` is a **third** implementation.
> Implementation must reuse `validator.compute_age`, not add another.

The placement rules are **verified intact**: `story_projection.py:154-169`
raises rather than infers an era; `_VALID_PLACEMENT_SOURCE` closed set at
`db.py:8428`, enforced `:8525`; unplaced ≠ Today at `story_projection.py:36-39`,
`:198-205`.

### 3.4 Lori delivery — the death defect's fifth location

`saved_biography` **drop_order 35**, `saved_biography_detail` **38**
(`prompt_section_policy.py:186-188`, `:217-219`); `identity_facts` and
`identity_grounding` `TRIM_NEVER` (`:176`, `:181`). The rule text is at
`:367-370` and enforced by `_BANNED_RATIONALES` (`:376-380`).

**No life status reaches Lori by any path, and one path removes it on
purpose.** Zero hits for `deceased|lifeStatus|passed away|dateOfDeath` across
the prompt pipeline; and `questionnaire_for_lori.py:158`
`_SKIP_FIELDS = {"_entryId", "deceased"}`, commented *"Bookkeeping that is not
biography."* Someone decided a person being dead was not biography. That is
the defect in `BUG-LORI-UNAWARE-OF-DEATH-01`, at its root.

### 3.5 Memoir, trips, media — prior claims verified

- **Memoir:** three lanes, `memoir_contract.py:87-115`, `memoir_export.py:822-830`;
  verbatim rule `:1092`; `grep -c questionnaire` → **0** in both files. No writer.
- **`trip_bio_suggestions` is dead:** sole writer hardcodes `field_key="travel.trip"`
  (`trip_timeline_bridge.py:200-207`); FK to `bio_fields` (`0011:103`); no
  `travel.*` key seeded anywhere; content never SELECTed — only counted.
- **Unassigned media:** `owner_predicate` is `person_id = :pid`
  (`narrator_data_inventory.py:662-663`), so NULL rows never export; and **no
  API can assign a `person_id` after upload** — the PATCH model has no such
  field (`media_archive.py:408-432`). Unassigned means permanently unassigned.
  This sharpens §2B: the shared-row question is not only "which database" but
  "there is no path to ever own it."

### 3.6 Not inspected, and why

`extract.py` beyond `EXTRACTABLE_FIELDS` and the bio router (11k lines — the
two repository reviews covered its bio routing; its narrative-field lanes were
not re-read); `chat_ws.py` turn handling beyond the two write sites cited;
`trip_repository.py` beyond the suggestion stub; the RAG tables (two fixed
documents, unchanged); `lori_witness_mode`; the guard/authority registry;
`narrator_merge_apply` beyond its FK closure; every `DbLane` individually
(79 — the graph and media lanes were read; the rest are relied on from the
inventory's own structure). The Repair A byte diff (§1.3).

### 3.7 Minimal coherent change surface

Not a refactor. In dependency order:

1. **Graph** — finish Repair A (§4).
2. **Identity writers** — `_overwriteBbPersonal` and `_syncIdentityToBB` need
   an operator gate or a provenance that Lori's writes cannot masquerade as.
   Small, product-visible, independent of the model.
3. **Concept catalog** — new module + loader + fail-closed checks against the
   four real producers. Touches `questionnaire_schema.py` (extend its
   fail-closed pattern), `extract.py` (`EXTRACTABLE_FIELDS` consumes the
   catalog), `projection-map.js`, `bio_schema.py`.
4. **Life record** — new tables (by migration, not `_ensure_*`), the single
   writer, `DbLane` entries, resolver reusing `compute_age`.
5. **Consumers** — `questionnaire_for_lori.py` stops skipping `deceased`;
   required-facts block into `identity_facts` territory; Profile Seed
   predicates from the catalog.
6. **Package** — new lanes, closure check, manifest exclusions, migrate path
   separate from restore.

---

## 4. Repair A verdict

**Not ready to commit as it stands.** It fixes what it set out to fix, and the
fix is real and tested. It leaves three things that §3 of the work order names
as requirements.

**What it fixes, with evidence:** the mother-only view no longer deletes the
father (checks 6-9); an empty questionnaire deletes nobody (5); entry ids are
adopted rather than duplicated (15-17); renames keep ids and edges (18-20);
same-name entries stay distinct (24-25); a late response for another narrator
is refused (12-14). Those are the defects that lost data, and they are closed.

**What blocks it:**

1. **Intentional deletion is now impossible.** Before: removing an entry from
   the questionnaire removed the graph node — as a side-effect of the very
   clear-and-rebuild that lost the father. After: pure upsert, and the only
   removal functions have no UI caller. So a person the operator removes from
   the form lives in the graph forever. §3 requires *"intentional deletion is
   still possible and scoped to the selected entity."* Not tested, because it
   cannot happen. The fix is small and is exactly §3.10's *"`remove` explicit
   and separate from `set`"*: an explicit remove signal from the questionnaire
   (entry deleted, not merely absent) that the graph honours.
2. **The restore/persist race is open, and the server makes it destructive.**
   `fullSync` never awaits `restoreFromBackend`; the server PUT is full
   replace with no version check. Check 13 covers stale-GET-over-fresh-GET; it
   does not cover PUT-during-GET. Either `persistToBackend` awaits a settled
   restore for the current generation, or the PUT carries a version the server
   checks. The first is a few lines in the module; the second touches
   `db.py:7958` and is the better fix but is product-code beyond Repair A.
3. **The NUL byte** at line 211, with the id-stability note in §1.3.

**Also true, not blocking:** `restoreFromBackend` merges into memory rather
than replacing, so a stale local node can be re-PUT — that is the resurrection
risk §3 names, and it is what (2) prevents.

**If accepted after those three, Chris would commit separately:**
`ui/js/bio-builder-graph.js` + `tests/test_bb_graph_partial_view_preservation.js`
(+ whatever small change carries the explicit-remove signal from the
questionnaire module), on their own, not bundled with design.

**Reliance:** the diff itself has not been read (§1.3). The verdict rests on the
full local file, the reproduced test run, and the author's record. If the
saved diff shows anything the agent's read missed, this section changes.

---

## 5. One integrated plan

### 5.1 Decisions needed **now** (they gate Batch A)

| decision | recommendation | consequence |
|---|---|---|
| **D1** the 26 `NEEDS_CONCEPT` groups and 41 questionnaire-only fields | per the decision sheet, corrected for the "(10)" miscount (it is eight; derive from the ledger) | defines the catalog; the health split changes what extraction may write |
| **D2** grandchildren and prior partners | **ordinary people**, time-aware relationships, a child may exist without every parent | adds person records; changes nothing in Lori until D5 |
| **D3** health reflections vs clinical facts | reflections as stories; `majorCondition`/`currentMedications` **retired from extraction** | changes Lori's noticing; the one to decide deliberately |
| **D4** `trip_bio_suggestions` | **delete the stub** (dead, FK-blocked, never read) | removes a phantom writer; no data effect |
| **D5** span endpoint for a living narrator | **keep it open** (current behaviour); add death-date truncation only | smallest change to a working engine; matches §3.3(b) |

### 5.2 Decisions safely **deferred**

Shared vs per-narrator SQLite (§2B, with the sharpened unassigned-media
finding) · typed occurrences canonical vs derived index · package encryption ·
exact eleven-topic UX beyond field coverage · `readingAbility` and
`dailyRoutine`.

### 5.3 The batches, with gates

**Batch 0 — close the review.** Fix the six design defects in one pass:
proposition identity for conflict (subject + concept + context, not list
length), date-assertion provenance, `birthEventRef` type+subject check,
narrator retelling as captured, decision-sheet counts derived, `biography.json`
declared a derived view of the JSONL. Reconcile §2A to §3.3(b) and (c). **Gate:**
the DOB fixture passes the full model rules; validator + mutations green; but
this gate is documentation of coherence, not product evidence.

**Batch R — finish Repair A** (§4's three items). **Gate:** an explicit-remove
test, a PUT-during-restore test, no NUL, 25 + new checks green, then a
Chris-owned commit. Also **the identity writers**: gate `_overwriteBbPersonal`
behind operator confirmation or retire it; give `_syncIdentityToBB` a
provenance that is not `ui_save`. **Gate:** no browser write to
`bio_builder_questionnaires` without an operator gesture or a distinguishable
source. This makes the tree clean for what follows.

**Batch A — catalog and authority.** Real loader, real fail-closed checks
against the four real producers and the consumers (Profile Seed predicates,
`questionnaire_for_lori`). `bio_facts` FK preserved. Every concept names an
owner and a `DbLane` or an intentional exception. **Gate:** every
`EXTRACTABLE_FIELDS` key resolves; the 69 homeless are gone by define / alias /
retire per D1; `suggestion_review` queues nothing undeliverable.

**Batch B — canonical record and safe writes.** Tables by migration; the
single writer with per-path `expectedPrevious` and all-or-nothing; explicit
`acceptedAssertionId`; `birthEventRef` validated; resolver reusing
`compute_age`. **Physical layout unchanged.** **Gate:** the §7 fixture families
against the real writer and real SQLite, in an isolated root.

**Batch C — the full questionnaire.** Field-level, uncapped, no write on
open/switch, explicit remove, stale drafts cannot win. **Gate:** the harness
drives the real UI; the PUT body is what is asserted.

**Batch D — consumers.** `questionnaire_for_lori` stops dropping `deceased`;
required-facts block lands in `TRIM_NEVER` territory with the measured ceiling;
retrieval for the rest; Profile Seed reads the catalog; chronology gains
death-date truncation only. **Gate:** parent death and living spouse in the
**assembled prompt under budget**; no unsolicited death prompt; unpromoted
event absent from the Life Map.

**Batch E — package.** New lanes; closure check; manifest exclusions for
drafts and unassigned media; migrate separate from restore. **Gate:** export →
isolated restore → re-export `EQUIVALENT`, on synthetic data; original
packages untouched.

### 5.4 What must never happen (stop conditions, restated from §7)

Any write to `lorevox_data` outside a Chris-approved batch — **Janice's real
record is in it.** Any change to a narrator's words. Any era from a year or
an age. Any restore that remaps. Any package that omits an owned lane without
refusing.

---

## 5A. Batch 0 and Batch R — executed 2026-09-22 on Chris's go-ahead

One consolidated handoff, per the execution rhythm in §0. Every number below
was produced in this sandbox and can be reproduced with the commands given.

### Batch 0 — the six design defects, closed

| defect | fix | proof |
|---|---|---|
| conflict inferred from list length | `proposition_key` = (concept, context); competing means same proposition, different value, both live; must be **linked** or **adjudicated** by `acceptedAssertionId`. Statuses no longer decide | case 11 (successive jobs) holds; case 12 (accepted beside retained) holds; DOB fixture through full `run()` at every stage |
| date assertions escaped provenance | classification by **location**: anything inside `dateAssertions` is an assertion | refusal "hiding among dates" |
| `birthEventRef` followed anything | `anchor_event` checks type, subject, ambiguity; resolver returns `available: False` + reason | refusals "someone else's wedding", "another person's birth"; contract asserts `ref_is_union…` / `subject_is_someone_else` |
| a third age implementation | `age_at` delegates to shipped `life_spine.validator.compute_age`; coarse dates bounded by calling it at the year's extremes | 31 before birthday, 32 on/after, "31 or 32" for a year-only event |
| spec described a computed endpoint the product lacks | §2A rewritten: span is **open** (D5); design adds death-date truncation only; DOB source is `profile_json` today; ages reuse `compute_age` | — |
| retelling labelled authored; `biography.json` vs JSONL | §2.6 three-row table (narrator aloud = captured; curation edit = not a story; operator note = authored); §3.11 `biography.json` is a **derived view the importer never reads** | case 10 already modelled it right |

Also: a bug in the new conflict rule caught by its own refusal set —
`None in {None}` read a missing id as a recorded decision. Fixed and mutated.

**Counts derived, not typed.** `build_concept_catalog.py` now groups the 41
questionnaire-only fields mechanically and labels every output `measured`
or `proposal`. Derivation found **three** hand-count errors in the decision
sheet's §4 table, not one: 8 not 10, and two groups of 4 written as 3. The
sheet is corrected from the ledger and its rows sum to 41.

**State:** `19 rules · 12 situations · 20 refusals · 11 contracts — DESIGN
COHERENT`; **31 mutations, all caught**; 195-row per-path ledger in
`--json`.

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/validate_life_record_design.py
PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/mutate_life_record_checks.py
PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/build_concept_catalog.py
```

### Batch R — Repair A, finished

| blocker (§4) | what landed | where |
|---|---|---|
| NUL byte | `""` escape; file is text again | `bio-builder-graph.js` (was line 211) |
| no explicit removal | `removeByEntryId(entryId)`; `fullSync({removedEntryIds})` applies removals after sync, before persist; **tombstones** by entry id so a stale draft cannot resurrect; `upsertPerson` returns a detached placeholder for a tombstoned entry (callers dereference `.id`); `upsertRelationship` refuses edges to it | `_tombstones`, `removeByEntryId`, `upsertPerson`, `upsertRelationship`, `fullSync` |
| PUT during restore | `_restoreInFlight {gen, pid, promise}`; `persistToBackend` waits for a pending restore of the same narrator+generation, **drops** the PUT if the generation moved while waiting, and stays synchronous when nothing is pending | `persistToBackend`, `_putGraph`, `restoreFromBackend` |

**Test:** `node tests/test_bb_graph_partial_view_preservation.js` → **36 of 36**
(25 prior + 11 new: explicit removal ×3, no resurrection ×3 including the
never-synced case, PUT-during-restore ×3, drop-on-switch, no-NUL).
**Five mutations against the module, all caught** — the first version of
the never-synced tombstone mutation survived until a test for that path was
added, which is the pattern working as intended.

Neighbouring suites unchanged: `test_bb_operator_intent_attribution` 8/8,
`test_operator_intake_write_safety` 4/4, `test_questionnaire_save_outcome`
all, `test_bio_builder_save_sequences` all.

**Scope finding that narrows blocker #1.** The questionnaire UI has **no
remove-entry control** — an "Add entry" button (`bio-builder-questionnaire.js:1287`)
and nothing to take one away — and the PUT request model has **no `removals`
field** (`questionnaire.py:42-66`), although `merge_whole_document` accepts
one. So the old clear-and-rebuild was never a deletion feature; it was a
graph-only phantom that dropped nameless rows the server still kept. **The
graph's half of explicit removal is now built and tested. The route field and
the UI control are Batch C**, and until they land a page reload re-hydrates a
removed entry from the questionnaire document. The module comment says so.

**Id stability note:** the same-name separator change alters minted ids for
same-name entries. The working root is empty (§1.1a), so nothing is affected.

**Identity writers — assessed, no code change, and the reason.**
`questionnaire.py:154-167` already names `_syncIdentityToBB` and
`_syncPrefillIfBlank` as Lori's writers, deliberately writes **no provenance**
for the shared PUT because of them, and assigns their fix to **WO-03B**'s
propose operation — which is this design's `needs_verify` path. That is
Batch B work with an existing home; relabelling a source string would change
nothing. **Proposal for `_overwriteBbPersonal` (`session-loop.js:749`)**, not
landed because it changes live chat behaviour: route it through the same
propose operation as a `needs_verify` candidate instead of a PUT, so a
misheard name becomes a review item rather than an overwrite of protected
identity. One decision for Chris (**D6**).

### Batch R follow-up — three more holes in the same boundary (external review)

The first version of the restore/persist gate stopped a *premature* PUT and
nothing else. Review reproduced three ways it still lost data, each against
the exported functions; all three are now fixed, tested and mutated.

| hole | what happened | fix |
|---|---|---|
| **edit lost to restore** | operator typed a new occupation while the GET was pending; the GET returned the old one; the handler did `g.persons[id] = server`; the queued PUT sent OLD | records written locally since the restore began (`_touchedSinceRestore`) keep their non-empty fields; the server fills only what is empty |
| **failed restore released a partial PUT** | GET returned 503; the queue released; the PUT sent the partial graph as a full replacement — the original mechanism through a new door | the queued PUT runs only when the restore's `outcome` is `ok`; a narrator whose last restore failed (`_restoreFailedFor`) refuses **every** persist until a restore succeeds |
| **wrong narrator, generation unmoved** | narrator id changed with no switch hook; queued PUT sent B's in-memory graph to A's endpoint | the continuation re-checks the **active narrator id**, and `_putGraph` checks it again at send time |

Also: **the test file itself carried a literal NUL** — inside the check that
asserts the module has none. Now `String.fromCharCode(0)`.

**Test:** **43 of 43** (36 + 6, + 1 after review found the never-synced case's "no edge" check was inspecting the wrong graph — an ordering slip from inserting it between a check and its follow-on; fixed and mutated). **Mutations:** the three new protections each
turn red when reverted; the two narrator-id guards are **redundant by design** —
either alone holds, and only removing both lets B's graph reach A's URL, which
is what the mutation now checks.

### Batch R follow-up 2 — Yes / No / not said (external review)

Review found an operator's deliberate **No** to `deceased`, made while a
restore was pending, lost to the server's older `true`: the merge kept a local
value only if it was not `false`. The obvious fix — let every local `false`
win — was also wrong, and the reviewer said so: the questionnaire mapping
produced `false` for an **absent** field (`p.deceased === "Yes" || …`), so
"nobody asked" would have overwritten "deceased".

**Fixed at both ends.** `_triState` maps Yes/true → `true`, No/false →
`false`, anything else → `undefined`, which means *leave it alone*. It is used at
all three sites that fed the graph (parents, spouse, profile kinship).
`_touchedSinceRestore` now records **which fields** a local write supplied,
with booleans counting when defined. `_mergeUnderLocal` restores exactly those
fields, `false` included, and takes everything else from the server.

**Test: 46 of 46** (+3: explicit No survives; not-said does not overwrite
`true`; explicit Yes survives). **Four new mutations caught**, including the
reported defect itself; the six earlier protections were re-mutated and all
still hold. Neighbouring suites unchanged.

**The limit this does not remove, and where it goes.** The graph *store* is
two-state: `graph_persons.deceased INTEGER NOT NULL DEFAULT 0` (`db.py:7665`),
written as `1 if p.get("deceased") else 0` (`db.py:7975`), and the client
serialises `!!p.deceased`. So a **new** person whose deceased field was never
answered is still stored as `0`, as it always has been. What changed is that a
restore merge no longer turns not-said into an overwrite. Representing
*unknown* durably needs a tri-state column, and that is the life record's
`lifeStatus: deceased | explicitly_living | unknown`, in **Batch B**. The
server is not touched in Repair A.

**What this suite does NOT establish, stated plainly:** `fetch` is simulated.
Nothing here proves server-side concurrency protection. The server PUT
remains an unconditional full replacement with no version check
(`db.py:7958`), and the browser now refuses to exploit that in the four ways
found so far. A version check on the server is the durable fix and is Batch B.

**Verdict: Repair A is ready for a separate, Chris-owned commit.**

### Suggested commit grouping (Chris runs these; nothing is staged)

```bash
cd /mnt/c/Users/chris/hornelore
git add ui/js/bio-builder-graph.js tests/test_bb_graph_partial_view_preservation.js
git commit -m "bio-builder graph: a routine sync never deletes; removal is explicit; a save cannot outrun or outlive its restore" -m "Pure upsert replaces clear-and-rebuild, which deleted a father when the saved card carried only the mother. removeByEntryId with tombstones, so a stale draft cannot resurrect a removed entry. Because the server PUT is an unconditional full replace: a persist waits for an in-flight restore of the same narrator; a record edited while the restore was pending keeps the edit; a failed restore blocks every persist until one succeeds; the queued PUT re-checks the active narrator id, not only the generation. Restore merges by field written, so an explicit No survives and an unanswered field overwrites nothing. Same-name entries mint distinct ids. 46 checks; every protection mutated. Route removals field and UI control are owed (Batch C); a server-side version check is owed (Batch B)."
```

```bash
cd /mnt/c/Users/chris/hornelore
git add scripts/design/validate_life_record_design.py scripts/design/mutate_life_record_checks.py scripts/design/build_concept_catalog.py docs/wo/WO-LIFE-RECORD-01_Spec.md docs/specs/CONCEPT-DECISION-SHEET-2026-09-22.md docs/wo/WO-HORNELORE-INTEGRATED-LIFE-RECORD-01_CHECKPOINT-01.md
git commit -m "design: close the six review defects; checkpoint 1 with the narrator cleanup" -m "Conflict is a property of propositions, not list length; date assertions classified by location; birthEventRef must be a birth event whose subject is that person; ages reuse life_spine.validator.compute_age; the span is open as shipped and the design adds death-date truncation only; a narrator's spoken correction is captured, never authored; biography.json is a derived view. Decision-sheet counts now derived (three hand-count errors found). 19 rules, 12 situations, 20 refusals, 11 contracts; 31 mutations caught. Checkpoint records the authorized working-root cleanup: three hard deletes, zero people remain."
```

## 5B. Batch A — A1 and A5 landed; A2–A4 held for the baseline eval (2026-09-22)

### A1 — the concept catalog

**One authority, compiled.** Human judgements live in
`server/code/api/services/concept_catalog_source.py` as small tables:

- whose fact each section holds (`SUBJECT_BY_SECTION`);
- what each field means (`CONCEPT_BY_FIELD`, with per-path overrides);
- which asking key and Profile Seed path read which concept;
- what was retired, and by which decision.

`scripts/catalog/compile_concept_catalog.py` compiles those tables, together
with the measured vocabularies and Chris's recorded decisions, into
`concept_catalog_v1.json`. The compile is deterministic, and a test fails if
the committed file differs from a fresh compile.

**Loader:** `concept_catalog.py`, standard library only. It is fail-closed on
load: every concept must *state* all four D1f properties, none defaulted,
enums must be valid, bindings must resolve, and no path may be bound twice.

**Contents** (after D11, 2026-09-22; re-derive with
`python3 scripts/catalog/compile_concept_catalog.py`, never copy forward):
- 84 concepts.
- 195 legacy paths: 16 retired outright, 5 retired from extraction only (D11),
  each with its decision.
- 84 asking keys.
- 69 Profile Seed evidence rows.
- **29** profile_json keys. *(This said 30. The file had 29; the reviewer
  counted the JSON and caught it — a hand-carried count, the exact failure
  this work exists to remove.)*
- 13 decided aliases, recorded path by path.

**The build gate:** the compile refuses if any decision it depends on is not
`approved`, if any producer key is unbound, or if a decided alias joins two
different facts.

**Tests:**
- `tests/test_concept_catalog.py`: **38 tests, 0 skipped** (32 at A1; +6 for D11 and D1e). Coverage is
  checked against the real producers imported independently; the drift test,
  the loader refusals, the compiler refusals and the decided semantics each
  name their decision.
- `tests/test_concept_migration_plan.py`: 12 tests.
- `scripts/catalog/mutate_concept_catalog.py`: **25 mutations, all caught**
  (17 at A1; +8 for the D11 extraction-retirement rules and the D1e occurrence
  binding). The first
  version of the "property may not default" test **survived** its mutation: it
  accepted any message that mentioned the property's name, so the value checks
  hid the absence. It now asserts the specific message.

### A5 — the migration plan

`concept_migration_plan.py` accounts for every leaf of a legacy questionnaire
document or profile_json **exactly once** as one of:

- `mapped`;
- `derived_not_migrated` (zodiac);
- `retired_value_kept`: **retiring a field is not permission to lose what
  someone typed into it**;
- `unmapped_value_kept`;
- `empty`;
- `bookkeeping`.

The invariant `rows == leaves` is tested and mutated. A blank `deceased`
stays empty; it never becomes "living". The fixture's shape is read from the
shipped schema.

### A2 — built, then deliberately held

Translating the 13 decided aliases in `suggestion_review.split_destination`
works, and makes every destination decision (acceptance, decline, the review
key, suppression) agree. But once those paths became defined, the existing
`test_extractor_vocabulary` guard examined them and found `family.spouse.*` has
no `"repeatable": "spouse"` marker, although the form's spouse section is
repeatable. That marker drives `_repeatableGroup` (`extract.py:7671`), which
changes extraction output. Fixing it is therefore an extractor change, and it
must follow the baseline. **The translation was reverted, and
`suggestion_review.py` is unchanged.** A2 lands together with A3 as one
extractor batch. The alias pairs themselves stay in the catalog as inert,
tested data.

### `r6-batchA-base2` — the valid pre-A2 baseline (B0), read 2026-09-23

**Run identity** `[verified_by_read: master_loop01_r6-batchA-base2.json run_metadata]`: `d446c3f`, **dirty**,
scorer `318df0d2ff1f`, case bank `b487e54cd84d`, `HORNELORE_EXTRACTION_BOUNDED=True`,
`MAX_NEW_TOKENS_EXTRACT_COMPOUND=384`, 146 extractable paths. Zero `PROMPT_TOO_LARGE` after the 23:40
restart (the 55 the whole-log grep counted are all from the void run, last one 23:28:22).

| | `r5k-guard-v2` (`5afead5`, clean) | **`r6-batchA-base2`** |
|---|---|---|
| pass | 71/114 | **62/114** |
| v3 / v2 | 44/72 · 39/72 | **37/72 · 32/72** |
| must_not_write | 0 | **0** |
| must_extract recall | 0.679 | 0.633 |
| should_ignore leak | 0.176 | 0.118 |
| extractable paths | 140 | 146 |

**Same scorer and same case bank, so this delta IS comparable** — unlike the r5h/r5j/r5k comparisons
CLAUDE.md warns about. 11 lost, 2 gained (`case_075`, `case_107`).

**Cause of the drop `[verified_by_execution: raw_items diff, both reports]`:** the lost cases' r5k
outputs contain paths that are no longer in `EXTRACTABLE_FIELDS`. WO-04 renamed/retired them
**without (a) updating the extractor prompt, (b) adding compatibility redirects, or (c) migrating
the case bank.**

| Retired path | Lost cases | Still taught by the prompt? |
|---|---|---|
| `family.marriageDate` | 004, 012, 023, 072, 076 | **yes** — few-shots `extract.py:793-799`, `:1237-1242`; rule `:1804-1805` ("Do NOT drop family.marriageDate") |
| `faith.values` | 036 | **yes** — few-shots `:851`, `:1305` |
| `personal.notes` | 041 | **yes** — guidance `:980`, `:1114` |
| `residence.period` | 050 | no |

The other four losses are output drift, not rejects: 007 (value changed), 069 (full-sentence values),
114 (model emitted `personal.birthPlace`), 072 also lost `birthOrder`.

**The case bank still scores the retired paths** `[verified_by_execution]`: must_extract/may_extract
entries on paths absent from `EXTRACTABLE_FIELDS` — `family.marriageDate` 9 (7 must_extract),
`military.significantEvent` 2, `faith.values` 2, `residence.period` 2, `personal.culture` 2,
`military.yearsOfService` 1, `military.deploymentLocation` 1, `faith.significantMoment` 1,
`family.marriagePlace` 1, `travel.significantTrip` 1. **The scorer matches paths exactly**
(`fp in extracted_map`, `run_question_bank_extraction_eval.py:~960`; no alias table), so **the D12
redirect alone will NOT recover these cases** — the extractor will emit `marriage.marriageDate` and the
bank will still expect `family.marriageDate`.

**Worse, the bank encodes the subject-identity defect:** `case_033` expects
`military.significantEvent` / `military.yearsOfService` / `military.deploymentLocation` for a
**great-grandfather's** Civil War service — i.e. it rewards `_ANCESTOR_MIL_DUP_MAP`. Removing that map
(A3) will drop `case_033` against the current bank. That drop is correct; the expectation is wrong.

**Consequence for A3 — the change set must contain four things together, or the eval cannot be read:**
1. prompt: every few-shot and rule text moved to canonical paths (no retired path taught);
2. compatibility redirects per D12/D13;
3. **case-bank migration** of the retired truth paths, as its own commit, bumping `case_bank_version`;
4. **re-score the stored `r6-batchA-base2` outputs under the migrated bank** before running A3 live, so
   bank movement and extractor movement are separated (same discipline as BACKLOG §6a).

**Output/parse metrics (B0)** `[verified_by_read: api.log from 23:40]`: 115 extraction calls (114 cases
+ 1 runner warmup probe, `run_question_bank_extraction_eval.py:395`) · direct parse 96 · **salvaged 19** ·
rules fallback 13 · not-in-vocab rejects **143** · turnscope drops 45 · kinship quarantines 36 ·
subject-filter strips 2.

*Salvage cause, corrected 2026-09-23 after B1 (this line said "18 at `max_new=384`"):* a salvage is a
**cap truncation** only when the parse error sits at the end of the output. By that test B0 has
**14 truncated at 384** + **1 at 128** (the negated-military empty-value list) + **1 premature stop**
(`germany_years`, which ends at exactly 1,100 chars in **both** B0 and B1 — the model stopped there itself; the cap
did not) + **3 internally malformed** (`# comment` inside the JSON: parenthood ×2 and marriage_children, errors at
char 395/395/628 of 1,271–1,473). Classes are defined in the B1 section below.

**Measurement series, agreed 2026-09-23 (Chris + reviewer):**
- **B0** = this run (bounded, compound cap 384).
- **B1** = B0 with **only** `MAX_NEW_TOKENS_EXTRACT_COMPOUND=768` — no code change. Compare direct-parse,
  salvage count, rules fallback, recall, rejects, wrong-subject drops, generated tokens, latency, and
  whether output grows *more verbose* rather than more correct.
- **B2** = A2/A3 (after the case-bank migration and B0 re-score).
- **B3** = A4 relevance-scoped catalog. 768 fixes output capacity; A4 fixes input choice. Each is
  measured on its own.

### `r6-batchA-b1-768` — B1, the output cap alone, read 2026-09-23

**Run identity** `[verified_by_read: report header]`: `b39e971`, **clean**, scorer `318df0d2ff1f`, case bank
`b487e54cd84d`, `MAX_NEW_TOKENS_EXTRACT_COMPOUND=768`, everything else as B0. Log window `api.log` from
line 272,722. Prompt unchanged: same 146 paths, catalog 9,116 chars, same few-shot counts per call;
compound budget 6,912 (was 7,296); zero `PROMPT_TOO_LARGE`.

| | B0 (384) | **B1 (768)** |
|---|---|---|
| pass | 62/114 | **63/114** |
| v3 / v2 | 37/72 · 32/72 | 37/72 · 32/72 |
| must_not_write | 0 | 0 |
| must_extract recall | 63.3% | 63.8% |
| may_extract bonus | 27.1% | 28.6% |
| should_ignore leak · wrong_executable | 11.8% · 23 | 11.8% · 23 |
| average score | .713 | .718 |
| correct executions · missing | 116 · 52 | 117 · 51 |
| stubborn pack `truncation_starved` | 3/7 | 3/7 |
| direct parse / salvaged | 96 / 19 | **105 / 10** |
| salvage (a) probable output exhaustion, compound cap | 14 | **3** |
| salvage (a) probable output exhaustion, 128 cap | 1 | 1 (same negated-military list) |
| salvage (b) premature incomplete — stops mid-JSON well below the cap | 1 | 2 |
| salvage (c) internally malformed — invalid syntax before the end | 3 | 4 |
| report `truncation_rate` | 0.0% | 0.0% — **structural, see below** |
| rules fallback | 13 | 13 |
| items extracted | 393 | 422 |
| not-in-vocab rejects | 143 | **179** |
| turnscope drops · kinship quarantines | 45 · 36 | 55 · 44 |
| `family.marriageDate` rejects | 8 | 9 |
| case time, mean · max · total | 20.3 s · 54 s · 38.6 min | **22.2 s · 99 s · 42.3 min** |

**Reading** `[verified_by_execution: case_results diff and raw-output diff, both runs]`:

**B1 result:** raising the compound output ceiling from 384 to 768 reduced probable cap-exhaustion events from
14 to 3, but produced **no demonstrable score improvement**; the observed +1 case is consistent with ordinary
run-to-run model variation. Contract performance and safety metrics were unchanged. Keep 768 fixed through
B2/B3 to reduce output-cap confounding; **production token policy remains undecided.** Output allowance is not
the principal remaining problem.

**Salvage classes** `[verified_by_execution: parse-error position vs output length, each salvaged call, both
windows — B0 from 23:41:09, B1 from line 272,722]`. The parser calls all of these `salvage_truncated`; that is a
recovery mechanism, not a diagnosis.
- **(a) probable output exhaustion** — parse error at the last character, output length near the cap
  (B0 1,178–1,503 chars at 384; B1 2,447 / 2,846 / 2,909 chars at 768). *Probable*, because token counts are not
  logged; B1's 2,447-char case is pretty-printed over 110 lines, which is token-dense.
- **(b) premature incomplete** — ends mid-JSON far below the cap. `germany_years` stops at exactly 1,100 chars in
  **both** runs (so the 384 cap never caused it); B1 `siblings` stops at 1,061 chars under a 768 cap.
- **(c) internally malformed** — a Python-style `# comment` inside the JSON: parenthood ×2 (char 395), marriage_children
  (char 628), and in B1 family_life (char 402 of 2,040). More tokens cannot repair these.

**The report's `truncation_rate: 0.0%` is structural, not measured** `[verified_by_read:
run_question_bank_extraction_eval.py:1910-1912]`: it counts "truncat" in the per-case method tag, and the extractor
never emits one, so it reads 0.0 whatever happens. Likewise `truncation_starved` is a historical label for the
**VRAM-guard** long tail (`:113`), not for the output cap — so 3/7 → 3/7 is consistent with, not proof against, the
cap reading above. Salvage class must be counted from `api.log` until a scorer change surfaces it.

**115 calls = 114 cases + the runner's warmup probe** `[verified_by_read: run_question_bank_extraction_eval.py:395-420]`:
the probe POSTs to the same `/api/extract-fields` with `"My name is Janice."`, `personal_identity`,
`personal.firstName` — the first call in each log window (B1 07:38:09).

1. **768 does what it says.** Probable cap exhaustion falls from 14 to 3.
2. **It buys no score.** The only case that changed is `case_073` (0.50 → 1.00), and that is **run-to-run
   noise, not the cap**: its two outputs diverge at character 68, far below the old cap. Across all 115
   calls, **11 outputs diverge from B0 inside the text both runs could have produced** — including a
   `health_and_body` call whose cap (128) did not change. Decoding here is not deterministic
   (`temp=0.01, top_p=0.90`), so **±1–2 cases is inside the noise band** for every later comparison.
3. **The extra room went to material that is then thrown away.** +29 items, but +36 not-in-vocab rejects,
   +10 turnscope drops, +8 quarantines, recall +0.5 pt. It is more output, not more correct output — the
   verbosity the reviewer asked us to watch for.
4. **It costs time.** Mean case +10%, total run +3.7 min, worst case 54 s → 99 s (`case_039`, one of the three
   calls that still hit 768). Extraction shares the GPU with Lori, so a 99 s extraction is a delay she can feel.
5. **The losses are not capacity.** They are the retired paths (marriage date now 9 rejects), wrong-branch
   output and malformed JSON. That is A3 and A4, not the cap.

**Decided 2026-09-23 — 768 is an evaluation-control setting, not a production decision.**
`MAX_NEW_TOKENS_EXTRACT_COMPOUND=768` stays **fixed through B2 and B3**. Not because it performs better — it has
not been shown to — but because it removes most probable cap exhaustion (14 → 3), so an improvement B2/B3 makes
to a schema path, alias, relevance rule or subject binding cannot be hidden by later facts being cut off. The
validators contained the extra output (+29 items; wrong_executable 23 → 23, leak 11.8% → 11.8%, must-not-write 0),
so 768 is a safe temporary ceiling. **No 1024 run. The 128 single-field cap is not raised** — its one exhaustion
in either run is the negated-military list of empty fields, every item rejected, no fact lost.

Sequence: **B0** = 384 baseline · **B1** = 768, cap exhaustion down, no demonstrated score gain · **B2, B3** = stay
at 768 · **after B3**, a separate measured step on responsiveness: 128/384 plus evidence-triggered retry against a
fixed 768, scored on accuracy **and** latency (extraction shares the GPU with Lori). Do not quote B1's
`truncation_rate` (dead instrumentation, see above) or the `truncation_starved` pack as evidence about the output
cap.

**Future design, recorded not scheduled — adaptive retry** (reviewer): make the normal call at the base cap;
retry once with a larger allowance **only** when the parser establishes class (a) — otherwise-valid JSON cut off
at the end. Never retry class (b) or (c). This replaces the length-of-answer routing idea discussed earlier, which
is another heuristic that can guess wrong, and may eventually replace a permanent 768 for compound calls.

**Carried forward from the reviewer (2026-09-23):**
- **Report rules fallbacks by reason**, not as one parse rate: parse failure · every item rejected on a
  retired path (the uncertain marriage date) · guard stripped everything (denial, refusal, wrong subject) ·
  model returned nothing. Only the first and last count against the model.
- **Subject binding — an A4 invariant, not one test.** Near-controlled evidence in B0: `father_identity`
  emits `parents.birthPlace = Stanley` **and** `personal.birthPlace = Stanley` — the narrator write is
  rejected only because that spelling is not a legal path; `mother_identity` emits `parents.birthPlace = spokane`
  **and** `personal.placeOfBirth = Spokane` — a legal path, so the false narrator fact survives. **A valid concept
  on the wrong subject is still false data.** Invariant: *when the active question or grounded clause is about
  another person, narrator-owned paths must not receive that person's value merely because those paths exist in
  the schema.* Test family: mother, father, spouse and child birthplace, and birth/death dates for the same
  subjects.
- **Keep A3 comparable.** The case-bank migration is versioned and the old bank + scorer stay runnable; A3
  reports the score under both the historical and the canonical path names.
- **Noise band.** Before B2 and B3 are read, repeat B-baseline at least once more (or run B2 twice) so a
  1–2 case delta can be told apart from decoding noise.

### A2–A4 scope, settled 2026-09-23 from `r6-batchA-base2` (`api.log`, 23:40–00:03)

Recorded before the build so the eval's findings are not lost. Evidence lines are in the findings table below.

**A3 — do**
- Redirect `family.marriageDate` → `marriage.marriageDate` and `family.marriagePlace` → `marriage.marriagePlace` (D12). Tests: legacy accepted and normalised; canonical unchanged; both in one response yield one fact. Keep the emitted path in provenance where that mechanism exists.
- Add the D1f paths the model is already emitting and losing: `family.children.middleName` (11 rejects), `siblings.middleName` (2), plus the rest of the D1f list.
- Retire D11/D1d/D1e/D3 paths from `EXTRACTABLE_FIELDS` **and** from every place that still names them: the `hobbies.* → pets.notes` rerouter (`extract.py:6839-6840`), and `_NARRATIVE_CATCHMENT_PATHS` (`:5806-5815`: `parents.notes`, `family.spouse.notes`, `family.marriageNotes`).
- Remove the ancestor-military copy into the narrator's `military.*` (`_ANCESTOR_MIL_DUP_MAP`, `:7071-7075`).
- **Remove the catch-all aliases that file people and facts into a story bucket** (`:4715-4719` `parents.sibling.* → parents.notableLifeEvents`, 9 hits this run, names like "Verene" stored as a parent's life event; `:4741` `parents.schooling → parents.notableLifeEvents`; `:5047` `family.relative → parents.notableLifeEvents`). An aunt/uncle is a person + relationship (D2); until Batch B can hold one, the value is logged as a disposition, not rewritten into narrative. Expect score movement on cases the old aliases were satisfying — scorer drift, reported per flip.
- Fix `parents.ageAtDeath` being dropped as "too short for narrative field" — D1c made it `person.death.reported_age`, a reported number.
- Reconcile `test_extract_schema_coverage` against WO-04; do not rewrite it green.

**A3 — evaluate, do not assume**
- `pets.dateOfBirth` → `pets.birthDate` (1 reject, "around 1964", approximate value kept as spoken). **Blocker:** `pets.birthDate` is a form field only; `animal.birth.date` is not extraction-eligible. Making it eligible is a D1f scope change — needs Chris's yes, not just an alias.

**A3 — do not**
- Rescue `narrator.ageAtMarriage` / `family.spouse.ageAtMarriage` — derived, never stored (D1c/D1e).
- Add `weather.description` or other model-invented one-offs.
- Collapse great-grandparent `serviceStart` / `serviceEnd` / `location` into `greatGrandparents.militaryEvent` — D7 needs a structured occurrence/period/place; Batch B.
- Alias every date-like education field: `education.graduationDate = 1981` is a real date, `education.periodEnd = "retirement"` is not. Education occurrences are Batch B.
- Add nested schemas (`grandparents.father.*`, `grandparents.mother.*`, `parents.sibling.*`). The rejection clusters (one family-origins answer lost 14 of 16 items) are the evidence for ordinary person + relationship records (D2), not for more hierarchy.

**Batch B/C — recorded**
- Relation words carrying other facts: `family.children.relation = "boy"` / `"youngest"` are dropped by the allowlist and the child group is then quarantined `relationship_unstated`. In the canonical model the parent–child edge states "child"; sex wording and birth order are their own attributes.
- Grandparent/great-grandparent relation words have no destination (grandmother ×6, grandfather ×5, great-grandfather ×3).

**A4 acceptance — measured against `r6-batchA-base2`, not just recall and prompt size**
- pass count, v2/v3, must-not-write, named flips, scorer-drift audit (standard block);
- prompt tokens per call (baseline 5,020–5,649);
- **direct-parse rate and salvage/truncation count** (baseline: 10 direct-parse failures in 74 calls, all salvaged);
- rejected-path count (baseline 78 not-in-vocabulary, 51 distinct);
- wrong-subject routing (turnscope drops, subject-filter strips, kinship quarantines).

**Output truncation — a flag, not the model (`verified_by_read`).** Dense answers stop near 1,433 characters because `.env` sets `MAX_NEW_TOKENS_EXTRACT_COMPOUND=384`, overriding the code default of 768 (`extract.py:2044`) that LOOP-01 R3 raised for exactly this truncation. The prompt has room: 5,649 + 768 + 512 reserve = 6,929 of 8,192. Raising it is a Tier 5 flag change — Chris's call, and it must be measured on its own, not folded into A4.

### Measured findings, recorded for the batches that own them

| finding | where | owner |
|---|---|---|
| Profile Seed reads **9 projection paths** that no producing vocabulary contains (`personal.ethnicity`, `military.yearsOfService`, `family.siblingCount`, …), so that evidence can never be satisfied through those paths | catalog `counts` | Batch D |
| ~~Five notes buckets kept under a generic `note.about_subject`~~ **DECIDED D11:** retired from structured extraction, still questionnaire-editable, bound to their lane (`story.about_person`, `story.faith`, `story.service`, new `story.about_animal`, `trip.story`); values migrate. `note.about_subject` no longer exists. New catalog property `extraction_retired_by`, separate from outright retirement. **A3 removes the five from `EXTRACTABLE_FIELDS`** | catalog | A3 |
| ~~D1e: `person.service.*` vs `event.service.*`~~ **CONFIRMED** (D1e refinement): `event.service.*`, the great-grandparent as participant. `greatGrandparents.militaryEvent` re-checked and is **not** narrative — label *"military event / deployment / dates"*; `extract.py:5054-5061` routes years of service, deployment location and rank into it — so it binds to new `event.service.occurrence`, not `story.service`. It packs several attributes in one value; Batch B splits it | catalog | Batch B |
| **Subject-identity defect, for A3:** `_ANCESTOR_MIL_DUP_MAP` (`extract.py:7071-7075`, LOOP-01 R4 Patch J) copies a great-grandparent's `militaryBranch` into the narrator's own `military.branch`, and `militaryUnit`/`militaryEvent` into `military.significantEvent`, "so scorer/consumer code that indexes military service at the root can match". That files an ancestor's service as the narrator's — the fact identity (narrator, **subject**, concept) is broken to satisfy a scorer. `military.significantEvent` is also in no vocabulary. Removing it will likely move eval cases that were scored on the dup; those flips are scorer drift, not regressions | `extract.py:7063-7106` | A3 — eval-gated |
| **Observed live in `r6-batchA-base2`, `api.log` 2026-09-22 23:41–23:54** (`verified_by_execution`): (1) the ancestor dup-emit above **survives the narrator's own denial** — at 23:50:15 the negation guard strips `military.branch/rank/yearsOfService/deploymentLocation`, but `military.significantEvent` (`"Civil War"`, `"Company G of the 28th Infantry"`) is not in the stripped set, so a narrator who said he never served is left holding his great-grandfather's war. (2) The model keeps emitting **`family.marriageDate`** (rejected 3× — 23:41:58, 23:45:34); WO-04 moved the field to `marriage.marriageDate` (`extract.py:290-292`) but no alias carries the old spelling, so real marriage dates are dropped. Same fact, same subject — **approved as D12 (2026-09-23)** with three required tests; `family.marriagePlace` deliberately excluded until evidence shows it is emitted. (3) **`family.children.middleName` (×7) and `siblings.middleName` (×2) are rejected** — exactly the D1f form paths A3 adds. (4) A rerouter **writes into `pets.notes`** (`extract.py:6839-6840`, `hobbies.hobbies → pets.notes`), and the model emits `pets.notes`/`parents.notes` directly; D11's A3 removal must retarget or remove that rerouter, not just the field. Budget: every call 5,020–5,609 tokens of a 7,296–7,552 budget, catalog 9,116 chars — A4's relevance scoping has room to take | `api.log` | A3 / A4 |
| **More from the same run, 23:57–00:03** (`verified_by_execution`): (5) **A3 scope for D11/D1d/D1e is wider than the field list.** `_NARRATIVE_CATCHMENT_PATHS` (`extract.py:5806-5815`) keeps `parents.notes` (live at 23:47:08 and 23:50:40) and still names `family.spouse.notes` and `family.marriageNotes`, which D1d/D1e already retired. A3 prunes all three there too. (6) The ancestor-military copy fired again at 00:02:55 in `military_family`, again after a narrator denial — three occurrences in one run. (7) **Candidate aliases the model keeps emitting — NOT approved, listed for Chris:** `greatGrandparents.military.serviceStart/serviceEnd/location` (rejected at 23:49:48 and 00:02:55; the existing alias map already routes `…military.yearsOfService` and `…deploymentLocation` to `militaryEvent`, `extract.py:5060-5061`, but not these); `grandparents.ethnicBackground` and `greatGrandparents.ethnicBackground` → `…ancestry` (23:48:40, 00:02:55); `pets.dateOfBirth` → `pets.birthDate` (23:52:24). (8) The model sometimes writes a `# comment` inside its JSON (23:44:06, 23:48:14); the salvage parser recovers it — not this batch. (9) Denial turns (`negated_military`, `negated_health`) correctly produce nothing, but are logged `method=rules-fallback`, so they count against the parse-success rate: a correct empty answer reads as a failure in that metric | `api.log` | A3 / Chris / scorer |
| profile_json spells one fact up to three ways (`dob/dateOfBirth`, `pob/placeOfBirth/place_of_birth`, `fullname/fullName/full_name`) | catalog `profile_json` bindings | Batch B |
| Phase G identity protection reads `profile.get("basics")` from the whole database row, so it is always `{}`; `preferredName`/`birthOrder` are never protected | `db.py:7438-7452` | **filed, not Batch A** |
| `test_extract_schema_coverage` (April) expects `family.marriageDate` and `residence.period`, which WO-04 removed and `test_extractor_vocabulary` (September) asserts are gone. **6 failures before and after this batch; not caused by it** | tests | A3 |
| `questionnaire_schema.py:312` leaves a file handle open | the shipped loader | trivial, noted |
| The eval runs against the empty working root; field scores remain comparable, but historical `r5*` runs are not, so the comparison is **`r6-batchA-base`** | checkpoint | Chris |
| **`r6-batchA-base` (34/114) is VOID as a baseline.** 0% parse, 100% rules fallback: the server ran with `HORNELORE_EXTRACTION_BOUNDED` off (`server_effective_flags` in the report; `r5k-guard-v2` had it on), so every call took the composed path and hit `413 PROMPT_TOO_LARGE` at ~10,000 tokens against 8,192. It measured the rules fallback, which A3/A4 do not touch. Re-run with the flag on as **`r6-batchA-base2`**; BACKLOG §2.6 corrected | checkpoint | Chris |

### A2 + A3 — landed in the tree 2026-09-23, before B2 (compound cap held at 768)

Scope settled by Chris: **"A — all four. Complete A3 in B2."** A4 (subject binding) is **not** in this batch.

**What changed, by subchange** (these labels are used again to attribute each B2 case):

| Label | Change | Where |
|---|---|---|
| **A2-alias** | `split_destination` translates the 13 decided aliases, plus the new D1f one, before splitting (`_decided_alias`) | `suggestion_review.py` |
| **A2-spouse** | `repeatable: "spouse"` on all 10 `family.spouse.*` fields, so the kinship guard and grouping see spouses as one group | `extract.py` EXTRACTABLE_FIELDS |
| **D12** | `family.marriageDate/Place` → `marriage.*` through `_SAME_FACT_REDIRECTS`, logged `REDIRECT` rather than `ALIAS`. `_fold_redirected_duplicates` drops only a redirected item whose (path, normalized value) matches a canonical item, so no duplicate fact is created. Bare `marriageDate`/`marriage_date` aliases point to `marriage.*`. Few-shots are rewritten, and SPANTAG's `marriage.` over-nest and invented-root rules are removed | `extract.py` |
| **D13** | `pets.birthDate` added (stated only, never computed); `pets.dateOfBirth` redirects to it | `extract.py` |
| **D1f** | Middle-name destinations `family.children.middleName` (alias `children.middleName`, `ALIASES_ADDED`), `siblings.middleName`, `siblings.maidenName` and `grandparents.middleName` | `extract.py`, catalog source |
| **D11/D1d/D1e/D3** | 20 paths removed from EXTRACTABLE_FIELDS: the 5 D11 story-lane notes (values stay in the questionnaire and route to story lanes, including `story.about_animal`) and the 15 RETIRED paths. The pets rerouter and splitter that wrote `pets.notes` are removed | `extract.py` |
| **WO-04 prompt** | Few-shots that taught retired or non-existent paths now teach real ones: `residence.periodStart/End`, `military.serviceStart/End/location`, `faith.communityRole/significantMoments`, `parents.preferredName` | `extract.py` prompt text, legacy and bounded copies |
| **AncMil** | `_ANCESTOR_MIL_DUP_MAP` (R4-J) removed with no replacement. The FIELD ROUTING rule now sends family service to that person's `greatGrandparents.military*` fields | `extract.py` |
| **CatchAll** | The `parents.sibling(s).*`, `family.member` and `family.relative` → `parents.notableLifeEvents` aliases are removed; they are now rejected rather than rewritten. `parents.schooling` → `parents.education` | `extract.py` |
| **D1c** | A stated `ageAtDeath` is exempt from the short-value drop | `extract.py` `_SHORT_VALUE_EXEMPT_SUFFIXES` |

EXTRACTABLE_FIELDS went from **146 to 131** paths. Recompiled catalog: 84 concepts, 196 paths (16 retired), 14 aliases. The compiler now keeps a RETIRED path as a row with `in: []` after its producer drops it, and **refuses a retired path the extractor still offers**: the retirement is enforced against the producer, not just stated.

**Scorer and bank are versioned, not overwritten.** The runner is untouched, so `scorer_version` is unchanged. v1 bank `b487e54cd84d` is untouched and stays the runner default. `data/qa/question_bank_extraction_cases_v2.json` (`fb9da1c9b565`) is generated by `scripts/eval/migrate_case_bank_v2.py` with four rules (M1 D12 rename, M2 forbidden rename, M3 ancestor-military correction for case_033/034, M4 removal of retired expectations plus one typo). It changes 41 cases, and each carries a `_migration` ledger. `scripts/eval/rescore_stored_outputs.py` rescores stored `raw_items` under both banks using the runner's own `score_case`.

**Bank-only movement, measured on stored outputs** (the same items under v1 and v2): B0 and B1 each go from **62 to 66**, v3 37→40, v2 32→35, must recall 0.6327→0.6474, mnw 0. Moved cases: 033 F→T, 036 F→T, 050 F→T, 088 F→T, 037 F→F (0.5→0.0), 046 F→F (0.667→0.5), 076 (0.55→0.6), 091 T→T (1.0→0.9). **case_088's pass is hollow:** its only must_extract was `pets.notes`, so under v2 it passes 0/0. It must never be quoted as an extractor gain. B1 reproduces 113/114 on rescore; case_073 does not, because of the runner's 100-character `raw_items` cap.

**Verification.** Interpreter for sandbox runs: `/usr/bin/python3` 3.10, no fastapi or pydantic.
- `test_extract_a3_vocabulary`: 27 OK, 1 expected failure (below).
- `test_extract_schema_coverage`: 32 OK. Reconciled to the real vocabulary; this closes the "6 failures before and after" row in the table above.
- Concept catalog mutation gate: **every mutation caught**. One mutation became equivalent after A3 and was replaced by two producer-side mutations; two guards gained their own tests.
- New `scripts/eval/mutate_a3_vocabulary.py`: **12/12 A2/A3 reverts caught**. Baseline 105 tests, 2 skipped.
- Pre-existing, reproduced unchanged on a HEAD (`fcc845c`) copy, **not caused by A3 and not fixed here**:
  - the `test_turn_extraction` 20-failure set;
  - `test_trip_narration_capture` photo-links 1 failure;
  - `test_timeline_context_events_isolation` LAW-3 1 failure;
  - `test_extraction_prompt_budget` stale stub (`lambda _r:` while production calls `_call_extractor(req, source_identity)`).
  The same file's 140-field pin was already wrong at HEAD (146). It is re-pinned to 131 because A3 sets that vocabulary.
- 17 suites cannot import in the sandbox and **must run in `.venv`**.
- **`.venv` run (Chris, WSL, `.venv/bin/python` 3.12), 23 modules together: 718 tests, 2 failures, 1 expected failure, 0 skipped.** Both failures reproduce on a `git archive fcc845c` export under the same interpreter, so they are **pre-existing**:
  - `test_extraction_prompt_budget` stale stub (above).
  - `test_extract_claims_validators::test_normalizes_relation_kids_to_child` expects `"Child"`. `_apply_claims_relation_allowlist` is byte-identical to `fcc845c`. Since `ea8638d` (2026-09-05) its `relationship_interpreter.interpret_phrase("kids")` branch returns the lowercase canonical `'child'` before the `.capitalize()` normalizer is reached, and the test was last updated `bc42de3` (2026-07-14).
- **Contamination found and fixed in A3's own test.** The first `.venv` run also showed errors in `test_confirmation_reasons` (`model_fields`) and `test_extract_api_subject_filters` (`FastAPI`). Neither reproduced on `fcc845c`. Cause: `test_extract_a3_vocabulary`, loaded first, called `fastapi_stub.install()` unconditionally. `install()` checks `sys.modules`, not importability, so it replaced the real fastapi/pydantic for every later module. The test now stubs only on `ImportError`. **Filed, not fixed:** `fastapi_stub.install()` does not honour its own docstring ("only if the real thing is absent"). Any of its seven users loaded first in a multi-module `.venv` run can do the same; so can the inline stubs in `test_extract_schema_coverage` and `test_extract_claims_validators`.

**Pre-existing defect found, filed, not fixed (to keep B2 attribution clean):** `_DATE_FIELD_SUFFIXES` is defined twice in `extract.py`. The camelCase frozenset at ~6559 shadows the lowercase tuple at ~4453, so `_is_date_field` never matches and the WO-04 req-7 uncertainty guard is dead code. It is pinned by an `expectedFailure` in `test_extract_a3_vocabulary`, alongside a companion test showing a redirected date is no weaker than a canonical one.

**Left out of this batch, deliberately:**
- D1f `lifeStatus` (Q10);
- `_SIBLINGS_REMAP` still maps child birth facts into `siblings.uniqueCharacteristics`;
- the R4-I `parents.deathDate`→`notableLifeEvents` duplicate;
- `family.member.name`→`parents.firstName`;
- SPANTAG spans still name `pets.notes`/`health.majorCondition` (SPANTAG is off);
- a stale "parents.education doesn't exist" line in one narrative few-shot;
- `personal.middleName`/`relationships.closeFriends` taught but not fields (pre-existing);
- **A4 subject binding**.

### `r6-batchA-b2-a3` — B2, A2 + complete A3, read 2026-09-23

**Run identity** `[verified_by_read: report header]`: `bb21631`, **clean**. Scorer `318df0d2ff1f`; bank v1 `b487e54cd84d`. Settings as B1: bounded on, narrative on, cap 128 / compound 768. **131** extractable fields. `api.log` from line 279,702; 115 calls = 114 cases + warmup. Each call was aligned to its case by `section == subTopic`, 114/114 in both windows.

**Aggregates.** v1 = historical paths; v2 = decided paths. The v2 figures come from `scripts/eval/rescore_stored_outputs.py`, rescoring the same stored items.

| | B1 v1 | B2 v1 | B1 v2 | **B2 v2** |
|---|---|---|---|---|
| pass | 63* | 59 | 66 | **66** |
| v3 / v2 contract | 37 · 32 | 35 · 30 | 40 · 35 | **40 · 35** |
| must recall | .638 | .582 | .647 | .626 |
| must_not_write | 0 | 0 | 0 | 0 |

*B1 live 63; its rescore gives 62 because of the 100-character `raw_items` cap on case_073.

**Verdict: no net score change on the decided bank.** Underneath the equal total are two different effects.

1. **Deterministic A3 code paths, net positive.** D12's `REDIRECT` turns the model's habitual `family.marriageDate` into a scored hit on the same model output. It flips **case_004** and **case_072** to pass and lifts **case_064** from 0 to 0.5. Nothing else in the A3 code paths moved a score.
2. **The prompt changes perturbed the model's output, net negative.** **77 of 114 outputs changed item content**, against 11 of 115 in B0→B1, where only the cap changed. Pretty-printed output went from 29 to 51, with total characters flat (75.1k vs 74.3k). Of the resulting flips, four went up (012, 037, 042, 078) and six went down (006, 033, 034, 063, 085, 107). With no repeat run, this cannot yet be told apart from decoding noise.

**Every case that changed on v2, attributed** `[verified_by_execution: raw output + validate/turnscope/guard lines per call]`:

| Case | v2 move | Cause |
|---|---|---|
| 004 | F→T | **D12**: same output both runs; B1 rejected `family.marriageDate`, B2 redirected it |
| 072 | F→T | **D12** redirect (hit `marriage.marriageDate`) |
| 064 | .00→.50 | **D12** redirect. The spouse group was quarantined in both runs; A2-spouse changed only its label |
| 012 | F→T | Prompt/D12: the model now emits `marriage.marriageDate` directly; in B1 it emitted no date. B2 also carries a DERIVED spouse DOB `approximately 1939-11` (pre-existing value-grounding rule, noted) |
| 042 | F→T | Model wording: species `Golden Retriever` vs `dog`. D13 `pets.birthDate` was captured but is unscored; D11 removed `pets.notes` |
| 037 | F→T | Model wording on `lifestyleChange`. D3 now rejects `health.majorCondition` (unscored on v2) |
| 078 | F→T | Model wording on `higherEducation` |
| 006 | T→F | Model routed the job to `community.*` instead of `education.*`. No A3 path involved |
| 033 | T→F | Model put "Civil War" in `militaryBranch` and dates in `militaryEvent`. The AncMil *code* removal does not score on v2; the rewritten AncMil *prompt rule* is the only A3 change on this turn. Plausible, unproven |
| 034 | T→F | Model put the event in `memorableStories`. Same note as 033 |
| 063 | T→F | Model terse: 2 items, schooling lost |
| 085 | T→F | Model spelled occupation `parents.profession` (invalid); in B1 it used `parents.workplace` (aliased). D11 now rejects `deliverer→parents.notes` (unscored) |
| 107 | T→F | Model omitted `parents.birthPlace`. No A3 path involved |
| 031 | .50→.00 | Model sent both grandparents to `parents.*`; turnscope dropped them; the nameless `side` was quarantined |
| 065 | .53→.00 | Model bound the **great-grandfather** as a grandparent; the kinship guard correctly quarantined him. **A4 class.** Also cap class (a) |
| 047, 066, 073, 077, 089 | score only | Model variation. On 066, **CatchAll** now rejects `parents.sibling.*` instead of aliasing it into `notableLifeEvents`, which B1 then quarantined anyway |
| 079 | .53→.43 | **D1f** captured `siblings.middleName` Edward/Richard (in B1 "Richard" was a quarantined firstName). The score fell on a should_ignore write of the narrator's own, true birthplace |
| 088 | 1.0→.70 (pass) | **D11**: with no notes bucket, the model writes `pets.name`/`species`/`residence.place`, which this follow-up marks should_ignore. v2 pass is hollow (0/0) |
| 091 | .90→.80 (pass) | **D12** redirect writes `marriage.marriageDate="October 10th"` (no year) on a should_ignore turn |
| 102 | 1.0→.70 (pass) | Model: B1 was a zero-item fallback; B2 is a 30× repetition loop to the cap, writing `grandparents.birthPlace=Ross` (**A4 class**) |

**The requested aggregates, decomposed.**
- **should_ignore leak 8→15 of 68** (11.8%→22.1%). 6 of the +7 come from two cases: 088 +3 (D11 consequence) and 102 +3 (repetition loop). The rest: 066, 079 and 082 +1 each; 078 and 089 −1 each.
- **missing 51→63, +12.** The runner computes it against the **v1** bank.
  - +5 are v1 expectations of retired behaviour: 033 and 034 expect the narrator `military.significantEvent` duplicate; 037 expects `health.majorCondition`; 046 and 088 expect `pets.notes`.
  - +10 are model output changes: 024, 031 ×2, 047, 063, 065, 073, 085, 087, 107.
  - −3 is case_080, which moved from missing to preserved-for-review.
- **wrong_executable 23→18.**
  - Only two wrong writes became correct: 037 and 042, both model wording, neither an A3 code path.
  - Five wrong writes became missing: 024, 031, 087 (model) and **046, 088 (D11: no notes-bucket write, by design)**.
  - Two new wrong writes: 006 and 075.
  - So the genuine A3 reduction is **2 notes-bucket writes prevented**; nothing moved from wrong to right.
- **executed_correct 117→106**, preserved_for_review 5→9.

**Parse and fallback, forensic** (from `api.log`; the report's `truncation_rate` is structurally 0 and ignored).

| | B1 | B2 |
|---|---|---|
| direct / salvaged | 104 / 10 | 101 / 13 |
| (a) probable cap exhaustion @768 | 3 (039, 068, 081) | **8** (065, 068, 077, 080, 081, 084, 087, 102) |
| (a) @128 | 1 (055) | 1 (055) |
| (b) premature stop | 2 (079, 103) | 2 (044, 103) |
| (c) malformed | 4 (013, 030, 070 `#`, 072) | 2 (023 `//` comment, 070) |
| fallback: guards removed all | 4 (008, 018, 038, 080) | 3 (008, 018, 100) |
| fallback: every item rejected | 7 (055, 056, 061, 074, 100, 101, 102) | 2 (055, 101) |
| fallback: model returned nothing | 2 (096, 097) | 4 (038, 056, 096, 097) |

The five extra cap exhaustions are spent on junk: lists of empty-value fields (077, 080), invented paths (065, 087) and a 30× repetition loop (102). **More tokens would not recover a fact from any of them.** "Every item rejected" fell 7→2 partly because the retired marriage spelling now redirects (061), which is the blocker below.

**BLOCKER — A3-created, found by log reading; the scorer cannot see it.** case_061: *"I think it was 1956, maybe 1957. I'm not sure of the exact year anymore."* In B1, `family.marriageDate` 1956 and 1957 were rejected, but only by accident, because the spelling was invalid. In B2 the D12 redirect **executes both as `marriage.marriageDate`**: `executable_count=2`, review 0. The bank has no `must_not_write` on that date, so the score is unchanged.
- Fixing the duplicate `_DATE_FIELD_SUFFIXES` alone would **not** catch it, because `_reads_as_uncertainty` reads the *value* and 1956/1957 are clean years. The hedge is in the narrator's sentence, and no live mechanism holds a date the narrator hedged. SPANTAG's `uncertainty_cue` is off.
- Across B2, date values whose sentence the narrator hedged: B1 **0**, B2 **3**. 061 ×2 (D12) and 042 `pets.birthDate="around 1964"` (D13). The D13 one keeps its hedge in the value, as D13 allows. The 061 ones lose it and contradict each other.

**Not caused by A2/A3, carried to A4:** case_065 (great-grandfather bound as grandparent), case_102 (`grandparents.birthPlace=Ross`), case_031 (grandparents emitted as `parents.*`).

### B2 repair — hedged or conflicting dates are held for review (approved 2026-09-23)

**Scope as approved.** No prompt change, no A4 change, the 128/768 caps unchanged, the scorer and both banks untouched, and `_DATE_FIELD_SUFFIXES` **not** revived.

**What landed:** `_apply_date_uncertainty_guard` in `extract.py`, called in `_finalize_extracted_items` right after the kinship guard. It uses the same seam, the same `(items, entries, clarifications)` shape and the same `not_applied` review-entry form (kind `uncertain_date`).
- **`conflicting_values`:** two different values for one date field of **one entity** (fieldPath + repeatableGroup) in one turn. Both are held.
- **`narrator_uncertain`:** the sentence the value came from carries a hedge ("I think", "maybe", "not sure", "probably", "or so", and similar). "I think about" does not count.
- **Exempt:** a value carrying its own approximation ("around 1964") executes as stated.
- The guard has its own date-leaf list, deliberately separate from the shadowed constant.

**Replay on stored outputs, measured before any live run.** Built with the shipped `_group_repeatable_items` plus the guard: **B1 holds 0 values; B2 holds 4.**
- **case_061:** 1956 and 1957, for both reasons. This is the blocker.
- **case_070:** two different children's birth dates that grouping had put on **one** child (`children_3`, Cole). R4-H normalizes the dates *before* grouping, so "1991-10-04" cannot be found in "October 4, 1991" and falls through to the last child. **In B2, Gretchen's birth date was executed on Cole's record.** Holding it is correct under the approved rule. It is also a **predictable score cost**: the scorer matches by path and cannot see which person a value is on. The grouping-after-normalization defect is entity binding and belongs to **A4**; it is filed here and not fixed.

**Tests:** `tests/test_extract_date_uncertainty_guard.py`.
- 11 helper tests: held for review, stays executable, and envelope hygiene.
- 3 production-boundary tests through `run_field_extraction`. Only the network call is replaced; the model's raw text goes through the shipped `_parse_llm_json`, so the D12 redirect is on the tested path. They need real pydantic and **skip in the sandbox**.
- **Mutations:** 7 added to `scripts/eval/mutate_a3_vocabulary.py`. In the sandbox 6 are caught; the seam mutation survives only by that skip and must be caught in `.venv`.

### `r6-batchA-b2r-a3` — B2 repeat after the date repair, read 2026-09-23

**Run identity** `[verified_by_read: report header]`: `8e60fad`, **clean**, scorer `318df0d2ff1f`, bank v1 `b487e54cd84d`. Cap 128 / compound 768, 131 fields, prompt `b2a`, **byte-identical to B2**. `api.log` from line 283,936; 115 calls, 114/114 aligned.

**Aggregates.** v1 59/114, contract 35/30. **v2 66/114, contract 40/35, mnw 0; must recall .6263 → .6368.** executed_correct 106 → 108, missing 63 → 61, wrong_executable 18 → 18, preserved_for_review 9 → 9.

**1. The repair works** `[verified_by_execution: api.log HELD lines + report review_entries]`. It held 6 values; all 6 are correct holds.
- **case_061:** `marriage.marriageDate` 1956 and 1957 held, reasons `conflicting_values` + `narrator_uncertain`. Executable dates: 0; review entries: 2. **The blocker is closed.**
- **case_070:** Gretchen's and Cole's birth dates held (`conflicting_values`, both on `children_3`). The runner counts them `preserved_for_review`. The cost is the one predicted: v2 pass → fail (1.0 → .533). The remaining problem is grouping after R4-H normalization, which puts two children's dates on one child. That is **A4 entity binding** and was already filed; the repair is behaving as designed.
- **case_068 (new in this run):** the model put grandfather George's 1914 death and father Ervin's 1967 death on one parent. Both held (`conflicting_values`). In B2 this turn had **executed** `parents.deathDate="before 1914"`, George's death on Ervin, so this is a wrong write prevented. Subject binding, A4 class.
- **Self-approximate dates still execute:** case_042 `pets.birthDate="around 1964"` executable, unconverted, score 1.0.
- **No systematic date loss:** date-shaped executable items went 41 → 34. That is the 6 holds above, plus case_068's `before 1914`, which the model did not re-emit.
- **No review explosion:** review entries 132 → 150. +6 are `uncertain_date`; the other +12 are `meaning_disposition` on two model-variant turns (068 +11, 019 +2). The guard adds no entries of other kinds.

**2. Noise band** `[verified_by_execution: the reports' final executable items, all 114 cases]`

| | final executable items changed | v2 flips | cases with score change |
|---|---|---|---|
| **B2 → B2r (same prompt)** | **12/114**, at least 3 of them the repair's own holds (061, 068, 070) | +1 −1 (065 up = model; 070 down = repair) | 4 |
| B1 → B2 (prompt changed) | **58/114** | +6 −6 | 24 |

*Corrected before commit.* A first version of this table compared the raw text in `api.log` and reported 103/114 byte-identical against 26/114. **The log truncates raw output at 500 characters** (46 calls in every window), so for those calls only a prefix was compared. The final executable items above are complete, apart from the report's 100-character value cap. The conclusion is unchanged.

**The A3 prompt movement is NOT decoding noise.** Every one of the 12 B1 → B2 flips **held** in B2r; none reversed. The four prompt-induced gains (012, 037, 042, 078) and six losses (006, 033, 034, 063, 085, 107) are reproducible effects of the rewritten few-shots and vocabulary text. The code-path gains (004, 072 via D12) are also stable. The net is still 0 on v2.

**Earlier B2 forensics that read raw text.** The salvage classes used the logged length and error position, which are complete, so they stand. The "77/114 content changed" and "pretty-printed 29 → 51" figures were computed on truncated text. Read them as directional; they are superseded by the table above.

**3. A3-created wrong write, found in this reading** `[verified_by_execution: every ageAtDeath item, B1/B2/B2r]`. **D1c** exempted `ageAtDeath` from the short-value drop so a *stated* age at death would survive. Every `ageAtDeath` written since is **the same false fact:**
- case_015, B2 and B2r: *"Dad died December 23rd, 1967. **I was twenty-eight.**"* → `parents.ageAtDeath="28"`. That is the narrator's age, not the father's.
- case_068, B2r: the same sentence, the same false `28`.
- B1 wrote **none**; the short-value drop removed them, by accident.

That makes **3 writes, all wrong, 0 correct**. The scorer cannot see it: case_015 scores 1.0 in all three runs, because the bank has no `must_not_write` on `parents.ageAtDeath`. This is the D12 pattern again (a change removed an accidental protection), and the error itself is **subject binding**: a first-person age attached to a parent.

### D1c reverted, verified by replay — and the B2 closeout (2026-09-23)

**D1c attempted to admit stated age-at-death values. B2 and B2r showed every value it admitted was the narrator's own age leaking onto a parent, so the exemption is reverted pending A4 subject binding.**
- The evidence: 3 writes, 0 correct. *"Dad died December 23rd, 1967. **I was twenty-eight.**"* → `parents.ageAtDeath="28"` (case_015 in B2 and B2r; case_068 in B2r).
- The revert removes `ageAtDeath` from `_SHORT_VALUE_EXEMPT_SUFFIXES`, so the short-value drop applies again. The comment at the definition records why.
- The test is now `ShortAgeAtDeathStillDropped`: `"28"` is rejected. The mutation "D1c revert undone" is caught.
- No prompt, bank, scorer, cap or A4 change.

**Carried to A4 as a requirement, not as a defect.** `ageAtDeath` may be reintroduced only when the age is **bound to the deceased person**, not merely present in the same sentence.

**Replay** `[verified_by_execution: B2r raw model outputs from api.log through the shipped run_field_extraction; only the network call replaced]`
- **Replayable calls:** 65 of 114. Excluded are the 46 whose logged output is truncated at 500 characters, and the salvaged ones.
- **Fidelity:** with the exemption restored, the replay reproduces the stored B2r executable items for 63 of 65. The 2 misses (002, 053) are sibling names that the live run's database profile lookup contributed. They are identical with and without the revert.
- **Revert vs no revert, across all 65:** exactly one difference. **case_015 loses `parents.ageAtDeath="28"`.** Nothing else changes.
- **Truncated calls, by construction.** The revert's only reader is `_apply_claims_value_shape` (`extract.py:6329`), and it affects only a `…ageAtDeath` value shorter than 3 characters.
  - **case_068's** stored `parents.ageAtDeath="28"` is dropped by that function; this is the same assertion as the test.
  - Removing a non-name, non-date member cannot change a group's subject (kinship guard), a date slot (date guard) or grouping.
  - **case_070** has no such item, so its path is untouched.
- **Invariants kept:**
  - case_061's two holds: replayed, still held.
  - case_070's and case_068's holds: untouched by construction.
  - case_042 `pets.birthDate="around 1964"`: replayed, still executes as stated.

**B2 ACCEPTED — A2+A3 complete, date regression repaired, D1c reverted, noise band measured.**
- On the decided (v2) bank: 66/114, contract 40/35, must_not_write 0. B1 is also 66, so the net score movement is zero.
- **What is underneath:**
  - D12's code path is net positive (004, 072).
  - The prompt rewrites have a reproducible, non-noise effect: four gains, six losses.
  - Two false-write paths that A3 opened were found in the logs, where the scorer could not see them, and were closed: uncertain dates now go to review; the age-at-death exemption is reverted.
- **Carried to B3/A4:**
  - entity grouping after R4-H normalization (070);
  - wrong-subject deaths and birthplaces (068, 102);
  - grandparent vs great-grandparent binding (065, 033/034);
  - grandparents emitted as `parents.*` (031);
  - the `ageAtDeath` reintroduction condition above.
- **Carried as filed, not scheduled:** the shadowed `_DATE_FIELD_SUFFIXES`; the stale test stub in `test_extraction_prompt_budget`; the `kids`/"Child" test; `fastapi_stub.install()` checking `sys.modules` rather than whether the package is installed; `api.log` truncating raw output at 500 characters.

### B3 / A4 — subject binding: design, before code (2026-09-23)

**Scope note.** In the pre-build batch plan (`A2–A4 scope`, above), "A4" meant **relevance-scoped extraction**: prompt scoping through `extraction_paths_for_scope`. Since B1, Chris has directed A4 to be **subject binding**. This design is subject binding. Relevance scoping is a prompt change; B2 showed prompt changes move about 58 of 114 outputs. It is **not** in B3, and whether it returns as its own batch is Chris's call.

**Invariant.** *Every extracted fact must identify the person or entity it describes before it can become executable. A fact about a parent, grandparent, great-grandparent, child, spouse, animal or the narrator is not accepted merely because its field path belongs to the right broad section.*

**One mechanism, three parts, all reusing machinery that already ships. No case-specific patterns.**

1. **Evidence span: where in the answer did this value come from?**
   - Each item carries the text it was extracted from, **as spoken, before normalization**, through the grouper's existing `_locate_value` hook (`extract.py:7655-7663`).
   - Today R4-H (`_apply_write_time_normalisation`, `:6657`) rewrites "October 4, 1991" → "1991-10-04" without setting it. The grouper then cannot find the value, and it falls through to the last child. That is **case_070**.
2. **Span subject: whom does that clause describe?**
   - This is resolved with the kinship guard's existing parts: sentence-clamped `_name_windows`, `_ROLE_LOCAL_LANGUAGE`, and `relationship_interpreter`.
   - Added: **first person** ("I was twenty-eight") → the narrator.
   - Added: **one level of possessive chaining** relative to the turn's subject: "*his own father* George" said of a parent → a grandparent; "*her father* John Michael" said of a grandmother → a great-grandparent.
3. **Decision, at the finalization seam, beside the kinship and date guards.**
   - Span subject matches the item's role → executable, as today.
   - Span subject resolves to a **different** role → **not executable**. The item goes to review as `wrong_subject`, proposing the resolved role's path.
   - Span unlocatable, or subject unresolved → **unchanged**. The existing guards (turnscope, kinship, subject filter) keep their jobs.
   - Nothing that ships today becomes executable because of B3 unless the evidence says so. The one deliberate exception is the D1c reintroduction below.

**Regression set.** Values come from the real B2/B2r model output. The binding is produced by shipped code and asserted at `run_field_extraction`.

| Case | Today | Under B3 | Which part |
|---|---|---|---|
| 070 | Gretchen's DOB grouped onto Cole; both held as conflicting | each date on its own child, executable | 1 |
| 068 | George's 1914 death on father Ervin (B2 executed it; B2r held it only because it conflicted) | 1914 → `wrong_subject` (grandparent); Ervin's 1967 executable | 2, 3 |
| 015 / 068 `ageAtDeath` | "I was twenty-eight" → `parents.ageAtDeath=28` (now dropped by the D1c revert) | narrator span → `wrong_subject` | 2, 3 |
| 065 | great-grandfather emitted as a grandparent; kinship guard quarantines `relationship_unstated` | still not executable; review proposes `greatGrandparents` | 2 |
| 031 | grandparents emitted as `parents.*`; turnscope **drops** them silently | see decision 1 | 2 |
| 102 | `grandparents.birthPlace=Ross` from "where my grandmother's people **homesteaded**" | **not a subject error**: the subject cue matches; the *predicate* is wrong (homestead ≠ birth) | see decision 2 |
| 033 / 034 | "Civil War" in `militaryBranch`, the event in `memorableStories` | **not a subject error**: right person, wrong attribute; a reproducible prompt effect (B2) | out of B3 |

**Decisions for Chris before code**
1. **Wrong subject: hold for review, or re-home?** Recommended: **hold** in B3. Re-homing writes a fact into another person's record on the model's say-so. Revisit when Batch B has real person records.
2. **102: add a predicate check in B3?** A birth or death field would require a birth or death cue in its span. Recommended: **yes**. It is the same span machinery, and "fact binding = subject + predicate" is the honest statement of the invariant.
3. **D1c reintroduction in B3:** `ageAtDeath` becomes admissible again **only** when its span's subject is the deceased person. Recommended: **yes**, as the batch's last step, with a mutation proving the narrator-age case stays rejected.
4. **Measurement.** `api.log` truncates raw model output at 500 characters (46 of 114 calls), which blocked a full replay in B2. Raising that log limit is logging only, not product behaviour. Recommended: **yes**, in B3's first commit, so B3's own replay is complete.

**Decisions, Chris, 2026-09-23** (the wording is tightened as he required; the agent's reading is written out so that it can be corrected):
1. **Wrong subject → held for review, never re-homed.**
   - No B3 code writes a fact into any other person's record.
   - A review entry may *name* the resolved role as a proposal; that is all.
2. **Predicate check: approved narrowly.**
   - Only birth and death **date and place** fields of non-narrator people.
   - It acts only when the value's span is located. A located span with no birth or death wording → held for review (`predicate_unstated`), not dropped.
   - No other field is touched.
3. **`ageAtDeath` returns only under all three conditions:**
   - the span is located;
   - its subject resolves to the same person the item is grouped with;
   - the span carries death wording.
   - A first-person span is always rejected. This is B3's last commit, with its own mutation.
4. **CHANGED: no permanent expansion of `api.log`.**
   - Full model output is captured only in an **armed evaluation trace**: off by default, written to its own file under `.runtime/`, never to `api.log`.
   - The ordinary log keeps its 500-character prefix. Avoiding a privacy and log-bloat regression outranks test convenience.
5. **Relevance-scoped prompting stays out of B3.** B3 establishes subject and event binding **under the same prompt**. Relevance scoping returns only if measurement later shows it is needed.

**Build order.** One commit per part, each with tests and mutations:
- (a) the armed trace, as a Tier 5 flag;
- (b) evidence span — R4-H sets `_locate_value`;
- (c) span subject and the `wrong_subject` hold;
- (d) the predicate check;
- (e) `ageAtDeath` reintroduction.

Then one live run with the trace armed, compared with B2r.

**Acceptance.**
- A live run at 768, compared with **B2r**. The noise band is 12/114 final outputs with an identical prompt; B3 changes no prompt.
- The standard block: pass, v2/v3, mnw, named flips, scorer-drift audit.
- New counts: `wrong_subject` holds, and every executable birth, death or age value traced to its span subject.
- Tests plus mutations for each part. No regex written for a named case.

### B3 — built (2026-09-23), before the live run

All five parts sit at the finalization seam, in this order: kinship guard → **subject binding** → **predicate** → **age at death** → date uncertainty. Binding comes first so that the date guard judges a conflict only among correctly bound values.
- **The prompt is byte-identical to B2r**: one sha256 over the bounded prompt for all 114 bank cases, HEAD versus the working tree, `937ddf04f99923da` both.
- One code commit. The design said one commit per part, but all five parts are interleaved in `extract.py`, and staging is by path.

**The five parts**
- **(a) Armed trace.**
  - `HORNELORE_EXTRACT_EVAL_TRACE` is off by default. When on, it appends one JSON line per call to `.runtime/eval_traces/extract-<date>.jsonl`, carrying the section, target, a hash of the answer (not the answer), and the full raw output.
  - `api.log` is unchanged; a test asserts it keeps its 500-character prefix while the trace is armed.
  - The runner header reports the flag as a boolean only.
- **(b) Evidence span.**
  - R4-H records what was said in `normalized_from`, which already means exactly that.
  - The grouper traces a date it cannot find to the spoken text, then its year, then an elided year ("'94"). This happens **only where the old lookup already failed**.
- **(c) Span subject.**
  - Mentions: "I", "my/our <kin>", bare "Dad"/"Mom", and names the model extracted.
  - One generation up for "his/her/their (own)" and for **"X's"** ("my mom's dad").
  - A name directly after a kin phrase takes the **phrase's** role; the narrator's words outrank the model's filing.
  - **Said once is said:** any occurrence governed by the claimed person supports the fact.
  - A mismatch is held as `wrong_subject`, carrying the resolved role as a proposal only. Never re-homed.
- **(d) Predicate.**
  - Scope: relatives' birth and death dates and places only.
  - The value's own sentence must carry birth or death wording. The previous sentence counts only when this one points back ("That was 1914.").
  - A date is located by **any** part said: year, elided year, or month and day.
  - A located value without the wording is held as `predicate_unstated`.
- **(e) Age at death.**
  - The D1c exemption is restored **behind** `_apply_age_at_death_guard`.
  - Three conditions: the value is located (digits or words, "twenty-eight"); it is the same person as the group (by name, and a parent noun agrees with the group's relation); and the sentence carries death wording.
  - A first-person age is **rejected**; anything else unmet is held as `age_unbound`.

**Measured on the stored outputs of B1, B2 and B2r before any live run.** These are the executable items, re-run through the new guards; it is a replay only, as the model output is unchanged.
- **`wrong_subject`: 2–3 holds per run.**
  - case_068 `parents.deathDate=1914`, George's death, held (B1, B2). In B2r it was already held by the conflict rule.
  - case_044 child born in "North Dakota" (actually Germany) and case_082 narrator born in "Dodge" (actually Spokane). Both are **false values held through an indirect reason**, recorded as such.
  - **False holds of true facts: 0.** A first draft held case_112 ("Mom was born in spokane, and I was born in Spokane too") and case_073 ("my mom's dad… born at home"). The said-once and possessive rules fixed both before anything was committed.
- **`predicate_unstated`: 8 per run, all false birthplaces.**
  - B2 and B2r: "Dad was *from* Stanley", "my mother *grew up* near Williston" (054); where Gretchen lives now and where Amelia worked (070); "*came from* Lorraine" (071); "where my grandmother's people *homesteaded*" (102).
  - B1 adds college in Bismarck (075), towns the family *moved* through (086), and "His family *came from* Ukraine" (031).
  - **False holds of true facts: 0.** One draft held case_090 ("until 1985. Died December 1st that year."); locating a date by month and day fixed it.
- **`ageAtDeath`:** case_015 and case_068's "28" (the narrator's own) are rejected. A bound "Dad died… at seventy-two" executes.

**Verification in the sandbox.** Interpreter `/usr/bin/python3`, fastapi and pydantic stubbed.
- Unit tests: 77 run, 9 skipped (the production classes). All nine production tests pass when run directly against the stubs.
- B3 gate (`scripts/eval/mutate_b3_binding.py`): **15 of 19 caught.** The four survivors are the four seam mutations; the production classes that catch them skip without real pydantic, so they must go red in `.venv`.
- The A3 gate's D1c mutation moved into the B3 gate.
- The repo-local default DB `data/db/lorevox.sqlite3` (gitignored, not narrator data) was opened by the previews' `init_db`. **No rows were written**: verified read-only, 0 people and none of the test IDs in any table.

**Not solved by B3, recorded here instead of stretched to fit:**
- **case_082.** The model wrote **six** narrator birthplaces (every town she lived in), and all executed in B2 and B2r. B3 holds one. The rest need a predicate check on the **narrator's** own birth fields, which decision 2 excluded. **Needs Chris.**
- **case_031.** Grandparents emitted as `parents.*` are still **dropped silently by turnscope**, earlier in the pipeline. They are not executable, but not preserved either.
- **case_065.** Still quarantined by the kinship guard; no great-grandparent proposal is added.
- **case_033 and case_034.** Right person, wrong attribute: a prompt effect, out of scope.

### `r6-batchA-b3-binding` — B3 live gate, read 2026-09-23

**Run.** `dc20d53`, **clean**, 131 fields, prompt `b2a`, cap 128 / compound 768. `api.log` from line 288,055; 115 calls, all aligned to their cases.
- **The trace did NOT run:** `HORNELORE_EXTRACT_EVAL_TRACE=False` on the server, and there is no trace directory; the running server had not loaded the setting. **Not needed:** every targeted question below was answerable from the report plus `api.log`.
- **v2:** 67/114 (B2r 66), contract 40/35, must recall .6421 (B2r .6368), **mnw 0**.
- **Preservation accounting:** executed_correct 108 → 109, wrong_executable 18 → 18, missing 61 → 61.
- **Guard actions in the live log: 15.** That is exactly the set the stored-output replay predicted.

**The Phase 1 exit questions**
1. **070 — yes.** Gretchen `1991-10-04` and Cole `2002-04-10` execute on their own children. Amelia's elided "'94" is held by pre-existing value-grounding. The four non-birth "birthplaces" (Austin, New Mexico, Colorado, Hawaii) are held as `predicate_unstated`. The case flips to **pass** (the only v2 flip).
2. **068 — yes.**
   - George's `parents.deathDate=1914` is held as `wrong_subject`, resolved to grandparents.
   - Ervin's `1967-12-23` now **executes**; in B2r it had been held as a conflict.
   - William McRaith's `1918` stays quarantined by the kinship guard.
   - The narrator's "28" is **rejected**.
3. **065 — NO. A known wrong-subject write is NOT prevented.**
   - `grandparents.birthPlace="near Nancy, Lorraine, France"` executes on grandmother Elizabeth. It is the **great-grandfather's** birthplace: "*Her father* John Michael Shong was born near Nancy *in* Lorraine, France".
   - It is **not new**: the same write executed in B2r.
   - B3 missed it because a place value is located **verbatim only**. The model's "Nancy, Lorraine" does not match the narrator's "Nancy in Lorraine", so the value is unlocated, and unlocated means unchanged by design.
4. **102 — yes.** `grandparents.birthPlace=Ross` ("homesteaded") is held as `predicate_unstated`. The narrator's own `placeOfBirth="North Dakota"` still executes; that is out of scope under decision 2.
5. **031 — unchanged, as designed and documented.** Turnscope still drops the grandparents' names emitted as `parents.*`. They are not executable, but not preserved either.
6. **033 / 034 — not subject binding.** The right great-grandfather, but the wrong attribute (`militaryBranch="Civil War"`). 034 also executes `greatGrandparents.birthPlace="unknown"` ×2, a junk value that exists before B3 and is unlocated. No narrator military leak.
7. **ageAtDeath — half is proven live.**
   - The narrator's "I was twenty-eight" is **rejected** in 015 and 068, and no `ageAtDeath` executes anywhere.
   - **No bank case produced a genuine deceased-person age in this run**, so the accepting path is proven only by the production-boundary test ("My father Walter died at 64", `.venv`), not by live data.
8. **New true-fact loss or silent false write caused by B3 — none found.**
   - Every B2r → B3 difference was accounted for.
   - **B3's own actions:** 015, 044, 054, 068, 070, 071, 082, 102. Each removes a false value, or binds a true one.
   - **Everything else:** 013 (name split), 019, 065 (`grandparents.side` ×2), 076, 081, 085, 098. These happen **before** B3's code runs. The item counts are already lower at the `[extract][summary]` accepted line, and all B3 guards run later, at finalization. So they are model variation, inside the 12/114 noise band.
   - No v2 pass → fail flips.

### B3 final repair — case_065 — and the Phase 1 close (2026-09-23)

**Why one more repair.** case_065 was a named B3 target and still executed a wrong-person fact in the live gate: the great-grandfather's birthplace written onto grandmother Elizabeth. The cause was one mechanism. A **place** was located verbatim only, and the model's "near Nancy, Lorraine, France" does not match the narrator's "near Nancy *in* Lorraine, France".

**The fix, bounded as Chris set it.**
- A birth or death place that is not found verbatim is located by its content words, all in **one** sentence (`_place_word_positions`).
- Everything after that is the existing binding: "*Her father* … was born near Nancy" → one generation above grandmother Elizabeth → `greatGrandparents` ≠ `grandparents` → `wrong_subject`.
- No special case for 065. No prompt, bank, scorer or cap change, and no live rerun. Nothing else was touched: 031, 033/034, 082 and 102 went to `docs/BACKLOG.md` §10.

**Evidence.**
- **Replay across the stored outputs of B1, B2, B2r and B3:** the only new hold anywhere is case_065's birthplace, in B2r and B3. Every other binding and predicate hold is unchanged.
- **Production replay of the B3 live output for 065** (`raw_items`, `dc20d53`) through `run_field_extraction`:
  - the birthplace is held as `wrong_subject`, resolved to `greatGrandparents`;
  - Elizabeth herself still executes.
- **A correctly attributed birthplace still passes:** "My mother was born near Minot in North Dakota".
- **Sandbox:** 81 tests, 10 skipped (production classes, previewed passing).
- **The new mutation "places located verbatim only" is caught.** The B3 gate is now 20 mutations; `.venv` confirmation is below.

**B3 ACCEPTED — PHASE 1 CLOSED** (subject to the `.venv` confirmation of this repair, then committed).
- Subject and event binding holds for every named target: 070, 068, 102, 015/068 age, 061 (B2), and now 065.
- No true fact was lost to B3, no new silent false write, the prompt is byte-identical, and mnw is 0. v2 is 67/114.
- The next roadmap step is **Phase 2 / Batch B — the canonical integrated Life Record and its one writer**, then Batch C, the actual Questionnaire V2 in Hornelore.

## Batch B — build plan (2026-09-23), for Chris's approval before code

**Goal:** Hornelore has **one coherent record of a person's life**, with one writer. The questionnaire (Batch C), Lori and Profile Seed (Batch D) and the package (Batch E) later converge on it. **This is a build plan, not a research phase.**

**Fixed inputs — nothing here is re-decided.**
- **Decisions:** D7(a) canonical occurrences **beneath** the DOB + seven-era scaffold · D8(a) **shared SQLite**, narrator isolation in the writer and data model · D9(a) the graph becomes a **projection**, and its PUT gets a version check until then.
- **Design:** `WO-LIFE-RECORD-01` §2–§5: the model (§3), the writer contract (§3.10), names (§4), dates (§5), counts, and story ownership (§2.6).
- **Owed from Repair A:** a durable *unknown* life status, and the server-side version check on the graph PUT.

**What Batch B does NOT do:**
- no UI change (the questionnaire is Batch C);
- no Lori or Profile Seed change (Batch D);
- no package or export change beyond the erase and export **lanes** every new table needs (Batch E does the rest);
- no per-narrator database;
- no migration of live data — the working root holds 0 people (§0A);
- no extraction work.

### The build order — five chunks, one coherent batch

**B-1 · Schema.** One new migration, `0063_life_record.sql`, through the existing filename-tracked runner. Every table is narrator-scoped.

| table | holds |
|---|---|
| `lr_record` | one row per narrator: `narrator_person_id`, `revision`, `schema_version` |
| `lr_people` | stable id, `life_status` ∈ {`deceased`, `explicitly_living`, `unknown`} (default **unknown**, never inferred), `birth_event_id`, `death_event_id` (pointers, §3.8) |
| `lr_names` | `full_text` as supplied (never parsed), supplied parts, `family`, `birth_family`, `kind` (current / former / variant / also-known-as), `use`, optional period, `pronunciation`, `origin_story` |
| `lr_places` | shared places, referenced by id, never text-rewritten |
| `lr_events` + `lr_event_participants` | typed occurrences (birth · death · union · separation · move · education · work · service · …); date as **text + optional EDTF value + precision** (§5); place; participants with roles |
| `lr_relationships` | subject → other, kind, `described_as`, qualifiers, period, basis (stated / derived from event); one direction stored |
| `lr_animals` | their own entity, not people (D1f) |
| `lr_stories` + refs | `origin` captured → **a reference to `story_candidates`, no copied body**; authored → body here; `supersedes` (§2.6) |
| `lr_assertions` | value · concept · subject · **`recorded_by` and `asserted_by` kept separate** · source · `recorded_at` · status · `supersedes` · `conflict_with` |
| `lr_acceptances` | the explicit decision per proposition: `accepted_assertion_id`, decided by, decided at. **Provenance is not truth; acceptance is a human act** (§2.4) |
| `lr_revisions` | audit: revision, base revision, changed paths, actor, time |

Every table gets a `DbLane` entry in `narrator_data_inventory.py` **in this batch**. Without one, narrator erasure would miss the table — the §3.11 gate.

**B-2 · The one writer.** `services/life_record/writer.py`: `apply_changes(narrator_id, base_revision, changes, actor)`, per §3.10.
- `set` / `add` / `remove` on addressed paths (`people/<id>/lifeStatus`, `people/<id>/names/<id>`, `events/<id>/date`, …).
- **`expectedPrevious` required on every `set` and `remove`**, including the explicit absent case.
- **Conflict per path:** rejected if and only if a path's current value differs from its `expectedPrevious`; unrelated concurrent edits both succeed.
- Runs inside `BEGIN IMMEDIATE`, all-or-nothing. A conflict names every offending path with its current value, and writes nothing.
- **Every id is checked to belong to this narrator**; a cross-narrator reference is refused.
- The model rules run on the resulting record **before commit**; a violation rolls back.
- Routes: `GET /api/life-record/{narrator_id}` writes nothing; `PATCH` calls the writer.

**B-3 · Identity rules — enforced by the writer, not the UI.**
- Server-side stable ids; **no inferred person merges**; a new name never mints a person.
- `birth_event_id` and `death_event_id` must point at **that person's own** birth or death event. Another person's birth, a union event, or a missing or ambiguous reference is refused.
- A death event implies deceased; nothing infers the reverse. *Unknown* stays unknown.
- **Unknown ≠ No; stated zero is kept.** "Six siblings stated, two named" keeps both.
- Dates keep their text, and "around 1945" never becomes exact.
- Conflicting assertions coexist until one is **explicitly** accepted; a correction supersedes, it does not erase.
- **The model rules are written once.** The 19 rules in `scripts/design/validate_life_record_design.py` move into product code (`services/life_record/rules.py`), and the design validator becomes a thin wrapper that imports them.

**B-4 · Graph as projection (D9).**
- `project_graph(narrator_id)` rebuilds `graph_persons` / `graph_relationships` **from the record**.
- The graph PUT (`relationships.py:88`) gets an expected-revision check **now**, so it cannot silently overwrite. That discharges the Repair A debt.
- The UI keeps using its current graph and questionnaire until Batch C switches it to the record. Batch B adds no second UI truth.

**B-5 · Acceptance on real SQLite.** A fresh isolated root, migrated by the product's own runner, with fictional narrators only.
- **Required for Batch B:** every item of the Phase 2 exit gate (below).
- **Also:** the design validator's rules and contracts, run against the record **as assembled from the database**, not against a hand-built JSON.
- **Concurrency:** two concurrent writers — disjoint paths succeed, the same path conflicts; a stale write is rejected.
- **Plus:** tests and a mutation gate for each writer rule. The gate is `.venv`-run, like B2 and B3.

**B-5 acceptance fixture** (Chris, 2026-09-23 — focused, not a giant program), each on real isolated SQLite:
- create a person;
- add relationships;
- an approximate DOB;
- two conflicting DOB assertions, then accept one;
- correct it later without deleting history;
- living / deceased / unknown;
- same-name distinct people;
- a stale same-path write rejected;
- a non-overlapping concurrent edit allowed;
- an atomic multi-part write;
- no cross-narrator contamination;
- the graph projection agrees with the canonical data.

**Phase 2 exit gate** (Chris's requirements sheet; covered by the fixture above plus these):
- one narrator with several related people;
- the same fact type about different people stays on the right person;
- current and former name belong to **one** person;
- current pronouns persist;
- unknown life status stays unknown;
- approximate dates stay approximate;
- conflicting assertions coexist until one is accepted;
- a correction does not erase provenance;
- a stale update cannot overwrite newer information;
- narrator words stay separate from extracted facts (a captured story is a reference, never a copied body);
- an unaccepted event does not appear as a promoted Life Map event.

### Settled by Chris, 2026-09-23 — nothing left to ask before B-1

- **Pronouns:** optional **person** facts, for any person; custom values supported; history optional and time-bounded; **never inferred**. Pronouns do not imply gender identity.
- **No structured gender-identity or sexual-orientation fields in Batch B or C.**
- **Former names:** they do not create another person, and carry a `use` and an optional period. **They are not disclosed merely because they exist.**
  - Batch B stores `use`, default `historical_only`.
  - Batch D enforces it for Lori and the memoir.
- **Everything else comes from D1–D13, unchanged.** In particular:
  - `person.death.reported_age` is a reported assertion, and a computed age is never stored as that fact;
  - service is `event.service.*` with the right person as participant;
  - the seven-era scaffold stays;
  - age is always `life_spine.validator.compute_age` (`validator.py:110`) — no second formula.

### The code surface checked — the only discovery Batch B needed

| what | found | consequence |
|---|---|---|
| **schema mechanism** | `db/migrations/*.sql`, applied by filename through `migrations_runner.run_pending_migrations` (`db.py:1586`); latest `0062` | **`0063_life_record.sql`.** No `_ensure_*` imperative schema for the new model |
| **existing stable id** | `people.id TEXT PRIMARY KEY` (`db.py:623`) is the narrator | **retained:** the narrator's own record person **is** `people.id`. Every other person gets a server-issued id. No existing id is rewritten; the working root holds 0 people, so nothing is migrated |
| **erasure** | `PRAGMA foreign_keys=ON` (`db.py:149`); `hard_delete_person` relies on the FK cascade (`db.py:6117`); graph tables cascade from `people(id)` | every `lr_*` table carries `narrator_id REFERENCES people(id) ON DELETE CASCADE`, plus a `DbLane` entry so inventory and export see it |
| **captured words** | `story_candidates.id TEXT` (UUID) (`0004`) | `lr_stories.candidate_id` references it; a captured story never copies the body |
| **graph writers** | `routers/relationships.py`: full PUT `:88`, person upsert `:95`, person delete `:119`, relationship upsert `:126`, relationship delete `:149`. **The UI calls only GET and PUT** (`bio-builder-graph.js:981`, `:1043`) | **a revision covers all five writers.** Every graph write bumps it; the PUT requires the revision it hydrated (409 if stale); GET returns it. The only UI change is the graph client sending back the revision it read, which is the guard itself, not Batch C UI |
| **compare-and-write pattern** | `questionnaire_persistence.py:384`: `BEGIN IMMEDIATE` around compare-and-write | the writer follows the same pattern |
| **model rules** | 19 rules, a reference `apply_changes` and `resolve_life_span` in `scripts/design/validate_life_record_design.py` | they move into `services/life_record/`; the script imports them. **One copy of the rules** |

**Stated plainly, the one transitional fact:**
- Between Batch B and Batch C, the record has **no UI writer yet**, so the live graph is still written by the UI's PUT, **now version-guarded**. `project_graph()` exists and is proven equal to the record in B-5.
- **Batch C** switches the UI to the record's writer and removes the UI's graph writes. From then on the graph is **only** a projection.
- No replacement shadow store is created in the meantime.

## Batch B — built and CLOSED (2026-09-23). Phase 2 CLOSED

*(The plan above said "21 rules". The validator has **19** — corrected in place.)*

**Built exactly as planned, with two deliberate deviations. Both come from "one fact, one home":**
- **Life status is not a column.** It is `person.life_status` assertions, and `lifeStatus` is **derived** at assembly: the accepted assertion, else the only live one, else absent (= unknown). A column beside the assertions would be a second home for one fact.
- **A date is not an event column.** It is an assertion on the event, under the event type's catalog concept. The assembly carries `dateAssertions` + `acceptedAssertionId` + a derived `date`, which is exactly the shape the moved rules read. Two live accounts with no decision assemble with **no** `date`.

| chunk | what landed | evidence (sandbox, `python3`, `PYTHONPYCACHEPREFIX`) |
|---|---|---|
| **B-1** | `0063_life_record.sql` (14 `lr_*` tables, single-column keys, `narrator_id` cascade from `people`); 14 `DbLane`s + `ColumnRef`s; concept `person.pronouns` (catalog 85 concepts) | inventory parity 16 OK · erasure 38 + 4 + 51 (12 skipped) OK · package export 24 · restore 21 · roundtrip 11 · encoded refs 20 OK · concept plan 12 OK |
| **B-3** | the 19 rules moved **verbatim** to `services/life_record/rules.py`; age reuses `life_spine.validator.compute_age`; the design validator imports them | validator: 19 rules · 12 situations · 20 refusals · 11 contracts, DESIGN COHERENT · its mutation gate: every mutation caught |
| **B-2** | `store.assemble` (reads only) · `writer.apply_changes` (per-path `expectedPrevious`, `BEGIN IMMEDIATE`, ownership on every id, catalog fail-closed, rules before commit, `lr_revisions` audit with previous values) · `GET`/`PATCH /api/life-record/{narrator_id}` | `tests/test_life_record_writer.py` — the B-5 list, **34 tests OK** |
| **B-4** | `0064_graph_revision.sql`; all five graph writers bump the revision; the PUT needs the hydrated revision (**428** if none, **409** if stale); rows tagged `source='life_record'` / ids `lr:*` are writable **only** by `graph_projection.project_graph`, which the writer runs **inside its own transaction**; the graph client sends back the revision it read, serializes its PUTs, and on a 409 re-reads and retries **once** | `tests/test_life_record_graph.py` **17 OK, 2 route tests skipped** (no fastapi in the sandbox — `.venv` must run them) · JS harness **52 checks** (new revision cases R1–R3), every client mutant caught |
| **B-5** | `scripts/design/mutate_life_record_writer.py` — writer, assembly, graph guard and projection | **29 required mutations caught** (`.venv`, 2026-09-23: 170 tests OK, zero skips; baseline 53, 0 red). 4 single-layer mutations report `info`, because each guard has a second layer. **Those single guards are not independently test-critical; the invariant is.** Three are proven by a mutation that removes BOTH layers (another narrator's candidate: writer + `rules.py`; routes touching projected rows: source guard + `lr:` prefix). The fourth — a captured story carrying a body — has as its second layer `0063`'s CHECK constraint, which the gate does not mutate; that invariant rests on the schema |

**The mutation gate found three tests that could not fail, and they were fixed before anything was reported green.**
- "no in-place assertion edit" was refused one layer earlier than the guard it named. A test that re-adds an existing id now pins that guard.
- "cross-narrator" was stopped by narrator-scoped reads before the ownership check ever ran. An assertion about another narrator's person now pins the check.
- "a captured story never copies the words" named a candidate that doesn't exist, so it was refused for the wrong reason. It now uses real `story_candidates` rows.

**Exit-gate item not closable in Batch B, stated rather than implied:**
- *"an unaccepted event does not appear as a promoted Life Map event"* — nothing outside `services/life_record/` reads an `lr_*` table (grep, 2026-09-23). The item therefore holds **vacuously**: no Life Map reader of the record exists yet.
- The positive version is Batch D's. **Beware the name collision:** `trip_timeline_bridge.sync_trip_to_life_record` is older, unrelated trip code and does not touch `lr_*`.

**The transitional fact, now concrete:**
- Projected graph rows sit beside the rows the UI writes. The UI's PUT must return projected rows unchanged, or it is refused (**422**).
- Nothing writes the record yet except `PATCH`, so today no narrator has projected rows.
- Batch C moves the questionnaire onto the writer, and the UI's graph writes retire.

**Pre-existing, unchanged:** the two `test_narrator_merge` composite-key failures (migrations 0059–0061) reproduce at HEAD. `0064` briefly joined them only because its **comment** read "primary key (the …"; the comment was reworded.

### Batch B closeout — `.venv` verification, run by Chris 2026-09-23

| gate | result (`.venv`, Python 3.12, WSL) |
|---|---|
| Life Record writer + graph + inventory parity + erasure + person-delete integrity + concept migration plan | **170 tests OK — no skips.** The two FastAPI route tests ran |
| writer / graph mutation gate (`mutate_life_record_writer.py`) | baseline 53 tests, 0 red · **every mutation caught** (29 required, 4 `info`) |
| design validator + its mutation gate | DESIGN COHERENT · **every mutation caught** |
| Bio Builder graph harness (node) | **52/52** |
| Portable Narrator preservation — export · restore · roundtrip · encoded references | **76 tests OK** (1137 s). The two `trips.jsonl sha256 validation failed` lines are the suite's deliberate tamper tests refusing, as designed |

**Batch B is closed, and with it Phase 2.** There is one trustworthy canonical Life Record and one authoritative writer; the graph is its version-guarded projection, and the new `lr_*` lanes left export, restore, roundtrip and encoded references intact.
- **Carried, non-blocking:** `docs/BACKLOG.md` §11 (the `bagit` → `pkg_resources` deprecation, and `graph_revisions` against the wipe script).
- **Stack boundary:** the stack was down at close. The next start is the first Phase 3 product session, with no prior server state carried over.

## Batch C — review of Chris's brief against the tree (prepared 2026-09-23, before code)

**The brief stands as written. The Life Record design is not reopened.** This section records what the tree already provides, the one real gap, and the defaults taken, so C-1 starts without a discovery pass.

**Already in place** (each claim was read from the code):
- **Every value the eleven topics need has a catalog concept** (`concept_catalog_v1.json`, 85 concepts), including:
  - military service, heritage, languages, faith raised and current, interests;
  - education, work, retirement, service and activity occurrences;
  - reported counts;
  - the `story.*` kinds: memory, lesson, message, tradition, home, reflection, `life_today.routine`, and so on;
  - `trip.view`, a `trip_ref` owned by the trip domain.
- **Names and pronouns:** `lr_names` carries kind, `use` and period, and the writer defaults former names to `historical_only`. Pronouns are a `person.pronouns` assertion (`many`), so optional history is simply more than one assertion.
- **Dates:** the writer stores `{text, value, precision}` and never normalizes `text`. "around 1945" round-trips.
- **Concurrency:** per-path `expectedPrevious`. The editor sends the value it hydrated as `expectedPrevious`, so a stale same-path edit is a 409 naming the path and its current value, and disjoint edits both save.
- **Provenance:** `recordedBy` is the writer's `actor`, and `assertedBy` and `source` are required per assertion. **Default taken:** operator-typed facts go in as `source=operator`, `assertedBy=operator`. They are marked narrator-asserted only when the operator explicitly chooses "the narrator told me" (or a family member or a document) on the card. Nothing is silently labelled a narrator memory.
- **Stories:** `lr_stories` (authored, or captured by reference to `story_candidates`). The paragraph questions write stories, never a notes fact.
- **Harnesses:**
  - `tests/harness/bio-builder-harness.js` (jsdom plus the unmodified UI JS, with a fake server) is the pattern for the DOM harness that observes the real outgoing `PATCH`.
  - Playwright specs in `tests/e2e/` cover C-7, run **inside WSL** against Chris's stack (a sandboxed agent browser cannot reach it — `CLAUDE.md`).

**THE ONE REAL GAP — recoverable Remove (D10).** The brief says "recoverable removal/tombstone/history semantics as designed". **The Life Record has no such design.** What Batch B does today:
- `remove` hard-deletes an entity row, and is recoverable only by reading `lr_revisions` (`writer.py` `_entity`, `remove`).
- Removing a person is refused while any assertion about them remains, and assertions can never be deleted — so **a person can't be removed at all once facts exist**.
- **What C-6 needs:** a removal *state*, not a DELETE.
  - An entity carries `removed_at` / `removed_by`, set through the writer with `expectedPrevious`, so a stale draft cannot quietly undo or redo it.
  - The assembly omits removed entities by default and can show them for recovery.
  - The graph projection drops them.
  - The writer refuses edits to a removed entity as a conflict, which is what stops resurrection by a stale draft or a late GET.
  - Hard deletion stays reserved for narrator erasure.
- **This extends the record's lifecycle; it does not change the model.** It is migration `0065` plus writer paths. **Taken as the C-6 design unless Chris objects.** Assertions already have `rejected` and `superseded` and need nothing new.

**Small items, with the defaults taken:**
1. **The tri-state is not wide enough.** `person.military_service` is `boolean_3` (yes / no / unanswered), and the brief asks for Yes / No / Unknown / Prefer not to answer.
   - Values become `yes | no | unknown | declined`, and blank means no assertion at all.
   - The writer gains a catalog value check for enum concepts: fail closed, so an HTML control cannot invent a value.
   - Life status is already `deceased | explicitly_living | unknown`.
2. **The catalog marks some V2 fields `not_offered`** (military service, the reported counts). Batch C flips them to `editable` in `concept_catalog_source.py` and recompiles; the catalog is data, not the record design.
3. **Topic 10 (Life today) has only `story.life_today.routine`.** Living situation, caregiving, technology, projects and goals go in as `story.*`, or as new `story.life_today.*` kinds added to the catalog. No new fact tables.
4. **Topic 2's name:** the spec says "Family of origin and caregivers" (`WO-LIFE-RECORD-01` §8.2); the brief says "Family and caregivers". **The brief wins.**

**The legacy questionnaire:**
- Twenty sections in `bio-builder-questionnaire.js` (2,313 lines), saved as a whole document through `PUT /api/bio-builder/questionnaire` → `merge_whole_document`, with `fullSync` → graph PUT.
- **Default taken:** V2 takes over the Bio Builder's Questionnaire tab. The legacy tab becomes a **read-only "Earlier answers"** view with no Save. No second authority survives, and the old save path is no longer reachable from the UI.
- Legacy leaves are **retained as legacy**; nothing is deleted. `concept_migration_plan.plan()` names every leaf's disposition, so what is not yet in the record is visible rather than silently dropped.
- The working root holds 0 people, so there is no live data to migrate now. A migration *writer* for the family packages belongs to Phase 7 preparation, not Batch C.

**Build order: C-1 → C-7 exactly as in the brief.** The only additions are migration `0065` (removal state) and the enum value check, both landing with C-6 and C-4 respectively. There is no micro-approval between chunks, and non-blocking UI issues go to `docs/BACKLOG.md`.

### Batch C — the review, as refined before code (Chris + ChatGPT, 2026-09-23)

- **Order:** C-1 → C-2 → C-3 → C-4 → C-5 → C-6 → C-7 → Batch D. **C-7 is the closeout gate, not another development phase.**
- **An early one-field smoke, before C-7.** Once the first real Save path exists (C-3 or C-4), run one check against the live API: open a fictional narrator, edit one field, the browser sends a real `PATCH /api/life-record/…`, reload, and the adapter reconstructs the value. It is a cheap check that the UI and the server agree on the PATCH shape before eleven topics are built on it.
- **Migration, split three ways:**
  - **C:** legacy answers are visible read-only, and nothing migrates.
  - **E:** prove the generic old-package/schema migration on fictional data if package compatibility needs it.
  - **Phase 7:** apply the proven path to real archived narrators, deliberately.
- **ONE epistemic vocabulary** for every yes/no-shaped question: `yes | no | unknown | declined`, and blank = no assertion. Controls do not invent their own.
- **Removal:** removed is a durable canonical state, and hard deletion is narrator erasure only. C-6 owns it; C-1 does not attempt it.

### C-1 — built 2026-09-23: the read model

**`ui/js/questionnaire-v2-model.js`** — `fromRecord(record, {trips?})` turns the record exactly as `GET /api/life-record` returns it into the eleven-topic view.
- **It is pure:** no fetch, no storage, no DOM, no clock.
- **Identity:** every person, relationship, event, place, animal and story keeps its record id. One person appearing in several topics is the same id.
- **Relationships are read in both stored directions** to give the role relative to the narrator: parent, caregiver, sibling, grandparent, partner, child, grandchild, wider, cared_for. A person unrelated to the narrator goes to topic 4 "others" — never lost.
- **An answer is `blank`, `value` or `unresolved`.** Blank means no live assertion; 0, "no" and "unknown" are values; two live accounts with no decision are unresolved, and both are shown.
- **Names come through whole**, preferred first then current, and former names are kept. Stories are either authored text or a captured `candidateRef`, never a copy. Trips arrive as `{tripId, label}` references only.

**Evidence — `tests/test_qv2_adapter.py`, 9 OK (sandbox `python3` + node):**
- A difficult fictional narrator is written through the **shipped writer** onto `init_db` SQLite, then read through the **shipped** adapter under node. The narrator has:
  - a current name plus a former one, and custom pronouns;
  - an approximate DOB, a disputed parent DOB, and a caregiver aunt with a stated 0;
  - military answers yes / no / unknown / blank, and two same-named people;
  - a former spouse with a period, a union dated to the month, and children in both stored directions;
  - a grandchild with no intermediate relative, and an in-law unrelated to the narrator;
  - a range-dated home, a current home with a co-resident, work and service events, a dog, and authored plus captured stories.
- **Zero IO:** the probe traps fetch, XHR, `localStorage`, `sessionStorage`, IndexedDB, `document`, `navigator` and sockets, and the DB file hash is unchanged across the run.
- **9 adapter mutations, all caught:**
  - blank collapsing into a value;
  - guessing between two accounts;
  - normalizing a date's text;
  - reading `child_of` in one direction only;
  - copying a captured story's words;
  - dropping the unrelated;
  - copying a trip whole;
  - touching storage;
  - hiding former names.

**A Batch B defect found and fixed by C-1 (`rules.py`):**
- `rule_competing_claims_kept_and_linked` compared every assertion list as ONE proposition. So "Igbo" beside "Swedish" was refused as an unlinked dispute, and **no narrator could record two languages or two heritages**.
- The rule now reads cardinality from the one catalog (`_many_valued_concepts`), where `many` means several facts. An event's `dateAssertions` are unaffected: one period per event is still one proposition.
- **Pinned:**
  - by 2 writer tests (two languages save; two unlinked accounts of a `one` concept are still refused);
  - by 2 new mutations (the writer gate: every mutation caught, baseline 55);
  - the design validator is still COHERENT, and its gate still catches every mutation.

**Two schema gaps C-4 must close first — both found while mapping, neither a redesign:**
1. **Work, education and separation events cannot carry a date.** The writer accepts dates only for event types with a catalog date concept (`store.EVENT_DATE_CONCEPT`: birth, death, union, move, service). The brief's multiple *dated* jobs and education entries need date concepts `event.work.period` and `event.education.period` (plus a separation date) added to the catalog and the map.
2. **There is no event type for community activity.** The catalog has `event.activity.{organization, period, role}`, but `lr_events.type` has no `activity`. The fix is a migration adding it (SQLite needs a table rebuild for a CHECK change) and `activity → event.activity.period`.

**For C-5:** `lr_stories` carries a `kind` but no catalog concept, so a Life Today routine and a generic description cannot be told apart. The adapter places a story by concept when the record has one, else by kind and what it refers to. C-5 decides whether stories get a nullable `concept_id` (a catalog `story.*` concept).

### C-2 — built 2026-09-23: the Questionnaire V2 shell

**`ui/js/questionnaire-v2.js`.** The Bio Builder's **Questionnaire** tab *is* V2 now (`bio-builder.js` → `LorevoxQuestionnaireV2.render`).
- **Layout:** eleven topics in a side nav, a topic panel showing the Life Record through the C-1 model, a header with the record revision, the unsaved count, **Save** and **Discard changes**, and inline messages for saved / info / conflict / refused.
- **One real field ships, to make the pipe real end to end:** the narrator's birth order, a one-valued assertion. Every other field arrives with C-3 to C-5 on the same framework.
- **Writes, exactly:**
  - Opening, hydrating, topic navigation and narrator switch send only GETs and write no storage.
  - An edit writes the draft `lorevox_qv2_draft_<pid>`, stamped with the revision it was made against.
  - **Save** sends one `PATCH /api/life-record/<pid>` of writer operations, never a document:
    - a first answer is `add`;
    - a changed answer adds a new assertion that `supersedes` the old one, then sets the old one's `supersededBy`, and its `status → superseded` with `expectedPrevious`.
  - The record is then **re-read**, and the draft is cleared.
- **Conflict and refusal:** a 409 is shown with the paths and their current values, and the draft is kept; nothing is resent. A 422 shows the refusal.
- **Provenance:** operator-typed values go in as `source=operator`, `assertedBy=operator`, `recordedBy=operator`.

**Earlier answers:**
- A new Bio Builder tab renders the legacy questionnaire **read-only**: values only, with no input and no button.
- **Operator Intake is read-only too.** It was a second live editor of the same legacy questionnaire (a whole-document `PUT` at `operator-intake.js:322`); its Save now refuses, the button is disabled, and a banner points to the Questionnaire tab. The legacy 20-section editor is no longer reachable from the UI. Nothing was deleted.

**Evidence** (sandbox `python3` + node + jsdom):
- **`tests/test_qv2_shell.py` + `tests/qv2_shell_harness.js`: 25 DOM checks.**
  - It loads the real `api.js`, model and shell into jsdom and drives them by clicks and change events.
  - **The fake server is not a double:** every Life Record request goes to `tests/qv2_bridge.py`, which runs the shipped writer on the test's real SQLite.
  - The DOM checks cover: open, navigate, switch, a late response for the previous narrator, dirty state, the narrator-scoped draft, navigating with an edit pending, reload and restore, discard, the Save PATCH shape, re-reading, a stale-tab 409 shown with the draft kept, a first answer, and Earlier answers holding no controls.
  - **The DB is then checked in Python.** Exactly one Nora write, the Save, landed; the stale tab's did not. The old account is superseded and linked, and the new one is operator-recorded and operator-asserted. Owen got one first-answer write and nothing leaked.
- **12 shell mutations, all caught.** The first run found one survivor: "navigation saves" was invisible because nothing was pending. A check that navigates *with an edit pending* now pins it.
- `test_operator_intake_write_safety.js`: 5/5, including the new read-only check, whose guard mutation is caught.
- The legacy harnesses still pass: `test_bio_builder_save_sequences.js` and the graph harness, 52/52.

**Still writing the legacy questionnaire — Batch D's, named, not touched:**
- `session-loop.js:744` and `:1021` — Lori's session loop PUTs identity and answers.
- `bio-builder-core.js:1493`, `:1720` and `:1979` — identity sync and Reset Identity.

These are Lori and Profile Seed paths. Batch D moves them to the Life Record. **They are not operator editors,** so there is still only one editable authority.

**Next — the early one-field smoke (agreed), on the first stack start:**
- Operator: create a fictional narrator → Bio Builder → Questionnaire → birth order → Save → reload.
- Then read the value back with `GET /api/life-record/<pid>`.
- It proves the real browser and the real HTTP route agree on the PATCH shape before C-3 builds on it.

### C-2 — LIVE ACCEPTANCE FAILED (2026-09-24); repair C-2R1–R7

**C-2 is not closed.** Commits `98744b0` and `341edbd` stand; nothing is reverted.

**Why it failed, as measured:**
- `.venv`: `test_qv2_shell` **timed out at 170 s**. The bridge spawned a new Python per request, and importing `api.db` on `/mnt/c` is slow.
- **Live, in Chris's Chrome** (checked by Claude through the extension):
  1. **No fictional narrator could be created easily.**
     - The real-narrator form demands legal name, preferred name, an **exact** DOB, birthplace, residence and **pronouns**, plus consent (`narrator-intake.js:310-328`).
     - The testing path was a blocking `window.prompt()`.
  2. **A brand-new narrator could never make the first Life Record write.**
     - A new narrator reads as revision 0 with no people. That is correct, and GET writes nothing.
     - The model returned no narrator, so the shell rendered "Nothing recorded yet" with **no input**.
     - The writer would have created the narrator's person on the first write, but the UI offered nothing to write.
     - **The harness missed it because the fixture pre-seeded every narrator's Life Record.** That breaks the doctrine rule that a fixture may not supply the property being proven.
  3. **The first real Save returned 503: `sqlite3.OperationalError: table lr_revisions has no column named id`.**
     - Chris's root applied a **draft** of `0063` (composite keys on four tables) at 2026-09-24 00:09 UTC, while B-1 was still being edited with the stack up. That was 18:09 local; the final file was committed at `4918a7e`, 20:53.
     - The migration runner tracks filenames, so it never re-applied the final file.
     - **Lesson: a migration is "landed" the moment any running stack applies it — committed or not. Never edit a migration while a stack that could run it is up.**
     - All 14 `lr_*` tables on that root were **empty**, so the repair (drop them and let the runner re-apply `0063`) loses nothing.
  4. **The retired Questionnaire First path still steered narrator open.**
     - The browser still held `hornelore_session_style_v1 = questionnaire_first`. It survived the root cleanup because it lives in the browser.
     - `session-loop.js` had retired QF chat turns, but `hornelore1.0.html:6290` and `session-style-router.js` still ran the QF open bypass and identity walk.

**Repairs (sandbox-verified; the live check follows the restart):**

| # | Repair | Evidence |
|---|---|---|
| R1 | **New Narrator:** an inline "fictional narrator for testing" name field and button (no `prompt()`), which creates the narrator and **opens Bio Builder → Questionnaire**. "Save and continue to Bio Builder" now does that too | Live: one `POST /api/people`, Bio Builder opens on V2 for the new narrator |
| R2 | **Life Record bootstrap:** creation writes the identity floor **through the one writer** (`services/life_record/identity.py`, from both creation routes): name (never split), preferred name, pronouns, birth date **as typed** (an ISO day is a day; other text keeps its words), birthplace. The model also presents an empty, editable narrator when the record has none; that is a view only, and nothing is stored by building it | `tests/test_life_record_identity.py` (4 + 1 route test that needs FastAPI) |
| R3 | **Empty-state UX:** with no narrator, the eleven topics show disabled beside a "Create or select a narrator" prompt. A new narrator's topics are live and say "the first Save creates their record". No internal id is ever shown as a name | shell harness |
| R4 | **Legacy intake authority:** the seven biography sections are removed from the New Narrator form, and it sends identity + consent only. The server's section fan-out has no UI caller now and is **retirement-bound** (inventory B14) | Live: the modal has 0 sections |
| R5 | **Startup:** the QF open bypass and identity walk now honour the same opt-in (`lv_qf_live_ownership=1`) as the rest of the QF retirement | Live: open status `incomplete`, not `questionnaire_first` |
| R6 | **Tests:** one persistent bridge process; `settle` waits for real replies. New scenarios: no narrator, and a **FRESH narrator with no Life Record** (not pre-seeded), whose first Save creates the record; the DB checks confirm `lr_record` rev 1 and the narrator's `lr_people` row | `test_qv2_shell`: 30 checks, 45 s in the sandbox. The mutation that drops the empty-narrator view is caught |
| + | **Rules crash:** a year-precision date with no normalised value raised `None.count` (a 500, not a refusal) | Fixed; pinned by `test_a_year_with_no_normalised_value_is_kept_not_a_crash` |
| R7 | **Live acceptance**, run in Chris's Chrome 2026-09-24 after the database repair: <ul><li>Drift check: **0 differ, 0 missing** (258 objects).</li><li>The browser still held `hornelore_session_style_v1=questionnaire_first`, with no opt-in, so the retired path was **actively provoked**.</li></ul> | **PASS**, all 15 steps — see the list after this table |


**R7, step by step (2026-09-24, live):**
1. The fictional create (inline button) sent one `POST /api/people`.
2. The narrator was selected automatically, with open status `incomplete` and **no QF state**.
3. Bio Builder opened on V2.
4. All **11 topics** were visible.
5. The header showed **"Maren Holt (fictional)"** at **record revision 1**: the server wrote the identity at creation.
6. Real keystrokes in birth order marked **1 unsaved change**.
7. Save was clicked.
8. The browser sent **`PATCH /api/life-record/8a144b74-… → 200`**, after its CORS preflight, then a re-read GET.
9. There was no 503 and no "Failed to fetch".
10. **"Saved."** appeared and the revision went **1 → 2**.
11. Full page reload: no narrator was selected on cold start.
12. The narrator was re-selected and V2 reopened.
13. **"second of three"** came back from the server at revision 2, with nothing unsaved. The server stores it as `operator_entered`, asserted by the operator and recorded by the operator.
14. All 10 Bio Builder tabs and all 11 topics were viewed: **zero writes, revision still 2**.
15. Narrator Session was opened: **no Bio Builder hijack, no QF state, Lori silent, zero writes.**

**Seen in R7, not C-2 regressions — carried forward:**
- **The room's readiness card says "missing: name and date of birth"** although the name is in the Life Record and on the `people` row. The gate reads the legacy profile store, which the fictional path does not write, and it requires a DOB. Its "Complete profile basics" button starts the legacy identity onboarding, which writes old stores; it was deliberately not clicked. → **D-0**: readiness reads the Life Record, plus the open real-narrator identity-floor decision.
- **The narrator-room style pill shows "Questionnaire first"** from the stale stored value. → **C-2b**: normalise the retired stored style on load.
- **The Bio Builder subtitle shows the id `8a144b74`.** → **C-2b** (name + revision in the header).


**C-2 ACCEPTED / CLOSED 2026-09-24.**
- **R7 live:** PASS (above).
- **Focused gate** (`.venv`, WSL): **119 tests OK, 0 skips, 1 expected failure**, in 53.5 s (1m11s wall). The expected failure is the documented `test_profile_seed_ordinary_intake_reachability` defect; had it begun passing, unittest would have reported it as an unexpected success.
- **Operator Intake write-safety:** 5/5.
- **Process note, recorded rather than hidden:** `ss` showed ports 8000 and 8082 still listening when `repair_draft_0063.py` ran, so the repair ran with the old stack apparently up, contrary to the procedure. It was **not** reopened, because every later check came out clean:
  - the script's own fresh-root comparison;
  - `integrity_check` ok, and `foreign_key_check` clean;
  - drift check 0 differ, 0 missing;
  - after `start_all.sh` restarted the processes, a real PATCH committed and survived reload.

  **The procedure stands: stop the stack first, and confirm with `ss -ltnp` that 8000/8082 are down.**
- **Next: C-2b**, the Bio Builder consolidation. C-3 follows it.

**The one-time database repair** is `scripts/repair_draft_0063.py`, run with the stack **stopped**. It repairs the database; `0063` itself is not edited.

- **0 · Nothing to do?** If the live `lr_*` schema already equals a freshly migrated root, it exits without a backup and without touching anything. A rerun is a no-op.
- **P · Preflight, read-only.** `integrity_check` must be `ok`, **no migration may be pending**, and there must be exactly one `0063` row.
- **1 · Back up** the database, with the WAL checkpointed into the copy first.
- **2 · Refuse** unless all 14 `lr_*` tables are empty.
- **3–4 · One transaction.** Drop exactly the 14 tables and delete exactly the `0063` row. Then **recompute the pending set inside the transaction**, and roll back unless it is exactly `[0063_life_record.sql]`. Without the row deletion, the filename-tracked runner would never re-run `0063`.
- **5 · Apply** with the normal runner.
- **6 · Compare** every `lr_*` object with the fresh root, and check that `lr_revisions` is keyed on `id`.
- **7 · Check integrity:** `integrity_check`, `foreign_key_check`, and no pending migrations left.

**Rehearsed on copies of the live database:**

| Case | Result |
|---|---|
| the real case | **REPAIRED** — 39 objects identical, integrity ok |
| a rerun | "nothing to repair", no backup |
| another migration pending | refused at P, **file hash unchanged** |
| no `0063` row | refused at P, hash unchanged |
| a non-empty `lr_record` | refused at 2, rows and tables intact. The backup had already been written; the database content was untouched |

**Drift check** (`scripts/check_schema_drift.py`, read-only): before the repair, **exactly 4 of the 258 objects the code builds** differed on the live root (`lr_acceptances`, `lr_event_participants`, `lr_revisions`, `lr_story_refs`); after the rehearsed repair, 0 differed. **Governance:** the immutability rule is now in `CLAUDE.md`, the fresh-database key contract is pinned in `tests/test_life_record_schema_contract.py`, and migration checksums are in `BACKLOG` §11.

**Decision left open (D-0, not assumed):** whether the **real-narrator** identity floor should drop its exact-DOB, residence and pronouns requirements. Those requirements feed Lori's first-turn anchoring and the Profile Seed readiness test (`test_profile_seed_ordinary_intake_reachability`). The fictional path needs only a name today.

## Legacy-surface and authority inventory (2026-09-24, read-only audit, no code changed)

**Locked rule (Chris, 2026-09-24):**
- **Questionnaire V2 is the only normal operator editor of canonical biography.** Truth enters through the Life Record writer and nowhere else.
- Every other biography surface is exactly one of:
  - **CURRENT RECORD**
  - **READ-ONLY · LEGACY**
  - **DRAFT · NOT IN LIFE RECORD**
  - **REVIEW**
  - **DERIVED**
- Nothing is left unnamed or "temporary". Every item below has a destination.

**Two release gates:**
- **Batch C exit — operator-authority gate:** no normal operator-facing biography write bypasses the Life Record writer. This includes New Narrator.
- **Batch D exit — runtime-authority gate:** no Lori, profile, projection, graph, sync or legacy background writer establishes authoritative biography outside the Life Record.

**Source:** three read-only sweeps of `ui/`, `server/`, and every non-GET browser request. Citations are to the tree at C-2 (local, not yet committed).

### A. Operator-facing surfaces — Batch C owns these

| # | Surface | What it does today | Category → destination |
|---|---|---|---|
| A1 | **Bio Builder → Questionnaire** (V2) | `PATCH /api/life-record` | **CURRENT RECORD.** C-3 to C-5 complete it |
| A2 | **Earlier answers** tab | GET only, no controls | **READ-ONLY · LEGACY.** C: retitle it "Earlier Questionnaire Answers — READ ONLY · LEGACY", with the explanation and a pointer to V2. It becomes the **single** legacy location |
| A3 | **Operator Intake** (top-level shell tab "Intake", `hornelore1.0.html:3049`) | Save refuses (C-2), but inputs, "+ Add", "Remove" and "Unsaved changes" still work locally (`operator-intake.js:390, 409, 614-630`). The header comments still say it writes canonical truth (`:13-16`, html `:3405-3412`) | C: **remove it from primary navigation** and fold its content into A2. No Save, Add, Remove, dirty state or "canonical truth" language survives |
| A4 | **The old 20-section editor** (`bio-builder-questionnaire.js`) | Unreachable from the tabs (C-2), but still exported: `LorevoxBioBuilder._saveSection` (`bio-builder.js:743`) and its save markup (`bio-builder-questionnaire.js:1313`) | C: extract only the read-only renderer A2 needs, and unexport the Save, add and remove handlers. Deletion is recorded for D closeout |
| A5 | **New Narrator intake modal** (`+ New`, html `:2943`, modal `:5043-5413` → `narrator-intake.js:377`) | A rich biography form: family, marriage, children, work, military, faith, Today. `POST /api/people/intake` fans it into the people row, **`profile_json`** and **`bio_facts`** (`routers/people.py:564`). "Save and continue to Bio Builder" does not open Bio Builder (`narrator-intake.js:419-426`) | C (C-3): **identity floor + consent → create → open Questionnaire V2.** Any biography field that remains must write through the Life Record writer. The fan-out to `profile_json`/`bio_facts` ends |
| A6 | **Reset Identity** (Bio Builder header `#bbResetIdentityBtn`, html `:4170`; also in Bug Panel `:4677`) | Clears legacy questionnaire, profile basics, projection identity and suggestions. Legacy PUT (`bio-builder-core.js:1979`). `PATCH /api/people` sets DOB/POB to null (`:1984`). Restarts onboarding. **Leaves the Life Record untouched**, so the button lies | C: **remove it from Bio Builder.** Corrections go through V2 with history. A fictional-test recovery tool, if still wanted, lives in the Bug Panel with Life Record semantics (D). Stale "Questionnaire First" wording goes |
| A7 | **Family Tree** (Bio Builder tab) | Add, Edit, Delete, Connect, Seed ×4. **Every edit and seed calls `_persistDrafts` → a whole-document `PUT /api/bio-builder/questionnaire`** (`bio-builder-family-tree.js:391, 435, 488, 500, 650, 775, 873, 967, 1016`). "Graph is the truth model" language at `:877-882` | **A live legacy write from an operator surface today.** C: badge it **DRAFT · NOT IN LIFE RECORD**, stop the server PUT side effect, and correct the "truth" language. D: it becomes a **DERIVED** view of Life Record people and relationships, not an editor |
| A8 | **Life Threads** (Bio Builder tab) | Its own editable narrative graph, seeded from the legacy questionnaire. **Same `_persistDrafts` → legacy PUT** on every edit (`bio-builder-life-threads.js:161, 200, 250, 258, 299, 351`) | C: DRAFT badge, and stop the legacy PUT side effect. **D-0 decision:** retire it, or redefine it as non-authoritative references to Life Map objects. It must not become a second narrative structure |
| A9 | **Quick Capture** | "Save Note" writes localStorage only (`bio-builder.js:739-745`) | **DRAFT · NOT IN LIFE RECORD.** C: badge it, and change "Save Note" to "Keep note" (it never reached the server) |
| A10 | **Source Inbox** | Cards and candidates live in memory only; nothing persists | **DRAFT.** C: badge |
| A11 | **Candidates** | Approve, Merge, Reject — **in memory only, lost on reload** (`bio-review.js:575-598`). The subtitle promises "structured biography" (`:481`) | **DRAFT/REVIEW.** C: badge it, and say plainly that approval here does not enter the Life Record. D: Accept → Life Record assertion |
| A12 | **Bug Panel → Reset BB for Current Narrator** / **Deep Reset Projection** (html `:4887-4915`) | Legacy PUT `{}` (`bio-builder-core.js:1495, 1722`); projection PUT replace (`:1756`). The Life Record is untouched | Developer tools. C: label them "legacy stores only — the Life Record is not reset". D: retire them, or rewrite them against the Life Record |
| A13 | **Peek at Memoir → Edit → "Save & Close"** (html `:10025-10048`) | Replaces the on-page text only. **Not persisted**, and the DOCX/TXT export takes whatever is on the page | Misleading. **Memoir-lane issue → D-0** (operator prose has no store). C: relabel it "Edit this preview (not saved)" |

### B. Review and runtime paths — Batch D owns these (D-0 contract, D-3 Lori)

| # | Path | Writes today | Destination |
|---|---|---|---|
| B1 | **Suggestions** tab: Accept, or "Save this as my value" (`suggestion-review.js:498`) | The server merges into the **legacy questionnaire blob** + `projection_json` (`services/suggestion_review.py:340-601`). Its hints send the operator to old sections that are now read-only (`:327, 335`) | **REVIEW.** D-3: Accept → a Life Record assertion + acceptance. C: fix the hint text to point at V2 |
| B2 | **Shadow Review** Correct, and **Conflicts** Replace/Merge | `projectValue(human_edit)` → `projection_json` PATCH **+ legacy PUT** (Path B). "Questionnaire always wins" means the legacy blob (`shadow-review.js:927`; `conflict-console.js:38, 103`) | **REVIEW.** D-3: resolve against Life Record assertions. C: badge it and correct the "questionnaire truth" wording |
| B3 | **WO-13 Review** → Promote (`wo13-review.js:244, 265`) | `family_truth_rows` / `family_truth_promoted`, which feed `peek_at_memoir` and the chronology | **REVIEW** into a separate truth store. D-0: retire it, or make promotion a Life Record acceptance |
| B4 | **Bug Panel Bio editor** (`HORNELORE_OPERATOR_BIO_EDITOR`) | Enters, approves and resolves **`bio_facts`** directly (`operator_bio_editor.py:223-390`) | **An alternate authority.** D-0: rebuild it as a Life Record assertion/acceptance inspector, or retire its writes. Default-off is not the final answer |
| B5 | Identity onboarding in chat (`app.js:6270-6460`) | One spoken name reaches **four stores**:<ul><li>`lvBbSyncIdentity` → legacy PUT</li><li>`projectValue` → suggestion POST</li><li>`PATCH`/`POST /api/people`</li><li>`saveProfile` → `PUT /api/profiles` (`profile_json`)</li></ul> | D-3: one Life Record assertion, marked narrator-stated. The other stores become projections or retire |
| B6 | `session-loop.js` `_saveBBAnswer` (`:1026`) and `_overwriteBbPersonal` (`:748`) | Legacy PUTs from the retired Questionnaire First walk | D-0: **remove**, not leave dormant |
| B7 | `projection-sync.js` `_syncPrefillIfBlank` (`:435`) / `_syncDirectTrustedWrite` (`:514`) → `_triggerBBPersist` | Every accepted extraction or projection write also sends a whole legacy questionnaire PUT | D-3: stop projecting into the legacy questionnaire |
| B8 | chat_ws correction mode → `projection_writer.apply_correction` (`chat_ws.py:5147`); extraction → `bio_facts` (`HORNELORE_BIO_FACT_ROUTING`, off) | `projection_json`, `bio_facts` | D-3: corrections go through the Life Record supersede path |
| B9 | `POST /api/interview/answer` (`interview.py:288`) | `interview_answers`, section summaries, memoir drafts | D-0: classify it (history, not biography authority) |
| B10 | Trips: `trip_timeline_bridge.sync_trip_to_life_record` | **Misnamed:** writes `timeline_events` + `trip_bio_suggestions`, not `lr_*` | D-0: rename it, and state that trips stay in the trip domain as references |
| B11 | Photo intake / media archive metadata (people, events, dates) | photo and media tables, with people tagged by free text | D-0: classify it (media metadata; linking people to Life Record ids is later work) |
| B12 | `init_db` startup `_wo13_backfill_facts_to_family_truth_rows` (`db.py:336, 1467`) | **Automatic at every startup** | D-0: retire it along with B3 |
| B13 | The `people` row: `display_name`, `date_of_birth`, `place_of_birth` | Identity duplicated outside the Life Record; written by intake, onboarding, `PATCH /api/people` and identity approval | D-0: the people row is the narrator **shell** (id, consent, label); DOB and POB become a projection of Life Record birth |
| B14 | Legacy API and storage | `PUT /api/bio-builder/questionnaire` (+ `/answer`, `/narrator-answer`); `bio_questionnaire_writer` | **Retirement-bound** at D closeout, once B1–B7 are moved. `GET` + `bio_questionnaire_view` stay as the read-only legacy/migration adapter |
| B15 | Graph API (`routers/relationships.py:3-14` still calls itself "Canonical relationship graph API") | Manual PUT, POST and DELETE on a projection (guarded since B-4) | C: correct the docstring. D-0: remove manual mutation once A7 is a derived view |
| B16 | Legacy browser drafts (`lorevox_qq_draft_`, `_ft_`, `_lt_`, `_proj_draft_`) | Unrelated to V2's `lorevox_qv2_draft_` | **V2 never hydrates from them** (true today: `questionnaire-v2.js` reads only its own key). C-6/C-7: inventory the old keys, then ignore them or offer an explicit import. Nothing is silently resurrected |
| B17 | The Bio Builder popover comment "Truth rule: Bio Builder writes only to state.bioBuilder" (html `:4158`) | False: A6, A7, A8, B1 and B2 all write server stores | C: correct it |

### C. Legitimate and kept (named so they are not mistaken for gaps)

- **Story candidate review** (Bug Panel, `PATCH /api/operator/story-candidates`): **REVIEW** of the narrator's recorded words and their placement. This is story ownership, not a second biography store.
- **Portable Narrator restore:** writes `lr_*` in bulk as a package transfer. It is not an editor.
- **Delete / restore narrator.**
- **Profile Seed pause/resume.**
- **Life Map, chronology accordion, timeline, photo timeline:** read-only (**DERIVED**).

### Additions to C-7

- **Legacy-surface sweep.** With the difficult fictional narrator, visit every surface above: open it, navigate it, switch narrators and come back. The Life Record revision must not move.
- **Network check.** For an ordinary operator editing biography, the only writes are `PATCH /api/life-record` plus narrator creation and consent. Any `PUT /api/bio-builder/questionnaire`, `/api/profiles`, `/api/interview/projection`, `/api/graph` or bio-editor write is **either a retained, named REVIEW mechanism from section B, or a defect.**

## C-2b — Bio Builder consolidation and authority cleanup — ACCEPTED / CLOSED 2026-09-24 (`be6b8b1`)

**Governing brief (Chris, 2026-09-24, after C-2 closed at `7d1e020`).** C-2b is
consolidation and authority cleanup: **no new store, no D-3 rewrite.** Every write to
the earlier biography system is either **held** or moved to the Life Record. The gate
is decided by **what an action writes, not by its verb** — "Approve" is held only
where it writes. Roadmap after it, unchanged: C-3 … C-7 → Batch D (D-0 authority and
consumer contract + Life Map → Memoir; D-1 historical context via
`timeline_context_events`; D-2 narrator-defined chapters as Life Record data; D-3 Lori
and Review; D-4 memoir; D-5 agreement gate) → Batch E (Portable Narrator) → Phase 6
fictional release candidate → Phase 7 real narrators.

**Target reached:** Bio Builder is `Questionnaire · Sources & Notes · Review · Family · ⋯ Legacy`,
with the header `<name> · Life Record revision N` read from the Life Record.

### What changed

| Area | Change | Where |
|---|---|---|
| Navigation | Five tabs. Review holds four sections: *From sources & notes* (candidates), *From Lori* (suggestions), *Source claims* (shadow review), *Conflicts*. Old tab names are aliases into the new area and section. `lifeThreads` routes to **Questionnaire**, never to the retired renderer | `bio-builder.js` `_TAB_ALIASES`, `_REVIEW_SECTIONS` |
| Retired from navigation | Life Threads, Reset Identity (the Bio Builder button), the shell's Operator Intake tab (hidden, not deleted), the top-level Earlier Answers tab (now under Legacy) | `hornelore1.0.html` |
| Status labels | Sources & Notes and Family: **DRAFT · NOT IN THE LIFE RECORD**. Review: **REVIEW**. Legacy: **READ ONLY · LEGACY**, with no controls | `_statusBanner` |
| Header | Prefers the Life Record: V2's `lorevox:life-record-shown` event `{pid, revision, name}`, else `GET /api/life-record/{pid}`. **No UUID fallback.** The event is cached per narrator and repaints only for the active one | `bio-builder.js` `_lifeRecordHeader`, listener; `questionnaire-v2.js` |
| Authority hold | New `life-record-authority.js`, loaded before every review surface. Guarded sites check it **immediately before the write call**; a missing module means **HELD** (fail closed). Held items stay pending — they are not counted committed, not removed from the queue | `life-record-authority.js` |
| Family / Life Threads | Their `_persistDrafts` is now `_persistGraphDraftsLocal`: FT/LT localStorage only. **Every** Family call site (Add, Edit, Delete, Connect, Seed ×4) goes through that alias, so none can carry the earlier-questionnaire PUT. Cut at the persistence seam, not at the buttons | `bio-builder-core.js`, `bio-builder-family-tree.js:39`, `bio-builder-life-threads.js:35` |
| Narrator switch | Three paths could create or refresh `lorevox_qq_draft_<pid>`: navigation persist (`_persistDrafts` with `navigationOnly`), the backend-restore mirror in `_restoreQuestionnaireFromBackend`, and app.js Phase G's snapshot mirror. **All three removed.** Existing drafts are left exactly as they are | `bio-builder-core.js`, `app.js` |
| `questionnaire_first` | Label "(retired)"; radio **disabled**; `lvSetSessionStyle` refuses it; a stored value hydrates as `oral_history`. Storage is not rewritten. The existing opt-in `lv_qf_live_ownership=1` still restores it for testing | `app.js` `_lvQfLegacyOptIn` |
| Old editor | `_openSection`, `_closeSection`, `_addRepeatEntry`, `_saveSection` no longer exported from `LorevoxBioBuilder` (caller audit: no normal runtime user) | `bio-builder.js` |
| Wording | "Questionnaire always wins", "approved truth", "structured biography", "Confirmed truth / safe to promote", "Promoted Truth", "graph is the truth model", "Canonical relationship graph" — all rewritten to say what the thing does | `conflict-console.js`, `bio-review.js`, `wo13-review.js`, `relationships.py`, graph comments, html help |

### Review actions — classified by what they write

| Action | Writes | C-2b |
|---|---|---|
| Suggestions → **Accept** / "Save this as my value" / acknowledge | server merges into the earlier questionnaire + `projection_json` | **HELD** — no Accept rendered (absent, with the reason), `_accept` refuses |
| Suggestions → Decline | review disposition | kept |
| Source claims → **Correct / Correct + Follow-up** with a field path | `projectValue(human_edit)` → projection + earlier questionnaire | **HELD**, claim stays open |
| Source claims → Correct on a candidate; Approve on a candidate | `LorevoxCandidateReview._promote` — **in memory** | kept (session staging, labelled so) |
| Source claims → Reject / Source only / status on a WO-13 row | review log; `PATCH` row status | kept |
| Conflicts → **Replace / Merge** | `projectValue` | **HELD**, conflict stays open |
| Conflicts → Keep current / follow-up / ambiguous | disagreement log | kept |
| WO-13 → **Promote approved** | `POST /api/family-truth/promote` | **HELD**, button disabled "(paused)" |
| WO-13 → status (approve, reject, …) | `PATCH` row status | kept — wording now "a decision only; nothing is promoted" |
| Candidates → Approve / Merge / Reject | `state.bioBuilder.review` — **memory only** | **not held**; relabelled "Mark approved", "Mark merge", "Staged in this browser session only — not saved, and not part of the Life Record" |

### Carried, not C-2b

- **Life Threads code is kept.** Named runtime dependency: `life-map.js:337` reads its
  theme counts. Reusable ideas for D-2 (narrator-defined chapters): themes as tags over
  Life Map periods; the thread ↔ era cross-reference; a narrator's own thread names as
  chapter candidates. It must not become a second narrative structure.
- **Identity onboarding in chat** (`app.js:6085-6307` → `lvBbSyncIdentity`) still writes
  the earlier questionnaire. Runtime, not an operator button → **D-3** (B5 above).
- **`lorevox_proj_draft_`** is still written on switch by projection sync → D-0 (B7).
- **Bug Panel Bio editor** remains a default-off alternate authority → D-0 (B4).
- **Readiness gate reads the legacy profile; real-narrator identity floor** → D-0.
- Bug Panel reset tools stay (developer), labelled "Earlier system only — the Life Record is NOT reset."

### Evidence

**Contract gate:** `tests/test_bb_consolidation.py` → `tests/bb_consolidation_harness.js`
(real `#bioBuilderPopover` markup + shipped scripts in page order, loaded as real
`<script>` elements; fake server recording every request; the legacy questionnaire
**has content**, the condition under which the old Family path PUT). **37 checks.**

*Found while building it — two harness defects that made checks pass vacuously:*
1. Scripts loaded with `window.eval` do **not** share top-level `const API` between
   files in jsdom, so every module that guards on `API` silently did nothing. Scripts
   now load as real `<script>` elements, and the harness refuses to run if `API` or
   `state` is not shared.
2. `render()` returns early unless the popover is open, and jsdom has no
   `:popover-open`, so `render()` never ran. The popover now carries the `open`
   attribute the page's own check accepts.

*Found BY it — three product defects, fixed in C-2b:* the backend-restore mirror and
app.js Phase G mirror were creating `lorevox_qq_draft_<pid>` on every switch; and the
header fell back to `_currentPersonName()` (the earlier profile's name), which is the
"find another name" patch the brief ruled out. It now says "Name not yet in the Life
Record" (or "Reading the Life Record…" while loading) and never an id or profile name.

**Mutations (each run against a copy of `ui/`; every one broke the check it should):**
authority opened · Family back on the old persist (the PUT reappeared on Add, Connect,
Seed, Delete) · navigation writing the old draft · the restore mirror put back ·
conflict guard removed · shadow guard removed · Accept button restored · conflict and
shadow guards made fail-OPEN when the module is missing · `questionnaire_first` radio
enabled and selection allowed · profile-name fallback put back in the header.
**One equivalent mutation, recorded honestly:** removing the pid check from the
`lorevox:life-record-shown` listener survives, because the header reads V2's own state
for the active narrator first and that overwrites any stale cache entry. The
stale-event check stays; it cannot discriminate that particular edit.

**Existing suites, sandbox (`PYTHONPYCACHEPREFIX=/tmp/pyc python3`, node 20):**
save_sequences, graph 52/52, operator intake 5/5 + helpers 16, questionnaire
save-outcome, cache authority, single questionnaire, persist-empty-guard 17,
questionnaire meta 12, operator intent 8, spouse edge types 26, profile cache and
seed authority 53; Python `test_bb_consolidation` + `test_qv2_shell` +
`test_qv2_adapter` + `test_questionnaire_route_fanout` + `test_operator_picker` +
`test_oral_history_default_integration`: **45 OK** — all pass.

**Laptop `.venv` (Chris, WSL, 2026-09-24):** the same six Python modules **45 OK, 0 skips**
(63.6 s); node: save sequences, graph 52/52, Operator Intake 5/5, persist-empty-guard 17,
questionnaire cache authority, single questionnaire — all pass. The `boom`, HTTP 500,
409 and narrator-switch lines in that output are exercised failure paths, not failures.
**Accepted on review (Chris + ChatGPT); C-3 next.**

**Browser sweep (Chrome, live stack, final code, Maren Holt (fictional)):** five tabs;
header "Maren Holt (fictional) · Life Record revision 2"; every area, every review
section and every old tab name opened; **the only non-GET request was the
stack-dashboard UI heartbeat**; no `lorevox_qq_draft_*` key; Promote disabled;
`questionnaire_first` radio disabled and the style `oral_history`; Life Record revision
2 before and 2 after.

## C-3 — people and relationships — ACCEPTED / CLOSED 2026-09-24 (`e387522` + `8a87738`, and the post-commit follow-up)

**Current totals — the ONLY current figures in this section.** Every other number below
is labelled with the moment it was measured.

| Gate | Value |
|---|---|
| `tests.test_qv2_people` (DOM checks + database checks) | **45** (37 at the first commit; +8 in the follow-up) |
| `tests/mutate_qv2_people.py` | **26 / 26 caught** (21 at the first commit; +5 in the follow-up) |
| Design validator | **20 rules · 14 situations · 22 refusals · 11 contracts**, COHERENT |
| `tests.test_intake_no_biography_seed` | **5** route tests (run under `.venv`; skip without fastapi) |
| Last full `.venv` run (historical — before the review repairs; not rerun) | 214 OK, 0 skips, 1 expected failure |
| **Final gate** — follow-up, laptop `.venv` (Chris, 2026-09-24) | `test_qv2_people`, `test_qv2_adapter`, `test_qv2_shell`, `test_bb_consolidation`, `test_intake_no_biography_seed`: **18 OK, 0 skips** (the 5 intake route tests ran); `mutate_qv2_people.py`: **26 of 26 caught** |
| `tests.test_bb_consolidation` | 41 checks |

**Boundary, as Chris set it (with ChatGPT's review of `16a68e1`):** Questionnaire V2
edits people and relationships against the existing writer. Family becomes a read-only
derived presentation. **No** migration of local Family drafts, **no** direct graph write,
**no** event/date schema change, **no** Remove, **no** reopening of a C-2b held path.
No migration was written; the stack was down throughout.

### What an operator can now do (Questionnaire → topics 1–4)

| | Stored as |
|---|---|
| Add a person, with their relationship to the narrator | `people/<id>` + `names/<id>` (`fullText` whole, `kind: current`) + `relationships/<id>` + a `relationship.kind` assertion carrying provenance — **one PATCH** |
| Relate someone already recorded (a grandmother who also raised the narrator) | a second relationship to the **same person id** |
| Roles | parent · sibling · grandparent · raised/cared for the narrator · spouse · partner · child · grandchild · chosen family · friend · mentor · someone the narrator cared for · other (description required). **None preselected.** Stored "subject is `kind` of other" in ONE direction (a child: narrator `parent_of` child) — no inverse row |
| Qualifiers | biological · adoptive · step · foster · half · in-law · twin · older · younger · former — `qualifiers[]`, none preselected |
| Side of the family | the catalog concept `relationship.qualifier.lineage_side`, as an **assertion** (the decision record calls it a qualifier of the relationship; the catalog gives it a concept, so it carries provenance) |
| What the narrator calls them · period (from / until) | `narratorLabel` · `period {start, end}`, each date **as said**: `1962` → year; `1962-05` → month; ISO day → day; anything else ("about 1989") keeps its text with `value: null, precision: "unknown"` — the identity.py convention. C-4 widens the parser |
| Life status | `person.life_status` — Living / Deceased / Not known, blank = no answer. A change supersedes |
| Names | edit in place (a `set` naming the name it replaces), add current / former / variant / also-known-as (former/variant default to `historical_only`), choose the preferred name |
| Pronouns · stated counts of siblings, children, grandchildren | `person.pronouns` (many) · `person.reported_count.*` as a **number**; "six" is refused on the form |
| Who a fact comes from | one selector per Save: entered by the operator (default) · the narrator told me (`narrator_stated`) · from a document. `recorded_by` is always the operator. **Not complete:** the operator cannot yet name a particular family member (or a particular document) as the person asserting a fact — recorded, not in C-3 |
| Change a saved relationship | qualifiers, label, description, period, side of the family, and the related person's names and living status — one `set` with the whole previous value as `expectedPrevious`. **A wrong relationship KIND (or the wrong person on it) cannot be corrected in C-3.** Correcting it means removing or replacing a persisted relationship, which is C-6's recoverable removal — not every relationship correction is available yet |

**Every id is minted before Save and kept in the narrator's draft** — people, names,
relationships, and the assertions that go with them (relationship kind, lineage side,
life status, answers). The writer does not use `baseRevision` as a lock for `add`, so
duplicate prevention rests on the ids: a network-ambiguous retry re-sends the same ids
and is refused whole ("already exists"). Pinned by re-sending the first Save verbatim.

**Family is rendered from the Life Record itself** (`GET /api/life-record` → the V2 read
model), **not from `/api/graph`.** That route returns projected rows (`lr:<id>`, kinds
`parent_of` …) mixed with old manual rows in the legacy vocabulary (`parent`, `guardian`,
`former_spouse` …, `bio-builder-graph.js`); reading it would need a projection-only
translation layer and would risk mixing the two. Family does not read, translate or
write the graph at all.

Unsaved additions are listed "unsaved" with **undo**; undoing a new person's only
relationship undoes the person, so nobody is left behind unrelated. A half-filled form
survives a repaint caused by another field (found by the harness: the first build lost
the operator's ticked qualifiers when a life-status change repainted the card).

**Family is DERIVED FROM THE LIFE RECORD** — grouped, read-only, "Edit in Questionnaire"
opens topic 2. The old Family Tree / Life Threads Add · Edit · Connect · Delete · Seed
handlers are **unexported** from `LorevoxBioBuilder`; their code stays
(`life-map.js:337` still reads Life Threads) and is reachable to tests through
`LorevoxBioBuilderModules`. **Existing `lorevox_ft_draft_*` drafts are kept, never
promoted into the record, never shown on Family** — the same anti-resurrection rule as
the old questionnaire drafts. An import/review of them would be a separate, explicit
decision.

### Server-side changes (small, and each pinned)

- **Real-narrator creation is identity + consent, not a biography seed.**
  `POST /api/people/intake` (`api_create_person_intake`) still carried the whole fan-out
  into `profile_json` and `bio_facts`, although the UI has sent identity + consent only
  since C-2. It now **refuses** family of origin, marriage, children, education/work,
  military (an explicit No included), faith and today for a real narrator — 422 naming
  the sections, nothing created — and points to the Questionnaire. Empty sections are not
  answers and do not refuse. **Kept, named:** `testing_only` narrators keep the old
  seeding, because 30+ Lori harnesses under `scripts/` build their fixtures through it and
  Lori does not read the Life Record until D-3 — retire it there. The identity mirror into
  `profile_json.personal` and the `people` row's DOB/POB also stay: they are the D-0
  duplicate-identity item, and Profile Seed readiness reads them. The real-narrator
  identity floor is untouched and still an open D-0 decision.
  `tests/test_intake_no_biography_seed.py` (route tests; **skip without fastapi** — they
  run under `.venv`; count in the totals table).
- **New model rule `rule_no_duplicate_relationship`** (`rules.py`): the writer accepted
  "P is `parent_of` N" twice. One pair + one kind + one description is one fact —
  unordered for symmetric kinds — **when the periods are EQUAL** (both absent, or the
  same span). One period absent and one known, or two different spans, are two
  relationships: "married Pat once, dates unknown; remarried Pat in 1992". *(Corrected
  in the supervisor review: the first version treated a missing period on either side
  as a duplicate, so that remarriage could not be stored. The browser's pre-check now
  uses the same equality.)*
  Writer tests through `apply_changes`; the design validator gained must-hold and
  must-refuse cases (a remarriage + grandmother-and-caregiver case must hold;
  a doubled parent and a friend stored both ways must be refused); validator mutation
  gate: 3 new mutations, all caught; writer mutation gate: all caught.
- **Known strictness, recorded not changed:** `rule_no_stored_inverse` refuses a second
  spouse edge stored in the *opposite* direction even with a different period. The
  editor always stores person → narrator, so it cannot reach this; a remarriage written
  the other way by another producer would be refused.
- **Graph projection:** a relationship period reached `graph_relationships.start_date`
  as JSON; it is now the text as said. Pinned in `test_life_record_graph`.

### Evidence at build (sandbox `python3` + node 20) — counts: see the totals table

- `tests.test_qv2_people` → `tests/qv2_people_harness.js`: DOM checks through the
  real forms, every request answered by the **shipped writer on real SQLite**, then the
  database checked in Python: 10 people (two named Erik Lund, two ids; a grandchild with
  no parent recorded between — one relationship, nothing inferred); Greta one id,
  two relationships; directions; qualifiers, label, period, lineage; provenance per
  Save; a life-status correction superseding; former and variant names whole
  (`given_parts` null); a count stored as `6`; graph re-projected (9 persons, one edge
  per relationship); **exactly two writes landed, the stale tab's 409 did not; every
  write in the run was `PATCH /api/life-record/…`** — no legacy questionnaire, graph,
  profile or `bio_facts` call. Also: a narrator switch with unsaved people pending writes
  nothing, shows none of them on narrator B, and switching back restores them with the
  same ids and the chosen provenance; a verbatim re-send of the first Save is refused
  whole; a refused relationship takes its new person with it (writer test).
- `tests/mutate_qv2_people.py`: all mutations caught (count in the totals table). The seven added after the
  review attack invariants, not wording: an assertion id minted at Save · an inverse row
  generated · the relationship left out of the PATCH · narrator A's draft landing on B
  (the first version of this mutation was inert — it edited a line the empty-draft early
  return never reached — and was rewritten) · a relationship edit without
  `expectedPrevious` · a full name split into parts · Save also PUTting the graph. The
  first eleven (UI duplicate check off ·
  ids re-minted at save · child direction ignored · relationship edit claiming the new
  value as previous · half-filled form forgotten · role preselected · undo leaving the
  person · count stored as text · provenance ignored · "about 1989" given a value ·
  names beyond the first hidden). The last **survived first** — no check read the
  narrator's names after a save — and a check was added.
- `tests.test_bb_consolidation`: **41 checks** — Family derived, no family editor
  controls, handlers unexported, an earlier FT draft neither shown nor sent and still
  kept, "Edit in Questionnaire" lands on topic 2, and the C-2b seam still local-only.
- C-2 contract intact: `tests.test_qv2_shell` passes unchanged. Writer, graph, identity,
  schema contract, adapter: 78 OK (3 route tests skip without fastapi under sandbox
  `python3`). JS preservation suites green (graph 52/52, save sequences, Operator
  Intake 5/5, persist-empty 17, cache authority, single questionnaire, spouse edges 26).

### Supervisor diff review — three defects, repaired (2026-09-24)

ChatGPT reviewed the product diff and found three defects none of the tests exposed:

1. **A stated zero passed the intake guard.** `_intake_biography_sections` tested
   numbers with `and v`, so `marriage.number_of_marriages = 0` counted as empty and a
   real narrator's intake carrying it would not be refused. A number is now an answer
   when present, zero included. Route test: 0 → 422 naming `marriage`, nobody created.
2. **Family had an A → B → A stale-response race.** `renderFamilyView` checked only that
   the narrator's box still existed — which it does again after A → B → A — so a slow
   first answer for A could paint over the second. Family now has its own generation
   guard on both success and failure. Deterministic harness check: requests held and
   released in the worst order; the older answer and a late failure are both refused.
3. **The duplicate rule contradicted its own remarriage design** when one period was
   unknown — above. Writer tests for both directions (unknown + dated both stand; the
   same dated span twice refused), a new must-hold validator case, a validator mutation
   restoring the old presence rule (caught), and a harness check that the browser
   refuses the same span and accepts the unknown-dates second marriage.

After the repairs (focused, sandbox `python3` + node): `test_qv2_people`,
`test_life_record_writer`, `test_intake_no_biography_seed`, `test_bb_consolidation`: all
OK; design validator COHERENT; validator mutation gate, writer mutation gate and every
C-3 mutation caught (3 new here: late Family answer, late Family failure, missing period
treated as a match). The live acceptance below stands: none of
the repairs changes the path it walked.

### Live acceptance — Chrome, live stack, Maren Holt (fictional), 2026-09-24

**Laptop `.venv` first (before the review repairs):** 214 tests OK, **0 skips**, 1 expected failure (the one C-2
carries); design validator COHERENT (13 situations at that time — 14 after the review); node suites all `exit=0` (save sequences, graph 52/52, Operator Intake 5/5,
persist-empty 17).

| Step | Result |
|---|---|
| Add through the real forms: parent (adoptive, maternal side, "Mor", deceased, from 1950), grandmother, **the same grandmother again as caregiver**, a paternal grandfather **Erik Holt** and a younger brother **also named Erik Holt**, a half-brother, a former spouse (1971 – "about 1989"), a child, a grandchild with no parent recorded between, a former name for the narrator; provenance "the narrator told me" | 18 pending edits; **no request** other than the stack UI heartbeat; draft written for this narrator |
| Switch to Nora Whitfield (fictional) with all of that unsaved, then back | Nora showed nothing of it, `dirty=0`, her record stayed revision 0 with no people; on return **all 18 edits, the same 8 person ids and the chosen provenance** came back. No write |
| Save | **exactly one `PATCH /api/life-record/<pid>` (39 operations)** — nothing else but the heartbeat; revision 2 → 3; **the 8 ids minted in the browser are the stored ids**; two people named Erik Holt, two ids; every relationship stored person → narrator except child and grandchild (narrator `parent_of` / `grandparent_of` them); "about 1989" kept as text with no value |
| Reload the page | draft gone (saved), header "Maren Holt (fictional) · Life Record revision 3"; the graph route shows 9 persons, **all 9 projected** (`lr:`), periods as text ("1971–about 1989") |
| Family | "DERIVED FROM THE LIFE RECORD", revision 3; parents, "Raised or cared for the narrator", siblings, grandparents (Greta on her mother's side, Erik on his father's), spouse, children, grandchildren — the two Eriks as two lines; **one control, "Edit in Questionnaire"**; opening it wrote nothing |
| Correct: "Edit in Questionnaire" → topic 2 → Astrid: name "Astrid M. Holt", adoptive → biological, "Mamma", living status Not known; provenance operator; Save | one PATCH: `set` name, `set` relationship, `add` assertion + supersede the old one — **every `set` carries `expectedPrevious`**; revision 3 → 4; **same person ids**; life status history `deceased (narrator_stated, superseded)` → `unknown (operator)`; Family now reads "Astrid M. Holt · biological · “Mamma” · Mother's side · from 1950 · Not known" |
| `POST /api/people/intake` for a **real** narrator carrying family, children and an explicit military No | **422** "biography is not seeded at creation", naming the three sections; people 3 → 3 |

Identity + consent creation of a real narrator was **not** exercised live on purpose (it
would leave a real narrator on the working root); `tests.test_intake_no_biography_seed`
covers it under `.venv`. **C-7 adds:** a normal operator cannot reach the `testing_only`
seeding exception (it is API-only, never sent by the UI).

### Post-commit follow-up — two transition defects (after `8a87738`) — ACCEPTED 2026-09-24

C-3 was committed and pushed (`e387522` implementation, `8a87738` docs) before the final
review finished. Those commits are the baseline and are **not** amended or rewritten; this
is one narrow corrective commit on top. C-3 is not reopened as a phase.

1. **Read-side `child_of`.** `child_of` is a valid stored kind the editor never writes
   (it writes `parent_of` from the parent's side), but records from before C-3 or from
   other producers can carry it. `detailedRole()` fell through to "other" for it. Now:
   narrator `child_of` P → P is **Parent**; P `child_of` narrator → P is **Child**. The
   editor still offers no second child direction. The browser's duplicate pre-check reads
   a stored `child_of` as the `parent_of` it would write, so re-adding that parent is
   caught on the form rather than refused at Save by `rule_no_stored_inverse`.
2. **Drafts from before C-3.** A C-2 draft has the same draft version but its answer edits
   carry no `newAssertionId`, and Save used to mint one — so a retried Save could send a
   different id. Now `upgradeDraftIds()` assigns any missing id **once, at hydration**, and
   **persists the upgraded draft immediately** (its own `baseRevision` and provenance kept;
   not discarded; version not bumped). Save never mints: a missing id stops the Save with a
   message and sends nothing.

Also: the `api_create_person_intake` header and docstring now describe the real behaviour —
identity + consent for a real narrator; the rich fan-out only as the `testing_only`
transitional exception through D-3.

**Accepted on supervisor review (Chris + ChatGPT), including the `child_of` duplicate pre-check. Verified under `.venv` (Chris, 2026-09-24): 18 OK, 0 skips; `test_qv2_people` 45 checks; all 26 C-3 mutations caught. The earlier full `.venv` (214 OK, 0 skips, 1 expected failure) and the live Chrome acceptance remain valid and were not rerun — the follow-up does not touch the path they walked. C-3 is CLOSED; C-4 is next.**

**Pinned (+8 checks, +5 mutations):** an old V1 answer draft with no `newAssertionId` is
upgraded and persisted before any Save, two Save builds use the same id, a reload keeps it,
the Save lands under it (checked in the database) and a verbatim retry is refused whole;
`child_of` read both ways by the model, on Family (Parents / Children) and in the editor,
where re-adding the parent is "already recorded". Mutations: `child_of` not read ·
`child_of` not normalised in the duplicate check · upgraded ids not persisted · draft not
upgraded · draft not upgraded **and** Save minting the id (the exact regression) — all
caught.

### Corrections recorded from the review of `16a68e1` (Chris + ChatGPT)

1. **`HANDOFF.md` heading and NOW block** said Batch B / C-1 while the table said C-2b
   closed — moved together in this edit; the C-2 row's "Do NOT start C-3" removed.
2. **`MASTER_WORK_ORDER_CHECKLIST.md`** had no row for this WO — row ★ added (order
   only; evidence stays here, current action in `HANDOFF.md`).
3. **The real-narrator identity floor stays OPEN** (D-0). A recommendation to allow an
   identity shell + consent is not a recorded decision.
4. **D consumes the WHOLE inventory B1–B17** above, not a short carried list.
5. **Migration numbers are not reserved.** This document called C-6's removal state
   "`0065`", but C-4 needs a migration first (`lr_events.type` has no `activity`; work,
   education and separation dates need schema and catalog work) and C-5 may need one
   (a story `concept_id`). **Each phase takes the next free number when its schema work
   lands.** Develop it only against disposable, freshly built scratch databases; once it
   has been applied to **any** persistent root it is immutable and a correction takes the
   next number. Stopping the stack prevents concurrent use; it does not make an applied
   migration editable. (Earlier mentions of "`0065`" in this document are historical.)
6. **Batch E does not add `graph_revisions` to portability — it is already there**
   (`narrator_data_inventory.py:332`, a derived portable lane; all 14 `lr_*` lanes are
   declared). E must prove closure and round-trip equivalence with a populated Life
   Record and graph revisions. The wipe script not clearing `graph_revisions` stays
   BACKLOG §11.
7. **C-7's network gate distinguishes biography authority from review disposition.**
   Decline, Reject, Source only, Keep and WO-13 status PATCHes are legitimate review
   writes; the prohibition is on establishing or changing biography outside
   `PATCH /api/life-record`.
8. **D-3 does not finish by flipping `legacyWritesHeld()` to false.** Each held action
   is rewritten to the Life Record, its old write branch removed, and only then does the
   transitional guard go. A global flip would reopen all four against the old stores.
9. **Life Threads code has a runtime consumer** (`life-map.js:337`); D-0/D-2 replace
   that dependency deliberately. It is not C-3 cleanup.

## C-4 — dates, places, events and periods (ACTIVE)

**Sequence (Chris, 2026-09-24):** C-4A date contract + fixtures → C-4B parser + server
validation → C-4C catalog / V2 reconciliation + missing date concepts → C-4D migration
(`activity` event type) → C-4E birth / death / places → C-4F homes and moves, unions and
separations → C-4G education / work / service / activity → focused mutation + live
acceptance and closeout. **One commit per accepted slice.** The catalog reconciliation and
the SQLite table rebuild are separate commits. Nothing from C-5 (stories, Life Today), C-6
(removal), D-1 (historical context) or D-3 (Lori) is pulled in. Stack down until a slice
needs the live check.

### C-4A — the date contract (DECIDED; recorded 2026-09-24)

A date keeps the shape `{text, value, precision}`:

| Field | Meaning |
|---|---|
| `text` | the wording as entered, after ordinary input trimming — never rewritten |
| `value` | a value from **Hornelore's bounded EDTF profile** (below), or `null` when the wording cannot be converted without inference |
| `precision` | calendar granularity only: **`day` · `month` · `year` · `unknown`** |

Approximation and uncertainty live in `value` — `~` approximate, `?` uncertain, `%` both —
and **new writes never emit `precision: "approximate"` or `"uncertain"`.** The profile is a
deliberate subset of EDTF Levels 0–1, not a claim of conformance.

**The shared fixture corpus is `tests/fixtures/life_record_dates_v1.json`** — 76 parse
cases (6 refusals, 23 text-only), 9 server-agreement cases and 4 legacy-compatibility
cases. The browser parser and the server parser/validator must both reproduce every case;
the corpus, not this prose, is the executable contract.

**Recognised (whole text must match; case-insensitive; internal whitespace collapsed for
matching only — `text` is stored as entered):**
- exact day, month, year: ISO (`1989-06-12`, `1989-06`, `1989`) and English month names
  (`June 12, 1989`, `12 June 1989`, `June 1989`, `Feb 3 1941`, `Sept. 1962`);
- approximate: `about / around / circa / c. / ca. / approximately X` → `X~`;
- uncertain: `probably / possibly / perhaps / maybe X`, or `X?` → `X?`;
- both: an approximate word **and** an uncertainty marker → `X%`;
- decades: `1920s`, `the 1920s`, `1920's` → `192X`;
- closed ranges with unqualified endpoints: `X–Y`, `X-Y` (two years), `X to Y`,
  `from X to Y`, `X through Y` → `X/Y`;
- explicitly ongoing: `X to present / now`, `X–present`, `X (ongoing)`, `X (still)` → `X/..`;
- explicitly unknown endpoint: `X to unknown` → `X/`, `unknown to Y` → `/Y`.

Qualifiers apply to the day, month or year they precede; `precision` is that granularity.
A closed range whose endpoints share a granularity takes it (`1980/1985` → `year`);
mixed-granularity, open and unknown-endpoint ranges are `unknown`.

**Text only (`value: null`, `precision: "unknown"`):** `early / late 1920s`; `before /
after X`; bare `from X`, `since X`, `until X`; `between X and Y`; seasons (`spring 1970`);
relative-event phrases (`after the war`); age-relative phrases (`when I was 12`); ranges with
a qualified endpoint (`about 1980 to 1985`); and anything else not matched as a whole.

**Refused (never silently downgraded to text):** a date-shaped value that is not a real
calendar date — `1989-13`, `1989-19-47`, `1989-02-30`, `1900-02-29`, `June 31, 1989` — and a
reversed range (`1985 to 1980`). Calendar validation is real (month lengths, Gregorian leap
years), not regex shape.

**Supervisor rulings (2026-09-24) — closed:**
1. **`1920s` → `{value: "192X", precision: "year"}`.** No `decade` value. EDTF defines
   `192X` as a year expression with an unspecified digit. **Precision is the granularity of
   the representation, not a claim that the value is exact**: a consumer that reads
   `precision: "year"` and ignores `X`, `?`, `~` or `%` in `value` is wrong — pinned by a test
   in C-4B.
2. **Slashed numeric dates are text only** — `12/06/1989`, `06/12/1989`, even `13/06/1989`.
   No locale inference; hyphenated ISO/EDTF forms are the machine-readable ones.
3. **Language-neutral numeric syntax normalises in any interface language** (`1989`,
   `1989-06`, `1989-06-12`, `1989?`, `1989~`); **English lexical phrases** normalise in C-4;
   **Spanish lexical phrases are text only** — a later Spanish profile is a bounded addition
   with its own fixtures.
4. **Server validation scope:** every CHANGED assertion whose catalog `value_type` is `date`
   or `date_interval` (derived from the catalog, not a hand list — this also covers e.g.
   `animal.birth.date`), plus changed `relationship.period` and changed name periods,
   validated structurally with the same date/interval validator. **`story.when` is NOT in
   C-4** (its shape is undefined; C-5 owns stories and can opt it in). Unchanged legacy dates
   pass through byte-for-byte.
5. **The V2 capability declaration is one executable JS constant whose literal is strict
   JSON, bounded by unmistakable marker comments** in `questionnaire-v2-model.js`. V2 uses
   that object at runtime; the catalog compiler extracts and JSON-parses the same literal. The
   parity test is **behavioural**: drive the V2 controls in the harness, capture the Life
   Record changes they build, translate structural fields (e.g. relationship periods) to their
   catalog concepts, and prove the writable set equals the declaration.

**Also approved:** round-century `…00s` text only; recognised years 1000–2999 (other
four-digit strings text only, not refused); bare `since X` text only; only explicit ongoing
wording (`to present`, `now`, `ongoing`, `still`) opens an interval.

**Authority.** The browser proposes; the server validates. For any date object a write
changes, the server parses its `text` with the same rules and requires the supplied `value`
and `precision` to equal the parse exactly — `{text: "1987", value: "1989"}` is refused even
though `1989` is valid EDTF, and unrecognised text must arrive with `value: null`,
`precision: "unknown"`. Empty text is refused.

**Compatibility (mandatory).** Stored dates from before C-4 — C-3's
`{value: null, precision: "unknown"}` periods, Batch B-era `precision: "approximate" /
"uncertain"` values, identity's `unknown` birth dates — are read as they are and **never
rewritten**: no background conversion, no startup normalisation, no data migration. A write
that carries one **unchanged** (re-sending a relationship with its old period while editing
its label) is accepted without re-validation; only a date the write actually changes is held
to the contract. This gets a permanent regression test in C-4B.

**Consumers that must learn the new values in C-4B** (found reading the code):
- `rules.age_at` treats a date as approximate only through
  `precision in {"approximate", "uncertain"}` and parses the value with
  `strip("~?")` + `int(...)` — it would treat `1989~` (precision `year`) as NOT
  approximate, and would crash on `192X`, `1989%` or an interval. It must read the
  qualifier from the value (and still honour the legacy precision values).
- `rules.rule_dates_keep_original_text` already fits (a year-precision value may not carry
  `-`; legacy approximate/uncertain precision still requires `~`/`?`).
- Graph projection reads `text` only; the V2 model passes values through; nothing else in
  the product reads Life Record date values yet (Batch D does).

**C-4D precondition — the migration runner (verified by reading `db/migrations_runner.py`).**
Its docstring says each file is applied inside its own transaction and that a failure leaves
`schema_migrations` without the row. The code calls `con.executescript(sql)` with no `BEGIN`
of its own — `executescript` commits any pending transaction and then does no implicit
transaction control — and only afterwards inserts the tracking row and commits. So: a
migration without its own `BEGIN … COMMIT` applies statement by statement (31 of the 63
migrations carry one; `0063` and `0064` do not), and a migration can commit its schema change
while the tracking insert fails, leaving it "unapplied" and retried against an already-changed
schema. **Before `0065` is written, C-4D first pins the runner's actual atomicity and
foreign-key behaviour in a focused test and, if needed, narrowly repairs it so the migration
body and its applied marker cannot leave an ambiguous half-landed migration.** No broad
redesign of the migration system. Then the `activity` table rebuild (which may need
`PRAGMA foreign_keys=OFF` before its own `BEGIN`, then `COMMIT`, re-enable and
`foreign_key_check`) is built on that proven behaviour.

**Death and places (for C-4E), as directed:** a death event requires the resulting person
to be deceased — if they are not already, the same Save adds the deceased assertion (and
supersedes a different live one); if they already are, no redundant assertion. Marking a
person deceased never creates a death event or date. Places: explicit **Choose existing
place** or **Create new place**; suggestions may show matching labels; nothing is merged or
identified from a string, and the Save knows which was chosen.

### C-4B — ACCEPTED 2026-09-24: one parser in each runtime, and a writer that holds changed dates

**Built and accepted:**

| Where | What |
|---|---|
| `server/code/api/services/life_record/dates.py` (new) | `parse(text)` → value / text-only / refuse; `check(obj, allow_interval)` — the writer's agreement test; `qualifiers(obj)` and `calendar_parts(value)` for consumers, honouring the legacy precision words |
| `ui/js/questionnaire-v2-model.js` | `parseDateText` replaced by the full parser (returns `{text, refuse}` for a date-shaped non-date); `dateQualifiers` exported |
| `ui/js/questionnaire-v2.js` | `periodOf(form, prior)` returns `{error}` for a refused end or a range typed into one end; both callers show it on the form and add nothing. **On an existing relationship an end whose text is unchanged is carried as the stored object byte-for-byte** and is not re-validated (the writer's rule, mirrored); only a changed end is parsed |
| `writer.py` | every **added** assertion whose **catalog `value_type`** is `date` / `date_interval` is checked (`allow_interval` from the type — the name of the concept decides nothing); relationship and name periods: **only an endpoint the write changes** is checked, so an unchanged legacy endpoint passes byte-for-byte |
| `identity.py` | parses by the contract; a refused birth date is **not written and not downgraded** — creation succeeds and reports `notRecorded`; a refused date alone creates no birth event |
| `routers/people.py` | `_legacy_birth_date`: a refused or range birth date reaches the **legacy `people` row as `""`** (the legacy `_sanitise_dob` checks shape only and kept `1939-02-30`); the original input still goes to `establish_narrator`, whose `notRecorded` the response carries. Applied to `POST /api/people` and to `POST /api/people/intake` (people row and its `personal.dateOfBirth` profile mirror). `_sanitise_dob` is not changed |
| `rules.py` | `age_at` reads qualifiers from the value and the legacy words, and returns `None` for a decade or a range (no calendar point). **`resolve_life_span` is unchanged** — a `qualifiers` field was added and then removed on review: certainty has one representation, the date's value, and callers read it with `dates.qualifiers(span["start"])` |

**Ruling 4 as built:** not `story.when` (C-5). Assertions are never edited, so every date
assertion a write adds is a changed date; periods compare against the stored value.

**Tests changed to the contract (they wrote legacy vocabulary through the writer):**
`test_life_record_writer` (Dates), `test_life_record_graph`, `test_life_record_identity`,
`test_qv2_adapter` (and its relationship periods were bare strings), `test_qv2_people`
(`about 1989` is now `1989~`/`year`). **Legacy shapes are now put in by SQL** and pinned as
readable and carried: `test_qv2_adapter.test_a_legacy_date_is_read_as_stored_never_rewritten`,
`test_life_record_writer` legacy DOB tests, and in `test_life_record_dates` every
`legacy_compatibility` corpus case through an unrelated **relationship** edit and an unrelated
**name** edit, plus the mixed case for each owner (one end changed and held to the contract, the
legacy end untouched; changing the legacy end itself is then checked).

**New:** `tests/test_life_record_dates.py` (both parsers against the whole corpus, browser ==
server per case, text never rewritten, every `server_agreement` case through the real writer,
catalog-derived typing, period endpoints, legacy carry for both owners, age consumers, identity,
and route tests: a bad DOB is `ok` + `notRecorded` with name, pronouns and place kept and
`people.date_of_birth == ""`; a failed Life Record write is `ok: false` + `refused` and never
`notRecorded`; the intake route keeps the bad DOB out of the row and the profile mirror);
`tests/mutate_life_record_dates.py` (**27** mutations over `dates.py`, the JS parser, `writer.py`,
`rules.py`, `identity.py` and `routers/people.py`, run through `tests/mutation_runner.py` —
restore after every mutation, verified byte-identical at exit; the four route mutations need
fastapi, so only `.venv` can catch them); **four** C-4B mutations in `tests/mutate_qv2_people.py`
(three replacing the C-3 one `about 1989` no longer discriminates, and
`legacy-period-reparsed-on-unrelated-edit`); five harness checks (impossible date and range in
one end refused on the form; an unrelated edit carries both legacy ends; the Save sends them with
the stored `expectedPrevious`; changing one end parses only that end); one design-validator
contract extension and one mutation (approximation read from precision only).

**Review history (not acceptance evidence).** First `.venv` run on the pre-review tree: 117 OK,
0 skips, 19/19 date mutations. ChatGPT's pre-commit patch review then found two defects, both
repaired: the bad DOB still stored in the legacy `people` row, and the editor re-parsing an
unchanged legacy period end during an unrelated edit. Sandbox runs after the repairs (121 run,
13 route skips — no fastapi) were orientation only.

**Acceptance evidence — `.venv`, Chris, 2026-09-24, on the repaired tree:**
- 11-suite bank: **125 tests OK, 0 skips.** The two bridge-sync tracebacks are the deliberate
  injected failures in `test_c2_bridge_order_swap`; the suite ended OK.
- Date mutation gate (`tests/mutate_life_record_dates.py`): **27/27 caught**, including the four
  route-level DOB mutations.
- Targeted C-4B people mutations (`tests/mutate_qv2_people.py`): **4/4 caught**, including
  `legacy-period-reparsed-on-unrelated-edit`.
- Design validator: 20 rules · 14 situations · 22 refusals · 11 contracts — **DESIGN COHERENT**.
- Design mutation gate: **every mutation caught**.
- Final pre-commit patch: **20 diffs**, `git diff --check` clean.

**C-4B — ACCEPTED 2026-09-24** (ChatGPT review of the repaired 20-file patch; the
`/api/people/intake` DOB repair is kept). Ready to commit. Next: **C-4C**.

## Roadmap refinements (Chris + ChatGPT, 2026-09-24, after the research review)

Recorded here so each lands in the right phase; **none is current work.** Governing rule
unchanged: current phase first; anything that does not close the current requirement goes
to BACKLOG unless it is a genuine blocker. Sequence: C-2 ✅ → C-2b ✅ → C-3 (post-commit
repair, then ✅) → C-4 → C-5 → C-6 → C-7 → D-0 → D-1 → D-2 → D-3 → D-4 → D-5 → E →
Phase 6 → Phase 7.

| Phase | Refinement |
|---|---|
| **C-4** | **Opens with the date-value decision.** Keep `{text, value, precision}`: `text` exactly as supplied; `value` a **bounded EDTF** expression only where the text maps to it unambiguously; `precision` retained/validated. "1989" → `1989`; "about 1989" → `1989~`; "1920s" → `192X`; "before the war" → text only, `value` null. No invented precision; not the whole ISO standard. C-4 also owns the schema gaps already found (work / education / separation date concepts; the missing `activity` event type) and takes **the next unused migration number**. |
| **Migrations** | No number is reserved (C-6 is no longer "0065"). A phase that needs schema work takes the next unused number when that work lands; developed on disposable scratch databases; once applied to any persistent dev DB it is immutable, and a correction takes the following number. |
| **C-7** | No normal operator action may establish or alter canonical biography outside the Life Record writer. **Decline, Reject, Source only, Keep current and other non-biographical review-state decisions may remain.** Also verify a normal operator cannot reach the `testing_only` intake exception. |
| **D-0** | Decides the **final real-narrator identity/readiness floor.** The Life Record supports unknown and partial biography, but Profile Seed/readiness still depend on DOB / residence / pronoun / profile mirrors. Do not silently make those legacy requirements permanent, and do not prematurely declare them eliminated. (Expectation, not a decision: identity + consent should be enough to create a narrator.) |
| **D-1 / D-2** | Historical-event similarity may surface an **operator-reviewed suggestion** for an undated story. It never writes a date, era, Life Map placement or chapter. |
| **D-3** | Source checklist is the **whole B1–B17 inventory**. Each held action is rebuilt onto the Life Record and its old branch removed; the authority guard is never turned off globally. **Lori never asserts an unconfirmed fact inside a question that solicits agreement** — solved first through Life Record status, prompt construction and Lori's question policy; a post-generation guard only if measurement shows failures remain. |
| **D-4 / D-5** | **Claim-level traceability:** every factual biographical claim and purported scene detail in a memoir traces to a Life Record assertion, a narrator-captured story, or clearly identified operator-authored interpretation. Connective prose may exist; it may not invent biography or pass itself off as the narrator's recollection. |
| **Doctrine (proposed for `CLAUDE.md` design principles, on Chris's confirmation)** | Lorevox does not generate synthetic visual depictions purporting to show a narrator's memories. Authentic family photos and media remain supported. |
| **Batch E** | Not lane design: `narrator_data_inventory.py` already declares the 14 `lr_*` lanes and `graph_revisions` (derived, portable/erasable). E = populate the Life Record + graph revisions → export → validate → isolated restore → re-export → prove semantic and reference equivalence. The wipe script's `graph_revisions` omission stays BACKLOG §11 unless it blocks E. |
| **Phase 6** | Two new gates before any real narrator: **STT** — measure the configuration we intend to ship on controlled fictional recordings, both ordinary WER and a critical-fact error rate (names, dates, locations, numbers, relationships, negation); **memoir** — traceability and representational-bias evaluation on difficult fictional biographies. |
| **Phase 7** | Unchanged: no real-narrator testing because one subsystem looks ready. |

## 6. Explicit statement

*(Corrected 2026-09-23 at B3 start. This section was written for the Repair A
checkpoint and was not updated as the same living document took in Batches A1–A3
and B0–B2. Its original claims — "Product code touched: only
`ui/js/bio-builder-graph.js`… Nothing under `server/`" and an open request for the
Repair A graph diff — were true when written and are wrong now. Read the per-batch
sections above for what each batch touched.)*

**Through Repair A / Batch R:** no live data was changed by Claude (every sandbox
database access was `mode=ro`; the §0A deletions were run by Chris through the
product's route), and no life-record product-code migration was begun. Product
code touched then: `ui/js/bio-builder-graph.js` and its test only. The Repair A
graph-diff request is **closed** — Repair A landed and was reviewed (§5A).

**Since then, server product code HAS changed**, each under an authorized batch:
A1/A5 (concept catalog + migration plan, `server/code/api/services/`), A2
(`suggestion_review.py`), A3 and the B2 repairs (`server/code/api/routers/extract.py`:
vocabulary, redirects, retirements, the date-uncertainty guard, the D1c revert).
Commits through `7bc681b` are Chris's; agents ran read-only git only (`log`,
`status`, `show`, with `--no-optional-locks` after one stray lock on 2026-09-23,
removed by Chris).
