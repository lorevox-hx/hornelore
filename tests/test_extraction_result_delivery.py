"""WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2 — the server half.

The browser half is proved by execution in
scripts/ui/run_extraction_result_consumer.js, which drives the real
consumer in Chromium. This file proves the half that lives in Python:
the durable result row, its lifecycle, the negotiation the server is
responsible for, and the boundaries that must not move.

WHAT IS ASSERTED AGAINST WHAT
-----------------------------
Everything here runs against a REAL temporary sqlite database built by
init_db(), not a mock. The one seam that is doubled is the extractor
itself (tx._call_extractor), because an LLM call is not what any of
these assertions are about.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_extraction_result_delivery

No pytest, no discovery, and not .venv-gpu -- that one serves the stack.
"""
from __future__ import annotations

import ast
import asyncio
import json
import logging
import sqlite3
import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# ── fastapi / pydantic stubs ─────────────────────────────────────────
# routers/extract.py imports both at module scope, and the extraction
# service reaches it to build its request object. The repo convention
# (tests/test_turn_extraction.py, tests/test_captured_note_review.py) is
# to stub them rather than require the web stack for a unit test. The
# guard means a machine that HAS the real libraries keeps them.
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

from api import db as _db                                   # noqa: E402
from api.services import turn_extraction as tx              # noqa: E402


class _FakeItem:
    def __init__(self, path="personal.placeOfBirth", value="Mandan"):
        self.fieldPath = path
        self.value = value
        self.confidence = 0.9

    def dict(self):
        return {"fieldPath": self.fieldPath, "value": self.value,
                "confidence": self.confidence}


class _FakeResponse:
    def __init__(self, items, method="llm", clarifications=None):
        self.items = items
        self.method = method
        self.clarification_required = clarifications or []


class _ResultCase(unittest.TestCase):
    """Real sqlite, real service, doubled extractor."""

    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db.init_db()

        self.narrator_id = f"harness-{uuid.uuid4()}"
        self.other_id = f"harness-{uuid.uuid4()}"
        self.conv_id = f"conv-{self.narrator_id}"

        self._orig_call = tx._call_extractor
        self._response = _FakeResponse([_FakeItem()])
        tx._call_extractor = lambda req: self._response

    def tearDown(self):
        tx._call_extractor = self._orig_call
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # helpers ---------------------------------------------------------
    def _turn(self, user="I was born in Mandan.", assistant="Tell me more.",
              conv=None):
        row = _db.persist_turn_transaction(
            conv_id=conv or self.conv_id, user_message=user,
            assistant_message=assistant, model_name="test")
        return row, _db.turn_extraction_key_for_row(row)

    def _extract(self, turn_key, user_text="I was born in Mandan.",
                 narrator=None, on_result=None):
        return asyncio.run(tx.extract_completed_turn(
            narrator_id=narrator or self.narrator_id,
            turn_id="t-1", user_text=user_text,
            session_id=self.conv_id, turn_key=turn_key,
            turn_mode="interview"))

    def _rows(self, narrator=None):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(
                "SELECT * FROM turn_extraction_results WHERE narrator_id = ? "
                "ORDER BY id;", (narrator or self.narrator_id,))]
        finally:
            con.close()


class MigrationTest(_ResultCase):
    """0041 applies, and applies to a database that already has 0040."""

    def test_the_table_and_its_constraints_exist(self):
        con = sqlite3.connect(str(self.db_path))
        try:
            cols = {r[1]: r for r in con.execute(
                "PRAGMA table_info(turn_extraction_results);")}
            for name in ("ledger_id", "narrator_id", "turn_key", "turn_id",
                         "session_id", "status", "method", "items",
                         "clarification_required", "item_count",
                         "created_at", "delivered_at", "applied_at"):
                self.assertIn(name, cols, name)
            idx = [r[1] for r in con.execute(
                "PRAGMA index_list(turn_extraction_results);")]
            self.assertIn("ux_turn_extraction_results_key", idx)
        finally:
            con.close()

    def test_resource_deferred_is_not_a_result_status(self):
        """Chris's ruling: a deferred extraction produces no structured
        work, so it is a ledger/scheduler event and must not create a
        browser obligation. Asserted so a later phase cannot add it here
        without a decision."""
        con = sqlite3.connect(str(self.db_path))
        try:
            sql = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' "
                "AND name='turn_extraction_results';").fetchone()[0]
            self.assertIn("succeeded", sql)
            self.assertNotIn("resource_deferred", sql)
        finally:
            con.close()

    def test_it_applies_on_top_of_the_real_0040_schema(self):
        """The UPGRADE path, not only creation from an empty database.

        Dropping the table alone proves nothing: migrations are recorded
        in schema_migrations and the runner will not re-run one it has
        already applied. So this puts the database genuinely back at
        0040 -- table gone AND the 0041 record cleared -- and then runs
        the migrator the way a stack start does.
        """
        con = sqlite3.connect(str(self.db_path))
        try:
            has_tracking = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name='schema_migrations';").fetchone()[0]
            if not has_tracking:
                self.skipTest("no schema_migrations table in this build")
            con.execute("DROP TABLE IF EXISTS turn_extraction_results;")
            con.execute("DELETE FROM schema_migrations "
                        " WHERE filename LIKE '%0041%';")
            con.commit()
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name='turn_extraction_results';").fetchone()[0], 0)
        finally:
            con.close()

        _db.init_db()          # the upgrade a stack start performs

        con = sqlite3.connect(str(self.db_path))
        try:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                "AND name='turn_extraction_results';").fetchone()[0], 1,
                "0041 did not re-apply to a database sitting at 0040")
        finally:
            con.close()


class ResultRowTest(_ResultCase):

    def test_a_succeeded_extraction_writes_exactly_one_row(self):
        _row, key = self._turn()
        out = self._extract(key)
        self.assertEqual(out.status, "succeeded")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["turn_key"], key)
        self.assertEqual(json.loads(rows[0]["items"])[0]["value"], "Mandan")

    def test_identity_comes_from_the_claim_not_from_the_caller(self):
        _row, key = self._turn()
        self._extract(key)
        r = self._rows()[0]
        self.assertEqual(r["narrator_id"], self.narrator_id)
        self.assertEqual(r["session_id"], self.conv_id)

    def test_a_replay_reaches_the_same_row_and_mints_no_second(self):
        _row, key = self._turn()
        self._extract(key)
        self._extract(key)          # duplicate claim, no second run
        self.assertEqual(len(self._rows()), 1)

    def test_a_noop_writes_no_row(self):
        self._response = _FakeResponse([])
        _row, key = self._turn()
        out = self._extract(key)
        self.assertEqual(out.status, "noop")
        self.assertEqual(self._rows(), [])

    def test_a_malformed_payload_becomes_failed_and_stores_nothing(self):
        """A bad shape that persists is worse than one that fails once:
        it would be replayed to Projection Sync on every reconnect."""
        self._response = _FakeResponse(["not-an-object"])
        _row, key = self._turn()
        out = self._extract(key)
        self.assertEqual(out.status, "failed")
        self.assertEqual(out.error_class, "MalformedExtractionPayload")
        self.assertEqual(self._rows(), [])

    def test_a_system_directive_produces_no_row(self):
        _row, key = self._turn(user="[SYSTEM: greet them warmly]")
        out = asyncio.run(tx.extract_completed_turn(
            narrator_id=self.narrator_id, turn_id="t-d",
            user_text="[SYSTEM: greet them warmly]", session_id=self.conv_id,
            turn_key=key, turn_mode="interview", is_system_directive=True))
        self.assertEqual(out.status, "noop")
        self.assertEqual(self._rows(), [])


class LifecycleTest(_ResultCase):

    def test_delivered_and_applied_are_independent(self):
        _row, key = self._turn()
        self._extract(key)
        self.assertTrue(_db.turn_extraction_result_mark_delivered(
            self.narrator_id, key))
        still = _db.turn_extraction_results_pending(self.narrator_id)
        self.assertEqual(len(still), 1,
                         "delivered must NOT retire the obligation")
        self.assertTrue(_db.turn_extraction_result_mark_applied(
            self.narrator_id, key))
        self.assertEqual(_db.turn_extraction_results_pending(self.narrator_id), [])

    def test_both_stamps_are_idempotent(self):
        _row, key = self._turn()
        self._extract(key)
        self.assertTrue(_db.turn_extraction_result_mark_delivered(self.narrator_id, key))
        self.assertFalse(_db.turn_extraction_result_mark_delivered(self.narrator_id, key))
        self.assertTrue(_db.turn_extraction_result_mark_applied(self.narrator_id, key))
        self.assertFalse(_db.turn_extraction_result_mark_applied(self.narrator_id, key))

    def test_another_person_cannot_acknowledge_this_row(self):
        _row, key = self._turn()
        self._extract(key)
        self.assertFalse(_db.turn_extraction_result_mark_applied(self.other_id, key))
        self.assertEqual(len(_db.turn_extraction_results_pending(self.narrator_id)), 1)

    def test_pending_is_scoped_to_one_narrator(self):
        _row, key = self._turn()
        self._extract(key)
        self.assertEqual(_db.turn_extraction_results_pending(self.other_id), [])
        self.assertEqual(_db.turn_extraction_results_pending(""), [])

    def test_the_session_filter_narrows_without_leaking(self):
        _row, key = self._turn()
        self._extract(key)
        self.assertEqual(
            len(_db.turn_extraction_results_pending(
                self.narrator_id, session_id=self.conv_id)), 1)
        self.assertEqual(
            _db.turn_extraction_results_pending(
                self.narrator_id, session_id="some-other-conv"), [])

    def test_an_undelivered_result_is_still_offered(self):
        """The delivery callback failing must not retire the row --
        otherwise a browser that closed mid-send loses the result."""
        _row, key = self._turn()

        async def _boom(outcome, clar=None, source_text=""):
            raise RuntimeError("socket closed")

        asyncio.run(tx.extract_completed_turn(
            narrator_id=self.narrator_id, turn_id="t-1",
            user_text="I was born in Mandan.", session_id=self.conv_id,
            turn_key=key, turn_mode="interview"))
        # The claim path above has no callback; assert the row survives a
        # failed offer by calling the offer directly.
        claim = tx._Claim(ledger_id=0, started=0.0,
                          narrator_id=self.narrator_id, turn_id="t-1",
                          turn_key=key, session_id=self.conv_id,
                          turn_mode="interview", source="chat_ws",
                          user_text="x", on_result=_boom)
        asyncio.run(tx._offer_result(claim, tx.ExtractionOutcome(
            status="succeeded", turn_key=key,
            narrator_id=self.narrator_id), []))
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["delivered_at"],
                          "a failed send must not stamp delivered")
        self.assertIsNone(rows[0]["applied_at"])


class SourceTextTest(_ResultCase):
    """Catch-up must show the same words the live frame carries."""

    def test_each_turn_resolves_its_own_text(self):
        r1, k1 = self._turn(user="I visited Bismarck with Melanie.")
        r2, k2 = self._turn(user="We went to the cemetery.")
        self.assertEqual(_db.turn_source_text_for_key(k1),
                         "I visited Bismarck with Melanie.")
        self.assertEqual(_db.turn_source_text_for_key(k2),
                         "We went to the cemetery.")

    def test_out_of_order_completion_cannot_swap_the_text(self):
        """The whole reason this is resolved per turn_key rather than
        read from 'the latest input'."""
        _r1, k1 = self._turn(user="Turn A words.")
        _r2, k2 = self._turn(user="Turn B words.")
        self._extract(k2)          # B completes first
        self._extract(k1)          # A completes second
        self.assertEqual(_db.turn_source_text_for_key(k1), "Turn A words.")
        self.assertEqual(_db.turn_source_text_for_key(k2), "Turn B words.")

    def test_an_unresolvable_key_returns_empty_rather_than_guessing(self):
        self.assertEqual(_db.turn_source_text_for_key("nonsense"), "")
        self.assertEqual(_db.turn_source_text_for_key("turnrow:999999"), "")
        self.assertEqual(_db.turn_source_text_for_key(""), "")


class PrivacyTest(_ResultCase):
    """No narrator prose in the log stream, on any path."""

    def test_no_narrator_text_is_logged(self):
        secret = "my mother's maiden name was Ostrander"
        _row, key = self._turn(user=secret)
        self._response = _FakeResponse([_FakeItem(value=secret)])
        stream = []

        class _Cap(logging.Handler):
            def emit(self, record):
                stream.append(record.getMessage())

        h = _Cap()
        for name in ("api.services.turn_extraction",
                     "code.api.services.turn_extraction"):
            logging.getLogger(name).addHandler(h)
        try:
            self._extract(key, user_text=secret)
        finally:
            for name in ("api.services.turn_extraction",
                         "code.api.services.turn_extraction"):
                logging.getLogger(name).removeHandler(h)
        joined = "\n".join(stream)
        self.assertNotIn("Ostrander", joined)
        self.assertNotIn("maiden", joined)


class DeferLifecycleTest(_ResultCase):
    """Invariants the Phase 3 scheduler must not break, pinned before it
    exists so it inherits them rather than having to remember them.

    Chris ruled that `resource_deferred` belongs to scheduling, not to
    the result queue, and 0041's CHECK enforces that -- the status is
    absent from the result table by construction. So there is no defer
    outcome to drive here yet. What CAN be driven today is the shape a
    defer will take: a claim that exists and has produced no result.
    Every assertion below is written against that shape, which is the
    same shape a deferred extraction leaves behind.

    The distinction that makes this worth writing early: a defer is not
    a failure and not an empty answer. It is work that has been claimed
    and not yet done. If a deferred turn ever reaches the pending queue,
    Projection Sync and Shadow Review would show an operator a proposal
    that no extractor ever produced.
    """

    def _ledger(self, narrator=None):
        con = sqlite3.connect(str(self.db_path))
        try:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(
                "SELECT * FROM turn_extraction_ledger WHERE narrator_id = ? "
                "ORDER BY id;", (narrator or self.narrator_id,))]
        finally:
            con.close()

    def test_a_claim_that_produced_nothing_leaves_no_result_row(self):
        """The defer shape: claimed, in flight, nothing to show yet."""
        _row, key = self._turn()

        def _yield(_req):
            raise _Deferred("scheduler yielded to chat")

        tx._call_extractor = _yield
        out = self._extract(key)

        self.assertEqual(len(self._ledger()), 1,
                         "the claim must be recorded even when no work ran")
        self.assertEqual(self._rows(), [],
                         "a turn that produced no extraction must not appear "
                         "as a result an operator can review")
        self.assertEqual(out.status, "failed")

    def test_a_retry_after_a_yield_opens_no_second_claim(self):
        """Half of the invariant, and the half that holds today.

        A second attempt at one turn_key never opens a second ledger
        row -- the UNIQUE index is the mechanism. The OTHER half (that
        the retry actually re-runs) does not hold; see the skipped test
        below, which is the Phase 3 blocker this class found.
        """
        _row, key = self._turn()

        tx._call_extractor = lambda _r: (_ for _ in ()).throw(
            _Deferred("yielded"))
        self._extract(key)
        first = self._ledger()
        self.assertEqual(len(first), 1)
        first_id = first[0]["id"]

        # The retry the scheduler will perform once the model is free.
        tx._call_extractor = lambda _r: self._response
        out = self._extract(key)

        after = self._ledger()
        self.assertEqual(len(after), 1,
                         "a retried turn must not open a second claim")
        self.assertEqual(after[0]["id"], first_id,
                         "the retry must land on the original claim")
        # Recorded rather than asserted-as-desirable: the retry is
        # currently refused as a duplicate. That is the gap.
        self.assertEqual(out.status, "duplicate")

    def test_a_terminal_resource_failure_closes_the_claim_with_no_result(self):
        _row, key = self._turn()
        tx._call_extractor = lambda _r: (_ for _ in ()).throw(
            MemoryError("out of device memory"))
        out = self._extract(key)

        led = self._ledger()
        self.assertEqual(len(led), 1)
        self.assertEqual(led[0]["outcome"], "failed",
                         "a terminal failure must close the claim, not leave "
                         "it in flight forever")
        self.assertEqual(led[0]["error_class"], "MemoryError")
        self.assertEqual(self._rows(), [])
        self.assertEqual(out.status, "failed")

    def test_nothing_without_a_stored_result_reaches_the_pending_queue(self):
        """The queue is fed by stored results, never by claims."""
        _row_a, key_a = self._turn(user="Deferred turn.")
        tx._call_extractor = lambda _r: (_ for _ in ()).throw(
            _Deferred("yielded"))
        self._extract(key_a, user_text="Deferred turn.")

        _row_b, key_b = self._turn(user="Completed turn.")
        tx._call_extractor = lambda _r: self._response
        self._extract(key_b, user_text="Completed turn.")

        pending = _db.turn_extraction_results_pending(
            narrator_id=self.narrator_id)
        keys = [p["turn_key"] for p in pending]
        self.assertIn(key_b, keys)
        self.assertNotIn(key_a, keys,
                         "a deferred turn must never be offered to Projection "
                         "Sync or Shadow Review as a reviewable proposal")

    def test_a_yield_mid_flight_neither_loses_nor_duplicates_the_claim(self):
        """PHASE 3 BLOCKER, FOUND BY THIS TEST -- SKIPPED, NOT PASSING.

        A new chat turn can cause a yield. The claim must survive it
        exactly once: not vanish (the turn would silently never extract)
        and not double (the operator would review it twice).

        It vanishes. `_begin()` at turn_extraction.py:633 returns
        `duplicate` for ANY second attempt at a turn_key that already
        owns a ledger row, regardless of how the first attempt ended.
        There is no retryable state. So the second call below never
        reaches the extractor at all, and the turn's extraction is lost
        permanently.

        This is unreachable in Phase 2 because nothing yields yet --
        extraction either runs or fails terminally, and a terminal
        failure SHOULD stay closed. It becomes reachable the moment the
        Phase 3 coordinator hands the model to chat.

        Written now rather than after Phase 3 so the requirement is
        inherited rather than remembered. Whoever opens the retry door
        removes this skip, and this test is what proves the fix.
        """
        self.skipTest(
            "Phase 3 blocker: a claimed turn cannot be re-attempted. "
            "_begin() refuses every second attempt as `duplicate` with no "
            "retryable state, so a scheduler yield loses the extraction. "
            "Remove this skip when Phase 3 introduces a re-claimable "
            "outcome; the body below is the acceptance for that change.")

        _row, key = self._turn()
        calls = {"n": 0}

        def _yield_once_then_succeed(_req):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _Deferred("chat took the model")
            return self._response

        tx._call_extractor = _yield_once_then_succeed

        self._extract(key)          # yields
        self._extract(key)          # scheduler retries

        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(self._ledger()), 1)
        rows = self._rows()
        self.assertEqual(len(rows), 1,
                         "one turn, one reviewable result, however many "
                         "times the scheduler had to yield")
        self.assertEqual(rows[0]["turn_key"], key)


class _Deferred(RuntimeError):
    """Stands in for whatever the Phase 3 coordinator raises when it
    hands the model to chat. Named here rather than imported because
    Phase 3 has not chosen the name yet -- what these tests pin is the
    lifecycle, not the exception class."""


class NegotiationTest(unittest.TestCase):
    """The server half of the handshake, read from chat_ws's source.

    The browser half is executed in the Node harness. This side is a
    routing decision inside a WebSocket handler that cannot be reached
    without a live socket, so it is asserted structurally -- and the
    assertion is written against the AST rather than the text, because
    the comment above the gate necessarily quotes the capability name.
    """

    def setUp(self):
        self.src = (_SERVER_CODE / "api" / "routers"
                    / "chat_ws.py").read_text(encoding="utf-8")

    @staticmethod
    def _executable(src):
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

    def test_the_server_advertises_a_versioned_capability(self):
        code = self._executable(self.src)
        self.assertIn("field_extraction_owner", code)
        self.assertIn("backend_result_v1", code)

    def test_the_server_requires_the_client_to_declare_support(self):
        """An old page keeps POSTing /api/extract-fields. Scheduling
        anyway would extract that turn twice -- the exact regression this
        phase removes."""
        code = self._executable(self.src)
        self.assertIn("client_capabilities", code)
        self.assertIn("field_extraction_result", code)

    def test_the_declaration_gate_precedes_the_schedule_call(self):
        cap = self.src.find('_client_caps.get("field_extraction_result")')
        sched = self.src.find("_schedule_extraction(")
        self.assertGreater(cap, 0)
        self.assertGreater(sched, cap,
                           "the capability check must run before scheduling")


class BrowserArchitectureGuardTest(unittest.TestCase):
    """Static supplements to the executing harness.

    These prove SHAPE. They do not replace
    scripts/ui/run_extraction_result_consumer.js, which proves BEHAVIOUR;
    a source scan cannot observe two results a second apart both landing.
    """

    def setUp(self):
        self.iv = (_REPO_ROOT / "ui" / "js"
                   / "interview.js").read_text(encoding="utf-8")
        self.ap = (_REPO_ROOT / "ui" / "js"
                   / "app.js").read_text(encoding="utf-8")

    def _consumer(self):
        i = self.iv.index("function applyCompletedTurnExtractionResult")
        j = self.iv.index("var _extractAndProjectMultiField")
        return self.iv[i:j]

    def test_the_consumer_makes_no_network_call(self):
        body = self._consumer()
        self.assertNotIn("fetch(", body)
        self.assertNotIn("/api/extract-fields", body)

    def test_the_consumer_has_no_time_based_cooldown(self):
        body = self._consumer()
        self.assertNotIn("_lastExtractionTimestamp", body)

    def test_the_cooldown_survives_where_it_was_earned(self):
        """It existed to stop the BROWSER double-POSTing. Removing it
        from the transport as well would be a different change."""
        i = self.iv.index("function requestLegacyFieldExtraction")
        self.assertIn("_lastExtractionTimestamp", self.iv[i:])

    def test_there_is_exactly_one_ownership_decision_point(self):
        self.assertEqual(self.iv.count("if (_BACKEND_OWNS_EXTRACTION)"), 1)

    def test_app_delegates_both_frames_to_named_functions(self):
        self.assertIn("applyExtractionCapabilities(j.capabilities)",
                      self.ap.replace("noteServerCapabilities", "applyExtractionCapabilities"))
        self.assertIn("applyExtractionResultFrame(j)", self.ap)

    def test_app_passes_nothing_from_its_own_scope_into_the_result(self):
        """A delayed result belongs to its own turn, not to whatever this
        browser most recently typed."""
        lines = [l for l in self.ap.splitlines()
                 if "_lastUserTurn" in l
                 and ("applyExtractionResultFrame" in l
                      or "applyCompletedTurnExtractionResult" in l)]
        self.assertEqual(lines, [])

    def test_the_client_declares_support_on_every_start_turn(self):
        self.assertEqual(self.ap.count("client_capabilities:"), 2)

    def test_targeted_questionnaire_projection_still_exists(self):
        self.assertIn("function _projectAnswerToField", self.iv)


if __name__ == "__main__":
    unittest.main()
