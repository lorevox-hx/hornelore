"""BUG-ML-SHADOW-EXTRACT-PLACE-AS-BIRTHPLACE-01 — birthplace-evidence guard tests.

Live evidence (Melanie Carter Spanish session, 2026-05-07):
  Narrator: "Cuando mi abuela hablaba de Perú, decía que extrañaba las
             montañas, el mercado donde compraba maíz, y el sonido de
             las campanas por la mañana."
  Extractor: grandparents.birthPlace = Peru   ← FALSE INFERENCE

The narrator never said the grandmother was born in Peru.  She said the
grandmother *talked about* Peru and *missed* it (narrative-connection
context, not birth-evidence context).  The new guard drops birthPlace
items whose value appears in source text only after narrative-connection
verbs and never with explicit birth-evidence.

Architecture mirrors BUG-EX-PLACE-LASTNAME-01 — three required conditions:
  1. fieldPath ends in .birthPlace / .placeOfBirth
  2. source text DOES contain value after narrative-connection verb
  3. source text does NOT contain explicit birth-evidence

All three required → drop.  Otherwise keep.

Run with:
    cd hornelore
    python -m unittest tests.test_extract_place_birthplace_guard -v
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# ── Stub FastAPI + pydantic ──
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
    _drop_place_as_birthplace,
    _looks_like_narrative_connection_for_value,
    _has_explicit_birth_evidence,
)


def _item(fieldPath, value):
    return {"fieldPath": fieldPath, "value": value, "confidence": 0.85}


# ── Spanish narrative-connection (live failure mode) ──────────────────────

class SpanishNarrativeConnection(unittest.TestCase):
    """The exact 2026-05-07 live failures (Melanie Carter Spanish session)."""

    def test_hablaba_de_peru_drops_birthplace(self):
        text = (
            "Cuando mi abuela hablaba de Perú, decía que extrañaba las "
            "montañas, el mercado donde compraba maíz, y el sonido de "
            "las campanas por la mañana."
        )
        item = _item("grandparents.birthPlace", "Perú")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_hablaba_de_peru_no_accent_drops(self):
        # Whisper accent-strip variant ("Perú" → "Peru")
        text = (
            "Cuando mi abuela hablaba de Peru, decía que extrañaba las "
            "montañas."
        )
        item = _item("grandparents.birthPlace", "Peru")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_extranaba_X_drops_birthplace(self):
        text = "Mi abuelo extrañaba mucho a México durante todos esos años."
        item = _item("grandparents.birthPlace", "México")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_recordaba_X_drops_birthplace(self):
        text = "Ella siempre recordaba Cuba con cariño."
        item = _item("grandparents.birthPlace", "Cuba")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_contaba_historias_de_X_drops(self):
        text = "Mi abuelo contaba historias de Argentina cada noche."
        item = _item("grandparents.birthPlace", "Argentina")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_decia_que_extranaba_X_drops(self):
        text = "Decía que extrañaba Colombia y los amigos de su juventud."
        item = _item("grandparents.birthPlace", "Colombia")
        self.assertTrue(_drop_place_as_birthplace(item, text))


# ── English narrative-connection ──────────────────────────────────────────

class EnglishNarrativeConnection(unittest.TestCase):
    """English equivalents of the Spanish patterns."""

    def test_talked_about_X_drops_birthplace(self):
        text = "When my grandmother talked about Mexico, she'd describe the markets."
        item = _item("grandparents.birthPlace", "Mexico")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_missed_X_drops_birthplace(self):
        text = "She missed Italy for the rest of her life."
        item = _item("grandparents.birthPlace", "Italy")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_remembered_X_drops_birthplace(self):
        text = "Grandpa remembered Poland fondly."
        item = _item("grandparents.birthPlace", "Poland")
        self.assertTrue(_drop_place_as_birthplace(item, text))

    def test_stories_of_X_drops_birthplace(self):
        text = "He told stories of Ireland every Sunday."
        item = _item("grandparents.birthPlace", "Ireland")
        self.assertTrue(_drop_place_as_birthplace(item, text))


# ── Birth evidence preserves the candidate ────────────────────────────────

class BirthEvidencePreservesCandidate(unittest.TestCase):
    """Explicit birth-evidence in source text → guard does NOT fire."""

    def test_nacio_en_X_keeps_birthplace(self):
        text = "Mi abuela nació en Perú y luego se mudó a Estados Unidos."
        item = _item("grandparents.birthPlace", "Perú")
        self.assertFalse(_drop_place_as_birthplace(item, text))

    def test_was_born_in_X_keeps_birthplace(self):
        text = "My grandmother was born in Peru in 1942."
        item = _item("grandparents.birthPlace", "Peru")
        self.assertFalse(_drop_place_as_birthplace(item, text))

    def test_era_de_X_keeps_birthplace(self):
        text = "Mi padre era de Cuba originalmente."
        item = _item("parents.birthPlace", "Cuba")
        self.assertFalse(_drop_place_as_birthplace(item, text))

    def test_originario_de_X_keeps_birthplace(self):
        text = "Mi tío era originario de Argentina."
        item = _item("parents.birthPlace", "Argentina")
        self.assertFalse(_drop_place_as_birthplace(item, text))

    def test_compound_birth_then_narrative_keeps(self):
        # When both birth-evidence AND narrative-connection appear, the
        # birth-evidence wins (guard does not fire).  Live narrators
        # often combine both: "my grandma was born in Peru and always
        # talked about it."
        text = (
            "Mi abuela nació en Perú. Después en Estados Unidos siempre "
            "hablaba de Perú con tanta nostalgia."
        )
        item = _item("grandparents.birthPlace", "Perú")
        self.assertFalse(_drop_place_as_birthplace(item, text))


# ── Schema and value gate ─────────────────────────────────────────────────

class SchemaAndValueGate(unittest.TestCase):
    """Items outside the guarded schema or with non-string values pass through."""

    def test_non_birthplace_field_keeps(self):
        text = "She missed Peru."
        item = _item("grandparents.firstName", "Peru")
        self.assertFalse(_drop_place_as_birthplace(item, text))

    def test_residence_place_keeps(self):
        # residence.place is a different schema slot and can legitimately
        # carry a place mentioned in narrative-connection context.
        text = "She missed Peru after she moved."
        item = _item("residence.place", "Peru")
        self.assertFalse(_drop_place_as_birthplace(item, text))

    def test_empty_value_keeps(self):
        item = _item("grandparents.birthPlace", "")
        self.assertFalse(_drop_place_as_birthplace(item, "anything"))

    def test_non_string_value_keeps(self):
        item = _item("grandparents.birthPlace", 12345)
        self.assertFalse(_drop_place_as_birthplace(item, "anything"))

    def test_value_not_in_text_keeps(self):
        # If the value doesn't appear in narrative-connection AND doesn't
        # appear in birth-evidence, neither side fires → keep.
        text = "She lived a quiet life."
        item = _item("grandparents.birthPlace", "Peru")
        self.assertFalse(_drop_place_as_birthplace(item, text))


# ── placeOfBirth field path also covered ──────────────────────────────────

class PlaceOfBirthFieldCovered(unittest.TestCase):
    """Both .birthPlace and .placeOfBirth suffixes are guarded."""

    def test_personal_placeofbirth_drops(self):
        text = "Mi abuela hablaba de Perú con frecuencia."
        item = _item("personal.placeOfBirth", "Perú")
        # Note: personal here is the narrator's own POB; same rule applies
        # — narrative-connection alone shouldn't infer the narrator's
        # birthplace from a grandmother's reminiscence.
        self.assertTrue(_drop_place_as_birthplace(item, text))


# ── Helper functions ──────────────────────────────────────────────────────

class HelperFunctions(unittest.TestCase):
    """Direct tests of the helper predicates."""

    def test_looks_like_narrative_connection_spanish(self):
        self.assertTrue(_looks_like_narrative_connection_for_value(
            "hablaba de Perú con cariño", "Perú"
        ))
        self.assertTrue(_looks_like_narrative_connection_for_value(
            "extrañaba mucho a México", "México"
        ))
        self.assertTrue(_looks_like_narrative_connection_for_value(
            "contaba historias de Cuba", "Cuba"
        ))

    def test_looks_like_narrative_connection_english(self):
        self.assertTrue(_looks_like_narrative_connection_for_value(
            "she talked about Mexico", "Mexico"
        ))
        self.assertTrue(_looks_like_narrative_connection_for_value(
            "he missed Ireland", "Ireland"
        ))

    def test_has_birth_evidence_spanish(self):
        self.assertTrue(_has_explicit_birth_evidence(
            "nació en Perú", "Perú"
        ))
        self.assertTrue(_has_explicit_birth_evidence(
            "era de Cuba", "Cuba"
        ))

    def test_has_birth_evidence_english(self):
        self.assertTrue(_has_explicit_birth_evidence(
            "was born in Peru", "Peru"
        ))
        self.assertTrue(_has_explicit_birth_evidence(
            "born at the city hospital in Lima", "Lima"
        ))

    def test_birth_evidence_does_not_match_narrative(self):
        # Sanity: narrative phrasing is NOT misclassified as birth evidence.
        self.assertFalse(_has_explicit_birth_evidence(
            "she talked about Peru", "Peru"
        ))
        self.assertFalse(_has_explicit_birth_evidence(
            "extrañaba Perú", "Perú"
        ))


if __name__ == "__main__":
    unittest.main()
