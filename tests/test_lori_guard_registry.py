"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Parts 4-7.

The registry only has value if it keeps agreeing with the tree. A
hand-maintained list of guards is the same failure mode as the stale
current-work lists CLAUDE.md records twice — it reads as authority while
being wrong.

So the accounting here is STRUCTURAL, taken from the AST of the shipped
router rather than from string occurrence counts. That distinction is not
pedantry: three source-slicing test bugs in one day came from `index()`
and `count()` matching a comment instead of a statement, and every one of
them passed against broken code. An `ast.Assign` node cannot be a
comment.
"""

import ast
import os
import unittest

from api.services import lori_guard_registry as reg


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAT_WS = os.path.join(
    _REPO, "server", "code", "api", "routers", "chat_ws.py")


def _chat_ws_tree():
    with open(_CHAT_WS, encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _final_text_assignments(tree):
    """(lineno, unparsed RHS) for every `final_text = ...` in the router."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "final_text":
                    out.append((node.lineno, ast.unparse(node.value)))
    return sorted(out)


def _turn_mode_gate_values(tree):
    """Every constant `turn_mode == "..."` comparison in the router."""
    out = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Compare)
                and isinstance(node.left, ast.Name)
                and node.left.id == "turn_mode"):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(
                        comparator.value, str):
                    out.add(comparator.value)
    return out


class RegistryInvariantTests(unittest.TestCase):

    def test_ids_are_unique(self):
        ids = [i.id for i in reg.REGISTRY]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate intervention id.")

    def test_names_are_unique(self):
        names = [i.name for i in reg.REGISTRY]
        self.assertEqual(len(names), len(set(names)))

    def test_pipeline_positions_are_unique(self):
        positions = [i.position for i in reg.REGISTRY]
        self.assertEqual(
            len(positions), len(set(positions)),
            "Two interventions claim the same pipeline position; execution "
            "order would be ambiguous.")

    def test_classes_are_valid(self):
        for item in reg.REGISTRY:
            with self.subTest(id=item.id):
                self.assertIn(item.cls, reg.VALID_CLASSES)

    def test_counterfactual_modes_are_valid(self):
        for item in reg.REGISTRY:
            with self.subTest(id=item.id):
                self.assertIn(item.counterfactual, reg.VALID_COUNTERFACTUALS)

    def test_every_entry_carries_descriptive_metadata(self):
        for item in reg.REGISTRY:
            with self.subTest(id=item.id):
                self.assertTrue(item.display.strip())
                self.assertTrue(item.purpose.strip())
                self.assertTrue(item.motivating_failure.strip())
                self.assertTrue(item.location.strip())

    def test_selection_order_cannot_change_execution_order(self):
        """{33, 40} and {40, 33} must denote the same experiment."""
        forward = [i.id for i in reg.in_pipeline_order()]
        self.assertEqual(forward, sorted(
            reg.REGISTRY, key=lambda i: i.position) and forward)
        positions = [i.position for i in reg.in_pipeline_order()]
        self.assertEqual(positions, sorted(positions))


class CounterfactualHonestyTests(unittest.TestCase):
    """A PROMPT block cannot produce an in-turn counterfactual.

    Excluding it changes the model's input, so there is nothing to
    record except that it was excluded. Any claim of the form
    "P11 would have produced X" requires a second generation.
    """

    def test_prompt_interventions_require_a_rerun(self):
        for item in reg.by_class(reg.CLASS_PROMPT):
            with self.subTest(id=item.id):
                self.assertEqual(
                    item.counterfactual, reg.CF_REQUIRES_RERUN,
                    f"Intervention {item.id} ({item.name}) is a PROMPT block "
                    f"claiming '{item.counterfactual}'. It changes generation "
                    f"itself; an in-turn counterfactual would be a fabricated "
                    f"claim.")

    def test_locked_entries_are_not_switchable(self):
        for item in reg.REGISTRY:
            if item.counterfactual == reg.CF_LOCKED:
                with self.subTest(id=item.id):
                    self.assertFalse(
                        item.switchable,
                        f"Intervention {item.id} is counterfactually locked "
                        f"but marked switchable.")

    def test_unswitchable_entries_explain_themselves(self):
        for item in reg.REGISTRY:
            if item.switchable:
                continue
            with self.subTest(id=item.id):
                self.assertTrue(
                    item.policy_reason.strip(),
                    f"Intervention {item.id} ({item.name}) is not switchable "
                    f"and does not say why. An unexplained lock is "
                    f"indistinguishable from an oversight.")


class ControlPolicyTests(unittest.TestCase):
    """Three states, because a padlock is not a reason.

    "Cannot, for safety" and "cannot, until someone splits a string"
    are different truths, and an operator looking at a disabled row
    deserves to know which one it is.
    """

    def test_policies_are_valid(self):
        for item in reg.REGISTRY:
            with self.subTest(id=item.id):
                self.assertIn(item.policy, reg.VALID_POLICIES)

    def test_switchable_is_derived_not_stored(self):
        """Two fields meaning the same thing is how they drift."""
        self.assertNotIn(
            "switchable", getattr(reg.Intervention, "__dataclass_fields__", {}),
            "`switchable` must remain a derived property of `policy`.")
        for item in reg.REGISTRY:
            with self.subTest(id=item.id):
                self.assertEqual(
                    item.switchable, item.policy == reg.POLICY_SWITCHABLE)

    def test_population_after_the_seams_landed(self):
        """37 / 6 / 0 — derived, not hard-coded anywhere in runtime logic.

        Was 35/6/2 at the Parts 4-7 checkpoint. Section B split the two
        prompt example families out of their parent constants, so the
        PENDING_SEAM population is now empty and `All Switchable Off`
        can finally be truthful about prompt composition.
        """
        counts = reg.policy_counts()
        self.assertEqual(counts[reg.POLICY_SWITCHABLE], 37)
        self.assertEqual(counts[reg.POLICY_PROTECTED], 6)
        self.assertEqual(counts[reg.POLICY_PENDING_SEAM], 0)
        self.assertEqual(sum(counts.values()), len(reg.REGISTRY))

    def test_no_authority_remains_unseparable(self):
        """The state that exists to be eliminated."""
        self.assertEqual(
            [i.id for i in reg.pending_seam()], [],
            "A PENDING_SEAM authority means All Switchable Off silently "
            "leaves it running.")

    def test_the_exemplar_families_are_now_switchable(self):
        for name in ("prompt_reflection_examples",
                     "prompt_witness_fewshot_examples"):
            with self.subTest(name=name):
                self.assertEqual(
                    reg.by_name(name).policy, reg.POLICY_SWITCHABLE)

    def test_floor_hold_is_protected_not_pending(self):
        """Id 20 is withheld by product judgment, not by a missing seam."""
        item = reg.by_name("route_floor_hold")
        self.assertEqual(item.policy, reg.POLICY_PROTECTED)

    def test_safety_entries_are_locked(self):
        for name in ("prompt_safety_protocol", "cc_safety_path"):
            item = reg.by_name(name)
            self.assertIsNotNone(item, f"{name} missing from the registry.")
            self.assertFalse(
                item.switchable,
                "CLAUDE.md: safety may never be activated or deactivated "
                "through an environment value.")


class StructuralAccountingTests(unittest.TestCase):
    """The tree is the authority; the registry must keep up with it."""

    def test_every_final_text_writer_is_accounted_for(self):
        tree = _chat_ws_tree()
        found = _final_text_assignments(tree)
        self.assertTrue(found, "No final_text assignments found — the AST "
                               "probe itself is broken.")
        unaccounted = [
            (lineno, rhs) for lineno, rhs in found
            if rhs not in reg.FINAL_TEXT_WRITERS
        ]
        self.assertEqual(
            unaccounted, [],
            f"chat_ws.py assigns final_text at a site the registry does not "
            f"account for: {unaccounted}. Add an Intervention and a "
            f"FINAL_TEXT_WRITERS entry, or classify it as infrastructure.")

    def test_registry_does_not_claim_writers_that_no_longer_exist(self):
        tree = _chat_ws_tree()
        actual = {rhs for _, rhs in _final_text_assignments(tree)}
        stale = sorted(set(reg.FINAL_TEXT_WRITERS) - actual)
        self.assertEqual(
            stale, [],
            f"FINAL_TEXT_WRITERS names expressions that are gone from "
            f"chat_ws.py: {stale}. A registry that describes code which no "
            f"longer exists is the stale-control-document failure.")

    def test_every_referenced_intervention_id_exists(self):
        for rhs, ids in reg.FINAL_TEXT_WRITERS.items():
            for i in ids:
                with self.subTest(rhs=rhs, id=i):
                    self.assertIsNotNone(
                        reg.by_id(i),
                        f"FINAL_TEXT_WRITERS[{rhs!r}] cites unknown id {i}.")

    def test_every_deterministic_route_gate_is_registered(self):
        tree = _chat_ws_tree()
        gates = _turn_mode_gate_values(tree)
        unaccounted = sorted(gates - set(reg.DETERMINISTIC_ROUTE_GATES))
        self.assertEqual(
            unaccounted, [],
            f"chat_ws.py gates on turn_mode values with no registry entry: "
            f"{unaccounted}. A new deterministic route can bypass the model "
            f"entirely; it must be registered.")

    def test_route_gate_ids_are_route_class(self):
        for mode, i in reg.DETERMINISTIC_ROUTE_GATES.items():
            item = reg.by_id(i)
            with self.subTest(mode=mode):
                self.assertIsNotNone(item)
                self.assertEqual(item.cls, reg.CLASS_ROUTE)


class CommControlDecompositionTests(unittest.TestCase):
    """One checkpoint named `comm_control` hid eleven authorities.

    Without the split you can learn "guard 4 hurt Lori" while having no
    idea whether that was word truncation, atomicity, reflection
    shaping, stub repair or the chain-anchor opener.
    """

    EXPECTED_OPERATIONS = (
        "cc_safety_path",
        "cc_question_atomicity",
        "cc_question_count_truncate",
        "cc_word_limit",
        "cc_reflection_shaper",
        "cc_reflection_validator",
        "cc_push_after_resistance",
        "cc_stub_collapse_repair",
        "cc_chain_anchor_opener",
        "cc_story_first_grounding",
        "cc_story_first_hierarchy",
    )

    def test_each_bundled_operation_is_independently_registered(self):
        for name in self.EXPECTED_OPERATIONS:
            with self.subTest(name=name):
                self.assertIsNotNone(
                    reg.by_name(name),
                    f"{name} is not independently registered; it would be "
                    f"indistinguishable inside the comm_control checkpoint.")

    def test_the_bundle_write_back_maps_to_all_of_them(self):
        ids = set(reg.FINAL_TEXT_WRITERS["_cc_result.final_text"])
        named = {reg.by_name(n).id for n in self.EXPECTED_OPERATIONS}
        self.assertTrue(
            named.issubset(ids),
            f"The comm_control write-back does not account for "
            f"{sorted(named - ids)}.")

    def test_operations_have_distinct_ordered_positions(self):
        items = [reg.by_name(n) for n in self.EXPECTED_OPERATIONS]
        positions = [i.position for i in items]
        self.assertEqual(len(positions), len(set(positions)))


class ProfileSeedIsTwoAuthoritiesTests(unittest.TestCase):
    """Memory strict, conversation light — applied to the one component
    that was doing both jobs at once."""

    def test_ledger_and_delivery_are_separate_entries(self):
        ledger = reg.by_name("profile_seed_ledger")
        delivery = reg.by_name("profile_seed_delivery")
        self.assertIsNotNone(ledger)
        self.assertIsNotNone(delivery)
        self.assertNotEqual(ledger.id, delivery.id)

    def test_ledger_is_locked_memory_integrity(self):
        ledger = reg.by_name("profile_seed_ledger")
        self.assertFalse(
            ledger.switchable,
            "The topic ledger is durable memory state. A phantom "
            "presentation once closed childhood_home forever without "
            "asking; that protection is not a conversational style choice.")

    def test_delivery_is_a_switchable_final_writer(self):
        delivery = reg.by_name("profile_seed_delivery")
        self.assertEqual(delivery.cls, reg.CLASS_FINAL_WRITER)
        self.assertTrue(delivery.switchable)

    def test_delivery_records_the_measured_finding(self):
        delivery = reg.by_name("profile_seed_delivery")
        self.assertIn("7 of 15", delivery.known_harm)


class ExemplarBlocksAreRegisteredTests(unittest.TestCase):
    """Kent and Janice are consenting lab narrators. This is an
    exemplar-leak and overfitting finding, not a privacy one."""

    def test_both_leaking_example_families_are_registered(self):
        for name in ("prompt_witness_fewshot_examples",
                     "prompt_reflection_examples"):
            with self.subTest(name=name):
                item = reg.by_name(name)
                self.assertIsNotNone(item)
                self.assertEqual(item.cls, reg.CLASS_PROMPT)
                self.assertTrue(
                    item.known_harm.strip(),
                    f"{name} must record its measured leak evidence.")

    def test_exemplar_blocks_point_at_their_seams(self):
        """The debt this test used to record is now paid.

        It previously asserted PENDING_SEAM and `NOT SEPARABLE YET`.
        Section B split both families out of their parent constants, so
        the assertion inverts: each must now name the composition
        function that assembles it.
        """
        for name, fn in (
            ("prompt_witness_fewshot_examples",
             "compose_witness_receipt_directive"),
            ("prompt_reflection_examples",
             "compose_interview_discipline"),
        ):
            item = reg.by_name(name)
            with self.subTest(name=name):
                self.assertEqual(item.policy, reg.POLICY_SWITCHABLE)
                self.assertNotIn("NOT SEPARABLE YET", item.policy_reason)
                self.assertIn(fn, item.location)

    def test_exemplar_residuals_are_recorded_not_hidden(self):
        """Excluding the examples does not make the prompt name-free.

        Both directives keep narrator nouns inside PROHIBITIONS — the
        witness MUST NOT names Vince and Janice, and reflection rule 4
        names Spokane and Montreal. Those are the guards against the
        failures they describe, not exemplars, so they stay; a baseline
        that claimed to be free of narrator names would be lying.
        """
        for name in ("prompt_witness_fewshot_examples",
                     "prompt_reflection_examples"):
            with self.subTest(name=name):
                self.assertIn("RESIDUAL", reg.by_name(name).known_harm)


class ProductionUnchangedTests(unittest.TestCase):
    """Parts 4-7 are an inventory. They must not alter behaviour."""

    RESPONSE_PATH = (
        ("server", "code", "api", "routers", "chat_ws.py"),
        ("server", "code", "api", "services", "lori_communication_control.py"),
        ("server", "code", "api", "services", "lori_response_guards.py"),
        ("server", "code", "api", "services", "lori_witness_mode.py"),
        ("server", "code", "api", "prompt_composer.py"),
    )

    def test_registry_is_not_imported_by_the_response_path(self):
        """Inert by design for this checkpoint.

        The seams that consume these ids land with the selector that
        gives them meaning, so production response behaviour is touched
        once rather than twice — once to add unused seams and again to
        wire them up. Until then nothing narrator-facing may consult the
        registry, or the inventory starts changing the behaviour it
        exists to describe.
        """
        for parts in self.RESPONSE_PATH:
            path = os.path.join(_REPO, *parts)
            with self.subTest(module=parts[-1]):
                with open(path, encoding="utf-8") as fh:
                    self.assertNotIn("lori_guard_registry", fh.read())


if __name__ == "__main__":
    unittest.main()
