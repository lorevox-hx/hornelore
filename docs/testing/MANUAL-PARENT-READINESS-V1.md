# MANUAL-PARENT-READINESS-V1

**Status:** Draft v1 · 2026-05-01  
**Owner:** Chris  
**Scope:** Manual parent-readiness follow-up pack for the current Hornelore readiness harness findings.  
**Purpose:** Convert the latest harness/readout results into a concrete manual verification and triage checklist so the issues are not trapped in chat.

---

## Current gate summary

The current parent-readiness gate is **RED**.

The system has made real progress:

- **TEST-07 — Life Map cold-start: PASS**
- **TEST-09 — Today date awareness: PASS**
- **TEST-12 — Leap-year DOB awareness: PASS**
- **DB lock delta: 0** in the reported runs
- **Narration sample JSON is installed and loading**

The remaining blockers are:

1. **TEST-08 — Life Map era cycle still failing**
2. **Narration matrix fails under realistic narrator turns due to GPU/OOM/timeouts**
3. **Harness report writer shows static tests as MISSING during `--narration-only` instead of SKIP**

Do **not** run live sessions with Kent or Janice until TEST-08 is green and the GPU/OOM behavior has a graceful parent-safe fallback.

---

## Evidence snapshot

### Confirmed wins

#### TEST-07 — Life Map cold-start

Observed:

```text
Life Map visible: YES
Era button count: 7
Memory River absent: YES
Console marker:
[life-map] rendered: 6 eras, active=none, today=inactive
```

Manual meaning: the right rail now renders immediately. The earlier Memory River false-positive was fixed.

#### TEST-09 — Today date awareness

Observed Lori reply:

```text
It's Friday, May 1st, 2026.
```

Manual meaning: Lori can answer the current date from device context, including inside the active session flow.

#### TEST-12 — Leap-year DOB awareness

Observed Lori reply:

```text
Margaret, a leap day baby! I love that. February 29, 1940, will be a special marker in your story.
```

Observed persistence:

```text
personal.dateOfBirth = 1940-02-29
```

Manual meaning: Lori treats a February 29 birthdate as valid, warm, and special; she does not challenge it as invalid.

---

## Remaining blocker 1 — TEST-08 Life Map era cycle

### Current observation

The repeated failure pattern is:

```text
Earliest Years: FAIL / not clickable
Today: PASS / clickable
Earliest Years again: FAIL
Early School Years: FAIL
Adolescence: FAIL
Coming of Age: FAIL
Building Years: FAIL
Later Years: FAIL
Today again: PASS
```

Additional observations:

```text
Visible popovers: none
Era overlays: none
DB lock delta: 0
Today click markers fire
Historical era click markers do not fire
```

### Working hypothesis

Historical era buttons may require identity completion before they become clickable/useful. Today is special-cased as the present-day anchor and can activate even before full identity is complete.

This means TEST-08 may be testing era cycling too early in the narrator state.

### Decision

Use **Option A** first:

> Complete test narrator identity before running the Life Map era cycle.

Do **not** change product behavior yet. Making historical eras clickable before DOB/name/birthplace are known may introduce new issues. The era-cycle test should verify a realistic post-intake narrator state.

---

## Manual TEST-08A — Era cycle after identity completion

**Purpose:** Verify historical Life Map eras are clickable once the narrator has minimum identity context.

### Setup

1. Start with the stack warm.
2. Open Chrome to:

```text
http://localhost:8082/ui/hornelore1.0.html
```

3. Press `Ctrl + Shift + R`.
4. Open DevTools Console.
5. Clear the console.
6. Confirm **Life Story** posture.
7. Click **Ready for Session**.
8. Confirm no RED readiness state.

### Create narrator

1. Click the active narrator chip.
2. In the Narrators popover, scroll to **Choose how you'd like to begin**.
3. Click **Questionnaire First**.
4. Capture the generated test narrator name.
5. Click **Start Narrator Session** or **Enter Interview Mode**.

### Complete identity

Answer Lori's intake questions:

```text
Name: Era Cycle Test
Date of birth: March 22, 1931
Place of birth: Montreal, Quebec, Canada
Birth order: youngest
```

Stop after birth order.

### Run era cycle

Click in this order:

```text
Earliest Years
Today
Earliest Years
Early School Years
Adolescence
Coming of Age
Building Years
Later Years
Today
```

For each click, record:

```text
Did the button accept the click?
Did the visual highlight change?
Did the chat input remain usable?
Did the console show an era-click marker?
```

### Send Today context check

With **Today** selected, type:

```text
Tell me about Today
```

Expected Lori behavior:

- Lori responds in present-day context.
- Lori does not treat “Tell” as the narrator's name.
- Lori does not return to basic identity onboarding if identity is already complete.

### PASS

PASS if all are true:

```text
All historical era buttons click successfully.
Today still clicks successfully.
No stuck green state.
No dead buttons.
Chat input remains usable.
Lori response reflects Today context.
DB lock delta = 0.
```

### FAIL

FAIL if any are true:

```text
Historical eras remain unclickable after identity completion.
Today click kills the other buttons.
The Life Map visually updates but behavior does not.
Lori treats “Tell me about Today” as the narrator's name after identity completion.
```

### RECORD

```text
MANUAL TEST-08A — Era cycle after identity completion

Narrator name:
Identity completed: YES / NO

Era clicks:
Earliest Years #1:
Today #1:
Earliest Years #2:
Early School Years:
Adolescence:
Coming of Age:
Building Years:
Later Years:
Today #2:

Console era-click markers seen: YES / NO
Lori Today response:
DB lock delta:
Result: PASS / AMBER / FAIL
Notes:
```

---

## Harness update for TEST-08

Patch the automated TEST-08 to complete identity before clicking eras.

Suggested helper:

```python
def _complete_identity_for_test_narrator(self):
    self._intake(
        "Era Cycle Test",
        "March 22, 1931",
        "Montreal, Quebec, Canada",
        "youngest",
    )
```

Then TEST-08 should do:

```text
ADD-NARRATOR(Questionnaire First)
SESSION-START
_complete_identity_for_test_narrator()
Click era cycle
Send “Tell me about Today”
Score response
WRAP
```

This keeps TEST-08 aligned with realistic parent-session state.

---

## Remaining blocker 2 — Narration matrix GPU/OOM/runtime failures

### Current observation

The narration matrix reported **12/12 FAIL**.

Sub-patterns:

```text
4 explicit GPU OOM errors:
Chat error: Not enough GPU memory for this turn — please try a shorter message or try again shortly.. Try again.

6 timeouts:
Lori didn't respond to the narration within 90s.

1 partial:
Lori greeted Elena warmly, then all follow-ups were empty.

1 short fragmented case also timed out despite only ~67 words.
```

### Why this matters

This is deployment-blocking because parents may naturally give 60–250 word turns. A parent-facing session cannot show:

```text
GPU memory
Try again shortly
Chat error
```

That is a dignity failure even if the technical cause is understandable.

### Working hypothesis

Likely contributing factors:

```text
KV cache grows after warmup and previous turns.
Prompt composer carries too much prior context.
Long narrator turns push VRAM over the limit.
After one OOM, subsequent turns may stay wedged.
Harness may be sending narration while QF onboarding is still active.
Reply detector may miss some actual replies, but explicit OOM confirms at least part of this is real runtime pressure.
```

---

## Manual GPU/OOM triage pack

### Goal

Find the actual serving ceiling for realistic narrator turns and define parent-safe fallback behavior.

### Manual TEST-OOM-01 — Fresh short fragmented turn

1. Restart/warm stack.
2. Create a fresh test narrator.
3. Use **Clear & Direct** or complete identity first.
4. Send a 60–80 word fragmented narration.
5. Wait for Lori.

Expected:

```text
Lori responds within 90 seconds.
No GPU/OOM error appears.
No technical language appears to narrator.
```

Record:

```text
Word count:
Prompt mode:
Identity complete: YES / NO
Lori response time:
Reply text:
GPU/OOM visible: YES / NO
Result:
```

---

### Manual TEST-OOM-02 — Fresh medium emotional turn

Repeat with a 180–240 word emotional sample.

Expected:

```text
Lori responds within 90 seconds.
Lori reflects or asks one grounded question.
No GPU/OOM error appears.
```

Record:

```text
Word count:
Response time:
Reply text:
GPU/OOM visible: YES / NO
Result:
```

---

### Manual TEST-OOM-03 — Progressive context buildup

Use one narrator and send this sequence:

```text
Turn 1: 60–80 words
Turn 2: 100–150 words
Turn 3: 180–240 words
Turn 4: Ask: What do you remember about what I just told you?
Turn 5: Ask: What day is it?
```

Expected:

```text
No OOM.
No timeout.
No technical error.
Lori remembers at least one concrete detail.
Lori can still answer date/time.
```

Record:

```text
Turn count before failure, if any:
Longest successful word count:
First failed word count:
Was failure explicit OOM or silent timeout?
Visible narrator-facing error:
Result:
```

---

### Manual TEST-OOM-04 — Graceful fallback check

Force or reproduce an OOM condition.

Expected parent-safe fallback must be:

```text
Warm, nontechnical, and recoverable.
```

Acceptable narrator-facing fallback:

```text
I’m sorry, I missed part of that. Could we try that in a smaller piece? I want to make sure I get your story right.
```

Unacceptable:

```text
GPU memory
Not enough GPU memory
Try again shortly
Internal error
API offline
Database error
```

Record:

```text
Raw error shown:
Was it parent-safe? YES / NO
Did system recover on next shorter input? YES / NO
Result:
```

---

## Required product work from OOM finding

Create a separate work order:

```text
WO-EX-GPU-CONTEXT-01
```

Minimum scope:

```text
1. Measure VRAM before/after warmup and per turn.
2. Add prompt-context trimming for chat turns.
3. Add maximum safe narrator-turn budget by mode.
4. Add automatic retry with smaller context after OOM.
5. Replace technical GPU/OOM UI message with parent-safe copy.
6. Add harness markers for OOM, retry, and fallback path.
7. Add a narration stress test that runs fresh-process and accumulated-context variants separately.
```

Acceptance:

```text
A 200-word narrator memory does not show a technical error.
A 60–100 word fragmented narrator memory never times out under normal warm conditions.
If backend OOM occurs, narrator sees warm fallback copy, not GPU language.
The next shorter turn can recover without restarting the whole stack.
```

---

## Small harness/report bug

### Symptom

When `--narration-only` is set, static tests appear as:

```text
MISSING
```

They should appear as:

```text
SKIP — narration-only
```

### Fix

Update report writer so expected static tests are prefilled as SKIP when omitted by narration-only mode.

Acceptance:

```text
--narration-only report shows TEST-01 through TEST-12 as SKIP, not MISSING.
Narration matrix tests remain visible with PASS/AMBER/FAIL.
Overall result is based only on tests actually run.
```

---

## Re-run order after fixes

After TEST-08 harness fix and OOM mitigation/fallback work:

### 1. Cold-priority slice

```bash
.venv-ui-test/bin/python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1.json \
  --only TEST-07,TEST-08,TEST-09
```

Expected:

```text
TEST-07 PASS
TEST-08 PASS
TEST-09 PASS
Overall GREEN for selected tests
```

### 2. Leap-year guard

```bash
.venv-ui-test/bin/python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1.json \
  --only TEST-12
```

Expected:

```text
TEST-12 PASS
DOB persists as 1940-02-29
No defensive language
```

### 3. Validator/reset/cross-narrator pack

```bash
.venv-ui-test/bin/python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1.json \
  --only TEST-01,TEST-02,TEST-03,TEST-04,TEST-05,TEST-06,TEST-10
```

Expected:

```text
All selected tests PASS or documented AMBER.
No protected identity corruption.
No cross-narrator leakage.
Reset clears all identity surfaces.
Peek/export match.
```

### 4. Narration matrix, slow lane

Run only after OOM mitigation or fallback exists:

```bash
.venv-ui-test/bin/python scripts/ui/run_parent_session_readiness_harness.py \
  --base-url http://localhost:8082/ui/hornelore1.0.html \
  --api http://localhost:8000 \
  --output docs/reports/parent_session_readiness_v1.json \
  --narration-only
```

Expected after mitigation:

```text
No narrator-facing GPU/OOM messages.
Fragmented and messy samples mostly PASS.
Emotional samples at least AMBER or PASS.
Clean 800-word samples may be AMBER if too long, but must not show technical errors.
```

---

## Roll-up gate

### GREEN

```text
TEST-01 through TEST-12 PASS.
Narration fragmented/messy/emotional samples pass or have acceptable AMBER.
No narrator-facing technical errors.
No DB lock delta.
No cross-narrator leakage.
No operator controls in narrator flow.
```

### AMBER

```text
All hard-stop tests PASS.
Narration clean/long samples may be AMBER due to length, but fallback is parent-safe.
Operator knows exactly what to watch.
```

### RED

```text
Any Life Map era dead-state remains.
Any protected identity corruption appears.
Any rejected text appears as memoir truth.
Any parent-visible GPU/API/internal error appears.
Any cross-narrator leak appears.
Any DB lock delta appears during normal turns.
```

Current state remains:

```text
RED — TEST-08 and GPU/OOM are not closed.
```

