# Hornelore → Lorevox Graduation Audit — 2026-05-01

**Author:** overnight pass, Hornelore agent.
**Audience:** Chris, when he sits down at Lorevox.
**Purpose:** identify what Hornelore has built since the 2026-04 promotion queue (locked in `/sessions/ecstatic-determined-pasteur/mnt/lorevox/README.md` "Hornelore Promotion Queue (2026-04)") that is now stable enough to consider for distillation into Lorevox. **This is an audit, not a port plan.** No code is moved by this document. Each candidate gets a deliberate posture (PROMOTE / HOLD / HORNELORE-ONLY) so Chris can decide on a calm morning whether and how to graduate it.

The relationship rule from the Lorevox README still holds: features move by deliberate promotion, never by file-parity backport. The `/hornelore` subfolder inside the Lorevox repo (which already contains the 2025-vintage `Hornelore-1.0-*.docx` reports + an early Hornelore snapshot) is a historical reference layer — not a sync target. New graduations land as fresh, generalized code in the appropriate Lorevox lane (`server/code/api/`, `server/code/api/services/`, `server/code/api/routers/`, `ui/js/`, `ui/css/`).

## Posture key

- **PROMOTE** — proven against real older-adult narrators (Kent/Janice/Christopher) or against deterministic regression evidence; Horne-family-specific assumptions can be stripped cleanly; ready for distillation.
- **HOLD** — works in Hornelore but still iterating against a measurable acceptance threshold; promote when the threshold locks.
- **HORNELORE-ONLY** — exists because Hornelore is a family-locked R&D crucible; promoting would be a category mistake.

Each PROMOTE candidate carries a **strip list** — the Horne-family assumptions to remove during graduation — and a **landing site** suggestion in the Lorevox tree.

---

## A. Proven in Hornelore — ready to promote (NEW since 2026-04 queue)

These are artifacts that have landed since the 2026-04 promotion queue snapshot. They are the new entries; the 2026-04 list (four-layer truth pipeline, photo system, document archive, memory archive, three-tab UI shell, narrator room layout, cognitive support model, bio-builder contamination hardening, operator UI health check harness, soft transcript review cue, audio preflight check, chronology accordion) remains valid and unchanged where not superseded below.

### A1. WO-LORI-STORY-CAPTURE-01 Phase 1A + 1B — golfball architecture **(PROMOTE)**

**What it is.** A separately-architected story-preservation lane that lives parallel to the extractor. When a narrator turn looks like a story (≥30s, ≥60 words, ≥1 scene anchor — OR the borderline path of ≥3 scene anchors regardless of duration), the raw transcript is preserved as a `story_candidate` row before any extraction runs. Path 1 (preservation) must succeed; Path 2 (extraction) is best-effort and can fail without losing the story.

**Why it matters for Lorevox.** It directly addresses BUG-212 ("questionnaire_first interrupts emotional disclosures, violates WO-10C 'no correction'") at the data layer rather than the behavior layer. Even when Lori's behavior layer steamrolls a disclosure, the story is now captured and surfaceable to the operator. This is structural protection of narrator dignity — exactly the kind of thing the Lorevox `Product Principles` list is built to enforce.

**The "golfball" framing.** The spec (`WO-LORI-STORY-CAPTURE-01_Spec.md`) lays out a four-shell architecture: CORE (Path 1 preservation, must-succeed), WINDINGS (Path 2 extraction, best-effort), COVER (operator review surface), PARTNER (future Lori-side narration). Six LAWs with a four-classification system (RUBBERBAND behavioral / WALL deterministic / STRUCTURAL system flow / INFRASTRUCTURE impossible-to-violate-in-code). LAW 3 (story_preservation can never import extraction stack) is enforced by an AST-walking unit test that fails the build on any forbidden-prefix import — that's the INFRASTRUCTURE class.

**Files in Hornelore.**
- `server/code/api/services/story_preservation.py`
- `server/code/api/services/story_trigger.py` (Tier-1/Tier-2 place-noun detection, conservative bigram anchor classifier; Janice-canonical mastoidectomy text fires 3 anchors)
- `server/code/api/services/age_arithmetic.py` (DOB + age_bucket → year arithmetic, multi-era ambiguity preserved as list)
- `server/code/db/migrations/0004_story_candidates.sql`
- `server/code/api/routers/operator_story_review.py` (read-only `GET /api/operator/story-candidates`, gated `HORNELORE_OPERATOR_STORY_REVIEW=0`)
- `ui/js/bug-panel-story-review.js` + `ui/css/bug-panel-story-review.css`
- `tests/test_story_preservation.py`, `test_story_preservation_isolation.py`, `test_age_arithmetic.py`, `test_story_trigger.py` (114/114 pass)
- `docs/golfball/{README.md, dialogue-2026-04-30.md, PHASE_1A_BUG_SWEEP_2026-04-30.md}` (lineage)

**Strip list.**
- `HORNELORE_*` env-flag prefix → `LOREVOX_*`.
- The Bug Panel mount section (`#lv10dBpStoryReview`) collapses into Lorevox's existing operator UI surface — the Phase 1B section is read-only and small enough to live anywhere there's an operator-only column.
- Tier-1/Tier-2 place-noun lists (hospital/church/factory/plant/mill/fairgrounds + the prep-required tier) are linguistically generic — keep them. The Janice-canonical test fixture should generalize to any older narrator's medical-event story; review for U.S.-centric place nouns and add region-aware extensions when Lorevox grows beyond U.S. narrators.

**Landing site.** `server/code/api/services/story_preservation.py` + `story_trigger.py` + `age_arithmetic.py` (parallel to the existing `media_archive`, `photo_intake`, `photo_elicit` services); migration `0004_story_candidates.sql`; new router `operator_story_review.py`; UI section in whatever Lorevox calls its operator surface (Lorevox doesn't have a Bug Panel — it has the v9 Operator tab).

**Open question for Chris.** Phase 2 of the spec adds a `story_capture` `turn_mode` to `prompt_composer.py` — Lori behavior change to slow down on memorable turns. That's still Hornelore-only until the parent-session readiness gates pass. Phase 1A + 1B (preservation + read-only review) graduate cleanly *without* Phase 2. The spec is written so the two phases decouple.

### A2. WO-LORI-SAFETY-INTEGRATION-01 Phase 1 + Phase 3 — chat-path safety hook + operator banner **(PROMOTE — highest priority)**

**What it is.** Lorevox's existing safety surface (the `safety.py` 50+ regex patterns + 7 categories + `RESOURCE_CARDS`, plus the `prompt_composer.py` ACUTE SAFETY RULE template) was already proven, but it was only wired into `/api/interview/answer`. The chat WebSocket path (`/api/chat/ws`) had **zero deterministic safety**. Phase 1 wires the existing `safety.py` `scan_answer()` into chat_ws *before* Lori responds, with a default-safe exception-handler fallback (any scanner failure forces `turn_mode="interview"` so the LLM-side ACUTE SAFETY RULE still fires; emits `[chat_ws][safety][default-safe]` log marker). Phase 3 adds the operator notification surface — Bug Panel banner card per unacknowledged event, acknowledge button, no scores no severity ranks no longitudinal trends.

**Why it matters for Lorevox.** This is the biggest functional safety gap in Lorevox right now. Every Lorevox narrator session that runs through the chat path (which is virtually all of them — `/api/interview/answer` is mostly the questionnaire dispatcher) is going through with LLM-only safety. The Hornelore Phase 1 hook is a 17-line patch with default-safe semantics; it costs nothing to ship and closes a real liability.

**Files in Hornelore.**
- `server/code/api/routers/chat_ws.py` L196-274 (the actual hook + default-safe fallback)
- `server/code/api/routers/safety_events.py` (operator surface — list, acknowledge, count)
- `ui/js/safety-banner.js` + the existing `ui/css/lori80.css` styles (banner cards inside Bug Panel)
- DB tables `interview_segment_flags` + `interview_sessions.softened_turn` (already in Lorevox schema; the Hornelore-side surface adds an `acknowledged_at` / `acknowledged_by` column and an unacked-only filter)
- `db_inspector.py` gate change (`HORNELORE_DB_INSPECTOR=0` default-OFF) — the inspector existed in Lorevox already; the gate change is a graduation-worthy hardening.

**Strip list.**
- The hook itself is generic — it just calls `safety.scan_answer()` which Lorevox already has.
- The banner styling in Hornelore lives in `bug-panel-*.css` — port to Lorevox's operator-tab CSS.
- Operator-notify is `[CHAT_WS][SAFETY] event_id=…` log + DB row + UI card; matches Lorevox's existing diagnostic style.
- Friendship Line resource (1-800-971-0016 for 60+) is U.S.-specific; Lorevox should extend with region-aware crisis resources as it broadens.

**Landing site.** `server/code/api/routers/chat_ws.py` (the wire), `server/code/api/routers/safety_events.py` (new), Lorevox's operator-tab UI for the banner.

**Open question for Chris.** The Lorevox README pre-parent-session checklist already lists "Safety detection wired into `/api/chat/ws`" as a gate. Phase 1 closes that. Phase 2 (LLM second-layer classifier for indirect ideation) and Phases 4–9 (warm-first IDEATION/DISTRESSED prompt, Friendship Line, kill-switch flag, red-team pack, runbook, consent disclosure) remain pending in Hornelore. The Phase 1 + Phase 3 pair graduates without those. **Recommend graduating these two phases first as a standalone safety landing in Lorevox.**

### A3. WO-OPERATOR-DASHBOARD-MERGE-01 — unified operator cockpit **(PROMOTE)**

**What it is.** A single Bug Panel that surfaces six gated read-only views: Eval Harness (extractor + behavior + safety + story-surfaces status), Stack Dashboard (CPU/GPU/VRAM/disk/memory polling), Heartbeat (camera/mic UI state), Story Review (unreviewed candidates), Safety Banner (unacked events), DB Inspector (read-only schema/row exploration). Each view is gated by a default-OFF env flag so the surface doesn't advertise itself when not wanted. All endpoints under `/api/operator/*` return 404 when the flag is off.

**Why it matters for Lorevox.** Lorevox today has the v9 Operator tab + a Test Lab for harness runs, but no live cockpit for "is the stack healthy and is anything in the danger zone right now." The Hornelore dashboard answers that question in one screen. The flag-gated discipline (`HORNELORE_OPERATOR_*=0` defaults, 404 when off) is the Lorevox-correct posture — the operator surface is a debugging tool, not a product feature.

**Files in Hornelore.**
- `server/code/api/services/stack_monitor.py`
- `server/code/api/routers/operator_stack_dashboard.py`, `operator_eval_harness.py`, `operator_story_review.py`, `safety_events.py`, `db_inspector.py`
- `ui/js/bug-panel-dashboard.js`, `bug-panel-dashboard-heartbeat.js`, `bug-panel-eval.js`, `bug-panel-softened-banner.js`, `bug-panel-story-review.js`, `safety-banner.js`
- `ui/css/bug-panel-eval.css`, `bug-panel-story-review.css` + the dashboard-specific CSS in `lori80.css`
- `scripts/stack_resource_logger.py` (background telemetry)
- All `.env.example` gate documentation

**Strip list.**
- Rename `HORNELORE_OPERATOR_*` flags to `LOREVOX_OPERATOR_*`.
- BUG-224 fix (frontend port 8082 vs API port 8000): the `const _O = (typeof ORIGIN !== "undefined" && ORIGIN) || "http://localhost:8000"` pattern in five frontend files. Lorevox should adopt the `ORIGIN` global pattern directly so its operator UI doesn't repeat this bug under a future split-port deployment.
- The eval-harness card calls Lorevox-specific eval names (extractor 70/104, etc.); generalize to "extractor master report freshness + topline" instead of the specific `r5h-*` suffix.

**Landing site.** Lorevox's Operator tab — the dashboard is a section, not a replacement.

### A4. Patches A + B — protected-identity validator + QF question-gate **(PROMOTE)**

**What it is.** Two surgical patches to `ui/js/session-loop.js`:
- **Patch A** extends `_validateProtectedIdentityValue` from 5 rules to 7. New rules: `question_not_answer` (rejects strings ending in `?` or matching wh-word + verb pattern), `imperative_command` (rejects `^(tell|show|give|help|explain|describe|list)\s+me\b`).
- **Patch B** adds `_isConversationalNonAnswer(text)` and a dispatcher gate before the digression check. When the QF walk receives conversational input ("tell me about you" / "what's the weather" / "huh?"), the walk doesn't advance — it stays on the current field and lets Lori respond conversationally instead of trying to bind the input as an answer.

**Why it matters for Lorevox.** Lorevox's identity-first onboarding has the same shape as Hornelore's QF walk. The validator strengthening prevents protected fields (fullName / preferredName / dateOfBirth / placeOfBirth / birthOrder) from being polluted by conversational input. The dispatcher gate prevents the QF walk from steamrolling. Both are pre-parent-session blockers in Hornelore; they're equally pre-first-narrator-session blockers in Lorevox.

**Files in Hornelore.** Single file: `ui/js/session-loop.js`. The validator additions are ~30 lines; the gate is ~15 lines + the helper.

**Strip list.** None. Both patches are generic.

**Landing site.** Lorevox's `ui/js/session-loop.js` (or its identity-first onboarding equivalent — Lorevox has slightly different file organization; the patch needs to land wherever the identity-phase dispatcher lives).

### A5. WO-PARENT-READINESS-HARNESS-01 — Playwright harness for 10-test pack **(PROMOTE — but generalize)**

**What it is.** A single-file Python Playwright harness (`scripts/ui/run_parent_session_readiness_harness.py`, ~2200 lines) that automates the 10-test manual `MANUAL-PARENT-READINESS-V1.md` pack. Headed Chromium, console arg capture via `msg.args.json_value()`, popover dismissal, port-fix consumers, narrator creation via UI clicks, identity completion helper, leap-year DOB regression-guard (TEST-12 Feb 29 1940), narration sample matrix (3 narrators × 4 sample sizes), HarnessReport dataclass with narration-only mode that renders absent static tests as SKIP.

**Why it matters for Lorevox.** Lorevox already has a Playwright-driven harness (`tests/`, `playwright.config.ts`) but it's organized around test-report files, not against a readiness gate pack. The Hornelore harness is a *gate*, not a coverage net — it returns a single pass/fail signal that's load-bearing for "can we put this in front of a real older narrator." That posture is Lorevox-correct because Lorevox's whole product is gated on first-narrator-session readiness.

**Files in Hornelore.** `scripts/ui/run_parent_session_readiness_harness.py` + `docs/test-packs/MANUAL-PARENT-READINESS-V1.md` + `docs/test-data/narration_samples.json` + `docs/test-packs/NARRATION_SAMPLES_AUTHORING_SPEC.md`.

**Strip list.**
- The 10-test pack is parent-specific (Kent + Janice + Christopher narrators); generalize to "first-narrator-session readiness" with parameterized narrator templates.
- The narration sample JSON has 3 fictional diverse narrators (Elena, Samuel, Rosa); already generic — just port.
- The leap-year regression-guard (TEST-12) is universal — keep.
- The "narration-only" CLI mode is generic — keep.

**Landing site.** `tests/parent_session_readiness/` (or `tests/first_narrator_readiness/` once renamed) as a sibling to Lorevox's existing test-report files.

**Open question for Chris.** This belongs in Lorevox once parent sessions land successfully in Hornelore. Promoting before the Hornelore parent sessions complete would be premature — the harness itself is still iterating on TEST-08 (era-button gate, real product question deferred to morning DOM inspection) and TEST-09 (first-turn timing). Mark this as PROMOTE-AFTER-PARENT-SESSION rather than PROMOTE-NOW.

### A6. WO-CANONICAL-LIFE-SPINE-01 — 7-era canonical spine + literary subtitles + Today **(PROMOTE)**

**What it is.** Migrates the entire Hornelore frontend + backend off legacy era keys (`early_childhood`, `midlife`, etc.) onto canonical 7-bucket era_ids (`earliest_years`, `early_school_years`, `adolescence`, `coming_of_age`, `building_years`, `later_years`, `today`). Includes a self-healing read/write layer (`_canonicalEra` + `_fallbackCanonicalEra` helpers in `state.js`, `legacy_key_to_era_id` accessor in `api/lv_eras.py`), a click-confirmation popover on Life Map era selection, and a "Today" memoir section that always renders last (even when blank — placeholder section renders), with literary subtitles per era and a warm-heading discipline (subtitle suppressed when warmLabel === memoirTitle).

**Why it matters for Lorevox.** Lorevox today walks a 6-era spine (Early Childhood through Later Life). The 7-bucket model adds Adolescence as a standalone era (currently consumed inside `school_years` in Lorevox) and adds Today as a forward-facing closing section that lets the memoir end on the present rather than on Later Life. Both are narrator-dignity wins: adolescence is where a lot of formative identity work happens and folding it into school_years was an undersight; ending the memoir on Today makes the narrator the author of their ongoing story, not a subject whose life is summarized as past tense.

**Files in Hornelore.**
- `ui/js/state.js` (`_canonicalEra`, `_fallbackCanonicalEra`, `getCurrentEra` repair-on-read, `setEra` route)
- `ui/js/lv-eras.js` + `server/code/api/lv_eras.py` (canonical `LV_ERAS` registry)
- `ui/js/life-map.js`, `projection-map.js`, `interview.js`, `bio-builder-family-tree.js`, `app.js` (eraTags, label-as-ID fixes, `prettyEra` delegation, `ERA_PROMPTS` keys, `ERA_ROLE_RELEVANCE`, `ERA_THEME_KEYWORDS`, `TIMELINE_ORDER`, `ERA_AGE_MAP`, `activeFocusEra` subsystem off the "era:Label" antipattern, `_lvInterviewConfirmEra` popover)
- `ui/js/projection-sync.js` (BUG-312 protected_identity gate — protected fields require trusted source `human_edit` / `preload` / `profile_hydrate` for ANY write, not just overwrites)
- `server/code/api/prompt_composer.py`, `routers/chronology_accordion.py` (TIMELINE_ORDER from `LV_ERAS`, today ghost at current_year), `life_spine/engine.py` (CATALOGS keys canonical), `routers/extract.py` (`_normalize_date_value` docstring, `[extract][era-normalize]` log marker, `_BIRTH_CONTEXT_SECTIONS` dual guard)
- `ui/hornelore1.0.html` (`_lv80MakeSection` helper, new `lv80RenderAdolescence` 7th renderer, `lv80BuildMemoirSections` reordered with Today last, `_memoirBuildTxtContent` structured-state branch with `data-era-id` selectors)
- `ui/css/lori80.css` (`memoir-section-subtitle`, `memoir-placeholder-section`, `lv-interview-confirm-*` popover)

**Strip list.**
- `LV_ERAS` registry generalizes cleanly; this is the canonical-spine-of-record across both products.
- The literary subtitles are Hornelore-authored but generic enough to keep; refresh language for Lorevox's broader audience tone.
- BUG-312 protected_identity gate is universal — port directly.

**Landing site.** Pervasive — every file in the strip list above maps cleanly to a Lorevox sibling. Recommend treating this as a major-version cut in Lorevox (e.g., the v10.1 distillation pass) rather than as a single landing.

**Open question for Chris.** Lorevox already shipped a 6-era spine in v10. The graduation here is *not* "drop in 7 eras instead of 6"; it's "adopt the canonical-spine-of-record discipline that v10's spine becomes a special-case of." Worth a deliberate v10.1 pass with operator review of the era-naming tone.

### A7. SESSION-AWARENESS-01 Phase 1 — memory_echo + chat_ws import fix + profile_seed wiring **(PROMOTE)**

**What it is.** Three small changes that together make Lori's "what do you know about me?" answer warm and grounded:
- `chat_ws.py` import fix: `from api.prompt_composer` → `from ..prompt_composer` (and the same for `api.memory_echo`). The broken late imports caused memory-echo crashes when the memory_echo composer or correction code paths executed.
- `compose_memory_echo` Phase 1a improvement in `prompt_composer.py`: surfaces `speaker_name` in body, renders explicit "(not on record yet)" instead of silent omission, adds `profile_seed` surface (childhood_home / parents_work / heritage / education / military / career / partner / children / life_stage), adds source citation footer ("Based on: …").
- `profile_seed` runtime data wiring (Phase 1b-minimum): the runtime payload now carries the profile seed fields so the composer has real data to surface.

**Why it matters for Lorevox.** Lorevox's runtime71 payload already supports rich state, but Lori's memory-echo answers tend to surface as system-tone outputs ("Based on: …" in the user-facing reply, "(not on record yet)" leaking through). Hornelore's Phase 1a moves the source-of-truth attribution operator-side and rewords the user-facing copy for elder narrators. This is a narrator-dignity win directly aligned with Lorevox's Product Principles #2 ("Hide the scaffolding") and #8 ("Recollection, not interrogation").

**Files in Hornelore.**
- `server/code/api/routers/chat_ws.py` (import fix)
- `server/code/api/prompt_composer.py` (compose_memory_echo Phase 1a + the four narrator-facing string edits in #330: 1-800-273-TALK softening, memory-echo elder-narrator rewording, NO QUESTION LISTS RULE narrowed to interview turn_mode, WO-10C cognitive-support framing aligned with banned-vocab spec)

**Strip list.** None — generic.

**Landing site.** Lorevox's `chat_ws.py` and `prompt_composer.py`.

### A8. WO-EX-EVAL-WRAPPER-01 spec — single-command extractor eval workflow **(HOLD — spec only; build before any future Lorevox extractor lane)**

**What it is.** A spec for `./scripts/run_extractor_eval.sh <suffix> [--spantag on|off]` that wraps the existing eval scripts with refusal-on-failure gates: `.env` flip + verify, stack restart with idempotency, HTTP listener wait, LLM warmup probe with extract-roundtrip threshold (not just `/health`), fresh-only log filter for SPANTAG verification, eval execution, inline post-eval summary (topline + value-coerce/spantag greps + failure categories + named regressions). Wraps existing scripts; adds NO new eval logic.

**Why it matters for Lorevox.** Lorevox doesn't have an active extractor eval lane today (its extractor work is HOLD per the 2026-04 promotion queue), but the wrapper *spec* is a generic "how to run a guarded eval" pattern. Worth saving for Lorevox to adopt if/when it stands up its own extractor eval cadence.

**Files in Hornelore.** `WO-EX-EVAL-WRAPPER-01_Spec.md`. **Note:** the wrapper itself has not been built — only the spec exists. The spec is the artifact worth graduating as a reference, not a working tool.

**Landing site.** Lorevox `docs/specs/` as a reference, to be picked up if a Lorevox extractor lane re-opens.

### A9. BUG-EX-PLACE-LASTNAME-01 — deterministic post-LLM regex guard **(HOLD — Hornelore-evidence-bound)**

**What it is.** A regex guard at extract.py that drops `.lastName` / `.maidenName` / `.middleName` candidates whose value appears in source text only after a place-preposition (`born in X`, `from X`, etc.) with no explicit name evidence. Six new eval fixtures (cases 105–110). 5 of 6 pass; case_110 fails on a separate field-path-mismatch lane.

**Why it matters for Lorevox.** Lorevox's extractor is in HOLD posture per the 2026-04 queue. This guard is targeting Type C binding errors (per the canonical Architecture Spec v1) and only graduates if/when Lorevox's extractor lane re-opens. Filing as HOLD; the Hornelore test fixtures and the regex itself are the durable artifacts.

**Files in Hornelore.** `server/code/api/routers/extract.py` (the guard) + `data/qa/question_bank_extraction_cases.json` (cases 105–110).

### A10. Lorevox Extractor Architecture Spec v1 **(PROMOTE — as canonical reference)**

**What it is.** `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md` — 12 sections + two appendices (system-map causal-flow diagram + one-page quick reference). Core Law LOCKED: *Extraction is semantics-driven, but errors arise from failures in causal attribution at the binding layer.* Five-layer pipeline: Architectural / Control / Binding (PRIMARY FAILURE SURFACE) / Decision / Evaluation. Type A/B/C question typology LOCKED. Fix → WO mapping through BINDING-01 / SPANTAG / FIELD-CARDINALITY-01 / SCHEMA-ANCESTOR-EXPAND-01 / VALUE-ALT-CREDIT-01.

**Why it matters for Lorevox.** This document is *named* the Lorevox Extractor Architecture Spec — it was written from day one as the canonical reference for the cross-product extractor lane, not as a Hornelore artifact. It already lives in `docs/specs/` in Hornelore. Promoting is a verbatim copy.

**Strip list.** None.

**Landing site.** Lorevox `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`.

---

## B. Existing 2026-04 promotion queue — status update

The Lorevox README's "Hornelore Promotion Queue (2026-04)" is still substantively correct. Quick refresh of items where the Hornelore status has moved:

- **Four-layer truth pipeline (WO-13).** Status unchanged — promote-ready.
- **Photo system.** Hornelore-side has gained PEOPLE-EDIT, narrator-room lightbox (BUG-240), CORS spec compliance fixes (BUG-PHOTO-CORS-01), and a per-photo edit UI for old/no-EXIF photos. Net-additional Hornelore work since 2026-04 strengthens the case for promotion. Strip list unchanged: `HORNELORE_PHOTO_INTAKE` flag → `LOREVOX_PHOTO_INTAKE`, Horne-narrator pre-seeding removed.
- **Document Archive / Memory Archive.** Memory archive gained per-turn audio capture endpoint + per-session zip export + per-turn metadata stamping (session_style, identity_phase, bb_field, timestamp, session_id, writer_role) since 2026-04. Document archive remains scoped-not-built.
- **Three-tab UI shell + narrator room.** Hornelore-side has retired Memory River as a UI surface (kept as research citation only — see RETIRED below) per 2026-05-01 design decision. Lorevox README still describes Memory River; recommend a deliberate audit pass on whether Lorevox follows Hornelore in retiring it.
- **Cognitive Support Model (WO-10C).** Status unchanged — single strongest distillable artifact; promote-ready.
- **Bio Builder contamination hardening.** Status unchanged — promote-ready.
- **Operator UI Health Check harness.** Superseded in Hornelore by the unified Operator Dashboard (A3 above). The 15-category PASS/WARN/FAIL/DISABLED/NOT_INSTALLED/SKIP/INFO grid is still in Hornelore but the dashboard is the more powerful surface.
- **Soft transcript review cue + audio preflight.** Status unchanged — both promote-ready.
- **Chronology Accordion (WO-CR).** Status unchanged — generalizes cleanly.

---

## C. Still in flux — keep in Hornelore until stable

Carried forward from the 2026-04 queue with status updates:

- **Extractor pipeline hardening (WO-EX series).** Active baseline `r5h` (70/104, v3=41/62, v2=35/62, mnw=2). Master eval `r5h-overnight-2026-05-01` running at time of writing. SPANTAG default-on REJECTED at v3 (-39 cases due to binding-layer hallucination); BINDING-01 PATCH 1-4 + micro-patch landed but default-off pending next iteration. Lorevox's existing `Pending` posture is correct.
- **WO-EX-SPANTAG-01.** Same — code in-tree behind `HORNELORE_SPANTAG=0` default, gated for further iteration.
- **WO-EX-BINDING-01.** Now SHIPPED + ITERATING (was "next to implement" in 2026-04 queue snapshot). Default-off; second eval cycle pending.
- **WO-LORI-CONFIRM-01.** Parked at v1 spec; reactivates after SPANTAG.
- **Phase-aware question composer.** Status unchanged — working but flag-gated.
- **WO-LORI-PHOTO-ELICIT-01 Phase 2.** Spec ready; LLM prompts pending.
- **WO-MEDIA-WATCHFOLDER-01 / WO-MEDIA-OCR-01 / WO-MEDIA-ARCHIVE-CANDIDATES-01.** Scoped, not built.
- **Kawa Model integration (WO-KAWA series).** **STATUS CHANGE — RETIRED 2026-05-01.** See RETIRED below. Should be removed from the Lorevox `Pending` and `In flux` lists.

### NEW IN-FLUX (added since 2026-04)

- **WO-LORI-SESSION-AWARENESS-01 Phase 2 (interview discipline composer guard) + Phase 3 (MediaPipe attention cue) + Phase 4 (Adaptive Narrator Silence Ladder).** Phase 1 PROMOTE-ready (A7 above). Phases 2–4 still iterating.
- **WO-LORI-STORY-CAPTURE-01 Phase 2 (story_capture turn mode in prompt_composer).** Phase 1A + 1B PROMOTE-ready (A1 above). Phase 2 (Lori behavior change) parked behind parent-session readiness.
- **WO-PARENT-KIOSK-01.** Spec authored; Chrome kiosk first per tested mic/camera path. Hornelore-only by design unless Lorevox grows a kiosk deployment story (currently it doesn't).
- **WO-EX-GPU-CONTEXT-01.** Spec authored; 6-phase GPU OOM resilience plan (VRAM probe → context-budget calculator → OOM recovery + UI fallback → KV cache lifecycle → eval gate → operator dashboard surface). Hard rule: "GPU memory" / "CUDA" / "VRAM" / traceback strings must NEVER reach narrator. Generic enough to graduate as a spec; not yet built.
- **WO-EX-NESTED-BINDING-01.** Spec only.
- **WO-EX-FIELDPATH-NORMALIZE-01.** Spec only.
- **WO-LORI-RESPONSE-HARNESS-01.** Spec only — response-quality test harness orthogonal to extraction evals; Bug Panel summaries + Test Lab runs scenarios; deterministic scoring foundational, LLM-judged metrics never load-bearing. Recommend graduating as a spec to Lorevox alongside the operator dashboard.

---

## D. Hornelore-only by design

Carried forward unchanged from 2026-04 queue. No changes:
- Closed Horne narrator universe.
- Pre-seeded Horne identity.
- Family templates (`kent-james-horne.json`, `janice-josephine-horne.json`, `christopher-todd-horne.json` — note: Phase 1.5 enrichment added pets + stepchildren placeholder discipline; the discipline is generic but the data is Horne-specific).
- Bug Panel as a dev surface (the generic dashboard surface graduates per A3; the Hornelore-specific Bug Panel chrome stays).
- Local family-specific flags, fixtures, and parent-session runbooks.
- Quality Harness (WO-QA series).

---

## E. RETIRED 2026-05-01 — Kawa / Memory River

**Decision.** The river metaphor (Kawa Model, Memory River UI) is retired in Hornelore as system, UI, and logic. It is kept *only as a research citation* — the four papers in `docs/references/Kawa/` (OTI2023-2768898, TST.2024.9010104, The_Dynamic_Use_of_the_Kawa_Model_A_Scop, newbury-lape-2021-well-being-aging-in-place) support the academic framing of "narrator-as-theorist of their own life" for write-ups.

**Trigger.** During the 2026-04-30 audit pass, the broken "narrator-room Memory River view tab" was traced to a second navigation metaphor confusing both the model and the user. The implementation has converged on the canonical 7-era life spine + Life Map UI (see A6).

**Implication for Lorevox.** Lorevox's README still describes the Kawa/Memory River layer. **Recommend a deliberate audit on whether Lorevox follows Hornelore in retiring the river metaphor as UI.** The four design principles locked in Hornelore's `CLAUDE.md` (no dual metaphors, no operator leakage, no system-tone outputs, no partial resets) are Lorevox-correct; the dual-metaphor rule speaks directly to the Kawa decision.

**Note.** Retiring Kawa as UI does not necessarily mean retiring it as a research framing. Lorevox could keep "Memory River" as a marketing / explanatory metaphor for the *temporal flow* of memory while running the canonical 7-era spine as the actual nav surface. That's a Chris-side product call.

---

## F. What NOT to backport

- **The closed Horne narrator universe.** Hornelore's removal of "add narrator" UI + backend write guards is a R&D crucible posture; Lorevox has the opposite product requirement.
- **Pre-seeded Horne identity.** Lorevox identity-first onboarding starts with a blank narrator.
- **The Bug Panel chrome itself.** The dashboard *content* graduates (A3); the Hornelore-specific Bug Panel toolbar / Reset Identity / Purge Test Narrators / BB Walk Test harness do not.
- **The 70/104 r5h baseline.** Lorevox's extractor is in HOLD posture; the Hornelore baseline is not a Lorevox target.
- **Family-specific extraction tunings** (e.g., the Janice mastoidectomy canonical, the Kent occupation canon).
- **The `/hornelore` subfolder inside the Lorevox repo.** That folder contains 2025-vintage `.docx` reports + an early Hornelore snapshot. It's a historical reference layer, not a sync target. Do not cross-write between it and Hornelore-current.

---

## G. Recommended next moves (suggestion only — Chris's call)

These are sequenced by ROI for narrator dignity + safety first, infrastructure second, extractor lane last (matching the Lorevox README posture).

1. **Graduate WO-LORI-SAFETY-INTEGRATION-01 Phase 1 + Phase 3 to Lorevox.** Smallest patch; biggest safety win; closes the existing pre-parent-session gate already listed in Lorevox's README. Single graduation pass.
2. **Graduate Patches A + B (validator + QF question-gate).** Single-file patch to `session-loop.js` (or its Lorevox equivalent). Pre-first-narrator-session blocker.
3. **Graduate WO-LORI-STORY-CAPTURE-01 Phase 1A + 1B.** Self-contained service + migration + read-only operator surface. Ports cleanly because LAW 3 isolation is enforced by AST-walking unit test.
4. **Audit Kawa retirement question for Lorevox.** Chris-side product call — does Lorevox follow Hornelore in retiring the river metaphor as UI, or keep it as a parallel?
5. **Graduate SESSION-AWARENESS-01 Phase 1 (memory_echo + import fix + profile_seed wiring + the four narrator-facing string edits).** Small, generic, narrator-dignity win.
6. **Graduate WO-OPERATOR-DASHBOARD-MERGE-01 + the canonical Architecture Spec v1.** Both are operator-side / docs; no narrator-facing risk.
7. **Graduate WO-CANONICAL-LIFE-SPINE-01 as a v10.1 distillation pass.** Larger landing; treat as a deliberate version cut with operator review of era-naming tone.
8. **PROMOTE-AFTER-PARENT-SESSION queue:** Parent readiness harness (A5), photo system Hornelore-side improvements (PEOPLE-EDIT, lightbox, CORS, no-EXIF edit), memory archive enhancements.
9. **Specs-only graduations** (no code, but worth banking in Lorevox docs for reference): WO-EX-EVAL-WRAPPER-01, WO-EX-GPU-CONTEXT-01, WO-LORI-RESPONSE-HARNESS-01.

---

## H. Open questions for Chris

1. **Kawa retirement scope.** Hornelore retired Memory River as UI. Lorevox README still describes it. Audit and decide.
2. **Era model.** Adopt the canonical 7-bucket spine in Lorevox v10.1, or keep the v10 6-era model?
3. **Operator surface.** Where does the unified dashboard land in Lorevox — extending the existing v9 Operator tab, or a new tab?
4. **Story capture Phase 2.** When the parent-session readiness gates pass and Phase 2 (Lori behavior change for `story_capture` turn mode) graduates from HOLD to PROMOTE, should it be merged with Lorevox's WO-LORI-PHOTO-ELICIT-01 Phase 2 (Lori narrating over photos in narrator room) since both are "Lori slows down on memorable moments" turn-mode shifts?
5. **Safety rollout.** Does Phase 1 + Phase 3 graduate as a standalone safety landing, or as part of a larger "narrator-readiness" cut that also includes Patches A + B + Phase 1a memory_echo?

---

## Sources

This audit was assembled from direct read of the following files (all in this Hornelore session's workspace mount):

- `CLAUDE.md` (Hornelore project posture + changelog)
- `MASTER_WORK_ORDER_CHECKLIST.md` (current WO state)
- `WO-LORI-STORY-CAPTURE-01_Spec.md`
- `WO-LORI-SAFETY-INTEGRATION-01_Spec.md`
- `WO-PARENT-SESSION-HARDENING-01_Spec.md`
- `WO-PARENT-KIOSK-01_Spec.md`
- `WO-EX-GPU-CONTEXT-01_Spec.md`
- `WO-EX-EVAL-WRAPPER-01_Spec.md`
- `WO-LORI-SESSION-AWARENESS-01_Spec.md`
- `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`
- `docs/golfball/{README.md, dialogue-2026-04-30.md, PHASE_1A_BUG_SWEEP_2026-04-30.md}`
- `docs/reports/CODE_REVIEW_2026-05-01_OVERNIGHT.md`
- `/sessions/ecstatic-determined-pasteur/mnt/lorevox/README.md` (Lorevox posture + 2026-04 promotion queue)
- `/sessions/ecstatic-determined-pasteur/mnt/lorevox/LOREVOX_ARCHITECTURE.md`
- Direct file inventory of both Hornelore and Lorevox repos (services, routers, migrations, ui/js).
