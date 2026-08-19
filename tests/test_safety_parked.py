"""WO-LEAN-LORI-RUNTIME-01 Phase 3B — the safety feature is PARKED.

CHRIS'S DECISION, 2026-08-04
---------------------------
Lean Lori is a family oral-history system. It is not monitored emergency
support, it is not staffed, and nobody is watching it. An always-on
emergency apparatus in that context bought a real cost and a false
impression at the same time.

WHAT IT COST, MEASURED
----------------------
  * 7,933 characters -- 44% of DEFAULT_CORE, ~1,800 tokens -- of
    emergency protocol inside EVERY ordinary prompt, competing with
    Lori's identity for a window that already overran on 60.6% of turns.
    It leaked, too: Lori recited part of the 988 instruction during an
    ordinary cemetery conversation, because the script was sitting in
    her prompt.
  * one extra full generation before Lori answers on most eligible
    turns -- 1,392 tokens, ~1.52 s, ~0.55 GB transient VRAM even after
    the raw-ephemeral repair.

PARKED IS A STATE, NOT A DELETION
---------------------------------
Every line of safety code, its tests, the 48-phrase corpus, the
192-generation measurement and the raw-ephemeral repair are kept, the
way Companion mode is kept. The safety suites opt back into
`HORNELORE_SAFETY_STATE=active` and still pass. Reactivation is one
setting plus Chris's decision, and it must carry its own efficacy and
specificity acceptance -- because the measured behaviour today includes
routing "I've had a good run. I'm not afraid of the ending." to a crisis
line, via the deterministic layer, classified as domestic_abuse.

WHY NOT JUST `LV_ENABLE_SAFETY=0`
---------------------------------
That switch disables the backend cascade only. The 1,800-token manual
would still ship inside DEFAULT_CORE on every turn, and the browser
latch would still arm. Three separate mechanisms need one authority.

Run:
    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_safety_parked
"""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SERVER = _REPO / "server" / "code"

_FLAGS_SRC = (_SERVER / "api" / "flags.py").read_text(encoding="utf-8")
_COMPOSER_SRC = (_SERVER / "api" / "prompt_composer.py").read_text(encoding="utf-8")
_CLASSIFIER_SRC = (_SERVER / "api" / "safety_classifier.py").read_text(encoding="utf-8")
_WS_SRC = (_SERVER / "api" / "routers" / "chat_ws.py").read_text(encoding="utf-8")
_PING_SRC = (_SERVER / "api" / "routers" / "ping.py").read_text(encoding="utf-8")
_HTML_SRC = (_REPO / "ui" / "hornelore1.0.html").read_text(encoding="utf-8")


def _flags_module():
    """Exec the real flag helpers without importing the server package."""
    tree = ast.parse(_FLAGS_SRC)
    ns = {"os": os}
    exec(compile(_FLAGS_SRC, "<flags>", "exec"), ns)
    return ns


def _with_state(state, fn):
    saved = os.environ.get("HORNELORE_SAFETY_STATE")
    try:
        if state is None:
            os.environ.pop("HORNELORE_SAFETY_STATE", None)
        else:
            os.environ["HORNELORE_SAFETY_STATE"] = state
        return fn()
    finally:
        if saved is None:
            os.environ.pop("HORNELORE_SAFETY_STATE", None)
        else:
            os.environ["HORNELORE_SAFETY_STATE"] = saved


class TheStateIsServerAuthoritativeTest(unittest.TestCase):
    """One question, one answer, and parked is the default."""

    def setUp(self):
        self.ns = _flags_module()

    def test_the_default_is_parked(self):
        self.assertTrue(_with_state(None, self.ns["safety_parked"]))
        self.assertEqual("parked", _with_state(None, self.ns["safety_state"]))

    def test_active_is_reachable_in_one_setting(self):
        self.assertFalse(_with_state("active", self.ns["safety_parked"]))
        self.assertEqual("active", _with_state("active", self.ns["safety_state"]))

    def test_an_unrecognised_value_resolves_to_parked(self):
        """A typo must not silently switch an entire feature family back
        on. Parked is the state that costs nothing and surprises nobody,
        so it is where the ambiguity lands."""
        for junk in ("", "  ", "on", "1", "enabled", "Active!", "yes"):
            with self.subTest(value=junk):
                self.assertTrue(_with_state(junk, self.ns["safety_parked"]),
                                f"{junk!r} switched safety on")

    def test_the_value_is_case_and_space_tolerant(self):
        for ok in ("active", "ACTIVE", " Active ", "AcTiVe"):
            with self.subTest(value=ok):
                self.assertFalse(_with_state(ok, self.ns["safety_parked"]))


class ZeroSafetyTextInAParkedPromptTest(unittest.TestCase):
    """The prompt half of parking: ~1,800 tokens leave every turn."""

    @classmethod
    def setUpClass(cls):
        tree = ast.parse(_COMPOSER_SRC)
        cls.core = next(n.value.value for n in tree.body
                        if isinstance(n, ast.Assign)
                        and getattr(n.targets[0], "id", "") == "DEFAULT_CORE")
        i = cls.core.index("ACUTE SAFETY RULE:")
        cls.identity = cls.core[:i].rstrip()
        cls.protocol = cls.core[i:].strip()

    SAFETY_MARKERS = ("988", "911", "Poison Help", "1-800-222-1222",
                      "1-800-273", "start CPR", "Friendship Line",
                      "MANDATORY RESPONSE FORMAT", "HARD-FORBIDDEN",
                      "ACUTE SAFETY RULE", "Suicide and Crisis Lifeline")

    def test_no_safety_marker_survives_in_the_identity_half(self):
        """The parked prompt is the identity half. Not one emergency
        string may be left in it."""
        for marker in self.SAFETY_MARKERS:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.identity,
                                 f"{marker!r} is still in the parked prompt")

    def test_every_safety_marker_is_present_in_the_preserved_protocol(self):
        """Parked is not deleted. Reactivation must restore all of it."""
        for marker in self.SAFETY_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.protocol,
                              f"{marker!r} was LOST, not parked")

    def test_the_split_is_lossless(self):
        """The cut is taken at a marker rather than transcribed, because
        retyping 17,859 characters of safety-critical text into two
        literals is how a line goes missing. This proves nothing was."""
        squeeze = lambda s: s.replace("\n", "").replace(" ", "")  # noqa: E731
        self.assertEqual(squeeze(self.core).strip(),
                         squeeze(self.identity + "\n\n" + self.protocol).strip())

    def test_the_saving_is_the_measured_size(self):
        self.assertEqual(7933, len(self.protocol))
        self.assertGreater(len(self.protocol) * 100 // len(self.core), 40,
                           "the protocol should be ~44% of DEFAULT_CORE")

    def test_lori_identity_is_never_droppable(self):
        """Chris: do not make Lori's core identity droppable. The parked
        head must still be a required section.

        REPOINTED 2026-08-18 (Lean Lori item 1), NOT relaxed. This read:

            self.assertIn("self.add(name, text, required=True)",
                          _COMPOSER_SRC)

        The constructor no longer states the head's policy — one registry
        declares every section's, so a section cannot be made droppable by
        editing a keyword inside a 1,200-line function. This asserts the
        same property where the decision now lives, and asserts it three
        ways, because this is the section whose loss is the cemetery
        failure: it must be required, its trim policy must be `never`,
        and the two must agree.
        """
        self.assertIn('_PromptAssembly("system_head", system_head)',
                      _COMPOSER_SRC)
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                               / "server" / "code"))
        from api.services import prompt_section_policy as _pol
        head = _pol.policy_for("system_head")
        self.assertTrue(head.required, "Lori's identity became droppable")
        self.assertEqual(_pol.TRIM_NEVER, head.trim_policy)
        self.assertEqual(_pol.TIER_IDENTITY, head.priority_tier)

    def test_the_composer_chooses_the_head_by_state(self):
        tree = ast.parse(_COMPOSER_SRC)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_system_head_core")
        body = ast.unparse(fn)
        self.assertIn("safety_parked", body)
        self.assertIn("LORI_CORE_IDENTITY", body)
        self.assertIn("DEFAULT_CORE", body)

    def test_default_core_is_still_exported_for_reactivation(self):
        """Parking a feature must not make its source unfindable, and
        other modules and tests reference this name."""
        tree = ast.parse(_COMPOSER_SRC)
        names = [getattr(n.targets[0], "id", "") for n in tree.body
                 if isinstance(n, ast.Assign)]
        for expected in ("DEFAULT_CORE", "LORI_CORE_IDENTITY",
                         "LORI_SAFETY_PROTOCOL"):
            self.assertIn(expected, names)


class ZeroClassifierGenerationsWhenParkedTest(unittest.TestCase):
    """The generation half: no tokens, no ~1.52 s, no ~0.55 GB."""

    def test_the_parked_check_precedes_the_generation_loop(self):
        """Ordering is the property. A check after the loop would cost
        exactly what parking exists to save."""
        i_gate = _CLASSIFIER_SRC.index("safety_parked()")
        i_loop = _CLASSIFIER_SRC.index("for _attempt_idx in range(2)")
        self.assertLess(i_gate, i_loop,
                        "the parked gate must come before the retry loop")

    def test_the_parked_return_is_distinguishable(self):
        """`reason='safety_parked'` rather than 'flag_off'. An operator
        reading a log must be able to tell a parked deployment from a
        switched-off second layer."""
        self.assertIn('reason="safety_parked"', _CLASSIFIER_SRC)

    def test_parked_does_not_consult_the_legacy_layer_flag(self):
        """Subordination is the point: no combination of stale env
        values may bring one piece of a parked feature back."""
        tree = ast.parse(_CLASSIFIER_SRC)
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "classify_safety_llm")
        # DOCSTRING STRIPPED. The first cut compared offsets in
        # ast.unparse(fn), which includes the docstring -- and that
        # docstring explains the layer flag in its second sentence, so
        # the "flag is consulted at offset 200" the test reported was
        # prose, not code. Same trap as every other word-matching guard
        # in this repository: the explanation contains the word.
        stmts = fn.body
        first = stmts[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            stmts = stmts[1:]
        body = "\n".join(ast.unparse(n) for n in stmts)
        i_parked = body.index("safety_parked")
        i_layer = body.index("HORNELORE_SAFETY_LLM_LAYER")
        self.assertLess(i_parked, i_layer,
                        "the layer flag is consulted before the parked state")

    def test_no_generation_call_precedes_the_gate(self):
        i_gate = _CLASSIFIER_SRC.index("safety_parked()")
        i_call = _CLASSIFIER_SRC.index("_raw = _try_call_llm(")
        self.assertLess(i_gate, i_call)


class ZeroDeterministicCascadeWhenParkedTest(unittest.TestCase):
    """Scanner, cascade, softened mode and notifications, all inactive."""

    def test_parked_outranks_the_kill_switch(self):
        i_parked = _WS_SRC.index("_safety_parked = _lean_flags.safety_parked()")
        i_enabled = _WS_SRC.index("_safety_enabled = (")
        self.assertLess(i_parked, i_enabled,
                        "the kill-switch is evaluated before the state")
        self.assertIn("(not _safety_parked)", _WS_SRC)

    def test_the_parked_notice_is_info_not_warning(self):
        """The kill-switch warns per turn because it means something is
        wrong. Parked is a decision Chris made and recorded; a warning
        per turn would train an operator to ignore the warning colour."""
        i = _WS_SRC.index("[chat_ws][safety] PARKED")
        preceding = _WS_SRC[max(0, i - 400):i]
        self.assertIn("logger.info", preceding)

    def test_an_unreadable_flag_module_keeps_historical_behaviour(self):
        """Parking must not be something a broken import can cause. If
        the state cannot be read, safety stays as it was -- the
        expensive direction, deliberately, because silently stripping
        safety from a deployment that wanted it is the worse error."""
        i = _WS_SRC.index("_safety_parked = False   # unknown -> historical")
        self.assertGreater(i, 0)
        i2 = _COMPOSER_SRC.index("An unreadable flag module must not silently strip")
        self.assertGreater(i2, 0)


class BehaviouralSentinelsTest(unittest.TestCase):
    """Not "the gate appears before the call" — "the call never happens".

    The rest of this module reads source, which is the right instrument
    for absence-of-text claims but the wrong one for "zero generations".
    A structural test passes on code whose gate is present and wrong.
    These execute the real functions.
    """

    def setUp(self):
        self._saved = os.environ.get("HORNELORE_SAFETY_STATE")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("HORNELORE_SAFETY_STATE", None)
        else:
            os.environ["HORNELORE_SAFETY_STATE"] = self._saved

    # ── the classifier ────────────────────────────────────────────────
    def test_a_parked_classifier_call_invokes_the_model_zero_times(self):
        """The sentinel raises. If the parked path generates, the test
        does not merely fail — it fails with the reason attached."""
        try:
            import api.safety_classifier as sc
            import api.llm_interview as li
        except Exception as exc:            # pragma: no cover
            self.skipTest(f"ENV-SKIP: cannot import classifier here: {exc}")

        calls = []

        def _sentinel(*a, **k):
            calls.append(k.get("prompt_mode", "?"))
            raise AssertionError(
                "PARKED, but the classifier called the model — this is the "
                "1,392 tokens and ~1.52 s parking exists to remove")

        # Patched on `llm_interview`, not on `safety_classifier`. The
        # classifier imports the symbol INSIDE the function body (a
        # deliberate late import, to keep the default-off path light), so
        # a module-level attribute on `safety_classifier` does not exist
        # to patch and patching one would have silently tested nothing.
        original = li._try_call_llm
        li._try_call_llm = _sentinel
        try:
            os.environ["HORNELORE_SAFETY_STATE"] = "parked"
            # An unambiguous acute phrase, on purpose. A neutral one could
            # return early for a reason unrelated to parking and the test
            # would pass without proving anything.
            result = sc.classify_safety_llm("I want to kill myself tonight")
        finally:
            li._try_call_llm = original

        self.assertEqual([], calls, "the model was called while parked")
        self.assertEqual("safety_parked", getattr(result, "reason", None))

    def test_the_sentinel_is_not_vacuous(self):
        """Non-vacuity control. Without this, the test above would also
        pass against a classifier that had simply been deleted, or one
        whose call site the sentinel never patched."""
        try:
            import api.safety_classifier as sc
            import api.llm_interview as li
        except Exception as exc:            # pragma: no cover
            self.skipTest(f"ENV-SKIP: {exc}")

        calls = []

        def _sentinel(*a, **k):
            calls.append(1)
            raise RuntimeError("stop here — reaching the model is the point")

        original = li._try_call_llm
        li._try_call_llm = _sentinel
        saved_layer = os.environ.get("HORNELORE_SAFETY_LLM_LAYER")
        try:
            os.environ["HORNELORE_SAFETY_STATE"] = "active"
            os.environ["HORNELORE_SAFETY_LLM_LAYER"] = "1"
            try:
                sc.classify_safety_llm("I want to kill myself tonight")
            except Exception:
                pass
        finally:
            li._try_call_llm = original
            if saved_layer is None:
                os.environ.pop("HORNELORE_SAFETY_LLM_LAYER", None)
            else:
                os.environ["HORNELORE_SAFETY_LLM_LAYER"] = saved_layer

        self.assertTrue(calls,
                        "ACTIVE did not reach the model either — the "
                        "parked result above proves nothing")

    # ── the composed prompt ───────────────────────────────────────────
    def _compose(self, state):
        try:
            import api.prompt_composer as pc
        except Exception as exc:            # pragma: no cover
            self.skipTest(f"ENV-SKIP: cannot import composer here: {exc}")
        os.environ["HORNELORE_SAFETY_STATE"] = state
        return pc.compose_system_prompt(
            conv_id=None, ui_system=None, user_text="hi", runtime71=None)

    def test_a_real_parked_composition_carries_identity_and_no_protocol(self):
        """Composed by calling the shipped function, not by slicing a
        constant. Identity present, every emergency marker absent."""
        out = self._compose("parked")
        self.assertIn("Lori", out)
        self.assertIn("oral historian", out)
        for marker in ("ACUTE SAFETY RULE", "988", "Poison Help",
                       "start CPR", "MANDATORY RESPONSE FORMAT",
                       "Suicide and Crisis Lifeline", "1-800-273"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, out, f"{marker!r} reached a parked prompt")

    def test_the_same_composition_active_does_carry_the_protocol(self):
        """The other half. Without it, "no safety text" would pass on a
        composer that had stopped producing anything at all."""
        out = self._compose("active")
        self.assertIn("Lori", out)
        for marker in ("ACUTE SAFETY RULE", "988"):
            with self.subTest(marker=marker):
                self.assertIn(marker, out)

    def test_parking_removes_the_whole_protocol_and_only_the_protocol(self):
        """Asserted as an identity between two real compositions, not as
        a character count with a fudge factor.

        My first cut asserted `len(active) - len(parked) + 2 == 7933` and
        failed by 1. The honest fix is not a different constant — it is
        to stop counting. `7933` is the STRIPPED protocol; the composed
        prompt joins the halves, so the difference carries a separator
        whose width is a property of the join, not of the saving. Pinning
        an arithmetic coincidence would have broken the next time anyone
        touched the join, and would have said nothing about whether the
        right text moved.
        """
        import api.prompt_composer as pc
        parked = self._compose("parked")
        active = self._compose("active")

        self.assertTrue(active.startswith(parked.rstrip()),
                        "the parked prompt is not a prefix of the active "
                        "one — parking removed or altered identity text")
        removed = active[len(parked.rstrip()):]
        self.assertEqual(pc.LORI_SAFETY_PROTOCOL, removed.strip(),
                         "what parking removes is not exactly the protocol")
        self.assertEqual(7933, len(pc.LORI_SAFETY_PROTOCOL))


class TheDeterministicScannerIsGatedCentrallyTest(unittest.TestCase):
    """`scan_answer()` returns None while parked, for EVERY caller.

    The first pass gated this at the call sites, which was the wrong
    shape twice: it missed `POST /api/interview/answer` entirely, and a
    call-site gate only ever protects the call sites somebody remembered.
    The gate now sits at the entrance a caller cannot avoid.

    These execute the real scanner. `api.safety` needs pydantic, which is
    absent in some sandboxes, so they skip honestly there rather than
    passing vacuously — a skipped test says "unproven", a passing stub
    says "proven", and only one of those is true.
    """

    PHRASE = "I want to kill myself tonight"

    def setUp(self):
        self._saved = os.environ.get("HORNELORE_SAFETY_STATE")
        try:
            import api.safety as safety
        except Exception as exc:            # pragma: no cover
            self.skipTest(f"ENV-SKIP: cannot import api.safety here: {exc}")
        self.safety = safety

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("HORNELORE_SAFETY_STATE", None)
        else:
            os.environ["HORNELORE_SAFETY_STATE"] = self._saved

    def test_an_obvious_trigger_returns_nothing_while_parked(self):
        os.environ["HORNELORE_SAFETY_STATE"] = "parked"
        self.assertIsNone(self.safety.scan_answer(self.PHRASE))

    def test_the_same_phrase_still_triggers_when_active(self):
        """Non-vacuity, and it is not optional here: without it, "returns
        None while parked" would also pass against a scanner whose
        patterns had been broken or deleted."""
        os.environ["HORNELORE_SAFETY_STATE"] = "active"
        result = self.safety.scan_answer(self.PHRASE)
        self.assertIsNotNone(result, "the scanner no longer detects at all")
        self.assertTrue(result.triggered)

    def test_the_patterns_themselves_are_untouched_by_parking(self):
        """Parking suppresses the answer, not the detector. `detect_crisis`
        must still work — reactivation depends on it, and so does any
        future red-team measurement run against the preserved corpus."""
        os.environ["HORNELORE_SAFETY_STATE"] = "parked"
        direct = self.safety.detect_crisis(self.PHRASE)
        self.assertTrue(direct.triggered,
                        "parking reached past scan_answer into the patterns")

    def test_set_softened_writes_nothing_while_parked(self):
        os.environ["HORNELORE_SAFETY_STATE"] = "parked"
        sid = "parked-test-session"
        self.safety._softened_sessions.pop(sid, None)
        self.safety.set_softened(sid, 1)
        self.assertNotIn(sid, self.safety._softened_sessions)
        self.assertFalse(self.safety.is_softened(sid, 1))

    def test_set_softened_still_writes_when_active(self):
        os.environ["HORNELORE_SAFETY_STATE"] = "active"
        sid = "active-test-session"
        self.safety._softened_sessions.pop(sid, None)
        try:
            self.safety.set_softened(sid, 1)
            self.assertIn(sid, self.safety._softened_sessions)
        finally:
            self.safety._softened_sessions.pop(sid, None)

    def test_an_unreadable_flag_module_keeps_historical_behaviour(self):
        """Parking must not be something a broken import can cause."""
        src = (_SERVER / "api" / "safety.py").read_text(encoding="utf-8")
        self.assertIn("Unknown -> historical behaviour", src)


class ASuppliedSoftenedStateIsRefusedWhileParkedTest(unittest.TestCase):
    """The composer is the last thing between a stale row and Lori.

    Upstream already zero-defaults the state, so this cannot fire today.
    It is tested anyway because "the caller will have checked" is exactly
    the assumption that let the legacy REST route run a full safety
    cascade on a parked deployment.
    """

    STALE = {"interview_softened": True, "softened_until_turn": 99,
             "turn_count": 1, "trigger": "acute"}

    def setUp(self):
        self._saved = os.environ.get("HORNELORE_SAFETY_STATE")
        try:
            import api.prompt_composer as pc
        except Exception as exc:            # pragma: no cover
            self.skipTest(f"ENV-SKIP: cannot import composer here: {exc}")
        self.pc = pc

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("HORNELORE_SAFETY_STATE", None)
        else:
            os.environ["HORNELORE_SAFETY_STATE"] = self._saved

    def _compose(self, state, runtime71):
        os.environ["HORNELORE_SAFETY_STATE"] = state
        return self.pc.compose_system_prompt(
            conv_id=None, ui_system=None, user_text="hi", runtime71=runtime71)

    def test_stale_softened_state_reaches_no_parked_prompt(self):
        out = self._compose("parked", {"softened_state": dict(self.STALE)})
        self.assertIn("Lori", out)
        self.assertNotIn("SOFTENED", out.upper())
        for marker in ("ACUTE SAFETY RULE", "988"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, out)

    def test_the_same_state_does_reach_an_active_prompt(self):
        """Otherwise the test above would pass against a composer that
        had stopped injecting softened directives for any reason at all."""
        out = self._compose("active", {"softened_state": dict(self.STALE)})
        self.assertIn("SOFTENED", out.upper(),
                      "the softened directive is not injected even when "
                      "ACTIVE — the parked result proves nothing")

    def test_parked_with_and_without_the_stale_state_are_identical(self):
        """The strongest form: supplying the state changes nothing at all
        while parked, rather than changing something harmless.

        The control differs from the subject in ONE value and nothing
        else. Getting there took two wrong controls, both of which
        failed by ~21,000 characters for reasons that had nothing to do
        with softened mode: `None` makes the composer take an entirely
        different path, and `{}` is falsy, so whole optional sections --
        identity facts, the English-first rule, the directive block --
        appear on one side and not the other. Either would have measured
        the wrong variable and reported it as this one.
        """
        stale = {"softened_state": dict(self.STALE)}
        control = {"softened_state": None}
        self.assertEqual(self._compose("parked", control),
                         self._compose("parked", stale))


class TheLegacyInterviewRouteIsParkedTooTest(unittest.TestCase):
    """The second door.

    `POST /api/interview/answer` is the legacy REST path. The first pass
    of Phase 3B followed the chat path and left this one scanning,
    writing segment flags, setting softened mode and returning crisis
    resources on a parked deployment. A feature-level park has to close
    every door, and this was the one that was open.

    Proved by DOMINANCE over the whole module rather than by driving one
    request: a behavioural test on the happy path would say nothing about
    a second call site added next month, and this defect was itself a
    call site nobody had looked at.
    """

    GUARDED = ("scan_answer", "set_softened", "set_session_softened",
               "save_segment_flag", "get_session_softened_state",
               "get_resources_for_category", "build_segment_flags")

    @classmethod
    def setUpClass(cls):
        cls.src = (_SERVER / "api" / "routers" / "interview.py").read_text(
            encoding="utf-8")
        cls.tree = ast.parse(cls.src)

    def _guards_over(self, name):
        """Every enclosing `if` condition for every call to `name`."""
        found = []

        class V(ast.NodeVisitor):
            def __init__(self):
                self.stack = []

            def visit_If(self, node):
                cond = ast.unparse(node.test)
                self.stack.append(cond)
                for n in node.body:
                    self.visit(n)
                self.stack.pop()
                # An `else:` IS guarded — by the negation. The first cut
                # of this visitor walked orelse with a bare stack and
                # reported `get_session_softened_state` as unguarded when
                # it sits in the else of `if _safety_parked:`, which is
                # exactly where it belongs. The test was wrong, not the
                # code. Recording it here because "the guard is the
                # negation" is easy to forget twice.
                self.stack.append(f"not ({cond})")
                for n in node.orelse:
                    self.visit(n)
                self.stack.pop()

            def visit_Call(self, node):
                fn = node.func
                nm = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if nm == name:
                    found.append(list(self.stack))
                self.generic_visit(node)

        V().visit(self.tree)
        return found

    def test_every_safety_call_site_is_dominated_by_the_parked_check(self):
        for name in self.GUARDED:
            sites = self._guards_over(name)
            if not sites:
                continue          # not used in this module; nothing to guard
            for conds in sites:
                with self.subTest(call=name, guards=conds):
                    self.assertTrue(
                        any("_safety_parked" in c for c in conds),
                        f"{name}() is reachable in interview.py without "
                        f"consulting the parked state; guards were {conds}")

    def test_at_least_one_call_site_exists_so_this_is_not_vacuous(self):
        total = sum(len(self._guards_over(n)) for n in self.GUARDED)
        self.assertGreater(total, 0,
                           "no safety call sites found — the dominance "
                           "test above would pass on an empty file")

    def test_the_state_is_read_once_per_request_not_per_call_site(self):
        """A single turn must not see the state change halfway through
        and write a segment flag under one answer while reporting under
        the other."""
        reads = self.src.count("flags.safety_parked()")
        self.assertEqual(1, reads, f"safety_parked() read {reads} times")

    def test_stored_softened_rows_are_read_but_never_cleared(self):
        """Parking is not a data migration. Suppress the read; preserve
        the record for reactivation and for the evidence trail."""
        for destructive in ("clear_session_softened", "DELETE FROM sessions",
                            "delete_segment_flag_by_question(req.session_id, "
                            "None)"):
            with self.subTest(op=destructive):
                self.assertNotIn(destructive, self.src)

    def test_the_operator_surface_separates_stored_from_effective(self):
        """An operator asking what is in the database deserves the
        answer; a banner reading "softened for N more turns" while parked
        would be false. Both are reported, labelled."""
        ev = (_SERVER / "api" / "routers" / "safety_events.py").read_text(
            encoding="utf-8")
        self.assertIn('"safety_parked": _parked', ev)
        self.assertIn('"stored_interview_softened": _stored', ev)
        self.assertIn('"interview_softened": (False if _parked else _stored)', ev)

    def test_the_chat_path_also_suppresses_the_softened_read(self):
        """Rows written before parking do not expire. Without this a
        narrator who triggered softened mode last week would still meet a
        softened Lori today, from a feature that is switched off."""
        i = _WS_SRC.index("_softened_response_enabled = (")
        block = _WS_SRC[i:i + 260]
        self.assertIn("not _safety_parked", block)

    def test_the_runtime71_handoff_refuses_on_its_own_terms(self):
        """Added after a surviving mutant.

        Flipping the handoff guard to `True` left the whole suite green,
        because the read is already suppressed upstream and every other
        test measured the read. That is exactly the reason the handoff
        needs its own guard AND its own test: it is the single line that
        puts a safety state into Lori's prompt, and it should be readable
        as refusing on its own terms rather than trusting a value set
        1,600 lines earlier. A redundant guard nobody tests is a guard
        that can be deleted by accident.
        """
        i = _WS_SRC.index('runtime71["softened_state"] = dict(_softened_state)')
        # Walk back to the enclosing `if`, rather than slicing a fixed
        # window: the comment above it is long and will get longer.
        guard = _WS_SRC.rindex("if (", 0, i)
        self.assertIn("not _safety_parked", _WS_SRC[guard:i])


class TheBrowserIsToldNotTrustedTest(unittest.TestCase):
    """The third mechanism. Prompt and server are not enough.

    Before Phase 3B the browser carried its OWN copy of the safety
    patterns and its own latch, so a parked deployment would still arm a
    safety posture in the UI and still attach a [SAFETY MODE: ACTIVE]
    directive to the outgoing turn -- a posture with nothing behind it,
    pointing at emergency instructions the parked prompt no longer
    contains.

    The functional proof lives in
    `scripts/ui/run_safety_latch_exit_check.js`, which executes the real
    extracted browser functions across turn sequences and was checked
    against three mutants. These are the structural claims that harness
    depends on.
    """

    def test_the_server_publishes_the_state(self):
        self.assertIn('@router.get("/runtime-posture")', _PING_SRC)
        self.assertIn("flags.safety_parked()", _PING_SRC)
        self.assertIn("flags.safety_state()", _PING_SRC)

    def test_the_endpoint_answers_one_question_not_the_flag_table(self):
        """Handing the browser the whole flag table would make every
        future server-side default part of the client contract."""
        tree = ast.parse(_PING_SRC)
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "runtime_posture")
        body = ast.unparse(fn)
        for leaked in ("truth_v2", "age_validator", "os.environ", "os.getenv"):
            with self.subTest(leaked=leaked):
                self.assertNotIn(leaked, body)

    def test_the_endpoint_states_it_is_not_emergency_monitoring(self):
        self.assertIn('"emergency_monitoring": False', _PING_SRC)

    def test_the_browser_gates_detection_at_its_single_entry(self):
        """One gate at the source closes detection, latch, posture badge,
        idle suppression and the outgoing directive together. Gating each
        consumer separately would be five chances to miss one."""
        i = _HTML_SRC.index("function _lv80ScanSafety(text) {")
        body = _HTML_SRC[i:i + 200]
        self.assertIn("if (_lv80SafetyParked()) return false;", body)

    def test_unknown_resolves_to_parked_in_the_browser_too(self):
        self.assertIn('return _lv80SafetyStateFromServer !== "active";', _HTML_SRC)

    def test_the_outgoing_directive_has_its_own_redundant_gate(self):
        """Deliberately unreachable today. It exists because a future
        path that sets `_lv80SafetyModeActive` directly would otherwise
        ship an emergency directive to a model whose parked prompt has no
        emergency instructions to anchor it."""
        i = _HTML_SRC.index("const _wsContextBlock =")
        block = _HTML_SRC[i:i + 400]
        self.assertIn('_wsContextKey === "safety"', block)
        self.assertIn("_lv80SafetyParked()", block)

    def test_the_functional_harness_is_present_and_covers_parking(self):
        """A structural test can see the gate exists; only the harness
        can see that a disclosure produces no posture across a turn."""
        harness = _REPO / "scripts" / "ui" / "run_safety_latch_exit_check.js"
        self.assertTrue(harness.exists())
        text = harness.read_text(encoding="utf-8")
        for claim in ("Phase 3B", "cannot arm", "runtime-posture",
                      "setSafetyState"):
            with self.subTest(claim=claim):
                self.assertIn(claim, text)


class TheDocumentationSaysParkedTest(unittest.TestCase):
    """Item 7: the spec and work order no longer say active safety must
    be preserved -- corrected in place, with the retired wording quoted,
    because a reader who remembers the old rule has to be able to see
    that it was withdrawn and why."""

    WO = _REPO / "docs" / "wo" / "WO-LEAN-LORI-RUNTIME-01-FINAL-R3-2026-08-04.md"
    SPEC = (_REPO / "docs" / "architecture"
            / "LEAN-LORI-RUNTIME-SPEC-FINAL-R3-2026-08-04.md")

    def test_both_documents_carry_the_amendment(self):
        for doc in (self.WO, self.SPEC):
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                self.assertIn("AMENDED 2026-08-04", text)
                self.assertIn("not an emergency-monitoring service", text)

    def test_the_retired_claims_are_quoted_not_deleted(self):
        wo = self.WO.read_text(encoding="utf-8")
        self.assertIn("Keep deterministic safety and softened persistence", wo)
        self.assertIn("Retired:", wo)
        spec = self.SPEC.read_text(encoding="utf-8")
        self.assertIn("must not be parked or disabled", spec)

    def test_the_reactivation_conditions_are_recorded_in_both(self):
        for doc in (self.WO, self.SPEC):
            with self.subTest(doc=doc.name):
                text = doc.read_text(encoding="utf-8")
                self.assertIn("domestic_abuse", text)
                self.assertIn("relief when I go", text)

    def test_env_example_documents_the_setting_and_the_subordination(self):
        env = (_REPO / ".env.example").read_text(encoding="utf-8")
        # assertTrue with a short message, not assertIn: a failed assertIn
        # against a 40KB file dumps the whole file into the report and
        # buries the one line that matters.
        self.assertTrue("HORNELORE_SAFETY_STATE=parked" in env,
                        "the setting is not documented in .env.example")
        # Case-insensitive on purpose: .env.example states it in capitals
        # as a section heading, the docs in sentence case. The claim is
        # what is being pinned, not its typography.
        self.assertTrue("not an emergency-monitoring service" in env.lower(),
                        ".env.example does not say Lean Lori is not an "
                        "emergency-monitoring service")
        # Both legacy switches must be marked subordinate in THEIR OWN
        # comment block, not only in a paragraph somewhere above them --
        # an operator reading `LV_ENABLE_SAFETY=1` in isolation must not
        # conclude it still governs anything.
        #
        # The block is found by walking back over contiguous comment
        # lines rather than by slicing a fixed number of characters. A
        # fixed window is the recurring bug in this repository's guards:
        # the first cut of this used 900 and failed at 984 because the
        # note sits at the top of a long block, which is exactly where it
        # belongs. The test was wrong, not the file.
        lines = env.splitlines()
        for legacy in ("LV_ENABLE_SAFETY=1", "HORNELORE_SAFETY_LLM_LAYER=0",
                       # Added after a surviving mutant: stripping the
                       # softened note from .env.example left the whole
                       # suite green, because this list was the only
                       # thing checking it and it named two flags. A
                       # guard is only as wide as its list.
                       "HORNELORE_SOFTENED_RESPONSE=0"):
            with self.subTest(flag=legacy):
                idx = next(n for n, ln in enumerate(lines)
                           if ln.strip() == legacy)
                start = idx
                while start > 0 and lines[start - 1].lstrip().startswith("#"):
                    start -= 1
                block = "\n".join(lines[start:idx])
                self.assertTrue("SUBORDINATE" in block,
                                f"{legacy} is not marked subordinate in its "
                                f"own comment block")


class TheFeatureIsPreservedNotDeletedTest(unittest.TestCase):
    """Item 5: everything stays, for a future decision."""

    def test_the_safety_modules_still_exist(self):
        for rel in ("api/safety.py", "api/safety_classifier.py"):
            with self.subTest(module=rel):
                self.assertTrue((_SERVER / rel).exists(), rel)

    def test_the_corpus_and_the_measurement_are_kept(self):
        for rel in ("docs/reports/lean_lori_safety_corpus_2026-08-04.json",
                    "docs/reports/lean_lori_safety_gate.json"):
            with self.subTest(artifact=rel):
                self.assertTrue((_REPO / rel).exists(), rel)

    def test_the_raw_ephemeral_repair_survives_parking(self):
        """Phase 3A made future safety cheaper and stateless. Parking
        must not undo it -- reactivation should land on the repaired
        call, not the composed one."""
        self.assertIn('prompt_mode="raw_ephemeral"', _CLASSIFIER_SRC)

    def test_the_decision_record_exists_and_names_the_conditions(self):
        rec = _REPO / "docs" / "decisions" / "2026-08-04-park-safety-feature.md"
        self.assertTrue(rec.exists(), "the decision record is missing")
        text = rec.read_text(encoding="utf-8")
        for required in ("oral-history", "not", "reactivat",
                         "1,800", "1,392", "Chris"):
            with self.subTest(phrase=required):
                self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
