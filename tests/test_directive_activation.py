"""The directive-family registry: one authority, no silent defaults.

WO-LEAN-LORI-DIRECTIVE-ACTIVATION-01 (Lean Lori item 2), 2026-08-18.

Item 1 gave every prompt SECTION a declared policy, which left
`directives_interview` as a ~980-line required monolith containing many
independent instruction families. Because it is required, all of it is
protected from the budget; because it is one string, none of it is
diagnosable.

These tests pin the policy layer that makes the families separable. They
do NOT yet assert runtime activation -- that is the gating commit, and
the predicates named here are the inventory it works through.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.services import directive_activation as da   # noqa: E402

_MODULE = (_REPO / "server" / "code" / "api" / "services"
           / "directive_activation.py")

# The families the supervisor's work order names as concerns that must be
# separable. Written out so a family quietly disappearing fails here.
_REQUIRED_CONCERNS = {
    "interview_core", "session_style", "story_momentum", "thread_surfacing",
    "bio_anchored_ask", "witness_receipt", "era_explanation",
    "softened_response", "identity_mode", "profile_seed_walk",
    "pass_2a", "pass_2b", "current_mode", "cognitive_support",
    "paired_interview", "visual_affect", "fatigue", "media_hints",
}


class TheRegistryIsComplete(unittest.TestCase):
    def test_every_named_concern_is_a_separate_family(self):
        missing = _REQUIRED_CONCERNS - set(da.REGISTRY)
        self.assertEqual(set(), missing, f"not separable: {sorted(missing)}")

    def test_every_family_declares_the_full_policy_set(self):
        for fid in da.family_ids_in_render_order():
            with self.subTest(family=fid):
                f = da.family_for(fid)
                self.assertTrue(f.owner)
                self.assertTrue(f.activation)
                self.assertTrue(f.source)
                self.assertTrue(f.priority_tier)
                self.assertIsInstance(f.required, bool)
                self.assertIsInstance(f.render_order, int)

    def test_family_ids_are_unique_and_stable(self):
        ids = da.family_ids_in_render_order()
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), len(da.REGISTRY))

    def test_render_order_is_deterministic_and_unshared(self):
        orders = [da.family_for(f).render_order
                  for f in da.family_ids_in_render_order()]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(orders), len(set(orders)))


class TheProtectiveCoreStaysRequired(unittest.TestCase):
    """Making the whole section optional would be wrong.

    The interview discipline is what stops Lori reverting to a generic
    assistant, and the no-visual-claims rule is what stops "I can see...".
    Both must be required and unconditional.
    """

    def test_the_interview_discipline_is_required(self):
        f = da.family_for("interview_core")
        self.assertTrue(f.required)
        self.assertEqual("always", f.activation)

    def test_the_no_visual_claims_rule_is_required(self):
        f = da.family_for("no_visual_claims")
        self.assertTrue(f.required)
        self.assertEqual("always", f.activation)

    def test_the_visual_claim_ban_outlives_the_affect_family(self):
        """It must hold precisely when affect guidance is ABSENT, so it
        cannot share that family's condition."""
        ban = da.family_for("no_visual_claims")
        affect = da.family_for("visual_affect")
        self.assertTrue(ban.required)
        self.assertFalse(affect.required)
        self.assertNotEqual(ban.activation, affect.activation)

    def test_only_the_protective_core_is_required(self):
        self.assertEqual({"interview_core", "no_visual_claims"},
                         set(da.required_family_ids()))


class NothingDefaultsSilently(unittest.TestCase):
    def test_an_unknown_family_raises(self):
        with self.assertRaises(da.UnknownFamilyError):
            da.family_for("not_a_family")

    def test_the_error_says_what_to_do(self):
        try:
            da.family_for("not_a_family")
        except da.UnknownFamilyError as exc:
            msg = str(exc)
        self.assertIn("REGISTRY", msg)
        self.assertIn("activation predicate", msg)

    def test_an_unknown_activation_predicate_fails_at_build(self):
        bad = da.family_for("fatigue")._replace(activation="invented")
        with self.assertRaises(da.UnknownPredicateError):
            da._build([bad])

    def test_a_duplicate_family_fails_at_build(self):
        f = da.family_for("fatigue")
        with self.assertRaises(ValueError):
            da._build([f, f])

    def test_shared_render_orders_fail_at_build(self):
        a = da.family_for("fatigue")
        b = da.family_for("paired_interview")._replace(
            render_order=a.render_order)
        with self.assertRaises(ValueError):
            da._build([a, b])

    def test_a_required_family_cannot_be_conditional(self):
        """"Never withheld" and "only sometimes present" cannot both
        hold. A required family with a condition is a contradiction that
        would read as protection while behaving as a gate."""
        bad = da.family_for("interview_core")._replace(
            activation="fatigue_elevated")
        with self.assertRaises(ValueError):
            da._build([bad])


class TheProfileSeedWalkIsServerResolved(unittest.TestCase):
    """The live-only retirement rests on this predicate.

    A browser-supplied narrator type must never decide whether a live
    narrator receives a ten-question questionnaire walk.
    """

    def test_its_predicate_names_the_reference_narrator_condition(self):
        f = da.family_for("profile_seed_walk")
        self.assertEqual("pass1_and_reference_narrator", f.activation)

    def test_its_source_declares_the_database(self):
        f = da.family_for("profile_seed_walk")
        self.assertIn("db", f.source)

    def test_it_is_droppable_rather_than_protective(self):
        self.assertFalse(da.family_for("profile_seed_walk").required)


class TheModuleIsPurePolicy(unittest.TestCase):
    """It declares. It does not evaluate, render, or reach for state."""

    def test_it_imports_nothing_from_the_project(self):
        import ast
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, ("typing", "__future__"),
                              f"policy layer imports {node.module}")
            elif isinstance(node, ast.Import):
                for a in node.names:
                    self.assertIn(a.name, ("typing",),
                                  f"policy layer imports {a.name}")

    def test_it_does_not_decide_history_versus_section_trimming(self):
        """That is item 3, from measurement. A vocabulary that could
        express it here would invite someone to guess."""
        code = _MODULE.read_text(encoding="utf-8")
        for banned in ("before_history", "after_history", "history_first",
                       "drop_before_history", "prefer_history"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, code)


if __name__ == "__main__":
    unittest.main()
