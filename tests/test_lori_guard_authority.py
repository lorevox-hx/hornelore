"""WO-LORI-BASELINE-RESET-AND-GUARD-LAB-01 Continuation A, sections D+E.

Covers the negative cases the work order names explicitly:

    V7   a protected authority can be changed through the API
    V9   reset copies the canonical default into an override
    V11  two different effective selections share a fingerprint
    V12  editing descriptive prose moves the behavioural fingerprint

and the three-state resolution that keeps the Operator panel honest
about rows where effective differs from canonical.
"""

import dataclasses
import unittest

from api.services import lori_guard_authority as auth
from api.services import lori_guard_registry as reg


def _parked(): return True
def _not_parked(): return False


class RegistryFingerprintTests(unittest.TestCase):
    """It identifies the behaviour contract, not the documentation."""

    def test_is_stable_and_hex(self):
        first = auth.registry_fingerprint()
        self.assertEqual(first, auth.registry_fingerprint())
        self.assertEqual(len(first), 64)
        int(first, 16)

    def test_editing_prose_does_not_move_it(self):
        """V12.

        If a `known_harm` paragraph moved the fingerprint, every
        transcript comparison would show a behaviour change whenever
        somebody improved a comment, and the identifier would stop
        meaning anything.
        """
        original = auth.registry_fingerprint()
        prose_edited = tuple(
            dataclasses.replace(
                item,
                purpose=item.purpose + " (reworded)",
                motivating_failure="rewritten for clarity",
                known_harm="expanded with new evidence",
                policy_reason=item.policy_reason + " ",
                location="moved to a different line",
                display=item.display + " v2",
            )
            for item in reg.REGISTRY
        )
        self.assertEqual(auth.registry_fingerprint(prose_edited), original)

    def test_changing_behaviour_does_move_it(self):
        """The other half — otherwise it is a constant, not a fingerprint."""
        original = auth.registry_fingerprint()
        for field, value in (("position", 9999), ("policy", reg.POLICY_PROTECTED),
                             ("default_on", False), ("counterfactual", reg.CF_LOCKED),
                             ("cls", reg.CLASS_LOCKED)):
            with self.subTest(field=field):
                mutated = list(reg.REGISTRY)
                mutated[0] = dataclasses.replace(mutated[0], **{field: value})
                self.assertNotEqual(
                    auth.registry_fingerprint(tuple(mutated)), original,
                    f"Changing {field} must move the behavioural fingerprint.")


class SelectionFingerprintTests(unittest.TestCase):

    def test_click_order_does_not_matter(self):
        self.assertEqual(
            auth.selection_fingerprint([33, 40]),
            auth.selection_fingerprint([40, 33]),
            "{33,40} and {40,33} are the same experiment.")

    def test_duplicates_do_not_matter(self):
        self.assertEqual(
            auth.selection_fingerprint([33, 40, 33]),
            auth.selection_fingerprint([33, 40]))

    def test_different_selections_never_collide(self):
        """V11 — checked across every adjacent pair, not one example."""
        ids = [i.id for i in reg.REGISTRY]
        seen = {}
        for n in range(len(ids) + 1):
            fp = auth.selection_fingerprint(ids[:n])
            self.assertNotIn(
                fp, seen,
                f"selection of {n} ids collides with {seen.get(fp)}")
            seen[fp] = n
        self.assertNotEqual(auth.selection_fingerprint([]),
                            auth.selection_fingerprint([1]))


class ThreeStateResolutionTests(unittest.TestCase):

    def test_no_override_means_canonical_default(self):
        snap = auth.resolve({}, safety_parked_probe=_not_parked)
        item = snap.state(35)          # word limit, canonically on
        self.assertIsNone(item.operator_override)
        self.assertEqual(item.reason, auth.REASON_CANONICAL_DEFAULT)
        self.assertEqual(item.effective, item.canonical_default)

    def test_operator_override_applies_to_switchable(self):
        snap = auth.resolve({35: False}, safety_parked_probe=_not_parked)
        item = snap.state(35)
        self.assertEqual(item.operator_override, False)
        self.assertFalse(item.effective)
        self.assertEqual(item.reason, auth.REASON_OPERATOR_OVERRIDE)
        self.assertFalse(snap.is_selected(35))

    def test_protected_authority_ignores_an_override(self):
        """V7 — second line of defence behind API validation.

        Persisted state could be edited by hand, or predate a policy
        change. Resolution must refuse it rather than quietly obey.
        """
        for pid in (i.id for i in reg.protected()):
            with self.subTest(id=pid):
                snap = auth.resolve({pid: False}, safety_parked_probe=_not_parked)
                item = snap.state(pid)
                self.assertEqual(item.effective, item.canonical_default)
                self.assertIn(item.reason,
                              (auth.REASON_PROTECTED, auth.REASON_SYSTEM_PARKED))

    def test_absent_override_is_not_the_same_as_an_override_to_default(self):
        """V9 — reset deletes the row, it does not write the default in."""
        reset = auth.resolve({}, safety_parked_probe=_not_parked).state(35)
        pinned = auth.resolve({35: True}, safety_parked_probe=_not_parked).state(35)
        self.assertEqual(reset.effective, pinned.effective)
        self.assertIsNone(reset.operator_override)
        self.assertIsNotNone(pinned.operator_override)
        self.assertNotEqual(reset.reason, pinned.reason)


class SystemStateTests(unittest.TestCase):
    """Canonical ON, effective PARKED — the row that motivated the split."""

    def test_safety_protocol_is_parked_by_default(self):
        snap = auth.resolve({}, safety_parked_probe=_parked)
        item = snap.state(2)
        self.assertTrue(item.canonical_default)
        self.assertFalse(item.effective)
        self.assertEqual(item.reason, auth.REASON_SYSTEM_PARKED)
        self.assertTrue(item.differs_from_canonical,
                        "The panel must explain this row.")

    def test_unparking_restores_the_canonical_default(self):
        item = auth.resolve({}, safety_parked_probe=_not_parked).state(2)
        self.assertTrue(item.effective)
        self.assertEqual(item.reason, auth.REASON_PROTECTED)

    def test_system_state_outranks_an_operator_override(self):
        item = auth.resolve({2: True}, safety_parked_probe=_parked).state(2)
        self.assertFalse(item.effective)
        self.assertEqual(item.reason, auth.REASON_SYSTEM_PARKED)


class SnapshotTests(unittest.TestCase):

    def test_snapshot_is_immutable(self):
        snap = auth.resolve({}, safety_parked_probe=_not_parked)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snap.revision = 99                       # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snap.states[0].effective = False         # type: ignore[misc]

    def test_covers_every_registered_authority(self):
        snap = auth.resolve({}, safety_parked_probe=_not_parked)
        self.assertEqual(len(snap.states), len(reg.REGISTRY))
        self.assertEqual(snap.selected | snap.excluded,
                         frozenset(i.id for i in reg.REGISTRY))
        self.assertFalse(snap.selected & snap.excluded)

    def test_states_are_in_canonical_pipeline_order(self):
        snap = auth.resolve({}, safety_parked_probe=_not_parked)
        positions = [s.position for s in snap.states]
        self.assertEqual(positions, sorted(positions))

    def test_trace_identity_carries_all_three_identifiers(self):
        snap = auth.resolve({35: False}, revision=7,
                            safety_parked_probe=_not_parked)
        identity = snap.trace_identity()
        self.assertEqual(identity["revision"], 7)
        self.assertEqual(identity["registry_fingerprint"],
                         auth.registry_fingerprint())
        self.assertEqual(identity["selection_fingerprint"],
                         auth.selection_fingerprint(snap.selected))
        self.assertIn(35, identity["excluded"])

    def test_selection_fingerprint_tracks_the_effective_set(self):
        a = auth.resolve({}, safety_parked_probe=_not_parked)
        b = auth.resolve({35: False}, safety_parked_probe=_not_parked)
        self.assertNotEqual(a.selection_fingerprint, b.selection_fingerprint)

    def test_revision_alone_does_not_change_the_selection_fingerprint(self):
        """They answer different questions and must vary independently."""
        a = auth.resolve({}, revision=1, safety_parked_probe=_not_parked)
        b = auth.resolve({}, revision=2, safety_parked_probe=_not_parked)
        self.assertEqual(a.selection_fingerprint, b.selection_fingerprint)
        self.assertNotEqual(a.revision, b.revision)


class AllSwitchableOffTests(unittest.TestCase):

    def test_preset_covers_exactly_the_switchable_population(self):
        overrides = auth.all_switchable_off_overrides()
        self.assertEqual(set(overrides), {i.id for i in reg.switchable()})
        self.assertTrue(all(v is False for v in overrides.values()))

    def test_preset_excludes_every_switchable_authority(self):
        snap = auth.resolve(auth.all_switchable_off_overrides(),
                            safety_parked_probe=_not_parked)
        for item in reg.switchable():
            with self.subTest(id=item.id):
                self.assertFalse(snap.is_selected(item.id))

    def test_preset_leaves_protected_authorities_alone(self):
        snap = auth.resolve(auth.all_switchable_off_overrides(),
                            safety_parked_probe=_not_parked)
        for item in reg.protected():
            with self.subTest(id=item.id):
                self.assertEqual(snap.state(item.id).effective,
                                 item.default_on)

    def test_the_label_is_currently_truthful(self):
        """It is only honest while no PENDING_SEAM authority exists.

        A pending seam would stay RUNNING through this preset, so the
        button would claim something the code cannot deliver.
        """
        self.assertEqual(
            [i.id for i in reg.pending_seam()], [],
            "All Switchable Off cannot be described without qualification "
            "while a PENDING_SEAM authority remains.")


if __name__ == "__main__":
    unittest.main()
