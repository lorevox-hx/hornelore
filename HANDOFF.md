# Hornelore — Laptop Handoff

This document is a step-by-step bring-up so you can clone Hornelore on a fresh laptop, run it, and share changes back. It assumes Windows + WSL2 + an NVIDIA GPU (preferably RTX 50-series Blackwell to match the production setup).

> **TL;DR if everything is already set up:** `cd /mnt/c/Users/chris/hornelore && bash scripts/start_all.sh`

---

## 0. What "Hornelore on the laptop" means

Hornelore is a **single-machine local-LLM** application. There's no cloud component. Everything that matters runs in WSL2 against the Windows-side NVIDIA driver. Three services come up in sequence:

| Port | Service | Process |
|---|---|---|
| 8000 | LLM API (FastAPI + Llama-3.1-8B INT4) | `launchers/hornelore_run_gpu_8000.sh` |
| 8001 | TTS server (Coqui VITS) | `launchers/hornelore_run_tts_8001.sh` |
| 8082 | UI static server | `python3 hornelore-serve.py` |

You open the UI in Chrome at `http://localhost:8082/ui/hornelore1.0.html`.

---

## 1. Prerequisites (one-time per laptop)

### Hardware
- NVIDIA GPU with at least **16 GB VRAM** (RTX 5080 / 4090 / equivalent)
- **128 GB system RAM** is what the production rig has; 64 GB will work; 32 GB is tight
- ≥ 200 GB free SSD space (model weights, HF cache, hornelore_data)

### Drivers
- **NVIDIA driver R570+** (Blackwell GPUs require this; check `nvidia-smi` shows it)
- WSL2 GPU passthrough enabled (run `nvidia-smi` inside WSL — should show the same GPU)

### Software
- Windows 11 with **WSL2** + Ubuntu 24.04 (or current LTS)
- **Python 3.12** inside WSL (Ubuntu 24.04 default)
- **git** + **bash** + **curl** + **sqlite3**
- **Chrome** on Windows side (UI runs in browser)
- A real **HuggingFace token** with access to `meta-llama/Llama-3.1-8B-Instruct` (the model is gated)

### One-time WSL setup
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git curl sqlite3 build-essential
```

---

## 2. Get the code

```bash
mkdir -p /mnt/c/Users/<you>
cd /mnt/c/Users/<you>
git clone <hornelore-remote-url> hornelore
cd hornelore
```

The expected layout:
```
/mnt/c/Users/<you>/hornelore/      ← code (this is the repo)
/mnt/c/hornelore_data/             ← runtime data (DB, uploads, media, test_lab) — created on first run
/mnt/c/Llama-3.1-8B/hf/...         ← model weights cache (downloaded on first API start)
/mnt/c/models/hornelore/hf_home/   ← HF transformers cache
```

Everything under `/mnt/c/hornelore_data/` is **gitignored** and machine-local. It's where your DB and chat archive live; never commit it.

---

## 3. Configure `.env`

The repo has `.env.example` as a template. Copy and edit:

```bash
cp .env.example .env
```

Edit `.env` and set:

| Key | What to set |
|---|---|
| `HUGGINGFACE_HUB_TOKEN` | your real HF token (Llama is gated) |
| `MODEL_PATH` | usually `/mnt/c/Llama-3.1-8B/hf/Meta-Llama-3.1-8B-Instruct` |
| `DATA_DIR` | `/mnt/c/hornelore_data` (or wherever you want runtime data) |
| `MAX_NEW_TOKENS_CHAT_HARD` | `2048` (required for the Quality Harness; default 1024 will clip the 1000-word stress test) |
| `REPETITION_PENALTY_DEFAULT` | `1.1` (production default; harness sweeps per-request) |

Leave the others at their defaults unless you know why you're changing them.

`.env` is **gitignored** — your changes never leave this laptop. `.env.example` is the tracked template; if you add a new env var, document it there.

---

## 4. Install Python deps

There are two virtualenvs (one for the GPU LLM stack, one for TTS). The launchers in `launchers/` already point at them, but you have to create them first.

```bash
# GPU env (FastAPI, transformers, bitsandbytes, torch)
python3 -m venv .venv-gpu
source .venv-gpu/bin/activate
pip install -r requirements-gpu.txt
deactivate

# TTS env (Coqui VITS, scipy, etc.)
python3 -m venv .venv-tts
source .venv-tts/bin/activate
pip install -r requirements-tts.txt
deactivate
```

If `requirements-gpu.txt` or `requirements-tts.txt` aren't in the repo, see `scripts/requirements.txt` and the launchers for hints. (The Quality Harness also needs `httpx` and `websockets`, which `scripts/run_test_lab.sh` auto-installs.)

---

## 5. First start — bring up the stack

```bash
cd /mnt/c/Users/<you>/hornelore
bash scripts/start_all.sh
```

This:
1. Kills any stale Hornelore processes
2. Shows current VRAM
3. Starts the API (waits up to 90s for `/api/ping` health)
4. Waits up to 3 min for the LLM to load and warm
5. Starts TTS (waits for `/api/tts/voices`)
6. Starts the UI server on 8082
7. Opens `http://localhost:8082/ui/hornelore1.0.html` in your default browser

Logs land in `logs/api.log`, `logs/tts.log`, `logs/ui.log`. To tail:
```bash
bash scripts/logs_visible.sh        # opens all three log streams in separate terminal windows
```

To stop everything:
```bash
bash scripts/stop_all.sh
```

To restart just the API (e.g., after a `.env` or `chat_ws.py` change):
```bash
bash scripts/restart_api.sh
```

---

## 6. First load — narrators auto-seed

The first time the API starts, `_horneloreEnsureNarrators()` checks the `people` table. If Chris, Kent, or Janice are missing, they're seeded from `ui/templates/`. Reference narrators (Shatner, Dolly) seed via `scripts/preload_trainer.py`:

```bash
python3 -m pip install -r scripts/requirements.txt --break-system-packages
python3 -m playwright install chromium
python3 scripts/preload_trainer.py --all
```

Synthetic test narrators for the Quality Harness seed via:

```bash
python3 scripts/seed_test_narrators.py
```

(or automatically when you click **Run Harness** in the Test Lab popover).

---

## 7. Running the Quality Harness on the laptop

After the stack is up:

**From the UI** (operator-only):
1. Open Chrome → Hornelore tab
2. F12 → Console → paste: `document.getElementById("testLabPopover").showPopover()`
3. Optionally tick **Dry run** (verifies plumbing in ~30s)
4. Optionally pick a baseline from "No compare baseline" dropdown
5. Click **Run Harness**
6. Watch the Live Console pane (GPU/CPU/RAM + log + elapsed/ETA)
7. Budget 45–90 minutes for a full matrix (depends on GPU speed)
8. When status flips to `finished`, pick the new run from "Select run to load"

**From WSL** (same thing, no UI needed):
```bash
bash scripts/run_test_lab.sh                              # full matrix
bash scripts/run_test_lab.sh --dry-run                    # plumbing check
bash scripts/run_test_lab.sh --compare-to <prior_run_id>  # regression vs baseline
bash scripts/test_lab_doctor.sh                           # one-shot health check
bash scripts/test_lab_watch.sh                            # terminal live monitor
```

Run artifacts land in `/mnt/c/hornelore_data/test_lab/runs/<run_id>/`. See `docs/wo-qa/WO-QA-01.md` for the full artifact list.

---

## 8. Sharing changes back

This repo is the only thing that needs to sync between machines. **Runtime data does not sync.**

### What syncs (via git)
- All code under `server/`, `ui/`, `scripts/`, `data/narrator_templates/`, `data/test_lab/`, `docs/`
- `.env.example`, `requirements*.txt`, launcher scripts
- README + HANDOFF + WO docs

### What does NOT sync (gitignored)
- `.env` (contains your HF token)
- `/mnt/c/hornelore_data/` (DB, uploads, media, test_lab runs)
- `/mnt/c/Llama-3.1-8B/` (model weights)
- `.venv-gpu/`, `.venv-tts/`
- `logs/`

### Push from the laptop
```bash
git add -p                                  # review changes piece by piece
git commit -m "<short-but-specific>"
git push origin main
```

### Pull from the desktop later
```bash
cd /mnt/c/Users/chris/hornelore
git pull origin main
```

If the pull touched `chat_ws.py`, any router, or anything in `server/`, restart the API:
```bash
bash scripts/restart_api.sh
```

If it touched UI files, hard-reload Chrome (Ctrl+Shift+R).

If it touched `.env.example`, manually merge any new keys into your local `.env`.

### What if a harness run is in progress when you sync?
Don't restart the API — let the run finish first. The runner reads `chat_ws.py` once at startup; in-flight requests use the loaded model. Status will flip to `finished` when done. Then pull, restart, and proceed.

### Sharing harness results between machines
If you want to compare a desktop baseline against a laptop run, copy the specific run directory across:

```bash
# On the desktop
tar czf qa02_baseline.tgz -C /mnt/c/hornelore_data/test_lab/runs qa02_20260414_154500

# Move qa02_baseline.tgz to the laptop (USB, syncthing, scp, your call)

# On the laptop
tar xzf qa02_baseline.tgz -C /mnt/c/hornelore_data/test_lab/runs/

# Now you can compare
bash scripts/run_test_lab.sh --compare-to qa02_20260414_154500
```

Hardware and timing numbers won't be apples-to-apples across machines (different GPUs, different VRAM contention), but **suppression** and **contamination** should be — those are config behaviors, not hardware.

---

## 9. Common bring-up snags

| Symptom | Likely cause | Fix |
|---|---|---|
| `nvidia-smi` works in PowerShell but not in WSL | WSL GPU passthrough not enabled | Update WSL: `wsl --update` (PowerShell as admin) |
| API hangs on "Waiting for LLM model to become ready" | First-time model download from HF | Watch `tail -f logs/api.log` — should show progress; can take 10+ min |
| 401/403 from HF | Token missing or doesn't accept Llama license | Get token from huggingface.co, accept Llama-3.1 license at `meta-llama/Llama-3.1-8B-Instruct` |
| Test Lab button missing | Dev mode off | Console: `toggleDevMode()` (or `document.getElementById("testLabPopover").showPopover()` directly) |
| `Status: failed` after Test Lab run | Stuck status from a previous run | `curl -X POST http://localhost:8000/api/test-lab/reset` |
| 404 on `/api/test-lab/*` | API on 8000 wasn't restarted after pulling new code | `bash scripts/restart_api.sh` |
| Browser hits the right URL but gets 404 on `/api/...` | Browser cached old `api.js`; UI routes calls to wrong port | Hard-reload (Ctrl+Shift+R) |
| Harness preflight fails with "only N tokens streamed" | `MAX_NEW_TOKENS_CHAT_HARD` not raised | Edit `.env`, restart API, retry |
| Seed script complains "no such column narrator_type" | DB predates WO-13 Phase 3 | Already fixed — script auto-ALTERs the column |

---

## 10. Quick reference

```bash
# Start everything
bash scripts/start_all.sh

# Stop everything
bash scripts/stop_all.sh

# Restart just the API (after code/env changes)
bash scripts/restart_api.sh

# Tail all logs in separate windows
bash scripts/logs_visible.sh

# Check stack health
bash scripts/test_stack_health.sh
bash scripts/status_all.sh

# Run the Quality Harness (full matrix)
bash scripts/run_test_lab.sh --compare-to <last-baseline>

# Diagnose a stuck Test Lab run
bash scripts/test_lab_doctor.sh

# Open Hornelore
# → http://localhost:8082/ui/hornelore1.0.html
```

For the architecture context behind any of this, see:
- `README.md` — current product surface, work order status, file inventory
- `docs/wo-qa/WO-QA-01.md` — Quality Harness scaffolding
- `docs/wo-qa/WO-QA-02.md` — Archive-truth methodology + suppression
- `docs/WO-13X-SHADOW-REVIEW-REDESIGN.md` and others — earlier WO history

Welcome to the laptop. Push your changes when you're done; the desktop will pick them up on the next pull.
