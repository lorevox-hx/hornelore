"""WO-LORI-SESSION-AWARENESS-01 Phase 4 (skeleton) — module isolation gate.

═══════════════════════════════════════════════════════════════════════
  LAW: narrator_pacing.py is pure deterministic. No LLM. No DB. No IO.
       No NLP framework. No extractor. No Lori. No prompt composer.
       No safety. No memory echo. No chat_ws. No story preservation.

  This test enforces the rule MECHANICALLY. It parses the AST of
  `services/narrator_pacing.py`, follows imports transitively, and
  fails the build if any reachable module is in the forbidden subgraph.

  Why mechanical, not aspirational:
    - narrator_pacing is the per-narrator silence-ladder learner. The
      eventual consumer is the visual-presence dispatcher (Phase 3),
      and POSSIBLY a future spoken-cue gate (Phase 5+ ONLY, behind
      test-matrix evidence).
    - It must be safe to call from a chat-turn hot path, a CLI debug
      runner, AND a unit-test loop — without bringing the rest of the
      world with it.
    - The whole module is feature-flag-gated to default-OFF. The
      isolation gate makes sure that when someone DOES wire it live,
      they cannot have accidentally coupled it to a consumer in the
      meantime.
    - Code review can miss imports. Refactors split modules and
      sometimes accidentally re-couple paths. This test is the only
      thing that can't forget.

  See WO-LORI-SESSION-AWARENESS-01_Spec.md Phase 4 design rules
  and the "DO NOT WIRE LIVE" docstring banner of narrator_pacing.py.
═══════════════════════════════════════════════════════════════════════

Negative-test verification (run during Phase 4 development):
    1. Add `from ..routers import extract` to
       server/code/api/services/narrator_pacing.py
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
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "narrator_pacing.py"

# The forbidden subgraph. Any module whose dotted name starts with one of
# these prefixes is part of the extractor / Lori / safety / UI / chat
# stack and must NOT be reachable from narrator_pacing.py.
#
# Sibling pure-function service modules (utterance_frame, lori_reflection,
# age_arithmetic) are NEITHER required nor forbidden — they're not in the
# prefix list at all because narrator_pacing has no need to import them.
# If a future phase legitimately needs one, add an _ALLOWED_OVERRIDES
# entry here AND a justification comment in narrator_pacing.py.
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
    # DB — pacing is in-memory only by design; no rows, no schema.
    "api.db",
    "code.api.db",
    "server.code.api.db",
    # Story preservation lane — keep its LAW 3 isolation intact.
    "api.services.story_preservation",
    "code.api.services.story_preservation",
    "server.code.api.services.story_preservation",
    "api.services.story_trigger",
    "code.api.services.story_trigger",
    "server.code.api.services.story_trigger",
    # Utterance frame — sibling pure-function module, but pacing
    # operates on gap durations + prompt_weight, not narrator text;
    # coupling here would be an architectural smell.
    "api.services.utterance_frame",
    "code.api.services.utterance_frame",
    "server.code.api.services.utterance_frame",
    # Lori reflection — sibling pure-function module. Pacing decides
    # WHEN Lori may speak; reflection decides HOW. They must not couple.
    "api.services.lori_reflection",
    "code.api.services.lori_reflection",
    "server.code.api.services.lori_reflection",
)

# Modules in this allowlist are deliberately permitted even if they would
# otherwise look forbidden by prefix. Empty for v1 — narrator_pacing
# should need stdlib only.
_ALLOWED_OVERRIDES: Tuple[str, ...] = ()


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
    relative imports against the current module's dotted name. Records
    BOTH `X` and `X.Y` for `from X import Y` (see story_preservation
    isolation test for bug history)."""
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
            # Skip unreadable / non-Python / binary files. The walk is
            # depth-bounded and best-effort — if a file can't be parsed,
            # it can't introduce a forbidden edge into our graph.
            continue

        for imp in _collect_imports_from_ast(tree, dotted):
            edges.append((dotted, imp))
            child_path = _resolve_dotted_to_path(imp, server_code)
            if child_path is not None and depth + 1 <= max_depth:
                queue.append((child_path, depth + 1))

    return visited, edges


# ── The actual test ───────────────────────────────────────────────────────

class NarratorPacingIsolationTest(unittest.TestCase):
    """LAW: narrator_pacing.py must not reach any forbidden module."""

    def test_target_file_exists(self):
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"narrator_pacing.py is missing at {_TARGET_FILE} — "
            "Phase 4 skeleton must include it.",
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
        """narrator_pacing.py must not REACH any forbidden module
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
                "LAW violation: narrator_pacing.py reaches a forbidden",
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
                "  narrator_pacing.py is the per-narrator silence-ladder",
                "  learner. It must remain pure deterministic so that the",
                "  visual-presence dispatcher (Phase 3) and any future",
                "  Phase 5+ spoken-cue gate can both consume it without",
                "  pulling extractor / Lori / safety / DB into their hot",
                "  path.",
                "",
                "If you genuinely need data from a forbidden module, the",
                "answer is NOT to import it here. Lift the data into the",
                "pacing call via add_response_gap() / get_silence_decision()",
                "arguments, OR write a consumer-side adapter that reads",
                "the pacing snapshot and pulls the downstream data on its",
                "own side.",
                "",
                "See WO-LORI-SESSION-AWARENESS-01_Spec.md Phase 4 and the",
                "DO NOT WIRE LIVE banner of narrator_pacing.py.",
            ]
            self.fail("\n".join(lines))

    def test_target_module_has_do_not_wire_live_banner(self):
        """Soft guardrail: the target file MUST announce the
        DO NOT WIRE LIVE rule near the top so anyone editing it knows
        Phase 4 is feature-flag-gated default-OFF until Chris green-
        lights live observation against Janice/Kent."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        text = _TARGET_FILE.read_text(encoding="utf-8")
        head = text[:4000]
        self.assertIn(
            "DO NOT WIRE LIVE",
            head,
            "narrator_pacing.py header is missing the DO NOT WIRE LIVE "
            "banner. Restore it — it is the only thing standing between "
            "the skeleton and an accidental cold-start ladder going live.",
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
            "narrator_pacing.py imports from a forbidden module.",
            "",
        ]
        for imp, forbidden in violations:
            lines.append(f"  {imp}   (forbidden prefix: {forbidden})")
        lines += [
            "",
            "narrator_pacing.py is a pure deterministic per-narrator",
            "silence-ladder learner. See WO-LORI-SESSION-AWARENESS-01",
            "Phase 4 design rules and the DO NOT WIRE LIVE banner.",
        ]
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main(verbosity=2)
