"""Durable Operator overrides for the Lori intervention registry.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section F.
Schema: migration `0053_lori_guard_authority_overrides.sql`.

CONVENTION, NOT PREFERENCE. Every function takes an open
`sqlite3.Connection` and this module does not import `db.py`. `db.py`
imports service modules for its own accessors, so importing it back
would close a cycle that surfaces as an ImportError at boot — the same
reasoning `profile_seed` records for itself.

WHAT MAKES A WRITE CORRECT HERE

  atomic      One operator action is one transaction and ONE revision.
              `All Switchable Off` moves 37 rows and the revision once.
              Thirty-seven sequential writes would produce 37 revisions
              and let a narrator turn start on a half-applied mixture no
              operator ever chose.

  guarded     Only SWITCHABLE authorities may be written. PROTECTED
              entries are refused here as well as at the API, because
              persisted state outlives the code that wrote it.

  reversible  Reset DELETES the row. Writing today's default in would
              freeze it into this installation and silently detach the
              authority from the registry — change the canonical default
              in code afterwards and this deployment keeps the old one,
              with nothing on screen to explain why.

  ordered     A write carries the revision it was based on. A mismatch
              is a conflict, never a silent overwrite of newer state.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Mapping, Optional, Tuple

from . import lori_guard_registry as registry


class GuardStoreError(RuntimeError):
    """Base for refusals this module raises deliberately."""


class StaleRevisionError(GuardStoreError):
    """The caller based its change on a revision that is no longer current.

    Not multi-operator architecture — protection against a stale panel
    in a second browser tab overwriting a newer configuration without
    anyone noticing.
    """

    def __init__(self, expected: int, actual: int):
        super().__init__(
            f"configuration changed underneath this request "
            f"(expected revision {expected}, current {actual})")
        self.expected = expected
        self.actual = actual


class NotSwitchableError(GuardStoreError):
    """An attempt to override an authority the operator may not change."""

    def __init__(self, authority_id: int, reason: str):
        super().__init__(
            f"authority {authority_id} cannot be overridden: {reason}")
        self.authority_id = authority_id


_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS lori_guard_authority_override (
        authority_id INTEGER PRIMARY KEY,
        enabled      INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        updated_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS lori_guard_control_state (
        id         INTEGER PRIMARY KEY CHECK (id = 1),
        revision   INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
        updated_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "INSERT OR IGNORE INTO lori_guard_control_state (id, revision) VALUES (1, 0);",
)


def ensure_schema(con: sqlite3.Connection) -> None:
    """Idempotent mirror of migration 0053.

    The migration is the canonical source; this exists so a test can
    build a database without running the whole boot path, in the same
    spirit as the legacy `CREATE TABLE IF NOT EXISTS` blocks in `db.py`.
    """
    for statement in _SCHEMA:
        con.execute(statement)
    con.commit()


# ── Reads ─────────────────────────────────────────────────────────────

def read_revision(con: sqlite3.Connection) -> int:
    row = con.execute(
        "SELECT revision FROM lori_guard_control_state WHERE id = 1"
    ).fetchone()
    return int(row[0]) if row else 0


def read_overrides(con: sqlite3.Connection) -> Dict[int, bool]:
    """Only deliberately overridden authorities appear.

    Unknown ids are dropped rather than raised on: registry ids are
    permanent and reserved, so a row for a retired authority is possible
    and must never be able to fail a narrator's turn.
    """
    known = {item.id for item in registry.REGISTRY}
    out: Dict[int, bool] = {}
    for authority_id, enabled in con.execute(
            "SELECT authority_id, enabled FROM lori_guard_authority_override"):
        if int(authority_id) in known:
            out[int(authority_id)] = bool(enabled)
    return out


def read_state(con: sqlite3.Connection) -> Tuple[Dict[int, bool], int]:
    """Overrides and revision read together.

    One call, so a snapshot cannot be built from overrides at revision N
    and a revision number from N+1.
    """
    return read_overrides(con), read_revision(con)


# ── Writes ────────────────────────────────────────────────────────────

def _assert_writable(authority_id: int) -> None:
    item = registry.by_id(authority_id)
    if item is None:
        raise NotSwitchableError(authority_id, "unknown authority id")
    if item.policy == registry.POLICY_PROTECTED:
        raise NotSwitchableError(
            authority_id,
            f"PROTECTED — {item.policy_reason or 'safety or integrity'}")
    if item.policy == registry.POLICY_PENDING_SEAM:
        raise NotSwitchableError(
            authority_id,
            "PENDING_SEAM — not separable in code yet, so an override "
            "here would be recorded but not honoured")


def apply_changes(
    con: sqlite3.Connection,
    changes: Mapping[int, Optional[bool]],
    *,
    expected_revision: Optional[int] = None,
) -> int:
    """Apply a whole operator action atomically. Returns the new revision.

    `changes` maps authority id to True (select), False (exclude), or
    None (RESET — delete the override so the canonical default resumes).

    An empty `changes` still advances the revision: the operator
    performed an action, and a configuration generation that produced
    turns deserves an identity even when it changed nothing.
    """
    for authority_id in changes:
        _assert_writable(int(authority_id))

    # One transaction. `with con` commits on success and rolls back on
    # any exception, so a refused id cannot leave a partial write.
    with con:
        current = read_revision(con)
        if expected_revision is not None and int(expected_revision) != current:
            raise StaleRevisionError(int(expected_revision), current)

        for authority_id, value in changes.items():
            if value is None:
                con.execute(
                    "DELETE FROM lori_guard_authority_override "
                    "WHERE authority_id = ?", (int(authority_id),))
            else:
                con.execute(
                    "INSERT INTO lori_guard_authority_override "
                    "(authority_id, enabled, updated_at) "
                    "VALUES (?, ?, CURRENT_TIMESTAMP) "
                    "ON CONFLICT(authority_id) DO UPDATE SET "
                    "enabled = excluded.enabled, "
                    "updated_at = CURRENT_TIMESTAMP",
                    (int(authority_id), 1 if value else 0))

        new_revision = current + 1
        con.execute(
            "UPDATE lori_guard_control_state "
            "SET revision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (new_revision,))
    return new_revision


def all_switchable_off(con: sqlite3.Connection, *,
                       expected_revision: Optional[int] = None) -> int:
    """The lean baseline, in one revision.

    PROTECTED authorities are untouched and keep behaving as their
    protected state dictates — this excludes the switchable population
    and nothing else, which is precisely what the label claims.
    """
    changes = {item.id: False for item in registry.switchable()}
    return apply_changes(con, changes, expected_revision=expected_revision)


def restore_canonical_defaults(con: sqlite3.Connection, *,
                               expected_revision: Optional[int] = None) -> int:
    """Delete every override so code-side defaults resume.

    Deliberately a DELETE of all rows rather than writing each default
    back — see the reset reasoning in the module docstring.
    """
    with con:
        current = read_revision(con)
        if expected_revision is not None and int(expected_revision) != current:
            raise StaleRevisionError(int(expected_revision), current)
        con.execute("DELETE FROM lori_guard_authority_override")
        new_revision = current + 1
        con.execute(
            "UPDATE lori_guard_control_state "
            "SET revision = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (new_revision,))
    return new_revision


def reset_authority(con: sqlite3.Connection, authority_id: int, *,
                    expected_revision: Optional[int] = None) -> int:
    """Return one authority to canonical/server resolution."""
    return apply_changes(con, {int(authority_id): None},
                         expected_revision=expected_revision)
