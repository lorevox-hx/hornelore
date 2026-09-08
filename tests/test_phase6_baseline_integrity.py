"""Phase 6 baseline-integrity corrections, pinned at production boundaries.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_phase6_baseline_integrity

Two defects found by the first Phase 6 lean run, both of which passed
every existing check because nothing tested the surface they lived on.

1. GUARD LAB AUTHORITY 44 DELETED A NARRATOR'S TURN.
   Era Fragment Repair is SWITCHABLE with a PURE counterfactual. Its OFF
   arm read `_repaired = ""` and then assigned unconditionally, so under
   Lean a complete reply became the empty string, was delivered as
   nothing, and was PERSISTED as nothing (turnrow:2285,
   `delivered_equals_persisted=True`). The logic sat inside the
   WebSocket handler where no test could reach it. It is now the pure
   service `api.services.lori_era_fragment.era_fragment_repair`, which
   imports only `re` — so these tests run on every interpreter and a
   mutation cannot hide behind a skip.

2. A DURABLY-KNOWN NAME NEVER REACHED THE MODEL.
   `runtime71.speaker_name` is session-scoped — the browser sets it only
   when the narrator SAYS their name (`session-loop.js:301`). For a
   narrator with the name on file who simply had not introduced
   themselves, `_known_identity_facts_block` omitted the Name line while
   the rules beside it told Lori to ask for anything missing. Measured:
   "Ada" appeared zero times across eleven traced prompts.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

# The pure guard, imported WITHOUT the router's web stack. Importing
# `api.routers.chat_ws` needs FastAPI; when it was the import target these
# six tests SKIPPED even on `.venv`, and a deliberate mutation "passed"
# because nothing ran. `OK` with skips is not a pass — so there is no
# skip guard here, and a broken import fails loudly instead.
from api.services.lori_era_fragment import era_fragment_repair
try:
    from api import prompt_composer
except Exception as exc:                                    # pragma: no cover
    prompt_composer = None
    _COMPOSER_ERR = exc


#: The exact reply Lean deleted, Phase 6 turn 10, 2026-09-07.
TURN_10 = "The seventies - that's a good starting point. What month and day were you born, then?"

#: Shapes the detector is meant to catch (registry id 44 "purpose").
FRAGMENTS = [
    "The conversations you had together back then?",
    "The reflections that came as you looked back on your life?",
    "Your favorite memory from that time?",
    "Those Sunday drives up to the pond?",
    TURN_10,
]

#: Shapes it must leave alone.
NOT_FRAGMENTS = [
    "That was a special time, wasn't it?",
    "The book is on the table?",
    "What was your mother like?",
    "Tell me about the quarry.",
    "I can imagine that was quite a route.",
]


class Authority44Counterfactual(unittest.TestCase):
    """OFF must mean 'do not repair', never 'delete'."""

    def test_selected_repairs_a_matching_fragment(self):
        text, fired, would = era_fragment_repair(
            "The conversations you had together back then?", selected=True)
        self.assertTrue(fired)
        self.assertEqual(
            text, "Can you tell me about the conversations you had "
                  "together back then?")
        self.assertEqual(would, text)

    def test_excluded_leaves_the_original_byte_for_byte(self):
        for original in FRAGMENTS:
            with self.subTest(original=original[:40]):
                text, fired, would = era_fragment_repair(
                    original, selected=False)
                self.assertEqual(
                    text, original,
                    "an excluded PURE counterfactual must yield the text "
                    "the model produced")
                self.assertFalse(fired)
                # The counterfactual stays OBSERVABLE without being applied.
                self.assertTrue(would)

    def test_excluded_can_never_empty_a_nonempty_reply(self):
        """The defect, stated as the property that forbids it."""
        for original in FRAGMENTS + NOT_FRAGMENTS:
            with self.subTest(original=original[:40]):
                text, _fired, _would = era_fragment_repair(
                    original, selected=False)
                self.assertNotEqual(
                    text.strip(), "",
                    "excluding a switchable transform manufactured an "
                    "empty response — this is exactly the Phase 6 turn 10 "
                    "defect")

    def test_turn_10_specifically_survives_when_44_is_off(self):
        text, fired, _ = era_fragment_repair(TURN_10, selected=False)
        self.assertEqual(text, TURN_10)
        self.assertFalse(fired)

    def test_non_fragments_are_untouched_in_both_arms(self):
        for original in NOT_FRAGMENTS:
            for selected in (True, False):
                with self.subTest(original=original[:36], selected=selected):
                    text, fired, would = era_fragment_repair(
                        original, selected=selected)
                    self.assertEqual(text, original)
                    self.assertFalse(fired)
                    self.assertEqual(would, "")

    def test_empty_and_none_input_are_safe(self):
        for value in (None, "", "   "):
            text, fired, would = era_fragment_repair(
                value, selected=True)
            self.assertFalse(fired)
            self.assertEqual(would, "")
            self.assertEqual(text, value or "")


@unittest.skipIf(prompt_composer is None, "api.prompt_composer did not import")
class DurableIdentityReachesTheModel(unittest.TestCase):
    """A narrator must not have to re-introduce themselves each session."""

    def test_persisted_identity_with_no_session_name_yields_all_three(self):
        """Chris's acceptance case, verbatim."""
        block = prompt_composer._known_identity_facts_block({
            "speaker_name": "",                 # never spoken this session
            "dob": "1948-03-17",
            "pob": "Barre, Vermont",
            "profile_seed": {"preferred_name": "Ada",
                             "full_name": "Ada Pruitt"},
        })
        self.assertIn("- Name: Ada", block)
        self.assertIn("- Date of birth: 1948-03-17", block)
        self.assertIn("- Place of birth: Barre, Vermont", block)

    def test_the_first_run_prompt_is_reproduced_and_then_corrected(self):
        """Before: no Name line at all. That is what shipped."""
        without_seed = prompt_composer._known_identity_facts_block({
            "speaker_name": "", "dob": "1948-03-17",
            "pob": "Barre, Vermont", "profile_seed": {},
        })
        self.assertNotIn("- Name:", without_seed)
        with_seed = prompt_composer._known_identity_facts_block({
            "speaker_name": "", "dob": "1948-03-17",
            "pob": "Barre, Vermont",
            "profile_seed": {"preferred_name": "Ada"},
        })
        self.assertIn("- Name: Ada", with_seed)

    def test_a_spoken_name_still_wins(self):
        self.assertEqual(
            prompt_composer.resolve_speaker_name({
                "speaker_name": "Addie",
                "profile_seed": {"preferred_name": "Ada"}}),
            "Addie", "session state is the narrator speaking now")

    def test_full_name_falls_back_to_its_first_token(self):
        self.assertEqual(
            prompt_composer.resolve_speaker_name({
                "speaker_name": "",
                "profile_seed": {"full_name": "Ada Pruitt"}}),
            "Ada")

    def test_nothing_known_stays_empty_rather_than_inventing(self):
        self.assertEqual(prompt_composer.resolve_speaker_name({}), "")
        self.assertEqual(
            prompt_composer._known_identity_facts_block({}),
            "KNOWN IDENTITY FACTS:\n- none yet")

    def test_childhood_home_is_never_rendered_as_a_birthplace(self):
        """The fallback deliberately NOT shared between the two blocks.

        `_narrator_identity_block` falls back `pob <- childhood_home`.
        Importing that into a block labelled authoritative would assert a
        birthplace nobody stated — the invention BUG-LG-01 exists to stop.
        """
        block = prompt_composer._known_identity_facts_block({
            "speaker_name": "Ada", "dob": "", "pob": "",
            "profile_seed": {"childhood_home": "Barre, Vermont"},
        })
        self.assertNotIn("Place of birth", block)
        self.assertIn("- Name: Ada", block)


class TraceTreatsNullEraAsAFact(unittest.TestCase):
    """`current_era=None` is a runtime fact, not broken instrumentation."""

    def setUp(self):
        from api.services import lori_response_trace as rt
        self.rt = rt
        self._prev = None
        import os
        self._prev = os.environ.get("HORNELORE_RESPONSE_TRACE")
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        rt._traces.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        import os
        if self._prev is None:
            os.environ.pop("HORNELORE_RESPONSE_TRACE", None)
        else:
            os.environ["HORNELORE_RESPONSE_TRACE"] = self._prev
        self.rt._traces.clear()

    def _armed(self):
        tid = self.rt.begin(narrator_id="n", conversation_id="c")
        self.assertIsNotNone(tid)
        return tid

    def test_a_null_era_does_not_fail_instrumentation(self):
        tid = self._armed()
        self.rt.note("narrator_input", "hello", trace_id=tid)
        self.rt.note("runtime71_current_era", None, trace_id=tid)
        self.rt.note("prompt_tokens", 2149, trace_id=tid)
        self.rt.note("prompt_budget", {"window": 8192}, trace_id=tid)
        self.rt.require(trace_id=tid)
        rec = self.rt._traces[tid]
        self.assertFalse(
            rec.get("instrumentation_failed"),
            "every turn of the Phase 6 baseline was stamped failed "
            "because no Life Map era was selected")
        self.assertEqual(rec.get("missing_required_context", []), [])

    def test_an_absent_era_key_still_fails(self):
        tid = self._armed()
        self.rt.note("narrator_input", "hello", trace_id=tid)
        self.rt.note("prompt_tokens", 2149, trace_id=tid)
        self.rt.note("prompt_budget", {"window": 8192}, trace_id=tid)
        self.rt.require(trace_id=tid)
        rec = self.rt._traces[tid]
        self.assertTrue(rec.get("instrumentation_failed"))
        self.assertIn("runtime71_current_era",
                      rec.get("missing_required_context", []))

    def test_genuinely_empty_prompt_evidence_still_fails(self):
        tid = self._armed()
        self.rt.note("narrator_input", "", trace_id=tid)
        self.rt.note("runtime71_current_era", None, trace_id=tid)
        self.rt.note("prompt_tokens", 2149, trace_id=tid)
        self.rt.note("prompt_budget", {"window": 8192}, trace_id=tid)
        self.rt.require(trace_id=tid)
        rec = self.rt._traces[tid]
        self.assertTrue(rec.get("instrumentation_failed"))
        self.assertIn("narrator_input",
                      rec.get("missing_required_context", []))


if __name__ == "__main__":
    unittest.main()
