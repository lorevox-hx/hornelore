# WO-MEMOIR-STORY-CANDIDATES-WIRE-01

**Status:** LANDED 2026-07-06.
**Lane:** Memoir / story preservation (closes the forgotten-item flagged in WORK-AUDIT-2026-07-05 and the 2026-05-09 Kokoro-session discovery; unblocks trips Phase D memoir injection).
**Parent:** `WO-LORI-STORY-CAPTURE-01` (the golfball lane that writes story_candidates).

## The gap this closes

The story-preservation lane has been writing `story_candidates` rows since 2026-04-30 — Janice's mastoidectomy story was the first — and the schema shipped with a `review_status` value **`memoir_only`** designed for export. But the memoir DOCX export (`POST /api/memoir/export-docx`) only ever rendered the FE-built `sections` payload (projection/threads/prose). Captured stories sat in the DB, invisible to the family-facing artifact. The narrator's own words — the whole point of Path 1 preservation — never reached the memoir.

## What landed

1. **`db.story_candidate_list_for_memoir(narrator_id)`** — rows with `review_status IN ('promoted','memoir_only')`, oldest-first. The export gate is explicit: `unreviewed`, `in_review`, and `discarded` NEVER reach a family-facing artifact (principle 5: final truth waits for the operator).
2. **`memoir_export._captured_story_sections(person_id)`** — harvests those rows into `MemoirSection`s grouped by the first `era_candidates` entry, ordered by the canonical 7-era spine, labeled *"In their own words — {era warm label}"*; era-less stories land in a trailing *"More stories"* group. **Transcripts are VERBATIM** — no summarization, no rewriting, ever. Never raises (memoir export must not fail because a story row is unreadable).
3. **Request wire** — `MemoirExportRequest` gains `person_id: Optional[str] = None` + `include_captured_stories: bool = True`. Harvested sections are appended after the FE sections before dispatch, so they flow through every existing render path unchanged: threads/draft, en/es/bilingual translation, photo inlining. **Absent `person_id` = byte-stable with every pre-wire caller.**
4. **FE** — `memoirExportDOCX()` passes `state.person_id`, so every export from the app now carries the narrator's cleared stories automatically.

## Review workflow (unchanged, now meaningful at export)

Operator reviews captured stories in the Bug Panel story review surface → sets `promoted` (full truth promotion) or `memoir_only` (tells the story in the memoir without promoting extracted fields) → next memoir export includes them, in the narrator's words, in the right era chapter.

## Deferred (named)

- **Trips Phase D tie-in:** `trip_story_links` grouping (stories under their trip's memoir section rather than only era grouping) — build when the standalone trip memoir and main memoir merge lands.
- Per-story operator captions/titles in the export.
- Spanish story transcripts already flow through the existing translation dispatch when target_language != en — dedicated per-story language handling (story rows carry their own language columns per migration 0006) is future work.

## Tests (`tests/test_memoir_story_wire.py`, 9)

promoted+memoir_only export · unreviewed/in_review/discarded never export · era grouping in spine order · unplaced trailing group · verbatim transcripts (quotes/dialect preserved) · unknown narrator empty · harvest never raises on broken DB · request-model defaults byte-stable · FE passes person_id.

## Revision history

- 2026-07-06 — Authored + landed (offline; stack was down awaiting restart for the Travels narration live test).
