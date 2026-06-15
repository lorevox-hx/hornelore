"""WO-LORI-BIO-BUILDER-UNIVERSAL-01 (2026-06-14) — Phase D Tier 3 tests.

Covers acceptance gates #6 (Tier 3 fires only when conditions met),
#7 (session frequency cap honored), #8 (Tier 3 never fires for
low-narrative-value fields). The chapter health floor (Defense 2)
test class belongs here too — separately surfaced because the
creep-defense file covers Defenses 1 + 3 + telemetry warnings.
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
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_bio_asker_")
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


class _AskerDbBase(unittest.TestCase):
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
        # Asker is off by default; tests turn it on explicitly via env.
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


# ─────────────────────────────────────────────────────────────────────
# Env flag test (lightweight; no DB)
# ─────────────────────────────────────────────────────────────────────


class AskerEnabledFlagTest(unittest.TestCase):
    def test_default_off(self):
        from api.services.bio_anchored_asker import asker_enabled
        os.environ.pop("HORNELORE_BIO_ANCHORED_ASKER", None)
        self.assertFalse(asker_enabled())

    def test_on_when_flag_set(self):
        from api.services.bio_anchored_asker import asker_enabled
        os.environ["HORNELORE_BIO_ANCHORED_ASKER"] = "1"
        try:
            self.assertTrue(asker_enabled())
        finally:
            os.environ.pop("HORNELORE_BIO_ANCHORED_ASKER", None)


# ─────────────────────────────────────────────────────────────────────
# Eligibility chain tests
# ─────────────────────────────────────────────────────────────────────


class EligibilityMomentumGateTest(_AskerDbBase):
    def test_high_momentum_blocks_ask(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.8,
            session_turn_word_counts=[],
            turns_since_last_ask=999,
            asks_this_session=0,
        )
        self.assertFalse(r.eligible)
        self.assertIn("momentum_too_high", r.reason)

    def test_low_momentum_allows_ask(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=[],
            turns_since_last_ask=999,
            asks_this_session=0,
        )
        self.assertTrue(r.eligible)

    def test_momentum_exactly_at_ceiling_blocks(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        # Ceiling default 0.4 — >= blocks per the spec rule
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.4,
            session_turn_word_counts=[],
            turns_since_last_ask=999,
            asks_this_session=0,
        )
        self.assertFalse(r.eligible)


class EligibilityRateLimitTest(_AskerDbBase):
    def test_turn_spacing_violation_blocks(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=[],
            turns_since_last_ask=2,  # below default 4
            asks_this_session=0,
        )
        self.assertFalse(r.eligible)
        self.assertIn("turn_spacing_violation", r.reason)

    def test_session_cap_reached_blocks(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=[],
            turns_since_last_ask=10,
            asks_this_session=3,  # default cap = 3
        )
        self.assertFalse(r.eligible)
        self.assertIn("session_cap_reached", r.reason)

    def test_one_below_cap_allows(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=[],
            turns_since_last_ask=10,
            asks_this_session=2,
        )
        self.assertTrue(r.eligible)


class EligibilityChapterHealthFloorTest(_AskerDbBase):
    """Defense 2 — chapter exhaustion blocks asks regardless of count."""

    def test_floor_violation_blocks(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        # First 5 turns averaged ~80 words; last 5 average ~20 words.
        # Ratio 0.25 << floor 0.8 → block.
        word_counts = [80, 80, 80, 80, 80] + [20, 20, 20, 20, 20]
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=word_counts,
            turns_since_last_ask=10,
            asks_this_session=0,
        )
        self.assertFalse(r.eligible)
        self.assertIn("chapter_health_floor_violated", r.reason)

    def test_healthy_session_passes_floor(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        # Last 5 ≈ first 5 → ratio ≈ 1.0 >> floor 0.8.
        word_counts = [80, 80, 80, 80, 80] + [85, 90, 75, 80, 80]
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=word_counts,
            turns_since_last_ask=10,
            asks_this_session=0,
        )
        self.assertTrue(r.eligible)

    def test_insufficient_turns_skips_check(self):
        from api.services.bio_anchored_asker import evaluate_eligibility
        # Fewer than 5 turns — can't compute floor, pass through.
        r = evaluate_eligibility(
            narrator_id="N1",
            momentum_score=0.2,
            session_turn_word_counts=[50, 60],
            turns_since_last_ask=10,
            asks_this_session=0,
        )
        self.assertTrue(r.eligible)


# ─────────────────────────────────────────────────────────────────────
# Gap selection tests
# ─────────────────────────────────────────────────────────────────────


class GapSelectionTest(_AskerDbBase):
    def test_match_military_branch_on_fort_anchor(self):
        from api.services.bio_anchored_asker import pick_anchored_gap
        gap = pick_anchored_gap(
            "N1", "I was stationed at Fort Ord for almost two years.",
        )
        self.assertIsNotNone(gap)
        self.assertEqual(gap.field_key, "military_branch")
        self.assertIn(gap.matched_anchor, ("fort", "army", "stationed at"))

    def test_no_match_when_text_lacks_anchors(self):
        from api.services.bio_anchored_asker import pick_anchored_gap
        gap = pick_anchored_gap(
            "N1", "It was a beautiful day today, the sun was warm.",
        )
        self.assertIsNone(gap)

    def test_filled_field_no_longer_a_gap(self):
        from api.services.bio_anchored_asker import pick_anchored_gap
        from api import db
        # Seed a row that fills military_branch
        db.bio_fact_create(
            narrator_id="N1", field_key="military_branch",
            value_json=json.dumps("Army"),
            status="extracted_needs_verify",
        )
        gap = pick_anchored_gap(
            "N1", "I was stationed at Fort Ord.",
        )
        # military_branch was filled → not eligible. Returns None
        # (no other gap matches "Fort Ord" precisely — military_locations
        # might match "stationed at" but it's a separate field).
        # Defensive check: if SOME other field matches, it must NOT
        # be military_branch.
        if gap is not None:
            self.assertNotEqual(gap.field_key, "military_branch")

    def test_no_match_for_low_value_fields(self):
        from api.services.bio_anchored_asker import pick_anchored_gap
        # narrative_value=low fields have empty asking_anchors per the
        # seed invariant — so even if a generic substring would match,
        # the asker should never propose them. This validates the
        # principle structurally via the seed rather than text-matching.
        gap = pick_anchored_gap(
            "N1", "My full legal name is something something.",
        )
        if gap is not None:
            self.assertNotIn(gap.field_key, (
                "full_legal_name", "middle_name",
                "father_birth_year", "mother_birth_year",
                "parents_marriage_year",
            ))

    def test_empty_narrator_text_returns_none(self):
        from api.services.bio_anchored_asker import pick_anchored_gap
        self.assertIsNone(pick_anchored_gap("N1", ""))
        self.assertIsNone(pick_anchored_gap("N1", None))


# ─────────────────────────────────────────────────────────────────────
# Composition tests
# ─────────────────────────────────────────────────────────────────────


class CompositionTest(unittest.TestCase):
    def test_surface_text_includes_field_label(self):
        from api.services.bio_anchored_asker import (
            compose_surface_text, GapMatch,
        )
        gap = GapMatch(
            field_key="military_branch",
            field_label="Military branch",
            matched_anchor="fort",
        )
        text = compose_surface_text(gap, "I was at Fort Ord.")
        self.assertIn("military branch", text.lower())
        self.assertIn("'fort'", text)

    def test_surface_text_forbids_generic_phrasing(self):
        # The directive must instruct the LLM toward chapter-natural
        # composition, NOT generic questionnaire phrasing.
        from api.services.bio_anchored_asker import (
            compose_surface_text, GapMatch,
        )
        gap = GapMatch(
            field_key="military_branch",
            field_label="Military branch",
            matched_anchor="boot camp",
        )
        text = compose_surface_text(gap, "Boot camp was tough.")
        # The composition guidance explicitly says "NOT a generic
        # questionnaire item" — verify the phrase is present in
        # the operator-visible directive.
        self.assertIn("NOT a generic", text)


# ─────────────────────────────────────────────────────────────────────
# fire_anchored_ask — placeholder row creation
# ─────────────────────────────────────────────────────────────────────


class FireAnchoredAskTest(_AskerDbBase):
    def test_fires_writes_placeholder_row(self):
        from api.services.bio_anchored_asker import (
            fire_anchored_ask, GapMatch,
        )
        from api import db
        gap = GapMatch(
            field_key="military_branch",
            field_label="Military branch",
            matched_anchor="fort",
        )
        rid = fire_anchored_ask(
            "N1", gap,
            session_id="s1", turn_id="t1",
            session_turn_word_counts=[60, 80, 70],
        )
        self.assertTrue(rid)
        row = db.bio_fact_get(rid)
        self.assertEqual(row["status"], "anchored_asked_pending")
        self.assertEqual(row["field_key"], "military_branch")
        src = json.loads(row["source"])
        self.assertEqual(src["tier"], 3)
        self.assertEqual(src["matched_anchor"], "fort")

    def test_metric_scaffold_populated(self):
        from api.services.bio_anchored_asker import (
            fire_anchored_ask, GapMatch,
        )
        from api import db
        gap = GapMatch(
            field_key="military_branch",
            field_label="Military branch",
            matched_anchor="fort",
        )
        rid = fire_anchored_ask(
            "N1", gap,
            session_id="s1",
            session_turn_word_counts=[60, 80, 70, 90, 75],
        )
        row = db.bio_fact_get(rid)
        metric = json.loads(row["chapter_continuation_metric"])
        # before = avg of last 3 = (70+90+75)/3 ≈ 78
        self.assertEqual(
            metric["narrator_turn_length_before_ask"], 78,
        )
        # baseline = session avg = (60+80+70+90+75)/5 = 75
        self.assertEqual(
            metric["narrator_turn_length_baseline"], 75,
        )
        # after / delta / chapter_end null at fire-time
        self.assertIsNone(metric["narrator_turn_length_after_ask"])
        self.assertIsNone(metric["continuation_delta"])
        self.assertIsNone(metric["ask_caused_chapter_end"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
