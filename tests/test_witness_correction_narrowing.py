"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Part 2.

John's opening chapter — 238 words of autobiography, his mother at 99,
West St. Paul in the sixties — was routed to META_FEEDBACK/correction by
the last un-narrowed member of the `not X but Y` family, and Lori
answered:

    "Got it — That I Still Picture Clearly. What happened next?"

`api.log` carries that misroute THREE times: conv=switch_mth7rdrj_3pnp
(2026-08-31), conv=da567099-505 and conv=8bd4ae81-1ec (2026-09-06). It
is deterministic, not sampling noise.

WHY THE PASSAGE IS READ FROM THE SHIPPED HARNESS RATHER THAN RETYPED.
`docs/TESTING-DOCTRINE.md`: a fixture may not supply the property being
proven. A hand-copied approximation of John's sentence would prove that
*this file's* string falls through, not that John's does. The passage is
loaded from `scripts/run_john_baldy_seven_era_harness.py` and its
properties are MEASURED at import, so a harness edit fails here loudly
instead of silently testing a different sentence.
"""

import os
import re
import unittest

from api.services import lori_witness_mode as wm


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HARNESS = os.path.join(_REPO, "scripts", "run_john_baldy_seven_era_harness.py")
_CHAT_WS = os.path.join(
    _REPO, "server", "code", "api", "routers", "chat_ws.py")


def _load_john_era_01():
    """The real passage, from the real harness file."""
    with open(_HARNESS, encoding="utf-8") as fh:
        for line in fh:
            if "still picture clearly" in line:
                return line.rstrip().rstrip("\\")
    raise AssertionError(
        f"John's era-01 passage no longer contains the clause this "
        f"regression exists for. Looked in {_HARNESS}.")


JOHN_ERA_01 = _load_john_era_01()

# ── MEASURED fixture properties. Declared, then checked against the
# real file — not asserted in a comment. ──────────────────────────────
_JOHN_WORDS = len(JOHN_ERA_01.split())
_JOHN_HAS_CLAUSE = "have not lived in for decades but that i still picture clearly" \
    in JOHN_ERA_01.lower()


def _code_lines(path):
    """Source lines with comments and blanks removed.

    CLAUDE.md records three source-slicing test bugs in one day where
    `index()` / `count()` matched a COMMENT or a definition instead of
    the statement, and all three passed against broken code. Every
    source assertion below runs over this stripped view.
    """
    out = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            out.append(stripped)
    return out


class JohnOpeningFixtureTests(unittest.TestCase):
    """If the harness text drifts, fail HERE with the measured values."""

    def test_passage_is_the_dense_autobiographical_chapter(self):
        self.assertGreaterEqual(
            _JOHN_WORDS, 200,
            f"John's era-01 passage measured {_JOHN_WORDS} words; this "
            f"regression is about a long autobiographical turn.")

    def test_passage_still_contains_the_triggering_clause(self):
        self.assertTrue(
            _JOHN_HAS_CLAUSE,
            "The 'not lived in ... but that I still picture clearly' "
            "clause is gone from the harness. This test no longer "
            "reproduces the John misroute.")


class JohnMustNotRouteAsCorrectionTests(unittest.TestCase):

    def test_john_opening_is_not_a_correction(self):
        d = wm.detect_witness_event(JOHN_ERA_01)
        self.assertNotEqual(
            d.sub_type, "correction",
            f"John's autobiography routed as a correction again: "
            f"anchor={d.factual_anchor!r}")

    def test_john_opening_yields_no_correction_anchor(self):
        """The exact string the narrator saw must be unreachable."""
        self.assertEqual(wm._extract_correction_value(JOHN_ERA_01), "")
        d = wm.detect_witness_event(JOHN_ERA_01)
        self.assertNotIn("picture clearly", (d.factual_anchor or "").lower())

    def test_john_opening_reaches_generation_not_the_deterministic_bypass(self):
        """META_FEEDBACK bypasses the model; STRUCTURED_NARRATIVE does not.

        chat_ws.py:3822 sets `turn_mode = "witness"` for META_FEEDBACK,
        and 4359 gates the deterministic finalize on that value — so a
        correction verdict means no LLM runs at all. STRUCTURED_NARRATIVE
        instead sets `_witness_use_llm_receipt` and leaves turn_mode
        alone, so generation proceeds. John must land on the second.
        """
        d = wm.detect_witness_event(JOHN_ERA_01)
        self.assertNotEqual(d.detection_type, "META_FEEDBACK")


class OrdinaryContrastFallsThroughTests(unittest.TestCase):

    CASES = (
        "I did not go to college but I went to trade school.",
        "We were not rich but we were happy.",
        "It was not something I planned but it turned out well.",
        "I have not seen my brother in years but we write.",
    )

    def test_ordinary_contrast_is_not_a_repair(self):
        for text in self.CASES:
            with self.subTest(text=text):
                self.assertFalse(wm._not_x_but_y_is_a_repair(text))
                self.assertNotEqual(
                    wm.detect_witness_event(text).sub_type, "correction")


class RealRepairsStillRouteTests(unittest.TestCase):
    """The narrowing must not mute a genuine correction."""

    def test_kent_k10_still_routes_and_keeps_its_value(self):
        text = ("you have the name of the hospital wrong not Lansdale Army "
                "hospital but landstuhl air force hospital ramstein air "
                "force base")
        d = wm.detect_witness_event(text)
        self.assertEqual(d.sub_type, "correction")
        self.assertIn("landstuhl", (d.factual_anchor or "").lower())

    def test_bare_not_x_but_y_repairs_still_route(self):
        for text in ("It was not Fargo but Bismarck.",
                     "you have the name wrong not Smith but Jones",
                     "The hospital was not Lansdale but it was Landstuhl."):
            with self.subTest(text=text):
                self.assertTrue(wm._not_x_but_y_is_a_repair(text))
                self.assertEqual(
                    wm.detect_witness_event(text).sub_type, "correction")

    def test_sibling_patterns_are_untouched(self):
        for text in ("actually it was Bismarck not Fargo",
                     "I meant Fort Ord not Fort Lewis",
                     "actually the year was 1962 not 1961",
                     "you got the year wrong, it was 1960 not 1959"):
            with self.subTest(text=text):
                self.assertEqual(
                    wm.detect_witness_event(text).sub_type, "correction")


class CommaFormTests(unittest.TestCase):
    """The extractor skip is scoped to the `but` form — and the comma
    alternative turns out to be unreachable anyway.

    MEASURED, and it corrected my own assumption. I scoped the extractor
    skip to `" but "` to avoid regressing comma-form repairs, then wrote
    a test asserting the comma form works. It does not, and it never did:
    `_CORRECTION_AFTER_NOT_BUT_RX` requires `\\s+` BEFORE `(?:but|,)`, so
    "hospital, Landstuhl" — the way anyone actually types — cannot reach
    the `,` alternative. Only "hospital , Landstuhl" does.

    The pattern is byte-identical to HEAD, so this is a PRE-EXISTING dead
    branch, not a regression from this change. It is recorded rather than
    widened: widening a correction detector on a live narrator path is
    exactly what this part is undoing, and the file already set that
    precedent — "a missed deterministic intercept is a much smaller harm
    than a wrong one".

    The scoping in `_extract_correction_value` stays. It costs nothing
    and it is correct if the pattern is ever repaired.
    """

    def test_comma_alternative_is_unreachable_as_typed(self):
        rx = wm._CORRECTION_AFTER_NOT_BUT_RX
        self.assertIsNone(
            rx.search("not Lansdale Army hospital, Landstuhl Air Force Hospital."),
            "The comma branch became reachable. Re-examine whether the "
            "extractor skip should still be scoped to the 'but' form.")
        self.assertIsNotNone(
            rx.search("not Lansdale Army hospital , Landstuhl Air Force Hospital."))

    def test_but_form_still_extracts(self):
        value = wm._extract_correction_value(
            "you got that wrong not Lansdale Army hospital but "
            "Landstuhl Air Force Hospital.")
        self.assertIn("landstuhl", value.lower())

    def test_ordinary_comma_contrast_is_not_a_repair(self):
        self.assertFalse(
            wm._not_x_but_y_is_a_repair("not lonely, just quiet"))


class BothDiscriminatorsAreLoadBearingTests(unittest.TestCase):
    """Each rule must be independently necessary.

    If either is deleted, one of these two cases starts reading as a
    repair — so a mutation of either branch fails a test rather than
    surviving behind the other.
    """

    def test_subordinator_rule_alone_rejects(self):
        # aux rule ACCEPTS (X "Fargo" is capitalised); only the
        # subordinator rule can reject this.
        self.assertFalse(
            wm._not_x_but_y_is_a_repair("It was not Fargo but that I remember well."))

    def test_auxiliary_rule_alone_rejects(self):
        # subordinator rule ACCEPTS ("I" is not a subordinator); only the
        # auxiliary rule can reject this.
        self.assertFalse(
            wm._not_x_but_y_is_a_repair("I have not lived there but I picture it clearly."))


class ProductionBoundaryTests(unittest.TestCase):
    """Cite the line that READS the value.

    The guard is only worth anything if production still routes on these
    verdicts. These assertions run over comment-stripped source.
    """

    def test_meta_feedback_sets_the_bypassing_turn_mode(self):
        lines = _code_lines(_CHAT_WS)
        self.assertIn('turn_mode = "witness"', lines)

    def test_structured_narrative_enables_the_receipt_instead(self):
        lines = _code_lines(_CHAT_WS)
        self.assertTrue(
            any(l.startswith("_witness_use_llm_receipt = True") for l in lines),
            "STRUCTURED_NARRATIVE no longer routes to the LLM receipt "
            "path; John's opening may be bypassing generation again.")

    def test_deterministic_finalize_is_gated_on_witness_turn_mode(self):
        lines = _code_lines(_CHAT_WS)
        self.assertTrue(
            any('if turn_mode == "witness" and _witness_answer is not None:' == l
                for l in lines),
            "The deterministic bypass gate changed shape. Re-verify that "
            "a non-correction verdict still reaches generation.")

    def test_detector_and_extractor_consult_one_authority(self):
        """Counted over CODE, not raw text.

        The first version of this test used `src.count(...)` on the whole
        file and matched a comment mentioning the function by name —
        the precise mistake CLAUDE.md records three instances of. It
        passed for the wrong reason.
        """
        lines = _code_lines(
            os.path.join(_REPO, "server", "code", "api", "services",
                         "lori_witness_mode.py"))
        definitions = [l for l in lines
                       if l.startswith("def _not_x_but_y_is_a_repair(")]
        call_sites = [l for l in lines
                      if "_not_x_but_y_is_a_repair(" in l
                      and not l.startswith("def ")]
        self.assertEqual(len(definitions), 1,
                         "There must be exactly one authority.")
        self.assertEqual(
            len(call_sites), 2,
            f"Expected the detector and the extractor to be the only two "
            f"callers; found {len(call_sites)}: {call_sites}. If they "
            f"stop agreeing, an ordinary contrast can be extracted as a "
            f"repair even when detection declined it.")


if __name__ == "__main__":
    unittest.main()
