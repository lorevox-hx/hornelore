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
        head must still be a required section."""
        self.assertIn('_PromptAssembly("system_head", system_head)',
                      _COMPOSER_SRC)
        self.assertIn("self.add(name, text, required=True)", _COMPOSER_SRC)

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
