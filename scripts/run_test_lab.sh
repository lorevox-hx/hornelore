#!/usr/bin/env bash
# WO-QA-01 — Hornelore Quality Harness
# Seeds synthetic test narrators and runs the full harness matrix.
#
# Prereqs (once per environment):
#   1. .env has MAX_NEW_TOKENS_CHAT_HARD=2048 and REPETITION_PENALTY_DEFAULT=1.1
#   2. API has been restarted after step 1 (env changes aren't hot-reloaded)
#   3. Hornelore API reachable at http://127.0.0.1:8000
#   4. No active interview session (harness competes for the single GPU slot)
#
# Arguments are passed through to test_lab_runner.py, e.g.:
#   bash scripts/run_test_lab.sh --compare-to 20260414_103500
#   bash scripts/run_test_lab.sh --dry-run
#   bash scripts/run_test_lab.sh --run-label my_label
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

STATEMENTS_FILE="$ROOT_DIR/data/test_lab/narrator_statements.json"

echo "[WO-QA-02] root=$ROOT_DIR"

# Ensure Python deps — httpx + websockets are needed by test_lab_runner.py
MISSING=()
python3 -c "import httpx" 2>/dev/null      || MISSING+=("httpx")
python3 -c "import websockets" 2>/dev/null || MISSING+=("websockets")
if (( ${#MISSING[@]} )); then
  echo "[WO-QA-02] installing missing deps: ${MISSING[*]}"
  python3 -m pip install --user "${MISSING[@]}" >/dev/null 2>&1 \
    || python3 -m pip install --break-system-packages "${MISSING[@]}" >/dev/null 2>&1 \
    || { echo "[WO-QA-02] pip install failed — install httpx and websockets manually"; exit 1; }
fi

# WO-QA-02 preflight: narrator statements fixture must exist for Channel A.
# A missing fixture would silently degrade to "Lori channel only" runs and
# we'd lose the suppression metric. Fail loud instead.
if [[ ! -f "$STATEMENTS_FILE" ]]; then
  echo "[WO-QA-02] ERROR: missing narrator statements fixture:"
  echo "  $STATEMENTS_FILE"
  echo "[WO-QA-02] add data/test_lab/narrator_statements.json before launch."
  exit 1
fi
echo "[WO-QA-02] verified narrator statements fixture: $STATEMENTS_FILE"

# Default to QA-02-style labeled runs unless caller already provided --run-label.
HAS_RUN_LABEL=0
for arg in "$@"; do
  [[ "$arg" == "--run-label" ]] && { HAS_RUN_LABEL=1; break; }
done
DEFAULT_RUN_LABEL="qa02_$(date +%Y%m%d_%H%M%S)"

echo "[WO-QA-02] seeding synthetic test narrators…"
python3 scripts/seed_test_narrators.py

echo "[WO-QA-02] launching harness…"
if [[ "$HAS_RUN_LABEL" -eq 1 ]]; then
  python3 scripts/test_lab_runner.py "$@"
else
  python3 scripts/test_lab_runner.py --run-label "$DEFAULT_RUN_LABEL" "$@"
fi

echo "[WO-QA-02] done."
