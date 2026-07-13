"""LIVE-TEST FIXES (2026-07-13) — the two real bugs the live run exposed.

BUG 1 — "Lookup public context" could NEVER work.
  With HORNELORE_PUBLIC_LOOKUP_PROVIDER=url_only (which fetches the exact page
  the operator supplies), the Lab button posted {source_type} and NO url, so
  the endpoint always answered "url_only provider requires a url". The button
  now carries a real URL field.

BUG 2 — Tesseract read scene text as garbage.
  Live: the Augustiner coaster ("Augustiner Brau Munchen 1328") came back as
  "VAMI i all, N STIVA RTAS INIT fart 1404 MI", and the Munich museum sign
  returned no_text_found — on FULL-RES 3072x4080 originals, so never a
  resolution problem. Cause: tesseract's DEFAULT page-segmentation mode is for
  scanned DOCUMENTS. We now preprocess and try sparse-text PSMs, keeping the
  best-scoring candidate.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SERVER_CODE = _REPO_ROOT / "server" / "code"
if str(_SERVER_CODE) not in sys.path:
    sys.path.insert(0, str(_SERVER_CODE))

_LAB = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_CSS = _REPO_ROOT / "ui" / "css" / "travel-doc-lab.css"

from api.services import travel_doc_photo_ocr as ocr  # noqa: E402


def _strip(js: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", js)


class LookupUrlInputTest(unittest.TestCase):
    """BUG 1 — the Lookup button must send a url."""

    def setUp(self):
        self.src = _strip(_LAB.read_text(encoding="utf-8"))

    def test_lookup_sends_a_url(self):
        # The regression: body was `{ source_type: "place_context" }` with no
        # url, which url_only can never satisfy.
        self.assertIn("url: u", self.src,
                      "the Lookup button no longer sends a url — with the "
                      "url_only provider it can never succeed")

    def test_a_url_field_exists(self):
        self.assertIn("tdl-ev-url", self.src)
        self.assertIn("Paste a public URL", self.src)

    def test_empty_url_is_explained_not_silently_fired(self):
        # Firing with no url just produced an opaque provider error.
        self.assertIn("Paste a public URL first", self.src)

    def test_typed_url_survives_rerender(self):
        self.assertIn("lookupUrl", self.src)

    def test_typed_url_does_not_bleed_onto_another_photo(self):
        # A URL typed for photo A must not silently attach to photo B.
        self.assertIn("sameLink", self.src)
        self.assertIn('lookupUrl: sameLink ?', self.src)

    def test_css_for_the_url_field(self):
        self.assertIn(".tdl-ev-url", _CSS.read_text(encoding="utf-8"))


class TesseractSceneTextTest(unittest.TestCase):
    """BUG 2 — scene text (signs, coasters), not scanned documents."""

    def test_sparse_text_psm_is_tried_first(self):
        # PSM 11 = "sparse text: find as much text as possible, in no
        # particular order" — the correct mode for a sign on a building.
        self.assertEqual(ocr.ocr_psms()[0], "11")

    def test_psms_are_env_overridable(self):
        # Restore the PREVIOUS value, don't just pop — popping an env var that
        # was already set is the same leak class as the HORNELORE_TRIPS one.
        prev = os.environ.get("HORNELORE_OCR_PSM")
        os.environ["HORNELORE_OCR_PSM"] = "6,4"
        self.addCleanup(
            lambda: (os.environ.__setitem__("HORNELORE_OCR_PSM", prev)
                     if prev is not None
                     else os.environ.pop("HORNELORE_OCR_PSM", None)))
        self.assertEqual(ocr.ocr_psms(), ("6", "4"))

    def test_real_text_outscores_the_live_garbage_reading(self):
        # THE live failure: both readings have the same raw char count, so a
        # flat score cannot tell them apart. Length-weighting must.
        garbage = "VAMI i all, N STIVA RTAS INIT fart 1404 MI"
        real = "Augustiner Brau Munchen seit 1328"
        self.assertGreater(ocr._wordlike_score(real),
                           ocr._wordlike_score(garbage),
                           "the PSM chooser cannot distinguish a true reading "
                           "from tesseract noise")

    def test_museum_sign_scores_well(self):
        self.assertGreater(
            ocr._wordlike_score("DEUTSCHES JAGD-UND FISCHEREIMUSEUM"), 200)

    def test_empty_and_noise_score_zero(self):
        self.assertEqual(ocr._wordlike_score(""), 0)
        self.assertEqual(ocr._wordlike_score("1404 . , 12 !!"), 0)

    def test_ocr_still_off_by_default(self):
        prev = os.environ.get("HORNELORE_PHOTO_OCR")
        os.environ.pop("HORNELORE_PHOTO_OCR", None)
        self.addCleanup(
            lambda: os.environ.__setitem__("HORNELORE_PHOTO_OCR", prev)
            if prev is not None else None)
        self.assertFalse(ocr.ocr_enabled())
        self.assertFalse(ocr.run_ocr("/nonexistent.jpg")["ok"])


if __name__ == "__main__":
    unittest.main()
