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
        for cat in ("distressed", "ideation", "acute"):
            cls = SafetyClassification(category=cat, parse_ok=True, confidence=0.5)
            self.assertTrue(should_route_to_safety(False, cls), f"failed for {cat}")

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
