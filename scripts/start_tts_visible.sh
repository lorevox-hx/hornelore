#!/usr/bin/env bash
set -euo pipefail
trap 'printf "\n*** Script failed. Press Enter to close. ***\n"; read' ERR
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

printf '\n=== Hornelore TTS visible startup ===\n'
printf 'Repo: %s\n' "$ROOT_DIR"
printf 'Log:  %s\n\n' "$LOG_DIR/tts.log"

start_named_process "Hornelore TTS" "$TTS_CMD" "$TTS_PID_FILE" "$LOG_DIR/tts.log"

printf 'Waiting for TTS health...\n'
# TTS model loading (Coqui VITS) can take 90–180s on cold start.
# Use retry: 90s initial + 120s extension if process is still alive.
if wait_for_health_retry "Hornelore TTS" tts_up 90 120 "$TTS_PID_FILE"; then
  printf 'TTS health check passed.\n'
  _tts_healthy=1
else
  printf 'TTS health check FAILED.\n'
  _tts_healthy=0
fi

if [[ -f "$ROOT_DIR/scripts/warm_tts.py" ]]; then
  # Try warmup even if health check timed out — the server may have come up
  # during the gap between health check and warmup call.
  printf 'Warming TTS...\n'
  python3 "$ROOT_DIR/scripts/warm_tts.py" \
    && { printf 'TTS warm.\n'; _tts_healthy=1; } \
    || printf 'TTS warmup failed.\n'
fi

if [[ "${_tts_healthy:-0}" -eq 0 ]]; then
  # Last-chance: one final health probe before declaring failure
  if tts_up; then
    printf 'TTS came up late — now healthy.\n'
  else
    printf 'TTS is not responding. Check log: %s\n' "$LOG_DIR/tts.log"
  fi
fi

printf '\nTTS visible startup complete.\n'
printf 'TTS: http://127.0.0.1:%s\n' "$TTS_PORT"
printf 'Tailing TTS log. Press Ctrl+C to stop tail.\n\n'

touch "$LOG_DIR/tts.log"
tail -f "$LOG_DIR/tts.log"
