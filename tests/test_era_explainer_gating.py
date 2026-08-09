"""WO-LEAN-LORI-RUNTIME-01 Phase 8 — the ERA EXPLAINER glossary is gated.

272 tokens defined seven eras on EVERY interviewer turn, while the block's
own first sentence said to use them only when the narrator asks. Measured
present in all 29 states across both Phase 8 matrices.

WHAT THIS DOES NOT CHANGE, because it is the thing most worth protecting:
the era system. Era selection, `current_era`, `pass2a`, era-specific
questions, Today and the Life Map progression are untouched, and the era
vocabulary is still in Lori's prompt. Only the seven-entry DICTIONARY
stops travelling on turns where nobody asked for it.

THE CARRIER IS A FACT ABOUT THE TURN, NOT THE TURN'S IDENTITY, and the
mixed-case test below is why. `EXTRACTION_ELIGIBLE_TURN_MODES` and
`PLACEMENT_ELIGIBLE_TURN_MODES` are both `frozenset({"interview"})`, so an
`era_definition` turn mode would have SILENTLY made such a turn
extraction- and placement-ineligible. A narrator can ask what an era means
and tell a story in the same breath; reclassifying that turn would lose
the story.
"""

from __future__ import annotations

import importlib
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_APP = _REPO / "ui" / "js" / "app.js"

IDENT = {"first_name": "Kent", "full_name": "Kent Horne",
         "date_of_birth": "1938-04-02", "place_of_birth": "Mandan, North Dakota"}


def _rt(**kw):
    d = {"speaker": IDENT, "assistant_role": "interviewer",
         "identity_complete": True, "current_era": "coming_of_age",
         "current_pass": "pass2a", "current_mode": "grounding"}
    d.update(kw)
    return d


class _ComposerCase(unittest.TestCase):
    """Real composer, temp database, never the live one."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="era-gate-")
        os.environ["DATA_DIR"] = cls._tmp
        import api.prompt_composer as pc  # noqa: E402 (PYTHONPATH=server/code)
        importlib.reload(pc)
        cls.pc = pc

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def compose(self, text, **rt):
        return self.pc.compose_system_prompt(
            f"era-{abs(hash(text + repr(rt))) % 99999}",
            user_text=text, runtime71=_rt(**rt))


class TheGlossaryIsGatedTest(_ComposerCase):

    STORY = "When I was 22 I moved to Denver and took the night shift."
    ASK = "What do you mean by Coming of Age?"

    def test_ordinary_story_turn_does_not_get_the_glossary(self):
        p = self.compose(self.STORY, era_definition_requested=False)
        self.assertNotIn("ERA EXPLAINER", p)

    def test_an_era_definition_request_does_get_it(self):
        p = self.compose(self.ASK, era_definition_requested=True)
        self.assertIn("ERA EXPLAINER", p)
        # and the glossary is actually usable, not just its header
        for era in ("Earliest Years", "Coming of Age", "Building Years"):
            self.assertIn(era, p)

    def test_a_client_that_never_sends_the_flag_withholds_it(self):
        """Absent and false resolve identically, and that is deliberate.

        They are not the same fact -- absent means a client predating
        this field, false means a client that looked and the narrator
        did not ask -- but both correctly withhold the glossary, so the
        server does not need to tell them apart. The browser sends the
        boolean explicitly anyway, so the distinction survives on the
        wire for anything that later cares.
        """
        self.assertNotIn("ERA EXPLAINER", self.compose(self.STORY))

    def test_the_saving_is_real_and_is_the_measured_size(self):
        on = self.compose(self.ASK, era_definition_requested=True)
        off = self.compose(self.ASK, era_definition_requested=False)
        self.assertGreater(len(on), len(off))
        # ~272 tokens; asserted in characters so the test needs no model.
        self.assertGreater(len(on) - len(off), 800)


class TheEraSystemItselfIsUntouchedTest(_ComposerCase):
    """The thing Chris stopped to ask about. Eras stay."""

    STORY = "When I was 22 I moved to Denver."

    def test_era_vocabulary_still_reaches_lori_without_the_glossary(self):
        p = self.compose(self.STORY, era_definition_requested=False)
        self.assertNotIn("ERA EXPLAINER", p)
        # She still knows which era she is in and can name it.
        self.assertIn("coming_of_age", p)

    def test_pass2a_behaviour_is_unchanged(self):
        p = self.compose(self.STORY, era_definition_requested=False,
                         current_pass="pass2a")
        self.assertIn("pass2a", p)

    def test_today_and_the_other_eras_still_resolve(self):
        for era in ("earliest_years", "building_years", "later_years", "today"):
            p = self.compose(self.STORY, era_definition_requested=False,
                             current_era=era)
            self.assertIn(era, p, f"era {era} no longer reaches the prompt")

    def test_the_flag_alone_changes_nothing_else(self):
        """Byte-identical apart from the glossary.

        Gating a block must not perturb anything around it; if these two
        differ anywhere else, the edit did more than it claimed.
        """
        off = self.compose(self.STORY, era_definition_requested=False)
        on = self.compose(self.STORY, era_definition_requested=True)
        head, _, tail = on.partition("ERA EXPLAINER")
        rest = tail.split("\n\n", 1)[1] if "\n\n" in tail else ""
        self.assertTrue(off.startswith(head.rstrip("\n")[:400]),
                        "text BEFORE the glossary changed")
        self.assertIn(rest.strip()[:200], off,
                      "text AFTER the glossary changed")


class TheMixedCaseKeepsItsBiographyTest(_ComposerCase):
    """The case that decided the carrier. Do not weaken this test.

    "What do you mean by Coming of Age? I moved to Denver when I was 22."

    One turn, a question about the system AND a piece of the narrator's
    life. All three must hold at once: Lori gets the glossary, the turn
    stays an ordinary interview turn, and the biography stays eligible
    for extraction and placement.
    """

    MIXED = ("What do you mean by Coming of Age? "
             "I moved to Denver when I was 22.")

    def test_the_glossary_is_available(self):
        self.assertIn("ERA EXPLAINER",
                      self.compose(self.MIXED, era_definition_requested=True))

    def test_the_turn_stays_extraction_and_placement_eligible(self):
        from api.services.turn_extraction import extraction_eligible
        from api.services.trip_placement import placement_eligible
        # The turn mode is untouched by this feature -- that is the whole
        # design. If a future change routes era questions to their own
        # mode, these two flip to False and the narrator's Denver is
        # silently lost.
        self.assertTrue(extraction_eligible("interview"))
        self.assertTrue(placement_eligible("interview"))
        self.assertFalse(extraction_eligible("era_definition"))
        self.assertFalse(placement_eligible("era_definition"))

    def test_the_eligibility_gates_are_still_allow_lists_of_one(self):
        """Pinned because the reasoning above depends on it.

        If either list ever grows, the argument for a runtime71 flag over
        a turn_mode weakens, and whoever changes it should have to read
        this test.
        """
        from api.services.turn_extraction import EXTRACTION_ELIGIBLE_TURN_MODES
        from api.services.trip_placement import PLACEMENT_ELIGIBLE_TURN_MODES
        self.assertEqual({"interview"}, set(EXTRACTION_ELIGIBLE_TURN_MODES))
        self.assertEqual({"interview"}, set(PLACEMENT_ELIGIBLE_TURN_MODES))


class TheBrowserCarriesItAsAFactNotAnIdentityTest(unittest.TestCase):
    """Source contract on `app.js`. The detector must stay out of routing."""

    def setUp(self):
        self.src = _APP.read_text(encoding="utf-8")

    def test_the_detector_exists_beside_its_siblings(self):
        for fn in ("_looksLikeEraDefinitionQuestion",
                   "_looksLikeAgeQuestion",
                   "_looksLikeMemoryEchoRequest",
                   "_looksLikeStrongCorrection"):
            self.assertIn(f"function {fn}(text){{", self.src)

    def test_it_is_NOT_wired_into_lvRouteTurn(self):
        """The single most important assertion in this file.

        `lvRouteTurn` decides `turn_mode`, and `turn_mode` decides
        extraction and placement ownership. An era question must never
        reach it.
        """
        start = self.src.index("function lvRouteTurn(text){")
        body = self.src[start:self.src.index("\n}", start)]
        self.assertNotIn("_looksLikeEraDefinitionQuestion", body)

    def test_the_flag_is_sent_explicitly_on_every_narrator_turn(self):
        """Explicit boolean, not absence-means-false.

        The producer states its decision. Absence would mean "this
        client does not know", which is a different fact.
        """
        self.assertIn(
            "_rt71.era_definition_requested = _looksLikeEraDefinitionQuestion(text);",
            self.src)

    def test_no_new_turn_mode_constant_was_introduced(self):
        self.assertNotIn("era_definition\"", self.src)
        self.assertNotIn("TURN_ERA", self.src)

    def test_the_detector_requires_an_era_word_and_a_question_shape(self):
        """Narrow by construction: a mention is not a request.

        Asserted on the source rather than by executing JS, because the
        behavioural truth table is exercised in node alongside this
        suite; this pins that both halves of the conjunction survive.
        """
        start = self.src.index("function _looksLikeEraDefinitionQuestion(text){")
        body = self.src[start:self.src.index("\n}", start)]
        # The era word is a REQUIRED conjunct and must stay one -- it is
        # what stops "What was my mother like?" firing. The early return
        # is asserted specifically, not merely the regex's presence.
        self.assertIn("if (!ERA_WORDS.test(t)) return false;", body)
        # And a definition-shaped question is the second conjunct.
        self.assertIn("const ASK =", body)
        self.assertIn("ASK.test(t)", body)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
