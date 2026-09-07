"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, sections G/H/I.

The gate decides whether an experimental configuration may govern a
turn. Every test here is really the same question asked from a different
angle: can anything short of all four conditions let a degraded Lori
reach a real narrator?

The four conditions are a real person, durably testing-only, an armed
evaluation, and a recording trace. The fourth is the one most likely to
be dropped as pedantry, so it has its own tests: `trace_env.sh` resolves
the marker into `HORNELORE_RESPONSE_TRACE` only when a process starts,
so arming mid-run leaves tracing off, and an experimental turn nobody
recorded is worse than no experiment.
"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from api.services import lori_guard_authority as authority
from api.services import lori_guard_gate as gate
from api.services import lori_guard_registry as reg
from api.services import lori_guard_store as store


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRATION = os.path.join(
    _REPO, "server", "code", "db", "migrations",
    "0053_lori_guard_authority_overrides.sql")


class _ArmedRepo:
    """A temp directory shaped like the repo, with a marker in it."""

    def __init__(self, contents=None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".runtime" / "eval").mkdir(parents=True)
        if contents is not None:
            gate.eval_marker_path(self.root).write_text(
                contents, encoding="utf-8")

    def cleanup(self):
        self._tmp.cleanup()


def _store_with(overrides=None):
    """A connection factory over an in-memory store."""
    con = sqlite3.connect(":memory:")
    with open(_MIGRATION, encoding="utf-8") as fh:
        con.executescript(fh.read())
    con.commit()
    if overrides:
        store.apply_changes(con, overrides)
    return lambda: con


class EvalMarkerTests(unittest.TestCase):
    """Same three rules as the shell: unreadable, blank, stripped."""

    def test_absent_marker_is_unarmed(self):
        repo = _ArmedRepo()
        self.addCleanup(repo.cleanup)
        self.assertIsNone(gate.armed_eval_dir(repo.root))
        self.assertFalse(gate.experiment_is_armed(repo.root))

    def test_blank_marker_is_unarmed(self):
        """The shell says so explicitly: a blank or deleted marker must
        not resolve to the repo root."""
        for contents in ("", "\n", "   ", "\t\n  \n"):
            repo = _ArmedRepo(contents)
            self.addCleanup(repo.cleanup)
            with self.subTest(contents=repr(contents)):
                self.assertIsNone(gate.armed_eval_dir(repo.root))

    def test_trailing_newline_is_not_part_of_the_path(self):
        """`$(<file)` strips trailing newlines; so does this."""
        repo = _ArmedRepo(".runtime/eval/run-20260907\n")
        self.addCleanup(repo.cleanup)
        self.assertEqual(gate.armed_eval_dir(repo.root),
                         ".runtime/eval/run-20260907")

    def test_a_directory_where_the_marker_should_be_is_unarmed(self):
        repo = _ArmedRepo()
        self.addCleanup(repo.cleanup)
        gate.eval_marker_path(repo.root).mkdir()
        self.assertIsNone(gate.armed_eval_dir(repo.root))

    def test_marker_path_matches_the_shell(self):
        repo = _ArmedRepo()
        self.addCleanup(repo.cleanup)
        self.assertEqual(
            gate.eval_marker_path(repo.root),
            repo.root / ".runtime" / "eval" / "current_eval_dir")


class GateDecisionTableTests(unittest.TestCase):
    """Each condition, failed alone, must close the gate."""

    def setUp(self):
        self.repo = _ArmedRepo(".runtime/eval/run-1")
        self.addCleanup(self.repo.cleanup)
        self.factory = _store_with({reg.by_name("cc_word_limit").id: False})

    def _acquire(self, **kw):
        params = dict(
            person_id="p-test",
            connection_factory=self.factory,
            testing_only_probe=lambda _pid: True,
            trace_enabled_probe=lambda: True,
            repo_root=self.repo.root,
        )
        params.update(kw)
        return gate.acquire_turn_authority(**params)

    def test_all_four_conditions_met_applies_the_experiment(self):
        """IC-6/IC-8 boundary: the only state that applies overrides."""
        result = self._acquire()
        self.assertTrue(result.experiment_applied)
        self.assertEqual(result.gate_reason, gate.GATE_EXPERIMENT_APPLIED)
        self.assertFalse(
            result.snapshot.is_selected(reg.by_name("cc_word_limit").id))

    def test_no_person_is_canonical(self):
        for pid in (None, "", "   "):
            with self.subTest(pid=repr(pid)):
                result = self._acquire(person_id=pid)
                self.assertFalse(result.experiment_applied)
                self.assertEqual(result.gate_reason, gate.GATE_NO_PERSON)

    def test_a_real_narrator_stays_canonical_even_while_armed(self):
        """The case this whole module exists for."""
        result = self._acquire(testing_only_probe=lambda _pid: False)
        self.assertFalse(result.experiment_applied)
        self.assertEqual(result.gate_reason, gate.GATE_NOT_TESTING_ONLY)
        self.assertTrue(
            result.snapshot.is_selected(reg.by_name("cc_word_limit").id),
            "A real narrator must receive the canonical configuration "
            "regardless of what an operator has selected.")

    def test_unarmed_evaluation_is_canonical(self):
        unarmed = _ArmedRepo()
        self.addCleanup(unarmed.cleanup)
        result = self._acquire(repo_root=unarmed.root)
        self.assertEqual(result.gate_reason, gate.GATE_NO_EVAL_MARKER)
        self.assertFalse(result.experiment_applied)

    def test_armed_but_not_recording_is_refused(self):
        """IC-8 — an unmeasured experimental turn is worse than none."""
        result = self._acquire(trace_enabled_probe=lambda: False)
        self.assertFalse(result.experiment_applied)
        self.assertEqual(result.gate_reason, gate.GATE_TRACE_NOT_ENABLED)
        self.assertTrue(
            result.snapshot.is_selected(reg.by_name("cc_word_limit").id))

    def test_unreadable_store_is_canonical(self):
        def _boom():
            raise sqlite3.OperationalError("unable to open database file")
        result = self._acquire(connection_factory=_boom)
        self.assertFalse(result.experiment_applied)
        self.assertEqual(result.gate_reason, gate.GATE_STORE_UNAVAILABLE)

    def test_a_failing_testing_only_probe_is_canonical(self):
        def _boom(_pid):
            raise sqlite3.OperationalError("database is locked")
        result = self._acquire(testing_only_probe=_boom)
        self.assertFalse(result.experiment_applied)
        self.assertEqual(result.gate_reason, gate.GATE_NO_PERSON)

    def test_a_failing_trace_probe_is_treated_as_not_recording(self):
        def _boom():
            raise RuntimeError("trace module exploded")
        result = self._acquire(trace_enabled_probe=_boom)
        self.assertEqual(result.gate_reason, gate.GATE_TRACE_NOT_ENABLED)

    def test_every_reason_is_from_the_declared_vocabulary(self):
        for kwargs in (
            {}, {"person_id": None},
            {"testing_only_probe": lambda _p: False},
            {"trace_enabled_probe": lambda: False},
        ):
            with self.subTest(kwargs=list(kwargs)):
                self.assertIn(self._acquire(**kwargs).gate_reason,
                              gate.VALID_GATE_REASONS)


class AcquisitionShapeTests(unittest.TestCase):

    def setUp(self):
        self.repo = _ArmedRepo(".runtime/eval/run-1")
        self.addCleanup(self.repo.cleanup)

    def test_a_snapshot_always_exists(self):
        """No consumer should ever handle 'no configuration'."""
        result = gate.acquire_turn_authority(
            None, repo_root=self.repo.root,
            testing_only_probe=lambda _p: False,
            trace_enabled_probe=lambda: True,
            connection_factory=_store_with())
        self.assertIsInstance(result.snapshot, authority.AuthoritySnapshot)
        self.assertEqual(len(result.snapshot.states), len(reg.REGISTRY))

    def test_result_is_immutable(self):
        import dataclasses
        result = gate.acquire_turn_authority(
            None, repo_root=self.repo.root,
            testing_only_probe=lambda _p: False,
            trace_enabled_probe=lambda: True,
            connection_factory=_store_with())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.experiment_applied = True     # type: ignore[misc]

    def test_trace_identity_carries_the_gate_reason(self):
        factory = _store_with({reg.by_name("cc_word_limit").id: False})
        result = gate.acquire_turn_authority(
            "p-test", repo_root=self.repo.root,
            testing_only_probe=lambda _p: True,
            trace_enabled_probe=lambda: True,
            connection_factory=factory)
        identity = result.trace_identity()
        for key in ("registry_fingerprint", "revision",
                    "selection_fingerprint", "selected", "excluded",
                    "gate_reason", "experiment_applied"):
            self.assertIn(key, identity)
        self.assertEqual(identity["gate_reason"], gate.GATE_EXPERIMENT_APPLIED)
        self.assertEqual(identity["eval_dir"], ".runtime/eval/run-1")


class ClientCannotArmItselfTests(unittest.TestCase):
    """IC-7 — server-side state only.

    A browser may propose a turn mode; it may never nominate itself for
    an experiment.
    """

    def test_the_gate_reads_nothing_client_supplied(self):
        """Checked over EXECUTABLE CODE, not raw text.

        The first version used `inspect.getsource` and a substring
        search, and failed instantly — on the module's own docstring,
        which says it never consults runtime71 or params. That is the
        comment-matching failure CLAUDE.md records three instances of,
        made here for the fourth time. Identifiers come from the AST;
        docstrings are excluded explicitly.
        """
        import ast
        import inspect

        tree = ast.parse(inspect.getsource(gate))

        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None)
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docstrings.add(id(body[0].value))

        identifiers = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, ast.arg):
                identifiers.add(node.arg)
            elif (isinstance(node, ast.Constant)
                  and isinstance(node.value, str)
                  and id(node) not in docstrings):
                identifiers.add(node.value)

        for forbidden in ("runtime71", "params", "request", "msg",
                          "profile_json", "turn_mode"):
            with self.subTest(token=forbidden):
                self.assertNotIn(
                    forbidden, identifiers,
                    f"{forbidden!r} is referenced in the gate's code. A "
                    f"client must never be able to influence experiment "
                    f"eligibility.")


if __name__ == "__main__":
    unittest.main()
