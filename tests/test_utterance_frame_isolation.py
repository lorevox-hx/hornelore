"""WO-EX-UTTERANCE-FRAME-01 Phase 0-2 — module isolation gate.

═══════════════════════════════════════════════════════════════════════
  LAW: utterance_frame.py is pure deterministic. No LLM. No DB. No IO.
       No NLP framework. No extractor. No Lori. No prompt composer.
       No safety. No memory echo. No chat_ws.

  This test enforces the rule MECHANICALLY. It parses the AST of
  `services/utterance_frame.py`, follows imports transitively, and
  fails the build if any reachable module is in the forbidden subgraph.

  Why mechanical, not aspirational:
    - The frame is the SHARED REPRESENTATION layer between Lori,
      extractor, validator, and safety. If it ever imports any of
      them, it becomes coupled to one consumer's lifecycle.
    - The frame must be safe to call from a chat-turn hot path, a
      CLI debug runner, a test fixture loop, AND eventually a Lori
      reflection check — without bringing the rest of the world
      with it.
    - Code review can miss imports. Refactors split modules and
      sometimes accidentally re-couple paths. This test is the only
      thing that can't forget.

  See WO-EX-UTTERANCE-FRAME-01_Spec.md "Locked design rules"
  rule #7 (NO FRAMEWORK DEPENDENCY) and the LAW preamble of
  utterance_frame.py.
═══════════════════════════════════════════════════════════════════════

Negative-test verification (run during Phase 0-2 development):
    1. Add `from ..routers import extract` to
       server/code/api/services/utterance_frame.py
    2. Run this test → must FAIL with a clear message naming
       `routers.extract` as the forbidden import.
    3. Remove the import.
    4. Run this test → must PASS.

Both states are required. A test that passes in both is broken.

WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6: the copy-pasted
walker + import collector now live in tests/source_scan_helpers.py
(unit-tested in tests/test_source_scan_helpers.py). Semantics unchanged:
ALL imports (module- and function-level) followed, depth-bounded at 4,
same forbidden prefixes and overrides, same failure messages.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import List, Tuple

try:
    from tests import source_scan_helpers as ssh
except ImportError:  # direct execution: python tests/test_utterance_frame_isolation.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as ssh


# ── Configuration ─────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "utterance_frame.py"

# The forbidden subgraph. Any module whose dotted name starts with one of
# these prefixes is part of the extractor / Lori / safety / UI / chat
# stack and must NOT be reachable from utterance_frame.py.
#
# Only `services.lori_reflection` is allowed (for _AFFECT_TOKENS_RX
# reuse). It's a sibling pure-function module, not a forbidden surface.
_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    # Extractor stack
    "api.routers.extract",
    "code.api.routers.extract",
    "server.code.api.routers.extract",
    # Prompt composer + memory echo (Lori's prompt-side runtime)
    "api.prompt_composer",
    "code.api.prompt_composer",
    "server.code.api.prompt_composer",
    "api.memory_echo",
    "code.api.memory_echo",
    "server.code.api.memory_echo",
    # LLM API + WS — chat hot path
    "api.routers.llm_api",
    "code.api.routers.llm_api",
    "server.code.api.routers.llm_api",
    "api.routers.chat_ws",
    "code.api.routers.chat_ws",
    "server.code.api.routers.chat_ws",
    # Family-truth pipeline
    "api.routers.family_truth",
    "code.api.routers.family_truth",
    "server.code.api.routers.family_truth",
    # Safety surface
    "api.safety",
    "code.api.safety",
    "server.code.api.safety",
    # DB — frame is pure; reads/writes are downstream consumers' job
    "api.db",
    "code.api.db",
    "server.code.api.db",
    # Story preservation — sibling pure-function lane, but coupling
    # would defeat the LAW 3 isolation that lane already enforces.
    "api.services.story_preservation",
    "code.api.services.story_preservation",
    "server.code.api.services.story_preservation",
    "api.services.story_trigger",
    "code.api.services.story_trigger",
    "server.code.api.services.story_trigger",
)

# Modules in this allowlist are deliberately permitted even if they would
# otherwise look forbidden by prefix — but our prefix list is already
# minimal enough that this is empty for v1.
_ALLOWED_OVERRIDES: Tuple[str, ...] = (
    "api.services.lori_reflection",
    "code.api.services.lori_reflection",
    "server.code.api.services.lori_reflection",
)


# ── AST analysis — shared machinery (tests/source_scan_helpers.py) ────────
# Thin wrappers over the shared, unit-tested helpers; this gate keeps its
# historical semantics (ALL imports followed, depth-bounded at 4).

def _module_path_to_dotted(path: Path, server_code: Path = _SERVER_CODE) -> str:
    return ssh.module_path_to_dotted(path, server_code)


def _collect_imports_from_ast(tree: ast.AST, current_module_dotted: str) -> List[str]:
    """Records BOTH `X` and `X.Y` for `from X import Y` (see the helper
    module's docstring for the bug history)."""
    return ssh.collect_import_names(tree, current_module_dotted)


def _violates_forbidden(dotted: str) -> str | None:
    return ssh.violates_forbidden(
        dotted, _FORBIDDEN_PREFIXES, allowed_overrides=_ALLOWED_OVERRIDES)


def _walk_import_graph(
    start_path: Path,
    server_code: Path = _SERVER_CODE,
    max_depth: int = 4,
):
    result = ssh.walk_import_graph(
        start_path, server_code=server_code, max_depth=max_depth,
        follow="all")
    return result.visited, result.edges


# ── The actual test ───────────────────────────────────────────────────────

class UtteranceFrameIsolationTest(unittest.TestCase):
    """LAW: utterance_frame.py must not reach any forbidden module."""

    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"utterance_frame.py is missing at {_TARGET_FILE} — "
            "Phase 0-2 must include it.",
        )

    def test_no_forbidden_imports_direct(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        source = _TARGET_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_TARGET_FILE))
        dotted = _module_path_to_dotted(_TARGET_FILE)
        imports = _collect_imports_from_ast(tree, dotted)

        violations: List[Tuple[str, str]] = []
        for imp in imports:
            forbidden = _violates_forbidden(imp)
            if forbidden is not None:
                violations.append((imp, forbidden))

        self.assertFalse(
            violations,
            self._format_violations_message(violations, transitive=False),
        )

    def test_no_forbidden_imports_transitive(self):
        """utterance_frame.py must not REACH any forbidden module
        through any chain of project-internal imports. Depth-bounded
        at 4 to keep the test fast (each hop is a real file read)."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")

        visited, edges = _walk_import_graph(_TARGET_FILE)

        violations: List[Tuple[str, str, str]] = []
        for parent, child in edges:
            forbidden = _violates_forbidden(child)
            if forbidden is not None:
                violations.append((parent, child, forbidden))

        if violations:
            lines = [
                "LAW violation: utterance_frame.py reaches a forbidden",
                "module through one or more import chains.",
                "",
                "Forbidden chains found:",
            ]
            for parent, child, forbidden in violations:
                lines.append(
                    f"  {parent}  →  {child}   (matches forbidden prefix: {forbidden})"
                )
            lines += [
                "",
                "Modules visited during the walk (depth-bounded at 4):",
                *(f"  - {m}" for m in sorted(visited)),
                "",
                "Why this fails the build:",
                "  utterance_frame.py is the SHARED REPRESENTATION layer.",
                "  It is consumed by extractor (binding hints), Lori (echo",
                "  grounding), validator (negation flags), and safety",
                "  (scene-anchor signals). If it imports any consumer, it",
                "  becomes coupled to that consumer's lifecycle.",
                "",
                "If you genuinely need data from a forbidden module, the",
                "answer is NOT to import it here. Lift the data into the",
                "frame via build_frame()'s narrator_text input, OR write a",
                "consumer-side adapter that reads the frame and pulls the",
                "downstream data on its own side.",
                "",
                "See WO-EX-UTTERANCE-FRAME-01_Spec.md rule #7",
                "(NO FRAMEWORK DEPENDENCY).",
            ]
            self.fail("\n".join(lines))

    def test_target_module_has_law_comment(self):
        """Soft guardrail: the target file should announce the LAW in
        a comment near the top so anyone editing it knows the rules."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        text = _TARGET_FILE.read_text(encoding="utf-8")
        head = text[:4000]
        self.assertIn(
            "LAW",
            head,
            "utterance_frame.py header is missing the LAW callout. "
            "Restore the import-policy comment block.",
        )

    # ── Helpers ──────────────────────────────────────────────────────────

    def _format_violations_message(
        self,
        violations: List[Tuple[str, str]],
        *,
        transitive: bool,
    ) -> str:
        scope = "transitive" if transitive else "direct"
        lines = [
            f"LAW violation ({scope} imports):",
            "utterance_frame.py imports from a forbidden module.",
            "",
        ]
        for imp, forbidden in violations:
            lines.append(f"  {imp}   (forbidden prefix: {forbidden})")
        lines += [
            "",
            "utterance_frame.py is the SHARED REPRESENTATION layer and",
            "must remain pure deterministic. See",
            "WO-EX-UTTERANCE-FRAME-01_Spec.md rule #7.",
        ]
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main(verbosity=2)
