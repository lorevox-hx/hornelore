# WO-LOREVOX-PORTABLE-NARRATOR-01

**Portable Narrator Package, Restore, and Clean Lorevox Cutover**

**Opened:** 2026-09-09
**Status:** APPROVED IN ARCHITECTURE 2026-09-09 — implementation begins with Phase 0
only (read-only ownership audit). No exporter, importer or deletion is authorized by
this document alone.
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
Lorevox DB with no missing lane.**

**Phase 4 — Round-trip equivalence.** original → export A → empty Lorevox → restore →
export B → compare, separately for DB rows, files, binary hashes, transcripts, audio,
photos, documents, travel, structured memory, story / review state, timeline,
provenance. Volatile package / job metadata excluded explicitly. **Exit gate: A and the
restored state are equivalent for every authoritative / portable lane.**

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
only when desired. **See §27.6–27.7 for the required runtime gate.**

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
holds export, validate, dry-run and restore. The operator UI (§16) and a thin
`scripts/narrator_package.py {validate|export|restore}` recovery CLI both call it.
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
itself was exercised. The three runs before it failed inside the fixture (a `TEXT PRIMARY
KEY` reported `notnull=0`, so no ids were minted; `trip_location_notes` rebuilt by `0019`;
a `%`-formatted bytes literal; the `0039:161` one-link-per-assistant-turn UNIQUE) and
touched no exporter line. `tests.test_narrator_data_inventory_parity` 15/15 and
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
