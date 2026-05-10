"""WO-LORI-WITNESS-FOLLOWUP-BANK-01 — pipeline stress harness (2026-05-10).

Exercises the full patience-layer pipeline END-TO-END against a
multi-narrator corpus, OFFLINE (no API, no DB, no LLM). Surfaces
pass/fail/gap behavior across every shape we expect to handle in
parent sessions:

  - Kent factual structured narrative (Fort Ord chapter)
  - Kent institutional passive ("I was put in charge of meal tickets")
  - Kent meta-feedback ("stop the sensory questions")
  - Kent self-correction ("not Lansdale, was Landstuhl")
  - Kent uncertainty marker on Tier B name ("I may not have Stanley right")
  - Kent ordinary Tier-N name (no spelling-confirm fires)
  - Janice hearth-sensory narrative
  - Mary short "what else?" flush cue
  - Mary long monologue with embedded "what else" (must NOT flush)
  - Mary Spanish memory_echo ("¿qué sabes de mí?") — KNOWN GAP
  - Mary Spanish age recall ("¿cuántos años tengo?") — KNOWN GAP
  - Marvin internal-state vs institutional-assignment disambiguation
  - Adult-competence overlay vs default selector behavior

Each fixture is asserted explicitly. Known gaps (Spanish detection)
are documented with `_skip_known_gap()` so they show up in the matrix
as GAP-rather-than-PASS but do not fail the suite. When the gap is
fixed, flip the corresponding `_GAP_*` constant to False — the test
will then become enforced.

Output: standard unittest output PLUS a behavior-matrix readout
emitted by `report_matrix()` (a final `zzz_*` test, naming chosen so
unittest's default lexicographic ordering runs it last).

Run:
    python -m unittest tests.test_witness_bank_pipeline_stress
    python tests/test_witness_bank_pipeline_stress.py        # also fine
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import lori_followup_bank as bank  # noqa: E402
from api.services import lori_witness_mode as wm  # noqa: E402


# ── Known gaps (flip these to False when the gap is closed) ────────────────
#
# Each constant gates a single test. When the underlying detector is
# extended to cover the gap (e.g. Spanish memory_echo regex), set the
# corresponding constant to False — the "known gap" branch becomes a
# strict assertion that the gap is closed.

_GAP_SPANISH_MEMORY_ECHO = True   # backend memory-echo regex is EN-only
_GAP_SPANISH_AGE_RECALL = True    # backend has no age_recall server-trigger


# ── Behavior-matrix accumulator ────────────────────────────────────────────
#
# Each test records its outcome here so the final matrix readout can
# reflect the full pipeline state in one block. We do NOT assertEquals
# against this matrix — it's diagnostic only. The actual contracts are
# enforced via individual assertions inside each test.

_MATRIX: List[Dict[str, str]] = []


def _record(case_id: str, narrator: str, pipeline_stage: str, outcome: str,
            note: str = "") -> None:
    _MATRIX.append({
        "case_id": case_id,
        "narrator": narrator,
        "stage": pipeline_stage,
        "outcome": outcome,  # PASS / GAP / NOTE
        "note": note,
    })


# ── Narrator fixture corpus ────────────────────────────────────────────────
#
# Realistic narrator turns drawn from the Kent transcripts banked in
# `docs/reports/kent_*` and the synthesis at
# `docs/reports/BANK_PRIORITY_REBUILD_2026-05-10.md`. Janice / Mary /
# Marvin turns are operator-shaped paraphrases of similar oral-history
# patterns (we don't have full transcripts banked yet for those three).


KENT_FORT_ORD_CHAPTER = (
    "I went from Stanley to Fargo on the train for the induction "
    "tests. I scored the highest on the admissions test of anyone in "
    "the group. From there I had been put in charge of meal tickets "
    "for the trainload of recruits headed to the West Coast. We rode "
    "the train all the way to Fort Ord, and that was where basic "
    "training started. I qualified expert on the M1 rifle."
)

KENT_NIKE_PASSIVE = (
    "After basic training I was selected for Nike Hercules training. "
    "I was assigned to a missile battery in Germany. I was sent up "
    "into the mountains for CBR training before deployment."
)

KENT_META_FEEDBACK = (
    "You are being vague and not asking about basic training rather "
    "the sensory parts of it. I want to tell my experience and you "
    "want to know how I felt."
)

KENT_SELF_CORRECTION = (
    "Vince was born at Lansdale Army Hospital. Wait — that's not "
    "right. It was not Lansdale Army Hospital. It was Landstuhl Air "
    "Force Hospital. I want it spelled correctly for the record."
)

KENT_TIER_B_UNCERTAIN = (
    "We were stationed near Stanley before basic training. I may not "
    "have Stanley right — that's how it comes back to me but I wish "
    "I had the city clear."
)

KENT_TIER_B_CONFIDENT = (
    "We were stationed near Fort Ord during basic training. The "
    "barracks were on the south side of the post."
)

KENT_INTERNAL_STATE = (
    "I was feeling tired during the long train ride. I was thinking "
    "about home a lot back then."
)

JANICE_HEARTH_NARRATIVE = (
    "I baked all our bread on the wood stove. The kitchen smelled of "
    "yeast and cinnamon every Saturday morning. The children would "
    "come in from the prairie wind smelling like cold and dirt. We "
    "had milk from the cow and butter we churned ourselves."
)

MARY_SHORT_WHAT_ELSE = "OK what else?"

MARY_LONG_MONOLOGUE_WITH_EMBEDDED_CUE = (
    "I remember when we lived in Spokane and the children were small. "
    "There was a big elm tree in the yard and we hung a tire swing "
    "from it. The neighbors had a dog named Rusty who would come "
    "over for treats. What else can I tell you about that house — I "
    "remember the kitchen had blue tile counters and a big window "
    "over the sink looking out at the garden."
)

MARY_SPANISH_MEMORY_ECHO = "¿qué sabes de mí?"

MARY_SPANISH_AGE = "¿cuántos años tengo?"

MARVIN_INSTITUTIONAL = (
    "I was promoted to staff sergeant in 1962. I was stationed at "
    "Selfridge Air Force Base. I was given the squadron records to "
    "manage."
)


# ── Fixture-driven pipeline tests ──────────────────────────────────────────


class KentFortOrdStructuredNarrativeTest(unittest.TestCase):
    """Kent's Fort Ord chapter — the canonical structured narrative.
    Witness mode MUST fire; passive Pass 2 MUST extract the meal-
    ticket assignment phrase; sensory doors MUST be banked under
    adult_competence overlay; Tier-N institutional names (Fort Ord,
    Stanley, Fargo) MUST NOT fire immediate spelling-confirms."""

    NARRATOR = "Kent"
    TEXT = KENT_FORT_ORD_CHAPTER

    def test_a_witness_detects_structured_narrative(self):
        det = wm.detect_witness_event(self.TEXT)
        self.assertTrue(det.is_witness_event)
        self.assertEqual(det.detection_type, "STRUCTURED_NARRATIVE")
        _record(
            "kent_fortord", self.NARRATOR, "witness_detect",
            "PASS", f"sub_type={det.sub_type} word_count={det.word_count}",
        )

    def test_b_passive_pass2_extracts_meal_tickets(self):
        phrases = wm._extract_event_phrases(self.TEXT)
        ok = any("meal tickets" in p.lower() for p in phrases)
        self.assertTrue(
            ok,
            f"Pass 2 should extract meal-tickets assignment; got {phrases!r}",
        )
        _record(
            "kent_fortord", self.NARRATOR, "passive_pass2",
            "PASS", "meal-tickets phrase present",
        )

    def test_c_doors_include_story_weighted_meal_tickets(self):
        doors = bank.detect_doors(self.TEXT)
        anchors = [d.triggering_anchor.lower() for d in doors]
        ok = any("meal tickets" in a for a in anchors)
        self.assertTrue(
            ok,
            f"Tier 1A door for meal-tickets expected; got anchors={anchors!r}",
        )
        _record(
            "kent_fortord", self.NARRATOR, "tier1a_door",
            "PASS", "meal-tickets surfaced",
        )

    def test_d_tier_n_fort_ord_does_not_fire_immediate_spelling(self):
        doors = bank.detect_doors(self.TEXT)
        immediate, _banked = bank.select_immediate_and_bank(
            doors, narrator_voice_overlay="adult_competence",
        )
        if immediate is None:
            _record(
                "kent_fortord", self.NARRATOR, "tier_n_immediate",
                "PASS", "no immediate door fired",
            )
            return
        self.assertNotIn(
            "fort_ord", immediate.intent.lower(),
            f"Fort Ord must never auto-immediate; got {immediate.intent}",
        )
        self.assertNotIn(
            "stanley", immediate.intent.lower(),
            f"Stanley must never auto-immediate; got {immediate.intent}",
        )
        self.assertNotIn(
            "fargo", immediate.intent.lower(),
            f"Fargo must never auto-immediate; got {immediate.intent}",
        )
        _record(
            "kent_fortord", self.NARRATOR, "tier_n_immediate",
            "PASS", f"immediate={immediate.intent}",
        )

    def test_e_sensory_door_banks_under_adult_competence(self):
        # Synthesize a sensory-shaped door manually and confirm the
        # selector demotes it under the Kent overlay.
        sensory = bank.Door(
            intent="daily_life_off_duty",
            question_en="What was the smell of the barracks like?",
            triggering_anchor="barracks",
            why_it_matters="sensory texture",
            priority=5,
        )
        story = bank.Door(
            intent="story_weighted_named_particular",
            question_en="What did the meal tickets look like day to day?",
            triggering_anchor="meal tickets",
            why_it_matters="adult-competence anchor",
            priority=1, tier="1A", story_weight=5,
        )
        immediate, banked = bank.select_immediate_and_bank(
            [sensory, story],
            narrator_voice_overlay="adult_competence",
        )
        self.assertIsNotNone(immediate)
        self.assertEqual(immediate.intent, "story_weighted_named_particular")
        self.assertIn(
            sensory, banked,
            "sensory door must be banked under adult_competence overlay",
        )
        _record(
            "kent_fortord", self.NARRATOR, "overlay_demotion",
            "PASS", "sensory banked / story-weighted immediate",
        )


class KentNikeInstitutionalAssignmentTest(unittest.TestCase):
    """Kent's Nike Hercules pivot — institutional passive grammar.
    Pass 2 of `_extract_event_phrases` must extract at least the
    selection phrase; witness mode should fire; bank should NOT
    auto-immediate a Nike Hercules spelling-confirm (Tier-N)."""

    NARRATOR = "Kent"
    TEXT = KENT_NIKE_PASSIVE

    def test_a_passive_pass2_extracts_nike_selection(self):
        phrases = wm._extract_event_phrases(self.TEXT)
        ok = any("selected for nike" in p.lower() for p in phrases)
        self.assertTrue(
            ok,
            f"selected-for-Nike phrase expected; got {phrases!r}",
        )
        _record(
            "kent_nike", self.NARRATOR, "passive_pass2",
            "PASS", "Nike Hercules selection extracted",
        )

    def test_b_passive_pass2_extracts_assigned_to_germany(self):
        phrases = wm._extract_event_phrases(self.TEXT)
        ok = any("assigned to" in p.lower() for p in phrases)
        self.assertTrue(
            ok,
            f"assigned-to phrase expected; got {phrases!r}",
        )
        _record(
            "kent_nike", self.NARRATOR, "passive_pass2_assigned",
            "PASS", "assigned-to-Germany extracted",
        )

    def test_c_tier_n_nike_does_not_auto_immediate(self):
        doors = bank.detect_doors(self.TEXT)
        immediate, _ = bank.select_immediate_and_bank(
            doors, narrator_voice_overlay="adult_competence",
        )
        if immediate is None:
            _record(
                "kent_nike", self.NARRATOR, "tier_n_nike",
                "PASS", "no immediate door fired",
            )
            return
        self.assertNotIn(
            "nike_ajax", immediate.intent.lower(),
        )
        self.assertNotIn(
            "nike_hercules", immediate.intent.lower(),
        )
        _record(
            "kent_nike", self.NARRATOR, "tier_n_nike",
            "PASS", f"immediate={immediate.intent}",
        )


class KentMetaFeedbackTest(unittest.TestCase):
    """Kent's literal meta-feedback turn must produce comprehending
    META_FEEDBACK detection with a sensible factual_anchor."""

    NARRATOR = "Kent"
    TEXT = KENT_META_FEEDBACK

    def test_a_witness_detects_meta_feedback(self):
        det = wm.detect_witness_event(self.TEXT)
        self.assertEqual(det.detection_type, "META_FEEDBACK")
        # sub_type is whichever comprehending category fired first;
        # all of them are valid responses to Kent's literal turn.
        self.assertIn(det.sub_type, (
            "stop_sensory", "ask_x_not_y", "want_facts", "being_vague",
        ))
        _record(
            "kent_meta", self.NARRATOR, "witness_detect",
            "PASS", f"sub_type={det.sub_type}",
        )

    def test_b_compose_response_no_sensory_followup(self):
        det = wm.detect_witness_event(self.TEXT)
        out = wm.compose_witness_response(det, target_language="en")
        self.assertTrue(out)
        out_lower = out.lower()
        # Comprehending acks must NOT propose more sensory work.
        self.assertNotIn("sights", out_lower)
        self.assertNotIn("sounds", out_lower)
        self.assertNotIn("smell", out_lower)
        self.assertNotIn("scenery", out_lower)
        _record(
            "kent_meta", self.NARRATOR, "ack_compose",
            "PASS", f"no sensory tokens in {out!r}",
        )


class KentSelfCorrectionTest(unittest.TestCase):
    """Self-correction "not Lansdale, was Landstuhl" must produce the
    fragile_name_confirm_correction door."""

    NARRATOR = "Kent"
    TEXT = KENT_SELF_CORRECTION

    def test_a_correction_door_fires(self):
        doors = bank.detect_doors(self.TEXT)
        intents = [d.intent for d in doors]
        ok = any("correction" in i.lower() for i in intents)
        self.assertTrue(
            ok,
            f"self-correction door expected; got intents={intents!r}",
        )
        _record(
            "kent_correction", self.NARRATOR, "correction_door",
            "PASS", f"intents={intents}",
        )

    def test_b_landstuhl_tier_a_fires(self):
        doors = bank.detect_doors(self.TEXT)
        anchors = [d.triggering_anchor.lower() for d in doors]
        ok = any("landstuhl" in a for a in anchors)
        self.assertTrue(
            ok,
            f"Landstuhl Tier A door expected; got anchors={anchors!r}",
        )
        _record(
            "kent_correction", self.NARRATOR, "tier_a_landstuhl",
            "PASS", "Landstuhl spelling-confirm fires",
        )


class KentTierBUncertaintyTest(unittest.TestCase):
    """Stanley + uncertainty marker must produce a Tier-B-uncertain
    door. Without the marker, no Stanley spelling-confirm fires."""

    NARRATOR = "Kent"
    TEXT_WITH_MARKER = KENT_TIER_B_UNCERTAIN
    TEXT_NO_MARKER = KENT_TIER_B_CONFIDENT

    def test_a_with_marker_fires_uncertain_door(self):
        doors = bank.detect_doors(self.TEXT_WITH_MARKER)
        intents = [d.intent for d in doors]
        ok = any("_uncertain" in i for i in intents)
        self.assertTrue(
            ok,
            f"Tier-B-uncertain door expected with marker; got {intents!r}",
        )
        _record(
            "kent_tier_b_uncertain", self.NARRATOR, "uncertain_door",
            "PASS", f"intents={intents}",
        )

    def test_b_without_marker_no_spelling_confirm(self):
        doors = bank.detect_doors(self.TEXT_NO_MARKER)
        intents = [d.intent for d in doors]
        # Confident "Fort Ord" mention with no uncertainty marker
        # should NOT fire a fragile-name confirm.
        bad = [i for i in intents if i.startswith("fragile_name_")]
        self.assertFalse(
            bad,
            f"no spelling-confirm expected without uncertainty; got {bad!r}",
        )
        _record(
            "kent_tier_b_confident", self.NARRATOR, "no_spelling_confirm",
            "PASS", f"intents={intents}",
        )


class KentInternalStateRejectionTest(unittest.TestCase):
    """Internal-state phrases ("I was feeling tired", "I was thinking
    about home") must NOT be extracted by passive Pass 2."""

    NARRATOR = "Kent"
    TEXT = KENT_INTERNAL_STATE

    def test_no_institutional_extraction(self):
        phrases = wm._extract_event_phrases(self.TEXT)
        bad = [
            p for p in phrases
            if "feeling tired" in p.lower()
            or "thinking about home" in p.lower()
        ]
        self.assertFalse(
            bad,
            f"internal-state phrases must not be extracted; got {bad!r}",
        )
        _record(
            "kent_internal_state", self.NARRATOR, "passive_pass2_reject",
            "PASS", "feeling/thinking rejected by allowlist",
        )


class JaniceHearthNarrativeTest(unittest.TestCase):
    """Janice's hearth narrative under hearth_sensory overlay should
    surface sensory anchors as banked doors. v1 detector emits
    daily_life_off_duty for "stationed at X" / "lived in X" patterns
    only — broad sensory anchor detection (kitchen / smell of bread)
    is parked. This test documents the current state."""

    NARRATOR = "Janice"
    TEXT = JANICE_HEARTH_NARRATIVE

    def test_a_witness_detects_some_narrative_shape(self):
        det = wm.detect_witness_event(self.TEXT)
        # Janice's narrative may or may not pass the structured-
        # narrative threshold (it's hearth-shaped, not chronological).
        # Either outcome is acceptable; we just record it.
        outcome = (
            "STRUCTURED_NARRATIVE" if det.is_witness_event else "no_witness"
        )
        _record(
            "janice_hearth", self.NARRATOR, "witness_detect",
            "NOTE", f"witness={outcome} subtype={det.sub_type}",
        )

    def test_b_no_false_fragile_name_doors(self):
        doors = bank.detect_doors(self.TEXT)
        bad = [
            d for d in doors
            if d.intent.startswith("fragile_name_")
        ]
        self.assertFalse(
            bad,
            f"no fragile-name doors expected for hearth narrative; got {bad}",
        )
        _record(
            "janice_hearth", self.NARRATOR, "no_false_fragile",
            "PASS", "no fragile-name false positives",
        )


class MaryFlushTriggerTest(unittest.TestCase):
    """Short "what else?" cues fire flush; long monologues with the
    same cue word embedded mid-prose do NOT (40-word chapter gate)."""

    NARRATOR = "Mary"

    def test_a_short_what_else_fires_flush(self):
        ok, reason = bank.should_flush_bank(
            narrator_text=MARY_SHORT_WHAT_ELSE,
            current_turn_doors=[],
        )
        self.assertTrue(ok, f"short cue should flush; reason={reason!r}")
        self.assertEqual(reason, "narrator_cued")
        _record(
            "mary_short_cue", self.NARRATOR, "flush_trigger",
            "PASS", f"reason={reason}",
        )

    def test_b_long_monologue_with_embedded_cue_does_not_flush(self):
        ok, reason = bank.should_flush_bank(
            narrator_text=MARY_LONG_MONOLOGUE_WITH_EMBEDDED_CUE,
            current_turn_doors=[],
        )
        self.assertFalse(
            ok,
            f"long monologue must not flush despite embedded cue; reason={reason}",
        )
        _record(
            "mary_long_monologue", self.NARRATOR, "no_flush_in_chapter",
            "PASS", "40-word gate held the floor",
        )


class MarySpanishGapsTest(unittest.TestCase):
    """Spanish memory-echo and age questions are KNOWN GAPS in the
    current detectors. These tests document the gap explicitly so the
    matrix surfaces them. When the gap closes (Spanish regex added),
    flip _GAP_SPANISH_MEMORY_ECHO / _GAP_SPANISH_AGE_RECALL to False
    and these tests will become strict assertions of the fix."""

    NARRATOR = "Mary"

    def test_a_spanish_memory_echo_status(self):
        # The witness-mode detector covers correction Spanish patterns
        # but NOT memory-echo Spanish phrasing. The chat_ws server-
        # side memory-echo override is also EN-only ("about me" /
        # "my life" / "who I am"). So Spanish "¿qué sabes de mí?"
        # currently does NOT route to deterministic memory_echo.
        det = wm.detect_witness_event(MARY_SPANISH_MEMORY_ECHO)
        is_handled_deterministically = det.is_witness_event
        if _GAP_SPANISH_MEMORY_ECHO:
            # Document the gap. Test still passes — but the matrix
            # row marks it GAP so it's visible in the readout.
            self.assertFalse(
                is_handled_deterministically,
                "Gap closed unexpectedly — flip _GAP_SPANISH_MEMORY_ECHO=False",
            )
            _record(
                "mary_spanish_memory_echo", self.NARRATOR,
                "spanish_memory_echo",
                "GAP",
                "no Spanish anchor in memory_echo regex (BE) or "
                "FE _looksLikeMemoryEchoRequest",
            )
        else:
            # Gap-closed enforcement: must route deterministically.
            self.assertTrue(
                is_handled_deterministically,
                "Spanish memory-echo must route deterministically",
            )
            _record(
                "mary_spanish_memory_echo", self.NARRATOR,
                "spanish_memory_echo",
                "PASS", "Spanish memory-echo deterministic route",
            )

    def test_b_spanish_age_recall_status(self):
        # FE detector _looksLikeAgeQuestion is EN-only and the backend
        # has NO age_recall server-trigger; backend relies on FE-set
        # turn_mode. Spanish "¿cuántos años tengo?" currently won't
        # route to compose_age_recall.
        # We can't test the FE detector from Python, but we can
        # confirm witness-mode does not absorb the question (it
        # shouldn't — age questions aren't witness territory).
        det = wm.detect_witness_event(MARY_SPANISH_AGE)
        # The age question is too short to be a structured narrative
        # AND doesn't match meta-feedback patterns, so witness mode
        # correctly returns no detection. The GAP is that no other
        # deterministic route covers it.
        self.assertFalse(det.is_witness_event)
        if _GAP_SPANISH_AGE_RECALL:
            _record(
                "mary_spanish_age", self.NARRATOR,
                "spanish_age_recall",
                "GAP",
                "no Spanish detector for age questions (FE or BE)",
            )
        else:
            _record(
                "mary_spanish_age", self.NARRATOR,
                "spanish_age_recall",
                "PASS", "Spanish age recall route landed",
            )


class MarvinInstitutionalAssignmentTest(unittest.TestCase):
    """Marvin's institutional turn — passive Pass 2 should extract
    promoted-to / stationed-at / given phrases."""

    NARRATOR = "Marvin"
    TEXT = MARVIN_INSTITUTIONAL

    def test_passive_extracts_promoted(self):
        phrases = wm._extract_event_phrases(self.TEXT)
        ok = any("promoted" in p.lower() for p in phrases)
        self.assertTrue(
            ok,
            f"promoted-to phrase expected; got {phrases!r}",
        )
        _record(
            "marvin_promoted", self.NARRATOR, "passive_pass2",
            "PASS", "promoted-to extracted",
        )


class OverlayDifferentiationTest(unittest.TestCase):
    """Same door set, different overlay → different selector outcomes.
    Validates the BANK_PRIORITY_REBUILD overlay arithmetic."""

    def setUp(self):
        self.sensory = bank.Door(
            intent="daily_life_off_duty",
            question_en="What did the barracks smell like?",
            triggering_anchor="barracks",
            why_it_matters="sensory",
            priority=5,
        )
        self.role = bank.Door(
            intent="role_pivot_courier_bridge",
            question_en="How did the courier route turn into the next role?",
            triggering_anchor="courier route",
            why_it_matters="career pivot",
            priority=3,
        )
        self.tier_n = bank.Door(
            intent="fragile_name_confirm_fort_ord",
            question_en="Did I get Fort Ord spelled right?",
            triggering_anchor="Fort Ord",
            why_it_matters="institutional spelling",
            priority=1,
        )

    def test_a_default_overlay_picks_tier_n_immediate(self):
        """Note: with NO overlay rule applied, the priority-1
        spelling-confirm would have won immediate. The Tier-N filter
        runs in select_immediate_and_bank UNCONDITIONALLY (not gated
        by overlay), so even default overlay banks Fort Ord. This
        test locks that contract — Tier-N is ALWAYS demoted."""
        immediate, banked = bank.select_immediate_and_bank(
            [self.tier_n, self.role, self.sensory],
            narrator_voice_overlay="default",
        )
        # role door (priority 3) wins because Tier-N is filtered out
        # and sensory is priority 5 (always banks regardless of overlay).
        self.assertIsNotNone(immediate)
        self.assertEqual(immediate.intent, "role_pivot_courier_bridge")
        self.assertIn(self.tier_n, banked)
        _record(
            "overlay_default", "synthetic", "tier_n_filter",
            "PASS", f"immediate={immediate.intent}",
        )

    def test_b_adult_competence_demotes_sensory(self):
        # role + sensory only (no Tier-N) under adult_competence:
        # role wins, sensory banks.
        immediate, banked = bank.select_immediate_and_bank(
            [self.role, self.sensory],
            narrator_voice_overlay="adult_competence",
        )
        self.assertIsNotNone(immediate)
        self.assertEqual(immediate.intent, "role_pivot_courier_bridge")
        self.assertIn(self.sensory, banked)
        _record(
            "overlay_adult_competence", "synthetic", "sensory_demote",
            "PASS", "sensory correctly banked",
        )

    def test_c_default_overlay_keeps_sensory_banked(self):
        # Even without adult_competence, sensory (priority 5) banks
        # because select_immediate_and_bank caps immediate at priority
        # 1-3. This locks the existing rule.
        immediate, banked = bank.select_immediate_and_bank(
            [self.sensory],
            narrator_voice_overlay="default",
        )
        self.assertIsNone(immediate)
        self.assertIn(self.sensory, banked)
        _record(
            "overlay_default_priority5", "synthetic", "priority_floor",
            "PASS", "priority 5 always banks",
        )


# ── Final matrix readout ────────────────────────────────────────────────────


class _zzz_PrintMatrix(unittest.TestCase):
    """Lexicographic ordering puts this last. Emits the behavior
    matrix to stderr so the readout sits at the bottom of `python
    -m unittest -v ...` output. Always passes."""

    def test_zzz_print_matrix(self):
        if not _MATRIX:
            return  # unittest may discover this class without others
        lines = [
            "",
            "─" * 78,
            "PIPELINE STRESS MATRIX (2026-05-10)",
            "─" * 78,
            f"{'narrator':<10} {'case':<28} {'stage':<22} {'outcome':<6} note",
            "─" * 78,
        ]
        for row in _MATRIX:
            lines.append(
                f"{row['narrator']:<10} "
                f"{row['case_id']:<28} "
                f"{row['stage']:<22} "
                f"{row['outcome']:<6} "
                f"{row['note']}"
            )
        # Counts
        outcomes = {
            "PASS": sum(1 for r in _MATRIX if r["outcome"] == "PASS"),
            "GAP": sum(1 for r in _MATRIX if r["outcome"] == "GAP"),
            "NOTE": sum(1 for r in _MATRIX if r["outcome"] == "NOTE"),
        }
        lines.append("─" * 78)
        lines.append(
            f"PASS={outcomes['PASS']}  "
            f"GAP={outcomes['GAP']}  "
            f"NOTE={outcomes['NOTE']}  "
            f"total={len(_MATRIX)}"
        )
        lines.append("─" * 78)
        sys.stderr.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
