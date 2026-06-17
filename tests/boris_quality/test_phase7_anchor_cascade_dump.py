from __future__ import annotations

import unittest

from scripts.harness_lib import ChapterConfig, score_chapter
from tests.boris_quality._helpers import assert_row_fails, require_callable
from tests.boris_quality.fixtures.boris_quality_cases import JOE_EARLIEST_NARRATOR


class AnchorCascadeDumpTests(unittest.TestCase):
    """Phase 7 — structured narrative fallback anchor-cascade tests."""

    CASCADE = (
        "You went from Cochiti Pueblo to August, then Frank, Elena, Andrew, "
        "Mary, Catholic, and Mass. What happened next?"
    )

    def test_scorer_fails_anchor_cascade_dump(self):
        chapter = ChapterConfig(
            label="Joe Earliest",
            runtime71_era="earliest_years",
            text=JOE_EARLIEST_NARRATOR,
            anchors=["cochiti pueblo", "frank", "elena"],
            word_budget=110,
        )
        score = score_chapter(chapter, self.CASCADE)
        assert_row_fails(self, score, "no_titlecased_anchor_cascade")
        assert_row_fails(self, score, "direct_human_voice")

    def test_direct_anchor_filter_drops_calendar_religious_and_common_noise(self):
        extract_safe_anchors = require_callable([
            ("server.code.api.services.structured_narrative_fallback", "extract_safe_anchors"),
            ("server.code.api.services.structured_narrative", "extract_safe_anchors"),
            ("server.code.api.services.lori_structured_narrative", "extract_safe_anchors"),
        ])
        text = (
            "Wednesday October Mass Catholic Cochiti Pueblo Frank Elena Andrew Mary "
            "August Tuesday Time Albany Movement Mount Zion"
        )
        anchors = extract_safe_anchors(text)
        anchors_lower = [str(a).lower() for a in anchors]
        for bad in ["wednesday", "tuesday", "october", "catholic", "mass", "time", "august"]:
            self.assertNotIn(bad, anchors_lower, f"Noise anchor should be filtered: {bad}")
        self.assertIn("cochiti pueblo", " ".join(anchors_lower))
        self.assertLessEqual(len(anchors_lower), 4, "Fallback anchor set should stay small and human.")

    def test_direct_structured_fallback_does_not_use_you_went_from_template(self):
        build_fallback = require_callable([
            ("server.code.api.services.structured_narrative_fallback", "build_structured_narrative_fallback"),
            ("server.code.api.services.structured_narrative", "build_structured_narrative_fallback"),
            ("server.code.api.services.lori_structured_narrative", "build_structured_narrative_fallback"),
        ])
        response = build_fallback(
            narrator_text=JOE_EARLIEST_NARRATOR,
            anchors=["Cochiti Pueblo", "Frank", "Elena", "Andrew", "Mary", "Catholic", "Mass"],
        )
        self.assertNotIn("You went from", response)
        self.assertNotRegex(response, r"then .+, .+, .+")
        self.assertIn("Cochiti", response)


if __name__ == "__main__":
    unittest.main()
