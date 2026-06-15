# WO-EX-GPU-CONTEXT-01 — GPU memory + context-window resilience

**Title:** GPU memory + context-window resilience for narrator turns
**Status:** SCOPED
**Date:** 2026-05-01
**Lane:** Stack tuning / parent-session readiness blocker / extractor adjacent
**Source:** Parent-readiness narration matrix (2026-05-01) — 12/12 FAIL,
4 explicit GPU OOM errors, 6 timeouts, 1 partial reply with subsequent
follow-up failures, 1 silent timeout on a 67-word input.
**Blocks:** Live parent sessions until GREEN — Janice or Kent telling a
200-word story will hit this exact ceiling and see "GPU memory" errors.

---

## Mission

A narrator must never see a technical error message. When the LLM stack
runs out of GPU memory, hits a context-window limit, or otherwise fails
to produce a turn, the narrator-facing experience must remain coherent
and warm. Today's behavior — surfacing `Chat error: Not enough GPU
memory for this turn — please try a shorter message or try again
shortly` — is a dignity violation. An older narrator reading "GPU
memory" will close the laptop.

The work here splits into three layers:

1. **Stop the OOM from happening** in the first place by trimming
   prompt context aggressively before submission.
2. **When it still happens**, recover transparently: shorter context,
   retry, fall back gracefully, never surface tech vocabulary.
3. **Before parent sessions**, prove via the narration matrix that the
   stack handles 800-word turns and 30-minute conversations without
   OOM. The harness already exposes the failure surface; this WO
   closes it.

---

## Evidence — what we observed in today's run

12-pair narration matrix (`--narration-only`, 2026-05-01):

| Sample | Words | Result |
|---|---|---|
| narrator_002-clean | 823 | Lori responded to narration; ALL 5 follow-ups returned empty (cache pressure after long turn) |
| narrator_002-messy | 143 | `Chat error: Not enough GPU memory` |
| narrator_002-emotional | 193 | No reply within 90s (silent OOM or hang) |
| narrator_002-fragmented | 67 | No reply within 90s (should NOT OOM at this length — likely cache pressure after warmup turns) |
| narrator_003-clean | 825 | No reply within 90s |
| narrator_003-messy | 139 | No reply within 90s |
| narrator_003-emotional | 190 | `Chat error: Not enough GPU memory` |
| narrator_003-fragmented | 61 | No reply within 90s |
| narrator_004-clean | 803 | `Chat error: Not enough GPU memory` (then all 5 follow-ups OOM as well) |
| narrator_004-messy | 138 | No reply within 90s |
| narrator_004-emotional | 194 | No reply within 90s |
| narrator_004-fragmented | 66 | No reply within 90s |

Patterns:
- OOM hits at varying input lengths (140–825 words). Length alone isn't the predictor.
- Cumulative-turn cache pressure compounds. After a long narration turn, even short follow-ups (5–10 words) silent-fail.
- 60-word fragmented inputs fail too — suggests warmup state already consumed most VRAM.
- The harness was running multiple test narrators back-to-back without stack restart. KV cache + accumulated turn history across sessions may not be cleared between narrators.

GPU: NVIDIA RTX 50-series Blackwell per CLAUDE.md. Sufficient hardware in absolute terms; the issue is allocation discipline + context size, not raw capacity.

---

## Hard stop conditions

The narrator MUST never see any of these strings:

```
- "GPU memory"
- "Not enough memory"
- "context length"
- "token limit"
- "max_new_tokens"
- "CUDA"
- "VRAM"
- "OOM"
- Any traceback fragment
- Any ".py" filename
- Any HTTP status code
```

If the narrator-facing UI surfaces ANY of those during the acceptance
test, this WO is RED.

Approved fallback copy (warmth-preserving):

```
Narrator-facing on retry-able failure:
  "Let me think about that for a moment..."
  (Then auto-retry with trimmed context. If retry succeeds, deliver the
   real reply. If retry also fails, fall through to the line below.)

Narrator-facing on unrecoverable failure:
  "I'm having a little trouble keeping up. Can you say that again, maybe
   a bit shorter?"
  (Operator beacon notified. Watchdog triggered if pattern repeats.)
```

Never blame the narrator. "Try again" is OK. "Try shorter" is OK
phrased warmly. "Your message was too long" is NOT OK.

---

## Pre-flight gates (must be open before code lands)

This WO touches the LLM serving path. Don't open it until:

1. **TEST-08 closed** — narrator-incomplete era cycle resolved (#current).
   We need the harness fully green before we modify the prompt path.
2. **CLAUDE.md baseline locked** at `r5h` — extractor lane is at a
   known state, so any regressions caused by context trimming are
   attributable.
3. **#344 BUG-DBLOCK-01 closed or scoped separately** — long-held
   SQLite write locks during safety hooks are an adjacent blocker; we
   don't want OOM-retry traffic stacking on top of lock contention.

This WO does NOT block on parent-session-readiness pack closing.
It IS one of the parent-session-readiness blockers itself.

---

## Implementation surface

```
server/code/api/services/
  llm_context_budget.py            # NEW — input/context budget calculator
  llm_oom_recovery.py              # NEW — retry with trimmed context
  vram_probe.py                    # NEW — read nvidia-smi, log free VRAM per turn

server/code/api/
  prompt_composer.py               # MODIFY — accept context_budget, trim oldest turns
  routers/chat_ws.py               # MODIFY — wrap LLM call in OOM recovery
  routers/llm_serve.py             # MODIFY — explicit OOM detection + structured error
  routers/llm_warmup.py            # MODIFY — log post-warmup baseline VRAM

ui/js/
  app.js                           # MODIFY — never render "GPU memory" / etc; route to warm fallback
  state.js                         # MODIFY — track per-session VRAM-pressure indicators

scripts/monitor/
  vram_telemetry.py                # NEW — separate process logging VRAM per second to JSONL

docs/reports/
  GPU_OOM_BASELINE_2026-05-01.md   # NEW — captured today's evidence + initial diagnosis
  WO-EX-GPU-CONTEXT-01_REPORT.md   # NEW — final report when WO closes
```

---

## Architecture

### The three knobs

VRAM consumption per turn = `model_weights + kv_cache + activations`.

- `model_weights` is fixed at warmup (the LLM file). We don't touch it.
- `kv_cache` grows monotonically with conversation length until cleared. This is the silent killer.
- `activations` = (prompt_tokens + max_new_tokens) × per-token activation. Capped at request time.

Three knobs available to us:

1. **Trim prompt context** before submission so prompt_tokens stays bounded.
2. **Cap max_new_tokens** so activation peak is bounded.
3. **Reset KV cache** on natural session boundaries (narrator switch, idle >N min, explicit `Wrap Up Session`).

### Context trimming policy

Replace the current "send everything" composer behavior with a budget-aware composer:

```
context_budget_tokens =  available_vram_mb × tokens_per_mb_factor
  where tokens_per_mb_factor is calibrated per model (logged at warmup)

per-turn budget:
  reserved_for_response   = max_new_tokens (typically 256)
  reserved_for_system     = system_prompt + safety + capabilities (~600 tokens)
  reserved_for_runtime71  = current runtime71 dump (~400 tokens)
  reserved_for_directives = SYSTEM_QF + style directive (~200 tokens)
  budget_for_history      = context_budget_tokens − above

trim policy:
  - keep the most recent N turns from history (newest-first)
  - drop oldest turns when budget exceeded
  - ALWAYS keep: identity_complete summary, last 2 narrator turns, last 2 Lori turns
  - NEVER drop: the current narrator turn (the one being processed)
  - log the trim decision: `[ctx-trim] kept=X dropped=Y budget=Z used=W`
```

### OOM recovery flow

```python
def llm_serve_with_recovery(payload):
    try:
        return llm_serve(payload)
    except CudaOOMError:
        # Strategy 1: aggressive context trim
        trimmed = trim_to_minimum_viable(payload)  # last 1 user + last 1 lori turn
        try:
            return llm_serve(trimmed)
        except CudaOOMError:
            # Strategy 2: clear KV cache, retry
            llm.reset_kv_cache()
            try:
                return llm_serve(trimmed)
            except CudaOOMError:
                # Strategy 3: graceful fallback to warm message
                return WARM_FALLBACK_REPLY
```

### Never-leak invariant

The error surface from the LLM serve layer up through the WS to the UI
MUST be transformed at the API boundary. The chat_ws response payload
schema:

```json
{
  "reply_text": "Lori's actual reply OR warm fallback",
  "fallback": false | true,
  "reason": null | "context_overflow" | "oom_retry_failed" | ...,
  "internal_error": null | "<stripped detail for operator log only>"
}
```

The narrator-side UI reads `reply_text` and `fallback` only. It NEVER
reads `reason` or `internal_error` for display. Those exist only for
operator dashboard / log triage.

---

## Phase plan

### Phase 1 — Diagnose (instrumentation only, no behavior change)

Deliver:
- `vram_probe.py` — calls `nvidia-smi --query-gpu=memory.free,memory.used,memory.total --format=csv` per LLM call entry/exit. Logs `[vram] free_before=X free_after=Y delta=Z prompt_tokens=N max_new=M` to api.log.
- `llm_warmup.py` modification — log baseline VRAM after warmup completes. Log `[vram-baseline] free_after_warmup=X total=Y model_size_estimate=Z`.
- `llm_serve.py` modification — wrap LLM forward pass in try/except for `torch.cuda.OutOfMemoryError`; on catch, log structured `[oom] prompt_tokens=N max_new=M free_at_attempt=X` then re-raise.
- `scripts/monitor/vram_telemetry.py` — separate process, samples VRAM per second to `.runtime/monitor/vram_<timestamp>.jsonl`. Run in parallel with the main API.

Acceptance: re-run the harness's `--narration-only` matrix. Every OOM
gets a `[oom]` log line with prompt_tokens / max_new / free_at_attempt.
The 12 timeouts are categorized: "OOM but silent", "actually hung",
"timed out before submission", etc. Phase 1 produces a report:
`docs/reports/GPU_OOM_BASELINE_2026-05-01.md` enumerating actual root
causes, not symptoms.

**No product behavior change in Phase 1.** Just measurement.

### Phase 2 — Context-budget calculator + composer integration

Deliver:
- `llm_context_budget.py` — given current_vram_free, model_size, target max_new_tokens, returns a max_prompt_tokens budget. Calibrated empirically from Phase 1 data.
- `prompt_composer.py` modification — accepts a `context_budget` kwarg; when supplied, applies the trim policy from "Architecture / Context trimming". Emits `[ctx-trim]` log per call.
- All call sites of `compose_system_prompt` updated to pass the budget.

Acceptance: re-run `--narration-only`. Expected: zero OOMs on inputs ≤200 words. Some OOMs may persist on 800-word `clean` samples but only because those are genuinely large; recovery (Phase 3) handles them.

### Phase 3 — OOM recovery + graceful UI fallback

Deliver:
- `llm_oom_recovery.py` — implements the 3-strategy retry from "Architecture / OOM recovery flow".
- `chat_ws.py` modification — wraps LLM call in `llm_serve_with_recovery()`. On final fallback, emits the WARM_FALLBACK_REPLY constant.
- `ui/js/app.js` modification — error-rendering code that currently surfaces `Chat error: Not enough GPU memory...` is removed. Replaced with: if WS reply has `fallback: true`, render the warm-fallback text in normal Lori-bubble styling. Console gets a `[lori][fallback] reason=context_overflow` debug line, but the narrator UI shows only Lori's warm reply.
- Operator beacon receives `fallback_count` per session for the operator dashboard.

Acceptance: kill VRAM artificially (allocate dummy tensor to leave only 500MB free), send a 200-word narration. The narrator-facing UI shows "Let me think about that for a moment..." then either a recovered reply OR the gentle "I'm having a little trouble keeping up..." line. Never sees GPU/CUDA/OOM/Python tracebacks.

### Phase 4 — KV cache lifecycle

Deliver:
- KV cache reset on natural session boundaries: narrator switch (already exists for state, extend to LLM cache), idle >15 min, explicit `Wrap Up Session`, watchdog-triggered restart.
- Per-session KV cache budget — track cache size, log to operator beacon.
- Optional: per-turn cache compression (model-supported only; if not supported by the current LLM, skip this).

Acceptance: 30-minute continuous narrator session. VRAM telemetry shows KV cache growing then plateauing (or being managed). No OOM from cache pressure alone.

### Phase 5 — Eval gate

Deliver:
- Re-run the parent-readiness `--narration-only` matrix.
- Re-run with a stress variant: same 12 pairs but back-to-back-to-back without stack restart.
- Re-run a 30-minute continuous-conversation simulation per the manual MANUAL-PARENT-READINESS-V1 pack (when authored).

Pass criteria:
- ≥10/12 of the narration matrix PASS or AMBER (allow 2 to be AMBER for genuinely-too-long inputs that recover via fallback).
- Zero "GPU memory" or other tech-error strings in any narrator-facing surface.
- 30-minute continuous session ends without OOM.
- Operator dashboard shows `fallback_count` per session — non-zero is OK and expected; zero is the goal but not the gate.

### Phase 6 — Operator dashboard surface

Deliver:
- Operator dashboard card (gated behind existing `HORNELORE_OPERATOR_STACK_DASHBOARD=1` flag) showing per-session: total turns, fallback count, max VRAM used, longest single-turn duration. Helps Chris see when a kiosk is degrading before parents notice.

Acceptance: the dashboard shows real-time VRAM + fallback metrics per active narrator. Already-built dashboard surface; this is a new card.

---

## Safety / dignity constraints

- Never surface technical vocabulary to the narrator. Period. The hard-stop list in this WO is enforced via UI test.
- Fallback copy must be reviewed in pre-existing voice tests against a soft-spoken older narrator's expected reaction. "Let me think about that for a moment..." is OK; "Loading..." is NOT.
- Auto-retry latency must stay under 5 seconds total for the warmth-fallback line to feel natural. If retry takes longer, deliver the fallback line first to maintain conversational rhythm.
- Session continues even after fallback. The WO does NOT permit ending a session because the LLM OOM'd. Lori always has the next turn.
- Operator beacon (per WO-PARENT-KIOSK-01 Phase 7) carries fallback metrics so Chris sees patterns remotely — without any transcript content.
- Watchdog (per WO-PARENT-KIOSK-01 Phase 6) escalates if fallback count exceeds 5 per session. Soft-restart restores headroom.

---

## Acceptance gate

This WO is complete when:

1. Phase 1 baseline report is filed at `docs/reports/GPU_OOM_BASELINE_2026-05-01.md` with structured root-cause categories per the 12 narration failures.
2. Context-budget calculator is in place and the composer trims aggressively.
3. OOM recovery never lets a tech error reach the narrator.
4. The narration matrix scores ≥10/12 PASS or AMBER, zero tech-error surface.
5. A 30-minute continuous-conversation simulation completes without OOM.
6. The operator dashboard surfaces per-session fallback metrics.
7. Acceptance run is documented at `docs/reports/WO-EX-GPU-CONTEXT-01_REPORT.md` with VRAM telemetry plots, before/after narration matrix, and per-phase deltas.

---

## Scope explicitly NOT in this WO

- Switching to a smaller-context model (separate decision; scoped under Hermes 3 / Qwen A/B in CLAUDE.md changelog).
- Streaming/chunked LLM output (separate WO).
- Multi-GPU sharding (RTX 50-series single GPU is the target; if budget-trim doesn't fit on one card, hardware decision is upstream).
- Quantization changes (model is pre-quantized; this WO doesn't change quant level).
- Extractor-side context (extract.py runs separately; this WO touches conversational LLM serving only).

---

## Dependencies

- **Hardware:** RTX 50-series Blackwell, single GPU, current
- **Software:** Existing PyTorch + transformers + vLLM (or whatever the active serve path is); `nvidia-smi` on PATH
- **Telemetry:** `.runtime/monitor/` directory writable for `vram_telemetry.py` JSONL output
- **Time:** Phase 1–3 ~2 days focused; Phase 4–5 ~1 day; Phase 6 ~half-day. ~3.5 days total.

---

## Suggested commit sequence

```
feat(stack): WO-EX-GPU-CONTEXT-01 Phase 1 — VRAM probe + OOM logging instrumentation
docs(stack): WO-EX-GPU-CONTEXT-01 Phase 1 — GPU OOM baseline report
feat(stack): WO-EX-GPU-CONTEXT-01 Phase 2 — context-budget calculator + composer trim
feat(stack): WO-EX-GPU-CONTEXT-01 Phase 3 — OOM recovery + warm UI fallback
feat(stack): WO-EX-GPU-CONTEXT-01 Phase 4 — KV cache lifecycle on session boundaries
docs(stack): WO-EX-GPU-CONTEXT-01 Phase 5 — narration matrix + 30-min stress eval
feat(stack): WO-EX-GPU-CONTEXT-01 Phase 6 — operator dashboard fallback metrics card
docs(stack): WO-EX-GPU-CONTEXT-01 — final report
```

---

## Revision history

- v1, 2026-05-01 — initial scope. Authored after the parent-readiness
  narration matrix exposed 12/12 failures, 4 explicit GPU OOMs, and
  the "Lori responded but follow-ups failed" cache-pressure pattern.
  Six phases plus two doc deliverables. Pre-flight gates require
  TEST-08 closure and r5h baseline lock so any regressions caused by
  context trimming are attributable cleanly.
