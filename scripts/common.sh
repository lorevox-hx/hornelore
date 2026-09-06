#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime"
PID_DIR="$RUNTIME_DIR/pids"
LOG_DIR="$RUNTIME_DIR/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

# ── WHAT THE CALLER ASKED FOR, BEFORE `.env` HAS ITS SAY ────────────
#
# Captured here and nowhere else, because after the next block there is
# no way to tell a value the operator typed from one `.env` supplied.
# `.env:258` pins `HORNELORE_RESPONSE_TRACE=0`, so `${VAR:-default}`
# below would never substitute and the evaluation marker could never arm
# anything — measured, after writing exactly that bug.
#
# Precedence, most specific first:
#   1. what the caller exported for THIS invocation
#   2. the experiment marker (`.runtime/eval/current_eval_dir`)
#   3. `.env`
#   4. off
_HL_TRACE_FROM_CALLER="${HORNELORE_RESPONSE_TRACE-}"
_HL_TRACE_DIR_FROM_CALLER="${HORNELORE_TRACE_DIR-}"

# ── Load .env if present ─────────────────────────────────────────
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

# ── RESPONSE-TRACE ENVIRONMENT — RESOLVED HERE, FOR EVERY LAUNCHER ──
#
# There are TWO launch paths and they do not share an environment:
#
#   scripts/start_all.sh          — one WSL shell, starts everything
#   Start Hornelore.bat           — Windows Terminal, four tabs, each
#                                   `wsl.exe bash --login <script>`
#
# The second is the one Chris actually uses. A `--login` shell launched
# from Windows inherits NOTHING from a WSL terminal, so
# `export HORNELORE_RESPONSE_TRACE=1` typed before clicking the shortcut
# never reaches the API process — and `start_all.sh` was the only file
# that exported it, so the shortcut path silently ran with tracing off
# while the operator believed it was on.
#
# Resolving it in `common.sh` puts it below both paths, which is the
# only place a single answer can live. An explicitly exported value
# still wins; this only supplies one when there is none.
#
# THE DESTINATION FOLLOWS A FILE, NOT AN INHERITED VARIABLE. The GPU
# recorder writes the run directory to `.runtime/eval/current_eval_dir`
# before the stack starts, so the API can read where this experiment's
# traces belong no matter how it was launched. That turns "did the
# export survive the login shell" from an inference into a fact on disk
# — and `/api/health/response-trace` reports `output_dir` so the
# preflight can prove it before a two-hour run is spent.
# ── THE MARKER FILE IS THE OPT-IN, AND IT IS SELF-LIMITING ──────────
#
# `.env` would also reach the shortcut path (it is sourced above under
# `set -a`), and it is the wrong place: a flag left there records every
# ordinary narrator turn from then on, forever, which is exactly what
# opt-in tracing exists to prevent. Nobody remembers to remove it.
#
# The marker is written by the GPU recorder when an experiment starts
# and removed by `stop_all.sh` when it ends, so arming and disarming are
# the same gesture as starting and stopping the measurement. An explicit
# `HORNELORE_RESPONSE_TRACE=0` still wins, for the case where the stack
# is restarted mid-experiment without wanting traces.
_hl_eval_dir=""
if [[ -r "$RUNTIME_DIR/eval/current_eval_dir" ]]; then
  # `$(<file)` strips trailing newlines, so a marker written with
  # `printf '%s\n'` yields the path and not the path-plus-newline.
  _hl_eval_dir="$(<"$RUNTIME_DIR/eval/current_eval_dir")"
fi

if [[ -n "$_HL_TRACE_FROM_CALLER" ]]; then
  export HORNELORE_RESPONSE_TRACE="$_HL_TRACE_FROM_CALLER"
elif [[ -n "$_hl_eval_dir" ]]; then
  export HORNELORE_RESPONSE_TRACE=1
else
  export HORNELORE_RESPONSE_TRACE="${HORNELORE_RESPONSE_TRACE:-0}"
fi

if [[ -n "$_HL_TRACE_DIR_FROM_CALLER" ]]; then
  export HORNELORE_TRACE_DIR="$_HL_TRACE_DIR_FROM_CALLER"
elif [[ -n "$_hl_eval_dir" ]]; then
  # A blank or deleted marker must not resolve to the repo root.
  # `_out_dir()` tests truthiness, so an empty value falls through to
  # the module default rather than writing traces into the cwd.
  export HORNELORE_TRACE_DIR="$_hl_eval_dir/response-trace"
else
  export HORNELORE_TRACE_DIR="${HORNELORE_TRACE_DIR:-}"
fi
unset _hl_eval_dir _HL_TRACE_FROM_CALLER _HL_TRACE_DIR_FROM_CALLER

#: Printed by the launchers so a run is never started in the belief
#: that tracing is on when it is off, or writing somewhere else.
hornelore_trace_banner() {
  if [[ "${HORNELORE_RESPONSE_TRACE:-0}" == "1" ]]; then
    printf 'Response trace: ENABLED (observation only)\n'
    printf '  destination: %s\n\n' \
      "${HORNELORE_TRACE_DIR:-<default> .runtime/eval/response-trace}"
  else
    printf 'Response trace: off. To record an evaluation run:\n'
    printf '  HORNELORE_RESPONSE_TRACE=1 ./scripts/start_all.sh\n'
    printf '  (or set it in .env before using the desktop shortcut)\n\n'
  fi
}

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