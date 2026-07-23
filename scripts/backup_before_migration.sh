#!/usr/bin/env bash
# backup_before_migration.sh
# --------------------------------------------------------------
# Portable pre-migration backup helper. Same script works on
# MAG-Chris (WSL2 Ubuntu, DB on /mnt/c/hornelore_data/…) and on
# the laptop (native Linux, DB wherever .env points).
#
# Reads DB_PATH from the repo-root .env so paths never need to be
# edited by hand. Uses SQLite's .backup online API so the backup
# is a single self-contained .sqlite3 file — no WAL/SHM sidecar
# to worry about — and works whether the stack is up or down.
#
# Usage:
#   ./scripts/backup_before_migration.sh
#   ./scripts/backup_before_migration.sh --tag pre_0034
#
# On success prints the path of the backup file it created + the
# result of PRAGMA integrity_check.
# --------------------------------------------------------------
set -e

# Optional --tag arg for a custom filename suffix; default is
# a timestamp only. Handy when doing 0034 → 0035 → next thing.
TAG=""
if [ "${1:-}" = "--tag" ] && [ -n "${2:-}" ]; then
  TAG="_${2}"
fi

# Walk up to the repo root by looking for .env
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  echo "ERROR: .env not found at $(pwd). Run from the repo checkout." >&2
  exit 1
fi

# Resolve the DB path the SAME way api/db.py does:
#   DATA_DIR = os.getenv("DATA_DIR", "data")
#   DB_DIR   = DATA_DIR / "db"
#   DB_NAME  = os.getenv("DB_NAME", "lorevox.sqlite3")
#   DB_PATH  = DB_DIR / DB_NAME
#
# .env may have DB_PATH explicitly (override), DATA_DIR + DB_NAME, or
# just DATA_DIR (with the compiled DB_NAME default). Walk the same
# precedence so we always land on the actual live DB.
DB_PATH=$(grep '^DB_PATH=' .env | head -1 | cut -d= -f2- | tr -d '[:space:]')
if [ -z "$DB_PATH" ]; then
  DATA_DIR=$(grep '^DATA_DIR=' .env | head -1 | cut -d= -f2- | tr -d '[:space:]')
  if [ -z "$DATA_DIR" ]; then
    echo "ERROR: neither DB_PATH= nor DATA_DIR= found in .env" >&2
    exit 1
  fi
  DB_NAME=$(grep '^DB_NAME=' .env | head -1 | cut -d= -f2- | tr -d '[:space:]')
  DB_NAME=${DB_NAME:-lorevox.sqlite3}
  DB_PATH="$DATA_DIR/db/$DB_NAME"
fi
if [ ! -f "$DB_PATH" ]; then
  echo "ERROR: resolved DB_PATH $DB_PATH does not point to an existing file" >&2
  echo "       (constructed from .env DATA_DIR + DB_NAME per api/db.py)" >&2
  exit 1
fi

BACKUP_DIR=$(dirname "$DB_PATH")
STAMP=$(date +%Y%m%d_%H%M%S)
BACKUP="$BACKUP_DIR/backup${TAG}_${STAMP}.sqlite3"

echo "→ backing up  $DB_PATH"
echo "        to    $BACKUP"

# SQLite's online backup — safe while the stack is running,
# produces a single consistent .sqlite3 file. If the stack is
# actively writing, .backup pages iteratively until it wins a
# consistent snapshot; failure exits non-zero.
sqlite3 "$DB_PATH" ".backup '$BACKUP'"

# Verify integrity of the backup
RESULT=$(sqlite3 "$BACKUP" "PRAGMA integrity_check;")
if [ "$RESULT" != "ok" ]; then
  echo "ERROR: backup integrity check failed:" >&2
  echo "$RESULT" >&2
  echo "Do NOT proceed with the migration." >&2
  exit 1
fi

# Report file size + confirmation
SIZE=$(du -h "$BACKUP" | cut -f1)
echo "✔ backup landed"
echo "  path: $BACKUP"
echo "  size: $SIZE"
echo "  integrity_check: ok"
echo
echo "To restore later:"
echo "  # (stop the stack first)"
echo "  cp \"$BACKUP\" \"$DB_PATH\""
echo "  rm -f \"$DB_PATH-wal\" \"$DB_PATH-shm\""
echo "  # (restart the stack)"
