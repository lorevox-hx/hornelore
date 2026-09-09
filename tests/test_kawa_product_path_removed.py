"""The Kawa / Memory River product path is unreachable — and stays that way.

    cd /mnt/c/Users/chris/hornelore
    PYTHONPATH=server/code .venv/bin/python -m unittest \
      tests.test_kawa_product_path_removed

WO-KAWA-REMOVAL-01, removal half. Companion to
`tests/test_kawa_retired_value_fallbacks.py`, which proves the OTHER half:
that a narrator whose persisted session still carries a retired value lands
somewhere real. This file proves the product path is gone.

WHY THIS IS NOT `grep -c kawa == 0`.

The work order is explicit that the completion test is **zero reachable Kawa
product path**, not zero occurrences, and the difference is the whole point.
Occurrences are SUPPOSED to remain in at least six places, every one of which
this file actively protects rather than merely tolerates:

  * narrator erasure, which must still find and erase historical Kawa files;
  * the erasure-integrity count in db.py;
  * migration 0003, which is immutable;
  * the `kawa_segment` media type, which existing rows may already carry;
  * the retired-language eval case, which REJECTS Kawa vocabulary and becomes
    a stronger negative test after removal, not a leftover;
  * this test, and the removal notes left at each cut site.

A test that demanded zero hits would fail against a correct product and would
pressure a future reader into deleting exactly the things that must survive.
So the assertions below are split in two directions: ABSENT for the product
path, PRESENT for the preservation set. Both halves must hold.

ONE TRAP WORTH NAMING. The word "River" also appears in
`_LV80_PLACE_FRAG_ANCHOR_RX`, the place-fragment anchor regex
(`Park|Lake|River|Avenue|Boulevard|Drive`). That is geography, not Kawa, and
removing it would quietly damage place extraction. It is asserted PRESENT
below so a future case-insensitive sweep trips this test instead of the
product.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

UI = REPO / "ui"
SERVER = REPO / "server" / "code"

#: Files that must not exist at all — the whole-file Kawa implementation.
DELETED_FILES = [
    "ui/js/lori-kawa.js",
    "server/code/api/routers/kawa.py",
    "server/code/kawa_store.py",
    "server/code/kawa_projection.py",
    "data/prompts/kawa_prompts.json",
]

#: (path, regex, what it would mean). Each is a REACHABLE product path — a
#: mount, a route, a rendered element, an injection point. Comments and the
#: removal notes are stripped before matching, so a note that names the thing
#: it removed does not fail its own test.
FORBIDDEN = [
    ("server/code/api/main.py", r"include_router\(\s*kawa\.router",
     "the Kawa router is mounted again"),
    ("server/code/api/main.py", r"^\s*kawa\s*,",
     "routers.kawa is imported again"),
    ("ui/js/api.js", r"/api/kawa/",
     "a client calls a Kawa REST route"),
    ("ui/js/api.js", r"function\s+api\w*Kawa\w*\s*\(",
     "a Kawa API helper is back"),
    ("ui/hornelore1.0.html", r'id="kawaRiverPopover"',
     "the Memory River popover markup is back"),
    ("ui/hornelore1.0.html", r'id="lv80RiverBtn"',
     "the Memory River launcher is back"),
    ("ui/hornelore1.0.html", r'src="js/lori-kawa\.js"',
     "lori-kawa.js is loaded again"),
    ("ui/hornelore1.0.html", r'value="(chronology_river|river_organized)"',
     "a retired memoir mode is selectable again"),
    ("ui/hornelore1.0.html", r'value="(hybrid|kawa_reflection)"',
     "a retired interview mode is selectable again"),
    ("ui/hornelore1.0.html", r'data-view="river"',
     "a river narrator-room view tab is back"),
    ("ui/js/app.js", r"function\s+renderKawaUI\s*\(",
     "the Kawa renderer is back"),
    ("ui/js/app.js", r"kawaRefreshList\s*\(",
     "Kawa segments are preloaded again"),
    ("ui/js/app.js", r"applyKawaToMemoirChapters",
     "the Kawa memoir overlay is back"),
    ("ui/js/app.js", r"\$\{kawaContext\}",
     "KAWA CONTEXT IS ENTERING THE MEMOIR PROMPT AGAIN - narrator-facing"),
    ("ui/js/interview.js", r"maybeApplyKawaFollowup\s*\(",
     "the interview follow-up interception is back"),
    ("ui/js/interview.js", r"function\s+setKawaMode\s*\(",
     "the Kawa mode setter is back"),
    ("ui/js/interview.js", r"KAWA_PROMPTS",
     "a deleted runtime prompt file is read again"),
    ("ui/js/state.js", r"^\s*kawa\s*:\s*\{",
     "the state.kawa slot is back"),
    ("ui/js/state.js", r"organizationMode",
     "the fourth retired-memoir-value home is back"),
]

#: (path, literal, why it must survive). The preservation set.
REQUIRED = [
    ("server/code/api/services/narrator_erasure.py", '("kawa_segments", ("kawa", "people"))',
     "narrator erasure must still erase historical Kawa data"),
    ("server/code/api/db.py", 'kawa_seg_dir = DATA_DIR / "kawa" / "people"',
     "the erasure-integrity count must still find historical Kawa files"),
    ("server/code/db/migrations/0003_media_archive.sql", "'kawa_segment'",
     "landed migrations are immutable"),
    ("server/code/services/media_archive/types.py", '"kawa_segment"',
     "existing media rows may already carry this type"),
    ("data/evals/sentence_diagram_cultural_context_cases_sd044_sd065.json", '"Kawa"',
     "the retired-language eval REJECTS Kawa vocabulary; it is a negative test"),
    ("ui/hornelore1.0.html", "Park|Lake|River|Avenue",
     "the place-fragment anchor regex is geography, not Kawa"),
    ("ui/js/state.js", "lvNormalizeInterviewMode",
     "the compatibility normalizers from kawa(1/2) must survive removal"),
    ("scripts/step6_ws_probe.py", '"kawa/people"',
     "the data-footprint probe must still report historical narrator data"),
]

_LINE_COMMENT = re.compile(r"^\s*(//|#|--)")


def _strip_comments(path: Path, text: str) -> str:
    """Remove comments so a removal NOTE cannot fail its own assertion.

    Deliberately conservative: block comments and full-line comments only.
    It never has to be clever, because the forbidden patterns are code
    shapes (a call, a mount, an attribute), not prose.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)      # js / css
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)      # html
    if path.suffix == ".py":
        text = re.sub(r'"""(.*?)"""', "", text, flags=re.S)
    return "\n".join(
        "" if _LINE_COMMENT.match(ln) else ln for ln in text.splitlines())


class KawaProductPathIsGone(unittest.TestCase):

    def test_the_whole_file_implementations_are_deleted(self):
        for rel in DELETED_FILES:
            with self.subTest(file=rel):
                self.assertFalse(
                    (REPO / rel).exists(),
                    f"{rel} exists again; it was deleted by WO-KAWA-REMOVAL-01")

    def test_no_reachable_kawa_product_path(self):
        for rel, pattern, meaning in FORBIDDEN:
            with self.subTest(file=rel, pattern=pattern):
                p = REPO / rel
                self.assertTrue(p.exists(), f"{rel} is missing entirely")
                body = _strip_comments(p, p.read_text(encoding="utf-8"))
                m = re.search(pattern, body, re.M)
                self.assertIsNone(
                    m, f"{rel}: {meaning} — matched {m.group(0)!r}" if m else "")

    def test_the_preservation_set_survives(self):
        """The half that a zero-occurrences test would have destroyed."""
        for rel, literal, why in REQUIRED:
            with self.subTest(file=rel, literal=literal):
                p = REPO / rel
                self.assertTrue(p.exists(), f"{rel} is missing entirely — {why}")
                self.assertIn(
                    literal, p.read_text(encoding="utf-8"),
                    f"{rel} no longer contains {literal!r}: {why}")

    def test_the_health_check_no_longer_requires_memory_river(self):
        """A correct removal must not read as a regression.

        The old `_check_memory_river` reported "#kawaRiverPopover missing" as
        a hard FAIL, so removing Kawa would have turned the health check red.
        """
        p = UI / "js" / "ui-health-check.js"
        raw = p.read_text(encoding="utf-8")
        # Read the STRIPPED body, for the reason this file exists: the removal
        # note at the cut site names `_check_memory_river`, and asserting
        # against the raw text made this test fail on its own documentation.
        code = _strip_comments(p, raw)
        self.assertNotIn(
            "_check_memory_river", code,
            "the old Memory-River-required health check is back")
        self.assertIn("_check_kawa_removed", code)
        self.assertIn("Memory River popover absent", code)
        self.assertNotIn(
            '"lv80RiverBtn",', code,
            "lv80RiverBtn is still counted in the launcher grid, so the grid "
            "check will WARN forever")

    def test_the_memoir_prompt_carries_no_kawa_context(self):
        """The one place Kawa language reached a narrator-facing output."""
        body = (UI / "js" / "app.js").read_text(encoding="utf-8")
        m = re.search(r"const prompt=`Please write a memoir draft[^`]*`", body)
        self.assertIsNotNone(m, "the memoir prompt template moved; re-pin this")
        prompt = m.group(0)
        for banned in ("kawaContext", "river", "Kawa"):
            self.assertNotIn(
                banned, prompt,
                f"the memoir prompt template contains {banned!r}")


if __name__ == "__main__":
    unittest.main()
