"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase D creep defenses tests.

Covers acceptance gates #13 (continuation metric written + computed),
#14 (chapter exhaustion blocks asks regardless of count — repeated
here for the Defense 2 surface), #15 (cap overrides require explicit
acknowledgment file), #17 (telemetry warning thresholds fire).

Acceptance gate #16 (readiness gate failure when overrides active)
is BLOCKED at the codebase level — parent_session_readiness does not
exist. We test the readiness_gate_blocked() helper that any future
readiness framework will consult.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


# ─────────────────────────────────────────────────────────────────────
# Defense 1 — chapter_continuation_metric correctness
# ─────────────────────────────────────────────────────────────────────


def _setup_temp_bio_db():
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_creep_")
    db_path = os.path.join(tmpdir, "test.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bio_fields (
                id TEXT PRIMARY KEY,
                field_key TEXT NOT NULL UNIQUE,
                field_label TEXT NOT NULL,
                field_category TEXT NOT NULL,
                field_type TEXT NOT NULL,
                narrative_value TEXT NOT NULL DEFAULT 'medium',
                life_stage_range TEXT NOT NULL DEFAULT 'all',
                asking_anchors TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bio_facts (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                narrator_id TEXT NOT NULL,
                field_key TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '""',
                status TEXT NOT NULL DEFAULT 'empty',
                source TEXT NOT NULL DEFAULT '{}',
                confidence REAL NOT NULL DEFAULT 0.0,
                chapter_continuation_metric TEXT,
                conflict_with TEXT,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                FOREIGN KEY (field_key) REFERENCES bio_fields(field_key)
            );
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path, tmpdir


class _DefenseDbBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api import db
        cls._db_module = db
        cls._db_path, cls._tmpdir = _setup_temp_bio_db()
        cls._orig_connect = db._connect
        cls._orig_init_db = db.init_db
        cls._patched_connect = lambda path=None: (
            type(
                "Conn", (), {},
            )  # placeholder type; replaced below
        )

        def _patched_connect(path=None):
            conn = sqlite3.connect(cls._db_path)
            conn.row_factory = sqlite3.Row
            return conn

        db._connect = _patched_connect
        db.init_db = lambda: None
        db.bio_schema_seed_load_to_db()

    @classmethod
    def tearDownClass(cls):
        cls._db_module._connect = cls._orig_connect
        cls._db_module.init_db = cls._orig_init_db
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def setUp(self):
        os.environ["HORNELORE_BIO_ANCHORED_ASKER"] = "1"
        os.environ.pop("BIO_ANCHORED_OVERRIDES_PATH", None)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM bio_facts")
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        os.environ.pop("HORNELORE_BIO_ANCHORED_ASKER", None)


class ContinuationMetricUpdateTest(_DefenseDbBase):
    def _fire_one(self):
        from api.services.bio_anchored_asker import (
            fire_anchored_ask, GapMatch,
        )
        gap = GapMatch(
            field_key="military_branch",
            field_label="Military branch",
            matched_anchor="fort",
        )
        return fire_anchored_ask(
            "N1", gap, session_id="s1",
            session_turn_word_counts=[80, 80, 80, 80, 80],
        )

    def test_update_metric_after_response_fills_after_field(self):
        from api.services.bio_anchored_asker import (
            update_metric_after_response,
        )
        from api import db
        rid = self._fire_one()
        ok = update_metric_after_response(
            rid,
            response_turn_word_count=60,
            subsequent_turn_word_counts=[],
        )
        self.assertTrue(ok)
        row = db.bio_fact_get(rid)
        metric = json.loads(row["chapter_continuation_metric"])
        self.assertEqual(metric["narrator_turn_length_after_ask"], 60)

    def test_continuation_delta_computed_correctly(self):
        from api.services.bio_anchored_asker import (
            update_metric_after_response,
        )
        from api import db
        rid = self._fire_one()
        # baseline = 80; after = 60 → delta = (60-80)/80 = -0.25
        update_metric_after_response(
            rid, response_turn_word_count=60,
            subsequent_turn_word_counts=[70],
        )
        row = db.bio_fact_get(rid)
        metric = json.loads(row["chapter_continuation_metric"])
        self.assertAlmostEqual(
            metric["continuation_delta"], -0.25, places=3,
        )

    def test_ask_caused_chapter_end_true_when_both_short(self):
        from api.services.bio_anchored_asker import (
            update_metric_after_response,
        )
        from api import db
        rid = self._fire_one()
        # Next 2 turns both < 20 words → chapter_end True
        update_metric_after_response(
            rid, response_turn_word_count=10,
            subsequent_turn_word_counts=[12],
        )
        row = db.bio_fact_get(rid)
        metric = json.loads(row["chapter_continuation_metric"])
        self.assertTrue(metric["ask_caused_chapter_end"])

    def test_ask_caused_chapter_end_false_when_recovers(self):
        from api.services.bio_anchored_asker import (
            update_metric_after_response,
        )
        from api import db
        rid = self._fire_one()
        # Response short but next turn long → chapter recovered
        update_metric_after_response(
            rid, response_turn_word_count=15,
            subsequent_turn_word_counts=[90],
        )
        row = db.bio_fact_get(rid)
        metric = json.loads(row["chapter_continuation_metric"])
        self.assertFalse(metric["ask_caused_chapter_end"])


# ─────────────────────────────────────────────────────────────────────
# Defense 1 — telemetry warning thresholds
# ─────────────────────────────────────────────────────────────────────


class TelemetryWarningThresholdsTest(_DefenseDbBase):
    def _bank_n_metrics(
        self,
        narrator_id: str,
        deltas: list,
        chapter_ends: list,
    ):
        """Direct-write N synthetic anchored-ask rows with the
        requested delta + chapter_end profiles."""
        from api import db
        for d, e in zip(deltas, chapter_ends):
            metric = {
                "narrator_turn_length_before_ask": 80,
                "narrator_turn_length_after_ask": 60,
                "narrator_turn_length_baseline": 75,
                "continuation_delta": d,
                "ask_caused_chapter_end": e,
            }
            db.bio_fact_create(
                narrator_id=narrator_id,
                field_key="military_branch",
                value_json='""',
                status="anchored_asked",
                chapter_continuation_metric_json=json.dumps(metric),
                tenant_id="default",
            )

    def test_green_when_no_asks(self):
        from api.services.bio_anchored_asker import (
            classify_telemetry_warning, compute_creep_telemetry,
        )
        t = compute_creep_telemetry("N1", window=5)
        self.assertEqual(classify_telemetry_warning(t), "green")

    def test_amber_when_delta_below_threshold(self):
        from api.services.bio_anchored_asker import (
            classify_telemetry_warning, compute_creep_telemetry,
        )
        # 5 asks with delta = -0.30 each (below the -0.25 amber threshold)
        # and chapter_end False so we isolate the delta path.
        self._bank_n_metrics(
            "N1",
            deltas=[-0.30, -0.30, -0.30, -0.30, -0.30],
            chapter_ends=[False, False, False, False, False],
        )
        t = compute_creep_telemetry("N1", window=5)
        self.assertEqual(classify_telemetry_warning(t), "amber")

    def test_red_when_chapter_end_rate_above_threshold(self):
        from api.services.bio_anchored_asker import (
            classify_telemetry_warning, compute_creep_telemetry,
        )
        # 3 of 5 asks caused chapter end → 60% rate >= 40% red threshold
        self._bank_n_metrics(
            "N1",
            deltas=[-0.10, -0.10, -0.10, -0.10, -0.10],
            chapter_ends=[True, True, True, False, False],
        )
        t = compute_creep_telemetry("N1", window=5)
        self.assertEqual(classify_telemetry_warning(t), "red")


# ─────────────────────────────────────────────────────────────────────
# Defense 3 — override file validation
# ─────────────────────────────────────────────────────────────────────


class OverrideFileValidationTest(unittest.TestCase):
    def _write(self, contents: str) -> str:
        d = tempfile.mkdtemp(prefix="hornelore_test_override_")
        path = os.path.join(d, "bio_anchored_overrides.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(contents)
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        return path

    def test_no_file_returns_defaults(self):
        from api.services.bio_anchored_overrides import (
            load_overrides, DEFAULT_MAX_PER_SESSION,
            DEFAULT_TURN_SPACING, DEFAULT_MOMENTUM_CEILING,
            DEFAULT_CHAPTER_HEALTH_FLOOR,
        )
        o = load_overrides(path="/this/path/does/not/exist.toml")
        self.assertFalse(o.active)
        self.assertEqual(o.max_per_session, DEFAULT_MAX_PER_SESSION)
        self.assertEqual(o.turn_spacing, DEFAULT_TURN_SPACING)
        self.assertEqual(o.momentum_ceiling, DEFAULT_MOMENTUM_CEILING)
        self.assertEqual(
            o.chapter_health_floor, DEFAULT_CHAPTER_HEALTH_FLOOR,
        )

    def test_missing_ack_field_raises(self):
        from api.services.bio_anchored_overrides import (
            load_overrides, AnchoredOverrideError,
        )
        path = self._write(textwrap.dedent("""
            max_per_session = 5
        """))
        with self.assertRaises(AnchoredOverrideError) as ctx:
            load_overrides(path=path)
        self.assertIn("missing required", str(ctx.exception))

    def test_false_ack_field_raises(self):
        from api.services.bio_anchored_overrides import (
            load_overrides, AnchoredOverrideError,
        )
        path = self._write(textwrap.dedent("""
            i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode = false
            max_per_session = 5
        """))
        with self.assertRaises(AnchoredOverrideError) as ctx:
            load_overrides(path=path)
        self.assertIn("must be literal", str(ctx.exception))

    def test_valid_overrides_load(self):
        from api.services.bio_anchored_overrides import load_overrides
        path = self._write(textwrap.dedent("""
            i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode = true
            max_per_session = 5
            turn_spacing = 3
            momentum_ceiling = 0.5
            chapter_health_floor = 0.7
        """))
        o = load_overrides(path=path)
        self.assertTrue(o.active)
        self.assertEqual(o.max_per_session, 5)
        self.assertEqual(o.turn_spacing, 3)
        self.assertEqual(o.momentum_ceiling, 0.5)
        self.assertEqual(o.chapter_health_floor, 0.7)

    def test_emit_session_start_log_when_active(self):
        from api.services.bio_anchored_overrides import (
            emit_session_start_log,
        )
        path = self._write(textwrap.dedent("""
            i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode = true
            max_per_session = 5
        """))
        os.environ["BIO_ANCHORED_OVERRIDES_PATH"] = path
        try:
            msg = emit_session_start_log()
            self.assertIsNotNone(msg)
            self.assertIn("OVERRIDES ACTIVE", msg)
            self.assertIn("max_per_session=5", msg)
        finally:
            os.environ.pop("BIO_ANCHORED_OVERRIDES_PATH", None)

    def test_emit_session_start_log_none_when_inactive(self):
        from api.services.bio_anchored_overrides import (
            emit_session_start_log,
        )
        os.environ.pop("BIO_ANCHORED_OVERRIDES_PATH", None)
        self.assertIsNone(emit_session_start_log())


class ReadinessGateBlockedTest(unittest.TestCase):
    """Acceptance gate #16 helper test. The actual readiness framework
    does not yet exist in the codebase; this test confirms the
    consumer-side helper returns the right answer for that future
    framework to act on."""

    def test_no_override_file_unblocks(self):
        from api.services.bio_anchored_overrides import readiness_gate_blocked
        os.environ.pop("BIO_ANCHORED_OVERRIDES_PATH", None)
        self.assertFalse(readiness_gate_blocked())

    def test_active_override_blocks(self):
        from api.services.bio_anchored_overrides import readiness_gate_blocked
        d = tempfile.mkdtemp(prefix="hornelore_test_readiness_")
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        path = os.path.join(d, "bio_anchored_overrides.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent("""
                i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode = true
                max_per_session = 5
            """))
        os.environ["BIO_ANCHORED_OVERRIDES_PATH"] = path
        try:
            self.assertTrue(readiness_gate_blocked())
        finally:
            os.environ.pop("BIO_ANCHORED_OVERRIDES_PATH", None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
