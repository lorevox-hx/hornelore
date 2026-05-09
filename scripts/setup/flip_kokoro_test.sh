#!/usr/bin/env bash
# WO-ML-TTS-EN-ES-01 — flip the live TTS service to Kokoro, run an EN+ES
# synthesis test through the Hornelore TTS service, decode WAVs to /tmp,
# and leave the service running so you can listen.
#
# Run from repo root:
#   bash scripts/setup/flip_kokoro_test.sh
#
# When done testing:
#   bash scripts/setup/flip_kokoro_test.sh revert
#   (flips .env back to coqui, restarts service, exits)

set -e

REPO_DIR=/mnt/c/Users/chris/hornelore
cd "$REPO_DIR"

MODE="${1:-test}"   # default: test (flip to kokoro + verify); "revert" flips back

# ── Helper: stop TTS ──────────────────────────────────────────────────────
_stop_tts() {
    fuser -k 8001/tcp 2>/dev/null || true
    # Wait for socket to actually free
    for _ in 1 2 3 4 5; do
        ss -lnt 2>/dev/null | grep -q ":8001 " || break
        sleep 1
    done
}

# ── Helper: start TTS in background, wait until /api/tts/engine responds ─
# Kokoro's first KPipeline init inside uvicorn can take 60-120s even with
# cached model (the warm hook spins up the English pipeline at startup).
# Subsequent restarts of the same .venv are faster. 180s is generous —
# adjust LORI_TTS_BOOT_TIMEOUT_SEC if needed.
_start_and_wait() {
    local timeout="${LORI_TTS_BOOT_TIMEOUT_SEC:-180}"
    bash launchers/hornelore_run_tts_8001.sh > /tmp/hornelore_tts_8001.log 2>&1 &
    local i
    for i in $(seq 1 "$timeout"); do
        if curl -sf http://localhost:8001/api/tts/engine > /dev/null 2>&1; then
            echo "  TTS up after ${i}s"
            return 0
        fi
        # Every 30s, print a heartbeat so the operator knows we're alive
        if [ $((i % 30)) -eq 0 ]; then
            echo "  ...${i}s waiting (warming Kokoro pipeline)"
        fi
        sleep 1
    done
    echo "  TTS failed to come up after ${timeout}s — last 30 log lines:"
    tail -30 /tmp/hornelore_tts_8001.log
    return 1
}

# ── Helper: set LORI_TTS_ENGINE in .env to $1 (idempotent) ───────────────
_set_engine_env() {
    local target="$1"
    if grep -q '^LORI_TTS_ENGINE=' .env; then
        sed -i "s/^LORI_TTS_ENGINE=.*/LORI_TTS_ENGINE=${target}/" .env
    else
        echo "LORI_TTS_ENGINE=${target}" >> .env
    fi
    grep '^LORI_TTS_ENGINE' .env
}

# ── Helper: ensure HF_HUB_OFFLINE=1 in .env (your locked rule) ───────────
_ensure_offline_env() {
    if ! grep -q '^HF_HUB_OFFLINE=' .env; then
        echo "HF_HUB_OFFLINE=1" >> .env
    fi
    grep '^HF_HUB_OFFLINE' .env
}

# ── Helper: synthesize text + decode b64 to a WAV at $2 ──────────────────
_synth() {
    local lang="$1"
    local text="$2"
    local out_path="$3"

    # Send the synthesis request, capture full response
    local resp
    resp="$(curl -s -X POST http://localhost:8001/api/tts/speak_stream \
        -H 'Content-Type: application/json' \
        -d "{\"text\":\"${text}\",\"language\":\"${lang}\"}")"

    if [ -z "$resp" ]; then
        echo "  FAIL: empty response for lang=${lang}"
        return 1
    fi

    # Decode b64 to wav, print metadata
    python3 - "$resp" "$out_path" <<'PY'
import sys, json, base64
resp = sys.argv[1]
out_path = sys.argv[2]
try:
    d = json.loads(resp.splitlines()[0])
except Exception as e:
    print(f"  FAIL: response not JSON: {e}")
    print(f"  raw[:200]: {resp[:200]}")
    sys.exit(2)
if 'wav_b64' not in d:
    print(f"  FAIL: no wav_b64 in response: {list(d.keys())}")
    sys.exit(3)
with open(out_path, 'wb') as f:
    f.write(base64.b64decode(d['wav_b64']))
print(f"  engine={d.get('engine')} voice={d.get('voice')} lang={d.get('language')} dur={d.get('duration_sec','?')}s -> {out_path}")
PY
}

# ──────────────────────────────────────────────────────────────────────────
case "$MODE" in
    test)
        echo "=== Flip TTS to Kokoro, synthesize EN + ES, decode WAVs ==="
        echo
        echo "[1/6] Stopping any running TTS on :8001..."
        _stop_tts

        echo "[2/6] Setting .env: LORI_TTS_ENGINE=kokoro, HF_HUB_OFFLINE=1..."
        _set_engine_env kokoro
        _ensure_offline_env

        echo "[3/6] Starting TTS in Kokoro mode (background)..."
        _start_and_wait || exit 1

        echo "[4/6] Engine diagnostic:"
        curl -s http://localhost:8001/api/tts/engine | python3 -m json.tool

        echo
        echo "[5/6] English synthesis (af_heart):"
        _synth en "Hello, this is Kokoro speaking through the Hornelore TTS service." \
               /tmp/hornelore_kokoro_en.wav

        echo
        echo "[6/6] Spanish synthesis (ef_dora):"
        _synth es "Hola, soy Lori, y esta es una prueba de la voz en espanol a traves del servicio TTS de Hornelore." \
               /tmp/hornelore_kokoro_es.wav

        echo
        echo "=== DONE ==="
        echo
        echo "Listen with:"
        echo "  explorer.exe \"\$(wslpath -w /tmp/hornelore_kokoro_en.wav)\""
        echo "  explorer.exe \"\$(wslpath -w /tmp/hornelore_kokoro_es.wav)\""
        echo
        echo "TTS service is still running on port 8001 (Kokoro mode)."
        echo "When done, revert with:  bash scripts/setup/flip_kokoro_test.sh revert"
        ;;

    revert)
        echo "=== Revert TTS to Coqui ==="
        echo
        echo "[1/3] Stopping TTS on :8001..."
        _stop_tts

        echo "[2/3] Setting .env: LORI_TTS_ENGINE=coqui..."
        _set_engine_env coqui

        echo "[3/3] Starting TTS in Coqui mode (background)..."
        _start_and_wait || exit 1

        echo
        echo "Engine confirmation:"
        curl -s http://localhost:8001/api/tts/engine | python3 -m json.tool
        echo
        echo "=== Reverted to Coqui ==="
        ;;

    stop)
        echo "=== Stopping TTS ==="
        _stop_tts
        echo "  done"
        ;;

    *)
        echo "Usage: bash scripts/setup/flip_kokoro_test.sh [test|revert|stop]"
        echo "  test   — (default) flip to kokoro, run EN+ES synth, leave service up"
        echo "  revert — flip back to coqui, restart service"
        echo "  stop   — kill TTS service, do nothing else"
        exit 1
        ;;
esac
