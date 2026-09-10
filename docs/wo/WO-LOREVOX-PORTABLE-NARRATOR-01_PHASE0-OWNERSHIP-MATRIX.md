# WO-LOREVOX-PORTABLE-NARRATOR-01 — Phase 0: narrator-ownership matrix

**Status:** PHASE 0 COMPLETE 2026-09-10, desktop. Read-only. No product mutation.
**Evidence run:** `.runtime/eval/phase0-ownership-audit-20260910T015024Z/` (local, gitignored —
carries real-narrator counts, orphan ids and paths; this document carries only schema-level
facts). Instrument: `scripts/phase0_narrator_ownership_audit.py`.
**Database:** `/mnt/c/hornelore_data/db/hornelore.sqlite3`, opened `mode=ro`, `BEGIN IMMEDIATE`
refused by SQLite — proven. **Data root:** `/mnt/c/hornelore_data`. **Repo:** `main` at `8dea22b`
plus the instrument. 72 tables · 52 migrations · 107 people rows (11 not deleted).

**Machine scope (corrected 2026-09-10):** this desktop's data root is the only live data.
Phase 0 runs here and closes here. The laptop is a later deployment target, not an
evidence source. Lanes that are installed but empty here are mapped from schema, migrations,
`db.py`, erasure logic and path rules; a second machine is not invented as a prerequisite.

---

## 1. Ownership rules Phase 0 established — the findings

These are what Phase 1's contract must state. Each cites the line that reads the value.

**R1 — Three chains end at a column, not a constraint.** `turns → sessions` is a declared
FK; `sessions.person_id` was added by `ALTER` in `0044_sessions_person_id.sql` with no
foreign key. Likewise `interview_threads → interview_sessions.person_id` and
`import_candidate → photos.narrator_id`, and `trip_photo_day_placement_skips.trip_id →
trips.person_id` with no FK at all. **An export derived from the FK graph alone loses the
conversation** (`turns`, 23,652 rows). The contract names these hops explicitly.

**R2 — Twenty-eight tables exist outside the migration system**, created by `init_db()`
(`db.py`): `affect_events`, `bio_builder_questionnaires`, `facts`, `family_truth_notes`,
`family_truth_promoted`, `family_truth_rows`, `graph_persons`, `graph_relationships`,
`identity_change_log`, `interview_answers`, `interview_plans`, `interview_projections`,
`interview_questions`, `interview_sections`, `interview_sessions`, `life_phases`, `media`,
`media_attachments`, `narrator_delete_audit`, `profiles`, `rag_chunks`, `rag_docs`,
`safety_events`, `schema_migrations`, `section_summaries`, `segment_flags`,
`timeline_events`, `turns`. Half the narrator's world. `sessions` and `people` are also
`init_db()`-created and later altered (`sessions`: `conv_id`, `title`, `updated_at`,
`payload_json` appear in no migration). **Static derivation from migrations was never going
to be sufficient; this is why live inspection is primary.**

**R3 — `photos.image_path` and `photos.thumbnail_path` are absolute source-machine paths**
on every existing row (`/mnt/c/hornelore_data/memory/archive/photos/<pid>/…`).
`memory_archive_sessions.archive_dir` is already `DATA_DIR`-relative. §8.5 path rewriting is
required on Restore for every photo row that exists today, not a future-proofing.

**R4 — Travel, media and uploads are installed but empty here.** `trips` and every `trip_*`
table 0 rows; `trip_sources` and `import_staging` directories absent;
`media/archive/people` absent; `media/` and `uploads/` empty. **Their ownership contract is
still required and is derived from the schema**: every `trip_*` table chains to
`trips.person_id` (declared FKs through `trip_regions → trip_stops → trip_days`), and the
dynamic filesystem lanes resolve through rows exactly as `narrator_erasure._dynamic_plan`
does (`narrator_erasure.py:357-373`). Zero rows is a fact about this installation, not
about the lane.

**R5 — Narrator disposition is orthogonal to lane class.** `testing_only`, `narrator_type`
and `is_deleted` describe *whose* data it is; the classes in WO §5 describe *what kind*.
A `testing_only` narrator is exportable (Phases 2–4 round-trip on a synthetic Ada depends
on it). A soft-deleted narrator still owns rows and directories (§14). **No `test-fixture`
class is added.** Which narrators are *selected* for export is an operator decision at
export time, not an ownership class.

**R6 — Orphan directories exist and the database references at least one.** 185
directories under `memory/archive/people` carry ids matching no `people` row (count only
here; ids in the local report). One `memory_archive_sessions.archive_dir` value points into
one. Hard-delete residue or the April reset. **Classified in Phase 1; never deleted by
portability.**

**R7 — Dynamic lanes are proven through rows.** `trip_sources/<source-id>` via
`trip_sources.trip_id → trips.person_id`; `import_staging/<batch-id>` and
`import_staging/.incoming/<batch-id>` via `import_batch.person_id`. A per-person directory
walk cannot see them. Two `import_batch` rows exist here with their staging already cleaned.

**R8 — Installation state has a definite shape.** Guard Lab (`lori_guard_authority_override`,
`lori_guard_control_state`, migration `0053`), `bio_fields`, `timeline_context_events`,
`interview_plans/_sections/_questions`, `rag_docs/_chunks`, `narrator_delete_audit`,
`narrator_erasure_jobs`, `schema_migrations`. None travels (§5-E).

**R9 — Shared/family lanes exist and are empty:** `media_archive_family_lines`,
`media_archive_links`. §6 applies — reported, never duplicated into a narrator package.

**R10 — A stray 0-byte `hornelore.sqlite3` sits at the data-root top level**, beside the real
database under `db/`. Harmless; recorded so nobody resolves the database by name alone.

---

## 2. The matrix — every table in the live schema

Proof: **explicit** = named in `db.py::_EXTENDED_PERSON_SCOPED_TABLES` or
`narrator_erasure.py::_LANE_TABLES` · **FK→people** = declared FK to `people` · **FK child** =
declared FK chain to an owned table · **column only** = chain ends at a person column with no
FK (R1). Erasure: **explicit** as above · **cascade** = FK to `people` · **via parent** = FK child
of a cascaded table · **VERIFY** = column-only chain, coverage to be proven in Phase 1.
Archive Export = the current `memory_archive.py:634` ZIP. v1 = Portable Narrator v1.

| table | rows | ownership (proposed) | proof | erasure knows | Archive Export | v1 |
|---|---|---|---|---|---|---|
| `people` | 107 | narrator — identity | the row itself | cascade root | no | yes |
| `profiles` | 107 | narrator | FK→people + `person_id` | cascade | no | yes |
| `sessions` | 10,847 | narrator | explicit (lane) | explicit | no | yes |
| `turns` | 23,652 | narrator | **column only** → `sessions.person_id` (R1) | **VERIFY** | no | yes |
| `memory_archive_sessions` | 4 | narrator | explicit | explicit | files only | yes |
| `memory_archive_turns` | 24 | narrator | explicit | explicit | files only | yes |
| `interview_sessions` | 44 | narrator | FK→people + `person_id` | cascade | no | yes |
| `interview_threads` | 50 | narrator | **column only** → `interview_sessions.person_id` (R1) | **VERIFY** | no | yes |
| `interview_projections` | 59 | narrator | FK→people + `person_id` | cascade | no | yes |
| `interview_answers` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `bio_builder_questionnaires` | 59 | narrator | FK→people + `person_id` | cascade | no | yes |
| `bio_facts` | 997 | narrator | explicit | explicit | no | yes |
| `family_truth_notes` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `family_truth_rows` | 0 | narrator | FK child via `family_truth_notes` | via parent | no | yes |
| `family_truth_promoted` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `facts` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `graph_persons` | 1 | narrator | FK→people + `narrator_id` | cascade | no | yes |
| `graph_relationships` | 0 | narrator | FK child via `graph_persons` | via parent | no | yes |
| `identity_change_log` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `consent_attestations` | 16 | narrator | FK→people + `narrator_id` | cascade | no | yes (§15) |
| `profile_seed_onboarding` | 7 | narrator | FK→people + `person_id` | cascade | no | yes |
| `life_phases` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `timeline_events` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `story_candidates` | 113 | narrator | explicit | explicit | no | yes |
| `follow_up_bank` | 100 | narrator | explicit | explicit | no | yes |
| `section_summaries` | 0 | narrator | explicit | explicit | no | yes |
| `segment_flags` | 3 | narrator | FK child via `interview_sessions` | via parent | no | yes |
| `affect_events` | 0 | narrator | FK child via `interview_sessions` | via parent | no | yes |
| `safety_events` | 17 | narrator | explicit | explicit | no | yes (§14) |
| `turn_extraction_ledger` | 42 | narrator | explicit | explicit | no | yes |
| `turn_extraction_results` | 10 | narrator | explicit | explicit | no | yes |
| `photos` | 4 | narrator | explicit; `image_path` absolute (R3) | explicit | no | yes + rewrite |
| `photo_sessions` | 0 | narrator | explicit | explicit | no | yes |
| `photo_people` | 0 | narrator | explicit | explicit | no | yes |
| `photo_events` | 0 | narrator | FK child via `photos` | via parent | no | yes |
| `photo_session_shows` | 0 | narrator | FK child via `photos` | via parent | no | yes |
| `photo_memories` | 0 | narrator | FK child via `photo_session_shows` | via parent | no | yes |
| `import_batch` | 2 | narrator | explicit (lane) | explicit | no | yes |
| `import_candidate` | 4 | narrator | **column only** → `photos.narrator_id` (R1) | **VERIFY** | no | yes |
| `media` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `media_attachments` | 0 | narrator | FK→people + `person_id` | cascade | no | yes |
| `media_archive_items` | 0 | narrator | explicit | explicit | no | yes |
| `media_archive_people` | 0 | narrator | explicit | explicit | no | yes |
| `media_archive_family_lines` | 0 | **shared/family — decide (§6)** | no person link | no | no | decision |
| `media_archive_links` | 0 | **shared/family — decide (§6)** | no person link | no | no | decision |
| `trips` | 0 | narrator | explicit (lane) | explicit | no | yes |
| `trip_regions` | 0 | narrator | FK child via `trips` | via parent | no | yes |
| `trip_stops` | 0 | narrator | FK child via `trip_regions` | via parent | no | yes |
| `trip_days` | 0 | narrator | FK child via `trip_stops` | via parent | no | yes |
| `trip_themes` | 0 | narrator | FK child via `trips` | via parent | no | yes |
| `trip_location_notes` | 0 | narrator | FK child via `trip_days` | via parent | no | yes |
| `trip_bio_suggestions` | 0 | narrator | explicit | explicit | no | yes |
| `trip_story_links` | 0 | narrator | FK child via `trip_stops` | via parent | no | yes |
| `trip_sources` | 0 | narrator | explicit (lane); files via rows (R7) | explicit | no | yes |
| `trip_public_context` | 0 | narrator | FK child via `trips` | via parent | no | yes |
| `trip_photo_links` | 0 | narrator | FK child via `trip_days` | via parent | no | yes |
| `trip_photo_context` | 0 | narrator | FK child via `trip_photo_links` | via parent | no | yes |
| `trip_photo_day_placements` | 0 | narrator | FK child via `trip_days` | via parent | no | yes |
| `trip_photo_day_placement_skips` | 0 | narrator | **column only** → `trips.person_id` (R1) | **VERIFY** | no | yes |
| `trip_turn_links` | 0 | narrator | FK child via `trip_days` | via parent | no | yes |
| `lori_guard_authority_override` | 37 | installation (§5-E) | migration `0053` | n/a | no | **no** |
| `lori_guard_control_state` | 1 | installation (§5-E) | migration `0053` | n/a | no | **no** |
| `bio_fields` | 84 | installation (§5-E) | global schema definitions | n/a | no | **no** |
| `timeline_context_events` | 0 | installation (§5-E) | global curated library | n/a | no | **no** |
| `interview_plans` | 2 | installation | plan template, no person link | n/a | no | **no** |
| `interview_sections` | 0 | installation | plan template | n/a | no | **no** |
| `interview_questions` | 0 | installation | plan template | n/a | no | **no** |
| `rag_docs` | 0 | installation | retrieval store, no person link, unused | n/a | no | **no** |
| `rag_chunks` | 0 | installation | retrieval store | n/a | no | **no** |
| `narrator_delete_audit` | 267 | installation (§5-E audit) | `person_id` but audit authority | n/a | no | **no** |
| `narrator_erasure_jobs` | 0 | installation (§12) | job records, `0049`/`0050` | n/a | no | **no** |
| `schema_migrations` | 52 | installation | migration ledger | n/a | no | **no** |

**Counts:** 60 narrator-owned · 10 installation-owned · 2 shared/family (decision) · 0
unexplained. **4 column-only chains need erasure coverage VERIFIED in Phase 1**, and every
one of them is on the export side by the rule in R1.

## 3. Filesystem lanes

| lane | root (under `DATA_DIR`) | keyed by | proof | erasure | Archive Export | v1 |
|---|---|---|---|---|---|---|
| memory archive | `memory/archive/people/<pid>` | person id | `FIXED_TARGETS` | yes | **yes — the only lane it covers** | yes |
| captured stories | `stories-captured/<pid>` | person id | `FIXED_TARGETS` | yes | no | yes |
| photo archive | `memory/archive/photos/<pid>` | person id | `FIXED_TARGETS`; `photos.image_path` | yes | no | yes |
| personal media archive | `media/archive/people/<pid>` | person id | `FIXED_TARGETS` (absent here) | yes | no | yes |
| uploads | `media/<pid>` | person id | `FIXED_TARGETS` (empty here) | yes | no | yes |
| Kawa segments (historical) | `kawa/people/<pid>` | person id | `FIXED_TARGETS` | yes | no | yes (§5-C) |
| trip sources | `trip_sources/<source-id>` | **row** (R7) | `_dynamic_plan` | yes | no | yes |
| import staging | `import_staging/<batch-id>`, `.incoming/<batch-id>` | **row** (R7) | `_dynamic_plan` | yes | no | decision — staging is transient; §2.4 |
| translation cache | `translations-cache/` | shared | `SHARED_PURGE` | purge | no | no (§5-D) |
| TTS cache, `cache_audio`, `voices` | top level | installation | — | no | no | no |
| `backups/`, `exports/` | top level | historical | excluded by erasure | no | no | no |
| `test_lab/`, `interview/`, `projects/`, `templates/`, `logs/` | top level | installation / empty | — | no | no | no |

## 4. What Phase 1 receives

* This matrix, with 4 `VERIFY` rows to close against `narrator_erasure.build_plan` and the
  FK cascade actually declared (`ON DELETE` per table was not captured by Phase 0).
* Two `decision` rows (§6) and one (`import_staging`) that is transient by design.
* R1–R10 as the rules the single ownership declaration must encode.
* The local report for real counts, orphan ids and paths — read there, not copied here.

## 5. What Phase 0 did not do

Did not write to the database (proven). Did not import `api.db`. Did not walk `backups/`.
Did not hash. Did not decide the `decision` rows. Did not touch an orphan. Did not need, and
does not require, a second machine.
