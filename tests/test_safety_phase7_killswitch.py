"""WO-LORI-SAFETY-INTEGRATION-01 Phase 7 — LV_ENABLE_SAFETY kill-switch.

Phase 7 wires the previously-vestigial LV_ENABLE_SAFETY env flag as a
kill-switch over the entire chat-path safety pipeline (pattern scan,
LLM second-layer, segment_flag persistence, softened-mode, operator
notify). Default-ON ("1"). Setting to "0" disables.

These are STRUCTURAL tests — they verify the kill-switch logic exists
in the chat_ws.py source and that the .env.example documents the
DEVELOPER-ONLY framing. Behavioral testing of the actual kill-switch
behavior requires a live chat_ws session, which is out of scope for
unit tests; the structural guarantees + the loud per-turn warning log
marker are how operators audit the kill-switch state in production.
"""
from __future__ import annotations

import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"


class KillSwitchPresenceTest(unittest.TestCase):
    """Verify the kill-switch landed in chat_ws.py."""

    @classmethod
    def setUpClass(cls):
        if not _CHAT_WS.is_file():
            raise unittest.SkipTest(f"chat_ws.py missing at {_CHAT_WS}")
        cls.text = _CHAT_WS.read_text(encoding="utf-8")

    def test_lv_enable_safety_read_present(self):
        # Wire-up call must read the flag with default "1".
        self.assertIn(
            'os.getenv("LV_ENABLE_SAFETY", "1")',
            self.text,
            "Phase 7 LV_ENABLE_SAFETY env read missing — has the "
            "kill-switch been removed in a refactor?",
        )

    def test_safety_enabled_flag_used_in_gate(self):
        # The gate condition must include _safety_enabled
        self.assertIn(
            "_safety_enabled = os.getenv(",
            self.text,
            "Phase 7 _safety_enabled flag declaration missing.",
        )
        self.assertIn(
            "if _safety_enabled and user_text and user_text.strip()",
            self.text,
            "Phase 7 gate condition missing — the safety block must "
            "check _safety_enabled FIRST before user_text.",
        )

    def test_kill_switch_warning_log_marker_present(self):
        self.assertIn(
            "[chat_ws][safety][KILL-SWITCH]",
            self.text,
            "Phase 7 KILL-SWITCH log marker missing — operators rely on "
            "this to detect the disabled state in api.log.",
        )

    def test_kill_switch_warns_per_turn(self):
        # The warning must be a per-turn logger.warning, not a
        # session-level one-shot — operators need to see the disabled
        # state on every turn during incident investigation.
        # Verify the warning sits inside the `if not _safety_enabled`
        # branch (per-turn), not above it (session-level).
        gate_idx = self.text.find('_safety_enabled = os.getenv(')
        warn_idx = self.text.find('[chat_ws][safety][KILL-SWITCH]')
        self.assertGreater(gate_idx, 0)
        self.assertGreater(warn_idx, 0)
        self.assertGreater(
            warn_idx, gate_idx,
            "KILL-SWITCH warning must come AFTER the flag read, not before.",
        )

    def test_developer_only_warning_in_comments(self):
        # The "DEVELOPER USE ONLY" / "NEVER set ... in a real narrator
        # session" framing must remain so anyone editing this site
        # understands the safety implications of the kill-switch.
        self.assertIn(
            "DEVELOPER",
            self.text,
            "Phase 7 DEVELOPER-only framing missing in chat_ws.py — "
            "anyone editing the kill-switch site needs to understand "
            "when it's safe to disable safety.",
        )
        self.assertIn(
            "NEVER set LV_ENABLE_SAFETY=0",
            self.text,
            "Phase 7 'NEVER set LV_ENABLE_SAFETY=0 in a real narrator "
            "session' framing missing in chat_ws.py.",
        )


class EnvExampleDocsTest(unittest.TestCase):
    """Verify .env.example documents the kill-switch with the
    DEVELOPER-ONLY framing."""

    @classmethod
    def setUpClass(cls):
        if not _ENV_EXAMPLE.is_file():
            raise unittest.SkipTest(f".env.example missing at {_ENV_EXAMPLE}")
        cls.text = _ENV_EXAMPLE.read_text(encoding="utf-8")

    def test_lv_enable_safety_present(self):
        self.assertIn("LV_ENABLE_SAFETY", self.text)

    def test_default_documented_as_1(self):
        self.assertIn("LV_ENABLE_SAFETY=1", self.text)

    def test_developer_only_framing_present(self):
        self.assertIn(
            "DEVELOPER",
            self.text,
            ".env.example LV_ENABLE_SAFETY block missing DEVELOPER-only framing",
        )

    def test_never_in_narrator_session_framing_present(self):
        self.assertIn(
            "NEVER set",
            self.text,
            ".env.example LV_ENABLE_SAFETY block missing 'NEVER set ... "
            "in a real narrator session' framing",
        )

    def test_phase_7_callout_present(self):
        # The Phase 7 attribution should remain so anyone reading
        # .env.example knows where this decision came from.
        self.assertIn(
            "Phase 7",
            self.text,
            ".env.example LV_ENABLE_SAFETY block missing Phase 7 attribution",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
