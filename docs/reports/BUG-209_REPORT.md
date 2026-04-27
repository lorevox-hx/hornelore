# BUG-209 — Archive transcript double-write — Implementation Report

**Filed:** 2026-04-25 morning
**Surfaced by:** Chris's first morning export (`hornelore_archive_4a55033c-...20260425T124838Z.zip`)
**Severity:** HIGH (parent-session blocker — Gate 2 of readiness checklist would FAIL)
**Status:** **CODE LANDED, awaits live verify** — export a fresh session and confirm only one row per turn.

## Symptom

The exported `transcript.jsonl` for the latest test session (`switch_moec2vfc_m84n`) contained every turn **twice** under different role names:

| seq | role | content | meta.ws | meta.session_id |
|---|---|---|---|---|
| 1 | user | `[SYSTEM_QF: ...]` | true | — |
| 2 | assistant | `Corky, it feels great...` | true | — |
| **3** | **lori** | **`Corky, it feels great...`** (DUPLICATE) | false | `s_moec0rt6_c01be6b5` |
| 4 | user | `what if i was chris` | true | — |
| **5** | **narrator** | **`what if i was chris`** (DUPLICATE) | false | `s_moec0rt6_c01be6b5` |
| 6 | assistant | `You were considering...` | true | — |
| **7** | **lori** | **`You were considering...`** (DUPLICATE) | false | `s_moec0rt6_c01be6b5` |

Two writers are racing into the same archive store:

- Backend `chat_ws` handler writes `user` / `assistant` rows directly (these carry `meta.ws=true`).
- Frontend `archive-writer.js` writes `narrator` / `lori` rows via `POST /api/memory-archive/turn` (these carry the rich BUG-209-related metadata `session_id`, `session_style`, `identity_phase`, `bb_field`, `timestamp`).

WO-ARCHIVE-INTEGRATION-01 (shipped earlier this week) introduced the second writer assuming the backend wasn't writing — but `chat_ws` already was. Result: redundant transcript pollution.

## Root cause

Two write paths into the same `transcript.jsonl`:

1. `server/code/api/chat_ws.py` (backend, pre-existing) — writes per-WS-frame.
2. `ui/js/archive-writer.js` (frontend, this week) — auto-chained `onAssistantReply` plus inline call from `app.js sendUserMessage`.

The backend WS path was already writing the canonical transcript well before WO-ARCHIVE-INTEGRATION-01 landed. Adding the frontend writer on top duplicated every turn.

## Fix shape (surgical, reversible)

### 1. `ui/js/archive-writer.js`

Auto-chain on `window.onAssistantReply` is **off by default**. The chainer (`_wireAssistantReplyChain`) is exposed as `window._lvArchiveWireAutoChain` for opt-in. Default behavior on load: log `[archive-writer] auto-chain DISABLED (BUG-209: backend chat_ws is sole transcript writer)`.

To re-enable (only if backend WS path goes away):

```js
window._lvArchiveAutoChain = true;   // BEFORE archive-writer.js loads
// or post-load:
window._lvArchiveWireAutoChain();
```

`lvArchiveOnNarratorTurn(text)` and `lvArchiveOnLoriReply(text)` remain callable for deliberate per-turn writes (e.g. WO-AUDIO-NARRATOR-ONLY-01's audio-attachment flow may want to fire a paired write).

### 2. `ui/js/app.js`

The inline `lvArchiveOnNarratorTurn(text)` call in `sendUserMessage` is commented out (kept in source as a clear opt-in path for future use). Backend WS path now writes the narrator turn alone.

### 3. `ui/js/ui-health-check.js`

The `archive` category check renamed from "onAssistantReply chained for Lori transcript" to **"transcript writer wiring (BUG-209)"**. Now PASS when:
- auto-chain is OFF (`oar._archiveWriterChained !== true`)
- AND manual hooks `lvArchiveOnNarratorTurn` / `lvArchiveOnLoriReply` remain callable

WARNs if auto-chain is ON (will double-write).

## Verification (Chris does this in browser)

1. Hard refresh — load the new `archive-writer.js` and `app.js`.
2. Console should show: `[archive-writer] auto-chain DISABLED (BUG-209: backend chat_ws is sole transcript writer). Manual hooks ... remain callable for audio attachment.`
3. Talk with a test narrator (Corky) for 4–6 turns.
4. Bug Panel → Archive → click **Export Current Session**.
5. Open the new session's `transcript.jsonl`. **Each turn should appear exactly once**, with `role: "user"` or `role: "assistant"` and `meta.ws=true`. **No `narrator` or `lori` rows** for normal-flow turns.
6. Run **Full UI Check**. Archive category should report:
   - `transcript writer wiring (BUG-209)` → PASS, "auto-chain OFF (backend WS is single source); manual hooks present for audio attachment"

## What's lost (and why that's OK for now)

The rich `meta` block I added in WO-TRANSCRIPT-TAGGING-01 (`session_id`, `session_style`, `identity_phase`, `bb_field`, `timestamp`, `writer_role`) **only landed on the frontend writer's rows**. With the frontend writer disabled, those metadata fields don't appear on `meta.ws=true` rows from the backend.

Tradeoff is acceptable for now because:

- The backend already records `ts`, `role`, `content` per turn — that's enough for transcript review.
- `session_style` is captured at session-level via `meta.json` (`switch_*` session = one entry per narrator switch already).
- `bb_field`, `identity_phase`, and `session_id` are recoverable from `api.log` if needed for debugging.

**Follow-up WO (deferred):** push the rich metadata server-side so the backend WS writer stamps the same fields. That eliminates the loss without reintroducing the double-write. Out of scope for tonight (Chris's overnight rule: no backend changes).

## Files changed

```
ui/js/archive-writer.js   — auto-chain default OFF; opt-in via window._lvArchiveAutoChain or
                            window._lvArchiveWireAutoChain()
ui/js/app.js              — inline lvArchiveOnNarratorTurn call commented out (revert to re-enable)
ui/js/ui-health-check.js  — Archive category check rewritten to assert auto-chain is OFF
docs/reports/BUG-209_REPORT.md — this file
```

All three modified JS files parse clean (`node --check`).

## Status

- BUG-208: Bio Builder cross-narrator contamination — code landed (overnight), awaits Chris's morning live verify.
- **BUG-209: Archive transcript double-write — code landed (this morning), awaits Chris's morning live verify.**

Once both are verified clean, **Gate 1 + Gate 2 of the parent-session readiness checklist** start GREEN. Gates 3 (audio), 4 (export verified end-to-end), 5 (UI Health Check clean), 6 (test session reviewable end-to-end), 7 (live checklist exists — DONE) remain.
