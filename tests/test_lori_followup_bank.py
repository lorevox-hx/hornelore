"""WO-LORI-WITNESS-FOLLOWUP-BANK-01 — unit tests.

Pure-stdlib tests for the door detector, immediate-vs-bank selector,
flush triggers, and flush composer. No DB writes — that's covered by
integration tests against the live api.

Tests are organized to match the locked priority hierarchy:

  1. Fragile-name confirms (immediate, priority 1)
  2. Communication / logistics (priority 2)
  3. Role transition mechanism (priority 3)
  4. Relationship / personality (BANK ONLY, never immediate)
  5. Daily life / off-duty (BANK ONLY)
  6. Medical / family (BANK ONLY)

Plus selector / flush-trigger / flush-composer behavior tests.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import lori_followup_bank as bank  # noqa: E402


# ── Section 1: Door detector — priority 1 fragile-name confirms ────────────


class FragileNameDetectorTests(unittest.TestCase):
    """Priority 1 — must surface immediately. Two-tier rule:
       TIER A (always-fragile foreign/record-critical): Landstuhl,
         Ramstein, Kaiserslautern, Schmick, 32nd Brigade, etc.
       TIER B (conditionally-fragile common American): Stanley,
         Fargo, Bismarck — fire ONLY when narrator signals
         uncertainty or self-corrects.
    """

    # Tier A — always fires on first appearance
    def test_landstuhl_in_kent_text_opens_door(self):
        text = (
            "Vince was born at Landstuhl Air Force Hospital, "
            "connected with Ramstein Air Force Base."
        )
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(
            any("landstuhl" in i for i in intents),
            f"expected landstuhl door; got {intents}"
        )

    def test_self_correction_pattern_opens_door(self):
        text = "It was not Lansdale Army Hospital. It was Landstuhl Air Force Hospital."
        doors = bank.detect_doors(text)
        labels = [d.intent for d in doors]
        # Either the self-correction OR the fragile-name match should fire
        self.assertTrue(
            any("fragile_name_confirm" in i for i in labels),
            f"expected fragile-name door; got {labels}"
        )

    def test_kaiserslautern_fires(self):
        text = "We were stationed in Kaiserslautern when Vince was born."
        doors = bank.detect_doors(text)
        self.assertTrue(any("kaiserslautern" in d.intent for d in doors))

    def test_schmick_fires(self):
        text = "I worked for General Peter Schmick, a Canadian-born officer."
        doors = bank.detect_doors(text)
        self.assertTrue(any("schmick" in d.intent for d in doors))

    def test_no_fragile_name_no_priority1_door(self):
        text = "I went to school in town and graduated in 1956."
        doors = bank.detect_doors(text)
        priority1 = [d for d in doors if d.priority == 1]
        self.assertEqual(priority1, [])

    # Tier B — must NOT fire on bare appearance (Chris's 2026-05-10
    # refinement: "Do not confirm ordinary known places every time.")
    def test_stanley_alone_does_not_open_priority1(self):
        """Kent's TEST-B opening: 'I went to the depot in Stanley'.
        Stanley is a common American place name — no fragile-confirm
        door should fire just because it appears."""
        text = (
            "I went down to the railroad depot in Stanley with my dad. "
            "From Stanley I went by train to Fargo for the induction."
        )
        doors = bank.detect_doors(text)
        priority1 = [d for d in doors if d.priority == 1]
        self.assertEqual(
            priority1, [],
            f"Stanley alone should not fire fragile-confirm door; got {priority1}"
        )

    def test_fargo_alone_does_not_open_priority1(self):
        text = "I scored high on the qualifying tests in Fargo."
        doors = bank.detect_doors(text)
        priority1 = [d for d in doors if d.priority == 1]
        self.assertEqual(priority1, [])

    def test_bismarck_alone_does_not_open_priority1(self):
        text = "I came home to Bismarck for the wedding."
        doors = bank.detect_doors(text)
        priority1 = [d for d in doors if d.priority == 1]
        self.assertEqual(priority1, [])

    # Tier B + uncertainty marker — DOES fire
    def test_stanley_with_uncertainty_opens_door(self):
        """When narrator volunteers uncertainty, Tier B name DOES
        get the confirmation door."""
        text = (
            "I went to a place called Stanley, but I may not have "
            "that name right."
        )
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(
            any("stanley" in i and "uncertain" in i for i in intents),
            f"expected stanley_uncertain door; got {intents}"
        )

    def test_something_like_southridge_fires_uncertain(self):
        """Kent's actual TEST-D phrasing: 'something like Southridge
        Air Force Base, though I may not have that exactly right.'
        Southridge isn't in the seed list (Selfridge is) but the
        uncertainty marker should still be detected — the test
        confirms the detection signal works even without a name match.
        """
        text = (
            "The base name is something like Southridge Air Force "
            "Base, though I may not have that exactly right."
        )
        # We don't assert a specific door fires (Southridge isn't in
        # the seed list), but we DO assert the uncertainty marker is
        # detected — which downstream consumers can use.
        self.assertTrue(
            bank._has_uncertainty_marker(text),
            f"uncertainty marker should fire on this turn"
        )

    def test_uncertainty_marker_alone_does_not_fire_door(self):
        """An uncertainty marker without any Tier-B name shouldn't
        manufacture a door."""
        text = "I'm not sure about that — it was a long time ago."
        doors = bank.detect_doors(text)
        priority1 = [d for d in doors if d.priority == 1]
        self.assertEqual(priority1, [])

    def test_self_correction_on_tier_b_fires(self):
        """Self-correction always fires regardless of which tier."""
        text = "I went to Fargo — actually, it was Bismarck where I met her."
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(
            any("correction" in i for i in intents),
            f"expected self-correction door; got {intents}"
        )


# ── Section 2: Communication / logistics (priority 2) ──────────────────────


class CommunicationLogisticsDetectorTests(unittest.TestCase):

    def test_kent_test_comms_opens_communication_door(self):
        text = (
            "I had been in Germany less than a year when I contacted "
            "my fiancée Janice. This was 1959, so it was not like today "
            "where you just text someone."
        )
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(
            any(i == "communication_with_partner_overseas" for i in intents),
            f"expected communication_with_partner_overseas door; got {intents}"
        )

    def test_communication_door_uses_partner_name(self):
        text = (
            "I was in Germany and I wrote letters to my fiancée Janice "
            "all through 1959."
        )
        doors = bank.detect_doors(text)
        comm = [d for d in doors if d.intent == "communication_with_partner_overseas"]
        self.assertEqual(len(comm), 1)
        self.assertIn("Janice", comm[0].question_en)

    def test_spouse_travel_door_opens(self):
        text = (
            "I came home to Bismarck, married Janice, and then we had "
            "to travel back to Germany under Army rules."
        )
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(any(i == "spouse_travel_paperwork" for i in intents))

    def test_no_overseas_no_communication_door(self):
        text = "Janice and I dated for two years before we got married."
        doors = bank.detect_doors(text)
        self.assertFalse(
            any(d.intent == "communication_with_partner_overseas" for d in doors)
        )


# ── Section 3: Role transition (priority 3) ────────────────────────────────


class RoleTransitionDetectorTests(unittest.TestCase):

    def test_courier_pivot_opens_door(self):
        text = (
            "I replaced Johnny Johnson on the courier route while he "
            "was on leave. The route took me to the 32nd Brigade where "
            "I asked if they had openings for photographers, and they "
            "said yes — that opened up the photography work."
        )
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(
            any("photography" in i or "courier" in i for i in intents),
            f"expected role-pivot door; got {intents}"
        )

    def test_career_choice_under_constraint_opens(self):
        text = (
            "I had originally enlisted hoping for Army Security Agency "
            "work, but they told me I would have to wait three months. "
            "I asked what else was available and chose Nike Ajax."
        )
        doors = bank.detect_doors(text)
        intents = [d.intent for d in doors]
        self.assertTrue(
            any(i == "career_choice_under_constraint" for i in intents)
        )


# ── Section 4: Relationship (priority 4 — BANK ONLY) ───────────────────────


class RelationshipDetectorTests(unittest.TestCase):
    """Priority 4 doors must NEVER be picked as immediate.
    They always bank, per Chris's rule about the 'private working as
    photographer for a General' question."""

    def test_private_photographer_for_general_banks(self):
        text = (
            "I was a private working as a photographer for General "
            "Peter Schmick, a Canadian-born officer."
        )
        doors = bank.detect_doors(text)
        rank_doors = [d for d in doors if d.intent == "rank_asymmetry_relationship"]
        self.assertEqual(len(rank_doors), 1, f"expected exactly 1 rank-asymmetry door, got {doors}")
        self.assertEqual(rank_doors[0].priority, 4)

    def test_relationship_door_never_wins_immediate(self):
        """Even when a relationship door is the ONLY door, selector
        returns None for immediate (because priority > 3)."""
        text = "I worked for Bob the foreman at the factory."
        doors = bank.detect_doors(text)
        # Filter to just the worked-for door
        rel_doors = [d for d in doors if d.priority >= 4]
        if rel_doors:
            immediate, banked = bank.select_immediate_and_bank(rel_doors)
            self.assertIsNone(immediate)
            self.assertEqual(len(banked), len(rel_doors))


# ── Section 5: Daily life (priority 5 — BANK ONLY) ─────────────────────────


class DailyLifeDetectorTests(unittest.TestCase):

    def test_living_in_kaiserslautern_opens_daily_life_door(self):
        text = "Janice and I were living up around Kaiserslautern for two years."
        doors = bank.detect_doors(text)
        daily = [d for d in doors if d.intent == "daily_life_off_duty"]
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0].priority, 5)


# ── Section 6: Medical / family (priority 6 — BANK ONLY) ───────────────────


class MedicalFamilyDetectorTests(unittest.TestCase):

    def test_premature_son_opens_medical_door(self):
        text = (
            "Our son Vince was born premature with cerebral palsy and "
            "spent weeks in the incubator."
        )
        doors = bank.detect_doors(text)
        medical = [d for d in doors if d.intent == "medical_family_care"]
        self.assertEqual(len(medical), 1)
        self.assertEqual(medical[0].priority, 6)

    def test_no_medical_no_medical_door(self):
        text = "Our son Vince was born in Germany and ended up American."
        doors = bank.detect_doors(text)
        medical = [d for d in doors if d.intent == "medical_family_care"]
        self.assertEqual(medical, [])


# ── Section 7: Selector — immediate vs bank ────────────────────────────────


class SelectorTests(unittest.TestCase):

    def _make(self, intent, priority):
        return bank.Door(
            intent=intent,
            question_en="Q?",
            triggering_anchor="anchor",
            why_it_matters="reason",
            priority=priority,
        )

    def test_priority_1_wins_over_priority_2(self):
        doors = [self._make("p2", 2), self._make("p1", 1)]
        immediate, banked = bank.select_immediate_and_bank(doors)
        self.assertEqual(immediate.intent, "p1")
        self.assertEqual(len(banked), 1)
        self.assertEqual(banked[0].intent, "p2")

    def test_priority_4_alone_does_not_get_immediate(self):
        doors = [self._make("p4", 4)]
        immediate, banked = bank.select_immediate_and_bank(doors)
        self.assertIsNone(immediate)
        self.assertEqual(len(banked), 1)

    def test_priority_4_with_priority_2_yields_priority_2_immediate(self):
        doors = [self._make("p4", 4), self._make("p2", 2)]
        immediate, banked = bank.select_immediate_and_bank(doors)
        self.assertEqual(immediate.intent, "p2")
        self.assertEqual(len(banked), 1)
        self.assertEqual(banked[0].intent, "p4")

    def test_empty_doors_yields_empty(self):
        immediate, banked = bank.select_immediate_and_bank([])
        self.assertIsNone(immediate)
        self.assertEqual(banked, [])

    def test_kent_test_g_combined(self):
        """Kent TEST-G: rank-asymmetry (private + General) + four
        fragile names (Schmick, Kaiserslautern, Landstuhl, Ramstein)
        + working_relationship_boss. Asserts the priority-1 fragile-
        name wins the immediate slot AND the priority-4 relationship
        doors are banked, never immediate."""
        text = (
            "I was a private working as a photographer for General "
            "Peter Schmick. While Janice and I were in Kaiserslautern "
            "our oldest son Vince was born at Landstuhl Air Force "
            "Hospital near Ramstein Air Force Base."
        )
        doors = bank.detect_doors(text)
        immediate, banked = bank.select_immediate_and_bank(doors)
        # Immediate must be a fragile-name confirm (priority 1).
        self.assertIsNotNone(immediate)
        self.assertEqual(
            immediate.priority, 1,
            f"immediate must be priority 1; got {immediate}",
        )
        # The private-photographer-for-General relationship door MUST
        # be in the bank, not immediate. Per Chris's locked rule.
        bank_intents = [d.intent for d in banked]
        self.assertTrue(
            "rank_asymmetry_relationship" in bank_intents
            or "working_relationship_boss" in bank_intents,
            f"rank-asymmetry or working-relationship must be banked. banked={bank_intents}",
        )


# ── Section 8: Flush triggers ──────────────────────────────────────────────


class FlushTriggerTests(unittest.TestCase):

    def test_short_answer_no_door_flushes(self):
        flush, reason = bank.should_flush_bank(
            narrator_text="Yeah, that's right.",
            current_turn_doors=[],
        )
        self.assertTrue(flush)
        self.assertTrue(reason.startswith("short_answer_no_door"))

    def test_short_answer_with_door_does_not_flush(self):
        # Door present means follow it, don't flush
        door = bank.Door("test", "Q?", "anchor", "why", 2)
        flush, reason = bank.should_flush_bank(
            narrator_text="Yes, I went to Stanley.",
            current_turn_doors=[door],
        )
        self.assertFalse(flush)

    def test_what_else_cue_flushes(self):
        flush, reason = bank.should_flush_bank(
            narrator_text="What else would you like to know?",
            current_turn_doors=[],
        )
        self.assertTrue(flush)
        self.assertEqual(reason, "narrator_cued")

    def test_where_were_we_flushes(self):
        flush, reason = bank.should_flush_bank(
            narrator_text="Where were we?",
            current_turn_doors=[],
        )
        self.assertTrue(flush)

    def test_long_answer_no_cue_does_not_flush(self):
        flush, reason = bank.should_flush_bank(
            narrator_text=(
                "I went to the depot in Stanley with my dad. He was "
                "carrying my bag and we walked the platform."
            ),
            current_turn_doors=[],
        )
        self.assertFalse(flush)

    def test_floor_released_directive_flushes(self):
        flush, reason = bank.should_flush_bank(
            narrator_text="[SYSTEM: floor released — narrator paused for 30 seconds]",
            current_turn_doors=[],
            is_system_directive=True,
        )
        self.assertTrue(flush)
        self.assertEqual(reason, "floor_released")

    def test_operator_click_directive_flushes(self):
        flush, reason = bank.should_flush_bank(
            narrator_text="[SYSTEM:ASK_BANKED_FOLLOWUP]",
            current_turn_doors=[],
            is_system_directive=True,
        )
        self.assertTrue(flush)
        self.assertEqual(reason, "operator_click")


# ── Section 9: Flush composer ──────────────────────────────────────────────


class FlushComposerTests(unittest.TestCase):

    def test_compose_uses_locked_phrase(self):
        out = bank.compose_bank_flush_response(
            "How did you and Janice keep in touch in 1959?"
        )
        self.assertIn("I want to come back to one detail", out)
        self.assertIn("How did you and Janice keep in touch in 1959?", out)

    def test_compose_empty_question_returns_empty(self):
        self.assertEqual(bank.compose_bank_flush_response(""), "")

    def test_kent_chris_example_renders_correctly(self):
        """Chris's example from the spec: 'I want to come back to one
        detail you mentioned earlier. As a private working as
        photographer for General Schmick, was it strictly yes-sir /
        no-sir, or did he know you through your photography skills?'"""
        q = (
            "As a private working as photographer for General Schmick, "
            "was it strictly yes-sir / no-sir, or did he know you "
            "through your photography skills?"
        )
        out = bank.compose_bank_flush_response(q)
        self.assertEqual(
            out,
            "I want to come back to one detail you mentioned earlier. " + q,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
