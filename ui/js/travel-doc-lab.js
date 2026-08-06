/* ==========================================================================
   Lorevox Travel Doc — the operator Travel Doc workspace.

   Mountable module. The Hornelore shell mounts it into
   #lvTravelDocUnifiedHost as the Travel Doc tab; ui/travel-doc-lab.html
   mounts it into #tdlRoot as a dev harness. Since
   WO-TRAVEL-DOC-UNIFY-01 Phase 4 the shell path is the only Travel Doc
   an operator sees. Design reference:
   docs/mockups/lorevox-travel-doc-ui-lab-v2/.

   The filename still says "lab" because renaming a 3,400-line module is
   churn that would bury a real diff; the rename to travel-doc.js is
   parked, not forgotten. Read "lab" here as "this file", not as "a
   thing you can throw away".

   WO-TRAVEL-DOC-UI-LAB-02 (2026-07-10, Chris's live usability review):
   sticky Save Day + dirty tracking, laptop drawer layout, consistent
   day-card actions, in-lab day photo picker (no more deep-linking away),
   in-lab day notes, Lori as an in-context drawer over Trip Plan with an
   explicit Back to Trip Plan control, collapsible inspector sections.

   WO-TRAVEL-DOC-UI-LAB-03 (2026-07-10, closes the two deferred gaps):
   true day-scoped sources (trip_sources.trip_day_id, migration 0029 —
   attach/move/unlink sources per day card, day-first counts) and the
   date-range reconcile flow (missing-day / outside-date banners, the
   reconcile review drawer — day cards are NEVER deleted), plus the
   lab-only evaluation checklist panel on Trip Plan.

   Boundaries (locked, enforced by tests/test_travel_doc_lab.py):
   - Zero reach into other surfaces: does NOT load or reference the older
     Travel Doc module, the narrator room, the Travels shelf, or any
     narrator-session state. The locked rule this serves: Travel Doc is
     the operator tool for editing trips, the Travels shelf is the
     narrator/Lori conversation surface, and their state does not mix.
   - API surface: /api/trips*, /api/photos/{id}/thumb, /api/people,
     /api/chat/ws (surface=travel_doc_modal) ONLY.
   - All DOM classes are tdl- namespaced; CSS lives in
     ui/css/travel-doc-lab.css.

   WO-TRAVEL-DOC-UNIFY-01 Phase 1 (2026-07-24) — MOUNTABLE.

   This file is no longer a page-level script. The entire module body is
   now the body of:

       window.lvTravelDocMount(hostEl, opts) -> { destroy() }

         opts.person_id     narrator id (falls back to ?person_id=)
         opts.person_label  display name (optional; boot() fetches it)
         opts.apiBase       API origin (falls back to ?api=, then
                            window.LOREVOX_API, then localhost:8000)

   Every former module-level binding (st, root, railCollapsed, insOpen,
   _tdlUpdateChannel, photoEvidence, lightbox, loriPane) is now scoped
   PER MOUNT, so two mounts cannot collide. Phase 1 changes behaviour in
   no other way — same tabs, same loads, same drawers, same Lori surface.

   DELIBERATE: the module body is NOT re-indented under the new function.
   Re-indenting 3,400 lines would bury the real Phase-1 diff in a
   whitespace change and make review impossible. The mount boundary is
   marked by the banner comments below and at the foot of the file.

   Teardown (amendment A1): destroy() closes the BroadcastChannel and the
   Lori WebSocket. The channel is NAMED ("hornelore-trip-updates"), so a
   leaked mount means duplicate subscriptions and double refreshes —
   always destroy() a mount you are replacing.

   Phase 1.1 (2026-07-24) — LIVENESS. destroy() also sets `destroyed`, and
   every asynchronous path in this file checks it before writing state or
   painting: api() (the file's only fetch), renderAll() (the file's only
   repaint entry point), the BroadcastChannel handler, the Lori socket's
   onmessage, the Lori send-retry timer, and the document-level keydown
   listener — which destroy() also unbinds, since it is the one listener
   not attached inside the host and so the only one clearing the host does
   not remove. Without this, a request in flight at teardown resolves and
   repaints a host the caller has already cleared.

   IF YOU ADD A NEW ASYNC PATH: route it through api(), or check
   `destroyed` yourself before touching `st` or the DOM.

   WO-TRAVEL-DOC-UNIFY-01 Phase 3A (2026-07-25) — TRIP FORCE-DELETE GATE.

   The first destructive control to move into the unified workspace, and
   the reason it went first: it is the safety-critical one. Ported from
   the production Documenter without loosening anything — unforced DELETE
   first, 409 impact payload read out of FastAPI's `detail` envelope, an
   in-panel review that shows the per-lane counts, force armed only by the
   trip's exact title or id, and the list refreshed with NOTHING
   auto-selected afterwards. No window.confirm / prompt / alert.

   This required teaching api() to attach `status` and `body` to its
   rejection: the old plain Error destroyed the impact payload at the
   choke point. That change is otherwise invisible — every existing call
   site reads e.message and still gets a sentence (a better one: the 409
   used to stringify to "[object Object]").

   SCOPE WALL (Phase 3A): region/stop deletion is NOT ported. Phase 3B
   below lifts that wall — deliberately, and not by copying production.

   WO-TRAVEL-DOC-UNIFY-01 Phase 3B (2026-07-25) — TRIP / REGION / STOP CRUD.

   The last production-only editing behaviour moves in: create and edit a
   trip, create/edit/delete a region, create/edit/delete a stop, and the
   insert-at-position ("+ Before" / "+ After") semantics that make the
   route board an itinerary rather than an append-only list. Front-end
   only — every endpoint and every field this uses already existed.

   Three things are deliberately NOT verbatim ports:

   1. Region and stop deletion go through an in-panel review drawer, not
      window.confirm(). Same reason as Phase 3A: a native dialog shows a
      sentence the operator cannot check against the data, and one click
      of "OK" is not a gate.

   2. Region deletion is a TWO-STAGE ladder, mirroring the trip gate.
      Production sends an unforced DELETE after its confirm() and stops
      there — but the backend refuses a non-empty region with 409
      RegionNotEmptyError unless ?force=true, so production's flow
      dead-ends on a raw 409 with nothing deleted, AFTER the operator has
      already agreed. Here stage 1 sends the unforced delete (an empty
      region is simply gone), and only a 409 opens stage 2, which quotes
      the backend's own refusal and offers the forced delete. The backend
      stays the authority on what is actually there, so a stale tree can
      never destroy something the operator was not shown.

   3. Reorder arrows are NOT here. Insert-at-position is existing
      production behaviour and had to survive; general reordering is
      Phase 3D (see below) and would have widened this diff.

   The Phase 2 "Current" tab — whose entire content was a banner saying
   the baseline lives in production — becomes the "Trip" tab and is that
   baseline. Phase 3B left a deep link at the foot of it, because the
   older surface had to stay reachable while the port was in flight;
   Phase 4 removed the link along with the fallback.

   WO-TRAVEL-DOC-UNIFY-01 Phase 3C (2026-07-25) — INTAKE.

   Photo upload, source-file upload and photo clustering. This is the
   capability that kept the legacy Documenter alive: until now the
   unified workspace could edit a trip but could not get material into
   it, so every operator still had to go back to the old surface to add
   a single photo.

   This one is a BUILD, not a port. Phases 3A/3B moved controls that had
   a shape to copy; this file had zero FormData and zero file inputs, and
   its own comments admitted the punt ("new uploads still come in via
   Photo Intake"). Every endpoint already existed — no backend, no API,
   no schema change — but the client side is new code.

   The constraint that shapes all of it: renderAll() rebuilds the whole
   DOM, and an <input type="file"> holds a FileList that script cannot
   write. A repaint between "choose files" and "Upload" destroys the
   operator's selection with no way to restore it. So the upload drawer
   repaints for NOTHING in between — the target line swaps its own
   textContent, the file hint counts in place, the button disables
   itself, and the flow's first renderAll() happens only after the
   response lands. Same doctrine the Phase 3B editors use for focus, for
   a harder reason: focus can be restored, a FileList cannot.

   Four deliberate decisions, none of them verbatim production:

   1. SCOPE IS AN EXPLICIT KEY, not the ambient selection. The target is
      one string — "trip" | "region:<id>" | "stop:<id>" — chosen in the
      drawer and read at submit. st.routeSel only SEEDS the select when
      the drawer opens; it is never consulted again. Production reads its
      ambient editorScope() at submit time, so retargeting the workspace
      mid-upload silently moves the destination. A named target line
      states the scope in words above the button, because a photo filed
      against the wrong stop is evidence corruption that looks like
      success.

   2. NO CAPTION FIELD AT INTAKE. The backend accepts one, and adding it
      would have been free. Upload is intake, not approval — captions
      belong to the approval ladder, and a caption box in the intake
      drawer invites the operator to author narrator-facing text at the
      moment they are least equipped to check it.

   3. NO trip_day_id AT INTAKE. Day attach stays its own deliberate act
      on the day card. The upload endpoint would take it; sending it
      would make intake and placement the same gesture.

   4. TITLE IS SENT ONLY FOR A SINGLE FILE. The backend stamps one title
      on every file in the request, so a title on a multi-file drop
      erases each document's own name. Production dodges this by never
      sending a title at all; here the field disables itself the moment a
      second file is chosen and says why.

   Clustering is reported honestly rather than flatteringly: the backend
   clusters every photo belonging to the NARRATOR, not only this trip's,
   so photos_considered counts the library. The result panel says so
   instead of letting the number read as a trip statistic.

   WO-TRAVEL-DOC-UNIFY-01 Phase 3D (2026-07-25) — ROUTE ORDER.

   The last workflow reason to open the legacy Documenter. Phases 3A/3B/3C
   took the delete gate, trip/region/stop CRUD and upload; what was left
   was that an operator could build a route here but not RE-ORDER one, so
   a stop entered in the wrong place still sent them back to the old
   surface. Four things landed, and one production affordance was
   deliberately not copied.

   1. STOP MOVES SEND TWO IDS, NOT A PERMUTATION. Production rebuilds the
      whole sibling group and POSTs /stops/reorder, which the backend
      accepts only when ordered_ids is EXACTLY that group. That request
      is precisely as stale as the tree it was built from: if anything
      landed since the last load — another tab, a clustering run, a
      sibling deleted — the permutation no longer matches and the move is
      refused for a reason the operator cannot see on screen. Here a stop
      move sends the stop and the neighbour it should land beside to
      /stops/{id}/move (before_stop_id / after_stop_id). The backend
      re-derives the group, so the wire carries the operator's intent
      ("put this one after that one") instead of a snapshot of the whole
      order. Same endpoint the cross-region move already used since 3B.

   2. REGION MOVES STILL SEND A PERMUTATION, because /regions/reorder is
      the only door — there is no /regions/{id}/move. That is a real
      staleness exposure, so it is handled rather than hidden: a refusal
      shows in the board (never a native dialog) AND reloads the tree, so
      the operator's next attempt is aimed at what actually exists.

   3. ARROWS DISABLE AT THE ENDS AND WHILE A MOVE IS IN FLIGHT.
      Production's arrows silently return at the ends — a control that
      answers a click with nothing reads as a broken build. st.routeBusy
      also disables the whole board mid-move, because two interleaved
      reorders are each computed from the tree as it looked before the
      other one landed.

   4. ROUTE ROWS ARE SELECTABLE, FOR REGIONS TOO. Before this, st.routeSel
      was set in exactly one place — the rail outline — and only ever for
      a stop, which left Phase 3C's region-scoped upload seeding dead
      code: the drawer could default to a region that nothing could
      select. The row body is now the selection control on both the board
      and the rail, and rows carry the evidence badges production shows
      (notes / docs / photos), read from already-loaded state so no row
      costs a fetch.

   NOT copied: nothing. Production has no drag-and-drop on either tile
   (grep-verified), so there is no reorder affordance left behind.

   WO-TRAVEL-DOC-UNIFY-01 Phase 4 (2026-07-25) — ONE SURFACE.

   Removal phase, no new behaviour. The shell used to carry a toggle over
   two hosts: this module, and the older ui/js/travel-documenter.js. With
   3A/3B/3C/3D landed there was no workflow left that needed the fallback,
   so Phase 4 took out the toggle, the stored surface preference, the
   second host, and the two legacy asset tags in hornelore1.0.html.

   What Phase 4 did NOT do: delete ui/js/travel-documenter.js, its
   stylesheet, ui/travel-documenter.html, or a single backend endpoint.
   The old module still exists and its own standalone page still mounts
   it, so every endpoint either surface calls is untouched. There is
   simply no route from the operator shell into it any more.

   Out of this file, Phase 4 removed prodTravelDocUrl() and the route
   board's deep link to that page — the last place this module knew the
   old page's filename.

   This file is no longer removable. It IS the operator Travel Doc; the
   header used to end with a delete-these-four-files recipe, and that
   recipe would now delete the Travel Doc tab. The dev harness page
   (ui/travel-doc-lab.html) is the removable part: dropping it costs the
   only non-shell caller of the mount, nothing an operator uses.
   ========================================================================== */
(function () {
  "use strict";

  // ══════════════════ MOUNT BOUNDARY — body begins ══════════════════
  window.lvTravelDocMount = function (hostEl, opts) {
  opts = opts || {};

  // WO-TRAVEL-DOC-UNIFY-01 Phase 2 — set by the Hornelore shell and by
  // nothing else. See the block next to `var root` below for what it does
  // to branding and layout; here it governs where identity comes from.
  var embedded = !!opts.embedded;

  var qsParams = new URLSearchParams(window.location.search);
  // Phase 2: the querystring fallbacks are STANDALONE-ONLY. On the Lab
  // page ?person_id= / ?api= are how the operator scopes the surface. In
  // the shell they are an attack on the shell's own idea of who is
  // selected: hornelore1.0.html can carry a ?person_id= from any other
  // launcher, and honouring it would mount Travel Doc against one
  // narrator while the shell header, the Travels shelf and every other
  // tab show a different one — silent cross-narrator writes. Embedded
  // identity comes from opts, or it does not come at all.
  var st = {
    apiBase: String(opts.apiBase || (embedded ? "" : qsParams.get("api")) ||
                    window.LOREVOX_API ||
                    "http://localhost:8000").replace(/\/+$/, ""),
    personId: String(opts.person_id ||
                     (embedded ? "" : qsParams.get("person_id")) || "").trim(),
    personLabel: String(opts.person_label || ""),
    tab: "plan",
    trips: [],
    trip: null,          // selected trip row
    tree: null,          // /tree for selected trip
    days: [],            // /days.days rows (in-window, numbered 1..N)
    preservedDays: [],   // /days.preserved rows (outside current window)
    countsWarning: "",   // /days.counts_warning when evidence counts partial
    // What the last trip-date save REMOVED. Chris's rule for empty
    // out-of-range cards is "dropped without asking" --- which is a rule
    // about prompts, not about disclosure. Reporting after the fact is
    // not asking.
    daysNotice: "",
    photoLinks: [],      // /photo-links rows
    notes: [],           // /location-notes rows
    sources: [],         // /sources rows
    // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: per-tab "Show hidden" state.
    // When on, the list fetch adds include_hidden=1 and hidden rows
    // render muted with a Restore affordance. Toggle-driven fetches
    // only (never fetched from render) — no auto-load loop possible.
    showHiddenNotes: false,
    showHiddenSources: false,
    publicContext: [],   // /public-context rows
    travelogue: null,    // /travelogue-preview (lazy)
    draft: null,         // Draft tab: {scopeKey, preview, result, instruction, status, busy}
    selectedDayId: null,
    selectedPhotoLinkId: null,
    routeSel: null,      // {kind:"region"|"stop", id, regionId}
    photoFilter: "all",
    sourceFilter: "all",     // Sources tab: all/day/unattached/memoir
    reconcile: null,         // /days/reconcile-preview (date-range diff)
    reconcileDrawerOpen: false,
    sourceDrawerDayId: null, // in-lab day source drawer
    loriOverlay: false,      // Lori as a drawer over Trip Plan / Photos
    loriReturnTab: "plan",   // context-aware Back label + return surface
    photoPickerDayId: null,  // in-lab day photo picker drawer
    noteDrawerDayId: null,   // in-lab day note drawer
    // WO-LIVE-TRIP-COMPANION-01 VS1 -- the trip timeline modal. null =
    // closed. Open shape: {dayId, days, preserved, items, unplaced,
    // unplacedCount, showUnplaced, busy, error}. Every field here is a
    // PROJECTION of what the server just said; nothing on this screen is
    // authored, so there is no dirty state to protect and a repaint can
    // never lose an operator's typing.
    tripCal: null,
    // WO-TRAVEL-DOC-UNIFY-01 Phase 3A — trip force-delete impact review.
    // null = closed. Open shape: {tripId, tripTitle, counts, error}. The
    // operator's typed confirmation deliberately does NOT live here: it is
    // held in the drawer's closure and read on submit, so typing never
    // triggers a repaint and the field never loses focus mid-word.
    deleteReview: null,
    // WO-TRAVEL-DOC-UNIFY-01 Phase 3B — the editor drawers. Each holds
    // only WHICH entity is open and any inline error; the typed field
    // values live in the drawer's closure and are read on submit, so
    // typing never repaints and no input can lose focus mid-word.
    tripEditor: null,        // {mode:"create"|"edit", error}
    regionEditor: null,      // {mode:"create"|"edit", regionId, error}
    stopEditor: null,        // {mode:"create"|"edit", stopId, regionId, error}
    routeDelete: null,       // {kind:"region"|"stop", id, title, stage, ...}
    insertContext: null,     // {region_id, parent_stop_id, sibling_stop_id, where}
    tripWarning: "",         // days_warning / sync_warning from a trip save
    // WO-TRAVEL-DOC-UNIFY-01 Phase 3D — route order. routeBusy holds the
    // id of the row whose move is in flight and disables every arrow on
    // the board while it is set: two interleaved reorders are each built
    // from the tree as it looked before the other one landed. routeError
    // is the in-board failure surface — a refused move has to be readable
    // next to the rows it is about, never in a native dialog.
    routeBusy: null,         // stop id / region id mid-move, or null
    routeError: "",          // last reorder/move refusal, shown in-board
    // WO-TRAVEL-DOC-UNIFY-01 Phase 3C — intake. uploadDrawer holds only
    // WHICH drawer is open plus an inline error: the scope select and the
    // file input are live handles in the drawer's closure, because a
    // repaint would silently discard the operator's chosen FileList and
    // script cannot put one back.
    uploadDrawer: null,      // {kind:"photo"|"source", error}
    photoIntake: null,       // Photos-tab result: {kind, busy, lines, warnings, error}
    sourceIntake: null,      // Sources-tab result: {lines, warnings}
    // WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 2 -- the review queue.
    // `evidence` is the whole GET /queue payload (page + total +
    // state_counts), held verbatim rather than unpacked, so the screen
    // cannot drift from what the route actually said. `evidenceOff` is
    // NOT an error: the import lane is flag-gated and answers 404 on
    // every route while it is off, which is a configuration fact and
    // must not paint the workspace-wide red bar.
    evidence: null,          // GET /queue payload, or null
    evidenceScope: "trip",   // "trip" (filter by selection) | "all"
    evidenceState: "pending",// "" = all five states
    evidenceBusy: false,
    evidenceOff: false,      // the lane is switched off on this server
    evidenceError: "",
    showHiddenEvidence: false,
    // Same closure discipline as every other drawer here: this holds only
    // WHICH review is open plus its inline error. The chosen file and the
    // typed reason live in the drawer's closure and are read on submit.
    evidenceDrawer: null,    // {kind:"promote"|"decide"|"file", candidateId, state, error}
    // WO-POST-LORI-CLEANUP-AND-UNBLOCK-01 Lane 3 -- captured-note review.
    // Person-scoped like the evidence queue, for the same reason: a note
    // captured by the Travel Doc modal lands under whichever trip scope
    // the operator happened to be in, so requiring a trip selection to
    // find it would hide exactly the rows that need finding. `captured`
    // holds the whole GET /captured-notes payload verbatim (notes +
    // counts) so the screen cannot drift from what the route said.
    captured: null,          // GET /captured-notes payload, or null
    capturedSurface: "travel_doc_modal", // "" = any surface
    capturedPromoted: "",    // "" = all | "0" unpromoted | "1" promoted
    capturedBusy: false,
    capturedOff: false,      // trips lane is flag-off on this server
    capturedError: "",
    showHiddenCaptured: false,
    // WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2D -- the import strip.
    // `pickerOff` is a SECOND and independent off-state, not a synonym
    // for `evidenceOff`: the queue needs HORNELORE_IMPORT_PROVENANCE and
    // the picker needs that flag AND HORNELORE_GOOGLE_PICKER, so "a
    // readable queue with no import affordance above it" is a real and
    // correct server configuration. One shared field would have rendered
    // it as a lie in one direction or the other.
    picker: null,            // the live run: {batchId, pickerUri, stage, run, ...}
    pickerHealth: null,      // GET /health payload -- presence BOOLEANS only
    pickerOff: false,        // both-flags gate is closed on this server
    pickerBusy: false,       // POST /sessions is in flight
    pickerError: "",         // strip-level failure, before a run exists
    pickerFileToTrip: true,  // destination is explicit (spec 10.2), never inferred
    mainScroll: 0,           // preserved across re-renders / drawer close
    error: "",
  };

  // Module vars (survive re-renders; deliberately NOT in st so a trip
  // switch doesn't reset the operator's layout preference).
  // LAPTOP FIX (2026-07-13): the 295px rail permanently eats ~20% of a 1440
  // screen, and this reset to false on every reload — so it had to be
  // re-collapsed every single time. Remember the operator's choice.
  var railCollapsed = (function () {
    try { return localStorage.getItem("tdlRailCollapsed") === "1"; }
    catch (e) { return false; }
  })();
  var insOpen = { overview: true };    // inspector collapsible sections

  // WO-TRAVEL-DOC-UNIFY-01 Phase 1 — the host element is supplied by the
  // caller. The getElementById fallback keeps travel-doc-lab.html working
  // if it is ever loaded without an explicit host.
  var root = hostEl || document.getElementById("tdlRoot");

  // WO-TRAVEL-DOC-UNIFY-01 Phase 2 — embedded mode + host scoping.
  //
  // `embedded` is set by the Hornelore shell and by nothing else. It does
  // exactly two things, and deliberately no more: it drops the Lab's own
  // branding (the "UI Lab · experimental" badge, the lab-only evaluation
  // checklist, the picker's "experimental lab" copy), because in the shell
  // this IS the Travel Doc workspace and calling it a lab is the
  // discoverability defect Phase 2 is closing; and it adds
  // .tdl-root-embedded, which swaps the stylesheet's dvh measurements for
  // percentages of the host.
  //
  // The .tdl-root class is added here rather than by the caller so that
  // EVERY mount is scoped — including the standalone page, which has no
  // shell code to remember to do it. destroy() takes both classes back
  // off, so a host handed on to something else carries none of the Lab's
  // styling with it.
  if (root) {
    root.classList.add("tdl-root");
    if (embedded) root.classList.add("tdl-root-embedded");
  }

  // WO-TRAVEL-DOC-UNIFY-01 Phase 1.1 — the liveness flag.
  //
  // destroy() closing the channel and clearing the host is not enough on
  // its own: this module is one long chain of async flows (boot, loadTrips,
  // loadTripBundle, evidence reloads, travelogue preview, the Lori drawer
  // refresh), and a request already in flight when the mount is torn down
  // will still resolve. Its callback then writes to `st` and repaints a
  // host the caller has already cleared and may have handed to something
  // else. That only shows up when panels are swapped — which is exactly
  // what Phase 2 introduces.
  //
  // This is deliberately not AbortController. There is exactly ONE fetch()
  // in this file (inside api()), ONE repaint entry point (renderAll()), one
  // BroadcastChannel handler, one WebSocket, TWO timers, and one
  // document-level listener. Guarding those seven is total coverage without
  // editing all 54 call sites and without inventing a cancellation layer.
  //
  // Corrected 2026-07-28 by WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase
  // 2D. This paragraph read "one timer [...] Guarding those six" from
  // Phase 1.1 until the Google Photos import strip added the second: the
  // picker's selection poll (`_pickerPollTimer`, armed by pickerPollArm()
  // and cleared by pickerPollStop()). It is corrected rather than deleted
  // because the COUNT is the argument -- the case against AbortController
  // rests entirely on the set of async exits being small enough to
  // enumerate, so a reader has to be able to see that the set grew by one
  // and that the new member is guarded the same way. The day this
  // paragraph cannot be kept accurate is the day the argument in it has
  // stopped being true, and that is worth noticing rather than papering
  // over.
  var destroyed = false;

  // A promise that never settles. api() returns this once the mount is
  // dead, so the caller's .then()/.catch() never runs. Call sites stay
  // ignorant of teardown and are covered by construction rather than by
  // somebody remembering to add a guard to each new one.
  function abandoned() {
    return new Promise(function () {});
  }

  // 2026-07-23 — cross-tab BroadcastChannel listener. When the
  // Documenter (in a different tab) saves a trip and posts
  // {trip_id, kind:"trip_saved"|"trip_created"} on the
  // "hornelore-trip-updates" channel, if the Lab currently has that
  // trip open we reload the bundle. Silent no-op in browsers without
  // BroadcastChannel; operators can still reload the Lab manually.
  var _tdlUpdateChannel = null;
  try {
    if (typeof BroadcastChannel !== "undefined") {
      _tdlUpdateChannel = new BroadcastChannel("hornelore-trip-updates");
      _tdlUpdateChannel.addEventListener("message", function (ev) {
        // Phase 1.1: close() does not retract message events already
        // queued on the task queue, so a cross-tab save landing in the
        // same tick as destroy() can still arrive here.
        if (destroyed) return;
        var msg = ev && ev.data;
        if (!msg || !msg.trip_id) return;
        if (!st.trip || String(st.trip.id) !== String(msg.trip_id)) return;
        // Reload the bundle for the currently-open trip. Preserves
        // operator UI state (selected day, filters, drawers) because
        // loadTripBundle only overwrites the data arrays, not the
        // selection ids.
        loadTripBundle(st.trip.id);
      });
    }
  } catch (_) { _tdlUpdateChannel = null; }

  // Phase 3B — the Lab has always LISTENED on this channel; now that it
  // writes trips it must also announce. A BroadcastChannel never delivers
  // to the instance that posted, so this cannot feed our own handler
  // above — it only reaches Travel Doc surfaces in other tabs.
  function notifyTripUpdated(tripId, kind) {
    if (!_tdlUpdateChannel || !tripId) return;
    try {
      _tdlUpdateChannel.postMessage({
        trip_id: String(tripId),
        kind: String(kind || "trip_saved"),
        from: "travel-doc-lab",
        at: Date.now(),
      });
    } catch (_) { /* a closed channel is not worth failing a save over */ }
  }

  // ── helpers ──────────────────────────────────────────────────────────

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined) {
      // Phase 3C — multipart intake. A FormData body must go out
      // untouched and WITHOUT a hand-set Content-Type: the browser has to
      // write that header itself so it can append the multipart boundary,
      // and stringifying a FormData yields "[object FormData]".
      if (typeof FormData !== "undefined" && opts.body instanceof FormData) {
        init.body = opts.body;
      } else {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(opts.body);
      }
    }
    // Phase 1.1 — the single async choke point. Three checks, because the
    // mount can die at three different moments: before the request goes
    // out, while it is in flight, and while the error body is being read.
    // The rejection arm matters as much as the success arm: nearly every
    // call site ends in .catch(e => { st.error = e.message; renderAll(); }),
    // which is itself a write to dead state.
    if (destroyed) return abandoned();
    return fetch(st.apiBase + path, init).then(function (r) {
      if (destroyed) return abandoned();
      if (!r.ok) {
        return r.text().then(function (t) {
          if (destroyed) return abandoned();
          // WO-TRAVEL-DOC-UNIFY-01 Phase 3A — the rejection must carry the
          // STRUCTURED failure, not only a sentence.
          //
          // The old shape (`new Error(msg)` and nothing else) threw away
          // the HTTP status and the parsed body at the file's one and only
          // fetch, which made a whole class of gated backend contract
          // unreachable from the Lab: the trip force-delete gate answers
          // 409 with {detail:{detail, trip_id, requires_force, counts}} and
          // 422 for a wrong confirm, and a caller that cannot see
          // e.status / e.body cannot tell those apart from a 500. It also
          // rendered "[object Object]": `JSON.parse(t).detail` is a DICT on
          // that 409, and string-concatenating a dict is exactly that.
          //
          // So: parse once, attach status + body (mirroring what the
          // production Documenter's api() has always done), and flatten the
          // message defensively for the plain `st.error = e.message` call
          // sites that just want a sentence.
          var body = null;
          try { body = JSON.parse(t); } catch (_) { body = null; }
          var detail = (body && body.detail !== undefined) ? body.detail : t;
          var msg;
          if (typeof detail === "string") {
            msg = detail;
          } else if (detail && typeof detail === "object" &&
                     typeof detail.detail === "string") {
            msg = detail.detail;                       // nested envelope
          } else {
            try { msg = JSON.stringify(detail); } catch (_) { msg = t; }
          }
          var err = new Error(init.method + " " + path + " -> " + r.status +
                              " " + msg);
          err.status = r.status;
          err.body = body;
          throw err;
        });
      }
      // WO-TRAVEL-DOC-CLOSEOUT-01 — `opts.raw` returns the Response
      // instead of parsed JSON, for the one route that answers with a
      // .docx byte stream rather than a document of facts.
      //
      // Added HERE rather than as a second `fetch()` elsewhere in the
      // module. The whole async-safety design of this file rests on
      // there being exactly one fetch with exactly one set of destroyed
      // guards -- `test_the_only_fetch_is_guarded_on_every_arm` exists
      // to hold that, and it caught the second fetch the moment it
      // appeared. A caller must opt in explicitly, so no existing call
      // site can be handed a Response by surprise.
      if (opts.raw) return r;
      return r.json();
    }, function (err) {
      if (destroyed) return abandoned();
      throw err;
    });
  }

  function el(tag, cls, text) {
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (text !== undefined && text !== null) d.textContent = String(text);
    return d;
  }

  function btn(cls, text, onClick) {
    var b = el("button", cls, text);
    b.type = "button";
    if (onClick) b.addEventListener("click", onClick);
    return b;
  }

  function thumbUrl(photoId) {
    return st.apiBase + "/api/photos/" + encodeURIComponent(photoId) + "/thumb";
  }

  // [Each of the four thumbnail call sites built its own img element and
  // set the native lazy loading hint on it until 2026-07-29. Three of the
  // four never showed a picture. Native lazy loading is evaluated against
  // the document's own scrollport, and the day inspector, the attach
  // drawer and every other panel that floats above the page are position
  // absolute or fixed containers with their own overflow auto body.
  // Chrome lays the thumbnail out, reserves the tile, and then never
  // issues the request --- the operator is left looking at an empty box
  // with a "Remove from this day" button under it. Verified live on
  // 2026-07-29 against the first promoted Picker photo: inside the Day 1
  // inspector the img stayed at naturalWidth 0 through open, scroll, and
  // even re-insertion into the already-open section, while the identical
  // URL loaded 301x400 the instant loading was set to "eager". The trip
  // gallery is the one site that worked, because it scrolls with the
  // page, and it is also the one site that can hold every photo on a
  // trip, so it is the one site that keeps the hint. The decision lives
  // in one place now instead of four, so the next panel cannot inherit
  // the bug by copying a line.]
  function thumbImg(photoId, alt, lazy) {
    var im = document.createElement("img");
    im.src = thumbUrl(photoId);
    im.alt = alt || "trip photo";
    if (lazy) im.loading = "lazy";
    return im;
  }

  function datePrefix(v) { return v ? String(v).slice(0, 10) : ""; }

  function linkTakenDate(l) {
    return datePrefix(l.taken_at || l.photo_date_value);
  }

  var WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function prettyDate(iso) {
    var p = (iso || "").split("-");
    if (p.length !== 3) return iso || "";
    var d = new Date(Date.UTC(+p[0], +p[1] - 1, +p[2]));
    return WEEKDAYS[d.getUTCDay()] + " · " + MONTHS[d.getUTCMonth()] + " " + (+p[2]);
  }

  // "July 19", not "Sun \u00b7 Jul 19". Chris wrote the refusal message
  // by hand and this is the shape he wrote the dates in; a refusal is
  // read once, under mild annoyance, and the long month name is the
  // form that reads as a sentence rather than as a table cell.
  function longDate(iso) {
    var p = (iso || "").split("-");
    if (p.length !== 3) return iso || "";
    return LONG_MONTHS[(+p[1]) - 1] + " " + (+p[2]);
  }

  var LONG_MONTHS = ["January", "February", "March", "April", "May",
    "June", "July", "August", "September", "October", "November",
    "December"];

  function findRegion(regionId) {
    var regions = (st.tree && st.tree.regions) || [];
    for (var i = 0; i < regions.length; i++) {
      if (regions[i].id === regionId) return regions[i];
    }
    return null;
  }

  function findStop(stopId) {
    var found = null;
    var regions = (st.tree && st.tree.regions) || [];
    regions.forEach(function (r) {
      (function walk(stops) {
        (stops || []).forEach(function (s) {
          if (s.id === stopId) found = s;
          walk(s.children);
        });
      })(r.stops);
    });
    return found;
  }

  // ── route graph helpers (WO-TRAVEL-DOC-UNIFY-01 Phase 3B) ────────────
  //
  // The Lab has only ever READ the tree, so findRegion/findStop were
  // enough. Editing a stop needs three things they cannot answer: which
  // region a stop lives in (the region selector), which stop is its
  // parent (the parent selector), and which ids sit underneath it — a
  // stop reparented into its own subtree would orphan the branch.

  var STOP_TYPES = ["base", "sight", "day_trip", "transit", "lodging",
                    "meal", "disruption", "memory_anchor"];

  function allStops(tree) {
    var out = [];
    ((tree && tree.regions) || []).forEach(function (r) {
      (function walk(stops, depth) {
        (stops || []).forEach(function (s) {
          out.push({ id: s.id, region_id: r.id, depth: depth, node: s });
          walk(s.children, depth + 1);
        });
      })(r.stops, 0);
    });
    return out;
  }

  function locateStop(stopId) {
    var res = null;
    ((st.tree && st.tree.regions) || []).forEach(function (r) {
      (function walk(stops, parent) {
        (stops || []).forEach(function (s) {
          if (res) return;
          if (s.id === stopId) {
            res = { node: s, region: r, parent: parent };
            return;
          }
          walk(s.children, s);
        });
      })(r.stops, null);
    });
    return res;
  }

  function subtreeIds(node) {
    var ids = [];
    (function walk(s) {
      ids.push(s.id);
      (s.children || []).forEach(walk);
    })(node);
    return ids;
  }

  function regionStopCount(region) {
    var n = 0;
    (function walk(stops) {
      (stops || []).forEach(function (s) { n += 1; walk(s.children); });
    })(region && region.stops);
    return n;
  }

  function regionLabel(r) { return (r && r.title) || "Region"; }

  function stopLabel(s) {
    return (s && (s.location_name || s.title)) || "Stop";
  }

  // Soft, NON-blocking out-of-range date check (YYYY-MM-DD compares
  // lexicographically). Ported from production: it warns, it never
  // refuses the save — operators legitimately record a stop that runs
  // past the trip window they entered first.
  function dateRangeWarning(start, end, boundStart, boundEnd, label) {
    var bad = (start && boundStart && start < boundStart) ||
              (end && boundEnd && end > boundEnd) ||
              (start && boundEnd && start > boundEnd) ||
              (end && boundStart && end < boundStart);
    return bad ? ("\u26a0 Dates fall outside the " + label +
      " range \u2014 saved anyway.") : "";
  }

  function dayById(dayId) {
    return st.days.filter(function (d) { return d.id === dayId; })[0] || null;
  }

  function dayLabel(day) {
    return day.title || day.main_location ||
      (day.trip_stop_id && (findStop(day.trip_stop_id) || {}).location_name) ||
      (day.trip_region_id && (findRegion(day.trip_region_id) || {}).title) ||
      "Untitled day";
  }

  function dayChipText(day) {
    return "Day " + day.day_index + " · " + day.date;
  }

  // ── data loading (single shared adapter — no per-view duplication) ───

  // opts.noAutoSelect — WO-TRAVEL-DOC-UNIFY-01 Phase 3A. On boot, landing
  // the operator on their first trip is the right default. Straight after a
  // force delete it is not: silently mounting some OTHER trip's workspace
  // under the cursor of someone who just destroyed irreplaceable evidence
  // is precisely the stale-selection confusion the confirm gate exists to
  // prevent. The refresh keeps the rail honest and leaves nothing selected.
  function loadTrips(opts) {
    var noAutoSelect = !!(opts && opts.noAutoSelect);
    return api("/api/trips?person_id=" + encodeURIComponent(st.personId))
      .then(function (out) {
        st.trips = out.trips || [];
        if (!noAutoSelect && !st.trip && st.trips.length) {
          // WO-LIVE-TRIP-COMPANION-01 VS1 — land on the trip the
          // narrator is actually on, not on whichever one sorts first.
          //
          // This is the restart behaviour the slice exists to prove.
          // The browser forgot everything; the server did not. Asked
          // through the SAME route the placement service resolves
          // against, so the workspace cannot open on one trip while
          // completed turns are being filed to another.
          //
          // Degrades to the old behaviour on ANY failure, including the
          // 404 an unmigrated or flag-off server answers with. Which
          // trip to open with is a convenience, and a convenience is
          // never allowed to leave the workspace empty.
          return api("/api/trips/active?person_id=" +
                     encodeURIComponent(st.personId))
            .then(function (act) {
              return (act && act.trip && act.trip.id) || null;
            })
            .catch(function () { return null; })
            .then(function (activeId) {
              if (destroyed) return;
              var known = st.trips.filter(function (t) {
                return t.id === activeId;
              })[0];
              return selectTrip(known ? known.id : st.trips[0].id);
            });
        }
        renderAll();
      });
  }

  function selectTrip(tripId) {
    st.trip = st.trips.filter(function (t) { return t.id === tripId; })[0] || null;
    st.selectedDayId = null;
    st.selectedPhotoLinkId = null;
    st.routeSel = null;
    st.routeBusy = null;
    st.routeError = "";
    st.travelogue = null;
    st.memoirPreview = null;   // WO-TRAVEL-DOC-CLOSEOUT-01
    st.docExport = null;      // {busy, error, status}
    st.draft = null;
    st.loriOverlay = false;
    st.loriReturnTab = "plan";
    st.photoPickerDayId = null;
    st.noteDrawerDayId = null;
    st.sourceDrawerDayId = null;
    st.reconcile = null;
    st.reconcileDrawerOpen = false;
    // Same H3 argument as the Lori pane reset: a timeline left open
    // across a trip switch would be showing Trip A's days over Trip B's
    // workspace, and its Move control would file Trip A's conversation
    // onto a day id it no longer has any relationship to.
    st.tripCal = null;
    // "2 empty day cards were removed" is a claim about THIS trip's
    // calendar. Carried across a switch it becomes a claim about a
    // calendar the operator is now looking at and never touched.
    st.daysNotice = "";
    // Phase 3A: a pending impact review belongs to the trip it was opened
    // for. Switching trips with it still open would leave a review armed
    // against a trip the operator is no longer looking at.
    st.deleteReview = null;
    // Phase 3B: an editor or a delete review belongs to the trip it was
    // opened against. Carrying one across a trip switch would save (or
    // destroy) inside a trip the operator is no longer looking at.
    st.tripEditor = null;
    st.regionEditor = null;
    st.stopEditor = null;
    st.routeDelete = null;
    st.insertContext = null;
    st.tripWarning = "";
    // Phase 3C: an open upload drawer is armed against the trip it was
    // opened from, and an intake result describes a trip the operator is
    // no longer looking at. Both die with the selection.
    st.uploadDrawer = null;
    st.photoIntake = null;
    st.sourceIntake = null;
    // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: hidden-row visibility is a
    // per-trip review choice — reset it on trip switch.
    st.showHiddenNotes = false;
    st.showHiddenSources = false;
    // WO-2 Phase 2: the review queue is person-scoped, but its default
    // filter is the selected trip, so the page it holds describes a trip
    // the operator is no longer looking at. Drop the page and any open
    // review with it; the tab reloads on next visit.
    st.evidence = null;
    st.evidenceDrawer = null;
    st.evidenceError = "";
    st.showHiddenEvidence = false;
    // Phase 2D. `st.picker` is deliberately NOT cleared here, and that is
    // the opposite of the line above it on purpose. The queue's page is a
    // VIEW of a trip and goes stale the moment the trip changes; a picking
    // run is a server-side batch that was filed at creation and carries on
    // existing either way. Dropping the panel would take the operator's
    // Google link and Import button with it mid-run while the batch it
    // belongs to survived -- the queue would then be the only evidence
    // that an import was ever started. The run badge names the batch's own
    // trip id so a switch cannot make the panel claim the wrong one. Only
    // the two view-level fields reset: a stale error about the previous
    // trip, and the destination toggle, which must default to the trip now
    // selected rather than remember a choice made about another one.
    st.pickerError = "";
    st.pickerFileToTrip = true;
    loriPane.reset();
    if (!st.trip) { renderAll(); return Promise.resolve(); }
    return loadTripBundle(tripId);
  }

  // ── trip force-delete impact gate (WO-TRAVEL-DOC-UNIFY-01 Phase 3A) ───
  //
  // Ported from the production Documenter, unchanged in substance. The
  // backend (DELETE /api/trips/{id}) already implements the whole ladder
  // and needs no change:
  //
  //   empty trip                     -> 200, gone
  //   any dependent evidence, no force -> 409 {detail:{detail, trip_id,
  //                                     requires_force, counts}},
  //                                     NOTHING modified
  //   force without an exact
  //     confirm_trip_id echo         -> 422, NOTHING modified
  //   force + exact echo             -> one transaction: audit row then
  //                                     FK cascade
  //
  // So the client's job is narrow and must be done exactly: try the plain
  // delete FIRST (never lead with force), read the impact payload out of
  // FastAPI's `detail` envelope, show the operator what they are about to
  // destroy, and refuse to arm the force button until they have typed the
  // trip's exact title or its id. No window.confirm / prompt / alert — a
  // native dialog cannot show the counts, and a one-click "OK" is not a
  // gate.
  //
  // (Phase 3A said region/stop deletion was not ported here. Phase 3B
  // ports it — see openRouteDelete() / renderRouteDeleteReview() — and
  // does NOT copy production's native dialog for it either.)
  //
  // Note the wire always carries confirm_trip_id = the trip id. Accepting
  // the TITLE as well is a client-side affordance (operators know the
  // trip by name, not by uuid); it never loosens the server's check.

  // The dependent-count lanes, in the order the operator should read them,
  // with their display labels. Sourced from the backend's
  // _TRIP_DEPENDENT_TABLES allowlist, which is the authority.
  //
  // NOTE (reported as a Phase 3A finding): the production Documenter's
  // grid renders only nine of these ten — it silently omits
  // bio_suggestions, so a trip whose ONLY evidence is bio suggestions
  // shows an all-zero impact grid while the backend is refusing the
  // delete. The unified workspace renders all ten, plus any key a future
  // backend adds (see the unknown-key sweep in renderDeleteTripReview).
  var TRIP_DELETE_COUNT_LANES = [
    ["regions", "Regions"],
    ["stops", "Stops"],
    ["days", "Day cards"],
    ["photo_links", "Photo links"],
    ["notes", "Story notes"],
    ["sources", "Sources"],
    ["story_links", "Story links"],
    ["public_context", "Public context"],
    ["photo_context", "Photo context"],
    ["bio_suggestions", "Bio suggestions"],
  ];

  // The 409 impact payload ships inside FastAPI's standard `detail`
  // envelope, so the structured body is at e.body.detail — NOT e.body.
  // Reading the wrong level is a silent failure: `requires_force` is
  // undefined there, the gate never opens, and the operator sees a raw
  // error string instead of an impact review. The e.body fallback is for
  // robustness only, in case a future backend flattens the envelope.
  function deleteImpactOf(e) {
    if (!e || !e.body) return null;
    if (e.body.detail && typeof e.body.detail === "object") return e.body.detail;
    return e.body;
  }

  function afterTripDeleted() {
    st.deleteReview = null;
    st.trip = null;
    st.tree = null;
    st.days = [];
    st.preservedDays = [];
    st.photoLinks = [];
    st.notes = [];
    st.sources = [];
    st.publicContext = [];
    st.travelogue = null;
    st.memoirPreview = null;   // WO-TRAVEL-DOC-CLOSEOUT-01
    st.docExport = null;      // {busy, error, status}
    st.draft = null;
    st.selectedDayId = null;
    st.selectedPhotoLinkId = null;
    st.routeSel = null;
    st.routeBusy = null;
    st.routeError = "";
    // Phase 3B — same rule as selectTrip(), and more urgent here: the
    // trip these editors point at no longer exists.
    st.tripEditor = null;
    st.regionEditor = null;
    st.stopEditor = null;
    st.routeDelete = null;
    st.insertContext = null;
    st.tripWarning = "";
    // Phase 3C — same rule, same urgency: the trip is gone.
    st.uploadDrawer = null;
    st.photoIntake = null;
    st.sourceIntake = null;
    st.error = "";
    loriPane.reset();
    return loadTrips({ noAutoSelect: true });
  }

  // Step 1: always the UNFORCED delete. An empty trip is simply gone; a
  // trip with evidence comes back 409 and opens the review.
  function deleteTrip(trip) {
    if (!trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(trip.id), { method: "DELETE" })
      .then(function () { return afterTripDeleted(); })
      .catch(function (e) {
        var impact = deleteImpactOf(e);
        if (e && e.status === 409 && impact && impact.requires_force) {
          st.deleteReview = {
            tripId: trip.id,
            tripTitle: String(trip.title || ""),
            counts: impact.counts || {},
            error: "",
          };
          st.error = "";
          renderAll();
          return;
        }
        st.error = e.message;
        renderAll();
      });
  }

  // Step 2: the forced delete, reachable only from the review drawer and
  // only once refreshArm() has armed the button.
  function forceDeleteTrip(reasonText) {
    var review = st.deleteReview;
    if (!review) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(review.tripId), {
      method: "DELETE",
      body: {
        force: true,
        confirm_trip_id: review.tripId,
        reason: (reasonText || "").trim() || "operator cleanup",
      },
    })
      .then(function () { return afterTripDeleted(); })
      .catch(function (e) {
        // A 422 (wrong confirm) or anything else renders INLINE in the
        // review, never as a native dialog and never by closing the panel
        // out from under the operator.
        if (st.deleteReview) st.deleteReview.error = "Delete failed: " + e.message;
        renderAll();
      });
  }

  function closeDeleteReview() {
    st.deleteReview = null;
    renderAll();
  }

  function loadTripBundle(tripId) {
    var t = encodeURIComponent(tripId);
    // 2026-07-15 Track C fix — stop silently converting /days and
    // /days/reconcile-preview failures into empty results. A missing
    // migration or a 500 from the backend used to render as
    // "No day cards yet — Generate them from the trip dates above",
    // which was indistinguishable from an operator who legitimately
    // hadn't clicked Generate. The two errors now go through a
    // best-effort wrapper that captures the error message onto
    // st.loadWarnings so the panel can show it.
    function _captureLoadError(label, fallback) {
      return function (e) {
        st.loadWarnings = st.loadWarnings || [];
        st.loadWarnings.push(label + ": " + e.message);
        return fallback;
      };
    }
    st.loadWarnings = [];
    return Promise.all([
      api("/api/trips/" + t + "/tree"),
      api("/api/trips/" + t + "/days").catch(
        _captureLoadError("Day cards failed to load", { days: [] })),
      api("/api/trips/" + t + "/photo-links"),
      // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: honor the Show-hidden
      // toggles on a bundle reload (e.g. cross-tab BroadcastChannel)
      // so hidden rows don't silently vanish mid-review.
      api("/api/trips/" + t + "/location-notes" +
        (st.showHiddenNotes ? "?include_hidden=1" : "")),
      api("/api/trips/" + t + "/sources" +
        (st.showHiddenSources ? "?include_hidden=1" : "")).catch(
        _captureLoadError("Sources failed to load", { sources: [] })),
      api("/api/trips/" + t + "/public-context").catch(
        _captureLoadError("Public context failed to load",
                          { public_context: [] })),
      api("/api/trips/" + t + "/days/reconcile-preview").catch(
        _captureLoadError("Reconcile preview failed to load", null)),
      api("/api/trips/" + t + "/travelogue-preview").catch(
        _captureLoadError("Travelogue preview failed to load", null)),
    ]).then(function (outs) {
      st.tree = outs[0];
      st.days = outs[1].days || [];
      // 2026-07-23 partition: outside-window cards are kept for
      // preservation but rendered in their own section so their stale
      // day_index numbers don't collide with the current 1..N calendar.
      st.preservedDays = outs[1].preserved || [];
      // 2026-07-23 (Bucket B) — when the /days endpoint could load
      // the day rows but the evidence-counts query failed (locked,
      // corrupt, disk full), the response carries a
      // ``counts_warning`` string. We surface it as an amber banner
      // above the calendar so operators don't mistake zero counts
      // for verified absence of evidence.
      st.countsWarning = outs[1].counts_warning || "";
      st.memoirPreview = null;   // whole-trip refresh: drop the cache
      st.photoLinks = outs[2].photo_links || [];
      st.notes = outs[3].notes || [];
      st.sources = outs[4].sources || [];
      st.publicContext = outs[5].public_context || [];
      st.reconcile = outs[6];
      st.travelogue = outs[7];
      st.error = "";
      renderAll();
    }).catch(function (e) {
      st.error = e.message;
      renderAll();
    });
  }

  // ── post-save refresh (WO-TRAVEL-DOC-UNIFY-01 Phase 3B) ──────────────

  function refreshTripBundle() {
    if (!st.trip) return Promise.resolve();
    return loadTripBundle(st.trip.id);
  }

  // st.trip is a ROW out of st.trips, not a live handle. After a trip
  // PATCH the rail rows are stale and st.trip is a detached copy of the
  // pre-save row — re-point it, or the sidebar card keeps showing the old
  // title and dates until the operator clicks away and back.
  function refreshTripsPreservingSelection(tripId) {
    var keep = tripId || (st.trip && st.trip.id) || null;
    return api("/api/trips?person_id=" + encodeURIComponent(st.personId))
      .then(function (out) {
        st.trips = out.trips || [];
        if (!keep) return;
        st.trip = st.trips.filter(function (t) {
          return t.id === keep;
        })[0] || st.trip;
      });
  }

  // POST /api/trips and PATCH /api/trips/{id} can answer with
  // days_warning (day-card generation could not complete) and/or
  // sync_warning (the life-record bridge could not sync). Production
  // learned the hard way that a transient status line loses these to the
  // very next setStatus() — so this is a persistent banner the operator
  // dismisses. A clean response CLEARS it: a warning left standing after
  // a successful re-save reads as an unresolved problem.
  function applyTripWarnings(out) {
    if (!out || typeof out !== "object") { st.tripWarning = ""; return; }
    var parts = [];
    if (out.days_warning) parts.push(String(out.days_warning));
    if (out.sync_warning) parts.push(String(out.sync_warning));
    st.tripWarning = parts.join(" \u2014 ");
    // The Trip Plan tab has carried a `st.daysWarning` banner since the
    // Lab was read-only — and nothing has ever set it, because nothing
    // here could save a trip. Trip create/edit is exactly the call that
    // produces days_warning, so wire it: the warning belongs next to the
    // calendar it is about, not only on the Trip tab.
    st.daysWarning = out.days_warning ? String(out.days_warning) : "";
    // Cleared for the same reason the warnings are: the removal report
    // from a previous save describes cards that are already gone, and
    // leaving it up next to a fresh calendar invites the operator to
    // hunt for a deletion that happened ten minutes ago.
    st.daysNotice = "";
  }

  // ── WO-TRAVEL-DOC-CLOSEOUT-01: memoir-preview invalidation ─────────
  //
  // The preview is cached on the first visit to the Travel Document tab.
  // Without this, approving a note, source or photo moved the COUNTS
  // (which read live `st`) while the rendered preview stayed as it was
  // — so the tab showed "3 story notes in the document" above a preview
  // containing two, and the exported DOCX matched neither of the things
  // on screen. Counts, preview and export must describe one state.
  //
  // Placed inside the RELOAD functions rather than at each approval call
  // site. There are seven writes that can change eligibility today —
  // notes, captured notes, sources, evidence rows, photo links, hide and
  // restore — and every one of them ends in a reload. A seam at the
  // reload is one that a write added next month inherits for free; a
  // list of call sites is one that the next write is quietly missing
  // from, which is exactly how this defect arrived.
  //
  // Refetches immediately only when the tab is OPEN. On any other tab
  // dropping the cache is enough: the tab-switch handler fetches when it
  // finds nothing cached, so a background refetch would be a request for
  // a surface nobody is looking at.
  function invalidateMemoirPreview() {
    st.memoirPreview = null;
    if (destroyed || st.tab !== "document" || !st.trip) return Promise.resolve();
    var tripId = st.trip.id;
    return api("/api/trips/" + encodeURIComponent(tripId) + "/memoir-preview")
      .then(function (out) {
        // The operator can switch trips while this is in flight; a
        // preview for the previous trip must not land on the new one.
        if (destroyed || !st.trip || st.trip.id !== tripId) return;
        st.memoirPreview = out;
        renderAll();
      })
      .catch(function (e) {
        if (destroyed) return;
        st.error = e.message;
        renderAll();
      });
  }

  function reloadDays() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/days")
      .then(function (out) {
        st.days = out.days || [];
        st.preservedDays = out.preserved || [];
        st.countsWarning = out.counts_warning || "";
      });
  }

  function reloadNotes() {
    if (!st.trip) return Promise.resolve();
    // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: include hidden rows only
    // while the Story Notes "Show hidden" toggle is on.
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/location-notes" +
      (st.showHiddenNotes ? "?include_hidden=1" : ""))
      .then(function (out) { st.notes = out.notes || []; })
      .then(invalidateMemoirPreview);
  }

  function reloadPhotoLinks() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/photo-links")
      .then(function (out) { st.photoLinks = out.photo_links || []; })
      .then(invalidateMemoirPreview);
  }

  function reloadSources() {
    if (!st.trip) return Promise.resolve();
    // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: include hidden rows only
    // while the Sources "Show hidden" toggle is on.
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/sources" +
      (st.showHiddenSources ? "?include_hidden=1" : ""))
      .then(function (out) { st.sources = out.sources || []; })
      .then(invalidateMemoirPreview);
  }

  function reloadReconcile() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) +
      "/days/reconcile-preview")
      .then(function (out) { st.reconcile = out; })
      .catch(function () { st.reconcile = null; })
      .then(function () { return maybeAutoAddMissingDays(); });
  }

  // WO-TRIP-PLAN-AS-HUB-01 Phase A --- day cards are generated from the
  // trip dates without being asked for. Chris's ruling, 2026-07-28:
  // "Auto-generate added days silently; if shrinking would drop a day
  // that has content, don't, and show what's on it so I can move or
  // clear it first. Empty days are dropped without asking."
  //
  // This is the ADD half, and only the add half. There is no route on
  // this surface that removes a day card, so the drop half --- including
  // the empty cards Chris is willing to lose --- is later work and the
  // outside-date banner says so in the operator's own words.
  //
  // "Silently" means without a prompt, not without a report: a failure
  // lands in st.daysWarning, which renderPlan already draws above the
  // calendar. Swallowing it would leave an operator looking at a short
  // calendar with nothing on screen admitting why.
  // Keyed on the trip AND on the exact set of dates that were missing
  // when the attempt ran.
  //
  // [The key was the trip id alone. Corrected 2026-07-28 on Chris's
  // review of this phase: "Replace the once-per-trip auto-generation
  // guard with a guard tied to the current missing-date set, or reset it
  // after trip-date edits." Keyed on the trip alone, extending a trip's
  // dates inside one browser session found the new dates missing and
  // then declined to add them, because that trip had already been
  // tried --- so the calendar stayed short until the surface was
  // remounted. That contradicts the promise this phase makes, which is
  // that the day cards are derived from the CURRENT trip dates.]
  //
  // The server covers the common path already: a PATCH that moves the
  // trip dates runs its own add-missing reconcile before it answers
  // (_auto_reconcile_days_on_patch). This guard is the second line, for
  // the paths that do not go through a trip-date save --- a window that
  // was already open when another tab moved the dates, a reconcile that
  // failed server-side and left the gap behind.
  var autoDaysTried = {};

  // A mount-lifetime ceiling, and deliberately not part of the key.
  // The key stops a repeat of the SAME attempt; this stops an unbounded
  // sequence of DIFFERENT ones. Adding reloads the preview, which lands
  // back here, so this is a cycle: while each pass strictly shrinks the
  // missing set the cycle ends on its own, and the old once-per-trip key
  // made that guarantee structurally. A key that moves with the data
  // does not, so the bound is stated instead of assumed.
  var autoDaysAttempts = 0;
  var AUTO_DAYS_MAX_ATTEMPTS = 6;

  function autoDaysKey(tripId, missing) {
    // Sorted, because the same gap reported in a different order is the
    // same gap, and a key that disagreed would re-add dates that are
    // already there.
    return String(tripId) + "|" + missing.slice().sort().join(",");
  }

  function maybeAutoAddMissingDays() {
    if (!st.trip) return Promise.resolve();
    var rec = st.reconcile;
    var missing = (rec && rec.missing_dates) || [];
    if (!missing.length) return Promise.resolve();
    var key = autoDaysKey(st.trip.id, missing);
    // Once per (trip, missing-set) per mount. The add reloads the
    // preview, which lands back in this function; without the guard a
    // route that failed to add would re-fire for as long as the tab
    // stayed open. A failed attempt keeps its key, so it does not
    // retry itself --- the operator retries it, from the reconcile
    // review, which is what the warning below points at.
    if (autoDaysTried[key]) return Promise.resolve();
    if (autoDaysAttempts >= AUTO_DAYS_MAX_ATTEMPTS) {
      st.daysWarning = "Day cards stopped generating automatically after " +
        AUTO_DAYS_MAX_ATTEMPTS + " attempts in this session. Reload the " +
        "page, and if the calendar is still short, open the reconcile " +
        "review and add the days by hand.";
      return Promise.resolve();
    }
    autoDaysTried[key] = true;
    autoDaysAttempts += 1;
    var tripId = st.trip.id;
    return api("/api/trips/" + encodeURIComponent(tripId) + "/days/reconcile",
      { method: "POST", body: { add_missing: true } })
      .then(function () {
        // Same rule applyTripWarnings already follows for the save path:
        // a warning left standing after the thing it complained about
        // succeeded reads as an unresolved problem.
        st.daysWarning = "";
        return Promise.all([reloadDays(), reloadReconcile()]);
      })
      .catch(function (e) {
        st.daysWarning = "Day cards could not be generated from the trip " +
          "dates automatically: " + e.message + " Open the reconcile " +
          "review to add them by hand.";
      });
  }

  // ── the shrink half (WO-TRIP-PLAN-AS-HUB-01 Phase A, correction 2) ──
  //
  // Chris, reviewing Phase A on 2026-07-28: "Implement the complete
  // shrinking-date rule: remove empty out-of-range days; refuse and
  // clearly list out-of-range days containing work."
  //
  // The measure of "holds work" here mirrors the server's _day_is_empty
  // deliberately, and just as deliberately does NOT use the `counts`
  // the /days route merges into each card. Those counts are generous by
  // design --- they include photos matched to the day by taken-date and
  // notes inherited through the day's stop or region --- and since
  // generated cards are auto-assigned a region, on any trip with
  // region-scoped notes EVERY card would report content, the refusal
  // would fire every time, and the feature would ship and do nothing.
  // What counts as work here is what is attached to this day card
  // (trip_day_id) plus what was typed into the day row itself.
  //
  // The client can undercount: the notes and sources lists exclude
  // hidden rows unless the operator asked for them. That is safe and
  // not merely tolerable --- the server re-decides emptiness inside the
  // write transaction and hands back anything it refused to delete in
  // kept_out_of_range, which this surface reports. The client's answer
  // decides what to SAY before the save; the server's decides what
  // actually happens.
  var DAY_OWN_TEXT_FIELDS = ["title", "main_location", "lodging_base",
    "morning_notes", "afternoon_notes", "evening_notes"];
  var DAY_OWN_LIST_FIELDS = ["places_visited_json", "meals_json"];

  function dayOwnContent(day) {
    var held = [];
    DAY_OWN_TEXT_FIELDS.forEach(function (f) {
      if (String(day[f] == null ? "" : day[f]).trim()) held.push(f);
    });
    DAY_OWN_LIST_FIELDS.forEach(function (f) {
      var v = day[f];
      if (typeof v === "string") {
        try { v = JSON.parse(v); } catch (e) { v = null; }
      }
      if (v && v.length) held.push(f);
    });
    // A day pinned to a stop is a routing decision somebody made. It is
    // not text, but re-making it is work, so the card is not bare.
    if (day.trip_stop_id) held.push("trip_stop_id");
    return held;
  }

  function dayHolds(day) {
    // Lori captures are counted apart from typed story notes because
    // they read differently to the person who has to go move them.
    var lori = 0, written = 0;
    st.notes.forEach(function (n) {
      if (n.trip_day_id !== day.id) return;
      if (n.source_surface === "travel_doc_modal") lori += 1;
      else written += 1;
    });
    return {
      photos: st.photoLinks.filter(function (l) {
        return l.trip_day_id === day.id;
      }).length,
      lori: lori,
      notes: written,
      sources: st.sources.filter(function (s) {
        return s.trip_day_id === day.id;
      }).length,
      own: dayOwnContent(day),
    };
  }

  function dayIsEmpty(day) {
    var h = dayHolds(day);
    return !(h.photos || h.lori || h.notes || h.sources || h.own.length);
  }

  function countPhrase(n, one, many) {
    return n + " " + (n === 1 ? one : many);
  }

  function holdsPhrase(h) {
    var parts = [];
    if (h.photos) parts.push(countPhrase(h.photos, "photo", "photos"));
    if (h.lori) parts.push(countPhrase(h.lori, "Lori capture", "Lori captures"));
    if (h.notes) parts.push(countPhrase(h.notes, "story note", "story notes"));
    if (h.sources) parts.push(countPhrase(h.sources, "source", "sources"));
    if (h.own.length) {
      parts.push(countPhrase(h.own.length, "typed field", "typed fields"));
    }
    if (!parts.length) return "content";
    if (parts.length === 1) return parts[0];
    return parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
  }

  // Day cards that are in the calendar NOW and would not be after a save
  // with these dates. Scoped to st.days on purpose: an already-preserved
  // card from some earlier date range must never block a date edit, or
  // one old card with a note on it would freeze the trip's dates for
  // good, and the operator's only way out would be to destroy the note.
  //
  // Clearing the dates returns nothing. It is not shrinking --- there is
  // no new window for a card to be outside of --- and the server's
  // existing preserve behaviour is the right answer to it.
  function daysLeavingWindow(startIso, endIso) {
    var s = datePrefix(startIso), e = datePrefix(endIso);
    if (!s || !e) return [];
    return (st.days || []).filter(function (d) {
      var dd = datePrefix(d.date);
      return dd && (dd < s || dd > e);
    });
  }

  // Sent only when the save actually took cards out of the window, so an
  // unrelated title edit cannot quietly remove empty preserved cards the
  // operator never asked about.
  function dropEmptyOutOfRangeDays(tripId) {
    return api("/api/trips/" + encodeURIComponent(tripId) + "/days/reconcile",
      { method: "POST", body: { drop_empty_out_of_range: true } })
      .then(function (out) {
        var dropped = (out && out.dropped_days) || [];
        var kept = (out && out.kept_out_of_range) || [];
        if (dropped.length) {
          st.daysNotice = countPhrase(dropped.length, "empty day card",
            "empty day cards") + " outside the new trip dates " +
            (dropped.length === 1 ? "was" : "were") + " removed: " +
            dropped.map(function (d) { return longDate(d.date); }).join(", ") +
            ".";
        }
        if (kept.length) {
          // The client thought these were bare and the server, looking
          // at rows the client cannot see, disagreed. It kept them, which
          // is the right call --- but saying nothing would leave cards on
          // screen that the operator was told would go.
          //
          // [This message opened "N day cards outside the new trip dates
          // could not be removed because there is content attached to
          // them (July 19). They are kept below." until 2026-07-28. Every
          // clause in it was true. It was still wrong, because it was the
          // FIRST thing on screen at the instant of Save and its opening
          // words were "could not be removed" --- which is what a failed
          // save looks like. The dates HAD saved; only the tidy-up was
          // refused. The .catch branch below had led with the save all
          // along, so the failure case read better than the success case.
          // Chris: "change the partial-success warning to begin with
          // 'The trip dates were saved, but...'".]
          //
          // Amber, deliberately, and not because st.daysWarning happened
          // to be the variable in hand. The save succeeded, but the
          // calendar on screen is not the one that was asked for. A
          // neutral st.daysNotice would let that difference pass
          // unremarked and the operator would meet the extra card later
          // with no memory of being told about it.
          st.daysWarning = "The trip dates were saved, but " +
            countPhrase(kept.length, "day card", "day cards") +
            " outside the new dates " +
            (kept.length === 1 ? "was" : "were") +
            " kept because there is content attached to " +
            (kept.length === 1 ? "it" : "them") + ": " +
            kept.map(function (d) { return longDate(d.date); }).join(", ") +
            ". " + (kept.length === 1 ? "It is" : "They are") +
            " still shown below. Turn on “Show hidden” in " +
            "Story Notes and Sources to see what is on them.";
        }
      })
      .catch(function (e) {
        // The dates saved; only the tidy-up failed. Say exactly that, or
        // the operator reads a stale calendar as a failed save.
        st.daysWarning = "The trip dates were saved, but the empty day " +
          "cards outside them could not be removed: " + e.message +
          " They are shown below and nothing was lost.";
      });
  }

  function reloadPublicContext() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/public-context")
      .then(function (out) { st.publicContext = out.public_context || []; })
      .catch(function () {});
  }

  // Evidence changes (OCR / lookup / draft observation / place inference /
  // approve / include / reject / edit) can shift the counts the day cards and
  // metrics show. Refresh the panel AND those counts so nothing stays stale.
  function refreshAfterEvidence() {
    reloadPhotoEvidence();  // clears + re-fetches the evidence panel
    Promise.all([reloadDays(), reloadPhotoLinks(), reloadPublicContext()])
      .then(renderAll)
      .catch(function () {});
  }

  // JS mirror of travel_doc_lori_modal._spoken_context_trim — MUST match so the
  // "Lori will say…" preview shows what the modal direct-answer actually speaks
  // (first sentence, 160-char budget, else word-boundary cap). OCR is NOT
  // trimmed on either side.
  var SPOKEN_CONTEXT_CHARS = 160;
  function spokenContextTrim(text) {
    var t = String(text == null ? "" : text).replace(/\s+/g, " ").trim();
    if (t.length <= SPOKEN_CONTEXT_CHARS) return t;
    var m = /[.!?](\s|$)/.exec(t);
    if (m) {
      var end = m.index + m[0].length;
      if (end >= 12 && end <= SPOKEN_CONTEXT_CHARS + 60) {
        return t.slice(0, end).trim();
      }
    }
    var head = t.slice(0, SPOKEN_CONTEXT_CHARS);
    var sp = head.lastIndexOf(" ");
    return (sp >= 60 ? head.slice(0, sp) : head).trim() + "…";
  }

  // ── person picker (no person_id in the URL) ──────────────────────────

  function renderPersonPicker() {
    root.innerHTML = "";
    var card = el("div", "tdl-card tdl-picker");
    card.appendChild(el("div", "tdl-kicker",
      embedded ? "Travel Doc" : "Travel Doc UI Lab"));
    card.appendChild(el("h2", "", "Choose a narrator"));
    card.appendChild(el("p", "tdl-muted", embedded
      ? "Travel Doc works on one narrator at a time. Pick one below."
      : "This experimental lab needs a narrator. Pick one below (or pass ?person_id= in the URL)."));
    api("/api/people").then(function (out) {
      var people = out.people || out || [];
      if (!people.length) {
        card.appendChild(el("p", "tdl-muted", "No people found."));
        return;
      }
      people.forEach(function (p) {
        card.appendChild(btn("tdl-btn", p.display_name || p.id, function () {
          var u = new URL(window.location.href);
          u.searchParams.set("person_id", p.id);
          window.location.href = u.toString();
        }));
      });
    }).catch(function (e) {
      card.appendChild(el("div", "tdl-error", "Could not load people: " + e.message));
    });
    root.appendChild(card);
  }

  // ── intake: photo upload / source upload / photo cluster ─────────────
  //
  // WO-TRAVEL-DOC-UNIFY-01 Phase 3C. The banner at the head of this file
  // carries the reasoning; this is the code.
  //
  // NOTHING in an open upload drawer may call renderAll(). An
  // <input type="file"> holds a FileList that script cannot write, so a
  // repaint between "choose files" and "Upload" throws the operator's
  // selection away with no way to restore it. Every in-drawer reaction is
  // therefore a direct DOM mutation, and the first repaint of the flow
  // happens after the response lands.

  var SOURCE_TYPES = ["itinerary", "receipt", "hotel", "ticket",
    "note", "map", "link", "other"];

  // Provenance stamp on every photo this surface ingests. The backend
  // records uploaded_from_surface verbatim as photo metadata and gives
  // exactly ONE value special meaning ("travels_shelf" -> stamped
  // needs_operator_review / narrator_uploaded). This is neither the
  // narrator shelf nor the legacy Documenter, so it does not claim to be
  // either.
  var UPLOAD_SURFACE = "travel_doc_unified";

  // ── explicit upload scope ────────────────────────────────────────────
  //
  // One string, three shapes: "trip" | "region:<id>" | "stop:<id>". The
  // destination is NEVER re-derived from st.routeSel at submit time; the
  // route selection seeds the select when the drawer opens and is not
  // consulted again. That is the whole difference between a convenience
  // default and a silent wrong-scope attach.

  function parseScopeKey(key) {
    var s = String(key || "trip");
    if (s.indexOf("region:") === 0) {
      return { level: "region", regionId: s.slice(7), stopId: null };
    }
    if (s.indexOf("stop:") === 0) {
      return { level: "stop", regionId: null, stopId: s.slice(5) };
    }
    return { level: "trip", regionId: null, stopId: null };
  }

  function scopeChoices() {
    var out = [["trip", "Trip — " +
      ((st.trip && st.trip.title) || "this trip")]];
    ((st.tree && st.tree.regions) || []).forEach(function (r) {
      out.push(["region:" + r.id, "Region — " + regionLabel(r)]);
      allStops({ regions: [r] }).forEach(function (e) {
        out.push(["stop:" + e.id, "Stop — " +
          new Array(e.depth + 1).join("• ") + stopLabel(e.node)]);
      });
    });
    return out;
  }

  function scopeNoun(scope) {
    if (scope.level === "stop") {
      var loc = locateStop(scope.stopId);
      return "the stop “" + (loc ? stopLabel(loc.node) : "?") + "”";
    }
    if (scope.level === "region") {
      var r = findRegion(scope.regionId);
      return "the region “" + (r ? regionLabel(r) : "?") + "”";
    }
    return "the trip “" + ((st.trip && st.trip.title) || "") + "”";
  }

  function scopeTargetText(key) {
    var scope = parseScopeKey(key);
    if (scope.level === "stop") {
      var loc = locateStop(scope.stopId);
      if (!loc) return "Target: that stop is no longer in this trip — pick again.";
      return "Target: the stop “" + stopLabel(loc.node) + "” in " +
        regionLabel(loc.region) + ".";
    }
    if (scope.level === "region") {
      var reg = findRegion(scope.regionId);
      if (!reg) return "Target: that region is no longer in this trip — pick again.";
      return "Target: the region “" + regionLabel(reg) +
        "” — not any one stop in it.";
    }
    return "Target: " + scopeNoun(parseScopeKey("trip")) +
      " — not any region or stop.";
  }

  // Seed only. st.routeSel is the Trip tab's selection, and starting the
  // drawer where the operator was already working saves a step — but a
  // stale id must never survive into a request, so both branches re-check
  // that the entity is still in the loaded tree.
  function defaultScopeKey() {
    var sel = st.routeSel;
    if (sel && sel.kind === "stop" && findStop(sel.id)) return "stop:" + sel.id;
    if (sel && sel.kind === "region" && findRegion(sel.id)) {
      return "region:" + sel.id;
    }
    return "trip";
  }

  // ── the intake drawer ────────────────────────────────────────────────

  function openUploadDrawer(kind) {
    if (!st.trip) return;
    if (dayFormDirtyBlocks()) return;
    st.uploadDrawer = { kind: kind, error: "" };
    renderAll();
  }

  function closeUploadDrawer() { st.uploadDrawer = null; renderAll(); }

  function renderUploadDrawer() {
    var ud = st.uploadDrawer;
    var isPhoto = ud.kind === "photo";
    var sh = drawerShell(isPhoto ? "Photo intake" : "Source intake",
      isPhoto ? "Upload photos" : "Upload documents",
      closeUploadDrawer, "tdl-edit-drawer tdl-upload-drawer");

    // Evidence doctrine, stated where the operator is acting rather than
    // in a doc they will not open.
    sh.body.appendChild(el("p", "tdl-intake-doctrine", isPhoto
      ? "Upload is intake, not approval. Photos land as evidence at the " +
        "scope you choose. Captions, OCR, public lookup and anything " +
        "shared with Lori stay behind their own approval steps."
      : "Upload is intake, not approval. Documents land private to this " +
        "trip. Nothing is promoted into the memoir here — that stays " +
        "the In-memoir toggle on the source itself."));

    var scopeSel = selectInput(scopeChoices(), defaultScopeKey());
    sh.body.appendChild(field("Upload to", scopeSel));
    var target = el("div", "tdl-scope-target", scopeTargetText(scopeSel.value));
    sh.body.appendChild(target);
    // Property assignment + textContent swap: the target line has to
    // track the select WITHOUT a repaint, or choosing a scope after
    // choosing files would wipe the files.
    scopeSel.onchange = function () {
      target.textContent = scopeTargetText(scopeSel.value);
    };

    var files = el("input");
    files.type = "file";
    files.multiple = true;
    if (isPhoto) files.accept = "image/*";
    sh.body.appendChild(field(isPhoto ? "Photo file(s)" : "File(s)", files));
    var hint = el("div", "tdl-file-hint", "No files chosen yet.");
    sh.body.appendChild(hint);

    var typeSel = null;
    var titleIn = null;
    if (!isPhoto) {
      typeSel = selectInput(SOURCE_TYPES.map(function (t) { return [t, t]; }),
        "other");
      sh.body.appendChild(field("Type", typeSel));
      titleIn = textInput("", "Leave empty to keep the file's own name");
      sh.body.appendChild(field("Title (optional)", titleIn,
        "One title per upload — with several files each keeps its own name."));
    }

    var errEl = drawerError(sh.body, ud.error);

    var upBtn = btn("tdl-btn tdl-btn-primary",
      isPhoto ? "⬆ Upload photos" : "⬆ Upload documents",
      function () {
        var chosen = Array.prototype.slice.call(files.files || []);
        if (!chosen.length) {
          errEl.textContent = "Choose at least one file first.";
          errEl.hidden = false;
          return;
        }
        var scope = parseScopeKey(scopeSel.value);
        errEl.hidden = true;
        upBtn.disabled = true;
        function fail(e) {
          upBtn.disabled = false;
          if (st.uploadDrawer) {
            st.uploadDrawer.error = "Upload failed: " + e.message;
          } else {
            st.error = e.message;
          }
          renderAll();
        }
        if (isPhoto) {
          uploadPhotoFiles(chosen, scope).catch(fail);
        } else {
          uploadSourceFiles(chosen, scope, typeSel.value,
            (titleIn.value || "").trim()).catch(fail);
        }
      });
    upBtn.disabled = true;

    files.onchange = function () {
      var n = (files.files || []).length;
      upBtn.disabled = !n;
      hint.textContent = !n ? "No files chosen yet."
        : (n === 1 ? "1 file chosen." : n + " files chosen.");
      if (titleIn) {
        // The backend stamps ONE title across the whole request, so a
        // title on a multi-file drop would erase every filename.
        titleIn.disabled = n > 1;
        titleIn.placeholder = n > 1
          ? "Several files — each keeps its own name"
          : "Leave empty to keep the file's own name";
      }
    };

    sh.foot.appendChild(upBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeUploadDrawer));
    return sh.wrap;
  }

  // ── photo upload ─────────────────────────────────────────────────────

  function photoUploadPath(scope) {
    if (scope.level === "stop") {
      return "/api/trips/stops/" + encodeURIComponent(scope.stopId) + "/photos";
    }
    if (scope.level === "region") {
      return "/api/trips/" + encodeURIComponent(st.trip.id) +
        "/regions/" + encodeURIComponent(scope.regionId) + "/photos";
    }
    return "/api/trips/" + encodeURIComponent(st.trip.id) + "/photos";
  }

  function photoUploadSummary(out, scope, sent) {
    var o = out || {};
    var lines = [
      "Sent " + sent + (sent === 1 ? " file" : " files") + " to " +
        scopeNoun(scope) + ".",
      "Ingested: " + (o.uploaded == null ? "?" : o.uploaded) + ".",
    ];
    var warnings = [];
    if (o.duplicates) {
      warnings.push(o.duplicates + " already existed in this narrator's " +
        "library and were not re-ingested.");
    }
    if (o.mismatches) {
      warnings.push(o.mismatches + " flagged: the EXIF date or GPS " +
        "disagrees with where you dropped them. The placement was kept " +
        "— they are in the Needs review filter.");
    }
    if (o.errors) {
      warnings.push(o.errors + " could not be read and were NOT ingested.");
    }
    if (scope.level !== "stop") {
      warnings.push("Dropped above stop level, so these stay unplaced " +
        "until Cluster photos or a stop-level drop places them.");
    }
    return { kind: "upload", busy: false, lines: lines, warnings: warnings };
  }

  function uploadPhotoFiles(chosen, scope) {
    var fd = new FormData();
    chosen.forEach(function (f) { fd.append("files", f); });
    fd.append("uploaded_by_user_id", UPLOAD_SURFACE);
    fd.append("narrator_ready", "true");
    fd.append("uploaded_from_surface", UPLOAD_SURFACE);
    // Deliberately NOT sent: caption. See decision 2 in the file banner.
    return api(photoUploadPath(scope), { method: "POST", body: fd })
      .then(function (out) {
        st.uploadDrawer = null;
        st.photoIntake = photoUploadSummary(out, scope, chosen.length);
        // The operator has to be able to SEE what they just uploaded. A
        // trip- or region-level drop lands unplaced, so a filter left on
        // "Needs review" or "Shared with Lori" would show an empty
        // gallery and read as a failed upload.
        st.photoFilter = "all";
        st.tab = "photos";
        st.error = "";
        notifyTripUpdated(st.trip.id, "photos_uploaded");
        return refreshTripBundle();
      });
  }

  // ── source upload ────────────────────────────────────────────────────

  function uploadSourceFiles(chosen, scope, sourceType, title) {
    var fd = new FormData();
    chosen.forEach(function (f) { fd.append("files", f); });
    fd.append("source_type", sourceType || "other");
    if (scope.level === "region") {
      fd.append("trip_region_id", scope.regionId);
    }
    if (scope.level === "stop") {
      var loc = locateStop(scope.stopId);
      if (loc && loc.region) fd.append("trip_region_id", loc.region.id);
      fd.append("trip_stop_id", scope.stopId);
    }
    if (title && chosen.length === 1) fd.append("title", title);
    // Deliberately NOT sent: trip_day_id (day attach is its own act) and
    // include_in_memoir (intake never promotes). See the file banner.
    return api("/api/trips/" + encodeURIComponent(st.trip.id) +
      "/sources/upload", { method: "POST", body: fd })
      .then(function (out) {
        var n = ((out && out.source_ids) || []).length || chosen.length;
        st.uploadDrawer = null;
        st.sourceIntake = {
          busy: false,
          lines: [
            "Uploaded " + n + (n === 1 ? " document" : " documents") +
              " to " + scopeNoun(scope) + " as “" +
              (sourceType || "other") + "”.",
            "Private to this trip. Not attached to a day card and not in " +
              "the memoir — both of those stay deliberate acts.",
          ],
          warnings: [],
        };
        st.sourceFilter = "all";
        st.tab = "sources";
        st.error = "";
        notifyTripUpdated(st.trip.id, "sources_uploaded");
        return refreshTripBundle();
      });
  }

  // ── photo cluster ────────────────────────────────────────────────────

  function runClusterPhotos() {
    if (!st.trip) return Promise.resolve();
    st.photoIntake = { kind: "cluster", busy: true, lines: [], warnings: [] };
    renderAll();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) +
      "/cluster-photos",
      { method: "POST", body: { narrator_id: st.personId || null } })
      .then(function (out) {
        var o = out || {};
        var warnings = [];
        if (o.needs_review) {
          warnings.push(o.needs_review + " placement" +
            (o.needs_review === 1 ? "" : "s") + " landed below the " +
            "confidence threshold (" +
            (o.review_threshold == null ? "?" : o.review_threshold) +
            ") — placed but unverified, in the Needs review filter.");
        }
        if (o.skipped_operator_confirmed) {
          warnings.push(o.skipped_operator_confirmed + " already carried an " +
            "operator placement and were left exactly as they were.");
        }
        // Honest, not flattering: the backend clusters the NARRATOR's
        // whole photo library, so this number is not a trip statistic.
        warnings.push("Clustering reads every photo belonging to this " +
          "narrator, not only ones uploaded here — “considered” " +
          "counts the library, not the trip.");
        st.photoIntake = {
          kind: "cluster",
          busy: false,
          lines: [
            "Photos considered: " +
              (o.photos_considered == null ? "?" : o.photos_considered) + ".",
            "Photo links written or updated: " +
              (o.links_written == null ? "?" : o.links_written) + ".",
          ],
          warnings: warnings,
        };
        st.photoFilter = "all";
        st.error = "";
        notifyTripUpdated(st.trip.id, "photos_clustered");
        return refreshTripBundle();
      })
      .catch(function (e) {
        st.photoIntake = {
          kind: "cluster", busy: false, lines: [], warnings: [],
          error: "Cluster failed: " + e.message,
        };
        renderAll();
      });
  }

  // ── in-panel intake result ───────────────────────────────────────────
  //
  // The result of an intake run renders INSIDE the tab that owns it. A
  // native dialog would be one OK click away from erasing a duplicate
  // count or a date mismatch the operator needed to read.

  function renderIntakeResult(res, dismiss) {
    var box = el("div", "tdl-intake-result" +
      (res.error ? " tdl-intake-failed" : ""));
    if (res.busy) {
      box.appendChild(el("p", "tdl-intake-line", "Working…"));
      return box;
    }
    if (res.error) box.appendChild(el("p", "tdl-intake-err", res.error));
    (res.lines || []).forEach(function (t) {
      box.appendChild(el("p", "tdl-intake-line", t));
    });
    (res.warnings || []).forEach(function (t) {
      box.appendChild(el("p", "tdl-intake-warn", "⚠ " + t));
    });
    box.appendChild(btn("tdl-btn tdl-btn-small", "Dismiss", dismiss));
    return box;
  }

  function renderPhotoIntakeBar() {
    var bar = el("div", "tdl-intake-bar");
    bar.appendChild(btn("tdl-btn tdl-btn-primary", "⬆ Upload photos",
      function () { openUploadDrawer("photo"); }));
    var clusterBtn = btn("tdl-btn", "✦ Cluster photos", runClusterPhotos);
    if (st.photoIntake && st.photoIntake.busy) clusterBtn.disabled = true;
    bar.appendChild(clusterBtn);
    bar.appendChild(el("span", "tdl-muted tdl-intake-note",
      "Intake only — placing, captioning and sharing stay separate."));
    return bar;
  }

  function renderSourceIntakeBar() {
    var bar = el("div", "tdl-intake-bar");
    bar.appendChild(btn("tdl-btn tdl-btn-primary", "⬆ Upload document",
      function () { openUploadDrawer("source"); }));
    bar.appendChild(el("span", "tdl-muted tdl-intake-note",
      "Uploaded documents are private to this trip and are not promoted " +
      "into the memoir."));
    return bar;
  }

  // ── shell ─────────────────────────────────────────────────────────────

  // WO-TRIP-PLAN-AS-HUB-01 Phase A -- the nav is three controls, not ten.
  //
  // [Corrected 2026-07-28. This read as a flat ten-entry TABS array:
  // trip, plan, photos, evidence, notes, captured, sources, travelogue,
  // draft, lori. It is kept here in words because the count was the
  // defect: ten tabs advertise ten destinations, and Chris's normal
  // workflow uses about three. Nothing in the list was wrong on its own,
  // which is exactly how a bar gets to ten.]
  //
  // Trip Plan is the workspace and Photos is the other place an operator
  // works. Everything else on the old bar is an administrative review
  // step, and Chris's ruling is that a review step does not get permanent
  // top-level standing: "I would not keep Evidence as a permanent
  // top-level tab unless you expect to review imported photographs
  // constantly. Your normal workflow is the trip and its days. Evidence is
  // an administrative review step."
  //
  // Two ids left the bar entirely, for different reasons:
  //   "trip" -- trip setup (dates, regions, stops) is reached from the
  //             Trip Plan toolbar, beside the dates it edits. It is a
  //             destination, so it keeps its tab id and its renderer; it
  //             just stops claiming a permanent slot next to the day
  //             calendar it configures.
  //   "lori" -- deleted outright, renderer and all. Lori is an overlay
  //             over the day you are already on (openLoriOverlay), and a
  //             tab was a second way in that arrived with no day.
  var PRIMARY_TABS = [
    ["plan", "Trip Plan"],
    ["photos", "Photos"],
  ];

  // Captured Notes sits here TEMPORARILY and the record should say so:
  // it is narrator-scoped across every trip (12 notes spanning two trips
  // at the time of writing), so it is the one surface here that does not
  // describe the selected trip at all. It belongs at a narrator-level
  // home, which a later work order owes it.
  var REVIEW_TABS = [
    ["evidence", "Evidence"],
    ["notes", "Story Notes"],
    ["sources", "Sources"],
    ["travelogue", "Travelogue"],
    ["document", "Travel Document"],
    ["draft", "Draft"],
    ["captured", "Captured Notes"],
  ];

  function reviewTabLabel(tab) {
    var hit = REVIEW_TABS.filter(function (t) { return t[0] === tab; })[0];
    return hit ? hit[1] : "";
  }

  function setTab(tab) {
    // Phase 3B renamed the "current" tab id to "trip". Anything still
    // asking for the old id lands on the tab that replaced it.
    if (tab === "current") tab = "trip";
    // Phase A deleted the Lori tab. Same treatment as "current": anything
    // still asking for it lands on the surface that replaced it, which is
    // Trip Plan with Lori available as an overlay over the selected day.
    // A dead tab id that fell through to the default arm would render an
    // empty div, which reads as a broken screen rather than a moved one.
    if (tab === "lori") tab = "plan";
    // WO-TRIP-LANE-AUDIT-FIXPACK-02 (M5b): a tab switch re-renders and
    // would silently discard unsaved day-inspector edits.
    if (dayFormDirtyBlocks()) return;
    st.tab = tab;
    st.loriOverlay = false;
    if (tab === "travelogue" && !st.travelogue && st.trip) {
      api("/api/trips/" + encodeURIComponent(st.trip.id) + "/travelogue-preview")
        .then(function (out) { st.travelogue = out; renderAll(); })
        .catch(function (e) { st.error = e.message; renderAll(); });
    }
    // WO-TRAVEL-DOC-CLOSEOUT-01 — the finished document's own surface.
    // Same lazy shape as the travelogue above, for the same reason: a
    // fetch from render() would re-render, which would fetch again.
    if (tab === "document" && !st.memoirPreview && st.trip) {
      api("/api/trips/" + encodeURIComponent(st.trip.id) + "/memoir-preview")
        .then(function (out) { st.memoirPreview = out; renderAll(); })
        .catch(function (e) { st.error = e.message; renderAll(); });
    }
    // WO-2 Phase 2 — same lazy shape as the travelogue: fetched on the tab
    // switch, never from render. A queue fetched during render would
    // re-render, which would fetch again.
    if (tab === "evidence" && !st.evidence && !st.evidenceOff && st.personId) {
      reloadEvidence().then(function () { renderAll(); });
    }
    // Phase 2D -- the import strip's own probe, on the same lazy shape and
    // kept as a SEPARATE request on purpose. /health reports the picker
    // lane's two flags and whether the server holds credentials at all;
    // the queue's own fetch can answer neither, because the two lanes are
    // gated differently. Guarded on st.pickerHealth rather than on
    // st.evidence so the queue failing does not silently take the strip's
    // probe with it.
    if (tab === "evidence" && !st.pickerHealth && !st.pickerOff &&
        st.personId) {
      reloadPickerHealth().then(function () { renderAll(); });
    }
    // Same lazy shape, same reason: fetched on the tab switch, never
    // from render.
    if (tab === "captured" && !st.captured && !st.capturedOff && st.personId) {
      reloadCaptured().then(function () { renderAll(); });
    }
    renderAll();
  }

  function renderAll() {
    // Phase 1.1 — the backstop. Every render* function in this file is
    // reached through renderAll(), so one early return here means a dead
    // mount cannot repaint no matter which path called it. api() should
    // already have swallowed the async ones; this catches synchronous
    // callers (a queued event handler, a timer) and any future flow that
    // does not go through api().
    if (destroyed) return;

    // Preserve the workspace scroll position across re-renders (drawer
    // open/close, saves, selection) so "back" always lands where the
    // operator left off.
    var prevMain = root.querySelector(".tdl-main");
    if (prevMain) st.mainScroll = prevMain.scrollTop;

    // Same reason, for the timeline's own scrolling pane: saving an
    // inline row repaints the whole app, and the day must not jump back
    // to the top under the operator.
    var prevTl = root.querySelector(".tdl-cal-timeline");
    if (prevTl && st.tripCal) st.tripCal.scroll = prevTl.scrollTop;

    root.innerHTML = "";
    var app = el("div", "tdl-app");

    // Topbar
    var top = el("header", "tdl-topbar");
    var brand = el("div", "tdl-brand");
    brand.appendChild(el("span", "tdl-brand-mark", "✣"));
    var b = el("strong", "", "Lorevox");
    brand.appendChild(b);
    brand.appendChild(el("span", "tdl-divider"));
    brand.appendChild(el("span", "", "Travel Doc"));
    // Phase 2: the badge is standalone-only. In the shell this surface is
    // the Travel Doc workspace, not a side experiment, and labelling it
    // "experimental" is what made operators route around it.
    if (!embedded) {
      brand.appendChild(el("span", "tdl-lab-badge", "UI Lab · experimental"));
    }
    if (st.personLabel) {
      brand.appendChild(el("span", "tdl-muted tdl-brand-person", st.personLabel));
    }
    top.appendChild(brand);
    var tabs = el("nav", "tdl-tabs");
    PRIMARY_TABS.forEach(function (t) {
      var tb = btn(st.tab === t[0] ? "tdl-active" : "", t[1], function () { setTab(t[0]); });
      tabs.appendChild(tb);
    });
    // Review is a native <details>, and that is a deliberate choice
    // rather than a shortcut. A hand-rolled menu needs a document-level
    // click listener to close on an outside click, and this module has a
    // destroy() contract that a stray global listener quietly breaks --
    // the same argument the timer inventory already makes about handles
    // nobody stores. renderAll() rebuilds the bar, so choosing an item
    // closes the menu for free.
    var isReview = REVIEW_TABS.filter(function (t) {
      return t[0] === st.tab;
    }).length > 0;
    var menu = document.createElement("details");
    menu.className = "tdl-tabmenu" + (isReview ? " tdl-active" : "");
    // When a review surface is open the summary names it, because a menu
    // that collapses back to the word "Review" would leave the operator
    // on a screen with nothing on the bar saying where they are.
    menu.appendChild(el("summary", "tdl-tabmenu-summary",
      isReview ? ("Review · " + reviewTabLabel(st.tab) + " \u25be") :
        "Review \u25be"));
    var panel = el("div", "tdl-tabmenu-panel");
    REVIEW_TABS.forEach(function (t) {
      panel.appendChild(btn(st.tab === t[0] ? "tdl-active" : "", t[1],
        function () { setTab(t[0]); }));
    });
    menu.appendChild(panel);
    tabs.appendChild(menu);
    top.appendChild(tabs);
    app.appendChild(top);

    // Layout
    var withInspector = (st.tab === "plan" && st.selectedDayId);
    var layoutCls = "tdl-layout" +
      (withInspector ? " tdl-has-inspector" : "") +
      (railCollapsed ? " tdl-rail-collapsed" : "");
    var layout = el("section", layoutCls);
    layout.appendChild(renderSidebar());
    var main = el("section", "tdl-main");
    if (st.error) main.appendChild(el("div", "tdl-error", st.error));
    // Phase 3B — days_warning / sync_warning from the last trip save.
    // Above the tab content and outside it, because the warning outlives
    // the tab the operator happened to be on when the save returned.
    if (st.tripWarning) main.appendChild(renderTripWarning());
    // WO-2 Phase 2 — the Evidence tab is deliberately exempt from the
    // selected-trip gate, and it is the only one. Every other tab
    // describes a trip. The review queue describes a PERSON's imports,
    // and the rows most in need of review are precisely the ones not
    // filed to a trip yet — so gating it on a selection would hide the
    // unfiled queue behind a trip the operator has not made.
    // Lane 3 adds the second exemption, on the same argument: the
    // captured-note review describes a PERSON's captured notes, and the
    // rows most in need of promotion are the ones the operator cannot
    // locate by trip.
    if (!st.trip && st.tab !== "evidence" && st.tab !== "captured") {
      main.appendChild(el("div", "tdl-empty",
        st.trips.length ? "Select a trip from the left rail." :
          "No trips yet for this narrator. Use + New trip in the left rail " +
          "to create one here."));
    } else {
      main.appendChild(renderTab());
    }
    layout.appendChild(main);
    if (withInspector) layout.appendChild(renderInspector());
    app.appendChild(layout);

    // Drawers / overlays (in-lab — never navigate away).
    if (st.trip && st.loriOverlay) app.appendChild(renderLoriOverlay());
    if (st.trip && st.tripCal) app.appendChild(renderTripCalendarModal());
    if (st.trip && st.photoPickerDayId) app.appendChild(renderPhotoPicker());
    if (st.trip && st.noteDrawerDayId) app.appendChild(renderNoteDrawer());
    if (st.trip && st.sourceDrawerDayId) app.appendChild(renderSourceDrawer());
    // Phase 3C — intake drawer. Gated on st.trip: every upload endpoint is
    // addressed under a trip, so there is no such thing as a trip-less
    // upload to keep reachable.
    if (st.trip && st.uploadDrawer) app.appendChild(renderUploadDrawer());
    if (st.trip && st.reconcileDrawerOpen) app.appendChild(renderReconcileDrawer());
    // Phase 3A — deliberately NOT gated on st.trip. Every other drawer
    // describes the selected trip; this one describes a trip that is being
    // taken away, and the flow that clears st.trip is the same flow that
    // clears the review. Gating it on st.trip would make an unclosable
    // invisible state reachable.
    // Phase 3B editors. The trip editor is deliberately NOT gated on
    // st.trip either: "+ New trip" is reachable precisely when there is
    // no selected trip, and gating it would make the empty state a dead
    // end again. The region/stop editors ARE gated — they edit rows that
    // only exist inside a selected trip.
    if (st.tripEditor) app.appendChild(renderTripEditorDrawer());
    if (st.trip && st.regionEditor) app.appendChild(renderRegionEditorDrawer());
    if (st.trip && st.stopEditor) app.appendChild(renderStopEditorDrawer());
    if (st.trip && st.routeDelete) app.appendChild(renderRouteDeleteReview());
    if (st.deleteReview) app.appendChild(renderDeleteTripReview());
    // WO-2 Phase 2 — not gated on st.trip, for the same reason the tab is
    // not: a review opened on an unfiled candidate has no trip behind it.
    if (st.evidenceDrawer) app.appendChild(renderEvidenceDrawer());

    root.appendChild(app);
    main.scrollTop = st.mainScroll || 0;
    if (st.tripCal) {
      var tlPane = root.querySelector(".tdl-cal-timeline");
      if (tlPane) tlPane.scrollTop = st.tripCal.scroll || 0;
      restoreTimelineEditFocus();
    }
  }

  // ── left rail: trip list + route navigator (collapsible) ─────────────

  function toggleRail() {
    railCollapsed = !railCollapsed;
    try {
      localStorage.setItem("tdlRailCollapsed", railCollapsed ? "1" : "0");
    } catch (e) { /* private mode — collapse still works for this session */ }
    renderAll();
  }

  function renderSidebar() {
    var side = el("aside", "tdl-sidebar" + (railCollapsed ? " tdl-collapsed" : ""));

    if (railCollapsed) {
      var expand = btn("tdl-rail-toggle", "⟩", toggleRail);
      expand.title = "Show trips";
      side.appendChild(expand);
      side.appendChild(el("div", "tdl-rail-vlabel", "Trips"));
      return side;
    }

    var railHead = el("div", "tdl-rail-head");
    railHead.appendChild(el("div", "tdl-section-label", "My Trips"));
    // Phase 3B — trip creation lives on the rail, not inside the Trip
    // tab, because the tab needs a selected trip and creating the FIRST
    // trip is the case with none.
    railHead.appendChild(btn("tdl-btn tdl-btn-small tdl-btn-gold",
      "+ New trip", function () { openTripEditor("create"); }));
    var collapse = btn("tdl-rail-toggle", "⟨", toggleRail);
    collapse.title = "Hide trips";
    railHead.appendChild(collapse);
    side.appendChild(railHead);

    var list = el("ul", "tdl-trip-list");
    st.trips.forEach(function (t) {
      var li = el("li");
      li.appendChild(btn(st.trip && st.trip.id === t.id ? "tdl-active" : "",
        t.title || "Untitled trip", function () { selectTrip(t.id); }));
      list.appendChild(li);
    });
    side.appendChild(list);

    if (st.trip) {
      var card = el("div", "tdl-card");
      card.appendChild(el("div", "tdl-trip-image"));
      card.appendChild(el("h3", "", st.trip.title || "Untitled trip"));
      var range = (st.trip.start_date || "?") + " → " + (st.trip.end_date || "?");
      card.appendChild(el("p", "tdl-muted", range));
      card.appendChild(el("span", "tdl-status", st.trip.status || "draft"));
      // Phase 3A — the destructive control lives on the selected-trip card
      // (never on the rail rows), so it can only ever act on the trip whose
      // title, dates and status the operator is currently looking at.
      var delRow = el("div", "tdl-card-actions");
      delRow.appendChild(btn("tdl-btn tdl-btn-small tdl-btn-danger",
        "Delete trip", function () { deleteTrip(st.trip); }));
      card.appendChild(delRow);
      side.appendChild(card);

      side.appendChild(el("div", "tdl-section-label", "Route Outline"));
      var tree = el("div", "tdl-route-tree");
      ((st.tree && st.tree.regions) || []).forEach(function (r) {
        var det = document.createElement("details");
        det.open = true;
        var sum = el("summary", "");
        // Phase 3D — the region label is a selection control here too, so
        // the rail and the board share one st.routeSel instead of the
        // rail being able to express only half of it. preventDefault
        // stops the click from also toggling the <details>: selecting a
        // region must not collapse its stops out from under the operator.
        var regBtn = btn("tdl-route-region-pick" +
          (isRouteSelected("region", r.id) ? " tdl-active" : ""),
          r.title || "Region", function (ev) {
            if (ev && ev.preventDefault) ev.preventDefault();
            if (ev && ev.stopPropagation) ev.stopPropagation();
            routeSelect("region", r.id, r.id);
          });
        sum.appendChild(regBtn);
        det.appendChild(sum);
        (function walk(stops) {
          (stops || []).forEach(function (s) {
            var isSel = isRouteSelected("stop", s.id);
            det.appendChild(btn("tdl-route-item" + (isSel ? " tdl-active" : ""),
              s.location_name || s.title || "Stop", function () {
                // FIXPACK-02 (M5b): route-rail selection re-renders too.
                routeSelect("stop", s.id, r.id);
              }));
            walk(s.children);
          });
        })(r.stops);
        tree.appendChild(det);
      });
      side.appendChild(tree);
    }
    return side;
  }

  // ── tab dispatch ──────────────────────────────────────────────────────

  function renderTab() {
    switch (st.tab) {
      case "trip": return renderTripTab();
      case "plan": return renderPlan();
      case "photos": return renderPhotos();
      case "evidence": return renderEvidence();
      case "notes": return renderNotes();
      case "captured": return renderCaptured();
      case "sources": return renderSources();
      case "travelogue": return renderTravelogue();
      case "document": return renderTravelDocument();
      case "draft": return renderDraft();
      default: return el("div");
    }
  }

  // ── Trip tab (WO-TRAVEL-DOC-UNIFY-01 Phase 3B) ───────────────────────
  //
  // Phase 2 shipped this tab as a banner pointing at the old Documenter.
  // It is now the trip/region/stop editor itself: header + toolbar +
  // route board, with every mutation going through a drawer.
  //
  // Phase 4 removed prodTravelDocUrl() and the deep link that used to sit
  // at the foot of the route board. That link was the last thing in the
  // workspace still framing this surface as the newcomer, and it was the
  // only reason this module knew the old page's filename at all.

  function renderTripWarning() {
    var box = el("div", "tdl-warn-banner tdl-trip-warning");
    box.appendChild(el("strong", "", "Trip save warning: "));
    box.appendChild(document.createTextNode(st.tripWarning));
    box.appendChild(btn("tdl-btn tdl-btn-small", "✕ Dismiss", function () {
      st.tripWarning = "";
      renderAll();
    }));
    return box;
  }

  // ── shared drawer field builders ─────────────────────────────────────
  //
  // Every editor below follows the drawer idiom already used by the note
  // and delete-review drawers: the input elements live in the render
  // closure and are read on submit. Nothing repaints while the operator
  // types, so no field can lose focus mid-word.

  function field(labelText, inputEl, hint) {
    var lab = el("label", "tdl-label");
    lab.appendChild(el("span", "", labelText));
    lab.appendChild(inputEl);
    if (hint) lab.appendChild(el("small", "tdl-muted", hint));
    return lab;
  }

  function textInput(value, placeholder) {
    var i = el("input");
    i.type = "text";
    i.value = (value === null || value === undefined) ? "" : String(value);
    if (placeholder) i.placeholder = placeholder;
    return i;
  }

  function dateInput(value) {
    var i = el("input");
    i.type = "date";
    i.value = value ? String(value).slice(0, 10) : "";
    return i;
  }

  function areaInput(value, placeholder) {
    var t = el("textarea");
    t.value = (value === null || value === undefined) ? "" : String(value);
    if (placeholder) t.placeholder = placeholder;
    return t;
  }

  // options: [[value, label], ...]
  function selectInput(options, value) {
    var sel = el("select");
    options.forEach(function (o) {
      var opt = el("option", "", o[1]);
      opt.value = o[0];
      sel.appendChild(opt);
    });
    sel.value = (value === null || value === undefined) ? "" : String(value);
    return sel;
  }

  function drawerShell(kicker, title, onClose, cls) {
    var wrap = el("div", "tdl-drawer-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) onClose();
    });
    var drawer = el("aside", "tdl-drawer " + cls);
    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    ht.appendChild(el("div", "tdl-kicker", kicker));
    ht.appendChild(el("strong", "", title));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn tdl-btn-small", "✕ Close", onClose));
    drawer.appendChild(head);
    var body = el("div", "tdl-drawer-body");
    var foot = el("div", "tdl-drawer-foot");
    drawer.appendChild(body);
    drawer.appendChild(foot);
    wrap.appendChild(drawer);
    return { wrap: wrap, drawer: drawer, body: body, foot: foot };
  }

  // Live, NON-blocking date sanity note. Property assignment on oninput
  // (not addEventListener) and a textContent swap, so it updates without
  // a repaint and re-opening the drawer cannot stack a stale handler.
  function attachDateNote(host, vStart, vEnd, boundStart, boundEnd, label) {
    var note = el("div", "tdl-date-warn", "");
    host.appendChild(note);
    function refresh() {
      var t = dateRangeWarning(vStart.value, vEnd.value,
                               boundStart, boundEnd, label);
      note.textContent = t;
      note.hidden = !t;
    }
    vStart.oninput = refresh;
    vEnd.oninput = refresh;
    refresh();
    return note;
  }

  // Inline error line. Failures render INSIDE the drawer the operator is
  // standing in — never as a native dialog, and never by closing the
  // panel out from under them and losing what they typed.
  function drawerError(host, text) {
    var box = el("div", "tdl-delete-error", text || "");
    box.hidden = !text;
    host.appendChild(box);
    return box;
  }

  // The date refusal is a LIST, so it cannot go through drawerError's
  // single string. It is also written in place rather than through
  // renderAll() for a reason drawerError's own comment implies but this
  // case makes sharp: a repaint rebuilds the date inputs from the SAVED
  // trip row, so the operator would watch the dates they just typed snap
  // back to the old ones at the very moment they were told why they
  // cannot have them --- reading as "it saved and then undid itself"
  // rather than "it refused."
  function drawerDateRefusal(host) {
    var box = el("div", "tdl-delete-error tdl-date-refusal");
    box.hidden = true;
    host.appendChild(box);
    return box;
  }

  function showDateRefusal(box, blocking) {
    box.textContent = "";
    if (!blocking || !blocking.length) { box.hidden = true; return; }
    box.appendChild(el("p", "", "The trip dates cannot be shortened yet."));
    box.appendChild(el("p", "", "These days contain work:"));
    var list = el("ul", "tdl-date-refusal-list");
    blocking.forEach(function (day) {
      list.appendChild(el("li", "",
        longDate(day.date) + " \u2014 " + holdsPhrase(dayHolds(day))));
    });
    box.appendChild(list);
    box.appendChild(el("p", "",
      "Move or remove that content, then try again."));
    box.hidden = false;
  }

  // ── editor open/close ────────────────────────────────────────────────
  //
  // Each opener re-checks dayFormDirtyBlocks() for the same reason
  // setTab() does: opening a drawer repaints, and an unsaved day-inspector
  // edit would be discarded silently.

  function openTripEditor(mode) {
    if (dayFormDirtyBlocks()) return;
    if (mode === "edit" && !st.trip) return;
    st.tripEditor = { mode: mode, error: "" };
    renderAll();
  }

  function closeTripEditor() { st.tripEditor = null; renderAll(); }

  function openRegionEditor(mode, regionId) {
    if (dayFormDirtyBlocks()) return;
    if (!st.trip) return;
    st.regionEditor = { mode: mode, regionId: regionId || null, error: "" };
    renderAll();
  }

  function closeRegionEditor() { st.regionEditor = null; renderAll(); }

  // opts: {stopId, regionId, insert}
  function openStopEditor(mode, opts) {
    if (dayFormDirtyBlocks()) return;
    if (!st.trip) return;
    opts = opts || {};
    st.insertContext = opts.insert || null;
    st.stopEditor = {
      mode: mode,
      stopId: opts.stopId || null,
      regionId: opts.regionId || null,
      error: "",
    };
    renderAll();
  }

  // Closing the stop editor drops the insert context with it: an insert
  // position is a property of the pending create, not of the trip.
  function closeStopEditor() {
    st.stopEditor = null;
    st.insertContext = null;
    renderAll();
  }

  // ── trip create / edit ───────────────────────────────────────────────

  function renderTripEditorDrawer() {
    var ed = st.tripEditor;
    var creating = ed.mode === "create";
    var trip = creating ? null : st.trip;
    if (!creating && !trip) { st.tripEditor = null; return el("div"); }

    var sh = drawerShell(creating ? "New trip" : "Edit trip",
      creating ? "Create a trip" : (trip.title || "Untitled trip"),
      closeTripEditor, "tdl-edit-drawer tdl-trip-editor");

    var vTitle = textInput(trip ? trip.title : "", "e.g. Portugal, spring 2019");
    var vStart = dateInput(trip ? trip.start_date : "");
    var vEnd = dateInput(trip ? trip.end_date : "");
    var vSummary = areaInput(trip ? trip.summary : "",
      "What this trip was, in a sentence or two…");
    sh.body.appendChild(field("Title", vTitle));
    sh.body.appendChild(field("Start date", vStart));
    sh.body.appendChild(field("End date", vEnd));
    attachDateNote(sh.body, vStart, vEnd, null, null, "trip");
    sh.body.appendChild(field("Summary", vSummary));
    sh.body.appendChild(el("p", "tdl-muted",
      "Saving trip dates regenerates the day calendar. If a day card " +
      "cannot be generated the save still succeeds and the reason is " +
      "shown as a warning banner — it is not silently dropped."));

    var errEl = drawerError(sh.body, ed.error);
    var refusalEl = drawerDateRefusal(sh.body);

    var saveBtn = btn("tdl-btn tdl-btn-primary",
      creating ? "✓ Create trip" : "✓ Save trip", function () {
        var title = (vTitle.value || "").trim();
        if (!title) {
          errEl.textContent = "A trip needs a title.";
          errEl.hidden = false;
          return;
        }
        saveBtn.disabled = true;
        var summary = (vSummary.value || "").trim();
        // A failed save must leave the drawer open with what the operator
        // typed still in it; only a vanished drawer falls back to st.error.
        function fail(e) {
          saveBtn.disabled = false;
          if (st.tripEditor) st.tripEditor.error = "Save failed: " + e.message;
          else st.error = e.message;
          renderAll();
        }
        if (creating) {
          api("/api/trips", { method: "POST", body: {
            person_id: st.personId,
            title: title,
            start_date: vStart.value || null,
            end_date: vEnd.value || null,
            summary: summary || null,
          } }).then(function (out) {
            applyTripWarnings(out);
            notifyTripUpdated(out.trip_id, "trip_created");
            st.tripEditor = null;
            st.error = "";
            // noAutoSelect: the list refresh must not pick trips[0] out
            // from under the trip that was just created.
            return loadTrips({ noAutoSelect: true }).then(function () {
              return selectTrip(out.trip_id);
            });
          }).catch(fail);
        } else {
          // Phase A correction 2 --- the shrinking-date rule, checked
          // BEFORE the save rather than cleaned up after it. Refusing
          // after the dates have already moved would mean a trip header
          // reading July 14-18 above a visible July 20 card, which is
          // exactly the confusion Chris named.
          var leaving = daysLeavingWindow(vStart.value, vEnd.value);
          var blocking = leaving.filter(function (d) {
            return !dayIsEmpty(d);
          });
          if (blocking.length) {
            saveBtn.disabled = false;
            showDateRefusal(refusalEl, blocking);
            return;
          }
          showDateRefusal(refusalEl, []);
          // Only ask for the removal when this save is what takes cards
          // out of the window.
          var shrinking = leaving.length > 0;
          api("/api/trips/" + encodeURIComponent(trip.id), {
            method: "PATCH", body: {
              title: title,
              start_date: vStart.value || null,
              clear_start_date: !vStart.value,
              end_date: vEnd.value || null,
              clear_end_date: !vEnd.value,
              summary: summary || null,
              clear_summary: !summary,
            } }).then(function (out) {
            applyTripWarnings(out);
            notifyTripUpdated(trip.id, "trip_saved");
            st.tripEditor = null;
            st.error = "";
            return refreshTripsPreservingSelection(trip.id)
              .then(function () {
                // After the trip row is re-pointed and before the bundle
                // reload, so the calendar that gets drawn is the one the
                // removal already ran against.
                return shrinking ? dropEmptyOutOfRangeDays(trip.id) : null;
              })
              .then(refreshTripBundle);
          }).catch(fail);
        }
      });
    sh.foot.appendChild(saveBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeTripEditor));
    return sh.wrap;
  }

  // ── region create / edit ─────────────────────────────────────────────

  function renderRegionEditorDrawer() {
    var ed = st.regionEditor;
    var creating = ed.mode === "create";
    var region = creating ? null : findRegion(ed.regionId);
    if (!creating && !region) { st.regionEditor = null; return el("div"); }

    var sh = drawerShell(creating ? "New region" : "Edit region",
      creating ? "Add a region" : regionLabel(region),
      closeRegionEditor, "tdl-edit-drawer tdl-region-editor");

    var vTitle = textInput(region ? region.title : "", "e.g. Algarve");
    var vArea = textInput(region ? region.country_or_area : "",
      "Country or area");
    var vStart = dateInput(region ? region.start_date : "");
    var vEnd = dateInput(region ? region.end_date : "");
    var vBase = textInput(region ? region.base_address : "",
      "Where you stayed in this region");
    var vSummary = areaInput(region ? region.summary : "",
      "What this leg of the trip was…");
    sh.body.appendChild(field("Region title", vTitle));
    sh.body.appendChild(field("Country / area", vArea));
    sh.body.appendChild(field("Start date", vStart));
    sh.body.appendChild(field("End date", vEnd));
    attachDateNote(sh.body, vStart, vEnd,
      st.trip.start_date, st.trip.end_date, "trip");
    sh.body.appendChild(field("Base", vBase));
    sh.body.appendChild(field("Summary", vSummary));

    var errEl = drawerError(sh.body, ed.error);

    var saveBtn = btn("tdl-btn tdl-btn-primary",
      creating ? "✓ Add region" : "✓ Save region", function () {
        var title = (vTitle.value || "").trim();
        if (!title) {
          errEl.textContent = "A region needs a title.";
          errEl.hidden = false;
          return;
        }
        saveBtn.disabled = true;
        var area = (vArea.value || "").trim();
        var base = (vBase.value || "").trim();
        var summary = (vSummary.value || "").trim();
        function fail(e) {
          saveBtn.disabled = false;
          if (st.regionEditor) st.regionEditor.error = "Save failed: " + e.message;
          else st.error = e.message;
          renderAll();
        }
        function done() {
          notifyTripUpdated(st.trip.id, "region_saved");
          st.regionEditor = null;
          st.error = "";
          return refreshTripBundle();
        }
        if (creating) {
          api("/api/trips/" + encodeURIComponent(st.trip.id) + "/regions", {
            method: "POST", body: {
              title: title,
              country_or_area: area || null,
              start_date: vStart.value || null,
              end_date: vEnd.value || null,
              base_address: base || null,
              summary: summary || null,
            } }).then(done).catch(fail);
        } else {
          api("/api/trips/regions/" + encodeURIComponent(region.id), {
            method: "PATCH", body: {
              title: title,
              country_or_area: area || null,
              clear_country_or_area: !area,
              start_date: vStart.value || null,
              clear_start_date: !vStart.value,
              end_date: vEnd.value || null,
              clear_end_date: !vEnd.value,
              base_address: base || null,
              clear_base_address: !base,
              summary: summary || null,
              clear_summary: !summary,
            } }).then(done).catch(fail);
        }
      });
    sh.foot.appendChild(saveBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeRegionEditor));
    return sh.wrap;
  }

  // ── stop create / edit (incl. insert-at-position) ────────────────────

  function stopTypeLabel(t) {
    return String(t || "").replace(/_/g, " ");
  }

  function renderStopEditorDrawer() {
    var ed = st.stopEditor;
    var creating = ed.mode === "create";
    var loc = creating ? null : locateStop(ed.stopId);
    if (!creating && !loc) { st.stopEditor = null; return el("div"); }
    var stop = loc ? loc.node : null;
    var regions = (st.tree && st.tree.regions) || [];
    if (!regions.length) { st.stopEditor = null; return el("div"); }
    var startRegionId = creating
      ? (ed.regionId || regions[0].id)
      : loc.region.id;
    var ctx = st.insertContext;

    var sh = drawerShell(creating ? "New stop" : "Edit stop",
      creating ? "Add a stop" : stopLabel(stop),
      closeStopEditor, "tdl-edit-drawer tdl-stop-editor");

    // The insert position is shown, not implied. Production put this in a
    // status line that the next status message erased.
    if (creating && ctx) {
      var sib = ctx.sibling_stop_id ? findStop(ctx.sibling_stop_id) : null;
      sh.body.appendChild(el("div", "tdl-insert-hint",
        "Inserting " + (ctx.where === "before" ? "before" : "after") + " " +
        (sib ? stopLabel(sib) : "the selected stop") +
        (ctx.parent_stop_id ? " (as a child stop)" : "")));
    }

    var vName = textInput(stop ? stop.location_name : "", "e.g. Lagos");
    var vType = selectInput(STOP_TYPES.map(function (t) {
      return [t, stopTypeLabel(t)];
    }), (stop && stop.stop_type) || "sight");
    var vStart = dateInput(stop ? (stop.date_start || stop.start_date) : "");
    var vEnd = dateInput(stop ? (stop.date_end || stop.end_date) : "");
    var vNotes = areaInput(stop ? stop.notes : "",
      "Anything worth remembering about this stop…");
    var vRegion = selectInput(regions.map(function (r) {
      return [r.id, regionLabel(r)];
    }), startRegionId);
    var vParent = el("select");

    sh.body.appendChild(field("Stop name", vName));
    sh.body.appendChild(field("Type", vType));
    sh.body.appendChild(field("Start date", vStart));
    sh.body.appendChild(field("End date", vEnd));
    var boundRegion = findRegion(startRegionId);
    attachDateNote(sh.body, vStart, vEnd,
      (boundRegion && boundRegion.start_date) || st.trip.start_date,
      (boundRegion && boundRegion.end_date) || st.trip.end_date,
      (boundRegion && boundRegion.start_date) ? "region" : "trip");
    sh.body.appendChild(field("Region", vRegion));
    sh.body.appendChild(field("Parent stop", vParent,
      "Leave as “Top level” unless this stop happened inside another."));
    sh.body.appendChild(field("Notes", vNotes));

    // A stop can never be reparented into its own subtree — that would
    // detach the branch from the tree entirely. Production computed this
    // with subtreeIds(); so does this.
    var forbidden = {};
    if (stop) subtreeIds(stop).forEach(function (id) { forbidden[id] = true; });

    function fillParentOptions(regionId, preferred) {
      vParent.innerHTML = "";
      var top = el("option", "", "Top level");
      top.value = "";
      vParent.appendChild(top);
      allStops(st.tree).forEach(function (row) {
        if (row.region_id !== regionId) return;
        if (forbidden[row.id]) return;
        var opt = el("option", "",
          new Array((row.depth || 0) + 1).join("— ") + stopLabel(row.node));
        opt.value = row.id;
        vParent.appendChild(opt);
      });
      vParent.value = preferred || "";
      if (vParent.value !== (preferred || "")) vParent.value = "";
    }
    fillParentOptions(startRegionId,
      creating ? ((ctx && ctx.parent_stop_id) || "")
               : ((loc.parent && loc.parent.id) || ""));
    // Property assignment: re-opening the drawer for a different stop can
    // never stack a handler closed over the previous stop's forbidden set.
    vRegion.onchange = function () { fillParentOptions(vRegion.value, ""); };

    var errEl = drawerError(sh.body, ed.error);

    var saveBtn = btn("tdl-btn tdl-btn-primary",
      creating ? "✓ Add stop" : "✓ Save stop", function () {
        var name = (vName.value || "").trim();
        if (!name) {
          errEl.textContent = "A stop needs a name.";
          errEl.hidden = false;
          return;
        }
        saveBtn.disabled = true;
        var notes = (vNotes.value || "").trim();
        var regionId = vRegion.value;
        var parentId = vParent.value || null;
        function fail(e) {
          saveBtn.disabled = false;
          if (st.stopEditor) st.stopEditor.error = "Save failed: " + e.message;
          else st.error = e.message;
          renderAll();
        }
        function done() {
          notifyTripUpdated(st.trip.id, "stop_saved");
          st.stopEditor = null;
          st.insertContext = null;
          st.error = "";
          return refreshTripBundle();
        }
        function moveBody(extra) {
          var b = { region_id: regionId, parent_trip_stop_id: parentId };
          if (extra) {
            b.before_stop_id = extra.where === "before"
              ? extra.sibling_stop_id : null;
            b.after_stop_id = extra.where === "after"
              ? extra.sibling_stop_id : null;
          }
          return b;
        }
        if (creating) {
          // An insert position is only meaningful while the stop is still
          // a sibling of the row it was anchored to. If the operator
          // changed the region or the parent in this drawer, the anchor no
          // longer applies and the insert is dropped rather than fighting
          // the choice they just made.
          var useCtx = (ctx && regionId === ctx.region_id &&
                        parentId === (ctx.parent_stop_id || null)) ? ctx : null;
          api("/api/trips/" + encodeURIComponent(st.trip.id) + "/regions/" +
              encodeURIComponent(regionId) + "/stops", {
            method: "POST", body: {
              location_name: name,
              stop_type: vType.value || null,
              date_start: vStart.value || null,
              date_end: vEnd.value || null,
              notes: notes || null,
              parent_trip_stop_id: parentId,
            } }).then(function (out) {
            if (!useCtx && !parentId) return done();
            return api("/api/trips/" + encodeURIComponent(st.trip.id) +
                "/stops/" + encodeURIComponent(out.stop_id) + "/move", {
              method: "POST", body: moveBody(useCtx),
            }).then(done);
          }).catch(fail);
        } else {
          var movedRegion = regionId !== loc.region.id;
          var movedParent = parentId !== ((loc.parent && loc.parent.id) || null);
          api("/api/trips/stops/" + encodeURIComponent(stop.id), {
            method: "PATCH", body: {
              location_name: name,
              stop_type: vType.value || null,
              date_start: vStart.value || null,
              clear_start_date: !vStart.value,
              date_end: vEnd.value || null,
              clear_end_date: !vEnd.value,
              notes: notes || null,
              clear_notes: !notes,
            } }).then(function () {
            if (!movedRegion && !movedParent) return done();
            return api("/api/trips/" + encodeURIComponent(st.trip.id) +
                "/stops/" + encodeURIComponent(stop.id) + "/move", {
              method: "POST", body: moveBody(null),
            }).then(done);
          }).catch(fail);
        }
      });
    sh.foot.appendChild(saveBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeStopEditor));
    return sh.wrap;
  }

  // ── region / stop delete review ──────────────────────────────────────
  //
  // Production gates both of these with window.confirm(). This does not,
  // for the Phase 3A reason: a native dialog states a consequence the
  // operator cannot check against the data, and one click of OK is not a
  // gate. The review names the row and counts what goes with it.

  function openRouteDelete(kind, id) {
    if (dayFormDirtyBlocks()) return;
    if (!st.trip) return;
    var title = "";
    var count = 0;
    if (kind === "region") {
      var r = findRegion(id);
      if (!r) return;
      title = regionLabel(r);
      count = regionStopCount(r);
    } else {
      var s = findStop(id);
      if (!s) return;
      title = stopLabel(s);
      count = ((s.children || []).length);
    }
    st.routeDelete = {
      kind: kind, id: id, title: title, count: count,
      stage: "review", serverMessage: "", error: "",
    };
    renderAll();
  }

  function closeRouteDelete() { st.routeDelete = null; renderAll(); }

  function afterRouteDeleted(kind, id) {
    // A selection or an editor pointing at a row that no longer exists is
    // a dangling handle; clear both before the tree reloads under them.
    if (st.routeSel && (st.routeSel.id === id || st.routeSel.regionId === id)) {
      st.routeSel = null;
    }
    if (kind === "region" && st.regionEditor &&
        st.regionEditor.regionId === id) st.regionEditor = null;
    if (kind === "stop" && st.stopEditor &&
        st.stopEditor.stopId === id) st.stopEditor = null;
    if (st.insertContext &&
        (st.insertContext.region_id === id ||
         st.insertContext.parent_stop_id === id ||
         st.insertContext.sibling_stop_id === id)) st.insertContext = null;
    st.routeDelete = null;
    st.error = "";
    // Phase 3D — a move in flight against a row that is being deleted is
    // a dangling handle of the same kind; drop it with the rest.
    st.routeBusy = null;
    st.routeError = "";
    notifyTripUpdated(st.trip.id, kind + "_deleted");
    return refreshTripBundle();
  }

  // Stage 1 — the UNFORCED region delete. An empty region is simply gone.
  // A non-empty one comes back 409 RegionNotEmptyError and opens stage 2.
  //
  // Production sends this same unforced call after its confirm() and then
  // stops: it neither passes force nor handles the 409, so an operator who
  // has already agreed to the cascade watches nothing happen. Splitting it
  // into two stages fixes that AND makes the backend, not a possibly stale
  // client-side tree, the authority on what is actually inside.
  function deleteRegionUnforced() {
    var rd = st.routeDelete;
    if (!rd) return Promise.resolve();
    return api("/api/trips/regions/" + encodeURIComponent(rd.id),
               { method: "DELETE" })
      .then(function () { return afterRouteDeleted("region", rd.id); })
      .catch(function (e) {
        if (e && e.status === 409 && st.routeDelete) {
          st.routeDelete.stage = "force";
          st.routeDelete.serverMessage = e.message;
          st.routeDelete.error = "";
          renderAll();
          return;
        }
        if (st.routeDelete) st.routeDelete.error = "Delete failed: " + e.message;
        renderAll();
      });
  }

  // Stage 2 — reachable only from the stage-2 panel, which only a real
  // backend 409 can open.
  function forceDeleteRegion() {
    var rd = st.routeDelete;
    if (!rd) return Promise.resolve();
    return api("/api/trips/regions/" + encodeURIComponent(rd.id) +
               "?force=true", { method: "DELETE" })
      .then(function () { return afterRouteDeleted("region", rd.id); })
      .catch(function (e) {
        if (st.routeDelete) st.routeDelete.error = "Delete failed: " + e.message;
        renderAll();
      });
  }

  // Stops are single-stage: the backend never refuses one. Child stops are
  // PROMOTED to top level in the same region, not destroyed — the review
  // copy says so, because "delete" reads as a cascade and here it is not.
  function deleteStopReviewed() {
    var rd = st.routeDelete;
    if (!rd) return Promise.resolve();
    return api("/api/trips/stops/" + encodeURIComponent(rd.id),
               { method: "DELETE" })
      .then(function () { return afterRouteDeleted("stop", rd.id); })
      .catch(function (e) {
        if (st.routeDelete) st.routeDelete.error = "Delete failed: " + e.message;
        renderAll();
      });
  }

  function renderRouteDeleteReview() {
    var rd = st.routeDelete;
    var isRegion = rd.kind === "region";
    var sh = drawerShell(isRegion ? "Delete region" : "Delete stop",
      rd.title, closeRouteDelete, "tdl-delete-drawer tdl-route-delete");

    if (isRegion && rd.stage === "force") {
      sh.body.appendChild(el("p", "tdl-delete-warn",
        "The server refused the plain delete because this region is not " +
        "empty. Deleting it now removes the region AND every stop inside " +
        "it, unrecoverably."));
      sh.body.appendChild(el("div", "tdl-section-label", "Server said"));
      sh.body.appendChild(el("p", "tdl-muted", rd.serverMessage ||
        "This region still has stops."));
      sh.body.appendChild(el("p", "", "Stops in this region, by the tree " +
        "loaded here: " + rd.count + "."));
    } else if (isRegion) {
      sh.body.appendChild(el("p", "tdl-delete-warn",
        rd.count
          ? ("This region holds " + rd.count + " stop" +
             (rd.count === 1 ? "" : "s") + ". The delete is tried WITHOUT " +
             "force first — if the server refuses, you will be shown " +
             "exactly what it says before anything is destroyed.")
          : "This region has no stops. Deleting it removes the region only."));
    } else {
      sh.body.appendChild(el("p", "tdl-delete-warn",
        rd.count
          ? ("This stop has " + rd.count + " child stop" +
             (rd.count === 1 ? "" : "s") + ". They are NOT deleted — " +
             "they move up to become top-level stops in the same region.")
          : "This stop will be removed from the route."));
      sh.body.appendChild(el("p", "tdl-muted",
        "Day cards, photos, notes and sources are not deleted by this. " +
        "Anything attached to this stop simply loses the stop link."));
    }
    sh.body.appendChild(el("p", "tdl-muted", "Id: " + rd.id));
    var errEl = drawerError(sh.body, rd.error);
    if (rd.error) errEl.hidden = false;

    var label, run;
    if (!isRegion) {
      label = "Delete stop";
      run = deleteStopReviewed;
    } else if (rd.stage === "force") {
      label = "Delete region and its " + rd.count + " stop" +
        (rd.count === 1 ? "" : "s");
      run = forceDeleteRegion;
    } else {
      label = "Delete region";
      run = deleteRegionUnforced;
    }
    var goBtn = btn("tdl-btn tdl-btn-danger", label, function () {
      if (goBtn.disabled) return;
      goBtn.disabled = true;
      run();
    });
    sh.foot.appendChild(goBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeRouteDelete));
    return sh.wrap;
  }

  // ── route order (WO-TRAVEL-DOC-UNIFY-01 Phase 3D) ────────────────────
  //
  // See decisions 1-3 in the header block. The short version: a stop move
  // names its stop and its neighbour and lets the backend re-derive the
  // sibling group; a region move has to send the whole permutation
  // because /regions/reorder is the only endpoint, so its staleness is
  // surfaced and reloaded rather than swallowed.

  function siblingsOf(regionId, parentStopId) {
    if (parentStopId) {
      var p = findStop(parentStopId);
      return (p && p.children) || [];
    }
    var r = findRegion(regionId);
    return (r && r.stops) || [];
  }

  function routeMoveFailed(prefix, e) {
    st.routeBusy = null;
    st.routeError = prefix + ": " + ((e && e.message) || "unknown error");
    // Reload before repainting. Leaving the board showing an order the
    // backend just refused would make the operator's next click argue
    // with a tree that only exists on screen.
    return refreshTripBundle().then(renderAll, renderAll);
  }

  function routeMoveDone(kind, id) {
    st.routeBusy = null;
    st.routeError = "";
    notifyTripUpdated(st.trip.id, kind + "_reordered");
    return refreshTripBundle().then(function () { renderAll(); });
  }

  function moveRegionRelative(regionId, dir) {
    if (!st.trip || st.routeBusy) return Promise.resolve();
    if (dayFormDirtyBlocks()) return Promise.resolve();
    var ids = ((st.tree && st.tree.regions) || []).map(function (r) {
      return r.id;
    });
    var i = ids.indexOf(regionId);
    var j = i + dir;
    if (i < 0 || j < 0 || j >= ids.length) return Promise.resolve();
    ids.splice(i, 1);
    ids.splice(j, 0, regionId);
    st.routeBusy = regionId;
    st.routeError = "";
    renderAll();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/regions/reorder", {
      method: "POST",
      // `api()` owns the encoding — it stringifies `opts.body` itself, ahead
      // of its FormData branch. Pre-stringifying here double-encodes the
      // request into a JSON *string* and the backend answers 422.
      body: { ordered_ids: ids },
    }).then(function () {
      return routeMoveDone("region", regionId);
    }, function (e) {
      return routeMoveFailed("Could not move that region", e);
    });
  }

  function moveStopRelative(stopId, dir) {
    if (!st.trip || st.routeBusy) return Promise.resolve();
    if (dayFormDirtyBlocks()) return Promise.resolve();
    var loc = locateStop(stopId);
    if (!loc) return Promise.resolve();
    var parentId = loc.parent ? loc.parent.id : null;
    var ids = siblingsOf(loc.region.id, parentId).map(function (s) {
      return s.id;
    });
    var i = ids.indexOf(stopId);
    var j = i + dir;
    if (i < 0 || j < 0 || j >= ids.length) return Promise.resolve();
    // The NEIGHBOUR is the whole request. A substop moves among its own
    // siblings only, so region_id and parent_trip_stop_id are echoed back
    // unchanged — a reorder must never quietly reparent, which is the one
    // way an arrow could destroy a branch the operator was not shown.
    var anchor = ids[j];
    st.routeBusy = stopId;
    st.routeError = "";
    renderAll();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) +
               "/stops/" + encodeURIComponent(stopId) + "/move", {
      method: "POST",
      // Raw object, never a pre-stringified one — see moveRegionRelative.
      body: {
        region_id: loc.region.id,
        parent_trip_stop_id: parentId,
        before_stop_id: dir < 0 ? anchor : null,
        after_stop_id: dir > 0 ? anchor : null,
      },
    }).then(function () {
      return routeMoveDone("stop", stopId);
    }, function (e) {
      return routeMoveFailed("Could not move that stop", e);
    });
  }

  // ── route selection + evidence badges (Phase 3D) ─────────────────────

  function routeSelect(kind, id, regionId) {
    if (dayFormDirtyBlocks()) return;
    st.routeSel = { kind: kind, id: id, regionId: regionId };
    renderAll();
  }

  function isRouteSelected(kind, id) {
    return !!(st.routeSel && st.routeSel.kind === kind && st.routeSel.id === id);
  }

  // Scope filter, same shape dayScopedRows() uses: a region owns the rows
  // pinned to it that are not pinned to one of its stops.
  function routeScopedRows(rows, kind, id) {
    if (kind === "stop") {
      return (rows || []).filter(function (r) { return r.trip_stop_id === id; });
    }
    return (rows || []).filter(function (r) {
      return r.trip_region_id === id && !r.trip_stop_id;
    });
  }

  // Production shows these on its tiles and they are how an operator
  // tells an empty stop from one that already carries material. Free to
  // port: st.notes / st.sources / st.photoLinks are already loaded and
  // already carry trip_region_id / trip_stop_id, so no row costs a fetch.
  function routeBadgeText(kind, id) {
    var n = routeScopedRows(st.notes, kind, id).length;
    var d = routeScopedRows(st.sources, kind, id).length;
    var p = routeScopedRows(st.photoLinks, kind, id).length;
    var parts = [];
    if (n) parts.push(n + " note" + (n > 1 ? "s" : ""));
    if (d) parts.push(d + " doc" + (d > 1 ? "s" : ""));
    if (p) parts.push(p + " photo" + (p > 1 ? "s" : ""));
    return parts.join(" · ");
  }

  // Disabled at the ends rather than silently no-oping, and disabled
  // everywhere while any move is in flight.
  function moveBtn(label, title, enabled, onClick) {
    var b = btn("tdl-btn tdl-btn-small tdl-route-move", label, onClick);
    b.title = title;
    if (!enabled || st.routeBusy) b.disabled = true;
    return b;
  }

  // The row body is the selection control. Selecting a row is what makes
  // the rest of the workspace agree with the board — the intake drawer
  // seeds its scope from st.routeSel — so this is also what revives the
  // region branch of Phase 3C's defaultScopeKey().
  function routePickCell(kind, id, regionId, title) {
    var cell = btn("tdl-route-row-main tdl-route-row-pick", "", function () {
      routeSelect(kind, id, regionId);
    });
    cell.title = title;
    if (isRouteSelected(kind, id)) cell.setAttribute("aria-current", "true");
    return cell;
  }

  // ── the route board ──────────────────────────────────────────────────

  function renderStopRow(s, region, depth, out, idx, total) {
    var row = el("div", "tdl-route-row tdl-route-row-stop");
    if (isRouteSelected("stop", s.id)) row.className += " tdl-route-row-sel";
    // Depth is expressed as indentation rather than nested containers so
    // every row keeps the same action bar geometry at any depth.
    row.style.paddingLeft = (18 + depth * 18) + "px";
    var mainCell = routePickCell("stop", s.id, region.id, "Select this stop");
    mainCell.appendChild(el("strong", "", stopLabel(s)));
    var meta = [];
    if (s.stop_type) meta.push(stopTypeLabel(s.stop_type));
    var ds = s.date_start || s.start_date;
    var de = s.date_end || s.end_date;
    if (ds || de) meta.push((ds || "?") + " → " + (de || "?"));
    if (meta.length) mainCell.appendChild(el("span", "tdl-muted", meta.join(" · ")));
    var badge = routeBadgeText("stop", s.id);
    if (badge) mainCell.appendChild(el("span", "tdl-route-ind", badge));
    row.appendChild(mainCell);

    var acts = el("div", "tdl-route-row-actions");
    acts.appendChild(moveBtn("↑", "Move up among its siblings", idx > 0,
      function () { return moveStopRelative(s.id, -1); }));
    acts.appendChild(moveBtn("↓", "Move down among its siblings",
      idx < total - 1,
      function () { return moveStopRelative(s.id, 1); }));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "+ Before", function () {
      openStopEditor("create", {
        regionId: region.id,
        insert: {
          region_id: region.id,
          parent_stop_id: s.parent_trip_stop_id || null,
          sibling_stop_id: s.id,
          where: "before",
        },
      });
    }));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "+ After", function () {
      openStopEditor("create", {
        regionId: region.id,
        insert: {
          region_id: region.id,
          parent_stop_id: s.parent_trip_stop_id || null,
          sibling_stop_id: s.id,
          where: "after",
        },
      });
    }));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Edit", function () {
      openStopEditor("edit", { stopId: s.id, regionId: region.id });
    }));
    acts.appendChild(btn("tdl-btn tdl-btn-small tdl-btn-danger", "Delete",
      function () { openRouteDelete("stop", s.id); }));
    row.appendChild(acts);
    out.appendChild(row);
    var kids = s.children || [];
    kids.forEach(function (c, i) {
      renderStopRow(c, region, depth + 1, out, i, kids.length);
    });
  }

  function renderRegionRow(r, out, idx, total) {
    var row = el("div", "tdl-route-row tdl-route-row-region");
    if (isRouteSelected("region", r.id)) row.className += " tdl-route-row-sel";
    var mainCell = routePickCell("region", r.id, r.id, "Select this region");
    mainCell.appendChild(el("strong", "", regionLabel(r)));
    var meta = [];
    if (r.country_or_area) meta.push(r.country_or_area);
    if (r.start_date || r.end_date) {
      meta.push((r.start_date || "?") + " → " + (r.end_date || "?"));
    }
    meta.push(regionStopCount(r) + " stops");
    mainCell.appendChild(el("span", "tdl-muted", meta.join(" · ")));
    var badge = routeBadgeText("region", r.id);
    if (badge) mainCell.appendChild(el("span", "tdl-route-ind", badge));
    row.appendChild(mainCell);

    var acts = el("div", "tdl-route-row-actions");
    acts.appendChild(moveBtn("↑", "Move region up", idx > 0,
      function () { return moveRegionRelative(r.id, -1); }));
    acts.appendChild(moveBtn("↓", "Move region down", idx < total - 1,
      function () { return moveRegionRelative(r.id, 1); }));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "+ Stop", function () {
      openStopEditor("create", { regionId: r.id });
    }));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Edit", function () {
      openRegionEditor("edit", r.id);
    }));
    acts.appendChild(btn("tdl-btn tdl-btn-small tdl-btn-danger", "Delete",
      function () { openRouteDelete("region", r.id); }));
    row.appendChild(acts);
    out.appendChild(row);
    var stops = r.stops || [];
    stops.forEach(function (s, i) {
      renderStopRow(s, r, 1, out, i, stops.length);
    });
  }

  function renderTripTab() {
    var wrap = el("div");
    var trip = st.trip;
    var regions = (st.tree && st.tree.regions) || [];

    var head = el("div", "tdl-head-row");
    head.appendChild(el("div", "tdl-title-icon", "✐"));
    var ht = el("div");
    ht.appendChild(el("h1", "", trip.title || "Untitled trip"));
    ht.appendChild(el("p", "tdl-muted",
      (trip.start_date || "?") + " → " + (trip.end_date || "?") +
      " · " + regions.length + " region" +
      (regions.length === 1 ? "" : "s") +
      " · " + countStops() + " stops"));
    if (trip.summary) ht.appendChild(el("p", "", trip.summary));
    head.appendChild(ht);
    wrap.appendChild(head);

    var bar = el("div", "tdl-toolbar");
    bar.appendChild(btn("tdl-btn", "✎ Edit trip", function () {
      openTripEditor("edit");
    }));
    bar.appendChild(btn("tdl-btn", "+ Region", function () {
      openRegionEditor("create", null);
    }));
    var addStop = btn("tdl-btn", "+ Stop", function () {
      openStopEditor("create", { regionId: regions.length ? regions[0].id : null });
    });
    // A stop must live in a region, so this is disabled rather than
    // hidden: an operator who wants a stop needs to be told what is
    // missing, not shown a control that quietly is not there.
    if (!regions.length) {
      addStop.disabled = true;
      addStop.title = "Add a region first — every stop lives in one.";
    }
    bar.appendChild(addStop);
    wrap.appendChild(bar);

    // Phase 3D — a refused move is reported HERE, beside the rows it is
    // about, and never in a native dialog. It is dismissible because the
    // tree has already been reloaded underneath it: the message describes
    // an attempt, not the current state.
    if (st.routeError) {
      var errBox = el("div", "tdl-route-error");
      errBox.appendChild(el("span", "", st.routeError));
      errBox.appendChild(btn("tdl-btn tdl-btn-small", "Dismiss", function () {
        st.routeError = "";
        renderAll();
      }));
      wrap.appendChild(errBox);
    }

    if (!regions.length) {
      wrap.appendChild(el("div", "tdl-empty",
        "No regions yet. Add a region to start building the route."));
    } else {
      var board = el("div", "tdl-route-board");
      regions.forEach(function (r, i) {
        renderRegionRow(r, board, i, regions.length);
      });
      wrap.appendChild(board);
    }

    // WO-TRAVEL-DOC-UNIFY-01 Phase 4: an "Older Travel Documenter (being
    // retired)" foot-note used to hang off the bottom of this board,
    // deep-linking to the old standalone page. The fallback is retired,
    // so the foot-note went with it.
    return wrap;
  }

  // ── Trip Plan (mockup2 — THE key screen) ─────────────────────────────

  function countStops() {
    var n = 0;
    ((st.tree && st.tree.regions) || []).forEach(function (r) {
      (function walk(stops) {
        (stops || []).forEach(function (s) { n += 1; walk(s.children); });
      })(r.stops);
    });
    return n;
  }

  function renderPlan() {
    var wrap = el("div");

    var head = el("div", "tdl-head-row");
    head.appendChild(el("div", "tdl-title-icon", "▦"));
    var ht = el("div");
    ht.appendChild(el("h1", "", "Trip Calendar"));
    ht.appendChild(el("p", "tdl-muted",
      "Day cards are created from your trip dates automatically. " +
      "Click a day to open its workspace: talk with Lori, write what " +
      "happened, attach photos, notes, meals, places and sources."));
    head.appendChild(ht);
    wrap.appendChild(head);
    wrap.appendChild(renderTripLiveBar());

    // 2026-07-15 Track C: surface any /days or /days/reconcile-preview
    // load errors instead of silently rendering the empty state — the
    // operator needs to see a real backend failure (missing migration,
    // 500) rather than "you must have forgotten to press Generate."
    if (st.loadWarnings && st.loadWarnings.length) {
      var warnBox = el("div", "tdl-error tdl-load-warnings");
      warnBox.appendChild(el("strong", "",
        "Some trip data could not be loaded:"));
      var ul = el("ul", "");
      st.loadWarnings.forEach(function (line) {
        ul.appendChild(el("li", "", line));
      });
      warnBox.appendChild(ul);
      wrap.appendChild(warnBox);
    }
    // Auto-generation / auto-reconcile warning from the last save call
    // (create_trip or patch_trip attached this to the response body).
    if (st.daysWarning) {
      var dwBox = el("div", "tdl-error tdl-days-warning");
      dwBox.appendChild(el("strong", "", "Day cards warning: "));
      dwBox.appendChild(document.createTextNode(st.daysWarning));
      wrap.appendChild(dwBox);
    }
    // 2026-07-28 (Phase A correction 2) — what the last trip-date save
    // removed. Neutral, not amber: this reports something that worked.
    // A card that was on the screen a moment ago and is gone now, with
    // nothing on screen admitting it, is the silent deletion this
    // doctrine exists to prevent — and "without asking" was never
    // "without saying."
    if (st.daysNotice) {
      var dnBox = el("div", "tdl-reconcile-banner tdl-reconcile-notice");
      dnBox.appendChild(el("span", "", st.daysNotice));
      dnBox.appendChild(btn("tdl-btn tdl-btn-small", "Dismiss", function () {
        st.daysNotice = "";
        renderAll();
      }));
      wrap.appendChild(dnBox);
    }
    // 2026-07-23 (Bucket B) — counts_warning banner. When the /days
    // endpoint could load the day rows but the evidence-counts query
    // failed, every card renders zero counts. Without this banner,
    // a locked or damaged counts query looks IDENTICAL to legitimate
    // absence of evidence. Amber styling matches the other partial-
    // failure banners in the shell.
    if (st.countsWarning) {
      var cwBox = el("div", "tdl-warn-banner tdl-counts-warning");
      cwBox.appendChild(el("strong", "",
        "Evidence counts could not be verified: "));
      cwBox.appendChild(document.createTextNode(st.countsWarning));
      wrap.appendChild(cwBox);
    }

    // Phase 2: the evaluation checklist is scaffolding for reviewing the
    // Lab against the spec. It says "this panel is part of the removable
    // lab" in the operator's face; standalone keeps it, the shell does not.
    if (!embedded) wrap.appendChild(renderEvalChecklist());

    var metrics = el("div", "tdl-metrics");
    [["Days", st.days.length],
      ["Regions", ((st.tree && st.tree.regions) || []).length],
      ["Stops", countStops()],
      ["Photos", st.photoLinks.length],
      ["Story Notes", st.notes.length],
      ["Sources", st.sources.length]].forEach(function (m) {
      var d = el("div");
      d.appendChild(el("strong", "", m[1]));
      d.appendChild(el("span", "", m[0]));
      metrics.appendChild(d);
    });
    wrap.appendChild(metrics);

    // Phase A: the "☑ Generate / reconcile day cards" button is gone.
    // [It read exactly that and called generateDays(). Retired 2026-07-28
    // because it asked the operator to perform the system's own
    // bookkeeping: the day cards are a function of the trip dates, and a
    // button that re-derives them is an admission that something else
    // might have failed to. The generation now happens on load --- see
    // maybeAutoAddMissingDays(). generateDays() itself is kept and still
    // reachable from the reconcile drawer, because a manual re-run is a
    // reasonable thing to have when the automatic one has reported a
    // failure.]
    //
    // Trip setup takes the slot instead. It sits beside the dates on
    // purpose: the dates are what it edits, and it is no longer on the
    // tab bar.
    var bar = el("div", "tdl-toolbar");
    bar.appendChild(btn("tdl-btn", "✎ Trip setup — dates, regions, stops",
      function () { setTab("trip"); }));
    bar.appendChild(el("span", "tdl-spacer"));
    bar.appendChild(el("span", "tdl-muted",
      "📅 " + (st.trip.start_date || "?") + " → " + (st.trip.end_date || "?")));
    wrap.appendChild(bar);

    // Date-range reconcile banners (WO-TRAVEL-DOC-UI-LAB-03). Missing
    // in-range days are addable in one click; day cards outside the
    // current trip dates are surfaced — never hidden, never deleted.
    // Phase A: the missing-days banner is gone with its button.
    // [It read "Trip dates include N day(s) not yet in the calendar."
    // beside an "Add missing days" control. Retired 2026-07-28: missing
    // in-range days are now added without being asked for, so a banner
    // announcing them would be describing a state that no longer
    // survives a page load. If the automatic add FAILS, that is reported
    // through st.daysWarning above, which is a different claim and keeps
    // its banner.]
    //
    // The outside-date banner stays, and it now describes BOTH halves
    // of Chris's ruling of 2026-07-28 on shrinking trip dates: "if
    // shrinking would drop a day that has content, don't, and show
    // what's on it so I can move or clear it first. Empty days are
    // dropped without asking." The refusal lives in the trip editor,
    // where the shortening is attempted; the removal is asked for right
    // after that save succeeds, via drop_empty_out_of_range.
    //
    // [Until 2026-07-28 this block read: "The other half of that ruling
    // --- 'empty days are dropped without asking' --- is NOT implemented
    // here and must not be read into this banner: this surface has no
    // route that removes a day card at all ... Dropping the empty cards
    // Chris is willing to lose needs a server route and is later work."
    // True when written, and the server route it was waiting for is the
    // one it named. Chris's Phase A review asked for the rest: "remove
    // empty out-of-range days; refuse and clearly list out-of-range days
    // containing work." What has NOT changed, and is the part worth
    // carrying forward: a card that holds anything is never removed from
    // this surface, and the reconcile review still only reviews.]
    var rec = st.reconcile;
    if (rec && (rec.out_of_range_days || []).length) {
      var ob = el("div", "tdl-reconcile-banner tdl-reconcile-outside");
      // [This read "They were kept, not deleted, because they have your
      // work on them." Corrected 2026-07-28: that was true of every
      // outside card when nothing could be removed. Now the empty ones
      // are removed on the save that pushes them out, so a card sitting
      // here either has work on it or arrived by a path that did not go
      // through a trip-date save --- and telling the operator all of
      // them hold work would send them looking for content that is not
      // on some of them.]
      ob.appendChild(el("span", "",
        rec.out_of_range_days.length + " day card(s) sit outside your " +
        "current trip dates. Cards with your work on them are kept, " +
        "never deleted; empty ones are removed when you change the " +
        "dates."));
      ob.appendChild(btn("tdl-btn tdl-btn-small", "See what is on them",
        openReconcileDrawer));
      wrap.appendChild(ob);
    }

    if (!st.days.length && !(st.preservedDays || []).length) {
      // [This read "No day cards yet. Generate them from the trip dates
      // above (needs trip start and end dates)." Retired 2026-07-28 with
      // the Generate button it was pointing at --- an empty state that
      // tells you to press something that is not on the screen is worse
      // than one that says nothing. The remaining cause is the real one:
      // day cards are derived from the dates, so with no dates there is
      // nothing to derive, and the fix is in Trip setup.]
      var noDates = !st.trip.start_date || !st.trip.end_date;
      wrap.appendChild(el("div", "tdl-empty", noDates ?
        "This trip has no start and end dates yet, so there are no days " +
        "to make cards from. Add the dates in Trip setup and the cards " +
        "appear here." :
        "No day cards for these dates yet. If they do not appear in a " +
        "moment, reload the page --- and if a warning appears above, it " +
        "says why."));
      return wrap;
    }

    if (st.days.length) {
      var list = el("div", "tdl-day-list");
      st.days.forEach(function (day) {
        list.appendChild(renderDayCard(day));
      });
      wrap.appendChild(list);
    } else {
      // Empty current-window with preserved cards below is a real
      // shape (operator shrank dates to the trip's edges then removed
      // all of them). Say so, don't imply nothing exists.
      wrap.appendChild(el("div", "tdl-empty",
        "No day cards inside the current trip dates. Preserved " +
        "cards from earlier date ranges are shown below."));
    }

    // 2026-07-23 partition: preserved day cards from outside the
    // current start/end window. They keep their prior day_index
    // (never renumbered), are dimmed to signal "not part of the
    // current calendar," and appear in their own section so an
    // operator who moves trip dates doesn't lose sight of prior
    // work — the notes on those cards are still there.
    if ((st.preservedDays || []).length) {
      var pwrap = el("div", "tdl-preserved-days");
      var phead = el("div", "tdl-preserved-days-head");
      phead.appendChild(el("strong", "",
        "Preserved cards outside current trip dates"));
      phead.appendChild(el("span", "tdl-muted",
        " · " + st.preservedDays.length + " kept " +
        "so their notes are not lost. Widen the trip dates to " +
        "bring them back into the calendar."));
      pwrap.appendChild(phead);
      var plist = el("div", "tdl-day-list tdl-day-list-preserved");
      st.preservedDays.forEach(function (day) {
        var card = renderDayCard(day);
        if (card && card.classList) {
          card.classList.add("tdl-day-card-preserved");
        }
        plist.appendChild(card);
      });
      pwrap.appendChild(plist);
      wrap.appendChild(pwrap);
    }
    return wrap;
  }

  // Generate / reconcile (WO-TRAVEL-DOC-UI-LAB-03): generation only
  // appends missing in-range dates — it never deletes operator work.
  // After generating, the reconcile preview refreshes so the banners
  // reflect the new state (missing days added, outside-date days kept).
  function generateDays() {
    if (!st.trip) return;
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/days/generate-from-dates",
      { method: "POST", body: {} })
      .then(function () { return Promise.all([reloadDays(), reloadReconcile()]); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function addMissingDays() {
    if (!st.trip) return;
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/days/reconcile",
      { method: "POST", body: { add_missing: true } })
      .then(function () { return Promise.all([reloadDays(), reloadReconcile()]); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function acknowledgeOutsideDays() {
    if (!st.trip) return;
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/days/reconcile",
      { method: "POST", body: { mark_out_of_range: true } })
      .then(function () { return Promise.all([reloadDays(), reloadReconcile()]); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function outsideDayIdSet() {
    var set = {};
    ((st.reconcile && st.reconcile.out_of_range_days) || []).forEach(function (d) {
      set[d.id] = true;
    });
    return set;
  }

  // ── Dev-harness evaluation checklist (WO-TRAVEL-DOC-UI-LAB-03 Part C) ──
  // Live booleans over the loaded trip data. Rendered only when this
  // module is NOT mounted by the shell, so an operator never sees it —
  // see the !embedded gate at its call site.
  function renderEvalChecklist() {
    var rec = st.reconcile;
    var reconciled = st.days.length > 0 && !!rec &&
      !(rec.missing_dates || []).length &&
      !(rec.out_of_range_days || []).length;
    var items = [
      ["Day cards generated / reconciled", reconciled],
      ["Photos attached to days", st.photoLinks.some(function (l) {
        return !!l.trip_day_id;
      })],
      ["Sources attached to days", st.sources.some(function (s) {
        return !!s.trip_day_id;
      })],
      ["Lori day captures present", st.notes.some(function (n) {
        return n.source_surface === "travel_doc_modal" && !!n.trip_day_id;
      })],
      ["Travelogue preview available", !!st.travelogue],
    ];
    var panel = el("div", "tdl-eval-panel");
    var head = el("div", "tdl-eval-head");
    head.appendChild(el("strong", "", "Lab-only evaluation checklist"));
    head.appendChild(el("span", "tdl-muted",
      " · live status of the Travel Doc flows. Dev harness only — the " +
      "operator's Travel Doc tab does not render this panel."));
    panel.appendChild(head);
    var row = el("div", "tdl-eval-items");
    items.forEach(function (it) {
      var item = el("span", "tdl-eval-item " +
        (it[1] ? "tdl-eval-on" : "tdl-eval-off"));
      item.appendChild(el("b", "", it[1] ? "✓" : "○"));
      item.appendChild(el("span", "", it[0]));
      row.appendChild(item);
    });
    panel.appendChild(row);
    return panel;
  }

  // [dayActionRow() was deleted here on 2026-07-28 by
  // WO-TRIP-PLAN-AS-HUB-01 Phase A. It built five buttons --- Talk with
  // Lori, Attach photos, Add note, Attach source, Edit day --- and its
  // stated virtue was that the SAME row appeared on the day card and in
  // the inspector, in one order, everywhere a day was actionable. That
  // was a real improvement over what preceded it and it is why the row
  // is quoted rather than dropped.
  //
  // It went because the sameness stopped being the point. Chris's ask
  // was that clicking a day opens a workspace with the day's actions in
  // it; a card that carries the actions too means the card has five
  // click targets that are not "open this day", and "Edit day" on a card
  // is a button whose whole job is to do what clicking the card already
  // did. The actions now live in the day workspace beside the things
  // they act on --- Attach photos under Photos, Talk with Lori and Add
  // note under Story, Attach source under Sources --- so the card has
  // exactly one meaning: open this day.]

  function renderDayCard(day) {
    var card = el("article", "tdl-day-card" +
      (st.selectedDayId === day.id ? " tdl-selected" : ""));

    var dd = el("div", "tdl-day-date");
    var inner = el("div");
    inner.appendChild(el("span", "", "Day"));
    inner.appendChild(el("strong", "", day.day_index));
    var parts = prettyDate(day.date).split(" · ");
    inner.appendChild(el("span", "", parts[0] || ""));
    inner.appendChild(el("span", "", parts[1] || day.date));
    dd.appendChild(inner);
    card.appendChild(dd);

    var main = el("div", "tdl-day-main");
    main.appendChild(el("h2", "", dayLabel(day)));
    if (outsideDayIdSet()[day.id]) {
      // Never hidden by default — outside-date cards stay visible with
      // an explicit chip (they are kept to protect operator notes).
      main.appendChild(el("span", "tdl-chip-outside",
        "Outside current trip dates" +
        (day.reconcile_status === "out_of_range_acknowledged" ?
          " · reviewed" : "")));
    }
    if (day.lodging_base) main.appendChild(el("p", "", "Lodging: " + day.lodging_base));
    // Phase A: route links are shown when they exist and are silent when
    // they do not. [The else arm read "No linked region/stop yet" in
    // muted text on every card. Retired 2026-07-28: a line on every
    // single day announcing the absence of a thing the operator has not
    // asked for is scaffolding, and the region/stop selects moved to the
    // day workspace's More details section, which is where an operator
    // who wants one goes.]
    var stop = day.trip_stop_id && findStop(day.trip_stop_id);
    var region = day.trip_region_id && findRegion(day.trip_region_id);
    if (stop) {
      main.appendChild(el("p", "", "Linked stop: " + (stop.location_name || "?")));
    } else if (region) {
      main.appendChild(el("p", "", "Linked region: " + (region.title || "?")));
    }

    var counts = day.counts || {};
    var stats = el("div", "tdl-day-stats");
    [["🖼", counts.photos || 0, "Photos"],
      ["📋", counts.notes || 0, "Notes"],
      ["📄", counts.sources || 0, "Sources"],
      ["📍", counts.public_context || 0, "Context"]].forEach(function (s) {
      var span = el("span");
      span.appendChild(el("i", "", s[0]));
      span.appendChild(el("b", "", s[1]));
      span.appendChild(el("small", "", s[2]));
      stats.appendChild(span);
    });
    main.appendChild(stats);
    main.appendChild(el("span", "tdl-day-open-hint", "Open this day \u203a"));
    card.appendChild(main);

    // Phase A instruction 4: the ENTIRE card is the control. It carries
    // no buttons any more, so there is no longer a part of a day card
    // that does something other than open the day.
    //
    // The closest("button") guard is kept even though nothing on the
    // card is a button today: the guard costs nothing and the next
    // person to add a control here should not have to rediscover that
    // the card swallows clicks.
    function openThisDay() {
      // FIXPACK M5, restated for Phase A instruction 10: selecting a
      // different day re-renders and would discard the open workspace's
      // typed-but-unsaved edits. This handler was the one path into the
      // inspector that did NOT ask --- day-to-day movement by clicking
      // the calendar is the most likely way to lose a half-typed day,
      // and it was the one that skipped the check.
      if (dayFormDirtyBlocks()) return;
      st.selectedDayId = day.id;
      renderAll();
    }
    card.addEventListener("click", function (e) {
      if (e.target.closest("button")) return;
      openThisDay();
    });
    // A whole-card control has to be reachable without a mouse, or
    // making it whole-card has taken a working button away from
    // keyboard users rather than given them a bigger target.
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openThisDay();
      }
    });
    return card;
  }

  // ── Day-detail inspector (fixed header / scroll body / sticky footer) ─

  // Stop/region-scope fallback rows for a day card. Day-ATTACHED rows
  // (trip_day_id, migrations 0028/0029) are handled by the callers —
  // this helper deliberately serves only the un-day-linked fallback.
  function dayScopedRows(rows, day) {
    if (day.trip_stop_id) {
      return rows.filter(function (r) { return r.trip_stop_id === day.trip_stop_id; });
    }
    if (day.trip_region_id) {
      return rows.filter(function (r) {
        return r.trip_region_id === day.trip_region_id && !r.trip_stop_id;
      });
    }
    return [];
  }

  function dayLinkedNotes(day) {
    return st.notes.filter(function (n) { return n.trip_day_id === day.id; });
  }

  function dayLinkedPhotoLinks(day) {
    return st.photoLinks.filter(function (l) { return l.trip_day_id === day.id; });
  }

  function dateMatchedPhotoLinks(day) {
    return st.photoLinks.filter(function (l) {
      return !l.trip_day_id && linkTakenDate(l) === day.date;
    });
  }

  // Dirty-state form registry for the currently open inspector. Field
  // edits mark it dirty in place (no re-render) so typing never loses
  // focus; Save/Cancel resolve it.
  var dayForm = null;

  function markDayFormDirty() {
    if (!dayForm || dayForm.dirty) {
      if (dayForm) dayForm.dirty = true;
      return;
    }
    dayForm.dirty = true;
    dayForm.badges.forEach(function (b) { b.classList.add("tdl-dirty-on"); });
    dayForm.saveButtons.forEach(function (b) { b.disabled = false; });
  }

  function cancelDayEdits() {
    // Esc / Cancel reverts: values re-render from st.days.
    dayForm = null;
    renderAll();
  }

  // WO-TRIP-LANE-AUDIT-FIXPACK-01 (M5): before any action that would
  // destructively re-render and discard the day inspector's typed-but-
  // unsaved edits, require an explicit discard confirmation. Returns
  // true if the caller should ABORT (user chose to keep editing). Save
  // and Cancel are deliberate and never call this.
  function dayFormDirtyBlocks() {
    if (!dayForm || !dayForm.dirty) return false;
    // Lab doctrine: NO native confirm() dialogs. Rather than silently
    // discarding typed edits on a destructive re-render, block the
    // action and flash the existing Save/Cancel affordance so the
    // operator explicitly Saves (keep) or Cancels (discard).
    (dayForm.badges || []).forEach(function (b) {
      b.classList.add("tdl-dirty-flash");
      b.textContent = "Unsaved changes \u2014 Save or Cancel first";
    });
    (dayForm.saveButtons || []).forEach(function (b) { b.disabled = false; });
    var sb = dayForm.saveButtons && dayForm.saveButtons[0];
    if (sb && sb.scrollIntoView) {
      try { sb.scrollIntoView({ block: "center" }); } catch (e) {}
    }
    return true;
  }

  function saveDayEdits() {
    if (!dayForm) return;
    var f = dayForm;
    var day = f.day;
    var body_ = {
      places_visited: f.fPlaces.value.split("\n").map(function (s) { return s.trim(); })
        .filter(Boolean),
      meals: f.fMeals.value.split("\n").map(function (s) { return s.trim(); })
        .filter(Boolean),
    };
    function setOrClear(field, value, clearFlag) {
      var v = value.trim();
      if (v) body_[field] = v; else body_[clearFlag] = true;
    }
    setOrClear("title", f.fTitle.value, "clear_title");
    setOrClear("main_location", f.fMain.value, "clear_main_location");
    setOrClear("lodging_base", f.fLodging.value, "clear_lodging_base");
    setOrClear("morning_notes", f.fMorning.value, "clear_morning_notes");
    setOrClear("afternoon_notes", f.fAfternoon.value, "clear_afternoon_notes");
    setOrClear("evening_notes", f.fEvening.value, "clear_evening_notes");
    if (f.fStop.value) {
      body_.trip_stop_id = f.fStop.value;
    } else {
      body_.clear_stop = true;
    }
    if (f.fRegion.value && !f.fStop.value) {
      body_.trip_region_id = f.fRegion.value;
    } else if (!f.fRegion.value && !f.fStop.value) {
      body_.clear_region = true;
    }
    api("/api/trips/days/" + encodeURIComponent(day.id),
      { method: "PATCH", body: body_ })
      .then(function () { return reloadDays(); })
      .then(function () { st.error = ""; dayForm = null; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function unlinkDayPhoto(day, linkId) {
    api("/api/trips/" + encodeURIComponent(st.trip.id) +
      "/days/" + encodeURIComponent(day.id) + "/photos/unlink",
      { method: "POST", body: { photo_link_ids: [linkId] } })
      .then(function () { return Promise.all([reloadDays(), reloadPhotoLinks()]); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function insSection(key, labelText, openDefault) {
    var det = document.createElement("details");
    det.className = "tdl-ins-sec";
    det.open = (key in insOpen) ? !!insOpen[key] : !!openDefault;
    var sum = el("summary", "tdl-ins-sec-label", labelText);
    det.appendChild(sum);
    det.addEventListener("toggle", function () { insOpen[key] = det.open; });
    return det;
  }

  function dirtyBadge() {
    // Hidden until the form is dirty (tdl-dirty-on).
    return el("span", "tdl-dirty-badge", "Unsaved changes");
  }

  function saveBtn(extraCls) {
    var b = btn("tdl-btn tdl-btn-primary " + (extraCls || ""), "✓ Save Day",
      saveDayEdits);
    b.disabled = true; // enabled by the first edit (dirty tracking)
    return b;
  }

  function renderInspector() {
    var day = dayById(st.selectedDayId);
    var ins = el("aside", "tdl-inspector");
    if (!day) return ins;

    dayForm = { day: day, dirty: false, badges: [], saveButtons: [] };

    // ── fixed header: nav + top mini action row ──
    var head = el("div", "tdl-inspector-head");
    var row1 = el("div", "tdl-inspector-head-row");
    // Phase A instruction 5: this panel is the day workspace and says so.
    // [The kicker read "Day N of M" alone. It was accurate and it was
    // also the only label on the panel, so the panel had no name ---
    // which is how it came to be described as a missing feature in a
    // review of a screen that already had it.]
    row1.appendChild(el("span", "tdl-kicker",
      "Day workspace \u00b7 Day " + day.day_index + " of " + st.days.length));
    var nav = el("div");
    var idx = st.days.indexOf(day);
    nav.appendChild(btn("tdl-btn tdl-btn-small", "‹", function () {
      if (idx > 0) { if (dayFormDirtyBlocks()) return; st.selectedDayId = st.days[idx - 1].id; renderAll(); }
    }));
    nav.appendChild(btn("tdl-btn tdl-btn-small", "›", function () {
      if (idx < st.days.length - 1) { if (dayFormDirtyBlocks()) return; st.selectedDayId = st.days[idx + 1].id; renderAll(); }
    }));
    nav.appendChild(btn("tdl-btn tdl-btn-small", "×", function () {
      if (dayFormDirtyBlocks()) return; st.selectedDayId = null; dayForm = null; renderAll();
    }));
    row1.appendChild(nav);
    head.appendChild(row1);

    // Top mini action row: Save Day · Cancel · More — no more hunting
    // for a Save button at the bottom of a long scroll.
    var actRow = el("div", "tdl-ins-actions");
    var topBadge = dirtyBadge();
    actRow.appendChild(topBadge);
    dayForm.badges.push(topBadge);
    var topSave = saveBtn("tdl-btn-small");
    actRow.appendChild(topSave);
    dayForm.saveButtons.push(topSave);
    actRow.appendChild(btn("tdl-btn tdl-btn-small", "Cancel", cancelDayEdits));
    actRow.appendChild(btn("tdl-btn tdl-btn-small", "More ▾", function () {
      // Expand every section (quick way to see the whole day).
      ins.querySelectorAll("details.tdl-ins-sec").forEach(function (d) {
        d.open = true;
      });
    }));
    head.appendChild(actRow);
    ins.appendChild(head);

    // ── scroll body: collapsible sections ──
    var body = el("div", "tdl-inspector-body");

    function labeled(text, input) {
      var l = el("label", "tdl-label");
      l.appendChild(el("span", "", text));
      l.appendChild(input);
      return l;
    }
    function watch(input) {
      input.addEventListener("input", markDayFormDirty);
      input.addEventListener("change", markDayFormDirty);
      return input;
    }

    // ── Section: Day (default open) ──
    //
    // Phase A instruction 5 reorganised this panel into the order Chris
    // asked for: Day, Photos, Story, Places and meals, Sources, More
    // details. [It previously ran Overview / Notes / Photos / Sources /
    // Lori captures, with Overview carrying the region and stop selects
    // and a technical Lori scope line, and with Notes carrying the
    // period notes, places, meals AND the day story notes together. The
    // old order is quoted because it was not arbitrary --- it followed
    // the shape of the day row in the database. It is being replaced
    // because the operator's order is not the table's order.]
    var ov = insSection("overview", "Day", true);
    ov.appendChild(el("h2", "", prettyDate(day.date) + " · " + day.date));
    ov.appendChild(el("h3", "", dayLabel(day)));

    var fTitle = watch(el("input")); fTitle.value = day.title || "";
    var fMain = watch(el("input")); fMain.value = day.main_location || "";
    var fLodging = watch(el("input")); fLodging.value = day.lodging_base || "";
    ov.appendChild(labeled("Day title", fTitle));
    ov.appendChild(labeled("Main location", fMain));
    ov.appendChild(labeled("Lodging", fLodging));
    body.appendChild(ov);

    // ── Section: Photos (day-linked first, then date matches) ──
    var dayLinks = dayLinkedPhotoLinks(day);
    var dateLinks = dateMatchedPhotoLinks(day);
    var ph = insSection("photos", "Photos (" + (dayLinks.length + dateLinks.length) + ")", false);
    if (dayLinks.length) {
      ph.appendChild(el("div", "tdl-row-title-plain", "Attached to this day"));
      var rowA = el("div", "tdl-photo-row");
      dayLinks.slice(0, 12).forEach(function (l) {
        var cellWrap = el("div", "tdl-photo-cell");
        var im = thumbImg(l.photo_id, l.caption, false);
        cellWrap.appendChild(im);
        cellWrap.appendChild(btn("tdl-btn tdl-btn-small", "Remove from this day",
          function () { unlinkDayPhoto(day, l.id); }));
        rowA.appendChild(cellWrap);
      });
      ph.appendChild(rowA);
    }
    if (dateLinks.length) {
      ph.appendChild(el("div", "tdl-row-title-plain", "Dated to this day (not attached)"));
      var rowB = el("div", "tdl-photo-row");
      dateLinks.slice(0, 8).forEach(function (l) {
        var im = thumbImg(l.photo_id, l.caption, false);
        rowB.appendChild(im);
      });
      ph.appendChild(rowB);
    }
    if (!dayLinks.length && !dateLinks.length) {
      ph.appendChild(el("p", "tdl-muted", "No photos on this day yet."));
    }
    // [Read "＋ Attach photos" until 2026-07-28. Chris: "rename
    // Attach photos to Add photos". Attaching an already-approved
    // photo is one of the things this control will do, not the only
    // one, and a label that names the narrowest case is a label that
    // has to be renamed again the moment a second source arrives.]
    ph.appendChild(btn("tdl-btn", "＋ Add photos",
      function () { openPhotoPicker(day.id); }));
    body.appendChild(ph);

    // ── Section: Story (Lori, then what she captured, then the day) ──
    //
    // Talk with Lori leads because it is how the day gets written, not
    // because it is the most-used control. The captures she takes are
    // directly under it so the result of the conversation is visible in
    // the same place the conversation starts.
    var loriNotes = st.notes.filter(function (n) {
      return n.source_surface === "travel_doc_modal" && n.trip_day_id === day.id;
    });
    var story = insSection("story", "Story", false);
    story.appendChild(btn("tdl-btn tdl-btn-gold", "💬 Talk with Lori",
      function () { openLoriOverlay(day.id); }));
    // Phase A instruction 6, in place of the technical scope line.
    // [The Overview section carried: "Lori scope: active_trip_day_id =
    // <first 8 chars>... Day-level conversation uses this day plus its
    // linked stop/photos/notes/sources." Retired 2026-07-28. The claim
    // was true and worth making --- an operator does need to know what
    // Lori can see --- but an identifier prefix is not how you make it
    // to the person whose trip this is. The identifier itself moved to
    // More details, where somebody debugging can still find it.]
    story.appendChild(el("p", "tdl-muted",
      "Lori sees this day — its title and location, its photos, notes " +
      "and sources — while you talk."));
    // WO-LIVE-TRIP-COMPANION-01 VS1 — where the conversation goes,
    // said before it happens rather than discovered afterwards.
    if (tripLiveState() === "active") {
      if (tripSelectedDayId() === day.id) {
        story.appendChild(el("p", "tdl-live-note",
          "You are on this day. What you say to Lori is filed here."));
      } else {
        var pickRow = el("p", "tdl-live-note");
        pickRow.appendChild(document.createTextNode(
          "Talking with Lori here will file the conversation to this day. "));
        pickRow.appendChild(btn("tdl-btn tdl-btn-small",
          "Make this the day I'm on",
          function () { setTripSelectedDay(day.id); }));
        story.appendChild(pickRow);
      }
      story.appendChild(btn("tdl-btn tdl-btn-small", "▤ What happened today",
        function () { openTripCalendar(day.id); }));
    } else {
      story.appendChild(el("p", "tdl-live-note",
        "This trip has not been started, so nothing said here is filed " +
        "to a day yet. Start the trip on the Trip Calendar."));
    }

    var lorHead = el("div", "tdl-row-title");
    lorHead.appendChild(el("span", "",
      "Captured from Lori (" + loriNotes.length + ")"));
    story.appendChild(lorHead);
    var ll = el("div", "tdl-mini-list");
    loriNotes.slice(0, 8).forEach(function (n) {
      var lrow = el("div");
      lrow.appendChild(el("span", "tdl-lori-drawer-src", "from Lori"));
      lrow.appendChild(el("span", "", " " + (n.note_text || "").slice(0, 110)));
      ll.appendChild(lrow);
    });
    if (!loriNotes.length) {
      ll.appendChild(el("div", "tdl-muted",
        "Nothing captured for this day yet — use Talk with Lori."));
    }
    story.appendChild(ll);

    var dNotes = dayLinkedNotes(day);
    var scopedNotes = dayScopedRows(st.notes, day).filter(function (n) {
      return !n.trip_day_id;
    });
    var nt = el("div", "tdl-row-title");
    nt.appendChild(el("span", "",
      "Day story notes (" + dNotes.length + ")"));
    story.appendChild(nt);
    var nl = el("div", "tdl-mini-list");
    dNotes.slice(0, 8).forEach(function (n) {
      nl.appendChild(el("div", "", (n.note_title ? n.note_title + " — " : "") +
        (n.note_text || "").slice(0, 90)));
    });
    scopedNotes.slice(0, 4).forEach(function (n) {
      nl.appendChild(el("div", "tdl-muted", "(stop/region) " +
        (n.note_text || "").slice(0, 90)));
    });
    if (!dNotes.length && !scopedNotes.length) {
      nl.appendChild(el("div", "tdl-muted", "No notes for this day yet."));
    }
    story.appendChild(nl);
    story.appendChild(btn("tdl-btn", "＋ Add note",
      function () { openNoteDrawer(day.id); }));

    var per = el("div", "tdl-period-grid");
    var fMorning = watch(el("textarea")); fMorning.value = day.morning_notes || "";
    var fAfternoon = watch(el("textarea")); fAfternoon.value = day.afternoon_notes || "";
    var fEvening = watch(el("textarea")); fEvening.value = day.evening_notes || "";
    [["Morning", fMorning], ["Afternoon", fAfternoon], ["Evening", fEvening]]
      .forEach(function (p) {
        var c = el("div", "tdl-period-card");
        c.appendChild(el("h4", "", p[0]));
        c.appendChild(p[1]);
        per.appendChild(c);
      });
    story.appendChild(per);
    body.appendChild(story);

    // ── Section: Places and meals ──
    var fPlaces = watch(el("textarea"));
    fPlaces.value = (day.places_visited_json || []).join("\n");
    fPlaces.placeholder = "One place per line";
    var fMeals = watch(el("textarea"));
    fMeals.value = (day.meals_json || []).join("\n");
    fMeals.placeholder = "One meal per line";
    var pm = insSection("places", "Places and meals", false);
    pm.appendChild(labeled("Places visited (one per line)", fPlaces));
    pm.appendChild(labeled("Meals (one per line)", fMeals));
    body.appendChild(pm);

    // ── Section: Sources (day-attached first, then stop/region scope) ──
    var dayLinkedSources = dayAttachedSources(day);
    var scopedSources = dayScopedRows(st.sources, day).filter(function (s) {
      return !s.trip_day_id;
    });
    var ss = insSection("sources",
      "Sources (" + (dayLinkedSources.length + scopedSources.length) + ")",
      false);
    if (dayLinkedSources.length) {
      ss.appendChild(el("div", "tdl-row-title-plain", "Attached to this day"));
      var sla = el("div", "tdl-mini-list");
      dayLinkedSources.slice(0, 8).forEach(function (s) {
        sla.appendChild(sourceMiniRow(s, day));
      });
      ss.appendChild(sla);
    }
    if (scopedSources.length) {
      ss.appendChild(el("div", "tdl-row-title-plain", "From linked stop/region"));
      var slb = el("div", "tdl-mini-list");
      scopedSources.slice(0, 6).forEach(function (s) {
        slb.appendChild(sourceMiniRow(s, null));
      });
      ss.appendChild(slb);
    }
    if (!dayLinkedSources.length && !scopedSources.length) {
      var sln = el("div", "tdl-mini-list");
      sln.appendChild(el("div", "tdl-muted", "None linked."));
      ss.appendChild(sln);
    }
    ss.appendChild(btn("tdl-btn", "＋ Attach source",
      function () { openSourceDrawer(day.id); }));
    body.appendChild(ss);

    // ── Section: More details (route links + identifiers) ──
    //
    // Phase A instruction 6: "The advanced region, stop, technical Lori
    // scope, and internal identifiers should be hidden under More
    // details. You should not normally see an active_trip_day_id."
    // Hidden, and deliberately not removed --- the identifier is the
    // thing you need when a day is behaving oddly, and a workspace that
    // cannot tell you which row it is editing is a workspace nobody can
    // debug. Collapsed by default is the whole of the fix.
    var more = insSection("more", "More details", false);
    more.appendChild(el("p", "tdl-muted",
      "Route links and internal identifiers. You do not normally need " +
      "these."));
    var fRegion = watch(document.createElement("select"));
    var optNone = el("option", "", "— no region —"); optNone.value = "";
    fRegion.appendChild(optNone);
    ((st.tree && st.tree.regions) || []).forEach(function (r) {
      var o = el("option", "", r.title || "Region"); o.value = r.id;
      if (day.trip_region_id === r.id) o.selected = true;
      fRegion.appendChild(o);
    });
    var fStop = watch(document.createElement("select"));
    var so = el("option", "", "— no stop —"); so.value = "";
    fStop.appendChild(so);
    ((st.tree && st.tree.regions) || []).forEach(function (r) {
      (function walk(stops, depth) {
        (stops || []).forEach(function (s) {
          var o = el("option", "",
            (r.title || "") + " › " + Array(depth + 1).join("  ") +
            (s.location_name || "Stop"));
          o.value = s.id;
          if (day.trip_stop_id === s.id) o.selected = true;
          fStop.appendChild(o);
          walk(s.children, depth + 1);
        });
      })(r.stops, 0);
    });
    more.appendChild(labeled("Linked region", fRegion));
    more.appendChild(labeled("Linked stop", fStop));
    var idLine = el("div", "tdl-lori-scope-note");
    idLine.appendChild(el("b", "", "Identifier: "));
    idLine.appendChild(el("span", "tdl-muted",
      "active_trip_day_id = " + day.id));
    more.appendChild(idLine);
    body.appendChild(more);

    ins.appendChild(body);

    // ── sticky footer: Save Day (mirror of the top action row) ──
    var foot = el("footer", "tdl-inspector-footer");
    var footBadge = dirtyBadge();
    foot.appendChild(footBadge);
    dayForm.badges.push(footBadge);
    var footSave = saveBtn("");
    foot.appendChild(footSave);
    dayForm.saveButtons.push(footSave);
    ins.appendChild(foot);

    // Register form fields for save/cancel + Esc-to-cancel.
    dayForm.fTitle = fTitle; dayForm.fMain = fMain; dayForm.fLodging = fLodging;
    dayForm.fRegion = fRegion; dayForm.fStop = fStop;
    dayForm.fMorning = fMorning; dayForm.fAfternoon = fAfternoon;
    dayForm.fEvening = fEvening; dayForm.fPlaces = fPlaces; dayForm.fMeals = fMeals;
    ins.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); cancelDayEdits(); }
    });
    return ins;
  }

  // ── Day-scoped sources (WO-TRAVEL-DOC-UI-LAB-03) ─────────────────────

  function dayAttachedSources(day) {
    return st.sources.filter(function (s) { return s.trip_day_id === day.id; });
  }

  function sourceTypeBadge(s) {
    return el("span", "tdl-badge tdl-badge-srctype", s.source_type || "other");
  }

  function sourceMemoirState(s) {
    return el("span", s.include_in_memoir ? "tdl-flag-on" : "tdl-flag-off",
      s.include_in_memoir ? "In memoir ON" : "In memoir OFF");
  }

  function sourceMiniRow(s, day) {
    var row = el("div", "tdl-src-row");
    row.appendChild(sourceTypeBadge(s));
    row.appendChild(el("span", "",
      (s.title || s.filename || s.summary || s.link_url || "untitled")));
    row.appendChild(sourceMemoirState(s));
    if (day) {
      // Unlink clears trip_day_id ONLY — the source row is never deleted.
      row.appendChild(btn("tdl-btn tdl-btn-small", "Unlink from day",
        function () { unlinkSourceFromDay(s.id); }));
    }
    return row;
  }

  function unlinkSourceFromDay(sourceId) {
    api("/api/trips/sources/" + encodeURIComponent(sourceId),
      { method: "PATCH", body: { clear_day: true } })
      .then(function () { return Promise.all([reloadSources(), reloadDays()]); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function openSourceDrawer(dayId) {
    if (dayFormDirtyBlocks()) return;
    st.selectedDayId = dayId;
    st.sourceDrawerDayId = dayId;
    st.photoPickerDayId = null;
    st.noteDrawerDayId = null;
    st.loriOverlay = false;
    renderAll();
  }

  function closeSourceDrawer() {
    st.sourceDrawerDayId = null;
    renderAll();
  }

  var SOURCE_TYPE_OPTIONS = ["receipt", "hotel", "ticket", "itinerary",
    "link", "note", "map", "other"];

  function renderSourceDrawer() {
    var day = dayById(st.sourceDrawerDayId);
    var wrap = el("div", "tdl-drawer-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeSourceDrawer();
    });
    var drawer = el("aside", "tdl-drawer tdl-source-drawer");
    if (!day) { st.sourceDrawerDayId = null; return wrap; }

    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    ht.appendChild(el("div", "tdl-kicker",
      "Attach source to Day " + day.day_index));
    ht.appendChild(el("strong", "", dayChipText(day)));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn tdl-btn-small", "✕ Back to Trip Plan",
      closeSourceDrawer));
    drawer.appendChild(head);

    var body = el("div", "tdl-drawer-body");

    // ── New pasted-text / link source, day-scoped ──
    body.appendChild(el("div", "tdl-row-title-plain", "New source"));
    function labeled(text, input) {
      var l = el("label", "tdl-label");
      l.appendChild(el("span", "", text));
      l.appendChild(input);
      return l;
    }
    var fTitle = el("input");
    fTitle.placeholder = "e.g. Hotel booking, museum ticket";
    var fType = document.createElement("select");
    SOURCE_TYPE_OPTIONS.forEach(function (t) {
      var o = el("option", "", t); o.value = t;
      fType.appendChild(o);
    });
    var fDate = el("input");
    fDate.placeholder = "YYYY-MM-DD (optional)";
    var fSummary = el("input");
    fSummary.placeholder = "Optional one-line summary";
    var fText = el("textarea");
    fText.placeholder = "Pasted text (confirmation email, receipt text…)";
    var fUrl = el("input");
    fUrl.placeholder = "https://… (optional link)";
    body.appendChild(labeled("Title", fTitle));
    body.appendChild(labeled("Source type", fType));
    body.appendChild(labeled("Date", fDate));
    body.appendChild(labeled("Summary", fSummary));
    body.appendChild(labeled("Pasted text", fText));
    body.appendChild(labeled("Link URL", fUrl));
    body.appendChild(el("p", "tdl-muted",
      "Saved day-scoped on this day card — In memoir OFF until you flip " +
      "it in Sources."));
    body.appendChild(btn("tdl-btn tdl-btn-primary", "✓ Save source to this day",
      function () {
        var title = (fTitle.value || "").trim();
        var text = (fText.value || "").trim();
        var url = (fUrl.value || "").trim();
        if (!title && !text && !url) return;
        api("/api/trips/" + encodeURIComponent(st.trip.id) + "/sources",
          { method: "POST", body: {
            source_type: fType.value || "other",
            title: title || null,
            pasted_text: text || null,
            link_url: url || null,
            source_date: (fDate.value || "").trim() || null,
            summary: (fSummary.value || "").trim() || null,
            trip_day_id: day.id,
          } })
          .then(function () { return Promise.all([reloadSources(), reloadDays()]); })
          .then(function () {
            st.error = "";
            st.sourceDrawerDayId = null;
            renderAll();
          })
          .catch(function (e) { st.error = e.message; renderAll(); });
      }));

    // ── Attach existing trip sources (Attach vs Move is explicit) ──
    body.appendChild(el("div", "tdl-row-title-plain", "Attach existing source"));
    var checked = {};
    function selCounts() {
      var counts = { attach: 0, move: 0 };
      Object.keys(checked).forEach(function (k) {
        if (!checked[k]) return;
        var s = st.sources.filter(function (x) { return x.id === k; })[0];
        if (s && s.trip_day_id) counts.move += 1; else counts.attach += 1;
      });
      return counts;
    }
    function paintAttachSources() {
      var c = selCounts();
      var total = c.attach + c.move;
      if (!total) {
        attach.textContent = "Attach selected to " + dayChipText(day);
      } else if (c.move) {
        attach.textContent = "Attach " + c.attach + " · Move " + c.move;
      } else {
        attach.textContent = "Attach " + c.attach + " to " + dayChipText(day);
      }
      attach.disabled = !total;
      moveNotice.textContent = c.move ?
        (c.move + " source(s) will move from other days.") : "";
      moveNotice.style.display = c.move ? "" : "none";
    }
    var listWrap = el("div", "tdl-src-pick-list");
    var pickable = st.sources.filter(function (s) {
      return s.trip_day_id !== day.id;
    });
    if (!pickable.length) {
      listWrap.appendChild(el("div", "tdl-muted",
        st.sources.length ?
          "Every trip source is already attached to this day." :
          "This trip has no other sources yet."));
    }
    pickable.forEach(function (s) {
      var rowLab = el("label", "tdl-src-pick-row");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.addEventListener("change", function () {
        checked[s.id] = cb.checked;
        paintAttachSources();
      });
      rowLab.appendChild(cb);
      rowLab.appendChild(sourceTypeBadge(s));
      rowLab.appendChild(el("span", "",
        s.title || s.filename || s.summary || s.link_url || "untitled"));
      if (s.trip_day_id) {
        var other = dayById(s.trip_day_id);
        rowLab.appendChild(el("small", "tdl-muted",
          other ? ("on Day " + other.day_index) : "on another day"));
      }
      rowLab.appendChild(el("small",
        "tdl-picker-action" + (s.trip_day_id ? " tdl-picker-action-move" : ""),
        s.trip_day_id ? "Move to this day" : "Attach"));
      listWrap.appendChild(rowLab);
    });
    body.appendChild(listWrap);
    drawer.appendChild(body);

    var moveNotice = el("div", "tdl-move-notice");
    moveNotice.style.display = "none";
    drawer.appendChild(moveNotice);

    var foot = el("div", "tdl-drawer-foot");
    var attach = btn("tdl-btn tdl-btn-primary",
      "Attach selected to " + dayChipText(day), function () {
        var ids = Object.keys(checked).filter(function (k) { return checked[k]; });
        if (!ids.length) return;
        Promise.all(ids.map(function (sid) {
          return api("/api/trips/sources/" + encodeURIComponent(sid),
            { method: "PATCH", body: { trip_day_id: day.id } });
        }))
          .then(function () { return Promise.all([reloadSources(), reloadDays()]); })
          .then(function () {
            st.error = "";
            st.sourceDrawerDayId = null;
            renderAll();
          })
          .catch(function (e) { st.error = e.message; renderAll(); });
      });
    attach.disabled = true;
    foot.appendChild(attach);
    foot.appendChild(btn("tdl-btn", "Cancel", closeSourceDrawer));
    drawer.appendChild(foot);

    wrap.appendChild(drawer);
    return wrap;
  }

  // ── Date-range reconcile review drawer (WO-TRAVEL-DOC-UI-LAB-03) ─────
  // Lists missing in-range dates (addable) and outside-date day cards
  // with per-day content indicators. There is NO delete control here —
  // outside-date cards were kept to protect your notes and stay kept.

  function openReconcileDrawer() {
    st.reconcileDrawerOpen = true;
    st.photoPickerDayId = null;
    st.noteDrawerDayId = null;
    st.sourceDrawerDayId = null;
    st.loriOverlay = false;
    renderAll();
  }

  function closeReconcileDrawer() {
    st.reconcileDrawerOpen = false;
    renderAll();
  }

  function dayLoriCaptureCount(dayId) {
    return st.notes.filter(function (n) {
      return n.source_surface === "travel_doc_modal" && n.trip_day_id === dayId;
    }).length;
  }

  function renderReconcileDrawer() {
    var rec = st.reconcile;
    var wrap = el("div", "tdl-drawer-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeReconcileDrawer();
    });
    var drawer = el("aside", "tdl-drawer tdl-reconcile-drawer");

    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    ht.appendChild(el("div", "tdl-kicker", "Reconcile day cards"));
    ht.appendChild(el("strong", "",
      "📅 " + (st.trip.start_date || "?") + " → " + (st.trip.end_date || "?")));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn tdl-btn-small", "✕ Back to Trip Plan",
      closeReconcileDrawer));
    drawer.appendChild(head);

    var body = el("div", "tdl-drawer-body");
    if (!rec) {
      body.appendChild(el("p", "tdl-muted", "No reconcile data loaded yet."));
    } else {
      var missing = rec.missing_dates || [];
      body.appendChild(el("div", "tdl-row-title-plain",
        "Missing days (" + missing.length + ")"));
      if (missing.length) {
        var ml = el("div", "tdl-mini-list");
        missing.forEach(function (iso) {
          ml.appendChild(el("div", "", prettyDate(iso) + " · " + iso));
        });
        body.appendChild(ml);
        body.appendChild(btn("tdl-btn tdl-btn-primary", "Add missing days",
          function () {
            addMissingDays();
            closeReconcileDrawer();
          }));
      } else {
        body.appendChild(el("p", "tdl-muted",
          "Every date in the trip window has a day card."));
      }

      var outside = rec.out_of_range_days || [];
      body.appendChild(el("div", "tdl-row-title-plain",
        "Outside-date day cards (" + outside.length + ")"));
      if (outside.length) {
        body.appendChild(el("p", "tdl-muted",
          "These day cards sit outside the current trip dates. They were " +
          "kept to protect your notes — nothing is ever deleted here. " +
          "Widen the trip dates to bring them back in range, or mark " +
          "them reviewed."));
        var ol = el("div", "tdl-mini-list");
        outside.forEach(function (d) {
          var full = dayById(d.id) || d;
          var row = el("div", "tdl-reconcile-day-row");
          var line1 = el("div");
          line1.appendChild(el("strong", "",
            "Day " + full.day_index + " · " + full.date));
          if (full.title) line1.appendChild(el("span", "", " — " + full.title));
          line1.appendChild(el("span", "tdl-chip-outside",
            "Outside current trip dates" +
            (full.reconcile_status === "out_of_range_acknowledged" ?
              " · reviewed" : "")));
          row.appendChild(line1);
          var counts = full.counts || {};
          var hasPeriodNotes = !!(full.morning_notes || full.afternoon_notes ||
            full.evening_notes || full.title || full.lodging_base);
          var ind = el("div", "tdl-reconcile-indicators");
          [["📋 notes", (counts.notes || 0) + (hasPeriodNotes ? " +day text" : "")],
            ["🖼 photos", counts.photos || 0],
            ["📄 sources", counts.sources || 0],
            ["💬 Lori captures", dayLoriCaptureCount(full.id) || "—"]]
            .forEach(function (c) {
              ind.appendChild(el("span", "", c[0] + ": " + c[1]));
            });
          row.appendChild(ind);
          ol.appendChild(row);
        });
        body.appendChild(ol);
        body.appendChild(btn("tdl-btn",
          "Mark outside-date days as reviewed (kept)",
          acknowledgeOutsideDays));
      } else {
        body.appendChild(el("p", "tdl-muted",
          "No day cards are outside the current trip dates."));
      }

      var badRows = rec.duplicate_or_invalid_days || [];
      if (badRows.length) {
        body.appendChild(el("div", "tdl-row-title-plain",
          "Days with unreadable dates (" + badRows.length + ")"));
        var bl = el("div", "tdl-mini-list");
        badRows.forEach(function (d) {
          bl.appendChild(el("div", "tdl-muted",
            "Day " + d.day_index + " · date: " + (d.date || "(empty)") +
            " — fix the date on the day card."));
        });
        body.appendChild(bl);
      }
    }
    drawer.appendChild(body);

    var foot = el("div", "tdl-drawer-foot");
    foot.appendChild(btn("tdl-btn", "Close", closeReconcileDrawer));
    drawer.appendChild(foot);

    wrap.appendChild(drawer);
    return wrap;
  }

  // ── In-lab day photo picker (drawer — no navigation away) ────────────

  function openPhotoPicker(dayId) {
    if (dayFormDirtyBlocks()) return;
    st.selectedDayId = dayId;
    st.photoPickerDayId = dayId;
    st.noteDrawerDayId = null;
    st.loriOverlay = false;
    renderAll();
  }

  function closePhotoPicker() {
    st.photoPickerDayId = null;
    renderAll();
  }

  function renderPhotoPicker() {
    var day = dayById(st.photoPickerDayId);
    var wrap = el("div", "tdl-drawer-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closePhotoPicker();
    });
    var drawer = el("aside", "tdl-drawer tdl-photo-picker");
    if (!day) { st.photoPickerDayId = null; return wrap; }

    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    // [Read "Attach existing trip photos" until 2026-07-28. Chris:
    // "rename the drawer to Choose existing Hornelore photos". The
    // old kicker named the ACTION, which was fine while this was the
    // only way a photo reached a day. It names the SOURCE now,
    // because the question this drawer answers is which of several
    // sources you are picking from --- and existing Hornelore photos
    // is the one source that needs no review, since a row in photos
    // is by definition already past it.]
    ht.appendChild(el("div", "tdl-kicker",
      "Choose existing Hornelore photos"));
    ht.appendChild(el("strong", "", dayChipText(day)));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn tdl-btn-small", "✕ Back to Trip Plan",
      closePhotoPicker));
    drawer.appendChild(head);

    var body = el("div", "tdl-drawer-body");
    body.appendChild(el("p", "tdl-muted",
      "Pick trip photos to attach to this day. Attached photos count on " +
      "this day card and show in the day's Photos section."));

    var checked = {};

    // Attach vs Move — reassignment is never silent. Links already on
    // ANOTHER day are labeled "Move to this day" per row, the confirm
    // button splits the counts, and a one-line notice spells out the
    // move. Inline notice only — no native confirm() dialogs.
    function selCounts() {
      var counts = { attach: 0, move: 0 };
      Object.keys(checked).forEach(function (k) {
        if (!checked[k]) return;
        var l = st.photoLinks.filter(function (x) { return x.id === k; })[0];
        if (l && l.trip_day_id) counts.move += 1; else counts.attach += 1;
      });
      return counts;
    }
    function paintAttach() {
      var c = selCounts();
      var total = c.attach + c.move;
      if (!total) {
        attach.textContent = "Attach selected to " + dayChipText(day);
      } else if (c.move) {
        attach.textContent = "Attach " + c.attach + " · Move " + c.move;
      } else {
        attach.textContent = "Attach " + c.attach + " to " + dayChipText(day);
      }
      attach.disabled = !total;
      moveNotice.textContent = c.move ?
        (c.move + " photo(s) will move from other days.") : "";
      moveNotice.style.display = c.move ? "" : "none";
    }

    var grid = el("div", "tdl-picker-grid");
    var pickable = st.photoLinks.filter(function (l) {
      return l.trip_day_id !== day.id;
    });
    if (!pickable.length) {
      // Compact when there is nothing to lay out. Chris: "the drawer in
      // your screenshot is far too large for an empty source. A source
      // chooser should be compact. The wide right-hand drawer should only
      // appear once there are thumbnails or photo details worth showing."
      // The 440px full-height panel is sized for a thumbnail grid; with
      // one sentence in it, it is almost entirely frame. The modifier goes
      // on here rather than into the class list at creation because the
      // drawer element is built before pickable is known.
      drawer.className += " tdl-photo-picker-bare";
      // [The no-photos branch read "This trip has no photos yet. Use
      // Upload on the trip toolbar to add them, then Cluster to sort them
      // into days." until 2026-07-28, and before Phase 4 it read "add them
      // via Photo Intake, then cluster from the production Travel Doc".
      // That is twice this one sentence has pointed at a destination that
      // stopped existing, and both times it stayed on screen telling
      // operators to go there. Chris: "remove the stale Upload message."
      //
      // It is not being re-aimed at a third destination. The source
      // chooser that will properly answer "so where DO photos come from"
      // is deliberately NOT built yet --- a button is a promise, and what
      // Browse this computer does, whether the existing trip-toolbar
      // Upload already bypasses the evidence queue, and how a requested
      // day survives review are all still open questions. Stating the
      // fact and inventing no instruction is the honest state until they
      // close.]
      grid.appendChild(el("div", "tdl-empty",
        st.photoLinks.length ?
          "Every trip photo is already attached to this day." :
          "This trip has no photos yet."));
    }
    pickable.forEach(function (l) {
      var cell = el("label", "tdl-picker-cell");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.addEventListener("change", function () {
        checked[l.id] = cb.checked;
        paintAttach();
      });
      cell.appendChild(cb);
      var im = thumbImg(l.photo_id, l.caption, false);
      cell.appendChild(im);
      var meta = el("div", "tdl-picker-meta");
      meta.appendChild(el("span", "", linkTakenDate(l) || "undated"));
      if (l.trip_day_id) {
        var other = dayById(l.trip_day_id);
        meta.appendChild(el("small", "tdl-muted",
          other ? ("on Day " + other.day_index) : "on another day"));
      }
      cell.appendChild(meta);
      cell.appendChild(el("small",
        "tdl-picker-action" + (l.trip_day_id ? " tdl-picker-action-move" : ""),
        l.trip_day_id ? "Move to this day" : "Attach"));
      grid.appendChild(cell);
    });
    body.appendChild(grid);
    drawer.appendChild(body);

    var moveNotice = el("div", "tdl-move-notice");
    moveNotice.style.display = "none";
    drawer.appendChild(moveNotice);

    var foot = el("div", "tdl-drawer-foot");
    var attach = btn("tdl-btn tdl-btn-primary",
      "Attach selected to " + dayChipText(day), function () {
        var ids = Object.keys(checked).filter(function (k) { return checked[k]; });
        if (!ids.length) return;
        api("/api/trips/" + encodeURIComponent(st.trip.id) +
          "/days/" + encodeURIComponent(day.id) + "/photos/link",
          { method: "POST", body: { photo_link_ids: ids } })
          .then(function () { return Promise.all([reloadDays(), reloadPhotoLinks()]); })
          .then(function () {
            st.error = "";
            st.photoPickerDayId = null;
            renderAll();
          })
          .catch(function (e) { st.error = e.message; renderAll(); });
      });
    attach.disabled = true;
    foot.appendChild(attach);
    foot.appendChild(btn("tdl-btn", "Cancel", closePhotoPicker));
    drawer.appendChild(foot);

    wrap.appendChild(drawer);
    return wrap;
  }

  // ── In-lab day note drawer ────────────────────────────────────────────

  function openNoteDrawer(dayId) {
    if (dayFormDirtyBlocks()) return;
    st.selectedDayId = dayId;
    st.noteDrawerDayId = dayId;
    st.photoPickerDayId = null;
    st.loriOverlay = false;
    renderAll();
  }

  function closeNoteDrawer() {
    st.noteDrawerDayId = null;
    renderAll();
  }

  function renderNoteDrawer() {
    var day = dayById(st.noteDrawerDayId);
    var wrap = el("div", "tdl-drawer-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeNoteDrawer();
    });
    var drawer = el("aside", "tdl-drawer tdl-note-drawer");
    if (!day) { st.noteDrawerDayId = null; return wrap; }

    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    ht.appendChild(el("div", "tdl-kicker", "Add note"));
    ht.appendChild(el("strong", "", dayChipText(day)));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn tdl-btn-small", "✕ Back to Trip Plan",
      closeNoteDrawer));
    drawer.appendChild(head);

    var body = el("div", "tdl-drawer-body");
    var fTitle = el("input");
    fTitle.placeholder = "Optional title";
    var fText = el("textarea");
    fText.placeholder = "What happened this day…";
    var lab1 = el("label", "tdl-label");
    lab1.appendChild(el("span", "", "Title"));
    lab1.appendChild(fTitle);
    var lab2 = el("label", "tdl-label");
    lab2.appendChild(el("span", "", "Note"));
    lab2.appendChild(fText);
    body.appendChild(lab1);
    body.appendChild(lab2);
    body.appendChild(el("p", "tdl-muted",
      "Saved as an operator story note on this day — In memoir OFF, " +
      "Use with Lori OFF until you flip them in Story Notes."));
    drawer.appendChild(body);

    var foot = el("div", "tdl-drawer-foot");
    foot.appendChild(btn("tdl-btn tdl-btn-primary", "✓ Save note", function () {
      var text = (fText.value || "").trim();
      if (!text) return;
      api("/api/trips/" + encodeURIComponent(st.trip.id) + "/location-notes",
        { method: "POST", body: {
          note_text: text,
          note_title: (fTitle.value || "").trim() || null,
          trip_day_id: day.id,
          trip_region_id: day.trip_region_id || null,
          trip_stop_id: day.trip_stop_id || null,
          source_type: "operator",
        } })
        .then(function () { return Promise.all([reloadNotes(), reloadDays()]); })
        .then(function () {
          st.error = "";
          st.noteDrawerDayId = null;
          renderAll();
        })
        .catch(function (e) { st.error = e.message; renderAll(); });
    }));
    foot.appendChild(btn("tdl-btn", "Cancel", closeNoteDrawer));
    drawer.appendChild(foot);

    wrap.appendChild(drawer);
    return wrap;
  }

  // ── trip force-delete impact review (Phase 3A) ───────────────────────
  //
  // Follows the drawer idiom used by the note/source drawers: the input
  // elements are held in this closure and read on submit, so nothing here
  // repaints while the operator types and the confirmation field cannot
  // lose focus mid-word. The arm/disarm is done by touching the button's
  // .disabled directly for the same reason.
  function renderDeleteTripReview() {
    var review = st.deleteReview;
    var counts = (review && review.counts) || {};
    var wrap = el("div", "tdl-drawer-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeDeleteReview();
    });
    var drawer = el("aside", "tdl-drawer tdl-delete-drawer");

    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    ht.appendChild(el("div", "tdl-kicker", "Delete trip"));
    ht.appendChild(el("strong", "", review.tripTitle || "Untitled trip"));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn tdl-btn-small", "✕ Cancel", closeDeleteReview));
    drawer.appendChild(head);

    var body = el("div", "tdl-drawer-body");
    body.appendChild(el("p", "tdl-delete-warn",
      "This trip still holds evidence. Deleting it removes everything " +
      "listed below in one unrecoverable cascade. Photos themselves are " +
      "not deleted — only their links to this trip."));

    body.appendChild(el("div", "tdl-section-label", "What will be deleted"));
    var countsHost = el("div", "tdl-delete-counts");
    var seen = {};
    TRIP_DELETE_COUNT_LANES.forEach(function (c) {
      seen[c[0]] = true;
      var cell = el("div", "tdl-delete-count" +
        (Number(counts[c[0]] || 0) > 0 ? " tdl-delete-count-hot" : ""));
      cell.appendChild(el("strong", "", String(counts[c[0]] || 0)));
      cell.appendChild(el("span", "", c[1]));
      countsHost.appendChild(cell);
    });
    // A count lane the backend added and this list has not learned yet
    // must still be SHOWN, not silently dropped — an unlisted lane is
    // evidence the operator would destroy without ever being told about.
    Object.keys(counts).forEach(function (k) {
      if (seen[k]) return;
      var cell = el("div", "tdl-delete-count" +
        (Number(counts[k] || 0) > 0 ? " tdl-delete-count-hot" : ""));
      cell.appendChild(el("strong", "", String(counts[k] || 0)));
      cell.appendChild(el("span", "", k));
      countsHost.appendChild(cell);
    });
    body.appendChild(countsHost);

    var confirmInput = el("input");
    confirmInput.placeholder = review.tripTitle || review.tripId;
    var labConfirm = el("label", "tdl-label");
    labConfirm.appendChild(el("span", "",
      "Type the exact trip title (or its id) to confirm"));
    labConfirm.appendChild(confirmInput);
    body.appendChild(labConfirm);
    body.appendChild(el("p", "tdl-muted", "Trip id: " + review.tripId));

    var reasonInput = el("input");
    reasonInput.placeholder = "e.g. duplicate import";
    var labReason = el("label", "tdl-label");
    labReason.appendChild(el("span", "", "Reason (recorded in the audit log)"));
    labReason.appendChild(reasonInput);
    body.appendChild(labReason);

    var errEl = el("div", "tdl-delete-error", review.error || "");
    errEl.hidden = !review.error;
    body.appendChild(errEl);
    drawer.appendChild(body);

    var foot = el("div", "tdl-drawer-foot");
    var confirmBtn = btn("tdl-btn tdl-btn-danger", "Force delete trip",
      function () {
        if (confirmBtn.disabled) return;   // belt and braces
        confirmBtn.disabled = true;
        forceDeleteTrip(reasonInput.value);
      });
    // Armed ONLY by an exact match of the trip title (trim-compared) or
    // the trip id. Nothing looser — no case folding, no prefix, no
    // "contains". A blank field never arms.
    function refreshArm() {
      var typed = (confirmInput.value || "").trim();
      var armed = typed !== "" &&
        (typed === String(review.tripTitle || "").trim() ||
         typed === String(review.tripId));
      confirmBtn.disabled = !armed;
    }
    // Property assignment, not addEventListener: re-opening the review
    // for another trip can then never stack a stale handler closed over
    // the previous trip's id.
    confirmInput.oninput = refreshArm;
    refreshArm();
    foot.appendChild(confirmBtn);
    foot.appendChild(btn("tdl-btn", "Cancel", closeDeleteReview));
    drawer.appendChild(foot);

    wrap.appendChild(drawer);
    return wrap;
  }

  // ── Photos (mockup3) ─────────────────────────────────────────────────

  function linkNeedsReview(l) {
    return l.cluster_confidence !== null && l.cluster_confidence !== undefined &&
      Number(l.cluster_confidence) < 0.5 && l.assignment_method !== "operator";
  }

  function linkSharedWithLori(l) {
    return !!(l.caption_approved_for_lori || l.operator_context_approved_for_lori ||
      l.photo_date_approved_for_lori || l.photo_location_approved_for_lori);
  }

  var PHOTO_FILTERS = [
    ["all", "All"],
    ["unplaced", "Unplaced"],
    ["review", "Needs review"],
    ["lori", "Shared with Lori"],
  ];

  function filteredLinks() {
    return st.photoLinks.filter(function (l) {
      if (st.photoFilter === "unplaced") return !l.trip_stop_id;
      if (st.photoFilter === "review") return linkNeedsReview(l);
      if (st.photoFilter === "lori") return linkSharedWithLori(l);
      return true;
    });
  }

  // ── WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 Phase 1/2: photo evidence panel ──
  // Operator-only: OCR / public-lookup draft context + the approval ladder
  // (Draft -> Approve for Lori -> Include in memoir). All text is rendered
  // via el() (textContent) so OCR/lookup output can never inject markup.
  var photoEvidence = { linkId: null, loading: false, pc: [], pub: [], note: "",
                        lookupUrl: "", busy: null };

  function reloadPhotoEvidence() { photoEvidence.linkId = null; renderAll(); }

  function loadPhotoEvidence(linkId) {
    // The typed URL survives a RE-RENDER of the same photo, but must NOT
    // bleed onto a DIFFERENT photo — otherwise the operator can silently
    // attach the previous photo's public URL to the new selection.
    var sameLink = (photoEvidence.linkId === linkId);
    photoEvidence = { linkId: linkId, loading: true, pc: [], pub: [],
                      note: photoEvidence.note, busy: photoEvidence.busy,
                      lookupUrl: sameLink ? (photoEvidence.lookupUrl || "") : "" };
    var t = encodeURIComponent(st.trip.id);
    var lid = encodeURIComponent(linkId);
    Promise.all([
      api("/api/trips/photo-links/" + lid + "/photo-context")
        .catch(function () { return { photo_context: [] }; }),
      api("/api/trips/" + t + "/public-context?photo_link_id=" + lid)
        .catch(function () { return { public_context: [] }; }),
    ]).then(function (res) {
      if (photoEvidence.linkId !== linkId) return;   // superseded
      photoEvidence.pc = (res[0] && res[0].photo_context) || [];
      photoEvidence.pub = (res[1] && res[1].public_context) || [];
      photoEvidence.loading = false;
      renderAll();
    });
  }

  function evidenceAction(path, label, body) {
    // LIVE (2026-07-13): OCR took 7-19s on a full-res photo with NO feedback —
    // the button looked dead and invited double-clicks. Show a busy state and
    // lock the actions until it returns.
    photoEvidence.busy = label;
    photoEvidence.note = label + " running… (a full-size photo can take a few "
      + "seconds)";
    renderAll();
    api(path, { method: "POST", body: body || {} }).then(function (out) {
      photoEvidence.busy = null;
      photoEvidence.note = label + ": " + (out.status || "done")
        + (out.message ? " — " + out.message : "");
      refreshAfterEvidence();
    }).catch(function (e) {
      photoEvidence.busy = null;
      photoEvidence.note = label + " failed: " + e.message; renderAll();
    });
  }

  function evBadge(text, on) {
    return el("span", "tdl-ev-badge " + (on ? "tdl-ev-on" : "tdl-ev-off"), text);
  }

  // Send the active trip_id as a scope guard so a stale panel row can't patch
  // another trip's evidence (backend returns 409 on mismatch).
  function _tripScopeQ() {
    return st.trip ? ("?trip_id=" + encodeURIComponent(st.trip.id)) : "";
  }
  function patchPhotoContext(id, body) {
    api("/api/trips/photo-context/" + encodeURIComponent(id) + _tripScopeQ(),
        { method: "PATCH", body: body })
      .then(refreshAfterEvidence)
      .catch(function (e) { photoEvidence.note = e.message; renderAll(); });
  }
  function patchPublicContext(id, body) {
    api("/api/trips/public-context/" + encodeURIComponent(id) + _tripScopeQ(),
        { method: "PATCH", body: body })
      .then(refreshAfterEvidence)
      .catch(function (e) { photoEvidence.note = e.message; renderAll(); });
  }

  // In-panel evidence editor (replaces native window.prompt — Lab doctrine:
  // NO browser-native dialogs). One state, three modes: add draft observation,
  // infer place from context, edit an existing row's text. Keystrokes persist
  // into ed.value so an async re-render doesn't wipe what the operator typed.
  function openEvidenceEditor(ed) { photoEvidence.editor = ed; renderAll(); }
  function closeEvidenceEditor() { photoEvidence.editor = null; renderAll(); }

  function renderEvidenceEditor() {
    var ed = photoEvidence.editor;
    var wrap = el("div", "tdl-ev-editor");
    wrap.appendChild(el("div", "tdl-ev-editor-title", ed.title));
    if (ed.hint) wrap.appendChild(el("div", "tdl-muted tdl-ev-editor-hint", ed.hint));
    var ta = document.createElement("textarea");
    ta.className = "tdl-ev-editor-input";
    ta.rows = 3;
    ta.value = ed.value || "";
    ta.placeholder = ed.placeholder || "";
    ta.oninput = function () { ed.value = ta.value; };  // survive re-render
    wrap.appendChild(ta);
    var row = el("div", "tdl-ev-editor-actions");
    row.appendChild(btn("tdl-btn tdl-btn-primary", ed.saveLabel || "Save",
      function () {
        var t = (ed.value || ta.value || "").trim();
        photoEvidence.editor = null;
        if (t) { ed.save(t); } else { renderAll(); }
      }));
    row.appendChild(btn("tdl-btn", "Cancel", closeEvidenceEditor));
    wrap.appendChild(row);
    return wrap;
  }

  // WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11): friendlier
  // row-type labels + Lori-wording preview so the operator sees exactly
  // what Lori will treat as "draft" vs "fact" per evidence type.
  function evLabel(r, isPublic) {
    var approved = !!r.approved_for_lori;
    var ct = isPublic ? (r.source_type || "context")
                      : (r.context_type || "context");
    var map = {
      ocr_text: "OCR draft",
      vision_description: "Image context (vision)",
      draft_observation: "Photo observation",
      filename_context: "Filename hint",
      operator_photo_context: "Operator note",
      place_context: "Place from context",
      public_web_context: "Public web context",
      reverse_geocode: "Reverse geocode",
      calendar_context: "Calendar context",
      food_context: "Food context",
    };
    var base = map[ct] || ct;
    return base + (approved ? "" : " (draft)");
  }

  // Operator-visible "Lori will say…" preview. Uses the exact wording
  // shape encoded in travel_doc_lori_modal.answer_modal_direct_question
  // so what the operator sees here matches what the modal produces.
  function evLoriWording(r, isPublic) {
    var approved = !!r.approved_for_lori;
    var s = (r.result_summary || "").trim();
    if (!s) return "";
    var stripDot = s.replace(/\.+$/, "");
    var ct = isPublic ? (r.source_type || "") : (r.context_type || "");
    if (r.rejected) return "Rejected — Lori will not see this row.";
    // The modal direct-answer path trims spoken vision / observation / place /
    // public context (travel_doc_lori_modal._spoken_context_trim), so the
    // preview must trim the same classes or it lies about what Lori says. OCR
    // is spoken untrimmed on both sides.
    var spoken = spokenContextTrim(stripDot);
    if (isPublic && ct === "place_context") {
      return approved
        ? ("Lori will say: The approved place context says: " + spoken + ".")
        : ("Lori will say: the place context suggests " + spoken + ".");
    }
    if (ct === "ocr_text") {
      return approved
        ? ("Lori will say: The approved OCR text says: " + stripDot + ".")
        : ("Lori will say: the OCR draft appears to read '" + stripDot + "'.");
    }
    if (ct === "vision_description") {
      return approved
        ? ("Lori will say: The approved image-context note says: "
           + spoken + ".")
        : ("Lori will say: the draft image context suggests "
           + spoken + ".");
    }
    if (ct === "draft_observation") {
      return approved
        ? ("Lori will say: The approved photo observation says: "
           + spoken + ".")
        : ("Lori will say: the draft photo observation suggests "
           + spoken + ".");
    }
    // Fallback for less-common types — still safe to preview (trimmed).
    return approved
      ? ("Lori will speak this as approved context: " + spoken + ".")
      : ("Lori will treat this as draft (never fact): " + spoken + ".");
  }

  function renderEvidenceRow(r, isPublic) {
    var row = el("div", "tdl-ev-row");
    var head = el("div", "tdl-ev-head");
    head.appendChild(el("span", "tdl-ev-type",
      evLabel(r, isPublic)
        + (!isPublic && r.engine ? (" · " + r.engine) : "")));
    var badges = el("span", "tdl-ev-badges");
    badges.appendChild(evBadge("Draft", !r.approved_for_lori && !r.rejected));
    badges.appendChild(evBadge("Approved for Lori", !!r.approved_for_lori));
    badges.appendChild(evBadge("In memoir", !!r.include_in_memoir));
    if (r.rejected) badges.appendChild(evBadge("Rejected", true));
    head.appendChild(badges);
    row.appendChild(head);
    row.appendChild(el("div", "tdl-ev-summary", r.result_summary || ""));
    // Wording preview — mirrors the modal contract.
    var wording = evLoriWording(r, isPublic);
    if (wording) {
      row.appendChild(el("div", "tdl-ev-wording tdl-muted", wording));
    }
    if (r.source_url) row.appendChild(el("div", "tdl-ev-src", r.source_url));
    var ctrls = el("div", "tdl-ev-ctrls");
    var patch = isPublic ? patchPublicContext : patchPhotoContext;
    // Edit text — backend PATCH result_summary REVOKES approval + clears memoir
    // inclusion (edit-revokes-approval doctrine). Live testing already depends
    // on that; the Lab should make it reachable. OCR text is editable too — an
    // operator can hand-correct a noisy read.
    ctrls.appendChild(btn("tdl-btn tdl-btn-small", "Edit text", function () {
      openEvidenceEditor({
        mode: "edit",
        title: "Edit evidence text",
        hint: "Saving revokes approval and removes it from the memoir until you "
          + "approve again. Stays draft.",
        value: r.result_summary || "",
        saveLabel: "Save (revokes approval)",
        save: function (t) { patch(r.id, { result_summary: t }); },
      });
    }));
    ctrls.appendChild(btn("tdl-btn tdl-btn-small",
      r.approved_for_lori ? "Unapprove" : "Approve for Lori",
      function () { patch(r.id, { approved_for_lori: !r.approved_for_lori }); }));
    if (r.approved_for_lori) {
      ctrls.appendChild(btn("tdl-btn tdl-btn-small",
        r.include_in_memoir ? "Remove from memoir" : "Include in memoir",
        function () { patch(r.id, { include_in_memoir: !r.include_in_memoir }); }));
    }
    // Preflight review-follow-up (2026-07-11): public-context rows
    // also get Reject / Hide (migration 0032 added trip_public_context
    // .rejected). Hide-don't-delete parity across both lanes.
    ctrls.appendChild(btn("tdl-btn tdl-btn-small",
      r.rejected ? "Unreject" : "Reject / Hide",
      function () { patch(r.id, { rejected: !r.rejected }); }));
    row.appendChild(ctrls);
    return row;
  }

  function renderPhotoEvidence(sel) {
    var box = el("div", "tdl-evidence");
    if (photoEvidence.busy) box.classList.add("tdl-ev-busy");
    box.appendChild(el("h4", "", "Photo evidence — draft until you approve"));
    var acts = el("div", "tdl-ev-actions");
    acts.appendChild(btn("tdl-btn", "🔎 Run OCR", function () {
      evidenceAction("/api/trips/photo-links/"
        + encodeURIComponent(sel.id) + "/ocr", "OCR");
    }));
    // Operator-entry lane for a drafted photo observation. In-panel editor
    // (Lab doctrine: NO native window.prompt).
    acts.appendChild(btn("tdl-btn", "✍ Add draft observation", function () {
      openEvidenceEditor({
        mode: "draft_observation",
        title: "Draft photo observation",
        hint: "What does the photo show? Stays DRAFT — it won't reach narrator "
          + "Lori until you approve it.",
        placeholder: "e.g. A stone church with twin spires; a river in the "
          + "foreground.",
        value: "",
        saveLabel: "Save draft",
        save: function (t) {
          evidenceAction("/api/trips/photo-links/"
            + encodeURIComponent(sel.id) + "/draft-observation",
            "Draft observation",
            { result_summary: t, engine: "operator_local" });
        },
      });
    }));
    // Operator's place inference rooted in already-reviewable evidence (OCR /
    // public context / operator labels / trip structure). Never consumes raw
    // GPS. Stored as DRAFT trip_public_context row. In-panel editor.
    acts.appendChild(btn("tdl-btn", "📍 Infer place from context", function () {
      openEvidenceEditor({
        mode: "place_from_context",
        title: "Place from context",
        hint: "Based on OCR, public context, trip labels, or operator place "
          + "notes. Stays DRAFT and never uses raw GPS.",
        placeholder: "e.g. Munich, near the old town",
        value: "",
        saveLabel: "Save draft",
        save: function (t) {
          evidenceAction("/api/trips/photo-links/"
            + encodeURIComponent(sel.id) + "/place-from-context",
            "Place from context",
            { result_summary: t,
              evidence_sources: ["ocr", "public_context", "trip_labels"] });
        },
      });
    }));
    // LIVE-TEST FIX (2026-07-13): this button used to post NO url. With the
    // url_only provider (which fetches the exact page the operator supplies)
    // that ALWAYS failed with "url_only provider requires a url" — the button
    // could never work. Give it a real URL field.
    var urlIn = el("input");
    urlIn.type = "url";
    urlIn.className = "tdl-ev-url";
    urlIn.placeholder = "Paste a public URL (Wikipedia, museum site)…";
    urlIn.value = photoEvidence.lookupUrl || "";
    urlIn.addEventListener("input", function () {
      photoEvidence.lookupUrl = urlIn.value;   // survive the re-render
    });
    acts.appendChild(urlIn);
    acts.appendChild(btn("tdl-btn", "🌐 Lookup public context", function () {
      var u = (photoEvidence.lookupUrl || "").trim();
      if (!u) {
        photoEvidence.note = "Paste a public URL first — the url_only provider "
          + "fetches the exact page you give it (there is no web search yet).";
        renderAll();
        return;
      }
      evidenceAction("/api/trips/photo-links/"
        + encodeURIComponent(sel.id) + "/lookup-context", "Lookup",
        { source_type: "place_context", url: u });
    }));
    box.appendChild(acts);
    // In-panel editor drawer (Add draft observation / Infer place / Edit text).
    if (photoEvidence.editor) {
      box.appendChild(renderEvidenceEditor());
    }
    if (photoEvidence.note) {
      box.appendChild(el("p", "tdl-ev-note", photoEvidence.note));
    }
    if (photoEvidence.linkId !== sel.id) {
      loadPhotoEvidence(sel.id);
      box.appendChild(el("p", "tdl-muted", "Loading evidence…"));
      return box;
    }
    if (photoEvidence.loading) {
      box.appendChild(el("p", "tdl-muted", "Loading evidence…"));
      return box;
    }
    if (!photoEvidence.pc.length) {
      box.appendChild(el("p", "tdl-muted",
        "No OCR / image-context draft yet — Run OCR to extract sign/label text."));
    }
    photoEvidence.pc.forEach(function (r) {
      box.appendChild(renderEvidenceRow(r, false));
    });
    if (photoEvidence.pub.length) {
      box.appendChild(el("h5", "", "Public context (this photo)"));
      photoEvidence.pub.forEach(function (r) {
        box.appendChild(renderEvidenceRow(r, true));
      });
    }
    return box;
  }

  // ── Photo lightbox (LIVE-TEST UX FIX 2026-07-13) ──────────────────────
  // On any laptop (<1500px) .tdl-photo-workspace collapses and the photo
  // detail becomes a FULL-WIDTH ROW BELOW the gallery — so choosing a photo
  // meant scrolling past a giant image to reach the evidence panel, which is
  // the actual work. The detail also rendered the THUMBNAIL, so you could not
  // read a menu you were about to OCR. The lightbox puts a full-resolution
  // image and the evidence panel side by side at ANY width, with prev/next,
  // arrow keys and Esc.
  var lightbox = { open: false };

  function fullImageUrl(photoId) {
    return st.apiBase + "/api/photos/" + encodeURIComponent(photoId) + "/image";
  }

  function openLightbox(linkId) {
    lightbox.open = true;
    st.selectedPhotoLinkId = linkId;
    renderAll();
  }
  function closeLightbox() { lightbox.open = false; renderAll(); }

  function lightboxStep(delta) {
    var links = filteredLinks();
    var i = -1;
    links.forEach(function (l, n) { if (l.id === st.selectedPhotoLinkId) i = n; });
    if (i < 0 || !links.length) return;
    st.selectedPhotoLinkId = links[(i + delta + links.length) % links.length].id;
    renderAll();
  }

  // Phase 1.1 — this is the only listener in the file bound OUTSIDE the
  // host element, so it is the only one clearing the host does not take
  // with it. Left attached it would outlive the mount forever: two mounts
  // means two live listeners on `document`, and after destroy() an arrow
  // key would still drive lightboxStep() -> renderAll() on a dead mount.
  // Held in a named ref so destroy() can remove it; guarded as well,
  // because removeEventListener does not retract an event already queued.
  function onDocKeydown(e) {
    if (destroyed) return;
    if (!lightbox.open) return;
    if (e.key === "Escape") { e.preventDefault(); closeLightbox(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); lightboxStep(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); lightboxStep(1); }
  }
  document.addEventListener("keydown", onDocKeydown);

  function renderLightbox() {
    var links = filteredLinks();
    var sel = links.filter(function (l) {
      return l.id === st.selectedPhotoLinkId;
    })[0];
    if (!sel) return null;
    var idx = 0;
    links.forEach(function (l, n) { if (l.id === sel.id) idx = n; });

    var ov = el("div", "tdl-lightbox");
    ov.addEventListener("click", function (e) {
      if (e.target === ov) closeLightbox();
    });
    var panel = el("div", "tdl-lb-panel");

    var head = el("div", "tdl-lb-head");
    head.appendChild(el("span", "tdl-lb-count",
      (idx + 1) + " of " + links.length));
    var stop = sel.trip_stop_id && findStop(sel.trip_stop_id);
    var region = sel.trip_region_id && findRegion(sel.trip_region_id);
    head.appendChild(el("span", "tdl-lb-title",
      (stop && stop.location_name) || (region && region.title) || "Unplaced"));
    head.appendChild(el("span", "tdl-lb-date",
      "Taken " + (linkTakenDate(sel) || "unknown")));
    head.appendChild(btn("tdl-btn tdl-btn-small tdl-lb-close", "✕ Close",
      closeLightbox));
    panel.appendChild(head);

    var body = el("div", "tdl-lb-body");

    var imgWrap = el("div", "tdl-lb-img");
    imgWrap.appendChild(btn("tdl-lb-nav tdl-lb-prev", "‹",
      function () { lightboxStep(-1); }));
    var im = document.createElement("img");
    im.src = fullImageUrl(sel.photo_id);   // FULL image, not the thumbnail
    im.alt = "trip photo";
    imgWrap.appendChild(im);
    imgWrap.appendChild(btn("tdl-lb-nav tdl-lb-next", "›",
      function () { lightboxStep(1); }));
    body.appendChild(imgWrap);

    var side = el("div", "tdl-lb-side");
    side.appendChild(btn("tdl-btn tdl-btn-gold",
      "💬 Talk with Lori about this photo", function () {
        closeLightbox();
        openLoriOverlayForPhoto(sel.id);
      }));
    side.appendChild(renderPhotoEvidence(sel));   // same panel, no duplicate logic
    body.appendChild(side);

    panel.appendChild(body);
    ov.appendChild(panel);
    return ov;
  }

  function renderPhotos() {
    var wrap = el("div");
    wrap.appendChild(el("h1", "", "Photo Story"));
    // Phase 3C — intake lives above the gallery, because the answer to
    // "there are no photos here" has to be reachable from the empty state.
    wrap.appendChild(renderPhotoIntakeBar());
    if (st.photoIntake) {
      wrap.appendChild(renderIntakeResult(st.photoIntake, function () {
        st.photoIntake = null; renderAll();
      }));
    }
    var ws = el("div", "tdl-photo-workspace");

    var rail = el("div", "tdl-filter-rail");
    PHOTO_FILTERS.forEach(function (f) {
      var n = st.photoLinks.filter(function (l) {
        if (f[0] === "unplaced") return !l.trip_stop_id;
        if (f[0] === "review") return linkNeedsReview(l);
        if (f[0] === "lori") return linkSharedWithLori(l);
        return true;
      }).length;
      rail.appendChild(btn(st.photoFilter === f[0] ? "tdl-active" : "",
        f[1] + " (" + n + ")", function () { st.photoFilter = f[0]; renderAll(); }));
    });
    ws.appendChild(rail);

    var gallery = el("div", "tdl-gallery");
    var links = filteredLinks();
    if (!links.length) gallery.appendChild(el("div", "tdl-empty", "No photos in this filter."));
    links.forEach(function (l) {
      var cell = btn("tdl-ph" + (st.selectedPhotoLinkId === l.id ? " tdl-selected" : ""), "",
        function () { openLightbox(l.id); });
      var im = thumbImg(l.photo_id, l.caption, true);
      cell.appendChild(im);
      cell.appendChild(el("span", "tdl-ph-date", linkTakenDate(l) || "undated"));
      gallery.appendChild(cell);
    });
    ws.appendChild(gallery);

    var sel = st.photoLinks.filter(function (l) {
      return l.id === st.selectedPhotoLinkId;
    })[0];
    var detail = el("div", "tdl-photo-detail");
    if (!sel) {
      detail.appendChild(el("p", "tdl-muted", "Select a photo to see its details."));
    } else {
      var big = thumbImg(sel.photo_id, sel.caption, false);
      detail.appendChild(big);
      var stop = sel.trip_stop_id && findStop(sel.trip_stop_id);
      var region = sel.trip_region_id && findRegion(sel.trip_region_id);
      detail.appendChild(el("h3", "", (stop && stop.location_name) ||
        (region && region.title) || "Unplaced"));
      detail.appendChild(el("p", "tdl-muted",
        "Taken: " + (linkTakenDate(sel) || "unknown") +
        " · date source: " + (sel.photo_date_source || "n/a") +
        " · method: " + (sel.assignment_method || "?") +
        " · confidence: " + (sel.cluster_confidence == null ? "?" : sel.cluster_confidence)));
      if (sel.trip_day_id) {
        var linkedDay = dayById(sel.trip_day_id);
        detail.appendChild(el("p", "",
          "Attached to " + (linkedDay ? dayChipText(linkedDay) : "a day card")));
      }
      if (sel.caption) detail.appendChild(el("p", "", "Caption: " + sel.caption));
      if (sel.narrator_caption) {
        detail.appendChild(el("p", "", "Narrator caption: " + sel.narrator_caption));
      }
      if (sel.operator_context_note) {
        detail.appendChild(el("p", "", "Operator note: " + sel.operator_context_note));
      }
      // Approval flags — read-only in the lab (approvals stay a
      // deliberate production-surface action).
      [["Caption → Lori", sel.caption_approved_for_lori],
        ["Note → Lori", sel.operator_context_approved_for_lori],
        ["Date → Lori", sel.photo_date_approved_for_lori],
        ["Place → Lori", sel.photo_location_approved_for_lori],
        // Two-surface doctrine (2026-07-10, locked): Travel Doc is the
        // EVIDENCE-RICH operator surface — GPS presence is advertised as
        // usable context here. "(private)" is narrator-room language and
        // is banned on this surface.
        ["GPS found — available for Travel Doc context", sel.photo_gps_present]].forEach(function (f) {
        var row = el("div", "tdl-flag-row");
        row.appendChild(el("span", "", f[0]));
        row.appendChild(el("span", f[1] ? "tdl-flag-on" : "tdl-flag-off",
          f[1] ? "ON" : "off"));
        detail.appendChild(row);
      });
      if (linkNeedsReview(sel)) {
        detail.appendChild(el("span", "tdl-needs-review", "needs review"));
      }
      detail.appendChild(btn("tdl-btn tdl-btn-gold",
        "💬 Talk with Lori about this photo", function () {
          // SAME in-context overlay drawer the day cards use — never
          // tab navigation away from the photo the operator is on.
          openLoriOverlayForPhoto(sel.id);
        }));
      if (!lightbox.open) detail.appendChild(renderPhotoEvidence(sel));
    }
    ws.appendChild(detail);
    wrap.appendChild(ws);
    if (lightbox.open) {
      var lb = renderLightbox();
      if (lb) wrap.appendChild(lb);
    }
    return wrap;
  }

  // ── Evidence lifecycle (WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01) ─────────
  // Removing a note/source from view is a reversible HIDE — a PATCH
  // {hidden:true} — never a DELETE. (Phase 3A narrowed the blanket
  // "the Lab never DELETEs" posture to exactly one sanctioned path: the
  // gated trip force-delete above. Every EVIDENCE lane — notes, sources,
  // photo context, public context — is still hide-only, and the tests
  // pin that.) Restore is PATCH {hidden:false}. The server excludes
  // hidden rows from list responses (unless include_hidden=1) and from
  // evidence assembly, so the Draft tab needs no change.

  function hideNote(noteId) {
    api("/api/trips/location-notes/" + encodeURIComponent(noteId),
      { method: "PATCH", body: { hidden: true } })
      .then(function () { return reloadNotes(); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function restoreNote(noteId) {
    api("/api/trips/location-notes/" + encodeURIComponent(noteId),
      { method: "PATCH", body: { hidden: false } })
      .then(function () { return reloadNotes(); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function hideSource(sourceId) {
    api("/api/trips/sources/" + encodeURIComponent(sourceId),
      { method: "PATCH", body: { hidden: true } })
      .then(function () { return reloadSources(); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  function restoreSource(sourceId) {
    api("/api/trips/sources/" + encodeURIComponent(sourceId),
      { method: "PATCH", body: { hidden: false } })
      .then(function () { return reloadSources(); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
  }

  // Per-tab Show-hidden toggle row. The count is only knowable while
  // hidden rows are actually loaded (toggle on) — the default fetch
  // excludes them by contract. Click-driven fetch only (no fetch from
  // render — same auto-load-loop caution as the Draft tab's
  // previewTried flag, solved here by never fetching during render).
  function hiddenToggleRow(flagName, hiddenCount, kindLabel) {
    var row = el("div", "tdl-hidden-toggle-row");
    var on = !!st[flagName];
    row.appendChild(btn("tdl-btn tdl-btn-small" + (on ? " tdl-active" : ""),
      on ? "Show hidden (" + hiddenCount + ") ✓" : "Show hidden",
      function () {
        st[flagName] = !st[flagName];
        var reload = (flagName === "showHiddenNotes") ?
          reloadNotes : reloadSources;
        reload()
          .then(function () { st.error = ""; renderAll(); })
          .catch(function (e) { st.error = e.message; renderAll(); });
      }));
    if (on) {
      row.appendChild(el("span", "tdl-muted",
        "Hidden " + kindLabel + " render dimmed — Restore brings one back."));
    }
    return row;
  }

  // ── Evidence Review Queue ────────────────────────────────────────────
  //
  // WO-TRAVEL-DOC-EVIDENCE-REVIEW-QUEUE-01 Phase 2, the screen.
  //
  // Phase 1 shipped GET /queue (the read a review screen is built on) and
  // Phase 3 shipped POST /candidates/{id}/promote (the write that makes
  // 'accepted' reachable at all). This tab is the operator surface over
  // both, and it is the first thing in this file to call anything outside
  // /api/trips. That widening is deliberate, not incidental: the
  // sanctioned-endpoint gate in tests/test_travel_doc_lab.py had to be
  // edited to allow it, which is exactly what that gate is for.
  //
  // Three closed decisions shape what is NOT here:
  //
  //   1. Placement is trip granularity. No region, stop or day control on
  //      any row, because the import tables have no column to hold one.
  //      "File to trip" is the whole of placement, and it is reversible.
  //   2. The states are the five that shipped in migration 0037 --
  //      pending, accepted, rejected, duplicate, error. The filter rail
  //      offers exactly those and this screen invents no others.
  //   3. Promotion is an explicit separate call, never a flag on the
  //      decision. So "Promote + accept" is TWO requests in sequence, the
  //      drawer says so, and the halfway state (promoted, still pending)
  //      is reported in those words when it happens -- because it is
  //      reachable, it is recoverable, and the retry is safe.
  //
  // Deliberately absent: no Takeout, no Lori control, nothing
  // narrator-facing, and no DELETE. Retirement is Hide, the same as every
  // other evidence lane in this workspace.
  //
  // Corrected 2026-07-28 by WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase
  // 2D, which added the Google Photos Picker import strip further down
  // this same section. This line read "Deliberately absent: no Google
  // Picker, no Takeout, ..." from the queue's own phase, when the picker
  // was the next epic step rather than this one. THE REST OF THE
  // SENTENCE IS UNCHANGED AND IS NOT WEAKENED BY THE PICKER'S ARRIVAL:
  // the strip opens a session, checks it, ingests it and reloads this
  // queue, and that is the whole of it. It writes PENDING candidates and
  // nothing else -- it takes no decision, creates no `photos` row, sets
  // no narrator-facing field, and surfaces no DELETE (including the
  // lane's one safe one, which only releases a session at Google). Every
  // candidate it produces is decided on the rows below, by the same seven
  // actions as every other candidate in the queue.

  var EVIDENCE_BASE = "/api/import-provenance";

  // The five states, plus an unfiltered view. Order is the order a
  // reviewer reads them in, not alphabetical.
  var EVIDENCE_STATES = [
    ["", "All"],
    ["pending", "Pending"],
    ["accepted", "Accepted"],
    ["rejected", "Rejected"],
    ["duplicate", "Duplicate"],
    ["error", "Error"],
  ];

  // The decisions an operator can record WITHOUT a photo. 'accepted' is
  // deliberately not in this list: it requires the photo_id of a row that
  // already exists, so it goes through the promote drawer instead.
  var EVIDENCE_REFUSALS = [
    ["rejected", "Reject", "not evidence for this trip"],
    ["duplicate", "Duplicate", "already in the archive"],
    ["error", "Error", "could not be imported"],
  ];

  function evidenceCandidates() {
    return (st.evidence && st.evidence.candidates) || [];
  }

  function evidenceCandidatePath(candidateId) {
    return EVIDENCE_BASE + "/candidates/" + encodeURIComponent(candidateId);
  }

  function candidateName(c) {
    return c.filename || c.external_id ||
      ("candidate " + String(c.id || "").slice(0, 8));
  }

  // person_id is required by the route and is not defaulted anywhere,
  // here or there. A queue that inferred its person would be one bad
  // inference away from showing a reviewer someone else's evidence.
  function evidenceQueryPath() {
    var q = "?person_id=" + encodeURIComponent(st.personId);
    if (st.evidenceScope === "trip" && st.trip) {
      q += "&trip_id=" + encodeURIComponent(st.trip.id);
    }
    if (st.evidenceState) {
      q += "&state=" + encodeURIComponent(st.evidenceState);
    }
    if (st.showHiddenEvidence) q += "&include_hidden=1";
    return EVIDENCE_BASE + "/queue" + q;
  }

  // Never rejects. Callers repaint unconditionally, so a failure has to
  // land on st rather than in an unhandled rejection.
  function reloadEvidence() {
    if (!st.personId) return Promise.resolve();
    st.evidenceBusy = true;
    return api(evidenceQueryPath())
      .then(function (out) {
        st.evidence = out;
        st.evidenceOff = false;
        st.evidenceError = "";
        st.evidenceBusy = false;
      })
      .catch(function (e) {
        st.evidenceBusy = false;
        if (e && e.status === 404) {
          // The whole lane is behind a default-off server flag and every
          // route in it answers 404 while that flag is off. Reporting
          // that as an error would send the operator looking for a broken
          // trip; it renders as its own explanatory panel instead.
          st.evidenceOff = true;
          st.evidence = null;
          st.evidenceError = "";
          return;
        }
        st.evidenceError = e.message;
      });
  }

  function setEvidenceScope(scope) {
    if (st.evidenceScope === scope) return;
    st.evidenceScope = scope;
    reloadEvidence().then(function () { renderAll(); });
  }

  function setEvidenceState(state) {
    if (st.evidenceState === state) return;
    st.evidenceState = state;
    reloadEvidence().then(function () { renderAll(); });
  }

  // Hide is retirement from a view. The candidate row, its match reason
  // and its decision all survive -- there is no DELETE in this lane and
  // this screen does not add one.
  function setEvidenceHidden(candidateId, hidden) {
    api(evidenceCandidatePath(candidateId) + "/hidden",
        { method: "PATCH", body: { hidden: !!hidden } })
      .then(function () { return reloadEvidence(); })
      .then(function () { renderAll(); })
      .catch(function (e) { st.evidenceError = e.message; renderAll(); });
  }

  // ── the queue screen ─────────────────────────────────────────────────

  function renderEvidence() {
    var wrap = el("div", "tdl-erq");
    wrap.appendChild(el("h1", "", "Evidence Review Queue"));
    wrap.appendChild(el("p", "tdl-muted",
      "Imported candidates waiting on an operator. Nothing on this screen " +
      "is narrator-facing and nothing on it approves anything for Lori: " +
      "promoting a candidate creates the photo, accepting records that the " +
      "promotion happened, and the photo stays unapproved either way."));

    if (!st.personId) {
      wrap.appendChild(el("div", "tdl-empty",
        "No narrator is selected, and this queue is per person."));
      return wrap;
    }
    if (st.evidenceOff) {
      wrap.appendChild(el("div", "tdl-erq-off",
        "The import provenance lane is switched off on this server, so " +
        "there is no queue to read — every route in it answers 404 while " +
        "the flag is off. Nothing is broken and nothing is lost."));
      return wrap;
    }

    // Phase 2D -- the import affordance, ABOVE the queue and inside the
    // same screen. Binding ruling 1.3 of the travel-document doctrine
    // gives it no screen of its own, so this is where it lives. It is
    // rendered after the flag-off return on purpose: the picker needs
    // both server flags, so a queue that is off makes an import strip
    // meaningless rather than merely empty.
    wrap.appendChild(renderPickerStrip());

    // Scope. The queue is person-scoped; the trip is a FILTER on it, not
    // its subject. "All trips" is where unfiled candidates live, because
    // the route has no "trip is null" filter and this screen does not
    // invent one -- it counts them on the page and says so instead.
    var scopeRail = el("div", "tdl-filter-rail tdl-filter-rail-row");
    scopeRail.appendChild(btn(
      st.evidenceScope === "trip" ? "tdl-active" : "",
      "This trip", function () { setEvidenceScope("trip"); }));
    scopeRail.appendChild(btn(
      st.evidenceScope === "all" ? "tdl-active" : "",
      "All trips", function () { setEvidenceScope("all"); }));
    if (!st.trip) {
      scopeRail.appendChild(el("span", "tdl-muted",
        "No trip selected — showing every candidate for this narrator."));
    }
    wrap.appendChild(scopeRail);

    // The counts describe the whole queue behind the page and are NOT
    // narrowed by the state filter -- that is a documented property of
    // GET /queue, and it is why a reviewer standing in Pending can still
    // see how much has been accepted without changing the filter to find
    // out. Summing them is therefore the honest "All" count.
    var counts = (st.evidence && st.evidence.state_counts) || {};
    var allCount = 0;
    EVIDENCE_STATES.forEach(function (s) {
      if (s[0]) allCount += (counts[s[0]] || 0);
    });
    var stateRail = el("div", "tdl-filter-rail tdl-filter-rail-row");
    EVIDENCE_STATES.forEach(function (s) {
      var label = s[1] + " (" + (s[0] ? (counts[s[0]] || 0) : allCount) + ")";
      stateRail.appendChild(btn(
        st.evidenceState === s[0] ? "tdl-active" : "", label,
        function () { setEvidenceState(s[0]); }));
    });
    wrap.appendChild(stateRail);

    var summary = el("div", "tdl-erq-summary");
    if (st.evidence) {
      var unfiled = evidenceCandidates().filter(function (c) {
        return !c.trip;
      }).length;
      summary.appendChild(el("span", "tdl-badge tdl-erq-depth",
        "Queue depth " + (st.evidence.queue_depth || 0)));
      summary.appendChild(el("span", "tdl-muted",
        "Showing " + (st.evidence.returned || 0) + " of " +
        (st.evidence.total || 0) + " in this filter" +
        (unfiled ? " · " + unfiled + " on this page not filed to a trip"
                 : "")));
    }
    summary.appendChild(btn("tdl-btn tdl-btn-small", "↻ Refresh",
      function () { reloadEvidence().then(function () { renderAll(); }); }));
    wrap.appendChild(summary);

    // Click-driven fetch only, never from render.
    var hidRow = el("div", "tdl-hidden-toggle-row");
    hidRow.appendChild(btn("tdl-btn tdl-btn-small" +
      (st.showHiddenEvidence ? " tdl-active" : ""),
      st.showHiddenEvidence ? "Show hidden ✓" : "Show hidden",
      function () {
        st.showHiddenEvidence = !st.showHiddenEvidence;
        reloadEvidence().then(function () { renderAll(); });
      }));
    if (st.showHiddenEvidence) {
      hidRow.appendChild(el("span", "tdl-muted",
        "Hidden candidates — and candidates in a hidden batch — render " +
        "dimmed. Unhide brings one back; nothing was deleted."));
    }
    wrap.appendChild(hidRow);

    if (st.evidenceError) {
      wrap.appendChild(el("div", "tdl-error", st.evidenceError));
    }
    if (!st.evidence) {
      wrap.appendChild(el("div", "tdl-empty", st.evidenceBusy ?
        "Loading the queue…" : "Queue not loaded yet — use Refresh."));
      return wrap;
    }
    var rows = evidenceCandidates();
    if (!rows.length) {
      wrap.appendChild(el("div", "tdl-empty", "Nothing in this filter." +
        ((st.evidenceScope === "trip" && st.trip) ?
          " Candidates not yet filed to a trip only appear under All trips."
          : "")));
      return wrap;
    }
    rows.forEach(function (c) { wrap.appendChild(renderErqRow(c)); });
    return wrap;
  }

  // The importer's reasoning, printed as the keys and values it actually
  // stored. The repository round-trips match_reason unchanged and states
  // why -- "round-trip, never a summary, never prose" -- so a screen that
  // paraphrased it would be the summary that refusal exists to prevent.
  function renderMatchReason(c) {
    var box = el("div", "tdl-erq-reason");
    function line(k, v) {
      var d = el("div", "tdl-erq-reason-line");
      d.appendChild(el("span", "tdl-erq-reason-key", k));
      d.appendChild(el("span", "tdl-erq-reason-val", v));
      box.appendChild(d);
    }
    if (typeof c.match_confidence === "number") {
      line("match_confidence", String(c.match_confidence));
    }
    var mr = c.match_reason;
    var keys = (mr && typeof mr === "object") ? Object.keys(mr) : [];
    if (!keys.length) {
      box.appendChild(el("div", "tdl-muted", "No match reason recorded."));
      return box;
    }
    keys.forEach(function (k) {
      var v = mr[k];
      var text;
      if (v === null || v === undefined) text = "null";
      else if (typeof v === "string") text = v;
      else {
        try { text = JSON.stringify(v); } catch (_) { text = String(v); }
      }
      line(k, text);
    });
    return box;
  }

  function renderErqRow(c) {
    var row = el("div", "tdl-erq-row" + (c.hidden ? " tdl-row-hidden" : ""));
    var b = c.batch || {};

    var badges = el("div", "tdl-note-badges");
    badges.appendChild(el("span", "tdl-badge tdl-erq-state-badge",
      c.state || "pending"));
    badges.appendChild(el("span", "tdl-badge", "batch · " +
      (b.label || b.source || (b.id ? String(b.id).slice(0, 8) : "?"))));
    if (b.source) badges.appendChild(el("span", "tdl-badge", b.source));
    if (b.status && b.status !== "open") {
      badges.appendChild(el("span", "tdl-badge", "batch " + b.status));
    }
    badges.appendChild(el("span",
      "tdl-badge" + (c.trip ? "" : " tdl-badge-unfiled"),
      c.trip ? ("trip · " + (c.trip.title || "Untitled trip"))
             : "not filed to a trip"));
    if (c.photo_id) badges.appendChild(el("span", "tdl-badge", "promoted"));
    if (c.hidden) {
      badges.appendChild(el("span", "tdl-badge tdl-badge-hidden", "hidden"));
    }
    if (b.hidden) {
      badges.appendChild(el("span", "tdl-badge tdl-badge-hidden",
        "batch hidden"));
    }
    row.appendChild(badges);

    row.appendChild(el("strong", "", candidateName(c)));

    // Filename AND external id, both, when both exist. They answer
    // different questions -- what the operator called it and what the
    // provider called it -- and collapsing them loses one of the two.
    var idBits = [];
    if (c.filename) idBits.push("file " + c.filename);
    if (c.external_id) idBits.push("external id " + c.external_id);
    if (c.mime_type) idBits.push(c.mime_type);
    if (c.byte_size) idBits.push(String(c.byte_size) + " bytes");
    if (idBits.length) row.appendChild(el("p", "tdl-muted", idBits.join(" · ")));

    // The trip's date window sits next to the candidate's taken_at on
    // purpose: "does this fall inside the trip it is filed under" is the
    // single most common review question, and the queue returns the trip
    // dates so it can be answered without opening the trip.
    var when = [];
    if (c.taken_at) {
      when.push("taken " + datePrefix(c.taken_at) +
        " (" + (c.taken_at_source || "unknown") + ")");
    }
    if (c.trip && (c.trip.start_date || c.trip.end_date)) {
      when.push("trip window " + (c.trip.start_date || "?") + " → " +
        (c.trip.end_date || "?"));
    }
    if (when.length) row.appendChild(el("p", "tdl-muted", when.join(" · ")));

    row.appendChild(renderMatchReason(c));
    if (c.state_reason) {
      row.appendChild(el("p", "tdl-erq-state-reason", c.state_reason));
    }

    var acts = el("div", "tdl-erq-actions");
    if (c.hidden) {
      // A hidden row is already out of review. Offer the way back and
      // nothing else -- deciding a row the operator has retired from the
      // view is a decision taken half-blind.
      acts.appendChild(btn("tdl-btn tdl-btn-small", "Unhide",
        function () { setEvidenceHidden(c.id, false); }));
      row.appendChild(acts);
      return row;
    }
    if (c.state === "pending") {
      acts.appendChild(btn("tdl-btn tdl-btn-small tdl-btn-primary",
        c.photo_id ? "Accept (already promoted)" : "Promote + accept",
        function () { openEvidencePromoteDrawer(c); }));
      EVIDENCE_REFUSALS.forEach(function (r) {
        acts.appendChild(btn("tdl-btn tdl-btn-small", r[1], function () {
          openEvidenceDrawer("decide", c.id, r[0]);
        }));
      });
    } else {
      // Decided rows are not re-decidable from here, and that is a
      // refusal rather than an omission. Re-deciding an accepted
      // candidate clears its photo_id and strands the photos row it
      // pointed at, unreferenced. That cleanup is a photo-lane act on
      // the photo, not something to trigger by mis-clicking in a queue.
      acts.appendChild(el("span", "tdl-muted", "Decided" +
        (c.reviewed_at ? " " + datePrefix(c.reviewed_at) : "") +
        " — this screen does not re-open a decision."));
    }
    acts.appendChild(btn("tdl-btn tdl-btn-small", "File to trip",
      function () { openEvidenceDrawer("file", c.id); }));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Hide",
      function () { setEvidenceHidden(c.id, true); }));
    row.appendChild(acts);
    return row;
  }

  // ── the review drawers ───────────────────────────────────────────────

  function openEvidenceDrawer(kind, candidateId, state) {
    if (dayFormDirtyBlocks()) return;
    st.evidenceDrawer = {
      kind: kind,
      candidateId: candidateId,
      state: state || "",
      error: "",
    };
    renderAll();
  }

  // The promote drawer needs the trip's days before it paints, not
  // after. Two reasons, and the second is the hard one:
  //
  //  * a day list that arrives late would make the operator watch the
  //    control they came here to use appear underneath their cursor;
  //  * this drawer can hold an <input type=file>, whose FileList script
  //    cannot write, so a repaint after a file was chosen would silently
  //    drop it. Loading first means the drawer paints exactly once.
  //
  // A candidate that is not filed to a trip has no days to offer. That
  // is not an error -- it is the "File to trip" step not having been
  // done yet -- so the drawer opens and says so.
  function openEvidencePromoteDrawer(c) {
    if (dayFormDirtyBlocks()) return;
    var tripId = c.trip && c.trip.id;
    var d = {
      kind: "promote",
      candidateId: c.id,
      state: "",
      error: "",
      days: [],
      daysError: "",
      dayId: "",
      daysLoaded: !tripId,
    };
    st.evidenceDrawer = d;
    if (!tripId) { renderAll(); return; }
    api("/api/trips/" + encodeURIComponent(tripId) + "/days")
      .then(function (out) {
        d.days = (out && out.days) || [];
        d.dayId = suggestedDayIdFor(c, d.days);
      })
      .catch(function (e) {
        d.daysError = e.message || String(e);
      })
      .then(function () {
        d.daysLoaded = true;
        // Only paint if this is still the drawer the operator is in.
        if (st.evidenceDrawer === d) renderAll();
      });
  }

  // The date on the photo, offered as a SUGGESTION and nothing more.
  // Returns "" when nothing matches, so the operator is asked rather
  // than given a silent default. Never used to file anything on its
  // own: the value only ever preselects a control the operator can
  // change, and the drawer says in words that it is a guess.
  function suggestedDayIdFor(c, days) {
    var taken = c && c.taken_at ? datePrefix(c.taken_at) : "";
    if (!taken) return "";
    var hit = (days || []).filter(function (day) {
      return day && day.date && String(day.date).slice(0, 10) === taken;
    })[0];
    return hit ? String(hit.id) : "";
  }

  function closeEvidenceDrawer() { st.evidenceDrawer = null; renderAll(); }

  function evidenceDrawerCandidate() {
    var d = st.evidenceDrawer;
    if (!d) return null;
    return evidenceCandidates().filter(function (c) {
      return String(c.id) === String(d.candidateId);
    })[0] || null;
  }

  function renderEvidenceDrawer() {
    var d = st.evidenceDrawer;
    var c = evidenceDrawerCandidate();
    if (!c) {
      // The row left the page under the open drawer (a filter change, a
      // reload after someone else decided it). Say so rather than acting
      // on an id this screen can no longer show the operator.
      var sh = drawerShell("Evidence review",
        "That candidate is no longer on this page", closeEvidenceDrawer,
        "tdl-edit-drawer tdl-erq-drawer");
      sh.body.appendChild(el("p", "tdl-muted",
        "Nothing was changed. Close this and find it again with the " +
        "filters above."));
      return sh.wrap;
    }
    if (d.kind === "promote") return renderEvidencePromoteDrawer(d, c);
    if (d.kind === "file") return renderEvidenceFileDrawer(d, c);
    return renderEvidenceDecideDrawer(d, c);
  }

  // Build points 1-4 walked from the client side. Promote hands back a
  // photo_id and leaves the candidate pending; the EXISTING decision
  // route is what accepts, using that photo_id. Nothing here invents a
  // photo_id and nothing here approves anything.
  //
  // 2026-07-29 — a third act was added at the end: filing the photo on
  // the day the operator chose. The order is deliberate and is the
  // order of the sentence the operator read: get the picture, record
  // the decision, put it on the day. Each step is idempotent, so a
  // failure anywhere is a retry rather than a repair — promotion
  // answers with the same photo, the decision refuses a second time
  // rather than duplicating, and the day link is keyed on the trip and
  // the photo so filing it twice files it once.
  //
  // Same file-input constraint as the intake drawer: an <input type=file>
  // holds a FileList that script cannot write, so nothing in an open
  // promote drawer may call renderAll(). The first repaint of the flow
  // happens after a response lands.
  function promoteAndAccept(candidateId, file, place, onFail) {
    var base = evidenceCandidatePath(candidateId);
    var opts = { method: "POST" };
    if (file) {
      // Multipart, and the browser must write its own Content-Type so it
      // can append the boundary — api() knows not to touch a FormData.
      var fd = new FormData();
      fd.append("file", file, file.name);
      opts.body = fd;
    }
    // No file and no body at all is the ordinary path now. It covers a
    // candidate that is already promoted, one whose picture is already
    // in the archive under the same fingerprint, and one whose import
    // brought the picture with it. Only an import the operator
    // themselves fed a file to still needs one here.
    api(base + "/promote", opts)
      .then(function (out) {
        var photoId = out && out.photo_id;
        if (!photoId) throw new Error("promotion returned no photo_id");
        return api(base + "/decision", {
          method: "POST",
          body: { state: "accepted", photo_id: photoId },
        }).catch(function (e) {
          // The halfway state, named exactly. The photo exists and is
          // unapproved, the candidate did not move, and the retry is
          // safe because promotion is idempotent.
          e.message = "Promoted (photo " + String(photoId).slice(0, 8) +
            ") but the accept did not land: " + e.message +
            " — the candidate is still pending and running this again is " +
            "safe.";
          throw e;
        }).then(function () { return photoId; });
      })
      .then(function (photoId) {
        if (!place || !place.tripId || !place.dayId) return null;
        return api("/api/trips/" + encodeURIComponent(place.tripId) +
          "/days/" + encodeURIComponent(place.dayId) + "/photos/link", {
            method: "POST",
            body: { photo_ids: [photoId] },
          }).catch(function (e) {
            // The second halfway state, and a gentler one: the photo is
            // in the archive and the candidate is accepted. Only the
            // day is missing, and the day can be set from the day card.
            e.message = "Accepted, but filing it on the day did not " +
              "land: " + e.message + " — the photo is saved and the " +
              "candidate is accepted, so you can add it from the day " +
              "itself or run this again.";
            throw e;
          });
      })
      .then(function () {
        st.evidenceDrawer = null;
        return reloadEvidence();
      })
      .then(function () {
        // The day cards read from the trip's photo links, and the count
        // on each card comes from /days. A photo filed on a day only
        // becomes visible once both are re-read. Failures here are
        // swallowed on purpose: the write already succeeded, and a
        // refresh that could not run is a stale screen, not a lost
        // photo.
        return Promise.all([
          reloadPhotoLinks().catch(function () { return null; }),
          reloadDays().catch(function () { return null; }),
        ]);
      })
      .then(function () { renderAll(); })
      .catch(function (e) { onFail(e.message); });
  }

  function renderEvidencePromoteDrawer(d, c) {
    var sh = drawerShell("Evidence review", "Promote + accept",
      closeEvidenceDrawer, "tdl-edit-drawer tdl-erq-drawer");
    sh.body.appendChild(el("strong", "", candidateName(c)));
    sh.body.appendChild(el("p", "tdl-intake-doctrine",
      "Three steps, in this order, because saving the picture, recording " +
      "your decision and putting it on a day are separate acts on " +
      "purpose. First the picture is saved — kept private, not shown to " +
      "the narrator, and not approved for Lori on either its date or its " +
      "location. Then the decision records that you accepted it. Then it " +
      "is filed on the day you chose. If one step lands and the next " +
      "does not, this drawer says which, and running it again is safe."));

    if (!d.daysLoaded) {
      sh.body.appendChild(el("p", "tdl-muted", "Loading this trip's days…"));
      sh.foot.appendChild(btn("tdl-btn", "Cancel", closeEvidenceDrawer));
      return sh.wrap;
    }

    var already = !!c.photo_id;
    // Derived by the server from whether the picture is actually here,
    // not from the name of the import it came through. A lane that
    // brings its own copy answers false and no file is asked for.
    var needsFile = !already && c.promotion_needs_upload !== false;
    var files = null;
    if (already) {
      sh.body.appendChild(el("p", "tdl-muted",
        "This one is already saved, so it needs no file — accepting will " +
        "reuse the picture it already has."));
    } else if (needsFile) {
      files = el("input");
      files.type = "file";
      files.accept = "image/*";
      sh.body.appendChild(field("Image file", files,
        "This one came in as a list entry rather than a picture, so the " +
        "image file has to come from you."));
    } else {
      sh.body.appendChild(el("p", "tdl-muted",
        "The picture came in with the import and is already here, so " +
        "there is nothing to upload."));
    }

    // ── the day ───────────────────────────────────────────────────────
    var dayCtl = null;
    var tripId = c.trip && c.trip.id;
    if (!tripId) {
      sh.body.appendChild(el("p", "tdl-muted",
        "This one is not filed to a trip yet, so there is no day to put " +
        "it on. Accepting it now saves the picture; use “File to trip” " +
        "first if you want it to land on a day."));
    } else if (d.daysError) {
      sh.body.appendChild(el("p", "tdl-muted",
        "This trip's days could not be loaded (" + d.daysError + "), so " +
        "no day can be offered. Accepting still saves the picture and " +
        "you can add it from the day itself."));
    } else if (!d.days.length) {
      sh.body.appendChild(el("p", "tdl-muted",
        "This trip has no days yet. Accepting still saves the picture; " +
        "build the days and add it from the day itself."));
    } else {
      var suggested = suggestedDayIdFor(c, d.days);
      var opts = [["", "Do not put it on a day yet"]];
      d.days.forEach(function (day) {
        opts.push([String(day.id),
          "Day " + day.day_index + " · " + (day.date || "no date") +
          (day.title ? " · " + day.title : "") +
          (String(day.id) === suggested ? "  (matches this photo's date)" : "")]);
      });
      dayCtl = selectInput(opts, d.dayId || "");
      sh.body.appendChild(field("Put it on", dayCtl,
        suggested
          ? "The day matching the date on this photo is pre-selected as a " +
            "suggestion only. Change it if the photo belongs somewhere else."
          : "Nothing on this photo says which day it belongs to, so pick " +
            "one."));
    }

    var errEl = drawerError(sh.body, d.error);
    var goBtn = btn("tdl-btn tdl-btn-primary", "Promote + accept",
      function () {
        var chosen = files ?
          Array.prototype.slice.call(files.files || []) : [];
        if (needsFile && !chosen.length) {
          errEl.textContent = "Choose the image file for this candidate first.";
          errEl.hidden = false;
          return;
        }
        errEl.hidden = true;
        goBtn.disabled = true;
        var place = (dayCtl && dayCtl.value)
          ? { tripId: tripId, dayId: dayCtl.value } : null;
        promoteAndAccept(c.id, chosen[0] || null, place, function (msg) {
          goBtn.disabled = false;
          if (st.evidenceDrawer) st.evidenceDrawer.error = msg;
          renderAll();
        });
      });
    sh.foot.appendChild(goBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeEvidenceDrawer));
    return sh.wrap;
  }

  function renderEvidenceDecideDrawer(d, c) {
    var meta = EVIDENCE_REFUSALS.filter(function (r) {
      return r[0] === d.state;
    })[0] || EVIDENCE_REFUSALS[0];
    var sh = drawerShell("Evidence review", meta[1] + " this candidate",
      closeEvidenceDrawer, "tdl-edit-drawer tdl-erq-drawer");
    sh.body.appendChild(el("strong", "", candidateName(c)));
    sh.body.appendChild(el("p", "tdl-muted",
      "Recording “" + meta[0] + "” — " + meta[2] + ". The candidate row, " +
      "its match reason and its batch all survive: a decision here is a " +
      "record, not an erasure, and this lane has no DELETE."));
    var reason = areaInput("",
      "Why (optional) — kept on the candidate as state_reason");
    sh.body.appendChild(field("Reason", reason));
    var errEl = drawerError(sh.body, d.error);
    var goBtn = btn("tdl-btn tdl-btn-primary", meta[1], function () {
      errEl.hidden = true;
      goBtn.disabled = true;
      // No photo_id: the route refuses one on any non-accepted state, and
      // sending one would be asking for a 400 that means nothing to the
      // operator.
      api(evidenceCandidatePath(c.id) + "/decision", {
        method: "POST",
        body: {
          state: meta[0],
          state_reason: (reason.value || "").trim() || null,
        },
      })
        .then(function () {
          st.evidenceDrawer = null;
          return reloadEvidence();
        })
        .then(function () { renderAll(); })
        .catch(function (e) {
          goBtn.disabled = false;
          if (st.evidenceDrawer) st.evidenceDrawer.error = e.message;
          renderAll();
        });
    });
    sh.foot.appendChild(goBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeEvidenceDrawer));
    return sh.wrap;
  }

  function renderEvidenceFileDrawer(d, c) {
    var sh = drawerShell("Evidence review", "File to trip",
      closeEvidenceDrawer, "tdl-edit-drawer tdl-erq-drawer");
    sh.body.appendChild(el("strong", "", candidateName(c)));
    sh.body.appendChild(el("p", "tdl-muted",
      "Placement in this lane is trip granularity and nothing finer — " +
      "there is no region, stop or day here because the import tables " +
      "have no column to hold one. Filing is reversible: choose “Not " +
      "filed” to unbind it again."));
    var choices = [["", "Not filed"]];
    st.trips.forEach(function (t) {
      choices.push([String(t.id), t.title || "Untitled trip"]);
    });
    var sel = selectInput(choices, c.trip_id ? String(c.trip_id) : "");
    sh.body.appendChild(field("Trip", sel));
    var errEl = drawerError(sh.body, d.error);
    var goBtn = btn("tdl-btn tdl-btn-primary", "Save placement", function () {
      errEl.hidden = true;
      goBtn.disabled = true;
      api(evidenceCandidatePath(c.id) + "/trip", {
        method: "PATCH",
        body: { trip_id: sel.value || null },
      })
        .then(function () {
          st.evidenceDrawer = null;
          return reloadEvidence();
        })
        .then(function () { renderAll(); })
        .catch(function (e) {
          goBtn.disabled = false;
          if (st.evidenceDrawer) st.evidenceDrawer.error = e.message;
          renderAll();
        });
    });
    sh.foot.appendChild(goBtn);
    sh.foot.appendChild(btn("tdl-btn", "Cancel", closeEvidenceDrawer));
    return sh.wrap;
  }

  // ── Google Photos Picker — the import affordance ─────────────────────
  //
  // WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01 Phase 2D. Spec §12.8 calls this
  // "minimal operator UI (open picker, check selection, ingest, refresh
  // queue)", and those four verbs are the whole of it.
  //
  // WHERE IT LIVES, AND WHY IT IS NOT AN ELEVENTH TAB. Binding ruling 1.3
  // of docs/architecture/TRAVEL_DOCUMENT_DOCTRINE.md: "There is one
  // review queue for photo/media candidates and it is the Evidence Review
  // Queue [...] A new import source makes its candidates visible *in that
  // queue*. It does not get a review screen of its own." A tab of its own
  // was considered and refused on that ruling — a screen with its own
  // name is a screen that grows its own list — so the affordance is a
  // strip at the top of the tab that already owns candidate review, and
  // every decision about every candidate is still taken on the rows
  // below it.
  //
  // WHAT THE RUN REPORT IS NOT. After an ingest this panel prints the
  // per-item results the route returned: outcome, filename, reason. That
  // is a RECEIPT for one run. It is rendered once from the HTTP response,
  // it is never refetched, and it carries no Accept, no Reject, no Hide,
  // no Promote and no File-to-trip. Those controls exist exactly once in
  // this file, on the queue rows. Ruling 1.3 again, in its own words: a
  // second queue "is a second approval semantics no matter how thin it
  // looks on the day it is written".
  //
  // WHAT NEVER REACHES THIS FILE. No client id, no client secret, no
  // refresh token, no access token, and no `baseUrl` — the bearer-scoped
  // download URL that spec §10.4 keeps out of every response and every
  // log. The Google session id is not returned to the browser either:
  // POST /sessions hands back a `batch_id` and a `picker_uri`, and those
  // two are all this module holds. Credentials are Chris's, they are read
  // from the server process environment, and §6 puts them out of an
  // agent's reach entirely. /health reports their PRESENCE as booleans
  // and this panel renders only that.
  //
  // NO GOOGLE JAVASCRIPT. There is no Picker SDK, no <script> from a
  // Google origin, and no popup driven from here. `picker_uri` renders as
  // a link the operator opens himself, in Google's own hosted UI, in his
  // own browser session — which is also why the picking step cannot be
  // automated from this screen and is not meant to be.
  //
  // THE ONE ROUTE IN THE LANE THAT IS DELIBERATELY NOT SURFACED is
  // DELETE /sessions/{batch_id}. It releases the picking session AT
  // GOOGLE and answers `batch_deleted: false`, so it does not breach the
  // no-DELETE rule and it could have been offered. It is left out on
  // SCOPE, not on safety: 2D's four verbs do not include it, an unused
  // Google session expires by itself, and the first UI a lane ever gets
  // is the wrong place to introduce that lane's only DELETE verb. A later
  // phase can add it with a reason of its own.

  var PICKER_BASE = "/api/google-picker";

  // Google returns pollingConfig.pollInterval as a protobuf Duration
  // string — "5s", and legally "5.5s". It is parsed defensively and
  // clamped at both ends by THIS module, not by Google: a malformed value
  // must not become a zero-delay loop hammering someone else's API, and
  // an absurd one must not leave the operator watching a panel that never
  // checks. The bounds are named rather than inlined so the failure mode
  // is readable from here.
  var PICKER_POLL_MIN_MS = 3000;
  var PICKER_POLL_MAX_MS = 30000;
  var PICKER_POLL_DEFAULT_MS = 5000;
  // A hard stop on UNATTENDED polling only. "Check now" is always
  // available, and Google expires the session on its own; this bounds the
  // timer, not the operator.
  var PICKER_POLL_MAX_TRIES = 120;

  function pickerPollMs(raw) {
    var n = parseFloat(String(raw === null || raw === undefined ? "" : raw));
    if (!isFinite(n) || n <= 0) return PICKER_POLL_DEFAULT_MS;
    var ms = n * 1000;
    if (ms < PICKER_POLL_MIN_MS) return PICKER_POLL_MIN_MS;
    if (ms > PICKER_POLL_MAX_MS) return PICKER_POLL_MAX_MS;
    return ms;
  }

  // Phase 1.1's liveness note counted ONE timer in this file. This is the
  // second, and it is guarded the same way and for the same reason: the
  // handle is a module var, `destroyed` is the first thing the callback
  // checks, and destroy() clears it. A poll that outlived the mount would
  // write to `st` and repaint a host the shell has already handed on.
  var _pickerPollTimer = null;

  function pickerPollStop() {
    if (_pickerPollTimer !== null) {
      try { clearTimeout(_pickerPollTimer); } catch (_) {}
      _pickerPollTimer = null;
    }
    if (st.picker) st.picker.polling = false;
  }

  function pickerPollArm(ms) {
    pickerPollStop();
    if (destroyed || !st.picker) return;
    st.picker.polling = true;
    _pickerPollTimer = setTimeout(function () {
      _pickerPollTimer = null;
      if (destroyed) return;
      pickerCheck(true);
    }, ms);
  }

  // api() already flattens this lane's nested {detail:{detail, reason}}
  // envelope into e.message. The REASON is the operator-actionable half —
  // `refresh_token_expired` means re-mint the token, `selection_incomplete`
  // means go and finish picking, `credentials_missing` means the server
  // was never configured — so it is appended rather than dropped on the
  // floor. It is a short enum string from the server's own table; it is
  // never a credential and never a URL.
  function pickerMessage(e) {
    var msg = (e && e.message) || "The request failed.";
    var d = e && e.body && e.body.detail;
    var reason = (d && typeof d === "object" && d.reason) ? String(d.reason) : "";
    return reason ? (msg + "  [" + reason + "]") : msg;
  }

  // The lane sits behind TWO default-off server flags and every route in
  // it — /health included — answers 404 while either is off. Same
  // convention as the queue's own 404 arm, and for the same reason: a
  // flag that is off is a configuration fact, not a fault, and painting
  // it red sends an operator hunting for something broken.
  //
  // The two off-states are INDEPENDENT and are held apart on purpose. The
  // queue needs HORNELORE_IMPORT_PROVENANCE; the picker needs that one
  // AND HORNELORE_GOOGLE_PICKER. So a readable queue with no import
  // affordance above it is a real, reachable and correct configuration,
  // and one shared flag would have rendered it as a lie in one direction
  // or the other.
  function pickerLaneOff() {
    st.pickerOff = true;
    st.pickerHealth = null;
    st.picker = null;
    st.pickerError = "";
    pickerPollStop();
  }

  // Never rejects. Side-effect free at the server, and the ONLY route in
  // this lane where a 404 has exactly one meaning: /health takes no path
  // parameter, so nothing behind it can be "not found" except the gate
  // itself. That is why the flag-off inference is made here and made
  // nowhere else — see pickerCheck() for the routes where a 404 is
  // ambiguous and is therefore reported rather than interpreted.
  function reloadPickerHealth() {
    if (!st.personId) return Promise.resolve();
    return api(PICKER_BASE + "/health")
      .then(function (out) {
        st.pickerHealth = out;
        st.pickerOff = false;
      })
      .catch(function (e) {
        if (e && e.status === 404) { pickerLaneOff(); return; }
        // Not a 404: the lane is on and something else went wrong. Say
        // so on the strip rather than silently hiding the affordance.
        st.pickerError = pickerMessage(e);
      });
  }

  function pickerStart() {
    if (!st.personId || st.pickerBusy) return;
    st.pickerBusy = true;
    st.pickerError = "";
    // Spec §10.2 — the destination is explicit and supplied by the
    // request. person_id comes from the mount and is NEVER inferred from
    // the Google account; trip_id is the operator's visible choice on the
    // strip. There is no default, no fallback, and no "if only one trip
    // exists, use that one".
    var body = { person_id: st.personId };
    if (st.pickerFileToTrip && st.trip) body.trip_id = st.trip.id;
    renderAll();
    api(PICKER_BASE + "/sessions", { method: "POST", body: body })
      .then(function (out) {
        st.pickerBusy = false;
        st.pickerOff = false;
        st.picker = {
          batchId: out.batch_id,
          tripId: out.trip_id || null,
          pickerUri: out.picker_uri,
          mediaItemsSet: !!out.media_items_set,
          pollMs: pickerPollMs(out.poll_interval),
          expireTime: out.expire_time || "",
          batchStatus: "open",
          ingestAvailable: false,
          stage: "picking",
          tries: 0,
          polling: false,
          checking: false,
          run: null,
          error: "",
        };
        pickerPollArm(st.picker.pollMs);
        renderAll();
      })
      .catch(function (e) {
        st.pickerBusy = false;
        // POST /sessions takes no path parameter either, so a 404 here is
        // the gate as well.
        if (e && e.status === 404) { pickerLaneOff(); renderAll(); return; }
        st.pickerError = pickerMessage(e);
        renderAll();
      });
  }

  // GET /sessions/{batch_id} polls Google and writes nothing — the route
  // says so, because the UI calls it on a timer. `fromTimer` separates
  // the automatic tick from the operator pressing Check now: only the
  // automatic one re-arms, and only the automatic one counts against the
  // try cap.
  //
  // A 404 is NOT read as flag-off here. On this path it could be the
  // gate, a batch id this server does not have, or Google reporting the
  // picking session gone — three different situations with three
  // different answers. Guessing one and rendering "the lane is switched
  // off" would be a confident wrong answer, so the message and its reason
  // are shown as they arrived.
  function pickerCheck(fromTimer) {
    var p = st.picker;
    if (!p || p.checking) return;
    p.checking = true;
    p.error = "";
    if (fromTimer) p.tries += 1;
    if (!fromTimer) renderAll();
    api(PICKER_BASE + "/sessions/" + encodeURIComponent(p.batchId))
      .then(function (out) {
        var q = st.picker;
        // A newer run replaced the one this poll was launched for.
        if (!q || String(q.batchId) !== String(out.batch_id)) return;
        q.checking = false;
        q.mediaItemsSet = !!out.media_items_set;
        q.batchStatus = out.batch_status || "";
        q.ingestAvailable = !!out.ingest_available;
        q.pollMs = pickerPollMs(out.poll_interval);
        if (out.expire_time) q.expireTime = out.expire_time;
        if (q.ingestAvailable) {
          q.stage = "ready";
          pickerPollStop();
        } else if (fromTimer && q.tries < PICKER_POLL_MAX_TRIES) {
          pickerPollArm(q.pollMs);
        } else {
          pickerPollStop();
        }
        renderAll();
      })
      .catch(function (e) {
        var q = st.picker;
        if (!q) return;
        q.checking = false;
        pickerPollStop();
        q.error = pickerMessage(e);
        renderAll();
      });
  }

  // The one write in this panel, and it writes only pending candidates.
  // Ingest never promotes, never creates a `photos` row and never records
  // an operator decision — the route's own docstring commits to that, and
  // `google_photos_picker` is not in PROMOTABLE_SOURCES, so this button
  // cannot become an approval by accident.
  //
  // max_items is deliberately not sent. A cap this screen chose would
  // truncate a run for a reason the operator never asked for; the route
  // reports `truncated` and `remaining` if one is ever supplied, and this
  // panel would render them, but it does not supply one.
  function pickerIngest() {
    var p = st.picker;
    if (!p || p.stage === "ingesting") return;
    pickerPollStop();
    p.stage = "ingesting";
    p.error = "";
    renderAll();
    api(PICKER_BASE + "/sessions/" + encodeURIComponent(p.batchId) + "/ingest",
        { method: "POST" })
      .then(function (out) {
        var q = st.picker;
        if (!q || String(q.batchId) !== String(out.batch_id)) return;
        q.stage = "done";
        q.run = out;
        q.batchStatus = out.batch_status || q.batchStatus;
        // The rows this run created are already in the queue below —
        // ingest does not build a second one and does not need to. The
        // reload is here so the receipt and the authoritative list are
        // read in the same glance: the panel reports the RUN, the queue
        // owns the ROWS.
        return reloadEvidence();
      })
      .then(function () { renderAll(); })
      .catch(function (e) {
        var q = st.picker;
        if (!q) return;
        // Back to `ready`, not to a dead end: a retryable failure means
        // run it again, `candidate_create` is idempotent on
        // (batch_id, external_id), and nothing already landed is
        // re-downloaded. That is what leaving the batch open is for.
        q.stage = "ready";
        q.error = pickerMessage(e);
        renderAll();
      });
  }

  // Clears the SCREEN and says so on the button. The import batch and
  // every candidate on it survive — there is no DELETE on this lane and
  // this control is not one. The Google picking session is left to expire
  // on its own, which it does.
  function pickerDismiss() {
    pickerPollStop();
    st.picker = null;
    st.pickerError = "";
    renderAll();
  }

  // ── the import strip ─────────────────────────────────────────────────

  function renderPickerStrip() {
    var box = el("div", "tdl-gp");
    box.appendChild(el("div", "tdl-kicker", "Import from Google Photos"));

    if (st.pickerOff) {
      box.appendChild(el("p", "tdl-gp-off",
        "The Google Photos import lane is switched off on this server, so " +
        "there is nothing to import from here — every route in it answers " +
        "404 while either of its two flags is off. Nothing is broken, and " +
        "the queue below is unaffected: it needs only the import lane's " +
        "own flag, which is clearly on or you would be reading a different " +
        "panel."));
      return box;
    }

    var h = st.pickerHealth;
    if (h && h.credentials_complete === false) {
      // Presence booleans, which is all /health will report. Naming the
      // missing variable is a configuration fact and helps; printing any
      // part of a value — prefix, tail or length — is forbidden by spec
      // §10.4 and nothing here has one to print.
      var missing = [];
      var present = h.credentials_present || {};
      Object.keys(present).forEach(function (k) {
        if (!present[k]) missing.push(k);
      });
      box.appendChild(el("p", "tdl-gp-off",
        "This server has the Google Photos lane switched on but is not " +
        "authorized yet" +
        (missing.length ? " — not set: " + missing.join(", ") : "") +
        ". That is Chris's one-time console step and nothing on this " +
        "screen can do it. The queue below is unaffected."));
      return box;
    }

    if (st.pickerError) box.appendChild(el("div", "tdl-error", st.pickerError));

    if (!st.picker) {
      box.appendChild(el("p", "tdl-muted",
        "Opens a picking session in your own Google account, in Google's " +
        "own window. Whatever you choose is downloaded here and lands as " +
        "PENDING candidates in the queue below — nothing is accepted, " +
        "nothing becomes a photo, and nothing reaches a narrator until you " +
        "decide it there."));

      // Destination, chosen in the open. The batch is filed at creation
      // and this is the only moment it is decided, so it is a visible
      // control rather than an inference from whatever tab filter the
      // operator happens to be standing in.
      var dest = el("div", "tdl-filter-rail tdl-filter-rail-row");
      if (st.trip) {
        dest.appendChild(btn(st.pickerFileToTrip ? "tdl-active" : "",
          "File to " + (st.trip.title || "this trip"), function () {
            st.pickerFileToTrip = true;
            renderAll();
          }));
        dest.appendChild(btn(st.pickerFileToTrip ? "" : "tdl-active",
          "Leave unfiled", function () {
            st.pickerFileToTrip = false;
            renderAll();
          }));
      } else {
        dest.appendChild(el("span", "tdl-muted",
          "No trip is selected, so this import will be filed to no trip. " +
          "Its candidates appear under All trips, and File to trip on each " +
          "row moves them later."));
      }
      box.appendChild(dest);

      var go = btn("tdl-btn tdl-btn-primary",
        st.pickerBusy ? "Opening a session…" : "Import from Google Photos",
        pickerStart);
      go.disabled = !!st.pickerBusy || !st.personId;
      box.appendChild(go);
      return box;
    }

    box.appendChild(renderPickerRun(st.picker));
    return box;
  }

  function renderPickerRun(p) {
    var wrap = el("div", "tdl-gp-run");

    var badges = el("div", "tdl-note-badges");
    badges.appendChild(el("span", "tdl-badge tdl-gp-stage", p.stage));
    badges.appendChild(el("span", "tdl-badge",
      "batch · " + String(p.batchId).slice(0, 8)));
    if (p.batchStatus) {
      badges.appendChild(el("span", "tdl-badge", "batch " + p.batchStatus));
    }
    // The batch's OWN trip, named by id rather than by the word "a trip".
    // selectTrip() deliberately leaves a run standing (see the note
    // there), so the operator can be looking at trip B while this panel
    // describes a batch filed to trip A. A badge that said only "filed to
    // a trip" would read as "filed to the one you are looking at", which
    // would be a lie exactly when it mattered.
    badges.appendChild(el("span",
      "tdl-badge" + (p.tripId ? "" : " tdl-badge-unfiled"),
      p.tripId ? ("filed to trip · " + String(p.tripId).slice(0, 8))
               : "not filed to a trip"));
    wrap.appendChild(badges);

    if (p.error) wrap.appendChild(el("div", "tdl-error", p.error));

    // Step one: the link, opened by the operator. Not window.open, not a
    // popup, and not a Google script — target=_blank with rel=noopener so
    // the new page gets no handle back to this one.
    if (p.stage === "picking" || p.stage === "ready") {
      var a = el("a", "tdl-gp-link", "Open the Google picker →");
      a.href = p.pickerUri;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      wrap.appendChild(a);
      wrap.appendChild(el("p", "tdl-muted",
        "Choose photos in Google's window, then come back here. This " +
        "screen checks on its own every few seconds; the session expires " +
        "at Google" + (p.expireTime ? " around " + datePrefix(p.expireTime)
                                    : "") + "."));
    }

    var acts = el("div", "tdl-gp-actions");
    if (p.stage === "picking") {
      acts.appendChild(el("span", "tdl-muted", p.checking ? "Checking…" :
        (p.polling ? ("Waiting for your selection — checked " + p.tries +
                      (p.tries === 1 ? " time" : " times"))
                   : "Not checking automatically any more.")));
      acts.appendChild(btn("tdl-btn tdl-btn-small", "Check now",
        function () { pickerCheck(false); }));
      if (p.polling) {
        acts.appendChild(btn("tdl-btn tdl-btn-small", "Stop checking",
          function () { pickerPollStop(); renderAll(); }));
      } else {
        acts.appendChild(btn("tdl-btn tdl-btn-small", "Resume checking",
          function () { p.tries = 0; pickerPollArm(p.pollMs); renderAll(); }));
      }
    } else if (p.stage === "ready") {
      acts.appendChild(el("span", "tdl-muted",
        "Your selection is finished at Google and can be imported."));
      acts.appendChild(btn("tdl-btn tdl-btn-primary tdl-btn-small",
        "Import the selection", pickerIngest));
    } else if (p.stage === "ingesting") {
      acts.appendChild(el("span", "tdl-muted",
        "Downloading and staging — this holds the originals, reads EXIF, " +
        "and writes one pending candidate per photo."));
    }
    // Available at every stage, including mid-run: it only clears the
    // panel. Worth being plain about, because "Dismiss" next to an import
    // reads like a cancel and it is not one.
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Dismiss this run",
      pickerDismiss));
    wrap.appendChild(acts);
    if (p.stage !== "done") {
      wrap.appendChild(el("p", "tdl-muted",
        "Dismiss clears this panel only. The import batch and every " +
        "candidate on it survive — there is no delete on this lane."));
    }

    if (p.run) wrap.appendChild(renderPickerReceipt(p.run));
    return wrap;
  }

  // The receipt. Rendered once, from the response body that is already in
  // hand, and never refetched — so it cannot drift into being a list that
  // is kept up to date, which is the first thing a second queue does.
  function renderPickerReceipt(run) {
    var box = el("div", "tdl-gp-receipt");

    var line = el("div", "tdl-gp-counts");
    [["created", run.created], ["repaired", run.repaired],
     ["unchanged", run.unchanged], ["failed", run.failed]].forEach(function (c) {
      line.appendChild(el("span", "tdl-badge tdl-gp-count-" + c[0],
        c[1] + " " + c[0]));
    });
    box.appendChild(line);

    var picked = el("p", "tdl-muted",
      "Picked " + run.picked + " · attempted " + run.attempted +
      (run.truncated ? " · " + run.remaining + " not attempted" : "") +
      (run.failed ? (" · of the failures, " + run.retryable_failures +
                     " can be retried and " + run.permanent_failures +
                     " cannot") : ""));
    box.appendChild(picked);

    if (run.queue) {
      box.appendChild(el("p", "tdl-muted",
        "This batch now holds " + run.queue.candidates_in_batch +
        " candidate(s), " + run.queue.pending_in_batch + " of them still " +
        "pending. They are in the queue below — this panel is a receipt " +
        "for the run, not a second place to review them."));
    }
    if (run.retryable_failures) {
      box.appendChild(el("p", "tdl-muted",
        "Running the import again picks up the retryable failures. " +
        "Nothing that already landed is downloaded twice."));
    }

    (run.results || []).forEach(function (r) {
      box.appendChild(renderPickerResultRow(r));
    });
    return box;
  }

  // Every field is read BY NAME. Iterating the response object would put
  // this screen at the mercy of whatever the route grows next, and the
  // one class of value that must never be rendered — a bearer-scoped
  // download URL, a token, a staging path — is exactly the kind of thing
  // that would arrive as a new key. An allow-list cannot leak a field
  // nobody has thought about yet.
  function renderPickerResultRow(r) {
    var row = el("div", "tdl-gp-result tdl-gp-result-" +
      (r.outcome || "unknown"));
    row.appendChild(el("span", "tdl-badge tdl-gp-outcome",
      r.outcome || "unknown"));
    row.appendChild(el("strong", "", r.filename || "(no filename)"));

    var bits = [];
    if (r.mime_type) bits.push(r.mime_type);
    if (r.byte_size) bits.push(String(r.byte_size) + " bytes");
    if (r.taken_at) {
      bits.push("taken " + datePrefix(r.taken_at) +
        " (" + (r.taken_at_source || "unknown") + ")");
    }
    if (r.location_source) bits.push("location " + r.location_source);
    if (r.gps_present_unparseable) bits.push("GPS present but unreadable");
    if (r.candidate_id) {
      bits.push("candidate " + String(r.candidate_id).slice(0, 8));
    }
    if (bits.length) row.appendChild(el("p", "tdl-muted", bits.join(" · ")));

    if (r.outcome === "failed") {
      row.appendChild(el("p", "tdl-gp-fail",
        (r.reason || "failed") + " — " + (r.detail || "no detail given") +
        (r.retryable ? "  (retryable)" : "  (permanent)")));
    }
    // No Accept, no Reject, no Hide, no Promote, no File to trip. This is
    // a run report; the queue below is where a candidate is decided.
    return row;
  }

  // ── Story Notes ──────────────────────────────────────────────────────

  function renderNotes() {
    var wrap = el("div");
    wrap.appendChild(el("h1", "", "Story Notes"));
    wrap.appendChild(el("p", "tdl-muted",
      "Location notes across the trip. Toggles write through the existing " +
      "location-notes PATCH — flags stay honest to the DB. Hide is " +
      "reversible (PATCH hidden) — nothing is deleted."));
    var hiddenNoteCount = st.notes.filter(function (n) {
      return !!n.hidden;
    }).length;
    wrap.appendChild(hiddenToggleRow("showHiddenNotes", hiddenNoteCount,
      "notes"));
    if (!st.notes.length) {
      wrap.appendChild(el("div", "tdl-empty", "No story notes yet."));
      return wrap;
    }
    st.notes.forEach(function (n) {
      var row = el("div", "tdl-note-row" +
        (n.hidden ? " tdl-row-hidden" : ""));
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge", n.source_type || "note"));
      if (n.hidden) {
        badges.appendChild(el("span", "tdl-badge tdl-badge-hidden",
          "hidden" + (n.hidden_at ? " · " + datePrefix(n.hidden_at) : "")));
      }
      if (n.source_surface === "travel_doc_modal") {
        badges.appendChild(el("span", "tdl-badge tdl-badge-lori", "from Lori modal"));
      }
      if (n.photo_link_id) badges.appendChild(el("span", "tdl-badge", "📷 photo-scoped"));
      if (n.trip_day_id) {
        var nd = dayById(n.trip_day_id);
        badges.appendChild(el("span", "tdl-badge",
          nd ? ("Day " + nd.day_index) : "day-scoped"));
      }
      var stop = n.trip_stop_id && findStop(n.trip_stop_id);
      var region = n.trip_region_id && findRegion(n.trip_region_id);
      if (stop) badges.appendChild(el("span", "tdl-badge", stop.location_name || "stop"));
      else if (region) badges.appendChild(el("span", "tdl-badge", region.title || "region"));
      row.appendChild(badges);
      if (n.note_title) row.appendChild(el("strong", "", n.note_title));
      row.appendChild(el("p", "", n.note_text || ""));

      if (n.hidden) {
        // Hidden rows are already out of evidence — offer Restore only.
        var hActs = el("div", "tdl-note-toggles");
        hActs.appendChild(btn("tdl-btn tdl-btn-small", "Restore",
          function () { restoreNote(n.id); }));
        row.appendChild(hActs);
        wrap.appendChild(row);
        return;
      }

      var toggles = el("div", "tdl-note-toggles");
      function toggle(labelText, field, checked) {
        var lab = el("label");
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = !!checked;
        cb.addEventListener("change", function () {
          var body = {};
          body[field] = cb.checked;
          api("/api/trips/location-notes/" + encodeURIComponent(n.id),
            { method: "PATCH", body: body })
            .then(function () { return reloadNotes(); })
            .catch(function (e) {
              cb.checked = !cb.checked;
              st.error = e.message; renderAll();
            });
        });
        lab.appendChild(cb);
        lab.appendChild(el("span", "", labelText));
        return lab;
      }
      toggles.appendChild(toggle("In memoir", "include_in_memoir",
        n.include_in_memoir));
      toggles.appendChild(toggle("Use with Lori", "include_in_interview_context",
        n.include_in_interview_context));
      // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: reversible hide (never a
      // DELETE) — the row reappears under Show hidden with a Restore.
      toggles.appendChild(btn("tdl-btn tdl-btn-small", "Hide",
        function () { hideNote(n.id); }));
      row.appendChild(toggles);
      wrap.appendChild(row);
    });
    return wrap;
  }

  // ── Captured-note review (WO-POST-LORI-CLEANUP-AND-UNBLOCK-01) ───────

  // Lane 3. This screen is a FINDER, not a new capture or promotion
  // path. Every checkbox on it writes through the same
  // PATCH /api/trips/location-notes/{id} the per-trip Story Notes list
  // has always used, with the same server validation. Nothing here
  // auto-promotes, nothing changes the include_in_memoir=0 default, and
  // nothing writes to the life-story archive -- these are trip rows and
  // the two-surface rule of 2026-07-09 is untouched.

  var CAPTURED_SURFACES = [
    ["travel_doc_modal", "Travel Doc modal"],
    ["", "Any surface"],
  ];

  var CAPTURED_PROMOTION = [
    ["", "All"],
    ["0", "Not in memoir"],
    ["1", "In memoir"],
  ];

  function capturedQueryPath() {
    var q = ["person_id=" + encodeURIComponent(st.personId || "")];
    if (st.capturedSurface) {
      q.push("source_surface=" + encodeURIComponent(st.capturedSurface));
    }
    if (st.capturedPromoted === "0") q.push("promoted=false");
    if (st.capturedPromoted === "1") q.push("promoted=true");
    if (st.showHiddenCaptured) q.push("include_hidden=true");
    return "/api/trips/captured-notes?" + q.join("&");
  }

  function reloadCaptured() {
    if (!st.personId) return Promise.resolve();
    st.capturedBusy = true;
    return api(capturedQueryPath())
      .then(function (out) {
        st.captured = out;
        st.capturedOff = false;
        st.capturedError = "";
        st.capturedBusy = false;
      })
      // A captured note IS a trip_location_notes row, so promoting one
      // changes what the document contains -- same table, same preview.
      .then(invalidateMemoirPreview)
      .catch(function (e) {
        st.capturedBusy = false;
        if (e && e.status === 404) {
          // The whole trips lane is behind a default-off server flag and
          // answers 404 while it is off. That is configuration, not an
          // error, and must not paint the workspace-wide red bar.
          st.capturedOff = true;
          st.captured = null;
          st.capturedError = "";
          return;
        }
        st.capturedError = e.message;
      });
  }

  function setCapturedSurface(v) {
    if (st.capturedSurface === v) return;
    st.capturedSurface = v;
    reloadCaptured().then(function () { renderAll(); });
  }

  function setCapturedPromoted(v) {
    if (st.capturedPromoted === v) return;
    st.capturedPromoted = v;
    reloadCaptured().then(function () { renderAll(); });
  }

  function toggleCapturedHidden() {
    st.showHiddenCaptured = !st.showHiddenCaptured;
    reloadCaptured().then(function () { renderAll(); });
  }

  // The one write on this screen. Deliberately the existing endpoint.
  function setCapturedMemoir(noteId, on, cb) {
    return api("/api/trips/location-notes/" + encodeURIComponent(noteId),
      { method: "PATCH", body: { include_in_memoir: !!on } })
      .then(function () { return reloadCaptured(); })
      .then(function () { renderAll(); })
      .catch(function (e) {
        if (cb) cb.checked = !cb.checked;
        st.capturedError = e.message;
        renderAll();
      });
  }

  function capturedScopeLabel(n) {
    var bits = [];
    if (n.stop_location_name || n.stop_title) {
      bits.push(n.stop_location_name || n.stop_title);
    } else if (n.region_title) {
      bits.push(n.region_title);
    }
    return bits.join(" · ");
  }

  function renderCaptured() {
    var wrap = el("div", "tdl-erq");
    wrap.appendChild(el("h1", "", "Captured Notes"));
    wrap.appendChild(el("p", "tdl-muted",
      "Story notes captured across every trip for this narrator, newest " +
      "first. Captured notes are OFF for the memoir by default — this " +
      "screen is where an operator finds them and turns one on. " +
      "“In memoir” here is the same flag, and the same write, as " +
      "the toggle on the per-trip Story Notes list."));

    if (!st.personId) {
      wrap.appendChild(el("div", "tdl-empty",
        "No narrator is selected, and this review is per person."));
      return wrap;
    }
    if (st.capturedOff) {
      wrap.appendChild(el("div", "tdl-erq-off",
        "The trips lane is switched off on this server, so there is no " +
        "captured-note feed to read. Nothing is broken and nothing is lost."));
      return wrap;
    }
    if (st.capturedError) {
      wrap.appendChild(el("div", "tdl-error", st.capturedError));
    }

    var surfRail = el("div", "tdl-filter-rail tdl-filter-rail-row");
    CAPTURED_SURFACES.forEach(function (s) {
      surfRail.appendChild(btn(
        st.capturedSurface === s[0] ? "tdl-active" : "", s[1],
        function () { setCapturedSurface(s[0]); }));
    });
    wrap.appendChild(surfRail);

    var promRail = el("div", "tdl-filter-rail tdl-filter-rail-row");
    CAPTURED_PROMOTION.forEach(function (p) {
      promRail.appendChild(btn(
        st.capturedPromoted === p[0] ? "tdl-active" : "", p[1],
        function () { setCapturedPromoted(p[0]); }));
    });
    promRail.appendChild(btn(
      st.showHiddenCaptured ? "tdl-active" : "",
      st.showHiddenCaptured ? "Hiding hidden" : "Show hidden",
      function () { toggleCapturedHidden(); }));
    wrap.appendChild(promRail);

    // Counts describe the whole feed behind the page, not the filter --
    // that is the point of a counter strip on a screen whose default
    // filter hides most of what it is counting.
    var counts = (st.captured && st.captured.counts) || {};
    var strip = el("div", "tdl-erq-summary");
    strip.appendChild(el("span", "tdl-badge tdl-erq-depth",
      "Captured from Travel Doc modal " + (counts.travel_doc_modal || 0)));
    strip.appendChild(el("span", "tdl-muted",
      (counts.total || 0) + " notes · " + (counts.promoted || 0) +
      " in memoir · " + (counts.unpromoted || 0) + " not in memoir" +
      (counts.hidden ? " · " + counts.hidden + " hidden" : "")));
    wrap.appendChild(strip);

    var notes = (st.captured && st.captured.notes) || [];
    if (!notes.length) {
      wrap.appendChild(el("div", "tdl-empty",
        st.capturedBusy ? "Loading…" :
          "No captured notes match this filter."));
      return wrap;
    }

    notes.forEach(function (n) {
      var row = el("div", "tdl-note-row" + (n.hidden ? " tdl-row-hidden" : ""));
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge", n.source_type || "note"));
      badges.appendChild(el("span",
        n.source_surface === "travel_doc_modal"
          ? "tdl-badge tdl-badge-lori" : "tdl-badge",
        n.source_surface || "no surface"));
      badges.appendChild(el("span",
        n.include_in_memoir ? "tdl-flag-on" : "tdl-flag-off",
        n.include_in_memoir ? "In memoir ON" : "In memoir OFF"));
      if (n.hidden) {
        badges.appendChild(el("span", "tdl-badge tdl-badge-hidden", "hidden"));
      }
      badges.appendChild(el("span", "tdl-badge",
        n.trip_title || "untitled trip"));
      var scope = capturedScopeLabel(n);
      if (scope) badges.appendChild(el("span", "tdl-badge", scope));
      badges.appendChild(el("span", "tdl-muted",
        datePrefix(n.created_at) || "no date"));
      row.appendChild(badges);

      if (n.note_title) row.appendChild(el("strong", "", n.note_title));
      // Preview only. The full note stays where it is edited: this is a
      // finder, and a second full editor for the same row is how two
      // surfaces drift apart.
      var text = String(n.note_text || "");
      row.appendChild(el("p", "",
        text.length > 400 ? text.slice(0, 400) + "…" : text));

      var toggles = el("div", "tdl-note-toggles");
      var lab = el("label");
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = !!n.include_in_memoir;
      cb.addEventListener("change", function () {
        setCapturedMemoir(n.id, cb.checked, cb);
      });
      lab.appendChild(cb);
      lab.appendChild(el("span", "", "In memoir"));
      toggles.appendChild(lab);
      toggles.appendChild(el("span", "tdl-muted",
        "Promotes this note into the memoir trip lane. Nothing is copied " +
        "into the life-story archive."));
      row.appendChild(toggles);
      wrap.appendChild(row);
    });
    return wrap;
  }

  // ── Sources ──────────────────────────────────────────────────────────

  var SOURCE_FILTERS = [
    ["all", "All"],
    ["day", "Day-scoped"],
    ["unattached", "Unattached"],
    ["memoir", "In memoir"],
  ];

  function sourceMatchesFilter(s, f) {
    if (f === "day") return !!s.trip_day_id;
    if (f === "unattached") {
      return !s.trip_day_id && !s.trip_stop_id && !s.trip_region_id;
    }
    if (f === "memoir") return !!s.include_in_memoir;
    return true;
  }

  function renderSources() {
    var wrap = el("div");
    wrap.appendChild(el("h1", "", "Sources"));
    var rail = el("div", "tdl-filter-rail tdl-filter-rail-row");
    SOURCE_FILTERS.forEach(function (f) {
      var n = st.sources.filter(function (s) {
        return sourceMatchesFilter(s, f[0]);
      }).length;
      rail.appendChild(btn(st.sourceFilter === f[0] ? "tdl-active" : "",
        f[1] + " (" + n + ")",
        function () { st.sourceFilter = f[0]; renderAll(); }));
    });
    wrap.appendChild(rail);
    // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: per-tab Show hidden toggle.
    var hiddenSourceCount = st.sources.filter(function (s) {
      return !!s.hidden;
    }).length;
    wrap.appendChild(hiddenToggleRow("showHiddenSources", hiddenSourceCount,
      "sources"));
    // Phase 3C — intake goes in ABOVE the early return below. This tab
    // returns early when the active filter is empty, and an upload control
    // appended after that point would disappear from exactly the state
    // where the operator needs it most: no sources yet.
    wrap.appendChild(renderSourceIntakeBar());
    if (st.sourceIntake) {
      wrap.appendChild(renderIntakeResult(st.sourceIntake, function () {
        st.sourceIntake = null; renderAll();
      }));
    }
    var rows = st.sources.filter(function (s) {
      return sourceMatchesFilter(s, st.sourceFilter);
    });
    if (!rows.length) {
      wrap.appendChild(el("div", "tdl-empty",
        st.sources.length ? "No sources in this filter." : "No sources yet."));
      return wrap;
    }
    rows.forEach(function (s) {
      var row = el("div", "tdl-note-row" +
        (s.hidden ? " tdl-row-hidden" : ""));
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge", s.source_type || "other"));
      if (s.hidden) {
        badges.appendChild(el("span", "tdl-badge tdl-badge-hidden",
          "hidden" + (s.hidden_at ? " · " + datePrefix(s.hidden_at) : "")));
      }
      if (s.include_in_memoir) badges.appendChild(el("span", "tdl-badge", "in memoir"));
      if (s.trip_day_id) {
        var sd = dayById(s.trip_day_id);
        badges.appendChild(el("span", "tdl-badge tdl-badge-day",
          sd ? ("Day " + sd.day_index) : "day-scoped"));
      }
      row.appendChild(badges);
      row.appendChild(el("strong", "", s.title || s.filename || "Untitled source"));
      if (s.summary) row.appendChild(el("p", "", s.summary));
      if (s.link_url) row.appendChild(el("p", "tdl-muted", s.link_url));
      if (s.source_date) row.appendChild(el("p", "tdl-muted", "Dated " + s.source_date));
      // WO-EVIDENCE-LIFECYCLE-TRIP-FORCE-01: reversible hide / restore
      // (PATCH hidden — never a DELETE).
      var acts = el("div", "tdl-note-toggles");
      if (s.hidden) {
        acts.appendChild(btn("tdl-btn tdl-btn-small", "Restore",
          function () { restoreSource(s.id); }));
      } else {
        acts.appendChild(btn("tdl-btn tdl-btn-small", "Hide",
          function () { hideSource(s.id); }));
      }
      row.appendChild(acts);
      wrap.appendChild(row);
    });
    return wrap;
  }

  // ── Travelogue (mockup4) ─────────────────────────────────────────────

  var BLOCK_NAMES = {
    region_chapter: "Region Chapter",
    itinerary_tile: "Itinerary Tile",
    discovery_tile: "Discovery Tile",
    sensory_coda: "Sensory Coda",
  };

  function renderTravelogue() {
    var wrap = el("div");
    if (!st.travelogue) {
      wrap.appendChild(el("div", "tdl-empty", "Loading travelogue preview…"));
      return wrap;
    }
    var doc = el("div", "tdl-document");
    doc.appendChild(el("p", "tdl-doc-kicker", "Travelogue · evidence-rich outline"));
    var ov = st.travelogue.overview || {};
    doc.appendChild(el("h1", "", ov.title || (st.trip && st.trip.title) || "Trip"));
    Object.keys(ov).forEach(function (k) {
      if (k === "title") return;
      var v = ov[k];
      if (typeof v === "string" || typeof v === "number") {
        doc.appendChild(el("p", "tdl-muted", k.replace(/_/g, " ") + ": " + v));
      }
    });

    (st.travelogue.blocks || []).forEach(function (b) {
      var sec = el("div", "tdl-doc-section");
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge",
        BLOCK_NAMES[b.block_type] || b.block_type || "block"));
      (b.provenance_badges || []).forEach(function (p) {
        badges.appendChild(el("span",
          "tdl-badge" + (p === "draft" ? " tdl-badge-draft" : ""), p));
      });
      if (b.needs_review) badges.appendChild(el("span", "tdl-needs-review", "needs review"));
      sec.appendChild(badges);
      sec.appendChild(el("h3", "", b.title || ""));
      (b.prose_anchors || []).forEach(function (a) {
        var row = el("div", "tdl-anchor-row");
        row.appendChild(el("span", "tdl-anchor-label", a.label || ""));
        row.appendChild(el("span", "", a.value || ""));
        sec.appendChild(row);
      });
      doc.appendChild(sec);
    });

    var ir = st.travelogue.intake_review || {};
    var irSec = el("div", "tdl-doc-section");
    var irBadges = el("div", "tdl-note-badges");
    irBadges.appendChild(el("span", "tdl-badge tdl-badge-draft",
      "Intake review · " + (ir.count || 0) + " unpromoted"));
    irSec.appendChild(irBadges);
    irSec.appendChild(el("h3", "", "Awaiting review — not in the travelogue"));
    (ir.notes || []).forEach(function (n) {
      var row = el("div", "tdl-anchor-row");
      row.appendChild(el("span", "tdl-anchor-label", n.label || "note"));
      row.appendChild(el("span", "", n.value || ""));
      irSec.appendChild(row);
    });
    doc.appendChild(irSec);
    wrap.appendChild(doc);
    return wrap;
  }

  // ── Draft assistant (WO-TRAVEL-DOC-OPERATOR-DRAFT-ASSISTANT-01) ───────
  //
  // Operator writing aid: assembles approved evidence + notes + sources
  // for a scope and drafts a travelogue paragraph. Draft text only — the
  // operator edits then explicitly keeps it as a source_type='draft' note
  // (both promote flags OFF). No narrator state, no auto truth write.

  function _draftScopeOptions() {
    var opts = [{ key: "trip", label: "Whole trip", region_id: null,
      stop_id: null }];
    var regions = (st.tree && st.tree.regions) || [];
    regions.forEach(function (r) {
      opts.push({ key: "region:" + r.id, label: "▸ " + (r.title || "Region"),
        region_id: r.id, stop_id: null });
      (function walk(stops, depth) {
        (stops || []).forEach(function (s) {
          opts.push({ key: "stop:" + s.id,
            label: "  ".repeat(depth) + "· " + (s.location_name || "Stop"),
            region_id: null, stop_id: s.id });
          walk(s.children, depth + 1);
        });
      })(r.stops, 1);
    });
    return opts;
  }

  function _draftDefaultKey() {
    if (st.routeSel && st.routeSel.kind === "stop") return "stop:" + st.routeSel.id;
    if (st.routeSel && st.routeSel.kind === "region") return "region:" + st.routeSel.id;
    return "trip";
  }

  function _draftEnsure() {
    if (!st.draft) {
      st.draft = { scopeKey: _draftDefaultKey(), preview: null, result: null,
        instruction: "", status: "", busy: false, previewTried: false };
    }
    return st.draft;
  }

  function _draftScopeBody(d) {
    var opt = _draftScopeOptions().filter(function (o) {
      return o.key === d.scopeKey; })[0] || { region_id: null, stop_id: null };
    return { trip_region_id: opt.region_id, trip_stop_id: opt.stop_id };
  }

  function _draftLoadPreview() {
    var d = _draftEnsure();
    if (!st.trip) return;
    var body = _draftScopeBody(d);
    body.preview_only = true;
    d.previewTried = true; d.busy = true; d.status = ""; renderAll();
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/draft-section",
      { method: "POST", body: body })
      .then(function (out) {
        d.preview = out.context_preview; d.busy = false; renderAll();
      })
      .catch(function (e) {
        d.busy = false; d.status = "Preview failed: " + e.message; renderAll();
      });
  }

  function _draftRun() {
    var d = _draftEnsure();
    if (!st.trip || d.busy) return;
    var body = _draftScopeBody(d);
    body.instruction = d.instruction || "";
    d.busy = true; d.status = "Drafting…"; d.result = null; renderAll();
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/draft-section",
      { method: "POST", body: body })
      .then(function (out) {
        d.busy = false;
        d.preview = out.context_preview || d.preview;
        if (out.status === "no_material") {
          d.status = "Nothing approved to draft from yet — approve some photo "
            + "evidence, or add notes/sources for this scope.";
        } else if (out.status === "llm_unavailable") {
          d.status = "The local model isn't available right now.";
        } else if (out.draft) {
          d.result = out.draft; d.status = "";
        } else {
          d.status = "No draft returned.";
        }
        renderAll();
      })
      .catch(function (e) {
        d.busy = false; d.status = "Draft failed: " + e.message; renderAll();
      });
  }

  function _draftKeep() {
    var d = _draftEnsure();
    if (!st.trip || !d.result || d.busy) return;
    var scope = _draftScopeBody(d);
    var opt = _draftScopeOptions().filter(function (o) {
      return o.key === d.scopeKey; })[0] || { label: "trip" };
    d.busy = true; d.status = "Saving draft note…"; renderAll();
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/location-notes", {
      method: "POST",
      body: {
        note_title: "Draft — " + opt.label.replace(/^[▸·\s]+/, ""),
        note_text: d.result,
        source_type: "draft",
        include_in_memoir: false,
        include_in_interview_context: false,
        trip_region_id: scope.trip_region_id,
        trip_stop_id: scope.trip_stop_id,
      },
    }).then(function () {
      d.busy = false; d.result = null;
      d.status = "Saved as a draft note (in Story Notes). It is NOT in the "
        + "memoir until you promote it there.";
      return reloadNotes ? reloadNotes() : null;
    }).then(function () { renderAll(); })
      .catch(function (e) {
        d.busy = false; d.status = "Save failed: " + e.message; renderAll();
      });
  }

  function _draftPreviewCard(pv) {
    var card = el("div", "tdl-draft-preview");
    card.appendChild(el("div", "tdl-draft-preview-head",
      "What will be sent (operator-approved only)"));
    if (pv.summary) {
      var sm = el("div", "tdl-anchor-row");
      sm.appendChild(el("span", "tdl-anchor-label", "summary"));
      sm.appendChild(el("span", "", pv.summary));
      card.appendChild(sm);
    }
    (pv.anchors || []).forEach(function (a) {
      var row = el("div", "tdl-anchor-row");
      row.appendChild(el("span",
        "tdl-anchor-label" + (a.draft ? " tdl-anchor-draft" : ""),
        a.label));
      row.appendChild(el("span", "", a.value));
      card.appendChild(row);
    });
    (pv.notes || []).forEach(function (n) {
      var row = el("div", "tdl-anchor-row");
      row.appendChild(el("span", "tdl-anchor-label",
        n.source_type + (n.promoted ? " ✓" : "")));
      row.appendChild(el("span", "", n.text));
      card.appendChild(row);
    });
    (pv.sources || []).forEach(function (s) {
      var row = el("div", "tdl-anchor-row");
      row.appendChild(el("span", "tdl-anchor-label", "source"));
      row.appendChild(el("span", "", (s.title ? s.title + ": " : "") + s.text));
      card.appendChild(row);
    });
    if (!pv.has_material) {
      card.appendChild(el("div", "tdl-muted",
        "No approved material for this scope yet."));
    }
    if (pv.draft_anchor_count) {
      card.appendChild(el("div", "tdl-draft-excluded",
        pv.draft_anchor_count + " item(s) are still draft evidence — they are "
        + "included but written cautiously until you approve them in Photos."));
    }
    return card;
  }

  // ── Travel Document (WO-TRAVEL-DOC-CLOSEOUT-01) ────────────────────
  //
  // The finished deliverable. Everything else in this workspace gathers
  // evidence; this is where the operator sees what the document will
  // actually contain and exports it.
  //
  // WHY IT SHOWS WHAT IS LEFT OUT
  // The backend already filters on `include_in_memoir` in three places
  // (story notes, sources, and the photo appendix via memoir_only=True).
  // That filtering is correct, and it is also invisible: an operator who
  // cannot see the excluded count has no way to tell "the gravesite story
  // is not approved yet" from "the export is broken". Showing both sides
  // is what makes the approval gate legible instead of merely enforced.
  //
  // ONE EXPORTER. This calls the existing GET /export-docx and renders
  // the existing memoir-preview. It builds no document of its own.
  // HIDDEN ROWS ARE NOT IN THE DOCUMENT, and the counts must say so.
  //
  // `trip_memoir_preview` reads `location_notes_list(trip_id)` and
  // `sources_list(trip_id)` with the DEFAULT include_hidden=False, so
  // the export drops hidden rows server-side. But `st.notes` and
  // `st.sources` carry hidden rows whenever the "Show hidden" toggle is
  // on -- the list fetch adds ?include_hidden=1 -- so counting them
  // as "in the document" told the operator a hidden-but-approved note
  // would be in a file that will not contain it.
  //
  // Hidden rows are reported SEPARATELY rather than silently dropped.
  // An operator looking at a hidden row with its "In memoir" tick still
  // set needs to know the hide is what is keeping it out, not wonder
  // why the tick appears to do nothing.
  function _visible(r) { return !r.hidden; }

  function _docCounts() {
    var notes = (st.notes || []).filter(_visible);
    var sources = (st.sources || []).filter(_visible);
    var links = (st.photoLinks || []).filter(_visible);
    var hiddenApproved =
      (st.notes || []).filter(function (r) {
        return r.hidden && r.include_in_memoir; }).length
      + (st.sources || []).filter(function (r) {
        return r.hidden && r.include_in_memoir; }).length;
    function inMemoir(r) { return !!r.include_in_memoir; }
    return {
      notesIn: notes.filter(inMemoir).length,
      notesOut: notes.length - notes.filter(inMemoir).length,
      sourcesIn: sources.filter(inMemoir).length,
      sourcesOut: sources.length - sources.filter(inMemoir).length,
      photosIn: links.filter(inMemoir).length,
      photosOut: links.length - links.filter(inMemoir).length,
      hiddenApproved: hiddenApproved,
    };
  }

  function _docLine(label, inCount, outCount, whereToApprove) {
    var row = el("div", "tdl-doc-count");
    row.appendChild(el("span", "tdl-doc-count-in",
      String(inCount) + " " + label + (inCount === 1 ? "" : "s")
      + " in the document"));
    if (outCount > 0) {
      row.appendChild(el("span", "tdl-doc-count-out",
        outCount + " not approved — " + whereToApprove));
    }
    return row;
  }

  // Handle + URL for the export's object-URL cleanup, so destroy() can
  // clear a pending revoke rather than leaving a timer and a blob alive.
  var docExportRevokeTimer = null;
  var docExportRevokeUrl = null;

  function docExportRevokeNow() {
    if (docExportRevokeTimer) {
      clearTimeout(docExportRevokeTimer);
      docExportRevokeTimer = null;
    }
    if (docExportRevokeUrl) {
      try { URL.revokeObjectURL(docExportRevokeUrl); } catch (_) {}
      docExportRevokeUrl = null;
    }
  }

  function _exportTravelDocument() {
    if (!st.trip) return;
    var d = st.docExport || (st.docExport = {});
    if (d.busy) return;                       // no double-download
    d.busy = true; d.error = null; d.status = "Building the document…";
    renderAll();

    // Through `api()` with `raw`, so this download inherits the module's
    // one set of destroyed guards and its structured error handling. A
    // non-ok response is already turned into an Error carrying .status
    // and .body before it reaches here.
    //
    // Deliberately NOT a plain <a download>: a 503 (python-docx missing
    // on the server) would be saved to disk AS the document, and the
    // operator would open a Word file containing an error page.
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/export-docx",
        { raw: true }).then(function (r) {
      if (destroyed || !r) return null;
      // The filename the server chose, so the saved file matches what an
      // operator would see if they hit the route directly.
      var name = "travel-document.docx";
      var cd = r.headers.get("Content-Disposition") || "";
      var hit = /filename="([^"]+)"/.exec(cd);
      if (hit) name = hit[1];
      return r.blob().then(function (blob) { return { blob: blob, name: name }; });
    }).then(function (got) {
      if (destroyed || !got) return;
      var href = URL.createObjectURL(got.blob);
      var a = document.createElement("a");
      a.href = href; a.download = got.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      // Revoked on a timer rather than immediately: some browsers have
      // not finished reading the blob when click() returns, and revoking
      // too early produces an empty file with no error anywhere.
      //
      // The handle is STORED, so destroy() can clear it and revoke at
      // once. That is the stronger of the two timer shapes this module
      // uses -- a handle nobody stores cannot be cleared -- and it also
      // frees a multi-megabyte blob on teardown instead of holding it
      // for the rest of the minute.
      // Retire the PREVIOUS export's cleanup before taking ownership of
      // this one. Two exports inside the same minute otherwise overwrote
      // both module vars, and the first blob URL was left with no timer
      // pointing at it and no way to reach it -- leaked for the life of
      // the page, holding a multi-megabyte buffer. Revoking first also
      // means the pending timer cannot fire later and revoke a URL that
      // by then belongs to a different download.
      docExportRevokeNow();
      docExportRevokeUrl = href;
      docExportRevokeTimer = setTimeout(function () {
        if (destroyed) return;
        docExportRevokeTimer = null;
        docExportRevokeUrl = null;
        URL.revokeObjectURL(href);
      }, 60000);
      d.busy = false;
      d.status = "Saved " + got.name;
      renderAll();
    }).catch(function (e) {
      if (destroyed) return;
      d.busy = false; d.status = null;
      d.error = e && e.message ? e.message : String(e);
      renderAll();
    });
  }

  function renderTravelDocument() {
    // Reuses `.tdl-document` so the finished write-up looks like the
    // page it is, the same as the travelogue surface; `tdl-doc` carries
    // only this tab's own hooks.
    var wrap = el("div", "tdl-document tdl-doc");
    if (!st.trip) {
      wrap.appendChild(el("div", "tdl-empty", "Select a trip first."));
      return wrap;
    }
    var d = st.docExport || (st.docExport = {});
    var c = _docCounts();
    var p = st.memoirPreview;

    wrap.appendChild(el("p", "tdl-doc-kicker",
      "Travel document · the finished, shareable write-up of this trip"));
    wrap.appendChild(el("h1", "", st.trip.title || "Travel document"));
    wrap.appendChild(el("p", "tdl-muted",
      "This is built from what you have approved. Anything you have not "
      + "ticked for the memoir stays out of it."));

    // What is in, and what is not.
    var counts = el("div", "tdl-doc-counts");
    counts.appendChild(_docLine("story note", c.notesIn, c.notesOut,
      "tick “In memoir” on the Story Notes tab"));
    counts.appendChild(_docLine("source", c.sourcesIn, c.sourcesOut,
      "tick “In memoir” on the Sources tab"));
    counts.appendChild(_docLine("photo", c.photosIn, c.photosOut,
      "tick “In memoir” on the Photos tab"));
    wrap.appendChild(counts);

    if (c.hiddenApproved > 0) {
      counts.appendChild(el("div", "tdl-doc-count-hidden",
        c.hiddenApproved + " hidden "
        + (c.hiddenApproved === 1 ? "row is" : "rows are")
        + " ticked for the memoir but stay out of the document while "
        + "hidden. Restore them if they belong in it."));
    }

    if (c.notesIn === 0 && c.sourcesIn === 0 && c.photosIn === 0) {
      wrap.appendChild(el("div", "tdl-doc-empty-note",
        "Nothing is approved for the memoir yet, so the document would "
        + "contain only the trip outline — the regions, stops and dates. "
        + "That is a valid document; it just has no stories in it yet."));
    }

    // Export.
    var bar = el("div", "tdl-doc-actions");
    var exportBtn = btn("tdl-btn tdl-btn-primary",
      d.busy ? "Building…" : "Export Travel Document",
      _exportTravelDocument);
    exportBtn.disabled = !!d.busy;
    bar.appendChild(exportBtn);
    if (d.status) bar.appendChild(el("span", "tdl-doc-status", d.status));
    wrap.appendChild(bar);
    if (d.error) {
      var err = el("div", "tdl-error", d.error);
      err.appendChild(btn("tdl-btn", "Dismiss", function () {
        d.error = null; renderAll();
      }));
      wrap.appendChild(err);
    }

    // The preview: exactly the rows the DOCX renders, from the same route.
    if (!p) {
      wrap.appendChild(el("div", "tdl-muted", "Loading the document…"));
      return wrap;
    }
    wrap.appendChild(el("h2", "", "What is in the document"));
    (p.part_one || []).forEach(function (region) {
      var card = el("div", "tdl-doc-region");
      card.appendChild(el("h3", "", region.region || "(untitled region)"));
      (region.story_notes || []).forEach(function (n) {
        card.appendChild(el("p", "tdl-doc-note", n.note_text || ""));
      });
      (region.stops || []).forEach(function (stop) {
        var sc = el("div", "tdl-doc-stop");
        sc.appendChild(el("div", "tdl-doc-stop-name",
          stop.location_name || "(unnamed stop)"));
        (stop.story_notes || []).forEach(function (n) {
          sc.appendChild(el("p", "tdl-doc-note", n.note_text || ""));
        });
        card.appendChild(sc);
      });
      wrap.appendChild(card);
    });
    if ((p.part_two || []).length) {
      wrap.appendChild(el("h2", "", "Themes"));
      (p.part_two || []).forEach(function (t) {
        wrap.appendChild(el("p", "tdl-doc-theme",
          (t.theme || "") + (t.stops && t.stops.length
            ? " — " + t.stops.join(", ") : "")));
      });
    }
    return wrap;
  }

  function renderDraft() {
    var wrap = el("div", "tdl-draft");
    if (!st.trip) {
      wrap.appendChild(el("div", "tdl-empty", "Select a trip first."));
      return wrap;
    }
    var d = _draftEnsure();
    if (!d.previewTried && !d.busy) _draftLoadPreview();

    wrap.appendChild(el("p", "tdl-doc-kicker",
      "Draft assistant · operator writing aid — no memoir write"));
    wrap.appendChild(el("h1", "", "Draft a section"));
    wrap.appendChild(el("p", "tdl-muted",
      "Pick a scope. I assemble the approved evidence, notes, and sources you "
      + "already gathered, and draft a paragraph you can edit and keep. Keeping "
      + "a draft never promotes it to the memoir."));

    // scope selector
    var scopeRow = el("div", "tdl-draft-row");
    scopeRow.appendChild(el("label", "tdl-draft-label", "Scope"));
    var sel = el("select", "tdl-draft-select");
    _draftScopeOptions().forEach(function (o) {
      var op = el("option", null, o.label);
      op.value = o.key;
      if (o.key === d.scopeKey) op.selected = true;
      sel.appendChild(op);
    });
    sel.addEventListener("change", function () {
      d.scopeKey = sel.value; d.preview = null; d.result = null; d.status = "";
      d.previewTried = false;
      _draftLoadPreview();
    });
    scopeRow.appendChild(sel);
    wrap.appendChild(scopeRow);

    // context preview
    if (d.busy && d.preview === null) {
      wrap.appendChild(el("div", "tdl-muted", "Loading evidence…"));
    } else if (d.preview) {
      wrap.appendChild(_draftPreviewCard(d.preview));
    }

    // instruction
    var instrWrap = el("div", "tdl-draft-row");
    instrWrap.appendChild(el("label", "tdl-draft-label", "Instruction"));
    var instr = el("textarea", "tdl-draft-instruction");
    instr.placeholder = "e.g. Draft a warm memoir paragraph in Chris's voice.";
    instr.value = d.instruction || "";
    instr.addEventListener("input", function () { d.instruction = instr.value; });
    instrWrap.appendChild(instr);
    wrap.appendChild(instrWrap);

    var actions = el("div", "tdl-draft-actions");
    var draftBtn = btn("tdl-btn tdl-btn-gold",
      d.busy ? "Working…" : "✍ Draft this section", _draftRun);
    if (d.busy) draftBtn.disabled = true;
    actions.appendChild(draftBtn);
    wrap.appendChild(actions);

    if (d.status) wrap.appendChild(el("div", "tdl-draft-status", d.status));

    // editable result
    if (d.result) {
      var resCard = el("div", "tdl-draft-result");
      resCard.appendChild(el("div", "tdl-draft-preview-head",
        "Draft (editable — not saved yet)"));
      var ta = el("textarea", "tdl-draft-resulttext");
      ta.value = d.result;
      ta.addEventListener("input", function () { d.result = ta.value; });
      resCard.appendChild(ta);
      var rowActions = el("div", "tdl-draft-actions");
      rowActions.appendChild(btn("tdl-btn tdl-btn-gold",
        "Keep as draft note", _draftKeep));
      rowActions.appendChild(btn("tdl-btn",
        "Discard", function () { d.result = null; d.status = ""; renderAll(); }));
      resCard.appendChild(rowActions);
      wrap.appendChild(resCard);
    }
    return wrap;
  }

  // ── Lori pane (surface=travel_doc_modal — full pane, own WebSocket) ──

  var loriPane = {
    ws: null,
    node: null,
    log: null,
    bubble: null,
    turn: 0,
    dayId: null,
    photoLinkId: null,

    anchorDay: function (dayId) {
      this.dayId = dayId || null;
      this.paintScope();
    },
    anchorPhoto: function (photoLinkId) {
      this.photoLinkId = photoLinkId || null;
      this.paintScope();
    },

    // WO-TRIP-LANE-AUDIT-FIXPACK-01 (H3): drop ALL per-trip Lori state on
    // a trip switch so Trip B can never combine its trip id with a
    // day/photo anchor or transcript left over from Trip A.
    reset: function () {
      try { if (this.ws) this.ws.close(); } catch (e) {}
      this.ws = null;
      this.dayId = null;
      this.photoLinkId = null;
      this.bubble = null;
      this.turn = 0;
      if (this.log) this.log.textContent = "";
      if (this.node) this.paintScope();
    },

    scope: function () {
      var day = this.dayId ? dayById(this.dayId) : null;
      var stopId = (day && day.trip_stop_id) ||
        (st.routeSel && st.routeSel.kind === "stop" ? st.routeSel.id : null);
      var regionId = (day && day.trip_region_id) ||
        (st.routeSel && st.routeSel.kind === "stop" ? st.routeSel.regionId : null);
      return {
        source_surface: "travel_doc_modal",
        person_id: st.personId,
        active_trip_id: st.trip && st.trip.id,
        active_trip_day_id: this.dayId,
        active_trip_region_id: regionId || null,
        active_trip_stop_id: stopId || null,
        active_photo_link_id: this.photoLinkId,
        selected_kind: this.photoLinkId ? "photo" :
          (this.dayId ? "day" : (stopId ? "stop" : "trip")),
      };
    },

    build: function () {
      var pane = el("div", "tdl-lori-pane");
      var head = el("div", "tdl-lori-head");
      head.appendChild(el("span", "", "Talk with Lori"));
      // [The header carried a second line reading "surface:
      // travel_doc_modal". Retired 2026-07-28 by Phase A instruction 6.
      // It named the server-side source_surface value this pane sends,
      // which is still sent and still asserted by the suite --- it was a
      // developer's note left where the operator reads.]
      pane.appendChild(head);
      this.scopeRow = el("div", "tdl-lori-scope");
      pane.appendChild(this.scopeRow);
      this.log = el("div", "tdl-lori-log");
      this.log.setAttribute("aria-live", "polite");
      pane.appendChild(this.log);
      var inRow = el("div", "tdl-lori-input-row");
      this.input = el("input");
      this.input.placeholder = "Say something about this trip…";
      var self = this;
      this.input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") self.send();
      });
      inRow.appendChild(this.input);
      inRow.appendChild(btn("tdl-btn tdl-btn-primary", "Send", function () { self.send(); }));
      pane.appendChild(inRow);
      this.drawer = el("div", "tdl-lori-drawer");
      this.drawer.appendChild(el("strong", "", "Lori Capture Intake Sandbox"));
      this.drawerList = el("div", "tdl-muted",
        "Captured notes from this conversation appear here — In memoir OFF, Use with Lori OFF.");
      this.drawer.appendChild(this.drawerList);
      pane.appendChild(this.drawer);
      this.node = pane;
      this.paintScope();
      this.refreshDrawer();
      return pane;
    },

    paintScope: function () {
      if (!this.scopeRow) return;
      this.scopeRow.innerHTML = "";
      this.scopeRow.appendChild(el("b", "", "Scope:"));
      this.scopeRow.appendChild(el("span", "",
        "Trip · " + ((st.trip && st.trip.title) || "—")));
      var self = this;
      if (this.dayId) {
        var day = dayById(this.dayId);
        var chip = el("span", "tdl-lori-chip");
        chip.appendChild(el("span", "",
          day ? dayChipText(day) : "Day"));
        // Phase A instruction 6: the chip already names the day in
        // words. [It also carried " active_trip_day_id=<8 chars>…".
        // Retired 2026-07-28 --- the identifier is in the day
        // workspace's More details section for anyone who needs it.]
        var x = btn("", "✕", function () { self.anchorDay(null); });
        x.title = "Unanchor day";
        chip.appendChild(x);
        this.scopeRow.appendChild(chip);
      }
      if (this.photoLinkId) {
        var link = st.photoLinks.filter(function (l) {
          return l.id === self.photoLinkId;
        })[0];
        var pchip = el("span", "tdl-lori-chip");
        if (link) {
          var im = thumbImg(link.photo_id, "anchored photo", false);
          pchip.appendChild(im);
        }
        pchip.appendChild(el("span", "", "Photo anchored"));
        var px = btn("", "✕", function () { self.anchorPhoto(null); });
        px.title = "Unanchor photo";
        pchip.appendChild(px);
        this.scopeRow.appendChild(pchip);
      }
    },

    connect: function () {
      // Phase 1.1 — never open a socket for a mount that is gone.
      if (destroyed) return;
      if (this.ws && this.ws.readyState === 1) return;
      var url = st.apiBase.replace(/^http/, "ws") + "/api/chat/ws";
      var self = this;
      try { this.ws = new WebSocket(url); } catch (e) {
        this.line("system", "Lori connection failed — is the backend running?");
        return;
      }
      // Phase 1.1 — pin the socket this handler belongs to. close() does
      // not retract already-queued message events, and reset() (trip
      // switch) nulls this.ws while the old socket may still deliver one
      // more frame. Comparing identity covers BOTH: a frame from a socket
      // that is no longer the pane's current one is dropped, so a Trip A
      // token can never append into Trip B's transcript.
      var sock = this.ws;
      this.ws.onmessage = function (ev) {
        if (destroyed || self.ws !== sock) return;
        var j = {};
        try { j = JSON.parse(ev.data); } catch (_) { return; }
        if (j.type === "token" && j.delta) self.append(j.delta);
        if (j.type === "done") {
          self.finish(j.final_text);
          Promise.all([reloadNotes(), reloadDays()])
            .then(function () {
              if (destroyed || self.ws !== sock) return;
              self.refreshDrawer();
            })
            .catch(function () {});
        }
      };
    },

    line: function (who, text) {
      var d = el("div", "tdl-lori-line tdl-lori-" + who, text);
      this.log.appendChild(d);
      this.log.scrollTop = this.log.scrollHeight;
      return d;
    },
    append: function (t) {
      if (!this.bubble) this.bubble = this.line("lori", "");
      this.bubble.textContent += t;
      this.log.scrollTop = this.log.scrollHeight;
    },
    finish: function (finalText) {
      if (this.bubble && finalText) this.bubble.textContent = finalText;
      this.bubble = null;
    },

    send: function () {
      var text = (this.input.value || "").trim();
      if (!text || !st.trip) return;
      if (!this.ws || this.ws.readyState !== 1) this.connect();
      this.line("user", text);
      this.input.value = "";
      this.turn += 1;
      var payload = {
        type: "start_turn",
        session_id: "tdlab_" + st.trip.id,
        message: text,
        params: {
          person_id: st.personId,
          surface: "travel_doc_modal",
          modal_scope: this.scope(),
          turn_id: "tdlab_t" + this.turn,
        },
      };
      var self = this;
      (function trySend(attempt) {
        // Phase 1.1 — the FIRST of the file's two timers. Without this
        // the retry ladder keeps running for up to 5s (20 × 250ms) past
        // destroy() and ends by writing "Lori connection unavailable."
        // into a log node that was detached from the document.
        //
        // Corrected 2026-07-28 by WO-TRAVEL-DOC-GOOGLE-PHOTOS-PICKER-01
        // Phase 2D, which added the second: the Google Photos picker's
        // selection poll, up in the evidence section. This comment said
        // "the one timer in the file", and it was true when it was
        // written. It is corrected rather than deleted because the two
        // timers are guarded DIFFERENTLY and a reader comparing them
        // should be able to see that it was a choice. This one is a
        // self-re-entering ladder with no handle kept, so the guard is
        // the `if (destroyed) return;` on the line below and there is
        // nothing for destroy() to clear. The picker's is armed from a
        // module var, so it is guarded twice over: the same check in its
        // callback, AND pickerPollStop() in destroy(). Neither approach
        // is wrong; a handle nobody stores cannot be cleared.
        if (destroyed) return;
        if (self.ws && self.ws.readyState === 1) {
          self.ws.send(JSON.stringify(payload));
        } else if (attempt < 20) {
          setTimeout(function () { trySend(attempt + 1); }, 250);
        } else {
          self.line("system", "Lori connection unavailable.");
        }
      })(0);
    },

    refreshDrawer: function () {
      if (!this.drawerList || !st.trip) return;
      var self = this;
      var mine = st.notes.filter(function (n) {
        if (n.source_surface !== "travel_doc_modal") return false;
        if (self.dayId) return n.trip_day_id === self.dayId;
        return true;
      }).slice(-6).reverse();
      if (!mine.length) return;
      this.drawerList.innerHTML = "";
      this.drawerList.className = "";
      var dl = this.drawerList;
      mine.forEach(function (n) {
        var row = el("div", "tdl-lori-drawer-row");
        row.appendChild(el("span", "tdl-lori-drawer-src", "from Lori modal"));
        if (n.photo_link_id) row.appendChild(el("span", "tdl-lori-drawer-src", "📷"));
        if (n.trip_day_id) {
          var nd = dayById(n.trip_day_id);
          row.appendChild(el("span", "tdl-lori-drawer-src",
            nd ? ("Day " + nd.day_index) : "day"));
        }
        row.appendChild(el("span", "", " " + (n.note_text || "").slice(0, 120)));
        row.appendChild(el("small", "tdl-muted",
          " · In memoir OFF · Use with Lori OFF"));
        dl.appendChild(row);
      });
    },
  };

  // ── Lori in context: right drawer over Trip Plan ─────────────────────

  // ── WO-LIVE-TRIP-COMPANION-01 Vertical Slice 1 (2026-07-30) ──────────
  //
  // The live trip, and the calendar that shows what was said on it.
  //
  // Two subsystems existed here and never met. The travel document knew
  // about trips, generated day cards, photos and sources. Lori knew how
  // to hold an interview and persist a turn. Nothing joined them, so a
  // conversation held while looking at Day 3 of a trip left no mark on
  // Day 3 of that trip. This section is the join, on the operator's
  // side of it.
  //
  // WHAT IS DELIBERATELY NOT HERE:
  //
  // - No second conversation store. Every word on this timeline is read
  //   back out of `turns` at render time by the server. The link table
  //   holds identifiers and nothing else, so there is no copy of the
  //   narrative to fall out of date with the original.
  // - No second data model for the calendar. The days are the same
  //   `trip_days` rows the day cards render, through the same
  //   windowed/preserved partition, so the calendar cannot disagree
  //   with the board next to it.
  // - No inferred "active". `live_state` is set by the operator with
  //   Start trip and Finish trip, and it lives in the database. The
  //   trip does not become active because today's date fell inside it,
  //   and it does not stop being active because the browser reloaded.
  //   That is the whole reason it is a column and not a variable.
  //
  // WHY THE SELECTED DAY IS SERVER-SIDE. The Lori pane already had a
  // `modal_scope.active_trip_day_id`, and it is a browser fact: it is
  // built per mount, it dies on reload, and the placement service is
  // forbidden from reading it. What a completed turn is filed against
  // is `trips.active_trip_day_id`, written by the operator's choice of
  // day and read back on the server. The two carry nearly the same name
  // because they mean the same thing to a person --- and only one of
  // them still means it after a restart.

  var LIVE_STATE_LABEL = {
    planning: "Planning",
    active: "On this trip now",
    completed: "Trip finished",
    archived: "Archived",
  };

  // Placement vocabulary, in operator language. The distinction between
  // the first two is required, not cosmetic: a day the operator chose is
  // a confirmed placement and a day inferred from a timestamp is a
  // suggestion, and a screen that renders them identically has quietly
  // turned a guess into a decision.
  var PLACEMENT_LABEL = {
    confirmed: "Confirmed day",
    suggested: "Suggested day",
    needs_day: "Needs a day",
    rejected: "Not on this trip",
  };

  function tripLiveState(trip) {
    var t = trip || st.trip;
    return (t && t.live_state) || "planning";
  }

  function tripSelectedDayId() {
    return (st.trip && st.trip.active_trip_day_id) || null;
  }

  function activeTripRow() {
    for (var i = 0; i < st.trips.length; i++) {
      if (st.trips[i].live_state === "active") return st.trips[i];
    }
    return null;
  }

  // Every lifecycle change goes through here so there is exactly one
  // place that knows a refused transition is a 409 carrying the trip
  // that is in the way. The refusal is deliberate: two trips at once is
  // the operator's problem to resolve, and finishing one of them behind
  // their back is not a resolution.
  function setTripLiveState(state) {
    if (!st.trip) return Promise.resolve();
    var t = encodeURIComponent(st.trip.id);
    st.error = "";
    return api("/api/trips/" + t + "/live-state",
               { method: "POST", body: { state: state } })
      .then(function () { return refreshTripsPreservingSelection(st.trip.id); })
      .then(function () {
        if (st.tripCal) return loadTripCalendar();
        renderAll();
      })
      .catch(function (e) {
        var other = e && e.body && e.body.detail &&
          e.body.detail.conflict;
        if (e && e.status === 409 && other) {
          st.error = "You are already on “" +
            (other.title || "another trip") + "”. Finish that trip " +
            "first, or go to it from the left rail.";
        } else {
          st.error = e.message;
        }
        renderAll();
      });
  }

  // The durable answer to "which day am I on". Called when the operator
  // opens Lori on a day and from the day picker in the calendar, because
  // both of those ARE the operator choosing the day --- and nothing
  // else may write it.
  function setTripSelectedDay(dayId) {
    if (!st.trip) return Promise.resolve();
    var t = encodeURIComponent(st.trip.id);
    return api("/api/trips/" + t + "/selected-day",
               { method: "POST", body: { trip_day_id: dayId || null } })
      .then(function (out) {
        if (out && out.trip) {
          st.trip.live_state = out.trip.live_state;
          st.trip.active_trip_day_id = out.trip.active_trip_day_id;
        }
        renderAll();
      })
      .catch(function (e) {
        st.error = e.message;
        renderAll();
      });
  }

  // ── the trip status bar, above the calendar ──────────────────────────

  function renderTripLiveBar() {
    var state = tripLiveState();
    var bar = el("div", "tdl-live-bar tdl-live-" + state);

    var chip = el("span", "tdl-live-chip", LIVE_STATE_LABEL[state] || state);
    bar.appendChild(chip);

    var selDayId = tripSelectedDayId();
    var selDay = selDayId ? dayById(selDayId) : null;
    var line = el("span", "tdl-live-line");
    if (state === "active" && selDay) {
      line.textContent = "Talking about Day " + selDay.day_index + " — " +
        prettyDate(selDay.date) + ". What you say to Lori is filed here.";
    } else if (state === "active") {
      line.textContent = "No day chosen yet. Open a day and start talking, " +
        "and it will be filed to that day.";
    } else if (state === "planning") {
      line.textContent = "Start the trip when you set off. Until then " +
        "nothing you say to Lori is filed to a day.";
    } else if (state === "completed") {
      line.textContent = "This trip is finished. Everything said on it is " +
        "still here.";
    } else {
      line.textContent = "This trip is put away.";
    }
    bar.appendChild(line);

    var acts = el("span", "tdl-live-actions");
    if (state === "planning") {
      acts.appendChild(btn("tdl-btn tdl-btn-gold", "Start trip",
        function () { setTripLiveState("active"); }));
    } else if (state === "active") {
      acts.appendChild(btn("tdl-btn", "Finish trip",
        function () { setTripLiveState("completed"); }));
    } else {
      acts.appendChild(btn("tdl-btn", "Reopen trip",
        function () { setTripLiveState("active"); }));
    }
    acts.appendChild(btn("tdl-btn", "▤ Trip timeline",
      function () { openTripCalendar(); }));
    bar.appendChild(acts);

    // Resume: when a DIFFERENT trip is the one running, say so here and
    // offer the way back to it. Without this the operator's only clue
    // that they are on the wrong screen is the refusal they get when
    // they press Start trip.
    var running = activeTripRow();
    if (running && (!st.trip || running.id !== st.trip.id)) {
      var res = el("div", "tdl-live-resume");
      res.appendChild(el("span", "", "You are on “" +
        (running.title || "a trip") + "” right now."));
      res.appendChild(btn("tdl-btn tdl-btn-small", "Resume that trip",
        function () { selectTrip(running.id); }));
      bar.appendChild(res);
    }
    return bar;
  }

  // ── the calendar / timeline modal ────────────────────────────────────

  function openTripCalendar(dayId) {
    if (!st.trip) return;
    // WO-LIVE-TRIP-COMPANION-02 step 1. Every other overlay opener asks
    // this first --- openLoriOverlay, openLoriOverlayForPhoto, the day
    // card, the route selectors --- and Trip timeline was the one that
    // did not. Opening it calls renderAll(), which rebuilds the day
    // inspector from st.days and throws away whatever the operator had
    // typed into it, with no warning and nothing to undo with. The text
    // was never saved, so nothing in the database is wrong afterwards;
    // it is still the operator's writing, destroyed by a button that
    // gave no sign it would do that. Fix the loss before adding a
    // second place to type.
    if (dayFormDirtyBlocks()) return;
    st.tripCal = {
      dayId: dayId || tripSelectedDayId() || st.selectedDayId || null,
      days: [], preserved: [], items: [], unplaced: [],
      unplacedCount: 0, showUnplaced: false,
      busy: true, error: "",
      // Step 3 state: the one open inline row, the timeline pane's own
      // scroll position, and whether the panel has taken focus yet.
      edit: null, scroll: 0, focused: false,
    };
    renderAll();
    loadTripCalendar();
  }

  // Every way out of the modal --- Close, the scrim, "Open this day",
  // "Open this conversation", Escape on the panel --- comes through
  // here, so the dirty guard only has to be written once. Returns false
  // when the close was refused, and callers that were going somewhere
  // afterwards must check it.
  function closeTripCalendar() {
    if (timelineEditDirtyBlocks()) return false;
    st.tripCal = null;
    renderAll();
    return true;
  }

  function loadTripCalendar() {
    if (!st.trip || !st.tripCal) return Promise.resolve();
    var t = encodeURIComponent(st.trip.id);
    st.tripCal.busy = true;
    renderAll();
    return api("/api/trips/" + t + "/calendar")
      .then(function (out) {
        if (!st.tripCal) return null;
        st.tripCal.days = out.days || [];
        st.tripCal.preserved = out.preserved || [];
        st.tripCal.unplacedCount = out.unplaced_count || 0;
        st.tripCal.error = "";
        // The modal opens on the day the operator is on. Failing that
        // it opens on the first day of the trip, because a timeline
        // that opens on nothing and says "choose a day" has made the
        // operator do the one piece of work the screen exists to save
        // them --- and it looks broken, which is worse. Opening on
        // Day 1 is not a claim that Day 1 was chosen: the rail shows
        // "You are here" only on the trip\'s actual selected day, and
        // that badge is the only thing that speaks for the operator.
        if (!st.tripCal.dayId && out.selected_day_id) {
          st.tripCal.dayId = out.selected_day_id;
        }
        if (!st.tripCal.dayId) {
          var first = (st.tripCal.days[0] || st.tripCal.preserved[0]);
          if (first) st.tripCal.dayId = first.id;
        }
        return loadTripDayTimeline(st.tripCal.dayId);
      })
      .catch(function (e) {
        if (!st.tripCal) return;
        st.tripCal.busy = false;
        st.tripCal.error = e.message;
        renderAll();
      });
  }

  function loadTripDayTimeline(dayId) {
    if (!st.trip || !st.tripCal) return Promise.resolve();
    st.tripCal.dayId = dayId || null;
    if (!dayId) {
      st.tripCal.items = [];
      st.tripCal.busy = false;
      renderAll();
      return Promise.resolve();
    }
    var t = encodeURIComponent(st.trip.id);
    var d = encodeURIComponent(dayId);
    st.tripCal.busy = true;
    renderAll();
    return api("/api/trips/" + t + "/days/" + d + "/timeline")
      .then(function (out) {
        if (!st.tripCal) return;
        st.tripCal.items = out.items || [];
        st.tripCal.busy = false;
        st.tripCal.error = "";
        renderAll();
      })
      .catch(function (e) {
        if (!st.tripCal) return;
        st.tripCal.items = [];
        st.tripCal.busy = false;
        st.tripCal.error = e.message;
        renderAll();
      });
  }

  function loadTripUnplaced() {
    if (!st.trip || !st.tripCal) return Promise.resolve();
    var t = encodeURIComponent(st.trip.id);
    return api("/api/trips/" + t + "/timeline/unplaced")
      .then(function (out) {
        if (!st.tripCal) return;
        st.tripCal.unplaced = out.items || [];
        st.tripCal.unplacedCount = out.count || 0;
        renderAll();
      })
      .catch(function (e) {
        if (!st.tripCal) return;
        st.tripCal.error = e.message;
        renderAll();
      });
  }

  // Moving is the operator overruling an automatic placement, so it is
  // recorded as their choice and it never deletes: sending a
  // conversation off a day returns it to the reconciliation list, where
  // it stays visible until somebody decides where it belongs.
  function moveTripTurnLink(linkId, dayId) {
    var l = encodeURIComponent(linkId);
    return api("/api/trips/trip-turn-links/" + l + "/move",
               { method: "POST", body: { trip_day_id: dayId || null } })
      .then(function () {
        if (!st.tripCal) return null;
        return loadTripCalendar().then(function () {
          if (st.tripCal && st.tripCal.showUnplaced) return loadTripUnplaced();
        });
      })
      .catch(function (e) {
        if (!st.tripCal) return;
        st.tripCal.error = e.message;
        renderAll();
      });
  }

  // ── inline row editing in the timeline ────────────────────────────────
  // WO-LIVE-TRIP-COMPANION-02 step 3.
  //
  // The rule this whole section obeys: the timeline edits the records it
  // displays; it never becomes the owner of copied trip content. There
  // is no timeline-edit table, no draft store, no second copy of
  // anybody's words. An expanded row writes straight back to the record
  // the projection read from, through the PATCH endpoint that already
  // owns it, and then re-reads the day.
  //
  // What it deliberately cannot edit, and why:
  //   * a conversation's words. Placement can change; the narrator and
  //     Lori turn rows are the record of what was actually said, and a
  //     viewer does not get to rewrite them.
  //   * Places visited and Meals on the day card. Those are lists, not
  //     prose. A text box over them would quietly flatten structure into
  //     a sentence, and the day inspector already edits them properly.
  //   * approval for Lori. Editing a caption and approving a caption are
  //     two different operator decisions; this surface only does the
  //     first one.
  var TL_EDIT_FIELDS = {
    photo: [{ name: "caption", label: "Photo caption", rows: 2 }],
    note: [
      { name: "note_title", label: "Title", rows: 1 },
      { name: "note_text", label: "Note", rows: 5 },
    ],
    source: [
      { name: "title", label: "Title", rows: 1 },
      { name: "summary", label: "Summary", rows: 4 },
    ],
    day_text: [{ name: "text", label: "", rows: 3 }],
    // WO-LIVE-TRIP-COMPANION-02 step 5. Quick capture rides the same
    // editor as the edits: one dirty guard, one Escape rule, one Save,
    // one place where a mistake can be made. The only difference is
    // that it POSTs a new row instead of PATCHing an existing one, and
    // it is the one editor here that creates anything at all.
    new_note: [
      { name: "note_title", label: "Title (optional)", rows: 1 },
      { name: "note_text", label: "Note", rows: 4 },
    ],
  };

  // The day-card columns that are plain prose. places_visited_json and
  // meals_json are absent on purpose --- see above.
  var TL_DAY_TEXT_FIELDS = [
    "main_location", "lodging_base",
    "morning_notes", "afternoon_notes", "evening_notes",
  ];

  function photoLinkById(linkId) {
    var rows = st.photoLinks || [];
    for (var i = 0; i < rows.length; i++) {
      if (rows[i] && rows[i].id === linkId) return rows[i];
    }
    return null;
  }

  // Which record does this row own, and may it be typed into? Returns
  // null for everything the timeline is not allowed to rewrite.
  function timelineEditTarget(item) {
    if (!item) return null;
    var kind = String(item.kind || "");
    if (kind === "photo") {
      if (!item.link_id) return null;
      return {
        kind: kind, key: "photo:" + item.link_id, ownerId: item.link_id,
        field: null, label: "Photo caption",
        values: { caption: item.caption || "" },
      };
    }
    if (kind === "note") {
      if (!item.note_id) return null;
      return {
        kind: kind, key: "note:" + item.note_id, ownerId: item.note_id,
        field: null, label: "Story note",
        values: { note_title: item.title || "", note_text: item.text || "" },
      };
    }
    if (kind === "source") {
      if (!item.source_id) return null;
      return {
        kind: kind, key: "source:" + item.source_id, ownerId: item.source_id,
        field: null, label: "Source",
        values: { title: item.title || "", summary: item.summary || "" },
      };
    }
    if (kind === "day_text") {
      var f = String(item.field || "");
      if (TL_DAY_TEXT_FIELDS.indexOf(f) < 0) return null;
      var dayId = String(item.id || "").split(":")[0];
      if (!dayId) return null;
      return {
        kind: kind, key: "day_text:" + dayId + ":" + f, ownerId: dayId,
        field: f, label: item.label || "On the day card",
        values: { text: item.text || "" },
      };
    }
    return null;
  }

  function timelineEdit() {
    return (st.tripCal && st.tripCal.edit) || null;
  }

  function tlOpenEditorFor(item) {
    var ed = timelineEdit();
    if (!ed) return null;
    var t = timelineEditTarget(item);
    return (t && t.key === ed.key) ? ed : null;
  }

  // Same contract as dayFormDirtyBlocks(): returns true when the caller
  // must ABORT. No native dialog --- lab doctrine forbids confirm() ---
  // and nothing typed is discarded. The row's own Save/Cancel is
  // flashed and scrolled to, and the operator decides.
  function timelineEditDirtyBlocks() {
    var ed = timelineEdit();
    if (!ed || !ed.dirty) return false;
    (ed.badges || []).forEach(function (b) {
      b.classList.add("tdl-dirty-on");
      b.classList.add("tdl-dirty-flash");
      b.textContent = "Unsaved changes — Save or Cancel first";
    });
    (ed.saveButtons || []).forEach(function (b) { b.disabled = false; });
    var sb = (ed.saveButtons || [])[0];
    if (sb && sb.scrollIntoView) {
      try { sb.scrollIntoView({ block: "center" }); } catch (e) {}
    }
    return true;
  }

  // One active editor at a time. Opening a second row while the first
  // one holds unsaved text is blocked, not silently resolved.
  function openTimelineEdit(item) {
    if (!st.tripCal) return;
    var t = timelineEditTarget(item);
    if (!t) return;
    var cur = timelineEdit();
    if (cur && cur.key === t.key) return;
    if (timelineEditDirtyBlocks()) return;
    var vals = {};
    var orig = {};
    Object.keys(t.values).forEach(function (k) {
      vals[k] = t.values[k];
      orig[k] = t.values[k];
    });
    var first = (TL_EDIT_FIELDS[t.kind] || [])[0];
    st.tripCal.edit = {
      key: t.key, kind: t.kind, ownerId: t.ownerId, field: t.field,
      label: t.label, values: vals, original: orig,
      dirty: false, saving: false, error: "",
      focus: first ? first.name : null,
      saveButtons: [], badges: [],
    };
    renderAll();
  }

  // Quick capture: a note written where the operator already is,
  // filed on the day they are already looking at. Save is off until
  // something has been typed, so an accidental click captures nothing.
  function openTimelineNewNote(dayId) {
    if (!st.tripCal || !dayId) return;
    var cur = timelineEdit();
    if (cur && cur.key === "new_note:" + dayId) return;
    if (timelineEditDirtyBlocks()) return;
    st.tripCal.edit = {
      key: "new_note:" + dayId, kind: "new_note", ownerId: dayId,
      field: null, label: "New note", method: "POST",
      values: { note_title: "", note_text: "" },
      original: { note_title: "", note_text: "" },
      dirty: false, saving: false, error: "",
      focus: "note_text", saveButtons: [], badges: [],
    };
    renderAll();
  }

  function cancelTimelineEdit() {
    if (!st.tripCal) return;
    st.tripCal.edit = null;
    renderAll();
  }

  // In place, never renderAll(): renderAll() empties the root, so a
  // repaint per keystroke would take the caret out of the box the
  // operator is typing into and lose the word they were mid-way through.
  function markTimelineEditDirty(ed) {
    var d = false;
    Object.keys(ed.values).forEach(function (k) {
      if (String(ed.values[k]) !== String(ed.original[k])) d = true;
    });
    ed.dirty = d;
    (ed.badges || []).forEach(function (b) {
      b.textContent = "Unsaved changes";
      b.classList.remove("tdl-dirty-flash");
      if (d) b.classList.add("tdl-dirty-on");
      else b.classList.remove("tdl-dirty-on");
    });
    (ed.saveButtons || []).forEach(function (b) { b.disabled = !d; });
  }

  // The PATCH body, or a refusal the row shows without closing itself.
  function timelineEditBody(ed) {
    var v = ed.values;
    function t(k) { return String(v[k] == null ? "" : v[k]).trim(); }
    if (ed.kind === "photo") {
      // caption ONLY. caption_approved_for_lori is never sent from here,
      // in either direction: approval is a separate decision, made on
      // the photo, about words somebody actually read.
      return { body: { caption: t("caption") } };
    }
    if (ed.kind === "note") {
      if (!t("note_text")) return { error: "A note needs some text." };
      var b = { note_text: t("note_text") };
      if (t("note_title")) b.note_title = t("note_title");
      else b.clear_title = true;
      return { body: b };
    }
    if (ed.kind === "source") {
      if (!t("title")) return { error: "A source needs a title." };
      return { body: { title: t("title"), summary: t("summary") } };
    }
    if (ed.kind === "day_text") {
      var out = {};
      if (t("text")) out[ed.field] = t("text");
      else out["clear_" + ed.field] = true;
      return { body: out };
    }
    if (ed.kind === "new_note") {
      if (!t("note_text")) return { error: "A note needs some text." };
      // Scoped to the day it was written on, and to that day's region
      // and stop if it has them --- the same shape the note drawer
      // already writes, so a note captured here is not a second kind of
      // note with a different provenance.
      var day = dayById(ed.ownerId) || {};
      return { body: {
        note_text: t("note_text"),
        note_title: t("note_title") || null,
        trip_day_id: ed.ownerId,
        trip_region_id: day.trip_region_id || null,
        trip_stop_id: day.trip_stop_id || null,
        source_type: "operator",
      } };
    }
    return { error: "This row cannot be edited here." };
  }

  function timelineEditPath(ed) {
    var id = encodeURIComponent(ed.ownerId);
    if (ed.kind === "photo") return "/api/trips/photo-links/" + id;
    if (ed.kind === "note") return "/api/trips/location-notes/" + id;
    if (ed.kind === "source") return "/api/trips/sources/" + id;
    if (ed.kind === "day_text") return "/api/trips/days/" + id;
    if (ed.kind === "new_note") {
      if (!st.trip) return null;
      return "/api/trips/" + encodeURIComponent(st.trip.id) +
        "/location-notes";
    }
    return null;
  }

  // The workspace behind the modal reads the same records. Refresh the
  // owning list too, or closing the timeline shows the old words on the
  // day card and the operator cannot tell which one is true.
  function timelineOwnerReload(kind) {
    if (kind === "photo") return reloadPhotoLinks();
    if (kind === "note") return reloadNotes();
    if (kind === "source") return reloadSources();
    if (kind === "day_text") return reloadDays();
    // A new note changes both the note list and the day's own counts.
    if (kind === "new_note") {
      return Promise.all([reloadNotes(), reloadDays()]);
    }
    return Promise.resolve();
  }

  function saveTimelineEdit() {
    var ed = timelineEdit();
    if (!ed || ed.saving) return;
    var made = timelineEditBody(ed);
    if (made.error) {
      ed.error = made.error;
      renderAll();
      return;
    }
    var path = timelineEditPath(ed);
    if (!path) return;
    ed.saving = true;
    ed.error = "";
    renderAll();
    // PATCH is the rule --- this surface edits records that already
    // exist. POST appears once, for quick capture, and only because the
    // row it writes does not exist yet.
    api(path, { method: ed.method || "PATCH", body: made.body })
      .then(function () { return timelineOwnerReload(ed.kind); })
      .then(function () {
        if (!st.tripCal) return null;
        st.tripCal.edit = null;
        // One call refreshes the day-rail counts and the selected day's
        // timeline, and it keeps the selected day: nothing else moves.
        return loadTripCalendar();
      })
      .catch(function (e) {
        // The editor stays open with the typed text still in it. A save
        // that fails and also loses the writing is two problems.
        if (!st.tripCal || st.tripCal.edit !== ed) return;
        ed.saving = false;
        ed.error = e.message || "That did not save.";
        renderAll();
      });
  }

  function tlEditButton(item) {
    return btn("tdl-btn tdl-btn-small tdl-tl-edit", "Edit", function () {
      openTimelineEdit(item);
    });
  }

  function renderTimelineEditor(ed) {
    var form = el("form", "tdl-tl-editor");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      saveTimelineEdit();
    });
    // Escape closes the row, not the modal. stopPropagation() is what
    // makes that ordering true: the panel's own Escape handler never
    // sees the key while a row is open.
    form.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      e.preventDefault();
      cancelTimelineEdit();
    });

    ed.saveButtons = [];
    ed.badges = [];

    if (ed.kind === "new_note") {
      form.appendChild(el("h4", "tdl-tl-title", "New note on this day"));
    }

    (TL_EDIT_FIELDS[ed.kind] || []).forEach(function (spec) {
      var input;
      if (spec.rows > 1) {
        input = el("textarea");
        input.rows = spec.rows;
      } else {
        input = el("input");
        input.type = "text";
      }
      input.value = ed.values[spec.name] == null ? "" : ed.values[spec.name];
      input.setAttribute("data-tl-field", spec.name);
      input.disabled = !!ed.saving;
      input.addEventListener("input", function () {
        ed.values[spec.name] = input.value;
        markTimelineEditDirty(ed);
      });
      input.addEventListener("focus", function () { ed.focus = spec.name; });
      form.appendChild(field(spec.label || ed.label, input));
    });

    if (ed.kind === "photo") {
      // Said out loud, every time. The endpoint takes approval off when
      // the caption text changes --- approval always refers to the words
      // that were actually reviewed --- and the operator should not
      // discover that afterwards.
      var link = photoLinkById(ed.ownerId);
      var approved = !!(link && link.caption_approved_for_lori);
      form.appendChild(el("p", "tdl-muted tdl-tl-approval", approved ?
        "This caption is approved for Lori. Saving a change takes that " +
        "approval off, because approval is for the words that were " +
        "actually read." :
        "Saving the caption does not approve it for Lori. That is a " +
        "separate step on the photo."));
    }

    // Above the buttons, and it stays until the operator acts: an error
    // that closes the editor takes the evidence away with it.
    if (ed.error) form.appendChild(el("div", "tdl-error", ed.error));

    var foot = el("div", "tdl-tl-editor-foot");
    var badge = el("span", "tdl-dirty-badge", "Unsaved changes");
    if (ed.dirty) badge.classList.add("tdl-dirty-on");
    ed.badges.push(badge);
    foot.appendChild(badge);
    var save = btn("tdl-btn tdl-btn-primary tdl-btn-small",
      ed.saving ? "Saving…" : "Save", saveTimelineEdit);
    save.disabled = !!ed.saving || !ed.dirty;
    ed.saveButtons.push(save);
    foot.appendChild(save);
    var cancel = btn("tdl-btn tdl-btn-small", "Cancel", cancelTimelineEdit);
    cancel.disabled = !!ed.saving;
    foot.appendChild(cancel);
    form.appendChild(foot);
    return form;
  }

  // Called at the end of renderAll(). A repaint that came from anywhere
  // else must not take the caret out of an open row.
  function restoreTimelineEditFocus() {
    if (!st.tripCal) return;
    var panel = root.querySelector(".tdl-cal-panel");
    if (!panel) return;
    var ed = st.tripCal.edit;
    if (!ed) {
      if (!st.tripCal.focused && panel.focus) {
        st.tripCal.focused = true;
        try { panel.focus(); } catch (e) {}
      }
      return;
    }
    var sel = ed.focus ?
      panel.querySelector('.tdl-tl-editor [data-tl-field="' + ed.focus + '"]') :
      panel.querySelector(".tdl-tl-editor [data-tl-field]");
    if (!sel || !sel.focus) return;
    try {
      sel.focus();
      var n = String(sel.value == null ? "" : sel.value).length;
      if (sel.setSelectionRange) sel.setSelectionRange(n, n);
    } catch (e) {}
  }

  // ── placement editing (WO-LIVE-TRIP-COMPANION-02 step 4) ─────────────
  //
  // Putting a thing on the right day is the edit that actually gets made
  // during a trip: the clock guessed, or the operator is filing an hour
  // later from the truck. Photographs and conversations move for the
  // same reasons, so they move the same way and with the same words.
  //
  // Neither one deletes. "Take off this day" leaves the record on the
  // trip --- a conversation returns to the reconciliation list, a
  // photograph stays in the Photos tab --- because a wrong day is not a
  // reason to lose the thing.
  function tlMovePicker(o) {
    var pick = el("select", "tdl-tl-move");
    var none = el("option", "", o.placeholder || "Move to…");
    none.value = "";
    pick.appendChild(none);
    (st.tripCal ? st.tripCal.days : []).forEach(function (d) {
      var op = el("option", "",
        "Day " + d.day_index + " · " + prettyDate(d.date));
      op.value = d.id;
      if (d.id === o.currentDayId) op.selected = true;
      pick.appendChild(op);
    });
    if (o.allowOff) {
      var off = el("option", "", "Take off this day");
      off.value = "__none__";
      pick.appendChild(off);
    }
    pick.addEventListener("change", function () {
      var v = pick.value;
      if (!v) return;
      // A move reloads the day and repaints, so it would discard an open
      // row's typed text exactly the way opening the timeline used to.
      if (timelineEditDirtyBlocks()) {
        pick.value = o.currentDayId || "";
        return;
      }
      o.onPick(v === "__none__" ? null : v);
    });
    return pick;
  }

  // A photograph moves by updating the ONE trip_photo_links row it
  // already has. No second placement record, and no "also show on
  // another day" here: a photograph on two days is a claim that it was
  // taken twice, and this surface is not where that gets decided.
  function moveTripPhotoLink(linkId, fromDayId, toDayId) {
    if (!st.trip || !st.tripCal) return Promise.resolve();
    var t = encodeURIComponent(st.trip.id);
    // Detach names the day it is coming off; attach names the day it is
    // going to. Both are the existing day-photo routes.
    var onDay = toDayId || fromDayId || st.tripCal.dayId;
    if (!onDay) return Promise.resolve();
    var path = "/api/trips/" + t + "/days/" + encodeURIComponent(onDay) +
      "/photos/" + (toDayId ? "link" : "unlink");
    return api(path, { method: "POST", body: { photo_link_ids: [linkId] } })
      .then(function () { return reloadPhotoLinks(); })
      .then(function () {
        if (!st.tripCal) return null;
        // Refreshes the rail counts on both days and the open day's
        // timeline, and keeps the selected day where it was.
        return loadTripCalendar();
      })
      .catch(function (e) {
        if (!st.tripCal) return;
        st.tripCal.error = e.message;
        renderAll();
      });
  }

  function clockOf(iso) {
    var s = String(iso || "");
    var m = s.match(/T(\d{2}):(\d{2})/);
    if (m) return m[1] + ":" + m[2];
    m = s.match(/^(\d{2}):(\d{2})/);
    return m ? m[1] + ":" + m[2] : "";
  }

  // The day timeline carries five kinds of item now, not one. The
  // first cut rendered conversations and nothing else, which was fine
  // while the endpoint only returned conversations and became a lie the
  // moment the endpoint told the truth about the rest of the day. Each
  // kind renders from the fields the projection already carries; none
  // of them holds a copy of anything.
  var TL_KIND_LABEL = {
    conversation: "Talk with Lori",
    photo: "Photograph",
    note: "Story note",
    source: "Source",
    day_text: "On the day card",
  };

  function renderTimelineItem(item, opts) {
    opts = opts || {};
    var kind = String(item.kind || "conversation");
    if (kind === "photo") return renderTimelinePhoto(item);
    if (kind === "note") return renderTimelineNote(item);
    if (kind === "source") return renderTimelineSource(item);
    if (kind === "day_text") return renderTimelineDayText(item);
    return renderTimelineConversation(item, opts);
  }

  function tlHead(item, label) {
    var head = el("div", "tdl-tl-head");
    head.appendChild(el("span", "tdl-tl-when", clockOf(item.at) || "—"));
    head.appendChild(el("span", "tdl-tl-kind", label));
    return head;
  }

  // Source navigation for the non-conversation kinds. Every one of them
  // already has a home --- the day card and its inspector --- so the
  // timeline sends the operator there rather than growing a second
  // place to look at a photograph.
  function openTripDayCard(dayId) {
    if (!closeTripCalendar()) return;
    setTab("plan");
    st.selectedDayId = dayId;
    renderAll();
  }

  function renderTimelinePhoto(item) {
    var row = el("article", "tdl-tl-item tdl-tl-photo");
    row.appendChild(tlHead(item, TL_KIND_LABEL.photo));
    if (item.photo_id) {
      var fig = el("div", "tdl-tl-thumb");
      // Eager, for the reason recorded at thumbImg: this panel floats
      // above the page with its own scrolling body, so the lazy hint
      // never fires and the operator gets an empty box.
      fig.appendChild(thumbImg(item.photo_id, item.caption || "trip photo",
        false));
      row.appendChild(fig);
    }
    // Expand in place. The rest of the timeline stays where it is ---
    // no drawer, no second navigation layer, no new Escape ladder.
    var edP = tlOpenEditorFor(item);
    if (edP) {
      row.appendChild(renderTimelineEditor(edP));
    } else if (item.caption) {
      row.appendChild(el("p", "tdl-tl-said", item.caption));
    }
    var acts = el("div", "tdl-tl-actions");
    if (!edP && timelineEditTarget(item)) acts.appendChild(tlEditButton(item));
    if (!edP && item.link_id) {
      var onDay = item.trip_day_id || (st.tripCal && st.tripCal.dayId) || null;
      acts.appendChild(tlMovePicker({
        currentDayId: onDay,
        placeholder: "Move to…",
        allowOff: !!onDay,
        onPick: function (dayId) {
          moveTripPhotoLink(item.link_id, onDay, dayId);
        },
      }));
    }
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Open this day",
      function () {
        var target = item.trip_day_id || (st.tripCal && st.tripCal.dayId);
        if (target) openTripDayCard(target);
      }));
    row.appendChild(acts);
    return row;
  }

  function renderTimelineNote(item) {
    var row = el("article", "tdl-tl-item tdl-tl-note");
    row.appendChild(tlHead(item, TL_KIND_LABEL.note));
    var edN = tlOpenEditorFor(item);
    if (edN) {
      row.appendChild(renderTimelineEditor(edN));
    } else {
      if (item.title) row.appendChild(el("h4", "tdl-tl-title", item.title));
      if (item.text) row.appendChild(el("p", "tdl-tl-said", item.text));
    }
    var acts = el("div", "tdl-tl-actions");
    if (!edN && timelineEditTarget(item)) acts.appendChild(tlEditButton(item));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Open this day",
      function () {
        var target = item.trip_day_id || (st.tripCal && st.tripCal.dayId);
        if (target) openTripDayCard(target);
      }));
    row.appendChild(acts);
    return row;
  }

  function renderTimelineSource(item) {
    var row = el("article", "tdl-tl-item tdl-tl-source");
    row.appendChild(tlHead(item, TL_KIND_LABEL.source));
    var edS = tlOpenEditorFor(item);
    if (edS) {
      row.appendChild(renderTimelineEditor(edS));
    } else {
      if (item.title) row.appendChild(el("h4", "tdl-tl-title", item.title));
      if (item.summary) row.appendChild(el("p", "tdl-tl-said", item.summary));
    }
    var acts = el("div", "tdl-tl-actions");
    if (!edS && timelineEditTarget(item)) acts.appendChild(tlEditButton(item));
    acts.appendChild(btn("tdl-btn tdl-btn-small", "Open this day",
      function () {
        var target = item.trip_day_id || (st.tripCal && st.tripCal.dayId);
        if (target) openTripDayCard(target);
      }));
    row.appendChild(acts);
    return row;
  }

  function renderTimelineDayText(item) {
    var row = el("article", "tdl-tl-item tdl-tl-daytext");
    var head = el("div", "tdl-tl-head");
    head.appendChild(el("span", "tdl-tl-when", "—"));
    head.appendChild(el("span", "tdl-tl-kind", item.label || "On the day card"));
    row.appendChild(head);
    // This row had no actions at all until now. It is the operator's own
    // writing about the day, so it is the first thing they will want to
    // fix from here --- number one on the list of useful edits.
    var edD = tlOpenEditorFor(item);
    if (edD) {
      row.appendChild(renderTimelineEditor(edD));
    } else if (item.text) {
      row.appendChild(el("p", "tdl-tl-said", item.text));
    }
    if (!edD && timelineEditTarget(item)) {
      var actsD = el("div", "tdl-tl-actions");
      actsD.appendChild(tlEditButton(item));
      row.appendChild(actsD);
    }
    return row;
  }

  function renderTimelineConversation(item, opts) {
    opts = opts || {};
    var row = el("article", "tdl-tl-item");

    var head = el("div", "tdl-tl-head");
    var when = clockOf(item.at);
    head.appendChild(el("span", "tdl-tl-when", when || "—"));
    head.appendChild(el("span", "tdl-tl-kind", "Talk with Lori"));
    var status = item.placement_status || "confirmed";
    head.appendChild(el("span", "tdl-tl-badge tdl-tl-" + status,
      PLACEMENT_LABEL[status] || status));
    row.appendChild(head);

    if (item.narrator_said) {
      var u = el("p", "tdl-tl-said tdl-tl-narrator");
      u.appendChild(el("span", "tdl-tl-who", "You"));
      u.appendChild(document.createTextNode(" " + item.narrator_said));
      row.appendChild(u);
    }
    if (item.lori_said) {
      var a = el("p", "tdl-tl-said tdl-tl-lori");
      a.appendChild(el("span", "tdl-tl-who", "Lori"));
      a.appendChild(document.createTextNode(" " + item.lori_said));
      row.appendChild(a);
    }
    if (!item.narrator_said && !item.lori_said) {
      // The link survived and the words did not. Say that plainly
      // instead of rendering an empty card: an item with no text is
      // exactly the kind of thing somebody needs to be able to find.
      row.appendChild(el("p", "tdl-muted",
        "This conversation is linked here but its words could not be " +
        "read back."));
    }

    var acts = el("div", "tdl-tl-actions");
    // Source navigation. A timeline entry the operator cannot open is a
    // claim without a receipt: this returns to the conversation surface,
    // on the day the entry is filed under.
    if (item.trip_day_id) {
      acts.appendChild(btn("tdl-btn tdl-btn-small", "Open this conversation",
        function () {
          var target = item.trip_day_id;
          if (!closeTripCalendar()) return;
          st.selectedDayId = target;
          openLoriOverlay(target);
        }));
    }

    // Same control the photographs get. Only the placement record
    // changes: the narrator and Lori turn rows are not touched, here or
    // in the endpoint behind it.
    acts.appendChild(tlMovePicker({
      currentDayId: item.trip_day_id || null,
      placeholder: opts.unplaced ? "Put on a day…" : "Move to…",
      allowOff: !!item.trip_day_id,
      onPick: function (dayId) { moveTripTurnLink(item.link_id, dayId); },
    }));
    row.appendChild(acts);
    return row;
  }

  function renderTripCalendarModal() {
    var cal = st.tripCal;
    var wrap = el("div", "tdl-drawer-scrim tdl-cal-scrim");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeTripCalendar();
    });
    var panel = el("section", "tdl-cal-panel");
    // Focusable so the panel can hear Escape at all. An open row stops
    // the key before it gets here, which is what makes "Escape cancels
    // the row before it closes the modal" true.
    panel.tabIndex = -1;
    panel.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      closeTripCalendar();
    });

    var head = el("header", "tdl-cal-head");
    var ht = el("div");
    ht.appendChild(el("h2", "", "Trip timeline"));
    ht.appendChild(el("p", "tdl-muted",
      (st.trip && st.trip.title ? st.trip.title + " · " : "") +
      (LIVE_STATE_LABEL[tripLiveState()] || tripLiveState())));
    head.appendChild(ht);
    head.appendChild(btn("tdl-btn", "Close", closeTripCalendar));
    panel.appendChild(head);

    if (cal.error) panel.appendChild(el("div", "tdl-error", cal.error));

    var body = el("div", "tdl-cal-body");

    // Left: every day of the trip.
    var list = el("nav", "tdl-cal-days");
    if (!cal.days.length && !cal.preserved.length) {
      list.appendChild(el("p", "tdl-muted",
        "This trip has no day cards yet. Set the trip dates and the day " +
        "cards are created for you."));
    }
    function dayButton(d, preserved) {
      var b = el("button", "tdl-cal-day" +
        (d.id === cal.dayId ? " tdl-active" : "") +
        (preserved ? " tdl-cal-day-preserved" : ""));
      b.type = "button";
      b.appendChild(el("span", "tdl-cal-day-index", "Day " + d.day_index));
      b.appendChild(el("span", "tdl-cal-day-date", prettyDate(d.date)));
      b.appendChild(el("span", "tdl-cal-day-title", dayLabel(d)));
      // What the day actually holds, in the operator\'s words. Counting
      // conversations alone made a day with a photograph and a story
      // note read as empty, and the rail then disagreed with the day
      // card two inches away.
      var bits = [];
      function part(n, one, many) {
        n = n || 0;
        if (n) bits.push(n === 1 ? one : (n + " " + many));
      }
      part(d.conversation_count, "1 conversation", "conversations");
      part(d.photo_count, "1 photo", "photos");
      part(d.note_count, "1 note", "notes");
      part(d.source_count, "1 source", "sources");
      b.appendChild(el("span", "tdl-cal-day-count", bits.join(" · ")));
      if (d.id === tripSelectedDayId()) {
        b.appendChild(el("span", "tdl-cal-day-here", "You are here"));
      }
      b.addEventListener("click", function () {
        // Changing the day rebuilds the pane the open row lives in, so
        // ask first and then close the row rather than leaving an
        // editor attached to a record that is no longer on screen.
        if (timelineEditDirtyBlocks()) return;
        if (st.tripCal) st.tripCal.edit = null;
        loadTripDayTimeline(d.id);
      });
      return b;
    }
    cal.days.forEach(function (d) { list.appendChild(dayButton(d, false)); });
    if (cal.preserved.length) {
      list.appendChild(el("div", "tdl-cal-sep", "Outside the trip dates"));
      cal.preserved.forEach(function (d) {
        list.appendChild(dayButton(d, true));
      });
    }
    body.appendChild(list);

    // Right: what happened on the chosen day.
    var pane = el("div", "tdl-cal-timeline");
    var selDay = cal.dayId ? dayById(cal.dayId) : null;
    if (!cal.dayId) {
      pane.appendChild(el("p", "tdl-empty",
        "Choose a day on the left to see what happened on it."));
    } else {
      var th = el("div", "tdl-cal-tl-head");
      th.appendChild(el("h3", "", selDay ?
        ("Day " + selDay.day_index + " · " + prettyDate(selDay.date)) :
        "This day"));
      if (cal.dayId !== tripSelectedDayId()) {
        th.appendChild(btn("tdl-btn tdl-btn-small", "Talk about this day",
          function () {
            if (timelineEditDirtyBlocks()) return;
            setTripSelectedDay(cal.dayId).then(function () {
              if (st.tripCal) loadTripCalendar();
            });
          }));
      } else {
        th.appendChild(el("span", "tdl-cal-day-here", "You are here"));
      }
      pane.appendChild(th);

      // Quick capture. During a trip this modal is where the operator
      // already is, so the three things they do most often start from
      // here instead of from a screen they have to go and find. The
      // note is written in place; photographs and Lori need the whole
      // workspace, so those hand over to it rather than pretending to
      // fit inside a panel.
      var qc = el("div", "tdl-cal-quick");
      qc.appendChild(btn("tdl-btn tdl-btn-small", "+ Note", function () {
        openTimelineNewNote(cal.dayId);
      }));
      qc.appendChild(btn("tdl-btn tdl-btn-small", "+ Photos", function () {
        var d = cal.dayId;
        if (!closeTripCalendar()) return;
        setTab("plan");
        openPhotoPicker(d);
      }));
      qc.appendChild(btn("tdl-btn tdl-btn-small", "Talk with Lori",
        function () {
          var d = cal.dayId;
          if (!closeTripCalendar()) return;
          openLoriOverlay(d);
        }));
      pane.appendChild(qc);
      if (cal.edit && cal.edit.kind === "new_note" &&
          cal.edit.ownerId === cal.dayId) {
        pane.appendChild(renderTimelineEditor(cal.edit));
      }

      if (cal.busy) {
        pane.appendChild(el("p", "tdl-muted", "Loading…"));
      } else if (!cal.items.length) {
        pane.appendChild(el("p", "tdl-empty",
          "Nothing has been recorded on this day yet — no conversation, " +
          "photo, note or source. Open the day and talk with Lori, and " +
          "it will appear here."));
      } else {
        cal.items.forEach(function (it) {
          pane.appendChild(renderTimelineItem(it, {}));
        });
      }
    }
    body.appendChild(pane);
    panel.appendChild(body);

    // The reconciliation list. It is shown as a footer rather than a
    // separate screen because it is not a queue somebody is supposed to
    // work through --- it is the small number of conversations that
    // completed with no day chosen, and it must stay visible instead of
    // being tidied away.
    var foot = el("footer", "tdl-cal-foot");
    if (cal.unplacedCount) {
      var fl = el("div", "tdl-cal-foot-line");
      fl.appendChild(el("span", "", cal.unplacedCount === 1 ?
        "1 conversation on this trip is not on a day yet." :
        cal.unplacedCount + " conversations on this trip are not on a day yet."));
      fl.appendChild(btn("tdl-btn tdl-btn-small",
        cal.showUnplaced ? "Hide them" : "Show them",
        function () {
          cal.showUnplaced = !cal.showUnplaced;
          if (cal.showUnplaced) loadTripUnplaced(); else renderAll();
        }));
      foot.appendChild(fl);
      if (cal.showUnplaced) {
        var ul = el("div", "tdl-cal-unplaced");
        cal.unplaced.forEach(function (it) {
          ul.appendChild(renderTimelineItem(it, { unplaced: true }));
        });
        foot.appendChild(ul);
      }
    } else {
      foot.appendChild(el("span", "tdl-muted",
        "Every conversation on this trip is on a day."));
    }
    panel.appendChild(foot);

    wrap.appendChild(panel);
    return wrap;
  }

  function openLoriOverlay(dayId) {
    if (dayFormDirtyBlocks()) return;
    st.tab = "plan";
    st.loriReturnTab = "plan";
    st.selectedDayId = dayId || st.selectedDayId;
    // WO-LIVE-TRIP-COMPANION-01 VS1. Opening Lori on a day IS the
    // operator choosing the day, so it is written through to
    // trips.active_trip_day_id -- the durable answer the placement
    // service reads when the turn completes. It is fire-and-forget on
    // purpose: the write is one local UPDATE and it lands in
    // milliseconds, while the earliest a turn can complete is after the
    // operator has typed a sentence and the model has answered it. A
    // failure here is not allowed to stop the conversation from opening;
    // the worst case is a turn that lands on the reconciliation list
    // with its words intact, which is the outcome this lane is built to
    // guarantee anyway.
    if (dayId && tripLiveState() === "active" &&
        tripSelectedDayId() !== dayId) {
      setTripSelectedDay(dayId);
    }
    st.photoPickerDayId = null;
    st.noteDrawerDayId = null;
    loriPane.anchorDay(dayId || null);
    st.loriOverlay = true;
    renderAll();
    loriPane.connect();
    if (loriPane.input) loriPane.input.focus();
  }

  // Photo-scoped Lori: the SAME overlay drawer, opened over the Photos
  // tab. Back returns to Photos with scroll position and the selected
  // photo intact (closeLoriOverlay never touches tab/selection/scroll).
  function openLoriOverlayForPhoto(photoLinkId) {
    if (dayFormDirtyBlocks()) return;
    st.tab = "photos";
    st.loriReturnTab = "photos";
    st.photoPickerDayId = null;
    st.noteDrawerDayId = null;
    loriPane.anchorPhoto(photoLinkId || null);
    st.loriOverlay = true;
    renderAll();
    loriPane.connect();
    if (loriPane.input) loriPane.input.focus();
  }

  function closeLoriOverlay() {
    // Back to Trip Plan / Back to Photos — the underlying tab, selected
    // day/photo, and workspace scroll position are all preserved
    // (renderAll restores st.mainScroll; st.tab is never changed here).
    st.loriOverlay = false;
    renderAll();
  }

  function renderLoriOverlay() {
    var wrap = el("div", "tdl-drawer-scrim tdl-lori-overlay");
    wrap.addEventListener("click", function (e) {
      if (e.target === wrap) closeLoriOverlay();
    });
    var drawer = el("aside", "tdl-drawer tdl-lori-overlay-panel");

    var head = el("div", "tdl-drawer-head");
    var ht = el("div");
    ht.appendChild(el("div", "tdl-kicker", "Talk with Lori"));
    // Phase A instruction 6. [This line read the trip title followed by
    // " · active_trip_day_id=<8 chars>…" and, for a photo-anchored
    // conversation, " · active_photo_link_id=<8 chars>…". Retired
    // 2026-07-28: it was telling the operator what Lori was scoped to,
    // which is worth saying, in the vocabulary of the request payload,
    // which is not. The payload itself is unchanged --- scope() still
    // sends active_trip_day_id and active_photo_link_id, because that is
    // a wire contract and not a caption.]
    var scopeLine = el("div", "tdl-lori-overlay-scope");
    scopeLine.appendChild(el("strong", "", (st.trip && st.trip.title) || "Trip"));
    if (loriPane.dayId) {
      var sday = dayById(loriPane.dayId);
      scopeLine.appendChild(el("span", "tdl-muted",
        " · " + (sday ? dayChipText(sday) : "this day")));
    }
    if (loriPane.photoLinkId) {
      scopeLine.appendChild(el("span", "tdl-muted", " · one photo"));
    }
    ht.appendChild(scopeLine);
    head.appendChild(ht);
    // Context-aware back label: the drawer returns wherever it came from.
    head.appendChild(btn("tdl-btn tdl-btn-small",
      st.loriReturnTab === "photos" ? "‹ Back to Photos" : "‹ Back to Trip Plan",
      closeLoriOverlay));
    drawer.appendChild(head);

    if (loriPane.dayId) {
      var day = dayById(loriPane.dayId);
      var chipRow = el("div", "tdl-lori-overlay-chip-row");
      var chip = el("span", "tdl-lori-chip");
      chip.appendChild(el("span", "", day ? dayChipText(day) : "Day"));
      var x = btn("", "✕", function () {
        loriPane.anchorDay(null);
        renderAll();
      });
      x.title = "Unanchor day";
      chip.appendChild(x);
      chipRow.appendChild(chip);
      drawer.appendChild(chipRow);
    }

    if (loriPane.photoLinkId) {
      var plink = st.photoLinks.filter(function (l) {
        return l.id === loriPane.photoLinkId;
      })[0];
      var pRow = el("div", "tdl-lori-overlay-chip-row");
      var pchip = el("span", "tdl-lori-chip");
      if (plink) {
        var pim = thumbImg(plink.photo_id, "anchored photo", false);
        pchip.appendChild(pim);
      }
      pchip.appendChild(el("span", "", "Photo anchored"));
      var px = btn("", "✕", function () {
        loriPane.anchorPhoto(null);
        renderAll();
      });
      px.title = "Unanchor photo";
      pchip.appendChild(px);
      pRow.appendChild(pchip);
      drawer.appendChild(pRow);
    }

    if (!loriPane.node) loriPane.build();
    loriPane.paintScope();
    loriPane.refreshDrawer();
    drawer.appendChild(loriPane.node);

    wrap.appendChild(drawer);
    return wrap;
  }

  // [renderLoriTab() was deleted here on 2026-07-28 by WO-TRIP-PLAN-AS-HUB-01
  // Phase A. It rendered the same loriPane the overlay renders, under an
  // "Operator workspace conversation" heading with a "Back to Trip Plan"
  // button -- which is the tell: a destination whose own header offers to
  // take you somewhere else was never a destination. Its real defect was
  // that it arrived with no day anchored, so a conversation started there
  // was scoped to the trip and the operator had to notice and fix that.
  // openLoriOverlay(dayId) opens the same pane over the day you are on and
  // returns you to it, which is what the tab was standing in for.]

  // ── boot ──────────────────────────────────────────────────────────────

  function boot() {
    if (!root) return;
    if (!st.personId) {
      renderPersonPicker();
      return;
    }
    api("/api/people").then(function (out) {
      var people = out.people || out || [];
      var me = people.filter(function (p) { return p.id === st.personId; })[0];
      if (me) st.personLabel = me.display_name || "";
    }).catch(function () {}).then(function () {
      renderAll();
      loadTrips().catch(function (e) { st.error = e.message; renderAll(); });
    });
  }

  boot();

  // WO-TRAVEL-DOC-UNIFY-01 Phase 1, amendment A1 — the mount handle.
  //
  // Without this there is no way to satisfy Phase 1's own acceptance
  // criterion ("no global state collision if mount is called twice").
  // The BroadcastChannel is the load-bearing case: it is a NAMED channel
  // ("hornelore-trip-updates"), so two live mounts mean two subscriptions
  // on the same name and one cross-tab trip update fires two refreshes.
  //
  // destroy() is idempotent and every step is individually guarded — a
  // teardown must never throw, or a caller swapping panels is left with
  // a half-torn-down mount and no way to recover.
  //
  // Phase 1.1 — `destroyed = true` is deliberately the FIRST statement.
  // Every step below can run script that re-enters this module (a close
  // handler, a rejected fetch settling in the same microtask checkpoint),
  // so the flag has to be set before anything else is touched, not after.
  // Closing the door and then flipping the sign leaves a window open.
  return {
    destroy: function () {
      destroyed = true;
      try { document.removeEventListener("keydown", onDocKeydown); } catch (e) {}
      // Phase 2D -- the picker poll. Its callback checks `destroyed`
      // first, so this is belt AND braces rather than the only guard;
      // clearing the handle means a torn-down mount leaves nothing
      // pending at all, instead of one timer that will wake up and
      // return.
      try { pickerPollStop(); } catch (e) {}
      // WO-TRAVEL-DOC-CLOSEOUT-01 -- the export's object-URL cleanup.
      // Same shape and same reason: the callback checks `destroyed`, and
      // clearing the handle here means teardown leaves nothing pending.
      // It also revokes immediately, which frees a multi-megabyte blob
      // rather than holding it for the rest of the minute.
      try { docExportRevokeNow(); } catch (e) {}
      try { if (_tdlUpdateChannel) _tdlUpdateChannel.close(); } catch (e) {}
      _tdlUpdateChannel = null;
      try { loriPane.reset(); } catch (e) {}
      try { if (root) root.textContent = ""; } catch (e) {}
      // Phase 2 — hand the host back unstyled. The shell reuses the same
      // <div> for the fallback Documenter comparison toggle; leaving
      // .tdl-root on it would paint the Lab's cream page background and
      // font behind whatever mounts next.
      try {
        if (root) root.classList.remove("tdl-root", "tdl-root-embedded");
      } catch (e) {}
    }
  };

  };  // ══════════════════ MOUNT BOUNDARY — body ends ══════════════════
})();
