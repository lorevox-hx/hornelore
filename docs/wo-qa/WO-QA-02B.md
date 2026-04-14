# WO-QA-02B — Seed Determinism Fix

**Status:** Complete (landed inside `b3fb8ff` alongside WO-QA-02)
**Owner area:** `server/code/api/routers/chat_ws.py`, `scripts/test_lab_runner.py`,
`scripts/test_lab_configs.json`

---

## Problem

WO-QA-01's first two baseline runs produced slightly different responses for
the same prompt at temp=0.3 and seed=0:

```
Run 1, structured/scn_5_word: "Where were you born, my friend?"
Run 2, structured/scn_5_word: "Where were you born, dear storyteller?"
```

Same config, same prompt, same `seed=0` in the config file. Output drifted.

Root cause: `chat_ws.py` was reading `params["seed"]` from the WS message but
never doing anything with it. The `model.generate()` call doesn't accept
`seed=` directly — torch's RNG state has to be set before `generate()` runs.
Without that, every request used whatever RNG state was left over from the
previous request, which made true regression testing impossible.

## Fix

Two changes in `chat_ws.py` (lines ~286–296):

```python
# Before generate():
_seed = params.get("seed")
if _seed is not None:
    try:
        torch.manual_seed(int(_seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(_seed))
    except Exception as _seed_err:
        logger.warning("[chat_ws][WO-QA-02B] seed apply failed: %s", _seed_err)
```

And on the harness side, `build_start_turn` in `scripts/test_lab_runner.py`
now forwards `seed` if the sampling config provides one:

```python
if sampling.get("seed") is not None:
    params["seed"] = int(sampling["seed"])
```

The config grid (`scripts/test_lab_configs.json`) already specifies `seed: 0`
for every cell, so all harness turns now go through the deterministic path.
Production UI turns omit `seed` entirely so live narrator behavior stays
naturally varied.

## Behavior contract

| Caller | `params.seed` | Outcome |
|---|---|---|
| WO-QA harness | always `0` | deterministic — same prompt → same response |
| Production UI | absent | torch RNG state inherited from previous request (current behavior) |
| Future ad-hoc | any int | torch reseeded before generate() |

## Verification

After applying this fix, two consecutive harness runs against the same config
should produce byte-identical responses for the same prompt. If they don't,
something else is non-deterministic upstream (chat template, prompt composer,
KV cache state) — that becomes a separate diagnostic.

## Why this matters for the harness

Without this, suppression deltas in `compare.json` are partly noise from
sampling variance, not just real config differences. With it, comparing
`qa02_20260414_154500` against `qa02_20260414_122140` gives a clean signal:
yield delta is attributable to the change being tested, not to RNG.
