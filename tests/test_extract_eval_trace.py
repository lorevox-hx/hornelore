"""B3(a) — the armed evaluation trace.

Chris, B3 decision 4 (2026-09-23): full model output is captured ONLY in an
armed evaluation trace -- off by default, its own file under `.runtime/`,
never `api.log`. The ordinary log keeps its 500-character prefix; widening it
would be a privacy and log-bloat regression bought for test convenience.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

try:
    import fastapi  # noqa: F401
    import pydantic  # noqa: F401
except ImportError:
    from fastapi_stub import install as _install_stub
    _install_stub()
    import pydantic  # noqa: F401
_REAL_STACK = bool(getattr(pydantic, "__file__", None))

from api.routers import extract as X  # noqa: E402

LONG_RAW = json.dumps([{"fieldPath": "parents.notableLifeEvents",
                        "value": "x" * 900, "confidence": 0.9}])
ANSWER = "My father Kent worked construction all over North Dakota."


class _Req:
    current_section = "early_caregivers"
    current_target_path = "parents.firstName"


class TraceFile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "eval_traces"
        self.p = mock.patch.object(X, "_EVAL_TRACE_DIR", self.dir)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def _lines(self):
        files = list(self.dir.glob("extract-*.jsonl")) if self.dir.exists() else []
        return [json.loads(l) for f in files for l in f.read_text("utf-8").splitlines()]

    def test_off_by_default_writes_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("HORNELORE_EXTRACT_EVAL_TRACE", None)
            X._write_eval_trace(_Req(), ANSWER, LONG_RAW)
        self.assertFalse(self.dir.exists(), "an unarmed trace must not even create its directory")

    def test_armed_writes_the_full_output_and_not_the_answer(self):
        with mock.patch.dict(os.environ, {"HORNELORE_EXTRACT_EVAL_TRACE": "1"}):
            X._write_eval_trace(_Req(), ANSWER, LONG_RAW)
        (rec,) = self._lines()
        self.assertEqual(rec["raw"], LONG_RAW, "the whole output, not a prefix")
        self.assertEqual(rec["raw_len"], len(LONG_RAW))
        self.assertEqual((rec["section"], rec["target"]),
                         ("early_caregivers", "parents.firstName"))
        self.assertNotIn(ANSWER, json.dumps(rec), "the narrator's answer is hashed, not stored")
        self.assertEqual(len(rec["answer_sha12"]), 12)

    def test_a_trace_failure_never_reaches_the_turn(self):
        with mock.patch.dict(os.environ, {"HORNELORE_EXTRACT_EVAL_TRACE": "1"}), \
             mock.patch("builtins.open", side_effect=OSError("disk full")):
            X._write_eval_trace(_Req(), ANSWER, LONG_RAW)   # must not raise

    def test_the_ordinary_log_keeps_its_prefix_when_armed(self):
        with mock.patch.dict(os.environ, {"HORNELORE_EXTRACT_EVAL_TRACE": "1"}), \
             self.assertLogs("lorevox.extract", level=logging.INFO) as cm:
            X._parse_llm_json(LONG_RAW)
        raw_lines = [m for m in cm.output if "Raw LLM output" in m]
        self.assertTrue(raw_lines)
        logged = raw_lines[0].split("chars): ", 1)[1]
        self.assertLessEqual(len(logged), 500, "api.log must not grow when the trace is armed")


@unittest.skipUnless(_REAL_STACK, "production boundary needs real pydantic — run in .venv")
class ProductionBoundary(unittest.TestCase):
    """An armed extraction writes the trace from inside run_field_extraction."""

    def test_an_armed_extraction_is_traced_in_full(self):
        with tempfile.TemporaryDirectory() as d:
            tdir = Path(d) / "eval_traces"
            req = X.ExtractFieldsRequest(answer=ANSWER, person_id="test-narrator",
                                         current_section="early_caregivers",
                                         current_target_path="parents.firstName")
            with mock.patch.object(X, "_EVAL_TRACE_DIR", tdir), \
                 mock.patch.dict(os.environ, {"HORNELORE_EXTRACT_EVAL_TRACE": "1"}), \
                 mock.patch.object(X, "_extract_via_llm",
                                   side_effect=lambda *a, **k: (X._parse_llm_json(LONG_RAW), LONG_RAW)), \
                 mock.patch.object(X, "_known_kinship_names", return_value={}):
                X.run_field_extraction(req)
            recs = [json.loads(l) for f in tdir.glob("*.jsonl")
                    for l in f.read_text("utf-8").splitlines()]
        self.assertEqual([r["raw"] for r in recs], [LONG_RAW])


if __name__ == "__main__":
    unittest.main()
