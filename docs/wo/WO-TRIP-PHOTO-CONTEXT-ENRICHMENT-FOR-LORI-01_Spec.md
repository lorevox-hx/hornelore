# WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01

**Status:** Phases 5 + 1 LANDED 2026-07-09. Phases 2-4, 6-9 open; Phase 10 mostly pre-existing (trip_story_capture); Phase 11 grows with each phase.
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

## Phase 1 — EXIF/file metadata for review (LANDED 2026-07-09, later same day)

Per Chris's directive: boring and reviewable, no LLM, no OCR, no web, NO dependency changes (locked by test — the parser is pure stdlib).

- **Migration 0023** — `photos` gains `date_source` (exif|filename_guess|operator_confirmed|missing|unknown, default unknown), `taken_at_filename_guess`, `date_approved_for_lori` + `location_approved_for_lori` (both DEFAULT 0). Existing columns already carried the rest (date_value/precision, location_label/source, raw lat/lon private, metadata_trust, metadata_json raw EXIF).
- **`photo_intake/filename_date.py`** (NEW, pure stdlib) — `parse_filename_date` (PXL_/IMG_/WhatsApp/Samsung/Screenshot/dashed shapes, real-calendar-date validated) + `derive_date_fields`: EXIF wins; a filename guess is stored SEPARATELY and NEVER auto-fills date_value; nothing → 'missing'. Suspect-scan EXIF dates stay quarantined (trust lane unchanged).
- **Intake** — `ingest.ingest_photo_file` stamps `date_source` + `taken_at_filename_guess` via new `photo_repo.set_date_review_fields` (fail-soft on pre-0023 DB, same posture as the trust column).
- **Revoke-on-edit at the REPOSITORY layer** — `patch_photo`: editing `date_value` clears `date_approved_for_lori` + stamps `date_source='operator_confirmed'` (unless the patch sets them); editing `location_label` clears `location_approved_for_lori`. Every caller inherits the rule; router adds DATE_SOURCES enum validation.
- **Operator read** — `trip_repository.photo_links_list` LEFT JOINs photos projecting `photo_date_value/precision/source`, `photo_taken_at_filename_guess`, `photo_location_label`, `photo_metadata_trust`, approval flags, `photo_narrator_ready`, and **`photo_gps_present` as a boolean — raw coordinates deliberately NOT projected**. Narrator read (`narrator_photo_links`) untouched.
- **Travel Doc photo cards** — "Date: … (EXIF)" / "Date guessed from filename: … (low confidence — not canonical)" / "No embedded EXIF date found"; "GPS found (kept private)" / "No GPS"; broad place-label input; "Date → Lori" + "Place → Lori" checkboxes (untick locally when edits revoke).
- **NOT in Ph1:** approved metadata does NOT feed Lori yet — that is Ph7. `trip_interview_context` untouched; test locks raw GPS out of the context text.
- **Tests** — `tests/test_trip_photo_metadata.py` (13): parser shapes + garbage/impossible dates, EXIF-wins, missing-EXIF clean state, filename-guess-never-canonical, suspect-scan demotion, pure-stdlib lock (no-dependency proof), approvals default 0, gps_present without raw coords, raw GPS absent from Lori context, review fields projected, edit-revokes-approval, cross-trip/narrator isolation.

## Same-session review fixes (2026-07-09)

- **BUG-TRIP-CLUSTER-FOREIGN-NARRATOR-01** — `cluster-photos` accepted any `narrator_id` and linked that narrator's photos into this trip. Now 400 unless it matches the trip owner.
- **Travels photo-added directive** was missing the mandatory calendar-date-recall ban (pre-existing test failure at HEAD; directive fixed).

## Open review findings for later phases (from the 2026-07-09 sweep)

- `include_in_memoir` defaults to 1 on photo links — every clustered low-confidence link auto-enters the memoir appendix. **Design decision needed:** photos opt-out by design, or flip to 0 + promotion like notes/sources.
- `/narrator-photo-links` ships operator provenance columns (assignment_method, confidence, lat/lon, operator caption) over the wire to the narrator surface (JS doesn't render them). Project narrator-safe columns only — natural to do in Ph2 when GPS privacy work happens.
- `cluster-photos` metrics over-report (`skipped_operator_confirmed` always 0; `links_written` counts preserved links).
- `_TRIP_PREV_LORI` / `_TRIP_LAST_CAPTURE` chat_ws globals grow unbounded per conv_id.
- `upload_source` multipart path untested.

## Enrichment-engine decision (LOCKED 2026-07-09, Chris)

**Local-first stays. The local LLM is the enrichment engine; no offline
datasets; no web.** Rationale: the rule protects narrator-data egress, not
system knowledge; Llama-3.1-8B carries the world knowledge the motivating
example needs (Christi Himmelfahrt/Vatertag, Maibock, Tracht); and the
approval gate structurally contains hallucination — every LLM draft lands
`approved_for_lori=0` and is reviewed by the operator who was on the trip.

- **Ph3 + Ph6 become LLM-draft lanes** — operator-triggered "Suggest
  context" prompts the LOCAL LLM with approved date/place/OCR text and
  writes DRAFT cards (provenance `source=local_llm`, flags 0). No
  `holidays` package.
- **Ph2 becomes "place from context, not coordinates"** — an 8B LLM
  confabulates lat/lon→city, so place labels come from the clustered stop,
  filename, OCR text, or the operator typing it. Raw GPS stays stored
  private and unused. A narrowly-scoped operator-side web-lookup flag
  (minimal public-fact queries only; never narrator content; Lori never
  browses) is a POSSIBLE LATER carve-out if real usage demands it —
  default absent.
- **Ph4 OCR is the one true dependency add** — `pytesseract` +
  system `tesseract-ocr` + `tesseract-ocr-deu` (CPU-only, zero VRAM
  pressure; draft quality is acceptable because output is approval-gated).
  Note: pytesseract was deliberately excluded from the lean hornelore venv
  (requirements-gpu.txt notes) — re-adding is a conscious, documented call.
- Enrichment runs as an OPERATOR-CONSOLE action, never inside Lori's
  runtime — locked rule 5 untouched.

## Remaining phases (build order)

Ph1 EXIF/file metadata (build on `metadata_trust` — extraction exists; add `date_confidence`, `location_approved_for_lori`/`date_approved_for_lori` default 0, "No embedded EXIF found" display) → Ph3 date/event enrichment (LOCAL-LLM draft cards in `photo_context_events`, provenance, approved_for_lori=0) → Ph4 OCR draft (`ocr_draft_text`/`ocr_approved_text`, approved only to Lori; pytesseract) → Ph2 place-from-context + Ph6 cultural cards (LOCAL-LLM drafts) → Ph7 context feed (extend the Ph5 block) → Ph8/9 question generation + direct factual answers ("I don't know that from the approved trip record yet") → Ph10 capture (exists: `trip_location_notes` source_type=lori, source_ref=photo_link:<id>, flags 0) → Ph11 tests throughout.

## Revision history

- 2026-07-09 — Spec banked; Ph5 landed same session with the code-review sweep that motivated its ordering.
- 2026-07-09 (later still) — Phase 1 landed per directive: schema/parser/intake/revoke-at-repository/operator-read/Travel-Doc display + 13 tests; zero dependencies; Lori feed deferred to Ph7.
- 2026-07-09 (later) — Enrichment-engine decision locked: local LLM drafts for Ph3/Ph6, place-from-context for Ph2 (no coordinates, no datasets, no web), pytesseract the only dependency add (Ph4). Local-first rule NOT lifted.
