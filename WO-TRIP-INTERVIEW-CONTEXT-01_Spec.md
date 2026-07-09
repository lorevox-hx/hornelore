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

## Step 1.5 — prompt-safety + wording (review 2026-07-08)

Before wiring: added `_safe()` prompt sanitizer (neutralizes `[`/`]`,
`SYSTEM:` directive shape, newlines; word + char clip) applied to every
dynamic value in the rendered `text`; changed route wording to "Places on
the Travel Doc route board: …" + "Do not claim the narrator personally
confirmed this order unless they have said so." Tests added for injection
sanitizing + wording.

## Step 2 — chat wiring — LANDED 2026-07-08 (default-OFF)

`trip_interview_context.context_block_for_turn(person_id, runtime71)` owns
the gate: flag `HORNELORE_TRIP_INTERVIEW_CONTEXT` ON, AND
`runtime71.active_trip_id`, AND `travels_shelf_open`, AND the trip owned by
`person_id` (via `build_trip_interview_context`). Returns a prompt-ready
block or "".

`chat_ws.py` (right after `compose_system_prompt`) appends that block to the
system prompt — minimal, non-fatal (try/except), read-only. **Default OFF →
live behavior byte-identical until the flag is set.** Travel Doc still never
dispatches or mutates runtime/session state; prompt_composer is untouched.

8 gate/boundary tests added: flag off; flag on + no active trip; shelf
closed; wrong owner; approved note appears; unapproved notes/sources/
non-ready captions excluded; injection sanitized. 18 tests total green.

Keep the "Lori context candidate — not used live yet" UI wording until you
flip the flag and verify live.

## Later

- WO-TRIP-LORI-ANSWER-CAPTURE-01 (narrator answers → candidate story notes)
  — only after Step 2.
- Sources need a dedicated `include_in_interview_context` flag before their
  summaries can be surfaced here.
