"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A — the wiring.

This is the slice where the 43 authorities stop being an inventory and
start governing the response path, so the tests are about the properties
that make that safe rather than about any single authority:

    V2  a consumer re-reads live configuration mid-turn
    V3  a stale browser turn_mode reactivates a disabled route

Structural assertions here walk the AST of `chat_ws.py`. They are not a
stylistic preference: no behavioural test can reliably catch "somebody
added a second store read in eight months' time", and a substring search
over source matches comments — which this session has now done four
times, once in a test written specifically to prevent it.
"""

import ast
import os
import unittest

from api.services import lori_guard_authority as authority
from api.services import lori_guard_gate as gate
from api.services import lori_guard_registry as reg


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAT_WS = os.path.join(
    _REPO, "server", "code", "api", "routers", "chat_ws.py")


def _source():
    with open(_CHAT_WS, encoding="utf-8") as fh:
        return fh.read()


def _lines():
    return _source().split("\n")


def _tree():
    return ast.parse(_source())


def _turn_function(tree):
    for node in ast.walk(tree):
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_generate_and_stream_inner"):
            return node
    raise AssertionError("_generate_and_stream_inner not found")


def _calls_to(node, name):
    """Line numbers of calls to `name`, however it was imported.

    Both forms matter here. `_rt.note(...)` is an Attribute call, but
    witness detection arrives as `from ... import detect_and_compose as
    _wm_dac` and is then a bare Name — so an Attribute-only matcher
    silently finds nothing and the ordering assertion it feeds passes
    for the wrong reason.
    """
    out = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        func = n.func
        if isinstance(func, ast.Attribute) and func.attr == name:
            out.append(n.lineno)
        elif isinstance(func, ast.Name) and func.id == name:
            out.append(n.lineno)
    return sorted(out)


def _aliases_for(tree, imported_name):
    """Local names bound to `imported_name` by any `from ... import`."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == imported_name:
                    names.add(alias.asname or alias.name)
    return names


class AcquisitionIsSingularTests(unittest.TestCase):
    """One acquisition boundary per turn. Not two, not zero."""

    def test_acquired_exactly_once(self):
        calls = _calls_to(_turn_function(_tree()), "acquire_turn_authority")
        self.assertEqual(
            len(calls), 1,
            f"acquire_turn_authority is called {len(calls)} times at "
            f"{calls}. A second acquisition would produce two "
            f"configurations in one turn and no way to say which one "
            f"the narrator's response came from.")

    def test_acquisition_dominates_every_authority(self):
        """It must precede routing, not merely prompt composition.

        The earliest registered authorities are the routes, and they act
        long before a prompt exists. Acquiring 'before prompt
        composition' would already be too late.
        """
        fn = _turn_function(_tree())
        acquisition = _calls_to(fn, "acquire_turn_authority")[0]

        tree = _tree()
        witness = []
        for alias in _aliases_for(tree, "detect_and_compose"):
            witness.extend(_calls_to(fn, alias))
        self.assertTrue(
            witness,
            "No witness-detection call found. The matcher, not the "
            "product, is probably wrong — check how it is imported.")
        self.assertLess(
            acquisition, min(witness),
            "Witness detection (registry ids 22/23) runs before the "
            "authority snapshot exists.")

        # The browser's proposed turn_mode, and the first route gate.
        proposal = next(
            i + 1 for i, l in enumerate(_lines())
            if l.strip().startswith("turn_mode = (params.get(\"turn_mode\")"))
        self.assertLess(
            acquisition, proposal,
            "The client's proposed turn_mode is adopted before the "
            "snapshot exists.")


class NoConsumerReResolvesTests(unittest.TestCase):
    """V2 — downstream reads the snapshot, never live configuration."""

    FORBIDDEN_CALLS = (
        "read_state", "read_overrides", "read_revision",   # the store
        "armed_eval_dir", "experiment_is_armed",           # the marker
        "person_is_testing_only",                          # eligibility
        "resolve",                                         # re-resolution
    )

    def test_the_turn_never_reads_live_configuration(self):
        fn = _turn_function(_tree())
        offenders = {}
        for attr in self.FORBIDDEN_CALLS:
            calls = _calls_to(fn, attr)
            if calls:
                offenders[attr] = calls
        self.assertEqual(
            offenders, {},
            f"{offenders} — a turn must read `_authority.snapshot` and "
            f"nothing else. Re-reading live state mid-turn means the "
            f"configuration can change underneath a response that is "
            f"already half-composed.")

    def test_the_store_is_not_imported_into_the_router(self):
        with open(_CHAT_WS, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.name)
        self.assertNotIn(
            "lori_guard_store", imported,
            "The router must reach persistence only through the gate's "
            "single acquisition.")


class RouteClampTests(unittest.TestCase):
    """V3 — client proposes, server resolves."""

    def _snapshot_without(self, *ids):
        overrides = {i: False for i in ids}
        return authority.resolve(overrides, safety_parked_probe=lambda: False)

    def test_every_deterministic_route_is_registered(self):
        """The clamp is only as complete as this mapping."""
        for mode, rid in reg.DETERMINISTIC_ROUTE_GATES.items():
            with self.subTest(mode=mode):
                item = reg.by_id(rid)
                self.assertIsNotNone(item)
                self.assertEqual(item.cls, reg.CLASS_ROUTE)

    def test_a_disabled_correction_route_is_not_selected(self):
        """Id 26's classifier is `lvRouteTurn` in the BROWSER, so a
        stale client can propose 'correction' whatever the server chose."""
        snapshot = self._snapshot_without(26)
        self.assertFalse(snapshot.is_selected(26))
        self.assertEqual(reg.DETERMINISTIC_ROUTE_GATES["correction"], 26)

    def test_protected_floor_hold_can_never_be_clamped(self):
        """A narrator who has claimed the floor is not an experiment."""
        snapshot = authority.resolve(
            authority.all_switchable_off_overrides(),
            safety_parked_probe=lambda: False)
        self.assertTrue(
            snapshot.is_selected(reg.DETERMINISTIC_ROUTE_GATES["floor_hold"]),
            "Floor hold is registry id 20 and PROTECTED; All Switchable "
            "Off must not silence it and let Lori talk over the narrator.")

    def test_all_switchable_off_excludes_every_switchable_route(self):
        snapshot = authority.resolve(
            authority.all_switchable_off_overrides(),
            safety_parked_probe=lambda: False)
        for mode, rid in reg.DETERMINISTIC_ROUTE_GATES.items():
            item = reg.by_id(rid)
            with self.subTest(mode=mode):
                if item.policy == reg.POLICY_SWITCHABLE:
                    self.assertFalse(snapshot.is_selected(rid))
                else:
                    self.assertTrue(snapshot.is_selected(rid))

    def test_the_clamp_runs_after_routing_and_before_the_gates(self):
        lines = _lines()
        clamp = next(
            i + 1 for i, l in enumerate(lines)
            if "DETERMINISTIC_ROUTE_GATES.get(turn_mode)" in l)
        first_gate = next(
            i + 1 for i, l in enumerate(lines)
            if l.strip() == 'if turn_mode == "floor_hold":')
        safety_pin = next(
            i + 1 for i, l in enumerate(lines)
            if l.strip() == "if _safety_forced_interview:")
        self.assertLess(safety_pin, clamp,
                        "Safety precedence must be resolved before the "
                        "clamp so it cannot be overridden by it.")
        self.assertLess(clamp, first_gate,
                        "The clamp must precede every route gate.")

    def test_structured_narrative_is_clamped_at_its_own_site(self):
        """Id 23 sets a flag rather than a turn_mode, so the turn_mode
        clamp cannot reach it."""
        lines = _lines()
        guarded = [
            i + 1 for i, l in enumerate(lines)
            if "_witness_use_llm_receipt = True" in l and not l.strip().startswith("#")
        ]
        self.assertTrue(guarded)
        window = "\n".join(lines[max(0, guarded[0] - 12):guarded[0]])
        self.assertIn("is_selected(23)", window)


class SafetyAndFailClosedTests(unittest.TestCase):

    def test_acquisition_failure_yields_canonical_production(self):
        """The authority layer may never fail a narrator's turn."""
        lines = _lines()
        idx = next(i for i, l in enumerate(lines)
                   if "acquire_turn_authority(person_id)" in l)
        window = "\n".join(lines[idx:idx + 20])
        self.assertIn("except Exception", window)
        self.assertIn(
            "canonical_acquisition", window,
            "The fallback must come from the gate. Reaching past it to "
            "lori_guard_authority would give the response path a second "
            "way to obtain a configuration.")

    def test_a_real_narrator_is_canonical_even_when_armed(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".runtime" / "eval").mkdir(parents=True)
            gate.eval_marker_path(root).write_text("run-1", encoding="utf-8")
            result = gate.acquire_turn_authority(
                "real-person",
                repo_root=root,
                testing_only_probe=lambda _p: False,
                trace_enabled_probe=lambda: True,
                connection_factory=lambda: None)
            self.assertFalse(result.experiment_applied)
            self.assertEqual(result.gate_reason, gate.GATE_NOT_TESTING_ONLY)


class TraceIdentityTests(unittest.TestCase):

    def test_identity_is_bound_to_the_trace(self):
        lines = _lines()
        self.assertTrue(
            any("_authority.trace_identity()" in l for l in lines),
            "Every traced turn must carry the configuration that "
            "produced it, or the transcript is not evidence.")

    def test_identity_is_recorded_on_canonical_turns_too(self):
        """Not only on experiments.

        'Production defaults, reason not_testing_only' is as much a fact
        about a turn as an armed experiment is; annotating only
        experiments would leave every baseline turn ambiguous.
        """
        result = gate.acquire_turn_authority(
            None, testing_only_probe=lambda _p: False,
            trace_enabled_probe=lambda: True,
            connection_factory=lambda: None)
        identity = result.trace_identity()
        self.assertFalse(identity["experiment_applied"])
        self.assertEqual(identity["gate_reason"], gate.GATE_NO_PERSON)
        self.assertIn("registry_fingerprint", identity)
        self.assertIn("selection_fingerprint", identity)


if __name__ == "__main__":
    unittest.main()
