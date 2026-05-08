"""WO-ML-05D — Spanish phantom-noun whitelist tests.

Validates that Spanish kinship/calendar/religious/holiday tokens are NOT
flagged as phantom proper nouns in Lori's Spanish reflections, and that
genuinely-phantom Spanish tokens (i.e., capitalized proper nouns the
narrator never said and the profile doesn't carry) ARE still flagged.

Architecture:
- Whitelist (`_PHANTOM_NOUN_WHITELIST`) is the false-positive filter.
- Detector regex must accept Spanish accents/ñ for both ASCII and
  accented capitalized tokens (María, Núñez, Jesús).
- Whitelist filtering happens after detection.

Run with:
    cd hornelore
    python -m unittest tests.test_phantom_noun_spanish -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.services.lori_communication_control import (  # noqa: E402
    _extract_proper_noun_candidates,
    _PHANTOM_NOUN_WHITELIST,
    scrub_phantom_proper_nouns,
)


class WhitelistMembership(unittest.TestCase):
    """Spanish kinship/calendar/religious tokens are in whitelist."""

    def test_spanish_kinship_in_whitelist(self):
        for word in ("Mamá", "Papá", "Abuela", "Abuelo", "Hermana", "Hermano",
                     "Tía", "Tío", "Hija", "Hijo", "Niña", "Niño"):
            self.assertIn(word, _PHANTOM_NOUN_WHITELIST,
                          f"Expected {word!r} in Spanish whitelist")

    def test_spanish_calendar_in_whitelist(self):
        for word in ("Lunes", "Martes", "Domingo", "Enero", "Diciembre",
                     "Primavera", "Verano", "Invierno"):
            self.assertIn(word, _PHANTOM_NOUN_WHITELIST)

    def test_spanish_religious_in_whitelist(self):
        for word in ("Dios", "Señor", "Cristo", "Jesús", "Virgen"):
            self.assertIn(word, _PHANTOM_NOUN_WHITELIST)

    def test_maria_NOT_in_whitelist(self):
        # "María" is the most common Spanish female name — must NOT be
        # whitelisted or it would mask real-narrator names. Verification
        # via narrator corpus / profile_seed is the correct gate.
        self.assertNotIn("María", _PHANTOM_NOUN_WHITELIST)
        self.assertNotIn("Maria", _PHANTOM_NOUN_WHITELIST)

    def test_country_names_NOT_in_whitelist(self):
        # Country/place names are real proper nouns. Verification via
        # narrator corpus is the correct gate.
        for word in ("México", "Mexico", "España", "Espana", "Cuba",
                     "Perú", "Peru", "Argentina", "Colombia"):
            self.assertNotIn(word, _PHANTOM_NOUN_WHITELIST,
                             f"{word} should not be whitelisted — it's a real proper noun")

    def test_spanish_holidays_in_whitelist(self):
        for word in ("Navidad", "Pascua"):
            self.assertIn(word, _PHANTOM_NOUN_WHITELIST)

    def test_spanish_q_words_in_whitelist(self):
        for word in ("Qué", "Cuándo", "Dónde", "Cómo", "Quién", "Cuál"):
            self.assertIn(word, _PHANTOM_NOUN_WHITELIST)


class DetectorRecognizesSpanishCaps(unittest.TestCase):
    """The proper-noun detector must accept Spanish accent capitals."""

    def test_detects_accented_proper_noun_after_first_word(self):
        # "Tu abuela María llamaba a Pepe."
        # First word "Tu" is sentence-start (skipped).
        # "María" should be detected as a candidate (accented capital).
        # "Pepe" should be detected.
        # "abuela" is lowercase — not detected.
        candidates = _extract_proper_noun_candidates(
            "Tu abuela María llamaba a Pepe."
        )
        self.assertIn("María", candidates)
        self.assertIn("Pepe", candidates)

    def test_detects_n_tilde_proper_noun(self):
        candidates = _extract_proper_noun_candidates(
            "El vecino se llamaba Núñez y vivía cerca."
        )
        self.assertIn("Núñez", candidates)


class WhitelistFiltersSpanishKinship(unittest.TestCase):
    """Spanish kinship words capitalized mid-sentence don't get flagged."""

    def test_mid_sentence_abuela_not_flagged(self):
        # "Esta era tu Abuela." — "Abuela" capitalized as honorific.
        # First word "Esta" is sentence-start. "Abuela" mid-sentence is
        # capitalized but should be filtered by whitelist.
        candidates = _extract_proper_noun_candidates(
            "Esta era tu Abuela."
        )
        self.assertNotIn("Abuela", candidates)

    def test_mid_sentence_navidad_not_flagged(self):
        candidates = _extract_proper_noun_candidates(
            "Yo recuerdo cuando era Navidad."
        )
        self.assertNotIn("Navidad", candidates)

    def test_dios_not_flagged(self):
        candidates = _extract_proper_noun_candidates(
            "Y mi mamá decía Dios bendiga."
        )
        self.assertNotIn("Dios", candidates)


class GenuinePhantomStillFlagged(unittest.TestCase):
    """Made-up names (not in narrator corpus, not in profile, not in
    whitelist) should still be flagged."""

    def test_phantom_spanish_name_flagged_via_scrub(self):
        # Lori reply mentions "Hannah" (live evidence — STT mishearing
        # of "hold my hand"). Narrator never said it; profile doesn't
        # have it; not a Spanish kinship/calendar term; should flag.
        # Keep two sentences so flagging the phantom one still leaves
        # behind a non-empty cleaned reply.
        reply = (
            "Tu abuela Hannah te llamaba con cariño. "
            "Tienes muchos recuerdos de tu familia."
        )
        narrator_corpus = "tomó mi mano para ir a la cocina"
        profile_seed = {"preferred_name": "María", "speaker_name": "María"}
        result = scrub_phantom_proper_nouns(
            reply,
            narrator_corpus=narrator_corpus,
            profile_seed=profile_seed,
            scrub_mode=False,
        )
        self.assertIn("Hannah", result["flagged"])
        self.assertNotIn("Tu", result["flagged"])
        self.assertNotIn("abuela", result["flagged"])

    def test_genuine_spanish_name_not_flagged_when_narrator_said_it(self):
        # Narrator mentioned María. Lori using "María" must NOT be flagged.
        reply = "Tu hija María suena como una persona especial."
        narrator_corpus = "Mi hija se llama María y es la mayor."
        profile_seed = {}
        result = scrub_phantom_proper_nouns(
            reply,
            narrator_corpus=narrator_corpus,
            profile_seed=profile_seed,
            scrub_mode=False,
        )
        self.assertNotIn("María", result["flagged"])

    def test_spanish_name_in_profile_not_flagged(self):
        # Profile carries "José" as parent name. Lori reflecting it
        # should not flag.
        reply = "Tu papá José trabajaba mucho."
        narrator_corpus = "él trabajaba mucho"  # narrator didn't name him
        profile_seed = {"father_name": "José"}
        result = scrub_phantom_proper_nouns(
            reply,
            narrator_corpus=narrator_corpus,
            profile_seed=profile_seed,
            scrub_mode=False,
        )
        self.assertNotIn("José", result["flagged"])


if __name__ == "__main__":
    unittest.main()
