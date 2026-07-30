"""WO-TRUTH-PIPELINE-01 Phase 2, Step 7 — the measuring instrument.

WHY THIS FILE EXISTS. scripts/archive/golfball_narrator_isolation.py
snapshots a narrator's rows before and after a turn and reports whether
anything leaked. Until 2026-07-30 its table list named seven tables that
have never existed in this schema, and misnamed an eighth
(`interview_projection`, singular). That was worse than an ordinary bug,
because of how the miss is handled: `_table_exists` returns False, the
snapshot records `None`, a `None` diffs as "unchanged", and "unchanged"
reads as ISOLATION HELD. Seven of twelve evidence columns were therefore
guaranteed passes measuring nothing — which is how the archived probe
produced the reading "speaker_zero_delta — turn did not write
anywhere" for a turn that in fact wrote a raw turn row and two archive
events.

The probe also omitted `turns`, the one table the turn is certain to
write, so the single most informative column was absent.

An inaccurate measuring instrument must not stay available to later
gates. This file is the guard: it pins the repaired list against the
schema `init_db()` actually creates, so the list cannot silently rot
again. It covers Phase 2 acceptance items 12 and 13.

WHY THE LIST IS READ FROM THE AST. The probe imports `requests` at
module scope and is a runnable script, not a library. The table groups
are module-level literal tuples, so they are read with
`ast.literal_eval` — no execution, no dependency on the HTTP stack,
and no chance of this test passing because it happened to read a
different copy of the list.
"""
from __future__ import annotations

import ast
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api import db as _db  # noqa: E402

_PROBE = _REPO_ROOT / "scripts" / "archive" / "golfball_narrator_isolation.py"

# The group prefix is the contract between this test and the probe. Any
# future table group has to use it, which is what makes
# test_no_group_escapes_this_test able to see a group that did not exist
# when this file was written.
_GROUP_PREFIX = "NARRATOR_SCOPED_TABLES_"

# The exact names Phase 1 found in the archived list that do not exist.
# Kept as a named set so a re-introduction fails loudly instead of
# quietly returning None again.
_PHANTOM_TABLES = frozenset({
    "photo_review_queue",
    "narrator_relationships",
    "memory_archive_audio",
    "memory_archive_events",
    "interview_segment_flags",
    "interview_projection",   # the singular misspelling
    "archive_events",
})


def _probe_tree() -> ast.AST:
    return ast.parse(_PROBE.read_text(encoding="utf-8"))


def _table_groups() -> dict:
    """{group_name: (table, ...)} for every module-level table tuple."""
    groups = {}
    for node in _probe_tree().body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            name = getattr(target, "id", "")
            if not name.startswith(_GROUP_PREFIX):
                continue
            groups[name] = tuple(ast.literal_eval(node.value))
    return groups


def _live_tables() -> set:
    """Every table name a fresh init_db() actually creates.

    Read from a throwaway database rather than from the live file, so
    this test states what the SCHEMA guarantees and never depends on
    what happens to be on this machine.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    path = Path(tmp.name)
    orig = _db.DB_PATH
    try:
        _db.DB_PATH = path
        _db.init_db()
        conn = sqlite3.connect(str(path))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        finally:
            conn.close()
        return {r[0] for r in rows}
    finally:
        _db.DB_PATH = orig
        try:
            path.unlink()
        except OSError:
            pass


class ProbeTableListTest(unittest.TestCase):
    """Acceptance items 12 and 13."""

    @classmethod
    def setUpClass(cls):
        cls.groups = _table_groups()
        cls.tables = {t for names in cls.groups.values() for t in names}
        cls.live = _live_tables()

    def test_the_probe_reads_as_three_named_groups(self):
        """A sanity anchor. If the tuples are renamed or turned into a
        computed value, every other test here would silently measure an
        empty list — the same class of failure the probe itself had."""
        self.assertGreaterEqual(
            len(self.groups), 3,
            "the probe's table groups could not be read as module-level "
            f"literal tuples. Found: {sorted(self.groups)}",
        )
        self.assertTrue(
            all(len(v) > 0 for v in self.groups.values()),
            f"an empty table group measures nothing: {self.groups}",
        )

    def test_the_probe_includes_turns(self):
        """Acceptance item 12.

        `turns` is the table a completed turn is certain to write. The
        archived list omitted it, so the probe could report "did not
        write anywhere" while the raw turn sat in the database.
        """
        self.assertIn(
            "turns", self.tables,
            "the isolation probe still does not look at `turns`, the one "
            "table a completed turn always writes.",
        )

    def test_every_probe_table_exists_in_the_live_schema(self):
        """Acceptance item 13.

        This is the assertion the repaired probe's own comment promises.
        A named table that does not exist is not a harmless typo here: it
        snapshots as None, diffs as unchanged, and reads as isolation
        held.
        """
        missing = sorted(t for t in self.tables if t not in self.live)
        self.assertEqual(
            missing, [],
            "the isolation probe names tables that init_db() does not "
            "create. Each one is a guaranteed false pass, because a "
            f"missing table snapshots as None and None reads as "
            f"'unchanged': {missing}",
        )

    def test_the_phantom_tables_did_not_come_back(self):
        """The specific seven, by name, plus the singular misspelling.

        test_every_probe_table_exists_in_the_live_schema would catch
        these too, but only while they stay nonexistent. If some later
        work order creates a real table called `archive_events`, that
        test would go green on a probe line that still means the wrong
        thing — the archive event count comes from the probe stage, not
        from a table of that name.
        """
        returned = sorted(self.tables & _PHANTOM_TABLES)
        self.assertEqual(
            returned, [],
            "names from the archived probe's phantom list are back in the "
            f"table groups: {returned}",
        )

    def test_the_projection_table_is_named_in_the_plural(self):
        """The archived list said `interview_projection`. The schema says
        `interview_projections`. A one-letter difference cost the whole
        projection column."""
        self.assertIn("interview_projections", self.tables)
        self.assertIn("interview_projections", self.live)

    def test_the_extraction_ledger_is_watched(self):
        """Phase 2 added a table that a turn can now legitimately write.
        A leakage probe that does not look at it would miss the only new
        write path this phase introduced."""
        self.assertIn("turn_extraction_ledger", self.tables)
        self.assertIn("turn_extraction_ledger", self.live)

    def test_no_group_escapes_this_test(self):
        """A future group added to the probe but not wired into the
        snapshot would measure nothing while looking complete.

        Both readers are checked: snapshot_narrator (the before/after
        counts) and find_text_in_any_narrator_row (the leakage search).
        """
        tree = _probe_tree()
        for fn_name in ("snapshot_narrator", "find_text_in_any_narrator_row"):
            fn = next(
                (n for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == fn_name),
                None,
            )
            self.assertIsNotNone(fn, f"{fn_name} is gone from the probe")
            referenced = {
                n.id for n in ast.walk(fn)
                if isinstance(n, ast.Name) and n.id.startswith(_GROUP_PREFIX)
            }
            unread = sorted(set(self.groups) - referenced)
            self.assertEqual(
                unread, [],
                f"{fn_name} does not read {unread}. A table group nobody "
                "reads is a column of guaranteed passes.",
            )


class MissingTableBehaviourTest(unittest.TestCase):
    """WHY a wrong name was a false pass, asserted rather than asserted
    about.

    The counting helpers must return None — not 0 — for a table that
    is not there. `_diff_snapshots` treats None as "not measured"; a 0
    would be indistinguishable from a real, correct zero, which is the
    reading that misled Gate 7 in the first place.
    """

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.path = Path(tmp.name)
        conn = sqlite3.connect(str(self.path))
        conn.execute("CREATE TABLE story_candidates (narrator_id TEXT)")
        conn.execute("CREATE TABLE turns (conv_id TEXT)")
        conn.commit()
        conn.close()
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.probe = self._load_probe()

    def tearDown(self):
        self.conn.close()
        try:
            self.path.unlink()
        except OSError:
            pass

    @staticmethod
    def _load_probe():
        """Load the probe by path, stubbing `requests` if absent.

        The probe is a script under scripts/archive/ and imports the HTTP
        client at module scope. Nothing in this test makes a request, so
        a stub is honest here.
        """
        import importlib.util
        import types as _types
        if "requests" not in sys.modules:
            _r = _types.ModuleType("requests")

            def _unavailable(*_a, **_k):
                raise AssertionError(
                    "this test must not make an HTTP request"
                )
            _r.get = _r.post = _r.patch = _r.delete = _unavailable
            _r.Session = object
            _r.RequestException = Exception
            sys.modules["requests"] = _r
        spec = importlib.util.spec_from_file_location(
            "_golfball_isolation_under_test", _PROBE,
        )
        mod = importlib.util.module_from_spec(spec)
        # Registered BEFORE execution: the probe defines a @dataclass at
        # module scope, and dataclasses resolves annotations through
        # sys.modules[cls.__module__]. A module executed outside
        # sys.modules raises AttributeError on that lookup.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod

    def test_cleanup_removes_the_disposable_people_row(self):
        """ADDED 2026-07-30. The Gate 7 Phase 2 acceptance run now creates
        a real `people` row for its disposable narrator, because
        interview_projections declares a FOREIGN KEY to people(id) and a
        correction could not otherwise be written. `people` is keyed on
        `id`, so neither of cleanup_synthetic's two loops --- one over
        narrator_id, one over person_id --- ever reaches it. A cleanup
        that left the row behind would report success while the synthetic
        narrator stayed in the operator's people list."""
        conn = sqlite3.connect(str(self.path))
        conn.execute("CREATE TABLE people (id TEXT PRIMARY KEY, "
                     "display_name TEXT NOT NULL)")
        conn.execute("INSERT INTO people (id, display_name) VALUES (?, ?)",
                     ("harness-test-alpha", "disposable"))
        conn.execute("INSERT INTO people (id, display_name) VALUES (?, ?)",
                     ("kent-real-narrator", "Kent"))
        conn.commit()
        conn.close()

        result = self.probe.cleanup_synthetic(str(self.path),
                                              "harness-test-alpha")
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(result["deleted"].get("people"), 1,
                         "cleanup did not delete the disposable people row")

        left = {r[0] for r in self.conn.execute("SELECT id FROM people")}
        self.assertNotIn("harness-test-alpha", left)
        self.assertIn("kent-real-narrator", left,
                      "cleanup reached a narrator it was never given")

    def test_cleanup_refuses_a_narrator_outside_the_harness_prefix(self):
        """The prefix guard is the only thing standing between this
        function and a live narrator's people row."""
        conn = sqlite3.connect(str(self.path))
        conn.execute("CREATE TABLE people (id TEXT PRIMARY KEY, "
                     "display_name TEXT NOT NULL)")
        conn.execute("INSERT INTO people (id, display_name) VALUES (?, ?)",
                     ("kent-real-narrator", "Kent"))
        conn.commit()
        conn.close()

        result = self.probe.cleanup_synthetic(str(self.path),
                                              "kent-real-narrator")
        self.assertFalse(result.get("ok"))
        left = {r[0] for r in self.conn.execute("SELECT id FROM people")}
        self.assertIn("kent-real-narrator", left,
                      "cleanup deleted a live narrator. The prefix guard "
                      "is the whole safety mechanism here.")

    def test_a_missing_table_counts_as_none_not_zero(self):
        self.assertIsNone(
            self.probe._scoped_count(self.conn, "no_such_table", "narrator_id", "n1"),
            "a missing table counted as a number. That is the mechanism "
            "that turned seven wrong table names into seven silent passes.",
        )
        self.assertIsNone(
            self.probe._conv_like_count(self.conn, "no_such_table", "n1"),
        )

    def test_a_present_but_empty_table_counts_as_zero(self):
        """The other half of the distinction. A real table with no
        matching rows is a measured zero and must not read as None."""
        self.assertEqual(
            self.probe._scoped_count(
                self.conn, "story_candidates", "narrator_id", "n1",
            ),
            0,
        )
        self.assertEqual(
            self.probe._conv_like_count(self.conn, "turns", "n1"), 0,
        )

    def test_an_empty_narrator_id_declines_instead_of_counting_everything(self):
        """`conv_id LIKE '%%'` matches every row in the table. An empty
        narrator id must therefore decline, not report the whole table as
        that narrator's."""
        self.conn.execute("INSERT INTO turns (conv_id) VALUES ('conv-other')")
        self.conn.commit()
        self.assertIsNone(self.probe._conv_like_count(self.conn, "turns", ""))

    def test_the_conv_like_count_matches_only_the_named_narrator(self):
        self.conn.executemany(
            "INSERT INTO turns (conv_id) VALUES (?)",
            [("conv-n1",), ("conv-n1",), ("conv-n2",)],
        )
        self.conn.commit()
        self.assertEqual(self.probe._conv_like_count(self.conn, "turns", "n1"), 2)
        self.assertEqual(self.probe._conv_like_count(self.conn, "turns", "n2"), 1)


if __name__ == "__main__":
    unittest.main()
