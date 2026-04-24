# WO-LORI-PHOTO-SHARED-01 — Shared Photo Authority Layer + Phase 1 Vertical Slice

**Status:** READY FOR EXECUTION
**Mode:** Surgical implementation
**Scope:** Shared backend / schema foundation + minimal runnable Phase 1 slice
**Goal:** Land the stable photo authority layer that both curator intake (Phase 2) and narrator elicitation (Phase 2) will build on.

---

## 0. UX AUTHORITY LOCK

The source of truth for the user experience is:

```
ui/mockups/lori_photo_mockup.html
```

Any behavior ambiguity in this spec is resolved by that mockup. The mockup is not a binding implementation plan — it is the authoritative UX reference. Spec overrides mockup only when explicitly noted (e.g., 4-mode conflict resolution supersedes mockup's 3-mode).

---

## 1. SPEC HIERARCHY (LOCKED)

```
WO-LORI-PHOTO-SHARED-01 = Phase 1 authority layer (this spec)
WO-LORI-PHOTO-INTAKE-01 = Phase 2 curator intelligence only
WO-LORI-PHOTO-ELICIT-01 = Phase 2 narrator intelligence only
```

SHARED-01 lands the full Phase 1 vertical slice — schema, services, API, three UI pages, tests. INTAKE and ELICIT are stripped to their Phase 2 scope (EXIF, real geocoder, LLM extraction, conflict detector, review queue) and do not land until SHARED-01 ships green.

---

## 2. HARD RULES

**DO NOT:**
- Touch `server/code/api/routers/extract.py`
- Add LLM extraction on the photo path
- Add real geocoding
- Build the conflict detector
- Merge curator and narrator UIs
- Require all photo facts before save

**Phase 1 principles:**
- A photo may be saved incomplete.
- A photo may be shown to a narrator even with unknown date / place / people.
- Every write carries provenance.
- Narrator memory capture is raw transcript only.
- The r5h extractor baseline stays untouched.

---

## 3. FILE TARGETS

### NEW

```
server/code/services/photos/__init__.py
server/code/services/photos/models.py
server/code/services/photos/repository.py
server/code/services/photos/provenance.py
server/code/services/photos/confidence.py

server/code/services/photo_intake/__init__.py
server/code/services/photo_intake/dedupe.py
server/code/services/photo_intake/thumbnail.py
server/code/services/photo_intake/storage.py
server/code/services/photo_intake/geocode.py

server/code/services/photo_elicit/__init__.py
server/code/services/photo_elicit/selector.py
server/code/services/photo_elicit/template_prompt.py

server/code/api/routers/photos.py

server/code/db/migrations/NNNN_lori_photo_shared.sql

ui/photo-intake.html
ui/photo-elicit.html
ui/photo-timeline.html

ui/js/photo-intake.js
ui/js/photo-elicit.js
ui/js/photo-timeline.js

ui/css/photo-intake.css
ui/css/photo-elicit.css
ui/css/photo-timeline.css

data/prompts/photo_gentle_followups.json   (already landed in prior docs commit)

tests/services/photos/test_repository.py
tests/services/photos/test_provenance.py
tests/services/photos/test_confidence.py
tests/services/photo_intake/test_dedupe.py
tests/services/photo_intake/test_storage.py
tests/services/photo_intake/test_geocode_null.py
tests/services/photo_elicit/test_template_prompt.py
tests/services/photo_elicit/test_selector.py
tests/api/test_photos_shared.py
```

### MODIFIED

```
server/code/api/main.py
server/code/flags/__init__.py
.env.example
CLAUDE.md
```

---

## 4. FEATURE FLAG

Add to `.env.example` and `server/code/flags/__init__.py`:

```
HORNELORE_PHOTO_ENABLED=0
```

**Behavior:**
- Flag OFF: router returns 404 on all `/api/photos/*` endpoints. The three HTML files still ship to disk (they are static) but `GET /` should not advertise links to them.
- Flag ON: full feature active.
- Do not split into `HORNELORE_PHOTO_INTAKE` / `HORNELORE_PHOTO_ELICIT` in Phase 1. The Phase 2 split will gate the extractor profile and the curator conflict-review UI, not the base narrator page.

---

## 5. SCHEMA (EXACT SQL)

File: `server/code/db/migrations/NNNN_lori_photo_shared.sql`

```sql
BEGIN;

------------------------------------------------------------
-- photos
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photos (
    id TEXT PRIMARY KEY,
    narrator_id TEXT NOT NULL,

    image_path TEXT NOT NULL,
    thumbnail_path TEXT,
    media_url TEXT,
    thumbnail_url TEXT,

    file_hash TEXT NOT NULL UNIQUE,

    description TEXT,

    date_value TEXT,
    date_precision TEXT NOT NULL DEFAULT 'unknown'
        CHECK (date_precision IN ('exact', 'month', 'year', 'decade', 'unknown')),

    location_label TEXT,
    location_source TEXT NOT NULL DEFAULT 'unknown'
        CHECK (location_source IN (
            'exif_gps',
            'typed_address',
            'spoken_place',
            'description_geocode',
            'unknown'
        )),

    latitude REAL,
    longitude REAL,

    narrator_ready INTEGER NOT NULL DEFAULT 0,
    needs_confirmation INTEGER NOT NULL DEFAULT 1,

    -- Provenance columns (authoritative; metadata_json is non-authoritative)
    uploaded_by_user_id TEXT,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_edited_by_user_id TEXT,
    last_edited_at TEXT,
    deleted_at TEXT,

    metadata_json TEXT NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photos_narrator_id
    ON photos(narrator_id);
CREATE INDEX IF NOT EXISTS idx_photos_narrator_ready
    ON photos(narrator_id, narrator_ready);
CREATE INDEX IF NOT EXISTS idx_photos_date
    ON photos(date_value, date_precision);
CREATE INDEX IF NOT EXISTS idx_photos_uploaded_by
    ON photos(uploaded_by_user_id);
CREATE INDEX IF NOT EXISTS idx_photos_deleted_at
    ON photos(deleted_at);

------------------------------------------------------------
-- photo_people
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_people (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    person_id TEXT,
    person_label TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_actor_id TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_people_photo_id
    ON photo_people(photo_id);

------------------------------------------------------------
-- photo_events
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_events (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    event_id TEXT,
    event_label TEXT NOT NULL,

    source_type TEXT NOT NULL,
    source_authority TEXT NOT NULL,
    source_actor_id TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low', 'unknown')),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_events_photo_id
    ON photo_events(photo_id);

------------------------------------------------------------
-- photo_sessions
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_sessions (
    id TEXT PRIMARY KEY,
    narrator_id TEXT NOT NULL,
    session_id TEXT,          -- optional link to interview session (semantics deferred; see Open Questions)

    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photo_sessions_narrator_id
    ON photo_sessions(narrator_id);
CREATE INDEX IF NOT EXISTS idx_photo_sessions_open
    ON photo_sessions(narrator_id, ended_at);

------------------------------------------------------------
-- photo_session_shows
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_session_shows (
    id TEXT PRIMARY KEY,
    photo_session_id TEXT NOT NULL,
    photo_id TEXT NOT NULL,

    shown_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    outcome TEXT NOT NULL DEFAULT 'shown'
        CHECK (outcome IN (
            'shown',
            'story_captured',
            'zero_recall',
            'distress_abort',
            'skipped',
            'technical_abort'
        )),

    prompt_text TEXT,
    followup_text TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_session_id) REFERENCES photo_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_session_shows_session_id
    ON photo_session_shows(photo_session_id);
CREATE INDEX IF NOT EXISTS idx_photo_session_shows_photo_id
    ON photo_session_shows(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_session_shows_outcome
    ON photo_session_shows(photo_id, outcome, shown_at);

------------------------------------------------------------
-- photo_memories
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS photo_memories (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    photo_session_show_id TEXT NOT NULL,

    transcript TEXT NOT NULL DEFAULT '',

    memory_type TEXT NOT NULL DEFAULT 'episodic_story'
        CHECK (memory_type IN (
            'episodic_story',
            'emotional_flash',
            'general_mood',
            'zero_recall',
            'distress_abort'
        )),

    -- STT transcript safety (integrates with WO-STT-LIVE-02)
    transcript_source TEXT,            -- 'stt_live' | 'typed' | 'hybrid' | NULL (system-generated)
    transcript_confidence REAL,        -- 0.0..1.0, min-over-segments from STT engine
    transcript_guard_flags TEXT,       -- JSON array of fragile-fact flags, e.g. ["fragile_name"]
    finalized_at TEXT,                 -- NULL while in-progress (follow-ups pending); set on close

    -- Provenance
    source_type TEXT NOT NULL DEFAULT 'narrator_story',
    source_authority TEXT NOT NULL DEFAULT 'narrator',
    source_actor_id TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
    FOREIGN KEY(photo_session_show_id) REFERENCES photo_session_shows(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_photo_memories_photo_id
    ON photo_memories(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_memories_show_id
    ON photo_memories(photo_session_show_id);

COMMIT;
```

**Notes on the schema:**
- `photos.metadata_json` is **non-authoritative**. It carries EXIF blob, orientation, storage-provider metadata, and similar optional data only. Provenance lives in explicit columns.
- All six tables are created inside a single `BEGIN / COMMIT` transaction so a failed migration leaves a clean state.
- Soft-delete is represented by `photos.deleted_at`. Repository reads must filter `WHERE deleted_at IS NULL` by default.

---

## 6. SHARED MODELS

File: `server/code/services/photos/models.py`

Define Pydantic (or project-standard) models matching the schema:

```
Photo
PhotoPerson
PhotoEvent
PhotoSession
PhotoSessionShow
PhotoMemory
ProvenanceStamp
```

**Locked enums:**

```
date_precision:      exact | month | year | decade | unknown
location_source:     exif_gps | typed_address | spoken_place | description_geocode | unknown
memory_type:         episodic_story | emotional_flash | general_mood | zero_recall | distress_abort
show_outcome:        shown | story_captured | zero_recall | distress_abort | skipped | technical_abort
confidence:          high | medium | low | unknown
transcript_source:   stt_live | typed | hybrid  (also NULL for system-generated)
```

**Locked naming (no synonyms anywhere in code, tests, or UI):**

```
person_label      (NOT person_name / person_name_raw)
date_precision    (NOT captured_at_confidence / date_accuracy)
location_label    (NOT place / place_text / place_name)
```

---

## 7. PROVENANCE RULES

File: `server/code/services/photos/provenance.py`

```python
def make_provenance(
    source_type: str,
    source_authority: str,
    source_actor_id: str | None = None,
) -> dict
```

**Allowed `source_type` (Phase 1):**
```
curator_input
narrator_story
system_hash
system_thumbnail
system_template_prompt
```

`system_exif` is deliberately omitted. Phase 1 has no EXIF extraction; the Phase 2 INTAKE spec will add `system_exif` to this enum when EXIF lands.

**Allowed `source_authority`:**
```
curator
narrator
system
imported
```

**Phase 1 hard requirements:**
- Every `photo_people` row carries provenance.
- Every `photo_events` row carries provenance.
- Every `photo_memories` row carries provenance.
- Every `photos` row carries `uploaded_by_user_id` + `uploaded_at` at creation; `last_edited_by_user_id` + `last_edited_at` on any PATCH.
- `metadata_json` may carry EXIF / orientation / storage hints only — not provenance.

Conflict detection is **Phase 2**. Do not implement it here.

---

## 8. CONFIDENCE RULES

File: `server/code/services/photos/confidence.py`

```python
def resolve_date_confidence(date_value, date_precision) -> str
```

| Precision  | Confidence |
|------------|------------|
| `exact`    | `high`     |
| `month`    | `medium`   |
| `year`     | `medium`   |
| `decade`   | `low`      |
| `unknown`  | `unknown`  |

```python
def resolve_location_confidence(location_source) -> str
```

| Source                | Confidence |
|-----------------------|------------|
| `exif_gps`            | `high`     |
| `typed_address`       | `medium`   |
| `spoken_place`        | `low`      |
| `description_geocode` | `low`      |
| `unknown`             | `unknown`  |

```python
def needs_confirmation_for_location(location_source) -> bool
```

| Source                | `needs_confirmation` |
|-----------------------|----------------------|
| `exif_gps`            | `False`              |
| all other sources     | `True`               |

---

## 9. INTAKE SERVICES (PHASE 1)

### `dedupe.py`

```python
def sha256_file(path: str) -> str
```
Acceptance: same bytes → same hash; different bytes → different hash.

### `thumbnail.py`

```python
def create_thumbnail(
    source_path: str,
    target_path: str,
    longest_edge: int = 400,
) -> dict  # { "path": str, "width": int, "height": int }
```
Pillow-backed. Preserves aspect ratio. EXIF orientation honored when writing the thumbnail.

### `storage.py`

```python
def store_photo_file(
    narrator_id: str,
    source_path: str,
    original_filename: str,
) -> dict  # { "photo_id", "image_path", "thumbnail_path", "file_hash" }
```

**Layout:**
```
DATA_DIR/memory/archive/photos/{narrator_id}/{photo_id}/original.{ext}
DATA_DIR/memory/archive/photos/{narrator_id}/{photo_id}/thumb_400.jpg
```

Creates parent directories idempotently. Fails fast if `DATA_DIR` is unset.

### `geocode.py` (Phase 1 = stub only)

```python
class NullGeocoder:
    def geocode(self, text: str) -> dict:
        return {
            "latitude": None,
            "longitude": None,
            "location_source": "unknown",
            "provider": "null",
        }
```

No network. No API keys. No Google dependency. Real geocoder lands in Phase 2 (INTAKE spec).

---

## 10. ELICIT SERVICES (PHASE 1)

### `template_prompt.py`

```python
def build_photo_prompt(photo: dict) -> str
```

**Tiers:**

*Tier high — people + place + date known:*
> `This photo shows {people}{place}{date}. Tell me what you remember about this moment.`

*Tier medium — partial (some combination of people / place / date known):*
> `I have a little information about this photo. Tell me what you remember when you look at it.`

*Tier zero — nothing known:*
> `I'm not sure when or where this was taken, but it looks meaningful. What do you remember when you look at it?`

**Forbidden phrasings (enforced by test):**
- `What year`
- `Who is this`
- `Confirm`

**People-list joining:** `X` for one, `X and Y` for two, `X, Y, and Z` for three+. Never read curator people-tag IDs aloud — only labels. "Teach the test" rule applies.

### `selector.py`

```python
def select_next_photo(
    narrator_id: str,
    repository,
) -> Photo | None
```

**Phase 1 rules (hard, not soft):**

```
ZERO_RECALL_COOLDOWN = 10     # shows
DISTRESS_ABORT_COOLDOWN = 30  # shows
```

Pseudocode:

```
ready_photos = repository.list_photos(narrator_id, narrator_ready=True, deleted=False)
shown_index  = repository.recent_shows(narrator_id, limit=max(ZERO_RECALL_COOLDOWN, DISTRESS_ABORT_COOLDOWN))

for photo in prioritize_unshown_first(ready_photos):
    last = repository.last_show_for_photo(photo.id)
    if last is None:
        return photo
    distance = count_shows_since(shown_index, last.shown_at)  # number of shows across any photo since this one's last
    if last.outcome == 'distress_abort' and distance < DISTRESS_ABORT_COOLDOWN:
        continue
    if last.outcome == 'zero_recall' and distance < ZERO_RECALL_COOLDOWN:
        continue
    return photo

return None
```

No ML. No scoring. Phase 2 selector abstraction is tracked in Open Questions.

---

## 11. GENTLE FOLLOW-UP LIBRARY

File: `data/prompts/photo_gentle_followups.json` (already landed in prior docs commit).

Phase 1 selection is random or round-robin; LLM is not involved. Seed entries live in the JSON; curator may edit.

---

## 12. REPOSITORY

File: `server/code/services/photos/repository.py`

SQLite-backed, uses existing project DB conventions. Required methods:

```
create_photo(...)
get_photo(photo_id)
list_photos(narrator_id, narrator_ready=None, deleted=False)
mark_photo_ready(photo_id, narrator_ready: bool, actor_id: str)
patch_photo(photo_id, patch: dict, actor_id: str)
soft_delete_photo(photo_id, actor_id: str)

add_photo_person(photo_id, person_label, person_id=None, provenance=...)
add_photo_event(photo_id, event_label,  event_id=None,  provenance=...)

create_photo_session(narrator_id, session_id=None)
end_photo_session(photo_session_id)         # sets ended_at; finalizes open shows

record_photo_show(photo_session_id, photo_id, prompt_text)
update_photo_show_outcome(show_id, outcome)
finalize_open_shows_for_session(photo_session_id)   # used by end_photo_session

create_photo_memory(
    photo_id,
    photo_session_show_id,
    transcript,
    memory_type,
    transcript_source=None,
    transcript_confidence=None,
    transcript_guard_flags=None,
    provenance=...,
)
list_photo_memories(photo_id)
last_show_for_photo(photo_id)
recent_shows(narrator_id, limit)
```

**Rule — no dangling `shown`:**
- When `end_photo_session` runs, any `photo_session_shows` with outcome `shown` must be resolved.
- Default resolution: outcome → `skipped` (the narrator was shown the photo but no memory was captured before session end).
- `technical_abort` is reserved for errors that interrupted a show attempt (audio failure, crash, etc.) and must be set explicitly by the caller.

---

## 13. API ROUTER

File: `server/code/api/routers/photos.py`
Prefix: `/api/photos`

All endpoints require `HORNELORE_PHOTO_ENABLED=1`; otherwise 404.

### `GET /api/photos/health`

```
{ "ok": true, "enabled": true }
```

### `POST /api/photos`

**Locked: multipart upload.**

```
Content-Type: multipart/form-data

Fields:
  file                 (required) — image binary
  narrator_id          (required)
  uploaded_by_user_id  (required)
  description          (optional)
  date_value           (optional; ISO 8601 partial or full)
  date_precision       (optional; default 'unknown')
  location_label       (optional)
  location_source      (optional; default 'unknown')
  narrator_ready       (optional; default false)
  people[]             (optional; list of {person_label, person_id?})
  events[]             (optional; list of {event_label, event_id?})
```

Server-side flow:
1. Stream file to a temp path; compute sha256 (`dedupe.sha256_file`).
2. If `file_hash` already exists for this narrator: return 409 with the existing photo.
3. Store file + thumbnail (`storage.store_photo_file`).
4. Insert `photos` row with provenance (`uploaded_by_user_id`, `uploaded_at`).
5. Insert `photo_people` / `photo_events` rows if provided, each with curator provenance.
6. Return created `photos` row + people/events.

### `GET /api/photos?narrator_id=...[&narrator_ready=true|false]`

Lists photos for the narrator. Filters soft-deleted. Optional `narrator_ready` filter.

### `GET /api/photos/{photo_id}`

Returns photo + people + events.

### `PATCH /api/photos/{photo_id}`

Payload (any subset):

```
description
date_value
date_precision
location_label
location_source
narrator_ready
needs_confirmation
last_edited_by_user_id   (required)
```

Recomputes `needs_confirmation` from `location_source` if `needs_confirmation` not explicitly set.
Stamps `last_edited_by_user_id` + `last_edited_at`.

### `DELETE /api/photos/{photo_id}`

Soft-delete: sets `deleted_at`. Does not remove files.

### `POST /api/photos/sessions`

Creates a `photo_sessions` row. Payload: `{ narrator_id, session_id? }`.

### `POST /api/photos/sessions/{photo_session_id}/show-next`

Runs `select_next_photo`, records a `photo_session_shows` row, returns:

```
{
  "photo":       <Photo>,
  "show_id":     "...",
  "prompt_text": "..."
}
```

If no eligible photo: `{ "photo": null }` (200, not 404).

### `POST /api/photos/shows/{show_id}/memory`

Creates a `photo_memories` row and updates the show outcome.

Payload:

```
transcript                (required; may be "" for zero_recall / distress_abort)
memory_type               (required)
transcript_source         (optional)
transcript_confidence     (optional)
transcript_guard_flags    (optional; JSON array, will be stored as JSON string)
```

**Rules:**
- Empty transcript allowed **only** for `memory_type` ∈ `{zero_recall, distress_abort}`.
- `memory_type='zero_recall'`    → show outcome = `zero_recall`
- `memory_type='distress_abort'` → show outcome = `distress_abort`
- Otherwise                       → show outcome = `story_captured`
- `photo_memories.finalized_at` left NULL by this endpoint (follow-ups may append). Session-end finalizes it.

### `POST /api/photos/sessions/{photo_session_id}/end` **(new; required)**

- Sets `photo_sessions.ended_at = CURRENT_TIMESTAMP`.
- Calls `finalize_open_shows_for_session`: every `photo_session_shows` row with outcome `shown` for this session is updated to `skipped`.
- Sets `photo_memories.finalized_at = CURRENT_TIMESTAMP` for any memory rows in this session whose `finalized_at` is NULL.
- Returns the closed session summary.

No dangling `shown` rows survive `end`. This is enforced by test.

---

## 14. UI MINIMAL RUNNABLE SLICE

Three separate HTML pages. Hard separation — no tab-gating between curator and narrator.

### `ui/photo-intake.html` (curator only)

- Upload widget (multipart `POST /api/photos`)
- `person_label` free-text input (multi)
- `date_value` input
- `date_precision` select
- `location_label` input
- `location_source` select
- `description` textarea
- `narrator_ready` checkbox
- Save button
- Saved-photo preview list
- **No** narrator session controls
- **No** prompt text, no transcript textarea

### `ui/photo-elicit.html` (narrator only)

**Route:** `ui/photo-elicit.html?narrator_id=<id>` (Phase 1 routing; auth deferred).

**Elements:**
- Large photo area (dominates viewport)
- Lori prompt text (rendered from `build_photo_prompt`)
- Transcript textarea or mic affordance (integrates with WO-STT-LIVE-02 `TranscriptGuard`)
- `Capture Story` button (POST memory with `memory_type='episodic_story'`; other memory types selected by UI flow)
- `Zero Recall` button (POST memory with `memory_type='zero_recall'`, transcript="")
- `Distress / Stop` button (POST memory with `memory_type='distress_abort'`, transcript="", then navigate to a soft wind-down screen)
- `Gentle Follow-up` button (pulls from `photo_gentle_followups.json`, renders; no network round-trip required)
- **No** curator fields, no upload affordance, no metadata editing, no conflict resolution, no review queue

**WO-10C compliance (load-bearing for dementia safety):**

```
Silence thresholds:
  120s → play a gentle follow-up prompt (from photo_gentle_followups.json)
  300s → invitational re-entry prompt
  600s → session wind-down (POST /sessions/{id}/end; show a quiet exit screen)

Behavioral guarantees:
  - Protected silence: no auto-interruption until 120s
  - No correction: Lori never contradicts a narrator's fact
  - Re-entry prompts bypass confidence gating
  - Single-thread context: one active photo at a time
  - Visual-as-patience: UI never spins / flashes "waiting"
```

Contract reference: `Hornelore-WO10C-Cognitive-Support-Report.docx` in the hornelore repo. If a constraint in that report contradicts this spec, the report wins.

**Transcript-guard integration (WO-STT-LIVE-02):**
- `photo-elicit.js` consumes `window.TranscriptGuard` to stage transcripts, capture `transcript_source`, `transcript_confidence`, and fragile-fact flags.
- Payload to `POST /api/photos/shows/{show_id}/memory` includes those fields when the frontend has them.
- Fragile-fact flags do **not** trigger any correction UI in Phase 1; they are recorded for curator review in Phase 2.

### `ui/photo-timeline.html` (shared read-only)

- Grouped by decade, then year, with a `Undated` bucket for photos lacking `date_value`
- Each entry: thumbnail + curator facts + memory transcript count
- Read-only; no editing, no session controls

### JS modules

```
ui/js/photo-intake.js    → /api/photos + PATCH + DELETE
ui/js/photo-elicit.js    → /api/photos/sessions/* + transcript-guard integration + WO-10C timers
ui/js/photo-timeline.js  → GET /api/photos + GET /api/photos/{id}
```

### CSS

- Tablet-first.
- Large buttons.
- **No** red required-field styling. Unknown states are normal and not visually stigmatized.

---

## 15. ROUTER REGISTRATION

File: `server/code/api/main.py`

Register the photos router behind an endpoint-level flag guard or a conditional `include_router` call, whichever matches the current app pattern. Do not disturb existing routers. Document the chosen pattern in the commit message.

---

## 16. ACCEPTANCE TESTS

Run with `pytest`.

### A. Schema (`tests/api/test_photos_shared.py`)

- Migration creates all six tables.
- `photos.file_hash` is unique.
- `date_precision` rejects values outside the enum.
- `location_source` rejects values outside the enum.
- `photo_session_shows.outcome` supports `distress_abort`.
- `photo_memories.memory_type` supports `zero_recall` and `distress_abort`.
- `photos` has `uploaded_by_user_id`, `uploaded_at`, `last_edited_by_user_id`, `last_edited_at`, `deleted_at` columns.
- `photo_memories` has `transcript_source`, `transcript_confidence`, `transcript_guard_flags`, `finalized_at` columns.

### B. Provenance (`tests/services/photos/test_provenance.py`)

- Curator-added person: `source_type='curator_input'`, `source_authority='curator'`.
- Narrator memory: `source_type='narrator_story'`, `source_authority='narrator'`.
- System hash stamp: `source_type='system_hash'`, `source_authority='system'`.
- Photo PATCH stamps `last_edited_by_user_id` and `last_edited_at`.

### C. Confidence (`tests/services/photos/test_confidence.py`)

- `exif_gps` → `high`, `needs_confirmation=False`.
- `typed_address` → `medium`, `needs_confirmation=True`.
- `spoken_place` → `low`, `needs_confirmation=True`.
- `unknown` → `unknown`, `needs_confirmation=True`.

### D. Dedupe (`tests/services/photo_intake/test_dedupe.py`)

- Same bytes → same sha256.
- Different bytes → different sha256.

### E. NullGeocoder (`tests/services/photo_intake/test_geocode_null.py`)

- No network sockets opened (use `socket.socket` monkeypatch or equivalent).
- Returns `latitude=None`, `longitude=None`, `provider='null'`, `location_source='unknown'`.

### F. Template prompt (`tests/services/photo_elicit/test_template_prompt.py`)

*Case 1 — all known:*
Input: `people=["Chris","Melanie"]`, `place="Austin, Texas"`, `date="2018"`
Assert output contains: `This photo shows Chris and Melanie`, `Austin, Texas`, `2018`, `Tell me what you remember`.

*Case 2 — tier zero:*
Assert exact prefix: `I'm not sure when or where this was taken, but it looks meaningful.`

*Case 3 — forbidden phrasings:*
Across all three tiers, assert the output does NOT contain `What year`, `Who is this`, or `Confirm`.

### G. Selector (`tests/services/photo_elicit/test_selector.py`)

- Selects a `narrator_ready=True` photo.
- Skips `narrator_ready=False`.
- Prefers photos not yet shown.
- Skips photos whose last outcome is `distress_abort` if fewer than `DISTRESS_ABORT_COOLDOWN` shows have elapsed.
- Returns a `distress_abort` photo after `DISTRESS_ABORT_COOLDOWN` shows elapse.
- Skips photos whose last outcome is `zero_recall` if fewer than `ZERO_RECALL_COOLDOWN` shows have elapsed.
- Returns a `zero_recall` photo after `ZERO_RECALL_COOLDOWN` shows elapse.

### H. API vertical slice (`tests/api/test_photos_shared.py`)

1. `POST /api/photos` (multipart) with `narrator_ready=true`. Expect 201 + photo row + `uploaded_at` set.
2. `GET /api/photos?narrator_id=...` returns the photo.
3. `POST /api/photos/sessions` returns a session.
4. `POST /api/photos/sessions/{id}/show-next` returns photo + show_id + prompt_text.
5. `POST /api/photos/shows/{show_id}/memory` with `{transcript:"That was a happy night.", memory_type:"episodic_story"}` → memory row + show outcome `story_captured`.
6. Create a second photo; show it; POST memory with `{transcript:"", memory_type:"zero_recall"}` → memory row + show outcome `zero_recall`.
7. Create a third photo; show it; POST memory with `{transcript:"", memory_type:"distress_abort"}` → memory row + show outcome `distress_abort`.
8. `POST /api/photos/sessions/{id}/end` — any remaining `shown` outcomes get set to `skipped`, `ended_at` set, `finalized_at` set on memory rows.
9. Assert no `photo_session_shows` row with outcome `shown` exists after session end.

### I. Manual UI smoke test

See §17.

---

## 17. MANUAL SMOKE TEST

```bash
# Chris starts the stack himself per CLAUDE.md.
export HORNELORE_PHOTO_ENABLED=1
# (Chris runs ./scripts/start_all.sh)
```

1. Open `ui/photo-intake.html`.
2. Upload a JPEG for narrator Chris.
3. Add one person (`person_label="Melanie"`), decade `1980s`, `location_source=spoken_place`, `location_label="Lake Michigan"`.
4. Check `narrator_ready`, save.
5. Open `ui/photo-elicit.html?narrator_id=chris`.
6. Start session, show next.
7. Verify large photo + prompt appear.
8. Enter transcript; click `Capture Story`.
9. Open `ui/photo-timeline.html`.
10. Verify the photo shows in the `1980s` decade bucket with memory count = 1.
11. Start a new session; let the 120s silence fire; verify a gentle follow-up plays.
12. End the session; verify `photo-elicit` returns to a quiet exit screen.

Expected:
- No required-field blocking at save.
- Unknown `date_value` / `location_label` / `people` allowed.
- Narrator page has no curator controls anywhere.
- Timeline `Undated` bucket exists for photos without dates.
- Raw transcript stored; STT-guard fields populated if STT was used.

---

## 18. STOP / GO GATES

**STOP if:**
- `extract.py` needs to be modified to pass Phase 1.
- LLM prompt or extraction is required to pass Phase 1.
- Real geocoder requires an API key.
- Narrator UI exposes any curator metadata controls.
- Save fails when `date_value` / `location_label` / `people` are unknown.
- Provenance is missing on any `photo_people`, `photo_events`, `photo_memories`, or `photos` row.
- `distress_abort` cannot be represented.
- Any `photo_session_shows` row survives session-end with outcome `shown`.
- STT safety fields on `photo_memories` are missing or null when the frontend provided them.

**GO when:**
- Six tables exist with the exact DDL above.
- CRUD photo flow works (multipart upload, list, read, patch, soft-delete).
- Session + show + memory flow works.
- `zero_recall` and `distress_abort` paths work end-to-end.
- Selector respects both cooldown windows.
- Template prompt test passes forbidden-question checks.
- WO-10C silence ladder fires in manual smoke.
- `POST /sessions/{id}/end` leaves zero dangling `shown` rows.
- UI smoke test passes.

---

## 19. REPORT FORMAT (at close)

```
FILES ADDED:      <count + list>
FILES MODIFIED:   <count + list>
MIGRATION:        applied yes/no
TESTS RUN:        <count>
PASS/FAIL TABLE:
  - schema enum constraints            PASS/FAIL
  - provenance stamping                PASS/FAIL
  - confidence ladder                  PASS/FAIL
  - sha256 dedupe                      PASS/FAIL
  - NullGeocoder                       PASS/FAIL
  - template prompt                    PASS/FAIL
  - selector (incl. both cooldowns)    PASS/FAIL
  - API vertical slice                 PASS/FAIL
  - end-session + dangling-shown       PASS/FAIL
  - UI smoke test                      PASS/FAIL
DEVIATIONS:       <repo path / convention deltas>
ASSUMPTIONS:      <anything chosen when spec was silent>
DEFERRED:         <list anything punted>
```

---

## 20. DEFERRED TO PHASE 2

Do not implement in this WO:

- EXIF GPS extraction + DMS-to-decimal conversion
- Real geocoder + reverse geocoder
- `photo_fact_conflicts` table
- Conflict detector (`services/photo_elicit/conflict_detector.py`)
- Curator conflict review queue UI
- `extraction_profile="photo_memory"` branch on `extract.py`
- `extracted_json`, `extraction_run_id`, `extraction_method`, `extraction_pipeline` columns on `photo_memories`
- Photo-memory eval cases
- LLM-generated prompts
- `HORNELORE_PHOTO_INTAKE` / `HORNELORE_PHOTO_ELICIT` split flags

These belong to `WO-LORI-PHOTO-INTAKE-01_Spec.md` (Phase 2) and `WO-LORI-PHOTO-ELICIT-01_Spec.md` (Phase 2).

---

## 21. OPEN QUESTIONS (tracked, not blocking Phase 1)

1. **Narrator-id routing** — Phase 1 uses `?narrator_id=<id>` query param. Phase 2 should move to a signed session token or SSO.
2. **`photos.metadata_json` retention** — keep (EXIF blob + orientation) or retire? Decision deferred until Phase 2 EXIF work lands.
3. **`photo_sessions.session_id` semantics** — link to the interview-engine session, or its own concept?
4. **Selector abstraction for Phase 2** — introduce `PhotoSelectorContext` or keep passing `repository` directly?
5. **Geocoder provider choice** (Phase 2) — OSM Nominatim, Google, or self-hosted?
6. **Cellupload / mobile upload port number** — Phase 1 smoke uses desktop browser only.
7. **Distress-response copy** — what does the wind-down screen say? Curator-editable.
8. **Auto-adopt on narrator conflict** (Phase 2 only) — policy default.
9. **TTS tone parameters for Coqui VITS p335** — Phase 1 uses existing config; Phase 2 may tune.

---

## 22. CHANGELOG

- **2026-04-23** — Authored. Absorbs the nine locked fixes from the SHARED-01 pushback disposition: STT-safety columns on `photo_memories`, provenance columns on `photos`, hard cooldowns in selector, WO-10C compliance on narrator UI, `POST /sessions/{id}/end` endpoint, multipart upload locked, unified naming (`person_label` / `date_precision` / `location_label`), mandatory-outcome rule for `photo_session_shows`, narrator-id query param. Supersedes Phase 1 content in `WO-LORI-PHOTO-INTAKE-01_Spec.md` and `WO-LORI-PHOTO-ELICIT-01_Spec.md`; those specs are now Phase 2 only.

---

END WO
