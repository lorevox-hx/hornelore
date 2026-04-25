# Hornelore System Sweep Protocol — 2026-04-25

**Purpose:** validate the system end-to-end after today's batch lands, surface bugs, classify, and reach a clean stable checkpoint before the next round of work.

**Operator:** Chris (or Claude-in-Chrome agent driving the live UI on your behalf).

**Mode:** observe / test / log only. Do NOT fix anything except items in the "Safe to fix in-flight" list at the end.

**Pre-conditions:**
- All today's commits pushed to `origin/feature/wo-archive-audio-01`
- Stack running on the desktop (`bash scripts/start_all.sh`)
- Browser open at `http://localhost:8082/ui/hornelore1.0.html` (incognito recommended)
- Hard-refreshed so today's code is loaded

---

## STEP 1 — Run Deep Reset on Chris narrator

This cleans the dirty `projection_family.parents` so Lori has a quiet baseline.

1. Operator tab → switch to Chris narrator.
2. Open Bug Panel.
3. Find the **Deep Reset (Projection + Family)** section.
4. Click **Deep Reset Projection for Current Narrator**.
5. Confirm dialog should show counts of what will clear (BB fields, candidates, projection fields, kinship rows, pets).
6. Click **Delete**.
7. Verify in console:
   ```
   [bb-deep-reset] PRE-RESET snapshot for Chris (a4b2f07a): N BB field(s), ...
   [bb-deep-reset] LorevoxProjectionSync.clearProjection() called
   [bb-deep-reset] backend QQ wipe → 200
   [bb-deep-reset] backend projection wipe → 200
   [bb-deep-reset] CLEARED for a4b2f07a (Chris) — was ...
   ```
8. Switch away (to Corky), then back to Chris. OR hard refresh.
9. Open DevTools console, type one of these:
   ```js
   buildRuntime71()
   ```
   or look at the next runtime71 payload in `[Lori 7.1] runtime71 → model:` log line.
10. **Acceptance:** `projection_family.parents` should NOT contain:
    - `"Stanley ND"` (was a placeOfBirth misroute)
    - `"and dad"` (token fragment)
    - any entry with `occupation="born"` (broken occupation)
11. Operator runs **Run Full UI Check** in Bug Panel — should remain **0 RED**.

If any of those pollutions remain, file as **BUG-### CRITICAL** with the runtime71 dump.

---

## STEP 2 — Narrator switching test

Goal: confirm BUG-208 cross-narrator scope holds, no bb-drift, no contamination.

1. From Chris (post-Deep-Reset), switch to Corky.
2. Open Bug Panel → run Full UI Check.
3. Expect 4 session-category BUG-208 checks PASS:
   - BB person scope
   - BB questionnaire identity matches active profile
   - BB localStorage draft key scoped to active narrator
   - BB narrator-switch generation counter wired
4. Switch back to Chris. Re-run UI Check. Same 4 PASS.
5. Switch Christopher → Corky → Christopher → Corky × 2 more cycles.
6. **Acceptance:**
   - Console must NOT show any `[bb-drift]` warnings during clean switches (the older debug-snapshot lines `[bb-drift] KEY MISMATCH` are noise — only treat new failures as real).
   - `state.bioBuilder.personId` must equal `state.person_id` after each switch.
7. Log any FAILs as BUG-###.

---

## STEP 3 — Test all 4 session styles

For each style: open a fresh narrator session with that style selected, run 4–6 narrator turns, observe Lori's behavior, log any deviations.

### Style 1: Questionnaire First

**Expected behavior:**
- Lori asks structured BB fields one at a time (preferredName, birthOrder, timeOfBirth in order)
- Saves answers via PUT /api/bio-builder/questionnaire
- On long-form digressions (>120 chars or memory cues), suppresses next-field prompt and lets Lori reflect (BUG-212 fix)
- No harsh "but I didn't ask about..." correction

**Test pattern:**
1. Pick a fresh narrator (or Deep Reset Chris first). Style = Questionnaire First.
2. Identity intake: give name, DOB, place naturally.
3. When Lori asks `birthOrder`, answer briefly: "I was the youngest."
4. When Lori asks next field, give a deliberate digression: "You know, my brother and I used to spend summers down by the river..."
5. **Acceptance:** Lori reflects warmly, does NOT say "I didn't ask about..." Console shows `[session-loop] BUG-212: digression detected ...`.

### Style 2: Clear & Direct

**Expected behavior:**
- Short questions, one fact at a time
- No rambling, no open-ended exploration
- Brief acknowledgment then move on
- Same digression handling as questionnaire_first (BUG-212 still applies)

**Test:**
1. Switch style to Clear & Direct mid-session OR start fresh.
2. Lori's tier-2 directive should now include "Ask one short question at a time. Avoid open-ended exploration."
3. Verify Lori's responses get noticeably shorter and more focused.

### Style 3: Warm Storytelling

**Expected behavior:**
- Open-ended invitations
- Reflective tone
- No forced structure
- Lori responds to what narrator says without redirecting to a checklist

**Test:**
1. Style = Warm Storytelling. Talk for 4–6 turns about anything.
2. Lori should NOT inject `[SYSTEM_QF: ...]` prompts (questionnaire_first lane is off).
3. Lori's responses should be reflective, asking follow-ups about what was said.

### Style 4: Memory Exercise

**Expected behavior (per WO-10C cognitive support):**
- Gentle prompting, recognition cues
- Allows uncertainty ("it's totally fine if you don't remember")
- Never corrects
- Speaks more slowly, longer silences allowed
- Supportive tone

**Test:**
1. Style = Memory Exercise. Identity intake → first conversation turn.
2. Verify Lori's tier-2 directive includes "Use recognition cues. Allow long silences. Never correct."
3. Pause for 2 minutes. Idle prompt should fire gently after 120s ("Take your time...").
4. Make a small factual error in your response ("My name is — wait, I think I said it wrong"). Lori should NOT correct; she should accept and reflect.

**Log every style as one of:**
- ✅ Behaves as expected
- ⚠ Mostly correct but one observation: [...]
- ❌ Wrong behavior — file BUG-###

---

## STEP 4 — Chat input + mic interaction

Test BUG-219 fix: typed-text-preserved-when-mic-toggles-on.

1. In a narrator session, click in chat input.
2. Type **"My father was"** (don't send).
3. Click the mic button to toggle on.
4. Speak: **"Kent Horne"**.
5. **Acceptance:** chat input reads **"My father was Kent Horne"** (or similar — the STT transcription quality varies). It must NOT be just "Kent Horne" (typed text wiped).
6. Console should show `[BUG-219] pre-mic draft snapshot: "My father was"`.
7. Click Send. Message should commit.

**Variation:** type a longer sentence, mic-toggle mid-typing, dictate the rest. Should append.

---

## STEP 5 — Archive writer + export round-trip

Test BUG-209 stays clean and audio capture still works (Gate 3 verified earlier today).

1. With a test narrator, talk for 4+ turns. At least one with mic on (audio capture).
2. In Bug Panel → click **Export Current Session**.
3. Save the zip.
4. Open the zip:
   - `sessions/<sid>/transcript.jsonl` — each turn appears once with `meta.ws=true`. **NO** duplicate `narrator`/`lori` rows for normal-flow turns.
   - `sessions/<sid>/audio/` — should have `.webm` files for narrator turns where mic was on. Open one externally (Chrome / VLC) — should play your voice with no Lori bleed.
5. Verify:
   - All transcript turns are present
   - meta.json has `session_id`, `person_id`, `started_at`
   - Audio files match number of mic-on narrator turns
6. **Acceptance:** Zero duplicate transcript rows, zero Lori-audio files (Lori's voice should never appear in `audio/`).

---

## STEP 6 — Runtime71 projection correctness

After Step 1's Deep Reset, runtime71's `projection_family` should be CLEAN (or empty).

1. Open DevTools console.
2. Send any narrator turn so runtime71 gets sent to the model.
3. Look for the `[Lori 7.1] runtime71 → model:` log line.
4. Inspect `projection_family`:
   - `parents` array: only legitimate parent entries (or empty after Deep Reset)
   - `siblings` array: only legitimate siblings (or empty after Deep Reset)
   - NO entries with garbage names, places-as-people, fragment text, broken occupations
5. **Acceptance:** No pollution. If pollution returns after Deep Reset → file as BUG-### CRITICAL with the runtime71 dump.

---

## STEP 7 — Photo tab navigation (no dead-ends)

Goal: confirm photo tab has a way back; no orphan empty views.

1. Operator tab → click **Start Photo Session** OR Operator launcher → **Media** tab.
2. Verify Media tab loads. Should NOT be a blank screen.
3. If photo features are disabled (`HORNELORE_PHOTO_ENABLED=0`):
   - Should show a clear "photos disabled" message
   - **Should NOT** be a blank empty view
   - Tab nav back to Operator/Narrator should work
4. If enabled:
   - Try uploading an image (small JPEG)
   - Verify image lands somewhere visible
   - Try to navigate back to Operator
5. **Acceptance:** Operator can ALWAYS navigate back to Operator or Narrator tab from any photo subview.

If you hit a dead-end, file as BUG-### HIGH.

---

## STEP 8 — Operator tab vs Narrator tab transitions

1. Operator tab → click **Start Narrator Session**. Should switch to Narrator tab.
2. Inside Narrator session → header has Bug Panel button (visible).
3. Open Bug Panel from inside Narrator session — should work.
4. Switch back to Operator tab via top nav. Then back to Narrator. Repeat 3×.
5. **Acceptance:** No frozen UI, no missing tabs, no narrator-room orphans.

---

## STEP 9 — Extraction pattern logging (observation only, NO fixes)

Goal: log what extraction misses or hallucinates. Do NOT touch extraction.

1. Run 2–3 short test sessions with Corky / Chris / Janice.
2. After each session, **Wrap Up Session** to get the operator log + zip.
3. Inspect `transcript.jsonl` for what facts were SAID but might not be EXTRACTED.
4. Look at the saved BB blob (or ask backend `GET /api/bio-builder/questionnaire?person_id=...`) to see what fields filled.
5. Categorize observations into one of:
   - **schema_gap** — fact was said but no field exists for it
   - **field_path_mismatch** — fact was said and a field exists, but it landed in the wrong field
   - **hallucination** — extracted value doesn't match what narrator said
   - **missed extraction** — clear fact stated, no extraction at all

Log patterns. Don't fix yet — that's extractor lane work and stays parked.

---

## Bug logging template

For each issue surfaced in the sweep, append to a running BUG list:

```
BUG-NNN — <Short title>
  Severity: CRITICAL | HIGH | POLISH
  Step: <which sweep step>
  Repro:
    1. ...
    2. ...
    3. ...
  Expected: ...
  Actual: ...
  Console / runtime71 dump: <if available>
```

Severity guide:
- **CRITICAL:** breaks data integrity, breaks parent sessions, causes Lori to lie or harm (e.g., cross-narrator contamination, hallucinated capabilities). Fix immediately.
- **HIGH:** breaks operator workflow, dead-ends UI, blocks export/audio. Fix soon.
- **POLISH:** UX glitches, label desync, wrong cosmetics. Defer.

## Safe to fix in-flight if surfaced

The following bug classes are safe to fix during the sweep without breaking anything else:

- BUG-217 (style pill desync — pill label not updating)
- Chat scroll issues (scroll position glitches, see-new-message button)
- Tab navigation bugs (frozen tabs, missing controls)
- Photo tab "no way back" (add a back button or proper nav)
- Input/mic interaction glitches (focus, paste, copy, etc.)

## Do NOT fix in this sweep

- Extraction logic (extractor lane is locked at r5h)
- Prompt rewrites (changes to Lori's behavior need careful testing)
- STT hands-free (deferred per Chris's directive)
- Large refactors (state.session split, app.js factor-out, etc.)
- Backend changes (server-side WOs are their own session)

## End-state acceptance

The sweep is "done" when:

1. Deep Reset ran successfully on Chris (or any polluted narrator).
2. All 4 session styles tested and observed.
3. Chat + mic interaction (BUG-219) verified clean.
4. Archive + export round-trip verified clean.
5. Photo navigation has no dead-ends.
6. Runtime71 projection_family is clean.
7. Full UI Health Check shows 0 RED.
8. Bug list captured with severity classification.
9. Any safe-to-fix CRITICAL/HIGH items addressed.

Once that's true → **commit everything as a stable checkpoint.**

## Commit message template (post-sweep)

```
chore(stabilize): post-sweep checkpoint 2026-04-25 evening

System sweep completed per docs/SYSTEM-SWEEP-PROTOCOL-2026-04-25.md
- 4 session styles validated
- Deep Reset cleaned Chris narrator's projection_family pollution
- Archive + audio + export round-trip verified
- Photo navigation has no dead-ends
- Runtime71 projection clean post-Deep-Reset
- Full UI Health Check: 0 RED, N AMBER, M PASS

Bug list:
- BUG-NNN: ... (CRITICAL — fixed in this commit)
- BUG-NNN: ... (HIGH — fixed in this commit)
- BUG-NNN: ... (POLISH — filed for later)
- ...

Stable checkpoint reached. Ready for next iteration.
```
