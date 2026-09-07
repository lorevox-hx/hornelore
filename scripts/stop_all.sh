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

# ── DISARMING IS A TRAP, NOT A LAST STATEMENT ───────────────────────
#
# CORRECTED 2026-09-06, after review. `.runtime/eval/current_eval_dir`
# is what turns response tracing ON: while it exists, EVERY start arms
# tracing, including ordinary sessions with Kent and Janice. That makes
# it a privacy boundary, and **a privacy boundary must not depend on
# every unrelated shutdown command succeeding.**
#
# This script runs `set -euo pipefail`. As the final statement, the
# disarm was skipped entirely if any earlier command exited non-zero — a
# wedged process, a missing pid file, a failed snapshot — and the next
# ordinary start would then quietly record every narrator turn. The
# failure mode was silent and the wrong way round: the messier the
# shutdown, the more likely tracing stayed on.
#
# On EVERY exit path now, because the trap fires last regardless of how
# the script leaves.
#
# CORRECTED 2026-09-06: an earlier version of this comment said the log
# snapshots below "write into the run's own directory". They do not —
# `snapshot_api_log` and `snapshot_useful_log` both write to
# `docs/reports/`. The ordering is still right, but not for the reason
# stated, and a plausible wrong reason in a comment is how the next
# person reasons wrongly about it.
#
# The run directory itself is never deleted. Only the "this run is
# current" pointer is, and `last_eval_dir` is written first so analysis
# after the Stop shortcut can `cat` it instead of hunting through
# terminal scrollback.
_hornelore_disarm_eval() {
  local marker="$RUNTIME_DIR/eval/current_eval_dir"
  [[ -r "$marker" ]] || return 0
  local dir
  dir="$(<"$marker")" || dir=""
  if [[ -n "$dir" ]]; then
    printf '%s\n' "$dir" > "$RUNTIME_DIR/eval/last_eval_dir" 2>/dev/null || true
  fi
  rm -f "$marker"
  printf '\nEvaluation DISARMED — response tracing is off for the next start.\n'
  if [[ -n "$dir" ]]; then
    printf '  This run:  %s\n' "$dir"
    printf '  Traces:    %s/response-trace\n' "$dir"
    printf '  Pointer:   .runtime/eval/last_eval_dir\n'
  fi
}
trap _hornelore_disarm_eval EXIT

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

printf '\nAll Hornelore services stopped.\n'
