"""WO-LEAN-LORI-RUNTIME-01 Phase 6 — the compacted core still carries Lori.

Phase 6 recovered 585 tokens (26%) from the always-on identity core, from
2,217 to 1,632 measured with the production tokenizer. The risk of a
compaction phase is not that it fails to save tokens. It is that it saves
them by quietly dropping a behavioural contract nobody notices until a
narrator is on the other end of it.

So these tests assert the contracts, not the size — with one size ceiling
whose only job is to fail if the removed example rosters come back.

WHY THE SOURCE IS READ BY AST RATHER THAN IMPORTED. `prompt_composer`
imports the database layer and, transitively, the server stack. Checking
that a string still contains a rule has no business loading torch. The
same technique is used by `tests/test_prompt_sections.py`, and it has the
same property: it exercises the shipped constant and cannot drift from it.

Python concatenates adjacent string literals at parse time, so the
`DEFAULT_CORE = ("..." "...")` expression is a single `ast.Constant` by
the time it is read here. That is not a trick; it is why this works
without executing the module.
"""

from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_COMPOSER = _REPO / "server" / "code" / "api" / "prompt_composer.py"
_SRC = _COMPOSER.read_text(encoding="utf-8")

#: The marker `prompt_composer` splits on. Duplicated here deliberately:
#: if the split marker is renamed, these tests should fail rather than
#: follow the rename, because the 7,933-byte assertion below is what
#: proves the safety manual was not edited by a prompt-compaction phase.
_SAFETY_MARKER = "ACUTE SAFETY RULE:"


def _default_core() -> str:
    tree = ast.parse(_SRC)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "DEFAULT_CORE":
                    val = node.value
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        return val.value
                    raise AssertionError(
                        "DEFAULT_CORE is no longer a plain concatenated string "
                        "literal. If it became an expression, this loader must "
                        "be taught how to evaluate it -- do not delete these "
                        "tests to make that failure go away.")
    raise AssertionError("DEFAULT_CORE not found in prompt_composer.py")


DEFAULT_CORE = _default_core()
_SPLIT_AT = DEFAULT_CORE.index(_SAFETY_MARKER)
IDENTITY = DEFAULT_CORE[:_SPLIT_AT].rstrip()
PROTOCOL = DEFAULT_CORE[_SPLIT_AT:].strip()


class SafetyHalfIsUntouchedTest(unittest.TestCase):
    """A prompt-compaction phase may not edit the emergency manual.

    Safety is PARKED, so the protocol is not emitted — but it is the
    reactivation artifact, and the day it is switched back on is not the
    day to discover that a token-saving pass reworded a 988 instruction.
    """

    def test_marker_is_still_present(self):
        self.assertIn(_SAFETY_MARKER, DEFAULT_CORE)

    def test_protocol_is_byte_for_byte_the_same_length(self):
        # 7,933 is asserted twice in tests/test_safety_parked.py. It is
        # repeated here so that a Phase 6 edit which strays past the
        # marker fails in the phase that caused it, not in a safety suite
        # whose author will have to work out why.
        self.assertEqual(
            7933, len(PROTOCOL),
            "Phase 6 edited past the ACUTE SAFETY RULE marker. The "
            "compaction must stop at the marker; the protocol half is "
            "out of scope for prompt compaction.")

    def test_the_two_halves_reconstitute_the_original(self):
        self.assertEqual(DEFAULT_CORE.strip(),
                         (IDENTITY + " " + PROTOCOL).strip())


class BehaviouralContractsSurviveTest(unittest.TestCase):
    """The ten contracts Phase 6 was required to preserve.

    Each assertion names the contract rather than the phrasing, so a
    future rewording that keeps the meaning can update the needle without
    anybody having to reconstruct what the test was protecting.
    """

    def _has(self, needle: str, contract: str):
        self.assertIn(needle, IDENTITY,
                      f"contract lost in compaction: {contract}")

    def test_identity_and_purpose(self):
        self._has("Lorevox", "Lori is Lorevox")
        self._has("Life Archive", "the purpose is a Life Archive")
        self._has("'Lore' means stories", "the etymology Lori can share")

    def test_lori_is_never_the_narrator(self):
        self._has("IDENTITY RULE:", "identity rule present")
        self._has("never yourself", "a 'Lori' in the story is a different person")

    def test_one_question_discipline(self):
        self._has("ONE question per turn, always",
                  "one-question discipline")

    def test_no_invention(self):
        self._has("FACT HUMILITY RULE:", "fact humility present")
        self._has("lived memory is always more authoritative",
                  "the narrator outranks Lori's general knowledge")

    def test_direct_answer_first_and_capability_honesty(self):
        self._has("Drop interview mode entirely",
                  "operator feedback drops the interview")
        self._has("what you can and cannot do",
                  "capability honesty")
        self._has("Do NOT ask an interview question at the end",
                  "no interview question tacked onto a product answer")

    def test_oral_history_listening_posture(self):
        self._has("ACTIVE LISTENING RULE", "active listening present")
        self._has("Reflect ONE concrete", "reflect one concrete detail")

    def test_narrator_ownership_of_their_own_facts(self):
        self._has("REVISION RULE:", "revision rule present")
        self._has("accept the revision without comment",
                  "a self-correction is authoritative")

    def test_language_and_voice_boundaries(self):
        self._has("LANGUAGE MODE RULE:", "language mode present")
        self._has("VOICE PRESERVATION RULE:", "voice preservation present")
        self._has("STORY CONTENT, not language preferences",
                  "foreign words do not trigger a language switch")
        self._has("Never replace the narrator's word with a translation",
                  "the narrator's own words are never translated at them")

    def test_empathy_classification_keeps_all_five_types(self):
        for t in ("interaction_feedback", "operator_feedback",
                  "emotional_distress", "meta_confusion", "content_answer"):
            self._has(t, f"empathy type {t}")

    def test_spanish_only_constraints_survive(self):
        self._has("NEVER 'mi'", "second-person kinship in Spanish")
        self._has("después de que", "no sentence ends on a connector")


class ActiveListeningIsLanguageNeutralTest(unittest.TestCase):
    """The repair inside this phase, not merely a saving.

    Before Phase 6 the reflect-one-detail / ask-one-open-question
    standard existed in exactly one place: inside the SPANISH rule, as
    "hold the same active-listening standard you use in English". There
    was no English statement of it to hold. On an English turn the model
    received a pointer to a rule that was never written down, wrapped in
    467 tokens of Spanish worked examples.
    """

    def test_the_rule_is_not_scoped_to_spanish(self):
        self.assertNotIn("SPANISH ACTIVE LISTENING", IDENTITY)
        self.assertIn("ACTIVE LISTENING RULE (applies in EVERY language)",
                      IDENTITY)

    def test_it_no_longer_points_at_a_rule_that_was_never_stated(self):
        self.assertNotIn("the same active-listening standard you use in English",
                         IDENTITY)

    def test_yes_no_closers_are_banned_in_both_languages(self):
        # The failure is identical in English; only the tag changes. If
        # only the Spanish tags are listed, the rule silently permits
        # "right?" on the English path, which is the more common one.
        for tag in ("right?", "isn't it?", "¿verdad?", "¿no?", "¿cierto?"):
            self.assertIn(tag, IDENTITY,
                          f"yes/no closer not banned: {tag}")


class InstructionRecitalTest(unittest.TestCase):
    """LLR-19, the structural half.

    R3 requires proof that no instruction block can be emitted as a
    narrator-visible reply. Only part of that is provable without a live
    model, and this class is deliberately explicit about which part.

    PROVABLE HERE: text that is not in the prompt cannot be recited from
    it, and the prompt no longer ships a verbatim example of a bad reply
    for the model to copy.

    NOT PROVABLE HERE: that the model never paraphrases an instruction it
    *was* given. That needs the live runtime states in R3's Phase 10 and
    Gate F case lists, and this class does not claim it.
    """

    def test_the_emergency_manual_is_not_in_the_identity_half(self):
        # With safety PARKED, `_system_head_core()` emits the identity
        # half alone, so anything absent from it cannot be recited.
        for phrase in ("988", "MANDATORY RESPONSE FORMAT",
                       "HARD-FORBIDDEN PHRASES", _SAFETY_MARKER):
            self.assertNotIn(phrase, IDENTITY,
                             f"emergency-manual text leaked into the "
                             f"always-on identity half: {phrase!r}")

    def test_no_verbatim_bad_reply_ships_in_the_prompt(self):
        # Phase 6 removed a worked "Bad Lori:" example whose text was a
        # real sentence Lori had produced. Shipping the failure verbatim
        # on every turn hands the model the exact string to copy.
        self.assertNotIn("Bad Lori:", IDENTITY)
        self.assertNotIn("Esas imágenes de Perú son muy queridas", IDENTITY)

    def test_no_good_reply_template_ships_either(self):
        self.assertNotIn("Good Lori:", IDENTITY)


class CompactionHoldsTest(unittest.TestCase):
    """One size ceiling, whose only job is to catch a regrowth.

    The removed material was example rosters: nine European place names,
    three food terms, nine `operator_feedback` phrasings, and two worked
    Spanish exchanges. Rosters are how a prompt grows back — each
    addition looks individually reasonable.
    """

    #: measured 7,365 chars after Phase 6, from 9,925 before.
    _CEILING_CHARS = 7_800

    def test_identity_half_stays_compact(self):
        self.assertLessEqual(
            len(IDENTITY), self._CEILING_CHARS,
            f"the always-on core grew back to {len(IDENTITY)} chars. "
            f"Phase 6 left it at 7,365. If the growth is a real new "
            f"rule, raise this ceiling deliberately and say why; if it "
            f"is an example roster, it belongs behind a state gate "
            f"(Phase 8), not in the always-on core.")

    def test_the_removed_rosters_did_not_come_back(self):
        for gone in ("Ljubljana", "Cittadella", "Chioggia", "prosciutto",
                     "the Bug Panel shows 404s", "'that's a strange way to ask'"):
            self.assertNotIn(gone, IDENTITY,
                             f"a removed example roster item is back: {gone!r}")

    @unittest.skipUnless(os.getenv("MODEL_PATH"),
                         "MODEL_PATH unset — real-token ceiling needs the "
                         "production tokenizer; the char ceiling above still ran")
    def test_real_token_ceiling(self):
        """R3 asks for real tokenizer deltas, so use the real tokenizer.

        Skipped rather than approximated when the model is not present:
        a token count from a different tokenizer is not a smaller
        measurement, it is a different one.
        """
        try:
            from tokenizers import Tokenizer  # type: ignore
        except ImportError:  # pragma: no cover
            self.skipTest("the `tokenizers` package is not installed here")
        path = Path(os.environ["MODEL_PATH"]) / "tokenizer.json"
        if not path.exists():  # pragma: no cover
            self.skipTest(f"no tokenizer.json under MODEL_PATH ({path})")
        tok = Tokenizer.from_file(str(path))
        n = len(tok.encode(IDENTITY).ids)
        self.assertLessEqual(
            n, 1_750,
            f"the always-on core is {n} tokens; Phase 6 left it at 1,632.")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
