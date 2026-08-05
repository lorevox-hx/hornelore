"""WO-LEAN-LORI-RUNTIME-01 Phase 2A — named prompt sections, same output.

WHY THIS PHASE EXISTS
---------------------
`compose_system_prompt` is 1,223 lines that appended into a bare list and
joined it in three places. Nobody could say which section cost what, so
nobody could compact the expensive ones -- and the composed prompt now
overruns the model's 8,192-token window on the MEDIAN narrator turn.

Measured from api.log over 630 real turns: p50 8,861 tokens, p90 10,345,
max 12,656, and 382 of 630 (60.6%) over the window. The slice at
api.py:310 keeps the LAST 8,192 tokens, so what is discarded is the
FRONT -- exactly where Lori's identity, purpose and instructions sit.
api.py:305 already says so in its own comment: "it cuts the FRONT, where
a system prompt lives."

That is the cemetery answer. Lori was not ignoring her instructions; she
was never shown them.

WHAT THIS PHASE CHANGES: NOTHING ABOUT THE OUTPUT
-------------------------------------------------
Step one is measurement, and a measurement step that also changes
behaviour cannot be trusted -- any later regression would have two
candidate causes. `_PromptAssembly` records a NAME beside every section
and renders with the identical expression the three exits already used:

    "\\n\\n".join([p for p in parts if p.strip()]).strip()

Same strings, same order, same filter, same strip. The output is
byte-identical BY CONSTRUCTION. These tests exist because "by
construction" is a claim, and the whole point of this phase is that the
next phase can trust its baseline.

Sizes are reported in CHARACTERS, deliberately. Phase 0 established that
the only honest token count is taken at api.py:288 after
_apply_chat_template, because that is the only place that sees the final
string including the template's own tokens; a builder-side estimate was
wrong by a wide margin in the reconnaissance that produced this phase.
A wrong number here would be worse than none, because it is the number
the compaction work will steer by.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_prompt_sections
"""
from __future__ import annotations

import ast
import logging
import random
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401  (used by exec'd source)

_REPO = Path(__file__).resolve().parent.parent
_COMPOSER = _REPO / "server" / "code" / "api" / "prompt_composer.py"
_SRC = _COMPOSER.read_text(encoding="utf-8")


def _load_assembly():
    """Exec the real `_PromptAssembly` source, not a copy of it.

    The module itself imports the database layer and the whole server
    stack, which this test has no business loading to check a string
    join. Extracting the class by AST keeps the test honest -- it
    exercises the shipped code, and it cannot drift from it -- without
    dragging in torch.
    """
    tree = ast.parse(_SRC)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "_PromptAssembly")
    ns: Dict[str, Any] = {
        "List": List, "Tuple": Tuple, "Optional": Optional,
        "logger": logging.getLogger("test_prompt_sections"),
    }
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "<composer>", "exec"), ns)
    return ns["_PromptAssembly"]


_PromptAssembly = _load_assembly()


def _historical_join(parts: List[str]) -> str:
    """The exact expression the three exits used before Phase 2A.

    Copied verbatim from the pre-change source so the comparison is
    against what actually shipped, not against a paraphrase of it.
    """
    return "\n\n".join([p for p in parts if p.strip()]).strip()


class RenderIsByteIdenticalTest(unittest.TestCase):
    """The whole contract of this phase, stated as equality."""

    CASES = [
        [],
        ["only one"],
        ["head", "body", "tail"],
        ["head", "", "tail"],                  # empty in the middle
        ["", "", ""],                          # all empty
        ["   ", "\n", "\t"],                   # whitespace-only: dropped
        ["  leading and trailing  ", "x"],
        ["head", "   ", "tail"],
        ["a\n\nb", "c"],                       # internal blank lines survive
        ["\n\nleading blanks", "trailing blanks\n\n"],
        ["unicode — em dash, curly ’, ñ", "second"],
    ]

    def test_every_shape_renders_identically(self):
        for parts in self.CASES:
            with self.subTest(parts=parts):
                asm = _PromptAssembly()
                for i, t in enumerate(parts):
                    asm.add(f"s{i}", t)
                self.assertEqual(_historical_join(parts), asm.render("conv"))

    def test_the_seeded_constructor_matches_a_seeded_list(self):
        """`parts = [system_head]` became
        `parts = _PromptAssembly("system_head", system_head)`."""
        head = "SYSTEM HEAD"
        rest = ["one", "", "two"]
        asm = _PromptAssembly("system_head", head)
        for i, t in enumerate(rest):
            asm.add(f"s{i}", t)
        self.assertEqual(_historical_join([head] + rest), asm.render("conv"))

    def test_an_empty_seed_is_not_added_as_a_section(self):
        """The old code seeded the list unconditionally, but an empty
        head was then dropped by the render filter anyway. Both produce
        the same string; this pins that they still do."""
        asm = _PromptAssembly("system_head", "")
        asm.add("body", "text")
        self.assertEqual(_historical_join(["", "text"]), asm.render("conv"))
        self.assertEqual("text", asm.render("conv"))

    def test_none_is_treated_as_empty_not_as_a_crash(self):
        asm = _PromptAssembly()
        asm.add("a", "kept")
        asm.add("b", None)
        asm.add("c", "also kept")
        self.assertEqual("kept\n\nalso kept", asm.render("conv"))

    def test_randomised_equality(self):
        """Fuzzed, because the hand-written cases are the ones I thought
        of and the join has three separate behaviours (filter, join,
        strip) that interact at the edges."""
        rnd = random.Random(20260804)
        pool = ["", "   ", "\n", "text", "  padded  ", "a\n\nb", "ñ — ’"]
        for _ in range(300):
            parts = [rnd.choice(pool) for _ in range(rnd.randint(0, 7))]
            asm = _PromptAssembly()
            for i, t in enumerate(parts):
                asm.add(f"s{i}", t)
            self.assertEqual(_historical_join(parts), asm.render(""),
                             f"diverged on {parts!r}")


class MeasurementTest(unittest.TestCase):
    """Measurement is the deliverable, and it must not cost a turn."""

    def test_sections_are_named_and_ordered(self):
        asm = _PromptAssembly("head", "AAA")
        asm.add("body", "BBBB")
        asm.add("tail", "CC")
        self.assertEqual([("head", 3), ("body", 4), ("tail", 2)], asm.measure())

    def test_empty_sections_are_still_recorded(self):
        """An expensive section that renders empty on this turn is a
        fact worth seeing -- "why is identity_facts 0 chars" is exactly
        the question the compaction work needs to be able to ask."""
        asm = _PromptAssembly()
        asm.add("identity_facts", "")
        self.assertEqual([("identity_facts", 0)], asm.measure())

    def test_render_survives_a_logger_that_raises(self):
        cls = _load_assembly()

        class _Boom:
            def info(self, *a, **k):
                raise RuntimeError("logging is down")

        # rebind the logger the exec'd class closed over
        cls.__init__.__globals__["logger"] = _Boom()
        asm = cls("head", "text")
        self.assertEqual("text", asm.render("conv"))


class TheComposerUsesItEverywhereTest(unittest.TestCase):
    """Structural: no exit may still hand-roll the join, and no other
    function in the module may have been disturbed."""

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(_SRC)
        cls.fn = next(n for n in cls.tree.body
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "compose_system_prompt")

    def test_no_bare_append_remains_in_the_composer(self):
        left = [n.lineno for n in ast.walk(self.fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "append"
                and getattr(n.func.value, "id", "") == "parts"]
        self.assertEqual([], left, f"bare parts.append at {left}")

    def test_every_exit_renders_through_the_assembly(self):
        returns = [ast.unparse(n) for n in ast.walk(self.fn)
                   if isinstance(n, ast.Return) and n.value is not None]
        joins = [r for r in returns if "join" in r]
        self.assertEqual([], joins,
                         f"an exit still hand-rolls the join: {joins}")
        renders = [r for r in returns if "parts.render" in r]
        self.assertEqual(3, len(renders),
                         f"expected 3 rendered exits, got {renders}")

    def test_all_ten_sections_are_named(self):
        names = []
        for n in ast.walk(self.fn):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "add"
                    and getattr(n.func.value, "id", "") == "parts"
                    and n.args and isinstance(n.args[0], ast.Constant)):
                names.append(n.args[0].value)
        for expected in ("ui_context", "pinned_facts", "identity_facts",
                         "identity_grounding", "english_first",
                         "factual_chain", "directives_interview",
                         "directives_bio_builder", "directives_questionnaire",
                         "memory_context"):
            self.assertIn(expected, names)
        self.assertEqual(len(names), len(set(names)),
                         f"duplicate section name: {names}")

    def test_other_functions_still_use_plain_lists(self):
        """The module has 15 other `parts.append` sites in unrelated
        functions. This phase must not have reached them."""
        outside = [n.lineno for n in ast.walk(self.tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "append"
                   and getattr(n.func.value, "id", "") == "parts"
                   and not (self.fn.lineno <= n.lineno <= self.fn.end_lineno)]
        self.assertEqual(15, len(outside),
                         f"expected 15 untouched append sites, found {len(outside)}")

    def test_the_composer_reports_no_token_estimate(self):
        """Phase 0: the only honest token count is at api.py:288, after
        _apply_chat_template. A builder-side estimate was measurably
        wrong, and this is the number the compaction work steers by."""
        i = _SRC.index("class _PromptAssembly")
        block = _SRC[i:_SRC.index("def compose_system_prompt")]
        body = "\n".join(l for l in block.splitlines()
                         if not l.strip().startswith("#"))
        for banned in ("token_estimate", "est_tokens", "// 4", "/ 4",
                       "approx_tokens"):
            self.assertNotIn(banned, body, banned)


if __name__ == "__main__":
    unittest.main(verbosity=2)
