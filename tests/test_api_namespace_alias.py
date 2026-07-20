"""Lock the tests/__init__.py meta_path finder that folds
``server.code.api.*`` onto ``api.*``.

Regression class: full-discover produced ~191 spurious "no such table:
trips" errors because trip tests set ``api.db.DB_PATH`` to a tempfile,
but some code path in the same process loaded a SECOND
``server.code.api.db`` module (via a helper that put REPO_ROOT on
sys.path — e.g. tests/boris_quality/_helpers.py). That second instance
had its own module-level ``DB_PATH`` still pointing at the default DB,
so ``trip_repository.trip_create`` opened that DB, which had no trips
table.

The alias makes both import paths resolve to the SAME module object.
Anything that mutates ``api.db.DB_PATH`` is now visible through
``server.code.api.db.DB_PATH`` too, and vice versa.

These tests deliberately do NOT stub sqlite3 — the reproducer relies on
real module identity semantics, which are trivial with sqlite3 in the
stdlib.
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


class ApiNamespaceAliasTest(unittest.TestCase):
    """The `server.code.api.*` prefix must fold onto `api.*`."""

    def setUp(self):
        # Ensure REPO_ROOT is on sys.path so the second import path is
        # RESOLVABLE — the alias must intercept it BEFORE it can create
        # a second module instance.
        self._path_added = False
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
            self._path_added = True

    def tearDown(self):
        if self._path_added:
            try:
                sys.path.remove(str(_REPO_ROOT))
            except ValueError:
                pass

    def test_db_module_is_shared_across_both_import_paths(self):
        from api import db as db_a
        from server.code.api import db as db_b
        self.assertIs(
            db_a, db_b,
            "api.db and server.code.api.db must be the SAME module "
            "instance — otherwise DB_PATH mutations don't cross-visit")

    def test_services_trip_repository_is_shared_across_both_paths(self):
        from api.services import trip_repository as tr_a
        from server.code.api.services import trip_repository as tr_b
        self.assertIs(tr_a, tr_b)

    def test_routers_chat_ws_is_shared_across_both_paths(self):
        # chat_ws has a big import surface; if any child import splits,
        # this catches it.
        try:
            from api.routers import chat_ws as ws_a
        except ImportError as exc:
            self.skipTest("chat_ws deps unavailable: {}".format(exc))
        from server.code.api.routers import chat_ws as ws_b
        self.assertIs(ws_a, ws_b)

    def test_db_path_mutation_is_visible_across_both_paths(self):
        """The load-bearing property: mutating DB_PATH via one path
        must be visible via the other. Without the alias this fails
        and produces the trips-table pollution class."""
        from api import db as db_a
        from server.code.api import db as db_b
        original = db_a.DB_PATH
        try:
            marker = Path("/tmp/hornelore-alias-test-canary.sqlite3")
            db_a.DB_PATH = marker
            self.assertEqual(db_b.DB_PATH, marker)
            # And the reverse:
            marker2 = Path("/tmp/hornelore-alias-test-canary-2.sqlite3")
            db_b.DB_PATH = marker2
            self.assertEqual(db_a.DB_PATH, marker2)
        finally:
            db_a.DB_PATH = original

    def test_trip_repository_reads_the_patched_db_path(self):
        """The end-to-end reproducer of the original pollution: with
        the alias in place, patching ``api.db.DB_PATH`` and then
        calling ``server.code.api.services.trip_repository.trip_create``
        must succeed against the tempfile — because both paths agree
        on which module holds DB_PATH."""
        from api import db as _db
        # Load trip_repository via the SECOND path — this is what
        # historically split.
        from server.code.api.services import trip_repository as _tr

        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        tmp_path = Path(tmp.name)
        original = _db.DB_PATH
        try:
            _db.DB_PATH = tmp_path
            _db.init_db()
            trip_id = _tr.trip_create(
                "p-alias-canary", "Alias canary trip")
            self.assertTrue(bool(trip_id))
        finally:
            _db.DB_PATH = original
            try:
                tmp_path.unlink()
            except OSError:
                pass

    def test_alias_finder_installed_once(self):
        """The meta_path finder must be installed exactly once —
        double-installs would slow every import and duplicate
        sys.modules writes."""
        marker = "__hornelore_api_namespace_alias__"
        count = sum(1 for f in sys.meta_path
                    if getattr(f, marker, False))
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
