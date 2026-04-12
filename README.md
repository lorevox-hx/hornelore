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

---

## File Inventory

| Category | Count | Key Files |
|---|---|---|
| JavaScript (UI) | 37 | app.js, api.js, state.js, wo13-review.js, narrator-preload.js |
| CSS | 11 | |
| HTML shell | 1 | `hornelore1.0.html` |
| Narrator templates | 6 | 3 family + 2 trainers + 1 base |
| Server routers | 25 | family_truth.py, profiles.py, extract.py, narrator_state.py |
| Scripts | 21 | preload_trainer.py, import_kent_james_horne.py, start/stop/restart |
| Tests | 4+ | test_api_smoke.py, test_db_smoke.py, e2e/ |
| Config | 4 | .env, package.json, playwright.config.ts, tsconfig |

---

## Work Orders

| WO | Status | Description |
|---|---|---|
| WO-8 | Complete | Transcript history, thread anchors, narrator resume flow |
| WO-9 | Complete | Rolling summaries, recent turns, memory intelligence |
| WO-10 | Complete | Cognitive support, operator tools, memory intelligence |
| WO-11 | Complete | Standalone repo separation from Lorevox |
| WO-12B | Complete | Cross-narrator contamination hunt and evidence archive |
| WO-13 | **Active** | Four-layer truth pipeline (phases 1-9) |

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
| 9 | **In Progress** | Kent dry run — validation, operator runbook |

---

## Key Differences from Lorevox

Hornelore is not a fork. It is a curated subset with a different product surface.

- **Closed narrator universe** — Lorevox allows creating unlimited narrators. Hornelore is locked to three (plus two read-only trainers).
- **Pre-seeded identity** — Lorevox interviews each narrator to establish identity. Hornelore loads identity from templates.
- **No creation or deletion** — UI controls for adding and removing narrators are disabled.
- **Separate data** — Hornelore uses its own database and filesystem. Running both products simultaneously is safe.
- **Four-layer truth pipeline** — WO-13 adds shadow archive, proposals, review, and promoted truth layers that Lorevox does not have.
- **Renamed shell** — `hornelore1.0.html` instead of `lori9.0.html`. Brand reads "Hornelore 1.0 — Horne Family Archive".
