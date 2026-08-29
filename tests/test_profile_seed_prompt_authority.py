"""The prompt states who owns the turn, and preserves the browser's claim.

WO-LORI-PROFILE-SEED-REACHABILITY-01, Phase 3, Commit A.

    PYTHONPATH=server/code python3 -m unittest tests.test_profile_seed_prompt_authority

── THE DEFECT THIS CLOSES ────────────────────────────────────────────

`current_pass` and `effective_pass` arrive FROM THE BROWSER. Eight UI
sites promote `pass1 → pass2a` on chronology readiness or an era click,
and none of them knows anything about onboarding. So the browser can
assert `pass2a` while the server is conducting a Profile Seed walk.

Phase 2 already stopped that from SUPPRESSING the walk — the pass
directive is skipped whenever a validated plan exists, and
`test_profile_seed_composer_section` pins it. What remained is that the
prompt still *stated* the browser's pass, so one system message could
read `pass: pass2a` while describing an onboarding turn. Lori was handed
a contradiction and asked to reconcile it.

── WHY THE BROWSER VALUE IS KEPT ─────────────────────────────────────

The obvious fix — rewrite `current_pass` to `pass1` while a walk runs —
was proposed and REJECTED, deliberately. It hides live client state from
anyone reading a captured prompt, and the browser's belief is a real
fact about the system even when it is not the authoritative one. A
debugger who cannot see that the browser thought it was in `pass2a`
cannot diagnose why it thought so.

So both truths are emitted, labelled:

    browser_pass: pass2a          <- what the client claims
    effective_pass: profile_seed  <- what the server is actually doing
    profile_seed_active: true     <- which machine owns this turn

── BYTE STABILITY IS THE OTHER HALF ──────────────────────────────────

An INACTIVE walk must compose exactly as it did before this change:
`pass:` then `effective_pass:`, no third line. Historical narrators,
completed walks, malformed payloads and narrators with no row all take
that path, and they are the overwhelming majority of turns. The
byte-stability tests below are what make this a bounded change rather
than a prompt rewrite.
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

from api import prompt_composer as _pc            # noqa: E402
from api.services import profile_seed as _seed    # noqa: E402
from api.services import profile_seed_turn as _turn  # noqa: E402

KEY = _pc.PROFILE_SEED_ONBOARDING_KEY
A = "childhood_home"
B = "siblings"

#: An identity-complete narrator mid-interview — the "existing prompt"
#: whose bytes must not move for any inactive state.
BASE_RUNTIME = {
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


def onboarding(action, topic_id=A, known=(), remaining=(B,),
               completes_walk=False):
    return {"action": action, "topic_id": topic_id,
            "known_topics": list(known), "remaining_topics": list(remaining),
            "completes_walk": completes_walk}


def compose(runtime, conv="conv-phase3"):
    return _pc.compose_system_prompt(conv, runtime71=runtime)


def runtime_with(plan_state=None, **over):
    r = dict(BASE_RUNTIME)
    r.update(over)
    if plan_state is not None:
        r[KEY] = plan_state
    return r


class ActiveWalkTests(unittest.TestCase):
    """A validated plan owns the turn, and the prompt says so."""

    def test_the_browser_pass_is_RELABELLED_not_erased(self):
        text = compose(runtime_with(onboarding("present")))
        self.assertIn("browser_pass: pass2a", text,
                      "the browser's claim was erased; a captured prompt no "
                      "longer shows what the client believed")
        self.assertNotIn("\n  pass: pass2a", text,
                         "the unlabelled `pass:` line survived, so the "
                         "browser value can still be read as authoritative")

    def test_the_effective_phase_is_SERVER_DERIVED(self):
        text = compose(runtime_with(onboarding("present")))
        self.assertIn("effective_pass: profile_seed", text)
        self.assertNotIn("effective_pass: pass2a", text)

    def test_the_prompt_states_which_machine_owns_the_turn(self):
        text = compose(runtime_with(onboarding("present")))
        self.assertIn("profile_seed_active: true", text)

    def test_every_renderable_action_gets_the_server_phase(self):
        """PRESENT, RE_PRESENT, ACKNOWLEDGE and HOLD are all active.

        HOLD especially: it asks nothing, but the walk is live and the
        legacy pass directive stays suppressed, so the prompt must not
        revert to describing a browser pass on a held turn.
        """
        for action in ("present", "re_present", "acknowledge", "hold"):
            with self.subTest(action=action):
                text = compose(runtime_with(onboarding(action)))
                self.assertIn("effective_pass: profile_seed", text)
                self.assertIn("browser_pass: pass2a", text)

    def test_a_stale_browser_identity_pass_does_NOT_activate_identity_mode(self):
        """The specific stale-state defect.

        A validated ACTIVE plan implies the server already resolved the
        identity anchors — that resolution is what promoted the row out
        of `pending`. A browser still asserting `effective_pass:
        identity` would otherwise drag the turn into identity
        interrogation, and the narrator would be asked for their name and
        their childhood home in the same breath.
        """
        text = compose(runtime_with(onboarding("present"),
                                    effective_pass="identity"))
        self.assertIn("effective_pass: profile_seed", text)
        self.assertNotIn("effective_pass: identity", text)

    def test_a_stale_identity_complete_FALSE_does_not_either(self):
        text = compose(runtime_with(onboarding("present"),
                                    identity_complete=False))
        self.assertIn("effective_pass: profile_seed", text)


class InactiveStatesPreserveBytesTests(unittest.TestCase):
    """Everything that is not a validated active plan composes as before.

    These are the majority of turns, and this class is what keeps the
    change bounded.
    """

    def baseline(self):
        return compose(runtime_with(None))

    def test_no_onboarding_key_at_all_is_unchanged(self):
        text = self.baseline()
        self.assertIn("  pass: pass2a", text)
        self.assertIn("  effective_pass: pass2a", text)
        self.assertNotIn("browser_pass", text)
        self.assertNotIn("profile_seed_active", text)

    def test_an_IDLE_plan_is_byte_identical_to_no_key(self):
        self.assertEqual(compose(runtime_with(onboarding("idle"))),
                         self.baseline(),
                         "an idle plan moved the prompt")

    def test_a_MALFORMED_payload_is_byte_identical_to_no_key(self):
        """Malformed renders nothing AND suppresses nothing.

        The accepted Phase 2 rule. A payload we cannot validate must
        leave the existing prompt untouched rather than half-applying a
        server phase we did not actually resolve.
        """
        for bad in ({"action": "present", "topic_id": "not_a_real_topic"},
                    {"action": "banana", "topic_id": A},
                    {"topic_id": A},
                    {"action": "present", "topic_id": A,
                     "known_topics": {"a": 1}},
                    "not-a-dict", 7, None, []):
            with self.subTest(payload=repr(bad)[:40]):
                self.assertEqual(compose(runtime_with(bad)), self.baseline())

    def test_an_unknown_topic_does_not_produce_a_server_phase(self):
        text = compose(runtime_with(onboarding("present",
                                               topic_id="no_such_topic")))
        self.assertNotIn("effective_pass: profile_seed", text)
        self.assertNotIn("profile_seed_active", text)

    def test_the_browser_effective_pass_still_wins_when_inactive(self):
        """Server authority applies to the walk, not to everything.

        With no active plan the composer has resolved nothing, so it must
        not start overriding client state it has no opinion about.
        """
        text = compose(runtime_with(None, effective_pass="identity"))
        self.assertIn("effective_pass: identity", text)


class TransportAuthorityTests(unittest.TestCase):
    """A client cannot inject an onboarding plan the server did not resolve.

    ── THE HOLE THIS CLOSES, 2026-08-29 ────────────────────────────────

    `attach_onboarding` used only to ADD the key. When the server had no
    plan it left the runtime untouched — and on the WebSocket path that
    runtime is `runtime71`, which **comes from the browser**. So a
    client-supplied onboarding payload survived into composition
    unchallenged, would have rendered an onboarding block, and would have
    suppressed the legacy pass directive for a narrator the server says
    has no walk at all.

    Found while fixing a different defect: the composer-side test
    `test_an_untruthful_sparse_runtime_does_NOT_get_identity_for_free`
    guards the identity half of the same hole, and following its
    reasoning back showed the transport half was open.
    """

    def setUp(self):
        from api.services import profile_seed_runtime as _rt
        self._rt = _rt

    def test_a_client_supplied_payload_is_REMOVED_when_the_server_has_none(self):
        forged = {"person_id": "p", KEY: onboarding("present")}
        out = self._rt.attach_onboarding(forged, _turn.TurnPlan(_turn.IDLE),
                                         None)
        self.assertNotIn(
            KEY, out,
            "a browser-supplied onboarding payload survived a turn on which "
            "the server resolved no plan — the client could fabricate a walk")

    def test_a_client_supplied_payload_is_OVERWRITTEN_when_the_server_has_one(self):
        forged = {"person_id": "p",
                  KEY: onboarding("present", topic_id="military")}
        plan = _turn.TurnPlan(_turn.PRESENT, A, 3)
        out = self._rt.attach_onboarding(
            forged, plan, {"known_topics": [], "remaining_topics": [A]})
        self.assertEqual(out[KEY]["topic_id"], A,
                         "the client's topic survived the server's plan")
        self.assertEqual(out[KEY]["action"], _turn.PRESENT)

    def test_the_forged_payload_WOULD_have_rendered(self):
        """Non-vacuity: prove the forgery is otherwise convincing.

        If the fabricated payload were malformed it would render nothing
        anyway, and the two tests above would pass for the wrong reason.
        """
        self.assertTrue(
            _pc.profile_seed_onboarding_active(
                runtime_with(onboarding("present"))),
            "the forged payload is not a renderable plan, so removing it "
            "proves nothing")

    def test_a_runtime_with_no_key_is_unaffected(self):
        plain = {"person_id": "p", "current_pass": "pass2a"}
        out = self._rt.attach_onboarding(plain, _turn.TurnPlan(_turn.IDLE),
                                         None)
        self.assertEqual(out, plain)
        self.assertIsNot(out, plain, "the runtime was mutated in place")


class NonVacuityTests(unittest.TestCase):
    """Proof the assertions above could fail."""

    def test_the_fixture_really_does_produce_an_active_plan(self):
        self.assertTrue(
            _pc.profile_seed_onboarding_active(
                runtime_with(onboarding("present"))),
            "the active fixture is not actually active, so every "
            "ActiveWalkTests assertion is about the inactive path")

    def test_the_inactive_fixtures_really_are_inactive(self):
        for state in (None, onboarding("idle"),
                      {"action": "present", "topic_id": "not_a_real_topic"}):
            with self.subTest(state=repr(state)[:40]):
                self.assertFalse(
                    _pc.profile_seed_onboarding_active(runtime_with(state)))

    def test_the_two_paths_produce_DIFFERENT_prompts(self):
        """If these ever matched, every test in this file would be vacuous."""
        self.assertNotEqual(compose(runtime_with(onboarding("present"))),
                            compose(runtime_with(None)))

    def test_the_runtime_key_is_imported_not_retyped(self):
        self.assertEqual(KEY, "profile_seed_onboarding")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
