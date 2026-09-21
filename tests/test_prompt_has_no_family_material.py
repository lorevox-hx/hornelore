"""A real narrator's life must not be compiled into everyone's prompt.

WHAT HAPPENED
=============
On 2026-09-21 Lori told a synthetic narrator, as though it were shared
history, that they had a relative who worked somewhere they had never
mentioned. The details belonged to a real family member. They had not
been retrieved from her record — narrator isolation held, and her own
biography section carried her own data.

They were in the prompt. `docs/archive/` traces the path: a real
development session, quoted into a design discussion, promoted into two
work-order specs as the canonical worked example, and compiled from
there into `prompt_composer.py`, which every narrator receives.

`GRADUATION_CANDIDATES_2026-05-01.md` had already listed that material
as family-specific and must-not-travel. It travelled anyway. A written
decision did not stop it; a test is the only thing that can.

WHY THE OBVIOUS CHECK WOULD HAVE PASSED
=======================================
The natural regression is to take proper nouns from the `people` table
and assert none appear in the prompt. It would have scored this exposure
CLEAN, because the most identifying phrase — a childhood surgery — is in
no database row at all. The session it came from is not in the current
database.

So the live-data check cannot be assertion one. It is assertion four,
useful only for material added tomorrow, and its limitation is stated
where someone reading a green run will see it.

THE DENYLIST IS PRIVATE
=======================
The real phrases live in `.runtime/privacy/family_phrases.txt`, which is
gitignored. Writing them here would put them in a public repository to
prove they are not in a public repository.

When that file is absent this module SKIPS the phrase assertions and
says so. A skip is not a pass — `unittest` prints OK either way, which
is exactly how twenty-three dead tests went unnoticed in this repo
before, so the skip message names what was not checked.

The fictional fixtures below are committed, and they test the checker
itself: if the scan is broken, the invented phrases catch it without
anyone's biography being involved.
"""
from __future__ import annotations

import re
import sqlite3
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPOSER = REPO / "server" / "code" / "api" / "prompt_composer.py"
PRIVATE_PHRASES = REPO / ".runtime" / "privacy" / "family_phrases.txt"

#: Marker every block carrying a narrator utterance must display.
EXAMPLE_MARKER = "[EXAMPLE — invented."

#: The invented scenario. Committed on purpose: these are the strings the
#: prompt SHOULD contain, and they prove the scanner reads real text.
FICTIONAL = ("Pellard Street", "feed store", "Marrow Bay")

#: Every constant that can reach a narrator, and the mode-ish surfaces
#: composed from them. Named explicitly rather than discovered, so a new
#: narrator-facing block has to be added here deliberately.
NARRATOR_FACING_CONSTANTS = (
    "_ID_BASE_0", "_ID_BASE_1", "_ID_BASE_2", "_ID_BASE_3", "_ID_BASE_4",
    "_ID_EXAMPLES_0", "_ID_EXAMPLES_1", "_ID_EXAMPLES_2", "_ID_EXAMPLES_3",
    "LORI_STORY_MODE_DIRECTIVE", "LORI_CORE_IDENTITY",
    "LORI_INTERVIEW_DISCIPLINE", "LORI_ORAL_HISTORY_RESPONSE",
    "LORI_QUESTION_HIERARCHY_GUIDANCE",
    "_WITNESS_RECEIPT_DIRECTIVE", "_WITNESS_RECEIPT_EXAMPLES",
)


def _load_phrases():
    if not PRIVATE_PHRASES.is_file():
        return None
    out = []
    for line in PRIVATE_PHRASES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out or None


def _constant_bodies():
    """name -> text, for every narrator-facing constant that exists."""
    src = COMPOSER.read_text(encoding="utf-8")
    found = {}
    for name in NARRATOR_FACING_CONSTANTS:
        m = re.search(r'^%s\s*=\s*(?:f?""")' % re.escape(name), src, re.M)
        if not m:
            continue
        end = src.find('"""', m.end())
        found[name] = src[m.end():end]
    return found


PHRASES = _load_phrases()
_SKIP = "private denylist absent — %s NOT CHECKED for real phrases" % PRIVATE_PHRASES

#: Committed, invented, and NEVER skipped. The private list may be
#: missing on any clone; these run everywhere and cover the scanner,
#: the assembled surfaces and the markers on their own.
FICTIONAL_DENYLIST = ("Pellard Street", "Marrow Bay", "Ferrous Gate",
                      "Kellerman", "Orrin Bay", "Cape Thistle", "Orla",
                      "Nessa", "Vantry", "Drommel", "Thistlecross")


class TheUnverifiedCaseIsReportedNotPassed(unittest.TestCase):
    """A missing fixture must not read as a clean result.

    `unittest` prints OK for a run that skipped everything, and this
    repository has already lost 23 tests to a green summary that meant
    less than it looked like. So the absence of the private list is
    asserted as an explicit UNVERIFIED state rather than left to a skip
    line nobody reads, and the committed assertions below never depend
    on it.
    """

    def test_the_private_list_state_is_explicit(self):
        if PHRASES is None:
            print("\n  [UNVERIFIED] %s is absent. The known-phrase "
                  "assertions did NOT run. Committed fictional-fixture "
                  "and assembled-prompt coverage DID run. This is not a "
                  "clean result for real phrases — it is no result."
                  % PRIVATE_PHRASES)
        self.assertTrue(
            PHRASES is None or len(PHRASES) >= 5,
            "the private denylist exists but is nearly empty, which "
            "would pass while checking almost nothing")

    def test_committed_coverage_runs_without_the_private_list(self):
        """The three committed classes must not be skip-gated."""
        import inspect
        src = inspect.getsource(TheAssembledPromptIsCleanInEveryMode)
        self.assertIn("def test_the_scan_detects_terms_in_assembled_text", src)
        self.assertIn("def test_every_surface_composed_to_something", src)
        for name in ("test_the_scan_detects_terms_in_assembled_text",
                     "test_every_surface_composed_to_something"):
            fn = getattr(TheAssembledPromptIsCleanInEveryMode, name)
            self.assertFalse(getattr(fn, "__unittest_skip__", False),
                             "%s is skip-gated; committed coverage must "
                             "run without the private fixture" % name)


class TheDenylistIsAbsentFromEveryConstant(unittest.TestCase):

    @unittest.skipIf(PHRASES is None, _SKIP)
    def test_no_known_family_phrase_in_any_narrator_facing_constant(self):
        bodies = _constant_bodies()
        self.assertTrue(bodies, "no narrator-facing constants found")
        for name, body in sorted(bodies.items()):
            low = body.lower()
            for phrase in PHRASES:
                with self.subTest(constant=name, phrase=phrase):
                    self.assertNotIn(phrase.lower(), low)

    def test_the_scanner_actually_reads_the_constants(self):
        """Guard against a green run produced by reading nothing.

        Uses the INVENTED strings, so it proves the scan works without
        putting a real phrase in a committed file.
        """
        bodies = _constant_bodies()
        joined = " ".join(bodies.values())
        self.assertIn("Pellard Street", joined,
                      "scanner found no known content — it is not reading "
                      "the constants it claims to check")


class TheAssembledPromptIsCleanInEveryMode(unittest.TestCase):
    """Constant-level checks miss what a composer interpolates."""

    MODES = ("oral_history", "questionnaire_first", "warm_storytelling",
             "clear_direct", "companion")

    def _assembled(self):
        """Every mode's composed interview directive, plus the witness
        receipt, which is composed separately and is its own surface."""
        import sys
        sys.path.insert(0, str(REPO / "server" / "code"))
        from api import prompt_composer as pc
        out = {}
        for mode in self.MODES:
            for with_examples in (True, False):
                key = "%s/examples=%s" % (mode, with_examples)
                out[key] = pc.compose_interview_discipline(
                    include_examples=with_examples)
        for with_examples in (True, False):
            out["witness_receipt/examples=%s" % with_examples] = (
                pc.compose_witness_receipt_directive(
                    include_examples=with_examples))
        return out

    @unittest.skipIf(PHRASES is None, _SKIP)
    def test_no_known_family_phrase_survives_composition(self):
        for key, text in sorted(self._assembled().items()):
            low = text.lower()
            for phrase in PHRASES:
                with self.subTest(surface=key, phrase=phrase):
                    self.assertNotIn(phrase.lower(), low)

    def test_every_surface_composed_to_something(self):
        for key, text in sorted(self._assembled().items()):
            with self.subTest(surface=key):
                self.assertGreater(len(text), 200,
                                   "surface composed to nothing; the clean "
                                   "result above would be meaningless")

    def test_the_scan_detects_terms_in_assembled_text(self):
        """Committed, never skipped: prove the scan can FIND something.

        A denylist scan that reads empty text passes perfectly. This
        asserts the machinery finds known invented strings in the
        composed surfaces, so a clean real-phrase result means the text
        was searched rather than missing.
        """
        surfaces = self._assembled()
        joined = " ".join(surfaces.values())
        found = [t for t in FICTIONAL_DENYLIST if t in joined]
        self.assertTrue(
            found,
            "no invented example term found in ANY composed surface — "
            "the scan is reading nothing, so its clean results are "
            "meaningless")
        # The witness examples and the interview examples are separate
        # surfaces; at least one term from each replacement must survive
        # composition, or a block was dropped rather than rewritten.
        witness = " ".join(v for k, v in surfaces.items()
                           if k.startswith("witness") and "True" in k)
        interview = " ".join(v for k, v in surfaces.items()
                             if not k.startswith("witness") and "True" in k)
        self.assertIn("Cape Thistle", witness)
        self.assertIn("Pellard Street", interview)


class ExamplesAreMarkedAsExamples(unittest.TestCase):
    """A narrator utterance in the prompt must announce that it is invented.

    The failure was not only WHOSE details were in the prompt. It was that
    Lori reproduced one and framed it as something she and the narrator
    had discussed. Marking every example is the part of the repair that
    survives the model reproducing the text anyway.
    """

    def test_blocks_holding_a_narrator_utterance_carry_the_marker(self):
        bodies = _constant_bodies()
        for name, body in sorted(bodies.items()):
            if "Narrator:" not in body and "ALLOWED" not in body:
                continue
            with self.subTest(constant=name):
                self.assertIn(EXAMPLE_MARKER, body,
                              "%s shows a narrator utterance without the "
                              "invented-example marker" % name)

    def test_the_marker_says_not_to_repeat_it(self):
        src = COMPOSER.read_text(encoding="utf-8")
        self.assertIn("Never repeat as their history.", src)


class LiveNarratorNounsAreASupplementNotTheTest(unittest.TestCase):
    """Assertion FOUR. Useful for material added tomorrow, and no use at
    all for the exposure this file exists because of.

    Kept deliberately last, and named so that nobody reading a green run
    mistakes it for the check that matters.
    """

    def _db(self):
        env = REPO / ".env"
        data_dir = db_name = None
        if env.is_file():
            for line in env.read_text(encoding="utf-8",
                                      errors="replace").splitlines():
                line = line.strip()
                if line.startswith("DATA_DIR=") and not data_dir:
                    data_dir = line.split("=", 1)[1].strip()
                elif line.startswith("DB_NAME=") and not db_name:
                    db_name = line.split("=", 1)[1].strip()
        if not (data_dir and db_name):
            return None
        p = Path(data_dir) / "db" / db_name
        return p if p.is_file() else None

    def test_no_live_narrator_display_name_appears_in_the_prompt(self):
        p = self._db()
        if p is None:
            self.skipTest("no live database reachable — supplement skipped")
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True)
        try:
            names = [r[0] for r in con.execute(
                "SELECT display_name FROM people WHERE COALESCE(testing_only,0)=0")]
        finally:
            con.close()
        src = COMPOSER.read_text(encoding="utf-8")
        for full in names:
            for token in str(full or "").split():
                if len(token) < 4:
                    continue
                with self.subTest(token=token):
                    self.assertNotIn(token, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
