# Phase 1 — Unit 4: voice capture / persistence truth chain

**2026-08-09 · READ-ONLY.** No code changed, no schema changed, no browser key read or
written, **no narrator turn taken**. Static trace of the producer chain only.

**Scope honesty up front:** this pass proves the *decision* end of the chain — what governs
the sentence Lori says — conclusively. It does **not** yet prove the *artifact* end. §5 names
exactly what is unverified so it is not assumed later.

---

## 1. 🔴 The headline: Lori's recording claim is made from an intention and a feature test

The capability sentence is built by `_capabilitiesHonesty()` in `ui/js/session-loop.js:558`,
injected into `runtime71.session_style_directive` by `app.js:2944`, and read server-side at
`prompt_composer.py:3836`. **The browser composes the sentence; the server transports it.**

The entire truth condition is two booleans:

```js
const recordVoice    = !!(state.session && state.session.recordVoice !== false);
const recorderAvail  = !!(window.lvNarratorAudioRecorder &&
                          window.lvNarratorAudioRecorder.isAvailable());
const audioActive    = recordVoice && recorderAvail;
```

and `isAvailable()` (`narrator-audio-recorder.js:72`) is:

```js
return (typeof MediaRecorder !== "undefined") &&
       !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
```

**That is a static browser feature-detection.** It asks whether the *API exists* in this
Chrome. It does not call it. So when `audioActive` is true, Lori tells the narrator:

> *"Yes, your voice is being saved this session — your voice only, never mine."*

on the strength of: **a checkbox is not off**, and **this browser ships `MediaRecorder`.**

**Two aggravating details.**

- **The default is the affirmative claim.** `recordVoice !== false` means `undefined → true`.
  A session where nothing ever set the flag claims audio is being saved.
- **`getUserMedia` is named in the condition but never invoked by it.** The check reads as
  though it tests microphone capability; it tests only that the function is *defined*.

---

## 2. The six states Chris asked to be distinguished, against what is actually consulted

| # | state | consulted by the sentence? | where the real fact lives |
|---|---|---|---|
| 1 | **requested** (Save my voice on) | ✅ **yes** — `state.session.recordVoice`, `app.js:2033` | in-memory session flag |
| 2 | **permission granted** | ❌ **no** | `getUserMedia()` resolution, `narrator-audio-recorder.js:99` |
| 3 | **capture active** (recorder running) | ❌ **no** | `_recorder.start()`, `:166` |
| 4 | **STT active** | ❌ **no** | not traced this pass — see §5 |
| 5 | **save-my-voice enabled** | ✅ conflated with #1 | same single flag |
| 6 | **artifact actually persisted** | ❌ **no** | `archive.append_event(audio_id=…)`, `archive.py:198` |

**Only state 1 is consulted, plus a static API check that is not any of the six.** States
2, 3 and 6 — the three that make the claim true or false — are all invisible to the sentence.

The gap chain from Phase 1, now confirmed rather than asserted:

```text
requested            ≠  permission granted
permission granted   ≠  recorder started
recorder started     ≠  blob produced
blob produced        ≠  artifact persisted
```

Every one of those inequalities is currently crossed by assumption.

**Concrete failure modes this admits, all of which produce a false "yes":** the narrator
denies the mic prompt; the OS has no input device; `getUserMedia` throws
(`narrator-audio-recorder.js:96` raises `"getUserMedia unavailable"`); no supported MIME type
is found (`:85–89` can return nothing); the recorder starts and the upload never lands.

---

## 3. 🟡 A second honesty hazard on the server side, reported as observed

`chat_ws.py:1170`:

```python
_ai_raw = params.get("audio_id") or params.get("turn_id") or None
```

**The archive's `audio_id` falls back to `turn_id`.** `archive.append_event()` then stores
whatever it is given (`archive.py:198–201`) with no check that audio exists behind it.

If that fallback can fire on a turn with no audio, the archive records an `audio_id` for a
turn that has none — which would make the archive itself unable to answer *"was this turn's
voice saved?"*, and would defeat any later attempt to derive capability honesty from it.

**Stated as observed, not concluded.** I have not read the guard conditions above line 1168,
so I do not know whether the fallback is reachable on a typed turn. **Determining that is the
first item of the Unit 4 follow-up**, because it decides whether the archive is usable as the
authoritative persistence signal.

---

## 4. The smallest authoritative runtime facts Lori should use

Chris asked for the minimum set. Deliberately four, each an **observed outcome** rather than
a setting, and each already produced somewhere in the chain — none requires new capture:

| fact | source of truth | why it is the honest one |
|---|---|---|
| `voice_capture_permitted` | `getUserMedia()` **resolved** this session | distinguishes denied/absent mic from an on checkbox |
| `voice_capture_active` | `_recorder.state === "recording"` at compose time | distinguishes "started" from "intended" |
| `last_voice_artifact_persisted` | server-side: an archive event for this session carries a **real** `audio_id` | the only fact that supports *"is being saved"* |
| `voice_persistence_requested` | `state.session.recordVoice` | keeps intent visible — but it may **never alone** license the affirmative claim |

**The rule that should govern the sentence:** *"your voice is being saved"* may be spoken only
when an artifact has actually been persisted for this session. Before the first artifact, the
honest form is forward-looking ("I'm set up to save your voice this session") or the negative.
**The affirmative present tense is a claim about the past, and only the past can license it.**

Three of the four facts are transient session state, not durable narrator state, so **this is
not a `localStorage` → SQLite migration.** It is a correction of *which* fact is read. Only
`last_voice_artifact_persisted` needs the server, and §5 must confirm it is trustworthy first.

**One narrower point worth keeping separate from the migration work:** the *capability
statement* is a Phase 6 behavioural contract, and it is currently the weakest of the ten —
not because the prompt is wrong but because the value handed to it is.

---

## 5. What Unit 4 did NOT establish — recorded so it is not assumed

- **STT selection (Web Speech vs Whisper) is untraced.** `lv_use_whisper_stt` /
  `lv_mic_modal_enabled` remain **unattached** to the capability sentence; nothing in
  `_capabilitiesHonesty()` reads them. My Phase 0 claim that they are the toggle behind the
  recording answer stays **withdrawn** — and this pass shows the real governor is
  `recordVoice` + `isAvailable()`. Whether those keys govern *STT* is still open.
- **The upload path is untraced.** I did not read how a blob leaves the browser, whether an
  `audio_id` is minted client- or server-side, or what returns it.
- **Artifact persistence is unverified.** The 2026-04-25 comment cites *"export zip with 7
  .webm files (Test B passed)"* — **that is a claim from April, not evidence about today.**
  No `.webm` was located, counted or opened in this pass, and the live DB was not queried.
- **The `turn_id` fallback's reachability is unknown** (§3).
- **`isLoriSpeaking` gating** (`narrator-audio-recorder.js:11`, recorder stops when Lori
  speaks) is noted but its interaction with `_recorder.state` at compose time is untraced —
  it may mean `voice_capture_active` reads false during a normal Lori turn, which would make
  it the wrong instantaneous signal. **This is a design detail for the eventual fix, not a
  finding.**

**None of the above is needed to accept §1 and §2.** The decision end of the chain is proven
from the source of the condition itself.

---

## 6. Effect on the plan

Unit 4 **does not add migration work** and it **does not create a table**. It converts one
Phase 6 behavioural contract from "believed preserved" to "known to be evaluated from the
wrong input," and it names the four facts that would fix it.

**Priority note.** Chris moved Unit 4 ahead of the hypothesis map because it affects what Lori
tells a narrator. That was right, and the result is stronger than expected: this is not a
storage-location problem at all. **Relocating `recordVoice` to SQLite would have changed
nothing** — the sentence would still be a claim about intent. Had this been discovered during
implementation rather than during the read-only trace, the migration would have "succeeded"
and the dishonesty would have survived it intact.

---

## Remaining Phase 1 units

| unit | status |
|---|---|
| 1 — live browser inventory | ✅ Phase 1d (`c884e22`) |
| 2 — `lv_segs_` browser vs server | ⏸️ **held** — no browser blob to compare; grain mismatch resolved in the server-owner design |
| 3 — consent callers / writers | ✅ Phase 1c |
| **4 — voice capture / persistence truth chain** | ✅ **decision end proven, this report**; artifact end open per §5 |
| 5 — writer + reader + shape per HYPOTHESIS mapping | next |
| 6 — progression: server condition + every `pass2a` setter + lifecycle | not started |
| 7 — final owner/migration map and minimal deltas | not started |

---

## Corrections to earlier reports

| claim | status |
|---|---|
| "`lv_use_whisper_stt` / `lv_mic_modal_enabled` are the toggle behind Lori's recording claim" (Phase 0 §1) | **withdrawn already; now positively replaced** — the governor is `state.session.recordVoice` + `isAvailable()`. Those keys are not read by the capability path at all. |
| "the honest surface is closer to `voice_capture_active`, `voice_persistence_enabled`, …" (Phase 1 §capability) | **narrowed to four facts** in §4, with the ordering rule that only a persisted artifact licenses the present-tense affirmative. |
| implicit assumption that capability honesty was a storage-location problem | **withdrawn** — §6. It is an input-selection problem; migration alone would not have fixed it. |
