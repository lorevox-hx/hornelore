# Scripts index — executable status, derived rather than assumed

**Baseline derived at:** `d0e52946aa77096841612df176f4cbb70d4edacd`
**Maintained live** by `WO-REPOSITORY-HYGIENE-01`. The inventory below — population, states,
in-refs — is a **measurement taken at `d0e5294`** and is not re-derived on every edit; Step 2b
later repointed nine evidence cells without changing any classification. **Treat the numbers
as dated evidence, not as live truth**, and re-derive when it matters:

```bash
git ls-tree -r --name-only origin/main -- scripts | wc -l
```

**Population at `d0e5294`:** 127 tracked files — 95 under `scripts/`, 32 under `scripts/archive/`
**Status:** no script has been moved, renamed, repaired or deleted.

---

## 1. The finding this index exists to record

> `scripts/archive/` is **not** a genuine inert archive.

It holds currently documented eval runners, backup and restore tools, a retired evaluator
kept for reproduction, Test Lab files, one-time import utilities, and historical
diagnostics — mixed together under a directory name that reads as "dead". **Nothing under
`scripts/archive/` may be bulk-deleted or assumed dead**, and the canonical eval command in
`CLAUDE.md` points *into* it:

```bash
./scripts/archive/run_question_bank_extraction_eval.py --mode live ...
```

A directory called `archive/` that the primary evaluation command depends on is a naming
defect, not an archive. Renaming it is future work with its own review; this index is the
prerequisite, because you cannot safely rename what you have not classified.

---

## 2. How state was derived, and where it stops

Every row below carries **evidence**, not an opinion. The columns:

* **Last change** — committer month of the most recent commit touching the file.
* **In-refs** — how many *other tracked files* mention this script by basename or path.
  Computed over 1,081 tracked text files. Untracked material is excluded, so a script
  invoked only from `docs/reports/` (gitignored) or from an operator's shell history
  counts as zero. **Zero in-refs is a question, not a verdict.**
* **State** — derived by rule:

| State | Rule | Count |
|---|---|---:|
| `**BROKEN**` | fails `py_compile` | 1 |
| `current acceptance` | named as an acceptance gate in `CLAUDE.md` | 1 |
| `operational` | referenced by a `.bat` launcher or a `start_`/`stop_`/`status_` script | 14 |
| `one-time setup` | lives under `scripts/setup/` | 7 |
| `package` | `__init__.py` | 1 |
| `UNREFERENCED — adjudicate` | no incoming reference from any tracked file | 10 |
| `referenced — classify` | referenced, but purpose not derivable mechanically | 93 |

**93 of 127 are `referenced — classify`, and that is the honest answer, not a gap.** The
audit's own ruling applies: *"Eighteen non-package files have no incoming current-tree
reference. That is not enough evidence to delete a command-line tool."* A last-change date
and a reference count cannot distinguish a supported legacy tool from a historical one.
That distinction needs a human who knows what the tool was for, and it is exactly the work
the repository-hygiene work order schedules.

**No script moves on the strength of this table alone.** The rule for a move is the one the
audit set: *move only tools whose purpose and replacement are both named.*

### On the unreferenced count

This index derives **10**; the audit reports **18** non-package files with no incoming
reference. Both are defensible and the methods differ — this pass matches basename *or*
full path across all tracked text files, which finds references the stricter method
misses. Neither number authorizes a deletion. The 10 are marked for adjudication below.

---

**Evidence that moved, 2026-08-28.** Nine rows below cite the agent changelog. Their
evidence now lives in the archived snapshot, and the cells point there. **No classification
and no in-refs count changed** — a script's status does not depend on where its evidence
file sits, and re-deriving those numbers because a document moved would be the wrong
lesson.

---

## 3. Must not move, and why

* **`scripts/run_mutation_gate.py`** — the reproducible acceptance gate; every anchor is
  checked in. Moving it breaks every acceptance claim in the Profile Seed lane. **The
  mutation count is derived, not written here** — it was "63" and has grown since:

  ```bash
  cd /mnt/c/Users/chris/hornelore
  grep -c '^    Mutation(' scripts/run_mutation_gate.py
  ```
* **`scripts/step6_ws_probe.py`** — the Profile Seed Step 6 **live acceptance instrument**,
  and the evidence for an accepted step. It creates one clearly synthetic narrator through
  the product endpoint, drives five turns over the production WebSocket, and verifies the
  committed metadata, the durable advance and the reconnect. **It has no deletion path at
  all** and refuses to run if its narrator already exists. Identities are a closed registry
  of two selected by `STEP6_PROBE`, never free text, because a script that creates
  narrators and drives live turns must not accept a name that could match a real one.
  Chris runs it; it needs the serving stack.
* **The eval runners under `scripts/archive/`** — `run_question_bank_extraction_eval.py`
  and `run_stubborn_pack_eval.py` are the commands `CLAUDE.md` prints verbatim.
* **Launchers and their dependencies** — `start_all.sh`, `stop_all.sh`, `status_all.sh`,
  the `.bat` files at the repository root, and everything they call. Chris starts and
  stops the stack himself; a broken launcher path is a broken working day.
* **`scripts/harness/`** — imported as a package by the eval runners.

---

## 4. The one broken script

`scripts/ui/run_test23_two_person_resume.py` — `IndentationError` at line 2082, from
`df82215` (2026-05-06). **Test 23 has not run since.** It is the only Python parse failure
in the tracked tree, confirmed by byte-compiling every tracked `.py`.

Recorded, deliberately not repaired: [`../BUG-HARNESS-TEST23-INDENTATION-01_Spec.md`](../BUG-HARNESS-TEST23-INDENTATION-01_Spec.md).

The interesting part is not the file. It is that **nothing in the ordinary test path
compiles it**, so a harness stopped parsing and stayed silent for three and a half months.
The repair owes a compile gate over `scripts/` and `tests/`, which is the only part that
prevents a recurrence.

---

## 5. Test Lab — a separate bounded lane, and do not "fix" it in passing

The live Test Lab router points at root script paths that do not exist. **Repointing it at
`scripts/archive/` is known to fail after returning a false success** — the archived
harness is not location-aware, so the naive fix produces a green result and a broken
feature, which is worse than the current loud 500.

Do not touch it during archive cohorts. It gets its own work order, its own evidence, and
its own review.

---

## 6. Tooling defects that are repairs, not archival

Recorded here because they are *about* scripts and configuration; each belongs in a bounded
tooling commit, and none may be hidden by moving the configuration into an archive:

* `package.json` `main` names a nonexistent `tailwind.config.js`;
* `package.json` `license` says `ISC`; `LICENSE` is the Lorevox Source-Available
  Proprietary License;
* **7 npm script entries** reference **4 distinct nonexistent** Playwright specs —
  `test:break`, `test:break:headed`, `test:timeline`, `test:memory`, `test:projection`,
  `test:q3`, `test:q3:headed`;
* `playwright.config.ts` invokes a nonexistent `scripts/start-lorevox-audit.sh`.

All four reproduce at `d0e5294`. See [`../docs/BACKLOG.md`](../docs/BACKLOG.md).

---

## 7. Inventory

Sorted by path. `scripts/archive/` is included and is **not** to be read as a dead cohort.

<!-- BEGIN GENERATED INVENTORY — derived from `git ls-tree` + a reference scan over 1,081 tracked text files -->
| Script | Last change | In-refs | State | Example referrer |
|---|---|---:|---|---|
| `scripts/archive/README.md` | 2026-08 | 22 | referenced — classify | `CLAUDE.md` |
| `scripts/archive/audit_canon_gaps.py` | 2026-04 | 1 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/backup_lorevox_data.sh` | 2026-04 | 3 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/debug_twopass_stage_loss.py` | 2026-04 | 1 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/dump_cases_per_narrator.py` | 2026-04 | 1 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/failure_pack.py` | 2026-04 | 3 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/golfball_narrator_isolation.py` | 2026-07 | 2 | referenced — classify | `scripts/gate7_phase2_acceptance.py` |
| `scripts/archive/golfball_style_diff.py` | 2026-04 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/archive/hornelore_prompt_sections_readonly.py` | 2026-08 | 1 | referenced — classify | `docs/architecture/LEAN-LORI-RUNTIME-SPEC-FINAL-R3-2026-08-04.md` |
| `scripts/archive/import_kent_james_horne.py` | 2026-04 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/lean_lori_safety_gate_readonly.py` | 2026-08 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/archive/preload_trainer.py` | 2026-04 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/requirements.txt` | 2026-04 | 6 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/restart_api.sh` | 2026-04 | 5 | operational | `reload_api.bat` |
| `scripts/archive/restore_lorevox_data.sh` | 2026-04 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/run_canon_grounded_eval.py` | 2026-04 | 2 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/run_golfball_interview_eval.py` | 2026-05 | 10 | referenced — classify | `scripts/archive/golfball_narrator_isolation.py` |
| `scripts/archive/run_memory_archive_smoke.py` | 2026-04 | 3 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/run_question_bank_extraction_eval.py` | 2026-08 | 31 | referenced — classify | `CLAUDE.md` |
| `scripts/archive/run_section_effect_matrix.py` | 2026-04 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/run_sentence_diagram_story_survey.py` | 2026-05 | 4 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/archive/run_stubborn_pack_eval.py` | 2026-04 | 8 | referenced — classify | `CLAUDE.md` |
| `scripts/archive/run_test_lab.sh` | 2026-04 | 11 | referenced — classify | `HANDOFF.md` |
| `scripts/archive/seed_interview_plan.py` | 2026-04 | 2 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/seed_test_narrators.py` | 2026-08 | 9 | referenced — classify | `HANDOFF.md` |
| `scripts/archive/setup_desktop.sh` | 2026-04 | 1 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/test_all.sh` | 2026-04 | 1 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/test_lab_configs.json` | 2026-04 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/test_lab_doctor.sh` | 2026-04 | 3 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/test_lab_runner.py` | 2026-04 | 8 | referenced — classify | `HANDOFF.md` |
| `scripts/archive/test_lab_watch.sh` | 2026-04 | 3 | referenced — classify | `scripts/archive/README.md` |
| `scripts/archive/test_stack_health.sh` | 2026-04 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/audit_identity_preflight.py` | 2026-07 | 4 | referenced — classify | `scripts/wipe_narrator_identity.py` |
| `scripts/audit_legacy_questionnaire_backfill.py` | 2026-06 | 1 | referenced — classify | `docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md` |
| `scripts/backup_before_migration.sh` | 2026-07 | 1 | referenced — classify | `scripts/wipe_narrator_identity.py` |
| `scripts/cleanup_test_narrators.py` | 2026-08 | 3 | referenced — classify | `scripts/wipe_narrator_identity.py` |
| `scripts/common.sh` | 2026-06 | 22 | operational | `scripts/archive/README.md` |
| `scripts/eval/run_lori_behavior_harness.py` | 2026-04 | 2 | referenced — classify | `docs/archive/workorders-pre-pivot/WO-LORI-BEHAVIOR-HARNESS-01_Spec.md` |
| `scripts/gate7_phase2_acceptance.py` | 2026-08 | 2 | referenced — classify | `tests/test_gate7_acceptance_predicates.py` |
| `scripts/harness/__init__.py` | 2026-08 | 20 | package | `scripts/run_mutation_gate.py` |
| `scripts/harness/extraction_scoring.py` | 2026-08 | 3 | referenced — classify | `scripts/archive/README.md` |
| `scripts/harness_lib.py` | 2026-06 | 13 | referenced — classify | `scripts/regrade_harness_reports.py` |
| `scripts/logs_visible.sh` | 2026-04 | 6 | operational | `logs_hornelore.bat` |
| `scripts/monitor/stack_resource_logger.py` | 2026-04 | 3 | referenced — classify | `docs/archive/workorders-pre-pivot/WO-OPS-VRAM-VISIBILITY-01_Spec.md` |
| `scripts/narrative_cue_detector_repl.py` | 2026-05 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/one_shot_kent_fort_ord_long.py` | 2026-05 | 4 | referenced — classify | `scripts/replay_kent_fortord_then_nike_multiturn.py` |
| `scripts/probe_trip_lane_post_1e388b5.sh` | 2026-07 | 1 | referenced — classify | `tests/test_probe_trip_lane_script.py` |
| `scripts/regrade_boris_reports.py` | 2026-06 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/regrade_harness_reports.py` | 2026-06 | 1 | referenced — classify | `BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01_Spec.md` |
| `scripts/replay_kent_arc.py` | 2026-05 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/replay_kent_deep_witness.py` | 2026-05 | 3 | referenced — classify | `scripts/set_session_language_mode.py` |
| `scripts/replay_kent_fortord_then_nike_multiturn.py` | 2026-05 | 1 | referenced — classify | `docs/archive/handoffs-pre-pivot/HANDOFF_2026-05-12_to_2026-06-10.md` |
| `scripts/restart_api_visible.sh` | 2026-04 | 3 | operational | `reload_api.bat` |
| `scripts/run_alex_they_long_narration_harness.py` | 2026-06 | 3 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_boris_quality_tests.sh` | 2026-06 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/run_factual_chain_capture_smoke.py` | 2026-06 | 3 | referenced — classify | `BUG-LORI-THEMATIC-TRIP-CHAIN-DETECTION-01_Spec.md` |
| `scripts/run_factual_chain_live_harness.py` | 2026-06 | 9 | referenced — classify | `scripts/run_trip_route_canary_harness.py` |
| `scripts/run_jake_long_narration_harness.py` | 2026-06 | 4 | referenced — classify | `scripts/harness_lib.py` |
| `scripts/run_john_baldy_full_diagnostic_harness.py` | 2026-06 | 2 | referenced — classify | `docs/BORIS_FULL_TEST_SUITE_REVIEW.md` |
| `scripts/run_john_baldy_master_check.py` | 2026-06 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/run_john_baldy_seven_era_harness.py` | 2026-06 | 1 | referenced — classify | `scripts/run_john_baldy_master_check.py` |
| `scripts/run_lori_behavior_pack.py` | 2026-05 | 1 | referenced — classify | `docs/archive/workorders-pre-pivot/WO-EX-SENTENCE-DIAGRAM-STORY-SURVEY-01_Spec.md` |
| `scripts/run_mutation_gate.py` | 2026-08 | 5 | current acceptance | `docs/wo/WO-LORI-PROFILE-SEED-REACHABILITY-01_PHASE2_TRANSPORT_MAP.md` |
| `scripts/run_narrative_cue_eval.py` | 2026-05 | 6 | operational | `start_hornelore_loricue.bat` |
| `scripts/run_narrator_product_harness.py` | 2026-08 | 4 | referenced — classify | `scripts/archive/README.md` |
| `scripts/run_pat_teacher_betty_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_regional_african_american_georgia_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_regional_asian_american_california_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_regional_crypto_jewish_new_mexico_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_regional_hispano_tex_mex_harness.py` | 2026-06 | 1 | referenced — classify | `data/qa/narrator_product_personas_v1.json` |
| `scripts/run_regional_native_american_new_mexico_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_richard_late_coming_out_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_seven_era_walk_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_shatner_long_narration_harness.py` | 2026-06 | 2 | referenced — classify | `scripts/run_john_baldy_full_diagnostic_harness.py` |
| `scripts/run_spanish_live_smoke.py` | 2026-06 | 3 | referenced — classify | `BUG-ML-SPANISH-DETECT-FRENCH-PLACE-OVERFIRE-01_Spec.md` |
| `scripts/run_trip_2019_france_italy_canary_harness.py` | 2026-06 | 4 | referenced — classify | `BUG-LORI-THEMATIC-TRIP-CHAIN-DETECTION-01_Spec.md` |
| `scripts/run_trip_route_canary_harness.py` | 2026-06 | 10 | referenced — classify | `scripts/run_factual_chain_live_harness.py` |
| `scripts/run_utterance_frame_survey.py` | 2026-05 | 4 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/seed_timeline_context_events.py` | 2026-05 | 3 | referenced — classify | `docs/archive/handoffs-pre-pivot/MASTER_WORK_ORDER_CHECKLIST.md` |
| `scripts/set_narrator_overlay.py` | 2026-08 | 3 | referenced — classify | `scripts/stress_kent_full_arc.py` |
| `scripts/set_session_language_mode.py` | 2026-05 | 9 | referenced — classify | `scripts/set_narrator_overlay.py` |
| `scripts/setup/apply_june_env_parity.sh` | 2026-06 | 0 | one-time setup | — |
| `scripts/setup/apply_kokoro_safety_env.sh` | 2026-05 | 1 | one-time setup | `scripts/setup/apply_june_env_parity.sh` |
| `scripts/setup/audit_travel_doc_evidence.sh` | 2026-07 | 0 | one-time setup | — |
| `scripts/setup/flip_kokoro_test.sh` | 2026-05 | 0 | one-time setup | — |
| `scripts/setup/install_kokoro.sh` | 2026-05 | 5 | one-time setup | `scripts/setup/smoke_kokoro.py` |
| `scripts/setup/install_travel_doc_evidence.sh` | 2026-07 | 0 | one-time setup | — |
| `scripts/setup/smoke_kokoro.py` | 2026-05 | 4 | one-time setup | `scripts/setup/install_kokoro.sh` |
| `scripts/start_all.sh` | 2026-06 | 37 | operational | `CLAUDE.md` |
| `scripts/start_all_media_archive_dev.sh` | 2026-04 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/start_all_photos_dev.sh` | 2026-04 | 2 | operational | `scripts/start_all_media_archive_dev.sh` |
| `scripts/start_api_visible.sh` | 2026-04 | 8 | operational | `reload_api.bat` |
| `scripts/start_tts_visible.sh` | 2026-04 | 4 | operational | `scripts/archive/README.md` |
| `scripts/start_ui_visible.sh` | 2026-04 | 4 | operational | `scripts/archive/README.md` |
| `scripts/status_all.sh` | 2026-04 | 5 | operational | `scripts/archive/README.md` |
| `scripts/stop_all.sh` | 2026-06 | 16 | operational | `CLAUDE.md` |
| `scripts/stress_kent_full_arc.py` | 2026-05 | 1 | referenced — classify | `docs/archive/handoffs-pre-pivot/HANDOFF_2026-05-12_to_2026-06-10.md` |
| `scripts/tail_harness_log.sh` | 2026-06 | 3 | referenced — classify | `BUG-CHATWS-CONV-FK-01_Spec.md` |
| `scripts/test_photo_exif.py` | 2026-04 | 5 | referenced — classify | `docs/archive/handoffs-pre-pivot/HANDOFF.md` |
| `scripts/ui/README.md` | 2026-07 | 22 | referenced — classify | `CLAUDE.md` |
| `scripts/ui/run_chronology_connection_behaviour.js` | 2026-08 | 3 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/ui/run_extraction_result_consumer.js` | 2026-07 | 1 | referenced — classify | `tests/test_extraction_result_delivery.py` |
| `scripts/ui/run_lazy_thumb_scrollport.js` | 2026-08 | 4 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/ui/run_memoir_canonical_lifecycle.js` | 2026-08 | 1 | referenced — classify | `tests/test_memoir_canonical_contract.py` |
| `scripts/ui/run_narrator_context_behaviour.js` | 2026-08 | 3 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/ui/run_parent_session_readiness_harness.py` | 2026-05 | 9 | referenced — classify | `scripts/ui/README.md` |
| `scripts/ui/run_parent_session_rehearsal_harness.py` | 2026-05 | 7 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/ui/run_photo_palette_behaviour.js` | 2026-08 | 6 | referenced — classify | `HANDOFF.md` |
| `scripts/ui/run_photo_placement_safety.js` | 2026-08 | 4 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/ui/run_photo_window_arithmetic.js` | 2026-08 | 5 | referenced — classify | `HANDOFF.md` |
| `scripts/ui/run_photo_window_liveness.js` | 2026-08 | 3 | referenced — classify | `scripts/ui/run_photo_window_arithmetic.js` |
| `scripts/ui/run_safety_latch_exit_check.js` | 2026-08 | 1 | referenced — classify | `tests/test_safety_parked.py` |
| `scripts/ui/run_story_evidence_behaviour.js` | 2026-08 | 2 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/ui/run_test23_two_person_resume.py` | 2026-05 | 8 | **BROKEN** | `HANDOFF.md` |
| `scripts/ui/run_travel_doc_mount_liveness.js` | 2026-07 | 7 | referenced — classify | `scripts/ui/README.md` |
| `scripts/ui/run_travel_doc_preview_race_check.js` | 2026-08 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/ui/run_travel_doc_shell_mount_liveness.js` | 2026-07 | 5 | referenced — classify | `scripts/ui/README.md` |
| `scripts/utterance_frame_repl.py` | 2026-05 | 4 | referenced — classify | `scripts/narrative_cue_detector_repl.py` |
| `scripts/validate_timeline_context_events.py` | 2026-05 | 4 | referenced — classify | `scripts/seed_timeline_context_events.py` |
| `scripts/verify_chain_meta_persistence.py` | 2026-08 | 5 | referenced — classify | `scripts/run_factual_chain_live_harness.py` |
| `scripts/verify_factual_chain_wire.py` | 2026-06 | 0 | UNREFERENCED — adjudicate | — |
| `scripts/vs1_trip_companion_acceptance.py` | 2026-07 | 1 | referenced — classify | `tests/test_trip_story_capture.py` |
| `scripts/warm_llm.py` | 2026-04 | 10 | operational | `scripts/archive/README.md` |
| `scripts/warm_tts.py` | 2026-04 | 4 | operational | `scripts/archive/README.md` |
| `scripts/wipe_narrator_identity.py` | 2026-07 | 2 | referenced — classify | [`docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md`](../docs/archive/changelogs/CHANGELOG-AGENT-through-2026-08-20.md) |
| `scripts/wo02_acceptance.py` | 2026-08 | 6 | referenced — classify | `docs/archive/handoffs/HANDOFF_2026-07-31_TRIP-NARRATOR-BRIDGE.md` |
| `scripts/wo_narrator_bridge_acceptance.py` | 2026-08 | 6 | referenced — classify | `docs/architecture/LEAN-LORI-RUNTIME-SPEC-FINAL-R3-2026-08-04.md` |
<!-- END GENERATED INVENTORY -->
