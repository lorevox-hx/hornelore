# WO-TRAVEL-DOC-LORI-MODAL-01

**Status:** BACKEND CAPTURE SLICE LANDED 2026-07-09 (migration 0024 source_surface + `capture_modal_turn` + chat_ws `surface=travel_doc_modal` branch + question-detector hardening + 8 tests). FE modal (UI + WS scope + sandbox drawer + anchor chip + prompt context) = next session's single focus. (Filed 2026-07-09 from ChatGPT/Chris live-workflow triage, transcript switch_mre0txvh_tb7w). **Build 3 (LLM date/event drafts) is PAUSED behind this** — "otherwise we keep adding smart context to the wrong interaction model."
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

## Photo-intelligence provenance model (CLARIFIED 2026-07-09 — supersedes a blanket "never vision")

Three tiers, and the rule is about PROVENANCE, not blindness:

1. **Raw image vision** (machine guess: "likely a Wels catfish sculpture")
2. **OCR / readable text** ("Deutsches Jagd- und Fischereimuseum", "BMZ / Neuhauser Str. 2")
3. **Approved photo context** (operator-approved fact)

Machine drafts (vision/OCR/metadata) MAY be generated — operator-triggered,
local tools or stubbed — stored with source/provenance, shown in Travel Doc,
and Lori MAY use them **only phrased as draft**: "The draft photo context
suggests… Is that right?" / "The OCR draft reads…" / "The file name
suggests…". Fact phrasing ("The approved photo context says…") ONLY after
operator approval. WRONG rule: never look at images / wait for the narrator
to type every fact. The danger is never image use — it is guesses stated as
certainty. Hard rules unchanged: no web lookup, no raw GPS to Lori, no
upload/save/download dates to Lori, filename date is a guess until approved,
never "I can see…" (reserved for a possible future narrator-facing vision
mode).

Approval gates for the modal build: draft observation · approved photo
context · approved OCR text · approved taken date · approved place.

## One-session build scope (Chris directive: "not baby steps")

(1) modal UI, (2) modal-owned chat scope (no shelf switch), (3) photo anchor
chip, (4) capture intake sandbox, (5) Mark Twain gate, (6) manual Chrome
acceptance with the real Munich fish photo, (7) draft OCR/vision lane —
operator-triggered button, stubbed or local-tool-backed (LLM is text-only;
Tesseract not installed until Ph4 — a stub that accepts operator-entered
draft observations with provenance labels satisfies the acceptance flow),
(8) the approval gates above. Acceptance adds: "what can you tell me about
the photo" BEFORE approval → "The draft photo context suggests this may be a
large fish sculpture outside the German Hunting and Fishing Museum. Is that
right?"; AFTER approval → "The approved photo context says this was the Wels
catfish outside the German Hunting and Fishing Museum in Munich."; memory
answer lands in the sandbox photo-linked, flags off.

## Manual live acceptance (Chrome, real photo — NOT a repo fixture)

Photo: `/mnt/c/Users/chris/Downloads/PXL_20260514_125640482.jpg` (fish
sculpture, Neuhauser Str., Munich). Expected Ph1 behavior: EXIF may be
absent → filename guess 2026-05-14, date_source=filename_guess,
date_approved_for_lori=0. Flow: upload to Spring 2026 trip → modal from
the photo card → "what date was that taken" → BEFORE approval: "I don't
have an approved taken date for this photo yet. The Travel Doc can
store one if you confirm it." → approve date → AFTER approval: "The
approved taken date for this photo is May 14, 2026." → add approved
caption ("Fish sculpture outside the German Hunting and Fishing Museum
in Munich.") + context note (Neuhauser Straße) → "can you tell me about
the photo" → approved text only, never "I can see". The automated Mark
Twain gate stays synthetic — never depend on Downloads.

Note for the build: `answer_modal_direct_question` needs the POST-
approval date answer shape above; filename TIME guess (12:56:40) is
optional parser polish — date-only is acceptable for the demo.

## Core acceptance test (the one that matters)

Open Travel Doc → select photo → Talk with Lori → modal opens IN Travel
Doc. Ask "what date was that taken?" → Lori answers "I don't have an
approved taken date for this photo yet…" — and the photo card is still
on screen to approve or edit the date.

## Adopted UI decisions (Chris+ChatGPT+Gemini convergence, 2026-07-09)

**IN the modal build (required, not polish):** (1) **Lori Capture Intake Sandbox** — persistent drawer in the modal: rolling capture feed from the current session, each row shows "from Lori modal" + scope (trip/region/stop/photo, thumbnail badge when photo-linked) + Assign-to-Stop ▼ + edit/delete + In-memoir OFF + Use-with-Lori OFF. (2) **Photo Anchor Chip** — thumbnail + label + ✕ Unanchor beside the modal input when active_photo_link_id is set; captures attach to the photo ONLY while the chip is present; ✕ clears the anchor; NO timeout-based clearing; narrator shelf does NOT get the chip yet.

**Build 7 polish (banked):** approval-block grouping "Shared with Lori" (VETOED wording: "Lori's Eyes Only") with green trusted / amber machine-draft badges + edit-clears-approval micro-animation; amber chronology nudge (child-stop dates outside parent range, non-blocking); big timeline split-pane/subway visual later.

**Rejected wording:** never label provisional inserts "Lori is remembering…" — "Draft"/"Provisional"/dotted outline only (parser drafts; Lori doesn't remember).

**Acceptance test file:** opt-in Mark Twain gate (`HORNELORE_RUN_MODAL_ACCEPTANCE=1`, tests/test_travel_doc_lori_modal_mark_twain.py) — arrives from ChatGPT via upload; review before commit.

## Tests (15 — from the filing, verbatim intent)

no-navigation · modal carries trip id · stop scope · photo scope · answer creates candidate note · provenance · flags 0 · photo_link preserved · close returns selection · Travels shelf unchanged · no raw GPS · no unapproved caption/OCR/date/place · no SYSTEM/meta leaks · "what date was that taken" answers from approved taken date or says unknown · "can you tell me about the photo" answers from approved caption/context or says unknown.

## Transcript evidence that motivated this (2026-07-09)

Build 1.5 guards verified WORKING live (Bavaria normalized, no SYSTEM leak, no preamble, no echo). What failed was the interaction model: "what date was that taken" → continuation boilerplate; "can you tell me about the photo" → generic recovery. The narrator was doing TRAVEL DOC work in the narrator-room surface. Interim fix (landed same day, see below) makes those questions answer honestly from the shelf surface; the modal is the real fix.

## Interim fix landed 2026-07-09 (same session as filing)

`trip_interview_context`: direct photo/date questions ("what date was that taken", "can you tell me about the photo", "when was that taken") now route to the deterministic trip-answer path and reply honestly — approved context when it exists, else "I don't know that from the approved trip record yet — but you might. What do you remember about that moment?" — instead of continuation boilerplate. Duplicate-idle-nudge repetition noted for the modal build (idle nudges should vary or stay silent on repeat).

## Revision history

- 2026-07-09 — Filed; Build 3 paused; interim honest-unknown fix landed.
