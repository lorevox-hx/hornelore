"""Unit tests for parse_correction_rule_based() in memory_echo.py.

Covers:
  - English regression — every pattern from BUG-LORI-CORRECTION-
    ABSORBED-NOT-APPLIED-01 Phase 3 (2026-05-07) preserved unchanged
  - WO-ML-05B Phase 5B Spanish patterns — birthplace, parent names
    (father + mother in three constructions each), child count (past
    + present, singular + plural narrator, digits + word numbers),
    compound count correction (sólo tuvimos N, no M), negation-first
    count correction (no eran M, eran N), "no había/era X" retract,
    "nunca dije X" retract, "quería/quise decir X, no Y" meant +
    retract (with multi-word capture), Spanish retirement
  - Code-switching — narrator turns mixing English + Spanish
  - False-positive resistance — short Spanish answers, predicates
    about objects, generic negation
  - Whisper-degraded (accent-stripped) Spanish — papá → papa,
    nací → naci, jubilé → jubile, había → habia
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.memory_echo import parse_correction_rule_based  # noqa: E402


class EnglishRegressionTest(unittest.TestCase):
    """Every English pattern from BUG-LORI-CORRECTION-ABSORBED-NOT-
    APPLIED-01 Phase 3 must continue to fire unchanged after Spanish
    patterns are added. These cases mirror the docstring examples
    in parse_correction_rule_based()."""

    def test_birthplace_en(self):
        out = parse_correction_rule_based("I was born in Spokane")
        self.assertEqual(out, {"identity.place_of_birth": "Spokane"})

    def test_father_name_en(self):
        out = parse_correction_rule_based("my father was John")
        self.assertEqual(out, {"family.parents.father.name": "John"})

    def test_mother_name_en(self):
        out = parse_correction_rule_based("my mother's name was Sarah")
        self.assertEqual(out, {"family.parents.mother.name": "Sarah"})

    def test_child_count_en_past(self):
        out = parse_correction_rule_based("I had 3 children")
        self.assertEqual(out, {"family.children.count": 3})

    def test_child_count_en_present(self):
        out = parse_correction_rule_based("I have 2 kids")
        self.assertEqual(out, {"family.children.count": 2})

    def test_compound_count_correction_en(self):
        # The Melanie Zollner pattern.
        out = parse_correction_rule_based("we only had two children, not three")
        self.assertEqual(out["family.children.count"], 2)
        self.assertIn(3, out.get("_retracted", []))

    def test_there_was_no_en(self):
        # Melanie's Hannah/STT pattern.
        out = parse_correction_rule_based(
            "there was no Hannah I said hold my hand"
        )
        self.assertIn("Hannah", out.get("_retracted", []))

    def test_i_never_said_en(self):
        out = parse_correction_rule_based("I never said hate")
        self.assertIn("hate", out.get("_retracted", []))

    def test_i_meant_en(self):
        out = parse_correction_rule_based("I meant pinch not paint")
        self.assertEqual(out.get("_meant"), "pinch")
        self.assertIn("paint", out.get("_retracted", []))

    def test_retirement_en(self):
        out = parse_correction_rule_based("I never really retired")
        self.assertEqual(out, {"education_work.retirement": "never fully retired"})


class SpanishBirthplaceTest(unittest.TestCase):
    def test_simple(self):
        out = parse_correction_rule_based("Nací en Sonora")
        self.assertEqual(out, {"identity.place_of_birth": "Sonora"})

    def test_with_yo(self):
        out = parse_correction_rule_based("Yo nací en Buenos Aires")
        self.assertEqual(out, {"identity.place_of_birth": "Buenos Aires"})

    def test_accent_stripped(self):
        # Whisper-degraded "nací" → "naci".
        out = parse_correction_rule_based("Naci en Lima")
        self.assertEqual(out, {"identity.place_of_birth": "Lima"})

    def test_multi_word_place(self):
        out = parse_correction_rule_based("Nací en Ciudad de México")
        self.assertEqual(
            out, {"identity.place_of_birth": "Ciudad de México"}
        )


class SpanishParentNameTest(unittest.TestCase):
    def test_father_se_llamaba(self):
        out = parse_correction_rule_based("Mi padre se llamaba Juan")
        self.assertEqual(out, {"family.parents.father.name": "Juan"})

    def test_father_papa(self):
        out = parse_correction_rule_based("Mi papá se llamaba José")
        self.assertEqual(out, {"family.parents.father.name": "José"})

    def test_father_papa_accent_stripped(self):
        out = parse_correction_rule_based("Mi papa se llamaba Jose")
        self.assertEqual(out, {"family.parents.father.name": "Jose"})

    def test_father_nombre_era(self):
        out = parse_correction_rule_based(
            "El nombre de mi padre era Carlos"
        )
        self.assertEqual(out, {"family.parents.father.name": "Carlos"})

    def test_mother_se_llamaba(self):
        out = parse_correction_rule_based("Mi madre se llamaba María")
        self.assertEqual(out, {"family.parents.mother.name": "María"})

    def test_mother_mama(self):
        out = parse_correction_rule_based("Mi mamá se llamaba Rosa")
        self.assertEqual(out, {"family.parents.mother.name": "Rosa"})

    def test_mother_nombre_era(self):
        out = parse_correction_rule_based(
            "El nombre de mi madre era Ana"
        )
        self.assertEqual(out, {"family.parents.mother.name": "Ana"})


class SpanishChildCountTest(unittest.TestCase):
    def test_tuve_digit(self):
        out = parse_correction_rule_based("Tuve 3 hijos")
        self.assertEqual(out, {"family.children.count": 3})

    def test_tuvimos_word(self):
        out = parse_correction_rule_based("Tuvimos dos hijas")
        self.assertEqual(out, {"family.children.count": 2})

    def test_tengo_present(self):
        out = parse_correction_rule_based("Tengo cuatro niños")
        self.assertEqual(out, {"family.children.count": 4})

    def test_tenemos_present(self):
        out = parse_correction_rule_based("Tenemos cinco hijos")
        self.assertEqual(out, {"family.children.count": 5})

    def test_chamacos_mexican(self):
        # Mexican Spanish "chamacos" for "kids".
        out = parse_correction_rule_based("Tuve tres chamacos")
        self.assertEqual(out, {"family.children.count": 3})


class SpanishCompoundCountCorrectionTest(unittest.TestCase):
    """The Spanish parallel of the Melanie Zollner pattern."""

    def test_solo_tuvimos_no_x(self):
        out = parse_correction_rule_based(
            "Sólo tuvimos dos hijos, no tres"
        )
        self.assertEqual(out["family.children.count"], 2)
        self.assertIn(3, out.get("_retracted", []))

    def test_solo_tuvimos_unaccented(self):
        # "Sólo" → "solo" (RAE accepts both).
        out = parse_correction_rule_based(
            "Solo tuvimos dos hijos, no tres"
        )
        self.assertEqual(out["family.children.count"], 2)
        self.assertIn(3, out.get("_retracted", []))

    def test_neg_first_eran(self):
        out = parse_correction_rule_based("No eran tres, eran dos")
        self.assertEqual(out["family.children.count"], 2)
        self.assertIn(3, out.get("_retracted", []))
        # Critically: should NOT also capture "tres" as a retracted
        # name token (the 5B fix that suppressed Spanish number
        # words from the generic "no había X" retract pattern).
        self.assertNotIn("tres", out.get("_retracted", []))

    def test_neg_first_fueron(self):
        out = parse_correction_rule_based("No fueron tres, fueron dos")
        self.assertEqual(out["family.children.count"], 2)
        self.assertIn(3, out.get("_retracted", []))


class SpanishRetractTest(unittest.TestCase):
    def test_no_habia(self):
        out = parse_correction_rule_based("No había Hannah")
        self.assertIn("Hannah", out.get("_retracted", []))

    def test_no_era(self):
        out = parse_correction_rule_based("No era Sonora, era Sinaloa")
        self.assertIn("Sonora", out.get("_retracted", []))

    def test_no_habia_accent_stripped(self):
        # Whisper "habia" without accent.
        out = parse_correction_rule_based("No habia Margarita")
        self.assertIn("Margarita", out.get("_retracted", []))

    def test_nunca_dije(self):
        out = parse_correction_rule_based("Yo nunca dije odio")
        self.assertIn("odio", out.get("_retracted", []))

    def test_nunca_dije_no_yo(self):
        out = parse_correction_rule_based("Nunca dije casarme")
        self.assertIn("casarme", out.get("_retracted", []))


class SpanishMeantTest(unittest.TestCase):
    def test_queria_decir_simple(self):
        out = parse_correction_rule_based("Quería decir Sonora, no Sinaloa")
        self.assertEqual(out.get("_meant"), "Sonora")
        self.assertIn("Sinaloa", out.get("_retracted", []))

    def test_quise_decir_multi_word(self):
        out = parse_correction_rule_based("Quise decir Lima Perú, no Lima")
        self.assertEqual(out.get("_meant"), "Lima Perú")
        self.assertIn("Lima", out.get("_retracted", []))

    def test_queria_decir_multi_word_meant(self):
        out = parse_correction_rule_based(
            "Quería decir Buenos Aires, no Bogotá"
        )
        self.assertEqual(out.get("_meant"), "Buenos Aires")
        self.assertIn("Bogotá", out.get("_retracted", []))

    def test_queria_decir_accent_stripped(self):
        out = parse_correction_rule_based("Queria decir Madrid, no Barcelona")
        self.assertEqual(out.get("_meant"), "Madrid")
        self.assertIn("Barcelona", out.get("_retracted", []))


class SpanishRetirementTest(unittest.TestCase):
    def test_nunca_me_jubile(self):
        out = parse_correction_rule_based("Nunca me jubilé")
        self.assertEqual(out, {"education_work.retirement": "never fully retired"})

    def test_nunca_me_retire(self):
        out = parse_correction_rule_based("Nunca me retiré")
        self.assertEqual(out, {"education_work.retirement": "never fully retired"})

    def test_nunca_me_jubile_accent_stripped(self):
        out = parse_correction_rule_based("Nunca me jubile")
        self.assertEqual(out, {"education_work.retirement": "never fully retired"})

    def test_jamas_alternative(self):
        # "jamás" is a stronger Spanish "never".
        out = parse_correction_rule_based("Jamás me jubilé")
        self.assertEqual(out, {"education_work.retirement": "never fully retired"})

    def test_no_realmente(self):
        out = parse_correction_rule_based("No me jubilé realmente")
        self.assertEqual(out, {"education_work.retirement": "never fully retired"})


class SpanishFalsePositiveResistanceTest(unittest.TestCase):
    def test_short_si(self):
        self.assertEqual(parse_correction_rule_based("sí"), {})

    def test_short_si_claro(self):
        self.assertEqual(parse_correction_rule_based("sí, claro"), {})

    def test_predicate_about_object(self):
        # State predicate, not a correction.
        self.assertEqual(
            parse_correction_rule_based("La cocina estaba limpia"), {}
        )

    def test_generic_negation(self):
        # General negation, no field correction.
        self.assertEqual(
            parse_correction_rule_based("No quiero hablar de eso"), {}
        )

    def test_no_se_response(self):
        self.assertEqual(parse_correction_rule_based("no sé"), {})


class CodeSwitchingTest(unittest.TestCase):
    """Code-switched narration mixes English + Spanish in one turn.
    Always-run-both posture means BOTH pattern sets fire and produce
    a combined correction map."""

    def test_english_meant_spanish_count(self):
        # "I meant" English pattern + "tuvimos N hijos" Spanish.
        out = parse_correction_rule_based(
            "I meant Sonora, tuvimos dos hijos in total"
        )
        self.assertEqual(out.get("_meant"), "Sonora")
        # Spanish tuvimos pattern requires "(?:hijos|hijas|...)" right after
        # the count, which "dos hijos in total" satisfies.
        self.assertEqual(out.get("family.children.count"), 2)

    def test_spanish_birthplace_english_father(self):
        # "Nací en X" + "my father was Y" — both fire on the same turn
        out = parse_correction_rule_based(
            "Nací en Lima but my father was John"
        )
        self.assertEqual(out.get("identity.place_of_birth"), "Lima but my father was John")
        # Note: the en-prep pattern is greedy to end-of-string, so it
        # captures up through the rest. This is the SAME behavior as
        # "i was born in" — it's a recognized limitation of the current
        # English pattern. Code-switched narrators have the same issue.
        # Documented here so the limitation is visible in tests; a
        # future tightening would add stop-words.


class ValueOvercaptureFixTest(unittest.TestCase):
    """BUG-ML-LORI-CORRECTION-PARSER-VALUE-OVERCAPTURE-01 (LANDED 2026-05-07).

    Eight value-capture patterns previously included the retraction
    clause inside the value (e.g. "Lima, no en Cuzco" → place="Lima,
    no en Cuzco"). Fix: non-greedy capture + optional retraction-clause
    group. Regression-safe for legitimate multi-part values like
    "Buenos Aires, Argentina".
    """

    # ── Spanish — birthplace ───────────────────────────────────────────

    def test_es_birthplace_with_retraction(self):
        out = parse_correction_rule_based("no, nací en Lima, no en Cuzco")
        self.assertEqual(out.get("identity.place_of_birth"), "Lima")
        self.assertIn("Cuzco", out.get("_retracted", []))

    def test_es_birthplace_with_retraction_no_en_form(self):
        # "no, no en X" form (without explicit "en" in the retraction)
        out = parse_correction_rule_based("Nací en Lima, no Cuzco")
        self.assertEqual(out.get("identity.place_of_birth"), "Lima")
        self.assertIn("Cuzco", out.get("_retracted", []))

    def test_es_birthplace_multipart_preserved(self):
        # Legitimate "Lima, Perú" (no retraction) must still capture full
        out = parse_correction_rule_based("Nací en Lima, Perú")
        self.assertEqual(out.get("identity.place_of_birth"), "Lima, Perú")
        self.assertNotIn("_retracted", out)

    # ── Spanish — parent names ─────────────────────────────────────────

    def test_es_father_with_retraction(self):
        out = parse_correction_rule_based(
            "no, mi padre se llamaba José, no Roberto"
        )
        self.assertEqual(out.get("family.parents.father.name"), "José")
        self.assertIn("Roberto", out.get("_retracted", []))

    def test_es_father_nombre_era_with_retraction(self):
        out = parse_correction_rule_based(
            "el nombre de mi padre era Juan, no Pedro"
        )
        self.assertEqual(out.get("family.parents.father.name"), "Juan")
        self.assertIn("Pedro", out.get("_retracted", []))

    def test_es_mother_with_retraction(self):
        out = parse_correction_rule_based(
            "no, mi madre se llamaba Carmen, no Lucía"
        )
        self.assertEqual(out.get("family.parents.mother.name"), "Carmen")
        self.assertIn("Lucía", out.get("_retracted", []))

    def test_es_mother_nombre_era_with_retraction(self):
        out = parse_correction_rule_based(
            "el nombre de mi madre era Ana, no Sofía"
        )
        self.assertEqual(out.get("family.parents.mother.name"), "Ana")
        self.assertIn("Sofía", out.get("_retracted", []))

    # ── English — same shape ───────────────────────────────────────────

    def test_en_birthplace_with_retraction(self):
        out = parse_correction_rule_based("no, I was born in Lima, not Cuzco")
        self.assertEqual(out.get("identity.place_of_birth"), "Lima")
        self.assertIn("Cuzco", out.get("_retracted", []))

    def test_en_father_with_retraction(self):
        out = parse_correction_rule_based(
            "my father was Robert, not Charles"
        )
        self.assertEqual(out.get("family.parents.father.name"), "Robert")
        self.assertIn("Charles", out.get("_retracted", []))

    def test_en_mother_with_retraction(self):
        out = parse_correction_rule_based(
            "my mother was Carmen, not Lucia"
        )
        self.assertEqual(out.get("family.parents.mother.name"), "Carmen")
        self.assertIn("Lucia", out.get("_retracted", []))

    def test_en_birthplace_multipart_preserved(self):
        # "Buenos Aires, Argentina" (no retraction) — still captures full
        out = parse_correction_rule_based("I was born in Buenos Aires, Argentina")
        self.assertEqual(
            out.get("identity.place_of_birth"), "Buenos Aires, Argentina"
        )
        self.assertNotIn("_retracted", out)

    # ── Regression: simple cases (no retraction) byte-stable ───────────

    def test_simple_birthplace_en_unchanged(self):
        out = parse_correction_rule_based("I was born in Lima")
        self.assertEqual(out, {"identity.place_of_birth": "Lima"})

    def test_simple_birthplace_es_unchanged(self):
        out = parse_correction_rule_based("Nací en Lima")
        self.assertEqual(out, {"identity.place_of_birth": "Lima"})

    def test_simple_father_es_unchanged(self):
        out = parse_correction_rule_based("Mi padre se llamaba José")
        self.assertEqual(out, {"family.parents.father.name": "José"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
