"""A hint built from a suggestion must not say it is "on record".

SCOPE — deliberately small, and smaller than it was.

`_build_profile_seed` keeps queued suggestions in their own `suggested`
map, separate from `provisional` and from the answer buckets. That
design is correct and is already pinned by
`test_projection_read_safety.SuggestionIsNotAFactTests`. Nothing here
changes it.

One consumer reads that map: the identity confirmation hint. It used the
same wording whichever source the value came from —

    ALREADY ON RECORD (provisional): name = 'X'
    "I have X on record — is that the name you'd like me to use?"

For a suggestion that sentence is false. Lori guessed it; the record
does not say it. The repair is the wording, and only the wording.

WHAT THIS FILE IS NOT
---------------------
An earlier version claimed a narrator could be asked whether "kind of
scared" was the name they wanted used, and added a filter to
`_build_profile_seed` to prevent it.

That claim was wrong. Measured against a narrator with a saved name and
all three bad legacy rows queued, `_seed_preferred_name` resolves to the
real name and the suggestion is never consulted; reaching `_sugg_name`
needs a narrator with no name at all, which session creation does not
produce. The filter also fought the separate-map design above and broke
two of its tests. Both the claim and the filter are withdrawn.

The example is closed. What survives is the part that was true
independently of it: describing a guess as being on record is the same
laundering the write path refuses, performed in prose.
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class TheHintNamesItsSource(unittest.TestCase):

    def setUp(self):
        self.src = (REPO / "server" / "code" / "api" / "prompt_composer.py").read_text(
            encoding="utf-8")

    def test_the_on_record_wording_is_gated_on_a_recorded_value(self):
        """Each hint branch decides which claim it is making before it
        makes it."""
        self.assertIn("_from_record = bool(_seed_preferred_name or _seed_full_name)",
                      self.src)
        self.assertIn("_from_record = bool(_known_childhood_home)", self.src)

    def test_a_suggestion_hint_says_it_is_lori_s_own_reading(self):
        self.assertEqual(
            self.src.count("NOT ON RECORD — LORI'S OWN READING, UNCONFIRMED"), 2,
            "both branches must label a guess as a guess")

    def test_it_forbids_the_on_record_phrasing_in_that_branch(self):
        self.assertEqual(
            self.src.count("Do NOT say 'I have X on record'")
            + self.src.count("Do NOT state this as something on record"), 2)

    def test_the_separate_map_design_is_untouched(self):
        """Suggestions still reach `suggested`, unfiltered. That is what
        `SuggestionIsNotAFactTests` pins, and this file must not quietly
        undo it — an earlier version did."""
        self.assertIn("suggested[fp] = v.strip()", self.src)
        self.assertNotIn("_skip_for_hint", self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
