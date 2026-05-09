"""BUG-LORI-IDENTITY-META-QUESTION-DETERMINISTIC-ROUTE-01 — module
isolation gate.

═══════════════════════════════════════════════════════════════════════
  LAW: lori_meta_question.py is pure deterministic. No LLM. No DB.
       No IO. No NLP framework. No extractor. No prompt composer.
       No safety. No memory echo. No chat_ws.

  This module is wired into chat_ws.py BEFORE the safety classifier
  and BEFORE the LLM. If it imports any of those modules, it
  re-introduces the very surfaces it's meant to bypass — destroying
  its correctness guarantee.

  The mechanical AST gate enforces this. Any forbidden import
  reachable transitively from lori_meta_question.py fails the build.
═══════════════════════════════════════════════════════════════════════

Negative-test verification (run during development):
    1. Add `from ..routers import extract` to
       server/code/api/services/lori_meta_question.py
    2. Run this test → must FAIL with a clear message.
    3. Remove the import.
    4. Run this test → must PASS.

Both states are required. A test that passes in both is broken.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Iterable, List, Set, Tuple


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "lori_meta_question.py"


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
    # Both the pattern-side safety and the LLM second-layer classifier
    # are forbidden — the whole point of this module is to bypass them
    # for narrator meta-questions.
    "api.safety",
    "code.api.safety",
    "server.code.api.safety",
    "api.safety_classifier",
    "code.api.safety_classifier",
    "server.code.api.safety_classifier",
    "api.db",
    "code.api.db",
    "server.code.api.db",
    "api.services.story_preservation",
    "code.api.services.story_preservation",
    "server.code.api.services.story_preservation",
    "api.services.story_trigger",
    "code.api.services.story_trigger",
    "server.code.api.services.story_trigger",
)

_ALLOWED_OVERRIDES: Tuple[str, ...] = ()


def _module_path_to_dotted(path: Path, server_code: Path = _SERVER_CODE) -> str:
    try:
        rel = path.resolve().relative_to(server_code.resolve())
    except ValueError:
        return str(path)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _collect_imports_from_ast(tree: ast.AST, current_module_dotted: str) -> List[str]:
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
                    base_parts = parent_parts[: len(parent_parts) - node.level + 1]
                if node.module:
                    base_parts = base_parts + node.module.split(".")
                base = ".".join(base_parts)
                _emit_module_and_children(base, [a.name for a in node.names])
            else:
                if node.module:
                    _emit_module_and_children(
                        node.module, [a.name for a in node.names]
                    )
    return imports


def _resolve_dotted_to_path(dotted: str, server_code: Path = _SERVER_CODE) -> Path | None:
    candidate_module = server_code / Path(*dotted.split("."))
    py_file = candidate_module.with_suffix(".py")
    init_file = candidate_module / "__init__.py"
    if py_file.is_file():
        return py_file
    if init_file.is_file():
        return init_file
    return None


def _is_allowed_override(dotted: str) -> bool:
    for allow in _ALLOWED_OVERRIDES:
        if dotted == allow or dotted.startswith(allow + "."):
            return True
    return False


def _violates_forbidden(dotted: str) -> str | None:
    if _is_allowed_override(dotted):
        return None
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


class LoriMetaQuestionIsolationTest(unittest.TestCase):
    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"lori_meta_question.py missing at {_TARGET_FILE}",
        )

    def test_no_forbidden_imports_direct(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        source = _TARGET_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(_TARGET_FILE))
        dotted = _module_path_to_dotted(_TARGET_FILE)
        imports = _collect_imports_from_ast(tree, dotted)
        violations = [
            (imp, _violates_forbidden(imp))
            for imp in imports
            if _violates_forbidden(imp) is not None
        ]
        self.assertFalse(
            violations,
            "Forbidden direct imports in lori_meta_question.py: "
            + ", ".join(f"{imp} (matches {f})" for imp, f in violations),
        )

    def test_no_forbidden_imports_transitive(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        visited, edges = _walk_import_graph(_TARGET_FILE)
        violations = [
            (parent, child, _violates_forbidden(child))
            for parent, child in edges
            if _violates_forbidden(child) is not None
        ]
        if violations:
            lines = [
                "LAW violation: lori_meta_question.py reaches a forbidden",
                "module through an import chain.",
                "",
                "Forbidden chains:",
            ]
            for parent, child, forbidden in violations:
                lines.append(f"  {parent}  →  {child}   (matches: {forbidden})")
            lines += [
                "",
                "Modules visited (depth ≤4):",
                *(f"  - {m}" for m in sorted(visited)),
                "",
                "lori_meta_question.py is the deterministic intercept",
                "BEFORE the safety classifier and BEFORE the LLM. If it",
                "imports either of those, it re-introduces the very",
                "surfaces it's meant to bypass.",
            ]
            self.fail("\n".join(lines))

    def test_target_module_has_law_comment(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        text = _TARGET_FILE.read_text(encoding="utf-8")
        head = text[:4000]
        # Looking for "LAW 3" or any LAW marker — tolerant
        self.assertTrue(
            "LAW" in head or "Pure" in head or "deterministic" in head.lower(),
            "lori_meta_question.py header should announce determinism / no-IO LAW",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
