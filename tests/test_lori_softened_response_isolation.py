"""WO-LORI-SOFTENED-RESPONSE-01 LAW-3 isolation gate.

Same pattern as the other isolation gates. The softened-response
module composes a string from a state dict; it must not import
extraction-stack code, LLM runtime libraries, or chat_ws / composer
internals. Pure-function only.
"""
from __future__ import annotations

import ast
import os
import unittest


_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "code", "api", "services", "lori_softened_response.py",
)

_FORBIDDEN_PREFIXES = (
    "api.routers.extract",
    "api.prompt_composer",
    "api.memory_echo",
    "api.routers.chat_ws",
    "api.routers.llm_",
    "api.routers.family_truth",
    "api.routers.safety_events",
    "api.db",
)


def _collect_imports(tree):
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


class LoriSoftenedResponseIsolationTests(unittest.TestCase):
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
            f"LAW-3 violation: lori_softened_response.py imports forbidden "
            f"modules: {violations}",
        )

    def test_no_runtime_llm_imports(self):
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        forbidden_runtime = ("torch", "transformers", "openai", "anthropic", "sqlite3")
        tree = ast.parse(src)
        imports = _collect_imports(tree)
        violations = [n for n in imports if any(n.startswith(p) for p in forbidden_runtime)]
        self.assertEqual(
            violations, [],
            f"lori_softened_response.py must be pure-function — found "
            f"runtime LLM/db imports: {violations}",
        )

    def test_only_stdlib_imports(self):
        """The module should import nothing beyond stdlib + typing.
        No DB, no LLM, no router, no service composition. It builds
        a string from a dict; that's it."""
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertIn(
                        alias.name.split(".")[0],
                        {"typing", "re", "os", "logging"},
                        f"Unexpected import: {alias.name}",
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Allow `from typing import ...` and `from __future__ import ...`
                if node.level >= 1:
                    # No relative imports — the module composes nothing
                    self.fail(f"Unexpected relative import: {module}")
                self.assertIn(
                    module.split(".")[0] if module else "",
                    {"typing", "__future__", ""},
                    f"Unexpected absolute import: from {module}",
                )


if __name__ == "__main__":
    unittest.main()
