"""WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01 — LAW 3 isolation gate.
Hardened by WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6.

The operator drafting assistant must never reuse the narrator
conversation path or touch narrator state. This build-gate enforces it
mechanically:

  1. Import allowlist — trip_draft.py may import ONLY the sanctioned
     operator-side modules (trip_repository, travelogue_builder,
     evidence_text, llm_interview) plus stdlib. Any import of chat_ws /
     prompt_composer / extract / memory_echo / safety / a router fails.
  2. TRANSITIVE walk (Phase 6.1 — the 2026-07-24 review found the old
     gate checked only DIRECT imports, so a forbidden import added to
     trip_repository / travelogue_builder / travel_doc_lori_modal /
     trip_story_capture / evidence_text / llm_interview stayed green).
     The walker follows MODULE-LEVEL imports transitively, unbounded
     depth, and fails if any reachable module hits a forbidden prefix.
  3. Forbidden-symbol scan — with strings and comments stripped, the
     executable source must not reference runtime71, activeTripId,
     tripStyle, chat_ws, prompt_composer, extract, or safety. (Phase 6:
     "extract" and "safety" were missing from the tuple even though this
     docstring claimed coverage.)
  4. Dynamic-import scan (Phase 6.2) — __import__("…") and
     importlib.import_module("…") LITERAL-string calls in any walked
     module are matched against the forbidden prefixes. Computed /
     non-literal dynamic imports cannot be proven statically; literal
     forms are covered (see tests/source_scan_helpers.py).

DESIGN DECISION — module-level walk + sanctioned lazy edge:
  llm_interview lazily does `from .api import chat` INSIDE a function
  (`_try_call_llm`) — the sanctioned non-narrator inference path. api.py
  imports prompt_composer at module level, so a naive walk that follows
  function-level imports would flag prompt_composer THROUGH the
  sanctioned edge. The gate therefore walks module-level imports
  transitively (that is the boot-time coupling LAW 3 forbids) and
  SEPARATELY asserts that function-level imports touching api.api exist
  only inside llm_interview (the one sanctioned lazy edge) and that no
  function-level import anywhere in the walked graph matches a forbidden
  prefix. If trip_draft (or anything it reaches) ever imports api.api at
  MODULE level, the walk follows it and fails on api.prompt_composer.

Negative-test ritual: add `from ..routers import chat_ws` to
trip_draft.py → this gate must FAIL; remove it → PASS. Both states
required — a gate that passes in both is broken. The machinery-level
negative fixtures (direct, transitive, __import__, import_module) live
in tests/test_source_scan_helpers.py and run on every build.
"""
from __future__ import annotations

import ast
import io
import sys
import tokenize
import unittest
from pathlib import Path
from typing import List, Tuple

try:
    from tests import source_scan_helpers as ssh
except ImportError:  # direct execution: python tests/test_trip_draft_isolation.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as ssh

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
_TARGET = _SERVER_CODE / "api" / "services" / "trip_draft.py"

# Modules trip_draft.py is allowed to import directly (leaf name after
# the last dot). Everything else must be stdlib.
_ALLOWED_PROJECT = {
    "trip_repository", "travelogue_builder", "evidence_text", "llm_interview",
}

_FORBIDDEN_SYMBOLS = (
    "chat_ws", "prompt_composer", "runtime71", "activeTripId", "tripStyle",
    "memory_echo", "family_truth",
    # Phase 6.1: the docstring always claimed these; the tuple omitted them.
    "extract", "safety",
)

# The forbidden subgraph for the transitive walk. Any module whose dotted
# name starts with one of these prefixes is narrator-path / extraction /
# safety infrastructure and must not be reachable from trip_draft.py at
# boot time. Spellings mirror test_story_preservation_isolation.py
# (api. / code.api. / server.code.api.).
_FORBIDDEN_PREFIXES: Tuple[str, ...] = tuple(
    f"{spelling}{mod}"
    for mod in (
        # Extractor stack.
        "api.routers.extract",
        # Prompt composer + memory echo — runtime71-carrying prompt side.
        "api.prompt_composer",
        "api.memory_echo",
        # LLM API router + chat WS — the narrator conversation hot path
        # (chat_ws threads runtime71 into every turn).
        "api.routers.llm_api",
        "api.routers.chat_ws",
        # Family-truth pipeline + narrator-state router.
        "api.routers.family_truth",
        "api.routers.narrator_state",
        # Safety surface (module, classifier, acknowledgments).
        "api.safety",
        "api.safety_classifier",
        "api.safety_acknowledgments",
    )
    for spelling in ("", "code.", "server.code.")
)

# The ONE sanctioned lazy edge: llm_interview's function-level
# `from .api import chat` (the non-narrator inference path). Matched at
# module granularity so the concurrent raw_ephemeral work can adjust the
# imported names without breaking the gate; the boundary that matters is
# that ONLY llm_interview holds a lazy edge into api.api.
_SANCTIONED_LAZY_SOURCE_SUFFIX = ".llm_interview"
_LAZY_API_TARGETS = tuple(
    f"{spelling}api.api" for spelling in ("", "code.", "server.code.")
)


def _direct_imports(tree: ast.AST) -> List[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.append(a.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[-1]
            # relative "from . import X" → the X names are the modules
            if node.module is None:
                for a in node.names:
                    names.append(a.name.split(".")[-1])
            else:
                names.append(mod)
    return names


def _code_without_strings_and_comments(source: str) -> str:
    """Return source with all string tokens and comments blanked, so a
    forbidden-symbol scan sees executable references only (not the
    docstring that legitimately describes the LAW)."""
    out = []
    try:
        toks = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in toks:
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return source
    return " ".join(out)


def _is_lazy_api_target(dotted: str) -> bool:
    return any(dotted == t or dotted.startswith(t + ".")
               for t in _LAZY_API_TARGETS)


class TripDraftIsolationTest(unittest.TestCase):
    def test_target_exists(self):
        self.assertTrue(_TARGET.is_file(), f"missing {_TARGET}")

    def test_import_allowlist(self):
        """Direct imports: sanctioned operator-side modules + stdlib only.
        Stdlib membership is checked against sys.stdlib_module_names so
        legitimate stdlib additions don't need a gate edit (the LAW is
        about project modules, not the stdlib)."""
        tree = ast.parse(_TARGET.read_text(encoding="utf-8"))
        bad = []
        for name in _direct_imports(tree):
            if name in _ALLOWED_PROJECT or name in sys.stdlib_module_names:
                continue
            bad.append(name)
        self.assertFalse(
            bad,
            "trip_draft.py imports outside the operator-side allowlist: "
            + ", ".join(sorted(set(bad)))
            + ". Allowed project modules: "
            + ", ".join(sorted(_ALLOWED_PROJECT)) + " (plus stdlib)",
        )

    def test_no_forbidden_symbols_in_code(self):
        code = _code_without_strings_and_comments(
            _TARGET.read_text(encoding="utf-8"))
        hits = [s for s in _FORBIDDEN_SYMBOLS if s in code]
        self.assertFalse(
            hits,
            "trip_draft.py executable code references forbidden narrator-path "
            "symbols: " + ", ".join(hits),
        )

    def test_law_comment_present(self):
        head = _TARGET.read_text(encoding="utf-8")[:1200]
        self.assertIn("LAW 3", head,
                      "trip_draft.py header must announce the LAW 3 boundary")

    # ── Phase 6.1: the transitive gate ────────────────────────────────────

    def _walk(self) -> ssh.WalkResult:
        return ssh.walk_import_graph(
            _TARGET, server_code=_SERVER_CODE, max_depth=None,
            follow="module_level")

    def test_no_forbidden_imports_transitive_module_level(self):
        """trip_draft.py must not REACH any forbidden module through any
        chain of MODULE-LEVEL project-internal imports (boot-time
        coupling). Unbounded depth — the visited-set keeps the walk
        linear in reachable files, so no forbidden module can hide
        behind a long helper chain. Covers at least: trip_repository,
        travelogue_builder (→ travel_doc_lori_modal → trip_story_capture),
        evidence_text, llm_interview, and everything they import."""
        result = self._walk()

        # Sanity: the walk actually traverses the known first hops.
        for expected in ("api.services.trip_repository",
                         "api.services.travelogue_builder",
                         "api.services.evidence_text",
                         "api.llm_interview"):
            self.assertIn(
                expected, result.visited,
                f"transitive walk no longer reaches {expected} — the walker "
                "or trip_draft's sanctioned imports changed; the gate must "
                "be re-verified, not ignored.")

        violations: List[Tuple[str, str, str]] = []
        for parent, child in result.edges:
            forbidden = ssh.violates_forbidden(child, _FORBIDDEN_PREFIXES)
            if forbidden is not None:
                violations.append((parent, child, forbidden))

        if violations:
            lines = [
                "LAW 3 violation: trip_draft.py reaches the narrator path /",
                "extraction / safety stack through one or more module-level",
                "import chains.",
                "",
                "Forbidden chains found:",
            ]
            for parent, child, forbidden in violations:
                lines.append(
                    f"  {parent}  →  {child}   (matches forbidden prefix: {forbidden})")
            lines += [
                "",
                "Modules visited during the walk:",
                *(f"  - {m}" for m in sorted(result.visited)),
                "",
                "The operator drafting assistant must stay boot-time-decoupled",
                "from chat_ws / prompt_composer / extract / safety / memory_echo",
                "/ family_truth / narrator_state. If you need model inference,",
                "the ONLY sanctioned route is llm_interview's lazy",
                "`from .api import chat` inside a function body.",
            ]
            self.fail("\n".join(lines))

    def test_function_level_imports_only_sanctioned_lazy_edge(self):
        """Lazy (function-level) imports across the walked graph:
          - none may match a forbidden prefix, and
          - a lazy import into api.api is sanctioned ONLY from
            llm_interview (`from .api import chat` — the non-narrator
            inference path). Any other module growing a lazy api.api
            edge is a new narrator-path coupling and fails here."""
        result = self._walk()

        violations: List[str] = []
        saw_sanctioned_edge = False
        for parent, child in result.function_edges:
            forbidden = ssh.violates_forbidden(child, _FORBIDDEN_PREFIXES)
            if forbidden is not None:
                violations.append(
                    f"{parent} lazily imports {child} "
                    f"(forbidden prefix: {forbidden})")
            if _is_lazy_api_target(child):
                if parent.endswith(_SANCTIONED_LAZY_SOURCE_SUFFIX):
                    saw_sanctioned_edge = True
                else:
                    violations.append(
                        f"{parent} lazily imports {child} — the lazy api.api "
                        "edge is sanctioned ONLY inside llm_interview")

        self.assertFalse(
            violations,
            "Unsanctioned lazy imports in trip_draft's reachable graph:\n  "
            + "\n  ".join(violations))

        # The sanctioned edge must still exist — if llm_interview stops
        # lazy-importing api.api, this design note is stale and the gate
        # needs re-verification against the new inference path.
        self.assertTrue(
            saw_sanctioned_edge,
            "llm_interview's sanctioned lazy `from .api import chat` edge "
            "was not found — the inference path changed; re-verify this "
            "gate's module-level/lazy split against the new design.")

    def test_no_dynamic_imports_of_forbidden_modules(self):
        """Phase 6.2: __import__("…") / importlib.import_module("…")
        literal-string calls anywhere in the walked graph must not name
        a forbidden module. Computed arguments are not statically
        provable — literal forms are covered (helper docstring)."""
        result = self._walk()
        violations = []
        for parent, literal in result.dynamic_edges:
            forbidden = ssh.violates_forbidden(literal, _FORBIDDEN_PREFIXES)
            if forbidden is not None:
                violations.append(
                    f'{parent} dynamically imports "{literal}" '
                    f"(forbidden prefix: {forbidden})")
        self.assertFalse(
            violations,
            "Dynamic imports of forbidden modules in trip_draft's reachable "
            "graph:\n  " + "\n  ".join(violations))


if __name__ == "__main__":
    unittest.main(verbosity=2)
