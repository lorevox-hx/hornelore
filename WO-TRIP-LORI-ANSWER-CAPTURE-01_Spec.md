# WO-TRIP-LORI-ANSWER-CAPTURE-01

**Goal:** When a trip is open on the Travels shelf and the narrator answers a
trip-scoped Lori question, capture that answer as a **candidate**
`trip_location_notes` row so the operator can review it in Travel Doc —
without auto-promoting anything into the memoir or back into Lori's context,
and without Travel Doc/UI or runtime71 changes.

This is the **reverse** of WO-TRIP-INTERVIEW-CONTEXT-01:

| flow | direction |
|---|---|
| `trip_interview_context` | Travel Doc → Lori prompt context (read) |
| `trip_story_capture` | Lori/narrator conversation → Travel Doc candidate note (write, review-only) |

## Step 1 — isolated service + tests — LANDED 2026-07-08

`server/code/api/services/trip_story_capture.py`

```python
capture_trip_story_answer(
    person_id, active_trip_id, narrator_text,
    previous_lori_text=None, previous_prompt_kind=None,
    active_trip_region_id=None, active_trip_stop_id=None,
    photo_link_id=None, conv_id=None, turn_id=None,
) -> dict
```

Writes a `trip_location_notes` row with `source_type="lori"`, a `source_ref`,
and **`include_in_memoir=0` + `include_in_interview_context=0`** (both
promotion flags OFF — nothing reaches the memoir or Lori automatically).

**Gates (all must pass to capture):** `active_trip_id` present; trip owned by
`person_id`; the prior Lori turn was trip-scoped; the reply is non-trivial.

**Scope resolution:** valid stop → stop note (region derived); else valid
region → region note; else trip-level. Stop/region/photo ids that belong to a
*different* trip are dropped (never write a cross-trip FK).

**source_ref:** `photo_link:<id>` (photo answer) > `turn:<id>` > `conv:<id>`.

**LAW 3:** imports only `trip_repository` + stdlib. Build-gated isolation test
fails if `chat_ws` / `prompt_composer` / `extract` / `memory_echo` / `llm_*` /
`safety` / `runtime71` ever appear.

**Pure:** no runtime71 mutation, no prompt dispatch, no extraction, no memoir
prose, no image inference. Reads the trip data layer, writes one candidate
note.

Result: `{captured, reason, note_id, trip_id, trip_region_id, trip_stop_id,
source_ref, scope}`. `reason` ∈ `meaningful_trip_answer`, `duplicate`,
`no_active_trip`, `no_person`, `trip_not_found`, `trip_not_owned`,
`not_trip_scoped`, `trivial_reply`.

16 tests green (`tests/test_trip_story_capture.py`).

## Step 1.5 — hardening (review 2026-07-08) — LANDED

1. **conv_id-only dedupe fixed.** Dedupe now keys **only** on a strong
   per-answer identity (`turn:<id>` or `photo_link:<id>`). `conv:<id>` is
   shared by every turn in a conversation, so it is stored for traceability
   but never triggers dedupe — two different answers in one conversation with
   no `turn_id` are both captured. Test: `test_conv_id_only_does_not_overdedupe`.
2. **photo-link trip-scope tightened.** `photo_link_id` only makes the turn
   trip-scoped if the link exists AND belongs to `active_trip_id`. A link from
   another trip does not scope the turn on its own. Test:
   `test_photo_link_from_other_trip_not_scoped`.

## Step 2 — chat wiring — LANDED 2026-07-08 (default-OFF)

Wired per WO-TRIP-LORI-CAPTURE-TO-TESTABLE-BETA-01. Default-OFF flag
`HORNELORE_TRIP_STORY_CAPTURE`; live behavior byte-identical until set.
Prior-turn trip-scope uses the **server-tracked** option: chat_ws stamps a
per-conversation `_TRIP_PREV_LORI[conv_id]` where the trip-interview-context
block is (not) injected, and the next narrator answer reads it — so capture
fires only after a genuinely trip-scoped Lori turn. As built:

### Flag
`HORNELORE_TRIP_STORY_CAPTURE=0` (default OFF, same posture as
`HORNELORE_TRIP_INTERVIEW_CONTEXT`). Live behavior byte-identical until set.
The gate helper lives in the service (`should_capture_turn(...)` /
`capture_for_turn(person_id, runtime71, user_text, params)`), so `chat_ws`
stays a one-call, non-fatal append — mirroring `context_block_for_turn`.

### Hook point (narrator turns only)
Inside `chat_ws._generate_and_stream_inner` (where the narrator's `user_text`,
`person_id`, `params["runtime71"]`, and the per-turn id already live). Run the
capture **after** the narrator turn is persisted (stable `turn_id`), wrapped
in `try/except` — a capture failure must never affect the chat turn. It is
fire-and-forget: no value is fed back into the prompt or the response.

### Gate (all required)
- flag ON, AND
- `runtime71.active_trip_id` present, AND
- `runtime71.travels_shelf_open` true, AND
- trip owned by `person_id` (service re-checks), AND
- the prior Lori turn was trip-scoped, AND
- reply is non-trivial (service checks).

### Prior-turn trip-scope signal (pick ONE at wiring time)
- **Preferred (explicit):** the frontend passes `previous_prompt_kind` (e.g.
  `"trip"`/`"photo"`) — and `photo_link_id` when the narrator is answering
  about a specific photo — on the narrator send. This matches the
  explicit-inputs ethos and needs no server-side turn memory. (A small
  `travels-shelf.js` change to stamp the last dispatched prompt kind — its own
  reviewed step, not part of this wiring.)
- **Alternative (server-tracked):** when trip-context was injected on the
  previous Lori turn (existing `[chat_ws][trip-context] injected` path), set a
  per-conv `last_lori_turn_trip_scoped` flag and read it on the next narrator
  turn. No FE change, but adds per-conv state.

### turn_id / source_ref strategy (locked by Step 1.5)
Step 2 **must always pass a unique narrator `turn_id`** so `source_ref` is
`turn:<id>` and the dedupe guard identifies one answer. `conv_id` may also be
passed for traceability but is never the dedupe key.

### Hard boundaries (unchanged)
- No auto-promotion (both flags stay 0).
- No runtime71 mutation, no prompt dispatch, no extraction.
- No Travel Doc UI changes in this step.
- Non-fatal: log `[chat_ws][trip-story-capture]` on capture/skip; never raise.
- No raw image inference; photo answers carry only `source_ref=photo_link:<id>`.

### Boundary tests (landed — tests/test_trip_story_capture.py)
1. flag off → never captures.
2. flag on, no active trip → no capture.
3. flag on, shelf closed → no capture.
4. wrong owner → no capture.
5. prior Lori turn not trip-scoped → no capture.
6. trivial reply → no capture.
7. meaningful trip answer → one candidate note, both flags 0, `source_type=lori`.
8. a capture-service exception does not break the chat turn (non-fatal path).

### After Step 2 lands
- Travel Doc "Story notes" surfaces these badged **"from Lori chat"** with
  edit / delete / **promote** controls (a later UI step — do not build with
  Step 2).
- Keep the "Lori context candidate — not used live yet" wording on the Travel
  Doc side until an operator has verified the captured notes look right.

## Later
- Sources need a dedicated `include_in_interview_context` (or
  `approved_for_lori_context`) flag before their summaries can enter Lori's
  prompt — do NOT reuse `include_in_memoir`.

## Beta batch — LANDED 2026-07-08 (WO-TRIP-LORI-CAPTURE-TO-TESTABLE-BETA-01)

- **Phase 1/2** chat_ws capture hook (narrator turns only, non-fatal,
  `[chat_ws][trip-story-capture]` log) + per-conv prior-turn trip-scope memory.
- **Phase 3** 15 boundary tests (flag/shelf/ownership/scope/trivial/dedupe/
  two-turns/photo/non-fatal/no-UI-import) — 43 capture tests green.
- **Phase 4** Travel Doc Story notes badge `from Lori chat` + source_ref line;
  In-memoir / Lori-context toggles + delete already present; Lori notes count
  in tile indicators.
- **Phase 5** `GET /api/trips/capture-status` (gated) + Bug Panel "Trip Story
  Capture" probe — DISABLED/INFO only, never RED.
- **Phase 6** stale-comment cleanup (this spec, trip_interview_context.py,
  travel-documenter.js header).
- **Phase 7** `docs/testing/TRIP_LORI_CAPTURE_LOCAL_TEST.md`.

Still pending: sources need their own `include_in_interview_context` flag;
optional Life Map trip photo projection (WO-TRIP-PHOTO-LIFEMAP-PROJECTION-01).
