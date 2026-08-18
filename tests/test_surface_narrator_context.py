"""WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part B.

ONE narrator-context contract for every narrator-scoped surface.

Before Phase 2, five surfaces each decided independently who the narrator
was, three of the shell's launchers passed no narrator at all, and the
per-surface caches were read without validation. Photo Intake stamps
`narrator_id` on every upload, so "the shell says A and this surface
remembers B" is a cross-narrator write.

These tests pin the SHAPE of the contract. The BEHAVIOUR -- that an
invalid explicit id fails closed instead of falling back to a cached
narrator -- is proved by executing the shipped module in
`scripts/ui/run_narrator_context_behaviour.js`, because a source scan
cannot tell a working fail-closed branch from a broken one.

pytest is not installed in this repo. Run with:

    PYTHONPATH=server/code .venv/bin/python -m unittest tests.test_surface_narrator_context
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tests.source_scan_helpers import strip_js_comments  # noqa: E402

_UI = _REPO_ROOT / "ui"
_HELPER = _UI / "js" / "narrator-context.js"
_APP = _UI / "js" / "app.js"
_SHELL = _UI / "hornelore1.0.html"

# Every standalone surface that is scoped to one narrator, with the
# legacy cache key it kept.
_SURFACES = {
    "trip-tab": ("js/trip-tab.js", "trip_tab_narrator_id_v1"),
    "photo-intake": ("js/photo-intake.js", "pi_narrator_id_v1"),
    # Deliberately shares Intake's key: the two pages are a pair.
    "photo-timeline": ("js/photo-timeline.js", "pi_narrator_id_v1"),
    "media-archive": ("js/media-archive.js", "ma_narrator_id_v1"),
}
_PAGES = ["trip-tab.html", "photo-intake.html", "photo-timeline.html",
          "media-archive.html"]

SHELL_KEY = "lv_active_person_v55"


def _js(rel: str) -> str:
    return strip_js_comments((_UI / rel).read_text(encoding="utf-8"))


class TheHelperExistsAndIsShared(unittest.TestCase):
    def test_the_helper_file_exists(self):
        self.assertTrue(_HELPER.exists())

    def test_every_narrator_scoped_page_loads_it(self):
        for page in _PAGES:
            with self.subTest(page=page):
                html = (_UI / page).read_text(encoding="utf-8")
                self.assertIn("js/narrator-context.js", html)

    def test_the_shell_loads_it_before_app_js(self):
        html = (_UI / "hornelore1.0.html").read_text(encoding="utf-8")
        i_ctx = html.find("js/narrator-context.js")
        i_app = html.find('src="js/app.js"')
        self.assertGreater(i_ctx, 0)
        self.assertGreater(i_app, 0)
        self.assertLess(i_ctx, i_app,
                        "lvOpenNarratorTool uses the helper, so it must load first")

    def test_it_declares_the_shell_key_only_to_refuse_it(self):
        src = strip_js_comments(_HELPER.read_text(encoding="utf-8"))
        self.assertIn(SHELL_KEY, src)
        # The one place the constant may be USED is the guard in
        # remember() and the matching guard in readCache().
        self.assertIn("legacyKey === SHELL_KEY", src)


class TheShellHandsTheNarratorOver(unittest.TestCase):
    def setUp(self):
        self.app = _js("js/app.js")
        self.shell = strip_js_comments(_SHELL.read_text(encoding="utf-8"))

    def test_there_is_one_launcher(self):
        self.assertIn("function lvOpenNarratorTool(", self.app)

    def test_no_narrator_scoped_tool_is_opened_bare(self):
        # The defect: `window.open("photo-intake.html", ...)` with no
        # narrator. Any direct window.open of a narrator-scoped page is a
        # launcher that forgot, so the pages are named and banned rather
        # than the call.
        pages = ["photo-intake.html", "photo-timeline.html", "trip-tab.html",
                 "media-archive.html", "photo-elicit.html"]
        for blob, where in ((self.app, "app.js"), (self.shell, "hornelore1.0.html")):
            for page in pages:
                with self.subTest(where=where, page=page):
                    self.assertNotIn('window.open("' + page, blob)
                    self.assertNotIn("window.open('" + page, blob)

    def test_the_media_tool_launchers_route_through_it(self):
        for page in ["photo-intake.html", "photo-timeline.html",
                     "media-archive.html", "trip-tab.html",
                     "photo-elicit.html"]:
            with self.subTest(page=page):
                self.assertIn('lvOpenNarratorTool("' + page, self.app)

    def test_the_inline_shell_buttons_route_through_it_too(self):
        self.assertIn("lvOpenNarratorTool('photo-intake.html')", self.shell)
        self.assertIn("lvOpenNarratorTool('photo-timeline.html')", self.shell)

    def test_the_trips_iframe_still_carries_the_narrator(self):
        self.assertIn('ctx.withNarrator("trip-tab.html", pid)', self.app)

    def test_the_launcher_falls_back_rather_than_dropping_the_narrator(self):
        # If the helper tag is ever missing, losing the narrator is the
        # bug being fixed -- so the fallback carries it by hand.
        body = self.app[self.app.find("function lvOpenNarratorTool("):]
        body = body[: body.find("\n}\n") + 3]
        self.assertIn("narrator_id=", body)


class TheSurfacesUseTheContract(unittest.TestCase):
    def test_each_surface_resolves_through_the_helper(self):
        for name, (rel, _key) in _SURFACES.items():
            with self.subTest(surface=name):
                src = _js(rel)
                self.assertIn("LorevoxNarratorContext", src)
                self.assertIn("NC.resolve(", src)

    def test_no_surface_writes_the_shell_key(self):
        for name, (rel, _key) in _SURFACES.items():
            with self.subTest(surface=name):
                src = _js(rel)
                self.assertNotIn(SHELL_KEY, src)

    def test_each_surface_keeps_its_own_legacy_key(self):
        # Demoted to a fallback cache, NOT deleted: a direct standalone
        # load with no query is still allowed to remember.
        for name, (rel, key) in _SURFACES.items():
            with self.subTest(surface=name):
                self.assertIn(key, _js(rel))

    def test_no_surface_writes_a_cache_without_going_through_remember(self):
        # A raw setItem on the narrator key is how an unvalidated id gets
        # persisted, which is what poisons the next visit.
        for name, (rel, key) in _SURFACES.items():
            with self.subTest(surface=name):
                src = _js(rel)
                for m in re.finditer(r"localStorage\.setItem\(\s*([A-Za-z_$][\w$]*)",
                                     src):
                    var = m.group(1)
                    if var != "LS_NARRATOR":
                        continue
                    # Permitted only as the no-helper fallback, i.e. on an
                    # `else` branch beside an NC.remember call.
                    window = src[max(0, m.start() - 220): m.start()]
                    self.assertIn("NC.remember(", window,
                                  f"{name}: bare setItem on the narrator key")

    def test_each_surface_still_has_its_own_picker(self):
        # "Preserve existing standalone pickers. Do not remove them."
        for name, (rel, _key) in _SURFACES.items():
            with self.subTest(surface=name):
                src = _js(rel)
                self.assertTrue(
                    "loadNarrators" in src or "resolveNarrator" in src,
                    f"{name} lost its picker loader")

    def test_only_a_query_sourced_selection_is_cached(self):
        # A rejected handoff must not become next visit's default.
        for name, (rel, _key) in _SURFACES.items():
            with self.subTest(surface=name):
                src = _js(rel)
                self.assertIn('res.source === "query"', src)


class CrossPageLinksPreserveContext(unittest.TestCase):
    def test_trip_tab_opens_intake_with_its_narrator(self):
        src = _js("js/trip-tab.js")
        self.assertIn('NC.openTool("photo-intake.html", state.narratorId)', src)

    def test_photo_timeline_rewrites_its_intake_link(self):
        src = _js("js/photo-timeline.js")
        self.assertIn('NC.withNarrator("photo-intake.html"', src)

    def test_trip_tab_photo_elicit_links_still_carry_the_narrator(self):
        src = _js("js/trip-tab.js")
        self.assertEqual(src.count("photo-elicit.html?narrator_id="), 2)


class TravelDocStaysBoundToTheShell(unittest.TestCase):
    """It must not acquire an independent selector authority."""

    def test_embedded_identity_still_comes_only_from_opts(self):
        src = _js("js/travel-doc-lab.js")
        self.assertIn('(embedded ? "" : qsParams.get("person_id"))', src)

    def test_the_mounted_workspace_has_no_narrator_picker_of_its_own(self):
        src = _js("js/travel-doc-lab.js")
        self.assertNotIn("LorevoxNarratorContext", src,
                         "Travel Doc takes its narrator from the shell's opts")


class KawaStaysFrozen(unittest.TestCase):
    """Phase 2 did not extend the retired river metaphor."""

    def test_no_phase_2_file_touches_kawa(self):
        for rel in ["js/narrator-context.js"]:
            with self.subTest(rel=rel):
                src = _js(rel).lower()
                for word in ("kawa", "memory river", "chronology_river"):
                    self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
