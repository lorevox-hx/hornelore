# Laptop checklist — Spanish live readiness test

Printable. One page. Do these in order.

---

## 1. Pull latest

```
cd /mnt/c/Users/chris/hornelore
git pull
```

Confirm last commit is `WO-SPANISH-LIVE-READINESS-01 — six patches for
laptop live use`.

---

## 2. Verify .env (per LAPTOP_HANDOFF_KOKORO_INSTALL.md)

```
cat .env | grep -E "LORI_TTS_ENGINE|KOKORO_VOICE|HF_HUB"
```

Required:

```
LORI_TTS_ENGINE=kokoro
LORI_TTS_KOKORO_VOICE_EN=af_heart
LORI_TTS_KOKORO_VOICE_ES=ef_dora
HF_HUB_CACHE=/home/<you>/.cache/huggingface/hub
HUGGINGFACE_HUB_CACHE=/home/<you>/.cache/huggingface/hub
HF_HUB_OFFLINE=1
```

If anything missing, follow `LAPTOP_HANDOFF_KOKORO_INSTALL.md` Step 8.

---

## 3. Verify Kokoro install + voices

```
.venv-gpu/bin/python scripts/setup/smoke_kokoro.py
```

Should print success + an audio sample.

If it fails: `bash scripts/setup/install_kokoro.sh` then retry.

---

## 4. Verify websockets package

```
.venv-gpu/bin/python -c "import websockets; print(websockets.__version__)"
```

If ImportError: `.venv-gpu/bin/pip install websockets`.

---

## 5. Start stack

```
./scripts/start_all.sh
```

**WAIT ~4 minutes.** HTTP listener comes up in ~60s but Llama +
Kokoro warmup continues for another 2-3 minutes. Don't run the smoke
harness until the api.log stops growing rapidly.

Quick check stack is up:

```
curl -s http://localhost:8000/ | head -5
```

---

## 5b. Optional focused unit gates (fast, ~2 min total)

Before the live smoke, you can run the Spanish-relevant unit packs to
catch any regression introduced by the WO patches before burning a
live-stack turn:

```
.venv-gpu/bin/python -m unittest discover -s tests/boris_quality -v
.venv-gpu/bin/python -m unittest \
  tests.test_code_switching_eval_fixtures \
  tests.test_compose_memory_echo_spanish \
  tests.test_compose_correction_ack_spanish \
  tests.test_lori_spanish_guard \
  -v
```

Boris should still report `40/40 OK`. The four Spanish packs should
report green or have only known-stale failures (e.g. the cs_001
"has_spanish_marker" case that's been flaky pre-patch — not a
regression introduced today).

If you want to skip this and go straight to live, go to step 6.

---

## 6. Run Spanish live smoke harness

```
cd /mnt/c/Users/chris/hornelore
python3 scripts/run_spanish_live_smoke.py
```

Takes ~5-10 minutes (6 turns × ~30-60s each + setup).

Watch for the final verdict line:

```
✓ GREEN     ← ≥ 33/36 cells passed — ready for real Spanish live use
• AMBER     ← 30-32/36 — stochastic variance; re-run once
✗ RED       ← < 30/36 — Spanish runtime needs more work
```

---

## 7. Read the report

```
ls -t docs/reports/spanish_live_smoke_*.txt | head -1 | xargs cat
```

Or open in editor:

```
ls -t docs/reports/spanish_live_smoke_*.txt | head -1
```

The report has per-turn breakdown + a 6×6 contract matrix.

---

## 8. Send back what's needed

If GREEN: just send "GREEN" — I'll know what to do next.

If AMBER or RED: send the entire report file. The per-turn verbatim
Lori responses + ✗ markers tell me exactly what regressed and where
to patch.

Email or copy-paste:

```
ls -t docs/reports/spanish_live_smoke_*.txt | head -1 | xargs cat
```

---

## Troubleshooting

### "Connection refused" — stack not warm

Wait longer. Re-check `curl http://localhost:8000/`.

### "No module named 'websockets'"

```
.venv-gpu/bin/pip install websockets
```

### "Kokoro pipeline failed to initialize"

```
HF_HUB_OFFLINE=0 .venv-gpu/bin/python scripts/setup/smoke_kokoro.py
```

This re-fetches Kokoro weights. Once it succeeds, set
`HF_HUB_OFFLINE=1` back in `.env`.

### Smoke run times out on Turn 1

Stack wasn't warm. Stop, wait another 2 minutes, re-run.

### Want to re-run without creating a new narrator each time

Currently the harness creates a fresh narrator per run. That's the
right default for smoke. If you want to repeat the SAME narrator
across runs, set:

```
HORNELORE_SMOKE_REUSE_PERSON_ID=<paste-uuid-from-previous-run>
```

(NOTE: this is not yet implemented — would need a small patch.)

### To stop the stack

```
./scripts/stop_all.sh
```

---

## What success looks like

After GREEN you can open the UI in a browser, click the smoke-harness
narrator (Esteban García), and start a real live session in Spanish.
Lori should respond in Spanish, no Spanglish, no fake meta-praise,
no questionnaire interrogation. Switch to English mid-session — Lori
follows. Switch back — Lori follows again.

That's the bar.
