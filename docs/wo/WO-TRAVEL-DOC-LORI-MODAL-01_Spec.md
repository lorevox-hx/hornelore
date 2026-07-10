# WO-TRAVEL-DOC-LORI-MODAL-01

**Status:** SPEC (filed 2026-07-09 from ChatGPT/Chris live-workflow triage, transcript switch_mre0txvh_tb7w). **Build 3 (LLM date/event drafts) is PAUSED behind this** — "otherwise we keep adding smart context to the wrong interaction model."
**Lane:** Travel Doc / Lori surfaces.

## Product rule (locked)

Two separate Lori surfaces from here on: (1) **Narrator Room / Life Map Lori** — general life-story conversation (Travels shelf stays as-is); (2) **Travel Doc Lori Modal** — trip-building conversation whose every capture flows back into Travel Doc as reviewable memoir material. For travel-memoir work, #2 is the surface.

## Hard rule

If the operator starts Lori from Travel Doc, the UI STAYS in Travel Doc. No narrator-room switch, no Life Map, no Travels-shelf dependency.

## Modal behavior

Right-side overlay/modal "Talk with Lori about this trip"; Travel Doc stays visible; selected trip/region/stop/photo stays active and is shown as a scope header (trip title · region/stop · photo thumbnail when photo-scoped); chat input + history inside the modal; closing returns to the same selection.

## Runtime scope (reuses chat_ws backend, distinct provenance)

`surface=travel_doc_modal` + `active_trip_id` / `active_trip_region_id` / `active_trip_stop_id` / `active_photo_link_id` / `person_id` / `conv_id`. The travel-documenter module keeps its boundary (no state.session, no shelf state) — the modal owns its OWN connection/scope, nothing rides runtime71.

## Lori prompt rules (all existing locks apply)

Approved trip/photo context only; never "I can see"; no browsing; no cold calendar-date asks; no echo; direct questions answered from approved context or "I don't know that from the approved trip record yet."

## Capture

Every meaningful narrator answer → `trip_location_notes` candidate: `source_type=lori`, `source_surface=travel_doc_modal`, `source_ref=modal_turn:<conv_id>:<turn_id>` (+ `photo_link:<id>` when photo-scoped), `include_in_memoir=0`, `include_in_interview_context=0`. No auto-promotion, no auto-approval, no auto-prose. Story Notes tab shows "from Lori modal" + linked photo/stop/region + edit/delete/toggles.

## Modal-specific answer wording (locked 2026-07-09 review)

The shelf's interim fallback ("I don't know that from the approved trip
record yet — but you might…") is right for the NARRATOR surface. The
modal is an OPERATOR workspace, so its fallback is workspace-aware:

> "I don't have an approved taken date for this photo yet. The Travel
> Doc can store one if you confirm it."

— because the operator can fix the missing field right there (the photo
card with Date→Lori / Place→Lori stays visible beside the modal).

## Core acceptance test (the one that matters)

Open Travel Doc → select photo → Talk with Lori → modal opens IN Travel
Doc. Ask "what date was that taken?" → Lori answers "I don't have an
approved taken date for this photo yet…" — and the photo card is still
on screen to approve or edit the date.

## Tests (15 — from the filing, verbatim intent)

no-navigation · modal carries trip id · stop scope · photo scope · answer creates candidate note · provenance · flags 0 · photo_link preserved · close returns selection · Travels shelf unchanged · no raw GPS · no unapproved caption/OCR/date/place · no SYSTEM/meta leaks · "what date was that taken" answers from approved taken date or says unknown · "can you tell me about the photo" answers from approved caption/context or says unknown.

## Transcript evidence that motivated this (2026-07-09)

Build 1.5 guards verified WORKING live (Bavaria normalized, no SYSTEM leak, no preamble, no echo). What failed was the interaction model: "what date was that taken" → continuation boilerplate; "can you tell me about the photo" → generic recovery. The narrator was doing TRAVEL DOC work in the narrator-room surface. Interim fix (landed same day, see below) makes those questions answer honestly from the shelf surface; the modal is the real fix.

## Interim fix landed 2026-07-09 (same session as filing)

`trip_interview_context`: direct photo/date questions ("what date was that taken", "can you tell me about the photo", "when was that taken") now route to the deterministic trip-answer path and reply honestly — approved context when it exists, else "I don't know that from the approved trip record yet — but you might. What do you remember about that moment?" — instead of continuation boilerplate. Duplicate-idle-nudge repetition noted for the modal build (idle nudges should vary or stay silent on repeat).

## Revision history

- 2026-07-09 — Filed; Build 3 paused; interim honest-unknown fix landed.
