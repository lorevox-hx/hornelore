"""WO-LORI-STORY-FIRST-PHASE-1-01 (2026-06-14) — thread bank tests.

Covers acceptance gate #3: thread extraction (3 sources, dedupe),
DB persistence with anchor-open-exists dedup, surfacing selection
(age + mode + closing marker gates), response evaluation.

Uses an in-memory sqlite DB via monkey-patching db._DEFAULT_DB_PATH
so we don't touch the real hornelore.sqlite. The schema is built by
running init_db() against the temp DB.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.services.thread_bank import (  # noqa: E402
    CLOSING_MARKERS,
    DECLINATION_PATTERNS,
    DEFAULT_SURFACING_MIN_AGE_TURNS,
    ThreadCandidate,
    bank_new_threads,
    build_surfacing_text,
    evaluate_response_to_surfaced_thread,
    extract_thread_candidates,
    select_surfacing_target,
)


# ─────────────────────────────────────────────────────────────────────
# Pure-extraction tests (no DB)
# ─────────────────────────────────────────────────────────────────────

WO_FAILURE_MODE_C_TEXT = (
    "We came from Germany when my grandmother was very sick. "
    "The train ride was long, and the church choir back home — "
    "I can still hear them — they sang the whole way to the station."
)


class ThreadCandidateExtractionTest(unittest.TestCase):
    def test_wo_failure_mode_c_extracts_four_threads(self):
        # Per WO §3 — this exact text must produce ≥4 trackable threads.
        cands = extract_thread_candidates(WO_FAILURE_MODE_C_TEXT, source_turn_index=0)
        # We expect: Germany, your grandmother, the train ride, the church choir
        anchors = [c.anchor.lower() for c in cands]
        self.assertGreaterEqual(len(cands), 4)
        self.assertIn("germany", anchors)
        self.assertIn("your grandmother", anchors)
        self.assertIn("the train ride", anchors)
        self.assertIn("the church choir", anchors)

    def test_wo_failure_mode_c_categories_correct(self):
        cands = {c.anchor.lower(): c.category for c in
                 extract_thread_candidates(WO_FAILURE_MODE_C_TEXT)}
        self.assertEqual(cands.get("germany"), "place")
        self.assertEqual(cands.get("your grandmother"), "person")
        self.assertEqual(cands.get("the train ride"), "event")
        self.assertEqual(cands.get("the church choir"), "object")

    def test_extraction_excerpts_populated(self):
        cands = extract_thread_candidates(WO_FAILURE_MODE_C_TEXT)
        for c in cands:
            self.assertTrue(c.excerpt, f"Empty excerpt for anchor={c.anchor}")

    def test_empty_text_returns_no_candidates(self):
        self.assertEqual(extract_thread_candidates(""), [])
        self.assertEqual(extract_thread_candidates(None), [])

    def test_extraction_dedupes_same_anchor(self):
        # "Spokane" mentioned twice — should yield one candidate
        text = "I grew up in Spokane. Spokane was a small town then."
        cands = extract_thread_candidates(text)
        spokane_count = sum(1 for c in cands if c.anchor.lower() == "spokane")
        self.assertEqual(spokane_count, 1)

    def test_extraction_caps_at_8(self):
        # Build a pathological turn with many anchors
        text = " ".join(f"Place{i} was lovely." for i in range(20))
        cands = extract_thread_candidates(text)
        self.assertLessEqual(len(cands), 8)

    def test_kinship_anchor_canonicalized(self):
        # "my dad" → "your father"
        cands = extract_thread_candidates("My dad ran the bakery.")
        anchors = [c.anchor for c in cands]
        self.assertIn("your father", anchors)

    def test_event_noun_in_definite_np_categorized_as_event(self):
        cands = extract_thread_candidates("The wedding was in June.")
        wedding = [c for c in cands if c.anchor == "the wedding"]
        self.assertEqual(len(wedding), 1)
        self.assertEqual(wedding[0].category, "event")


# ─────────────────────────────────────────────────────────────────────
# DB persistence tests
# ─────────────────────────────────────────────────────────────────────


def _setup_temp_db_with_threads_table():
    """Build a temp sqlite file with just the interview_threads table.
    We don't run init_db() because that drags the full schema in; the
    bank only needs interview_threads."""
    tmpdir = tempfile.mkdtemp(prefix="hornelore_test_thread_bank_")
    db_path = os.path.join(tmpdir, "test.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS interview_threads (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                thread_anchor TEXT NOT NULL,
                source_turn_index INTEGER NOT NULL DEFAULT 0,
                source_excerpt TEXT,
                category TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                introduced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                surfaced_at TEXT,
                resolved_at TEXT,
                tenant_id TEXT NOT NULL DEFAULT 'default'
            );
            CREATE INDEX IF NOT EXISTS idx_threads_session_status
                ON interview_threads(session_id, status);
            CREATE INDEX IF NOT EXISTS idx_threads_introduced_at
                ON interview_threads(introduced_at);
        """)
        conn.commit()
    finally:
        conn.close()
    return db_path, tmpdir


class _DbBackedThreadTest(unittest.TestCase):
    """Base class that monkey-patches db._connect to use a temp file."""

    @classmethod
    def setUpClass(cls):
        from api import db  # noqa: F401 — import after sys.path fix
        cls._db_module = db
        cls._db_path, cls._tmpdir = _setup_temp_db_with_threads_table()
        cls._orig_default_path = getattr(db, "_DEFAULT_DB_PATH", None)
        # Best-effort path override; if db uses a different attr name
        # we fall back to patching _connect.
        if hasattr(db, "_DEFAULT_DB_PATH"):
            db._DEFAULT_DB_PATH = cls._db_path
        cls._orig_connect = db._connect
        cls._orig_init_db = db.init_db

        def _patched_connect(path=None):
            import sqlite3 as _sql
            conn = _sql.connect(cls._db_path)
            conn.row_factory = _sql.Row
            return conn

        def _patched_init_db():
            # Test fixture pre-built interview_threads with the same
            # schema mirror. The real init_db builds dozens of unrelated
            # tables we don't need and would only obscure errors. No-op.
            return None

        db._connect = _patched_connect
        db.init_db = _patched_init_db

    @classmethod
    def tearDownClass(cls):
        cls._db_module._connect = cls._orig_connect
        cls._db_module.init_db = cls._orig_init_db
        if cls._orig_default_path is not None:
            cls._db_module._DEFAULT_DB_PATH = cls._orig_default_path
        try:
            import shutil
            shutil.rmtree(cls._tmpdir, ignore_errors=True)
        except Exception:
            pass

    def setUp(self):
        # Clear table between tests
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("DELETE FROM interview_threads")
            conn.commit()
        finally:
            conn.close()


class BankNewThreadsTest(_DbBackedThreadTest):
    def test_persists_candidates(self):
        cands = extract_thread_candidates(WO_FAILURE_MODE_C_TEXT, source_turn_index=2)
        ids = bank_new_threads("session_x", cands)
        self.assertEqual(len(ids), len(cands))
        for tid in ids:
            self.assertTrue(tid)

    def test_anchor_open_exists_dedup_skips_duplicate(self):
        cands = extract_thread_candidates(WO_FAILURE_MODE_C_TEXT, source_turn_index=2)
        first_round = bank_new_threads("session_x", cands)
        self.assertGreater(len(first_round), 0)
        # Second round with same anchors should write nothing new
        second_round = bank_new_threads("session_x", cands)
        self.assertEqual(second_round, [])

    def test_empty_candidate_list_returns_empty(self):
        self.assertEqual(bank_new_threads("session_x", []), [])

    def test_empty_session_id_returns_empty(self):
        cands = extract_thread_candidates(WO_FAILURE_MODE_C_TEXT)
        self.assertEqual(bank_new_threads("", cands), [])

    def test_candidate_with_empty_anchor_skipped(self):
        c = ThreadCandidate(anchor="", excerpt="x", category="other",
                            source_turn_index=0)
        self.assertEqual(bank_new_threads("session_x", [c]), [])


# ─────────────────────────────────────────────────────────────────────
# Surfacing selection tests
# ─────────────────────────────────────────────────────────────────────


class SurfacingTargetTest(_DbBackedThreadTest):
    def _bank_one(self, session_id, anchor, source_turn_index):
        c = ThreadCandidate(
            anchor=anchor,
            excerpt=f"... {anchor} ...",
            category="person",
            source_turn_index=source_turn_index,
        )
        return bank_new_threads(session_id, [c])

    def test_story_mode_suppresses_surfacing(self):
        self._bank_one("s_story", "your grandmother", 0)
        target = select_surfacing_target(
            "s_story", current_turn_index=10, momentum_mode="story",
        )
        self.assertIsNone(target)

    def test_emerging_mode_without_closing_marker_suppresses(self):
        self._bank_one("s_em", "your grandmother", 0)
        target = select_surfacing_target(
            "s_em", current_turn_index=10, momentum_mode="emerging",
            narrator_text="I was just remembering the war years.",
        )
        self.assertIsNone(target)

    def test_emerging_mode_with_closing_marker_allows_surfacing(self):
        self._bank_one("s_emc", "your grandmother", 0)
        target = select_surfacing_target(
            "s_emc", current_turn_index=10, momentum_mode="emerging",
            narrator_text="Anyway, that's about all I remember.",
        )
        self.assertIsNotNone(target)
        self.assertEqual(target["thread_anchor"], "your grandmother")

    def test_normal_mode_picks_oldest_eligible(self):
        # Two threads, oldest at turn 0, newer at turn 2. Current turn
        # is 5, min_age is 3 → only turn 0 is eligible.
        self._bank_one("s_old", "your grandmother", 0)
        self._bank_one("s_old", "germany", 4)  # NOT yet old enough
        target = select_surfacing_target(
            "s_old", current_turn_index=5, momentum_mode="normal",
        )
        self.assertIsNotNone(target)
        self.assertEqual(target["thread_anchor"], "your grandmother")

    def test_no_eligible_thread_when_all_too_young(self):
        self._bank_one("s_young", "your grandmother", 4)
        target = select_surfacing_target(
            "s_young", current_turn_index=5, momentum_mode="normal",
        )
        self.assertIsNone(target)

    def test_empty_session_id_returns_none(self):
        self.assertIsNone(select_surfacing_target("", 5, "normal"))


# ─────────────────────────────────────────────────────────────────────
# Pure helper tests
# ─────────────────────────────────────────────────────────────────────


class BuildSurfacingTextTest(unittest.TestCase):
    def test_template_shape(self):
        thread = {"thread_anchor": "your grandmother", "id": "abc"}
        text = build_surfacing_text(thread, "What was she like?", 0)
        self.assertIn("Earlier you mentioned your grandmother.", text)
        self.assertIn("What was she like?", text)

    def test_uses_connecting_phrase_from_bank(self):
        thread = {"thread_anchor": "Germany"}
        text = build_surfacing_text(thread, "What stands out?", 0)
        # The 0-index phrase per the module
        self.assertIn("I keep thinking about it.", text)

    def test_empty_thread_returns_empty(self):
        self.assertEqual(build_surfacing_text({}), "")
        self.assertEqual(build_surfacing_text(None), "")
        self.assertEqual(build_surfacing_text({"thread_anchor": ""}), "")

    def test_phrase_index_wraps(self):
        thread = {"thread_anchor": "X"}
        a = build_surfacing_text(thread, "?", 0)
        b = build_surfacing_text(thread, "?", 5)  # wraps around
        self.assertEqual(a, b)


class ResponseEvaluationTest(unittest.TestCase):
    def test_substantive_response_resolves(self):
        text = (
            "Yes, my grandmother was a stern woman. She wore the same "
            "navy-blue dress every day, and she used to read aloud from "
            "the Bible in German before bed. I remember the smell of "
            "her coffee in the morning especially clearly."
        )
        self.assertEqual(evaluate_response_to_surfaced_thread(text), "resolved")

    def test_declination_phrase_declines(self):
        for p in DECLINATION_PATTERNS:
            with self.subTest(p=p):
                # Make sure the substring is long enough to exceed the
                # word floor on its own, isolating the phrase test
                text = f"Well, {p} right now if that's okay."
                self.assertEqual(
                    evaluate_response_to_surfaced_thread(text),
                    "declined",
                )

    def test_short_response_declines(self):
        self.assertEqual(
            evaluate_response_to_surfaced_thread("Not much."), "declined",
        )

    def test_empty_response_declines(self):
        self.assertEqual(evaluate_response_to_surfaced_thread(""), "declined")
        self.assertEqual(evaluate_response_to_surfaced_thread(None), "declined")

    def test_medium_response_unclear(self):
        # 12 words, no declination phrase → unclear
        text = "She lived next door to us for nearly twenty years before moving."
        self.assertEqual(evaluate_response_to_surfaced_thread(text), "unclear")


class ConstantsExportedTest(unittest.TestCase):
    def test_closing_markers_nonempty(self):
        self.assertGreater(len(CLOSING_MARKERS), 0)
        for m in CLOSING_MARKERS:
            self.assertEqual(m, m.lower())

    def test_declination_patterns_nonempty(self):
        self.assertGreater(len(DECLINATION_PATTERNS), 0)
        for p in DECLINATION_PATTERNS:
            self.assertEqual(p, p.lower())

    def test_default_surfacing_min_age_sensible(self):
        self.assertGreaterEqual(DEFAULT_SURFACING_MIN_AGE_TURNS, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
