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
#: ── ATTESTATION IS PART OF VALIDITY, Phase 3 (2026-08-29) ─────────────
#:
#: This file's subject is what the section RENDERS, not where the payload
#: came from. Phase 3 made the server attestation part of a plan's
#: validity — fail closed, so a payload no transport produced is ignored
#: entirely — which means every hand-built runtime here must now carry
#: the marker a real transport would have set. Adding it is what makes
#: these fixtures resemble production rather than a shortcut around it.
#:
#: The attestation gate itself is tested in
#: `tests/test_profile_seed_prompt_authority.py`, including the case
#: this file no longer covers: an UNATTESTED payload composing
#: byte-identically to no payload at all.
ATTEST = _pc.PROFILE_SEED_SERVER_ATTESTED_KEY
A = "childhood_home"
B = "siblings"
#: A third REAL topic id. *(These fixtures used
#: "military_service", which is not in the registry at all —
#: the id is `military`. It silently behaved as an unknown id,
#: so a "valid other topic" positive control was really
#: testing the unknown-id path, and one failure message raised
#: AttributeError while formatting itself.)*
C = "military"

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


class NoStateClaimMixin:
    """The one place that knows what an unsupported state claim is.

    *(Written twice, once per class that needed it, and the two copies
    had ALREADY drifted apart before either was committed — one knew
    about "that's all" and "we're done", the other did not. That is the
    same defect as the suppression predicate disagreeing with the
    renderer, at test-instrument scale, and it fails in the worse
    direction: the weaker copy passes and reports the prompt clean.)*

    Compared CASE-FOLDED, because a lowercase-only assertion lets
    `Complete`, `COMPLETE`, `Last` and `FINISHED` walk straight past a
    guard that then only catches the spelling I happened to think of.
    """

    #: Wording that would assert something about server state.
    FORBIDDEN_CLAIMS = ("last", "complete", "completed", "finished",
                        "done with", "all the questions", "that's all",
                        "we're done")

    def state_claim_words(self, text):
        """Detection, separated from assertion.

        *(The two were one method, and the positive control below could
        not test it: `subTest` RECORDS a failure against the running
        test rather than raising, so `assertRaises(AssertionError)` saw
        nothing raised and failed while the guard underneath was working
        perfectly. A control that cannot observe the thing it controls
        is worse than none — it reports green either way.)*
        """
        folded = text.casefold()
        return tuple(w for w in self.FORBIDDEN_CLAIMS
                     if w.casefold() in folded)

    def assertNoStateClaim(self, text, context=""):
        for word in self.state_claim_words(text):
            with self.subTest(word=word, context=context):
                self.fail(
                    f"{context}the prompt claims {word!r} — that is a "
                    "statement about server state, and the composer "
                    "cannot know it before the versioned apply")

    def test_the_state_claim_guard_is_not_vacuous(self):
        """Positive control. A guard nobody has seen fail is a rumour."""
        self.assertEqual(
            self.state_claim_words("This is the LAST topic still open."),
            ("last",), "the guard missed a capitalised claim")
        self.assertEqual(
            self.state_claim_words("We are DONE WITH all the questions."),
            ("done with", "all the questions"),
            "the guard missed a multi-word claim")
        self.assertEqual(
            self.state_claim_words("Ask warmly about their childhood home."),
            (), "the guard fires on innocent wording")


class SectionRenderTests(NoStateClaimMixin, unittest.TestCase):
    """What the block says, given a plan."""

    def block(self, state):
        return _pc._profile_seed_onboarding_block({KEY: state, ATTEST: True})

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

    def test_acknowledge_asks_no_REGISTRY_question(self):
        """The acknowledgement turn is the one most likely to regress.

        It must not re-ask the answered topic and must not ask the next
        one — until the post-commit apply succeeds, the next topic is a
        prediction rather than a fact.
        """
        text = self.block(onboarding("acknowledge", A))
        # THE GUARANTEE THAT MATTERS, and it is unchanged: not one
        # registry question appears anywhere in the block. This is what
        # stops Lori running ahead of the server, and it holds whether
        # or not she asks a follow-up of her own.
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, text)
        self.assertIn("PROFILE SEED — ACKNOWLEDGE", text)
        self.assertIn("Do NOT ask the next Profile Seed question", text)
        self.assertIn("Do NOT ask that question again", text)
        # ONE follow-up is now permitted, and the permission is bounded.
        self.assertIn("at most ONE short, natural follow-up", text)
        self.assertIn("the same subject, not a new one", text)

    def test_known_topics_are_named_so_they_are_not_re_asked(self):
        text = self.block(onboarding("present", B, known=[A],
                                     remaining=[B]))
        self.assertIn(_seed.topic(A).intent, text)
        self.assertNotIn(_seed.topic(A).question, text,
                         "a settled topic was re-asked as a question")

    def test_an_ASKING_turn_never_claims_a_last_topic(self):
        """*(The block used to end with "This is the last topic still
        open" whenever a filtered `remaining_topics` count was `<= 1`.
        Missing, empty and non-list metadata ALL filtered to zero, and
        `0 <= 1` — so the very first question of a ten-topic walk could
        be announced as the last one, purely because a field was absent.
        The line is deleted; the acknowledgement owns the warm
        transition and nothing here claims state.)*"""
        for remaining in ([A, B], [A], list(_seed.TOPIC_IDS)):
            with self.subTest(remaining=remaining):
                self.assertNoStateClaim(
                    self.block(onboarding("present", A, remaining=remaining)))

    def test_MALFORMED_remaining_topics_asks_the_topic_and_claims_nothing(self):
        """The three payloads review reproduced, plus the shapes beside
        them. Each must ask exactly its own topic and claim nothing."""
        malformed = ({"action": "present", "topic_id": A},
                     {"action": "present", "topic_id": A,
                      "remaining_topics": "junk"},
                     {"action": "present", "topic_id": A,
                      "remaining_topics": []},
                     {"action": "present", "topic_id": A,
                      "remaining_topics": None},
                     {"action": "present", "topic_id": A,
                      "remaining_topics": 3},
                     {"action": "re_present", "topic_id": A},
                     {"action": "re_present", "topic_id": A,
                      "remaining_topics": "junk"})
        for state in malformed:
            with self.subTest(state=state):
                text = self.block(state)
                self.assertIn(_seed.topic(A).question, text,
                              "the selected topic was not asked")
                for other in _seed.TOPIC_IDS:
                    if other != A:
                        self.assertNotIn(_seed.topic(other).question, text)
                self.assertNoStateClaim(text, "malformed remaining_topics: ")

    #: The one function these structural checks are ABOUT.
    TARGET_FUNCTION = "_profile_seed_onboarding_block"

    #: Synthetic source for the isolation controls, assembled rather
    #: than written as a literal so this file contains no nested triple
    #: quotes. `unrelated_helper()` deliberately uses `remaining` AND the
    #: forbidden phrase; the target function has neither outside its own
    #: docstring.
    _SYNTHETIC_HEAD = (
        "def unrelated_helper(rows):\n"
        "    remaining = len(rows)\n"
        '    return "This is the last topic still open." if remaining else ""\n'
        "\n\n"
        "def _profile_seed_onboarding_block(runtime71):\n"
        "    QQQMentions the last topic still open, in a DOCSTRING.QQQ\n"
        '    lines = ["PROFILE SEED — ONE QUESTION."]\n'
    ).replace("QQQ", '"' * 3)

    @classmethod
    def synthetic(cls, body):
        return cls._SYNTHETIC_HEAD + body + "\n    return lines\n"

    @staticmethod
    def function_symbols(source, name):
        """`(names, literals)` for ONE function. Docstrings excluded.

        *(Both checks below scanned the WHOLE composer module. That was
        raised at Step 4 acceptance and deferred; deferring it was the
        wrong call and it is corrected here. A module-wide ban on the
        NAME `remaining` is a Profile Seed guard that unrelated future
        code would trip, and a guard that fails for reasons outside its
        own subject teaches people to switch it off. Scope is the fix.

        Docstrings stay excluded for the separate reason established
        earlier in this lane: the first version of this check failed on
        the comment explaining the removal — a guard firing on the prose
        that describes the guarded thing.)*
        """
        import ast
        target = None
        for node in ast.walk(ast.parse(source)):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == name):
                target = node
                break
        if target is None:
            raise AssertionError(
                f"{name}() is not in this source — the guard has no subject, "
                "which is a broken instrument and not a passing test")
        docstrings = set()
        for node in ast.walk(target):
            body = getattr(node, "body", None)
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef))
                    and body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                docstrings.add(id(body[0].value))
        names = {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
        literals = [n.value for n in ast.walk(target)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, str) and id(n) not in docstrings]
        return names, literals

    def composer_symbols(self):
        return self.function_symbols(
            (_SERVER_CODE / "api" / "prompt_composer.py")
            .read_text(encoding="utf-8"), self.TARGET_FUNCTION)

    def test_the_asking_block_no_longer_reads_remaining_topics_for_a_claim(self):
        """Structural: the count that produced the claim is gone.

        Kept because deleting the LINE while leaving the count would be
        a natural half-fix, and the next person wanting a heads-up would
        find the count sitting there ready to be misused again.
        """
        names, literals = self.composer_symbols()
        for phrase in ("last topic still open", "last topic"):
            with self.subTest(phrase=phrase):
                self.assertNotIn(
                    phrase, " ".join(literals),
                    f"{self.TARGET_FUNCTION}() can still emit a last-topic "
                    "claim")
        self.assertNotIn("remaining", names,
                         "the `remaining` count survived the deletion of the "
                         "line it existed to produce")

    def test_the_structural_check_is_not_vacuous(self):
        """It really is reading the target function's own symbols."""
        names, literals = self.composer_symbols()
        self.assertIn("PROFILE SEED — ONE QUESTION.", " ".join(literals),
                      "the literal extractor found nothing, so the check "
                      "above proves nothing")
        self.assertIn("lines", names,
                      "the name extractor found nothing, so the check above "
                      "proves nothing")

    def test_the_guard_DETECTS_the_defect_inside_the_target_function(self):
        """Control 1. A live `remaining` in the target IS caught."""
        source = self.synthetic(
            "    remaining = 1\n"
            "    if remaining <= 1:\n"
            '        lines.append("This is the last topic still open.")')
        names, literals = self.function_symbols(source, self.TARGET_FUNCTION)
        self.assertIn("remaining", names,
                      "the guard missed the count inside its own subject")
        self.assertIn("last topic still open", " ".join(literals),
                      "the guard missed the claim inside its own subject")

    def test_the_guard_IGNORES_an_unrelated_function(self):
        """Control 2. The false failure the deferred fix would have caused.

        `unrelated_helper()` uses `remaining` and contains the forbidden
        phrase. The target has neither, except in its DOCSTRING. A
        module-wide scan fails here; a scoped one passes, and that
        difference is the whole correction.
        """
        names, literals = self.function_symbols(self.synthetic("    pass"),
                                                self.TARGET_FUNCTION)
        self.assertNotIn("remaining", names,
                         "an unrelated function's local tripped a Profile "
                         "Seed guard")
        self.assertNotIn("last topic still open", " ".join(literals),
                         "an unrelated function's string, or the target's own "
                         "docstring, tripped the guard")

    def test_a_missing_target_function_FAILS_rather_than_passes(self):
        """A guard whose subject vanished must not report success."""
        with self.assertRaises(AssertionError):
            self.function_symbols("def other():\n    pass\n",
                                  self.TARGET_FUNCTION)

    # ── silence, in every shape that must produce it ────────────────
    def test_a_HOLD_block_asks_nothing_names_no_topic_and_claims_nothing(self):
        """The whole content of a held turn, in one test.

        Naming the parked question is one edit away from asking it, so
        the block must not carry the topic label either — even though
        the plan knows which topic is being held.
        """
        block = self.block(onboarding("hold", A, remaining=[A, B]))
        self.assertTrue(block, "a held turn rendered nothing, so it "
                               "suppressed the legacy block and replaced it "
                               "with a hole")
        self.assertIn("PROFILE SEED — HOLD", block)
        self.assertNotIn("?", block, "the held block contains a question mark")
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, block)
                self.assertNotIn(_seed.topic(topic_id).intent or topic_id,
                                 block)
        self.assertNoStateClaim(block, "hold: ")

    def test_a_HOLD_block_renders_for_every_registry_topic(self):
        for topic_def in _seed.TOPIC_REGISTRY:
            with self.subTest(topic=topic_def.topic_id):
                block = self.block(onboarding("hold", topic_def.topic_id))
                self.assertIn("PROFILE SEED — HOLD", block)
                self.assertNotIn(topic_def.question, block)

    def test_a_HOLD_plan_with_an_UNKNOWN_topic_renders_nothing(self):
        """`hold` is validated like every other action.

        A held plan naming a topic that does not exist is a malformed
        payload, and a malformed payload must leave the existing prompt
        alone — it must NOT suppress. Otherwise `hold` becomes a way to
        delete the legacy block by sending junk.
        """
        state = onboarding("hold", "favourite_colour")
        self.assertEqual(self.block(state), "")
        self.assertFalse(_pc.profile_seed_onboarding_active({KEY: state, ATTEST: True}))

    def test_idle_and_malformed_states_render_nothing(self):
        for state in (onboarding("idle"), {}, {"action": "present"},
                      {"action": "present", "topic_id": "favourite_colour"},
                      {"action": "banana", "topic_id": A},
                      {"action": None, "topic_id": A},
                      "not a dict", None, 3, []):
            with self.subTest(state=state):
                self.assertEqual(
                    _pc._profile_seed_onboarding_block({KEY: state, ATTEST: True}), "")

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


class CompletionTransitionTests(NoStateClaimMixin, unittest.TestCase):
    """The walk ends warmly, on the turn that can actually say so."""

    def block(self, state):
        return _pc._profile_seed_onboarding_block({KEY: state, ATTEST: True})

    #: Words that would be an authoritative claim about server state.
    #:
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
        self.assertNoStateClaim(
            self.block(onboarding("acknowledge", A, completes_walk=True)),
            "acknowledgement: ")

    def test_a_MOVED_VERSION_completion_still_claims_nothing(self):
        """THE CONCURRENCY CASE, end to end.

        *(Renamed and rewritten at 0052. It was
        `test_a_STALE_VERSION_...`, and its premise was that independent
        evidence moving the row version makes the outstanding question
        stale — so the apply conflicts, nothing is written, and A is
        asked again. That premise WAS the acceptance blocker. Evidence
        for an unrelated topic must not re-interrogate the narrator, and
        since 0052 it does not: the epoch is unchanged, the answer is
        acknowledged, and the write uses the CURRENT version.*

        *The property this test actually guards is untouched by that and
        is why it is kept: an acknowledgement must never CLAIM in
        narrator-visible text that the walk is over. The genuine-conflict
        half moves to a genuine epoch change below.)*

        1. Lori presents A at epoch 3, version 7.
        2. Unrelated evidence moves the row to version 8. The question
           on screen has not changed.
        3. The narrator answers; the plan acknowledges, says this
           completes the walk, and writes with version 8.
        4. Nothing in the emitted block claims a state.
        """
        state = {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                 "active_topic_id": A, "version": 8,
                 "presentation_epoch": 3,
                 "known_topics": [t for t in _seed.TOPIC_IDS if t != A],
                 "remaining_topics": [A]}
        history = [{"role": "assistant",
                    "meta": {_turn.PRESENTED_TOPIC: A,
                             _turn.PRESENTED_VERSION: 7,
                             _turn.PRESENTED_EPOCH: 3}},
                   {"role": "user", "content": "Still working.", "meta": {}}]
        plan = _turn.plan_turn(state=state, history=history,
                               narrator_text="Still working.")
        self.assertEqual(
            plan.action, _turn.ACKNOWLEDGE,
            "an unrelated evidence write re-interrogated the narrator")
        self.assertTrue(plan.completes_walk)
        self.assertEqual(plan.version, 8,
                         "the apply would use the superseded version and "
                         "conflict for no reason")

        text = self.block({"action": plan.action, "topic_id": plan.topic_id,
                           "known_topics": state["known_topics"],
                           "remaining_topics": state["remaining_topics"],
                           "completes_walk": plan.completes_walk})
        self.assertNoStateClaim(text, "moved-version acknowledgement: ")

    def test_a_NEW_EPOCH_makes_the_question_genuinely_stale(self):
        """The other half, on the condition that really is staleness.

        A settled topic reopened, so the server minted a new epoch. The
        answer to the old question does not close the new one, and A is
        asked again — which is correct, and is why the acknowledgement
        must never have claimed the walk was over.
        """
        state = {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                 "active_topic_id": A, "version": 8,
                 "presentation_epoch": 4,
                 "known_topics": [t for t in _seed.TOPIC_IDS if t != A],
                 "remaining_topics": [A]}
        history = [{"role": "assistant",
                    "meta": {_turn.PRESENTED_TOPIC: A,
                             _turn.PRESENTED_VERSION: 7,
                             _turn.PRESENTED_EPOCH: 3}},
                   {"role": "user", "content": "Still working.", "meta": {}},
                   {"role": "assistant",
                    "meta": {_turn.RESPONSE_TOPIC: A,
                             _turn.RESPONSE_VERSION: 7,
                             _turn.RESPONSE_EPOCH: 3,
                             _turn.RESPONSE_DISPOSITION: _seed.ADDRESSED}}]
        nxt = _turn.plan_turn(state=state, history=history,
                              narrator_text="Hello again")
        self.assertIn(nxt.action, (_turn.PRESENT, _turn.RE_PRESENT))
        self.assertEqual(nxt.topic_id, A,
                         "the reopened topic must still be asked — this "
                         "is why the acknowledgement must not have claimed "
                         "the walk was over")
        self.assertFalse(nxt.advances)


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

    def test_the_ASKING_turn_makes_no_promise_and_no_claim(self):
        """The asking turn says nothing about where the walk stands.

        *(It first carried "when they have answered, tell them warmly
        that you now have a sense of their story" — an instruction for a
        turn on which this block no longer exists. That was replaced by
        "This is the last topic still open", which was a STATE CLAIM
        that fired whenever `remaining_topics` was missing, empty or not
        a list. Both are gone: the acknowledgement owns the transition,
        and the asking turn asks.)*
        """
        for remaining in (["life_stage"], [A, B], []):
            with self.subTest(remaining=remaining):
                text = self.block(onboarding("present", "life_stage",
                                             remaining=remaining))
                folded = text.casefold()
                self.assertNotIn("when they have answered", folded)
                self.assertNotIn("sense of their story", folded)
                self.assertNoStateClaim(text, "asking turn: ")

    def test_the_plan_and_the_prompt_agree_end_to_end(self):
        """The reducer's own completes_walk drives the block."""
        state = {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                 "active_topic_id": A, "version": 7,
                 "presentation_epoch": 3,
                 "known_topics": [t for t in _seed.TOPIC_IDS if t != A],
                 "remaining_topics": [A]}
        history = [{"role": "assistant",
                    "meta": {_turn.PRESENTED_TOPIC: A,
                             _turn.PRESENTED_VERSION: 7,
                             _turn.PRESENTED_EPOCH: 3}},
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
                runtime[ATTEST] = True
                self.assertEqual(
                    self.compose(runtime), baseline,
                    "malformed onboarding state changed the prompt — it must "
                    "be indistinguishable from the key being absent")

    def test_malformed_state_leaves_the_section_list_identical(self):
        baseline = self.sections(dict(FULL_RUNTIME))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = {"action": "present", "topic_id": "bad"}
        runtime[ATTEST] = True
        self.assertEqual(self.sections(runtime), baseline)

    def test_idle_state_is_byte_identical_to_no_key(self):
        baseline = self.compose(dict(FULL_RUNTIME))
        for state in (onboarding("idle"), {}, None):
            with self.subTest(state=state):
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = state
                runtime[ATTEST] = True
                self.assertEqual(self.compose(runtime), baseline)

    def test_pending_paused_completed_plans_are_byte_identical(self):
        """Every non-active lifecycle reduces to an IDLE plan, and an
        idle plan must be invisible."""
        baseline = self.compose(dict(FULL_RUNTIME))
        for status in (_seed.STATUS_PENDING, _seed.STATUS_PAUSED,
                       _seed.STATUS_COMPLETED):
            state = {"person_id": "p1", "status": status,
                     "active_topic_id": A, "version": 7,
                     "presentation_epoch": 3,
                     "known_topics": [], "remaining_topics": [A]}
            plan = _turn.plan_turn(state=state, history=[],
                                   narrator_text="Hi")
            with self.subTest(status=status):
                self.assertEqual(plan.action, _turn.IDLE)
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = {"action": plan.action,
                                "topic_id": plan.topic_id,
                                "known_topics": [], "remaining_topics": []}
                runtime[ATTEST] = True
                self.assertEqual(self.compose(runtime), baseline)

    # ── malformed `known_topics`: crash, or a FALSE "already settled" ──
    #: Every shape review reproduced, plus the two found reproducing it.
    MALFORMED_KNOWN = (
        3,                              # TypeError — not iterable
        object(),                       # TypeError — not iterable
        [{}],                           # TypeError — unhashable dict
        [[]],                           # TypeError — unhashable list
        {"childhood_home": True},       # iterates KEYS → false "settled"
        {"military": True},             # the SAME defect, on another topic
                                        # — see the dedicated test below for
                                        # why this shape is the one that
                                        # discriminates
        [1, 2],                         # non-string members
        "childhood_home",               # a str iterates its CHARACTERS
        [A],                            # contradiction: asking what it
                                        # calls settled
    )

    def test_malformed_known_topics_is_byte_identical_to_no_key(self):
        """Two failure modes, and the quiet one is worse.

        `3` and `object()` raised TypeError; `[{}]` and `[[]]` raised
        unhashable TypeError inside the registry lookup; a bare string
        was iterated as CHARACTERS. Those are loud or inert.

        `{"childhood_home": True}` was the dangerous one. A dict
        iterates its keys, so the block rendered *"Already settled, and
        NOT to be asked again: where the narrator grew up"* — about a
        topic nothing had established. Lori then would not ask it, and
        the narrator would never be asked a question they were owed.
        Principle 8 holds only while "known" is TRUE.
        """
        for pass_name in ("pass1", "pass2a"):
            runtime_base = dict(FULL_RUNTIME)
            runtime_base["current_pass"] = pass_name
            baseline = self.compose(runtime_base)
            for known in self.MALFORMED_KNOWN:
                with self.subTest(pass_name=pass_name, known=known):
                    runtime = dict(runtime_base)
                    runtime[KEY] = {"action": "present", "topic_id": A,
                                    "known_topics": known}
                    runtime[ATTEST] = True
                    self.assertEqual(
                        self.compose(runtime), baseline,
                        "malformed known_topics changed the prompt — it must "
                        "be indistinguishable from the key being absent")
                    self.assertEqual(self.sections(runtime),
                                     self.sections(runtime_base),
                                     "malformed known_topics changed the "
                                     "section list")

    def test_a_DICT_never_announces_its_keys_as_settled(self):
        """The quiet defect, isolated so a mutation can discriminate.

        *(The aggregate fixture used `{"childhood_home": True}` while
        asking `childhood_home` — so the CONTRADICTION guard rejected it
        before dict-iteration was ever reached, and a mutation weakening
        only the container check was caught by a different guard than
        the one it targeted. Caught for the wrong reason is the failure
        this gate already names for syntax errors, and I walked into it
        anyway. The key here is a DIFFERENT topic, so nothing but the
        container check stands between the dict and the prompt.)*
        """
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = {"action": "present", "topic_id": A,
                        "known_topics": {C: True}}
        runtime[ATTEST] = True
        text = self.compose(runtime)
        self.assertEqual(
            text, self.compose(dict(FULL_RUNTIME)),
            f"a dict was accepted, so Lori is told {_seed.topic(C).intent!r} "
            "is already settled when nothing established it — and she will "
            "not ask about it")

    def test_NON_STRING_members_never_render_as_a_valid_plan(self):
        """Element type, isolated. Ints are hashable, so this shape
        reaches the renderer without an unhashable error — which is what
        makes it the discriminating case for the element check."""
        for known in ([1, 2], [None], [A, 7]):
            with self.subTest(known=known):
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = {"action": "present", "topic_id": B,
                                "known_topics": known}
                runtime[ATTEST] = True
                self.assertEqual(self.compose(runtime),
                                 self.compose(dict(FULL_RUNTIME)),
                                 "non-string members were accepted")

    def test_a_VALID_plan_still_changes_the_prompt(self):
        """Positive control, so the equalities above cannot pass vacuously.

        If the validator rejected everything, every byte-equality test
        would report green while the feature was dead.
        """
        for pass_name in ("pass1", "pass2a"):
            runtime_base = dict(FULL_RUNTIME)
            runtime_base["current_pass"] = pass_name
            baseline = self.compose(runtime_base)
            for known in ([], [C], ["retired_topic_id"]):
                with self.subTest(pass_name=pass_name, known=known):
                    runtime = dict(runtime_base)
                    runtime[KEY] = {"action": "present", "topic_id": A,
                                    "known_topics": known}
                    runtime[ATTEST] = True
                    self.assertNotEqual(
                        self.compose(runtime), baseline,
                        f"a VALID plan (known_topics={known!r}) left the "
                        "prompt unchanged — the validator is rejecting good "
                        "state, so the equality tests above prove nothing")

    def test_absent_known_topics_is_still_a_valid_plan(self):
        """Absent stays equivalent to empty — a plan that has settled
        nothing is ordinary, especially at the start of a walk."""
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = {"action": "present", "topic_id": A}
        runtime[ATTEST] = True
        text = self.compose(runtime)
        self.assertIn(_seed.topic(A).question, text)
        self.assertNotIn("Already settled", text)

    def test_a_plan_never_calls_its_OWN_topic_already_settled(self):
        """The contradiction, stated as the narrator experiences it.

        `known_topics=[A]` with `topic_id=A` rendered the settled line
        and the question about the same topic in one turn.
        """
        for action in ("present", "re_present"):
            with self.subTest(action=action):
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = {"action": action, "topic_id": A,
                                "known_topics": [A, C]}
                runtime[ATTEST] = True
                self.assertEqual(self.compose(runtime),
                                 self.compose(dict(FULL_RUNTIME)))

    # ── active: exactly one section added, one deliberately replaced ──
    def test_an_active_plan_adds_ONLY_the_canonical_section(self):
        baseline = dict(self.sections(dict(FULL_RUNTIME)))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        runtime[ATTEST] = True
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
        runtime[ATTEST] = True
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
        runtime[ATTEST] = True
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
        runtime[ATTEST] = True
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
                  KEY: onboarding("present", A, remaining=[A]),
                  ATTEST: True}
        text = self.compose(sparse)
        self.assertIn(_seed.topic(A).question, text)
        for phrase in ("single next missing piece of identity",
                       "name, date of birth, and place of birth are all "
                       "confirmed"):
            with self.subTest(phrase=phrase[:30]):
                self.assertNotIn(phrase, text)

    def test_an_untruthful_sparse_runtime_does_NOT_get_identity_for_free(self):
        """The inference stays withdrawn — and it is about a CALLER.

        Omitting `identity_complete` must leave identity mode ON when the
        onboarding keys came from the caller. If supplying them could
        switch it off, the gate is not a gate.

        ── DELIBERATELY UNATTESTED, Phase 3 (2026-08-29) ────────────────

        *(A mechanical sweep added `ATTEST: True` to every hand-built
        runtime in this file, and it was WRONG here — it inverted the
        one test whose subject is an untrustworthy caller. Attestation is
        precisely what a caller cannot supply: transports strip it from
        client input before resolving, and the composer requires it.*

        *So this fixture stays unattested, because that is what "an
        untruthful sparse runtime" MEANS. An attested plan legitimately
        does settle identity — the resolver established the anchors
        before promoting the row out of `pending` — and that case is
        covered in `test_profile_seed_prompt_authority.py`. The two are
        opposite halves of the same rule and must not be merged.)*
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
        explicit_absent.pop(ATTEST, None)
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
        runtime[ATTEST] = True
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
        runtime[ATTEST] = True
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
        runtime[ATTEST] = True
        text = _pc.compose_system_prompt("conv-idle", runtime71=runtime)
        self.assertIn("Gather the following 10 facts", text)

    def test_a_HOLD_plan_suppresses_the_legacy_block(self):
        """THE DEFECT THIS CLOSES, 2026-08-27.

        Every turn that must not participate — a system directive, a
        deterministic mode, a cancelled turn, a narrator saying "pause" —
        used to plan `idle`, and the test directly above shows what
        `idle` does: it leaves the browser's ten-question list standing.

        So a directive arriving mid-walk advanced nothing (correct) and
        handed Lori back the pass the server had taken ownership of
        (not correct), on a turn nobody was watching. "Server state
        overrides browser pass" has to hold on the turns that do nothing.
        """
        runtime = self._pass1_runtime()
        runtime[KEY] = onboarding("hold", A)
        runtime[ATTEST] = True
        text = _pc.compose_system_prompt("conv-hold", runtime71=runtime)
        self.assertNotIn(
            "Gather the following 10 facts", text,
            "a held turn revived the legacy browser Profile Seed block")

    def test_a_HOLD_plan_asks_NO_question_at_all(self):
        runtime = self._pass1_runtime()
        runtime[KEY] = onboarding("hold", A)
        runtime[ATTEST] = True
        text = _pc.compose_system_prompt("conv-hold-silent", runtime71=runtime)
        for topic_id in _seed.TOPIC_IDS:
            with self.subTest(topic=topic_id):
                self.assertNotIn(_seed.topic(topic_id).question, text)

    def test_a_HOLD_plan_REPLACES_the_legacy_block_rather_than_deleting_it(self):
        """The distinction from the malformed-payload case.

        A malformed payload renders nothing AND suppresses nothing, so
        the existing prompt is untouched — that is C6, and it is right.
        `hold` suppresses, so it owes a replacement: removing working
        instructions and putting nothing in their place is the shape C6
        exists to punish.
        """
        runtime = self._pass1_runtime()
        runtime[KEY] = onboarding("hold", A)
        runtime[ATTEST] = True
        text = _pc.compose_system_prompt("conv-hold-replaced",
                                         runtime71=runtime)
        self.assertIn("PROFILE SEED — HOLD", text)
        self.assertIn("Do NOT ask a Profile Seed question this turn", text)


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
        runtime[ATTEST] = True
        composed = _pc.compose_prompt_sections("conv-sections",
                                               runtime71=runtime)
        names = [s.name for s in composed.sections]
        self.assertIn("profile_seed_onboarding", names)

    def test_the_section_is_absent_from_the_assembly_when_idle(self):
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("idle")
        runtime[ATTEST] = True
        composed = _pc.compose_prompt_sections("conv-sections-idle",
                                               runtime71=runtime)
        names = [s.name for s in composed.sections]
        self.assertNotIn("profile_seed_onboarding", names)

    def test_rendered_text_and_the_string_entry_point_agree(self):
        """Both public entry points go through one assembly, so a
        section added to one cannot be missing from the other."""
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A])
        runtime[ATTEST] = True
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
        with_onboarding[ATTEST] = True
        text = _pc.compose_system_prompt("conv-seed", runtime71=with_onboarding)

        self.assertEqual(runtime["profile_seed"],
                         {"preferred_name": "Verlie", "age_years": 89,
                          "life_stage": "senior elder"},
                         "the composer mutated the legacy profile_seed dict")
        # Everything the legacy seed contributed still appears. The pass
        # directive is deliberately replaced (see the byte-stability
        # suite); nothing the seed produced is.
        head = baseline.split("DIRECTIVE: You are in Pass 2A")[0]
        # ── TWO RUNTIME LINES ARE DELIBERATELY DIFFERENT, Phase 3 ────────
        #
        # This walks the whole prompt head, which contains the LORI_RUNTIME
        # block as well as the legacy seed's output. Phase 3 relabels the
        # browser's pass to `browser_pass` and sets `effective_pass:
        # profile_seed` while a validated walk is active — a change this
        # test is not about and must not silently forbid.
        #
        # They are exempted BY PREFIX rather than by dropping the walk,
        # because the claim being made — that nothing the LEGACY SEED
        # contributed moved — is still asserted line for line, and it is
        # the claim worth keeping.
        _phase3_runtime_lines = ("  pass: ", "  effective_pass: ")
        for line in head.splitlines():
            if line.strip() and not line.startswith(_phase3_runtime_lines):
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
        runtime[ATTEST] = True
        return runtime

    def _state(self, active=A, version=7, epoch=3):
        # `presentation_epoch` is supplied by every real transport since
        # 0052, and `plan_turn` HOLDs without it — an active walk with no
        # question identity must not be planned against.
        return {"person_id": "p1", "status": _seed.STATUS_ACTIVE,
                "active_topic_id": active, "version": version,
                "presentation_epoch": epoch,
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
                        _turn.PRESENTED_TOPIC: A, _turn.PRESENTED_VERSION: 7,
                        _turn.PRESENTED_EPOCH: 3}},
                   {"role": "user", "content": "Devils Lake.", "meta": {}}]
        plan = _turn.plan_turn(state=state, history=history,
                               narrator_text="Devils Lake.")
        self.assertEqual(plan.action, _turn.ACKNOWLEDGE)
        text = _pc.compose_system_prompt(
            "conv-plan-ack", runtime71=self._runtime_from_plan(plan, state))
        self.assertIn("PROFILE SEED — ACKNOWLEDGE", text)
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
        runtime[ATTEST] = True
        composed = _pc.compose_prompt_sections("conv-plan-idle",
                                               runtime71=runtime)
        self.assertNotIn("profile_seed_onboarding",
                         [s.name for s in composed.sections])


class IdentityCompleteIsReportedNotDerived(unittest.TestCase):
    """`LORI_RUNTIME: identity_complete:` states what it was given.

    ── WHY THIS CLASS EXISTS, 2026-09-05 ────────────────────────────

    Mutation `C8` — *"identity_complete inferred from an onboarding
    payload again"* — **survived the authoritative gate**, green across
    all three composer suites. It ORs `profile_seed_onboarding_active()`
    into the value read at `prompt_composer.py:4118`.

    It survived because the invariant MOVED and no test followed it.
    When C8 was written, the inference flipped `identity_mode`. The
    attestation restructure then put `identity_mode = False` inside the
    `if _ps_attested:` branch unconditionally — so under an attested
    walk `identity_complete` is no longer read for that decision at all,
    and every test aimed at identity interrogation went blind to it.

    But `identity_complete` has a SECOND reader, and it is unconditional:
    `prompt_composer.py:4243` renders it into the `LORI_RUNTIME:` block
    of the system prompt on every turn. Measured HEAD versus mutated on
    an attested active walk carrying `identity_complete: False`:

        HEAD      identity_complete: False
        C8        identity_complete: True

    with `identity_mode` False and no identity interrogation in either.
    So the surviving effect is that **the prompt tells Lori a narrator's
    identity is established because an onboarding payload was present** —
    the exact inference `prompt_composer.py:4103-4117` records as
    withdrawn, reappearing at a reader that comment predates.

    That is a fact about a narrator, stated to Lori, derived from the
    shape of a dict. The composer's job here is to REPORT the value the
    server supplied, not to improve it.
    """

    KEY = KEY
    ATTEST = ATTEST

    def _attested_walk(self, *, identity_complete):
        """An attested ACTIVE walk — the only case where C8 differs.

        With no attestation `profile_seed_onboarding_active()` is False,
        so the mutation's added disjunct is False too and nothing can be
        measured. The attested runtime IS the discriminating fixture.
        """
        runtime = dict(FULL_RUNTIME)
        runtime["current_pass"] = "pass1"
        runtime["identity_complete"] = identity_complete
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        runtime[ATTEST] = True
        return runtime

    def _runtime_line(self, text, field):
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(field + ":"):
                return stripped
        self.fail(f"{field!r} is absent from the composed prompt — this "
                  f"test cannot pass by the line simply not being there")

    def test_a_false_identity_complete_is_reported_as_false(self):
        """The C8 regression. Was `identity_complete: True`."""
        text = _pc.compose_system_prompt(
            "c8-false", runtime71=self._attested_walk(identity_complete=False))
        self.assertEqual(
            "identity_complete: False",
            self._runtime_line(text, "identity_complete"),
            "the composer derived identity_complete from the presence of "
            "an onboarding payload instead of reporting what it was given")

    def test_a_true_identity_complete_is_reported_as_true(self):
        """The positive control.

        Without this, the test above would still pass if the composer
        started reporting `False` unconditionally — which would be a
        different defect with the same green.
        """
        text = _pc.compose_system_prompt(
            "c8-true", runtime71=self._attested_walk(identity_complete=True))
        self.assertEqual(
            "identity_complete: True",
            self._runtime_line(text, "identity_complete"))

    def test_the_walk_really_is_attested_in_this_fixture(self):
        """Non-vacuity.

        If attestation were absent, C8's disjunct would be False and both
        tests above would pass against the mutated product — proving
        nothing. This asserts the fixture is the discriminating one.
        """
        runtime = self._attested_walk(identity_complete=False)
        self.assertTrue(
            _pc.profile_seed_onboarding_active(runtime),
            "the fixture is not an attested active walk, so it cannot "
            "discriminate the mutation it exists to catch")
        text = _pc.compose_system_prompt("c8-attested", runtime71=runtime)
        self.assertEqual("profile_seed_active: true",
                         self._runtime_line(text, "profile_seed_active"))

    def test_identity_interrogation_is_off_either_way(self):
        """What C8 does NOT change, recorded so the claim stays narrow.

        `identity_mode` is False under an attested walk regardless of
        `identity_complete`, so this mutation is not about interrogation
        — and a future reader should not go looking for that difference.
        """
        for value in (True, False):
            with self.subTest(identity_complete=value):
                text = _pc.compose_system_prompt(
                    f"c8-mode-{value}",
                    runtime71=self._attested_walk(identity_complete=value))
                self.assertIn("effective_pass: profile_seed", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
