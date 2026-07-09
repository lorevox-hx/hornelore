# WO-TRIP-INTERVIEW-CONTEXT-01

**Goal:** When a trip is actively open (Travels shelf), give Lori a small,
deterministic, narrator-safe trip context block so she can ask grounded
questions — without Travel Doc ever dispatching prompts or mutating
runtime/session state.

## Step 1 — isolated service + tests — LANDED 2026-07-08

`server/code/api/services/trip_interview_context.py`

`build_trip_interview_context(person_id, active_trip_id, active_trip_stop_id=None)`
→ compact dict (or `None` if the trip is missing / not owned by the
person), with a ready-to-inject `text` rendering.

**Reads (narrator-safe only):** trip title + date span; region/stop route
outline (labelled NOT journey order); active stop/region if supplied;
`trip_location_notes` where `include_in_interview_context=1`;
narrator-ready photo **captions** (via `narrator_photo_links`, captioned
links only).

**Excludes (hard):** operator provenance; non-narrator-ready photos; raw
source documents/text (trip_sources has no interview-approval flag yet, so
**nothing** from sources is surfaced); notes not flagged for interview;
any image/pixel interpretation.

**Pure read:** no writes, no runtime71 mutation, no prompt dispatch, no
extraction, no memory writes, no Travel Doc state writes.

**LAW 3:** imports only `trip_repository`. Build-gated isolation test
(`tests/test_trip_interview_context.py::test_law3_isolation`) fails if
`chat_ws` / `prompt_composer` / `extract` / `memory_echo` / `llm_*` /
`safety` ever appear. 9 tests green (owned/unowned, interview-only notes,
memoir-only excluded, narrator-ready captions in / non-ready out, no raw
source text, compactness, active-stop, isolation).

## Step 2 — chat wiring — PENDING APPROVAL (NOT STARTED)

Minimal read into `chat_ws`/`prompt_composer` behind a default-off flag
`HORNELORE_TRIP_INTERVIEW_CONTEXT=0`. Gates: flag on AND
`runtime71.active_trip_id` set AND Travels shelf open AND trip belongs to
the active person. Insert ONLY the compact `text` block into Lori's prompt.
Travel Doc still never dispatches or mutates runtime/session state. Keep
the "Lori context candidate — not used live yet" UI wording until Step 2
lands. Do not begin until approved.

## Later

- WO-TRIP-LORI-ANSWER-CAPTURE-01 (narrator answers → candidate story notes)
  — only after Step 2.
- Sources need a dedicated `include_in_interview_context` flag before their
  summaries can be surfaced here.
