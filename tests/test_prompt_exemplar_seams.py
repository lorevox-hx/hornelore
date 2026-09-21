"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Section B.

Registry authorities 4 and 11 were `PENDING_SEAM`: real prompt
interventions that could not be switched because their example families
lived inside larger string constants. `All Switchable Off` cannot be a
truthful label while an authority in that state exists — the operator
would press it and still ship Kent's induction story.

THE PROOF THAT MATTERS IS BYTE-EQUALITY. Separation is only safe if the
default composition reproduces the previous literal exactly. A split
that "looks right" but drops a blank line changes the prompt, and every
measurement taken afterwards would be against a different Lori than the
one the diagnostic studied.

These tests read the constants out of the module rather than importing
`prompt_composer`, which pulls the whole server package.
"""

import ast
import hashlib
import os
import unittest


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMPOSER = os.path.join(
    _REPO, "server", "code", "api", "prompt_composer.py")


def _module_constants():
    """Literal-valued module constants, plus the segment tuple's shape."""
    tree = ast.parse(open(_COMPOSER, encoding="utf-8").read())
    values, segments = {}, []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "_INTERVIEW_DISCIPLINE_SEGMENTS":
                for element in node.value.elts:
                    segments.append(
                        (element.elts[0].id, element.elts[1].value))
            else:
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except Exception:
                    pass
    return values, segments


_VALUES, _SEGMENTS = _module_constants()


class WitnessReceiptSeamTests(unittest.TestCase):
    """Authority 11 — one contiguous block between instruction and close."""

    def _parts(self):
        return (_VALUES["_WITNESS_RECEIPT_INSTRUCTION"],
                _VALUES["_WITNESS_RECEIPT_EXAMPLES"],
                _VALUES["_WITNESS_RECEIPT_CLOSING"])

    # The digest of the single literal that existed before the split,
    # measured at the moment of separation and proven equal to the
    # reassembled parts. Pinning it is what makes this a regression test
    # rather than a tautology: any edit to instruction, examples or
    # closing moves the digest and forces a deliberate decision instead
    # of silently changing the prompt every later measurement is
    # compared against.
    # Re-pinned 2026-09-21. The previous value pinned a composition whose
    # worked examples were one family's induction, wedding and the birth
    # of their first child, named hospital included — taken from a real
    # session and shipped to every narrator. The examples are invented
    # now. The seam property this digest protects is unchanged; when it
    # fails, read the diff before re-pinning, because a hash cannot tell
    # a deliberate replacement from an accidental edit.
    COMPOSITION_SHA256 = (
        "a6c337e25dd5b1a9c172501ed9d9246290d275266f5de6bc99ebfad33699b0c7")

    def test_default_composition_reassembles_to_one_exact_document(self):
        instruction, examples, closing = self._parts()
        rebuilt = instruction + examples + closing
        self.assertEqual(
            hashlib.sha256(rebuilt.encode()).hexdigest(),
            self.COMPOSITION_SHA256,
            "The default witness-receipt composition changed. Either a "
            "fragment was edited, or the separators drifted. Both change "
            "Lori; re-pin only after reading the diff.")
        self.assertNotIn("\n\n\n", rebuilt)
        self.assertTrue(rebuilt.startswith("WITNESS RECEIPT MODE"))
        self.assertTrue(
            rebuilt.rstrip().endswith("End with exactly one question mark."))

    def test_excluding_examples_removes_the_example_scenario(self):
        instruction, _examples, closing = self._parts()
        without = instruction + closing
        for token in ("Orrin Bay", "Cape Thistle", "Kellerman",
                      "Thistlecross", "Vantry", "lamp-oil manifest"):
            with self.subTest(token=token):
                self.assertNotIn(token, without)

    def test_the_forbidden_examples_travel_with_the_good_ones(self):
        """They carry the same scenario, so they are one authority.

        Excluding only the GOOD block would still ship the narrative
        into a prompt calling itself a clean baseline. This mattered
        more when the scenario was a real family's; it is still the
        right coupling now that it is invented, because a half-excluded
        example teaches half a lesson.
        """
        examples = _VALUES["_WITNESS_RECEIPT_EXAMPLES"]
        self.assertIn("GOOD EXAMPLE A", examples)
        self.assertIn("FORBIDDEN EXAMPLE A", examples)
        self.assertIn("FORBIDDEN EXAMPLE E", examples)

    def test_the_mimicry_prohibition_still_names_a_family_but_not_a_real_one(self):
        """The MUST NOT line has to quote the mimicry it forbids.

        REPLACES `test_residual_prohibition_names_are_kept_deliberately`,
        which asserted that a real son's and a real wife's names were
        PRESENT here. The reasoning was sound and the conclusion was
        wrong: the line is the guard against first-person mimicry, it
        does need concrete names to quote, and it lived in the
        INSTRUCTION rather than the examples — so it survived even when
        authority 11 excluded every example.

        The names are invented now. Both halves are pinned: the
        prohibition still demonstrates the failure, and it no longer
        does so with anyone's family.
        """
        instruction, _e, _c = self._parts()
        self.assertIn("daughter Nessa", instruction)
        self.assertIn("first-person mimicry", instruction)
        self.assertIn("You are NOT the narrator", instruction)
        for real in ("Janice", "Vince", "Kent"):
            with self.subTest(name=real):
                self.assertNotIn(real, instruction)

    def test_excluding_examples_is_a_large_share_of_the_directive(self):
        instruction, examples, closing = self._parts()
        full = len(instruction + examples + closing)
        self.assertGreater(
            len(examples) / full, 0.5,
            "The example block should dominate this directive; if it no "
            "longer does, the seam may have moved.")


class InterviewDisciplineSeamTests(unittest.TestCase):
    """Authority 4 — four fragments interleaved with the rules."""

    def _compose(self, include_examples):
        return "".join(
            _VALUES[name] for name, is_example in _SEGMENTS
            if include_examples or not is_example)

    def test_segments_alternate_and_cover_the_document(self):
        self.assertTrue(_SEGMENTS, "No segment tuple found.")
        self.assertEqual(
            sum(1 for _n, is_ex in _SEGMENTS if is_ex), 4,
            "Expected four example fragments: control-yield shapes, echo "
            "forms, and the illustrations inside rules 2 and 4.")

    # The nine segments must still reassemble into exactly one document,
    # with no seam drift. The hash pins THAT, not any particular wording.
    #
    # Updated 2026-09-21. The previous value pinned the composition that
    # carried a real family member's details — her town, her father's
    # workplace, her childhood surgery — taken from a development session
    # and compiled into a prompt every narrator receives. Leaving the old
    # hash in place would have made this test the thing that kept it.
    #
    # A hash test cannot tell a deliberate content change from an
    # accidental one, so when this fails, read the diff before re-pinning:
    # the seam property is what is being protected, and a new value
    # asserts only that somebody looked.
    COMPOSITION_SHA256 = (
        "7a504005f99b679bc99ba174be19c488d73cb00046abea82710439a5b72caccd")

    def test_default_composition_reassembles_to_one_exact_document(self):
        self.assertEqual(
            hashlib.sha256(self._compose(True).encode()).hexdigest(),
            self.COMPOSITION_SHA256,
            "The default interview-discipline composition changed. Nine "
            "segments must reassemble exactly; re-pin only after reading "
            "the diff.")

    def test_default_composition_has_no_doubled_blank_separators(self):
        composed = self._compose(True)
        self.assertNotIn("\n\n\n", composed)
        self.assertTrue(composed.startswith("INTERVIEW DISCIPLINE"))

    def test_excluding_examples_removes_the_leaked_biography(self):
        without = self._compose(False)
        for token in ("aluminum plant", "mastoidectomy", "Captain Kirk",
                      "T.J. Hooker"):
            with self.subTest(token=token):
                self.assertNotIn(token, without)

    def test_rules_still_read_continuously_without_their_examples(self):
        """A fragment removal must not leave a dangling rule.

        Each fragment is bounded by blank lines, so excluding one leaves
        exactly one separator rather than a rule that stops mid-thought.
        """
        without = self._compose(False)
        self.assertNotIn("\n\n\n", without)
        for header in ("ECHO FIRST, ASK SECOND",
                       "EXPLICIT REFLECTION DISCIPLINE",
                       "ANTI-CONFABULATION RULE",
                       "3. NO PSEUDO-EMPATHY OPENING"):
            with self.subTest(header=header):
                self.assertIn(header, without)

    def test_the_prohibition_still_names_places_but_invented_ones(self):
        """Rule 4 has to name places; it may not name a narrator's.

        REPLACES `test_residual_prohibition_names_are_kept_deliberately`,
        which asserted that Spokane and Montreal were PRESENT here. That
        was true, deliberate and wrong: rule 4 reads "if they said
        Spokane, do not add Washington" — real towns from a real
        narrator's record, inside the rule body rather than the exemplar
        block, and therefore surviving even when authority 4 excluded
        every example.

        The rule is unchanged and still needs concrete place names to
        teach with. They are invented now. This test pins both halves:
        the teaching survives, the family does not.
        """
        without = self._compose(False)
        self.assertIn("4. NO INVENTED CONTEXT", without)
        self.assertIn("Pellard Street", without)
        self.assertIn("Echo only what they put on the table.", without)

    def test_excluding_examples_measurably_shrinks_the_directive(self):
        full, without = len(self._compose(True)), len(self._compose(False))
        self.assertGreater(full - without, 2000)


if __name__ == "__main__":
    unittest.main()
