"""WO-LEAN-LORI-RUNTIME-01 Phase 1C — the extraction pre-generation is gone.

WHAT WAS WRONG
--------------
`_is_llm_available()` reads like a status check and is not one. It performs
a real COMPOSED generation:

    _try_call_llm('Return exactly: {"status":"ok"}', "ping", max_new=20, ...)

and because it passes a conv_id it goes through `chat()`, which composes
Lori's full persona and calls `ensure_session("ping")`.

`_extract_via_singlepass` called it before every extraction. With
`HORNELORE_EXTRACTION_BOUNDED=1` -- which is what Chris's `.env` carries,
so this was production and not a hypothetical -- one eligible completed
turn therefore cost TWO generations: a composed ping, then the real
bounded raw_ephemeral extraction.

`GET /api/extract-diag` had the same defect in a worse place. It generated
on every GET, and operator surfaces poll status routes, so a dashboard on
a refresh timer fired model generations behind the operator's back --
competing with the narrator's own turn for the single uvicorn worker.

WHY THE REAL CALL IS THE READINESS TEST
---------------------------------------
It always was. `_extract_via_singlepass` already calls
`_mark_llm_unavailable("empty-response")` on a falsy result and
`_mark_llm_available()` on success, so the extraction itself refreshes the
cache. The ping answered a question the next statement was about to answer
properly -- and answered it about a different prompt on a different call
mode. A 20-token composed ping succeeding says very little about whether a
bounded extraction will fit its budget.

R3 forbids replacing it with "a free-floating Boolean that can disagree
with the actual call", which is exactly what the cached result was: a value
up to `_LLM_CHECK_TTL` seconds old could green-light a turn whose
extraction then failed, or skip a turn the model would have served.

WHAT IS DELIBERATELY UNCHANGED
------------------------------
The legacy composed path keeps its gate -- its generation is unbounded and
goes through `chat()`, and the pre-check is load-bearing there for the v8.0
reason in the function's own docstring. The two-pass (`:2142`, `:2501`) and
SPANTAG (`:4061`) call sites are on lanes whose flags are 0 and are left
alone rather than deleted blindly, per R3's "do not delete shared legacy
behavior blindly".

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_extraction_pre_generation_removed
"""
from __future__ import annotations

import ast
import os
import sys
import types
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SERVER = _REPO / "server" / "code"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

# Same offline stub convention as tests/test_extraction_prompt_budget.py.
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
        def __init__(self, status_code=500, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    _fa.APIRouter = _APIRouter
    _fa.HTTPException = _HTTPException
    _fa.Query = lambda default=None, **_k: default
    _fa.Body = lambda default=None, **_k: default
    _fa.Depends = lambda *a, **k: None
    sys.modules["fastapi"] = _fa

from api.routers import extract as E  # noqa: E402

_EXTRACT_SRC = (_SERVER / "api" / "routers" / "extract.py").read_text(encoding="utf-8")


def _fn_body(name: str) -> str:
    """Executable body of a module-level function, docstring stripped.

    The comment block explaining this repair names `_is_llm_available`,
    `_try_call_llm` and "ping" repeatedly. A raw substring scan would
    match the explanation and pass on code that still pings -- the
    guard-writing trap this repository keeps hitting.
    """
    tree = ast.parse(_EXTRACT_SRC)
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            stmts = n.body
            first = stmts[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                stmts = stmts[1:]
            return "\n".join(ast.unparse(b) for b in stmts)
    raise AssertionError(f"no function {name!r}")


class _Recorder:
    """Stands in for `_try_call_llm` and records every call."""

    def __init__(self, result='[{"fieldPath":"personal.firstName",'
                              '"value":"Kent","confidence":0.9}]'):
        self.calls = []
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls.append({"args": args, "kwargs": kwargs})
        return self.result

    @property
    def n(self):
        return len(self.calls)


class BoundedPathMakesExactlyOneCallTest(unittest.TestCase):
    """The headline requirement: one eligible bounded extraction produces
    one extraction LLM call, not a ping plus an extraction."""

    def setUp(self):
        self._env = dict(os.environ)
        os.environ["HORNELORE_EXTRACTION_BOUNDED"] = "1"
        self._li = sys.modules.get("api.llm_interview")
        if self._li is None:
            self._li = types.ModuleType("api.llm_interview")
            sys.modules["api.llm_interview"] = self._li
        self._orig_call = getattr(self._li, "_try_call_llm", None)
        # A cold cache, so a surviving ping could not be masked by a hit.
        E._llm_available_cache["available"] = None
        E._llm_available_cache["checked_at"] = 0.0

    def tearDown(self):
        if self._orig_call is not None:
            self._li._try_call_llm = self._orig_call
        os.environ.clear()
        os.environ.update(self._env)

    def test_one_bounded_extraction_is_exactly_one_llm_call(self):
        rec = _Recorder()
        self._li._try_call_llm = rec
        E._extract_via_singlepass("I was born in Stanley in 1936.", None, None)
        self.assertEqual(
            1, rec.n,
            f"expected exactly one generation, got {rec.n}: "
            f"{[c['args'][1:2] for c in rec.calls]}")

    def test_that_one_call_is_the_bounded_raw_ephemeral_extraction(self):
        """Not merely 'one call' -- the RIGHT call. A version that kept
        the ping and dropped the extraction would also count one."""
        rec = _Recorder()
        self._li._try_call_llm = rec
        E._extract_via_singlepass("I was born in Stanley in 1936.", None, None)
        kw = rec.calls[0]["kwargs"]
        self.assertEqual("raw_ephemeral", kw.get("prompt_mode"))
        self.assertEqual("extraction", kw.get("request_kind"))
        self.assertIsNone(kw.get("conv_id"),
                          "raw_ephemeral with a conv_id is a contract error")

    def test_no_ping_prompt_is_ever_sent_on_the_bounded_path(self):
        rec = _Recorder()
        self._li._try_call_llm = rec
        E._extract_via_singlepass("I was born in Stanley in 1936.", None, None)
        for c in rec.calls:
            blob = repr(c["args"]) + repr(c["kwargs"])
            self.assertNotIn('"status":"ok"', blob)
            self.assertNotIn("'ping'", blob)

    def test_a_cached_unavailable_does_not_skip_a_bounded_extraction(self):
        """R3: no free-floating Boolean that can disagree with the actual
        call. A stale 'unavailable' from up to the TTL ago must not veto
        a turn the model would have served."""
        E._llm_available_cache["available"] = False
        E._llm_available_cache["checked_at"] = 9e9  # fresh, so it would be used
        rec = _Recorder()
        self._li._try_call_llm = rec
        items, raw = E._extract_via_singlepass("I was born in Stanley.", None, None)
        self.assertEqual(1, rec.n, "a stale cached False skipped the extraction")
        self.assertTrue(raw)

    def test_a_successful_extraction_refreshes_the_readiness_state(self):
        """Success MAY refresh passive readiness state -- and does, which
        is what makes the removed ping unnecessary."""
        E._llm_available_cache["available"] = False
        rec = _Recorder()
        self._li._try_call_llm = rec
        E._extract_via_singlepass("I was born in Stanley.", None, None)
        self.assertIs(True, E._llm_available_cache["available"])

    def test_an_empty_result_records_unavailable_from_the_real_call(self):
        rec = _Recorder(result=None)
        self._li._try_call_llm = rec
        items, raw = E._extract_via_singlepass("I was born in Stanley.", None, None)
        self.assertEqual(1, rec.n)
        self.assertEqual([], items)
        self.assertIsNone(raw)
        self.assertIs(False, E._llm_available_cache["available"])


class TheLegacyPathIsDeliberatelyUnchangedTest(unittest.TestCase):
    """`do not delete shared legacy behavior blindly`. With the bounded
    flag OFF the pre-check is load-bearing and must still run."""

    def setUp(self):
        self._env = dict(os.environ)
        os.environ["HORNELORE_EXTRACTION_BOUNDED"] = "0"
        E._llm_available_cache["available"] = None
        E._llm_available_cache["checked_at"] = 0.0

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_the_gate_still_guards_the_composed_path(self):
        body = _fn_body("_extract_via_singlepass")
        self.assertIn("_is_llm_available", body,
                      "the legacy gate was removed; that is a wider change "
                      "than Phase 1C authorised")
        self.assertIn("_bounded", body)

    def test_the_gate_is_conditional_on_the_bounded_flag(self):
        """Structural, not textual: the `_is_llm_available()` call must sit
        inside a test that also mentions `_bounded`, so it cannot fire on
        the bounded path."""
        tree = ast.parse(_EXTRACT_SRC)
        fn = next(n for n in tree.body
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_extract_via_singlepass")
        guarded = False
        for n in ast.walk(fn):
            if isinstance(n, ast.If) and "_is_llm_available" in ast.unparse(n.test):
                if "_bounded" in ast.unparse(n.test):
                    guarded = True
        self.assertTrue(
            guarded,
            "_is_llm_available() is not gated on _bounded — the bounded "
            "path would ping again")

    def test_the_flag_is_resolved_before_the_gate_reads_it(self):
        body = _fn_body("_extract_via_singlepass")
        self.assertLess(body.index("_bounded = _extraction_bounded_enabled()"),
                        body.index("_is_llm_available"))

    def test_the_parked_lanes_keep_their_own_gates(self):
        """Two-pass and SPANTAG are flag-0 lanes. Phase 1C names them and
        leaves them alone; deleting their gates would be exactly the blind
        removal R3 warns against."""
        for name in ("_extract_spans", "_classify_spans_llm",
                     "_extract_via_spantag"):
            with self.subTest(fn=name):
                self.assertIn("_is_llm_available", _fn_body(name))


class ExtractDiagIsObservationalTest(unittest.TestCase):
    """A GET named `diag` must be safe to call while a narrator is
    mid-sentence."""

    def setUp(self):
        self._env = dict(os.environ)
        os.environ.pop("HORNELORE_ALLOW_DIAG_PROBE", None)
        self._li = sys.modules.get("api.llm_interview")
        if self._li is None:
            self._li = types.ModuleType("api.llm_interview")
            sys.modules["api.llm_interview"] = self._li
        self._orig_call = getattr(self._li, "_try_call_llm", None)
        E._llm_available_cache["available"] = True
        E._llm_available_cache["checked_at"] = 1.0

    def tearDown(self):
        if self._orig_call is not None:
            self._li._try_call_llm = self._orig_call
        os.environ.clear()
        os.environ.update(self._env)

    def test_a_plain_get_generates_nothing(self):
        rec = _Recorder()
        self._li._try_call_llm = rec
        out = E.extract_diag()
        self.assertEqual(0, rec.n, "extract_diag generated on a plain GET")
        self.assertTrue(out["observational"])
        self.assertFalse(out["probe_ran"])

    def test_a_plain_get_reports_the_cached_reading_and_its_age(self):
        out = E.extract_diag()
        self.assertIn("llm_cache_age_sec", out)
        self.assertEqual(True, out["llm_available"])

    def test_an_unobserved_cache_is_not_flattened_to_unavailable(self):
        """None means 'nothing has been observed', which is a different
        fact from 'the model is down' and must survive the report."""
        E._llm_available_cache["available"] = None
        out = E.extract_diag()
        self.assertIsNone(out["llm_available"])

    def test_the_probe_is_refused_without_the_maintenance_flag(self):
        rec = _Recorder()
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(0, rec.n, "the probe generated without the flag")
        self.assertFalse(out["probe_ran"])
        self.assertIn("refused", (out["llm_error"] or "").lower())

    def test_the_probe_runs_once_when_explicitly_permitted(self):
        os.environ["HORNELORE_ALLOW_DIAG_PROBE"] = "1"
        rec = _Recorder(result='{"status":"ok"}')
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(1, rec.n)
        self.assertTrue(out["probe_ran"])
        self.assertFalse(out["observational"])
        self.assertTrue(out["llm_available"])

    def test_two_deliberate_acts_are_required_not_one(self):
        """The flag alone must not turn a routine GET into a generation --
        a dashboard poll on a maintenance-flagged server would otherwise
        start generating."""
        os.environ["HORNELORE_ALLOW_DIAG_PROBE"] = "1"
        rec = _Recorder()
        self._li._try_call_llm = rec
        E.extract_diag()          # no ?probe=1
        self.assertEqual(0, rec.n)


if __name__ == "__main__":
    unittest.main(verbosity=2)
