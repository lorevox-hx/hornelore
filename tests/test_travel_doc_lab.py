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
    from tests import travel_doc_surfaces as _tds
except ImportError:  # direct execution: python tests/test_travel_doc_lab.py
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import travel_doc_surfaces as _tds

# WO-TRAVEL-DOC-UNIFY-01 Phase 5: these used to be private Path
# literals. Six suites each kept a copy, so moving a file meant
# six edits and the sixth was the one always missed. The paths,
# the roles and the comment strippers now live in
# tests/travel_doc_surfaces.py; the names below are aliases, kept
# so the assertions read exactly as they did before.
_JS = _tds.UNIFIED_JS.path
_CSS = _tds.UNIFIED_CSS.path
_HTML = _tds.DEV_HARNESS.path


def _stripped_js() -> str:
    # Phase 5: the stripper moved to Surface.stripped(). WHY it has to be
    # string-aware is recorded there, and it matters here: a naive
    # comment regex reads the "//" inside "http://localhost:8000"
    # (travel-doc-lab.js:40) as a line comment and blinds every
    # banned-token scan below from there to end of line.
    return _tds.UNIFIED_JS.stripped()


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
    return _tds.UNIFIED_CSS.stripped()


def _stripped_html() -> str:
    return _tds.DEV_HARNESS.stripped()


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

    def test_the_unified_module_never_loads_the_retired_one(self):
        # Renamed in Phase 5. The assertion is unchanged and still
        # required; the OLD NAME was the stale thing. "Lab does not
        # import production" described a world where the Documenter was
        # production and this module was an experiment beside it. Phase 4
        # inverted that: this module IS the operator Travel Doc, and the
        # rule reads forward now. The one surface an operator reaches
        # must not drag the retired module back in.
        #
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
        # WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 2 widened this
        # tuple by one entry, on purpose and with the failure read first.
        # /api/import-provenance is the fifth surface this module may
        # touch, and it is here because the Evidence Review Queue tab is
        # the operator screen over that lane -- GET /queue to read it,
        # promote/decision/trip/hidden to act on it.
        #
        # The gate is not weakened by the addition. It is a PREFIX
        # allow-list, so widening it admits exactly one lane and still
        # fails the build on anything else; and every route behind that
        # prefix is behind a default-off server flag, none of it is
        # narrator-facing, and none of it can delete. What this gate
        # exists to catch -- the module quietly growing a reach into
        # narrator or Travels-shelf state -- is unchanged.
        #
        # WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2D widened it again,
        # by one, on the same terms and with the failure read first: the
        # run was `unsanctioned endpoint in travel-doc-lab.js:
        # /api/google-picker`, which is the gate doing its job on a lane
        # it had never been told about. /api/google-picker is the sixth
        # surface, and it is here because the import strip at the top of
        # that same Evidence tab is the operator screen over the Google
        # Photos lane -- /health to ask whether the lane is even on,
        # POST /sessions to open a picking session, GET /sessions/{id} to
        # poll it, POST /sessions/{id}/ingest to stage what was picked.
        #
        # It is a SEPARATE prefix rather than a widening of the
        # import-provenance one because they are separate lanes with
        # separate gates: the queue needs HORNELORE_IMPORT_PROVENANCE and
        # the picker needs that flag AND HORNELORE_GOOGLE_PICKER. Folding
        # them together here would have let one prefix stand for two
        # different sets of preconditions.
        #
        # The same three properties hold of the new lane as of the last
        # one, which is why it is admitted: every route behind it is
        # behind default-off server flags, none of it is narrator-facing,
        # and the module surfaces none of its DELETE (the lane has exactly
        # one, it releases a session at Google, it answers
        # `batch_deleted: false`, and this UI does not call it).
        allowed = ("/api/trips", "/api/photos/", "/api/people",
                   "/api/chat/ws", "/api/import-provenance",
                   "/api/google-picker")
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

    def test_both_timers_stop_at_destroy(self):
        r"""RETIRED AND REPLACED 2026-07-28, in place rather than deleted.

        This test was `test_lori_send_retry_timer_stops_at_destroy`. Its
        comment read `The file's only timer`, and its first assertion was:

            self.assertEqual(
                len(re.findall(r"\bsetTimeout\(|\bsetInterval\(", src)), 1,
                "a second timer appeared; it needs its own destroyed guard",
            )

        WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2D added the second
        timer -- the Google Photos selection poll -- and this assertion is
        what caught it, before any human read the diff. That is the whole
        point of counting: the message it failed with was already the
        instruction ("it needs its own destroyed guard"), so the count is
        kept and only the number moves.

        WHAT THE TWO TIMERS ARE, AND WHY THEIR GUARDS DIFFER. The Lori
        retry ladder is a self-re-entering function that stores no handle,
        so there is nothing for destroy() to clear and its only possible
        guard is the `destroyed` check at the top of its own body. The
        picker poll is armed from the module var `_pickerPollTimer`, so it
        is guarded twice: the same check inside its callback, AND
        pickerPollStop() in destroy(), which clears the pending handle.
        Neither shape is wrong -- a handle nobody stores cannot be
        cleared -- but the shared, non-negotiable half is the `destroyed`
        check, and that is what is asserted of both.

        The count stays exact. A third timer must fail here and be
        described, the same way this one was.
        """
        src = _stripped_js()
        self.assertEqual(
            len(re.findall(r"\bsetTimeout\(|\bsetInterval\(", src)), 2,
            "a third timer appeared; it needs its own destroyed guard",
        )

        # Both are checked by slicing the real body and reading its FIRST
        # statement, not by looking inside a fixed-width window. The old
        # version took `src[i:i + 160]` and that window stopped reaching
        # the guard the moment 2D grew the comment above it -- turning a
        # correct guard into a red test, which is the failure mode
        # _destroy_body() above already carries a comment about. "First
        # statement" is also the stronger claim: a `destroyed` check
        # somewhere in the body is not the same promise as one that runs
        # before the body does anything.
        def first_statement(body):
            lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
            return lines[1] if len(lines) > 1 else ""

        # 1. The Lori send retry ladder. Unguarded it keeps retrying for
        #    up to 5s (20 x 250ms) past teardown and signs off by writing
        #    "Lori connection unavailable." into a log node that is no
        #    longer in the document.
        i = src.index("function trySend(attempt)")
        ladder = src[i:src.index("})(0);", i)]
        self.assertIn("setTimeout(", ladder, "the ladder re-arms somewhere else now")
        self.assertEqual("if (destroyed) return;", first_statement(ladder),
                         "the retry ladder does not check destroyed first")

        # 2. The picker selection poll. Unguarded it wakes up to 30s past
        #    teardown, writes to `st` and repaints a host the shell has
        #    already handed on to something else. Its callback clears its
        #    own handle first -- a timer that has fired is no longer
        #    pending and leaving the var set would make pickerPollStop()
        #    lie -- so the guard is the second statement, not the first,
        #    and it still precedes every effect.
        j = src.index("function pickerPollArm(")
        arm = src[j:src.index("\n  }", j)]
        self.assertIn("setTimeout(", arm, "the poll is armed somewhere else now")
        cb = arm[arm.index("setTimeout("):]
        self.assertIn("if (destroyed) return;", cb[:cb.index("pickerCheck(")],
                      "the poll callback reaches pickerCheck() without "
                      "checking destroyed")

        # And the half the ladder cannot have: the handle is cleared on
        # the way out, so a torn-down mount leaves nothing pending at all
        # rather than one timer that will wake and return.
        self.assertIn("pickerPollStop()", _destroy_body())
        self.assertIn("clearTimeout(_pickerPollTimer)",
                      src[src.index("function pickerPollStop("):])

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
        p = _tds.MOUNT_LIVENESS_HARNESS.path
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

    def test_day_card_is_one_control_and_carries_no_action_row(self):
        """WO-TRIP-PLAN-AS-HUB-01 Phase A instruction 4.

        [This test was `test_day_card_actions_are_full_labels_in_one_order`
        until 2026-07-28. It asserted that `dayActionRow` existed, that it
        built the labels "Talk with Lori", "Attach photos", "Add note" and
        "Edit day", and that they appeared in that order inside the shared
        builder. Every one of those claims was true and is now false: the
        row is gone, and the reason is worth keeping rather than deleting.

        Five buttons on a card that is itself a link asked the operator to
        choose an action before choosing a day, and four of the five only
        made sense once the day was open anyway. The actions did not
        disappear -- they moved into the day workspace, each one beside
        the section it acts on. So the assertion inverts: what the old
        test required to be present, this one requires to be absent.]
        """
        src = _stripped_js()
        # The builder and its call site are both gone. Asserting on the
        # DECLARATION, not on the word: the retirement comment in the
        # module names dayActionRow, as this docstring does.
        self.assertNotIn("function dayActionRow", src)
        self.assertNotIn("dayActionRow(day)", src)
        # The card is the control, and it says so in words as well as with
        # a cursor -- a pointer cursor is invisible to a keyboard user and
        # does not exist on a touch screen.
        self.assertIn("tdl-day-open-hint", src)
        i = src.index("function renderDayCard(")
        card = src[i:src.index("\n  }", i)]
        self.assertIn("function openThisDay()", card)
        self.assertIn('card.setAttribute("role", "button")', card)
        self.assertIn("card.tabIndex = 0", card)
        # Reachable by keyboard, not only by mouse.
        self.assertIn('e.key === "Enter"', card)
        self.assertIn('e.key === " "', card)

    def test_opening_a_day_from_the_card_asks_before_discarding_edits(self):
        # Phase A instruction 10. renderDayCard's click handler was the
        # ONE path into the day workspace that skipped dayFormDirtyBlocks
        # -- and clicking another day is the most likely way an operator
        # loses a half-typed one, because it does not feel like leaving.
        src = _stripped_js()
        i = src.index("function renderDayCard(")
        card = src[i:src.index("\n  }", i)]
        j = card.index("function openThisDay()")
        body = card[j:card.index("\n    }", j)]
        self.assertIn("if (dayFormDirtyBlocks()) return;", body)
        # The guard has to come FIRST: after the assignment it would be
        # asking about a day the operator has already left.
        self.assertLess(body.index("dayFormDirtyBlocks"),
                        body.index("st.selectedDayId = day.id"))

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
        """The day workspace's sections, in render order.

        [Until 2026-07-28 this asserted the headings "Overview", "Notes",
        "Photos", "Sources" and "Lori captures", and that Overview was the
        only default-open one via
        `insSection("overview", "Overview", true)`. Phase A instruction 5
        renamed and reorganised the panel as the day workspace: "Overview"
        became "Day" because the operator is looking at a day and not at
        an overview of one; "Notes" and "Lori captures" stopped being
        top-level sections and became parts of "Story", which is what they
        both are; and "Places and meals" and "More details" were added.
        The KEY is still "overview" -- renaming a state key would have
        silently reset every operator's open/closed sections, and the
        heading is the part that had to change.]
        """
        src = _stripped_js()
        self.assertIn("tdl-ins-sec", src)
        # Headings, in the order they are built. Pinned as an ordered list
        # rather than as five unordered assertIns, because the ORDER is
        # the instruction: the day, then what is on it, then the story,
        # then the administrative tail.
        heads = re.findall(r'insSection\("(\w+)",', src)
        self.assertEqual(
            heads, ["overview", "photos", "story", "places", "sources", "more"],
            "day workspace section order drifted")
        for section in ("\"Day\", true)", "Story", "Places and meals",
                        "Sources", "More details"):
            self.assertIn(section, src)
        # Day is still the only default-open section, and still keyed
        # "overview" so saved open/closed state survives the rename.
        self.assertIn('insSection("overview", "Day", true)', src)
        self.assertEqual(len(re.findall(r'insSection\("\w+", [^;]*?, true\)', src)), 1,
                         "exactly one section opens by default")


class TripPlanAsHubTest(unittest.TestCase):
    """WO-TRIP-PLAN-AS-HUB-01 Phase A -- Trip Plan is the page you work on.

    Chris's report was that there were too many tabs across the top and
    that the trip and its days were buried among them. The fix is mostly
    subtraction: ten tabs become two plus a Review menu, the Lori tab goes
    (it duplicated an overlay that already existed), the day card loses
    its button row, and the day inspector -- which was already the modal
    he was asking for -- gets renamed and reordered as the day workspace.

    These tests guard the SHAPE of that, because shape is exactly what a
    later feature erodes one reasonable addition at a time. The rationale
    Chris gave for the split is the thing being pinned: "Your normal
    workflow is the trip and its days. Evidence is an administrative
    review step."
    """

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def test_the_bar_carries_two_primary_tabs_and_a_review_menu(self):
        self.assertNotIn("var TABS", self.src)
        self.assertIn("var PRIMARY_TABS", self.src)
        self.assertIn("var REVIEW_TABS", self.src)
        prim = re.search(r"var PRIMARY_TABS = \[[\s\S]*?\];", self.src).group(0)
        self.assertEqual(re.findall(r'\["(\w+)"', prim), ["plan", "photos"])
        rev = re.search(r"var REVIEW_TABS = \[[\s\S]*?\];", self.src).group(0)
        self.assertEqual(
            re.findall(r'\["(\w+)"', rev),
            ["evidence", "notes", "sources", "travelogue", "draft", "captured"],
            "Review menu contents drifted from the 2026-07-28 instruction")

    def test_trip_plan_is_the_default_entry_page(self):
        # Instruction 2 was already satisfied when Phase A opened; this
        # pins it so a later default cannot move without a decision.
        self.assertIn('tab: "plan",', self.src)

    def test_review_menu_is_a_native_details_with_no_global_listener(self):
        # A hand-rolled popover needs a document-level click listener to
        # close on an outside click, and this module has a destroy()
        # contract that a stray global listener quietly breaks -- the same
        # argument the timer inventory makes about handles nobody stores.
        self.assertIn('document.createElement("details")', self.src)
        self.assertIn("tdl-tabmenu-summary", self.src)
        self.assertIn("tdl-tabmenu-panel", self.src)
        # NOT "no global listener exists" -- one does, and correctly:
        # the lightbox's Escape/arrow keydown, paired with a
        # removeEventListener in destroy(). The claim is that the Review
        # menu added no SECOND one, so the count is pinned the way the
        # timer inventory pins its own. A third listener has to fail here.
        adds = re.findall(r"document\.addEventListener\(\"(\w+)\"", self.src)
        self.assertEqual(adds, ["keydown"],
                         "a document-level listener was added; it needs a "
                         "matching removeEventListener in destroy()")
        self.assertIn('document.removeEventListener("keydown"', self.src)
        # An open review surface is NAMED on the bar. A menu that
        # collapsed back to the word "Review" would leave the operator on
        # a screen with nothing saying where they are.
        self.assertIn("Review \u00b7 ", self.src)
        self.assertIn("function reviewTabLabel(", self.src)
        for sel in (".tdl-tabmenu", ".tdl-tabmenu-summary",
                    ".tdl-tabmenu-panel"):
            self.assertIn(sel, self.css, sel)
        # The panel is positioned against the menu itself, so nothing
        # further up the tree has to cooperate.
        i = self.css.index(".tdl-tabmenu {")
        self.assertIn("position: relative",
                      self.css[i:self.css.index(".tdl-tabmenu-summary")])

    def test_the_review_tabs_still_load_their_data_on_entry(self):
        # setTab() carries four lazy fetches. They were wired when these
        # were top-level tabs, and a menu that navigated without them
        # would render four empty screens.
        i = self.src.index("function setTab(")
        body = self.src[i:self.src.index("\n  }", i)]
        for hook in ("travelogue", "evidence", "picker", "captured"):
            self.assertIn(hook, body, hook)

    def test_the_lori_tab_is_gone_and_the_overlay_is_the_only_route(self):
        # The Lori tab and the Lori overlay were two doors to one room,
        # and the tab was the worse one: it left the day behind, so the
        # operator came back to the top of the trip.
        self.assertNotIn('["lori", "Lori"]', self.src)
        self.assertNotIn("function renderLoriTab", self.src)
        self.assertNotIn('case "lori"', self.src)
        # Anything still asking for it lands on Trip Plan rather than on a
        # blank tab: old bookmarks and any missed call site both survive.
        self.assertIn('if (tab === "lori") tab = "plan";', self.src)
        # The overlay -- which already returned to the same day -- stays.
        for fn in ("function openLoriOverlay(", "function closeLoriOverlay(",
                   "function openLoriOverlayForPhoto("):
            self.assertIn(fn, self.src, fn)

    def test_technical_identifiers_are_not_in_the_normal_view(self):
        """Instruction 6. "You should not normally see an
        active_trip_day_id."

        The wire contract keeps the field -- Lori is scoped by it and
        section 10.2 requires the destination to be explicit -- so this is
        a test about what is PAINTED, not about what is sent.
        """
        # Still sent. Removing it would be a scope bug, not a tidy-up.
        self.assertIn("active_trip_day_id:", self.src)
        # Not painted. The scope chip used to print a truncated uuid, and
        # the overlay header printed the raw id beside it.
        self.assertNotIn('" active_trip_day_id=" + String(', self.src)
        self.assertNotIn("surface: travel_doc_modal", self.src)
        # The one place an identifier is still shown on purpose is More
        # details, which is collapsed by default and is where an operator
        # who needs to quote an id to a developer will go.
        i = self.src.index('insSection("more"')
        more = self.src[i:self.src.index("body.appendChild(more);", i)]
        self.assertIn("active_trip_day_id = ", more)
        # And it is closed, so the normal view stays clean.
        self.assertIn('insSection("more", "More details", false)', self.src)

    def test_photo_actions_offer_move_and_remove_but_never_a_second_place(self):
        """Chris's ruling of 2026-07-28, first half.

        "One photo may have one placement per trip. Use Move, not Also
        show on another day."

        No migration was needed: trip_photo_links has carried
        UNIQUE (trip_id, photo_id) since migration 0015 and it has never
        been dropped. The database already refused a second placement;
        what was missing was a UI that agreed with it, because an offer
        the database will reject is a promise the operator gets to
        discover as an error.
        """
        self.assertIn("Move to this day", self.src)
        self.assertIn("Remove from this day", self.src)
        self.assertNotIn("Also show on another day", self.src)
        self.assertNotIn("Add to another day", self.src)

    def test_the_photo_drawer_empty_state_spans_the_grid(self):
        # Instruction 9. The drawer's empty message is appended INTO
        # .tdl-picker-grid, so it was laid out as one 118px thumbnail
        # cell: a two-sentence explanation rendered in a column the width
        # of a photo. Spanning every track is the whole fix.
        i = self.css.index(".tdl-picker-grid .tdl-empty")
        rule = self.css[i:self.css.index("}", i)]
        self.assertIn("grid-column: 1 / -1", rule)
        # Scoped, not global: .tdl-empty is used in a dozen non-grid
        # places where grid-column means nothing. Anchored to the start of
        # a line, because the unanchored form is a substring of the scoped
        # rule it was supposed to be distinguishing itself from -- it
        # matched the very rule asserted three lines above.
        i = self.css.index("\n.tdl-empty {")
        self.assertNotIn("grid-column", self.css[i:self.css.index("}", i)])

    def test_the_day_card_grid_lost_its_action_column(self):
        i = self.css.index(".tdl-day-card {")
        rule = self.css[i:self.css.index("}", i)]
        self.assertIn("grid-template-columns: 86px minmax(0, 1fr);", rule)
        self.assertIn("cursor: pointer", rule)
        self.assertNotIn(".tdl-day-actions {", self.css)
        # Focus is visible, or the keyboard route added above is one no
        # keyboard user can follow.
        self.assertIn(".tdl-day-card:focus-visible", self.css)


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

    def test_reconcile_banners_and_automatic_day_generation(self):
        """Phase A instruction 3: day cards come from the trip dates.

        [This test was `test_reconcile_banners_and_generate_relabel` until
        2026-07-28, and it required four strings Phase A retired: the
        toolbar button "Generate / reconcile day cards", the missing-days
        banner "Trip dates include N day(s) not yet in the calendar." with
        its "Add missing days" control beside it, and the outside-date
        banner's "Review outside-date days" button.

        The button and the banner went for the same reason: both asked the
        operator to perform the system's own bookkeeping. Day cards are a
        function of the trip dates, so a screen that announces "N days are
        missing" and offers to add them is describing a state that should
        never have been visible. Generation now happens on load.

        What survives, and is asserted below, is the half of the reconcile
        flow that is a real decision rather than bookkeeping: day cards
        OUTSIDE the current dates. Those hold the operator's work, and
        Hornelore refuses to drop them and shows what is on them instead
        -- Chris's ruling of 2026-07-28. The manual generate path is kept
        too, in the reconcile drawer, because a manual re-run is a
        reasonable thing to have once the automatic one has reported a
        failure.]
        """
        src = _stripped_js()
        # Automatic generation, once per (trip, missing-date set) per
        # page load. [This read "once per trip per page load" until
        # 2026-07-28. That was the shipped behaviour and it was wrong ---
        # see test_the_auto_generation_guard_follows_the_missing_dates
        # below, and Chris's review that found it.]
        self.assertIn("function maybeAutoAddMissingDays()", src)
        self.assertIn("autoDaysTried", src)
        i = src.index("function reloadReconcile(")
        self.assertIn("maybeAutoAddMissingDays()", src[i:i + 400])
        # A failure to generate is REPORTED, never swallowed: silence
        # would look exactly like a trip with no dates.
        j = src.index("function maybeAutoAddMissingDays()")
        auto = src[j:src.index("\n  }", j)]
        self.assertIn("st.daysWarning", auto)
        self.assertIn(".catch(", auto)
        # The manual path is kept, in the drawer.
        self.assertIn("Add missing days", src)
        # The outside-date banner and the never-delete language stay.
        # [This asserted the banner said "They were kept, not deleted"
        # until 2026-07-28. That sentence was true of EVERY out-of-range
        # card while this surface could not remove one; correction 2
        # removes the empty ones on the save that pushes them out, so
        # the banner would have been promising the operator something
        # about cards that are no longer there to promise it about. The
        # claim the assertion was really protecting -- a card with work
        # on it is never deleted -- is asserted below, in the wording
        # that now carries it.]
        self.assertIn("outside the current trip dates", src)
        self.assertIn("kept to protect your notes", src)
        self.assertIn("Cards with your work on them are kept, ", src)
        self.assertIn("never deleted", src)
        self.assertIn("See what is on them", src)
        # The UI still reads the read-only preview endpoint.
        self.assertIn("/days/reconcile-preview", src)
        self.assertIn("reloadReconcile", src)

    def test_the_auto_generation_guard_follows_the_missing_dates(self):
        """Chris's correction 1, 2026-07-28.

        "Replace the once-per-trip auto-generation guard with a guard
        tied to the current missing-date set, or reset it after trip-date
        edits."

        His scenario: open a trip, let the automatic generation run and
        mark the trip tried, open Trip setup, widen July 14-19 to
        July 14-21, come back. The preview reports July 20 and 21
        missing, the trip is already marked tried, and nothing is added
        until the surface is remounted. That contradicts the promise the
        phase makes.
        """
        src = _stripped_js()
        j = src.index("function maybeAutoAddMissingDays()")
        auto = src[j:src.index("\n  }", j)]
        # The key is built from the trip AND the dates, and it is sorted:
        # the same gap reported in a different order is the same gap.
        self.assertIn("function autoDaysKey(", src)
        k = src.index("function autoDaysKey(")
        keyfn = src[k:src.index("\n  }", k)]
        self.assertIn("missing.slice().sort().join(", keyfn)
        self.assertIn("String(tripId)", keyfn)
        # The guard reads and writes the composite key.
        self.assertIn("autoDaysTried[key]", auto)
        # And the retired per-trip key is gone from the code. The words
        # survive in the comment that records the retirement, so this is
        # asserted against the subscript form, not the identifier.
        self.assertNotIn("autoDaysTried[st.trip.id]", src)

    def test_the_auto_generation_guard_still_terminates(self):
        """A key that moves with the data is not a bound by itself.

        The retired per-trip key could fire at most once per trip per
        mount, so add -> reload -> add was bounded by construction. The
        missing-date key is bounded only while each pass strictly shrinks
        the missing set, which is the normal case and not a guarantee.
        The ceiling is separate from the key on purpose and says so.
        """
        src = _stripped_js()
        self.assertIn("var AUTO_DAYS_MAX_ATTEMPTS", src)
        j = src.index("function maybeAutoAddMissingDays()")
        auto = src[j:src.index("\n  }", j)]
        self.assertIn("autoDaysAttempts >= AUTO_DAYS_MAX_ATTEMPTS", auto)
        self.assertIn("autoDaysAttempts += 1", auto)
        # Hitting the ceiling is reported, not silent: a calendar that
        # quietly stopped filling itself in looks like a trip with no
        # dates.
        self.assertIn("stopped generating automatically after", auto)
        self.assertIn("st.daysWarning", auto)

    def test_a_successful_auto_generation_clears_its_own_warning(self):
        """applyTripWarnings already follows this rule for the save path.

        A warning left standing after the thing it complained about
        succeeded reads as an unresolved problem, and the automatic add
        can now legitimately run more than once in a session, so a
        failure followed by a success is a shape that actually happens.
        """
        src = _stripped_js()
        j = src.index("function maybeAutoAddMissingDays()")
        auto = src[j:src.index("\n  }", j)]
        self.assertIn('st.daysWarning = "";', auto)
        # The failure still says where to go by hand.
        self.assertIn("Open the reconcile", auto)

    def test_shrinking_dates_only_ever_removes_a_card_that_holds_nothing(self):
        """The wall moved forward on 2026-07-28. Doctrine 1.11.

        [This test was test_shrinking_dates_never_drops_a_day_card_from_
        this_surface, and it asserted the stronger claim that this
        surface has no route that removes a day card AT ALL. Its
        docstring recorded the gap as a decision: "Phase A implements the
        refusal. It does NOT implement the drop ... Dropping the empty
        cards needs a server route and is later work." Chris's review of
        Phase A asked for that work, on this phase: "Implement the
        complete shrinking-date rule: remove empty out-of-range days;
        refuse and clearly list out-of-range days containing work." The
        server route the old wall was waiting for is the one it named, so
        this is a wall moved forward and told why -- not a wall dropped.]

        What is still walled, and is the half that was always the point:
        the removal goes through the reconcile POST and nowhere else, no
        prune/drop/remove route was invented here, and the automatic
        add-missing lane still only adds.
        """
        src = _stripped_js()
        self.assertIn("out_of_range_days", src)
        # Still no removal route of this surface's own invention. The one
        # deletion path is the reconcile POST, whose server side decides
        # emptiness again inside its write transaction.
        for banned in ("/days/prune", "/days/drop", "days/remove"):
            self.assertNotIn(banned, src, banned)
        self.assertIn("drop_empty_out_of_range: true", src)
        # The automatic reconcile call adds and does nothing else. It is
        # a different lane from the trip-date save and must not acquire
        # the flag: auto-add fires on a preview load, and a removal that
        # fires on a page view is not a removal anyone asked for.
        j = src.index("function maybeAutoAddMissingDays()")
        auto = src[j:src.index("\n  }", j)]
        self.assertIn("add_missing: true", auto)
        self.assertNotIn("drop", auto)
        self.assertNotIn("remove", auto)

    def test_a_leaving_day_with_work_on_it_refuses_in_chriss_words(self):
        """The refusal message is quoted, not paraphrased.

        Chris wrote the message he wanted, down to the bullet shape:

            The trip dates cannot be shortened yet.

            These days contain work:
            * July 19 - 4 photos and 1 story note
            * July 20 - 2 Lori captures

            Move or remove that content, then try again.

        Asserted as literals because a rewrite into house voice is
        exactly the kind of change nobody would think to mention.
        """
        src = _stripped_js()
        self.assertIn("The trip dates cannot be shortened yet.", src)
        self.assertIn("These days contain work:", src)
        self.assertIn("Move or remove that content, then try again.", src)
        # Per day: the long date, then what is on it.
        self.assertIn("function longDate(", src)
        self.assertIn("function holdsPhrase(", src)
        j = src.index("function showDateRefusal(")
        box = src[j:src.index("\n  }", j)]
        self.assertIn("longDate(day.date)", box)
        self.assertIn("holdsPhrase(dayHolds(day))", box)
        # Chris's own vocabulary for what a day holds.
        self.assertIn('"Lori capture", "Lori captures"', src)
        self.assertIn('"story note", "story notes"', src)
        self.assertIn('"photo", "photos"', src)

    def test_the_refusal_happens_before_the_dates_are_saved(self):
        """Order is the whole feature.

        Chris named the failure this prevents: "the trip header could
        say July 14-18 while July 19 and July 20 still appear below." A
        check that ran after the PATCH would produce exactly that -- the
        header already moved, the cards still there, and a message
        explaining a state the operator is already looking at.
        """
        src = _stripped_js()
        j = src.index("function renderTripEditorDrawer()")
        ed = src[j:src.index("\n  function renderRegionEditorDrawer(", j)]
        self.assertIn("daysLeavingWindow(vStart.value, vEnd.value)", ed)
        patch = ed.index('api("/api/trips/" + encodeURIComponent(trip.id), {')
        self.assertLess(ed.index("var blocking = leaving.filter"), patch)
        self.assertLess(ed.index("showDateRefusal(refusalEl, blocking)"), patch)
        # A refusal leaves the drawer usable: the button comes back and
        # the operator's typed dates are not repainted away.
        self.assertIn("saveBtn.disabled = false;", ed)
        self.assertNotIn("showDateRefusal(refusalEl, blocking);\n"
                         "            renderAll()", ed)
        # Only a save that actually pushes cards out asks for a removal.
        self.assertIn("var shrinking = leaving.length > 0;", ed)
        self.assertIn("shrinking ? dropEmptyOutOfRangeDays(trip.id) : null",
                      ed)
        # An already-preserved card must never block a date edit: one old
        # card with a note on it would freeze the trip's dates forever.
        j = src.index("function daysLeavingWindow(")
        leaving = src[j:src.index("\n  }", j)]
        self.assertIn("st.days", leaving)
        self.assertNotIn("preservedDays", leaving)

    def test_emptiness_is_not_measured_from_the_display_counts(self):
        """The decision this feature lives or dies on.

        Each day card carries `counts` merged in by the /days route, and
        reaching for them here is the obvious simplification. It would
        also make the feature ship and do nothing: those counts include
        photos matched to the day by taken-date and notes inherited
        through the day's stop or region, and generated cards are
        auto-assigned a region -- so on any trip with region-scoped notes
        every card reports content and every shrink is refused.

        Emptiness is what is ATTACHED to this card (trip_day_id) plus
        what was typed into the day row.
        """
        src = _stripped_js()
        j = src.index("function dayHolds(")
        holds = src[j:src.index("\n  }", j)]
        self.assertIn("trip_day_id === day.id", holds)
        self.assertNotIn("day.counts", holds)
        self.assertNotIn("counts.", holds)
        j = src.index("function dayOwnContent(")
        own = src[j:src.index("\n  }", j)]
        self.assertIn("DAY_OWN_TEXT_FIELDS", own)
        self.assertIn("trip_stop_id", own)
        self.assertNotIn("day.counts", own)
        # The typed fields are the day row's own columns, all of them.
        for f in ("morning_notes", "afternoon_notes", "evening_notes",
                  "main_location", "lodging_base"):
            self.assertIn(f, src, f)
        for f in ("places_visited_json", "meals_json"):
            self.assertIn(f, src, f)

    def test_the_removal_is_reported_after_it_happens(self):
        """"Without asking" is a rule about prompts, not about silence.

        Chris: "Empty days are dropped without asking." A card that was
        on the screen a moment ago and is gone now, with nothing on
        screen admitting it, is the silent deletion this doctrine exists
        to prevent -- and reporting after the fact is not asking.

        The other direction matters as much: the client decides
        emptiness from lists that exclude hidden rows, so the server can
        legitimately refuse a card the client thought was bare. Those
        come back in kept_out_of_range and have to be said out loud, or
        cards stay on screen that the operator was told would go.
        """
        src = _stripped_js()
        j = src.index("function dropEmptyOutOfRangeDays(")
        drop = src[j:src.index("\n  }", j)]
        self.assertIn("dropped_days", drop)
        self.assertIn("kept_out_of_range", drop)
        self.assertIn("st.daysNotice", drop)
        self.assertIn("st.daysWarning", drop)
        # A failed tidy-up must not read as a failed save.
        self.assertIn("The trip dates were saved", drop)
        # The banner exists, is dismissible, and is not styled as a
        # warning -- see the note on st.daysNotice.
        self.assertIn("tdl-reconcile-notice", src)
        css = _stripped_css()
        self.assertIn(".tdl-reconcile-notice", css)
        self.assertIn(".tdl-date-refusal-list", css)
        # It belongs to the trip it was produced for.
        j = src.index("function selectTrip(")
        sel = src[j:src.index("\n  }", j)]
        self.assertIn('st.daysNotice = "";', sel)

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
        # Phase 5: the path and the stripper both come from the map.
        self.src = _tds.RETIRED_JS.stripped()

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


class EvidenceReviewQueueTest(unittest.TestCase):
    """WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 2 — the operator screen.

    Phase 1 shipped GET /queue and Phase 3 shipped POST
    /candidates/{id}/promote. This suite pins the tab built over them,
    and it pins the three CLOSED decisions as much as it pins the
    feature, because the decisions are the part a later edit is most
    likely to undo by accident:

      1. placement is trip granularity and nothing finer;
      2. the states are the five that shipped, and no others;
      3. promotion is a separate explicit call, never a flag on the
         decision.
    """

    def setUp(self):
        self.src = _stripped_js()
        self.css = _stripped_css()

    def _section(self):
        # Exact slice, not a fixed-width window: the queue starts at its
        # own constants and ends where Story Notes begins. A fixed window
        # either clips the constants off the front (and stops seeing the
        # action labels) or overruns into code this suite has no business
        # asserting about — both were observed while writing this.
        i = self.src.index("var EVIDENCE_BASE")
        return self.src[i:self.src.index("function renderNotes(", i)]

    def test_evidence_tab_is_registered(self):
        self.assertIn('["evidence", "Evidence"]', self.src)
        self.assertIn('case "evidence": return renderEvidence();', self.src)

    def test_queue_is_read_through_the_phase_1_route(self):
        i = self.src.index("function evidenceQueryPath(")
        block = self.src[i:i + 700]
        self.assertIn('"/queue', block)
        # person_id is required by the route and is never defaulted: a
        # queue that inferred its person could show a reviewer somebody
        # else's evidence.
        self.assertIn("person_id=", block)
        self.assertIn("trip_id=", block)
        self.assertIn("state=", block)
        self.assertIn("include_hidden=1", block)

    def test_flag_off_renders_as_configuration_not_as_an_error(self):
        # Every route in the lane answers 404 while the server flag is
        # off. Painting that as an error would send the operator hunting
        # for a broken trip, so the 404 arm is pinned to set its own
        # state and to CLEAR the error rather than set one.
        i = self.src.index("function reloadEvidence(")
        block = self.src[i:i + 1200]
        self.assertIn("e.status === 404", block)
        self.assertIn("st.evidenceOff = true", block)
        self.assertIn('st.evidenceError = ""', block)
        self.assertIn("tdl-erq-off", self.src)
        self.assertIn(".tdl-erq-off", self.css)

    def test_screen_shows_the_six_things_build_point_6_asks_for(self):
        sec = self._section()
        # counts + queue depth
        self.assertIn("state_counts", sec)
        self.assertIn("queue_depth", sec)
        # batch and trip, both inline on the row
        self.assertIn('"batch · "', sec)
        self.assertIn('"trip · "', sec)
        # filename AND external id -- they answer different questions
        # (what the operator called it vs what the provider called it)
        # and collapsing them loses one of the two.
        self.assertIn('"file "', sec)
        self.assertIn('"external id "', sec)
        # match_reason and state
        self.assertIn("function renderMatchReason(", self.src)
        self.assertIn("tdl-erq-state-badge", sec)

    def test_match_reason_is_printed_verbatim_never_paraphrased(self):
        # The repository round-trips match_reason unchanged and says why:
        # "round-trip, never a summary, never prose". A screen that
        # paraphrased it would be the summary that refusal prevents.
        i = self.src.index("function renderMatchReason(")
        block = self.src[i:i + 1400]
        self.assertIn("Object.keys(", block)
        self.assertIn("match_confidence", block)
        self.assertIn("tdl-erq-reason-key", block)
        self.assertIn("tdl-erq-reason-val", block)

    def test_state_rail_offers_exactly_the_five_shipped_states(self):
        i = self.src.index("var EVIDENCE_STATES")
        block = self.src[i:self.src.index("]", self.src.index("]", i) + 1) + 400]
        for state in ("pending", "accepted", "rejected", "duplicate",
                      "error"):
            self.assertIn('"%s"' % state, block)
        # Decision 2: `changed` and `skipped` did NOT become states, and
        # this screen does not invent them.
        for ghost in ("changed", "skipped"):
            self.assertNotIn('"%s"' % ghost, block)

    def test_promote_then_accept_is_two_requests_in_that_order(self):
        # Decision 3, option B: promotion is an explicit separate route.
        # The promote call must come first, the decision must consume the
        # photo_id it returned, and nothing may invent a photo_id.
        i = self.src.index("function promoteAndAccept(")
        block = self.src[i:i + 1800]
        p = block.index('"/promote"')
        d = block.index('"/decision"')
        self.assertLess(p, d, "accept must follow promote, not precede it")
        self.assertIn("out.photo_id", block)
        self.assertIn('state: "accepted"', block)
        self.assertIn("photo_id: photoId", block)

    def test_the_halfway_state_is_reported_in_those_words(self):
        # Promoted-but-not-accepted is reachable, recoverable, and safe to
        # retry (promotion is idempotent). The operator is told all three
        # rather than left with a bare failure.
        i = self.src.index("function promoteAndAccept(")
        block = self.src[i:i + 1800]
        self.assertIn("still pending", block)
        self.assertIn("safe", block)

    def test_promote_uses_formdata_through_the_single_api_choke_point(self):
        i = self.src.index("function promoteAndAccept(")
        block = self.src[i:i + 1800]
        self.assertIn("new FormData()", block)
        self.assertIn('fd.append("file"', block)
        # No hand-set Content-Type: the browser must write its own so it
        # can append the multipart boundary.
        self.assertNotIn("Content-Type", block)
        self.assertNotIn("fetch(", block)

    def test_refusals_send_no_photo_id(self):
        # The decision route refuses a photo_id on any non-accepted state
        # (400). Sending one would buy a 400 that means nothing to the
        # operator.
        i = self.src.index("function renderEvidenceDecideDrawer(")
        block = self.src[i:i + 1800]
        self.assertIn("state_reason", block)
        self.assertNotIn("photo_id", block)

    def test_all_seven_row_actions_exist(self):
        sec = self._section()
        for label in ('"Promote + accept"', '"Reject"', '"Duplicate"',
                      '"Error"', '"Hide"', '"Unhide"', '"File to trip"'):
            self.assertIn(label, sec, label)

    def test_placement_is_trip_granularity_and_nothing_finer(self):
        # Decision 1: no migration 0038, so the import tables have no
        # column for a region, stop or day. The screen must not offer a
        # placement it cannot store.
        i = self.src.index("function renderEvidenceFileDrawer(")
        block = self.src[i:i + 1600]
        self.assertIn('"/trip"', block)
        self.assertIn('method: "PATCH"', block)
        self.assertIn("trip_id: sel.value || null", block)
        for finer in ("region_id", "stop_id", "day_id", "day_index"):
            self.assertNotIn(finer, block, finer)

    def test_hide_is_reversible_and_the_queue_has_no_delete(self):
        i = self.src.index("function setEvidenceHidden(")
        block = self.src[i:i + 600]
        self.assertIn('method: "PATCH"', block)
        self.assertIn("hidden: !!hidden", block)
        self.assertNotIn("DELETE", block)
        # Build point 12, module-wide for this lane: nothing aimed at
        # /api/import-provenance may be a DELETE.
        for m in re.finditer(re.escape("/api/import-provenance"), self.src):
            window = self.src[m.start():m.start() + 400]
            self.assertNotIn('method: "DELETE"', window,
                             "DELETE aimed at the import-provenance lane")

    def test_the_queue_adds_nothing_narrator_facing_and_no_lori_control(self):
        # Build points 10 and 11. Promotion creates a photo born not
        # narrator-facing and not approved for Lori; the screen must not
        # offer to change either, and must say so.
        sec = self._section()
        for banned in ("narrator_ready", "include_in_memoir",
                       "date_approved_for_lori",
                       "location_approved_for_lori"):
            self.assertNotIn(banned, sec, banned)
        self.assertIn("not narrator-facing", sec)

    def test_no_takeout_and_the_picker_stays_an_import_affordance(self):
        """RETIRED AND REPLACED 2026-07-28, in place rather than deleted.

        This test was `test_no_picker_and_no_takeout_in_this_phase` and it
        read, in full:

            # Build points 8 and 9 — the next epic step, not this one.
            sec = self._section()
            for banned in ("google_photos_picker", "google_takeout",
                           "Picker", "Takeout"):
                self.assertNotIn(banned, sec, banned)

        It was correct for exactly as long as build point 8 was the next
        step. WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2D took it, so
        two of those four strings are now supposed to be here and the
        assertion had to go. Deleting it outright would have thrown away
        the half that is still true along with the half that expired --
        and the half that is still true is the one that matters more,
        because it is the wall this lane could most plausibly be pushed
        through by accident.

        WHAT IS STILL FORBIDDEN, AND WHY EACH ONE. Takeout is untouched:
        build point 9 has not been done, no phase has started it, and a
        Takeout string appearing in this section would mean somebody
        started the next lane inside this one. And the picker, now that it
        IS here, is held to what it was allowed in as: an import
        affordance, not a review screen. Binding ruling 1.3 of
        docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md gives candidate
        review to the Evidence Review Queue alone, so the strip may open a
        session, check it, ingest it and reload the queue -- and may not
        grow a decision control of its own. The per-item run report it
        prints after an ingest is the thing most likely to drift into
        being a second queue, so the decision verbs are asserted absent
        from the section's picker half specifically.
        """
        sec = self._section()

        # Build point 9 -- not started, and not to be started here.
        for banned in ("google_takeout", "Takeout"):
            self.assertNotIn(banned, sec, banned)

        # Build point 8 -- present, and present as the four verbs 12.8
        # names. `google_photos_picker` and `Picker` are no longer banned
        # strings; they are expected ones.
        self.assertIn("/api/google-picker", sec)
        for verb in ('"/health"', '"/sessions"', '"/ingest"'):
            self.assertIn(verb, sec, verb)

        # Ruling 1.3. The strip's own half of the section carries no
        # decision control. These labels exist exactly once each in this
        # file, on the queue rows, and test_all_seven_row_actions_exist
        # above is what pins them there.
        picker = sec[sec.index("var PICKER_BASE"):]
        for verb in ('"Promote + accept"', '"Reject"', '"Duplicate"',
                     '"Error"', '"Hide"', '"Unhide"', '"File to trip"',
                     '"/promote"', '"/decision"'):
            self.assertNotIn(verb, picker,
                             f"the import strip grew a decision control: {verb}")

        # And the lane's one DELETE route is not surfaced. It is safe --
        # it releases the picking session at Google and answers
        # `batch_deleted: false` -- so this is a scope wall, not a safety
        # one, and it is asserted rather than assumed because "safe and
        # therefore fine to add" is how the first DELETE gets in.
        self.assertNotIn('method: "DELETE"', picker)

    def test_decided_rows_are_not_re_decidable_from_this_screen(self):
        # candidate_decide writes photo_id unconditionally, so re-deciding
        # an accepted candidate sets it to NULL and strands the photos row
        # it pointed at. That cleanup is a photo-lane act; it is not
        # something to trigger by mis-clicking in a queue. The refusal is
        # explained on the row rather than silently omitted.
        sec = self._section()
        self.assertIn("does not re-open a decision", sec)

    def test_evidence_state_clears_with_the_trip(self):
        i = self.src.index("function selectTrip(")
        block = self.src[i:i + 1600]
        for field in ("st.evidence = null", "st.evidenceDrawer = null",
                      "st.showHiddenEvidence = false"):
            self.assertIn(field, block, field)

    def test_only_the_review_tabs_are_exempt_from_the_trip_gate(self):
        # A deliberate structural change to the single repaint entry
        # point: the rows most in need of review are precisely the ones
        # not filed to a trip yet, so these tabs must render with no
        # trip selected.
        #
        # WO-POST-LORI-CLEANUP-AND-UNBLOCK-01 Lane 3 added the second
        # and, so far, last exemption -- "captured", the cross-trip
        # captured-note review, which is person-scoped for exactly the
        # same reason the evidence queue is. This assertion is pinned to
        # the literal so a third exemption cannot be added by accident:
        # every OTHER tab in this file describes one trip.
        self.assertIn(
            'if (!st.trip && st.tab !== "evidence" && st.tab !== "captured") {',
            self.src)
        exempt = re.findall(r'st\.tab !== "(\w+)"', self.src)
        self.assertEqual(sorted(set(exempt)), ["captured", "evidence"])

    def test_queue_drawers_add_no_native_dialogs(self):
        sec = self._section()
        for banned in ("window.prompt", "window.confirm", "window.alert",
                       "prompt(", "confirm(", "alert("):
            self.assertNotIn(banned, sec, banned)

    def test_promote_drawer_does_not_repaint_between_choose_and_upload(self):
        # Same FileList constraint as the intake drawer: an
        # <input type="file"> holds a FileList that script cannot write,
        # so a repaint between "choose file" and "Promote" throws the
        # operator's selection away with no way to restore it. The
        # validation failure therefore writes textContent directly.
        i = self.src.index("function renderEvidencePromoteDrawer(")
        block = self.src[i:self.src.index("function renderEvidenceDecideDrawer(")]
        choose = block.index('errEl.textContent =')
        self.assertNotIn("renderAll()", block[:choose])

    def test_queue_css_is_tdl_namespaced_and_does_not_collide(self):
        for cls in (".tdl-erq", ".tdl-erq-row", ".tdl-erq-summary",
                    ".tdl-erq-actions", ".tdl-erq-reason",
                    ".tdl-erq-state-badge", ".tdl-badge-unfiled"):
            self.assertIn(cls, self.css, cls)
        # The queue is namespaced tdl-erq-, NOT tdl-ev-: tdl-ev- was
        # already owned by the per-photo evidence panel, and reusing it
        # would restyle that panel from across the file. Two different
        # meanings of "evidence" live here; they do not share a prefix.
        sec = self._section()
        self.assertNotIn("tdl-ev-", sec)


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
        # Phase 5 narrowing: this test also asserted that
        # prodTravelDocUrl and the ?api= deep link are absent MODULE-WIDE.
        # That is the same claim about the same file that
        # test_the_fallback_deep_link_is_gone_module_wide makes below, so
        # a future change to the escape hatch had two owners and no clear
        # one. The module-wide claim belongs to that test; this one owns
        # the delete gate.
        self.assertTrue(
            _tds.RETIRED_JS.path.exists(),
            "travel-documenter.js must not be deleted — Phase 4 unmounts "
            "it from the shell, it does not remove the module")
        shell = _tds.SHELL_HTML.read()
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
