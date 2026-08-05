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

SCOPE (honest): static/AST contract PLUS a lightweight runtime contract —
it really constructs SafetyResult with the synthesis site's kwargs and really
calls scan_answer(). No DB, no network, no WebSocket. The runtime half is
gated on REAL pydantic and is never stubbed (a stubbed constructor test would
prove nothing). This does NOT prove end-to-end safety routing through the WS —
that is Track C1b.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))
_CHAT_WS = _REPO_ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
_SAFETY = _REPO_ROOT / "server" / "code" / "api" / "safety.py"


# The runtime half needs the REAL pydantic (safety.py builds SafetyResult on
# it). We deliberately do NOT stub it: a stubbed constructor contract proves
# nothing about the real constructor.
#
# TEST-ORDER HAZARD (found live 2026-07-13): ~20 test modules install a FAKE
# pydantic into sys.modules at import time and never remove it. In a shared
# process / discover run, whichever module lands first wins — so importing
# api.safety here can silently pick up the stub and the "runtime" contract
# becomes worthless (or errors). So we run the runtime checks in a CLEAN
# SUBPROCESS, which is immune to sys.modules pollution regardless of order.
import subprocess

try:  # pragma: no cover - env dependent
    import pydantic  # noqa: F401
    _HAVE_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAVE_PYDANTIC = False


def _run_in_clean_interpreter(body: str):
    """Run a snippet in a fresh interpreter with server/code importable, so no
    stubbed module from another test file can leak in."""
    code = ("import sys\n"
            "sys.path.insert(0, %r)\n" % str(_SERVER_CODE)) + body
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=60)


# ── WO-LEAN-LORI-RUNTIME-01 Phase 3B ──────────────────────────────────
# This suite tests the ACTIVE deterministic safety layer, which as of
# 2026-08-04 is not the default: `HORNELORE_SAFETY_STATE` defaults to
# "parked" and `safety.scan_answer()` returns None for every caller.
#
# Opting in explicitly, rather than relaxing the assertions, is the point
# of parking rather than deleting: reactivation must land on suites that
# still hold the feature to its original contract. Restored afterwards so
# the parked default is what every other module sees, and set on
# os.environ (not just locally) because parts of this suite run in a
# subprocess that inherits it.
_SAVED_SAFETY_STATE = None


def setUpModule():  # noqa: N802
    import os
    global _SAVED_SAFETY_STATE
    _SAVED_SAFETY_STATE = os.environ.get("HORNELORE_SAFETY_STATE")
    os.environ["HORNELORE_SAFETY_STATE"] = "active"


def tearDownModule():  # noqa: N802
    import os
    if _SAVED_SAFETY_STATE is None:
        os.environ.pop("HORNELORE_SAFETY_STATE", None)
    else:
        os.environ["HORNELORE_SAFETY_STATE"] = _SAVED_SAFETY_STATE


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


@unittest.skipUnless(
    _HAVE_PYDANTIC,
    "pydantic not installed — the runtime safety contract is SKIPPED here. "
    "It MUST pass in the real venv (.venv-gpu); a stub would prove nothing.")
class SafetyResultConstructorContractTest(unittest.TestCase):
    """RUNTIME half of the guard (ChatGPT review 2026-07-13).

    The import contract above proves `SafetyResult` is imported. It does NOT
    prove chat_ws can actually CONSTRUCT it. The synthesis site calls
    `SafetyResult(triggered=..., category=..., confidence=...)`; if safety.py
    ever renames a field, the import check still passes and the call blows up
    at runtime — straight back into the swallowing `except Exception`.

    So: really build one, with the exact kwargs the synthesis site uses, and
    assert the LLM->pattern category map targets are real categories.
    """

    def test_safety_result_constructs_with_the_kwargs_chat_ws_uses(self):
        p = _run_in_clean_interpreter(
            "from api.safety import SafetyResult\n"
            "r = SafetyResult(triggered=True,"
            " category='suicidal_ideation_indirect', confidence=0.81)\n"
            "assert r.triggered and r.category == 'suicidal_ideation_indirect'\n"
            "assert abs(r.confidence - 0.81) < 1e-6\n"
            "print('OK')\n")
        self.assertIn("OK", p.stdout,
                      "chat_ws's SafetyResult(...) call no longer constructs: "
                      + (p.stderr or "")[-400:])

    def test_llm_category_map_targets_are_real_categories(self):
        # chat_ws maps LLM categories -> pattern-side categories. A typo here
        # routes a real ideation catch into a category nothing downstream
        # handles, which looks identical to "safety never fired".
        src = _CHAT_WS.read_text(encoding="utf-8")
        for mapped in ("suicidal_ideation", "suicidal_ideation_indirect",
                       "cognitive_distress"):
            self.assertIn('"%s"' % mapped, src,
                          "chat_ws no longer maps the LLM classifier onto "
                          "%s — an indirect-ideation catch would route "
                          "nowhere" % mapped)

    def test_scan_answer_is_callable_and_returns_a_safety_result(self):
        # Cheapest possible proof the deterministic layer is actually alive.
        p = _run_in_clean_interpreter(
            "from api.safety import scan_answer, SafetyResult\n"
            "out = scan_answer('I want to kill myself')\n"
            "assert isinstance(out, SafetyResult), 'not a SafetyResult'\n"
            "assert out.triggered, 'pattern layer did not fire on acute phrase'\n"
            "assert out.category == 'suicidal_ideation', out.category\n"
            "print('OK')\n")
        self.assertIn("OK", p.stdout,
                      "the deterministic safety layer no longer fires on an "
                      "explicit acute phrase: " + (p.stderr or "")[-400:])

    def test_benign_turn_does_not_trigger(self):
        # Contract: scan_answer returns the highest-confidence TRIGGERED
        # result, or None. chat_ws relies on the falsy-None path
        # (`if _safety_result:`) to mean "no safety on this turn".
        p = _run_in_clean_interpreter(
            "from api.safety import scan_answer\n"
            "assert scan_answer('We had lunch in Munich.') is None\n"
            "print('OK')\n")
        self.assertIn("OK", p.stdout, (p.stderr or "")[-400:])


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
