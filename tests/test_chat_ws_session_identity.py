"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.3 — COMMIT 3 tests.

No shared "default" sessions. Two ID-less WebSocket clients used to
land in the SAME literal conv_id "default" — sharing history, softened
state, segment flags, and follow-up-bank rows across narrators. Now
each socket mints `socket_conv_id = f"ws_{uuid.uuid4()}"` at connect
and every ID-less start_turn uses it; supplied session_id/conv_id
values are honored verbatim.

Behavior tests drive the REAL ws_chat handler (shared ChatWsHarness);
the conv_id each turn actually used is observed through the
persist_turn_transaction call the deterministic floor-hold path makes.
One source-scan assertion pins the absence of any executable
`or "default"` session fallback, per the WO.
"""
from __future__ import annotations

import sys
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
from api.routers import chat_ws as _chat_ws  # noqa: E402

_CHAT_WS_SRC = (
    _SERVER_CODE / "api" / "routers" / "chat_ws.py"
).read_text(encoding="utf-8")

# Deterministic floor-hold turn: no LLM, but persist_turn_transaction is
# called with the conv_id the handler resolved — our observation point.
FLOOR_HOLD = ("[SYSTEM: The narrator pressed and held the floor. "
              "Do not ask a question. Do not summarize.]")


class _ConvRecorder:
    """Swap chat_ws.persist_turn_transaction for a recorder."""

    def __init__(self):
        self.conv_ids = []

    def __enter__(self):
        self._orig = _chat_ws.persist_turn_transaction

        def _record(**kw):
            self.conv_ids.append(kw.get("conv_id"))
        _chat_ws.persist_turn_transaction = _record
        return self

    def __exit__(self, *exc):
        _chat_ws.persist_turn_transaction = self._orig
        return False


def _idless_start_turn(message: str, person_id: str):
    # Deliberately NO session_id and NO conv_id keys.
    return {"type": "start_turn", "message": message,
            "turn_mode": "interview",
            "params": {"person_id": person_id}}


class DistinctIdlessSocketsTest(_HarnessCase):
    def test_two_idless_sockets_get_distinct_ws_prefixed_ids(self):
        with ChatWsHarness() as h:
            with _ConvRecorder() as rec:
                # Socket 1 and socket 2: separate ws_chat invocations.
                h.run([_idless_start_turn(FLOOR_HOLD, h.person_id),
                       ("wait_done", 1)])
                h.run([_idless_start_turn(FLOOR_HOLD, h.person_id),
                       ("wait_done", 1)])
            self.assertEqual(len(rec.conv_ids), 2, rec.conv_ids)
            conv1, conv2 = rec.conv_ids
            self.assertTrue(conv1.startswith("ws_"), conv1)
            self.assertTrue(conv2.startswith("ws_"), conv2)
            self.assertNotEqual(conv1, conv2,
                                "two ID-less sockets shared a session — "
                                "history/softened/segment-flag/bank rows "
                                "would bleed across narrators")
            self.assertNotIn("default", (conv1, conv2))

    def test_same_socket_reuses_its_own_minted_id(self):
        # Within ONE socket, consecutive ID-less turns stay in the same
        # (socket-scoped) conversation — continuity is preserved.
        with ChatWsHarness() as h:
            with _ConvRecorder() as rec:
                h.run([_idless_start_turn(FLOOR_HOLD, h.person_id),
                       ("wait_done", 1),
                       _idless_start_turn(FLOOR_HOLD, h.person_id),
                       ("wait_done", 2)])
            self.assertEqual(len(rec.conv_ids), 2)
            self.assertEqual(rec.conv_ids[0], rec.conv_ids[1])


class SuppliedIdsStillHonoredTest(_HarnessCase):
    def test_supplied_session_id_used_verbatim(self):
        with ChatWsHarness() as h:
            with _ConvRecorder() as rec:
                h.run([{"type": "start_turn",
                        "session_id": "operator-supplied-conv",
                        "message": FLOOR_HOLD, "turn_mode": "interview",
                        "params": {"person_id": h.person_id}},
                       ("wait_done", 1)])
            self.assertEqual(rec.conv_ids, ["operator-supplied-conv"])

    def test_supplied_conv_id_key_also_honored(self):
        with ChatWsHarness() as h:
            with _ConvRecorder() as rec:
                h.run([{"type": "start_turn",
                        "conv_id": "legacy-conv-key",
                        "message": FLOOR_HOLD, "turn_mode": "interview",
                        "params": {"person_id": h.person_id}},
                       ("wait_done", 1)])
            self.assertEqual(rec.conv_ids, ["legacy-conv-key"])


class SessionVerificationSurfacesSocketIdTest(_HarnessCase):
    def test_session_verified_carries_the_minted_socket_conv_id(self):
        with ChatWsHarness() as h:
            with _ConvRecorder() as rec:
                ws = h.run([
                    {"type": "sync_session", "person_id": h.person_id},
                    _idless_start_turn(FLOOR_HOLD, h.person_id),
                    ("wait_done", 1),
                ])
            verified = [m for m in ws.sent
                        if m.get("type") == "session_verified"]
            self.assertEqual(len(verified), 1)
            socket_id = verified[0].get("socket_conv_id")
            self.assertTrue(socket_id and socket_id.startswith("ws_"))
            # The ID-less turn used exactly the advertised socket id, so
            # a client can adopt it and re-supply it later.
            self.assertEqual(rec.conv_ids, [socket_id])


class NoDefaultFallbackSourceScanTest(unittest.TestCase):
    def test_no_executable_or_default_session_fallback_remains(self):
        self.assertNotIn(
            'or "default"', _CHAT_WS_SRC,
            "the shared-'default' session fallback is back in the "
            "start-turn path")
        self.assertNotIn("or 'default'", _CHAT_WS_SRC)

    def test_socket_conv_id_is_minted_per_connection(self):
        self.assertIn('socket_conv_id = f"ws_{uuid.uuid4()}"',
                      _CHAT_WS_SRC)

    def test_idless_assignment_is_operator_visible(self):
        self.assertIn("[chat_ws][session-identity]", _CHAT_WS_SRC)


if __name__ == "__main__":
    unittest.main(verbosity=2)
