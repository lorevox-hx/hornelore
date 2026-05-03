# WO-OPS-VRAM-VISIBILITY-01 — Phase 0 Audit

**Date:** 2026-05-03
**Auditor:** Claude (sandbox read-only inspection)
**Scope:** Determine what VRAM-related infrastructure already exists in the Hornelore stack so subsequent phases EXTEND rather than DUPLICATE.

---

## Headline finding

**The vast majority of WO-OPS-VRAM-VISIBILITY-01 is already built.** CLAUDE.md tasks #333–#337 (resource dashboard backend / router / monitor / Bug Panel widget) shipped 2026-04-29 and already capture, expose, and display VRAM. The remaining work is **two small wires + one test artifact**.

**Estimated cost was ~half session (~4 hours).** Actual remaining cost is **~1 hour** because Phases 1–3 collapse to "confirm, don't rebuild."

---

## What was audited

| File | Path | Bytes | Last touched |
|---|---|---:|---|
| `stack_monitor.py` | `server/code/api/services/` | 40,147 | 2026-04-29 |
| `operator_stack_dashboard.py` | `server/code/api/routers/` | 13,510 | 2026-04-29 |
| `bug-panel-dashboard.js` | `ui/js/` | 22,958 | 2026-05-01 |
| `bug-panel-dashboard.css` | `ui/css/` | 8,466 | 2026-04-29 |
| `chat_ws.py` (BLOCKING-turn site) | `server/code/api/routers/` | (large) | recent |
| `run_question_bank_extraction_eval.py` (discipline header) | `scripts/archive/` | 107,598 | 2026-04-29 |
| `stack_resource_logger.py` | `scripts/` | (NOT FOUND) | — |

---

## Phase-by-phase audit

### Phase 0 — Audit (this memo) ✓

Done.

### Phase 1 — VRAM snapshot fields ✓ ALREADY EXISTS

`stack_monitor.py` L239-318 implements `collect_gpu()` with:
- nvidia-smi query: `name,utilization.gpu,memory.used,memory.total,memory.free,temperature.gpu,power.draw`
- 4-second cache (`_GPU_CACHE_TTL_SEC = 4.0`, L96)
- 2-second subprocess timeout
- Graceful failure modes:
  - `FileNotFoundError` → `{"status": "unavailable", "error": "nvidia-smi not on PATH"}`
  - `TimeoutExpired` → `{"status": "unavailable", "error": "nvidia-smi timed out (>2s)"}`
  - Generic exception → `{"status": "unavailable", "error": "nvidia-smi failed: {e}"}`
- Threshold env vars: `DASH_VRAM_FREE_AMBER_MB=2048`, `DASH_VRAM_FREE_RED_MB=512`

Returns normalized:
```python
{
    "status": "ok",
    "name": "NVIDIA GeForce RTX 5080",
    "util_percent": 12,
    "vram_used_mb": 8120,
    "vram_total_mb": 16384,
    "vram_free_mb": 8264,
    "temperature_c": 54,
    "power_draw_w": 95,
}
```

**Phase 1 status: NO ACTION NEEDED. Already built and operationally correct.**

### Phase 2 — Rolling peak/trend ✓ MOSTLY EXISTS, ONE GAP

`operator_stack_dashboard.py` exposes:
- `GET /summary` — current snapshot via `stack_monitor.build_summary()`
- `GET /history?minutes=N` (1–120) — rolling history from `.runtime/monitor/latest.jsonl`
- `GET /system-status` — compatibility alias

The `/history` endpoint reads from a JSONL written by `stack_resource_logger.py` — **but that script is NOT at the expected path** (`scripts/stack_resource_logger.py`). The endpoint gracefully returns `{"available": False, "rows": []}` if the file is missing. So either the logger lives elsewhere or it's not running. Either way, the read-side machinery exists.

**Gap:** The `vram_guard_blocks_last_hour` counter from the WO spec — i.e., counting `[chat_ws][WO-10M] BLOCKING turn` events — is NOT currently exposed anywhere. The chat_ws.py side logs the event at WARNING but no aggregator counts them.

**Phase 2 status: ONE WIRE TO ADD — guard-block counter in `stack_monitor.py` + 1-line increment call from `chat_ws.py` BLOCKING site.**

### Phase 3 — Bug Panel surface ✓ ALREADY EXISTS

`bug-panel-dashboard.js`:
- L242 `_renderGpuCard(gpu)` — full GPU/VRAM card
- Shows: name, util %, VRAM used / total, free, temperature, power
- L276 `_sparkline(_historyValues("gpu.vram_used_mb"))` — visual trend
- L253 unavailable handling: "nvidia-smi not available"
- Already wired into the operator dashboard mounting at L442-444

Status badging (OK / WATCH / DANGER per the WO spec) is the only minor enhancement — current widget shows raw numbers but doesn't badge them. **Defer this enhancement** until guard-block counter (Phase 2 gap above) is wired, then both can be added in one Bug Panel polish pass.

**Phase 3 status: NO ACTION NEEDED for v1. Optional badging polish later.**

### Phase 4 — Eval discipline header ⚠ DOES NOT EXIST

`scripts/archive/run_question_bank_extraction_eval.py`:
- Discipline header builder around L216-330
- Currently captures: `eval_tag`, `started_at`, `mode`, `git_sha`, `git_dirty`, `branch`, `flags`, `api_endpoint`, `api_model`, `api_log_last_line_age_seconds`, `warmup_probe`, `scorer_version`, `case_bank_version`
- **NO VRAM snapshot block.**

The natural slot is alongside `warmup_probe` — call `nvidia-smi` once before the eval starts and once after, capture the delta and peak.

**Phase 4 status: ADD `vram_snapshot` block. ~30 lines.**

### Phase 5 — Baseline bench ⚠ NOT RUN

Awaiting Chris to run on the live RTX 5080 stack. Specific sequence:
1. Start the stack normally, let it warm.
2. Capture nvidia-smi snapshot (idle loaded).
3. Run a typical interview turn through Lori, capture during + 5s after.
4. Run a long-prompt turn (SPANTAG-on or equivalent), capture during + 5s after.
5. Bank readings to `docs/reports/WO-OPS-VRAM-VISIBILITY-01_BASELINE.md`.

**Phase 5 status: BLOCKED on Chris's hardware-side bench (~10 min when the stack is warm).**

---

## Summary table

| Phase | Status | Action |
|---|---|---|
| 0 — Audit | ✓ Complete | This memo |
| 1 — VRAM snapshot | ✓ Already exists | None |
| 2 — Rolling peak/trend | ⚠ One wire | Add `vram_guard_blocks` counter (10 lines in stack_monitor + 1 in chat_ws) |
| 3 — Bug Panel widget | ✓ Already exists | Optional badge polish later |
| 4 — Eval discipline header | ⚠ Add `vram_snapshot` | ~30 lines in run_question_bank_extraction_eval.py |
| 5 — Baseline bench | ⏳ Awaits Chris | Hardware-side, ~10 min |

---

## Revised cost estimate

```
Phase 0 (this audit):        DONE (~30 min)
Phase 2 wire (guard counter): ~15 min code + AST validate
Phase 4 vram_snapshot block:  ~30 min code + AST validate
Phase 5 baseline bench:       ~10 min on Chris's machine

Total remaining:  ~55 min code + 10 min Chris bench = ~1 hour total
```

Down from the WO's original ~4 hour estimate, because the heavy lifting (Phases 1–3) was already done by tasks #333–#337.

---

## What this means for the locked principle

The WO's principle — *"Verified VRAM beats estimated VRAM"* — gets its first verified data point as soon as Phase 5 baseline bench banks. Until then, the README's "RTX 5080 working envelope" table (`~8-9 idle / ~10-11 normal / ~13-15 long / OOM worst`) remains a **working hypothesis grounded in plausible math**, not measurement.

After Phase 5 banks, every subsequent eval also writes a per-run `vram_snapshot` to its discipline header, so we accumulate a real distribution over time instead of repeating estimation arguments.

---

## Recommendation

Ship Phase 2 wire + Phase 4 block in this same session (the work is small and contained). Hand Phase 5 bench to Chris as a 10-minute task once his stack is warm. Total elapsed: this session.
