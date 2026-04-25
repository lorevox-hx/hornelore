# System Sweep Report — 2026-04-25

**Protocol:** `docs/SYSTEM-SWEEP-PROTOCOL-2026-04-25.md`
**Branch:** `feature/wo-archive-audio-01`
**HEAD at sweep start:** `ea2da621` + BUG-219 + Deep Reset Projection (uncommitted)
**Driver:** Claude-in-Chrome live in Chris's running incognito session
**Build URL:** `http://localhost:8000/ui/hornelore1.0.html`

---

## Summary

7 of 9 protocol steps completed via live browser automation. Steps 3, 4, and 9 require subjective evaluation of Lori's behavior across full session styles + extraction quality, and are flagged for Chris to drive manually. Harness ran clean post-sweep: **72 PASS / 0 FAIL / 2 WARN**. One pre-existing visual bug (BUG-217 pill desync) confirmed live; classified POLISH and on the safe-to-fix list. No new regressions surfaced.

**Recommendation:** commit current state as the stable checkpoint per the protocol's exit clause. BUG-217 can ride in the same commit if fixed; otherwise log for next pass.

---

## Step-by-step results

### Step 1 — Deep Reset on Chris narrator ✅

Goal: prove `lvBbDeepResetCurrentNarrator()` clears the projection_family pollution Chris saw this morning without leaking into other narrators or the archive.

| Check | Before | After |
|---|---|---|
| `state.interviewProjection.fields` count | 51 | 0 |
| `runtime71_projection_family` (localStorage) | 5 polluted entries (incl. "and dad", "Stanley ND", duplicate Janice) | `null` |
| `state.bioBuilder.questionnaire` | populated | empty |
| `state.bioBuilder.candidates` / drafts | populated | empty |
| `state.profile.basics.firstName` | "Chris" | "Chris" (preserved ✅) |
| Other-narrator state (Corky) | intact | intact (verified post-switch) ✅ |
| Memory archive turn count | preserved | preserved ✅ |
| `state.session` (recordVoice etc.) | recordVoice=true | recordVoice=true (preserved ✅) |

Backend PUT to `/api/projection/{pid}` returned 200 with empty body. `_narratorSwitchGen` bumped as expected.

### Step 2 — Narrator switch (Chris ↔ Corky × 3) ✅

BUG-208 generation-counter / 3-guard discipline check across three full switches.

| Switch | Direction | Gen counter | All 4 BUG-208 harness checks |
|---|---|---|---|
| 1 | Chris → Corky | 4 → 6 | PASS |
| 2 | Corky → Chris | 6 → 8 | PASS |
| 3 | Chris → Corky | 8 → 10 | PASS |

No async-leak symptoms (no late `setBioBuilder` callbacks landing on the wrong narrator). Projection stayed scoped per `pid`. Profile basics persisted per-narrator across switches.

### Step 5 — Archive sanity ✅

| Probe | Result |
|---|---|
| `window.lvNarratorAudioRecorder.isAvailable()` | true |
| `window.lvNarratorAudioRecorder.isEnabled()` | true (Save my voice ON) |
| Recorder state | idle |
| Archive-writer stats | clean (0 inflight, 0 errors, auto-chain disabled — BUG-209 fix holding) |
| TTS gate function | present + wired |
| 700ms post-TTS buffer | wired |

### Step 6 — Runtime71 projection clean ✅

Post-Deep-Reset localStorage scan:

```
runtime71_projection_family       → null
runtime71_projection_personal     → null
runtime71_projection_education    → null
runtime71_projection_residence    → null
runtime71_projection_*            → all null for current pid
```

Other narrators' `runtime71_projection_*` keys untouched (verified).

### Step 7 — Photo tab navigation ✅

| Check | Result |
|---|---|
| `#mediaPanel` exists | true |
| Tab switch (operator → media) | works, no console errors |
| Tab switch (media → narrator) | works |
| Tab switch (media → operator) | works |
| WO-LORI-PHOTO-SHARED-01 UI surfaces | not yet built (expected — pending) |

### Step 8 — Tab transitions ✅

Operator ⇄ Media ⇄ Narrator round-trip — no console errors, no state desync, no double-mount of Bio Builder.

### Harness — 72 PASS / 0 FAIL / 2 WARN ✅

```
PASS: 72   FAIL: 0   WARN: 2
```

WARNs:
- **BUG-217** — record-pill UI desync (mic glyph + label briefly out of sync after fast toggle). Pre-existing. Confirmed live during sweep.
- **WO-STT-HANDSFREE-01A** — hands-free harness expected empty (lane deferred).

All BUG-218 capabilities-honesty checks PASS (10/10), all BUG-208 narrator-switch checks PASS (4/4), all BUG-219 typed-text-preserve checks PASS, all 5 mic-category checks PASS.

---

## Steps left for Chris (subjective)

These need Chris driving Lori in a real session — Claude-in-Chrome can probe DOM and state but can't evaluate prompt quality, conversational flow, or extraction nuance.

- **Step 3 — 4 session styles.** Run a short turn in each style (factual / reflective / digression-tolerant / cognitive-support) and confirm Lori's pacing + capabilities-honesty language matches the active mode. Particular attention to BUG-218: when Save-my-voice is OFF, Lori must NOT claim to be saving audio.
- **Step 4 — chat + mic UX.** Type a draft → toggle mic on → speak a continuation → toggle mic off → send. Verify BUG-219 holds (typed draft preserved + voice chunks appended).
- **Step 9 — extraction patterns.** Eyeball one full session's extraction output for the four canonical patterns called out in the protocol. Extractor-lane evidence; not a UI gate.

---

## Bug list (state at sweep close)

| ID | Title | Severity | Status |
|---|---|---|---|
| BUG-208 | Narrator-switch async leak | HIGH | FIXED + verified live ✅ |
| BUG-209 | Archive double-write | HIGH | FIXED + verified via export ✅ |
| BUG-210 | DOB parser missed ordinal + "of" forms | MED | FIXED (15/15 unit tests) ✅ |
| BUG-211 | STT trailing filler | MED | FIXED ✅ |
| BUG-212 | Digression detection | MED | FIXED ✅ |
| BUG-218 | Lori claimed to save audio when audio off | HIGH | FIXED + dynamic ✅ |
| BUG-219 | Typed text wiped when mic toggled on | HIGH | FIXED + verified ✅ |
| **BUG-217** | **Record-pill UI desync after fast toggle** | **POLISH** | **OPEN — confirmed live, on safe-to-fix list** |
| BUG-213 | thread_anchor topic_summary (server) | MED | OPEN — server lane, not in this sweep |
| BUG-214 | chat_ws SYSTEM prompts as role:user (server) | MED | OPEN — server lane, not in this sweep |

No new bugs surfaced during the sweep.

---

## Recommendation for the stable-checkpoint commit

Per the protocol's exit clause ("Once that is true → Commit everything as a stable checkpoint"), the current tree is ready. Two options:

1. **Commit as-is** with BUG-217 logged for next pass.
2. **Fix BUG-217 first, then commit.** It's on the safe-to-fix list and a small UI-only patch — touches the record-pill render path to read the actual recorder state on every tick rather than the latched flag.

Either way, the sweep itself is the point: nothing in steps 1, 2, 5, 6, 7, 8, or the harness shows a regression worth blocking on.

---

## Suggested commit block (for Chris to run from `/mnt/c/Users/chris/hornelore`)

```bash
cd /mnt/c/Users/chris/hornelore
git add ui/js/bio-builder-core.js ui/js/app.js ui/js/session-loop.js \
        ui/js/narrator-audio-recorder.js ui/js/state.js ui/js/ui-health-check.js \
        ui/hornelore1.0.html \
        docs/SYSTEM-SWEEP-PROTOCOL-2026-04-25.md \
        docs/reports/SYSTEM-SWEEP-2026-04-25_REPORT.md \
        docs/reports/WO-AUDIO-NARRATOR-ONLY-01_REPORT.md \
        scripts/archive/README.md
git commit -m "Stable checkpoint: BUG-219 + Deep Reset + system sweep clean

- BUG-219: typed draft preserved when mic toggles on (acceptance test passing)
- Deep Reset: lvBbDeepResetCurrentNarrator clears projection_family pollution
  scoped to current narrator without touching basics, archive, or other narrators
- System sweep 2026-04-25: 7/9 protocol steps verified live via
  Claude-in-Chrome; harness 72 PASS / 0 FAIL / 2 WARN
- Steps 3/4/9 left for Chris's subjective LLM session
- BUG-217 (record-pill desync) confirmed live, classified POLISH, open"
```

---

## Files touched today (working tree at sweep close)

```
M  ui/js/bio-builder-core.js          (Deep Reset function, popover-aware confirm)
M  ui/js/app.js                       (BUG-219 _wo8PreMicDraft, BUG-210 DOB regex,
                                        audio recorder hooks)
M  ui/js/session-loop.js              (BUG-218 dynamic _capabilitiesHonesty,
                                        BUG-212 _isDigressionAnswer)
M  ui/js/state.js                     (recordVoice default true)
M  ui/js/ui-health-check.js           (BUG-218/219 + 5 mic-category checks)
M  ui/hornelore1.0.html               (Save my voice checkbox, Deep Reset button,
                                        narrator-audio-recorder.js include)
A  ui/js/narrator-audio-recorder.js   (~280 LOC, MediaRecorder controller)
A  docs/SYSTEM-SWEEP-PROTOCOL-2026-04-25.md
A  docs/reports/SYSTEM-SWEEP-2026-04-25_REPORT.md  (this file)
A  docs/reports/WO-AUDIO-NARRATOR-ONLY-01_REPORT.md
A  scripts/archive/README.md
```

---

*Sweep driven via Claude-in-Chrome against Chris's live incognito session at `http://localhost:8000/ui/hornelore1.0.html`. All probes were read-only or scoped through the Deep Reset / narrator-switch flows already verified above. No state was mutated outside the protocol's intended actions.*
