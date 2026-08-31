"""The trace must observe, never participate.

    PYTHONPATH=server/code python3 -m unittest tests.test_lori_response_trace

WO-LORI-LISTEN-AND-RETAIN-01 Phase 1/2. Five properties, each of which
would let the instrumentation lie if it were untrue:

1. The trace does not alter delivered text.
2. One turn keeps one identity across every stage.
3. The raw model output is captured BEFORE the first rewrite.
4. Delivered and persisted text are compared, not assumed equal.
5. A failed or unavailable storage check can never read as absent
   or passing.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
for _p in (str(_REPO / "server" / "code"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services import lori_response_trace as RT      # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._orig = os.environ.get("HORNELORE_TRACE_DIR")
        os.environ["HORNELORE_TRACE_DIR"] = self.tmp.name
        self.addCleanup(self._restore)
        os.environ.pop("HORNELORE_RESPONSE_TRACE", None)

    def _restore(self):
        if self._orig is None:
            os.environ.pop("HORNELORE_TRACE_DIR", None)
        else:
            os.environ["HORNELORE_TRACE_DIR"] = self._orig

    def _written(self):
        out = []
        for f in Path(self.tmp.name).glob("*.jsonl"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    out.append(json.loads(line))
        return out


# ── 1. the trace does not alter delivered text ───────────────────────
class TraceIsNonParticipatingTests(_Base):
    """The pipeline shape, run with the trace ON and OFF."""

    @staticmethod
    def _pipeline(raw_text, trace_on):
        """A miniature of chat_ws: raw text, three rewrites, deliver."""
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1" if trace_on else "0"
        tid = RT.begin(narrator_id="p1", conversation_id="c1")
        RT.raw(raw_text, trace_id=tid)
        final = raw_text
        prev = [final]

        def ck(name):
            RT.stage(name, fired=(prev[0] != final), before=prev[0],
                     after=final, trace_id=tid)
            prev[0] = final

        final = final.replace("  ", " ")
        ck("comm_control")
        final = final.strip()
        ck("trim")
        final = final + ""
        ck("guards")
        RT.finish(delivered=final, persisted=final, trace_id=tid)
        return final

    def test_delivered_text_is_byte_identical_with_trace_on_and_off(self):
        for raw in ("  Hello  there. What happened next?  ",
                    "New York marked a significant departure for you.",
                    "", "   ", "¿Qué pasó después?"):
            self.assertEqual(self._pipeline(raw, False),
                             self._pipeline(raw, True),
                             f"trace changed delivered text for {raw!r}")

    def test_a_raising_sink_still_delivers(self):
        """If the trace itself breaks, the turn must not."""
        os.environ["HORNELORE_TRACE_DIR"] = "/proc/nonexistent/cannot/write"
        try:
            self.assertEqual(self._pipeline("Hello there.", True),
                             "Hello there.")
        finally:
            os.environ["HORNELORE_TRACE_DIR"] = self.tmp.name

    def test_disabled_writes_nothing(self):
        self._pipeline("Hello there.", False)
        self.assertEqual([], self._written())


# ── 2. one turn, one identity ────────────────────────────────────────
class TraceIdentityTests(_Base):
    def test_one_turn_keeps_one_identity_across_stages(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n1", conversation_id="c1", turn_key="t1")
        self.assertTrue(tid)
        RT.raw("raw text here", trace_id=tid)
        for name in ("comm_control", "reflection_shape", "receipt", "guards"):
            RT.stage(name, fired=True, before="a", after="b", trace_id=tid)
        RT.finish(delivered="b", persisted="b", trace_id=tid)

        rows = self._written()
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual(tid, row["trace_id"])
        self.assertEqual(["comm_control", "reflection_shape", "receipt",
                          "guards"], [s["stage"] for s in row["stages"]])
        self.assertEqual([0, 1, 2, 3], [s["index"] for s in row["stages"]])

    def test_two_turns_do_not_share_a_trace(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        a = RT.begin(narrator_id="n", conversation_id="SAME")
        RT.raw("first", trace_id=a)
        RT.stage("comm_control", fired=True, before="first", after="f",
                 trace_id=a)
        RT.finish(delivered="f", trace_id=a)
        b = RT.begin(narrator_id="n", conversation_id="SAME")
        RT.raw("second", trace_id=b)
        RT.finish(delivered="second", trace_id=b)

        self.assertNotEqual(a, b)
        rows = {r["trace_id"]: r for r in self._written()}
        self.assertEqual(2, len(rows))
        # THE POINT: same conversation, different turns. Correlating by
        # conv= cannot tell these apart — which is exactly why the
        # 58/77 cascade figure is provisional.
        self.assertEqual("SAME", rows[a]["conversation_id"])
        self.assertEqual("SAME", rows[b]["conversation_id"])
        self.assertEqual(1, len(rows[a]["stages"]))
        self.assertEqual(0, len(rows[b]["stages"]))


# ── 3. raw is captured before rewriting ──────────────────────────────
class RawCaptureTests(_Base):
    def test_raw_is_the_pre_rewrite_text(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.raw("New York marked a significant departure from Minnesota.",
               trace_id=tid)
        RT.stage("comm_control", fired=True,
                 before="New York marked a significant departure from Minnesota.",
                 after="Let and After - there's a lot held in that.",
                 trace_id=tid)
        RT.finish(delivered="Let and After - there's a lot held in that.",
                  trace_id=tid)
        row = self._written()[0]
        self.assertEqual(
            "New York marked a significant departure from Minnesota.",
            row["raw_text"])
        self.assertFalse(row["raw_equals_delivered"])
        self.assertEqual(8, row["raw_words"])
        # NOT a word-count claim, deliberately. This real capture
        # replaced an 8-word grounded sentence with a 10-word template,
        # so `net_words_removed` is NEGATIVE while the turn got worse.
        # Length is not the measure of harm; the report must compare
        # the texts, and any future rule that scores this pipeline on
        # word count alone would call this substitution an improvement.
        self.assertEqual(-2, row["net_words_removed"])

    def test_raw_cannot_be_overwritten_by_a_later_call(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.raw("the real model output", trace_id=tid)
        RT.raw("a rewritten version", trace_id=tid)
        RT.finish(delivered="x", trace_id=tid)
        self.assertEqual("the real model output", self._written()[0]["raw_text"])

    def test_word_and_question_deltas_are_recorded_per_stage(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.stage("comm_control", fired=True,
                 before="one two three four five? six seven?",
                 after="one two?", trace_id=tid)
        RT.finish(delivered="one two?", trace_id=tid)
        st = self._written()[0]["stages"][0]
        self.assertEqual(7, st["words_before"])
        self.assertEqual(2, st["words_after"])
        self.assertEqual(-5, st["words_delta"])
        self.assertEqual(2, st["questions_before"])
        self.assertEqual(1, st["questions_after"])
        self.assertTrue(st["changed"])

    def test_a_layer_that_ran_and_changed_nothing_is_still_recorded(self):
        """Absent from the trace must not be confusable with did-not-run."""
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.stage("response_guards", fired=False, before="same", after="same",
                 trace_id=tid)
        RT.finish(delivered="same", trace_id=tid)
        st = self._written()[0]["stages"][0]
        self.assertFalse(st["fired"])
        self.assertFalse(st["changed"])


# ── 4. delivered vs persisted is compared, not assumed ───────────────
class DeliveredVersusPersistedTests(_Base):
    def test_match_is_recorded_as_a_result_not_an_assumption(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.finish(delivered="hello", persisted="hello", trace_id=tid)
        self.assertTrue(self._written()[0]["delivered_equals_persisted"])

    def test_a_mismatch_is_visible(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.finish(delivered="what the narrator saw",
                  persisted="what the database kept", trace_id=tid)
        self.assertFalse(self._written()[0]["delivered_equals_persisted"])


# ── 5. a failed measurement can never read as absent or passing ──────
class StorageVocabularyTests(_Base):
    def test_measurement_failed_is_distinct_from_measured_absent(self):
        self.assertNotEqual(RT.RESULT_MEASUREMENT_FAILED,
                            RT.RESULT_MEASURED_ABSENT)
        self.assertIn(RT.RESULT_MEASUREMENT_FAILED, RT.RESULTS)

    def test_a_wrong_origin_404_is_measurement_failed_not_absent(self):
        """The memoir case. A 404 from the static server on :8082 means
        the correct source was never queried — not that memoir data is
        missing."""
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.storage("memoir_source", RT.RESULT_MEASUREMENT_FAILED,
                   detail={"url": "http://localhost:8082/api/memoir/canonical",
                           "http": 404,
                           "why": "static file server, route not served here"},
                   trace_id=tid)
        RT.finish(delivered="x", trace_id=tid)
        cell = self._written()[0]["storage"]["memoir_source"]
        self.assertEqual(RT.RESULT_MEASUREMENT_FAILED, cell["result"])
        self.assertNotEqual(RT.RESULT_MEASURED_ABSENT, cell["result"])
        self.assertNotEqual(RT.RESULT_PERSISTED, cell["result"])

    def test_an_unknown_result_degrades_to_not_measured(self):
        """A typo must never become a pass."""
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.storage("bio_facts", "ok", trace_id=tid)
        RT.storage("chronology", "PASS", trace_id=tid)
        RT.finish(delivered="x", trace_id=tid)
        store = self._written()[0]["storage"]
        for k in ("bio_facts", "chronology"):
            self.assertEqual(RT.RESULT_NOT_MEASURED, store[k]["result"])
            self.assertIsNotNone(store[k]["coerced_from"])

    def test_the_five_results_are_all_distinct(self):
        self.assertEqual(5, len(set(RT.RESULTS)))


# ── the wiring in chat_ws is present and observation-only ────────────
class ChatWsWiringTests(unittest.TestCase):
    def setUp(self):
        self.src = (_REPO / "server" / "code" / "api" / "routers"
                    / "chat_ws.py").read_text(encoding="utf-8")

    def test_raw_is_captured_immediately_after_generation(self):
        gen = self.src.index('final_text = "".join(reply_parts).strip()')
        raw = self.src.index("_rt.raw(final_text", gen)
        between = self.src[gen:raw]
        self.assertNotIn("_rt_ck(", between,
                         "a transformation checkpoint precedes the raw "
                         "capture; raw would no longer be raw")

    def test_every_final_text_assignment_has_a_checkpoint(self):
        import re
        # each assignment site should be followed by a checkpoint within
        # a few lines; count them rather than pin line numbers
        self.assertGreaterEqual(self.src.count("_rt_ck("), 11)

    def test_the_trace_import_cannot_break_the_router(self):
        self.assertIn("except Exception:  # pragma: no cover - defensive",
                      self.src)
        self.assertIn("def begin(*a, **k): return None", self.src)


if __name__ == "__main__":       # pragma: no cover
    unittest.main()


# ── opt-in, and the retention continuation ───────────────────────────
class OptInTests(_Base):
    def test_tracing_is_off_unless_explicitly_enabled(self):
        os.environ.pop("HORNELORE_RESPONSE_TRACE", None)
        self.assertFalse(RT.enabled())
        self.assertIsNone(RT.begin(narrator_id="n", conversation_id="c"))

    def test_only_explicit_truthy_values_enable_it(self):
        for v, want in (("1", True), ("true", True), ("on", True),
                        ("yes", True), ("0", False), ("", False),
                        ("off", False), ("maybe", False)):
            os.environ["HORNELORE_RESPONSE_TRACE"] = v
            self.assertEqual(want, RT.enabled(), f"for {v!r}")


class RetentionContinuationTests(_Base):
    def setUp(self):
        super().setUp()
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"

    def _parked_turn(self, row="1909"):
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.raw("model text", trace_id=tid)
        RT.seal(delivered="delivered text", persisted="delivered text",
                trace_id=tid)
        RT.storage("durable_turns", RT.RESULT_PERSISTED, trace_id=tid)
        RT.park(keys=[row, f"turnrow:{row}"], trace_id=tid)
        return tid

    def test_park_does_not_write_yet(self):
        self._parked_turn()
        self.assertEqual([], self._written(),
                         "parking wrote the record before retention "
                         "results could attach")

    def test_extraction_attaches_by_durable_row_id(self):
        """The extraction hook knows the row, not the trace."""
        tid = self._parked_turn(row="1909")
        self.assertTrue(RT.attach("turnrow:1909", "extraction",
                                  RT.RESULT_PERSISTED, detail={"items": 8}))
        RT.close("turnrow:1909")
        rows = self._written()
        self.assertEqual(1, len(rows))
        self.assertEqual(tid, rows[0]["trace_id"])
        self.assertEqual(RT.RESULT_PERSISTED,
                         rows[0]["storage"]["extraction"]["result"])
        self.assertEqual(8, rows[0]["storage"]["extraction"]["detail"]["items"])

    def test_the_response_half_survives_into_the_written_record(self):
        self._parked_turn()
        RT.close("1909")
        row = self._written()[0]
        self.assertEqual("model text", row["raw_text"])
        self.assertEqual("delivered text", row["delivered_text"])
        self.assertTrue(row["delivered_equals_persisted"])

    def test_unattached_stages_are_not_measured_never_absent(self):
        """The rule the whole report depends on."""
        self._parked_turn()
        RT.close("1909")
        store = self._written()[0]["storage"]
        for stage in RT.RETENTION_STAGES:
            self.assertIn(stage, store)
        for stage in ("rolling_summary", "archive", "memoir_source",
                      "life_map", "bio_facts", "chronology", "extraction"):
            self.assertEqual(RT.RESULT_NOT_MEASURED, store[stage]["result"],
                             f"{stage} was never attached and must not "
                             f"render as absent or passing")
        self.assertEqual(RT.RESULT_PERSISTED, store["durable_turns"]["result"])

    def test_a_never_closed_trace_is_swept_out_not_lost(self):
        import time as _t
        self._parked_turn(row="7001")
        RT._sweep(max_age_s=-1)
        rows = self._written()
        self.assertEqual(1, len(rows))
        self.assertTrue(rows[0].get("swept"))
        self.assertEqual("model text", rows[0]["raw_text"])

    def test_attach_to_an_unknown_key_reports_failure(self):
        self.assertFalse(RT.attach("no-such-row", "extraction",
                                   RT.RESULT_PERSISTED))

    def test_reflection_shape_is_its_own_stage_in_chat_ws(self):
        """*(This asserted `span_shared_with` / `intermediate_text` —
        the placeholders used while the shaper's own before/after was
        unavailable. CommunicationControlResult now exposes the real
        span, so the workaround is gone and the stage carries the
        shaper's actual text.)*"""
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        self.assertIn('"reflection_shape"', src)
        self.assertIn("_cc_result.reflection_before_text", src)
        self.assertIn("_cc_result.reflection_after_text", src)
        self.assertNotIn("intermediate_text", src,
                         "the not-measured placeholder should be gone now "
                         "that the real span is exposed")


class RetentionWiringHonestyTests(unittest.TestCase):
    """The docstring must not claim more than the code does."""

    def test_the_module_lists_what_is_actually_wired(self):
        src = (_REPO / "server" / "code" / "api" / "services"
               / "lori_response_trace.py").read_text(encoding="utf-8")
        self.assertIn("WHAT IS AND IS NOT WIRED", src)
        self.assertIn("NOT WIRED -> not_measured", src)

    def test_extraction_attaches_from_product_code(self):
        """*(Was `_trace_extraction`, called from two sites. Renamed to
        `_finalize_extraction_trace` and moved behind a wrapper on the
        public entry point so failure, malformed shape, timeout and
        cancellation also attach and close.)*"""
        src = (_REPO / "server" / "code" / "api" / "services"
               / "turn_extraction.py").read_text(encoding="utf-8")
        self.assertIn("_finalize_extraction_trace", src)
        self.assertIn("RESULT_MEASURED_ABSENT", src)
        self.assertIn("RESULT_MEASUREMENT_FAILED", src)


# ── the six blockers from the e579ffc review ─────────────────────────
class TraceHealthEndpointTests(_Base):
    def test_health_reports_the_live_enabled_value(self):
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        self.assertTrue(RT.health()["enabled"])
        os.environ["HORNELORE_RESPONSE_TRACE"] = "0"
        self.assertFalse(RT.health()["enabled"])

    def test_health_carries_schema_and_location(self):
        h = RT.health()
        for k in ("enabled", "schema_version", "env_flag", "output_dir",
                  "output_dir_exists", "retention_stages"):
            self.assertIn(k, h)
        self.assertEqual(RT.SCHEMA_VERSION, h["schema_version"])

    def test_the_route_exists(self):
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "ping.py").read_text(encoding="utf-8")
        self.assertIn('@router.get("/health/response-trace")', src)


class RequiredContextTests(_Base):
    def setUp(self):
        super().setUp()
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"

    def test_missing_required_context_is_an_instrumentation_failure(self):
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.note("narrator_input", "hello", trace_id=tid)
        RT.require(trace_id=tid)
        RT.finish(delivered="x", trace_id=tid)
        row = self._written()[0]
        self.assertTrue(row["instrumentation_failed"])
        self.assertIn("prompt_tokens", row["missing_required_context"])
        self.assertIn("runtime71_current_era", row["missing_required_context"])

    def test_complete_context_is_not_a_failure(self):
        tid = RT.begin(narrator_id="n", conversation_id="c")
        for k, v in (("narrator_input", "hello"),
                     ("runtime71_current_era", "today"),
                     ("prompt_tokens", 6300),
                     ("prompt_budget", {"kept_turns": 2})):
            RT.note(k, v, trace_id=tid)
        RT.require(trace_id=tid)
        RT.finish(delivered="x", trace_id=tid)
        self.assertFalse(self._written()[0]["instrumentation_failed"])

    def test_chat_ws_reads_real_names_not_locals_guesses(self):
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        self.assertNotIn("locals()[_rt_k]", src,
                         "required evidence read through a swallowed "
                         "locals() lookup")
        for real in ("_budget.kept_turns", "_budget.dropped_turns",
                     "_prompt_tokens", '_rt71.get("current_era")',
                     "_rt.require("):
            self.assertIn(real, src)


class ExtractionFinalizerTests(_Base):
    """Every terminal outcome must close the trace, not just two."""

    def setUp(self):
        super().setUp()
        os.environ["HORNELORE_RESPONSE_TRACE"] = "1"
        self.src = (_REPO / "server" / "code" / "api" / "services"
                    / "turn_extraction.py").read_text(encoding="utf-8")

    def test_there_is_one_funnel(self):
        self.assertIn("_finalize_extraction_trace", self.src)
        self.assertEqual(1, self.src.count("def _finalize_extraction_trace"))

    def test_the_public_entry_point_is_wrapped(self):
        self.assertIn("async def extract_completed_turn(**kwargs)", self.src)
        self.assertIn("async def _extract_completed_turn_inner(", self.src)

    def test_exceptions_and_cancellation_are_covered(self):
        self.assertIn("except BaseException as exc:", self.src)
        self.assertIn('"exception"', self.src)

    def test_failure_is_measurement_failed_not_absent(self):
        tid = RT.begin(narrator_id="n", conversation_id="c")
        RT.seal(delivered="d", trace_id=tid)
        RT.park(keys=["turnrow:5"], trace_id=tid)
        RT.attach("turnrow:5", "extraction", RT.RESULT_MEASUREMENT_FAILED,
                  detail={"status": "failed"})
        RT.close("turnrow:5")
        cell = self._written()[0]["storage"]["extraction"]
        self.assertEqual(RT.RESULT_MEASUREMENT_FAILED, cell["result"])
        self.assertNotEqual(RT.RESULT_MEASURED_ABSENT, cell["result"])


class ReflectionSpanTests(unittest.TestCase):
    def test_comm_control_exposes_the_shapers_own_span(self):
        src = (_REPO / "server" / "code" / "api" / "services"
               / "lori_communication_control.py").read_text(encoding="utf-8")
        for f in ("reflection_before_text", "reflection_after_text",
                  "reflection_actions"):
            self.assertIn(f, src)
        self.assertIn("_reflect_before = current", src)

    def test_chat_ws_uses_that_span_not_the_combined_one(self):
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        self.assertIn("_cc_result.reflection_before_text", src)
        self.assertIn("_cc_result.reflection_after_text", src)


class DefensiveStubTests(unittest.TestCase):
    def test_the_stub_covers_every_method_the_router_calls(self):
        src = (_REPO / "server" / "code" / "api" / "routers"
               / "chat_ws.py").read_text(encoding="utf-8")
        stub = src[src.index("class _rt:"):src.index("from ..services.lori_response_guards")]
        import re
        called = set(re.findall(r"_rt\.([a-z_]+)\(", src))
        defined = set(re.findall(r"def ([a-z_]+)\(\*a, \*\*k\)", stub))
        missing = called - defined - {"RESULT_PERSISTED"}
        self.assertEqual(set(), missing,
                         f"the no-op fallback lacks {sorted(missing)}; an "
                         f"import failure would hit a missing method, be "
                         f"swallowed, and silently produce no trace")
