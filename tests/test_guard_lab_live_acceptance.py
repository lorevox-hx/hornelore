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


if __name__ == "__main__":
    unittest.main()
