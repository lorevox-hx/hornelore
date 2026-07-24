"""WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01 — LAW 3 isolation gate.

The operator drafting assistant must never reuse the narrator conversation
path or touch narrator state. This build-gate enforces it mechanically:

  1. Import allowlist — trip_draft.py may import ONLY the sanctioned
     operator-side modules (trip_repository, travelogue_builder,
     evidence_text, llm_interview) plus stdlib. Any import of chat_ws /
     prompt_composer / extract / memory_echo / safety / a router fails.
  2. Forbidden-symbol scan — with the module docstring and comments
     stripped, the executable source must not reference runtime71,
     activeTripId, tripStyle, chat_ws, prompt_composer, or extract.

Negative-test: add `from ..routers import chat_ws` to trip_draft.py →
this test must FAIL; remove it → PASS. Both states required.
"""
from __future__ import annotations

import ast
import io
import tokenize
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TARGET = _REPO_ROOT / "server" / "code" / "api" / "services" / "trip_draft.py"

# Modules trip_draft.py is allowed to import (leaf name after the last dot
# for project modules; full name for stdlib).
_ALLOWED_PROJECT = {
    "trip_repository", "travelogue_builder", "evidence_text", "llm_interview",
}
_ALLOWED_STDLIB = {
    "__future__", "re", "typing", "logging", "json", "datetime",
}

_FORBIDDEN_SYMBOLS = (
    "chat_ws", "prompt_composer", "runtime71", "activeTripId", "tripStyle",
    "memory_echo", "family_truth",
)


def _direct_imports(tree: ast.AST):
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


class TripDraftIsolationTest(unittest.TestCase):
    def test_target_exists(self):
        self.assertTrue(_TARGET.is_file(), f"missing {_TARGET}")

    def test_import_allowlist(self):
        tree = ast.parse(_TARGET.read_text(encoding="utf-8"))
        bad = []
        for name in _direct_imports(tree):
            if name in _ALLOWED_PROJECT or name in _ALLOWED_STDLIB:
                continue
            bad.append(name)
        self.assertFalse(
            bad,
            "trip_draft.py imports outside the operator-side allowlist: "
            + ", ".join(sorted(set(bad)))
            + ". Allowed: " + ", ".join(sorted(_ALLOWED_PROJECT | _ALLOWED_STDLIB)),
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
