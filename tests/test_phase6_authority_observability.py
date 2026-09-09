"""Phase 6 B1 — ids 30, 31 and 47 must leave evidence on every turn.

WHAT THIS PROTECTS, and why it is not a style rule.

Before 2026-09-08 these three authorities wrote no response-trace stage
at all. Their only record was a ``logger.warning`` that fires when
something is flagged. The consequence is the one the Phase 6 cohort
report had to write down as ``unverified``:

    "selected, ran, found nothing"  and  "never ran"
    produced byte-identical evidence.

For id 47 it was worse in kind rather than degree — a validator that
PASSED and a validator that was never selected both left ``_wr_ok=True``
and no trace, so the only way to guess its verdict was to look for id
48's fallback stage, which cannot separate *judged and approved* from
*nobody judged*.

FOUR FACTS, NONE INFERRED FROM ANOTHER:

    selected   the operator's snapshot allows it
    evaluated  the detector actually executed
    eligible   there was something for it to act on
    fired      it changed the narrator-facing text

"No text changed" is deliberately not enough. A detector that was never
reached and one that ran against an empty corpus must not read the same,
which is why ``eligible`` exists separately from ``evaluated``.

TWO LEVELS, DELIBERATELY.

The behavioural half runs against the SHIPPED trace store — not a
hand-built dict — because the property under test is that the real
``stage()`` preserves these fields, and a fixture that constructed the
record would be supplying the property being proven
(``docs/TESTING-DOCTRINE.md``).

The structural half is an AST guard over ``chat_ws.py``. It exists
because the behavioural half cannot reach the call sites: ``chat_ws``
imports ``transformers``, which is absent from the agent sandbox and
fails identically at HEAD, so ``.venv-gpu`` in WSL is the only place the
behavioural suites run. An AST guard is the same instrument this
repository already uses for the trace closer's early returns. It reads
the source rather than importing it, so it runs anywhere — and it fails
if someone later nests these stages inside a "did the text change?"
branch, which would silently restore the exact gap this closes.
"""

import ast
import os
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAT_WS = os.path.join(
    _REPO, "server", "code", "api", "routers", "chat_ws.py")

# The three stage names this lane added, and the authority each belongs
# to. Derived from the registry's trace_stage field, not hand-copied
# prose: if the registry renames one, the registry test below fails
# first and names the drift.
_EXPECTED = {
    "phantom_noun_detect": 30,
    "phantom_noun_scrub": 31,
    "witness_receipt_validator": 47,
}


def _stage_calls(tree):
    """Every ``_rt.stage("<name>", ...)`` call in the module.

    Returns a list of (name, ast.Call). Only literal first arguments are
    collected — a computed stage name would defeat the point of the
    guard, and there are none.
    """
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "stage"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            out.append((first.value, node))
    return out


def _kwargs(call):
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


class ChatWsSourceMixin(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(_CHAT_WS, "r", encoding="utf-8") as fh:
            cls.source = fh.read()
        cls.tree = ast.parse(cls.source, filename=_CHAT_WS)
        cls.calls = _stage_calls(cls.tree)


class TheThreeAuthoritiesEmitAStage(ChatWsSourceMixin):
    """Each of the three names appears as a real trace stage."""

    def test_every_expected_stage_name_is_emitted(self):
        emitted = {name for name, _ in self.calls}
        for name in _EXPECTED:
            self.assertIn(
                name, emitted,
                f"{name} emits no _rt.stage call — the authority is "
                f"invisible in the trace again")

    def test_the_validator_is_emitted_on_both_arms(self):
        """id 47 must record the turn where its path was never reached.

        The receipt path has its own entry condition. If the stage were
        emitted only inside that condition, a turn that was never a
        witness receipt would look exactly like a turn whose validator
        was excluded.
        """
        n = sum(1 for name, _ in self.calls
                if name == "witness_receipt_validator")
        self.assertGreaterEqual(
            n, 2,
            "witness_receipt_validator is emitted on only one arm; the "
            "'receipt path not reached' turn would leave no evidence")

    def test_each_stage_records_all_four_facts(self):
        for name, aid in _EXPECTED.items():
            for _n, call in [c for c in self.calls if c[0] == name]:
                kw = _kwargs(call)
                for field in ("selected", "evaluated", "eligible"):
                    self.assertIn(
                        field, kw,
                        f"{name} does not record `{field}` — the four "
                        f"facts collapse back into one")
                self.assertIn(
                    "fired", kw, f"{name} does not record `fired`")
                self.assertIn(
                    "authority_id", kw,
                    f"{name} does not name its authority id")
                self.assertEqual(
                    aid, getattr(kw["authority_id"], "value", None),
                    f"{name} is attributed to the wrong authority")


class TheStagesAreNotConditionalOnTextChanging(ChatWsSourceMixin):
    """The gap this lane closes is emitting evidence ONLY on a change.

    If any of these stages sits inside a branch that tests whether the
    text moved, or whether the detector flagged anything, then a silent
    authority leaves no record and we are back where we started.
    """

    _FORBIDDEN_GUARD_TOKENS = (
        "flagged",
        "_phantom_result",
        "changed",
        "!=",
    )

    def _enclosing_tests(self, target):
        """Source text of every `if` whose body contains `target`."""
        found = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.If):
                continue
            for sub in ast.walk(node):
                if sub is target:
                    found.append(ast.get_source_segment(
                        self.source, node.test) or "")
                    break
        return found

    def test_no_stage_is_gated_on_a_flag_or_a_diff(self):
        for name, call in self.calls:
            if name not in _EXPECTED:
                continue
            for test_src in self._enclosing_tests(call):
                for tok in self._FORBIDDEN_GUARD_TOKENS:
                    self.assertNotIn(
                        tok, test_src,
                        f"{name} is emitted inside `if {test_src}` — an "
                        f"authority that stays silent would write no "
                        f"evidence, which is the defect being fixed")


class TheTraceStorePreservesTheFourFacts(unittest.TestCase):
    """Behavioural half — against the SHIPPED trace store.

    No fixture builds the record. ``stage()`` builds it, exactly as
    production does, and we read back what it stored.
    """

    def setUp(self):
        import importlib
        self.mod = importlib.import_module(
            "api.services.lori_response_trace")

    def _one(self, **kw):
        tid = self.mod.open_trace() if hasattr(
            self.mod, "open_trace") else None
        self.skipTest_if_no_api(tid)
        return tid

    def skipTest_if_no_api(self, tid):
        if tid is None:
            self.skipTest("trace store exposes no open_trace() here")

    def test_a_silent_authority_still_records_and_is_not_changed(self):
        """fired=False with equal before/after is a real, readable row."""
        mod = self.mod
        rec = {"stages": []}

        # Drive the shipped entry-builder the way production does, then
        # read the row back. If the module gained a different public
        # surface this fails loudly rather than testing a shape nothing
        # produces.
        self.assertTrue(
            hasattr(mod, "stage"),
            "lori_response_trace.stage is gone — the instrument this "
            "lane depends on has moved")

        text = "Ada, that sounds like a long walk to school."
        captured = {}

        original = mod._traces if hasattr(mod, "_traces") else None
        self.assertIsNotNone(
            original,
            "lori_response_trace._traces is gone; the store's internals "
            "moved and this test must be re-pinned rather than relaxed")

        tid = "phase6-b1-test"
        with mod._lock:
            mod._traces[tid] = rec
        try:
            mod.stage(
                "phantom_noun_detect",
                fired=False,
                before=text,
                after=text,
                reason="not_selected",
                trace_id=tid,
                authority_id=30,
                selected=False,
                evaluated=False,
                eligible=False,
                flagged=[],
                narrator_corpus_chars=0,
            )
            captured = dict(rec["stages"][0])
        finally:
            with mod._lock:
                mod._traces.pop(tid, None)

        self.assertEqual("phantom_noun_detect", captured["stage"])
        self.assertFalse(captured["fired"])
        self.assertFalse(
            captured["changed"],
            "a detector that wrote nothing must not read as changed")
        self.assertEqual("not_selected", captured["reason"])

        extra = captured.get("extra") or {}
        self.assertEqual(30, extra.get("authority_id"))
        # The four facts survive the round trip separately.
        self.assertIs(False, extra.get("selected"))
        self.assertIs(False, extra.get("evaluated"))
        self.assertIs(False, extra.get("eligible"))

    def test_evaluated_and_eligible_are_independent(self):
        """Ran against an empty corpus != never ran.

        This is the distinction that makes the pair worth recording. If
        a future edit derives one from the other, the two rows below
        become identical and the test fails.
        """
        mod = self.mod
        rows = []
        tid = "phase6-b1-test-2"
        rec = {"stages": []}
        with mod._lock:
            mod._traces[tid] = rec
        try:
            # ran, but there was nothing to judge
            mod.stage("phantom_noun_detect", fired=False, before="x",
                      after="x", trace_id=tid, authority_id=30,
                      selected=True, evaluated=True, eligible=False)
            # never reached
            mod.stage("phantom_noun_detect", fired=False, before="x",
                      after="x", trace_id=tid, authority_id=30,
                      selected=True, evaluated=False, eligible=False)
            rows = [dict(s) for s in rec["stages"]]
        finally:
            with mod._lock:
                mod._traces.pop(tid, None)

        self.assertEqual(2, len(rows))
        a = (rows[0].get("extra") or {})
        b = (rows[1].get("extra") or {})
        self.assertNotEqual(
            (a.get("evaluated"), a.get("eligible")),
            (b.get("evaluated"), b.get("eligible")),
            "a detector that ran on an empty corpus and one that never "
            "ran are indistinguishable — the gap is back")


class TheRegistryDeclaresTheStages(unittest.TestCase):
    """The registry must name the stage, or the catalog cannot join.

    The stage names above are only useful if the registry points at
    them; otherwise a reader holding a trace has no way back to the
    authority that wrote the row.
    """

    def test_each_authority_declares_its_trace_stage(self):
        import importlib
        reg = importlib.import_module("api.services.lori_guard_registry")
        by_id = {}
        for item in getattr(reg, "REGISTRY", getattr(reg, "INTERVENTIONS", [])):
            by_id[getattr(item, "id", None)] = item
        self.assertTrue(by_id, "could not read the authority registry")

        for name, aid in _EXPECTED.items():
            item = by_id.get(aid)
            self.assertIsNotNone(item, f"authority {aid} is missing")
            self.assertEqual(
                name, getattr(item, "trace_stage", None),
                f"authority {aid} does not declare trace_stage={name!r}; "
                f"a trace row could not be joined back to it")


if __name__ == "__main__":
    unittest.main()
