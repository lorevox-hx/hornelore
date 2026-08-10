# Phase 1 — Unit 4c: server audio persistence proof

**2026-08-09 · READ-ONLY.** No code changed, no schema changed, no browser key touched,
**no narrator turn taken**. Static trace of `POST /api/memory-archive/audio`.

Answers the single question Chris posed. **The answer is yes, and the fact already exists.**

---

## 1. ✅ The answer: `audio_ref`

> **What existing server fact can prove a specific narrator-turn audio artifact was
> successfully persisted?**
>
> **`audio_ref` on the transcript row — written only after the file write succeeds — with the
> read path re-verifying the file on disk and stamping `audio_lost` when it is gone.**

**No new field is needed.** The `identity vs outcome` split Chris asked for is already in the
code; it has simply never been named as such or read by the capability sentence.

```text
audio_id   = identity / address   ← minted client-side before capture is known (Unit 4b)
audio_ref  = verified outcome     ← written server-side only after dest.write_bytes() returns
```

---

## 2. The endpoint, traced

`memory_archive.py:494–566`. Order is the point, so it is given in order:

| step | line | behaviour |
|---|---|---|
| feature gate | `:507` | `_require_enabled()` |
| **role guard** | `:510–514` | `lori`/`assistant` → **400**; anything not narrator/user → 400 |
| id validation | `:516–521` | `safe_id()` on all three; any empty → 400 |
| **quota guard** | `:525–533` | usage ≥ cap → **413**, *audio blocked, transcript still accepted* |
| dirs | `:535–536` | `ensure_session_archive_dirs`, `get_session_audio_dir` |
| extension | `:539–545` | from filename; non-alnum or >5 chars → forced `webm` |
| **file write** | `:549–555` | `dest.write_bytes(content)`; `OSError` → **500 `"failed to persist audio file"`** |
| **ref update** | `:557–561` | `_update_turn_audio_ref(tid, pid, cid, "audio/{tid}.{ext}")` |
| response | `:563–569` | `{ok, turn_id, audio_ref, bytes, archive_dir}` |

**Successful completion means the bytes reached `audio/{tid}.{ext}` and `write_bytes` returned
without raising.** Every failure mode short-circuits with a status code before the ref is
written — 400 (role/ids), 413 (quota), 500 (write). **There is no path that writes `audio_ref`
without having written the file first.** That ordering is what makes the fact trustworthy.

**Failure is observable server-side afterwards**, which Unit 4b could not establish from the
browser: the 500 branch logs `[memory_archive] audio write failed <dest>: <exc>`. The 400 and
413 branches are HTTP-visible and quota state is queryable via
`get_person_archive_usage_bytes`. **The 413 case deserves naming on its own** — an archive
over quota accepts the transcript and silently drops the audio *by design*, and that is
precisely a session where Lori would currently say *"your voice is being saved"* while the
system has deliberately decided not to save it.

---

## 3. The read path already re-verifies, which makes the fact stronger than a flag

`GET /api/memory-archive/session/{conv_id}` (`:570+`) does not trust the stored ref. For every
row carrying an `audio_ref` it **stats the file** and stamps `audio_lost: true` when it is
missing — with the comment that a missing file is *"a diagnostic annotation, not a reason to
lose the text."*

So the Archive can already distinguish three states, and the third is the one a persisted-flag
design would have missed:

| state | signal |
|---|---|
| no audio was ever persisted for this turn | no `audio_ref` |
| audio persisted and is present | `audio_ref` + file stats OK |
| **audio persisted and has since been lost** | `audio_ref` + `audio_lost: true` |

**This is a better foundation than the boolean I would have proposed**, because it survives
the file disappearing after the fact — deletion, a failed backup, a moved data directory.
A `audio_persisted = true` column would have kept asserting a truth about the past that had
stopped being true about the present.

---

## 4. Restating Unit 4b's claim with the correct precision

Unit 4b said *"a failed upload always leaves an Archive `audio_id`."* Chris asked that it not
be promoted to a permanent architectural finding before the endpoint was read. **It survives,
narrowed, and the narrowing matters:**

- **Still true:** an Archive event's `audio_id` is populated on every turn, so its presence
  proves nothing about audio, and a failed upload leaves it identical to a successful one.
- **Now also true, and it was not visible from the browser:** the *transcript row's*
  `audio_ref` is **absent** in exactly those failure cases, because every failure returns
  before `_update_turn_audio_ref` is reached.

**So the record was never as blind as Unit 4b implied — it was being read in the wrong place.**
The Archive event field cannot answer the question; the transcript row field can, and always
could. That is a correction to my Unit 4b framing, not to its conclusion.

---

## 5. The one gap, stated as a gap

`_update_turn_audio_ref` is described at `:557–559` as pointing an existing transcript row at
the file — *"If a transcript row exists."* **I did not read its body.** So two things are
unproven:

1. **What happens when no transcript row exists yet.** The upload is fire-and-forget from
   `app.js:5947` and races the WS turn's own persistence. If the audio lands first, the ref
   update may find no row. **This is the difference between "the ref is authoritative" and
   "the ref is authoritative once the row exists," and the distinction should be settled
   before anything reads it.**
2. **Whether a failed ref-update is surfaced.** The file write is already done at that point,
   so this failure direction is the *safe* one — an artifact exists that nothing points to,
   producing a false negative rather than a false claim. Worth knowing, not worth blocking on.

**Not traced, carried forward unchanged:** STT selection (Web Speech vs Whisper), and whether
any `.webm` exists on disk today — no file was counted or opened in this pass, so the
2026-04-25 *"7 .webm files"* note is still an April note.

---

## 6. What this means for the four sentences

Updating §4 of Unit 4b with what the server can now be shown to support:

| Lori sentence | required fact | status |
|---|---|---|
| "I'm ready to record your voice." | `recordVoice` + `isAvailable()` | ✅ **exists** — this is the check the code already performs |
| "I'm recording your voice now." | `getUserMedia()` resolved + `_recorder.state === "recording"` | ⚠️ observable in-browser, **discarded** |
| "Your voice is being saved." | the above + a healthy persistence path (ids present, **not over quota**, no failure this session) | ⚠️ **all inputs exist**; quota is already queryable server-side |
| "Your voice was saved." | **`audio_ref` on the turn's transcript row, `audio_lost` false** | ✅ **exists today** |

**The strongest and the weakest claims are both already answerable.** The gap is the middle
two, and it is browser state being thrown away rather than anything missing from the server.

**Design implication, adopting Chris's rule:** do not change the meaning of `audio_id`. It is
a correct, stable address. The verified-outcome fact is `audio_ref`, it is already separate,
and the fix is to **read it** — not to add a field, and not to overload the one that exists.

---

## 7. Status

**Unit 4 is complete across all three passes.** The chain is traced end to end: the claim is
computed from an intention (4), the Archive event field cannot correct it (4b), and the
transcript row field can (4c).

**No schema change is required for capability honesty**, which is a materially better outcome
than Unit 4 projected. Two of the four sentences are supportable from facts that exist today;
the other two need browser outcomes to be recorded rather than discarded.

| unit | status |
|---|---|
| 1 — live browser inventory | ✅ `c884e22` |
| 2 — `lv_segs_` browser vs server | ⏸️ held |
| 3 — consent callers / writers | ✅ Phase 1c |
| 4 — voice truth chain, decision end | ✅ `afbfd01` |
| 4b — voice truth chain, artifact end | ✅ `1a608b7` |
| **4c — server persistence proof** | ✅ **this report** |
| 5 — writer + reader + shape per HYPOTHESIS mapping | **next** |
| 6 — progression: server condition + every `pass2a` setter + lifecycle | not started |
| 7 — final owner/migration map and minimal deltas | not started |

---

## Corrections to earlier reports

| claim | status |
|---|---|
| "a failed upload always leaves an Archive `audio_id`" (Unit 4b §2) | **stands, but was read in the wrong place.** True of the Archive event field; the transcript row's `audio_ref` is absent on every failure path. |
| "no such confirmation is retained anywhere" — *"Your voice was saved"* (Unit 4 §4, Unit 4b §4) | **withdrawn.** `audio_ref` is exactly that confirmation, written only after a successful file write, and re-verified on read via `audio_lost`. |
| implied assumption that a persistence fact would have to be added | **withdrawn** — §1. It exists; it has never been read by the capability path. |
