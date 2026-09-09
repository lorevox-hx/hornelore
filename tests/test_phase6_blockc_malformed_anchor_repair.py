"""Phase 6 Block C — the malformed-anchor repair.

WO-LORI-ARCHIVE-TO-MEMOIR-02, Phase 6, Block C (authorized 2026-09-08).

THE DEFECT. Both local proper-noun extractors tokenized names with
`[A-Z][a-zA-Z]+`, a character class admitting neither "." nor "'".
Punctuation inside a legitimate proper name therefore TERMINATED the
phrase and the remainder began a new one:

    "West St. Paul"        -> ['West St', 'Paul']
    "Saint Patrick's Day"  -> ['Saint Patrick', 'Day']
    "O'Connor"             -> ['Connor']

Those are not truncations. They are manufactured entities, and two
different Guard Lab authorities echoed them to the narrator verbatim:

    id 40  cc_chain_anchor_opener      "From Saint Patrick to Day to 1950 —"
           lori_communication_control.py, Step 6b
    id 48  witness_receipt_fallback    "X and Y — there's a lot held in that."
           lori_witness_mode.compose_chronological_chain_receipt

The two authorities consume DIFFERENT extractors, which is why both are
pinned here:

    id 40 <- factual_chain_capture.detect_factual_chain()["anchors"],
             threaded by chat_ws.py:6577-6579 as `narrator_anchors` and
             read at lori_communication_control.py:1282
    id 48 <- lori_structured_narrative_fallback.extract_safe_anchors(),
             called at lori_witness_mode.py:2157 and rendered straight
             into the receipt at lori_witness_mode.py:2176-2177

WHAT IS *NOT* ASSERTED HERE. The two extractors are mirrored on purpose
and are NOT identical — factual_chain_capture caps phrases at three
words and filters through _BAD_ANCHOR_TOKENS; the structured fallback
caps at four and filters through _CASCADE_FILTER_TOKENS. This file pins
only the punctuation invariant they legitimately share:

    punctuation inside a proper name must not manufacture separate
    entities.

There is no assertion anywhere in this file that the two extractors
return equal anchor sets, and `test_the_two_extractors_are_deliberately_
not_identical` exists to make a future "just share a helper" refactor
fail loudly.

SCOPE NOTE. Repairing these extractors does NOT vindicate id 40 or
id 48. It makes their inputs truthful enough that the authorities can be
evaluated on their own merits. Whether either stays enabled, defaults
off, or disappears is a later Phase 6 measured decision.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"
sys.path.insert(0, str(SERVER_CODE))

# All four modules are pure-stdlib at import time (re / dataclasses /
# typing), so none of this needs fastapi and none of it should skip.
from api.services.factual_chain_capture import (  # noqa: E402
    detect_factual_chain,
)
from api.services import factual_chain_capture as _fcc  # noqa: E402
from api.services.lori_structured_narrative_fallback import (  # noqa: E402
    extract_safe_anchors,
)
from api.services import (  # noqa: E402
    lori_structured_narrative_fallback as _lsnf,
)
from api.services.lori_communication_control import (  # noqa: E402
    enforce_lori_communication_control,
)
from api.services.lori_witness_mode import (  # noqa: E402
    compose_chronological_chain_receipt,
)


# "West St" must never appear unless a "." immediately follows it. This
# is the discriminating form: a plain `"West St" not in text` assertion
# would fail on the CORRECT output too, since "West St. Paul" contains
# "West St" as a substring.
_SPLIT_ST_RX = re.compile(r"West St(?!\.)")
# "Saint Patrick" not followed by the possessive clitic.
_SPLIT_PATRICK_RX = re.compile(r"Saint Patrick(?!['’]s)")


def _assert_name_intact(case, text, *, whole, split_rx):
    """The name survives whole AND its split form is absent."""
    case.assertIn(
        whole, text,
        f"expected the intact name {whole!r} in {text!r}")
    found = split_rx.search(text)
    case.assertIsNone(
        found,
        f"punctuation-split fabrication {found.group(0)!r} present "
        f"in {text!r}" if found else "")


# ══════════════════════════════════════════════════════════════════════
# Extractor regression — factual_chain_capture (id 40's anchor source)
# ══════════════════════════════════════════════════════════════════════

class FactualChainExtractorTests(unittest.TestCase):
    """Anchors are produced by the shipped classifier, never supplied."""

    def _anchors(self, text):
        return detect_factual_chain(text)["anchors"]

    def test_period_inside_a_place_name_does_not_split_it(self):
        anchors = self._anchors(
            "We moved from West St. Paul to Bardstown in 1961.")
        self.assertIn("West St. Paul", anchors)
        self.assertNotIn("West St", anchors)
        self.assertNotIn("Paul", anchors)

    def test_apostrophe_inside_a_holiday_name_does_not_split_it(self):
        anchors = self._anchors(
            "We always went to the Saint Patrick's Day parade in Lowell.")
        self.assertIn("Saint Patrick's Day", anchors)
        self.assertNotIn("Saint Patrick", anchors)
        self.assertNotIn("Day", anchors)

    def test_leading_apostrophe_surname_keeps_its_prefix(self):
        anchors = self._anchors(
            "Kathleen O'Connor drove us from Lowell to Boston that summer.")
        joined = " | ".join(anchors)
        self.assertIn("O'Connor", joined)
        self.assertNotIn("Connor", anchors)

    def test_from_to_endpoints_are_also_punctuation_aware(self):
        """_FROM_TO_RX feeds the id-40 opener most directly.

        Leaving it punctuation-blind would have preserved the defect on
        exactly the surface Block C repairs.
        """
        anchors = self._anchors(
            "We drove from West St. Paul to Mexico City that spring.")
        self.assertIn("West St. Paul", anchors)
        self.assertIn("Mexico City", anchors)

    # ── unchanged behaviour ──────────────────────────────────────────

    def test_ordinary_multiword_place_is_unchanged(self):
        anchors = self._anchors(
            "We went from Mexico City to North Quincy, then to Boston.")
        self.assertIn("Mexico City", anchors)
        self.assertIn("North Quincy", anchors)

    def test_existing_filter_token_behaviour_is_unchanged(self):
        """The 2026-07-02 live defect: "For the 2019 trip..." reached the
        narrator as the anchor "For". _BAD_ANCHOR_TOKENS still drops it.
        """
        anchors = self._anchors(
            "For the 2019 trip we went from Paris to Rome, then Naples.")
        self.assertNotIn("For", anchors)
        self.assertNotIn("Then", anchors)
        self.assertIn("Paris", anchors)

    def test_trailing_possessive_still_drops_the_clitic(self):
        """A possessive is only glued when another capitalized token
        follows. "Kent's house" is one entity either way, so the old
        unpossessed anchor is preserved rather than "improved" into
        something the narrator did not name.
        """
        anchors = self._anchors(
            "We drove to Kent's house in Lowell, then on to Boston.")
        self.assertIn("Kent", anchors)
        self.assertNotIn("Kent's", anchors)

    def test_a_sentence_boundary_is_not_a_name_boundary_to_be_crossed(self):
        """Only "St." joins across a period. An ordinary sentence-final
        period must still terminate the phrase.
        """
        anchors = self._anchors(
            "We settled in Boston. Paul came out the following year.")
        self.assertIn("Boston", anchors)
        self.assertNotIn("Boston. Paul", anchors)

    def test_sentence_final_st_keeps_its_previous_behaviour(self):
        """"St." only joins when a capitalized token immediately follows.

        With nothing to continue into, the abbreviation branch does not
        apply and the phrase terminates exactly as it did before.
        """
        anchors = self._anchors(
            "We lived on Currier St. we stayed nine years there.")
        self.assertIn("Currier St", anchors)


# ══════════════════════════════════════════════════════════════════════
# Extractor regression — structured fallback (id 48's anchor source)
# ══════════════════════════════════════════════════════════════════════

class StructuredFallbackExtractorTests(unittest.TestCase):

    def test_period_inside_a_place_name_does_not_split_it(self):
        anchors = extract_safe_anchors(
            "We moved to West St. Paul in 1961, and later to Bardstown.")
        self.assertIn("West St. Paul", anchors)
        self.assertNotIn("West St", anchors)
        self.assertNotIn("Paul", anchors)

    def test_apostrophe_inside_a_holiday_name_does_not_split_it(self):
        anchors = extract_safe_anchors(
            "The Saint Patrick's Day parade in Lowell was the big one.")
        self.assertIn("Saint Patrick's Day", anchors)
        self.assertNotIn("Saint Patrick", anchors)
        self.assertNotIn("Day", anchors)

    def test_leading_apostrophe_surname_keeps_its_prefix(self):
        anchors = extract_safe_anchors(
            "Kathleen O'Connor lived next door to us in Lowell.")
        joined = " | ".join(anchors)
        self.assertIn("O'Connor", joined)
        self.assertNotIn("Connor", anchors)

    # ── unchanged behaviour ──────────────────────────────────────────

    def test_ordinary_multiword_place_is_unchanged(self):
        anchors = extract_safe_anchors(
            "We went to Cochiti Pueblo and then Boston Latin School.")
        self.assertIn("Cochiti Pueblo", anchors)
        self.assertIn("Boston Latin School", anchors)

    def test_existing_cascade_filter_behaviour_is_unchanged(self):
        """Pins the two things the cascade filter actually guarantees.

        CORRECTED 2026-09-09. The first version of this test fed a bare
        run of capitalized words —

            "Wednesday October Mass Catholic Cochiti Pueblo Frank Elena"

        — and demanded the anchor "Cochiti Pueblo". That is not the
        pre-Block-C behaviour. This extractor's regex is deliberately
        greedy over up to FOUR capitalized words, so an unbroken run is
        one four-word phrase, and the filter only ever inspected the
        FIRST token and the WHOLE candidate. Demanding two-word
        segmentation invented a new requirement and dressed it as
        preservation — which would have pushed a production change to
        satisfy a test, in the wrong direction, for no measured reason.

        What the filter really guarantees, and all this test claims:

          * a leading filter token is stripped when a capitalized
            remainder follows  (lori_structured_narrative_fallback.py:69-79)
          * a candidate that IS a filter token in full is dropped  (:81-82)
        """
        anchors = extract_safe_anchors(
            "The Wednesday meeting was out at Cochiti Pueblo.")
        # "The Wednesday" -> leading "The" stripped -> "Wednesday" is
        # itself a filter token -> dropped entirely.
        self.assertNotIn("The Wednesday", anchors)
        self.assertNotIn("Wednesday", anchors)
        # The real place still survives.
        self.assertIn("Cochiti Pueblo", anchors)

    def test_the_four_word_greediness_is_pre_existing_and_not_changed(self):
        """Records the segmentation Block C deliberately leaves alone.

        An unbroken run of capitalized words becomes ONE phrase of up to
        four tokens. That is the behaviour at 4b205a8 and this repair
        does not touch it. It is pinned here so a future reader can tell
        that the coarse grouping is inherited and intentional, not
        something Block C introduced — and so nobody "fixes" it into
        matching factual_chain_capture's three-token cap by accident.
        """
        anchors = extract_safe_anchors(
            "We visited Cochiti Pueblo Frank Elena together.")
        self.assertIn("Cochiti Pueblo Frank Elena", anchors)

    def test_trailing_possessive_still_drops_the_clitic(self):
        anchors = extract_safe_anchors(
            "We drove to Kent's house in Lowell.")
        self.assertIn("Kent", anchors)
        self.assertNotIn("Kent's", anchors)

    def test_a_sentence_boundary_is_not_a_name_boundary_to_be_crossed(self):
        anchors = extract_safe_anchors(
            "We settled in Boston. Paul came out the following year.")
        self.assertIn("Boston", anchors)
        self.assertNotIn("Boston. Paul", anchors)


# ══════════════════════════════════════════════════════════════════════
# Production boundary — id 40, the chain-anchor opener
# ══════════════════════════════════════════════════════════════════════

class ChainAnchorOpenerBoundaryTests(unittest.TestCase):
    """The anchors are produced by the shipped classifier and consumed by
    the shipped enforcement entry point. Nothing in this class hands the
    guard a hand-built anchor list — that would supply the very property
    under test.
    """

    # Echoes none of the narrator's anchors, and is short enough to stay
    # under the 80-word skip threshold, so the opener is eligible.
    BLAND_REPLY = "That sounds like quite a journey. What happened after that?"

    def _run(self, narrator_text, assistant_text=None):
        detection = detect_factual_chain(narrator_text)
        result = enforce_lori_communication_control(
            assistant_text if assistant_text is not None else self.BLAND_REPLY,
            narrator_text,
            narrator_anchors=list(detection["anchors"]),
            is_factual_chain=bool(detection["is_factual_chain"]),
        )
        return detection, result

    def test_id40_cannot_manufacture_a_split_west_st_paul_opener(self):
        narrator = (
            "We moved from West St. Paul to Bardstown in 1961, "
            "then on to Mexico City.")
        detection, result = self._run(narrator)
        self.assertTrue(
            detection["is_factual_chain"],
            "fixture no longer classifies as a factual chain; the id-40 "
            "branch is unreachable and this test would pass vacuously. "
            f"detection={detection!r}")
        self.assertIn(
            "chain_anchor_echo_injected", result.warnings,
            "the id-40 opener did not fire, so this assertion proves "
            f"nothing. warnings={result.warnings!r} "
            f"anchors={detection['anchors']!r}")
        _assert_name_intact(
            self, result.final_text,
            whole="West St. Paul", split_rx=_SPLIT_ST_RX)

    def test_id40_cannot_manufacture_a_split_saint_patricks_day_opener(self):
        narrator = (
            "We went from the Saint Patrick's Day parade to Lowell, "
            "then out to Bardstown that same year.")
        detection, result = self._run(narrator)
        self.assertTrue(
            detection["is_factual_chain"],
            f"fixture no longer classifies as a chain: {detection!r}")
        self.assertIn(
            "chain_anchor_echo_injected", result.warnings,
            f"the id-40 opener did not fire. warnings={result.warnings!r} "
            f"anchors={detection['anchors']!r}")
        _assert_name_intact(
            self, result.final_text,
            whole="Saint Patrick's Day", split_rx=_SPLIT_PATRICK_RX)


# ══════════════════════════════════════════════════════════════════════
# Production boundary — id 48, the witness-receipt fallback
# ══════════════════════════════════════════════════════════════════════

class WitnessReceiptFallbackBoundaryTests(unittest.TestCase):
    """compose_chronological_chain_receipt is the shipped producer of the
    "X and Y — there's a lot held in that." string that id 48 substitutes
    as final_text at chat_ws.py:7178.
    """

    TEMPLATE_TAIL = "there's a lot held in that."

    def test_id48_cannot_manufacture_a_split_west_st_paul_receipt(self):
        receipt = compose_chronological_chain_receipt(
            "We moved to West St. Paul in 1961, and later to Bardstown.")
        self.assertTrue(
            receipt and self.TEMPLATE_TAIL in receipt,
            "the id-48 receipt template did not compose, so this "
            f"assertion proves nothing. receipt={receipt!r}")
        _assert_name_intact(
            self, receipt, whole="West St. Paul", split_rx=_SPLIT_ST_RX)

    def test_id48_cannot_manufacture_a_split_saint_patricks_day_receipt(self):
        receipt = compose_chronological_chain_receipt(
            "The Saint Patrick's Day parade in Lowell was the big one "
            "every single year.")
        self.assertTrue(
            receipt and self.TEMPLATE_TAIL in receipt,
            f"the id-48 receipt template did not compose: {receipt!r}")
        _assert_name_intact(
            self, receipt,
            whole="Saint Patrick's Day", split_rx=_SPLIT_PATRICK_RX)

    def test_id48_keeps_the_apostrophe_prefix_on_a_surname(self):
        receipt = compose_chronological_chain_receipt(
            "Kathleen O'Connor lived next door to us in Lowell for years.")
        self.assertTrue(
            receipt and self.TEMPLATE_TAIL in receipt,
            f"the id-48 receipt template did not compose: {receipt!r}")
        self.assertIn("O'Connor", receipt)


# ══════════════════════════════════════════════════════════════════════
# Parity — the punctuation invariant ONLY
# ══════════════════════════════════════════════════════════════════════

class PunctuationParityTests(unittest.TestCase):
    """The narrow invariant both extractors share.

    Deliberately NOT a general-equality test: the two return different
    anchor sets for the same input by design, and asserting otherwise
    would refuse against a correct product.
    """

    CASES = (
        ("We moved to West St. Paul in 1961 and later to Bardstown.",
         "West St. Paul", _SPLIT_ST_RX),
        ("The Saint Patrick's Day parade in Lowell was the big one.",
         "Saint Patrick's Day", _SPLIT_PATRICK_RX),
    )

    def test_neither_extractor_splits_a_punctuated_proper_name(self):
        for text, whole, split_rx in self.CASES:
            with self.subTest(name=whole, extractor="factual_chain_capture"):
                _assert_name_intact(
                    self, " | ".join(detect_factual_chain(text)["anchors"]),
                    whole=whole, split_rx=split_rx)
            with self.subTest(name=whole, extractor="structured_fallback"):
                _assert_name_intact(
                    self, " | ".join(extract_safe_anchors(text)),
                    whole=whole, split_rx=split_rx)

    def test_the_two_extractors_are_deliberately_not_identical(self):
        """Guards against a future "just share a helper" refactor.

        factual_chain_capture caps a phrase at three name tokens;
        lori_structured_narrative_fallback caps at four. They also filter
        through different vocabularies. If these ever converge it should
        be a decision, not a side effect.
        """
        self.assertNotEqual(
            _fcc._NAME_PHRASE, _lsnf._NAME_PHRASE,
            "the two extractors' phrase patterns became identical; the "
            "differing word caps are intentional (3 vs 4)")
        self.assertNotEqual(
            _fcc._BAD_ANCHOR_TOKENS, _lsnf._CASCADE_FILTER_TOKENS,
            "the two filter vocabularies became identical; they are "
            "intentionally different")


# ══════════════════════════════════════════════════════════════════════
# Recorded residue — ambiguity this repair does NOT claim to solve
# ══════════════════════════════════════════════════════════════════════

class RecordedAmbiguityTests(unittest.TestCase):
    """Per the Block C brief: RECORD the ambiguous grammar, do not
    pretend to solve it.

    "We lived on Currier St. Paul visited that winter" cannot be
    resolved by any regex — it is either "Currier St." followed by the
    person "Paul", or the place "Currier St. Paul". The repaired pattern
    reads it as ONE name.

    This test pins that choice so it is a visible, reviewable decision
    rather than an accident. It is NOT a claim that the reading is
    correct. Do not grow the parser to chase this case.
    """

    AMBIGUOUS = "We lived on Currier St. Paul visited that winter."

    def test_the_ambiguous_st_case_reads_as_one_name_and_is_recorded(self):
        anchors = extract_safe_anchors(self.AMBIGUOUS)
        self.assertIn("Currier St. Paul", anchors)


if __name__ == "__main__":
    unittest.main()
