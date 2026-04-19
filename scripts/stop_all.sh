#!/usr/bin/env bash
# scripts/stop_all.sh — Hornelore 1.0
# Stops all three Hornelore services (UI first, then TTS, then API).
# Sets a clean-start flag so the next startup clears Hornelore browser state.
#
# Usage:
#   bash scripts/stop_all.sh            # stop + set clean-start flag (default)
#   bash scripts/stop_all.sh --no-clean # stop without setting clean-start flag
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/common.sh"

# ── Parse flags ──────────────────────────────────────────────────
_set_clean_flag=1
_snapshot_logs=1
for arg in "$@"; do
  case "$arg" in
    --no-clean)    _set_clean_flag=0 ;;
    --no-snapshot) _snapshot_logs=0 ;;
  esac
done

# ── Snapshot API log for post-run review ─────────────────────────
# Copies .runtime/logs/api.log to docs/reports/ so eval reports and
# log analysis always have a stable companion artifact on disk after
# the services stop. Snapshot files are gitignored (see .gitignore).
# Runs BEFORE services stop so the log is fully flushed by the tail.
snapshot_api_log() {
  local log_src="$LOG_DIR/api.log"
  local reports_dir="$ROOT_DIR/docs/reports"
  if [[ ! -f "$log_src" ]]; then
    printf 'Snapshot: no api.log to snapshot (service may not have started).\n'
    return 0
  fi
  mkdir -p "$reports_dir"
  local ts size
  ts="$(date +%Y%m%d_%H%M%S)"
  size="$(du -h "$log_src" 2>/dev/null | cut -f1)"
  cp "$log_src" "$reports_dir/api_log_${ts}.txt"
  cp "$log_src" "$reports_dir/api_log_latest.txt"
  printf 'Snapshot: docs/reports/api_log_%s.txt (%s)\n' "$ts" "${size:-?}"
  printf 'Latest:   docs/reports/api_log_latest.txt\n'
}

if [[ "$_snapshot_logs" -eq 1 ]]; then
  snapshot_api_log || printf 'Snapshot failed — continuing stop.\n'
fi

stop_named_process "Hornelore UI"  "$UI_PID_FILE"  "hornelore-serve.py|http.server.*${UI_PORT}"
stop_named_process "Hornelore TTS" "$TTS_PID_FILE" "hornelore_run_tts_8001|run_tts_8001|uvicorn.*${TTS_PORT}"
stop_named_process "Hornelore API" "$API_PID_FILE" "hornelore_run_gpu_8000|run_gpu_8000|uvicorn.*${API_PORT}"

# ── Set clean-start flag for next startup ────────────────────────
# When Hornelore restarts, the browser will auto-clear all Hornelore-scoped
# localStorage/sessionStorage/caches so the session starts fresh.
if [[ "$_set_clean_flag" -eq 1 ]]; then
  mkdir -p "$RUNTIME_DIR"
  printf '%s\n' "$(date -Iseconds)" > "$RUNTIME_DIR/reset_on_start"
  printf 'Clean-start flag set — next startup will clear browser state.\n'
fi

printf '\nAll Hornelore services stopped.\n'
