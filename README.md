# Hornelore 1.0

**A curated, hardened production build of Lorevox — locked to the Horne family.**

Hornelore captures the life stories of Christopher Todd Horne, Kent James Horne, and Janice Josephine Horne. It is not a general-purpose memoir platform. It is a family archive with a fixed narrator universe, pre-seeded identity data, and no way to create or delete narrators through the UI.

Built from a live-audited subset of Lorevox 9.0. Every included file was verified against actual browser network requests — not inferred from imports or guessed from the repo tree.

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

Both flags are currently **ON** in `.env`. The profile read seam uses a hybrid strategy: promoted-truth values override `basics.*` for the 5 protected identity fields; all other promoted rows appear in a `basics.truth[]` sidecar array; unmapped fields (kinship, pets, culture, pronouns, etc.) pass through from legacy `profile_json`.

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
| Scripts | 25 | preload_trainer.py, import_kent_james_horne.py, start/stop/restart, run_test_lab.sh, seed_test_narrators.py, test_lab_runner.py, test_lab_doctor.sh, test_lab_watch.sh |
| Tests | 4+ | test_api_smoke.py, test_db_smoke.py, e2e/ |
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
| WO-QA-02 | Complete | Archive-truth methodology — Channel A ceilings + suppression ranking |
| WO-QA-02B | Complete | Seed determinism — `chat_ws.py` honors `params.seed` for reproducible runs |
| WO-14 | Deferred | TensorRT-LLM runtime swap (deferred pending Blackwell SM_120 maturity) |

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

## Key Differences from Lorevox

Hornelore is not a fork. It is a curated subset with a different product surface.

- **Closed narrator universe** — Lorevox allows creating unlimited narrators. Hornelore is locked to three (plus two read-only trainers).
- **Pre-seeded identity** — Lorevox interviews each narrator to establish identity. Hornelore loads identity from templates.
- **No creation or deletion** — UI controls for adding and removing narrators are disabled.
- **Separate data** — Hornelore uses its own database and filesystem. Running both products simultaneously is safe.
- **Four-layer truth pipeline** — WO-13 adds shadow archive, proposals, review, and promoted truth layers that Lorevox does not have.
- **Chronology Accordion** — WO-CR-01 / WO-CR-PACK-01 add a read-only left-side time ladder that merges three lanes (world / personal / ghost) at request time. Never writes to the database; gives Lori provenance-tagged temporal context without creating a new truth layer.
- **Renamed shell** — `hornelore1.0.html` instead of `lori9.0.html`. Brand reads "Hornelore 1.0 — Horne Family Archive".
