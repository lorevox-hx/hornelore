"""Bind the production database path to a test's temporary database.

WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 1 isolation correction,
2026-08-12.

THE FAILURE THIS EXISTS TO PREVENT, exactly as it happened. Two suites
for this lane each did the obvious thing at module scope:

    os.environ["DATA_DIR"] = _TMP
    for _m in [m for m in sys.modules if m.endswith("api.db")]:
        del sys.modules[_m]
    import api.db as db

Each passed alone. Run together they produced 2 failures and 12 errors,
with repository calls reading a database that had no ``trip_days`` and no
``trip_photo_links``. Measured cause:

    A.db is B.db        -> False      TWO live api.db module objects
    A.repo is B.repo    -> True       ONE shared trip_repository

``trip_repository._connect()`` resolves ``from .. import db`` LATE, at
call time, so it binds to whatever ``sys.modules["api.db"]`` holds when
it runs -- which, after the second suite's delete-and-reimport, is the
SECOND module object. The first suite then set ``DB_PATH`` on a module
object nothing else was using, created its schema in one file, and
watched the repository read another.

Deleting a module from ``sys.modules`` does not unload it. It makes the
next import build a NEW object while every already-imported module keeps
the old one. A late import is what turns that into a silent split.

The rule this module enforces: never remove ``api.db`` from
``sys.modules``; bind ``DB_PATH`` on the single live object the
repository will actually resolve; restore it afterwards; and PROVE the
binding by asking the connection which file it opened, rather than
trusting that it worked.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


def live_db_module() -> Any:
    """The one ``api.db`` object the repository will resolve.

    Imported, never re-imported. If something has already forked it this
    returns whatever is live now, which is the object that matters.
    """
    import api.db as _live
    assert _live is sys.modules["api.db"], (
        "api.db was forked: the imported object is not the one in "
        "sys.modules. Something deleted it from sys.modules and "
        "re-imported it; late-importing callers will not see your "
        "DB_PATH.")
    return _live


def connected_path(repo: Any) -> str:
    """The file the repository's own connection actually opens."""
    con = repo._connect()
    try:
        # PRAGMA database_list: (seq, name, file) for each attached db.
        return str(con.execute("PRAGMA database_list").fetchall()[0][2])
    finally:
        con.close()


def bind_db(testcase: Any, repo: Any, path: str) -> None:
    """Point every production connection path at ``path`` for this test.

    Registers an ``addCleanup`` restoring the previous ``DB_PATH``, so a
    suite cannot leak its temporary database into whatever runs next --
    which is the other half of the same isolation failure.

    Asserts, not assumes: the repository is asked which file it opened
    and the answer must be this test's database. A test whose binding
    silently failed would otherwise pass or fail for reasons unrelated
    to what it claims to check.
    """
    live = live_db_module()
    previous = live.DB_PATH
    live.DB_PATH = Path(path)
    testcase.addCleanup(setattr, live, "DB_PATH", previous)

    got = connected_path(repo)
    if os.path.abspath(got) != os.path.abspath(path):
        raise AssertionError(
            "database binding failed: the repository opened %r but this "
            "test uses %r. api.db is probably forked in sys.modules."
            % (got, path))


def temp_data_dir(tmp: str) -> None:
    """Set DATA_DIR only if nothing has set it.

    ``api.db`` reads DATA_DIR once at import to compute DB_DIR/DB_PATH
    and creates that directory. Overwriting it after another suite has
    imported api.db achieves nothing except making the two suites
    disagree about where 'the database' is; every test binds DB_PATH
    explicitly anyway.
    """
    os.environ.setdefault("DATA_DIR", tmp)
