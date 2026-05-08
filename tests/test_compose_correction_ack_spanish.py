"""WO-ML-05E — compose_correction_ack Spanish path tests.

Spanish-speaking narrators get Spanish acknowledgments instead of code-
switched English ones. Detection via looks_spanish() heuristic on the
narrator's correction text.

Run with:
    cd hornelore
    python -m unittest tests.test_compose_correction_ack_spanish -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.prompt_composer import compose_correction_ack  # noqa: E402


class SpanishChildrenCount(unittest.TestCase):
    """Spanish corrections of children count."""

    def test_two_children_es(self):
        # "no, tengo dos hijos, no tres"
        ack = compose_correction_ack("no, tengo dos hijos, no tres")
        # Should be in Spanish (not English "Got it")
        self.assertIn("Lo entiendo", ack)
        self.assertIn("dos hijos", ack)
        self.assertNotIn("Got it", ack)
        # Must include a Spanish courtesy clause — either "Disculpa la
        # confusión" (no retraction) or "Gracias por corregirme" (with
        # retraction).
        self.assertTrue(
            "Disculpa" in ack or "Gracias por corregirme" in ack,
            f"Expected Spanish closing courtesy; got: {ack!r}",
        )


class SpanishFatherName(unittest.TestCase):
    def test_father_name_es(self):
        ack = compose_correction_ack(
            "no, mi padre se llamaba José, no Roberto"
        )
        self.assertIn("Lo entiendo", ack)
        self.assertIn("tu padre era", ack)
        self.assertIn("José", ack)
        self.assertNotIn("Got it", ack)


class SpanishMotherName(unittest.TestCase):
    def test_mother_name_es(self):
        ack = compose_correction_ack(
            "no, mi madre se llamaba Carmen"
        )
        # Not all Spanish corrections will parse — but the no-parse
        # fallback should still be in Spanish.
        self.assertNotIn("Got it", ack)
        # Either the matched ack ("tu madre era Carmen") OR the
        # no-parse fallback ("Oí eso como una corrección...") — both
        # are Spanish.
        self.assertTrue(
            "Lo entiendo" in ack or "Oí eso" in ack,
            f"Expected Spanish ack or fallback; got: {ack!r}",
        )


class SpanishPlaceOfBirth(unittest.TestCase):
    def test_pob_es(self):
        # Test a Spanish correction-shape that the parser supports.
        # The parser pattern "no, nací en X" should ideally hit
        # identity.place_of_birth. If it doesn't parse yet, the
        # fallback should still be in Spanish.
        ack = compose_correction_ack("no, nací en Lima")
        self.assertNotIn("Got it", ack)


class SpanishMeantPattern(unittest.TestCase):
    def test_quise_decir_es(self):
        # "quise decir Lima, no Cuzco"
        ack = compose_correction_ack("quise decir Lima, no Cuzco")
        # Should be Spanish — either matched or no-parse fallback.
        self.assertNotIn("Got it", ack)
        self.assertTrue(
            "Lo entiendo" in ack or "Oí eso" in ack or "Disculpa" in ack,
            f"Expected Spanish ack; got: {ack!r}",
        )


class SpanishUnparseable(unittest.TestCase):
    """Spanish texts that don't match a known correction pattern get
    a Spanish no-parse fallback, not an English one."""

    def test_pure_spanish_unparseable(self):
        ack = compose_correction_ack(
            "Cuando mi abuela hablaba de Perú, todo era diferente."
        )
        # Spanish detected → Spanish fallback.
        self.assertIn("Oí eso", ack)
        self.assertNotIn("I heard that", ack)


class EnglishStillEnglish(unittest.TestCase):
    """Regression: English correction text still gets English ack."""

    def test_english_two_children(self):
        # Use digit form — parser doesn't currently handle English number
        # words for "have N children"; that's a separate parser lane.
        ack = compose_correction_ack("no, I have 2 children, not 3")
        self.assertIn("Got it", ack)
        self.assertIn("two children", ack)
        # Not Spanish
        self.assertNotIn("Lo entiendo", ack)
        self.assertNotIn("Disculpa", ack)

    def test_english_father_name(self):
        ack = compose_correction_ack(
            "no, my father's name was Robert, not Charles"
        )
        self.assertIn("Got it", ack)
        self.assertIn("Robert", ack)
        # Not Spanish
        self.assertNotIn("Lo entiendo", ack)

    def test_english_unparseable(self):
        ack = compose_correction_ack("Some random text I'm just typing")
        # English fallback
        self.assertIn("I heard that", ack)
        self.assertNotIn("Oí eso", ack)


if __name__ == "__main__":
    unittest.main()
