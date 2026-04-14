#!/usr/bin/env bash
# WO-QA-01 — Test Lab doctor / one-shot verifier
#
# Runs all diagnostic + recovery + dry-run steps in one pass. Safe to
# re-run. Prints exactly what's going on at each step so when something
# fails you know which step broke.
#
# Usage:
#   bash scripts/test_lab_doctor.sh
#
# Optional:
#   DRY_ONLY=1 bash scripts/test_lab_doctor.sh   # run only up to dry-run
#   NO_DRY=1   bash scripts/test_lab_doctor.sh   # skip dry-run entirely

set -u  # unset vars are errors, but don't exit on first failure (-e off so we can summarize)

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

BLUE="\033[1;34m"
GREEN="\033[1;32m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
NC="\033[0m"

say()  { echo -e "${BLUE}==${NC} $*"; }
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  ⚠${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; }

# ── 1. Kill any stuck harness processes ──────────────────────────
say "Step 1 — killing any stuck harness processes"
pkill -f test_lab_runner 2>/dev/null && ok "killed test_lab_runner" || ok "no test_lab_runner processes"
pkill -f run_test_lab    2>/dev/null && ok "killed run_test_lab"    || ok "no run_test_lab processes"

# ── 2. Load .env so DATA_DIR / DB_NAME are available ─────────────
say "Step 2 — loading .env"
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/.env"
  set +a
  ok ".env loaded"
else
  fail ".env not found at ${REPO_ROOT}/.env"
fi

DATA_DIR="${DATA_DIR:-/mnt/c/hornelore_data}"
DB_NAME="${DB_NAME:-hornelore.sqlite3}"
DB_PATH="${DATA_DIR}/db/${DB_NAME}"
API_BASE="${HORNELORE_API_BASE:-http://localhost:8000}"
LOG_PATH="${DATA_DIR}/test_lab/runner.log"

echo "    DATA_DIR = ${DATA_DIR}"
echo "    DB_NAME  = ${DB_NAME}"
echo "    DB_PATH  = ${DB_PATH}"
echo "    API_BASE = ${API_BASE}"

# ── 3. Reset Test Lab status ─────────────────────────────────────
say "Step 3 — resetting Test Lab status"
if curl -sS --max-time 5 -X POST "${API_BASE}/api/test-lab/reset" >/dev/null 2>&1; then
  ok "status reset"
else
  warn "could not reach ${API_BASE}/api/test-lab/reset (API may be down)"
fi

# ── 4. Confirm API is alive ──────────────────────────────────────
say "Step 4 — confirming API is alive"
if curl -sS --max-time 5 "${API_BASE}/api/ping" >/dev/null 2>&1; then
  ok "API responded on ${API_BASE}"
else
  fail "API not responding on ${API_BASE} — start the stack first"
  exit 1
fi

# ── 5. Confirm DB exists and inspect schema ──────────────────────
say "Step 5 — inspecting DB"
if [[ ! -f "${DB_PATH}" ]]; then
  fail "DB not found at ${DB_PATH}"
  exit 1
fi
ok "DB exists: ${DB_PATH}"
echo "    people columns:"
sqlite3 "${DB_PATH}" "PRAGMA table_info(people);" 2>&1 | awk -F'|' '{print "      "$2" ("$3")"}' || warn "could not read schema"

# ── 6. Seed test narrators ───────────────────────────────────────
say "Step 6 — seeding synthetic test narrators"
python3 scripts/seed_test_narrators.py
SEED_RC=$?
if [[ $SEED_RC -eq 0 ]]; then
  ok "seed succeeded"
else
  fail "seed failed (exit $SEED_RC) — see traceback above"
  exit $SEED_RC
fi

# ── 7. Verify rows landed ────────────────────────────────────────
say "Step 7 — verifying test narrators are in the DB"
TEST_ROWS="$(sqlite3 "${DB_PATH}" "SELECT id,display_name,narrator_type FROM people WHERE narrator_type='test';" 2>/dev/null)"
if [[ -n "${TEST_ROWS}" ]]; then
  ok "test narrators present:"
  echo "${TEST_ROWS}" | awk -F'|' '{print "    - "$2" ("$1") type="$3}'
else
  fail "no rows with narrator_type='test' — seed did not persist"
  exit 1
fi

# ── 8. Start dry-run via API (optional) ──────────────────────────
if [[ "${NO_DRY:-0}" == "1" ]]; then
  say "Step 8 — skipped (NO_DRY=1)"
else
  say "Step 8 — starting dry-run via /api/test-lab/run"
  RESP="$(curl -sS --max-time 10 -X POST "${API_BASE}/api/test-lab/run" \
           -H 'Content-Type: application/json' \
           -d '{"dry_run":true,"run_label":"doctor_dry"}' 2>&1)"
  if echo "${RESP}" | grep -q '"ok":true'; then
    PID="$(echo "${RESP}" | grep -oE '"pid":[0-9]+' | head -1 | cut -d: -f2)"
    ok "dry-run started (pid ${PID})"
    echo "    response: ${RESP}"
  else
    fail "could not start dry-run: ${RESP}"
    exit 1
  fi

  if [[ "${DRY_ONLY:-0}" == "1" ]]; then
    ok "DRY_ONLY=1 → exiting. Tail ${LOG_PATH} to watch."
    exit 0
  fi

  # ── 9. Tail the log and wait for completion ───────────────────
  say "Step 9 — tailing log while dry-run finishes (Ctrl-C to stop tailing; run continues in background)"
  : > /tmp/wo_qa01_tail_marker
  # Wait up to 4 minutes, watching for the completion line
  tail -n 0 -F "${LOG_PATH}" &
  TAIL_PID=$!
  trap 'kill $TAIL_PID 2>/dev/null' EXIT

  DEADLINE=$(( $(date +%s) + 240 ))
  while (( $(date +%s) < DEADLINE )); do
    if grep -q "WO-QA-01] complete" "${LOG_PATH}" 2>/dev/null; then
      echo ""
      ok "dry-run completed"
      break
    fi
    if grep -q "Traceback" "${LOG_PATH}" 2>/dev/null && ! grep -q "preflight" "${LOG_PATH}"; then
      echo ""
      fail "traceback detected — dry-run failed"
      break
    fi
    sleep 2
  done

  kill $TAIL_PID 2>/dev/null
  echo ""

  # ── 10. Summary ───────────────────────────────────────────────
  say "Step 10 — summary"
  STATUS="$(curl -sS --max-time 5 "${API_BASE}/api/test-lab/status" 2>/dev/null)"
  echo "    status: ${STATUS}"
  LATEST="$(curl -sS --max-time 5 "${API_BASE}/api/test-lab/results" 2>/dev/null | \
            grep -oE '\[[^]]*\]' | tr -d '[]' | tr ',' '\n' | head -3)"
  if [[ -n "${LATEST}" ]]; then
    ok "recent runs:"
    echo "${LATEST}" | awk '{print "    "$0}'
  fi
fi

say "Doctor finished."
