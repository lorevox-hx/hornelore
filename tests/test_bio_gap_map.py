"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase F gap map tests.

Covers acceptance gate #10 (bio gap map displays correctly): per-narrator
completeness by category, recently asked surfacing, suggested asks
logic, conflict surfacing, creep telemetry rollup.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))


def _setup_temp_bio_db():
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_gap_map_")
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


class _GapMapDbBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api import db
        cls._db_module = db
        cls._db_path, cls._tmpdir = _setup_temp_bio_db()
        cls._orig_connect = db._connect
        cls._orig_init_db = db.init_db

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
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM bio_facts")
            conn.commit()
        finally:
            conn.close()


class CompletenessTest(_GapMapDbBase):
    def test_empty_narrator_zero_percent(self):
        from api.services.bio_gap_map import compute_completeness
        r = compute_completeness("N1")
        self.assertEqual(r.overall_percentage, 0.0)
        self.assertEqual(r.filled_fields, 0)
        self.assertGreater(r.total_fields, 0)  # seed populated

    def test_seeded_filled_field_counts(self):
        from api.services.bio_gap_map import compute_completeness
        from api import db
        # Seed two filled rows
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="approved", confidence=1.0,
        )
        db.bio_fact_create(
            narrator_id="N1", field_key="father_name",
            value_json=json.dumps("Frank"),
            status="document_sourced", confidence=1.0,
        )
        r = compute_completeness("N1")
        self.assertGreaterEqual(r.filled_fields, 2)
        # Per-category — identity should have at least 1, family at least 1
        cat_dict = {c.category: c for c in r.by_category}
        self.assertGreaterEqual(cat_dict["identity"].filled_fields, 1)
        self.assertGreaterEqual(cat_dict["family"].filled_fields, 1)

    def test_empty_status_does_not_count(self):
        from api.services.bio_gap_map import compute_completeness
        from api import db
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json='""', status="empty",
        )
        r = compute_completeness("N1")
        self.assertEqual(r.filled_fields, 0)

    def test_anchored_pending_does_not_count(self):
        from api.services.bio_gap_map import compute_completeness
        from api import db
        db.bio_fact_create(
            narrator_id="N1", field_key="military_branch",
            value_json='""',
            status="anchored_asked_pending",
        )
        r = compute_completeness("N1")
        self.assertEqual(r.filled_fields, 0)


class RecentlyAskedTest(_GapMapDbBase):
    def test_lists_tier_3_rows_only(self):
        from api.services.bio_gap_map import recently_asked
        from api import db
        # Tier 1 row (extractor) — should NOT surface in recently_asked
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="extracted_needs_verify",
            source_json=json.dumps({"tier": 1, "session_id": "s1"}),
        )
        # Tier 3 row (anchored ask) — SHOULD surface
        db.bio_fact_create(
            narrator_id="N1", field_key="military_branch",
            value_json='""',
            status="anchored_asked_pending",
            source_json=json.dumps({
                "tier": 3, "session_id": "s1",
                "matched_anchor": "fort",
            }),
        )
        items = recently_asked("N1")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].field_key, "military_branch")
        self.assertEqual(items[0].outcome, "pending")
        self.assertEqual(items[0].matched_anchor, "fort")


class SuggestedAsksTest(_GapMapDbBase):
    def test_high_value_gaps_appear(self):
        from api.services.bio_gap_map import suggested_asks
        s = suggested_asks("N1")
        # Seed has many high-value fields; none filled → all appear
        self.assertGreater(len(s), 10)
        for item in s:
            self.assertGreater(len(item.asking_anchors), 0)

    def test_filled_field_excluded(self):
        from api.services.bio_gap_map import suggested_asks
        from api import db
        db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="approved", confidence=1.0,
        )
        s = suggested_asks("N1")
        keys = {x.field_key for x in s}
        self.assertNotIn("birth_date", keys)

    def test_anchored_pending_treated_as_attempted(self):
        from api.services.bio_gap_map import suggested_asks
        from api import db
        db.bio_fact_create(
            narrator_id="N1", field_key="military_branch",
            value_json='""',
            status="anchored_asked_pending",
            source_json=json.dumps({"tier": 3}),
        )
        s = suggested_asks("N1")
        keys = {x.field_key for x in s}
        self.assertNotIn("military_branch", keys)

    def test_low_value_fields_never_suggested(self):
        from api.services.bio_gap_map import suggested_asks
        s = suggested_asks("N1")
        keys = {x.field_key for x in s}
        # narrative_value=low fields per seed
        for low in (
            "full_legal_name", "middle_name",
            "father_birth_year", "mother_birth_year",
            "parents_marriage_year",
        ):
            self.assertNotIn(low, keys)

    def test_sorted_by_category_then_key(self):
        from api.services.bio_gap_map import suggested_asks
        from api.services.bio_schema import FIELD_CATEGORIES
        s = suggested_asks("N1")
        cat_order = {c: i for i, c in enumerate(FIELD_CATEGORIES)}
        prev_cat_index = -1
        prev_key = ""
        for item in s:
            idx = cat_order[item.field_category]
            if idx == prev_cat_index:
                self.assertGreaterEqual(item.field_key, prev_key)
            else:
                self.assertGreater(idx, prev_cat_index)
            prev_cat_index = idx
            prev_key = item.field_key


class ConflictsListTest(_GapMapDbBase):
    def test_groups_by_field_key(self):
        from api.services.bio_gap_map import list_conflicts
        from api import db
        a = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1938"),
            status="conflicted",
        )
        b = db.bio_fact_create(
            narrator_id="N1", field_key="birth_date",
            value_json=json.dumps("1937"),
            status="conflicted",
            conflict_with=a,
        )
        conflicts = list_conflicts("N1")
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].field_key, "birth_date")
        self.assertEqual(len(conflicts[0].rows), 2)


class FullSummaryTest(_GapMapDbBase):
    def test_full_summary_shape(self):
        from api.services.bio_gap_map import full_summary
        s = full_summary("N1")
        for k in (
            "narrator_id", "completeness", "recently_asked",
            "suggested_asks", "suggested_asks_total",
            "conflicts", "creep_telemetry",
        ):
            self.assertIn(k, s)
        self.assertEqual(s["narrator_id"], "N1")

    def test_full_summary_caps_suggested_at_20(self):
        from api.services.bio_gap_map import full_summary
        s = full_summary("N1")
        # All high-value fields are unfilled — there are more than 20
        self.assertLessEqual(len(s["suggested_asks"]), 20)
        self.assertGreater(s["suggested_asks_total"], 20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
