"""WO-TRAVEL-DOC-UNIFY-01 Phase 2 — shell coexistence gate.

Phase 2 mounts the (now mountable) Travel Doc workspace inside the main
Hornelore Travel Doc tab while the legacy Documenter stays reachable
behind a temporary comparison toggle. That creates exactly one new class
of defect worth a build gate, and it is not async liveness — Phase 1.1
closed that. It is:

  1. CSS LEAKAGE. The Lab's stylesheet was written for a standalone page
     that owned <body>. Loaded by hornelore1.0.html it would publish its
     custom properties globally and its element resets would either miss
     the workspace or repaint the dark shell. Every rule must hang off
     .tdl-root, the class the module puts on its own host.

  2. TWO LIVE TRAVEL DOC SURFACES. Each surface owns a BroadcastChannel
     subscription, a document-level keydown listener and a Lori socket.
     Two mounts means two of each, and both keydown handlers answering
     Escape. The shell must destroy before it mounts, on every path that
     can reach a mount: surface toggle, narrator switch, tab exit.

Everything else here is acceptance-criteria lockdown: the shell supplies
identity (never the querystring), the Lab's "experimental" self-branding
must not appear on the operator path, the standalone harness must keep
working, and no native prompt/confirm/alert may sneak in.
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


class ShellLoadsTheModuleTest(unittest.TestCase):
    """Requirement 2 — load the mountable Travel Doc module and CSS."""

    def test_shell_loads_the_lab_script_and_stylesheet(self):
        html = _stripped_shell_html()
        self.assertRegex(html, r'src="js/travel-doc-lab\.js')
        self.assertRegex(html, r'href="css/travel-doc-lab\.css')

    def test_lab_stylesheet_loads_before_the_shell_stylesheet(self):
        # lori80.css owns the Travel Doc host sizing and the surface
        # switch. It must be able to win a specificity tie against the
        # Lab sheet, which means it has to come second.
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

    def test_tab_has_a_dedicated_unified_host(self):
        html = _stripped_shell_html()
        self.assertIn('id="lvTravelDocUnifiedHost"', html)
        # ...alongside, not instead of, the legacy host (non-goal: "do not
        # remove the old Documenter yet").
        self.assertIn('id="lvTravelDocHost"', html)

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

    def test_the_legacy_handle_is_stored_too(self):
        # Pre-existing leak closed by Phase 2: travel-documenter.js always
        # returned a handle with destroy(); the shell threw it away, so
        # every narrator switch leaked a keydown listener and a socket.
        block = _traveldoc_block()
        self.assertIn("window._lvTravelDocLegacyHandle = lvTravelDocumenterMount(",
                      block)

    def test_both_destroyers_call_destroy_on_the_handle(self):
        app = _stripped_app()
        for fn in ("_lvTravelDocDestroyUnified", "_lvTravelDocDestroyLegacy"):
            m = re.search(r"function " + fn + r"\(\) \{[\s\S]*?\n\}", app)
            self.assertIsNotNone(m, f"{fn} missing from app.js")
            body = m.group(0)
            self.assertIn('typeof h.destroy === "function"', body)
            self.assertIn("h.destroy()", body)
            # Teardown must never throw — a caller swapping surfaces would
            # be left with a half-destroyed mount and no way to recover.
            self.assertIn("try {", body)


class OnlyOneSurfaceIsEverLiveTest(unittest.TestCase):
    """The Phase 2 top risk, gated on every path that reaches a mount."""

    def test_showing_the_tab_destroys_the_other_surface(self):
        block = _traveldoc_block()
        self.assertIn('if (_tdSurface === "unified") _lvTravelDocDestroyLegacy();',
                      block)
        self.assertIn("else _lvTravelDocDestroyUnified();", block)

    def test_remount_destroys_before_it_mounts(self):
        # Requirement 4: destroy() before remounting. A narrator change
        # takes this path, and remounting over a live mount is the second
        # way to end up with two of everything.
        block = _traveldoc_block()
        mount_at = block.index("window.lvTravelDocMount(host, {")
        destroy_at = block.rindex("_lvTravelDocDestroyUnified();", 0, mount_at)
        self.assertLess(destroy_at, mount_at)

    def test_switching_surface_tears_both_down_first(self):
        app = _stripped_app()
        m = re.search(r"window\.lvTravelDocSetSurface = function[\s\S]*?\n\};", app)
        self.assertIsNotNone(m, "lvTravelDocSetSurface missing from app.js")
        body = m.group(0)
        teardown_at = body.index("window.lvTravelDocTeardownAll();")
        remount_at = body.index('lvShellShowTab("traveldoc")')
        self.assertLess(teardown_at, remount_at)

    def test_leaving_the_tab_tears_both_down(self):
        # A hidden shell panel is display:none, not unloaded. Without this
        # the operator navigating to Media left a live keydown listener,
        # BroadcastChannel and Lori socket under the tab they were looking
        # at.
        app = _stripped_app()
        m = re.search(r'if \(tabName !== "traveldoc"\) \{[\s\S]*?\n  \}', app)
        self.assertIsNotNone(m)
        self.assertIn("window.lvTravelDocTeardownAll()", m.group(0))

    def test_narrator_switch_tears_both_down(self):
        html = _stripped_shell_html()
        m = re.search(r"async function lv80SwitchPerson[\s\S]{0,1600}", html)
        self.assertIsNotNone(m)
        self.assertIn("window.lvTravelDocTeardownAll()", m.group(0))

    def test_teardown_covers_both_surfaces(self):
        app = _stripped_app()
        m = re.search(r"window\.lvTravelDocTeardownAll = function[\s\S]*?\n\};", app)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("_lvTravelDocDestroyUnified();", body)
        self.assertIn("_lvTravelDocDestroyLegacy();", body)

    def test_no_narrator_selected_destroys_rather_than_hides(self):
        # Deselecting leaves the empty-state message. If the previous
        # narrator's mount merely sat underneath it, its socket would stay
        # bound to a narrator the operator has navigated away from.
        block = _traveldoc_block()
        m = re.search(r"if \(!pid\) \{[\s\S]*?Choose a narrator first", block)
        self.assertIsNotNone(m, "empty-state arm missing from the mount block")
        arm = m.group(0)
        self.assertIn("_lvTravelDocDestroyUnified()", arm)
        self.assertIn("_lvTravelDocDestroyLegacy()", arm)

    def test_hiding_a_host_is_never_the_only_teardown(self):
        # The visual half of the switch lives in its own function, and
        # that function must not be mistaken for a teardown: it may toggle
        # classes and aria state, and must not be the thing that "removes"
        # a mount.
        app = _stripped_app()
        m = re.search(r"function _lvTravelDocPaintSurfaceChrome\(surface\) \{"
                      r"[\s\S]*?\n\}", app)
        self.assertIsNotNone(m)
        body = m.group(0)
        self.assertIn("lv-td-host-off", body)
        for banned in ("lvTravelDocMount", "lvTravelDocumenterMount",
                       "innerHTML"):
            self.assertNotIn(banned, body,
                             "the surface-chrome painter must stay presentational")


class DefaultSurfaceTest(unittest.TestCase):
    """Requirements 5, 6, 7 — unified by default, legacy still reachable,
    no Lab framing on the operator path."""

    def test_default_surface_is_the_unified_workspace(self):
        app = _stripped_app()
        m = re.search(r"function _lvTravelDocSurface\(\) \{[\s\S]*?\n\}", app)
        self.assertIsNotNone(m)
        body = m.group(0)
        # Anything that is not the literal "legacy" resolves to unified,
        # so a corrupt or absent stored value lands on the default path
        # rather than on the fallback.
        self.assertIn('(s === "legacy") ? "legacy" : "unified"', body)

    def test_no_window_property_shadows_a_top_level_function(self):
        """ui/js/app.js is a classic script with no IIFE wrapper, so every
        top-level `function foo()` also defines `window.foo`. Assigning
        `window.foo = <anything else>` silently destroys the function; the
        call site fails later and somewhere else, which is how
        `_lvTravelDocSurface` shipped a self-clobbering cache and only blew
        up on the second tab open. Cheap to assert, expensive to debug."""
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

    def test_markup_defaults_to_unified_and_hides_legacy(self):
        html = _stripped_shell_html()
        m = re.search(r'<div class="lv-td-surface-switch">[\s\S]*?</section>', html)
        self.assertIsNotNone(m, "surface switch row missing from the tab")
        panel = m.group(0)
        self.assertRegex(
            panel,
            r'data-td-surface="unified"\s*\n?\s*aria-pressed="true"')
        self.assertRegex(
            panel,
            r'data-td-surface="legacy"\s*\n?\s*aria-pressed="false"')
        # The legacy host ships hidden; the unified one does not.
        self.assertRegex(panel, r'id="lvTravelDocHost"[^>]*lv-td-host-off')
        self.assertNotRegex(panel,
                            r'id="lvTravelDocUnifiedHost"[^>]*lv-td-host-off')

    def test_legacy_is_still_reachable(self):
        # Non-goal for Phase 2: "Do not remove the old Documenter yet."
        html = _stripped_shell_html()
        self.assertIn("lvTravelDocSetSurface('legacy')", html)
        self.assertRegex(html, r'src="js/travel-documenter\.js')

    def test_the_lab_launcher_is_gone_from_the_shell(self):
        # WO-TRAVEL-DOC-LAB-LAUNCH-BUTTON-01's button opened a SECOND
        # browser tab, had no stylesheet anywhere in ui/ so it rendered as
        # unstyled text on the dark shell, and framed the workspace as a
        # side experiment. All three are the discoverability defect Phase
        # 2 closes.
        html = _stripped_shell_html()
        for banned in ("Open Travel Doc UI Lab", "lvTravelDocLabBtn",
                       "lv-td-lab-launch", "travel-doc-lab.html"):
            self.assertNotIn(banned, html,
                             f"shell still carries the Lab launcher: {banned}")

    def test_no_experimental_badge_on_the_shell_path(self):
        # Acceptance: no visible "UI Lab · experimental" in the main shell
        # path. The badge and the lab-only evaluation checklist must both
        # be gated on !embedded.
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
        # The shell reuses hosts across surfaces; a leftover .tdl-root
        # would paint the Lab's cream page background behind whatever
        # mounts next.
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
        # down — the height of the Lab's own topbar. In the shell that
        # offset is meaningless and a fixed panel would cover the Hornelore
        # header and tab strip, taking away the operator's way out of the
        # tab. Embedded anchors it to the host instead.
        css = _stripped_lab_css()
        m = re.search(r"\.tdl-root-embedded \.tdl-inspector \{[^}]*position:"
                      r"\s*absolute", css)
        self.assertIsNotNone(
            m, "the embedded inspector overlay must be host-anchored")

    def test_shell_stylesheet_sizes_the_unified_host(self):
        css = _SHELL_CSS.read_text(encoding="utf-8")
        self.assertIn("#lvTravelDocTab > .lv-td-host", css)
        self.assertIn("#lvTravelDocTab > .lv-td-host-off { display: none; }",
                      css)
        self.assertIn(".lv-td-surface-switch", css)


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
    """Acceptance: standalone travel-doc-lab.html still works."""

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


if __name__ == "__main__":
    unittest.main()
