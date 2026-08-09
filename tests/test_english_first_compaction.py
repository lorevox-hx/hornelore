"""WO-LEAN-LORI-RUNTIME-01 Phase 7 — the English-first block, compacted.

850 tokens to 108. The four worked examples cost 706 of the 850; the
surviving 108 are the per-turn anti-drift rule that the Phase 6 core does
not already own.

R3 requires the compacted block to preserve four behaviours, and each has
a test below: English does not switch because of foreign names, foods,
places or accented terms; a language changes only by explicit preference
or sustained narration; narrator foreign words stay verbatim; translation
happens only when requested. Two of those four are owned by the core
rather than by this block, and this file asserts WHERE each one lives, so
that a future edit cannot delete both copies believing the other exists.

The block is read from source by AST, for the reason given at the top of
`tests/test_prompt_core_compaction.py`: checking a prompt string should
not import the database layer.
"""

from __future__ import annotations

import ast
import os
import re
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_COMPOSER = _REPO / "server" / "code" / "api" / "prompt_composer.py"
_SRC = _COMPOSER.read_text(encoding="utf-8")


def _assigned_str(name: str) -> str:
    tree = ast.parse(_SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == name:
                    v = node.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        return v.value
                    raise AssertionError(
                        f"{name} is no longer a plain string literal; teach "
                        f"this loader to evaluate it rather than deleting "
                        f"these tests.")
    raise AssertionError(f"{name} not found in prompt_composer.py")


BLOCK = _assigned_str("_english_first_block")
CORE = _assigned_str("DEFAULT_CORE")
IDENTITY = CORE[:CORE.index("ACUTE SAFETY RULE:")]


class TheFourPreservedBehavioursTest(unittest.TestCase):
    """R3 Phase 7's preserve-list, each located deliberately."""

    def test_english_does_not_switch_for_foreign_terms(self):
        # Owned by BOTH: the block states the per-turn imperative, the
        # core states the general principle. That is not duplication --
        # the block answers "what do I do on THIS turn", the core
        # answers "what does a foreign word mean at all".
        self.assertIn("still English narration", BLOCK)
        self.assertIn("never a request to change language", BLOCK)
        self.assertIn("STORY CONTENT, not language preferences", IDENTITY)

    def test_language_changes_only_by_preference_or_sustained_narration(self):
        # Owned by the CORE. The block must not restate it; if this
        # assertion ever needs moving, move it, do not duplicate it.
        self.assertIn("session_language_mode", IDENTITY)
        self.assertIn("writes a full turn in another language", IDENTITY)

    def test_narrator_foreign_words_stay_verbatim(self):
        # Owned by the CORE (VOICE PRESERVATION RULE).
        self.assertIn("Preserve the narrator's own words verbatim", IDENTITY)
        self.assertIn("Never replace the narrator's word with a translation",
                      IDENTITY)

    def test_translation_only_on_request(self):
        # Owned by BOTH, and deliberately: the block adds that the reply
        # STAYS English while doing it, which the core does not say.
        self.assertIn("only when the narrator asks", BLOCK)
        self.assertIn("stay in English when you do", BLOCK)


class TheAntiDriftBlockNoLongerCarriesTheDriftTest(unittest.TestCase):
    """The finding that made removal better than shortening.

    This block exists because Llama-3.1-8B pattern-completes into Spanish
    when narrator text piles up European place names. It taught that with
    three complete Spanish sentences, shipped on every English turn.
    Labelling them WRONG is a semantic annotation on tokens that are
    Spanish either way.
    """

    _SPANISH_MARKERS = ("Ese viaje desde Praga", "Ese momento en el balcón",
                        "Esa conexión entre", "¿Qué recuerdas?",
                        "tiene mucho encanto", "tiene mucha belleza")

    def test_no_spanish_exemplars_ship_in_the_english_first_block(self):
        for m in self._SPANISH_MARKERS:
            self.assertNotIn(m, BLOCK,
                             f"the anti-Spanish-drift block is shipping "
                             f"Spanish again: {m!r}")

    def test_no_spanish_sentence_punctuation_at_all(self):
        # A structural backstop for phrasings the list above does not
        # name: inverted marks appear in Spanish and not in English.
        for ch in ("¿", "¡"):
            self.assertNotIn(ch, BLOCK)

    def test_no_bracket_placeholders_and_so_no_rule_to_suppress_them(self):
        # The examples introduced sixteen ([CITY_A]..[CITY_E], [BASE],
        # [FOREIGN_WORD], ...) and then needed four separate "do not emit
        # the bracketed tokens" instructions to contain a hazard nothing
        # else in the prompt had. Both leave together.
        found = set(re.findall(r"\[([A-Z_]{2,})\]", BLOCK))
        self.assertEqual(
            {"ENGLISH_FIRST_RULE"}, found,
            f"bracket placeholders are back: {sorted(found)}. They are "
            f"only ever needed by worked examples, and they bring their "
            f"own suppression instructions with them.")
        self.assertNotIn("do not emit the bracketed", BLOCK)

    def test_the_city_roster_did_not_grow_back_here(self):
        # Phase 6 removed this exact roster from the core. It had
        # already grown back once, in this block. Rosters recur.
        for city in ("Ljubljana", "Salzburg", "Cittadella", "Scrovegni",
                     "Treviso", "Mirano"):
            self.assertNotIn(city, BLOCK,
                             f"the European city roster is back: {city}")


class GatingIsUnchangedTest(unittest.TestCase):
    """Phase 7 compacts the block. It does not change when it appears.

    Changing which runtime states receive which instructions is Phase 8
    and has its own state-matrix requirement. Asserted against source so
    that a Phase 7 commit cannot quietly do Phase 8's job.
    """

    def test_block_is_still_conditional_on_the_narrator_looking_english(self):
        self.assertIn("if _narrator_is_english:", _SRC)
        self.assertIn('parts.add("english_first", _english_first_block', _SRC)

    def test_it_is_still_droppable_at_the_same_priority(self):
        m = re.search(r'parts\.add\("english_first",\s*_english_first_block,\s*'
                      r'required=(\w+),\s*drop_order=(\d+)', _SRC)
        self.assertIsNotNone(m, "the english_first add() call changed shape")
        self.assertEqual("False", m.group(1))
        self.assertEqual("20", m.group(2),
                         "drop_order changed; that is a budget-priority "
                         "decision (Phase 9), not a compaction one.")

    def test_the_spanish_detour_still_exists(self):
        # A Spanish narrator must still skip this block entirely.
        self.assertIn("_looks_spanish(user_text)", _SRC)


class CompactionHoldsTest(unittest.TestCase):

    _CEILING_CHARS = 700   # measured 524 after Phase 7, from 3,301 before

    def test_block_stays_compact(self):
        self.assertLessEqual(
            len(BLOCK), self._CEILING_CHARS,
            f"the English-first block grew to {len(BLOCK)} chars; Phase 7 "
            f"left it at 524. If a real new rule is needed, raise this "
            f"ceiling deliberately. If it is a worked example, it belongs "
            f"in a regression test, not in every English turn.")

    def test_no_worked_examples_returned(self):
        for marker in ("EXAMPLES —", "Narrator:", "Lori (CORRECT",
                       "Lori (WRONG", "do NOT do this"):
            self.assertNotIn(marker, BLOCK,
                             f"a worked example is back: {marker!r}")

    @unittest.skipUnless(os.getenv("MODEL_PATH"),
                         "MODEL_PATH unset — real-token ceiling needs the "
                         "production tokenizer; the char ceiling still ran")
    def test_real_token_ceiling(self):
        try:
            from tokenizers import Tokenizer  # type: ignore
        except ImportError:  # pragma: no cover
            self.skipTest("the `tokenizers` package is not installed here")
        path = Path(os.environ["MODEL_PATH"]) / "tokenizer.json"
        if not path.exists():  # pragma: no cover
            self.skipTest(f"no tokenizer.json under MODEL_PATH ({path})")
        n = len(Tokenizer.from_file(str(path)).encode(BLOCK).ids)
        self.assertLessEqual(
            n, 160, f"English-first is {n} tokens; Phase 7 left it at 108.")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
