# WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01

**Status:** Phase 5 LANDED 2026-07-09 (first phase per the low-risk-first build order). Phases 1-4, 6-9 open; Phase 10 mostly pre-existing (trip_story_capture); Phase 11 grows with each phase.
**Lane:** Trips / Lori grounding.
**Parents:** `WO-TRIP-INTERVIEW-CONTEXT-01` (read side), `trip_story_capture` (write side), `photo_intake/metadata_trust` (Ph1 foundation).

## Goal

Lori asks intelligent, grounded trip-photo questions using APPROVED photo/file context — metadata, geo, date/event, OCR, caption, cultural enrichment — without inventing facts or claiming she sees the image.

Photo → metadata/OCR/geo/date enrichment → **operator approval + provenance** → Lori context → better questions → narrator answer → Travel Doc story note.

## Locked rules (every phase)

1. Lori uses ONLY approved context. Unapproved OCR/date/place/event/caption never reaches her prompt.
2. Lori never says "I can see …" — she says "the approved text says …".
3. Raw GPS never reaches Lori — only an approved broad label ("Munich area").
4. Nothing auto-promotes to memoir or narrator truth (candidate notes carry both flags 0).
5. No live browsing inside Lori; enrichment from stored/approved lookups only.

## Phase 5 — caption + operator context note (LANDED 2026-07-09)

**The review finding it closes:** `trip_interview_context` surfaced operator `caption` to Lori's prompt gated ONLY on `narrator_ready` — no per-caption approval. The old test suite locked the leak in (`test_includes_narrator_ready_caption` asserted an unapproved operator caption surfaces).

What landed:

- **Migration 0022** — `trip_photo_links` gains `caption_approved_for_lori` (DEFAULT 0), `operator_context_note`, `operator_context_approved_for_lori` (DEFAULT 0). Nothing is approved by silence.
- **Approval semantics:** `narrator_caption` (the narrator's OWN words from a photo-elicit session) is allowed by construction — no flag. Operator `caption` requires `caption_approved_for_lori=1`. Operator context note requires its own flag. **Editing the caption or note REVOKES its approval** server-side (approval refers to the text the operator actually reviewed); the Travel Doc checkbox unticks to mirror it.
- **`trip_interview_context`** — caption gate rewritten (narrator caption > approved operator caption > nothing); approved notes render as `Approved photo context (place): …` per locked rule 2. Hard-exclusion docstring updated.
- **Repository/router** — `photo_link_update` + `PhotoLinkPatch` + `PATCH /api/trips/photo-links/{id}` carry the new fields (`clear_operator_context_note` clears note AND approval); pre-Ph5 payloads byte-stable.
- **Travel Doc UI** — photo cards in the editor Photos tab gain: narrator-caption read-only line, "Caption → Lori" checkbox, context-note textarea ("operator-only" placeholder), "Note → Lori" checkbox; caption/note edits untick approval locally.
- **Tests** — `test_trip_interview_context` +4: unapproved caption withheld / narrator caption allowed flag-free / note gated both directions + "Approved photo context" phrasing / edit revokes approval. The leak-locking test flipped to assert the APPROVED path.

## Same-session review fixes (2026-07-09)

- **BUG-TRIP-CLUSTER-FOREIGN-NARRATOR-01** — `cluster-photos` accepted any `narrator_id` and linked that narrator's photos into this trip. Now 400 unless it matches the trip owner.
- **Travels photo-added directive** was missing the mandatory calendar-date-recall ban (pre-existing test failure at HEAD; directive fixed).

## Open review findings for later phases (from the 2026-07-09 sweep)

- `include_in_memoir` defaults to 1 on photo links — every clustered low-confidence link auto-enters the memoir appendix. **Design decision needed:** photos opt-out by design, or flip to 0 + promotion like notes/sources.
- `/narrator-photo-links` ships operator provenance columns (assignment_method, confidence, lat/lon, operator caption) over the wire to the narrator surface (JS doesn't render them). Project narrator-safe columns only — natural to do in Ph2 when GPS privacy work happens.
- `cluster-photos` metrics over-report (`skipped_operator_confirmed` always 0; `links_written` counts preserved links).
- `_TRIP_PREV_LORI` / `_TRIP_LAST_CAPTURE` chat_ws globals grow unbounded per conv_id.
- `upload_source` multipart path untested.

## Remaining phases (build order)

Ph1 EXIF/file metadata (build on `metadata_trust` — extraction exists; add `date_confidence`, `location_approved_for_lori`/`date_approved_for_lori` default 0, "No embedded EXIF found" display) → Ph3 date/event enrichment (`photo_context_events`, provenance, approved_for_lori=0) → Ph4 OCR draft (`ocr_draft_text`/`ocr_approved_text`, approved only to Lori) → Ph2 geocode broad label (raw GPS stays private) + Ph6 cultural cards → Ph7 context feed (extend the Ph5 block) → Ph8/9 question generation + direct factual answers ("I don't know that from the approved trip record yet") → Ph10 capture (exists: `trip_location_notes` source_type=lori, source_ref=photo_link:<id>, flags 0) → Ph11 tests throughout.

## Revision history

- 2026-07-09 — Spec banked; Ph5 landed same session with the code-review sweep that motivated its ordering.
