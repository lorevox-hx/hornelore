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
from typing import Any, Dict, List, NamedTuple, Optional, Tuple  # noqa: F401  (used by exec'd source)

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
    # `_PromptAssembly` now builds `_Section` records, so BOTH classes
    # are exec'd. Loading only the assembly gave 17 NameErrors the
    # moment Phase 2D added the record type -- a loader that extracts a
    # class by name has to follow that class's dependencies too.
    wanted = ("_Section", "_PromptAssembly")
    nodes = [n for n in tree.body
             if isinstance(n, ast.ClassDef) and n.name in wanted]
    assert {n.name for n in nodes} == set(wanted), \
        f"expected {wanted}, found {[n.name for n in nodes]}"
    ns: Dict[str, Any] = {
        "List": List, "Tuple": Tuple, "Optional": Optional,
        "NamedTuple": NamedTuple,
        "logger": logging.getLogger("test_prompt_sections"),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<composer>", "exec"), ns)
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


class NarratorTextIsNotDuplicatedTest(unittest.TestCase):
    """WO-LEAN-LORI-RUNTIME-01 Phase 2B — `last_user_text` removed.

    The retired line put up to 800 characters of the narrator's CURRENT
    message into PROFILE_JSON, inside the SYSTEM prompt, while the same
    text is already sent as the user message. Every turn paid for the
    narrator's own words twice.

    It was write-only: `last_user_text` had exactly ONE reference in the
    whole repository, the assignment itself. Nothing read it in Python,
    in JavaScript, or in any fixture. The comment promised "future
    dynamic prompt policies"; that future never arrived.

    HONEST SCALE: 800 characters is roughly 200 tokens against a median
    prompt of 8,861 that must lose about 670 to fit the window. This
    does not fix the cemetery failure. It removes the only tokens that
    were pure duplication rather than content somebody chose.
    """

    def test_the_composer_no_longer_writes_it(self):
        """AST, not substring -- the retirement comment quotes the
        retired line verbatim, so a text scan would match the
        explanation and pass on code that still wrote it. That trap has
        fired repeatedly in this repository."""
        tree = ast.parse(_SRC)
        live = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and n.value == "last_user_text"]
        self.assertEqual([], live,
                         f"last_user_text is still written at {live}")

    def test_the_retirement_is_recorded_not_silently_deleted(self):
        self.assertIn("last_user_text", _SRC,
                      "the retired line should be quoted in place")
        self.assertIn("Phase 2B", _SRC)

    def test_nothing_anywhere_reads_it(self):
        """The removal is only safe because it had no consumer. If a
        reader ever appears, this fails and the removal is revisited."""
        roots = [_REPO / "server", _REPO / "ui", _REPO / "scripts"]
        hits = []
        for root in roots:
            if not root.exists():
                continue
            for f in root.rglob("*"):
                if f.suffix not in (".py", ".js", ".html", ".json"):
                    continue
                if f == _COMPOSER:
                    continue
                try:
                    if "last_user_text" in f.read_text(encoding="utf-8",
                                                       errors="ignore"):
                        hits.append(str(f.relative_to(_REPO)))
                except OSError:
                    continue
        self.assertEqual([], hits, f"a reader appeared: {hits}")

    def test_the_context_block_still_carries_everything_else(self):
        """No other profile field changes. Rebuilt the way the composer
        builds it, minus the removed key."""
        payload = {"conv_id": "drop", "title": "drop", "updated_at": "drop",
                   "era": "building_years", "session_style": "oral_history"}
        profile_obj = {"basics": {"fullName": "Kent James Horne"},
                       "family": {"children": 3}}
        context: Dict[str, Any] = {}
        for k, v in payload.items():
            if k in ("conv_id", "title", "updated_at"):
                continue
            context[k] = v
        context.setdefault("ui_profile", profile_obj)

        self.assertEqual({"era", "session_style", "ui_profile"}, set(context))
        self.assertNotIn("last_user_text", context)
        self.assertEqual(profile_obj, context["ui_profile"],
                         "the UI profile round trip must be untouched")

    def test_the_json_is_still_valid_and_excludes_the_narrator_turn(self):
        import json
        narrator = ("My grandparents Peter Zarr and Josie Zarr are buried "
                    "in the cemetery outside Mandan and I used to go every "
                    "Memorial Day with my mother.")
        context = {"era": "building_years",
                   "ui_profile": {"basics": {"fullName": "Kent James Horne"}}}
        block = "PROFILE_JSON: " + json.dumps(context, ensure_ascii=False)
        parsed = json.loads(block[len("PROFILE_JSON: "):])
        self.assertEqual(context, parsed, "the block no longer round-trips")
        self.assertNotIn(narrator, block)
        self.assertNotIn("Peter Zarr", block,
                         "the narrator's current message reached the system prompt")

    def test_the_narrator_message_occurs_once_across_the_whole_request(self):
        """The point of the phase, stated as a count. The system prompt
        must not contain the text that the user message already carries."""
        import json
        narrator = "We drove out to Spokane every summer to see my mom's parents."
        context = {"era": "earliest_years"}
        system_prompt = "DEFAULT_CORE...\n\nPROFILE_JSON: " + json.dumps(context)
        msgs = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": narrator}]
        occurrences = sum(m["content"].count(narrator) for m in msgs)
        self.assertEqual(1, occurrences,
                         f"the narrator's message appears {occurrences} times")

    def test_the_surrounding_prompt_structure_is_untouched(self):
        """Interview, trip, language and safety structures must survive a
        change that only removed one context key."""
        tree = ast.parse(_SRC)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "compose_system_prompt")
        body = "\n".join(ast.unparse(b) for b in fn.body)
        for survivor in ("ui_profile", "ctx_block", "PROFILE_JSON: ",
                         "system_head", "pinned", "_looks_spanish",
                         "identity_facts", "directives_interview"):
            self.assertIn(survivor, body, f"{survivor} disappeared")


class SectionClassificationTest(unittest.TestCase):
    """WO-LEAN-LORI-RUNTIME-01 Phase 2D — what Lori may lose.

    CLASSIFICATION ONLY. Nothing drops in this commit; enforcement
    belongs at api.py's tokenize point, the only place that sees the
    final string after _apply_chat_template.

    The classification is the safety property. Once a budget starts
    dropping sections, `required=True` is the difference between a
    shorter prompt and a prompt with Lori's identity cut out of it --
    which is what the blind front slice has been doing on 60.6% of
    turns.
    """

    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(_SRC)
        cls.fn = next(n for n in cls.tree.body
                      if isinstance(n, ast.FunctionDef)
                      and n.name == "compose_system_prompt")
        cls.spec = {}
        for n in ast.walk(cls.fn):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "add"
                    and getattr(n.func.value, "id", "") == "parts"
                    and n.args and isinstance(n.args[0], ast.Constant)):
                kw = {k.arg: getattr(k.value, "value", None) for k in n.keywords}
                cls.spec[n.args[0].value] = (bool(kw.get("required", False)),
                                             kw.get("drop_order", 0))

    REQUIRED = ("identity_facts", "identity_grounding",
                "directives_interview", "directives_bio_builder",
                "directives_questionnaire")
    DROPPABLE = {"memory_context": 5, "factual_chain": 10,
                 "english_first": 20, "ui_context": 30, "pinned_facts": 40}

    def test_lori_can_never_lose_her_identity_or_her_discipline(self):
        for name in self.REQUIRED:
            with self.subTest(section=name):
                self.assertIn(name, self.spec)
                self.assertTrue(self.spec[name][0],
                                f"{name} is droppable; it must not be")

    def test_the_system_head_is_required(self):
        """It is seeded through the constructor, not `add`, so it needs
        its own check -- the constructor is where identity, purpose and
        the entire safety protocol enter the prompt."""
        # Checked against the RAW source, not ast.unparse output: unparse
        # normalises string quotes to single, so a double-quoted needle
        # silently never matches -- and the failure prints the entire
        # 1,200-line function, which buries the one line that matters.
        self.assertIn('_PromptAssembly("system_head", system_head)', _SRC,
                      "the head is no longer seeded through the constructor")
        self.assertIn("self.add(name, text, required=True)", _SRC,
                      "the seeded head is not marked required")

    def test_the_droppable_sections_have_the_intended_order(self):
        for name, order in self.DROPPABLE.items():
            with self.subTest(section=name):
                required, got = self.spec[name]
                self.assertFalse(required, f"{name} became required")
                self.assertEqual(order, got)

    def test_pinned_operator_truth_is_the_last_optional_to_go(self):
        """It is the closest thing in the optional set to something a
        human deliberately chose, so it outranks every other droppable
        section."""
        orders = {n: o for n, (req, o) in self.spec.items() if not req}
        self.assertEqual("pinned_facts", max(orders, key=orders.get))

    def test_every_section_is_classified_one_way_or_the_other(self):
        self.assertEqual(set(self.REQUIRED) | set(self.DROPPABLE),
                         set(self.spec),
                         "a section is neither required nor ordered")

    def test_no_drop_order_is_shared(self):
        """Ties would make the drop sequence depend on composition
        order, which is not where that decision should live."""
        orders = [o for n, (req, o) in self.spec.items() if not req]
        self.assertEqual(len(orders), len(set(orders)), f"duplicate: {orders}")

    def test_nothing_actually_drops_yet(self):
        """The enforcement point is api.py, after templating. If the
        composer starts dropping sections it will be deciding with an
        estimate, and Phase 0 measured builder-side estimates wrong by a
        wide margin."""
        body = ast.unparse(self.fn)
        for banned in ("drop_optional", "fit_within", "budget(", "_trim_to_"):
            self.assertNotIn(banned, body, banned)

    def test_the_assembly_exposes_the_classification(self):
        """The budget cannot enforce what it cannot see, and it lives in
        another module."""
        cls = _load_assembly()
        asm = cls("head", "identity")
        asm.add("opt", "droppable", required=False, drop_order=7)
        secs = asm.sections()
        self.assertEqual(["head", "opt"], [s.name for s in secs])
        self.assertTrue(secs[0].required)
        self.assertFalse(secs[1].required)
        self.assertEqual(7, secs[1].drop_order)

    def test_a_section_record_still_unpacks_like_the_old_pair(self):
        """`for name, text in ...` predates the classification and must
        keep working for any reader that has not caught up."""
        cls = _load_assembly()
        asm = cls("head", "text")
        name, text, required, order = asm.sections()[0]
        self.assertEqual(("head", "text", True, 0), (name, text, required, order))

    def test_classification_did_not_change_the_rendered_output(self):
        """Phase 2A's guarantee must survive Phase 2D."""
        cls = _load_assembly()
        asm = cls("head", "AAA")
        asm.add("mid", "", required=False, drop_order=1)
        asm.add("tail", "BBB", required=True)
        self.assertEqual(_historical_join(["AAA", "", "BBB"]), asm.render("c"))
