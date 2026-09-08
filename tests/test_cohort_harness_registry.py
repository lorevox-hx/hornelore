"""Every registered cohort harness must resolve. A missing one SHRINKS the run.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_cohort_harness_registry

WHY THIS EXISTS, AND WHY IT IS NOT "DO THE FILES EXIST".

`run_narrator_cohort_acceptance.load_personas` builds the cohort like this
(`:733`):

    for stem, expected in COHORT_HARNESSES.items():
        cfg, _err = load_harness_config(stem)
        if cfg is None or not intake_is_testing_only(cfg):
            continue

**It skips silently.** A harness that has been moved, renamed, archived or
broken does not raise: it drops out, the cohort gets smaller, and the run
still reports success over whatever remains. That is not hypothetical —
Phase 6 Run B reported a clean 10-turn run over 2 narrators when 38 turns
over 12 were expected, because a flag narrowed the selection and nothing
refused.

The repository-hygiene pass then came within one decision of archiving
`run_jake_long_narration_harness.py` and `run_shatner_long_narration_harness.py`
because they looked like superseded one-offs. They are named in the
runner's own EXCLUSIONS registry, each with a recorded reason — Jake is
Kent-derived and the only harness with `testing_only=False`, Shatner is a
read-only reference persona. **Archiving them would not have crashed
anything. It would have left two exclusion reasons pointing at files that
no longer exist, which is worse: a silent registry describing a tree that
has moved on.**

So this test pins two different invariants:

1. every COHORT_HARNESSES stem actually LOADS — the thing that decides
   cohort size;
2. every EXCLUSIONS key names a real file — the thing that keeps the
   documented reasons honest.

It imports no server code and starts no stack.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_narrator_cohort_acceptance as runner          # noqa: E402


class CohortHarnessRegistry(unittest.TestCase):

    def test_the_registry_is_not_empty(self):
        """Guard against every assertion below passing vacuously."""
        self.assertTrue(
            runner.COHORT_HARNESSES,
            "COHORT_HARNESSES is empty; the cohort would be silently zero")

    def test_every_registered_harness_loads(self):
        """The invariant that decides how many narrators a run covers.

        `load_harness_config` returning None is exactly what
        `load_personas` swallows, so this is the production boundary that
        matters — not `Path.is_file()`.
        """
        unresolved = []
        for stem in runner.COHORT_HARNESSES:
            cfg, err = runner.load_harness_config(stem)
            if cfg is None:
                unresolved.append(f"{stem}: {err}")
        self.assertEqual(
            unresolved, [],
            "Registered cohort harnesses failed to load. load_personas "
            "SKIPS these silently, so the next cohort run would report "
            "success over a smaller cohort than the one requested: "
            f"{unresolved}")

    def test_every_excluded_harness_still_exists(self):
        """An exclusion reason about a deleted file explains nothing."""
        missing = [
            stem for stem in runner.EXCLUSIONS
            if not (REPO_ROOT / "scripts" / f"{stem}.py").is_file()
        ]
        self.assertEqual(
            missing, [],
            "EXCLUSIONS names harnesses that no longer exist. Each entry "
            "records WHY a harness is kept out of the cohort; if the file "
            "is gone the reason is unreadable and the next reader cannot "
            "tell a deliberate exclusion from an accident: "
            f"{missing}")

    def test_a_harness_is_not_both_registered_and_excluded(self):
        """The two registries must not disagree about one harness."""
        both = sorted(set(runner.COHORT_HARNESSES) & set(runner.EXCLUSIONS))
        self.assertEqual(
            both, [],
            f"Registered as cohort members AND excluded: {both}")


if __name__ == "__main__":
    unittest.main()
