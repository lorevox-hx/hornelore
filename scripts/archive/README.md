# scripts/archive/ — preserved but not part of normal start/stop

Everything in this folder was moved out of `scripts/` on 2026-04-25 to keep the
`scripts/` folder clean for shortcuts on the laptop. Nothing was deleted.

The `scripts/` root now contains:
- `start_all.sh`
- `stop_all.sh`
- `common.sh` (sourced by both — must stay alongside them)
- `start_api_visible.sh`, `start_tts_visible.sh`, `start_ui_visible.sh`,
  `restart_api_visible.sh`, `logs_visible.sh`, `status_all.sh` —
  **wired to the Windows launchers** in the repo root
  (`start_hornelore.bat`, `logs_hornelore.bat`). These were briefly
  archived on 2026-04-25 morning, then restored that evening when the
  Windows Terminal tabs started exiting with code 127 on launch.
  Do NOT re-archive without also rewriting the .bat files first.

## What's in here, organized by purpose

### Stack restart + restart variants

- `restart_api.sh` — restart the API only (after `.env` or code change)
- ~~`restart_api_visible.sh`~~ — RESTORED to `scripts/` (Windows launcher dependency)
- ~~`start_api_visible.sh`~~ — RESTORED to `scripts/` (Windows launcher dependency)
- ~~`start_tts_visible.sh`~~ — RESTORED to `scripts/` (Windows launcher dependency)
- ~~`start_ui_visible.sh`~~ — RESTORED to `scripts/` (Windows launcher dependency)
- ~~`status_all.sh`~~ — RESTORED to `scripts/` (called from `logs_visible.sh`)

### Diagnostic + log helpers

- ~~`logs_visible.sh`~~ — RESTORED to `scripts/` (Windows launcher dependency)
- `test_stack_health.sh` — check API/TTS/UI reachability + warmth
- `test_lab_doctor.sh` — diagnose stuck Test Lab runs
- `test_lab_watch.sh` — terminal live monitor for Test Lab
- `test_all.sh` — run repo unit tests
- `warm_llm.py` — pre-warm LLM
- `warm_tts.py` — pre-warm TTS

### Eval runners (extractor lane)

- `run_question_bank_extraction_eval.py` — **MASTER EVAL** (was at `./scripts/`)
  Used by the standard eval block in `CLAUDE.md`. Path moved.
- `run_stubborn_pack_eval.py` — stubborn-pack diagnostic eval
- `run_canon_grounded_eval.py` — canon-grounded eval runner
- `run_section_effect_matrix.py` — #95 SECTION-EFFECT Phase 3 matrix runner
- `run_memory_archive_smoke.py` — memory archive backend smoke test
- `failure_pack.py` — cluster-JSON sidecar for master eval

### Quality Harness

- `run_test_lab.sh` — full Quality Harness matrix
- `test_lab_runner.py` — Test Lab Python runner
- `test_lab_configs.json` — Test Lab config

### Seeding + one-time setup

- `seed_test_narrators.py` — synthetic test narrators (Quality Harness)
- `seed_interview_plan.py` — interview plan seeder
- `preload_trainer.py` — reference narrator preload (Shatner, Dolly)
- `import_kent_james_horne.py` — one-time Kent narrator import
- `setup_desktop.sh` — one-time desktop bring-up script
- `requirements.txt` — Python deps for these scripts

### Backup + restore

- `backup_lorevox_data.sh` — back up DATA_DIR
- `restore_lorevox_data.sh` — restore from backup

### Extractor debug

- `audit_canon_gaps.py` — canon-gap audit (#104)
- `dump_cases_per_narrator.py` — per-narrator eval case dump (#105)
- `debug_twopass_stage_loss.py` — TWOPASS regression debug (deferred lane)

## To use any of these from the new path

```bash
# was:
./scripts/run_question_bank_extraction_eval.py --mode live ...

# now:
./scripts/archive/run_question_bank_extraction_eval.py --mode live ...
```

Same applies to all other scripts in this folder. The standard eval block in
`CLAUDE.md` and the runbook in `HANDOFF.md` were updated 2026-04-25 to reflect
the new paths.

## To restore one back to scripts/ root

If you start using a script frequently and want it pinned at the root for
shortcuts, just `git mv scripts/archive/<name> scripts/<name>` and update any
doc references.
