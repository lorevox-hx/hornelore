"""Phase 6 baseline integrity — the ten-turn set is MEASURED, not assumed.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_phase6_baseline_turnset

WHAT THESE PIN
==============

The Phase 6 capture claims "this report is the intended ten-turn
baseline". Before this suite, that claim rested on the runbook: run the
turns correctly and the report is correct. An interrupted or retried
session would leave 11 or 15 traced turns behind, and the renderer would
have drawn every one of them into a report indistinguishable from a
clean run — the contamination invisible exactly when it mattered.

`_sequence_problems` turns that into a refusal, and these tests fail if
any arm of it stops refusing.

THE FIXTURE DOES NOT SUPPLY THE PROPERTY BEING PROVEN
=====================================================

`_narrator_input` claims to read where the runtime records the narrator's
words. A hand-built `{"context": {"narrator_input": ...}}` would prove
only that this file and that reader agree with each other.

So `_traced()` below builds its records by calling the SHIPPED trace
module — `lori_response_trace.begin()` then `note("narrator_input", ...)`,
which is the same call `chat_ws.py:97` makes — and reads the record the
store actually produced. If `note` ever stops writing into `context`, or
the key is renamed, these tests fail at the fixture with the real shape
in the message, rather than passing against a shape nothing produces.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server" / "code"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from api.services import lori_response_trace as rt        # noqa: E402
import phase6_conversation_capture as cap                 # noqa: E402


class _TracingOn(unittest.TestCase):
    """Tracing is opt-in; an unarmed fixture gets `None` from `begin`."""

    def setUp(self):
        self._prev = os.environ.get("HORNELORE_RESPONSE_TRACE")
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        rt._traces.clear()
        rt._parked.clear()
        rt._parked_keys.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        if self._prev is None:
            os.environ.pop("HORNELORE_RESPONSE_TRACE", None)
        else:
            os.environ["HORNELORE_RESPONSE_TRACE"] = self._prev
        rt._traces.clear()
        rt._parked.clear()
        rt._parked_keys.clear()

    def _traced(self, texts):
        """Records built by the SHIPPED store. See the module docstring."""
        records = []
        for text in texts:
            trace_id = rt.begin(narrator_id="ada", conversation_id="c1")
            self.assertIsNotNone(
                trace_id, "begin() returned None — tracing is not armed, "
                          "so this fixture would prove nothing")
            rt.note("narrator_input", text, trace_id=trace_id)
            records.append(dict(rt._traces[trace_id]))
        return records


class TurnSetFile(unittest.TestCase):
    """The authoritative list, and the scoring split Chris asked for."""

    def setUp(self):
        self.data = json.loads(cap.TURN_SET.read_text(encoding="utf-8"))
        self.turns = self.data["turns"]

    def test_the_set_is_exactly_ten_turns(self):
        self.assertEqual(len(self.turns), 10)

    def test_indexes_are_one_through_ten_in_order(self):
        self.assertEqual([t["index"] for t in self.turns],
                         list(range(1, 11)))

    def test_exactly_one_turn_is_the_deterministic_correction(self):
        corrections = [t for t in self.turns
                       if t["expected_route"] == "correction"]
        self.assertEqual(
            [t["index"] for t in corrections], [6],
            "the deliberate correction is turn 6 and nothing else routes "
            "deterministically")

    def test_the_correction_turn_is_excluded_from_the_aggregate(self):
        """One deterministic response must not enter a model-quality mean.

        Turn 6 never reaches the model, so it cannot be evidence about
        what the model does. It stays in the report answering its own
        question.
        """
        by_index = {t["index"]: t for t in self.turns}
        self.assertFalse(by_index[6]["in_quality_aggregate"])
        aggregate = [t["index"] for t in self.turns
                     if t["in_quality_aggregate"]]
        self.assertEqual(aggregate, [1, 2, 3, 4, 5, 7, 8, 9, 10])

    def test_every_turn_carries_a_category_and_nonempty_text(self):
        for turn in self.turns:
            self.assertTrue(str(turn.get("category") or "").strip())
            self.assertTrue(str(turn.get("text") or "").strip())

    def test_no_turn_text_is_repeated(self):
        texts = [t["text"] for t in self.turns]
        self.assertEqual(len(set(texts)), len(texts))


class SequenceEnforcement(_TracingOn):
    """Every arm of the refusal, driven through the shipped trace store."""

    def setUp(self):
        super().setUp()
        self.turns = json.loads(
            cap.TURN_SET.read_text(encoding="utf-8"))["turns"]
        self.texts = [t["text"] for t in self.turns]

    def test_the_intended_run_is_accepted(self):
        problems = cap._sequence_problems(self._traced(self.texts),
                                          self.turns)
        self.assertEqual(problems, [], f"a clean run was refused: {problems}")

    def test_a_short_run_is_refused(self):
        problems = cap._sequence_problems(self._traced(self.texts[:9]),
                                          self.turns)
        self.assertTrue(any("found 9" in p for p in problems), problems)

    def test_an_extra_turn_is_refused(self):
        extra = self.texts + ["And that's about all I remember today."]
        problems = cap._sequence_problems(self._traced(extra), self.turns)
        self.assertTrue(any("found 11" in p for p in problems), problems)

    def test_a_retried_turn_is_refused_as_contamination(self):
        """The failure this exists for: a resend leaves both attempts."""
        retried = self.texts[:3] + [self.texts[2]] + self.texts[3:]
        problems = cap._sequence_problems(self._traced(retried), self.turns)
        self.assertTrue(any("sent 2 times" in p for p in problems), problems)

    def test_reordering_is_refused_and_named_as_reordering(self):
        swapped = list(self.texts)
        swapped[3], swapped[6] = swapped[6], swapped[3]
        problems = cap._sequence_problems(self._traced(swapped), self.turns)
        self.assertTrue(any("OUT OF ORDER" in p for p in problems), problems)

    def test_a_foreign_turn_is_refused(self):
        foreign = list(self.texts)
        foreign[4] = "Tell me about the weather."
        problems = cap._sequence_problems(self._traced(foreign), self.turns)
        self.assertTrue(
            any("not a baseline turn" in p for p in problems), problems)

    def test_whitespace_around_a_turn_does_not_refuse(self):
        """A trailing newline from the composer is not contamination."""
        padded = ["  " + t + "\n" for t in self.texts]
        self.assertEqual(
            cap._sequence_problems(self._traced(padded), self.turns), [])


class PreflightAgreesWithTheSameFile(unittest.TestCase):
    """The JS consumer is EXECUTED, not grepped.

    A source-string assertion that the preflight mentions the JSON path
    is not evidence that it reads it — the doctrine file is explicit that
    source-string assertions are never acceptance evidence by themselves.
    Running it proves the three consumers share one list.
    """

    def test_the_shipped_router_preflight_passes_on_this_set(self):
        script = REPO_ROOT / "scripts" / "ui" / "phase6_turn_route_preflight.js"
        try:
            proc = subprocess.run(["node", str(script)], cwd=str(REPO_ROOT),
                                  capture_output=True, text=True, timeout=120)
        except FileNotFoundError:
            self.skipTest("node is not available on this interpreter's host")
        self.assertEqual(
            proc.returncode, 0,
            f"the route preflight refused the committed turn set:\n"
            f"{proc.stdout}\n{proc.stderr}")
        self.assertIn("nine reach the model", proc.stdout)


if __name__ == "__main__":
    unittest.main()
