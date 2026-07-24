"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.2 — COMMIT 3 tests.

Per-turn cancellation events. The old socket-wide pattern
(`ev.set(); current_task.cancel(); ev.clear()`) had a race: the clear
could land while the previous generation thread was between StopOnEvent
checks, un-cancelling it — an old generation could observe a newly
cleared event and keep streaming a dead turn's tokens.

Invariant under test: every start_turn mints a FRESH threading.Event
owned by exactly that generation; a superseded turn's event is set once
and NEVER cleared. cancel_turn and WebSocket disconnect target the
ACTIVE turn's event.

Behavior tests drive the REAL ws_chat handler via the shared
ChatWsHarness; the fake model records the exact Event object each
generation's StopOnEvent received, plus whether it was already set at
generation start.
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.test_chat_ws_safety_precedence import (  # noqa: E402
    ChatWsHarness,
    _HarnessCase,
)

_CHAT_WS_SRC = (
    _SERVER_CODE / "api" / "routers" / "chat_ws.py"
).read_text(encoding="utf-8")

BENIGN_A = "Then we drove north toward Fargo that afternoon."
BENIGN_B = "Later that summer we visited my brother in Duluth."


def _start_turn(conv: str, message: str, person_id: str):
    return {
        "type": "start_turn", "session_id": conv, "message": message,
        "turn_mode": "interview",
        "params": {"person_id": person_id},
    }


def _wait_generation(h: ChatWsHarness):
    """Script callable: block until the fake model reports a generation
    has started, then clear the latch for the next one."""
    async def _wait():
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if h.generation_started.is_set():
                h.generation_started.clear()
                return None
            await asyncio.sleep(0.005)
        raise AssertionError("generation never started")
    return _wait


class NewTurnSupersedesOldTest(_HarnessCase):
    def test_turn_b_sets_turn_a_event_permanently_and_gets_fresh_event(self):
        with ChatWsHarness(block_generation=True) as h:
            conv = "conv_cancel_ab"
            ws = h.run([
                _start_turn(conv, BENIGN_A, h.person_id),
                _wait_generation(h),          # A is generating
                _start_turn(conv, BENIGN_B, h.person_id),
                _wait_generation(h),          # B is generating
                # script exhausted → disconnect (sets B's event, ends B)
            ])
            self.assertEqual(len(h.generation_events), 2,
                             "both generations must have run: %r" % ws.sent)
            ev_a, ev_b = h.generation_events
            self.assertIsNotNone(ev_a)
            self.assertIsNotNone(ev_b)
            # Different event objects — per-turn ownership.
            self.assertIsNot(ev_a, ev_b)
            # A's event was set (permanently) when B started; it is
            # STILL set now — never cleared. An old generation can never
            # observe a newly cleared event.
            self.assertTrue(ev_a.is_set())
            # B received a fresh, UNSET event at its generation start.
            self.assertFalse(h.generation_start_states[1],
                             "turn B must start with an unset event")


class CancelTurnTest(_HarnessCase):
    def test_cancel_turn_sets_the_active_events_own_event(self):
        with ChatWsHarness(block_generation=True) as h:
            conv = "conv_cancel_explicit"
            ws = h.run([
                _start_turn(conv, BENIGN_A, h.person_id),
                _wait_generation(h),
                {"type": "cancel_turn"},
                ("wait_done", 1),   # generation observes the event, ends
            ])
            self.assertEqual(len(h.generation_events), 1)
            self.assertTrue(h.generation_events[0].is_set())
            # The handler acked the cancellation...
            self.assertTrue(any(
                m.get("type") == "status" and m.get("state") == "cancelled"
                for m in ws.sent))
            # ...and the turn finished on the fail-closed cancelled path
            # (no persistence of a half-generated turn).
            done = ws.dones()[0]
            self.assertTrue(done.get("cancelled"))


class DisconnectTest(_HarnessCase):
    def test_disconnect_sets_the_active_turn_event(self):
        with ChatWsHarness(block_generation=True) as h:
            conv = "conv_cancel_disconnect"
            h.run([
                _start_turn(conv, BENIGN_A, h.person_id),
                _wait_generation(h),
                # script exhausted → WebSocketDisconnect while generating
            ])
            self.assertEqual(len(h.generation_events), 1)
            self.assertTrue(
                h.generation_events[0].is_set(),
                "disconnect must set the in-flight turn's cancel event")


class NoEventClearSourceScanTest(unittest.TestCase):
    """The invariant is structural too: no executable ev.clear() left."""

    def test_no_executable_event_clear_remains(self):
        self.assertIsNone(
            re.search(r"^\s*(?:ev|current_cancel_event)\.clear\(\)",
                      _CHAT_WS_SRC, re.MULTILINE),
            "an executable cancel-event .clear() re-appeared — an old "
            "generation could observe a newly cleared event again")

    def test_per_turn_event_is_minted_on_start_turn(self):
        i = _CHAT_WS_SRC.index('elif msg_type == "start_turn"')
        block = _CHAT_WS_SRC[i:i + 3000]
        self.assertIn("current_cancel_event = threading.Event()", block)
        self.assertIn("current_cancel_event.set()", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
