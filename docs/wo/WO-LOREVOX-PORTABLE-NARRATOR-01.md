# WO-LOREVOX-PORTABLE-NARRATOR-01

**Portable Narrator Package, Restore, and Clean Lorevox Cutover**

**Opened:** 2026-09-09
**Status (2026-09-11):** **Phases 0–4 LANDED** (§31 · §32 · §33 + §33.1 · §34);
**Phase 5 (operator jobs + UI, §16.1) is CURRENT.** Deletion remains outside this WO:
Phase 7 is a clean-root cutover and `/mnt/c/hornelore_data` remains preserved (§25). *(This line read "APPROVED IN ARCHITECTURE 2026-09-09 —
implementation begins with Phase 0 only" until 2026-09-11; that was true for two days and
then became a standing instruction to redo finished work.)*
**Repository reviewed:** `lorevox-hx/hornelore` · `main` ·
`7d5d040cf8060e9501a6053c77978047dc6b41f9`
**Drafted** from the 2026-09-09 review (ChatGPT draft, Claude repo-grounded amendments
in §27, Chris's decisions in §25). Authority order is unchanged: current code > current
tests and live evidence > accepted closeout records > `HANDOFF.md` > this file.

---

## Mission alignment

Lorevox is the memory system and Lori is the conversational interface to it. A
narrator's life story must therefore belong to the narrator rather than to one laptop,
one SQLite database, one Hornelore installation, or one filesystem path.

This work order makes a narrator portable as a complete, auditable package while
preserving original source evidence, structured memory, review state, photographs,
documents, travel records, transcripts, narrator audio, and provenance.

Hornelore remains the Horne-family R&D history. Lorevox becomes the clean product into
which a narrator can be restored.

## Non-regression requirements

This WO MUST NOT:

* reduce narrator dignity;
* introduce new `must_not_write` violations or system-tone narrator outputs;
* regress the current Lori conversational baseline;
* modify the model or the locked 8,192-token context window;
* change the extraction algorithm or attempt to fix the current extraction-prompt
  overflow;
* change story-capture thresholds, meaning rules, review semantics, or memoir
  eligibility;
* expand operator controls into narrator-facing UI;
* add a second narrator-identity authority;
* silently infer ownership for unattributable historical data;
* silently omit a narrator-owned lane because it is inconvenient to export;
* copy credentials, OAuth tokens, API keys, cookies, `.env` contents, Guard Lab
  configuration, or installation secrets into a narrator package;
* combine Export with Delete;
* delete `/mnt/c/hornelore_data` as part of the Lorevox cutover;
* rename the GitHub repository, local repository path, or every `HORNELORE_*`
  compatibility symbol as part of portability.

The existing interview, story-capture, extraction, memoir, photo, travel and archive
behavior remains unchanged except for the new operator import/export capability.

---

## 1. Why this work order exists

The existing button called **Archive Export** is not a narrator export.

`server/code/api/routers/memory_archive.py:634` exports only
`DATA_DIR/memory/archive/people/<person_id>` — the durable two-sided transcript archive
and narrator-only audio — by recursively zipping that directory into an in-memory
`BytesIO` and nothing else.

It does not export the complete narrator. The present archive is not a restore package
for: the `people` row; profile state; projection state; Bio Facts; Family Truth and
provenance; timeline / Life Map state; story candidates and operator review state;
extraction ledger / results; photographs and photo metadata; personal media / document
archive; travel documents; trips, regions, stops and days; trip photo placement; trip
narration links; import provenance / staging; onboarding state; consent / history
state; legacy narrator material that the erasure system still recognizes.

There is also no inverse operation that accepts one of these archive ZIPs and recreates
the narrator.

**Archive Export and Narrator Export are different product concepts.** The current
Memory Archive remains useful and is not removed by this WO.

## 2. Repo findings that govern the design

### 2.1 Erasure currently knows more than export

`server/code/api/services/narrator_erasure.py` already recognizes narrator filesystem
targets (`FIXED_TARGETS`, line 101): `memory/archive/people/<pid>`;
`stories-captured/<pid>`; `memory/archive/photos/<pid>`; historical `kawa/people/<pid>`;
`media/archive/people/<pid>`; `media/<pid>`; plus dynamic lanes for trip-source
directories, import staging and legacy transcript / export locations. It recognizes
shared disposable stores (`SHARED_PURGE`) and historical stores separately. That
distinction is preserved.

### 2.2 Database ownership is currently distributed

`server/code/api/db.py` contains both ordinary FK-cascaded narrator state and an
`_EXTENDED_PERSON_SCOPED_TABLES` list (`db.py:5603`) for tables the `people` FK cannot
reach, consumed by `person_delete_inventory()` (`db.py:5716`). The code itself documents
that narrator-owned tables have previously been missed by deletion inventory.

**This WO MUST NOT create yet another independent hand-maintained export list.**

### 2.3 Travel is a complete domain, not one table

Travel state spans migrations `0015` through `0043`. A complete narrator package must
preserve the trip root and all narrator-owned descendants, including as applicable:
trips; regions; stops; themes; location / story notes; Bio suggestions; story links;
source documents; trip days; day links; photo links; multi-day photo placements;
placement skips; trip / turn links; live / shelf placement state; public / context
state and review state. Trip-source files under `DATA_DIR/trip_sources/...` are part of
the same domain.

### 2.4 Existing import infrastructure is not the narrator importer

`server/code/api/services/import_repository.py` is an intake / provenance system for
external photo material (`0037_import_provenance_foundation`). Its principles are
reused — person boundaries enforced, cross-person writes refused, intake is not
approval, raw credentials refused, staged bytes verified, hashes authoritative, state
transitions deliberate — but `import_batch` / `import_candidate` MUST NOT be repurposed
into a whole-narrator restore mechanism. Narrator restore has different atomicity and
identity requirements.

### 2.5 The current archive implementation will not scale

`memory_archive.py` builds the ZIP in `io.BytesIO`. Reasonable for transcript / audio;
not for a complete narrator with a large photo / document collection. Narrator package
export uses a temporary-file or streaming implementation with explicit size accounting.

## 3. Locked portability principle

```text
LOREVOX APPLICATION
        ├── Narrator A  └── portable narrator package
        ├── Narrator B  └── portable narrator package
        └── Narrator C  └── portable narrator package
```

A narrator is data. Lorevox is the application. A specific installation is merely one
place that narrator data can live.

## 4. One narrator-ownership contract

### 4.1 Required architectural change

Create one small server-side narrator ownership inventory — suggested
`server/code/api/services/narrator_data_inventory.py`. A declaration layer, not a plugin
framework. Each lane records enough to answer: how ownership by narrator X is proven;
which child rows follow an owned parent; which filesystem paths belong to those rows;
whether the lane is portable; whether it is erasable; whether it is authoritative,
derived, historical, cache, or installation-owned; which ids / references must survive
Restore; which path fields must be rewritten relative to the destination `DATA_DIR`.

### 4.2 Inventory discovery sources

Phase 1 MUST reconcile the ownership contract against all four current authorities:
**A** the live schema and FK graph via SQLite metadata; **B** `person_delete_inventory()`
and `_EXTENDED_PERSON_SCOPED_TABLES`; **C** the schema created by migrations `0001`
through current HEAD; **D** `narrator_erasure.build_plan()`, including dynamic paths.
Any narrator-owned lane found by one authority but absent from the portability
inventory is a failure.

### 4.3 No inference from column names alone

A column named `person_id` does not automatically make a table narrator-owned; lack of a
direct `person_id` does not make a child table global. Ownership is explicit and follows
real domain relationships.

## 5. Ownership classes

Every durable lane is assigned exactly one class.

**Classes describe what KIND of data a lane holds, never WHOSE.** `testing_only`,
`narrator_type` and `is_deleted` are narrator dispositions on the `people` row and are
orthogonal to these classes (decided 2026-09-10, Phase 0 R5). A `testing_only` narrator is
exportable — Phases 2–4 round-trip on a synthetic narrator depends on it — and a
soft-deleted narrator still owns its rows and directories (§14). Which narrators are
*selected* for export is an operator decision at export time. There is no "test-fixture"
class.

**A — Narrator authoritative.** Original information or operator / narrator decisions
that must survive: identity; transcripts; narrator audio; photographs / original
documents; operator corrections; review decisions; trip source documents.

**B — Narrator derived, but portable.** Derived state whose loss would alter what the
installation knows or what work has been completed: profile / projection state; Bio
Facts; Family Truth; timeline events; story candidates; extraction results; section
summaries; memoir placement / review state. Included even if a future Lorevox could
regenerate some of them.

**C — Narrator historical / legacy.** Retired product data that still belongs to the
narrator, e.g. `DATA_DIR/kawa/people/<pid>`. Kawa is NOT restored as a feature; its
historical data is preserved so portability does not become an accidental deletion
mechanism.

**D — Re-generable cache.** Translation cache; temporary thumbnails where a verified
original exists and regeneration is guaranteed. A cache may be excluded only by an
explicit ownership declaration.

**E — Installation-owned. MUST NOT travel.** Guard Lab overrides (`0053`); schema
migration state as active target configuration; global `bio_fields` schema; global
curated timeline-context library; operator / application credentials; application
configuration; environment variables; API keys and tokens; logs not scoped exclusively
to this narrator; narrator deletion audit history. The manifest may RECORD source
schema / commit for compatibility but does not restore installation state.

## 6. Shared and unassigned material

Narrator-owned and family-shared are not automatically the same thing. Phase 1 produces
a separate report: `narrator-owned` · `shared/family-owned` · `unassigned` ·
`installation-owned` · `historical backup/export`. For the cutover: narrator-owned data
goes in narrator packages; shared / unassigned family material remains preserved in the
frozen Hornelore data root; any material required in clean Lorevox receives an explicit
disposition; if significant shared-family data exists, a companion shared-library
package is proposed as an amendment rather than silently added to V1. **No data is
discarded while that decision is pending.**

**Orphan material — locked 2026-09-10 (Phase 0 R6 found 185 such directories).** A file or
directory whose owner cannot be read from a row or a declared path rule is handled by
exactly one of three branches, and proximity to a narrator's files is never one of them:

1. ownership proven for a narrator → packaged with that narrator;
2. a database row still references it → the relationship is preserved and reported, and
   Phase 1 determines why the owner is unresolved before anything moves;
3. ownership cannot be proven → it stays in the frozen Hornelore root and is reported as
   orphan / unattributed.

An orphan is never placed in a package because it happens to sit beside that narrator's
data.

## 7. Lorevox Narrator Package v1

### 7.1 File format

`<Narrator_Display_Name>_<package-id>.lorevox.zip`. An ordinary ZIP so recovery does not
depend on proprietary software.

### 7.2 Top-level structure

**SUPERSEDED by §28.1 (BagIt), which is what the exporter builds.** Kept as the original
design so the amendment reads against something; do not implement from this diagram.

```text
manifest.json
checksums.json
records/
    people.jsonl
    profiles.jsonl
    interview_projections.jsonl
    ...  one file for each included narrator-owned table/domain
files/
    memory/archive/people/<pid>/...
    memory/archive/photos/<pid>/...
    media/archive/people/<pid>/...
    media/<pid>/...
    stories-captured/<pid>/...
    trip_sources/<source-id>/...
    import_staging/<batch-id>/...
    kawa/people/<pid>/...
    ...  other narrator-owned DATA_DIR-relative paths
```

**The exact list of `records/` files is derived from the accepted ownership inventory,
not frozen into this diagram.**

### 7.3 Manifest

*(The file is `lorevox-manifest.json`, a BagIt tag file — §28.1; the field list below is
current and the implementation adds `path_column_basis`, `ownership_declaration`,
`lanes_absent_in_source`, `installation_dependencies`, `residue_not_packaged`,
`payload_integrity`, `verified_source_digests_checked` — §32, §33.)*

`manifest.json` includes at minimum: `package_format`, `package_format_version`,
`package_id`, `created_at`, `narrator_id`, `narrator_display_name`, `package_kind`,
`source_app`, `source_commit`, `source_schema_migrations`, `source_schema_fingerprint`,
`path_basis` (always `DATA_DIR-relative`), `record_counts_by_lane`,
`file_counts_by_lane`, `bytes_by_lane`, `external_person_dependencies`, `warnings`.
No source-machine absolute path becomes an active restored path.

### 7.4 Integrity

Every payload file receives SHA-256 integrity information. The package refuses
completion if a listed file could not be read; the final hash differs from the hash
measured during collection; a narrator-owned DB lane could not be queried; a known
filesystem target could not be inspected; or the narrator changed during construction.
**No "best effort" narrator package is labeled complete.**

## 8. Export contract

**8.1 Export is read-only.** No approvals, promotions, profile changes, review marks,
trip changes, transcript edits or deletions.
**8.2 Export may contain empty lanes.** A narrator with a profile and photographs but no
Memory Archive sessions is still exportable; the new exporter MUST NOT inherit the
current behavior where an absent archive directory means "no narrator export".
**8.3 Consistent snapshot.** Narrator-owned state is measured before and after
collection; if it changed, `EXPORT REFUSED — narrator changed during snapshot` and the
incomplete package is discarded. This avoids a product-wide export lock.
**8.4 Large packages.** Temporary-file / streaming, never `BytesIO`.
**8.5 Path normalization.** Known DB path columns are normalized to `DATA_DIR`-relative
form and rewritten to the destination root on Restore.
**8.6 Secrets.** Reuse the import-provenance secret-detection principles: refuse or
strip OAuth tokens, Authorization headers, signed credential query parameters, API keys,
cookies, `.env` content. Ordinary source URLs and narrator-authored text are not
censored.

## 9. Audio and transcript policy

Existing archive policy remains authoritative. The package includes narrator text, Lori
text, narrator audio when the narrator opted to save it, and audio metadata /
provenance. The transcript remains the primary recoverable evidence even when audio is
unavailable.

*(Amended 2026-09-10, before Phase 1 closed. This paragraph said the package "does NOT
include … video". That collapsed two different things: a live camera stream that is never
written, and a recording a narrator chose to keep. Only the first is excluded.)*

**The rule is about intent to keep, not about medium:**

| | travels |
|---|---|
| Narrator text · Lori text | yes |
| Narrator audio the narrator chose to save | yes |
| Narrator video the narrator chose to save — **if/when the product persists it** | yes |
| Audio / video metadata and provenance · session / turn / story links | yes |
| Lori-generated audio or video | no |
| Live microphone buffer · live camera / browser stream · unsaved temporary recording | no |

**Where saved audio actually lives today (`verified_by_read`):** the file is written by
`routers/memory_archive.py:553-563` to `utils/archive_paths.py:107` →
`memory/archive/people/<pid>/sessions/<conv>/audio/<turn>.webm`, which is inside the
person-keyed `memory_archive` FS lane; its metadata is `memory_archive_turns.audio_ref`
(`0002:51`), narrator-only by `CHECK` (`0002:57-60`); a best-effort copy sits under
`stories-captured/…/audio.webm` (`story_preservation.py:414-419`), the `stories_captured`
lane. Both lanes are declared portable and erasable in `narrator_data_inventory.py`. **So
saved audio was never outside the contract — it is carried by the lane it is stored in,
and needs no lane of its own.**

**Video today:** `memory_archive_sessions.video_enabled` exists (`0002:24`) and is
carried as a column; no code path writes a video file (`memory_archive.py:12` "Video
uploads are not part of this WO"; `stack_monitor.py:753` reports `video_archive:
disabled`; the Google Picker refuses VIDEO at `google_picker.py:827`). **When video
persistence is added, its files must be written under the same session archive directory
(`…/sessions/<conv>/video/<turn>.<ext>`) with a `video_ref` column beside `audio_ref`,
so it inherits the `memory_archive` lane's portability and erasure without a new lane.**
Writing it anywhere else is a Phase 1 parity failure by design: the completeness test
fails on an undeclared table, and a new top-level directory under `DATA_DIR` must be
declared as an FS lane before the exporter will collect it.

## 10. Restore v1

**10.1 Restore preserves identity.** V1 has one import meaning: *restore this narrator
as this narrator.* Narrator id, session ids, turn ids, story candidate ids, photo ids,
trip ids, source ids, extraction keys, provenance references and every other internal
id are preserved. This protects joinability and provenance.
**10.2 Collision policy.** If the target already contains the narrator id or any
package-owned id that would be overwritten: `RESTORE REFUSED — collision`. V1 does not
overwrite, merge, guess, remap, clone, or "use existing" silently.
**10.3 Why remapping is deferred.** A UUID-remapping importer must rewrite every foreign
key, embedded JSON reference, provenance pointer, turn key and filesystem reference
correctly. Unnecessary for the Hornelore→Lorevox goal. Merge / Clone / Remap is a later
WO.
**10.4 Dry run is mandatory** and writes nothing: narrator, package version, source
version, creation date, records and files by domain, total bytes, destination
collisions, unsupported schema items, missing dependencies, credential warnings, unsafe
paths, checksum status → `RESTORE READY` / `RESTORE REFUSED`.

## 11. Restore security

The package is untrusted input even when Chris created it. Refuse: absolute archive
paths; `..` traversal; filesystem-root paths; symlinks; links escaping the target root;
duplicate ZIP entries mapping to one destination; files not declared by the manifest;
missing declared files; checksum mismatches; unsupported package format; unsafe
decompression / size expansion; overwrite of any pre-existing destination. The
narrator-erasure path-safety rules (`safe_target`, component-by-component `lstat`) are
the model.

## 12. Restore atomicity and crash recovery

```text
 1. Receive package into temporary staging
 2. Validate structure
 3. Validate manifest
 4. Validate hashes
 5. Validate schema compatibility
 6. Run dry-run ownership/collision checks
 7. Create durable restore job
 8. Copy package files to final DATA_DIR-relative locations, no-overwrite
 9. Re-hash copied files
10. BEGIN one SQLite transaction
11. Insert narrator and narrator-owned DB records in dependency order
12. Verify row counts / required references
13. COMMIT
14. Mark restore job complete
15. Remove temporary staging
```

**Files first, database visibility last.** A crash before commit may leave staged /
orphan files but cannot expose a half-imported narrator. If insertion fails, rows roll
back and files created by that job are removed. Suggested migration
`0054_narrator_package_jobs.sql` with states `staged` · `validated` · `files_copied` ·
`db_committed` · `complete` · `failed` · `cleanup_required`. The job table holds
operational metadata, never life-story content.

## 13. Cross-person references

Phase 1 must identify any narrator-owned row containing a hard reference to a different
`people.id`. Do not invent placeholder people; do not silently null such references.
Dry run reports them as package dependencies. If a cross-person dependency prevents
independent restore, implementation pauses at that finding and the WO is amended
deliberately. No generalized relationship merging is built preemptively.

## 14. Historical and hidden state

Portable means faithful, not "only things currently visible in the UI." Where
narrator-owned, packages preserve hidden records; soft-deleted photographs / documents;
rejected candidates; unreviewed story candidates; provisional truth; promoted truth;
corrections; review decisions; extraction failures; declined story-capture decisions;
old / legacy narrator material. **Restore MUST NOT turn a hidden / rejected / deleted
item back into an active one.**

## 15. Consent and operator provenance

Historical consent / attestation records that belong to the narrator are preserved as
historical evidence. Importing an old attestation does not silently create new
authorization the target installation would otherwise require. Operator identifiers in
provenance may be retained as historical strings; credentials never travel with them.

## 16. Operator UI

An operator feature. **Export Narrator** on the existing narrator management surface
shows narrator name, estimated domains, preparation status, final file, counts, bytes,
integrity status. **Import Narrator Package** flows: choose package → dry run → review
narrator + contents + warnings → restore → verification → narrator available. The
narrator-facing interview UI shows no package mechanics. **Do NOT create "Export and
Delete" as one button.**

**16.1 Phase 5 requirements recorded 2026-09-11, after Phases 2–3 landed** (from review of
the service as built; none of this is implemented yet):

* **Two verdicts, never one.** *Package integrity* (ZIP structurally safe · BagIt complete ·
  checksums valid · Lorevox manifest readable) is shown separately from *Lorevox restore
  readiness* (schema compatible · narrator identity · installation dependencies satisfied ·
  no id collisions · no destination-file collisions · external-person warnings → `RESTORE
  READY` / `RESTORE REFUSED`). A valid bag can still be unrestorable *here*.
* **Plain language first, RFC detail behind "Advanced".** The operator sees *Package verified
  · N records · N photos · N documents · N audio files · size · Integrity: Verified ·
  Warnings: N*; BagIt validity, package id, source commit, schema fingerprint, per-lane
  counts, dependencies, residue and checksums live in an Advanced panel.
* **Export has a preflight.** Before the final Export button: narrator identity and the
  domains expected to travel, estimated from the ownership declaration without building a
  package — so "why zero trips?" is asked before minutes of ZIP building, not after.
* **Asynchronous jobs, explicit artifacts.** Export runs as a server-side job with
  status/progress; the `.lorevox.zip` is written to disk **outside `DATA_DIR`**; the browser
  gets a job id, polls or subscribes, then a download endpoint streams the existing file.
  Never a package in server or browser memory.
* **Uploads land in a controlled staging area outside `DATA_DIR`.** Upload → validate →
  dry-run → restore. A selected file is not narrator state until `restore_narrator()` says so.
* **Export jobs are NOT `narrator_package_jobs` rows.** `0054` is landed and its `kind CHECK`
  is immutable; the export lifecycle (queued → snapshotting → collecting → bagging →
  complete) is not the restore lifecycle. Either a separate `narrator_package_export_jobs`
  table or a deliberately designed generalisation in a **new** migration (`0056` or later —
  `0055` is landed, for `file_manifest_json`) — **decided in Phase 5, not before**, and
  never by destabilising the proven restore state machine.
* **One service.** Routers manage jobs, uploads and downloads; `narrator_package.py` remains
  the only export, dry-run, restore and recovery implementation (§28.5).
* **Hard rules restated:** dry-run refusal is final — no "restore anyway"; export and delete
  are never one control; `bagit` stays at 1.8.1 (SHA-256 manifests are RFC 8493-compliant)
  until Phase 6 is accepted, with the `1.9b1` prerelease that drops `pkg_resources` noted
  for later evaluation.

## 17. Phase plan

**Phase 0 — Read-only repo and live-data ownership audit.** No product mutation, no
stack, no UI. **Method, decided 2026-09-09 (§25.16):**

1. **Live SQLite inspection — primary.** A script opens
   `/mnt/c/hornelore_data/db/hornelore.sqlite3` with `mode=ro` via a URI, **takes the
   path as an explicit argument** (the WSL profile carries stale `DATA_DIR` /
   `DB_NAME` exports), and **refuses to run if it cannot prove read-only** — any
   write attempt must raise. It reads the actual tables, columns and foreign keys,
   narrator-owned row counts for Chris, Kent, Janice and one synthetic Ada, and every
   narrator-linked path the rows name.
2. **Repo derivation — reconciliation check.** Migrations `0001`–`0053`, `db.py`
   including `init_db()`'s non-migration columns, `person_delete_inventory()`,
   `_EXTENDED_PERSON_SCOPED_TABLES`, and `narrator_erasure.build_plan()`. Where the
   live database and the code disagree, that disagreement is a row in the table, not
   something to resolve quietly.
3. **Filesystem inventory — read-only.** What exists under `/mnt/c/hornelore_data`
   compared with what the live database references. Orphan / unreferenced material is
   **classified, never deleted or guessed into an owner.**

The report is written only under `.runtime/` or `docs/reports/` — real-family counts
and paths never enter Git. Chris's part is one command and pasting the result; nothing
is deleted, moved, imported, exported or altered. Output classes: `portable
narrator-owned` · `shared/unassigned` · `installation-owned` · `cache` · `historical` ·
`unknown`. **Exit gate: no unexplained narrator-data lane.**

**Phase 1 — Land the ownership contract.** The small shared declaration used by
portability; reconcile erasure coverage with it. A structural parity check must fail
when portability owns a lane erasure does not know, or erasure finds narrator data
portability would omit, unless the difference has an explicit policy classification.
**Exit gate: one reviewed ownership truth.** *(**LANDED 2026-09-10** — see §31. Phase 2 is governed by §30.)*

**Phase 2 — Package v1 exporter.** Manifest, row serialization, filesystem collection,
path normalization, SHA-256, secret refusal, snapshot consistency, temp-file ZIP,
operator endpoint. Memory Archive export unchanged. **Exit gate: synthetic narrator
package with all expected domains.** *(**LANDED 2026-09-10** — see §32. The operator
endpoint (§16) is deferred to Phase 5 with the UI; the service and recovery CLI landed.)*

**Phase 3 — Dry-run + Restore v1.** Validation, ZIP / path safety, compatibility,
collisions, durable job, staged file restore, one DB transaction, cleanup / recovery,
exact-id restoration. **Exit gate: synthetic package restores into an empty disposable
Lorevox DB with no missing lane.** *(**LANDED 2026-09-11** — see §33.)*

**Phase 4 — Round-trip equivalence.** original → export A → empty Lorevox → restore →
export B → compare, separately for DB rows, files, binary hashes, transcripts, audio,
photos, documents, travel, structured memory, story / review state, timeline,
provenance. Volatile package / job metadata excluded explicitly. **Exit gate: A and the
restored state are equivalent for every authoritative / portable lane.** *(**LANDED
2026-09-11** — see §34.)*

**Phase 4 finding, 2026-09-11 — the Restore-only V1 boundary, measured on the first
round-trip run.** Three narrator-owned lanes have `INTEGER PRIMARY KEY AUTOINCREMENT` keys
— `turns` (`db.py:588`), `turn_extraction_ledger` (`0038:55`), `turn_extraction_results`
(`0041:62`); every other narrator key is a UUID or text. Restore preserves ids verbatim
(§10.1) and refuses any package-owned id already present (§10.2) — Phase 4's sentinel
narrator, created on a fresh destination, took `turns.id` 1, Ada's package carried
`turns.id` 1, and dry run refused. Correct behaviour, and a named boundary:

**Installation-local integer-id boundary.** `turns.id` (and the two extraction ledgers)
are AUTOINCREMENT surrogates allocated per installation, not identities. Exact-id Restore
is fully portable into a collision-free target. **Packages exported from the SAME source
installation** share one `turns` sequence, so their integer ranges are disjoint by
construction and they may coexist in one root, subject to the ordinary dry-run check.
**Packages from DIFFERENT installations** have no shared integer namespace and may collide
even when the narrators are unrelated — V1 refuses and does not remap. Dry run is
authoritative either way. Pinned by
`tests/test_narrator_package_roundtrip.py::RestoreOnlyV1Boundary`.

What follows: Phase 6 stays as written — each real package, from each machine, into its
**own** disposable clean root; no remapping is attempted there. Phase 7's "restore
packages only when desired" **must not be read as consolidating multi-origin packages
into one `/mnt/c/lorevox_data`.** Before the final one-root family cutover an explicit
decision is owed: (1) restore only a mutually collision-free, same-origin package set into
that root, or (2) open a separate Multi-Origin Merge/Remap WO — which must first inventory
every reference to `turns.id` (FKs, `trip_turn_links.user_turn_row_id` /
`assistant_turn_row_id`, extraction ledger/result keys, provenance and embedded JSON turn
keys) before choosing between integer remapping and a globally unique turn identity.
**That design is not absorbed into V1.** Recorded as a Phase 4 success: the round trip
found a limit of the format before Kent or the cutover did.

**The broader shape of that WO (recorded 2026-09-11).** Integer keys are only half of it.
Christopher carries the **same `people.id`** on the desktop and the laptop (§31), so once
either Christopher package is restored into a root, the other is a `narrator_exists`
refusal (§10.2) — correctly — even if every integer were disjoint. The Merge/Remap WO
therefore has two distinct problems: **same-person merge across installations**
(combining complementary lanes of one narrator without duplicating or overwriting
identity or provenance) and **installation-local id reconciliation** (`turns` and the
extraction ledgers, and everything that references them). Phase 6's per-package clean
roots are what give that WO real packages to design against; it is not built before
Phase 6.

**Phase 5 — Operator UI acceptance.** Export, download, import select, dry run, refusal
on collision, successful restore, narrator in picker, transcript / photo / travel
document open, timeline / profile / memoir resolve as before. No narrator-facing UI
changes.

**Phase 6 — Real-family portability acceptance.** Only after synthetic round-trip
passes. Export Chris, Kent, Janice separately (and Melanie or any other real narrator
with data to retain). **Packages and comparison reports stay OUTSIDE Git.** Restore each
into a disposable clean root; verify counts and hashes. **No deletion of originals.**

**Phase 7 — Clean Lorevox data world.** Full immutable backup of `/mnt/c/hornelore_data`;
leave it untouched; create `/mnt/c/lorevox_data` and `lorevox.sqlite3`; run migrations;
verify zero real narrators; reconcile `DATA_DIR`, `AUTHORS_DIR`, `KNOWLEDGE_DIR`,
`UPLOADS_DIR`, `MEDIA_DIR`, `DB_NAME` so no mixed root is accepted; restore packages
only when desired — **and only a mutually collision-free set: same-origin packages, or
packages whose dry runs all pass against that root. Multi-origin consolidation into one
root is NOT a V1 capability (Phase 4 finding above; §10.3).** **See §27.6–27.7 for the
required runtime gate.**

**Phase 8 — Product naming cutover.** Package / UI language becomes Lorevox. No blind
repository-wide rename; compatibility names kept where change adds unrelated risk.
Repository / path rename is a later explicit cleanup.

## 18. Round-trip acceptance contract

**Identity** — narrator exists once; original id preserved; display identity preserved;
testing / real classification not accidentally changed.
**Conversation** — session and turn ids preserved; narrator and Lori text
byte-equivalent; order and ownership preserved.
**Audio** — narrator-only; same count; same SHA-256; missing stays missing.
**Structured memory** — profile, projection, Bio Facts, Family Truth, provenance,
correction / review states, extraction ledger / results, onboarding state, timeline
state match their original portable state.
**Stories / memoir** — candidate identities, source-turn provenance, placement, review
and promotion status preserved; canonical memoir after Restore agrees with pre-export.
**Photos / media** — metadata, original hashes, links, soft-delete / hidden state
preserved; thumbnails preserved or deterministically regenerated per declared class.
**Travel** — trip identity, regions / stops / days, photo links and multi-day
placements, notes, source documents and hashes, narrator / turn provenance preserved.
**Isolation** — restoring A changes no B rows or files.
**Installation state** — Guard Lab configuration, global curated context, credentials,
schema / application configuration identical before and after.

## 19. Failure semantics

Export: `complete` · `refused_changed_during_snapshot` · `refused_unreadable_lane` ·
`refused_unsafe_path` · `refused_secret` · `failed`.
Dry run: `ready` · `refused_collision` · `refused_checksum` · `refused_schema` ·
`refused_dependency` · `refused_unsafe_package`.
Restore: `complete` · `rolled_back` · `cleanup_required` · `recovery_required` ·
`failed_before_visibility`.
**No generic `success` when a lane was skipped.**

## 20. Tests and evidence — deliberately bounded

Required automated coverage is limited to the destructive / portability boundaries:
ownership-inventory parity; ZIP traversal / symlink refusal; checksum / refusal
behavior; id-collision refusal; DB rollback with no visible partial narrator;
filesystem cleanup / recovery; synthetic export→restore→re-export equivalence;
narrator-A restore cannot mutate narrator B; Guard Lab / install state does not travel.
Then the real-family local acceptance once. **Do NOT run unrelated multi-hour Lori /
Guard Lab gates as prerequisites.**

## 21. Explicitly out of scope

Narrator merge; duplicate-person merge; clone; automatic UUID remapping; cross-install
account migration; credential migration; Google account migration; cloud sync; cloud
backup; encrypted package format; post-session extraction engine; fixing the ~9,830-token
extraction prompt; reprocessing old transcripts; repository rename; universal env
rename; automatic destruction of Hornelore data; shared-family package unless Phase 0
proves it required and Chris adds it.

## 22. Relationship to post-session processing

Compatible, not implemented here. The package preserves original narrator evidence plus
current derived knowledge, so a future Lorevox may restore, read the original
transcript / audio / photos / documents, run newer post-session extraction, and produce
newer structured memory without losing the narrator's words. **Portability lands before
reprocessing is relied upon.**

## 23. Hornelore → Lorevox final state

```text
/mnt/c/hornelore_data   historical family/R&D world — preserved, no longer active
Narrator packages       Chris / Kent / Janice / … .lorevox.zip
/mnt/c/lorevox_data     fresh installation, fresh lorevox.sqlite3, zero built-in family
                        narrators; narrators appear only by creation or Restore
```

## 24. Acceptance definition

**A** completeness — every narrator-owned portable lane identified by the audit is in
the package · **B** integrity — every packaged file checksummed and every restored
authoritative file matches · **C** identity — narrator and dependent ids preserved ·
**D** atomicity — failed Restore never exposes a partial narrator · **E** isolation ·
**F** travel / media demonstrably included · **G** evidence — transcript both sides,
audio narrator-only · **H** round trip on synthetic and selected real narrators ·
**I** clean product — fresh `/mnt/c/lorevox_data` contains zero real narrators before
any package is imported · **J** preservation — `/mnt/c/hornelore_data` not destroyed.

## 25. Decisions locked by approval — Chris, 2026-09-09

1. Narrator package is the portability unit.
2. Package format is transparent `.lorevox.zip`.
3. V1 Restore preserves ids and refuses collisions.
4. Merge / remap / clone are deferred.
5. Travel documents and photographs are mandatory package content where narrator-owned.
6. Transcripts include both sides; saved audio remains narrator-only.
7. Guard Lab and installation configuration do not travel.
8. Export never automatically deletes.
9. Shared / unassigned family data is reported, never duplicated or guessed.
10. The clean transition uses a fresh data root, not erasure of the only Hornelore
    source.
11. The old Hornelore data root remains preserved until a separate explicit retention /
    deletion decision.
12. Post-session extraction is a separate subsequent WO; this package preserves the
    evidence it needs.
13. **The Horne-family auto-seeder is REMOVED from the Lorevox product runtime — not
    disabled by flag.** See §27.6.
14. **A consistent database snapshot does not make the whole package consistent.
    Database and filesystem consistency are separate proofs.** A file that appears
    while export runs can become neither an undeclared extra nor an omitted asset
    without being detected. See §28.2.
15. **BagIt tooling operates only inside an exporter-created temporary staging
    directory.** It is never pointed at `/mnt/c/hornelore_data`, `/mnt/c/lorevox_data`,
    or any live `DATA_DIR`. See §28.1.
16. **Phase 0 uses live read-only SQLite inspection as primary evidence**, with the
    migrations / `db.py` / erasure-plan derivation as the reconciliation check and a
    read-only filesystem inventory classifying what exists on disk against what the
    database references. See §17 Phase 0 and §27.9.

## 26. First implementation action after approval

**Do not start with an exporter.** Start with Phase 0. Its first deliverable is one
table showing every narrator-data lane found in current `main`, where it lives, how
ownership is proven, whether erasure already knows it, whether current Archive Export
contains it, and whether Portable Narrator v1 will include it. Only after that table has
no unexplained gaps does implementation proceed to the package format.

---

## 27. Repo-grounded amendments — recorded 2026-09-09 against `7d5d040`

Each is a line that READS the value, not a name that resembles it.

**27.1 Restore-only, preserve ids, refuse collisions** (§10) — locked. Today's Phase 6
work spent hours on joinability (`turn_key`, provenance rows, candidates bound to source
turns); an id-remapping restore severs every one of those links.

**27.2 `/mnt/c/hornelore_data` is never deleted as part of cutover** (§7, §23, §24-J) —
locked. Deletion of narrator data is a separate authorized act
(`docs/decisions/`, `narrator_erasure.py`), never a side effect.

**27.3 Shared / unassigned material is reported, never guessed or duplicated** (§6) —
locked.

**27.4 `testing_only` is set at person-row creation.** It is creation-time only with no
write partner — `db.py:2852`, and
`WO-LORI-ARCHIVE-TO-MEMOIR-02_PHASE6-BASELINE-PROTOCOL.md` §2. §18's "classification not
accidentally changed" is therefore satisfied only if Restore writes it in the `people`
insert, not afterwards. `GET /api/operator/guard-lab/narrators` is the check that
proves it took.

**27.5 Real-narrator Phase 0 evidence stays outside Git.** Phase 0 runs against Chris,
Kent and Janice; its report carries their counts, paths and filenames. Same rule as
Phase 6: `docs/reports/` or `.runtime/`, never staged. (`docs/reports/` is gitignored
since `a87e865` for exactly this reason.)

**27.6 Phase 7 REQUIRES removal of the family-locked runtime before a clean root can be
accepted.** `ui/hornelore1.0.html:10083` `_horneloreEnsureNarrators()` iterates
`HORNELORE_NARRATORS` (`:10073` — Chris, Kent, Janice), fetches
`templates/<name>.json` and calls `lv80PreloadNarrator(tpl)` for any missing one on
first boot; `:10136` replaces `lvxStageDeleteNarrator` to refuse their deletion outside
operator mode. The block's own header (`:10063`) reads *"LOCKED NARRATOR UNIVERSE — Only
three narrators: Chris, Kent, Janice Horne. Auto-seeds from templates on first boot."*
While it runs, acceptance criterion I is unreachable by construction: the UI recreates
the family the first time it loads against an empty root. **Decision (Chris,
2026-09-09): remove it. No replacement flag.** A family-specific product assumption is
what the universal pivot exists to remove; building a flag around it keeps it. Hornelore
history stays in Git history and the frozen data world. Do this in Phase 7, not in
tonight's commit cleanup.

**27.7 The three Horne templates are not an active source for generalized Lorevox.**
`ui/templates/christopher-todd-horne.json`, `kent-james-horne.json`,
`janice-josephine-horne.json` are real-person data sitting in the repo folder (untracked
since `a87e865`). They must not remain something the runtime reads to create narrators.
Preserve them with the frozen Hornelore material as appropriate; they are not part of
the clean data world.

**27.8 Two things this WO does not resolve and must not absorb.** The LLM extraction
prompt overflow (~9,830 vs 8,192, `docs/BACKLOG.md` §2.6) and the false-green session
health. Both were found 2026-09-09; both are Phase 6 / post-session lanes. Moving
extraction post-session does not shrink the prompt.

**27.9 Phase 0 tooling note.** The live-schema / FK-graph step needs SQLite access.
Either a read-only inspection script run by Chris in WSL against the absolute live
database path (the WSL profile carries stale `DATA_DIR` / `DB_NAME` exports — pass the
path, do not rely on the environment), or a static derivation from migrations
`0001`–`0053` reconciled against `db.py`. The live one is stronger; both are legitimate
and the report must say which it used.

---

## 28. Packaging amendments — accepted 2026-09-09, apply from Phase 2

No new phases. These sharpen §7, §8, §12, §16 and Phase 4. Nothing here is needed for
Phase 0 or Phase 1, and nothing is installed until Phase 2 begins.

**28.1 The package is BagIt-compatible internally (RFC 8493), with
`lorevox-manifest.json` layered on top.** §7.2's layout becomes:

```text
<Narrator>_<package-id>.lorevox.zip
├── bagit.txt
├── bag-info.txt              (includes Payload-Oxum: bytes.count)
├── manifest-sha256.txt       (every payload file under data/, SHA-256)
├── tagmanifest-sha256.txt    (the tag files above, including lorevox-manifest.json)
├── lorevox-manifest.json     (§7.3 — narrator id, source commit, schema, counts,
│                              dependencies, compatibility; BagIt does not know
│                              what the payload means, this does)
└── data/
    ├── records/   one .jsonl per narrator-owned table/domain, per the inventory
    └── files/     DATA_DIR-relative narrator-owned paths
```

BagIt's *complete* (every listed file present, no undeclared files) and *valid*
(complete + every checksum verifies) are exactly §7.4 and §11's requirements, with
standard vocabulary and an independent validator. `records/*.jsonl` are payload files
and are hashed like everything else. Adopt `bagit` (Library of Congress, Python) and
**pin it in both `requirements-gpu.txt` and `requirements-test.txt` at Phase 2**, at
whatever version is current and verified then. **The library builds a bag in place —
it moves files into `data/`. It runs only on the exporter's temporary directory, never
on `DATA_DIR`.**

**28.2 Export reads narrator rows from a `sqlite3` `backup()` snapshot, not the live
database.** Python's `Connection.backup()` produces a consistent point-in-time copy
while other connections keep using the live file. The exporter takes one snapshot into
a temporary database, extracts that narrator's rows from it, and discards it. The
whole snapshot never enters the package. This replaces the DB half of §8.3's
before/after measurement; **the filesystem half stays** — files are measured before
and after collection, and cross-checked against the snapshot's rows so a file no row
references is refused or warned, never silently packed. A narrator who changes between
the snapshot and the file pass still produces `refused_changed_during_snapshot`.

**28.3 ZIP is written to a temporary file with ZIP64 enabled** (`force_zip64` where a
member's size is not known ahead), consistent with §8.4. Restore never calls
`extractall()` on a package: every member is inspected first against §11 before any
byte lands.

**28.4 Phase 4 compares semantics, never outer bytes.** Two ZIPs of the same narrator
legitimately differ in member order, timestamps and package/job metadata. Equivalence
is: narrator DB records compared semantically by stable id · every payload file's
SHA-256 · record counts by lane · relationships and provenance references. That is
BagIt's own notion of validity — completeness plus declared checksums — not container
identity.

**28.5 One service, two front ends.** `server/code/api/services/narrator_package.py`
holds export, validate, dry-run, restore, **recover** (§33.1) and **compare** (§34). The
operator UI (§16) and a thin `scripts/narrator_package.py
{export|validate|dry-run|restore|recover|compare}` recovery CLI both call it.
**There is never a second implementation of portability.** The CLI exists for when the
UI is unavailable; it is not the normal way to operate Lorevox.

**28.6 Encryption is a later, separate WO.** A `.lorevox.zip` is a complete copy of a
person's life record and will sit on USB drives. Python's `zipfile` cannot encrypt, and
ZIP passwords are the wrong tool. The intended shape is `age` (recipient key or
passphrase) wrapping an already-correct package — `<name>.lorevox.zip.age` — added
only after export → restore → re-export equivalence is proven. Not on V1's critical
path; recorded so it is not forgotten.

**28.7 What this does and does not install.**

---

## 29. Phase 1 policy edges — locked 2026-09-10 after Phase 0

**29.1 The contract expresses selectors and relationships, never bare table names.** A
table can hold rows of different disposition. The Phase 2 exporter consumes the Phase 1
declaration and never reconstructs ownership from the Phase 0 matrix document, which is
evidence, not code.

**29.2 Media archive ownership is row-level through the parent item.**
`media_archive_links` and `media_archive_family_lines` have no person column; they belong
through `archive_item_id → media_archive_items.person_id`. `db.py:5696-5705` already
deletes them by that selector. If the item is narrator-owned, the item and all its child
rows travel. If the item has no person owner it is shared/family or unassigned — reported
under §6, not packaged. `media_archive_people` follows the item; a tag naming another
person is preserved with the item and recorded as an external-person dependency (§13).
**Proximity or a mention never establishes ownership.**

**29.3 Import provenance and staging.** `import_batch` and `import_candidate` rows are
portable narrator state. `import_staging/<batch>/<candidate>/original.<ext>` is portable
**conditionally**: it is the verified local byte source promotion builds from
(`import_repository.py:136-152, 231-235`; promotion refuses without it), so it travels when
the candidate is unresolved and excluding it would make the restored candidate no longer
actionable — verified against the candidate's `file_hash`. Once a candidate has
materialized into a permanent `photos` row and file, the staging copy is redundant and need
not travel. `import_staging/.incoming/…` is acquisition scratch and never travels.

**29.4 The column-only chains are closed with deletion evidence, not inference — and three
of them are erasure GAPS, verified 2026-09-10.** *(This clause listed four chains until
2026-09-10; `import_candidate` was miscounted — it has a direct FK to `people`, which the
Phase 0 instrument's own `FKs→people: 1` column recorded while its chain walker reported a
longer path through `photos`. Instrument corrected to prefer the direct FK and to capture
`ON DELETE`.)* The three that remain:

| chain | declared FK | erasure today | status |
|---|---|---|---|
| `turns → sessions.person_id` | `turns.session` FK, `sessions.person_id` added by `ALTER` (`0044`) with no FK | `sessions` is an erasure lane; `turns` coverage to be cited | **VERIFY** |
| `interview_threads → interview_sessions.person_id` | `0009:56` `REFERENCES interview_sessions(id)`, **no `ON DELETE`** | only a `DELETE … WHERE session_id=?` helper (`db.py:9017`) that hard-delete does not call; not in `_EXTENDED_PERSON_SCOPED_TABLES` | **GAP — repair in Phase 1** |
| `trip_photo_day_placement_skips → trips.person_id` | **no FK at all** (`0043`, a historical skip ledger) | not in the extended list; `db.py` names it only in schema checks (`493–534`) | **GAP — repair in Phase 1** |

And one asymmetry in the media archive: `media_archive_people` FKs to `media_archive_items`
(`0003:156`, no `ON DELETE`) and is deleted only by its own `person_id` (`db.py:5613`),
while `media_archive_links` and `media_archive_family_lines` are deleted **by parent item**
(`5696–5705`). A tag on a narrator-owned item that names a *different* person is deleted by
neither path and can block the parent delete. **GAP — repair in Phase 1**, with a test that
pins the other-person tag case.

Phase 1 cites the line in `db.py` or `narrator_erasure.py` that deletes each lane, or
repairs it, and a parity test fails loudly if a narrator-owned lane is known to export and
not to erasure, or the reverse, without an explicit policy classification. These repairs
are targeted; §17 Phase 1's "do not rewrite hard deletion wholesale" stands.

*(§28.7, restored — the §29 insertion split it:)* **Phases 0–1: nothing. Phase 2:
`bagit`.** Everything else is stdlib — `sqlite3`, `zipfile`, `hashlib`, `json`,
`tempfile`, `pathlib`, `shutil` — already in `.venv-gpu` (Python 3.12). No new database,
service, container or daemon.

## 30. Travel domain and referential integrity — locked 2026-09-10, governs Phase 2

**Product requirement, generic:** for ANY narrator, if Lorevox holds narrator-owned travel
material, the package carries the **entire travel domain** and restores it faithfully. No
export logic may depend on which narrator is being exported.

**What "entire travel domain" means** — every lane the declaration owns through
`trips.person_id`, when present: `trips`, `trip_regions`, `trip_stops`, `trip_days`,
`trip_themes`, `trip_location_notes`, `trip_bio_suggestions`, `trip_story_links`,
`trip_public_context`, `trip_photo_links`, `trip_photo_context`,
`trip_photo_day_placements`, `trip_photo_day_placement_skips`, `trip_turn_links`,
`trip_sources` rows **and the `trip_sources/<id>` files those rows name**; plus the
narrator's photos and media those rows reference, which travel through their own
ownership lanes, not through travel. Current review / placement / live state and
provenance columns travel as-is (§14, §18). All of this is already declared in
`narrator_data_inventory.py` and proven reachable by the Phase 1 parity test — Phase 2
adds no travel-specific ownership, it consumes the declaration.

**Referenced files must exist — and only referenced files count.** A narrator-owned
`trip_sources` row whose `storage_path` names a file that is not on disk is an unresolved
dependency: the exporter reports it and refuses a package that would claim the document,
never packages a row that points at nothing. The rule is scoped to **files referenced by
this narrator's rows**. Directories under `trip_sources/` (or any lane) that no row of this
narrator references are filesystem residue, not narrator travel evidence: they are reported
as residue, never packaged, and never block an otherwise valid export.

**Referential-integrity invariant (generic, all lanes, first met in travel):** *a package
must never contain a narrator-owned row whose referenced turn / session / photo / item
the exporter would otherwise omit.* Resolution, in order: (1) if the accepted ownership
declaration proves the referenced row belongs to this narrator, it is included through
its normal lane; (2) otherwise the dependency is **reported as unresolved and the export
refuses**, naming the rows. The exporter does **not** guess ownership, does not sweep
unowned sessions, and carries no per-narrator attribution rule. Whether an
operator-confirmed attribution mechanism is needed at all is decided only if the generic
exporter demonstrates it on a real acceptance run — not built in advance.

**Acceptance fixtures:** synthetic Ada with a seeded travel domain (two trips, days,
placements, `trip_sources` files, turn links, and a deliberately dangling link) proves the
rules in Phases 2–4. The laptop's real narrator with two trips / 39 days / 27 photos /
20 turn links is the demanding Phase 6 acceptance case — a fixture, never a definition.

**Recorded and closed:** the 2026-09-10 desktop probe of `trip_turn_links` ran on a machine
with zero trips and measured nothing; the laptop probe is deferred to Phase 6, because
the invariant above resolves the question generically without it.

## 31. Phase 1 closeout — landed 2026-09-10

**Exit gate met: one reviewed ownership truth, held by test in both directions.**
Measured under `.venv`: `tests.test_narrator_erasure_ownership_gaps` **4/4** and
`tests.test_narrator_data_inventory_parity` **15/15**, 19 ran, 0 skipped, 170 s.

**What landed.**

| piece | where | what it is |
|---|---|---|
| The declaration | `server/code/api/services/narrator_data_inventory.py` | Every one of the 72 live tables carries an owner — `Direct(column)`, `Parent(fk, table)` or `Installation(reason)` — a class (§5), `portable`, `erasable`, `path_columns` (§8.5) and `external_person_columns` (§13). Thirteen filesystem lanes keyed by person, by row (with the resolving SQL), shared, or installation. `select_sql()` / `delete_sql()` generate the narrator selector by recursion through parents, bound to one `:pid`. Stdlib only. |
| The three repairs | `server/code/api/db.py` `_PARENT_OWNED_CHILDREN` | The inline media-archive parent-child loop lifted into a named list and extended with `interview_threads` (via `interview_sessions.person_id`), `trip_photo_day_placement_skips` (via `trips.person_id`) and `media_archive_people` (via `media_archive_items.person_id`, in addition to its own `person_id`). Same subselect idiom; nothing else in `hard_delete_person` changed. |
| Gap tests | `tests/test_narrator_erasure_ownership_gaps.py` | Through the real `hard_delete_person()` with `foreign_keys=ON`: delete succeeds AND A's rows are gone AND B is untouched. 3 RED at `c575570` (two rollbacks, one residue), 4 GREEN after the repair. |
| Parity | `tests/test_narrator_data_inventory_parity.py` | Against the schema `init_db()` actually builds, never a hand list: completeness both ways; reach — every erasable lane is hit by `_EXTENDED_PERSON_SCOPED_TABLES`, `_PARENT_OWNED_CHILDREN`, `_hard_delete_media`, or an `ON DELETE CASCADE` chain read from `PRAGMA foreign_key_list` to fixpoint, and the reverse; installation tables never reached; `db.py`'s columns equal the declaration's; every selector `EXPLAIN`s against the live schema; a two-narrator boundary; FS lanes equal `FIXED_TARGETS` / `SHARED_PURGE`, and the row lanes are checked by **running** `_dynamic_plan`. `POLICY_EXCEPTIONS` is the only sanctioned way to differ, and it is empty. |

**Found while landing, not in Phase 0.** The erasure planner names a fourth row-keyed
lane — legacy transcript exports under `memory/agents/<sub>/<slug>`, keyed by
`sessions.conv_id` and named only by `chat_memory_paths.export_basenames()`
(`narrator_erasure.py:376-395`). Added as `agent_transcripts` (class C, portable). The
dynamic-plan parity test is what caught it; a hand-listed set would have passed.

**The one allowed asymmetry, declared rather than exempted.** `media_archive_people` is
Parent-owned (follows the item) *and* is still swept by its own `person_id` at
`db.py` `_EXTENDED_PERSON_SCOPED_TABLES` — tags naming this narrator on other people's
items go with the narrator, the item stays. The parity test permits that only because the
column is declared in `external_person_columns`; any other column mismatch fails.

**Not done, on purpose.** Erasure does not consume the declaration (§17: no wholesale
rewrite). `import_candidate`'s staged original remains *conditional* (§29). Nothing was
exported. `bagit` is not installed.

**Data-location finding for Phase 6 (measured 2026-09-10, both machines).** Eleven labelled
Phase 0 reports under `.runtime/eval/` — five desktop roots / backups, five laptop, one
laptop id-comparison. **No real narrator has a trip on the desktop** (its July backup's one
`trips` row is the placeholder id `PASTE_UU`; `C:\lorevox_data` is a pre-trip April world;
the E: root is January experiments). **The laptop live root holds the travel domain**: 2
trips, 39 days, 21 stops, 24 location notes, 51 photo-context rows, 40 photo links, 3
placements, 20 turn links, 27 photos — and **0 `trip_sources` rows** (the directory holds
3 files, 433 B). Laptop backups are subsets of laptop live by id. Desktop live holds
conversations, bio facts and saved audio the laptop does not. **Neither machine is the
copy; both hold unique narrator evidence, and Phase 6 exports from both.** Both machines
also carry ~10,800 `sessions` rows with no owner — the §6 residue class, generic, reported
never swept. Details: `docs/handoffs/HANDOFF_2026-09-10_LAPTOP-NARRATOR-AUDIT.md`.

**Cross-copy comparison — `scripts/phase0_report_comparator.py`, run
`phase0-report-comparison-20260910T234618Z` over desktop-live, laptop-live and one
backup of each.** 176 `people` ids seen across the four reports (label from the row's own
fields and name: 39 "real"-looking, 69 synthetic/test, 68 deleted residue — the 39
includes repeated `John` / `Walt` fixtures with plain names, so it is an upper bound).
**Only 5 ids exist on both machines, 3 of them real: Chris, Kent, Janice.** 131 ids on
"more than one copy" is each machine's live + its own backup, not reconciliation scope.
Pre-0044 schemas report `unattrib.` for `sessions`/`turns`, never a false zero. Of the 5
shared ids, all 5 have lanes on one machine only and 1 (Chris) has lanes whose counts differ
between machines. **The real / synthetic-test / deleted-residue classification is comparator
reporting metadata only.** Phase 2 never decides inclusion from a name or from that label:
the exporter receives one selected `people.id` and follows `narrator_data_inventory.py`.
Per narrator, lanes on exactly one machine (counts from the audit JSONs; ids not compared):

| narrator | only on desktop | only on laptop |
|---|---|---|
| Christopher `a4b2f07a` | `sessions` 3, `turns` 26, `interview_threads` 7, `bio_facts` 16, `memory_archive_*` (saved audio) | the whole travel domain (2 trips … 20 turn links), `graph_*`, `family_truth_*`, `story_candidates` 3, `timeline_events` 2, `safety_events` 4; `photos` 27 vs 4 and `import_*` 5/14 vs 1/3 differ — ids to compare |
| Kent `4aa0cc2b` | `follow_up_bank` 50, `import_batch` 1 / `import_candidate` 1 | `graph_*` 12/10, `family_truth_*` 5/5/5, `interview_sessions` 1, `media_archive_items` 1 |
| Janice `93479171` | `story_candidates` 1 | `graph_*` 14/10, `family_truth_*`, `photos` 1 + photo children, `sessions` 1 / `turns` 13 |
| Melanie `d56900b5` | — (not on desktop) | everything |

**THE LAPTOP AUDIT IS CLOSED.** Phase 6 exports each family narrator from **both**
machines (Melanie from the laptop only) and the comparison above is the checklist a
restored narrator is measured against. Nothing is merged; §10.2's collision rule means
the two copies of one narrator restore into **separate** clean roots until a later WO
defines merge. No further audit questions are opened unless a generic package invariant
cannot be resolved from the accepted contract and the schema.

## 32. Phase 2 closeout — Package v1 exporter landed 2026-09-10

**Exit gate met: a synthetic narrator package with every declared domain, including the
complete travel domain, built by a generic exporter that knows no narrator.**

**Measured under `.venv` (Python 3.12, `bagit==1.8.1`):** `tests.test_narrator_package_export`
**18/18**, 0 skipped, 180 s — the first run in which `_seed()` completed and the exporter
itself was exercised. The **four** runs before it failed inside the fixture (a `TEXT PRIMARY
KEY` reported `notnull=0`, so no ids were minted; `trip_location_notes` rebuilt by `0019`;
a `%`-formatted bytes literal; the `0039:161` one-link-per-assistant-turn UNIQUE) and
touched no exporter line. *(This said "three runs" while listing four causes — corrected
2026-09-11 on review.)* `tests.test_narrator_data_inventory_parity` 15/15 and
`tests.test_narrator_erasure_ownership_gaps` 4/4 were green in the combined run
immediately before and nothing they cover changed after it. The `sha256 validation failed`
line printed during `test_validator_rejects_a_tampered_package` is the validator catching
the deliberately corrupted payload — evidence, not a warning.

**What landed.**

| piece | where | what it is |
|---|---|---|
| The service (§28.5, one implementation) | `server/code/api/services/narrator_package.py` | `export_narrator(person_id, data_dir, db_path, out_dir)` and `validate_package(zip)`. `sqlite3.backup()` snapshot (§28.2) → pass 1 collects the narrator's keys per lane through `owner_predicate` → pass 2 streams `records/<table>.jsonl` and checks every `PRAGMA foreign_key_list` FK plus every declared `ColumnRef`: owned parent must be in the package; installation parent recorded as a dependency Restore must satisfy; declared external-person column recorded, never pulled; anything else refused by name (§30). Declared path columns rewritten DATA_DIR-relative and must exist (§8.5). Person-keyed lanes walked whole; row-keyed lanes only for ids the snapshot resolves; `import_staging` only for `conditional_sql` sub-paths; `.incoming` never; unreferenced directories reported as residue and never a refusal. File set measured before and after copy (§8.3). Credential shapes refuse (§8.6). `bagit.make_bag` on the temporary directory only, `lorevox-manifest.json` as a tag file, `Bag.validate()` before a ZIP64 stream to `.part` then rename (§28.1, §28.3). Refuses to write inside DATA_DIR. **Names no table but `people` and `sessions`; a test pins that.** |
| Declaration additions | `narrator_data_inventory.py` | `ColumnRef` + `COLUMN_ONLY_REFERENCES` (turn links → sessions/turns, photo context → photos, story links, `timeline_event_id`, memory-archive `conv_id`); `FsLane.conditional_sql` on `import_staging`. Ownership rules stay where they were — the exporter consumes, never reconstructs. |
| Recovery CLI | `scripts/narrator_package.py export\|validate` | Thin; explicit `--data-dir` / `--db` / `--out`; environment never consulted. |
| Dependency | `requirements-gpu.txt`, `requirements-test.txt` | `bagit==1.8.1`, same pin in both. `pkg_resources` deprecation noted in `docs/BACKLOG.md` §5, no setuptools pin. |
| Proof | `tests/test_narrator_package_export.py` | Synthetic Ada + Bea in one DATA_DIR built by `init_db()`. Ada: two trips with all 15 `trip_*` lanes populated (placements, a skip, turn links into her own two conversations, two source files on disk), saved audio, three photos with absolute paths, pending + accepted import candidates with staged originals, a media item tagged with Bea, family truth / graph / timeline / interview thread. Proven: valid BagIt and manifest-consistent; every seeded Ada row travels and nothing of Bea's except the one declared §13 tag; all travel lanes at fixture-measured counts; paths rewritten and files present; conditional staging and honest residue; provenance and installation dependencies; source untouched. Refusals proven by reason code: dangling `conv_id`, dangling turn rowid, missing source file (orphan dir does not block), path outside DATA_DIR, credential, files changing during collection, out-dir inside DATA_DIR, unknown narrator, tampered package fails validation. The fixture is schema-driven and fails at the seed line naming any unknown column or dangling FK value. |

**Package layout, as built:** `bagit.txt` · `bag-info.txt` (Payload-Oxum) ·
`manifest-sha256.txt` · `tagmanifest-sha256.txt` · `lorevox-manifest.json` ·
`data/records/<table>.jsonl` · `data/files/<DATA_DIR-relative path>`. Manifest fields per
§7.3 plus `ownership_declaration`, `lanes_absent_in_source`, `installation_dependencies`,
`residue_not_packaged`.

**Not done, on purpose.** No dry-run, no Restore (Phase 3). No operator endpoint or UI
(Phase 5). No deletion, no merge. No real narrator exported — the first real export is
Phase 6, after Phases 3–4 prove restore and round-trip on synthetic Ada. The
`session_ownership_residue` class (§6) is reported in every manifest and decided nowhere
in this phase.

**Review corrections, 2026-09-11 (review of pushed `a6d5805`; folded into the Phase 3
block, same service).** Seven findings, all accepted:

1. **§29.3 was not implemented.** The conditional lane packaged a staged original because
   its directory existed; `import_candidate.file_hash` was never compared. Now
   `FsLane.verified_by_digest` (declared, not coded): the `conditional_sql`'s last column
   is the row's digest; a valid SHA-256 with a missing original → `verified_source_missing`
   REFUSES, with mismatching bytes → `verified_source_hash_mismatch` REFUSES; a row whose
   digest is not a SHA-256 (historical residue) travels as a ROW, its staging is residue,
   `unverifiable_candidate_staging_not_packaged` WARNS; accepted candidates never travel.
   Classified mechanically from the digest — no name, no narrator.
2. **Bytes are bound.** `_copy_bound` hashes the source as it is read, hashes the copy,
   requires equality (`copy_digest_mismatch`); the row-declared digest check sits on that
   same source digest. The before/after `(size, mtime_ns)` measure stays as the
   independent §8.3 snapshot proof.
3. **Nested symlinks refuse.** `_lane_files_or_refuse` applies erasure's `safe_target`
   rule — a link anywhere under a selected lane is `symlink_in_lane`, never skipped.
4. `parents[3]` was `server`; default repo discovery now walks to `.git`.
5. `db_outside_data_dir`: the source database must live under the supplied DATA_DIR.
6. `unsafe_package_id`: caller-supplied ids are shape-checked before entering a filename.
7. "three runs" → four (above); the stale `Current action` row label in `HANDOFF.md`.

## 33. Phase 3 closeout — dry-run + Restore v1 landed 2026-09-11

**Exit gate met: the synthetic Ada package restores into an empty, disposable root built
by `init_db()`, with no missing lane, every id verbatim, and nothing of any other narrator.**

**Measured under `.venv` (Python 3.12, `bagit==1.8.1`), one run after the §32 review
corrections were folded in: `tests.test_narrator_package_export` 24/24 (18 before review; the
staging test replaced by the four-branch digest test, six added) ·
`tests.test_narrator_package_restore` 13/13 · `tests.test_narrator_data_inventory_parity`
15/15 · `tests.test_narrator_erasure_ownership_gaps` 4/4 — 56 ran, 0 skipped, 734 s.**
The 46/46 run that preceded it (restore 13/13 on its first real execution, before the
corrections) is the Phase 3 baseline; the 56/56 run is the acceptance evidence for the
corrected Phase 2 foundation and Phase 3 together. The nested-symlink test created a real
link and refused it (`ok`, not skipped). The two `sha256 validation failed` lines are the
validator catching the deliberately corrupted payload.

**What landed.**

| piece | where | what it is |
|---|---|---|
| Restore job | `server/code/db/migrations/0054_narrator_package_jobs.sql` | `narrator_package_jobs` — `staged → validated → files_copied → db_committed → complete` / `failed` / `cleanup_required`; holds paths, counts, error, never life-story content. Declared **installation-owned** in the inventory; parity proves erasure never reaches it and a re-export from a restored root does not carry it. |
| Untrusted-package safety (§11) | `narrator_package._safe_extract` | Every member inspected before a byte lands: absolute / `..` / drive-letter / backslash paths, symlink members, duplicates by **normalised destination**, members over 8 GiB, expansion ratio > 200 on members over 16 MiB. Never `extractall()`. Shared by validate, dry-run and restore. |
| Dry run (§10.4) | `dry_run_restore()` | Writes nothing. Structure, manifest, BagIt hashes, format/version/kind; schema compatibility (every packaged table must exist and be narrator-owned in the destination's declaration, every packaged column must exist); collisions — narrator id, any packaged primary key, any destination file (§10.2); installation dependencies the package cannot carry (e.g. `interview_plans` ids) → `missing_dependency`, named; external-person rows reported as warnings, never refused (§13); credential shapes; unsafe destination paths via an `lstat` component walk. Verdict `RESTORE READY` / `RESTORE REFUSED` with every reason. |
| Restore (§12, steps 1–15 in order) | `restore_narrator()` | Dry run first, always. Job row committed in its own connection **before** the first file. Files copied with `O_CREAT\|O_EXCL` (cannot overwrite), directories the job creates recorded, each copy re-hashed against `manifest-sha256.txt`. Then ONE `BEGIN IMMEDIATE` with `defer_foreign_keys` so order is irrelevant and violations fail at COMMIT; rows inserted in declaration order with ids verbatim; path columns the source stored **absolute** rewritten under the new root per the manifest's `path_column_basis`, relative ones untouched; inserted counts must equal the manifest and `foreign_key_check` on every written table must be empty before COMMIT. On failure: rollback, the job's own files removed, job `failed` (or `cleanup_required` naming what is left). |
| CLI | `scripts/narrator_package.py dry-run \| restore --yes` | Restore always dry-runs first and needs `--yes`; destination paths explicit; **stack down** — it writes the live destination database. |
| Proof | `tests/test_narrator_package_restore.py` | Reuses the Phase 2 fixture; exports Ada, builds a fresh destination with `init_db()`, seeds the one installation dependency. Dry run READY and write-free; missing dependency named; narrator / row-id / file collisions; tampered and traversal packages refused before any byte lands; every packaged row present in the destination by primary key with FKs holding; every payload file at `DATA_DIR/<rel>` hash-identical; photo paths absolute under the **new** root and pointing at nothing on the source; relative columns still relative; the complete travel domain at fixture-measured counts with turn links resolving; Bea absent, the §13 tag kept verbatim; a second restore refused, not overwritten; a deferred-FK failure at COMMIT leaves no rows, no files, a `failed` job. |

**Decisions this phase made for the format.** `path_column_basis` (per table, per
declared path column: `absolute` / `relative`, recorded at export, mixed refuses) is now
part of the manifest and is what Restore rewrites by. Installation dependencies are the
destination's to provide — a package never carries them and Restore never creates them.

**Not done, on purpose.** No merge, remap or clone (§10.3). No operator UI or endpoint
(Phase 5). No deletion (Phase 7). No round-trip equivalence proof yet — Phase 4 compares
export A → restore → export B semantically (§28.4); one Phase 3 test already shows equal
record counts on re-export from the restored root, which is a preview, not the proof.

**33.1 Crash-recovery correction, 2026-09-11 (review of pushed `1bc24b8`).** The first
implementation wrote `files_copied` after ALL files, and jumped from COMMIT straight to
`complete` — `db_committed` existed in `0054` and was never written. Two crash windows:
a death mid-copy left files the job could not name; a death after COMMIT left published
rows with a job that said `files_copied`, which a recovery routine would have read as
"delete the files". Corrected in the same service, no redesign:

* **`0055_narrator_package_jobs_file_manifest.sql`** (additive; `0054` untouched) —
  `file_manifest_json`: DATA_DIR-relative path → expected SHA-256 for every planned file,
  written **before the first byte**. `files_json` keeps `0054`'s meaning exactly — files
  CREATED — and is journaled after each file lands.
* **`db_committed` is written INSIDE the narrator transaction**, on the same connection,
  after count and FK verification and before `COMMIT`: rows and state publish together or
  not at all. `complete` follows in its own write.
* **`recover_restore_jobs()`** + CLI `recover`. Below `db_committed`: every planned path
  is safe-walked and **hashed; a file is removed only when its bytes equal the job's
  planned digest** — foreign bytes at a planned path are left, named, and the job goes to
  `cleanup_required`. At `db_committed`: rows, per-table counts and every planned file
  are verified **against the job's own manifest — the package ZIP is not consulted** —
  then `complete`, or `recovery_required` with nothing deleted. A pre-`0055` job with no
  manifest is `recovery_required`, never guessed. A job below `db_committed` whose
  narrator IS present is refused as a contradiction — **in all four pre-commit states,
  `cleanup_required` included** *(the first cut exempted `cleanup_required`; review of
  pushed `main` caught it: a failed job left `cleanup_required`, then a successful second
  restore of the same package, then recovery of the old job would have deleted the live
  narrator's files because their bytes hash-match the old manifest. Corrected 2026-09-11,
  pinned by `test_cleanup_required_under_a_published_narrator_is_refused_too`, which builds
  exactly that sequence.)*
* **Six recovery cases pinned** — five through a test-only seam that raises a
  `BaseException` so ordinary cleanup provably does not run, plus the `cleanup_required`
  contradiction above: death after the first file (job names what
  landed, recovery removes exactly those by hash, idempotent after `failed`); death after
  the first file **plus foreign bytes at a planned path** (preserved, named,
  `cleanup_required`, retry after the operator resolves it → `failed`); death after
  COMMIT (`db_committed` with counts, **package deleted before recovery**, verified from
  the manifest, `complete`, idempotent); forged `files_copied` under a published narrator
  (refused); `db_committed` with a missing and an altered file (`recovery_required`,
  nothing deleted); `cleanup_required` under a narrator a later restore published
  (refused, files and rows untouched). Restore suite: **19/19**.

## 34. Phase 4 closeout — round-trip equivalence landed 2026-09-11

**Exit gate met (§17): export A → restore into an empty root → export B, and A and B are
equivalent for every authoritative / portable lane — proven by a comparator that is shown
to catch a single changed value and a single changed byte.**

**Measured under `.venv`:** `tests.test_narrator_package_roundtrip` **9/9** (215 s);
combined restore 18 + round-trip 9 + export 24 + parity 15 = **66** — see the run recorded
in `HANDOFF.md`. The first combined run (65) failed all seven restore-dependent
round-trip tests on ONE collision — `row_id_exists turns.id=1` — which was correct
production behaviour and the boundary recorded under Phase 4 above; the sentinel fixture
was corrected and the boundary pinned as its own test.

**What landed.** `compare_packages_semantically(a, b)` in the same service (§28.5) and a
`compare` CLI verb. Both packages pass the §11 extraction and BagIt validation first — an
invalid package is a `package_invalid` difference, not an exception. **Compared:** narrator
id and display name; every record table independent of JSONL order — **rows carrying `id`
are compared by stable id and changed columns are named; rows without `id` are compared
as multiplicity-preserving canonical-row multisets**, so a changed id-less row is reported
as one `row_only_in_a` plus one `row_only_in_b` (inequality detected, columns not named)
and a duplicate occurrence as one extra row-only difference;
`data/files/<rel>` → SHA-256 from the validated manifests; record / file / byte counts by
lane; `path_column_basis`; installation-dependency and external-person-dependency
declarations. **Informational, never a difference:** source commit, migrations, schema
fingerprint. **Ignored by design:** `package_id`, `created_at`, ZIP order and timestamps,
`residue_not_packaged`, `warnings` — a restore deliberately does not carry source-only
residue.

**Proven:** A ≡ B while the two ZIPs are byte-different with different package ids; path
columns equivalent though the live rows point at two different absolute roots; the
complete travel domain and both dependency declarations equal; a sentinel narrator
already in the destination unchanged row-for-row and hash-for-hash; installation state
unchanged except `narrator_package_jobs`; one changed `trips.title` → exactly one
`row_differs`; one flipped photo byte → exactly one `file_hash_differs`; a junk file → one
`package_invalid`.

**Not done, on purpose.** No real narrator (Phase 6). No UI (Phase 5, §16.1). No remap —
the integer-id boundary above is recorded, pinned, and deferred to its own WO.

## 35. Phase 5 design — operator jobs and UI, decided 2026-09-11 against the shipped patterns

**What Phase 5 is.** A safe operator workflow over the proven service. It adds an HTTP
layer and one Operator-tab card; it adds no portability logic. Every decision below cites
the shipped pattern it copies.

| decision | choice | copied from |
|---|---|---|
| Gate | `HORNELORE_OPERATOR_PORTABLE_NARRATOR=1`; router prefix `/api/operator/narrator-package`; **404 when off**, never 403 | `operator_guard_lab.py:64-77`, `.env.example` |
| Where packages are written | `HORNELORE_PACKAGE_OUT_DIR` — absolute, **outside `DATA_DIR`** (the service already refuses inside); default `<DATA_DIR's parent>/lorevox_packages` | `narrator_package.py` `out_dir_inside_data_dir` |
| Where uploads land | `HORNELORE_PACKAGE_STAGING_DIR` — absolute, outside `DATA_DIR`; default `<parent>/lorevox_package_staging/<upload_id>/package.lorevox.zip`; **streamed to disk in 64 KiB chunks, never buffered**; size cap `HORNELORE_PACKAGE_MAX_MB` (default 20480) → 413 | `media_archive.py:228-245` (tempfile, chunked), not `memory_archive.py:568` (whole-body) |
| Export job persistence | **its own table**, `narrator_package_export_jobs`, migration **`0056`** (`queued → running → complete` / `failed`); `0054`/`0055` untouched; declared installation-owned | §16.1 decision; `0049`/`0054` durable-job pattern |
| Asynchrony | one daemon `threading.Thread` per export or restore, state durable in the job tables and polled by `GET`; **one package operation at a time** in-process (a module lock) — the Phase 3 exclusivity assumption becomes an application lock | no `BackgroundTasks` exists in the tree; generation threads are the only precedent |
| Download | `FileResponse` of the finished file on disk with `Content-Disposition` | `media_archive.py:147-153`, not the in-memory `memory_archive.py:655` |
| Two verdicts | `POST /import/upload` returns `integrity` (structure · BagIt complete · checksums · manifest readable) and `readiness` (the dry-run report) **as separate objects**; readiness is only computed when integrity passes | §16.1 |
| No "restore anyway" | `POST /import/{upload_id}/restore` re-runs the dry run and refuses unless READY; the card renders Restore disabled until readiness is READY and never offers an override | §16.1 |
| Preflight | `GET /preflight/{person_id}` — narrator identity + per-lane record counts and file counts/bytes **from the declaration**, nothing built | §16.1; `narrator_data_inventory` |
| Plain language first | the router returns a `summary` (records · conversations · photos · documents · trips · files · size · warnings) computed once, server-side; BagIt/manifest detail is under `advanced` | §16.1; the card computes nothing |
| UI | one card on the Operator tab, `#lvOperatorPortableNarrator`, `ui/js/operator-portable-narrator-card.js`, IIFE, local `request()` wrapper, 404 = feature off, narrator-switch clamp, `renderInto` exported for the DOM harness; nothing narrator-visible; **no delete control anywhere on it** | `operator-guard-lab-card.js` |
| Recovery | `POST /recover` → `recover_restore_jobs()`; the card shows incomplete restore jobs and offers Recover, which deletes only what the service's rules allow | §33.1 |

**Not in Phase 5:** merge/remap (§10.3, Phase 4 finding), deletion (Phase 7), any real
narrator (Phase 6), encryption (§28.6).

**35.1 Phase 5 split, decided 2026-09-11 — the Narrator Data Center.** Review reframed the
surface as the operator's one window into what Lorevox holds for a narrator, with
portability as its most consequential capability. Adopted, and **split so the migration is
not behind a UI project**:

* **5a — NOW, on the migration path.** The Data Center *entry* on the Operator tab: a
  persistent header (narrator, summary line from `preflight`, "Creating or downloading a
  package does not remove this narrator"); three plain views — **View & Download** (the
  Complete Data Check: what Lorevox recognises, from the same declaration the exporter
  uses; the "Photo Timeline says 27, inventory says 25" question is answered here),
  **Move or Restore** (one complete, **non-selective** package — every domain listed, nothing
  to untick; and Import as an explicit seven-step stepper whose completed/current/pending
  marks are the server's, so leaving and returning re-orients), **Activity** (the durable
  `0056` export and `0054` restore ledgers — no second persistence model; plain downloads get
  no jobs). Stage progress (snapshot → records → files n/N → bag → verify → zip) is
  observational — a callback that cannot change what the package contains — persisted in
  `0056.progress_json`, rendered as stages with a native `<progress>` only where the
  denominator is real, never a percentage. A native `<dialog>` confirms Restore with the
  narrator's name and plain consequences, initial focus on Cancel; the control exists only
  while the server says READY. A polite `role="status"` region announces transitions only.
  **Retention:** "Remove server copy" deletes the finished artifact outside `DATA_DIR`; the
  job record stays and says the copy was removed; the period of automatic removal is a
  decision still owed and is stated as such, never invented. Facts stated on the card:
  thumbnails are preserved files in the `photo_archive` lane and travel; Lori audio is not
  stored (`0002:57-60` CHECK).
* **5b — AFTER Phase 7, its own scope, never blocking Phase 6 or the cutover.** Rich
  per-domain inspection: domain cards with cross-surface counts (timeline placements, Life
  Map associations, trip links), an audio browser with per-turn play/download/transcript
  jump, a live memoir view, Bio Builder and questionnaire completeness, drag-and-drop
  upload as an enhancement over the labelled file control, richer activity. Each needs
  aggregate endpoints that do not exist and inspects the product that will actually
  remain — built against Lorevox, not against Hornelore.

**35.2 The card's contract, made precise on review.** No "Restore anyway"; no control that
deletes narrator rows or files; no combined Export+Delete. "Discard upload" and "Remove
server copy" are the only removal controls and touch only a staged file and a finished
artifact, both outside `DATA_DIR`. Pinned by `tests/test_operator_narrator_package_api.py`
(source pins, labelled as such) and by the router's route table (no DELETE verb — the
stronger server invariant).

## 35.3 Phase 5a live acceptance — walked 2026-09-11 in Chrome, ACCEPTED with three repairs

**Method.** Chris's real Chrome, driven from the desktop, against the shipped UI. Part A
(steps 1–9) on the running stack over `/mnt/c/hornelore_data`; Part B (steps 10–14) on the
same API started alone against an **empty root `/mnt/c/hornelore_clean_5a`** (the UI hard-wires
`localhost:8000`, so the clean installation took the stack's port while the stack was down).
Narrator: **synthetic Ada Pruitt `8ec7a427`** — one of seven Ada rows the Phase 0 probes left
on the live root (all created 2026-09-09, `testing_only`), the richest one: 2 conversations,
24 turns, 9 `memory_archive` files, no photos, no trips. **No real narrator was touched.**
Every claim below was read from the DOM, the card's exported state, or the router's own
responses, not from the card's wording.

| # | Acceptance point | Result | Evidence |
|---|---|---|---|
| 1 | Stack with `HORNELORE_OPERATOR_PORTABLE_NARRATOR=1` | PASS | flag absent → card reads "Narrator Data Center is off…" and every route 404; flag on → `GET /export/jobs` 200 |
| 2 | Operator → Narrator Data Center | PASS | `#lvOperatorPortableNarrator` is inside `#lvOperatorTab`; zero `opnc-` elements outside it; hidden while Intake is selected |
| 3 | Select the synthetic narrator | **FAIL → FIXED** | defect A below; after the fix the card follows the picker |
| 4 | View & Download | PASS | header "Ada Pruitt — everything Lorevox currently holds"; Complete Data Check `authoritative records 93 · narrator-owned files 9 · 16.2 KB · Complete ✓`, numbers equal to `GET /preflight/<id>`; the no-removal sentence is in the header |
| 5 | Move or Restore | PASS | eleven domains, all ticked, "nothing to untick", no checkboxes; job `queued → running → complete` in ~2 s; server progress observed `snapshot → bag → complete` at 60 ms sampling (the throttled ledger skips stages a 34 KB narrator finishes inside one write), card rendered `✓ snapshot ✓ records ✓ files ● bag ○ verify ○ zip`; `files 9 of 9` was observed persisted on the refused first run; **no `%` anywhere** (`/\d+\s*%/` false on every sample) |
| 6 | Leave and return | PASS in-page; **reload → FIXED** | Intake → Operator kept the job; after a full reload Activity listed it with Download but the Move view offered a fresh Create — defect B below |
| 7 | Complete: verified · download · Activity | PASS | `Integrity Verified · Warnings 0`; download 200, 33,884 bytes = `package_bytes`, SHA-256 stable across three fetches; `api.log`: 7 download requests, 6×200 + 1×410, **no 503** (Chrome's extension log showed 503 on anchor-click downloads — a browser-side artifact, refuted by the server log) |
| 8 | Remove server copy | PASS | download → 410 `package_file_gone`; narrator still in `/api/people`; preflight record and file lanes byte-identical before/after; job row kept with `package_removed_at`; Activity "· server copy removed"; status "Server copy removed. The narrator is untouched." |
| 9 | Fresh package for restore | PASS | `Ada_Pruitt_a73d71c8bcd5.lorevox.zip`, 34,853 bytes, downloaded through Chrome |
| 10 | Clean root: import without a narrator; seven steps; two verdicts | PASS in form; **readiness FAIL → FIXED** | `{"people":[]}`; import reachable with no narrator; stepper `✓1 ✓2 ✓3 ✕4 ○5 ○6 ○7`; Integrity VERIFIED in its own box while Readiness read CANNOT RESTORE — the refusal was genuine and exposed defects C and D below |
| 11 | READY → Restore offered → dialog → Cancel focused → confirm | PASS (after C+D) | Readiness READY, step 5 current, "Restore this narrator…" present; `<dialog>` "Restore Ada Pruitt? … Existing records will not be overwritten. A collision will stop the restore. Nothing is deleted."; `document.activeElement` = Cancel; no "anyway" |
| 12 | Restore completes; narrator available; records/files resolve | PASS | steps `5 → 6 → 7` in 2 s; `/api/people` = Ada with id `8ec7a427` verbatim; clean-root preflight 141 records · 24 turns · 2 conversations · 9 files 16,560 B = the package; transcript endpoint returns her events (200); picker shows her with DOB and birthplace; **photos / trips N/A — none in the source narrator** (the travel domain is proven by the suites, not by this root, which the audit already showed has no real trips) |
| 13 | Same package again | PASS | Integrity VERIFIED; Readiness CANNOT RESTORE with `narrator_exists · row_id_exists · file_exists`; no Restore control; `POST /import/{id}/restore` with `{"force":true,"restore_anyway":true}` → **409 `restore_refused`**; narrator lanes unchanged |
| 14 | Activity and recovery from the ledgers | PASS | Activity "✓ Restore · 8ec7a427 · complete"; `POST /recover` → `state_before complete · action none`, `refused 0`; Recover control absent while `incomplete = 0` |

**Defects found and repaired during the walk (product, not cosmetics):**

* **A — the card ignored the narrator picked from the picker** (`ui/js/operator-portable-narrator-card.js`).
  `app.js:4340` announces the switch **before** `await loadPerson(pid)` assigns
  `state.person_id` (`app.js:3823`); the hook discarded its `pid` argument and read state,
  so it preflighted the *previous* narrator — nothing on first pick — and the card sat on
  "Choose a narrator." after every selection. Fix: the announced pid is the answer until
  state catches up, then state is the authority again (a later delete nulls state without
  announcing and is still seen).
* **B — "you may leave this screen; the job continues" was true of the server, not the card.**
  After a full reload the ledger held the job and Activity listed it, but the Move view
  offered a fresh Create with no progress. Fix: on preflight the card re-attaches this
  narrator's newest ledger job — running resumes polling, complete-with-file offers the
  download. It reads the server's records; it decides nothing.
* **C — dry-run matched installation dependencies on the wrong column**
  (`narrator_package.py`). The exporter records dependency ids from the column the
  narrator's rows **reference** (`_check_ref` receives `parent_key`: `bio_facts.field_key →
  bio_fields.field_key`); dry-run looked them up by the **primary key** (`bio_fields.id`, a
  UUID from the product's seed loader). Every clean installation refused every narrator
  with a questionnaire: `missing_dependency bio_fields: birth_date, birth_place, …` against
  a fully seeded table. **The suites never reached it because synthetic Ada carried no
  `bio_facts`** — a coverage gap in the fixture, now closed: Ada has a questionnaire value
  whose `bio_fields` row comes from `init_db()`'s seed loader, never from the fixture. Fix:
  `_dependency_key_columns()` resolves the key column from the destination's own FK graph;
  the refusal now names the key value (`['birth_place']`) when the row is really absent.
* **D — a clean installation could not accept anyone who had ever talked to Lori**
  (`db.py init_db`). Every chat session references plan `chat_ws`, which
  `BUG-CHATWS-CONV-FK-01` lazy-seeds on the first chat turn only; a root that has never
  chatted refused with `missing_dependency interview_plans: chat_ws` and offered no
  operator path to create it except starting a conversation. Fix: `init_db()` seeds
  `chat_ws` beside `default` (idempotent `INSERT OR IGNORE`; the lazy seed stays).

C and D are exactly the Phase 7 cutover case — restoring into a root that has never run —
and they would have been met there with real narrators. Pinned by
`DryRun.test_dependency_ids_are_matched_on_the_referenced_column_not_the_primary_key` and
`DryRun.test_clean_installation_owns_the_chat_plan_before_anyone_has_chatted`
(`tests/test_narrator_package_restore.py`, production-boundary: exporter ids on one side,
`init_db()`'s own seed on the other).

**Environment finding, not code:** `bagit` was pinned in `requirements-gpu.txt` but never
installed into `.venv-gpu`; the first Create was refused `bagit_not_installed` — a durable
*refused* job, "Nothing was written." — which is the right product behaviour and also the
first thing the Activity ledger recorded. Installed 1.8.1; the `pkg_resources` warning is
BACKLOG §5.

**Observations for 5b (presentation, deliberately not changed now):** the queued frame renders
an empty stage list until the server writes the first `progress_json` (the card invents no
stages); the Move view shows only the six stage names for a narrator this small because the
job outruns the 1 s poll; the confirmation `<dialog>` opens top-left rather than centred; the
upload registry is in-process, so a staged file survives an API restart without its record
(a start-up sweep of the staging directory is owed); the full-page reload always reopens the
picker (the app's behaviour, not the card's).

**Pre-existing behaviour observed, outside this WO:** opening a narrator appends **12
`bio_facts` rows every time** (Ada: 12 → 72 → 96 across the day's opens) and `interview_threads`
went 8 → 0 on open — the app's narrator-load hydration rewrites rows. The Data Center reported
each live count correctly; the growth is the product's, and it belongs in BACKLOG.

**Deployment note recorded on review (ChatGPT, 2026-09-11), not a 5a change:** the
one-operation-at-a-time guarantee is a process-local `threading.Lock`. The stack runs one
Uvicorn process, so the Phase 3 exclusivity assumption holds; a multi-worker deployment would
need a cross-process lock. Hardening, owed with deployment, documented in the router header.

**Cleanup, decided by Chris 2026-09-11 (his option 4).** The seven Ada rows are
WO-LORI-ARCHIVE-TO-MEMOIR-02 Block D fixtures (`scripts/phase6_populated_narrator.py`,
2026-09-09, `testing_only`), held by that lane's handoff — Phase 5a borrowed `8ec7a427` and
does not own it, so **none of the seven is erased here**; `8ec7a427`'s changed state is
recorded in that handoff's §7 addendum. Phase 5a removes only what it created: the clean root
`/mnt/c/hornelore_clean_5a`, the package copies on Desktop and in Downloads, the second
package's server copy (through Remove server copy, so the ledger says so), and any staging
residue. Retained by contract: the three `0056` job rows (one refused, two complete) and the
`.env` flag.

**Boundaries kept:** no narrator data deleted by any verb; the only removals were a staged
upload and a finished artifact, both outside `DATA_DIR`; `/mnt/c/hornelore_data` unchanged
except by the app's own narrator-open writes; `0054`/`0055`/`0056` untouched; model and
window untouched.
