"""Phase 5B item 1 — current vs former spouse, measured before changing it.

    PYTHONPATH=server/code .venv/bin/python -m unittest \\
        tests.test_spouse_state_characterization

`WO-LORI-ARCHIVE-TO-MEMOIR-02` Phase 5B.

── CHARACTERIZATION FIRST, THEN THE REGRESSION IT BECAME ─────────────

Every test here began as a MEASUREMENT of the shipped behaviour, taken
before any Phase 5B code existed. The measurement is what decided the
fix, and eight of these tests failed the moment it landed — deliberately,
each carrying its own "Phase 5B has landed; update this" message. They
now assert the corrected behaviour.

Keeping that history matters: a suite written straight to the desired
behaviour would have been red for the whole phase and quietly ignored.

── WHAT WAS MEASURED, 2026-09-05 ─────────────────────────────────────

The predicted hazard was that the spouse cue regex matches `wife` inside
`ex-wife`. **The reality was broader: the spouse lane performed no
relationship-state check at all.** Whatever destination the extractor
proposed was accepted verbatim, so:

  * `My ex-wife Susan` proposed as `family.spouse.firstName` made Susan
    the CURRENT spouse, unquarantined;
  * `ex-husband`, `former wife` and `previous wife` behaved the same;
  * and the fully CROSSED assignment survived — the current wife filed
    as a prior partner and the ex-wife as the current spouse.

`family.priorPartners.*` already accepted values, so the destination was
never the missing piece. The missing piece was any deterministic binding
of *current* versus *former* from the narrator's own words.

That is why the fix is not "a negative lookbehind on `ex-`". A lookbehind
would have stopped one spelling of one direction, left the meaning
nowhere honest to go, and not touched the crossed case at all.

── WHAT LANDED ───────────────────────────────────────────────────────

`services/relationship_interpreter` reads the narrator's phrase into
group / relation / state / qualifier / source_phrase, and
`_normalize_relationship_lane` moves a proposal when the narrator's
wording names a different lane — but only when the same subfield exists
there. When it does not, the proposal is left for the review lane rather
than forced into a field that was never designed for it.

"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "server" / "code")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.routers import extract as EX  # noqa: E402

MIXED = "My wife Mary is a nurse. My ex-wife Susan was a teacher."


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


def run(answer, items, profile=None):
    """Drive the SHIPPED extraction path with fixed model output.

    The model is not the property under test — binding is — so its
    output is held constant, exactly as `TheJimCase` does.
    """
    req = EX.ExtractFieldsRequest(person_id="N", answer=answer,
                                  current_section="family_life")
    with mock.patch("api.db.get_profile", return_value=profile), \
         mock.patch.object(EX, "_extract_via_llm",
                           return_value=(list(items), "[stub]")):
        return EX.run_field_extraction(req)


def paths(resp):
    return [(i.fieldPath, i.value) for i in resp.items]


class CurrentSpouseWorks(unittest.TestCase):
    """The positive control. Any fix must keep this passing."""

    def test_a_current_wife_reaches_the_spouse_field(self):
        r = run("My wife Mary worked as a teacher.",
                [item("family.spouse.firstName", "Mary")])
        self.assertEqual([("family.spouse.firstName", "Mary")], paths(r))

    def test_a_current_husband_reaches_the_spouse_field(self):
        r = run("My husband Frank drove a bus.",
                [item("family.spouse.firstName", "Frank")])
        self.assertEqual([("family.spouse.firstName", "Frank")], paths(r))

    def test_the_prior_partner_destination_accepts_values(self):
        """`family.priorPartners.*` is not the missing piece."""
        r = run("My ex-wife Susan worked as a teacher.",
                [item("family.priorPartners.firstName", "Susan")])
        self.assertEqual([("family.priorPartners.firstName", "Susan")], paths(r))


class FormerSpouseReachesThePriorPartnerLane(unittest.TestCase):
    """DESIRED BEHAVIOUR, landed 2026-09-05.

    These were `FormerSpouseIsNotDistinguished` and asserted the defect:
    every former-spouse wording reached the CURRENT spouse field. Each
    now asserts the correction, and each failed on the way here — which
    is what the characterization was for.
    """

    def test_ex_wife_reaches_the_prior_partner_lane(self):
        r = run("My ex-wife Susan worked as a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual([("family.priorPartners.firstName", "Susan")], paths(r))

    def test_ex_husband_reaches_the_prior_partner_lane(self):
        r = run("My ex-husband Frank drove a bus.",
                [item("family.spouse.firstName", "Frank")])
        self.assertEqual([("family.priorPartners.firstName", "Frank")], paths(r))

    def test_former_wife_reaches_the_prior_partner_lane(self):
        """Unhyphenated wording — a lookbehind on `ex-` would miss it."""
        r = run("My former wife Susan worked as a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual([("family.priorPartners.firstName", "Susan")], paths(r))

    def test_previous_wife_reaches_the_prior_partner_lane(self):
        r = run("My previous wife Susan worked as a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual([("family.priorPartners.firstName", "Susan")], paths(r))

    def test_ex_wife_is_never_stored_as_a_canonical_relation(self):
        """`ex-wife` is a phrase. The relation is `wife`.

        The lane carries the former state; storing `ex-wife` as the
        relation would collapse three separate facts into one string.
        """
        from api.services.relationship_interpreter import interpret_phrase
        reading = interpret_phrase("my ex-wife Susan")
        self.assertEqual(reading.relation, "wife")
        self.assertEqual(reading.state, "former")
        self.assertEqual(reading.source_phrase, "ex-wife")


class TheCrossedAssignmentIsCorrected(unittest.TestCase):
    """The decisive Phase 5B regression.

    Was `TheCrossedAssignmentSurvives`. The narrator's wording now
    decides the lane, so a model that swaps the destinations is
    corrected rather than obeyed.
    """

    def test_both_named_as_current_spouse_are_separated(self):
        r = run(MIXED, [item("family.spouse.firstName", "Mary"),
                        item("family.spouse.firstName", "Susan")])
        got = paths(r)
        self.assertIn(("family.spouse.firstName", "Mary"), got)
        self.assertIn(("family.priorPartners.firstName", "Susan"), got)

    def test_the_correct_separation_is_left_alone(self):
        """Correct input must not be 'corrected' into something else."""
        r = run(MIXED, [item("family.spouse.firstName", "Mary"),
                        item("family.priorPartners.firstName", "Susan")])
        got = paths(r)
        self.assertIn(("family.spouse.firstName", "Mary"), got)
        self.assertIn(("family.priorPartners.firstName", "Susan"), got)

    def test_the_FULLY_CROSSED_assignment_is_put_right(self):
        """The measurement that decided Phase 5B's shape.

        Mary proposed as prior partner, Susan as current spouse. Both
        are corrected from the narrator's own words.
        """
        r = run(MIXED, [item("family.priorPartners.firstName", "Mary"),
                        item("family.spouse.firstName", "Susan")])
        got = paths(r)
        self.assertIn(("family.spouse.firstName", "Mary"), got)
        self.assertIn(("family.priorPartners.firstName", "Susan"), got)
        self.assertNotIn(("family.priorPartners.firstName", "Mary"), got)
        self.assertNotIn(("family.spouse.firstName", "Susan"), got)

    def test_the_husband_equivalent(self):
        mixed = ("My husband Frank drives a bus. "
                 "My ex-husband Danny was a welder.")
        r = run(mixed, [item("family.priorPartners.firstName", "Frank"),
                        item("family.spouse.firstName", "Danny")])
        got = paths(r)
        self.assertIn(("family.spouse.firstName", "Frank"), got)
        self.assertIn(("family.priorPartners.firstName", "Danny"), got)


class RelationValuesAreCanonicalizedInProduction(unittest.TestCase):
    """The relation VALUE, not just the lane — through the real path.

    ── WHY THIS CLASS REPLACES A HELPER ASSERTION, 2026-09-05 ────────

    `test_ex_wife_is_never_stored_as_a_canonical_relation` called
    `interpret_phrase()` and checked the helper returned `wife`. It did.
    **Production stored `ex-wife` anyway** — the lane pass moved the
    field path and never touched the value. The test's name described a
    property nothing had verified.

    Every case here sends a `*.relation` item through
    `run_field_extraction` and reads what actually lands.
    """

    def test_ex_wife_relation_is_stored_as_wife(self):
        r = run("My ex-wife Susan was a teacher.",
                [item("family.spouse.relation", "ex-wife")])
        self.assertEqual([("family.priorPartners.relation", "wife")], paths(r))

    def test_former_wife_relation_is_stored_as_wife(self):
        r = run("My former wife Susan was a teacher.",
                [item("family.spouse.relation", "former wife")])
        self.assertEqual([("family.priorPartners.relation", "wife")], paths(r))

    def test_previous_husband_relation_is_stored_as_husband(self):
        r = run("My previous husband Frank drove a bus.",
                [item("family.spouse.relation", "previous husband")])
        self.assertEqual([("family.priorPartners.relation", "husband")], paths(r))

    def test_current_relations_are_left_alone(self):
        """Canonical input must not be 'canonicalized' into something else."""
        for said, rel in (("My wife Mary is a nurse.", "wife"),
                          ("My partner Sam is a nurse.", "partner")):
            with self.subTest(relation=rel):
                r = run(said, [item("family.spouse.relation", rel)])
                self.assertEqual([("family.spouse.relation", rel)], paths(r))

    def test_no_narrator_phrase_survives_as_a_canonical_relation(self):
        """The contract, stated as a property rather than a case list."""
        for phrase in ("ex-wife", "ex-husband", "former wife",
                       "previous wife", "ex-partner"):
            with self.subTest(phrase=phrase):
                r = run(f"My {phrase} Susan was a teacher.",
                        [item("family.spouse.relation", phrase)])
                for _p, v in paths(r):
                    self.assertNotEqual(
                        v, phrase,
                        f"{phrase!r} was stored as a canonical relation")


class UnsupportedSubfieldsGoToReview(unittest.TestCase):
    """The promise that was NOT secured, now enforced.

    ── MEASURED, 2026-09-05 ─────────────────────────────────────────

    The claim was that an ex-wife's occupation proposed as
    `family.spouse.occupation` would decline to the guard, because
    `family.priorPartners.occupation` does not exist. Half of that was
    true — the lane pass refused to invent the field. **The other half
    was not: the item stayed, and became the CURRENT spouse's
    occupation.** `group_pattern("family.spouse")` contains bare `wife`,
    `-` is a word boundary, so the guard read `ex-wife` as current-spouse
    support.

    The refusal is now made where the lane is known, rather than
    delegated to a guard answering a different question.
    """

    EXWIFE = "My ex-wife Susan was a teacher for thirty years."
    WIFE = "My wife Mary was a teacher for thirty years."

    def test_an_ex_wife_occupation_does_not_become_the_current_spouses(self):
        r = run(self.EXWIFE, [item("family.spouse.occupation", "teacher")])
        self.assertNotIn(("family.spouse.occupation", "teacher"), paths(r))

    def test_it_is_not_invented_on_the_prior_partner_lane_either(self):
        """No destination is manufactured to make the value fit."""
        r = run(self.EXWIFE, [item("family.spouse.occupation", "teacher")])
        self.assertNotIn(("family.priorPartners.occupation", "teacher"),
                         paths(r))

    def test_it_receives_a_review_disposition_naming_what_is_missing(self):
        """Meaning that has nowhere to go must not simply vanish."""
        r = run(self.EXWIFE, [item("family.spouse.occupation", "teacher")])
        entries = [c for c in (r.clarification_required or [])
                   if c.get("reason") == "relationship_state_has_no_destination"]
        self.assertTrue(entries, "the meaning disappeared without a record")
        self.assertEqual(entries[0].get("would_need"),
                         "family.priorPartners.occupation")
        self.assertEqual(entries[0].get("narrator_phrase"), "ex-wife")

    def test_the_CURRENT_wifes_occupation_still_survives(self):
        """Positive control. A pass that drops everything proves nothing."""
        r = run(self.WIFE, [item("family.spouse.occupation", "teacher")])
        self.assertEqual([("family.spouse.occupation", "teacher")], paths(r))


class LateSpouseIsNotAFormerSpouse(unittest.TestCase):
    """`late wife` means widowed, not divorced.

    ── AN ALIAS I ADDED WITHOUT MEASURING, REMOVED 2026-09-05 ───────

    The first Phase 5B table grouped `late wife|late husband` with
    `former|previous|first`. It reads as a tidy alternation and it is a
    semantic collapse — in a phase that exists to prevent exactly that.

      "my ex-wife Susan"   — the marriage ENDED; she is living
      "my late wife Susan" — the marriage did not end that way; she died

    Filing a widower's wife under `priorPartners`, and downstream under
    `former_marriage`, tells the family the marriage was dissolved. For a
    memoir that is the system contradicting the narrator about the most
    significant relationship of their life.

    `ex`, `former` and `previous` were measured against the shipped path.
    `late` was not — it was added by pattern-matching the shape of the
    other words. It stays out until its destination is designed.
    """

    def test_a_late_wife_remains_on_the_CURRENT_lane(self):
        r = run("My late wife Susan was a teacher.",
                [item("family.spouse.firstName", "Susan")])
        self.assertEqual([("family.spouse.firstName", "Susan")], paths(r))

    def test_a_late_husband_remains_on_the_CURRENT_lane(self):
        r = run("My late husband Frank drove a bus.",
                [item("family.spouse.firstName", "Frank")])
        self.assertEqual([("family.spouse.firstName", "Frank")], paths(r))

    def test_the_interpreter_does_not_read_late_as_former(self):
        from api.services.relationship_interpreter import interpret_phrase
        reading = interpret_phrase("my late wife Susan")
        self.assertEqual(reading.state, "current")
        self.assertNotEqual(reading.group, "family.priorPartners")

    def test_ex_is_still_read_as_former(self):
        """The discriminating control — `late` out, `ex` still in."""
        from api.services.relationship_interpreter import interpret_phrase
        self.assertEqual(interpret_phrase("my ex-wife Susan").state, "former")

    def test_the_omission_is_recorded_rather_than_silent(self):
        """So a future session re-adding `late` has to read the reason."""
        src = (ROOT / "server" / "code" / "api" / "services"
               / "relationship_interpreter.py").read_text(encoding="utf-8")
        self.assertIn("late wife` IS NOT IN THIS TABLE", src)


class TheGuardHandlesAnEmptyItemList(unittest.TestCase):
    """A latent crash the lane pass made reachable.

    `_apply_kinship_binding_guard` returned TWO values on three early
    paths while its call site unpacks three, so each raised
    `ValueError: not enough values to unpack` and took the endpoint down.
    Two of the three are the `HORNELORE_CLAIMS_VALIDATORS` branches —
    **turning that flag off crashed extraction instead of relaxing it.**
    """

    def test_removing_every_item_does_not_crash_extraction(self):
        r = run("My ex-wife Susan was a teacher for thirty years.",
                [item("family.spouse.occupation", "teacher")])
        self.assertEqual([], paths(r))

    def test_extraction_survives_with_the_validators_flag_off(self):
        with mock.patch("api.flags.claims_validators_enabled",
                        return_value=False):
            r = run("My wife Mary is a nurse.",
                    [item("family.spouse.firstName", "Mary")])
        self.assertEqual([("family.spouse.firstName", "Mary")], paths(r))


class PartnerBindsWithoutManufacturingMarriage(unittest.TestCase):
    """CURRENT BEHAVIOUR — and it contradicts the expectation.

    ── MEASURED 2026-09-05, AND IT WAS A SURPRISE ────────────────────

    The review expected `partner` to be *"probably test-only closure"* —
    the schema treats `family.spouse.*` as spouse-or-partner, the relation
    field accepts `partner`, the role mapper knows it, and the QA bank
    carries both partner cases. All true, and all upstream of the guard.

    At the production boundary **`partner` is quarantined
    `relationship_unstated`, exactly like `daddy`.** Sam does not reach
    the spouse lane, and no marriage is manufactured either — because
    nothing survives at all.

    So this is a THIRD instance of the same missing-vocabulary shape, not
    a coverage gap. It also means the schema/QA evidence the review cited
    is real but does not reach the binding decision, which is precisely
    the "cite the line that READS the value" rule: `family.spouse.relation`
    accepting `partner` says nothing about whether the guard binds it.
    """

    def test_partner_now_binds(self):
        """DESIRED BEHAVIOUR. Was quarantined `relationship_unstated`."""
        r = run("My partner Sam and I have never married.",
                [item("family.spouse.firstName", "Sam")])
        self.assertEqual([("family.spouse.firstName", "Sam")], paths(r))

    def test_the_same_holds_without_the_marriage_disclaimer(self):
        r = run("My partner Sam is a nurse.",
                [item("family.spouse.firstName", "Sam")])
        self.assertEqual([("family.spouse.firstName", "Sam")], paths(r))

    def test_partner_stays_in_the_CURRENT_lane(self):
        """A partner is current. The ex-spouse work must not move them."""
        r = run("My partner Sam is a nurse.",
                [item("family.spouse.firstName", "Sam")])
        self.assertNotIn(("family.priorPartners.firstName", "Sam"), paths(r))

    def test_wife_binds_in_the_identical_sentence_shape(self):
        """The discriminating control. Only the relationship word differs."""
        r = run("My wife Mary is a nurse.",
                [item("family.spouse.firstName", "Mary")])
        self.assertEqual([("family.spouse.firstName", "Mary")], paths(r))

    def test_no_marriage_is_manufactured_for_a_partner(self):
        """Holds today only because nothing survives.

        Kept because it must STILL hold once `partner` binds — that is
        the regression the ex-spouse work is most likely to cause.
        """
        r = run("My partner Sam and I have never married.",
                [item("family.spouse.firstName", "Sam")])
        self.assertFalse([p for p, _v in paths(r) if "marriage" in p.lower()],
                         "a marriage field appeared for an unmarried partner")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
