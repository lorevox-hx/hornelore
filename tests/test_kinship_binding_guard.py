"""WO-LORI-ARCHIVE-TO-MEMOIR-02 Phase 3 — kinship binding refusal.

THE DEFECT THESE GUARD AGAINST, in the narrator's own words.

Mable Hudson, turn 2110 (`turnrow:2111` in turn_extraction_results,
2026-09-01T02:04:16): "Otis died in 2005. Heart attack at sixty-three."
The extractor proposed `parents.firstName="Otis"` at confidence 0.9,
with parents.birthDate / deathDate / notableLifeEvents in the same
`parents_0` group. Otis was her HUSBAND -- her stored profile already
held `spouses=[Otis Bell]` and `parents=[Clarence Hudson, Ida Hudson]`,
written 22 hours earlier. Tomasita Reyes and Domingo produced the same
shape eight minutes later.

The fixtures below are the REAL sentences, not paraphrases, because the
property that matters -- containing no relationship word at all -- is
exactly what a paraphrase would quietly repair.

WHY NOT THE LIVE DB. These tests build the profile shape in memory and
patch `get_profile`, so they run in a clone. A test that read
/mnt/c/hornelore_data would skip everywhere it mattered.
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

# ── the real narrator statements ───────────────────────────────────────
MABLE = ("Otis died in 2005. Heart attack at sixty-three. The kids were "
         "grown — Charlene was in Atlanta with her family, Bernard in "
         "Detroit still — and I sat in the house on Plymouth Road for a "
         "year by myself and I thought about whether this was where I was "
         "going to die.")
TOMASITA = ("I am eighty-five years old. Domingo passed in 2008. The "
            "tortillería I ran for two more years after that and then I "
            "closed it in 2010.")
# Mable's own words establishing the marriage, from cohort turn 1856 --
# a DIFFERENT conversation, which is why the extractor had no local cue.
MABLE_MARRIAGE = ("A few months before I met Otis Bell. He was from "
                  "Mississippi originally, but he had been in Detroit "
                  "since '54. We were married in 1965.")

MABLE_PROFILE = {"profile_json": {
    "spouses": [{"firstName": "Otis", "lastName": "Bell", "yearMarried": 1965}],
    "parents": [{"firstName": "Clarence", "lastName": "Hudson"},
                {"firstName": "Ida", "lastName": "Hudson"}],
}}


def item(field_path, value, conf=0.9, group="parents_0"):
    return {"fieldPath": field_path, "value": value, "confidence": conf,
            "writeMode": "candidate_only", "repeatableGroup": group}


class _GuardCase(unittest.TestCase):
    def guard(self, items, answer, profile=None, person_id="mable"):
        target = "api.routers.extract.get_profile"
        with mock.patch.dict(sys.modules):
            with mock.patch("api.db.get_profile",
                            return_value=profile) as _:
                return EX._apply_kinship_binding_guard(
                    items, answer=answer, person_id=person_id)


class RuleOneUnstatedRelationship(_GuardCase):
    """A kinship path written from words carrying no anchor for that role."""

    def test_the_sentence_contains_no_relationship_word_at_all(self):
        """The premise of Rule 1, measured rather than asserted. If this
        ever fails, the fixture has been edited into a different case and
        every test below is testing something else."""
        for pat in (EX._PARENT_ANCHORS, EX._SIBLING_CONFLICT_CUES,
                    EX._KINSHIP_ROLE_ANCHORS["family.spouse"]):
            self.assertIsNone(pat.search(MABLE),
                              f"{pat.pattern!r} unexpectedly matches MABLE")

    def test_otis_is_downgraded_not_dropped(self):
        out = self.guard([item("parents.firstName", "Otis")], MABLE,
                         profile=None)
        self.assertEqual(1, len(out), "the narrator's words are not discarded")
        self.assertEqual("suggest_only", out[0]["writeMode"])
        self.assertTrue(out[0]["needs_confirmation"])
        self.assertEqual("relationship_unstated", out[0]["confirmation_reason"])

    def test_confidence_is_capped_because_the_model_is_not_the_authority(self):
        out = self.guard([item("parents.firstName", "Otis", conf=0.9)],
                         MABLE, profile=None)
        self.assertLessEqual(out[0]["confidence"], 0.5)

    def test_domingo_behaves_identically(self):
        out = self.guard([item("parents.firstName", "Domingo")], TOMASITA,
                         profile=None)
        self.assertEqual("relationship_unstated", out[0]["confirmation_reason"])

    def test_a_stated_relationship_passes_through_untouched(self):
        """The guard must not tax narrators who said the word."""
        answer = "My father Harold worked at Firestone until he retired."
        before = item("parents.firstName", "Harold")
        out = self.guard([dict(before)], answer, profile=None)
        self.assertEqual([before], out)

    def test_a_stated_marriage_passes_through(self):
        out = self.guard(
            [item("family.spouse.firstName", "Otis", group="spouse_0")],
            MABLE_MARRIAGE, profile=None)
        self.assertEqual("candidate_only", out[0]["writeMode"])
        self.assertNotIn("needs_confirmation", out[0])

    def test_non_kinship_fields_are_never_touched(self):
        keep = [{"fieldPath": "residence.place", "value": "Plymouth Road",
                 "confidence": 0.9, "writeMode": "candidate_only"},
                {"fieldPath": "personal.fullName", "value": "Mable",
                 "confidence": 0.9, "writeMode": "candidate_only"}]
        self.assertEqual(keep, self.guard([dict(k) for k in keep], MABLE,
                                          profile=None))


class RuleTwoKnownStructure(_GuardCase):
    """The narrator's stored truth gets a vote."""

    def test_a_known_spouse_cannot_enter_parents(self):
        out = self.guard([item("parents.firstName", "Otis")], MABLE,
                         profile=MABLE_PROFILE)
        self.assertEqual([], out, "Otis is her husband; parents_0 is refused")

    def test_the_whole_contaminated_group_goes_not_just_the_name(self):
        """parents_0.deathDate is exactly as mis-filed as parents_0.firstName
        once the group's subject is wrong. This is the shape the live row
        actually had: four fields, one wrong subject."""
        out = self.guard([
            item("parents.firstName", "Otis"),
            item("parents.birthDate", "1922", conf=0.7),
            item("parents.deathDate", "2005"),
            item("parents.notableLifeEvents", "died 2005", conf=0.8),
        ], MABLE, profile=MABLE_PROFILE)
        self.assertEqual([], out)

    def test_a_different_group_in_the_same_turn_survives(self):
        """Refusal is scoped to the contaminated group. Charlene and Bernard
        are real children and must not be collateral."""
        out = self.guard([
            item("parents.firstName", "Otis"),
            item("family.children.firstName", "Charlene", group="children_0"),
        ], MABLE, profile=MABLE_PROFILE)
        self.assertEqual(1, len(out))
        self.assertEqual("Charlene", out[0]["value"])

    def test_a_name_contradicting_a_known_parent_is_downgraded_not_refused(self):
        """A narrator correcting their own parent's name is legitimate and
        must not be silenced by their stale profile. It goes to the operator
        with the collision named -- downgrade, never drop."""
        answer = "My father was Clarence, though everyone called him Sonny."
        out = self.guard([item("parents.firstName", "Sonny")], answer,
                         profile=MABLE_PROFILE)
        self.assertEqual(1, len(out))
        self.assertEqual("contradicts_known_parents",
                         out[0]["confirmation_reason"])

    def test_a_known_parent_named_with_an_anchor_passes_clean(self):
        answer = "My father Clarence worked at the plant for thirty years."
        out = self.guard([item("parents.firstName", "Clarence")], answer,
                         profile=MABLE_PROFILE)
        self.assertEqual("candidate_only", out[0]["writeMode"])


class FailureIsolation(_GuardCase):
    """A guard that can raise into extraction is worse than no guard."""

    def test_a_profile_lookup_that_raises_leaves_rule_one_working(self):
        with mock.patch("api.db.get_profile", side_effect=RuntimeError("db")):
            out = EX._apply_kinship_binding_guard(
                [item("parents.firstName", "Otis")], answer=MABLE,
                person_id="mable")
        self.assertEqual(1, len(out), "degrades to Rule 1, does not explode")
        self.assertEqual("relationship_unstated", out[0]["confirmation_reason"])

    def test_no_person_id_still_applies_rule_one(self):
        out = EX._apply_kinship_binding_guard(
            [item("parents.firstName", "Otis")], answer=MABLE, person_id=None)
        self.assertTrue(out[0]["needs_confirmation"])

    def test_empty_inputs_are_returned_unchanged(self):
        self.assertEqual([], EX._apply_kinship_binding_guard([], answer=MABLE))

    def test_it_is_wired_into_both_extraction_paths(self):
        """One engine passing the bar and the other not is how a fallback
        becomes a bypass."""
        src = (ROOT / "server" / "code" / "api" / "routers"
               / "extract.py").read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.split("\n")
                         if not ln.lstrip().startswith("#"))
        self.assertIn("_apply_kinship_binding_guard(\n            llm_items",
                      code)
        self.assertIn("_apply_kinship_binding_guard(\n            rules_items",
                      code)


class RoleResolution(unittest.TestCase):
    def test_longest_prefix_wins(self):
        self.assertEqual("family.children",
                         EX._kinship_role_of("family.children.firstName"))
        self.assertEqual("family.spouse",
                         EX._kinship_role_of("family.spouse.firstName"))
        self.assertEqual("parents", EX._kinship_role_of("parents.birthDate"))

    def test_non_kinship_paths_resolve_to_none(self):
        for fp in ("personal.fullName", "residence.place", "family.marriageNotes",
                   "education.school", ""):
            self.assertIsNone(EX._kinship_role_of(fp), fp)

    def test_every_role_has_both_an_anchor_and_a_profile_key(self):
        """Half-adding a role is how a kinship path silently escapes the
        guard: an anchor with no profile key skips Rule 2, and a profile
        key with no anchor skips Rule 1."""
        self.assertEqual(set(EX._KINSHIP_ROLE_ANCHORS),
                         set(EX._KINSHIP_PROFILE_KEYS))


if __name__ == "__main__":
    unittest.main()
