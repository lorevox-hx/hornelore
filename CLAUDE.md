# CLAUDE.md — Hornelore Agent Env Notes

**Read this first at the start of every session.** These are persistent operational facts, not a task log.

## Environment

- **OS**: Windows 11 + WSL2 (Ubuntu). Chris works from WSL.
- **Repo path (WSL)**: `/mnt/c/Users/chris/hornelore` — NOT `~/hornelore`.
- **Agent workspace mount**: `/sessions/<session-id>/mnt/hornelore`. Edits here are live on Chris's repo.
- **GPU**: NVIDIA RTX 50-series (Blackwell). Local LLM serves from this machine.

## Stack ownership

- **Chris starts and stops the API and full stack himself.** Do NOT include `./scripts/start_all.sh` or `./scripts/stop_all.sh` in copy-paste blocks.
- The API is assumed to be running at `http://localhost:8000` whenever an eval is asked for.

## Standard eval command (copy-paste ready)

When asked to run or re-run a master eval, emit exactly this block, rotating the output suffix:

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_<SUFFIX>.json
grep "\[extract\]\[turnscope\]" .runtime/logs/api.log | tail -40
```

The eval script auto-writes `docs/reports/master_loop01_<SUFFIX>.console.txt` next to the JSON — no shell `| tee` needed (was silently producing 0-byte files under WSL pipe-buffer conditions; r4h's empty console triggered the fix on 2026-04-19).

Suffix convention: `r4f` = Patch F narrowing, `r4g` = WO-EX-TURNSCOPE-01 v1 (target hit, +2 compound-extract regressions), `r4h` = TURNSCOPE v2 (target hit, 060/062 restored, must_not_write=0 — **#72 CLOSED**; case_012/020 newly missing fields are LLM stochasticity, filter is provably no-op when extractPriority=None). Next: `r4i` = #67 holiday-date fix land.

The grep at the end rotates — change the tag to whatever filter is being tested (`turnscope`, `negation-guard`, `R4-E`, etc.) or drop it when not needed.

## Stubborn-pack diagnostic eval (copy-paste ready)

When the master eval moves but we need to know why stubborn cases (the frozen fail set) did or didn't shift, run this alongside. The master above stays the decision gate; this layer is diagnostic only.

```bash
cd /mnt/c/Users/chris/hornelore
HORNELORE_PROMPTSHRINK=1 ./scripts/run_stubborn_pack_eval.py \
  --tag <SUFFIX> \
  --runs 3 \
  --api http://localhost:8000 \
  --master docs/reports/master_loop01_<SUFFIX>.json
```

Writes `docs/reports/stubborn_pack_<SUFFIX>_run{1,2,3}.json` plus a cross-run `stubborn_pack_<SUFFIX>_stability.json` + `.console.txt`. The stability console includes the master topline (when `--master` supplied) and buckets the 15 stubborn cases into stable_pass / stable_fail / unstable with per-case VRAM-GUARD truncation flag, failure-category change count, and field-path shape-change flag across the 3 runs.

Stubborn pack (15 cases, fixed): `case_008, case_009, case_017, case_018, case_053, case_075, case_080, case_081, case_082, case_083, case_084, case_085, case_086, case_087, case_088`.

Drop the `HORNELORE_PROMPTSHRINK=1` prefix when running the legacy prompt path — the wrapper itself is env-flag-agnostic.

## Standard post-eval audit block

After every eval that follows a code change, report this exact block before declaring any movement real:

- total pass count
- v2 contract subset
- v3 contract subset
- must_not_write violations
- named affected cases (newly passed, newly failed)
- pass↔fail flips
- scorer-drift audit on every flip (eyeball the truth zones — does the score change reflect a real extraction change, or a scorer/expectation drift?)

## Where files live

| Kind | Path |
|---|---|
| API log | `/mnt/c/Users/chris/hornelore/.runtime/logs/api.log` |
| Eval JSON reports | `/mnt/c/Users/chris/hornelore/docs/reports/master_loop01_*.json` |
| Eval console readouts | `/mnt/c/Users/chris/hornelore/docs/reports/master_loop01_*.console.txt` |
| Stubborn-pack reports | `/mnt/c/Users/chris/hornelore/docs/reports/stubborn_pack_*.json` (+ `_stability.console.txt`) |
| Eval case source | `/mnt/c/Users/chris/hornelore/data/qa/question_bank_extraction_cases.json` |
| Extract router | `/mnt/c/Users/chris/hornelore/server/code/api/routers/extract.py` |
| WO specs | `/mnt/c/Users/chris/hornelore/WO-*_Spec.md` (repo root) |
| WO reports | `/mnt/c/Users/chris/hornelore/docs/reports/WO-*_REPORT.md` |
| SECTION-EFFECT Phase 1 output | `/mnt/c/Users/chris/hornelore/docs/reports/WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` (pending) |
| SECTION-EFFECT Phase 3 output | `/mnt/c/Users/chris/hornelore/docs/reports/WO-EX-SECTION-EFFECT-01_CAUSAL.md` (pending) |

All of these are readable from the agent workspace mount via the session prefix. After an eval runs, read the console + JSON directly — do not ask Chris to paste them.

## Current phase

**LOOP-01 R5.5 Phase 1 — SPANTAG spec sharpened, implementation paused behind SECTION-EFFECT-01.** R4 is closed. r4i is locked as the active post-R4 baseline (see `docs/reports/POST-R4-BASELINE-LOCK.md`). Next eval tag is **r5a**, not r4k.

Three-agent convergence on 2026-04-20 (Chris / Claude / ChatGPT) identified **section-conditioned schema coercion** as a distinct failure mode on the stubborn frontier (case_008, 009, 082). Today's single-pass extractor is forced to interpret + bind + commit-to-schema simultaneously while under pressure from `current_section` / `current_target_path`. The section context leaks into the projection because there's no way to tag evidence without committing to a field. SPANTAG's Pass 2 needs adjudicated truth labels and a payload extension (era/pass/mode) before its eval can be read cleanly. Hence #63 was promoted from cleanup to prerequisite.

Active sequence:

1. **#63 / WO-EX-SECTION-EFFECT-01** (prerequisite, BLOCKS SPANTAG). Phase 1: adjudicate stubborn-15 expected-truth labels into subject_only / section_only / dual_answer. Phase 2: thread `currentEra` / `currentPass` / `currentMode` from interview runtime into extraction payload + logs (today only `current_section` + `current_target_path` reach the backend). Phase 3: 2-3-case causal matrix varying stage context. Scorer policy gains `alt_defensible_paths`. #72-leftover retag `guard_false_positive` → `scope_escape` bundled. See `WO-EX-SECTION-EFFECT-01_Spec.md`.
2. **#90 / WO-EX-SPANTAG-01** — two-pass extraction: Pass 1 evidence-only NL tag inventory, Pass 2 bind/project with **section / target_path / era / pass / mode as explicit controlled priors** (not implicit forces). Subject-beats-section rule when Pass 1 binds a non-narrator relation_cue. Dual-path emission as first-class Pass 2 output. First target pack = the 15 stubborn cases, scored against SECTION-EFFECT-01-adjudicated labels. Flag `HORNELORE_SPANTAG=1`, off by default. **Implementation unblocks after SECTION-EFFECT-01 Phase 1 signoff.** See `WO-EX-SPANTAG-01_Spec.md`.
3. **Post-SPANTAG gate** — if SPANTAG ships default-on, R5.5 Pillar 2 (entity-role binding) opens. If it doesn't, iterate SPANTAG or revisit.

Each WO above must report the standard audit block (extended with `truncation_rate`) before being called done.

**Closed:**
- **#72 / WO-EX-TURNSCOPE-01** (r4h: case_094 pass, 060/062 restored, must_not_write=0).
- **#67 / WO-EX-PATCH-H-DATEFIELD-01** (r4i: case_011 + case_012 green).
- **#68 / case_053 wrong-entity** — disposition memo, deferred to R6 Pillar 2.
- **#81 / WO-EX-PROMPTSHRINK-01** — measured at r4j, **not adopted**. r4j produced one regression (`case_012` green→red via schema_gap/spouse-DOB fabrication) and zero gains. 15/15 stubborn-pack truncation across 3 runs showed the frontier is truncation-dominated, not prompt-verbosity-dominated. Flag stays in-tree (`HORNELORE_PROMPTSHRINK=1`) for possible SPANTAG Pass 2 pairing. See `WO-EX-PROMPTSHRINK-01_Spec.md` Disposition section.

**Deferred (long tail):**
- Hermes 3 / Qwen A/B — sequenced *after* SPANTAG signoff to keep attribution clean (see SPANTAG spec Appendix A).
- KORIE staged-pipeline (detection/OCR/IE) — conditional on SPANTAG delivering ≥20% topline lift or ≥3 stubborn flips (Appendix B).
- #35 V4 scope axes, R6 Pillars 2 & 3.

## Chris's working preferences

- Honest critique over flattery. Push back on ideas when warranted.
- Tight readouts, not walls of text.
- Do NOT relitigate things already decided.
- When three agents (Claude/Gemini/ChatGPT) converge on the same answer, act on it; don't re-argue.
- Do not regenerate command blocks from memory — copy from this file.
- Read logs and reports directly from the workspace mount; don't ask Chris to paste.

## Changelog

- 2026-04-19: Created. Captures WSL path correction and eval-command template.
- 2026-04-19 (late): r4h confirms WO-EX-TURNSCOPE-01 closes. Eval script now auto-writes `.console.txt` (shell `| tee` dropped after r4h produced an empty file). Standard post-eval audit block codified. #67 staged but not yet landed.
- 2026-04-19 (later): #67 landed (r4i: 55/104, case_011 + case_012 flipped green). #68 disposition memo written and deferred to R5 Pillar 2. #81 PROMPTSHRINK patch landed behind `HORNELORE_PROMPTSHRINK=1` flag — topic-scoped dynamic few-shot selection (3–8 per call vs 33 static), legacy path byte-stable when flag off. Stubborn-pack diagnostic wrapper added (`scripts/run_stubborn_pack_eval.py`) — 15-case pack, 3 runs, VRAM-GUARD truncation attribution, stable_pass/stable_fail/unstable buckets. Next eval = `r4j` = master + stubborn-pack with PROMPTSHRINK on.
- 2026-04-20: r4j measured (54/104, one regression `case_012`, 15/15 stubborn truncation). **PROMPTSHRINK closed as "measured, not adopted"**; flag stays off by default, in-tree for possible SPANTAG Pass 2 pairing. **r4i locked** as active baseline (`POST-R4-BASELINE-LOCK.md`). **#82 post-R4 memo** written. **WO-EX-SPANTAG-01 rewritten** from single-pass stub to two-pass (evidence + bind). Then three-agent convergence (Chris / Claude / ChatGPT) flagged **section-conditioned schema coercion** as a distinct failure mechanism on case_008 / 009 / 082 — SPANTAG spec sharpened with explicit controlled-prior inputs + subject-beats-section rule + first-class dual-path emission. **#63 promoted** from cleanup to prerequisite WO (WO-EX-SECTION-EFFECT-01): adjudicate stubborn-15 labels, extend extraction payload with `currentEra`/`currentPass`/`currentMode`, run causal matrix. **SPANTAG implementation paused** pending SECTION-EFFECT-01 Phase 1 signoff.
- 2026-04-20 (later): **#92 SECTION-EFFECT Phase 1** landed (`WO-EX-SECTION-EFFECT-01_ADJUDICATION.md` + `alt_defensible_paths` patched into cases_008/009/018/082). Classification tally: truncation_starved 7, dual_answer_defensible 4, scorer_drift_suspect 2, subject_only_defensible 1, wrong_entity_bind 1, section_only_misapplied 0. **SPANTAG spec narrowed** — primary sub-pack is 4 cases, not 15; ship-blocker on #94. **#94 SECTION-EFFECT scorer policy** landed — scorer credits `alt_defensible_paths` on must_extract zones (value must still fuzzy-match ≥0.5); classifier adds `defensible_alt_credit` (informative, non-penal). r4i re-scored with patched scorer: 55/104 → 57/104 (+2: case_008, case_009); 0 crashes; 0 newly-failing. **#93 SECTION-EFFECT Phase 2** landed — life-map stage fields (`current_era` / `current_pass` / `current_mode`) threaded from interview runtime (`ui/js/interview.js` reads `state.session`) through extraction payload (`ExtractFieldsRequest`) into `[extract]` log lines (attempt + summary both carry era/pass/mode now). Eval harness synthesizes stage context per case via new `_phase_to_era()` mapping (all 104 cases mapped cleanly, no unmapped phases). Pure plumbing; no extractor-behavior change. Next tag = **r5a** (master with life-map logs; Phase 3 causal matrix is #95).
