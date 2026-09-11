#!/usr/bin/env bash
# Hornelore — serve the API alone against a CLEAN ROOT (acceptance / cutover).
#
#   bash launchers/hornelore_run_clean_root.sh /mnt/c/hornelore_clean_kent
#   bash launchers/hornelore_run_clean_root.sh /mnt/c/hornelore_clean_kent --reuse
#   bash launchers/hornelore_run_clean_root.sh /mnt/c/hornelore_clean_kent --port 8010
#
# WO-LOREVOX-PORTABLE-NARRATOR-01, added 2026-09-11 after the Phase 5a live
# acceptance walk. Phase 6 restores each real narrator into its own clean root,
# on both machines, several times over. Until now that was a hand-typed
# `DATA_DIR=... PORT=8000 python -m uvicorn ...` — one typo away from serving,
# or restoring into, the real installation. This launcher makes the clean root
# explicit and refuses the dangerous cases:
#
#   * the root must be absolute;
#   * the root must not be the installation's DATA_DIR (from .env), nor inside it;
#   * a root that already holds a database is refused unless --reuse is passed,
#     so a "clean" root is actually clean;
#   * the port must be free (stop the stack first; both want 8000, because the
#     UI hard-wires localhost:8000 — see ui/js/api.js:7).
#
# What it sets: DATA_DIR=<root>; the package output and staging directories as
# SIBLINGS named after the root (<root>.packages, <root>.staging) so a clean
# root never shares artifacts with the real installation; the portable
# narrator flag on; TTS off. main.py loads .env with override=False, so these
# shell values win over .env. The model loads lazily and is never touched
# unless someone chats.
#
# It does NOT replace scripts/start_all.sh. Chris starts and stops the normal
# stack himself; this is the acceptance/cutover path only.
set -euo pipefail

REPO_DIR=/mnt/c/Users/chris/hornelore

usage() {
  printf 'usage: bash launchers/hornelore_run_clean_root.sh /abs/clean/root [--reuse] [--port N]\n' >&2
  exit 2
}

ROOT="${1:-}"
[[ -n "$ROOT" ]] || usage
shift
REUSE=0
PORT=8000
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reuse) REUSE=1 ;;
    --port) [[ -n "${2:-}" ]] || usage; PORT="$2"; shift ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; usage ;;
  esac
  shift
done

case "$ROOT" in
  /*) ;;
  *) printf 'REFUSED: the clean root must be an absolute path (got %s)\n' "$ROOT" >&2; exit 3 ;;
esac

# The installation's own root, as the server would resolve it (last DATA_DIR= wins,
# the launcher default if .env has none).
REAL="$(grep -E '^DATA_DIR=' "$REPO_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
REAL="${REAL:-/mnt/c/hornelore_data}"
REAL_R="$(readlink -f "$REAL" 2>/dev/null || printf '%s' "$REAL")"
ROOT_R="$(readlink -f "$ROOT" 2>/dev/null || printf '%s' "$ROOT")"

if [[ "$ROOT_R" == "$REAL_R" ]]; then
  printf 'REFUSED: %s is the installation DATA_DIR (%s). A clean root is never the real one.\n' "$ROOT" "$REAL" >&2
  exit 3
fi
case "$ROOT_R/" in
  "$REAL_R"/*) printf 'REFUSED: %s is inside the installation DATA_DIR (%s).\n' "$ROOT" "$REAL" >&2; exit 3 ;;
esac
if [[ "$ROOT_R" == "/" || "$ROOT_R" == "/mnt" || "$ROOT_R" == "/mnt/c" ]]; then
  printf 'REFUSED: %s is not a root anyone means.\n' "$ROOT" >&2
  exit 3
fi

if [[ -e "$ROOT/db" && "$REUSE" -eq 0 ]]; then
  printf 'REFUSED: %s already holds a database. Pass --reuse to serve it as it is.\n' "$ROOT" >&2
  exit 4
fi

if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -qE "[:.]${PORT}[[:space:]]"; then
  printf 'REFUSED: port %s is in use. Stop the stack first (both want the port the UI hard-wires).\n' "$PORT" >&2
  exit 5
fi

mkdir -p "$ROOT"
OUT_DIR="${ROOT%/}.packages"
STAGING_DIR="${ROOT%/}.staging"

printf '[clean-root] DATA_DIR=%s\n' "$ROOT"
printf '[clean-root] installation DATA_DIR=%s (untouched)\n' "$REAL"
printf '[clean-root] packages=%s staging=%s\n' "$OUT_DIR" "$STAGING_DIR"
printf '[clean-root] PORT=%s portable_narrator=1 TTS=0 reuse=%s\n' "$PORT" "$REUSE"

# shellcheck disable=SC1091
source "$REPO_DIR/.venv-gpu/bin/activate"
cd "$REPO_DIR/server"
exec env \
  DATA_DIR="$ROOT" \
  HORNELORE_PACKAGE_OUT_DIR="$OUT_DIR" \
  HORNELORE_PACKAGE_STAGING_DIR="$STAGING_DIR" \
  HORNELORE_OPERATOR_PORTABLE_NARRATOR=1 \
  USE_TTS=0 \
  HOST=127.0.0.1 \
  PORT="$PORT" \
  python -m uvicorn code.api.main:app --host 127.0.0.1 --port "$PORT"
