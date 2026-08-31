"""A presentation event may only follow a question the narrator received.

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_presentation_delivery

── THE DEFECT ────────────────────────────────────────────────────────

Live, 2026-08-30. Narrator `c6f78b9b-612e-43d7-a518-9bc2fbc45995`,
conversation `switch_mtgkaq7n_ilpl`. The server planned and committed:

    presented(childhood_home, epoch 2)

while Lori's visible words were:

    "We've touched on several parts of your story. Where would you like
     to continue today?"

She never asked about a childhood home. The narrator's next, unrelated
message — "Please go ahead and ask me whatever is next" — was correlated
against that phantom presentation, recorded `childhood_home` as
ADDRESSED, and advanced the walk. `addressed` is DURABLE: the topic is
closed permanently, and the narrator was never asked it.

For a narrator who may have cognitive decline, that is their account of
their own childhood home silently deleted from the walk.

── WHY A PROMPT INSTRUCTION IS NOT THE FIX ───────────────────────────

The composer already told the model to ask only the canonical question.
The model ignored it, which is the one thing a prompt instruction can
always do. So the question sentence is the SERVER'S and is delivered by
construction — `finalize_presentation` builds the narrator-visible text,
and `delivers_question` decides whether metadata may be stamped.

Nothing here judges whether model prose is "close enough". There is no
semantic comparison in the implementation or in this file: interrogative
sentences are removed, the canonical sentence is appended, and the stamp
follows a containment check against the server's own string.
"""
from __future__ import annotations

import re
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

A = _seed.TOPIC_IDS[0]      # childhood_home
B = _seed.TOPIC_IDS[1]      # siblings

GENERIC = ("We've touched on several parts of your story. "
           "Where would you like to continue today?")


def present(topic=A, version=7, epoch=2):
    return _turn.TurnPlan(_turn.PRESENT, topic, version, epoch=epoch)


def re_present(topic=A, version=7, epoch=2):
    return _turn.TurnPlan(_turn.RE_PRESENT, topic, version, epoch=epoch)


class NarratorQuestionRegistryTests(unittest.TestCase):
    """The ten strings the narrator actually hears.

    The old `question` field was documented as narrator-facing and was
    nothing of the kind — ALL-CAPS labels, third person, a
    `[their birthplace]` placeholder, an operator aside, and two compound
    questions the atomicity rule forbids. These assertions exist so that
    cannot recur silently on `narrator_question`.
    """

    def setUp(self):
        self.questions = {t.topic_id: t.narrator_question
                          for t in _seed.TOPIC_REGISTRY}

    def test_every_topic_has_one(self):
        self.assertEqual(len(self.questions), 10)
        for tid, q in self.questions.items():
            with self.subTest(topic=tid):
                self.assertTrue(q and q.strip(), f"{tid} has no question")

    def test_all_are_distinct(self):
        values = list(self.questions.values())
        self.assertEqual(len(values), len(set(values)))

    def test_each_ends_with_exactly_one_question_mark(self):
        """One question, and it IS a question."""
        for tid, q in self.questions.items():
            with self.subTest(topic=tid):
                self.assertTrue(q.rstrip().endswith("?"), f"{tid}: {q!r}")
                self.assertEqual(1, q.count("?"),
                                 f"{tid} asks more than one thing: {q!r}")

    def test_no_bracketed_placeholder(self):
        """`[their birthplace]` reached the registry once. Never again."""
        for tid, q in self.questions.items():
            with self.subTest(topic=tid):
                self.assertNotRegex(q, r"[\[\{]", f"{tid}: {q!r}")

    def test_no_all_caps_label_prefix(self):
        """`CHILDHOOD HOME — ` is a prompt directive, not speech."""
        for tid, q in self.questions.items():
            with self.subTest(topic=tid):
                self.assertIsNone(
                    re.match(r"^[A-Z][A-Z' ]{2,}\s*[—-]", q),
                    f"{tid} carries a label prefix: {q!r}")

    def test_no_operator_aside(self):
        """`(Ask warmly — many older narrators did.)` was in `military`."""
        for tid, q in self.questions.items():
            with self.subTest(topic=tid):
                self.assertNotIn("(", q, f"{tid}: {q!r}")

    def test_second_person_never_third(self):
        """The narrator is `you`, not `they`."""
        for tid, q in self.questions.items():
            with self.subTest(topic=tid):
                lowered = q.lower()
                for banned in (" they ", " their ", " them ",
                               "they ", "their "):
                    self.assertNotIn(
                        banned, " " + lowered,
                        f"{tid} refers to the narrator in third person: {q!r}")
                self.assertRegex(lowered, r"\byou\b|\byour\b",
                                 f"{tid} never addresses the narrator: {q!r}")

    def test_the_directive_field_is_still_present_for_the_composer(self):
        """`question` is retained deliberately, and is NOT speech."""
        for t in _seed.TOPIC_REGISTRY:
            with self.subTest(topic=t.topic_id):
                self.assertTrue(t.question)
                self.assertNotEqual(t.question, t.narrator_question)


class FinalizationTests(unittest.TestCase):
    """Cases 1-3: what the narrator receives."""

    def test_generic_model_prose_does_not_become_the_question(self):
        """CASE 1 + 2 — the exact live failure, as a test.

        The model returns generic prose ending in its own question. The
        narrator must receive the canonical question instead.
        """
        out = _turn.finalize_presentation(GENERIC, present())
        self.assertIn(_seed.topic(A).narrator_question, out)
        self.assertNotIn("Where would you like to continue today?", out)

    def test_only_one_question_is_delivered(self):
        """CASE 3 — the model's question and the server's must not stack.

        Two questions in one turn is what the ONE THOUGHT, ONE QUESTION
        rule forbids, and what an older narrator experiences as being
        asked two things at once.
        """
        out = _turn.finalize_presentation(GENERIC, present())
        self.assertEqual(1, out.count("?"), out)

    def test_a_declarative_reflection_is_kept_as_a_lead_in(self):
        """Lori still sounds like Lori. Only the question is fixed."""
        out = _turn.finalize_presentation(
            "That sounds like a warm memory.", present())
        self.assertTrue(out.startswith("That sounds like a warm memory."))
        self.assertTrue(out.endswith(_seed.topic(A).narrator_question))

    def test_no_usable_lead_in_sends_the_question_alone(self):
        for prose in ("", None, "   ", "Where to next? Or somewhere else?"):
            with self.subTest(prose=prose):
                out = _turn.finalize_presentation(prose, present())
                self.assertEqual(_seed.topic(A).narrator_question, out)

    def test_a_rambling_lead_in_is_bounded_at_whole_sentences(self):
        """Bounded, and never cut mid-sentence.

        *(This first asserted the lead-in was DROPPED entirely, and the
        implementation was right and the test wrong: the sentence cap
        keeps the first two COMPLETE sentences, which is a bound rather
        than the mid-sentence truncation the name implied. Half a
        sentence would be worse than none; two whole ones are not.)*
        """
        long_prose = " ".join(["This is a very long reflection."] * 12)
        out = _turn.finalize_presentation(long_prose, present())
        self.assertTrue(out.endswith(_seed.topic(A).narrator_question))
        self.assertEqual(1, out.count("?"))
        lead = out[:-len(_seed.topic(A).narrator_question)].strip()
        self.assertLessEqual(lead.count("."), 2, lead)
        self.assertTrue(lead.endswith("."), f"lead cut mid-sentence: {lead!r}")

    def test_a_single_overlong_sentence_is_dropped(self):
        """One 60-word sentence cannot be bounded, so it goes."""
        out = _turn.finalize_presentation(
            " ".join(["word"] * 60) + ".", present())
        self.assertEqual(_seed.topic(A).narrator_question, out)

    def test_re_present_uses_the_fixed_gentle_lead_in(self):
        out = _turn.finalize_presentation("anything at all", re_present(B))
        self.assertTrue(out.startswith(_turn.RE_PRESENT_LEAD_IN))
        self.assertTrue(out.endswith(_seed.topic(B).narrator_question))
        self.assertEqual(1, out.count("?"))

    def test_a_non_presenting_action_finalizes_nothing(self):
        for action in (_turn.ACKNOWLEDGE, _turn.HOLD, _turn.IDLE):
            with self.subTest(action=action):
                plan = _turn.TurnPlan(action, A, 7, epoch=2)
                self.assertEqual("", _turn.finalize_presentation("x", plan))

    def test_an_unknown_topic_delivers_nothing(self):
        plan = _turn.TurnPlan(_turn.PRESENT, "favourite_colour", 7, epoch=2)
        self.assertEqual("", _turn.finalize_presentation("x", plan))


class StampGateTests(unittest.TestCase):
    """Cases 5, 6, 9: when metadata may be committed."""

    def test_generic_prose_is_never_a_successful_presentation(self):
        """CASE 5 — the gate that would have stopped the live defect."""
        self.assertFalse(_turn.delivers_question(GENERIC, present()))

    def test_the_finalized_text_passes_the_gate(self):
        """CASE 9 — positive control. A genuine presentation is accepted."""
        out = _turn.finalize_presentation(GENERIC, present())
        self.assertTrue(_turn.delivers_question(out, present()))

    def test_the_gate_is_topic_specific(self):
        """Delivering topic A does not license stamping topic B."""
        out = _turn.finalize_presentation("", present(A))
        self.assertTrue(_turn.delivers_question(out, present(A)))
        self.assertFalse(_turn.delivers_question(out, present(B)))

    def test_the_gate_refuses_empty_and_non_presenting_plans(self):
        self.assertFalse(_turn.delivers_question("", present()))
        self.assertFalse(_turn.delivers_question(None, present()))
        ack = _turn.TurnPlan(_turn.ACKNOWLEDGE, A, 7, epoch=2)
        self.assertFalse(
            _turn.delivers_question(_seed.topic(A).narrator_question, ack))


class RouterWiringTests(unittest.TestCase):
    """Cases 4, 6, 7, 8 — pinned over the router source.

    Driving the real handler needs fastapi, torch and a model, so the
    seam is asserted structurally. Each assertion names a property that
    would have to be deliberately removed, not one that drifts.
    """

    @classmethod
    def setUpClass(cls):
        cls.src = (_SERVER_CODE / "api" / "routers" / "chat_ws.py").read_text(
            encoding="utf-8")

    def test_delivery_runs_before_the_metadata_merge(self):
        deliver = self.src.index("[chat_ws][profile-seed][deliver]")
        merge = self.src.index("PROFILE SEED, STEP 6 — the ONE sanctioned")
        self.assertLess(deliver, merge,
                        "metadata is merged before delivery is finalized")

    def test_the_finalized_text_is_assigned_to_final_text(self):
        """CASE 4 — emitted bytes and persisted bytes are one string.

        `_buffer_mode` is unconditionally True and the deferred delta
        emits `final_text`, which is also what is persisted. Rewriting
        `final_text` here is what makes those identical rather than
        merely similar.
        """
        self.assertIn("final_text = _ps_delivered", self.src)
        self.assertIn("_buffer_mode = True", self.src)

    def test_a_failed_delivery_drops_the_metadata(self):
        self.assertEqual(2, self.src.count("_ps_planned_meta = {}"),
                         "both drop paths must survive")
        self.assertIn("delivers_question", self.src)

    def test_cancellation_still_stamps_nothing(self):
        """CASE 6 — unchanged, and asserted so it stays that way."""
        self.assertIn("_ps_cancelled_at_commit = ev.is_set()", self.src)
        self.assertIn(
            "{} if _ps_cancelled_at_commit else dict(_ps_planned_meta)",
            self.src)

    def test_acknowledge_is_not_touched_by_the_finalizer(self):
        """CASE 7 — the one natural same-topic follow-up is preserved.

        The finalizer runs only for PRESENT/RE_PRESENT. An ACKNOWLEDGE
        turn's text is never rewritten, so Chris's 2026-08-29 ruling
        that Lori may ask one natural follow-up is untouched.
        """
        self.assertIn("_ps_plan.action in (\n                _ps_turn.PRESENT, "
                      "_ps_turn.RE_PRESENT)", self.src)

    def test_no_second_persistence_path_was_added(self):
        """CASE 8's structural half — one writer, still.

        The finalizer mutates `final_text` in place before the existing
        persist call. If a new writer appears, this count moves.
        """
        self.assertEqual(1, self.src.count("final_text = _ps_delivered"))
        self.assertNotIn("_ps_persist", self.src)


if __name__ == "__main__":      # pragma: no cover
    unittest.main()
