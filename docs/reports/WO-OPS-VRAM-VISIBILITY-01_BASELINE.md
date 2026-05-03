# WO-OPS-VRAM-VISIBILITY-01 — Baseline VRAM Bench

**Date:** 2026-05-03
**Hardware:** RTX 5080 16GB
**Stack:** Llama 3.1-8B Q4 + Coqui VITS + Whisper + Hornelore extractor
**Method:** nvidia-smi sampled every 1s during each scenario; raw logs at
            `docs/reports/WO-OPS-VRAM-VISIBILITY-01_BASELINE.raw.log` (SPANTAG-off, 8 scenarios)
            `docs/reports/WO-OPS-VRAM-VISIBILITY-01_BASELINE_SPANTAG_ON.raw.log` (SPANTAG-on, 1 scenario)

---

## Headline

Real measured VRAM is **substantially lower than the README hypothesis** for
typical workloads. The 13–15 GB / OOM tail noted in the README envelope was an
estimate, not a measurement; today's bench finds steady-state operation for both
SPANTAG-OFF and SPANTAG-ON workloads sits in the **~6.0–8.0 GB band** on the warm
RTX 5080 stack with Llama 3.1-8B Q4 + Coqui VITS resident.

This unlocks **headroom for a co-resident Archive-only ASR experiment**
(Canary-Qwen 4-bit ~3 GB) without exceeding the 16 GB ceiling, subject to the
Listening-before-hearing constraint that the ASR feeds the Archive only — never
bypassing the Review Queue.

---

## Results (SPANTAG default-OFF — locked production state)

| Scenario | Workload | Peak used (MB) | Min free (MB) | Avg used (MB) | Samples |
|---|---|---:|---:|---:|---:|
| A. Idle loaded | model resident, no active turn | 5,868 | 10,110 | 5,868 | 1 |
| B. P020 curl | /api/extract-fields, 20-word prompt | 7,954 | 8,024 | 7,954 | 34 |
| C. P030 curl | 30-word prompt | 7,954 | 8,024 | 7,954 | 50 |
| D. P100 curl | 100-word prompt | 7,954 | 8,024 | 7,954 | 53 |
| E. P280 curl | 280-word prompt | 7,954 | 8,024 | 7,954 | 55 |
| F. P1000 curl | 1000-word prompt | 7,954 | 8,024 | 7,954 | 53 |
| G. Eval slice | master eval, 5 long-prompt cases | 7,954 | 8,024 | 7,954 | 222 |
| H. Sentence-diagram-survey | chat + extract + frame, ~9 cases | 8,036 | 6,370 | 7,623 | 295 |

(Scenario A is a single-shot snapshot. Earlier raw-log peak-analysis reported
"10,110 MB" for Scenario A — that was an awk-parser bug grabbing the FREE
column on a non-row-numbered line; corrected here. B–G all pinned within
sub-MB across hundreds of samples; the LLM either holds an answer in flight at
~7,954 MB or is at idle at ~5,868 MB, with no intermediate states observed
at 1s resolution.)

---

## Results (SPANTAG default-ON, BINDING-01 PATCH 1-4 also active)

| Scenario | Workload | Peak used (MB) | Min free (MB) | Samples |
|---|---|---:|---:|---:|
| I. Eval slice SPANTAG-on | master eval, 10 cases (case_001/005/008/018/028/033/077/082/087/110) | 6,974 | 9,004 | 240 |

**Discipline-header trap surfaced:** the eval-script's discipline header reported
`HORNELORE_SPANTAG=0 (default)` even though the server was actually SPANTAG-on
(verified by `/proc/<uvicorn-PID>/environ` carrying `HORNELORE_SPANTAG=1`, plus
4 fresh `[extract][spantag] flag ON` log lines for 2026-05-03 from the Stage-1
warmup curl). The discipline header reads the eval-script's `os.environ`, not
the running uvicorn process's. **Not authoritative for SPANTAG state** — the
server-process env (`/proc/<PID>/environ`) and the per-request log marker
(`[extract][spantag] flag ON`) are the only authoritative checks. Worth a
follow-up patch to the eval discipline header to read the live server env via
the API (or to mark this field "(eval-shell only — not server)").

---

## VRAM-vs-prompt-length curve

VRAM does NOT scale linearly with prompt length on the curl-driven scenarios.
B (20 words) through F (1000 words) all pinned at 7,954 MB used. The LLM
allocates working memory for the answer at extraction time, and the difference
between a 20-word and 1000-word input prompt is invisible at 1s sampling
resolution on this stack.

The real spread shows up under realistic eval flow (H = 8,036 peak vs B–G
7,954 pinned, +82 MB) and under fallback execution (the 3 `rules_fallback`
emissions in Scenario I likely contributed to the slightly LOWER 6,974 peak —
fallback doesn't allocate the same KV-cache-heavy working set as a full LLM
forward pass).

---

## VRAM_GUARD blocks observed during bench

Bug Panel widget reports **0** `vram_guard_blocks_last_hour` across the entire
bench window (Scenarios A–I, ~25 minutes wall clock). No turn was blocked by
the WO-10M VRAM_GUARD during any scenario. The new counter (banked today
under WO-OPS-VRAM-VISIBILITY-01 Phase 2) is green and operational.

---

## README envelope: confirms or revises?

README hypothesis (working until verified) — **OVERESTIMATE**:

| Hypothesis | Measured |
|---|---|
| Idle floor: ~8–9 GB | **5.9 GB** (32–35% lower) |
| Normal active turn: ~10–11 GB | **8.0 GB** (20–27% lower) |
| Long prompt: ~13–15 GB | **8.0 GB** SPANTAG-off (38–47% lower) |
| SPANTAG pressure: ~13–15 GB | **7.0 GB** SPANTAG-on (46–53% lower) |
| Worst case observed | OOM (2026-04-27, 6 HTTP 500s) — **historical, not reproduced** |

**Verdict: REVISES.** Real footprint is 20–50% lower than the README hypothesis
for both SPANTAG-OFF and SPANTAG-ON across all benched scenarios. The
"(working hypothesis)" caveat is dropped from the SPANTAG-OFF rows. The
SPANTAG-on long-prompt tail keeps the caveat (caveat 1 below).

---

## Headroom for model-swap decisions

- **Canary-Qwen 4-bit (~3 GB) — co-resident in Archive-only mode:**
  Min free during bench = 6,370 MB (Scenario H, sentence-diagram-survey).
  Need ≥ 4,000 MB (3 GB model + 1 GB safety margin).
  **Verdict: FITS** with ~2.4 GB margin. Recommend sandbox install + WER
  measurement against Janice + Kent voice profiles before any production wire.

- **Canary-Qwen 8-bit (~6.5 GB) — co-resident in Archive-only mode:**
  Min free 6,370 MB. Need ≥ 7,500 MB.
  **Verdict: TIGHT.** Would leave negative margin under H workload. Not safe.

- **PersonaPlex 7B 4-bit (~6 GB):**
  Same headroom math as Canary 8-bit, plus the locked semantic objection
  (PersonaPlex's 300ms full-duplex turn-taking is wrong-target for the older
  narrator population per WO-10C 120s/300s/600s silence cadence).
  **Verdict: NOT VIABLE as live co-resident.**

- **Nemotron 30B-A3B:**
  Confirmed not viable for live narrator session. Reasonable for offline
  overnight reasoning experiments only.

---

## Three caveats this bench does NOT resolve

1. **Long-prompt SPANTAG tail.** Today's SPANTAG-on slice exercised 10 cases
   from the 114-case master pack. The historical OOM (2026-04-27, 6 HTTP 500s)
   was on the full master with rare ~6k-token cases. A follow-up targeted
   SPANTAG-on bench against case_044 + case_069 specifically (the two known
   long-prompt cases) is needed before the SPANTAG envelope can be declared
   fully verified. While SPANTAG stays default-OFF (locked), this is a parked
   risk, not a live one.

2. **1-second sampling resolution.** nvidia-smi polled every 1s may miss
   sub-second peaks during model forward passes. For tighter envelope work,
   sample at 100ms or use NVML's event API.

3. **Cold-boot envelope.** Today's bench was on a warm stack. Cold-boot
   transient allocations (model loading, accelerate dispatch) may exceed
   steady-state and were not measured here.

---

## What this changes for the model-swap decision

**Lock:** Canary-Qwen 4-bit Archive-only sandbox is **GREEN to proceed**.
The headroom math is solid (2.4 GB margin under realistic workload); the
residual risk is the long-prompt SPANTAG tail (caveat 1 above), which only
matters if SPANTAG re-enables under BINDING-01 second iteration. While SPANTAG
stays default-OFF, no risk.

**Defer:** PersonaPlex stays parked on locked semantic grounds (older narrator
silence cadence > sub-300ms turn-taking).

**Keep:** Llama 3.1-8B Q4 + Coqui VITS as the production stack. No swap.

---

## Bonus finding: SPANTAG-on extraction-quality regression confirmed

Eval slice with SPANTAG-on (Scenario I) yielded 3/10 = 30% pass rate vs the
same slice run SPANTAG-off this morning at 7/10 = 70%. parse_success_rate
dropped from ~95% to 70%, rules_fallback rose from 0% to 30%. Same stubborn-pack
PRIMARY cases (case_018 and case_082) that pass on SPANTAG-off both fail under
SPANTAG-on. Two new failure modes surfaced in the failure_pack: case_001
schema_gap (pass on SPANTAG-off) and case_028 field_path_mismatch
`hobbies.hobbies` (pass on SPANTAG-off).

This confirms the 2026-04-27 r5f-spantag-on-v3 rejection at the slice level:
SPANTAG-on default-active is not viable until BINDING-01's binding-hallucination
containment lands its second iteration. **WO-OPS-VRAM-VISIBILITY-01 verified
the VRAM concern is not the gating problem; the extraction-quality regression
is.**

`HORNELORE_SPANTAG=0` discipline lock holds. The default-off `.bat` shortcut
pair (`Start Hornelore SPANTAG ON.bat` / `Stop Hornelore SPANTAG OFF.bat`,
banked today) makes future SPANTAG-on benches one-click without risking the
default-off discipline.
