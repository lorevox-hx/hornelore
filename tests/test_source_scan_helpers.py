"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6 — unit tests
for the shared boundary-gate machinery in tests/source_scan_helpers.py.

The 2026-07-24 review found the transitive import walker copy-pasted 8x
across isolation gates and NEVER itself tested, and a shared JS comment
stripper that blinded banned-token scans after any "http://…" URL. This
file is the proof the machinery works — including the required negative
fixtures showing the walker CAN fail for each detection lane:

  1. direct forbidden import                       (module-level edge)
  2. transitive forbidden import (A → B → chat_ws) (walked edge)
  3. __import__("api.routers.chat_ws")             (dynamic literal)
  4. importlib.import_module("api.prompt_composer")(dynamic literal)

All fixtures are temporary files in tempfile dirs handed to the walker as
its project root — production files are NEVER edited at test runtime.
A gate whose machinery cannot be made to fail is broken; these tests are
the standing replacement for the manual "inject forbidden import → gate
FAILS → remove → PASSES" ritual at the machinery level (each consumer
gate still documents the ritual for its own target file).
"""
from __future__ import annotations

import ast
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

try:
    from tests import source_scan_helpers as ssh
except ImportError:  # direct execution: python tests/test_source_scan_helpers.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as ssh


_FORBIDDEN = (
    "api.routers.chat_ws",
    "api.routers.extract",
    "api.prompt_composer",
)


def _parse(src: str) -> ast.AST:
    return ast.parse(textwrap.dedent(src))


# ── Import collector: every spelling ─────────────────────────────────────

class CollectImportNamesTest(unittest.TestCase):
    """The collector must resolve absolute, relative, from-import, and
    aliased spellings — the review found it copy-pasted and untested
    despite a documented from-import bug in its history."""

    def test_absolute_import(self):
        names = ssh.collect_import_names(
            _parse("import api.routers.chat_ws\n"), "api.services.x")
        self.assertIn("api.routers.chat_ws", names)

    def test_aliased_import(self):
        names = ssh.collect_import_names(
            _parse("import api.prompt_composer as pc\n"), "api.services.x")
        self.assertIn("api.prompt_composer", names)

    def test_from_import_records_both_module_and_child(self):
        # Bug history: only `X` was recorded for `from X import Y`, so an
        # injected `from api.routers import extract` passed the gate.
        names = ssh.collect_import_names(
            _parse("from api.routers import extract\n"), "api.services.x")
        self.assertIn("api.routers", names)
        self.assertIn("api.routers.extract", names)

    def test_relative_from_import(self):
        # In api/services/x.py: `from ..routers import extract`
        names = ssh.collect_import_names(
            _parse("from ..routers import extract\n"), "api.services.x")
        self.assertIn("api.routers.extract", names)

    def test_relative_dot_import(self):
        # In api/services/x.py: `from . import trip_repository`
        names = ssh.collect_import_names(
            _parse("from . import trip_repository\n"), "api.services.x")
        self.assertIn("api.services.trip_repository", names)

    def test_relative_from_module_import_name(self):
        # In api/llm_interview.py: `from .api import chat`
        names = ssh.collect_import_names(
            _parse("from .api import chat\n"), "api.llm_interview")
        self.assertIn("api.api", names)
        self.assertIn("api.api.chat", names)

    def test_aliased_from_import(self):
        names = ssh.collect_import_names(
            _parse("from api.routers import chat_ws as ws\n"),
            "api.services.x")
        # alias target name, not the alias, is what matters
        self.assertIn("api.routers.chat_ws", names)

    def test_star_import_records_module_only(self):
        names = ssh.collect_import_names(
            _parse("from api.routers.extract import *\n"), "api.services.x")
        self.assertIn("api.routers.extract", names)
        self.assertNotIn("api.routers.extract.*", names)


class CollectModuleImportsSplitTest(unittest.TestCase):
    """Module-level vs function-level vs dynamic-literal separation —
    the mechanism behind the sanctioned-lazy-edge design in the
    trip_draft gate."""

    SRC = """
        import api.routers.extract

        class C:
            from api import memory_echo

        def lazy():
            from .api import chat
            mod = __import__("api.routers.chat_ws")

        async def lazy2():
            import importlib
            importlib.import_module("api.prompt_composer")
    """

    def test_split(self):
        got = ssh.collect_module_imports(_parse(self.SRC), "api.llm_interview")
        # class-body imports execute at import time → module-level
        self.assertIn("api.routers.extract", got.module_level)
        self.assertIn("api.memory_echo", got.module_level)
        self.assertNotIn("api.api", got.module_level)
        # function bodies → lazy
        self.assertIn("api.api", got.function_level)
        self.assertIn("api.api.chat", got.function_level)
        self.assertIn("importlib", got.function_level)
        # dynamic literals collected regardless of nesting
        self.assertIn("api.routers.chat_ws", got.dynamic_literal)
        self.assertIn("api.prompt_composer", got.dynamic_literal)

    def test_dynamic_import_aliased_importlib(self):
        got = ssh.collect_module_imports(_parse("""
            import importlib as il
            def f():
                il.import_module("api.routers.chat_ws")
        """), "api.services.x")
        self.assertIn("api.routers.chat_ws", got.dynamic_literal)

    def test_dynamic_import_bare_import_module(self):
        got = ssh.collect_module_imports(_parse("""
            from importlib import import_module
            def f():
                import_module("api.prompt_composer")
        """), "api.services.x")
        self.assertIn("api.prompt_composer", got.dynamic_literal)

    def test_computed_dynamic_import_not_detectable(self):
        # Documented limitation: non-literal args cannot be proven
        # statically. This test pins the limitation so nobody assumes
        # coverage the helper does not provide.
        got = ssh.collect_module_imports(_parse("""
            def f(name):
                __import__(name)
        """), "api.services.x")
        self.assertEqual(got.dynamic_literal, [])


class ViolatesForbiddenTest(unittest.TestCase):
    def test_exact_and_prefix_match(self):
        self.assertEqual(
            ssh.violates_forbidden("api.routers.chat_ws", _FORBIDDEN),
            "api.routers.chat_ws")
        self.assertEqual(
            ssh.violates_forbidden("api.routers.chat_ws.helper", _FORBIDDEN),
            "api.routers.chat_ws")

    def test_no_false_prefix_match_on_name_fragment(self):
        # "api.routers.chat_wsx" is NOT under the chat_ws prefix.
        self.assertIsNone(
            ssh.violates_forbidden("api.routers.chat_wsx", _FORBIDDEN))

    def test_allowed_override_wins(self):
        self.assertIsNone(ssh.violates_forbidden(
            "api.prompt_composer", _FORBIDDEN,
            allowed_overrides=("api.prompt_composer",)))


# ── Negative fixtures: the walker CAN fail ───────────────────────────────

class _FixtureWalkBase(unittest.TestCase):
    """Temp-dir project roots handed to the walker. Never touches
    production source."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, rel: str, src: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(src), encoding="utf-8")
        return p

    def edge_violations(self, result: ssh.WalkResult):
        return [(p, c, f) for p, c in result.edges
                if (f := ssh.violates_forbidden(c, _FORBIDDEN))]

    def dynamic_violations(self, result: ssh.WalkResult):
        return [(p, lit, f) for p, lit in result.dynamic_edges
                if (f := ssh.violates_forbidden(lit, _FORBIDDEN))]


class NegativeFixtureTest(_FixtureWalkBase):
    """Required Phase 6.3 fixtures — each detected for the EXPECTED
    reason. If any of these stops failing, the gates are decorative."""

    def test_direct_forbidden_import_detected(self):
        start = self.write("pkg/a.py", """
            from api.routers import chat_ws
        """)
        result = ssh.walk_import_graph(start, server_code=self.root)
        bad = self.edge_violations(result)
        self.assertTrue(bad, "direct forbidden import went undetected")
        self.assertIn(("pkg.a", "api.routers.chat_ws", "api.routers.chat_ws"),
                      bad)

    def test_transitive_forbidden_import_detected(self):
        # A imports B (clean-looking); B imports chat_ws.
        start = self.write("pkg/a.py", """
            from pkg import b
        """)
        self.write("pkg/b.py", """
            import api.routers.chat_ws
        """)
        self.write("pkg/__init__.py", "")
        result = ssh.walk_import_graph(start, server_code=self.root)
        bad = self.edge_violations(result)
        self.assertTrue(bad, "transitive forbidden import went undetected")
        self.assertIn(("pkg.b", "api.routers.chat_ws", "api.routers.chat_ws"),
                      bad)
        # And the walk really did pass through B.
        self.assertIn("pkg.b", result.visited)

    def test_dunder_import_literal_detected(self):
        start = self.write("pkg/a.py", """
            def sneak():
                return __import__("api.routers.chat_ws")
        """)
        result = ssh.walk_import_graph(start, server_code=self.root)
        bad = self.dynamic_violations(result)
        self.assertTrue(bad, '__import__("api.routers.chat_ws") undetected')
        self.assertIn(("pkg.a", "api.routers.chat_ws", "api.routers.chat_ws"),
                      bad)

    def test_importlib_import_module_literal_detected(self):
        start = self.write("pkg/a.py", """
            import importlib
            def sneak():
                return importlib.import_module("api.prompt_composer")
        """)
        result = ssh.walk_import_graph(start, server_code=self.root)
        bad = self.dynamic_violations(result)
        self.assertTrue(
            bad, 'importlib.import_module("api.prompt_composer") undetected')
        self.assertIn(("pkg.a", "api.prompt_composer", "api.prompt_composer"),
                      bad)

    def test_clean_module_produces_no_violations(self):
        # The other half of the ritual: a clean tree must PASS.
        start = self.write("pkg/a.py", """
            import json
            from pkg import b
        """)
        self.write("pkg/b.py", "import re\n")
        self.write("pkg/__init__.py", "")
        result = ssh.walk_import_graph(start, server_code=self.root)
        self.assertEqual(self.edge_violations(result), [])
        self.assertEqual(self.dynamic_violations(result), [])


class ModuleLevelFollowModeTest(_FixtureWalkBase):
    """follow="module_level" must NOT walk through lazy edges (the
    sanctioned llm_interview → api.api pattern) but must still surface
    the lazy edge itself for separate policing."""

    def test_lazy_edge_not_followed_but_recorded(self):
        start = self.write("pkg/a.py", """
            def lazy():
                from pkg import hot
        """)
        # pkg/hot.py module-level-imports a forbidden module; it must NOT
        # be reached by a module-level-only walk from a.
        self.write("pkg/hot.py", "import api.routers.chat_ws\n")
        self.write("pkg/__init__.py", "")
        result = ssh.walk_import_graph(
            start, server_code=self.root, follow="module_level")
        self.assertNotIn("pkg.hot", result.visited)
        self.assertEqual(self.edge_violations(result), [])
        self.assertIn(("pkg.a", "pkg.hot"), result.function_edges)

    def test_all_mode_does_follow_lazy_edges(self):
        start = self.write("pkg/a.py", """
            def lazy():
                from pkg import hot
        """)
        self.write("pkg/hot.py", "import api.routers.chat_ws\n")
        self.write("pkg/__init__.py", "")
        result = ssh.walk_import_graph(start, server_code=self.root,
                                       follow="all")
        self.assertIn("pkg.hot", result.visited)
        self.assertTrue(self.edge_violations(result))

    def test_unbounded_depth_reaches_deep_chain(self):
        # a → b1 → … → b6 → chat_ws: deeper than the old depth-4 bound.
        start = self.write("pkg/a.py", "from pkg import b1\n")
        for i in range(1, 6):
            self.write(f"pkg/b{i}.py", f"from pkg import b{i + 1}\n")
        self.write("pkg/b6.py", "import api.routers.chat_ws\n")
        self.write("pkg/__init__.py", "")
        result = ssh.walk_import_graph(start, server_code=self.root,
                                       max_depth=None)
        self.assertTrue(self.edge_violations(result),
                        "unbounded walk missed a depth-7 forbidden edge")

    def test_import_cycle_terminates(self):
        start = self.write("pkg/a.py", "from pkg import b\n")
        self.write("pkg/b.py", "from pkg import a\n")
        self.write("pkg/__init__.py", "")
        result = ssh.walk_import_graph(start, server_code=self.root,
                                       max_depth=None)
        self.assertEqual({"pkg.a", "pkg.b", "pkg"} & result.visited,
                         {"pkg.a", "pkg.b", "pkg"})


class PathResolutionTest(unittest.TestCase):
    def test_real_repo_roundtrip(self):
        target = ssh.SERVER_CODE / "api" / "services" / "trip_draft.py"
        if not target.is_file():
            self.skipTest("trip_draft.py missing")
        dotted = ssh.module_path_to_dotted(target)
        self.assertEqual(dotted, "api.services.trip_draft")
        self.assertEqual(ssh.resolve_dotted_to_path(dotted), target)

    def test_unresolvable_returns_none(self):
        self.assertIsNone(ssh.resolve_dotted_to_path("no.such.module"))
        self.assertIsNone(ssh.resolve_dotted_to_path(""))


# ── JS comment stripper ──────────────────────────────────────────────────

class StripJsCommentsTest(unittest.TestCase):
    """Required Phase 6.4 cases. The old regex stripper treated the "//"
    inside "http://…" as a comment and blinded every scan to EOL."""

    def test_banned_token_after_url_stays_visible(self):
        js = 'var base = "http://localhost:8000"; runtime71.poke();\n'
        out = ssh.strip_js_comments(js)
        self.assertIn("runtime71", out)

    def test_url_string_itself_stays_intact(self):
        js = 'var base = "http://localhost:8000";\n'
        self.assertIn('"http://localhost:8000"', ssh.strip_js_comments(js))

    def test_banned_token_in_line_comment_removed(self):
        js = "var a = 1; // mentions runtime71 legally in docs\n"
        self.assertNotIn("runtime71", ssh.strip_js_comments(js))

    def test_banned_token_in_block_comment_removed(self):
        js = "/* runtime71 is banned here */ var a = 1;\n"
        out = ssh.strip_js_comments(js)
        self.assertNotIn("runtime71", out)
        self.assertIn("var a = 1;", out)

    def test_escaped_quote_does_not_terminate_early(self):
        js = 'var s = "he said \\"http://x\\" loudly"; runtime71;\n'
        out = ssh.strip_js_comments(js)
        self.assertIn("runtime71", out)
        self.assertIn('\\"http://x\\"', out)

    def test_single_quote_string_with_url(self):
        js = "var s = 'http://x.test/y'; runtime71;\n"
        out = ssh.strip_js_comments(js)
        self.assertIn("runtime71", out)
        self.assertIn("'http://x.test/y'", out)

    def test_template_literal_does_not_blind_rest_of_line(self):
        js = "var t = `ws://x/${id}//path`; runtime71;\n"
        out = ssh.strip_js_comments(js)
        self.assertIn("runtime71", out)
        self.assertIn("`ws://x/${id}//path`", out)

    def test_comment_after_string_still_removed(self):
        js = 'var u = "http://x"; // trailing runtime71 note\n'
        out = ssh.strip_js_comments(js)
        self.assertIn('"http://x"', out)
        self.assertNotIn("runtime71", out)

    def test_regex_literal_with_quote_char_does_not_open_string(self):
        # travel-documenter.js:48-49 does .replace(/"/g, …).replace(/'/g, …)
        js = ('s.replace(/"/g, "&quot;").replace(/\'/g, "&#39;");\n'
              "// comment with runtime71\nvar a = 1;\n")
        out = ssh.strip_js_comments(js)
        self.assertNotIn("runtime71", out)
        self.assertIn('"&quot;"', out)
        self.assertIn("var a = 1;", out)

    def test_regex_literal_with_slashes_does_not_open_comment(self):
        js = 'var x = url.replace(/\\/$/, ""); runtime71;\n'
        out = ssh.strip_js_comments(js)
        self.assertIn("runtime71", out)
        self.assertIn('/\\/$/', out)

    def test_division_is_not_regex(self):
        js = "var half = total / 2; // runtime71 comment\n"
        out = ssh.strip_js_comments(js)
        self.assertIn("total / 2;", out)
        self.assertNotIn("runtime71", out)

    def test_multiline_block_comment_removed(self):
        js = "var a = 1;\n/* line1 runtime71\nline2 */\nvar b = 2;\n"
        out = ssh.strip_js_comments(js)
        self.assertNotIn("runtime71", out)
        self.assertIn("var a = 1;", out)
        self.assertIn("var b = 2;", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
