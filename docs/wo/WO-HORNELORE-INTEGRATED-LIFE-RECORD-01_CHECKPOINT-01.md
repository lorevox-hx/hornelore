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
+ 1 diag probe) · direct parse 96 · **salvaged 19** (18 at `max_new=384`, raw 1,100–1,503 chars;
1 at `max_new=128`, the negated-military empty-value list) · rules fallback 13 · not-in-vocab rejects
**143** · turnscope drops 45 · kinship quarantines 36 · subject-filter strips 2. Two of the salvages
also carried a `# comment` inside the JSON, which fails parse independently of length.

**Measurement series, agreed 2026-09-23 (Chris + reviewer):**
- **B0** = this run (bounded, compound cap 384).
- **B1** = B0 with **only** `MAX_NEW_TOKENS_EXTRACT_COMPOUND=768` — no code change. Compare direct-parse,
  salvage count, rules fallback, recall, rejects, wrong-subject drops, generated tokens, latency, and
  whether output grows *more verbose* rather than more correct.
- **B2** = A2/A3 (after the case-bank migration and B0 re-score).
- **B3** = A4 relevance-scoped catalog. 768 fixes output capacity; A4 fixes input choice. Each is
  measured on its own.

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

## 6. Explicit statement

During this checkpoint: **no live data was changed by Claude** (every
database access from the sandbox was `mode=ro`; the §0A deletions were run by
Chris through the product's route); **no git command was executed** (HEAD was
read from `.git/HEAD` and the ref file; no lock was taken); **no life-record
product-code migration was begun**. Product code touched: **only**
`ui/js/bio-builder-graph.js` and its test, under the authorized Batch R.
Nothing under `server/`.

One outstanding request to Chris: the read-only `git diff` into
`.runtime/repairA-graph.diff`, so §4 can be closed on the bytes rather than
on the author's memory.
