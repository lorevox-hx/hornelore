# Phase 1 — Unit 4d: `_update_turn_audio_ref` race and semantics

**2026-08-09 · READ-ONLY.** No code changed, no schema changed, no browser key touched,
**no narrator turn taken**.

Closes the gap Unit 4c flagged. **The updater is a bare `UPDATE` with no upsert, no retry and
no return value, and there is no reconciliation path.**

---

## 1. The answer

> **Is `audio_ref` guaranteed to be attached eventually after a successful audio write, or
> only when the transcript row already exists at upload time?**
>
> **Only when the row already exists.** There is no eventual attachment, no retry, and no
> reconciliation. If the row is not there at that instant, the file is written, the ref is
> never attached, and **nothing anywhere later notices.**

---

## 2. The body, in full

`memory_archive.py:233–246` — the entire function:

```python
def _update_turn_audio_ref(turn_id: str, person_id: str, conv_id: str, audio_ref: str) -> None:
    con = _connect()
    try:
        con.execute(
            """
            UPDATE memory_archive_turns
               SET audio_ref=?, ts=?
             WHERE id=? AND person_id=? AND conv_id=?;
            """,
            (audio_ref, _now_iso(), turn_id, person_id, conv_id),
        )
        con.commit()
    finally:
        con.close()
```

Against Chris's six questions:

| question | answer |
|---|---|
| exact row key | `memory_archive_turns` on **`id` AND `person_id` AND `conv_id`** — `id` is the `turn_id`, i.e. the same `_audioTurnId` that names the file |
| behaviour when the row does not exist | **silent no-op.** `UPDATE` matches zero rows, commits successfully, raises nothing |
| does it return success/failure | **no.** Signature is `-> None`. `con.execute()`'s result — which carries `.rowcount` — is **discarded on the same line** |
| does the endpoint check the result | **it cannot.** `:560` calls it as a bare statement; there is no value to check |
| can a file be written and permanently orphaned | **yes** |
| any later reconciliation | **none found** |

**Exactly one caller**, `memory_archive.py:560`, immediately after the file write.

**The distinguishing detail is `.rowcount`.** SQLite makes the outcome available and the code
discards it. This is not a case of the database being unable to report the miss — it is a
report that is not collected. **That is what makes it a small defect rather than a design
limit**, and it is why the fix is cheap.

---

## 3. 🔴 The orphan direction is the one nothing checks

The Archive is careful about the *opposite* failure and blind to this one:

| condition | detected? | where |
|---|---|---|
| `audio_ref` present, file missing | ✅ **yes** — `audio_lost: true` | `:605` `row["audio_lost"] = not audio_path.is_file()` |
| **file present, `audio_ref` missing** | ❌ **no** | nothing stats the audio directory for unreferenced files |

`GET /session/{conv_id}` iterates **transcript rows** and checks their refs. A file with no row
pointing at it is never visited, because the loop never looks at the directory. The module
docstring states the guarantee it does provide — *"Missing audio file + present transcript
row → `audio_lost: true`"* (`:14`) — and it is accurate. The inverse simply has no owner.

**Consequence for the Unit 4 chain:** `audio_ref` remains the correct proof of persistence and
Unit 4c's finding stands — but it is a **one-directional** proof. Its presence proves the file
was written. **Its absence does not prove the file was not written.** For the four sentences
that is the safe direction (a false *"not saved"* beats a false *"saved"*), and it should be
stated that way rather than as *"`audio_ref` tells you whether audio persisted."*

---

## 4. Whether the race actually fires — stated as unproven

The two writes are independent: the browser fires `recorder.stop(_audioTurnId)`
**fire-and-forget** at `app.js:5947`, while the WS turn persists the transcript row by its own
path. Nothing orders them.

**I have not proven which usually wins, and I am not going to infer it.** Plausibly the
transcript row lands first in most sessions — the upload waits on `onstop`, blob assembly and
a network round trip with a timeout. But *usually* is not a guarantee, and the honest
statement is the one about the code rather than about the odds:

> **Nothing in the code orders these two writes, and the code that would notice the bad
> ordering discards its only signal.**

**A slow or large upload, a retried request, or an upload completing after a page event are
all ordinary conditions**, and each produces a silently orphaned file. Establishing the actual
frequency would need either a live instrumented turn or a filesystem-vs-DB comparison — and
**neither was done here**, per the read-only scope.

---

## 5. The smallest missing fact — identified, not implemented

**No schema change is required**, which is the useful part. The filename already encodes the
row key: the file is `audio/{tid}.{ext}` and the row is `id = tid`. **The link is fully
recoverable from what is already on disk.**

Two candidate shapes, both small, and I am proposing neither:

- **Collect the signal at the write.** Read `cur.rowcount`; on 0, log that the file was
  written with no matching row. Converts a silent orphan into a visible one at zero
  structural cost.
- **Mirror the existing read-side check.** `GET /session` already stats a file for each row;
  the symmetric pass — for rows with no `audio_ref`, stat `audio/{id}.webm` — would attach or
  report orphans on read, using the key that is already there.

**Which is right depends on whether the ref is meant to be authoritative at write time or
resolvable at read time, and that is a design decision for Chris**, not a gap to fill
unilaterally. The second is closer to how `audio_lost` already behaves.

---

## 6. Status — Unit 4 closed

The chain is traced end to end across four passes:

| pass | finding |
|---|---|
| **4** | the claim is computed from an intention plus a static feature test |
| **4b** | `audio_id` is minted unconditionally; the Archive event field cannot correct the claim |
| **4c** | `audio_ref` is a genuine persistence proof, written only after a successful file write |
| **4d** | that proof is **one-directional** — attached only if the row exists at upload time, with no retry and no reconciliation |

**No new schema is required for capability honesty**, and none for the orphan gap either. The
outstanding work is reading facts that exist and collecting a signal that is currently thrown
away — in the browser (Unit 4) and at `:557` (this report).

| unit | status |
|---|---|
| 1 — live browser inventory | ✅ `c884e22` |
| 2 — `lv_segs_` browser vs server | ⏸️ held |
| 3 — consent callers / writers | ✅ Phase 1c |
| 4 / 4b / 4c — voice truth chain | ✅ `afbfd01` · `1a608b7` · `aa058b7` |
| **4d — `audio_ref` race and semantics** | ✅ **this report — Unit 4 CLOSED** |
| 5 — writer + reader + shape per HYPOTHESIS mapping | **next** |
| 6 — progression: server condition + every `pass2a` setter + lifecycle | not started |
| 7 — final owner/migration map and minimal deltas | not started |

---

## Corrections to earlier reports

| claim | status |
|---|---|
| *"`audio_ref` … proves a specific narrator-turn audio artifact was successfully persisted"* (Unit 4c §1) | **stands, narrowed to one direction.** Presence proves the write happened. **Absence does not prove it did not.** |
| *"the failure direction is at least the safe one"* (Unit 4c §5) | **confirmed** — a false negative, not a false claim. But *"safe"* now also means *permanent and unreported*: no path ever revisits it. |
| the open question of whether the updater retries/upserts (Unit 4c §5) | **answered** — it does neither. Bare `UPDATE`, `-> None`, `.rowcount` discarded, one caller, no reconciliation. |
