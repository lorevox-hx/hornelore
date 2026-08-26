"""The turn state machine: who asked what, who answered, what advances.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 step 3 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_turn_reducer

No database, no fastapi, no connection — `profile_seed_turn` takes its
resolve and apply functions as arguments, so the entire state machine is
exercised in memory. `.venv` runs this file with **zero skips**, which is
the point of building the service layer dependency-free.

── WHAT IS BEING GUARDED ─────────────────────────────────────────────

Three designs were carried by the Phase 2 map before this file existed,
and each was a real defect caught in review:

  1. advance the topic that was ASKED, in the same committed turn,
     before the narrator said anything;
  2. one event type, re-stamped — which cannot tell "Lori presented A"
     from "the narrator answered A and Lori acknowledged it", so the
     acknowledgement turn re-asks the question it acknowledges;
  3. compare `topic` where the identity is `(topic, version)`, so an
     answer to an old version consumes a newer presentation;

and one thing the map DESCRIBED but never implemented:

  4. "durable retry" that was really repetition — the narrator asked a
     question they had already answered, with their answer committed one
     row above.

**Every one of those is a mutation in `mutations.py`-style form below,
and every one must fail behaviourally.** A suite that would not have
noticed any of the four is not worth having.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
for _p in (str(_SERVER_CODE), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.services import profile_seed as _seed  # noqa: E402
from api.services import profile_seed_turn as _turn  # noqa: E402

TOPICS = _seed.TOPIC_IDS
A = TOPICS[0]   # childhood_home
B = TOPICS[1]   # siblings
C = TOPICS[2]   # parents_work


# ── fixtures ────────────────────────────────────────────────────────────
def state(active=A, version=7, status=_seed.STATUS_ACTIVE):
    return {"person_id": "p1", "enrolled": True, "status": status,
            "active_topic_id": active, "version": version,
            "topic_state": {t: _seed.UNANSWERED for t in TOPICS},
            "known_topics": [], "remaining_topics": list(TOPICS)}


def presented(topic, version):
    return {"role": "assistant", "content": "…",
            "meta": {_turn.PRESENTED_TOPIC: topic,
                     _turn.PRESENTED_VERSION: version}}


def responded(topic, version, disposition=_seed.ADDRESSED):
    return {"role": "assistant", "content": "…",
            "meta": {_turn.RESPONSE_TOPIC: topic,
                     _turn.RESPONSE_VERSION: version,
                     _turn.RESPONSE_DISPOSITION: disposition}}


def said(text="Devils Lake, North Dakota."):
    return {"role": "user", "content": text, "meta": {}}


def plain_assistant(text="Mm."):
    return {"role": "assistant", "content": text, "meta": {}}


# ── 1. Classification ───────────────────────────────────────────────────
class ClassificationTests(unittest.TestCase):

    def test_a_substantive_answer_is_addressed(self):
        for text in ("Devils Lake, North Dakota.",
                     "Two brothers and a sister.",
                     "My father ran the grain elevator and my mother taught."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text), _seed.ADDRESSED)

    def test_a_four_word_answer_is_addressed(self):
        """No word-count threshold. Four words can answer completely."""
        self.assertEqual(_turn.classify_response("Devils Lake, North Dakota."),
                         _seed.ADDRESSED)

    def test_thirty_words_of_hesitation_is_still_addressed(self):
        """The other half of the no-threshold ruling.

        Grading answer quality is not this layer's job. If a long,
        content-free turn were stationary, Lori would keep asking — and
        the ruling deliberately favours narrator dignity over trying to
        score answers.
        """
        text = ("Oh goodness, that was such a very long time ago now and I "
                "really am not sure I could tell you very much about it at "
                "all these days, you know how it is.")
        self.assertGreater(len(text.split()), 30)
        self.assertEqual(_turn.classify_response(text), _seed.ADDRESSED)

    def test_an_explicit_refusal_is_declined(self):
        for text in ("I'd rather not talk about that.",
                     "That's not for putting in a book.",
                     "Let's skip that, if you don't mind."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text), _seed.DECLINED)

    def test_forgetting_is_addressed_not_declined(self):
        """THE DIGNITY RULING, as behaviour.

        "I don't remember" closes the topic so an older narrator is not
        confronted with the same unreachable question every session. It
        is NOT a refusal — recording it as one would write their memory
        loss down as an unwillingness to speak.
        """
        for text in ("I don't remember.", "I can't recall that at all.",
                     "Nothing comes to mind.", "I never knew, really."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text),
                                 _seed.ADDRESSED)

    def test_a_temporary_deferral_is_stationary(self):
        for text in ("Let me think.", "Give me a moment.", "Hold on.",
                     "Can we come back to that?", "Let me think about that."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text),
                                 _turn.STATIONARY)

    def test_a_deferral_FOLLOWED_BY_AN_ANSWER_is_addressed(self):
        """Whole-utterance matching, not substring.

        A substring search would call this stationary and re-ask a
        question the narrator had just answered — which is the failure
        the deferral category exists to avoid, arriving through the
        deferral category itself.
        """
        for text in ("Let me think — Devils Lake, North Dakota.",
                     "Hold on. Two brothers.",
                     "Give me a moment... it was 1952, I think."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text),
                                 _seed.ADDRESSED)

    def test_empty_and_whitespace_are_stationary(self):
        for text in ("", "   ", "\n\t", None):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text),
                                 _turn.STATIONARY)

    def test_a_refusal_beats_a_deferral(self):
        """Order matters: "I'd rather not, let me think" is a refusal."""
        self.assertEqual(
            _turn.classify_response("I'd rather not. Let me think."),
            _seed.DECLINED)


# ── 2. Event parsing, including malformed metadata ──────────────────────
class EventParsingTests(unittest.TestCase):

    def test_a_well_formed_presentation_parses(self):
        e = _turn.event_from_meta({_turn.PRESENTED_TOPIC: A,
                                   _turn.PRESENTED_VERSION: 3})
        self.assertEqual((e.kind, e.topic_id, e.version),
                         (_turn.PRESENTED, A, 3))

    def test_a_well_formed_response_parses(self):
        e = _turn.event_from_meta({_turn.RESPONSE_TOPIC: A,
                                   _turn.RESPONSE_VERSION: 3,
                                   _turn.RESPONSE_DISPOSITION: _seed.DECLINED})
        self.assertEqual((e.kind, e.topic_id, e.version, e.disposition),
                         (_turn.RESPONSE, A, 3, _seed.DECLINED))

    def test_an_unknown_topic_is_ignored(self):
        for key, extra in ((_turn.PRESENTED_TOPIC,
                            {_turn.PRESENTED_VERSION: 3}),
                           (_turn.RESPONSE_TOPIC,
                            {_turn.RESPONSE_VERSION: 3,
                             _turn.RESPONSE_DISPOSITION: _seed.ADDRESSED})):
            with self.subTest(key=key):
                meta = {key: "favourite_colour", **extra}
                self.assertIsNone(_turn.event_from_meta(meta))

    def test_an_invalid_version_is_ignored(self):
        for bad in (None, 0, -1, "", "abc", 1.5, [], {}):
            with self.subTest(version=bad):
                self.assertIsNone(_turn.event_from_meta(
                    {_turn.PRESENTED_TOPIC: A, _turn.PRESENTED_VERSION: bad}))

    def test_a_boolean_is_not_a_version(self):
        """`isinstance(True, int)` is True in Python.

        A `True` reaching a version field would compare equal to version
        1 and could silently consume a real presentation.
        """
        for bad in (True, False):
            with self.subTest(version=bad):
                self.assertIsNone(_turn.event_from_meta(
                    {_turn.PRESENTED_TOPIC: A, _turn.PRESENTED_VERSION: bad}))

    def test_a_numeric_string_version_is_accepted(self):
        e = _turn.event_from_meta({_turn.PRESENTED_TOPIC: A,
                                   _turn.PRESENTED_VERSION: "3"})
        self.assertEqual(e.version, 3)

    def test_an_invalid_disposition_is_ignored(self):
        for bad in (None, "", "known", "completed", "unanswered", "maybe", 1):
            with self.subTest(disposition=bad):
                self.assertIsNone(_turn.event_from_meta(
                    {_turn.RESPONSE_TOPIC: A, _turn.RESPONSE_VERSION: 3,
                     _turn.RESPONSE_DISPOSITION: bad}))

    def test_a_half_written_event_is_ignored(self):
        for meta in ({_turn.PRESENTED_TOPIC: A},
                     {_turn.PRESENTED_VERSION: 3},
                     {_turn.RESPONSE_TOPIC: A},
                     {_turn.RESPONSE_TOPIC: A, _turn.RESPONSE_VERSION: 3}):
            with self.subTest(meta=meta):
                self.assertIsNone(_turn.event_from_meta(meta))

    def test_non_mapping_meta_is_ignored(self):
        for meta in (None, "", [], 3, "profile_seed_presented_topic"):
            with self.subTest(meta=meta):
                self.assertIsNone(_turn.event_from_meta(meta))

    def test_only_assistant_rows_carry_events(self):
        """A user row with event-shaped metadata is not an event.

        Events describe what LORI did. A narrator row carrying these
        keys would mean the client had asserted a topic was answered,
        which no transport may do.
        """
        forged = {"role": "user", "content": "…",
                  "meta": {_turn.PRESENTED_TOPIC: A,
                           _turn.PRESENTED_VERSION: 3}}
        self.assertEqual(_turn.read_events([forged]), [])

    def test_malformed_rows_do_not_break_the_scan(self):
        history = [None, "junk", 3, {"role": "assistant"},
                   {"role": "assistant", "meta": None}, presented(A, 3)]
        events = _turn.read_events(history)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].tuple, (A, 3))


# ── 3. The reduction ────────────────────────────────────────────────────
class ReductionTests(unittest.TestCase):

    def test_no_history_means_nothing_outstanding(self):
        self.assertIsNone(_turn.outstanding_presentation([]))
        self.assertIsNone(_turn.outstanding_presentation(None))

    def test_a_presentation_is_outstanding_until_answered(self):
        h = [presented(A, 7), said()]
        self.assertEqual(_turn.outstanding_presentation(h).tuple, (A, 7))

    def test_an_exact_response_consumes_its_presentation(self):
        h = [presented(A, 7), said(), responded(A, 7)]
        self.assertIsNone(_turn.outstanding_presentation(h))

    def test_a_response_at_a_DIFFERENT_VERSION_does_not_consume(self):
        """THE TUPLE, not the topic.

        The same topic stays active while the version moves — an
        unrelated operator entry, a superseded row, a pause and resume.
        An answer to the old question must not consume the new
        presentation.
        """
        h = [presented(A, 7), said(), responded(A, 7),
             presented(A, 8), said()]
        outstanding = _turn.outstanding_presentation(h)
        self.assertIsNotNone(outstanding)
        self.assertEqual(outstanding.tuple, (A, 8))

    def test_an_old_response_cannot_consume_a_newer_presentation(self):
        h = [responded(A, 7), presented(A, 8), said()]
        self.assertEqual(_turn.outstanding_presentation(h).tuple, (A, 8))

    def test_a_LATE_old_response_does_not_consume_a_newer_presentation(self):
        """The case that discriminates tuple-consumption from topic-consumption.

        *(Added after a mutation survived. The two tests above put the
        newer presentation LAST, so the reverse scan returned it before
        the consumed set had anything in it — they passed identically
        whether consumption compared tuples or topics, and "the tuple is
        the identity" was therefore unproven on the consumption side.)*

        Here the stale response arrives AFTER the newer presentation: a
        duplicated or replayed acknowledgement of version 7 landing once
        version 8 is already the open question. Consuming on topic alone
        would close a question the narrator has not answered.
        """
        h = [presented(A, 8), said(), responded(A, 7)]
        outstanding = _turn.outstanding_presentation(h)
        self.assertIsNotNone(
            outstanding,
            "a stale response at version 7 consumed the open version 8 "
            "question — the narrator would never be asked it")
        self.assertEqual(outstanding.tuple, (A, 8))

    def test_two_open_versions_resolve_to_the_newer_one(self):
        """Same shape, without an intervening user row.

        Consuming on topic would discard the version-8 presentation and
        hand back version 7 — an outstanding question two versions
        behind the authoritative state, which then reads as stale and
        re-presents forever.
        """
        h = [presented(A, 7), presented(A, 8), responded(A, 7)]
        self.assertEqual(_turn.outstanding_presentation(h).tuple, (A, 8))

    def test_a_response_to_another_topic_does_not_consume(self):
        h = [presented(A, 7), said(), responded(B, 7)]
        self.assertEqual(_turn.outstanding_presentation(h).tuple, (A, 7))

    def test_repeated_presentations_leave_the_latest_outstanding(self):
        h = [presented(A, 7), said("Let me think."), presented(A, 7)]
        self.assertEqual(_turn.outstanding_presentation(h).tuple, (A, 7))

    def test_a_full_walk_of_three_topics_reduces_correctly(self):
        h = [presented(A, 7), said(), responded(A, 7),
             presented(B, 8), said(), responded(B, 8),
             presented(C, 9), said()]
        self.assertEqual(_turn.outstanding_presentation(h).tuple, (C, 9))
        self.assertEqual(_turn.latest_response(h).tuple, (B, 8))


# ── 4. The turn plan ────────────────────────────────────────────────────
class TurnPlanTests(unittest.TestCase):

    def test_the_first_presentation_advances_nothing(self):
        """DEFECT 1, as a named test.

        The original design marked the topic it had just asked as
        addressed, in the same committed turn, before the narrator said
        anything about it.
        """
        plan = _turn.plan_turn(state=state(), history=[], narrator_text="Hello")
        self.assertEqual(plan.action, _turn.PRESENT)
        self.assertEqual(plan.topic_id, A)
        self.assertFalse(plan.advances,
                         "the first presentation advanced its own question")
        self.assertEqual(plan.response_meta(), {})

    def test_a_presentation_turn_stamps_only_a_presented_event(self):
        plan = _turn.plan_turn(state=state(), history=[], narrator_text="Hi")
        self.assertEqual(plan.turn_meta(),
                         {_turn.PRESENTED_TOPIC: A, _turn.PRESENTED_VERSION: 7})

    def test_an_answer_acknowledges_and_asks_nothing(self):
        """DEFECT 2, as a named test.

        An acknowledgement carries a response event and NO presentation
        event, so nothing re-asks A and nothing speculatively asks B.
        """
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(), history=h,
                               narrator_text="Devils Lake, North Dakota.")
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        self.assertTrue(plan.advances)
        self.assertEqual(plan.presented_meta(), {},
                         "the acknowledgement turn re-asked a question")
        self.assertEqual(plan.turn_meta(),
                         {_turn.RESPONSE_TOPIC: A, _turn.RESPONSE_VERSION: 7,
                          _turn.RESPONSE_DISPOSITION: _seed.ADDRESSED})

    def test_a_refusal_acknowledges_as_declined(self):
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(), history=h,
                               narrator_text="I'd rather not talk about that.")
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        self.assertEqual(plan.disposition, _seed.DECLINED)

    def test_a_deferral_re_presents_and_writes_no_response_event(self):
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(), history=h,
                               narrator_text="Let me think.")
        self.assertEqual(plan.action, _turn.RE_PRESENT)
        self.assertFalse(plan.advances)
        self.assertEqual(plan.response_meta(), {},
                         "a deferral produced a response event, which would "
                         "close a question the narrator is still working on")
        self.assertEqual(plan.presented_meta(),
                         {_turn.PRESENTED_TOPIC: A, _turn.PRESENTED_VERSION: 7})

    def test_a_stale_tuple_re_presents_and_advances_nothing(self):
        """DEFECT 3, as a named test: same topic, new version."""
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(active=A, version=8), history=h,
                               narrator_text="Devils Lake.")
        self.assertEqual(plan.action, _turn.RE_PRESENT)
        self.assertFalse(
            plan.advances,
            "an answer to version 7 advanced a question at version 8")
        self.assertEqual(plan.version, 8)

    def test_a_moved_topic_re_presents(self):
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(active=B, version=8), history=h,
                               narrator_text="Devils Lake.")
        self.assertEqual((plan.action, plan.topic_id), (_turn.RE_PRESENT, B))
        self.assertFalse(plan.advances)

    def test_the_acknowledgement_applies_the_OUTSTANDING_version(self):
        """Not the version read at composition.

        This is what makes a duplicated hook conflict rather than
        advance: it re-applies the same tuple and Phase 1 refuses it.
        """
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(active=A, version=7), history=h,
                               narrator_text="Devils Lake.")
        self.assertEqual((plan.topic_id, plan.version), (A, 7))

    def test_after_an_acknowledgement_the_next_turn_presents_B(self):
        h = [presented(A, 7), said(), responded(A, 7)]
        plan = _turn.plan_turn(state=state(active=B, version=8), history=h,
                               narrator_text="Yes.")
        self.assertEqual((plan.action, plan.topic_id, plan.version),
                         (_turn.PRESENT, B, 8))
        self.assertFalse(plan.advances)

    def test_an_ineligible_turn_is_idle(self):
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(), history=h,
                               narrator_text="Devils Lake.", eligible=False)
        self.assertEqual(plan.action, _turn.IDLE)
        self.assertFalse(plan.advances)
        self.assertEqual(plan.turn_meta(), {})

    def test_a_historical_narrator_is_idle(self):
        plan = _turn.plan_turn(state=None, history=[], narrator_text="Hi")
        self.assertEqual(plan.action, _turn.IDLE)

    def test_pending_paused_and_completed_are_idle(self):
        for status in (_seed.STATUS_PENDING, _seed.STATUS_PAUSED,
                       _seed.STATUS_COMPLETED):
            with self.subTest(status=status):
                plan = _turn.plan_turn(state=state(status=status), history=[],
                                       narrator_text="Hi")
                self.assertEqual(plan.action, _turn.IDLE)

    def test_a_corrupt_state_is_idle_rather_than_guessed(self):
        for bad in ({"status": _seed.STATUS_ACTIVE, "active_topic_id": None,
                     "version": 7},
                    {"status": _seed.STATUS_ACTIVE,
                     "active_topic_id": "favourite_colour", "version": 7},
                    {"status": _seed.STATUS_ACTIVE, "active_topic_id": A,
                     "version": 0}):
            with self.subTest(state=bad):
                self.assertEqual(_turn.plan_turn(state=bad, history=[],
                                                 narrator_text="Hi").action,
                                 _turn.IDLE)

    def test_no_plan_ever_carries_narrator_prose(self):
        """Work-order decision 8, on the turn row."""
        secret = "My father drank and we did not speak of it."
        for text in (secret, "I'd rather not.", "Let me think.", ""):
            for hist in ([], [presented(A, 7), said()]):
                plan = _turn.plan_turn(state=state(), history=hist,
                                       narrator_text=text)
                blob = repr(plan.turn_meta())
                with self.subTest(text=text[:20]):
                    self.assertNotIn("father", blob)
                    self.assertNotIn("rather", blob)
                    self.assertTrue(
                        set(plan.turn_meta()).issubset(set(_turn.META_KEYS)))


# ── 5. Recovery ─────────────────────────────────────────────────────────
class _Recorder:
    """A resolve/apply pair with scripted behaviour and a call log."""

    def __init__(self, states, apply_raises=None):
        self._states = list(states)
        self.resolves = 0
        self.applies = []
        self._apply_raises = apply_raises

    def resolve(self, person_id):
        self.resolves += 1
        index = min(self.resolves - 1, len(self._states) - 1)
        return self._states[index]

    def apply(self, person_id, *, expected_version, action, topic_id):
        self.applies.append((person_id, expected_version, action, topic_id))
        if self._apply_raises is not None:
            raise self._apply_raises
        return {}


class RecoveryTests(unittest.TestCase):

    def test_no_response_event_means_nothing_owed(self):
        r = _Recorder([state()])
        out = _turn.recover("p1", [presented(A, 7)],
                            resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(out.status, _turn.NOTHING_OWED)
        self.assertEqual(r.applies, [])

    def test_an_unapplied_response_is_retried(self):
        """DEFECT 4, as a named test.

        Without recovery the response consumes the presentation,
        onboarding still holds (A, 7) active, the reduction finds
        nothing outstanding, and the machine RE-ASKS A — a question the
        narrator has already answered, with their answer committed one
        row above.
        """
        after = state(active=B, version=8)
        r = _Recorder([state(active=A, version=7), after])
        history = [presented(A, 7), said(), responded(A, 7)]
        out = _turn.recover("p1", history,
                            resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(out.status, _turn.RETRIED)
        self.assertEqual(r.applies,
                         [("p1", 7, _seed.ADDRESSED, A)])
        self.assertEqual(out.state["active_topic_id"], B,
                         "recovery did not re-resolve, so composition would "
                         "still see the question that was just closed")

    def test_recovery_preserves_the_stored_disposition(self):
        """A retry applies what the narrator was TOLD had happened.

        Topic and version alone cannot reconstruct `declined` — this is
        the whole reason the disposition is on the committed row.
        """
        r = _Recorder([state(active=A, version=7), state(active=B, version=8)])
        history = [presented(A, 7), said(), responded(A, 7, _seed.DECLINED)]
        _turn.recover("p1", history, resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(r.applies[0][2], _seed.DECLINED)

    def test_an_already_applied_response_is_not_reapplied(self):
        r = _Recorder([state(active=B, version=8)])
        history = [presented(A, 7), said(), responded(A, 7)]
        out = _turn.recover("p1", history,
                            resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(out.status, _turn.NOTHING_OWED)
        self.assertEqual(r.applies, [])

    def test_a_conflict_re_resolves_and_never_forces_the_disposition(self):
        moved = state(active=B, version=9)
        r = _Recorder([state(active=A, version=7), moved],
                      apply_raises=_seed.VersionConflict(7, 9, None))
        history = [presented(A, 7), said(), responded(A, 7)]
        out = _turn.recover("p1", history,
                            resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(out.status, _turn.CONFLICT_RESOLVED)
        self.assertEqual(len(r.applies), 1, "the apply was retried after a "
                                            "conflict instead of yielding")
        self.assertEqual(out.state["active_topic_id"], B,
                         "the authoritative state was not re-resolved after "
                         "the conflict")

    def test_a_non_conflict_storage_error_propagates(self):
        """The caller must refuse composition visibly.

        Falling back would mean "ask it again", and asking again is an
        onboarding decision — which Phase 1 established a storage fault
        must never make.
        """
        import sqlite3
        r = _Recorder([state(active=A, version=7)],
                      apply_raises=sqlite3.OperationalError("database is locked"))
        history = [presented(A, 7), said(), responded(A, 7)]
        with self.assertRaises(sqlite3.OperationalError):
            _turn.recover("p1", history, resolve_fn=r.resolve, apply_fn=r.apply)

    def test_a_failing_resolve_propagates(self):
        import sqlite3

        def boom(person_id):
            raise sqlite3.OperationalError("database is locked")

        with self.assertRaises(sqlite3.OperationalError):
            _turn.recover("p1", [presented(A, 7), said(), responded(A, 7)],
                          resolve_fn=boom, apply_fn=lambda *a, **k: None)

    def test_a_historical_narrator_recovers_nothing(self):
        r = _Recorder([None])
        out = _turn.recover("p1", [presented(A, 7), said(), responded(A, 7)],
                            resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(out.status, _turn.NOTHING_OWED)
        self.assertEqual(r.applies, [])

    def test_recovery_then_planning_presents_B_not_A(self):
        """The end-to-end shape of the repair.

        After a crashed apply, the next turn must ask the NEXT question,
        not repeat the one already answered.
        """
        r = _Recorder([state(active=A, version=7), state(active=B, version=8)])
        history = [presented(A, 7), said(), responded(A, 7)]
        out = _turn.recover("p1", history,
                            resolve_fn=r.resolve, apply_fn=r.apply)
        plan = _turn.plan_turn(state=out.state, history=history,
                               narrator_text="Hello again")
        self.assertEqual((plan.action, plan.topic_id), (_turn.PRESENT, B))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
