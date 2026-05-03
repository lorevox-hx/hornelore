"""WO-LORI-SESSION-AWARENESS-01 Phase 1c-wire — composer + chat_ws wire tests.

Phase 1c-wire threads peek_at_memoir output into runtime71 (chat_ws side)
and renders promoted_facts in compose_memory_echo's new "From our records"
section. Default-off behind HORNELORE_PEEK_AT_MEMOIR_LIVE.

Tests:
  - compose_memory_echo behavior with peek_data present (renders section)
  - compose_memory_echo behavior with peek_data absent (skips section,
    byte-stable with pre-wire behavior)
  - chat_ws structural: the wire block is present and gated on the flag
  - .env.example documents the flag with the right framing
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_CHAT_WS = _SERVER_CODE / "api" / "routers" / "chat_ws.py"
_PROMPT_COMPOSER = _SERVER_CODE / "api" / "prompt_composer.py"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"

if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


# ── compose_memory_echo behavioral tests ──────────────────────────────────

class ComposerPromotedFactsRenderTest(unittest.TestCase):
    """When runtime carries peek_data.promoted_facts, the composer
    renders a 'From our records' section."""

    def setUp(self):
        try:
            from api.prompt_composer import compose_memory_echo
            self.compose = compose_memory_echo
        except Exception as exc:
            self.skipTest(f"prompt_composer import failed: {exc}")

    def test_no_peek_data_no_section(self):
        # Pre-wire behavior: no peek_data key in runtime → no
        # "From our records" section
        runtime = {"speaker_name": "Janice"}
        out = self.compose(text="what do you know about me?", runtime=runtime)
        self.assertNotIn("From our records", out)

    def test_empty_peek_data_no_section(self):
        runtime = {
            "speaker_name": "Janice",
            "peek_data": {"promoted_facts": [], "sources_used": []},
        }
        out = self.compose(text="x", runtime=runtime)
        self.assertNotIn("From our records", out)

    def test_promoted_facts_render_with_speaker_name(self):
        runtime = {
            "speaker_name": "Janice",
            "peek_data": {
                "promoted_facts": [
                    {"subject": "self", "field": "date_of_birth", "value": "1937-12-31"},
                    {"subject": "self", "field": "place_of_birth", "value": "Spokane, WA"},
                ],
                "sources_used": ["promoted truth"],
            },
        }
        out = self.compose(text="x", runtime=runtime)
        self.assertIn("From our records", out)
        self.assertIn("Janice's date of birth: 1937-12-31", out)
        self.assertIn("Janice's place of birth: Spokane, WA", out)

    def test_promoted_facts_other_subject_renders_capitalized(self):
        runtime = {
            "speaker_name": "Janice",
            "peek_data": {
                "promoted_facts": [
                    {"subject": "father", "field": "full_name", "value": "Pete Zarr"},
                    {"subject": "mother", "field": "occupation", "value": "homemaker"},
                ],
                "sources_used": ["promoted truth"],
            },
        }
        out = self.compose(text="x", runtime=runtime)
        self.assertIn("Father's name: Pete Zarr", out)
        self.assertIn("Mother's occupation: homemaker", out)

    def test_promoted_facts_skip_empty_field_or_value(self):
        runtime = {
            "speaker_name": "Janice",
            "peek_data": {
                "promoted_facts": [
                    {"subject": "self", "field": "", "value": "something"},
                    {"subject": "self", "field": "x", "value": ""},
                    {"subject": "self", "field": "real", "value": "kept"},
                ],
                "sources_used": [],
            },
        }
        out = self.compose(text="x", runtime=runtime)
        self.assertIn("From our records", out)
        self.assertIn("real: kept", out)
        # Empty-field one and empty-value one should NOT appear
        self.assertNotIn("'s : something", out)

    def test_promoted_facts_speaker_name_fallback_to_your(self):
        # No speaker_name → use "Your" possessive
        runtime = {
            "peek_data": {
                "promoted_facts": [
                    {"subject": "self", "field": "date_of_birth", "value": "1937-12-31"},
                ],
                "sources_used": [],
            },
        }
        out = self.compose(text="x", runtime=runtime)
        self.assertIn("Your date of birth: 1937-12-31", out)

    def test_promoted_facts_adds_promoted_truth_to_sources(self):
        runtime = {
            "speaker_name": "Janice",
            "dob": "1937-12-31",  # triggers profile source
            "peek_data": {
                "promoted_facts": [
                    {"subject": "father", "field": "full_name", "value": "Pete"},
                ],
                "sources_used": ["promoted truth"],
            },
        }
        out = self.compose(text="x", runtime=runtime)
        # Sources footer must mention "promoted truth"
        self.assertIn("promoted truth", out)

    def test_field_name_humanization(self):
        runtime = {
            "speaker_name": "Janice",
            "peek_data": {
                "promoted_facts": [
                    # Snake_case fields not in the label map should
                    # render with underscores replaced by spaces
                    {"subject": "self", "field": "favorite_color", "value": "blue"},
                ],
                "sources_used": [],
            },
        }
        out = self.compose(text="x", runtime=runtime)
        self.assertIn("Janice's favorite color: blue", out)


# ── chat_ws structural test for the wire block ────────────────────────────

class ChatWsWireBlockPresenceTest(unittest.TestCase):
    """The wire block in chat_ws.py must be present, gated on
    HORNELORE_PEEK_AT_MEMOIR_LIVE, and lazy-import peek_at_memoir."""

    @classmethod
    def setUpClass(cls):
        if not _CHAT_WS.is_file():
            raise unittest.SkipTest(f"chat_ws.py missing")
        cls.text = _CHAT_WS.read_text(encoding="utf-8")

    def test_peek_flag_read_present(self):
        self.assertIn(
            'os.getenv("HORNELORE_PEEK_AT_MEMOIR_LIVE", "0")',
            self.text,
            "Phase 1c-wire flag read missing in chat_ws.py.",
        )

    def test_peek_block_uses_lazy_import(self):
        # Lazy import keeps default-off path light
        self.assertIn(
            "from ..services.peek_at_memoir import",
            self.text,
            "Phase 1c-wire must lazy-import peek_at_memoir inside the gate.",
        )

    def test_peek_log_marker_present(self):
        self.assertIn(
            "[chat_ws][memory-echo][peek]",
            self.text,
            "Phase 1c-wire log marker missing.",
        )

    def test_peek_block_gated_by_person_id(self):
        # Without person_id we have no narrator to query for, so the
        # block must include a person_id check
        self.assertIn(
            "if (\n                person_id\n                and os.getenv(",
            self.text,
            "Phase 1c-wire gate must include person_id check (the "
            "accessor needs a narrator to query).",
        )

    def test_peek_failure_swallowed(self):
        # Build failure must not break the turn — log warning + continue
        self.assertIn(
            "[chat_ws][memory-echo][peek] build failed",
            self.text,
            "Phase 1c-wire failure-handler missing.",
        )


# ── .env.example documentation test ────────────────────────────────────────

class EnvExampleWireDocTest(unittest.TestCase):
    """The flag must be documented in .env.example with the right framing."""

    @classmethod
    def setUpClass(cls):
        if not _ENV_EXAMPLE.is_file():
            raise unittest.SkipTest(".env.example missing")
        cls.text = _ENV_EXAMPLE.read_text(encoding="utf-8")

    def test_flag_present(self):
        self.assertIn("HORNELORE_PEEK_AT_MEMOIR_LIVE=0", self.text)

    def test_default_off_framing(self):
        self.assertIn("Default-OFF", self.text)

    def test_safety_filter_callout_present(self):
        # The Phase 5c safety filter integration is load-bearing —
        # documentation must call it out so anyone flipping the flag
        # knows distress content is safety-filtered automatically
        self.assertIn(
            "safety.filter_safety_flagged_turns",
            self.text,
            ".env.example must document the Phase 5c safety filter "
            "integration so anyone flipping the flag understands "
            "distress turns can never surface in memory_echo.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
