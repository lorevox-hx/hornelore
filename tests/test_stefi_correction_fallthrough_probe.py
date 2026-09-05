"""The Stefi probe's assertions must claim exactly what they prove.

    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_stefi_correction_fallthrough_probe

── WHY THIS FILE EXISTS ──────────────────────────────────────────────

The probe's `turn_mode` assertion was worded wrongly twice in one day,
in opposite directions, and both readings passed their own run:

  1. **"the committed turn is stamped interview, not correction."**
     Overstated. The persisted value was `None`, and `None` is not a
     stamp. A reader would conclude the product records `interview`
     somewhere. It does not.

  2. **"vacuous — it cannot fail."** An overcorrection, and wrong on the
     facts. `turn_mode` IS persisted: 55 turns carry it in the live
     database and **4 of them carry `correction`**. The assertion
     discriminates, and there is real data that would fail it.

The truth sits between them and is a property of ONE function:
`_finalize_deterministic_turn` (`chat_ws.py:278`) is the only writer of
`turn_mode` into turn meta, and ordinary turns finalise elsewhere with
`meta={"ws": True}`. So the mode is stamped exactly on the deterministic
routes, and its ABSENCE is how an ordinary interview turn is stored.

These tests pin that shape against the shipped source, so the wording
cannot drift back to either error without a failure here.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROBE = _REPO_ROOT / "scripts" / "stefi_correction_fallthrough_probe.py"
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"

PROBE_SRC = _PROBE.read_text(encoding="utf-8")


def _executable_source(src: str) -> str:
    """The probe's CODE, with docstrings AND comments removed.

    ── THE SELF-DOCUMENTATION TRAP, THIRD OCCURRENCE ─────────────────

    *(Written as a raw text scan, and it failed on the probe's own
    explanations — twice in one file. The probe documents the wording
    error it used to have ("stamped interview") and the stub bug it used
    to have (`sys.modules.setdefault("websockets"`), because a reader
    needs to know why the current shape is what it is. A substring scan
    cannot tell a post-mortem from a violation, so it demanded the
    explanations be deleted to go green.*

    *This repository has now hit that trap three times — the cohort
    runner's deletion scan, the browser helper's positional scan, and
    here. The rule each time is the same: scan the executable code.)*
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                if len(body) == 1:
                    body[0] = ast.Pass()
                else:
                    body.pop(0)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)      # ast.unparse drops comments entirely


EXEC_SRC = _executable_source(PROBE_SRC)


class AssertionWordingTests(unittest.TestCase):
    """The claim must match the evidence."""

    def test_it_does_not_claim_the_turn_is_stamped_interview(self):
        self.assertNotIn(
            "stamped interview", EXEC_SRC,
            "absence of turn_mode is not a stamp; the product never writes "
            "'interview' into turn meta")

    def test_it_claims_only_that_no_correction_mode_persisted(self):
        self.assertIn("no correction mode was persisted", PROBE_SRC)

    def test_it_records_why_absence_is_meaningful(self):
        """Otherwise the reader cannot tell absence from 'not measured'."""
        self.assertIn("absence is how ordinary turns are stored", PROBE_SRC)
        self.assertIn("_finalize_deterministic_turn", PROBE_SRC)

    def test_it_does_not_call_the_assertion_vacuous(self):
        """The overcorrection was also wrong and must not come back."""
        body = PROBE_SRC
        self.assertNotIn("VACUOUS HERE", body)


class ProductShapeTests(unittest.TestCase):
    """The facts the wording depends on, read from the shipped server."""

    def test_only_the_deterministic_finaliser_stamps_turn_mode(self):
        src = _CHAT_WS.read_text(encoding="utf-8")
        writers = [m.start() for m in
                   re.finditer(r'turn_meta[^\n]*"turn_mode"\s*:', src)]
        self.assertEqual(
            len(writers), 1,
            "more than one site writes turn_mode into turn meta; the probe's "
            "wording assumes exactly one (_finalize_deterministic_turn)")

        tree = ast.parse(src)
        enclosing = None
        line = src[:writers[0]].count("\n") + 1
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                if node.lineno <= line <= end:
                    if enclosing is None or node.lineno > enclosing.lineno:
                        enclosing = node
        self.assertIsNotNone(enclosing)
        self.assertEqual(enclosing.name, "_finalize_deterministic_turn")

    def test_the_fallthrough_branch_still_resets_both_mode_copies(self):
        """The Phase 3 fix itself, pinned.

        Resetting only the local variable would leave `params["turn_mode"]`
        as "correction", and the completed-turn hooks read the mode from
        params — so the turn would still be treated as deterministic.
        """
        src = _CHAT_WS.read_text(encoding="utf-8")
        i = src.find("[correction-fallthrough]")
        self.assertGreater(i, 0, "the fallthrough log line is gone")
        window = src[max(0, i - 600):i]
        self.assertIn('turn_mode = "interview"', window)
        self.assertIn('params["turn_mode"] = "interview"', window)


class ProbeSafetyTests(unittest.TestCase):
    """Properties the probe must keep whatever else changes."""

    DESTRUCTIVE = {"delete", "rmtree", "unlink", "rmdir", "erase",
                   "hard_delete", "remove"}

    def test_the_probe_has_no_deletion_call_site(self):
        offenders = []
        for node in ast.walk(ast.parse(PROBE_SRC)):
            if isinstance(node, ast.Call):
                name = (getattr(node.func, "attr", None)
                        or getattr(node.func, "id", "") or "")
                if name.lower() in self.DESTRUCTIVE:
                    offenders.append((name, node.lineno))
        self.assertEqual(offenders, [])

    def test_the_deletion_scan_can_actually_fail(self):
        """Positive control."""
        planted = "import shutil\nshutil.rmtree('/x')\n"
        found = [n for n in ast.walk(ast.parse(planted))
                 if isinstance(n, ast.Call)
                 and (getattr(n.func, "attr", "") or "").lower() in self.DESTRUCTIVE]
        self.assertTrue(found)

    def test_the_database_is_resolved_the_way_the_server_resolves_it(self):
        self.assertIn("DATA_DIR", PROBE_SRC)
        self.assertIn("DB_NAME", PROBE_SRC)
        self.assertIn('data_dir / "db" / db_name', PROBE_SRC)

    def test_the_websockets_stub_is_removed_again(self):
        """The stub escaped once and cost a narrator.

        Scanned over the EXECUTABLE source: the probe documents the old
        `setdefault` bug in a comment, and that explanation is why the
        current code is shaped as it is.
        """
        self.assertIn("sys.modules.pop('websockets', None)",
                      EXEC_SRC.replace('"', "'"))
        self.assertNotIn("sys.modules.setdefault('websockets'",
                         EXEC_SRC.replace('"', "'"))

    def test_the_stub_scan_can_actually_fail(self):
        """Positive control — the scan must reject the real defect."""
        planted = _executable_source(
            'import sys\n'
            'def f():\n'
            '    sys.modules.setdefault("websockets", object())\n')
        self.assertIn("sys.modules.setdefault('websockets'",
                      planted.replace('"', "'"))

    def test_the_transport_is_checked_before_a_narrator_is_created(self):
        i_check = PROBE_SRC.find("require_real_websockets()      # before")
        i_create = PROBE_SRC.find("person_id = create_narrator()")
        self.assertGreater(i_check, 0)
        self.assertGreater(i_create, i_check,
                           "narrator creation must not precede the transport "
                           "check — a hollow module cost one already")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
