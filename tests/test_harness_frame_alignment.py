"""A refused turn must leave the socket clean for the next one.

`WO-LORI-LISTEN-AND-RETAIN-01` §9.

── THE DEFECT THIS PINS ──────────────────────────────────────────────

The server's blocked-turn contract is **`error` THEN `done`**. Every
refusal path sends both: `PROMPT_TOO_LARGE`, `VRAM_PRESSURE`,
`GENERATION_BUSY`, `CUDA_OOM`.

`_send_turn_and_capture` returned as soon as it saw `error`, leaving that
`done` queued on the WebSocket. The next era would send its chapter and
immediately read the PREVIOUS turn's completion frame — so from the first
refusal onward, every result was attributed to the wrong era. Silently,
with entirely plausible-looking output.

**And refusal is one of the outcomes this diagnostic exists to find.**
The failure was triggered by the very thing being measured, which is the
worst possible coupling: the run would look successful and the data would
be wrong from the point the interesting thing happened.

── WHY A FAKE SOCKET AND NOT A LIVE ONE ──────────────────────────────

The property is about frame bookkeeping, not about the server. A fake
socket states the exact sequence — including the interleaving that caused
the bug — where a live run would need a real refusal to reproduce it and
would still only cover the one refusal it happened to trigger.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
for _p in (str(_REPO), str(_REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── `websockets` IS STUBBED, AND ONLY IT ─────────────────────────────
#
# `harness_lib` imports the library at module scope. These tests drive
# `_send_turn_and_capture` against a fake socket object and never open a
# connection, so the real library plays no part in what is being proven
# — but its absence would make every test here an ERROR on any
# interpreter without it, and an interpreter that cannot run a test is
# how a suite quietly stops covering something.
#
# Only the import is satisfied. Nothing about frame ordering, which is
# the actual subject, comes from the stub.
if "websockets" not in sys.modules:
    import types
    _ws_stub = types.ModuleType("websockets")

    def _refuse_connect(*_a, **_k):           # pragma: no cover
        raise AssertionError(
            "these tests must not open a real WebSocket — they prove "
            "frame bookkeeping, not connectivity")

    _ws_stub.connect = _refuse_connect
    sys.modules["websockets"] = _ws_stub


class _FakeWS:
    """A socket that hands out queued frames in order.

    `recv` raising when the queue empties is deliberate: it turns
    "consumed a frame that was not there" into a visible failure instead
    of a hang.
    """

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        if not self._frames:
            raise AssertionError(
                "the harness tried to read a frame that was never sent — "
                "it is consuming another turn's output")
        return json.dumps(self._frames.pop(0))

    @property
    def remaining(self):
        return list(self._frames)


def _capture(ws, *, text="chapter text", label="Era 1", era="today"):
    import harness_lib
    return asyncio.get_event_loop().run_until_complete(
        harness_lib._send_turn_and_capture(
            ws, text=text, conv_id="c1", person_id="p1",
            speaker_name="Walt", runtime71_era=era,
            chapter_label=label, client_turn_id=f"t:{label}"))


class ARefusedTurnConsumesItsOwnDoneTests(unittest.TestCase):

    def setUp(self):
        try:
            asyncio.get_event_loop()
        except RuntimeError:                  # pragma: no cover
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_the_error_frame_does_not_end_the_turn(self):
        """The regression. Was: return at `error`, leaving `done` queued."""
        ws = _FakeWS([
            {"type": "error", "code": "VRAM_PRESSURE", "message": "no room"},
            {"type": "done", "final_text": "", "blocked": "vram_pressure"},
        ])
        final, events = _capture(ws)
        self.assertEqual("", final)
        self.assertEqual(
            [], ws.remaining,
            "the turn's `done` frame was left on the socket for the next "
            "era to consume")
        self.assertEqual(["error", "done"], [e["type"] for e in events])

    def test_the_next_turn_cannot_eat_the_previous_turns_done(self):
        """The decisive case, driven end to end.

        Turn A is refused; turn B is normal. If A returned early, B's
        first read would be A's `done` and B would report an empty
        response while A's real completion vanished.
        """
        ws = _FakeWS([
            # turn A — refused
            {"type": "error", "code": "PROMPT_TOO_LARGE"},
            {"type": "done", "final_text": "", "blocked": "prompt_too_large"},
            # turn B — a normal answer
            {"type": "token", "delta": "I remember "},
            {"type": "token", "delta": "the mill."},
            {"type": "done", "final_text": "I remember the mill."},
        ])
        a_text, _ = _capture(ws, label="Era 6")
        b_text, b_events = _capture(ws, label="Era 7")

        self.assertEqual("", a_text)
        self.assertEqual(
            "I remember the mill.", b_text,
            "the second era did not receive its own response — the frames "
            "are off by one turn")
        self.assertNotIn(
            "error", [e["type"] for e in b_events],
            "the second era inherited the first era's error frame")
        self.assertEqual([], ws.remaining)

    def test_a_normal_turn_is_unaffected(self):
        """The positive control.

        A fix that broke ordinary turns would satisfy the two tests above
        for the wrong reason.
        """
        ws = _FakeWS([
            {"type": "token", "delta": "Yes. "},
            {"type": "token", "delta": "Go on."},
            {"type": "done", "final_text": "Yes. Go on."},
        ])
        final, events = _capture(ws)
        self.assertEqual("Yes. Go on.", final)
        self.assertEqual([], ws.remaining)
        self.assertEqual("done", events[-1]["type"])

    def test_every_refusal_code_behaves_the_same_way(self):
        """All four server refusal paths send `error` then `done`.

        Naming them individually so a new refusal code added without its
        `done` is caught here rather than during a two-hour run.
        """
        for code in ("PROMPT_TOO_LARGE", "VRAM_PRESSURE",
                     "GENERATION_BUSY", "CUDA_OOM"):
            with self.subTest(code=code):
                ws = _FakeWS([
                    {"type": "error", "code": code},
                    {"type": "done", "final_text": ""},
                ])
                final, _ = _capture(ws)
                self.assertEqual("", final)
                self.assertEqual([], ws.remaining)


class TheHarnessSendsADeterministicTurnIdTests(unittest.TestCase):
    """The join key between the trace, the console and the GPU timeline."""

    def setUp(self):
        try:
            asyncio.get_event_loop()
        except RuntimeError:                  # pragma: no cover
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_the_id_reaches_the_params_contract(self):
        ws = _FakeWS([{"type": "done", "final_text": "ok"}])
        _capture(ws, label="Era 3")
        sent = ws.sent[0]
        self.assertEqual("t:Era 3",
                         sent["params"].get("client_turn_id"))

    def test_the_cap_is_still_256(self):
        """Not raised before the measurement that asks whether it binds."""
        ws = _FakeWS([{"type": "done", "final_text": "ok"}])
        _capture(ws)
        self.assertEqual(256, ws.sent[0]["params"]["max_new_tokens"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
