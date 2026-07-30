"""TRUTH-PIPELINE-01 Phase 1 (Gate 7) --- behavior gate for the probe.

What these tests pin, and why each one earns its place:

  - The five stage names are exactly the ones the checklist names. If a
    later session renames one, the harness evidence stops comparing to
    the record and nobody notices. Fail the build instead.

  - Default OFF. The flag is the whole safety story for a probe that
    sits inside db.py's turn commit. With the flag off, begin_turn
    returns None and mark() must be a no-op --- no allocation, no
    record, no log line.

  - mark() outside a turn is a no-op. This is not an edge case: it is
    the NORMAL path for `extract_fields_called` and
    `family_truth_written`, which the browser posts as separate HTTP
    requests. Those stages legitimately read 0 on a chat_ws turn. The
    probe has to survive that quietly rather than raise or leak into
    whatever request context happens to be running.

  - EVERY stage has a real mark() call site in the tree. This is the
    load-bearing test of the whole phase. Gate 7 exists to tell a real
    routing bug apart from a harness coverage gap, and a stage that
    reads 0 only means "did not fire" if we know it was measured. A
    stage silently losing its call site during a refactor would turn
    the evidence back into the ambiguity it was built to end.

  - ONE log line per turn. log_filter.py records that api.log had
    become roughly 95 percent polling noise. Five lines per turn would
    re-create that.

  - No narrator text anywhere in the line. CLAUDE.md:44 --- no operator
    leakage, no diagnostic surfaces. Ids and counts only.

  - The Phase 1 READING itself (added 2026-07-30, after the live
    evidence run). Two of the three zeros are correct-by-design and one
    is a real gap, and that split is the entire deliverable of Gate 7.
    A reading recorded only in prose goes stale the first time somebody
    wires family truth into the turn path. TurnPathReachabilityTest
    pins the three structural facts the reading rests on, so a later
    change to any of them fails the build and forces the doctrine
    forward instead of leaving the record quietly wrong.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services import truth_pipeline_probe as tp  # noqa: E402

_FLAG = "HORNELORE_TRUTH_PIPELINE_LOG"


class _FlagBase(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get(_FLAG)
        tp.reset_for_tests()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = self._saved
        tp.reset_for_tests()

    def _on(self):
        os.environ[_FLAG] = "1"

    def _off(self):
        os.environ.pop(_FLAG, None)


class StageNamesTest(_FlagBase):
    def test_the_five_stage_names_are_exactly_the_checklist_names(self):
        self.assertEqual(
            tp.STAGES,
            (
                "raw_turn_saved",
                "archive_event_created",
                "extract_fields_called",
                "family_truth_written",
                "projection_updated",
            ),
            "The stage names are fixed by MASTER_WORK_ORDER_CHECKLIST.md "
            "item 3. Renaming one here silently breaks the comparison "
            "between harness evidence and the written record. Move the "
            "checklist forward first, then this test.",
        )


class DefaultOffTest(_FlagBase):
    def test_flag_defaults_off(self):
        self._off()
        self.assertFalse(tp.enabled())

    def test_begin_turn_returns_none_when_off(self):
        self._off()
        self.assertIsNone(tp.begin_turn(conv_id="c", person_id="p", turn_id="t"))

    def test_mark_is_a_no_op_when_off(self):
        self._off()
        tp.begin_turn(conv_id="c", person_id="p", turn_id="t")
        tp.mark("raw_turn_saved")
        self.assertIsNone(tp.summary_for_turn_id("t"))
        self.assertEqual(tp.recent(10), [])

    def test_end_turn_of_none_is_none(self):
        self._off()
        self.assertIsNone(tp.end_turn(None))


class RecordingTest(_FlagBase):
    def test_a_turn_records_the_stages_that_fired(self):
        self._on()
        token = tp.begin_turn(conv_id="conv1", person_id="p1", turn_id="t1",
                              turn_mode="interview")
        self.assertIsNotNone(token)
        tp.mark("raw_turn_saved", "turns")
        tp.mark("archive_event_created", "transcript.jsonl")
        tp.mark("archive_event_created", "transcript.jsonl")
        summary = tp.end_turn(token)

        self.assertIsNotNone(summary)
        self.assertEqual(summary["counts"]["raw_turn_saved"], 1)
        self.assertEqual(summary["counts"]["archive_event_created"], 2)
        self.assertEqual(summary["counts"]["extract_fields_called"], 0)
        self.assertEqual(summary["counts"]["family_truth_written"], 0)
        self.assertEqual(summary["counts"]["projection_updated"], 0)
        self.assertEqual(summary["stages_fired_count"], 2)
        self.assertEqual(summary["stages_total"], 5)
        self.assertEqual(summary["turn_id"], "t1")
        self.assertEqual(summary["conv_id"], "conv1")
        self.assertEqual(summary["turn_mode"], "interview")

    def test_a_zero_is_reported_as_instrumented(self):
        """A stage reading 0 must be distinguishable from a stage that
        was never measured --- that distinction IS Gate 7."""
        self._on()
        token = tp.begin_turn(turn_id="t2")
        tp.mark("raw_turn_saved")
        summary = tp.end_turn(token)
        for stage in tp.STAGES:
            self.assertTrue(
                summary["instrumented"][stage],
                f"{stage} must report instrumented=True so a count of 0 "
                "reads as 'did not fire', never as 'not measured'.",
            )

    def test_mark_outside_a_turn_is_a_no_op(self):
        """The normal path for the two browser-driven stages."""
        self._on()
        tp.mark("extract_fields_called", "extract-fields")
        self.assertEqual(tp.recent(10), [])

    def test_unknown_stage_is_ignored(self):
        self._on()
        token = tp.begin_turn(turn_id="t3")
        tp.mark("not_a_real_stage", "x")
        summary = tp.end_turn(token)
        self.assertEqual(summary["stages_fired_count"], 0)
        self.assertNotIn("not_a_real_stage", summary["counts"])

    def test_detail_is_truncated_and_first_wins(self):
        self._on()
        token = tp.begin_turn(turn_id="t4")
        tp.mark("raw_turn_saved", "a" * 200)
        summary = tp.end_turn(token)
        self.assertEqual(summary["counts"]["raw_turn_saved"], 1)

    def test_two_turns_do_not_bleed_into_each_other(self):
        self._on()
        t1 = tp.begin_turn(turn_id="turnA")
        tp.mark("raw_turn_saved")
        tp.end_turn(t1)
        t2 = tp.begin_turn(turn_id="turnB")
        tp.mark("projection_updated")
        tp.end_turn(t2)

        a = tp.summary_for_turn_id("turnA")
        b = tp.summary_for_turn_id("turnB")
        self.assertEqual(a["counts"]["raw_turn_saved"], 1)
        self.assertEqual(a["counts"]["projection_updated"], 0)
        self.assertEqual(b["counts"]["raw_turn_saved"], 0)
        self.assertEqual(b["counts"]["projection_updated"], 1)


class LookupTest(_FlagBase):
    def test_summary_for_unknown_turn_id_is_none(self):
        self._on()
        self.assertIsNone(tp.summary_for_turn_id("nope"))

    def test_summary_for_empty_turn_id_is_none(self):
        self._on()
        token = tp.begin_turn(turn_id="")
        tp.end_turn(token)
        self.assertIsNone(tp.summary_for_turn_id(""))

    def test_recent_is_newest_first_and_bounded(self):
        self._on()
        for i in range(80):
            token = tp.begin_turn(turn_id=f"t{i}")
            tp.mark("raw_turn_saved")
            tp.end_turn(token)
        items = tp.recent(5)
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]["turn_id"], "t79")
        self.assertEqual(items[-1]["turn_id"], "t75")
        # Ring is bounded --- the earliest turns have aged out.
        self.assertIsNone(tp.summary_for_turn_id("t0"))


class LogLineTest(_FlagBase):
    def _summary(self):
        self._on()
        token = tp.begin_turn(conv_id="conv9", person_id="p9", turn_id="t9",
                              turn_mode="interview")
        tp.mark("raw_turn_saved")
        tp.mark("archive_event_created")
        return tp.end_turn(token)

    def test_log_line_is_exactly_one_line(self):
        line = tp.log_line(self._summary())
        self.assertNotIn("\n", line)
        self.assertNotIn("\r", line)

    def test_log_line_carries_the_marker_and_every_stage(self):
        line = tp.log_line(self._summary())
        self.assertIn("[truth-pipeline]", line)
        for stage in tp.STAGES:
            self.assertIn(stage + "=", line)

    def test_log_line_carries_counts_and_a_fired_ratio(self):
        line = tp.log_line(self._summary())
        self.assertIn("raw_turn_saved=1", line)
        self.assertIn("archive_event_created=1", line)
        self.assertIn("extract_fields_called=0", line)
        self.assertIn("fired=2/5", line)

    def test_log_line_carries_ids_but_no_narrator_text(self):
        summary = self._summary()
        line = tp.log_line(summary)
        self.assertIn("turn_id=t9", line)
        self.assertIn("conv=conv9", line)
        self.assertIn("person=p9", line)
        for key in ("content", "message", "assistant", "transcript"):
            self.assertNotIn(key, line)


class NeverRaisesTest(_FlagBase):
    def test_mark_survives_garbage(self):
        self._on()
        token = tp.begin_turn(turn_id="tg")
        for bad in (None, 123, object(), b"raw_turn_saved"):
            tp.mark(bad)  # type: ignore[arg-type]
        tp.end_turn(token)

    def test_end_turn_twice_is_safe(self):
        self._on()
        token = tp.begin_turn(turn_id="tt")
        tp.end_turn(token)
        tp.end_turn(token)


# ── Source-level gates ────────────────────────────────────────────────────

class CallSiteCoverageTest(unittest.TestCase):
    """Every stage must have a real mark() call site in the tree.

    This is the load-bearing test of Phase 1. Gate 7's entire purpose is
    to separate "the turn wrote nothing" from "we were not watching". A
    stage that quietly loses its mark() during a refactor collapses that
    distinction and hands the next reader a false negative dressed as
    evidence.
    """

    _SITES = {
        "raw_turn_saved": ["server/code/api/db.py"],
        "archive_event_created": ["server/code/api/archive.py"],
        # WO-TRUTH-PIPELINE-01 Phase 2 (2026-07-30) — this entry read
        # ["server/code/api/routers/extract.py"] until this date. It
        # stopped being true when the extraction body moved behind
        # api.services.turn_extraction, which is where the mark now
        # lives so that `extract_fields_called` means "the shared
        # service ran" rather than "somebody hit that HTTP route".
        "extract_fields_called": ["server/code/api/services/turn_extraction.py"],
        "family_truth_written": ["server/code/api/db.py"],
        "projection_updated": ["server/code/api/services/projection_writer.py"],
    }

    def test_every_stage_has_a_mark_call_site(self):
        missing = []
        for stage, files in self._SITES.items():
            found = False
            for rel in files:
                text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
                if f'_tp.mark("{stage}"' in text:
                    found = True
                    break
            if not found:
                missing.append((stage, files))
        self.assertFalse(
            missing,
            "A truth-write stage has no mark() call site:\n"
            + "\n".join(f"  {s} expected in {f}" for s, f in missing)
            + "\n\nWithout the call site, that stage reports 0 forever and "
            "the harness cannot tell a routing bug from a blind spot. "
            "Restore the mark, or move this gate forward with a written "
            "reason in the doctrine.",
        )

    def test_every_mark_call_site_is_exception_swallowed(self):
        """A probe must never break a turn. Each call site sits inside
        try/except and the module import is lazy, so a missing or broken
        probe cannot take the write path down with it."""
        for rel in sorted({f for files in self._SITES.values() for f in files}):
            text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
            for chunk in text.split("_tp.mark(")[1:]:
                self.assertIn(
                    "except Exception:", chunk[:200],
                    f"a mark() call site in {rel} is not exception-guarded",
                )


class ChatWsWrapperTest(unittest.TestCase):
    """chat_ws wraps the turn body rather than instrumenting inside it.

    The turn body returns early from several deterministic short-circuit
    branches. Anything placed at the end of the body would miss those
    turns entirely and under-report. A finally around the call is the
    only placement that sees every exit.
    """

    _CHAT_WS = _REPO_ROOT / "server/code/api/routers/chat_ws.py"

    def test_body_is_split_out_and_called_from_the_wrapper(self):
        text = self._CHAT_WS.read_text(encoding="utf-8")
        self.assertIn("async def _generate_and_stream_body(", text)
        self.assertIn("await _generate_and_stream_body(", text)

    def test_probe_is_closed_in_a_finally(self):
        text = self._CHAT_WS.read_text(encoding="utf-8")
        head = text[text.index("async def generate_and_stream("):]
        head = head[:head.index("async def _generate_and_stream_body(")]
        self.assertIn("finally:", head)
        self.assertIn("_tp.end_turn(", head)
        self.assertIn("_tp.log_line(", head)

    def test_probe_open_and_close_are_both_exception_guarded(self):
        text = self._CHAT_WS.read_text(encoding="utf-8")
        head = text[text.index("async def generate_and_stream("):]
        head = head[:head.index("async def _generate_and_stream_body(")]
        self.assertGreaterEqual(head.count("except Exception"), 2)


class FlagAndEnvExampleTest(unittest.TestCase):
    def test_flags_module_exposes_the_gate_and_defaults_off(self):
        sys.path.insert(0, str(_SERVER_CODE))
        from api import flags  # noqa: E402
        saved = os.environ.pop(_FLAG, None)
        try:
            self.assertFalse(flags.truth_pipeline_log_enabled())
        finally:
            if saved is not None:
                os.environ[_FLAG] = saved

    def test_env_example_documents_the_flag_as_off(self):
        text = (_REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn(
            f"{_FLAG}=0", text,
            "A new flag must land in .env.example in the same commit, "
            "default OFF, or the operator has no way to find it.",
        )


class HarnessSurfaceTest(unittest.TestCase):
    _HARNESS = _REPO_ROOT / "server/code/api/routers/operator_harness.py"

    def test_response_carries_an_optional_truth_pipeline_field(self):
        text = self._HARNESS.read_text(encoding="utf-8")
        self.assertIn("truth_pipeline: Optional[Dict[str, Any]] = None", text)

    def test_the_field_is_additive_and_defaults_to_none(self):
        """Existing harness callers must keep working with the flag off,
        so the field defaults to None rather than an empty summary that
        would read as five genuine zeros."""
        text = self._HARNESS.read_text(encoding="utf-8")
        self.assertIn("if not _tp.enabled():", text)
        self.assertIn("return None", text)


class TurnPathReachabilityTest(unittest.TestCase):
    """Pins the TRUTH-PIPELINE-01 Phase 1 reading (2026-07-30).

    The live evidence run fired two harness turns --- one synthetic
    narrator, one real narrator (Kent) --- with identical results:

        raw_turn_saved=1  archive_event_created=2
        extract_fields_called=0  family_truth_written=0
        projection_updated=0     fired=2/5

    Before Phase 1 that read as one undifferentiated failure, which is
    what the archived golfball probe called "speaker_zero_delta --- turn
    did not write anywhere". The probe plus a caller trace split it into
    three different things:

      - extract_fields_called=0 WAS a REAL GAP. Until 2026-07-30 this
        entry read: "The endpoint has no internal Python caller anywhere
        in the tree; only the browser (ui/js/interview.js) posts to it.
        A chat_ws turn therefore never extracts, so nothing downstream
        of extraction can fire either. This is the single defect, and it
        is Phase 2 material."

        That stopped being true on 2026-07-30. Phase 2 closed the gap:
        the extraction body moved out of the route into
        routers.extract.run_field_extraction, and both callers — the
        HTTP endpoint and the chat_ws completed-turn path — now reach
        it through api.services.turn_extraction. So on a completed
        interview turn the EXPECTED value is now
        extract_fields_called=1, and a 0 there is a regression. The
        structural facts that survived the fix are pinned below by
        test_the_extraction_route_is_only_a_seam.

      - family_truth_written=0 is CORRECT BY DESIGN for any turn. Every
        path into ft_add_note / ft_add_row is an explicit operator HTTP
        action: POST /note, POST /note/{id}/propose, and POST /backfill
        (which is the only caller of ft_backfill_from_profile_json).
        Family truth is a review-gated pipeline. A turn is not supposed
        to write it, and if a turn ever did, that would be the bug.

      - projection_updated=0 is CORRECT BY DESIGN for an INTERVIEW turn.
        chat_ws reaches projection_writer.apply_correction only inside
        the `turn_mode == "correction"` branch. Both evidence turns ran
        turn_mode="interview", the harness default.

    So Phase 2 was one fix, not three — and as of 2026-07-30 it has
    shipped. These tests exist because the reading above is only true
    while the three structural facts below hold.
    They read the AST rather than the raw text on purpose: every one of
    these names also appears in comments and docstrings nearby, and a
    substring guard would pass on prose while missing a real call.
    """

    _API = _REPO_ROOT / "server/code/api"

    @staticmethod
    def _tree(rel_or_path):
        path = rel_or_path
        if not isinstance(path, Path):
            path = _REPO_ROOT / rel_or_path
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    @staticmethod
    def _called_names(tree):
        """Terminal callee names for every Call in the tree.

        `db.ft_add_note(...)` and a bare `ft_add_note(...)` both reduce
        to "ft_add_note"; anything in a comment or a string reduces to
        nothing at all, which is the point.
        """
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name):
                out.append(func.id)
            elif isinstance(func, ast.Attribute):
                out.append(func.attr)
        return out

    def _api_py_files(self):
        return sorted(
            p for p in self._API.rglob("*.py")
            if "__pycache__" not in p.parts
        )

    def test_family_truth_is_never_written_from_the_turn_path(self):
        """chat_ws must not call the family-truth writers.

        family_truth_written=0 on a harness turn is only correct-by-
        design while this holds. If a later phase wires extraction
        through to family truth, this test fails first --- move the
        reading forward in the doctrine and the checklist in the same
        commit, do not just delete the assert.
        """
        called = set(self._called_names(
            self._tree("server/code/api/routers/chat_ws.py")
        ))
        leaked = sorted({"ft_add_note", "ft_add_row"} & called)
        self.assertFalse(
            leaked,
            "chat_ws.py now calls the family-truth writer(s) "
            f"{leaked}. The Phase 1 reading recorded in CLAUDE.md and "
            "the checklist says family_truth_written=0 is correct by "
            "design because every write is an explicit operator HTTP "
            "action. That reading is now wrong. Update it with a date, "
            "per CLAUDE.md:441, rather than weakening this gate.",
        )

    def test_the_extraction_route_is_only_a_seam(self):
        """The gap is closed; these are the shapes of the closure.

        WO-TRUTH-PIPELINE-01 Phase 2 (2026-07-30). This test replaces
        test_extract_fields_has_no_internal_python_caller, which asserted
        that NOTHING under server/code/api called extraction. Its own
        failure message said: "If Phase 2 has closed that gap, say so in
        the record and move this gate forward with a written reason."
        Phase 2 closed it, the record is moved forward in this class
        docstring and in the doctrine, and the reason is that a completed
        turn is now supposed to extract.

        The gate is moved forward, not removed. Three things that MUST
        still hold, and each of which the old test was really protecting:

          1. `extract_fields` — the FastAPI route function — still
             has no internal Python caller. New code must go through the
             service, not re-enter the endpoint. (A route function called
             directly from Python is the shape that grows into a
             self-call.)
          2. The extraction implementation has exactly ONE internal
             caller module: api/services/turn_extraction.py. If a second
             module appears here, the "one shared service" property has
             been lost.
          3. chat_ws.py holds no copy of the implementation — it calls
             the service and nothing else.
        """
        route_callers = []
        impl_callers = []
        for path in self._api_py_files():
            text = path.read_text(encoding="utf-8")
            if "extract_fields" not in text and "run_field_extraction" not in text:
                continue  # cheap prefilter; the AST below is the gate
            called = self._called_names(self._tree(path))
            rel = str(path.relative_to(_REPO_ROOT)).replace("\\", "/")
            if "extract_fields" in called:
                route_callers.append(rel)
            if "run_field_extraction" in called:
                impl_callers.append(rel)

        self.assertFalse(
            route_callers,
            "the /api/extract-fields ROUTE FUNCTION now has internal "
            f"Python caller(s) in {route_callers}. Phase 2's rule is "
            "that both callers reach the shared service, not the "
            "endpoint. Route the new caller through "
            "api.services.turn_extraction instead.",
        )

        self.assertEqual(
            sorted(impl_callers),
            ["server/code/api/services/turn_extraction.py"],
            "the extraction implementation run_field_extraction() is "
            f"called from {sorted(impl_callers)}. Phase 2 requires "
            "exactly one internal caller — the shared service — so "
            "that the probe mark, the six-outcome observability "
            "vocabulary and the persisted idempotency claim apply "
            "uniformly. A second caller silently bypasses all three.",
        )

    def test_chat_ws_reaches_extraction_only_through_the_shared_service(self):
        """The positive half of Phase 2, asserted behaviourally-in-shape.

        The old gate proved a NEGATIVE (nothing calls extraction) and so
        could pass forever while the fix rotted. This one proves the
        POSITIVE: chat_ws calls the shared service, and calls nothing
        else that could be an extraction shortcut.
        """
        tree = self._tree("server/code/api/routers/chat_ws.py")
        called = set(self._called_names(tree))

        # Resolve import aliases before asking who is called. chat_ws
        # imports the service as `extract_completed_turn as _extract_turn`
        # (the repo's local-import convention), so the callee name in the
        # AST is the alias. Mapping alias -> real name keeps this a
        # structural check instead of a naming-convention check.
        aliases = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.asname:
                        aliases[a.asname] = a.name
        called = {aliases.get(name, name) for name in called}

        self.assertIn(
            "extract_completed_turn", called,
            "chat_ws.py no longer calls extract_completed_turn(). That "
            "call IS the Phase 2 fix: without it a completed interview "
            "turn persists and archives but never extracts, which is "
            "exactly the defect Gate 7 Phase 1 measured as "
            "extract_fields_called=0.",
        )

        shortcuts = sorted(
            {"run_field_extraction", "extract_fields", "run_http_extraction"} & called
        )
        self.assertFalse(
            shortcuts,
            f"chat_ws.py calls {shortcuts} directly. The completed-turn "
            "path must reach extraction only through "
            "extract_completed_turn(), which is the one place the "
            "idempotency claim and the failure isolation live. Calling "
            "the implementation or the HTTP seam directly skips both.",
        )

        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if "routers.extract" in node.module or node.module.endswith("extract"):
                    imported.add(node.module)
        self.assertFalse(
            imported,
            f"chat_ws.py imports {sorted(imported)}. The WebSocket path "
            "must not reach into the HTTP router module; it goes through "
            "api.services.turn_extraction.",
        )

    def test_projection_write_from_chat_ws_sits_in_the_correction_branch(self):
        """projection_updated=0 is design for interview, not for correction.

        The distinction matters for reading future evidence: a
        correction turn that still reports projection_updated=0 IS a
        defect, and an interview turn that reports 0 is not. That is
        only a usable rule while every apply_correction call in chat_ws
        is inside `if turn_mode == "correction":`.
        """
        tree = self._tree("server/code/api/routers/chat_ws.py")

        def _is_correction_test(node):
            return (
                isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Name)
                and node.left.id == "turn_mode"
                and len(node.ops) == 1
                and isinstance(node.ops[0], ast.Eq)
                and len(node.comparators) == 1
                and isinstance(node.comparators[0], ast.Constant)
                and node.comparators[0].value == "correction"
            )

        def _apply_call_ids(root):
            found = set()
            for node in ast.walk(root):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "apply_correction"
                ):
                    found.add(id(node))
            return found

        all_calls = _apply_call_ids(tree)
        self.assertTrue(
            all_calls,
            "chat_ws.py no longer calls projection_writer."
            "apply_correction at all. The Phase 1 reading says a "
            "correction turn is the one turn shape that can move the "
            "projection. If that path is gone, the reading is stale.",
        )

        guarded = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _is_correction_test(node.test):
                for stmt in node.body:
                    guarded |= _apply_call_ids(stmt)

        self.assertEqual(
            all_calls, guarded,
            "an apply_correction() call in chat_ws.py sits outside the "
            '`turn_mode == "correction"` branch. Phase 1 recorded '
            "projection_updated=0 as correct-by-design for an interview "
            "turn on exactly that basis. Either restore the guard or "
            "date the correction into the record.",
        )


if __name__ == "__main__":
    unittest.main()
