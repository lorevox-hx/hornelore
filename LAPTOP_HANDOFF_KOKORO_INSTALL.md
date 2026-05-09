# Laptop Handoff — Kokoro install + recovery (2026-05-08 morning, REVISED v2)

**Status of laptop right now:** broken `.venv` from earlier install attempt (hit phonemizer-fork namespace collision, never reached model download).

**What this doc does:** ONE clean reset path that incorporates every fix we learned on MAG-Chris over the past 24 hours. Run top-to-bottom in order. No multi-step pasting blocks — most steps are single commands.

**KEY DECISION LOCKED 2026-05-08:** Coqui is RETIRED as the active TTS engine. Kokoro is the SOLE TTS engine going forward (en + es + 6 more languages, Apache 2.0, smaller VRAM footprint, sounds good). Coqui adapter code stays in the tree as a fallback option but is never activated. Both machines will run with `LORI_TTS_ENGINE=kokoro` permanently.

---

## What we learned over the past 24 hours (so the laptop doesn't hit the same bumps)

1. ❌ **Don't install Kokoro into system Python** (PEP 668 blocks it on Ubuntu 23.04+). Use `.venv`.
2. ❌ **Don't install `phonemizer` alongside Kokoro.** It collides with `phonemizer-fork` in the same namespace; older one wins, Kokoro crashes with `EspeakWrapper has no attribute 'set_data_path'`. Fix: uninstall phonemizer + force-reinstall phonemizer-fork + espeakng-loader.
3. ❌ **Don't forget fastapi + uvicorn + python-multipart.** `.venv-tts` (legacy Coqui venv) had them via Coqui's transitive deps; the new `.venv` doesn't. The TTS service is a FastAPI app served by uvicorn — without these the launcher fails with `No module named uvicorn`.
4. ❌ **Kokoro 0.9.x yields `KPipeline.Result` objects, NOT plain tuples.** Audio is `chunk.audio`, not `chunk[2]`.
5. ❌ **The router's hardcoded `voice="lori"` (Coqui default) breaks Kokoro.** Kokoro doesn't have a voice named `lori`; it tries to fetch `lori.pt` from HF cache, fails with `LocalEntryNotFoundError`. Fix is in `kokoro.py` adapter — falls back to per-language default if the requested voice isn't in the engine's known-voice list. Already patched in tree.
6. ❌ **`.env` setting `HF_HOME=/mnt/c/models/hornelore/hf_home` (for Llama) breaks Kokoro cache lookup.** When the launcher sources `.env`, the TTS process inherits Llama's HF_HOME and looks for Kokoro files at `${HF_HOME}/hub` — wrong place. Fix: pin `HF_HUB_CACHE` and `HUGGINGFACE_HUB_CACHE` explicitly to `/home/<user>/.cache/huggingface/hub` in `.env` so Kokoro and Llama can use different cache locations.
7. ❌ **Launcher script-name typos**: `hornelore_run_all_dev.sh` was calling `launchers/run_gpu_8000.sh` and `launchers/run_tts_8001.sh` (missing the `hornelore_` prefix). Files are actually named `hornelore_run_gpu_8000.sh` etc. Already patched.
8. ⚠️ **Your shell almost certainly has `HF_HUB_OFFLINE=1` exported** (from your Llama setup). It blocks Kokoro's first-time model download. Override inline for the first online run; turn on permanently afterward.
9. ⚠️ **First-time model download = ~330MB** (model) + ~500KB per voice + spaCy `en_core_web_sm` (~12MB).

**All eight fixes are baked into the patched scripts** that MAG-Chris pushed. The laptop just needs to pull + run.

## Engine decision: Kokoro is the SOLE TTS engine

After validating Kokoro live in the Hornelore stack on MAG-Chris (English `af_heart` + Spanish `ef_dora` both confirmed audible + grammatical), we retired Coqui. Reasons:
- Kokoro covers BOTH English AND Spanish (Coqui was English-only)
- Apache 2.0 license (Coqui VITS was English-only via VCTK and CPML-restricted for cloning)
- Smaller VRAM footprint on the 16GB RTX 5080 (Coqui + Kokoro both warm = GPU contention with Llama)
- Voice quality acceptable for elder narrators

`.venv-tts` (the legacy Coqui venv, ~7.5GB) stays on disk for now — gitignored, not loaded, harmless. Future cleanup deletes it. The Coqui adapter (`server/code/api/tts/coqui.py`) stays in code as a fallback option only.

**Both machines will run with `LORI_TTS_ENGINE=kokoro` permanently.**

---

## Recovery sequence (laptop)

### Step 1 — Pull MAG-Chris's commits (gets all the fixes)

```bash
cd /mnt/c/Users/chris/hornelore   # or wherever the laptop's path is
git status                         # confirm clean tree
git pull origin main
git log --oneline -1               # confirm latest commit is on
```

You should see the latest commit at the top (the `feat(tts): WO-ML-TTS-EN-ES-01 Phase 1` and any subsequent `fix(tts):` commits MAG-Chris pushed).

### Step 2 — Nuke the broken `.venv`

```bash
rm -rf .venv
```

The laptop's `.venv` was created by the BUGGY original install script and has the phonemizer collision baked in. Cleaner to start fresh than try to repair.

### Step 3 — Run the patched install script

```bash
bash scripts/setup/install_kokoro.sh
```

The patched script does, in order:
1. `apt-get install espeak-ng` (will say "newest version" — already installed)
2. Find or create `.venv` at repo root (now it's missing → creates fresh)
3. Upgrade pip/setuptools/wheel inside venv
4. `pip install kokoro soundfile numpy fastapi 'uvicorn[standard]' python-multipart`
5. **Defensive repair**: `pip uninstall -y phonemizer` (no-op since fresh) + `pip install --upgrade --force-reinstall phonemizer-fork espeakng-loader`
6. Verify imports + assert `EspeakWrapper.set_data_path` AND `set_library` exist

Final line should be `All imports OK.`

### Step 4 — Quick import sanity check

```bash
.venv/bin/python -c "from kokoro import KPipeline; print('OK')"
```

Should print `OK`. If it errors with the EspeakWrapper attribute — the script's defensive repair didn't fire properly, paste output and we'll triage.

### Step 5 — First-time online smoke (needs network)

This downloads the Kokoro model + both voices into your local HuggingFace cache. It must run ONLINE the first time:

```bash
HF_HUB_OFFLINE=0 TRANSFORMERS_OFFLINE=0 HF_HUB_ENABLE_HF_TRANSFER=0 \
  .venv/bin/python scripts/setup/smoke_kokoro.py
```

Why each override:
- `HF_HUB_OFFLINE=0` — your shell likely has `HF_HUB_OFFLINE=1` exported permanently from Llama setup; this overrides for THIS COMMAND ONLY
- `TRANSFORMERS_OFFLINE=0` — same idea
- `HF_HUB_ENABLE_HF_TRANSFER=0` — your shell sets this to 1 but `hf_transfer` package isn't installed in `.venv`; force off to avoid that failure

Expected: ~30-90 seconds first run (download progress bars), final line `=== Smoke probe PASSED ===`. Two WAVs land in `/tmp/`.

### Step 6 — Verify offline mode works (your locked-rule check)

```bash
HF_HUB_OFFLINE=1 .venv/bin/python scripts/setup/smoke_kokoro.py
```

Should pass entirely from cache (no download bars), final line `=== Smoke probe PASSED ===`. This proves: after first cache, the runtime stack can use Kokoro with `HF_HUB_OFFLINE=1` set permanently.

### Step 7 — Listen to verify voices

```bash
explorer.exe "$(wslpath -w /tmp/kokoro_smoke_en.wav)"
explorer.exe "$(wslpath -w /tmp/kokoro_smoke_es.wav)"
```

Same EN + ES voices MAG-Chris already validated — should sound the same. If not, ping Chris.

### Step 8 — Update laptop's `.env` to match MAG-Chris

**Coqui is RETIRED. Kokoro is the sole engine on both machines** (locked 2026-05-08 after live verification on MAG-Chris). Set `LORI_TTS_ENGINE=kokoro` directly — do not stage as coqui-first.

#### 8a — Inspect what's already in laptop's `.env`

```bash
cd /mnt/c/Users/chris/hornelore   # or wherever laptop's path is
grep -E "^LORI_TTS|^HF_HUB|^HUGGINGFACE|^TRANSFORMERS|^HF_HOME" .env
```

You should see Llama-related vars from the laptop's existing setup:
- `HF_HOME=/mnt/c/...` (some Llama-cache path)
- `HF_HUB_OFFLINE=1`
- `TRANSFORMERS_OFFLINE=1`
- maybe `HF_HUB_ENABLE_HF_TRANSFER=1`

If `LORI_TTS_ENGINE` is already there from a stale install attempt, note its value — you'll overwrite it.

#### 8b — Apply the TTS block

The required end-state in `.env`:

```
LORI_TTS_ENGINE=kokoro
LORI_TTS_KOKORO_VOICE_EN=af_heart
LORI_TTS_KOKORO_VOICE_ES=ef_dora
HF_HUB_CACHE=/home/chris/.cache/huggingface/hub
HUGGINGFACE_HUB_CACHE=/home/chris/.cache/huggingface/hub
HF_HUB_OFFLINE=1
```

The two `*_HUB_CACHE` lines are CRITICAL — they pin Kokoro's cache to `~/.cache/huggingface/hub` so it doesn't fight Llama's `HF_HOME` (which lives elsewhere). Without them, the TTS uvicorn process inherits `HF_HOME` from `.env` and looks for Kokoro files at `${HF_HOME}/hub` — wrong place — `LocalEntryNotFoundError`. Surfaced live on MAG-Chris 2026-05-08.

**If laptop's home dir isn't `/home/chris`**, replace the two paths above with `/home/$(whoami)/.cache/huggingface/hub`.

#### 8c — Apply via heredoc append (non-destructive)

If `.env` doesn't yet have any `LORI_TTS_*` or `HF_HUB_CACHE` lines, append cleanly:

```bash
cat >> .env <<EOF

# WO-ML-TTS-EN-ES-01 (locked 2026-05-08): Kokoro is sole engine. Coqui retired.
LORI_TTS_ENGINE=kokoro
LORI_TTS_KOKORO_VOICE_EN=af_heart
LORI_TTS_KOKORO_VOICE_ES=ef_dora

# Pin Kokoro cache to user cache dir so Llama HF_HOME doesn't redirect
# Kokoro file lookups. CRITICAL — without these the TTS service hits
# LocalEntryNotFoundError on Spanish KPipeline init.
HF_HUB_CACHE=/home/$(whoami)/.cache/huggingface/hub
HUGGINGFACE_HUB_CACHE=/home/$(whoami)/.cache/huggingface/hub
EOF
```

The `$(whoami)` substitution at heredoc time picks up the laptop's actual user. Don't quote the EOF marker — quoting prevents substitution.

If `.env` ALREADY has any of these lines (e.g. from a stale install), edit them directly with `sed`:

```bash
# Flip any existing LORI_TTS_ENGINE=coqui → kokoro
grep -q '^LORI_TTS_ENGINE=' .env && \
  sed -i 's|^LORI_TTS_ENGINE=.*|LORI_TTS_ENGINE=kokoro|' .env || \
  echo "LORI_TTS_ENGINE=kokoro" >> .env

# Same pattern for the voice + cache vars
grep -q '^LORI_TTS_KOKORO_VOICE_EN=' .env || echo "LORI_TTS_KOKORO_VOICE_EN=af_heart" >> .env
grep -q '^LORI_TTS_KOKORO_VOICE_ES=' .env || echo "LORI_TTS_KOKORO_VOICE_ES=ef_dora" >> .env
grep -q '^HF_HUB_CACHE=' .env || echo "HF_HUB_CACHE=/home/$(whoami)/.cache/huggingface/hub" >> .env
grep -q '^HUGGINGFACE_HUB_CACHE=' .env || echo "HUGGINGFACE_HUB_CACHE=/home/$(whoami)/.cache/huggingface/hub" >> .env
grep -q '^HF_HUB_OFFLINE=' .env || echo "HF_HUB_OFFLINE=1" >> .env
```

#### 8d — Verify the env block matches MAG-Chris

```bash
grep -E "^LORI_TTS|^HF_HUB_CACHE|^HUGGINGFACE_HUB_CACHE|^HF_HUB_OFFLINE" .env
```

Expected (in any order — all 6 lines must be present):
```
LORI_TTS_ENGINE=kokoro
LORI_TTS_KOKORO_VOICE_EN=af_heart
LORI_TTS_KOKORO_VOICE_ES=ef_dora
HF_HUB_CACHE=/home/chris/.cache/huggingface/hub
HUGGINGFACE_HUB_CACHE=/home/chris/.cache/huggingface/hub
HF_HUB_OFFLINE=1
```

**Do NOT remove existing `HF_HOME=` from `.env`** — that's pinned for Llama. The `HF_HUB_CACHE` you just added overrides it for HF Hub library lookups (Kokoro), but Llama still uses `HF_HOME` directly.

### Step 9 — Stop here for tonight

The laptop install + smoke + env are done. Don't restart the live stack until Chris explicitly says go. The TTS launcher will start cleanly with Kokoro on next stack start because:
- `.env` says `LORI_TTS_ENGINE=kokoro`
- Patched launcher (`hornelore_run_tts_8001.sh`) reads that and activates `.venv` (Kokoro)
- Cache is pinned to the right dir
- Both EN + ES voices are pre-cached

When Chris greenlights: `bash launchers/hornelore_run_all_dev.sh` (the patched one — fixed path typos). The TTS log line should read `[launcher] LORI_TTS_ENGINE=kokoro — using .venv (Kokoro multilingual)`.

---

## Sanity-check block before declaring laptop done

Run all 6 lines, eyeball each output:

```bash
.venv/bin/python --version                                                  # Python 3.12.x
.venv/bin/python -c "from kokoro import KPipeline; print('OK')"             # OK
.venv/bin/python -c "import fastapi, uvicorn, soundfile; print('web OK')"   # web OK
ls -lh /tmp/kokoro_smoke_*.wav                                              # 2 WAVs, ~500KB each
grep "^LORI_TTS_ENGINE\|^HF_HUB_OFFLINE\|^LORI_TTS_KOKORO" .env             # 4 lines
git log --oneline -1                                                        # latest commit on
```

If all six look right → laptop is parity-complete. Done for tonight.

---

## If anything fails

| Symptom | Fix |
|---|---|
| `git pull` reports merge conflict | STOP. Ping Chris before resolving. |
| `python3 -m venv .venv` fails with "ensurepip not available" | `sudo apt install -y python3-venv python3-full` then re-run install script |
| Install script errors on `EspeakWrapper.set_data_path` assertion | Force-reinstall step didn't fire. Manual repair: `.venv/bin/python -m pip install --upgrade --force-reinstall phonemizer-fork espeakng-loader` |
| Smoke probe step 2 fails with `LocalEntryNotFoundError` | HF_HUB_OFFLINE override didn't take. Check current env: `env \| grep HF_HUB_OFFLINE`. If still set to 1, the override syntax got mangled — copy the inline-override command exactly from step 5. |
| Smoke probe step 3 fails with `inhomogeneous shape (3,)` chunk decode | The smoke probe wasn't pulled. Run `git log --oneline -1` to confirm latest commit; should reference the chunk.audio fix. |
| WAVs are silent / wrong language / robotic | Voice key issue. Try `LORI_TTS_KOKORO_VOICE_EN=af_bella` and `LORI_TTS_KOKORO_VOICE_ES=em_alex` in .env, re-run smoke. |

Don't try to recover with manual pip commands beyond what the table says. If anything else breaks, paste the FIRST error line + 3 surrounding lines to Chris.
