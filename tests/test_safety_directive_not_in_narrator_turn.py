"""BUG-SAFETY-DIRECTIVE-CONCATENATED-INTO-NARRATOR-TURN-01.

LIVE (2026-07-14). The UI appended its posture directive onto the narrator's
own message before sending it. The turn archived for a narrator IN CRISIS was:

  "I don't want to be here anymore. There's no point to any of it.
   [SAFETY MODE: ACTIVE — ... Do NOT say 'I cannot continue' ...
    Do NOT reset to interview mode.]"

Every consequence of that was observed live:
  * the narrator's most vulnerable sentence is permanently contaminated with
    machine instructions in the memoir source;
  * the extractor and story-trigger read the directive as narrator speech;
  * the follow-up bank mined "Do NOT" as an ANCHOR, and Lori recited it back
    to them: "From what you just shared, I heard about Do NOT.";
  * safety mode is STICKY, so the following turn was polluted too.

A directive is not something the narrator said. It travels BESIDE the message,
never inside it — and it lands in the system prompt, where it always belonged.

The safety behaviour itself must NOT be weakened by this fix: silently dropping
the directive would be far worse than the leak. Hence the composer test.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

_HTML_RAW = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")

def _strip_js_line_comments(src: str) -> str:
    """Scan CODE, not commentary.

    The fix's own comment quotes the offending line verbatim as the historical
    record — which is exactly what we want a future reader to see, and exactly
    what must not trip the check. So compare against code with // lines removed.
    """
    out = []
    for line in src.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//"):
            continue
        out.append(line)
    return "\n".join(out)

_HTML = _strip_js_line_comments(_HTML_RAW)
_CHAT_WS = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
    encoding="utf-8")


class DirectiveNeverEntersTheNarratorTurnTest(unittest.TestCase):
    def test_ui_does_not_concatenate_the_directive_into_the_message(self):
        # The exact line that caused it.
        self.assertNotIn("parsed.message += _wsContextBlock", _HTML,
                         "the posture directive is being appended to the "
                         "narrator's own words again")

    def test_ui_sends_the_directive_beside_the_message(self):
        self.assertIn("parsed.params.ui_context_block", _HTML)

    def test_no_posture_block_is_appended_to_any_message(self):
        # Guard the whole family, not just safety: companion,
        # companion_override and memory_exercise_fact_seed used the same path.
        self.assertFalse(
            re.search(r"\.message\s*\+=", _HTML),
            "something is appending to the narrator's message again")

    def test_server_routes_the_block_to_the_system_prompt(self):
        self.assertIn('params.get("ui_context_block")', _CHAT_WS)
        self.assertIn("ui_system=_ui_system_for_prompt", _CHAT_WS)

    def test_server_caps_the_untrusted_block(self):
        # A directive channel, not an open prompt-injection surface.
        self.assertIn("[:1200]", _CHAT_WS)


class SafetyBehaviourStillWorksTest(unittest.TestCase):
    """Dropping the directive would be WORSE than the leak. Prove it lands."""

    def test_safety_directive_reaches_the_system_prompt(self):
        from api.prompt_composer import compose_system_prompt
        out = compose_system_prompt(
            "t",
            ui_system="[SAFETY MODE: ACTIVE — This conversation involves an "
                      "acute life-threatening emergency. Give the resource or "
                      "911 directly.]",
            user_text="I don't want to be here anymore.")
        self.assertIn("SAFETY MODE: ACTIVE", out)

    def test_composer_tolerates_no_block(self):
        from api.prompt_composer import compose_system_prompt
        out = compose_system_prompt("t", ui_system=None, user_text="hello")
        self.assertTrue(out.strip())


if __name__ == "__main__":
    unittest.main()
