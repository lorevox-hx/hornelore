"""WO-LORI-STORY-CAPTURE-01 Phase 1A Commit 1 — LAW 3 INFRASTRUCTURE gate.

═══════════════════════════════════════════════════════════════════════
  LAW 3 [INFRASTRUCTURE]: Preservation is guaranteed; extraction is
  best-effort. The code path for preservation does NOT call the
  extractor. The extractor does NOT block preservation.

  This test enforces the rule MECHANICALLY. It parses the AST of
  `services/story_preservation.py`, follows imports transitively, and
  fails the build if any reachable module is in the extraction-stack
  subgraph.

  The build gate exists from Phase 1A Commit 1 forward. Any future
  commit that adds an extraction import to story_preservation.py — or
  to any module story_preservation transitively imports — will fail
  this test before it can land.

  Why mechanical, not aspirational:
    - Code review can miss imports
    - LLMs writing patches sometimes pull in "the obvious thing"
    - Refactors that split modules can accidentally re-couple paths
    - This test is the only thing that can't forget

  See WO-LORI-STORY-CAPTURE-01_Spec.md §0.5 (golfball architecture):
  this test is the wall around the WINDINGS layer. It says: nothing
  from the COVER layer (extraction) gets to write here.
═══════════════════════════════════════════════════════════════════════

Usage:
    python tests/test_story_preservation_isolation.py
    python -m unittest tests.test_story_preservation_isolation
    pytest tests/test_story_preservation_isolation.py

Negative-test verification (run during Phase 1A Commit 1 development):
    1. Add `from ..routers import extract` to
       server/code/api/services/story_preservation.py
    2. Run this test → must FAIL with a clear message naming
       `routers.extract` as the forbidden import.
    3. Remove the import.
    4. Run this test → must PASS.

Both states are required. A test that passes in both is broken.

WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6: the walker and
import collector this gate pioneered (including the from-import
both-forms fix — bug history preserved in the helper's docstring) now
live in tests/source_scan_helpers.py, unit-tested there, and are shared
by the sibling isolation gates. Semantics unchanged: ALL imports
(module- and function-level) are followed, depth-bounded at 4, same
forbidden-prefix list, same failure messages.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from typing import List, Tuple

try:
    from tests import source_scan_helpers as ssh
except ImportError:  # direct execution: python tests/test_story_preservation_isolation.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as ssh


# ── Configuration ─────────────────────────────────────────────────────────
# Repo root is two parents up from this file: tests/<this>.py
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET_FILE = _SERVER_CODE / "api" / "services" / "story_preservation.py"

# The forbidden subgraph. Any module whose dotted name STARTS WITH any of
# these prefixes is part of the extraction stack and must not be reachable
# from story_preservation.py.
#
# Prefixes are matched against the resolved dotted module name (the
# project-internal path to the module). Stdlib and third-party imports
# are not in this set — they're allowed.
_FORBIDDEN_PREFIXES: Tuple[str, ...] = (
    # Direct extractor module — the primary forbidden path.
    "api.routers.extract",
    "code.api.routers.extract",
    "server.code.api.routers.extract",
    # Prompt composer drives extraction prompts; preservation must not see it.
    "api.prompt_composer",
    "code.api.prompt_composer",
    "server.code.api.prompt_composer",
    # Memory echo — extraction-side composer.
    "api.memory_echo",
    "code.api.memory_echo",
    "server.code.api.memory_echo",
    # LLM API + WS — extraction calls them; preservation must not.
    "api.routers.llm_api",
    "code.api.routers.llm_api",
    "server.code.api.routers.llm_api",
    "api.routers.chat_ws",
    "code.api.routers.chat_ws",
    "server.code.api.routers.chat_ws",
    # Family-truth pipeline — downstream of extraction, not preservation.
    "api.routers.family_truth",
    "code.api.routers.family_truth",
    "server.code.api.routers.family_truth",
)


# ── AST analysis — shared machinery (tests/source_scan_helpers.py) ────────
# The walker + collector this gate pioneered are now the shared,
# unit-tested helpers. Thin local wrappers keep this gate's historical
# semantics: ALL imports followed (module- AND function-level — lazy
# coupling is forbidden here too), depth-bounded at 4.

def _module_path_to_dotted(path: Path, server_code: Path = _SERVER_CODE) -> str:
    return ssh.module_path_to_dotted(path, server_code)


def _collect_imports_from_ast(tree: ast.AST, current_module_dotted: str) -> List[str]:
    return ssh.collect_import_names(tree, current_module_dotted)


def _violates_forbidden(dotted: str) -> str | None:
    """Return the first forbidden prefix that `dotted` matches, or None."""
    return ssh.violates_forbidden(dotted, _FORBIDDEN_PREFIXES)


def _walk_import_graph(
    start_path: Path,
    server_code: Path = _SERVER_CODE,
    max_depth: int = 4,
):
    """Walk ALL imports transitively from `start_path`. Returns
    (set of every dotted module visited, list of (parent, child) edges)."""
    result = ssh.walk_import_graph(
        start_path, server_code=server_code, max_depth=max_depth,
        follow="all")
    return result.visited, result.edges


# ── The actual test ───────────────────────────────────────────────────────

class StoryPreservationIsolationTest(unittest.TestCase):
    """LAW 3 INFRASTRUCTURE gate. story_preservation.py must not reach
    any module in the extraction-stack subgraph through any chain of
    imports."""

    def test_target_file_exists(self):
        """Sanity: the file we're testing must exist before we can
        meaningfully test its imports."""
        self.assertTrue(
            _TARGET_FILE.is_file(),
            f"story_preservation.py is missing at {_TARGET_FILE} — "
            "Phase 1A Commit 1 must include it.",
        )

    def test_no_forbidden_imports_direct(self):
        """story_preservation.py itself must not import anything from
        the forbidden list. This is the cheap check that runs first
        and gives the clearest error message."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing; covered by test_target_file_exists")

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
        """story_preservation.py must not REACH any forbidden module
        through any chain of project-internal imports. This is the
        real LAW 3 enforcement — direct imports could be hidden behind
        an innocent-looking helper module. The walker follows them all.

        Depth-bounded at 4 to keep the test fast (each hop is a real
        file read + parse). 4 hops is more than enough to catch any
        plausible coupling in this codebase; if a future architecture
        legitimately needs deeper chains, raise the bound and revisit
        whether the rule still mechanically holds."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing; covered by test_target_file_exists")

        visited, edges = _walk_import_graph(_TARGET_FILE)

        violations: List[Tuple[str, str, str]] = []
        for parent, child in edges:
            forbidden = _violates_forbidden(child)
            if forbidden is not None:
                violations.append((parent, child, forbidden))

        if violations:
            lines = [
                "LAW 3 INFRASTRUCTURE violation: story_preservation.py reaches",
                "the extraction stack through one or more import chains.",
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
                "  Path 1 (preservation) MUST NOT depend on Path 2 (extraction).",
                "  See WO-LORI-STORY-CAPTURE-01_Spec.md §0.5 and LAW 3.",
                "  If the extractor dies, every story must still be preserved.",
                "  The way to make that guaranteed (not just hoped-for) is to",
                "  refuse to compile when the two paths get coupled.",
                "",
                "If you genuinely need data from the extraction side inside",
                "preservation, the answer is NOT to import it here. Write it",
                "back to story_candidates.extracted_fields via a separate",
                "accessor in db.py and read it from there.",
            ]
            self.fail("\n".join(lines))

    def test_target_module_has_law3_comment(self):
        """Soft guardrail — the target file should announce LAW 3 in a
        comment near the top so anyone editing it knows what they're
        agreeing to. Catches the case where the file gets rewritten
        and the rule is silently lost."""
        if not _TARGET_FILE.is_file():
            self.skipTest("target file missing")
        text = _TARGET_FILE.read_text(encoding="utf-8")
        head = text[:4000]  # check the first 4KB
        self.assertIn(
            "LAW 3",
            head,
            "story_preservation.py header is missing the LAW 3 callout. "
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
            "story_preservation.py imports from the forbidden extraction stack.",
            "",
        ]
        for imp, forbidden in violations:
            lines.append(f"  {imp}   (forbidden prefix: {forbidden})")
        lines += [
            "",
            "Path 1 (preservation) cannot depend on Path 2 (extraction).",
            "See WO-LORI-STORY-CAPTURE-01_Spec.md §0.5 and LAW 3.",
        ]
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main(verbosity=2)
