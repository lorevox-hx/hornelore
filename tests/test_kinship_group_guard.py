"""Group-local kinship guard — the rebuild of the reverted add4753.

WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 (2026-09-04).

THE CASE, in the narrator's own words. Mable Hudson: "Otis died in 2005. Heart
attack at sixty-three." The extractor filed `parents.firstName=Otis` at 0.9
plus three more `parents_0` fields. Otis was her HUSBAND, and her stored
profile already said so. Tomasita/Domingo is the identical shape.

EVERY TEST HERE GOES THROUGH `run_field_extraction`. The first attempt shipped
19 passing tests that called the guard helper directly and handed it a
`repeatableGroup` key production does not have at that stage; the guard's
decisions were then overwritten downstream and reached no caller. Asserting on
the final `ExtractFieldsResponse` is the only way that failure is visible.

QUARANTINE, NOT DOWNGRADE. A lower-confidence `parents.firstName=Otis` is still
an approvable claim that Otis was Mable's father. The group leaves `items`
entirely and becomes one neutral review entry carrying every proposed field as
evidence.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "server" / "code") not in sys.path:
    sys.path.insert(0, str(ROOT / "server" / "code"))

from api.routers import extract as EX  # noqa: E402

MABLE = ("Otis died in 2005. Heart attack at sixty-three. The kids were grown "
         "— Charlene was in Atlanta with her family, Bernard in Detroit still.")
MABLE_PROFILE = {"profile_json": {
    "spouses": [{"firstName": "Otis", "lastName": "Bell"}],
    "parents": [{"firstName": "Clarence"}, {"firstName": "Ida"}]}}


def item(fp, value, conf=0.9):
    return {"fieldPath": fp, "value": value, "confidence": conf}


def run(answer, items, profile=None, target=None, force_rules=False):
    """Drive the SHIPPED pipeline. force_rules exercises the fallback tail."""
    req = EX.ExtractFieldsRequest(
        person_id="narrator-1", answer=answer,
        current_section="family_life", current_target_path=target)
    llm = ([], "[stub]") if force_rules else (list(items), "[stub]")
    ctx = [mock.patch("api.db.get_profile", return_value=profile),
           mock.patch.object(EX, "_extract_via_llm", return_value=llm)]
    if force_rules:
        ctx.append(mock.patch.object(EX, "_extract_via_rules",
                                     return_value=list(items)))
    with ctx[0], ctx[1]:
        if force_rules:
            with ctx[2]:
                return EX.run_field_extraction(req)
        return EX.run_field_extraction(req)


def paths(resp):
    return [i.fieldPath for i in resp.items]


def entries(resp):
    return [c for c in resp.clarification_required
            if c.get("kind") == "unbound_relationship"]


class TheOtisCase(unittest.TestCase):

    ITEMS = [item("parents.firstName", "Otis"),
             item("parents.birthDate", "1922", 0.7),
             item("parents.deathDate", "2005"),
             item("parents.notableLifeEvents", "died 2005", 0.8),
             item("residence.place", "Plymouth Road")]

    def test_no_executable_parents_item_survives(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertFalse([p for p in paths(r) if p.startswith("parents.")],
                         "a false parent fact reached the caller")

    def test_the_WHOLE_group_is_quarantined_not_just_firstName(self):
        """The reverted guard downgraded firstName and left the dates at full
        authority under the same doubt."""
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        e = entries(r)
        self.assertEqual(1, len(e))
        got = {(p["fieldPath"], p["value"]) for p in e[0]["proposed_items"]}
        self.assertEqual(
            {("parents.firstName", "Otis"), ("parents.birthDate", "1922"),
             ("parents.deathDate", "2005"),
             ("parents.notableLifeEvents", "died 2005")}, got)

    def test_the_safe_item_in_the_same_answer_survives(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        self.assertIn("residence.place", paths(r),
                      "no collateral loss — Plymouth Road is not in doubt")

    def test_both_reasons_are_recorded_in_precedence_order(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        e = entries(r)[0]
        self.assertEqual(["identity_conflict", "relationship_unstated"],
                         e["reasons"])
        self.assertEqual("identity_conflict", e["reason"])

    def test_the_entry_is_neutral_and_not_applied(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE)
        e = entries(r)[0]
        self.assertTrue(e["not_applied"])
        self.assertIn("relationship to you", e["label"])
        self.assertNotIn("father", e["label"].lower(),
                         "the label must not assert the error it is asking about")
        self.assertNotIn("fieldPath", e,
                         "a quarantine entry must carry NO executable fieldPath")
        self.assertEqual("parents.firstName", e["proposed_fieldPath"])

    def test_the_same_shape_on_the_rules_fallback_path(self):
        r = run(MABLE, self.ITEMS, MABLE_PROFILE, force_rules=True)
        self.assertEqual("rules_fallback", r.method)
        self.assertFalse([p for p in paths(r) if p.startswith("parents.")])
        self.assertEqual(1, len(entries(r)))


class LocalEvidenceDecides(unittest.TestCase):

    def test_stated_relationship_in_the_same_sentence_is_supported(self):
        r = run("My father Clarence Hudson worked at the plant for thirty years.",
                [item("parents.firstName", "Clarence"),
                 item("parents.lastName", "Hudson")], MABLE_PROFILE)
        self.assertEqual(["parents.firstName", "parents.lastName"], paths(r))
        self.assertEqual([], entries(r))

    def test_evidence_does_not_leak_across_sentences(self):
        """THE DEFECT THAT SANK THE FIRST ATTEMPT. One 'my father' anywhere
        licensed every parents.* item in the whole answer."""
        r = run("My father Clarence worked at the plant. Otis died in 2005.",
                [item("parents.firstName", "Clarence"),
                 item("parents.firstName", "Otis")], MABLE_PROFILE)
        vals = [i.value for i in r.items if i.fieldPath == "parents.firstName"]
        self.assertIn("Clarence", vals)
        self.assertNotIn("Otis", vals,
                         "a relationship stated about Clarence licensed Otis")
        self.assertEqual(1, len(entries(r)))

    def test_a_mixed_spouse_and_parent_answer_keeps_the_valid_group(self):
        r = run("My father Clarence worked at the plant. I married Otis in 1965.",
                [item("parents.firstName", "Clarence"),
                 item("family.spouse.firstName", "Otis")], MABLE_PROFILE)
        self.assertIn("parents.firstName", paths(r))
        self.assertIn("family.spouse.firstName", paths(r),
                      "'I married Otis' states the spouse relationship locally")
        self.assertEqual([], entries(r))

    def test_narrators_say_dad_without_my(self):
        """The first attempt reused conflict-cue regexes requiring the literal
        word 'my', so 'Dad was Kent Horne' read as unstated."""
        r = run("Dad was Kent Horne, born in Stanley.",
                [item("parents.firstName", "Kent")], None)
        self.assertEqual(["parents.firstName"], paths(r))


class NameEqualityAloneNeverRefuses(unittest.TestCase):

    JOHN_PROFILE = {"profile_json": {"spouses": [{"firstName": "John"}]}}

    def test_father_John_survives_a_spouse_named_John(self):
        """Explicit local wording outranks a same-first-name collision: a
        narrator who says 'my father John' has told us which John."""
        r = run("My father John was a machinist at the yard.",
                [item("parents.firstName", "John")], self.JOHN_PROFILE)
        self.assertEqual(["parents.firstName"], paths(r))
        self.assertEqual([], entries(r))

    def test_the_collision_only_adds_a_reason_to_an_already_unsupported_group(self):
        r = run("John died in 2005.", [item("parents.firstName", "John")],
                self.JOHN_PROFILE)
        e = entries(r)
        self.assertEqual(1, len(e))
        self.assertIn("identity_conflict", e[0]["reasons"])

    def test_an_unsupported_group_with_no_collision_is_only_unstated(self):
        r = run("Otis died in 2005.", [item("parents.firstName", "Otis")], None)
        self.assertEqual(["relationship_unstated"], entries(r)[0]["reasons"])

    def test_a_profile_outage_does_not_lose_the_local_check(self):
        with mock.patch("api.db.get_profile", side_effect=RuntimeError("db")):
            with mock.patch.object(EX, "_extract_via_llm",
                                   return_value=([item("parents.firstName", "Otis")],
                                                 "[stub]")):
                r = EX.run_field_extraction(EX.ExtractFieldsRequest(
                    person_id="n", answer="Otis died in 2005."))
        self.assertEqual([], [p for p in paths(r) if p.startswith("parents.")])
        self.assertEqual(["relationship_unstated"], entries(r)[0]["reasons"])


class ReasonsCompose(unittest.TestCase):
    """A kinship quarantine and a transcript-safety downgrade can both apply
    to one turn; neither may erase the other's explanation."""

    def test_transcript_safety_reasons_are_retained_alongside(self):
        req = EX.ExtractFieldsRequest(
            person_id="n",
            answer="My father Clarence worked there. Otis died in 2005.",
            transcript_source="whisper", transcript_confidence=0.42,
            confirmation_required=True)
        items = [item("parents.firstName", "Clarence"),
                 item("parents.firstName", "Otis")]
        with mock.patch("api.db.get_profile", return_value=MABLE_PROFILE), \
             mock.patch.object(EX, "_extract_via_llm", return_value=(items, "[s]")):
            r = EX.run_field_extraction(req)
        kinds = {c.get("kind") for c in r.clarification_required}
        self.assertIn("unbound_relationship", kinds)
        self.assertTrue(
            any(c.get("kind") != "unbound_relationship"
                for c in r.clarification_required),
            "the transcript-safety clarification for Clarence was lost")
        clarence = [i for i in r.items if i.value == "Clarence"][0]
        self.assertIn("low_confidence", clarence.confirmation_reasons)


if __name__ == "__main__":
    unittest.main()
