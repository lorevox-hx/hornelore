"""A guard that ran and declined is evidence. Record it.

THE DEFECT
==========
`chat_ws.py` emitted one trace stage per communication-control authority
— selected, eligible, fired, result, before/after — from inside
`if _cc_result.changed:`.

So a turn that comm_control did not mutate recorded NO authorities at
all. The paired transcript could truthfully say the delivered text
equals the generated text, and show an empty authority table beside it.
Those are different claims. An empty table reads as "no guard ran"; the
truth was "several ran, and none of them changed anything" — which is
the finding the instrument was built to surface.

Measured on the ZZ captures of 2026-09-21:

    BEFORE turn 1  UNCHANGED  0 authority rows
    BEFORE turn 3  CHANGED   10 authority rows
    AFTER  turn 1  CHANGED    0 authority rows   <- changed by
                                                    era_fragment_repair,
                                                    which is not
                                                    comm_control

That last one is the proof the gate was on `_cc_result.changed` rather
than on change at all.

It also contradicted the trace module's own contract, which this suite
now holds the call site to:

    `fired=False` still records the stage — a layer that ran and
    declined to change anything is evidence, and its absence from the
    trace would be indistinguishable from the layer not existing.

WHAT THIS FILE PINS
===================
1. The per-authority loop is NOT inside the `changed` branch.
2. Observation does not touch the delivered text.
3. `authority_records` really are populated on an unchanged reply, so
   moving the emit has something to emit.
4. The parent `comm_control` span still runs after the possible
   `final_text` assignment — it derives `fired` by comparison, so
   hoisting it too would record every changed turn as unchanged and
   swap one false negative for another.

WHY SOURCE-LEVEL ASSERTIONS. `chat_ws` opens a WebSocket, loads a model
and imports torch; the placement of an observation call is a property of
the code, and reading the code is the honest way to assert it. The
behavioural half — that an unchanged reply has real authority records —
runs against the shipping function.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHAT_WS = REPO / "server" / "code" / "api" / "routers" / "chat_ws.py"

import sys
sys.path.insert(0, str(REPO / "server" / "code"))
from api.services.lori_communication_control import (  # noqa: E402
    enforce_lori_communication_control as enforce,
)


def _block_of(src_lines, needle):
    """(index, indent) of the first line containing `needle`."""
    for i, line in enumerate(src_lines):
        if needle in line:
            return i, len(line) - len(line.lstrip())
    raise AssertionError("not found in chat_ws.py: %r" % needle)


def _enclosing_conditions(src_lines, index):
    """Every `if`/`for`/`try` that encloses `index`, outermost last."""
    out = []
    cur = len(src_lines[index]) - len(src_lines[index].lstrip())
    for j in range(index, -1, -1):
        line = src_lines[j]
        if not line.strip():
            continue
        k = len(line) - len(line.lstrip())
        if k < cur and line.strip().startswith(
                ("if ", "elif ", "else", "try", "with ", "for ", "while ",
                 "def ", "async def")):
            out.append(line.strip())
            cur = k
            if k == 0:
                break
    return out


class TheEmitIsOutsideTheChangedBranch(unittest.TestCase):

    def setUp(self):
        self.lines = CHAT_WS.read_text(encoding="utf-8").split("\n")

    def test_the_per_authority_loop_is_not_gated_on_changed(self):
        i, _ = _block_of(self.lines, 'for _ar in getattr(_cc_result, "authority_records"')
        for cond in _enclosing_conditions(self.lines, i):
            with self.subTest(condition=cond):
                self.assertNotIn("_cc_result.changed", cond,
                                 "the authority emit is gated on the "
                                 "combined result again")

    def test_the_loop_runs_only_when_comm_control_ran(self):
        """Unconditional within its lane, not unconditional everywhere.

        There is nothing to record when the service never ran, and a row
        emitted then would be its own false claim.
        """
        i, _ = _block_of(self.lines, 'for _ar in getattr(_cc_result, "authority_records"')
        conds = " | ".join(_enclosing_conditions(self.lines, i))
        self.assertIn("_cc_enabled", conds)

    def test_observation_does_not_touch_the_delivered_text(self):
        """The loop body may read `_ar`; it may not assign final_text."""
        i, indent = _block_of(self.lines, 'for _ar in getattr(_cc_result, "authority_records"')
        body = []
        for line in self.lines[i + 1:]:
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                break
            body.append(line)
        joined = "\n".join(body)
        self.assertIn("_rt.stage(", joined, "loop body not found")
        self.assertNotIn("final_text =", joined)
        self.assertNotIn("_cc_result.final_text", joined)

    def test_the_parent_span_still_follows_the_assignment(self):
        """`_rt_ck` compares against the running text, so order matters."""
        src = "\n".join(self.lines)
        assign = src.index("final_text = _cc_result.final_text")
        parent = src.index('_rt_ck("comm_control"')
        self.assertLess(assign, parent,
                        "_rt_ck('comm_control') hoisted above the "
                        "final_text assignment; every changed turn would "
                        "record as unchanged")

    def test_the_parent_span_is_also_ungated(self):
        i, _ = _block_of(self.lines, '_rt_ck("comm_control"')
        for cond in _enclosing_conditions(self.lines, i):
            with self.subTest(condition=cond):
                self.assertNotIn("_cc_result.changed", cond)


class AnUnchangedReplyHasRealAuthorityRecords(unittest.TestCase):
    """Moving the emit is worthless if there is nothing to emit."""

    # Fictional. Atomic, within the word cap, grounded in the narrator's
    # own nouns — nothing for comm_control to correct.
    NARRATOR = "We kept chickens behind the house on Pellard Street."
    REPLY = "Chickens behind the house. What do you remember about them?"

    def setUp(self):
        self.r = enforce(self.REPLY, self.NARRATOR,
                         session_style="oral_history")

    def test_the_reply_really_is_unchanged(self):
        self.assertFalse(self.r.changed)
        self.assertEqual(self.r.final_text, self.REPLY)

    def test_authority_records_are_present_anyway(self):
        self.assertTrue(self.r.authority_records,
                        "an unchanged turn produced no authority records "
                        "at all — the emit would have nothing to write")

    def test_each_record_carries_the_full_state(self):
        for rec in self.r.authority_records:
            with self.subTest(authority=rec.get("id")):
                for key in ("id", "name", "selected", "eligible", "fired"):
                    self.assertIn(key, rec)

    def test_fired_and_changed_are_separable(self):
        """A validator that ran and reported is not a rewriter.

        On this input every authority declines, so `fired` must be False
        throughout while the records still exist — the exact state the
        old gate made invisible.
        """
        self.assertTrue(all(not rec.get("fired")
                            for rec in self.r.authority_records))

    def test_delivered_text_is_byte_identical_to_the_generated_text(self):
        """The guarantee the move must not break.

        `tests/test_lori_response_trace.py` asserts delivered text is
        byte-identical with tracing on and off. This asserts the same
        thing across the observation change: enforcement is untouched,
        so an unchanged reply comes back exactly as written.
        """
        self.assertEqual(self.r.final_text, self.REPLY)
        self.assertEqual(self.r.original_text, self.REPLY)


class CollectionGuardTests(unittest.TestCase):
    """Nothing in this file may sit after `unittest.main()`."""

    def test_every_test_class_is_collected(self):
        import inspect
        mod = sys.modules[__name__]
        defined = {n for n, o in inspect.getmembers(mod, inspect.isclass)
                   if issubclass(o, unittest.TestCase)
                   and o.__module__ == __name__}
        loaded = unittest.defaultTestLoader.loadTestsFromModule(mod)
        seen = set()

        def walk(suite):
            for t in suite:
                if isinstance(t, unittest.TestSuite):
                    walk(t)
                else:
                    seen.add(type(t).__name__)
        walk(loaded)
        self.assertEqual(defined - seen, set())

    def test_nothing_follows_unittest_main(self):
        src = Path(__file__).read_text(encoding="utf-8")
        tail = src[src.rindex("unittest.main("):]
        self.assertNotIn("\nclass ", tail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
