"""WO-LORI-SAFETY-INTEGRATION-01 Phase 4 — INDIRECT IDEATION + DISTRESSED
RESPONSE BLOCK structural tests.

Phase 4 added a warm-first response template to prompt_composer.py for
the narrower IDEATION (indirect) / DISTRESSED tiers — additive to the
existing ACUTE SAFETY RULE.

These tests are STRUCTURAL: they verify the block is present in the
prompt source and contains the load-bearing language. They do NOT
attempt to validate the LLM's actual response to a distressed turn —
that's red-team eval work in Phase 6 (separate red-team pack with
Chris-cycled live model).

Why this matters as a regression guard:
- Prompt rules are easy to silently lose in a refactor
- The Friendship Line phone number must remain literal so it's stably
  surfaceable to operators auditing api.log responses
- The "do NOT lead with a refusal" rule is the load-bearing distinction
  between ACUTE (resource-first) and IDEATION (warm-first); losing it
  collapses Phase 4 back into Phase 1's ACUTE behavior on indirect
  language

Usage:
    python tests/test_safety_response_block.py
    python -m unittest tests.test_safety_response_block
    pytest tests/test_safety_response_block.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROMPT_COMPOSER = _REPO_ROOT / "server" / "code" / "api" / "prompt_composer.py"


class IndirectIdeationBlockPresenceTest(unittest.TestCase):
    """The Phase 4 INDIRECT IDEATION block is in prompt_composer.py."""

    @classmethod
    def setUpClass(cls):
        if not _PROMPT_COMPOSER.is_file():
            raise unittest.SkipTest(f"prompt_composer.py missing at {_PROMPT_COMPOSER}")
        cls.text = _PROMPT_COMPOSER.read_text(encoding="utf-8")

    def test_block_marker_present(self):
        self.assertIn(
            "INDIRECT IDEATION + DISTRESSED RESPONSE BLOCK",
            self.text,
            "Phase 4 block marker missing — has the INDIRECT IDEATION block "
            "been removed or renamed in a refactor?",
        )

    def test_friendship_line_number_present(self):
        # The literal phone number must appear so operators can grep
        # api.log for what the model surfaced. If a refactor or rewrite
        # drops the literal, the Friendship Line surface silently
        # disappears.
        self.assertIn(
            "1-800-971-0016",
            self.text,
            "Friendship Line phone number missing — Phase 4 specifies "
            "the literal number so it appears in surfaced responses.",
        )

    def test_friendship_line_context_present(self):
        self.assertIn(
            "Friendship Line",
            self.text,
            "Friendship Line label missing.",
        )
        self.assertIn(
            "60 and over",
            self.text,
            "'60 and over' framing for Friendship Line missing — this is "
            "the load-bearing population-fit framing.",
        )

    def test_988_still_present(self):
        # ACUTE rule's 988 reference is the safety floor; Phase 4 also
        # references 988 in its step-3 framing. Either way 988 must
        # remain in the prompt.
        self.assertIn("988", self.text)

    def test_warm_first_rule_present(self):
        # Load-bearing distinction from ACUTE: do NOT lead with the
        # resource on indirect ideation.
        self.assertIn(
            "ACKNOWLEDGE first",
            self.text,
            "Phase 4 'acknowledge first' rule missing — without it, "
            "indirect ideation collapses back into ACUTE-style "
            "resource-first response.",
        )
        self.assertIn(
            "Do NOT lead with a resource",
            self.text,
            "Phase 4 'do NOT lead with a resource' negative rule missing.",
        )

    def test_reflective_exception_present(self):
        # Past-tense references should NOT trigger Phase 4 — older
        # narrators talk about dark times in memoir mode and that's
        # normal processing.
        self.assertIn(
            "REFLECTIVE",
            self.text,
            "Reflective / past-tense exception marker missing.",
        )
        self.assertIn(
            "memory processing",
            self.text,
            "'memory processing' framing for past-tense exception missing.",
        )

    def test_no_pivot_rule_present(self):
        self.assertIn(
            "Do not pivot",
            self.text,
            "Phase 4 'do not pivot back to interview' rule missing.",
        )

    def test_no_refusal_rule_present(self):
        # Forbid the "I cannot continue" + "I'm an AI" disclaimer
        # opening on indirect ideation. This is shared with ACUTE but
        # repeated for the IDEATION block so it survives independent
        # edits to either block.
        self.assertIn(
            "DO NOT issue a refusal sentence",
            self.text,
            "Phase 4 no-refusal-sentence rule missing.",
        )

    def test_acute_rule_still_present(self):
        # Phase 4 must NOT have removed or weakened the ACUTE SAFETY RULE.
        self.assertIn("ACUTE SAFETY RULE", self.text)
        self.assertIn(
            "MANDATORY RESPONSE FORMAT for suicidal ideation",
            self.text,
            "Phase 4 must NOT have removed the ACUTE rule's mandatory "
            "response format.",
        )

    def test_outdated_273_still_forbidden(self):
        # The HARD-FORBIDDEN PHRASES list (273-TALK / 1-800-273-8255)
        # must still mention each as forbidden, not as a recommended
        # number. Spot-check via the canonical 273 prefix.
        self.assertIn(
            "273-TALK",
            self.text,
            "ACUTE rule's 273-TALK forbidden-phrase guard missing.",
        )

    def test_block_appears_after_acute_rule(self):
        # Structural ordering check: Phase 4 block should come AFTER
        # the ACUTE rule's HARD-FORBIDDEN PHRASES section. If it ever
        # appears BEFORE, that indicates a refactor moved the blocks
        # in a way that could affect prompt-composition order.
        acute_idx = self.text.find("ACUTE SAFETY RULE:")
        ideation_idx = self.text.find("INDIRECT IDEATION + DISTRESSED RESPONSE BLOCK")
        self.assertGreater(acute_idx, 0, "ACUTE rule marker not found")
        self.assertGreater(ideation_idx, 0, "Phase 4 block marker not found")
        self.assertGreater(
            ideation_idx, acute_idx,
            "Phase 4 block appears BEFORE the ACUTE rule — ordering "
            "regression. ACUTE rule must come first; Phase 4 is the "
            "narrower additive tier.",
        )


class FriendshipLineSourceCitationTest(unittest.TestCase):
    """The Friendship Line context paragraph cites the operator (Institute
    on Aging) and the population fit (60+). If those disappear, the
    surface loses its grounding."""

    @classmethod
    def setUpClass(cls):
        if not _PROMPT_COMPOSER.is_file():
            raise unittest.SkipTest(f"prompt_composer.py missing")
        cls.text = _PROMPT_COMPOSER.read_text(encoding="utf-8")

    def test_institute_on_aging_cited(self):
        self.assertIn("Institute on Aging", self.text)

    def test_24_7_warmline_framing(self):
        # The warmline framing distinguishes Friendship Line from 988.
        # 988 is acute crisis; Friendship Line is companionable +
        # crisis. Both can serve older narrators differently.
        self.assertIn("24/7 warmline", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
