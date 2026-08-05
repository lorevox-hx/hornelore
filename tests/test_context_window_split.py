"""WO-LEAN-LORI-RUNTIME-01 Phase 2C — chat and extraction windows separated.

WHAT WAS WRONG
--------------
One constant, `MAX_CONTEXT_WINDOW`, governed two unrelated policies:

  * how much of a CHAT prompt survives before the front is sliced off
    (api.py `_generate_text`, api.py `chat_stream`, chat_ws), and
  * the fail-closed ceiling the bounded EXTRACTION budget refuses against
    (api.py `_extraction_budget_for` -> extraction_budget).

Those are different questions with opposite failure modes. Chat truncates
and carries on; extraction refuses and records a durable failure. Coupling
them meant that raising the chat window -- to stop discarding the front of
the prompt, where Lori's identity and instructions live -- would silently
loosen extraction's refusal threshold. That is a behaviour change on a
lane nobody was working on, invisible in the diff, and directly contrary
to Phase 5, whose entire premise was making the extraction prompt fit a
fixed window.

WHY 8,192 WAS NOT A CEILING
---------------------------
`.env.example` asserted that "MAX_CONTEXT_WINDOW stays 8192 and is NOT a
tuning option -- Hornelore must operate within the tested VRAM envelope of
the existing machine." That reads as a measurement and is not one. The
envelope it appeals to (WO-OPS-VRAM-VISIBILITY-01, 2026-05-03) was
measured WITH the 8,192 cap already in force; nothing above 8,192 has ever
been run on this machine. Llama 3.1 8B is designed for 128,000 tokens.
8,192 was a conservative deployment choice that a comment later froze into
a rule, and the `.env.example` text is corrected in the same commit.

THIS COMMIT CHANGES NO BEHAVIOUR
--------------------------------
Both windows default to 8,192, and both fall back to the legacy
`MAX_CONTEXT_WINDOW` when it is set -- which it is, in the live `.env` --
so an existing deployment is unaffected. The point is only that the two
numbers become separately nameable, so the chat one can later be raised on
its own evidence: VRAM *and* latency, since prefill attention is quadratic
and nobody has yet timed a 12K turn on this laptop.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_context_window_split
"""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SERVER = _REPO / "server" / "code"
_API = _SERVER / "api" / "api.py"
_WS = _SERVER / "api" / "routers" / "chat_ws.py"
_BUDGET = _SERVER / "api" / "services" / "extraction_budget.py"

_API_SRC = _API.read_text(encoding="utf-8")
_WS_SRC = _WS.read_text(encoding="utf-8")


def _resolve(env: dict) -> dict:
    """Execute the real resolution block from api.py under a given env.

    Executing the shipped source rather than restating the precedence
    rules is the point: a restatement can agree with itself while
    disagreeing with production.
    """
    start = _API_SRC.index("_LEGACY_CONTEXT_WINDOW_ENV =")
    end = _API_SRC.index("# The ambiguous name is deliberately NOT rebound")
    block = _API_SRC[start:end]
    saved = dict(os.environ)
    try:
        for k in ("MAX_CONTEXT_WINDOW", "MAX_CHAT_PROMPT_TOKENS",
                  "MAX_EXTRACTION_CONTEXT_WINDOW"):
            os.environ.pop(k, None)
        os.environ.update(env)
        ns = {"os": os, "print": lambda *a, **k: None}
        exec(block, ns)
        return {"chat": ns["MAX_CHAT_PROMPT_TOKENS"],
                "extraction": ns["MAX_EXTRACTION_CONTEXT_WINDOW"]}
    finally:
        os.environ.clear()
        os.environ.update(saved)


class ResolutionPreservesTodaysBehaviourTest(unittest.TestCase):
    """The commit must be a no-op on the running deployment."""

    def test_nothing_set_gives_8192_and_8192(self):
        self.assertEqual({"chat": 8192, "extraction": 8192}, _resolve({}))

    def test_the_live_env_today_gives_8192_and_8192(self):
        """`.env` carries MAX_CONTEXT_WINDOW=8192. This deployment must
        not move because the constant was split."""
        self.assertEqual({"chat": 8192, "extraction": 8192},
                         _resolve({"MAX_CONTEXT_WINDOW": "8192"}))

    def test_the_legacy_value_still_feeds_both_when_it_is_all_that_is_set(self):
        """Deprecated does not mean ignored. Someone who set only the old
        name keeps exactly the behaviour they had."""
        self.assertEqual({"chat": 12288, "extraction": 12288},
                         _resolve({"MAX_CONTEXT_WINDOW": "12288"}))


class TheTwoWindowsMoveIndependentlyTest(unittest.TestCase):
    """The whole point of the phase."""

    def test_chat_can_be_raised_while_extraction_stays_pinned(self):
        """The approved candidate: chat 12,288, extraction 8,192. If this
        fails, raising the chat window silently loosens extraction's
        fail-closed ceiling -- the coupling this phase removed."""
        got = _resolve({"MAX_CONTEXT_WINDOW": "8192",
                        "MAX_CHAT_PROMPT_TOKENS": "12288"})
        self.assertEqual({"chat": 12288, "extraction": 8192}, got)

    def test_extraction_can_be_raised_while_chat_stays_pinned(self):
        got = _resolve({"MAX_CONTEXT_WINDOW": "8192",
                        "MAX_EXTRACTION_CONTEXT_WINDOW": "10240"})
        self.assertEqual({"chat": 8192, "extraction": 10240}, got)

    def test_a_specific_setting_beats_the_legacy_one(self):
        got = _resolve({"MAX_CONTEXT_WINDOW": "4096",
                        "MAX_CHAT_PROMPT_TOKENS": "12288",
                        "MAX_EXTRACTION_CONTEXT_WINDOW": "8192"})
        self.assertEqual({"chat": 12288, "extraction": 8192}, got)


class TheAmbiguousNameIsGoneFromCodeTest(unittest.TestCase):
    """Deprecating a name that is still in scope deprecates nothing."""

    def test_no_module_constant_named_MAX_CONTEXT_WINDOW(self):
        """It must not be rebound as an alias. An alias would let any
        future line reach for it and be silently wrong about which lane
        it meant -- which is the defect, not the spelling."""
        tree = ast.parse(_API_SRC)
        bound = [n.lineno for n in tree.body
                 if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", "") == "MAX_CONTEXT_WINDOW"
                         for t in n.targets)]
        self.assertEqual([], bound, f"rebound at {bound}")

    def test_no_executable_use_of_the_old_identifier_anywhere(self):
        """AST, not substring: the explanatory comment and the
        deprecation message both name it, and a text scan would match
        those and pass on code that still used it."""
        for label, src in (("api.py", _API_SRC), ("chat_ws.py", _WS_SRC)):
            with self.subTest(file=label):
                tree = ast.parse(src)
                used = sorted({n.lineno for n in ast.walk(tree)
                               if isinstance(n, ast.Name)
                               and n.id == "MAX_CONTEXT_WINDOW"})
                self.assertEqual([], used, f"{label}: still used at {used}")

    def test_the_legacy_env_var_is_still_read_and_announced(self):
        """It is deprecated, not deleted -- an existing .env must keep
        working, and the operator must be told why it still matters."""
        self.assertIn('os.getenv("MAX_CONTEXT_WINDOW")', _API_SRC)
        self.assertIn("DEPRECATED", _API_SRC)


class EachLaneUsesItsOwnWindowTest(unittest.TestCase):
    """Structural: which constant each call site actually reads."""

    def test_the_extraction_budget_reads_the_extraction_window(self):
        tree = ast.parse(_API_SRC)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_extraction_budget_for")
        body = ast.unparse(fn)
        self.assertIn("window=MAX_EXTRACTION_CONTEXT_WINDOW", body)
        self.assertNotIn("MAX_CHAT_PROMPT_TOKENS", body,
                         "the extraction budget must not read the chat window")

    def test_no_chat_lane_slices_tokens_any_more(self):
        """REWRITTEN by Phase 4A, 2026-08-04.

        The retired assertion was:

            self.assertEqual(2, _API_SRC.count("MAX_CHAT_PROMPT_TOKENS:] for k, v"))
            self.assertEqual(1, _WS_SRC.count("MAX_CHAT_PROMPT_TOKENS:] for k, v"))

        It counted the blind front-slices and required them to be
        present, which was correct while they were the mechanism. Phase
        4A removes all three: the prompt is now fitted on MESSAGES before
        the template, so no chat lane cuts tokens at all.

        Inverting rather than deleting, because the property still worth
        holding is which window each lane spends -- and now the strongest
        statement of that is that the chat lanes spend it by fitting
        rather than by cutting.
        """
        self.assertEqual(0, _API_SRC.count("MAX_CHAT_PROMPT_TOKENS:] for k, v"),
                         "api.py still blind-slices a chat prompt")
        self.assertEqual(0, _WS_SRC.count("MAX_CHAT_PROMPT_TOKENS:] for k, v"),
                         "chat_ws still blind-slices a chat prompt")

    def test_every_chat_lane_fits_against_the_chat_window(self):
        """The replacement mechanism, and it must name the CHAT window.

        This is the same property the retired test protected -- a chat
        lane must not spend extraction's budget -- restated against the
        code that now does the work.
        """
        for label, src, needle in (
                ("api.py", _API_SRC, "limit=MAX_CHAT_PROMPT_TOKENS"),
                ("chat_ws.py", _WS_SRC, "limit=MAX_CHAT_PROMPT_TOKENS")):
            with self.subTest(file=label):
                self.assertIn(needle, src,
                              f"{label} does not fit against the chat window")
                self.assertNotIn("limit=MAX_EXTRACTION_CONTEXT_WINDOW", src,
                                 f"{label} fits a chat prompt against "
                                 f"extraction's window")

    def test_the_truncation_CONDITION_reads_the_chat_window_too(self):
        """ADDED after mutation M2 survived. The original test asserted
        only that the SLICE names the chat window, so a mutant could test
        `n_tokens > MAX_EXTRACTION_CONTEXT_WINDOW` and then slice to
        MAX_CHAT_PROMPT_TOKENS -- the condition and the cut disagreeing
        about which lane's budget is being spent, which is precisely the
        class of defect this phase exists to remove. Both halves must
        name the same window."""
        self.assertIn("elif n_tokens > MAX_CHAT_PROMPT_TOKENS:", _API_SRC)
        self.assertIn('if inputs["input_ids"].shape[-1] > MAX_CHAT_PROMPT_TOKENS:',
                      _API_SRC)
        self.assertIn('if inputs["input_ids"].shape[-1] > MAX_CHAT_PROMPT_TOKENS:',
                      _WS_SRC)

    def test_the_extraction_window_never_leaks_into_a_chat_lane(self):
        """WHERE it may appear, not how often.

        The first cut asserted a count of exactly two -- definition plus
        the budget call -- and failed on the real file, because the
        deprecation message names it as well. That was the test being
        wrong, and a bare count would have been brittle regardless: a
        third harmless module-level mention would break it while a real
        leak into a chat function might not change the total.

        What matters is the enclosing scope. Module level is fine
        (definition, deprecation notice); `_extraction_budget_for` is
        fine; anything else is the extraction window reaching a lane
        that truncates instead of refusing."""
        tree = ast.parse(_API_SRC)
        owners = [(n.lineno, n.end_lineno, n.name) for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

        def owner_of(line):
            best = None
            for a, b, name in owners:
                if a <= line <= b and (best is None or a > best[0]):
                    best = (a, b, name)
            return best[2] if best else None

        seen = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and n.id == "MAX_EXTRACTION_CONTEXT_WINDOW":
                seen.setdefault(owner_of(n.lineno), []).append(n.lineno)
        self.assertEqual(
            {None, "_extraction_budget_for"}, set(seen),
            f"the extraction window appears in unexpected scopes: {seen}")
        self.assertNotIn("MAX_EXTRACTION_CONTEXT_WINDOW", _WS_SRC,
                         "the extraction window reached the chat WebSocket")

    def test_the_websocket_guard_plans_against_the_chat_window(self):
        self.assertIn("min(_prompt_tokens, MAX_CHAT_PROMPT_TOKENS)", _WS_SRC)

    def test_chat_ws_imports_only_the_chat_window(self):
        tree = ast.parse(_WS_SRC)
        names = []
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("api"):
                names += [a.name for a in n.names]
        self.assertIn("MAX_CHAT_PROMPT_TOKENS", names)
        self.assertNotIn("MAX_CONTEXT_WINDOW", names)
        self.assertNotIn("MAX_EXTRACTION_CONTEXT_WINDOW", names,
                         "the chat lane has no business with the extraction window")

    def test_the_budget_module_still_reads_no_window_itself(self):
        """It receives the window; it must never resolve one. Two readers
        could disagree, and then the guard and the enforcement would be
        defending different numbers."""
        src = _BUDGET.read_text(encoding="utf-8")
        for name in ("MAX_CONTEXT_WINDOW", "MAX_CHAT_PROMPT_TOKENS",
                     "MAX_EXTRACTION_CONTEXT_WINDOW"):
            self.assertNotIn(f'getenv("{name}"', src)
            self.assertNotIn(f"getenv('{name}'", src)


class TheCorrectedPolicyIsRecordedTest(unittest.TestCase):
    """The old claim was wrong in a way worth leaving visible."""

    def test_env_example_retires_the_tested_ceiling_claim(self):
        src = (_REPO / ".env.example").read_text(encoding="utf-8")
        self.assertIn("CORRECTED 2026-08-04", src)
        self.assertIn("was measured", src.replace("\n# ", " "))
        self.assertIn("MAX_CHAT_PROMPT_TOKENS", src)
        self.assertIn("MAX_EXTRACTION_CONTEXT_WINDOW", src)

    def test_the_retired_claim_is_quoted_rather_than_deleted(self):
        """A reader who remembers the old rule must be able to see it was
        retired, and why -- not merely find it missing."""
        src = (_REPO / ".env.example").read_text(encoding="utf-8")
        self.assertIn("is NOT a tuning option", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
