"""WO-LORI-REFLECTION-01 LAW-3 isolation gate.

Same pattern as test_question_atomicity_isolation.py /
test_story_preservation_isolation.py — AST-walks lori_reflection.py and
asserts it imports zero extraction-stack modules.
"""
from __future__ import annotations

import ast
import os
import unittest


_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "code", "api", "services", "lori_reflection.py",
)

_FORBIDDEN_PREFIXES = (
    "api.routers.extract",
    "api.prompt_composer",
    "api.memory_echo",
    "api.routers.chat_ws",
    "api.routers.llm_",
    "api.routers.family_truth",
)


def _collect_imports(tree: ast.AST) -> list:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                qualified = f"{module}.{alias.name}" if module else alias.name
                names.append(qualified)
                if module:
                    names.append(module)
    return names


class LoriReflectionIsolationTests(unittest.TestCase):
    def test_module_file_exists(self):
        self.assertTrue(os.path.exists(_MODULE_PATH))

    def test_no_forbidden_imports(self):
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        imports = _collect_imports(tree)
        violations = []
        for name in imports:
            for prefix in _FORBIDDEN_PREFIXES:
                if prefix in name:
                    violations.append((name, prefix))
        self.assertEqual(
            violations, [],
            f"LAW-3 violation: lori_reflection.py imports forbidden "
            f"modules: {violations}",
        )

    def test_no_runtime_llm_imports(self):
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        forbidden_runtime = ("torch", "transformers", "openai", "anthropic")
        tree = ast.parse(src)
        imports = _collect_imports(tree)
        violations = [n for n in imports if any(n.startswith(p) for p in forbidden_runtime)]
        self.assertEqual(
            violations, [],
            f"lori_reflection.py must be pure-function — found runtime "
            f"LLM imports: {violations}",
        )


if __name__ == "__main__":
    unittest.main()
