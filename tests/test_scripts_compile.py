"""Every tracked Python file under scripts/ and tests/ must parse.

    PYTHONPATH=server/code python3 -m unittest tests.test_scripts_compile

── WHY THIS EXISTS ───────────────────────────────────────────────────

`scripts/ui/run_test23_two_person_resume.py` — the two-narrator,
seven-era resume canary — stopped parsing on 2026-05-06 and nobody
noticed until 2026-08-27. Three and a half months in which the harness
that walks Mary and Marvin through every Life Map era, the cold restart
and the cross-person isolation check could not run at all, and said
nothing about it.

The defect itself was one over-indented block. Its cost was the silence:
**nothing in the ordinary test path compiles these files**, so a harness
can break and stay broken for as long as nobody happens to run it by
hand. Unit tests import the modules they test; they never import the
harnesses, because the harnesses drive a browser.

This gate closes exactly that hole and nothing more. It does not run the
harnesses, does not need a stack, a browser or a network, and takes well
under a second. It answers one question: does this file still parse?

Recorded in BUG-HARNESS-TEST23-INDENTATION-01 §4 as the third thing the
repair owed, after correcting the indentation and running the harness.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

#: Directories whose Python must always parse.
_ROOTS = ("scripts", "tests")


def _tracked_python_files():
    """Ask Git, so untracked scratch files never fail the build.

    Read-only (`git ls-files`), per the standing rule that agents run no
    write-side Git. Falls back to a filesystem walk when Git is not
    usable, because a gate that silently checks nothing is worse than one
    that checks a slightly wider set.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", *_ROOTS],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60)
        if out.returncode == 0 and out.stdout.strip():
            return [_REPO_ROOT / line for line in out.stdout.splitlines()
                    if line.endswith(".py")]
    except (OSError, subprocess.SubprocessError):
        pass
    files = []
    for root in _ROOTS:
        files.extend((_REPO_ROOT / root).rglob("*.py"))
    return [f for f in files if "__pycache__" not in f.parts]


class ScriptsCompileTests(unittest.TestCase):

    def test_every_tracked_script_parses(self):
        files = _tracked_python_files()
        self.assertGreater(len(files), 20,
                           "found almost no Python to check — the file "
                           "discovery is broken, not the repository")
        broken = []
        for path in files:
            source = path.read_text(encoding="utf-8", errors="replace")
            try:
                compile(source, str(path), "exec")
            except SyntaxError as exc:      # IndentationError included
                rel = path.relative_to(_REPO_ROOT)
                broken.append(f"{rel}:{exc.lineno}: "
                              f"{type(exc).__name__}: {exc.msg}")
        self.assertEqual(
            broken, [],
            "these tracked Python files do not parse:\n  "
            + "\n  ".join(broken))

    def test_the_harnesses_this_gate_was_written_for_are_covered(self):
        """Named explicitly, so a discovery change cannot drop them.

        A gate whose value depends on a glob still matching is one
        refactor away from checking nothing.
        """
        covered = {str(p.relative_to(_REPO_ROOT)).replace("\\", "/")
                   for p in _tracked_python_files()}
        for harness in (
            "scripts/ui/run_test23_two_person_resume.py",
            "scripts/ui/run_parent_session_readiness_harness.py",
            "scripts/ui/run_parent_session_rehearsal_harness.py",
        ):
            with self.subTest(harness=harness):
                self.assertIn(harness, covered)

    def test_the_gate_actually_catches_a_broken_file(self):
        """Positive control. A guard that cannot fail proves nothing.

        The precise shape of the original defect: a correctly indented
        call followed by an over-indented line.
        """
        planted = (
            "def f():\n"
            "    ctx.add_init_script(\n"
            "        'x'\n"
            "    )\n"
            "            page = ctx.new_page()\n"
        )
        with self.assertRaises(IndentationError):
            compile(planted, "<planted>", "exec")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
