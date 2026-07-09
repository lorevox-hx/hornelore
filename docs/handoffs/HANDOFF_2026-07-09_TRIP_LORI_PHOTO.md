# Handoff — Trip ↔ Lori ↔ Travel Doc (2026-07-09)

Reviewable + shareable snapshot of the trip/Lori system: what is live, what
is committed, what is deferred, and the next direction (photo-context
enrichment).

**Baseline:** HEAD `5cfe56d`, working tree **clean**. **245 trip tests green.**

---

## 1. Executive summary

The full trip conversation loop is working end-to-end and committed:

> Travel Doc builds the trip → Travels shelf opens it for Lori → Lori gets
> approved trip context → Lori asks / answers trip questions → narrator (and
> now photos) feed answers back → answers land in Travel Doc as **candidate**
> story notes for operator review → operator promotes to memoir / Lori context.

Nothing auto-promotes: every captured note is `include_in_memoir=0` +
`include_in_interview_context=0` until an operator flips a flag by hand. Lori
never claims to see a photo.

---

## 2. What's live & committed (feature by feature)

| Feature | State | Where |
|---|---|---|
| **Trip story capture** (narrator answer → candidate `trip_location_notes`) | ✅ live, flag-gated | `services/trip_story_capture.py`, wired in `chat_ws.py` |
| **Note titles** from the prior Lori question | ✅ | `chat_ws` stamps `_TRIP_PREV_LORI[conv_id].lori_text` |
| **Skip direct-questions / meta** (`direct_question_or_command`) | ✅ | `trip_story_capture._is_question_or_meta` |
| **Direct trip answer** ("what do you know about my trip") | ✅ deterministic intercept | `trip_interview_context.direct_answer_for_turn`, `chat_ws` shim |
| **Direct answer place dedupe + Bavaria display fix** | ✅ | `trip_interview_context.compose_direct_answer` |
| **In-chat "+ Add trip photo"** button | ✅ needs live smoke | `hornelore1.0.html` + `travels-shelf.js` |
| **Photo card w/ thumbnail in chat** | ✅ needs live smoke | `travels-shelf.js _renderPhotoCard` |
| **Photo-linked capture** (`source_ref=photo_link:<id>`) | ✅ needs live smoke | `runtime71.active_photo_link_id` → `capture_for_turn` |
| **Short photo prompt** (no title/place echo) | ✅ | `travels-shelf.js _dispatchSafePrompt` |
| **Travel Doc "from Lori chat" review** (badge, source_ref, toggles, delete) | ✅ | `travel-documenter.js` |
| **`GET /api/trips/capture-status`** + Bug Panel probe | ✅ never-RED | `routers/trips.py`, `ui-health-check.js` |
| **Life Map trip meta** (cover photo + photo/story counts) | ✅ backend only | `trip_timeline_bridge.py` |
| **Bug Panel severity model** (RED only for live-session dangers; STALE tier) | ✅ | `session-health-monitor.js` |
| **Bug Panel "historical story candidates"** (renamed, collapsed, narrator-filtered) | ✅ | `bug-panel-story-review.js` |

**Live-verified in Chris's 2026-07-09 sessions:** direct trip answer fires
(`[chat_ws][trip-direct-answer] handled=true`), capture fires 3× (`captured=True
reason=meaningful_trip_answer`), the "+ Add trip photo" button appears, upload
+ "📷 Photo added" + Lori's photo question all fired. Bug Panel read
`103 PASS · 4 AMBER · 0 STALE · 0 RED`.

**Committed but NOT yet live-smoked** (landed after the last live run): photo
**thumbnail card** in chat, **photo-link** capture (`active_photo_link_id`),
short photo prompt, place **dedupe** / Bavaria fix. Run `TRIP_LORI_REAL_BETA_TEST.md`
Tests A + D to confirm.

---

## 3. How to run

`.env` (already set on the laptop):

```
HORNELORE_TRIPS=1
HORNELORE_TRIP_INTERVIEW_CONTEXT=1
HORNELORE_TRIP_STORY_CAPTURE=1
HORNELORE_TRIP_NARRATION=log     # route/structure dry-run (separate feature)
```

Restart stack → hard-reload `http://localhost:8082/ui/hornelore1.0.html`.
Watch: `tail -f .runtime/logs/api.log | grep -E "trip-story-capture|trip-direct-answer|trip-context"`.
Full script: `docs/testing/TRIP_LORI_REAL_BETA_TEST.md`.

---

## 4. Test coverage

245 trip tests green across `test_trip_story_capture`, `test_trip_interview_context`,
`test_trip_timeline_bridge`, `test_trip_location_notes`, `test_trip_sources`,
`test_trip_reorder_move`, `test_trip_patch`, `test_trip_editable_fixes`,
`test_travel_documenter_panel`, `test_trip_import`, `test_trip_narration_capture`.

Key guarantees under test: LAW-3 isolation (`trip_story_capture` /
`trip_interview_context` import no chat_ws/prompt_composer/extract/safety),
ownership enforcement, no auto-promotion, dedupe, non-fatal capture, direct
answer never invents order / never leaks raw sources or captions.

---

## 5. Known issues / limitations

1. **⚠️ `ui/hornelore1.0.html` is truncated in the repo.** It ends mid-function
   (~line 10057, no `</html>`) and has been that way across many commits back to
   `591dd33` — a pre-existing corruption (likely the 2026-07-06 mount incident),
   not from recent edits. The browser tolerates it, but the tail (a media
   lightbox `_lbDelete` + closing tags) is gone. **Recommend restoring the
   complete file from a Windows-side backup** and re-applying the small
   `+ Add trip photo` snippet. Do this before it bites something at the tail.
2. **Photo over-linking (minor).** `active_photo_link_id` persists until the trip
   is opened/closed or a new photo is uploaded, so multiple answers during an
   active photo discussion all link to that photo. Acceptable for beta (operator
   reviews notes); a true one-shot clear is a refinement.
3. **Lori still deflected a direct question once in an old transcript** before the
   deterministic intercept landed. The intercept (`5cfe56d` lineage) should fix
   it — confirm with Test A.
4. **Deferred phases** from `WO-TRIP-LORI-REAL-BETA-USABILITY-01`: silence-ladder
   respecting the active photo (Ph5), UI cleanup / oversized clock / focus mode
   (Ph11), and the whole metadata/OCR/caption lane (Ph6–8) — now folded into the
   new WO below.

---

## 6. Next direction — photo-context enrichment

Captured as **`WO-TRIP-PHOTO-CONTEXT-ENRICHMENT-FOR-LORI-01_Spec.md`** (repo
root). The core idea:

> Photo → metadata / OCR / geo / date enrichment → **operator approval /
> provenance** → Lori context → smarter questions → narrator answer → Travel
> Doc note.

Lori may use only **approved** context (caption, OCR text, broad place label,
date/event, cultural notes) and must never claim to see the image, never
expose raw GPS, never invent facts. For the Munich beer-menu photo, the goal
is Lori being able to ask: *"The approved text on this photo says Augustiner
Maibock — was this your first Munich meal?"* only after OCR/caption is approved.

**Recommended build order (lowest risk → highest ML):**

1. **Manual caption lane** (WO Ph5) — fastest path to Lori using approved photo
   text, zero ML. Highest value/lowest risk.
2. **EXIF/file metadata + filename-date guess** (Ph1) — deterministic; GPS stays
   private, broad label only after approval.
3. **Date/event enrichment** (Ph3) — stored calendar/holiday lookup, approval-gated.
4. **OCR draft + approval** (Ph4) — needs an OCR engine; draft-only until approved.
5. **Reverse-geocode broad place** (Ph2), **cultural suggestions** (Ph6).
6. **Feed approved context into `trip_interview_context`** (Ph7) + **better
   question generation** (Ph8) + **direct factual answers** (Ph9).

All of it flows through the existing `trip_interview_context` (read, LAW-3
isolated) and `trip_story_capture` (write) — the enrichment adds
**approval-gated fields**, it does not bypass the current safety posture.

---

## 7. Commit history (this arc)

```
5cfe56d fix(trips): dedupe + normalize place labels in direct trip answer
73083e4 feat(trips): show uploaded photo in chat + anchor it for photo-linked capture
94def10 chore(trips): real beta test script + clarify historical story backlog
f0913ac feat(trips): add in-chat trip photo upload for Lori sessions
b2b1547 fix(trips): answer direct trip questions from approved context (deterministic intercept)
91099ed fix(trips): trip-context block answers direct 'what do you know about my trip'
7057e7f feat(trips): project trip photo/story counts to Life Map
3143e1b fix(trips): polish Lori trip capture titles and skip direct questions
3dc2b78 feat(trips): wire Lori trip answer capture for local beta testing
7e97505 feat(trips): trip_story_capture Step 1 + hardening + Step 2 spec
```

## 8. File map

- **Backend services:** `trip_story_capture.py` (capture), `trip_interview_context.py`
  (read context + direct answer), `trip_timeline_bridge.py` (Life Map meta),
  `trip_repository.py` (data), `trip_narration_capture.py` (route/structure),
  `trip_photo_clustering.py`, `trip_import.py`, `trip_memoir_docx.py`.
- **Routers:** `routers/trips.py` (gated `HORNELORE_TRIPS`), `routers/chat_ws.py`
  (capture hook + direct-answer intercept + prior-turn memory).
- **Frontend:** `travels-shelf.js` (narrator shelf + in-chat photo),
  `travel-documenter.js` (operator Travel Doc), `app.js` (runtime71),
  `bug-panel-story-review.js`, `ui-health-check.js`, `session-health-monitor.js`.
- **Specs/docs:** `WO-TRIP-*_Spec.md`, `BUG-LORI-TRIP-DIRECT-QUESTION-DODGE-01_Spec.md`,
  `docs/testing/TRIP_LORI_REAL_BETA_TEST.md`, this handoff.
