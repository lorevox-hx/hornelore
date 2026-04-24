# WO-LORI-PHOTO-INTAKE-01 — Curator Intake Intelligence (Phase 2)

**Status:** BLOCKED on WO-LORI-PHOTO-SHARED-01 (Phase 1 foundation) landing green.
**Mode:** Curator-facing intelligence layer.
**Scope:** Phase 2 only — everything below assumes the SHARED-01 schema, services, and UI pages are already in place.

---

## 0. UX AUTHORITY LOCK

The source of truth for the user experience is `ui/mockups/lori_photo_mockup.html`. The curator-intake tab / screens in that mockup define the curator UX. This spec covers the intelligence layer behind that UX; it does not restate UX decisions already captured in the mockup.

---

## 1. SPEC HIERARCHY

```
WO-LORI-PHOTO-SHARED-01 = Phase 1 authority layer
WO-LORI-PHOTO-INTAKE-01 = Phase 2 curator intelligence (this spec)
WO-LORI-PHOTO-ELICIT-01 = Phase 2 narrator intelligence
```

All Phase 1 concerns — schema, provenance, confidence, `NullGeocoder`, multipart upload, three UI pages, selector cooldowns, WO-10C wiring, session end — are owned by SHARED-01 and are not restated here. If this spec and SHARED-01 appear to contradict, SHARED-01 wins for Phase 1 concerns and this spec wins for Phase 2 concerns.

---

## 2. GOAL

Lift the curator intake flow from "schema CRUD" (Phase 1) to "curator intelligence":

- EXIF GPS extraction on upload.
- Real geocoder + reverse geocoder.
- Curator-facing conflict review queue (narrator-provided facts vs. curator-provided facts).
- Curator-resolvable `photo_fact_conflicts` with four resolution modes.

---

## 3. HARD RULES

**DO NOT:**
- Touch `server/code/api/routers/extract.py` (extractor baseline stays untouched; conflict-detection signal comes from outside the extractor).
- Break byte-stability of any existing eval case.
- Require curator to resolve a conflict synchronously at narrator-session time.

**Phase 2 principles:**
- EXIF GPS, when present, is high-confidence and auto-stamps `location_source='exif_gps'` + `needs_confirmation=false`.
- Real geocoder is a pluggable provider; offline mode must degrade gracefully to `NullGeocoder`.
- Conflicts are surfaced as curator review items, not narrator-visible corrections. The "no correction" rule from WO-10C is preserved.

---

## 4. FILE TARGETS

### NEW

```
server/code/services/photo_intake/exif.py
server/code/services/photo_intake/geocode_real.py
server/code/services/photo_intake/conflict_detector.py
server/code/services/photo_intake/review_queue.py

server/code/db/migrations/NNNN_lori_photo_conflicts.sql

tests/services/photo_intake/test_exif.py
tests/services/photo_intake/test_geocode_real.py
tests/services/photo_intake/test_conflict_detector.py
tests/api/test_photos_conflicts.py
```

### MODIFIED

```
server/code/services/photo_intake/geocode.py      (register real provider alongside NullGeocoder)
server/code/services/photos/repository.py         (conflict CRUD methods)
server/code/api/routers/photos.py                 (conflict endpoints, EXIF on upload)
server/code/flags/__init__.py                     (HORNELORE_PHOTO_INTAKE)
ui/photo-intake.html                              (review-queue section)
ui/js/photo-intake.js                             (review-queue UI + conflict resolution)
ui/css/photo-intake.css                           (review-queue styling)
.env.example
CLAUDE.md
```

---

## 5. FEATURE FLAG

```
HORNELORE_PHOTO_INTAKE=0
```

- Flag OFF: Phase 1 behavior preserved. Upload endpoint ignores EXIF. Conflict endpoints return 404. Real geocoder is not instantiated.
- Flag ON: EXIF extraction runs on upload, real geocoder active, conflict detector runs on memory commit, review queue endpoints live.

`HORNELORE_PHOTO_ENABLED=1` is a prerequisite. The two flags compose (`PHOTO_ENABLED && PHOTO_INTAKE` gates Phase 2 intake features).

---

## 6. SCHEMA ADDITIONS

File: `server/code/db/migrations/NNNN_lori_photo_conflicts.sql`

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS photo_fact_conflicts (
    id TEXT PRIMARY KEY,
    photo_id TEXT NOT NULL,
    photo_memory_id TEXT,              -- source memory (narrator side); nullable for external triggers

    field_path TEXT NOT NULL,          -- e.g. 'date_value', 'location_label', 'people[0].person_label'
    curator_value TEXT,                -- canonicalized curator-side value
    narrator_value TEXT,               -- canonicalized narrator-side value (as extracted)

    confidence_curator TEXT,
    confidence_narrator TEXT,

    resolution TEXT NOT NULL DEFAULT 'pending'
        CHECK (resolution IN ('pending', 'keep_curator', 'adopt_narrator', 'both_true', 'ambiguous')),

    resolved_by_user_id TEXT,
    resolved_at TEXT,
    resolution_note TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
    FOREIGN KEY(photo_memory_id) REFERENCES photo_memories(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_photo_fact_conflicts_photo_id
    ON photo_fact_conflicts(photo_id);

CREATE INDEX IF NOT EXISTS idx_photo_fact_conflicts_pending
    ON photo_fact_conflicts(resolution, created_at);

COMMIT;
```

Resolution modes:

| Mode              | Meaning                                                                         |
|-------------------|---------------------------------------------------------------------------------|
| `pending`         | Default on insert; awaiting curator action.                                     |
| `keep_curator`    | Curator value stands; narrator value archived.                                  |
| `adopt_narrator`  | Narrator value replaces curator value; curator value archived in metadata.      |
| `both_true`       | Both values are independently correct (e.g., two trips to the same place).      |
| `ambiguous`       | Cannot reconcile; hold both, mark photo for clarification with family member.   |

---

## 7. EXIF EXTRACTION

File: `server/code/services/photo_intake/exif.py`

```python
def extract_exif(source_path: str) -> dict
```

Returns:

```
{
  "captured_at": ISO8601 | None,
  "captured_at_precision": 'exact' | 'month' | 'year' | 'unknown',
  "gps": {
    "latitude": float | None,
    "longitude": float | None,
    "source": 'exif_gps' | 'unknown'
  },
  "orientation": int | None,
  "raw_exif": dict   # full tag map for metadata_json
}
```

- DMS-to-decimal conversion lives here.
- Fail-soft: corrupt EXIF returns `{"captured_at": None, "gps": {...None...}, "raw_exif": {}}`; does not 500 the upload.
- EXIF blob goes into `photos.metadata_json` under key `"exif"` (metadata_json remains non-authoritative; it is not used for provenance).
- On upload, if EXIF GPS present:
  - `photos.latitude` = lat, `photos.longitude` = lng
  - `photos.location_source` = `'exif_gps'`
  - `photos.needs_confirmation` = `False`
  - `location_label` is populated by reverse-geocoding (§8) if available; otherwise left NULL.

Test: known-good EXIF fixture (with GPS) returns correct lat/lng; corrupt fixture returns None-everything; DMS conversion is correct to ±1e-5 degrees.

---

## 8. REAL GEOCODER

File: `server/code/services/photo_intake/geocode_real.py`

Interface matches `NullGeocoder.geocode(text)`:

```python
class RealGeocoder:
    def __init__(self, provider: str, api_key: str | None = None): ...
    def geocode(self, text: str) -> dict:
        """Forward geocode: text -> lat/lng."""
        ...
    def reverse(self, lat: float, lng: float) -> dict:
        """Reverse geocode: lat/lng -> location_label."""
        ...
```

Provider choice is deferred (see Open Questions) — likely OSM Nominatim for no-API-key start, with Google as an opt-in upgrade.

Offline / failure behavior:
- Any network error, rate-limit, or empty result returns `{"latitude": None, "longitude": None, "provider": <name>, "location_source": "unknown"}`.
- Never raise to the caller. Upload path must continue even if geocoder is down.

Test: simulate provider with `responses` / `httpx_mock`; verify forward + reverse round-trip for one known location; verify graceful failure on 500 / timeout / empty.

---

## 9. CONFLICT DETECTOR

File: `server/code/services/photo_intake/conflict_detector.py`

```python
def detect_conflicts_for_memory(
    photo: Photo,
    memory: PhotoMemory,
    extracted_json: dict,         # produced by ELICIT Phase 2 extract
) -> list[PhotoFactConflict]
```

Compares `extracted_json` (narrator-derived facts) against curator-side facts on the photo + `photo_people` + `photo_events`. Emits a `photo_fact_conflicts` row for each disagreement.

**Fields compared in Phase 2:**
- `date_value` / `date_precision` (narrator-derived year/decade vs. curator-stamped)
- `location_label` (fuzzy match < 0.5)
- `people[].person_label` (narrator mentions someone not in curator people-list, or contradicts)

**Fuzzy threshold:** reuse existing scorer fuzzy-match with ≥0.5 gate for `location_label`. Names: exact-match on normalized form (case-fold + trim) for now; fuzzy name matching is a Phase 3 concern.

Conflicts are emitted with `resolution='pending'` and reviewed by curator via the review queue.

**Hard rule:** conflict detection runs on write of a `photo_memories` row with `extracted_json != NULL`. It never mutates existing `photos` / `photo_people` / `photo_events` rows. Resolution is the only path that can mutate authoritative data.

---

## 10. REVIEW QUEUE

File: `server/code/services/photo_intake/review_queue.py`

```python
def list_pending_conflicts(narrator_id: str, limit: int = 50) -> list[dict]
def get_conflict(conflict_id: str) -> dict
def resolve_conflict(
    conflict_id: str,
    resolution: str,                  # 'keep_curator' | 'adopt_narrator' | 'both_true' | 'ambiguous'
    resolved_by_user_id: str,
    resolution_note: str | None = None,
) -> dict
```

**Resolution side effects:**
- `keep_curator`: stamp resolution; no change to authoritative fields.
- `adopt_narrator`: update authoritative field on `photos` (or insert `photo_people` / `photo_events` row) using the narrator value, with curator-originated provenance preserved in a history audit row (`last_edited_by_user_id` / `last_edited_at` updated).
- `both_true`: no authoritative change; both values survive as separate records where schema supports it (multi-row tables).
- `ambiguous`: no authoritative change; conflict archived but flagged for future family-member review.

---

## 11. API ENDPOINTS (added)

### `POST /api/photos` (modified)

On upload, if `HORNELORE_PHOTO_INTAKE=1`, call `exif.extract_exif` and stamp:
- `date_value` + `date_precision` (from EXIF `captured_at`) **only if** the upload payload did not supply these fields.
- `latitude` / `longitude` / `location_source='exif_gps'` / `needs_confirmation=false` if EXIF GPS is present.
- `location_label` from reverse geocode if EXIF GPS present and geocoder returns a result.
- Raw EXIF into `photos.metadata_json.exif`.

Curator-supplied fields always win over EXIF. EXIF never overwrites narrator facts (narrator path is separate).

### `GET /api/photos/conflicts?narrator_id=...[&resolution=pending]`

Lists conflicts.

### `GET /api/photos/conflicts/{conflict_id}`

Returns a conflict with full detail: photo snapshot, both values, confidence, and (Phase 2.1) the memory transcript excerpt the narrator value came from.

### `POST /api/photos/conflicts/{conflict_id}/resolve`

Payload:

```
{
  "resolution": "keep_curator" | "adopt_narrator" | "both_true" | "ambiguous",
  "resolved_by_user_id": "...",
  "resolution_note": "..."
}
```

Returns updated conflict + any authoritative-field deltas.

---

## 12. UI — REVIEW QUEUE

Added to `ui/photo-intake.html`:

- New section `Review Queue` on the curator page.
- List of pending conflicts, grouped by photo.
- Per-conflict row: photo thumbnail, `field_path`, curator value, narrator value, four resolution buttons (`Keep mine` / `Adopt narrator` / `Both true` / `Ambiguous`), optional note field.
- Resolved conflicts collapse into an "Archive" subsection (toggle).

This stays inside `ui/photo-intake.html` — it does not get its own page. Review UX is a curator-only concern.

---

## 13. ACCEPTANCE TESTS

### A. EXIF

- Known-good JPEG with GPS EXIF → correct `latitude`, `longitude`, `captured_at`.
- DMS-to-decimal conversion accurate to ±1e-5.
- Corrupt EXIF → None-everything, no exception.
- Upload honors curator-supplied `date_value` over EXIF.

### B. Real geocoder

- Forward geocode for a known location → returns lat/lng.
- Reverse geocode for a known lat/lng → returns a label.
- Provider 500 → returns `latitude=None, longitude=None, location_source='unknown'`; upload path continues.

### C. Conflict detector

- Narrator says `1975`, curator said `decade=1970s` → no conflict (narrator refines, not contradicts).
- Narrator says `1975`, curator said `1980` → conflict on `date_value`.
- Narrator says `Lake Michigan`, curator said `Lake Superior` → conflict (fuzzy < 0.5).
- Narrator mentions `Aunt Rose` not in curator people-list → conflict on `people`.
- Conflicts emitted with `resolution='pending'`.

### D. Review queue

- Each of the four resolutions mutates state correctly.
- `adopt_narrator` on `date_value` writes new value to `photos.date_value` AND stamps `last_edited_by_user_id`.
- `keep_curator` leaves authoritative fields untouched.

### E. Byte-stability

- With `HORNELORE_PHOTO_INTAKE=0`, upload behavior is byte-identical to Phase 1 (no EXIF, no geocode, no conflict rows).
- Existing eval harness results are unchanged (this WO must not move the master eval score in either direction).

---

## 14. STOP / GO GATES

**STOP if:**
- `extract.py` must be modified to pass this WO.
- Master eval score changes by ±1 case.
- Real geocoder requires a paid API key that has not been provisioned.
- Conflict detector mutates authoritative fields outside the resolution path.
- EXIF with a corrupt tag causes an upload to 500.
- "No correction" rule is violated (any narrator-facing correction UI).

**GO when:**
- EXIF extraction + real geocoder + conflict detector + review queue all land behind `HORNELORE_PHOTO_INTAKE=1`.
- Default-off behavior is byte-identical to Phase 1.
- All Phase 2 tests green.
- Manual smoke: curator uploads a GPS-tagged photo, sees auto-stamped location; narrator captures a conflicting memory; curator sees conflict in review queue; each of the four resolutions works end-to-end.

---

## 15. REPORT FORMAT

Same as SHARED-01 §19, plus:

- EXIF pass/fail table (GPS, DMS, corrupt, precedence).
- Geocoder provider + quota used.
- Conflict detector pass/fail per field.
- Byte-stability confirmation against last master eval tag.

---

## 16. DEFERRED TO PHASE 3

- Fuzzy name matching in conflict detector.
- Family-member clarification loop for `ambiguous` conflicts.
- Automatic reverse-geocode enrichment of Phase 1 `typed_address` / `spoken_place` photos (retrospective backfill).
- `photo_fact_conflicts` retention policy.

---

## 17. OPEN QUESTIONS

1. Real geocoder provider — OSM Nominatim vs. Google vs. self-hosted.
2. Conflict detection signal on `location_label` — is 0.5 fuzzy the right threshold, or should it be stricter for location than for names?
3. Should `both_true` produce two `photos` rows (one per reality) or one photo with a structured "multiple truths" field? Current default: one photo, `both_true` recorded on conflict, no duplication.

---

## 18. CHANGELOG

- **2026-04-23** — Rewritten to Phase 2 scope only. Phase 1 content moved into `WO-LORI-PHOTO-SHARED-01_Spec.md`. This spec now covers EXIF, real geocoder, conflict detector, review queue — the curator intelligence layer that sits above the SHARED-01 foundation.

---

END WO
