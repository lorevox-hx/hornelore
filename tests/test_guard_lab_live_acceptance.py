"""The live-acceptance instrument must be incapable of changing anything.

WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, section X.

`scripts/guard_lab_live_acceptance.py` runs against Chris's real stack
and his real database — the one holding Kent and Janice. Its docstring
says READ ONLY. A docstring cannot fail, so these tests read the module
and refuse it if the claim ever stops being true.

THE THREE PROPERTIES

  It cannot write to the database. Every connection is opened
  `mode=ro`, which SQLite enforces; a plain `sqlite3.connect` on a real
  path would not.

  It cannot mutate through the API. No POST, PUT, PATCH or DELETE, and
  no guard-lab mutation route named anywhere in its executable code.

  UNVERIFIED IS NOT A PASS. The summary must exit non-zero when a clause
  could not be decided. Rounding absent evidence up to green is the
  failure this project has paid for most often, and the exit code is
  what a future harness would trust.
"""
from __future__ import annotations

import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "guard_lab_live_acceptance.py"


def _tree() -> ast.Module:
    return ast.parse(SCRIPT.read_text(encoding="utf-8"))


def _executable_strings(tree: ast.Module) -> set:
    """Every string constant EXCEPT docstrings.

    Reading raw source and searching for a word matches this module's own
    prose — the comment-matching failure CLAUDE.md records four instances
    of. Docstrings are excluded by identity.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                             ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


class ReadOnlyTests(unittest.TestCase):

    def test_the_script_exists(self):
        self.assertTrue(SCRIPT.exists(), f"{SCRIPT} is missing")

    def test_every_database_connection_is_read_only(self):
        """`mode=ro` is enforced by SQLite; a comment is not."""
        tree = _tree()
        connects = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ]
        self.assertTrue(connects, "no sqlite3.connect found — this guard has "
                                  "lost its subject and would pass vacuously")
        for call in connects:
            with self.subTest(line=call.lineno):
                first = call.args[0] if call.args else None
                literal = ""
                if isinstance(first, ast.JoinedStr):
                    literal = "".join(
                        v.value for v in first.values
                        if isinstance(v, ast.Constant)
                        and isinstance(v.value, str))
                elif isinstance(first, ast.Constant):
                    literal = str(first.value)
                self.assertIn(
                    "mode=ro", literal,
                    "every connection must be opened read-only — this "
                    "instrument runs against the database holding real "
                    "narrators")
                self.assertTrue(
                    any(kw.arg == "uri" for kw in call.keywords),
                    "mode=ro only takes effect with uri=True")

    def test_it_issues_no_mutating_http_method(self):
        strings = _executable_strings(_tree())
        for verb in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(verb=verb):
                self.assertNotIn(
                    verb, strings,
                    f"{verb} appears in executable code. The acceptance is "
                    f"Chris in the browser; this file records what that "
                    f"left behind and must never drive it.")

    def test_it_names_no_guard_lab_mutation_route(self):
        strings = _executable_strings(_tree())
        for route in ("/all-switchable-off", "/restore-defaults",
                      "/authorities"):
            with self.subTest(route=route):
                self.assertFalse(
                    any(route in s for s in strings),
                    f"{route} is referenced in executable code — an "
                    f"instrument that can apply the configuration cannot "
                    f"be trusted to describe it")

    def test_it_never_opens_a_file_for_writing_outside_the_run_directory(self):
        """Snapshots and the run directory are the only writes allowed."""
        tree = _tree()
        writes = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("write_text", "write_bytes", "mkdir")
        ]
        for call in writes:
            with self.subTest(line=call.lineno):
                source = ast.get_source_segment(
                    SCRIPT.read_text(encoding="utf-8"), call) or ""
                self.assertTrue(
                    "out" in source or "_run_dir" in source,
                    f"unexpected write at line {call.lineno}: {source[:80]}")


class VerdictTests(unittest.TestCase):
    """Unverified is a third state, and it must not exit green."""

    def _module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_guard_lab_live_acceptance", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)          # type: ignore[union-attr]
        return module

    def test_the_three_verdicts_are_distinct(self):
        m = self._module()
        self.assertEqual(3, len({m.PASS, m.FAIL, m.UNVERIFIED}))

    def test_an_unverified_clause_does_not_exit_zero(self):
        m = self._module()
        self.assertEqual(0, m._summarise([(m.PASS, "a", "")]))
        self.assertEqual(
            2, m._summarise([(m.PASS, "a", ""), (m.UNVERIFIED, "b", "")]),
            "absent evidence must not be reported as an acceptance")
        self.assertEqual(
            1, m._summarise([(m.PASS, "a", ""), (m.FAIL, "b", "")]))

    def test_a_failure_outranks_an_unverified(self):
        m = self._module()
        self.assertEqual(
            1, m._summarise([(m.UNVERIFIED, "a", ""), (m.FAIL, "b", "")]))


class RestartPersistenceTests(unittest.TestCase):
    """The verdict must come from the NAMED pair, not from file order.

    THE BUG THIS EXISTS FOR, found in review before the live run. The
    first version took `sorted(glob("state-*.json"))[0]` and `[-1]`. The
    acceptance procedure asks for three snapshots — `before-all-off`,
    `before-restart`, `after-restart` — so on a CORRECT run the pair
    compared was `before-all-off` (revision 0, no overrides) against
    `after-restart` (37 overrides). They differ for the obvious reason,
    the guard fell through, and a restart that worked was reported
    UNVERIFIED.

    It failed safe — under-reporting a pass rather than certifying a
    failure — and it would still have cost the run, then an argument
    about whether persistence actually worked. Which is the question the
    instrument exists to settle.

    These tests write real snapshot files in the format `snapshot`
    emits and run the shipped decision over them.
    """

    def setUp(self):
        import importlib.util
        import tempfile
        spec = importlib.util.spec_from_file_location(
            "_guard_lab_live_acceptance_restart", SCRIPT)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)          # type: ignore[union-attr]
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.run_dir = Path(self._tmp.name)

    def _write(self, stamp: str, label: str, *, revision: int,
               overridden: dict) -> Path:
        """A snapshot in the exact shape `snapshot` saves."""
        authorities = []
        for aid in range(1, 6):
            authorities.append({
                "id": aid,
                "name": f"a{aid}",
                "switchable": True,
                "canonical_default": True,
                "operator_override": overridden.get(aid),
                "effective": overridden.get(aid, True),
                "reason": ("operator_override" if aid in overridden
                           else "canonical_default"),
            })
        path = self.run_dir / f"state-{stamp}-{label}.json"
        path.write_text(json.dumps({
            "revision": revision,
            "registry_fingerprint": "r" * 64,
            "selection_fingerprint": "s" * 64,
            "authorities": authorities,
        }), encoding="utf-8")
        return path

    def _procedure_run(self, *, after_overrides=None, after_revision=None):
        """The three snapshots the written procedure actually produces."""
        self._write("20260907T120000Z", "before-all-off",
                    revision=0, overridden={})
        self._write("20260907T121000Z", "before-restart",
                    revision=1, overridden={1: False, 2: False, 3: False})
        self._write("20260907T123000Z", "after-restart",
                    revision=1 if after_revision is None else after_revision,
                    overridden={1: False, 2: False, 3: False}
                    if after_overrides is None else after_overrides)

    def test_a_correct_run_passes_despite_the_earlier_snapshot(self):
        """The exact shape that used to report UNVERIFIED."""
        self._procedure_run()
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.PASS, verdict, detail)
        self.assertIn("before-restart", detail)
        self.assertIn("after-restart", detail)
        self.assertNotIn("before-all-off", detail,
                         "the pre-All-Off snapshot must play no part in "
                         "the restart verdict")

    def test_a_lost_override_fails(self):
        """MUTATION: the restart drops one. It must go red, not amber."""
        self._procedure_run(after_overrides={1: False, 2: False})
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.FAIL, verdict, detail)
        self.assertIn("[3]", detail.replace(" ", ""))

    def test_a_flipped_override_fails(self):
        self._procedure_run(after_overrides={1: True, 2: False, 3: False})
        verdict, _ = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.FAIL, verdict)

    def test_everything_lost_fails(self):
        self._procedure_run(after_overrides={})
        verdict, _ = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.FAIL, verdict)

    def test_a_moved_revision_is_unverified_not_a_pass(self):
        """Matching overrides at a different revision is not a clean pair —
        something changed the configuration between the snapshots."""
        self._procedure_run(after_revision=4)
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.UNVERIFIED, verdict, detail)

    def test_an_empty_before_snapshot_proves_nothing(self):
        """Two override-free snapshots compare equal and test nothing.

        A green verdict there would be the fixture supplying the very
        property under test.
        """
        self._write("20260907T120000Z", "before-restart",
                    revision=0, overridden={})
        self._write("20260907T121000Z", "after-restart",
                    revision=0, overridden={})
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.UNVERIFIED, verdict, detail)

    def test_a_missing_label_says_which_one(self):
        self._write("20260907T120000Z", "before-all-off",
                    revision=0, overridden={})
        self._write("20260907T121000Z", "before-restart",
                    revision=1, overridden={1: False})
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.UNVERIFIED, verdict)
        self.assertIn("after-restart", detail)

    def test_the_latest_pair_wins_when_a_restart_is_retried(self):
        """A second attempt supersedes the first rather than being mixed."""
        self._write("20260907T120000Z", "before-restart",
                    revision=1, overridden={1: False})
        self._write("20260907T120500Z", "after-restart",
                    revision=9, overridden={4: False})      # failed attempt
        self._write("20260907T121000Z", "before-restart",
                    revision=2, overridden={2: False})
        self._write("20260907T122000Z", "after-restart",
                    revision=2, overridden={2: False})      # good attempt
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.PASS, verdict, detail)
        self.assertIn("20260907T122000Z", detail)

    def test_an_out_of_order_pair_is_refused(self):
        self._write("20260907T123000Z", "before-restart",
                    revision=1, overridden={1: False})
        self._write("20260907T120000Z", "after-restart",
                    revision=1, overridden={1: False})
        verdict, detail = self.m._restart_verdict(self.run_dir)
        self.assertEqual(self.m.UNVERIFIED, verdict, detail)

    def test_the_label_parser_matches_what_snapshot_writes(self):
        """Pin the filename format against the writer, not against hope.

        If `snapshot` ever changes its naming, this fails here rather
        than silently making every restart UNVERIFIED during a live run.
        """
        import ast
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        joined = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.JoinedStr)
            and any(isinstance(v, ast.Constant)
                    and isinstance(v.value, str) and "state-" in v.value
                    for v in n.values)
        ]
        self.assertTrue(joined, "snapshot no longer builds a state- filename")
        self._write("20260907T120000Z", "before-restart",
                    revision=1, overridden={1: False})
        groups = self.m._labelled_snapshots(self.run_dir)
        self.assertIn("before-restart", groups)


if __name__ == "__main__":
    unittest.main()
