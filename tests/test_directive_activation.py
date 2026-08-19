"""Directive families: executable gates, roles, and typed degradation.

WO-LEAN-LORI-DIRECTIVE-ACTIVATION-01 (Lean Lori item 2), 2026-08-18.

Lean Lori withholds instructions for INACTIVE states. It does not retire
product capabilities. These tests pin that distinction in the policy
layer:

  * a family may be absent because its feature is inactive;
  * it may NOT be absent merely because fewer tokens would be convenient;
  * `activation` decides presence, `required` decides whether the budget
    may remove it once present -- and a conditional family may be
    required;
  * a helper turn does not inherit interviewer-only directives;
  * the forbidden justification -- that the narrator can be asked again
    -- is not expressible, because degradation is a closed type rather
    than an English sentence.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.services import directive_activation as da        # noqa: E402
from api.services import directive_predicates as dp        # noqa: E402
from api.services import prompt_policy_vocab as voc        # noqa: E402

_MODULE = (_REPO / "server" / "code" / "api" / "services"
           / "directive_activation.py")

# Concerns the work order requires to be separately diagnosable.
_REQUIRED_CONCERNS = {
    "interview_core", "session_style", "story_mode", "question_hierarchy",
    "thread_surfacing", "bio_anchored_ask", "witness_receipt",
    "era_explanation", "softened_response", "identity_mode",
    "profile_seed_walk", "pass_2a", "pass_2b", "current_mode",
    "cognitive_support", "cognitive_variant", "paired_interview",
    "visual_affect", "fatigue", "media_hints",
    # Completed inventory.
    "runtime_state", "device_time", "narrator_location",
    "oral_history_posture",
}


class TheRegistryIsComplete(unittest.TestCase):
    def test_every_named_concern_is_a_separate_family(self):
        missing = _REQUIRED_CONCERNS - set(da.REGISTRY)
        self.assertEqual(set(), missing, f"not separable: {sorted(missing)}")

    def test_every_family_declares_the_full_policy_set(self):
        for fid in da.family_ids_in_render_order():
            with self.subTest(family=fid):
                f = da.family_for(fid)
                for field in ("owner", "capability", "activation", "source",
                              "priority_tier", "degradation"):
                    self.assertTrue(getattr(f, field), f"{fid}: no {field}")
                self.assertTrue(f.roles)
                self.assertIsInstance(f.required, bool)

    def test_ids_are_unique_and_render_order_is_total(self):
        ids = da.family_ids_in_render_order()
        self.assertEqual(len(ids), len(set(ids)))
        orders = [da.family_for(i).render_order for i in ids]
        self.assertEqual(orders, sorted(orders))
        self.assertEqual(len(orders), len(set(orders)))


class ActivationIsExecutable(unittest.TestCase):
    """A named predicate nobody runs is an inventory entry, not a gate.

    The first cut declared activation as a string and evaluated nothing
    -- the same shape as the `drop_order` that sat unread for a phase.
    """

    def test_every_declared_predicate_has_an_implementation(self):
        for fid in da.family_ids_in_render_order():
            with self.subTest(family=fid):
                self.assertIn(da.family_for(fid).activation, dp.PREDICATES)

    def test_the_registry_sources_its_predicate_set_from_the_implementations(self):
        self.assertEqual(set(dp.PREDICATES), set(da.ACTIVATION_PREDICATES))

    def test_an_unimplemented_predicate_fails_at_build(self):
        bad = da.family_for("fatigue")._replace(activation="invented")
        with self.assertRaises(da.UnknownPredicateError):
            da._build([bad])

    def test_every_predicate_has_positive_and_negative_coverage(self):
        """Both arms, for every gate. A predicate that can only ever
        answer one way is not a gate."""
        base = dp.build_turn_state({})
        on = dp.build_turn_state({
            "assistant_role": "helper", "current_pass": "pass2a",
            "current_mode": "recognition", "identity_mode": True,
            "identity_complete": True, "session_style": "clear_direct",
            "speaker_name": "Alex", "device_date": "2026-08-18",
            "location_label": "Corpus Christi", "media_count": 2,
            "memoir_state": "threads", "story_first_momentum_mode": "story",
            "story_first_thread_surface_text": "t",
            "bio_anchored_surface_text": "a", "witness_receipt_text": "w",
            "era_definition_requested": True, "softened_state": True,
            "cognitive_support_mode": True, "cognitive_mode": "alongside",
            "paired": True, "visual_baseline": True,
            "affect_state": "reflective", "fatigue_score": 80,
        }, unanswered_profile_topics=("siblings",), visual_fresh=True)
        # Mutually exclusive with the "everything on" state: a turn has
        # ONE role and ONE pass, so these need their own positive case.
        # Naming them is better than loosening the sweep, which would
        # stop proving the others.
        exclusive = {
            "role_onboarding": dp.build_turn_state(
                {"assistant_role": "onboarding"}),
            "pass_2b": dp.build_turn_state({"current_pass": "pass2b"}),
        }
        for pid in dp.PREDICATES:
            with self.subTest(predicate=pid):
                if pid in ("always", "runtime_present",
                           "session_style_default_oral"):
                    continue   # unconditional by design; covered below
                positive = exclusive.get(pid, on)
                self.assertTrue(dp.evaluate(pid, positive), f"{pid} never true")
                self.assertFalse(dp.evaluate(pid, base), f"{pid} never false")

    def test_the_default_style_predicate_is_the_inverse_of_the_override(self):
        oral = dp.build_turn_state({})
        styled = dp.build_turn_state({"session_style": "clear_direct"})
        self.assertTrue(dp.evaluate("session_style_default_oral", oral))
        self.assertFalse(dp.evaluate("session_style_non_default", oral))
        self.assertFalse(dp.evaluate("session_style_default_oral", styled))
        self.assertTrue(dp.evaluate("session_style_non_default", styled))

    def test_a_failing_predicate_is_inactive_rather_than_fatal(self):
        """A family included by accident is a narrator receiving an
        instruction nobody chose."""
        dp.PREDICATES["_boom"] = lambda s: 1 / 0
        try:
            self.assertFalse(dp.evaluate("_boom", dp.build_turn_state({})))
        finally:
            del dp.PREDICATES["_boom"]


class RolesBranchRatherThanInherit(unittest.TestCase):
    """A helper turn is not a quieter interview.

    Before this field the role blocks APPENDED and execution fell through
    into the interview passes, so a helper turn received the Profile Seed
    walk and the era-walk directives.
    """

    def test_a_helper_turn_never_considers_interviewer_only_families(self):
        helper = set(da.families_for_role(voc.ROLE_HELPER))
        for interviewer_only in ("profile_seed_walk", "pass_2a", "pass_2b",
                                 "era_explanation", "story_mode",
                                 "question_hierarchy", "session_style",
                                 "oral_history_posture", "witness_receipt"):
            with self.subTest(family=interviewer_only):
                self.assertNotIn(interviewer_only, helper)

    def test_the_helper_family_belongs_only_to_the_helper_role(self):
        self.assertEqual({voc.ROLE_HELPER},
                         set(da.family_for("role_helper").roles))

    def test_onboarding_keeps_identity_collection_but_not_the_passes(self):
        ob = set(da.families_for_role(voc.ROLE_ONBOARDING))
        self.assertIn("identity_mode", ob)
        self.assertIn("role_onboarding", ob)
        self.assertNotIn("profile_seed_walk", ob)
        self.assertNotIn("pass_2a", ob)

    def test_the_protective_core_belongs_to_every_role(self):
        for fid in ("interview_core", "no_visual_claims", "runtime_state"):
            with self.subTest(family=fid):
                self.assertEqual(voc.ROLES, set(da.family_for(fid).roles))

    def test_an_unknown_role_fails_at_build(self):
        bad = da.family_for("fatigue")._replace(roles=frozenset({"wizard"}))
        with self.assertRaises(ValueError):
            da._build([bad])


class CapabilitiesAreNotExpendable(unittest.TestCase):
    def test_most_families_are_protected_once_active(self):
        protected = [f for f in da.REGISTRY.values() if f.required]
        self.assertGreater(len(protected), len(da.REGISTRY) // 2)

    def test_a_conditional_family_may_be_required(self):
        both = [f for f in da.REGISTRY.values()
                if f.required and f.activation != "always"]
        self.assertTrue(both, "the two words have been conflated again")
        da._build([da.family_for("role_helper")])

    def test_an_evidence_bearing_family_may_not_be_droppable(self):
        bad = da.family_for("witness_receipt")._replace(
            required=False, degradation=voc.DEGRADE_COSMETIC)
        with self.assertRaises(ValueError):
            da._build([bad])

    def test_a_required_family_declares_no_degradation(self):
        bad = da.family_for("role_helper")._replace(
            degradation=voc.DEGRADE_COSMETIC)
        with self.assertRaises(ValueError):
            da._build([bad])

    def test_a_droppable_family_must_name_a_typed_degradation(self):
        bad = da.family_for("thread_surfacing")._replace(
            degradation=voc.DEGRADE_NONE)
        with self.assertRaises(ValueError):
            da._build([bad])


class TheNarratorIsNotTheRecoveryMechanism(unittest.TestCase):
    """Enforced by TYPE, not by scanning English.

    A substring ban fired twice on prose arguing AGAINST the rationale it
    forbade. The degradation is now drawn from a closed set that simply
    does not contain "ask the narrator again", so it cannot be smuggled
    in and no scanner is needed.
    """

    def test_the_forbidden_rationale_is_not_a_member_of_the_type(self):
        for d in voc.DEGRADATIONS:
            with self.subTest(degradation=d):
                self.assertNotIn("ask", d)
                self.assertNotIn("narrator", d)

    def test_every_droppable_family_names_a_durable_or_free_source(self):
        for f in da.REGISTRY.values():
            if not f.required:
                with self.subTest(family=f.family_id):
                    self.assertIn(f.degradation, voc.DROPPABLE_DEGRADATIONS)

    def test_an_invented_degradation_fails_at_build(self):
        bad = da.family_for("thread_surfacing")._replace(
            degradation="narrator_can_be_asked_again")
        with self.assertRaises(ValueError):
            da._build([bad])


class TheProfileSeedWalkIsPreserved(unittest.TestCase):
    """The ten-topic new-narrator walk stays.

    It is the only conversational filler for the nine `profile_seed`
    buckets, and a new Lorevox narrator may have no operator to seed
    them.
    """

    def test_narrator_type_decides_nothing(self):
        self.assertEqual("profile_walk_active",
                         da.family_for("profile_seed_walk").activation)
        joined = " ".join(dp.PREDICATES)
        self.assertNotIn("reference", joined)
        self.assertNotIn("narrator_type", joined)
        self.assertNotIn("narrator_type", dp.TurnState._fields)

    def test_it_activates_on_incomplete_onboarding(self):
        active = dp.build_turn_state(
            {"identity_complete": True},
            unanswered_profile_topics=("siblings", "military"))
        self.assertTrue(dp.evaluate("profile_walk_active", active))

    def test_it_stops_when_onboarding_is_complete(self):
        done = dp.build_turn_state(
            {"identity_complete": True},
            unanswered_profile_topics=(),
            profile_onboarding_complete=True)
        self.assertFalse(dp.evaluate("profile_walk_active", done))

    def test_it_does_not_start_before_identity_is_complete(self):
        early = dp.build_turn_state(
            {"identity_complete": False},
            unanswered_profile_topics=("siblings",))
        self.assertFalse(dp.evaluate("profile_walk_active", early))

    def test_it_does_not_end_after_a_single_topic(self):
        """"Do not terminate after one bucket becomes populated."""
        still_going = dp.build_turn_state(
            {"identity_complete": True},
            unanswered_profile_topics=("military",))
        self.assertTrue(dp.evaluate("profile_walk_active", still_going))

    def test_it_is_required_and_evidence_bearing(self):
        f = da.family_for("profile_seed_walk")
        self.assertTrue(f.required)
        self.assertTrue(f.affects_evidence)
        self.assertEqual(voc.DEGRADE_NONE, f.degradation)


class ActivationIsNarrow(unittest.TestCase):
    """Stored data is not an active task."""

    def test_archived_media_alone_does_not_activate_photo_instructions(self):
        nothing_in_view = dp.build_turn_state({"media_count": 0})
        self.assertFalse(dp.evaluate("media_in_view", nothing_in_view))

    def test_media_in_view_does_activate_them(self):
        in_view = dp.build_turn_state({"media_count": 3})
        self.assertTrue(dp.evaluate("media_in_view", in_view))

    def test_stale_visual_evidence_produces_nothing(self):
        stale = dp.build_turn_state(
            {"visual_baseline": True, "affect_state": "reflective"},
            visual_fresh=False)
        self.assertFalse(dp.evaluate("visual_affect_fresh", stale))

    def test_affect_without_a_baseline_produces_nothing(self):
        no_base = dp.build_turn_state({"affect_state": "reflective"},
                                      visual_fresh=True)
        self.assertFalse(dp.evaluate("visual_affect_fresh", no_base))

    def test_the_visual_claim_ban_holds_when_affect_is_absent(self):
        ban = da.family_for("no_visual_claims")
        self.assertTrue(ban.required)
        self.assertEqual("always", ban.activation)
        self.assertNotEqual(ban.activation,
                            da.family_for("visual_affect").activation)


class OneAuthorityForTheVocabulary(unittest.TestCase):
    """Two registries, one set of words.

    Both had begun declaring their own tiers, which is two authorities
    for one concept and the start of the drift this lane removes.
    """

    def test_the_family_registry_imports_the_shared_vocabulary(self):
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        modules = {n.module for n in ast.walk(tree)
                   if isinstance(n, ast.ImportFrom)}
        self.assertIn("prompt_policy_vocab", modules)

    def test_it_declares_no_tier_or_source_constants_of_its_own(self):
        src = _MODULE.read_text(encoding="utf-8")
        code = "\n".join(l for l in src.splitlines()
                         if not l.lstrip().startswith("#"))
        for own in ("TIER_DISCIPLINE = ", "SOURCE_STATIC = ",
                    "DEGRADE_NONE = "):
            with self.subTest(constant=own):
                self.assertNotIn(own, code)

    def test_the_section_registry_uses_the_same_vocabulary(self):
        from api.services import prompt_section_policy as sp
        self.assertTrue(set(sp._TIERS) <= voc.TIERS)


if __name__ == "__main__":
    unittest.main()
