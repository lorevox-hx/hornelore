"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 1 — LAW 3 isolation gate.

═══════════════════════════════════════════════════════════════════════
  LAW 3 [INFRASTRUCTURE]: The questionnaire read aggregator is a pure
  read-only projection over canonical truth. It must NOT pull in
  extractor / chat_ws / prompt_composer / family_truth or any other
  side-effecting subsystem. If it does, a refactor could turn a
  questionnaire GET into a live-LLM call or DB write.

  This test enforces the rule MECHANICALLY by AST-walking the imports
  of `services/bio_questionnaire_view.py`, following them transitively,
  and failing the build if any reachable module is in the forbidden
  subgraph.

  Pattern mirrors test_story_preservation_isolation.py exactly. Same
  walker, same dotted-name resolution, same depth bound.

  Negative-test verification (run during Phase 1 development):
    1. Add `from ..routers import extract` to
       server/code/api/services/bio_questionnaire_view.py
    2. Run this test → must FAIL naming `routers.extract`.
    3. Remove the import.
    4. Run this test → must PASS.

  Both states are required. A test that passes in both is broken.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Iterable, List, Set, Tuple


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "bio_questionnaire_view.py"


# Forbidden subgraph. Any module whose dotted name STARTS WITH any of
# these prefixes is forbidden for the view aggregator.
_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    "api.routers.extract",
    "code.api.routers.extract",
    "server.code.api.routers.extract",
    "api.prompt_composer",
    "code.api.prompt_composer",
    "server.code.api.prompt_composer",
    "api.memory_echo",
    "code.api.memory_echo",
    "server.code.api.memory_echo",
    "api.routers.llm_api",
    "code.api.routers.llm_api",
    "server.code.api.routers.llm_api",
    "api.routers.chat_ws",
    "code.api.routers.chat_ws",
    "server.code.api.routers.chat_ws",
    "api.routers.family_truth",
    "code.api.routers.family_truth",
    "server.code.api.routers.family_truth",
    "api.safety",
    "code.api.safety",
    "server.code.api.safety",
)


def _module_path_to_dotted(path: Path, server_code: Path = _SERVER_CODE) -> str:
    try:
        rel = path.resolve().relative_to(server_code.resolve())
    except ValueError:
        return str(path)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _collect_imports_from_ast(
    tree: ast.AST, current_module_dotted: str,
) -> List[str]:
    imports: List[str] = []
    parent_parts = current_module_dotted.split(".")[:-1]

    def _emit_module_and_children(base: str, names: Iterable[str]) -> None:
        if base:
            imports.append(base)
        for name in names:
            if name and name != "*":
                imports.append(f"{base}.{name}" if base else name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if node.level > len(parent_parts):
                    base_parts: List[str] = []
                else:
                    base_parts = parent_parts[
                        : len(parent_parts) - node.level + 1
                    ]
                if node.module:
                    base_parts = base_parts + node.module.split(".")
                base = ".".join(base_parts)
                _emit_module_and_children(
                    base, [a.name for a in node.names],
                )
            else:
                if node.module:
                    _emit_module_and_children(
                        node.module, [a.name for a in node.names],
                    )
    return imports


def _resolve_dotted_to_path(
    dotted: str, server_code: Path = _SERVER_CODE,
) -> Path | None:
    candidate_module = server_code / Path(*dotted.split("."))
    py_file = candidate_module.with_suffix(".py")
    init_file = candidate_module / "__init__.py"
    if py_file.is_file():
        return py_file
    if init_file.is_file():
        return init_file
    return None


def _violates_forbidden(dotted: str) -> str | None:
    for prefix in _FORBIDDEN_PREFIXES:
        if dotted == prefix or dotted.startswith(prefix + "."):
            return prefix
    return None


def _walk_import_graph(
    start_path: Path,
    server_code: Path = _SERVER_CODE,
    max_depth: int = 4,
) -> Tuple[Set[str], List[Tuple[str, str]]]:
    visited: Set[str] = set()
    edges: List[Tuple[str, str]] = []
    queue: List[Tuple[Path, int]] = [(start_path, 0)]
    while queue:
        path, depth = queue.pop(0)
        if depth > max_depth:
            continue
        dotted = _module_path_to_dotted(path, server_code)
        if dotted in visited:
            continue
        visited.add(dotted)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for imp in _collect_imports_from_ast(tree, dotted):
            edges.append((dotted, imp))
            child_path = _resolve_dotted_to_path(imp, server_code)
            if child_path is not None and depth + 1 <= max_depth:
                queue.append((child_path, depth + 1))
    return visited, edges


class BioQuestionnaireViewIsolationTest(unittest.TestCase):
    """LAW 3 INFRASTRUCTURE gate. bio_questionnaire_view.py must not
    reach extractor / prompt_composer / chat_ws / family_truth / safety
    through any chain of project-internal imports."""

    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"bio_questionnaire_view.py is missing at {_TARGET_FILE} — "
            "Phase 1 must include it.",
        )

    def test_target_file_parses(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        source = _TARGET_FILE.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(_TARGET_FILE))
        except SyntaxError as exc:
            self.fail(f"bio_questionnaire_view.py has SyntaxError: {exc}")

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
            "Forbidden direct imports detected:\n  "
            + "\n  ".join(
                f"{imp} → matches {forbidden}" for imp, forbidden in violations
            ),
        )

    def test_no_forbidden_imports_transitive(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        _, edges = _walk_import_graph(_TARGET_FILE)
        violations: List[Tuple[str, str, str]] = []
        for parent, child in edges:
            forbidden = _violates_forbidden(child)
            if forbidden is not None:
                violations.append((parent, child, forbidden))
        self.assertFalse(
            violations,
            "Forbidden TRANSITIVE imports detected:\n  "
            + "\n  ".join(
                f"{parent} → {child} (matches {forbidden})"
                for parent, child, forbidden in violations
            ),
        )


if __name__ == "__main__":
    unittest.main()
