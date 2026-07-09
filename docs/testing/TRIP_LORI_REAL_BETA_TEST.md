# Real-user beta test — Trip + Lori (one script)

WO-TRIP-LORI-REAL-BETA-USABILITY-01. This is the single script to follow when
powering up for a real narrator session with trips.

## Environment (`.env`, then restart the stack)

```
HORNELORE_TRIPS=1
HORNELORE_TRIP_INTERVIEW_CONTEXT=1
HORNELORE_TRIP_STORY_CAPTURE=1
```

Restart, then hard-reload `http://localhost:8082/ui/hornelore1.0.html`.

Watch the log the whole time:

```
tail -f .runtime/logs/api.log | grep -E "trip-story-capture|trip-direct-answer|trip-context"
```

## Test A — direct trip answer

1. Open **Chris** as narrator.
2. Open the **Spring 2026** trip; click **Talk with Lori**.
3. Ask: **what do you know about my trip**

Expected:
- Lori answers with the trip name, dates, and the places on record.
- She does **not** deflect ("where would you like to continue", "let's start
  again").
- Log shows `[chat_ws][trip-direct-answer] handled=true`.
- **No** story note is captured for this direct question.

## Test B — normal story capture

1. Let Lori ask a trip question.
2. Answer with a real memory (a full sentence).

Expected:
- Log: `[chat_ws][trip-story-capture] captured=True reason=meaningful_trip_answer`.
- Travel Doc → Story notes shows a note badged **"from Lori chat"**, titled
  with Lori's question, both promotion flags OFF.

## Test C — direct question skip

Ask: **what can you tell me about the weather story**

Expected:
- Lori answers honestly from known context or says she doesn't know it yet.
- Capture log: `reason=direct_question_or_command`; **no** note created.

## Test D — in-chat photo upload

1. With the trip open, click **+ Add trip photo** in the chat footer.
2. Upload a Germany/Munich photo.
3. Lori asks you to describe it (she does **not** claim to see it).
4. Answer with what you remember.

Expected:
- Photo attaches to the active trip (`narrator_ready=true`).
- Log: `[chat_ws][trip-story-capture] captured=True … source=photo`
  (the answer carries `source_ref=photo_link:<id>`).
- Travel Doc shows the linked note + the photo.
- The button is only visible while a trip is open on the shelf.

## Test E — Travel Doc photo upload

1. Open Travel Doc.
2. Add a photo at trip/stop level (existing upload controls).
3. Confirm the photo appears and photo counts update.

## Test F — Life Map card *(backend ready; FE card is a later phase)*

Trip timeline meta now carries `cover_photo_id`,
`narrator_ready_photo_count`, `memoir_photo_count`, `story_note_count`,
`promoted_story_note_count`. The Life Map trip-card render that displays them
is not built yet — for now verify the meta via the DB/timeline read if needed.

## Test G — Bug Panel

Expected:
- No false RED (severity model: only live-session dangers are RED).
- "Historical unreviewed story candidates — not live Lori context" is
  **collapsed** by default and filtered to the active narrator.
- "Trip Story Capture" section shows the flag + last capture result.

## Known limitations (this batch)

- In-chat photo upload attaches at **trip level** (clustering places it);
  direct stop-level attach mid-chat is a refinement.
- Life Map trip-**card** front-end rendering (Phase 5) not built yet.
- Travel Doc photo-upload affordances (Phase 3) and photo-linked note review
  polish (Phase 4) are the next batch.
- `ui/hornelore1.0.html` has a **pre-existing truncated tail** in the repo
  (ends mid-function, no `</html>`) across many prior commits — flagged
  separately; recover from a complete backup when convenient.
