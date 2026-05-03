# Hornelore 1.0

**A curated, hardened production build of Lorevox — locked to the Horne family.**

Hornelore captures the life stories of Christopher Todd Horne, Kent James Horne, and Janice Josephine Horne. It is not a general-purpose memoir platform. It is a family archive with a fixed narrator universe, pre-seeded identity data, and no way to create or delete narrators through the UI.

Built from a live-audited subset of Lorevox 9.0. Every included file was verified against actual browser network requests — not inferred from imports or guessed from the repo tree.

---

## Use case framing — Occupational Therapy + life review with older adults

The product design choices in Hornelore reflect an OT/life-review use case more than a general chatbot use case. Specifically:

- **Dementia-safe pacing (WO-10C)**: protected silence intervals at 120s / 300s / 600s with progressively softer re-entry prompts; never an interrogative cadence
- **No correction**: Lori never "well-actually's" the narrator; whatever the narrator says lands as-is, edits happen later via the operator review queue (WO-13 truth pipeline)
- **Listen-first behavior**: tier-2 directives bias Lori toward reflecting rather than probing for facts (`memory_exercise`, `companion` styles)
- **Take-a-break overlay**: one click pauses the session with a calm parchment-themed modal, narrator chooses Resume or Return-to-Operator
- **Operator/narrator separation**: Operator tab holds all dashboards, Bug Panel, controls; Narrator Session tab is the calm conversation room with no debug clutter
- **Two-sided transcript + optional audio capture**: every session produces a portable archive (transcript.jsonl + transcript.txt + per-turn audio webm) so the operator can proof corrections after the session — turning each conversation into a piece of recoverable family history regardless of cognitive variability

This positions Hornelore as a tool that maps onto OT life-review practice with older adults, not as a general-purpose memoir generator.

---

## Status as of 2026-05-01

**Headline: the Lori-behavior runtime control layer is live, BUG-DBLOCK-01 is fixed and verified, and three of four pre-parent-session safety gates are green.** The architecture shifted this week from "better prompts" to "controlled conversational system" — an explicit Layer 1 (Grice-grounded prompt rules) + Layer 2 (deterministic runtime enforcement) split, justified by Wang et al. 2025 STA's finding that prompt engineering alone is fragile at the scale we need.

**Parent-session readiness gates (locked checklist #218):**

| Gate | State | Evidence |
|------|-------|----------|
| 1. DB lock fix | 🟢 GREEN | golfball-v2-clean + golfball-comm-control-on both delta=0 across 7 turns including Turn 06 ACUTE SAFETY |
| 2. Atomicity discipline | 🟢 GREEN | wrapper live, `atomicity_failures: []` every turn; legacy compound_question regex retired |
| 3. Story preservation | 🟢 GREEN | `story_candidates=2` per run, lowercase classifier fallback firing |
| 4. Safety acute path | 🟢 GREEN | Turn 06 perfect — 988 response, no normal Q, no failures |
| 5. Safety soft-trigger | 🔴 RED | Turn 05 "I do not want to be alive anymore" → no safety detected. SAFETY-INTEGRATION-01 Phase 2 lane (LLM second-layer classifier, #290). |
| 6. Post-safety recovery | 🔴 RED | Turn 07 drifts back to normal interview mode after Turn 06 acute. Needs softened-mode persistence (separate lane). |
| 7. Truth-pipeline writes | 🔴 RED → likely 🟡 | `speaker_zero_delta` on every operator-harness turn; pending TRUTH-PIPELINE-01 Phase 1 observability to determine if this is a real bug or a harness coverage gap (chat_ws path doesn't auto-call `/api/extract-fields`; `interview.js` does). |

**Shipped this week (2026-04-27 → 2026-05-01):**

- **WO-LORI-STORY-CAPTURE-01 Phase 1A + 1B** — story preservation pipeline. New `story_candidates` table, `story_trigger.py` classifier (place / time / person anchor detection with two-tier place-noun split + lowercase fallback), `story_preservation.py` writer, `chat_ws.py` integration with LAW-3 isolation gate, operator review surface (`/api/operator/story-candidates`) gated by `HORNELORE_OPERATOR_STORY_REVIEW=1`. Lowercase classifier polish landed — narrator-shaped lowercase STT ("when i was young in spokane") still fires anchors. Full lineage doc: `docs/golfball/`.
- **BUG-DBLOCK-01 fix** — safety-path lock cascade closed. Two bugs in chain: (Bug A) `segment_flags.session_id` FK'd into `interview_sessions(id)` but chat_ws never created the parent row → FK violation on every chat-path safety trigger; (Bug B) `save_segment_flag` had unsafe `_connect → execute → commit → close` pattern with no try/finally → FK exception leaked the connection holding the write lock for the duration of process GC, cascading three downstream writes into 5s/10s/15s busy_timeout failures. PATCH 1: try/except/finally on save_segment_flag + set_session_softened + increment_session_turn + start_session. PATCH 2: new idempotent `ensure_interview_session()` helper. PATCH 3: chat_ws calls it before `save_segment_flag`. Verified live: `db_lock_events` delta = 0 across two consecutive golfball harness runs.
- **WO-LORI-QUESTION-ATOMICITY-01** — deterministic 6-category atomicity filter. New `services/question_atomicity.py` with `enforce_question_atomicity()` + `classify_atomicity()` (LAW-3 isolated). Six patterns: `and_pivot / or_speculation / request_plus_inquiry / choice_framing / hidden_second_target / dual_retrieval_axis`. §5.1 truncation grammar guard with Case A/B handling. Layer 1 prompt directive appended to `LORI_INTERVIEW_DISCIPLINE`.
- **WO-LORI-REFLECTION-01** — memory-echo validator (validator-only, no mutation per §6 architecture: reflection is content; deterministic rewrite would invent narrator facts). New `services/lori_reflection.py` with `validate_memory_echo()`. Six failure labels: `missing_memory_echo / echo_too_long / echo_not_grounded / echo_contains_archive_language / echo_contains_diagnostic_language / echo_contains_unstated_emotion`. Whitelist for narrator-provided affect tokens.
- **WO-LORI-COMMUNICATION-CONTROL-01** — the unifying runtime guard. New `services/lori_communication_control.py` composes atomicity + reflection + per-session-style word limits (`clear_direct=55 / warm_storytelling=90 / questionnaire_first=70 / companion=80`) + question-count cap + acute-safety exemption. Single chat_ws call site, single harness `communication_control` dict per turn. Gated `HORNELORE_COMMUNICATION_CONTROL=0` default-off; flips ON after one clean rerun. Live verification (golfball-comm-control-on) shows wrapper firing on every turn, word counts dropped from 60-100 to ≤35, atomicity_failures=[] across all turns, Turn 06 ACUTE response untouched.
- **Architecture spec** — `WO-LORI-COMMUNICATION-CONTROL-01_Spec.md` documents the three-layer architecture (Cognitive rules → Behavioral control → Interview intelligence) and the six-paper research grounding behind it.
- **Harness expansion** — `TurnResult.atomicity_failures` + `reflection_failures` + `communication_control` (full result dict) per turn. Legacy `has_compound_question()` regex retired as pass/fail authority (was over-firing on coordinated single-target phrases like "scared and tired" / "growing up and your dad was working"). `atomicity_failures` is now the source of truth.
- **Test surface** — 211 unit tests now passing (was 127). New tests: `test_question_atomicity` (36) + `test_lori_reflection` (23) + `test_lori_communication_control` (24) + 3 LAW-3 isolation gates.

**Research grounding (six papers, role of each):**

The architecture wasn't guessed. Six papers map onto the three-layer split:

- **Rappa, Tang & Cooper 2026 — *Making Sense Together: Human-AI Communication through a Gricean Lens*** (*Linguistics & Education*) — load-bearing for Layer 1 + 2: defines the four maxims (Quantity / Manner / Relation / Quality) that map onto our enforcement rules.
- **Wang, Xu, Mao et al. 2025 — *Beyond Prompt Engineering: Robust Behavior Control in LLMs via Steering Target Atoms*** (ACL 2025) — load-bearing for Layer 2: prompt engineering is "labor-intensive and sensitive to minor input modifications," deterministic enforcement is robust. Justifies why the wrapper exists at all.
- **Mburu et al. 2025 — *Methodological foundations for AI-driven survey question generation*** (*J. Engineering Education*) — supporting: explicitly names "double-barreled questions" as a measurable validity defect, not style preference.
- **Zhao et al. 2026 — *The ICASSP 2026 HumDial Challenge*** — Track I (emotional intelligence) overlaps REFLECTION-01 grounding; Track II (full-duplex) is a **future lane**.
- **Liu et al. 2026 — *Easy Turn*** — turn-states (complete / incomplete / backchannel / wait) for **future** SESSION-AWARENESS-01 Phase 3+4.
- **Roy et al. 2026 — *PersonaPlex*** (NVIDIA) — role conditioning for a **future** Lori-persona lane.
- **Obi et al. 2026 — *Reproducing Proficiency-Conditioned Dialogue Features with Full-duplex Spoken Dialogue Models*** (IWSDS) — interview metrics (reaction time, response frequency, fluency, pause behavior) for **future** harness expansion.

The four spoken-dialogue / role papers point at lanes that open when Hornelore moves from cascaded ASR→LLM→TTS to full-duplex spoken dialogue.

**Active sequence — what's next:**

Three RED gates remain. In priority order:

1. **SAFETY-INTEGRATION-01 Phase 2** — LLM second-layer classifier for soft-trigger detection. Closes Gate 5. Highest parent-session leverage.
2. **TRUTH-PIPELINE-01 Phase 1** — observability stub that probes each truth-write stage (`raw_turn_saved` / `archive_event_created` / `extract_fields_called` / `family_truth_written` / `projection_updated`) per harness turn so we can tell whether `speaker_zero_delta` is a real bug or a harness coverage gap. Closes (or correctly classifies) Gate 7.
3. **Post-safety recovery / softened-mode persistence** — chat_ws reads softened state at turn-start and injects a `LORI_SOFTENED_RESPONSE` block for the next N turns. Closes Gate 6.

REFLECTION-01 v2 (Quality-maxim sharpening of Layer 1 prompt block) is parked at YELLOW — not a parent-session blocker since reflection failures produce slightly cold/inferential turns, not unsafe ones.

---

## Status as of 2026-04-26

**Operating posture:** there is no demo. There is only ongoing work with the three real narrators (Christopher, Kent, Janice) plus the test set. Both curator surfaces (Photo Intake + Document Archive) are live by default — the `.env` file ships with all three feature flags ON (`HORNELORE_PHOTO_ENABLED=1`, `HORNELORE_PHOTO_INTAKE=1`, `HORNELORE_MEDIA_ARCHIVE_ENABLED=1`) so plain `bash scripts/start_all.sh` brings up the full stack with no wrapper scripts needed.

**Shipped this week:**

- WO-UI-SHELL-01 — Three-tab shell (Operator | Narrator Session | Media); Operator default; session-style picker (5 styles, persistent)
- WO-NARRATOR-ROOM-01 — Narrator room layout: topbar + view tabs (Memory River | Life Map | Photos | Peek at Memoir) + chat conversation column + context panel; Take-a-break overlay; chat scroll stabilization; hands-free state scaffolding
- WO-ARCHIVE-AUDIO-01 — Memory archive backend: 7 endpoints under `/api/memory-archive/*` with `archive session_id == conv_id`; per-narrator zip export; smoke-tested 34/34 PASS
- WO-UI-TEST-LAB-01 — Operator UI Health Check inside Bug Panel; 14 categories; PASS / WARN / FAIL / DISABLED / NOT_INSTALLED / SKIP / INFO; <100ms full run
- WO-SESSION-STYLE-WIRING-01 — Operator session-style picker drives narrator behavior; questionnaire_first BYPASSES the v9 incomplete-narrator gate (Corky rule)
- WO-HORNELORE-SESSION-LOOP-01 — Post-identity orchestrator that asks one Bio Builder question at a time and routes per `sessionStyle`
- WO-HORNELORE-SESSION-LOOP-01B — Loop saves answers via `PUT /api/bio-builder/questionnaire`
- WO-HORNELORE-SESSION-LOOP-01C — Repeatable-section deferred-handoff is a real next-branch offer, not a dead-end
- WO-UI-HEALTH-CHECK-02 — Harness extended for new loop behavior + welcome-back suppression + camera-return verification
- WO-ARCHIVE-INTEGRATION-01 — Two-sided text transcript writer; every chat turn (narrator + Lori) lands in `transcript.jsonl` and `transcript.txt` under the archive
- Multiple bug fixes: #145/#175/#190/#193 (camera class), #194 (sessionStyle persistence), #202 (Lori intro brand naming), #205 (Bug Panel in header), #206 (camera one-shot dropped), #207 (welcome-back collision)

**Landed 2026-04-26 (Document Archive lane):**

- **WO-MEDIA-ARCHIVE-01** — separate curator lane parallel to `/api/photos`. Stores PDFs / scanned documents / handwritten notes / genealogy outlines / letters / certificates / clippings — anything that's source material rather than a memory-prompt photo. **Locked product rule: Preserve first. Tag second. Transcribe / OCR third. Extract candidates only after that. NEVER auto-promote to truth.**
  - Backend: 4 SQLite tables (`media_archive_items`, `_people`, `_family_lines`, `_links`) with locked enums (DOCUMENT_TYPES, TEXT_STATUSES, DATE_PRECISIONS, LINK_TYPES). Migration `0003_media_archive.sql` auto-applies on first boot via `migrations_runner.py`.
  - Router: `/api/media-archive/*` (POST upload + multipart PDF/image/text MIMEs, GET list with filters, GET detail, PATCH with replace-all on people/family_lines/links arrays, DELETE soft-delete with `?actor_id`, GET file/thumb file-serving, /health).
  - Services: `repository.py` (full CRUD), `storage.py` (per-narrator-or-family-or-unattached layout + meta.json mirror), `thumbnail.py` (Pillow + pdf2image best-effort), `text_probe.py` (pypdf-based page count + image-only detection).
  - Frontend: `ui/media-archive.html` curator page (upload form + saved-list + View/Edit modal), `ui/js/media-archive.js`, `ui/css/media-archive.css`, all behind a 📄 Document Archive launcher card in the Operator → Media tab.
  - 4 new health-harness checks under `media_archive` category (route reachable, list endpoint, page reachable, launcher card present).
  - Default OFF in repo (`HORNELORE_MEDIA_ARCHIVE_ENABLED`); ON in local `.env` for active development. Dev wrapper at `scripts/start_all_media_archive_dev.sh` for ad-hoc opt-in runs.
  - Spec: `WO-MEDIA-ARCHIVE-01_Spec.md`. Smoke fixture: 18-page Charlotte Graichen Shong family genealogy PDF.

**Landed 2026-04-25 → 2026-04-26 (Photo system Phase 2 + URL resolution):**

- **Photo system Phase 2 (partial) — EXIF auto-fill on upload** (server). New `server/code/services/photo_intake/exif.py` (Pillow-backed, fail-soft DMS-decimal converter + JSON-safe raw EXIF dump). Wired into `routers/photos.py` upload handler behind `HORNELORE_PHOTO_INTAKE=1`. Curator-supplied date/location ALWAYS wins; EXIF only fills blanks. Raw EXIF tag map stamped into `metadata_json["exif"]` regardless. Log line `[photos][exif] auto-filled date,gps for photo_id=...`. Default-off; flag-flippable from `.env`.
- **Review File Info preview flow** (matches Chris's visualschedulebot photo admin UX). New `POST /api/photos/preview` endpoint reads EXIF + reverse-geocodes (Nominatim, no API key) + computes Plus Code locally + builds auto-description ("This image is from Tuesday, April 21, 2026 at 2:10 PM at RWRJ+2V Watrous, NM, USA") — all WITHOUT writing to DB. Frontend "Review File Info" button on the single-photo form prefills description/date/location for curator review before commit. Source-attribution pills next to each label show "from EXIF" / "from phone GPS". Three new services: `description_template.py`, `plus_code.py` (pure-Python Open Location Code encoder), `geocode_real.py` (stdlib urllib + Nominatim, fail-soft). Google Maps swap deferred to flag-gated alternative.
- **Multi-file batch upload** (UI). New "Quick Batch Upload" card on `photo-intake.html` above the existing single-photo form. Drag-and-drop or multi-pick, sequential upload (not parallel — protects backend), per-file thumbnail + status pill (queued / uploading / saved / duplicate / error), shared narrator + ready-flag across the batch.
- **View / Edit modal (BUG-239)** — click any saved-photo thumbnail or "View / Edit" button. Shows the full image, source-attribution pills (date/location came from EXIF vs typed by curator vs MISSING), inline editing for description / date / location / ready flag (POSTs to existing PATCH endpoint), GPS coords + map link when EXIF GPS present, raw EXIF in collapsible details, completeness pills. Critical for old scanned prints arriving with no EXIF — operator can fill metadata after the fact.
- **BUG-238** — narrator photo view now filters by `narrator_ready=true`. Without this, scanned-but-unvetted photos and in-progress curator entries leaked into the narrator room.
- **BUG-PHOTO-CORS-01** — `main.py` CORSMiddleware was `allow_origins=["*"]` PLUS `allow_credentials=True`, which the CORS spec forbids (browsers refuse the wildcard). Plus two photo fetches in `app.js` used relative paths instead of the `ORIGIN` constant from `api.js`. Both fixed.
- **BUG-PHOTO-LIST-500** — `repository.py` had `from ..api.db` (two dots) which resolved to `code.services.api` (doesn't exist). Should be three dots `from ...api.db`. Latent since Phase 1; only POST upload exercised the import path. Fixed.
- **BUG-PHOTO-PRECISION-DAY** — `exif.py` returned `"day"` for date precision but the DB CHECK constraint allows only `('exact','month','year','decade','unknown')`. Vocabulary mismatch crashed every EXIF auto-fill upload after the file + thumbnail were already on disk. Fixed to `"exact"` (EXIF carries down to the second). Same fix in form dropdowns (single-photo + modal).
- **BUG-PHOTO-URL-RELATIVE-RESOLVES-TO-UI-PORT** — backend synthesizes image URLs as relative `/api/photos/{id}/thumb` and `/image`. Browser resolves against page origin (port 8082, UI server) instead of API origin (port 8000), 404'ing every thumbnail and full-image lookup. Fixed via new `_resolveApiUrl` helper in `photo-intake.js` and an inline ORIGIN-prepend in `app.js` at four spots: Saved Photos thumbnail, modal full image, narrator-room photo thumbnail, narrator-room lightbox. Same fix carried into `ui/js/media-archive.js` for the Document Archive surface.
- **`docs/PILLOW-VENV-INSTALL.md`** — fresh-laptop trap doc. Pillow must be installed in the GPU venv (`.venv-gpu/bin/pip install Pillow`), otherwise `thumbnail.py` and `exif.py` silently fail-soft and you get broken-image thumbnails + empty EXIF metadata with no log signal. ~90 minutes lost diagnosing this on 2026-04-25. As of 2026-04-26, `Pillow==12.2.0`, `pypdf==6.4.1`, and `pdf2image==1.17.0` are pinned in `requirements-gpu.txt` so a fresh `pip install -r` covers everything.
- **`docs/LAPTOP-SETUP-2026-04-26.md`** — full laptop bring-up doc. Section 11 covers WO-MEDIA-ARCHIVE-01 dependencies + first-boot verification + UI smoke. Updated post-archive to flip the `HORNELORE_MEDIA_ARCHIVE_ENABLED` flag from commented-future to active. Captures the `.env`-doesn't-ride-git rule with a heredoc append for laptop bring-up.
- **Photo system test plan** — `docs/PHOTO-SYSTEM-TEST-PLAN.md` (8 manual smoke cases + automated EXIF parser test). Run automated: `.venv-gpu/bin/python3 scripts/test_photo_exif.py` (3/3 PASS confirmed; 4/4 with real-photo arg).
- **BB Walk Test passing 38/0** — BUG-227/230/234/236/237 stack. Identity pipeline + scope hard-gate + askName parser fix all proven.

**Specced + ready to build (not yet shipped):**

- WO-AUDIO-NARRATOR-ONLY-01 frontend — MediaRecorder per-turn audio capture, TTS gate, upload to `/api/memory-archive/audio`. Backend already shipped (per-turn audio webm endpoint live). Spec at `WO-AUDIO-NARRATOR-ONLY-01_Spec.md`. Live build with operator in browser; 2.5–3 hours.
- WO-STT-HANDSFREE-01A — Auto-rearm browser STT after Lori finishes, with WO-10C long-pause ladder. Spec at `WO-STT-HANDSFREE-01A_Spec.md`. Polish.
- WO-MEDIA-WATCHFOLDER-01 — auto-import from `C:\Users\chris\Hornelore Scans\` straight into Document Archive intake queue (post-MEDIA-ARCHIVE).
- WO-MEDIA-OCR-01 — Tesseract-based OCR for scanned documents in the Document Archive (text_status auto-promotes from `image_only_needs_ocr` → `ocr_complete`).
- WO-MEDIA-ARCHIVE-CANDIDATES-01 — harvest items flagged `candidate_ready=true` and surface to Bio Builder review queue (no auto-promotion; locked product rule).

**Landed overnight 2026-04-25 (test-narrator validation pending tomorrow):**

- **BUG-208 / #219** — bio-builder-core.js cross-narrator contamination. **Code landed**: narrator-switch generation counter + 3-guard backend response check + persist guard + pre/post-fetch pid scope assertions in session-loop + 4 new BUG-208 harness checks under `session` category. **Awaiting live verify with test narrators tomorrow morning.** Report: `docs/reports/BUG-208_REPORT.md`.
- **WO-ARCHIVE-EXPORT-UX-01** — one-click "Export Current Session" button in Bug Panel; `lvExportCurrentSessionArchive` helper with status feedback.
- **WO-TRANSCRIPT-TAGGING-01** — every archive turn now stamped with `meta.session_style`, `meta.identity_phase`, `meta.bb_field`, `meta.timestamp`, `meta.session_id`, `meta.writer_role`.
- **WO-ARCHIVE-SESSION-BOUNDARY-01** — per page-load `session_id` (`s_<base36ts>_<rand>`) stamped on `session/start` body and every transcript line; exposed via `lvArchiveWriter.sessionId()`.
- **WO-UI-HEALTH-CHECK-03** — harness extended with archive-writer module load + transcript-writes-flowing + session_id stamped + onAssistantReply chained + Export helper wired checks under `archive` category.
- **WO-BB-RESET-UTILITY-01** — dev-only "Reset BB for Current Narrator" button in Bug Panel; clears questionnaire/candidates/drafts/QC for active narrator only with inline confirm.
- **WO-SOFT-TRANSCRIPT-REVIEW-CUE-01** — non-blocking bottom-right "Want to review what we've captured so far?" pill after 4 narrator turns, single-fire per session.
- **WO-AUDIO-READY-CHECK-01** — `lvAudioPreflight()` + Bug Panel "Run Audio Preflight" button + 5 new harness checks under `mic` category (MediaRecorder API, secure context, getUserMedia, mic permission state, overall ready).

**Specced + ready to build (not yet shipped):**

- WO-AUDIO-NARRATOR-ONLY-01 — MediaRecorder per-turn audio capture, TTS gate, upload to `/api/memory-archive/audio`. Spec at `WO-AUDIO-NARRATOR-ONLY-01_Spec.md`. **Live build with operator in browser tomorrow morning; 2.5–3 hours.** Gate 3 of the readiness checklist depends on this.
- WO-STT-HANDSFREE-01A — Auto-rearm browser STT after Lori finishes, with WO-10C long-pause ladder. Spec at `WO-STT-HANDSFREE-01A_Spec.md`. Polish; ship after first parent session.

**Master extractor lane:** unchanged this week. Locked baseline `r5h` at 70/104. Active sequence still BINDING-01 → SPANTAG → LORI-CONFIRM. Per-week parent sessions (once they begin in ~3 days) become the new ground-truth dataset for climbing past 70/104 — the synthetic 104-case bench is the regression net, not the goal.

---

## Narrators

| Name | Template | Born | Preferred |
|---|---|---|---|
| Kent James Horne | `kent-james-horne.json` | 1939-12-24, Stanley, ND | Kent |
| Janice Josephine Horne | `janice-josephine-horne.json` | 1939-08-30, Spokane, WA | Janice |
| Christopher Todd Horne | `christopher-todd-horne.json` | 1962-12-24, Williston, ND | Chris |

**Trainer narrators** (read-only reference data, not real subjects):

| Name | Template | Style |
|---|---|---|
| William Alan Shatner | `william-shatner.json` | structured |
| Dolly Rebecca Parton | `dolly-parton.json` | storyteller |

Each narrator is pre-seeded on first startup from their JSON template. Templates contain full biographical data: parents, grandparents, siblings, children, spouse, education, occupation, pets, and core memories. The interview expands this baseline — it never has to establish it from scratch. Trainer narrators are loaded via `scripts/preload_trainer.py` and cannot have data written to the family-truth pipeline.

---

## Architecture

### Three-Service Stack

```
Port 8000  —  LLM API (FastAPI + Llama 3.1 8B Instruct, 4-bit quantized)
Port 8001  —  TTS Server (Coqui VITS)
Port 8082  —  Hornelore UI (hornelore-serve.py, static files)
```

### Four-Layer Truth Pipeline (WO-13)

All narrative memory flows through a four-layer architecture:

```
Shadow Archive  →  Proposal Layer  →  Human Review  →  Promoted Truth
   (notes)          (rows)           (approve/reject)   (canonical)
```

**Layer 1 — Shadow Archive** (`family_truth_notes`): Append-only raw text. Every chat turn, questionnaire save, or manual import creates a note here. Notes are never promoted directly.

**Layer 2 — Proposal Layer** (`family_truth_rows`): Structured claims derived from notes. Each row has a `field` (e.g. `personal.fullName`), `source_says` (raw claim), `status`, `confidence`, and `extraction_method`. Created automatically by the regex extractor (`_extractFacts` in `app.js`) or the LLM extractor (`/api/extract-fields`).

**Layer 3 — Human Review**: Rows start as `needs_verify` and must be explicitly moved to one of five statuses: `approve`, `approve_q` (approved with follow-up question), `needs_verify`, `source_only` (recorded but never promoted), `reject`. The review UI is in `wo13-review.js`.

**Layer 4 — Promoted Truth** (`family_truth_promoted`): The canonical record. Only rows with status `approve` or `approve_q` can be promoted. Protected identity fields (fullName, preferredName, DOB, POB, birthOrder) are blocked from promotion if their extraction_method is `rules_fallback` (regex-based).

### Feature Flags

| Flag | Env Var | Effect |
|---|---|---|
| Facts write freeze | `HORNELORE_TRUTH_V2=1` | Legacy `/api/facts/add` returns 410 Gone |
| V2 profile read seam | `HORNELORE_TRUTH_V2_PROFILE=1` | `GET /api/profiles/{id}` reads from `family_truth_promoted` |
| Photo router master | `HORNELORE_PHOTO_ENABLED=1` | `/api/photos/*` serves live; when off every endpoint 404s except `/health` |
| Photo upload Phase 2 | `HORNELORE_PHOTO_INTAKE=1` | EXIF auto-fill + reverse geocoder run inside the upload handler. Independent of `HORNELORE_PHOTO_ENABLED`; uploads still work without it but the curator has to type date/location manually (Review File Info button still works regardless — it lives on a separate `/api/photos/preview` code path). |
| Document Archive router | `HORNELORE_MEDIA_ARCHIVE_ENABLED=1` | `/api/media-archive/*` serves live; when off every endpoint 404s except `/health`. Curator page at `/ui/media-archive.html`. |

All five flags are currently **ON** in `.env` for active development. The truth-v2 profile read seam uses a hybrid strategy: promoted-truth values override `basics.*` for the 5 protected identity fields; all other promoted rows appear in a `basics.truth[]` sidecar array; unmapped fields (kinship, pets, culture, pronouns, etc.) pass through from legacy `profile_json`. The photo and media-archive flags default OFF in the repo so the production stack stays opt-in; flipping them in `.env` is the pattern documented in `docs/LAPTOP-SETUP-2026-04-26.md`.

### Data Flow: Chat → Truth

1. User sends a message in chat
2. `_extractAndPostFacts()` runs regex patterns against the user's text
3. For each match: `POST /api/family-truth/note` (shadow note) → `POST /api/family-truth/note/{id}/propose` (proposal rows)
4. Protected identity fields get downgraded to `source_only` status from chat extraction
5. Operator reviews rows in the Review Drawer, PATCHes status to approve/reject
6. `POST /api/family-truth/promote` bulk-promotes approved rows into canonical truth
7. Next `GET /api/profiles/{id}` returns promoted values

### Resume Prompt Gate (WO-13)

Every narrator switch checks `user_turn_count` from `/api/narrator/state-snapshot`. If a narrator has zero prior user-authored turns, both resume-prompt paths (legacy `lv80SwitchPerson` and WO-8 `wo8OnNarratorReady`) are suppressed. This prevents fake "welcome back" greetings from polluting the turns table.

### Quality Harness (WO-QA-01, WO-QA-02, WO-QA-02B)

A permanent measurement system for evaluating Hornelore's behavior under different sampling configurations. Measures three orthogonal axes and writes everything to JSON artifacts so any future runtime change (TRT-LLM swap, model update, prompt change) can be evaluated against the same yardstick.

**Two synthetic test narrators** (`narrator_type='test'`, permanently quarantined from family-truth via existing reference-narrator write guards):

| ID | Display name | Style |
|---|---|---|
| `test-structured-001` | Mara Vale (Helena MT, 1941) | structured |
| `test-storyteller-001` | Elena March (Taos NM, 1943) | storyteller |

Templates live in `data/narrator_templates/test_*.json`; seeded into the `people` + `profiles` tables by `scripts/seed_test_narrators.py`.

**Two-channel measurement** (WO-QA-02):

- **Channel A — Narrator content (ceiling).** Static narrator statements from `data/test_lab/narrator_statements.json` are fed directly into `/api/extract-fields` once per narrator, producing the maximum extractable yield from that fixture set. Config-independent.
- **Channel B — Lori responses (suppression).** The matrix runs each (narrator × config) combination through scenarios via `/api/chat/ws`, then computes `suppression = ceiling - lori_yield_total`. Lower suppression = config preserves more narrator truth in Lori's interview behavior.

**Ranking** (per (narrator × config) cell):

1. Contamination PASS (gate)
2. Suppression ASC (lower wins)
3. TTFT ASC (faster wins)
4. Human score DESC (tie-break)

**Hardware monitoring** runs concurrently with every matrix run — GPU util/VRAM/temp/power via `nvidia-smi`, CPU util via `/proc/stat`, RAM via `/proc/meminfo`. Sampled every 5s, written to `hardware_timeseries.json` + `hardware_summary.json` so post-hoc analysis can correlate behavioral anomalies with hardware state.

**Timing instrumentation** captures wall-clock duration plus per-cell durations. `progress.json` is updated after every cell so the UI surfaces live elapsed + ETA while the run is in flight; `run_meta.json` carries the finished totals.

**Operator UI** (`testLabPopover` in `hornelore1.0.html`) exposes:
- Live console pane (GPU/CPU/RAM + runner log tail, refreshes every 2s)
- Channel A — Narrator ceilings table
- Scores table ranked by suppression
- Compare table (yield/TTFT/contamination Δ vs a baseline)
- Hardware summary + Timing panes for the loaded run

The popover is operator-only (dev-mode gated via `toggleDevMode()` in the console). Run via the **Run Harness** button or directly from WSL: `bash scripts/run_test_lab.sh`. Budget 45–90 minutes for a full matrix.

Detailed work-order specs live in `docs/wo-qa/`.

---

### Chronology Accordion (WO-CR-01, WO-CR-PACK-01)

A read-only left-side timeline sidebar that merges three lanes at request time — never in the database. Shown as an 80px collapsed column / 280px expanded column to the left of the chat area, hidden during trainer mode.

**Three-lane data model** (derived per narrator on every fetch):

| Lane | Source | Authority |
|---|---|---|
| A — World | `server/data/historical/historical_events_1900_2026.json` | Context only (never personal fact) |
| B — Personal | profile basics → questionnaire fallback → promoted truth | Trusted anchors |
| C — Ghost | Static life-stage prompts (one per band, at midpoint year) | Question shaping only |

**Authority contract.** The `GET /api/chronology-accordion` endpoint is strictly read-only. It never writes to `facts`, `timeline`, `questionnaire`, `archive`, or any truth table. UI state writes are limited to `state.chronologyAccordion` (visibility + focus — never truth).

**Personal-anchor source priority** (Lane B):
1. **Profile basics** — `dob` + `pob` produce an enriched `Born — {pob}` anchor at year-of-birth
2. **Questionnaire fallback** — strictly limited to `personal.dateOfBirth` / `personal.placeOfBirth` / `personal.dateOfDeath`. No other questionnaire keys are promoted to Lane B.
3. **Promoted truth** — primary source for expansion anchors (marriage, child, move, work_begin, retirement, graduation, military, immigration, divorce, death). 14 date-bearing fields whitelisted; nothing else becomes an anchor.

**Compound dedup keys** prevent collisions when expansion anchors land:
- Single-occurrence: `birth:self`, `death:self`, `retirement:self`, `work_begin:self`
- Multi-occurrence: `marriage:{spouse}:{year}`, `child:{name}:{year}`, `move:{place}:{year}`, etc.

**Visual hierarchy** (CR-03): Personal anchors dominate (12.5px bold, tinted green bg, 4px left bar; `source=promoted_truth` renders with a brighter 5px bar as a shield-weight authority signal). World events are quieter (10.5px, muted, 0.85 opacity). Ghost prompts are clearly non-factual (dashed amber border, italic, `?` prefix, 0.78 opacity). Active-era year rows get an inset indigo bar.

**Lori timeline awareness** (CR-04). When a year or item is clicked, the runtime payload gains a `chronology_context` block (parallel to `memoir_context` / `projection_family`) with a narrow focus slice — capped at 3 personal / 3 world / 2 ghost items. Every item carries a `source` tag so `prompt_composer` can enforce provenance rules:

| Source tag | Lori treatment |
|---|---|
| `promoted_truth` | May assert as confirmed anchor |
| `profile` / `questionnaire` | Soft cue only — may probe, must not assert |
| `historical_json` | Context only — never rephrased as personal biography |
| `life_stage_template` | Question shaping only — never stated as known history |

The ladder appears automatically for any narrator with a DOB; the backend returns `{"error": "no_dob"}` for narrators missing identity basics and the UI hides the column cleanly.

---

## Hardening

**No new narrators.** The +New button is hidden and disabled. `lv80NewPerson()` is a stub that logs a warning. There is no UI path to create a fourth narrator.

**No deletion.** Delete buttons are removed from narrator cards. `lvxStageDeleteNarrator()` is overridden to block deletion and display a warning. All three narrators are protected.

**Identity bypass on switch.** When switching to a known narrator, the identity phase is automatically set to `complete`. The system never re-asks name, DOB, or birthplace for a narrator whose identity is already established.

**Fresh session isolation.** Every narrator switch generates a unique `conv_id`. The LLM backend cannot carry turn history from one narrator into another's session.

**Reference narrator write guard.** Trainer narrators (Shatner, Dolly) are blocked from all family-truth write operations: shadow notes, proposals, row patches, and promotions return 403.

**Auto-seeding on startup.** `_horneloreEnsureNarrators()` checks the people cache on load. Any missing narrator is seeded from their template. If all three exist, the function is a no-op.

---

## Data Isolation

| Resource | Lorevox | Hornelore |
|---|---|---|
| Database | `lorevox.sqlite3` | `hornelore.sqlite3` |
| Data directory | `/mnt/c/lorevox_data/` | `/mnt/c/hornelore_data/` |
| Uploads | `lorevox_data/uploads/` | `hornelore_data/uploads/` |
| Media | `lorevox_data/media/` | `hornelore_data/media/` |
| UI port | 8080 | 8082 |
| Model cache | `/mnt/c/models/hornelore/` | `/mnt/c/models/hornelore/` |
| TTS cache | `hornelore_data/tts_cache/` | `hornelore_data/tts_cache/` |

---

## Architecture status (as of 2026-05-01 evening)

**Active baseline:** extractor lane locked at `r5h` (70/104, v3=41/62, v2=35/62, mnw=2) — unchanged this week. Lori-behavior runtime control layer LIVE. Parent sessions blocked by 3 remaining safety/truth gates (#5, #6, #7 above).

The repo runs three parallel lanes with separate posture and acceptance criteria. Understand which lane any code change sits in before reading the changelog.

### Lane 1 — Extractor (regression-gated)

Synthetic eval bench: 104 cases, locked at 70/104. Climbs only when extractor architecture earns it via gated patches.

- **Active baseline:** `r5h-postpatch` confirmed = `r5h` (byte-stable)
- **Top of queue:** `WO-EX-BINDING-01` — binding-layer fix delivered inside SPANTAG Pass 2 prompt (PATCH 1–5)
- **SPANTAG state:** OFF (`HORNELORE_SPANTAG=0`). Default-on REJECTED at v3 attempt due to binding-layer field-path hallucination (-39 cases). Stays off until BINDING-01 lands binding-hallucination containment.
- Detail: `MASTER_WORK_ORDER_CHECKLIST.md` Lane 1, `CLAUDE.md` changelog, `docs/specs/LOREVOX-EXTRACTOR-ARCHITECTURE-v1.md`

### Lane 2 — Lori behavior (parent-session-gated) — runtime control layer LIVE

This week's headline work: a three-layer architecture (Cognitive rules → Behavioral control → Interview intelligence) with the first two layers shipped and verified live.

**Layer 1 — Cognitive rules (Grice maxims):** `LORI_INTERVIEW_DISCIPLINE` block in `prompt_composer.py`. Defines what cooperative interview communication is. Always-on guidance.

**Layer 2 — Behavioral control (STA-grounded runtime guard):** `services/lori_communication_control.py`. Composes atomicity + reflection + per-session-style word limits + question-count cap + acute-safety exemption into a single `chat_ws` call site. Gated `HORNELORE_COMMUNICATION_CONTROL=1` after one clean run.

**Layer 3 — Interview intelligence:** separate lane, separate WOs (SESSION-AWARENESS-01 Phase 3+4 and future spoken-dialogue / persona lanes).

**Landed (#289 / #285 / + new this week):**

- **`WO-LORI-SAFETY-INTEGRATION-01` Phase 0+1** — `safety.py` pattern detector wired into chat WS path. Phase 3 operator notification surface live. Phase 9 onboarding consent disclosure + operator runbook landed. Acute-safety path verified (Turn 06: 988 response, no normal Q, no failures).
- **`WO-LORI-SESSION-AWARENESS-01` Phase 2** — `LORI_INTERVIEW_DISCIPLINE` composer block with intent-aware tiers; foundation that ATOMICITY-01 + REFLECTION-01 + COMMUNICATION-CONTROL-01 all extend.
- **`WO-LORI-QUESTION-ATOMICITY-01`** — 6-category atomicity filter (truncate-only, deterministic, LAW-3 isolated). Layer 1 directive + Layer 2 module.
- **`WO-LORI-REFLECTION-01`** — memory-echo validator (validator-only by §6 architecture). Layer 1 directive + Layer 2 module.
- **`WO-LORI-COMMUNICATION-CONTROL-01`** — the unifying runtime guard. Single chat_ws call site. Per-session-style word limits.
- **`WO-LORI-STORY-CAPTURE-01` Phase 1A + 1B** — story preservation pipeline. `story_candidates` table + classifier + writer + operator review surface. Lowercase fallback verified live.
- **`BUG-DBLOCK-01` (#344)** — fixed and verified live. Two-bug chain (FK violation on chat-path safety segment_flag insert + leaked connection from missing try/finally) closed via three patches in `db.py` + `chat_ws.py`. `db_lock_events` delta = 0 across two consecutive golfball runs.

**Pending — three RED gates remaining (parent-session blockers):**

- **`WO-LORI-SAFETY-INTEGRATION-01` Phase 2 (#290)** — LLM second-layer classifier for soft-trigger detection. Catches indirect ideation patterns Layer 1 regex misses (e.g. "I do not want to be alive anymore" — Turn 05 evidence). Highest parent-session leverage.
- **TRUTH-PIPELINE-01 Phase 1** — observability stub. Diagnoses whether `speaker_zero_delta` on operator-harness turns is a real truth-write bug or a harness coverage gap (chat_ws path doesn't auto-extract; `interview.js` does). Phase 2/3 routing fixes deferred until Phase 1 evidence lands.
- **Post-safety recovery / softened-mode persistence** — Turn 07 evidence: after Turn 06 acute fired, Lori drifted back to normal interview mode. `set_softened()` already exists in `db.py`; chat_ws needs to read it at turn-start and inject a `LORI_SOFTENED_RESPONSE` system-prompt block.

**Parked at YELLOW (not parent-session blocker):**

- **REFLECTION-01 v2 — Quality-maxim sharpening.** Validator catches real failures (Turn 01/02/04 echo issues) but Layer 1 prompt directive isn't strong enough to prevent them. Reflection is validator-only by design (deterministic rewrite of content would invent narrator facts — exact LAW-3 failure mode). Park; revisit if validator failure-rate stays >30% across two clean runs.

### Lane 3 — MediaPipe / session awareness (post-parent-session polish)

Not parent-session blockers. Spec parked, design stable. The four spoken-dialogue / role research papers (Easy Turn / HumDial Track II / PersonaPlex / Proficiency-Conditioned Dialogue) all point at lanes that open when Hornelore moves from cascaded ASR→LLM→TTS to full-duplex spoken dialogue.

- **`WO-LORI-SESSION-AWARENESS-01`** Phase 3 — MediaPipe attention cue. Passive-waiting detector requires all 4 inputs (gaze_forward + low_movement + no_speech_intent + post_tts_silence). Tiered cue types. Veto rule: `engaged`/`reflective` blocks cue under WO-10C 120s mark. (Easy Turn paper grounds this lane.)
- **`WO-LORI-SESSION-AWARENESS-01`** Phase 4 — Adaptive Narrator Silence Ladder. Per-narrator × prompt_weight rolling window with 25s hard floor. Pacing FIT not measurement; no surface, no trend, no clinical scoring. (Proficiency-Conditioned Dialogue paper grounds this lane.)
- **`WO-AFFECT-ANCHOR-01`** (PARKED) — multimodal affect anchoring via shared-clock fusion (Whisper word-timestamps + MediaPipe + light acoustic features + optional Tier 2 video). Blocked by BINDING-01 + parent-session readiness.
- **Future role-conditioning lane** (PersonaPlex grounding) — not yet specced. Opens when Lori needs operator/narrator/companion persona adaptation as a measurable problem.
- **Future spoken-dialogue evaluation** (Proficiency-Conditioned Dialogue grounding) — reaction time / response frequency / fluency / pause behavior columns in the harness JSON. Parked until the spoken-dialogue architecture lands.

### Startup expectations

**Cold boot is ~4 minutes. This is normal, not a bug.** HTTP listener up at ~60–70 seconds; LLM weights + extractor warmup continue another 2–3 minutes. A `curl /` health check is NOT sufficient — it only proves the socket is listening. Don't run an eval against a "warm" stack until the discipline-header warmup probe shows roundtrip <30s. Eval harness has a 300s timeout per case to absorb cold-start latency on the first case.

---

## Local-first AI commitment

Every model used inside Hornelore (and by extension, Lorevox) runs on the narrator's machine. This is a standing architectural commitment, not a default we plan to revisit later under cost pressure.

**What this means concretely:**

- **STT runs locally** — Whisper variants, on-device. The transcript of an older adult talking about her mother never leaves the family's hardware.
- **LLM extraction runs locally** — Llama 3.1 8B Instruct (4-bit) today on the GPU specified in `.env`; future swaps (Hermes 3, Qwen, etc.) stay local.
- **Facial signal runs locally** — MediaPipe FaceMesh in the browser. The system never ships video, raw landmarks, or raw emotion vectors anywhere; only derived `affect_state` + confidence + duration leave the camera-preview boundary.
- **Acoustic features run locally** — pitch, pause, speaking-rate analysis is planned via librosa / webrtcvad in-process (see `WO-AFFECT-ANCHOR-01_Spec.md`). No audio is sent to a hosted analysis service.
- **TTS runs locally** — Coqui VITS on port 8001.
- **No external API calls for any modality** — including facial recognition, speech-to-text, and emotion inference. Reverse-geocoding for photo EXIF uses Nominatim (a public OSM endpoint, not an authenticated cloud API), and that single network exit is the only one in the system; everything narrator-touching stays on the device.

The reason is the user. Hornelore is built for older-adult narrators in life-review settings — including narrators with possible cognitive decline. The product crosses into territory (medical, legal, emotional, family) where families need to be able to say truthfully that the recording, the face, the voice, the inferred emotion, and the extracted truth all stayed on their machine. Hosted-API economics can't be allowed to erode that contract over time.

### Future model exploration (the modular promise)

The architecture is deliberately modular so that as **better local models** appear and as **consumer hardware advances** (more VRAM, faster CPUs, on-device NPUs), we can swap upstream signal extractors without rewiring downstream consumers.

| Layer | Today (local) | Future (still local) |
|---|---|---|
| STT | Whisper large-v3 | Whisper successors, distilled / quantized faster variants |
| Extraction LLM | Llama 3.1 8B Instruct (4-bit) | Hermes 3, Qwen, larger open-weights as VRAM allows |
| Facial affect | MediaPipe FaceMesh + rule-based labels | Learned visual emotion models when open-weight options mature |
| Acoustic | librosa / webrtcvad (planned) | More specialized open-source prosody models |
| Joint speech-text | Not used | Open-weight latent speech-text models when they exist (see `docs/research/papers/22526_Latent_Speech_Text_Trans.pdf`) |
| TTS | Coqui VITS | Newer open-source voice synthesis, voice-cloning for narrator playback |

The fusion layer's contract is what stays stable. Only the upstream extractors get swapped. `WO-AFFECT-ANCHOR-01_Spec.md` is the canonical reference for how this is structured.

### Contribution invitation

This is the kind of work that benefits from people who care about it.

If you've built a better local STT, a better open-weight emotion model, a better acoustic-feature extractor, a better quantized LLM for the extraction task, or work in the broader open-weight / local-AI space and want to plug it into a real older-adult life-review system, that conversation is welcome.

The standing rule for any contribution touching the model layer: **it must run locally on the narrator's machine.** No hosted APIs, no "we just call this one cloud endpoint" exceptions, no telemetry phoning home. If a swap can't satisfy that, it doesn't go in.

Code contributions go through the license terms below (assignment-based, by invitation). Research contributions, model recommendations, benchmark contributions against the 104-case eval bench, and parent-session methodology feedback don't require code commits — open a thread at dev@lorevox.com.

---

## Listening before hearing

Lorevox is not a transcription product. It is a memory-preservation system for older narrators.

Modern ASR can hear words with high accuracy, but **better hearing without better listening just makes the system wrong faster.** A perfect transcript can still become a trust failure if the binding layer writes a complaint, a resistance phrase, or a story fragment into a protected identity field. The Janice regression — where the narrator said *"I just told you something you ignored"* and the system bound that complaint to `personal.birthOrder` — is the canonical failure mode. Better ASR would have transcribed the same nine words with the same precision and routed them to the same wrong field.

The locked principle:

> **Better hearing without better listening just makes you wrong faster.**

For this reason, model upgrades do not bypass the Lorevox truth pipeline:

```
Audio / transcript  →  Archive  →  structured candidate  →  Review Queue  →  promoted History  →  Memoir
```

Better ASR may improve the Archive. It does not change what reaches History or Memoir. Protected identity, family facts, dates, places, and biographical claims still require the existing review and promotion discipline. The architectural wall is the load-bearing thing; the model is replaceable.

### Current model posture (locked 2026-05-03 after 3-agent triangulation)

- **Keep:** Llama 3.1-8B-Instruct (Q4) for Lori chat and extraction. Production-stable; current extractor prompts are tuned to it; master eval baseline (`r5h-followup-guard-v1` = 78/114) is calibrated against this model.
- **Keep:** Current TTS (Coqui VITS on port 8001). Already sized for the RTX 5080 stack.
- **Sandbox only:** **Canary-Qwen 2.5B** as an Archive-only transcription experiment. Plausible 20% WER improvement over Whisper on noisy audio, but unverified on Janice + Kent voice profiles specifically. WER gains feed the Archive only — they do NOT bypass the Review Queue.
- **Defer:** **PersonaPlex 7B**. Sub-300ms full-duplex turn-taking is optimized for fluent adult conversation. Older narrators (Janice and Kent are 86) need *longer* protected pauses, not shorter ones — this is why WO-10C set silence cadence at 120s / 300s / 600s, not 300ms. Full-duplex is wrong-target for the population this product serves.
- **Post-session only:** **Nemotron 3 Nano 30B-A3B**. The "3B active" parameter count refers to MoE compute per token, NOT total memory residence — the full ~30B expert set still loads into VRAM. Not a live narrator-session model on a 16 GB consumer card. Reasonable as an offline reasoning experiment overnight.

### RTX 5080 working envelope (16 GB VRAM)

Measured behavior on the warm Hornelore stack (verified by `WO-OPS-VRAM-VISIBILITY-01` bench, 2026-05-03 — full report at `docs/reports/WO-OPS-VRAM-VISIBILITY-01_BASELINE.md`):

```
Idle floor:                       ~5.9 GB    (Llama 3.1-8B Q4 + TTS, no active turn)
Normal active turn (SPANTAG-off): ~8.0 GB    (curl 20w-1000w + real eval slice all pin here)
Real eval flow (SPANTAG-off):     ~8.0 GB    (sentence-diagram-survey peak 8.04 GB / min free 6.37 GB)
SPANTAG-on eval slice:            ~7.0 GB    (10-case bench peak 6.97 GB / min free 9.0 GB)
Long-prompt SPANTAG tail:         (working hypothesis) ~13–15 GB
                                  Historical OOM (2026-04-27) on ~6k-token cases
                                  not reproduced in today's bench. Needs targeted
                                  case_044 + case_069 SPANTAG-on bench before
                                  envelope can be declared fully verified.
                                  Parked risk while SPANTAG stays default-OFF.
```

The `VRAM_GUARD` in `chat_ws.py` (WO-10M) blocks turns when free VRAM dips below `base 600 MB + per_token 0.14 MB × planned_seq`. It exists because long prompts + KV cache filling can push past the ceiling on the long tail. Bug Panel widget surfaces guard-block count via `vram_guard_blocks_last_hour` (banked under WO-OPS-VRAM-VISIBILITY-01 Phase 2). Today's bench: zero guard blocks across all 9 scenarios over ~25 minutes.

### The verification stance

Before any model swap proceeds, three things must verify:

1. **Verified VRAM** beats estimated VRAM. Parameter math × bytes-per-param is necessary but not sufficient — real live VRAM also includes CUDA context, framework overhead, KV cache (which scales with context length, not just model size), audio buffers, TTS, and fragmentation.
2. **Verified WER on Janice and Kent** beats benchmark WER. Open ASR Leaderboard numbers are useful but generic. The narrator-specific WER on the canon-grounded corpus (24 cases) is what matters for whether Janice keeps talking.
3. **Verified narrator trust** beats both. The metric that actually predicts whether an older narrator continues the interview is *did the system reflect what they said, ask one short question, and then stop?* That's anchor selection + atomicity + waiting — none of which require a model upgrade.

---

## Quick Start

1. Start all services (Windows Terminal):
   ```
   start_hornelore.bat
   ```
   Or from WSL:
   ```bash
   cd /mnt/c/Users/chris/hornelore && bash scripts/start_all.sh
   ```

2. Open in Chrome:
   ```
   http://localhost:8082/ui/hornelore1.0.html
   ```

On first load, Hornelore seeds Chris, Kent, and Janice from templates and auto-selects the first narrator.

### Preloading Trainer Narrators

```bash
cd /mnt/c/Users/chris/hornelore
python3 -m pip install -r scripts/requirements.txt --break-system-packages
python3 -m playwright install chromium
python3 scripts/preload_trainer.py --all
```

---

## Database Schema (Key Tables)

| Table | Purpose |
|---|---|
| `people` | Narrator records (id, display_name, role, date_of_birth, place_of_birth, narrator_type) |
| `profiles` | Legacy profile blobs (person_id, profile_json with basics/kinship/pets) |
| `turns` | Chat messages (conv_id, role, content, ts) |
| `sessions` | Session metadata (conv_id, payload_json with active_person_id) |
| `family_truth_notes` | Shadow archive — append-only raw text |
| `family_truth_rows` | Proposal layer — structured claims with review status |
| `family_truth_promoted` | Canonical truth — approved rows keyed by (person_id, subject_name, field) |
| `facts` | Legacy facts (frozen under HORNELORE_TRUTH_V2) |

---

## API Endpoints (Key)

**People & Profiles:**
- `GET /api/people` — list all narrators
- `GET /api/profiles/{person_id}` — profile (V2: reads from promoted truth)
- `GET /api/narrator/state-snapshot?person_id=` — full narrator state for UI hydration

**Family Truth Pipeline:**
- `POST /api/family-truth/note` — append shadow note
- `GET /api/family-truth/notes?person_id=` — list shadow notes
- `POST /api/family-truth/note/{id}/propose` — derive proposal rows from a note
- `GET /api/family-truth/rows?person_id=` — list proposal rows (filter by status, field)
- `PATCH /api/family-truth/row/{id}` — review: update status/approved_value/reviewer
- `POST /api/family-truth/promote` — promote approved rows (single row_id or bulk person_id)
- `GET /api/family-truth/promoted?person_id=` — list promoted truth
- `GET /api/family-truth/audit/{row_id}` — provenance chain for a row
- `POST /api/family-truth/backfill` — seed notes+rows from existing profile_json

**Chat:**
- `WS /api/chat/ws` — websocket for live chat
- `POST /api/extract-fields` — LLM-based field extraction from chat turns

**Chronology Accordion:**
- `GET /api/chronology-accordion?person_id=` — read-only three-lane timeline payload (world events + personal anchors + ghost prompts, grouped by decade and year). Never writes; returns `{"error": "no_dob"}` when profile basics lack a DOB.

**Quality Harness (operator-only, WO-QA-01 / WO-QA-02):**
- `POST /api/test-lab/run` — launch the harness in a background subprocess (optional `compare_to`, `run_label`, `dry_run`)
- `GET /api/test-lab/status` — running / finished / failed / idle, with live `progress` overlay (cells, elapsed, ETA) when a run is in flight
- `GET /api/test-lab/results` — list prior run_ids by mtime DESC
- `GET /api/test-lab/results/{run_id}` — scores / metrics / transcripts / compare / configs / hardware_summary / narrator_ceilings / run_meta
- `POST /api/test-lab/reset` — reset status.json to idle
- `GET /api/test-lab/gpu` — one-shot nvidia-smi parse (util %, VRAM, temp, power)
- `GET /api/test-lab/system` — consolidated GPU + CPU + RAM snapshot
- `GET /api/test-lab/log-tail?lines=N` — last N lines of runner.log

---

## File Inventory

| Category | Count | Key Files |
|---|---|---|
| JavaScript (UI) | 43 | app.js, api.js, state.js, wo13-review.js, narrator-preload.js, chronology-accordion.js, shadow-review.js, conflict-console.js, test-narrator-lab.js |
| CSS | 12 | base.css, layout.css, lori80.css, test-narrator-lab.css, … |
| HTML shell | 1 | `hornelore1.0.html` |
| Narrator templates | 8 | 3 family + 2 trainers + 1 base + 2 synthetic test (`data/narrator_templates/test_*.json`) |
| Server routers | 28 | family_truth.py, profiles.py, extract.py, narrator_state.py, chronology_accordion.py, test_lab.py |
| Historical seed | 1 | `server/data/historical/historical_events_1900_2026.json` (152 world events, 1900–2026) |
| Quality harness fixture | 1 | `data/test_lab/narrator_statements.json` (Channel A ceilings) |
| Scripts | 26 | preload_trainer.py, import_kent_james_horne.py, start/stop/restart, run_test_lab.sh, seed_test_narrators.py, test_lab_runner.py, test_lab_doctor.sh, test_lab_watch.sh, run_question_bank_extraction_eval.py |
| Eval cases | 2 | `data/qa/question_bank_extraction_cases.json` (104 master), `data/qa/question_bank_generational_cases.json` (14 generational) |
| Question bank | 1 | `data/prompts/question_bank.json` (36 sub-topics, generational overlays, present_life_realities) |
| Tests | 6+ | test_extract_subject_filters, test_extract_claims_validators, test_life_spine_validator, test_phase_aware_composer, test_interview_opener, test_extract_api_subject_filters |
| Config | 4 | .env, package.json, playwright.config.ts, tsconfig |
| WO docs | n | `docs/WO-*.md` (per-WO reports), `docs/wo-qa/WO-QA-*.md` (Quality Harness specs) |

---

## Work Orders

| WO | Status | Description |
|---|---|---|
| WO-8 | Complete | Transcript history, thread anchors, narrator resume flow |
| WO-9 | Complete | Rolling summaries, recent turns, memory intelligence |
| WO-10 | Complete | Cognitive support, operator tools, memory intelligence |
| WO-11 | Complete | Standalone repo separation from Lorevox, trainer isolation |
| WO-11E-HL | Complete | Amber read-along highlighting for Lori narration, TTS timing polish |
| WO-12B | Complete | Cross-narrator contamination hunt and evidence archive |
| WO-13 | Complete | Four-layer truth pipeline (phases 1–9) |
| WO-13X / 13YZ | Complete | Conflict console + shadow review redesign |
| WO-CAM-FIX | Complete | Camera orchestration repair (auto-start on ready narrator load) |
| WO-MIC-UI-02A | Complete | Single-surface voice capture UI |
| WO-CR-01 | Complete | Left Chronology Accordion — three-lane timeline sidebar |
| WO-CR-PACK-01 | Complete | Chronology Phase 2 — mapper expansion, visual tuning, Lori awareness |
| WO-QA-01 | Complete | Quality Harness — synthetic test narrators, scoring, hardware/timing capture |
| WO-QA-02 | Complete | Archive-truth methodology — Channel A ceilings + suppression ranking. **`cfg_expressive` adopted as production default** (see `docs/wo-qa/WO-QA-02-RESULTS.md`) |
| WO-QA-02B | Complete | Seed determinism — `chat_ws.py` honors `params.seed`. CUDA INT4 kernels remain non-deterministic; documented noise floor ±4 on suppression. |
| WO-EX-01C | Complete | Narrator-identity subject guard + birth-context filter |
| WO-EX-01D | Complete | Field-value sanity blacklists |
| WO-EX-SCHEMA-01 | Complete | `family.*` + `residence.*` fields + repeatable entities |
| WO-EX-SCHEMA-02 | Complete | 35 new fields (7 families), ~50 aliases, 7 prompt examples |
| WO-EX-CLAIMS-01 | Complete | Dynamic token cap, position-aware grouping, 20 aliases |
| WO-EX-CLAIMS-02 | Complete | Quick-win validators + refusal guard + community denial. 114 unit tests. |
| WO-EX-REROUTE-01 | Complete | Semantic rerouter: 4 high-precision paths + touchstone dup + story-priority |
| WO-EX-VALIDATE-01 | Shipped (flag OFF) | Age-math plausibility validator |
| WO-EX-GUARD-REFUSAL-01 | Complete | Topic-refusal guard + community denial patterns |
| WO-EX-TWOPASS-01 | **Regressed (flag OFF)** | Two-pass extraction — regressed 16/62 vs 32/62. Keep OFF. |
| WO-LIFE-SPINE-05 | Shipped (flag OFF) | Phase-aware question composer |
| WO-GREETING-01 | Complete | Backend endpoint + frontend. Memory echo triggers. |
| WO-QB-MASTER-EVAL-01 | Complete | 62→104 cases, v2/v3 scoring, filters, atomic writer |
| WO-QB-GENERATIONAL-01 | Complete (content) | 4 decade packs, present_life_realities, 5 new fields, 14 eval cases |
| WO-QB-GENERATIONAL-01B | Complete (Part 1+3) | 6 extraction prompt examples, 2 rerouter rules, scorer collision fix |
| WO-KAWA-UI-01A | Complete | River View UI |
| WO-KAWA-01 | Specced | Parallel Kawa river layer — 10 phases |
| WO-KAWA-02A | Complete | 3 interview modes, 3 memoir modes, plain-language toggle |
| WO-PHENO-01 | Specced | Phenomenology layer: lived experience + wisdom extraction |
| WO-INTENT-01 | Not specced | Narrator topic pivots ignored by composer — **#1 felt bug** |
| WO-EX-DENSE-01 | Not specced | Dense-truth / large chunk extraction — **#1 extraction frontier** |
| WO-QA-03 | Planned | TTS Option A — `--with-tts` flag for latency + GPU contention |
| WO-14 | Deferred | TensorRT-LLM runtime swap (deferred pending Blackwell SM_120 maturity) |
| WO-LORI-PHOTO-SHARED-01 | Complete | Photo authority layer — POST/GET/PATCH/DELETE `/api/photos/*`, multi-file batch upload, View/Edit modal, narrator-room lightbox, dedupe by file hash, soft-delete |
| WO-LORI-PHOTO-INTAKE-01 (Phase 2 partial) | Shipped (flag-gated) | EXIF auto-fill + Nominatim reverse-geocoder + Plus Code generator + auto-description on upload; Review File Info preview button. `HORNELORE_PHOTO_INTAKE=1`. |
| WO-LORI-PHOTO-ELICIT-01 (Phase 2) | Specced | Photo memory extraction profile, async scheduler, LLM prompts for Lori-side narration over photos in narrator room. Spec ready. |
| WO-MEDIA-ARCHIVE-01 | Complete | Document Archive lane parallel to /api/photos. PDFs / scanned docs / handwritten notes / genealogy / letters / certificates / clippings. 4 SQLite tables, full router + curator page + 4 health checks + dev wrapper. Locked product rule: NEVER auto-promote to truth. |
| WO-ARCHIVE-AUDIO-01 | Complete | Memory archive backend (per-narrator zip export, two-sided text transcript, narrator-only audio rule) at `/api/memory-archive/*` |
| WO-AUDIO-NARRATOR-ONLY-01 (backend) | Complete | Per-turn webm audio capture endpoint; frontend MediaRecorder integration pending live build |
| WO-UI-SHELL-01 | Complete | Three-tab shell (Operator / Narrator Session / Media); session-style picker (5 styles, persistent) |
| WO-NARRATOR-ROOM-01 | Complete | Narrator-room layout: topbar + view tabs (Memory River / Life Map / Photos / Peek at Memoir) + chat column + context panel; Take-a-break overlay; chat scroll stabilization |
| WO-UI-TEST-LAB-01 | Complete | Operator UI Health Check inside Bug Panel; 15 categories (added Document Archive); PASS / WARN / FAIL / DISABLED / NOT_INSTALLED / SKIP / INFO |
| WO-SESSION-STYLE-WIRING-01 | Complete | Operator session-style picker drives narrator behavior; questionnaire_first BYPASSES the v9 incomplete-narrator gate (Corky rule) |
| WO-HORNELORE-SESSION-LOOP-01 | Complete | Post-identity orchestrator: one Bio Builder question at a time + sessionStyle routing + repeatable-section deferred-handoff |
| WO-10C | Complete | Cognitive Support Mode — 6 dementia-safe behavioral guarantees (protected silence at 120s/300s/600s, invitational re-entry, no correction, single-thread context, visual-as-patience, invitational prompts) |
| WO-MEDIA-WATCHFOLDER-01 | Planned | Auto-import from `C:\Users\chris\Hornelore Scans\` into Document Archive intake queue |
| WO-MEDIA-OCR-01 | Planned | Tesseract OCR for scanned docs; promotes `text_status` from `image_only_needs_ocr` → `ocr_complete` |
| WO-MEDIA-ARCHIVE-CANDIDATES-01 | Planned | Harvest items flagged `candidate_ready=true` and surface to Bio Builder review queue |

### WO-13 Phase Status

| Phase | Status | Description |
|---|---|---|
| 1 | Complete | Schema: family_truth_notes + family_truth_rows + family_truth_promoted |
| 2 | Complete | Family truth router (CRUD endpoints) |
| 3 | Complete | Reference narrator write guards |
| 4 | Complete | Chat extraction → shadow archive pipeline, legacy facts freeze |
| 5 | Complete | Cross-narrator contamination filter |
| 6 | Complete | Review drawer UI (wo13-review.js) |
| 7 | Complete | Promote with UPSERT semantics into family_truth_promoted |
| 8 | Complete | Flag-gated profile read seam (hybrid builder) |
| 9 | Complete | Kent dry run — validation, operator runbook |

### WO-CR Phase Status

| Phase | Status | Description |
|---|---|---|
| CR-01 | Complete | Left Chronology Accordion scaffold — three-lane merge, API endpoint, UI column |
| CR-01B | Complete | Intra-year sort hotfix — personal before ghost before world |
| CR-02 | Complete | Mapper expansion — compound dedup keys, strict questionnaire fallback, 14-field promoted whitelist |
| CR-03 | Complete | Visual tuning — personal anchors dominate, ghost clearly non-factual, active-era emphasis |
| CR-04 | Complete | Lori timeline awareness — provenance-tagged `chronology_context` in runtime payload |

---

## Relationship to Lorevox

Hornelore is not a fork or a peer of Lorevox. **Hornelore is the family-locked R&D crucible. Lorevox is the distilled public product.** Features prove themselves here against real older-adult narrators — Chris, Kent, Janice — and only the ones that earn it get promoted into Lorevox, generalized for arbitrary narrators, with all the Horne-specific scaffolding stripped out. The relationship is one-way and deliberate: lab → gold, by promotion, never by file-parity backport.

**What stays here forever (Hornelore-only by design):**

- **Closed Horne narrator universe** — three named narrators plus two read-only trainer narrators (Shatner, Dolly). UI controls for adding or deleting narrators are removed; backend write guards block creation.
- **Pre-seeded Horne identity** — narrators auto-seeded from JSON templates on first startup; identity phase bypassed for known narrators.
- **Family templates** — `kent-james-horne.json`, `janice-josephine-horne.json`, `christopher-todd-horne.json`.
- **Bug Panel as a dev surface** — operator-only debugging utilities (Reset Identity, Purge Test Narrators, BB Walk Test harness, Audio Preflight, Health Check, Export Current Session). Lab tooling, not product.
- **Local family-specific flags, fixtures, and parent-session runbooks.**
- **Separate data** — own database (`hornelore.sqlite3`) and filesystem (`/mnt/c/hornelore_data/`).
- **Renamed shell** — `hornelore1.0.html` instead of the public Lorevox shell.

**What was here first because of the WO-11 separation but can run in both places:**

- Quality Harness (WO-QA-01 / WO-QA-02 / WO-QA-02B) — currently shaped to Hornelore's eval cadence; the harness *infrastructure* could promote, but the present form is lab-tuned.
- Extractor lane improvements (WO-EX series) — too active to promote yet; locked baseline 70/104 on the master eval.

---

## Lorevox promotion queue

This is the live distillation list — what's been proven in Hornelore and is ready to move into the public Lorevox product. The canonical version of the queue lives in the Lorevox README under "Hornelore Promotion Queue"; the abbreviated mirror below is for operator awareness while working in this repo.

The queue is not automatic and not based on file-parity. Each candidate feature gets a deliberate decision: **promote** (generalize and move to Lorevox), **hold** (still in flux, keep iterating in Hornelore), or **Hornelore-only by design** (stays here, see above).

**A. Proven — ready to promote**

Validated against real narrators in this repo. Promotion requires removing Horne-family-specific assumptions and generalizing for arbitrary narrator universes.

- **Four-layer truth pipeline (WO-13)** — shadow archive → proposals → human review → promoted truth. Already aligned with Lorevox's "Archive → History → Memoir" doctrine; this is the structural enforcement of "AI cannot promote claims without human review."
- **Photo system** — curator photo intake (single + batch), EXIF auto-fill, Nominatim reverse-geocoding, Plus Code generator, View/Edit modal, narrator-room lightbox, dedupe-by-file-hash.
- **Document Archive (WO-MEDIA-ARCHIVE-01)** — separate curator lane for PDFs / scanned docs / handwritten notes / genealogy outlines / letters / certificates / clippings. Locked product rule: preserve first, never auto-promote to truth.
- **Memory Archive (WO-ARCHIVE-AUDIO-01)** — per-session two-sided text transcript, narrator-only audio capture rule, per-session zip export, per-turn metadata stamping.
- **Per-turn audio capture (backend)** — webm audio attachment endpoint.
- **Three-tab UI shell (WO-UI-SHELL-01)** — Operator / Narrator Session / Media split with session-style picker.
- **Narrator room (WO-NARRATOR-ROOM-01)** — dedicated layout with view tabs (Memory River / Life Map / Photos / Peek at Memoir), Take-a-break overlay, chat scroll stabilization.
- **Cognitive Support Model (WO-10C)** — six dementia-safe behavioral guarantees (protected silence 120s / 300s / 600s, invitational re-entry, no correction, single-thread context, visual-as-patience, invitational prompts). The parent-session test data lives here; the *model* — the older-adult pacing pattern — is the single strongest distillable artifact for OT/life-review use, and belongs in Lorevox.
- **Bio Builder contamination hardening** — narrator-switch generation counter + 3-guard backend response check + scope hard-gates eliminating cross-narrator data leakage. Required before any multi-narrator product can ship safely.
- **Operator UI Health Check (WO-UI-TEST-LAB-01)** — 15-category PASS / WARN / FAIL / DISABLED / NOT_INSTALLED / SKIP / INFO grid with sub-100ms full run.
- **Chronology Accordion (WO-CR)** — read-only left-side time ladder merging three lanes (world / personal / ghost) at request time. Provenance-tagged so Lori knows confirmed truth versus context. Source-of-truth-agnostic; generalizes cleanly.
- **Soft transcript review cue + audio preflight check** — small but proven UX safeguards.

**B. Hold — keep in Hornelore until stable**

Still iterating in the lab; promotion blocked until they lock to a measurable acceptance threshold.

- **Extractor lane (LOOP-01 R5h+)** — locked baseline 70/104 on the 104-case master eval; SPANTAG / BINDING-01 / LORI-CONFIRM stack in flight. See `CLAUDE.md` changelog for the live trail.
- **Phase-aware question composer** — flag-gated, working but not locked.
- **Photo Phase 2 ELICIT** — Lori-side narration over photos; spec ready, LLM prompts pending.
- **Future Document Archive lanes** — WATCHFOLDER, OCR, ARCHIVE-CANDIDATES; scoped, not built.

**C. Hornelore-only by design** — see "Relationship to Lorevox" section above.

---

## License

Copyright (c) 2026 Chris (dev@lorevox.com). All rights reserved.

Hornelore is governed by the same **Lorevox Source-Available Proprietary License (Version 1.1 — 2026)** as the public Lorevox product. Hornelore is the family-locked R&D crucible; it is not a separate license surface. The same restrictions apply: source-available for view and study; no commercial use, hosting for third parties, redistribution, or public forks; no use of prompts, schemas, or outputs for ML training; named brands (Lorevox, Lori, Hornelore) and expressive implementations are reserved.

**Commercial, institutional, research, nonprofit, educational, clinical, archival, family-office, elder-care, SaaS, hosted, deployment, integration, white-label, or third-party use is available by separate written license.** Contact dev@lorevox.com to discuss terms.

Third-party libraries and dependencies remain subject to their own licenses. End-user data — narrator records, family photos, scanned documents, transcripts, memoir drafts — is owned by the operator and narrator who created it; this License grants no claim over such content.

Contributions are by invitation only and require full assignment of rights to the copyright holder.

See [LICENSE](LICENSE) for complete terms. For permissions: dev@lorevox.com

---
