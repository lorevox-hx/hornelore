"""WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 §3.1 — COMMIT 3 tests.

Response-guard wrapper failure must FAIL CLOSED at the chat_ws call
site: when the guard layer itself raises, the raw UNGUARDED LLM text
must never reach the narrator (WS events, persistence, archive). A
deterministic fallback replaces it — the safety wording + locked
resource cards on a safety-triggered turn, the locked neutral
continuation otherwise — honoring the session language pin.

Behavior tests drive the REAL ws_chat handler via the shared
ChatWsHarness from tests/test_chat_ws_safety_precedence.py. A companion
class unit-tests the module-level fallback composer and pins the
INC-2026-07-09 boot-time-import doctrine fix for
detect_sensory_pivot_on_chain.
"""
from __future__ import annotations

import json
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
    DISTRESS,
    _HarnessCase,
)
from api import db as _db  # noqa: E402
from api.routers import chat_ws as _chat_ws  # noqa: E402
from api.services import lori_response_guards as _guards  # noqa: E402

_SAVED_SAFETY_STATE = None


def setUpModule():  # noqa: N802
    """Put safety in the state this module's assertions presume.

    2026-08-17, found by the .venv gate.
    ``test_safety_triggered_guard_failure_uses_safety_fallback`` asserted
    the SAFETY fallback and got the neutral one. That was not a product
    regression -- it reproduces identically on a clean checkout of
    ``2c3a593``, and the product was right: runtime safety is PARKED, and
    parked outranks everything, so ``scan_answer`` never runs, there is no
    safety turn, and the neutral fail-closed fallback is the correct
    answer.

    The gap was here. This module borrows ``ChatWsHarness`` and
    ``DISTRESS`` from ``test_chat_ws_safety_precedence`` but NOT its
    module fixture -- and importing a module does not run its
    ``setUpModule``. So a suite asserting safety behaviour ran in a
    deployment state where the safety feature does not exist.

    That sibling module states the rule this now follows, in its own
    words: *a suite that exists to prove the safety feature works should
    be entirely in the state where the feature exists.* The parked
    behaviour is asserted separately, by ``ParkedGuardFailureTest`` below
    and by ``tests/test_safety_parked.py``.

    Nothing about the assertion is weakened and no product code changes:
    the environment is put into the state the assertion was always
    written against.
    """
    import os
    global _SAVED_SAFETY_STATE
    _SAVED_SAFETY_STATE = os.environ.get("HORNELORE_SAFETY_STATE")
    os.environ["HORNELORE_SAFETY_STATE"] = "active"


def tearDownModule():  # noqa: N802
    import os
    if _SAVED_SAFETY_STATE is None:
        os.environ.pop("HORNELORE_SAFETY_STATE", None)
    else:
        os.environ["HORNELORE_SAFETY_STATE"] = _SAVED_SAFETY_STATE

_GUARDS_SRC = (
    _SERVER_CODE / "api" / "services" / "lori_response_guards.py"
).read_text(encoding="utf-8")
_CHAT_WS_SRC = (
    _SERVER_CODE / "api" / "routers" / "chat_ws.py"
).read_text(encoding="utf-8")

RAW_LLM = "RAW-UNGUARDED-SENTINEL the guard layer never validated this."


class _GuardCrashMixin:
    """Patch the module-scope guard binding chat_ws actually calls."""

    def _with_crashing_guards(self, harness_kwargs=None):
        h = ChatWsHarness(**(harness_kwargs or {}))

        def _boom(*a, **kw):
            raise RuntimeError("simulated guard-layer crash")

        class _Ctx:
            def __enter__(_self):
                h.__enter__()
                _self._orig = _chat_ws._APPLY_RESPONSE_GUARDS
                _chat_ws._APPLY_RESPONSE_GUARDS = _boom
                return h

            def __exit__(_self, *exc):
                _chat_ws._APPLY_RESPONSE_GUARDS = _self._orig
                return h.__exit__(*exc)

        return _Ctx()


class GuardFailureFailClosedTest(_GuardCrashMixin, _HarnessCase):
    def test_raw_llm_text_never_reaches_output_on_ordinary_turn(self):
        with self._with_crashing_guards({"llm_text": RAW_LLM}) as h:
            conv = "conv_guardfail_plain"
            ws = h.run_turn(conv,
                            "We lived on a farm outside Minot back then.")
            self.assert_no_ws_errors(ws)
            wire = json.dumps(ws.sent)
            # The raw text is nowhere on the wire — not in the token
            # delta, not in the done event.
            self.assertNotIn("RAW-UNGUARDED-SENTINEL", wire)
            done = ws.dones()[0]
            # Neutral deterministic fallback: the locked continuation.
            self.assertEqual(done.get("final_text"),
                             "Tell me more about that.")
            # Persistence also carries the fallback, never the raw text.
            turns = _db.export_turns(conv) or []
            assistant = [t.get("content") for t in turns
                         if t.get("role") == "assistant"]
            self.assertIn("Tell me more about that.", assistant)
            self.assertNotIn(RAW_LLM, assistant)

    def test_safety_triggered_guard_failure_uses_safety_fallback(self):
        with self._with_crashing_guards({"llm_text": RAW_LLM}) as h:
            conv = "conv_guardfail_safety"
            ws = h.run_turn(conv, DISTRESS)
            self.assert_no_ws_errors(ws)
            wire = json.dumps(ws.sent)
            self.assertNotIn("RAW-UNGUARDED-SENTINEL", wire)
            done = ws.dones()[0]
            final = done.get("final_text") or ""
            # Safety wording + locked 988 resource-card text for the
            # suicidal_ideation category.
            self.assertTrue(final.startswith("I hear you"), final)
            self.assertIn("988", final)
            # The rest of the safety cascade still happened.
            self.assertEqual(len(ws.events("safety_triggered")), 1)
            self.assertEqual(len(h.sensitive_flags(conv)), 1)

    def test_ordinary_failure_honors_spanish_language(self):
        with self._with_crashing_guards({"llm_text": RAW_LLM}) as h:
            ws = h.run_turn(
                "conv_guardfail_es",
                "Mi abuela vivía en una casa pequeña y hablaba conmigo "
                "cada día.")
            self.assert_no_ws_errors(ws)
            done = ws.dones()[0]
            self.assertEqual(done.get("final_text"),
                             "Cuéntame más sobre eso.")
            self.assertNotIn("RAW-UNGUARDED-SENTINEL", json.dumps(ws.sent))


class ParkedGuardFailureTest(_GuardCrashMixin, _HarnessCase):
    """The OTHER deployment state, pinned so neither can regress silently.

    Runtime safety is PARKED in this deployment. Parked outranks the
    kill-switch and every legacy env value, so a distress turn produces
    no safety scan and no safety turn. The guard wrapper must STILL fail
    closed -- the raw LLM text must not reach the narrator -- and the
    correct fallback there is the neutral continuation, because there is
    no safety turn to compose safety wording for.

    Without this, `setUpModule` above would leave the parked path
    unexercised by this module, and a future change that made the
    fallback unconditionally "safety-shaped" would pass every test here
    while contradicting the parking decision.
    """

    def test_parked_distress_turn_still_fails_closed_to_neutral(self):
        import os
        _prev = os.environ.get("HORNELORE_SAFETY_STATE")
        os.environ["HORNELORE_SAFETY_STATE"] = "parked"
        try:
            with self._with_crashing_guards({"llm_text": RAW_LLM}) as h:
                ws = h.run_turn("conv_guardfail_parked", DISTRESS)
                self.assert_no_ws_errors(ws)
                # Fail-closed is the invariant that holds in BOTH states.
                self.assertNotIn("RAW-UNGUARDED-SENTINEL", json.dumps(ws.sent))
                done = ws.dones()[0]
                self.assertEqual(done.get("final_text"),
                                 "Tell me more about that.")
                # And parking is real: no safety cascade ran.
                self.assertEqual(len(ws.events("safety_triggered")), 0)
        finally:
            if _prev is None:
                os.environ.pop("HORNELORE_SAFETY_STATE", None)
            else:
                os.environ["HORNELORE_SAFETY_STATE"] = _prev


class FallbackComposerUnitTest(unittest.TestCase):
    """The module-level helper: composed at boot, bulletproof at call."""

    def test_neutral_en_and_es_reuse_locked_wording(self):
        self.assertEqual(
            _guards.compose_guard_failure_fallback("en", False),
            "Tell me more about that.")
        self.assertEqual(
            _guards.compose_guard_failure_fallback("es", False),
            "Cuéntame más sobre eso.")

    def test_safety_fallback_includes_resource_card_wording(self):
        from api.safety import get_resources_for_category
        out = _guards.compose_guard_failure_fallback(
            "en", True, get_resources_for_category("suicidal_ideation"))
        self.assertIn("988", out)
        self.assertTrue(out.startswith("I hear you"))

    def test_safety_fallback_without_resources_is_presence_only(self):
        out = _guards.compose_guard_failure_fallback("en", True, [])
        self.assertEqual(out, "I hear you, and I'm staying right here "
                              "with you.")

    def test_malformed_resource_entries_never_raise(self):
        out = _guards.compose_guard_failure_fallback(
            "en", True, [None, 42, {"name": ""}, {"name": "X",
                                                  "description": "Y"}])
        self.assertIn("X: Y.", out)

    def test_neutral_fallback_shape_constraints(self):
        # No new fact, no sensory probe, no diagnosis, no compound
        # question, no claims about narrator content.
        out = _guards.compose_guard_failure_fallback("en", False)
        self.assertLessEqual(out.count("?"), 1)
        for banned in ("sights", "sounds", "smells", "scenery", "feel"):
            self.assertNotIn(banned, out.lower())


class BootTimeImportDoctrineTest(unittest.TestCase):
    """INC-2026-07-09: structural breakage fails at boot, not lazily."""

    def test_sensory_probe_rx_imported_at_module_scope(self):
        self.assertIn("from .factual_chain_capture import", _GUARDS_SRC)
        idx_import = _GUARDS_SRC.index("from .factual_chain_capture import")
        idx_def = _GUARDS_SRC.index("def detect_sensory_pivot_on_chain")
        self.assertLess(idx_import, idx_def,
                        "the _SENSORY_PROBE_RX import must be module-"
                        "scope, before the detector definition")

    def test_no_lazy_import_inside_the_detector(self):
        body = _GUARDS_SRC[_GUARDS_SRC.index(
            "def detect_sensory_pivot_on_chain"):]
        body = body[:body.index("\ndef ")]
        self.assertNotIn("import", body.replace(
            "imported at module scope", ""),
            "detect_sensory_pivot_on_chain must not lazily import")

    def test_detector_still_fires_and_declines_correctly(self):
        self.assertTrue(_guards.detect_sensory_pivot_on_chain(
            "What was your impression of the city's atmosphere?", True))
        self.assertFalse(_guards.detect_sensory_pivot_on_chain(
            "What was your impression of the city's atmosphere?", False))
        self.assertFalse(_guards.detect_sensory_pivot_on_chain(
            "What happened next on the route?", True))

    def test_chat_ws_imports_fallback_at_module_scope(self):
        self.assertIn("compose_guard_failure_fallback as "
                      "_COMPOSE_GUARD_FAILURE_FALLBACK", _CHAT_WS_SRC)

    def test_guard_call_site_logs_error_not_warning(self):
        marker = "[chat_ws][response-guards] wrapper raised — FAIL CLOSED,"
        self.assertIn(marker, _CHAT_WS_SRC)
        i = _CHAT_WS_SRC.index(marker)
        block = _CHAT_WS_SRC[max(0, i - 200):i + 200]
        self.assertIn("logger.error", block)
        self.assertNotIn("passing through", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
