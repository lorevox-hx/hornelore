"""WO-LORI-ORAL-HISTORY-DEFAULT-01 (2026-06-14) — integration tests.

Covers acceptance gate #0 (style exists as first-class runtime style)
and gate #3 (composer assembles oral_history when style is missing or
unknown). Verifies the cross-file wiring without spinning the full
stack.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


class PromptBlockExistsTest(unittest.TestCase):
    def test_lori_oral_history_response_defined(self):
        from api.prompt_composer import LORI_ORAL_HISTORY_RESPONSE
        self.assertIsInstance(LORI_ORAL_HISTORY_RESPONSE, str)
        self.assertGreater(len(LORI_ORAL_HISTORY_RESPONSE), 200)

    def test_block_carries_oral_history_posture_markers(self):
        import re
        from api.prompt_composer import LORI_ORAL_HISTORY_RESPONSE
        # Normalize whitespace so phrases that wrap a 70-col block
        # still match. The block's READABILITY is the source of truth
        # for the LLM; the test verifies semantic content, not column
        # width.
        text = re.sub(r"\s+", " ", LORI_ORAL_HISTORY_RESPONSE.lower())
        # The block must explicitly establish the posture per WO §0a
        for phrase in (
            "narrator leads",
            "one question",
            "you may open one door",
            "long stories are welcome",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), text)

    def test_block_lists_forbidden_actions(self):
        # Per WO §0a, the posture must explicitly forbid redirection,
        # verification, and steering — these are the failure modes the
        # block is engineered to prevent. Whitespace is normalized
        # before substring search because the block wraps at ~70 cols
        # for readability and phrases like "do not redirect" can span
        # a line break in the source.
        import re
        from api.prompt_composer import LORI_ORAL_HISTORY_RESPONSE
        text = re.sub(r"\s+", " ", LORI_ORAL_HISTORY_RESPONSE.lower())
        for phrase in ("do not redirect", "do not verify", "do not steer"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


class StyleDispatchTest(unittest.TestCase):
    """The composer's style dispatch was added in this WO. When
    runtime71['session_style'] is missing/empty/unknown OR explicitly
    'oral_history', the LORI_ORAL_HISTORY_RESPONSE block injects.
    For any of the known non-oral styles, it does NOT inject.

    These tests inspect the dispatch source rather than running the
    full composer, which would require a heavy mock stack."""

    def test_known_non_oral_styles_set_is_complete(self):
        path = (
            _REPO_ROOT / "server" / "code" / "api" / "prompt_composer.py"
        )
        src = path.read_text(encoding="utf-8")
        # Extract the _KNOWN_NON_ORAL_STYLES literal
        import re
        m = re.search(
            r'_KNOWN_NON_ORAL_STYLES\s*=\s*\{([\s\S]+?)\}',
            src,
        )
        self.assertIsNotNone(m)
        items = set(re.findall(r'"([a-z_]+)"', m.group(1)))
        # The set must include every supported non-oral style; if a
        # new style gets added, this test surfaces it.
        expected_non_oral = {
            "warm_storytelling", "companion",
            "clear_direct", "questionnaire_first",
            "memory_exercise",
        }
        self.assertEqual(items, expected_non_oral)

    def test_injection_logs_verifiable_marker(self):
        # The acceptance-gate log line must be present in the source.
        path = (
            _REPO_ROOT / "server" / "code" / "api" / "prompt_composer.py"
        )
        src = path.read_text(encoding="utf-8")
        self.assertIn(
            "[composer] style=oral_history block=LORI_ORAL_HISTORY_RESPONSE",
            src,
        )


class SafetyPathsUnchangedTest(unittest.TestCase):
    """Acceptance gate #9: safety paths fire identically across styles.

    We can't easily run the safety classifier inline without the full
    LLM stack, but we can verify the safety entry points don't branch
    on session_style — which is the structural guarantee that safety
    behavior is style-independent."""

    def test_safety_module_does_not_branch_on_session_style(self):
        # Read the safety modules and confirm no `session_style`
        # references exist there. The safety routing layer must be
        # entirely style-agnostic.
        for fname in ("safety.py", "safety_classifier.py"):
            path = _SERVER_CODE / "api" / fname
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "session_style",
                src,
                msg=f"{fname} unexpectedly references session_style",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
