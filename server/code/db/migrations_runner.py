"""Minimal SQL migration runner for hornelore.

The legacy schema lives in ``server/code/api/db.py:init_db()`` and is
already idempotent (CREATE TABLE IF NOT EXISTS). New-era schema lands
here as discrete ``NNNN_*.sql`` files so each landing is a bounded,
reversible chunk.

The runner is called from ``init_db()`` AFTER the legacy tables are
created so the legacy behavior is byte-stable for the pre-WO-PHOTO
call path. Already-applied migrations are skipped by looking them up
in ``schema_migrations``.

Contract (C-4D, 2026-09-25 — pinned by tests/test_migrations_runner.py):

  * Files are applied in lexical order (zero-padded NNNN prefix).

  * RUNNER-MANAGED files — no transaction control of their own — are
    applied inside ONE transaction the runner opens (``BEGIN IMMEDIATE``),
    together with their ``schema_migrations`` row. A failure anywhere,
    including the tracking insert, rolls the whole file back: nothing is
    half-applied, nothing is recorded, and the next boot retries cleanly.
    (Before C-4D the runner opened no transaction: ``executescript``
    autocommitted each statement, so a failure half way left a partial
    schema behind, unrecorded, and the retry then failed on it.)

  * A runner-managed file may declare, on a line of its own,

        -- migration: foreign_keys=off

    for a table rebuild whose parent is referenced by other tables. The
    runner then switches foreign keys off OUTSIDE its transaction (SQLite
    ignores the pragma inside one), runs the file, and refuses — rolling
    back — if the file created any foreign-key violation that was not
    already present. Foreign keys are restored afterwards, success or not.

  * SELF-MANAGED files carry their own ``BEGIN … COMMIT`` (historical
    files, several toggling ``PRAGMA foreign_keys``). They are immutable
    and are run as they are. On failure the runner rolls back whatever
    transaction the file left open and restores ``PRAGMA foreign_keys`` to
    its value before the file. Their tracking row is still written after
    the file's own commit — that narrow window is inherent to a file that
    commits itself, and is documented rather than hidden.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

# Statement-level transaction control. Trigger bodies (`BEGIN … END;`) do not
# match: a trigger's BEGIN carries no semicolon, and END is not listed.
_SELF_MANAGED_RX = re.compile(
    r"^\s*(BEGIN(\s+(DEFERRED|IMMEDIATE|EXCLUSIVE|TRANSACTION))?|COMMIT|ROLLBACK)\s*;",
    re.IGNORECASE | re.MULTILINE)
_FK_OFF_RX = re.compile(r"^--\s*migration:\s*foreign_keys\s*=\s*off\s*$", re.IGNORECASE | re.MULTILINE)


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


def is_self_managed(sql: str) -> bool:
    return bool(_SELF_MANAGED_RX.search(sql))


def wants_foreign_keys_off(sql: str) -> bool:
    return bool(_FK_OFF_RX.search(sql))


def _fk_violations(con: sqlite3.Connection) -> set:
    return {tuple(r) for r in con.execute("PRAGMA foreign_key_check").fetchall()}


def _rollback_if_open(con: sqlite3.Connection) -> None:
    if con.in_transaction:
        con.rollback()


def _apply_runner_managed(con: sqlite3.Connection, path: Path, sql: str) -> None:
    fk_off = wants_foreign_keys_off(sql)
    if fk_off and is_self_managed(sql):
        raise ValueError(f"{path.name}: the foreign_keys=off directive is for runner-managed files only")
    _rollback_if_open(con)          # never let a stray open transaction absorb the file
    if fk_off:
        con.execute("PRAGMA foreign_keys=OFF;")          # must be outside the transaction
    before = _fk_violations(con) if fk_off else None
    try:
        con.executescript("BEGIN IMMEDIATE;\n" + sql)   # the file runs INSIDE one transaction
        if fk_off:
            created = _fk_violations(con) - before
            if created:
                raise sqlite3.IntegrityError(
                    f"{path.name} created {len(created)} foreign-key violation(s), "
                    f"e.g. {sorted(created)[:3]!r}")
        con.execute("INSERT INTO schema_migrations(filename) VALUES (?);", (path.name,))
        con.commit()                                      # body + tracking row: one commit
    except Exception:
        _rollback_if_open(con)
        raise


def _apply_self_managed(con: sqlite3.Connection, path: Path, sql: str) -> None:
    try:
        con.executescript(sql)
        con.execute("INSERT INTO schema_migrations(filename) VALUES (?);", (path.name,))
        con.commit()
    except Exception:
        _rollback_if_open(con)
        raise


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
        fk_before = con.execute("PRAGMA foreign_keys;").fetchone()[0]
        try:
            if is_self_managed(sql):
                _apply_self_managed(con, path, sql)
            else:
                _apply_runner_managed(con, path, sql)
        except Exception:
            logger.exception("Migration failed: %s", path.name)
            # Nothing half-applied is left behind and the tracking row is
            # absent, so the next boot retries; the error is not swallowed,
            # so init_db() fails loudly on a broken migration.
            raise
        finally:
            _rollback_if_open(con)
            con.execute(f"PRAGMA foreign_keys={'ON' if fk_before else 'OFF'};")
        applied.append(path.name)
        logger.info("Applied migration %s", path.name)
    return applied


__all__: Iterable[str] = ["run_pending_migrations", "is_self_managed", "wants_foreign_keys_off"]
