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

# Offline stubs for `pydantic` and `fastapi`, with one deliberate
# difference from the convention the other twenty test modules use.
#
# THEY STUB UNCONDITIONALLY WHEN THE NAME IS ABSENT FROM sys.modules.
# In a single-process batch that poisons every module loaded after them:
# the stub is registered as the real `fastapi`, and a later suite that
# needs a name the stub does not define fails on an import that would
# have worked. That is not hypothetical -- it is exactly how
# `tests.test_trip_placement` failed on 2026-08-04 with
# `cannot import name 'File' from 'fastapi' (unknown location)`, while
# passing alone. CLAUDE.md records the same class from 2026-07-27:
# "whichever file loads first wins for the whole process, so suites
# passed alone and failed in batch on alphabetical load order."
#
# So this module PREFERS THE REAL PACKAGE and only falls back to a stub
# when it is genuinely unavailable. In `.venv`, where fastapi and
# pydantic are installed, importing them here puts the real modules into
# sys.modules -- which every other suite's `if "fastapi" not in
# sys.modules` guard then sees, so they skip their stubs too. One
# module's fix improves the whole batch rather than only itself.
#
# This is NOT the shared `tests/_offline_stubs.py` refactor, which is
# ~30 files and out of scope here. It is the same idea applied to the
# one file this work order owns.
try:  # noqa: SIM105
    import fastapi as _real_fastapi  # noqa: F401
    import pydantic as _real_pydantic  # noqa: F401
except Exception:
    pass

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
        # AMENDED 2026-08-04. The flag alone stopped being sufficient when
        # the live-narration interlock landed, and this test caught that
        # correctly: `api.api` is unimportable in an offline test process
        # (no torch), so the guard read "unknown" and refused -- which is
        # the deliberate fail-safe, since a guard that cannot read its
        # signal must not permit the thing it guards. The quiet reading is
        # forced here so this test still asks its own question, which is
        # "does the permitted probe generate exactly once".
        _mod = sys.modules.get("api.api")
        if _mod is None:
            _mod = types.ModuleType("api.api")
            sys.modules["api.api"] = _mod
        _mod.seconds_since_generation = lambda: 9999.0
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


class TheProbeCannotRunDuringLiveNarrationTest(unittest.TestCase):
    """R3: an active probe "cannot run during live narration".

    The two-key requirement (?probe=1 plus HORNELORE_ALLOW_DIAG_PROBE=1)
    stops the probe being reached by ACCIDENT. It does not stop an
    operator reaching it deliberately mid-session, and code inspection on
    2026-08-04 confirmed nothing did: no in-flight or activity signal
    existed anywhere in the tree.

    `api._mark_generation()` now runs at all three `model.generate` call
    sites, so the signal covers chat turns, automatic drafting,
    follow-ups and summaries -- every path that competes for the single
    worker, not just the chat one.
    """

    def setUp(self):
        self._env = dict(os.environ)
        os.environ["HORNELORE_ALLOW_DIAG_PROBE"] = "1"
        self._li = sys.modules.get("api.llm_interview")
        if self._li is None:
            self._li = types.ModuleType("api.llm_interview")
            sys.modules["api.llm_interview"] = self._li
        self._orig_call = getattr(self._li, "_try_call_llm", None)
        self._api = sys.modules.get("api.api")
        self._orig_secs = getattr(self._api, "seconds_since_generation", None) \
            if self._api else None

    def tearDown(self):
        if self._orig_call is not None:
            self._li._try_call_llm = self._orig_call
        if self._api is not None and self._orig_secs is not None:
            self._api.seconds_since_generation = self._orig_secs
        os.environ.clear()
        os.environ.update(self._env)

    def _with_quiet(self, seconds):
        """Force the narration-activity reading."""
        mod = sys.modules.get("api.api")
        if mod is None:
            mod = types.ModuleType("api.api")
            sys.modules["api.api"] = mod
        mod.seconds_since_generation = lambda: seconds
        return mod

    def test_a_probe_is_refused_while_narration_is_live(self):
        self._with_quiet(2.0)
        rec = _Recorder()
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(0, rec.n, "the probe generated during live narration")
        self.assertFalse(out["probe_ran"])
        self.assertTrue(out["narration_live"])
        self.assertIn("narrator", (out["llm_error"] or "").lower())

    def test_a_probe_is_permitted_after_the_quiet_window(self):
        self._with_quiet(999.0)
        rec = _Recorder(result='{"status":"ok"}')
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(1, rec.n)
        self.assertTrue(out["probe_ran"])
        self.assertFalse(out["narration_live"])

    def test_a_model_that_has_never_generated_is_idle_not_busy(self):
        """None means nothing has ever run. That is genuinely idle and
        must not be confused with 'unknown'."""
        self._with_quiet(None)
        rec = _Recorder(result='{"status":"ok"}')
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(1, rec.n)
        self.assertFalse(out["narration_live"])

    def test_the_quiet_window_is_operator_tunable(self):
        os.environ["HORNELORE_DIAG_PROBE_QUIET_SEC"] = "1"
        self._with_quiet(5.0)
        rec = _Recorder(result='{"status":"ok"}')
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(1, rec.n, "a 5s-quiet model should pass a 1s window")
        self.assertEqual(1.0, out["probe_quiet_window_sec"])

    def test_a_plain_get_is_never_blocked_by_the_interlock(self):
        """The observational read must stay safe to call at any moment.
        Blocking it would defeat the purpose of making it passive."""
        self._with_quiet(0.1)
        out = E.extract_diag()
        self.assertTrue(out["observational"])
        self.assertIn("llm_cache_age_sec", out)

    def test_the_marker_is_at_every_generate_site(self):
        """A marker on the chat path alone would miss drafting,
        follow-ups and summaries -- three of the four competitors."""
        api_src = (_SERVER / "api" / "api.py").read_text(encoding="utf-8")
        tree = ast.parse(api_src)
        gens = sum(1 for n in ast.walk(tree)
                   if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "generate"
                   and getattr(n.func.value, "id", "") == "model")
        marks = sum(1 for n in ast.walk(tree)
                    if isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "_mark_generation")
        self.assertGreaterEqual(gens, 2)
        self.assertGreaterEqual(
            marks, 3,
            f"{gens} model.generate call(s) but only {marks} marker(s); "
            "the threaded streaming site is easy to miss because its "
            "generate is a `target=` argument, not a statement")

    def test_an_unreadable_signal_is_treated_as_BUSY_not_idle(self):
        """The fail-safe direction, and the one that matters.

        Added after mutation M2 survived: flipping the except-branch
        default from "busy" to "idle" broke nothing, because no test
        exercised the case where the activity signal cannot be read at
        all. A guard that silently permits the thing it guards whenever
        it cannot see is worse than no guard, because it looks like one.
        """
        mod = sys.modules.get("api.api")
        if mod is None:
            mod = types.ModuleType("api.api")
            sys.modules["api.api"] = mod

        def _boom():
            raise RuntimeError("activity signal unavailable")

        mod.seconds_since_generation = _boom
        rec = _Recorder(result='{"status":"ok"}')
        self._li._try_call_llm = rec
        out = E.extract_diag(probe=1)
        self.assertEqual(0, rec.n,
                         "the probe generated while its guard was blind")
        self.assertFalse(out["probe_ran"])
        self.assertTrue(out["narration_live"],
                        "an unreadable signal must report as live, not idle")
