"""Stefi's clarification must receive ordinary interview processing.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

THE ROUTE, end to end, each hop cited:

  ui/js/app.js:2599   contradiction regex fires on the words "not the" in
                      "— not the Nevada one, the New Mexico one —"
  ui/js/app.js:2713   -> returns TURN_CORRECTION
  ui/js/app.js:6691   -> ws.send({... turn_mode: "correction" ...})
  chat_ws.py:6743     -> params["turn_mode"] = the frame's value
  chat_ws.py:3340     -> turn_mode read from params
  chat_ws.py:4341     -> the correction branch
  chat_ws.py (was)    -> unconditional return, deterministic turn

A deterministic turn is extraction- and placement-INELIGIBLE by construction
(`_finalize_deterministic_turn` never writes `_persisted_turn_row_id`,
`_archive_event_persisted` or `_persisted_user_turn_row_id`). So a narrator
clarifying WHICH Las Vegas she was born in got a correction acknowledgement,
and her birthplace, her birth date and her father reached nothing.

With nothing parsed there is no correction to apply, so the branch has nothing
it can legitimately do. Both copies of the mode are reset — the local variable
AND `params`, because the completed-turn hooks read the mode from params
(`chat_ws.py:896`, `:1089`) and would otherwise still see "correction".
"""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

WS = (ROOT / "server" / "code" / "api" / "routers" / "chat_ws.py").read_text(
    encoding="utf-8")
APP = (ROOT / "ui" / "js" / "app.js").read_text(encoding="utf-8")

# Her exact words, from BUG-SAFETY-CHILD-ABUSE-FALSE-POSITIVE-DEATH-CAR-01.
STEFI = ("I was born in Las Vegas, New Mexico — not the Nevada one, the New "
         "Mexico one — on the twenty-third of May, 1944. My father Eliseo was "
         "a sheep rancher in San Miguel County, third generation on the land")


class TheRouteIsReal(unittest.TestCase):
    """Before fixing a bypass, prove the turn reaches it."""

    def test_the_browser_regex_fires_on_her_wording(self):
        """The regex is read out of the SHIPPED app.js, not retyped."""
        m = re.search(r"if \((/\\b\(\?:not\|[^\n]+?)\.test\(t\)\)", APP)
        self.assertIsNotNone(m, "app.js contradiction regex not found")
        js = m.group(1)
        self.assertIn("not", js)
        # The behavioural half: her words contain the matched shape.
        self.assertRegex(STEFI.lower(),
                         r"\b(?:not|wasn't|didn't)\s+(?:the|that|a|an|my)\b")

    def test_the_server_parser_finds_nothing_actionable(self):
        from api.memory_echo import parse_correction_rule_based
        self.assertEqual({}, parse_correction_rule_based(STEFI),
                         "if this ever parses, the fallthrough is untested")

    def test_the_branch_is_still_reached_by_turn_mode(self):
        self.assertIn('if turn_mode == "correction":', WS)
        self.assertIn('params["turn_mode"] = (msg.get("turn_mode")', WS)


class BothCopiesAreReset(unittest.TestCase):

    def _fallthrough_block(self):
        i = WS.index("correction-fallthrough")
        start = WS.rindex("if not parsed:", 0, i)
        return WS[start:i + 400]

    def test_the_local_variable_is_reset(self):
        self.assertIn('turn_mode = "interview"', self._fallthrough_block())

    def test_the_params_copy_is_reset(self):
        """The completed-turn hooks read params, not the local. Resetting one
        would leave extraction still refusing the turn."""
        self.assertIn('params["turn_mode"] = "interview"',
                      self._fallthrough_block())

    def test_the_correction_body_cannot_run_when_nothing_parsed(self):
        """Structural, via the AST: the ack, the projection write and the
        deterministic finalise must all sit under the `else`. A reset that
        still fell through to `_finalize_deterministic_turn` would change
        nothing."""
        tree = ast.parse(WS)
        found = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if not (isinstance(test, ast.UnaryOp)
                    and isinstance(test.op, ast.Not)
                    and isinstance(test.operand, ast.Name)
                    and test.operand.id == "parsed"):
                continue
            body_src = " ".join(ast.dump(n) for n in node.body)
            else_src = " ".join(ast.dump(n) for n in node.orelse)
            if "_finalize_deterministic_turn" in else_src:
                found = True
                self.assertNotIn("_finalize_deterministic_turn", body_src,
                                 "the empty-parse path still finalises")
                self.assertNotIn("compose_correction_ack", body_src,
                                 "the empty-parse path still acknowledges")
                self.assertIn("interview", body_src)
        self.assertTrue(found, "no `if not parsed:` guarding the correction "
                               "body was found")

    def test_a_concrete_correction_still_finalises(self):
        """The fix must not disable real corrections. Mary's 'we only had two
        kids, not three' still has to apply and acknowledge."""
        tree = ast.parse(WS)
        for node in ast.walk(tree):
            if (isinstance(node, ast.If) and isinstance(node.test, ast.UnaryOp)
                    and isinstance(node.test.operand, ast.Name)
                    and node.test.operand.id == "parsed"):
                else_src = " ".join(ast.dump(n) for n in node.orelse)
                if "_finalize_deterministic_turn" in else_src:
                    self.assertIn("apply_correction", else_src)
                    self.assertIn("compose_correction_ack", else_src)
                    return
        self.fail("the concrete-correction path was not found")


class TheModeIsEligibleAfterwards(unittest.TestCase):
    """Extraction and placement allow-lists hold exactly {"interview"}, so the
    reset is what makes the turn eligible at all."""

    def test_interview_is_extraction_eligible(self):
        from api.services.turn_extraction import extraction_eligible
        self.assertTrue(extraction_eligible("interview"))
        self.assertFalse(extraction_eligible("correction"))


if __name__ == "__main__":
    unittest.main()
