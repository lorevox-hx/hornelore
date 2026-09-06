#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Response-trace environment: ONE authority, called twice ─────────
#
# The rule lives in `trace_env.sh` because a SECOND shell decides this
# too — `launchers/hornelore_run_gpu_8000.sh` loads `.env` again after
# this file has resolved it, and `.env` pins the flag to 0. Both shells
# call the same capture/resolve pair around their own `.env` load, so
# the chain composes instead of the last writer winning.
#
# Capture must happen BEFORE `.env`: it is sourced with `set -a`, and
# afterwards a value the caller exported is indistinguishable from one
# `.env` supplied.
# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/trace_env.sh"
hornelore_trace_capture

# ── Load .env if present ─────────────────────────────────────────
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

hornelore_trace_resolve "$ROOT_DIR"

API_PORT="${LOREVOX_API_PORT:-8000}"
TTS_PORT="${LOREVOX_TTS_PORT:-8001}"
UI_PORT="${HORNELORE_UI_PORT:-8082}"

API_PID_FILE="$PID_DIR/api.pid"
TTS_PID_FILE="$PID_DIR/tts.pid"
UI_PID_FILE="$PID_DIR/ui.pid"

# ── Useful (filtered) log — always-on per Chris's design 2026-06-17 ──
# Strips dashboard/heartbeat/test-lab noise, surfaces real harness
# events (chat_ws, story-trigger, utterance-frame, profile-seed,
# VRAM-GUARD, comm_control, reflection-shape, facts/add, family-truth,
# bio-builder/questionnaire, profiles/, chronology, transcript,
# extract-fields, interview/projection, ERROR, WARNING, Traceback,
# HTTP 4xx/5xx). Started by start_all.sh, stopped + snapshotted by
# stop_all.sh.
USEFUL_LOG_PID_FILE="$PID_DIR/useful_log.pid"
USEFUL_LOG_FILE="$LOG_DIR/useful.log"

# Hornelore uses its own launcher copies in hornelore/launchers.
API_CMD_DEFAULT="bash launchers/hornelore_run_gpu_8000.sh"
TTS_CMD_DEFAULT="bash launchers/hornelore_run_tts_8001.sh"
UI_CMD_DEFAULT="python3 hornelore-serve.py"

API_CMD="${LOREVOX_API_CMD:-$API_CMD_DEFAULT}"
TTS_CMD="${LOREVOX_TTS_CMD:-$TTS_CMD_DEFAULT}"
UI_CMD="${LOREVOX_UI_CMD:-$UI_CMD_DEFAULT}"

api_up() { curl -fsS "http://127.0.0.1:${API_PORT}/api/ping" >/dev/null 2>&1; }
tts_up() { curl -fsS "http://127.0.0.1:${TTS_PORT}/api/tts/voices" >/dev/null 2>&1; }
ui_up()  { curl -fsS "http://127.0.0.1:${UI_PORT}/ui/hornelore1.0.html" >/dev/null 2>&1; }

pid_is_running() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  tr -d '[:space:]' < "$file"
}

write_pid() {
  local file="$1" pid="$2"
  printf '%s\n' "$pid" > "$file"
}

clear_pid() {
  local file="$1"
  rm -f "$file"
}

start_named_process() {
  local name="$1" cmd="$2" pid_file="$3" log_file="$4"
  if [[ -f "$pid_file" ]]; then
    local old_pid
    old_pid="$(read_pid "$pid_file" || true)"
    if pid_is_running "$old_pid"; then
      printf '%s already running (pid %s).\n' "$name" "$old_pid"
      return 0
    fi
    clear_pid "$pid_file"
  fi

  printf 'Starting %s...\n' "$name"
  (
    cd "$ROOT_DIR"
    nohup bash -lc "$cmd" >> "$log_file" 2>&1 &
    echo $! > "$pid_file"
  )

  sleep 1
  local new_pid
  new_pid="$(read_pid "$pid_file" || true)"
  if pid_is_running "$new_pid"; then
    printf '%s started (pid %s).\n' "$name" "$new_pid"
  else
    printf '%s failed to start. Check %s\n' "$name" "$log_file"
    return 1
  fi
}

stop_named_process() {
  local name="$1" pid_file="$2" fallback_pattern="$3"
  local stopped=0
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(read_pid "$pid_file" || true)"
    if pid_is_running "$pid"; then
      printf 'Stopping %s (pid %s)...\n' "$name" "$pid"
      kill "$pid" 2>/dev/null || true
      sleep 1
      if pid_is_running "$pid"; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      stopped=1
    fi
    clear_pid "$pid_file"
  fi

  if pgrep -f "$fallback_pattern" >/dev/null 2>&1; then
    printf 'Stopping stray %s processes...\n' "$name"
    pkill -f "$fallback_pattern" || true
    stopped=1
  fi

  if [[ "$stopped" -eq 0 ]]; then
    printf '%s was not running.\n' "$name"
  fi
}

wait_for_health() {
  local name="$1" check_fn="$2" timeout_s="${3:-45}"
  local i=0
  local _reported_starting=0
  until "$check_fn"; do
    i=$((i+1))
    if [[ "$i" -ge "$timeout_s" ]]; then
      printf '%s did not become healthy within %ss.\n' "$name" "$timeout_s"
      return 1
    fi
    # Two-phase reporting: show "starting" at 5s, progress every 15s
    if [[ "$_reported_starting" -eq 0 && "$i" -ge 5 ]]; then
      printf '%s still starting... (waited %ds / %ds)\n' "$name" "$i" "$timeout_s"
      _reported_starting=1
    elif [[ "$_reported_starting" -eq 1 ]] && (( i % 15 == 0 )); then
      printf '%s still starting... (%ds / %ds)\n' "$name" "$i" "$timeout_s"
    fi
    sleep 1
  done
  printf '%s is healthy.\n' "$name"
}

# Extended health wait with retry after initial failure.
# Useful for services that take longer than the first timeout window
# (e.g. TTS model loading). Tries a second window before giving up.
wait_for_health_retry() {
  local name="$1" check_fn="$2" initial_timeout="${3:-90}" retry_timeout="${4:-120}"
  if wait_for_health "$name" "$check_fn" "$initial_timeout"; then
    return 0
  fi
  # Check if the process is still alive — if so, the service is probably
  # still loading (not crashed). Retry with a second window.
  local pid_file="${5:-}"
  if [[ -n "$pid_file" && -f "$pid_file" ]]; then
    local pid
    pid="$(read_pid "$pid_file" || true)"
    if pid_is_running "$pid"; then
      printf '%s process still alive — extending health check by %ds...\n' "$name" "$retry_timeout"
      if wait_for_health "$name" "$check_fn" "$retry_timeout"; then
        return 0
      fi
    fi
  fi
  printf '%s health check FAILED after all retries.\n' "$name"
  return 1
}

open_ui_in_windows() {
  local url="${1:-http://localhost:${UI_PORT}/ui/hornelore1.0.html}"
  if [[ -f "$RUNTIME_DIR/reset_on_start" ]]; then
    url="${url}?lorevox_reset=clean"
    rm -f "$RUNTIME_DIR/reset_on_start"
    printf '[startup] Clean-start flag detected — browser will auto-clear state.\n'
  fi
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Start-Process '$url'" >/dev/null 2>&1 || true
  fi
}

kill_stale_hornelore() {
  local killed=0
  for pattern in "hornelore_run_gpu_8000|run_gpu_8000" "uvicorn.*8000"; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      printf 'Killing stale process: %s\n' "$pattern"
      pkill -f "$pattern" 2>/dev/null || true
      killed=1
    fi
  done
  if [[ "$killed" -eq 1 ]]; then
    printf 'Waiting for GPU memory to release...\n'
    local _waited=0
    while [[ "$_waited" -lt 15 ]]; do
      sleep 1
      _waited=$((_waited + 1))
      if command -v nvidia-smi >/dev/null 2>&1; then
        local _used
        _used="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | xargs)"
        if [[ "$_used" -lt 1000 ]]; then
          printf 'GPU memory freed (%s MB used).\n' "$_used"
          break
        fi
        if (( _waited % 5 == 0 )); then
          printf '  Still waiting... (%s MB used, %ds)\n' "$_used" "$_waited"
        fi
      else
        sleep 4
        break
      fi
    done
    printf 'Stale processes cleaned up.\n'
  fi
  for f in "$API_PID_FILE"; do
    if [[ -f "$f" ]]; then
      local pid
      pid="$(tr -d '[:space:]' < "$f")"
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$f"
      fi
    fi
  done
}

kill_all_hornelore() {
  local killed=0
  for pattern in "hornelore_run_gpu_8000|run_gpu_8000" "uvicorn.*8000" "hornelore_run_tts_8001|run_tts_8001" "uvicorn.*8001" "hornelore-serve"; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      printf 'Killing stale process: %s\n' "$pattern"
      pkill -f "$pattern" 2>/dev/null || true
      killed=1
    fi
  done
  if [[ "$killed" -eq 1 ]]; then
    printf 'Waiting for ports to release...\n'
    sleep 2
    printf 'Stale processes cleaned up.\n'
  fi
  for f in "$API_PID_FILE" "$TTS_PID_FILE" "$UI_PID_FILE"; do
    if [[ -f "$f" ]]; then
      local pid
      pid="$(tr -d '[:space:]' < "$f")"
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$f"
      fi
    fi
  done
}

show_vram() {
  if command -v nvidia-smi >/dev/null 2>&1; then
    printf '\n--- GPU VRAM ---\n'
    nvidia-smi --query-gpu=name,memory.used,memory.free,memory.total --format=csv,noheader,nounits \
      | while IFS=',' read -r name used free total; do
          printf '  %s: %s MB used / %s MB free / %s MB total\n' "$name" "$used" "$free" "$total"
        done
  fi
}

# ── Useful (filtered) log tail — always-on background process ─────
# Started by start_all.sh BEFORE the API so it catches startup events.
# Tails api.log + tts.log (created when those services start), strips
# dashboard/heartbeat/poller noise, and surfaces only real harness
# events. Output appended to .runtime/logs/useful.log; stop_all.sh
# snapshots that file to docs/reports/ before stopping the tail.
start_useful_log_tail() {
  local pid_file="$USEFUL_LOG_PID_FILE"
  local out_file="$USEFUL_LOG_FILE"

  if [[ -f "$pid_file" ]]; then
    local old_pid
    old_pid="$(read_pid "$pid_file" || true)"
    if pid_is_running "$old_pid"; then
      printf 'Useful log filter already running (pid %s).\n' "$old_pid"
      return 0
    fi
    clear_pid "$pid_file"
  fi

  mkdir -p "$LOG_DIR"

  {
    printf '\n=== Hornelore useful log started %s ===\n' "$(date -Iseconds)"
    printf 'Filter: chat/story/profile/extract/projection/facts/family-truth/errors only\n\n'
  } >> "$out_file"

  printf 'Starting useful log filter...\n'
  (
    cd "$ROOT_DIR"
    nohup bash -lc '
      tail -F .runtime/logs/api.log .runtime/logs/tts.log 2>/dev/null \
        | grep --line-buffered -Ev '"'"'test-lab|stack-dashboard/(ui-heartbeat|summary|history|system-status)|/api/ping|/api/operator/safety-events|/api/operator/eval-harness/summary|/ui/hornelore1.0.html|/api/tts/voices'"'"' \
        | grep --line-buffered -E '"'"'chat_ws|story-trigger|utterance-frame|profile-seed|VRAM-GUARD|comm_control|reflection-shape|facts/add|family-truth|bio-builder/questionnaire|profiles/|chronology|transcript|extract-fields|interview/projection|ERROR|WARNING|Traceback|HTTP/1.1" [45][0-9][0-9]'"'"' \
        >> .runtime/logs/useful.log
    ' >/dev/null 2>&1 &
    echo $! > "$pid_file"
  )

  sleep 1
  local new_pid
  new_pid="$(read_pid "$pid_file" || true)"
  local api_log="$LOG_DIR/api.log"
  local ts
  ts="$(date -Iseconds)"
  if pid_is_running "$new_pid"; then
    printf 'Useful log filter started (pid %s): %s\n' "$new_pid" "$out_file"
    # Single-source-of-truth marker — also write to api.log so a
    # plain `tail .runtime/logs/api.log` proves the filter is up
    # without having to chase a separate PID file.
    printf '[%s] [startup] Useful log filter started (pid %s) -> %s\n' "$ts" "$new_pid" "$out_file" >> "$api_log"
  else
    printf 'Useful log filter failed to start.\n'
    printf '[%s] [startup] Useful log filter FAILED to start\n' "$ts" >> "$api_log"
    return 1
  fi
}

stop_useful_log_tail() {
  # Marker before tearing down, so the api.log snapshot captures the
  # stop event. stop_named_process is silent about which log it
  # belongs to; this gives the api.log reader one clear line.
  local api_log="$LOG_DIR/api.log"
  local ts
  ts="$(date -Iseconds)"
  printf '[%s] [shutdown] Stopping useful log filter\n' "$ts" >> "$api_log" 2>/dev/null || true
  stop_named_process "Hornelore useful log filter" "$USEFUL_LOG_PID_FILE" "tail -F .runtime/logs/api.log .runtime/logs/tts.log"
}