"""Test package marker + module-namespace alias.

Without this file, ``python -m unittest discover -s tests -t .`` fails with
"Start directory is not importable" — the canonical full-suite command did not
run at all, which is a large part of why the repo had no trustworthy all-green
signal. Module-style invocation (``python -m unittest tests.test_x``) worked
via implicit namespace packages, which masked the breakage.

2026-07-15 — DUAL-MODULE ALIAS (fixes ~191 "no such table: trips" errors
in full-discover only):

Some tests (``tests/boris_quality/_helpers.py``) put the REPO ROOT on
``sys.path``. Others (the standard sandbox setup) put ``server/code`` on
``sys.path``. Both are valid, but together they make it possible to load
the SAME source file as TWO SEPARATE module instances::

    api.db                          # loaded via `from api import db`
    server.code.api.db              # loaded via `from server.code.api import db`

Each instance has its own module-level ``DB_PATH``. So when a trip test
does:

    from api import db as _db
    _db.DB_PATH = tempfile
    _db.init_db()          # migrates the tempfile
    trip_repository.trip_create(...)  # goes THROUGH server.code.api.db
                                      # which still points at the default
                                      # data/db/lorevox.sqlite3 → "no such
                                      # table: trips"

The fix is a meta_path finder that redirects any ``server.code.api.*``
import to the already-loaded ``api.*`` module (or triggers the ``api.*``
load first). Both paths resolve to the SAME module object → one
``DB_PATH`` to mutate, no split-brain state.

This only affects the test process — production runs from the launcher
under a single canonical import path.
"""

import sys as _sys


class _ApiNamespaceAliasFinder:
    """Meta_path finder that folds ``server.code.api.*`` onto ``api.*``.

    Installed AT THE TOP of ``sys.meta_path`` so it runs before Python's
    normal file-based finders. When a caller asks for ``server.code.api
    .services.X``, this finder imports ``api.services.X`` (triggering a
    single module load if not yet loaded), aliases it under both names in
    ``sys.modules``, and returns None so the standard machinery finds
    the alias on its next pass.

    Non-goal: hide real ImportErrors. If ``api.services.X`` genuinely
    doesn't exist, we let the exception propagate.
    """

    _PREFIX = "server.code.api"

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self._PREFIX and not fullname.startswith(
                self._PREFIX + "."):
            return None
        aliased_name = "api" + fullname[len(self._PREFIX):]
        # Already loaded under the api.* name? Just alias it.
        if aliased_name in _sys.modules:
            _sys.modules[fullname] = _sys.modules[aliased_name]
            return None
        # Load api.* now (may raise; propagate). __import__ handles the
        # full submodule chain when fromlist is non-empty.
        try:
            __import__(aliased_name, fromlist=["*"])
        except Exception:
            return None  # let the normal import machinery raise
        # After a successful load api.* is in sys.modules. Alias it.
        if aliased_name in _sys.modules:
            _sys.modules[fullname] = _sys.modules[aliased_name]
        return None


# Install exactly once. Re-installing on module re-execution would be a
# no-op but the guard keeps sys.meta_path clean.
_finder_marker = "__hornelore_api_namespace_alias__"
if not any(getattr(f, _finder_marker, False) for f in _sys.meta_path):
    _finder = _ApiNamespaceAliasFinder()
    setattr(_finder, _finder_marker, True)
    _sys.meta_path.insert(0, _finder)
