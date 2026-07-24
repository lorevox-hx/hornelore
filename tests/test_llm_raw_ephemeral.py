"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 — raw ephemeral chat mode.

api.chat(prompt_mode="raw_ephemeral") must send the supplied system + user
messages VERBATIM: no compose_system_prompt (so no DEFAULT_CORE persona, no
PROFILE_JSON context block, no pinned RAG / golden-mock docs), no
extract_profile_json_from_ui_system, no session/profile/turn persistence,
and a nonempty conv_id is refused loudly. Composed mode keeps the legacy
contract (composer called; conv_id persists turns via add_turn).

Test style mirrors test_trip_draft.py: stub/monkeypatch at module
boundaries. Generation is stubbed at chat()'s single non-streaming entry
(api._generate_text) so no model is ever loaded; the fake tokenizer has no
apply_chat_template so _apply_chat_template renders the plain
ROLE:/content fallback — the captured prompt is exactly the messages that
would reach the model.

Offline fastapi/pydantic stubs use the shared conditional pattern
(test_travelogue_builder / test_travel_doc_evidence_tools) so this module
composes with the rest of the trip-lane suite in one process — importing
REAL fastapi here would break sibling modules that call router functions
directly and rely on stubbed Query defaults.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

if "fastapi" not in sys.modules:
    stub = types.ModuleType("fastapi")

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

    stub.APIRouter = _APIRouter
    stub.HTTPException = _HTTPException
    stub.Query = lambda default=None, **k: default
    stub.Body = lambda default=None, **k: default
    stub.File = lambda default=None, **k: default
    stub.Form = lambda default=None, **k: default
    stub.UploadFile = object
    responses = types.ModuleType("fastapi.responses")

    class _StreamingResponse:
        def __init__(self, content=None, media_type=None, **k):
            self.content, self.media_type = content, media_type

    responses.StreamingResponse = _StreamingResponse
    stub.responses = responses
    sys.modules["fastapi"] = stub
    sys.modules["fastapi.responses"] = responses

if "pydantic" not in sys.modules:
    pstub = types.ModuleType("pydantic")

    class _BaseModel:
        # Enough pydantic for direct construction: class-attr defaults
        # applied, kwargs override. No validation/coercion (tests pass
        # ChatTurn instances explicitly so this also matches real pydantic).
        def __init__(self, **kw):
            for klass in reversed(type(self).__mro__):
                for k, v in vars(klass).items():
                    if k.startswith("_") or callable(v):
                        continue
                    setattr(self, k, v)
            self.__dict__.update(kw)

    pstub.BaseModel = _BaseModel
    pstub.Field = lambda default=None, **k: default
    pstub.field_validator = lambda *a, **k: (lambda f: f)
    pstub.validator = lambda *a, **k: (lambda f: f)
    pstub.ConfigDict = dict
    sys.modules["pydantic"] = pstub

from api import api as api_mod  # noqa: E402  (model load is lazy)
from api import db as db_mod  # noqa: E402
from api import llm_interview  # noqa: E402
from api import prompt_composer  # noqa: E402

# Distinctive contamination markers asserted ABSENT from raw prompts.
# Each is self-checked against the real composer source below so the
# markers can't silently drift away from production.
_MARKER_DEFAULT_CORE = "the voice of your stories"      # DEFAULT_CORE persona
_MARKER_PROFILE = "PROFILE_JSON"                        # session context block
_MARKER_RAG = "[ORAL_HISTORY_GUIDELINES]"               # pinned RAG doc header
_MARKER_GOLDEN = "[GOLDEN_MOCK]"                        # pinned golden mock


def _raise(*a, **k):
    raise AssertionError("forbidden call reached a bypassed touchpoint")


class _StubbedChatCase(unittest.TestCase):
    """Monkeypatch _load_model + _generate_text; capture rendered prompts."""

    def setUp(self):
        self.prompts = []

        def _fake_load_model():
            # SimpleNamespace has no apply_chat_template → plain fallback.
            return (types.SimpleNamespace(), types.SimpleNamespace())

        def _fake_generate(model, tok, prompt, req):
            self.prompts.append(prompt)
            return "CANNED COMPLETION"

        self._patch(api_mod, "_load_model", _fake_load_model)
        self._patch(api_mod, "_generate_text", _fake_generate)

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _chat(self, *, system="TEST DRAFT SYSTEM: use ONLY the evidence.",
              user="Evidence:\n- approved place: Prague, Czechia",
              mode="raw_ephemeral", conv_id=None, messages=None):
        if messages is None:
            messages = [("system", system), ("user", user)]
        req = api_mod._ChatReq(
            messages=[api_mod.ChatTurn(role=r, content=c)
                      for r, c in messages],
            temp=0.5, top_p=0.9, max_new=64,
            conv_id=conv_id, prompt_mode=mode)
        return api_mod.chat(req)


class MarkerSelfCheckTest(unittest.TestCase):
    """The absence assertions below are only meaningful if the markers are
    really what the composer emits — lock them to production source."""

    def test_markers_exist_in_composer(self):
        self.assertIn(_MARKER_DEFAULT_CORE, prompt_composer.DEFAULT_CORE)
        import inspect
        src = inspect.getsource(prompt_composer.compose_system_prompt)
        self.assertIn(_MARKER_PROFILE, src)
        self.assertIn(_MARKER_RAG, src)
        self.assertIn(_MARKER_GOLDEN, src)


class RawEphemeralModeTest(_StubbedChatCase):
    def test_raw_succeeds_when_composer_raises(self):
        self._patch(api_mod, "compose_system_prompt", _raise)
        out = self._chat()
        self.assertTrue(out["ok"])
        self.assertEqual(out["text"], "CANNED COMPLETION")

    def test_raw_succeeds_when_persistence_raises(self):
        # Every session/profile/turn persistence touchpoint armed to blow.
        self._patch(api_mod, "compose_system_prompt", _raise)
        self._patch(api_mod, "extract_profile_json_from_ui_system", _raise)
        self._patch(api_mod, "add_turn", _raise)
        self._patch(api_mod, "upsert_session", _raise)
        self._patch(api_mod, "get_session", _raise)
        self._patch(db_mod, "ensure_session", _raise)
        self._patch(db_mod, "add_turn", _raise)
        self._patch(db_mod, "upsert_session", _raise)
        out = self._chat()
        self.assertEqual(out["text"], "CANNED COMPLETION")

    def test_raw_prompt_is_verbatim_and_uncontaminated(self):
        self._patch(api_mod, "compose_system_prompt", _raise)
        system = ("You are a careful travel-memoir drafting assistant. "
                  "Use ONLY the evidence provided. SENTRY-SYS-9Q.")
        user = "Evidence (use only this):\n- approved caption: EV-ANCHOR-7Z"
        self._chat(system=system, user=user)
        self.assertEqual(len(self.prompts), 1)
        prompt = self.prompts[0]
        # exact supplied system text + evidence reach generation
        self.assertIn("SENTRY-SYS-9Q", prompt)
        self.assertIn(system, prompt)
        self.assertIn("EV-ANCHOR-7Z", prompt)
        # no composed wrap markers
        self.assertNotIn(_MARKER_DEFAULT_CORE, prompt)
        self.assertNotIn(_MARKER_PROFILE, prompt)
        self.assertNotIn(_MARKER_RAG, prompt)
        self.assertNotIn(_MARKER_GOLDEN, prompt)

    def test_raw_refuses_conv_id(self):
        self._patch(api_mod, "add_turn", _raise)
        with self.assertRaises(api_mod.HTTPException) as cm:
            self._chat(conv_id="conv-must-not-persist")
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(self.prompts, [])   # refused BEFORE generation

    def test_raw_requires_nonempty_system(self):
        with self.assertRaises(api_mod.HTTPException) as cm:
            self._chat(messages=[("user", "hi")])
        self.assertEqual(cm.exception.status_code, 400)
        with self.assertRaises(api_mod.HTTPException):
            self._chat(system="   ")
        self.assertEqual(self.prompts, [])

    def test_raw_rejected_on_stream_endpoint(self):
        req = api_mod._ChatReq(
            messages=[api_mod.ChatTurn(role="system", content="s"),
                      api_mod.ChatTurn(role="user", content="u")],
            prompt_mode="raw_ephemeral")
        with self.assertRaises(api_mod.HTTPException) as cm:
            api_mod.chat_stream(req)
        self.assertEqual(cm.exception.status_code, 400)


class ComposedModeStillComposesTest(_StubbedChatCase):
    def setUp(self):
        super().setUp()
        self.compose_calls = []

        def _fake_compose(conv_id, ui_system=None, user_text=None,
                          runtime71=None):
            self.compose_calls.append({"conv_id": conv_id,
                                       "ui_system": ui_system})
            return "COMPOSED-WRAP " + (ui_system or "")
        self._patch(api_mod, "compose_system_prompt", _fake_compose)

    def test_composed_mode_calls_composer(self):
        self._chat(mode="composed")
        self.assertEqual(len(self.compose_calls), 1)
        # conv_id=None maps to the legacy 'default' session
        self.assertEqual(self.compose_calls[0]["conv_id"], "default")
        self.assertIn("COMPOSED-WRAP", self.prompts[0])

    def test_composed_default_mode_field(self):
        req = api_mod._ChatReq(messages=[
            api_mod.ChatTurn(role="user", content="hi")])
        self.assertEqual(req.prompt_mode, "composed")

    def test_composed_with_conv_id_persists_turns(self):
        added = []

        def _count_add_turn(conv_id, role, content, *a, **k):
            added.append((conv_id, role))
        self._patch(api_mod, "add_turn", _count_add_turn)
        out = self._chat(mode="composed", conv_id="conv-persist-1")
        self.assertEqual(out["text"], "CANNED COMPLETION")
        self.assertEqual(
            added, [("conv-persist-1", "user"), ("conv-persist-1", "assistant")])

    def test_composed_without_conv_id_does_not_persist(self):
        self._patch(api_mod, "add_turn", _raise)
        out = self._chat(mode="composed", conv_id=None)
        self.assertEqual(out["text"], "CANNED COMPLETION")


class DraftTravelSectionRawPathTest(_StubbedChatCase):
    """End-to-end: llm_interview.draft_travel_section → _try_call_llm →
    api.chat in raw_ephemeral mode, with all composed/persistence
    touchpoints armed to raise."""

    def _arm(self):
        self._patch(api_mod, "compose_system_prompt", _raise)
        self._patch(api_mod, "extract_profile_json_from_ui_system", _raise)
        self._patch(api_mod, "add_turn", _raise)
        self._patch(api_mod, "upsert_session", _raise)
        self._patch(api_mod, "get_session", _raise)
        self._patch(db_mod, "ensure_session", _raise)

    def test_draft_travel_section_is_raw_and_uncontaminated(self):
        self._arm()
        out = llm_interview.draft_travel_section(
            scope_title="Prague",
            instruction="Warm and short.",
            evidence_text="- approved caption: Charles Bridge EV-ANCHOR-7Z")
        self.assertEqual(out, "CANNED COMPLETION")
        self.assertEqual(len(self.prompts), 1)
        prompt = self.prompts[0]
        # the exact draft system text and evidence reached generation
        self.assertIn("use ONLY the evidence provided", prompt)
        self.assertIn("no trains, stations, airports, flights, cars, buses, "
                      "or walking", prompt)
        self.assertIn("Charles Bridge EV-ANCHOR-7Z", prompt)
        # and none of the composed wrap did
        self.assertNotIn(_MARKER_DEFAULT_CORE, prompt)
        self.assertNotIn(_MARKER_PROFILE, prompt)
        self.assertNotIn(_MARKER_RAG, prompt)
        self.assertNotIn(_MARKER_GOLDEN, prompt)

    def test_other_helpers_stay_composed(self):
        compose_calls = []

        def _fake_compose(conv_id, ui_system=None, user_text=None,
                          runtime71=None):
            compose_calls.append(conv_id)
            return "COMPOSED-WRAP"
        self._patch(api_mod, "compose_system_prompt", _fake_compose)
        out = llm_interview.draft_section_summary(
            section_title="Childhood", instruction="Summarize.",
            transcript="Q: where? A: Prague.")
        self.assertEqual(out, "CANNED COMPLETION")
        self.assertEqual(compose_calls, ["default"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
