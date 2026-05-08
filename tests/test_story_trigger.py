"""Unit tests for services/story_trigger.py.

Pure-function tests, no DB or filesystem. The trigger logic is the
gate between every chat_ws turn and the story preservation lane —
correctness here determines whether real stories get preserved or
quietly dropped.

Critical scenarios (from WO §3.3 and §12):
  - Janice canonical: ~25s/50w but 3+ anchors → borderline trigger
  - Long answer with anchor → full_threshold trigger
  - Short answer with no anchors → no trigger (correct null)
  - Empty / None / whitespace transcript → no trigger
  - Anchor false-positive resistance (bare keywords don't fire)
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Make `api.services.story_trigger` importable.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import story_trigger  # noqa: E402


class CountSceneAnchorsTest(unittest.TestCase):
    """Each axis (place / time / person) contributes at most 1 to the
    anchor count. Total range is 0–3 per turn."""

    def test_empty_string(self):
        self.assertEqual(story_trigger.count_scene_anchors(""), 0)

    def test_none_safe(self):
        self.assertEqual(story_trigger.count_scene_anchors(None), 0)  # type: ignore[arg-type]

    def test_no_anchors(self):
        # Bare statement — no place, no relative time, no relation.
        self.assertEqual(
            story_trigger.count_scene_anchors("Yes that is correct."),
            0,
        )

    def test_place_only(self):
        # Multi-word capitalized run hits the proper-noun pattern
        self.assertEqual(
            story_trigger.count_scene_anchors("We lived in Grand Forks."),
            1,
        )

    def test_place_noun_only(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("My uncle worked at the factory."),
            2,  # factory (place) + my uncle (person)
        )

    def test_time_only(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("That happened back then."),
            1,
        )

    def test_person_only(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("My dad helped a lot."),
            1,
        )

    def test_three_axes_canonical_janice(self):
        # The canonical reference — Janice's mastoidectomy story.
        # Place: Spokane (capitalized after "in")
        # Time: when I was
        # Person: my dad
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights at the aluminum plant."
        )
        self.assertEqual(story_trigger.count_scene_anchors(text), 3)

    def test_axis_caps_at_one_per_dimension(self):
        # Five place mentions still only contribute 1 to the place
        # axis — anchor count is dimensional richness, not raw frequency.
        text = "Spokane Spokane Spokane in Spokane near Spokane"
        self.assertEqual(story_trigger.count_scene_anchors(text), 1)


class FalsePositiveResistanceTest(unittest.TestCase):
    """The keyword list ChatGPT originally proposed (`remember`,
    `home`, `school`, `when i was`, etc. as bare keywords) would
    overfire. Tighter detection keeps short conversational answers
    out of story-trigger territory."""

    def test_bare_remember_no_fire(self):
        # "I don't remember" should NOT fire the time anchor on its
        # own. Only specific time phrases qualify.
        self.assertEqual(story_trigger.count_scene_anchors("I don't remember."), 0)

    def test_bare_lowercase_dad_no_fire_without_my(self):
        # Lowercase bare "dad" should not fire — only "my dad" or the
        # capitalized proper-noun form "Dad" (added in 2026-04-30
        # polish, see RealWorldNarratorPolishTest below) are the
        # anchor patterns.
        self.assertEqual(story_trigger.count_scene_anchors("dad was tall."), 0)

    def test_yes_no_answer(self):
        for short_answer in ("yes", "no", "I think so", "maybe", "no idea"):
            self.assertEqual(
                story_trigger.count_scene_anchors(short_answer),
                0,
                f"unexpected anchor on bare answer: {short_answer!r}",
            )

    # 2026-04-30 reviewer caught the docstring's stated intent diverging
    # from the implementation: "School was hard" was firing as a place
    # anchor even though the comment said it shouldn't. These lock the
    # tier-2 (preposition-required) common-noun behavior.

    def test_bare_school_no_place_anchor(self):
        # State predicate about an experience, not a location.
        self.assertEqual(
            story_trigger.count_scene_anchors("School was hard."), 0
        )

    def test_bare_home_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Home was quiet."), 0
        )

    def test_bare_kitchen_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Kitchen was tidy."), 0
        )

    def test_bare_yard_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Yard needs mowing."), 0
        )

    def test_bare_library_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Library is closed."), 0
        )

    def test_in_school_DOES_fire_place(self):
        # The same noun WITH a place preposition is legitimate — narrator
        # is locating the memory in school, not commenting on it.
        self.assertEqual(
            story_trigger.count_scene_anchors("We were in school then."), 1
        )

    def test_at_the_kitchen_table_DOES_fire_place(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("We sat at the kitchen table."),
            1,
        )

    def test_to_the_barn_DOES_fire_place(self):
        # Updated 2026-04-30 polish: "Dad" capitalized fires person
        # anchor via the bare-capital relation pattern, so this turn
        # correctly counts 2 anchors (place + person).
        self.assertEqual(
            story_trigger.count_scene_anchors("Dad walked to the barn."),
            2,
        )

    def test_implant_does_not_match_plant(self):
        # The pre-fix substring approach matched "plant" inside "implant"
        # and "mill" inside "million". Word-boundary regex prevents that.
        self.assertEqual(
            story_trigger.count_scene_anchors("She got an implant."), 0
        )

    def test_million_does_not_match_mill(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("That cost a million dollars."),
            0,
        )

    def test_factory_bare_DOES_fire_place(self):
        # Tier 1 institutional/industrial nouns DO fire on bare mention —
        # "Factory was loud" reads as locational, not state-predicate.
        self.assertEqual(
            story_trigger.count_scene_anchors("Factory was loud."), 1
        )

    # plant / mill demotion (2026-04-30 reviewer round 2): both were
    # originally Tier 1 BARE but overfired on bare predicate uses,
    # because each noun is also a common noun (houseplant) or a verb
    # ("mill around"). Demoted to Tier 2 — locked in below.

    def test_plant_as_living_thing_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("The plant died."), 0
        )

    def test_plant_as_object_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("I watered the plant."), 0
        )

    def test_mill_as_action_no_place_anchor(self):
        # "mill around" — verb usage, no preposition before "mill".
        self.assertEqual(
            story_trigger.count_scene_anchors("They mill around."), 0
        )

    def test_mill_as_verb_with_object_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("We mill flour at home."), 0
        )

    def test_at_the_plant_DOES_fire_place(self):
        # Same noun WITH a place preposition fires correctly.
        # Updated 2026-04-30 polish: "Dad" capitalized now ALSO fires
        # person anchor via the bare-capital relation pattern, so
        # this turn correctly counts 2 anchors (place + person).
        self.assertEqual(
            story_trigger.count_scene_anchors("Dad worked at the plant."),
            2,
        )

    def test_at_the_aluminum_plant_DOES_fire_place(self):
        # The Janice canonical phrase — "aluminum plant" with adjective
        # between determiner and noun must still fire as place anchor
        # (this is the regression risk introduced by demoting "plant"
        # from Tier 1; the prep regex was widened to a 0–2 token
        # adjective slot so this still hits).
        # Updated 2026-04-30 polish: "Dad" capitalized fires person
        # anchor too, so this turn now counts 2.
        self.assertEqual(
            story_trigger.count_scene_anchors("Dad worked at the aluminum plant."),
            2,
        )

    def test_to_the_mill_DOES_fire_place(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("We walked to the mill."), 1
        )


class RealWorldNarratorPolishTest(unittest.TestCase):
    """2026-04-30 evening polish — three improvements that address
    actual classifier misses observed in the live runtime test session
    (Janice canonical fired only with capital S; lowercase "spokane"
    missed; "because of the war" missed; bare-capital "Dad walked"
    missed)."""

    # ── lowercase proper-noun place fallback ──────────────────────────

    def test_lowercase_in_spokane_DOES_fire_place(self):
        # STT and quick narrator typing produce all-lowercase text.
        # The proper-noun fallback retries against title-case when the
        # source has no uppercase anywhere.
        self.assertEqual(
            story_trigger.count_scene_anchors("we lived in spokane."), 1
        )

    def test_mixed_case_intentional_lowercase_does_not_fire(self):
        # Real narrator uses some capitals → we trust their casing and
        # do NOT title-case-fallback. "i was in spokane" still has the
        # "I" lowercase by typing convention but no other capitals
        # are missing — we still fall back here because the WHOLE text
        # contains no capitals. The boundary case: as soon as there's
        # ANY capital, we stop fallback to respect the narrator's
        # casing intent.
        self.assertEqual(
            story_trigger.count_scene_anchors(
                "I was in Spokane and went to the doctor."
            ),
            1,
        )

    def test_lowercase_with_no_place_word_does_not_fire(self):
        # No place preposition → no proper-noun match even after
        # title-case fallback. Avoids "every word with a capital"
        # false positive.
        self.assertEqual(
            story_trigger.count_scene_anchors("yes that is correct"), 0
        )

    # ── because/due to/since the war/depression time anchor ───────────

    def test_because_of_the_war_DOES_fire_time(self):
        self.assertEqual(
            story_trigger.count_scene_anchors(
                "He walked because gas was so expensive because of the war."
            ),
            1,
        )

    def test_due_to_the_depression_DOES_fire_time(self):
        self.assertEqual(
            story_trigger.count_scene_anchors(
                "Money was tight due to the depression."
            ),
            1,
        )

    def test_since_the_war_DOES_fire_time(self):
        self.assertEqual(
            story_trigger.count_scene_anchors(
                "Things had been different since the war."
            ),
            1,
        )

    def test_because_of_X_unrelated_does_not_fire(self):
        # "because of" without one of the era nouns must NOT fire —
        # the pattern requires war/depression/drought/flu/epidemic.
        self.assertEqual(
            story_trigger.count_scene_anchors("I left because of him."), 0
        )

    # ── bare-capital relation (Dad / Mom / Grandma proper-noun usage)──

    def test_capital_dad_bare_DOES_fire_person(self):
        # "Dad" capitalized used as a proper noun (specific person).
        # Common narrator shorthand for "my dad".
        self.assertEqual(
            story_trigger.count_scene_anchors("Dad worked nights."), 1
        )

    def test_capital_mom_bare_DOES_fire_person(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Mom sang in the choir."), 1
        )

    def test_capital_grandma_bare_DOES_fire_person(self):
        self.assertEqual(
            story_trigger.count_scene_anchors(
                "Grandma made the best apple pie."
            ),
            1,
        )

    def test_lowercase_dad_alone_still_no_fire(self):
        # Bare lowercase "dad" must still NOT fire (pre-polish behavior
        # preserved). Only the capitalized proper-noun form is the
        # narrator-shorthand convention we recognize.
        self.assertEqual(
            story_trigger.count_scene_anchors("dad walked nights."), 0
        )

    def test_unrelated_capital_word_does_not_fire_person(self):
        # "Tom" / "Sara" / random capital names are not in the bare
        # relation set. Person anchor must not fire on arbitrary
        # capitalized words.
        self.assertEqual(
            story_trigger.count_scene_anchors("Tom worked nights."), 0
        )

    # ── combined: live narrator turn from the session that didn't fire ──

    def test_real_narrator_turn_now_fires_borderline(self):
        # The actual line Janice's narrator typed during runtime test:
        # lowercase, "Dad" capitalized, mentions both place + war.
        # Pre-polish: anchors=2 (place via prep "at the aluminum plant"
        #            + person via lowercase "dad" — wait, "Dad" was
        #            capitalized in the live transcript). Actually
        #            pre-polish hit anchors=2 for this exact text:
        #            place(at the plant) + ??? Let's just count under
        #            the new rules.
        # Post-polish: should now hit place + time(because of war) +
        # person(capital Dad if present), reaching 3.
        text = (
            "Dad worked nights at the aluminum plant. "
            "He walked because of the war."
        )
        self.assertEqual(
            story_trigger.count_scene_anchors(text), 3,
            "real narrator turn should fire all 3 axes after polish",
        )


class HasSceneAnchorTest(unittest.TestCase):
    def test_predicate_matches_count(self):
        self.assertTrue(story_trigger.has_scene_anchor("My dad worked nights."))
        self.assertFalse(story_trigger.has_scene_anchor("Yes."))


class ClassifyStoryCandidateTest(unittest.TestCase):
    """Two trigger paths plus the null case. WO §3.3 nailed-down."""

    def test_janice_borderline(self):
        # Canonical scenario from WO §12: ~25s/50w but 3+ anchors
        # → must fire as borderline_scene_anchor.
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights at the aluminum plant because it "
            "paid more, and the nurses would let him bring me a "
            "hamburger."
        )
        # Word count is roughly 30; below the 60 floor for full_threshold
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=25.0,
            transcript=text,
        )
        self.assertEqual(result, "borderline_scene_anchor")

    def test_full_threshold_long_with_anchors(self):
        # 70+ words, 60+ seconds, 1+ anchor → full_threshold.
        text = (
            "When I was a child growing up in Stanley, North Dakota, "
            "we had a small house on the edge of town. My dad was a "
            "farmer and my mom raised four of us. Every summer we'd "
            "drive into Minot to see my grandmother. The trip felt "
            "longer than it was. I remember the dust on the dashboard "
            "and the songs on the radio and the way the wheat looked."
        )
        self.assertGreaterEqual(len(text.split()), 60, "test setup needs ≥60 words")
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=60.0,
            transcript=text,
        )
        self.assertEqual(result, "full_threshold")

    def test_long_no_anchors_no_trigger(self):
        # 70+ words but zero scene anchors — should NOT fire either
        # path. The presence of anchor signal is what distinguishes a
        # story from rambling.
        text = " ".join(["yes that is correct"] * 20)
        self.assertGreaterEqual(len(text.split()), 60)
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=60.0,
            transcript=text,
        )
        self.assertIsNone(result)

    def test_short_no_anchors_no_trigger(self):
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=2.0,
            transcript="Yes.",
        )
        self.assertIsNone(result)

    def test_short_with_one_anchor_no_trigger(self):
        # Only 1 anchor — below the 3-anchor borderline floor AND
        # below the duration/word floor. Correctly null.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=3.0,
            transcript="My dad was nice.",
        )
        self.assertIsNone(result)

    def test_short_with_two_anchors_no_trigger(self):
        # 2 anchors — still below the 3-anchor borderline floor.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=3.0,
            transcript="My dad worked at the factory.",
        )
        self.assertIsNone(result)

    def test_empty_transcript(self):
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=30.0,
            transcript="",
        )
        self.assertIsNone(result)

    def test_whitespace_transcript(self):
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=30.0,
            transcript="   \n  ",
        )
        self.assertIsNone(result)

    def test_none_duration_treated_as_zero(self):
        # Duration unknown → can't satisfy full_threshold's duration
        # check, but if anchor count is high enough for borderline
        # we still fire.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=None,
            transcript=(
                "I had a mastoidectomy when I was little, in Spokane. "
                "My dad worked nights."
            ),
        )
        self.assertEqual(result, "borderline_scene_anchor")


class EnvTunableThresholdsTest(unittest.TestCase):
    """Operator can re-tune thresholds without a code change.
    Tests verify env var changes flow through."""

    def setUp(self):
        # Snapshot the env so we can restore.
        self._snap = {
            k: os.environ.get(k)
            for k in (
                "STORY_TRIGGER_MIN_DURATION_SEC",
                "STORY_TRIGGER_MIN_WORDS",
                "STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT",
            )
        }

    def tearDown(self):
        for k, v in self._snap.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_lowering_word_floor_admits_more_full_threshold(self):
        # 30 words at 30s with 1 anchor — below default 60-word floor.
        text = (
            "I grew up in Stanley with my dad and brothers. "
            "We had a farm and chickens and one old dog."
        )
        os.environ["STORY_TRIGGER_MIN_WORDS"] = "20"
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=30.0, transcript=text,
        )
        self.assertEqual(result, "full_threshold")

    def test_raising_anchor_floor_blocks_borderline(self):
        # Janice canonical text — fires borderline by default. Raise
        # the threshold to 5 (impossible — only 3 axes exist) and
        # the trigger should disappear.
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights."
        )
        os.environ["STORY_TRIGGER_BORDERLINE_ANCHOR_COUNT"] = "5"
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=10.0, transcript=text,
        )
        self.assertIsNone(result)


class TriggerDiagnosticTest(unittest.TestCase):
    """The diagnostic returns the underlying numbers so chat_ws can
    emit a [story-trigger] log line per turn for operator review."""

    def test_diagnostic_shape(self):
        d = story_trigger.trigger_diagnostic(
            audio_duration_sec=25.0,
            transcript="I had a surgery in Spokane when I was little. My dad came.",
        )
        for key in (
            "trigger", "duration_sec", "word_count", "anchor_count",
            "place_anchor", "time_anchor", "person_anchor", "thresholds",
        ):
            self.assertIn(key, d, f"missing diagnostic key: {key}")
        self.assertEqual(d["place_anchor"], True)
        self.assertEqual(d["time_anchor"], True)
        self.assertEqual(d["person_anchor"], True)
        self.assertEqual(d["anchor_count"], 3)

    def test_diagnostic_thresholds_from_env(self):
        d = story_trigger.trigger_diagnostic(
            audio_duration_sec=0,
            transcript="anything",
        )
        self.assertIn("min_duration_sec", d["thresholds"])
        self.assertIn("min_words", d["thresholds"])
        self.assertIn("borderline_anchor_count", d["thresholds"])


# ── WO-ML-05A (Phase 5A multilingual capture, 2026-05-07) ─────────────
# Spanish anchor patterns + code-switching coverage. Always-run-both
# posture — English patterns continue to fire on English content;
# Spanish patterns fire on Spanish content; both fire on code-
# switched content. No language gating, no narrator-profile lookup.

class SpanishAnchorTest(unittest.TestCase):
    """Spanish-monolingual anchor detection. Each axis (place / time
    / person) contributes at most 1 to the anchor count; total range
    is 0–3 per turn — same as English. These cases mirror the English
    canonical scenarios so we can verify equivalent coverage."""

    def test_place_only_proper_noun_after_prep_es(self):
        # "en Lima" — Spanish prep + capitalized place.
        self.assertEqual(
            story_trigger.count_scene_anchors("Nací en Lima."),
            1,
        )

    def test_place_only_bare_es(self):
        # "iglesia" alone — Tier 1 BARE noun in Spanish.
        self.assertEqual(
            story_trigger.count_scene_anchors("La iglesia estaba llena."),
            1,
        )

    def test_place_prep_required_es(self):
        # "cocina" alone is NOT a place anchor; "en la cocina" IS.
        self.assertEqual(
            story_trigger.count_scene_anchors("La cocina estaba limpia."), 0
        )
        self.assertEqual(
            story_trigger.count_scene_anchors("Estábamos en la cocina."), 1
        )

    def test_time_only_cuando_era_nina(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Cuando era niña, vivíamos en el campo."),
            2,  # time (cuando era niña) + place (en el campo)
        )

    def test_time_only_en_aquellos_tiempos(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("En aquellos tiempos no había luz."),
            1,
        )

    def test_time_durante_la_guerra(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Durante la guerra todo cambió."),
            1,
        )

    def test_person_only_mi_mama(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Mi mamá cocinaba todos los domingos."),
            1,
        )

    def test_person_only_mi_abuela(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("Mi abuela me enseñó a tejer."),
            1,
        )

    def test_person_bare_capital_papa(self):
        # Bare-capital relation noun used as proper noun. Same convention
        # as English "Dad walked nights" → Spanish "Papá trabajaba de noche".
        self.assertEqual(
            story_trigger.count_scene_anchors("Papá trabajaba de noche en la fábrica."),
            2,  # person (Papá) + place (la fábrica — Tier 1 bare)
        )

    def test_three_axes_canonical_spanish(self):
        # The Spanish parallel of Janice's mastoidectomy story:
        # place (en Sonora), time (cuando era niña), person (mi papá).
        text = (
            "Cuando era niña, me operaron del oído en Sonora. "
            "Mi papá trabajaba de noche en la fábrica."
        )
        self.assertEqual(story_trigger.count_scene_anchors(text), 3)

    def test_axis_caps_at_one_per_dimension_es(self):
        # Multiple Spanish person references, only 1 from person axis.
        text = "Mi mamá, mi papá, mi tío, mi tía, mi abuela todos vivían juntos."
        self.assertEqual(story_trigger.count_scene_anchors(text), 1)

    # ── WO-ML-05A.1 hardening (2026-05-07) ─────────────────────────
    # Whisper STT occasionally drops Spanish diacritics. These cases
    # verify the unaccented-alias additions for fábrica/río/callejón
    # keep firing the place anchor when the input is accent-stripped.

    def test_place_bare_fabrica_unaccented_es(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("La fabrica estaba llena."),
            1,
        )

    def test_place_prep_rio_unaccented_es(self):
        # "cerca del rio" — also tests the new "cerca del" contraction.
        self.assertEqual(
            story_trigger.count_scene_anchors("Jugábamos cerca del rio."),
            1,
        )

    def test_place_prep_callejon_unaccented_es(self):
        # "junto al callejon" — also tests the "junto al" contraction.
        self.assertEqual(
            story_trigger.count_scene_anchors("Vivíamos junto al callejon."),
            1,
        )

    def test_place_prep_del_contraction_es(self):
        # "del" contraction with an accented Tier-2 noun.
        self.assertEqual(
            story_trigger.count_scene_anchors("La iglesia estaba detrás del pueblo."),
            1,
        )

    def test_place_prep_al_contraction_es(self):
        # "al" contraction. "Granja" is Tier-2; "junto al granero".
        self.assertEqual(
            story_trigger.count_scene_anchors("Cuando éramos niños jugábamos junto al granero."),
            2,  # place (junto al granero) + time (cuando éramos niños)
        )

    def test_three_axes_canonical_spanish_unaccented_stt(self):
        # Whisper-degraded variant of the canonical 3-axis Spanish
        # story — accents stripped, contraction "del" used. Should
        # still fire all three anchors so a Whisper-output Spanish
        # narrator's stories aren't silently dropped.
        text = (
            "Cuando era nina, me operaron del oido en Sonora. "
            "Mi papa trabajaba de noche en la fabrica."
        )
        self.assertEqual(story_trigger.count_scene_anchors(text), 3)


class SpanishFalsePositiveResistanceTest(unittest.TestCase):
    """Same posture as the English false-positive resistance suite —
    short conversational Spanish answers should NOT fire anchors.
    Bare common nouns ("escuela was hard" pattern in Spanish:
    "escuela era difícil") stay below the place-anchor threshold."""

    def test_yes_no_answer_es(self):
        for short_answer in ("sí", "no", "tal vez", "no sé", "creo que sí"):
            self.assertEqual(
                story_trigger.count_scene_anchors(short_answer),
                0,
                f"unexpected anchor on bare Spanish answer: {short_answer!r}",
            )

    def test_bare_escuela_no_place_anchor(self):
        # Same Tier 2 posture as English "school was hard" → no anchor.
        self.assertEqual(
            story_trigger.count_scene_anchors("La escuela era difícil."), 0
        )

    def test_bare_casa_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("La casa estaba tranquila."), 0
        )

    def test_bare_cocina_no_place_anchor(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("La cocina estaba limpia."), 0
        )

    def test_bare_lowercase_mama_no_fire_without_mi(self):
        # Lowercase bare "mamá" without "mi" — not an anchor.
        # ("mamá" alone is too loose; only "mi mamá" or capitalized
        # "Mamá" as a proper noun fires.)
        self.assertEqual(
            story_trigger.count_scene_anchors("la mamá llegó tarde."), 0
        )


class CodeSwitchingAnchorTest(unittest.TestCase):
    """Code-switched narration mixes English + Spanish within a single
    utterance. Always-run-both posture means anchors from BOTH sides
    fire together. These cases verify a code-switched narrator gets
    full coverage (no axis lost to language gating)."""

    def test_english_place_spanish_person(self):
        # "I was born in Spokane. Mi mamá cocinaba todos los días."
        text = "I was born in Spokane. Mi mamá cocinaba todos los días."
        # place (Spokane via en prep), person (mi mamá), no time anchor.
        self.assertEqual(story_trigger.count_scene_anchors(text), 2)

    def test_spanish_place_english_person(self):
        # Inverse: "Nos mudamos a Sonora. My dad worked at the plant."
        text = "Nos mudamos a Sonora. My dad worked at the plant."
        self.assertEqual(story_trigger.count_scene_anchors(text), 2)

    def test_three_axes_split_languages(self):
        # Place from Spanish, time from English, person from Spanish.
        text = (
            "Cuando era niña, en Sonora, my dad worked at the plant. "
            "Mi abuela vivía con nosotros."
        )
        self.assertEqual(story_trigger.count_scene_anchors(text), 3)

    def test_mid_utterance_switch(self):
        # Single sentence, mid-utterance switch.
        text = "I was born in Spokane pero nos mudamos a Sonora cuando era pequeña."
        # place (Spokane OR Sonora — either fires), time (cuando era pequeña).
        self.assertEqual(story_trigger.count_scene_anchors(text), 2)


class SpanishClassifyStoryCandidateTest(unittest.TestCase):
    """End-to-end trigger classification with Spanish content — verify
    full_threshold AND borderline paths fire on Spanish-monolingual
    narration."""

    def test_full_threshold_spanish(self):
        # Long-enough + 1 anchor → full_threshold. Word count must
        # clear the 60-default floor; Spanish sentences run shorter
        # word-count than English (more polysyllabic words), so the
        # fixture text deliberately lists multiple memories to push
        # past the floor without padding fillers.
        text = " ".join([
            "Cuando era niña vivíamos en Sonora en una casa pequeña con techo de lámina.",
            "Mi papá trabajaba en la fábrica todas las noches y mi mamá cuidaba la casa durante el día.",
            "Mi mamá hacía tortillas frescas en la cocina cada mañana antes de que saliera el sol.",
            "Aprendí a leer cuando tenía cinco años con la ayuda de mi abuela paterna.",
            "La iglesia estaba al final de la calle y los domingos íbamos toda la familia.",
            "Mi abuela me enseñó a coser durante el invierno cuando hacía mucho frío en la casa.",
            "Recuerdo que mi tío llegaba los sábados con dulces para todos los niños del barrio.",
        ])
        # Make sure the word count clears the floor (60 default).
        self.assertGreaterEqual(len(text.split()), 60)
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=45.0,
            transcript=text,
        )
        self.assertEqual(result, "full_threshold")

    def test_borderline_spanish_short_but_anchored(self):
        # Three axes fire on a short turn → borderline.
        text = (
            "Cuando era niña, en Sonora, mi papá trabajaba de noche."
        )
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=12.0,
            transcript=text,
        )
        self.assertEqual(result, "borderline_scene_anchor")

    def test_no_trigger_short_spanish(self):
        # Short answer with one anchor → neither path fires.
        result = story_trigger.classify_story_candidate(
            audio_duration_sec=3.0,
            transcript="Sí, mi mamá.",
        )
        self.assertIsNone(result)


class EnglishRegressionAfterSpanishLandedTest(unittest.TestCase):
    """Confirm the Spanish patterns don't introduce false-positives
    on the existing English fixture content. These cases mirror the
    canonical English-only checks above."""

    def test_existing_english_canonical_still_three(self):
        text = (
            "I had a mastoidectomy when I was little, in Spokane. "
            "My dad worked nights at the aluminum plant."
        )
        self.assertEqual(story_trigger.count_scene_anchors(text), 3)

    def test_existing_english_yes_still_zero(self):
        for short_answer in ("yes", "no", "I think so", "maybe", "no idea"):
            self.assertEqual(
                story_trigger.count_scene_anchors(short_answer), 0,
                f"unexpected anchor on bare English answer: {short_answer!r}",
            )

    def test_existing_school_was_hard_still_zero(self):
        self.assertEqual(
            story_trigger.count_scene_anchors("School was hard."), 0,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
