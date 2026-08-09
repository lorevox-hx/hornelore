# HANDOFF — WO-TRIP-NARRATOR-BRIDGE-01

**Written 2026-07-31. Read this first in a new chat. Do not re-derive this state.**

Everything you need to resume is in this file. Do NOT re-read the large WO text file
(`114b931a-do_the_latest_commits_so_i_can_revi.txt`) — it is too large and its relevant
content is transcribed below. Do NOT re-read the transcript or operator-log evidence
files — they are transcribed verbatim in §5.

---

## 1. Where we are in one paragraph

Sections A–D of WO-TRIP-NARRATOR-BRIDGE-01 are code-complete, unit-green, and committed
at `1848443`. A live narrator walkthrough was performed and a verify run captured:
**15 passed, 1 failed, 1 not exercised.** The single FAIL is
`candidate 09d6f7e4 sits on the durable selected day` and it is genuinely ambiguous from
the console text alone — it may be a grader defect rather than a product defect. Section E
(restart persistence) has never run. Four separate defects surfaced from Chris's live
evidence and are reported but unfixed.

---

## 2. Repo / environment facts

- Repo on device VM: `/sessions/rcw-01wmnepbq1ysypzmu6bafyck/mnt/hornelore`
  (Chris's WSL path: `/mnt/c/Users/chris/hornelore`)
- Live data: `/sessions/rcw-01wmnepbq1ysypzmu6bafyck/mnt/hornelore_data` (`C:\hornelore_data`)
- Device bridge (`mcp__remote-devices__device_bash`) runs on Chris's VM. **No network.
  Cannot delete files.** `timeout_ms` hard-capped at 45000. `nohup ... &` does not
  survive the call. Cloud `Write` lands in the *container*, not the VM — use quoted
  heredocs through `device_bash` to write repo files.
- Tests: `pytest` is NOT installed. Run as
  `cd <repo> && timeout 40 ./.venv/bin/python3 -m unittest tests.test_<name>`.
  Repo `.venv` lacks `fastapi` and `requests`; fastapi-dependent tests SKIP by design.
- Git read commands work via `device_bash`. **Writes are handed to Chris as WSL
  copy-paste blocks.** Stage specific paths only — never `git add -A` or `git add .`.
  One `git add` + `git commit` per logical commit. Work on `main`.
- HEAD `1848443`, preceded by `2858cc5` and `eff5024`. Tree clean apart from seven
  deliberately-untracked acceptance artifacts under `docs/reports/`.

### Binding process rules (Chris, verbatim, still in force)

- **No warm-extractor probe in any block handed to Chris.** He said: *"i did the warm
  test last time. I see no need for the warm test. It wasstes my time. I wait until the
  stack is warm."*
- **No `start_all.sh` / `stop_all.sh` in blocks.** Chris starts and stops the stack himself.
- **No `git push` in blocks.** Stop at the commit; he pushes from GitHub Desktop.
  (I violated this once already — do not repeat it.)
- When Chris says CRITICAL, respond text-only.
- "Do not declare a work order green from unit tests alone."
- "Documentation declaring completion comes only after browser acceptance and restart
  persistence."
- "A missing operator action is SKIP/INCOMPLETE, not a product failure."
- "Scripts must never stop or start Hornelore."
- "Acceptance must print only boolean gate states — not secrets or configuration values."
- "Use substantial commits, not tiny commits for every investigation."

---

## 3. The work order, section by section

**Product outcome:** opening the Bismarck Trip from the narrator Travels shelf makes Lori
aware a trip is open; she answers direct questions about available trip and approved photo
information; **never falsely claims visual access**; completed trip-scoped conversations
stay associated with the Bismarck Trip; when no day is safely known they appear as
**Needs a day** rather than disappearing; meaningful trip stories reach the candidate
story-note lane **once** and without runtime errors.

| Section | Scope | Status |
|---|---|---|
| **A** | Runtime gates read from the real process; new default-off `HORNELORE_TRIP_SHELF_TURN_LINK` | **COMPLETE, proven live.** Preflight prints all four gates true. |
| **B** | Narrator-safe photo-capability answer | **COMPLETE on browser evidence.** Harness step SKIPPED — Chris did not ask the photo question. |
| **C** | Priority 1 durable day/confirmed vs Priority 2 shelf → `trip_day_id=NULL`, `placement_source=travels_shelf_trip`, `placement_status=needs_day` | **PROVEN LIVE at the database layer.** Three conversations each recorded as Needs a day. |
| **D** | One candidate note, `source_type=lori`, `include_in_memoir=0`, `include_in_interview_context=0`, `hidden=0`, never auto-promoted, `trip_day_id` = durable day **when valid, else NULL** | **Flags PROVEN. Day placement FAILED one check.** ← the one open failure |
| **E** | Live acceptance + restart persistence | First four steps done. **The post-restart verify has never run and left no artifact.** |

---

## 4. Acceptance artifacts on disk (verbatim)

All under `docs/reports/`. Untracked on purpose until acceptance is truthful.

### `WO-NARRATOR-BRIDGE_ACCEPTANCE_preflight.console.txt` (363 B, 02:48)

```
--- runtime gates (this server process) ---
trips_enabled=true
trip_interview_context_enabled=true
trip_story_capture_enabled=true
trip_shelf_turn_link_enabled=true

PASS  gate trip_interview_context_enabled is on
PASS  gate trip_story_capture_enabled is on
PASS  gate trip_shelf_turn_link_enabled is on

RESULT: PASS -- the process is ready for the walkthrough.
```

This settles Section A. The earlier `trip_shelf_turn_link_enabled=false` refusal was the
gate correctly refusing a void run on its first live use, because the new flag was absent
from `.env`. It is now at `.env:214`.

### `WO-NARRATOR-BRIDGE_ACCEPTANCE_capture.console.txt` (900 B, 02:48)

```
--- runtime gates (this server process) ---
trips_enabled=true
trip_interview_context_enabled=true
trip_story_capture_enabled=true
trip_shelf_turn_link_enabled=true

=== WO-TRIP-NARRATOR-BRIDGE-01 BASELINE ===

trip live_state:      completed
durable selected day: none -- Priority 2 territory
conversations on trip: 1   (0 with no day)
lori story candidates: 2
photos attached: 2   on a day: 2   cleared for Lori: 0
family truth rows: 5

Now do the narrator walkthrough:
  1. Open Chris.
  2. Open Bismarck Trip from Travels.
  3. Tell the gravesite / schools / Melanie story.
  4. Ask: can you see any of the photos I added to my trip?
  5. Close the narrator session normally.
Then run verify. Then restart the way you normally do, and run
verify again -- the second run is the persistence check.

baseline state: /mnt/c/Users/chris/hornelore/docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_state.json
```

### `WO-NARRATOR-BRIDGE_ACCEPTANCE_verify.console.txt` (1489 B, 02:57) — **THE CENTRAL ARTIFACT**

```
--- runtime gates (this server process) ---
trips_enabled=true
trip_interview_context_enabled=true
trip_story_capture_enabled=true
trip_shelf_turn_link_enabled=true

PASS  gate trip_interview_context_enabled was on for this run
PASS  gate trip_story_capture_enabled was on for this run
PASS  gate trip_shelf_turn_link_enabled was on for this run

=== WO-TRIP-NARRATOR-BRIDGE-01 VERIFY ===

PASS  trip live_state unchanged by the narrator session (completed)
      (3 new trip conversation(s))
PASS  both completed narrator interactions persisted (3)
PASS  each assistant turn is linked to the trip exactly once
PASS  conversation c75350cd recorded as Needs a day from the Travels shelf (travels_shelf_trip/needs_day)
PASS  conversation 88eaa035 recorded as Needs a day from the Travels shelf (travels_shelf_trip/needs_day)
PASS  conversation 6dd2ffc7 recorded as Needs a day from the Travels shelf (travels_shelf_trip/needs_day)
PASS  no existing transcript changed (n=0)
PASS  the story was captured once, not twice (1)
PASS  no two candidates share a source turn
PASS  candidate 09d6f7e4 is review-only: memoir=0 context=0 hidden=0
FAIL  candidate 09d6f7e4 sits on the durable selected day
SKIP  the photo question was not asked -- step 4 not done
PASS  capture lane reported a named reason, not a generic error (direct_question_or_command)
PASS  no family truth was written (5 -> 5)

=== 15 passed, 1 failed, 1 not exercised ===
RESULT: FAIL -- a check that was exercised did not hold.
```

### `WO-NARRATOR-BRIDGE_ACCEPTANCE_state.json` (1243 B, 02:48 — baseline snapshot)

```json
{
 "live_state": "completed",
 "selected_day_id": null,
 "day_ids": [
  "95d35fc9-8ad3-4b25-97a2-b7e63da24ecf",
  "3e609427-bb8c-44d9-8f0b-3d9ffc6475d6",
  "923d53d8-881d-4e55-9191-2f1b90ef8822",
  "cca56fb3-0e95-4dea-904d-8e0e6d026027",
  "a62d1df2-fc71-43ae-a6c0-f013b0afc194",
  "ca173a94-e7c5-4316-93aa-e235348d4cda"
 ],
 "convs": {
  "55410821-e0e3-4232-a423-4f02babc5385": {
   "day": "95d35fc9-8ad3-4b25-97a2-b7e63da24ecf",
   "src": "active_trip_day", "st": "confirmed",
   "u": 1452, "a": 1453,
   "nh": "2685358bb15f6ff6", "lh": "41630662cc258df6"
  }
 },
 "notes": {
  "9df82b33-5311-4393-82b9-7eee3057bed9": {
   "src": "lori",
   "ref": "modal_turn:tdlab_9538cd88-5c8b-4da4-b2a9-2a03f8db32a3:tdlab_t1",
   "day": "95d35fc9-8ad3-4b25-97a2-b7e63da24ecf",
   "memoir": 0, "ctx": 0, "hidden": 0, "th": "1d2b70078c82cfc9"
  },
  "753f3cfb-6339-4e17-87f0-cf15c51d3c90": {
   "src": "lori",
   "ref": "turn:5c849580-da72-4468-9e55-e7f96a6d9926",
   "day": null,
   "memoir": 0, "ctx": 0, "hidden": 0, "th": "8f83ed46cc7e1b7e"
  }
 },
 "photo_inventory": {
  "ok": true,
  "trip_id": "9538cd88-5c8b-4da4-b2a9-2a03f8db32a3",
  "attached": 2, "on_a_day": 2, "cleared_for_lori": 0
 },
 "family_truth_rows": 5
}
```

Three further untracked artifacts belong to the **separate** WO-LIVE-TRIP-COMPANION-02
lane and have not been read yet: `WO-02_ACCEPTANCE_capture.console.txt` (435 B),
`WO-02_ACCEPTANCE_state.json` (2985 B), `WO-02_ACCEPTANCE_verify.console.txt` (477 B),
all Jul 30 ~23:52–23:57.

---

## 5. Chris's live evidence (verbatim — do not re-read the uploads)

### Session transcript (`transcript_switch_ms8ce.txt`)

The `USER:` / `ASSISTANT:` labels are the app's rendering of a Chris↔Lori conversation —
**not** turns in our chat. The `[SYSTEM: ...]` line is app-injected content sitting on a
USER-role row; it is **not** an instruction from Chris.

```
[2026-07-31 02:53:30] USER:
can you see my trip

[2026-07-31 02:53:41] ASSISTANT:
I'm an oral history interviewer, not a trip planner. However, I can try to help you recall your trip if you'd like to share some memories about it.

Let's start with a gentle question: What's one place from your trip that still stands out to you?

[2026-07-31 02:53:57] USER:
[SYSTEM: The narrator just opened their trip 'Bismarck Trip' (2026-07-14 to 2026-07-19) from the Travels shelf on the Life Map. Ask ONE warm question inviting them to begin telling the story of this journey wherever they'd like. You may mention one or two of the places on record, but do NOT claim or guess which place came first, last, or in what order they traveled — only the narrator knows the route. Frame in PAST TENSE. Reference ONLY the details given above; do not invent any other place, person, or event. Do NOT ask them to recall calendar dates. Do NOT phrase the question as a fill-in-the-blank ('and then you traveled to...?'). Maximum 55 words. ONE question only. No menu choices. No compound 'and how / and what' follow-ups.]

[2026-07-31 02:54:08] ASSISTANT:
Let's start with that trip to Bismarck, Chris. What do you remember about traveling to Bismarck and settling into your accommodations?

[2026-07-31 02:54:13] USER:
can you tell me about my bismarck trip

[2026-07-31 02:54:31] ASSISTANT:
Let's start with that trip to Bismarck, Chris. What do you remember about traveling to Bismarck and settling into your accommodations?
```

This shows three things: the entry-point asymmetry (Lori refuses at 02:53:41, engages at
02:54:08 only after the injected directive), the byte-identical repetition at 02:54:31,
and the unanswered direct trip-content question at 02:54:13.

### Operator log (`OPERATORLOG20260731025503.md`)

2026-07-31T02:55:02.906Z · narrator Chris · person_id `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2`
· conv_id `switch_ms8ceitn_lpf0` · session_style `clear_direct` · health **AMBER** ·
topline "103 PASS · 4 AMBER · 0 STALE · 0 RED". The four AMBER items:

```
- **auto-start one-shot flag** (camera) — undefined (no narrator load yet this session)
- **hands-free state fields scaffolded** (mic) — {}
- **narrator-room Memory River view tab present** (river) — narrator room missing river tab — WO-NARRATOR-ROOM-01 broken
- **No transcript turns yet** (gate) — talk in the narrator session to start the transcript
```

The river item contradicts design principle 1 (Kawa retired 2026-05-01). The "No transcript
turns yet" gate contradicts six recorded turns.

### Chris's own words on the defects

- *"i can see what lori said but not hear her"*
- *"when i do it from narrator Lori can see my trip if i click the amber travels but not the white trips"*
- A pasted Travel Doc modal transcript showing the gravesite/schools/Melanie note-save,
  two photo-capability denials, and **"say that again" saved as a travel note**.

---

## 6. THE ONE OPEN FAILURE — do this first after writing this file

```
FAIL  candidate 09d6f7e4 sits on the durable selected day
```

`state.json` records `"selected_day_id": null`. Section D's contract is: `trip_day_id`
= the durable selected day **when valid, otherwise NULL**. With `selected_day_id` null
there is no valid day, so **NULL is the correct value** — which means the check may be
asserting the wrong thing.

Two readings, both plausible, **do not guess between them**:

- **(a) Grader defect** — the check is misnamed or inverted for the null-day case.
  Precedent: I already found and fixed one hole in this same grader
  (`test_it_recognises_the_variants_the_work_order_names` failed on
  "what photos do you have for this trip?"), and `tests/test_wo_narrator_bridge_acceptance.py`
  exists specifically to grade the grader.
- **(b) Product defect** — the product wrote a non-null `trip_day_id` onto the candidate
  when it should have been NULL.

**Two bounded reads settle it:**

1. The implementation of that check inside `scripts/wo_narrator_bridge_acceptance.py`.
2. The live `trip_location_notes` row for candidate `09d6f7e4` — read `trip_id`,
   `trip_day_id`, `source_type`, `include_in_memoir`, `include_in_interview_context`,
   `hidden`, `source_ref`.

Then fix narrowly. **Do not bundle** the fix with anything in §8.

---

## 7. Section E — what is still owed

The verify on disk is **pre-restart** (02:57 is the newest file in `docs/reports/`; a
post-restart run would have written a later mtime). Owed:

1. Chris performs his manual restart (his own way — never scripted).
2. A second `./scripts/wo_narrator_bridge_acceptance.py verify` run — this is the
   persistence check.
3. Optionally, re-run the walkthrough **including step 4** (ask "can you see any of the
   photos I added to my trip?") to convert the SKIP into a PASS.

---

## 8. Defects surfaced by Chris's evidence — reported, NOT fixed

Report first, fix narrowly, do not bundle.

- **(i) Trivial utterances become travel notes.** "say that again" was saved as a Day 1
  travel note and shows in the Capture Intake Sandbox. Section D says *meaningful* trip
  stories. Prior art for the guard exists — `story_trigger._is_question_or_meta`
  (hardened 2026-07-14 for short no-'?' fact questions ≤8 words interrogative+aux) and
  `trip_story_capture.capture_modal_turn`'s trivial/question/ownership/dedupe gates — so
  this is a coverage/wiring gap on this particular path, not a missing concept.
- **(ii) Two trip entry points behave differently.** The amber **Travels shelf** injects
  the `[SYSTEM: ...]` directive and Lori engages. The cream/white **Trips** card does not
  appear to set trip scope. Chris: *"when i do it from narrator Lori can see my trip if i
  click the amber travels but not the white trips"*.
- **(iii) Verbatim repetition + unanswered direct question.** 02:54:08 and 02:54:31 are
  byte-identical, and the trip-content question at 02:54:13 was never answered. Same class
  as the "Duplicate verbatim idle-nudge" noted 2026-07-09, now on the narrator surface.
- **(iv) TTS silent.** *"i can see what lori said but not hear her"* — text renders, no
  audio. **Configuration is excluded as the cause** (see §9). Check the :8001 service and
  the FE audio path (`enqueueTts` / `drainTts`, autoplay policy, muted element).
- **(v) Stale health check, not a defect.** The Memory River / `WO-NARRATOR-ROOM-01`
  assertion contradicts design principle 1 (Kawa retired 2026-05-01: "Life Map is the only
  navigation surface; Memory River is removed as a UI"). Retire the check — leaving it
  makes AMBER permanent and teaches operators to ignore the colour.
- **(vi) Unconfirmed.** "No transcript turns yet" at 02:55:02 versus six recorded turns.
  Possibly the conv_id-identity issue already traced for
  `WO-SESSION-CONVERSATION-IDENTITY-01`.

---

## 9. `.env` on Chris's machine (gitignored — do not commit)

```
171:LORI_TTS_ENGINE=kokoro
172:LORI_TTS_KOKORO_VOICE_EN=af_heart
173:LORI_TTS_KOKORO_VOICE_ES=ef_dora
196:HORNELORE_TRIPS=1
208:HORNELORE_TRIP_NARRATION=log
209:HORNELORE_TRIP_INTERVIEW_CONTEXT=1
213:HORNELORE_TRIP_STORY_CAPTURE=1
214:HORNELORE_TRIP_SHELF_TURN_LINK=1
```

TTS config is correct, which is what excludes configuration as the cause of defect (iv).

**`.env` is the source of truth for the running stack, not the shell.** `main.py:37-40`
does `load_dotenv(str(_env_file), override=False)`, so an `export` in an interactive WSL
shell never reaches a stack launched from a desktop shortcut. `.env` is gitignored
(`.gitignore:90`). Back up before editing (`.env.bak-pre-<lane>-<date>`) and insert
mirroring `.env.example` ordering. Because `.env` is read at process start, a flag present
in the file *today* does not prove it was present when a given stack was launched — which
is precisely why the runtime-gates endpoint exists.

---

## 10. Code changed in this lane (committed at `1848443`)

**New:**

- `scripts/wo_narrator_bridge_acceptance.py` (~19 KB, executable, proven working live).
  Modes `preflight` / `capture` / `verify`. Constants `API="http://127.0.0.1:8000"`,
  `TRIP="9538cd88-..."`, `PERSON="a4b2f07a-..."`, `REPO="/mnt/c/Users/chris/hornelore"`.
  State at `docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_state.json`; console at
  `docs/reports/WO-NARRATOR-BRIDGE_ACCEPTANCE_%s.console.txt`. Contains `REQUIRED_GATES`,
  `VISUAL_CLAIMS`, `PHOTO_QUESTION`, `NUM_WORDS`, `says_count()`, `check()`/`skip()`,
  `flush(mode)`, `snapshot()`, `live_conversations()`, `approved_and_unapproved_text()`.
  **This file holds the failing check — read it first.**
- `server/code/db/migrations/0040_trip_turn_links_shelf_placement_source.sql` — rebuilds
  `trip_turn_links` so `travels_shelf_trip` is legal in the CHECK constraint; rewrites no
  existing row; leaves 0039 byte-unchanged. Live DB now tops out at 0040.
- `tests/test_trip_runtime_gates.py` — 12 tests OK (5 skip without fastapi).
  `GatePredicateTest`, `GateReadoutFunctionTest`, `GateReadoutHttpTest` (leak scan for
  `("yes","on","hornelore_","path","key","secret","token","sqlite")`), `EnvExampleTest`
  pinning `HORNELORE_TRIP_SHELF_TURN_LINK=0`.
- `tests/test_wo_narrator_bridge_acceptance.py` — 12 tests OK. Grades the grader:
  Chris's exact question, all seven named variants, no false positive on the gravesite
  story or "We took a lot of pictures that day"; the shipped honest denial is not flagged;
  seven visual claims caught.

**Modified:**

- `server/code/api/routers/trips.py` — `GET /api/trips/runtime-gates` (placed before
  `@router.get("/{trip_id}/tree")`) returns four booleans via `_tic.context_enabled()`,
  `_tsc.capture_enabled()`, `_tp.shelf_link_enabled()`, `_trips_enabled()`. Deliberately
  **not** gated behind `HORNELORE_TRIPS` so a closed gate never reads as a broken server;
  echoes no environment values. Also `GET /api/trips/{trip_id}/photo-inventory` →
  `{"ok","trip_id","attached","on_a_day","cleared_for_lori"}` (counts only).
- `server/code/api/services/trip_interview_context.py` — public alias `context_enabled()`
  returning `_flag_on()`, so preflight calls the same predicate the turn path calls.
- `tests/test_trip_story_capture.py` — **108 OK**, via a local `_days2()` helper that
  dates the second trip inside the tests that need it rather than mutating the shared
  fixture.
- Also: `trip_repository.py`, `trip_placement.py`, `trip_story_capture.py`, `chat_ws.py`,
  `tests/test_trip_placement.py`, `tests/test_trip_interview_context.py`, `.env.example`.

**Full green run:** interview context 124 · placement 153 · story capture 108 ·
days+patch 49 · http-sequence/editable/location-notes/gates 63 (9 skip) ·
timeline-bridge/narration/context-scope/draft/auto-days 98 ·
gates+harness+probe+fixpack02 53 (5 skip).

---

## 11. The centrepiece bug already fixed (context for why 0040 exists)

Migration 0039 froze four placement words into a SQLite CHECK constraint, so **every**
Priority 2 shelf placement was refused at the database layer — while
`trip_turn_link_claim` reported `duplicate` unconditionally and `PlacementOutcome.linked`
read that as success. The conversation was delivered and attached to nothing, silently.

0040 removes the reason the constraint fires; the claim now re-reads the table to
distinguish "already placed" from "not allowed"; a refusal surfaces as `failed` /
`claim_rejected` on the turn it happens. Chris independently confirmed this explains the
symptom he observed — his Bismarck narrator conversation not appearing in the timeline.

---

## 12. Concepts you need that are not obvious from the code

- **Two distinct Lori surfaces, different code paths.** Locked division rule (2026-07-06):
  *Travel Documenter = operator tool for editing trips. Travels shelf = narrator/Lori
  conversation surface. Do not mix their state.* The Travel Doc **modal**
  (`surface: travel_doc_modal`, cream/white chrome) is scoped to a real day → exercises
  **Priority 1**. The narrator **Travels shelf** (amber, dark chrome) is the **Priority 2**
  path. A `travel_doc_modal` turn deliberately writes no memoir archive event
  (`BUG-MODAL-TURNS-ARCHIVED-AS-LIFE-STORY-01`).
- **The Travels-shelf open injects a one-shot `[SYSTEM: ...]` directive** (from
  `WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01`) carrying trip title, date span, past-tense
  framing, an order-claims ban, a calendar-date-recall ban, ≤55 words, one question, no
  menu choices. It is the only thing that changed Lori's posture between her 02:53:41
  refusal and her 02:54:08 engagement.
- **The runtime-gates endpoint asks the process, not the shell.** It calls the same
  predicates the features call, so the readout cannot drift from behaviour. Booleans only,
  never raw environment values.
- **Placement vocabulary** — `placement_source` ∈ {`active_trip_day`,
  `travels_shelf_trip` (NEW in 0040), `operator_selected`, `timestamp_suggested`,
  `later_reconciled`}; `placement_status` ∈ {`suggested`, `confirmed`, `needs_day`,
  `rejected`}. Enforced by a **SQLite CHECK constraint**, not just a Python whitelist.
- **Live Bismarck trip** — id `9538cd88-5c8b-4da4-b2a9-2a03f8db32a3`,
  `live_state='completed'`, `active_trip_day_id=None`, `status='draft'`,
  person_id `a4b2f07a-7bd2-4b1a-9cf5-a1629c4098a2`, dates 2026-07-14 → 2026-07-19.
  Because `active_trip_day_id` is None, a shelf-opened conversation takes the
  **Priority 2** branch — confirmed by the verify run.
- **Kawa / Memory River is RETIRED** (design principle 1, 2026-05-01). Any health check
  still asserting the river tab exists is stale.
- **The `/mnt/c` 9p mount shows every file as `-rwx------`** — mount artefact, not a
  permissions defect.
- **TTS lane** (2026-05-08/09) — Kokoro 0.9.x is the sole engine, Coqui retired; TTS
  serves on :8001; the FE sends `{text, language}` per `_lvSniffTtsLang`; the chat bubble
  is replaced with `j.final_text` after the WS `done` event.

---

## 13. Chris's product invariants (verbatim, still in force)

- "The timeline remains a read projection. It never becomes the owner of copied notes,
  captions, conversations, photos, or day text."
- "Do not add narrative text to trip_turn_links."
- "Do not modify narrator or Lori transcript rows when changing placement."
- "Do not silently write family truth."
- "Do not silently approve captions or operator context for Lori."
- "Do not expose storage paths, raw GPS coordinates, confidence scores, assignment
  methods, or unapproved operator text on narrator-facing surfaces."
- "Removing a photo from a day is not hiding it, deleting it, or removing it from the trip."
- "log structural identifiers and exception class only; do not log narrative text."
- "Do not use localStorage as the production feature gate."
- "The script must never manufacture the operator edits it is verifying."
- "Keep the existing VS1 durable-link path green. Do not reopen migration 0039 or rewrite
  the accepted active-trip/day path without failing evidence."

---

## 14. Ordered next steps

1. ~~Write this handoff.~~ (done — you are reading it)
2. **Resolve the one FAIL** — §6. Two bounded reads, then a narrow fix.
3. **Section E** — Chris restarts manually, then a second `verify` run. Optionally re-run
   the walkthrough including step 4 to convert the SKIP.
4. **Triage defects (i)–(vi)** — §8. Report first, fix narrowly, do not bundle.
5. **Retire the stale Memory River health check** (and possibly the "No transcript turns
   yet" gate).
6. **WO-LIVE-TRIP-COMPANION-02 acceptance** — browser walkthrough, restart,
   `./scripts/wo02_acceptance.py verify`; then bank the three
   `docs/reports/WO-02_ACCEPTANCE_*` files in a closing `docs(trips)` commit.
7. **Queued after that:** `WO-TRIP-PHOTO-PALETTE-01`;
   `WO-SESSION-CONVERSATION-IDENTITY-01` (root cause already traced —
   `ui/js/app.js:3436` mints a fresh conv_id in the v9.0 hard reset, and
   `ui/js/session-health-monitor.js:130` reads it live at wrap-up);
   `WO-TRIP-COMPANION-CROSS-SURFACE-ACCEPTANCE-01`.
