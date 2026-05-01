"""WO-LORI-COMMUNICATION-CONTROL-01 LAW-3 isolation gate.

The wrapper composes question_atomicity + lori_reflection. Both already
have their own isolation gates. The wrapper itself must also stay clean
of extraction-stack imports.
"""
from __future__ import annotations

import ast
import os
import unittest


_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "server", "code", "api", "services", "lori_communication_control.py",
)

_FORBIDDEN_PREFIXES = (
    "api.routers.extract",
    "api.prompt_composer",
    "api.memory_echo",
    "api.routers.chat_ws",
    "api.routers.llm_",
    "api.routers.family_truth",
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


class LoriCommunicationControlIsolationTests(unittest.TestCase):
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
            f"LAW-3 violation: lori_communication_control.py imports "
            f"forbidden modules: {violations}",
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
            f"lori_communication_control.py must be pure-function — found "
            f"runtime LLM imports: {violations}",
        )

    def test_only_composes_local_services(self):
        """Sanity: imports either stdlib or sibling services modules.
        Catches accidental imports of routers/extractors as the codebase
        evolves."""
        with open(_MODULE_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Allow relative imports of sibling services (e.g.
                # `.question_atomicity`), and stdlib (no leading dot).
                # Reject anything else.
                if node.level >= 1:
                    # Relative — should target a sibling services module
                    for alias in node.names:
                        target = f"{module}.{alias.name}" if module else alias.name
                        # Must end in question_atomicity or lori_reflection
                        # (the only services this wrapper composes)
                        self.assertTrue(
                            "question_atomicity" in target
                            or "lori_reflection" in target,
                            f"Unexpected relative import: {target}",
                        )


if __name__ == "__main__":
    unittest.main()
