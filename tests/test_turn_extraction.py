"""WO-TRUTH-PIPELINE-01 Phase 2 (Gate 7) — the turn-to-extraction path.

THE DEFECT THIS FILE GUARDS. Gate 7 Phase 1 instrumented five
truth-write stages and ran two live harness turns. Both reported:

    raw_turn_saved=1  archive_event_created=2  extract_fields_called=0
    family_truth_written=0  projection_updated=0

Three of those zeroes look identical and mean different things. Two are
correct by design (family truth is operator-gated; projections are
correction-only). One was a real defect: a completed chat_ws interview
turn never requested field extraction, because /api/extract-fields had
no internal Python caller anywhere under server/code/api — only
ui/js/interview.js posted to it.

Phase 2 closed exactly that gap and nothing else. The governing rule is:

    Connect completed turns to extraction through one shared,
    idempotent, observable, failure-isolated service. Do NOT connect
    interview turns directly to truth.

Each test below maps to one numbered acceptance item of the Phase 2 work
order; the mapping is named in the test docstring so a later reader can
tell which requirement a failure retires.

WHY THE TESTS ARE SHAPED THIS WAY. Every name involved here
(extract_fields, run_field_extraction, ft_add_row, apply_correction)
also appears in the comments and docstrings of the files being checked
— this file included. A substring guard would pass on prose while
missing a real call, which is the exact failure mode CLAUDE.md warns
about. So the structural assertions read the AST, and the behavioural
assertions run the real service against a real sqlite database with a
fake extractor injected at the one seam.
"""
from __future__ import annotations

import ast
import asyncio
import os
import sqlite3
import sys
import threading
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# ── fastapi / pydantic stubs ──────────────────────────────────────────────
# routers/extract.py imports both at module scope. The repo convention
# (see tests/test_captured_note_review.py) is to stub them rather than
# require the web stack for a unit test.
if "fastapi" not in sys.modules:
    _f = types.ModuleType("fastapi")

    class _APIRouter:
        def __init__(self, *a, **k):
            pass

        def _deco(self, *a, **k):
            def wrap(fn):
                return fn
            return wrap
        get = post = patch = delete = put = _deco

    class _HTTPException(Exception):
        def __init__(self, status_code=0, detail=""):
            self.status_code, self.detail = status_code, detail
            super().__init__(detail)

    _f.APIRouter = _APIRouter
    _f.HTTPException = _HTTPException
    _f.Query = lambda default=None, **k: default
    _f.File = lambda default=None, **k: default
    _f.Form = lambda default=None, **k: default
    _f.UploadFile = object
    _resp = types.ModuleType("fastapi.responses")
    _resp.StreamingResponse = object
    _resp.JSONResponse = object
    _f.responses = _resp
    sys.modules["fastapi"] = _f
    sys.modules["fastapi.responses"] = _resp

if "pydantic" not in sys.modules:
    _p = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    def _field(default=None, default_factory=None, **k):
        if default_factory is not None:
            return default_factory()
        return default

    _p.BaseModel = _BaseModel
    _p.Field = _field
    _p.field_validator = lambda *a, **k: (lambda fn: fn)
    _p.validator = lambda *a, **k: (lambda fn: fn)
    _p.ConfigDict = dict
    sys.modules["pydantic"] = _p

from api import db as _db                                    # noqa: E402
from api.routers import extract as _extract_router           # noqa: E402
from api.services import turn_extraction as tx               # noqa: E402
from api.services import truth_pipeline_probe as _tp         # noqa: E402

_CHAT_WS = _SERVER_CODE / "api" / "routers" / "chat_ws.py"
_EXTRACT_ROUTER = _SERVER_CODE / "api" / "routers" / "extract.py"
_SERVICE = _SERVER_CODE / "api" / "services" / "turn_extraction.py"


_MAIN_PY = _SERVER_CODE / "api" / "main.py"
_HARNESS_ROUTER = _SERVER_CODE / "api" / "routers" / "operator_harness.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _string_values(tree) -> set:
    """Every string CONSTANT in the tree that is not a docstring.

    A guard written against a word fires on the documentation that
    quotes the word. Docstrings are prose, so they are excluded here for
    the same reason comments are: the thing under test is whether the
    module holds a route path as a VALUE it could send a request to.
    """
    docstrings = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    }


def _enclosing_function(tree, lineno: int) -> str:
    """Name of the innermost function whose body spans `lineno`.

    Ordering facts in chat_ws.py have to be asserted WITHIN a function.
    The module is over four thousand lines long and defines the
    extraction hook near the top while the persistence path it guards
    lives near the bottom, so raw file offsets carry no information
    about runtime order.
    """
    best = ""
    best_line = -1
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.lineno <= lineno <= (node.end_lineno or node.lineno):
            if node.lineno > best_line:
                best, best_line = node.name, node.lineno
    return best


def _called_names(tree) -> set:
    """Terminal callee names, alias-resolved. Comments reduce to nothing."""
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.asname:
                    aliases[a.asname] = a.name
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Name):
            out.add(aliases.get(fn.id, fn.id))
        elif isinstance(fn, ast.Attribute):
            out.add(aliases.get(fn.attr, fn.attr))
    return out


class _FakeItem:
    """Stands in for ExtractedItem. model_dump() is the shape the service
    normalises through, so the fake honours it."""

    def __init__(self, path="birth.place", value="Mandan"):
        self.fieldPath, self.value = path, value

    def model_dump(self):
        return {"fieldPath": self.fieldPath, "value": self.value}


class _FakeResponse:
    def __init__(self, items=None, method="fake"):
        self.items = list(items or [])
        self.method = method
        self.raw_llm_output = ""
        self.clarification_required = False


class _ServiceCase(unittest.TestCase):
    """Real sqlite, real service, fake extractor.

    The extractor is replaced at exactly one seam — tx._call_extractor
    — because that is the single place the shared implementation is
    invoked. Patching there proves the wiring without spending an LLM
    call, and if a future change adds a second way in, the "one internal
    caller" test in tests/test_truth_pipeline_probe.py fails first.
    """

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.narrator_id = f"harness-test-{uuid.uuid4()}"
        self.conv_id = f"conv-{self.narrator_id}"

        self._orig_call = tx._call_extractor
        self.calls = []          # every req handed to the extractor
        self._response = _FakeResponse([_FakeItem()])
        self._raise = None

        def _fake(req):
            self.calls.append(req)
            if self._raise is not None:
                raise self._raise
            return self._response

        tx._call_extractor = _fake

        self._orig_force = os.environ.pop("HORNELORE_EXTRACTION_FORCE_FAILURE", None)

    def tearDown(self):
        tx._call_extractor = self._orig_call
        _db.DB_PATH = self._orig_db
        if self._orig_force is not None:
            os.environ["HORNELORE_EXTRACTION_FORCE_FAILURE"] = self._orig_force
        else:
            os.environ.pop("HORNELORE_EXTRACTION_FORCE_FAILURE", None)
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # helpers ————————————————————-
    def _save_turn(self, user_text="I was born in Mandan in 1958."):
        """Commit one turn the way chat_ws does, returning its stable key."""
        row_id = _db.persist_turn_transaction(
            conv_id=self.conv_id,
            user_message=user_text,
            assistant_message="Tell me more about Mandan.",
            model_name="test",
        )
        return row_id, _db.turn_extraction_key_for_row(row_id)

    def _extract(self, turn_key, **kw):
        params = dict(
            narrator_id=self.narrator_id,
            turn_id=kw.pop("turn_id", "t-1"),
            user_text=kw.pop("user_text", "I was born in Mandan in 1958."),
            session_id=self.conv_id,
            turn_key=turn_key,
            turn_mode=kw.pop("turn_mode", "interview"),
        )
        params.update(kw)
        return asyncio.run(tx.extract_completed_turn(**params))

    def _count(self, table, column, value):
        con = sqlite3.connect(str(self.db_path))
        try:
            return int(con.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (value,)
            ).fetchone()[0])
        except sqlite3.OperationalError:
            return 0
        finally:
            con.close()


# ══ 0. A directive is not the narrator ═══════════════════════════════════

# The four in-band directives ui/js/session-loop.js actually sent during
# the 2026-07-31 Bismarck session, copied from api.log. They arrive as
# USER-role WebSocket payloads carrying turn_mode='interview' and they
# persist an ordinary `turns` row, so every guard in _begin() said yes to
# them and the extractor was handed an operator instruction to mine for
# biography. One came back as
#
#   fieldPath="system.message"  value="The narrator has been quiet..."
#
# rejected by EXTRACTABLE_FIELDS -- after the model call had been paid
# for, on a GPU the narrator was waiting on.
JULY_31_DIRECTIVES = {
    "trip_opened": (
        "[SYSTEM: The narrator just opened their trip 'Bismarck Trip' "
        "(2026-07-14 to 2026-07-19) from the Travels shelf on the Life "
        "Map. Ask ONE warm question inviting them to begin telling the "
        "story of this journey wherever they'd like.]"
    ),
    "quiet_invitation": (
        "[SYSTEM: The narrator has been quiet for a while. Offer a "
        "gentle, warm invitation to continue their life story — one "
        "short sentence only.]"
    ),
    "photo_added": (
        "[SYSTEM: The narrator just added 1 photo to their trip "
        "'Bismarck Trip'. Invite them, in ONE short warm question, to "
        "tell you about it.]"
    ),
    "photo_selected": (
        "[SYSTEM: The narrator is looking at a photo from their trip "
        "'Bismarck Trip'. Invite them to tell you about this photo in "
        "their own words.]"
    ),
}


class SystemDirectiveIsNotExtractedTest(_ServiceCase):
    """WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 1.

    Required of a directive payload: zero ledger claims, zero extractor
    model calls, zero projection writes, zero Shadow Review claims. The
    first two are asserted here directly; the second two follow, because
    a projection write and a Shadow Review claim are both built from
    extracted items and there are none.
    """

    def _schedule(self, turn_key, user_text, directive):
        return asyncio.run(self._sched(turn_key, user_text, directive))

    async def _sched(self, turn_key, user_text, directive):
        out = tx.schedule_completed_turn_extraction(
            narrator_id=self.narrator_id,
            turn_id="t-directive",
            user_text=user_text,
            session_id=self.conv_id,
            turn_key=turn_key,
            turn_mode="interview",
            is_system_directive=directive,
        )
        await tx.drain_pending_extractions()
        return out

    def _ledger_rows(self):
        return self._count("turn_extraction_ledger",
                           "narrator_id", self.narrator_id)

    # -- the four real ones ------------------------------------------

    def test_the_july_31_directives_are_never_extracted(self):
        for name, text in JULY_31_DIRECTIVES.items():
            with self.subTest(directive=name):
                self.calls[:] = []
                row_id, key = self._save_turn(user_text=text)
                before = self._ledger_rows()
                out = self._schedule(key, text, True)
                self.assertEqual(out.status, "noop", name)
                self.assertEqual(out.method, "system_directive", name)
                self.assertEqual(self.calls, [], "extractor was called")
                self.assertEqual(self._ledger_rows(), before,
                                 "a ledger claim was written")
                self.assertIsNone(out.ledger_id, name)
                self.assertEqual(out.items, [], name)
                self.assertEqual(out.item_count, 0, name)

    def test_the_narrator_turn_beside_them_still_extracts(self):
        """The non-vacuity control. A gate that refused everything would
        look identical to a gate that works."""
        self.calls[:] = []
        row_id, key = self._save_turn(
            user_text="I added a picture of the Lewis and Clark Visitor "
                      "Center north of Bismarck.")
        before = self._ledger_rows()
        out = self._schedule(key, "I added a picture...", False)
        self.assertEqual(out.status, "scheduled")
        self.assertEqual(len(self.calls), 1, "extractor should have run")
        self.assertEqual(self._ledger_rows(), before + 1)

    def test_the_default_is_false_so_no_caller_changes_silently(self):
        import inspect
        for fn in (tx.schedule_completed_turn_extraction,
                   tx.extract_completed_turn,
                   tx.begin_completed_turn_extraction):
            sig = inspect.signature(fn)
            self.assertIn("is_system_directive", sig.parameters, fn.__name__)
            self.assertIs(sig.parameters["is_system_directive"].default,
                          False, fn.__name__)

    def test_the_await_entry_point_refuses_them_too(self):
        """schedule_* is the chat_ws door; extract_completed_turn is the
        replay door. Both reach _begin, so both must refuse."""
        self.calls[:] = []
        text = JULY_31_DIRECTIVES["trip_opened"]
        row_id, key = self._save_turn(user_text=text)
        before = self._ledger_rows()
        out = self._extract(key, user_text=text, is_system_directive=True)
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.method, "system_directive")
        self.assertEqual(self.calls, [])
        self.assertEqual(self._ledger_rows(), before)


class SystemDirectiveDecisionLivesAtTheBoundaryTest(unittest.TestCase):
    """The service is handed a verdict; it does not form one.

    Two definitions of "this is a directive" is one more than the system
    can keep in agreement. chat_ws already computes it for story capture
    and trip placement, and this reads that same value.
    """

    def setUp(self):
        self.svc = (_SERVER_CODE / "api" / "services"
                    / "turn_extraction.py").read_text(encoding="utf-8")
        self.ws = (_SERVER_CODE / "api" / "routers"
                   / "chat_ws.py").read_text(encoding="utf-8")

    @staticmethod
    def _executable(src):
        """The module's CODE, with every docstring removed.

        The first version of this test scanned raw source and failed --
        on the comment inside _begin() that exists to explain the rule,
        which necessarily quotes the directive marker it forbids. That
        is the fifth time in this repository that a guard written
        against a WORD has fired on the prose about the word. A guard
        has to match what the interpreter executes.
        """
        tree = ast.parse(src)
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if (isinstance(first, ast.Expr)
                    and isinstance(getattr(first, "value", None), ast.Constant)
                    and isinstance(first.value.value, str)):
                body.pop(0)
                if not body:
                    body.append(ast.Pass())
        return ast.unparse(ast.fix_missing_locations(tree))

    def test_the_service_never_sniffs_the_transcript(self):
        """It receives a verdict. It does not look for one."""
        code = self._executable(self.svc)
        self.assertNotIn("[SYSTEM", code)
        self.assertNotIn("startswith", code)
        # Non-vacuity: the walker really is reading this module's code.
        self.assertIn("is_system_directive", code)

    def test_the_boundary_computes_it_once_and_forwards_it(self):
        self.assertEqual(
            self.ws.count('_is_system_directive = _ut_lstrip.startswith'), 1)
        self.assertIn('params["_is_system_directive"] = _is_system_directive',
                      self.ws)
        self.assertIn("is_system_directive=bool(", self.ws)

    def test_extraction_and_placement_read_the_same_verdict(self):
        """If these ever diverge, a directive lands on one lane and not
        the other, which is worse than it landing on both."""
        self.assertEqual(self.ws.count('params.get("_is_system_directive")'), 2)


# ══ 1. The HTTP endpoint still behaves as before ═════════════════════════
class HttpEndpointUnchangedTest(_ServiceCase):
    """Acceptance item 1.

    The refactor MOVED the extraction body; it did not change it. What can
    be asserted without an LLM is that the endpoint is still a pure
    pass-through: same request object in, same response object out, no
    extra arguments, no ledger row, no swallowed exception.
    """

    def _req(self):
        return _extract_router.ExtractFieldsRequest(
            person_id=self.narrator_id, answer="I was born in Mandan.",
        )

    def test_the_route_returns_the_extractor_result_unchanged(self):
        req = self._req()
        out = _extract_router.extract_fields(req)
        self.assertIs(out, self._response)
        self.assertEqual(len(self.calls), 1)
        self.assertIs(
            self.calls[0], req,
            "the endpoint must hand the extractor the SAME request object "
            "it received. Rebuilding it here would let the HTTP path and "
            "the turn path drift apart silently.",
        )

    def test_the_route_still_propagates_extractor_exceptions(self):
        """Pre-Phase-2 an extractor error surfaced to the HTTP caller. The
        turn path deliberately swallows failures; the HTTP path must NOT
        inherit that, or the browser loses its error reporting."""
        self._raise = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            _extract_router.extract_fields(self._req())

    def test_the_route_takes_no_idempotency_claim(self):
        """A browser that posts the same answer twice deliberately gets two
        extractions, exactly as before. The claim belongs to the turn path,
        which has a committed row to key on; the HTTP request has none."""
        _extract_router.extract_fields(self._req())
        _extract_router.extract_fields(self._req())
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(
            _db.turn_extraction_count_for_narrator(self.narrator_id), 0,
            "the HTTP endpoint wrote a turn-extraction ledger row. It has "
            "no persisted turn identity, so any key it invented would be "
            "text-derived — the thing Phase 2 Step 3 forbids.",
        )

    def test_the_route_still_marks_the_probe_stage(self):
        _tp_token = None
        os.environ["HORNELORE_TRUTH_PIPELINE_LOG"] = "1"
        try:
            _tp_token = _tp.begin_turn(
                conv_id=self.conv_id, person_id=self.narrator_id,
                turn_id="t-http", turn_mode="interview",
            )
            _extract_router.extract_fields(self._req())
            summary = _tp.end_turn(_tp_token)
        finally:
            os.environ.pop("HORNELORE_TRUTH_PIPELINE_LOG", None)
        # summarize() files the per-stage tallies under "counts" as plain
        # ints. Reading a shape the probe does not produce would make this
        # test pass or fail for the wrong reason, so it reads the real one.
        counts = (summary or {}).get("counts", {})
        self.assertEqual(
            counts.get("extract_fields_called"), 1,
            "the probe mark moved with the extraction body and must still "
            f"fire on the HTTP path. Got: {counts}",
        )


# ══ 2. One shared service, two callers ═══════════════════════════════════
class SharedServiceTest(_ServiceCase):
    """Acceptance item 2: the HTTP endpoint and the WebSocket path use the
    same shared service.

    Asserted twice over, because either alone is weak: behaviourally (both
    entry points land on the one patched seam) and structurally (there is
    exactly one internal caller of the implementation, and the WebSocket
    server does not call its own HTTP endpoint)."""

    def test_both_entry_points_reach_the_same_seam(self):
        _extract_router.extract_fields(_extract_router.ExtractFieldsRequest(
            person_id=self.narrator_id, answer="one",
        ))
        _row, key = self._save_turn()
        out = self._extract(key, user_text="two")
        self.assertEqual(out.status, "succeeded")
        self.assertEqual(
            len(self.calls), 2,
            "patching the single shared seam must intercept BOTH callers. "
            "If only one call arrived, one path has its own extractor.",
        )

    def test_the_websocket_does_not_call_its_own_http_endpoint(self):
        """Phase 2 forbids an internal HTTP self-call. Structural: chat_ws
        must contain no client call aimed at the extract route."""
        # The route path is READ from the AST's string VALUES -- neither
        # from the raw file nor from docstrings. chat_ws.py legitimately
        # NAMES the route twice in prose (a comment at the top of the
        # module and the extraction hook's own docstring), both times to
        # explain why it is NOT called. A raw-text check fails on that
        # prose and keeps failing until someone deletes the explanation,
        # which is the exact false positive Phase 2 forbids.
        tree = _tree(_CHAT_WS)
        offenders = sorted(
            v for v in _string_values(tree) if "extract-fields" in v
        )
        self.assertEqual(
            offenders, [],
            "chat_ws.py holds the extract route path as a string value, "
            f"which is how an internal HTTP self-call is built: {offenders}",
        )
        called = _called_names(tree)
        for verb in ("post", "request", "aiohttp", "AsyncClient"):
            self.assertNotIn(
                verb, {c for c in called if c == verb},
                f"chat_ws.py appears to make an HTTP {verb} call. The "
                "completed-turn path must call the Python service "
                "directly.",
            )

    def test_the_implementation_is_not_duplicated_in_chat_ws(self):
        """Phase 2 forbids a copy of the extraction implementation in
        chat_ws.py. The implementation is identified by its own defined
        name, so this checks function DEFINITIONS, not mentions."""
        defined = {
            n.name for n in ast.walk(_tree(_CHAT_WS))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("run_field_extraction", defined)
        self.assertNotIn("extract_fields", defined)

    def test_the_service_is_independently_importable(self):
        """Step 2 requires the service to be independently testable. It
        must therefore import no router at module scope — routers/
        extract.py imports IT from inside the route function, so a
        module-scope import either way is a cycle."""
        module_level = set()
        for node in _tree(_SERVICE).body:
            if isinstance(node, ast.ImportFrom) and node.module:
                module_level.add(node.module)
            elif isinstance(node, ast.Import):
                module_level.update(a.name for a in node.names)
        leaked = sorted(m for m in module_level if "router" in m)
        self.assertFalse(
            leaked, f"turn_extraction imports {leaked} at module scope.",
        )


# ══ 3 + 4. Exactly once, and idempotent on replay ════════════════════════
class IdempotencyTest(_ServiceCase):
    """Acceptance items 3 and 4, plus Step 3's persistence requirement."""

    def test_a_completed_turn_invokes_extraction_exactly_once(self):
        _row, key = self._save_turn()
        out = self._extract(key)
        self.assertEqual(out.status, "succeeded")
        self.assertEqual(out.item_count, 1)
        self.assertEqual(len(self.calls), 1)

    def test_a_replay_of_the_same_turn_does_not_duplicate_extraction(self):
        _row, key = self._save_turn()
        first = self._extract(key)
        second = self._extract(key, turn_id="t-2-retry-different-id")
        self.assertEqual(first.status, "succeeded")
        self.assertEqual(
            second.status, "duplicate",
            "a replayed completed turn must be recognised as already "
            "processed. A reconnecting client mints a NEW turn_id for the "
            "same saved turn, which is why the key is the committed row.",
        )
        self.assertEqual(second.method, "already_processed")
        self.assertEqual(
            len(self.calls), 1,
            "the extractor ran twice for one committed turn.",
        )
        self.assertEqual(
            _db.turn_extraction_count_for_narrator(self.narrator_id), 1,
            "the replay created a second ledger row; the UNIQUE index is "
            "not doing its job.",
        )

    def test_two_different_turns_with_identical_text_both_extract(self):
        """The key is the persisted turn, NOT the text. A narrator may
        legitimately repeat themselves, and a text-derived key would
        silently drop the second answer."""
        same = "We had cattle and chickens then."
        _r1, k1 = self._save_turn(same)
        _r2, k2 = self._save_turn(same)
        self.assertNotEqual(k1, k2)
        self.assertEqual(self._extract(k1, user_text=same).status, "succeeded")
        self.assertEqual(self._extract(k2, user_text=same).status, "succeeded")
        self.assertEqual(len(self.calls), 2)

    def test_the_guard_is_persisted_not_in_memory(self):
        """Step 3 forbids an in-memory-only guard. Proof: the claim
        survives re-importing the service with a fresh module state, which
        an in-process set would not."""
        _row, key = self._save_turn()
        self.assertEqual(self._extract(key).status, "succeeded")
        row = _db.turn_extraction_get(self.narrator_id, key)
        self.assertIsNotNone(row, "no ledger row was written")
        self.assertEqual(row["outcome"], "succeeded")
        self.assertEqual(row["turn_key"], key)
        self.assertTrue(key.startswith("turnrow:"))

    def test_the_key_comes_from_the_committed_row_and_nothing_else(self):
        self.assertEqual(_db.turn_extraction_key_for_row(41), "turnrow:41")
        for bad in (None, "", 0, -1, "abc", object()):
            self.assertEqual(
                _db.turn_extraction_key_for_row(bad), "",
                f"{bad!r} produced a usable key. A missing row id must "
                "yield no key, so the service declines rather than "
                "falling back to hashing the narrator's words.",
            )

    def test_no_stable_key_declines_instead_of_guessing(self):
        out = self._extract("")
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.method, "no_stable_turn_key")
        self.assertEqual(len(self.calls), 0)


# ══ 5 + 6 + 7 + 8. Failure isolation and observability ═══════════════════
class FailureIsolationTest(_ServiceCase):
    """Acceptance items 5, 6, 7 and 8.

    Items 5 and 6 (raw turn / archive event survive an extraction
    failure) are structural facts about ORDER: extraction runs after both
    writes have committed and after the done frame has been sent, so
    there is nothing left for it to roll back. Both the ordering and the
    non-raising behaviour are asserted.
    """

    def test_extraction_failure_does_not_raise(self):
        _row, key = self._save_turn()
        self._raise = RuntimeError("extractor exploded")
        out = self._extract(key)
        self.assertEqual(out.status, "failed")
        self.assertEqual(out.error_class, "RuntimeError")
        self.assertFalse(out.ok)

    def test_the_raw_turn_survives_an_extraction_failure(self):
        """Acceptance item 5."""
        row_id, key = self._save_turn()
        self._raise = RuntimeError("boom")
        self._extract(key)
        con = sqlite3.connect(str(self.db_path))
        try:
            n = int(con.execute(
                "SELECT COUNT(*) FROM turns WHERE conv_id = ?",
                (self.conv_id,),
            ).fetchone()[0])
            still = con.execute(
                "SELECT content FROM turns WHERE id = ?", (row_id,),
            ).fetchone()
        finally:
            con.close()
        self.assertEqual(n, 2, "the user+assistant pair must both remain")
        self.assertIsNotNone(still, "the committed turn row was removed")

    def test_extraction_runs_after_persistence_not_inside_it(self):
        """Acceptance items 5 and 6, structurally.

        The reason a failing extraction cannot roll anything back is that
        it is not in either transaction. persist_turn_transaction must not
        call the service, and neither must the archive writer.
        """
        for rel in ("api/db.py", "api/archive.py"):
            called = _called_names(_tree(_SERVER_CODE / rel))
            self.assertNotIn(
                "extract_completed_turn", called,
                f"{rel} calls the extraction service. Extraction must sit "
                "OUTSIDE the persistence path, or a failing extractor can "
                "take the turn or the archive event down with it.",
            )

    def test_the_archive_event_is_written_before_extraction_is_asked(self):
        """Acceptance item 6, as an ordering fact in chat_ws.

        The hook refuses to run unless the archive append actually
        returned — the flag is set inside the try, after the call — so
        a raising archive write skips extraction rather than the reverse.
        """
        lines = _CHAT_WS.read_text(encoding="utf-8").splitlines()

        def _line_of(needle: str) -> int:
            hits = [i for i, l in enumerate(lines, 1) if needle in l]
            self.assertEqual(
                len(hits), 1,
                f"expected exactly one site for {needle!r}, found {hits}",
            )
            return hits[0]

        # Ordering INSIDE the persistence function: the flag may only be
        # set after the archive append has returned.
        n_append = _line_of("archive_rebuild_txt(person_id=person_id")
        n_flag = _line_of('params["_archive_event_persisted"] = True')
        self.assertLess(
            n_append, n_flag,
            "the archive-persisted flag is set before the append returns, "
            "so a raising archive write would still admit extraction.",
        )
        self.assertEqual(
            _enclosing_function(_tree(_CHAT_WS), n_append),
            _enclosing_function(_tree(_CHAT_WS), n_flag),
            "the append and its flag drifted into different functions, so "
            "the append's own exception no longer guards the flag.",
        )

        # And the hook REFUSES to run without it. Runtime order between
        # the two functions is asserted by
        # test_the_completed_response_is_sent_before_extraction; file
        # order says nothing about it, because the hook is defined near
        # the top of the module and the persistence path lives far below.
        self.assertEqual(
            _enclosing_function(
                _tree(_CHAT_WS),
                _line_of('if not params.get("_archive_event_persisted"):'),
            ),
            "_run_completed_turn_extraction",
            "the archive gate is not inside the extraction hook.",
        )

    def test_the_completed_response_is_sent_before_extraction(self):
        """Acceptance item 7, structurally.

        The hook is awaited in generate_and_stream AFTER the turn body
        returns. Every path through the body — the main path and all six
        deterministic short-circuits — has already sent its done frame
        by then, so extraction cannot delay or replace the browser's
        completed-turn signal.
        """
        tree = _tree(_CHAT_WS)
        wrapper = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.AsyncFunctionDef)
                    and node.name == "generate_and_stream"):
                wrapper = node
                break
        self.assertIsNotNone(wrapper, "generate_and_stream is gone")

        order = []
        for node in ast.walk(wrapper):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in (
                    "_generate_and_stream_body",
                    "_run_completed_turn_extraction",
                ):
                    order.append((node.lineno, node.func.id))
        order.sort()
        self.assertEqual(
            [n for _, n in order],
            ["_generate_and_stream_body", "_run_completed_turn_extraction"],
            "the extraction hook must be awaited AFTER the turn body, "
            f"once. Found: {order}",
        )

    def test_the_hook_cannot_raise_into_the_socket(self):
        """Acceptance item 7. The hook wraps everything in try/except and
        re-raises only CancelledError, so no extractor fault reaches the
        WebSocket handler."""
        src = _CHAT_WS.read_text(encoding="utf-8")
        start = src.index("async def _run_completed_turn_extraction(")
        end = src.index("async def _generate_and_stream_body(")
        body = src[start:end]
        self.assertIn("except asyncio.CancelledError:", body)
        self.assertIn("except Exception as _ext_exc:", body)
        self.assertNotIn(
            "raise _ext_exc", body,
            "the hook re-raises a plain exception into the turn.",
        )

    def test_extraction_failure_is_recorded_in_the_ledger(self):
        """Acceptance item 8, the durable half."""
        _row, key = self._save_turn()
        self._raise = ValueError("bad shape")
        out = self._extract(key)
        row = _db.turn_extraction_get(self.narrator_id, key)
        self.assertEqual(out.status, "failed")
        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(row["error_class"], "ValueError")

    def test_extraction_failure_is_visible_in_the_log(self):
        """Acceptance item 8, the api.log half."""
        _row, key = self._save_turn()
        self._raise = ValueError("bad shape")
        with self.assertLogs("api.services.turn_extraction", level="INFO") as cap:
            self._extract(key)
        blob = "\n".join(cap.output)
        self.assertIn("extract_fields_requested", blob)
        self.assertIn("extract_fields_started", blob)
        self.assertIn("extract_fields_failed", blob)
        self.assertIn("ValueError", blob)

    def _stage_count_for(self, turn_key: str) -> int:
        """Run the service inside a live probe turn; return the
        `extract_fields_called` tally the harness would report."""
        os.environ["HORNELORE_TRUTH_PIPELINE_LOG"] = "1"
        try:
            token = _tp.begin_turn(
                conv_id=self.conv_id, person_id=self.narrator_id,
                turn_id="t-probe", turn_mode="interview",
            )
            self._extract(turn_key)
            summary = _tp.end_turn(token)
        finally:
            os.environ.pop("HORNELORE_TRUTH_PIPELINE_LOG", None)
        return ((summary or {}).get("counts") or {}).get(
            "extract_fields_called", 0)

    def test_the_probe_stage_fires_when_extraction_succeeds(self):
        """Acceptance item 8, the harness half --- the control."""
        _row, key = self._save_turn()
        self.assertEqual(self._stage_count_for(key), 1)

    def test_the_probe_stage_still_fires_when_extraction_fails(self):
        """Acceptance item 8, the harness half --- the real assertion.

        THE STAGE MEANS "ASKED", NOT "SUCCEEDED". Until 2026-07-30 the
        mark sat inside the worker body BELOW the forced-failure seam, so
        a turn that invoked extraction and then failed reported
        `extract_fields_called=0` --- byte-identical to the reading the
        original defect produced, which was `extract_fields_called=0`
        because nothing ever called it. Gate 7 was opened precisely
        because three identical zeroes meant three different things, so a
        stage that cannot separate "never asked" from "asked and failed"
        is not observability. Live Test C reads this exact field.
        """
        _row, key = self._save_turn()
        self._raise = ValueError("bad shape")
        self.assertEqual(
            self._stage_count_for(key), 1,
            "a failed extraction reported the same stage count as a "
            "turn that never asked for extraction at all.",
        )

    def test_the_forced_failure_seam_also_marks_the_stage(self):
        """The Test C seam runs earlier than any other failure --- it
        short-circuits before the extractor is built --- so it is the one
        failure mode most likely to slip past the mark."""
        _row, key = self._save_turn()
        os.environ["HORNELORE_EXTRACTION_FORCE_FAILURE"] = "raise"
        try:
            self.assertEqual(self._stage_count_for(key), 1)
        finally:
            os.environ.pop("HORNELORE_EXTRACTION_FORCE_FAILURE", None)
        row = _db.turn_extraction_get(self.narrator_id, key)
        self.assertEqual(row["outcome"], "failed")
        self.assertEqual(row["error_class"], "ForcedExtractionFailure")

    def test_the_probe_stage_does_not_fire_when_nothing_was_asked(self):
        """The zero must keep its meaning. A turn declined before the
        claim never invoked the capability, so the stage stays 0 ---
        which is what made the original defect visible."""
        os.environ["HORNELORE_TRUTH_PIPELINE_LOG"] = "1"
        try:
            token = _tp.begin_turn(
                conv_id=self.conv_id, person_id=self.narrator_id,
                turn_id="t-probe-none", turn_mode="correction",
            )
            asyncio.run(tx.extract_completed_turn(
                narrator_id=self.narrator_id, turn_id="t-probe-none",
                user_text="I was born in Toledo.", assistant_text="Noted.",
                session_id=self.conv_id, turn_key="turnrow:999999",
                turn_mode="correction",
            ))
            summary = _tp.end_turn(token)
        finally:
            os.environ.pop("HORNELORE_TRUTH_PIPELINE_LOG", None)
        counts = (summary or {}).get("counts") or {}
        self.assertEqual(counts.get("extract_fields_called", 0), 0)

    def test_the_six_outcome_events_all_exist_and_are_all_emitted(self):
        """Step 5's vocabulary, checked by emission rather than by
        declaration — a tuple of names nobody logs is not
        observability."""
        self.assertEqual(tx.EXTRACTION_EVENTS, (
            "extract_fields_requested", "extract_fields_started",
            "extract_fields_succeeded", "extract_fields_noop",
            "extract_fields_duplicate", "extract_fields_failed",
        ))
        seen = set()
        # succeeded + requested + started
        _r1, k1 = self._save_turn()
        with self.assertLogs("api.services.turn_extraction", level="INFO") as c1:
            self._extract(k1)
        # duplicate
        with self.assertLogs("api.services.turn_extraction", level="INFO") as c2:
            self._extract(k1)
        # noop (zero items)
        self._response = _FakeResponse([], method="none")
        _r2, k2 = self._save_turn("mm")
        with self.assertLogs("api.services.turn_extraction", level="INFO") as c3:
            self._extract(k2, user_text="mm")
        # failed
        self._raise = RuntimeError("x")
        _r3, k3 = self._save_turn("zz")
        with self.assertLogs("api.services.turn_extraction", level="INFO") as c4:
            self._extract(k3, user_text="zz")
        blob = "\n".join(c1.output + c2.output + c3.output + c4.output)
        for ev in tx.EXTRACTION_EVENTS:
            if ev in blob:
                seen.add(ev)
        self.assertEqual(
            seen, set(tx.EXTRACTION_EVENTS),
            "these Step 5 events are declared but never emitted: "
            f"{sorted(set(tx.EXTRACTION_EVENTS) - seen)}",
        )

    def test_the_log_line_carries_ids_and_classifications_only(self):
        """Step 5's privacy rule: no raw private narrative text in the
        log. The narrator's words and the extracted values must not
        appear — an extractor's own error message can quote them, which
        is why only the exception CLASS is recorded."""
        secret = "Mandan North Dakota 1958 cattle"
        _row, key = self._save_turn(secret)
        self._response = _FakeResponse([_FakeItem("birth.place", secret)])
        with self.assertLogs("api.services.turn_extraction", level="INFO") as cap:
            out = self._extract(key, user_text=secret)
        blob = "\n".join(cap.output)
        self.assertNotIn(secret, blob)
        self.assertNotIn("Mandan", blob)
        self.assertNotIn(secret, out.as_log_fields())
        for token in ("turn_key", "outcome", "items", "duration_ms"):
            self.assertIn(token, out.as_log_fields())

    def test_an_extractor_message_never_reaches_the_log(self):
        secret = "narrator said Spokane in 1961"
        _row, key = self._save_turn()
        self._raise = RuntimeError(secret)
        with self.assertLogs("api.services.turn_extraction", level="INFO") as cap:
            self._extract(key)
        blob = "\n".join(cap.output)
        self.assertNotIn(secret, blob)
        self.assertNotIn("Spokane", blob)
        self.assertIn("RuntimeError", blob)

    def test_the_forced_failure_seam_is_harness_only_and_off_by_default(self):
        """Live Test C needs a failure without corrupting production
        config. The seam is an env var, default OFF."""
        self.assertEqual(tx.forced_failure_mode(), "")
        _row, key = self._save_turn()
        os.environ["HORNELORE_EXTRACTION_FORCE_FAILURE"] = "raise"
        try:
            out = self._extract(key)
        finally:
            os.environ.pop("HORNELORE_EXTRACTION_FORCE_FAILURE", None)
        self.assertEqual(out.status, "failed")
        self.assertEqual(out.error_class, "ForcedExtractionFailure")
        self.assertEqual(
            len(self.calls), 0,
            "the forced-failure seam must short-circuit BEFORE the real "
            "extractor runs, or Test C spends an LLM call to fail.",
        )
        self.assertEqual(
            _db.turn_extraction_get(self.narrator_id, key)["outcome"],
            "failed",
        )


# ══ 9 + 10 + 11. The two deliberate boundaries ═══════════════════════════
class BoundariesTest(_ServiceCase):
    """Acceptance items 9, 10 and 11 — Step 6.

    Both boundaries get a BEHAVIOURAL test (run the real thing against a
    real database and count the rows) as well as the retained structural
    guard, because Chris's Step 6 says not to prove these with a
    substring test alone. The structural half still earns its place: it
    catches a call added on a branch the behavioural test does not reach.
    """

    def test_an_interview_turn_writes_no_family_truth_row(self):
        """Acceptance item 9, behaviourally."""
        _row, key = self._save_turn()
        before_rows = self._count(
            "family_truth_rows", "person_id", self.narrator_id)
        before_notes = self._count(
            "family_truth_notes", "person_id", self.narrator_id)
        out = self._extract(key)
        self.assertEqual(out.status, "succeeded")
        self.assertEqual(
            self._count("family_truth_rows", "person_id", self.narrator_id),
            before_rows,
            "a completed interview turn wrote a family-truth ROW. Family "
            "truth is review-gated: every legitimate write is an explicit "
            "operator HTTP action. Phase 2 connects turns to EXTRACTION, "
            "not to TRUTH.",
        )
        self.assertEqual(
            self._count("family_truth_notes", "person_id", self.narrator_id),
            before_notes,
            "a completed interview turn wrote a family-truth NOTE.",
        )

    def test_the_service_never_calls_a_family_truth_writer(self):
        """Acceptance item 9, structurally — AST, retained on purpose.

        The behavioural test above only covers the paths one fake
        extractor reaches. This covers every branch, and reads the AST
        because 'ft_add_row' appears in this file's own prose.
        """
        called = _called_names(_tree(_SERVICE))
        leaked = sorted(
            {"ft_add_note", "ft_add_row", "ft_backfill_from_profile_json"}
            & called
        )
        self.assertFalse(
            leaked, f"turn_extraction.py calls family-truth writer(s) {leaked}.",
        )

    def test_an_interview_turn_performs_no_projection_correction(self):
        """Acceptance item 10, behaviourally."""
        _row, key = self._save_turn()
        before = self._count(
            "interview_projections", "person_id", self.narrator_id)
        self._extract(key)
        self.assertEqual(
            self._count("interview_projections", "person_id",
                        self.narrator_id),
            before,
            "a completed interview turn moved the interview projection. "
            "Projections are correction-only; an interview turn that "
            "writes one has crossed the boundary Phase 1 proved was "
            "deliberate.",
        )

    def test_the_service_never_calls_apply_correction(self):
        """Acceptance item 10, structurally."""
        self.assertNotIn("apply_correction", _called_names(_tree(_SERVICE)))

    def test_correction_mode_still_reaches_apply_correction(self):
        """Acceptance item 11.

        The control. Phase 2 must not have broken the one turn shape that
        IS allowed to move a projection. Structural, because reaching the
        real branch needs a live model: every apply_correction call in
        chat_ws must still exist and still sit inside
        `turn_mode == "correction"`.
        """
        tree = _tree(_CHAT_WS)

        def _ids(root):
            return {
                id(n) for n in ast.walk(root)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "apply_correction"
            }

        all_calls = _ids(tree)
        self.assertTrue(
            all_calls,
            "chat_ws no longer calls apply_correction at all. Phase 2 was "
            "not allowed to redesign correction behaviour.",
        )
        guarded = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.If)
                    and isinstance(node.test, ast.Compare)
                    and isinstance(node.test.left, ast.Name)
                    and node.test.left.id == "turn_mode"
                    and node.test.comparators
                    and isinstance(node.test.comparators[0], ast.Constant)
                    and node.test.comparators[0].value == "correction"):
                for stmt in node.body:
                    guarded |= _ids(stmt)
        self.assertEqual(all_calls, guarded)

    def test_a_correction_turn_is_not_extracted(self):
        """The other side of item 11: extraction is interview-only, so a
        correction turn takes no claim and runs no extractor. That is what
        keeps the two lanes from interfering."""
        _row, key = self._save_turn()
        out = self._extract(key, turn_mode="correction")
        self.assertEqual(out.status, "noop")
        self.assertEqual(out.method, "ineligible_turn_mode")
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(
            _db.turn_extraction_count_for_narrator(self.narrator_id), 0,
            "a correction turn took an extraction claim. It must not "
            "even reach the ledger.",
        )
        self.assertFalse(tx.extraction_eligible("correction"))
        self.assertTrue(tx.extraction_eligible("interview"))

    def test_the_extractor_receives_only_the_narrator_text(self):
        """A quieter boundary, worth pinning: the assistant reply is not
        the subject of extraction. Extracting from Lori's own words would
        let the model's phrasing become the narrator's biography."""
        _row, key = self._save_turn()
        self._extract(key, user_text="I grew up in Mandan.")
        req = self.calls[0]
        self.assertEqual(req.answer, "I grew up in Mandan.")
        self.assertEqual(req.person_id, self.narrator_id)
        self.assertIsNone(
            getattr(req, "transcript_source", None),
            "transcript_source must be left unset rather than guessed, or "
            "the WO-STT-LIVE-02 fragile-field confirmation gate is "
            "silently bypassed for dictated answers.",
        )


# ══ 14 + 15. Nothing else moved ══════════════════════════════════════════
# ══ 6. The completion task: scheduled, held, drained ═════════════════════
class ScheduledCompletionTest(_ServiceCase):
    """The fix for the first live acceptance run.

    That run recorded outcome='failed' error_class='CancelledError' at
    815 ms and 839 ms for both interview turns. The cause was structural,
    not a bug in the extractor: the hook awaited extraction inside the
    turn's own task, the harness closed its socket the moment it had the
    `done` frame, and chat_ws cancelled the turn task with the extractor
    still inside it. Every assertion in this class exists because that
    happened.
    """

    def _ledger(self):
        con = sqlite3.connect(str(self.db_path))
        con.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in con.execute(
                "SELECT * FROM turn_extraction_ledger WHERE narrator_id = ? "
                "ORDER BY id", (self.narrator_id,))]
        finally:
            con.close()

    def _schedule(self, turn_key, **kw):
        params = dict(
            narrator_id=self.narrator_id,
            turn_id=kw.pop("turn_id", "t-sched"),
            user_text=kw.pop("user_text", "I was born in Mandan in 1958."),
            session_id=self.conv_id,
            turn_key=turn_key,
            turn_mode=kw.pop("turn_mode", "interview"),
        )
        params.update(kw)
        return tx.schedule_completed_turn_extraction(**params)

    def test_scheduling_claims_inline_and_finishes_on_a_held_task(self):
        """The claim must be durable BEFORE the task exists, so an
        abandoned attempt is auditable rather than invisible."""
        _row_id, key = self._save_turn()

        async def go():
            out = self._schedule(key)
            # Claimed and recorded before anything is awaited.
            self.assertEqual(out.status, "scheduled")
            self.assertTrue(out.ok, "a scheduled turn is not a failed turn")
            self.assertFalse(
                out.terminal,
                "'scheduled' is not an outcome, it is a promise of one",
            )
            mid = self._ledger()
            self.assertEqual(len(mid), 1)
            self.assertEqual(
                mid[0]["outcome"], "started",
                "the claim row must exist at 'started' the instant "
                "scheduling returns, not after the extractor finishes",
            )
            self.assertEqual(tx.pending_extraction_count(), 1)
            report = await tx.drain_pending_extractions(timeout=10.0)
            return report

        report = asyncio.run(go())
        self.assertEqual(report["cancelled"], 0)
        rows = self._ledger()
        self.assertEqual(len(rows), 1, "one turn, one ledger row")
        self.assertEqual(rows[0]["outcome"], "succeeded")
        self.assertEqual(rows[0]["error_class"], "")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(tx.pending_extraction_count(), 0,
                         "a finished task must be released from the registry")

    def test_the_extraction_survives_cancellation_of_the_turn_task(self):
        """THE REGRESSION. Cancel the parent task mid-extraction; the
        extraction must still complete and record a real outcome.

        A sibling task created with create_task is not cancelled when the
        task that created it is cancelled. That property is the entire
        reason the work moved off the turn task, so it is asserted
        directly rather than inferred from the absence of an error.
        """
        _row_id, key = self._save_turn()
        entered = threading.Event()
        release = threading.Event()

        def _slow(req):
            entered.set()
            release.wait(10.0)
            self.calls.append(req)
            return self._response

        tx._call_extractor = _slow

        async def go():
            async def turn_task():
                self._schedule(key)
                # The turn body goes on living until the client vanishes.
                await asyncio.sleep(3600)

            parent = asyncio.create_task(turn_task())
            for _ in range(500):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(entered.is_set(),
                            "the extractor never started; test is invalid")
            # This is the harness closing its socket.
            parent.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await parent
            self.assertEqual(
                tx.pending_extraction_count(), 1,
                "cancelling the turn task took the extraction with it — "
                "this is exactly the live defect of 2026-07-30",
            )
            release.set()
            return await tx.drain_pending_extractions(timeout=10.0)

        try:
            report = asyncio.run(go())
        finally:
            release.set()   # never leave a pool thread blocked at exit

        self.assertEqual(report["cancelled"], 0)
        rows = self._ledger()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["outcome"], "succeeded",
            "the extraction died with its parent again; the live run "
            "recorded exactly this as failed/CancelledError",
        )
        self.assertEqual(rows[0]["error_class"], "")

    def test_the_drain_cancels_leftovers_and_records_each_one(self):
        """Step 4: no task may silently disappear on process shutdown
        without recording its state."""
        _row_id, key = self._save_turn()
        entered = threading.Event()
        release = threading.Event()   # deliberately never set in time

        def _stuck(req):
            entered.set()
            release.wait(30.0)
            return self._response

        tx._call_extractor = _stuck

        async def go():
            self._schedule(key)
            for _ in range(500):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            return await tx.drain_pending_extractions(timeout=0.5)

        try:
            report = asyncio.run(go())
        finally:
            release.set()

        self.assertEqual(report["pending_at_shutdown"], 1)
        self.assertEqual(report["finished_within_timeout"], 0)
        self.assertEqual(report["cancelled"], 1)
        rows = self._ledger()
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["outcome"], "failed",
            "a cancelled extraction left its ledger row at 'started'. "
            "An abandoned attempt that looks in-flight forever is the "
            "'silently disappear' case Step 4 forbids.",
        )
        self.assertEqual(rows[0]["error_class"], "CancelledError")

    def test_the_drain_is_a_no_op_when_nothing_is_pending(self):
        report = asyncio.run(tx.drain_pending_extractions(timeout=0.5))
        self.assertEqual(report["pending_at_shutdown"], 0)
        self.assertEqual(report["cancelled"], 0)

    def test_an_ineligible_mode_is_terminal_and_creates_no_task(self):
        _row_id, key = self._save_turn()

        async def go():
            out = self._schedule(key, turn_mode="correction")
            self.assertEqual(out.status, "noop")
            self.assertTrue(out.terminal)
            self.assertEqual(tx.pending_extraction_count(), 0)
            return out

        asyncio.run(go())
        self.assertEqual(self._ledger(), [],
                         "an ineligible turn must not claim the ledger")
        self.assertEqual(self.calls, [])

    def test_a_replayed_turn_is_a_duplicate_and_creates_no_second_task(self):
        _row_id, key = self._save_turn()

        async def go():
            first = self._schedule(key)
            await tx.drain_pending_extractions(timeout=10.0)
            second = self._schedule(key, turn_id="t-replay")
            self.assertEqual(tx.pending_extraction_count(), 0,
                             "a duplicate must not spawn a second extractor")
            return first, second

        first, second = asyncio.run(go())
        self.assertEqual(first.status, "scheduled")
        self.assertEqual(second.status, "duplicate")
        self.assertTrue(second.terminal)
        self.assertEqual(len(self._ledger()), 1)
        self.assertEqual(len(self.calls), 1)

    def test_scheduling_without_a_running_loop_closes_its_own_claim(self):
        """Never raise into the caller, and never abandon a claim.

        There is no running loop here, so the task cannot be created. The
        row must not be left at 'started' forever just because the
        scheduler could not do its job.
        """
        _row_id, key = self._save_turn()
        out = self._schedule(key)          # called from sync context
        self.assertEqual(out.status, "failed")
        self.assertTrue(out.terminal)
        rows = self._ledger()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["outcome"], "failed")
        self.assertNotEqual(rows[0]["error_class"], "")

    def test_the_awaiting_entry_point_is_unchanged(self):
        """extract_completed_turn still runs inline and returns a
        terminal outcome. The HTTP-side and test-side callers depend on
        that, and Phase 2 added a second entry point rather than
        replacing the first."""
        _row_id, key = self._save_turn()
        out = self._extract(key)
        self.assertEqual(out.status, "succeeded")
        self.assertTrue(out.terminal)
        self.assertEqual(tx.pending_extraction_count(), 0)
        self.assertEqual(self._ledger()[0]["outcome"], "succeeded")

    def test_forced_failure_armed_reports_this_process_only(self):
        """The acceptance script refuses to run Test C unless the SERVER
        says the seam is live. It was run once against a server that had
        never been restarted with it, and scored a meaningless
        CancelledError as the result."""
        self.assertFalse(tx.forced_failure_armed())
        os.environ["HORNELORE_EXTRACTION_FORCE_FAILURE"] = "raise"
        try:
            self.assertTrue(tx.forced_failure_armed())
        finally:
            os.environ.pop("HORNELORE_EXTRACTION_FORCE_FAILURE", None)
        self.assertFalse(tx.forced_failure_armed())


# ══ 7. The wiring around the task ════════════════════════════════════════
class SchedulingWiringTest(unittest.TestCase):
    """Source-level facts. Asserted through the AST, never by substring:
    every string below also appears in a docstring somewhere in these
    files, and a substring check would go green on the prose alone."""

    def test_the_chat_ws_hook_schedules_and_does_not_await_extraction(self):
        tree = _tree(_CHAT_WS)
        called = _called_names(tree)
        self.assertIn(
            "schedule_completed_turn_extraction", called,
            "the completed-turn hook stopped scheduling extraction",
        )
        self.assertNotIn(
            "extract_completed_turn", called,
            "chat_ws is awaiting extraction inline again. That is the "
            "shape that produced failed/CancelledError on every "
            "interview turn of the 2026-07-30 live run.",
        )

    def test_the_hook_still_lives_in_the_completed_turn_path(self):
        """Scheduling is only safe where awaiting was: after the turn is
        persisted, after the archive event, after the done frame."""
        tree = _tree(_CHAT_WS)
        sites = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "_schedule_extraction"
        ]
        self.assertTrue(sites, "no call to the scheduling alias at all")
        for lineno in sites:
            self.assertEqual(
                _enclosing_function(tree, lineno),
                "_run_completed_turn_extraction",
                "extraction is being scheduled from somewhere other than "
                "the completed-turn hook",
            )

    def test_main_py_drains_pending_extractions_on_shutdown(self):
        """Without this the background task is exactly the 'fragile
        detached task that can silently disappear on process shutdown'
        Step 4 forbids."""
        tree = _tree(_MAIN_PY)
        handlers = [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(d, ast.Call)
                and getattr(d.func, "attr", "") == "on_event"
                and any(getattr(a, "value", None) == "shutdown"
                        for a in d.args)
                for d in n.decorator_list
            )
        ]
        self.assertTrue(handlers, "main.py has no shutdown handler")
        drains = [h for h in handlers
                  if "drain_pending_extractions" in _called_names(h)]
        self.assertTrue(
            drains,
            "a shutdown handler exists but nothing drains the extraction "
            "tasks, so in-flight rows would be stranded at 'started'",
        )

    def test_the_harness_reports_its_own_arming_state(self):
        tree = _tree(_HARNESS_ROUTER)
        health = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "harness_health"), None)
        self.assertIsNotNone(health, "the harness health route is gone")
        keys = {
            k.value for n in ast.walk(health) if isinstance(n, ast.Dict)
            for k in n.keys if isinstance(k, ast.Constant)
        }
        self.assertIn("forced_failure_armed", keys)
        self.assertIn("truth_pipeline_log", keys)
        self.assertIn(
            "forced_failure_armed", _called_names(health),
            "the health route reports a key it never asks the service "
            "for — a hardcoded boolean would be worse than no boolean",
        )

    def test_the_harness_probe_window_outlasts_the_turn_body(self):
        """The first live run reported truth_pipeline=None for turns the
        server's own api.log had already recorded. That was a 0.5 s
        reporting window, not a missing probe."""
        tree = _tree(_HARNESS_ROUTER)
        fn = next(
            (n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == "_truth_pipeline_summary"), None)
        self.assertIsNotNone(fn)
        waits = [
            n.value for n in ast.walk(fn)
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add)
            and isinstance(n.right, ast.Constant)
            and isinstance(n.right.value, (int, float))
            for n in [n.right]
        ]
        self.assertTrue(waits, "the poll deadline is no longer a literal")
        self.assertGreaterEqual(
            max(waits), 5.0,
            "the probe poll window shrank back below 5 s; a false "
            "absence there reads as a pipeline defect",
        )


class NoCollateralChangeTest(unittest.TestCase):
    """Acceptance items 14 and 15.

    Item 15 (existing Gate 7 tests still pass) is satisfied by running
    tests/test_truth_pipeline_probe.py and its isolation companion; that
    is a command, not an assertion, and the run is recorded in the phase
    report. What IS asserted here is item 14: the narrator/reference
    protections Phase 1 verified are untouched.
    """

    def test_the_reference_narrator_protection_is_untouched(self):
        """Phase 1 found that synthetic-narrator silence came from
        narrator_type='reference' plus _block_if_reference, not from any
        extraction behaviour. Phase 2 must not have loosened it."""
        # The guard is DEFINED in the family-truth router, not in db.py.
        # Asserting its presence in the wrong file would have proved
        # nothing and would have gone green the day the guard was
        # deleted.
        guard_home = _SERVER_CODE / "api" / "routers" / "family_truth.py"
        defined = {
            n.name for n in ast.walk(_tree(guard_home))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn(
            "_block_if_reference", defined,
            "the reference-narrator guard Phase 1 credited for synthetic "
            "narrator silence is gone from family_truth.py.",
        )
        # Until 2026-07-30 this asserted "at least 7" call sites, on the
        # strength of the Phase 1 note that the guard appears at "7
        # sites" in family_truth.py. That count was a count of MENTIONS:
        # six calls plus the def line itself. Six is the real number of
        # protected write paths -- shadow note creation, proposal
        # creation, row mutation, bulk promotion, promotion, and backfill
        # from profile_json -- and it is what the AST can actually see.
        call_sites = [
            n for n in ast.walk(_tree(guard_home))
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", "") == "_block_if_reference"
        ]
        self.assertGreaterEqual(
            len(call_sites), 6,
            "the guard lost call sites. Phase 1 found it on six "
            "family-truth write paths and Phase 2 touched none of them; "
            f"now there are {len(call_sites)}.",
        )
        for rel in ("api/services/turn_extraction.py",):
            called = _called_names(_tree(_SERVER_CODE / rel))
            self.assertNotIn(
                "_block_if_reference", called,
                f"{rel} reaches into the reference-narrator guard. The "
                "extraction service has no business there.",
            )

    def test_persist_turn_transaction_stayed_behaviour_compatible(self):
        """Phase 2 changed this function's return type from None to the
        committed assistant rowid. Every pre-Phase-2 caller ignores the
        return value, which is what makes that safe — so no caller may
        start depending on None."""
        tree = _tree(_SERVER_CODE / "api" / "db.py")
        fn = None
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name == "persist_turn_transaction"):
                fn = node
                break
        self.assertIsNotNone(fn)
        returns = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Return) and n.value is not None
        ]
        self.assertTrue(
            returns,
            "persist_turn_transaction returns nothing again. The "
            "committed assistant rowid IS the Phase 2 idempotency key; "
            "without it the turn path has no stable key and declines to "
            "extract.",
        )


if __name__ == "__main__":
    unittest.main()
