# Master Work Order Checklist

**As of:** 2026-05-02 (continuous-work session — utterance-frame Phase 0-2 day)
**Active baseline:** `r5h-followup-guard-v2` = **77/114, v3=48/72, v2=42/72, mnw=2** — locked 2026-05-02 (BUG-EX-PLACE-LASTNAME-FOLLOWUP-01 closed GREEN; case_111/112 dual-place fixtures pass; case_113/114 negative fixtures pass). Earlier baseline `r5h` (70/104) remains the legacy-pack reference.
**SPANTAG state:** OFF (`HORNELORE_SPANTAG=0`). BINDING-01 PATCH 1-4 + micro-patch in-tree (`42accc9` / `3f3deba`); default-off after `r5g-binding-on-v1` master REJECTED (`c547ddb`). Both flags gated for next iteration cycle.
**Parent sessions:** Day-of-readiness — Reset Identity utility staged, scan_answer hardening landed, BUG-DBLOCK-01 closed (write-rollback hygiene mirrored across `save_safety_event` + 4 `story_candidate_*` writers). Lori-behavior reflection lane: BUG-LORI-REFLECTION-01 base committed (`ea13cbf`), Patch B REJECTED + reverted (golfball regressed 4/8 → 1/8 — locked principle: prompt-heavy reflection rules make Lori worse; runtime shaping is the path). Clock UI v1 landed (`2e10aba`). **Today (2026-05-02):** WO-EX-UTTERANCE-FRAME-01 promoted from PARKED to ACTIVE Phase 0-2 — pure-deterministic Story Clause Map builder + 24 fixtures + 16 unit tests + 4-test build-gate isolation + CLI debug runner + chat_ws observability log behind `HORNELORE_UTTERANCE_FRAME_LOG=1` (default-off). 24/24 tests green; consumer wiring deferred to Phase 3+. **Evening (2026-05-02):** WO-EX-CASE-BANK-FIXUP-01 Phase 1 shipped (case_110 spouse path normalized bare `spouse.*` → canonical `family.spouse.*`, 5 occurrences, only outlier in bank); BUG-EX-BIRTH-DATE-PATTERN-01 + WO-EX-CASE-BANK-FIXUP-01 umbrella specs parked. Audit at `r5h-followup-guard-after-utterance-frame-v1` = 76/114 v3=48/72 v2=42/72 mnw=0.012 — single non-contract flip on case_075 ([GAP], stochastic). Stubborn-pack 3-run stability: stable_pass=11/15 stable_fail=4/15 **unstable=0/15** (case_075 stable_pass 3/3, scores 1.0/1.0/1.0). Verdict: utterance-frame Phase 0-2 + case_110 patch byte-stable; active baseline `r5h-followup-guard-v2` preserved. Per-case verification of case_110 flip pending next master eval (`r5h-followup-guard-v3` if Chris keeps the suffix scheme).

---

## Three lanes, separate posture

The repo runs three parallel lanes. They touch different code paths and get worked in parallel without blocking each other.

### Lane 1 — Extractor (regression-gated)

Synthetic eval bench: 104 cases, locked at 70/104. Climbs only when the extractor architecture earns it. Frozen baseline is `r5h`.

### Lane 2 — Lori behavior (parent-session-gated)

In-session listener behavior: safety responsiveness, interview discipline, memory echo grounding, attention awareness. Three pre-parent-session blockers in this lane.

### Lane 3 — MediaPipe / session awareness (post-parent-session polish)

Attention cue + adaptive silence ladder. Doesn't block first parent sessions. Scoped, parked behind Lane 2 closure.

---

## Lane 1 — Extractor (active baseline `r5h` locked)

### Active sequence

| # | WO | Status | Eval tag | Notes |
|---|---|---|---|---|
| 1 | **BUG-EX-PLACE-LASTNAME-01** | LANDED 2026-04-29 (`9b9e557`) | `r5h-place-guard` re-run unblocked by eval-script printer fix `4ac71f0` (#323) | Deterministic post-LLM guard at `extract.py` drops `.lastName`/`.maidenName`/`.middleName` candidates appearing only after place-prepositions. 6 new fixtures `case_105–110`. Smoke 15/15. Ships independent of SPANTAG. First eval run completed 110 cases cleanly (75/110, mnw 1.2%) but lost the report to a printer crash; re-run pending. |
| 2 | **WO-EX-BINDING-01** | **PATCH 1-4 LANDED + iterating.** PATCH 1-4 (`42accc9`) + micro-patch (`3f3deba`); `r5g-binding-on-v1` master REJECTED (`c547ddb`). | `r5g-binding-on-v1` (banked), next iteration TBD | Binding-layer fix. SPANTAG Pass 2 binding pre-normalizer + `_validate_item` re-entry + 9 `_FIELD_ALIASES` from r5g probe. Default-OFF after rejection at default-on. Probes `r5g-binding-probe-7cases` (3/7 primary 3/3) + v2/v3 confirmed micro-patch was real. Next move: additional binding rules / second eval cycle / scope re-evaluation. |
| 3 | **#144 WO-SCHEMA-ANCESTOR-EXPAND-01** | Lane 1 trial annotated | `r5h` (banked) | Lane 1 (`alt_defensible_paths` for case_033 + case_039) landed scorer-side; Lane 2 schema expansion gated behind Lane 1 evidence. |
| 4 | **#97 WO-EX-VALUE-ALT-CREDIT-01** | Spec landed | (planned) | Value-axis alt-credit under ≥0.5 fuzzy gate. Targets case_087 ancestry value drift. |
| 5 | SPANTAG re-enable evaluation | **GATED — paired with BINDING-01 second iteration cycle** | next BINDING tag | After next BINDING iteration: cycle stack with `HORNELORE_SPANTAG=1` exported in server env (`SPANTAG_PASS1_MAX_NEW=1024`, `SPANTAG_PASS2_MAX_NEW=1536` already in `.env`); rerun master eval; judge by Type A/B/C, not general gate. |

### Locked decisions

- `r5h` is the regression net. Climbing past 70/104 happens via real parent-session data once it accrues, not synthetic patching alone.
- SPANTAG default-off until BINDING-01 lands. Three patches from commit e579ed0 (value-coerce wrapper at extract.py:7006, HF_HUB_OFFLINE init at api.py:50, `.env` revert) are dormant when SPANTAG=0; they prove their value the moment SPANTAG re-enables.
- Two known `must_not_write` offenders are pre-r5e1 carryover (case_035 faith turn `education.schooling`, case_093 spouse-detail `education.higherEducation`); both are WO-LORI-CONFIRM-01 targets. Don't chase them in Lane 1 patches.

### Parallel cleanup (do not block main sequence)

- **WO-EX-UTTERANCE-FRAME-01 Phase 0-2** — **LANDED 2026-05-02 morning + POLISH 2026-05-02 evening.** Pure-deterministic Narrator Utterance Frame / Story Clause Map builder at `server/code/api/services/utterance_frame.py`. Public `build_frame(narrator_text) → NarratorUtteranceFrame` returns clause-level decomposition (subject_class / event_class / place / time / negation / uncertainty / candidate_fieldPaths). Zero new deps (stdlib + reuse of `lori_reflection._AFFECT_TOKENS_RX`). 24 hand-authored fixtures (`tests/fixtures/utterance_frame_cases.json`) including case_111/112 dual-subject motivators (uf_001/002) plus polish fixtures uf_021–024 (lowercase Stanley/Spokane STT, aluminum plant specific phrase, stated feeling visibility). 16 unit tests + 4 build-gate isolation tests (negative-test-verified). CLI debug runner at `scripts/utterance_frame_repl.py`. Chat_ws observability log behind `HORNELORE_UTTERANCE_FRAME_LOG=1` (default-off, mirrors story-trigger gate, fires `[utterance-frame]` log line per narrator turn). **Polish patch (2026-05-02 evening)** added: lowercase known-place fallback (spokane/stanley/mandan/bismarck/montreal/oslo/hanover/norway → canonical capitalized when verbatim after place preposition), prefer-specific-workplace-object (place=plant + object=aluminum plant → place=aluminum plant), richer log shape with `obj=` + `feel=`. Polish driven by **WO-EX-UTTERANCE-FRAME-SURVEY-01** (new harness + spec at `scripts/run_utterance_frame_survey.py` + `WO-EX-UTTERANCE-FRAME-SURVEY-01_Spec.md`) which paired golfball traffic + api.log frame lines, surfaced AMBER findings, and sized the polish exactly. **Phase 0-2 ships zero behavior change** — frame is observation-only; consumer wiring (extractor binding Phase 3, Lori grounding Phase 4, validator Phase 5, UI surface Phase 6) opens after BINDING-01 second iteration evidence.
- **WO-EX-EVAL-WRAPPER-01** — single-command extractor eval workflow. Spec authored 2026-04-27. Eliminates the 6-step manual ritual for SPANTAG / BINDING-01 evals (refusal-on-failure gates for .env flip + stack restart + warmup probe + flag verification + inline post-eval summary). 3–5 hours implementation. Build before the next BINDING-01 eval cycle.
- **WO-EX-FIELD-CARDINALITY-01** — deferred separate lane per Architecture Spec v1 §7.3. Opens only if BINDING-01's minimal scalar guard proves insufficient.
- **WO-SCHEMA-DIVERSITY-RESTORE-01** — three-phase plan. Spec authored 2026-04-29. Phase 1 (template port from `/mnt/lorevox/ui/templates/`: 17 named diverse + 9 dopplegangers + manifest) = pure file copies, ~1-2 hrs. **Phase 1.5 LANDED 2026-04-29** (Janice pet pig + Christopher 5 lifetime pets + stepchildren placeholder + relation:"biological" on existing 3 children). Phase 2 (array-shape normalization adapter for spouse/marriage) ~1 day, gates Lorevox-template ingestion. Phase 3 (sensitive identity capture: genderIdentity, sexualOrientation, religiousAffiliation, spiritualBackground, culturalAffiliations[], raceEthnicity[] with visibility/provenance state) 2-3 days code + 1-2 days policy. Required before Hornelore can ingest Lorevox's diverse-shape templates without surprises. BUG-311 evidence (extractor binding hallucination on test-harness.js:65-98) reinforces Phase 3 sensitive-field guard rationale.
- **#142 WO-EX-DISCIPLINE-01** — run-report header. Live and working (visible in r5h-postpatch eval).
- **#141 WO-EX-FAILURE-PACK-01** — cluster JSON sidecar. Live and working.
- **WO-LORI-CONFIRM-01** — parked. v1 = 3-field pilot (`personal.birthOrder`, `siblings.birthOrder`, `parents.relation`). dateRange v1.1 reactivation unlocked by #111 corpus expansion (cg_019, cg_020, cg_021).

### Standard eval block (when invoked)

```bash
cd /mnt/c/Users/chris/hornelore
./scripts/archive/run_question_bank_extraction_eval.py --mode live \
  --api http://localhost:8000 \
  --output docs/reports/master_loop01_<SUFFIX>.json
grep "\[extract\]\[turnscope\]" .runtime/logs/api.log | tail -40
```

Suffix rotates per-eval. Standard post-eval audit block per CLAUDE.md.

---

## Lane 2 — Lori behavior (pre-parent-session blockers)

Three WOs gate parent sessions. They land in this order; Phase 0/1 of each is the urgent slice.

### Active sequence

| # | WO | Status | Land before parents | Notes |
|---|---|---|---|---|
| 1 | **WO-LORI-SAFETY-INTEGRATION-01** Phase 1 | **LANDED** (`8aab2c2`) + **default-safe fallback hardening LANDED 2026-04-29** (chat_ws.py L206-228) | DONE | Chat-path scan_answer hook live. Mirrors interview.py:269-307. Persists segment flag + softened mode + WS overlay event + operator notify + forces turn_mode=interview. 2026-04-29 hardening: when scan_answer raises, force turn_mode=interview anyway + emit `[chat_ws][safety][default-safe]` log marker. Stress-test #325 pending. |
| 2 | **WO-LORI-SESSION-AWARENESS-01** Phase 1 | **Import-fix LANDED 2026-04-27 evening** (chat_ws.py L163, L180, L181). Peek-at-Memoir consultation + warm composer remain. | YES | Three broken late imports (`from api.X` → `from ..X`) fixed and AST-verified. Eval-safe (chat_ws not exercised by extraction eval). Peek-at-Memoir backend may not exist — see parity audit Risk #2; verify before Peek consultation work. |
| 3 | **WO-LORI-SESSION-AWARENESS-01** Phase 2 + **WO-LORI-ACTIVE-LISTENING-01** | Specs landed (ACTIVE-LISTENING new 2026-04-29) — **land both together** | YES — interview discipline | ACTIVE-LISTENING is the discipline-rules + filter implementation for SESSION-AWARENESS Phase 2. LORI_INTERVIEW_DISCIPLINE system prompt block + runtime filter with intent-aware tiers (memory_echo 100w/1q, interview_question 55w/1q, attention_cue 25w/0–1q, repair 30w/1q, safety 200w/0q exempt). Two-layer defense (prompt block default-on; `_trim_to_one_question` runtime filter behind env flag). Six new metrics ride existing WO-LORI-RESPONSE-HARNESS-01 Test Type A. |
| 4 | **WO-LORI-SAFETY-INTEGRATION-01** Phase 3 | Spec landed | YES — operator surface | Bug Panel real-time banner + between-session digest. Pattern fires today but operator gets no signal. Highest-leverage new work — Phase 1 already landed so this is the actual top SAFETY priority now. |
| 5 | **WO-LORI-SAFETY-INTEGRATION-01** Phase 2 | Spec landed | YES — additive | LLM second-layer classifier (catches indirect ideation pattern misses Phase 1's regex doesn't). |
| 6 | **WO-LORI-SAFETY-INTEGRATION-01** Phases 4–9 | Spec landed | YES — most | IDEATION/DISTRESSED prompt block additive to ACUTE rule (Phase 4), composer/WO-10C/memory-echo/family_truth integration (Phase 5), Friendship Line resource (Phase 6), LV_ENABLE_SAFETY cleanup (Phase 7), red-team pack (Phase 8), operator runbook + onboarding consent (Phase 9, NON-NEGOTIABLE). |
| 7 | **WO-LORI-RESPONSE-HARNESS-01** | Spec landed | NO — first iteration after parents start | Response-quality test harness. Bug Panel + Test Lab. Answers "Did Lori respond like a good interviewer?" (orthogonal to extraction evals). |

### Acceptance gates (per WO)

- **WO-LORI-SAFETY-INTEGRATION-01** — zero false negatives on suicidal_ideation across both chat AND interview paths; operator runbook in place; onboarding consent disclosure shipped
- **WO-LORI-SESSION-AWARENESS-01** Phase 1 — memory echo answers warmly without crashing; Peek-at-Memoir consulted when available
- **WO-LORI-SESSION-AWARENESS-01** Phase 2 — 30-turn dev session with zero `[lori][discipline] violation=` log entries (or all violations cleanly trimmed by filter); reference shapes preserved (memory echo not over-trimmed; soft invitation not blocked)

### Pre-parent-session blocker checklist

Use `docs/PARENT-SESSION-READINESS-CHECKLIST.md` as the canonical 7-gate list. The Lori-behavior items above are the new pre-parent additions to that checklist:

- [ ] Memory echo import hotfix landed + regression test
- [ ] LORI_INTERVIEW_DISCIPLINE prompt block + runtime filter live
- [ ] Safety scan wired into `chat_ws.py`
- [ ] Operator notification surface live (Bug Panel banner + digest)
- [ ] LLM safety second-layer live
- [ ] IDEATION/DISTRESSED prompt block additive to ACUTE
- [ ] Friendship Line resource added
- [ ] Red-team pack passes (zero false negative on suicidal_ideation)
- [ ] Operator runbook written
- [ ] Onboarding consent disclosure language added

---

## Lane 3 — MediaPipe / session awareness (post-parent-session polish)

Not parent-session blockers. Spec parked, design stable.

| # | WO | Status | Notes |
|---|---|---|---|
| 1 | **WO-LORI-SESSION-AWARENESS-01** Phase 3 | Spec landed | MediaPipe attention cue. Requires all 4 inputs (gaze_forward + low_movement + no_speech_intent + post_tts_silence) for `passive_waiting`. Tiered cue types (silent indicator → affirmation → soft offer → break offer). Veto rule: `engaged`/`reflective` blocks cue under WO-10C 120s mark. Per parity audit Missing #8: visual signals not currently routed to backend — wiring needed. |
| 2 | **WO-LORI-SESSION-AWARENESS-01** Phase 4 | Spec landed | Adaptive Narrator Silence Ladder. Per-narrator × prompt_weight rolling window (last 30 turns), p75/p90/p95 → tier1/tier2/tier3 with 25s hard floor. Cold-start <10 turns falls back to WO-10C 120s/300s/600s. Pacing FIT not measurement; no surface, no trend, no clinical scoring. |
| 3 | **WO-AFFECT-ANCHOR-01** | Spec landed (PARKED) | Multimodal affect anchoring via shared-clock fusion (Whisper word-timestamps + MediaPipe + light acoustic features + optional Tier 2 video). Blocked by BINDING-01 + parent-session readiness. |

---

## Open spec / unbuilt items (low priority backlog)

- **#171 WO-LORI-PHOTO-SHARED-01 acceptance tests** — schema/provenance/confidence/dedupe/geocode-null/template_prompt/selector/API vertical
- **#172 WO-LORI-PHOTO-INTAKE-01 Phase 2** — EXIF + real geocoder + conflict detector + review queue + flag
- **#173 WO-LORI-PHOTO-ELICIT-01 Phase 2** — photo_memory extraction profile + async scheduler + LLM prompts + flag
- **#246 WO-FACEMESH-01** — `face_mesh.binarypb` 404 + SIMD WASM crash loop
- **#35 V4 eval scope** — log density + intent-class + topic-shift axes (post-freeze)
- **WO-EX-NORMALIZE-EXPAND-01** (unwritten) — extend Patch H pattern to phone/address/format-sensitive fields
- **WO-EVAL-MULTITURN-01** — parked spec for multi-turn harness to validate WO-LORI-CONFIRM-01

---

## Closed (last 14 days, abbreviated)

| Item | Outcome |
|---|---|
| **WO-BUG-PANEL-EVAL-HARNESS-01 Phase 1** (2026-04-29 evening, #332) | Read-only Bug Panel Eval Harness cockpit. New `server/code/api/routers/operator_eval_harness.py` + `ui/js/bug-panel-eval.js` + `ui/css/bug-panel-eval.css`. 4-card surface (Extractor / Lori Behavior / Safety / Story Surface) backed by `/api/operator/eval-harness/{summary,reports,report/{name},log-tail}`. `HORNELORE_OPERATOR_EVAL_HARNESS=0` default-off gate → 404. Smoke-tested against `r5h-restore` (PASS, 70/104, mnw 1.2%, age 0.89d). Phase 2 (run buttons) parked. |
| **prompt_composer warmth + legacy-language cleanup** (2026-04-29 evening, #330) | Four narrator-facing string edits: 273-TALK no-go softened with 988/AFSP context; memory-echo "What I'm less sure about" reworded warmer for elder narrators; NO QUESTION LISTS RULE narrowed to narrator-facing interview mode only; WO-10C "cognitive difficulty (dementia or similar)" replaced with "benefits from extra pacing support" framing per SESSION-AWARENESS-01 banned-vocab spec. AST parse green. |
| **Eval-script printer crash fix** (2026-04-29 evening, `4ac71f0`) | r5h-place-guard initial run completed 110 cases (75/110 pass, 1.2% mnw) but crashed in `print_summary._print_breakdown("By era")` from `None` keys + mixed legacy era names. Three patches: `_canonical_eval_era()` helper using `legacy_key_to_era_id`, None-safe `_breakdown` + `_print_breakdown`, JSON write moved BEFORE printer (so future printer crashes never lose reports). `print_summary` itself wrapped in try/except. |
| **BUG-EX-PLACE-LASTNAME-01** (2026-04-29 afternoon, `9b9e557`) | Deterministic post-LLM regex guard at extract.py drops `.lastName`/`.maidenName`/`.middleName` candidates appearing only after place-prepositions. 6 new fixtures `case_105–110`. Smoke 15/15. Master pack 104 → 110. r5h-place-guard eval queued (#323). |
| **scan_answer() default-safe fallback** (2026-04-29 afternoon, chat_ws.py L206-228) | When scan_answer raises, force turn_mode='interview' so ACUTE SAFETY RULE in prompt fires + emit `[chat_ws][safety][default-safe]` log marker. Closes silent-skip gap surfaced by code review. ~17 lines. AST parse green. |
| **WO-LORI-SAFETY-INTEGRATION-01 Phase 1** (`8aab2c2`) | Chat-path scan_answer hook live in chat_ws.py L196-274. Mirrors interview.py:269-307. Persists segment flag + softened mode + WS overlay event + operator notify + forces turn_mode=interview. Doc surfaced 2026-04-29 — was already shipped before this session opened; master checklist had not been refreshed. |
| **db.py PRAGMA busy_timeout=5000** (`8023501`) | Fixes safety-hook lock contention surfaced after SAFETY-INTEGRATION-01 Phase 1 landed. Already active. |
| **WO-INTERVIEW-MODE-01 Phase 1** (`f1e0612`) + narrator-room unified 3-column (`bc02b32`) | Focused 3-column interview view; Memory River removed from narrator room. |
| **r5h-restore master eval** (`66f41ae`) | SPANTAG flag fix verified; 70/104 baseline preserved at the post-BINDING-01-rejection state. |
| **WO-EX-BINDING-01 PATCH 1-4 + micro-patch** (`42accc9` / `3f3deba`) | SPANTAG Pass 2 binding pre-normalizer + `_validate_item` re-entry + 9 `_FIELD_ALIASES`. Probed against 7 cases (3/7 primary 3/3) at `8564840`; v2/v3 (`2ec7de5`) confirmed micro-patch real, not stochasticity. Default-on master `r5g-binding-on-v1` REJECTED (`c547ddb`). Code in-tree behind `HORNELORE_SPANTAG=1` flag, default-off; iteration cycle TBD. |
| **WO-CANONICAL-LIFE-SPINE-01 Steps 3a-fix → 8** (2026-04-29) | Eight atomic commits migrating frontend + backend from legacy era keys to canonical 7-bucket era_ids (earliest_years / early_school_years / adolescence / coming_of_age / building_years / later_years / today) with self-healing read/write. Live-verified on Christopher Horne narrator. Memoir Peek shows 7 sections with warm heading + literary subtitle; Life Map renders 7 buttons routed through Step 7 confirm popover; Step 8 TXT export uses `data-era-id` selectors. |
| **BUG-312 protected_identity gate** (2026-04-29) | `ui/js/projection-sync.js` L91-130. Protected fields require trusted source for ANY write, not just overwrites. Fixes BUG-309 DOB regression upstream. Closed task #309 completed-via-#312. |
| **Pre-laptop-migration backup** (2026-04-28T23:40) | `/mnt/c/hornelore_data/backups/2026-04-28_2340_before-laptop-migration-canonical-reset/`. SQLite integrity OK; WAL checkpoint clean. |
| **BUG-311 reclassification** (2026-04-29) | Investigation traced "Lori-text leakage" to extractor span-binding hallucination on narrator-side text (test-harness.js:65-98). Belongs in WO-EX-BINDING-01 lane as additional Type C fixture. No code change; investigation-only. |
| `r5h-postpatch` eval | Confirmed `r5h` baseline preserved (70/104). Three e579ed0 patches dormant + clean when SPANTAG=0. |
| **SPANTAG default-on REJECTED** at v3 attempt | Net -39 cases. Field-path hallucination cluster confirmed as binding-layer issue. SPANTAG demoted to evidence pipeline; BINDING-01 promoted to top. |
| #95 SECTION-EFFECT Phase 3 | PARKED. Type A/B/C question typology LOCKED. Bumper sticker: "Extraction is semantics-driven, but errors are binding-driven." |
| #141 WO-EX-FAILURE-PACK-01 | Cluster JSON sidecar wired into master eval. |
| #142 WO-EX-DISCIPLINE-01 | Run-report header live. Confirmed working in r5h-postpatch. |
| WO-EX-SPANTAG-01 Commit 3 | Pipeline wired default-off. Pass 2 controlled-prior carries section + target_path only (era/pass/mode dropped per Q1=NO). |
| WO-MEDIA-ARCHIVE-01 | Document Archive lane shipped (PDFs / scanned docs / handwritten notes / genealogy / letters / certificates / clippings). |
| WO-LORI-PHOTO-* (PHASE 1 + Phase 2 partial) | Photo intake, EXIF auto-fill, Review File Info preview, batch upload, View/Edit modal, narrator-room lightbox, dedupe-by-file-hash. |
| WO-NARRATOR-ROOM-01 | Three-tab shell, narrator room layout, Take-a-break overlay, chat scroll stabilization. |
| WO-ARCHIVE-AUDIO-01 | Memory archive backend (per-narrator zip export, two-sided text transcript, narrator-only audio rule). |
| WO-AUDIO-NARRATOR-ONLY-01 | Per-turn audio capture (backend + frontend MediaRecorder). |

---

## Standing reminders

- Chris runs / stops the API himself. Don't include `start_all.sh` or `stop_all.sh` in command blocks.
- Cold boot is ~4 minutes (HTTP listener ~60–70s; LLM weights + extractor warmup another 2–3 min). This is normal, not a bug. Eval harness must wait for warmup or first cases time out.
- Every eval that follows a code change must report the standard post-eval audit block (in CLAUDE.md).
- Each WO must report the audit block before being called done (extractor lane); Lori-behavior lane uses its own acceptance gate per WO.
- When three agents (Claude/Gemini/ChatGPT) converge, act — don't re-argue.
- Sandbox can't run git. Commit blocks must be handed to Chris as copy-paste from `/mnt/c/Users/chris/hornelore`.
- Banned vocabulary in Lori-behavior WOs is structural (not stylistic). Pull requests against any Lori-behavior phase introducing scoring/classification/drift-tracking get rejected on the values clause alone.

---

## Quick file reference

| Kind | Path |
|---|---|
| Canonical extractor architecture | `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` |
| Active extractor spec | `WO-EX-BINDING-01_Spec.md` |
| Parent-session readiness gates | `docs/PARENT-SESSION-READINESS-CHECKLIST.md` |
| Parity audit (this batch) | `docs/reports/HORNELORE_PARITY_AUDIT_2026-04-27.md` |
| Lori behavior — safety | `WO-LORI-SAFETY-INTEGRATION-01_Spec.md` |
| Lori behavior — session awareness | `WO-LORI-SESSION-AWARENESS-01_Spec.md` |
| Lori behavior — interview discipline (Phase 2 implementation) | `WO-LORI-ACTIVE-LISTENING-01_Spec.md` (2026-04-29) |
| Lori behavior — response harness | `WO-LORI-RESPONSE-HARNESS-01_Spec.md` |
| Schema diversity restoration | `WO-SCHEMA-DIVERSITY-RESTORE-01_Spec.md` (2026-04-29) |
| Multimodal affect (parked) | `WO-AFFECT-ANCHOR-01_Spec.md` |
| Lorevox parity audit (template universe) | `docs/reports/LOREVOX_TEMPLATE_PARITY_2026-04-29.md` |
| BUG-311 investigation (reclassification → BINDING-01) | `docs/reports/BUG-311_INVESTIGATION_2026-04-29.md` |
| Code review (2026-04-29) | `docs/reports/CODE_REVIEW_2026-04-29.md` |
| Eval bank | `data/qa/question_bank_extraction_cases.json` (104 master) + `data/qa/question_bank_generational_cases.json` (24 canon-grounded) |
| Latest eval | `docs/reports/master_loop01_r5h-postpatch.json` (+ `.console.txt` + `.failure_pack.json`) |
| Extract router | `server/code/api/routers/extract.py` |
| Safety detector | `server/code/api/safety.py` |
| Prompt composer | `server/code/api/prompt_composer.py` (ACUTE SAFETY RULE at L108–193) |
| CLAUDE.md | `CLAUDE.md` (read first every session) |
