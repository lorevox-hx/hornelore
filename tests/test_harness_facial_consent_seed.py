"""The Test 23 facial-consent seed must match the product's contract.

    PYTHONPATH=server/code python3 -m unittest tests.test_harness_facial_consent_seed

── WHY THIS EXISTS ───────────────────────────────────────────────────

`BUG-HARNESS-FACIAL-CONSENT-OVERLAY-BLOCK-01` was filed on 2026-05-06,
repaired, extended to a third browser context on 2026-08-30, and landed
at `66197c3` — and the seed never worked once, in any of the three
contexts. It wrote:

    localStorage.setItem('lorevox_facial_consent_granted', '1');
    localStorage.setItem('lorevox_facial_consent_declined', '0');

Two independent faults, either of which is fatal on its own:

  * The VALUE. `ui/js/facial-consent.js` stores a tri-state — `'true'`
    granted, `'false'` declined, absent never asked — and its legacy
    migration tests `getItem(LS_KEY_LEGACY) === 'true'`. `'1'` is not
    `'true'`, so the migration never ran.

  * The KEY. `lorevox_facial_consent_declined` does not exist anywhere
    in the product. A decline is the VALUE `'false'` on the same key.
    Writing `'0'` to an invented key did nothing at all.

Nothing noticed, because a harness that blocks on a consent overlay
looks exactly like a harness that is slow, and the only observer was a
human waiting for it.

── WHAT THIS FILE PINS, AND WHAT IT CANNOT ───────────────────────────

This asserts the harness agrees with the product's own constants, read
out of `facial-consent.js` rather than restated here — a copy of a
contract is not a check on it. It is a static agreement test and it runs
in under a second with no browser.

**It does NOT prove the overlay is suppressed.** Only a live run does
that, and that is recorded as still owed rather than implied by a green
suite here.
"""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS = _REPO_ROOT / "scripts" / "ui" / "run_test23_two_person_resume.py"
_CONSENT_JS = _REPO_ROOT / "ui" / "js" / "facial-consent.js"


class ProductContractTests(unittest.TestCase):
    """Read the contract off the product, so the test cannot drift alone."""

    @classmethod
    def setUpClass(cls):
        cls.js = _CONSENT_JS.read_text(encoding="utf-8")
        cls.py = _HARNESS.read_text(encoding="utf-8")

    def test_the_product_still_uses_the_key_names_the_harness_seeds(self):
        self.assertIn("const LS_KEY_LEGACY = 'lorevox_facial_consent_granted';",
                      self.js)
        self.assertIn("const LS_KEY_PREFIX = 'lorevox_facial_consent:';",
                      self.js)

    def test_the_product_migration_requires_the_string_true(self):
        """The exact comparison the seed has to satisfy."""
        self.assertIn("localStorage.getItem(LS_KEY_LEGACY) === 'true'", self.js)

    def test_the_declined_key_does_not_exist_in_the_product(self):
        """A decline is a VALUE, not a key. Pinned so nobody re-invents it."""
        self.assertNotIn("lorevox_facial_consent_declined", self.js)
        self.assertIn("localStorage.setItem(_activeKey(), 'false')", self.js)


def _string_literals(text: str) -> str:
    """Every string constant in the module, joined.

    ── AST, NOT RAW TEXT, 2026-08-30 ──────────────────────────────────

    The first version of the guards below scanned raw source and BOTH
    failed on the COMMENT that explains why the old seed was wrong,
    which quotes it verbatim. A guard that cannot tell a prohibition
    from a violation puts pressure on the next person to delete the
    explanation to get their build green — and the explanation is the
    most valuable thing in that file.

    Stripping comments by tokenizing was the second attempt and it also
    failed, for a duller reason: `tokenize` yields one token at a time,
    so `add_init_script(CONSENT_SEED_SCRIPT)` reassembles as four tokens
    and no substring survives.

    The AST is the honest instrument. The seed is a STRING the harness
    hands to Playwright, so the question "does the harness write '1'"
    is exactly "does any string constant say so" — and comments are not
    constants. This is the same lesson `run_narrator_cohort_acceptance`
    records after its scans failed four times on its own documentation.
    """
    tree = ast.parse(text)
    return "\n".join(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str))


def _seeded_context_count(text: str) -> int:
    """`add_init_script(CONSENT_SEED_SCRIPT)` call sites, by AST."""
    tree = ast.parse(text)
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_init_script"):
            continue
        if (len(node.args) == 1 and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "CONSENT_SEED_SCRIPT"):
            n += 1
    return n


class HarnessSeedTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.py = _HARNESS.read_text(encoding="utf-8")
        cls.code = _string_literals(cls.py)

    def test_the_seed_value_is_true_and_never_one(self):
        """FAILS for the '1' that shipped."""
        self.assertIn("CONSENT_SEED_VALUE = \"true\"", self.py)
        self.assertNotIn("'lorevox_facial_consent_granted', '1'", self.code)
        self.assertNotIn('"lorevox_facial_consent_granted", "1"', self.code)

    def test_the_prohibition_is_still_EXPLAINED_in_the_source(self):
        """Non-vacuity for the comment-stripping above.

        If the explanation is ever deleted to satisfy a scanner, this
        fails and says so — which is the whole reason the scanners are
        comment-blind.
        """
        self.assertIn("'1'", self.py)
        self.assertIn("lorevox_facial_consent_declined", self.py)
        self.assertNotIn("lorevox_facial_consent_declined", self.code)

    def test_the_harness_never_writes_the_nonexistent_declined_key(self):
        """FAILS for the invented key that shipped.

        Scoped to `setItem` rather than the bare name: the file discusses
        the key at length in the comment explaining why it is wrong, and
        a guard that cannot tell a prohibition from a violation pressures
        the next person to delete the explanation.
        """
        writes = re.findall(
            r"setItem\(\s*['\"]lorevox_facial_consent_declined['\"]", self.code)
        self.assertEqual([], writes,
                         "the harness writes a key the product never reads")

    def test_no_seed_literal_is_hand_written_anywhere(self):
        """Three copies is how three copies stayed wrong together.

        The seed is composed from `CONSENT_SEED_KEY` and
        `CONSENT_SEED_VALUE`, so a hand-written `setItem('lorevox_...')`
        anywhere in the file is by definition a second definition — the
        shape that let one correction miss two contexts.
        """
        hand_written = re.findall(
            r"setItem\('lorevox_facial_consent_granted'", self.code)
        self.assertEqual(
            [], hand_written,
            "a seed literal is hand-written; route it through "
            "CONSENT_SEED_SCRIPT so the three contexts cannot diverge")
        self.assertIn("CONSENT_SEED_KEY = \"lorevox_facial_consent_granted\"",
                      self.py)
        self.assertIn("CONSENT_PER_NARRATOR_PREFIX = \"lorevox_facial_consent:\"",
                      self.py)

    def test_every_fresh_context_seeds_through_the_one_definition(self):
        """All three browser contexts, including the cold restart."""
        self.assertEqual(3, _seeded_context_count(self.py),
                         "expected exactly three browser contexts seeded "
                         "through the single CONSENT_SEED_SCRIPT definition")

    def test_the_migration_is_ASSERTED_after_narrator_selection(self):
        """Seeding is step one. Migrating is the part that matters.

        FAILS if the post-selection assertion is dropped — which is the
        state that let a dead seed look alive for three months.
        """
        self.assertIn("def _assert_consent_migrated(", self.py)
        self.assertIn("_assert_consent_migrated(new_page, nr.person_id",
                      self.py)
        self.assertIn("CONSENT_PER_NARRATOR_PREFIX", self.py)

    def test_the_assertion_checks_the_narrator_scoped_key_not_the_legacy_one(self):
        start = self.py.index("def _assert_consent_migrated(")
        end = self.py.index("def _restart_browser_and_resume(", start)
        block = self.py[start:end]
        self.assertIn("CONSENT_PER_NARRATOR_PREFIX", block)
        self.assertIn("person_id", block)
        self.assertNotIn("LS_KEY_LEGACY", block)
        # It must compare against the tri-state value, not truthiness.
        self.assertIn("value == CONSENT_SEED_VALUE", block)

    def test_a_failed_migration_is_reported_rather_than_swallowed(self):
        start = self.py.index("def _assert_consent_migrated(")
        end = self.py.index("def _restart_browser_and_resume(", start)
        block = self.py[start:end]
        self.assertIn("nr.notes.append", block)
        self.assertIn("did NOT migrate", block)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
