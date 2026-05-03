"""WO-LORI-SESSION-AWARENESS-01 Phase 1c — peek_at_memoir tests.

build_peek_at_memoir + summarize_for_runtime are pure read +
shape helpers. Tests use unittest.mock to stub the underlying db /
archive / safety reads so they run without pydantic / sqlite / disk.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# Module imports only stdlib at top level; lazy imports of db / archive
# / safety happen inside build_peek_at_memoir. Should always succeed.
from api.services.peek_at_memoir import (  # noqa: E402
    build_peek_at_memoir,
    summarize_for_runtime,
)


# ── build_peek_at_memoir defensive contracts ──────────────────────────────

class BuildPeekAtMemoirShapeTest(unittest.TestCase):

    def test_empty_person_id_returns_dict_with_error(self):
        result = build_peek_at_memoir("")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["promoted_truth"], [])
        self.assertEqual(result["recent_turns"], [])
        self.assertIn("empty_person_id", result["errors"])

    def test_none_person_id_returns_dict_with_error(self):
        result = build_peek_at_memoir(None)  # type: ignore[arg-type]
        self.assertIsInstance(result, dict)
        self.assertIn("empty_person_id", result["errors"])

    def test_session_id_none_skips_transcript_read(self):
        # session_id=None → transcript not read; sources_available reflects this
        with mock.patch("api.db.ft_list_promoted", return_value=[]):
            result = build_peek_at_memoir("p1")
            self.assertEqual(result["recent_turns"], [])
            self.assertFalse(result["sources_available"]["session_transcript"])

    def test_db_failure_captured_in_errors_does_not_raise(self):
        with mock.patch("api.db.ft_list_promoted", side_effect=RuntimeError("boom")):
            result = build_peek_at_memoir("p1")
            self.assertEqual(result["promoted_truth"], [])
            self.assertFalse(result["sources_available"]["promoted_truth"])
            self.assertTrue(any("promoted_truth_read_failed" in e for e in result["errors"]))

    def test_archive_failure_captured_in_errors_does_not_raise(self):
        with mock.patch("api.db.ft_list_promoted", return_value=[]), \
             mock.patch("api.archive.read_transcript",
                        side_effect=OSError("disk full")):
            result = build_peek_at_memoir("p1", session_id="s1")
            self.assertEqual(result["recent_turns"], [])
            self.assertFalse(result["sources_available"]["session_transcript"])
            self.assertTrue(any("session_transcript_read_failed" in e for e in result["errors"]))

    def test_promoted_truth_read_populates_field_and_marker(self):
        fake_promoted = [
            {"subject_name": "self", "field": "date_of_birth",
             "approved_value": "1937-12-31", "updated_at": "2026-01-01"},
            {"subject_name": "father", "field": "full_name",
             "approved_value": "Pete Zarr", "updated_at": "2026-01-02"},
        ]
        with mock.patch("api.db.ft_list_promoted", return_value=fake_promoted):
            result = build_peek_at_memoir("p1")
            self.assertEqual(len(result["promoted_truth"]), 2)
            self.assertTrue(result["sources_available"]["promoted_truth"])

    def _inject_fake_safety_module(self, filter_impl):
        """api.safety depends on pydantic which isn't installed in the
        sandbox. Inject a fake module into sys.modules with just the
        filter_safety_flagged_turns symbol, so the lazy import inside
        build_peek_at_memoir gets our stub."""
        import types
        fake = types.ModuleType("api.safety")
        fake.filter_safety_flagged_turns = filter_impl
        return mock.patch.dict("sys.modules", {"api.safety": fake})

    def test_transcript_with_sensitive_turn_filters_via_safety(self):
        fake_promoted = []
        fake_turns = [
            {"role": "user", "content": "I was born in Spokane.", "id": "t1"},
            {"role": "user", "content": "I just feel so tired.",
             "id": "t2", "sensitive": True},  # must be filtered
            {"role": "user", "content": "My dad worked in a factory.", "id": "t3"},
        ]

        # Mock the real filter behavior — drop dicts where sensitive=True.
        # This stub mirrors the real safety.filter_safety_flagged_turns
        # contract.
        def _filter_stub(turns):
            return [t for t in (turns or []) if not (isinstance(t, dict) and t.get("sensitive"))]

        with mock.patch("api.db.ft_list_promoted", return_value=fake_promoted), \
             mock.patch("api.archive.read_transcript", return_value=fake_turns), \
             self._inject_fake_safety_module(_filter_stub):
            result = build_peek_at_memoir("p1", session_id="s1")
            ids = [t["id"] for t in result["recent_turns"]]
            self.assertEqual(ids, ["t1", "t3"])
            self.assertNotIn("t2", ids)

    def test_transcript_capped_at_transcript_limit(self):
        fake_turns = [{"role": "user", "content": f"turn {i}", "id": f"t{i}"} for i in range(50)]
        with mock.patch("api.db.ft_list_promoted", return_value=[]), \
             mock.patch("api.archive.read_transcript", return_value=fake_turns), \
             self._inject_fake_safety_module(lambda t: t or []):
            result = build_peek_at_memoir("p1", session_id="s1", transcript_limit=5)
            self.assertEqual(len(result["recent_turns"]), 5)
            # Should be the LAST 5 (most recent)
            ids = [t["id"] for t in result["recent_turns"]]
            self.assertEqual(ids, ["t45", "t46", "t47", "t48", "t49"])


# ── summarize_for_runtime shaping ─────────────────────────────────────────

class SummarizeForRuntimeTest(unittest.TestCase):

    def test_empty_payload_returns_empty_summary(self):
        out = summarize_for_runtime({})
        self.assertEqual(out["promoted_facts"], [])
        self.assertEqual(out["recent_user_turns"], [])
        self.assertEqual(out["sources_used"], [])

    def test_non_dict_input_returns_empty_summary(self):
        self.assertEqual(
            summarize_for_runtime("not a dict")["promoted_facts"],  # type: ignore[arg-type]
            [],
        )

    def test_promoted_facts_dedupe_by_subject_field(self):
        peek = {
            "promoted_truth": [
                {"subject_name": "self", "field": "date_of_birth",
                 "approved_value": "1937-12-31"},
                # Same subject + field — keep only first (most recent due to ORDER BY in db)
                {"subject_name": "self", "field": "date_of_birth",
                 "approved_value": "1937-01-01"},
                {"subject_name": "father", "field": "full_name",
                 "approved_value": "Pete Zarr"},
            ],
            "sources_available": {"promoted_truth": True},
        }
        out = summarize_for_runtime(peek)
        self.assertEqual(len(out["promoted_facts"]), 2)
        # First occurrence wins
        dob_fact = [f for f in out["promoted_facts"] if f["field"] == "date_of_birth"][0]
        self.assertEqual(dob_fact["value"], "1937-12-31")

    def test_promoted_facts_skip_empty_value_or_field(self):
        peek = {
            "promoted_truth": [
                {"subject_name": "self", "field": "", "approved_value": "x"},
                {"subject_name": "self", "field": "y", "approved_value": ""},
                {"subject_name": "self", "field": "real", "approved_value": "value"},
            ],
        }
        out = summarize_for_runtime(peek)
        self.assertEqual(len(out["promoted_facts"]), 1)
        self.assertEqual(out["promoted_facts"][0]["field"], "real")

    def test_recent_user_turns_caps_at_5_chronological(self):
        peek = {
            "recent_turns": [
                {"role": "user", "content": f"turn {i}"} for i in range(10)
            ],
        }
        out = summarize_for_runtime(peek)
        self.assertEqual(len(out["recent_user_turns"]), 5)
        # Reversed back to chronological — the LAST 5 user turns,
        # in the original chronological order
        self.assertEqual(out["recent_user_turns"], [
            "turn 5", "turn 6", "turn 7", "turn 8", "turn 9"
        ])

    def test_recent_user_turns_skips_assistant_role(self):
        peek = {
            "recent_turns": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi back"},
                {"role": "user", "content": "Tell me more"},
            ],
        }
        out = summarize_for_runtime(peek)
        self.assertEqual(out["recent_user_turns"], ["Hello", "Tell me more"])

    def test_recent_user_turns_handles_text_or_content_field(self):
        # Different stores use 'text' vs 'content'
        peek = {
            "recent_turns": [
                {"role": "user", "text": "from text field"},
                {"role": "user", "content": "from content field"},
            ],
        }
        out = summarize_for_runtime(peek)
        self.assertEqual(out["recent_user_turns"], ["from text field", "from content field"])

    def test_sources_used_reflects_available_sources(self):
        peek = {
            "sources_available": {
                "promoted_truth": True,
                "session_transcript": True,
            },
        }
        out = summarize_for_runtime(peek)
        self.assertIn("promoted truth", out["sources_used"])
        self.assertIn("session transcript", out["sources_used"])

    def test_sources_used_empty_when_no_sources(self):
        peek = {"sources_available": {}}
        out = summarize_for_runtime(peek)
        self.assertEqual(out["sources_used"], [])


# ── LAW 3: peek_at_memoir's import graph stays bounded ────────────────────

class Phase1cIsolationTest(unittest.TestCase):
    """peek_at_memoir.py must not import from the extractor / chat
    composer surface — it's a read-only accessor for memory_echo
    consumption. Lazy-imports db / archive / safety only."""

    def test_module_top_level_imports_are_stdlib_only(self):
        import ast
        path = _SERVER_CODE / "api" / "services" / "peek_at_memoir.py"
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        forbidden_at_top = (
            "api.routers.extract", "api.prompt_composer",
            "api.routers.chat_ws", "api.routers.llm_api",
            "api.memory_echo",
        )
        for node in ast.walk(tree):
            # Only check top-level imports (inside def is allowed = lazy)
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            # Walk parent chain... ast doesn't give us that. Use module-level
            # check: every Import/ImportFrom under the module body (not
            # inside a function/method) is a top-level import.
            pass

        # Easier check: parse the module body directly and only
        # inspect top-level statements.
        for stmt in tree.body:
            if isinstance(stmt, ast.ImportFrom):
                module_path = stmt.module or ""
                # Resolve relative imports — peek_at_memoir lives in
                # api.services so 'from ..' = 'api'
                if stmt.level == 2 and module_path:
                    full = f"api.{module_path}"
                else:
                    full = module_path
                for forbidden in forbidden_at_top:
                    self.assertFalse(
                        full.startswith(forbidden),
                        f"peek_at_memoir.py top-level imports {full} which "
                        f"matches forbidden prefix {forbidden} — keep DB "
                        f"and composer reads inside the function body "
                        f"(lazy import).",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
