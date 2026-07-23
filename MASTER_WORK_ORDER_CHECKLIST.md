# MASTER_WORK_ORDER_CHECKLIST

**Active as of:** 2026-07-23 (live-verification pass on the running stack — migrations 0034/0035, trip API baseline, Travel Doc smoke, and response-guard health all GREEN; INC-2026-07-09 response-guard outage closed; camera-consent ambush + extractor guards + trip-create day-count + public-lookup wording fixed. See README "Status as of 2026-07-23" and the CLAUDE.md 2026-07-14 changelog entry.)
**Previously:** 2026-07-11 (doc-consistency pass — split "code landed" vs "flag live" vs "formal verification" statuses per Chris's audit; 2026-07-11 HIGH repo-review batch closed via commits ebe64af / cf62c49 / round-2 / round-3), 2026-07-02 (code-vs-checklist adjudication — ALL six build-sequence WOs verified LANDED in-tree; trip-lane conversation layer at 62/72→GREEN pending harness re-verify; Spanish-detection overfire class fixed), 2026-06-16 (post Phase 3+4+5+6+7.5 of QUESTIONNAIRE-BIO-FACTS-MIGRATE), 2026-06-14 (post-universal-pivot)

---

## Status legend (locked 2026-07-11)

Three distinct dimensions — do NOT conflate them:

- **CODE-LANDED** — the implementation exists in-tree, has unit-test coverage, and AST-parses clean. Verifiable by reading the code.
- **FLAG-LIVE** — the corresponding `HORNELORE_*` env flag is set to `1` in the running `.env`, so the code path actually fires in real sessions. Verifiable by reading `.env` + api.log startup line.
- **FORMAL-VERIFIED** — a written verification report exists in `docs/reports/` demonstrating the feature works under a target scenario (red-team pack, canary session, harness eval, live-narrator transcript). Verifiable by opening the report.

Something can be code-landed but not flag-live (behind a default-off flag). Something can be code-landed AND flag-live but not formal-verified (running in the wild but no written proof yet). "LANDED" without qualifier historically meant code-landed; from 2026-07-11 forward the word alone is deprecated — use one of the three explicit terms.
**Supersedes:** Pre-pivot checklist (archived at `docs/archive/handoffs-pre-pivot/MASTER_WORK_ORDER_CHECKLIST.md`)
**Read first:** [`docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`](docs/architecture/HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md), [`docs/architecture/LORI-RUNTIME-ARCHITECTURE.md`](docs/architecture/LORI-RUNTIME-ARCHITECTURE.md)

---

## Posture

Hornelore is Lorevox. The Horne family is tenant zero, not a special case in the architecture. Every WO from this date forward is written against the universal assumption: Lori must work for narrators she has never met. Pre-pivot WOs (114 specs, locked-narrator framing) are archived at `docs/archive/workorders-pre-pivot/` for traceability — they are not the active source of truth.

Interview default is moving from questionnaire-first to **oral-history-as-default**. Structured styles become operator-selectable overrides.

---

## Build sequence — one Cowork session per WO, in order

Each WO gets its own Cowork session with the WO spec as the brief. Do NOT start more than one at a time.

| # | WO | File | Closes / Introduces |
|---|---|---|---|
| 1 | SAFETY-LLM-CLASSIFIER | [`docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md`](docs/wo/WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md) | Closes Gate 5 (soft-trigger safety) — **LANDED (verified in-tree 2026-07-02):** `safety_classifier.py` 3-dim taxonomy + LLM layer + confidence floor + 44 tests; gated `HORNELORE_SAFETY_LLM_LAYER=0` |
| 2 | SOFTENED-MODE-PERSISTENCE | [`docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md`](docs/wo/WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md) | Closes Gate 6 (post-safety recovery) — **LANDED (verified in-tree 2026-07-02):** `lori_softened_response.py` 3-state machine + per-trigger caps (30/35/50) + 32 tests; gated `HORNELORE_SOFTENED_RESPONSE=0` |
| — | **Flag already flipped** | `HORNELORE_SAFETY_LLM_LAYER=1` + `HORNELORE_SOFTENED_RESPONSE=1` | ✅ **FLAG-LIVE 2026-07-05** (both `.env` values set). Remaining item is FORMAL-VERIFIED — red-team pack + softened-persistence harness against the live flag state. NOT a code-work blocker. |
| 3 | PHASE-9-DISCLOSURE-UPDATE | [`docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md`](docs/wo/WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md) | Consent disclosure edits — **LANDED (verified in-tree 2026-07-02):** three-tier disclosure + style descriptions in `docs/runbooks/SAFETY_OPERATOR_RUNBOOK.md` (docs-only WO) |
| 4 | STORY-FIRST-PHASE-1 | [`docs/wo/WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md`](docs/wo/WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md) | Oral-history behavior engine — **LANDED (verified in-tree 2026-07-02):** `reflection_grounding.py` + `story_momentum.py` + `thread_bank.py` + `question_hierarchy.py` + chat_ws wiring + 66 tests; REPORT-ONLY behind `HORNELORE_STORY_FIRST_PHASE_1=0` |
| 5 | ORAL-HISTORY-DEFAULT | [`docs/wo/WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md`](docs/wo/WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md) | Introduces `oral_history` style + makes it default — **LANDED AND ACTIVE (verified in-tree 2026-07-02):** style @ 90-word cap, system default in comm-control signatures, picker + 29 tests |
| 6 | BIO-BUILDER-UNIVERSAL | [`docs/wo/WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md`](docs/wo/WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md) | Four-tier Bio Builder — **LANDED (verified in-tree 2026-07-02):** `bio_fact_router.py` + `document_authority.py` + `bio_anchored_asker.py` + `bio_gap_map.py` + 3 creep defenses + 66 tests; gated `HORNELORE_BIO_*=0` |
| 6a | OPERATOR-NEW-NARRATOR-INTAKE-FORM-01 | (root WO, 2026-06-15) | 9-section intake form + Phase 2B orchestrator + Phase 2C modal — **LANDED** |
| 6b | QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 | [`docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md`](docs/wo/WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01_Spec.md) | Phase 1 read swap + Phase 2 FE badges + Phase 3 write fan-out + Phase 4 primary_career bug + Phase 5 23-test pack + Phase 6 self-review + Phase 7.5 backfill readiness — **LANDED 2026-06-16**, Phase 7 live verify pending |
| 7 | MEMORY-EXERCISE-IMPLEMENTATION | (not yet drafted) | Specced in [`docs/architecture/MEMORY-EXERCISE-DECISION.md`](docs/architecture/MEMORY-EXERCISE-DECISION.md) |

---

## Superseded / history

The two docs below land for design-history traceability. Do NOT build from them.

- [`docs/wo/superseded/WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md`](docs/wo/superseded/WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01_Spec.md) — merged into #1 SAFETY-LLM-CLASSIFIER
- [`docs/wo/superseded/PRE-BUILD-ADDITIONS.md`](docs/wo/superseded/PRE-BUILD-ADDITIONS.md) — changelog of edits already folded into the strategy + WO specs
- [`docs/wo/superseded/REDESIGN-DOC-HEADER-TO-PREPEND.md`](docs/wo/superseded/REDESIGN-DOC-HEADER-TO-PREPEND.md) — header block for `WO-INTERVIEW-PROCESS-REDESIGN-01`; target doesn't exist in repo, header was not applied

---

## Parent-session readiness gates (locked checklist)

Inherited from pre-pivot work. Pre-pivot evidence in `docs/archive/`; post-pivot evidence as it lands.

| Gate | Code | Flag | Formal | Lane / note |
|------|------|------|--------|-------------|
| 1. DB lock fix | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 2. Atomicity discipline | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 3. Story preservation | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 4. Safety acute path | ✅ landed | ✅ live | ✅ verified | pre-pivot |
| 5. Safety soft-trigger | ✅ landed 2026-07-02 (`safety_classifier.py`, 44 tests) | ✅ live 2026-07-05 (`HORNELORE_SAFETY_LLM_LAYER=1` in `.env`) | 🟡 pending | Remaining: red-team pack on live flags; report → `docs/reports/`. Also `SafetyResult` NameError in `chat_ws.py` closed 2026-07-11 via `ebe64af` — no more silent no-op on trigger. |
| 6. Post-safety recovery | ✅ landed 2026-07-02 (`lori_softened_response.py`, 32 tests) | ✅ live 2026-07-05 (`HORNELORE_SOFTENED_RESPONSE=1` in `.env`) | 🟡 pending | Remaining: softened-persistence harness evidence on live flags (lockstep with Gate 5). |
| 7. Truth-pipeline observability | 🔴 not started | — | — | Scoped separately; not in the 6-WO sequence. Highest-priority unstarted lane. |

---

## Open work (locked 2026-07-23)

Priority order for what to build next. Items 1 + 2 (migration/trip verification, Travel Doc smoke) are **DONE** as of the 2026-07-23 live pass — the queue below is the remainder.

**✅ Closed 2026-07-23 (live-verified on the running stack):**

- **Migration 0034/0035 verification** — FK + orphan cleanup applied clean; 0 orphan trips; no FK-check errors.
- **Trip API live baseline** — bogus person_id → 422; create → auto-days; patch → renumber; delete → cleanup; real trips preserved; zero DB locks / FK failures / 500s. ND-incident class contained.
- **Travel Doc smoke (9 canaries)** — OCR text/textless, real+blocked lookup, approval ladder, Lori wording (no "I can see"/coords), capture scope. All green.
- **Response-guard health** — 0 `wrapper raised` in current boot; no first-person parrot. INC-2026-07-09 closed.
- **P1/P2 fixes** — trip-create surfaces `days_created` (+ Trips-tab message); public-lookup title suffix strip + spoken-context trim; camera-consent ambush; extractor affect-hedge + vague-temporal guards; narrator-label collision; modal-turns-as-life-story archive gate.

**Remaining open work (priority order):**

1. **C1b — end-to-end WebSocket safety-routing test** — indirect ideation → classifier → `SafetyResult` → segment flag → softened mode → operator-visible signal → safe reply. Not yet proven end-to-end; protects Kent & Janice. Highest-value open safety item.
2. **`.env.example` drift audit (NEW WO)** — codify a grep gate: `grep -oh 'os.getenv("[A-Z_]\+"' server/code/ | sort -u`. Compare against `.env.example`. Reconcile ~24 stale documented flags + ~30 code-referenced undocumented flags. Flag drift is becoming a real ops risk.
3. **TRUTH-PIPELINE-01 Phase 1 (Gate 7)** — observability stub across the five truth-write stages (`raw_turn_saved` / `archive_event_created` / `extract_fields_called` / `family_truth_written` / `projection_updated`) per harness turn. Highest-priority unstarted lane. Blocks the remaining 🟡 formal-verified marks on Gates 5 + 6 becoming ✅ (the harness needs turn-level truth-write visibility to distinguish a real bug from a harness coverage gap).
4. **`sysBubble()` narrator-dignity pass** — some operator-tone bubbles retired behind `LV_INLINE_OPERATOR_BUBBLES`; the full 28-call sweep is still open. Operator/status/debug strings must not write into narrator chat.
5. **Extraction Track D (measurement first)** — D1 Travel Doc binding-eval corpus (report-only, UI scope as expected binding), D2 `story_candidates` Path 2 (preserved story text → draft candidates, operator review, no auto-promotion), D3 `utterance_frame` first consumer (hints vs Travel Doc scope, report-only). No truth writes.
6. **QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 7 live verify** — code + tests landed 2026-06-16; live verify pending. Either finish it or explicitly park.
7. **WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01 draft** — ADR at `docs/architecture/MEMORY-EXERCISE-DECISION.md` says the style stays and needs a real implementation. Draft the WO spec before starting code.

## Travel Doc Lab finish-pass — CLOSED, live-smoked (2026-07-23)

The finish-pass ran as one batch and passed a 16-canary live smoke on the
restarted stack. **CLOSED:** native `window.prompt()` removal (in-panel drawers);
"Lori will say…" preview aligned with the backend spoken trim (OCR untrimmed);
evidence text editing (Edit → PATCH revokes approval + clears memoir); refresh of
day/public-context counts after evidence actions; context patch/delete
trip-scoping (wrong trip_id → **409** live); unbounded conv-cache cap;
`travel-documenter.js` double-send guard; **mortality/988 reply leak** (live:
mortality → no escalation/no 988, acute → still triggers + 988). **C1b**:
composed-chain test code-landed AND live WebSocket smoke passed (indirect
ideation → safety_triggered + 988 + warm reply). Live smoke also: boot clean, 0
`wrapper raised`, OCR text/textless fail-safe, both drawers, real+blocked lookup,
approval ladder, no article dump / "I can see" / coordinates.

Minor open: public lookup does not supersede prior lookup drafts (repeated
lookups accumulate → Lori repeats the context). Parallel to the OCR supersede
work; low priority.

Remaining queue (unchanged priority): `.env.example` audit → sysBubble dignity
pass → Gate 7 truth-pipeline observability → Track D measurement-first.

## Travel Doc Lab — original get-it-working batch (2026-07-23, superseded by the CLOSED block above)

Organized by **restart-need**, to kill the stop/start churn: do all FRONTEND
items first (browser reload only, no stack restart), then ONE backend batch +
ONE restart that also picks up the three already-committed-but-not-yet-live
backend fixes (mortality-988 exception, modal spoken-trim, trip days_created).

**✅ Working, live-verified (2026-07-23):** trip lifecycle (create/patch/delete +
auto-days), OCR (tesseract eng+deu+ita+hrv+slv, confidence-gated, fails safe),
public lookup (url_only, SSRF-blocked, title-clean at storage), approval ladder
(draft → approved → memoir, edit revokes), Lori modal wording (provenance, no "I
can see"/coords), capture (modal turns → trip notes, scope-tagged), day-card
generate/reconcile.

**⚙️ Off by config (not bugs — deliberate):** vision (`HORNELORE_PHOTO_VISION=0`;
operators use manual "Add draft observation" instead), trip narration
(`HORNELORE_TRIP_NARRATION=log`, dry-run — flip to `1` when ready to bank), all
command adapters empty (`OCR_CMD` / `VISION_CMD` / `LOOKUP_CMD`).

**FRONTEND-ONLY (reload, NO restart) — do freely:**

1. **Replace `window.prompt()` in the Lab evidence panel** (`travel-doc-lab.js`
   L2089 + L2104 — "Add draft observation" + "Infer place from context") with an
   in-panel text input. Violates the Lab's own locked no-native-dialog doctrine.
2. Laptop-width UX: rail-collapse persists (done); re-verify the photo gallery /
   inspector at ≤1440px after any layout change.

**BACKEND (batch → ONE restart):**

1. **Context patch/delete route trip-scoping** — `patch_photo_context` (L2464) /
   `delete_photo_context` (L2496) / `patch_public_context` (L2127) /
   `delete_public_context` (L2172) accept `context_id` alone. Single-tenant so
   not a security hole, but a stale FE cache could patch the wrong trip's row.
   Add a body/query trip_id scope check.
2. **`chat_ws._TRIP_PREV_LORI` + `_TRIP_LAST_CAPTURE` unbounded dicts** — cap or
   LRU-evict; memory-leak on a long-running process.
3. **`travel-documenter.js` modal double-send guard** — parity with the
   2026-05-07 chat-path `_loriIsBusy` fix.
4. Restart picks up these + the 3 already-committed backend fixes above.

**DEFERRED (not this pass — spec-only or gated):** vision provider wiring;
PaddleOCR / Brave / SearXNG; `WO-TRAVEL-DOC-ACCORDION-TIMELINE-01` (spec only);
`WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01` (spec only, deferred 2026-07-08);
`WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01` (TODO: timeline-bridge photo meta, cover-
photo control); `story_candidates` Path 2 (Track D).

---

**MEDIUM open items (not blocking, but named so they don't drift):**

- Context patch/delete route trip-scoping — see the Travel Doc Lab batch above.
- `chat_ws._TRIP_PREV_LORI` + `_TRIP_LAST_CAPTURE` unbounded module-level dicts (memory-leak on long-running processes).
- `travel-documenter.js` modal double-send guard (parity with the 2026-05-07 chat-path fix).
- 7 named misses in `narrative_cue_detector` eval pack (33/40 = 82.5%).
- Travel Doc Lab evidence panel — replace native `window.prompt()` for draft observation + place-from-context with an in-panel editor / drawer — see the Travel Doc Lab batch above (frontend-only).

**Older README-open items to triage (decide active / parked / superseded / closed):**

- `WO-AUDIO-NARRATOR-ONLY-01`
- `WO-STT-HANDSFREE-01A`
- `WO-MEDIA-WATCHFOLDER-01`
- `WO-MEDIA-OCR-01`
- `WO-MEDIA-ARCHIVE-CANDIDATES-01`

These sit in the historical README status text and should not stay there forever.

---

## Where things live now

```
docs/
  architecture/                      strategic ADRs + this session's brief
    HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md
    LORI-RUNTIME-ARCHITECTURE.md
    MEMORY-EXERCISE-DECISION.md
    COWORK-HANDOFF.md
  wo/                                active WO specs (build from these)
    WO-LORI-SAFETY-LLM-CLASSIFIER-01_Spec.md
    WO-LORI-SOFTENED-MODE-PERSISTENCE-01_Spec.md
    WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01_Spec.md
    WO-LORI-STORY-FIRST-PHASE-1-01_Spec.md
    WO-LORI-ORAL-HISTORY-DEFAULT-01_Spec.md
    WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md
    superseded/
  archive/
    workorders-pre-pivot/            114 pre-pivot specs (history only)
    handoffs-pre-pivot/              pre-pivot HANDOFF / MORNING / LAPTOP / CHECKLIST docs
  reports/                           eval reports, WO completion reports, .docx history
  (existing subtrees preserved: research/, specs/, observations/, voice_models/, …)
```

Root carries operational files only: `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `AGENT_CONTRACT.md`, `LICENSE`, this checklist, `.env`, `*.bat` launchers, top-level dirs (`launchers/`, `scripts/`, `server/`, `ui/`, `data/`, `docs/`, `tests/`).
