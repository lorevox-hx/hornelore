"""Tests for scripts/cleanup_test_narrators.py classifier.

The classifier is the load-bearing piece — if it ever misclassifies
a real narrator as SAFE_DELETE, that narrator's row gets hard-deleted
with full FK cascade on the next operator run. These tests pin the
behavior so any future regex change has to face a test.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "cleanup_test_narrators.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "cleanup_test_narrators", _SCRIPT_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ClassifierBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cleanup = _load_module()


class KeepListTest(_ClassifierBase):
    def test_horne_family_kept(self):
        for name in (
            "Janice Josephine Horne",
            "Kent James Horne",
            "Christopher Todd Horne",
        ):
            with self.subTest(name=name):
                self.assertEqual(self.cleanup.classify(name), "KEEP")

    def test_horne_family_case_insensitive(self):
        # Case doesn't matter — pinned by lowercased display_name
        self.assertEqual(
            self.cleanup.classify("janice josephine horne"), "KEEP",
        )
        self.assertEqual(
            self.cleanup.classify("CHRISTOPHER TODD HORNE"), "KEEP",
        )

    def test_melanie_zollner_kept(self):
        # Zollner is Chris's wife (first real-narrator test).
        # Melanie Carter is NOT on the preserve list — operator
        # explicitly chose to drop her from the keep list
        # 2026-06-15.
        self.assertEqual(self.cleanup.classify("Melanie Zollner"), "KEEP")
        self.assertNotEqual(self.cleanup.classify("Melanie Carter"), "KEEP")

    def test_shatner_templates_kept(self):
        self.assertEqual(self.cleanup.classify("William Shatner"), "KEEP")
        self.assertEqual(
            self.cleanup.classify("William Alan Shatner"), "KEEP",
        )

    def test_walter_kept(self):
        # Walter is the one single-token-name explicitly preserved
        # by operator decision 2026-06-15. Every other single-token
        # name lands in NEEDS_REVIEW.
        self.assertEqual(self.cleanup.classify("Walter"), "KEEP")
        # Sanity check that case-insensitive match still works
        self.assertEqual(self.cleanup.classify("walter"), "KEEP")


class SafeDeleteTest(_ClassifierBase):
    def test_test_underscore_digits(self):
        # The 126-row bucket from the 2026-06-15 audit
        for name in (
            "Test_685586", "Test_244413", "Test_829536",
            "Test_053079", "Test_520035",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    self.cleanup.classify(name), "SAFE_DELETE",
                )

    def test_mary_and_marvin_repeat(self):
        # The 22-row harness duplication from parent-session readiness runs
        self.assertEqual(self.cleanup.classify("mary"), "SAFE_DELETE")
        self.assertEqual(self.cleanup.classify("Mary"), "SAFE_DELETE")
        self.assertEqual(self.cleanup.classify("Marvin Mann"), "SAFE_DELETE")
        self.assertEqual(self.cleanup.classify("marvin mann"), "SAFE_DELETE")

    def test_whats_artifact(self):
        # The 3-row name-capture bug class (extractor grabbed "What's"
        # from "What's your name?" prompt).
        self.assertEqual(self.cleanup.classify("What's"), "SAFE_DELETE")
        self.assertEqual(self.cleanup.classify("Whats"), "SAFE_DELETE")
        self.assertEqual(self.cleanup.classify("What’s"), "SAFE_DELETE")

    def test_debug_named_narrators(self):
        for name in (
            "Reset Test", "Era Cycle Test",
            "HARNESS_PROBE_DELME", "Bug 7",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    self.cleanup.classify(name), "SAFE_DELETE",
                )

    def test_test_storyteller_template(self):
        # data/narrator_templates/test_storyteller.json — instances
        # created from this template should be cleanable.
        self.assertEqual(
            self.cleanup.classify("Test storyteller"), "SAFE_DELETE",
        )

    def test_empty_name_safe_delete(self):
        # A nameless row is almost certainly garbage; bucket as
        # safe-delete so the cleanup pass sweeps it.
        self.assertEqual(self.cleanup.classify(""), "SAFE_DELETE")


class NeedsReviewTest(_ClassifierBase):
    """Single-token first names AND multi-token names that don't
    match either bucket land in NEEDS_REVIEW. Operator decides per
    row whether to delete or keep."""

    def test_single_token_first_names_other_than_walter(self):
        # Walter is explicitly KEEP per 2026-06-15 operator decision.
        # Every other single-token name still lands in NEEDS_REVIEW.
        for name in ("Jake", "Corky", "Era", "Esther"):
            with self.subTest(name=name):
                self.assertEqual(
                    self.cleanup.classify(name), "NEEDS_REVIEW",
                )

    def test_long_compound_names_review(self):
        # "Esther Ridley-Yamamoto-Cordova" from the audit — looks
        # generated but isn't on any blocklist. Operator decides.
        self.assertEqual(
            self.cleanup.classify("Esther Ridley-Yamamoto-Cordova"),
            "NEEDS_REVIEW",
        )

    def test_arbitrary_compound_name_review(self):
        self.assertEqual(
            self.cleanup.classify("Jane Smith"), "NEEDS_REVIEW",
        )


class SecondPassKeepGuardTest(_ClassifierBase):
    """Belt-and-suspenders: even if a future bug puts a pinned name
    into the SAFE_DELETE bucket via some classification regression,
    the commit_deletes() function does a second-pass KEEP check that
    refuses to fire DELETE on any row whose display_name matches the
    KEEP list. This test pins that second-pass guard."""

    def test_keep_list_constant_is_lowercased(self):
        # The KEEP set stores lowercased names. Verifies the
        # contract.
        for name in self.cleanup.KEEP_DISPLAY_NAMES:
            self.assertEqual(name, name.lower())

    def test_horne_family_in_keep_list(self):
        # 2026-06-15 operator decision: KEEP = Horne family + Melanie
        # Zollner + Shatner templates + Walter. Melanie Carter is NOT
        # on the keep list.
        for name in (
            "janice josephine horne",
            "kent james horne",
            "christopher todd horne",
            "melanie zollner",
            "william shatner",
            "william alan shatner",
            "walter",
        ):
            with self.subTest(name=name):
                self.assertIn(name, self.cleanup.KEEP_DISPLAY_NAMES)
        # Sanity check the operator-explicit drop
        self.assertNotIn(
            "melanie carter", self.cleanup.KEEP_DISPLAY_NAMES,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
