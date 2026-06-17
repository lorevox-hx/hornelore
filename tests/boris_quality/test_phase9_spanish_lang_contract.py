from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails
from tests.boris_quality.fixtures.boris_quality_cases import STEFI_CRYPTO_JEWISH_NARRATOR


class SpanishLanguageContractTests(unittest.TestCase):
    """Spanish/lang-contract regressions surfaced by the full-family run."""

    def test_looks_spanish_does_not_treat_english_with_names_as_spanish(self):
        from server.code.api.services.lori_spanish_guard import looks_spanish

        english_with_spanish_names = (
            "I had an older brother Antonio. I made my First Communion in Las Vegas, "
            "New Mexico. My mother lit candles in the cellar, but I asked her in "
            "English what those candles meant."
        )
        self.assertFalse(
            looks_spanish(english_with_spanish_names),
            "Names like Antonio and places like Las Vegas must not make an English narrator turn Spanish.",
        )

    def test_looks_spanish_detects_actual_spanish_narrator_text(self):
        from server.code.api.services.lori_spanish_guard import looks_spanish

        spanish = (
            "Mi mamá encendía velas en el sótano y yo le preguntaba por qué lo hacía."
        )
        self.assertTrue(looks_spanish(spanish))

    def test_scorer_fails_broken_code_mix(self):
        chapter = ChapterConfig(
            label="Stefi Earliest",
            runtime71_era="earliest_years",
            text=STEFI_CRYPTO_JEWISH_NARRATOR,
            anchors=["antonio", "first communion", "candles"],
            word_budget=110,
        )
        response = (
            "Tú had an older brother Antonio, made my First Communion, asked her why "
            "she lit candles down there, y asked my mother. ¿Qué pasó después?"
        )
        score = score_chapter(chapter, response)
        assert_row_fails(self, score, "no_broken_code_mix")


if __name__ == "__main__":
    unittest.main()
