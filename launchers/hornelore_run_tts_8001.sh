#!/usr/bin/env bash
# Hornelore — TTS server (port 8001)
# Uses Hornelore repo config, Hornelore-owned venv, and hornelore_data.
# WO-11: Standalone repo layout. No parent lorevox dependency.
set -e

REPO_DIR=/mnt/c/Users/chris/hornelore

# ── Load Hornelore .env (repo root) ───────────────────────────────────────
if [ -f "$REPO_DIR/.env" ]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
  echo "[launcher] Loaded Hornelore .env"
fi

# ── Defaults (only apply if not already set by Hornelore .env) ───────────
export USE_TTS=${USE_TTS:-1}
export DATA_DIR=${DATA_DIR:-/mnt/c/hornelore_data}
export HOST=${HOST:-0.0.0.0}
export TTS_PORT=${TTS_PORT:-8001}

# TTS — default GPU=0 to keep VRAM free for LLM + STT
export TTS_MODEL=${TTS_MODEL:-tts_models/en/vctk/vits}
export TTS_GPU=${TTS_GPU:-0}
export TTS_SPEAKER_LORI=${TTS_SPEAKER_LORI:-p335}

# ── Kill any stale process on this port ───────────────────────────────────
fuser -k ${TTS_PORT}/tcp 2>/dev/null || true

# ── Create data dirs ──────────────────────────────────────────────────────
mkdir -p "$DATA_DIR"/{db,voices,cache_audio,memory,projects,interview,logs,templates}

# ── Start server ──────────────────────────────────────────────────────────
# WO-11: Activate the Hornelore-owned TTS venv. No parent repo dependency.
source "$REPO_DIR/.venv-tts/bin/activate"
# cwd MUST be hornelore/server so uvicorn loads code.api.tts_service
# against the canonical source tree.
cd "$REPO_DIR/server"

echo "[launcher] cwd=$(pwd)"
echo "[launcher] Starting Hornelore TTS server on port $TTS_PORT"
echo "[launcher] DATA_DIR=$DATA_DIR"
echo "[launcher] TTS_MODEL=$TTS_MODEL  TTS_GPU=$TTS_GPU  SPEAKER=$TTS_SPEAKER_LORI"

python -m uvicorn code.api.tts_service:app --host "$HOST" --port "$TTS_PORT"
