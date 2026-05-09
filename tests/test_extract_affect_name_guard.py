"""BUG-EX-PROTECTED-IDENTITY-FRAGMENT-WRITE-01 — affect-name guard tests.

Live evidence (Mary's session, 2026-05-09 14:02:50):
  Narrator: "I am kind of scared, are you safe to talk to?"
  Followup: extractor wrote `personal.fullName = "scared about talking to"`
  → narrator's panic fragment routed to identity field

The guard drops candidates that:
  (1) start with affect/distress vocabulary (the literal failure mode), OR
  (2) appear in source text after a distress phrase ("I'm afraid of {name}")

Field must be a guarded identity suffix:
  fullName / firstName / lastName / middleName / maidenName / preferredName

Architecture mirrors BUG-EX-PLACE-LASTNAME-01 + BUG-ML-SHADOW-EXTRACT-
PLACE-AS-BIRTHPLACE-01. Pure post-LLM regex — no SPANTAG flag.

Run with:
    cd hornelore
    python -m unittest tests.test_extract_affect_name_guard -v
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# ── Stub FastAPI + pydantic (extract.py imports both at module top) ──
if "fastapi" not in sys.modules:
    fa = types.ModuleType("fastapi")
    class _APIRouter:
        def __init__(self, *a, **kw): pass
        def post(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def get(self, *a, **kw):
            def deco(fn): return fn
            return deco
    class _HTTPException(Exception): pass
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
    _drop_affect_phrase_as_name,
    _value_starts_with_affect_token,
    _looks_like_affect_phrase_for_value,
)


def _item(fieldPath, value):
    return {"fieldPath": fieldPath, "value": value, "confidence": 0.85}


# ── Mary's literal failure mode (the load-bearing test) ────────────────────


class MaryLiteralFailureMode(unittest.TestCase):
    """The exact 2026-05-09 live failure. Mary's panic fragment 'scared
    about talking to' was written to personal.fullName. The guard must
    drop it."""

    def test_marys_fullname_extraction_drops(self):
        text = "I am kind of scared, are you safe to talk to?"
        item = _item("personal.fullName", "scared about talking to")
        self.assertTrue(_drop_affect_phrase_as_name(item, text))

    def test_marys_value_starts_with_distress_token(self):
        # The value-prefix trigger fires regardless of source text
        item = _item("personal.fullName", "scared about talking to")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))


# ── Trigger 1: value starts with distress token ───────────────────────────


class ValueStartsWithDistressTokenTest(unittest.TestCase):
    """When the candidate value begins with affect vocabulary, drop it
    regardless of source-text context. Real names rarely start with
    these words."""

    def test_scared_prefix_drops(self):
        item = _item("personal.fullName", "scared about something")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_afraid_prefix_drops(self):
        item = _item("personal.firstName", "afraid of dogs")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_anxious_prefix_drops(self):
        item = _item("parents.firstName", "anxious mother")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_worried_prefix_drops(self):
        item = _item("siblings.lastName", "worried")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_frightened_prefix_drops(self):
        item = _item("personal.fullName", "frightened of the dark")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_nervous_prefix_drops(self):
        item = _item("personal.preferredName", "nervous")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_overwhelmed_prefix_drops(self):
        item = _item("personal.fullName", "overwhelmed by talking")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_terrified_prefix_drops(self):
        item = _item("personal.fullName", "terrified")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_case_insensitive(self):
        item = _item("personal.fullName", "SCARED about something")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))


# ── Trigger 1: Spanish distress prefixes ──────────────────────────────────


class SpanishDistressPrefixTest(unittest.TestCase):
    def test_asustada_prefix_drops(self):
        item = _item("personal.fullName", "asustada de hablar")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_asustado_prefix_drops(self):
        item = _item("personal.fullName", "asustado")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_preocupada_prefix_drops(self):
        item = _item("parents.firstName", "preocupada")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_miedo_prefix_drops(self):
        item = _item("personal.fullName", "miedo de hablar contigo")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))

    def test_nerviosa_prefix_drops(self):
        item = _item("siblings.lastName", "nerviosa")
        self.assertTrue(_drop_affect_phrase_as_name(item, ""))


# ── Trigger 2: value appears after distress phrase in source ──────────────


class IndirectDistressPhraseTest(unittest.TestCase):
    """Catches the indirect case: 'I'm scared of [name]' should not
    extract [name] to identity slot."""

    def test_scared_of_name_drops(self):
        text = "I'm scared of Stanley these days."
        item = _item("parents.firstName", "Stanley")
        self.assertTrue(_drop_affect_phrase_as_name(item, text))

    def test_afraid_of_name_drops(self):
        text = "I am afraid of John in the next room."
        item = _item("parents.firstName", "John")
        self.assertTrue(_drop_affect_phrase_as_name(item, text))

    def test_estoy_asustada_de_drops(self):
        text = "Estoy asustada de Juan cuando viene a casa."
        item = _item("parents.firstName", "Juan")
        self.assertTrue(_drop_affect_phrase_as_name(item, text))

    def test_tengo_miedo_de_drops(self):
        text = "Tengo miedo de Pedro porque grita mucho."
        item = _item("parents.firstName", "Pedro")
        self.assertTrue(_drop_affect_phrase_as_name(item, text))


# ── False-positive resistance ─────────────────────────────────────────────


class FalsePositiveResistanceTest(unittest.TestCase):
    """Real names + neutral text must not drop. The guard is identity-
    field-only and sees no triggers in normal narrative."""

    def test_real_full_name_kept(self):
        text = "My name is Mary Stanley."
        item = _item("personal.fullName", "Mary Stanley")
        self.assertFalse(_drop_affect_phrase_as_name(item, text))

    def test_real_first_name_kept(self):
        text = "My father was Kent Horne."
        item = _item("parents.firstName", "Kent")
        self.assertFalse(_drop_affect_phrase_as_name(item, text))

    def test_legitimate_name_in_distress_unrelated_text_kept(self):
        # Distress vocabulary present but not adjacent to the name
        text = "I was scared of the storms. My father was Kent."
        item = _item("parents.firstName", "Kent")
        # "scared" appears in the source but not adjacent to "Kent",
        # and "Kent" is not the value starting with a distress token.
        # Guard should NOT fire.
        self.assertFalse(_drop_affect_phrase_as_name(item, text))

    def test_spanish_real_name_kept(self):
        text = "Mi padre se llamaba Pedro Núñez."
        item = _item("parents.firstName", "Pedro")
        self.assertFalse(_drop_affect_phrase_as_name(item, text))

    def test_non_identity_field_ignored(self):
        # The guard only fires on identity field paths. A non-identity
        # field should not be touched even if its value looks distressing.
        text = "I was scared the whole time."
        item = _item("parents.occupation", "scared worker")
        self.assertFalse(_drop_affect_phrase_as_name(item, text))

    def test_empty_value_ignored(self):
        item = _item("personal.fullName", "")
        self.assertFalse(_drop_affect_phrase_as_name(item, "I am scared"))

    def test_non_string_value_ignored(self):
        item = {"fieldPath": "personal.fullName", "value": 42}
        self.assertFalse(_drop_affect_phrase_as_name(item, "I am scared"))

    def test_missing_fieldpath_ignored(self):
        item = {"value": "scared"}
        self.assertFalse(_drop_affect_phrase_as_name(item, ""))


# ── Helper unit tests ─────────────────────────────────────────────────────


class HelperFunctionTest(unittest.TestCase):
    def test_value_starts_with_affect_token_positive(self):
        self.assertTrue(_value_starts_with_affect_token("scared something"))
        self.assertTrue(_value_starts_with_affect_token("afraid"))
        self.assertTrue(_value_starts_with_affect_token("asustada"))
        self.assertTrue(_value_starts_with_affect_token("MIEDO de algo"))

    def test_value_starts_with_affect_token_negative(self):
        self.assertFalse(_value_starts_with_affect_token("Mary Stanley"))
        self.assertFalse(_value_starts_with_affect_token("Kent"))
        self.assertFalse(_value_starts_with_affect_token(""))
        self.assertFalse(_value_starts_with_affect_token("the brave one"))

    def test_looks_like_affect_phrase_for_value_positive(self):
        self.assertTrue(_looks_like_affect_phrase_for_value(
            "I am scared of Stanley", "Stanley"))
        self.assertTrue(_looks_like_affect_phrase_for_value(
            "Estoy asustada de Juan en la casa", "Juan"))

    def test_looks_like_affect_phrase_for_value_negative(self):
        self.assertFalse(_looks_like_affect_phrase_for_value(
            "Stanley was my father.", "Stanley"))
        self.assertFalse(_looks_like_affect_phrase_for_value(
            "Mi padre Juan era amable", "Juan"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
