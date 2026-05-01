# PARENT-SESSION-READINESS-V1 — Manual Test Pack

**Status:** v1 · 2026-05-01
**Owner:** Chris
**Purpose:** Lock down the user-facing UI before any live session with Kent or Janice. Ten tests. If all ten PASS, the system is parent-ready. If any one FAILs, parent sessions are blocked until that test passes.
**Audience:** Chris today, anyone in the future running regression on the same scope.

---

## Why this pack exists

The 2026-05-01 live test on Janice exposed real product bugs (truth-pipeline corruption, cross-narrator state leak, operator controls visible to narrator, broken Today mode). WO-PARENT-SESSION-HARDENING-01 is the build-side fix for all of them. This test pack is the **proof-side** — observable, repeatable evidence that each fix actually works in the running system.

The pack covers Phases 1–6 of WO-PARENT-SESSION-HARDENING-01 plus the four locked design principles (no dual metaphors / no operator leakage / no system-tone outputs / no partial resets). It does **not** cover Phase 7 polish or Phase 8 mode consolidation — those land in a v2 of this pack later.

## How to use this pack

1. Run the **Preconditions** once at the start of a session.
2. Run each test in order, top to bottom, **using a dedicated test narrator per test** (do not reuse).
3. Fill in the RECORD block under each test as you go.
4. At the end, fill in the **Final summary** and read the roll-up gate.

Each test should take 5–10 min. The full pack ~60–90 min once.

## Pass / Amber / Fail rules

- **PASS** — every Expected line is observed exactly. No console errors related to the test.
- **AMBER** — primary expectation met, but a non-blocking secondary detail is off (e.g., Lori's wording is slightly clinical but the structural test passes). Note in the test's RECORD what was AMBER.
- **FAIL** — any Expected line is not observed, OR a hard stop condition fires.

## Hard stop conditions (RED — abort the session if you see any of these)

```
- Bad birthplace value writes into personal.placeOfBirth (truth, not candidate).
- Bad birthOrder value writes into personal.birthOrder (truth, not candidate).
- Rejected text appears in Peek at Memoir as a confirmed fact.
- Life Map is missing on cold start in any session style.
- Life Map era buttons go visually-active-but-behaviorally-dead (stuck).
- Lori claims she cannot tell the date when device_context is in the prompt.
- Operator controls (Return-to-Operator, Reset Identity, etc.) appear in narrator flow.
- Cross-narrator data appears under the wrong narrator after switching.
- DB lock events increment during a normal session turn.
```

If any RED condition fires: **stop the test, write the symptom in the RECORD, and report**. Do not continue.

---

## Live UI naming (verified 2026-05-01 from `localhost:8082/ui/hornelore1.0.html`)

The current Hornelore UI uses these visible labels. Tests below use these names verbatim.

| Surface | Label |
|---|---|
| Shell tabs (header) | `Operator` · `Narrator Session` · `Media` |
| Top-right buttons | `Mic` · `Cam` · `Bug` · ⚙️ (settings) |
| Top-center pills (Lori interaction posture / `memoryMode`) | `Life Story` · `Memory Exercise` · `Companion` |
| Active posture indicator (right of top pills) | `• Life Story` (or active mode) — shows `lv80PostureBadge` effective posture |
| Active narrator chip (header) | `[Initials] [Name] ▼ Choose a narrator` |
| Operator panel section | `SESSION READINESS` (with `Session: GREEN/AMBER/RED` badge) |
| Operator panel section | `SESSION HEALTH` (status: `Ready` / `Ready with notes` / etc.) |
| Operator action buttons | `Ready for Session` · `Wrap Up Session` · `Open Full Bug Panel` |
| Operator handoff | `Enter Interview Mode` (top button) · `Start Narrator Session` (style picker bottom) |
| Style picker tiles (operator panel) | `Questionnaire First` · `Clear & Direct` · `Warm Storytelling` · `Companion` |
| Narrator switcher popover | Title: `Narrators` |
| Narrator switcher cards | `[Open]` · `[Delete]` buttons; `TEST` or `FAMILY` tag |
| New-narrator path | Bottom of narrator switcher: `Choose how you'd like to begin` row, with trainer-seed buttons `Questionnaire First` · `Clear & Direct` · `Warm Storytelling`. **There is no separate "+ Add Test Narrator" button** — clicking a trainer-seed button creates a new test narrator pre-seeded with that interview style. |
| Narrator-room right rail | `Bio Builder` (popover) · `Peek at Memoir` (popover) |
| Bio Builder tabs | `Questionnaire` · `Candidates` · others |
| Bio Builder header | `Reset Identity` button (top-right of popover) |

**Two-axis behavior model (verified from source):**

Lori's behavior is controlled by TWO independent axes. Tests in this pack work within `Life Story` posture only — Memory Exercise and Companion are out of scope for v1.

- **Lori interaction posture (`memoryMode`)** — set via top-center pills:
  - `life_story` = biography interview, full extraction, memoir active *(default — used for all tests in this pack)*
  - `memory_exercise` = gentle recall prompts, limited extraction, no pressure
  - `companion` = social presence, no extraction, no interview agenda
- **Interview style (`sessionStyle`)** — set via the operator-panel style picker tiles, WITHIN the chosen posture:
  - `Questionnaire First` · `Clear & Direct` · `Warm Storytelling` · `Companion` (style)

The `• Life Story` indicator to the right of the top pills is the EFFECTIVE posture badge — it can differ from selection when auto-routing overrides for non-memoir concerns or safety.

**Bug Panel access** — there are two entry points to the same popover (`#lv10dBugPanel`):

- Top-right `Bug` button — global, always available
- Operator panel `Open Full Bug Panel` button (in the SESSION HEALTH section, alongside `Ready for Session` and `Wrap Up Session`)

Either suffices for tests below. The pack uses `Open Full Bug Panel` since it lives in operator context.

---

## Preconditions (one-time setup at the start of a test session)

1. Stack is up. From the repo: `./scripts/start_all.sh` (or whatever the operator's start path is).
2. Wait for full warmup — about 4 minutes from cold. HTTP listener comes up in ~60–70s; LLM weights + extractor warmup take another 2–3 min.
3. Open Chrome to `http://localhost:8082/ui/hornelore1.0.html`.
4. Press `Ctrl + Shift + R` to hard-refresh.
5. Press `F12` to open DevTools.
6. Click the **Console** tab in DevTools.
7. Click the 🚫 icon (or `Ctrl + L`) to clear the console.
8. Confirm header shows three shell tabs: `Operator | Narrator Session | Media`. The `Operator` tab is the default. If you're on a different tab, click `Operator`.
9. Confirm the top-center Lori posture pills show **`Life Story`** as selected (highlighted). All tests in this pack run in Life Story posture. If `Memory Exercise` or `Companion` is selected, click `Life Story` to switch back.
10. Confirm the `• Life Story` indicator to the right of the pills also reads `Life Story` (the effective posture matches the selection — if it shows something else, auto-routing is overriding; document and continue).
11. In the operator panel, click **Ready for Session**.
12. Wait for the `SESSION READINESS` badge to settle. Expected: `Session: GREEN` or `Session: AMBER`. RED is a hard stop.
13. Click **Open Full Bug Panel**. Glance for any RED or AMBER findings unrelated to the tests below. Note any standouts. Close or move the Bug Panel so it doesn't block operator controls.

If any precondition fails: stop, fix, restart from step 1.

---

## Reusable steps (each test references these by ID)

### BOOT
Steps 1–13 of Preconditions. Run once per test session, not per test.

### ADD-NARRATOR(`<style>`)
The narrator-creation flow seeds a NEW narrator pre-tagged with an interview style.

1. Click the **active narrator chip** in the header (top-left, shows current narrator name + ▼).
2. The `Narrators` popover opens.
3. Scroll to the bottom of the narrator list to find the **Choose how you'd like to begin** row.
4. Click one of the three trainer-seed buttons matching `<style>`:
   - `Questionnaire First` — for tests that exercise the QF intake flow (TEST-01 through TEST-06, TEST-10)
   - `Clear & Direct` — for tests that exercise the chat/Life Map flow without the QF walk (TEST-07, TEST-08, TEST-09)
   - `Warm Storytelling` — not used in this v1 pack
5. The popover closes. The header chip updates to show the new test narrator's auto-generated name.
6. Capture that auto-generated name into the test's RECORD block under `Narrator name:` (so anyone can find this narrator later via the narrator switcher).

**Notes for testers:**
- The current UI does NOT prompt for a custom narrator name. Each trainer-seed click creates a uniquely-named test narrator. Multiple clicks of the same seed button create multiple distinct narrators.
- Test narrators carry a `TEST` tag in the switcher (vs. `FAMILY` for production narrators like Kent / Janice).
- Do not delete a test narrator until you've finished the entire pack run — some tests reference earlier narrators.

### SESSION-START
1. Confirm the operator panel's `SESSION READINESS` shows GREEN or AMBER.
2. Click **Ready for Session** if you haven't already in this session.
3. Click **Enter Interview Mode** (top operator-panel button) OR **Start Narrator Session** (bottom of style picker — same destination).
4. Confirm the narrator room opens (`Narrator Session` shell tab now active).

### INTAKE(`<name>`, `<dob>`, `<place>`, `<order>`)
1. Wait for Lori's first intake question.
2. When she asks for the narrator's name, type `<name>` and click Send.
3. When she asks for date of birth, type `<dob>` and click Send.
4. When she asks for place of birth, type `<place>` and click Send.
5. When she asks for birth order, type `<order>` and click Send.

### CHECK-CONSOLE(`<pattern>`)
1. Click DevTools Console tab.
2. Visually scan recent log lines for `<pattern>`.
3. Record YES (saw it) / NO (didn't).

### CHECK-BB-FIELD(`<section>.<field>`)
1. Click **Bio Builder** in the operator UI.
2. Click the **Questionnaire** tab.
3. Locate `<section>.<field>` (e.g., personal.placeOfBirth).
4. Record the value exactly, or `<empty>` if blank.
5. Click **Candidates** tab. Note if anything related is sitting in the queue.
6. Close Bio Builder.

### CHECK-PEEK-MEMOIR(`<phrase_to_search_for>`)
1. Click **Peek at Memoir**.
2. Read each era section.
3. Record YES (phrase found as a confirmed fact) / NO (phrase absent or only in candidate-style language).
4. Close Peek at Memoir.

### CHECK-DB-LOCKS
1. From a terminal: `grep "database is locked\|sqlite.*locked\|OperationalError" /mnt/c/hornelore_data/logs/api.log | tail -20`
   (path may differ — use `.runtime/logs/api.log` if that exists)
2. Record the count of lines (or 0).

### WRAP
1. Click **Wrap Up Session**.

---

## TEST-01 — Clean Control

**What it proves:** Clean intake values save normally end-to-end. No false rejections. The validator does not over-fire on legitimate place names / birth-order labels.

**Setup:** ADD-NARRATOR(`Questionnaire First`)

**Steps:**
1. Capture the auto-generated narrator name from the header chip into RECORD.
2. SESSION-START
3. INTAKE(`Mary Test`, `March 22, 1931`, `Montreal, Quebec, Canada`, `youngest`)
3. Stop typing. Don't keep chatting.
4. CHECK-CONSOLE(`[bb-drift] qf_walk validation REJECTED`)
5. CHECK-BB-FIELD(`personal.fullName`)
6. CHECK-BB-FIELD(`personal.dateOfBirth`)
7. CHECK-BB-FIELD(`personal.placeOfBirth`)
8. CHECK-BB-FIELD(`personal.birthOrder`)
9. CHECK-PEEK-MEMOIR(`Mary Test, born March 22, 1931 in Montreal, Quebec, Canada`)
10. CHECK-DB-LOCKS
11. WRAP

**Expected:**
- Console rejection log: NO (clean values must NOT be rejected)
- personal.fullName = `Mary Test`
- personal.dateOfBirth = `1931-03-22` (or normalized equivalent)
- personal.placeOfBirth = `Montreal, Quebec, Canada` (or normalized equivalent)
- personal.birthOrder = `youngest`
- Peek at Memoir Earliest Years shows the clean intake values
- DB lock delta = 0

**RECORD:**
```
Narrator name: ___
Console rejection log seen: ___
personal.fullName actual: ___
personal.dateOfBirth actual: ___
personal.placeOfBirth actual: ___
personal.birthOrder actual: ___
Peek at Memoir Earliest Years: ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-02 — Reject placeOfBirth Narrative

**What it proves:** The Phase 1.1 value-shape gate blocks past-tense narrative text from landing in `personal.placeOfBirth`. The Janice 2026-05-01 smoking-gun string MUST be caught.

**Setup:** ADD-NARRATOR(`Questionnaire First`)

**Steps:**
1. Capture the auto-generated narrator name from the header chip into RECORD.
2. SESSION-START
3. When Lori asks for name, type `BadPlace Test` and click Send.
3. When Lori asks for date of birth, type `March 22, 1931` and click Send.
4. When Lori asks for place of birth, type **exactly**: `My dad worked nights at the aluminum plant.`
5. Click Send. Stop. Do not answer another intake question.
6. CHECK-CONSOLE(`[bb-drift] qf_walk validation REJECTED personal.placeOfBirth`)
7. CHECK-BB-FIELD(`personal.placeOfBirth`)
8. CHECK-PEEK-MEMOIR(`My dad worked nights at the aluminum plant`)
9. CHECK-DB-LOCKS
10. WRAP

**Expected:**
- Console shows `[bb-drift] qf_walk validation REJECTED personal.placeOfBirth reason=past_tense_narrative_verb` (or similar reason)
- personal.placeOfBirth = `<empty>` (NOT the polluted string)
- Peek at Memoir does NOT show "My dad worked nights at the aluminum plant" as birthplace (it's allowed to appear as a candidate or in transcript notes; it must NOT appear as a confirmed fact)
- DB lock delta = 0

**RECORD:**
```
Console rejection log seen: ___
personal.placeOfBirth actual: ___
Candidate visible (informational): YES / NO
Peek at Memoir contains phrase as birthplace: ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-03 — Reject birthOrder Complaint

**What it proves:** The Phase 1.1 value-shape gate blocks resistance/complaint text from landing in `personal.birthOrder`. The other Janice smoking-gun string MUST be caught.

**Setup:** ADD-NARRATOR(`Questionnaire First`)

**Steps:**
1. Capture the auto-generated narrator name from the header chip into RECORD.
2. SESSION-START
3. INTAKE(`BadOrder Test`, `March 22, 1931`, `Montreal, Quebec, Canada`, `I just told you something you ignored.`)

   (i.e., name + dob + place clean; birthOrder is the rejected string)
4. After the birthOrder Send, stop. Do not keep chatting.
5. CHECK-CONSOLE(`[bb-drift] qf_walk validation REJECTED personal.birthOrder`)
6. CHECK-BB-FIELD(`personal.birthOrder`)
7. CHECK-PEEK-MEMOIR(`I just told you something you ignored`)
8. CHECK-DB-LOCKS
9. WRAP

**Expected:**
- Console shows `[bb-drift] qf_walk validation REJECTED personal.birthOrder reason=second_person_pronoun` (or `first_person_narrative_start` or `past_tense_narrative_verb` — any of those three is acceptable; the string trips multiple rules)
- personal.birthOrder = `<empty>`
- Peek at Memoir does NOT show "I just told you something you ignored" as birth order
- DB lock delta = 0

**RECORD:**
```
Console rejection log seen: ___
personal.birthOrder actual: ___
Candidate visible (informational): YES / NO
Peek at Memoir contains phrase as birth order: ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-04 — Reject fullName First-Person

**What it proves:** The Phase 1.1 value-shape gate blocks first-person narrative ("I am...", "My name is...") from landing as a literal fullName. Tests rule 5 (first-person sentence start).

**Setup:** ADD-NARRATOR(`Questionnaire First`)

**Steps:**
1. Capture the auto-generated narrator name from the header chip into RECORD.
2. SESSION-START
3. When Lori asks for name, type **exactly**: `I think my name is whatever you say it is.`
4. Click Send. Stop.
5. CHECK-CONSOLE(`[bb-drift] qf_walk validation REJECTED personal.fullName`)
6. CHECK-BB-FIELD(`personal.fullName`)
7. CHECK-PEEK-MEMOIR(`I think my name is`)
8. CHECK-DB-LOCKS
9. WRAP

**Expected:**
- Console shows `[bb-drift] qf_walk validation REJECTED personal.fullName reason=first_person_narrative_start` (or `second_person_pronoun` for "you say"; either valid)
- personal.fullName = `<empty>`
- Peek at Memoir does NOT show the rejected string as the narrator's name
- DB lock delta = 0

**RECORD:**
```
Console rejection log seen: ___
personal.fullName actual: ___
Peek at Memoir contains phrase as name: ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-05 — Reset Identity Clears All Identity Surfaces

**What it proves:** Phase 1.2 — Reset Identity now also clears the projection layer (6 identity field paths) AND drops pending identity suggestions AND clears the localStorage projection draft. No partial resets.

**Setup:** ADD-NARRATOR(`Questionnaire First`) → capture name into RECORD

**Steps:**
1. SESSION-START
2. INTAKE(`Reset Test`, `April 5, 1945`, `Boise, Idaho`, `oldest`)
3. Confirm BB Questionnaire shows the four values (CHECK-BB-FIELD on each).
4. Click **Reset Identity** (in the Bio Builder header).
5. In the confirmation dialog, read what it says will be cleared. **It must list:**
   - Wipe bb.questionnaire.personal
   - Clear state.profile.basics identity fields
   - Clear interview projection entries for the 6 identity paths
   - Drop any pending identity suggestions
   - Clear lorevox_proj_draft_<pid> from localStorage
   - PATCH the backend person row
   - Re-fire identity onboarding
6. Click OK.
7. CHECK-CONSOLE(`[bb-reset-identity] starting reset for pid=`)
8. CHECK-CONSOLE(`[bb-reset-identity] projection cleared:`)
9. CHECK-CONSOLE(`[bb-reset-identity] cleared localStorage`)
10. CHECK-CONSOLE(`[bb-reset-identity] PATCH person cleared DOB+POB`)
11. CHECK-CONSOLE(`[bb-reset-identity] complete`)
12. CHECK-BB-FIELD(`personal.fullName`)
13. CHECK-BB-FIELD(`personal.dateOfBirth`)
14. CHECK-BB-FIELD(`personal.placeOfBirth`)
15. CHECK-BB-FIELD(`personal.birthOrder`)
16. CHECK-PEEK-MEMOIR(`Reset Test`)
17. CHECK-PEEK-MEMOIR(`Boise`)
18. WRAP

**Expected:**
- Confirmation dialog lists all 7 clears (lines 5a–g above)
- All 5 console markers fire (steps 7–11)
- All 4 BB identity fields = `<empty>` after reset
- Peek at Memoir Earliest Years shows "(no entries yet)" — the prior intake values are gone

**RECORD:**
```
Confirmation dialog listed all 7 clears: YES / NO (note any missing)
Console: starting reset: ___
Console: projection cleared: ___
Console: cleared localStorage: ___
Console: PATCH person: ___
Console: complete: ___
fullName after reset: ___
dateOfBirth after reset: ___
placeOfBirth after reset: ___
birthOrder after reset: ___
Peek shows "Reset Test" anywhere: ___
Peek shows "Boise" anywhere: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-06 — Cross-Narrator State Isolation

**What it proves:** Switching from one narrator to another does NOT leak state — no Janice data shows under Kent, no softened-mode posture from one carries into the other.

**Setup:**
1. ADD-NARRATOR(`Questionnaire First`) → capture name as `Narrator06A` into RECORD
2. ADD-NARRATOR(`Clear & Direct`) → capture name as `Narrator06B` into RECORD

(Two narrators created. Narrator06B is selected after step 2 — switch back to Narrator06A for step 1 of the test.)

**Steps:**
1. Switch to `Test06A Janice-like` (click in narrator switcher).
2. SESSION-START
3. INTAKE(`Janice Like`, `August 30, 1939`, `Spokane, Washington`, `youngest`)
4. CHECK-BB-FIELD(`personal.fullName`) — confirm it's `Janice Like`.
5. CHECK-PEEK-MEMOIR(`Janice Like`) — confirm her name appears.
6. WRAP.
7. Switch to `Test06B Kent-like` via narrator switcher.
8. CHECK-BB-FIELD(`personal.fullName`) — should be `<empty>` (Kent has no intake yet).
9. CHECK-PEEK-MEMOIR(`Janice Like`) — Kent's memoir must NOT contain the string "Janice Like".
10. CHECK-PEEK-MEMOIR(`Spokane`) — Kent's memoir must NOT contain the string "Spokane".
11. SESSION-START on Kent.
12. INTAKE(`Kent Like`, `April 4, 1936`, `Stanley, North Dakota`, `oldest`)
13. CHECK-BB-FIELD(`personal.fullName`) — confirm Kent's name is `Kent Like`.
14. CHECK-PEEK-MEMOIR(`Janice Like`) — must STILL not appear.
15. CHECK-PEEK-MEMOIR(`Spokane`) — must STILL not appear.
16. CHECK-DB-LOCKS
17. WRAP

**Expected:**
- Kent's BB.fullName starts empty when switched to (no Janice carryover)
- Kent's Peek at Memoir never contains Janice's data at any point
- Kent's intake saves cleanly with his own values
- DB lock delta = 0 across the whole test
- No console errors during narrator switch

**RECORD:**
```
Janice intake saved correctly: ___
Kent on switch: empty start: ___
Kent peek (before intake) contains "Janice Like": ___
Kent peek (before intake) contains "Spokane": ___
Kent intake saved correctly: ___
Kent peek (after intake) contains "Janice Like": ___
Kent peek (after intake) contains "Spokane": ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-07 — Life Map Cold-Start

**What it proves:** Life Map renders on the right immediately on cold-start in `Questionnaire First`. No mode-switch dance required (the 2026-05-01 reproducer).

**Setup:** ADD-NARRATOR(`Questionnaire First`) → capture name into RECORD

**Steps:**
1. SESSION-START
2. As soon as the narrator room opens, look at the right side of the screen.
3. Confirm the **Life Map** panel is visible (era buttons: Earliest Years, Early School Years, Adolescence, Coming of Age, Building Years, Later Years, Today).
4. Confirm there is NO Memory River tab anywhere in the narrator room (it should be removed per the 2026-05-01 retirement decision).
5. Confirm no mode-switch was required to reveal the Life Map.
6. WRAP

**Expected:**
- Life Map visible on cold start: YES
- All 7 era buttons present
- No Memory River UI anywhere

**RECORD:**
```
Life Map visible on cold start: ___
All 7 era buttons present: ___
Memory River UI present anywhere: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-08 — Life Map Era Cycle

**What it proves:** All 7 era buttons clickable in any order. No "stuck green" state. Each click updates highlight, runtime era, and Lori's prompt context. Today is wired the same way as the other six.

**Setup:** ADD-NARRATOR(`Clear & Direct`) → capture name into RECORD

**Steps:**
1. SESSION-START
2. Click **Earliest Years**. Confirm highlight changes. Confirm chat input still works (type "test", confirm input is accepted, but don't actually send).
3. Click **Today**. Confirm highlight changes.
4. Click **Earliest Years** again. Confirm highlight switches back.
5. Click **Early School Years**. Confirm highlight changes.
6. Click **Adolescence**. Confirm highlight changes.
7. Click **Coming of Age**. Confirm highlight changes.
8. Click **Building Years**. Confirm highlight changes.
9. Click **Later Years**. Confirm highlight changes.
10. Click **Today** one final time. Confirm highlight changes.
11. After all clicks, type `Tell me about Today` and click Send.
12. Read Lori's response. Confirm she addresses the present-day context (not a past era).
13. CHECK-DB-LOCKS
14. WRAP

**Expected:**
- All 7 era buttons accept clicks throughout the cycle
- Visual highlight updates each click (no "stuck green")
- Chat input remains functional throughout
- After the final Today click + send, Lori's response references present-day context
- DB lock delta = 0

**RECORD:**
```
Earliest Years (1st click): ___
Today (1st click): ___
Earliest Years (2nd click): ___
Early School Years: ___
Adolescence: ___
Coming of Age: ___
Building Years: ___
Later Years: ___
Today (2nd click): ___
Lori response addresses Today context: ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-09 — Today Mode Date Awareness

**What it proves:** When Today is selected, Lori can answer "what day is it?" with the actual date from device_context. She must NOT claim she can't tell the date.

**Setup:** ADD-NARRATOR(`Clear & Direct`) → capture name into RECORD

**Steps:**
1. SESSION-START
2. Click **Today** in Life Map. Confirm Today highlights green.
3. Type `What day is it?` and click Send.
4. Read Lori's response carefully.
5. Acceptable responses include: today's actual date (e.g., "Friday, May 1, 2026"), today's day-of-week + brief acknowledgment, or a warm "It's <date>, which means..." style answer.
6. Unacceptable responses: any variation of "I can't tell the date" / "I'm in a conversation mode that doesn't allow me to keep track of the current date" / "I don't know what today is."
7. WRAP

**Expected:**
- Lori's response includes today's date (or at minimum today's day-of-week)
- Lori does NOT claim a hallucinated capability constraint about not knowing the date

**RECORD:**
```
Lori's full response (paste): ___
Response includes actual date: ___
Response includes day-of-week: ___
Response claims she can't tell the date: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## TEST-10 — Memoir Consistency: Peek = Export

**What it proves:** In-app Peek at Memoir and TXT export read from the same source of truth. They must show identical content. No divergence between the two surfaces.

**Setup:** ADD-NARRATOR(`Questionnaire First`) → capture name into RECORD

**Steps:**
1. SESSION-START
2. INTAKE(`Memoir Test`, `June 14, 1942`, `Cleveland, Ohio`, `middle child`)
3. Click **Peek at Memoir**.
4. Read each era section. Capture the Earliest Years content verbatim.
5. Close Peek at Memoir.
6. Trigger a TXT export (operator-side button — exact name varies; whatever produces a downloadable memoir file).
7. Open the downloaded TXT.
8. Compare Earliest Years section in TXT to the Peek snapshot from step 4.
9. Repeat comparison for at least 2 other era sections (e.g., Today, Building Years) — both should say "(no entries yet)" in both surfaces.
10. CHECK-DB-LOCKS
11. WRAP

**Expected:**
- Earliest Years content is character-identical (modulo trivial whitespace) between Peek and TXT export
- Empty era sections show identical placeholder text in both surfaces (e.g., both say "(no entries yet)" — not one saying "(no entries yet)" and the other being blank)
- DB lock delta = 0

**RECORD:**
```
Peek Earliest Years snapshot:
___

TXT Earliest Years snapshot:
___

Snapshots match: ___
Other era checked 1 (name + match): ___
Other era checked 2 (name + match): ___
DB lock delta: ___
Result: PASS / AMBER / FAIL
Notes: ___
```

---

## Final summary

After running all 10 tests, fill this in:

```
PARENT-SESSION-READINESS-V1 results — <date> <tester>

TEST-01 Clean Control:                     PASS / AMBER / FAIL
TEST-02 Reject placeOfBirth narrative:     PASS / AMBER / FAIL
TEST-03 Reject birthOrder complaint:       PASS / AMBER / FAIL
TEST-04 Reject fullName first-person:      PASS / AMBER / FAIL
TEST-05 Reset Identity clears all:         PASS / AMBER / FAIL
TEST-06 Cross-narrator state isolation:    PASS / AMBER / FAIL
TEST-07 Life Map cold-start:               PASS / AMBER / FAIL
TEST-08 Life Map era cycle:                PASS / AMBER / FAIL
TEST-09 Today mode date awareness:         PASS / AMBER / FAIL
TEST-10 Memoir Peek = Export:              PASS / AMBER / FAIL

Count by status:
  PASS:  ___ / 10
  AMBER: ___ / 10
  FAIL:  ___ / 10

Hard stops fired:
  ___ (list any RED conditions seen)

DB lock events across the whole pack:
  before: ___
  after:  ___
  delta:  ___
```

## Roll-up acceptance gate

- **GREEN — parent-session ready:** all 10 = PASS, 0 AMBER, 0 FAIL.
- **AMBER — eligible for parent session with operator caveat:** 10 of 10 are PASS or AMBER, 0 FAIL. Document each AMBER finding before the live session so the operator knows what to watch for.
- **RED — parent session blocked:** any FAIL OR any hard-stop condition fired. Fix the failing test before re-running.

If the gate is RED, do NOT run a live session with Kent or Janice. Fix what failed, re-run only the failing tests + any whose state could have been affected by the fix.

---

## Appendix A — Console marker reference

The patterns to search for in DevTools Console:

| Marker | Where it comes from | Test |
|---|---|---|
| `[bb-drift] qf_walk validation REJECTED personal.<field> reason=...` | Phase 1.1 in session-loop.js | TEST-02, TEST-03, TEST-04 |
| `[bb-drift] _saveBBAnswer SKIPPED` | pid-drift guard (pre-existing) | informational |
| `[bb-reset-identity] starting reset for pid=` | Phase 1.2 in bio-builder-core.js | TEST-05 |
| `[bb-reset-identity] projection cleared: N identity field(s), M pending suggestion(s) dropped` | Phase 1.2 | TEST-05 |
| `[bb-reset-identity] cleared localStorage lorevox_proj_draft_<pid>` | Phase 1.2 | TEST-05 |
| `[bb-reset-identity] PATCH person cleared DOB+POB` | Phase 1.2 (pre-existing line) | TEST-05 |
| `[bb-reset-identity] complete — Lori will re-ask name + DOB + birthplace` | Phase 1.2 (pre-existing) | TEST-05 |
| `[chat_ws][softened]` | Softened-mode runtime (gate #6) | informational |
| `[story-trigger]` | Story preservation trigger | informational |
| `[story-preservation]` | Story preservation row writes | informational |
| `database is locked` / `OperationalError` | DB-lock symptom | RED stop condition |

## Appendix B — Test narrator naming convention

- Each test uses ONE dedicated narrator named `TestNN <suffix>`.
- Do not reuse a narrator across tests.
- Do not reset identity on a test narrator unless the test explicitly tells you to.
- Test narrators can be cleaned up after a full pack run via the operator panel's bulk-purge tool (do not delete during a test).

## Appendix C — How to extend this pack

When a new bug is found that should be covered, add a new test by:
1. Numbering it the next sequential ID (TEST-11, TEST-12, ...).
2. Following the same template (What it proves / Setup / Steps / Expected / RECORD).
3. Adding a row to the Final summary table.
4. If the test introduces a new console marker, add a row to Appendix A.

The pack is intentionally small and concrete. If it grows past ~20 tests, split it into v2 (UI hardening) and v3 (Lori behavior) packs rather than ballooning v1.

---

## Revision history

- v1, 2026-05-01 — initial pack. 10 tests covering WO-PARENT-SESSION-HARDENING-01 Phases 1–6 and the four locked design principles. Authored after the 2026-05-01 Janice live test surfaced truth-pipeline corruption + UI human-in-the-loop concerns.
- v1, 2026-05-01 (later) — UI naming verified live against http://localhost:8082/ui/hornelore1.0.html and against the source HTML. Two-axis behavior (Lori posture × interview style) clarified. Bug Panel surface confirmed as single popover with two entry points. ADD-NARRATOR signature corrected to match actual UI: trainer-seed buttons inside narrator switcher, no separate "+ Add Test Narrator" button exists. Both [VERIFY] flags resolved.
