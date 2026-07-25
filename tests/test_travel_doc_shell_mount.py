"""WO-TRAVEL-DOC-UNIFY-01 Phase 4 — single-surface shell gate.

Phase 2 mounted the (now mountable) Travel Doc workspace inside the main
Hornelore Travel Doc tab while the legacy Documenter stayed reachable
behind a temporary comparison toggle. Phases 3A-3D moved the last four
reasons to use the old surface across — the trip force-delete impact
gate, trip/region/stop CRUD, photo/source upload + cluster, and route
ordering — and Phase 4 removed the fallback. The tab now holds ONE host
and mounts ONE module.

Two classes of defect are worth a build gate here.

  1. CSS LEAKAGE. The module's stylesheet was written for a standalone
     page that owned <body>. Loaded by hornelore1.0.html it would publish
     its custom properties globally and its element resets would either
     miss the workspace or repaint the dark shell. Every rule must hang
     off .tdl-root, the class the module puts on its own host.

  2. TWO LIVE TRAVEL DOC MOUNTS. A mount owns a BroadcastChannel
     subscription, a document-level keydown listener and a Lori socket.
     Two mounts means two of each, and both keydown handlers answering
     Escape. Phase 4 removed the surface toggle, which was one of the
     three paths that could reach a mount — the other two, narrator
     switch and tab exit/re-entry, are unchanged and still gated below.
     Removing a fallback does not remove this risk; it removes one of
     its doors.

WHAT PHASE 4 ADDED TO THIS FILE
-------------------------------
LegacyFallbackIsGoneTest asserts the removal directly rather than
trusting the absence of the old assertions. A test suite that merely
stops checking for the toggle would pass just as happily against a build
where the toggle came back. The rule those tests encode: from the normal
shell path there is no reference to the old module, no way to ask for
it, and no copy that tells an operator it exists.

What Phase 4 did NOT remove: ui/js/travel-documenter.js, its stylesheet,
ui/travel-documenter.html, and every backend endpoint either surface
calls. LegacyModuleStillExistsTest pins that, because "retire the
fallback" is a frontend routing change and deleting the module would
have been a different, larger, riskier one.

Everything else here is acceptance-criteria lockdown: the shell supplies
identity (never the querystring), the module's dev self-branding must not
appear on the operator path, the standalone harness must keep working,
and no native prompt/confirm/alert may sneak in.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

try:
    from tests import source_scan_helpers as _ssh
except ImportError:  # direct execution: python tests/test_travel_doc_shell_mount.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as _ssh

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP = _REPO_ROOT / "ui" / "js" / "app.js"
_SHELL = _REPO_ROOT / "ui" / "hornelore1.0.html"
_LAB_JS = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_LAB_CSS = _REPO_ROOT / "ui" / "css" / "travel-doc-lab.css"
_LAB_HTML = _REPO_ROOT / "ui" / "travel-doc-lab.html"
_SHELL_CSS = _REPO_ROOT / "ui" / "css" / "lori80.css"
_LEGACY_JS = _REPO_ROOT / "ui" / "js" / "travel-documenter.js"
_LEGACY_CSS = _REPO_ROOT / "ui" / "css" / "travel-documenter.css"
_LEGACY_HTML = _REPO_ROOT / "ui" / "travel-documenter.html"
_LIVENESS = (_REPO_ROOT / "scripts" / "ui" /
             "run_travel_doc_shell_mount_liveness.js")


def _stripped_app() -> str:
    return _ssh.strip_js_comments(_APP.read_text(encoding="utf-8"))


def _stripped_lab_js() -> str:
    return _ssh.strip_js_comments(_LAB_JS.read_text(encoding="utf-8"))


def _stripped_shell_html() -> str:
    # Comments in the shell carry a lot of "do not do X" prose that would
    # otherwise trip the banned-string scans below.
    html = _SHELL.read_text(encoding="utf-8")
    return re.sub(r"<!--[\s\S]*?-->", "", html)


def _stripped_lab_css() -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", _LAB_CSS.read_text(encoding="utf-8"))


def _css_rules(css: str):
    """Yield (ancestors, selector) for every block in `css`.

    A line-oriented scan cannot tell a real selector from a keyframe step:
    `0% {` looks exactly like an unscoped element rule. Track brace depth
    instead, so the caller can skip anything nested under @keyframes while
    still checking the selectors inside @media — which are real, and are
    exactly where a scoping mistake would hide.
    """
    buf: list[str] = []
    stack: list[str] = []
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


def _traveldoc_block() -> str:
    """The `if (tabName === "traveldoc")` arm of lvShellShowTab()."""
    app = _stripped_app()
    m = re.search(r'if \(tabName === "traveldoc"\) \{[\s\S]*?\n  \}', app)
    assert m is not None, "traveldoc mount block missing from app.js"
    return m.group(0)


def _traveldoc_panel() -> str:
    """The <section id="lvTravelDocTab"> markup, comments stripped."""
    html = _stripped_shell_html()
    m = re.search(r'<section id="lvTravelDocTab"[\s\S]*?</section>', html)
    assert m is not None, "Travel Doc panel missing from the shell"
    return m.group(0)


class ShellLoadsTheModuleTest(unittest.TestCase):
    """Requirement 2 — load the mountable Travel Doc module and CSS."""

    def test_shell_loads_the_lab_script_and_stylesheet(self):
        html = _stripped_shell_html()
        self.assertRegex(html, r'src="js/travel-doc-lab\.js')
        self.assertRegex(html, r'href="css/travel-doc-lab\.css')

    def test_lab_stylesheet_loads_before_the_shell_stylesheet(self):
        # lori80.css owns the Travel Doc host sizing. It must be able to
        # win a specificity tie against the module's sheet, which means it
        # has to come second.
        html = _stripped_shell_html()
        lab = html.index('href="css/travel-doc-lab.css')
        shell = html.index('href="css/lori80.css')
        self.assertLess(lab, shell,
                        "travel-doc-lab.css must load before lori80.css")

    def test_module_still_has_no_load_time_side_effects(self):
        # The shell loads this file on EVERY page view, including sessions
        # that never open the Travel Doc tab. If the module did anything
        # at script scope — grab a host, open the update channel, add a
        # listener — every narrator session would pay for it and the
        # "exactly one mount" invariant would be false before the operator
        # clicked anything.
        src = _stripped_lab_js()
        self.assertNotIn("\n  boot();\n})();", src)
        self.assertNotIn("DOMContentLoaded", src)


class ShellMountContractTest(unittest.TestCase):
    """Requirements 1, 3, 4 — host, mount call, handle."""

    def test_tab_holds_exactly_one_host(self):
        panel = _traveldoc_panel()
        self.assertIn('id="lvTravelDocUnifiedHost"', panel)
        # Phase 4 inverted this: Phase 2 required the legacy host to sit
        # BESIDE the unified one ("do not remove the old Documenter yet").
        # The whole point of Phase 4 is that it no longer does.
        self.assertNotIn('id="lvTravelDocHost"', panel)
        self.assertEqual(len(re.findall(r'\bid="lvTravelDoc\w*Host"', panel)), 1)
        # One host element in the panel, full stop — not one *named* host
        # with an anonymous second one alongside it.
        self.assertEqual(len(re.findall(r"<div\b", panel)), 1)

    def test_shell_calls_the_mount_with_shell_supplied_identity(self):
        block = _traveldoc_block()
        self.assertIn("window.lvTravelDocMount(host, {", block)
        self.assertIn("person_id: pid", block)
        self.assertIn("embedded: true", block)
        # pid is the shell's selected narrator, not a pasted or parsed id.
        self.assertIn("(state && state.person_id)", block)

    def test_shell_never_reads_identity_from_the_querystring(self):
        # Acceptance: "active narrator/person id comes from the shell
        # opts, not querystring."
        block = _traveldoc_block()
        for banned in ("URLSearchParams", "location.search", "person_id="):
            self.assertNotIn(banned, block,
                             f"traveldoc mount must not parse {banned}")

    def test_embedded_mounts_quarantine_the_querystring(self):
        # The other half of the same rule, enforced in the module: even if
        # the shell URL carries ?person_id= from another launcher, an
        # embedded mount must ignore it rather than silently scope Travel
        # Doc to a narrator no other tab agrees with.
        src = _stripped_lab_js()
        self.assertIn('(embedded ? "" : qsParams.get("person_id"))', src)
        self.assertIn('(embedded ? "" : qsParams.get("api"))', src)

    def test_the_returned_handle_is_stored(self):
        block = _traveldoc_block()
        self.assertIn("window._lvTravelDocUnifiedHandle = window.lvTravelDocMount(",
                      block)

    def test_the_destroyer_calls_destroy_on_the_handle(self):
        # Phase 2 ran this over two destroyers. There is one now, and it is
        # the only thing standing between a narrator switch and a stranded
        # keydown listener + Lori socket.
        app = _stripped_app()
        m = re.search(r"function _lvTravelDocDestroyUnified\(\) \{[\s\S]*?\n\}", app)
        self.assertIsNotNone(m, "_lvTravelDocDestroyUnified missing from app.js")
        body = m.group(0)
        self.assertIn('typeof h.destroy === "function"', body)
        self.assertIn("h.destroy()", body)
        # Teardown must never throw — a caller remounting would otherwise
        # be left with a half-destroyed mount and no way to recover.
        self.assertIn("try {", body)
        # It must also null the marker, or the next tab-show sees a
        # person_id that "matches" and skips the remount entirely.
        self.assertIn("window._lvTravelDocUnifiedMountedFor = null;", body)


class OnlyOneMountIsEverLiveTest(unittest.TestCase):
    """The standing top risk, gated on every path that reaches a mount.

    Phase 4 deleted the surface-toggle path and with it two tests. Read
    the deletions together with scripts/ui/run_travel_doc_shell_mount_
    liveness.js, whose recorded negative controls found the toggle's two
    guards were mutually redundant — the guards that survive here are the
    ones that were never redundant with anything.
    """

    def test_remount_destroys_before_it_mounts(self):
        # Requirement 4: destroy() before remounting. A narrator change
        # takes this path, and remounting over a live mount is now the
        # ONLY way to end up with two of everything while the tab is open.
        # Phase 2 had a second guard inside lvTravelDocSetSurface(); Phase
        # 4 removed the setter, so this line lost its backstop and carries
        # the invariant alone.
        block = _traveldoc_block()
        mount_at = block.index("window.lvTravelDocMount(host, {")
        destroy_at = block.rindex("_lvTravelDocDestroyUnified();", 0, mount_at)
        self.assertLess(destroy_at, mount_at)

    def test_leaving_the_tab_tears_down(self):
        # A hidden shell panel is display:none, not unloaded. Without this
        # the operator navigating to Media left a live keydown listener,
        # BroadcastChannel and Lori socket under the tab they were looking
        # at.
        app = _stripped_app()
        m = re.search(r'if \(tabName !== "traveldoc"\) \{[\s\S]*?\n  \}', app)
        self.assertIsNotNone(m)
        self.assertIn("window.lvTravelDocTeardownAll()", m.group(0))

    def test_narrator_switch_tears_down(self):
        html = _stripped_shell_html()
        m = re.search(r"async function lv80SwitchPerson[\s\S]{0,1600}", html)
        self.assertIsNotNone(m)
        self.assertIn("window.lvTravelDocTeardownAll()", m.group(0))

    def test_the_narrator_switch_fallback_nulls_a_marker_that_exists(self):
        # The switch flow falls back to nulling the mount marker by hand if
        # app.js has not defined the teardown. Phase 4 found that fallback
        # nulling _lvTravelDocMountedFor — the OLD Documenter's marker,
        # which no longer exists — so the fallback had quietly become a
        # no-op that would leave a stale mount in place.
        html = _stripped_shell_html()
        m = re.search(r"async function lv80SwitchPerson[\s\S]{0,1600}", html)
        self.assertIsNotNone(m)
        flow = m.group(0)
        self.assertIn("window._lvTravelDocUnifiedMountedFor = null;", flow)
        self.assertNotRegex(flow, r"_lvTravelDocMountedFor\s*=")

    def test_teardown_destroys_the_one_surface(self):
        app = _stripped_app()
        m = re.search(r"window\.lvTravelDocTeardownAll = function[\s\S]*?\n\};", app)
        self.assertIsNotNone(m)
        self.assertIn("_lvTravelDocDestroyUnified();", m.group(0))

    def test_no_narrator_selected_destroys_rather_than_hides(self):
        # Deselecting leaves the empty-state message. If the previous
        # narrator's mount merely sat underneath it, its socket would stay
        # bound to a narrator the operator has navigated away from.
        block = _traveldoc_block()
        m = re.search(r"if \(!pid\) \{[\s\S]*?Choose a narrator first", block)
        self.assertIsNotNone(m, "empty-state arm missing from the mount block")
        self.assertIn("_lvTravelDocDestroyUnified()", m.group(0))


class LegacyFallbackIsGoneTest(unittest.TestCase):
    """Phase 4 required-behaviour gates 1-5.

    Asserted as absences on purpose. Simply deleting the Phase 2 tests
    that checked FOR the toggle would leave a suite that passes just as
    happily against a build where the toggle came back.
    """

    def test_the_shell_never_names_the_legacy_module(self):
        # The strongest single gate in this file, and the reason every
        # Phase 4 replacement comment in hornelore1.0.html was written to
        # avoid the word: this is the RAW file, comments included. A
        # reference cannot hide in prose.
        self.assertNotIn("travel-documenter",
                         _SHELL.read_text(encoding="utf-8"),
                         "the shell must not reference the legacy module "
                         "at all, not even in a comment")

    def test_the_shell_loads_no_legacy_asset(self):
        html = _stripped_shell_html()
        self.assertNotRegex(html, r'src="js/travel-documenter\.js')
        self.assertNotRegex(html, r'href="css/travel-documenter\.css')

    def test_the_legacy_mount_is_never_called_from_the_shell(self):
        # Requirement 3: stop mounting lvTravelDocumenterMount from the
        # shell Travel Doc tab. Checked in both shell files, because the
        # call could live in either.
        self.assertNotIn("lvTravelDocumenterMount", _stripped_app())
        self.assertNotIn("lvTravelDocumenterMount", _stripped_shell_html())

    def test_no_surface_switching_machinery_survives_in_app_js(self):
        app = _stripped_app()
        for banned in ("lvTravelDocSetSurface", "_lvTravelDocSurface",
                       "_LV_TD_SURFACE_KEY", "_lvTravelDocActiveSurface",
                       "_lvTravelDocDestroyLegacy", "_lvTravelDocLegacyHandle",
                       "_lvTravelDocPaintSurfaceChrome", "lvTravelDocSurface"):
            self.assertNotIn(banned, app,
                             f"surface-toggle machinery survives: {banned}")

    def test_no_surface_switch_markup_survives_in_the_shell(self):
        html = _stripped_shell_html()
        for banned in ("lv-td-surface", "data-td-surface", "lv-td-host-off",
                       "lv-td-host-legacy", "lvTravelDocHost",
                       "lvTravelDocSetSurface"):
            self.assertNotIn(banned, html,
                             f"surface-toggle markup survives: {banned}")

    def test_the_operator_never_reads_that_a_fallback_exists(self):
        # Requirement 5, and the work order's own acceptance line: no
        # visible "legacy", "production Travel Doc", "UI Lab" or
        # "experimental" on the normal shell path.
        #
        # Scoped to the Travel Doc panel and to the mount block's own
        # string literals rather than to the whole shell: hornelore1.0.html
        # contains ~19 unrelated uses of "legacy" (retired facts endpoints,
        # QF ownership, era key mapping), and a file-wide ban would be a
        # gate that fails for reasons having nothing to do with Travel Doc.
        haystacks = (_traveldoc_panel(), _traveldoc_block())
        for text in haystacks:
            low = text.lower()
            for banned in ("legacy", "documenter", "ui lab", "experimental",
                           "production travel doc", "older travel doc"):
                self.assertNotIn(banned, low,
                                 f"legacy framing on the operator path: {banned}")

    def test_the_module_never_sends_an_operator_to_the_old_surface(self):
        # Phase 4 found the day photo picker's empty state still reading
        # "add them via Photo Intake, then cluster from the production
        # Travel Doc" — ungated, so operator-visible, and a dead end twice
        # over once Phase 3C put upload and cluster on this surface.
        src = _stripped_lab_js()
        for banned in ("production Travel Doc", "Documenter",
                       "travel-documenter"):
            self.assertNotIn(banned, src,
                             f"module still points at the old surface: {banned}")

    def test_the_route_board_deep_link_is_gone(self):
        # Phase 3B parked a "Older Travel Documenter (being retired)"
        # foot-note under the route board, built from prodTravelDocUrl().
        # It was the last thing in the workspace framing this surface as
        # the newcomer.
        src = _stripped_lab_js()
        self.assertNotIn("prodTravelDocUrl", src)
        self.assertNotIn("tdl-route-legacy", src)
        self.assertNotIn("tdl-route-legacy", _stripped_lab_css())

    def test_the_liveness_harness_drives_one_surface(self):
        # The headless proof must not call a function Phase 4 deleted: a
        # step that throws is not a weaker check, it is a crash mid-run.
        # Checked on the executable half of the file — its header
        # legitimately RECORDS the two-surface negative controls, and
        # deleting that history to satisfy a grep would be worse than the
        # grep is worth.
        src = _ssh.strip_js_comments(_LIVENESS.read_text(encoding="utf-8"))
        self.assertNotIn('step("switch_to_legacy"', src)
        self.assertNotIn('step("switch_to_unified"', src)
        self.assertNotIn("lvTravelDocSetSurface(", src)
        # ...and it must positively assert the removal, not merely omit it.
        self.assertIn("single surface", src)
        self.assertIn("the tab holds exactly one Travel Doc host", src)


class LegacyModuleStillExistsTest(unittest.TestCase):
    """Requirement 7 — retire the fallback, do not delete the backend.

    Phase 4 is a routing change. ui/js/travel-documenter.js still exists,
    ui/travel-documenter.html still mounts it, and every endpoint either
    surface ever called is untouched. If a later phase deletes the module
    it should delete these assertions in the same commit, deliberately.
    """

    def test_the_legacy_module_and_its_page_are_not_deleted(self):
        for p in (_LEGACY_JS, _LEGACY_CSS, _LEGACY_HTML):
            self.assertTrue(p.exists(),
                            f"Phase 4 must not delete {p.name}")

    def test_the_legacy_standalone_page_still_mounts_it(self):
        html = _LEGACY_HTML.read_text(encoding="utf-8")
        self.assertIn("lvTravelDocumenterMount", html)
        self.assertIn("js/travel-documenter.js", html)


class OperatorPathFramingTest(unittest.TestCase):
    """The operator path must read as the product, not as a trial."""

    def test_no_window_property_shadows_a_top_level_function(self):
        """ui/js/app.js is a classic script with no IIFE wrapper, so every
        top-level `function foo()` also defines `window.foo`. Assigning
        `window.foo = <anything else>` silently destroys the function; the
        call site fails later and somewhere else, which is how
        `_lvTravelDocSurface` shipped a self-clobbering cache and only blew
        up on the second tab open. Cheap to assert, expensive to debug.

        The function that motivated this test is gone as of Phase 4. The
        test stays: the hazard is app.js's shape, not that one symbol."""
        app = _stripped_app()
        declared = set(re.findall(r"^function ([A-Za-z_$][\w$]*)\s*\(",
                                  app, re.M))
        self.assertGreater(len(declared), 50,
                           "regex stopped matching app.js — fix the test, "
                           "not the assertion count")
        assigned = set(re.findall(r"\bwindow\.([A-Za-z_$][\w$]*)\s*=(?!=)",
                                  app))
        clash = sorted(declared & assigned)
        # A top-level function may legitimately re-export ITSELF
        # (`window.foo = foo;`), so only flag assignments of something else.
        real = [n for n in clash
                if not re.search(r"\bwindow\.%s\s*=\s*%s\s*;" % (n, n), app)]
        self.assertEqual(real, [],
                         "these window properties overwrite same-named "
                         "top-level functions in app.js: %r" % (real,))

    def test_the_lab_launcher_is_gone_from_the_shell(self):
        # WO-TRAVEL-DOC-LAB-LAUNCH-BUTTON-01's button opened a SECOND
        # browser tab, had no stylesheet anywhere in ui/ so it rendered as
        # unstyled text on the dark shell, and framed the workspace as a
        # side experiment. All three are the discoverability defect Phase
        # 2 closed and Phase 4 keeps closed.
        html = _stripped_shell_html()
        for banned in ("Open Travel Doc UI Lab", "lvTravelDocLabBtn",
                       "lv-td-lab-launch", "travel-doc-lab.html"):
            self.assertNotIn(banned, html,
                             f"shell still carries the Lab launcher: {banned}")

    def test_no_experimental_badge_on_the_shell_path(self):
        # Acceptance: no visible "UI Lab · experimental" in the main shell
        # path. The badge and the harness-only evaluation checklist must
        # both be gated on !embedded.
        src = _stripped_lab_js()
        m = re.search(r"if \(!embedded\) \{\s*\n\s*brand\.appendChild"
                      r"[\s\S]*?tdl-lab-badge", src)
        self.assertIsNotNone(m, "the UI Lab badge is not gated on !embedded")
        self.assertIn("if (!embedded) wrap.appendChild(renderEvalChecklist());",
                      src)

    def test_picker_copy_drops_lab_framing_when_embedded(self):
        src = _stripped_lab_js()
        self.assertIn('embedded ? "Travel Doc" : "Travel Doc UI Lab"', src)


class CssScopingTest(unittest.TestCase):
    """Requirements 8, 9 — scope to the host, keep the tdl- prefix."""

    def test_variables_live_on_the_host_not_on_root(self):
        css = _stripped_lab_css()
        self.assertIn(".tdl-root {", css)
        self.assertNotIn(":root {", css,
                         "custom properties must not be published globally")

    def test_no_bare_element_rules_escape_the_host(self):
        # A bare `button {` or `input, textarea {` in a sheet the shell
        # loads globally would restyle the whole Hornelore UI.
        checked = 0
        for ancestors, selector in _css_rules(_stripped_lab_css()):
            if selector.startswith("@"):
                continue
            if any(a.startswith("@keyframes") for a in ancestors):
                continue  # 0% / from / to are steps, not selectors
            for part in selector.split(","):
                part = part.strip()
                if not part:
                    continue
                checked += 1
                self.assertTrue(
                    part.startswith(".tdl-"),
                    f"unscoped Travel Doc rule leaks into the shell: {part}")
        # Guard the guard: a parser change that stopped finding selectors
        # would turn this into a test that passes by looking at nothing.
        self.assertGreater(checked, 200)

    def test_the_standalone_body_rule_is_the_only_tdl_body_rule(self):
        # .tdl-body never matches inside the shell (the shell owns <body>),
        # so anything the workspace NEEDS must not be keyed off it.
        css = _stripped_lab_css()
        body_rules = [ln.strip() for ln in css.splitlines()
                      if ln.strip().startswith(".tdl-body")]
        self.assertEqual(len(body_rules), 1,
                         f"unexpected .tdl-body rules: {body_rules}")

    def test_the_module_owns_the_host_class(self):
        # Applied by the module rather than the caller, so the standalone
        # page is scoped too without any page-side code to remember it.
        src = _stripped_lab_js()
        self.assertIn('root.classList.add("tdl-root")', src)
        self.assertIn('if (embedded) root.classList.add("tdl-root-embedded")',
                      src)

    def test_destroy_hands_the_host_back_unstyled(self):
        # A leftover .tdl-root would paint the module's cream page
        # background behind an empty host after teardown.
        src = _stripped_lab_js()
        self.assertIn('root.classList.remove("tdl-root", "tdl-root-embedded")',
                      src)

    def test_class_prefix_is_unchanged(self):
        # Requirement 9: keep the tdl- prefix, do not rename all classes.
        css = _stripped_lab_css()
        self.assertIn(".tdl-app", css)
        self.assertIn(".tdl-inspector", css)
        self.assertNotIn(".td-root", css)

    def test_embedded_variant_does_not_pin_overlays_to_the_viewport(self):
        # Standalone pins the narrow-screen inspector to the VIEWPORT 58px
        # down — the height of the harness page's own topbar. In the shell
        # that offset is meaningless and a fixed panel would cover the
        # Hornelore header and tab strip, taking away the operator's way
        # out of the tab. Embedded anchors it to the host instead.
        css = _stripped_lab_css()
        m = re.search(r"\.tdl-root-embedded \.tdl-inspector \{[^}]*position:"
                      r"\s*absolute", css)
        self.assertIsNotNone(
            m, "the embedded inspector overlay must be host-anchored")

    def test_shell_stylesheet_sizes_the_one_host(self):
        css = _SHELL_CSS.read_text(encoding="utf-8")
        self.assertIn("#lvTravelDocTab > .lv-td-host", css)

    def test_shell_stylesheet_dropped_the_two_surface_rules(self):
        # Comment-stripped: the Phase 4 replacement comment in lori80.css
        # explains what came out and legitimately names it.
        css = re.sub(r"/\*[\s\S]*?\*/", "",
                     _SHELL_CSS.read_text(encoding="utf-8"))
        for banned in (".lv-td-surface-switch", ".lv-td-surface-btn",
                       ".lv-td-surface-hint", ".lv-td-host-off",
                       "lv-td-focus"):
            self.assertNotIn(banned, css,
                             f"dead two-surface rule survives in lori80.css: "
                             f"{banned}")


class NoNativeDialogsTest(unittest.TestCase):
    """Acceptance: no native prompt/confirm/alert added."""

    def test_no_native_dialogs_in_the_travel_doc_shell_path(self):
        block = _traveldoc_block()
        app = _stripped_app()
        surface_fns = "".join(
            m.group(0) for m in re.finditer(
                r"(?:window\.)?_?lvTravelDoc\w*\s*=?\s*function[\s\S]*?\n\}?;?\n",
                app))
        for src in (block, surface_fns):
            for banned in ("window.prompt(", "window.confirm(",
                           "window.alert(", " prompt(", " confirm(",
                           " alert("):
                self.assertNotIn(banned, src,
                                 f"native dialog in the Travel Doc path: {banned}")

    def test_lab_module_still_has_no_native_dialogs(self):
        src = _stripped_lab_js()
        for banned in ("window.prompt(", "window.confirm(", "window.alert(",
                       " prompt(", " confirm(", " alert("):
            self.assertNotIn(banned, src)


class StandaloneStillWorksTest(unittest.TestCase):
    """Requirement 6 — keep the standalone harness, marked dev-only."""

    def test_harness_page_still_mounts_the_module(self):
        html = re.sub(r"<!--[\s\S]*?-->", "",
                      _LAB_HTML.read_text(encoding="utf-8"))
        self.assertIn("lvTravelDocMount(", html)
        self.assertIn('id="tdlRoot"', html)
        self.assertIn("css/travel-doc-lab.css", html)
        self.assertIn("js/travel-doc-lab.js", html)

    def test_harness_page_does_not_pass_embedded(self):
        # embedded:true is the SHELL's flag. If the standalone page set it
        # too, the page would lose its own branding and, worse, its
        # ?person_id= contract — the only way to scope the harness.
        html = _LAB_HTML.read_text(encoding="utf-8")
        self.assertNotIn("embedded", html)

    def test_harness_page_keeps_its_body_class(self):
        html = _LAB_HTML.read_text(encoding="utf-8")
        self.assertIn('class="tdl-body"', html)

    def test_harness_page_is_marked_dev_only(self):
        # Requirement 6: keep it only if still needed as a dev harness, or
        # explicitly mark it as dev-only. It is kept AND marked — it is the
        # only caller of lvTravelDocMount() that exercises the non-embedded
        # branch, so deleting it would leave that branch untested.
        html = _LAB_HTML.read_text(encoding="utf-8")
        self.assertIn("DEV-ONLY", html)
        self.assertIn("DEV HARNESS", html)
        # ...and it must not still describe the shell's Travel Doc as
        # something it is not part of, or name a host that no longer exists.
        self.assertNotIn("lvTravelDocHost", html)
        self.assertNotIn("travel-documenter", html)


if __name__ == "__main__":
    unittest.main()
