# BUG-LORI-LATENCY-VISIBILITY-01 — No operator-side or narrator-side surface for Lori response latency

**Status:** OPEN — quality-of-life issue surfaced 2026-05-06 by Chris during live testing.
**Severity:** AMBER — not a regression; it's missing observability that's load-bearing for parent-session calm-failure handling.
**Surfaced by:** Chris's question 2026-05-06 morning: "is there a way to track the model especially when lori is asked something it seems to take longer to respond"
**Author:** Chris + Claude (2026-05-06)
**Lane:** Lane 2 / parent-session readiness — quality-of-life additive.

---

## Problem

When Lori takes a long time to respond, neither the narrator nor the operator can tell:
- Is the LLM slow on this turn? (cold context window, complex prompt, VRAM pressure)
- Is TTS slow on this turn? (network, model swap, queue buildup)
- Has the request actually been sent, or is it stuck in a frontend queue?
- Is the WebSocket alive?

Narrator sees a generic `_lv80MirrorStatus("thinking")` indicator with no time elapsed. After 30 seconds of waiting, the narrator may type again or click an era thinking the request was lost — which produces the rapid-fire-message problem we saw in Mary's transcripts (multiple user inputs queued, only the last gets a response).

Operator sees nothing during the turn. After the fact, api.log has timing — but nothing live.

## Two-surface fix

**Surface 1 — Narrator-side "Lori is thinking…" with elapsed time.**

Existing: `_lv80MirrorStatus("thinking")` paints a static indicator.
Proposed: extend the indicator to show a small elapsed-time counter when the wait crosses a threshold:
- 0–5s: static "Lori is thinking…" (current behavior)
- 5–15s: "Lori is thinking… (5s)" — small monospace counter
- 15–30s: "Lori is thinking… (15s)" + a calm tone shift ("Take your time, she's gathering her thoughts")
- 30s+: "Lori is taking a moment — she'll be with you shortly" + suggestion to wait, NOT to retype

Per CLAUDE.md design principle 2 (no operator leakage) — the narrator never sees "WebSocket idle" or "LLM cold-start" or any system-tone vocabulary. Only narrator-friendly phrasing.

**Surface 2 — Operator-side Bug Panel latency widget.**

New tile in the existing operator-side Bug Panel showing the most recent N turns:
- turn timestamp
- prompt-build elapsed (frontend → /api/chat/ws send)
- LLM first-token elapsed (server-side)
- TTS first-audio elapsed (TTS server)
- total assistant-text-rendered elapsed
- a sparkline of the last 20 turns' total latencies

Reads from the existing `[lv80-turn-debug]` console markers + a new `[lori][latency]` server log line that emits per-turn timing summary.

Implementation:
- `chat_ws.py` — emit `[lori][latency] turn=N prompt_ms=X first_token_ms=Y done_ms=Z` per turn.
- `ui/js/app.js` — `lv80OnAssistantReply` already captures the assistant turn boundary; capture `_turnStartMs` when `sendChat` fires, compute elapsed deltas, log `[lv80-turn-debug] {event:'latency', prompt_ms, first_token_ms, total_ms}`.
- `ui/js/bug-panel-latency.js` (new) — IIFE reads the most recent 20 latency events from `state.session.recentTurnLatencies` (new ring buffer), renders the tile.
- `ui/css/bug-panel-latency.css` (new) — minimal styling matching the existing Bug Panel tiles.

## Acceptance gate

- Narrator-side: 30-second LLM stall produces "Lori is thinking… (15s)" instead of indefinite spinner.
- Operator-side: Bug Panel shows last 20 turn latencies with prompt/first-token/done split visible.
- No narrator-facing "WebSocket disconnected" / "LLM cold" / system-tone strings (principle 2 compliance).
- Existing `_lv80MirrorStatus("thinking")` still works — this is additive.

## Files (planned)

**New:**
- `ui/js/bug-panel-latency.js` (~150 lines)
- `ui/css/bug-panel-latency.css` (~50 lines)

**Modified:**
- `ui/js/app.js` — extend `_lv80MirrorStatus` with elapsed-time counter; wire `_turnStartMs` capture in sendChat; ring buffer for recent latencies.
- `ui/hornelore1.0.html` — mount new Bug Panel tile.
- `server/code/api/routers/chat_ws.py` — emit `[lori][latency]` per-turn log marker.

**Zero touch:**
- LLM prompt composition (no semantic change).
- Memory_echo / safety / correction composers.

## Risks and rollback

**Risk 1: counter feels intrusive.** Older narrators may find the elapsed counter anxiety-inducing. Mitigation: the counter only appears at 5s+ (skipping fast turns). At 5–15s the tone is neutral; at 15+ it's calming, not alarming.

**Risk 2: operator-tile read latency.** Bug Panel reading recentTurnLatencies on every paint could thrash. Mitigation: only re-render when the ring buffer mutates (single dirty flag).

**Rollback:** revert. No data loss; observability surfaces just disappear.

## Cross-references

- **Existing `_lv80MirrorStatus`** in `ui/js/app.js` — current static thinking indicator to extend.
- **WO-10C cognitive-support mode** — narrator-friendly tone for the calm "she's taking a moment" copy.
- **CLAUDE.md design principle 2** — no operator leakage. The 15s+ copy must be narrator-friendly, never reveal "WebSocket queue depth" or "VRAM pressure."

## Changelog

- 2026-05-06: Spec authored after Chris asked for latency tracking observability during live testing.
