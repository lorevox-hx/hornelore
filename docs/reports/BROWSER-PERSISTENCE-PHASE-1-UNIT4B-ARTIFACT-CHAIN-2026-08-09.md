# Phase 1 — Unit 4b: artifact-side voice trace

**2026-08-09 · READ-ONLY.** No code changed, no schema changed, no browser key touched,
**no narrator turn taken**. Static trace of the artifact chain.

Completes what Unit 4 (`afbfd01`) deliberately left open. **The §3 hazard is confirmed, and
the mechanism is not the one I proposed.**

---

## 1. 🔴 The fallback was the wrong suspect. `audio_id` is minted unconditionally.

Unit 4 flagged `chat_ws.py:1170` — `params.get("audio_id") or params.get("turn_id")` — and
asked whether the fallback was reachable on a typed turn. **The fallback is not the defect.
It rarely fires, because the browser sends `audio_id` populated on every turn.**

`app.js:5935–5942`, at the top of the send path:

```js
let _audioTurnId = null;
try {
  _audioTurnId = crypto.randomUUID ? crypto.randomUUID() : ("t_" + …);
  window._lvLastAudioTurnId = _audioTurnId;
} catch (e) { … }
```

**There is no gate.** Not on `recordVoice`, not on recorder availability, not on permission.
A fresh UUID is minted for **every** send. The recorder is only consulted *afterwards*
(`:5944`), and only to address an upload if one happens.

Then `:6072–6073` puts it on the wire twice:

```js
audio_id: _audioTurnId,
turn_id:  _audioTurnId,
```

So on a **typed turn, with the microphone never touched**, `params["audio_id"]` arrives
non-null and ~36 characters. It clears `chat_ws.py:1173`'s `len >= 8` shape guard, and
`archive.append_event(audio_id=…)` (`archive.py:198–201`) stores it.

> ### 🔴 An `audio_id` in an Archive event is **not** evidence that audio exists.
> It is evidence that a turn was sent. The two are currently indistinguishable in the record.

**This is worse than the Unit 4 hypothesis and better-defined.** I proposed a fallback firing
in an edge case; the reality is an identifier minted before anything is known, on the
majority path. Had we tried to derive capability honesty from the Archive — the obvious next
move after Unit 4 — we would have built it on a field that is populated for typed turns.

**Why it is nevertheless not a *storage* bug.** The upload is addressed by the same id
(`_uploadSegment(blob, tid)` → `fd.append("turn_id", turn_id)`, filename
`turn_id.slice(0,24) + ".webm"`). So when audio does exist the id **correctly** addresses it.
The identifier is right; the **claim implied by its presence** is wrong. The 2026-05-07
comment at `app.js:5917–5931` says as much in its own words — *"the linkage field is still
well-formed"* — which is true, and is a statement about addressing, not about existence.

---

## 2. The upload path, and where confirmation is lost

```text
sendUserMessage()                app.js:5935   mint _audioTurnId  (UNCONDITIONAL)
  └─ recorder.stop(_audioTurnId) app.js:5947   FIRE-AND-FORGET, .catch() logs only
       └─ onstop → Blob(_chunks) narrator-audio-recorder.js:196
            ├─ blob.size < 200 → DISCARD, return           :200
            └─ _uploadSegment(blob, tid)                    :207
                 └─ POST /api/memory-archive/audio  (multipart) :249
                      ├─ 200 → _stats.segments_uploaded++       :253
                      └─ non-200 → console.warn, return false   :259
  └─ WS start_turn { audio_id, turn_id }  app.js:6072  ← sent REGARDLESS of all the above
       └─ archive.append_event(audio_id=…)  archive.py:198  ← stores it unconditionally
```

**Three places the truth is dropped:**

1. **`stop()` is fire-and-forget.** `app.js:5947` attaches only a `.catch()` that logs. The
   send path does not await it and cannot know the outcome.
2. **The upload's success is recorded only in a browser-local counter.**
   `_stats.segments_uploaded++` is in-memory JS. Nothing returns to the WS turn, and nothing
   server-side reconciles it.
3. **A sub-200-byte blob is silently discarded** (`:200`) — a real outcome for a turn where
   the narrator typed, or spoke while Lori was speaking (the recorder stops when
   `isLoriSpeaking` flips true). The turn still carries its `audio_id`.

**Answer to Chris's question — can a failed upload still leave an Archive `audio_id`?**
**Yes, always.** The WS frame and the upload are independent, the frame is not conditioned on
the upload, and the upload's result never reaches the server. A 500, a timeout
(`AbortController`, `_UPLOAD_TIMEOUT_MS`), a missing `conv_id` (`:212` returns false before
any request), or a discarded blob all leave the Archive event byte-identical to a success.

**Storage side, traced but not opened:** `POST /api/memory-archive/audio`
(`memory_archive.py:494`) is the endpoint; `:512` rejects assistant/Lori audio with 400,
which confirms the narrator-only rule is enforced server-side. **I did not read the write
body, so where the bytes land on disk and under what name is traced to the endpoint and no
further.** `stt.py:154` is a *separate* consumer of an audio blob for transcription and is not
part of the persistence chain.

---

## 3. Which of the five states current code can distinguish

| state | distinguishable today? | why |
|---|---|---|
| **recording requested** | ✅ yes | `state.session.recordVoice` — in-memory, browser only |
| **permission granted** | ⚠️ **knowable, not recorded** | `getUserMedia()` resolves at `:99` and the outcome is never stored or transmitted |
| **recording active** | ⚠️ **knowable, not recorded** | `_recorder.state` exists in the browser; never leaves it |
| **upload attempted** | ❌ **no** | browser-local `_stats` only |
| **artifact persisted** | ❌ **no** | the endpoint's 200 is discarded client-side; the Archive's `audio_id` is populated either way |

**The system currently distinguishes exactly one of the five, and it is the weakest one.**
The two middle states are *observable in the browser at the right moment* and simply never
recorded — which is the cheap half of the fix. The two right-hand states need a server fact
that does not exist yet.

---

## 4. What can honestly support each sentence — using Chris's three-tier distinction

I accept the correction: *"is being saved"* should not require a completed artifact. The
tiers below are graded on **tense and on what is being promised**, and each names the fact it
needs and whether that fact exists today.

| Lori sentence | fact required | exists today? |
|---|---|---|
| **"I'm ready to record your voice."** | `recordVoice` on **AND** `MediaRecorder`/`getUserMedia` present. This is the *only* claim `isAvailable()` legitimately supports — and it is what the current code actually tests. | ✅ **yes — available now** |
| **"I'm recording your voice now."** | `getUserMedia()` **resolved** this session **AND** `_recorder.state === "recording"` at compose time | ⚠️ observable, **not recorded or transmitted** |
| **"Your voice is being saved."** | the above **AND** an upload path with no known failure — i.e. `conv_id`/`person_id` present, and no upload for this session has failed | ❌ **cannot be said honestly today**; failure is invisible to the server |
| **"Your voice was saved."** | a **confirmed** persisted artifact — a 200 from `/api/memory-archive/audio`, recorded server-side and reconcilable against the turn | ❌ **no such confirmation is retained anywhere** |

**The single most useful correction is the first row.** The current code performs exactly the
check that licenses *"I'm ready to record"* and then uses it to say *"your voice is being
saved."* **The test is not wrong — it is being asked the wrong question.** That reframes the
fix: the readiness check keeps its job and gets its own sentence, and the two stronger claims
need facts the system does not yet carry.

**Sequencing that follows, and it is deliberately cheap first:** rows 1–2 need nothing on the
server — they are browser facts that exist at the right moment and are simply thrown away.
Row 3 needs the upload outcome to survive. Row 4 needs a persistence confirmation, and that
is the only one implying a possible schema question — **which I am not proposing here.**

---

## 5. What Unit 4b did NOT establish

- **The endpoint's write body is unread.** Disk layout, filename and any DB row written by
  `POST /api/memory-archive/audio` are untraced beyond the route and its 400-on-assistant
  guard.
- **No artifact was counted or opened.** The 2026-04-25 *"7 .webm files"* claim remains an
  April comment; whether any audio exists on disk today is still unverified.
- **STT selection remains untraced.** `stt.py` was identified as a separate consumer; the
  Web Speech vs Whisper decision path was not followed, and `lv_use_whisper_stt` is still not
  shown to govern anything in this chain.
- **Whether `chat_ws.py:1170`'s fallback ever fires is now moot but unproven** — with
  `audio_id` always populated upstream, the `or turn_id` branch appears unreachable from
  `app.js`, but other producers (Travel Doc, harnesses) were not checked.

---

## 6. Status

Unit 4's finding stands and is now **completed on the artifact side**: the defect is a
narrator-facing truth defect at both ends. The claim is computed from an intention (Unit 4),
and the record that might have corrected it cannot distinguish audio from no audio (Unit 4b).

**No migration work is added.** Nothing here moves a key from browser to database. Three of
the four facts in §4 are transient session state; the fourth is a server confirmation that
does not exist. This remains an input-selection and outcome-recording problem.

| unit | status |
|---|---|
| 1 — live browser inventory | ✅ `c884e22` |
| 2 — `lv_segs_` browser vs server | ⏸️ held |
| 3 — consent callers / writers | ✅ Phase 1c |
| 4 — voice truth chain, decision end | ✅ `afbfd01` |
| **4b — voice truth chain, artifact end** | ✅ **this report** |
| 5 — writer + reader + shape per HYPOTHESIS mapping | next |
| 6 — progression: server condition + every `pass2a` setter + lifecycle | not started |
| 7 — final owner/migration map and minimal deltas | not started |

---

## Corrections to earlier reports

| claim | status |
|---|---|
| "`audio_id -> turn_id` fallback … if typed turns can end up with `audio_id=turn_id`" (Unit 4 §3) | **confirmed in effect, wrong in mechanism.** The fallback is not the path; `audio_id` is minted unconditionally at `app.js:5935` and sent populated on every turn. Same conclusion, stronger and on the majority path. |
| "only a persisted artifact licenses the present-tense affirmative" (Unit 4 §4) | **superseded by Chris's three-tier rule**, adopted in §4. *"Is being saved"* requires active capture plus a healthy persistence path; *"was saved"* requires the confirmed artifact. |
| implied assumption that the Archive could serve as the persistence signal | **withdrawn** — §1. It cannot, as it stands. |
