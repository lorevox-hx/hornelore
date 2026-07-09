# Local manual test — Trip → Lori → Travel Doc capture loop

WO-TRIP-LORI-CAPTURE-TO-TESTABLE-BETA-01. This walks the full beta loop:
Travel Doc builds the trip → Travels shelf opens it for Lori → Lori asks a
trip-scoped question → narrator answers → the answer lands in Travel Doc as a
**candidate** story note (never auto-promoted).

## Environment

Set in `.env`, then restart the stack (Chris owns start/stop):

```
HORNELORE_TRIPS=1
HORNELORE_TRIP_INTERVIEW_CONTEXT=1
HORNELORE_TRIP_STORY_CAPTURE=1
```

Notes:
- `HORNELORE_TRIP_STORY_CAPTURE` default is **0**. With it off, nothing is
  captured (byte-stable).
- Capture's prior-turn "trip-scoped" signal is stamped where the trip
  interview-context block is injected, so **`HORNELORE_TRIP_INTERVIEW_CONTEXT`
  must be ON** for capture to fire in this loop.

## Steps

1. Restart the stack; wait the full ~4 min warmup.
2. Hard reload `http://localhost:8082/ui/hornelore1.0.html`.
3. Open a narrator (one who owns a trip — e.g. Christopher Todd Horne with the
   Spring 2026 trip).
4. Open the **Travel Doc** tab; the trip auto-opens and auto-selects.
5. Click **Talk with Lori** → confirm the Travels shelf opens the *same* trip
   ("Lori is now focused on this trip").
6. Confirm Lori asks a **trip-scoped** question (about a place on the route).
7. Answer **meaningfully** (a real sentence, not "yes"):
   > "We were tired when we landed, but Munich felt like the real start of the trip."
8. Return to the **Travel Doc → Story notes** tab for that stop/region/trip.
9. Confirm a new note appears badged **"from Lori chat"** with a small
   `source_ref` (e.g. `turn:…` or `photo_link:…`).
10. Confirm on the note: **In memoir = OFF**, **Lori context candidate = OFF**.
11. Flip **In memoir** ON. Open **Memoir preview** → the note now appears.
    (Before the flip it must NOT appear.)
12. Confirm Lori context does **not** include the note until you flip **Lori
    context candidate** ON (and only takes effect next turn).
13. **Trivial reply test:** ask Lori another trip question, answer "Yes." →
    confirm **no** new note is created.
14. **Photo test:** click a narrator-ready photo, answer about it
    ("That was the train station after we landed.") → confirm the new note's
    `source_ref` is `photo_link:<id>`.
15. **Close the Travels shelf** and keep chatting → confirm **no further
    capture** happens.

## What to watch (server log — `.runtime/logs/api.log`)

```
grep "\[chat_ws\]\[trip-story-capture\]" .runtime/logs/api.log | tail -20
```

Each narrator turn logs `captured=<bool> reason=<why> scope=<stop|region|trip>
note=<id|->`. Skip reasons: `flag_off`, `shelf_closed`, `no_active_trip`,
`trip_not_owned`, `not_trip_scoped`, `trivial_reply`, `duplicate`, `error`.

## Bug Panel

Open the Bug Panel → **Trip Story Capture** section shows the flag state
(DISABLED when off — never RED), the active trip / shelf-open, and the last
capture result. It probes `GET /api/trips/capture-status`.

## Pass criteria

- Meaningful trip answers create candidate `source_type=lori` notes with both
  promotion flags OFF.
- Trivial / non-trip-scoped / shelf-closed turns create nothing.
- A capture failure never breaks the chat turn.
- Notes reach the memoir / Lori context **only** after the operator flips a
  flag by hand.
- With `HORNELORE_TRIP_STORY_CAPTURE=0`, no notes are ever captured.
