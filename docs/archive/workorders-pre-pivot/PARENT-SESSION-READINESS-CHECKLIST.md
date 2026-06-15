# Parent-Session Readiness Checklist

**Created:** 2026-04-25 night
**Authority:** Chris's directive (locked)
**Goal:** real parent (Mom + Dad) sessions begin **only after** every gate below is GREEN.
**Timeline:** prep + debug now (test narrators only) → real parents in **~3 days** (not tomorrow).

---

## The locked rule

> Do not run real parent sessions until every gate below is GREEN.
> Tomorrow is **prep + debug only**, with **test narrators only** (Corky + the existing test set).
> No real parent data is collected during the prep window.

---

## The 7 gates

### Gate 1 — No cross-narrator contamination

**What it checks.** Switching between narrators must not bleed any narrator's questionnaire / candidates / drafts into another's view, on read or on write.

**How to verify (Chris does this in browser):**

1. Hard refresh.
2. Open Bug Panel → run **Full UI Health Check**.
3. Switch Christopher → Corky → Christopher → Corky.
4. After EACH switch, look at the `Session Style` category in the harness:
   - `BB person scope: bb.personId === state.person_id (BUG-208)` → PASS
   - `BB questionnaire identity matches active profile (BUG-208)` → PASS
   - `BB localStorage draft key scoped to active narrator (BUG-208)` → PASS
   - `BB narrator-switch generation counter wired (BUG-208)` → PASS
5. With Corky active, save a Corky `personal.birthOrder`, switch to Christopher, switch back. Corky's value persists; Christopher's questionnaire is untouched.
6. Console must be free of `[bb-drift]` warnings during a clean session.

**Status:** Code landed (BUG-208). **AWAITING LIVE BROWSER VERIFICATION.**

---

### Gate 2 — Text archive saves both sides

**What it checks.** Every narrator turn AND every Lori turn must land in the archive's `transcript.jsonl` and `transcript.txt`.

**How to verify:**

1. With a test narrator, talk for 6+ turns (3 narrator + 3 Lori).
2. Bug Panel → Archive section → all checks PASS:
   - `archive-writer module loaded (WO-HC-03)` → PASS, `enabled=true`
   - `archive transcript writes flowing (WO-HC-03)` → PASS, `narrator>=3 lori>=3 fails=0`
   - `onAssistantReply chained for Lori transcript (WO-HC-03)` → PASS
   - `archive session_id stamped (WO-ARCHIVE-SESSION-BOUNDARY-01)` → PASS
3. Click **Export Current Session**. Open the downloaded zip. Verify `transcript.jsonl` shows alternating `role: "narrator"` / `role: "lori"` turns with non-empty `content` and a populated `meta.session_id` per row.

**Status:** Backend + frontend wired (WO-ARCHIVE-INTEGRATION-01 + WO-TRANSCRIPT-TAGGING-01 + WO-ARCHIVE-SESSION-BOUNDARY-01). **AWAITING LIVE END-TO-END VERIFICATION.**

---

### Gate 3 — Narrator-only audio rule verified

**What it checks.** Audio capture records ONLY the narrator's voice. Lori's TTS audio is NEVER captured. Defense-in-depth: client-side (TTS gate stops MediaRecorder) + server-side (`/api/memory-archive/audio` rejects `role=lori|assistant` with 400).

**How to verify (after WO-AUDIO-NARRATOR-ONLY-01 lands tomorrow morning live build):**

1. Server-side: existing 34/34 PASS smoke proves backend rejects Lori audio with 400. Re-run the audio smoke after any backend touch.
2. Client-side (after morning build): with mic permission granted, record 3 narrator turns. Verify:
   - `audio/<turn_id>.webm` files appear in DATA_DIR for narrator turns ONLY.
   - No `audio/<turn_id>.webm` for Lori turns.
   - `transcript.jsonl` rows for narrator turns have `audio_ref` set; Lori rows have `audio_ref: null`.
3. While Lori is speaking (`isLoriSpeaking=true`), MediaRecorder must be in stopped state — verify by clicking mic during Lori TTS and confirming no `audio/<turn_id>.webm` is uploaded for that interval.

**Status:** Backend complete (34/34 PASS). **Frontend recorder = morning live build with Chris.**

---

### Gate 4 — Export zip verified

**What it checks.** Operator can download a clean zip of any narrator's full archive: `transcript.txt`, `transcript.jsonl`, `meta.json`, `audio/<turn_id>.webm` per confirmed narrator turn.

**How to verify:**

1. Bug Panel → Archive Export section → click **Export Current Session**.
2. The downloaded zip must contain (at minimum):
   - `transcript.txt` — human-readable two-sided transcript
   - `transcript.jsonl` — one row per turn with `role`, `content`, `meta.session_id`, `meta.session_style`, `meta.identity_phase`, `meta.bb_field`, `meta.timestamp`
   - `meta.json` — session metadata including `session_id` and per-narrator basics
3. After Gate 3 lands: verify zip also contains `audio/<turn_id>.webm` per narrator turn.
4. Open `transcript.jsonl` in a text editor; rows must NOT contain another narrator's data.

**Status:** Backend endpoint `GET /api/memory-archive/people/{pid}/export` live. Button + helper landed (WO-ARCHIVE-EXPORT-UX-01). **AWAITING LIVE END-TO-END VERIFICATION.**

---

### Gate 5 — UI Health Check clean

**What it checks.** Full UI Health Check returns 0 critical FAIL across all categories.

**How to verify:**

1. Bug Panel → click **Run Full UI Check**.
2. Expand each category. The following MUST be PASS (or DISABLED for unused features, INFO/SKIP for prerequisites not yet met):
   - Startup, Operator Tab, Narrator Switch, Camera Consent, Mic / STT, Chat Scroll, Memory River, Life Map, Peek at Memoir, Media Tab, Photos, Archive, Session Style, Navigation Recovery, Harness Self-Check.
3. **Zero entries** with status `FAIL` are allowed. WARN/INFO/SKIP/DISABLED are acceptable for prep-day; FAIL is a hard block.
4. After every code change, re-run from cold open.

**Status:** Harness extended with WO-HC-03 + audio preflight. **AWAITING CLEAN RUN AFTER MORNING WORK.**

---

### Gate 6 — Test narrator session can be reviewed end-to-end from transcript + audio

**What it checks.** A complete loop: open Hornelore → select test narrator → run questionnaire_first → talk for 5–10 minutes → click Export → open transcript + audio outside of Hornelore → review.

**How to verify:**

1. Use Corky (or another test narrator). DO NOT use a parent.
2. Run questionnaire_first lane for 5–10 minutes — let Lori walk through the personal-section fields.
3. Click **Export Current Session** in Bug Panel.
4. Outside of Hornelore: extract the zip. Open `transcript.txt` in any text editor. The conversation reads as a clean two-sided transcript.
5. Open `transcript.jsonl` in a JSON viewer. Each row has the rich `meta` block (session_id, session_style, identity_phase, bb_field, timestamp).
6. After Gate 3 lands: open one or two `audio/<turn_id>.webm` files in any audio player. Confirm only the narrator's voice; no Lori bleed.
7. Verify nothing in the export contains data from a different narrator.

**Status:** Pending Gates 1–5. **THIS IS THE FINAL DRY-RUN BEFORE PARENTS.**

---

### Gate 7 — Live parent-session checklist exists (this document)

**What it checks.** A printable / readable checklist that the operator (Chris) walks through before, during, and after a real parent session.

**Pre-session checklist:**

- [ ] All Gates 1–6 above have been verified GREEN within the last 24 hours.
- [ ] Stack is up: `localhost:8000` (API), `localhost:8001` (TTS), `localhost:8082` (UI). Cold boot ~4 min — start before parent arrives.
- [ ] Hard-refresh Chrome to ensure latest JS is loaded.
- [ ] Bug Panel → Run Full UI Check → confirm 0 FAIL.
- [ ] Bug Panel → Run Audio Preflight → "Mic ready ✓".
- [ ] The narrator profile for the parent is selected (Mom or Dad), NOT a test narrator.
- [ ] Camera Consent dialog has been handled (decline is fine; emotion stack is optional).
- [ ] Session style chosen: `questionnaire_first` for first-session basics, `warm_storytelling` once basics are captured.
- [ ] Take-a-break overlay is dismissed and reachable in the topbar.
- [ ] No other narrator's tab is open in another window.

**During-session monitoring:**

- [ ] Watch the Bug Panel for `[bb-drift]` console warnings — none should fire.
- [ ] Glance at `narrator_writes` / `lori_writes` in archive stats — should both increment.
- [ ] If the parent gets tired or distressed, hit Take a Break.
- [ ] Long pauses are GOOD — WO-10C cognitive support pacing handles them. Don't talk over silence.

**End-of-session:**

- [ ] Click **Export Current Session** in Bug Panel.
- [ ] Verify the zip downloaded.
- [ ] Save the zip to a dated folder outside the repo (real parent data is sensitive).
- [ ] Stop the stack only after the export is confirmed saved.
- [ ] Optionally: switch to a test narrator and back to verify scope is clean before next session.

**After-session review (ARCHIVE → HISTORY → MEMOIR pipeline begins here):**

- [ ] Open `transcript.txt` and read end-to-end.
- [ ] Mark any uncertain transcripts (parent mumbled, STT misheard, fragile fact ambiguous) for fact-check.
- [ ] If audio capture lands (Gate 3): listen to clips for any uncertain transcripts.
- [ ] Note any extraction failures (Lori misroutes a fact, drops a fact, etc.) — these become the next eval-corpus expansion targets.

**Status:** This document IS the checklist. Living document — update after first real session.

---

## Status summary as of 2026-04-25 night

| Gate | What | Status |
|---|---|---|
| 1 | No cross-narrator contamination | Code landed (BUG-208), awaiting live verify |
| 2 | Text archive saves both sides | Wired, awaiting end-to-end verify |
| 3 | Narrator-only audio rule | Backend done; **frontend = morning live build** |
| 4 | Export zip verified | Helper landed, awaiting live verify |
| 5 | UI Health Check clean | Harness extended; awaiting clean run after morning work |
| 6 | Test session end-to-end | Pending Gates 1–5 |
| 7 | This checklist exists | DONE — this document |

**Until ALL 7 gates are GREEN, no real parent sessions.**

## Operating posture during the prep window

- **Test narrators only.** Corky and the existing seeded test set. No Mom or Dad data is collected during prep.
- **Aggressive bug filing.** Every glitch surfaced during prep gets a `BUG-NNN` ID. CRITICAL/HIGH/POLISH classification per the overnight rule. Fix CRITICAL+HIGH only that block parent sessions.
- **Daily "could parents start today?" gut-check.** Walk this checklist top to bottom. If any answer is "not yet," parents wait another day.

## When parents actually start (target: ~3 days from 2026-04-25)

The first session is **bigger** than just one parent. It's a calibration of the whole pipeline against real older-adult narration with possible cognitive variability. Expect:

- Some misroutes (a fact the parent says lands in the wrong field). File as eval-corpus targets.
- Some STT misheard fragile facts (dates, names). The transcript-guard fragile-fact pipeline (WO-STT-LIVE-02) flags these for confirmation.
- Some long pauses where Lori shouldn't keep talking. WO-10C is built for this.
- The first parent session is the data acquisition pipeline starting to flow. Expect surprises; don't panic.

Take notes on what surprised you. Those notes become the prep gate refinements for session #2.
