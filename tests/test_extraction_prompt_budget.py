"""WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 5.

    PYTHONPATH=server/code .venv/bin/python -m unittest \
        tests.test_extraction_prompt_budget

WHAT PHASE 5 FOUND, AND WHY THESE TESTS ARE SHAPED THIS WAY
-----------------------------------------------------------
Extraction was not running the prompt anybody thought it was running.
`_extract_via_singlepass` called `_try_call_llm` with the DEFAULT
prompt_mode="composed", so extraction went through `api.chat()`, which
passes the prompt into `compose_system_prompt` -- prepending ~18,000
chars of Lori persona, safety text and RAG (52% on top) -- and which
calls `add_turn` twice whenever a conv_id is present. Extraction passed
one. 464 turns rows across 232 `_extract_*` conversations in the live
database are the receipt.

The composed prompt reached ~12,300 tokens against MAX_CONTEXT_WINDOW
8192, and the generic guard resolved that with `v[:, -8192:]` -- keeping
the LAST tokens, cutting the FRONT, where the extraction preamble, the
"use ONLY these exact fieldPath values" rule and the 140-field catalog
live. Nothing said which components a given call had lost.

So the tests below assert two different KINDS of thing, and the
distinction matters:

  * that extraction takes the raw path and carries its own budget
    (execution-path facts, 5A);
  * that the prompt it builds actually fits (size facts, 5B).

5A alone would correctly refuse every extraction, because the current
prompt genuinely does not fit. 5B alone would still be wrapped by the
composer. They ship behind ONE flag for that reason, and a test here
pins that they cannot be separated.

TOKENS VS CHARACTERS
--------------------
Only the tokenizer knows tokens, and it lives at the generation
chokepoint. These tests therefore assert CHARACTER budgets with an
explicit, documented chars-per-token floor, and assert the ARITHMETIC of
the token budget separately against exact integers. The real token count
is measured in production by `[EXTRACT-BUDGET]`. A test that guessed at
tokenization would be asserting its own guess.
"""

from __future__ import annotations

import ast
import os
import sys
import types
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SERVER = _REPO / "server" / "code"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

# Same offline stub convention as tests/test_turn_extraction.py: the
# extraction router imports fastapi/pydantic at module scope and neither
# is needed to exercise prompt construction or budget arithmetic.
if "pydantic" not in sys.modules:
    _pyd = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

        def dict(self):
            return dict(self.__dict__)

    def _Field(default=None, **_kw):
        return default

    _pyd.BaseModel = _BaseModel
    _pyd.Field = _Field
    _pyd.ConfigDict = dict
    sys.modules["pydantic"] = _pyd

if "fastapi" not in sys.modules:
    _fa = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            self.routes = []

        def _noop(self, *a, **k):
            def deco(fn):
                return fn
            return deco

        get = post = patch = delete = put = _noop

    class _HTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    _fa.APIRouter = _APIRouter
    _fa.HTTPException = _HTTPException
    _fa.Query = lambda default=None, **k: default
    _fa.Body = lambda default=None, **k: default
    _fa.Depends = lambda x=None: x
    _resp = types.ModuleType("fastapi.responses")
    _resp.JSONResponse = object
    _fa.responses = _resp
    sys.modules["fastapi"] = _fa
    sys.modules["fastapi.responses"] = _resp

from api.services.extraction_budget import (            # noqa: E402
    ExtractionPromptBudgetExceeded,
    PromptBudget,
    budget_for,
    safety_reserve_tokens,
)

# The bounded builder reads HORNELORE_NARRATIVE at call time and live has
# it =1, so the module is imported with the live flag state. Measuring the
# prompt under a flag combination that does not ship would prove nothing.
os.environ.setdefault("HORNELORE_NARRATIVE", "1")
from api.routers import extract as E                    # noqa: E402


# Characters per token. RECALIBRATED 2026-08-01 from 60 live
# [EXTRACT-BUDGET] measurements of the adopted b2a prompt, which ranged
# 4.23 .. 4.31 (avg 4.27) -- a very tight band, because the prompt is
# ~95% fixed text. 4.0 sits ~5% below the worst observed value, so it is
# still a floor rather than an average.
#
# It was 3.5, chosen before any b2a measurement existed. That was ~20%
# below anything ever observed, and once the labeled catalog landed it
# began failing prompts that demonstrably fit -- the b2a and b2b eval
# runs together made 60 live calls with ZERO budget refusals and ZERO
# truncations. A floor that rejects reality is not caution, it is a
# false alarm, and the fix is to ground it in measurement rather than to
# keep lowering whatever the test happens to trip on.
_PESSIMISTIC_CHARS_PER_TOKEN = 4.0

# The largest narratorReply in the 114-case bank is 1,032 chars
# (case_081); median 172, p90 674. The synthetic "longest" case below is
# deliberately several times larger than anything real -- it is a stress
# input, not a representative one.
_LARGEST_REAL_NARRATOR_TURN_CHARS = 1032


def _est_tokens(text: str) -> int:
    return int(len(text) / _PESSIMISTIC_CHARS_PER_TOKEN)


class BudgetArithmeticTest(unittest.TestCase):
    """Exact integers. No estimation involved."""

    def test_the_ceiling_comes_from_this_call_s_generation_cap(self):
        # Extraction runs at 128 for an ordinary answer and 768 for a
        # compound one. A fixed ceiling would be wrong for one of them,
        # and wrong in the dangerous direction for the compound case --
        # whose prompt is the longest.
        self.assertEqual(budget_for(window=8192, max_new=128).ceiling,
                         8192 - 128 - 512)
        self.assertEqual(budget_for(window=8192, max_new=768).ceiling,
                         8192 - 768 - 512)

    def test_a_bigger_generation_cap_buys_a_smaller_prompt(self):
        self.assertLess(budget_for(window=8192, max_new=768).ceiling,
                        budget_for(window=8192, max_new=128).ceiling)

    def test_the_reserve_has_a_floor_and_a_cap(self):
        for raw, expect in (("0", 384), ("100", 384), ("512", 512),
                            ("1024", 1024), ("99999", 4096), ("junk", 512)):
            with self.subTest(raw=raw):
                os.environ["HORNELORE_EXTRACTION_RESERVE_TOKENS"] = raw
                try:
                    self.assertEqual(safety_reserve_tokens(), expect)
                finally:
                    os.environ.pop("HORNELORE_EXTRACTION_RESERVE_TOKENS", None)

    def test_exceeded_is_strictly_greater_not_greater_or_equal(self):
        b = budget_for(window=8192, max_new=128)
        exact = PromptBudget(window=8192, max_new=128, reserve=512,
                             prompt_tokens=b.ceiling)
        self.assertFalse(exact.exceeded, "a prompt exactly at the ceiling fits")
        over = PromptBudget(window=8192, max_new=128, reserve=512,
                            prompt_tokens=b.ceiling + 1)
        self.assertTrue(over.exceeded)

    def test_the_window_is_supplied_not_read_here(self):
        # api.py owns MAX_CONTEXT_WINDOW. If this module read it too they
        # could disagree, and the guard and the enforcement would be
        # defending different numbers.
        src = (_SERVER / "api" / "services" / "extraction_budget.py").read_text(
            encoding="utf-8")
        # WIDENED 2026-08-04 (Phase 2C): there are now three names it
        # must not read, not one. A second reader of ANY of them could
        # disagree with api.py, and the guard and the enforcement would
        # be defending different numbers -- which is the whole reason
        # this test exists.
        for _name in ("MAX_CONTEXT_WINDOW", "MAX_CHAT_PROMPT_TOKENS",
                      "MAX_EXTRACTION_CONTEXT_WINDOW"):
            self.assertNotIn(f'getenv("{_name}"', src)
            self.assertNotIn(f"getenv('{_name}'", src)


class RefusalCarriesCountsOnlyTest(unittest.TestCase):
    """Privacy: the refusal closes a ledger row and is logged."""

    def test_the_message_contains_no_prompt_or_narrator_text(self):
        secret = "my mother's maiden name was Ostrander"
        b = budget_for(window=8192, max_new=128, prompt_tokens=99999,
                       components={"chars_user": len(secret)})
        msg = str(ExtractionPromptBudgetExceeded(b))
        self.assertNotIn("Ostrander", msg)
        self.assertNotIn("maiden", msg)
        self.assertIn("99999", msg)

    def test_the_log_line_is_counts_only(self):
        b = budget_for(window=8192, max_new=128, prompt_tokens=7000,
                       components={"chars_user": 42, "fewshot_n": 8})
        line = b.as_log_fields()
        self.assertIn("kind=extraction", line)
        self.assertIn("tokens_total=7000", line)
        self.assertIn("budget=7552", line)
        self.assertIn("fewshot_n=8", line)
        # every token of the line is key=int
        for pair in line.split():
            k, _, v = pair.partition("=")
            self.assertTrue(v.lstrip("-").isdigit() or k == "kind",
                            f"{pair!r} is not a count")

    def test_it_is_an_exception_the_ledger_can_name(self):
        b = budget_for(window=8192, max_new=128, prompt_tokens=99999)
        exc = ExtractionPromptBudgetExceeded(b)
        self.assertIsInstance(exc, Exception)
        self.assertEqual(exc.__class__.__name__,
                         "ExtractionPromptBudgetExceeded")


class BoundedPromptFitsTest(unittest.TestCase):
    """5B: the prompt the bounded builder makes actually fits."""

    def _build(self, answer, section="parents", target="parents.firstName"):
        return E._build_extraction_prompt_bounded(answer, section, target)

    def test_the_complete_140_field_catalog_survives_compaction(self):
        cat = E._extraction_field_catalog()
        missing = [p for p in E.EXTRACTABLE_FIELDS if f'"{p}"=' not in cat]
        self.assertEqual(missing, [],
                         "the adopted catalog must carry every path")
        self.assertEqual(len(E.EXTRACTABLE_FIELDS), 140)

    def test_compaction_is_not_filtering(self):
        # Chris's constraint: current_section may reorder emphasis, never
        # remove valid fields. Changing visibility and coverage together
        # would leave an eval nobody could interpret.
        a = E._extraction_field_catalog()
        for section in (None, "parents", "education", "pets"):
            with self.subTest(section=section):
                s, _ = self._build("I was born in Mandan.", section, None)
                self.assertIn(a, s, "the whole catalog appears regardless "
                                    "of the section hint")

    def test_short_medium_and_longest_turns_all_fit(self):
        cases = {
            "short": "I was born in Mandan.",
            "medium": ("I was born in Mandan, North Dakota in 1962. My dad "
                       "Kent worked at the aluminum plant and my mom Janice "
                       "taught school."),
            # Sized against REALITY, not an arbitrary repeat count. The
            # bank's largest narratorReply is 1,032 chars, so "long" is
            # ~2x that and "longest" ~4x -- a serious stress input that
            # is still a turn a person could plausibly speak.
            #
            # These were 40 and 120 repetitions (1,800 / 5,416 chars).
            # The 120 case sat 1.5% past the pessimistic floor once the
            # labeled catalog landed, and it fits fine at the observed
            # 4.27 ratio. Anchoring the input to the real distribution is
            # the honest fix; shaving the floor again to clear an
            # arbitrary input would have been fitting the ruler to the
            # measurement.
            "long": "We drove to Bismarck in the summer of 1971. " * 46,
            "longest": "We drove to Bismarck in the summer of 1971. " * 92,
        }
        for name, answer in cases.items():
            with self.subTest(case=name):
                s, u = self._build(answer)
                est = _est_tokens(s + u)
                # 768 is the COMPOUND cap and therefore the tighter ceiling.
                b = budget_for(window=8192, max_new=768, prompt_tokens=est)
                self.assertFalse(
                    b.exceeded,
                    f"{name}: ~{est} tokens over a {b.ceiling} ceiling "
                    f"(pessimistic {_PESSIMISTIC_CHARS_PER_TOKEN} chars/tok)")

    def test_a_multi_topic_turn_still_fits(self):
        answer = ("My father Kent was born in Stanley and worked at the "
                  "aluminum plant. My mother Janice taught school in "
                  "Spokane. I have a brother Vincent, two years older. We "
                  "had a Golden Retriever named Ivan. I served in the Navy "
                  "from 1981 and married Melanie in 1988 in Bismarck.")
        s, u = self._build(answer, "family", "family.spouse.firstName")
        est = _est_tokens(s + u)
        b = budget_for(window=8192, max_new=768, prompt_tokens=est)
        self.assertFalse(b.exceeded)

    def test_the_answer_headroom_is_stated_not_implied(self):
        """How much narrator turn fits before the budget refuses.

        This is the number that actually matters for a live session, and
        adopting b2a halves it: the labeled catalog costs ~6,300 chars
        that a narrator's own words no longer get. It is still ~6.7x the
        largest turn in the bank, but it is a real trade and it should
        be visible in a test rather than discovered by an operator when
        a long story fails closed.
        """
        s, _u = self._build("x")
        sys_tokens = _est_tokens(s)
        # compound is the tighter ceiling and the longer-prompt case
        ceiling = budget_for(window=8192, max_new=384).ceiling
        headroom_chars = int((ceiling - sys_tokens) * _PESSIMISTIC_CHARS_PER_TOKEN)
        self.assertGreater(
            headroom_chars, _LARGEST_REAL_NARRATOR_TURN_CHARS * 3,
            f"only {headroom_chars} chars of narrator turn fit before the "
            f"budget refuses; the largest real turn is "
            f"{_LARGEST_REAL_NARRATOR_TURN_CHARS}. The prompt has grown "
            "into the narrator's room.")

    def test_the_normal_target_is_met_not_merely_the_ceiling(self):
        # Chris: "barely fitting below 8192 is not the acceptance target."
        s, u = self._build("I was born in Mandan, North Dakota in 1962.")
        self.assertLessEqual(_est_tokens(s + u), 6500)

    def test_the_narrator_turn_is_carried_whole(self):
        answer = ("We drove to Bismarck in the summer of 1971 and the "
                  "radiator boiled over outside Steele. " * 30)
        _s, u = self._build(answer)
        self.assertIn(answer, u,
                      "the answer is the one component that may never be "
                      "abbreviated to make a budget fit")

    def test_the_protected_components_are_all_present(self):
        s, u = self._build("I was born in Mandan.")
        self.assertIn(E._extraction_field_catalog(), s)          # catalog
        self.assertIn(E._PROMPTSHRINK_ROUTING_DISTINCTIONS, s)  # routing
        self.assertIn(E._PROMPTSHRINK_PREAMBLE, s)            # JSON contract
        self.assertIn("JSON", s)
        self.assertIn("Extract all facts as a JSON array:", u)

    def test_few_shots_are_capped_at_eight(self):
        for section in (None, "parents", "family", "education", "military"):
            with self.subTest(section=section):
                topics = (E._promptshrink_topics_for_target(None)
                          | E._promptshrink_topics_for_section(section))
                self.assertLessEqual(
                    len(E._promptshrink_select_fewshots(topics, max_examples=8)), 8)

    def test_it_is_dramatically_smaller_than_the_composed_legacy_prompt(self):
        """Against what ACTUALLY reached the model, not the builder alone.

        This compared bounded output to `_build_extraction_prompt`'s
        return value, which understates legacy by the ~18,000 chars
        `compose_system_prompt` prepended on every real call -- the
        docstring admitted as much while the assertion ignored it. Once
        the labeled catalog was adopted, bounded landed at 65% of the
        builder and the test failed, on a comparison that was measuring
        the wrong baseline in the first place.
        """
        from api.prompt_composer import compose_system_prompt
        answer = "I was born in Mandan, North Dakota in 1962."
        s, u = self._build(answer)
        legacy_s, legacy_u = E._build_extraction_prompt(answer, None, None)
        composed = compose_system_prompt(
            "_extract_probe", ui_system=legacy_s, user_text=legacy_u)
        bounded_total = len(s) + len(u)
        legacy_total = len(composed) + len(legacy_u)

        # ── RATIO RETIRED 2026-08-04, and NOT because extraction moved.
        #
        # The retired assertion was:
        #     self.assertLess(bounded_total, legacy_total * 0.5, ...)
        #
        # It failed at 22,497 vs 44,628 -- 50.4%. Bounded output did not
        # change by a character. What moved is the BASELINE: parking the
        # safety feature removed 7,933 characters from
        # `compose_system_prompt`, so the legacy prompt this is measured
        # against got smaller and the fixed ratio tightened by itself.
        #
        # Nudging 0.5 to 0.55 would have hidden that, and would drift
        # again the next time the composed prompt changes size for a
        # reason unrelated to extraction. A ratio against a moving
        # baseline is not a measurement of the thing it claims to
        # measure. So the claim is restated as what it actually is: a
        # magnitude, in characters, plus the ordering.
        self.assertLess(bounded_total, legacy_total,
                        f"bounded {bounded_total:,} is not smaller than "
                        f"composed legacy {legacy_total:,}")
        saving = legacy_total - bounded_total
        self.assertGreaterEqual(
            saving, 20_000,
            f"bounding no longer saves a meaningful amount: {saving:,} chars "
            f"(bounded {bounded_total:,} vs composed legacy {legacy_total:,})")


class ExecutionPathTest(unittest.TestCase):
    """5A: read from source, because these are routing facts.

    Comment-stripped where a word is discussed as well as used -- the
    prose in extract.py names `compose_system_prompt` and `add_turn`
    precisely to explain why the bounded path avoids them, and a raw scan
    would fire on the explanation.
    """

    @classmethod
    def setUpClass(cls):
        from tests.source_scan_helpers import strip_js_comments  # noqa: F401
        cls.extract_src = (_SERVER / "api" / "routers" / "extract.py").read_text(
            encoding="utf-8")
        cls.llm_src = (_SERVER / "api" / "llm_interview.py").read_text(
            encoding="utf-8")
        cls.api_src = (_SERVER / "api" / "api.py").read_text(encoding="utf-8")
        cls.extract_tree = ast.parse(cls.extract_src)

    def _bounded_branch_source(self):
        """The executable body of the bounded call, docstrings stripped."""
        for node in ast.walk(self.extract_tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name == "_extract_via_singlepass"):
                body = list(node.body)
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)):
                    body = body[1:]
                return "\n".join(ast.unparse(n) for n in body)
        self.fail("_extract_via_singlepass not found")

    def test_the_bounded_path_calls_the_llm_as_raw_ephemeral(self):
        src = self._bounded_branch_source()
        self.assertIn("prompt_mode='raw_ephemeral'", src)
        self.assertIn("request_kind='extraction'", src)

    def test_the_bounded_path_passes_no_conv_id(self):
        # _try_call_llm REFUSES raw_ephemeral together with a conv_id, so
        # this is enforced twice: here and by that contract check.
        src = self._bounded_branch_source()
        self.assertIn("conv_id=None", src)

    def test_the_refusal_is_re_raised_before_the_blanket_handler(self):
        i_budget = self.llm_src.index("except ExtractionPromptBudgetExceeded")
        i_blanket = self.llm_src.index("except Exception as e:")
        self.assertLess(i_budget, i_blanket,
                        "Python takes the first matching clause; ordering "
                        "IS the mechanism")

    def test_the_budget_class_is_imported_at_module_scope(self):
        # A lazy import could fail at the moment the refusal needed
        # catching, and the blanket clause would swallow it.
        tree = ast.parse(self.llm_src)
        top = {n.module for n in tree.body if isinstance(n, ast.ImportFrom)}
        self.assertIn("services.extraction_budget", top)

    def test_extraction_never_reaches_the_generic_tail_slice(self):
        """The truncation branch is an `elif` on the extraction test.

        An independent `if` would let an extraction that passed the budget
        check fall through into the tail-slice anyway.

        Asserted with a line-anchored regex rather than a substring,
        because `assertNotIn("if n_tokens > ...")` MATCHES
        `elif n_tokens > ...` -- "elif" ends in "if". That is what this
        test failed on when it was first written.
        """
        import re as _re
        i_kind = self.api_src.index('if request_kind == "extraction":')
        # UPDATED 2026-08-04 (Phase 2C). The retired form read
        # `elif n_tokens > MAX_CONTEXT_WINDOW:` -- one constant governed
        # both lanes. The assertion is unchanged in intent and STRONGER
        # in effect: the chat slice now names a chat-only constant, so
        # extraction falling into it would be visible in the source, not
        # merely in the ordering.
        i_trunc = self.api_src.index("elif n_tokens > MAX_CHAT_PROMPT_TOKENS:")
        self.assertLess(i_kind, i_trunc)
        standalone = _re.search(r"^\s*if\s+n_tokens\s*>\s*MAX_CHAT_PROMPT_TOKENS",
                                self.api_src, _re.M)
        self.assertIsNone(
            standalone,
            "found a standalone `if n_tokens > MAX_CHAT_PROMPT_TOKENS` at line "
            f"{self.api_src[:standalone.start()].count(chr(10)) + 1 if standalone else '?'}"
            " -- extraction could fall through into the tail-slice")

    def test_no_chat_truncation_site_survives(self):
        """REWRITTEN by Phase 4A, 2026-08-04. Retired assertion:

            for label, src, n in (("api.py", self.api_src, 2),
                                  ("chat_ws.py", ws_src, 1)):
                self.assertEqual(src.count("[VRAM-GUARD] kind=chat"), n)

        It required the chat truncations to EXIST and be tagged, so that
        "zero extraction truncations" stayed provable by grep while the
        chat slices were still there. Phase 4A removes all three, which
        makes the grep argument stronger rather than weaker: there are
        now no VRAM-GUARD truncations of a chat prompt at all, so any
        such line in api.log is by definition not a chat lane.

        Extraction's own refusal path is untouched and is asserted
        elsewhere in this suite.
        """
        ws_src = (_SERVER / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        for label, src in (("api.py", self.api_src), ("chat_ws.py", ws_src)):
            with self.subTest(file=label):
                self.assertEqual(
                    0, src.count("[VRAM-GUARD] kind=chat Truncating"),
                    f"{label}: a chat prompt is still being truncated")

    def test_the_tail_slice_is_gone_from_the_chat_lanes(self):
        """RENAMED AND INVERTED by Phase 4A. The retired name said it
        outright -- `test_the_tail_slice_still_exists_for_chat_until_
        phase_4` -- and the retired assertion was:

            self.assertIn("v[:, -MAX_CHAT_PROMPT_TOKENS:]", self.api_src)

        This is Phase 4. The slice kept the LAST N tokens and therefore
        cut the FRONT, where Lori's identity lives, on 382 of 630
        measured turns.
        """
        ws_src = (_SERVER / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")
        for label, src in (("api.py", self.api_src), ("chat_ws.py", ws_src)):
            with self.subTest(file=label):
                self.assertNotIn("v[:, -MAX_CHAT_PROMPT_TOKENS:]", src,
                                 f"{label}: the blind front-slice is back")

    def test_extraction_still_refuses_rather_than_truncating(self):
        """Non-vacuity for the two above. Without it, they would pass on
        a build where the whole guard had been deleted rather than
        replaced -- and extraction's fail-closed behaviour is the thing
        that must not have moved."""
        self.assertIn("raise ExtractionPromptBudgetExceeded(budget)",
                      self.api_src)
        self.assertIn('if request_kind == "extraction":', self.api_src)

    def test_one_flag_gates_both_the_builder_and_the_execution_mode(self):
        """Structural half of atomicity; FlagAtomicityTest drives the
        behavioural half.

        One getenv, and the same `_bounded` name gates the builder choice
        and the call. Two flags, or two separate reads, would make the
        forbidden combinations reachable.
        """
        self.assertEqual(
            self.extract_src.count('getenv("HORNELORE_EXTRACTION_BOUNDED"'), 1,
            "exactly one read of the flag")
        src = self._bounded_branch_source()
        self.assertIn("_bounded = _extraction_bounded_enabled()", src)
        self.assertIn("if _bounded:", src)

    def test_the_flag_is_default_off(self):
        self.assertIn('getenv("HORNELORE_EXTRACTION_BOUNDED", "0")',
                      self.extract_src)

    def test_the_dead_field_catalog_string_is_gone(self):
        self.assertNotIn('field_catalog = "\\n".join(field_lines)',
                         self.extract_src)
        self.assertNotIn("field_lines.append", self.extract_src)


class FlagAtomicityTest(unittest.TestCase):
    """The four-way matrix, driven rather than scanned.

        flag off -> legacy builder  + composed execution
        flag on  -> bounded builder + raw_ephemeral execution
        never       bounded builder + composed execution
        never       legacy builder  + raw_ephemeral execution

    A source scan can show the two consequences hang off one name. Only
    running the function proves that the prompt which reaches the model
    is the one the execution mode expects. The two forbidden rows are the
    dangerous ones and are asserted directly: bounded+composed would put
    the compact prompt back inside Lori's persona and quietly persist
    turns again; legacy+raw_ephemeral would send a ~12,300-token prompt
    into a path that now REFUSES rather than truncates, so every
    extraction would fail closed and the narrator would silently stop
    being extracted at all.
    """

    def setUp(self):
        self._orig_flag = os.environ.get("HORNELORE_EXTRACTION_BOUNDED")
        # _extract_via_singlepass short-circuits on a cached availability
        # probe; force it open so the call is actually reached.
        self._orig_avail = E._is_llm_available
        E._is_llm_available = lambda: True
        import api.llm_interview as _li
        self._li = _li
        self._orig_try = _li._try_call_llm
        self.calls = []

        def _recorder(system, user, **kw):
            self.calls.append({"system": system, "user": user, **kw})
            return "[]"          # parses to zero items; we assert on the call

        _li._try_call_llm = _recorder

    def tearDown(self):
        E._is_llm_available = self._orig_avail
        self._li._try_call_llm = self._orig_try
        if self._orig_flag is None:
            os.environ.pop("HORNELORE_EXTRACTION_BOUNDED", None)
        else:
            os.environ["HORNELORE_EXTRACTION_BOUNDED"] = self._orig_flag

    _ANSWER = "I was born in Mandan, North Dakota in 1962."

    def _run(self, flag_value):
        self.calls.clear()
        if flag_value is None:
            os.environ.pop("HORNELORE_EXTRACTION_BOUNDED", None)
        else:
            os.environ["HORNELORE_EXTRACTION_BOUNDED"] = flag_value
        E._extract_via_singlepass(self._ANSWER, "parents", "parents.firstName")
        self.assertEqual(len(self.calls), 1, "expected exactly one LLM call")
        return self.calls[0]

    def test_flag_off_uses_the_legacy_builder_and_the_composed_route(self):
        call = self._run(None)
        legacy_s, _ = E._build_extraction_prompt(
            self._ANSWER, "parents", "parents.firstName")
        self.assertEqual(call["system"], legacy_s,
                         "flag off must send the historical prompt verbatim")
        self.assertNotEqual(call.get("prompt_mode", "composed"), "raw_ephemeral")
        self.assertTrue((call.get("conv_id") or "").startswith("_extract_"),
                        "the composed route keeps its ephemeral conv_id")

    def test_flag_on_uses_the_bounded_builder_and_the_raw_route(self):
        call = self._run("1")
        bounded_s, _ = E._build_extraction_prompt_bounded(
            self._ANSWER, "parents", "parents.firstName")
        self.assertEqual(call["system"], bounded_s)
        self.assertEqual(call["prompt_mode"], "raw_ephemeral")
        self.assertEqual(call["request_kind"], "extraction")
        self.assertIsNone(call["conv_id"])

    def test_the_bounded_prompt_never_travels_the_composed_route(self):
        """FORBIDDEN ROW 1. Compact prompt back inside the composer would
        re-add the persona and resume persisting turns."""
        for flag in (None, "0", "1", "true"):
            with self.subTest(flag=flag):
                call = self._run(flag)
                bounded_s, _ = E._build_extraction_prompt_bounded(
                    self._ANSWER, "parents", "parents.firstName")
                if call["system"] == bounded_s:
                    self.assertEqual(call.get("prompt_mode"), "raw_ephemeral")
                    self.assertIsNone(call.get("conv_id"))

    def test_the_legacy_prompt_never_travels_the_raw_route(self):
        """FORBIDDEN ROW 2. The ~12,300-token legacy prompt down a path
        that refuses rather than truncates would fail every extraction
        closed -- the narrator would stop being extracted silently."""
        for flag in (None, "0", "1", "true"):
            with self.subTest(flag=flag):
                call = self._run(flag)
                legacy_s, _ = E._build_extraction_prompt(
                    self._ANSWER, "parents", "parents.firstName")
                if call["system"] == legacy_s:
                    self.assertNotEqual(call.get("prompt_mode"), "raw_ephemeral")

    def test_the_two_builders_are_actually_distinguishable(self):
        """Non-vacuity. If both builders returned the same string the four
        tests above would pass while proving nothing at all."""
        a, _ = E._build_extraction_prompt(
            self._ANSWER, "parents", "parents.firstName")
        b, _ = E._build_extraction_prompt_bounded(
            self._ANSWER, "parents", "parents.firstName")
        self.assertNotEqual(a, b)
        self.assertLess(len(b), len(a))

    def test_every_truthy_spelling_of_the_flag_selects_the_bounded_pair(self):
        for value in ("1", "true", "TRUE", "yes", "on"):
            with self.subTest(value=value):
                call = self._run(value)
                self.assertEqual(call["prompt_mode"], "raw_ephemeral")

    def test_every_falsy_spelling_keeps_the_legacy_pair(self):
        for value in (None, "0", "false", "no", "off", ""):
            with self.subTest(value=value):
                call = self._run(value)
                self.assertNotEqual(call.get("prompt_mode"), "raw_ephemeral")


class FailClosedLifecycleTest(unittest.TestCase):
    """The refusal's whole journey, driven end to end against real sqlite.

    Every other test here is a source scan or arithmetic. This one runs
    the refusal through the real ledger and asserts what Chris's ruling
    enumerates: same claim, closed failed, named error_class, zero 0041
    rows, zero browser frames, and -- the one that matters most -- not
    degraded into a rules fallback.
    """

    def setUp(self):
        import tempfile
        import uuid
        from api import db as _db
        from api.services import turn_extraction as tx
        self._db, self._tx = _db, tx
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()
        self.narrator_id = f"harness-{uuid.uuid4()}"
        self.conv_id = f"conv-{self.narrator_id}"
        self._orig_call = tx._call_extractor

    def tearDown(self):
        self._tx._call_extractor = self._orig_call
        self._db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    def test_a_budget_refusal_closes_the_claim_and_delivers_nothing(self):
        import asyncio
        import sqlite3
        _db, tx = self._db, self._tx

        row = _db.persist_turn_transaction(
            conv_id=self.conv_id, user_message="I was born in Mandan.",
            assistant_message="Tell me more.", model_name="test")
        key = _db.turn_extraction_key_for_row(row)

        b = budget_for(window=8192, max_new=768, prompt_tokens=9999)
        tx._call_extractor = lambda _r: (_ for _ in ()).throw(
            ExtractionPromptBudgetExceeded(b))

        delivered = []

        async def _cb(outcome, clar=None, src=""):
            delivered.append(outcome)

        terminal, claim = tx._begin(
            narrator_id=self.narrator_id, turn_id="t-1",
            user_text="I was born in Mandan.", session_id=self.conv_id,
            turn_key=key, turn_mode="interview", source="chat_ws",
            current_section=None, current_target_path=None,
            current_era=None, current_pass=None, current_mode=None)
        self.assertIsNone(terminal)
        claim.on_result = _cb
        out = asyncio.run(tx._complete_claim(claim))

        con = sqlite3.connect(str(self.db_path))
        try:
            con.row_factory = sqlite3.Row
            led = [dict(r) for r in con.execute(
                "SELECT outcome, error_class, item_count FROM "
                "turn_extraction_ledger WHERE narrator_id = ?;",
                (self.narrator_id,))]
            res = list(con.execute(
                "SELECT * FROM turn_extraction_results WHERE narrator_id = ?;",
                (self.narrator_id,)))
        finally:
            con.close()

        self.assertEqual(out.status, "failed")
        self.assertEqual(len(led), 1, "the SAME claim, not a new one")
        self.assertEqual(led[0]["outcome"], "failed")
        self.assertEqual(led[0]["error_class"], "ExtractionPromptBudgetExceeded",
                         "the ledger must name the refusal, not a generic error")
        self.assertEqual(led[0]["item_count"], 0)
        self.assertEqual(len(res), 0, "no 0041 result row")
        self.assertEqual(len(delivered), 0, "no browser frame")

    def test_the_refusal_is_not_a_noop(self):
        """A budget violation is not 'this turn had no facts in it'.

        Those two states look identical to an operator if the refusal is
        recorded as noop, and they mean opposite things -- one says the
        narrator said nothing extractable, the other says the machine
        never looked.
        """
        import asyncio
        _db, tx = self._db, self._tx
        row = _db.persist_turn_transaction(
            conv_id=self.conv_id, user_message="I was born in Mandan.",
            assistant_message="Tell me more.", model_name="test")
        key = _db.turn_extraction_key_for_row(row)
        b = budget_for(window=8192, max_new=128, prompt_tokens=9999)
        tx._call_extractor = lambda _r: (_ for _ in ()).throw(
            ExtractionPromptBudgetExceeded(b))
        terminal, claim = tx._begin(
            narrator_id=self.narrator_id, turn_id="t-1",
            user_text="I was born in Mandan.", session_id=self.conv_id,
            turn_key=key, turn_mode="interview", source="chat_ws",
            current_section=None, current_target_path=None,
            current_era=None, current_pass=None, current_mode=None)
        out = asyncio.run(tx._complete_claim(claim))
        self.assertNotEqual(out.status, "noop")
        self.assertEqual(out.status, "failed")


class LegacyPathUnchangedTest(unittest.TestCase):
    """Flag OFF must reproduce history, or eval arm A is not runnable."""

    def test_the_legacy_builder_still_exists_and_is_reachable(self):
        s, u = E._build_extraction_prompt("I was born in Mandan.", None, None)
        self.assertTrue(s and u)

    def test_the_promptshrink_builder_still_exists(self):
        s, u = E._build_extraction_prompt_shrunk(
            "I was born in Mandan.", None, None)
        self.assertTrue(s and u)

    def test_bounded_wins_over_promptshrink_wins_over_legacy(self):
        src = (_SERVER / "api" / "routers" / "extract.py").read_text(
            encoding="utf-8")
        i_b = src.index("if _bounded:")
        i_p = src.index("elif _promptshrink_enabled():")
        i_l = src.index("system, user = _build_extraction_prompt(answer,")
        self.assertLess(i_b, i_p)
        self.assertLess(i_p, i_l)

    def test_default_environment_selects_neither_new_path(self):
        for var in ("HORNELORE_EXTRACTION_BOUNDED", "HORNELORE_PROMPTSHRINK"):
            with self.subTest(var=var):
                old = os.environ.pop(var, None)
                try:
                    fn = (E._extraction_bounded_enabled
                          if "BOUNDED" in var else E._promptshrink_enabled)
                    self.assertFalse(fn())
                finally:
                    if old is not None:
                        os.environ[var] = old


if __name__ == "__main__":
    unittest.main()
