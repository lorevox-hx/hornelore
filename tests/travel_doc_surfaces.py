"""WO-TRAVEL-DOC-UNIFY-01 Phase 5 — the one Travel Doc surface map.

Before Phase 4 there were two Travel Doc surfaces in the operator path
and the test suites were split along that seam: one file guarded "the
Lab", another guarded "the production Documenter", and each carried its
own private copy of the paths, the comment strippers and the app.js
block regex. Phase 4 retired the fallback, so that seam is gone -- but
six suites were still describing the world by which work order created
them rather than by what the code now is.

This module is the single answer to "what are the Travel Doc surfaces,
and which of them is on the operator path". Every Travel Doc suite
imports it instead of re-deriving it. When a surface moves, it moves
here once.

The map deliberately keeps naming the retired module. Retiring a
fallback is not deleting a module: ui/js/travel-documenter.js, its
stylesheet and ui/travel-documenter.html are all still on disk and
still served, and a map that quietly forgot them would let them drift
back into the shell unobserved.

The file names still say "lab". Renaming a 3,400-line module is churn
that would bury a real diff; that rename is parked, not forgotten, and
ROLE strings below are how a reader learns what each file actually is.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from typing import Iterator, List, NamedTuple, Tuple

try:
    from tests import source_scan_helpers as _ssh
except ImportError:  # direct execution from inside tests/
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as _ssh

REPO_ROOT = Path(__file__).resolve().parent.parent
_UI = REPO_ROOT / "ui"


class Surface(NamedTuple):
    path: Path
    role: str
    on_operator_path: bool

    @property
    def name(self) -> str:
        return self.path.name

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def stripped(self) -> str:
        """Source with comments removed.

        Every Travel Doc suite scans for banned strings, and every one of
        them has to let documentation comments NAME the thing they forbid
        -- otherwise the comment explaining a boundary trips the gate that
        enforces it. Stripping is therefore part of the map, not a helper
        each suite reinvents slightly differently.
        """
        raw = self.read()
        if self.path.suffix == ".js":
            return _ssh.strip_js_comments(raw)
        if self.path.suffix == ".css":
            return re.sub(r"/\*[\s\S]*?\*/", "", raw)
        return re.sub(r"<!--[\s\S]*?-->", "", raw)


# --------------------------------------------------------------- operator path
UNIFIED_JS = Surface(
    _UI / "js" / "travel-doc-lab.js",
    "the operator's only Travel Doc module since Phase 4", True)
UNIFIED_CSS = Surface(
    _UI / "css" / "travel-doc-lab.css",
    "the unified Travel Doc's stylesheet", True)
SHELL_JS = Surface(
    _UI / "js" / "app.js",
    "the shell; mounts the unified module into the Travel Doc tab", True)
SHELL_HTML = Surface(
    _UI / "hornelore1.0.html",
    "the shell page; carries the Travel Doc tab and panel", True)
SHELL_CSS = Surface(
    _UI / "css" / "lori80.css",
    "the shell stylesheet; sizes the one Travel Doc host", True)

# ------------------------------------------------------------ off that path
DEV_HARNESS = Surface(
    _UI / "travel-doc-lab.html",
    "DEV-ONLY harness; the only non-shell caller of lvTravelDocMount(), "
    "and so the only thing that exercises the non-embedded branch", False)
RETIRED_JS = Surface(
    _UI / "js" / "travel-documenter.js",
    "retired from the operator path by Phase 4; still on disk, still "
    "served, reachable only through its own standalone page", False)
RETIRED_CSS = Surface(
    _UI / "css" / "travel-documenter.css",
    "the retired module's stylesheet; no longer loaded by the shell", False)
RETIRED_PAGE = Surface(
    _UI / "travel-documenter.html",
    "the retired module's only surviving caller", False)

LIVENESS_HARNESS = Surface(
    REPO_ROOT / "scripts" / "ui" / "run_travel_doc_shell_mount_liveness.js",
    "behavioural proof that the shell mounts and tears down one surface",
    True)
MOUNT_LIVENESS_HARNESS = Surface(
    REPO_ROOT / "scripts" / "ui" / "run_travel_doc_mount_liveness.js",
    "Phase 1.1 behavioural proof that a mount/destroy cycle leaves "
    "nothing behind; drives the module directly, without the shell",
    False)
# WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 3b. Added to the map on
# 2026-08-13 because a harness absent from this inventory is a harness
# the doctrine scans do not read -- which is how the Phase 2D picker
# script sat outside every dialog scan until somebody noticed.
PHOTO_WINDOW_LIVENESS = Surface(
    REPO_ROOT / "scripts" / "ui" / "run_photo_window_liveness.js",
    "Phase 3b behavioural proof that every placement on a day is "
    "reachable and the mounted tile count stays bounded; drives the "
    "real DOM against a canned API",
    False)
PHOTO_WINDOW_ARITHMETIC = Surface(
    REPO_ROOT / "scripts" / "ui" / "run_photo_window_arithmetic.js",
    "Phase 3b proof of the window arithmetic itself; executes the real "
    "photoWindow/slidePhotoWindow without a browser, so the load-shape "
    "maths is verified where Chromium cannot run",
    False)

PHOTO_PLACEMENT_SAFETY = Surface(
    REPO_ROOT / "scripts" / "ui" / "run_photo_placement_safety.js",
    "Phase 5-readiness proof that a half-failed multi-batch Add reports "
    "what actually happened, and that every day-inspector photo control "
    "refuses to discard typed edits; executes the real shipped "
    "functions against an api that fails on demand",
    False)

LAZY_THUMB_SCROLLPORT = Surface(
    REPO_ROOT / "scripts" / "ui" / "run_lazy_thumb_scrollport.js",
    "2026-08-14 proof that deferred thumbnails load inside a NESTED "
    "scrollport. Carries two controls that reproduce the old native-hint "
    "failure, so a green run cannot come from a double that says yes to "
    "everything; executes the real armLazyThumbs against a DOM stand-in",
    False)

#: Every file this project considers part of a Travel Doc surface.
ALL: List[Surface] = [
    UNIFIED_JS, UNIFIED_CSS, SHELL_JS, SHELL_HTML, SHELL_CSS,
    DEV_HARNESS, RETIRED_JS, RETIRED_CSS, RETIRED_PAGE,
    LIVENESS_HARNESS, MOUNT_LIVENESS_HARNESS,
    PHOTO_WINDOW_LIVENESS, PHOTO_WINDOW_ARITHMETIC,
    PHOTO_PLACEMENT_SAFETY, LAZY_THUMB_SCROLLPORT,
]

#: The surfaces an operator can actually reach from the shell.
OPERATOR_PATH: List[Surface] = [s for s in ALL if s.on_operator_path]

#: On disk and still served, but off the operator path.
OFF_PATH: List[Surface] = [s for s in ALL if not s.on_operator_path]


# ------------------------------------------------------------------ extractors
def traveldoc_block() -> str:
    """The `if (tabName === "traveldoc")` arm of lvShellShowTab().

    Two suites used to carry this regex privately, which meant a change
    to the shell's mount block could be caught by one and missed by the
    other. It lives here now.
    """
    m = re.search(r'if \(tabName === "traveldoc"\) \{[\s\S]*?\n  \}',
                  SHELL_JS.stripped())
    assert m is not None, "traveldoc mount block missing from app.js"
    return m.group(0)


def traveldoc_panel() -> str:
    """The <section id="lvTravelDocTab"> markup, comments stripped."""
    m = re.search(r'<section id="lvTravelDocTab"[\s\S]*?</section>',
                  SHELL_HTML.stripped())
    assert m is not None, "Travel Doc panel missing from the shell"
    return m.group(0)


def css_rules(css: str) -> Iterator[Tuple[Tuple[str, ...], str]]:
    """Yield (ancestors, selector) for every block in `css`.

    A line-oriented scan cannot tell a real selector from a keyframe
    step: `0% {` looks exactly like an unscoped element rule. Track brace
    depth instead, so a caller can skip anything nested under @keyframes
    while still checking the selectors inside @media -- which are real,
    and are exactly where a scoping mistake would hide.
    """
    buf: List[str] = []
    stack: List[str] = []
    for ch in css:
        if ch == "{":
            sel = "".join(buf).strip()
            buf = []
            yield tuple(stack), sel
            stack.append(sel)
        elif ch == "}":
            buf = []
            if stack:
                stack.pop()
        else:
            buf.append(ch)


class SurfaceMapTest(unittest.TestCase):
    """The map is only useful if it still describes the repository."""

    def test_every_declared_surface_exists_on_disk(self):
        for s in ALL:
            with self.subTest(surface=s.name):
                self.assertTrue(
                    s.path.exists(),
                    f"{s.path} is declared in the surface map ({s.role}) "
                    f"but is not on disk -- update the map or restore it")

    def test_the_retired_module_is_still_here(self):
        # Phase 4 retired a fallback; it did not delete a module. If this
        # ever fails, the deletion was a separate decision and the map,
        # the spec and the checklist all have to move together.
        for s in (RETIRED_JS, RETIRED_CSS, RETIRED_PAGE):
            with self.subTest(surface=s.name):
                self.assertTrue(s.path.exists())

    def test_operator_path_and_off_path_partition_the_map(self):
        self.assertEqual(len(OPERATOR_PATH) + len(OFF_PATH), len(ALL))
        self.assertEqual(len({s.path for s in ALL}), len(ALL),
                         "a surface is declared twice in the map")

    def test_extractors_still_find_their_targets(self):
        self.assertIn("traveldoc", traveldoc_block())
        self.assertIn("lvTravelDocTab", traveldoc_panel())


if __name__ == "__main__":
    unittest.main()
