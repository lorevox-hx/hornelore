#!/usr/bin/env bash
# probe_trip_lane_post_1e388b5.sh
# ---------------------------------------------------------------
# Post-commit-1e388b5 live-API probe for the trip lane.
#
# 2026-07-23 (revision 2) — full rewrite after ChatGPT + live-ND
# review flagged HIGH-severity defects in the first version:
#   (1) response parser looked for {"trip":{"id":"..."}} but the API
#       actually returns {"trip_id":"..."} — so successful trip
#       creates produced empty NEW_ID and probe trips could not be
#       cleaned up.
#   (2) heredoc-plus-pipe conflict: `printf JSON | python - <<PY`
#       fed the Python program into stdin, so `json.load(sys.stdin)`
#       never saw the piped JSON. Two call sites: auto-narrator
#       selection AND day-index verification.
#   (3) "read-only by default" was false: the fake-person POST
#       always fired. If the validation gate ever regressed, this
#       "dry" probe would create the exact orphan trip it was
#       testing against.
#
# All three fixed here. Additional hardening:
#   * every POST/PATCH/DELETE gated behind CONFIRM_WRITES=1
#   * write mode REQUIRES explicit PERSON_ID (no auto-first-narrator)
#   * strict HTTP-422 assertion for the fake-person test with detail
#     verification (missing route would 404 and previously passed)
#   * shell trap tracks every trip we successfully created and DELETEs
#     each one on EXIT/INT/TERM, checking HTTP status of the delete
#   * SQLite version comparison uses Python numeric tuples, not a
#     shell glob (the glob missed the intended 3.44.x / 3.50.x
#     ranges and matched unrelated later ones)
#   * PRAGMA readout now honestly labels busy_timeout and
#     foreign_keys as CLI-session values (they're connection-scoped,
#     so a fresh CLI can't verify the API's connection settings)
#
# READ-ONLY BY DEFAULT. Every mutation — including the fake-person
# POST — is fenced behind CONFIRM_WRITES=1. A bare run performs only
# read-only queries. CONFIRM_WRITES=1 additionally requires an
# explicit PERSON_ID.
#
# Usage:
#   ./scripts/probe_trip_lane_post_1e388b5.sh                    # dry
#   PERSON_ID=<REAL_UUID> CONFIRM_WRITES=1 \
#       ./scripts/probe_trip_lane_post_1e388b5.sh
#
# Environment overrides (defaults from .env.example):
#   API=http://localhost:8000
#   DB=/mnt/c/hornelore_data/hornelore.sqlite3
#   PY=.venv-gpu/bin/python
#   ORPHAN_TRIP=4fdd9f93-dc86-4881-ae09-d690a4de9741
#   PERSON_ID=<REAL_UUID>   # REQUIRED when CONFIRM_WRITES=1
# ---------------------------------------------------------------
set -u  # unset variables are errors; -e off so probes continue past failures

API=${API:-http://localhost:8000}
DB=${DB:-/mnt/c/hornelore_data/hornelore.sqlite3}
PY=${PY:-.venv-gpu/bin/python}
ORPHAN_TRIP=${ORPHAN_TRIP:-4fdd9f93-dc86-4881-ae09-d690a4de9741}
CONFIRM_WRITES=${CONFIRM_WRITES:-0}
PERSON_ID=${PERSON_ID:-}

PASS=0
FAIL=0
WARN=0
CREATED_TRIPS=""   # space-separated list of trip IDs we made — trap cleans

# ── Cleanup trap ─────────────────────────────────────────────────
# Any trip we successfully created gets a best-effort DELETE on
# EXIT (normal), INT (Ctrl-C), or TERM. Checks the HTTP status so
# an operator can see cleanup that DIDN'T land — a stale probe
# trip in the DB is exactly the kind of state this probe was
# rewritten to prevent.
#
# 2026-07-23 (post-A+B review fix): the previous version registered
# `_cleanup` on all three signals AND called `exit` inside it. On
# INT/TERM that fired the cleanup TWICE — the signal-triggered
# _cleanup ran, called exit, which re-triggered the EXIT handler
# for a second cleanup pass. The second DELETE saw the trip
# already gone, returned 404, and printed the misleading "MANUAL
# CLEANUP REQUIRED" — despite cleanup having succeeded. Ctrl-C
# also produced exit code 0 instead of the SIGINT-conventional
# 130. Fix: `_cleanup` runs ONCE, and separate INT/TERM handlers
# just exit with the conventional signal codes (128 + signum) so
# the EXIT trap owns the actual DELETE work.
_cleanup() {
  local exit_code=$?
  # Detach every signal handler before we start so a slow DELETE
  # or a repeated Ctrl-C can never re-enter _cleanup.
  trap - EXIT INT TERM
  local id
  for id in $CREATED_TRIPS; do
    printf "     cleanup: DELETE trip %s ... " "$id"
    local code
    code=$(curl -sS -o /tmp/probe_cleanup_$$.out \
      -w "%{http_code}" --max-time 5 \
      -X DELETE "$API/api/trips/$id")
    if [ "$code" = "200" ] || [ "$code" = "204" ]; then
      printf "%s\n" "$code"
    else
      printf "\033[1;31mHTTP %s — MANUAL CLEANUP REQUIRED\033[0m\n" "$code"
      cat /tmp/probe_cleanup_$$.out 2>/dev/null | head -c 200; echo
    fi
    rm -f /tmp/probe_cleanup_$$.out 2>/dev/null
  done
  exit "$exit_code"
}
# EXIT owns the cleanup work; INT/TERM just exit with the
# conventional signal codes and the EXIT handler catches the exit.
trap _cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

hdr() { printf "\n\033[1;34m── %s ──\033[0m\n" "$*"; }
ok()  { printf "  \033[1;32m✔\033[0m  %s\n" "$*"; PASS=$((PASS+1)); }
bad() { printf "  \033[1;31m✘\033[0m  %s\n" "$*"; FAIL=$((FAIL+1)); }
warn(){ printf "  \033[1;33m!\033[0m  %s\n" "$*"; WARN=$((WARN+1)); }
info(){ printf "     %s\n" "$*"; }

cd /mnt/c/Users/chris/hornelore 2>/dev/null || {
  echo "This script must be run from WSL where /mnt/c/Users/chris/hornelore exists."
  exit 2
}

# ── 0. Stack health ────────────────────────────────────────────
hdr "0. Stack health"
if curl -fsS --max-time 3 "$API/" >/dev/null 2>&1; then
  ok "API reachable at $API"
else
  bad "API not reachable at $API — start the stack before running this script"
  echo
  echo "Nothing else to probe. Bounce the stack and re-run."
  exit 1
fi

# ── 1. SQLite runtime version (web-search #9, numeric compare) ─
hdr "1. SQLite runtime version"
# We hand the version string to Python and let it do numeric-tuple
# comparison. The original shell glob 3.5[12].0|... matched only
# 3.51.x and 3.52.x — NOT the intended 3.50.x pre-3.50.7 or 3.44.x
# pre-3.44.6 fixes. Numeric tuple parsing is unambiguous.
if [ -x "$PY" ]; then
  # Use python -c to avoid pipe/heredoc conflict — Python source
  # goes via -c argv, not stdin.
  VER_OUT=$("$PY" -c '
import sqlite3, sys
print(f"python={sys.version.split()[0]}")
print(f"sqlite3_module={sqlite3.version}")
print(f"sqlite_runtime={sqlite3.sqlite_version}")
' 2>/dev/null)
  echo "$VER_OUT" | while read L; do info "$L"; done
  RUNTIME=$(echo "$VER_OUT" | awk -F= '/sqlite_runtime/{print $2}')
  # Compare via Python: tuple(int, int, int)
  #
  # WAL-reset race window per SQLite release notes / official
  # documentation: BUG PRESENT from 3.7.0 through 3.51.2 EXCEPT the
  # specific backported fixes in 3.44.6 and 3.50.7. Main fix landed
  # in 3.51.3 and every subsequent release.
  #
  # Rules (evaluated top-down; first match wins):
  #   v >= (3,51,3)                       → safe
  #   v[:2] == (3,50) and v >= (3,50,7)   → safe (backport)
  #   v[:2] == (3,44) and v >= (3,44,6)   → safe (backport)
  #   v >= (3,7,0)                        → affected (broad WAL-reset window)
  #   otherwise                           → unknown (pre-WAL era)
  #
  # 2026-07-23 (post-A+B review fix): earlier version only flagged
  # 3.44.0-5 / 3.50.0-6 / 3.51.0-2 as affected, so 3.45.x-3.49.x
  # were incorrectly labeled "safe" — they are ALSO in the
  # affected window per SQLite's own docs.
  if [ -n "$RUNTIME" ]; then
    RISK=$("$PY" -c "
v = tuple(int(x) for x in '$RUNTIME'.split('.'))
if len(v) < 3:
    print('unknown')
elif v >= (3, 51, 3):
    print('safe')
elif v[:2] == (3, 50) and v >= (3, 50, 7):
    print('safe')
elif v[:2] == (3, 44) and v >= (3, 44, 6):
    print('safe')
elif v >= (3, 7, 0):
    print('affected')
else:
    print('unknown')
" 2>/dev/null)
    case "$RISK" in
      affected)
        warn "SQLite $RUNTIME is in the WAL-reset race window (present from 3.7.0 through 3.51.2 except the backported fixes in 3.44.6 and 3.50.7; primary fix in 3.51.3+). Watch for spurious SQLITE_BUSY under load."
        ;;
      safe)
        ok "SQLite runtime $RUNTIME is at or past the WAL-reset fix"
        ;;
      *)
        warn "Could not parse or classify SQLite runtime version '$RUNTIME'"
        ;;
    esac
  fi
else
  warn "Interpreter $PY not found; skipping version check. Set PY=<path> or activate the venv."
fi

# ── 2. Narrator UUID selection (WRITE mode requires explicit) ──
hdr "2. Narrator UUID"
if [ "$CONFIRM_WRITES" = "1" ]; then
  if [ -z "$PERSON_ID" ]; then
    bad "CONFIRM_WRITES=1 requires an explicit PERSON_ID (auto-picking the first narrator would create probe trips under a real user like Stefi/Joe/Frank). Re-run with PERSON_ID=<REAL_UUID>."
    exit 1
  fi
  # Verify the narrator exists BEFORE we start writing.
  # Use a temp file for the JSON body — no pipe/heredoc conflict.
  TMPJSON=$(mktemp -t probe_people.XXXXXX.json)
  curl -fsS --max-time 5 "$API/api/people" -o "$TMPJSON" 2>/dev/null || {
    bad "Could not fetch /api/people to verify PERSON_ID"
    rm -f "$TMPJSON"
    exit 1
  }
  NARRATOR_NAME=$("$PY" -c "
import json, sys
try:
    data = json.load(open('$TMPJSON'))
except Exception as exc:
    print(''); sys.exit(0)
if isinstance(data, dict):
    data = data.get('people') or data.get('items') or []
for row in data:
    if isinstance(row, dict) and row.get('id') == '$PERSON_ID':
        print(row.get('display_name') or '(no display name)'); break
" 2>/dev/null)
  rm -f "$TMPJSON"
  if [ -z "$NARRATOR_NAME" ]; then
    bad "PERSON_ID $PERSON_ID does not match any narrator on this instance. Refusing to write."
    exit 1
  fi
  ok "Using narrator $PERSON_ID ($NARRATOR_NAME)"
else
  # Read-only mode: don't need PERSON_ID for anything.
  info "Read-only mode — PERSON_ID not needed. (Set CONFIRM_WRITES=1 + PERSON_ID=<uuid> to run write tests.)"
fi

# ── 3. Orphan trip status ─────────────────────────────────────
hdr "3. Orphan trip from ND run"
if [ -r "$DB" ]; then
  ORPHAN_ROW=$(sqlite3 -readonly "$DB" \
    "SELECT id||'|'||COALESCE(title,'')||'|'||COALESCE(person_id,'') FROM trips WHERE id = '$ORPHAN_TRIP';" 2>/dev/null)
  if [ -n "$ORPHAN_ROW" ]; then
    warn "Orphan trip still present: $ORPHAN_ROW"
    if [ "$CONFIRM_WRITES" = "1" ]; then
      RESP=$(curl -sS -o /tmp/orphan_del.out -w "%{http_code}" \
        --max-time 5 -X DELETE "$API/api/trips/$ORPHAN_TRIP")
      if [ "$RESP" = "200" ] || [ "$RESP" = "204" ]; then
        ok "DELETE /api/trips/$ORPHAN_TRIP returned $RESP"
      else
        bad "DELETE /api/trips/$ORPHAN_TRIP returned $RESP — see /tmp/orphan_del.out"
        cat /tmp/orphan_del.out 2>/dev/null | head -c 400
        echo
      fi
    else
      info "Re-run with CONFIRM_WRITES=1 to delete via API"
    fi
  else
    ok "Orphan trip $ORPHAN_TRIP is gone"
  fi
else
  warn "DB not readable at $DB — skipping DB-side orphan check"
fi

# ── 4. Broader orphan sweep ───────────────────────────────────
hdr "4. Broader orphan sweep (all trips whose person_id has no /people row)"
if [ -r "$DB" ]; then
  ORPHANS=$(sqlite3 -readonly "$DB" \
    "SELECT COUNT(*) FROM trips t LEFT JOIN people p ON t.person_id=p.id WHERE p.id IS NULL;" 2>/dev/null)
  if [ "$ORPHANS" = "0" ]; then
    ok "0 orphan trips in DB"
  else
    warn "$ORPHANS orphan trip(s) — list:"
    sqlite3 -readonly "$DB" -header -column \
      "SELECT t.id, substr(t.title,1,40) title, t.person_id, t.created_at FROM trips t LEFT JOIN people p ON t.person_id=p.id WHERE p.id IS NULL LIMIT 20;" \
      2>/dev/null | sed 's/^/     /'
    info "These will be cleaned up automatically by the deferred FK-migration commit."
    info "For now, DELETE via API (or add IDs to a follow-up cleanup script)."
  fi
else
  warn "DB not readable; skipping sweep"
fi

# ── 5. person_id validation gate (WRITE ONLY — regression check) ──
# The whole point of this test is to catch the regression class where
# a bogus person_id gets accepted and creates an orphan trip. Under
# the corrected API this returns 422 and does not write — but if that
# regression comes back, running this test in dry mode would produce
# the exact orphan we're testing for. Fence behind CONFIRM_WRITES=1
# so a bare probe run never mutates the DB.
hdr "5. POST /api/trips must reject a nonexistent person_id (WRITE)"
if [ "$CONFIRM_WRITES" != "1" ]; then
  info "Skipped in read-only mode (CONFIRM_WRITES=1 required to probe validation)"
else
  FAKE_PID="PASTE_UUID_HERE"
  RESP=$(curl -sS -o /tmp/probe_reject.out -w "%{http_code}" \
    --max-time 5 -X POST "$API/api/trips" \
    -H "Content-Type: application/json" \
    -d "{\"person_id\":\"$FAKE_PID\",\"title\":\"PROBE_REJECT_$(date +%s)\"}")
  if [ "$RESP" = "422" ]; then
    # Verify the detail actually mentions the fake person_id — a
    # missing route would return 404 and previously slipped through
    # the accept-list. A generic 422 from some other validator would
    # also mislead. We want to see the exact "does not match any
    # narrator" branch.
    DETAIL=$(cat /tmp/probe_reject.out 2>/dev/null)
    if echo "$DETAIL" | grep -qE "does not match any narrator|not found|no narrator"; then
      ok "Fake person_id rejected with 422 + descriptive detail"
    else
      bad "422 returned but detail did NOT mention the missing narrator — Pydantic-level rejection, not the app-level gate. Detail: $(echo "$DETAIL" | head -c 200)"
    fi
  else
    bad "Fake person_id returned HTTP $RESP (expected 422) — validation gate may have regressed. Response: $(cat /tmp/probe_reject.out 2>/dev/null | head -c 300)"
  fi
  # If somehow a trip DID get created under PASTE_UUID_HERE despite
  # our expectations, sweep it. This is the belt-and-braces case that
  # the pre-rewrite version could produce on regression.
  if [ -r "$DB" ]; then
    ROW=$(sqlite3 -readonly "$DB" \
      "SELECT id FROM trips WHERE person_id = 'PASTE_UUID_HERE';" 2>/dev/null)
    if [ -n "$ROW" ]; then
      warn "Regression detected — an orphan trip WAS created under PASTE_UUID_HERE despite the gate:"
      for orphan_id in $ROW; do
        info "  registering for cleanup: $orphan_id"
        CREATED_TRIPS="$CREATED_TRIPS $orphan_id"
      done
    fi
  fi
fi

# ── 6. Auto-day-generation on trip create (WRITE) ─────────────
hdr "6. Auto-day-generation on trip create (July 14–19 → 6 cards)"
if [ "$CONFIRM_WRITES" != "1" ]; then
  info "Skipped in read-only mode"
else
  TITLE="PROBE_TRIP_$(date +%s)"
  # POST create — write body via -d, capture response to temp file for
  # honest parsing (no pipe/heredoc conflict).
  RESP_FILE=$(mktemp -t probe_create.XXXXXX.json)
  HTTP_CODE=$(curl -sS -o "$RESP_FILE" -w "%{http_code}" --max-time 15 \
    -X POST "$API/api/trips" -H "Content-Type: application/json" \
    -d "{\"person_id\":\"$PERSON_ID\",\"title\":\"$TITLE\",\"start_date\":\"2026-07-14\",\"end_date\":\"2026-07-19\"}")
  if [ "$HTTP_CODE" != "200" ]; then
    bad "POST /api/trips returned HTTP $HTTP_CODE — $(cat "$RESP_FILE" | head -c 300)"
    rm -f "$RESP_FILE"
  else
    # Correct trip_id parser (the previous d.get("trip",{}).get("id")
    # was the primary bug — the API returns {"trip_id": "..."}).
    NEW_ID=$("$PY" -c "
import json, sys
try:
    d = json.load(open('$RESP_FILE'))
except Exception as exc:
    print(''); sys.exit(0)
print(d.get('trip_id') or '')
" 2>/dev/null)
    rm -f "$RESP_FILE"
    if [ -z "$NEW_ID" ]; then
      bad "Trip create returned HTTP 200 but no trip_id in response — parser regression?"
    else
      ok "Trip created: $NEW_ID"
      CREATED_TRIPS="$CREATED_TRIPS $NEW_ID"

      # GET /days and check partition count
      DAY_FILE=$(mktemp -t probe_days.XXXXXX.json)
      curl -fsS --max-time 5 "$API/api/trips/$NEW_ID/days" -o "$DAY_FILE"
      DAY_CT=$("$PY" -c "
import json, sys
try:
    d = json.load(open('$DAY_FILE'))
except Exception:
    print('0'); sys.exit(0)
# Partition contract: 'days' is in-window; 'preserved' is out-of-window.
print(len(d.get('days') or []))
" 2>/dev/null)
      PRESERVED_CT=$("$PY" -c "
import json, sys
try:
    d = json.load(open('$DAY_FILE'))
except Exception:
    print('0'); sys.exit(0)
print(len(d.get('preserved') or []))
" 2>/dev/null)
      rm -f "$DAY_FILE"
      if [ "$DAY_CT" = "6" ] && [ "$PRESERVED_CT" = "0" ]; then
        ok "6 day cards in current window, 0 preserved (correct partition)"
      else
        bad "Expected days=6, preserved=0. Got days=$DAY_CT, preserved=$PRESERVED_CT"
      fi

      # 6b. Move start earlier and verify renumber + partition
      #
      # 2026-07-23 (post-A+B review fix): the previous version threw
      # away the PATCH's HTTP status and treated any-count-that-is-
      # sequential as OK-with-warning. A PATCH that failed with 500
      # (leaving the original 6 cards intact) still returned
      # `count=6, sequential`, printed a soft warn, and the probe
      # exited 0. Now: PATCH must be HTTP 200, and exactly 10 cards
      # is the ONLY acceptable outcome.
      hdr "6b. Move start to 2026-07-10 and verify day_index renumber"
      PATCH_RC=$(curl -sS -o /tmp/probe_prepend_$$.out \
        -w "%{http_code}" --max-time 10 \
        -X PATCH "$API/api/trips/$NEW_ID" \
        -H "Content-Type: application/json" \
        -d '{"start_date":"2026-07-10"}')
      if [ "$PATCH_RC" != "200" ]; then
        bad "PATCH start_date returned HTTP $PATCH_RC (expected 200) — response: $(cat /tmp/probe_prepend_$$.out 2>/dev/null | head -c 300)"
      else
        D2_FILE=$(mktemp -t probe_days2.XXXXXX.json)
        DAYS_RC=$(curl -sS -o "$D2_FILE" -w "%{http_code}" \
          --max-time 5 "$API/api/trips/$NEW_ID/days")
        if [ "$DAYS_RC" != "200" ]; then
          bad "GET /days after PATCH returned HTTP $DAYS_RC (expected 200)"
        else
          ORDER_OK=$("$PY" -c "
import json, sys
try:
    d = json.load(open('$D2_FILE'))
except Exception as exc:
    print(f'FAIL parse: {exc}'); sys.exit(0)
days = d.get('days') or []
days_sorted = sorted(days, key=lambda r: r.get('date',''))
for i, row in enumerate(days_sorted, start=1):
    if row.get('day_index') != i:
        print(f'FAIL row date={row.get(\"date\")!r} day_index={row.get(\"day_index\")!r} expected={i}')
        sys.exit(0)
print(f'OK count={len(days)}')
" 2>/dev/null)
          case "$ORDER_OK" in
            OK\ count=10)
              ok "day_index renumbered 1..10 in date order (July 10–19)"
              ;;
            OK\ count=*)
              # Sequential but not the expected 10 = real failure,
              # not a warning. The PATCH may have silently no-op'd
              # or generation may not have added the 4 new days.
              bad "day_index sequential but count wrong: $ORDER_OK (expected exactly 10 for July 10-19)"
              ;;
            *)
              bad "day_index NOT sequential after prepend: $ORDER_OK"
              ;;
          esac
        fi
        rm -f "$D2_FILE"
      fi
      rm -f /tmp/probe_prepend_$$.out
      # Trap will DELETE this trip on exit
    fi
  fi
fi

# ── 7. days_warning + sync_warning surfaced on reversed-date PATCH ─
hdr "7. PATCH with reversed dates surfaces days_warning"
if [ "$CONFIRM_WRITES" != "1" ]; then
  info "Skipped in read-only mode"
else
  TITLE="PROBE_WARN_$(date +%s)"
  CRESP=$(mktemp -t probe_warn_create.XXXXXX.json)
  curl -sS -o "$CRESP" --max-time 15 -X POST "$API/api/trips" \
    -H "Content-Type: application/json" \
    -d "{\"person_id\":\"$PERSON_ID\",\"title\":\"$TITLE\",\"start_date\":\"2026-08-01\",\"end_date\":\"2026-08-05\"}"
  NEW_ID=$("$PY" -c "
import json, sys
try:
    d = json.load(open('$CRESP'))
except Exception:
    print(''); sys.exit(0)
print(d.get('trip_id') or '')
" 2>/dev/null)
  rm -f "$CRESP"
  if [ -z "$NEW_ID" ]; then
    bad "Warning probe: trip create failed, cannot proceed"
  else
    CREATED_TRIPS="$CREATED_TRIPS $NEW_ID"
    PATCH_FILE=$(mktemp -t probe_patch.XXXXXX.json)
    curl -sS --max-time 15 -o "$PATCH_FILE" -X PATCH \
      "$API/api/trips/$NEW_ID" -H "Content-Type: application/json" \
      -d '{"start_date":"2026-08-05","end_date":"2026-08-01"}'
    HAS_WARN=$("$PY" -c "
import json, sys
try:
    d = json.load(open('$PATCH_FILE'))
except Exception:
    print('NO'); sys.exit(0)
print('YES' if 'days_warning' in d else 'NO')
" 2>/dev/null)
    if [ "$HAS_WARN" = "YES" ]; then
      DW=$("$PY" -c "
import json
d = json.load(open('$PATCH_FILE'))
print(d.get('days_warning',''))
" 2>/dev/null)
      ok "days_warning present in PATCH response"
      info "days_warning: $DW"
    else
      bad "days_warning NOT surfaced on reversed-date PATCH. Response head: $(cat "$PATCH_FILE" | head -c 300)"
    fi
    rm -f "$PATCH_FILE"
  fi
fi

# ── 8. WAL / journal-mode sanity (persistent DB property) ─────
# journal_mode is a persistent DB-level setting (survives across
# connections). busy_timeout and foreign_keys are connection-local
# settings, so a fresh CLI can't verify the API's connection state.
# The router's DB _connect() sets both explicitly per connection.
hdr "8. Journal-mode sanity (persistent property)"
if [ -r "$DB" ]; then
  JM=$(sqlite3 -readonly "$DB" "PRAGMA journal_mode;" 2>/dev/null)
  info "journal_mode=$JM  (persistent — verified via any connection)"
  [ "$JM" = "wal" ] && ok "WAL enabled" || warn "journal_mode is $JM (expected wal)"
  # busy_timeout and foreign_keys shown for information only, with
  # honest labeling — a fresh CLI connection cannot verify what the
  # API's own connection sees. The API sets both explicitly per
  # request via _connect().
  BT=$(sqlite3 -readonly "$DB" "PRAGMA busy_timeout;" 2>/dev/null)
  FK=$(sqlite3 -readonly "$DB" "PRAGMA foreign_keys;" 2>/dev/null)
  info "busy_timeout=$BT  (CLI-session value; API sets its own per-connection)"
  info "foreign_keys=$FK   (CLI-session value; API sets ON per-connection)"
fi

# ── Summary ───────────────────────────────────────────────────
hdr "Summary"
printf "  passed:   %d\n" "$PASS"
printf "  warnings: %d\n" "$WARN"
printf "  failed:   %d\n" "$FAIL"
echo
if [ "$FAIL" -eq 0 ]; then
  echo "Trip lane looks healthy for the 1e388b5 acceptance surface."
  echo "If any warnings remain: FK migration is the biggest deferred item — it turns 'API-level gate' into 'schema-level guarantee'."
  exit 0
else
  echo "One or more probes failed. Copy this output back and I'll triage."
  exit 1
fi
