# WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01 — Spec (NOT YET IMPLEMENTED)

**Status:** SPEC ONLY. Deferred by decision (2026-07-08). Do not wire an
LLM path until a clean operator-side inference path is confirmed (see §6).
The storage side already exists — draft output lands as a
`trip_location_notes` row with `source_type='draft'`, so no new table is
needed.

## 1. Goal

Give the operator a **drafting assistant** inside Travel Doc that turns the
material they've already gathered — a scope's `summary`/`notes`, promoted
story notes, and sources — into a first-draft memoir paragraph they can
edit and then explicitly promote. It is a writing aid for the operator, not
a narrator conversation.

## 2. Hard boundaries (locked)

The draft assistant is **operator-only** and must never:

- touch `runtime71`, `activeTripId`, `tripStyle`, or any Travels-shelf state;
- write or read the narrator transcript / chat archive;
- run extraction or any narrator-memory write;
- auto-include its output in the memoir or interview context.

It must **not** reuse the narrator conversation path (`chat_ws.py` /
`prompt_composer.py`). Those compose narrator-facing prompts with safety,
memory-echo, and extraction wiring — none of which belongs on an operator
drafting tool.

## 3. Endpoint

```
POST /api/trips/{trip_id}/draft-section
```

Request:

```json
{
  "trip_region_id": "…|null",
  "trip_stop_id": "…|null",
  "instruction": "Draft a warm memoir paragraph in Chris's voice.",
  "include_note_ids": ["…"],        // optional: which location notes to feed
  "include_source_ids": ["…"]       // optional: which sources to feed
}
```

The handler assembles **only operator-approved context** for the scope:
the scope's `summary`/`notes`, the selected (or all scope) `trip_location_notes`
rows, and selected `trip_sources` (pasted_text/summary). It sends that to
the model, and returns:

```json
{ "draft": "…draft text only…" }
```

Output is **draft text only** — it is NOT persisted automatically.

## 4. Persisting a draft (uses the existing story layer)

When the operator keeps a draft, the UI creates a `trip_location_notes` row:

```
source_type = "draft"
include_in_memoir = 0
include_in_interview_context = 0
note_text = <draft>
note_title = "Draft — <scope name>"
```

The operator later promotes it like any other note (flip `include_in_memoir`).
No new storage is required — `location_note_create` already accepts
`source_type='draft'` (migration 0019).

## 5. UI (a "Draft" tab, later)

A fourth-plus editor tab ("Draft") for the selected scope:

- shows the approved context that would be sent (read-only preview),
- an instruction box,
- a "Draft" button → calls `/draft-section`,
- the returned draft in an editable box with "Keep as draft note" (creates
  the `source_type='draft'` location note) and "Discard".

Nothing here dispatches to Lori or writes narrator state.

## 6. Inference path — CONFIRM BEFORE IMPLEMENTING

`server/code/api/llm_interview.py` exists and is a candidate operator-side
inference module. Before implementing:

1. Confirm `llm_interview.py` (or a sibling) exposes a plain
   "prompt in → text out" call that does **not** pull in the narrator
   prompt composer, safety layer, memory-echo, or extraction.
2. If it does, wrap it behind a small `services/trip_draft.py` that takes
   assembled operator context + instruction and returns text — LAW-3 style
   (no imports from `chat_ws` / `prompt_composer` / `extract`).
3. If no clean path exists, either add a minimal dedicated inference helper
   or keep this WO parked. Do **not** shoehorn the draft call through the
   narrator path.

## 7. Acceptance gates (when implemented)

- `/draft-section` returns text only; no DB write on the call itself.
- No reference to `runtime71` / `activeTripId` / `chat_ws` / `prompt_composer`
  / `extract` in the draft service (build-gated isolation test, mirroring
  `test_travel_documenter_panel.py`).
- Kept drafts persist as `trip_location_notes` `source_type='draft'` with
  both promotion flags OFF.
- The operator must explicitly flip `include_in_memoir` for a draft to reach
  the memoir; nothing auto-promotes.

## 8. Sequencing

Last of the trip story-layer passes. Depends on the story layer
(WO-TRAVEL-DOC-STORY-LAYER-01, LANDED) for draft storage and on the sources
lane (WO-TRAVEL-DOC-SOURCES-01, LANDED) for source context. Build only after
§6 is answered.
