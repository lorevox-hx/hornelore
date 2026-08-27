"""One topic reaches Lori, and nothing else changes.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 step 4 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_composer_section

**Runs on BOTH interpreters with zero skips.**

*(This module first carried a `skipUnless(_HAS_FASTAPI)` on every class,
with a header claiming "prompt_composer's import chain reaches fastapi".
That was simply wrong — `prompt_composer` imports cleanly without it,
verified by importing it under `.venv`. The gate hid all 35 tests on an
interpreter perfectly capable of running them, which is worse than a
missing test: it reports OK. Removed.)*

── THIS IS THE FIRST CHANGE TO WHAT LORI IS TOLD ─────────────────────

Steps 1–3 moved code and added a service nothing imported. This step
puts text in the prompt, so the tests are shaped around the two ways
that goes wrong:

  1. **the new section says the wrong thing** — asks two questions,
     asks a question it was told to acknowledge, invents a topic, or
     keeps its own copy of the ten-question list;
  2. **the new section changes something else** — and this is the
     dangerous one, because it is invisible in review.

The second is why byte-stability is asserted rather than argued.
`prompt_composer.py:3942` opens `if runtime71:`, and inside it `:4100`
reads `identity_complete` with a default of `False`, which makes
`identity_mode` True. A caller supplying a SPARSE runtime object just
to carry onboarding state would flip Lori into identity interrogation —
asking a narrator she has known for months for their name, because a
dict gained a key. Several tests below exist only to prove that adding
onboarding state adds a section and moves nothing else.
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

from api import prompt_composer as _pc  # noqa: E402
from api.services import profile_seed as _seed  # noqa: E402
from api.services import profile_seed_turn as _turn  # noqa: E402

KEY = "profile_seed_onboarding"
A = "childhood_home"
B = "siblings"

#: A full, realistic runtime object — an identity-complete narrator mid
#: interview. Used as the "existing prompt" whose bytes must not move.
FULL_RUNTIME = {
    "person_id": "p-fixture",
    "current_pass": "pass2a",
    "current_era": "school_years",
    "current_mode": "open",
    "identity_complete": True,
    "identity_phase": "complete",
    "assistant_role": "interviewer",
    "speaker_name": "Verlie",
    "dob": "1936-11-08",
    "pob": "Devils Lake, North Dakota",
}


def onboarding(action, topic_id=None, known=(), remaining=(),
               completes_walk=False):
    return {"action": action, "topic_id": topic_id,
            "known_topics": list(known), "remaining_topics": list(remaining),
            "completes_walk": completes_walk}


class SectionRenderTests(unittest.TestCase):
    """What the block says, given a plan."""

    def block(self, state):
        return _pc._profile_seed_onboarding_block({KEY: state})

    def test_present_asks_exactly_one_registry_question(self):
        text = self.block(onboarding("present", A, remaining=[A, B]))
        self.assertIn(_seed.topic(A).question, text)
        for other in _seed.TOPIC_IDS:
            if other == A:
                continue
            with self.subTest(other=other):
                self.assertNotIn(_seed.topic(other).question, text,
                                 "more than one topic reached the prompt")

    def test_every_registry_topic_renders_when_it_is_active(self):
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                text = self.block(onboarding("present", topic_id,
                                             remaining=[topic_id, B]))
                self.assertIn(_seed.topic(topic_id).question, text)

    def test_re_present_asks_the_same_topic_and_says_so(self):
        text = self.block(onboarding("re_present", B, remaining=[B]))
        self.assertIn(_seed.topic(B).question, text)
        self.assertIn("asked for a moment", text)

    def test_acknowledge_asks_nothing_at_all(self):
        """The acknowledgement turn is the one most likely to regress.

        It must not re-ask the answered topic and must not ask the next
        one — until the post-commit apply succeeds, the next topic is a
        prediction rather than a fact.
        """
        text = self.block(onboarding("acknowledge", A))
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, text)
        self.assertIn("ACKNOWLEDGE ONLY", text)
        self.assertIn("Do NOT ask the next Profile Seed question", text)

    def test_known_topics_are_named_so_they_are_not_re_asked(self):
        text = self.block(onboarding("present", B, known=[A],
                                     remaining=[B]))
        self.assertIn(_seed.topic(A).intent, text)
        self.assertNotIn(_seed.topic(A).question, text,
                         "a settled topic was re-asked as a question")

    def test_the_last_remaining_topic_says_it_is_the_last(self):
        """A neutral heads-up now — see CompletionTransitionTests for why
        the closing instruction moved to the acknowledgement turn."""
        text = self.block(onboarding("present", "life_stage",
                                     remaining=["life_stage"]))
        self.assertIn("last topic still open", text)

    def test_a_mid_walk_topic_does_not_claim_to_be_the_last(self):
        text = self.block(onboarding("present", A, remaining=[A, B]))
        self.assertNotIn("last topic still open", text)

    # ── silence, in every shape that must produce it ────────────────
    def test_idle_and_malformed_states_render_nothing(self):
        for state in (onboarding("idle"), {}, {"action": "present"},
                      {"action": "present", "topic_id": "favourite_colour"},
                      {"action": "banana", "topic_id": A},
                      {"action": None, "topic_id": A},
                      "not a dict", None, 3, []):
            with self.subTest(state=state):
                self.assertEqual(
                    _pc._profile_seed_onboarding_block({KEY: state}), "")

    def test_an_IDLE_action_with_a_VALID_topic_renders_nothing(self):
        """The idle case that a topic check cannot catch.

        `onboarding("idle")` has `topic_id=None`, so the topic guard
        rejects it and the ACTION guard is never exercised. A plan that
        is idle but carries a perfectly valid topic is the case that
        proves the action guard does its own work.
        """
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertEqual(
                    self.block({"action": "idle", "topic_id": topic_id}), "")

    def test_an_absent_key_and_an_absent_runtime_render_nothing(self):
        self.assertEqual(_pc._profile_seed_onboarding_block({}), "")
        self.assertEqual(_pc._profile_seed_onboarding_block(None), "")
        self.assertEqual(_pc._profile_seed_onboarding_block("junk"), "")

    def test_unknown_topics_in_known_and_remaining_are_ignored(self):
        text = self.block(onboarding("present", A,
                                     known=["favourite_colour", "siblings"],
                                     remaining=[A, "not_a_topic"]))
        self.assertNotIn("favourite_colour", text)
        self.assertNotIn("not_a_topic", text)
        self.assertIn(_seed.topic("siblings").intent, text)

    def test_the_block_contains_no_narrator_prose(self):
        """It is built from the registry and the plan, never from text.

        The plan carries no narrator words (asserted in the reducer
        suite); this asserts the composer adds none either.
        """
        text = self.block(onboarding("present", A, known=[B], remaining=[A]))
        for word in ("Devils Lake", "Verlie", "1936"):
            self.assertNotIn(word, text)


class CompletionTransitionTests(unittest.TestCase):
    """The walk ends warmly, on the turn that can actually say so."""

    def block(self, state):
        return _pc._profile_seed_onboarding_block({KEY: state})

    #: Words that would be an authoritative claim about server state.
    FORBIDDEN_CLAIMS = ("LAST", "last thing", "complete", "completed",
                        "finished", "done with", "all the questions")

    def test_a_completing_acknowledgement_is_WARM_not_authoritative(self):
        """Soft relational wording only. No state claim.

        *(This asserted "LAST thing you needed" was PRESENT. That was a
        claim about the server, made before the versioned apply, and it
        can be false — see the conflict test below.)*
        """
        text = self.block(onboarding("acknowledge", A, completes_walk=True))
        self.assertIn("good sense of their story", text)
        self.assertIn("ready to hear it properly", text)

    def test_a_completing_acknowledgement_claims_NOTHING_about_state(self):
        text = self.block(onboarding("acknowledge", A, completes_walk=True))
        for word in self.FORBIDDEN_CLAIMS:
            with self.subTest(word=word):
                self.assertNotIn(
                    word, text,
                    f"the acknowledgement claims {word!r} — that is a "
                    "statement about server state made BEFORE the versioned "
                    "apply, and a conflict can make it false")

    def test_a_STALE_VERSION_completion_still_claims_nothing(self):
        """THE CONCURRENCY CASE, end to end.

        1. Lori presents A at version 7.
        2. The narrator answers; the plan says this completes the walk.
        3. Meanwhile evidence moves the server to version 8, A still
           active — so applying (A, 7) will CONFLICT and write nothing.
        4. The next turn presents A again.

        If the acknowledgement had claimed completion, the narrator
        would have been told they were finished and then asked the same
        question again. The claim is gone, so the only cost of the
        conflict is one repeated question — which the recovery stage
        exists to avoid and which is survivable when it happens.
        """
        state = {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                 "active_topic_id": A, "version": 7,
                 "known_topics": [t for t in _seed.TOPIC_IDS if t != A],
                 "remaining_topics": [A]}
        history = [{"role": "assistant",
                    "meta": {_turn.PRESENTED_TOPIC: A,
                             _turn.PRESENTED_VERSION: 7}},
                   {"role": "user", "content": "Still working.", "meta": {}}]
        plan = _turn.plan_turn(state=state, history=history,
                               narrator_text="Still working.")
        self.assertTrue(plan.completes_walk)
        self.assertEqual(plan.version, 7)

        text = self.block({"action": plan.action, "topic_id": plan.topic_id,
                           "known_topics": state["known_topics"],
                           "remaining_topics": state["remaining_topics"],
                           "completes_walk": plan.completes_walk})
        for word in self.FORBIDDEN_CLAIMS:
            with self.subTest(word=word):
                self.assertNotIn(word, text)

        # The server moved to 8 underneath. Applying (A, 7) conflicts and
        # writes nothing, so A is still active and gets presented again.
        moved = dict(state, version=8)
        nxt = _turn.plan_turn(state=moved, history=history + [
            {"role": "assistant",
             "meta": {_turn.RESPONSE_TOPIC: A, _turn.RESPONSE_VERSION: 7,
                      _turn.RESPONSE_DISPOSITION: _seed.ADDRESSED}}],
            narrator_text="Hello again")
        self.assertIn(nxt.action, (_turn.PRESENT, _turn.RE_PRESENT))
        self.assertEqual(nxt.topic_id, A,
                         "the conflicted topic must still be asked — this "
                         "is why the acknowledgement must not have claimed "
                         "the walk was over")

    def test_a_completing_acknowledgement_STILL_asks_nothing(self):
        """Closing warmly must not become an eleventh question."""
        text = self.block(onboarding("acknowledge", A, completes_walk=True))
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, text)
        self.assertIn("Do NOT ask another question of any kind", text)

    def test_a_NON_BOOLEAN_completes_walk_does_not_claim_completion(self):
        """A loose comparison would let a caller make Lori tell the
        narrator her walk is over when the plan never said so."""
        for value in ("yes", 1, "true", [1], {"a": 1}, "False"):
            with self.subTest(value=value):
                text = self.block({"action": "acknowledge", "topic_id": A,
                                   "completes_walk": value})
                self.assertEqual(
                    text, "",
                    "a non-Boolean completes_walk must make the whole plan "
                    "invalid, not merely soften one line")

    def test_an_ordinary_acknowledgement_does_not_claim_completion(self):
        text = self.block(onboarding("acknowledge", A, completes_walk=False))
        self.assertNotIn("good sense of their story", text)
        self.assertIn("Do NOT ask the next Profile Seed question", text)

    def test_the_ASKING_turn_no_longer_makes_an_unreachable_promise(self):
        """*(The presentation block used to say "when they have
        answered, tell them warmly that you now have a sense of their
        story" on the turn that ASKED the last question. That describes
        the NEXT turn, by which point the block is gone — Lori could not
        keep it. It is a neutral heads-up now, and the instruction that
        can be acted on rides on the acknowledgement.)*"""
        text = self.block(onboarding("present", "life_stage",
                                     remaining=["life_stage"]))
        self.assertIn("last topic still open", text)
        self.assertNotIn("when they have answered", text.lower())
        self.assertNotIn("sense of their story", text)

    def test_the_plan_and_the_prompt_agree_end_to_end(self):
        """The reducer's own completes_walk drives the block."""
        state = {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                 "active_topic_id": A, "version": 7,
                 "known_topics": [t for t in _seed.TOPIC_IDS if t != A],
                 "remaining_topics": [A]}
        history = [{"role": "assistant",
                    "meta": {_turn.PRESENTED_TOPIC: A,
                             _turn.PRESENTED_VERSION: 7}},
                   {"role": "user", "content": "Still working.", "meta": {}}]
        plan = _turn.plan_turn(state=state, history=history,
                               narrator_text="Still working.")
        self.assertTrue(plan.completes_walk)
        text = self.block({"action": plan.action, "topic_id": plan.topic_id,
                           "known_topics": state["known_topics"],
                           "remaining_topics": state["remaining_topics"],
                           "completes_walk": plan.completes_walk})
        self.assertIn("good sense of their story", text)


class NoSecondTopicListTests(unittest.TestCase):
    """`TOPIC_REGISTRY` is the ONLY list of questions in the system."""

    def setUp(self):
        self.source = (_SERVER_CODE / "api" / "prompt_composer.py").read_text(
            encoding="utf-8")

    def test_the_composer_source_contains_ZERO_registry_questions(self):
        """The structural requirement, stated as zero rather than one.

        *(This first asserted "at most once" and, separately, that each
        question string WAS present — which together permitted exactly
        the defect review found: the wording moved to the registry while
        the complete ordered ten-item list stayed hard-coded here, kept
        identical only by a test comparing strings. Two hand-written
        authorities is what §4.1 forbids, and "at most once" could never
        have caught it.)*
        """
        offenders = [t.topic_id for t in _seed.TOPIC_REGISTRY
                     if t.question in self.source]
        self.assertEqual(
            offenders, [],
            "these question strings are literals in prompt_composer.py — "
            "the composer is keeping a second hand-written list instead of "
            "rendering from TOPIC_REGISTRY: " + ", ".join(offenders))

    def test_the_legacy_list_is_generated_from_the_registry(self):
        self.assertIn("_legacy_profile_seed_question_list()", self.source)
        generated = _pc._legacy_profile_seed_question_list()
        for number, topic_def in enumerate(_seed.TOPIC_REGISTRY, 1):
            with self.subTest(topic=topic_def.topic_id):
                self.assertIn(f"{number:>3}. {topic_def.question}", generated)

    def test_reordering_the_registry_reorders_the_legacy_list(self):
        """Non-vacuity: prove the list really is derived.

        A generator that happened to emit the same constant text would
        pass every assertion above. This one cannot.
        """
        original = _seed.TOPIC_REGISTRY
        try:
            _seed.TOPIC_REGISTRY = tuple(reversed(original))
            reordered = _pc._legacy_profile_seed_question_list()
        finally:
            _seed.TOPIC_REGISTRY = original
        self.assertIn(f"  1. {original[-1].question}", reordered)
        self.assertNotEqual(reordered,
                            _pc._legacy_profile_seed_question_list())

    def test_every_registry_topic_has_a_question(self):
        for topic_def in _seed.TOPIC_REGISTRY:
            with self.subTest(topic=topic_def.topic_id):
                self.assertTrue(topic_def.question.strip())


class LegacyBlockGoldenBytesTests(unittest.TestCase):
    """The historical block's rendered bytes are unchanged.

    Generating the list from the registry must not reflow it. The hash
    below was measured from the rendered prompt BEFORE the change, so it
    pins the previous bytes rather than the current implementation's
    opinion of them — including the right-aligned numbering that gives
    item 10 one leading space where items 1–9 have two.
    """

    #: FULL sha256 of the rendered `PROFILE SEED QUESTIONS ...` block,
    #: measured at `620d692` before generation was introduced.
    #:
    #: *(This stored and compared `hexdigest()[:16]` — a truncated
    #: 64-bit digest presented as SHA-256 evidence. Truncation is not
    #: free: it is the difference between a collision being infeasible
    #: and merely unlikely, and the claim in the name was stronger than
    #: the check underneath it. All 64 characters now.)*
    GOLDEN_SHA256 = ("c5b4f9e74ca07c2b213f2694cda41b9e"
                     "7b8ebf44cb1e4686b6f71c7a1e6bcfc7")

    def _rendered_block(self):
        runtime = dict(FULL_RUNTIME)
        runtime["current_pass"] = "pass1"
        text = _pc.compose_system_prompt("golden", runtime71=runtime)
        start = text.index("PROFILE SEED QUESTIONS")
        return text[start:text.index("RULES:", start)]

    def test_the_rendered_block_matches_the_golden_hash(self):
        import hashlib
        digest = hashlib.sha256(
            self._rendered_block().encode("utf-8")).hexdigest()
        self.assertEqual(
            digest, self.GOLDEN_SHA256,
            "the historical Pass-1 question block changed bytes. Every "
            "pre-migration narrator sees this block and only this block, "
            "so a reflow is a silent behaviour change for all of them.")

    def test_item_ten_keeps_its_single_leading_space(self):
        block = self._rendered_block()
        self.assertIn("\n  1. ", block)
        self.assertIn("\n 10. ", block)
        self.assertNotIn("\n  10. ", block)

    def test_the_block_still_lists_all_ten_in_registry_order(self):
        block = self._rendered_block()
        positions = [block.index(t.question) for t in _seed.TOPIC_REGISTRY]
        self.assertEqual(positions, sorted(positions),
                         "the legacy list is no longer in registry order")


class ByteStabilityTests(unittest.TestCase):
    """Onboarding state adds the section and moves NOTHING else.

    ── THE SUBSET ASSERTION WAS THE WRONG PROPERTY, 2026-08-26 ─────────

    *(These tests first asserted only that every baseline line still
    appeared SOMEWHERE in the new prompt. Review measured what that
    actually permitted: no runtime at all renders 7,365 characters; a
    sparse onboarding runtime renders 23,023; the onboarding block
    itself is 557. So 15,101 characters of unrelated runtime content —
    identity grounding, LORI_RUNTIME, English-first rules, interview
    discipline, default pass/era/mode values — arrived, and every
    assertion still passed.*

    *A subset test cannot express "old prompt PLUS exactly this
    section". These compare bytes and section lists instead.)*
    """

    def compose(self, runtime=None):
        return _pc.compose_system_prompt("conv-stability", runtime71=runtime)

    def sections(self, runtime=None):
        composed = _pc.compose_prompt_sections("conv-stability",
                                               runtime71=runtime)
        return [(sec.name, sec.text) for sec in composed.sections]

    # ── malformed and idle: BYTE-IDENTICAL to the key being absent ──
    def test_malformed_state_is_byte_identical_to_no_key(self):
        """THE DEFECT REVIEW FOUND, as an equality.

        `{"action": "present", "topic_id": "bad"}` rendered no block —
        correctly — while the suppression predicate returned True
        anyway, so the legacy pass directive vanished and nothing
        replaced it. Malformed state must leave the ENTIRE prompt
        untouched, not quietly remove working instructions.
        """
        baseline = self.compose(dict(FULL_RUNTIME))
        malformed = (
            {"action": "present", "topic_id": "bad"},
            {"action": "present", "topic_id": None},
            {"action": "present"},
            {"action": "re_present", "topic_id": "not_a_topic"},
            {"action": "acknowledge", "topic_id": "bad"},
            {"action": "acknowledge"},
            {"action": "banana", "topic_id": A},
            {"action": None, "topic_id": A},
            {}, "not a dict", None, 3, [],
        )
        for state in malformed:
            with self.subTest(state=state):
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = state
                self.assertEqual(
                    self.compose(runtime), baseline,
                    "malformed onboarding state changed the prompt — it must "
                    "be indistinguishable from the key being absent")

    def test_malformed_state_leaves_the_section_list_identical(self):
        baseline = self.sections(dict(FULL_RUNTIME))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = {"action": "present", "topic_id": "bad"}
        self.assertEqual(self.sections(runtime), baseline)

    def test_idle_state_is_byte_identical_to_no_key(self):
        baseline = self.compose(dict(FULL_RUNTIME))
        for state in (onboarding("idle"), {}, None):
            with self.subTest(state=state):
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = state
                self.assertEqual(self.compose(runtime), baseline)

    def test_pending_paused_completed_plans_are_byte_identical(self):
        """Every non-active lifecycle reduces to an IDLE plan, and an
        idle plan must be invisible."""
        baseline = self.compose(dict(FULL_RUNTIME))
        for status in (_seed.STATUS_PENDING, _seed.STATUS_PAUSED,
                       _seed.STATUS_COMPLETED):
            state = {"person_id": "p1", "status": status,
                     "active_topic_id": A, "version": 7,
                     "known_topics": [], "remaining_topics": [A]}
            plan = _turn.plan_turn(state=state, history=[],
                                   narrator_text="Hi")
            with self.subTest(status=status):
                self.assertEqual(plan.action, _turn.IDLE)
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = {"action": plan.action,
                                "topic_id": plan.topic_id,
                                "known_topics": [], "remaining_topics": []}
                self.assertEqual(self.compose(runtime), baseline)

    # ── active: exactly one section added, one deliberately replaced ──
    def test_an_active_plan_adds_ONLY_the_canonical_section(self):
        baseline = dict(self.sections(dict(FULL_RUNTIME)))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        active = dict(self.sections(runtime))

        added = set(active) - set(baseline)
        self.assertEqual(added, {"profile_seed_onboarding"},
                         "an active plan added sections other than the "
                         "canonical onboarding block")

        for name, text in baseline.items():
            with self.subTest(section=name):
                if name == "directives_interview":
                    continue
                self.assertEqual(active.get(name), text,
                                 f"section {name!r} changed bytes")

    def test_section_ORDER_is_unchanged_apart_from_the_addition(self):
        baseline = [n for n, _ in self.sections(dict(FULL_RUNTIME))]
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        active = [n for n, _ in self.sections(runtime)]
        self.assertEqual([n for n in active if n != "profile_seed_onboarding"],
                         baseline,
                         "adding the onboarding section reordered the prompt")

    def test_the_only_changed_section_is_the_pass_directive(self):
        """The one deliberate replacement, named and bounded.

        Supervisory boundary 1: a valid server-authoritative plan
        overrides the browser's opinion of the pass. Rendering both
        would hand Lori the canonical question AND "ask ONE open,
        place-anchored question about this era".
        """
        baseline = dict(self.sections(dict(FULL_RUNTIME)))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        active = dict(self.sections(runtime))
        changed = [n for n in baseline if active.get(n) != baseline[n]]
        self.assertEqual(changed, ["directives_interview"],
                         "something other than the pass directive changed")
        self.assertIn("Pass 2A", baseline["directives_interview"])
        self.assertNotIn("Pass 2A", active["directives_interview"])

    def test_an_acknowledge_plan_adds_only_its_own_section(self):
        baseline = dict(self.sections(dict(FULL_RUNTIME)))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("acknowledge", A)
        active = dict(self.sections(runtime))
        self.assertEqual(set(active) - set(baseline),
                         {"profile_seed_onboarding"})

    # ── the sparse-runtime trap ─────────────────────────────────────
    def test_a_sparse_runtime_must_supply_a_truthful_identity_result(self):
        """Step 4 briefly INFERRED identity from the payload. Withdrawn.

        Phase 1 holds the row at `pending` until the anchors exist, so
        `active` implies them — of the DATABASE ROW. It implies nothing
        about a dict a caller put in `runtime71`, and inferring a
        gate-shaped fact from an unvalidated payload is the wrong
        direction of trust. Step 5 supplies the real server-derived
        result (transport map §10); a test may state it truthfully.
        """
        sparse = {"person_id": "p-fixture",
                  "identity_complete": True,
                  KEY: onboarding("present", A, remaining=[A])}
        text = self.compose(sparse)
        self.assertIn(_seed.topic(A).question, text)
        for phrase in ("single next missing piece of identity",
                       "name, date of birth, and place of birth are all "
                       "confirmed"):
            with self.subTest(phrase=phrase[:30]):
                self.assertNotIn(phrase, text)

    def test_an_untruthful_sparse_runtime_does_NOT_get_identity_for_free(self):
        """The inference stays withdrawn.

        Omitting `identity_complete` must leave identity mode ON. If a
        caller can switch it off by supplying two onboarding keys, the
        gate is not a gate.
        """
        sparse = {"person_id": "p-fixture",
                  KEY: onboarding("present", A, remaining=[A])}
        text = self.compose(sparse)
        self.assertIn("single next missing piece of identity", text,
                      "onboarding state switched off identity mode without "
                      "a server-derived identity result")

    def test_no_runtime_at_all_still_composes(self):
        self.assertTrue(self.compose(None))


class LegacyBlockSuppressionTests(unittest.TestCase):
    """Two lists must never both render."""

    def _pass1_runtime(self, **extra):
        runtime = dict(FULL_RUNTIME)
        runtime["current_pass"] = "pass1"
        runtime.update(extra)
        return runtime

    def test_a_historical_narrator_still_gets_the_legacy_block(self):
        """No onboarding row means no key. Decision 3: they are never
        enrolled, so the legacy block is the only Profile Seed behaviour
        they have, and removing it would change every pre-migration
        narrator.

        *(This asserted ONE phrase was present, which would pass with
        the ten questions gone. It compares the whole rendered prompt to
        the same runtime with an explicitly absent key, and pins the
        question block by hash.)*
        """
        import hashlib
        runtime = self._pass1_runtime()
        text = _pc.compose_system_prompt("conv-legacy", runtime71=runtime)

        explicit_absent = dict(runtime)
        explicit_absent.pop(KEY, None)
        self.assertEqual(
            text,
            _pc.compose_system_prompt("conv-legacy",
                                      runtime71=explicit_absent))

        self.assertIn("Gather the following 10 facts", text)
        start = text.index("PROFILE SEED QUESTIONS")
        block = text[start:text.index("RULES:", start)]
        self.assertEqual(
            hashlib.sha256(block.encode("utf-8")).hexdigest(),
            LegacyBlockGoldenBytesTests.GOLDEN_SHA256,
            "the historical narrator's question block changed bytes")
        for topic_def in _seed.TOPIC_REGISTRY:
            with self.subTest(topic=topic_def.topic_id):
                self.assertIn(topic_def.question, block)

    def test_an_enrolled_narrator_gets_the_canonical_block_only(self):
        runtime = self._pass1_runtime()
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        text = _pc.compose_system_prompt("conv-enrolled", runtime71=runtime)
        self.assertIn("PROFILE SEED — ONE QUESTION", text)
        self.assertNotIn(
            "Gather the following 10 facts", text,
            "both topic lists rendered — Lori was handed one canonical "
            "question AND an instruction to gather ten facts")
        self.assertEqual(text.count(_seed.topic(A).question), 1)

    def test_an_acknowledge_turn_also_suppresses_the_legacy_block(self):
        runtime = self._pass1_runtime()
        runtime[KEY] = onboarding("acknowledge", A)
        text = _pc.compose_system_prompt("conv-ack", runtime71=runtime)
        self.assertNotIn("Gather the following 10 facts", text)
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, text)

    def test_an_idle_plan_leaves_the_legacy_block_intact(self):
        """Idle is not enrolment. A pending or paused narrator on the
        legacy pass-1 path behaves exactly as before."""
        runtime = self._pass1_runtime()
        runtime[KEY] = onboarding("idle")
        text = _pc.compose_system_prompt("conv-idle", runtime71=runtime)
        self.assertIn("Gather the following 10 facts", text)


class SectionPolicyTests(unittest.TestCase):
    """Budgeting goes through the existing named-section machinery."""

    def test_the_section_is_registered_with_a_policy(self):
        from api.services import prompt_section_policy as _policy
        self.assertIn("profile_seed_onboarding", _policy.known_section_ids())

    def test_the_section_is_never_trimmed(self):
        """Step 6 stamps a `presented` event on the turn that ASKS. If
        the budget could drop this block, the event would record a
        question Lori never asked, and the reducer would wait for an
        answer to it forever."""
        from api.services import prompt_section_policy as _policy
        policy = _policy.policy_for("profile_seed_onboarding")
        self.assertEqual(policy.trim_policy, _policy.TRIM_NEVER)

    def test_the_section_appears_in_the_classified_assembly(self):
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A])
        composed = _pc.compose_prompt_sections("conv-sections",
                                               runtime71=runtime)
        names = [s.name for s in composed.sections]
        self.assertIn("profile_seed_onboarding", names)

    def test_the_section_is_absent_from_the_assembly_when_idle(self):
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("idle")
        composed = _pc.compose_prompt_sections("conv-sections-idle",
                                               runtime71=runtime)
        names = [s.name for s in composed.sections]
        self.assertNotIn("profile_seed_onboarding", names)

    def test_rendered_text_and_the_string_entry_point_agree(self):
        """Both public entry points go through one assembly, so a
        section added to one cannot be missing from the other."""
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A])
        self.assertEqual(
            _pc.compose_prompt_sections("conv-agree", runtime71=runtime).text,
            _pc.compose_system_prompt("conv-agree", runtime71=runtime))


class LegacyProfileSeedKeyUntouchedTests(unittest.TestCase):
    """`runtime71["profile_seed"]` is load-bearing and is NOT this key."""

    def test_the_new_key_is_distinct(self):
        self.assertNotEqual(_pc.PROFILE_SEED_ONBOARDING_KEY, "profile_seed")

    def test_onboarding_state_does_not_disturb_the_legacy_seed(self):
        runtime = dict(FULL_RUNTIME)
        runtime["profile_seed"] = {"preferred_name": "Verlie",
                                   "age_years": 89,
                                   "life_stage": "senior elder"}
        baseline = _pc.compose_system_prompt("conv-seed", runtime71=runtime)

        with_onboarding = dict(runtime)
        with_onboarding[KEY] = onboarding("present", A, remaining=[A])
        text = _pc.compose_system_prompt("conv-seed", runtime71=with_onboarding)

        self.assertEqual(runtime["profile_seed"],
                         {"preferred_name": "Verlie", "age_years": 89,
                          "life_stage": "senior elder"},
                         "the composer mutated the legacy profile_seed dict")
        # Everything the legacy seed contributed still appears. The pass
        # directive is deliberately replaced (see the byte-stability
        # suite); nothing the seed produced is.
        head = baseline.split("DIRECTIVE: You are in Pass 2A")[0]
        for line in head.splitlines():
            if line.strip():
                self.assertIn(line, text,
                              "adding onboarding state changed what the "
                              "legacy profile_seed contributed")
        for value in ("Verlie", "89", "senior elder"):
            with self.subTest(value=value):
                if value in baseline:
                    self.assertIn(value, text,
                                  "a legacy profile_seed value vanished when "
                                  "onboarding state was added")


class PlanToPromptTests(unittest.TestCase):
    """The reducer's own output drives the composer, unmodified."""

    def _runtime_from_plan(self, plan, state):
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = {
            "action": plan.action,
            "topic_id": plan.topic_id,
            "known_topics": state["known_topics"],
            "remaining_topics": state["remaining_topics"],
        }
        return runtime

    def _state(self, active=A, version=7):
        return {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                "active_topic_id": active, "version": version,
                "known_topics": [], "remaining_topics": list(_seed.TOPIC_IDS)}

    def test_a_first_turn_plan_produces_one_question(self):
        state = self._state()
        plan = _turn.plan_turn(state=state, history=[], narrator_text="Hello")
        text = _pc.compose_system_prompt(
            "conv-plan", runtime71=self._runtime_from_plan(plan, state))
        self.assertIn(_seed.topic(A).question, text)

    def test_an_answer_turn_plan_produces_an_acknowledgement(self):
        state = self._state()
        history = [{"role": "assistant", "meta": {
                        _turn.PRESENTED_TOPIC: A, _turn.PRESENTED_VERSION: 7}},
                   {"role": "user", "content": "Devils Lake.", "meta": {}}]
        plan = _turn.plan_turn(state=state, history=history,
                               narrator_text="Devils Lake.")
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        text = _pc.compose_system_prompt(
            "conv-plan-ack", runtime71=self._runtime_from_plan(plan, state))
        self.assertIn("ACKNOWLEDGE ONLY", text)
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, text)

    def test_an_idle_plan_produces_no_section(self):
        state = self._state()
        state["status"] = _seed.STATUS_PAUSED
        plan = _turn.plan_turn(state=state, history=[], narrator_text="Hi")
        self.assertEqual(plan.action, _turn.IDLE)
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = {"action": plan.action, "topic_id": plan.topic_id,
                        "known_topics": [], "remaining_topics": []}
        composed = _pc.compose_prompt_sections("conv-plan-idle",
                                               runtime71=runtime)
        self.assertNotIn("profile_seed_onboarding",
                         [s.name for s in composed.sections])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
