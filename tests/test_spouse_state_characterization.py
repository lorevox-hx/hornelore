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
