"""Shared source-scanning machinery for the mechanical boundary gates.

WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6.

The 2026-07-24 code review found the transitive import walker + AST
import collector copy-pasted across isolation gates (8x) and never
itself unit-tested, and a shared broken JS comment stripper that deleted
everything after "//" inside string literals (any "http://…" URL blinded
the banned-token scan to end-of-line). This module is the single home
for both, with its own unit tests in tests/test_source_scan_helpers.py.

Consumers:
  - tests/test_trip_draft_isolation.py         (module-level transitive walk)
  - tests/test_story_preservation_isolation.py (legacy all-imports walk)
  - tests/test_utterance_frame_isolation.py    (legacy all-imports walk)
  - tests/test_travel_doc_lab.py               (string-aware JS stripper)
  - tests/test_travel_documenter_panel.py      (string-aware JS stripper)

── Python import analysis ────────────────────────────────────────────────

collect_import_names(tree, dotted)
    Every import target in the module, resolving relative imports against
    the module's dotted name. For `from X import Y` it records BOTH `X`
    and `X.Y` — Python's AST cannot distinguish whether Y is a submodule
    (import resolves to `X.Y`) or a name defined in X (resolves to `X`).
    Bug history (inherited from the story_preservation gate, where it was
    discovered by running the negative test BEFORE banking the gate): the
    original collector only emitted `X` for `from X import Y`, so an
    injected `from ..routers import extract` silently passed because the
    forbidden prefix `api.routers.extract` did not match the recorded
    `api.routers`.

collect_module_imports(tree, dotted) -> ModuleImports
    Same resolution rules, but SPLIT into:
      .module_level    — imports executed at import time (module body,
                         class bodies, module-level if/try blocks). This
                         is the boot-time coupling most gates enforce.
      .function_level  — imports inside (async) function bodies: lazy
                         edges that only fire when the function runs.
      .dynamic_literal — literal string arguments of __import__("…") /
                         importlib.import_module("…") calls anywhere in
                         the module. LIMITATION (documented, deliberate):
                         computed/dynamic imports (variables, f-strings,
                         getattr tricks) cannot be proven statically;
                         only the literal forms are covered. A gate that
                         wants stronger guarantees must forbid the
                         dynamic-import callables outright.

walk_import_graph(start_path, server_code, max_depth=None, follow=...)
    Transitive BFS over project-internal imports. follow="all" reproduces
    the legacy gates' behavior (module- and function-level imports are
    both recorded in .edges and followed). follow="module_level" records
    and follows ONLY boot-time imports in .edges, while still collecting
    every visited module's function-level (.function_edges) and dynamic
    (.dynamic_edges) imports so a gate can police lazy edges separately
    (e.g. llm_interview's sanctioned lazy `from .api import chat`).
    max_depth=None means unbounded — the visited-set makes cost linear in
    the reachable file count, so gates no longer need a depth bound.

── JS comment stripping ──────────────────────────────────────────────────

strip_js_comments(js)
    String-aware replacement for the old
    re.sub(r"/\\*[\\s\\S]*?\\*/|//[^\\n]*", "", js) one-liner, which treated
    the "//" inside "http://localhost:8000" as a line comment and blinded
    every banned-token scan from there to end-of-line. This scanner
    tokenizes string literals first (single-quote, double-quote, template
    literals, backslash escapes) and regex literals (heuristic: a "/" in
    expression position, e.g. after "(", ",", "=", "return"; needed
    because the gated files contain /"/g and /'/g whose quote chars would
    otherwise open phantom strings), and removes ONLY real // and /* */
    comments. String/regex contents are preserved verbatim.

Negative-test doctrine (applies to every consumer gate): inject a
forbidden import → the gate must FAIL; remove it → PASS. Both states are
required; a gate that passes in both is broken. The reusable fixtures
proving the walker CAN fail live in tests/test_source_scan_helpers.py.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set, Tuple

# ── Repo layout constants (importers may override per-call) ──────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_CODE = REPO_ROOT / "server" / "code"


# ── Dotted-name / path resolution ────────────────────────────────────────

def module_path_to_dotted(path: Path, server_code: Path = SERVER_CODE) -> str:
    """Convert a file path under `server_code` to a dotted module name.

    Example: server/code/api/services/trip_draft.py → api.services.trip_draft
    Paths outside `server_code` are returned as-is (they won't match any
    project-internal forbidden prefix).
    """
    try:
        rel = path.resolve().relative_to(server_code.resolve())
    except ValueError:
        return str(path)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def resolve_dotted_to_path(dotted: str,
                           server_code: Path = SERVER_CODE) -> Optional[Path]:
    """Best-effort: resolve a dotted module name to a file under
    `server_code`. Tries `.py`, then `__init__.py`. Returns None if not
    project-internal (stdlib / third-party / unresolvable)."""
    if not dotted or dotted.startswith("."):
        return None
    candidate_module = server_code / Path(*dotted.split("."))
    py_file = candidate_module.with_suffix(".py")
    init_file = candidate_module / "__init__.py"
    if py_file.is_file():
        return py_file
    if init_file.is_file():
        return init_file
    return None


# ── Import collection ────────────────────────────────────────────────────

def _names_from_import_node(node: ast.stmt, parent_parts: List[str]) -> List[str]:
    """Resolve one Import/ImportFrom node to dotted names. Records BOTH
    `X` and `X.Y` for from-imports (see module docstring: bug history)."""
    names: List[str] = []

    def _emit(base: str, subnames: Iterable[str]) -> None:
        if base:
            names.append(base)
        for name in subnames:
            if name and name != "*":
                names.append(f"{base}.{name}" if base else name)

    if isinstance(node, ast.Import):
        for alias in node.names:
            names.append(alias.name)  # alias.name is the full dotted path
    elif isinstance(node, ast.ImportFrom):
        if node.level and node.level > 0:
            # Relative import: resolve against the module's package.
            if node.level > len(parent_parts):
                base_parts: List[str] = []
            else:
                base_parts = parent_parts[: len(parent_parts) - node.level + 1]
            if node.module:
                base_parts = base_parts + node.module.split(".")
            _emit(".".join(base_parts), [a.name for a in node.names])
        elif node.module:
            _emit(node.module, [a.name for a in node.names])
    return names


def collect_import_names(tree: ast.AST, current_module_dotted: str) -> List[str]:
    """Legacy collector: EVERY import target in the module (module-level
    and function-level alike), relative imports resolved. This is the
    exact semantics the story_preservation / utterance_frame gates have
    always enforced — kept for gates that forbid even lazy coupling."""
    parent_parts = current_module_dotted.split(".")[:-1]
    out: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.extend(_names_from_import_node(node, parent_parts))
    return out


@dataclass
class ModuleImports:
    """Imports of one module, split by when they execute."""
    module_level: List[str] = field(default_factory=list)
    function_level: List[str] = field(default_factory=list)
    dynamic_literal: List[str] = field(default_factory=list)


_DYNAMIC_IMPORT_CALLABLES = ("__import__", "import_module")


def _collect_dynamic_literals(tree: ast.AST) -> List[str]:
    """Literal string arguments of __import__("…") and
    importlib.import_module("…") calls (any alias of the importlib module
    is matched via the .import_module attribute name). Computed arguments
    are NOT detectable statically — see module docstring."""
    out: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_dynamic = (
            (isinstance(func, ast.Name) and func.id in _DYNAMIC_IMPORT_CALLABLES)
            or (isinstance(func, ast.Attribute)
                and func.attr in _DYNAMIC_IMPORT_CALLABLES)
        )
        if not is_dynamic or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append(arg.value)
    return out


def collect_module_imports(tree: ast.AST,
                           current_module_dotted: str) -> ModuleImports:
    """Split collector: boot-time (module-level) vs lazy (function-level)
    imports, plus dynamic-import literals. Imports inside class bodies and
    module-level if/try blocks execute at import time → module_level."""
    parent_parts = current_module_dotted.split(".")[:-1]
    result = ModuleImports()

    def _visit(node: ast.AST, in_function: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _visit(child, True)
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                bucket = (result.function_level if in_function
                          else result.module_level)
                bucket.extend(_names_from_import_node(child, parent_parts))
            else:
                _visit(child, in_function)

    _visit(tree, False)
    result.dynamic_literal = _collect_dynamic_literals(tree)
    return result


# ── Forbidden-prefix matching ────────────────────────────────────────────

def violates_forbidden(dotted: str,
                       forbidden_prefixes: Sequence[str],
                       allowed_overrides: Sequence[str] = ()) -> Optional[str]:
    """Return the first forbidden prefix `dotted` matches, or None.
    A prefix matches on exact equality or as a dotted-path prefix
    (`prefix.`). Allowed overrides are checked first and win."""
    for allow in allowed_overrides:
        if dotted == allow or dotted.startswith(allow + "."):
            return None
    for prefix in forbidden_prefixes:
        if dotted == prefix or dotted.startswith(prefix + "."):
            return prefix
    return None


# ── Transitive walk ──────────────────────────────────────────────────────

@dataclass
class WalkResult:
    """Result of walk_import_graph.

    visited        — dotted name of every module parsed during the walk.
    edges          — (parent, child) for every FOLLOWED import kind
                     (all imports for follow="all"; boot-time imports
                     only for follow="module_level").
    function_edges — (parent, child) for function-level (lazy) imports of
                     every visited module. For follow="all" these are
                     ALSO present in .edges; recorded separately so gates
                     can allowlist sanctioned lazy edges.
    dynamic_edges  — (parent, literal) for __import__/import_module
                     literal-string calls in every visited module. Never
                     followed (the target may not even exist on disk);
                     gates match the literal against forbidden prefixes.
    """
    visited: Set[str] = field(default_factory=set)
    edges: List[Tuple[str, str]] = field(default_factory=list)
    function_edges: List[Tuple[str, str]] = field(default_factory=list)
    dynamic_edges: List[Tuple[str, str]] = field(default_factory=list)


def walk_import_graph(
    start_path: Path,
    server_code: Path = SERVER_CODE,
    max_depth: Optional[int] = None,
    follow: str = "all",
) -> WalkResult:
    """Walk project-internal imports transitively from `start_path`.

    follow="all"           — legacy gate semantics: module- and function-
                             level imports are both recorded in .edges
                             and followed into child modules.
    follow="module_level"  — only boot-time imports are recorded in
                             .edges and followed. Function-level and
                             dynamic imports of every visited module are
                             still COLLECTED (function_edges /
                             dynamic_edges) for separate policing, but a
                             lazy import does not pull its target's own
                             import graph into the walk.

    max_depth=None walks the whole reachable subgraph (the visited-set
    keeps this linear in reachable file count). Unreadable / unparsable
    files are skipped: they cannot introduce a forbidden edge.
    """
    if follow not in ("all", "module_level"):
        raise ValueError(f"unknown follow mode: {follow!r}")

    result = WalkResult()
    queue: List[Tuple[Path, int]] = [(start_path, 0)]

    while queue:
        path, depth = queue.pop(0)
        if max_depth is not None and depth > max_depth:
            continue
        dotted = module_path_to_dotted(path, server_code)
        if dotted in result.visited:
            continue
        result.visited.add(dotted)

        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
            # Skip unreadable / non-Python files. Best-effort: a file
            # that can't be parsed can't add a forbidden edge here.
            continue

        collected = collect_module_imports(tree, dotted)

        for parent, child in ((dotted, c) for c in collected.function_level):
            result.function_edges.append((parent, child))
        for literal in collected.dynamic_literal:
            result.dynamic_edges.append((dotted, literal))

        if follow == "all":
            followable = collected.module_level + collected.function_level
        else:
            followable = collected.module_level

        for imp in followable:
            result.edges.append((dotted, imp))
            child_path = resolve_dotted_to_path(imp, server_code)
            if child_path is not None and (
                max_depth is None or depth + 1 <= max_depth
            ):
                queue.append((child_path, depth + 1))

    return result


# ── String-aware JS comment stripper ─────────────────────────────────────

# A "/" starts a regex literal (not division) when the previous
# significant character puts us in expression position, or the previous
# word is one of these keywords. Heuristic — covers every regex literal
# in the gated UI files (all appear after "(" or ",").
_REGEX_PRECEDER_CHARS = set("([{,;:=!&|?+*%^~<>-\n")
_REGEX_PRECEDER_KEYWORDS = {
    "return", "typeof", "case", "in", "of", "new", "delete", "void",
    "do", "else", "instanceof", "yield", "await",
}
_TRAILING_WORD_RX = re.compile(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*$")


def strip_js_comments(js: str) -> str:
    """Remove real // and /* */ comments from JS source, preserving the
    contents of string literals ('…', "…", `…`), template literals, and
    regex literals verbatim.

    Replaces the broken re.sub(r"/\\*[\\s\\S]*?\\*/|//[^\\n]*") stripper the
    boundary gates shared, which treated the "//" inside a string like
    "http://localhost:8000" as a line comment and deleted the rest of the
    line — blinding banned-token scans (2026-07-24 review finding).

    Mechanics:
      - '…' / "…" / `…`: consumed until the matching unescaped delimiter;
        backslash escapes ("\\"", '\\'', \\`) never terminate early.
        Template-literal contents (including "//" and "${…}") are kept
        as-is; interpolation is not recursed into — a backtick inside an
        interpolated expression is the one unsupported corner, absent
        from the gated files.
      - Regex literals: a "/" in expression position consumes to the
        closing unescaped "/" (character classes respected), so /"/g and
        /'/g never open phantom strings and /\\/$/ never opens a comment.
        If no closing "/" appears on the same line the guess is abandoned
        (division), with the consumed text kept verbatim.
      - // comments: dropped to (not including) the newline.
      - /* */ comments: dropped entirely, including the newlines inside —
        same as the old stripper, so line/offset-based assertions in the
        gates keep their meaning.
    """
    out: List[str] = []
    i = 0
    n = len(js)
    last_sig = "\n"  # start-of-input behaves like expression position

    def _prev_word_is_keyword() -> bool:
        m = _TRAILING_WORD_RX.search("".join(out[-16:]))
        return bool(m) and m.group(1) in _REGEX_PRECEDER_KEYWORDS

    while i < n:
        c = js[i]
        nxt = js[i + 1] if i + 1 < n else ""

        if c == "/" and nxt == "/":            # line comment
            i += 2
            while i < n and js[i] != "\n":
                i += 1
            continue                            # newline (if any) kept

        if c == "/" and nxt == "*":            # block comment
            i += 2
            while i + 1 < n and not (js[i] == "*" and js[i + 1] == "/"):
                i += 1
            i = min(i + 2, n)
            continue

        if c in ('"', "'", "`"):               # string / template literal
            quote = c
            out.append(c)
            i += 1
            while i < n:
                ch = js[i]
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    out.append(js[i + 1])
                    i += 2
                    continue
                i += 1
                if ch == quote:
                    break
            last_sig = quote
            continue

        if c == "/" and (
            last_sig in _REGEX_PRECEDER_CHARS or _prev_word_is_keyword()
        ):                                      # regex literal
            start_out_len = len(out)
            start_i = i
            out.append(c)
            i += 1
            in_class = False
            closed = False
            while i < n:
                ch = js[i]
                if ch == "\n":
                    break                       # bad guess — bail
                out.append(ch)
                if ch == "\\" and i + 1 < n:
                    out.append(js[i + 1])
                    i += 2
                    continue
                i += 1
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    closed = True
                    break
            if closed:
                while i < n and js[i].isalpha():   # regex flags
                    out.append(js[i])
                    i += 1
                last_sig = "/"
            else:
                # Not a regex after all: rewind and re-scan as plain code
                # starting one char past the "/" (division operator).
                del out[start_out_len:]
                out.append("/")
                i = start_i + 1
                last_sig = "/"
            continue

        out.append(c)
        if not c.isspace() or c == "\n":
            last_sig = c
        i += 1

    return "".join(out)
