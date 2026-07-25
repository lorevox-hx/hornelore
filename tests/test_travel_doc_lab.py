"""WO-TRAVEL-DOC-UI-LAB-01 — boundary gate for the Travel Doc module.

This file started as the gate for an experimental, removable redesign
surface sitting beside the shipped Travel Documenter. WO-TRAVEL-DOC-
UNIFY-01 turned that experiment into the product: Phases 3A-3D ported
the force-delete gate, trip/region/stop CRUD, upload/source/cluster and
route ordering into it, and Phase 4 unmounted the older Documenter from
the shell. ui/js/travel-doc-lab.js and ui/css/travel-doc-lab.css are now
the operator's only Travel Doc; only ui/travel-doc-lab.html is still a
removable dev harness. (The file names still say "lab" because renaming
a 3,400-line module is churn that would bury a real diff — that rename
is parked, not forgotten.)

The tests still FAIL THE BUILD if this surface leaks into narrator or
Travels-shelf state, loads the older Travel Doc module, calls an
unsanctioned endpoint, or drops its tdl- namespace. The older module
(ui/js/travel-documenter.js) cannot be guarded byte-for-byte from a
test, so we lock this side: it must not import or script-load that one.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

try:
    from tests import source_scan_helpers as _ssh
except ImportError:  # direct execution: python tests/test_travel_doc_lab.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import source_scan_helpers as _ssh

_REPO_ROOT = Path(__file__).resolve().parent.parent
_JS = _REPO_ROOT / "ui" / "js" / "travel-doc-lab.js"
_CSS = _REPO_ROOT / "ui" / "css" / "travel-doc-lab.css"
_HTML = _REPO_ROOT / "ui" / "travel-doc-lab.html"


def _stripped_js() -> str:
    # WO-POST-REVIEW-SAFETY-DRAFT-EXPORT-HARDENING-01 Phase 6.4: the old
    # re.sub(r"/\*[\s\S]*?\*/|//[^\n]*") stripper treated the "//" inside
    # string literals like "http://localhost:8000" (travel-doc-lab.js:40)
    # as a line comment, blinding every banned-token scan below from
    # there to end-of-line. The shared string-aware scanner removes real
    # comments only; string/template/regex contents stay visible.
    js = _JS.read_text(encoding="utf-8")
    return _ssh.strip_js_comments(js)


def _destroy_body() -> str:
    # Phase 1.1: slice the actual destroy() body rather than a fixed-width
    # window. A fixed window silently stops covering the last teardown step
    # the moment a step is added, which turns an ordering pin into a
    # "substring not found" error instead of a real failure.
    src = _stripped_js()
    i = src.index("destroy: function ()")
    end = src.index("\n    }", i)
    return src[i:end]


def _stripped_css() -> str:
    css = _CSS.read_text(encoding="utf-8")
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def _stripped_html() -> str:
    html = _HTML.read_text(encoding="utf-8")
    return re.sub(r"<!--[\s\S]*?-->", "", html)


class LabFilesExistTest(unittest.TestCase):
    def test_all_three_lab_files_exist(self):
        for p in (_JS, _CSS, _HTML):
            self.assertTrue(p.exists(), f"missing lab file: {p}")

    def test_the_harness_page_is_the_removable_one(self):
        # This gate used to require all three files to say REMOVABLE,
        # because all three WERE — the lab was an experiment sitting
        # beside a separate operator Travel Doc, and the marker told the
        # next reader they could delete the whole set.
        #
        # WO-TRAVEL-DOC-UNIFY-01 Phase 4 inverted that for two of them.
        # The shell now mounts travel-doc-lab.js, styled by
        # travel-doc-lab.css, as the operator's only Travel Doc. Deleting
        # those two would delete the Travel Doc tab. Keeping the old
        # assertion would have kept a delete-me sign nailed to
        # load-bearing code, so the gate now pins the true split: the
        # harness PAGE is removable and says so; the two modules are not,
        # and must not claim to be.
        html = _HTML.read_text(encoding="utf-8")
        self.assertIn("REMOVABLE", html,
                      "the dev harness page must declare itself removable")
        self.assertIn("DEV-ONLY", html,
                      "the dev harness page must declare itself dev-only")
        for p in (_JS, _CSS):
            self.assertNotIn(
                "REMOVABLE", p.read_text(encoding="utf-8"),
                f"{p.name} IS the operator Travel Doc since Phase 4 — it "
                f"must not carry a removable marker")


class BoundaryTest(unittest.TestCase):
    def test_lab_never_touches_narrator_or_shelf_state(self):
        # Same posture as the production panel gate, applied to the lab:
        # no narrator-session scope, no runtime71, no Travels shelf, no
        # system-prompt dispatch. Checked on comment-stripped source.
        src = _stripped_js()
        for banned in ("runtime71", "state.session", "travelsShelfOpen",
                       "activeTripId", "activeTripStopId", "tripStyle",
                       "sendSystemPrompt", "wo9SendOrQueueSystemPrompt",
                       "lvTravelsOpenTripById"):
            self.assertNotIn(banned, src,
                             f"travel-doc-lab must not reference {banned}")

    def test_lab_does_not_import_production_module(self):
        # Deep-linking to the standalone travel-documenter.html page is
        # sanctioned (existing flows); loading its JS/CSS is not.
        # Comment-stripped: the docs comments explaining the boundary
        # are allowed to NAME the production files; code may not.
        src = _stripped_js()
        self.assertNotIn("travel-documenter.js", src)
        self.assertNotIn("travel-documenter.css", src)
        self.assertNotIn("lvTravelDocumenterMount", src)
        self.assertNotIn("travel-documenter", _stripped_css())

    def test_endpoints_are_a_subset_of_the_sanctioned_api(self):
        src = _stripped_js()
        allowed = ("/api/trips", "/api/photos/", "/api/people",
                   "/api/chat/ws")
        for m in re.finditer(r'"(/api/[^"]*)"', src):
            path = m.group(1)
            self.assertTrue(
                any(path.startswith(a) for a in allowed),
                f"unsanctioned endpoint in travel-doc-lab.js: {path}")
        # And the sanctioned surfaces are actually exercised.
        for required in ("/api/trips", "/api/people", "/api/chat/ws"):
            self.assertIn('"' + required, src.replace("' ", '"'))

    def test_lori_pane_uses_modal_surface_and_day_scope(self):
        src = _stripped_js()
        self.assertIn("travel_doc_modal", src)
        self.assertIn("modal_scope", src)
        self.assertIn("active_trip_day_id", src)
        self.assertIn("turn_id", src)


class NamespaceTest(unittest.TestCase):
    def test_css_is_tdl_namespaced(self):
        css = _CSS.read_text(encoding="utf-8")
        # No production .td- classes may be reused (`.td-` followed by
        # anything but the lab's own l).
        self.assertIsNone(re.search(r"\.td-[^l]", css),
                          "lab CSS reuses a production .td- class")
        self.assertIn(".tdl-", css)

    def test_js_classes_are_tdl_namespaced(self):
        src = _stripped_js()
        self.assertIsNone(re.search(r"""["'][^"']*\btd-""", src),
                          "lab JS uses a non-tdl td- class string")
        self.assertIn("tdl-", src)


class HtmlPageTest(unittest.TestCase):
    def test_page_loads_only_lab_assets(self):
        html = _stripped_html()
        self.assertIn("css/travel-doc-lab.css", html)
        self.assertIn("js/travel-doc-lab.js", html)
        self.assertNotIn("travel-documenter.js", html)
        self.assertNotIn("travel-documenter.css", html)
        self.assertNotIn("app.js", html)
        self.assertNotIn("lori80.css", html)
        # Exactly one stylesheet, and exactly one EXTERNAL script — the
        # lab's own. WO-TRAVEL-DOC-UNIFY-01 Phase 1 deliberately relaxed
        # this from "one <script> tag" to "one <script src=>": the page
        # is now a harness, so it carries a second, inline script whose
        # only job is to call the mount. The property this test exists
        # to protect is "no foreign assets", not "no inline code".
        self.assertEqual(len(re.findall(r"<link\b", html)), 1)
        srcs = re.findall(r'<script\b[^>]*\bsrc="([^"]+)"', html)
        self.assertEqual(srcs, ["js/travel-doc-lab.js"])

    def test_page_mounts_the_lab_root(self):
        html = _HTML.read_text(encoding="utf-8")
        self.assertIn('id="tdlRoot"', html)
        self.assertIn('class="tdl-body"', html)


class MountContractTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UNIFY-01 Phase 1 — the lab is a mountable module.

    The lab used to be a page-level IIFE that booted itself on load and
    grabbed #tdlRoot out of the document. It is now
    window.lvTravelDocMount(hostEl, opts) -> {destroy()}, so the shell
    can mount it into #lvTravelDocHost and the standalone page becomes
    one caller among two rather than the only entry point.
    """

    def test_module_exposes_the_mount_entry_point(self):
        src = _stripped_js()
        self.assertIn("window.lvTravelDocMount = function (hostEl, opts)", src)

    def test_host_element_comes_from_the_caller(self):
        # The getElementById fallback may stay, but the caller's hostEl
        # must win — otherwise a shell mount silently renders into the
        # standalone page's root, or nothing at all.
        src = _stripped_js()
        self.assertIn('var root = hostEl || document.getElementById("tdlRoot")',
                      src)

    def test_module_does_not_boot_itself_at_page_scope(self):
        # boot() must be called from INSIDE the mount body. A bare
        # page-scope boot() would fire on script load with no host and
        # defeat the point of the mount.
        src = _stripped_js()
        self.assertNotIn("\n  boot();\n})();", src)

    def test_opts_are_preferred_over_the_querystring(self):
        # The querystring stays the STANDALONE page's contract, but opts
        # must take precedence or the shell cannot select a narrator.
        #
        # WO-TRAVEL-DOC-UNIFY-01 Phase 2 tightened this from "opts win" to
        # "embedded mounts do not read the querystring at all". Precedence
        # alone stopped being enough once the module mounts inside
        # hornelore1.0.html, because that page can carry a ?person_id=
        # from any other launcher: whenever the shell passed no person_id
        # (no narrator selected, or mid-switch) the old chain fell through
        # to the shell URL and mounted Travel Doc against a narrator the
        # header, the Travels shelf and every other tab disagreed with —
        # silent cross-narrator writes. Embedded identity comes from opts
        # or it does not come at all.
        src = _stripped_js()
        for field in ('opts.apiBase || (embedded ? "" : qsParams.get("api"))',
                      "opts.person_id ||",
                      '(embedded ? "" : qsParams.get("person_id"))'):
            self.assertIn(field, src)

    def test_mount_returns_a_destroy_handle_that_closes_the_channel(self):
        # Amendment A1. "hornelore-trip-updates" is a NAMED channel, so
        # a leaked mount means a duplicate subscription and a double
        # refresh on every cross-tab save. destroy() must close it, drop
        # the Lori socket, and clear the host.
        src = _stripped_js()
        self.assertIn("destroy: function ()", src)
        self.assertIn("_tdlUpdateChannel.close()", src)
        self.assertIn("loriPane.reset()", src)

    def test_harness_page_calls_the_mount(self):
        html = _stripped_html()
        self.assertIn("lvTravelDocMount(", html)
        self.assertIn("tdlRoot", html)


class MountLivenessTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UNIFY-01 Phase 1.1 — nothing paints a dead mount.

    Phase 1's destroy() closed the channel, reset Lori, and cleared the
    host, but held no liveness state. Every async flow in this module
    (boot, loadTrips, loadTripBundle, evidence reloads, travelogue
    preview, the Lori drawer refresh) resolves on its own schedule, so a
    request in flight at teardown still ran its callback: it wrote to
    `st` and repainted a host the caller had already cleared and may
    have handed to something else. That only surfaces when panels are
    swapped, which is precisely what Phase 2 introduces — so it is
    pinned here, before the shell mount, not after.

    The guard is cheap because the module has exactly one of each thing
    worth guarding. These tests pin all six choke points; if a future
    change adds a second fetch() or a second repaint entry point, the
    coverage assertion below fails and this class has to be revisited.
    """

    def _mount_body(self) -> str:
        src = _stripped_js()
        i = src.index("window.lvTravelDocMount = function (hostEl, opts)")
        return src[i:]

    def test_mount_declares_a_liveness_flag(self):
        # Per mount, inside the closure — a module-level flag would be
        # shared by every mount and one destroy() would kill them all.
        body = self._mount_body()
        self.assertIn("var destroyed = false;", body)
        self.assertNotIn(
            "window.destroyed", body,
            "the liveness flag must not be global",
        )

    def test_destroy_sets_the_flag_before_anything_else(self):
        # Ordering is the whole point. Each teardown step below can run
        # script that re-enters the module (a close handler, a rejected
        # fetch settling at the next microtask checkpoint), so the flag
        # has to be up before the first one runs. Closing the door and
        # then flipping the sign leaves a window open.
        head = _destroy_body()
        first = head.index("destroyed = true;")
        for later in ("removeEventListener", "_tdlUpdateChannel",
                      "loriPane.reset()", "root.textContent"):
            self.assertIn(
                later, head,
                f"destroy() no longer performs the {later} teardown step",
            )
            self.assertLess(
                first, head.index(later),
                f"destroy() touches {later} before setting destroyed",
            )

    def test_render_entry_point_no_ops_when_destroyed(self):
        # renderAll() is the only repaint entry point in the file: every
        # render* function is reached through it. One early return here
        # means a dead mount cannot paint regardless of the caller.
        src = _stripped_js()
        i = src.index("function renderAll()")
        head = src[i:i + 200]
        self.assertIn("if (destroyed) return;", head)
        # ...and it must come before the host is touched.
        self.assertLess(head.index("if (destroyed) return;"),
                        head.index("root."))

    def test_there_is_still_exactly_one_repaint_entry_point(self):
        # The guard above is only total coverage while this holds.
        src = _stripped_js()
        self.assertEqual(
            len(re.findall(r"\broot\.innerHTML\s*=", src)), 2,
            "root.innerHTML assignments moved; renderAll() and "
            "renderPersonPicker() were the only two — a third needs its "
            "own destroyed guard",
        )

    def test_the_only_fetch_is_guarded_on_every_arm(self):
        # api() wraps the file's single fetch(). The mount can die at
        # three moments — before the request goes out, in flight, and
        # while an error body is being read — and the REJECTION arm
        # matters as much as the success arm, because nearly every call
        # site ends in .catch(e => { st.error = e.message; renderAll() }),
        # which is itself a write to dead state.
        src = _stripped_js()
        self.assertEqual(
            len(re.findall(r"\bfetch\(", src)), 1,
            "a second fetch() appeared; it needs its own destroyed guard",
        )
        i = src.index("function api(path, opts)")
        body = src[i:src.index("function el(tag, cls, text)", i)]
        self.assertGreaterEqual(
            len(re.findall(r"if \(destroyed\) return abandoned\(\);", body)), 4,
            "api() must bail on call, on response, on error-body read, "
            "and on rejection",
        )
        # The rejection arm specifically: a two-arg then(), not a bare
        # .then() that only covers success.
        self.assertIn("}, function (err) {", body)

    def test_abandoned_promise_never_settles(self):
        # Returning a rejected promise would fire every call site's
        # .catch(); returning a resolved one would fire its .then(). The
        # only shape that runs neither is a promise that never settles.
        src = _stripped_js()
        i = src.index("function abandoned()")
        head = src[i:i + 120]
        self.assertIn("new Promise(function () {})", head)
        self.assertNotIn("resolve", head)
        self.assertNotIn("reject", head)

    def test_broadcast_channel_handler_bails_when_destroyed(self):
        # close() does not retract message events already queued on the
        # task queue.
        src = _stripped_js()
        i = src.index('_tdlUpdateChannel.addEventListener("message"')
        head = src[i:i + 200]
        self.assertIn("if (destroyed) return;", head)

    def test_lori_socket_message_bails_when_destroyed_or_after_reset(self):
        # Identity comparison against the socket the handler was bound
        # to covers BOTH cases: destroy(), and reset() on a trip switch
        # (which nulls this.ws while the old socket may still deliver a
        # frame). Without it a Trip A token can append into Trip B's
        # transcript.
        src = _stripped_js()
        i = src.index("connect: function ()")
        body = src[i:i + 1200]
        self.assertIn("var sock = this.ws;", body)
        self.assertIn("if (destroyed || self.ws !== sock) return;", body)
        # connect() itself must refuse to open a socket for a dead mount.
        self.assertIn("if (destroyed) return;", body)

    def test_lori_send_retry_timer_stops_at_destroy(self):
        # The file's only timer. Unguarded it keeps retrying for up to
        # 5s (20 x 250ms) past teardown and signs off by writing into a
        # log node that is no longer in the document.
        src = _stripped_js()
        self.assertEqual(
            len(re.findall(r"\bsetTimeout\(|\bsetInterval\(", src)), 1,
            "a second timer appeared; it needs its own destroyed guard",
        )
        i = src.index("function trySend(attempt)")
        head = src[i:i + 160]
        self.assertIn("if (destroyed) return;", head)

    def test_document_level_listener_is_named_and_unbound_on_destroy(self):
        # This is the only listener bound outside the host element, so
        # it is the only one clearing the host does not take with it.
        # Left attached it outlives the mount forever: two mounts means
        # two live listeners on `document`, and after destroy() an arrow
        # key would still drive lightboxStep() into renderAll().
        src = _stripped_js()
        self.assertEqual(
            len(re.findall(r"document\.addEventListener\(", src)), 1,
            "a second document-level listener appeared; it needs "
            "unbinding in destroy()",
        )
        self.assertIn('document.addEventListener("keydown", onDocKeydown)', src)
        self.assertIn(
            'document.removeEventListener("keydown", onDocKeydown)', src)
        # Guarded as well — removeEventListener does not retract an
        # event already queued.
        i = src.index("function onDocKeydown(e)")
        self.assertIn("if (destroyed) return;", src[i:i + 120])

    def test_destroy_remains_idempotent_and_cannot_throw(self):
        # Unchanged from A1 and re-pinned here, because Phase 1.1 added
        # a step to destroy(): every statement that touches something
        # external stays individually try/caught. A teardown that throws
        # strands a caller mid-swap with a half-dead mount.
        src = _stripped_js()
        i = src.index("destroy: function ()")
        body = src[i:src.index("};", src.index("root.textContent", i))]
        for step in ("document.removeEventListener", "_tdlUpdateChannel.close()",
                     "loriPane.reset()", "root.textContent"):
            j = body.index(step)
            self.assertIn(
                "try {", body[max(0, j - 90):j],
                f"destroy() step {step} is not individually guarded",
            )

    def test_the_behavioural_proof_ships_alongside_the_guards(self):
        # Everything above this line reads source text. None of it can
        # watch a stale callback land on a dead host — that takes a real
        # browser, and it lives in the headless script below. Pinning the
        # script's existence and its four scenario names keeps the static
        # pins from staying green while the behaviour goes unverified.
        p = _REPO_ROOT / "scripts" / "ui" / "run_travel_doc_mount_liveness.js"
        self.assertTrue(
            p.is_file(),
            "the Phase 1.1 headless liveness proof is missing; the static "
            "pins in this class only check shape, not behaviour",
        )
        src = p.read_text(encoding="utf-8")
        for scenario in ("control_live", "destroyed_then",
                         "destroyed_notok", "destroyed_reject"):
            self.assertIn(
                scenario, src,
                f"the {scenario} scenario is gone from the liveness proof",
            )
        # control_live is the row that makes the other three mean
        # anything: three empty hosts also happen when the harness never
        # delivers a callback at all.
        self.assertIn("control repaints a live host", src)


class UsabilityReviewTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UI-LAB-02 — Chris's 2026-07-10 laptop review fixes.

    Locks the ten-item verdict: save without hunting, add photos to THAT
    day in-lab, Lori stays scoped to the day with an obvious way back,
    and no crowded horizontal layout on laptop widths.
    """

    def test_sticky_save_with_top_action_row_and_dirty_badge(self):
        src = _stripped_js()
        # Save Day exists at BOTH ends of the inspector (top action row
        # + sticky footer) and dirty-state gates it.
        self.assertIn("tdl-ins-actions", src)
        self.assertIn("tdl-inspector-footer", src)
        self.assertIn("Unsaved changes", src)
        self.assertIn("Save Day", src)
        self.assertIn("Cancel", src)
        self.assertIn('"Escape"', src)
        css = _stripped_css()
        self.assertIn(".tdl-dirty-badge", css)
        self.assertIn(".tdl-inspector-footer", css)
        self.assertIn("sticky", css)

    def test_no_navigation_away_from_the_lab(self):
        # The old "+ Photos" / "+ Add note" buttons deep-linked to the
        # production Travel Documenter page via window.open — gone. The
        # only remaining production reference is the sanctioned <a> link
        # on the Current tab.
        src = _stripped_js()
        self.assertNotIn("window.open", src)

    def test_in_lab_day_photo_picker(self):
        src = _stripped_js()
        self.assertIn("tdl-photo-picker", src)
        self.assertIn("/photos/link", src)
        self.assertIn("/photos/unlink", src)
        self.assertIn("photo_link_ids", src)
        self.assertIn("Attach photos", src)
        self.assertIn("Attach existing trip photos", src)
        self.assertIn("Unlink", src)
        # Day attachment is first-class in the link rows.
        self.assertIn("trip_day_id", src)

    def test_photo_picker_attach_vs_move_is_explicit(self):
        # 2026-07-10 review fix 3: links already attached to ANOTHER day
        # are never silently reassigned. Per-row labels split Attach vs
        # Move, the confirm button carries both counts, and a one-line
        # inline notice replaces any native confirm() dialog.
        src = _stripped_js()
        self.assertIn("Move to this day", src)
        self.assertIn('"Attach"', src)
        self.assertIn("Attach \" + c.attach + \" · Move \" + c.move", src)
        self.assertIn("will move from other days.", src)
        self.assertIn("on Day ", src)
        self.assertIn("tdl-move-notice", src)
        self.assertNotIn("confirm(", src.replace("paintAttach(", ""))
        css = _stripped_css()
        self.assertIn(".tdl-move-notice", css)
        self.assertIn(".tdl-picker-action", css)

    def test_gps_wording_uses_two_surface_doctrine(self):
        # 2026-07-10 review fix 2: Travel Doc is the evidence-rich
        # operator surface. "(private)" GPS phrasing is narrator-room
        # language and is banned here.
        src = _stripped_js()
        self.assertNotIn("GPS on file (private)", src)
        self.assertIn("GPS found — available for Travel Doc context", src)

    def test_in_lab_day_note_drawer(self):
        src = _stripped_js()
        self.assertIn("tdl-note-drawer", src)
        self.assertIn("Add note", src)
        self.assertIn("/location-notes", src)

    def test_lori_opens_as_in_context_drawer_with_back_control(self):
        src = _stripped_js()
        self.assertIn("tdl-lori-overlay", src)
        self.assertIn("Back to Trip Plan", src)
        # Day chip + scope line stay visible in the overlay.
        self.assertIn("active_trip_day_id", src)
        self.assertIn("Unanchor day", src)

    def test_photo_lori_opens_overlay_drawer_not_tab(self):
        # 2026-07-10 review fix 1: "Talk with Lori about this photo"
        # opens the SAME in-context overlay drawer the day cards use.
        # The photo action must never tab-navigate to the Lori tab.
        src = _stripped_js()
        self.assertNotIn('setTab("lori")', src)
        self.assertIn("openLoriOverlayForPhoto", src)
        # Context-aware back label: photos return to Photos, day cards
        # return to Trip Plan.
        self.assertIn("Back to Photos", src)
        self.assertIn("loriReturnTab", src)
        # Photo chip stays visible in the overlay.
        self.assertIn("Unanchor photo", src)
        self.assertIn("active_photo_link_id", src)

    def test_day_card_actions_are_full_labels_in_one_order(self):
        src = _stripped_js()
        # One consistent action row builder used everywhere.
        self.assertIn("dayActionRow", src)
        for label in ("Talk with Lori", "Attach photos", "Add note",
                      "Edit day"):
            self.assertIn(label, src)
        # Order locked: Talk with Lori, then Attach photos, then Add
        # note, then Edit day, inside the shared builder.
        i = src.index("function dayActionRow")
        block = src[i:i + 700]
        pos = [block.index("Talk with Lori"), block.index("Attach photos"),
               block.index("Add note"), block.index("Edit day")]
        self.assertEqual(pos, sorted(pos), "day action order drifted")

    def test_compact_laptop_layout_rules(self):
        css = _stripped_css()
        self.assertIn("@media (max-width: 1500px)", css)
        # The workspace column must be minmax(0, 1fr) so 1280-1500px
        # widths never horizontal-scroll.
        self.assertIn("minmax(0, 1fr)", css)
        self.assertNotIn("minmax(520px", css)
        self.assertNotIn("minmax(460px", css)
        # Left rail collapse + inspector drawer + drawer chrome exist.
        self.assertIn(".tdl-rail-collapsed", css)
        self.assertIn(".tdl-drawer", css)
        js = _stripped_js()
        self.assertIn("railCollapsed", js)

    def test_inspector_sections_are_collapsible(self):
        src = _stripped_js()
        self.assertIn("tdl-ins-sec", src)
        for section in ("Overview", "Notes", "Photos", "Sources",
                        "Lori captures"):
            self.assertIn(section, src)
        # Overview is the only default-open section.
        self.assertIn('insSection("overview", "Overview", true)', src)


class Lab03Test(unittest.TestCase):
    """WO-TRAVEL-DOC-UI-LAB-03 — the two formerly-deferred gaps are now
    REQUIRED behavior: true day-scoped sources and the date-range
    reconcile flow, plus the lab-only evaluation checklist. These
    assertions also lock the never-delete posture (no DELETE calls
    anywhere in the lab) and preserve the round-2 fixes untouched."""

    def test_day_scoped_sources_ui(self):
        src = _stripped_js()
        # Attach-source drawer, day-scoped by construction.
        self.assertIn("Attach source to Day", src)
        self.assertIn("＋ Attach source", src)
        self.assertIn("Save source to this day", src)
        # Day inspector splits day-attached sources from the scope
        # fallback, and unlinking clears trip_day_id ONLY.
        self.assertIn("Attached to this day", src)
        self.assertIn("From linked stop/region", src)
        self.assertIn("Unlink from day", src)
        self.assertIn("clear_day", src)
        # Flags-honest display state.
        self.assertIn("In memoir OFF", src)

    def test_source_attach_vs_move_is_explicit(self):
        # Same Attach-vs-Move doctrine as the photo picker: sources on
        # another day are never silently reassigned. "Move to this day"
        # now appears for BOTH pickers (photos + sources), the source
        # move gets its own inline notice, and there is still no native
        # confirm() dialog anywhere in the lab.
        src = _stripped_js()
        self.assertGreaterEqual(src.count("Move to this day"), 2)
        self.assertIn("source(s) will move from other days.", src)
        cleaned = src.replace("paintAttach(", "").replace(
            "paintAttachSources(", "")
        self.assertNotIn("confirm(", cleaned)

    def test_sources_tab_day_badge_and_filters(self):
        src = _stripped_js()
        self.assertIn("sourceFilter", src)
        for label in ("Day-scoped", "Unattached", "In memoir"):
            self.assertIn(label, src)
        self.assertIn("tdl-badge-day", src)

    def test_reconcile_banners_and_generate_relabel(self):
        src = _stripped_js()
        self.assertIn("Generate / reconcile day cards", src)
        self.assertIn("not yet in the calendar.", src)
        self.assertIn("Add missing days", src)
        self.assertIn("outside the current trip dates", src)
        self.assertIn("kept to protect your notes", src)
        self.assertIn("Review outside-date days", src)
        # The UI reads the read-only preview endpoint and refreshes it
        # after generation.
        self.assertIn("/days/reconcile-preview", src)
        self.assertIn("reloadReconcile", src)

    def test_out_of_range_day_cards_visible_never_hidden(self):
        src = _stripped_js()
        self.assertIn("Outside current trip dates", src)
        # Chip renders inside the day card body — cards are never
        # filtered out of the Trip Plan list.
        self.assertIn("tdl-chip-outside", src)
        css = _stripped_css()
        self.assertIn(".tdl-chip-outside", css)
        self.assertIn(".tdl-reconcile-banner", css)

    def test_reconcile_drawer_reviews_without_deleting(self):
        src = _stripped_js()
        self.assertIn("tdl-reconcile-drawer", src)
        self.assertIn("Missing days (", src)
        self.assertIn("Outside-date day cards (", src)
        # Per-day content indicators in the review drawer.
        self.assertIn("Lori captures", src)
        self.assertIn("Mark outside-date days as reviewed (kept)", src)
        # NEVER-DELETE lock, narrowed by WO-TRAVEL-DOC-UNIFY-01 Phase 3A.
        #
        # This used to assert the whole file contained no DELETE at all.
        # Phase 3A ports exactly one destructive control — the gated trip
        # force-delete — so the file-wide form is no longer true. What the
        # test was really protecting is that RECONCILE reviews rather than
        # destroys: a missing or outside-date day card is reported to the
        # operator, never silently removed. So assert it of the reconcile
        # drawer and its loader, which is where a "just clean it up for me"
        # regression would actually land.
        recon = src[src.index("function renderReconcileDrawer("):][:6000]
        self.assertNotIn('"DELETE"', recon)
        self.assertNotIn("'DELETE'", recon)
        loader = src[src.index("function reloadReconcile("):][:1600]
        self.assertNotIn('"DELETE"', loader)
        self.assertNotIn("'DELETE'", loader)

    def test_lab_only_evaluation_checklist(self):
        src = _stripped_js()
        self.assertIn("Lab-only evaluation checklist", src)
        # The panel's own copy has to say who it is for. It used to read
        # "part of the removable lab, not production Travel Doc" — a
        # sentence Phase 4 made false in both halves: this module is not
        # removable any more, and there is no other Travel Doc to be the
        # production one. What the copy still has to convey is the part
        # that stayed true: an operator never sees this panel. The gate
        # that actually enforces that is the !embedded call site, pinned
        # below, so the copy and the code cannot drift apart.
        self.assertIn("Dev harness only", src)
        self.assertNotIn("removable lab, not production", src)
        self.assertIn("if (!embedded) wrap.appendChild(renderEvalChecklist());",
                      src)
        for label in ("Day cards generated / reconciled",
                      "Photos attached to days",
                      "Sources attached to days",
                      "Lori day captures present",
                      "Travelogue preview available"):
            self.assertIn(label, src)
        css = _stripped_css()
        self.assertIn(".tdl-eval-panel", css)

    def test_round_2_fixes_preserved(self):
        # WO-TRAVEL-DOC-UI-LAB-03 must not regress the round-2 review
        # fixes: photo-Lori overlay, GPS two-surface doctrine wording,
        # explicit Attach vs Move for photos, "Attach photos" naming.
        src = _stripped_js()
        self.assertIn("openLoriOverlayForPhoto", src)
        self.assertIn("GPS found — available for Travel Doc context", src)
        self.assertNotIn("GPS on file (private)", src)
        self.assertIn("Attach \" + c.attach + \" · Move \" + c.move", src)
        self.assertIn("Attach photos", src)
        self.assertNotIn("Add photos", src)


class FinishPassTest(unittest.TestCase):
    """2026-07-23 Travel Doc Lab finish-pass: no native prompts, preview matches
    the backend spoken trim, evidence text is editable, and evidence actions
    refresh the day/public-context counts."""

    def setUp(self):
        self.src = _stripped_js()   # comments removed — mentions don't count

    # ── Lab doctrine: no native dialogs ──────────────────────────────────
    def test_no_window_prompt_in_the_lab(self):
        self.assertNotIn("window.prompt(", self.src)
        self.assertNotIn("prompt(", self.src.replace("window.prompt(", ""))

    def test_no_native_confirm_or_alert(self):
        self.assertNotIn("window.confirm(", self.src)
        self.assertNotIn("window.alert(", self.src)

    def test_in_panel_editor_replaces_the_prompt(self):
        self.assertIn("openEvidenceEditor(", self.src)
        self.assertIn("renderEvidenceEditor(", self.src)
        # the two operator-entry lanes now open the editor
        self.assertIn('mode: "draft_observation"', self.src)
        self.assertIn('mode: "place_from_context"', self.src)

    # ── preview matches the backend spoken trim ──────────────────────────
    def test_spoken_trim_helper_present(self):
        self.assertIn("function spokenContextTrim(", self.src)
        # 160-char budget mirrors _SPOKEN_CONTEXT_CHARS on the backend
        self.assertIn("SPOKEN_CONTEXT_CHARS = 160", self.src)

    def test_preview_trims_place_vision_observation_but_not_ocr(self):
        i = self.src.index("function evLoriWording(")
        block = self.src[i:i + 1600]
        # OCR branch speaks the untrimmed value (stripDot), like the backend
        self.assertIn("the OCR draft appears to read '\" + stripDot", block)
        # place / vision / observation branches speak the trimmed value
        self.assertIn("the place context suggests \" + spoken", block)
        self.assertIn("the draft image context suggests \"\n           + spoken",
                      block)
        self.assertIn("the draft photo observation suggests \"\n           + spoken",
                      block)

    # ── evidence text editing (edit revokes approval, clears memoir) ──────
    def test_edit_row_patches_result_summary(self):
        self.assertIn('"Edit text"', self.src)
        self.assertIn("result_summary: t", self.src)
        # the drawer for edit warns it revokes approval
        self.assertIn("revokes approval", self.src)

    # ── refresh the counts after evidence changes ────────────────────────
    def test_refresh_after_evidence_reloads_days_and_public_context(self):
        self.assertIn("function refreshAfterEvidence(", self.src)
        i = self.src.index("function refreshAfterEvidence(")
        block = self.src[i:i + 400]
        self.assertIn("reloadDays()", block)
        self.assertIn("reloadPublicContext()", block)
        # and the evidence actions call it
        self.assertIn(".then(refreshAfterEvidence)", self.src)
        self.assertIn("refreshAfterEvidence();", self.src)


class DocumenterDoubleSendGuardTest(unittest.TestCase):
    """travel-documenter.js modal double-send guard (parity with the 2026-05-07
    chat-path _loriIsBusy fix) — a second click while Lori is generating must
    not fire the turn twice."""

    def setUp(self):
        p = _REPO_ROOT / "ui" / "js" / "travel-documenter.js"
        # Phase 6.4: string-aware stripper (see _stripped_js above).
        self.src = _ssh.strip_js_comments(p.read_text(encoding="utf-8"))

    def test_send_is_guarded_and_cleared(self):
        i = self.src.index("_send: function ()")
        block = self.src[i:i + 400]
        self.assertIn("if (this._busy) return;", block)
        self.assertIn("this._busy = true;", block)
        # cleared on done, on connection failure, and by a failsafe timer
        self.assertIn("self._busy = false;", self.src)
        self.assertIn("_busyTimer", self.src)


class DraftAssistantTest(unittest.TestCase):
    """WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01 — the Draft tab wiring."""

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def test_draft_tab_registered(self):
        self.assertIn('["draft", "Draft"]', self.src)
        self.assertIn('case "draft": return renderDraft();', self.src)

    def test_render_and_helpers_present(self):
        for fn in ("function renderDraft(", "function _draftLoadPreview(",
                   "function _draftRun(", "function _draftKeep(",
                   "function _draftScopeOptions("):
            self.assertIn(fn, self.src, fn)

    def test_calls_draft_section_endpoint(self):
        self.assertIn("/draft-section", self.src)
        # preview uses preview_only; the run does not force it
        self.assertIn("preview_only = true", self.src)

    def test_keep_persists_as_draft_note_not_memoir(self):
        # Keeping a draft writes a source_type='draft' note with promotion OFF.
        self.assertIn('source_type: "draft"', self.src)
        self.assertIn("include_in_memoir: false", self.src)
        self.assertIn("include_in_interview_context: false", self.src)
        self.assertIn("/location-notes", self.src)

    def test_no_native_dialogs_in_draft_path(self):
        # Lab doctrine: no window.prompt/confirm/alert anywhere.
        for banned in ("window.prompt", "window.confirm", "window.alert",
                       "prompt(", "confirm(", "alert("):
            self.assertNotIn(banned, self.src, banned)

    def test_draft_css_present(self):
        self.assertIn(".tdl-draft-result", self.css)
        self.assertIn(".tdl-draft-select", self.css)


class EvidenceLifecycleLabTest(unittest.TestCase):
    """WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01 — reversible hide in the Lab.

    Story Notes / Sources rows are removed from view via PATCH
    {hidden:true} (never a DELETE — the lab's never-delete posture
    holds), restored via PATCH {hidden:false}, and each tab carries a
    Show hidden toggle that refetches with include_hidden=1 and renders
    hidden rows muted with a Restore affordance."""

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def test_hide_is_patch_hidden_true_then_reload(self):
        for fn, reload_call in (("function hideNote(", "reloadNotes()"),
                                ("function hideSource(", "reloadSources()")):
            i = self.src.index(fn)
            block = self.src[i:i + 450]
            self.assertIn('method: "PATCH"', block, fn)
            self.assertIn("{ hidden: true }", block, fn)
            self.assertIn(reload_call, block, fn)

    def test_restore_is_patch_hidden_false(self):
        for fn in ("function restoreNote(", "function restoreSource("):
            i = self.src.index(fn)
            block = self.src[i:i + 450]
            self.assertIn('method: "PATCH"', block, fn)
            self.assertIn("{ hidden: false }", block, fn)

    def test_show_hidden_toggle_per_tab_with_include_hidden_fetch(self):
        # Toggle state lives on st (per-tab), the toggled fetch adds the
        # sanctioned include_hidden=1 query param, and both labels exist
        # (off: "Show hidden"; on: "Show hidden (n) ✓").
        self.assertIn("showHiddenNotes", self.src)
        self.assertIn("showHiddenSources", self.src)
        self.assertIn("?include_hidden=1", self.src)
        self.assertIn('"Show hidden"', self.src)
        self.assertIn('"Show hidden ("', self.src)
        self.assertIn("function hiddenToggleRow(", self.src)
        # Hide + Restore affordances render as plain buttons — no native
        # dialogs (doctrine re-checked by FinishPassTest).
        self.assertIn('"Hide"', self.src)
        self.assertIn('"Restore"', self.src)

    def test_hidden_rows_render_muted_with_new_tdl_classes(self):
        self.assertIn("tdl-row-hidden", self.src)
        self.assertIn("tdl-badge-hidden", self.src)
        self.assertIn(".tdl-row-hidden", self.css)
        self.assertIn(".tdl-badge-hidden", self.css)
        self.assertIn(".tdl-hidden-toggle-row", self.css)

    def test_evidence_lanes_are_still_hide_only(self):
        # Hide/restore stay PATCH-only.
        #
        # This test used to read "the lab issues no DELETE at all".
        # WO-TRAVEL-DOC-UNIFY-01 Phase 3A ports exactly one destructive
        # control — the gated trip force-delete — so the blanket assertion
        # is now false by design. It is narrowed rather than deleted: the
        # property worth keeping is that EVIDENCE (notes, sources, photo
        # links, photo/public context) is never destroyed from this
        # surface, and that stays pinned. TripForceDeleteGateTest below
        # pins the one sanctioned exception.
        for fn in ("function hideNote(", "function hideSource(",
                   "function restoreNote(", "function restoreSource("):
            i = self.src.index(fn)
            self.assertNotIn("DELETE", self.src[i:i + 450], fn)
        for lane in ("location-notes/", "/sources/", "photo-context/",
                     "public-context/", "photo-links/"):
            for m in re.finditer(re.escape(lane), self.src):
                window = self.src[m.start():m.start() + 220]
                self.assertNotIn('method: "DELETE"', window,
                                 f"DELETE aimed at the {lane} evidence lane")


class TripForceDeleteGateTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UNIFY-01 Phase 3A — the trip force-delete impact gate.

    The production Documenter's destructive-trip control, ported into the
    unified workspace. These are the ten gates from the work order. They
    are source-pattern tests (this repo has no JS runner), so each one is
    written to fail loudly if the SPECIFIC unsafe variant reappears — the
    wrong error envelope, a looser arming rule, a native dialog — rather
    than merely checking that some delete code exists.
    """

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def _fn(self, name: str, span: int = 1400) -> str:
        i = self.src.index(name)
        return self.src[i:i + span]

    # 1 — the unified workspace exposes a delete-trip control.
    def test_unified_workspace_exposes_a_delete_trip_control(self):
        sidebar = self._fn("function renderSidebar(", 3000)
        self.assertIn('"Delete trip"', sidebar)
        self.assertIn("deleteTrip(st.trip)", sidebar)
        # It hangs off the SELECTED-trip card, not the rail rows, so it can
        # only ever act on the trip the operator is looking at.
        self.assertLess(sidebar.index('el("div", "tdl-card")'),
                        sidebar.index('"Delete trip"'))
        self.assertIn("tdl-btn-danger", sidebar)

    # 2 — the first attempt is a NORMAL delete, never a force.
    def test_delete_attempts_the_unforced_delete_first(self):
        block = self._fn("function deleteTrip(")
        self.assertIn('{ method: "DELETE" }', block)
        # No force payload on the first attempt — leading with force would
        # skip the impact review entirely.
        head = block[:block.index(".catch(")]
        self.assertNotIn("force", head)
        self.assertNotIn("confirm_trip_id", head)

    # 3 — a 409 impact response opens the in-panel review.
    def test_409_impact_response_opens_the_in_panel_review(self):
        block = self._fn("function deleteTrip(")
        self.assertIn("e.status === 409", block)
        self.assertIn("impact.requires_force", block)
        self.assertIn("st.deleteReview = {", block)
        # The review is a drawer inside the mount — it never navigates away
        # and never opens a window.
        self.assertIn("function renderDeleteTripReview(", self.src)
        self.assertIn(
            "if (st.deleteReview) app.appendChild(renderDeleteTripReview())",
            self.src)

    # 4 — the gate reads e.body.detail, not the wrong envelope.
    def test_gate_reads_the_detail_envelope_not_the_flat_body(self):
        block = self._fn("function deleteImpactOf(")
        self.assertIn("e.body.detail", block)
        self.assertIn('typeof e.body.detail === "object"', block)
        # The flat read is the silent-failure shape: requires_force is
        # undefined at that level, so the gate would never open and the
        # operator would see a raw error string instead of the review.
        self.assertNotIn("e.body.requires_force", self.src)
        self.assertNotIn("e.body.counts", self.src)

    # 4b — api() must actually carry the envelope, or 4 is unreachable.
    def test_api_attaches_status_and_body_to_the_rejection(self):
        block = self._fn("function api(", 2600)
        self.assertIn("err.status = r.status", block)
        self.assertIn("err.body = body", block)
        # And the old lossy shape is gone: a bare throw of a string-only
        # Error at the choke point destroys the payload for every caller.
        self.assertNotIn(
            'throw new Error(init.method + " " + path + " -> " + r.status',
            self.src)

    # 5 — the counts render in the review panel.
    def test_counts_render_in_the_review_panel(self):
        block = self._fn("function renderDeleteTripReview(", 3800)
        self.assertIn("TRIP_DELETE_COUNT_LANES.forEach", block)
        self.assertIn("tdl-delete-counts", block)
        self.assertIn("tdl-delete-count", block)
        self.assertIn(".tdl-delete-counts", self.css)
        self.assertIn(".tdl-delete-count", self.css)
        # Every lane the backend's _TRIP_DEPENDENT_TABLES allowlist can
        # return has a labelled cell — including bio_suggestions, which the
        # production panel's nine-cell grid silently omits.
        lanes = self.src[self.src.index("var TRIP_DELETE_COUNT_LANES"):]
        lanes = lanes[:lanes.index("];")]
        for key in ("regions", "stops", "days", "photo_links", "notes",
                    "sources", "story_links", "public_context",
                    "photo_context", "bio_suggestions"):
            self.assertIn('"' + key + '"', lanes, key)
        # A lane the backend adds later must still be shown, not dropped.
        self.assertIn("Object.keys(counts).forEach", block)

    # 6 — a wrong confirmation blocks the force delete.
    def test_wrong_confirmation_blocks_force_delete(self):
        block = self._fn("function renderDeleteTripReview(", 3800)
        self.assertIn("function refreshArm()", block)
        self.assertIn("confirmBtn.disabled = !armed", block)
        # Blank never arms, and the button starts disabled (refreshArm is
        # called once at build time, before the operator types anything).
        self.assertIn('typed !== ""', block)
        self.assertIn("refreshArm();", block)
        # Nothing looser than an exact compare: no case folding, no
        # substring/prefix matching on the confirmation.
        arm = block[block.index("function refreshArm()"):]
        arm = arm[:arm.index("confirmInput.oninput")]
        for loose in ("toLowerCase", "toUpperCase", "indexOf", "startsWith",
                      "includes"):
            self.assertNotIn(loose, arm, loose)

    # 7 — the exact title or the trip id arms the force delete.
    def test_exact_title_or_trip_id_arms_force_delete(self):
        block = self._fn("function renderDeleteTripReview(", 3800)
        self.assertIn('typed === String(review.tripTitle || "").trim()', block)
        self.assertIn("typed === String(review.tripId)", block)
        # The WIRE still echoes the id exactly — accepting the title is a
        # client-side affordance and must never reach the server as one,
        # or the backend's 422 guard is defeated.
        force = self._fn("function forceDeleteTrip(")
        self.assertIn("force: true", force)
        self.assertIn("confirm_trip_id: review.tripId", force)
        self.assertNotIn("confirm_trip_id: review.tripTitle", self.src)
        self.assertIn("reason:", force)
        # The handler is a property assignment, so re-opening the review
        # for a different trip cannot stack a stale closure.
        self.assertIn("confirmInput.oninput = refreshArm", block)
        self.assertNotIn('confirmInput.addEventListener("input"', block)

    # 8 — force delete refreshes the list and clears the deleted selection.
    def test_force_delete_refreshes_list_and_clears_selection(self):
        after = self._fn("function afterTripDeleted(")
        self.assertIn("st.trip = null", after)
        self.assertIn("st.tree = null", after)
        self.assertIn("st.deleteReview = null", after)
        self.assertIn("st.selectedDayId = null", after)
        self.assertIn("loriPane.reset()", after)
        self.assertIn("loadTrips({ noAutoSelect: true })", after)
        # Both delete paths (empty trip, forced) land there.
        self.assertIn("afterTripDeleted()", self._fn("function deleteTrip("))
        self.assertIn("afterTripDeleted()",
                      self._fn("function forceDeleteTrip("))
        # And loadTrips honours the flag — otherwise the refresh silently
        # mounts some OTHER trip's workspace right after a destructive act.
        loader = self._fn("function loadTrips(")
        self.assertIn("noAutoSelect", loader)
        self.assertIn("if (!noAutoSelect && !st.trip && st.trips.length)",
                      loader)
        # A pending review never survives a trip switch.
        self.assertIn("st.deleteReview = null",
                      self._fn("function selectTrip(", 1200))

    # 9 — no native dialogs anywhere in the unified delete flow.
    def test_no_native_dialogs_in_the_delete_flow(self):
        for banned in ("window.confirm", "window.prompt", "window.alert",
                       "confirm(", "prompt(", "alert("):
            self.assertNotIn(banned, self.src, banned)
        # This loop used to read "and no /regions or /stops DELETE exists
        # here at all", which was true while Phase 3A was the whole of the
        # port. Phase 3B ports region and stop deletion deliberately, so
        # that form is now false by design — but it is WIDENED, not
        # dropped, because the property it protects is the one that
        # matters: every DELETE this file issues is aimed at the trip
        # graph (trip / region / stop) and never at an evidence lane.
        # An unrecognised DELETE shape still fails the build.
        sanctioned = ('"/api/trips/" + encodeURIComponent(',
                      '"/api/trips/regions/" + encodeURIComponent(',
                      '"/api/trips/stops/" + encodeURIComponent(')
        for m in re.finditer(r'method:\s*"DELETE"', self.src):
            call = self.src[max(0, m.start() - 220):m.start()]
            self.assertTrue(any(p in call for p in sanctioned),
                            "unrecognised DELETE target in the lab")
            for lane in ("photo-context", "public-context", "location-notes",
                         "/sources", "photo-links"):
                self.assertNotIn(lane, call, lane)

    # 10 — the force-delete gate does not depend on a second surface.
    def test_force_delete_gate_needs_no_fallback_surface(self):
        # Phase 3A wrote this as "the legacy fallback remains reachable":
        # while the impact gate was new, the old page had to stay one
        # click away so an operator could finish a delete if the new
        # drawer misbehaved. WO-TRAVEL-DOC-UNIFY-01 Phase 4 retired that
        # escape hatch on purpose — the gate has shipped and been smoked
        # through 3B/3C/3D — so asserting the deep link and the surface
        # toggle would now assert the exact thing Phase 4 removed.
        #
        # What still has to be proved is the half that never depended on
        # the fallback: the force-delete gate is self-contained on this
        # surface, and Phase 4 did not delete the older module (Phase 4
        # requirement 7 — its backend endpoints stay in use).
        self.assertNotIn("function prodTravelDocUrl(", self.src)
        self.assertNotIn("travel-documenter.html?api=", self.src)
        self.assertTrue(
            (_REPO_ROOT / "ui" / "js" / "travel-documenter.js").exists(),
            "travel-documenter.js must not be deleted — Phase 4 unmounts "
            "it from the shell, it does not remove the module")
        shell = (_REPO_ROOT / "ui" / "hornelore1.0.html").read_text(
            encoding="utf-8")
        self.assertNotIn('data-td-surface="legacy"', shell)
        self.assertNotIn('data-td-surface="unified"', shell)
        # The gate itself: impact counts, then an explicit force confirm,
        # both rendered by this module with no way out to another page.
        self.assertIn("force=true", self.src)
        self.assertIn("tdl-delete-drawer", self.src)

    def test_delete_review_css_is_tdl_namespaced(self):
        for cls in (".tdl-delete-drawer", ".tdl-delete-warn",
                    ".tdl-delete-counts", ".tdl-delete-count",
                    ".tdl-delete-error", ".tdl-card-actions"):
            self.assertIn(cls, self.css, cls)

    def test_review_drawer_is_not_gated_on_a_selected_trip(self):
        # Every other drawer describes the SELECTED trip and is gated on
        # st.trip. This one describes a trip being taken away, and the
        # flow that clears st.trip is the same flow that clears the
        # review — gating it on st.trip makes an unclosable invisible
        # state reachable.
        self.assertNotIn("if (st.trip && st.deleteReview)", self.src)
        self.assertIn("function closeDeleteReview(", self.src)


class TripRegionStopCrudTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UNIFY-01 Phase 3B — trip / region / stop CRUD.

    The last production-only editing behaviour, ported into the unified
    workspace. Source-pattern tests, same doctrine as Phase 3A: each one
    is written to fail if the SPECIFIC unsafe or lossy variant reappears
    (a native dialog, a pre-emptive force, a dropped insert position, a
    reparent into a stop's own subtree), not merely to confirm that some
    editing code exists.
    """

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def _fn(self, name: str) -> str:
        """Slice the ACTUAL function body, not a fixed-width window.

        A fixed window spills into whatever function comes next, which
        turns every "this must NOT appear here" assertion below into a
        coin flip decided by line count. Top-level functions in this file
        are indented two spaces, so the next one is the end of this one;
        nested helpers are indented deeper and stay inside.
        """
        i = self.src.index(name)
        j = self.src.find("\n  function ", i + len(name))
        return self.src[i:(len(self.src) if j == -1 else j)]

    # 1 — the empty state no longer sends the operator to production.
    def test_empty_state_copy_is_unified(self):
        self.assertNotIn("Create one in the production Travel Doc tab",
                         self.src)
        self.assertIn("No trips yet for this narrator.", self.src)
        self.assertIn("+ New trip in the left rail", self.src)

    # 2 — a trip can be created from the unified workspace.
    def test_trip_create_control_exists_in_the_unified_workspace(self):
        sidebar = self._fn("function renderSidebar(")
        self.assertIn('"+ New trip"', sidebar)
        self.assertIn('openTripEditor("create")', sidebar)
        self.assertIn("function renderTripEditorDrawer(", self.src)
        drawer = self._fn("function renderTripEditorDrawer(")
        self.assertIn('api("/api/trips", { method: "POST"', drawer)
        self.assertIn("person_id: st.personId", drawer)

    # 3 — trip edit goes through the existing PATCH, with the clear_ flags
    #     production uses to distinguish "unset this" from "leave it".
    def test_trip_edit_saves_through_the_existing_api(self):
        drawer = self._fn("function renderTripEditorDrawer(")
        self.assertIn('method: "PATCH"', drawer)
        self.assertIn('"/api/trips/" + encodeURIComponent(trip.id)', drawer)
        for f in ("title:", "start_date:", "clear_start_date:", "end_date:",
                  "clear_end_date:", "summary:", "clear_summary:"):
            self.assertIn(f, drawer, f)

    # 4 — days_warning / sync_warning survive a save as a dismissible
    #     banner, not a status line the next message overwrites.
    def test_trip_save_warnings_are_preserved(self):
        fn = self._fn("function applyTripWarnings(")
        self.assertIn("days_warning", fn)
        self.assertIn("sync_warning", fn)
        self.assertIn("st.tripWarning", fn)
        self.assertIn("function renderTripWarning(", self.src)
        self.assertIn("applyTripWarnings(out)", self.src)

    # 5 — region create / edit / delete controls all exist.
    def test_region_crud_controls_exist(self):
        board = self._fn("function renderRegionRow(")
        self.assertIn('"+ Stop"', board)
        self.assertIn('openRegionEditor("edit", r.id)', board)
        self.assertIn('openRouteDelete("region", r.id)', board)
        self.assertIn('openRegionEditor("create", null)', self.src)
        drawer = self._fn("function renderRegionEditorDrawer(")
        self.assertIn('"/regions", {', drawer)
        self.assertIn('"/api/trips/regions/" + encodeURIComponent(region.id)',
                      drawer)
        for f in ("country_or_area:", "base_address:", "clear_base_address:",
                  "clear_country_or_area:", "clear_summary:"):
            self.assertIn(f, drawer, f)

    # 6 — stop create / edit / delete controls all exist.
    def test_stop_crud_controls_exist(self):
        row = self._fn("function renderStopRow(")
        self.assertIn('openStopEditor("edit"', row)
        self.assertIn('openRouteDelete("stop", s.id)', row)
        drawer = self._fn("function renderStopEditorDrawer(")
        self.assertIn('"/stops", {', drawer)
        self.assertIn('"/api/trips/stops/" + encodeURIComponent(stop.id)',
                      drawer)
        for f in ("location_name:", "stop_type:", "date_start:", "date_end:",
                  "clear_notes:"):
            self.assertIn(f, drawer, f)
        # The region selector and the stop-type list are both present —
        # production supports both and losing either would make the
        # unified workspace a downgrade.
        self.assertIn("var STOP_TYPES", self.src)
        self.assertIn('field("Region", vRegion)', drawer)

    # 7 — insert-at-position is preserved, not quietly dropped.
    def test_insert_at_position_is_preserved(self):
        row = self._fn("function renderStopRow(")
        self.assertIn('"+ Before"', row)
        self.assertIn('"+ After"', row)
        self.assertIn('where: "before"', row)
        self.assertIn('where: "after"', row)
        drawer = self._fn("function renderStopEditorDrawer(")
        self.assertIn('"/move"', drawer)
        self.assertIn("before_stop_id", drawer)
        self.assertIn("after_stop_id", drawer)
        # An insert anchor only holds while the new stop is still a
        # sibling of the row it was anchored to. If the operator changes
        # the region or the parent in the drawer, the context is dropped
        # rather than issuing a move that fights the choice just made.
        self.assertIn("var useCtx", drawer)
        self.assertIn("ctx.region_id", drawer)

    # 8 — a stop can never be reparented into its own subtree.
    def test_parent_selector_excludes_the_stops_own_subtree(self):
        self.assertIn("function subtreeIds(", self.src)
        drawer = self._fn("function renderStopEditorDrawer(")
        self.assertIn("subtreeIds(stop)", drawer)
        self.assertIn("if (forbidden[row.id]) return;", drawer)

    # 9 — region/stop deletion is in-panel, never a native dialog.
    def test_region_and_stop_delete_use_an_in_panel_review(self):
        self.assertIn("function renderRouteDeleteReview(", self.src)
        self.assertIn("function openRouteDelete(", self.src)
        for banned in ("window.confirm", "window.prompt", "window.alert",
                       "confirm(", "prompt(", "alert("):
            self.assertNotIn(banned, self.src, banned)
        # Both destructive route controls open the review; neither fires
        # a delete straight off the click.
        row = self._fn("function renderStopRow(")
        self.assertIn('openRouteDelete("stop"', row)
        region = self._fn("function renderRegionRow(")
        self.assertIn('openRouteDelete("region"', region)

    # 10 — the region delete is a two-stage ladder, unforced FIRST.
    #
    #      This is the one place Phase 3B deliberately diverges from
    #      production behaviour rather than merely from its UI. Production
    #      sends an unforced DELETE after its confirm() and neither passes
    #      force nor handles the backend's 409, so a non-empty region
    #      dead-ends with nothing deleted AFTER the operator agreed.
    def test_region_delete_tries_unforced_first_then_offers_force(self):
        unforced = self._fn("function deleteRegionUnforced(")
        self.assertIn('{ method: "DELETE" }', unforced)
        self.assertNotIn("force=true", unforced)
        self.assertIn("e.status === 409", unforced)
        self.assertIn('st.routeDelete.stage = "force"', unforced)
        # Stage 2 is reachable only from a real backend refusal, and it
        # quotes that refusal rather than paraphrasing it.
        forced = self._fn("function forceDeleteRegion(")
        self.assertIn("force=true", forced)
        review = self._fn("function renderRouteDeleteReview(")
        self.assertIn('rd.stage === "force"', review)
        self.assertIn("rd.serverMessage", review)

    # 11 — the stop delete states what actually happens to children.
    def test_stop_delete_review_says_children_are_promoted(self):
        review = self._fn("function renderRouteDeleteReview(")
        self.assertIn("they move up to become top-level stops", review)
        stop_del = self._fn("function deleteStopReviewed(")
        self.assertIn('"/api/trips/stops/" + encodeURIComponent(rd.id)',
                      stop_del)
        self.assertNotIn("force", stop_del)

    # 12 — a delete leaves no dangling selection or open editor behind.
    def test_route_delete_clears_dangling_handles(self):
        fn = self._fn("function afterRouteDeleted(")
        self.assertIn("st.routeSel = null", fn)
        self.assertIn("st.regionEditor = null", fn)
        self.assertIn("st.stopEditor = null", fn)
        self.assertIn("st.insertContext = null", fn)
        self.assertIn("refreshTripBundle()", fn)

    # 13 — editors are per-trip state and never survive a trip switch.
    def test_editors_are_cleared_on_trip_switch_and_trip_delete(self):
        for fn_name in ("function selectTrip(", "function afterTripDeleted("):
            fn = self._fn(fn_name)
            for field in ("st.tripEditor = null", "st.regionEditor = null",
                          "st.stopEditor = null", "st.routeDelete = null",
                          "st.insertContext = null"):
                self.assertIn(field, fn, fn_name + " / " + field)

    # 14 — the Trip tab rewrite strands nobody, and offers no way out.
    def test_the_tab_rewrite_strands_no_operator(self):
        # Phase 3B put a foot-note deep link at the bottom of the route
        # board so an operator could bail to the old page mid-rewrite.
        # Phase 4 removed the link with the fallback it pointed at, so
        # this test keeps the half that is still load-bearing — the tab
        # id migration — and inverts the half that Phase 4 retired.
        self.assertIn("function renderTripTab(", self.src)
        tab = self._fn("function renderTripTab(")
        self.assertNotIn("prodTravelDocUrl()", tab)
        self.assertNotIn("tdl-route-legacy", tab)
        # The old placeholder tab id must not strand an operator whose
        # last session ended on it.
        self.assertIn('if (tab === "current") tab = "trip";', self.src)
        self.assertNotIn('case "current": return renderCurrent();', self.src)

    # 15 — the new chrome is tdl- namespaced, like everything else here.
    def test_phase3b_css_is_tdl_namespaced(self):
        for cls in (".tdl-route-board", ".tdl-route-row",
                    ".tdl-route-row-region", ".tdl-route-row-stop",
                    ".tdl-route-row-actions", ".tdl-edit-drawer",
                    ".tdl-date-warn", ".tdl-insert-hint"):
            # .tdl-route-legacy was in this list until Phase 4. It styled
            # the deep-link foot-note; rule and markup came out together.
            self.assertIn(cls, self.css, cls)
        for cls in ("tdl-route-board", "tdl-edit-drawer", "tdl-insert-hint"):
            self.assertIn(cls, self.src, cls)


class TripIntakeUploadClusterTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UNIFY-01 Phase 3C — photo / source intake + cluster.

    The capability the unified workspace was missing entirely: getting
    material IN. Same doctrine as 3A/3B — every assertion below is aimed
    at a specific way this can go wrong (a stringified FormData, a scope
    re-read at submit time, a native dialog swallowing a duplicate count,
    an upload that quietly promotes itself into the memoir), not merely
    at the existence of an upload button.
    """

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def _fn(self, name: str) -> str:
        i = self.src.index(name)
        j = self.src.find("\n  function ", i + len(name))
        return self.src[i:(len(self.src) if j == -1 else j)]

    # 1 — the unified workspace exposes a photo upload control.
    def test_photo_upload_control_exists_in_unified_workspace(self):
        self.assertIn("function renderPhotoIntakeBar(", self.src)
        bar = self._fn("function renderPhotoIntakeBar(")
        self.assertIn("Upload photos", bar)
        self.assertIn('openUploadDrawer("photo")', bar)
        # It has to be reachable from the empty gallery, so it is rendered
        # by the Photos tab itself and not by a per-photo row.
        photos = self._fn("function renderPhotos(")
        self.assertIn("renderPhotoIntakeBar()", photos)

    # 2 — upload goes out as multipart, through the file's one fetch.
    def test_upload_uses_formdata_through_the_single_api_choke_point(self):
        up = self._fn("function uploadPhotoFiles(")
        self.assertIn("new FormData()", up)
        self.assertIn('fd.append("files", f)', up)
        self.assertIn("api(", up)
        self.assertNotIn("fetch(", up)
        # The choke point must pass a FormData through untouched. Both
        # halves matter: JSON.stringify(fd) yields "[object FormData]",
        # and a hand-set Content-Type omits the multipart boundary.
        api = self._fn("function api(path, opts)")
        self.assertIn("opts.body instanceof FormData", api)
        i = api.index("opts.body instanceof FormData")
        j = api.index("JSON.stringify(opts.body)")
        self.assertLess(i, j, "FormData branch must precede the JSON branch")
        self.assertIn("init.body = opts.body;", api)

    # 3 — trip / region / stop are three distinct, explicit endpoints.
    def test_photo_upload_target_is_explicit_per_scope(self):
        path = self._fn("function photoUploadPath(")
        self.assertIn('scope.level === "stop"', path)
        self.assertIn('"/api/trips/stops/"', path)
        self.assertIn('scope.level === "region"', path)
        self.assertIn('"/regions/"', path)
        self.assertIn('"/photos"', path)
        # The destination comes from the drawer's chosen key, never from
        # the ambient route selection re-read at submit time — that is how
        # a photo silently lands on the wrong stop.
        self.assertIn("function parseScopeKey(", self.src)
        self.assertNotIn("st.routeSel", path)
        up = self._fn("function uploadPhotoFiles(")
        self.assertNotIn("st.routeSel", up)
        src_up = self._fn("function uploadSourceFiles(")
        self.assertNotIn("st.routeSel", src_up)
        # routeSel may SEED the drawer, and only there.
        self.assertIn("st.routeSel", self._fn("function defaultScopeKey("))

    # 4 — after upload, the photo lanes and counts actually refresh.
    def test_uploaded_photo_refreshes_links_and_counts(self):
        up = self._fn("function uploadPhotoFiles(")
        self.assertIn("refreshTripBundle()", up)
        self.assertIn("notifyTripUpdated(", up)
        # A trip/region drop lands unplaced, so a filter left on "Needs
        # review" would show an empty gallery and read as a failed upload.
        self.assertIn('st.photoFilter = "all"', up)
        self.assertIn('st.tab = "photos"', up)

    # 5 — the Sources tab exposes its own upload control.
    def test_source_upload_control_exists(self):
        self.assertIn("function renderSourceIntakeBar(", self.src)
        bar = self._fn("function renderSourceIntakeBar(")
        self.assertIn('openUploadDrawer("source")', bar)
        sources = self._fn("function renderSources(")
        self.assertIn("renderSourceIntakeBar()", sources)
        # renderSources() returns early when the active filter is empty.
        # The control must be appended ABOVE that return or it vanishes
        # from exactly the state where it is needed most: no sources yet.
        self.assertLess(sources.index("renderSourceIntakeBar()"),
                        sources.index("No sources yet."))

    # 6 — source upload is multipart against the existing endpoint.
    def test_source_upload_uses_formdata_and_existing_endpoint(self):
        up = self._fn("function uploadSourceFiles(")
        self.assertIn("new FormData()", up)
        self.assertIn('fd.append("files", f)', up)
        self.assertIn('"/sources/upload"', up)
        self.assertIn('fd.append("source_type"', up)
        self.assertNotIn("fetch(", up)

    # 7 — title/source metadata behaviour is preserved, including the
    #     one-title-per-request truth the backend actually implements.
    def test_source_metadata_is_preserved(self):
        self.assertIn("SOURCE_TYPES", self.src)
        for t in ("itinerary", "receipt", "hotel", "ticket", "note",
                  "map", "link", "other"):
            self.assertIn('"' + t + '"', self.src, t)
        up = self._fn("function uploadSourceFiles(")
        # The backend stamps ONE title across every file in the request,
        # so sending a title with several files would erase every
        # filename. Guard the single-file condition, not just the append.
        self.assertIn("chosen.length === 1", up)
        drawer = self._fn("function renderUploadDrawer(")
        self.assertIn("titleIn.disabled = n > 1", drawer)

    # 8 — intake is intake. Nothing here promotes into the memoir.
    def test_uploaded_source_is_not_auto_promoted(self):
        up = self._fn("function uploadSourceFiles(")
        self.assertNotIn("include_in_memoir", up)
        # Nor does it attach itself to a day card; day attach stays a
        # separate, deliberate act.
        self.assertNotIn("trip_day_id", up)
        self.assertNotIn("promote", up.lower())

    # 9 — the cluster control exists and is wired to the real endpoint.
    def test_cluster_control_exists(self):
        bar = self._fn("function renderPhotoIntakeBar(")
        self.assertIn("Cluster photos", bar)
        self.assertIn("runClusterPhotos", bar)
        run = self._fn("function runClusterPhotos(")
        self.assertIn('"/cluster-photos"', run)
        self.assertIn("narrator_id", run)

    # 10 — the cluster result renders in the panel, not in a dialog, and
    #      the numbers that matter are named rather than dumped.
    def test_cluster_result_renders_in_panel(self):
        run = self._fn("function runClusterPhotos(")
        self.assertIn("st.photoIntake", run)
        for key in ("photos_considered", "links_written", "needs_review",
                    "review_threshold", "skipped_operator_confirmed"):
            self.assertIn(key, run, key)
        self.assertIn("refreshTripBundle()", run)
        self.assertIn("function renderIntakeResult(", self.src)
        box = self._fn("function renderIntakeResult(")
        self.assertIn("tdl-intake-result", box)
        self.assertIn("tdl-intake-warn", box)
        # A failure has to be visible too — a silent catch would leave the
        # busy panel spinning forever.
        self.assertIn(".catch(", run)
        self.assertIn("Cluster failed", run)

    # 11 — no native dialogs anywhere, including the new intake code.
    def test_intake_adds_no_native_dialogs(self):
        for token in ("confirm(", "prompt(", "alert("):
            self.assertNotIn(token, self.src, token)
        for fn in ("function renderUploadDrawer(", "function uploadPhotoFiles(",
                   "function uploadSourceFiles(", "function runClusterPhotos("):
            body = self._fn(fn)
            self.assertNotIn("window.", body, fn)

    # 12 — intake adds no DELETE on any evidence lane.
    def test_intake_adds_no_evidence_lane_delete(self):
        for fn in ("function uploadPhotoFiles(", "function uploadSourceFiles(",
                   "function runClusterPhotos(", "function renderUploadDrawer(",
                   "function renderPhotoIntakeBar(",
                   "function renderSourceIntakeBar("):
            body = self._fn(fn)
            self.assertNotIn('"DELETE"', body, fn)
            self.assertNotIn("method: \"DELETE\"", body, fn)

    # 13 — the drawer must not repaint between "choose files" and
    #      "Upload". A FileList cannot be written by script, so a
    #      renderAll() in between destroys the operator's selection with
    #      no way to restore it. This is the load-bearing constraint of
    #      the whole phase, so it is pinned rather than trusted.
    def test_drawer_does_not_repaint_between_choose_and_upload(self):
        drawer = self._fn("function renderUploadDrawer(")
        self.assertIn("scopeSel.onchange", drawer)
        self.assertIn("files.onchange", drawer)
        self.assertIn("target.textContent", drawer)
        self.assertIn("hint.textContent", drawer)
        self.assertNotIn("addEventListener", drawer)
        # The only renderAll() allowed in the drawer is on the failure
        # path, where the selection is already spent.
        for marker in ("scopeSel.onchange = function () {",
                       "files.onchange = function () {"):
            i = drawer.index(marker)
            j = drawer.index("};", i)
            self.assertNotIn("renderAll()", drawer[i:j], marker)

    # 14 — an open drawer is armed against a specific trip, so switching
    #      or deleting the trip must disarm it.
    def test_intake_state_clears_with_the_trip(self):
        for fn_name in ("function selectTrip(", "function afterTripDeleted("):
            fn = self._fn(fn_name)
            for field in ("st.uploadDrawer = null", "st.photoIntake = null",
                          "st.sourceIntake = null"):
                self.assertIn(field, fn, fn_name + " / " + field)

    # 15 — provenance is honest: this surface does not impersonate the
    #      narrator shelf, whose stamp carries backend review meaning.
    def test_upload_surface_stamp_is_honest(self):
        self.assertIn('UPLOAD_SURFACE = "travel_doc_unified"', self.src)
        up = self._fn("function uploadPhotoFiles(")
        self.assertIn('fd.append("uploaded_from_surface", UPLOAD_SURFACE)', up)
        self.assertNotIn("travels_shelf", up)

    # 16 — the new chrome is tdl- namespaced, like everything else here.
    def test_phase3c_css_is_tdl_namespaced(self):
        for cls in (".tdl-upload-drawer", ".tdl-scope-target",
                    ".tdl-file-hint", ".tdl-intake-doctrine",
                    ".tdl-intake-bar", ".tdl-intake-result",
                    ".tdl-intake-line", ".tdl-intake-warn",
                    ".tdl-intake-err", ".tdl-intake-failed"):
            self.assertIn(cls, self.css, cls)
        for cls in ("tdl-upload-drawer", "tdl-intake-bar",
                    "tdl-intake-result"):
            self.assertIn(cls, self.src, cls)


class RouteOrderBoardTest(unittest.TestCase):
    """WO-TRAVEL-DOC-UNIFY-01 Phase 3D — route order and board ergonomics.

    The last workflow reason to open the legacy Documenter. Same doctrine
    as 3A/3B/3C: every test below is written to fail if the SPECIFIC
    unsafe or lossy variant comes back — a stop reorder that also
    reparents, a permutation request that a stale tree turns into a
    refusal, an arrow that silently does nothing at the end of a list, a
    move refusal reported through a native dialog or swallowed entirely,
    a badge that costs a fetch per row — not merely to confirm that some
    reorder code exists.
    """

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def _fn(self, name: str) -> str:
        """Slice the ACTUAL function body — see Phase 3B's note above."""
        i = self.src.index(name)
        j = self.src.find("\n  function ", i + len(name))
        return self.src[i:(len(self.src) if j == -1 else j)]

    # 1 — the board renders regions, then each region's stops, in the
    #     order the backend returned them. Client-side sorting would make
    #     the board disagree with the thing the arrows actually move.
    def test_route_board_renders_regions_and_stops_in_server_order(self):
        tab = self._fn("function renderTripTab(")
        self.assertIn("regions.forEach(function (r, i) {", tab)
        self.assertIn("renderRegionRow(r, board, i, regions.length);", tab)
        region = self._fn("function renderRegionRow(")
        self.assertIn("var stops = r.stops || [];", region)
        self.assertIn("renderStopRow(s, r, 1, out, i, stops.length);", region)
        stop = self._fn("function renderStopRow(")
        self.assertIn("var kids = s.children || [];", stop)
        self.assertIn("renderStopRow(c, region, depth + 1, out, i, kids.length);",
                      stop)
        for fn, label in ((tab, "renderTripTab"), (region, "renderRegionRow"),
                          (stop, "renderStopRow")):
            self.assertNotIn(".sort(", fn, label)
            self.assertNotIn(".reverse()", fn, label)

    # 2 — the region reorder affordance is PRESENT (not retired). It was
    #     the one production route control with no unified equivalent.
    def test_region_reorder_affordance_is_present(self):
        region = self._fn("function renderRegionRow(")
        self.assertIn("moveRegionRelative(r.id, -1)", region)
        self.assertIn("moveRegionRelative(r.id, 1)", region)
        self.assertIn('moveBtn("↑", "Move region up"', region)
        self.assertIn('moveBtn("↓", "Move region down"', region)

    # 3 — a region move goes through the endpoint that already exists.
    #     No new backend surface was in scope for this phase.
    def test_region_move_uses_the_existing_reorder_endpoint(self):
        fn = self._fn("function moveRegionRelative(")
        self.assertIn('"/regions/reorder"', fn)
        self.assertIn("ordered_ids: ids", fn)
        self.assertIn('method: "POST"', fn)
        self.assertNotIn('method: "DELETE"', fn)
        self.assertNotIn('method: "PUT"', fn)

    # 4 — a STOP move names its neighbour instead of shipping the whole
    #     sibling permutation. Production's /stops/reorder is refused
    #     outright when the tree has drifted since the last load, which
    #     turns a legal-looking move into an unexplained failure.
    def test_stop_move_sends_a_neighbour_not_a_permutation(self):
        fn = self._fn("function moveStopRelative(")
        self.assertIn('"/stops/" + encodeURIComponent(stopId) + "/move"', fn)
        self.assertIn("before_stop_id: dir < 0 ? anchor : null", fn)
        self.assertIn("after_stop_id: dir > 0 ? anchor : null", fn)
        # The production variant must not come back through this door.
        self.assertNotIn("ordered_ids", fn)
        self.assertNotIn("/stops/reorder", fn)

    # 5 — a reorder must NEVER reparent. region_id and parent id are
    #     echoed back from where the stop already lives, so an arrow
    #     cannot move a branch into a place the operator was not shown.
    def test_stop_reorder_cannot_reparent(self):
        fn = self._fn("function moveStopRelative(")
        self.assertIn("var loc = locateStop(stopId);", fn)
        self.assertIn("var parentId = loc.parent ? loc.parent.id : null;", fn)
        self.assertIn("region_id: loc.region.id", fn)
        self.assertIn("parent_trip_stop_id: parentId", fn)
        # Nothing in a reorder may read an editor's selectors.
        self.assertNotIn("st.stopEditor", fn)
        self.assertNotIn("regionSel", fn)
        self.assertNotIn("parentSel", fn)

    # 6 — a substop moves among its OWN siblings, never among the
    #     region's top-level stops.
    def test_substop_moves_stay_inside_its_sibling_group(self):
        sib = self._fn("function siblingsOf(")
        self.assertIn("var p = findStop(parentStopId);", sib)
        self.assertIn("return (p && p.children) || [];", sib)
        fn = self._fn("function moveStopRelative(")
        self.assertIn("siblingsOf(loc.region.id, parentId)", fn)

    # 7 — Phase 3B's cross-region move / reparent, with its own-subtree
    #     exclusion, is untouched by this phase.
    def test_cross_region_move_and_subtree_guard_survive(self):
        self.assertIn("function subtreeIds(", self.src)
        drawer = self._fn("function renderStopEditorDrawer(")
        self.assertIn("subtreeIds(", drawer)
        self.assertIn("function moveBody(", drawer)
        self.assertIn("before_stop_id", drawer)
        self.assertIn("after_stop_id", drawer)
        self.assertIn("parent_trip_stop_id", drawer)

    # 8 — arrows are DISABLED at the ends. Production returns silently
    #     there, and a control that answers a click with nothing is
    #     indistinguishable from a broken build.
    def test_arrows_disable_at_the_ends(self):
        mb = self._fn("function moveBtn(")
        self.assertIn("if (!enabled || st.routeBusy) b.disabled = true;", mb)
        stop = self._fn("function renderStopRow(")
        self.assertIn("idx > 0", stop)
        self.assertIn("idx < total - 1", stop)
        region = self._fn("function renderRegionRow(")
        self.assertIn("idx > 0", region)
        self.assertIn("idx < total - 1", region)

    # 9 — one move at a time. Two interleaved reorders are each computed
    #     from the tree as it looked before the other one landed.
    def test_a_move_in_flight_blocks_the_next_one(self):
        for name in ("function moveStopRelative(", "function moveRegionRelative("):
            fn = self._fn(name)
            self.assertIn("if (!st.trip || st.routeBusy) return Promise.resolve();",
                          fn, name)
            self.assertIn("st.routeBusy = ", fn, name)
            self.assertIn("dayFormDirtyBlocks()", fn, name)

    # 10 — a refused move is reported in the panel AND the tree reloads,
    #      so the next click argues with what exists rather than with an
    #      order that only survives on screen.
    def test_move_failure_is_in_panel_and_reloads_the_tree(self):
        fail = self._fn("function routeMoveFailed(")
        self.assertIn("st.routeBusy = null;", fail)
        self.assertIn("st.routeError = prefix", fail)
        self.assertIn("refreshTripBundle()", fail)
        tab = self._fn("function renderTripTab(")
        self.assertIn("if (st.routeError) {", tab)
        self.assertIn('el("div", "tdl-route-error")', tab)
        done = self._fn("function routeMoveDone(")
        self.assertIn("st.routeError = \"\";", done)
        self.assertIn("notifyTripUpdated(", done)
        self.assertIn("refreshTripBundle()", done)

    # 11 — no native dialog and no evidence-lane DELETE anywhere on the
    #      new path. Both are standing rules for this work order.
    def test_route_order_path_has_no_native_dialog_and_no_delete(self):
        for name in ("function moveStopRelative(", "function moveRegionRelative(",
                     "function routeMoveFailed(", "function routeMoveDone(",
                     "function moveBtn(", "function routeSelect("):
            fn = self._fn(name)
            for banned in ("window.confirm", "window.alert", "window.prompt",
                           'method: "DELETE"'):
                self.assertNotIn(banned, fn, name + " / " + banned)

    # 12 — route rows are selectable, and for REGIONS as well as stops.
    #      Before this phase st.routeSel was written in exactly one place
    #      and only ever as a stop, which left Phase 3C's region-scoped
    #      upload seeding unreachable: the drawer could default to a
    #      region that nothing on the surface could select.
    def test_route_rows_select_regions_and_stops(self):
        pick = self._fn("function routePickCell(")
        self.assertIn("routeSelect(kind, id, regionId)", pick)
        self.assertIn("tdl-route-row-pick", pick)
        sel = self._fn("function routeSelect(")
        self.assertIn("st.routeSel = { kind: kind, id: id, regionId: regionId };",
                      sel)
        self.assertIn("dayFormDirtyBlocks()", sel)
        stop = self._fn("function renderStopRow(")
        self.assertIn('routePickCell("stop", s.id, region.id', stop)
        region = self._fn("function renderRegionRow(")
        self.assertIn('routePickCell("region", r.id, r.id', region)
        # ...and the rail agrees, so both surfaces write the same field.
        sidebar = self._fn("function renderSidebar(")
        self.assertIn('routeSelect("region", r.id, r.id)', sidebar)
        self.assertIn('routeSelect("stop", s.id, r.id)', sidebar)
        self.assertIn("tdl-route-region-pick", sidebar)
        # The region branch of the intake seed is now reachable.
        scope = self._fn("function defaultScopeKey(")
        self.assertIn('sel.kind === "region"', scope)

    # 13 — badges read state that is already loaded. A per-row fetch on a
    #      full-repaint surface is a render loop waiting to happen.
    def test_evidence_badges_cost_no_fetch(self):
        badge = self._fn("function routeBadgeText(")
        for field in ("st.notes", "st.sources", "st.photoLinks"):
            self.assertIn(field, badge, field)
        self.assertNotIn("api(", badge)
        self.assertNotIn("fetch(", badge)
        scoped = self._fn("function routeScopedRows(")
        self.assertIn("r.trip_stop_id === id", scoped)
        self.assertIn("r.trip_region_id === id && !r.trip_stop_id", scoped)
        self.assertNotIn("api(", scoped)
        stop = self._fn("function renderStopRow(")
        self.assertIn('routeBadgeText("stop", s.id)', stop)
        region = self._fn("function renderRegionRow(")
        self.assertIn('routeBadgeText("region", r.id)', region)

    # 14 — insert-before / insert-after and the stale-insert-context
    #      guard are Phase 3B behaviour that this phase must not disturb.
    def test_insert_context_behaviour_remains_pinned(self):
        stop = self._fn("function renderStopRow(")
        for marker in ('"+ Before"', '"+ After"', 'where: "before"',
                       'where: "after"', "sibling_stop_id: s.id"):
            self.assertIn(marker, stop, marker)
        drawer = self._fn("function renderStopEditorDrawer(")
        self.assertIn("var useCtx = (ctx && regionId === ctx.region_id &&", drawer)
        self.assertIn("st.insertContext", self.src)

    # 15 — Phase 3D held the fallback open; Phase 4 closed it. This is
    #      the module-wide version of that close-out: no helper, no
    #      caller, no URL left behind anywhere in the file.
    def test_the_fallback_deep_link_is_gone_module_wide(self):
        tab = self._fn("function renderTripTab(")
        self.assertNotIn("tdl-route-legacy", tab)
        self.assertNotIn("prodTravelDocUrl()", tab)
        self.assertNotIn("function prodTravelDocUrl(", self.src)
        self.assertNotIn("prodTravelDocUrl", self.src)
        # Nothing else may hand-roll the same escape hatch.
        self.assertNotIn("travel-documenter.html", self.src)

    # 16 — a move armed against one trip must not survive a trip switch
    #      or a trip delete, same rule the editors and drawers follow.
    def test_route_order_state_clears_with_the_trip(self):
        for name in ("function selectTrip(", "function afterTripDeleted(",
                     "function afterRouteDeleted("):
            fn = self._fn(name)
            self.assertIn("st.routeBusy = null", fn, name)
            self.assertIn('st.routeError = ""', fn, name)

    # 17 — the new chrome is tdl- namespaced and structural: the theme
    #      pass is explicitly out of scope, so no new colour literal may
    #      appear in these rules.
    def test_phase3d_css_is_tdl_namespaced_and_structural(self):
        names = (".tdl-route-row-pick", ".tdl-route-row-sel",
                 ".tdl-route-ind", ".tdl-route-move",
                 ".tdl-route-error", ".tdl-route-region-pick")
        for cls in names:
            self.assertIn(cls, self.css, cls)
            self.assertIn(cls.lstrip("."), self.src, cls)
        # Collect only THIS phase's rules — slicing to end-of-file would
        # sweep in every later block and make the no-new-colour check
        # about somebody else's code.
        rules = [ln for ln in self.css.splitlines()
                 if ln.startswith(names)]
        self.assertGreaterEqual(len(rules), len(names))
        for ln in rules:
            self.assertNotIn("#", ln,
                             "Phase 3D CSS must reuse --tdl-* colours: " + ln)

    # 18 — the encoding convention. Found by the Phase 3D live smoke and
    #      NOT by this suite, which is exactly why the gate now exists.
    def test_no_call_site_pre_stringifies_an_api_body(self):
        """`api()` owns the encoding. A call site must never do it too.

        `api()` stringifies `opts.body` itself, in the branch that sits
        after the FormData check. Both Phase 3D movers were first written
        as `body: JSON.stringify({...})`, so the request went out as a
        JSON *string* rather than an object and the backend answered 422
        on every arrow press. Every other call site in the file passes a
        raw object, so the convention was already unanimous — the two new
        ones were simply wrong, and no source-scanning test could see it
        because both spellings look equally plausible in isolation.

        The check is deliberately file-wide rather than scoped to the
        movers: the next person to add a POST is who it protects.
        """
        self.assertNotIn(
            "body: JSON.stringify", self.src,
            "api() stringifies opts.body itself; a call site that also "
            "stringifies double-encodes the request into a JSON string "
            "and the backend rejects it with 422.")
        # The positive half — the encoding still happens exactly once,
        # inside api(). Without this, deleting it from both ends passes.
        self.assertIn("init.body = JSON.stringify(opts.body);", self.src)

    # 19 — and the movers specifically still send a body at all.
    def test_route_movers_send_a_plain_object_body(self):
        """The file-wide ban above would also pass if a mover stopped
        sending a body entirely, or built one through a helper that
        stringified on the way. These pin the actual shape."""
        for name, key in (
            ("function moveRegionRelative(", "body: { ordered_ids: ids },"),
            ("function moveStopRelative(", "body: {"),
        ):
            fn = self._fn(name)
            self.assertIn(key, fn, name + " must post a raw object body")
            self.assertNotIn("JSON.stringify", fn,
                             name + " must leave encoding to api()")


if __name__ == "__main__":
    unittest.main()
