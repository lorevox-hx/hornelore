# WO-EXPORT-ARCHIVE-WRITER-BRIDGE-01 — Diagnosis

Status: **DIAGNOSIS COMPLETE — NO DEFECT FOUND ON THE STATED SCOPE.**
Date: 2026-07-27
Predecessor closeout: c40e6fe (WO-2 Evidence Review Queue, closed)
Production code changed by this diagnosis: **none.**

The work order's first scope line is "Diagnose the intended backend
transcript/archive writer after BUG-209." That diagnosis contradicts the
work order's stated Problem, so no code was written. This report records
what the repo and the live data actually show, and what the real gap is.

---

## 1. The stated problem

> The turns table is receiving current rows, but
> DATA_DIR/memory/archive/people/<person_id>/sessions/ has not been
> written since 2026-07-23. Export zips the archive store, so current
> Travel Doc/Lori turns are safe in SQLite but absent from export.

Half of this is correct. The conclusion drawn from it is not.

## 2. The archive writer is not broken

Christopher's own archive directory did stop on 2026-07-23:

    memory/archive/people/a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2/sessions/
      2026-07-23 23:00  smoke_1784847598215
      2026-07-23 22:59  smoke_1784847585363
      2026-07-23 21:48  safetylive_...

But other narrators kept writing after that date, and the archive event
matches the SQLite row to the second:

    memory/archive/people/93479171-0b97-4072-bcf0-d44c7f9078ba/sessions/
      2026-07-26 03:21:31  switch_ms18e7zp_z62u/transcript.jsonl
    turns row for that session:
      2026-07-26T03:21:30.749725

The smoke person ac271ebc-4e1b-4b5e-b954-e72c4b0149be was written
2026-07-24 15:17:27.

Turns per day since 2026-07-10: 07-10: 14, 07-13: 6, 07-14: 108,
07-23: 68, 07-24: 18, 07-25: 2, 07-26: 2, 07-27: 4.

Every recent conv_id is `tdlab_*` (Travel Doc lab), `switch_*` (narrator
switch — which DID archive), or `smoke_*`. The 07-27 turns are all
`tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3`.

**Conclusion: there is no missing writer and no broken bridge.** What is
absent from the archive store is exactly and only `travel_doc_modal`
turns.

## 3. That absence is deliberate, and a test enforces it

`server/code/api/routers/chat_ws.py:1264`

    _skip_life_story_archive = (_archive_surface == "travel_doc_modal")

mirrored at the assistant-turn site near line 4594:

    _skip_modal_archive = (... == "travel_doc_modal")

Both gates are pinned by `tests/test_modal_archive_boundary.py`
(BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01), which records the LOCKED
PRODUCT RULE of 2026-07-09 and the live incident of 2026-07-14: chat_ws
archived every turn to the narrator's life-story archive gated on
person_id and never on surface, so Travel Doc modal turns landed in the
Narrator Room transcript as things the NARRATOR said. Because
`peek_at_memoir` / `compose_memory_echo` read archive sessions to build
"what you've shared so far", operator workspace chatter became narrator
memory and Lori recited it back as the narrator's own life. The test
docstring closes: "This test exists so that never regresses."

Implementing the work order's literal scope line — "Add the missing
backend archive.append_event() bridge" — would resurrect that bug, break
four of that file's five tests, and violate the standing rule "Travel
Documenter = operator tool for editing trips. Travels shelf =
narrator/Lori conversation surface. Do not mix their state."

**Not implemented. Escalated instead.**

## 4. There are three exports, and the work order conflates them

| Export | Entry point | Reads |
|---|---|---|
| Archive zip | `memory_archive.py:614 export_person` | the archive filesystem store |
| Narrator memoir DOCX | `memoir_export.py:731 _captured_story_sections` | `_db.story_candidate_list_for_memoir(person_id)` — **not the archive store at all** |
| Trip memoir DOCX | `trips.py:2099 export_docx` -> `trip_repository.trip_memoir_preview` | `location_notes_list(trip_id)`, filtered on `include_in_memoir` |

So "Export zips the archive store" is true of the zip and false of the
memoir. The memoir DOCX is DB-driven and archive-independent. Writing
modal turns into the archive store would therefore not have put them in
the memoir anyway.

## 5. The real reason modal material does not appear

The Travel Doc modal capture chain is intact end to end:

    chat_ws capture_modal_turn
      -> services/trip_story_capture.py
      -> trip_location_notes  (source_surface='travel_doc_modal')

and `ui/js/travel-doc-lab.js:5588` already renders an "In memoir" toggle
per note, backed by `PATCH /api/trips/location-notes/{note_id}`.

Live DB, `trip_location_notes`:

    source_surface     include_in_memoir   n   last
    NULL               0                   8   2026-07-24T11:57:29Z
    travel_doc_modal   0                   4   2026-07-27T04:17:05Z
    total: 12

**All twelve notes are `include_in_memoir=0`. Nothing has ever been
promoted.** `trip_memoir_preview` skips every unflagged note by design:
"Notes NOT flagged never reach the memoir
(WO-TRAVEL-DOC-STORY-LAYER-01)."

The 2026-07-27 Bismarck turn is captured correctly as note
`9df82b33-5311-4393-82b9-7eee3057bed9` on trip
`9538cd88-5c8b-4da4-b2a9-2a03f8db32a3`. It is simply not flagged.

## 6. Gaps that ARE real (candidates for a redirected work order)

1. **Narrator memoir has no trip lane.** `memoir_export.py` contains no
   `trip_location_notes` path. A promoted trip story reaches the trip
   DOCX and never the narrator memoir DOCX. This is a genuine export
   bridge, and it touches neither the archive store nor the two-surface
   rule.
2. **The promotion toggle is not discoverable.** The mechanism exists and
   has never been used once in twelve notes across seventeen days. That
   is a workflow/visibility problem, not a code defect.

## 7. Untouched by this diagnosis

* WO-2 import-provenance behavior — unchanged.
* The `candidate_promote()` mirror guard — kept, per ruling.
* No Picker, Takeout, or Lori Review Assistant work started.
* The old browser archive writer — remains disabled.
* No memoir/export format rewrite.
