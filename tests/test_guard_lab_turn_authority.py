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

    def test_structured_narrative_is_unreachable_when_excluded(self):
        """Id 23 sets a flag rather than a turn_mode, so the turn_mode
        clamp cannot reach it.

        SUPERSEDED DESIGN, kept as a corrected assertion rather than
        deleted. This originally required a guard on the branch itself.
        That was the wrong place: the same detector also produces id 22,
        and its verdict leaks into ordinary turns through other
        variables, so the verdict is now discarded at the detector and
        this branch simply becomes unreachable. A branch-level guard
        would be a second authority for one decision.
        """
        lines = _lines()
        branch = next(
            i for i, l in enumerate(lines)
            if "_witness_use_llm_receipt = True" in l
            and not l.strip().startswith("#"))
        # The branch is entered only when a verdict survived the
        # detector clamp above it.
        gate_line = next(
            i for i in range(branch, 0, -1)
            if "_is_witness_mode and _witness_answer is not None" in lines[i])
        clamp = next(i for i, l in enumerate(lines)
                     if "is_selected(_wm_authority)" in l)
        self.assertLess(
            clamp, gate_line,
            "The witness verdict must be discarded before the routing "
            "branch reads it.")


class EffectiveModeHandoffTests(unittest.TestCase):
    """V3, completed: the clamp must reset BOTH copies of turn_mode.

    The local variable governs the response branch; the completed-turn
    hooks read the mode back out of `params` (`:896`, `:1089`) to decide
    extraction and placement eligibility, and both eligibility sets are
    frozenset({"interview"}).

    The first cut of the clamp reset only the local. So a stale browser
    proposing "correction" with id 26 excluded got the ordinary
    interview response — correct — and then lost extraction anyway,
    because the completion hook still saw "correction" in params. That
    is conversation-light bought by weakening memory-strict, which is
    the one trade this work order exists to refuse.
    """

    def test_the_clamp_writes_params_as_well_as_the_local(self):
        lines = _lines()
        idx = next(i for i, l in enumerate(lines)
                   if "DETERMINISTIC_ROUTE_GATES.get(turn_mode)" in l)
        window = "\n".join(lines[idx:idx + 14])
        self.assertIn('turn_mode = "interview"', window)
        self.assertIn(
            'params["turn_mode"] = "interview"', window,
            "The completed-turn hooks read params, not the local. "
            "Resetting one copy leaves a rejected client proposal "
            "deciding extraction eligibility.")

    def test_the_rejected_proposal_is_kept_but_never_decides(self):
        lines = _lines()
        self.assertTrue(
            any("_proposed_turn_mode" in l for l in lines),
            "Keep what the client asked for, for the trace.")
        fn = _turn_function(_tree())
        # It may be logged; it may not gate anything.
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                names = {n.id for n in ast.walk(node.test)
                         if isinstance(n, ast.Name)}
                self.assertNotIn(
                    "_proposed_turn_mode", names,
                    "A rejected client proposal must not appear in a "
                    "branch condition.")

    def test_the_precedent_it_follows_still_exists(self):
        """The correction fallthrough learned this first.

        If that fix is ever removed, this clamp is the only thing left
        holding the invariant and somebody should notice.
        """
        lines = _lines()
        self.assertTrue(
            any('params["turn_mode"] = "interview"' in l
                and "correction" not in l for l in lines))
        joined = "\n".join(lines)
        self.assertIn("Reset BOTH copies of the", joined)


class DeterministicRouteTraceTests(unittest.TestCase):
    """An ON route must be as attributable as an LLM turn."""

    def test_the_trace_opens_before_every_route_finalizer(self):
        fn = _turn_function(_tree())
        begins = _calls_to(fn, "begin")
        self.assertEqual(
            len(begins), 1,
            f"Exactly one trace per turn; found {begins}. Two traces for "
            f"one turn means two partial records and no way to say which "
            f"one is the response.")

        finalizers = _calls_to(fn, "_finalize_deterministic_turn")
        self.assertTrue(finalizers, "no route finalizers found")
        self.assertLess(
            begins[0], min(finalizers),
            "Deterministic routes finalize and return before the trace "
            "exists, so a routed turn answers the narrator and leaves no "
            "record — John's era 01 is the standing example.")

    def test_the_finalizer_completes_the_trace_as_a_response(self):
        lines = _lines()
        idx = next(i for i, l in enumerate(lines)
                   if l.startswith("async def _finalize_deterministic_turn"))
        end = next(i for i in range(idx + 1, len(lines))
                   if lines[i].startswith("async def _safety_notify_operator"))
        body = "\n".join(lines[idx:end])

        self.assertIn("_rt.finish(", body)
        self.assertIn("generation_attempted", body)
        self.assertIn("effective_turn_mode", body)
        self.assertNotIn(
            "_rt.terminal(", body,
            "terminal() means the model was never called AND no response "
            "was produced. A deterministic answer IS a response; "
            "recording one as terminal corrupts the distinction that "
            "vocabulary exists to protect.")

    def test_completion_lives_in_the_shared_seam_not_six_branches(self):
        fn = _turn_function(_tree())
        self.assertEqual(
            _calls_to(fn, "finish"), [],
            "The turn function must not complete the trace per branch — "
            "five inline copies drifted apart once already, which is why "
            "_finalize_deterministic_turn exists.")


class DetectorIsolationTests(unittest.TestCase):
    """An excluded route's DETECTOR must not still change the turn.

    The clamp controls entry into the deterministic finalizer. That is
    not the same as isolating the authority, because two detectors set
    state that is read on ORDINARY turns:

      * `_is_meta_question` is read at `:4093`, where it suppresses bank
        flush;
      * `_story_recall_subject` is read at `:4267`, where it turns story
        grounding on — and that line's own comment says the variable "is
        set only by the recall detector".

    So a route could be OFF while its detector still altered what a
    supposedly ordinary turn received. The switch would not be isolating
    the thing it names. Excluded therefore means the verdict is
    DISCARDED, not merely unrouted.
    """

    def _clamp_line(self, needle):
        return next(i + 1 for i, l in enumerate(_lines()) if needle in l)

    def test_meta_question_verdict_is_discarded_before_the_bank_flush_read(self):
        clamp = self._clamp_line("meta_question \"\n" ) if False else next(
            i + 1 for i, l in enumerate(_lines())
            if "is_selected(21)" in l)
        leak = next(
            i + 1 for i, l in enumerate(_lines())
            if "_is_meta_question and _meta_question_answer is not None)" in l
            and l.strip().startswith("and not"))
        self.assertLess(
            clamp, leak,
            "id 21's verdict must be discarded before :4093 reads it to "
            "suppress bank flush on an ordinary turn.")

    def test_story_recall_verdict_is_discarded_before_the_grounding_read(self):
        clamp = next(i + 1 for i, l in enumerate(_lines())
                     if "is_selected(24)" in l)
        leak = next(i + 1 for i, l in enumerate(_lines())
                    if "_grounding_on or _story_recall_subject" in l)
        self.assertLess(
            clamp, leak,
            "id 24's verdict must be discarded before the grounding read, "
            "or an excluded route still injects grounding context into an "
            "ordinary turn.")

    def test_witness_verdict_is_discarded_per_detection_type(self):
        """One detector, two separately selectable authorities."""
        lines = _lines()
        idx = next(i for i, l in enumerate(lines) if "_wm_authority = (" in l)
        window = "\n".join(lines[idx:idx + 12])
        self.assertIn("STRUCTURED_NARRATIVE", window)
        self.assertIn("is_selected(_wm_authority)", window)
        self.assertIn("_witness_answer = None", window)

    def test_id23_is_not_clamped_twice(self):
        """Discarding the verdict makes the branch unreachable.

        A second guard on the same decision is a second authority for
        it, and the two can disagree.
        """
        lines = _lines()
        self.assertEqual(
            sum(1 for l in lines if "is_selected(23)" in l), 0,
            "id 23 is clamped at the detector; a branch-level guard "
            "would be a duplicate authority.")

    def test_every_detector_clamp_follows_acquisition(self):
        fn = _turn_function(_tree())
        acquisition = _calls_to(fn, "acquire_turn_authority")[0]
        clamps = [i + 1 for i, l in enumerate(_lines())
                  if "detector-clamp" in l]
        self.assertGreaterEqual(len(clamps), 3)
        self.assertLess(acquisition, min(clamps))

    def test_protected_routes_have_no_detector_clamp(self):
        """Floor hold is id 20 and PROTECTED — never discarded."""
        lines = _lines()
        self.assertEqual(
            sum(1 for l in lines if "is_selected(20)" in l), 0,
            "A protected authority must not be conditionally discarded.")


class ConsumerAccountingTests(unittest.TestCase):
    """Every switchable authority must reach a real consumer.

    This is the claim that was NOT yet earned when the registry landed:
    the ids existed and the catalog was generated, but nothing proved a
    given id was consulted anywhere in production. An id that no
    consumer reads is a switch wired to nothing — it would appear in the
    Operator panel, accept a click, change a fingerprint, and alter no
    behaviour at all.

    Consumers are discovered by AST across the three surfaces that
    consume the snapshot, so the accounting cannot drift into a
    hand-written list agreeing with another hand-written list.
    """

    SURFACES = (
        ("server", "code", "api", "routers", "chat_ws.py"),
        ("server", "code", "api", "prompt_composer.py"),
        ("server", "code", "api", "services", "lori_communication_control.py"),
    )

    def _consumed_ids(self):
        """Ids appearing in a selection check anywhere on the surfaces."""
        found = set()
        for parts in self.SURFACES:
            path = os.path.join(_REPO, *parts)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())

            # Literal checks: is_selected(41), _selected(sel, 41)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", ""))
                if name not in ("is_selected", "_selected", "_guard_selected"):
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(
                            arg.value, int):
                        found.add(arg.value)
                    elif isinstance(arg, ast.Name):
                        found.add(arg.id)          # resolved below

            # Named constants: CC_WORD_LIMIT = 35, GUARD_ANCHORED_ASK = 9
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and isinstance(
                        node.value, ast.Constant) and isinstance(
                        node.value.value, int):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id in found:
                            found.discard(t.id)
                            found.add(node.value.value)

        # ROUTES ARE CONSUMED DYNAMICALLY, and that is correct rather
        # than a gap. The clamp looks the id up by turn mode —
        # `DETERMINISTIC_ROUTE_GATES.get(turn_mode)` — precisely so a new
        # route cannot be added without appearing in the registry map,
        # and the witness detector picks 22 or 23 from the detection
        # type. A literal-only scan cannot see either, so the mapping
        # itself is the evidence: every id it names is reachable.
        for parts in self.SURFACES:
            path = os.path.join(_REPO, *parts)
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
            if "DETERMINISTIC_ROUTE_GATES.get(turn_mode)" in source:
                found |= set(reg.DETERMINISTIC_ROUTE_GATES.values())
            if "is_selected(_wm_authority)" in source:
                found |= {22, 23}
        return {i for i in found if isinstance(i, int)}

    def test_every_switchable_authority_has_a_consumer(self):
        consumed = self._consumed_ids()
        missing = sorted(
            i.id for i in reg.switchable() if i.id not in consumed)
        self.assertEqual(
            missing, [],
            f"Switchable authorities with no consumer: {missing}. A "
            f"switch that reads nowhere would accept an operator click, "
            f"move the selection fingerprint, and change no behaviour.")

    def test_no_protected_authority_is_individually_guarded(self):
        """No literal `is_selected(<protected id>)` anywhere.

        A generic lookup is a different matter and is allowed: the route
        clamp resolves an id from `DETERMINISTIC_ROUTE_GATES`, which
        includes floor hold at id 20. That check is safe because the
        resolver guarantees a PROTECTED authority always resolves to its
        canonical default — the next test proves that rather than
        assuming it — whereas a hand-written `is_selected(20)` would be
        somebody deciding to make it conditional.
        """
        literals = set()
        for parts in self.SURFACES:
            path = os.path.join(_REPO, *parts)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (node.func.attr if isinstance(node.func, ast.Attribute)
                        else getattr(node.func, "id", ""))
                if name not in ("is_selected", "_selected", "_guard_selected"):
                    continue
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(
                            arg.value, int):
                        literals.add(arg.value)
        wrongly = sorted(i.id for i in reg.protected() if i.id in literals)
        self.assertEqual(
            wrongly, [],
            f"Protected authorities individually guarded: {wrongly}. "
            f"Safety, floor ownership, fail-closed paths and the Profile "
            f"Seed ledger must not be made conditional by hand.")

    def test_the_route_map_cannot_exclude_a_protected_route(self):
        """The guarantee the previous test relies on.

        Floor hold passes through the same lookup as every other route,
        so what protects it is the resolver, not the call site. Proven
        under the most aggressive configuration available.
        """
        snapshot = authority.resolve(
            authority.all_switchable_off_overrides(),
            safety_parked_probe=lambda: False)
        for mode, rid in reg.DETERMINISTIC_ROUTE_GATES.items():
            item = reg.by_id(rid)
            if item.policy != reg.POLICY_PROTECTED:
                continue
            with self.subTest(mode=mode):
                self.assertTrue(
                    snapshot.is_selected(rid),
                    f"All Switchable Off excluded protected route {rid} "
                    f"({mode}); the clamp would then demote it.")

    def test_the_comm_control_ids_match_the_registry(self):
        """Two copies of one number is how they drift."""
        from api.services import lori_communication_control as cc
        for const, name in (
            ("CC_SAFETY_PATH", "cc_safety_path"),
            ("CC_QUESTION_ATOMICITY", "cc_question_atomicity"),
            ("CC_QUESTION_COUNT_TRUNCATE", "cc_question_count_truncate"),
            ("CC_WORD_LIMIT", "cc_word_limit"),
            ("CC_REFLECTION_SHAPER", "cc_reflection_shaper"),
            ("CC_REFLECTION_VALIDATOR", "cc_reflection_validator"),
            ("CC_PUSH_AFTER_RESISTANCE", "cc_push_after_resistance"),
            ("CC_STUB_COLLAPSE_REPAIR", "cc_stub_collapse_repair"),
            ("CC_CHAIN_ANCHOR_OPENER", "cc_chain_anchor_opener"),
            ("CC_STORY_FIRST_GROUNDING", "cc_story_first_grounding"),
            ("CC_STORY_FIRST_HIERARCHY", "cc_story_first_hierarchy"),
        ):
            with self.subTest(const=const):
                self.assertEqual(getattr(cc, const), reg.by_name(name).id)

    def test_the_prompt_ids_match_the_registry(self):
        from api import prompt_composer as pc
        for const, name in (
            ("GUARD_CORE_IDENTITY", "prompt_core_identity"),
            ("GUARD_INTERVIEW_DISCIPLINE", "prompt_interview_discipline"),
            ("GUARD_REFLECTION_EXAMPLES", "prompt_reflection_examples"),
            ("GUARD_ORAL_HISTORY_RESPONSE", "prompt_oral_history_response"),
            ("GUARD_STORY_MODE_DIRECTIVE", "prompt_story_mode_directive"),
            ("GUARD_QUESTION_HIERARCHY", "prompt_question_hierarchy"),
            ("GUARD_THREAD_SURFACING", "prompt_thread_surfacing"),
            ("GUARD_ANCHORED_ASK", "prompt_anchored_ask"),
            ("GUARD_WITNESS_RECEIPT_DIRECTIVE",
             "prompt_witness_receipt_directive"),
            ("GUARD_WITNESS_FEWSHOT_EXAMPLES",
             "prompt_witness_fewshot_examples"),
        ):
            with self.subTest(const=const):
                self.assertEqual(getattr(pc, const), reg.by_name(name).id)


class PromptSurfaceTests(unittest.TestCase):
    """PROMPT authorities compose from the turn's selection."""

    def test_production_default_composes_everything(self):
        from api import prompt_composer as pc
        self.assertTrue(pc._guard_selected(None, pc.GUARD_ANCHORED_ASK))
        self.assertTrue(pc._guard_selected(None, 999))

    def test_an_excluded_prompt_authority_is_dropped(self):
        from api import prompt_composer as pc
        sel = frozenset({pc.GUARD_INTERVIEW_DISCIPLINE})
        self.assertTrue(
            pc._guard_selected(sel, pc.GUARD_INTERVIEW_DISCIPLINE))
        self.assertFalse(
            pc._guard_selected(sel, pc.GUARD_WITNESS_FEWSHOT_EXAMPLES))

    def test_the_composer_does_not_resolve_its_own_authority(self):
        """It receives a selection; it never builds one."""
        path = os.path.join(_REPO, "server", "code", "api",
                            "prompt_composer.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.name)
                if node.module:
                    imported.add(node.module.rsplit(".", 1)[-1])
        for forbidden in ("lori_guard_store", "lori_guard_gate",
                          "lori_guard_authority", "lori_guard_registry"):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported)


class RevisionSemanticsTests(unittest.TestCase):
    """`revision` is the CONSUMED generation, not the persisted one."""

    def test_canonical_turns_carry_the_documented_sentinel(self):
        result = gate.canonical_acquisition(gate.GATE_NOT_TESTING_ONLY)
        self.assertEqual(result.snapshot.revision, gate.CANONICAL_REVISION)
        self.assertEqual(gate.CANONICAL_REVISION, 0)

    def test_the_sentinel_is_documented_as_consumed_not_persisted(self):
        import inspect
        doc = inspect.getdoc(gate) or ""
        module_src = inspect.getsource(gate)
        self.assertIn("CANONICAL_REVISION", module_src)
        self.assertIn("consumed", module_src.lower())

    def test_a_real_narrator_does_not_claim_the_stores_revision(self):
        """The store may be at 12 while this turn consumed none of it."""
        result = gate.acquire_turn_authority(
            "real-person",
            testing_only_probe=lambda _p: False,
            trace_enabled_probe=lambda: True,
            connection_factory=lambda: None)
        self.assertEqual(result.snapshot.revision, gate.CANONICAL_REVISION)
        self.assertFalse(result.experiment_applied)


class MarkerSemanticsHonestyTests(unittest.TestCase):
    """Don't claim parity with the shell that the code does not have."""

    def test_the_difference_from_the_shell_is_documented(self):
        """Assert the acknowledgement, don't ban a phrase.

        The first version forbade "same semantics" anywhere in the
        module — and failed on the sentence explaining why that claim
        would be false. Banning a string cannot distinguish a claim from
        a correction of it; this is the fifth time in this session that
        a source-matching test has matched its own prose.
        """
        import inspect
        src = inspect.getsource(gate).lower()
        self.assertIn(
            "not byte-for-byte identical", src,
            "Python uses .strip(); the shell's $(<file) strips trailing "
            "newlines only. The difference must be stated, not implied.")
        self.assertIn("deliberate", src)

    def test_whitespace_only_marker_is_unarmed_here(self):
        repo = _ArmedRepoLocal("   \t  ")
        self.addCleanup(repo.cleanup)
        self.assertIsNone(gate.armed_eval_dir(repo.root))


class _ArmedRepoLocal:
    def __init__(self, contents=None):
        import tempfile
        from pathlib import Path
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".runtime" / "eval").mkdir(parents=True)
        if contents is not None:
            gate.eval_marker_path(self.root).write_text(
                contents, encoding="utf-8")

    def cleanup(self):
        self._tmp.cleanup()


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
