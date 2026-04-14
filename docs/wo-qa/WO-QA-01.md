# WO-QA-01 — Hornelore Quality Harness

**Status:** Complete (with WO-QA-02 methodology supersession for the yield axis)
**Commits:** `6fdb2dc` → `7fe1520` (15 commits total including fixes)
**Owner area:** `scripts/test_lab_*`, `server/code/api/routers/test_lab.py`, `ui/js/test-narrator-lab.js`, `ui/css/test-narrator-lab.css`

---

## Purpose

Build a permanent quality measurement system for Hornelore that evaluates real system
behavior using the live websocket path, with objective scoring and reproducible
baselines. Not a one-time tuning sprint — the harness is the regression scaffolding
every future runtime change is measured against.

## Final shape

The harness is a standalone Python runner (`scripts/test_lab_runner.py`) plus an
operator-only popover in the Hornelore UI plus a thin FastAPI router that wires
them together. Nothing in the production interview path was changed; this is
purely additive infrastructure.

```
ui/js/test-narrator-lab.js       (popover JS — polls status/system/log every 2s)
ui/css/test-narrator-lab.css     (popover styling)
ui/hornelore1.0.html             (popover markup, dev-only 🧪 button)

server/code/api/routers/test_lab.py
  POST /api/test-lab/run         — launch harness in background subprocess
  GET  /api/test-lab/status      — running | finished | failed | idle (+ live progress)
  GET  /api/test-lab/results     — list run_ids by mtime DESC
  GET  /api/test-lab/results/{id}— scores / metrics / transcripts / compare /
                                    summary / configs / hardware_summary /
                                    narrator_ceilings / run_meta
  POST /api/test-lab/reset       — reset status.json to idle
  GET  /api/test-lab/gpu         — one-shot nvidia-smi parse
  GET  /api/test-lab/system      — consolidated GPU + CPU + RAM snapshot
  GET  /api/test-lab/log-tail    — last N lines of runner.log

scripts/run_test_lab.sh          (launcher: deps check → seed → run)
scripts/seed_test_narrators.py   (UPSERT 2 synthetic test narrators)
scripts/test_lab_runner.py       (the matrix runner; talks to /api/chat/ws)
scripts/test_lab_doctor.sh       (one-shot diagnostic + dry-run verifier)
scripts/test_lab_watch.sh        (compact terminal monitor, GPU+log+status)
scripts/test_lab_configs.json    (the 4-config grid)

data/test_lab/narrator_statements.json   (Channel A fixture — added in WO-QA-02)
data/narrator_templates/test_structured.json   (Mara Vale fixture)
data/narrator_templates/test_storyteller.json  (Elena March fixture)
```

## Two synthetic test narrators

`narrator_type='test'` so the existing reference-narrator write guards permanently
quarantine them from the family-truth pipeline.

| ID | Display name | Style | Built from |
|---|---|---|---|
| `test-structured-001` | Mara Vale | structured | Helena MT 1941, county clerk, fact-anchored |
| `test-storyteller-001` | Elena March | storyteller | Taos NM 1943, art teacher, narrative |

Both have rich fictional biographies in `data/narrator_templates/test_*.json` that
the seed script loads. They're meant to bracket the response-style axis.

## Config grid (4 purposive points, not exhaustive)

```
cfg_archive    T=0.3  p=0.90  r=1.15
cfg_balanced   T=0.5  p=0.95  r=1.10
cfg_expressive T=0.7  p=0.95  r=1.05
cfg_focused    T=0.5  p=0.85  r=1.15
```

Constants: `max_new_tokens=2048`, `seed=0`. `max_new_tokens` requires
`MAX_NEW_TOKENS_CHAT_HARD>=2048` in `.env` (verified by pre-flight check).

## Scenarios per (narrator × config)

```
scn_5_word           — 5-word discipline
scn_100_word         — 100-word response
scn_200_word         — 200-word response
scn_1000_word        — 1000-word stress test
scn_repetition       — degenerate input ("hello hello…")
+ real-prompt replay  — 3 typical interview prompts
+ scn_recovery       — same prompt before/after stress
+ scn_contamination  — Chris-style → Kent-style → return-to-Chris with anchor words
```

## Metrics captured

Lori channel (the existing flow):
- TTFT (ms), inter-token timestamps, total time, tokens/sec
- Coherence / adherence / style / stability scores (1–5 heuristic)
- Contamination PASS/FAIL (anchor-word detection)
- VRAM-pressure / OOM events per cell

Hardware (added in `ddcfbb2`, runs concurrent with matrix):
- GPU util %, VRAM used MiB, GPU temp C, GPU power W
- CPU util % (from /proc/stat delta)
- RAM used MiB
- Sampled every 5s, written to `hardware_timeseries.json` + `hardware_summary.json`

Timing (added in `7fe1520`):
- Total wall-clock duration
- Per-cell duration (saved in `run_meta.json`)
- Live elapsed + ETA exposed via `progress.json` and overlaid into status endpoint

## Run artifacts (per run, in `hornelore_data/test_lab/runs/<run_id>/`)

```
configs.json              — the config grid that was used
metrics.json              — every cell × scenario row (includes channel field)
transcripts.json          — first 18 prompts + responses for inspection
scores.json               — ranked configs (see WO-QA-02 for ranking semantics)
narrator_ceilings.json    — Channel A per-narrator ceilings (WO-QA-02)
run_meta.json             — timing summary (matrix start/end, per-cell, avg/min/max)
progress.json             — live progress (overwritten as cells complete)
hardware_timeseries.json  — every 5s GPU/CPU/RAM sample
hardware_summary.json     — aggregates (avg/peak GPU util, peak VRAM, etc.)
compare.json              — present only if --compare-to was passed
summary.md                — human-readable summary block
```

## Operator flow

1. Set `MAX_NEW_TOKENS_CHAT_HARD=2048` and `REPETITION_PENALTY_DEFAULT=1.1` in `.env`.
2. Restart the API.
3. Open Hornelore UI in Chrome.
4. F12 → Console → `document.getElementById("testLabPopover").showPopover()`
   (or enable dev-mode with `toggleDevMode()` to show the 🧪 button in the header).
5. Optionally tick "Dry run" to verify plumbing in ~30 seconds.
6. Optionally select a baseline run from "No compare baseline" dropdown.
7. Click **Run Harness**. Budget 45–90 minutes for a full matrix.
8. Live console pane shows GPU/CPU/RAM + runner log tail + elapsed/ETA.
9. When status flips to `finished`, pick the new run from "Select run to load".

CLI alternative (everything also runs from a WSL terminal):
```bash
cd /mnt/c/Users/chris/hornelore
bash scripts/run_test_lab.sh                            # full matrix
bash scripts/run_test_lab.sh --dry-run                  # plumbing check
bash scripts/run_test_lab.sh --compare-to <prior_run>   # regression vs baseline
bash scripts/test_lab_doctor.sh                         # one-shot health check
bash scripts/test_lab_watch.sh                          # terminal live monitor
```

## Backend changes that landed for WO-QA-01

- `chat_ws.py` — added `repetition_penalty` as a per-request param + env default.
- `.env.example` — documented `MAX_NEW_TOKENS_CHAT`, `MAX_NEW_TOKENS_CHAT_HARD`,
  `REPETITION_PENALTY_DEFAULT`.
- `main.py` — registers `test_lab.router`.

## What WO-QA-01 produced (first real baseline: `20260414_122140`)

Top finding: **`cfg_expressive` won on yield**, contradicting the "lower temp =
cleaner extraction" intuition. The combination of low temp + high repetition_penalty
in `cfg_archive` made Lori hedge and self-censor, starving the extractor.

Secondary findings:
- 7 of 8 cells passed contamination; storyteller × cfg_archive was the only fail.
- Throughput floor: ~5.4 tok/s — significantly below the 20–40 tok/s expected on
  a 5080 with Llama-3.1-8B INT4. Genuine optimization lead, deferred.
- Human scores (3.6–4.2) too tightly clustered to differentiate.

The methodology of measuring yield from Lori's responses was identified as
flawed (Lori asks questions; her responses don't contain narrator facts). This
led directly to WO-QA-02.

## Known limits / deferred

- **TTS drift validation** — placeholder returns `(None, None)`; real wiring
  deferred to WO-QA-01B (would need to expose `_wo11eTtsPlaybackStarted` chunk
  timestamps to the harness).
- **Per-narrator sampling params** — not yet supported. If WO-QA-02 confirms
  per-style optimal configs differ, a small chat_ws patch could allow narrators
  to carry their own defaults.
- **Throughput optimization** — the 5 tok/s floor finding is its own future
  WO. Hardware monitoring (added later) confirms whether GPU- or CPU-bound.
