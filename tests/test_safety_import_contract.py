"""TRACK-A2 — the SafetyResult silent-no-op regression guard.

THE BUG THIS LOCKS (2026-07-11 repo review, HIGH):
`chat_ws.py` used `SafetyResult` without importing it. The resulting NameError
was swallowed by the broad `except Exception` wrapping the safety block, so
WO-LORI-SAFETY-INTEGRATION-01 Phase 2 **silently no-op'd on every indirect-
ideation catch**. Safety events never routed. No test caught it; a human
reading the code did.

For a system whose narrators are older adults, a safety layer that can fail
INVISIBLY is worse than one that fails loudly. These tests make that class of
failure test-visible:

  1. every name chat_ws imports from `safety` must actually exist in safety.py
  2. every safety symbol chat_ws *uses* must actually be imported
     (this is the exact SafetyResult bug)
  3. the safety block must keep its default-safe fallback: if the scan raises,
     the turn is forced onto the LLM/interview path rather than silently
     skipping safety.

Static/AST only — no server, no DB, no network.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
_SAFETY = _REPO_ROOT / "server" / "code" / "api" / "safety.py"


def _tree(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _safety_public_names() -> set:
    """Top-level public names defined by safety.py."""
    names = set()
    for node in _tree(_SAFETY).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
    return {n for n in names if not n.startswith("_")}


def _imported_from_safety() -> set:
    """Names chat_ws.py imports from the safety module."""
    out = set()
    for node in ast.walk(_tree(_CHAT_WS)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                "safety") and "safety_classifier" not in (node.module or ""):
            for a in node.names:
                out.add(a.asname or a.name)
    return out


def _names_used(tree: ast.Module) -> set:
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


class SafetyImportContractTest(unittest.TestCase):
    def test_safety_module_still_exports_the_expected_symbols(self):
        # If safety.py renames one of these, chat_ws breaks at runtime.
        for required in ("scan_answer", "build_segment_flags",
                         "get_resources_for_category", "set_softened",
                         "SafetyResult"):
            self.assertIn(required, _safety_public_names(),
                          "safety.py no longer exports %s" % required)

    def test_every_name_chat_ws_imports_from_safety_exists(self):
        missing = _imported_from_safety() - _safety_public_names()
        self.assertFalse(
            missing,
            "chat_ws imports names that do not exist in safety.py: %s"
            % sorted(missing))

    def test_every_safety_symbol_chat_ws_uses_is_imported(self):
        # THE REGRESSION: SafetyResult was USED but never IMPORTED, and the
        # NameError was swallowed by the wrapping `except Exception`.
        used = _names_used(_tree(_CHAT_WS))
        imported = _imported_from_safety()
        used_from_safety = used & _safety_public_names()
        not_imported = used_from_safety - imported
        self.assertFalse(
            not_imported,
            "chat_ws USES safety symbol(s) it never imports — this silently "
            "no-ops the safety layer via the broad `except Exception`: %s"
            % sorted(not_imported))

    def test_safety_result_specifically_is_imported(self):
        # Named explicitly so the failure message points at the real history.
        self.assertIn(
            "SafetyResult", _imported_from_safety(),
            "SafetyResult is not imported in chat_ws — this is the exact "
            "2026-07-11 HIGH bug: SAFETY-INTEGRATION-01 Phase 2 silently "
            "no-op'd on every indirect-ideation catch.")


class SafetyDefaultSafeFallbackTest(unittest.TestCase):
    """If the deterministic scan raises, the turn must NOT quietly skip
    safety — it is forced onto the LLM/interview path (which carries the
    ACUTE SAFETY RULE) and logged for the operator."""

    def setUp(self):
        self.src = _CHAT_WS.read_text(encoding="utf-8")

    def test_scan_failure_sets_a_default_safe_flag(self):
        self.assertIn("_safety_scan_failed", self.src,
                      "the scan_answer failure path no longer sets a "
                      "default-safe flag — a safety scan crash would "
                      "silently skip safety")

    def test_scan_failure_is_operator_visible(self):
        self.assertIn("default-safe", self.src,
                      "the default-safe fallback no longer emits an operator "
                      "log marker — a silent safety failure would be invisible")

    def test_scan_failure_forces_the_llm_path(self):
        # memory_echo / correction composers skip the LLM entirely, so a
        # failed scan must force turn_mode back to the interview path.
        self.assertRegex(
            self.src,
            r"_safety_scan_failed[\s\S]{0,400}turn_mode\"?\]?\s*=\s*\"interview\"",
            "a failed safety scan no longer forces turn_mode=interview; a "
            "distress turn could be answered by a composer that never sees "
            "the ACUTE SAFETY RULE")


if __name__ == "__main__":
    unittest.main()
