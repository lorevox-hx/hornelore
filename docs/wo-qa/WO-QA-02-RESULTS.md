# WO-QA-02 Results — `cfg_expressive` adopted as production default

**Decision date:** 2026-04-14
**Baselines used:** `qa02_20260414_151527` (Run 1), `qa02_20260414_160221` (Run 2)
**Hardware:** RTX 5080 (16 GB), 128 GB RAM, WSL2 Ubuntu 24.04, Llama-3.1-8B-Instruct INT4 (bitsandbytes)
**Stack at decision time:** `b3fb8ff` (WO-QA-02 main) + `7fe1520` (timing) + WO-QA-02B seed patch in `chat_ws.py`

---

## Production default selected

```
cfg_expressive
  temperature        = 0.7
  top_p              = 0.95
  repetition_penalty = 1.05
  max_new_tokens     = 2048   (harness ceiling; live chat caps at 512 per request)
```

Live-chat defaults applied (`.env`):

```
MAX_NEW_TOKENS_CHAT=512
MAX_NEW_TOKENS_CHAT_HARD=2048
REPETITION_PENALTY_DEFAULT=1.05
```

`temperature=0.7` and `max_new_tokens=512` are sent explicitly by the UI on
every chat request (`ui/js/app.js` line ~5248), so they're already at the
winning values in production. `top_p=0.95` is the chat_ws hardcoded fallback
and matches the winner. The two `.env` changes (`REPETITION_PENALTY_DEFAULT`
1.1 → 1.05 and `MAX_NEW_TOKENS_CHAT` 256 → 512) bring the env back-stops
into line with the live UI behavior so nothing silently overrides the winner
when the UI doesn't supply a value.

---

## Rationale

```
Production default selected: cfg_expressive
Rationale:
  - stable top-ranked config across two runs
  - suppression metric noise floor approximately ±4
  - contamination probe flicker observed, but no config displaced cfg_expressive
  - hardware/timing profile stable across runs
```

### Cross-run summary

| Metric | Run 1 | Run 2 | Stability |
|---|---|---|---|
| Total runtime | 17m 56s | 18m 0s | ±0.4% |
| Avg cell duration | 134.5s | 134.8s | ±0.2% |
| GPU util avg | 25.5% | 24.6% | ±0.9 pp |
| GPU util peak | 100% | 100% | identical |
| VRAM peak | 7105 MiB | 7225 MiB | +120 MiB |
| CPU util avg | 6.0% | 6.0% | identical |
| **Top-ranked config (overall)** | **cfg_expressive** | **cfg_expressive** | **stable** |

### Suppression deltas Run 1 → Run 2

| Style | Config | Run 1 | Run 2 | Δ |
|---|---|---|---|---|
| structured | cfg_expressive | 11 | 10 | -1 |
| structured | cfg_archive | 13 | 13 | 0 |
| structured | cfg_focused | 14 | 11 | -3 |
| structured | cfg_balanced | 12 | 13 | +1 |
| storyteller | cfg_expressive | 14 | 10 | -4 |
| storyteller | cfg_balanced | 15 | 15 | 0 |
| storyteller | cfg_focused | 16 | 16 | 0 |
| storyteller | cfg_archive | 18 | 16 | -2 |

Per-cell deltas range 0 to −4. **Practical noise floor: ±4 on suppression.**

### Contamination flicker

Two cells flipped between runs in opposite directions (`structured/cfg_balanced`
FAIL→PASS, `structured/cfg_expressive` PASS→FAIL). Treated as **probe flicker
at current scale**, not real config interactions.

> **Going forward:** treat the contamination probe as
> - **strong signal** if a config fails repeatedly across runs
> - **weak signal** if it flips once
>
> Don't displace a winner on a single contamination flip.

---

## Why the harness isn't byte-deterministic

The seed-determinism patch (WO-QA-02B) calls `torch.manual_seed(0)` before
every `model.generate()`, but two sources of CUDA non-determinism remain:

1. **bitsandbytes INT4 dequant kernels** use atomic ops in some paths
2. **CUDA attention/matmul** floating-point accumulation order isn't
   deterministic by default

Even the `/api/extract-fields` endpoint inherits this — `storyteller/st_104`
yielded 2 facts in Run 1 and 0 facts in Run 2 from the same input.

True byte-determinism would require:

```
torch.use_deterministic_algorithms(True)
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
CUBLAS_WORKSPACE_CONFIG=:4096:8
```

…with a 20–30% throughput cost. **Not worth it for a product decision** when
the winner is stable across runs anyway. Documented as deferred WO-QA-04 if
research interest emerges.

---

## Caveats for future harness use

- Don't overinterpret 1-point suppression differences between nearby configs.
  The harness is precise enough to pick a winner from the four-config grid,
  not precise enough to declare significance on every small delta.
- The extractor (`/api/extract-fields`) is non-deterministic too. Channel A
  ceilings will vary slightly run to run; treat them as approximate caps,
  not exact ground truth.
- Hardware/timing numbers are reproducible run-to-run; trust those for
  regression detection (e.g., a future runtime change that adds 30s to
  avg_cell is a real signal).

---

## Recommended next moves (ordered)

1. **Done:** `.env` updated with cfg_expressive defaults
2. **Pending:** restart API to pick up the env changes (`bash scripts/restart_api.sh`)
3. **Pending:** sanity-check 3–5 real narrator turns (Chris/Kent/Janice) to
   confirm the new defaults feel right in live use
4. **Then:** WO-QA-03 / TTS Option A — `--with-tts` flag on the harness for
   end-to-end latency + GPU contention measurement. The TTS-instrumented
   first run becomes the post-tuning baseline that captures the full
   user-perceived experience.
5. **If ever:** WO-QA-04 — true byte-determinism investigation. Set the four
   PyTorch deterministic flags above, accept the throughput hit, re-run to
   establish a noise-zero baseline. Research question, not product need.

---

## Files touched at adoption time

| File | Change |
|---|---|
| `.env` | `REPETITION_PENALTY_DEFAULT` 1.1 → 1.05, `MAX_NEW_TOKENS_CHAT` 256 → 512 |
| `.env.example` | Same, plus updated comment block citing this results doc |
| `docs/wo-qa/WO-QA-02-RESULTS.md` | This file (new) |
| `README.md` | Work order table marks WO-QA-02 with adopted defaults |

Operator follow-up after pulling these changes: `bash scripts/restart_api.sh`,
then test 3–5 turns. No code changes required.
