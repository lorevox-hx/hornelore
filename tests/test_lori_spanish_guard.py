"""Unit tests for services/lori_spanish_guard.py.

Covers:
  - English passthrough (no-op when input lacks Spanish indicators)
  - Spanish detection heuristic (accents OR function-word density)
  - Perspective guard: "Mi abuela" → "Tu abuela" when narrator said
    "mi abuela", and the same for all kinship terms / plural forms
  - Quote-safe behavior: text inside «», "", '', '' is preserved
  - Defense-in-depth: when narrator did NOT use the same relation,
    Lori's "Mi X" is left alone (cross-reference check)
  - Fragment guard: trim trailing connector + period
  - Integrated apply_spanish_guards public surface
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.lori_spanish_guard import (  # noqa: E402
    apply_spanish_guards,
    detect_question_quality,
    looks_spanish,
    repair_spanish_fragment,
    repair_spanish_perspective,
)


class LooksSpanishTest(unittest.TestCase):
    def test_empty(self):
        self.assertFalse(looks_spanish(""))

    def test_none(self):
        self.assertFalse(looks_spanish(None))  # type: ignore[arg-type]

    def test_pure_english(self):
        self.assertFalse(looks_spanish(
            "What was your favorite memory from that time?"
        ))

    def test_spanish_chars(self):
        self.assertTrue(looks_spanish("¿Cómo estás?"))

    def test_spanish_accents(self):
        self.assertTrue(looks_spanish("Mi abuela hacía tortillas."))

    def test_spanish_function_words(self):
        # No accents, but enough Spanish function words.
        self.assertTrue(looks_spanish("La casa de mi familia es muy grande"))

    def test_one_function_word_not_enough(self):
        # Single function word is not enough.
        self.assertFalse(looks_spanish("la"))


class PerspectiveSingularTest(unittest.TestCase):
    """Live-evidence cases from BUG-ML-LORI-SPANISH-PERSPECTIVE-01."""

    def test_mi_abuela_rewritten(self):
        # The exact 2026-05-07 live failure.
        narrator = "Recuerdo que mi abuela se levantaba temprano los domingos."
        lori = "Mi abuela y su aroma a maíz caliente — esos son detalles importantes."
        repaired, changes = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tu abuela", repaired)
        self.assertNotIn("Mi abuela", repaired)
        self.assertTrue(any("perspective_singular" in c for c in changes))

    def test_mi_papa(self):
        narrator = "Mi papá trabajaba de noche en la fábrica."
        lori = "Mi papá trabajaba de noche — qué historia fuerte."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tu papá", repaired)
        self.assertNotIn("Mi papá", repaired)

    def test_mi_mama(self):
        narrator = "Mi mamá era cariñosa."
        lori = "Mi mamá era cariñosa — qué imagen tan tierna."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tu mamá", repaired)

    def test_mi_abuelo(self):
        narrator = "Mi abuelo trabajaba la tierra."
        lori = "Mi abuelo y la tierra — eso suena a una vida muy honesta."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tu abuelo", repaired)

    def test_mi_padre(self):
        narrator = "Mi padre nunca habló de la guerra."
        lori = "Mi padre y su silencio sobre la guerra son significativos."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tu padre", repaired)

    def test_mid_sentence_position(self):
        # "Mi abuela" not at sentence start should also be caught.
        narrator = "Mi abuela hacía tortillas."
        lori = "Eso es hermoso. Mi abuela y las tortillas — qué memoria sensorial tan vívida."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tu abuela", repaired)
        self.assertNotIn("Mi abuela", repaired)


class PerspectivePluralTest(unittest.TestCase):
    def test_mis_hermanos(self):
        narrator = "Mis hermanos eran más jóvenes que yo."
        lori = "Mis hermanos y los recuerdos compartidos — eso es importante."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tus hermanos", repaired)
        self.assertNotIn("Mis hermanos", repaired)

    def test_mis_padres(self):
        narrator = "Mis padres siempre trabajaron juntos."
        lori = "Mis padres trabajando juntos — qué imagen tan poderosa."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("Tus padres", repaired)


class QuoteSafeTest(unittest.TestCase):
    """Narrator's quoted words inside quotation marks must NOT be
    rewritten — they're explicit quotes, not Lori's perspective."""

    def test_double_quotes_preserved(self):
        narrator = "Mi abuela me decía cosas."
        # Lori is QUOTING the narrator's exact phrase from somewhere.
        lori = 'Lo recuerdas con mucha ternura. Decías: "Mi abuela siempre decía eso."'
        repaired, _ = repair_spanish_perspective(lori, narrator)
        # Inside the double-quote span, "Mi abuela" stays.
        self.assertIn('"Mi abuela siempre decía eso."', repaired)

    def test_curly_quotes_preserved(self):
        narrator = "Mi abuela me decía cosas."
        lori = "Decías: “Mi abuela siempre decía eso.”"
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("“Mi abuela siempre decía eso.”", repaired)

    def test_spanish_typographic_quotes_preserved(self):
        narrator = "Mi abuela me decía cosas."
        lori = "Decías: «Mi abuela siempre decía eso.»"
        repaired, _ = repair_spanish_perspective(lori, narrator)
        self.assertIn("«Mi abuela siempre decía eso.»", repaired)

    def test_outside_quote_still_repaired(self):
        # Mixed: one Mi inside quotes (preserve) and one outside (repair).
        narrator = "Mi abuela hacía tortillas."
        lori = 'Mi abuela y las tortillas — y dijiste "mi abuela me enseñó."'
        repaired, _ = repair_spanish_perspective(lori, narrator)
        # Outside the quote: rewritten to Tu
        self.assertTrue(repaired.startswith("Tu abuela"))
        # Inside the quote: preserved
        self.assertIn('"mi abuela me enseñó."', repaired)


class DefenseInDepthTest(unittest.TestCase):
    """When narrator_text is not provided, default to repairing
    aggressively (Lori has no business saying 'Mi abuela' in
    interview mode regardless). When narrator_text IS provided
    and the narrator never mentioned that relation, leave Lori's
    text alone — could be legit context (rare)."""

    def test_no_narrator_context_repairs_aggressively(self):
        # No narrator_text given; "Mi abuela" should still be rewritten.
        lori = "Mi abuela hacía tortillas — qué historia hermosa."
        repaired, changes = repair_spanish_perspective(lori, None)
        self.assertIn("Tu abuela", repaired)
        self.assertTrue(any("perspective_singular" in c for c in changes))

    def test_narrator_didnt_use_same_relation_no_repair(self):
        # Narrator talked about their PAPA, not their ABUELA. Lori's
        # "Mi abuela" doesn't have a narrator counterpart — leave alone.
        narrator = "Mi papá trabajaba en el campo."
        lori = "Mi abuela en la cocina — qué imagen tan tierna."
        repaired, _ = repair_spanish_perspective(lori, narrator)
        # No rewrite — Lori's "Mi abuela" doesn't mirror narrator's "mi abuela".
        self.assertIn("Mi abuela", repaired)


class EnglishPassthroughTest(unittest.TestCase):
    """English Lori responses must not be touched."""

    def test_english_with_my_grandmother_unchanged(self):
        narrator = "My grandmother made bread on Sundays."
        lori = "My grandmother and the bread — that's a beautiful memory."
        repaired, changes = repair_spanish_perspective(lori, narrator)
        self.assertEqual(repaired, lori)
        self.assertEqual(changes, [])

    def test_english_question_unchanged(self):
        narrator = "I had three children."
        lori = "Tell me more about your children. What were their names?"
        repaired, changes = repair_spanish_perspective(lori, narrator)
        self.assertEqual(repaired, lori)
        self.assertEqual(changes, [])


class FragmentGuardTest(unittest.TestCase):
    """Spanish dangling-fragment endings."""

    def test_after_de_que_fragment(self):
        # Live evidence 2026-05-07.
        lori = "Eso es hermoso. ¿Qué recuerdas sobre las tardes de los domingos, después de que su."
        repaired, changes = repair_spanish_fragment(lori)
        # Trailing fragment trimmed.
        self.assertNotIn("después de que su.", repaired)
        self.assertTrue(any("fragment_trim" in c for c in changes))

    def test_dangling_que(self):
        lori = "Tu mamá y la cocina son detalles especiales que."
        repaired, _ = repair_spanish_fragment(lori)
        self.assertFalse(repaired.endswith("que."))

    def test_dangling_su(self):
        lori = "Eso es muy importante. Tu papá y su."
        repaired, _ = repair_spanish_fragment(lori)
        self.assertFalse(repaired.endswith("su."))

    def test_dangling_cuando(self):
        lori = "Eso suena hermoso. Las tardes con tu abuela cuando."
        repaired, _ = repair_spanish_fragment(lori)
        self.assertFalse(repaired.endswith("cuando."))

    def test_question_mark_not_treated_as_fragment(self):
        lori = "¿Qué recuerdas de esa época?"
        repaired, changes = repair_spanish_fragment(lori)
        self.assertEqual(repaired, lori)
        self.assertEqual(changes, [])

    def test_clean_period_not_treated_as_fragment(self):
        lori = "Tu abuela hacía tortillas los domingos. Es un recuerdo precioso."
        repaired, changes = repair_spanish_fragment(lori)
        self.assertEqual(repaired, lori)
        self.assertEqual(changes, [])

    def test_english_passthrough_fragment(self):
        # English text must be left alone even if it ends on "that"
        # or similar — this guard is Spanish-only.
        lori = "Tell me about that"
        repaired, changes = repair_spanish_fragment(lori)
        self.assertEqual(repaired, lori)
        self.assertEqual(changes, [])

    def test_quote_at_end_preserved(self):
        # Spanish text where the LAST thing is a quoted phrase; even
        # if the quoted text ends on a connector, don't trim.
        lori = 'Como decía tu abuela: "después de que su."'
        repaired, _ = repair_spanish_fragment(lori)
        self.assertEqual(repaired, lori)


class ApplySpanishGuardsTest(unittest.TestCase):
    """Integrated public-surface tests."""

    def test_live_evidence_first_failure(self):
        narrator = (
            "Recuerdo que mi abuela se levantaba temprano los domingos. "
            "Yo estaba sentada cerca de la cocina, y el olor del maíz "
            "caliente me hacía sentir segura."
        )
        lori = (
            "Mi abuela y su aroma a maíz caliente — esos son detalles "
            "importantes. ¿Qué recuerdas sobre las tardes de los domingos, "
            "después de que su."
        )
        repaired, changes = apply_spanish_guards(lori, narrator)
        # Perspective fix
        self.assertIn("Tu abuela", repaired)
        self.assertNotIn("Mi abuela", repaired)
        # Fragment fix
        self.assertNotIn("después de que su.", repaired)
        # Both changes recorded
        self.assertTrue(any("perspective_singular" in c for c in changes))
        self.assertTrue(any("fragment_trim" in c for c in changes))

    def test_live_evidence_second_failure(self):
        narrator = (
            "después de que mi abuela terminaba las tortillas, nos "
            "sentábamos juntos y ella me contaba historias de cuando "
            "era joven en Perú."
        )
        lori = (
            "Mi abuela y sus historias de Perú — eso suena como una "
            "conexión muy fuerte. ¿Te gustaba escuchar esas historias "
            "de su juventud en Perú?"
        )
        repaired, changes = apply_spanish_guards(lori, narrator)
        self.assertIn("Tu abuela", repaired)
        self.assertNotIn("Mi abuela", repaired)

    def test_idempotent(self):
        narrator = "Mi abuela hacía tortillas."
        lori = "Mi abuela y las tortillas — qué hermoso recuerdo."
        once, _ = apply_spanish_guards(lori, narrator)
        twice, twice_changes = apply_spanish_guards(once, narrator)
        self.assertEqual(once, twice)
        self.assertEqual(twice_changes, [])

    def test_english_unchanged(self):
        narrator = "My grandmother made bread."
        lori = "Your grandmother and the bread — that's a special memory. What were Sunday afternoons like?"
        repaired, changes = apply_spanish_guards(lori, narrator)
        self.assertEqual(repaired, lori)
        self.assertEqual(changes, [])

    def test_failure_returns_input(self):
        # Should never crash even on weird input.
        repaired, _ = apply_spanish_guards("", None)
        self.assertEqual(repaired, "")


class DetectQuestionQualityTest(unittest.TestCase):
    """BUG-ML-LORI-SPANISH-ACTIVE-LISTENING-QUESTION-01 — detector
    only, returns issue tags. No content rewrites."""

    def test_yes_no_verdad_closer(self):
        # The exact 2026-05-07 live failure.
        text = "Esas imágenes de Perú son muy queridas para ti, ¿verdad?"
        issues = detect_question_quality(text)
        self.assertTrue(any("yes_no_closer" in i for i in issues))
        self.assertTrue(any("verdad" in i for i in issues))

    def test_yes_no_no_closer(self):
        text = "Era un momento muy especial, ¿no?"
        issues = detect_question_quality(text)
        self.assertTrue(any("yes_no_closer" in i for i in issues))

    def test_yes_no_cierto_closer(self):
        text = "Esas memorias son tuyas, ¿cierto?"
        issues = detect_question_quality(text)
        self.assertTrue(any("yes_no_closer" in i for i in issues))

    def test_yes_no_no_es_cierto(self):
        text = "Tu abuela era muy importante para ti, ¿no es cierto?"
        issues = detect_question_quality(text)
        self.assertTrue(any("yes_no_closer" in i for i in issues))

    def test_open_question_qué_clean(self):
        text = "Tu abuela y la voz — qué imagen tan tierna. ¿Qué recuerdas de cómo sonaba su voz?"
        issues = detect_question_quality(text)
        # No yes/no closer, has Q-word in question — clean.
        self.assertEqual(issues, [])

    def test_open_question_cómo_clean(self):
        text = "Tu mamá hacía tortillas — qué hermoso. ¿Cómo era el olor de la cocina los domingos?"
        issues = detect_question_quality(text)
        self.assertEqual(issues, [])

    def test_open_question_cuándo_clean(self):
        text = "Tu papá y las tardes — eso suena especial. ¿Cuándo fue la última vez que pensaste en eso?"
        issues = detect_question_quality(text)
        self.assertEqual(issues, [])

    def test_question_without_q_word(self):
        # Question without a Q-word — should be flagged.
        text = "Las tardes con tu abuela suenan hermosas. ¿Tu abuela te enseñó a hacer tortillas?"
        issues = detect_question_quality(text)
        # Yes/no question structure without a Q-word → flagged.
        self.assertTrue(any("no_q_word_in_question" in i for i in issues))

    def test_no_question_no_flag(self):
        # Reflective response with no question at all — not the
        # detector's concern (interview-mode requires questions but
        # that's enforced elsewhere).
        text = "Tu abuela y las montañas de Perú — qué hermoso recuerdo."
        issues = detect_question_quality(text)
        self.assertEqual(issues, [])

    def test_english_response_passthrough(self):
        # English text returns [] — detector is Spanish-only.
        text = "Your grandmother and the corn — what a beautiful memory, right?"
        issues = detect_question_quality(text)
        self.assertEqual(issues, [])

    def test_empty(self):
        self.assertEqual(detect_question_quality(""), [])
        self.assertEqual(detect_question_quality(None), [])  # type: ignore[arg-type]

    def test_live_failure_full_response(self):
        # The full Lori response from the 2026-05-07 live test.
        text = "Esas imágenes de Perú son muy queridas para ti, ¿verdad?"
        issues = detect_question_quality(text)
        # Should flag yes/no closer AND no Q-word (¿verdad? has no
        # Q-word inside the question span)
        self.assertTrue(any("yes_no_closer" in i for i in issues))
        self.assertTrue(any("no_q_word" in i for i in issues))


if __name__ == "__main__":
    unittest.main(verbosity=2)
