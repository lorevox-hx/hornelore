"""A dropped trip_context must not classify the next answer as trip evidence.

WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 4 correction, 2026-08-18.

Phase 4 made the Travels-shelf trip-context block a CLASSIFIED SECTION so
the budget could see it. That was necessary -- concatenating it onto the
finished string meant the budget priced a system message that was not the
one sent -- but it introduced a defect on the way in.

`_TRIP_PREV_LORI[conv_id]` is what the NEXT narrator answer consults to
decide whether it is trip evidence. It was stamped `bool(_tic_block)` at
INJECTION time. That was safe while the block could never be removed. It
stopped being safe the moment `trip_context` became optional: an
over-budget turn can shed it, and the stamp would still have claimed the
turn was trip-scoped.

THE HARM IS NOT COSMETIC. Lori would never have seen the trip, the
narrator's reply would have been about something else, and it would have
been captured against a real trip anyway. Wrong evidence attached to a
real trip is worse than no evidence -- an operator reviewing that trip
has no way to tell the mis-scoped note from a true one.

The rule these tests pin:

    trip_scoped is true only if the trip context REACHED THE MODEL.

    * no section removal  -> the injected block was kept
    * section removal     -> only if `trip_context` is in kept_sections
    * budget refuses      -> no prior-Lori record is created at all
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "server" / "code"))

from api.prompt_composer import _PromptAssembly, render_sections   # noqa: E402
from api.services.prompt_budget import (                           # noqa: E402
    fit_chat_messages_with_sections,
)

_CHAT_WS = _REPO / "server" / "code" / "api" / "routers" / "chat_ws.py"
_API = _REPO / "server" / "code" / "api" / "api.py"
_SRC = _CHAT_WS.read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """Source with comment lines removed.

    The retired form is quoted in a comment explaining the fix, so a raw
    scan for it would fire on the explanation -- a mistake this
    repository has made repeatedly and does not need to make again.
    """
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))


def _count(msgs):
    return sum(len(m["content"].split()) for m in msgs)


def _assembly_with_trip(trip_text="TRIPCTX " * 40):
    asm = _PromptAssembly("system_head", "HEAD " * 40)
    asm.add("identity_facts", "FACTS " * 30, required=True)
    asm.add("memory_context", "MEM " * 30, required=False, drop_order=5)
    asm.add("trip_context", trip_text, required=False, drop_order=15)
    asm.add("pinned_facts", "PIN " * 20, required=False, drop_order=40)
    return asm


def _msgs(sections):
    return [{"role": "system", "content": render_sections(sections)},
            {"role": "user", "content": "CURRENT " * 8}]


def _trip_scope_after_budget(outcome, *, injected: bool):
    """The shipped rule, expressed once so the tests exercise one thing.

    Mirrors the three branches in `chat_ws.py` after the budget: refusal
    records nothing, no section removal keeps the injected value, and
    section removal defers to `kept_sections`.
    """
    if not outcome.fits:
        return None                       # no record is created
    scoped = injected
    if injected and outcome.dropped_sections:
        scoped = "trip_context" in outcome.kept_sections
    return {"trip_scoped": scoped,
            "prompt_kind": "trip" if scoped else None}


class TheBudgetDecidesTripScope(unittest.TestCase):
    def test_a_dropped_trip_context_is_not_trip_scoped(self):
        """The defect, stated as the test that would have caught it."""
        secs = _assembly_with_trip().sections()
        msgs = _msgs(secs)
        # Tight enough that memory_context AND trip_context must both go.
        out = fit_chat_messages_with_sections(
            msgs, limit=90, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertTrue(out.fits)
        self.assertIn("trip_context", out.dropped_sections,
                      "fixture did not exercise the case under test")
        rec = _trip_scope_after_budget(out, injected=True)
        self.assertIsNotNone(rec)
        self.assertFalse(rec["trip_scoped"],
                         "a turn Lori never saw the trip on was recorded "
                         "as trip-scoped")
        self.assertIsNone(rec["prompt_kind"])

    def test_the_dropped_section_is_absent_from_the_prompt_too(self):
        """Not merely reclassified -- actually gone from what is sent.

        Without this, a bug that reported the drop while still sending the
        text would pass the test above.
        """
        secs = _assembly_with_trip().sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs), limit=90, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertNotIn("TRIPCTX", out.messages[0]["content"])

    def test_a_kept_trip_context_stays_trip_scoped(self):
        """The other half. A rule that always answered 'not scoped' would
        pass the first test and destroy the feature."""
        secs = _assembly_with_trip().sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs), limit=10_000, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertEqual([], out.dropped_sections)
        rec = _trip_scope_after_budget(out, injected=True)
        self.assertTrue(rec["trip_scoped"])
        self.assertEqual("trip", rec["prompt_kind"])
        self.assertIn("TRIPCTX", out.messages[0]["content"])

    def test_scope_survives_a_drop_of_some_OTHER_section(self):
        """Section removal alone must not un-scope the turn -- only the
        removal of `trip_context` may."""
        secs = _assembly_with_trip().sections()
        msgs = _msgs(secs)
        # A limit that sheds memory_context (drop_order 5) but keeps the
        # trip block (15).
        out = fit_chat_messages_with_sections(
            msgs, limit=155, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertTrue(out.fits)
        self.assertEqual(["memory_context"], out.dropped_sections)
        rec = _trip_scope_after_budget(out, injected=True)
        self.assertTrue(rec["trip_scoped"])
        self.assertIn("TRIPCTX", out.messages[0]["content"])

    def test_a_refusal_creates_no_record_at_all(self):
        asm = _PromptAssembly("system_head", "HEAD " * 60)
        asm.add("identity_facts", "FACTS " * 60, required=True)
        asm.add("trip_context", "TRIPCTX " * 20, required=False, drop_order=15)
        secs = asm.sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs), limit=40, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        self.assertFalse(out.fits)
        self.assertIsNone(_trip_scope_after_budget(out, injected=True))

    def test_a_turn_with_no_trip_block_is_never_scoped(self):
        secs = _assembly_with_trip().sections()
        out = fit_chat_messages_with_sections(
            _msgs(secs), limit=10_000, count_tokens=_count,
            sections=secs, render_sections=render_sections)
        rec = _trip_scope_after_budget(out, injected=False)
        self.assertFalse(rec["trip_scoped"])


class TheShippedCodeFollowsThatRule(unittest.TestCase):
    """The helper above states the rule; these pin that chat_ws obeys it."""

    def test_the_stamp_is_not_made_at_injection_time(self):
        code = _code_only(_SRC)
        self.assertNotIn('_TRIP_PREV_LORI[conv_id] = {', code,
                         "the prior-Lori record is still built inline at "
                         "injection time")
        self.assertIn("_tic_pending", code)

    def test_the_stamp_happens_after_the_budget(self):
        code = _code_only(_SRC)
        i_budget = code.index("_budget = fit_chat_messages_with_sections(")
        i_stamp = code.index("_TRIP_PREV_LORI[conv_id] = _tic_pending")
        self.assertGreater(i_stamp, i_budget,
                           "trip scope is stamped before the budget decides")

    def test_the_stamp_consults_kept_sections(self):
        code = _code_only(_SRC)
        self.assertIn('"trip_context" in _budget.kept_sections', code)

    def test_the_refusal_path_returns_before_the_stamp(self):
        """`return` on refusal must precede the stamp, or a refused turn
        would still record a prior-Lori scope."""
        code = _code_only(_SRC)
        i_refuse = code.index('"blocked": "prompt_too_large"')
        i_stamp = code.index("_TRIP_PREV_LORI[conv_id] = _tic_pending")
        self.assertGreater(i_stamp, i_refuse)
        between = code[i_refuse:i_stamp]
        self.assertIn("return", between,
                      "the refusal path falls through to the stamp")


class SectionOnlyReductionsAreLogged(unittest.TestCase):
    """A section-only reduction used to succeed in total silence.

    Both transports tested `dropped_turns` alone, so an over-budget turn
    with no history to shed reported nothing -- the one case the new
    machinery exists to handle was the one case with no telemetry.
    """

    def test_the_websocket_logs_on_either_kind_of_reduction(self):
        code = _code_only(_SRC)
        self.assertIn("if _budget.dropped_turns or _budget.dropped_sections:",
                      code)

    def test_the_rest_paths_log_on_either_kind_of_reduction(self):
        code = _code_only(_API.read_text(encoding="utf-8"))
        self.assertIn("if outcome.dropped_turns or outcome.dropped_sections:",
                      code)

    def test_neither_transport_still_tests_dropped_turns_alone(self):
        for path in (_CHAT_WS, _API):
            with self.subTest(path=path.name):
                code = _code_only(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    [], re.findall(r"if \w+\.dropped_turns:\s*$", code, re.M),
                    "a transport still logs only on history drops")


class TheModuleStillParses(unittest.TestCase):
    def test_chat_ws_parses(self):
        ast.parse(_SRC)


if __name__ == "__main__":
    unittest.main()
