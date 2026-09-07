"""Block C — every completed turn closes by its actual retention outcome.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Block C.

WHAT THIS BLOCK IS NOT. It is NOT "the browser path has no trace
closer". That claim was carried forward from the frozen Walt/John tree
and asserted here without re-measuring. **Measured 2026-09-07 against
the two live Guard Lab turns**: both reached
`_complete_claim -> _finalize_extraction_trace -> attach -> close`,
both have `swept` ABSENT, both have ledger rows `turnrow:2259` /
`turnrow:2261` with `outcome=succeeded`, and the trace file was written
at 19:47:48Z for a turn that ended 19:47:39Z — a sweep could not have
fired before 19:50:39Z. **The normal funnel already works and is not
touched here.**

WHAT WAS ACTUALLY BROKEN. `_run_completed_turn_extraction` runs AFTER
the response is parked, and had five pre-schedule early returns —
`chat_ws.py:1073`+ — none of which touched the trace at all. Every one
left a parked record waiting the full 180 seconds for `_sweep()`, which
exists for abnormal abandonment and not as the way understood branches
finish.

THE INVARIANT. After an ordinary generated response is parked, either
ownership passes to `schedule_completed_turn_extraction` — whose
completion funnel closes it — or the code terminalizes the extraction
stage and closes it before returning. **There is no third legal state.**

`AnEarlyReturnCannotEscape` walks the function's AST. A sixth early
return added six months from now fails there until its disposition is
declared, rather than quietly recreating the problem because nobody
wrote a test for it.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server" / "code"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATA_DIR", "/tmp/_trace_lifecycle")

from api.services import lori_response_trace as rt      # noqa: E402


class _TracingOn(unittest.TestCase):
    """Tracing is OPT-IN, and correctly so.

    `begin()` returns None unless `HORNELORE_RESPONSE_TRACE` is truthy —
    default-on would have every ordinary production turn writing an
    evidence record nobody consented to. The first version of these
    tests did not arm it and got `None` back from every `begin`, which
    is the store being right and the fixture being wrong.
    """

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

CHAT_WS = ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py"
SEAM = "_terminalize_parked_extraction"
SCHEDULER = "_schedule_extraction"


def _function(name: str) -> ast.AST:
    tree = ast.parse(CHAT_WS.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name):
            return node
    raise AssertionError(f"{name} not found in chat_ws.py")


class TheBindableTurnKey(_TracingOn):
    """The canonical key, late-bound — the evidence weakness Block C found.

    Both live traces persisted with `turn_key: ""` while their ledger
    rows carried `turnrow:2259` / `turnrow:2261`. The mechanism worked
    (park indexes aliases); the RECORD did not carry the join.
    """

    def test_an_empty_key_accepts_the_canonical_one(self):
        tid = rt.begin(narrator_id="n1", conversation_id="c1")
        self.assertEqual("", rt._traces[tid]["turn_key"])
        self.assertTrue(rt.bind_turn_key("turnrow:2259", trace_id=tid))
        self.assertEqual("turnrow:2259", rt._traces[tid]["turn_key"])

    def test_binding_the_same_key_again_is_idempotent(self):
        tid = rt.begin(narrator_id="n1")
        rt.bind_turn_key("turnrow:2259", trace_id=tid)
        self.assertTrue(rt.bind_turn_key("turnrow:2259", trace_id=tid))
        self.assertEqual("turnrow:2259", rt._traces[tid]["turn_key"])
        self.assertFalse(rt._traces[tid].get("instrumentation_failed"))

    def test_a_CONFLICTING_key_is_refused_and_recorded(self):
        """A silent overwrite would let one trace claim two committed
        turns — a join that is confidently wrong rather than absent."""
        tid = rt.begin(narrator_id="n1")
        rt.bind_turn_key("turnrow:2259", trace_id=tid)
        self.assertFalse(rt.bind_turn_key("turnrow:9999", trace_id=tid))
        rec = rt._traces[tid]
        self.assertEqual("turnrow:2259", rec["turn_key"],
                         "the first binding must survive")
        self.assertTrue(rec.get("instrumentation_failed"))
        conflict = rec["context"][rt.BIND_CONFLICT]
        self.assertEqual("turnrow:2259", conflict["existing"])
        self.assertEqual("turnrow:9999", conflict["offered"])

    def test_an_empty_offer_binds_nothing(self):
        tid = rt.begin(narrator_id="n1")
        for value in ("", "   ", None):
            self.assertFalse(rt.bind_turn_key(value, trace_id=tid))
        self.assertEqual("", rt._traces[tid]["turn_key"])

    def test_a_parked_trace_can_still_be_bound(self):
        tid = rt.begin(narrator_id="n1")
        rt.seal(delivered="hi", trace_id=tid)
        rt.park(keys=["2259"], trace_id=tid)
        self.assertTrue(rt.bind_turn_key("turnrow:2259", trace_id=tid))
        self.assertEqual("turnrow:2259", rt._parked[tid]["turn_key"])


class TheChatWsSiteBindsTheCanonicalKey(unittest.TestCase):
    """And it derives it from the committed row, never the client id."""

    def test_the_bind_uses_the_canonical_db_key_builder(self):
        src = CHAT_WS.read_text(encoding="utf-8", errors="replace")
        idx = src.index("_rt.bind_turn_key(")
        window = src[max(0, idx - 900):idx]
        self.assertIn("turn_extraction_key_for_row", window,
                      "the canonical key must come from the DB builder "
                      "that the ledger itself uses")

    def test_the_bound_VALUE_is_derived_from_the_committed_row(self):
        """FOLLOW THE VALUE, not the call.

        The first version of this read the `bind_turn_key(...)` call
        segment and asserted it contained no `turn_id`. It did not — the
        call passes a local — so swapping the LOCAL's derivation to the
        browser's `turn_id` two lines above sailed straight through. A
        mutation caught that, and the test now resolves the name to its
        assignment and requires the canonical DB builder.

        `turn_id` is a client identifier. Substituting it would make the
        trace/ledger join look right and be wrong, which is worse than
        the empty field this block set out to fix.
        """
        node = _function("_generate_and_stream_inner")
        binds = [n for n in ast.walk(node)
                 if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)
                 and n.func.attr == "bind_turn_key"]
        self.assertTrue(binds, "nothing binds a canonical turn key")

        for call in binds:
            arg = call.args[0] if call.args else None
            self.assertIsInstance(
                arg, ast.Name,
                "the bound value should be a local resolved below")
            # Every assignment to that name inside this function.
            sources = []
            for assign in ast.walk(node):
                if not isinstance(assign, ast.Assign):
                    continue
                names = [t.id for t in assign.targets
                         if isinstance(t, ast.Name)]
                if arg.id in names:
                    sources.append(assign.value)
            self.assertTrue(sources, f"{arg.id} is never assigned")
            for value in sources:
                self.assertIsInstance(
                    value, ast.Call,
                    f"{arg.id} must come from the canonical key builder")
                fn = value.func
                fname = (fn.id if isinstance(fn, ast.Name)
                         else getattr(fn, "attr", ""))
                self.assertIn(
                    "key_of", fname.lower() + "|" + fname.lower(),
                    f"{arg.id} is assigned from {fname!r}, not the "
                    f"canonical `turn_extraction_key_for_row` alias")


class AnEarlyReturnCannotEscape(unittest.TestCase):
    """THE STRUCTURAL GUARD, and the reason this block cannot regress.

    Five hand-written branch tests would pass while a SIXTH early
    return, added later, silently reintroduced the parked-until-swept
    state. This walks the AST instead: every `return` that executes
    before the scheduler takes ownership must be preceded by the
    terminalization seam in the same branch.
    """

    def _pre_schedule_returns(self):
        node = _function("_run_completed_turn_extraction")
        src = CHAT_WS.read_text(encoding="utf-8", errors="replace")

        schedule_line = None
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == SCHEDULER):
                schedule_line = call.lineno
                break
        self.assertIsNotNone(
            schedule_line,
            f"{SCHEDULER} is not called — this guard has lost its subject")

        out = []
        for ret in ast.walk(node):
            if isinstance(ret, ast.Return) and ret.lineno < schedule_line:
                out.append((ret.lineno, src.splitlines()[ret.lineno - 1].strip()))
        return node, src, schedule_line, out

    def test_there_are_pre_schedule_returns_to_guard(self):
        """Non-vacuity. If the function stops having early returns this
        passes for the wrong reason."""
        _node, _src, _line, returns = self._pre_schedule_returns()
        self.assertGreaterEqual(len(returns), 5, returns)

    def test_every_pre_schedule_return_passes_through_the_seam(self):
        node, src, schedule_line, returns = self._pre_schedule_returns()

        # Collect the line of every seam call, then require that each
        # early return has one immediately above it inside its own
        # branch. Proximity is checked against the enclosing `if` body
        # rather than by line distance, so reformatting cannot fool it.
        unguarded = []
        for stmt in ast.walk(node):
            body = getattr(stmt, "body", None)
            if not isinstance(body, list):
                continue
            for i, child in enumerate(body):
                if not isinstance(child, ast.Return):
                    continue
                if child.lineno >= schedule_line:
                    continue
                guarded = any(
                    isinstance(prev, ast.Expr)
                    and isinstance(prev.value, ast.Call)
                    and isinstance(prev.value.func, ast.Name)
                    and prev.value.func.id == SEAM
                    for prev in body[:i])
                if not guarded:
                    unguarded.append(
                        f"line {child.lineno}: "
                        f"{src.splitlines()[child.lineno - 1].strip()}")
        self.assertEqual(
            unguarded, [],
            "these returns leave the response trace PARKED until the "
            "180-second sweep. Each needs a truthful extraction "
            "disposition through " + SEAM + ":\n  " + "\n  ".join(unguarded))

    def test_the_seam_attaches_AND_closes(self):
        """Attaching without closing still waits for the sweep."""
        node = _function(SEAM)
        called = {n.func.attr for n in ast.walk(node)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)}
        self.assertIn("attach", called)
        self.assertIn("close", called)

    def test_no_second_closer_was_added_to_the_main_path(self):
        """The normal funnel already closes correctly — measured live.

        A second `close()` on the response path could fire BEFORE
        retention attaches, converting real unmeasured work into
        apparently finished evidence.
        """
        node = _function("_generate_and_stream_inner")
        closes = [n for n in ast.walk(node)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "close"
                  and isinstance(n.func.value, ast.Name)
                  and n.func.value.id == "_rt"]
        self.assertEqual([], closes,
                         "the response path must PARK and let the "
                         "extraction funnel close")


class TheTerminalVocabularyIsUsedTruthfully(unittest.TestCase):
    """`measured_absent` means WE LOOKED. None of these looked."""

    def test_no_early_return_claims_measured_absent(self):
        node = _function("_run_completed_turn_extraction")
        src = CHAT_WS.read_text(encoding="utf-8", errors="replace")
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == SEAM):
                segment = ast.get_source_segment(src, call) or ""
                self.assertNotIn(
                    "MEASURED_ABSENT", segment,
                    "nothing was queried on this path, so absence "
                    "cannot be reported")

    def test_each_classification_is_from_the_declared_vocabulary(self):
        node = _function("_run_completed_turn_extraction")
        src = CHAT_WS.read_text(encoding="utf-8", errors="replace")
        seen = []
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == SEAM):
                segment = ast.get_source_segment(src, call) or ""
                for name in ("RESULT_NOT_APPLICABLE", "RESULT_NOT_MEASURED",
                             "RESULT_MEASUREMENT_FAILED"):
                    if name in segment:
                        seen.append(name)
        self.assertGreaterEqual(len(seen), 5, seen)
        # All three classes are used — otherwise one of the branches is
        # being described with the wrong word.
        self.assertEqual(
            {"RESULT_NOT_APPLICABLE", "RESULT_NOT_MEASURED",
             "RESULT_MEASUREMENT_FAILED"}, set(seen))

    def test_legacy_ownership_is_not_measured_and_names_the_owner(self):
        src = CHAT_WS.read_text(encoding="utf-8", errors="replace")
        idx = src.index("legacy_client_owns_extraction")
        window = src[max(0, idx - 500):idx + 200]
        self.assertIn("RESULT_NOT_MEASURED", window)
        self.assertNotIn("RESULT_MEASURED_ABSENT", window)


class ParkAndCloseBehaveAsTheLifecycleAssumes(_TracingOn):
    """The store's own half, exercised rather than asserted."""

    def _parked_turn(self, key="turnrow:2259"):
        tid = rt.begin(narrator_id="n1", conversation_id="c1")
        rt.bind_turn_key(key, trace_id=tid)
        rt.seal(delivered="hi", persisted="hi", trace_id=tid)
        rt.park(keys=["2259", key], trace_id=tid)
        return tid

    def test_attach_then_close_removes_it_from_parked_state(self):
        tid = self._parked_turn()
        self.assertIn(tid, rt._parked)
        self.assertTrue(rt.attach("turnrow:2259", "extraction",
                                  rt.RESULT_NOT_APPLICABLE,
                                  detail={"reason": "x"}))
        rt.close("turnrow:2259")
        self.assertNotIn(tid, rt._parked)

    def test_a_closed_trace_is_not_marked_swept(self):
        """`swept` is written ONLY by `_sweep`. Its presence is the
        difference between a record that closed and one that timed out."""
        written = []
        original = rt._write
        rt._write = lambda rec: written.append(rec)
        try:
            self._parked_turn()
            rt.attach("turnrow:2259", "extraction", rt.RESULT_NOT_APPLICABLE)
            rt.close("turnrow:2259")
        finally:
            rt._write = original
        self.assertEqual(1, len(written))
        self.assertNotIn("swept", written[0])
        self.assertEqual("turnrow:2259", written[0]["turn_key"])
        self.assertEqual(rt.RESULT_NOT_APPLICABLE,
                         written[0]["storage"]["extraction"]["result"])

    def test_the_sweep_still_rescues_a_genuinely_abandoned_trace(self):
        """Recovery is retained. It is simply not how normal branches
        finish any more."""
        written = []
        original = rt._write
        rt._write = lambda rec: written.append(rec)
        try:
            tid = self._parked_turn()
            rt._parked[tid]["parked_at"] = 0.0        # long abandoned
            rt._sweep()
        finally:
            rt._write = original
        self.assertEqual(1, len(written))
        self.assertTrue(written[0]["swept"])

    def test_an_unattached_close_still_writes_the_record(self):
        """Evidence is never dropped, even with nothing attached."""
        written = []
        original = rt._write
        rt._write = lambda rec: written.append(rec)
        try:
            self._parked_turn()
            rt.close("turnrow:2259")
        finally:
            rt._write = original
        self.assertEqual(1, len(written))
        self.assertNotIn("swept", written[0])


if __name__ == "__main__":
    unittest.main()
