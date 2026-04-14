#!/usr/bin/env bash
# WO-QA-01 — Live monitor: GPU + harness log + status in one terminal.
#
# Refreshes every 2 seconds. Ctrl+C to stop (harness run, if any, continues
# in the background unaffected).
#
# Usage:
#   bash scripts/test_lab_watch.sh
set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load .env for DATA_DIR
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a; source "${REPO_ROOT}/.env"; set +a
fi
DATA_DIR="${DATA_DIR:-/mnt/c/hornelore_data}"
LOG_PATH="${DATA_DIR}/test_lab/runner.log"
API_BASE="${HORNELORE_API_BASE:-http://localhost:8000}"

clear
trap 'echo; echo "[watch] stopped"; exit 0' INT TERM

while true; do
  clear
  echo "=================================================================="
  echo "  WO-QA-01 Test Lab — Live Monitor"
  echo "  $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=================================================================="

  # ── GPU ─────────────────────────────────────────────────────
  echo ""
  echo "── GPU ────────────────────────────────────────────────────────────"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw \
               --format=csv,noheader 2>/dev/null \
      | awk -F', ' '{printf "  %s\n  GPU: %-6s  VRAM: %-12s / %-12s  Temp: %-6s  Power: %s\n", $1, $2, $3, $4, $5, $6}'
  else
    echo "  nvidia-smi not available"
  fi

  # ── Harness status ──────────────────────────────────────────
  echo ""
  echo "── Test Lab status ────────────────────────────────────────────────"
  STATUS="$(curl -sS --max-time 3 "${API_BASE}/api/test-lab/status" 2>/dev/null)"
  if [[ -n "${STATUS}" ]]; then
    STATE="$(echo "${STATUS}" | grep -oE '"state":"[^"]+"' | head -1 | cut -d'"' -f4)"
    PID="$(echo "${STATUS}"   | grep -oE '"pid":[0-9]+' | head -1 | cut -d: -f2)"
    LATEST="$(echo "${STATUS}" | grep -oE '"latest_run":"[^"]+"' | head -1 | cut -d'"' -f4)"
    echo "  state:  ${STATE:-unknown}"
    [[ -n "${PID:-}" ]]    && echo "  pid:    ${PID}"
    [[ -n "${LATEST:-}" ]] && echo "  latest: ${LATEST}"
  else
    echo "  (API not responding at ${API_BASE})"
  fi

  # ── Log tail ────────────────────────────────────────────────
  echo ""
  echo "── runner.log (last 15 lines) ─────────────────────────────────────"
  if [[ -f "${LOG_PATH}" ]]; then
    tail -n 15 "${LOG_PATH}" 2>/dev/null | sed 's/^/  /'
  else
    echo "  log not found at ${LOG_PATH}"
  fi

  echo ""
  echo "── (Ctrl+C to stop watching; harness run continues in background) ─"
  sleep 2
done
