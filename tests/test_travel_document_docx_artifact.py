"""The Part III photo appendix — RETIRED 2026-08-06.

WHAT THIS FILE USED TO PROVE
----------------------------
21 tests built a real .docx and opened it to check the photo appendix:
that `approved`, `available` and `embedded` stayed three separate
numbers; that two stops with the same display name stayed two sections;
that a group whose every file was missing said so rather than printing
a bare heading; that the narrator's caption and an approved operator
caption both reached the page; and that the per-stop "· N approved
photos" line agreed with the appendix below it.

Every one of those was true, and several were hard-won.

WHY IT IS GONE
--------------
The product rule changed:

    The visible trip timeline is the editable source of truth.
    Export Travel Document produces a DOCX snapshot of that timeline.

Under that rule a photograph is printed once, under the day it is
placed on. An appendix would embed every image a SECOND time — a
duplication, and at roughly 5 MB a photograph, a doubling of the file.
So `build_trip_docx` no longer emits Part III, `trip_memoir_preview`
no longer builds `photo_appendix_projection`, and the subject of these
tests does not exist.

They are not deleted silently and they are not loosened to pass. The
claims that survive the change moved, and this file records where:

  * captions, and the rule that machine-written text is never allowed
    to look like something Chris wrote —
        test_travel_document_day_lane.MachineCaptionTest
  * a photograph appearing exactly once, embedded, in a real document —
        test_travel_document_day_lane.ExactlyOnceTest
  * a day-placed photograph not being labelled "Unplaced" —
        test_travel_document_day_lane.VisibleMeansExportedTest
  * a missing file being reported rather than silently dropped —
        test_travel_document_day_lane (the builder appends
        "(photograph could not be found on disk)")
  * hidden and soft-deleted photographs staying out —
        test_travel_document_day_lane.OnlyTheFourExclusionsTest

The one claim with NO successor is the appendix's own arithmetic —
`approved` vs `available` vs `embedded` as three distinct numbers.
There is nothing left to count: approval no longer decides membership,
and each photograph is embedded at the point it is mentioned, so
"approved but not embedded" is no longer a state the document can be
in. That is a real reduction in what is asserted and it is recorded
here rather than left for someone to notice.

The single test below exists so this file is not an empty stub that a
future reader mistakes for an oversight.

Run:
    PYTHONPYCACHEPREFIX=/tmp/pyc PYTHONPATH=server/code \\
        .venv/bin/python -m unittest tests.test_travel_document_docx_artifact
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "server" / "code"))


class AppendixStaysRetiredTest(unittest.TestCase):
    """A guard against the appendix quietly coming back.

    If it does, photographs are embedded twice and the rule that every
    visible timeline item appears exactly once is broken — which is
    exactly the failure this retirement prevents. Read with comments
    and docstrings stripped, because the retirement notes in the
    builder name Part III to explain that it is gone.
    """

    def setUp(self):
        src = (_REPO / "server" / "code" / "api" / "services"
               / "trip_memoir_docx.py").read_text(encoding="utf-8")
        code = re.sub(r"#.*$", "", src, flags=re.M)
        self.code = re.sub(r'"""[\s\S]*?"""', "", code)

    def test_the_builder_emits_no_photo_appendix_heading(self):
        self.assertNotIn("Part III", self.code)
        self.assertNotIn("Photo Appendix", self.code)

    def test_the_builder_builds_no_appendix_projection(self):
        self.assertNotIn("photo_appendix_projection", self.code)

    def test_the_builder_still_embeds_photographs(self):
        """Non-vacuity. The two tests above would also pass on a
        builder that had stopped embedding images altogether."""
        self.assertIn("add_picture", self.code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
