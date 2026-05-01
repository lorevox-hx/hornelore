"""WO-LORI-QUESTION-ATOMICITY-01 LAW-3 isolation gate.

Same pattern as tests/test_story_preservation_isolation.py — AST-walks
question_atomicity.py and asserts it imports zero extraction-stack
modules. If any forbidden prefix appears in any import statement
(direct or transitive in the same module file), the build FAILS.

Forbidden prefixes:
    api.routers.extract
    api.prompt_composer
    api.memory_echo
    api.routers.chat_ws
    api.routers.llm_*
    api.routers.family_truth

These are the modules that would couple atomicity (a chat-side concern)
to the extraction stack (a different concern with its own LLM and
schema). Per the §6 architecture in WO-LORI-QUESTION-ATOMICITY-01_Spec
the filter must remain a pure-function module.
"""
from __future__ import annotations

import ast
import os
import unittest


_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "code", "api", "services", "question_atomicity.py",
)

# Forbidden module-name prefixes. Match against both:
#   from <prefix>... import X
#   from .....<prefix>... import X  (relative)
#   import <prefix>...
_FORBIDDEN_PREFIXES = (
    "api.routers.extract",
    "api.prompt_composer",
    "api.memory_echo",
    "api.routers.chat_ws",
    "api.routers.llm_",
    "api.routers.family_truth",
)


def _collect_imports(tree: ast.AST) -> list:
    """Return a list of fully-qualified module names imported by the
    AST. Handles both `import x` and `from x import y` forms, including
    relative `from ..package import y`."""
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Relative imports get a leading dot count we mostly ignore;
            # what matters is the module name suffix.
            for alias in node.names:
                qualified = f"{module}.{alias.name}" if module else alias.name
                names.append(qualified)
                # Also include the module itself
                if module:
                    names.append(module)
    return names


class QuestionAtomicityIsolationTests(unittest.TestCase):
    def test_module_file_exists(self):
        self.assertTrue(
            os.path.exists(_MODULE_PATH),
            f"question_atomicity.py not found at {_MODULE_PATH}",
        )

    def test_no_forbidden_imports(self):
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        imports = _collect_imports(tree)
        violations = []
        for name in imports:
            for prefix in _FORBIDDEN_PREFIXES:
                # Match prefix anywhere — handles `from
                # api.routers.extract import X`, `from
                # ...routers.extract import X`, and bare `import
                # api.routers.extract`.
                if prefix in name:
                    violations.append((name, prefix))
        self.assertEqual(
            violations, [],
            f"LAW-3 isolation violation: question_atomicity.py imports "
            f"forbidden modules: {violations}",
        )

    def test_no_runtime_llm_call_imports(self):
        """Sanity: no torch/transformers/llm-loading imports either.
        The filter is pure-function deterministic per the §6 spec."""
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        forbidden_runtime = ("torch", "transformers", "openai", "anthropic")
        tree = ast.parse(src)
        imports = _collect_imports(tree)
        violations = [n for n in imports if any(n.startswith(p) for p in forbidden_runtime)]
        self.assertEqual(
            violations, [],
            f"question_atomicity.py must be pure-function — found runtime "
            f"LLM imports: {violations}",
        )


if __name__ == "__main__":
    unittest.main()
