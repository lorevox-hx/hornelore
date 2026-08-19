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

    def test_only_the_protective_core_is_unconditional(self):
        """CORRECTED 2026-08-18. This read:

            self.assertEqual({"interview_core", "no_visual_claims"},
                             set(da.required_family_ids()))

        which was true only while `required` wrongly implied
        `always`. Under the corrected semantics 20 families are required
        once active. What is still exactly two is the set that is present
        on EVERY turn regardless of state -- the interview discipline and
        the ban on unevidenced visual claims.
        """
        unconditional = {f.family_id for f in da.REGISTRY.values()
                         if f.activation == "always"}
        self.assertEqual({"interview_core", "no_visual_claims"}, unconditional)

    def test_most_families_are_protected_once_their_feature_is_active(self):
        """The philosophical correction, stated as a count.

        Lean Lori withholds instructions for INACTIVE states. It does not
        make active capabilities expendable. If this number collapses
        toward two, someone has gone back to treating 'optional' as
        'expendable'.
        """
        protected = [f for f in da.REGISTRY.values() if f.required]
        self.assertGreater(len(protected), len(da.REGISTRY) // 2)
        # And every unprotected one has said exactly how it degrades.
        for f in da.REGISTRY.values():
            if not f.required:
                with self.subTest(family=f.family_id):
                    self.assertTrue(f.degradation)
                    self.assertFalse(f.affects_evidence)

    def test_no_degradation_is_justified_by_re_asking_the_narrator(self):
        """Lorevox's purpose forbids it.

        An older narrator is not a recoverable storage device. A section
        may be safe to drop because its source is DURABLE on the server,
        never because the person could be made to say it again.
        """
        for f in da.REGISTRY.values():
            with self.subTest(family=f.family_id):
                text = (f.degradation + " " + f.note).lower()
                for banned in ("asked again", "ask again", "re-ask",
                               "repeat it", "narrator can always"):
                    self.assertNotIn(banned, text)


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

    def test_a_conditional_family_may_be_required(self):
        """INVERTED 2026-08-18, and the inversion is the point.

        This asserted the opposite -- that a required family could not be
        conditional -- and that conflated two independent words:

            activation  decides whether the family is PRESENT
            required    decides whether the budget may REMOVE it

        A helper turn's guidance is both: conditional, because it appears
        only in the helper role, and required, because a helper turn that
        silently loses it does not become a shorter helper turn, it
        becomes an interview.

        The retired assertion read:

            bad = da.family_for("interview_core")._replace(
                activation="fatigue_elevated")
            with self.assertRaises(ValueError):
                da._build([bad])
        """
        conditional_and_required = [
            f for f in da.REGISTRY.values()
            if f.required and f.activation != "always"
        ]
        self.assertTrue(conditional_and_required,
                        "no family is both conditional and protected, which "
                        "means the two words have been conflated again")
        # And the build accepts one, rather than rejecting it as before.
        ok = da.family_for("role_helper")
        self.assertTrue(ok.required)
        self.assertNotEqual("always", ok.activation)
        da._build([ok])

    def test_a_droppable_family_must_name_its_degradation(self):
        """A loss nobody described is a loss nobody can observe."""
        bad = da.family_for("thread_surfacing")._replace(degradation="")
        with self.assertRaises(ValueError):
            da._build([bad])

    def test_an_evidence_bearing_family_may_not_be_droppable(self):
        """Dropping it could change what is persisted or attributed, and
        that is not a degradation, it is a wrong record."""
        bad = da.family_for("witness_receipt")._replace(
            required=False, degradation="some words")
        with self.assertRaises(ValueError):
            da._build([bad])

    def test_a_required_family_has_no_degradation(self):
        """It is kept, or the turn refuses. There is no middle."""
        bad = da.family_for("role_helper")._replace(degradation="quietly skip")
        with self.assertRaises(ValueError):
            da._build([bad])

    def test_every_family_records_the_capability_it_supports(self):
        for fid in da.family_ids_in_render_order():
            with self.subTest(family=fid):
                self.assertTrue(da.family_for(fid).capability)


class TheProfileSeedWalkIsPreserved(unittest.TestCase):
    """The ten-topic new-narrator walk stays. The retirement was wrong.

    It is the ONLY conversational filler for the nine `profile_seed`
    buckets -- childhood_home, parents_work, heritage, education,
    military, career, partner, children, life_stage. Everything else that
    populates them is operator-side: the intake form, Bio Builder,
    template preload. That is sufficient in Hornelore, where the operator
    knows the narrator. It is not sufficient in Lorevox, where a new
    narrator may have no operator at all, and where retiring the walk
    would leave those buckets permanently empty and Lori's readback
    permanently "(not on record yet)".
    """

    def test_the_walk_still_exists(self):
        self.assertIn("profile_seed_walk", da.REGISTRY)

    def test_narrator_type_does_not_decide_whether_it_exists(self):
        """The retired predicate was `pass1_and_reference_narrator`,
        which made the walk a property of who the narrator IS rather than
        of what is still unknown about them."""
        f = da.family_for("profile_seed_walk")
        self.assertEqual("profile_walk_active", f.activation)
        self.assertNotIn("reference", f.activation)
        self.assertNotIn("reference", "".join(da.ACTIVATION_PREDICATES))

    def test_it_is_required_once_active(self):
        """An onboarding turn that loses its walk asks nothing and
        records nothing."""
        f = da.family_for("profile_seed_walk")
        self.assertTrue(f.required)
        self.assertEqual("", f.degradation)

    def test_it_is_evidence_bearing(self):
        self.assertTrue(da.family_for("profile_seed_walk").affects_evidence)

    def test_its_capability_is_named_as_the_walk(self):
        cap = da.family_for("profile_seed_walk").capability
        self.assertIn("ten-topic", cap)


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
