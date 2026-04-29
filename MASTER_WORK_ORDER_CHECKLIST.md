# Master Work Order Checklist

**As of:** 2026-04-29 (overnight)
**Active baseline:** `r5h-postpatch` confirmed = `r5h` (70/104, v3=41/62, v2=35/62, mnw=2) — unchanged
**SPANTAG state:** OFF (`HORNELORE_SPANTAG=0`). Do not flip until BINDING-01 lands.
**Parent sessions:** ~2 days out. Canonical-life-spine + BUG-312 protected_identity gate landed today; pre-laptop-migration backup intact. Pre-parent-session blockers in Lane 2 still ahead.

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
| 1 | **WO-EX-BINDING-01** | TOP OF QUEUE | `r5g-binding` (planned) | Binding-layer fix. Delivered inside SPANTAG Pass 2 prompt via PATCH 1–5 (Type C binding rules + negative examples + childhood_moves tie-break + minimal scalar guard for `personal.placeOfBirth` + `[extract][BINDING-01]` log marker). Unblocks SPANTAG re-enable. |
| 2 | **#144 WO-SCHEMA-ANCESTOR-EXPAND-01** | Lane 1 trial annotated | `r5h` (banked) | Lane 1 (`alt_defensible_paths` for case_033 + case_039) landed scorer-side; Lane 2 schema expansion gated behind Lane 1 evidence. |
| 3 | **#97 WO-EX-VALUE-ALT-CREDIT-01** | Spec landed | (planned) | Value-axis alt-credit under ≥0.5 fuzzy gate. Targets case_087 ancestry value drift. |
| 4 | SPANTAG re-enable evaluation | **GATED — do not run until BINDING-01 lands** | `r5g-binding`, then later | After BINDING-01: cycle stack with `HORNELORE_SPANTAG=1` exported in server env (`SPANTAG_PASS1_MAX_NEW=1024`, `SPANTAG_PASS2_MAX_NEW=1536` already in `.env`); rerun master eval; judge by Type A/B/C, not general gate. |

### Locked decisions

- `r5h` is the regression net. Climbing past 70/104 happens via real parent-session data once it accrues, not synthetic patching alone.
- SPANTAG default-off until BINDING-01 lands. Three patches from commit e579ed0 (value-coerce wrapper at extract.py:7006, HF_HUB_OFFLINE init at api.py:50, `.env` revert) are dormant when SPANTAG=0; they prove their value the moment SPANTAG re-enables.
- Two known `must_not_write` offenders are pre-r5e1 carryover (case_035 faith turn `education.schooling`, case_093 spouse-detail `education.higherEducation`); both are WO-LORI-CONFIRM-01 targets. Don't chase them in Lane 1 patches.

### Parallel cleanup (do not block main sequence)

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
| 1 | **WO-LORI-SAFETY-INTEGRATION-01** Phase 1 | Spec landed | YES — CRITICAL | Wire existing `safety.py:scan_answer()` into `chat_ws.py` between user_text receipt (~L199) and `compose_system_prompt` (L208). Currently zero deterministic safety on chat path. Per parity audit: this is the highest-acuity gap. |
| 2 | **WO-LORI-SESSION-AWARENESS-01** Phase 1 | **Import-fix LANDED 2026-04-27 evening** (chat_ws.py L163, L180, L181). Peek-at-Memoir consultation + warm composer remain. | YES | Three broken late imports (`from api.X` → `from ..X`) fixed and AST-verified. Eval-safe (chat_ws not exercised by extraction eval). Peek-at-Memoir backend may not exist — see parity audit Risk #2; verify before Peek consultation work. |
| 3 | **WO-LORI-SESSION-AWARENESS-01** Phase 2 + **WO-LORI-ACTIVE-LISTENING-01** | Specs landed (ACTIVE-LISTENING new 2026-04-29) — **land both together** | YES — interview discipline | ACTIVE-LISTENING is the discipline-rules + filter implementation for SESSION-AWARENESS Phase 2. LORI_INTERVIEW_DISCIPLINE system prompt block + runtime filter with intent-aware tiers (memory_echo 100w/1q, interview_question 55w/1q, attention_cue 25w/0–1q, repair 30w/1q, safety 200w/0q exempt). Two-layer defense (prompt block default-on; `_trim_to_one_question` runtime filter behind env flag). Six new metrics ride existing WO-LORI-RESPONSE-HARNESS-01 Test Type A. |
| 4 | **WO-LORI-SAFETY-INTEGRATION-01** Phase 3 | Spec landed | YES — operator surface | Bug Panel real-time banner + between-session digest. Pattern fires today but operator gets no signal. Highest-leverage new work. |
| 5 | **WO-LORI-SAFETY-INTEGRATION-01** Phases 2, 4–9 | Spec landed | YES — most | LLM second-layer classifier (Phase 2), IDEATION/DISTRESSED prompt block additive to ACUTE rule (Phase 4), composer/WO-10C/memory-echo/family_truth integration (Phase 5), Friendship Line resource (Phase 6), LV_ENABLE_SAFETY cleanup (Phase 7), red-team pack (Phase 8), operator runbook + onboarding consent (Phase 9, NON-NEGOTIABLE). |
| 6 | **WO-LORI-RESPONSE-HARNESS-01** | Spec authoring this batch | NO — first iteration after parents start | Response-quality test harness. Bug Panel + Test Lab. Answers "Did Lori respond like a good interviewer?" (orthogonal to extraction evals). |

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
