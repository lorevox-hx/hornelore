#!/usr/bin/env bash
# WO-QA-01 — Compact live monitor for the Test Lab harness.
# Shows: GPU util + VRAM, harness state, last 8 log lines. Refreshes every 2s.
# Ctrl+C stops watching (harness run continues unaffected).
#
# Usage:
#   bash scripts/test_lab_watch.sh
set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a; source "${REPO_ROOT}/.env"; set +a
fi
DATA_DIR="${DATA_DIR:-/mnt/c/hornelore_data}"
LOG_PATH="${DATA_DIR}/test_lab/runner.log"
API_BASE="${HORNELORE_API_BASE:-http://localhost:8000}"

trap 'echo; exit 0' INT TERM

while true; do
  clear
  TS="$(date '+%H:%M:%S')"

  # ── GPU: one line ─────────────────────────────────────────────
  if command -v nvidia-smi >/dev/null 2>&1; then
    GPU_LINE="$(nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu \
                           --format=csv,noheader,nounits 2>/dev/null | head -1)"
    IFS=', ' read -r UTIL VRAM VTOT TEMP <<< "${GPU_LINE}"
    GPU_FMT="GPU ${UTIL}%   VRAM ${VRAM}/${VTOT} MiB   ${TEMP}°C"
  else
    GPU_FMT="(nvidia-smi unavailable)"
  fi

  # ── Status: state + pid ───────────────────────────────────────
  STATUS="$(curl -sS --max-time 2 "${API_BASE}/api/test-lab/status" 2>/dev/null)"
  STATE="$(echo "${STATUS}" | grep -oE '"state":"[^"]+"' | head -1 | cut -d'"' -f4)"
  PID="$(echo "${STATUS}"   | grep -oE '"pid":[0-9]+'    | head -1 | cut -d: -f2)"
  STATE_FMT="${STATE:-?}"
  [[ -n "${PID:-}" ]] && STATE_FMT="${STATE_FMT} (pid ${PID})"

  echo "  [${TS}]   ${GPU_FMT}   |   test-lab: ${STATE_FMT}"
  echo "  ────────────────────────────────────────────────────────────────"
  if [[ -f "${LOG_PATH}" ]]; then
    tail -n 8 "${LOG_PATH}" 2>/dev/null | sed 's/^/  /'
  else
    echo "  (no runner.log yet)"
  fi

  sleep 2
done
