# CLAUDE.md — Hornelore Agent Env Notes

**Read this first at the start of every session.** These are persistent operational facts, not a task log.

## Environment

- **OS**: Windows 11 + WSL2 (Ubuntu). Chris works from WSL.
- **Repo path (WSL)**: `/mnt/c/Users/chris/hornelore` — NOT `~/hornelore`.
- **Agent workspace mount**: `/sessions/<session-id>/mnt/hornelore`. Edits here are live on Chris's repo.
- **Git is NOT accessible from the sandbox mount.** `git status`, `git add`, `git commit`, `git diff --stat`, `git log` from the sandbox either fault with "not a git repository" or "unable to read <oid>". This is permanent — do not retry. File reads and edits work; only the git tooling is broken. All commit/branch/log operations must be handed to Chris as copy-paste blocks that he runs from `/mnt/c/Users/chris/hornelore`.
- **GPU**: NVIDIA RTX 50-series (Blackwell). Local LLM serves from this machine.

## Stack ownership

- **Chris starts and stops the API and full stack himself.** Do NOT include `./scripts/start_all.sh` or `./scripts/stop_all.sh` in copy-paste blocks.
- The API is assumed to be running at `http://localhost:8000` whenever an eval is asked for.
- **Cold boot takes ~4 minutes** — the HTTP listener comes up in ~60–70s but the LLM weights + extractor warmup continue for another 2–3 minutes after that. A `curl /` health check is NOT sufficient; it only proves the socket is listening, not that the extractor can serve a real request in <30s. This is why Chris owns start/stop: the agent-run combined blocks that restart the stack and immediately kick off evals cold-start the first case into a 90s read-timeout (observed on cg_001 during narrative-field r5c, 2026-04-21).
- If Chris ever explicitly asks for a combined restart+eval block, gate the eval behind an extractor-warmup probe (POST a trivial extract and loop until round-trip is <30s), not a bare `curl /` loop.

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

**LOOP-01 R5.5 Phase 1 — NARRATIVE-FIELD-01 closed, r5e1 locked as the active performance floor.** R4 is closed (r4i baseline locked, see `POST-R4-BASELINE-LOCK.md`). R5.5 evals r5a → r5e1 landed over 2026-04-20 → 2026-04-21; r5e2 attribution-boundary experiment (2026-04-21) was REJECTED — see evening changelog entry for full detail. SPANTAG implementation still paused behind SECTION-EFFECT-01 Phase 3 (#95).

**Active baseline: r5e1 (59/104, v3=38/62, v2=32/62, mnw=2).** Known cost of the baseline is two mnw offenders: `case_035` (faith turn, `education.schooling` narrator-leak) and `case_093` (spouse-detail follow-up, `education.higherEducation` narrator-leak). Three-agent convergence (Chris / Claude / ChatGPT, 2026-04-21) chose to accept those two as the known cost rather than keep the r5e2 ATTRIBUTION-BOUNDARY rule on — r5e2 cleared mnw but friendly-fired on 7 clean passes including case_075 (the rule's own target class). The ATTRIBUTION-BOUNDARY exemplar block stays in-tree behind the default-off `HORNELORE_ATTRIB_BOUNDARY=1` flag for reference / future diagnostics; default live behavior is byte-identical to r5e1.

The real fix for the attribution/ownership class is now planned as **WO-LORI-CONFIRM-01** (parked spec, repo root) — interview-engine confirm pass + kinship skeleton block. Elicitation-side, not prompt-side. Sequenced behind SECTION-EFFECT Phase 3 + SPANTAG default-on/off decision so extractor accountability doesn't get blurred.

Active sequence:

1. **#63 / WO-EX-SECTION-EFFECT-01 Phase 3** (#95) — 2–3-case causal matrix varying stage context. Phases 1 & 2 landed. Unblocks SPANTAG.
2. **#119 / turnscope greatGrandparents fix** — small surgical fix to `allowed_branches` when section targets greatGrandparents subtree.
3. **#90 / WO-EX-SPANTAG-01** — two-pass extraction: Pass 1 evidence-only NL tag inventory, Pass 2 bind/project with **section / target_path / era / pass / mode as explicit controlled priors** (not implicit forces). Subject-beats-section rule when Pass 1 binds a non-narrator relation_cue. Dual-path emission as first-class Pass 2 output. First target pack = the 15 stubborn cases, scored against SECTION-EFFECT-01-adjudicated labels. Flag `HORNELORE_SPANTAG=1`, off by default. **Implementation unblocks after SECTION-EFFECT-01 Phase 3 signoff.** See `WO-EX-SPANTAG-01_Spec.md`.
4. **Post-SPANTAG gate** — if SPANTAG ships default-on, R5.5 Pillar 2 (entity-role binding) opens. If it doesn't, iterate SPANTAG or revisit.
5. **WO-LORI-CONFIRM-01** — parked spec, opens for implementation after the SPANTAG decision. Interview-engine confirm pass + kinship skeleton block; 4-field pilot (personal.birthOrder / siblings.birthOrder / parents.relation / date-range). Product-lane, orthogonal to the extractor pillars.

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
- 2026-04-21: Stack-ownership rule sharpened — cold boot is **~4 minutes** (HTTP listener ~60–70s, then 2–3 min model warmup). The agent-issued combined restart+eval block on 2026-04-21 cold-started cg_001 into a 90s read-timeout because the wait loop only checked the listener, not the extractor. Codified the warmup-probe requirement on any future combined block, but default remains: agent does NOT restart the stack.
- 2026-04-21 (mid-day): **WO-EX-NARRATIVE-FIELD-01 Phase 2 tighten landed** (commits `3fec639`, `9706a87`) — anti-consolidation SCALAR CO-EMISSION rule + NARRATOR-IDENTITY PRIORITY rule appended to `_NARRATIVE_FIELD_FEWSHOTS` (extract.py L1537–1584), gated behind `HORNELORE_NARRATIVE=1`. Fixes the Phase 2 regression where narrative fewshots pulled narrator scalars (`personal.dateOfBirth`, `personal.placeOfBirth`) into parent-prose buckets on case_049. Targeted smoke: case_049 → 1.000. **CLAIMS-02 role-exempt** landed (commit `291cbb8`) — added `"role"` to `_SHORT_VALUE_EXEMPT_SUFFIXES` (extract.py L4547). Fixes CLAIMS-02 validator dropping `community.role='OT'` as <3-char on case_040; this was pre-existing, masked by r5c/r5d length-luck (LLM randomly emitted `'OT (Occupational Therapist)'`). **Phase 3 Fix A landed** (commit `77e5b52`) — `_ROLE_ALIASES` + `_role_alias_match` in `scripts/run_question_bank_extraction_eval.py` L149–168, wired into `score_field_match` at L181. Bidirectional alias for 6 healthcare/therapy initialisms (OT/PT/RN/LPN/NP/SLP). **Measurement-side change** — on every r5e flip involving a `.role` field, scorer-drift audit must attribute whether extraction changed or scorer credited a value it wouldn't have before. **Phase 3 Fix C landed** (commit `74f7b0d`) — DATE-RANGE PREFERENCE RULE appended to `_NARRATIVE_FIELD_FEWSHOTS` (extract.py L1586–1595): for `*.yearsActive`/`*.dateRange`/`*.servicePeriod` fields, prefer explicit range (`1997-2026`) over duration phrase (`twenty-five years`); expand professional-role abbreviations in context. Next eval = **r5e** (master + Phase 2 tighten + role-exempt + Fix A + Fix C composite). Methodology flag: 5 stacked commits, one scorer-side — audit flips rigorously on landing. r5d floor = 58/104 v2=30. r5e prediction: 59–62/104 v2=31–33.
- 2026-04-21 (evening): **r5e2 master REJECTED** (56/104 v3=35/62 v2=29/62 mnw=0). Three-agent convergence (Chris / Claude / ChatGPT): the ATTRIBUTION-BOUNDARY RULE did clean up forbidden writes (mnw 2 → 0) and hit its named targets (case_093 0.70 → 0.90, case_005 0.00 → 1.00), but friendly-fired on 7 clean passes (case_003/018/022/034/067/075/088 all regressed to ≤0.50, three of them 1.00 → 0.00), **including case_075 which is exactly the mother_stories class the rule was meant to protect**. `noise_leakage` tripled (4 → 12). Net -3 vs r5e1 floor. Action taken: **(b) + (c) combined** — r5e1 re-locked as the performance floor; ATTRIBUTION-BOUNDARY exemplar block kept in-tree but gated behind a new default-off `HORNELORE_ATTRIB_BOUNDARY=1` flag (paired with `HORNELORE_NARRATIVE=1`). extract.py change: `_NARRATIVE_FIELD_FEWSHOTS` truncated at end of DATE-RANGE PREFERENCE RULE; ATTRIBUTION-BOUNDARY block extracted into a separate `_ATTRIBUTION_BOUNDARY_FEWSHOT` constant; both append sites (L929, L1491) now consult `_attribution_boundary_enabled()` as a secondary condition. Default live behavior is now byte-identical to r5e1. The real fix for the attribution/ownership class is parked as **WO-LORI-CONFIRM-01** (interview-engine confirm pass + kinship skeleton, spec at repo root), sequenced behind SECTION-EFFECT Phase 3 (#95) + SPANTAG (#90) default-on/off decision. `FAILING_CASES_r5e1_RUNDOWN.md` authored today: 45-case Q/A/era/issue rundown, surfacing birth-order arithmetic cluster, pet salience, silent-drop explicit-answer class, and the attribution class that WO-LORI-CONFIRM-01 now targets. Active baseline = r5e1 (59/104, mnw=2 known, case_035 + case_093 the two offenders). Next tag = **r5f** (post-SECTION-EFFECT Phase 3 or next extractor-lane patch), unrelated to the rejected r5e2.
- 2026-04-20 (evening): **#99 / WO-STT-LIVE-02** landed — STT-agnostic fragile-fact guard + transcript safety layer. Backend: `ExtractFieldsRequest` gains 6 Optional transcript fields (`transcript_source`, `transcript_confidence`, `raw_transcript`, `normalized_transcript`, `fragile_fact_flags`, `confirmation_required`); `ExtractedItem` gains `audio_source` / `needs_confirmation` / `confirmation_reason`; `ExtractFieldsResponse` gains `clarification_required: List[Dict]`. New fragile-field classifier (narrator identity + spouse + indexed parents/siblings/children/grandparents/greatGrandparents prefixes with leaf filter). New `_apply_transcript_safety_layer(items, req)` stamps `audio_source` on every item (Pass 1) and downgrades fragile fields to `writeMode=suggest_only` + emits clarification envelope when `confirmation_required=True` (Pass 2). `[extract] Attempting` and `[extract][summary]` log lines extended with `stt_src` / `stt_conf` / `confirm_req`. Frontend: new `ui/js/transcript-guard.js` IIFE (`window.TranscriptGuard`) with 7-pattern fragile-fact classifier, `populateFromRecognition` (Web Speech → min-over-segments confidence), `markTypedInput`, `reconcileForSend` (30s staleness cap + substring match → "typed" fallback on hand-edit), `buildExtractionPayloadFields` (returns `{}` when nothing staged, preserving byte-stability). `state.js` gains `lastTranscript` object. `app.js` wires `recognition.onresult` and `sendUserMessage()` typed-input staging. `interview.js` merges STT fields into extraction payload and dispatches clarifications (custom handler → shadow-review → console fallback). **Byte-stable with r5a eval** — eval harness doesn't populate transcript fields; pre-WO callers behave identically. Smoke: 68/68 assertions green (38 frontend + 30 backend via AST-slice). Full landing report at `docs/reports/WO-STT-LIVE-02_REPORT.md`. Deferred: live round-trip in browser (Chris's stack cycle), WO-STT-LIVE-03 backend Whisper migration, UI surface for fragile clarifications (three-tier dispatch already in place).
