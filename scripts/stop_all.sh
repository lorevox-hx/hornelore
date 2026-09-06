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

# Useful-log snapshot — parallel to api_log snapshot. Captures the
# always-on filtered log so every stop leaves a clean, denoised
# evidence trail in docs/reports/ alongside the raw api.log.
# Both snapshots are .gitignored.
snapshot_useful_log() {
  local log_src="$USEFUL_LOG_FILE"
  local reports_dir="$ROOT_DIR/docs/reports"
  if [[ ! -f "$log_src" ]]; then
    printf 'Snapshot: no useful.log to snapshot.\n'
    return 0
  fi
  mkdir -p "$reports_dir"
  local ts size
  ts="$(date +%Y%m%d_%H%M%S)"
  size="$(du -h "$log_src" 2>/dev/null | cut -f1)"
  cp "$log_src" "$reports_dir/useful_log_${ts}.txt"
  cp "$log_src" "$reports_dir/useful_log_latest.txt"
  printf 'Snapshot: docs/reports/useful_log_%s.txt (%s)\n' "$ts" "${size:-?}"
  printf 'Latest:   docs/reports/useful_log_latest.txt\n'
}

if [[ "$_snapshot_logs" -eq 1 ]]; then
  snapshot_api_log    || printf 'API snapshot failed — continuing stop.\n'
  snapshot_useful_log || printf 'Useful snapshot failed — continuing stop.\n'
fi

# Stop the useful-log tail FIRST so it's not chasing logs that
# disappear when UI/TTS/API shut down. Snapshot already copied above.
stop_useful_log_tail

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

# ── DISARM THE EVALUATION MARKER ────────────────────────────────
#
# Added 2026-09-06, and it is the other half of the arming design
# rather than a tidy-up. `.runtime/eval/current_eval_dir` is what turns
# response tracing on: while it exists, EVERY start arms tracing,
# including ordinary sessions with Kent and Janice. Leaving it behind
# would be worse than the `.env` flag it replaced, because at least a
# flag in `.env` is visible when you go looking for one.
#
# Arming and disarming are therefore the same gesture as starting and
# stopping the measurement. Deliberately AFTER the log snapshots above:
# those write into the run's own directory, and removing the marker
# first would send them somewhere else.
#
# The path is REPORTED before it is removed. It is the only pointer to
# the run that just finished, and an operator who wants to analyse it
# needs to be told where it went, not left to reconstruct it from a
# timestamp.
if [[ -r "$RUNTIME_DIR/eval/current_eval_dir" ]]; then
  _eval_dir="$(<"$RUNTIME_DIR/eval/current_eval_dir")"
  rm -f "$RUNTIME_DIR/eval/current_eval_dir"
  printf '\nEvaluation DISARMED. Response tracing is off for the next start.\n'
  if [[ -n "$_eval_dir" ]]; then
    printf '  This run:  %s\n' "$_eval_dir"
    printf '  Traces:    %s/response-trace\n' "$_eval_dir"
  fi
  unset _eval_dir
fi

printf '\nAll Hornelore services stopped.\n'
