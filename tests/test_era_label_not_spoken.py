"""BUG-LORI-ERA-LABEL-IN-NARRATOR-PROSE-01 — Lori must not speak system labels.

LIVE (2026-07-14), Christopher's session:
    "What was your daily life like during those Coming of Age years in Stanley?"
    "What do you remember about where you were living during your Coming of Age?"

"Coming of Age" is the TITLE-CASED HEADING form from era_id_to_warm_label() —
correct on a Life Map button, wrong in a sentence spoken to an 86-year-old. The
pass-2A directive literally handed Lori the template
    "...during your {era_label}?"
so she said it back. The bug was in what we GAVE her, not in what she did.

lv_eras already carries the speakable form ("the years when you were coming of
age"). Per the locked principle from the 2026-05-02 Patch B postmortem —
prompt-heavy rules make Lori WORSE — the fix is a DATA fix: hand her the right
words rather than add a paragraph telling her not to use the wrong ones.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

from api.prompt_composer import _era_spoken_phrase  # noqa: E402

_COMPOSER = (_SERVER_CODE / "api" / "prompt_composer.py").read_text(
    encoding="utf-8")

# The seven canonical heading labels. None may appear in a narrator-facing
# example sentence.
_HEADING_LABELS = [
    "Earliest Years", "Early School Years", "Adolescence", "Coming of Age",
    "Building Years", "Later Years",
]


class EraSpokenPhraseTest(unittest.TestCase):
    def test_the_live_failure_case(self):
        self.assertEqual(_era_spoken_phrase("coming_of_age", "Coming of Age"),
                         "the years when you were coming of age")

    def test_every_canonical_era_has_a_speakable_phrase(self):
        for era in ("earliest_years", "early_school_years", "adolescence",
                    "coming_of_age", "building_years", "later_years", "today"):
            spoken = _era_spoken_phrase(era, "X")
            self.assertTrue(spoken)
            self.assertNotIn("_", spoken, era)      # no raw era_id
            # no title-cased heading label leaking through
            for lab in _HEADING_LABELS:
                self.assertNotIn(lab, spoken, "%s leaked %r" % (era, lab))

    def test_unknown_era_degrades_to_human_words_not_the_label(self):
        # Falling back to the raw label IS the bug. Anything unknown must
        # still come out as something a person would say.
        for bad in ("", "not yet set", "bogus_era", None):
            spoken = _era_spoken_phrase(bad, "Coming of Age")
            self.assertEqual(spoken, "that time in your life", repr(bad))
            self.assertNotIn("Coming of Age", spoken)


class DirectiveDoesNotHandLoriTheLabelTest(unittest.TestCase):
    def test_pass2a_example_sentence_uses_the_spoken_phrase(self):
        # The exact template that produced the live failure.
        self.assertNotIn(
            "during your {era_label}?", _COMPOSER,
            "the pass-2A example still hands Lori the heading label to speak")
        self.assertIn("during {era_spoken}?", _COMPOSER)

    def test_directives_mark_the_label_as_internal(self):
        # era_label may still orient her internally — it just may not be the
        # thing she says out loud.
        self.assertIn("internal label", _COMPOSER)
        self.assertIn("never the label itself", _COMPOSER)


if __name__ == "__main__":
    unittest.main()
