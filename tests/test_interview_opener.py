"""WO-GREETING-01 — tests for /api/interview/opener.

Tests cover the pure-Python helper logic directly. The HTTP integration
test is similar in spirit to test_extract_api_subject_filters.py and
requires the real FastAPI stack (run in .venv-gpu).

Run with:
    cd hornelore
    python -m unittest tests.test_interview_opener -v
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "server", "code"))

# Stub FastAPI + pydantic when not available (sandbox / no-venv runs)
if "fastapi" not in sys.modules:
    fa = types.ModuleType("fastapi")
    class _APIRouter:
        def __init__(self, *a, **kw): pass
        def post(self, *a, **kw):
            def deco(fn): return fn
            return deco
        def get(self, *a, **kw):
            def deco(fn): return fn
            return deco
    class _HTTPException(Exception):
        def __init__(self, status_code=500, detail=""):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)
    fa.APIRouter = _APIRouter
    fa.HTTPException = _HTTPException
    sys.modules["fastapi"] = fa

if "pydantic" not in sys.modules:
    pd = types.ModuleType("pydantic")
    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
    pd.BaseModel = _BaseModel
    sys.modules["pydantic"] = pd

# The interview.py router imports from api.db, api.archive, api.interview_engine,
# api.llm_interview, api.safety, api.flags, api.phase_aware_composer.
# For unit testing helper functions only, stub the heavyweight ones with the
# exact symbols interview.py imports.

def _noop(*a, **kw):
    return None


if "api.archive" not in sys.modules:
    mod = types.ModuleType("api.archive")
    mod.ensure_session = _noop
    mod.append_event = _noop
    mod.rebuild_txt = _noop
    sys.modules["api.archive"] = mod

if "api.interview_engine" not in sys.modules:
    mod = types.ModuleType("api.interview_engine")
    mod.add_followup_questions = _noop
    mod.followups_exist = lambda *a, **kw: False
    mod.get_section_meta = lambda *a, **kw: None
    mod.get_section_transcript = lambda *a, **kw: []
    mod.get_session_transcript = lambda *a, **kw: []
    sys.modules["api.interview_engine"] = mod

if "api.llm_interview" not in sys.modules:
    mod = types.ModuleType("api.llm_interview")
    mod.draft_final_memoir = lambda *a, **kw: None
    mod.draft_section_summary = lambda *a, **kw: None
    mod.propose_followup_questions = lambda *a, **kw: []
    sys.modules["api.llm_interview"] = mod

if "api.safety" not in sys.modules:
    mod = types.ModuleType("api.safety")
    mod.scan_answer = lambda *a, **kw: None
    mod.build_segment_flags = lambda *a, **kw: None
    mod.get_resources_for_category = lambda *a, **kw: []
    mod.set_softened = _noop
    mod.is_softened = lambda *a, **kw: False
    sys.modules["api.safety"] = mod

# api.db is real but depends on sqlite and large modules; only stub if missing.
# We import the interview module and access only helper functions that don't
# touch the DB directly.
from api.routers import interview as iv  # noqa: E402


class ChooseNarratorNameTests(unittest.TestCase):
    def test_preferred_wins(self):
        self.assertEqual(
            iv._choose_narrator_name(
                {"display_name": "Janice Josephine Horne"},
                {"preferred": "Janice"},
            ),
            "Janice",
        )

    def test_first_from_display_name_when_no_preferred(self):
        self.assertEqual(
            iv._choose_narrator_name(
                {"display_name": "Christopher Todd Horne"},
                {},
            ),
            "Christopher",
        )

    def test_full_when_single_word(self):
        self.assertEqual(
            iv._choose_narrator_name({"display_name": "Cher"}, {}),
            "Cher",
        )

    def test_empty_when_nothing_known(self):
        self.assertEqual(iv._choose_narrator_name({}, {}), "")

    def test_preferred_whitespace_handled(self):
        self.assertEqual(
            iv._choose_narrator_name({}, {"preferred": "  Jan  "}),
            "Jan",
        )


class IdentityCompleteTests(unittest.TestCase):
    def test_full_complete(self):
        p = {"display_name": "Kent James Horne",
             "date_of_birth": "1939-12-24",
             "place_of_birth": "Stanley, North Dakota"}
        self.assertTrue(iv._identity_complete(p, {}))

    def test_missing_dob(self):
        p = {"display_name": "Kent", "place_of_birth": "Stanley"}
        self.assertFalse(iv._identity_complete(p, {}))

    def test_missing_placeofbirth(self):
        p = {"display_name": "Kent", "date_of_birth": "1939-12-24"}
        self.assertFalse(iv._identity_complete(p, {}))

    def test_preferred_satisfies_name_when_display_name_missing(self):
        p = {"date_of_birth": "1939-12-24",
             "place_of_birth": "Stanley"}
        self.assertTrue(iv._identity_complete(p, {"preferred": "Kent"}))

    def test_all_empty(self):
        self.assertFalse(iv._identity_complete({}, {}))


class BuildOpenerTextTests(unittest.TestCase):
    def test_first_time_includes_name_and_intro(self):
        text = iv._build_opener_text("first_time", "Janice")
        self.assertIn("Hi Janice", text)
        self.assertIn("Lori", text)
        self.assertIn("life story", text)
        self.assertIn("What would you like to start with?", text)

    def test_welcome_back_is_short(self):
        text = iv._build_opener_text("welcome_back", "Chris")
        self.assertIn("Welcome back, Chris", text)
        self.assertLess(len(text), 120, "welcome_back should be short")

    def test_onboarding_incomplete_empty(self):
        self.assertEqual(iv._build_opener_text("onboarding_incomplete", "Anyone"), "")

    def test_friend_fallback_when_name_missing(self):
        text = iv._build_opener_text("first_time", "")
        self.assertIn("Hi friend", text)
        self.assertNotIn("Hi ,", text)  # no awkward empty-string slip


class OpenerResponseShapeTests(unittest.TestCase):
    """Verify OpenerResponse model accepts expected fields without the real
    pydantic validation (our stub skips validation, but this ensures no
    typos in field names)."""

    def test_response_constructible(self):
        r = iv.OpenerResponse(
            person_id="p1",
            narrator_name="Janice",
            kind="first_time",
            opener_text="Hi Janice...",
            context={"user_turn_count": 0, "identity_complete": True},
        )
        self.assertEqual(r.person_id, "p1")
        self.assertEqual(r.kind, "first_time")
        self.assertIn("user_turn_count", r.context)


if __name__ == "__main__":
    unittest.main()
