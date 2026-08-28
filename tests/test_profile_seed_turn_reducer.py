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

**Every one of those is a checked-in mutation, and every one must fail
behaviourally.** They are in `scripts/run_mutation_gate.py` — not in
this file and not in a `mutations.py`, neither of which exists — so a
reviewer runs them rather than believing a report. A suite that would
not have noticed any of the four is not worth having.
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

    def test_CONTRACTED_deferrals_are_stationary(self):
        """The defect that made the category nearly useless.

        *(`_PUNCT` turned punctuation into a SPACE, so "I'll come back to
        that" normalised to "i ll come back to that" and never matched
        the configured `ill come back to that`. The single most natural
        way to ask for a moment was classified `addressed` and the topic
        was CLOSED. The fixtures had all been written apostrophe-free,
        which is exactly why they agreed.)*

        Both apostrophe forms, because a phone keyboard and most word
        processors produce the curly one by default.
        """
        for text in ("I'll come back to that.", "I’ll come back to that.",
                     "Let's come back to it.", "Let’s come back to it.",
                     "I'll come back to it", "I’d like a moment.",
                     "I'd like a minute."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text),
                                 _turn.STATIONARY,
                                 f"{text!r} closed the topic instead of "
                                 "leaving it open")

    def test_contracted_REFUSALS_are_still_declined(self):
        """The apostrophe change must not reclassify refusals."""
        for text in ("I'd rather not talk about that.",
                     "I’d rather not talk about that.",
                     "Let's skip that.", "Let’s skip that."):
            with self.subTest(text=text):
                self.assertEqual(_turn.classify_response(text),
                                 _seed.DECLINED)

    def test_contracted_ANSWERS_are_still_addressed(self):
        """And must not turn ordinary contracted speech into a deferral."""
        for text in ("Devils Lake, that's where.",
                     "I'll tell you — Devils Lake.",
                     "I’ll tell you — Devils Lake.",
                     "That's my brother's name.", "I don't remember."):
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

    def test_a_response_consumes_EVERY_earlier_identical_presentation(self):
        """The deferral-then-answer history, which is ordinary.

        *(This case was a live defect. The reducer modelled consumption
        as one-for-one — it discarded the tuple after matching a single
        presentation — so the reverse scan consumed the newer
        presentation, emptied the set, and handed back the OLDER
        identical one as still outstanding. A question the narrator had
        just answered would be re-presented, and re-presented again
        after every deferral. The deferral path is what makes this
        reachable in normal conversation rather than only under a
        race.)*

        Consumption is TEMPORAL: a response answers every earlier
        presentation of its exact tuple, however many times Lori asked.
        """
        h = [presented(A, 7), said("Let me think."),
             presented(A, 7), said("Devils Lake."), responded(A, 7)]
        self.assertIsNone(
            _turn.outstanding_presentation(h),
            "an already-answered question was left outstanding, so Lori "
            "would ask it again")

    def test_three_deferrals_then_an_answer_leaves_nothing_outstanding(self):
        h = [presented(A, 7), said("Let me think."),
             presented(A, 7), said("Hold on."),
             presented(A, 7), said("Give me a moment."),
             presented(A, 7), said("Devils Lake."), responded(A, 7)]
        self.assertIsNone(_turn.outstanding_presentation(h))

    def test_a_LATER_presentation_of_the_same_tuple_stays_outstanding(self):
        """The other side of the same rule, and the reason it is not
        simply "ignore every presentation whose tuple was ever answered".

        If Lori asks A/7 again AFTER the response — because evidence has
        not moved and the topic is genuinely still open — that question
        is live and must be answerable.
        """
        h = [presented(A, 7), said(), responded(A, 7),
             presented(A, 7), said()]
        outstanding = _turn.outstanding_presentation(h)
        self.assertIsNotNone(
            outstanding,
            "a genuinely later re-presentation was swallowed by an older "
            "response, so the narrator's answer could never be recorded")
        self.assertEqual(outstanding.tuple, (A, 7))

    def test_two_full_rounds_on_the_same_tuple_leave_nothing_outstanding(self):
        h = [presented(A, 7), said(), responded(A, 7),
             presented(A, 7), said(), responded(A, 7)]
        self.assertIsNone(_turn.outstanding_presentation(h))

    def test_a_deferral_round_then_a_plan_acknowledges_rather_than_re_asking(self):
        """End to end, because the defect's cost was behavioural.

        With the old reducer this planned RE_PRESENT — asking the
        narrator the same question a third time — instead of
        acknowledging the answer they had just given.
        """
        h = [presented(A, 7), said("Let me think."), presented(A, 7)]
        plan = _turn.plan_turn(state=state(active=A, version=7), history=h,
                               narrator_text="Devils Lake, North Dakota.")
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        self.assertEqual((plan.topic_id, plan.version), (A, 7))

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

    def test_an_ineligible_turn_on_an_ACTIVE_walk_HOLDS(self):
        """DEFECT 5, as a named test — and it is a suppression defect.

        This asserted `IDLE`, and `IDLE` is the action that leaves the
        LEGACY BROWSER BLOCK STANDING. So an internal system directive,
        a deterministic mode or a cancelled turn arriving mid-walk
        advanced nothing — correct — and handed Lori back "Gather the
        following 10 facts", the pass the server had taken ownership of.

        `HOLD` is the same "do nothing", with the suppression kept.
        """
        h = [presented(A, 7), said()]
        plan = _turn.plan_turn(state=state(), history=h,
                               narrator_text="Devils Lake.", eligible=False)
        self.assertEqual(plan.action, _turn.HOLD)
        self.assertFalse(plan.advances)
        self.assertEqual(plan.turn_meta(), {},
                         "an ineligible turn stamped an event")

    def test_an_ineligible_turn_with_NO_active_walk_is_still_idle(self):
        """`HOLD` must not enrol anybody.

        A historical narrator, and a pending / paused / completed row,
        have no walk to hold. They stay `IDLE`, which is what keeps their
        prompt byte-identical to the pre-onboarding one.
        """
        self.assertEqual(
            _turn.plan_turn(state=None, history=[], narrator_text="Hi",
                            eligible=False).action, _turn.IDLE)
        for status in (_seed.STATUS_PENDING, _seed.STATUS_PAUSED,
                       _seed.STATUS_COMPLETED):
            with self.subTest(status=status):
                self.assertEqual(
                    _turn.plan_turn(state=state(status=status), history=[],
                                    narrator_text="Hi",
                                    eligible=False).action, _turn.IDLE)

    def test_an_ineligible_turn_with_a_CORRUPT_state_is_idle(self):
        """Malformed is not "active". A state too broken to plan against
        is not a walk to hold, and treating it as one would suppress the
        legacy block on the strength of a payload nothing validated."""
        bad = {"status": _seed.STATUS_ACTIVE, "active_topic_id": "nonsense",
               "version": 7}
        self.assertEqual(
            _turn.plan_turn(state=bad, history=[], narrator_text="Hi",
                            eligible=False).action, _turn.IDLE)

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


class ConversationControlTests(unittest.TestCase):
    """A turn that operates the conversation is never an answer.

    ── WHAT THE CLASSIFIER ACTUALLY REPORTED, 2026-08-27 ───────────────

        "repeat that"     -> addressed
        "say that again"  -> addressed
        "pause"           -> addressed
        "help"            -> addressed
        "change narrator" -> addressed

    Every one of those CLOSED the open topic. A narrator asking to hear
    the question again would have had it recorded as answered and never
    hear it again — the failure this module exists to prevent, arriving
    through the one category of turn that says plainly it is not an
    answer.

    The rule "everything else non-empty is `addressed`" was written
    against ANSWERS of varying quality, and refusing to grade answers is
    right. A control is not a low-quality answer.

    ── ONE VOCABULARY, NOT A SECOND ONE ────────────────────────────────

    The detector is `services/conversation_control.py`, which is the
    trip-capture detector EXTRACTED rather than copied. A test below
    asserts this module holds no phrase list of its own, because "we
    reused it" is a claim that decays silently.
    """

    HOLDING = ("pause", "stop", "help", "change narrator", "never mind",
               "forget it", "go on", "start over")
    REPEATING = ("repeat that", "say that again", "say it again",
                 "what was that", "come again", "louder", "slower",
                 "read that back")

    def test_no_control_is_ever_addressed(self):
        for text in self.HOLDING + self.REPEATING:
            with self.subTest(text=text):
                self.assertNotEqual(
                    _turn.classify_response(text), _seed.ADDRESSED,
                    f"{text!r} closed the open topic")

    def test_controls_survive_politeness_and_punctuation(self):
        for text in ("Repeat that, please.", "Lori, say that again!",
                     "Can you say it again?", "  PAUSE  ", "Help, please."):
            with self.subTest(text=text):
                self.assertNotEqual(_turn.classify_response(text),
                                    _seed.ADDRESSED)

    def test_a_HOLDING_control_asks_nothing_and_stamps_nothing(self):
        h = [presented(A, 7), said()]
        for text in self.HOLDING:
            with self.subTest(text=text):
                plan = _turn.plan_turn(state=state(), history=h,
                                       narrator_text=text)
                self.assertEqual(plan.action, _turn.HOLD)
                self.assertFalse(plan.advances)
                self.assertEqual(plan.turn_meta(), {})
                self.assertFalse(plan.completes_walk)

    def test_a_REPEATING_control_re_presents_the_SAME_tuple(self):
        """"Say that again" is a request FOR the question. Re-present it
        at the version it was asked at — a new presentation, no response
        event, and nothing advanced."""
        h = [presented(A, 7), said()]
        for text in self.REPEATING:
            with self.subTest(text=text):
                plan = _turn.plan_turn(state=state(), history=h,
                                       narrator_text=text)
                self.assertEqual(plan.action, _turn.RE_PRESENT)
                self.assertEqual((plan.topic_id, plan.version), (A, 7))
                self.assertEqual(plan.response_meta(), {})
                self.assertFalse(plan.advances)

    def test_a_DEFERRAL_still_beats_a_control(self):
        """"hold on" is in both vocabularies. Step 3's accepted rule for
        a request for time is to come back to the question gently, and
        that is unchanged: a narrator who says "hold on" is still working
        on the answer, and falling silent on them would be a regression
        dressed as a correction."""
        h = [presented(A, 7), said()]
        for text in ("hold on", "just a minute", "hang on", "one moment"):
            with self.subTest(text=text):
                plan = _turn.plan_turn(state=state(), history=h,
                                       narrator_text=text)
                self.assertEqual(plan.action, _turn.RE_PRESENT)
                self.assertEqual(plan.presented_meta(),
                                 {_turn.PRESENTED_TOPIC: A,
                                  _turn.PRESENTED_VERSION: 7})

    def test_real_narration_containing_control_words_is_still_addressed(self):
        """The anchoring, from the consumer side.

        Each of these CONTAINS a command and IS a memory. A substring
        match would eat all of them, and this is the direction that
        costs something the narrator cannot get back.
        """
        h = [presented(A, 7), said()]
        for text in ("We had to go back to the hotel that night.",
                     "She would say that again every Christmas.",
                     "We stopped at the school and continued to the cemetery.",
                     "I had to wait for my brother at the station.",
                     "Help was a long way off in those days.",
                     # SHORT ones that BEGIN with a command word. These
                     # are the cases the trailing anchor earns its keep
                     # on: they are inside the six-word ceiling, so the
                     # ceiling cannot save them, and a starts-with match
                     # would read every one as a button press.
                     "Stop signs were rare out there.",
                     "Go back roads, we always did.",
                     "Wait tables? I did for years.",
                     "Help came from the neighbours."):
            with self.subTest(text=text[:30]):
                self.assertEqual(_turn.classify_response(text),
                                 _seed.ADDRESSED)
                self.assertEqual(
                    _turn.plan_turn(state=state(), history=h,
                                    narrator_text=text).action,
                    _turn.ACKNOWLEDGE)

    def test_a_control_never_completes_the_walk(self):
        """The last topic is the dangerous one: a control read as an
        answer there would end the walk on a turn that answered nothing.
        """
        last = {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                "active_topic_id": A, "version": 7,
                "known_topics": [t for t in TOPICS if t != A],
                "remaining_topics": [A]}
        h = [presented(A, 7), said()]
        for text in self.HOLDING + self.REPEATING:
            with self.subTest(text=text):
                plan = _turn.plan_turn(state=last, history=h,
                                       narrator_text=text)
                self.assertFalse(plan.completes_walk)
                self.assertFalse(plan.advances)

    def test_a_control_on_the_FIRST_turn_does_not_skip_the_question(self):
        """No presentation outstanding yet. A holding control still holds
        — it must not ask — and the question is simply asked on a later
        turn, because nothing was consumed."""
        plan = _turn.plan_turn(state=state(), history=[],
                               narrator_text="pause")
        self.assertEqual(plan.action, _turn.HOLD)
        self.assertEqual(plan.turn_meta(), {})

    def test_this_module_keeps_NO_phrase_list_for_controls(self):
        """"Reuse the detector" is a claim that decays silently.

        The one vocabulary lives in `conversation_control`. If a phrase
        from it appears literally in `profile_seed_turn.py`, a second
        list has started — and the first divergence is a turn one
        detector skips and the other records as `addressed`.

        The DEFERRAL list is a different category and stays here: it is
        about a narrator who is still answering, not one who is
        operating the conversation.

        Scanned over the AST rather than the raw text, and DOCSTRINGS
        ARE EXCLUDED — a module that explains why it does not keep the
        list has to be able to name what it is not keeping. Comments
        never reach the AST at all. What is checked is the string
        constants the code can actually match against.
        """
        import ast
        path = _SERVER_CODE / "api" / "services" / "profile_seed_turn.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))

        docstrings = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = getattr(node, "body", None) or []
            first = body[0] if body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))

        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, str)
                    and id(n) not in docstrings]

        for phrase in ("say that again", "repeat that", "change narrator",
                       "never mind", "speak up", "slow down", "what was that"):
            with self.subTest(phrase=phrase):
                hit = next((s for s in literals if phrase in s), None)
                self.assertIsNone(
                    hit,
                    f"{phrase!r} is a live string constant in "
                    f"profile_seed_turn.py ({hit!r}); the control "
                    "vocabulary has been copied instead of imported")

    def test_the_no_phrase_list_guard_is_not_vacuous(self):
        """The guard above must be able to fail.

        A source scan that finds nothing because it is looking in the
        wrong place passes forever. This runs the same extraction over a
        module that DOES carry a phrase list — `conversation_control`
        itself — and requires a hit.
        """
        import ast
        path = _SERVER_CODE / "api" / "services" / "conversation_control.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = getattr(node, "body", None) or []
            first = body[0] if body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, str)
                    and id(n) not in docstrings]
        self.assertTrue(
            any("say (?:that|it) again" in s for s in literals),
            "the extraction found no vocabulary in the module that owns "
            "it, so finding none in profile_seed_turn proves nothing")

    def test_the_shared_detector_is_the_one_trip_capture_uses(self):
        """Extraction, asserted rather than described.

        `trip_story_capture` must resolve to the SAME function object.
        A copy that happens to agree today is exactly what this checks
        against.
        """
        from api.services import conversation_control as _cc
        from api.services import trip_story_capture as _tsc
        self.assertIs(_tsc._is_conversation_command, _cc.is_conversation_command)
        self.assertIs(_tsc._normalize, _cc.normalize)


class CompletionTransitionTests(unittest.TestCase):
    """The last answer ends the walk warmly, on a turn that can say so.

    *(The presentation block used to carry "when they have answered,
    tell them warmly that you now have a sense of their story" on the
    turn that ASKED the final question. That instruction described the
    NEXT turn, by which point the block was gone and the acknowledgement
    had no idea the walk had finished — a promise Lori was structurally
    unable to keep.)*
    """

    def _state(self, remaining):
        return {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                "active_topic_id": remaining[0], "version": 7,
                "known_topics": [t for t in TOPICS if t not in remaining],
                "remaining_topics": list(remaining)}

    def test_answering_the_last_topic_sets_completes_walk(self):
        state = self._state([A])
        plan = _turn.plan_turn(state=state, history=[presented(A, 7), said()],
                               narrator_text="Devils Lake.")
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        self.assertTrue(plan.completes_walk)

    def test_DECLINING_the_last_topic_also_completes_the_walk(self):
        """A refusal is an answer. It must end the walk like one."""
        state = self._state([A])
        plan = _turn.plan_turn(state=state, history=[presented(A, 7), said()],
                               narrator_text="I'd rather not talk about that.")
        self.assertEqual(plan.disposition, _seed.DECLINED)
        self.assertTrue(plan.completes_walk)

    def test_answering_a_mid_walk_topic_does_not(self):
        state = self._state([A, B])
        plan = _turn.plan_turn(state=state, history=[presented(A, 7), said()],
                               narrator_text="Devils Lake.")
        self.assertFalse(plan.completes_walk)

    def test_a_deferral_on_the_last_topic_does_not_complete_it(self):
        state = self._state([A])
        plan = _turn.plan_turn(state=state, history=[presented(A, 7), said()],
                               narrator_text="Let me think.")
        self.assertEqual(plan.action, _turn.RE_PRESENT)
        self.assertFalse(plan.completes_walk,
                         "a request for time ended the walk")

    def test_a_presentation_never_completes(self):
        state = self._state([A])
        plan = _turn.plan_turn(state=state, history=[], narrator_text="Hi")
        self.assertEqual(plan.action, _turn.PRESENT)
        self.assertFalse(plan.completes_walk)

    def test_unknown_remaining_topics_do_not_fake_completion(self):
        state = self._state([A])
        state["remaining_topics"] = [A, "favourite_colour"]
        plan = _turn.plan_turn(state=state, history=[presented(A, 7), said()],
                               narrator_text="Devils Lake.")
        self.assertTrue(plan.completes_walk,
                        "an unknown id in remaining_topics blocked a real "
                        "completion")


# ── 5. Recovery ─────────────────────────────────────────────────────────
class _Recorder:
    """A resolve/apply pair with scripted behaviour and a call log.

    ── `raise_once`, AND WHY A PERMANENT RAISER IS A BAD INSTRUMENT ─────

    *(Added 2026-08-27. `apply_raises` raised on EVERY call, and mutation
    M8 — "a version conflict forces the stored disposition anyway" — was
    written against exactly this fixture. Under M8 the illicit second
    apply hit the same permanent raiser, the `VersionConflict` escaped
    `recover()`, and every test in the module ERRORED. The gate scored
    M8 `BROKEN`: errors only, no assertion failed.*

    *That is not a scoring quirk. An instrument that CONVERTS THE DEFECT
    INTO AN EXCEPTION cannot observe the defect. The claim M8 exists to
    prove is "the apply is not retried after a conflict", and proving it
    requires a second apply that would SUCCEED — otherwise the test
    cannot tell "it did not retry" from "it retried and blew up".*

    *So the conflict recorder now raises ONCE and then succeeds. Correct
    code calls apply exactly once and never sees the difference; M8 calls
    it twice, the second call is recorded, and `len(applies) == 1` fails
    as an assertion. Same defect, evidence instead of a traceback.)*
    """

    def __init__(self, states, apply_raises=None, raise_once=False):
        self._states = list(states)
        self.resolves = 0
        self.applies = []
        self._apply_raises = apply_raises
        self._raise_once = raise_once

    def resolve(self, person_id):
        self.resolves += 1
        index = min(self.resolves - 1, len(self._states) - 1)
        return self._states[index]

    def apply(self, person_id, *, expected_version, action, topic_id):
        self.applies.append((person_id, expected_version, action, topic_id))
        if self._apply_raises is not None:
            if not (self._raise_once and len(self.applies) > 1):
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
        """The CONFLICT-ONCE recorder is the point of this test.

        Its second apply would SUCCEED. So "one apply" is a measurement
        rather than a side effect of a fixture that cannot do anything
        else — see `_Recorder` for the version of this that could not
        observe its own defect.
        """
        moved = state(active=B, version=9)
        r = _Recorder([state(active=A, version=7), moved],
                      apply_raises=_seed.VersionConflict(7, 9, None),
                      raise_once=True)
        history = [presented(A, 7), said(), responded(A, 7)]
        out = _turn.recover("p1", history,
                            resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(out.status, _turn.CONFLICT_RESOLVED)
        self.assertEqual(len(r.applies), 1, "the apply was retried after a "
                                            "conflict instead of yielding")
        self.assertEqual(out.state["active_topic_id"], B,
                         "the authoritative state was not re-resolved after "
                         "the conflict")

    def test_the_conflict_recorder_CAN_succeed_on_a_second_apply(self):
        """The instrument itself, proved.

        If `raise_once` did not work, the test above would pass for the
        emptiest possible reason: a second apply that was impossible
        rather than absent. This drives the recorder directly and shows
        the second call returning normally.
        """
        r = _Recorder([state()], apply_raises=_seed.VersionConflict(7, 9, None),
                      raise_once=True)
        with self.assertRaises(_seed.VersionConflict):
            r.apply("p1", expected_version=7, action=_seed.ADDRESSED,
                    topic_id=A)
        self.assertEqual(
            r.apply("p1", expected_version=7, action=_seed.ADDRESSED,
                    topic_id=A), {},
            "the second apply raised too, so a forced re-apply would be "
            "invisible to every test using this fixture")
        self.assertEqual(len(r.applies), 2)

    def test_a_conflict_records_EXACTLY_ONE_apply_call(self):
        """The same claim as the test above, stated as the call log.

        Two assertions on one behaviour, deliberately: this one names
        the ARGUMENTS, so a forced re-apply is caught even if some future
        edit made the second call look like a different operation.
        """
        r = _Recorder([state(active=A, version=7), state(active=B, version=9)],
                      apply_raises=_seed.VersionConflict(7, 9, None),
                      raise_once=True)
        history = [presented(A, 7), said(), responded(A, 7, _seed.DECLINED)]
        _turn.recover("p1", history, resolve_fn=r.resolve, apply_fn=r.apply)
        self.assertEqual(
            r.applies, [("p1", 7, _seed.DECLINED, A)],
            "after a conflict the stored disposition was applied a second "
            "time — the state moved for a reason this turn cannot see, and "
            "forcing (A, 7) onto it writes a disposition against a tuple "
            "that no longer exists")

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
