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

    # ── LIVE ROUND 2 (2026-07-13, after restart) ──────────────────────
    def test_symbol_soup_is_rejected_by_the_shape_gate(self):
        # The shape gate still earns its keep on pure symbol soup.
        noise = ("# : 9 #4 - s 4 | | di i s k EJ s? v k Y a 1 1 LI hy > | 6 "
                 "en 4 KS ) K x - .. i e A i >= x ne = s ia > ae ej } ve + ict")
        self.assertLess(ocr._wordlike_ratio(noise), ocr.ocr_min_ratio())

    def test_shape_alone_CANNOT_catch_hallucinated_words(self):
        # THE HARD LESSON (live, 2026-07-13): on a photo of FOOD — no text in
        # it at all — tesseract hallucinated WORD-SHAPED tokens: SEHEN,
        # initial, VITA, Capra, SIONI, Natit. That 762-char noise scored a
        # word-like ratio of 0.443 — ABOVE the 0.40 gate — so it sailed
        # through and was stored as evidence Lori would read back. Word length
        # does not save us either; the junk had plenty of 5+ char tokens.
        #
        # This test exists to stop anyone "fixing" hallucinations with another
        # text-shape heuristic. It cannot work. Confidence is the answer.
        hallucinated = ("GELA SEHEN initial VITA, SIONI Capra Natit ho Nan "
                        "po su MRI id ge sa ZAS")
        self.assertGreaterEqual(
            ocr._wordlike_ratio(hallucinated), ocr.ocr_min_ratio(),
            "if this ever fails, the ratio changed — but do NOT rely on it to "
            "reject hallucinations; that is what the CONFIDENCE gate is for")

    def test_confidence_gate_exists_and_is_the_primary_filter(self):
        # Tesseract knows when it is guessing. Real signs/menus come back
        # 70-90; hallucinated texture is far lower. No new OCR package needed —
        # pytesseract already exposes per-word confidence via image_to_data.
        self.assertGreater(ocr.ocr_min_confidence(), 0)
        self.assertGreaterEqual(ocr.ocr_min_words(), 1)
        src = (_REPO_ROOT / "server" / "code" / "api" / "services"
               / "travel_doc_photo_ocr.py").read_text(encoding="utf-8")
        self.assertIn("image_to_data", src)
        self.assertIn("output_type=Output.DICT", src)
        self.assertIn("conf < min_conf", src)

    def test_rejection_reports_the_confidence_it_actually_saw(self):
        # A rejection that says only "no_text_found" is a dead end: you cannot
        # tell a photo with NO text from a photo whose text missed the floor by
        # two points. Live proof (2026-07-14): the ZUBR beer mug — big, clear,
        # embossed lettering — was rejected, and there was no way to see how
        # close it came. Curved glass depresses per-word confidence.
        r = ocr._result(False, "tesseract", error="no_text_found",
                        confidence=48.0,
                        observed="best pass: confidence 48, 3 words, floor 55")
        self.assertFalse(r["ok"])
        self.assertEqual(r["confidence"], 48.0)
        self.assertIn("floor 55", r["observed"])

    def test_success_reports_confidence_too(self):
        r = ocr._result(True, "tesseract", raw_text="AUGUSTINER",
                        confidence=87.4)
        self.assertEqual(r["confidence"], 87.4)

    def test_min_conf_override_is_clamped_and_plumbed(self):
        # The Lab can lower the floor for a hard photo without a stack restart
        # per attempt. Out-of-range values must not disable the gate entirely.
        import inspect
        self.assertIn("min_conf",
                      inspect.signature(ocr.run_ocr).parameters)
        self.assertIn("min_conf",
                      inspect.signature(ocr._run_tesseract).parameters)
        src = inspect.getsource(ocr._run_tesseract)
        self.assertIn("max(0.0, min(100.0, float(min_conf)))", src)

    def test_override_does_not_change_the_stored_confidence_tier(self):
        # Lowering the floor admits MORE drafts. It must never promote one:
        # the row is still confidence='draft' and still needs approval.
        src = (_REPO_ROOT / "server" / "code" / "api" / "routers"
               / "trips.py").read_text(encoding="utf-8")
        ocr_ep = src[src.index('@router.post("/photo-links/{link_id}/ocr")'):]
        ocr_ep = ocr_ep[:ocr_ep.index("@router.post", 10)]
        self.assertIn('confidence="draft"', ocr_ep)

    def test_confidence_thresholds_are_env_tunable(self):
        prev = os.environ.get("HORNELORE_OCR_MIN_CONF")
        os.environ["HORNELORE_OCR_MIN_CONF"] = "72"
        self.addCleanup(
            lambda: (os.environ.__setitem__("HORNELORE_OCR_MIN_CONF", prev)
                     if prev is not None
                     else os.environ.pop("HORNELORE_OCR_MIN_CONF", None)))
        self.assertAlmostEqual(ocr.ocr_min_confidence(), 72.0)

    def test_a_short_real_sign_still_passes(self):
        # A raw SCORE cannot do this job: the noise scores 86 and this real
        # sign scores 93. The word-like RATIO is what separates them.
        for real in ("GRAND CAFE ORIENT MENU",
                     "DEUTSCHES JAGD-UND FISCHEREIMUSEUM"):
            self.assertGreaterEqual(ocr._wordlike_ratio(real),
                                    ocr.ocr_min_ratio(), real)

    def test_ratio_gate_is_env_tunable(self):
        prev = os.environ.get("HORNELORE_OCR_MIN_RATIO")
        os.environ["HORNELORE_OCR_MIN_RATIO"] = "0.9"
        self.addCleanup(
            lambda: (os.environ.__setitem__("HORNELORE_OCR_MIN_RATIO", prev)
                     if prev is not None
                     else os.environ.pop("HORNELORE_OCR_MIN_RATIO", None)))
        self.assertAlmostEqual(ocr.ocr_min_ratio(), 0.9)

    def test_downscale_cap_and_early_exit_exist(self):
        # OCR took 7s (coaster) to 19s (dense menu) live on full-res photos.
        self.assertGreater(ocr.ocr_max_dim(), 0)
        self.assertGreater(ocr.ocr_early_exit_score(), 0)

    def test_ocr_still_off_by_default(self):
        prev = os.environ.get("HORNELORE_PHOTO_OCR")
        os.environ.pop("HORNELORE_PHOTO_OCR", None)
        self.addCleanup(
            lambda: os.environ.__setitem__("HORNELORE_PHOTO_OCR", prev)
            if prev is not None else None)
        self.assertFalse(ocr.ocr_enabled())
        self.assertFalse(ocr.run_ocr("/nonexistent.jpg")["ok"])


class PhotoLightboxTest(unittest.TestCase):
    """LIVE UX (2026-07-13): below 1500px — i.e. every laptop — the photo
    workspace grid collapses and the detail becomes a full-width row BELOW the
    gallery, so choosing a photo meant scrolling past a huge image to reach the
    evidence panel (the actual work). The detail also showed the THUMBNAIL, so
    you could not read the menu you were about to OCR."""

    def setUp(self):
        self.src = _strip(_LAB.read_text(encoding="utf-8"))
        self.css = _CSS.read_text(encoding="utf-8")

    def test_clicking_a_thumbnail_opens_the_lightbox(self):
        self.assertIn("openLightbox(l.id)", self.src)

    def test_lightbox_shows_the_full_image_not_the_thumbnail(self):
        self.assertIn("fullImageUrl", self.src)
        self.assertIn("/image", self.src)

    def test_evidence_panel_lives_inside_the_lightbox(self):
        self.assertIn("tdl-lb-side", self.src)
        m = re.search(r"tdl-lb-side[\s\S]{0,400}renderPhotoEvidence\(sel\)",
                      self.src)
        self.assertIsNotNone(
            m, "the evidence panel is not rendered inside the lightbox")

    def test_evidence_panel_is_not_rendered_twice(self):
        # It must not appear both inline AND in the lightbox (shared state).
        self.assertIn("if (!lightbox.open) detail.appendChild", self.src)

    def test_prev_next_and_keyboard_navigation(self):
        self.assertIn("lightboxStep", self.src)
        for key in ("Escape", "ArrowLeft", "ArrowRight"):
            self.assertIn(key, self.src)

    def test_image_and_evidence_are_side_by_side(self):
        self.assertRegex(
            self.css, r"\.tdl-lb-body\s*\{[^}]*grid-template-columns")

    def test_busy_state_while_ocr_runs(self):
        # OCR took 7-19s live with no feedback; the button looked dead.
        self.assertIn("photoEvidence.busy", self.src)
        self.assertIn("tdl-ev-busy", self.src)
        self.assertIn("tdl-ev-busy", self.css)

    def test_thumbnails_are_big_enough_to_tell_apart(self):
        self.assertIn("minmax(150px", self.css)


class LaptopUsabilityTest(unittest.TestCase):
    """LIVE REVIEW (2026-07-13) at laptop width. Three measured problems:
      1. the narrator name overflowed the topbar (scrollWidth 379 vs client
         282) and collided with the tab strip, pushing Current/Trip Plan/
         Photos off the bar;
      2. the photo filter rail held a fixed 150px COLUMN for four buttons,
         stealing width from the gallery on exactly the screens with none
         to spare;
      3. the 295px left rail reset to EXPANDED on every reload, so it had to
         be re-collapsed every single time.
    """

    def setUp(self):
        self.src = _strip(_LAB.read_text(encoding="utf-8"))
        self.css = _CSS.read_text(encoding="utf-8")

    def test_rail_collapse_is_remembered(self):
        self.assertIn("tdlRailCollapsed", self.src)
        self.assertIn("localStorage.setItem(\"tdlRailCollapsed\"", self.src)

    def test_narrator_name_cannot_push_the_tabs_off(self):
        self.assertIn("tdl-brand-person", self.src)
        self.assertIn(".tdl-brand-person", self.css)
        self.assertRegex(self.css, r"\.tdl-brand-person\s*\{[^}]*text-overflow:\s*ellipsis")
        self.assertRegex(self.css, r"\.tdl-tabs\s*\{[^}]*flex-wrap:\s*nowrap")

    def test_filter_rail_becomes_chips_on_a_laptop(self):
        # Below 1500px the 150px filter COLUMN must give its width back to the
        # gallery. (There is more than one 1500px block, so check them all.)
        blocks = re.findall(r"@media \(max-width: 1500px\)\s*\{([\s\S]*?)\n\}",
                            self.css)
        self.assertTrue(blocks, "no 1500px breakpoint at all")
        joined = "\n".join(blocks)
        self.assertIn(".tdl-filter-rail", joined,
                      "the filter rail still holds a fixed column on a laptop")
        self.assertIn(".tdl-photo-workspace { grid-template-columns: minmax(0, 1fr); }",
                      joined,
                      "the photo workspace does not reclaim the filter column")


if __name__ == "__main__":
    unittest.main()
