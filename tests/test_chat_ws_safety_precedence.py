"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 — COMMIT 2 tests.

Deterministic safety scan must precede EVERY narrator short-circuit in
chat_ws: claimed-floor buffering, identity/meta-question detection,
travel-doc modal / trip direct answers, memory-echo routing, witness
routing, follow-up-bank flushing.

These are BEHAVIOR tests, not source-scans: they import the REAL
`api.routers.chat_ws` module (real fastapi / torch / transformers are
available; model load is lazy), point the DB layer at a private temp
SQLite file, stub ONLY the heavyweight LLM pieces (`_load_model`,
`TextIteratorStreamer`, `_apply_chat_template`, `compose_system_prompt`)
and the filesystem archive writers, then drive the real `ws_chat`
WebSocket handler end to end with a fake WebSocket object. Every route
decision under test is made by production code.

The `ChatWsHarness` / `FakeWS` classes below are shared by the other
COMMIT-3 chat_ws behavior test modules
(tests/test_chat_ws_guard_failure.py,
 tests/test_chat_ws_turn_cancellation.py,
 tests/test_chat_ws_session_identity.py) — keep them import-stable.
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

# DATA_DIR must be a throwaway before api.db first computes its paths —
# nothing in these tests may touch the real data tree.
os.environ.setdefault(
    "DATA_DIR", tempfile.mkdtemp(prefix="hornelore_chatws_tests_"))
# The LLM safety second-layer stays OFF (its own suites cover it); the
# deterministic pattern layer is the subject here.
os.environ["HORNELORE_SAFETY_LLM_LAYER"] = "0"
os.environ.pop("LV_ENABLE_SAFETY", None)  # default-ON kill-switch

from fastapi import WebSocketDisconnect  # noqa: E402  (real fastapi)

from api import db as _db  # noqa: E402
from api.routers import chat_ws as _chat_ws  # noqa: E402
from api import safety as _safety  # noqa: E402


# ── Fake WebSocket ─────────────────────────────────────────────────────────

class FakeWS:
    """Drives ws_chat. `script` is a list of:
      - dict            → returned from receive_json as a client message
      - ("wait_done",n) → receive_json blocks until n `done` events sent
      - callable        → invoked (may be async); a dict result is
                          returned as a message, anything else skipped
    When the script is exhausted, raises WebSocketDisconnect (after
    waiting for any outstanding turns via a final explicit wait entry —
    callers should end scripts with ("wait_done", n))."""

    def __init__(self, script):
        self.script = list(script)
        self.sent: List[Dict[str, Any]] = []

    async def accept(self):
        return None

    async def send_text(self, text: str):
        self.sent.append(json.loads(text))

    # ── helpers for assertions ──
    def events(self, ev_type: str) -> List[Dict[str, Any]]:
        return [m for m in self.sent if m.get("type") == ev_type]

    def dones(self) -> List[Dict[str, Any]]:
        return self.events("done")

    async def _wait_dones(self, n: int, timeout: float = 30.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.dones()) >= n:
                return True
            await asyncio.sleep(0.01)
        return False

    async def receive_json(self):
        while self.script:
            item = self.script.pop(0)
            if callable(item):
                res = item()
                if asyncio.iscoroutine(res):
                    res = await res
                if isinstance(res, dict):
                    return res
                continue
            if isinstance(item, tuple) and item and item[0] == "wait_done":
                await self._wait_dones(int(item[1]))
                continue
            return item
        raise WebSocketDisconnect()


# ── LLM stack stubs (structure mirrors the real objects chat_ws touches) ──

class _FakeTensor:
    shape = (1, 8)


class _FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=_FakeTensor())

    def to(self, device):
        return self


class _FakeTok:
    eos_token_id = 0

    def encode(self, prompt):
        return [1] * 8

    def __call__(self, prompt, return_tensors=None):
        return _FakeInputs()


class _FakeStreamer:
    """Queue-backed stand-in for TextIteratorStreamer. `None` is the
    end-of-stream sentinel (maps onto StopIteration exactly like the
    real streamer)."""

    def __init__(self, tok=None, skip_prompt=True, skip_special_tokens=True):
        self.q: "queue.Queue" = queue.Queue()

    def __iter__(self):
        return self

    def __next__(self):
        item = self.q.get()
        if item is None:
            raise StopIteration
        return item


class _FakeModel:
    device = "cpu"

    def __init__(self, harness: "ChatWsHarness"):
        self.h = harness

    def generate(self, input_ids=None, streamer=None,
                 stopping_criteria=None, **kw):
        h = self.h
        # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 follow-up
        # (serialize generation): track how many generate() calls are in
        # flight AT ONCE — production must never overlap them on a
        # socket (dual-generation VRAM pressure, the audit finding).
        with h.gen_lock:
            h.llm_calls += 1
            h.active_generations += 1
            h.max_concurrent_generations = max(
                h.max_concurrent_generations, h.active_generations)
        try:
            # Record the per-generation cancellation event exactly as the
            # production StopOnEvent received it — the cancellation tests
            # assert on THESE objects.
            ev: Optional[threading.Event] = None
            try:
                ev = stopping_criteria[0].ev
            except Exception:
                ev = None
            h.generation_events.append(ev)
            # Was this generation's OWN event already set when it started?
            # (Per-turn cancellation invariant: a fresh turn must receive
            # a fresh, UNSET event.)
            h.generation_start_states.append(
                bool(ev is not None and ev.is_set()))
            h.generation_started.set()
            if h.block_generation:
                # Long-running generation: only the stop event releases
                # it, exactly like a real generate() honoring StopOnEvent.
                deadline = time.monotonic() + 30.0
                while (ev is not None and not ev.is_set()
                       and time.monotonic() < deadline):
                    time.sleep(0.005)
            if h.generation_exit_delay:
                # Simulates the token-boundary latency between the stop
                # event being observed and generate() actually RETURNING
                # — the exact window where an unserialized second
                # generate would overlap this one.
                time.sleep(h.generation_exit_delay)
            streamer.q.put(h.llm_text)
            streamer.q.put(None)
        finally:
            with h.gen_lock:
                h.active_generations -= 1


# ── The harness ────────────────────────────────────────────────────────────

class ChatWsHarness:
    """Context manager: temp DB + narrator person row + LLM stubs patched
    onto the REAL chat_ws module globals. Restores everything on exit."""

    DEFAULT_LLM_TEXT = "I'm here with you, and I'm listening closely."

    def __init__(self, llm_text: str = "", block_generation: bool = False):
        self.llm_text = llm_text or self.DEFAULT_LLM_TEXT
        self.block_generation = block_generation
        self.llm_calls = 0
        self.generation_events: List[Optional[threading.Event]] = []
        self.generation_start_states: List[bool] = []
        self.generation_started = threading.Event()
        # Serialize-generation follow-up instrumentation:
        self.gen_lock = threading.Lock()
        self.active_generations = 0
        self.max_concurrent_generations = 0
        self.generation_exit_delay = 0.0
        self.scan_calls: List[str] = []
        self.person_id: str = ""
        self._patched: Dict[str, Any] = {}
        self._db_path: Optional[Path] = None
        self._orig_db_path = None

    # -- scan wrapper (counts + delegates to the REAL deterministic scan) --
    def _counting_scan(self, text):
        self.scan_calls.append(text)
        return _safety.scan_answer(text)

    # ── DB split-brain defense ────────────────────────────────────────
    # Some test modules (e.g. tests/test_chatws_conv_fk_hygiene.py)
    # DELETE api.db from sys.modules mid-suite, so in a shared process
    # several api.db module INSTANCES can coexist: the one this module
    # imported at load time, the one currently in sys.modules (used by
    # chat_ws's lazy `from ..db import ...` calls), and the one whose
    # functions chat_ws bound at ITS import time. Point every reachable
    # instance's DB_PATH at the same temp file so the whole turn reads
    # and writes one database.
    def _db_target_dicts(self):
        dicts = []
        seen = set()

        def _add(d):
            if isinstance(d, dict) and id(d) not in seen:
                seen.add(id(d))
                dicts.append(d)

        _add(_db.__dict__)
        for _name in ("api.db", "server.code.api.db"):
            _mod = sys.modules.get(_name)
            if _mod is not None:
                _add(getattr(_mod, "__dict__", None))
        # The globals dict backing chat_ws's module-scope db bindings —
        # live even if that instance lost its sys.modules slot.
        try:
            _add(_chat_ws.persist_turn_transaction.__globals__)
        except Exception:
            pass
        return dicts

    def __enter__(self) -> "ChatWsHarness":
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        tmp.close()
        self._db_path = Path(tmp.name)
        # Some suites DELETE api.db from sys.modules and rely on env-var
        # re-import; if the slot is empty, chat_ws's lazy
        # `from ..db import ...` calls would mint a FRESH instance
        # mid-turn (after we've synced DB_PATH) pointed at the default
        # database. Re-register our known instance first.
        sys.modules.setdefault("api.db", _db)
        self._orig_db_paths = []
        for _d in self._db_target_dicts():
            self._orig_db_paths.append((_d, _d.get("DB_PATH")))
            _d["DB_PATH"] = self._db_path
        _db.init_db()
        person = _db.create_person(
            display_name="Harness Narrator",
            date_of_birth="",
            place_of_birth="",
            narrator_type="live",
            pronouns="they_them",
            current_residence="",
        )
        self.person_id = person["id"] if isinstance(person, dict) else person

        self.tok = _FakeTok()
        self.model = _FakeModel(self)

        def _patch(name: str, value: Any):
            self._patched[name] = getattr(_chat_ws, name)
            setattr(_chat_ws, name, value)

        _patch("_load_model", lambda: (self.model, self.tok))
        _patch("TextIteratorStreamer", _FakeStreamer)
        _patch("_apply_chat_template", lambda msgs: "PROMPT")
        _patch("compose_system_prompt",
               lambda conv_id, ui_system=None, user_text=None,
               runtime71=None: "SYSTEM PROMPT")
        _patch("archive_ensure_session", lambda **kw: None)
        _patch("archive_append_event", lambda **kw: None)
        _patch("archive_rebuild_txt", lambda **kw: None)
        _patch("scan_answer", self._counting_scan)
        return self

    def __exit__(self, *exc):
        for name, value in self._patched.items():
            setattr(_chat_ws, name, value)
        self._patched.clear()
        for _d, _orig in self._orig_db_paths:
            _d["DB_PATH"] = _orig
        self._orig_db_paths = []
        try:
            if self._db_path:
                self._db_path.unlink()
        except OSError:
            pass
        return False

    # -- drive the real WebSocket handler --
    def run(self, script) -> FakeWS:
        ws = FakeWS(script)
        asyncio.run(_chat_ws.ws_chat(ws))
        return ws

    def run_turn(self, conv_id: str, message: str,
                 params: Optional[Dict[str, Any]] = None,
                 turn_mode: str = "interview") -> FakeWS:
        params = dict(params or {})
        params.setdefault("person_id", self.person_id)
        return self.run([
            {"type": "start_turn", "session_id": conv_id,
             "message": message, "turn_mode": turn_mode, "params": params},
            ("wait_done", 1),
        ])

    # -- DB assertion helpers --
    def sensitive_flags(self, conv_id: str) -> List[Dict[str, Any]]:
        return [f for f in (_db.get_segment_flags(conv_id) or [])
                if f.get("sensitive")]

    def safety_events_count(self, conv_id: str) -> int:
        import sqlite3
        con = sqlite3.connect(str(self._db_path))
        try:
            return con.execute(
                "SELECT COUNT(*) FROM safety_events WHERE session_id=?",
                (conv_id,)).fetchone()[0]
        finally:
            con.close()


DISTRESS = "I want to kill myself."


class _HarnessCase(unittest.TestCase):
    def assert_no_ws_errors(self, ws: FakeWS):
        self.assertEqual(
            ws.events("error"), [],
            "handler emitted error events — harness or route broke: %r"
            % ws.sent)


# ── 1. Distress + identity/meta language → safety wins ────────────────────

class DistressBeatsMetaQuestionTest(_HarnessCase):
    def test_meta_shaped_distress_routes_to_safety_not_identity(self):
        with ChatWsHarness() as h:
            conv = "conv_meta_distress"
            ws = h.run_turn(conv, "What is your name? " + DISTRESS)
            self.assert_no_ws_errors(ws)
            # Deterministic pattern layer ran on the turn text.
            self.assertEqual(len(h.scan_calls), 1)
            # Complete safety cascade: UI event + resources + DB rows.
            triggered = ws.events("safety_triggered")
            self.assertEqual(len(triggered), 1)
            self.assertEqual(triggered[0].get("category"),
                             "suicidal_ideation")
            self.assertTrue(triggered[0].get("resources"))
            self.assertEqual(len(h.sensitive_flags(conv)), 1)
            self.assertEqual(h.safety_events_count(conv), 1)
            # Route: forced interview — never the identity answer.
            done = ws.dones()[0]
            self.assertEqual(done.get("turn_mode"), "interview")
            final = done.get("final_text") or ""
            self.assertNotIn("Lori", final.split(".")[0][:20])
            self.assertNotIn("meta_question", json.dumps(ws.sent))

    def test_benign_identity_question_still_deterministic(self):
        # Control: without distress the identity route still answers.
        with ChatWsHarness() as h:
            ws = h.run_turn("conv_meta_benign", "What is your name?")
            self.assert_no_ws_errors(ws)
            self.assertEqual(ws.dones()[0].get("turn_mode"), "meta_question")
            self.assertEqual(h.llm_calls, 0)


# ── 2. Benign "Are you safe to talk to?" — the Mary fix preserved ─────────

class BenignSafeToTalkTest(_HarnessCase):
    def test_scan_runs_but_meta_route_wins_without_escalation(self):
        with ChatWsHarness() as h:
            conv = "conv_mary"
            ws = h.run_turn(conv, "Are you safe to talk to?")
            self.assert_no_ws_errors(ws)
            # FORBIDDEN per WO §2.3: skipping the deterministic scan for
            # meta questions. It must run — and not trigger.
            self.assertEqual(len(h.scan_calls), 1)
            self.assertEqual(ws.events("safety_triggered"), [])
            self.assertEqual(h.sensitive_flags(conv), [])
            self.assertEqual(h.safety_events_count(conv), 0)
            # Deterministic meta route still available and no LLM call
            # (the LLM safety classifier stays skipped for meta routes).
            self.assertEqual(ws.dones()[0].get("turn_mode"), "meta_question")
            self.assertEqual(h.llm_calls, 0)


# ── 3 + 4. Claimed-floor buffering vs safety ──────────────────────────────

class FloorBufferPrecedenceTest(_HarnessCase):
    def test_distress_chunk_is_never_buffered_away(self):
        with ChatWsHarness() as h:
            conv = "conv_floor_distress"
            ws = h.run_turn(conv, DISTRESS, params={"turn_final": False})
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            # No "I'm listening." buffer ack; full safety handling.
            self.assertNotEqual(done.get("turn_mode"), "floor_buffer")
            self.assertEqual(done.get("turn_mode"), "interview")
            self.assertNotEqual(done.get("final_text"), "I'm listening.")
            self.assertEqual(len(ws.events("safety_triggered")), 1)
            # The chunk itself is flagged — no chapter-completion rescan.
            self.assertEqual(len(h.sensitive_flags(conv)), 1)
            self.assertEqual(h.safety_events_count(conv), 1)

    def test_benign_chunk_keeps_buffer_ack_and_persistence(self):
        with ChatWsHarness() as h:
            conv = "conv_floor_benign"
            ws = h.run_turn(
                conv, "And then we drove on toward Bismarck that morning",
                params={"turn_final": False})
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            self.assertEqual(done.get("turn_mode"), "floor_buffer")
            self.assertEqual(done.get("final_text"), "I'm listening.")
            self.assertEqual(h.llm_calls, 0)
            # Existing persistence behavior: the chunk is retained.
            turns = _db.export_turns(conv) or []
            user_turns = [t for t in turns if t.get("role") == "user"]
            self.assertTrue(any("Bismarck" in (t.get("content") or "")
                                for t in user_turns))


# ── 5. Safety + memory-echo wording ───────────────────────────────────────

class MemoryEchoPrecedenceTest(_HarnessCase):
    def test_distress_with_echo_wording_stays_on_safety_route(self):
        with ChatWsHarness() as h:
            conv = "conv_echo_distress"
            ws = h.run_turn(conv, "What do you know about me? " + DISTRESS)
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            self.assertEqual(done.get("turn_mode"), "interview")
            self.assertEqual(len(ws.events("safety_triggered")), 1)
            self.assertEqual(len(h.sensitive_flags(conv)), 1)

    def test_benign_echo_wording_still_routes_memory_echo(self):
        # Control: the server-side memory-echo trigger still works.
        with ChatWsHarness() as h:
            ws = h.run_turn("conv_echo_benign", "What do you know about me?")
            self.assert_no_ws_errors(ws)
            self.assertEqual(ws.dones()[0].get("turn_mode"), "memory_echo")


# ── 6. Safety + witness/meta-feedback wording ─────────────────────────────

class WitnessPrecedenceTest(_HarnessCase):
    WITNESS_FEEDBACK = "You are being vague."

    def test_distress_with_meta_feedback_stays_on_safety_route(self):
        with ChatWsHarness() as h:
            conv = "conv_witness_distress"
            ws = h.run_turn(conv, self.WITNESS_FEEDBACK + " " + DISTRESS)
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            self.assertNotEqual(done.get("turn_mode"), "witness")
            self.assertEqual(done.get("turn_mode"), "interview")
            self.assertEqual(len(ws.events("safety_triggered")), 1)
            self.assertEqual(len(h.sensitive_flags(conv)), 1)

    def test_benign_meta_feedback_still_routes_witness(self):
        # Control: witness META_FEEDBACK still wins on a benign turn.
        with ChatWsHarness() as h:
            ws = h.run_turn("conv_witness_benign", self.WITNESS_FEEDBACK)
            self.assert_no_ws_errors(ws)
            self.assertEqual(ws.dones()[0].get("turn_mode"), "witness")
            self.assertEqual(h.llm_calls, 0)


# ── 7. Safety + bank-flush trigger ────────────────────────────────────────

class BankFlushPrecedenceTest(_HarnessCase):
    def _seed_bank(self, conv: str, person_id: str) -> str:
        return _db.followup_bank_add(
            session_id=conv,
            intent="relationship_expansion",
            question_en="Who traveled with you on that trip?",
            triggering_anchor="the trip",
            why_it_matters="companion detail",
            priority=4,
            triggering_turn_index=1,
            person_id=person_id,
        )

    def test_distress_flush_trigger_emits_no_banked_question(self):
        with ChatWsHarness() as h:
            conv = "conv_bank_distress"
            self._seed_bank(conv, h.person_id)
            ws = h.run_turn(conv, "What else? " + DISTRESS)
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            self.assertNotEqual(done.get("turn_mode"), "bank_flush")
            self.assertEqual(done.get("turn_mode"), "interview")
            self.assertNotIn("Who traveled with you",
                             done.get("final_text") or "")
            self.assertEqual(len(ws.events("safety_triggered")), 1)
            # The banked row was NOT burned (not marked asked).
            still_open = _db.followup_bank_get_unanswered(conv)
            self.assertEqual(len(still_open), 1)

    def test_benign_flush_trigger_still_flushes(self):
        # Control: the bank-flush lane itself still works.
        with ChatWsHarness() as h:
            conv = "conv_bank_benign"
            self._seed_bank(conv, h.person_id)
            ws = h.run_turn(conv, "What else do you want to know?")
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            self.assertEqual(done.get("turn_mode"), "bank_flush")
            self.assertIn("Who traveled with you",
                          done.get("final_text") or "")
            self.assertEqual(_db.followup_bank_get_unanswered(conv), [])


# ── 8. scan_answer raises → default-safe, no deterministic takeover ──────

class ScanFailureDefaultSafeTest(_HarnessCase):
    def test_scan_crash_forces_interview_over_meta_route(self):
        with ChatWsHarness() as h:
            def _boom(text):
                h.scan_calls.append(text)
                raise RuntimeError("simulated scan crash")
            _chat_ws.scan_answer = _boom  # restored by harness __exit__
            ws = h.run_turn("conv_scanfail_meta", "What is your name?")
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            # Default-safe: the LLM interview path answers — no
            # deterministic identity route may take over.
            self.assertEqual(done.get("turn_mode"), "interview")
            self.assertEqual(h.llm_calls, 1)

    def test_scan_crash_forces_interview_over_memory_echo(self):
        with ChatWsHarness() as h:
            def _boom(text):
                h.scan_calls.append(text)
                raise RuntimeError("simulated scan crash")
            _chat_ws.scan_answer = _boom
            ws = h.run_turn("conv_scanfail_echo",
                            "What do you know about me?")
            self.assert_no_ws_errors(ws)
            self.assertEqual(ws.dones()[0].get("turn_mode"), "interview")


# ── 9. Deterministic scan executes exactly once per narrator turn ────────

class ScanExactlyOnceTest(_HarnessCase):
    def test_distress_turn_scans_exactly_once(self):
        with ChatWsHarness() as h:
            h.run_turn("conv_once_distress", DISTRESS)
            self.assertEqual(len(h.scan_calls), 1)

    def test_benign_interview_turn_scans_exactly_once(self):
        with ChatWsHarness() as h:
            h.run_turn("conv_once_benign",
                       "We lived on a farm outside Minot back then.")
            self.assertEqual(len(h.scan_calls), 1)


# ── 10. System directives retain existing handling ────────────────────────

class SystemDirectiveHandlingTest(_HarnessCase):
    FLOOR_HOLD = ("[SYSTEM: The narrator pressed and held the floor. "
                  "Do not ask a question. Do not summarize.]")

    def test_floor_hold_directive_not_scanned_and_keeps_ack(self):
        with ChatWsHarness() as h:
            ws = h.run_turn("conv_directive", self.FLOOR_HOLD)
            self.assert_no_ws_errors(ws)
            # Directives are not narrator disclosures — never scanned.
            self.assertEqual(h.scan_calls, [])
            done = ws.dones()[0]
            self.assertEqual(done.get("turn_mode"), "floor_hold")
            self.assertIn(done.get("final_text"),
                          ("Take your time.", "I'm listening.",
                           "Keep going."))
            self.assertEqual(ws.events("safety_triggered"), [])
            self.assertEqual(h.llm_calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
