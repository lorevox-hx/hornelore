"""WO-EX-SPANTAG-01 Commit 1 — Pass 1 scaffold unit tests.

Covers the three pure helpers introduced in Commit 1:
  - _build_spantag_pass1_prompt: prompt shape, schema-blindness
  - _parse_spantag_pass1: tolerant JSON parser for LLM output
  - _relocate_spans: substring-invariant offset correction

No LLM is called. No API is started. These are pure-function tests over
hand-written inputs that exercise each branch of the parser: well-formed
JSON, malformed JSON with trailing prose, missing polarity, offset drift,
orphan spans, duplicate IDs, unknown tag types, ```json fences, and the
permissive-regex recovery path.

Run with:
    cd hornelore
    python -m unittest tests.test_spantag_pass1
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
# server deps installed. Matches the pattern used in
# tests/test_extract_subject_filters.py.
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
    _SPANTAG_POLARITY_VALUES,
    _SPANTAG_TAG_TYPES,
    _build_spantag_pass1_prompt,
    _parse_spantag_pass1,
    _relocate_spans,
    _spantag_extract_balanced_object,
    _spantag_regex_recover_tags,
)


# Silence the scaffold's info logs during tests. Warnings are still shown
# so catastrophic parse failures surface in the test runner output.
logging.getLogger("lorevox.extract").setLevel(logging.WARNING)


class BuildPass1PromptTests(unittest.TestCase):
    """The Pass 1 prompt must be schema-blind and carry the 10-tag NL
    inventory in the stable order defined in the WO spec."""

    def test_prompt_is_schema_blind(self):
        answer = "I was born in 1942 and married Janice in 1959."
        system, user = _build_spantag_pass1_prompt(
            answer,
            current_section="earlyMemories",
            current_target_path="parents.notableLifeEvents",
        )
        # The section and target path must NOT leak into the Pass 1 prompt.
        # Pass 2 will consume them as controlled priors; Pass 1 is evidence-only.
        self.assertNotIn("earlyMemories", system)
        self.assertNotIn("earlyMemories", user)
        self.assertNotIn("parents.notableLifeEvents", system)
        self.assertNotIn("parents.notableLifeEvents", user)
        # No dotted fieldPaths anywhere.
        self.assertNotIn("fieldPath", system)
        self.assertNotIn("family.spouse", system)

    def test_prompt_lists_all_ten_tag_types(self):
        system, _ = _build_spantag_pass1_prompt("dummy")
        for tag_type in _SPANTAG_TAG_TYPES:
            self.assertIn(tag_type, system,
                          f"tag type {tag_type!r} missing from Pass 1 system prompt")
        # Exactly ten.
        self.assertEqual(len(_SPANTAG_TAG_TYPES), 10)

    def test_prompt_includes_answer_in_user_turn(self):
        answer = "My dog was named Ivan."
        _, user = _build_spantag_pass1_prompt(answer)
        self.assertIn(answer, user)

    def test_prompt_specifies_polarity_values(self):
        system, _ = _build_spantag_pass1_prompt("dummy")
        # All three polarity values must be described for the LLM.
        for pol in _SPANTAG_POLARITY_VALUES:
            self.assertIn(pol, system)

    def test_prompt_specifies_json_output_contract(self):
        system, _ = _build_spantag_pass1_prompt("dummy")
        self.assertIn('"tags"', system)
        self.assertIn('"id"', system)
        self.assertIn('"type"', system)
        self.assertIn('"start"', system)
        self.assertIn('"end"', system)
        self.assertIn('"polarity"', system)


class ParsePass1WellFormedTests(unittest.TestCase):
    """Happy path: the LLM returns clean JSON. Parser preserves everything."""

    def test_clean_json_three_tags(self):
        answer = "I married Janice on October 10th, 1959."
        # Offsets match the substrings in `answer`.
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "relation_cue", "text": "married",
                 "start": 2, "end": 9, "polarity": "asserted"},
                {"id": "t1", "type": "person", "text": "Janice",
                 "start": 10, "end": 16, "polarity": "asserted"},
                {"id": "t2", "type": "date_text", "text": "October 10th, 1959",
                 "start": 20, "end": 38, "polarity": "asserted"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 3)
        ids = [t["id"] for t in tags]
        self.assertEqual(ids, ["t0", "t1", "t2"])
        self.assertEqual(tags[1]["text"], "Janice")
        self.assertEqual(tags[1]["polarity"], "asserted")

    def test_empty_tags_array(self):
        answer = "Hmm."
        raw = '{"tags": []}'
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(tags, [])


class ParsePass1MalformedTests(unittest.TestCase):
    """Recovery paths: prose wrapping, fences, missing braces."""

    def test_json_wrapped_in_prose_leading(self):
        answer = "I was born in 1942."
        raw = (
            "Sure, here is the tag inventory you requested:\n\n"
            '{"tags": [{"id": "t0", "type": "date_text", "text": "1942", '
            '"start": 15, "end": 19, "polarity": "asserted"}]}'
        )
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["text"], "1942")

    def test_json_wrapped_in_prose_trailing(self):
        answer = "I was born in 1942."
        raw = (
            '{"tags": [{"id": "t0", "type": "date_text", "text": "1942", '
            '"start": 15, "end": 19, "polarity": "asserted"}]}\n\n'
            "Let me know if you need more tags."
        )
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)

    def test_json_in_code_fence(self):
        answer = "I was born in 1942."
        raw = (
            "```json\n"
            '{"tags": [{"id": "t0", "type": "date_text", "text": "1942", '
            '"start": 15, "end": 19, "polarity": "asserted"}]}\n'
            "```"
        )
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)

    def test_regex_recovery_when_object_malformed(self):
        answer = "I was born in 1942."
        # The surrounding object is malformed (missing closing brace)
        # but the inner tags array is well-formed JSON.
        raw = (
            'junk prefix "tags": [{"id": "t0", "type": "date_text", '
            '"text": "1942", "start": 15, "end": 19, "polarity": "asserted"}]'
        )
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["text"], "1942")

    def test_catastrophic_parse_failure_returns_empty(self):
        answer = "x"
        # No JSON structure at all, no tags key.
        raw = "I don't understand the question."
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(tags, [])

    def test_empty_raw_returns_empty(self):
        tags = _parse_spantag_pass1("", "some answer")
        self.assertEqual(tags, [])

    def test_tags_not_a_list_returns_empty(self):
        raw = '{"tags": "not an array"}'
        tags = _parse_spantag_pass1(raw, "answer")
        self.assertEqual(tags, [])

    def test_top_level_not_an_object_returns_empty(self):
        raw = '["not", "an", "object"]'
        tags = _parse_spantag_pass1(raw, "answer")
        self.assertEqual(tags, [])


class ParsePass1NormalizationTests(unittest.TestCase):
    """Field-level normalization: missing polarity, unknown types, duplicate IDs."""

    def test_missing_polarity_defaults_to_asserted(self):
        answer = "I married Janice."
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "person", "text": "Janice",
                 "start": 10, "end": 16},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["polarity"], "asserted")

    def test_unknown_polarity_defaults_to_asserted(self):
        answer = "I married Janice."
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "person", "text": "Janice",
                 "start": 10, "end": 16, "polarity": "whatever"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["polarity"], "asserted")

    def test_negated_polarity_preserved(self):
        answer = "We never went to church."
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "organization", "text": "church",
                 "start": 17, "end": 23, "polarity": "negated"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["polarity"], "negated")

    def test_unknown_tag_type_dropped(self):
        answer = "x"
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "bogus_type", "text": "x",
                 "start": 0, "end": 1, "polarity": "asserted"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(tags, [])

    def test_duplicate_ids_second_dropped(self):
        answer = "Janice married Bob."
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "person", "text": "Janice",
                 "start": 0, "end": 6, "polarity": "asserted"},
                # Duplicate id — second should be dropped.
                {"id": "t0", "type": "person", "text": "Bob",
                 "start": 15, "end": 18, "polarity": "asserted"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["text"], "Janice")

    def test_empty_text_dropped(self):
        answer = "x"
        raw = json.dumps({
            "tags": [
                {"id": "t0", "type": "person", "text": "",
                 "start": 0, "end": 0, "polarity": "asserted"},
                {"id": "t1", "type": "person", "text": "   ",
                 "start": 0, "end": 3, "polarity": "asserted"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(tags, [])

    def test_non_dict_tag_entry_skipped(self):
        answer = "Janice."
        raw = json.dumps({
            "tags": [
                "not a dict",
                {"id": "t0", "type": "person", "text": "Janice",
                 "start": 0, "end": 6, "polarity": "asserted"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["id"], "t0")

    def test_missing_id_auto_assigned(self):
        answer = "Janice."
        raw = json.dumps({
            "tags": [
                {"type": "person", "text": "Janice",
                 "start": 0, "end": 6, "polarity": "asserted"},
            ]
        })
        tags = _parse_spantag_pass1(raw, answer)
        self.assertEqual(len(tags), 1)
        # Auto-assigned id follows the t<idx> convention.
        self.assertEqual(tags[0]["id"], "t0")


class RelocateSpansTests(unittest.TestCase):
    """_relocate_spans is the substring-invariant parser discipline —
    orphan spans must be dropped, drifted offsets must be corrected."""

    def test_matching_offsets_passthrough(self):
        answer = "I married Janice in 1959."
        spans = [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": 10, "end": 16, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, answer)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], 10)
        self.assertEqual(result[0]["end"], 16)

    def test_drifted_offsets_corrected(self):
        answer = "I married Janice in 1959."
        # Claimed offsets (0, 6) → "I marr" which does not equal "Janice".
        # The text IS present at (10, 16) and should be recovered.
        spans = [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": 0, "end": 6, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, answer)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], 10)
        self.assertEqual(result[0]["end"], 16)

    def test_missing_offsets_located_by_substring(self):
        answer = "I married Janice in 1959."
        spans = [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": None, "end": None, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, answer)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], 10)
        self.assertEqual(result[0]["end"], 16)

    def test_orphan_span_dropped(self):
        answer = "I married Janice."
        spans = [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": 10, "end": 16, "polarity": "asserted"},
            # "Ethel" is not in the answer — orphan.
            {"id": "t1", "type": "person", "text": "Ethel",
             "start": 50, "end": 55, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, answer)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "t0")

    def test_empty_answer_drops_everything(self):
        spans = [
            {"id": "t0", "type": "person", "text": "Janice",
             "start": 0, "end": 6, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, "")
        self.assertEqual(result, [])

    def test_first_occurrence_wins(self):
        # When the tag text appears multiple times, substring-search returns
        # the first occurrence. This is documented behavior: the LLM should
        # be emitting unique spans; if it duplicates, we take the first.
        answer = "Bob met Bob at the store."
        spans = [
            {"id": "t0", "type": "person", "text": "Bob",
             "start": 8, "end": 11, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, answer)
        self.assertEqual(len(result), 1)
        # Fast path: claimed offsets already point to a valid "Bob" — preserved.
        self.assertEqual(result[0]["start"], 8)
        self.assertEqual(result[0]["end"], 11)

        # Now test the slow-path relocation — claimed offsets are wrong,
        # substring-search returns the first "Bob".
        spans = [
            {"id": "t0", "type": "person", "text": "Bob",
             "start": 99, "end": 102, "polarity": "asserted"},
        ]
        result = _relocate_spans(spans, answer)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], 0)
        self.assertEqual(result[0]["end"], 3)


class ExtractBalancedObjectTests(unittest.TestCase):
    """_spantag_extract_balanced_object scans prose for the first JSON
    object with a 'tags' key — tested directly here so failure modes of
    the helper are visible even when the full parser path succeeds."""

    def test_finds_embedded_object(self):
        text = 'prefix {"tags": [{"id": "t0"}]} suffix'
        obj = _spantag_extract_balanced_object(text)
        self.assertIsNotNone(obj)
        self.assertIn("tags", obj)

    def test_ignores_braces_in_strings(self):
        # A '{' inside a string literal must not start a new balance attempt.
        text = '{"tags": [{"text": "with { brace"}]}'
        obj = _spantag_extract_balanced_object(text)
        self.assertIsNotNone(obj)
        self.assertEqual(obj["tags"][0]["text"], "with { brace")

    def test_returns_none_on_no_match(self):
        text = "no json here at all"
        self.assertIsNone(_spantag_extract_balanced_object(text))

    def test_skips_non_tags_object(self):
        # First {...} is not what we want; second one is.
        text = '{"other": 1} then {"tags": []}'
        obj = _spantag_extract_balanced_object(text)
        self.assertIsNotNone(obj)
        self.assertIn("tags", obj)


class RegexRecoverTagsTests(unittest.TestCase):
    """Last-resort regex recovery when neither json.loads nor balanced
    scanning find a valid object."""

    def test_recovers_tags_array(self):
        text = 'garbage "tags": [{"id":"t0","type":"person","text":"Bob"}] more garbage'
        arr = _spantag_regex_recover_tags(text)
        self.assertIsNotNone(arr)
        self.assertEqual(len(arr), 1)
        self.assertEqual(arr[0]["id"], "t0")

    def test_returns_none_when_no_tags_key(self):
        self.assertIsNone(_spantag_regex_recover_tags("no tags here"))

    def test_returns_none_on_malformed_array(self):
        text = '"tags": [this is not json'
        self.assertIsNone(_spantag_regex_recover_tags(text))


if __name__ == "__main__":
    unittest.main()
