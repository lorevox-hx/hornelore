# WO-QA-02 — Archive-Truth Methodology Patch

**Status:** Complete — `cfg_expressive` adopted as production default
**Production-default decision:** see [`WO-QA-02-RESULTS.md`](WO-QA-02-RESULTS.md)
**Commits:** `b3fb8ff` (main patch) + `7fe1520` (timing instrumentation)
**Owner area:** `scripts/test_lab_runner.py`, `data/test_lab/narrator_statements.json`,
`server/code/api/routers/test_lab.py`, `ui/`

---

## Problem WO-QA-02 solves

WO-QA-01 measured archive yield by extracting facts from **Lori's responses**.
But in production:

```
Narrator speaks  →  /api/extract-fields runs on narrator content  →  archive
Lori responds    →  no extraction
```

So the harness was measuring the wrong channel. The 0–3 yield numbers in the
first baseline (`20260414_122140`) reflect Lori asking questions back, not
narrators stating facts. The transcripts confirmed: every cell of cfg_archive
produced responses like *"Where were you born, my friend?"* — interviewer
behavior, not factual statements.

WO-QA-02 corrects this without breaking the existing harness.

## Two-channel architecture

```
CHANNEL A — Narrator content   (PRIMARY for archive-truth)
  Static narrator statements → /api/extract-fields
  → produces a per-narrator CEILING: max extractable yield from this fixture set

CHANNEL B — Lori responses     (SECONDARY for behavior)
  WS start_turn → Lori response → /api/extract-fields
  → produces lori_yield_total (lower than ceiling — Lori suppresses some content)
```

## The key reframing — Suppression as the ranking metric

Channel A is computed **once per narrator**, not per config. The extractor is
its own LLM with its own params; calling it on a fixed statement returns the
same yield regardless of what config is under test. Running Channel A inside
the config loop (as the spec originally proposed) would have produced identical
numbers across cfg_archive / cfg_balanced / cfg_expressive / cfg_focused — no
config differentiation at all.

Instead Channel A is the **ceiling**, and each config's ranking metric becomes:

```
suppression = ceiling - lori_yield_total
```

**Lower suppression = better.** A config that produces Lori responses that
preserve more of the narrator's truth content scores well. A config that makes
Lori hedge and self-censor scores poorly.

## Updated ranking

```
1. contamination PASS (gate — fail sinks to bottom)
2. suppression ASC   (lower = config preserves more narrator truth)
3. TTFT ASC          (faster wins)
4. human score DESC  (tie-break)
```

## New artifacts per run

| File | Contents |
|---|---|
| `narrator_ceilings.json` | Per-narrator ceiling totals + per-statement detail |
| `scores.json` | Now carries `suppression`, `archive_yield_ceiling`, `lori_yield_total` |
| `compare.json` | Now carries `suppression_delta` (replaces `yield_delta`) |
| `run_meta.json` | Timing summary: matrix duration, per-cell durations, avg/min/max |
| `progress.json` | Live progress (cells_completed/total, elapsed_sec, eta_sec) |

## New fixture: `data/test_lab/narrator_statements.json`

4 statements per narrator (Mara + Elena), aligned to the existing template
biographies. Each statement contains real extractable facts (names, dates,
places, occupations, kinship) that the extractor pipeline should recognize.

Example (Mara, statement 1):
> *"I was born in Helena, Montana on March 12, 1941. My father Elias Vale was
> a railroad mechanic for the Northern Pacific, and my mother Ruth Vale was a
> school secretary at Helena West Elementary."*

The launcher (`scripts/run_test_lab.sh`) preflight aborts loud if this file is
missing — silently degrading to "Lori channel only" would lose the suppression
metric.

## Backward compatibility

WO-QA-01 baseline runs (e.g. `20260414_122140`) remain valid as
**interviewer-quality baselines**. Their Lori-channel data is unchanged. They
load in the UI with empty Suppression / Ceiling cells (no Channel A data to
compute against), but TTFT, contamination, throughput, and human-score columns
still render. Comparing old → new runs falls back to inverted `yield_delta` so
the column is at least directional.

## UI changes

- New **Channel A — Narrator ceilings** table at the top of the results pane
  (Style / Ceiling / # Statements / Avg per Statement).
- Scores table gains: **Suppression** (primary), **Ceiling**, **Lori Yield**.
- Compare table: **Suppression Δ** replaces **Yield Δ**.
- Status line shows `· label=qa02_…` when a run label is set.
- Live status line shows `· N/M cells · elapsed Xm Ys · ETA Zm Ws` while running.
- New **Timing (loaded run)** pane shows total duration + per-cell breakdown
  sorted slowest-first.

## Launcher changes (`scripts/run_test_lab.sh`)

- Preflight: aborts loud if `data/test_lab/narrator_statements.json` is missing.
- Default labels new runs as `qa02_YYYYMMDD_HHMMSS` (caller's `--run-label` still wins).
- Auto-installs `httpx` and `websockets` if missing.

## Router changes (`server/code/api/routers/test_lab.py`)

- `/api/test-lab/results/{id}` now returns `narrator_ceilings` and `run_meta`.
- `/api/test-lab/status` overlays `progress.json` (when present) with live
  elapsed + ETA + cells_completed.
- `latest_run` always persisted explicitly on every status transition.

## Companion fix: WO-QA-02B (seed determinism)

Documented separately in `docs/wo-qa/WO-QA-02B.md`. `chat_ws.py` now honors
`params.seed` via `torch.manual_seed` + `torch.cuda.manual_seed_all` so
regression runs can reproduce identical responses. The harness sets `seed=0`
in its config grid.

## Strategic outcome

After WO-QA-02 the harness measures three orthogonal axes per run:

```
Behavior (scores)         — which configs preserve narrator truth (suppression)
Bottleneck (hardware)     — GPU- or CPU-bound, VRAM/RAM headroom
Pace (timing)             — wall-clock duration, per-cell breakdown, ETA
```

Together these answer "what config is best AND why it took as long as it did,"
and the saved baselines mean every future runtime change (TRT-LLM swap, model
update, prompt change) can be evaluated against the same yardstick.
