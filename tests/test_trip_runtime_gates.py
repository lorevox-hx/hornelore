"""WO-TRIP-NARRATOR-BRIDGE-01 section A — the runtime gate readout.

The work order asks for a preflight that prints

    trip_interview_context_enabled=true
    trip_story_capture_enabled=true
    trip_shelf_turn_link_enabled=true

and says "acceptance must print only boolean gate states -- not secrets
or configuration values". Both halves of that are tested here: the
route answers the question, and it cannot answer any other one.

It also pins the thing that made the readout necessary. A flag set in a
terminal that never reached the serving process is how the first Gate 7
live run was voided, so the route must read the SAME predicate the
feature reads, in the SAME process. A copy of the parsing rule would
pass this file and still lie on Chris's laptop.

Real FastAPI TestClient against a minimal app mounting trips.router
only, with the same skip posture as test_trip_days_http_sequence: never
hot-swap fastapi in sys.modules, because sibling files bind
HTTPException at import time.
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

_HAVE_FASTAPI = False
_fastapi_mod = sys.modules.get("fastapi")
if _fastapi_mod is not None and getattr(_fastapi_mod, "__file__", None) is None:
    # A sibling file already stubbed it. Never hot-swap the real module
    # back in: sibling files bind HTTPException at import time and would
    # then be catching a different class than the router raises.
    _HAVE_FASTAPI = False
else:
    try:
        from fastapi import FastAPI  # noqa: E402
        from fastapi.testclient import TestClient  # noqa: E402
        _HAVE_FASTAPI = True
    except Exception:  # pragma: no cover
        _HAVE_FASTAPI = False

if not _HAVE_FASTAPI and "fastapi" not in sys.modules:
    # No real fastapi in this environment. Install the same offline stub
    # the rest of tests/ uses, so the route FUNCTION is still exercised
    # even where the HTTP layer cannot be. Installed only after the real
    # import has been tried, so a machine that has fastapi never gets
    # the stub and never loses the HTTP test.
    import types

    _stub = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def _deco(self, *a, **k):
            def wrap(f):
                return f
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    _stub.APIRouter = _APIRouter
    _stub.HTTPException = _HTTPException
    _stub.Query = lambda default=None, **k: default
    _stub.File = lambda default=None, **k: default
    _stub.Form = lambda default=None, **k: default
    _stub.UploadFile = object
    sys.modules["fastapi"] = _stub

if "pydantic" not in sys.modules:
    import types as _t

    _pstub = _t.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kw):
            for _k, _v in kw.items():
                setattr(self, _k, _v)

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    _pstub.BaseModel = _BaseModel
    _pstub.Field = _field
    _pstub.field_validator = lambda *a, **k: (lambda f: f)
    _pstub.validator = lambda *a, **k: (lambda f: f)
    _pstub.ConfigDict = dict
    sys.modules["pydantic"] = _pstub

from api.services import trip_interview_context as _tic  # noqa: E402
from api.services import trip_placement as _tp  # noqa: E402
from api.services import trip_story_capture as _tsc  # noqa: E402

_FLAGS = (
    "HORNELORE_TRIP_INTERVIEW_CONTEXT",
    "HORNELORE_TRIP_STORY_CAPTURE",
    "HORNELORE_TRIP_SHELF_TURN_LINK",
    "HORNELORE_TRIPS",
)

# The three names the work order requires, spelled exactly as it spells
# them. A rename is a broken acceptance script, so it is a failing test.
_REQUIRED = (
    "trip_interview_context_enabled",
    "trip_story_capture_enabled",
    "trip_shelf_turn_link_enabled",
)


class _FlagCase(unittest.TestCase):
    """Every test starts from a clean environment and puts it back.

    Left-behind flags are the classic way one test file turns a default
    -off feature on for another, so the whole set is saved and restored
    rather than only the ones a given test touches."""

    def setUp(self):
        self._saved = dict((k, os.environ.get(k)) for k in _FLAGS)
        for k in _FLAGS:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _on(self, *names):
        for n in names:
            os.environ[n] = "1"


class GatePredicateTest(_FlagCase):
    """The predicates themselves, with no HTTP in the way."""

    def test_all_three_are_off_when_nobody_set_anything(self):
        """Default-off is the whole rollout posture. A flag that
        defaults on ships the behaviour to everyone the moment the file
        merges, which is the opposite of what a rollout flag is for."""
        self.assertFalse(_tic.context_enabled())
        self.assertFalse(_tsc.capture_enabled())
        self.assertFalse(_tp.shelf_link_enabled())

    def test_the_public_gate_name_is_the_same_gate_the_turn_reads(self):
        """context_enabled() exists so the readout can ask the question
        without reaching into a private name. If it ever stops agreeing
        with _flag_on the readout starts describing a second flag that
        nothing else consults."""
        for value in ("1", "0", "true", "no", "", "on"):
            os.environ["HORNELORE_TRIP_INTERVIEW_CONTEXT"] = value
            self.assertEqual(_tic.context_enabled(), _tic._flag_on(),
                             "disagreed on %r" % value)

    def test_the_three_words_that_mean_yes_are_the_same_everywhere(self):
        """Three modules parse three env vars. If one of them accepts
        'on' and another does not, the preflight prints true for a
        behaviour that is off, which is worse than printing nothing."""
        for value in ("1", "true", "TRUE", "yes", "on", " 1 "):
            self._on()
            for n in _FLAGS[:3]:
                os.environ[n] = value
            self.assertTrue(_tic.context_enabled(), value)
            self.assertTrue(_tsc.capture_enabled(), value)
            self.assertTrue(_tp.shelf_link_enabled(), value)
        for value in ("0", "false", "no", "off", "", "  ", "maybe", "2"):
            for n in _FLAGS[:3]:
                os.environ[n] = value
            self.assertFalse(_tic.context_enabled(), value)
            self.assertFalse(_tsc.capture_enabled(), value)
            self.assertFalse(_tp.shelf_link_enabled(), value)


class GateReadoutFunctionTest(_FlagCase):
    """The route function itself, called directly.

    fastapi is not installed everywhere this suite runs, and a check
    that only exists behind TestClient is a check that quietly stops
    running. The HTTP class below proves the wiring; this one proves the
    answer, and it proves it in every environment."""

    def _gates(self):
        from api.routers import trips as _trips
        importlib.reload(_trips)
        return _trips.trip_runtime_gates()

    def test_off_is_off_and_the_call_still_succeeds(self):
        body = self._gates()
        for k in _REQUIRED:
            self.assertIn(k, body)
            self.assertIs(body[k], False)

    def test_on_is_on(self):
        self._on(*_FLAGS)
        body = self._gates()
        for k in _REQUIRED:
            self.assertIs(body[k], True, k)

    def test_nothing_but_booleans_comes_back(self):
        os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = "yes"
        body = self._gates()
        for k, v in body.items():
            self.assertIsInstance(v, bool, "%s carried %r" % (k, type(v)))


@unittest.skipUnless(
    _HAVE_FASTAPI,
    "fastapi + fastapi.testclient are required for the gate readout test")
class GateReadoutHttpTest(_FlagCase):

    def _client(self):
        from api.routers import trips as _trips
        importlib.reload(_trips)
        app = FastAPI()
        app.include_router(_trips.router)
        return TestClient(app)

    def test_the_readout_answers_even_when_every_trip_flag_is_off(self):
        """A preflight whose job is to say whether the trip features are
        on cannot itself 404 when they are off. A 404 reads as a broken
        server and sends the operator looking for the wrong problem."""
        r = self._client().get("/api/trips/runtime-gates")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for k in _REQUIRED:
            self.assertIn(k, body)
            self.assertFalse(body[k])
        self.assertFalse(body["trips_enabled"])

    def test_it_reports_what_this_process_actually_has(self):
        self._on(*_FLAGS)
        body = self._client().get("/api/trips/runtime-gates").json()
        for k in _REQUIRED:
            self.assertTrue(body[k], k)
        self.assertTrue(body["trips_enabled"])

    def test_each_gate_moves_on_its_own(self):
        """Three separate flags, so three separate answers. One switch
        that turns on three behaviours would make the preflight's three
        lines decoration."""
        for flag, key in zip(_FLAGS[:3], _REQUIRED):
            for k in _FLAGS:
                os.environ.pop(k, None)
            self._on(flag)
            body = self._client().get("/api/trips/runtime-gates").json()
            for other in _REQUIRED:
                self.assertEqual(body[other], other == key,
                                 "%s while only %s was set" % (other, flag))

    def test_it_returns_booleans_and_nothing_else(self):
        """The rule the work order states outright. These flags live in
        a file next to API keys and database paths, and an endpoint that
        echoed the value of a named variable would be a way to read any
        of them. true or false is the entire question a preflight asks."""
        os.environ["HORNELORE_TRIP_INTERVIEW_CONTEXT"] = "1"
        os.environ["HORNELORE_TRIP_STORY_CAPTURE"] = "yes"
        os.environ["HORNELORE_TRIP_SHELF_TURN_LINK"] = "on"
        os.environ["HORNELORE_TRIPS"] = "1"
        body = self._client().get("/api/trips/runtime-gates").json()
        for k, v in body.items():
            self.assertIsInstance(v, bool, "%s carried %r" % (k, type(v)))
        blob = repr(body).lower()
        for word in ("yes", "on", "hornelore_", "path", "key", "secret",
                     "token", "sqlite"):
            self.assertNotIn(word, blob, "readout leaked %r" % word)

    def test_the_shelf_flag_is_the_new_one_and_it_is_off_by_default(self):
        """Section A adds HORNELORE_TRIP_SHELF_TURN_LINK=0 and says to
        turn it on only for the live acceptance. Everything else on can
        still leave Priority 2 dark."""
        self._on("HORNELORE_TRIPS", "HORNELORE_TRIP_INTERVIEW_CONTEXT",
                 "HORNELORE_TRIP_STORY_CAPTURE")
        body = self._client().get("/api/trips/runtime-gates").json()
        self.assertTrue(body["trip_interview_context_enabled"])
        self.assertTrue(body["trip_story_capture_enabled"])
        self.assertFalse(body["trip_shelf_turn_link_enabled"])


class EnvExampleTest(unittest.TestCase):
    """The repository example is not the process, but it is what a new
    checkout inherits, so it has to ship the flag OFF and it has to ship
    the flag at all -- an undocumented switch is one nobody turns on."""

    def test_the_example_ships_the_shelf_flag_default_off(self):
        path = _REPO_ROOT / ".env.example"
        if not path.exists():
            self.skipTest("no .env.example in this checkout")
        text = path.read_text(encoding="utf-8", errors="replace")
        self.assertIn("HORNELORE_TRIP_SHELF_TURN_LINK=0", text)
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("HORNELORE_TRIP_SHELF_TURN_LINK="):
                self.assertEqual(s.split("=", 1)[1].strip(), "0")


if __name__ == "__main__":
    unittest.main()
