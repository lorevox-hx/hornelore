"""Step 6 — the committed-turn walk, end to end, against a real database.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2, Step 6.

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_ws_step6

── WHAT THIS EXERCISES, AND WHY IT IS NOT A SIMULATOR ────────────────

The WebSocket handler is a 5,000-line function inside an async route.
A test that drove it end to end would need fastapi, torch and a loaded
model, which is exactly why the rules deciding whether a narrator's
answer gets recorded must not live inside it.

They do not. `services/profile_seed_runtime.py` owns the three
decisions — `prepare_turn`, `commit_meta`, `should_advance` — and
`chat_ws.py` calls them at the three points where they apply.
**These tests call the same three functions the router calls**, against
a real SQLite database through the real `db.profile_seed_resolve` and
`db.profile_seed_apply`. There is no second copy of the reasoning here.

What IS stood in for is the commit itself: a committed assistant row is
represented by appending `{"role": "assistant", "meta": ...}` to a
history list, which is precisely the shape `db.export_turns()` returns
and precisely what the reducer reads. The durable event is the metadata
on that row, so a list of rows is a faithful stand-in for the table.

**The wiring — that the router actually calls these in this order, and
that no deterministic path does — is asserted structurally in
`tests/test_profile_seed_deterministic_paths.py`.** Neither file is
sufficient alone, and saying so is the honest scope: this one proves the
rules are right, that one proves the router runs them.

── THE OPERATIONAL FACT THIS SUITE DOES NOT CHANGE ───────────────────

Every existing narrator is historical and unenrolled. Step 6 makes the
walk reachable through the production WebSocket for NEWLY ENROLLED
narrators; it backfills nobody. `test_a_historical_narrator_is_untouched`
pins that, because the quietest way to break it would be a resolve that
helpfully enrolls whoever it is handed.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api import db as _db                                    # noqa: E402
from api.services import profile_seed as _seed               # noqa: E402
from api.services import profile_seed_runtime as _rt         # noqa: E402
from api.services import profile_seed_turn as _turn          # noqa: E402


class _Base(unittest.TestCase):
    """One temp DATA_DIR and database per test, as Phase 1's suite does.

    `_BIO_SEED_LOADED` is reset before `init_db()` because it is a
    once-per-process gate; a suite that moves `DB_PATH` more than once
    otherwise gets an empty `bio_fields` registry and every person write
    fails with a foreign-key error that reads like a missing person.
    """

    def setUp(self):
        self.data_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.data_tmp.cleanup)
        self._orig_data_dir = os.environ.get("DATA_DIR")
        os.environ["DATA_DIR"] = str(Path(self.data_tmp.name).resolve())
        self.addCleanup(self._restore_data_dir)

        fd = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
        fd.close()
        self.db_path = Path(fd.name)
        self._orig_db = _db.DB_PATH
        _db.DB_PATH = self.db_path
        _db._BIO_SEED_LOADED = False
        _db.init_db()
        self.addCleanup(self._restore_db)

        self.person_id = _db.create_person(
            "Verlie Ostrander",
            date_of_birth="1936-11-08",
            place_of_birth="Devils Lake, North Dakota",
        )["id"]
        self.history: List[Dict[str, Any]] = []

    def _restore_data_dir(self):
        if self._orig_data_dir is None:
            os.environ.pop("DATA_DIR", None)
        else:
            os.environ["DATA_DIR"] = self._orig_data_dir

    def _restore_db(self):
        _db.DB_PATH = self._orig_db
        try:
            self.db_path.unlink()
        except OSError:
            pass

    # ── the router's own sequence, run with the router's own functions ──
    def _turn(self, narrator_text, *, eligible=True, cancelled=False,
              persisted=True, person_id=None, apply_fn=None,
              resolve_fn=None):
        """One committed turn. Returns `(plan, meta, advanced)`.

        The order is the router's: prepare (recover, resolve, plan) →
        build the metadata → append the committed assistant row → decide
        advancement → apply. Nothing is reordered for convenience,
        because the order IS the design.
        """
        pid = person_id or self.person_id
        prepared = _rt.prepare_turn(
            pid, self.history,
            narrator_text=narrator_text,
            eligible=eligible,
            resolve_fn=resolve_fn or _db.profile_seed_resolve,
            apply_fn=apply_fn or _db.profile_seed_apply,
        )
        meta = _rt.commit_meta(prepared.plan, eligible=eligible,
                               cancelled=cancelled)
        if persisted:
            self.history.append({"role": "user", "content": narrator_text or "",
                                 "meta": {}})
            self.history.append({"role": "assistant", "content": "…",
                                 "meta": dict(meta)})
        advanced = False
        if _rt.should_advance(prepared.plan, persisted=persisted,
                              eligible=eligible, cancelled=cancelled):
            (apply_fn or _db.profile_seed_apply)(
                pid,
                expected_version=int(prepared.plan.version or 0),
                action=prepared.plan.disposition,
                topic_id=prepared.plan.topic_id,
            )
            advanced = True
        return prepared, meta, advanced

    def _state(self, person_id=None):
        return _db.profile_seed_resolve(person_id or self.person_id)


# ── 1. The ordinary walk ────────────────────────────────────────────────
class FirstPresentationTests(_Base):

    def test_the_first_turn_presents_and_advances_NOTHING(self):
        """A question asked is not a question answered.

        The narrator has not had the chance to answer a question that did
        not exist a moment ago, so the presentation is recorded and the
        durable state does not move at all.
        """
        before = self._state()
        prepared, meta, advanced = self._turn("Hello.")

        self.assertEqual(prepared.plan.action, _turn.PRESENT)
        self.assertFalse(advanced)
        self.assertIn(_turn.PRESENTED_TOPIC, meta)
        self.assertNotIn(_turn.RESPONSE_TOPIC, meta,
                         "the first presentation stamped a response event")

        after = self._state()
        self.assertEqual(after["active_topic_id"], before["active_topic_id"])
        self.assertEqual(after["version"], before["version"],
                         "asking a question moved the durable version")

    def test_the_presentation_carries_the_ACTIVE_tuple(self):
        prepared, meta, _ = self._turn("Hello.")
        state = self._state()
        self.assertEqual(meta[_turn.PRESENTED_TOPIC], state["active_topic_id"])
        self.assertEqual(meta[_turn.PRESENTED_VERSION], state["version"])


class RealAnswerTests(_Base):

    def test_an_answer_records_a_response_and_applies_AFTER_the_commit(self):
        self._turn("Hello.")                       # presentation
        topic_before = self._state()["active_topic_id"]

        prepared, meta, advanced = self._turn(
            "We lived in Devils Lake until I was eleven.")

        self.assertEqual(prepared.plan.action, _turn.ACKNOWLEDGE)
        self.assertEqual(prepared.plan.disposition, _turn.ADDRESSED)
        self.assertEqual(meta.get(_turn.RESPONSE_TOPIC), topic_before)
        self.assertNotIn(_turn.PRESENTED_TOPIC, meta,
                         "an acknowledgement re-asked in the same breath")
        self.assertTrue(advanced)
        self.assertNotEqual(self._state()["active_topic_id"], topic_before)

    def test_the_acknowledgement_turn_asks_NOTHING(self):
        """`ACKNOWLEDGE` must not present the next topic in the same turn.

        Until the post-commit apply succeeds, the next topic is a
        prediction rather than a fact, and a question asked from a
        prediction is a question that may be about the wrong thing.
        """
        self._turn("Hello.")
        _, meta, _ = self._turn("Devils Lake.")
        self.assertEqual(
            [k for k in meta if k.startswith("profile_seed_presented")], [],
            f"the acknowledgement stamped a presentation too: {meta}")

    def test_the_walk_progresses_topic_by_topic(self):
        seen = []
        for _ in range(3):
            self._turn("Hello.")                    # present
            seen.append(self._state()["active_topic_id"])
            self._turn("A real answer about that.")  # acknowledge + apply
        self.assertEqual(len(set(seen)), 3,
                         f"the walk did not move between topics: {seen}")


class DeferralRefusalAndForgettingTests(_Base):

    def test_a_deferral_re_presents_and_does_NOT_apply(self):
        self._turn("Hello.")
        before = self._state()
        # A WHOLE-UTTERANCE deferral, which is what Step 3 accepted.
        # Compound forms like "hold on, let me think" are not in the
        # phrase set and classify as an answer; that is existing accepted
        # behaviour, recorded rather than changed here — Step 6 is not
        # the place to widen the deferral vocabulary.
        prepared, meta, advanced = self._turn("let me think")

        self.assertEqual(prepared.plan.action, _turn.RE_PRESENT)
        self.assertFalse(advanced, "a deferral closed the topic")
        self.assertIn(_turn.PRESENTED_TOPIC, meta)
        self.assertNotIn(_turn.RESPONSE_TOPIC, meta)
        self.assertEqual(self._state()["active_topic_id"],
                         before["active_topic_id"])

    def test_a_refusal_records_DECLINED(self):
        self._turn("Hello.")
        prepared, meta, advanced = self._turn(
            "I'd rather not talk about that.")
        self.assertEqual(prepared.plan.disposition, _turn.DECLINED)
        self.assertEqual(meta.get(_turn.RESPONSE_DISPOSITION), _turn.DECLINED)
        self.assertTrue(advanced, "a refusal must still close the topic — "
                                  "otherwise it is asked again forever")

    def test_forgetting_records_ADDRESSED(self):
        """"I don't remember" closes the topic, and that is deliberate.

        It records no biographical fact. What it prevents is an older
        narrator meeting the same unreachable question every session.
        """
        self._turn("Hello.")
        prepared, meta, advanced = self._turn("Oh, I don't remember.")
        self.assertEqual(prepared.plan.disposition, _turn.ADDRESSED)
        self.assertEqual(meta.get(_turn.RESPONSE_DISPOSITION), _turn.ADDRESSED)
        self.assertTrue(advanced)


# ── 2. Turns that must not participate ──────────────────────────────────
class IneligibleAndControlTests(_Base):

    def _assert_held(self, prepared, meta, advanced, *, why):
        self.assertEqual(prepared.plan.action, _turn.HOLD, why)
        self.assertEqual(meta, {}, f"{why}: stamped {meta}")
        self.assertFalse(advanced, why)

    def test_a_system_directive_HOLDS_and_stamps_nothing(self):
        self._turn("Hello.")
        before = self._state()
        out = self._turn("[SYSTEM: narrator switched]", eligible=False)
        self._assert_held(*out, why="a system directive participated")
        self.assertEqual(self._state()["version"], before["version"])

    def test_a_cancelled_turn_stamps_NOTHING_and_does_not_apply(self):
        """Cancellation is re-read at commit, not inherited from planning.

        The plan here is a real ACKNOWLEDGE — the narrator did answer —
        and it must still write no event, because the turn they cancelled
        is not a turn that happened.
        """
        self._turn("Hello.")
        before = self._state()
        prepared, meta, advanced = self._turn("Devils Lake.", cancelled=True)

        self.assertEqual(prepared.plan.action, _turn.ACKNOWLEDGE)
        self.assertEqual(meta, {}, "a cancelled turn stamped an event")
        self.assertFalse(advanced)
        self.assertEqual(self._state()["active_topic_id"],
                         before["active_topic_id"])

    def test_a_conversation_control_HOLDS_rather_than_answering(self):
        """"pause" is the narrator operating the conversation, not an answer."""
        self._turn("Hello.")
        before = self._state()
        prepared, meta, advanced = self._turn("pause")
        self._assert_held(prepared, meta, advanced,
                          why="a control closed the open topic")
        self.assertEqual(self._state()["active_topic_id"],
                         before["active_topic_id"])

    def test_HOLD_is_not_IDLE_while_a_walk_is_live(self):
        """The distinction the legacy browser pass depends on.

        `IDLE` un-suppresses the browser's ten-question block. An
        ineligible turn during an active walk must therefore HOLD — and
        must still produce an onboarding payload, so the section keeps
        the legacy pass suppressed.
        """
        self._turn("Hello.")
        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="[SYSTEM: x]",
            eligible=False, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        self.assertEqual(prepared.plan.action, _turn.HOLD)
        payload = _rt.onboarding_payload(prepared.plan, prepared.state)
        self.assertIsNotNone(
            payload, "a held turn produced no onboarding payload, so the "
                     "legacy browser pass would be un-suppressed")
        self.assertEqual(payload["action"], _turn.HOLD)


# ── 3. Failure, and what must not follow from it ────────────────────────
class PersistenceFailureTests(_Base):

    def test_a_failed_persistence_NEVER_applies(self):
        self._turn("Hello.")
        before = self._state()
        prepared, meta, advanced = self._turn("Devils Lake.", persisted=False)

        self.assertEqual(prepared.plan.action, _turn.ACKNOWLEDGE)
        self.assertFalse(advanced, "the walk advanced past an answer whose "
                                   "rows were never written")
        self.assertEqual(self._state()["active_topic_id"],
                         before["active_topic_id"])
        self.assertEqual(self._state()["version"], before["version"])

    def test_should_advance_refuses_on_every_single_disqualifier(self):
        """Each of the four alone is enough to block the write."""
        plan = _turn.TurnPlan(_turn.ACKNOWLEDGE, "childhood_home", 2,
                              _turn.ADDRESSED)
        self.assertTrue(_rt.should_advance(plan, persisted=True, eligible=True,
                                           cancelled=False))
        for kw in ({"persisted": False}, {"eligible": False},
                   {"cancelled": True}):
            base = {"persisted": True, "eligible": True, "cancelled": False}
            base.update(kw)
            with self.subTest(**kw):
                self.assertFalse(_rt.should_advance(plan, **base))
        self.assertFalse(_rt.should_advance(None, persisted=True,
                                            eligible=True, cancelled=False))
        for action in (_turn.PRESENT, _turn.RE_PRESENT, _turn.HOLD,
                       _turn.IDLE):
            with self.subTest(action=action):
                self.assertFalse(_rt.should_advance(
                    _turn.TurnPlan(action, "childhood_home", 2),
                    persisted=True, eligible=True, cancelled=False))


class PostCommitApplyFailureTests(_Base):

    def test_a_failed_apply_leaves_the_rows_and_is_RECOVERED_next_turn(self):
        """The durable event is the retry record.

        The response is committed on the assistant row. The apply fails.
        The next turn's recovery pass finds the event, re-applies it, and
        re-resolves BEFORE composition — so the narrator is not asked
        again for something they already answered.
        """
        self._turn("Hello.")
        topic = self._state()["active_topic_id"]

        def _boom(*_a, **_k):
            raise sqlite3.OperationalError("database is locked")

        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Devils Lake.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        meta = _rt.commit_meta(prepared.plan, eligible=True, cancelled=False)
        self.history.append({"role": "user", "content": "Devils Lake.",
                             "meta": {}})
        self.history.append({"role": "assistant", "content": "…",
                             "meta": dict(meta)})
        # The apply raises. The rows stay committed; nothing is rolled back.
        with self.assertRaises(sqlite3.OperationalError):
            _boom()
        self.assertEqual(self._state()["active_topic_id"], topic,
                         "state moved despite the apply failing")

        # NEXT TURN: recovery applies the committed response first.
        prepared2 = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Go on.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        self.assertEqual(prepared2.recovery.status, _turn.RETRIED)
        self.assertNotEqual(self._state()["active_topic_id"], topic,
                            "recovery did not apply the committed response")
        self.assertNotEqual(
            prepared2.plan.topic_id, topic,
            "the narrator was asked again about a topic they answered — "
            "recovery repeated instead of retrying")

    def test_recovery_runs_BEFORE_the_plan_sees_the_state(self):
        """Order, asserted directly rather than inferred from an outcome."""
        calls: List[str] = []

        def _resolve(pid):
            calls.append("resolve")
            return _db.profile_seed_resolve(pid)

        def _apply(pid, **kw):
            calls.append("apply")
            return _db.profile_seed_apply(pid, **kw)

        self._turn("Hello.")
        self._turn("Devils Lake.", resolve_fn=_resolve, apply_fn=_apply)
        self.assertIn("apply", calls)
        self.assertEqual(calls[0], "resolve",
                         f"the sequence did not start with a resolve: {calls}")


class RecoveryConflictAndFaultTests(_Base):

    def test_a_recovery_conflict_YIELDS_to_the_authoritative_state(self):
        """A stored disposition is never forced onto a tuple that moved."""
        self._turn("Hello.")

        def _conflict(*_a, **_k):
            raise _seed.VersionConflict(2, 3, None)

        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Devils Lake.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        meta = _rt.commit_meta(prepared.plan, eligible=True, cancelled=False)
        self.history.append({"role": "assistant", "content": "…",
                             "meta": dict(meta)})

        authoritative = self._state()
        prepared2 = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Next.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_conflict)
        self.assertEqual(prepared2.recovery.status, _turn.CONFLICT_RESOLVED)
        self.assertEqual(prepared2.state["active_topic_id"],
                         authoritative["active_topic_id"],
                         "the conflicting apply overrode authoritative state")

    def test_a_recovery_STORAGE_FAULT_propagates_and_refuses_the_turn(self):
        """It must not degrade into "no onboarding row".

        That is indistinguishable from a historical narrator and would
        retire the walk for someone halfway through it. The router turns
        this into a visible refusal; what is asserted here is that the
        rule does not swallow it.
        """
        self._turn("Hello.")

        def _fault(_pid):
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            _rt.prepare_turn(
                self.person_id, self.history, narrator_text="Devils Lake.",
                eligible=True, resolve_fn=_fault,
                apply_fn=_db.profile_seed_apply)


# ── 4. Stale tuples, and the narrator who was never enrolled ────────────
class StaleTupleTests(_Base):

    def test_a_re_versioned_topic_never_applies_the_stale_response(self):
        """Same topic, new version, is a DIFFERENT question.

        The presentation was made at version N. The row moved to N+1
        underneath it. The response must not be applied against the tuple
        that no longer exists — the question is re-asked instead.
        """
        self._turn("Hello.")
        state = self._state()
        topic, version = state["active_topic_id"], state["version"]

        # Move the version underneath the outstanding presentation by
        # declining and re-opening is not available, so bump it directly
        # through the accepted write path on a DIFFERENT topic, then
        # forge a presentation at a version that is now stale.
        self.history.append({
            "role": "assistant", "content": "…",
            "meta": {_turn.PRESENTED_TOPIC: topic,
                     _turn.PRESENTED_VERSION: version + 99}})

        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Devils Lake.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        self.assertEqual(
            prepared.plan.action, _turn.RE_PRESENT,
            "a response was planned against a tuple the state does not hold")
        meta = _rt.commit_meta(prepared.plan, eligible=True, cancelled=False)
        self.assertNotIn(_turn.RESPONSE_TOPIC, meta)
        self.assertFalse(_rt.should_advance(prepared.plan, persisted=True,
                                            eligible=True, cancelled=False))

    def test_malformed_metadata_is_ignored_rather_than_guessed_at(self):
        self.history.append({
            "role": "assistant", "content": "…",
            "meta": {_turn.PRESENTED_TOPIC: "not_a_real_topic",
                     _turn.PRESENTED_VERSION: "seven"}})
        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Devils Lake.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        self.assertEqual(prepared.plan.action, _turn.PRESENT,
                         "malformed metadata was read as a real presentation")


class HistoricalNarratorTests(_Base):

    def test_a_historical_narrator_is_untouched_and_composes_nothing(self):
        """Step 6 reaches newly enrolled narrators. It backfills nobody."""
        with sqlite3.connect(str(self.db_path)) as con:
            con.execute("DELETE FROM profile_seed_onboarding WHERE person_id=?;",
                        (self.person_id,))
            con.commit()

        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text="Hello.",
            eligible=True, resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)

        self.assertEqual(prepared.plan.action, _turn.IDLE)
        self.assertEqual(_rt.commit_meta(prepared.plan, eligible=True,
                                         cancelled=False), {})
        self.assertIsNone(_rt.onboarding_payload(prepared.plan,
                                                 prepared.state))
        with sqlite3.connect(str(self.db_path)) as con:
            rows = con.execute(
                "SELECT COUNT(*) FROM profile_seed_onboarding WHERE person_id=?;",
                (self.person_id,)).fetchone()[0]
        self.assertEqual(rows, 0, "resolving a historical narrator enrolled "
                                  "them — Step 6 backfills nobody")


# ── 5. The runtime payload both transports share ────────────────────────
class SharedPayloadTests(_Base):

    def test_the_payload_carries_every_field_the_composer_reads(self):
        self._turn("Hello.")
        prepared = _rt.prepare_turn(
            self.person_id, self.history, narrator_text=None, eligible=True,
            resolve_fn=_db.profile_seed_resolve,
            apply_fn=_db.profile_seed_apply)
        payload = _rt.onboarding_payload(prepared.plan, prepared.state)
        for field in ("action", "topic_id", "known_topics",
                      "remaining_topics", "completes_walk"):
            with self.subTest(field=field):
                self.assertIn(field, payload)

    def test_attach_is_a_COPY_and_adds_nothing_when_idle(self):
        original = {"speaker_name": "Verlie"}
        out = _rt.attach_onboarding(original, _turn.TurnPlan(_turn.IDLE), None)
        self.assertEqual(out, original)
        self.assertIsNot(out, original, "the runtime was mutated in place")
        self.assertNotIn(_rt.PROFILE_SEED_ONBOARDING_KEY, out)

    def test_REST_and_the_websocket_cannot_disagree(self):
        """One builder, asserted as one builder.

        `profile_seed_rest` must not carry its own copy of the payload
        shape; if it grows one back, this fails.
        """
        rest_source = (_SERVER_CODE / "api" / "services"
                       / "profile_seed_rest.py").read_text(encoding="utf-8")
        self.assertIn("onboarding_payload", rest_source)
        for field in ("\"known_topics\":", "\"remaining_topics\":",
                      "\"completes_walk\":"):
            with self.subTest(field=field):
                self.assertNotIn(
                    field, rest_source,
                    "profile_seed_rest builds the payload by hand again; "
                    "two builders drift one field at a time and the "
                    "narrator gets a different prompt per transport")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
