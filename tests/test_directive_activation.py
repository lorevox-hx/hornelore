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
    "interview_core", "story_mode", "question_hierarchy",
    "thread_surfacing", "bio_anchored_ask", "witness_receipt",
    "era_explanation", "softened_response", "identity_mode",
    "profile_seed_walk", "pass_2a", "pass_2b", "current_mode",
    "cognitive_support", "cognitive_variant", "paired_interview",
    "visual_affect", "fatigue", "media_hints",
    # Completed inventory.
    "runtime_state", "device_time", "narrator_location",
    "oral_history_posture", "capabilities_honesty", "transparency_rule",
}


# ── composer-shaped state ───────────────────────────────────────────────
# Tests build state the way the COMPOSER hands it over -- already
# normalised -- not the way the browser sends it. The payload shape is
# the composer's problem and is proven at the consumer boundary; mixing
# the two here is what produced an adapter that read five nested
# contexts as flat keys.
_STATE_DEFAULTS = dict(
    assistant_role="interviewer", current_pass="", effective_pass="",
    current_era="not yet set", current_mode="open", identity_mode=False,
    identity_complete=True, identity_phase="unknown", session_style="",
    style_directive="", speaker_name="", device_date="", device_time="",
    location_label="", media_count=0, memoir_state="empty",
    story_momentum="", thread_surface="", anchored_surface="",
    witness_block=False, era_definition_requested=False,
    softened_state=False, softened_parked=False,
    cognitive_support_mode=False, cognitive_mode="", paired=False,
    visual_baseline=False, visual_affect="", visual_gaze=None,
    fatigue_score=0,
)


def _state(**overrides):
    kw = dict(_STATE_DEFAULTS)
    kw.update(overrides)
    return dp.state_from_composer(**kw)


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
        base = _state()
        on = _state(
            assistant_role="helper", current_pass="pass2a",
            current_mode="recognition", identity_mode=True,
            session_style="clear_direct", style_directive="be honest",
            speaker_name="Alex", device_date="2026-08-18",
            location_label="Corpus Christi", media_count=2,
            memoir_state="threads", story_momentum="story",
            thread_surface="t", anchored_surface="a", witness_block=True,
            era_definition_requested=True, softened_state=True,
            cognitive_support_mode=True, cognitive_mode="alongside",
            paired=True, visual_baseline=True, visual_affect="reflective",
            fatigue_score=80)
        # Mutually exclusive with the "everything on" state: a turn has
        # ONE role and ONE pass, so these need their own positive case.
        # Some pairs cannot both hold: a turn has ONE role and ONE pass,
        # identity mode excludes the pass directives, and full cognitive
        # support excludes the variants. Each needs its own positive
        # state. Naming them is better than loosening the sweep, which
        # would stop proving the rest.
        exclusive = {
            "role_onboarding": _state(assistant_role="onboarding"),
            "role_interviewer": _state(assistant_role="interviewer"),
            "pass_2a": _state(current_pass="pass2a", identity_mode=False),
            "pass_2b": _state(current_pass="pass2b", identity_mode=False),
            "profile_walk_pass1": _state(current_pass="pass1",
                                         identity_mode=False),
            "cognitive_variant_set": _state(cognitive_mode="alongside",
                                            cognitive_support_mode=False),
            "session_style_default_oral": _state(session_style=""),
        }
        for pid in dp.PREDICATES:
            with self.subTest(predicate=pid):
                if pid == "always":
                    continue   # unconditional by design
                positive = exclusive.get(pid, on)
                self.assertTrue(dp.evaluate(pid, positive), f"{pid} never true")
                negative = base
                if pid in ("session_style_default_oral", "role_interviewer"):
                    negative = _state(session_style="companion",
                                      assistant_role="helper")
                self.assertFalse(dp.evaluate(pid, negative), f"{pid} never false")

    def test_companion_is_a_non_oral_style(self):
        """It was missing from the first cut's set, and `guided_trip_walk`
        -- which the composer has never had -- was invented. The set is
        now read from the composer."""
        self.assertIn("companion", dp.NON_ORAL_STYLES)
        self.assertNotIn("guided_trip_walk", dp.NON_ORAL_STYLES)
        self.assertFalse(dp.evaluate("session_style_default_oral",
                                     _state(session_style="companion")))

    def test_an_unknown_style_falls_through_to_the_oral_posture(self):
        """The composer's own behaviour: unrecognised styles get the
        default posture rather than nothing."""
        self.assertTrue(dp.evaluate("session_style_default_oral",
                                    _state(session_style="invented_style")))

    def test_a_failing_predicate_is_inactive_rather_than_fatal(self):
        """A family included by accident is a narrator receiving an
        instruction nobody chose."""
        dp.PREDICATES["_boom"] = lambda s: 1 / 0
        try:
            self.assertFalse(dp.evaluate("_boom", _state()))
        finally:
            del dp.PREDICATES["_boom"]


class RolesMirrorTheComposersEarlyReturns(unittest.TestCase):
    """Helper and onboarding each build a section and RETURN.

    The composer says so itself: "Helper and onboarding roles completely
    replace the interview directives. They return early from the
    directive block so no pass/era/mode rules fire."

    An earlier draft modelled them as appending blocks that fell through
    into the interview material. They do not, and the correction matters
    in both directions: the interviewer tail is larger than it looked,
    and the shared prelude is the ONLY thing helper and onboarding get
    besides their own block.
    """

    SHARED_PRELUDE = ["runtime_state", "device_time", "narrator_location",
                      "memoir_arc", "speaker_name", "capabilities_honesty",
                      "media_hints", "transparency_rule"]

    def test_the_shared_prelude_reaches_every_role(self):
        for role in voc.ROLES:
            with self.subTest(role=role):
                fams = da.families_for_role(role)
                for fid in self.SHARED_PRELUDE:
                    self.assertIn(fid, fams)

    def test_helper_gets_the_prelude_plus_only_its_own_block(self):
        self.assertEqual(self.SHARED_PRELUDE + ["role_helper"],
                         da.families_for_role(voc.ROLE_HELPER))

    def test_onboarding_gets_the_prelude_plus_only_its_own_block(self):
        self.assertEqual(self.SHARED_PRELUDE + ["role_onboarding"],
                         da.families_for_role(voc.ROLE_ONBOARDING))

    def test_the_entire_interviewer_tail_is_interviewer_only(self):
        """Including the interview discipline and the visual-claims ban,
        which an earlier draft wrongly marked universal."""
        for fid in ("interview_core", "no_visual_claims", "softened_response",
                    "identity_mode", "cognitive_support", "cognitive_variant",
                    "paired_interview", "visual_affect", "fatigue",
                    "profile_seed_walk", "pass_2a", "pass_2b",
                    "era_explanation", "oral_history_posture"):
            with self.subTest(family=fid):
                self.assertEqual({voc.ROLE_INTERVIEWER},
                                 set(da.family_for(fid).roles))

    def test_onboarding_does_not_reach_the_later_identity_mode_block(self):
        """It returns before it. Its own block collects the anchors."""
        ob = da.families_for_role(voc.ROLE_ONBOARDING)
        self.assertIn("role_onboarding", ob)
        self.assertNotIn("identity_mode", ob)

    def test_render_order_places_the_prelude_before_the_role_blocks(self):
        order = {f: da.family_for(f).render_order
                 for f in da.family_ids_in_render_order()}
        latest_prelude = max(order[f] for f in self.SHARED_PRELUDE)
        self.assertLess(latest_prelude, order["role_helper"])
        self.assertLess(latest_prelude, order["role_onboarding"])
        self.assertLess(order["role_onboarding"], order["interview_core"])

    def test_interview_core_follows_the_prelude_not_precedes_it(self):
        """It was registered at order 10, before location, memoir,
        speaker, style and media. The composer emits it after all of
        them."""
        order = da.family_for("interview_core").render_order
        for earlier in self.SHARED_PRELUDE:
            with self.subTest(family=earlier):
                self.assertLess(da.family_for(earlier).render_order, order)

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
    """The ten-topic new-narrator walk stays, and its TRIGGER is unchanged.

    It is the only conversational filler for the nine `profile_seed`
    buckets, and a new Lorevox narrator may have no operator to seed
    them.

    An earlier draft gated it on "onboarding incomplete AND topics
    remain". No production caller computes either value, and the browser
    promotes `pass1 -> pass2a` once chronology is ready -- so that gate
    would have depended on inputs nobody supplies. The existing trigger
    is preserved exactly and the reachability gap is recorded as a debt.
    """

    def test_narrator_type_decides_nothing(self):
        self.assertEqual("profile_walk_pass1",
                         da.family_for("profile_seed_walk").activation)
        joined = " ".join(dp.PREDICATES)
        self.assertNotIn("reference", joined)
        self.assertNotIn("narrator_type", joined)
        self.assertNotIn("narrator_type", dp.TurnState._fields)

    def test_the_trigger_is_unchanged_from_the_composer(self):
        self.assertTrue(dp.evaluate("profile_walk_pass1",
                                    _state(current_pass="pass1")))
        for other in ("pass2a", "pass2b", "identity", ""):
            with self.subTest(current_pass=other):
                self.assertFalse(dp.evaluate("profile_walk_pass1",
                                             _state(current_pass=other)))

    def test_it_does_not_auto_activate_for_historical_incomplete_profiles(self):
        """Starting a ten-topic questionnaire for every narrator with a
        profile gap is interrogation, not onboarding."""
        self.assertFalse(dp.evaluate("profile_walk_pass1",
                                     _state(current_pass="pass2a",
                                            identity_complete=False)))

    def test_the_reachability_debt_is_recorded_not_papered_over(self):
        note = da.family_for("profile_seed_walk").note
        self.assertIn("DEBT", note.upper())
        self.assertIn("pass2a", note)
        src = (_REPO / "server" / "code" / "api" / "services"
               / "directive_predicates.py").read_text(encoding="utf-8")
        self.assertIn("REACHABILITY DEBT", src)

    def test_it_is_required_and_evidence_bearing(self):
        f = da.family_for("profile_seed_walk")
        self.assertTrue(f.required)
        self.assertTrue(f.affects_evidence)
        self.assertEqual(voc.DEGRADE_NONE, f.degradation)


class MediaCountIsNotAnInViewSignal(unittest.TestCase):
    """`media_count` is the narrator's TOTAL uploaded photo count.

    An earlier draft renamed the predicate `media_in_view`, which would
    have claimed a turn-scoped signal the payload does not carry -- and
    would have silently removed a hint that fires today. Behaviour is
    preserved; narrowing it needs a real in-view signal first.
    """

    def test_the_predicate_is_not_named_as_an_in_view_signal(self):
        self.assertIn("media_present", dp.PREDICATES)
        self.assertNotIn("media_in_view", dp.PREDICATES)

    def test_it_fires_on_any_uploaded_media_exactly_as_before(self):
        self.assertTrue(dp.evaluate("media_present", _state(media_count=1)))
        self.assertFalse(dp.evaluate("media_present", _state(media_count=0)))

    def test_the_registry_records_that_it_is_a_total_not_a_view(self):
        note = da.family_for("media_hints").note
        self.assertIn("TOTAL", note)


class VisualAffectMatchesTheComposerCondition(unittest.TestCase):
    def test_it_requires_a_baseline_and_a_reading(self):
        self.assertTrue(dp.evaluate("visual_affect_emits",
                                    _state(visual_baseline=True,
                                           visual_affect="reflective")))
        self.assertFalse(dp.evaluate("visual_affect_emits",
                                     _state(visual_affect="reflective")))
        self.assertFalse(dp.evaluate("visual_affect_emits",
                                     _state(visual_baseline=True)))

    def test_no_freshness_signal_is_invented(self):
        self.assertNotIn("visual_fresh", dp.TurnState._fields)
        self.assertNotIn("visual_affect_fresh", dp.PREDICATES)

    def test_it_matches_actual_emission_not_the_outer_guard(self):
        """`v_baseline and v_affect` is the OUTER guard. The inner ladder
        emits for distressed/overwhelmed with eligible gaze, for
        reflective/moved, or for gaze explicitly off -- and nothing else.
        A neutral affect with gaze on screen renders no block."""
        cases = [
            ("neutral", True, False),      # passes the guard, emits nothing
            ("neutral", None, False),
            ("neutral", False, True),      # gaze explicitly off
            ("reflective", True, True),
            ("moved", None, True),
            ("distressed", True, True),
            ("distressed", False, True),   # falls to the gaze-off arm
            ("overwhelmed", False, True),
        ]
        for affect, gaze, expected in cases:
            with self.subTest(affect=affect, gaze=gaze):
                st = _state(visual_baseline=True, visual_affect=affect,
                            visual_gaze=gaze)
                self.assertEqual(expected,
                                 dp.evaluate("visual_affect_emits", st))

    def test_the_visual_claim_ban_holds_when_affect_is_absent(self):
        ban = da.family_for("no_visual_claims")
        self.assertTrue(ban.required)
        self.assertEqual("always", ban.activation)
        self.assertNotEqual(ban.activation,
                            da.family_for("visual_affect").activation)


class TheEvaluatedAssembly(unittest.TestCase):
    """Role eligibility AND predicate, in one place."""

    def test_an_ordinary_ready_turn_omits_inactive_families(self):
        active = {f.family_id for f in da.active_families(_state())}
        for inactive in ("era_explanation", "witness_receipt", "story_mode",
                         "paired_interview", "visual_affect", "fatigue",
                         "cognitive_support", "pass_2a", "pass_2b",
                         "softened_response", "media_hints"):
            with self.subTest(family=inactive):
                self.assertNotIn(inactive, active)

    def test_an_ordinary_ready_turn_keeps_the_protective_core(self):
        active = {f.family_id for f in da.active_families(_state())}
        for core in ("runtime_state", "interview_core", "transparency_rule",
                     "no_visual_claims", "oral_history_posture"):
            with self.subTest(family=core):
                self.assertIn(core, active)

    def test_a_helper_turn_gets_helper_guidance_and_no_interview_tail(self):
        active = {f.family_id
                  for f in da.active_families(_state(assistant_role="helper"))}
        self.assertIn("role_helper", active)
        self.assertIn("transparency_rule", active)
        for tail in ("interview_core", "profile_seed_walk", "pass_2a",
                     "no_visual_claims", "oral_history_posture"):
            with self.subTest(family=tail):
                self.assertNotIn(tail, active)

    def test_each_active_family_appears_exactly_once(self):
        ids = [f.family_id for f in da.active_families(_state())]
        self.assertEqual(len(ids), len(set(ids)))

    def test_active_families_come_back_in_render_order(self):
        orders = [f.policy.render_order for f in da.active_families(_state())]
        self.assertEqual(orders, sorted(orders))

    def test_inactive_is_distinguished_from_role_ineligible(self):
        """'your feature is off' and 'this is not that conversation' are
        different answers."""
        helper = _state(assistant_role="helper")
        inactive = set(da.inactive_families(helper))
        self.assertNotIn("pass_2a", inactive)      # role-ineligible, not inactive
        self.assertIn("media_hints", inactive)     # eligible, condition false

    def test_an_active_capability_is_present_exactly_once(self):
        active = [f.family_id for f in
                  da.active_families(_state(era_definition_requested=True))]
        self.assertEqual(1, active.count("era_explanation"))


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


class MutuallyExclusiveBranches(unittest.TestCase):
    """The composer uses `if/elif`. Two arms can never both render.

    Activating both would put a ten-topic questionnaire beside an
    identity question on one turn -- two jobs at once and neither done.
    """

    def test_identity_mode_excludes_the_profile_seed_walk(self):
        st = _state(current_pass="pass1", identity_mode=True,
                    identity_complete=False)
        active = {f.family_id for f in da.active_families(st)}
        self.assertIn("identity_mode", active)
        self.assertNotIn("profile_seed_walk", active)

    def test_identity_mode_excludes_both_era_passes(self):
        for p in ("pass2a", "pass2b"):
            with self.subTest(current_pass=p):
                st = _state(current_pass=p, identity_mode=True)
                active = {f.family_id for f in da.active_families(st)}
                self.assertIn("identity_mode", active)
                self.assertNotIn(f"pass_{p[-2:]}", active)

    def test_the_walk_remains_for_an_identity_complete_pass1_turn(self):
        """The preserved path. The exclusion must not delete it."""
        st = _state(current_pass="pass1", identity_mode=False,
                    identity_complete=True)
        active = {f.family_id for f in da.active_families(st)}
        self.assertIn("profile_seed_walk", active)
        self.assertNotIn("identity_mode", active)

    def test_full_cognitive_support_excludes_the_variants(self):
        st = _state(cognitive_support_mode=True, cognitive_mode="alongside")
        active = {f.family_id for f in da.active_families(st)}
        self.assertIn("cognitive_support", active)
        self.assertNotIn("cognitive_variant", active)

    def test_a_variant_renders_when_full_support_is_off(self):
        st = _state(cognitive_mode="recognition")
        active = {f.family_id for f in da.active_families(st)}
        self.assertIn("cognitive_variant", active)
        self.assertNotIn("cognitive_support", active)


class UnknownRolesKeepCurrentBehaviour(unittest.TestCase):
    """The composer treats anything but helper/onboarding as interviewer.

    Preserving an unexpected value would make `active_families` return
    nothing -- a silently empty prompt, worse than the behaviour it
    replaces.
    """

    def test_an_unexpected_role_normalises_to_interviewer(self):
        for weird in ("wizard", "", None, "INTERVIEWER", " helper "):
            with self.subTest(role=weird):
                st = _state(assistant_role=weird)
                self.assertIn(st.role, ("interviewer", "helper"))
                self.assertTrue(da.active_families(st),
                                "an unknown role produced an empty prompt")

    def test_an_unknown_role_gets_the_full_interviewer_path(self):
        active = {f.family_id
                  for f in da.active_families(_state(assistant_role="wizard"))}
        self.assertIn("interview_core", active)
        self.assertIn("no_visual_claims", active)


class StyleGuidanceStaysDiagnosable(unittest.TestCase):
    """companion and clear_direct guidance lives INSIDE the combined
    capabilities-honesty block. It must not disappear into a family
    described only as honesty."""

    def test_the_active_style_is_exposed_in_diagnostics(self):
        for style in ("companion", "clear_direct"):
            with self.subTest(style=style):
                st = _state(session_style=style, style_directive="honesty + s")
                fam = [f for f in da.active_families(st)
                       if f.family_id == "capabilities_honesty"]
                self.assertEqual(1, len(fam))
                self.assertEqual(style, fam[0].style)

    def test_the_default_path_reports_no_operator_style(self):
        """Reporting "oral_history" would imply a choice nobody made."""
        st = _state(session_style="", style_directive="honesty only")
        fam = [f for f in da.active_families(st)
               if f.family_id == "capabilities_honesty"][0]
        self.assertEqual("", fam.style)

    def test_a_non_oral_style_suppresses_the_oral_posture(self):
        st = _state(session_style="companion", style_directive="h")
        active = {f.family_id for f in da.active_families(st)}
        self.assertNotIn("oral_history_posture", active)
        self.assertIn("capabilities_honesty", active)

    def test_the_registry_declares_the_block_as_combined(self):
        note = da.family_for("capabilities_honesty").note
        self.assertIn("COMBINED", note)
        self.assertIn("companion", note)
