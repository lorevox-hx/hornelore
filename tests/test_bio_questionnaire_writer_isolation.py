"""WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 3 — LAW 3 isolation.

Mechanical gate: bio_questionnaire_writer.py must not reach extractor /
chat_ws / prompt_composer / family_truth / safety through any chain of
project-internal imports. Pattern matches the bio_questionnaire_view
gate from Phase 1.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Iterable, List, Set, Tuple


_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = (
    _SERVER_CODE / "api" / "services" / "bio_questionnaire_writer.py"
)

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

    def _emit(base: str, names: Iterable[str]) -> None:
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
                _emit(".".join(base_parts), [a.name for a in node.names])
            else:
                if node.module:
                    _emit(node.module, [a.name for a in node.names])
    return imports


def _resolve_dotted_to_path(
    dotted: str, server_code: Path = _SERVER_CODE,
) -> Path | None:
    candidate = server_code / Path(*dotted.split("."))
    py = candidate.with_suffix(".py")
    init = candidate / "__init__.py"
    if py.is_file():
        return py
    if init.is_file():
        return init
    return None


def _violates(dotted: str) -> str | None:
    for prefix in _FORBIDDEN_PREFIXES:
        if dotted == prefix or dotted.startswith(prefix + "."):
            return prefix
    return None


def _walk_imports(
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
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            continue
        for imp in _collect_imports_from_ast(tree, dotted):
            edges.append((dotted, imp))
            child = _resolve_dotted_to_path(imp, server_code)
            if child is not None and depth + 1 <= max_depth:
                queue.append((child, depth + 1))
    return visited, edges


class BioQuestionnaireWriterIsolationTest(unittest.TestCase):
    def test_target_exists(self):
        self.assertTrue(_TARGET_FILE.is_file())

    def test_target_parses(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target missing")
        try:
            ast.parse(_TARGET_FILE.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            self.fail(f"writer SyntaxError: {exc}")

    def test_no_forbidden_direct_imports(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target missing")
        tree = ast.parse(_TARGET_FILE.read_text(encoding="utf-8"))
        imports = _collect_imports_from_ast(
            tree, _module_path_to_dotted(_TARGET_FILE),
        )
        viol = [(i, _violates(i)) for i in imports if _violates(i)]
        self.assertFalse(
            viol,
            "Forbidden direct imports:\n  "
            + "\n  ".join(f"{i} → {v}" for i, v in viol),
        )

    def test_no_forbidden_transitive(self):
        if not _TARGET_FILE.is_file():
            self.skipTest("target missing")
        _, edges = _walk_imports(_TARGET_FILE)
        viol = [(p, c, _violates(c)) for p, c in edges if _violates(c)]
        self.assertFalse(
            viol,
            "Forbidden transitive imports:\n  "
            + "\n  ".join(f"{p} → {c} ({v})" for p, c, v in viol),
        )


if __name__ == "__main__":
    unittest.main()
