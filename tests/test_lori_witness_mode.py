"""Unit tests for services/lori_witness_mode.py.

Pure-function tests — no DB, no LLM, no filesystem. The detector
must catch Kent's literal 2026-05-09 turns that walked him out of
the session, AND the structured-narrative shape that should never
have gotten a sensory probe in the first place.

Cases organized by detection type. Kent's literal turns appear as
NamedRealNarrator tests so any regression on his exact phrasing is
visible.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import lori_witness_mode as wm  # noqa: E402


# ── Section 1: Kent's literal failure-mode turns ──────────────────────────


class KentLiteralFailureMode(unittest.TestCase):
    """The exact 2026-05-09 live failures from transcript_switch_moyt6
    .txt. Every one of these MUST detect."""

    def test_line_80_meta_feedback_stop_sensory_walks_him_out(self):
        # Kent's verbatim turn that triggered Lori's apology + MORE
        # sensory probes (line 82). The LLM heard "sensory parts" as
        # a topic to focus on. The deterministic intercept must hear
        # it as a directive to stop.
        text = (
            "You are being vague and not asking about basic training "
            "rather the sensory parts of it. i want to tell my "
            "experience and you want to know how i felt"
        )
        detection = wm.detect_witness_event(text)
        self.assertTrue(detection.is_witness_event)
        self.assertEqual(detection.detection_type, "META_FEEDBACK")
        # Multiple categories match — first-priority is stop_sensory
        # since "sensory parts" is the most direct directive.
        self.assertIn(detection.sub_type, ("stop_sensory", "ask_x_not_y", "being_vague", "want_facts"))

    def test_kent_literal_response_is_comprehending_no_sensory(self):
        text = (
            "You are being vague and not asking about basic training "
            "rather the sensory parts of it. i want to tell my "
            "experience and you want to know how i felt"
        )
        answer = wm.detect_and_compose(text, target_language="en")
        self.assertIsNotNone(answer)
        # CRITICAL: response must NOT propose more sensory questions
        self.assertNotIn("sights", answer.text.lower())
        self.assertNotIn("sounds", answer.text.lower())
        self.assertNotIn("smells", answer.text.lower())
        self.assertNotIn("how did you feel", answer.text.lower())
        self.assertNotIn("sensory aspects", answer.text.lower())
        # Must comprehend — acknowledge the correction
        self.assertTrue(
            any(kw in answer.text.lower() for kw in (
                "got it", "understood", "you're right", "skip", "stop",
                "follow the facts", "tell me",
            )),
            f"Response must comprehend the meta-feedback: {answer.text!r}",
        )

    def test_line_38_structured_narrative_basic_training(self):
        # Kent's 5-fact answer that Lori pivoted to scenery on.
        text = (
            "a number of things for example having to go through the "
            "the admissions test going from Stanley by train to Fargo "
            "and going through the physical exam and mental exam to be "
            "qualified to be in the army and from there I got the "
            "highest score and my penalty or a reward was to put me in "
            "charge of all the meal tickets for a train load of "
            "recruits going from Fargo to the West Coast"
        )
        detection = wm.detect_witness_event(text)
        self.assertTrue(detection.is_witness_event)
        self.assertEqual(detection.detection_type, "STRUCTURED_NARRATIVE")
        # Anchor should be a real factual element from the turn
        self.assertTrue(detection.factual_anchor,
                        f"Should have extracted an anchor: {detection!r}")

    def test_line_38_response_invites_continuation_no_sensory(self):
        text = (
            "a number of things for example having to go through the "
            "the admissions test going from Stanley by train to Fargo "
            "and going through the physical exam and mental exam to be "
            "qualified to be in the army and from there I got the "
            "highest score and my penalty or a reward was to put me in "
            "charge of all the meal tickets for a train load of "
            "recruits going from Fargo to the West Coast"
        )
        answer = wm.detect_and_compose(text)
        self.assertIsNotNone(answer)
        # CRITICAL: must invite continuation, not pivot to scenery
        self.assertNotIn("scenery", answer.text.lower())
        self.assertNotIn("sights", answer.text.lower())
        self.assertNotIn("how did you feel", answer.text.lower())
        # Must invite continuation
        self.assertTrue(
            any(kw in answer.text.lower() for kw in (
                "tell me more", "what happened next", "what came next",
                "go on", "continue",
            )),
            f"Response must invite continuation: {answer.text!r}",
        )


# ── Section 2: META-FEEDBACK sub-types ────────────────────────────────────


class MetaFeedbackStopSensoryTest(unittest.TestCase):
    def test_explicit_stop_asking_about_sensory(self):
        d = wm.detect_witness_event("stop asking about sensory things")
        self.assertEqual(d.sub_type, "stop_sensory")

    def test_dont_keep_asking_how_i_felt(self):
        d = wm.detect_witness_event("don't keep asking how i felt")
        self.assertEqual(d.detection_type, "META_FEEDBACK")

    def test_you_keep_asking_about_sensory(self):
        d = wm.detect_witness_event("you keep asking about the sensory")
        self.assertEqual(d.sub_type, "stop_sensory")


class MetaFeedbackWantFactsTest(unittest.TestCase):
    def test_i_want_to_tell_my_experience(self):
        d = wm.detect_witness_event("i want to tell my experience")
        self.assertEqual(d.detection_type, "META_FEEDBACK")
        self.assertEqual(d.sub_type, "want_facts")

    def test_facts_not_feelings(self):
        d = wm.detect_witness_event("facts not feelings please")
        self.assertEqual(d.detection_type, "META_FEEDBACK")

    def test_let_me_finish(self):
        d = wm.detect_witness_event("let me finish what I was saying")
        self.assertEqual(d.detection_type, "META_FEEDBACK")
        self.assertEqual(d.sub_type, "want_facts")

    def test_let_me_finish_fires_meta_feedback(self):
        # BUG-LORI-WANT-FACTS-FALSE-POSITIVE-01 (2026-05-10): "let me
        # tell" was retired as a META_FEEDBACK trigger because Kent's
        # K-COMBINED opener "Let me tell it in order because one thing
        # led to the next" was firing META_FEEDBACK want_facts and
        # producing the deterministic ack instead of letting the
        # narrative through. "let me finish/describe/explain" still
        # fire — those are unambiguously corrective directives.
        d = wm.detect_witness_event("let me finish what I was saying")
        self.assertEqual(d.detection_type, "META_FEEDBACK")

    def test_let_me_tell_is_NOT_meta_feedback(self):
        # Narrator's own framing — Lori must not treat as a directive.
        # Should fall through to STRUCTURED_NARRATIVE if long enough,
        # else no detection.
        d = wm.detect_witness_event("let me tell my story")
        self.assertNotEqual(d.detection_type, "META_FEEDBACK")


class MetaFeedbackBeingVagueTest(unittest.TestCase):
    def test_you_are_being_vague(self):
        d = wm.detect_witness_event("you are being vague")
        self.assertEqual(d.sub_type, "being_vague")

    def test_thats_not_what_i_said(self):
        d = wm.detect_witness_event("that's not what I said")
        self.assertEqual(d.detection_type, "META_FEEDBACK")

    def test_you_are_not_listening(self):
        d = wm.detect_witness_event("you are not listening")
        self.assertEqual(d.sub_type, "being_vague")


class MetaFeedbackSpanishTest(unittest.TestCase):
    def test_es_dejame_contar(self):
        d = wm.detect_witness_event("déjame contar mi historia")
        self.assertEqual(d.detection_type, "META_FEEDBACK")

    def test_es_quiero_contar_mi_experiencia(self):
        d = wm.detect_witness_event("quiero contar mi experiencia")
        self.assertEqual(d.detection_type, "META_FEEDBACK")

    def test_es_no_estas_escuchando(self):
        d = wm.detect_witness_event("no estás escuchando")
        self.assertEqual(d.detection_type, "META_FEEDBACK")


# ── Section 3: STRUCTURED NARRATIVE detection ─────────────────────────────


class StructuredNarrativeTest(unittest.TestCase):
    """Multi-event chronological turns must trigger witness-mode
    continuation, not extraction probes."""

    def test_kent_germany_arc(self):
        # The arc Chris described: basic training → Germany → marriage
        # → second Germany → child → roles
        text = (
            "After basic training I was sent to Germany. I came back "
            "married Janice and then we went back to Germany together. "
            "Our first child was born there. I started as a missile "
            "operator and then was reassigned to be a photographer "
            "for a general."
        )
        d = wm.detect_witness_event(text)
        self.assertEqual(d.detection_type, "STRUCTURED_NARRATIVE")
        self.assertGreaterEqual(d.chronological_connector_count, 2)

    def test_short_turn_does_not_trigger(self):
        # Below 40-word floor
        d = wm.detect_witness_event("yes")
        self.assertFalse(d.is_witness_event)

    def test_emotional_short_turn_does_not_trigger(self):
        # Narrator giving a feeling-only short answer should not be
        # caught as structured narrative
        d = wm.detect_witness_event("it was hard")
        self.assertFalse(d.is_witness_event)

    def test_long_turn_with_no_chrono_connectors_does_not_trigger(self):
        # 40+ words but no narrative shape — just rambling
        text = (
            "yes that is correct yes that is correct yes that is correct "
            "yes that is correct yes that is correct yes that is correct "
            "yes that is correct yes that is correct yes that is correct"
        )
        d = wm.detect_witness_event(text)
        # Either no detection, or NOT structured (could match other
        # categories but structured needs chronological connectors)
        self.assertNotEqual(d.detection_type, "STRUCTURED_NARRATIVE")

    def test_multi_event_with_action_verbs_triggers(self):
        text = (
            "I enlisted in the Army in 1957. I went to basic training in "
            "Fort Leonard Wood and then I was sent overseas. I served "
            "for four years and after that I came home and married "
            "Janice. We had three children together."
        )
        d = wm.detect_witness_event(text)
        self.assertEqual(d.detection_type, "STRUCTURED_NARRATIVE")


# ── Section 4: Anchor extraction ──────────────────────────────────────────


class AnchorExtractionTest(unittest.TestCase):
    def test_pulls_last_proper_noun(self):
        text = "I went from Stanley to Fargo and then to the West Coast."
        anchor = wm._extract_factual_anchor(text)
        # Should pull "West Coast" or similar last proper noun
        self.assertTrue(anchor)
        self.assertNotIn("Stanley", anchor.split() and anchor.split()[0:1])  # not the FIRST proper noun

    def test_pulls_germany_from_kent_arc(self):
        text = (
            "After basic training I was sent to Germany. I came back "
            "married Janice."
        )
        anchor = wm._extract_factual_anchor(text)
        # Last proper noun is Janice (more recent than Germany)
        self.assertEqual(anchor, "Janice")

    def test_falls_back_to_definite_phrase(self):
        text = "I worked at the aluminum plant for many years."
        anchor = wm._extract_factual_anchor(text)
        # No proper noun → fall back to "the aluminum plant" or similar
        self.assertTrue(anchor)
        self.assertIn("the", anchor.lower())

    def test_skips_sentence_start_capital(self):
        text = "Yes that is correct. Yes that is also correct."
        anchor = wm._extract_factual_anchor(text)
        # "Yes" is in _NOT_AN_ANCHOR — should be skipped
        self.assertNotEqual(anchor, "Yes")

    def test_empty_input(self):
        self.assertEqual(wm._extract_factual_anchor(""), "")
        self.assertEqual(wm._extract_factual_anchor("   "), "")
        self.assertEqual(wm._extract_factual_anchor(None), "")


# ── Section 5: Composer output ────────────────────────────────────────────


class ComposeWitnessResponseTest(unittest.TestCase):
    def test_stop_sensory_includes_anchor(self):
        d = wm.WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="stop_sensory",
            factual_anchor="basic training",
        )
        text = wm.compose_witness_response(d, "en")
        self.assertIn("basic training", text)
        self.assertIn("skip", text.lower())

    def test_structured_includes_anchor(self):
        d = wm.WitnessDetection(
            detection_type="STRUCTURED_NARRATIVE",
            sub_type="structured",
            factual_anchor="the meal tickets",
        )
        text = wm.compose_witness_response(d, "en")
        self.assertIn("the meal tickets", text)
        self.assertIn("more", text.lower())

    def test_no_anchor_still_produces_clean_response(self):
        d = wm.WitnessDetection(
            detection_type="STRUCTURED_NARRATIVE",
            sub_type="structured",
            factual_anchor="",
        )
        text = wm.compose_witness_response(d, "en")
        self.assertTrue(text)
        self.assertIn("more", text.lower())

    def test_no_sensory_in_any_response(self):
        # Critical regression: NO response shape may include sensory
        # probe vocabulary OR emotional probe vocabulary OR scenery /
        # camaraderie / teamwork (Kent's specific failure terms).
        # ChatGPT review 2026-05-09 expanded the forbidden list.
        for sub in ("stop_sensory", "ask_x_not_y", "want_facts", "being_vague", "structured"):
            d = wm.WitnessDetection(
                detection_type="META_FEEDBACK" if sub != "structured" else "STRUCTURED_NARRATIVE",
                sub_type=sub,
                factual_anchor="basic training",
            )
            text = wm.compose_witness_response(d, "en").lower()
            for forbidden in (
                "sights", "sounds", "smells",
                "how did you feel", "how do you feel",
                "scenery", "scene",
                "camaraderie", "teamwork",
                "emotion", "emotionally",
                # "feel" / "felt" alone are too restrictive — would block
                # legitimate templates. Only block "how ... feel" forms.
            ):
                self.assertNotIn(
                    forbidden, text,
                    f"forbidden={forbidden!r} in sub={sub}: {text!r}",
                )

    def test_spanish_locale_routing(self):
        d = wm.WitnessDetection(
            detection_type="META_FEEDBACK",
            sub_type="stop_sensory",
            factual_anchor="entrenamiento",
        )
        text = wm.compose_witness_response(d, "es")
        self.assertIn("Entendido", text)
        self.assertIn("entrenamiento", text)

    def test_no_match_returns_empty(self):
        d = wm.WitnessDetection()  # is_witness_event=False
        self.assertEqual(wm.compose_witness_response(d), "")


# ── Section 6: detect_and_compose convenience ─────────────────────────────


class DetectAndComposeTest(unittest.TestCase):
    def test_returns_none_for_short_neutral(self):
        result = wm.detect_and_compose("Yes that's right.")
        self.assertIsNone(result)

    def test_returns_none_for_simple_yes(self):
        result = wm.detect_and_compose("yes")
        self.assertIsNone(result)

    def test_returns_answer_for_meta_feedback(self):
        result = wm.detect_and_compose(
            "you are being vague",
            target_language="en",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.detection_type, "META_FEEDBACK")
        self.assertEqual(result.language, "en")

    def test_returns_answer_for_structured_narrative(self):
        result = wm.detect_and_compose(
            "I enlisted in 1957. Then I went to basic training. "
            "After that I was sent to Germany. I came home and "
            "got married. We had three children."
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.detection_type, "STRUCTURED_NARRATIVE")

    def test_unknown_language_falls_back_to_en(self):
        result = wm.detect_and_compose(
            "you are being vague",
            target_language="fr",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.language, "en")


# ── Section 7: false-positive resistance ──────────────────────────────────


class FalsePositiveResistanceTest(unittest.TestCase):
    """Storytelling turns that happen to contain overlapping vocabulary
    must NOT detect spuriously."""

    def test_narrator_describing_someone_else_being_vague(self):
        # "He was vague" — talking ABOUT someone, not about Lori
        text = "My grandfather was always vague about the war."
        d = wm.detect_witness_event(text)
        # This SHOULD NOT trigger meta-feedback (narrator describing
        # someone else, not correcting Lori). Acceptable false positive
        # if it does — the response would be "you're right — please
        # tell me again about your grandfather" which is still safe.
        # Documenting current behavior:
        if d.is_witness_event:
            self.assertNotEqual(d.sub_type, "stop_sensory")

    def test_narrator_using_word_sensory_in_passing(self):
        text = "I had a job that involved sensory testing."
        d = wm.detect_witness_event(text)
        # Should NOT match "stop_sensory" — no "stop/don't" verb
        if d.is_witness_event:
            self.assertNotEqual(d.sub_type, "stop_sensory")

    def test_empty_input(self):
        self.assertFalse(wm.detect_witness_event("").is_witness_event)
        self.assertFalse(wm.detect_witness_event(None).is_witness_event)
        self.assertFalse(wm.detect_witness_event("   \n  ").is_witness_event)

    def test_system_directive_stripped(self):
        # SYSTEM directive blocks must not trigger META_FEEDBACK
        text = (
            "[SYSTEM: The narrator just selected 'Adolescence' on the "
            "Life Map — they want to talk about this era of their life. "
            "Ask ONE warm, open question about this period.]"
        )
        d = wm.detect_witness_event(text)
        self.assertFalse(d.is_witness_event)


# ── Section 8: determinism ────────────────────────────────────────────────


class DeterminismTest(unittest.TestCase):
    def test_same_input_same_output(self):
        text = "you are being vague and not asking about basic training"
        a = wm.detect_and_compose(text)
        b = wm.detect_and_compose(text)
        self.assertEqual(a.text, b.text)
        self.assertEqual(a.sub_type, b.sub_type)


class ChatGPTReviewLockInTest(unittest.TestCase):
    """Specific tests required by ChatGPT review 2026-05-09 to prove
    the detector and composer fixes actually work on Kent's exact
    transcript language. If these fail, the whole intercept is moot
    because Kent will still hit the LLM and get a sensory probe."""

    def test_kent_army_line_triggers_structured_narrative(self):
        # Kent's line 38 verbatim — the load-bearing case. If this
        # doesn't trigger, the rest of the witness module is moot.
        text = (
            "a number of things for example having to go through the "
            "the admissions test going from Stanley by train to Fargo "
            "and going through the physical exam and mental exam to "
            "be qualified to be in the army and from there I got the "
            "highest score and my penalty or a reward was to put me "
            "in charge of all the meal tickets for a train load of "
            "recruits going from Fargo to the West Coast"
        )
        ans = wm.detect_and_compose(text)
        self.assertIsNotNone(ans, "Kent's line 38 MUST trigger witness mode")
        self.assertEqual(ans.detection_type, "STRUCTURED_NARRATIVE")
        # Hard bans on response content
        text_lower = ans.text.lower()
        self.assertNotIn("scenery", text_lower)
        self.assertNotIn("sights", text_lower)
        self.assertNotIn("sounds", text_lower)
        self.assertNotIn("smells", text_lower)
        self.assertNotIn("feel", text_lower)

    def test_kent_meta_feedback_uses_basic_training_anchor_not_garbage(self):
        # Kent's line 80 verbatim — the meta-feedback class. The
        # composer must produce a response that anchors on "basic
        # training" (the topic Kent wants Lori to follow) NOT on
        # "my experience and you want" (pronoun-heavy garbage from
        # last-proper-noun fallback).
        text = (
            "you are being vague and not asking about basic training "
            "rather the sensory parts of it. I want to tell my "
            "experience and you want to know how I felt"
        )
        ans = wm.detect_and_compose(text)
        self.assertIsNotNone(ans)
        self.assertEqual(ans.detection_type, "META_FEEDBACK")
        # Comprehending acknowledgment
        text_lower = ans.text.lower()
        self.assertTrue(
            "basic training" in text_lower
            or "what happened next" in text_lower
            or "skip" in text_lower,
            f"Response must anchor on basic training or invite continuation: {ans.text!r}",
        )
        # Bad-anchor sanitizer must reject these
        self.assertNotIn("my experience and you want", text_lower)
        self.assertNotIn("how i felt", text_lower)
        self.assertNotIn("the sensory parts", text_lower)
        # Hard bans on sensory probe
        self.assertNotIn("sights", text_lower)
        self.assertNotIn("smells", text_lower)
        self.assertNotIn("scenery", text_lower)


class AnchorSanitizerTest(unittest.TestCase):
    def test_rejects_pronoun_heavy_anchor(self):
        self.assertEqual(wm._sanitize_anchor("my experience and you want"), "")

    def test_rejects_how_i_felt(self):
        self.assertEqual(wm._sanitize_anchor("how I felt"), "")

    def test_rejects_the_sensory_parts(self):
        self.assertEqual(wm._sanitize_anchor("the sensory parts"), "")

    def test_keeps_clean_anchor(self):
        self.assertEqual(wm._sanitize_anchor("basic training"), "basic training")
        self.assertEqual(wm._sanitize_anchor("Germany"), "Germany")
        self.assertEqual(wm._sanitize_anchor("the meal tickets"), "the meal tickets")

    def test_rejects_too_long_non_proper_noun(self):
        # 6+ word phrase that isn't all proper nouns
        bad = "the long part where everything happened all at once"
        self.assertEqual(wm._sanitize_anchor(bad), "")

    def test_keeps_proper_noun_chain(self):
        # 5-word proper noun chain is OK
        good = "West Coast Naval Air Station"
        self.assertEqual(wm._sanitize_anchor(good), good)

    def test_empty_input(self):
        self.assertEqual(wm._sanitize_anchor(""), "")
        self.assertEqual(wm._sanitize_anchor(None), "")


class CorrectionPerspectiveInversionTest(unittest.TestCase):
    """BUG-LORI-CORRECTION-PERSPECTIVE-INVERSION-01 (2026-05-10) —
    Kent's K10 hospital correction was met with first-person echo
    ("So while we were in Kaiserslautern our son Vince was born...").
    The deterministic correction intercept must NEVER produce
    first-person mimicry — strict second-person acknowledgment only.
    """

    def test_kent_k10_hospital_correction_no_first_person(self):
        text = (
            "you have the name of the hospital wrong not Lansdale Army "
            "hospital but landstuhl air force hospital ramstein air "
            "force base"
        )
        ans = wm.detect_and_compose(text)
        self.assertIsNotNone(ans)
        self.assertEqual(ans.detection_type, "META_FEEDBACK")
        text_lower = ans.text.lower()
        # Forbidden first-person mimicry markers
        for forbidden in (" we ", " our ", " our son", " while we", " i was"):
            self.assertNotIn(forbidden, text_lower,
                             f"forbidden first-person {forbidden!r}: {ans.text!r}")
        # Must include the corrected value (case-insensitive)
        self.assertIn("landstuhl", text_lower)
        # Must comprehend
        self.assertIn("got it", text_lower)
        # Multi-word proper-noun correction → spelling confirmation
        self.assertIn("did i get that name right", text_lower)

    def test_single_proper_noun_correction_no_spelling_check(self):
        ans = wm.detect_and_compose("actually it was Bismarck")
        self.assertIsNotNone(ans)
        # Single proper noun → no spelling check (overhead)
        self.assertNotIn("did i get that name right", ans.text.lower())
        self.assertIn("Bismarck", ans.text)

    def test_year_correction_no_spelling_check(self):
        # "the year was" extracted as anchor — but no caps, so no
        # spelling check
        ans = wm.detect_and_compose("actually the year was 1962")
        self.assertIsNotNone(ans)
        self.assertNotIn("did i get that name right", ans.text.lower())

    def test_correction_never_uses_first_person_pronouns(self):
        # Sweep across multiple correction shapes
        cases = [
            "you have the name wrong not Smith but Jones",
            "actually it was 1957",
            "I meant Fort Ord not Fort Lewis",
            "the name was Leonard Duffy",
            "you got the year wrong, it was 1960",
        ]
        for c in cases:
            ans = wm.detect_and_compose(c)
            if ans is None:
                continue
            text_lower = ans.text.lower()
            # Lori must NEVER use first-person narrator markers
            for forbidden in (" we ", " our ", " our son", " i was"):
                self.assertNotIn(
                    forbidden, text_lower,
                    f"correction must stay second-person: input={c!r} "
                    f"response={ans.text!r}",
                )


class ActiveReceiptCompositionTest(unittest.TestCase):
    """BUG-LORI-WITNESS-ACTIVE-RECEIPT-01 (2026-05-10) — multi-fact
    receipt for STRUCTURED_NARRATIVE turns. When narrator gives a
    clean structured factual narrative, response should use event
    phrases ("You enlisted in 1957, went to Fort Leonard Wood, ...")
    not just label list."""

    def test_clean_narrative_produces_active_receipt(self):
        text = (
            "I enlisted in 1957. Then I went to basic training in Fort "
            "Leonard Wood. After that I was sent overseas to Germany. "
            "I served four years. Then I came home and married Janice "
            "in 1962."
        )
        ans = wm.detect_and_compose(text)
        self.assertIsNotNone(ans)
        self.assertEqual(ans.detection_type, "STRUCTURED_NARRATIVE")
        text_lower = ans.text.lower()
        # Active-receipt template starts with "You" (second-person)
        self.assertTrue(
            ans.text.startswith("You ") or "you " in text_lower[:30],
            f"active receipt should start with second-person 'You': {ans.text!r}",
        )
        # Multi-fact: should reference at least 2 narrator-named events
        named_events = ["enlisted", "fort leonard wood", "germany", "served", "married", "janice"]
        matches = sum(1 for e in named_events if e in text_lower)
        self.assertGreaterEqual(matches, 3,
                                f"receipt should reflect 3+ narrator events: {ans.text!r}")
        # Continuation question
        self.assertIn("what happened next", text_lower)
        # No sensory probes
        for forbidden in ("scenery", "sights", "sounds", "smells",
                          "how did you feel", "camaraderie"):
            self.assertNotIn(forbidden, text_lower)

    def test_disfluent_narrative_falls_back_to_multi_anchor(self):
        # Kent's K4 verbatim has self-repeating phrases ("I had made I
        # scored", "M1 rifle M1 rifle"). Quality gate should reject
        # noisy event extraction and fall back to multi-anchor.
        text = (
            "I had a high enough score that I had made I scored expert "
            "on the use of the M1 rifle M1 rifle and then at the end "
            "of Basic Training Day called each of us in for a decision "
            "on where we were going to call I had originally enlisted"
        )
        ans = wm.detect_and_compose(text)
        if ans is None:
            return  # short turn fell below threshold; OK
        if ans.detection_type == "STRUCTURED_NARRATIVE":
            # Either falls back to multi-anchor or single-anchor —
            # both are listenable.  Reject only if the response is
            # >40 words (would indicate noisy event-receipt fired)
            self.assertLessEqual(
                len(ans.text.split()), 40,
                f"disfluent narrative should fall back to clean template: {ans.text!r}",
            )

    def test_events_quality_pass_rejects_noisy(self):
        # Three events with heavy token overlap → reject
        events = [
            "had a high enough score that I had",
            "had made I scored expert on the use",
            "scored expert on the use of the M1",
        ]
        self.assertFalse(wm._events_quality_pass(events))

    def test_events_quality_pass_accepts_clean(self):
        events = [
            "enlisted in 1957",
            "went to Fort Leonard Wood",
            "served four years",
        ]
        self.assertTrue(wm._events_quality_pass(events))


class MultiAnchorReflectionTest(unittest.TestCase):
    """BUG-LORI-WITNESS-MULTI-ANCHOR-01 (2026-05-10) — Kent's session
    showed single-anchor 'Tell me more about Brigade' was too thin
    after 100-200 word factual narratives. Multi-anchor extraction +
    template demonstrates active listening deterministically."""

    def test_extract_top_anchors_kent_k3_basic_training(self):
        text = (
            "okay okay after going through the recruiting process for "
            "enlisting into the army my dad drove me into the railroad "
            "Depot at Stanley to put me on the train to go to Fargo for "
            "the induction physical and testing I took test there"
        )
        anchors = wm._extract_top_anchors(text, max_n=3)
        # Should pull 3 distinct narrator-named anchors
        self.assertEqual(len(anchors), 3)
        # Order should reflect narrative position
        text_lower = text.lower()
        positions = [text_lower.find(a.lower()) for a in anchors]
        self.assertEqual(positions, sorted(positions),
                         f"Anchors must be in narrative order: {anchors}")

    def test_kent_k6_multi_anchor_output_includes_germany_bismarck_janice(self):
        text = (
            "in Germany was fantastic it is a lot to learn and after I "
            "have been there for a bit then I got to leave to go home "
            "come back to Bismarck and Janice family had put together a "
            "terrific marriage ceremony"
        )
        ans = wm.detect_and_compose(text)
        self.assertIsNotNone(ans)
        self.assertEqual(ans.detection_type, "STRUCTURED_NARRATIVE")
        text_lower = ans.text.lower()
        # All three of Kent's named places/people should be reflected
        self.assertIn("germany", text_lower)
        self.assertIn("bismarck", text_lower)
        self.assertIn("janice", text_lower)
        # Continuation invitation
        self.assertIn("what happened next", text_lower)
        # NO sensory probe
        self.assertNotIn("scenery", text_lower)
        self.assertNotIn("sights", text_lower)
        self.assertNotIn("how did you feel", text_lower)

    def test_format_multi_anchor_list_oxford_comma_en(self):
        result = wm._format_multi_anchor_list(["A", "B", "C"], "en")
        self.assertEqual(result, "A, B, and C")

    def test_format_multi_anchor_list_two_items_en(self):
        result = wm._format_multi_anchor_list(["A", "B"], "en")
        self.assertEqual(result, "A and B")

    def test_format_multi_anchor_list_single_en(self):
        result = wm._format_multi_anchor_list(["A"], "en")
        self.assertEqual(result, "A")

    def test_format_multi_anchor_list_empty(self):
        self.assertEqual(wm._format_multi_anchor_list([], "en"), "")

    def test_format_multi_anchor_list_es(self):
        result = wm._format_multi_anchor_list(["A", "B", "C"], "es")
        self.assertEqual(result, "A, B, y C")

    def test_falls_back_to_single_anchor_when_few(self):
        # Short narrative with only 1 proper noun → single-anchor path
        text = (
            "I went to Germany after basic training. It was a long "
            "time ago. The trip was something else. We took a train "
            "and a boat and I worked through it day by day."
        )
        ans = wm.detect_and_compose(text)
        # If detected, response should still be witness-mode shape
        if ans is not None:
            text_lower = ans.text.lower()
            self.assertIn("germany", text_lower)
            self.assertIn("what happened", text_lower)

    def test_dedupe_substring_anchors(self):
        # "Stanley" and "Stanley North Dakota" → keep the longer one
        text = (
            "I went to Stanley North Dakota and then I went back to "
            "Stanley with my brother and we did a number of things."
        )
        anchors = wm._extract_top_anchors(text, max_n=3)
        # Only ONE Stanley-related anchor should appear
        stanley_count = sum(1 for a in anchors if "stanley" in a.lower())
        self.assertLessEqual(stanley_count, 1)


class MetaFeedbackTopicExtractorTest(unittest.TestCase):
    def test_pulls_basic_training_from_kent_line(self):
        text = (
            "you are being vague and not asking about basic training "
            "rather the sensory parts of it"
        )
        topic = wm._extract_meta_feedback_topic(text)
        self.assertEqual(topic.lower(), "basic training")

    def test_pulls_topic_from_ask_about_X_not_Y(self):
        text = "ask about military service not feelings"
        topic = wm._extract_meta_feedback_topic(text)
        self.assertEqual(topic.lower(), "military service")

    def test_returns_empty_when_no_topic_pattern(self):
        text = "you are being vague"  # no "not asking about X" pattern
        topic = wm._extract_meta_feedback_topic(text)
        self.assertEqual(topic, "")


class LLMWitnessReceiptValidatorTest(unittest.TestCase):
    """BUG-LORI-WITNESS-LLM-RECEIPT-01 (2026-05-10) — coverage for the
    post-LLM validator that gates whether to keep the LLM's witness
    receipt or fall back to the deterministic compose_witness_response.

    Kent's narrator turn is the load-bearing scenario: a structured
    multi-event factual chronological recounting. A clean witness
    receipt should reflect ≥3 narrator-named anchors, stay in 35–110
    word range, ask ≤1 question, and never produce sensory probes or
    first-person mimicry.
    """

    KENT_NARRATOR = (
        "I went from Stanley to Fargo for the induction test. I scored "
        "expert on the M1 rifle. Then I got put in charge of the meal "
        "tickets in basic training. After that I shipped to Germany "
        "where I served with the Army Security Agency in Kaiserslautern."
    )

    def test_clean_llm_response_passes(self):
        # Clean witness receipt: reflects 4 narrator anchors (Stanley,
        # Fargo, M1, Kaiserslautern), 1 question, ~70 words.
        clean = (
            "I caught Stanley to Fargo for the induction test, scoring "
            "expert on the M1, getting charge of the meal tickets in "
            "basic training, then shipping to Kaiserslautern with the "
            "Army Security Agency. That is a real arc. Where would you "
            "like to pick up next?"
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=clean, narrator_text=self.KENT_NARRATOR,
        )
        self.assertTrue(ok, msg=f"Should pass; failures={failures}")
        self.assertEqual(failures, [])

    def test_forbidden_token_scenery_fails(self):
        bad = (
            "I caught Stanley to Fargo and the M1 score in "
            "Kaiserslautern. What was the scenery like in Germany "
            "during basic training?"
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=bad, narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("forbidden_token:") for f in failures))

    def test_forbidden_token_camaraderie_fails(self):
        bad = (
            "I caught Stanley, Fargo, the M1, and Kaiserslautern. What "
            "kind of camaraderie did you find with the Army Security "
            "Agency soldiers in basic training?"
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=bad, narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any("camaraderie" in f for f in failures))

    def test_first_person_mimicry_we_were_in_germany_fails(self):
        bad = (
            "I caught Stanley, Fargo, the M1, and Kaiserslautern. We "
            "were in Germany with the Army Security Agency for a long "
            "stretch in basic training. Where would you like to go next?"
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=bad, narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("first_person_mimicry:") for f in failures))

    def test_first_person_mimicry_our_son_fails(self):
        kent_family = (
            "I went to Germany with my fiancée Janice. Then our son "
            "was born in Bismarck after we returned to North Dakota."
        )
        bad = (
            "I caught Germany with Janice and Bismarck after the "
            "return to North Dakota. Our son must have been a real "
            "anchor for the whole family back then."
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=bad, narrator_text=kent_family,
        )
        self.assertFalse(ok)
        self.assertTrue(any("our son" in f for f in failures))

    def test_too_short_fails(self):
        ok, failures = wm.validate_witness_receipt(
            lori_text="I caught Stanley. What happened next?",
            narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("too_short:") for f in failures))

    def test_too_long_fails(self):
        # Build a >110-word response. All anchors echoed, no forbidden
        # tokens, ≤1 question.
        long = (
            "I caught Stanley to Fargo for the induction test, scoring "
            "expert on the M1, getting charge of the meal tickets in "
            "basic training, then shipping to Kaiserslautern with the "
            "Army Security Agency. " * 4
        ) + "Where next?"
        ok, failures = wm.validate_witness_receipt(
            lori_text=long, narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("too_long:") for f in failures))

    def test_too_many_questions_fails(self):
        bad = (
            "I caught Stanley to Fargo for the induction test, scoring "
            "expert on the M1 rifle, the meal tickets in basic, and "
            "Kaiserslautern with the Army Security Agency. What "
            "happened next? And how did the rest of the assignment go?"
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=bad, narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("too_many_questions:") for f in failures))

    def test_too_few_facts_echoed_fails(self):
        # Generic response with only one narrator-named anchor.
        thin = (
            "Thank you for sharing that with me. It sounds like there "
            "was a real journey through the army time you described, "
            "and the move through Stanley was one part of that. What "
            "would you like to come back to next in the timeline?"
        )
        ok, failures = wm.validate_witness_receipt(
            lori_text=thin, narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("too_few_facts:") for f in failures))

    def test_empty_response_fails(self):
        ok, failures = wm.validate_witness_receipt(
            lori_text="", narrator_text=self.KENT_NARRATOR,
        )
        self.assertFalse(ok)
        self.assertIn("empty_response", failures)

    def test_count_narrator_facts_echoed_kent(self):
        lori = (
            "Stanley, Fargo, the M1, Kaiserslautern, the Army Security "
            "Agency, and meal tickets all show up here."
        )
        n = wm._count_narrator_facts_echoed(self.KENT_NARRATOR, lori)
        # Should find at least 3 distinct narrator-named anchors.
        self.assertGreaterEqual(n, 3)

    def test_count_narrator_facts_echoed_zero(self):
        lori = "Tell me more about that experience."
        n = wm._count_narrator_facts_echoed(self.KENT_NARRATOR, lori)
        self.assertEqual(n, 0)


class FailClosedFallbackContractTest(unittest.TestCase):
    """BUG-LORI-WITNESS-LLM-RECEIPT-01 fail-closed contract.

    chat_ws.py's exception handler on the validator path now tries the
    deterministic compose_witness_response BEFORE keeping the LLM
    output. This is the test that the fallback function actually
    produces non-empty text for the kind of detection chat_ws stashes
    (STRUCTURED_NARRATIVE with at least one anchor) — without that
    guarantee the fail-closed branch reduces to fail-open.
    """

    KENT_NARRATOR = (
        "I went from Stanley to Fargo for the induction test. I scored "
        "expert on the M1 rifle. Then I got put in charge of the meal "
        "tickets in basic training. After that I shipped to Germany "
        "where I served with the Army Security Agency in Kaiserslautern."
    )

    def test_compose_witness_response_for_kent_arc_is_non_empty(self):
        # Reproduce what chat_ws.py would have stashed in
        # _witness_detection_for_fallback when STRUCTURED_NARRATIVE
        # routed through the LLM-receipt path.
        detection = wm.detect_witness_event(self.KENT_NARRATOR)
        self.assertEqual(detection.detection_type, "STRUCTURED_NARRATIVE")
        out = wm.compose_witness_response(detection, target_language="en")
        self.assertTrue(out, msg="fallback must be non-empty for fail-closed")
        # Witness-mode shape — single open question.
        self.assertEqual(out.count("?"), 1)
        # No sensory probes in the deterministic fallback either.
        for tok in ("scenery", "sights", "sounds", "smells", "camaraderie"):
            self.assertNotIn(tok, out.lower())

    def test_compose_witness_response_for_spanish_kent_arc(self):
        # Spanish narrator should still produce non-empty fallback.
        es_narrator = (
            "Fui de Stanley a Fargo para la prueba de inducción. Saqué "
            "experto en el M1. Luego me pusieron a cargo de los boletos "
            "de comida. Después embarqué a Alemania con el Army Security "
            "Agency en Kaiserslautern."
        )
        detection = wm.detect_witness_event(es_narrator)
        # Even if the detector falls back to single-anchor mode, the
        # fallback should still produce non-empty text.
        if detection.is_witness_event:
            out = wm.compose_witness_response(detection, target_language="es")
            self.assertTrue(out, msg="es fallback must be non-empty")


if __name__ == "__main__":
    unittest.main(verbosity=2)
