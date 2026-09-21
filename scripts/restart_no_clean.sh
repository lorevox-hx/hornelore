#!/usr/bin/env bash
# Restart Hornelore WITHOUT clearing browser state.
#
#   bash scripts/restart_no_clean.sh
#
# WHY THIS EXISTS
# ---------------
# `stop_all.sh` sets a clean-start flag by default, and the next startup
# uses it to clear every Hornelore-scoped localStorage, sessionStorage
# and cache entry in the browser. That is the right default after a
# schema change or a confusing session — it guarantees the page is not
# reading something stale.
#
# It is the wrong default in the middle of a walkthrough. Clearing
# browser state loses the open narrator, the current era, any unsent
# draft in the questionnaire, and the scroll position in a long
# transcript. On a restart you are doing to pick up new SERVER code,
# none of that needed to go.
#
# WHAT IT DOES NOT DO
# -------------------
# It does not touch the database. It does not run a migration, a
# backfill, or any data script. Server-side migrations still apply on
# startup exactly as they always do — `init_db()` runs pending ones on
# nearly every DB call, and that is unchanged by anything here.
#
# THE `rm -f` IS NOT REDUNDANT
# -----------------------------
# `--no-clean` stops THIS shutdown writing the flag. It does nothing
# about a flag an EARLIER shutdown already left behind — and the
# ordinary `stop_all.sh` writes one every time. Without the removal, a
# normal stop last night would still clear the browser on this restart,
# which is the exact surprise this script exists to prevent.
#
# `common.sh:235` consumes and deletes the flag at startup, so removing
# it here is the same operation done earlier and deliberately.

set -euo pipefail

ROOT="/mnt/c/Users/chris/hornelore"
cd "$ROOT"

echo "=== Stopping Hornelore (browser state preserved) ==="
bash scripts/stop_all.sh --no-clean

# See "THE rm -f IS NOT REDUNDANT" above. Deletes a flag file only;
# no browser data is touched by this, or by anything in this script.
if [[ -f .runtime/reset_on_start ]]; then
  echo "Clearing a clean-start flag left by an earlier shutdown."
  rm -f .runtime/reset_on_start
fi

echo
echo "=== Restarting Hornelore ==="
bash scripts/start_all.sh
