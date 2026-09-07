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
    PRE_SPLIT_SHA256 = (
        "527232726cf04790c5d1354e15bf3164f025f8760a026fffbc81efb9f733d799")

    def test_default_composition_is_byte_identical_to_the_old_literal(self):
        instruction, examples, closing = self._parts()
        rebuilt = instruction + examples + closing
        self.assertEqual(
            hashlib.sha256(rebuilt.encode()).hexdigest(),
            self.PRE_SPLIT_SHA256,
            "The default witness-receipt composition no longer matches the "
            "literal it replaced. Either a fragment was edited, or the "
            "separators drifted. Both change Lori.")
        self.assertNotIn("\n\n\n", rebuilt)
        self.assertTrue(rebuilt.startswith("WITNESS RECEIPT MODE"))
        self.assertTrue(
            rebuilt.rstrip().endswith("End with exactly one question mark."))

    def test_excluding_examples_removes_the_leaked_biography(self):
        instruction, _examples, closing = self._parts()
        without = instruction + closing
        for token in ("Fargo", "Fort Ord", "Stanley", "Landstuhl",
                      "Bismarck", "Kaiserslautern", "meal ticket"):
            with self.subTest(token=token):
                self.assertNotIn(token, without)

    def test_the_forbidden_examples_travel_with_the_good_ones(self):
        """They carry the same biography, so they are one authority.

        Excluding only the GOOD block would still ship "train to Fargo"
        and "Stanley, Fargo, and Fort Ord" into a prompt calling itself
        a clean baseline.
        """
        examples = _VALUES["_WITNESS_RECEIPT_EXAMPLES"]
        self.assertIn("GOOD EXAMPLE A", examples)
        self.assertIn("FORBIDDEN EXAMPLE A", examples)
        self.assertIn("FORBIDDEN EXAMPLE E", examples)

    def test_residual_prohibition_names_are_kept_deliberately(self):
        """Vince and Janice stay in the MUST NOT section.

        That line is the guard against Kent's original K10 first-person
        mimicry. Removing it to make a baseline look name-free would
        reintroduce the failure the directive exists to prevent.
        """
        instruction, _e, _c = self._parts()
        self.assertIn("our son", instruction)
        self.assertIn("Janice", instruction)

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

    PRE_SPLIT_SHA256 = (
        "2b00eeadb2035aadb00c5c4a15ba2e85624f01ae023b3104135ca51445c833e6")

    def test_default_composition_is_byte_identical_to_the_old_literal(self):
        self.assertEqual(
            hashlib.sha256(self._compose(True).encode()).hexdigest(),
            self.PRE_SPLIT_SHA256,
            "The default interview-discipline composition no longer matches "
            "the literal it replaced. Nine segments must reassemble exactly.")

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

    def test_residual_prohibition_names_are_kept_deliberately(self):
        """Rule 4 names Spokane and Montreal inside the prohibition.

        "If they said Spokane, do not add Washington or quite far from
        Montreal" IS the rule. It is not an exemplar and it stays.
        """
        without = self._compose(False)
        self.assertIn("Spokane", without)
        self.assertIn("Montreal", without)

    def test_excluding_examples_measurably_shrinks_the_directive(self):
        full, without = len(self._compose(True)), len(self._compose(False))
        self.assertGreater(full - without, 2000)


if __name__ == "__main__":
    unittest.main()
