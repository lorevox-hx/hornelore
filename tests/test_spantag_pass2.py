"""WO-EX-SPANTAG-01 Commit 2 — Pass 2 scaffold unit tests.

Covers the four pure helpers introduced in Commit 2:
  - _build_spantag_pass2_prompt: prompt shape, controlled-prior surface
  - _parse_spantag_pass2: tolerant JSON parser for Pass 2 LLM output
  - _spantag_pass2_normalize_write: per-write validation
  - _spantag_pass2_normalize_no_write: per-refusal validation
  - _spantag_extract_balanced_object_for: key-scoped balanced-object scan

No LLM is called. No API is started. These are pure-function tests over
hand-written inputs exercising each branch: well-formed JSON, fences,
prose wrapping, missing fields, illegal tag IDs, out-of-range spans,
normalized values, dual-path writes, polarity-driven no_write entries.

Run with:
    cd hornelore
    python -m unittest tests.test_spantag_pass2
"""
from __future__ import annotations

import json
import logging
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# Stub FastAPI + pydantic so we can import extract.py without the full
# server deps installed. Same pattern as tests/test_spantag_pass1.py.
if "fastapi" not in sys.modules:
    fa = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **kw):
            pass

        def post(self, *a, **kw):
            def deco(fn):
                return fn

            return deco

        def get(self, *a, **kw):
            def deco(fn):
                return fn

            return deco

    class _HTTPException(Exception):
        pass

    fa.APIRouter = _APIRouter
    fa.HTTPException = _HTTPException
    sys.modules["fastapi"] = fa

if "pydantic" not in sys.modules:
    pd = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    pd.BaseModel = _BaseModel
    sys.modules["pydantic"] = pd

from api.routers.extract import (  # noqa: E402
    _SPANTAG_PASS2_PRIORITIES,
    _build_spantag_pass2_prompt,
    _parse_spantag_pass2,
    _spantag_extract_balanced_object_for,
    _spantag_pass2_normalize_no_write,
    _spantag_pass2_normalize_write,
)


# Silence info-level scaffold logs during tests; warnings still surface.
logging.getLogger("lorevox.extract").setLevel(logging.WARNING)


# ──────────────────────────────────────────────────────────────────────────────
# BuildPass2PromptTests
# ──────────────────────────────────────────────────────────────────────────────


class BuildPass2PromptTests(unittest.TestCase):
    """The Pass 2 prompt is schema-aware and surfaces the controlled priors
    explicitly. Unlike Pass 1, Pass 2 IS allowed to see section / target_path /
    era / pass / mode and the allowed output space."""

    def test_prompt_carries_priors_explicitly(self):
        tags = [{"id": "t0", "type": "person", "text": "Janice",
                 "start": 10, "end": 16, "polarity": "asserted"}]
        _, user = _build_spantag_pass2_prompt(
            "I married Janice in 1959.",
            tags,
            current_section="marriage",
            current_target_path="family.spouse",
            current_era="early_adulthood",
            current_pass="pass1",
            current_mode="interview",
        )
        self.assertIn("marriage", user)
        self.assertIn("family.spouse", user)
        self.assertIn("early_adulthood", user)
        self.assertIn("pass1", user)
        self.assertIn("interview", user)

    def test_prompt_surfaces_allowed_field_paths(self):
        _, user = _build_spantag_pass2_prompt(
            "dummy",
            [],
            allowed_field_paths=[
                "family.spouse.firstName",
                "family.spouse.lastName",
                "family.marriageDate",
            ],
        )
        self.assertIn("family.spouse.firstName", user)
        self.assertIn("family.marriageDate", user)

    def test_prompt_includes_pass1_tags_as_json(self):
        tags = [
            {"id": "t0", "type": "person", "text": "Bob",
             "start": 0, "end": 3, "polarity": "asserted"},
        ]
        _, user = _build_spantag_pass2_prompt("Bob", tags)
        self.assertIn('"id": "t0"', user)
        self.assertIn('"type": "person"', user)

    def test_prompt_carries_extract_priority(self):
        _, user = _build_spantag_pass2_prompt(
            "dummy", [],
            extract_priority=["family.spouse", "family.marriageDate"],
        )
        self.assertIn("family.spouse", user)
        self.assertIn("family.marriageDate", user)

    def test_prompt_carries_narrator_identity(self):
        _, user = _build_spantag_pass2_prompt(
            "dummy", [],
            narrator_identity={"firstName": "Harold", "lastName": "Zarr"},
        )
        self.assertIn("Harold", user)

    def test_prompt_describes_subject_beats_section_rule(self):
        system, _ = _build_spantag_pass2_prompt("dummy", [])
        # The binding rule must be on the system prompt surface — this is
        # the core mechanism SPANTAG is designed to teach the model.
        self.assertIn("ubject", system)
        self.assertIn("ection", system)

    def test_prompt_describes_dual_path_emission(self):
        system, _ = _build_spantag_pass2_prompt("dummy", [])
        self.assertIn("PRIMARY", system)
        self.assertIn("SECONDARY", system)

    def test_prompt_describes_polarity_no_write_rules(self):
        system, _ = _build_spantag_pass2_prompt("dummy", [])
        self.assertIn("negated", system)
        self.assertIn("hypothetical", system)

    def test_prompt_specifies_output_contract(self):
        system, _ = _build_spantag_pass2_prompt("dummy", [])
        self.assertIn('"writes"', system)
        self.assertIn('"no_write"', system)
        self.assertIn('"fieldPath"', system)
        self.assertIn('"sourceSpan"', system)
        self.assertIn('"sourceTagIds"', system)

    def test_prompt_handles_missing_optional_inputs(self):
        # When all optional args are None/empty, the prompt must still build.
        system, user = _build_spantag_pass2_prompt("answer", [])
        self.assertIsInstance(system, str)
        self.assertIsInstance(user, str)
        self.assertIn("answer", user)
        self.assertIn("(none supplied)", user)


# ──────────────────────────────────────────────────────────────────────────────
# ParsePass2WellFormedTests
# ──────────────────────────────────────────────────────────────────────────────


class ParsePass2WellFormedTests(unittest.TestCase):
    """Happy path: LLM returns clean JSON with writes + no_write."""

    def _pass1_set(self):
        return [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": 10, "end": 16, "polarity": "asserted"},
            {"id": "t1", "type": "date_text", "text": "1959",
             "start": 20, "end": 24, "polarity": "asserted"},
            {"id": "t2", "type": "quantity_or_ordinal", "text": "twenty",
             "start": 30, "end": 36, "polarity": "asserted"},
        ]

    def test_clean_single_write(self):
        answer = "I married Janice in 1959, she was twenty."
        raw = json.dumps({
            "writes": [
                {
                    "fieldPath": "family.spouse.firstName",
                    "value": "Janice",
                    "confidence": 0.95,
                    "priority": "primary",
                    "sourceSpan": {"start": 10, "end": 16},
                    "sourceTagIds": ["t0"],
                },
            ],
            "no_write": [],
        })
        out = _parse_spantag_pass2(raw, self._pass1_set(), answer)
        self.assertEqual(len(out["writes"]), 1)
        self.assertEqual(len(out["no_write"]), 0)
        w = out["writes"][0]
        self.assertEqual(w["fieldPath"], "family.spouse.firstName")
        self.assertEqual(w["value"], "Janice")
        self.assertAlmostEqual(w["confidence"], 0.95)
        self.assertEqual(w["priority"], "primary")
        self.assertEqual(w["sourceTagIds"], ["t0"])
        self.assertEqual(w["sourceSpan"], {"start": 10, "end": 16})

    def test_no_write_entry_preserved(self):
        answer = "I married Janice in 1959, she was twenty."
        raw = json.dumps({
            "writes": [],
            "no_write": [
                {"reason": "age_at_event_not_a_dob", "sourceTagIds": ["t2"]},
            ],
        })
        out = _parse_spantag_pass2(raw, self._pass1_set(), answer)
        self.assertEqual(len(out["writes"]), 0)
        self.assertEqual(len(out["no_write"]), 1)
        self.assertEqual(out["no_write"][0]["reason"], "age_at_event_not_a_dob")
        self.assertEqual(out["no_write"][0]["sourceTagIds"], ["t2"])

    def test_dual_path_primary_and_secondary(self):
        """The signature case_008-style output: one primary subject-driven
        write + one secondary section-driven write with alt_path_section_driven
        and disagreement_reason."""
        answer = "My mom's brother James was born in a car during a blizzard."
        pass1 = [
            {"id": "t0", "type": "person", "text": "James",
             "start": 23, "end": 28, "polarity": "asserted"},
            {"id": "t1", "type": "event_phrase", "text": "born in a car during a blizzard",
             "start": 29, "end": 60, "polarity": "asserted"},
        ]
        raw = json.dumps({
            "writes": [
                {
                    "fieldPath": "parents.notableLifeEvents",
                    "value": "James born in a car during a blizzard",
                    "confidence": 0.85,
                    "priority": "primary",
                    "sourceTagIds": ["t0", "t1"],
                    "disagreement_reason": "subject_beats_section",
                },
                {
                    "fieldPath": "earlyMemories.significantEvent",
                    "value": "James born in a car during a blizzard",
                    "confidence": 0.55,
                    "priority": "secondary",
                    "sourceTagIds": ["t1"],
                    "alt_path_section_driven": True,
                    "disagreement_reason": "section_current_target_path_match",
                },
            ],
            "no_write": [],
        })
        out = _parse_spantag_pass2(raw, pass1, answer)
        self.assertEqual(len(out["writes"]), 2)
        primary, secondary = out["writes"]
        self.assertEqual(primary["priority"], "primary")
        self.assertEqual(secondary["priority"], "secondary")
        self.assertEqual(secondary["alt_path_section_driven"], True)
        self.assertEqual(primary["disagreement_reason"], "subject_beats_section")

    def test_normalization_field_preserved(self):
        answer = "I married Janice on October 10th, 1959."
        pass1 = [
            {"id": "t0", "type": "date_text", "text": "October 10th, 1959",
             "start": 20, "end": 38, "polarity": "asserted"},
        ]
        raw = json.dumps({
            "writes": [
                {
                    "fieldPath": "family.marriageDate",
                    "value": "1959-10-10",
                    "confidence": 0.9,
                    "priority": "primary",
                    "sourceTagIds": ["t0"],
                    "sourceSpan": {"start": 20, "end": 38},
                    "normalization": {
                        "raw": "October 10th, 1959",
                        "normalized": "1959-10-10",
                    },
                },
            ],
            "no_write": [],
        })
        out = _parse_spantag_pass2(raw, pass1, answer)
        self.assertEqual(len(out["writes"]), 1)
        self.assertEqual(
            out["writes"][0]["normalization"]["normalized"], "1959-10-10"
        )

    def test_empty_writes_and_no_write(self):
        raw = '{"writes": [], "no_write": []}'
        out = _parse_spantag_pass2(raw, [], "anything")
        self.assertEqual(out, {"writes": [], "no_write": []})


# ──────────────────────────────────────────────────────────────────────────────
# ParsePass2MalformedTests
# ──────────────────────────────────────────────────────────────────────────────


class ParsePass2MalformedTests(unittest.TestCase):

    def test_prose_leading_recovered(self):
        answer = "I married Janice."
        pass1 = [{"id": "t0", "type": "person", "text": "Janice",
                  "start": 10, "end": 16, "polarity": "asserted"}]
        raw = (
            "Here are the writes you requested:\n"
            '{"writes": [{"fieldPath": "family.spouse.firstName", '
            '"value": "Janice", "confidence": 0.9, "priority": "primary", '
            '"sourceTagIds": ["t0"]}], "no_write": []}'
        )
        out = _parse_spantag_pass2(raw, pass1, answer)
        self.assertEqual(len(out["writes"]), 1)

    def test_json_fence_stripped(self):
        answer = "I married Janice."
        pass1 = [{"id": "t0", "type": "person", "text": "Janice",
                  "start": 10, "end": 16, "polarity": "asserted"}]
        raw = (
            "```json\n"
            '{"writes": [{"fieldPath": "family.spouse.firstName", '
            '"value": "Janice", "confidence": 0.9, "priority": "primary", '
            '"sourceTagIds": ["t0"]}], "no_write": []}\n'
            "```"
        )
        out = _parse_spantag_pass2(raw, pass1, answer)
        self.assertEqual(len(out["writes"]), 1)

    def test_only_no_write_object_recovered(self):
        """Model refused everything — 'writes' key may be absent entirely.
        The balanced-object scan falls through to the 'no_write' key."""
        pass1 = [{"id": "t0", "type": "person", "text": "x",
                  "start": 0, "end": 1, "polarity": "asserted"}]
        raw = (
            'prefix {"no_write": [{"reason": "negated_in_source", '
            '"sourceTagIds": ["t0"]}]} suffix'
        )
        out = _parse_spantag_pass2(raw, pass1, "x")
        self.assertEqual(out["writes"], [])
        self.assertEqual(len(out["no_write"]), 1)
        self.assertEqual(out["no_write"][0]["reason"], "negated_in_source")

    def test_catastrophic_parse_failure_returns_empty(self):
        out = _parse_spantag_pass2("total garbage no json", [], "x")
        self.assertEqual(out, {"writes": [], "no_write": []})

    def test_empty_raw_returns_empty(self):
        out = _parse_spantag_pass2("", [], "x")
        self.assertEqual(out, {"writes": [], "no_write": []})

    def test_top_level_array_rejected(self):
        # Pass 2 contract is an object, not an array.
        out = _parse_spantag_pass2('["not an object"]', [], "x")
        self.assertEqual(out, {"writes": [], "no_write": []})

    def test_writes_not_a_list(self):
        out = _parse_spantag_pass2(
            '{"writes": "not a list", "no_write": []}', [], "x",
        )
        self.assertEqual(out["writes"], [])
        self.assertEqual(out["no_write"], [])


# ──────────────────────────────────────────────────────────────────────────────
# NormalizeWriteTests
# ──────────────────────────────────────────────────────────────────────────────


class NormalizeWriteTests(unittest.TestCase):
    """_spantag_pass2_normalize_write enforces per-write discipline."""

    def test_missing_field_path_dropped(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"value": "x", "sourceTagIds": ["t0"]}, 0, legal, "x",
        )
        self.assertIsNone(out)

    def test_empty_field_path_dropped(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "   ", "value": "x", "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertIsNone(out)

    def test_missing_value_key_dropped(self):
        # Even an explicit None value is permitted, but the key must exist.
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "family.spouse.firstName", "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertIsNone(out)

    def test_null_value_allowed(self):
        # The LLM may legitimately want to write a null marker; downstream
        # guards will reject it. Parser discipline only requires the key.
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "family.spouse.firstName",
             "value": None, "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertIsNotNone(out)
        self.assertIsNone(out["value"])

    def test_non_dict_dropped(self):
        out = _spantag_pass2_normalize_write("not a dict", 0, set(), "x")
        self.assertIsNone(out)

    def test_confidence_clamped_high(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "confidence": 1.7, "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertEqual(out["confidence"], 1.0)

    def test_confidence_clamped_low(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "confidence": -0.4, "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertEqual(out["confidence"], 0.0)

    def test_confidence_unparseable_defaults_to_zero(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "confidence": "high", "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertEqual(out["confidence"], 0.0)

    def test_confidence_default_when_missing(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x", "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertAlmostEqual(out["confidence"], 0.5)

    def test_priority_unknown_defaults_primary(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "priority": "urgent", "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertEqual(out["priority"], "primary")

    def test_priority_values_preserved(self):
        legal = {"t0"}
        for pri in _SPANTAG_PASS2_PRIORITIES:
            out = _spantag_pass2_normalize_write(
                {"fieldPath": "a.b", "value": "x",
                 "priority": pri, "sourceTagIds": ["t0"]},
                0, legal, "x",
            )
            self.assertEqual(out["priority"], pri)

    def test_illegal_tag_ids_filtered(self):
        legal = {"t0", "t1"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "sourceTagIds": ["t0", "t_ghost", "t1", 42]},
            0, legal, "x",
        )
        # t_ghost + integer 42 are filtered; t0 and t1 kept.
        self.assertEqual(out["sourceTagIds"], ["t0", "t1"])

    def test_all_tag_ids_illegal_keeps_write(self):
        # The write is preserved (rules-based writes may not have tag
        # anchors) but the sourceTagIds ends up empty.
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x", "sourceTagIds": ["ghost"]},
            0, legal, "x",
        )
        self.assertIsNotNone(out)
        self.assertEqual(out["sourceTagIds"], [])

    def test_source_span_out_of_range_stripped(self):
        legal = {"t0"}
        answer = "Short."  # len=6
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "sourceSpan": {"start": 0, "end": 100},
             "sourceTagIds": ["t0"]},
            0, legal, answer,
        )
        self.assertIsNotNone(out)
        self.assertNotIn("sourceSpan", out)

    def test_source_span_valid_preserved(self):
        legal = {"t0"}
        answer = "I married Janice."  # len=17
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "family.spouse.firstName", "value": "Janice",
             "sourceSpan": {"start": 10, "end": 16},
             "sourceTagIds": ["t0"]},
            0, legal, answer,
        )
        self.assertEqual(out["sourceSpan"], {"start": 10, "end": 16})

    def test_source_span_non_int_stripped(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "sourceSpan": {"start": "10", "end": "16"},
             "sourceTagIds": ["t0"]},
            0, legal, "I married Janice.",
        )
        self.assertNotIn("sourceSpan", out)

    def test_source_span_not_a_dict_stripped(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "sourceSpan": [10, 16],
             "sourceTagIds": ["t0"]},
            0, legal, "I married Janice.",
        )
        self.assertNotIn("sourceSpan", out)

    def test_alt_path_flag_passthrough(self):
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "alt_path_section_driven": True,
             "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertTrue(out["alt_path_section_driven"])

    def test_alt_path_flag_false_not_emitted(self):
        # Only emit the flag when truthy — keeps the write shape minimal for
        # the default (primary subject-driven) case.
        legal = {"t0"}
        out = _spantag_pass2_normalize_write(
            {"fieldPath": "a.b", "value": "x",
             "alt_path_section_driven": False,
             "sourceTagIds": ["t0"]},
            0, legal, "x",
        )
        self.assertNotIn("alt_path_section_driven", out)


# ──────────────────────────────────────────────────────────────────────────────
# NormalizeNoWriteTests
# ──────────────────────────────────────────────────────────────────────────────


class NormalizeNoWriteTests(unittest.TestCase):

    def test_missing_reason_dropped(self):
        out = _spantag_pass2_normalize_no_write(
            {"sourceTagIds": ["t0"]}, 0, {"t0"},
        )
        self.assertIsNone(out)

    def test_empty_reason_dropped(self):
        out = _spantag_pass2_normalize_no_write(
            {"reason": "   ", "sourceTagIds": ["t0"]}, 0, {"t0"},
        )
        self.assertIsNone(out)

    def test_non_dict_dropped(self):
        out = _spantag_pass2_normalize_no_write("negated", 0, set())
        self.assertIsNone(out)

    def test_illegal_tag_ids_filtered(self):
        out = _spantag_pass2_normalize_no_write(
            {"reason": "negated_in_source",
             "sourceTagIds": ["t0", "ghost", 99]},
            0, {"t0"},
        )
        self.assertEqual(out["sourceTagIds"], ["t0"])

    def test_missing_tag_ids_defaulted_empty(self):
        out = _spantag_pass2_normalize_no_write(
            {"reason": "negated_in_source"}, 0, set(),
        )
        self.assertEqual(out, {"reason": "negated_in_source", "sourceTagIds": []})


# ──────────────────────────────────────────────────────────────────────────────
# ExtractBalancedObjectForTests
# ──────────────────────────────────────────────────────────────────────────────


class ExtractBalancedObjectForTests(unittest.TestCase):
    """_spantag_extract_balanced_object_for is the Pass 2 key-scoped form
    of the Pass 1 balanced-object helper. Same brace-matching logic,
    different target key."""

    def test_finds_writes_object(self):
        text = 'prefix {"writes": [{"fieldPath": "a.b"}]} suffix'
        obj = _spantag_extract_balanced_object_for(text, key="writes")
        self.assertIsNotNone(obj)
        self.assertIn("writes", obj)

    def test_finds_no_write_object(self):
        text = 'junk {"no_write": [{"reason": "negated"}]} more'
        obj = _spantag_extract_balanced_object_for(text, key="no_write")
        self.assertIsNotNone(obj)
        self.assertIn("no_write", obj)

    def test_skips_unrelated_objects(self):
        text = '{"other": 1} then {"writes": []}'
        obj = _spantag_extract_balanced_object_for(text, key="writes")
        self.assertIsNotNone(obj)
        self.assertIn("writes", obj)

    def test_returns_none_on_no_match(self):
        text = "no json anywhere"
        self.assertIsNone(
            _spantag_extract_balanced_object_for(text, key="writes")
        )

    def test_ignores_braces_in_strings(self):
        text = '{"writes": [{"value": "with { brace"}]}'
        obj = _spantag_extract_balanced_object_for(text, key="writes")
        self.assertIsNotNone(obj)
        self.assertEqual(obj["writes"][0]["value"], "with { brace")

    def test_handles_escape_inside_string(self):
        # An escaped quote shouldn't end string mode.
        text = '{"writes": [{"value": "line\\"break"}]}'
        obj = _spantag_extract_balanced_object_for(text, key="writes")
        self.assertIsNotNone(obj)
        self.assertEqual(obj["writes"][0]["value"], 'line"break')


# ──────────────────────────────────────────────────────────────────────────────
# EndToEndShapeTests
# ──────────────────────────────────────────────────────────────────────────────


class EndToEndShapeTests(unittest.TestCase):
    """Integration-style tests across _parse_spantag_pass2 that exercise the
    full normalization pipeline on realistic outputs."""

    def test_polarity_driven_no_write(self):
        """Parser preserves the refusal contract for negated-polarity
        tags. The Pass 2 model declines to write, logs a reason, cites
        the source tag."""
        answer = "We never went to church."
        pass1 = [
            {"id": "t0", "type": "organization", "text": "church",
             "start": 17, "end": 23, "polarity": "negated"},
        ]
        raw = json.dumps({
            "writes": [],
            "no_write": [
                {"reason": "negated_in_source", "sourceTagIds": ["t0"]},
            ],
        })
        out = _parse_spantag_pass2(raw, pass1, answer)
        self.assertEqual(len(out["writes"]), 0)
        self.assertEqual(out["no_write"][0]["reason"], "negated_in_source")
        self.assertEqual(out["no_write"][0]["sourceTagIds"], ["t0"])

    def test_mixed_writes_and_refusals(self):
        """The case_012-class regression fix: model writes what it can and
        explicitly refuses the age-mistaken-for-DOB inference."""
        answer = "I married Janice in 1959, she was twenty."
        pass1 = [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": 10, "end": 16, "polarity": "asserted"},
            {"id": "t1", "type": "date_text", "text": "1959",
             "start": 20, "end": 24, "polarity": "asserted"},
            {"id": "t2", "type": "quantity_or_ordinal", "text": "twenty",
             "start": 34, "end": 40, "polarity": "asserted"},
        ]
        raw = json.dumps({
            "writes": [
                {"fieldPath": "family.spouse.firstName", "value": "Janice",
                 "confidence": 0.95, "priority": "primary",
                 "sourceTagIds": ["t0"]},
                {"fieldPath": "family.marriageDate", "value": "1959",
                 "confidence": 0.9, "priority": "primary",
                 "sourceTagIds": ["t1"]},
            ],
            "no_write": [
                {"reason": "age_at_event_not_a_dob", "sourceTagIds": ["t2"]},
            ],
        })
        out = _parse_spantag_pass2(raw, pass1, answer)
        self.assertEqual(len(out["writes"]), 2)
        self.assertEqual(len(out["no_write"]), 1)
        paths = [w["fieldPath"] for w in out["writes"]]
        self.assertIn("family.spouse.firstName", paths)
        self.assertIn("family.marriageDate", paths)

    def test_malformed_write_dropped_peer_preserved(self):
        """One malformed write (missing value) is dropped; the other survives."""
        pass1 = [{"id": "t0", "type": "person", "text": "x",
                  "start": 0, "end": 1, "polarity": "asserted"}]
        raw = json.dumps({
            "writes": [
                {"fieldPath": "a.b", "sourceTagIds": ["t0"]},
                # Legal peer:
                {"fieldPath": "a.c", "value": "ok",
                 "confidence": 0.7, "sourceTagIds": ["t0"]},
            ],
            "no_write": [],
        })
        out = _parse_spantag_pass2(raw, pass1, "x")
        self.assertEqual(len(out["writes"]), 1)
        self.assertEqual(out["writes"][0]["fieldPath"], "a.c")


if __name__ == "__main__":
    unittest.main()
