"""WO-LORI-ORAL-HISTORY-DEFAULT-01 (2026-06-14) — per-style parameter tests.

Covers acceptance gate #4: per-style word-cap dict explicit values
for all 6 supported styles; default for unknown styles flips from
55 → 90 (clear_direct heritage → oral_history heritage).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.lori_communication_control import (  # noqa: E402
    _DEFAULT_WORD_LIMIT,
    _SESSION_STYLE_WORD_LIMITS,
)


class WordLimitsTableShapeTest(unittest.TestCase):
    def test_all_six_styles_present(self):
        # Order in the dict drives readability — assert presence, not
        # iteration order (Python dicts are ordered but tests should
        # not couple to that for resilience).
        expected = {
            "oral_history", "warm_storytelling", "companion",
            "memory_exercise", "questionnaire_first", "clear_direct",
        }
        self.assertEqual(set(_SESSION_STYLE_WORD_LIMITS.keys()), expected)

    def test_default_flipped_to_oral_history_cap(self):
        # Pre-WO default was 55 (clear_direct heritage). Post-WO, the
        # default for unrecognized styles becomes 90 (oral_history
        # heritage) so missing/unknown keys land on the new system
        # default's cap instead of the tightest.
        self.assertEqual(_DEFAULT_WORD_LIMIT, 90)


class WordLimitsValueTest(unittest.TestCase):
    def test_oral_history_word_cap(self):
        # Per WO §4 target table: 90
        self.assertEqual(_SESSION_STYLE_WORD_LIMITS["oral_history"], 90)

    def test_warm_storytelling_word_cap(self):
        # Per WO §4: kept at 90 (operator-confirmed "defensible" path —
        # oral_history and warm_storytelling share cap; styles differ
        # on posture, not cap).
        self.assertEqual(_SESSION_STYLE_WORD_LIMITS["warm_storytelling"], 90)

    def test_companion_word_cap(self):
        # Pre-WO: 80. WO §4 target: 50. We keep at 80 in v1 to avoid
        # tightening companion mid-flight for current narrators; if
        # the next iteration shows companion turns are too long the
        # tightening lands as a follow-up.
        self.assertEqual(_SESSION_STYLE_WORD_LIMITS["companion"], 80)

    def test_memory_exercise_word_cap(self):
        # Per WO §4: 60 — picker entry stays shelved (REMOVED
        # 2026-04-25) but the table is closed so unknown-key lookups
        # never silently fall through to default.
        self.assertEqual(_SESSION_STYLE_WORD_LIMITS["memory_exercise"], 60)

    def test_questionnaire_first_word_cap(self):
        # Per WO §4: 70 (unchanged from pre-WO)
        self.assertEqual(
            _SESSION_STYLE_WORD_LIMITS["questionnaire_first"], 70,
        )

    def test_clear_direct_word_cap(self):
        # Per WO §4: 55 (unchanged from pre-WO; v1 disposition keeps
        # picker entry pending separate reconciliation WO)
        self.assertEqual(_SESSION_STYLE_WORD_LIMITS["clear_direct"], 55)


class CommunicationControlPublicAPITest(unittest.TestCase):
    def test_default_session_style_keyword_flipped(self):
        # The public enforce_lori_communication_control entry point's
        # session_style kwarg default flipped clear_direct → oral_history.
        import inspect
        from api.services.lori_communication_control import (
            enforce_lori_communication_control,
        )
        sig = inspect.signature(enforce_lori_communication_control)
        self.assertEqual(
            sig.parameters["session_style"].default,
            "oral_history",
        )

    def test_result_dataclass_default_style_flipped(self):
        # The CommunicationControlResult dataclass's session_style
        # default also flips so harness records that omit the field
        # report the new default style.
        from api.services.lori_communication_control import (
            CommunicationControlResult,
        )
        r = CommunicationControlResult(
            original_text="x", final_text="x", changed=False,
        )
        self.assertEqual(r.session_style, "oral_history")


if __name__ == "__main__":
    unittest.main(verbosity=2)
