# WO-OPS-VRAM-VISIBILITY-01 — Real VRAM measurement, Bug Panel visibility, eval-harness discipline header

**Status:** SCOPED — ready for implementation, ~half session
**Date:** 2026-05-03
**Lane:** Ops / parent-session safety / model-swap readiness
**Blocks:** Any ASR model swap (Whisper → Canary-Qwen) or chat-side model swap (Llama → PersonaPlex). No model swap proceeds until the long-tail VRAM curve is measured, not estimated.
**Sequencing:** Independent of all extractor lanes. Independent rollback per phase. Touches `services/stack_monitor.py` + `routers/operator_stack_dashboard.py` + Bug Panel JS + the two eval-harness scripts. Zero extract.py touch. Zero Lori behavior change. Zero narrator-facing change.
**Lights up:** the 3-agent (Claude / ChatGPT / Gemini) convergence on "verified VRAM beats estimated VRAM"; the Janice-regression class of failures that proves model swaps don't fix binding bugs; and the next time `[chat_ws][WO-10M] BLOCKING turn` fires, we'll know exactly what conditions produced it.

---

## 0. Locked principle

> **Verified VRAM beats estimated VRAM.**

Plausible model-sizing math is not the same as measured runtime behavior on Chris's RTX 5080 with the Hornelore stack actually warm. This WO replaces estimation with measurement.

No ASR / chat-model swap proceeds until the eval-harness VRAM curve shows safe headroom on the long-tail SPANTAG-on case across at least 5 consecutive runs.

---

## 1. Why this exists

The 3-agent triangulation (Claude + ChatGPT + Gemini, 2026-05-03) produced a stable model-tier decision (see README "Listening before hearing"):

- Keep Llama 3.1-8B Q4 + TTS live stack
- Sandbox Canary-Qwen as Archive-only ASR experiment
- Defer PersonaPlex (sub-300ms latency is wrong-target for elder narrators)
- Post-session only for Nemotron 3 Nano 30B-A3B

But the working VRAM numbers in that decision are estimates:

```
Idle floor:                  ~8-9 GB
Normal active turn:          ~10-11 GB
Long prompt / SPANTAG:       ~13-15 GB
Worst case observed:         OOM (6 HTTP 500s on 2026-04-27)
```

These are credible but unverified. The `VRAM_GUARD` in `chat_ws.py:23-24,766-816` exists because the long tail does spike past safe headroom — but we don't have the per-turn distribution that tells us *how often*, *under what prompt shapes*, or *whether Canary-Qwen would safely co-resident with the current stack*.

This WO produces that data on three surfaces.

---

## 2. What this WO is NOT

```
- NOT a model swap.
  This WO does not switch ASR or LLM. It only adds visibility.

- NOT a behavior change.
  Lori, the extractor, the narrator UI all remain byte-stable.
  No env flag changes. No prompt changes. No schema changes.

- NOT a new monitoring infrastructure.
  We already have stack_monitor.py + operator_stack_dashboard.py
  + the Bug Panel dashboard widget + stack_resource_logger.py
  (CLAUDE.md tasks #333-#337). This WO extends what exists rather
  than building parallel.

- NOT a continuous-recording surface.
  No DB writes per VRAM sample. In-memory rolling stats only.
  Per-eval banked snapshots write to the existing eval JSON
  reports + a single baseline doc.
```

---

## 3. Scope: three surfaces, one data source

| Surface | Audience | Cadence | Purpose |
|---|---|---|---|
| Bug Panel widget | Operator (live during parent session) | Real-time poll, ~10s | Catch dangerous turns mid-session |
| Eval harness discipline header | Developer (post-eval review) | Per-eval-run | Build historical distribution; prove headroom claim |
| One-off baseline bench report | Developer (today) | Single run | Establish baseline numbers in `docs/reports/` |

All three read from the same `nvidia-smi` capture. Phase 0 confirms whether `stack_monitor.py` already does this; Phase 1 adds it if not.

---

## 4. Phase 0 — Audit existing monitor (READ-ONLY)

Inspect:

```text
server/code/api/services/stack_monitor.py
server/code/api/routers/operator_stack_dashboard.py
ui/js/bug-panel-dashboard.js
ui/css/bug-panel-dashboard.css
scripts/stack_resource_logger.py
scripts/archive/run_question_bank_extraction_eval.py
scripts/archive/run_golfball_interview_eval.py (if exists)
scripts/archive/run_sentence_diagram_story_survey.py
```

Determine:
1. Does `stack_monitor.py` capture VRAM today? If yes, in what shape?
2. Does the Bug Panel dashboard widget surface it?
3. Do any of the eval harnesses capture or report VRAM?
4. Are there any pre-existing nvidia-smi calls in the codebase that should be the canonical source?

**Output:** A 1-page audit memo at `docs/reports/WO-OPS-VRAM-VISIBILITY-01_PHASE_0_AUDIT.md` with a table of "what exists / what's missing" so subsequent phases extend rather than duplicate.

**Acceptance:** Phase 0 is complete when the audit memo is written and the implementation plan for Phase 1 is sized against the actual gap (not assumed gap).

---

## 5. Phase 1 — Add VRAM snapshot fields (or confirm existing)

If `stack_monitor.py` does not already capture VRAM, add a minimal probe.

Canonical capture command:

```bash
nvidia-smi --query-gpu=memory.used,memory.free,memory.total,utilization.gpu \
           --format=csv,noheader,nounits
```

Expected normalized return shape:

```python
{
    "gpu": {
        "vram_total_mb": 16384,
        "vram_used_mb": 8120,
        "vram_free_mb": 8264,
        "gpu_util_percent": 12,
        "captured_at": "2026-05-03T18:42:11Z"
    }
}
```

Implementation rules:
- Subprocess timeout 2 seconds (don't block live narrator turns on a slow nvidia-smi).
- Failure mode: return None + log `[stack_monitor][vram] capture failed: {exc}` at WARNING. Never raise.
- Cache for 1 second to avoid hammering nvidia-smi on dashboard polls.
- If `nvidia-smi` is unavailable (non-NVIDIA dev box), gracefully return `{"gpu": {"available": false}}`.

Read-only. No behavior change. No DB writes.

---

## 6. Phase 2 — Rolling peak/trend (in-memory)

Track lightweight rolling stats inside `stack_monitor.py`:

```python
{
    "current_used_mb": 8120,
    "current_free_mb": 8264,
    "peak_used_mb_last_hour": 14100,
    "avg_used_mb_last_hour": 10300,
    "min_free_mb_last_hour": 1880,
    "samples_last_hour": 360,
    "vram_guard_blocks_last_hour": 0,
}
```

Rolling window = 360 samples × 10s poll = 1 hour, in a `collections.deque(maxlen=360)`. Memory cost: ~30 KB. Resets on stack restart (acceptable — restart events themselves are observable).

`vram_guard_blocks_last_hour` reads from a counter incremented at the existing `[chat_ws][WO-10M] BLOCKING turn` log emission point in `chat_ws.py:801-816`. If that counter doesn't exist yet, add it (~5 lines).

---

## 7. Phase 3 — Bug Panel surface

Add a card to the existing Bug Panel dashboard widget (`ui/js/bug-panel-dashboard.js`):

```
GPU / VRAM
─────────────────────────────────
Current:    8.1 GB used / 8.2 GB free
Peak (1h):  14.1 GB
Min free (1h): 1.9 GB
Guard blocks (1h): 0
Status: OK
```

Status thresholds (operator-facing badge color):

```
OK      → free > 2500 MB AND guard_blocks_last_hour == 0
WATCH   → free 1000-2500 MB OR guard_blocks_last_hour > 0
DANGER  → free < 1000 MB OR guard_blocks_last_hour ≥ 3 in last hour
```

Polls the existing operator-stack-dashboard endpoint every 10s when Bug Panel is open. Backs off to 60s when Bug Panel is hidden (visibility API).

**Narrator never sees this surface.** Same posture as the existing Bug Panel — operator-only, never narrator-visible.

---

## 8. Phase 4 — Eval discipline header

Extend the existing `[discipline]` block in `scripts/archive/run_question_bank_extraction_eval.py` (and any other eval harness with the discipline header) to include a `vram_snapshot` block, mirroring the existing `warmup_probe`:

```
[discipline] vram_snapshot:
  pre_eval_total_mb=16384
  pre_eval_free_mb=8200
  pre_eval_used_mb=7800
  post_eval_peak_used_mb=14100
  post_eval_avg_used_mb=10300
  post_eval_min_free_mb=1800
  guard_blocks_during_eval=0
  capture_method=nvidia-smi
  classification: ok | watch | danger
```

The same object goes into the eval JSON report under `discipline.vram_snapshot` so future automation can consume it.

Capture cadence during the eval run: every 5 seconds via background thread, or per-case (one before + one after each case). The per-case approach is simpler and gives us per-case attribution ("case_080 spiked to 14.2GB").

---

## 9. Phase 5 — Baseline bench (the immediate data point)

Run three measured workloads from a freshly-warm stack:

| Scenario | What | Expected VRAM range |
|---|---|---|
| **A. Idle loaded** | Stack warm, no active turn for 60 seconds | ~8-9 GB |
| **B. Normal turn** | One typical interview turn (~1500 token prompt, ~300 token response) | ~10-11 GB |
| **C. Long prompt** | One SPANTAG-on style turn (~6k token prompt, full extractor pipeline) | ~13-15 GB |

For each scenario, capture:
- Start used / start free (immediately before)
- Peak used (max across the turn)
- Min free (min across the turn)
- End used / end free (5s after turn completes)
- Guard blocks observed
- Wall-clock duration
- Any error events

Bank results at:

```
docs/reports/WO-OPS-VRAM-VISIBILITY-01_BASELINE.md
```

Report format:

```markdown
# WO-OPS-VRAM-VISIBILITY-01 — Baseline VRAM Bench

**Date:** 2026-05-XX
**Hardware:** RTX 5080 16GB
**Stack:** Llama 3.1-8B Q4 + Coqui VITS + Whisper + Hornelore extractor
**Measurement:** nvidia-smi sampled every 1s during each scenario

| Scenario | Start used | Peak used | Min free | End used | Duration | Guard blocks | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| A. Idle loaded | | | | | | | |
| B. Normal turn | | | | | | | |
| C. Long prompt | | | | | | | |

## Baseline interpretation

(Operator-readable narrative comparing measured numbers to the README's working-hypothesis estimates. Confirms or revises the README's
"Idle floor / Normal turn / Long prompt / Worst case" table.)

## Implications for model-swap decisions

- Canary-Qwen swap headroom: (used_mb_canary_qwen + min_free_during_long_prompt) ≤ 16384?
- PersonaPlex headroom: would require dropping Llama 3.1-8B from VRAM
- Nemotron 30B-A3B: confirmed not viable for live narrator session
```

This is the single most important deliverable from this WO. Until this report exists, every model-sizing argument is theory.

---

## 10. Locked design rules

```
1. nvidia-smi only.
   Don't introduce nvml-python or pyvNVML dependencies. The
   existing stack_monitor.py likely already shells out to
   nvidia-smi for other metrics; we use the same surface.

2. Read-only on production behavior.
   This WO never changes Lori behavior, extractor behavior,
   eval scoring, or narrator UI. It only OBSERVES.

3. Operator-only visibility.
   The Bug Panel widget is operator-only. Narrator never sees
   VRAM badges, guard-block counters, or any system metric.

4. In-memory rolling stats — no DB writes per sample.
   The Phase 2 rolling stats live in process memory.
   Eval-harness snapshots persist via the existing eval JSON
   report write (one row per eval run), not per-sample.

5. Failure-tolerant.
   nvidia-smi failure → log WARNING + return None. Never raise.
   Never block a live narrator turn waiting for VRAM data.

6. Cadence respects the live session.
   Bug Panel polls 10s when visible, 60s when hidden.
   Eval harness captures pre/post per case (or 5s background
   thread, but per-case is simpler and gives attribution).
```

---

## 11. Acceptance gates

```
Phase 0  [ ] Audit memo banked at
             docs/reports/WO-OPS-VRAM-VISIBILITY-01_PHASE_0_AUDIT.md
         [ ] Phase 1+ scope sized against actual gap

Phase 1  [ ] stack_monitor.py captures VRAM (or confirmed already does)
         [ ] Failure mode tested (nvidia-smi unavailable returns
             {"gpu": {"available": false}})
         [ ] Subprocess timeout 2s honored
         [ ] No new dependencies added

Phase 2  [ ] Rolling stats accessible from operator_stack_dashboard
             endpoint
         [ ] vram_guard_blocks_last_hour counter incremented at the
             existing chat_ws.py:801-816 BLOCKING-turn point

Phase 3  [ ] Bug Panel widget shows the GPU/VRAM card with current,
             peak, min free, guard-block count, status badge
         [ ] OK / WATCH / DANGER thresholds correctly applied
         [ ] Narrator UI byte-stable (no leakage to narrator surface)

Phase 4  [ ] Eval discipline header includes vram_snapshot block
         [ ] Same object in eval JSON report under
             discipline.vram_snapshot
         [ ] Per-case attribution available (which case spiked highest)

Phase 5  [ ] Baseline bench report banked at
             docs/reports/WO-OPS-VRAM-VISIBILITY-01_BASELINE.md
         [ ] All three scenarios measured (idle / normal / long)
         [ ] README "RTX 5080 working envelope" table either
             confirmed or revised based on real numbers
```

---

## 12. What this unlocks

After Phase 5 banks, we have a defensible answer to:

1. **"Can we swap Whisper → Canary-Qwen safely?"**
   Answer becomes: Canary-Qwen 8-bit ≈ 6.5 GB (per NVIDIA card). If `min_free_during_long_prompt` from Phase 5 baseline > 6.5 GB + 1 GB safety margin, the swap is viable. Otherwise the long tail puts us in DANGER.

2. **"How often does the long tail actually fire?"**
   Phase 4 eval-discipline data over 30+ runs gives us a real distribution of `peak_used_mb_during_eval`. We can predict guard-block frequency under future workloads.

3. **"Is the SPANTAG default-on rejection still correct?"**
   The 2026-04-27 r5f-spantag-on-v3 attempt was REJECTED at -39 cases. Some of that was binding hallucination, but VRAM pressure may have contributed. Phase 5 measurement of scenario C (Long prompt / SPANTAG) tells us whether SPANTAG-on is even physically feasible without the OOM tail.

4. **"What's the actual headroom for adding a second model?"**
   PersonaPlex defer is correct on latency grounds (sub-300ms wrong-target for elder narrators), but the VRAM math also matters. Phase 5 settles whether it's 0 GB headroom, 4 GB headroom, or somewhere between.

---

## 13. Sequencing relative to other lanes

```
WO-LORI-SENTENCE-DIAGRAM-RESPONSE-01 Phase 1   ← Lori behavior measurement (parallel, also in-flight)
WO-NARRATIVE-CUE-LIBRARY-01 Phase 2            ← cue detector code (parallel)
WO-OPS-VRAM-VISIBILITY-01                      ← THIS (ops measurement, parallel)
WO-EX-BINDING-01 second iter                   ← extractor binding (parallel)
[any future ASR / chat model swap]             ← BLOCKED until this WO Phase 5 banks baseline
```

This WO is independent of all extractor / Lori / cue lanes. Can land in parallel with anything.

---

## 14. Cost estimate

```
Phase 0 (audit memo):            ~30 min reading + 30 min writing
Phase 1 (VRAM capture if missing): ~30 min code + tests
Phase 2 (rolling stats):           ~45 min code + smoke
Phase 3 (Bug Panel widget):        ~45 min JS/CSS
Phase 4 (eval discipline header):  ~30 min × 2-3 harness scripts = ~1 hr
Phase 5 (baseline bench):          ~10 min run + 30 min writeup
                                   ─────
Total:                             ~half session (~4 hours)
```

If Phase 0 reveals `stack_monitor.py` already captures VRAM (likely, given tasks #333-#337), Phases 1+2 collapse to minutes and total drops to ~2 hours.

---

## 15. Bumper sticker

```
Verified VRAM beats estimated VRAM.
Verified WER on Janice's voice beats benchmarked WER on synthetic test sets.
Verified narrator trust beats both.

Measure before swap.
```

---

## 16. Citation context

- `chat_ws.py` L20-24 + L766-816 — the existing WO-10M VRAM_GUARD that this WO builds visibility around
- CLAUDE.md tasks #333-#337 — the existing stack_monitor.py + operator_stack_dashboard.py + Bug Panel dashboard work this WO extends
- README "Listening before hearing" section (banked 2026-05-03) — the strategic frame that justifies this WO existing
- 3-agent triangulation 2026-05-03 (Claude / ChatGPT / Gemini) — the convergent design discussion that produced the "verified VRAM beats estimated VRAM" principle
