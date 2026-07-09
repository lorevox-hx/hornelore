# WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01 (ORIGINAL FILING)

> **SUPERSEDED for status tracking:** the LIVING copy is
> `docs/wo/WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01_Spec.md`
> (Phase 5 LANDED 2026-07-09 + review findings + remaining build order).
> This root file is preserved as the original filing text.

**Status:** SPEC as originally filed 2026-07-09. The next direction after the
trip photo loop landed.

## Goal

Let Lori ask **intelligent, grounded** trip-photo questions using **approved**
photo/file context: metadata, geo, date/event, OCR text, caption, and cultural
enrichment — **without** letting her invent facts or claim she sees the image.

Core flow (approval/provenance in the middle is non-negotiable):

> Photo → metadata / OCR / geo / date enrichment → **operator approval +
> provenance** → Lori context → better questions → narrator answer → Travel
> Doc story note.

**Locked rules (apply to every phase):**
- Lori may use ONLY approved context. Unapproved OCR/date/place/event/caption
  never reaches her prompt.
- Lori never says "I can see …". She says "the approved text says …".
- Raw GPS coordinates never reach Lori — only a broad label ("Munich area")
  after approval.
- Nothing here auto-promotes to memoir or narrator truth. It is context for
  better questions, plus review-only candidate notes (both flags 0).
- No live browsing inside Lori. Enrichment comes from stored/approved lookups.

## Motivating example (Munich beer-menu photo)

Approved context card the system should be able to build:
- Possible date: 2026-05-14 (from filename `PXL_20260514_…`, low-confidence)
- Possible place: Munich, Bavaria (from GPS → broad label, if present)
- Event: Christi Himmelfahrt / Ascension Day; Vatertag (German Father's Day)
- Approved OCR: "Augustiner Maibock", "Heller Bock", "Augustiner-Bräu-München"
- Cultural: Bavarian Tracht (Lederhosen / Dirndl); Maibock/Heller Bock; Weißwurst,
  Brezen, sweet mustard, beer-hall food

Then Lori can ask: *"The approved text on this photo says Augustiner Maibock —
was that part of your first Munich meal?"*

## Phases

1. **File + EXIF metadata on upload** — filename, MIME, dimensions, hash, upload
   ts; EXIF DateTimeOriginal/offset, GPS, camera make/model; filename-date guess.
   Fields incl. `date_confidence` (exif|filename_guess|operator_confirmed|missing),
   `location_approved_for_lori`/`date_approved_for_lori` (default false). Raw GPS
   never exposed; "No embedded EXIF found" shown clearly when absent.
2. **Reverse-geocode broad place** — GPS → city/region/country label; exact GPS
   stored private; broad label to Lori only after approval.
3. **Date/event enrichment** — approved calendar/holiday lookup (e.g. Ascension
   Day / Vatertag) stored as draft `photo_context_events` with provenance +
   `approved_for_lori` default false.
4. **OCR draft** — run OCR (button or on upload); store `ocr_draft_text` +
   confidence + engine; `ocr_approved_text` / `ocr_approved_for_lori` default
   false. Lori uses approved OCR only.
5. **Manual caption + operator context note** — `caption_text` /
   `caption_approved_for_lori`, `operator_context_note` /
   `operator_context_approved_for_lori`. **Fastest path — build first.**
6. **Cultural context suggestions** — triggered by approved place/date/OCR/text;
   candidate cards (clothing / holiday / food); approval-gated.
7. **Feed approved context into `trip_interview_context`** — compact block:
   approved caption + OCR + date/place + event/cultural + linked notes. Exclude
   unapproved OCR, raw vision, raw GPS, unapproved guesses, non-narrator-ready
   photos, operator-only notes.
8. **Better Lori question generation** — one short, cautious question from
   approved context; "Does that sound right?" when uncertain; no invented
   restaurant names; no "I see".
9. **Direct factual question handling** — "what holiday was it / what does the
   sign say / what are those clothes called" answered from approved context;
   "I don't know that from the approved trip record yet" when absent; never echo
   the question back.
10. **Story capture** — narrator answer → `trip_location_notes`,
    `source_type=lori`, `source_ref=photo_link:<id>`, both flags 0. Travel Doc
    shows "from Lori chat" + linked photo + approved-context badges.
11. **Tests (20)** — EXIF present/absent, filename-date low-confidence, GPS broad
    label + raw hidden, approved-vs-unapproved gating for date/OCR/caption/event/
    cultural, direct-factual no-echo + answers only from approved context, no raw
    GPS/vision in prompt, no restaurant invention, `source_ref=photo_link` on
    capture.

## Recommended build order (low risk → high ML)

Ph5 caption lane → Ph1 EXIF/file → Ph3 date/event → Ph4 OCR → Ph2 geocode +
Ph6 cultural → Ph7 context feed → Ph8/9 question + factual → Ph10 capture (mostly
already done) → Ph11 tests throughout.

## Commit plan

1. `feat(trips): extract trip photo metadata for review`
2. `feat(trips): add approved photo captions and OCR context`
3. `feat(trips): add date and cultural enrichment for trip photos`
4. `feat(trips): feed approved photo context into Lori trip prompts`

## Where it plugs in

- Read side: `trip_interview_context` gains an approved-photo-context block
  (Ph7), staying LAW-3 isolated + read-only.
- Write side: `trip_story_capture` already links answers to photos (Ph10 done).
- Storage: new approval-gated fields on the photo/photo-link records +
  `photo_context_events` / OCR / caption tables, all with provenance +
  `approved_for_lori` defaults false.
