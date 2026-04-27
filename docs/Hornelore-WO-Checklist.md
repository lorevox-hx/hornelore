# Hornelore Master Work Order Checklist

**Updated: 2026-04-25 night** · **Active baseline (extractor): r5h 70/104**

**Posture (locked 2026-04-25 evening):** **Tomorrow is prep + debug only with test narrators. Real parent sessions are ~3 days out, NOT tomorrow.** Real parents only start once all 7 gates in `docs/PARENT-SESSION-READINESS-CHECKLIST.md` are GREEN.

This is the single-source-of-truth checklist for everything in flight. The repo runs **two parallel lanes** — distinguish them when reading:

- **Companion-app lane** (Hornelore UI / Lori) — the application as a whole. OT-appropriate life review with older adults. **Mom + Dad as first family-real narrators ~3 days from now, after readiness gates clear.**
- **Extractor lane** (LOOP-01 R5.5 Pillar 1) — the truth-extraction pipeline behind the companion. Synthetic 104-case bench until parents start producing real narrator data.

Authoritative for current-day state: `CLAUDE.md` (extractor), `README.md` (companion), `HANDOFF.md` (laptop bring-up), `docs/reports/CODE-REVIEW-2026-04-25.md` (this week's tech debt), `docs/PARENT-SESSION-READINESS-CHECKLIST.md` (the 7 gates). Read those first.

---

## OVERNIGHT QUEUE (2026-04-25 night) — locked priority

Per Chris's directive 2026-04-25 evening (corrected late-evening: prep + debug only, NOT live parent sessions tomorrow).
**DO NOT expand feature scope overnight.** When agent wakes up, the workflow Chris should be able to run from a cold open with **a TEST narrator (e.g. Corky)** is:

> 1. Open Hornelore → 2. Select a TEST narrator (no parents) → 3. Run Questionnaire First → 4. Talk for 5–10 minutes → 5. Click Export → 6. Open transcript + audio → 7. Review + mark corrections.

Tomorrow's milestone is **clean test-session-to-export round-trip with no contamination**, NOT a parent session. Real parents only after the 7 readiness gates clear (see `docs/PARENT-SESSION-READINESS-CHECKLIST.md`).

### Priority order

1. **BUG-208** — Bio Builder cross-narrator questionnaire contamination. **Block-everything fix.** Build tonight; do NOT mark closed until live browser verification passes tomorrow morning.
2. **Harness-driven bug sweep.** Once BUG-208 is built, run the full UI Health Check as a bug hunter. File any new issues as `BUG-<n+1>`, classify CRITICAL / HIGH / POLISH, fix only CRITICAL+HIGH that block parent sessions, defer the rest.
3. **WO-ARCHIVE-EXPORT-UX-01** — one-click export button (Bug Panel or Operator).
4. **WO-TRANSCRIPT-TAGGING-01** — per-turn metadata (`role`, `session_style`, `identity_phase`, `bb_field`, `timestamp`).
5. **WO-ARCHIVE-SESSION-BOUNDARY-01** — `session_id` per narrator session, stamped on `meta.json`, transcript lines, audio filenames.
6. **WO-UI-HEALTH-CHECK-03** — extend harness with archive integrity + Bio Builder scope checks.
7. **WO-BB-RESET-UTILITY-01** — dev-only "Reset Bio Builder for current narrator" button (safety valve).
8. **WO-SOFT-TRANSCRIPT-REVIEW-CUE-01** — soft "want to review what we've captured?" cue after 3–5 turns. Non-blocking.
9. **WO-AUDIO-READY-CHECK-01** — preflight before record: mic permission + `MediaRecorder` availability. Surface ✅/⚠️.

### Bug-sweep classification rule (Chris's overnight directive)

```
During overnight harness runs:
  Bug touches data integrity / narrator identity / archive correctness
    → CRITICAL → fix immediately
  Visual / UX only
    → POLISH → defer

Parent-session blockers (auto-CRITICAL):
  - cross-narrator data contamination
  - archive transcript not saving
  - narrator audio saving wrong/missing
  - Lori audio being saved
  - camera/mic state leaking between narrators
  - chat/session loop dead-ending
```

### Hard stop (DO NOT do overnight)

- No STT hands-free expansion
- No new UI tabs
- No Kawa changes
- No prompt rewrites
- No new APIs unless required by an item above

### BUG-208 build spec (verbatim from Chris)

Acceptance verified live tomorrow morning:

- Switch Chris → Corky → Corky questionnaire is empty or Corky-specific (no Christopher fullName/DOB/birthplace)
- Save Corky `personal.birthOrder` → switch away and back → Corky birthOrder persists only for Corky; Chris questionnaire unchanged
- Full UI Health Check: 0 critical FAIL

Files in scope: `ui/js/bio-builder-core.js`, `ui/js/bio-builder-questionnaire.js`, `ui/js/session-loop.js`, `ui/js/ui-health-check.js`, backend `/api/bio-builder/questionnaire` only if necessary.

Required behaviors:

1. **On narrator switch** — clear `bb.questionnaire` immediately; set `bb.personId = active pid`; restore questionnaire only for active pid; never reuse prior in-memory questionnaire.
2. **In restore** — reject backend payload if `person_id` mismatches requested pid; reject localStorage fallback if key/payload mismatches pid; log `[bb-drift]`; clear instead of loading contaminated data.
3. **In persist** — if pid !== `bb.personId`, do NOT save; log hard warning; never write stale questionnaire under another narrator.
4. **In session-loop** — before read/save `currentField`, assert `state.bioBuilder.personId === state.person_id`; if mismatch, stop loop, restore active narrator, and do NOT save answer.
5. **Add UI Health Check tests** — Bio Builder person scope; `state.person_id === state.bioBuilder.personId`; questionnaire identity does not contradict active profile; FAIL if Corky shows Christopher data.

Morning live verification (Chris does this):
- Hard refresh
- Switch Chris → Corky → Chris → Corky
- Verify BB scope on each switch
- Save a Corky field
- Verify Chris unchanged
- Run Full UI Health Check again
- **Do not run parent sessions until BUG-208 live verification passes.**

---

## Companion-app lane

### Shipped this week (2026-04-22 → 2026-04-25)

| WO | What | Status | Verification |
|---|---|---|---|
| WO-UI-SHELL-01 | Three-tab shell: Operator / Narrator Session / Media | Live-tested | Acceptance A–H green; harness reports tab dispatcher present |
| WO-NARRATOR-ROOM-01 | Narrator room: Memory River / Life Map / Photos / Peek; chat scroll stabilize; topbar controls; break overlay; hands-free hooks; 1.5s paint tick | Live-tested | Acceptance A–H green |
| Bug #190 / #194 / #206 | Camera carryover on switch + sessionStyle preservation + camera one-shot drop | Live-fixed | Camera now stops engine on switch, revokes consent, restarts on returning narrator |
| Bug #205 | Bug Panel inaccessible from Narrator tab | Fixed | Moved button back into header |
| Bug #207 | WO-13 welcome-back collision with questionnaire_first dispatch | Fixed | Welcome-back gated when `state.session.sessionStyle === "questionnaire_first"` |
| Bug #202 | Hornelore etymology in Lori intro | Fixed | Lori intro is now Lori + Lorevox (not Hornelore) |
| WO-SESSION-STYLE-WIRING-01 | Session-style picker actually drives Lori behavior; tier-2 directive injection via `_emitStyleDirective` | Live-tested | questionnaire_first / clear_direct / warm_storytelling all dispatch correctly |
| WO-UI-TEST-LAB-01 | UI Health Check harness; observable side-channel flags; per-tab dispatch | Live-tested | Caught photo preflight staleness + camera state-on-but-preview-missing |
| WO-HORNELORE-SESSION-LOOP-01 | Post-identity orchestrator (`session-loop.js`) | Live-tested | Lori never dead-ends post-identity |
| WO-HORNELORE-SESSION-LOOP-01B | Save BB answers via `PUT /api/bio-builder/questionnaire` from inside the loop | Live-tested | savedKeys ledger materializes in harness |
| WO-HORNELORE-SESSION-LOOP-01C | Repeatable-section handoff after personal exhausts | Live-tested | Concrete next-branch prompt fires |
| WO-UI-HEALTH-CHECK-02 | 4 new Session Style harness checks (loop savedKeys, BB endpoint, WO-13 suppression, camera one-shot) | Live-tested | All 4 PASS |
| WO-ARCHIVE-AUDIO-01 | Memory archive filesystem + transcript store + `/api/memory-archive/audio` endpoint with quota gating + role-validation | 34/34 PASS | Backend-only; frontend recorder = WO-AUDIO-NARRATOR-ONLY-01 |
| WO-ARCHIVE-INTEGRATION-01 | Two-sided text transcript writer (`archive-writer.js`); auto-chains into `onAssistantReply` and `sendUserMessage` | Live-tested | Both narrator + Lori turns land in `transcript.jsonl` |
| WO-STT-LIVE-02 | Fragile-fact transcript guard (7-pattern classifier + 30s staleness cap + typed-input fallback) | Live-tested | Backend + frontend; byte-stable with eval harness |
| WO-MIC-UI-02A | 4-state mic UI: LISTENING / OFF / WAIT amber / BLOCKED | Live-tested | (See `WO-MIC-UI-02A_Report.md`) |
| WO-LORI-PHOTO-SHARED-01 | Phase 1 authority layer: schema migration, photo services, elicit services, API router + `HORNELORE_PHOTO_SHARED` flag | Backend complete; UI pages in flight (#170) | Acceptance tests #171 still pending |
| Code review 2026-04-25 | End-of-session technical debt audit | Written | `docs/reports/CODE-REVIEW-2026-04-25.md` — Bug #219 P0, app.js + lori80.css size shape, cache-busting brittle |

### Active companion-app open work (going into overnight 2026-04-25)

| Priority | WO | What | Sized |
|---|---|---|---|
| P0 (overnight) | **BUG-208** | Cross-narrator BB contamination — strict narrator-scope on read/restore/persist + UI-Check assertion | ~150 LOC; 5 files |
| P0 (overnight) | **Harness bug sweep** | Run full UI Health Check post-BUG-208; file CRITICAL/HIGH/POLISH; fix CRITICAL+HIGH only | open |
| P1 (overnight) | WO-ARCHIVE-EXPORT-UX-01 | One-click "Export Current Session" button → `/api/memory-archive/people/{pid}/export` | ~10 LOC |
| P1 (overnight) | WO-TRANSCRIPT-TAGGING-01 | Per-turn metadata stamped on archive lines | ~30 LOC `archive-writer.js` |
| P1 (overnight) | WO-ARCHIVE-SESSION-BOUNDARY-01 | `session_id` per session, stamped everywhere in archive | ~40 LOC |
| P1 (overnight) | WO-UI-HEALTH-CHECK-03 | Archive integrity + BB scope checks | ~80 LOC `ui-health-check.js` |
| P2 (overnight) | WO-BB-RESET-UTILITY-01 | Dev-only "Reset BB for current narrator" button | ~30 LOC |
| P2 (overnight) | WO-SOFT-TRANSCRIPT-REVIEW-CUE-01 | Non-blocking review cue after 3–5 turns | ~20 LOC |
| P2 (overnight) | WO-AUDIO-READY-CHECK-01 | Mic preflight check (permission + `MediaRecorder` available) | ~30 LOC |
| P0 (morning) | WO-AUDIO-NARRATOR-ONLY-01 | Per-turn webm segments → `/api/memory-archive/audio`. Live build with Chris in browser. ~3 hr. **Ship-critical for parents** | spec ready |
| Bug #170 | WO-LORI-PHOTO-SHARED-01 UI pages | `photo-intake.html` / `photo-elicit.html` / `photo-timeline.html` | in flight |
| Bug #171 | WO-LORI-PHOTO-SHARED-01 acceptance | Schema, provenance, confidence, dedupe, geocode-null, template_prompt, selector, API vertical | pending #170 |
| Bug #193 | Camera not working post-restart on archive branch | Triage | pending |

### Companion-app deferred (post first parent session)

| WO | What | Why deferred |
|---|---|---|
| WO-STT-HANDSFREE-01A | Auto-rearm STT after Lori speaks | Polish; parents can type or single-shot mic |
| WO-LORI-PHOTO-INTAKE-01 (Phase 2) | EXIF + real geocoder + conflict detector + review queue | Phase 1 authority layer must land first |
| WO-LORI-PHOTO-ELICIT-01 (Phase 2) | photo_memory extraction profile + async scheduler + LLM prompts | Same |
| WO-INTAKE-IDENTITY-01 | Minimal identity intake + legacy migration | UI landed; awaiting Chris's pre-implementation grep audit + idempotency-guard scan |
| Tech-debt P3 | `state.session` split (session-scoped vs narrator-scoped) | Quiet-day refactor |
| Tech-debt P3 | Diagnostic accessor on every module (touch-as-needed) | Polish |
| Tech-debt P3 | `_v9GateClassify` / `_v9GateRoute` extraction | Quiet day |
| Tech-debt P2 | Factor app.js shell+narrator helpers into separate modules | Post first family session |
| Tech-debt P2 | Factor lori80.css into per-feature files | Same |
| Tech-debt P2 | Standardize log prefixes | Same |
| Tech-debt P1 | Cache-busting strategy (`?v=<git-sha>` on `<script src>` or `Cache-Control: no-cache`) | Next quiet day |
| Tech-debt P1 | `lv80SwitchPerson` MERGE into existing session vs replace | Next quiet day |

---

## Extractor lane (LOOP-01 R5.5)

### Active baseline

**`r5h`: 70/104 · v3=41/62 · v2=35/62 · mnw=2.** Two known mnw offenders (pre-r5e1 carryover, both WO-LORI-CONFIRM-01 v1 targets): `case_035` faith turn (`education.schooling` narrator-leak) and `case_093` spouse-detail follow-up (`education.higherEducation`). r5h delta vs r5f (69/104) is scorer-side only: +1 case_081 via Lane 1 alt_defensible_paths trial annotation. parse_success_rate 93.3%, truncation_rate 0.0%.

r5h hallucination prefix rollup: parents 11, family 10, siblings 7, greatGrandparents 5, education 5, grandparents 4, laterYears 2, residence 1.

### Active extractor sequence (reordered 2026-04-23 evening)

| # | WO | What | Status |
|---|---|---|---|
| 1 | **#90 WO-EX-SPANTAG-01** | Two-pass span tag → bind. Commit 3 landed default-off 2026-04-23 night | **Awaiting clean `r5f-spantag` master eval** with raised caps + flag confirmed firing server-side via api.log grep |
| 2 | **#152 WO-EX-BINDING-01** | Type C binding rules via SPANTAG Pass 2 prompt (Option A primary) | Spec v2 final; eval tag `r5g-binding` layered on `r5f-spantag` |
| 3 | **#144 WO-SCHEMA-ANCESTOR-EXPAND-01** | Lane 1 (scorer-only alt_defensible_paths) trial-running on cases 081/087; Lane 2 (schema expansion: greatGrandparents.firstName/lastName/relation/ancestry) | Lane 1 partial; Lane 2 gated behind Lane 1 evidence |
| 4 | **#97 WO-EX-VALUE-ALT-CREDIT-01** | Value-axis alt-credit at ≥0.5 fuzzy gate. case_087 ancestry French vs French (Alsace-Lorraine), German (Hanover) | Spec ready |
| 5 | **WO-LORI-CONFIRM-01** | v1 = 3-field confirm pass (`personal.birthOrder` / `siblings.birthOrder` / `parents.relation`). dateRange v1.1 REACTIVATION UNLOCKED via #111 corpus expansion | Prep pack ready; v1 implementation pending |
| 6 | **WO-INTAKE-IDENTITY-01** | Minimal identity intake + DOB normalization + legacy migration | v3 spec FINAL; awaiting Chris's pre-impl grep + idempotency scan |

### Parallel cleanup lanes (do not block main sequence)

| WO | What | Status |
|---|---|---|
| #142 WO-EX-DISCIPLINE-01 | Run-report discipline header (git SHA, flag state, model hash, api.log freshness, stack uptime) | Spec ready |
| WO-EX-FIELD-CARDINALITY-01 | Broader scalar-vs-multi-value discipline (deferred separate lane per Architecture Spec v1 §7.3) | Conditional on BINDING-01's minimal scalar guard proving insufficient |

### Recently closed (extractor lane)

| Suffix → Outcome | Date | What |
|---|---|---|
| `r5h` ADOPTED | 2026-04-22 evening | +1 (case_081) via Lane 1 alt_defensible_paths trial; zero regressions |
| `r5g` complete-with-caveat | 2026-04-22 late afternoon | #119 turnscope greatGrandparents EXPAND fires; items die at schema validation; real unlock = #144 Lane 2 |
| `r5f` ADOPTED | 2026-04-22 afternoon | WO-EX-SILENT-OUTPUT-01 Phase 1+2 composite: +10 newly-passed / 0 newly-failed / zero scorer drift |
| `r5e2` REJECTED | 2026-04-21 evening | ATTRIBUTION-BOUNDARY rule friendly-fired on 7 clean passes (incl. case_075). Flag `HORNELORE_ATTRIB_BOUNDARY` in-tree default-off |
| `r5e1` retired | 2026-04-22 afternoon | Was 59/104; superseded by r5f |
| #95 SECTION-EFFECT Phase 3 | 2026-04-23 | PARK. 72/72 clean. Q1=NO; Q2/Q3 stratified by Type A/B/C. Bumper: "Extraction is semantics-driven, but errors are binding-driven." |
| #111 corpus expansion | 2026-04-23 | 24 cases at `_version=2`, 8/8/8 narrator balance, 3 stubborn date-range cases unlock LORI v1.1 |
| #141 WO-EX-FAILURE-PACK-01 | 2026-04-23 | Cluster-JSON sidecar wired into master eval |
| `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` | 2026-04-23 evening | Canonical reference; required reading before any extractor-lane WO |

### Extractor deferred (long tail)

- Hermes 3 / Qwen A/B (post-SPANTAG; attribution clean-up first)
- KORIE staged-pipeline (conditional on SPANTAG ≥20% lift or ≥3 stubborn flips)
- #35 V4 scope axes (log density + intent-class + topic-shift)
- R6 Pillars 2 & 3
- #68 case_053 wrong-entity (disposition memo, deferred to R6 Pillar 2)
- WO-EVAL-MULTITURN-01 (parked spec ready — for validating WO-LORI-CONFIRM-01)
- #96 truncation-lane scoping (the 7 baseline-stable-dead stubborn cases)

### Regressed / shelved

| WO | What | Status | Notes |
|---|---|---|---|
| WO-EX-TWOPASS-01 | Two-pass extraction (early version) | Flag OFF | Regressed 16/62 vs 32/62 baseline. Token starvation + context loss. SPANTAG is the successor; learned the lesson |
| WO-EX-FIELDPATH-NORMALIZE-01A | Confusion-table-driven path normalization | Reverted | Regressed 32/62 → 14/62. Answer vs value text mismatch |
| WO-EX-PROMPTSHRINK-01 | Topic-scoped dynamic few-shot selection (3–8 vs 33 static) | Measured, not adopted | Flag in-tree default-off, available for SPANTAG Pass 2 pairing if useful |
| WO-EX-NARRATIVE-FIELD-01 ATTRIBUTION-BOUNDARY block | Narrator-scope rule for attribution | Default-off | r5e2 friendly-fired 7 cases; in-tree behind `HORNELORE_ATTRIB_BOUNDARY=1` |

---

## Pre-2026-04-22 historical (shipped + proven before this week)

| WO | What | Status |
|---|---|---|
| WO-EX-01C | Narrator-identity subject guard + birth-context filter | Live-proven |
| WO-EX-01D | Field-value sanity blacklists | Live-proven |
| WO-LIFE-SPINE-05 | Phase-aware question composer | Shipped, flag OFF |
| WO-EX-VALIDATE-01 | Age-math plausibility validator | Shipped, flag OFF |
| WO-EX-SCHEMA-01 | family.* + residence.* fields + repeatable entities | Live-proven |
| WO-EX-SCHEMA-02 | 35 new fields (7 families), ~50 aliases | Live-proven |
| WO-EX-CLAIMS-01 | Dynamic token cap, position-aware grouping, 20 aliases | Live-proven |
| WO-EX-CLAIMS-02 | Quick-win validators + refusal guard + community denial | Live-proven, 114 unit tests |
| WO-EX-REROUTE-01 | Semantic rerouter: 4 high-precision paths | Live-proven |
| WO-EX-GUARD-REFUSAL-01 | Topic-refusal guard + community denial | Live-proven; 0 must_not_write |
| WO-EX-TURNSCOPE-01 | `_apply_turn_scope_filter` + ancestor branches | Live-proven; r4h |
| WO-EX-NARRATIVE-FIELD-01 | Phase 2 tighten + CLAIMS-02 role-exempt + Fix A/C composite | Live-proven; r5e1 |
| WO-EX-SILENT-OUTPUT-01 | Phase 1 instrumentation + Phase 2 parser preamble-tolerance | Live-proven; r5f |
| WO-GREETING-01 | Backend endpoint + frontend memory echo | Live-tested 2026-04-16 |
| WO-QB-MASTER-EVAL-01 | 62 → 104 cases, v2/v3 scoring, filters, atomic writer | Live-tested |
| WO-QB-GENERATIONAL-01 (content) | 4 decade packs, 5 new fields, 14 eval cases | Live-tested |
| WO-QB-GENERATIONAL-01B (Part 1+3) | 6 prompt examples, 2 rerouter rules, scorer collision fix | Live-tested |
| WO-KAWA-UI-01A | River View UI | Implementation complete; needs live test |
| WO-KAWA-02A | 3 interview modes, 3 memoir modes, plain-language toggle | Implementation complete; needs live test |
| WO-10C Cognitive Support Mode | 6 dementia-safe behavioral guarantees; 120s/300s/600s silence ladder | Live-proven |

---

## Backlog (long-tail, not specced)

| WO | What | Priority |
|---|---|---|
| WO-INTENT-01 | Narrator topic pivots ignored by composer | High (#1 felt bug from live) |
| WO-EX-DENSE-01 | Dense-truth / large chunk / good-garbage extraction | High (#1 extraction frontier) |
| WO-QB-GENERATIONAL-01B Part 2 | Runtime composer wiring — interleave overlays at 1:4 | Medium |
| WO-KAWA-01 | Parallel Kawa river layer — wire LLM into kawa_projection.py | Medium (10 phases specced) |
| WO-KAWA-02 (remaining) | Phases 4–9: storage promotion, chapter weighting, deeper memoir | Medium (depends on KAWA-01) |
| WO-PHENO-01 | Phenomenology layer: lived experience + wisdom extraction | Medium (3–4 sessions specced) |
| WO-REPETITION-01 | Narrator repeats same content 2-3×, Lori keeps responding | Medium |
| WO-MODE-01/02 | Session Intent Profiles after narrator Open | Low |
| WO-UI-SHADOWREVIEW-01 | Show Phase G suppression reason instead of silent drop | Low |
| WO-EX-DIAG-01 | Surface extraction failure reason in response envelope | Low |

---

## Active env flags (extractor lane)

| Flag | Default | Purpose |
|---|---|---|
| `HORNELORE_TRUTH_V2` | 1 | Facts write freeze |
| `HORNELORE_TRUTH_V2_PROFILE` | 1 | Profile reads from promoted truth |
| `HORNELORE_PHASE_AWARE_QUESTIONS` | 0 | Phase-aware question composer |
| `HORNELORE_AGE_VALIDATOR` | 0 | Age-math plausibility filter |
| `HORNELORE_CLAIMS_VALIDATORS` | 1 | Value-shape, relation, confidence validators |
| `HORNELORE_TWOPASS_EXTRACT` | 0 | Two-pass extraction (REGRESSED — keep OFF) |
| `HORNELORE_NARRATIVE` | 1 | Phase 2 tighten + DATE-RANGE PREFERENCE |
| `HORNELORE_ATTRIB_BOUNDARY` | 0 | r5e2 ATTRIBUTION-BOUNDARY (in-tree default-off) |
| `HORNELORE_PROMPTSHRINK` | 0 | Topic-scoped dynamic few-shot (in-tree default-off) |
| `HORNELORE_SILENT_DEBUG` | 0 | Raw-output dump for silent-cause classification |
| `HORNELORE_SPANTAG` | 0 | Two-pass span tag → bind (Commit 3 landed default-off; awaiting clean `r5f-spantag` eval) |
| `SPANTAG_PASS1_MAX_NEW` | 512 | Pass 1 token cap (raise to 1024 to fix Pass 1 truncation observed in ad-hoc r5f-spantag session) |
| `SPANTAG_PASS2_MAX_NEW` | 1024 | Pass 2 token cap (raise to 1536 alongside Pass 1) |
| `HORNELORE_PHOTO_SHARED` | 0 | Phase 1 photo authority layer (Backend complete; UI in flight) |

---

## Reference docs

| File | What |
|---|---|
| `CLAUDE.md` | Agent env + standard eval block + extractor changelog |
| `README.md` | Product surface + OT framing + Status as of 2026-04-25 |
| `HANDOFF.md` | Laptop bring-up + bring-up snags + 3-terminal eval methodology |
| `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` | Canonical extractor architecture spec — Core Law + Type A/B/C typology + 5-layer pipeline. Required reading before any extractor-lane WO |
| `docs/reports/CODE-REVIEW-2026-04-25.md` | This week's tech-debt audit; Bug #219 P0 |
| `WO-LORI-CONFIRM-01_PREP_PACK.md` | Prep pack for confirmation pass v1 |
| `WO-EX-SECTION-EFFECT-01_PHASE3_WO.md` | Boris-style execution pack for Phase 3 (now closed PARK) |
| `WO-EX-SPANTAG-01_FULL_WO.md` | Two-pass span tag spec; commits 3–6 |
| `WO-EX-BINDING-01_Spec.md` | v2 spec, Option A primary; PATCH 1–5 |
| `WO-AUDIO-NARRATOR-ONLY-01_Spec.md` | Per-turn webm capture spec |
| `WO-STT-HANDSFREE-01A_Spec.md` | Auto-rearm STT spec (deferred past first parent session) |
| `WO-EVAL-MULTITURN-01_Spec.md` | Parked multi-turn harness spec |
| `docs/reports/FAILING_CASES_r5h_RUNDOWN.md` | 34-case rundown by narrator × phase × failure_category × score bucket |

---

## Big picture

```
ARCHIVE -> HISTORY -> MEMOIR
```

Right now we are building **ARCHIVE** correctly. That is the foundation for everything else. Tomorrow morning's milestone is one clean parent-session-to-export round-trip: open Hornelore → select a parent → run Questionnaire First → talk for 5–10 minutes → click Export → open the transcript and audio. Once that round-trip works, parents become the data acquisition pipeline that improves extraction beyond the synthetic 70/104 bench.
