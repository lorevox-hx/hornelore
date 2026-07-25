"""WO-TRAVEL-DOC-UNIFY-01 Phase 5 — doctrine gates across every surface.

Before Phase 4 each cross-cutting Travel Doc rule was proved once per
work order, on whichever file that work order happened to touch. The
no-native-dialog rule was asserted separately in the Lab suite, the
shell suite and the Documenter suite; the no-evidence-lane-DELETE rule
was asserted in two of the three. That is three chances for the rule to
drift apart and one guarantee that a NEW surface arrives uncovered,
because nothing enforces a rule against a list.

This file states each doctrine rule once and applies it to the surface
map in travel_doc_surfaces.py. Adding a surface to that map opts it
into every rule here automatically.

It also does something the per-work-order suites structurally could
not: it proves the Phase 4 inversion is real rather than asserting each
half in a different file. The retired module still deletes a region
behind a native window.confirm() and still pre-stringifies its request
bodies. The unified module does neither. Those are the same facts the
old "Lab vs production" boundary tests were reaching for -- but stated
from the direction the code now runs, and pinned so that a regression
in either direction fails the build.

The retired module's two native confirms are NOT a failure here. They
are pinned at exactly two, with the rule that the module must stay off
the operator path. Deleting the assertion would hide them; "fixing" a
module Phase 4 deliberately left alone would be a different phase.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

try:
    from tests import travel_doc_surfaces as tds
except ImportError:  # direct execution from inside tests/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import travel_doc_surfaces as tds

_DIALOGS = ("window.alert(", "window.confirm(", "window.prompt(",
            "alert(", "confirm(", "prompt(")

#: Evidence lanes are hide-only. Nothing on any surface may hard-delete
#: a photo, a source, a note or a story link.
_EVIDENCE_LANE_TOKENS = ("/api/photos", "/sources", "/notes", "/story",
                         "/evidence", "/captures")


def _named_operator_regions():
    """(label, source) for every region the Travel Doc doctrine governs.

    That is the operator path plus the two dev harnesses and the two
    headless liveness scripts: a harness that opens a native dialog
    still teaches the next reader that dialogs are acceptable here, and
    a liveness run that hits one hangs instead of failing.

    app.js and hornelore1.0.html are whole-application files that carry
    dialogs in lanes that have nothing to do with Travel Doc, so the
    Travel Doc rule is applied to the Travel Doc regions of them -- the
    mount block and the panel -- not to the files. Scoping it honestly
    is what makes the rule enforceable instead of permanently red.
    """
    return [
        ("travel-doc-lab.js (whole module)", tds.UNIFIED_JS.stripped()),
        ("app.js :: traveldoc mount block", tds.traveldoc_block()),
        ("hornelore1.0.html :: Travel Doc panel", tds.traveldoc_panel()),
        ("travel-doc-lab.html (dev harness)", tds.DEV_HARNESS.stripped()),
        ("run_travel_doc_shell_mount_liveness.js",
         tds.LIVENESS_HARNESS.stripped()),
        ("run_travel_doc_mount_liveness.js",
         tds.MOUNT_LIVENESS_HARNESS.stripped()),
    ]


class NoNativeDialogAnywhereOnTheOperatorPathTest(unittest.TestCase):
    """Doctrine: the operator is never stopped by a browser dialog."""

    def test_no_native_dialog_on_any_operator_path_surface(self):
        for label, src in _named_operator_regions():
            for bad in _DIALOGS:
                with self.subTest(surface=label, dialog=bad):
                    self.assertNotIn(
                        bad, src,
                        f"{label} reaches for a native {bad} -- Travel Doc "
                        f"flows resolve in-panel, so an operator is never "
                        f"blocked by a dialog they cannot style, test or "
                        f"screenshot")

    def test_the_retired_page_adds_no_dialog_of_its_own(self):
        # The retired MODULE has two (pinned below). Its page must not
        # add a third, or the quarantine count stops being meaningful.
        page = tds.RETIRED_PAGE.stripped()
        for bad in _DIALOGS:
            with self.subTest(dialog=bad):
                self.assertNotIn(bad, page)


class TheRetiredModuleStaysQuarantinedTest(unittest.TestCase):
    """Phase 4 retired a fallback. It did not delete a module."""

    def test_the_retired_modules_native_confirms_are_pinned_not_forgotten(self):
        # Exactly two: deleteRegion() and deleteStop(). This is the flow
        # Chris ruled against in Phase 3B -- "do not copy a production
        # flow that dead-ends after a native confirm" -- and it is why
        # the unified module grew an in-panel review instead.
        #
        # Pinning the count beats deleting the assertion. If someone
        # adds a third, this fails and the decision gets made on purpose.
        src = tds.RETIRED_JS.stripped()
        self.assertEqual(
            2, len(re.findall(r"window\.confirm\(", src)),
            "the retired module's native-confirm count changed; it is "
            "pinned at 2 (deleteRegion, deleteStop) precisely because "
            "nobody is maintaining it")
        self.assertIn("deleteRegion", src)
        self.assertIn("deleteStop", src)

    def test_only_its_own_page_still_references_the_retired_module(self):
        offenders = []
        for p in sorted((tds.REPO_ROOT / "ui").rglob("*")):
            if not p.is_file() or p.suffix not in (".js", ".css", ".html"):
                continue
            if p == tds.RETIRED_PAGE.path or p == tds.RETIRED_JS.path:
                continue
            src = tds.Surface(p, "", False).stripped()
            for tok in ("travel-documenter.js", "travel-documenter.css",
                        "lvTravelDocumenterMount"):
                if tok in src:
                    offenders.append(f"{p.name} names {tok}")
        self.assertEqual(
            [], offenders,
            "the retired module is reachable only through "
            "ui/travel-documenter.html; something re-attached it")

    def test_the_shell_loads_no_retired_asset(self):
        shell = tds.SHELL_HTML.stripped()
        for tok in ("js/travel-documenter.js", "css/travel-documenter.css",
                    'id="lvTravelDocHost"'):
            with self.subTest(token=tok):
                self.assertNotIn(tok, shell)

    def test_the_retired_page_is_the_only_caller_of_the_retired_mount(self):
        self.assertIn("lvTravelDocumenterMount", tds.RETIRED_PAGE.stripped())
        self.assertIn("window.lvTravelDocumenterMount",
                      tds.RETIRED_JS.stripped())


class ThePhase4InversionIsProvedTest(unittest.TestCase):
    """The old suites asserted each half of this in a different file."""

    def test_the_unified_module_replaced_the_native_confirm_delete_flow(self):
        retired = tds.RETIRED_JS.stripped()
        unified = tds.UNIFIED_JS.stripped()
        # The retired module: region/stop delete dead-ends at a dialog.
        self.assertIn("window.confirm(", retired)
        # The unified module: same capability, resolved in-panel.
        self.assertNotIn("window.confirm(", unified)
        self.assertIn("routeDelete", unified,
                      "the in-panel region/stop delete review is what "
                      "replaced the retired module's native confirm")

    def test_the_unified_module_does_not_pre_stringify_api_bodies(self):
        # api() owns request encoding. The retired module pre-stringifies
        # and double-encodes; that bug is exactly why the unified module
        # passes raw objects. Asserting both directions makes the reason
        # legible instead of leaving a bare "no JSON.stringify" rule.
        self.assertIn("JSON.stringify({", tds.RETIRED_JS.stripped())
        self.assertNotIn(
            "body: JSON.stringify(", tds.UNIFIED_JS.stripped(),
            "call sites must hand api() a raw object; pre-stringifying "
            "double-encodes and the server answers 422")

    def test_the_shell_mounts_the_unified_module_and_only_that(self):
        block = tds.traveldoc_block()
        # Phase 5 mutation check: the bare name "lvTravelDocMount" also
        # matches the `typeof window.lvTravelDocMount === "function"`
        # guard on the line above the call, so this gate stayed green
        # against a block that checked whether it could mount and then
        # never did. Pin the call itself and the handle it must produce
        # -- the handle is what teardown later needs to find.
        self.assertIn("lvTravelDocMount(", block)
        self.assertIn(
            "_lvTravelDocUnifiedHandle = window.lvTravelDocMount(", block,
            "the shell must keep the mount HANDLE; a mount whose handle "
            "is dropped cannot be destroyed on tab exit")
        self.assertNotIn("lvTravelDocumenterMount", block)
        self.assertNotIn("lvTravelDocSetSurface", block)


class EvidenceLanesAreHideOnlyTest(unittest.TestCase):
    """Doctrine: no evidence-lane DELETE, on any surface."""

    _DELETE_CALL = re.compile(
        r'api\(\s*("(?:[^"\\]|\\.)*"(?:\s*\+\s*[^,]+?)?)\s*,\s*\{'
        r'\s*method:\s*"DELETE"')

    def test_every_delete_in_the_unified_module_is_a_trip_region_or_stop(self):
        src = tds.UNIFIED_JS.stripped()
        total = len(re.findall(r'method:\s*"DELETE"', src))
        calls = self._DELETE_CALL.findall(src)
        # If the shapes ever diverge, the scan below is silently missing
        # a delete and the gate would pass by not looking.
        self.assertEqual(
            total, len(calls),
            f"{total} DELETEs in the module but the URL scan matched "
            f"{len(calls)} -- a delete is written in a shape this gate "
            f"cannot read, so it is unverified")
        self.assertTrue(calls, "the delete lanes vanished entirely")
        for url in calls:
            with self.subTest(url=re.sub(r"\s+", " ", url)[:70]):
                self.assertTrue(
                    url.lstrip().startswith('"/api/trips/'),
                    "only trip, region and stop lanes may hard-delete")
                for lane in _EVIDENCE_LANE_TOKENS:
                    self.assertNotIn(
                        lane, url,
                        f"evidence lanes are hide-only; {lane} must be "
                        f"patched hidden, never deleted")

    def test_no_evidence_lane_delete_on_any_operator_path_surface(self):
        for label, src in _named_operator_regions():
            for m in re.finditer(r'method:\s*"DELETE"', src):
                window = src[max(0, m.start() - 220):m.start()]
                for lane in _EVIDENCE_LANE_TOKENS:
                    with self.subTest(surface=label, lane=lane):
                        self.assertNotIn(lane, window,
                                         f"{label} deletes on {lane}")


class OneMountCallerOffTheShellTest(unittest.TestCase):
    """The dev harness earns its keep by being that one caller."""

    def test_the_dev_harness_is_the_only_non_shell_caller_of_the_mount(self):
        callers = []
        for p in sorted((tds.REPO_ROOT / "ui").rglob("*")):
            if not p.is_file() or p.suffix not in (".js", ".html"):
                continue
            if p == tds.UNIFIED_JS.path:  # the module defines it
                continue
            if "lvTravelDocMount" in tds.Surface(p, "", False).stripped():
                callers.append(p.name)
        self.assertEqual(
            ["app.js", "hornelore1.0.html", "travel-doc-lab.html"],
            sorted(callers),
            "the shell and the DEV-ONLY harness are the only callers; the "
            "harness is kept because it is the only thing that exercises "
            "the non-embedded branch")

    def test_the_harness_still_says_what_it_is(self):
        html = tds.DEV_HARNESS.read()
        self.assertIn("DEV-ONLY", html)
        self.assertIn("REMOVABLE", html)
        # ...and the two load-bearing modules must not.
        for s in (tds.UNIFIED_JS, tds.UNIFIED_CSS):
            with self.subTest(surface=s.name):
                self.assertNotIn(
                    "REMOVABLE", s.read(),
                    f"{s.name} is {s.role} -- it must not carry a "
                    f"delete-me marker")


if __name__ == "__main__":
    unittest.main()
