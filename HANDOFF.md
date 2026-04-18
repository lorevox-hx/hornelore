# Hornelore — Laptop Handoff

This document is a step-by-step bring-up so you can clone Hornelore on a fresh laptop, run it, and share changes back. It assumes Windows + WSL2 + an NVIDIA GPU (preferably RTX 50-series Blackwell to match the production setup).

> **TL;DR if everything is already set up:** `cd /mnt/c/Users/chris/hornelore && bash scripts/start_all.sh`

---

## Current state (as of 2026-04-17)

This section is a rolling summary of what's been shipped recently and what's still in-flight. If you're coming back after time away, read this first.

### Recently shipped (committed)

| Work order | What it is | State |
|---|---|---|
| **WO-EX-01C** | Narrator-identity subject guard + strict section-only birth-context filter | Live-proven; closed the "west Fargo → placeOfBirth" and "Cole's DOB → narrator DOB" bugs |
| **WO-EX-01D** | Field-value sanity blacklists (US state abbr for lastName, stopwords for firstName) | Live-proven; closed "Stanley/ND" and "and/dad" token-fragment bugs |
| **WO-LIFE-SPINE-05** | Phase-aware question composer over `data/prompts/question_bank.json` | Shipped, flag `HORNELORE_PHASE_AWARE_QUESTIONS` default OFF |
| **WO-EX-VALIDATE-01** | Age-math plausibility validator (drops events that predate birth, age<min for civic events, etc.) | Shipped, flag `HORNELORE_AGE_VALIDATOR` default OFF |
| **question_bank v3** | 36 sub-topics, 144 openers, 108 follow-ups. v3 adds civic_entry_age_18, tightens launch/off-ramp, fixes retirement anchor | Content-only, ready for phase-aware activation |
| **WO-EX-SCHEMA-01** | Added `family.*` and `residence.*` field families + repeatable entity support (siblings, children, spouse, grandchildren, residence, priorPartners) | Live-proven; unblocked CLAIMS-01 |
| **WO-EX-CLAIMS-01** | Dynamic token cap (128 simple / 384 compound), position-aware entity grouping, 20 field aliases (batch 1 + 2), narrator identity signals in subject guard | Live eval baseline: **22/30 (73.3%)**. Stable. |
| **WO-GREETING-01** | Backend endpoint + frontend wired. Opener fetched on narrator open in `lv80SwitchPerson()`. Memory echo triggers expanded (5 → 14 phrases). | **Live-tested 2026-04-16** — all 3 narrators show greeting. |

### Unshipped / in-flight

| Work order | State | Notes |
|---|---|---|
| **WO-SCHEMA-02** | **Implementation complete** (2026-04-17). 35 new fields (7 families), ~50 aliases, 7 prompt examples, 14 eval cases (cases 031-044). | Fields: grandparents, military, faith, health, community, pets, travel. Eval suite expanded: 30 → 44 cases. Needs re-run. |
| **WO-CLAIMS-02** | **Quick-win validators shipped** (2026-04-17). See `docs/CLAIMS-02_failure_taxonomy.md`. | 3 validators in extract.py: value-shape rejection (garbage words + short fragments), relation allowlist (enumerated valid values), confidence floor (<0.5 auto-reject). Flag `HORNELORE_CLAIMS_VALIDATORS` default ON. 32 new tests (114 total). Remaining: entity coherence, compound splitting, narrator style tuning. |
| **WO-EX-REROUTE-01** | **Implementation complete** (2026-04-17). | Semantic rerouter: 4 high-precision rerouters (pets, siblings, birthplace, career) that fix valid-but-wrong fieldPaths using section+path+lexical triple-agreement. 4 prompt routing distinction exemplars. 8 micro-eval cases (4 reroute, 4 no-reroute). Eval suite: 44 → 52 cases. |
| **WO-EX-TWOPASS-01** | **A/B eval complete — REGRESSED** (2026-04-17). | Two-pass extraction pipeline: Pass 1 (schema-blind span tagger) → Pass 2A (rule-based classifier) → Pass 2B (LLM classifier for unresolved spans). Flag `HORNELORE_TWOPASS_EXTRACT` remains **OFF**. A/B result: baseline 32/62 (51.6%, avg 0.590) → two-pass 16/62 (25.8%, avg 0.325). Both pairs stable across 2 runs. Major regression in `extract_multiple` (16/35 → 4/35). Root-cause hypothesis (unconfirmed): Pass 1 token starvation (128/256 cap too small for multi-entity spans), span abstraction losing semantic context before classification, Pass 2B seeing only stripped spans instead of original answer. Next step: stage-level log inspection before any v2 attempt. |
| **WO-INTENT-01** | Not yet specced | Narrator says "let's talk about X" → composer ignores and stays anchored. #1 felt bug from live sessions |
| **WO-KAWA-UI-01A** | **Implementation complete** (2026-04-17). See `docs/reports/WO-KAWA-UI-01A_REPORT.md`. | River View UI as popover: segment list, detail pane, flow/rocks/driftwood/banks/spaces editing, river strip, 4 REST endpoints, local-first JSON storage. Needs live test. |
| **WO-KAWA-01** | Fully specced (`hornelore/WO-KAWA-01_Spec.md`). 10 phases. | Parallel Kawa river layer: LLM-driven proposals, confirmation loop, instrumentation. Next: wire LLM into `kawa_projection.py`. |
| **WO-KAWA-02A** | **Implementation complete** (2026-04-17). See `docs/reports/WO-KAWA-02A_REPORT.md`. | 3 interview modes (chronological/hybrid/kawa_reflection), 3 memoir modes (chronology/chronology_river/river_organized), plain-language toggle, Kawa weight metadata, prompt_composer directives. Needs live test. |
| **WO-KAWA-02** (remaining) | Phases 4-9 not yet implemented. | Storage promotion, chapter weighting UI, deeper memoir panel integration, eval hooks. |
| **WO-PHENO-01** | Fully specced (`hornelore/WO-PHENO-01_Spec.md`). 3-4 sessions. | Phenomenology layer: lived experience + wisdom extraction. Question bank (5 phases), experience schema, bio-builder staging. |
| **WO-REPETITION-01** | Not yet specced | Narrator pastes same content 2-3x, Lori keeps responding |
| **WO-MODE-01/02** | Not yet specced | Session Intent Profiles (Questionnaire First / Clear & Direct / Warm Storytelling) after narrator Open |
| **WO-UI-SHADOWREVIEW-01** | Not yet specced | Show Phase G suppression reason ("we already have this") instead of silent drop |
| **WO-EX-DIAG-01** | Not yet specced | Surface extraction failure reason in response envelope |

### Priority sequence to Kawa readiness

```
SCHEMA-02 (done) → CLAIMS-02 quick-wins (done) → eval run 1-4 (done, 24/44) → EX-REROUTE-01 (done) → temp sweep (done, not a lever) → EX-TWOPASS-01 (done, regressed 16/62 vs 32/62 baseline, flag OFF) → stage-level debug or constrained Pass 2 WO → INTENT-01 → KAWA-01 Phase 1
```

### Extraction eval baseline (2026-04-17)

**Single-pass baseline (locked):** 32/62 (51.6%, avg 0.590) — stable across 2 runs.

Failure breakdown (30 failures): schema_gap: 16-17, field_path_mismatch: 9-11, llm_hallucination: 10-11.

**Two-pass A/B (HORNELORE_TWOPASS_EXTRACT=1):** 16/62 (25.8%, avg 0.325) — stable across 2 runs. Major regression; flag remains OFF.

Two-pass failure breakdown (46 failures): schema_gap: 26, field_path_mismatch: 21, llm_hallucination: 10, guard_false_positive: 1.

Root-cause hypothesis (pending stage-log confirmation): Pass 1 token budget too small for multi-entity spans, span abstraction loses context needed for classification, Pass 2B receives only stripped spans without original answer text. The `extract_multiple` category collapsed from 16/35 to 4/35, consistent with token starvation on longer answers.

Eval suite: **62 cases** (52 original + 10 two-pass-specific cases 053-062).

### Extraction pipeline order (updated 2026-04-17)

**Single-pass (flag OFF):**
```
LLM generate → JSON parse → semantic rerouter → birth-context filter → month-name sanity → field-value sanity → claims validators (shape + relation + confidence + negation guard)
```

**Two-pass (HORNELORE_TWOPASS_EXTRACT=1):**
```
Pass 1: span tagger (LLM, schema-blind) → span JSON parse
→ Pass 2A: rule-based classifier (deterministic)
→ Pass 2B: LLM classifier (unresolved spans only)
→ merge → semantic rerouter → birth-context filter → month-name sanity → field-value sanity → claims validators
Falls back to single-pass on pass 1 failure.
```

### Reference docs saved

| File | What it is |
|---|---|
| `hornelore/WO-KAWA-01_Spec.md` | Full 10-phase Kawa data/engine work order |
| `hornelore/WO-KAWA-UI-01_Spec.md` | Full River View UI work order |
| `hornelore/WO-PHENO-01_Spec.md` | Full phenomenology layer work order |
| `hornelore/WO-SCHEMA-02_Gap-Analysis.md` | Life map coverage expansion execution pack |
| `hornelore/Memoir-Upgrade-Phased-Plan.md` | 7-phase memoir system roadmap |
| `hornelore/Hornelore-WO-Checklist.docx` | Printable priority checklist of all pending WOs |
| `docs/CLAIMS-02_failure_taxonomy.md` | Failure root cause analysis + fix priorities |
| `docs/reports/WO-KAWA-UI-01A_REPORT.md` | River View implementation report |
| `docs/reports/WO-KAWA-02A_REPORT.md` | Kawa questioning + memoir integration report |
| `docs/references/` | 4 Kawa/OT reference papers (Iwama, Newbury/Lape, Crepeau, Norell) + 6 extraction papers (NegBERT, Temporal-Relation, HGAN-EODI) + 4 architecture papers (Structured-Data-LLMs, Small-Models-Decomposition, ML-Agent-RL, SLQ-Oral-History) |

### Env flag state

| Flag | Default | Purpose |
|---|---|---|
| `HORNELORE_TRUTH_V2` | 1 | Facts write freeze (legacy /api/facts/add → 410) |
| `HORNELORE_TRUTH_V2_PROFILE` | 1 | Profile reads from family_truth_promoted |
| `HORNELORE_PHASE_AWARE_QUESTIONS` | 0 | Phase-aware question composer (WO-LIFE-SPINE-05) |
| `HORNELORE_AGE_VALIDATOR` | 0 | Age-math plausibility filter (WO-EX-VALIDATE-01) |
| `HORNELORE_CLAIMS_VALIDATORS` | 1 | Value-shape, relation allowlist, confidence floor (WO-EX-CLAIMS-02) |
| `HORNELORE_TWOPASS_EXTRACT` | 0 | Two-pass extraction pipeline: span tagger + field classifier (WO-EX-TWOPASS-01) |

### Test state

114 unit tests across 6 suites, all passing:

```bash
cd /mnt/c/Users/chris/hornelore
source .venv-gpu/bin/activate
python -m unittest tests.test_extract_subject_filters \
                   tests.test_extract_claims_validators \
                   tests.test_life_spine_validator \
                   tests.test_phase_aware_composer \
                   tests.test_interview_opener -v
# Plus the integration tests:
python -m unittest tests.test_extract_api_subject_filters -v  # requires FastAPI
```

### Known issues from live observation (updated 2026-04-17)

See `docs/observations/2026-04-15-extraction-taxonomy.md` for the full writeup. Short version:

- ~~**Critical:** question bank references field paths that don't exist in `EXTRACTABLE_FIELDS`.~~ **FIXED** by WO-EX-SCHEMA-01.
- **High:** Lori ignores narrator-stated topic pivots ("let's talk about my parents"). Fix = WO-INTENT-01.
- **High:** Compound sentences ("my sisters Linda and Sharon", "my three kids...") produce partial extractions (~8 of 30 eval cases still fail). Fix = WO-EX-CLAIMS-02. Root causes now categorized in `docs/CLAIMS-02_failure_taxonomy.md`.
- ~~**High:** Life map coverage gaps — 16 of 37 interview sections have no extraction fields.~~ **FIXED** by WO-SCHEMA-02 (35 new fields across 7 families).
- **Medium:** Narrator repeats same content 2-3×, Lori keeps asking similar follow-ups. Fix = WO-REPETITION-01.
- ~~**Medium:** Lori doesn't introduce herself on session open.~~ **FIXED** — WO-GREETING-01 live-tested, all 3 narrators show greeting.
- **Low:** Accordion shows DOB year only when canonical has full date. Display renderer issue.

### Recommended activation sequence (next time you're ready to test)

1. Commit any outstanding work (`git status` should be clean)
2. Flip `HORNELORE_PHASE_AWARE_QUESTIONS=1` in `.env` if you haven't
3. Restart API: `bash scripts/restart_api.sh`
4. Run a fresh narrator session — confirm question IDs start with `qb:` in network tab
5. Collect observations in `docs/observations/YYYY-MM-DD-*.md`
6. Before building anything new, triage observations against the WO queue

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

## WO-QB-MASTER-EVAL-01 — Master Eval Suite (2026-04-17)
**Status:** SHIPPED
**Files changed:**
- `scripts/run_question_bank_extraction_eval.py` — scorer + report generator
- `data/qa/question_bank_extraction_cases.json` — 62 → 104 cases

Expanded eval from 62 narrow benchmark cases to 104-case master suite.
Original 62 contract/regression cases preserved and tagged. Added 42 new cases:
19 mixed narrative, 8 dense truth, 8 follow-up, 7 null/clarify.

Each case now carries: `caseType`, `style_bucket`, `chunk_size`, `noise_profile`,
`case_mode`, `sequence_group`, `style_expectations`, and `truthZones` with four
zones per field (`must_extract`, `may_extract`, `should_ignore`, `must_not_write`).

Report now shows two scoring layers:
- Layer 1 (contract/regression): must_extract recall, routing, hallucination, violations
- Layer 2 (oral-history style): by case type, style bucket, chunk size, noise profile

Contract subset section tracks the original 62 cases separately for regression comparison.

Run: `python scripts/run_question_bank_extraction_eval.py --mode live --api http://localhost:14501`

## WO-EX-FIELDPATH-NORMALIZE-01A — Deterministic Routing Corrections (2026-04-17)
**Status:** FAILED / REVERTED
Attempted confusion-table-driven field-path normalization. Regressed from 32/62 to 14/62.
All changes reverted. Lesson: rerouter fixes that change what text is checked (answer vs value)
are not safe without understanding that LLM output values don't contain cue phrases.

For the architecture context behind any of this, see:
- `README.md` — current product surface, work order status, file inventory
- `docs/wo-qa/WO-QA-01.md` — Quality Harness scaffolding
- `docs/wo-qa/WO-QA-02.md` — Archive-truth methodology + suppression
- `docs/WO-13X-SHADOW-REVIEW-REDESIGN.md` and others — earlier WO history

Welcome to the laptop. Push your changes when you're done; the desktop will pick them up on the next pull.
