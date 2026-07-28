"""WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2D — the operator UI.

Spec 12.8 defines this phase as "minimal operator UI (open picker, check
selection, ingest, refresh queue), only after 2A and 2B are reviewed, so
the UI cannot hide a server defect". That sentence is the whole test plan:
the four verbs must be there, and everything the UI could plausibly hide
must be asserted absent rather than assumed absent.

These are source-pattern tests, like every other Travel Doc suite here --
this repository has no JS runner, so a suite either greps the module or
proves nothing. The paths and the string-aware comment stripper come from
tests/travel_doc_surfaces.py.

WHAT THIS SUITE IS ACTUALLY GUARDING, in the order the risks matter:

  1. CREDENTIALS. Spec 6 puts Chris's Google credentials out of an agent's
     reach entirely and spec 10.4 keeps token values, prefixes, tails and
     lengths out of every response and every log. The browser is the least
     trustworthy place any of it could land, and `baseUrl` -- the
     bearer-scoped download URL -- is the one a well-meaning change would
     render by accident while adding a thumbnail. Asserted absent by name.

  2. RULING 1.3. There is one review queue for photo candidates and the
     Picker does not get a second one. The per-item run report printed
     after an ingest is exactly the thing that drifts into being a queue,
     so its decision verbs are asserted absent.

  3. SPEC 10.2. The destination is explicit and supplied by the request.
     Nothing here may infer person_id or trip_id from the Google account,
     and there is no "if only one person exists, use that one".

  4. THE FLAG-OFF ARM, and the disambiguation that goes with it. A 404 may
     be read as "the lane is switched off" ONLY where a 404 can mean
     nothing else.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
import travel_doc_surfaces as _tds  # noqa: E402

_CSS = _tds.UNIFIED_CSS.path


class PickerUiTest(unittest.TestCase):
    def setUp(self):
        self.src = _tds.UNIFIED_JS.stripped()
        self.css = _tds.UNIFIED_CSS.stripped()

    def _block(self):
        """The picker block alone.

        It lives inside the slice test_travel_doc_lab.py takes with
        _section() -- between `var EVIDENCE_BASE` and `renderNotes(` --
        which is deliberate and is what makes the queue's own
        section-scoped gates (no native dialogs, nothing narrator-facing,
        no tdl-ev- prefix) cover this code without a line being added to
        any of them. This narrower slice starts at the picker's own
        constant so that the assertions BELOW about what the strip must
        not contain are not silently satisfied by the queue's half.
        """
        i = self.src.index("var PICKER_BASE")
        return self.src[i:self.src.index("function renderNotes(", i)]

    # ---------------------------------------------------- the four verbs

    def test_the_four_verbs_spec_12_8_asks_for_are_all_here(self):
        blk = self._block()
        self.assertIn('var PICKER_BASE = "/api/google-picker"', blk)
        # open a picking session
        self.assertIn('PICKER_BASE + "/sessions", { method: "POST"', blk)
        # check the selection
        self.assertIn('PICKER_BASE + "/sessions/" + encodeURIComponent(', blk)
        # ingest it
        self.assertIn('"/ingest"', blk)
        # refresh the queue -- the same reload the queue tab uses, not a
        # second read of a second list.
        self.assertIn("reloadEvidence()", blk)

    def test_health_is_probed_and_only_presence_booleans_are_rendered(self):
        blk = self._block()
        self.assertIn('PICKER_BASE + "/health"', blk)
        self.assertIn("credentials_complete", blk)
        self.assertIn("credentials_present", blk)
        # The route promises PRESENCE BOOLEANS -- "Booleans. Not values,
        # not prefixes, not lengths" is the route's own comment -- and the
        # strip has to treat them as booleans. What it may render is the
        # NAME of a variable that is not set, which is a configuration
        # fact. What it may never render is anything derived from a value.
        #
        # The first version of this assertion banned ".length" anywhere
        # near the panel and failed on `missing.length`, which is the
        # count of missing KEY NAMES and is exactly what the panel is
        # supposed to know. Banning a method name was the wrong shape of
        # test: the question is not which methods are called, it is what
        # they are called ON. So it is pinned to the two operations the
        # panel is allowed on the payload -- read the keys, test each
        # value for truth -- and nothing else may touch `present`.
        i = blk.index("var present = h.credentials_present")
        panel = blk[i:blk.index("return box;", i)]
        self.assertIn("Object.keys(present)", panel)
        self.assertIn("if (!present[k]) missing.push(k);", panel)
        self.assertEqual(panel.count("present["), 1,
                         "the credential panel reads a value more than once")
        for leak in ("present[k].", "present[k] +", "String(present",
                     "JSON.stringify(present"):
            self.assertNotIn(leak, panel,
                             f"the credential panel is using a value: {leak}")
        # And the only thing that reaches the screen is the key list.
        self.assertIn('missing.join(", ")', panel)

    # ------------------------------------------------- credentials (1)

    def test_no_credential_shaped_value_is_read_out_of_any_response(self):
        # The whole point of Phase 2's server design is that these never
        # cross the wire to the browser. This asserts the browser could
        # not render them even if a future route regressed and started
        # sending one: nothing in the module reads a field by these names.
        #
        # `session_id` is on the list with the rest because the Google
        # session id is deliberately not returned by POST /sessions at
        # all -- the batch id is the only handle this module holds, and
        # spec 10.4's key-hint list names `session_id` as a forbidden key.
        for leak in ("baseUrl", "base_url", "access_token", "refresh_token",
                     "client_id", "client_secret", "session_id",
                     "Authorization", "Bearer"):
            self.assertNotIn(leak, self._block(), leak)

    def test_no_google_javascript_and_no_popup(self):
        # picker_uri opens in Google's own hosted UI, in the operator's
        # own browser session, from a link he clicks himself. A Picker
        # SDK would put Google script on the page that also renders the
        # narrator's evidence; window.open would make this screen
        # responsible for a window it cannot see.
        blk = self._block()
        for banned in ("apis.google.com", "accounts.google.com",
                       'createElement("script"', "window.open",
                       "gapi", "google.picker"):
            self.assertNotIn(banned, blk, banned)
        # The link, and its opener guard: a new tab reached with
        # target=_blank gets a handle back to this page unless rel says
        # otherwise.
        self.assertIn('a.target = "_blank"', blk)
        self.assertIn('a.rel = "noopener noreferrer"', blk)

    def test_the_strip_goes_through_the_single_fetch_choke_point(self):
        # api() is the one fetch() in the module and the one place the
        # destroyed-mount guard lives. A second fetch here would be a
        # second async exit nobody is guarding.
        blk = self._block()
        self.assertNotIn("fetch(", blk)
        self.assertNotIn("XMLHttpRequest", blk)
        self.assertGreaterEqual(blk.count("api(PICKER_BASE"), 4)

    # ------------------------------------------------ ruling 1.3 (2)

    def test_the_run_report_is_a_receipt_and_not_a_second_queue(self):
        # Doctrine ruling 1.3: one review queue for photo candidates, and
        # a new import source makes its candidates visible IN that queue
        # rather than getting a review screen of its own. The receipt is
        # where that would erode first -- it already lists items, so it is
        # one button away from being a list of items you act on.
        blk = self._block()
        for verb in ('"Promote + accept"', '"Reject"', '"Duplicate"',
                     '"Error"', '"Hide"', '"Unhide"', '"File to trip"',
                     '"/promote"', '"/decision"', '"/hidden"'):
            self.assertNotIn(verb, blk,
                             f"the run report grew a decision control: {verb}")
        # And it is rendered from the response already in hand, once. A
        # refetch would make it a list that is kept up to date, which is
        # the first thing a second queue does.
        i = blk.index("function renderPickerReceipt(")
        receipt = blk[i:blk.index("function renderPickerResultRow(", i)]
        self.assertNotIn("api(", receipt)

    def test_it_is_not_an_eleventh_tab(self):
        # The affordance is a strip on the tab that already owns candidate
        # review. A screen with its own name is a screen that grows its
        # own list, which is the failure ruling 1.3 forbids.
        self.assertNotIn('"picker", "', self.src)
        self.assertNotIn('case "picker":', self.src)
        self.assertIn("wrap.appendChild(renderPickerStrip());", self.src)
        # Rendered from inside renderEvidence(), below its heading.
        i = self.src.index("function renderEvidence(")
        block = self.src[i:self.src.index("wrap.appendChild(renderPickerStrip());", i)]
        self.assertIn("Evidence Review Queue", block)

    def test_ingest_reloads_the_authoritative_queue(self):
        # The rows the run created are in the queue below, and the strip
        # says so rather than showing them again. reloadEvidence() is the
        # queue's own reader; calling anything else here would be a
        # second read of the same lane.
        blk = self._block()
        i = blk.index("function pickerIngest(")
        block = blk[i:blk.index("function pickerDismiss(", i)]
        self.assertIn("reloadEvidence()", block)
        self.assertNotIn(" EVIDENCE_BASE", block)

    def test_the_lanes_one_delete_is_not_surfaced(self):
        # DELETE /sessions/{batch_id} releases the picking session AT
        # GOOGLE and answers `batch_deleted: false`, so it does not breach
        # the no-DELETE rule and could have been offered. It is left out
        # on scope. Asserted rather than assumed, because "safe and
        # therefore fine to add" is how the first DELETE gets in.
        blk = self._block()
        self.assertNotIn('method: "DELETE"', blk)
        # Dismiss clears the panel and nothing else; the batch and its
        # candidates survive and the operator is told so in those words.
        self.assertIn("there is no delete on this lane", blk)

    # ------------------------------------------------- spec 10.2 (3)

    def test_the_destination_is_explicit_and_never_inferred(self):
        # "The application must never infer person_id or trip_id from the
        # Google account [...] There is no default, no fallback, and no
        # 'if only one person exists, use that one.'"
        blk = self._block()
        i = blk.index("function pickerStart(")
        block = blk[i:blk.index("function pickerCheck(", i)]
        self.assertIn("person_id: st.personId", block)
        self.assertIn("body.trip_id = st.trip.id", block)
        # Guarded on an explicit operator toggle, not on availability.
        self.assertIn("st.pickerFileToTrip && st.trip", block)
        # narrator_id is not a separately-suppliable destination field
        # (spec 10.3) and must not appear as one.
        self.assertNotIn("narrator_id", blk)

    def test_the_unfiled_case_is_stated_rather_than_defaulted_away(self):
        # With no trip selected the import is filed to no trip, and the
        # strip says that instead of quietly picking one.
        blk = self._block()
        self.assertIn("filed to no trip", blk)
        self.assertIn("not filed to a trip", blk)

    # --------------------------------------------- the flag-off arm (4)

    def test_flag_off_renders_as_configuration_not_as_an_error(self):
        # Both routes in the lane answer 404 while either flag is off.
        # Same convention as the queue's own 404 arm and for the same
        # reason: a flag that is off is a configuration fact, and painting
        # it red sends an operator hunting for something broken.
        blk = self._block()
        i = blk.index("function pickerLaneOff(")
        block = blk[i:blk.index("function reloadPickerHealth(", i)]
        self.assertIn("st.pickerOff = true", block)
        self.assertIn('st.pickerError = ""', block)
        self.assertIn("tdl-gp-off", blk)
        self.assertIn(".tdl-gp-off", self.css)
        # Neutral, not the error treatment.
        i = self.css.index(".tdl-gp-off")
        rule = self.css[i:self.css.index("}", i)]
        self.assertIn("dashed", rule)

    def test_the_two_off_states_are_independent(self):
        # The queue needs HORNELORE_IMPORT_PROVENANCE; the picker needs
        # that flag AND HORNELORE_GOOGLE_PICKER. So "a readable queue with
        # no import affordance above it" is a real, reachable and correct
        # server configuration -- one shared field would have rendered it
        # as a lie in one direction or the other.
        blk = self._block()
        self.assertNotIn("st.evidenceOff = true", blk)
        self.assertNotIn("st.evidenceError", blk)
        self.assertIn("pickerOff: false", self.src)
        self.assertIn("evidenceOff: false", self.src)

    def test_a_404_is_only_read_as_flag_off_where_it_can_mean_nothing_else(self):
        """The subtlest correctness point in this phase.

        /health and POST /sessions take no path parameter, so a 404 on
        either can only be the gate -- there is nothing behind them to be
        "not found". GET /sessions/{batch_id} and the ingest route both
        do, so a 404 there could be the gate, a batch id this server does
        not have, or Google reporting the picking session gone. Three
        situations, three different answers. Rendering "the lane is
        switched off" over the other two would be a confident wrong
        answer, and a confident wrong answer about a flag is worse than a
        raw error message: the operator stops looking.
        """
        blk = self._block()
        for fn, after, expect in (
            ("function reloadPickerHealth(", "function pickerStart(", True),
            ("function pickerStart(", "function pickerCheck(", True),
            ("function pickerCheck(", "function pickerIngest(", False),
            ("function pickerIngest(", "function pickerDismiss(", False),
        ):
            i = blk.index(fn)
            body = blk[i:blk.index(after, i)]
            self.assertEqual("pickerLaneOff()" in body, expect, fn)
            # Either way the reason travels with the message, because the
            # reason is the operator-actionable half.
            self.assertIn("pickerMessage(e)", body, fn)

    def test_the_reason_is_shown_and_is_never_a_value(self):
        blk = self._block()
        i = blk.index("function pickerMessage(")
        block = blk[i:blk.index("function pickerLaneOff(", i)]
        self.assertIn("e.body && e.body.detail", block)
        self.assertIn("d.reason", block)

    # ------------------------------------------------------- the timer

    def test_the_poll_is_bounded_at_both_ends_and_by_this_module(self):
        # Google returns pollingConfig.pollInterval as a protobuf Duration
        # string ("5s") and picker_client passes it through unchanged. A
        # malformed value must not become a zero-delay loop against
        # somebody else's API, and an absurd one must not leave the
        # operator watching a panel that never checks.
        blk = self._block()
        self.assertIn("PICKER_POLL_MIN_MS", blk)
        self.assertIn("PICKER_POLL_MAX_MS", blk)
        self.assertIn("PICKER_POLL_DEFAULT_MS", blk)
        self.assertIn("PICKER_POLL_MAX_TRIES", blk)
        i = blk.index("function pickerPollMs(")
        body = blk[i:blk.index("var _pickerPollTimer", i)]
        self.assertIn("isFinite(n)", body)
        self.assertIn("n <= 0", body)

    def test_the_second_timer_is_guarded_the_same_way_as_the_first(self):
        # The module's case against AbortController rests on the set of
        # async exits being small enough to enumerate. This adds one, so
        # it has to be guarded the same way: destroyed is checked first in
        # the callback, and destroy() clears the handle.
        blk = self._block()
        i = blk.index("function pickerPollArm(")
        body = blk[i:blk.index("function pickerMessage(", i)]
        self.assertIn("if (destroyed || !st.picker) return;", body)
        self.assertIn("if (destroyed) return;", body)
        i = self.src.index("destroy: function () {")
        teardown = self.src[i:i + 900]
        self.assertIn("pickerPollStop()", teardown)

    def test_the_liveness_inventory_was_corrected_rather_than_left_stale(self):
        # The count IS the argument. Phase 1.1's paragraph said "one
        # timer [...] Guarding those six"; leaving it standing would have
        # left a false sentence inside a true paragraph, which is exactly
        # the failure the doctrine document was written in response to.
        #
        # Read from the RAW source, not from self.src: the inventory is a
        # comment, and every other assertion in this file runs against a
        # comment-stripped module on purpose. This is the one property
        # here that lives in prose, because it is a claim ABOUT the code
        # rather than a behaviour of it.
        raw = _tds.UNIFIED_JS.read()
        i = raw.index("deliberately not AbortController")
        para = raw[i:i + 1400]
        self.assertIn("TWO timers", para)
        self.assertIn("those seven", para)

    # ------------------------------------------------------ the state

    def test_a_trip_switch_does_not_silently_strand_a_run(self):
        # st.evidence is a VIEW of a trip and is dropped. st.picker is a
        # server-side batch that was filed at creation and carries on
        # existing either way, so dropping the panel would take the
        # operator's Google link and Import button with it mid-run. The
        # run badge therefore names the batch's own trip id, so a switch
        # cannot make the panel claim the wrong one.
        i = self.src.index("function selectTrip(")
        block = self.src[i:i + 2600]
        self.assertIn("st.evidence = null", block)
        self.assertNotIn("st.picker = null", block)
        self.assertIn('st.pickerError = ""', block)
        self.assertIn("st.pickerFileToTrip = true", block)
        self.assertIn('"filed to trip · "', self._block())

    def test_the_health_probe_is_lazy_and_separate_from_the_queues(self):
        # Same lazy shape as the queue -- fetched on the tab switch, never
        # from render, because a fetch during render re-renders and
        # fetches again. Separate from the queue's fetch because the two
        # lanes are gated differently and one request could not have
        # answered for both.
        i = self.src.index("function setTab(")
        block = self.src[i:self.src.index("function renderAll(", i)]
        self.assertIn("reloadPickerHealth()", block)
        self.assertIn("!st.pickerHealth", block)
        self.assertIn("!st.pickerOff", block)
        # And it adds no third exemption to the trip gate.
        exempt = re.findall(r'st\.tab !== "(\w+)"', self.src)
        self.assertEqual(sorted(set(exempt)), ["captured", "evidence"])

    def test_max_items_is_not_sent(self):
        # The route accepts an optional cap and reports `truncated` and
        # `remaining` when one is supplied. A cap this screen chose would
        # truncate a run for a reason the operator never asked for, so it
        # supplies none -- while still rendering both fields if the server
        # ever reports them.
        blk = self._block()
        i = blk.index("function pickerIngest(")
        block = blk[i:blk.index("function pickerDismiss(", i)]
        self.assertNotIn("max_items", block)
        self.assertIn("run.truncated", blk)
        self.assertIn("run.remaining", blk)

    def test_result_fields_are_read_by_name_never_iterated(self):
        # Iterating the response would put this screen at the mercy of
        # whatever the route grows next, and the one class of value that
        # must never be rendered -- a bearer-scoped download URL, a token,
        # a staging path -- is exactly the kind of thing that arrives as a
        # new key. An allow-list cannot leak a field nobody has thought
        # about yet.
        blk = self._block()
        i = blk.index("function renderPickerResultRow(")
        body = blk[i:]
        self.assertNotIn("Object.keys(r)", body)
        self.assertNotIn("for (var k in r)", body)
        for field in ("r.outcome", "r.filename", "r.mime_type", "r.byte_size",
                      "r.taken_at", "r.taken_at_source", "r.location_source",
                      "r.gps_present_unparseable", "r.candidate_id",
                      "r.reason", "r.detail", "r.retryable"):
            self.assertIn(field, body, field)

    def test_the_video_refusal_is_rendered_as_the_server_words_it(self):
        # A picked video is refused by the ingest path with
        # reason="unsupported_content" and a sentence of detail. The strip
        # prints reason and detail verbatim rather than paraphrasing --
        # the same discipline the queue applies to match_reason, and for
        # the same reason: a paraphrase is a second source of truth.
        blk = self._block()
        i = blk.index("function renderPickerResultRow(")
        body = blk[i:]
        self.assertIn('r.reason || "failed"', body)
        self.assertIn('r.detail || "no detail given"', body)
        self.assertIn("r.retryable", body)

    # --------------------------------------------------------- the CSS

    def test_css_is_namespaced_tdl_gp_and_does_not_collide(self):
        for cls in (".tdl-gp", ".tdl-gp-off", ".tdl-gp-run", ".tdl-gp-link",
                    ".tdl-gp-actions", ".tdl-gp-receipt", ".tdl-gp-result",
                    ".tdl-gp-outcome", ".tdl-gp-fail"):
            self.assertIn(cls, self.css, cls)
        # NOT tdl-picker-: that prefix is already taken twice in this
        # stylesheet -- the day photo-picker grid and the person picker --
        # and either would have been restyled from the new block. Same
        # argument the queue block records for tdl-erq- over tdl-ev-.
        blk = self._block()
        self.assertNotIn("tdl-picker", blk)
        self.assertNotIn("tdl-ev-", blk)


if __name__ == "__main__":
    unittest.main()
