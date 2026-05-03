"""WO-NARRATIVE-CUE-LIBRARY-01 Phase 2 — LAW 3 INFRASTRUCTURE gate
for narrative_cue_detector.py.

═══════════════════════════════════════════════════════════════════════
  LAW 3 [INFRASTRUCTURE]: The cue library is a LISTENER AID. It must
  not write truth, must not infer narrator identity, must not couple to
  the extraction pipeline. The mechanical guarantee is that
  narrative_cue_detector.py CANNOT IMPORT anything that would let it
  reach the extractor, the prompt composer, the chat WS, the family
  truth pipeline, the safety scanner, the DB, or its sibling
  preservation services.

  This test parses the AST of narrative_cue_detector.py, follows
  imports transitively, and fails the build if any reachable module is
  in the forbidden subgraph.

  The gate exists from Phase 2 forward. Any future commit that adds an
  extraction / db / sibling-service import to narrative_cue_detector.py
  — or to any module it transitively imports — will fail this test
  before it can land.

  Why mechanical, not aspirational:
    - Code review can miss imports
    - LLMs writing patches sometimes pull in "the obvious thing"
    - Refactors that split modules can accidentally re-couple paths
    - This test is the only thing that can't forget

  See WO-NARRATIVE-CUE-LIBRARY-01_Spec.md (locked: cue library may
  shape Lori's next question/statement/silence but cannot write Bio
  Builder / projection / promoted_truth / family_truth / protected
  identity — and the schema sets runtime_exposes_extract_hints: false).
═══════════════════════════════════════════════════════════════════════

Usage:
    python tests/test_narrative_cue_detector_isolation.py
    python -m unittest tests.test_narrative_cue_detector_isolation
    pytest tests/test_narrative_cue_detector_isolation.py

Negative-test verification (run during Phase 2 development):
    1. Add `from ..routers import extract` to
       server/code/api/services/narrative_cue_detector.py
    2. Run this test → must FAIL with a clear message naming
       `routers.extract` as the forbidden import.
    3. Remove the import.
    4. Run this test → must PASS.

Both states are required. A test that passes in both is broken.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import Iterable, List, Set, Tuple


# ── Configuration ─────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "narrative_cue_detector.py"

# Forbidden subgraph. Any module whose dotted name STARTS WITH any of
# these prefixes is OUT OF BOUNDS for the cue detector.
#
# Note: this list INTENTIONALLY includes sibling services
# (story_preservation, story_trigger, utterance_frame, lori_reflection)
# because the cue library has its own scope and must not silently
# borrow logic from them — if it needs something from one of them, the
# answer is to extract a third pure-stdlib helper or duplicate the
# minimum needed, not to couple the modules at runtime.
_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    # Direct extractor module — primary forbidden path.
    "api.routers.extract",
    "code.api.routers.extract",
    "server.code.api.routers.extract",
    # Prompt composer — extraction-side composer.
    "api.prompt_composer",
    "code.api.prompt_composer",
    "server.code.api.prompt_composer",
    # Memory echo — extraction-side composer.
    "api.memory_echo",
    "code.api.memory_echo",
    "server.code.api.memory_echo",
    # LLM API + WS — extraction calls them; cue library must not.
    "api.routers.llm_api",
    "code.api.routers.llm_api",
    "server.code.api.routers.llm_api",
    "api.routers.chat_ws",
    "code.api.routers.chat_ws",
    "server.code.api.routers.chat_ws",
    # Family-truth pipeline — downstream of extraction, not cue library.
    "api.routers.family_truth",
    "code.api.routers.family_truth",
    "server.code.api.routers.family_truth",
    # Safety scanner — separate concern; cue library must not borrow it.
    "api.safety",
    "code.api.safety",
    "server.code.api.safety",
    # DB layer — cue library must not write truth or read state.
    "api.db",
    "code.api.db",
    "server.code.api.db",
    # Sibling services — cue library must remain a stand-alone listener aid.
    # If a future detector legitimately needs a helper from one of these,
    # extract a third pure-stdlib module both can import.
    "api.services.story_preservation",
    "code.api.services.story_preservation",
    "server.code.api.services.story_preservation",
    "api.services.story_trigger",
    "code.api.services.story_trigger",
    "server.code.api.services.story_trigger",
    "api.services.utterance_frame",
    "code.api.services.utterance_frame",
    "server.code.api.services.utterance_frame",
    "api.services.lori_reflection",
    "code.api.services.lori_reflection",
    "server.code.api.services.lori_reflection",
    "api.services.lori_softened_response",
    "code.api.services.lori_softened_response",
    "server.code.api.services.lori_softened_response",
    "api.services.lori_communication_control",
    "code.api.services.lori_communication_control",
    "server.code.api.services.lori_communication_control",
    "api.services.question_atomicity",
    "code.api.services.question_atomicity",
    "server.code.api.services.question_atomicity",
    "api.services.stack_monitor",
    "code.api.services.stack_monitor",
    "server.code.api.services.stack_monitor",
)


# ── AST analysis (mirror of test_story_preservation_isolation pattern) ────

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
    """Resolve relative imports against the current module's package and
    record BOTH the base module and base.name forms for `from X import Y`.

    Why both: AST cannot tell whether Y is a submodule (resolves to X.Y)
    or a name in X (resolves to just X). Recording both makes the
    forbidden-prefix check robust against either spelling. Same fix as
    test_story_preservation_isolation — see its docstring for the bug
    history.
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


def _resolve_dotted_to_path(dotted: str, server_code: Path = _SERVER_CODE) -> Path | None:
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


# ── The actual test ───────────────────────────────────────────────────────

class NarrativeCueDetectorIsolationTest(unittest.TestCase):
    """LAW 3 INFRASTRUCTURE gate. narrative_cue_detector.py must not
    reach any forbidden module through any chain of imports."""

    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"narrative_cue_detector.py is missing at {_TARGET_FILE}",
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
        """narrative_cue_detector.py must not REACH any forbidden module
        through any chain of project-internal imports. Depth-bounded at 4."""
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
                "LAW 3 INFRASTRUCTURE violation: narrative_cue_detector.py",
                "reaches a forbidden module through one or more import chains.",
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
                "  Cue library is a LISTENER AID. It must not write truth,",
                "  must not couple to extraction, must not read DB state,",
                "  must not borrow from sibling services. If you need a",
                "  helper, extract it as a third pure-stdlib module that",
                "  both modules can import — don't couple this one.",
                "",
                "  See WO-NARRATIVE-CUE-LIBRARY-01_Spec.md.",
            ]
            self.fail("\n".join(lines))

    def test_target_module_has_law3_comment(self):
        """Soft guardrail — the target file should announce LAW 3 in a
        comment block near the top so anyone editing it knows what they
        are agreeing to."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        text = _TARGET_FILE.read_text(encoding="utf-8")
        head = text[:4000]
        self.assertIn(
            "LAW 3",
            head,
            "narrative_cue_detector.py header is missing the LAW 3 callout. "
            "Restore the import-policy comment block.",
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _format_violations_message(
        self,
        violations: List[Tuple[str, str]],
        *,
        transitive: bool,
    ) -> str:
        scope = "transitive" if transitive else "direct"
        lines = [
            f"LAW 3 INFRASTRUCTURE violation ({scope} imports):",
            "narrative_cue_detector.py imports from a forbidden module.",
            "",
        ]
        for imp, forbidden in violations:
            lines.append(f"  {imp}   (forbidden prefix: {forbidden})")
        lines += [
            "",
            "Cue library is a LISTENER AID. See LAW 3 in narrative_cue_detector.py",
            "and WO-NARRATIVE-CUE-LIBRARY-01_Spec.md.",
        ]
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main(verbosity=2)
