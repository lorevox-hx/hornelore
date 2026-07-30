"""TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- module isolation gate.

=======================================================================
  LAW: truth_pipeline_probe.py is OBSERVABILITY ONLY. No DB. No LLM.
       No archive. No extractor. No Lori. No safety. No chat_ws. No
       family-truth pipeline. No projection writer. No FastAPI.

  This test enforces the rule MECHANICALLY. It parses the AST of
  services/truth_pipeline_probe.py, follows imports transitively, and
  fails the build if any reachable module is in the forbidden subgraph.

  Why mechanical, not aspirational:
    - The probe is called FROM inside the truth-write stages it
      measures. If it ever imports one of them, it creates an import
      cycle at best and a measurement that changes the thing being
      measured at worst.
    - The probe must be safe to call from a chat-turn hot path, a
      db.py transaction commit, a filesystem archive append, and an
      HTTP handler --- without dragging any of those into each other.
    - Phase 1 is allowed to observe and forbidden to route. An import
      of db / archive / projection_writer would be the first step
      toward Phase 2 behavior leaking into a Phase 1 commit.
    - Code review can miss imports. This test cannot forget.
=======================================================================

Negative-test verification (run during Phase 1 development):
    1. Add `from .. import db` to
       server/code/api/services/truth_pipeline_probe.py
    2. Run this test --> must FAIL naming `api.db` as forbidden.
    3. Remove the import.
    4. Run this test --> must PASS.

Both states are required. A test that passes in both is broken.

Only `api.flags` is permitted: flags.py is the repo's single place to
ask "is this flag on", it imports nothing but os + typing, and keeping
the probe on it prevents a second copy of the truthy-parsing rule.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import List, Tuple

try:
    from tests import source_scan_helpers as ssh
except ImportError:  # direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as ssh


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "truth_pipeline_probe.py"

_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    # DB --- the probe counts nothing and reads nothing
    "api.db",
    "code.api.db",
    "server.code.api.db",
    # Archive --- one of the five stages; must not be reachable
    "api.archive",
    "code.api.archive",
    "server.code.api.archive",
    # Extractor stack --- one of the five stages
    "api.routers.extract",
    "code.api.routers.extract",
    "server.code.api.routers.extract",
    # Family-truth pipeline --- one of the five stages
    "api.routers.family_truth",
    "code.api.routers.family_truth",
    "server.code.api.routers.family_truth",
    # Projection writer --- one of the five stages
    "api.services.projection_writer",
    "code.api.services.projection_writer",
    "server.code.api.services.projection_writer",
    # Chat hot path
    "api.routers.chat_ws",
    "code.api.routers.chat_ws",
    "server.code.api.routers.chat_ws",
    "api.routers.llm_api",
    "code.api.routers.llm_api",
    "server.code.api.routers.llm_api",
    # Operator surfaces --- consumers read the probe, never the reverse
    "api.routers.operator_harness",
    "code.api.routers.operator_harness",
    "server.code.api.routers.operator_harness",
    # Lori prompt-side runtime
    "api.prompt_composer",
    "code.api.prompt_composer",
    "server.code.api.prompt_composer",
    "api.memory_echo",
    "code.api.memory_echo",
    "server.code.api.memory_echo",
    # Safety surface
    "api.safety",
    "code.api.safety",
    "server.code.api.safety",
)

_ALLOWED_OVERRIDES: Tuple[str, ...] = ()


def _module_path_to_dotted(path: Path, server_code: Path = _SERVER_CODE) -> str:
    return ssh.module_path_to_dotted(path, server_code)


def _collect_imports_from_ast(tree: ast.AST, current_module_dotted: str) -> List[str]:
    return ssh.collect_import_names(tree, current_module_dotted)


def _violates_forbidden(dotted: str) -> "str | None":
    return ssh.violates_forbidden(
        dotted, _FORBIDDEN_PREFIXES, allowed_overrides=_ALLOWED_OVERRIDES)


def _walk_import_graph(start_path: Path, server_code: Path = _SERVER_CODE,
                       max_depth: int = 4):
    result = ssh.walk_import_graph(
        start_path, server_code=server_code, max_depth=max_depth, follow="all")
    return result.visited, result.edges


class TruthPipelineProbeIsolationTest(unittest.TestCase):
    """LAW: the probe must not reach any module it measures."""

    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"truth_pipeline_probe.py is missing at {_TARGET_FILE} --- "
            "Phase 1 must include it.",
        )

    def test_no_forbidden_imports_direct(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        tree = ast.parse(_TARGET_FILE.read_text(encoding="utf-8"),
                         filename=str(_TARGET_FILE))
        dotted = _module_path_to_dotted(_TARGET_FILE)
        violations = []
        for imp in _collect_imports_from_ast(tree, dotted):
            forbidden = _violates_forbidden(imp)
            if forbidden is not None:
                violations.append((imp, forbidden))
        self.assertFalse(
            violations,
            "LAW violation (direct imports): truth_pipeline_probe.py "
            "imports a module it is supposed to be measuring.\n"
            + "\n".join(f"  {i}  (matches {f})" for i, f in violations),
        )

    def test_no_forbidden_imports_transitive(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        visited, edges = _walk_import_graph(_TARGET_FILE)
        violations = []
        for parent, child in edges:
            forbidden = _violates_forbidden(child)
            if forbidden is not None:
                violations.append((parent, child, forbidden))
        if violations:
            lines = [
                "LAW violation: truth_pipeline_probe.py reaches a forbidden",
                "module through one or more import chains.",
                "",
                "Forbidden chains found:",
            ]
            for parent, child, forbidden in violations:
                lines.append(f"  {parent}  ->  {child}   (matches {forbidden})")
            lines += [
                "",
                "Modules visited (depth-bounded at 4):",
                *(f"  - {m}" for m in sorted(visited)),
                "",
                "Why this fails the build:",
                "  The probe is called from inside the stages it measures.",
                "  Importing one of them makes the instrument part of the",
                "  circuit. If you need data from a forbidden module, pass",
                "  it in as a mark() detail string from the caller's side.",
            ]
            self.fail("\n".join(lines))

    def test_target_module_has_law_comment(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        head = _TARGET_FILE.read_text(encoding="utf-8")[:4000]
        self.assertIn(
            "LAW", head,
            "truth_pipeline_probe.py header is missing the LAW callout. "
            "Restore the import-policy comment block.",
        )

    def test_probe_declares_observability_only(self):
        """Phase 1 is allowed to observe and forbidden to route. The
        header has to say so, because the next session reads the header
        before it reads the checklist."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        head = _TARGET_FILE.read_text(encoding="utf-8")[:4000]
        self.assertIn("OBSERVABILITY ONLY", head)
        self.assertIn("changes NO behavior", head)


if __name__ == "__main__":
    unittest.main()
