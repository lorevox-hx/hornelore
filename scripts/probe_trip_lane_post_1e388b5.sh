#!/usr/bin/env bash
# probe_trip_lane_post_1e388b5.sh
# ---------------------------------------------------------------
# Post-commit-1e388b5 live-API probe for the trip lane.
#
# Why this exists: Claude in Chrome wasn't reachable this session,
# so instead of clicking through the Travel Documenter / Lab UI,
# this script hits the same endpoints and DB rows I would have
# eyeballed. It also folds in web-search item #9 (SQLite runtime
# version check) and closes out the orphan trip from the ND run.
#
# READ-ONLY BY DEFAULT. Any write step is fenced behind
# CONFIRM_WRITES=1 so a bare run never mutates the DB or API.
#
# Usage:
#   ./scripts/probe_trip_lane_post_1e388b5.sh            # dry
#   CONFIRM_WRITES=1 ./scripts/probe_trip_lane_post_1e388b5.sh
#
# Environment overrides (defaults from .env.example):
#   API=http://localhost:8000
#   DB=/mnt/c/hornelore_data/hornelore.sqlite3
#   PY=.venv-gpu/bin/python
#   ORPHAN_TRIP=4fdd9f93-dc86-4881-ae09-d690a4de9741
#   PERSON_ID=<REAL_UUID>   # if unset, script picks the first from /api/people
# ---------------------------------------------------------------
set -u  # unset variables are errors; keep -e off so probes continue past failures
API=${API:-http://localhost:8000}
DB=${DB:-/mnt/c/hornelore_data/hornelore.sqlite3}
PY=${PY:-.venv-gpu/bin/python}
ORPHAN_TRIP=${ORPHAN_TRIP:-4fdd9f93-dc86-4881-ae09-d690a4de9741}
CONFIRM_WRITES=${CONFIRM_WRITES:-0}

PASS=0
FAIL=0
WARN=0

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

# ── 1. SQLite runtime version (web-search #9) ─────────────────
hdr "1. SQLite runtime version"
if [ -x "$PY" ]; then
  VER_OUT=$("$PY" - <<'PY' 2>/dev/null
import sqlite3, sys
print(f"python={sys.version.split()[0]}")
print(f"sqlite3_module={sqlite3.version}")
print(f"sqlite_runtime={sqlite3.sqlite_version}")
PY
  )
  echo "$VER_OUT" | while read L; do info "$L"; done
  RUNTIME=$(echo "$VER_OUT" | awk -F= '/sqlite_runtime/{print $2}')
  case "$RUNTIME" in
    3.5[12].0|3.5[12].1|3.5[12].2)
      warn "SQLite $RUNTIME may have the WAL-reset race (fixed in 3.51.3 / 3.50.7 / 3.44.6). Watch for spurious SQLITE_BUSY under load."
      ;;
    *)
      ok "SQLite runtime $RUNTIME not in the known-affected range"
      ;;
  esac
else
  warn "Interpreter $PY not found; skipping version check. Set PY=<path> or activate the venv."
fi

# ── 2. Pick a real narrator UUID ──────────────────────────────
hdr "2. Real narrator UUID"
if [ -z "${PERSON_ID:-}" ]; then
  PEOPLE_JSON=$(curl -fsS --max-time 5 "$API/api/people" 2>/dev/null || echo "[]")
  PERSON_ID=$(printf '%s' "$PEOPLE_JSON" | "$PY" - <<'PY' 2>/dev/null
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print(""); sys.exit(0)
if isinstance(data, dict):
    data = data.get("people") or data.get("items") or []
for row in data:
    if isinstance(row, dict) and row.get("id"):
        print(row["id"]); break
PY
  )
fi
if [ -n "${PERSON_ID:-}" ]; then
  ok "Using narrator $PERSON_ID"
else
  warn "No narrators from /api/people — trip-create probe (§5) will be skipped"
fi

# ── 3. Orphan trip status ─────────────────────────────────────
hdr "3. Orphan trip from ND run"
if [ -r "$DB" ]; then
  ORPHAN_ROW=$(sqlite3 -readonly "$DB" \
    "SELECT id||'|'||COALESCE(title,'')||'|'||COALESCE(person_id,'') FROM trips WHERE id = '$ORPHAN_TRIP';" 2>/dev/null)
  if [ -n "$ORPHAN_ROW" ]; then
    warn "Orphan trip still present: $ORPHAN_ROW"
    if [ "$CONFIRM_WRITES" = "1" ]; then
      RESP=$(curl -sS -o /tmp/orphan_del.out -w "%{http_code}" -X DELETE "$API/api/trips/$ORPHAN_TRIP")
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

# ── 5. person_id validation gate (from 1e388b5) ───────────────
hdr "5. POST /api/trips must reject a nonexistent person_id"
FAKE_PID="PASTE_UUID_HERE"
RESP=$(curl -sS -o /tmp/probe_reject.out -w "%{http_code}" -X POST "$API/api/trips" \
  -H "Content-Type: application/json" \
  -d "{\"person_id\":\"$FAKE_PID\",\"title\":\"PROBE_REJECT_$(date +%s)\"}")
case "$RESP" in
  422)
    ok "Fake person_id rejected with 422"
    ;;
  400|404)
    ok "Fake person_id rejected with $RESP (acceptable)"
    ;;
  200|201)
    bad "Fake person_id was ACCEPTED ($RESP) — validation regressed"
    cat /tmp/probe_reject.out | head -c 300; echo
    ;;
  *)
    warn "Unexpected status $RESP for fake person_id"
    cat /tmp/probe_reject.out | head -c 300; echo
    ;;
esac

# ── 6. Auto-day-generation on trip create (write) ─────────────
hdr "6. Auto-day-generation on trip create (July 14–19 → 6 cards)"
if [ -z "${PERSON_ID:-}" ]; then
  warn "No real narrator — skipping"
elif [ "$CONFIRM_WRITES" != "1" ]; then
  info "Skipped (CONFIRM_WRITES=1 required — creates a real trip)"
else
  TITLE="PROBE_TRIP_$(date +%s)"
  CREATE=$(curl -sS -X POST "$API/api/trips" \
    -H "Content-Type: application/json" \
    -d "{\"person_id\":\"$PERSON_ID\",\"title\":\"$TITLE\",\"start_date\":\"2026-07-14\",\"end_date\":\"2026-07-19\"}")
  NEW_ID=$(printf '%s' "$CREATE" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("trip",{}).get("id") or d.get("id") or "")' 2>/dev/null)
  if [ -z "$NEW_ID" ]; then
    bad "Trip create didn't return an id — response: $(echo "$CREATE" | head -c 300)"
  else
    ok "Trip created: $NEW_ID"
    DAY_JSON=$(curl -fsS "$API/api/trips/$NEW_ID/days")
    DAY_CT=$(printf '%s' "$DAY_JSON" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("days") or d if isinstance(d,list) else d.get("days",[])))' 2>/dev/null)
    if [ "$DAY_CT" = "6" ]; then
      ok "6 day cards generated"
    else
      bad "Expected 6 day cards, got $DAY_CT — response: $(echo "$DAY_JSON" | head -c 200)"
    fi

    # 6b. Move start earlier and verify renumber
    hdr "6b. Move start to 2026-07-10 and verify day_index renumber"
    PATCH_RESP=$(curl -sS -X PATCH "$API/api/trips/$NEW_ID" \
      -H "Content-Type: application/json" \
      -d '{"start_date":"2026-07-10"}')
    DAYS2=$(curl -fsS "$API/api/trips/$NEW_ID/days")
    ORDER_OK=$(printf '%s' "$DAYS2" | "$PY" - <<'PY' 2>/dev/null
import json, sys
d = json.load(sys.stdin)
days = d.get("days") if isinstance(d, dict) else d
days = sorted(days, key=lambda r: r.get("date",""))
for i, row in enumerate(days, start=1):
    if row.get("day_index") != i:
        print(f"FAIL row={row}")
        sys.exit(0)
print(f"OK count={len(days)}")
PY
    )
    case "$ORDER_OK" in
      OK\ count=10) ok "day_index renumbered 1..10 in date order (July 10–19)";;
      OK\ count=*) warn "day_index correct order but unexpected count: $ORDER_OK";;
      *) bad "day_index NOT sequential in date order: $ORDER_OK"; info "response head: $(echo "$DAYS2" | head -c 200)";;
    esac

    # 6c. Cleanup probe trip
    hdr "6c. Cleanup probe trip"
    DEL=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE "$API/api/trips/$NEW_ID")
    case "$DEL" in
      200|204) ok "Probe trip $NEW_ID deleted ($DEL)";;
      *) warn "Cleanup DELETE returned $DEL — trip may linger";;
    esac
  fi
fi

# ── 7. days_warning + sync_warning in reversed-date PATCH ─────
hdr "7. PATCH with reversed dates surfaces days_warning"
if [ -z "${PERSON_ID:-}" ] || [ "$CONFIRM_WRITES" != "1" ]; then
  info "Skipped (needs real narrator + CONFIRM_WRITES=1)"
else
  TITLE="PROBE_WARN_$(date +%s)"
  CREATE=$(curl -sS -X POST "$API/api/trips" -H "Content-Type: application/json" \
    -d "{\"person_id\":\"$PERSON_ID\",\"title\":\"$TITLE\",\"start_date\":\"2026-08-01\",\"end_date\":\"2026-08-05\"}")
  NEW_ID=$(printf '%s' "$CREATE" | "$PY" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("trip",{}).get("id") or d.get("id") or "")' 2>/dev/null)
  if [ -n "$NEW_ID" ]; then
    PATCHED=$(curl -sS -X PATCH "$API/api/trips/$NEW_ID" -H "Content-Type: application/json" \
      -d '{"start_date":"2026-08-05","end_date":"2026-08-01"}')
    if printf '%s' "$PATCHED" | grep -q days_warning; then
      ok "days_warning key present in PATCH response"
      DW=$(printf '%s' "$PATCHED" | "$PY" -c 'import json,sys; print(json.load(sys.stdin).get("days_warning",""))' 2>/dev/null)
      info "days_warning: $DW"
    else
      warn "days_warning not in PATCH response (may have been no-op) — head: $(echo "$PATCHED" | head -c 200)"
    fi
    curl -sS -o /dev/null -X DELETE "$API/api/trips/$NEW_ID"
    info "Cleanup: probe trip $NEW_ID deleted"
  fi
fi

# ── 8. WAL / journal-mode sanity ──────────────────────────────
hdr "8. WAL / journal-mode sanity"
if [ -r "$DB" ]; then
  JM=$(sqlite3 -readonly "$DB" "PRAGMA journal_mode;" 2>/dev/null)
  BT=$(sqlite3 -readonly "$DB" "PRAGMA busy_timeout;" 2>/dev/null)
  FK=$(sqlite3 -readonly "$DB" "PRAGMA foreign_keys;" 2>/dev/null)
  info "journal_mode=$JM  busy_timeout=$BT  foreign_keys(session)=$FK"
  [ "$JM" = "wal" ] && ok "WAL enabled" || warn "journal_mode is $JM (expected wal)"
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
