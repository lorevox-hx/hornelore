"""WO-TIMELINE-CONTEXT-EVENTS-01 Phase A — LAW 3 INFRASTRUCTURE gate.

═══════════════════════════════════════════════════════════════════════
  LAW 3 [INFRASTRUCTURE]: timeline_context_events is operator-curated
  historical scaffolding. Lori does NOT write to it, ever. The
  repository module must NOT reach the live narrator path through any
  chain of imports.

  This test enforces the rule MECHANICALLY. It parses the AST of
  `services/timeline_context_events_repository.py`, follows imports
  transitively, and fails the build if any reachable module is in the
  forbidden subgraph.

  Pattern mirrors test_story_preservation_isolation.py — same AST
  walker shape, same negative-test discipline.

  Why mechanical, not aspirational:
    - Code review can miss imports
    - LLMs writing patches sometimes pull in "the obvious thing"
    - Refactors that split modules can accidentally re-couple paths
    - This test is the only thing that can't forget

  See WO-TIMELINE-CONTEXT-EVENTS-01_Spec.md §"North Star (locked)" —
  Lori does not write to this table. The repository is the wall.
═══════════════════════════════════════════════════════════════════════

Usage:
    python tests/test_timeline_context_events_isolation.py
    python -m unittest tests.test_timeline_context_events_isolation
    pytest tests/test_timeline_context_events_isolation.py

Negative-test verification (run during Phase A development):
    1. Add `from ..routers import extract` to
       server/code/api/services/timeline_context_events_repository.py
    2. Run this test → must FAIL with a clear message naming
       `routers.extract` as the forbidden import.
    3. Remove the import.
    4. Run this test → must PASS.

Both states are required. A test that passes in both is broken.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import Iterable, List, Set, Tuple


# ── Configuration ─────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = (
    _SERVER_CODE / "api" / "services" / "timeline_context_events_repository.py"
)

# The forbidden subgraph. Any module whose dotted name STARTS WITH any
# of these prefixes is in the live narrator path / extraction stack
# / Lori behavior layer and must not be reachable from the repository.
_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    # Extractor + extraction-side composers
    "api.routers.extract",
    "code.api.routers.extract",
    "server.code.api.routers.extract",
    "api.prompt_composer",
    "code.api.prompt_composer",
    "server.code.api.prompt_composer",
    "api.memory_echo",
    "code.api.memory_echo",
    "server.code.api.memory_echo",
    # LLM API + chat WS — runtime narrator path
    "api.routers.llm_api",
    "code.api.routers.llm_api",
    "server.code.api.routers.llm_api",
    "api.routers.chat_ws",
    "code.api.routers.chat_ws",
    "server.code.api.routers.chat_ws",
    # Family-truth pipeline — downstream of extraction
    "api.routers.family_truth",
    "code.api.routers.family_truth",
    "server.code.api.routers.family_truth",
    # Story-capture lane (separate write surface; must stay separate)
    "api.services.story_preservation",
    "code.api.services.story_preservation",
    "server.code.api.services.story_preservation",
    "api.services.story_trigger",
    "code.api.services.story_trigger",
    "server.code.api.services.story_trigger",
    # Lori-behavior services
    "api.services.lori_communication_control",
    "code.api.services.lori_communication_control",
    "server.code.api.services.lori_communication_control",
    "api.services.lori_reflection",
    "code.api.services.lori_reflection",
    "server.code.api.services.lori_reflection",
    "api.services.lori_narrative_cues",
    "code.api.services.lori_narrative_cues",
    "server.code.api.services.lori_narrative_cues",
    "api.services.safety_classifier",
    "code.api.services.safety_classifier",
    "server.code.api.services.safety_classifier",
    # Utterance frame — pure but adjacent to the live path; keep
    # the timeline-context lane separate so future composer hooks
    # don't accidentally cross-import.
    "api.services.utterance_frame",
    "code.api.services.utterance_frame",
    "server.code.api.services.utterance_frame",
    # Peek-at-memoir — read accessor for memory_echo; keep separate.
    "api.services.peek_at_memoir",
    "code.api.services.peek_at_memoir",
    "server.code.api.services.peek_at_memoir",
)


# ── AST analysis ──────────────────────────────────────────────────────────


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
    """Extract every import target from a parsed module, resolving
    relative imports against the current module's dotted name.

    For `from X import Y`, we record BOTH `X` and `X.Y` so the
    forbidden-prefix check catches whichever spelling lands on the list.
    """
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


def _resolve_dotted_to_path(dotted: str, server_code: Path = _SERVER_CODE):
    candidate_module = server_code / Path(*dotted.split("."))
    py_file = candidate_module.with_suffix(".py")
    init_file = candidate_module / "__init__.py"
    if py_file.is_file():
        return py_file
    if init_file.is_file():
        return init_file
    return None


def _violates_forbidden(dotted: str):
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


# ── Tests ─────────────────────────────────────────────────────────────────


class TimelineContextEventsIsolationTest(unittest.TestCase):
    """LAW 3 INFRASTRUCTURE gate. The repository module must not reach
    any forbidden module through any chain of imports."""

    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"Target file not found: {_TARGET_FILE}",
        )

    def test_target_file_parses(self):
        source = _TARGET_FILE.read_text(encoding="utf-8")
        try:
            ast.parse(source, filename=str(_TARGET_FILE))
        except SyntaxError as exc:
            self.fail(f"Target file has syntax error: {exc}")

    def test_no_forbidden_imports_reachable(self):
        visited, edges = _walk_import_graph(_TARGET_FILE)
        violations: List[Tuple[str, str]] = []

        for parent, child in edges:
            offending_prefix = _violates_forbidden(child)
            if offending_prefix:
                violations.append((parent, child))

        if violations:
            msg_lines = [
                "",
                "Timeline-context-events repository imports a forbidden module.",
                "",
                "Per LAW 3 [INFRASTRUCTURE], the repository module must not",
                "reach the live narrator path / extractor / Lori-behavior",
                "layer through any import chain.",
                "",
                "Found violations:",
            ]
            for parent, child in violations[:20]:
                msg_lines.append(f"  - {parent}  →  {child}")
            if len(violations) > 20:
                msg_lines.append(f"  ... and {len(violations) - 20} more")
            msg_lines.extend([
                "",
                "Either remove the import, or — if the import is genuinely",
                "needed — file a WO to re-architect the seam. Do NOT add",
                "the offending module to the allowlist without a spec.",
            ])
            self.fail("\n".join(msg_lines))


if __name__ == "__main__":
    unittest.main()
