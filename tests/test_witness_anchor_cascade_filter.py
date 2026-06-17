"""
BUG-LORI-ANCHOR-CASCADE-DUMP-01
================================

Tests for the anchor-cascade filter + 2-item cap in
`services.lori_witness_mode._format_multi_anchor_list` plus
`_filter_cascade_residue`.

Before the patch the structured-narrative templates produced these
mechanical cascade dumps across the 2026-06-17 full-family run:

  - Walter Era 2: "You went from Saint Augustine to Brendan, then Eileen,
    Patrick, Catholic, South Boston, Mass, and Walter. What happened next?"
  - Walter Era 4: "You went from Boston College to Brendan, then Chestnut
    Hill, Kennedy, Irish, Catholic, Schlitz, and Eileen. What happened next?"
  - Joe Earliest: "You went from Cochiti Pueblo to August, then Frank,
    Elena, Andrew, Mary, Catholic, and Mass. What happened next?"
  - Pat Later: "You went from Wednesday to Betty, then Madeleine, Engle,
    Wrinkle, Time, Tuesday, and October."
  - Mable Later: "You went from Charlene to Atlanta, then Bernard, Detroit,
    Plymouth Road, Albany, Earnest, and Lillian."

The fix:
  1. `_filter_cascade_residue()` drops calendar tokens (Wednesday,
     October, August, March, etc.), religious-residue tokens (Catholic,
     Mass, Church, School), and joining-word residue (then, the, and).
  2. `_format_multi_anchor_list` caps at 2 items (was Oxford-style "A,
     B, and C" with no cap).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))

from server.code.api.services.lori_witness_mode import (
    _filter_cascade_residue,
    _format_multi_anchor_list,
)


class FilterCascadeResidueTest(unittest.TestCase):
    def test_drops_calendar_tokens(self):
        anchors = ["Wednesday", "Betty", "October"]
        filtered = _filter_cascade_residue(anchors)
        self.assertEqual(filtered, ["Betty"])

    def test_drops_religious_residue(self):
        anchors = ["Catholic", "Saint Augustine", "Mass", "Church"]
        filtered = _filter_cascade_residue(anchors)
        self.assertEqual(filtered, ["Saint Augustine"])

    def test_drops_joining_residue(self):
        anchors = ["then", "the", "and", "Boston Latin"]
        filtered = _filter_cascade_residue(anchors)
        self.assertEqual(filtered, ["Boston Latin"])

    def test_strips_leading_then(self):
        anchors = ["then Eileen"]
        filtered = _filter_cascade_residue(anchors)
        self.assertEqual(filtered, ["Eileen"])

    def test_dedupes_case_insensitive(self):
        anchors = ["Boston", "boston", "BOSTON"]
        filtered = _filter_cascade_residue(anchors)
        self.assertEqual(filtered, ["Boston"])

    def test_preserves_real_anchors(self):
        anchors = ["Stanley", "Fargo", "Boston Latin School"]
        filtered = _filter_cascade_residue(anchors)
        self.assertEqual(filtered, ["Stanley", "Fargo", "Boston Latin School"])


class FormatMultiAnchorListCapTest(unittest.TestCase):
    def test_one_anchor_returns_as_is(self):
        out = _format_multi_anchor_list(["Stanley"], "en")
        self.assertEqual(out, "Stanley")

    def test_two_anchors_joined_with_and(self):
        out = _format_multi_anchor_list(["Stanley", "Fargo"], "en")
        self.assertEqual(out, "Stanley and Fargo")

    def test_three_anchors_capped_at_two(self):
        # Was Oxford-style "Stanley, Fargo, and Germany" pre-patch
        out = _format_multi_anchor_list(["Stanley", "Fargo", "Germany"], "en")
        # Should drop the 3rd entry entirely
        self.assertEqual(out, "Stanley and Fargo")

    def test_seven_anchors_capped_at_two_after_filter(self):
        # Walter Era 2 verbatim cascade input
        anchors = [
            "Saint Augustine", "Brendan", "then Eileen", "Patrick",
            "Catholic", "South Boston", "Mass", "Walter",
        ]
        out = _format_multi_anchor_list(anchors, "en")
        # After filter ("Catholic"/"Mass" dropped, "then Eileen" → "Eileen")
        # and 2-item cap, the result should be "Saint Augustine and Brendan"
        self.assertEqual(out, "Saint Augustine and Brendan")

    def test_cochiti_pueblo_calendar_filtered(self):
        # Joe Earliest verbatim cascade
        anchors = [
            "Cochiti Pueblo", "August", "then Frank", "Elena",
            "Andrew", "Mary", "Catholic", "Mass",
        ]
        out = _format_multi_anchor_list(anchors, "en")
        # August (month) dropped, Catholic/Mass dropped, "then Frank" → "Frank"
        # First two survivors: Cochiti Pueblo and Frank
        self.assertEqual(out, "Cochiti Pueblo and Frank")

    def test_all_filtered_returns_empty(self):
        anchors = ["Catholic", "Mass", "Wednesday", "October", "then"]
        out = _format_multi_anchor_list(anchors, "en")
        self.assertEqual(out, "")

    def test_spanish_locale_uses_y_conjunction(self):
        out = _format_multi_anchor_list(["Stanley", "Fargo"], "es")
        self.assertEqual(out, "Stanley y Fargo")


if __name__ == "__main__":
    unittest.main()
