"""WO-LORI-SAFETY-INTEGRATION-01 Phase 5 — integration tests.

Phase 5 closes the loop so a safety event actually changes the rest of
the chat-path's behavior, not just Lori's words. Four sub-phases:

  5a — Discipline filter exemption: trim-to-one-question is SKIPPED on
       safety-routed turns (so 988+Friendship Line+warm acknowledgment
       isn't mis-clipped as a compound question)
  5b — WO-10C silence ladder yields to safety dispatch
       (PARKED on Phase 3 build)
  5c — Memory-echo filter excludes sensitive segment-flagged turns
       (PARKED on Phase 1b session-transcript read accessor; primitive
       helper landed: safety.filter_safety_flagged_turns)
  5d — family_truth pipeline isolation: notes carrying sensitive=True
       are REJECTED at the /api/family-truth/note endpoint with 403

These tests cover the in-this-phase work (5a structural, 5d structural,
5c primitive helper). 5b sits behind Phase 3 build.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
_FAMILY_TRUTH = _REPO_ROOT / "server" / "code" / "api" / "routers" / "family_truth.py"
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


# ── 5a — chat_ws safety-exempt structural test ────────────────────────────

class Phase5aDisciplineExemptionTest(unittest.TestCase):
    """The trim filter must SKIP on safety-routed turns. Verify the
    exempt block is present in chat_ws.py source."""

    @classmethod
    def setUpClass(cls):
        if not _CHAT_WS.is_file():
            raise unittest.SkipTest(f"chat_ws.py missing at {_CHAT_WS}")
        cls.text = _CHAT_WS.read_text(encoding="utf-8")

    def test_safety_exempt_block_present(self):
        self.assertIn(
            "[lori][discipline][safety-exempt]",
            self.text,
            "Phase 5a safety-exempt log marker missing — has the trim "
            "exemption been removed in a refactor?",
        )

    def test_is_safety_turn_check_present(self):
        self.assertIn(
            "_is_safety_turn",
            self.text,
            "Phase 5a _is_safety_turn flag missing.",
        )

    def test_skip_buffer_mode_when_safety(self):
        self.assertIn("_buffer_mode_for_trim = False", self.text)
        self.assertIn("if _buffer_mode_for_trim and final_text", self.text)

    def test_safety_exempt_appears_before_trim_call(self):
        exempt_idx = self.text.find("[lori][discipline][safety-exempt]")
        trim_idx = self.text.find("from ..prompt_composer import _trim_to_one_question")
        self.assertGreater(exempt_idx, 0, "exempt log marker not found")
        self.assertGreater(trim_idx, 0, "trim import not found")
        self.assertLess(
            exempt_idx, trim_idx,
            "Phase 5a exempt block must appear BEFORE the trim import "
            "site, otherwise the safety check happens after trim runs.",
        )


# ── 5d — family_truth.py sensitive-rejection structural test ──────────────

class Phase5dFamilyTruthRejectionTest(unittest.TestCase):
    """family_truth.py must reject sensitive=True notes with HTTP 403."""

    @classmethod
    def setUpClass(cls):
        if not _FAMILY_TRUTH.is_file():
            raise unittest.SkipTest(f"family_truth.py missing")
        cls.text = _FAMILY_TRUTH.read_text(encoding="utf-8")

    def test_sensitive_field_in_note_request(self):
        self.assertIn(
            "sensitive: bool = Field(default=False",
            self.text,
            "Phase 5d sensitive field missing from NoteAddRequest.",
        )

    def test_safety_reject_log_marker_present(self):
        self.assertIn(
            "[family_truth][safety-reject]",
            self.text,
            "Phase 5d safety-reject log marker missing.",
        )

    def test_403_raised_on_sensitive_note(self):
        self.assertIn(
            "status_code=403",
            self.text,
            "Phase 5d must raise HTTPException with 403 on sensitive=True.",
        )
        self.assertIn(
            "if req.sensitive:",
            self.text,
            "Phase 5d gate condition missing.",
        )

    def test_phase_5d_marker_in_comments(self):
        self.assertIn(
            "Phase 5d",
            self.text,
            "Phase 5d explanatory comment missing.",
        )


# ── 5c — Pure-function helper test (forward-looking) ──────────────────────

class Phase5cFilterHelperTest(unittest.TestCase):
    """safety.filter_safety_flagged_turns is a pure-function primitive
    that the eventual Phase 1b session-transcript read accessor will
    use. Test it standalone (no DB, no IO)."""

    def setUp(self):
        try:
            from api.safety import filter_safety_flagged_turns
            self.filter_fn = filter_safety_flagged_turns
        except Exception as exc:
            self.skipTest(f"safety.filter_safety_flagged_turns import failed: {exc}")

    def test_empty_input_returns_empty(self):
        self.assertEqual(self.filter_fn([]), [])
        self.assertEqual(self.filter_fn(None), [])

    def test_no_sensitive_turns_passes_all_through(self):
        turns = [
            {"id": "t1", "role": "user", "content": "I was born in 1937."},
            {"id": "t2", "role": "assistant", "content": "Tell me more."},
        ]
        self.assertEqual(self.filter_fn(turns), turns)

    def test_drops_sensitive_true_turn(self):
        turns = [
            {"id": "t1", "content": "normal"},
            {"id": "t2", "content": "distress", "sensitive": True},
            {"id": "t3", "content": "normal"},
        ]
        result = self.filter_fn(turns)
        self.assertEqual([t["id"] for t in result], ["t1", "t3"])

    def test_drops_segment_flag_sensitive_variant(self):
        turns = [
            {"id": "t1", "content": "normal"},
            {"id": "t2", "content": "distress", "segment_flag_sensitive": True},
        ]
        result = self.filter_fn(turns)
        self.assertEqual([t["id"] for t in result], ["t1"])

    def test_drops_safety_flagged_variant(self):
        turns = [
            {"id": "t1", "safety_flagged": True, "content": "x"},
            {"id": "t2", "content": "y"},
        ]
        result = self.filter_fn(turns)
        self.assertEqual([t["id"] for t in result], ["t2"])

    def test_drops_nested_segment_flag_dict_variant(self):
        turns = [
            {"id": "t1", "segment_flag": {"sensitive": True}, "content": "x"},
            {"id": "t2", "segment_flag": {"sensitive": False}, "content": "y"},
            {"id": "t3", "content": "z"},
        ]
        result = self.filter_fn(turns)
        self.assertEqual([t["id"] for t in result], ["t2", "t3"])

    def test_non_dict_items_pass_through_defensive(self):
        turns = ["raw string metadata", 42, {"id": "real_turn", "content": "x"}]
        result = self.filter_fn(turns)
        self.assertEqual(len(result), 3)

    def test_pure_function_no_side_effects(self):
        turns = [
            {"id": "t1", "sensitive": True},
            {"id": "t2"},
        ]
        a = self.filter_fn(turns)
        b = self.filter_fn(turns)
        self.assertEqual(a, b)
        self.assertEqual(len(turns), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
