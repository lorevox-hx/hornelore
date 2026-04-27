#!/usr/bin/env bash
# scripts/start_all_photos_dev.sh — Hornelore 1.0
#
# Wrapper around scripts/start_all.sh that explicitly enables the photo
# intake/elicit backend by setting HORNELORE_PHOTO_ENABLED=1 in the env
# inherited by uvicorn.
#
# WHY THIS IS A SEPARATE SCRIPT (per ChatGPT 2026-04-26):
#   The default parent stack should NOT auto-enable photo routes until
#   the intake + Life Map anchor UI is stable. Operators who want to
#   work on photos use this wrapper explicitly. start_all.sh stays
#   photos-off by default.
#
# USAGE:
#   bash scripts/start_all_photos_dev.sh
#
# OR (if the env var is already exported in your shell):
#   bash scripts/start_all.sh
#
# This script just sets the flag, then delegates to start_all.sh —
# no other behavior change.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Force-enable the photo router. Backend reads this from os.environ,
# so it must be exported BEFORE the uvicorn child process is spawned.
export HORNELORE_PHOTO_ENABLED=1

printf '[photos-dev] HORNELORE_PHOTO_ENABLED=1 set.\n'
printf '[photos-dev] Photo routes /api/photos/* will respond instead of 404.\n'
printf '[photos-dev] Operator launchers: 📷 Photo Intake, 🖼 Photo Timeline\n'
printf '[photos-dev] Delegating to scripts/start_all.sh...\n\n'

exec bash "$ROOT_DIR/scripts/start_all.sh" "$@"
