"""Minimal SQL migration runner for hornelore.

The legacy schema lives in ``server/code/api/db.py:init_db()`` and is
already idempotent (CREATE TABLE IF NOT EXISTS). New-era schema lands
here as discrete ``NNNN_*.sql`` files so each landing is a bounded,
reversible chunk.

The runner is called from ``init_db()`` AFTER the legacy tables are
created so the legacy behavior is byte-stable for the pre-WO-PHOTO
call path. Already-applied migrations are skipped by looking them up
in ``schema_migrations``.

Contract:
  * Each file is applied inside its own transaction.
  * Files are applied in lexical order (zero-padded NNNN prefix).
  * Failure inside a migration leaves ``schema_migrations`` without
    the entry for that file, so the next boot retries.
  * Migration bodies themselves may use BEGIN/COMMIT to keep the same
    file portable to a ``sqlite3`` CLI; the runner uses ``executescript``
    which accepts nested transaction control statements gracefully.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _ensure_tracking_table(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    con.commit()


def _applied_filenames(con: sqlite3.Connection) -> set[str]:
    cur = con.execute("SELECT filename FROM schema_migrations;")
    return {row[0] for row in cur.fetchall()}


def _iter_migration_files(base_dir: Path) -> List[Path]:
    if not base_dir.is_dir():
        return []
    return sorted(p for p in base_dir.iterdir() if p.is_file() and p.suffix == ".sql")


def run_pending_migrations(
    con: sqlite3.Connection,
    migrations_dir: Path | None = None,
) -> list[str]:
    """Apply any not-yet-applied migrations against ``con``.

    Returns the list of filenames applied during this call.
    """

    base_dir = migrations_dir or _MIGRATIONS_DIR
    _ensure_tracking_table(con)
    already = _applied_filenames(con)

    applied: list[str] = []
    for path in _iter_migration_files(base_dir):
        if path.name in already:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            con.executescript(sql)
            con.execute(
                "INSERT INTO schema_migrations(filename) VALUES (?);",
                (path.name,),
            )
            con.commit()
        except Exception:
            logger.exception("Migration failed: %s", path.name)
            # Leave tracking row absent; do not swallow the error silently
            # so init_db() can fail loudly on a broken migration.
            raise
        applied.append(path.name)
        logger.info("Applied migration %s", path.name)
    return applied


__all__: Iterable[str] = ["run_pending_migrations"]
