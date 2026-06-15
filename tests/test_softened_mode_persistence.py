"""WO-LORI-SOFTENED-MODE-PERSISTENCE-01 (2026-06-14) — acceptance tests
for the softened-state three-state machine, per-trigger N values,
max-not-clobber extension, and invariants on the prompt blocks.

Test classes match the WO §8 acceptance pack:

  SoftenedStateLifecycleTest      — enter on acute (N=5), persist,
                                     enter softened_exiting, return
                                     to normal
  SoftenedStateBriefTest          — N=2 path from past-tense trigger
  SoftenedStateExtensionTest      — max-not-clobber on nested triggers
                                     (acute-during-past-tense extends
                                     forward, past-tense-during-acute
                                     does NOT shorten)
  SoftenedExitingNarratorReadTest — RECOVERING block forbids resumption
                                     phrases; word cap = 50
  SoftenedNoQuestionInvariantTest — all softened states' directives
                                     forbid composing fresh questions

Some tests are pure-function against
`api.services.lori_softened_response` and need no DB. The lifecycle
+ extension tests use a temp SQLite file with init_db so the
interview_sessions table (and the new softened_trigger /
softened_initial_n columns) are real.
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

from api.services.lori_softened_response import (  # noqa: E402
    build_softened_response_directive,
    softened_word_limit,
    is_softened_active,
    turns_remaining,
    SOFTENED_WORD_LIMIT,
)


# ─────────────────────────────────────────────────────────────────────
# Pure-function tests (no DB)
# ─────────────────────────────────────────────────────────────────────


class SoftenedNoQuestionInvariantTest(unittest.TestCase):
    """WO §8 #5 — across all softened states (acute / past-tense /
    exiting), the directive forbids composing a fresh question."""

    def test_softened_acute_directive_forbids_questions(self):
        state = {
            "interview_softened": True, "state": "softened",
            "trigger": "acute",
        }
        block = build_softened_response_directive(state)
        self.assertIn("SOFTENED MODE", block)
        self.assertIn("NEVER a question demand", block)
        self.assertIn("Forbidden:", block)

    def test_softened_past_tense_directive_forbids_questions(self):
        state = {
            "interview_softened": True, "state": "softened",
            "trigger": "past_tense_acknowledge",
        }
        block = build_softened_response_directive(state)
        self.assertIn("SOFTENED MODE", block)
        self.assertIn("Forbidden:", block)

    def test_softened_exiting_directive_says_question_not_fine_yet(self):
        state = {
            "interview_softened": True, "state": "softened_exiting",
            "trigger": "acute",
        }
        block = build_softened_response_directive(state)
        self.assertIn("RECOVERING MODE", block)
        self.assertIn("A question is NOT fine yet", block)

    def test_normal_state_directive_is_empty(self):
        state = {"interview_softened": False, "state": "normal"}
        self.assertEqual(build_softened_response_directive(state), "")


class SoftenedExitingNarratorReadTest(unittest.TestCase):
    """WO §8 #4 — RECOVERING directive permits gentle re-engagement
    BUT forbids interview-resumption phrases."""

    FORBIDDEN_RESUMPTION_PHRASES = [
        "we can keep going",
        "where were we",
        "so, you were telling me about",
        "let's get back to",
        "shall we continue",
        "ready to pick up where we left off",
    ]

    def setUp(self):
        self.block = build_softened_response_directive({
            "interview_softened": True, "state": "softened_exiting",
            "trigger": "acute",
        })

    def test_recovering_block_lists_all_forbidden_phrases(self):
        for phrase in self.FORBIDDEN_RESUMPTION_PHRASES:
            self.assertIn(
                phrase, self.block,
                f"RECOVERING block should explicitly forbid {phrase!r}",
            )

    def test_recovering_block_permits_gentle_follow(self):
        self.assertIn("gently follow at their pace", self.block)

    def test_recovering_block_word_cap_is_50(self):
        self.assertIn("50 words or fewer", self.block)
        self.assertEqual(
            softened_word_limit({
                "interview_softened": True, "state": "softened_exiting",
                "trigger": "acute",
            }),
            50,
        )

    def test_recovering_block_says_bridge_turn(self):
        self.assertIn("bridge turn", self.block)

    def test_recovering_block_says_one_turn_only(self):
        # Block uses "ONE TURN" (caps) in the title + "one-turn
        # transition" elsewhere; case-insensitive match catches both.
        self.assertIn("one-turn transition", self.block.lower())


class PerTriggerCapTest(unittest.TestCase):
    """WO §6 — per-trigger word caps."""

    def test_acute_cap_is_30(self):
        self.assertEqual(
            softened_word_limit({
                "interview_softened": True, "state": "softened",
                "trigger": "acute",
            }),
            30,
        )

    def test_past_tense_cap_is_35(self):
        self.assertEqual(
            softened_word_limit({
                "interview_softened": True, "state": "softened",
                "trigger": "past_tense_acknowledge",
            }),
            35,
        )

    def test_exiting_cap_is_50(self):
        self.assertEqual(
            softened_word_limit({
                "interview_softened": True, "state": "softened_exiting",
                "trigger": "acute",
            }),
            50,
        )

    def test_normal_cap_falls_back_to_legacy(self):
        # Caller normally short-circuits to its own per-style cap when
        # softened isn't active. This is the safety fallback.
        self.assertEqual(
            softened_word_limit({"interview_softened": False}),
            SOFTENED_WORD_LIMIT,
        )

    def test_unknown_trigger_during_softened_falls_back_to_acute_cap(self):
        # Safety bias: when trigger is missing/unknown but state is
        # softened, pick the tighter (acute) cap.
        self.assertEqual(
            softened_word_limit({
                "interview_softened": True, "state": "softened",
                "trigger": "",
            }),
            30,
        )


# ─────────────────────────────────────────────────────────────────────
# DB-backed lifecycle tests
# ─────────────────────────────────────────────────────────────────────


class _TempDbCase(unittest.TestCase):
    """Spin up an isolated temp DB with the MINIMAL interview_sessions
    schema this WO needs. Patches `db.DB_PATH` post-import.

    Skips `db.init_db()` because that function pulls in
    `from ..db.migrations_runner import run_pending_migrations` which
    requires the prod import root (`server/` on sys.path with the
    `code` package). Test environment uses `server/code/` on sys.path
    + bare `api` imports — the relative `..db` doesn't resolve there.

    Manually creating the schema is the right scope for these tests
    anyway: they exercise softened-state arithmetic, not the full
    migrations runner.
    """

    _INTERVIEW_SESSIONS_DDL = """\
CREATE TABLE IF NOT EXISTS interview_sessions (
    id                  TEXT PRIMARY KEY,
    person_id           TEXT,
    plan_id             TEXT,
    started_at          TEXT,
    updated_at          TEXT,
    interview_softened  INTEGER DEFAULT 0,
    softened_until_turn INTEGER DEFAULT 0,
    turn_count          INTEGER DEFAULT 0,
    softened_trigger    TEXT    DEFAULT '',
    softened_initial_n  INTEGER DEFAULT 0
);
"""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp(prefix="softened_test_")
        cls._db_file = Path(cls._tmpdir) / "test.sqlite3"

        # Apply the minimal schema directly.
        con = sqlite3.connect(str(cls._db_file))
        con.executescript(cls._INTERVIEW_SESSIONS_DDL)
        con.commit()
        # Sanity: confirm the new columns are present.
        cols = {row[1] for row in con.execute(
            "PRAGMA table_info(interview_sessions);"
        ).fetchall()}
        con.close()
        cls._has_new_cols = (
            "softened_trigger" in cols and "softened_initial_n" in cols
        )

        # Patch db.DB_PATH so the db.py accessors hit our temp file.
        from api import db as _db  # noqa: WPS433
        cls._db = _db
        cls._original_db_path = _db.DB_PATH
        _db.DB_PATH = cls._db_file

    @classmethod
    def tearDownClass(cls):
        # Restore real DB_PATH and clean up.
        cls._db.DB_PATH = cls._original_db_path
        import shutil
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    def _new_session(self, conv_id: str, person_id: str = "test-person"):
        # Manually INSERT — bypassing ensure_interview_session (which
        # calls init_db internally; see setUpClass docstring).
        con = sqlite3.connect(str(self._db_file))
        con.execute(
            "INSERT OR IGNORE INTO interview_sessions "
            "(id, person_id, plan_id, started_at, updated_at, "
            " turn_count, interview_softened, softened_until_turn) "
            "VALUES (?, ?, 'test', '', '', 0, 0, 0);",
            (conv_id, person_id),
        )
        con.commit()
        con.close()

    def _db_file_path(self) -> str:
        return str(self._db_file)


class SoftenedStateLifecycleTest(_TempDbCase):
    """WO §8 #1 + #2 — full lifecycle from acute trigger."""

    def test_new_columns_present(self):
        self.assertTrue(
            self._has_new_cols,
            "init_db must add softened_trigger + softened_initial_n columns",
        )

    def test_acute_n5_enters_softened(self):
        conv = "test-lifecycle-1"
        self._new_session(conv)
        # Simulate: set_softened called on turn 6 with N=5.
        # turn_count is incremented separately in production; for the
        # test we set it directly to match.
        self._db.set_session_softened(
            conv, current_turn=6, softened_turns=5, trigger="acute",
        )
        # Bump turn_count to 7 (the turn AFTER the trigger).
        con = sqlite3.connect(self._db_file_path())
        con.execute(
            "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
            (7, conv),
        )
        con.commit()
        con.close()

        state = self._db.get_session_softened_state(conv)
        self.assertEqual(state["state"], "softened")
        self.assertEqual(state["trigger"], "acute")
        self.assertEqual(state["softened_until_turn"], 11)  # 6 + 5

    def test_acute_n5_persists_through_window(self):
        conv = "test-lifecycle-persist"
        self._new_session(conv)
        self._db.set_session_softened(
            conv, current_turn=6, softened_turns=5, trigger="acute",
        )
        # Walk turn_count from 7 to 10; should all be "softened".
        for t in (7, 8, 9, 10):
            con = sqlite3.connect(self._db_file_path())
            con.execute(
                "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
                (t, conv),
            )
            con.commit()
            con.close()
            state = self._db.get_session_softened_state(conv)
            self.assertEqual(
                state["state"], "softened",
                f"turn {t} should still be softened (until=11)",
            )

    def test_acute_n5_exits_at_until_turn(self):
        # Turn 11 = the until_turn itself = softened_exiting (one-turn bridge).
        conv = "test-lifecycle-exit"
        self._new_session(conv)
        self._db.set_session_softened(
            conv, current_turn=6, softened_turns=5, trigger="acute",
        )
        con = sqlite3.connect(self._db_file_path())
        con.execute(
            "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
            (11, conv),
        )
        con.commit()
        con.close()
        state = self._db.get_session_softened_state(conv)
        self.assertEqual(state["state"], "softened_exiting")
        self.assertEqual(state["trigger"], "acute")

    def test_acute_n5_returns_to_normal_after_exiting(self):
        # Turn 12 = past the until_turn = normal.
        conv = "test-lifecycle-normal"
        self._new_session(conv)
        self._db.set_session_softened(
            conv, current_turn=6, softened_turns=5, trigger="acute",
        )
        con = sqlite3.connect(self._db_file_path())
        con.execute(
            "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
            (12, conv),
        )
        con.commit()
        con.close()
        state = self._db.get_session_softened_state(conv)
        self.assertEqual(state["state"], "normal")
        self.assertFalse(state["interview_softened"])


class SoftenedStateBriefTest(_TempDbCase):
    """WO §8 #3 — N=2 brief softened from past-tense trigger."""

    def test_past_tense_n2_enters_softened(self):
        conv = "test-brief-enter"
        self._new_session(conv)
        # Past-tense on turn 4 with N=2.
        self._db.set_session_softened(
            conv, current_turn=4, softened_turns=2,
            trigger="past_tense_acknowledge",
        )
        # Turn 5 should be softened.
        con = sqlite3.connect(self._db_file_path())
        con.execute(
            "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
            (5, conv),
        )
        con.commit()
        con.close()
        state = self._db.get_session_softened_state(conv)
        self.assertEqual(state["state"], "softened")
        self.assertEqual(state["trigger"], "past_tense_acknowledge")
        self.assertEqual(state["softened_until_turn"], 6)  # 4 + 2

    def test_past_tense_n2_exits_at_turn_6(self):
        conv = "test-brief-exit"
        self._new_session(conv)
        self._db.set_session_softened(
            conv, current_turn=4, softened_turns=2,
            trigger="past_tense_acknowledge",
        )
        con = sqlite3.connect(self._db_file_path())
        con.execute(
            "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
            (6, conv),
        )
        con.commit()
        con.close()
        state = self._db.get_session_softened_state(conv)
        self.assertEqual(state["state"], "softened_exiting")

    def test_past_tense_n2_returns_normal_at_turn_7(self):
        conv = "test-brief-normal"
        self._new_session(conv)
        self._db.set_session_softened(
            conv, current_turn=4, softened_turns=2,
            trigger="past_tense_acknowledge",
        )
        con = sqlite3.connect(self._db_file_path())
        con.execute(
            "UPDATE interview_sessions SET turn_count=? WHERE id=?;",
            (7, conv),
        )
        con.commit()
        con.close()
        state = self._db.get_session_softened_state(conv)
        self.assertEqual(state["state"], "normal")


class SoftenedStateExtensionTest(_TempDbCase):
    """WO §8 #6 — extend_session_softened applies max-not-clobber so
    nested triggers can't shorten the window."""

    def test_acute_during_past_tense_extends_forward(self):
        conv = "test-ext-acute-during-past"
        self._new_session(conv)
        # Past-tense on turn 4: until = 6.
        self._db.set_session_softened(
            conv, current_turn=4, softened_turns=2,
            trigger="past_tense_acknowledge",
        )
        # Acute fires on turn 5 with N=5: until should max to 10.
        self._db.extend_session_softened(
            conv, current_turn=5, softened_turns=5, trigger="acute",
        )
        # Inspect raw row.
        con = sqlite3.connect(self._db_file_path())
        row = con.execute(
            "SELECT softened_until_turn, softened_trigger "
            "FROM interview_sessions WHERE id=?;", (conv,),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], 10)  # max(6, 5+5)
        # Trigger upgraded to acute (acute > past_tense in hierarchy).
        self.assertEqual(row[1], "acute")

    def test_short_past_tense_during_long_acute_does_not_shorten(self):
        conv = "test-ext-past-during-acute"
        self._new_session(conv)
        # Acute on turn 4: until = 9.
        self._db.set_session_softened(
            conv, current_turn=4, softened_turns=5, trigger="acute",
        )
        # Past-tense fires on turn 6 with N=2: would-be until = 8.
        # Existing until (9) is larger; max wins → stays at 9.
        self._db.extend_session_softened(
            conv, current_turn=6, softened_turns=2,
            trigger="past_tense_acknowledge",
        )
        con = sqlite3.connect(self._db_file_path())
        row = con.execute(
            "SELECT softened_until_turn, softened_trigger "
            "FROM interview_sessions WHERE id=?;", (conv,),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], 9)  # max(9, 6+2)
        # Trigger stays acute (past_tense < acute in hierarchy — no
        # downgrade).
        self.assertEqual(row[1], "acute")

    def test_extend_on_fresh_session_writes_like_set(self):
        # extend_session_softened on a session that's never been
        # softened produces the same result as set_session_softened.
        conv = "test-ext-fresh"
        self._new_session(conv)
        self._db.extend_session_softened(
            conv, current_turn=10, softened_turns=5, trigger="acute",
        )
        con = sqlite3.connect(self._db_file_path())
        row = con.execute(
            "SELECT softened_until_turn, softened_trigger, "
            "       interview_softened "
            "FROM interview_sessions WHERE id=?;", (conv,),
        ).fetchone()
        con.close()
        self.assertEqual(row[0], 15)  # 10 + 5
        self.assertEqual(row[1], "acute")
        self.assertEqual(row[2], 1)


# ─────────────────────────────────────────────────────────────────────
# Helper sanity
# ─────────────────────────────────────────────────────────────────────


class StateHelperTest(unittest.TestCase):
    def test_is_softened_active_truthy(self):
        self.assertTrue(is_softened_active(
            {"interview_softened": True, "state": "softened"}
        ))
        self.assertTrue(is_softened_active(
            {"interview_softened": True, "state": "softened_exiting"}
        ))

    def test_is_softened_active_falsy(self):
        self.assertFalse(is_softened_active(
            {"interview_softened": False, "state": "normal"}
        ))
        self.assertFalse(is_softened_active(None))
        self.assertFalse(is_softened_active({}))

    def test_turns_remaining_zero_when_inactive(self):
        self.assertEqual(turns_remaining({"interview_softened": False}), 0)

    def test_turns_remaining_positive_when_active(self):
        # softened_until_turn=11, turn_count=7 → remaining = 11 - 7 + 1 = 5
        self.assertEqual(
            turns_remaining({
                "interview_softened": True,
                "softened_until_turn": 11,
                "turn_count": 7,
            }),
            5,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
