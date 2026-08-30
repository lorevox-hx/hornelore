"""Presentation identity is not the concurrency version. Migration 0052.

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_presentation_epoch

── THE DEFECT THIS FILE EXISTS FOR ───────────────────────────────────

`plan_turn` correlated a narrator's answer with Lori's question using
`(topic_id, version)`, where `version` is the onboarding row's
optimistic-concurrency counter. `resolve_effective` moves that counter
on every durable change, which includes two events that leave the
narrator looking at exactly the same question:

  * a pause and a resume — a shipped operator control;
  * an evidence write for SOME OTHER topic, from Bio Builder or from
    extraction.

After either, the outstanding `(siblings, 5)` no longer equalled the
current `(siblings, 7)`, the STALE branch fired, and Lori asked about
siblings a second time while the narrator's answer was discarded — no
response event, no disposition applied.

For a system whose narrators may have cognitive decline, being asked the
same question twice and told nothing about the answer you already gave
is not a cosmetic defect. It is the product failing at the thing it
exists to do.

── WHAT IS PINNED HERE ───────────────────────────────────────────────

Each test is one of the discriminating cases required for acceptance,
and each is written to FAIL against the pre-0052 reducer rather than to
describe the new one. Two use the real database so the resolver's own
epoch arithmetic is exercised rather than a hand-built dict.
"""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services import profile_seed as _seed        # noqa: E402
from api.services import profile_seed_turn as _turn   # noqa: E402

TOPICS = _seed.TOPIC_IDS
A = TOPICS[0]
B = TOPICS[1]


# ── in-memory fixtures ──────────────────────────────────────────────────
def state(*, active=A, version, epoch, status=_seed.STATUS_ACTIVE,
          remaining=None):
    remaining = list(TOPICS) if remaining is None else list(remaining)
    return {"person_id": "p1", "enrolled": True, "status": status,
            "active_topic_id": active, "version": version,
            "presentation_epoch": epoch,
            "topic_state": {t: _seed.UNANSWERED for t in remaining},
            "known_topics": [t for t in TOPICS if t not in remaining],
            "remaining_topics": remaining}


def presented(topic, version, epoch):
    return {"role": "assistant", "content": "…",
            "meta": {_turn.PRESENTED_TOPIC: topic,
                     _turn.PRESENTED_VERSION: version,
                     _turn.PRESENTED_EPOCH: epoch}}


def responded(topic, version, epoch, disposition=_seed.ADDRESSED):
    return {"role": "assistant", "content": "…",
            "meta": {_turn.RESPONSE_TOPIC: topic,
                     _turn.RESPONSE_VERSION: version,
                     _turn.RESPONSE_EPOCH: epoch,
                     _turn.RESPONSE_DISPOSITION: disposition}}


def said(text="Devils Lake, North Dakota."):
    return {"role": "user", "content": text, "meta": {}}


ANSWER = "Two brothers and a sister."


class PauseResumeTests(unittest.TestCase):
    """CASE 1 — the acceptance blocker, stated exactly."""

    def test_pause_and_resume_do_not_re_interrogate(self):
        """The version moved. The question did not. The answer counts.

        Against the pre-0052 reducer this planned RE_PRESENT, and the
        narrator was asked about their siblings for a second time.
        """
        history = [presented(A, 5, 2), said(ANSWER)]
        # Pause bumped 5 -> 6, resume bumped 6 -> 7. The epoch is
        # untouched: the same question was outstanding throughout.
        plan = _turn.plan_turn(state=state(version=7, epoch=2),
                               history=history, narrator_text=ANSWER)
        self.assertEqual(
            plan.action, _turn.ACKNOWLEDGE,
            "a pause and resume made Lori re-ask a question the narrator "
            "had already answered")
        self.assertTrue(plan.advances)
        self.assertEqual(plan.topic_id, A)
        self.assertEqual(plan.disposition, _seed.ADDRESSED)

    def test_the_acknowledgement_writes_with_the_CURRENT_version(self):
        """Not the version the question was stamped with.

        The epoch has already proved this is the same question. Writing
        with the stale version would make every pause/resume a 409 and
        lose the disposition — the same defect one layer down.
        """
        history = [presented(A, 5, 2), said(ANSWER)]
        plan = _turn.plan_turn(state=state(version=7, epoch=2),
                               history=history, narrator_text=ANSWER)
        self.assertEqual(plan.version, 7)
        self.assertEqual(plan.epoch, 2)


class EvidenceDriftTests(unittest.TestCase):
    """CASE 2 — an unrelated write, with no operator action on the walk."""

    def test_evidence_for_another_topic_does_not_re_interrogate(self):
        """The quieter half of the defect, and the more dangerous one.

        Nobody touched the walk. An operator entered a fact in Bio
        Builder, or an extraction wrote one, some OTHER topic flipped
        `unanswered -> known`, and the row version moved. The narrator's
        answer to the question actually on screen stopped counting.
        """
        history = [presented(A, 5, 2), said(ANSWER)]
        plan = _turn.plan_turn(
            state=state(version=6, epoch=2,
                        remaining=[t for t in TOPICS if t != B]),
            history=history, narrator_text=ANSWER)
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        self.assertEqual(plan.topic_id, A)


class GenuineAdvanceTests(unittest.TestCase):
    """CASE 3 — the protection that must SURVIVE the fix."""

    def test_a_real_topic_advance_rejects_the_stale_response(self):
        history = [presented(A, 5, 2), said(), responded(A, 5, 2)]
        plan = _turn.plan_turn(state=state(active=B, version=6, epoch=3),
                               history=history, narrator_text=ANSWER)
        self.assertEqual(plan.action, _turn.PRESENT)
        self.assertEqual(plan.topic_id, B)
        self.assertFalse(plan.advances)

    def test_an_answer_to_the_previous_question_cannot_close_the_new_one(self):
        """Non-vacuity for the case above: the stale event is present
        and outstanding, and it still does not advance."""
        history = [presented(B, 6, 3), said(), responded(B, 5, 2)]
        outstanding = _turn.outstanding_presentation(history)
        self.assertIsNotNone(outstanding)
        self.assertEqual(outstanding.tuple, (B, 3))


class ReopenedTopicTests(unittest.TestCase):
    """CASE 4 — a settled topic that later reopens is a NEW question."""

    def test_a_reopened_topic_gets_a_new_epoch_and_is_asked_again(self):
        history = [presented(A, 5, 2), said(), responded(A, 5, 2)]
        # A was settled at epoch 2. The evidence that settled it was
        # removed, A is active again, and the resolver minted epoch 4.
        plan = _turn.plan_turn(state=state(active=A, version=9, epoch=4),
                               history=history, narrator_text=ANSWER)
        # ASKS rather than acknowledges. Which asking action it is
        # depends only on whether an outstanding presentation survived —
        # here the old response consumed the old presentation, so it is
        # PRESENT. The property under test is that the narrator's earlier
        # answer does not silently close the reopened question.
        self.assertIn(
            plan.action, (_turn.PRESENT, _turn.RE_PRESENT),
            "a reopened topic reused its old answer instead of asking")
        self.assertEqual(plan.epoch, 4)
        self.assertFalse(plan.advances)
        self.assertEqual(plan.response_meta(), {})


class RecoveryTests(unittest.TestCase):
    """CASE 5 — a failed post-commit apply recovers on the same epoch."""

    def test_recovery_retries_across_a_version_move(self):
        """The response committed; the apply did not land; the version
        then moved. Before 0052 `recover` compared the version, called
        it superseded, and owed nothing — so the narrator was asked a
        question whose answer was committed one row above."""
        history = [presented(A, 5, 2), said(), responded(A, 5, 2)]
        applied = []

        def resolve(_pid):
            return state(version=7, epoch=2)

        def apply(pid, *, expected_version, action, topic_id):
            applied.append((pid, expected_version, action, topic_id))

        outcome = _turn.recover("p1", history, resolve_fn=resolve,
                                apply_fn=apply)
        self.assertEqual(outcome.status, _turn.RETRIED)
        self.assertEqual(
            applied, [("p1", 7, _seed.ADDRESSED, A)],
            "the retry used the stamped version rather than the current "
            "one, which is a guaranteed 409")

    def test_recovery_owes_nothing_once_the_question_has_moved_on(self):
        history = [presented(A, 5, 2), said(), responded(A, 5, 2)]
        outcome = _turn.recover(
            "p1", history,
            resolve_fn=lambda _p: state(active=B, version=6, epoch=3),
            apply_fn=lambda *a, **k: self.fail("applied onto a new question"))
        self.assertEqual(outcome.status, _turn.NOTHING_OWED)


class LegacyMetadataTests(unittest.TestCase):
    """CASE 7 — pre-0052 rows, handled explicitly rather than vanishing."""

    def _legacy_presented(self, topic, version):
        return {"role": "assistant", "content": "…",
                "meta": {_turn.PRESENTED_TOPIC: topic,
                         _turn.PRESENTED_VERSION: version}}

    def _legacy_responded(self, topic, version):
        return {"role": "assistant", "content": "…",
                "meta": {_turn.RESPONSE_TOPIC: topic,
                         _turn.RESPONSE_VERSION: version,
                         _turn.RESPONSE_DISPOSITION: _seed.ADDRESSED}}

    def test_a_legacy_presentation_is_read_not_dropped(self):
        event = _turn.event_from_meta(
            self._legacy_presented(A, 5)["meta"])
        self.assertIsNotNone(event, "a pre-0052 row disappeared silently")
        self.assertTrue(event.is_legacy)
        self.assertIsNone(event.epoch)
        self.assertEqual(event.version, 5)

    def test_a_legacy_presentation_re_presents_exactly_once(self):
        """The deliberate one-time cost at the migration boundary.

        Asking once more is the safe direction: the alternative is
        acknowledging an answer against a question identity that was
        never minted.
        """
        history = [self._legacy_presented(A, 5), said(ANSWER)]
        plan = _turn.plan_turn(state=state(version=6, epoch=1),
                               history=history, narrator_text=ANSWER)
        self.assertEqual(plan.action, _turn.RE_PRESENT)
        self.assertEqual(plan.epoch, 1)

        # And the very next answer correlates normally, so the cost is
        # one question and not a loop.
        history = history + [presented(A, 6, 1), said(ANSWER)]
        plan = _turn.plan_turn(state=state(version=6, epoch=1),
                               history=history, narrator_text=ANSWER)
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)

    def test_a_legacy_response_owes_no_recovery(self):
        """It cannot prove which question it answered."""
        history = [self._legacy_responded(A, 5)]
        outcome = _turn.recover(
            "p1", history,
            resolve_fn=lambda _p: state(version=5, epoch=1),
            apply_fn=lambda *a, **k: self.fail(
                "a pre-0052 response was forced onto a live question"))
        self.assertEqual(outcome.status, _turn.NOTHING_OWED)

    def test_an_active_walk_with_no_epoch_holds_rather_than_idling(self):
        """IDLE would hand the walk back to the browser, which is the one
        outcome a corrupt epoch must not produce."""
        plan = _turn.plan_turn(
            state={"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                   "active_topic_id": A, "version": 7,
                   "presentation_epoch": None,
                   "remaining_topics": list(TOPICS)},
            history=[], narrator_text="Hello")
        self.assertEqual(plan.action, _turn.HOLD)

    def test_a_boolean_epoch_is_not_epoch_one(self):
        """`isinstance(True, int)` is True in Python."""
        self.assertIsNone(_turn._valid_epoch(True))
        self.assertIsNone(_turn._valid_epoch(False))
        self.assertEqual(_turn._valid_epoch(1), 1)


# ── The resolver's own arithmetic, against a real database ──────────────
class _Db:
    """The smallest schema `resolve_effective` needs, plus 0051 + 0052."""

    def __init__(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.executescript("""
            CREATE TABLE people (
                id TEXT PRIMARY KEY, display_name TEXT,
                date_of_birth TEXT, place_of_birth TEXT);
            CREATE TABLE profile_seed_onboarding (
                person_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                topic_state_json TEXT NOT NULL DEFAULT '{}',
                active_topic_id TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                presentation_epoch INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                completed_at TEXT);
            -- The four evidence sources the resolver reads. Empty, so
            -- every topic is `unanswered` and the walk actually walks.
            -- They must EXIST: the readers deliberately do not catch
            -- sqlite3.Error, because a storage fault must never look
            -- like "this narrator has answered nothing".
            CREATE TABLE profiles (person_id TEXT PRIMARY KEY,
                                   profile_json TEXT);
            CREATE TABLE interview_projections (person_id TEXT PRIMARY KEY,
                                                projection_json TEXT);
            CREATE TABLE bio_facts (narrator_id TEXT, field_key TEXT,
                                    value TEXT, status TEXT,
                                    last_updated TEXT);
        """)

    def narrator(self, pid="p1"):
        self.con.execute(
            "INSERT INTO people (id, display_name, date_of_birth, "
            "place_of_birth) VALUES (?,?,?,?);",
            (pid, "ZZ Epoch Probe", "1948-01-11", "Boston"))
        _seed.enroll(self.con, pid, now="t0")
        return pid

    def row(self, pid="p1"):
        return _seed.read_row(self.con, pid)


class ResolverEpochTests(unittest.TestCase):
    """The arithmetic itself, not a hand-built dict."""

    def setUp(self):
        self.db = _Db()
        self.pid = self.db.narrator()

    def _reconcile(self, now):
        state = _seed.reconcile(self.db.con, self.pid, now=now)
        self.db.con.commit()
        return state

    def test_enrollment_starts_at_epoch_zero(self):
        """A pending row has no question outstanding. 0 says so."""
        self.assertEqual(self.db.row()["presentation_epoch"], 0)

    def test_first_activation_mints_epoch_one(self):
        state = self._reconcile("t1")
        self.assertEqual(state.status, _seed.STATUS_ACTIVE)
        self.assertEqual(state.presentation_epoch, 1)

    def test_a_second_resolve_changes_nothing(self):
        first = self._reconcile("t1")
        second = self._reconcile("t2")
        self.assertEqual(second.presentation_epoch, 1)
        self.assertEqual(second.version, first.version,
                         "a read that discovered nothing moved the version")

    def test_pause_and_resume_move_the_version_and_not_the_epoch(self):
        """THE ACCEPTANCE BLOCKER, at the resolver."""
        active = self._reconcile("t1")

        _seed.set_paused(self.db.con, self.pid, paused=True, now="t2")
        paused = self._reconcile("t2")
        self.assertEqual(paused.status, _seed.STATUS_PAUSED)
        self.assertEqual(paused.presentation_epoch, 1)
        self.assertEqual(
            paused.active_topic_id, active.active_topic_id,
            "the pause discarded the outstanding topic, which is what "
            "made resume look like a new question")

        _seed.set_paused(self.db.con, self.pid, paused=False, now="t3")
        resumed = self._reconcile("t3")
        self.assertEqual(resumed.status, _seed.STATUS_ACTIVE)
        self.assertEqual(
            resumed.presentation_epoch, 1,
            "resuming minted a new question identity, so the narrator "
            "would be asked the same thing again")
        self.assertGreater(resumed.version, active.version,
                           "the concurrency version stopped moving, which "
                           "would break the write guard")

    def test_advancing_a_topic_mints_a_new_epoch(self):
        first = self._reconcile("t1")
        _seed.apply_disposition(self.db.con, self.pid,
                                topic_id=first.active_topic_id,
                                disposition=_seed.ADDRESSED, now="t2")
        second = self._reconcile("t2")
        self.assertNotEqual(second.active_topic_id, first.active_topic_id)
        self.assertEqual(second.presentation_epoch, 2)

    def test_a_completed_walk_carries_its_epoch_rather_than_resetting(self):
        state = self._reconcile("t1")
        for topic in TOPICS:
            _seed.apply_disposition(self.db.con, self.pid, topic_id=topic,
                                    disposition=_seed.ADDRESSED, now="t2")
        done = self._reconcile("t2")
        self.assertEqual(done.status, _seed.STATUS_COMPLETED)
        self.assertGreaterEqual(done.presentation_epoch,
                                state.presentation_epoch)

    def test_the_api_body_exposes_the_epoch(self):
        body = self._reconcile("t1").as_dict()
        self.assertEqual(body["presentation_epoch"], 1)

    def test_a_historical_narrator_reports_a_null_epoch(self):
        """`None`, not 0 — never enrolled is not "enrolled, not started"."""
        body = _seed.not_enrolled_body("nobody")
        self.assertIsNone(body["presentation_epoch"])
        self.assertFalse(body["enrolled"])


class MigrationTests(unittest.TestCase):
    """CASE 6 — backfill, and what it must not do."""

    MIGRATION = (_REPO_ROOT / "server" / "code" / "db" / "migrations"
                 / "0052_profile_seed_presentation_epoch.sql")

    def _pre_0052(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.executescript("""
            CREATE TABLE people (id TEXT PRIMARY KEY);
            CREATE TABLE profile_seed_onboarding (
                person_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                topic_state_json TEXT NOT NULL DEFAULT '{}',
                active_topic_id TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                completed_at TEXT);
        """)
        for pid, status in (("pend", "pending"), ("act", "active"),
                            ("paus", "paused"), ("done", "completed")):
            con.execute("INSERT INTO people (id) VALUES (?);", (pid,))
            con.execute(
                "INSERT INTO profile_seed_onboarding "
                "(person_id, status, topic_state_json, version, "
                " created_at, updated_at) VALUES (?,?,'{}',4,'t','t');",
                (pid, status))
        # A narrator who was never enrolled: no onboarding row at all.
        con.execute("INSERT INTO people (id) VALUES ('historical');")
        con.commit()
        return con

    def test_the_backfill_gives_live_walks_an_epoch(self):
        con = self._pre_0052()
        con.executescript(self.MIGRATION.read_text(encoding="utf-8"))
        rows = {r["person_id"]: r["presentation_epoch"] for r in con.execute(
            "SELECT person_id, presentation_epoch FROM profile_seed_onboarding;")}
        self.assertEqual(rows["act"], 1)
        self.assertEqual(rows["paus"], 1)
        self.assertEqual(rows["pend"], 0)
        self.assertEqual(rows["done"], 0)

    def test_the_migration_enrolls_nobody(self):
        """The standing decision on historical narrators, as a test.

        An ALTER TABLE adds a column to rows that already exist. A
        narrator with no onboarding row still has none afterwards.
        """
        con = self._pre_0052()
        before = con.execute(
            "SELECT COUNT(*) FROM profile_seed_onboarding;").fetchone()[0]
        con.executescript(self.MIGRATION.read_text(encoding="utf-8"))
        after = con.execute(
            "SELECT COUNT(*) FROM profile_seed_onboarding;").fetchone()[0]
        self.assertEqual(before, after)
        self.assertIsNone(con.execute(
            "SELECT 1 FROM profile_seed_onboarding WHERE person_id='historical';"
        ).fetchone())

    def test_the_backfill_does_not_touch_the_concurrency_version(self):
        con = self._pre_0052()
        con.executescript(self.MIGRATION.read_text(encoding="utf-8"))
        for row in con.execute(
                "SELECT person_id, version FROM profile_seed_onboarding;"):
            self.assertEqual(row["version"], 4, row["person_id"])


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
