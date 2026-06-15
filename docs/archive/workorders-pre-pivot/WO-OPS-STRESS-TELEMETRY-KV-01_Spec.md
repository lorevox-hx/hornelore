# WO-OPS-STRESS-TELEMETRY-KV-01 — Stress run telemetry + KV/VRAM cleanup

**Status:** ACTIVE (lands after v11/v12 confirms harness baseline; runs after that)
**Origin:** 2026-05-04 — quick harness proves behavior one narrator at a time. Full TEST-22 stress (3 voices + long-life cascade) needs cleanup + telemetry to produce real engineering data instead of false REDs from accumulated VRAM/KV pressure.
**Sequencing:** Phase A (KV-clear endpoint) → Phase B (telemetry hooks) → Phase C (CLI flags) → Phase D (stress run + report).

---

## Purpose

Make the full TEST-22 stress run produce real engineering data instead of false REDs from accumulated VRAM/KV pressure.

**Reason:** The quick harness proves behavior one narrator at a time. The full stress run adds multiple voices and long-life cascade pressure. Without cleanup and telemetry, a RED result only tells us "something failed." With cleanup and telemetry, RED tells us *why*.

---

## Scope

1. Add KV/VRAM clear endpoint
2. Add telemetry snapshots to rehearsal harness
3. Add prompt-token histogram
4. Add stress-run report section
5. Run full TEST-22 with all voices and turns

---

## Phase A — KV-clear endpoint

`POST /api/operator/stack-dashboard/clear-kv`

**Behavior:**
- `gc.collect()`
- `torch.cuda.empty_cache()`
- `torch.cuda.ipc_collect()`
- `torch.cuda.synchronize()`
- Returns `{before_mb, after_mb, freed_mb, elapsed_ms, gc_collected_objects}`
- Gated behind `HORNELORE_OPERATOR_CLEAR_KV=1` AND `HORNELORE_OPERATOR_STACK_DASHBOARD=1` (compounds existing dashboard gate to avoid widening the surface)

**Implementation:** lives inside `routers/operator_stack_dashboard.py` as a new endpoint. Reuses `stack_monitor.collect_gpu(force=True)` for before/after VRAM snapshots.

**Pre-work review:**
- `torch.cuda.synchronize()` BEFORE the cleanup, to ensure any in-flight ops complete before we measure
- `force=True` on `collect_gpu` to bypass the 4s cache (otherwise after_mb might equal before_mb)
- Total elapsed_ms cap at 30s (safety — if clear takes longer than that something is genuinely wrong)
- Logged as `[stack-dashboard][clear-kv]` so post-run grep can correlate

---

## Phase B — Telemetry hooks in rehearsal harness

**New helper:** `_capture_telemetry_snapshot(label: str, extra: dict) -> dict` in `run_parent_session_rehearsal_harness.py`.

**Behavior:** calls `GET /api/operator/stack-dashboard/summary`, captures:
- VRAM (used/free/total MB, util_percent, temperature_c)
- CPU% + RAM (used/free/total MB)
- Process uptime + warnings
- Active conv_id count (from stack_monitor's session collector)

Plus harness-side context:
- `label` (e.g. `run_start`, `voice_start:hearth`, `after_clear_kv:hearth`)
- `wall_clock_ts` (ISO-8601)
- `elapsed_ms_since_run_start`
- `extra` dict for context-specific fields (era_id, voice_id, etc.)

**Snapshot points:**
- `run_start`
- `voice_start:<voice_id>` + `voice_end:<voice_id>` for each voice
- `after_clear_kv:<voice_id>` immediately after KV-clear call
- `lifemap_era_click:<era_id>`
- `shatner_identity_complete` / `shatner_identity_failed`
- `test22_era_click:<voice_id>:<era_id>`
- `run_end`

---

## Phase C — Telemetry derived metrics

**Built once per run, after all snapshots collected:**

| Metric | Source |
|---|---|
| Peak VRAM per voice | max(vram_used_mb) within voice_start..voice_end window |
| KV-clear effectiveness | freed_mb avg + variance across all clear-kv calls |
| FK constraint count | grep `[chat_ws][softened] turn_count increment failed` in api.log run window |
| comm_control trim count + reasons | grep `[chat_ws][comm_control] changed=True` in run window |
| sendSystemPrompt timeout count | grep `[WO-11][chat-state]` in run window |
| Phase G disconnect count | grep `[chat-ws] Phase G: WebSocket disconnected` in run window |
| GPU OOM count | grep `Not enough GPU memory` in run window |
| story_candidates created | DB count delta (run_start vs run_end) |
| BB fields populated per narrator | per-narrator BB read at run_end |
| RAM peak | max(ram_used_mb) across all snapshots |
| CPU peak | max(cpu_percent) across all snapshots |
| **prompt_tokens histogram** | grep `[chat_ws][WO-10M] prompt_tokens=N` from api.log run window; emit min/p25/median/p75/p95/max + bucketed histogram (1k/2k/3k/4k/5k/6k/7k+); flag if monotonically growing >N% per turn |
| Generation time per turn | api.log delta: `[chat_ws] turn` start ts → next user-side event |

---

## Phase D — Telemetry file

`docs/reports/parent_rehearsal_<tag>.telemetry.json`

**Top-level shape:**

```json
{
  "tag": "stress_v1",
  "run_start": "2026-05-04T12:00:00Z",
  "run_end": "2026-05-04T12:18:42Z",
  "elapsed_seconds": 1122,
  "snapshots": [{ ... }, { ... }, ...],
  "kv_clears": [
    {"label": "after_clear_kv:hearth", "before_mb": 8123.4,
     "after_mb": 6450.0, "freed_mb": 1673.4, "elapsed_ms": 145,
     "gc_collected_objects": 1024}
  ],
  "derived_metrics": {
    "peak_vram_per_voice": {...},
    "fk_constraint_count": 27,
    "comm_control_trim_count": 12,
    "phase_g_disconnect_count": 1,
    "gpu_oom_count": 0,
    "send_system_prompt_timeouts": 0,
    "prompt_tokens_summary": {
      "n": 47,
      "min": 1247, "p25": 3547, "median": 4198, "p75": 5651,
      "p95": 6851, "max": 7124,
      "histogram": {
        "0-1000": 0, "1000-2000": 1, "2000-3000": 0,
        "3000-4000": 18, "4000-5000": 12, "5000-6000": 9,
        "6000-7000": 6, "7000+": 1
      },
      "monotonic_growth_pct_per_turn": 4.2
    }
  }
}
```

---

## Phase E — Stress-run report sections

**New markdown sections in `parent_rehearsal_<tag>.md`** when `--emit-telemetry` is on:

1. **Stress Summary** — one-paragraph high-level pass/fail with key numbers
2. **VRAM Before/After Each Voice** — table with peak/min/avg per voice
3. **KV Clear Effectiveness** — table with before/after/freed per clear
4. **Prompt Token Histogram** — ASCII bar chart + summary stats
5. **Generation Time by Turn** — per-turn latency table
6. **FK Error Count** — total + per-voice breakdown
7. **comm_control Trim Count** — total + reasons
8. **Phase G Disconnect Count** — count + correlation with active turn timing
9. **GPU OOM Count** — count + which voice/era
10. **TEST-22 Era Cascade Results** — per-era pass/fail across voices
11. **Memory Recall Result** — long-life cascade memory recall step result
12. **Final Fix List** — sorted by severity (RED → AMBER) with category tag

---

## CLI flags

```
--clear-kv-between-voices    # opt in to KV cleanup between voice loops
--emit-telemetry             # opt in to telemetry capture + report sections
                             # auto-enabled when --include-long-life
```

---

## Run after v11/v12 passes

```bash
python -m scripts.ui.run_parent_session_rehearsal_harness \
  --mode standard \
  --include-long-life \
  --clear-kv-between-voices \
  --emit-telemetry \
  --tag stress_v1
```

---

## Acceptance gates

**PASS:**
- No GPU OOM
- No Phase G disconnect during active turn
- KV clear frees or stabilizes VRAM (post-clear value ≤ pre-clear value)
- All voices complete (each runs T1-T6)
- TEST-22 reaches all 7 eras across all 3 voices
- Memory recall step at end of long-life cascade runs

**AMBER (note but not block):**
- prompt_tokens > 5000 on any turn
- Generation time > 60s on any turn
- comm_control trims frequent (>30% of turns)
- Timeline / Memoir downstream subscribers still informational-only (separate WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01)

**RED (blocks parent sessions):**
- GPU OOM
- WebSocket disconnect during active turn
- TEST-22 aborts before era steps
- Identity intake cannot complete
- Cross-narrator contamination (BB shows wrong narrator's data)
- DB write to wrong narrator

---

## Report-after rule

After stress_v1 completes, do not summarize casually. Produce:

1. **What passed**
2. **What failed**
3. **Which failures are product bugs**
4. **Which failures are runtime/VRAM bugs**
5. **Which failures are harness bugs**
6. **Exact next work order(s)** — concrete file paths + scope estimate

---

## Files this WO touches

**Phase A (endpoint):**
- `server/code/api/routers/operator_stack_dashboard.py` — add `clear-kv` route
- `.env.example` — add `HORNELORE_OPERATOR_CLEAR_KV=0`

**Phase B-C (harness):**
- `scripts/ui/run_parent_session_rehearsal_harness.py` — telemetry helper, CLI flags, snapshot calls, KV-clear hook between voices, derived metrics aggregator, telemetry JSON writer, stress report section emitter

**Phase D-E (outputs):**
- `docs/reports/parent_rehearsal_stress_v1.telemetry.json` (new file format)
- `docs/reports/parent_rehearsal_stress_v1.md` (extended sections)

---

## Non-negotiables

- KV clear endpoint must be SAFE on Llama-3.1-8B-Q4 — `torch.cuda.empty_cache()` + `gc.collect()` are documented-safe operations. `torch.cuda.synchronize()` waits for in-flight ops; that's the right semantics.
- Telemetry must NEVER block harness flow — every snapshot wrapped in try/except, missing values render as `null` not exception.
- Must work without nvidia-smi present — gracefully degrade to `null` GPU metrics, harness still completes.
- Telemetry payload size capped — don't blow up the JSON file with noise. Cap snapshots at ~1MB total per run.
