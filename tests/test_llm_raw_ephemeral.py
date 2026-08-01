"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 — raw ephemeral LLM mode.

Follow-up hardening shape: raw ephemeral generation is an INTERNAL Python
function (api._generate_raw_ephemeral) called directly by
llm_interview._try_call_llm for prompt_mode="raw_ephemeral". It sends the
supplied system + user prompts VERBATIM: no compose_system_prompt (so no
DEFAULT_CORE persona, no PROFILE_JSON context block, no pinned RAG /
golden-mock docs), no extract_profile_json_from_ui_system, no session/
profile/turn persistence, and it has no conv_id parameter at all.

The public HTTP surface is composed-only: prompt_mode is NOT a declared
_ChatReq field, and a request smuggling prompt_mode='raw_ephemeral'
through extra="allow" is REJECTED with 400 by chat() and chat_stream() —
never honored, never silently composed.

Test style mirrors test_trip_draft.py: stub/monkeypatch at module
boundaries. Generation is stubbed at the single non-streaming entry
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
        # applied, kwargs override (extra kwargs kept, mirroring
        # extra="allow"). No validation/coercion (tests pass ChatTurn
        # instances explicitly so this also matches real pydantic).
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

# ── SERVING-STACK STUBS (WO-EXTRACTION-...-01 Phase 5, 2026-07-31) ──────
#
# api.py imports torch, six names from transformers, and PeftModel at
# module scope. `.venv` -- the DESIGNATED test environment -- carries none
# of them, so this module died during import with
#
#     ModuleNotFoundError: No module named 'peft'
#
# and unittest reported it as "Ran 1 test ... errors=1" via a synthetic
# _FailedTest. That reads like one failing test. It is zero tests: not a
# single assertion in this file had ever run in `.venv`.
#
# That mattered, because this suite is the closest coverage of the raw
# path Phase 5 now routes extraction through -- so the phase's own
# regression surface was invisible.
#
# STUBBED RATHER THAN INSTALLED, deliberately. Adding peft/torch to the
# test venv would drag the CUDA generation in (`.venv` and `.venv-gpu`
# differ below the web stack by design) and would make a test venv that
# can load a model -- inviting a suite that accidentally loads one. This
# file never needs the serving stack: it monkeypatches _load_model AND
# _generate_text, so no tensor is ever created. It needs the NAMES to
# exist so `import api.api` succeeds.
#
# Only fills genuine gaps. Where the real module is importable -- as in
# `.venv-gpu` -- the real one is used and these stubs never load, so the
# suite cannot start passing because of a fake.
def _stub_if_missing(name, build):
    if name in sys.modules:
        return False
    try:
        __import__(name)
        return False                      # the real one is here; use it
    except Exception:
        pass
    mod = build()
    sys.modules[name] = mod
    return True


def _build_torch():
    t = types.ModuleType("torch")

    class _OOM(RuntimeError):
        """torch.cuda.OutOfMemoryError. A REAL exception class because
        api.py names it in an `except (...)` tuple; a MagicMock there
        raises TypeError at handling time instead of catching."""

    cuda = types.SimpleNamespace(
        is_available=lambda: False,
        # (free, total). api.py divides these, so they must be numbers.
        mem_get_info=lambda: (0, 0),
        empty_cache=lambda: None,
        OutOfMemoryError=_OOM,
    )
    t.cuda = cuda
    t.float16 = "float16"
    t.bfloat16 = "bfloat16"

    class _NoGrad:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    t.no_grad = _NoGrad
    return t


def _build_transformers():
    tr = types.ModuleType("transformers")

    class _StoppingCriteria:
        """Subclassed at api.py module scope (StopOnEvent), so this has to
        be a usable base class rather than a sentinel."""
        def __init__(self, *a, **k): pass

    class _Unloadable:
        @classmethod
        def from_pretrained(cls, *a, **k):
            raise AssertionError(
                "a stubbed serving stack must never load a model -- this "
                "suite stubs _load_model; reaching here means it did not")

    tr.AutoModelForCausalLM = _Unloadable
    tr.AutoTokenizer = _Unloadable
    tr.TextIteratorStreamer = type("TextIteratorStreamer", (), {})
    tr.BitsAndBytesConfig = lambda *a, **k: None
    tr.StoppingCriteria = _StoppingCriteria
    tr.StoppingCriteriaList = list
    tr.GenerationConfig = lambda *a, **k: None
    return tr


def _build_peft():
    p = types.ModuleType("peft")

    class _PeftModel:
        @classmethod
        def from_pretrained(cls, *a, **k):
            raise AssertionError("stubbed peft must never load an adapter")

    p.PeftModel = _PeftModel
    return p


_STUBBED_SERVING = [
    n for n, build in (("torch", _build_torch),
                       ("transformers", _build_transformers),
                       ("peft", _build_peft))
    if _stub_if_missing(n, build)
]

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

_SYS = "TEST DRAFT SYSTEM: use ONLY the evidence."
_USR = "Evidence:\n- approved place: Prague, Czechia"


def _raise(*a, **k):
    raise AssertionError("forbidden call reached a bypassed touchpoint")


class _StubbedChatCase(unittest.TestCase):
    """Monkeypatch _load_model + _generate_text; capture rendered prompts."""

    def setUp(self):
        self.prompts = []
        self.gen_kwargs = []

        def _fake_load_model():
            # SimpleNamespace has no apply_chat_template → plain fallback.
            return (types.SimpleNamespace(), types.SimpleNamespace())

        # WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 5 widened
        # _generate_text with request_kind/budget_components. A double that
        # does not mirror the real signature raises TypeError the moment
        # production passes them, so the kwargs are accepted AND recorded --
        # which turns a signature change into coverage instead of a break.
        def _fake_generate(model, tok, prompt, req, **kw):
            self.prompts.append(prompt)
            self.gen_kwargs.append(dict(kw))
            return "CANNED COMPLETION"

        self._patch(api_mod, "_load_model", _fake_load_model)
        self._patch(api_mod, "_generate_text", _fake_generate)

    def _patch(self, obj, name, value):
        orig = getattr(obj, name)
        setattr(obj, name, value)
        self.addCleanup(setattr, obj, name, orig)

    def _raw(self, system=_SYS, user=_USR):
        """Call the INTERNAL raw ephemeral function directly."""
        return api_mod._generate_raw_ephemeral(
            system, user, temp=0.5, top_p=0.9, max_new=64)

    def _mk_req(self, *, system=_SYS, user=_USR, conv_id=None,
                messages=None, extra=None):
        if messages is None:
            messages = [("system", system), ("user", user)]
        return api_mod._ChatReq(
            messages=[api_mod.ChatTurn(role=r, content=c)
                      for r, c in messages],
            temp=0.5, top_p=0.9, max_new=64,
            conv_id=conv_id, **(extra or {}))

    def _chat(self, **kw):
        """Call the PUBLIC chat() endpoint (composed-only surface)."""
        return api_mod.chat(self._mk_req(**kw))


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


class RawEphemeralInternalTest(_StubbedChatCase):
    """Raw-mode behavior of the internal function + _try_call_llm routing."""

    def test_raw_succeeds_when_composer_raises(self):
        self._patch(api_mod, "compose_system_prompt", _raise)
        self.assertEqual(self._raw(), "CANNED COMPLETION")

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
        self.assertEqual(self._raw(), "CANNED COMPLETION")

    def test_raw_prompt_is_verbatim_and_uncontaminated(self):
        self._patch(api_mod, "compose_system_prompt", _raise)
        system = ("You are a careful travel-memoir drafting assistant. "
                  "Use ONLY the evidence provided. SENTRY-SYS-9Q.")
        user = "Evidence (use only this):\n- approved caption: EV-ANCHOR-7Z"
        self._raw(system=system, user=user)
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

    def test_raw_requires_nonempty_system(self):
        with self.assertRaises(ValueError):
            self._raw(system="")
        with self.assertRaises(ValueError):
            self._raw(system="   ")
        self.assertEqual(self.prompts, [])   # refused BEFORE generation

    def test_try_call_llm_raw_refuses_conv_id_loudly(self):
        # A conv_id combined with raw mode is a programming error — it must
        # raise, never degrade to a persisted composed call or a silent None.
        self._patch(api_mod, "add_turn", _raise)
        with self.assertRaises(ValueError):
            llm_interview._try_call_llm(
                _SYS, _USR, max_new=64, temp=0.5, top_p=0.9,
                conv_id="conv-must-not-persist",
                prompt_mode="raw_ephemeral")
        self.assertEqual(self.prompts, [])   # refused BEFORE generation

    def test_try_call_llm_raw_does_not_use_public_chat(self):
        # llm_interview must call the internal function directly, never the
        # public chat() endpoint.
        self._patch(api_mod, "chat", _raise)
        self._patch(api_mod, "compose_system_prompt", _raise)
        out = llm_interview._try_call_llm(
            _SYS, _USR, max_new=64, temp=0.5, top_p=0.9,
            prompt_mode="raw_ephemeral")
        self.assertEqual(out, "CANNED COMPLETION")

    # ── WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 5 ──────────
    # Extraction now travels this same raw path, so the request_kind it
    # carries has to survive the two hops from _try_call_llm through
    # _generate_raw_ephemeral to _generate_text. If it is dropped anywhere
    # the budget check silently never runs and extraction goes back to
    # being tail-truncated without anybody noticing.

    def test_request_kind_reaches_generation_unchanged(self):
        self._patch(api_mod, "chat", _raise)
        self._patch(api_mod, "compose_system_prompt", _raise)
        llm_interview._try_call_llm(
            _SYS, _USR, max_new=64, temp=0.5, top_p=0.9,
            prompt_mode="raw_ephemeral", request_kind="extraction",
            budget_components={"chars_user": 12})
        self.assertEqual(len(self.gen_kwargs), 1)
        self.assertEqual(self.gen_kwargs[0].get("request_kind"), "extraction")
        self.assertEqual(self.gen_kwargs[0].get("budget_components"),
                         {"chars_user": 12})

    def test_the_sole_raw_caller_passes_request_kind_explicitly(self):
        """Why _generate_raw_ephemeral's own default is unreachable.

        Mutating that default from "chat" to "extraction" changes nothing
        observable, which looks like a coverage gap and is not: this is
        the only production caller and it always passes the value on. The
        default only becomes reachable if someone adds a second caller
        that omits it -- at which point "chat" is the safe answer, since
        an evidence-drafting call refused for exceeding an EXTRACTION
        budget would be a confusing way to fail.

        Pinned so the reasoning survives the next reader.
        """
        import ast
        src = (Path(__file__).resolve().parents[1] / "server" / "code"
               / "api" / "llm_interview.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and getattr(n.func, "id", "") == "_generate_raw_ephemeral"]
        self.assertEqual(len(calls), 1, "sole caller expected")
        kw = {k.arg for k in calls[0].keywords}
        self.assertIn("request_kind", kw,
                      "the caller must pass request_kind explicitly; if it "
                      "stops, the callee's default silently governs")

    def test_the_default_request_kind_is_chat_so_other_raw_callers_are_unchanged(self):
        # draft_travel_section and the other evidence-drafting callers pass
        # no request_kind; they must keep the historical behaviour, which
        # means the tail-slice, not the extraction refusal.
        self._patch(api_mod, "chat", _raise)
        self._patch(api_mod, "compose_system_prompt", _raise)
        llm_interview._try_call_llm(
            _SYS, _USR, max_new=64, temp=0.5, top_p=0.9,
            prompt_mode="raw_ephemeral")
        self.assertEqual(self.gen_kwargs[0].get("request_kind"), "chat")


class PublicSurfaceClosedTest(_StubbedChatCase):
    """The HTTP surface accepts ONLY composed mode — raw is unreachable."""

    def setUp(self):
        super().setUp()
        self.compose_calls = []

        def _fake_compose(conv_id, ui_system=None, user_text=None,
                          runtime71=None):
            self.compose_calls.append(conv_id)
            return "COMPOSED-WRAP " + (ui_system or "")
        self._patch(api_mod, "compose_system_prompt", _fake_compose)

    def test_prompt_mode_not_declared_on_public_contract(self):
        req = self._mk_req()
        self.assertFalse(hasattr(req, "prompt_mode"),
                         "prompt_mode must not be part of the public "
                         "_ChatReq contract")

    def test_chat_rejects_smuggled_raw_mode(self):
        # extra="allow" would let prompt_mode ride along as an extra field —
        # it must be REJECTED, never honored, never silently composed.
        with self.assertRaises(api_mod.HTTPException) as cm:
            self._chat(extra={"prompt_mode": "raw_ephemeral"})
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(self.prompts, [])         # raw path NOT taken
        self.assertEqual(self.compose_calls, [])   # rejected at the boundary

    def test_chat_stream_rejects_smuggled_raw_mode(self):
        with self.assertRaises(api_mod.HTTPException) as cm:
            api_mod.chat_stream(
                self._mk_req(extra={"prompt_mode": "raw_ephemeral"}))
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(self.prompts, [])

    def test_chat_ignores_other_smuggled_prompt_mode_values(self):
        # Non-raw smuggled values behave like any unknown extra field:
        # plain composed behavior (pre-WO public contract).
        out = self._chat(extra={"prompt_mode": "composed"})
        self.assertEqual(out["text"], "CANNED COMPLETION")
        self.assertEqual(len(self.compose_calls), 1)
        self.assertIn("COMPOSED-WRAP", self.prompts[0])


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
        self._chat()
        self.assertEqual(len(self.compose_calls), 1)
        # conv_id=None maps to the legacy 'default' session
        self.assertEqual(self.compose_calls[0]["conv_id"], "default")
        self.assertIn("COMPOSED-WRAP", self.prompts[0])

    def test_composed_with_conv_id_persists_turns(self):
        added = []

        def _count_add_turn(conv_id, role, content, *a, **k):
            added.append((conv_id, role))
        self._patch(api_mod, "add_turn", _count_add_turn)
        out = self._chat(conv_id="conv-persist-1")
        self.assertEqual(out["text"], "CANNED COMPLETION")
        self.assertEqual(
            added, [("conv-persist-1", "user"), ("conv-persist-1", "assistant")])

    def test_composed_without_conv_id_does_not_persist(self):
        self._patch(api_mod, "add_turn", _raise)
        out = self._chat(conv_id=None)
        self.assertEqual(out["text"], "CANNED COMPLETION")


class DraftTravelSectionRawPathTest(_StubbedChatCase):
    """End-to-end: llm_interview.draft_travel_section → _try_call_llm →
    api._generate_raw_ephemeral (INTERNAL — never through public chat()),
    with all composed/persistence touchpoints armed to raise."""

    def _arm(self):
        self._patch(api_mod, "compose_system_prompt", _raise)
        self._patch(api_mod, "extract_profile_json_from_ui_system", _raise)
        self._patch(api_mod, "add_turn", _raise)
        self._patch(api_mod, "upsert_session", _raise)
        self._patch(api_mod, "get_session", _raise)
        self._patch(api_mod, "chat", _raise)   # public endpoint off-limits
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
