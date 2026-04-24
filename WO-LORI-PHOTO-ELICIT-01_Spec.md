# WO-LORI-PHOTO-ELICIT-01 — Narrator Elicitation Intelligence (Phase 2)

**Status:** BLOCKED on WO-LORI-PHOTO-SHARED-01 (Phase 1 foundation) landing green.
**Mode:** Narrator-facing intelligence layer.
**Scope:** Phase 2 only — everything below assumes the SHARED-01 schema, services, selector, three UI pages, and WO-10C integration are already in place.

---

## 0. UX AUTHORITY LOCK

The source of truth for the user experience is `ui/mockups/lori_photo_mockup.html`. The Lori session screens in that mockup define the narrator UX. This spec covers the intelligence layer behind that UX; it does not restate UX decisions already captured in the mockup or in SHARED-01 §14.

---

## 1. SPEC HIERARCHY

```
WO-LORI-PHOTO-SHARED-01 = Phase 1 authority layer
WO-LORI-PHOTO-INTAKE-01 = Phase 2 curator intelligence
WO-LORI-PHOTO-ELICIT-01 = Phase 2 narrator intelligence (this spec)
```

All Phase 1 concerns — schema, template-only prompts, selector cooldowns, WO-10C silence ladder, STT-guard integration, session end, raw-transcript memory rows — are owned by SHARED-01 and are not restated here. If this spec and SHARED-01 appear to contradict, SHARED-01 wins for Phase 1 concerns and this spec wins for Phase 2 concerns.

---

## 2. GOAL

Lift the narrator elicitation flow from "raw transcript capture" (Phase 1) to "narrator intelligence":

- LLM extraction on photo-memory transcripts using a dedicated `extraction_profile="photo_memory"`.
- Structured `extracted_json` stored on each `photo_memories` row.
- Narrator-side signal for the curator conflict-review queue (consumed by INTAKE Phase 2).
- LLM-generated prompt variants (replacing template-only prompts) when narrator context allows.

---

## 3. HARD RULES

**DO NOT:**
- Modify `extract.py` at the Lane 1 (question-bank) code path. A new, isolated `photo_memory` profile branches off the `extraction_profile` dispatch without touching the existing question-bank pipeline.
- Move the r5h baseline score by ±1 case. Byte-stability on the question-bank eval is a gate.
- Add any narrator-facing correction UI. WO-10C "no correction" rule is preserved throughout.
- Block narrator-session commit on extraction completion. Extraction runs **asynchronously** after the show is closed.

**Phase 2 principles:**
- Extraction is best-effort and deferred; a narrator's session never waits on it.
- `extracted_json` is a read surface for curator review, not an authoritative fact store. Authoritative fact updates happen only via the INTAKE Phase 2 conflict-resolution path.
- LLM-generated prompts must still pass the SHARED-01 template-prompt forbidden-question test (`What year`, `Who is this`, `Confirm`) — this is enforced as a post-generation filter.

---

## 4. FILE TARGETS

### NEW

```
server/code/services/photo_elicit/extraction.py         (photo_memory profile wrapper; no extract.py touch)
server/code/services/photo_elicit/memory_prompt.py      (LLM-generated prompt variants)
server/code/services/photo_elicit/scheduler.py          (async extraction dispatch)

server/code/db/migrations/NNNN_lori_photo_memory_extraction.sql

tests/services/photo_elicit/test_extraction_profile.py
tests/services/photo_elicit/test_memory_prompt_filter.py
tests/services/photo_elicit/test_scheduler.py
tests/api/test_photos_memory_extraction.py
```

### MODIFIED

```
server/code/api/routers/photos.py               (extraction endpoints, async dispatch on memory write)
server/code/services/photos/repository.py       (extraction-column read/write)
server/code/services/photo_elicit/selector.py   (no behavior change; re-read with extracted context for future richer scoring)
server/code/flags/__init__.py                   (HORNELORE_PHOTO_ELICIT)
ui/photo-intake.html                            (read-only curator view of extracted_json alongside the conflict item)
ui/js/photo-intake.js                           (render extracted summary next to conflict rows)
.env.example
CLAUDE.md
```

**Explicit non-modification:** `server/code/api/routers/extract.py` is NOT on this list. The photo-memory extraction wrapper calls into shared LLM infrastructure but does not branch inside the existing question-bank dispatch.

---

## 5. FEATURE FLAG

```
HORNELORE_PHOTO_ELICIT=0
```

- Flag OFF: Phase 1 behavior preserved. Memory write does not trigger extraction. `extracted_json` remains NULL. LLM prompt variants are not used; template prompts only.
- Flag ON: Memory write enqueues an async extraction job. Completed extraction writes back to `photo_memories.extracted_json` + `extraction_run_id` + `extraction_method` + `extraction_pipeline`. LLM prompt variants are allowed (still filtered through forbidden-question guard).

`HORNELORE_PHOTO_ENABLED=1` is a prerequisite. The two flags compose (`PHOTO_ENABLED && PHOTO_ELICIT` gates Phase 2 elicit features).

INTAKE Phase 2 (`HORNELORE_PHOTO_INTAKE=1`) is a hard prerequisite for the conflict detector to fire — but memory extraction itself does not require INTAKE Phase 2 to be on.

---

## 6. SCHEMA ADDITIONS

File: `server/code/db/migrations/NNNN_lori_photo_memory_extraction.sql`

```sql
BEGIN;

ALTER TABLE photo_memories ADD COLUMN extracted_json TEXT;
ALTER TABLE photo_memories ADD COLUMN extraction_run_id TEXT;
ALTER TABLE photo_memories ADD COLUMN extraction_method TEXT;
ALTER TABLE photo_memories ADD COLUMN extraction_pipeline TEXT;
ALTER TABLE photo_memories ADD COLUMN extraction_status TEXT NOT NULL DEFAULT 'none'
    CHECK (extraction_status IN ('none', 'pending', 'running', 'completed', 'failed'));
ALTER TABLE photo_memories ADD COLUMN extraction_started_at TEXT;
ALTER TABLE photo_memories ADD COLUMN extraction_completed_at TEXT;
ALTER TABLE photo_memories ADD COLUMN extraction_error TEXT;

CREATE INDEX IF NOT EXISTS idx_photo_memories_extraction_status
    ON photo_memories(extraction_status, created_at);

COMMIT;
```

- `extracted_json` is a JSON blob with a schema documented in §7.
- `extraction_status` lets the UI show "extraction in progress" without blocking the narrator flow.
- `extraction_error` captures the last failure reason; retries overwrite it.

---

## 7. PHOTO_MEMORY EXTRACTION PROFILE

File: `server/code/services/photo_elicit/extraction.py`

```python
def run_photo_memory_extraction(
    memory: PhotoMemory,
    photo: Photo,
    people_hints: list[str],   # curator-provided people labels; teach-the-test rule: never injected into narrator prompt
) -> dict
```

The function wraps the shared LLM client with a dedicated prompt template that is **separate** from the question-bank prompt path. It does not reuse `_NARRATIVE_FIELD_FEWSHOTS` or any other question-bank artifact.

**Output schema (`extracted_json`):**

```json
{
  "schema_version": 1,
  "extracted_at": "<ISO8601>",
  "model": "<model-id>",
  "memory_claims": {
    "date_value": null | "1975" | "1975-06-10",
    "date_precision": "exact" | "month" | "year" | "decade" | "unknown",
    "location_label": null | "Lake Michigan",
    "people_mentioned": [
      {"person_label": "Melanie", "salience": "high"},
      {"person_label": "Aunt Rose", "salience": "medium"}
    ],
    "events_mentioned": [
      {"event_label": "summer camp", "salience": "medium"}
    ],
    "affect": "warm" | "sad" | "proud" | "neutral" | "mixed" | null,
    "novelty": "known_to_curator" | "new_to_curator" | "unknown",
    "confidence_overall": "high" | "medium" | "low"
  },
  "free_text_summary": "<2-sentence narrator-voice summary>",
  "raw_transcript_ref": "<photo_memory_id>"
}
```

**Hard rules:**
- Extraction never writes to `photos` / `photo_people` / `photo_events`. Those rows are only mutated by the INTAKE Phase 2 conflict-resolution path.
- `people_hints` go into the system prompt as "candidate names the narrator may mention"; they are never read back to the narrator and never forced into the output. The LLM is instructed to emit a person only if the narrator actually mentions them.
- `confidence_overall` is the model's self-report and is treated as soft. Curator conflict review is still the source of truth.

---

## 8. ASYNC SCHEDULER

File: `server/code/services/photo_elicit/scheduler.py`

```python
def enqueue_extraction(photo_memory_id: str) -> None
def process_pending_extractions(batch_size: int = 4) -> int
```

- Phase 2 implementation: simple in-process task queue (thread pool or asyncio) with a cron-style drain. No external queue dependency.
- On memory write (both `story_captured` and `emotional_flash` / `general_mood` kinds — not `zero_recall` or `distress_abort`), the API enqueues an extraction job and sets `extraction_status='pending'`.
- Jobs are idempotent keyed on `photo_memory_id`. Re-running is safe.
- On completion: write `extracted_json`, set `extraction_status='completed'`, `extraction_completed_at=now`, populate `extraction_run_id` (unique per job run).
- On failure (LLM error, JSON parse error, schema validation fail): set `extraction_status='failed'`, `extraction_error=<reason>`. Retry policy: manual endpoint (§9) for Phase 2; automatic exponential-backoff retry is Phase 3.

No scheduled extraction fires for `zero_recall` or `distress_abort` memories. There is nothing to extract and running the LLM on empty transcripts wastes GPU time.

---

## 9. API ENDPOINTS (added)

### `POST /api/photos/shows/{show_id}/memory` (modified)

On memory write, if `HORNELORE_PHOTO_ELICIT=1` AND `memory_type` ∈ `{episodic_story, emotional_flash, general_mood}`:
- Enqueue extraction via `scheduler.enqueue_extraction(memory.id)`.
- Set `extraction_status='pending'` in the same transaction.

Endpoint return payload extended with `extraction_status`.

### `GET /api/photos/memories/{memory_id}/extraction`

Returns current extraction state:
```
{
  "memory_id": "...",
  "status": "none" | "pending" | "running" | "completed" | "failed",
  "extracted_json": {...} | null,
  "error": "..." | null,
  "started_at": "...",
  "completed_at": "..."
}
```

### `POST /api/photos/memories/{memory_id}/extraction/retry`

Forces a retry. Allowed when `status ∈ {failed, completed}`. Disallowed when `status ∈ {pending, running}`.

### `GET /api/photos/{photo_id}` (extended)

Includes a list of memories with their `extracted_json` (when `HORNELORE_PHOTO_ELICIT=1` AND requester is curator-scoped).

**Note for the narrator page:** `ui/photo-elicit.html` continues to **not** display `extracted_json` anywhere. Extraction output is a curator-only read surface. "No correction" rule is preserved.

---

## 10. LLM-GENERATED PROMPT VARIANTS

File: `server/code/services/photo_elicit/memory_prompt.py`

```python
def build_memory_prompt_llm(photo: Photo, prior_memories: list[PhotoMemory]) -> str | None
```

- Called **only** when `HORNELORE_PHOTO_ELICIT=1` and the photo has at least one prior completed extraction (rich context).
- Otherwise falls back to `template_prompt.build_photo_prompt` (SHARED-01).
- Output is filtered through the forbidden-question guard (`What year`, `Who is this`, `Confirm`). If the LLM output fails the filter, fall back to template.
- Output is also length-capped at 240 characters (single conversational beat; WO-10C pacing).
- Teach-the-test rule: people-label IDs never enter the LLM input; only labels, and only when the prior extraction already surfaced them.

---

## 11. ACCEPTANCE TESTS

### A. Extraction profile (`tests/services/photo_elicit/test_extraction_profile.py`)

- Given a realistic narrator transcript (`"That was the summer Melanie and I went to Lake Michigan. I was about six or seven. My grandmother made sandwiches."`), `run_photo_memory_extraction` returns a valid `extracted_json` matching the schema.
- People mentioned contains `Melanie` and `grandmother` (or `Grandma`); `location_label` contains `Lake Michigan`; `date_precision` ∈ `{year, decade}`.
- Free-text summary is ≤ 2 sentences.
- Extraction on a `zero_recall` or `distress_abort` memory does not run; `extraction_status` stays `none`.

### B. Forbidden-question filter (`tests/services/photo_elicit/test_memory_prompt_filter.py`)

- LLM output containing `What year was this?` falls back to template.
- LLM output containing `Who is this?` falls back to template.
- LLM output containing `Can you confirm...` falls back to template.
- Clean LLM output (≤ 240 chars, no forbidden phrasings) is returned as-is.

### C. Scheduler (`tests/services/photo_elicit/test_scheduler.py`)

- Enqueue + drain completes a single job end-to-end.
- Failed job sets `extraction_status='failed'` and records `extraction_error`.
- Retry endpoint re-runs a failed job.
- Idempotency: re-enqueueing while `pending` is a no-op; re-enqueueing while `completed` is also a no-op unless retry is called.

### D. API (`tests/api/test_photos_memory_extraction.py`)

- Memory write with `HORNELORE_PHOTO_ELICIT=1` returns `extraction_status='pending'`.
- `GET /api/photos/memories/{memory_id}/extraction` returns `pending` then (after drain) `completed`.
- `GET /api/photos/{photo_id}` (curator-scoped) returns extracted summary in the memory list.
- Narrator-scoped read path (SHARED-01 Phase 1) does NOT expose `extracted_json`.

### E. Byte-stability

- With `HORNELORE_PHOTO_ELICIT=0`, memory write is byte-identical to SHARED-01 Phase 1; `extracted_json` stays NULL.
- Master question-bank eval at latest tag unchanged (±0 cases). Required gate.

### F. Integration with INTAKE Phase 2

- When both `HORNELORE_PHOTO_INTAKE=1` and `HORNELORE_PHOTO_ELICIT=1`, completed extraction triggers `conflict_detector.detect_conflicts_for_memory(photo, memory, extracted_json)`.
- Conflict rows appear in the curator review queue with `photo_memory_id` pointing to the correct memory.

---

## 12. STOP / GO GATES

**STOP if:**
- `extract.py` must be modified to pass this WO.
- Master question-bank eval score changes by ±1 case.
- Narrator page surfaces `extracted_json` in any form.
- Async extraction ever blocks the narrator session commit.
- LLM prompt variant fails the forbidden-question filter and is returned to narrator anyway.
- Extraction runs on `zero_recall` or `distress_abort` memories.

**GO when:**
- Extraction profile + scheduler + LLM prompt variants all land behind `HORNELORE_PHOTO_ELICIT=1`.
- Default-off behavior is byte-identical to Phase 1.
- All Phase 2 tests green.
- Manual smoke: narrator captures a memory, session closes, extraction completes within N seconds (Phase 2 target: < 10s per memory on warm model), curator sees `extracted_json` on the photo detail view in the review queue.
- Question-bank master eval unchanged vs. last banked tag.

---

## 13. REPORT FORMAT

Same as SHARED-01 §19, plus:

- Extraction profile pass/fail on 5 seed transcripts.
- Forbidden-question filter pass/fail.
- Scheduler retry + idempotency pass/fail.
- Byte-stability confirmation against latest master eval tag.
- Average extraction latency on warm model.

---

## 14. DEFERRED TO PHASE 3

- Fine-tuned photo-memory extractor (Phase 2 uses shared LLM).
- Automatic exponential-backoff retry on extraction failure.
- Narrator-affect → session-pacing feedback loop (SHARED-01 handles pacing via WO-10C silence timers; Phase 3 may tune based on `affect` signal in extracted JSON).
- Multi-turn memory threading (a single `photo_memories` row carrying multiple narrator turns).

---

## 15. OPEN QUESTIONS

1. **Photo-memory schema versioning** — `schema_version: 1` in output; when do we bump? Policy: bump on any breaking field add/remove.
2. **Extraction budget** — how many GPU-seconds per memory before we cut and fall back to a stub summary? Phase 2 default: 15s per memory.
3. **LLM prompt variant frequency** — always use LLM when available, or A/B against template? Phase 2 default: always use LLM when context-rich; template fallback on filter-fail or low context.
4. **Curator-side diff rendering** — when `extracted_json` disagrees with curator facts, which diff format is most legible? (INTAKE Phase 2 decision; mentioned here for coordination.)

---

## 16. CHANGELOG

- **2026-04-23** — Rewritten to Phase 2 scope only. Phase 1 content moved into `WO-LORI-PHOTO-SHARED-01_Spec.md`. This spec now covers the `photo_memory` extraction profile, async scheduler, LLM prompt variants, and the curator-facing read surface for `extracted_json` — the narrator intelligence layer that sits above the SHARED-01 foundation.

---

END WO
