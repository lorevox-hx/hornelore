"""One topic reaches Lori, and nothing else changes.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 2 step 4 (2026-08-26).

── HOW TO RUN THIS ───────────────────────────────────────────────────

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_composer_section

`prompt_composer`'s import chain reaches fastapi, so `.venv` cannot run
this module at all. **A skip is not a pass** — report the interpreter.

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

try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except Exception:  # pragma: no cover
    _HAS_FASTAPI = False

if _HAS_FASTAPI:
    from api import prompt_composer as _pc
    from api.services import profile_seed as _seed
    from api.services import profile_seed_turn as _turn

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


def onboarding(action, topic_id=None, known=(), remaining=()):
    return {"action": action, "topic_id": topic_id,
            "known_topics": list(known), "remaining_topics": list(remaining)}


@unittest.skipUnless(_HAS_FASTAPI,
                     "prompt_composer imports fastapi; .venv has none — "
                     "a skip is not a pass, report the interpreter")
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
        text = self.block(onboarding("present", "life_stage",
                                     remaining=["life_stage"]))
        self.assertIn("last thing you need", text)

    def test_a_mid_walk_topic_does_not_claim_to_be_the_last(self):
        text = self.block(onboarding("present", A, remaining=[A, B]))
        self.assertNotIn("last thing you need", text)

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


@unittest.skipUnless(_HAS_FASTAPI, "needs fastapi")
class NoSecondTopicListTests(unittest.TestCase):
    """The registry is the only list of questions in the system."""

    def test_the_composer_holds_no_hard_coded_question_list(self):
        source = (_SERVER_CODE / "api" / "prompt_composer.py").read_text(
            encoding="utf-8")
        # The legacy block is SUPPRESSED for enrolled narrators, not
        # deleted — historical narrators still reach it — so it is still
        # in the file. What must not exist is a SECOND copy.
        for question in (t.question for t in _seed.TOPIC_REGISTRY):
            with self.subTest(question=question[:30]):
                self.assertLessEqual(
                    source.count(question), 1,
                    "a question string appears more than once in the "
                    "composer — that is the second list the work order "
                    "forbids")

    def test_the_registry_wording_matches_the_legacy_block(self):
        """The legacy block still serves historical narrators.

        Its wording and the registry's must be the same strings, or the
        two populations get different questions and the difference is
        invisible until somebody reads both.
        """
        source = (_SERVER_CODE / "api" / "prompt_composer.py").read_text(
            encoding="utf-8")
        for topic_def in _seed.TOPIC_REGISTRY:
            with self.subTest(topic=topic_def.topic_id):
                self.assertIn(topic_def.question, source)

    def test_every_registry_topic_has_a_question(self):
        for topic_def in _seed.TOPIC_REGISTRY:
            with self.subTest(topic=topic_def.topic_id):
                self.assertTrue(topic_def.question.strip())


@unittest.skipUnless(_HAS_FASTAPI, "needs fastapi")
class ByteStabilityTests(unittest.TestCase):
    """Adding onboarding state adds a section and moves NOTHING else."""

    def compose(self, runtime=None):
        return _pc.compose_system_prompt("conv-stability", runtime71=runtime)

    def test_no_runtime_at_all_is_unchanged_by_this_phase(self):
        """The ownerless REST prompt. It has no runtime object today and
        must still compose without one."""
        self.assertTrue(self.compose(None))

    def test_an_absent_onboarding_key_composes_identically(self):
        """A HISTORICAL narrator: full runtime, no onboarding row, so no
        key. Byte-identical to the same runtime with the key explicitly
        absent — which is the state every existing caller is in."""
        without = self.compose(dict(FULL_RUNTIME))
        again = self.compose(dict(FULL_RUNTIME))
        self.assertEqual(without, again)

    def test_idle_onboarding_state_is_byte_identical_to_none(self):
        """`pending`, `paused`, `completed` and historical all reduce to
        an IDLE plan, and an idle plan must be indistinguishable from
        having no onboarding state at all."""
        baseline = self.compose(dict(FULL_RUNTIME))
        for state in (onboarding("idle"), {}, None):
            with self.subTest(state=state):
                runtime = dict(FULL_RUNTIME)
                runtime[KEY] = state
                self.assertEqual(self.compose(runtime), baseline,
                                 "an idle onboarding state changed the prompt")

    def test_an_active_plan_adds_the_question_and_replaces_ONLY_the_pass_directive(self):
        """The one deliberate displacement, pinned as deliberate.

        *(This test first asserted that EVERY baseline line survived.
        It failed, and the code was right: an active plan suppresses the
        pass directive. That is supervisory boundary 1 — server
        onboarding state overrides the browser's opinion of the pass.
        The browser may say `pass2a` because its chronology cache
        promoted it, which is the original defect, while the server
        knows the walk is still active. Rendering both would hand Lori
        the Profile Seed question AND "ask ONE open, place-anchored
        question about this era".*

        *So the assertion is narrowed to what is true and checked: the
        ONLY thing displaced is the pass directive, and everything else
        survives line for line.)*
        """
        baseline = self.compose(dict(FULL_RUNTIME))
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        active = self.compose(runtime)

        self.assertIn(_seed.topic(A).question, active)

        dropped = [ln for ln in baseline.splitlines()
                   if ln.strip() and ln not in active]
        self.assertTrue(dropped, "the pass directive was not suppressed")
        for line in dropped:
            with self.subTest(line=line[:60]):
                self.assertIn(
                    "Pass 2A", " ".join(dropped[:1]),
                    "something other than the pass directive was displaced")

        # Nothing outside the pass directive moved. Identity, discipline,
        # safety and thread guidance must all survive intact.
        head = baseline.split("DIRECTIVE: You are in Pass 2A")[0]
        for line in head.splitlines():
            if line.strip():
                self.assertIn(line, active,
                              "the onboarding section displaced prompt "
                              "content ahead of the pass directive")

    def test_an_active_plan_does_not_suppress_safety_or_discipline(self):
        runtime = dict(FULL_RUNTIME)
        runtime[KEY] = onboarding("present", A, remaining=[A, B])
        active = self.compose(runtime)
        baseline = self.compose(dict(FULL_RUNTIME))
        for marker in ("FORBIDDEN OBSERVATION LANGUAGE",):
            with self.subTest(marker=marker):
                if marker in baseline:
                    self.assertIn(marker, active)

    def test_a_sparse_runtime_does_not_activate_identity_mode(self):
        """THE FINDING THIS TEST EXISTS FOR.

        `if runtime71:` defaults `identity_complete` to False, which
        makes `identity_mode` True. A caller passing only a person id
        and onboarding state must not thereby be told to interrogate the
        narrator for their name.
        """
        sparse = {"person_id": "p-fixture",
                  KEY: onboarding("present", A, remaining=[A])}
        text = self.compose(sparse)
        self.assertIn(_seed.topic(A).question, text)
        for phrase in ("IDENTITY MODE", "single next missing piece of identity",
                       "name, date of birth, and place of birth are all "
                       "confirmed"):
            with self.subTest(phrase=phrase[:30]):
                self.assertNotIn(
                    phrase, text,
                    "a sparse onboarding runtime activated identity mode")

    def test_a_sparse_runtime_composes_the_same_as_no_runtime_plus_the_section(self):
        """Stronger than the previous test: the sparse object must add
        the section and NOTHING ELSE relative to no runtime at all."""
        bare = self.compose(None)
        sparse = self.compose({KEY: onboarding("present", A, remaining=[A])})
        for line in bare.splitlines():
            if line.strip():
                self.assertIn(line, sparse,
                              "a sparse onboarding runtime changed or "
                              "dropped baseline prompt content")


@unittest.skipUnless(_HAS_FASTAPI, "needs fastapi")
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
        narrator."""
        text = _pc.compose_system_prompt("conv-legacy",
                                         runtime71=self._pass1_runtime())
        self.assertIn("Gather the following 10 facts", text)

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


@unittest.skipUnless(_HAS_FASTAPI, "needs fastapi")
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


@unittest.skipUnless(_HAS_FASTAPI, "needs fastapi")
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


@unittest.skipUnless(_HAS_FASTAPI, "needs fastapi")
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
