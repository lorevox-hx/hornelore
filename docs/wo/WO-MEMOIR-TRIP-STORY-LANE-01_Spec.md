# WO-MEMOIR-TRIP-STORY-LANE-01 — Spec

**Status:** BUILT, tests green (21/21 new, neighbours green). Awaiting
Chris's live verification on the serving stack.
**Opened:** 2026-07-27
**Supersedes:** WO-EXPORT-ARCHIVE-WRITER-BRIDGE-01 (closed no-defect,
diagnosis at `docs/reports/WO-EXPORT-ARCHIVE-WRITER-BRIDGE-01_DIAGNOSIS.md`,
commit `1a7f3d8`)

---

## Goal

Let approved/promoted Travel Doc `trip_location_notes` reach the narrator
memoir DOCX **without** writing Travel Doc modal turns into the
life-story archive.

## Why this work order exists

WO-EXPORT-ARCHIVE-WRITER-BRIDGE-01 was opened on the premise that the
archive filesystem writer had stopped and needed an
`archive.append_event()` bridge for Travel Doc turns. Diagnosis found
otherwise:

* The archive writer is healthy. Janice's session
  `93479171-.../sessions/switch_ms18e7zp_z62u/transcript.jsonl` was
  written 2026-07-26 03:21:31, matching her `turns` row at
  `2026-07-26T03:21:30.749725`.
* Only `travel_doc_modal` turns are absent, and that exclusion is
  deliberate — the two-surface rule of 2026-07-09, enforced at
  `chat_ws.py:1264` and locked by `tests/test_modal_archive_boundary.py`
  after BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01.
* The narrator memoir DOCX does not read the archive store at all; it is
  DB-driven via `_captured_story_sections`.
* The real gap: modal turns land in `trip_location_notes` and the
  narrator memoir had no lane for them. All 12 live notes were at
  `include_in_memoir=0`.

Chris's ruling (2026-07-27): close the bridge work order as no-defect, do
not override the two-surface rule, build the memoir-side trip lane next.

## Scope — as ruled

| Requirement | Status |
|---|---|
| Keep Travel Documenter and Travels shelf separate | HELD — no cross-surface state added |
| Do not archive `travel_doc_modal` turns as narrator life-story turns | HELD — zero archive writes in this change |
| Read approved `trip_location_notes` from the DB | DONE |
| Include only notes with `include_in_memoir=1` | DONE |
| Add a trip-story section, clearly sourced as Travel Doc trip material | DONE |
| Preserve existing trip DOCX behavior | HELD — `trips.py` untouched, test pins it |
| Tests proving unapproved stay out and approved appear | DONE |
| No Picker, Takeout, Lori Review Assistant, archive rewrite | HELD |

## Design

One new harvester in `memoir_export.py`, mirroring the shape of the
existing `_captured_story_sections` lane so trip material flows through
translation and all four renderers with no renderer changes:

```
_trip_story_sections(person_id) -> List[MemoirSection]
    gate:   HORNELORE_TRIPS must be on (trips are a default-OFF surface)
    read:   trip_repository.trip_list(person_id)
            trip_repository.location_notes_list(trip_id)
    filter: include_in_memoir truthy AND note_text non-blank
            (hidden=1 already excluded by location_notes_list default —
             this lane never passes include_hidden=True)
    order:  dated trips chronologically, undated trailing
    emit:   MemoirSection(id="trip_stories_<trip_id>",
                          label="From your travels — <trip title>",
                          items=[...])
    never raises
```

Wired into `api_memoir_export_docx` immediately after the captured-story
append, gated on `req.person_id and req.include_trip_stories`. New
request field `include_trip_stories: bool = True` mirrors
`include_captured_stories` and gives the caller an opt-out.

`person_id -> trip` binding is `trips.person_id`, one narrator per trip.

Item rendering: `"<note_title> — <note_text>"` when the note carries a
title (modal captures often do — the title is the question Lori asked),
bare `note_text` otherwise.

## The boundary this work order respects

This lane performs **no archive write of any kind**. A test asserts
`append_event` never appears in `memoir_export.py`, and a second test
unparses `_trip_story_sections` with its docstring stripped and asserts
the executable body contains no reference to `archive` at all. A third
re-asserts that `chat_ws.py` still carries `_skip_life_story_archive`,
`== "travel_doc_modal"`, and `_skip_modal_archive = (` — so this work
order cannot silently loosen the gates that
`tests/test_modal_archive_boundary.py` owns.

## Acceptance

* [x] Approved note (`include_in_memoir=1`) appears in the narrator memoir.
* [x] Unapproved note never appears.
* [x] Hidden note never appears.
* [x] Section is clearly labeled as travel material and carries the trip title.
* [x] Trip DOCX export path unchanged.
* [x] Captured-story lane (WO-MEMOIR-STORY-CANDIDATES-WIRE-01) still wired.
* [x] Two-surface gates in `chat_ws.py` unchanged.
* [x] No archive write introduced.
* [ ] Live verification on the serving stack — Chris.

## Tests

`tests/test_memoir_trip_story_lane.py` — 21 tests, all passing.

| Class | Covers |
|---|---|
| `ApprovalGateTest` (6) | approved in, unapproved out, mixed trip, hidden left to repo default, blank text skipped, no-approved-notes trip emits nothing |
| `PresentationTest` (4) | section id/label sourcing, title carried into item, untitled bare, chronological ordering with undated trailing |
| `ResilienceTest` (4) | trips flag off, repository raises, per-trip note failure isolated, no trips |
| `TwoSurfaceBoundaryTest` (3) | no `append_event`, executable body archive-free, `chat_ws` gates intact |
| `RouteWiringTest` (3) | route appends, opt-out + person gate, captured-story lane still wired |
| `TripDocxUntouchedTest` (1) | trip DOCX still renders from `trip_memoir_preview` |

Neighbours re-run green: `test_modal_archive_boundary` (5),
`test_memoir_story_wire` (9).

`test_memoir_export_security` could not run in the diagnosis VM — it
imports real `fastapi`, which that VM lacks. **It must be run in Chris's
`.venv`.** This is an environment gap, not a defect introduced here.

## Operator note — the thing that actually unblocks the memoir

The pipeline was never the blocker. `trip_location_notes` has been
capturing modal turns correctly, and `travel-doc-lab.js:5588` has
rendered an "In memoir" toggle per note the whole time. It has never been
flipped once across 12 notes and 17 days. This lane means flipping it now
does something. If it stays unflipped the memoir stays empty of trip
material by design — nothing is approved by silence.

The follow-on candidate (Chris: "later, but useful") is an operator
promotion surface that makes that toggle findable.

## Files

* `server/code/api/routers/memoir_export.py` — modified (+98 lines)
* `tests/test_memoir_trip_story_lane.py` — added (316 lines)
* `docs/wo/WO-MEMOIR-TRIP-STORY-LANE-01_Spec.md` — added (this file)

## Explicitly not done

Picker, Takeout, Lori Review Assistant, archive rewrite, memoir format
rewrite, browser archive writer re-enable, any change to WO-2
import-provenance behavior, any change to the `candidate_promote()`
mirror guard.
