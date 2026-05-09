"""WO-LORI-SAFETY-INTEGRATION-01 Phase 2 — safety_classifier unit tests.

Two layers:
  1. Pure-function tests for response parsing + composition rule
     (no LLM mock required, no pydantic dependency)
  2. End-to-end tests with mocked LLM call (covers the
     classify_safety_llm wrapper; requires unittest.mock only)

The pure-function layer always runs in any environment. The end-to-end
layer requires the api.safety_classifier import to succeed; it skips
gracefully when llm_interview can't be imported (sandbox without
pydantic).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# safety_classifier itself only depends on stdlib at top level.
# The LLM call is lazy-imported. So the import below should work even
# when pydantic is missing.
try:
    from api.safety_classifier import (  # noqa: E402
        SafetyClassification,
        classify_safety_llm,
        should_route_to_safety,
        _parse_classification_response,
        _build_user_prompt,
        _VALID_CATEGORIES,
    )
    _IMPORT_OK = True
    _IMPORT_ERR = None
except Exception as _exc:
    SafetyClassification = None  # type: ignore[assignment]
    classify_safety_llm = None  # type: ignore[assignment]
    should_route_to_safety = None  # type: ignore[assignment]
    _parse_classification_response = None  # type: ignore[assignment]
    _build_user_prompt = None  # type: ignore[assignment]
    _VALID_CATEGORIES = ()  # type: ignore[assignment]
    _IMPORT_OK = False
    _IMPORT_ERR = repr(_exc)


def _skip_if_no_import():
    if not _IMPORT_OK:
        raise unittest.SkipTest(f"safety_classifier import failed: {_IMPORT_ERR}")


# ── Layer 1: pure-function tests ──────────────────────────────────────────

class ResponseParserTest(unittest.TestCase):
    """_parse_classification_response handles every documented edge case."""

    def setUp(self):
        _skip_if_no_import()

    def test_clean_json_response(self):
        result = _parse_classification_response('{"category": "ideation", "confidence": 0.75}')
        self.assertEqual(result.category, "ideation")
        self.assertEqual(result.confidence, 0.75)
        self.assertTrue(result.parse_ok)
        self.assertEqual(result.reason, "ok")

    def test_all_valid_categories_parse(self):
        for cat in _VALID_CATEGORIES:
            result = _parse_classification_response(f'{{"category": "{cat}", "confidence": 0.5}}')
            self.assertEqual(result.category, cat)
            self.assertTrue(result.parse_ok)

    def test_capitalized_category_normalized(self):
        result = _parse_classification_response('{"category": "IDEATION", "confidence": 0.6}')
        self.assertEqual(result.category, "ideation")
        self.assertTrue(result.parse_ok)

    def test_invalid_category_returns_none_parse_fail(self):
        result = _parse_classification_response('{"category": "panic", "confidence": 0.9}')
        self.assertEqual(result.category, "none")
        self.assertFalse(result.parse_ok)
        self.assertIn("invalid_category", result.reason)

    def test_missing_category_returns_none_parse_fail(self):
        result = _parse_classification_response('{"confidence": 0.5}')
        self.assertEqual(result.category, "none")
        self.assertFalse(result.parse_ok)
        self.assertEqual(result.reason, "missing_category")

    def test_malformed_json_returns_parse_fail(self):
        result = _parse_classification_response("not json at all")
        self.assertEqual(result.category, "none")
        self.assertFalse(result.parse_ok)
        self.assertEqual(result.reason, "parse_fail")

    def test_empty_response_returns_parse_fail(self):
        result = _parse_classification_response("")
        self.assertEqual(result.category, "none")
        self.assertFalse(result.parse_ok)
        self.assertEqual(result.reason, "empty_response")

    def test_whitespace_only_response_returns_parse_fail(self):
        result = _parse_classification_response("   \n\t  ")
        self.assertEqual(result.category, "none")
        self.assertFalse(result.parse_ok)
        self.assertEqual(result.reason, "empty_response")

    def test_json_in_preamble_salvaged(self):
        """LLM sometimes wraps the JSON in prose. Salvage the first {...}."""
        wrapped = (
            'Here is my classification:\n'
            '{"category": "distressed", "confidence": 0.7}\n'
            'I hope this helps.'
        )
        result = _parse_classification_response(wrapped)
        self.assertEqual(result.category, "distressed")
        self.assertTrue(result.parse_ok)

    def test_confidence_clamped_to_unit_interval(self):
        # Confidence above 1.0 → clamp to 1.0
        result = _parse_classification_response('{"category": "ideation", "confidence": 5.0}')
        self.assertEqual(result.confidence, 1.0)
        # Negative → clamp to 0.0
        result = _parse_classification_response('{"category": "ideation", "confidence": -0.5}')
        self.assertEqual(result.confidence, 0.0)

    def test_confidence_string_handled(self):
        # Sometimes models emit "0.7" as a string
        result = _parse_classification_response('{"category": "ideation", "confidence": "0.7"}')
        self.assertEqual(result.confidence, 0.7)

    def test_confidence_invalid_defaults_to_zero(self):
        result = _parse_classification_response('{"category": "ideation", "confidence": "high"}')
        self.assertEqual(result.confidence, 0.0)

    def test_category_with_quotes_in_word(self):
        # LLM might emit the word in quotes: "ideation" with extra whitespace
        result = _parse_classification_response('{"category": "  ideation  ", "confidence": 0.5}')
        self.assertEqual(result.category, "ideation")


class CompositionRuleTest(unittest.TestCase):
    """should_route_to_safety encodes the locked composition rule from
    the WO spec."""

    def setUp(self):
        _skip_if_no_import()

    def test_pattern_triggered_always_wins(self):
        # Pattern triggered + LLM none → route
        cls = SafetyClassification(category="none", parse_ok=True)
        self.assertTrue(should_route_to_safety(True, cls))
        # Pattern triggered + LLM acute → route (pattern wins, but both agree)
        cls = SafetyClassification(category="acute", parse_ok=True, confidence=0.9)
        self.assertTrue(should_route_to_safety(True, cls))

    def test_llm_distressed_ideation_acute_route_when_pattern_none(self):
        # BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01 (2026-05-09):
        # distressed/ideation now require confidence ≥ 0.65 to route
        # (was: any confidence). Acute is the floor exception — always
        # routes regardless of confidence. This test was tightened
        # alongside Mary's external-fear class fix; the high-confidence
        # path here uses 0.75 so distressed/ideation still cross the
        # new floor.
        for cat in ("distressed", "ideation", "acute"):
            cls = SafetyClassification(category=cat, parse_ok=True, confidence=0.75)
            self.assertTrue(should_route_to_safety(False, cls), f"failed for {cat}")
        # Acute at low confidence still routes (no floor on acute).
        low_acute = SafetyClassification(category="acute", parse_ok=True, confidence=0.30)
        self.assertTrue(should_route_to_safety(False, low_acute))
        # Distressed at 0.5 (Mary's class) must NOT route — this is the
        # exact behavior change from BUG-LORI-SAFETY-FALSE-POSITIVE-
        # EXTERNAL-FEAR-01. See SafetyFalsePositiveExternalFearTest below
        # for full coverage.
        low_distress = SafetyClassification(category="distressed", parse_ok=True, confidence=0.5)
        self.assertFalse(should_route_to_safety(False, low_distress))

    def test_llm_reflective_does_not_route(self):
        cls = SafetyClassification(category="reflective", parse_ok=True, confidence=0.5)
        self.assertFalse(should_route_to_safety(False, cls))

    def test_llm_none_does_not_route(self):
        cls = SafetyClassification(category="none", parse_ok=True)
        self.assertFalse(should_route_to_safety(False, cls))

    def test_parse_fail_does_not_route_fail_open(self):
        # Even if category looks scary, parse_ok=False = fail open
        cls = SafetyClassification(category="acute", parse_ok=False, reason="parse_fail")
        self.assertFalse(should_route_to_safety(False, cls))


class UserPromptBuildTest(unittest.TestCase):
    """_build_user_prompt produces a stable, delimiter-protected prompt."""

    def setUp(self):
        _skip_if_no_import()

    def test_includes_delimited_text(self):
        prompt = _build_user_prompt("I am tired all the time.")
        self.assertIn("<<<NARRATOR_TEXT", prompt)
        self.assertIn("NARRATOR_TEXT>>>", prompt)
        self.assertIn("I am tired all the time.", prompt)

    def test_handles_empty_input(self):
        prompt = _build_user_prompt("")
        self.assertIn("<<<NARRATOR_TEXT", prompt)
        # Should still produce valid prompt structure

    def test_handles_none_input(self):
        prompt = _build_user_prompt(None)  # type: ignore[arg-type]
        self.assertIn("<<<NARRATOR_TEXT", prompt)


# ── Layer 2: gate + LLM-mocked end-to-end ─────────────────────────────────

class GateTest(unittest.TestCase):
    """Default-off behavior + flag enabling."""

    def setUp(self):
        _skip_if_no_import()

    def test_default_off_returns_none_with_flag_off_reason(self):
        # Ensure flag is unset (default: off)
        with mock.patch.dict("os.environ", {}, clear=False):
            import os as _os
            _os.environ.pop("HORNELORE_SAFETY_LLM_LAYER", None)
            result = classify_safety_llm("I want to die.")
            self.assertEqual(result.category, "none")
            self.assertTrue(result.parse_ok)
            self.assertEqual(result.reason, "flag_off")

    def test_flag_on_invokes_llm(self):
        # When flag is on, the function attempts the LLM call.
        # Mock _try_call_llm to return a clean classification.
        with mock.patch.dict("os.environ", {"HORNELORE_SAFETY_LLM_LAYER": "1"}):
            with mock.patch(
                "api.llm_interview._try_call_llm",
                return_value='{"category": "ideation", "confidence": 0.8}',
            ) as m:
                result = classify_safety_llm(
                    "I just don't see the point in any of this anymore."
                )
                self.assertTrue(m.called)
                self.assertEqual(result.category, "ideation")
                self.assertEqual(result.confidence, 0.8)
                self.assertTrue(result.parse_ok)

    def test_flag_on_empty_input_short_circuits(self):
        with mock.patch.dict("os.environ", {"HORNELORE_SAFETY_LLM_LAYER": "1"}):
            with mock.patch(
                "api.llm_interview._try_call_llm",
                return_value='{"category": "ideation", "confidence": 0.8}',
            ) as m:
                result = classify_safety_llm("")
                # Should NOT have called LLM for empty input
                self.assertFalse(m.called)
                self.assertEqual(result.category, "none")
                self.assertEqual(result.reason, "empty_input")

    def test_llm_returns_none_handled_cleanly(self):
        with mock.patch.dict("os.environ", {"HORNELORE_SAFETY_LLM_LAYER": "1"}):
            with mock.patch("api.llm_interview._try_call_llm", return_value=None):
                result = classify_safety_llm("any text")
                self.assertEqual(result.category, "none")
                self.assertFalse(result.parse_ok)
                self.assertEqual(result.reason, "llm_returned_none")

    def test_llm_raises_handled_cleanly(self):
        with mock.patch.dict("os.environ", {"HORNELORE_SAFETY_LLM_LAYER": "1"}):
            with mock.patch(
                "api.llm_interview._try_call_llm",
                side_effect=RuntimeError("simulated LLM failure"),
            ):
                result = classify_safety_llm("any text")
                self.assertEqual(result.category, "none")
                self.assertFalse(result.parse_ok)
                self.assertIn("llm_error", result.reason)

    def test_llm_returns_garbage_handled_cleanly(self):
        with mock.patch.dict("os.environ", {"HORNELORE_SAFETY_LLM_LAYER": "1"}):
            with mock.patch(
                "api.llm_interview._try_call_llm",
                return_value="this is not JSON at all",
            ):
                result = classify_safety_llm("any text")
                self.assertEqual(result.category, "none")
                self.assertFalse(result.parse_ok)
                self.assertEqual(result.reason, "parse_fail")


class StructuralSanityTest(unittest.TestCase):
    """Files-on-disk checks. Run even if safety_classifier import failed."""

    def test_safety_classifier_file_exists(self):
        path = _SERVER_CODE / "api" / "safety_classifier.py"
        self.assertTrue(path.is_file(), f"safety_classifier.py missing at {path}")

    def test_env_example_documents_flag(self):
        env_example = _REPO_ROOT / ".env.example"
        if not env_example.is_file():
            self.skipTest(".env.example missing")
        text = env_example.read_text(encoding="utf-8")
        # Should document HORNELORE_SAFETY_LLM_LAYER (lands in same commit)
        # If flag is missing, this commit is incomplete.
        self.assertIn(
            "HORNELORE_SAFETY_LLM_LAYER",
            text,
            ".env.example must document the HORNELORE_SAFETY_LLM_LAYER flag",
        )


class IndirectIdeationRedTeamMiniPack(unittest.TestCase):
    """Phase 2 acceptance gate (≥80% indirect ideation detected).

    Uses mock LLM responses keyed to representative indirect-ideation
    phrases from the WO spec. Each phrase has a "ground truth" expected
    category — a well-tuned LLM should classify ≥80% correctly. Since we
    can't run the real LLM in unit tests, we mock the LLM's output for
    each phrase based on what a reasonable structured-output classifier
    would emit, and confirm:

      1. The composition+routing logic correctly routes ≥80% to safety
      2. Pattern-detector results always win on positive detection
      3. Reflective (past-tense) cases are NOT routed even when the LLM
         identifies them

    The full LLM-loop red-team (live LLM, all phrases) is Phase 8 territory
    — file at `data/safety_red_team_cases.json` + `scripts/run_safety_red_team.py`.
    This unit-level mini-pack is the structural acceptance gate for Phase 2.
    """

    # Each entry: (narrator_text, simulated_llm_category, expected_routed)
    # The LLM category is what a competent LLM SHOULD return for the
    # phrase — these are the empirical targets for the prompt's tuning.
    INDIRECT_IDEATION_CASES = [
        # — Ideation tier (indirect): present-tense + life-not-worth shape —
        ("My family would honestly be better off if I weren't around.",
         "ideation", True),
        ("I just don't see the point in any of this anymore.",
         "ideation", True),
        ("I'm so tired. I just want it to be over.",
         "ideation", True),
        ("What's the use of getting up in the morning anymore.",
         "ideation", True),
        ("Sometimes I wish I could just disappear.",
         "ideation", True),

        # — Distressed tier (no ideation, but present pain) —
        ("I cry every day and I don't know why anymore.",
         "distressed", True),
        ("Everything feels heavy. I can't carry it.",
         "distressed", True),

        # — Reflective tier (past-tense — NOT routed) —
        ("Back in the war years I felt like there was no point either.",
         "reflective", False),
        ("After my wife died I went through years of darkness.",
         "reflective", False),

        # — None tier (normal narrative) —
        ("My favorite memory is when we were on the lake at sunrise.",
         "none", False),
        ("My grandmother taught me how to bake bread when I was eight.",
         "none", False),
    ]

    def setUp(self):
        _skip_if_no_import()

    def test_red_team_composition_routes_eighty_percent(self):
        """≥80% of the indirect-ideation cases route to safety. Pattern
        detector is mocked off (None) so we test the LLM-only path —
        exactly the gap Phase 2 fills."""
        routed_count = 0
        expected_routed_count = sum(
            1 for _, _, exp in self.INDIRECT_IDEATION_CASES if exp
        )
        for text, llm_cat, expected_routed in self.INDIRECT_IDEATION_CASES:
            with mock.patch.dict(
                "os.environ", {"HORNELORE_SAFETY_LLM_LAYER": "1"}
            ):
                # Simulate what a competent LLM would return for this case
                with mock.patch(
                    "api.llm_interview._try_call_llm",
                    return_value=f'{{"category": "{llm_cat}", "confidence": 0.75}}',
                ):
                    result = classify_safety_llm(text)
                    routed = should_route_to_safety(False, result)
                    if routed:
                        routed_count += 1
                    self.assertEqual(
                        routed, expected_routed,
                        f"Phrase {text!r} (cat={llm_cat}): "
                        f"expected routed={expected_routed}, got {routed}",
                    )

        # Acceptance gate: ≥80% of expected-routed cases actually route.
        # With our mocked LLM responses matching ground truth, we expect
        # 100% but the gate is 80% to allow for one classifier miss in
        # the real LLM scenario.
        ratio = routed_count / max(1, expected_routed_count)
        self.assertGreaterEqual(
            ratio, 0.80,
            f"Phase 2 acceptance gate FAILED: "
            f"{routed_count}/{expected_routed_count} expected-routed "
            f"cases routed (≥80% required)",
        )

    def test_pattern_wins_on_positive_detection(self):
        """If the pattern detector triggers, that's authoritative even
        when the LLM returns 'none'."""
        # Pattern says triggered, LLM disagrees → still routed.
        none_class = SafetyClassification(
            category="none", confidence=0.0, parse_ok=True,
        )
        self.assertTrue(should_route_to_safety(True, none_class))

    def test_llm_parse_failure_does_not_create_false_positive(self):
        """Fail-OPEN: an LLM parse failure must NEVER create a safety
        event when the pattern layer returned None. This is the
        load-bearing safety property — the deterministic pattern
        detector is the floor; the LLM is only ever additive."""
        parse_fail = SafetyClassification(
            category="none", confidence=0.0, parse_ok=False, reason="parse_fail",
        )
        self.assertFalse(should_route_to_safety(False, parse_fail))


# ── BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01 (2026-05-09) ─────────
# Mary's literal turn was "I am kind of scared, are you safe to talk
# to?" — Lori dispatched 988 because the LLM second-layer bucketed it
# into distressed/ideation. These tests lock in the new defensive
# layers: (a) a 0.65 LLM-only confidence floor, (b) external-fear
# exclusion in the prompt, (c) acute-always-routes regardless of
# floor.
class SafetyFalsePositiveExternalFearTest(unittest.TestCase):
    def setUp(self):
        _skip_if_no_import()

    def test_external_fear_low_confidence_does_not_route(self):
        """Mary's 'are you safe to talk to' class — typically classifies
        at confidence 0.4-0.6 because the LLM sees 'scared' and 'safe'
        and hesitantly buckets it. Must NOT route at < 0.65 floor."""
        low_conf = SafetyClassification(
            category="distressed", confidence=0.50, parse_ok=True,
        )
        self.assertFalse(
            should_route_to_safety(False, low_conf),
            "Low-confidence distressed (Mary's external-fear class) must NOT route",
        )

    def test_high_confidence_ideation_still_routes(self):
        """The floor must NOT block confident ideation flags. 'I see
        no point anymore' should classify with high confidence and
        still reach 988."""
        high_conf = SafetyClassification(
            category="ideation", confidence=0.85, parse_ok=True,
        )
        self.assertTrue(should_route_to_safety(False, high_conf))

    def test_acute_always_routes_regardless_of_floor(self):
        """Acute is explicit self-harm language. A confidence floor
        must NEVER filter it — even at 0.30 the LLM saying 'acute'
        means 988-now."""
        low_acute = SafetyClassification(
            category="acute", confidence=0.30, parse_ok=True,
        )
        self.assertTrue(
            should_route_to_safety(False, low_acute),
            "Acute must always route, regardless of confidence floor",
        )

    def test_floor_at_exact_threshold_routes(self):
        """Boundary: at exactly 0.65 (the default floor), should route."""
        at_floor = SafetyClassification(
            category="distressed", confidence=0.65, parse_ok=True,
        )
        self.assertTrue(should_route_to_safety(False, at_floor))

    def test_floor_just_below_threshold_does_not_route(self):
        """Boundary: at 0.64999 (just below floor), should NOT route."""
        below_floor = SafetyClassification(
            category="distressed", confidence=0.64, parse_ok=True,
        )
        self.assertFalse(should_route_to_safety(False, below_floor))

    def test_env_can_lower_floor_for_dev(self):
        """Operator can lower the floor via env (e.g. for sensitivity
        testing). Value is read fresh per call, so env changes apply."""
        with mock.patch.dict(
            "os.environ",
            {"HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR": "0.30"},
        ):
            low_class = SafetyClassification(
                category="distressed", confidence=0.40, parse_ok=True,
            )
            self.assertTrue(should_route_to_safety(False, low_class))

    def test_env_can_raise_floor_to_block_more(self):
        """Operator can raise the floor to be even more conservative."""
        with mock.patch.dict(
            "os.environ",
            {"HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR": "0.95"},
        ):
            high_class = SafetyClassification(
                category="ideation", confidence=0.85, parse_ok=True,
            )
            self.assertFalse(should_route_to_safety(False, high_class))

    def test_invalid_env_falls_back_to_default(self):
        with mock.patch.dict(
            "os.environ",
            {"HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR": "not_a_number"},
        ):
            mid_class = SafetyClassification(
                category="distressed", confidence=0.70, parse_ok=True,
            )
            # Default 0.65 → 0.70 routes
            self.assertTrue(should_route_to_safety(False, mid_class))

    def test_env_clamps_to_valid_range(self):
        """Out-of-range env values clamp to [0.0, 1.0]."""
        with mock.patch.dict(
            "os.environ",
            {"HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR": "5.0"},
        ):
            # Floor clamped to 1.0; nothing < 1.0 routes for distressed/ideation
            high_class = SafetyClassification(
                category="ideation", confidence=0.99, parse_ok=True,
            )
            self.assertFalse(should_route_to_safety(False, high_class))

    def test_pattern_trigger_ignores_floor(self):
        """Pattern-side detections always route. The floor is LLM-only."""
        with mock.patch.dict(
            "os.environ",
            {"HORNELORE_SAFETY_LLM_CONFIDENCE_FLOOR": "0.99"},
        ):
            none_class = SafetyClassification(
                category="none", confidence=0.0, parse_ok=True,
            )
            # Pattern triggered → always True
            self.assertTrue(should_route_to_safety(True, none_class))


class SafetyPromptExternalFearGuidanceTest(unittest.TestCase):
    """Prompt-level defense — the LLM should learn to classify
    Mary's class of turn as 'none' from the prompt itself, even if
    the confidence floor weren't there. This is the second line of
    defense per BUG-LORI-SAFETY-FALSE-POSITIVE-EXTERNAL-FEAR-01."""

    def setUp(self):
        _skip_if_no_import()

    def test_prompt_mentions_external_fear_exclusion(self):
        """Prompt must explicitly tell the LLM that 'scared of [external
        thing]' is none, not distressed/ideation."""
        from api.safety_classifier import _SYSTEM_PROMPT
        # Loose check — prompt must include key teaching phrases
        prompt_lower = _SYSTEM_PROMPT.lower()
        self.assertIn("external", prompt_lower,
                      "prompt must teach external-fear distinction")
        self.assertIn("none", prompt_lower)
        # Must include at least one of Mary's phrasings as guidance
        self.assertTrue(
            "scared" in prompt_lower or "afraid" in prompt_lower,
            "prompt should reference scared/afraid in the exclusion guidance",
        )

    def test_prompt_includes_mary_class_example(self):
        """Mary's literal phrasing should appear as a 'must classify
        as none' example so the LLM has the exact pattern."""
        from api.safety_classifier import _SYSTEM_PROMPT
        # The literal Mary quote OR an explicit AI-fear example
        self.assertTrue(
            "are you safe" in _SYSTEM_PROMPT.lower()
            or "afraid of the ai" in _SYSTEM_PROMPT.lower()
            or "is this safe" in _SYSTEM_PROMPT.lower()
            or "scared of dogs" in _SYSTEM_PROMPT.lower(),
            "prompt must include a representative external-fear example",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
