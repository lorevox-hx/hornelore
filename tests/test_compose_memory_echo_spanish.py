"""WO-ML-05G — compose_memory_echo Spanish locale tests.

Phase 1 of BUG-ML-LORI-DETERMINISTIC-COMPOSERS-ENGLISH-ONLY-01.

The composer emits text DIRECTLY to the narrator (no LLM round-trip
→ LANGUAGE MIRRORING RULE doesn't apply to its output). Spanish
narrators must hear the readback in Spanish, not in code-switched
English. Locale detection happens at the chat_ws.py call site via
looks_spanish(user_text); composer accepts target_language="es".

Run with:
    cd hornelore
    python -m unittest tests.test_compose_memory_echo_spanish -v
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

from api.prompt_composer import (  # noqa: E402
    compose_memory_echo,
    _MEMORY_ECHO_LOCALE,
    _translate_relation,
)


class LocalePackShape(unittest.TestCase):
    """The locale pack must carry both en + es entries with parity keys."""

    def test_en_pack_present(self):
        self.assertIn("en", _MEMORY_ECHO_LOCALE)

    def test_es_pack_present(self):
        self.assertIn("es", _MEMORY_ECHO_LOCALE)

    def test_es_has_all_en_keys(self):
        en_keys = set(_MEMORY_ECHO_LOCALE["en"].keys())
        es_keys = set(_MEMORY_ECHO_LOCALE["es"].keys())
        missing = en_keys - es_keys
        self.assertEqual(missing, set(),
                         f"Spanish pack missing keys: {missing}")

    def test_no_extra_es_keys(self):
        en_keys = set(_MEMORY_ECHO_LOCALE["en"].keys())
        es_keys = set(_MEMORY_ECHO_LOCALE["es"].keys())
        extra = es_keys - en_keys
        self.assertEqual(extra, set(),
                         f"Spanish pack has unexpected keys: {extra}")

    def test_no_empty_strings_es(self):
        for key, val in _MEMORY_ECHO_LOCALE["es"].items():
            self.assertTrue(val and val.strip(),
                            f"Empty Spanish translation for key={key}")


class TranslateRelation(unittest.TestCase):
    """Relation labels translate to narrator's language."""

    def test_father_to_padre(self):
        self.assertEqual(_translate_relation("Father", "es"), "Padre")

    def test_mother_to_madre(self):
        self.assertEqual(_translate_relation("Mother", "es"), "Madre")

    def test_brother_to_hermano(self):
        self.assertEqual(_translate_relation("Brother", "es"), "Hermano")

    def test_sister_to_hermana(self):
        self.assertEqual(_translate_relation("Sister", "es"), "Hermana")

    def test_unknown_passes_through(self):
        self.assertEqual(_translate_relation("Stepuncle", "es"), "Stepuncle")

    def test_english_passthrough(self):
        # target_language="en" is no-op
        self.assertEqual(_translate_relation("Father", "en"), "Father")

    def test_empty_passthrough(self):
        self.assertEqual(_translate_relation("", "es"), "")


class EnglishDefaultBehaviorPreserved(unittest.TestCase):
    """Calling compose_memory_echo without target_language must produce
    the existing English readback byte-stable."""

    def test_default_args_returns_english(self):
        # Minimal runtime — no name, no DOB, no family, no profile_seed.
        out = compose_memory_echo("hi", runtime={})
        self.assertIn("What I know about you so far:", out)
        self.assertIn("Identity", out)
        self.assertIn("Family", out)
        self.assertIn("(not on record yet)", out)
        self.assertIn("(none on record yet)", out)
        self.assertIn("What I'm less sure about", out)
        self.assertIn("Some parts are still blank", out)
        self.assertIn("You can correct anything that is wrong", out)
        # NO Spanish artifacts
        self.assertNotIn("Identidad", out)
        self.assertNotIn("Lo que aún no tengo claro", out)
        self.assertNotIn("aún sin registrar", out)

    def test_explicit_english_matches_default(self):
        # target_language="en" must be byte-identical to no-arg call.
        runtime = {
            "speaker_name": "Mary",
            "dob": "1942-06-15",
            "pob": "Spokane",
        }
        default = compose_memory_echo("hi", runtime=runtime)
        explicit = compose_memory_echo("hi", runtime=runtime, target_language="en")
        self.assertEqual(default, explicit)


class SpanishHeader(unittest.TestCase):
    """Spanish target — heading + section labels."""

    def test_minimal_runtime_spanish(self):
        out = compose_memory_echo(
            "qué sabes de mí",
            runtime={},
            target_language="es",
        )
        self.assertIn("Esto es lo que sé de ti hasta ahora:", out)
        self.assertIn("Identidad", out)
        self.assertIn("Familia", out)
        # No English artifacts
        self.assertNotIn("What I know about", out)
        self.assertNotIn("Identity\n", out)
        self.assertNotIn("(not on record yet)", out)

    def test_named_speaker_spanish_header(self):
        out = compose_memory_echo(
            "qué sabes de mí",
            runtime={"speaker_name": "María"},
            target_language="es",
        )
        self.assertIn("Esto es lo que sé de María hasta ahora:", out)
        self.assertIn("- Nombre: María", out)


class SpanishMissingFields(unittest.TestCase):
    """Spanish placeholder for missing values."""

    def test_missing_dob_pob(self):
        out = compose_memory_echo(
            "hola",
            runtime={"speaker_name": "Carmen"},
            target_language="es",
        )
        # Spanish placeholder
        self.assertIn("(aún sin registrar)", out)
        # NOT the English version
        self.assertNotIn("(not on record yet)", out)

    def test_no_parents_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={},
            target_language="es",
        )
        self.assertIn("- Padres: (ninguno aún registrado)", out)
        self.assertIn("- Hermanos: (ninguno aún registrado)", out)


class SpanishFamilyRendering(unittest.TestCase):
    """Family section translates relation labels."""

    def test_father_renders_as_padre(self):
        out = compose_memory_echo(
            "qué sabes de mi familia",
            runtime={
                "speaker_name": "María",
                "projection_family": {
                    "parents": [{"relation": "Father", "name": "José"}],
                },
            },
            target_language="es",
        )
        self.assertIn("- Padre: José", out)
        # Make sure English label didn't slip through
        self.assertNotIn("- Father:", out)

    def test_mother_with_occupation(self):
        out = compose_memory_echo(
            "hola",
            runtime={
                "speaker_name": "Carmen",
                "projection_family": {
                    "parents": [{
                        "relation": "Mother",
                        "name": "Rosa",
                        "occupation": "maestra",
                    }],
                },
            },
            target_language="es",
        )
        self.assertIn("- Madre: Rosa (maestra)", out)

    def test_sister_rendering(self):
        out = compose_memory_echo(
            "hola",
            runtime={
                "speaker_name": "Carmen",
                "projection_family": {
                    "siblings": [{"relation": "Sister", "name": "Lucía"}],
                },
            },
            target_language="es",
        )
        self.assertIn("- Hermana: Lucía", out)

    def test_parent_no_name_spanish(self):
        # Slot exists but no name yet
        out = compose_memory_echo(
            "hola",
            runtime={
                "speaker_name": "Carmen",
                "projection_family": {
                    "parents": [{"relation": "Father"}],
                },
            },
            target_language="es",
        )
        self.assertIn("- Padre: (en archivo, nombre aún no capturado)", out)


class SpanishProfileSeed(unittest.TestCase):
    """profile_seed labels translate."""

    def test_childhood_home_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={
                "speaker_name": "Carmen",
                "profile_seed": {"childhood_home": "Lima"},
            },
            target_language="es",
        )
        self.assertIn("Notas de nuestra conversación", out)
        self.assertIn("- Hogar de la infancia: Lima", out)

    def test_career_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={
                "speaker_name": "José",
                "profile_seed": {"career": "ingeniero"},
            },
            target_language="es",
        )
        self.assertIn("- Carrera: ingeniero", out)


class SpanishUncertainSection(unittest.TestCase):
    def test_uncertain_block_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={"speaker_name": "Carmen"},
            target_language="es",
        )
        self.assertIn("Lo que aún no tengo claro", out)
        self.assertIn(
            "Algunas partes aún están en blanco, y eso está completamente bien.",
            out,
        )
        self.assertIn(
            "Lo que mencione ahora lo mantendré como borrador hasta que lo confirmes.",
            out,
        )

    def test_footer_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={
                "speaker_name": "Carmen",
                "dob": "1962-12-20",
                "pob": "Lima",
            },
            target_language="es",
        )
        # When sources are present, "Basado en: ..." footer fires.
        self.assertIn("(Basado en: ", out)
        self.assertIn("perfil", out)
        self.assertNotIn("(Based on:", out)

    def test_no_records_footer_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={},
            target_language="es",
        )
        self.assertIn(
            "(Aún no tengo nada registrado para ti — ¿te gustaría empezar con tu nombre?)",
            out,
        )

    def test_footer_corrections_spanish(self):
        out = compose_memory_echo(
            "hola",
            runtime={"speaker_name": "Carmen"},
            target_language="es",
        )
        self.assertIn(
            "Puedes corregir cualquier cosa que esté equivocada",
            out,
        )


class UnknownLanguageFallsBackToEnglish(unittest.TestCase):
    """Unknown target_language falls back to English (defensive)."""

    def test_unknown_locale_uses_english(self):
        out = compose_memory_echo(
            "hi",
            runtime={"speaker_name": "Test"},
            target_language="fr",  # no French pack yet
        )
        # Should produce English readback
        self.assertIn("What I know about Test", out)
        self.assertIn("Identity", out)
        self.assertNotIn("Identidad", out)


class PromotedFactsLocale(unittest.TestCase):
    """Promoted-truth section translates field labels + possessive form."""

    def test_promoted_self_fact_spanish_named(self):
        out = compose_memory_echo(
            "qué sabes",
            runtime={
                "speaker_name": "María",
                "peek_data": {
                    "promoted_facts": [
                        {"subject": "self", "field": "place_of_birth", "value": "Lima"},
                    ],
                },
            },
            target_language="es",
        )
        self.assertIn("De nuestros registros", out)
        # Spanish possessive form: "lugar de nacimiento de María: Lima"
        self.assertIn("- lugar de nacimiento de María: Lima", out)

    def test_promoted_self_fact_spanish_unnamed(self):
        # No speaker_name → "Tu {field}: {value}"
        out = compose_memory_echo(
            "qué sabes",
            runtime={
                "peek_data": {
                    "promoted_facts": [
                        {"subject": "self", "field": "occupation", "value": "doctor"},
                    ],
                },
            },
            target_language="es",
        )
        self.assertIn("- Tu ocupación: doctor", out)

    def test_promoted_other_subject_spanish(self):
        out = compose_memory_echo(
            "qué sabes",
            runtime={
                "speaker_name": "Carmen",
                "peek_data": {
                    "promoted_facts": [
                        {"subject": "father", "field": "occupation", "value": "ingeniero"},
                    ],
                },
            },
            target_language="es",
        )
        # Subject should translate "father" → "Padre"
        self.assertIn("- ocupación de Padre: ingeniero", out)


if __name__ == "__main__":
    unittest.main()
