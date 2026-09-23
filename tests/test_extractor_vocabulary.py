"""The extractor may only propose where the form can render. WO-04.

WHY THIS TEST EXISTS
--------------------
`EXTRACTABLE_FIELDS` and the questionnaire's `SECTIONS` drifted into two
different vocabularies, and nothing noticed for months. The cost was
measured on 2026-09-20: of 30 queued suggestions, 20 pointed at
destinations the form does not define. One of them was accepted through
the review surface and became a value nobody could see or correct.

The rule this enforces: an extractor path must resolve to a field the
form renders, or be on a PINNED list of known-legacy exceptions.

WHY THE LEFT SIDE CANNOT GO STALE
---------------------------------
`questionnaire_schema.load_schema()` parses
`ui/js/bio-builder-questionnaire.js` — the file that actually renders
the form — and self-validates its parse. There is no second copy of the
vocabulary to maintain, so this check cannot be satisfied by updating a
list someone forgot about.

WHY THE EXCEPTION LIST IS PINNED AND NOT MERELY DOCUMENTED
----------------------------------------------------------
A test that only demands "a one-line disposition" lets the list grow
forever: each new drift costs one comment and passes. So the set is
frozen at its measured contents. Removing a path (by giving it a real
destination) is always allowed. ADDING one fails, and the failure says
so — a new exception is a schema decision and needs its own
authorisation, not a line in a dict.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "server" / "code"))
sys.path.insert(0, str(REPO / "tests"))

from fastapi_stub import install as _install_stub  # noqa: E402
_install_stub()

from api.services import questionnaire_schema as qs  # noqa: E402
from api.services.suggestion_review import split_destination  # noqa: E402


# ── the pinned exception set ─────────────────────────────────────────
#
# Measured 2026-09-20, AFTER WO-04 gave military, residence, travel,
# faith, marriage.marriagePlace and education.gradeLevel real homes: 77.
#
# SHRUNK 2026-09-23 (A2 + A3) to 49, by the two routes this test allows:
#   * 13 gained a destination — the catalog's decided aliases (D1a/D1b),
#     which `split_destination` now translates: family.children.* and
#     family.spouse.* to the form's children.* / spouse.*, and
#     grandparents.memorableStory to memorableStories;
#   * 15 left EXTRACTABLE_FIELDS — retired from extraction by D1d, D1e
#     and D3 (the *.notes buckets, community logistics, ageAtMarriage,
#     health.majorCondition and currentMedications).
#
# Each that remains is a real drift with a real disposition owed; none
# may be accepted into a biography, because the destination guard in
# `suggestion_review.accept` refuses an undefined destination regardless
# of this list. This set governs the TEST, not the runtime.
#
# THIS SET MAY SHRINK. IT MAY NOT GROW.
KNOWN_DRIFT_PINNED = frozenset({
    # No `community` section. `community.organization` collected Kent's
    # military unit; WO-04 gave that `military.unit` instead.
    "community.organization", "community.role",
    "community.significantEvent", "community.yearsActive",
    # No `cultural` section.
    "cultural.touchstoneMemory",
    # education extras the form does not have.
    "education.readingAbility", "education.training",
    # family.children extras with no form field under any spelling.
    "family.children.birthOrder", "family.children.preferredName",
    # No `grandchildren` or `priorPartners` sections.
    "family.grandchildren.firstName", "family.grandchildren.relation",
    "family.priorPartners.firstName", "family.priorPartners.lastName",
    "family.priorPartners.period", "family.priorPartners.relation",
    # family.spouse extras with no form field under any spelling.
    "family.spouse.education", "family.spouse.preferredName",
    "family.spouse.relation",
    # grandparent / parent / sibling extras the form does not have.
    "grandparents.childCount", "grandparents.deathDate",
    "grandparents.occupation",
    "parents.ageAtDeath", "parents.deathDate", "parents.education",
    "parents.ethnicBackground", "parents.placeOfDeath", "parents.preferredName",
    "siblings.birthDate", "siblings.birthPlace", "siblings.occupation",
    "siblings.preferredName",
    # No `greatGrandparents` section.
    "greatGrandparents.ancestry", "greatGrandparents.birthDate",
    "greatGrandparents.birthPlace", "greatGrandparents.firstName",
    "greatGrandparents.lastName", "greatGrandparents.maidenName",
    "greatGrandparents.memorableStories", "greatGrandparents.militaryBranch",
    "greatGrandparents.militaryEvent", "greatGrandparents.militaryUnit",
    "greatGrandparents.side",
    # health field names differ from the form's three.
    "health.cognitiveChange", "health.lifestyleChange", "health.milestone",
    # laterYears extras.
    "laterYears.dailyRoutine", "laterYears.desiredStory",
    "laterYears.significantEvent",
    # personal extras.
    "personal.nameStory",
})


def _extractable_paths():
    """Parse EXTRACTABLE_FIELDS keys out of extract.py.

    Read as TEXT rather than imported, because importing the router
    pulls the whole FastAPI app. The keys are one per line in a dict
    literal; the count is asserted below so a parse that quietly matched
    fewer cannot pass.
    """
    src = (REPO / "server" / "code" / "api" / "routers" / "extract.py").read_text(encoding="utf-8")
    start = src.index("EXTRACTABLE_FIELDS = {")
    body = src[start:src.index("\n}\n", start)]
    paths = re.findall(r'^\s*"([a-zA-Z][\w.]*)":\s*\{', body, re.M)
    return paths, body


class ExtractorVocabulary(unittest.TestCase):

    def setUp(self):
        self.paths, self.body = _extractable_paths()

    def test_the_parse_found_a_plausible_number_of_paths(self):
        """A regex that matched two lines would make every check below
        pass vacuously."""
        self.assertGreater(len(self.paths), 100,
                           "EXTRACTABLE_FIELDS parse looks broken")
        self.assertIn("personal.fullName", self.paths)

    def test_every_path_is_defined_or_pinned(self):
        """THE CHECK. A path the form cannot render, and that nobody has
        recorded as known drift, is a new invisible destination."""
        undefined = []
        for p in self.paths:
            sec, fld, _rep = split_destination(p)
            if not qs.is_defined(sec, fld):
                undefined.append(p)
        unpinned = sorted(set(undefined) - KNOWN_DRIFT_PINNED)
        self.assertEqual(
            unpinned, [],
            "These extractor paths have no questionnaire destination and are "
            "not on the pinned legacy list. A suggestion sent to one of them "
            "cannot be accepted (the destination guard refuses it), so it "
            "would sit in the queue unactionable forever. Give it a real "
            "destination, or get a new exception authorised:\n  "
            + "\n  ".join(unpinned))

    def test_the_pinned_set_may_shrink_but_not_grow(self):
        """Every pinned path must still BE drift. One that has gained a
        destination must be removed from the set — otherwise the list
        rots into a permanent excuse."""
        stale = []
        for p in sorted(KNOWN_DRIFT_PINNED):
            sec, fld, _rep = split_destination(p)
            if qs.is_defined(sec, fld):
                stale.append(p)
        self.assertEqual(
            stale, [],
            "These are pinned as known drift but the questionnaire now "
            "defines them. Remove them from KNOWN_DRIFT_PINNED — the set "
            "must shrink as destinations are built:\n  " + "\n  ".join(stale))

    def test_pinned_paths_all_still_exist_in_the_extractor(self):
        """A pinned path that was deleted from EXTRACTABLE_FIELDS should
        leave the list too, or the set quietly accumulates ghosts."""
        present = set(self.paths)
        ghosts = sorted(p for p in KNOWN_DRIFT_PINNED if p not in present)
        self.assertEqual(ghosts, [],
                         "pinned but no longer in EXTRACTABLE_FIELDS: " + str(ghosts))

    def test_repeatable_metadata_agrees_with_the_questionnaire(self):
        """Decision 5's refinement: canonical paths AND repeatability.

        `residence.*` carried `repeatable: "residences"` — plural, matching
        no section, so grouping could never work. `military.*` was half
        repeatable, sorting one posting's fields into two buckets. String
        presence alone would have missed both.
        """
        problems = []
        for p in self.paths:
            sec, fld, _rep = split_destination(p)
            if not qs.is_defined(sec, fld):
                continue
            m = re.search(r'"' + re.escape(p) + r'":\s*\{[^}]*?"repeatable":\s*"([^"]*)"',
                          self.body)
            declared = m.group(1) if m else None
            expected = sec if qs.is_repeatable(sec) else None
            if declared != expected:
                problems.append(f"{p}: extractor says {declared!r}, "
                                f"questionnaire wants {expected!r}")
        self.assertEqual(problems, [], "\n  ".join([""] + problems))

    def test_personal_notes_is_gone(self):
        """WO-04 decision 4. The path that produced the invisible
        acceptance is retired, not re-homed to a catch-all."""
        self.assertNotIn("personal.notes", self.paths)
        self.assertFalse(qs.is_defined("personal", "notes"),
                         "and no catch-all field was created to absorb it")

    def test_the_four_new_sections_are_reachable(self):
        """The other half: giving information a home is pointless if the
        extractor cannot propose to it."""
        for p in ("military.branch", "military.unit", "residence.place",
                  "travel.destination", "faith.denomination",
                  "marriage.marriagePlace", "education.gradeLevel"):
            self.assertIn(p, self.paths, p)
            sec, fld, _rep = split_destination(p)
            self.assertTrue(qs.is_defined(sec, fld), p)

    def test_the_retired_military_paths_are_gone(self):
        """`military.yearsOfService` collected "in Germany" — a place in a
        years field. Replaced by two date fields, and the old path must
        not linger."""
        for gone in ("military.yearsOfService", "military.deploymentLocation",
                     "military.significantEvent", "residence.period",
                     "residence.region", "family.marriageDate",
                     "family.marriagePlace"):
            self.assertNotIn(gone, self.paths, f"{gone} should have been replaced")


if __name__ == "__main__":
    unittest.main(verbosity=2)
