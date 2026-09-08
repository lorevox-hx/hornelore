"""There is ONE canonical test root, and this notices if a second appears.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_single_test_root

WHY THIS EXISTS. Until 2026-09-08 the repository had two test trees one
letter apart: `tests/` with 350 files, and a singular `test/` with nine.
Nothing was wrong with the nine — one of them,
`test_wo10c_cognitive_support.py`, was the ONLY coverage anywhere for
`api.archive.wo10c_select_single_support_thread`, which is live
production. The problem was that every glob, every discovery run and
every agent's mental model addressed `tests/`, so that coverage was
invisible for five months and would have been archived as "historical"
by anyone reading the directory name instead of the file.

The failure mode is silence, which is why a test is the right shape for
the fix: a directory that nobody looks in cannot announce itself, but a
red suite can.

WHAT THIS DOES NOT DO. It does not forbid fixture or data directories,
and it does not care what lives under `tests/`. It refuses exactly one
thing: a SECOND top-level directory that Python test discovery would
plausibly claim.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The one canonical root. Everything executable lives here.
CANONICAL = "tests"

#: Directory names a reader, a glob or a discovery run would take for a
#: test root. `test` is the one that actually happened.
LOOKALIKES = ("test", "testing", "unittests", "unittest", "pytests", "spec")


class SingleTestRoot(unittest.TestCase):

    def test_the_canonical_root_exists(self):
        """Guard against the guard being vacuously true."""
        self.assertTrue(
            (REPO_ROOT / CANONICAL).is_dir(),
            f"{CANONICAL}/ is missing — this test would otherwise pass "
            f"by finding no lookalikes in a repository with no tests")

    def test_no_second_top_level_test_tree_holds_python(self):
        """A lookalike directory may exist; it may not hold test modules.

        Deliberately narrow. An empty `test/` left behind by an untracked
        local file is not a defect and must not fail the suite — what
        matters is whether executable test code has appeared somewhere
        discovery will miss.
        """
        offenders = []
        for name in LOOKALIKES:
            d = REPO_ROOT / name
            if not d.is_dir():
                continue
            offenders += [str(p.relative_to(REPO_ROOT))
                          for p in d.rglob("*.py")
                          if "__pycache__" not in p.parts]
        self.assertEqual(
            offenders, [],
            "Python test code exists outside tests/. Standard discovery "
            "addresses tests/ only, so this code is invisible to every "
            "glob and every agent that looks there — which is how "
            "test/test_wo10c_cognitive_support.py, the only coverage for "
            "a live production symbol, went unseen for five months. Move "
            "it under tests/ rather than adding a path here: "
            f"{offenders}")

    def test_no_second_top_level_test_tree_holds_fixtures(self):
        """Same rule for fixture data, which is how the split survives."""
        offenders = []
        for name in LOOKALIKES:
            d = REPO_ROOT / name
            if not d.is_dir():
                continue
            offenders += [str(p.relative_to(REPO_ROOT))
                          for p in d.rglob("*.json")]
        self.assertEqual(
            offenders, [],
            "Test fixture data exists outside tests/. Fixtures follow the "
            "tests that own them; a fixture left behind in a second tree "
            "is how the tree grows back. "
            f"{offenders}")


if __name__ == "__main__":
    unittest.main()
