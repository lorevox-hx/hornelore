/* ═══════════════════════════════════════════════════════════════
   travels-shelf.js — WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01
   Phases 1–5 (shelf + panel + trip session state + narration scope +
   EXIF date confirmations + guided style).

   The "Travels" shelf on the Life Map: narrator entry point into
   trips. Opens the trip in the MAIN Lori conversation (era-click
   pattern) + paints a live trip outline panel in the same column.

   HARD RULES (spec §3, graded at acceptance):
   - Travels is a SHELF, never an era. Nothing here touches LV_ERAS,
     era_id_from_age, memoir ordering, or era prompts.
   - Panel shows narrator-facing human labels ONLY. Never renders:
     confidence scores, assignment_method, cluster_confidence,
     metadata_trust, "provisional", parser warnings, review-queue
     vocabulary. Operator provenance lives in the Trip Tab.
   - Lori directives are deterministic, mechanical-truth-only, and
     NEVER ask the narrator to recall calendar dates.
   - Photo-click grounding uses operator/photo metadata only (stop
     name, caption). No inferred emotion/identity/meaning. Trusted-
     date grounding arrives with Phase 4 EXIF confirmations — until
     then dates are omitted from photo prompts entirely (a link's
     taken_at can originate from an untrusted scan date, and the
     panel has no trust column by design).
   - Identity gate: same rule as era clicks (BUG-LORI-IDENTITY-MUST-
     BLOCK-LIFEMAP-01) — no Lori dispatch before name/DOB/POB.
   - Zero-trip state dispatches a warm invitation AND flags
     travels_shelf_open on runtime71 so the server-side narration
     parser (trip_narration_capture, gated HORNELORE_TRIP_NARRATION)
     can create the FIRST provisional trip from what the narrator
     says; the panel polls and opens that trip silently. Closing the
     shelf clears ALL trip scope — general chat is never trip-parsed.
═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var ORIGIN = window.LOREVOX_API || "http://localhost:8000";

  function _esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function _panel() { return document.getElementById("lvTravelsOutlinePanel"); }

  function _session() {
    if (!window.state) window.state = {};
    if (!state.session) state.session = {};
    return state.session;
  }

  // ── Phase 1.5: trip session state ────────────────────────────
  function _setActiveTrip(trip) {
    var s = _session();
    s.activeTripId = trip ? trip.id : null;
    s.activeTripTitle = trip ? (trip.title || "") : "";
    s.activeTripStopId = null; s.activeTripPhotoLinkId = null;
    // Phase 5: guided_trip_walk is OPERATOR-selectable (never default —
    // spec §3.5). Operator sets localStorage["lv_trip_style"] =
    // "guided_trip_walk"; anything else means listening mode.
    var opStyle = null;
    try { opStyle = localStorage.getItem("lv_trip_style"); } catch (e) {}
    s.tripStyle = (opStyle === "guided_trip_walk")
      ? "guided_trip_walk" : "trip_listening";
    console.info("[travels-shelf] active_trip=" + (s.activeTripId || "none") +
      " style=" + s.tripStyle);
  }

  // ── Phase 3: live panel refresh while open ────────────────────
  // The narration parser writes provisional stops server-side; this
  // keeps the outline visibly assembling while the narrator talks.
  var _refreshTimer = null;
  var _knownStopIds = {};   // for the "just added" cue + order confirm
  var _newStopsThisSession = [];

  function _startPanelRefresh(trip) {
    _stopPanelRefresh();
    _refreshTimer = setInterval(function () {
      var s = _session();
      if (!s.travelsPanelOpen || !s.activeTripId) { _stopPanelRefresh(); return; }
      _refetchAndPaint(trip);
    }, 8000);
  }

  function _stopPanelRefresh() {
    if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
  }

  // BUG-TRAVELS-STALE-DELETED-TRIP-TREE-404-01 (2026-07-09): a persisted
  // activeTripId for a DELETED trip kept 404-ing on /tree (restore + 8s
  // refresh + open) and poisoned the current active-trip scope. When
  // /tree returns 404 (the trip is gone), clear ALL trip scope cleanly —
  // the same fields the close path clears — so a stale id never rides
  // runtime71 into the chat turn.
  function _clearStaleTrip(reason) {
    var s = _session();
    console.info("[travels-shelf] clearing stale trip scope (" + reason +
      "): " + (s.activeTripId || "none"));
    s.activeTripId = null;
    s.activeTripTitle = "";
    s.activeTripStopId = null; s.activeTripPhotoLinkId = null;
    s.tripStyle = null;
    s.travelsShelfOpen = false;
    s.travelsPanelOpen = false;
    _stopPanelRefresh();
    try { _stopZeroTripPoll(); } catch (e) {}
    var panel = _panel();
    if (panel) panel.hidden = true;
  }

  function _refetchAndPaint(trip) {
    Promise.all([
      fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/tree")
        .then(function (r) {
          if (r.status === 404) { _clearStaleTrip("tree_404"); return null; }
          return r.ok ? r.json() : null;
        }),
      fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/narrator-photo-links")
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; }),
    ]).then(function (out) {
      var tree = out[0], links = (out[1] && out[1].photo_links) || [];
      if (!tree) return;
      if (!Array.isArray(links)) links = [];
      _paintOutline(tree, links, trip);
      _maybeOfferOrderConfirm(trip, tree);
      // BUG-TRAVELS-DATE-CONFIRM-STILL-TIMER-RACES-TRIP-OPEN-01
      // (review 2026-07-05): the 8s tick can land while the trip-open
      // reply is still generating. Gate on the narrator having spoken
      // at least once since the trip opened — a turn signal, not a
      // timer guess.
      if (!_dateConfirmTried[trip.id] && _narratorTurnsSinceOpen >= 1) {
        // BUG-TRAVELS-DATE-CONFIRM-TRIED-SET-BEFORE-OFFER-FOUND-01:
        // the tried flag is set INSIDE _maybeOfferDateConfirmation,
        // just before dispatch — a fetch failure or empty offer list
        // must not burn the one attempt (photos may arrive later).
        _maybeOfferDateConfirmation(trip);
      }
    }).catch(function () {});
  }

  var _dateConfirmTried = {};  // trip_id → true (once per page session)
  var _narratorTurnsSinceOpen = 0;
  // app.js notifies on every narrator send (one-line hook).
  window._lvTravelsNarratorTurn = function () { _narratorTurnsSinceOpen += 1; };

  // ── Shelf toggle ──────────────────────────────────────────────
  function lvTravelsShelfToggle() {
    var panel = _panel();
    if (!panel) return;
    if (!panel.hidden) {           // open → close
      // BUG-TRAVELS-CLOSE-LEAVES-ACTIVE-TRIP-SCOPE-01 (review
      // 2026-07-05): closing Travels must clear ALL trip scope —
      // activeTripId kept riding runtime71 after close, so normal
      // chat could still be parsed into the last trip.
      panel.hidden = true;
      var sClose = _session();
      sClose.travelsPanelOpen = false;
      sClose.travelsShelfOpen = false;
      sClose.activeTripId = null;
      sClose.activeTripTitle = "";
      sClose.activeTripStopId = null; sClose.activeTripPhotoLinkId = null;
      sClose.tripStyle = null;
      _stopPanelRefresh();
      _stopZeroTripPoll();
      return;
    }
    panel.hidden = false;
    _session().travelsPanelOpen = true;
    panel.innerHTML = '<p class="lv-travels-note">Opening your travels…</p>';
    var pid = (window.state && state.person_id) || "";
    if (!pid) {
      panel.innerHTML = '<p class="lv-travels-note">Start a session first.</p>';
      return;
    }
    fetch(ORIGIN + "/api/trips?person_id=" + encodeURIComponent(pid))
      .then(function (r) { return r.ok ? r.json() : { trips: [] }; })
      .then(function (j) {
        var trips = Array.isArray(j && j.trips) ? j.trips : [];
        if (!trips.length) return _zeroTrips(panel);
        if (trips.length === 1) return _openTrip(trips[0]);
        _paintPicker(panel, trips);
      })
      .catch(function () {
        panel.innerHTML = '<p class="lv-travels-note">Your travels aren’t available right now.</p>';
      });
  }

  // BUG-TRAVELS-ZERO-TRIP-NARRATION-HOOK-NEVER-CREATES-TRIP-01
  // (review 2026-07-05): the chat_ws hook only fired with an
  // active_trip_id — so the FIRST trip could never be born from
  // narration. Zero-trip state now (a) flags travels_shelf_open in
  // session state (rides runtime71 → server hook), (b) polls for the
  // trip the parser creates and opens it SILENTLY (the narrator just
  // narrated; Lori's natural reply is the response — no extra prompt).
  var _zeroTripPoll = null;

  function _stopZeroTripPoll() {
    if (_zeroTripPoll) { clearInterval(_zeroTripPoll); _zeroTripPoll = null; }
    _session().travelsShelfOpen = false;
  }

  function _zeroTrips(panel) {
    // BUG-TRAVELS-ZERO-TRIP-SCOPE-FLAG-CLEARED-IMMEDIATELY-01 (review
    // 2026-07-05): _stopZeroTripPoll() clears travelsShelfOpen — it
    // must run BEFORE the scope flag is set, or the flag is dead
    // before the narrator's next turn ever reaches runtime71.
    _stopZeroTripPoll();
    var s = _session();
    s.travelsShelfOpen = true;   // runtime71.travels_shelf_open → hook scope
    s.activeTripId = null;
    panel.innerHTML =
      '<p class="lv-travels-note">No journeys here yet — tell Lori about one whenever you’d like.</p>';
    var pid = (window.state && state.person_id) || "";
    _zeroTripPoll = setInterval(function () {
      if (!_session().travelsPanelOpen) { _stopZeroTripPoll(); return; }
      fetch(ORIGIN + "/api/trips?person_id=" + encodeURIComponent(pid))
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (j) {
          var trips = (j && j.trips) || [];
          if (trips.length) {
            _stopZeroTripPoll();
            // Silent open: the parser just created this from the
            // narrator's own words — no trip-open prompt on top.
            _dispatchedTrips[trips[0].id] = true;
            _openTrip(trips[0]);
          }
        })
        .catch(function () {});
    }, 6000);
    _dispatch(
      "[SYSTEM: The narrator just opened the Travels shelf on their Life Map, " +
      "but no trips are on record yet. Ask ONE warm, open question inviting " +
      "them to tell you about a journey they remember — any trip, from any " +
      "time of life. Do NOT invent or suggest any specific trip, place, or " +
      "year. Do NOT ask them to recall calendar dates. Maximum 55 words. " +
      "ONE question only. No menu choices. No compound follow-ups.]");
  }

  function _paintPicker(panel, trips) {
    // No active trip until the narrator actually picks one — the
    // picker itself must not leave a stale trip scope in runtime71.
    var sPick = _session();
    sPick.activeTripId = null;
    sPick.activeTripTitle = "";
    sPick.activeTripStopId = null; sPick.activeTripPhotoLinkId = null;
    panel.innerHTML = '<p class="lv-travels-note">Which journey would you like to visit?</p>';
    trips.forEach(function (t) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "lv-travels-pick";
      var when = [t.start_date, t.end_date].filter(Boolean).join(" to ");
      card.innerHTML = '<span class="lv-travels-pick-title">' + _esc(t.title || "A trip") +
        "</span>" + (when ? '<span class="lv-travels-pick-dates">' + _esc(when) + "</span>" : "");
      card.addEventListener("click", function () { _openTrip(t); });
      panel.appendChild(card);
    });
  }

  // ── Open a trip: state + panel + ONE deliberate Lori prompt ──
  function _openTrip(trip) {
    _setActiveTrip(trip);
    var panel = _panel();
    if (panel) {
      panel.hidden = false;
      panel.innerHTML = '<p class="lv-travels-note">Opening ' + _esc(trip.title || "your trip") + "…</p>";
    }
    Promise.all([
      fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/tree")
        .then(function (r) {
          if (r.status === 404) { _clearStaleTrip("tree_404"); return null; }
          return r.ok ? r.json() : null;
        }),
      fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/narrator-photo-links")
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; }),
    ]).then(function (out) {
      var tree = out[0], links = (out[1] && out[1].photo_links) || [];
      if (!Array.isArray(links)) links = [];
      _paintOutline(tree || {}, links, trip);
      _seedKnownStops(tree || {});
      _session().travelsShelfOpen = true;  // trip open ⇒ still shelf scope
      _narratorTurnsSinceOpen = 0;         // date-confirm waits for a turn
      _dispatchTripOpen(trip, tree || {});
      _startPanelRefresh(trip);
      // BUG-TRAVELS-OPEN-DISPATCHES-DATE-CONFIRM-TOO-SOON-01: the
      // date confirmation is DEFERRED to the refresh tick (>=8s after
      // open) — one deliberate prompt per gesture, and the WO-9 queue
      // only holds one system prompt at a time.
    }).catch(function () {
      if (panel) panel.innerHTML = '<p class="lv-travels-note">Couldn’t open that trip right now.</p>';
    });
  }

  var _dispatchedTrips = {};  // trip_id → true; once per page session

  function _dispatchTripOpen(trip, tree) {
    // Identity gate — same rule as era clicks.
    if (typeof hasIdentityBasics74 === "function" && !hasIdentityBasics74()) {
      console.info("[travels-shelf] BLOCKED Lori dispatch — identity incomplete");
      return;
    }
    // Dedup (live finding 2026-07-05): toggling the shelf closed/open
    // re-ran _openTrip and double-dispatched the trip prompt. One
    // deliberate prompt per trip per page session; re-opens repaint
    // the panel silently.
    if (_dispatchedTrips[trip.id]) {
      console.info("[travels-shelf] dispatch skipped — trip already opened this session");
      return;
    }
    _dispatchedTrips[trip.id] = true;
    var span = [trip.start_date, trip.end_date].filter(Boolean).join(" to ");
    var regions = (tree.regions || []).map(function (r) { return r.title; })
      .filter(Boolean).slice(0, 6).join(", ");

    // Phase 5: guided_trip_walk (operator-selected only, never default).
    // Hook-anchored per the research base — "How did the trip begin?"
    // is a hook; "what was the start date?" is a memory test. The two
    // QF-proof rules ride in the directive: stories always win, and a
    // shrug is accepted once and never re-asked.
    if (_session().tripStyle === "guided_trip_walk") {
      _dispatch(
        "[SYSTEM: The narrator opened their trip '" + _promptSafe(trip.title || "a trip") + "'" +
        (span ? " (" + _promptSafe(span) + ")" : "") + " in guided mode." +
        (regions ? " Places on record (in NO particular order): " +
          _promptSafe(regions) + "." : "") +
        " Walk the journey with them chronologically as a listener: open " +
        "with ONE hook-anchored question such as 'How did the trip begin?'. " +
        "Per stop, at most one question about arrival, a meal or moment, or " +
        "who was there — then move onward. RULES: if they start telling a " +
        "story, FOLLOW THE STORY and drop your next route question. If they " +
        "say they don't remember something, accept it once and NEVER ask " +
        "that again. Do NOT claim or guess the order of places — only the " +
        "narrator knows the route. Do NOT ask them to recall " +
        "calendar dates. Maximum 55 words. ONE question only. No menu choices.]");
      return;
    }
    // Deterministic, mechanical-truth-only directive (era-click pattern).
    //
    // LIVE FINDING 2026-07-05 (Mirano bug): region list order is ENTRY
    // order, not journey order — the old "you may name the first place
    // on record" line let Lori confidently assert "you started in
    // Mirano" when the journey started in Munich. The directive now
    // FORBIDS claiming sequence; only the narrator establishes order.
    _dispatch(
      "[SYSTEM: The narrator just opened their trip '" + _promptSafe(trip.title || "a trip") + "'" +
      (span ? " (" + _promptSafe(span) + ")" : "") + " from the Travels shelf on the Life Map." +
      (regions ? " Places on record for this trip (in NO particular order): " +
        _promptSafe(regions) + "." : "") +
      " Ask ONE warm question inviting them to begin telling the story of this " +
      "journey wherever they’d like. You may mention one or two of the places " +
      "on record, but do NOT claim or guess which place came first, last, or " +
      "in what order they traveled — only the narrator knows the route. " +
      "Frame in PAST TENSE. Reference ONLY the details given above; do not " +
      "invent any other place, person, or event. Do NOT ask them to recall " +
      "calendar dates. Do NOT phrase the question as a fill-in-the-blank " +
      "('and then you traveled to...?'). Maximum 55 words. ONE question only. " +
      "No menu choices. No compound 'and how / and what' follow-ups.]");
  }

  // ── Live trip outline panel (narrator-facing, human labels) ──
  function _paintOutline(tree, links, trip) {
    var panel = _panel();
    if (!panel) return;
    panel.innerHTML = "";

    var head = document.createElement("div");
    head.className = "lv-travels-trip-head";
    var when = [trip.start_date, trip.end_date].filter(Boolean).join(" to ");
    head.innerHTML = '<span class="lv-travels-trip-title">' + _esc(trip.title || "Your trip") +
      "</span>" + (when ? '<span class="lv-travels-trip-dates">' + _esc(when) + "</span>" : "");
    panel.appendChild(head);

    // Stops by region — location names only, nothing operator-flavored.
    (tree.regions || []).forEach(function (r) {
      var reg = document.createElement("div");
      reg.className = "lv-travels-region";
      var rh = document.createElement("div");
      rh.className = "lv-travels-region-head";
      rh.textContent = r.title || "";
      reg.appendChild(rh);
      var paint = function (s, depth) {
        var row = document.createElement("div");
        row.className = "lv-travels-stop";
        row.style.marginLeft = (depth * 14) + "px";
        row.textContent = s.title || s.location_name || "";
        reg.appendChild(row);
        (s.children || []).forEach(function (c) { paint(c, depth + 1); });
      };
      (r.stops || []).forEach(function (s) { paint(s, 0); });
      panel.appendChild(reg);
    });

    // Photo strip — narrator-ready linked photos (backend already
    // wrote the links; thumb endpoint 404s silently for missing).
    var withPhotos = links.filter(function (l) { return l && l.photo_id; });
    if (withPhotos.length) {
      var stopNames = {};
      (tree.regions || []).forEach(function (r) {
        var walk = function (s) {
          stopNames[s.id] = s.title || s.location_name || "";
          (s.children || []).forEach(walk);
        };
        (r.stops || []).forEach(walk);
      });
      var strip = document.createElement("div");
      strip.className = "lv-travels-photos";
      withPhotos.slice(0, 24).forEach(function (l) {
        var img = document.createElement("img");
        img.className = "lv-travels-thumb";
        img.loading = "lazy";
        img.alt = l.caption || "Trip photo";
        img.src = ORIGIN + "/api/photos/" + encodeURIComponent(l.photo_id) + "/thumb";
        img.addEventListener("error", function () { img.remove(); });
        img.addEventListener("click", function () {
          _openPhoto(l, stopNames[l.trip_stop_id] || "", trip);
        });
        strip.appendChild(img);
      });
      panel.appendChild(strip);
    }

    // "+ add photos" — narrator self-vetted upload (REV 9 metadata
    // stamped server-side via uploaded_from_surface=travels_shelf).
    var addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "lv-travels-add-photos";
    addBtn.textContent = "+ Add photos to this trip";
    var input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.accept = "image/*,.heic,.heif";
    input.style.display = "none";
    addBtn.addEventListener("click", function () { input.click(); });
    input.addEventListener("change", function () {
      var files = Array.prototype.slice.call(input.files || []);
      input.value = "";
      if (!files.length) return;
      addBtn.disabled = true;
      addBtn.textContent = "Adding your photos…";
      var fd = new FormData();
      files.forEach(function (f) { fd.append("files", f); });
      fd.append("uploaded_by_user_id", "narrator");
      fd.append("narrator_ready", "true");
      fd.append("uploaded_from_surface", "travels_shelf");
      fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/photos",
            { method: "POST", body: fd })
        .then(function (r) {
          if (!r.ok) throw new Error("upload failed (" + r.status + ")");
          return r.json();
        })
        .then(function (resp) {
          _openTrip(trip);  // repaint with new photos (dispatch deduped)
          // LIVE FINDING 2026-07-05: uploading got no Lori response —
          // but adding a photo is as deliberate a gesture as clicking
          // one. ONE grounded prompt per upload batch, metadata-only
          // (count + trip title; nothing about image content).
          var n = (resp && (resp.uploaded + (resp.duplicates || 0))) || 0;
          if (n > 0 &&
              !(typeof hasIdentityBasics74 === "function" && !hasIdentityBasics74())) {
            _dispatch(
              "[SYSTEM: The narrator just added " + n + " photo" +
              (n === 1 ? "" : "s") + " to their trip '" +
              _promptSafe(trip.title || "a trip") + "'. Invite them, in ONE " +
              "short warm question, to tell you about one of those " +
              "pictures. Do NOT guess or describe what is in any photo, who " +
              "is in it, or where it was taken — you have not seen it. Do " +
              "NOT ask them to recall calendar dates. Maximum 40 words. ONE " +
              "question only.]");
          }
        })
        .catch(function () {
          addBtn.disabled = false;
          addBtn.textContent = "+ Add photos to this trip";
        });
    });
    panel.appendChild(addBtn);
    panel.appendChild(input);
  }

  // ── Photo click: lightbox + grounded Lori prompt ─────────────
  function _openPhoto(link, stopName, trip) {
    // Lightbox (same surface the timeline strip uses).
    try {
      var overlay = document.getElementById("lvNarratorLightbox");
      if (overlay) {
        var img = overlay.querySelector(".lv-narrator-lightbox-img") || overlay.querySelector("img");
        if (img) img.src = ORIGIN + "/api/photos/" + encodeURIComponent(link.photo_id) + "/image";
        var cap = overlay.querySelector(".lv-narrator-lightbox-caption");
        if (cap) cap.textContent = link.caption || "";
        var sub = overlay.querySelector(".lv-narrator-lightbox-subline");
        if (sub) sub.textContent = stopName || "";
        overlay.hidden = false;
      }
    } catch (e) { /* lightbox is cosmetic; prompt still fires */ }

    if (typeof hasIdentityBasics74 === "function" && !hasIdentityBasics74()) return;

    // Grounded prompt — operator/photo metadata ONLY (spec §3.6 REV 8):
    // stop name + visible caption. No dates in Phase 1 (trust-gated
    // date grounding lands with Phase 4). No inference about image
    // content, people, or feelings.
    var known = [];
    if (stopName) known.push("place: " + _promptSafe(stopName));
    if (link.caption) known.push("note: " + _promptSafe(link.caption));
    _dispatch(
      "[SYSTEM: The narrator is looking at a photo from their trip '" +
      _promptSafe(trip.title || "a trip") + "'." +
      (known.length ? " Known details — " + known.join("; ") + "." : "") +
      " Invite them to tell you about this photo in ONE short, warm question, " +
      "referencing ONLY the known details above. Do NOT guess what is in the " +
      "photo, who is in it, what happened, or how anyone felt. Do NOT ask " +
      "them to recall calendar dates. Maximum 40 words. ONE question only.]");
  }

  // ── Dispatch through the main conversation ────────────────────
  // ── Stop tracking (Phase 3 cue + Phase 4 order confirm) ───────
  function _allStops(tree) {
    var out = [];
    (tree.regions || []).forEach(function (r) {
      var walk = function (s) {
        out.push(s);
        (s.children || []).forEach(walk);
      };
      (r.stops || []).forEach(walk);
    });
    return out;
  }

  function _seedKnownStops(tree) {
    _knownStopIds = {};
    _newStopsThisSession = [];
    _allStops(tree).forEach(function (s) { _knownStopIds[s.id] = true; });
  }

  // ── Phase 4: EXIF date confirmation (recognition over recall) ──
  // Oral-history practice: the interviewer SUPPLIES known dates to jog
  // memory rather than asking for them. One offer per stop, ever —
  // the offered-ledger persists so a shrug is never re-asked.
  function _offeredLedger(tripId) {
    try {
      return JSON.parse(localStorage.getItem("lv_trip_confirm_offered_" + tripId) || "[]");
    } catch (e) { return []; }
  }

  function _markOffered(tripId, stopName) {
    try {
      var led = _offeredLedger(tripId);
      if (led.indexOf(stopName) < 0) led.push(stopName);
      localStorage.setItem("lv_trip_confirm_offered_" + tripId,
                           JSON.stringify(led));
    } catch (e) {}
  }

  function _maybeOfferDateConfirmation(trip) {
    fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/date-confirmations")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var offers = (j && j.confirmations) || [];
        if (!offers.length) return;
        if (typeof hasIdentityBasics74 === "function" && !hasIdentityBasics74()) return;
        // BUG-TRAVELS-DATE-CONFIRM-LEDGER-USES-STOP-NAME-01 (review
        // 2026-07-05): repeated names ("Paris arrival"/"Paris return")
        // could suppress the wrong stop — ledger keys on stop_id now,
        // with stop_name fallback for pre-fix ledger entries.
        var led = _offeredLedger(trip.id);
        var next = null;
        for (var i = 0; i < offers.length; i++) {
          var key = offers[i].stop_id || offers[i].stop_name;
          if (led.indexOf(key) < 0 && led.indexOf(offers[i].stop_name) < 0) {
            next = offers[i]; break;
          }
        }
        if (!next) return;  // everything already offered once — never re-ask
        _dateConfirmTried[trip.id] = true;  // real offer found → tried
        _markOffered(trip.id, next.stop_id || next.stop_name);
        _dispatch(
          "[SYSTEM: The narrator's pictures from " + _promptSafe(next.stop_name) +
          " are dated around " + _promptSafe(next.date) + " (from the photos " +
          "themselves — trusted). Offer this ONE date gently for confirmation, " +
          "e.g. 'Your pictures from " + _promptSafe(next.stop_name) +
          " are from around " + _promptSafe(next.date) + " — does that sound " +
          "right?' If they say no or don't remember, accept it warmly and " +
          "move on — never press. Do NOT ask them to recall calendar dates " +
          "themselves. Maximum 40 words. ONE question only.]");
      })
      .catch(function () {});
  }

  // ── Phase 4: order confirmation pass ──────────────────────────
  // After the narration parser has added >=2 new stops this session,
  // ONE summary confirmation — confirming what was HEARD (allowed,
  // WO-LORI-CONFIRM-01 pattern), never asking for what's missing.
  // BUG-TRAVELS-ORDER-CONFIRM-STATE-GLOBAL-ACROSS-TRIPS-01: per-trip,
  // not global — Trip A's confirmation must not block Trip B's.
  var _orderConfirmDoneByTrip = {};

  function _maybeOfferOrderConfirm(trip, tree) {
    if (_orderConfirmDoneByTrip[trip.id]) return;
    var stops = _allStops(tree);
    stops.forEach(function (s) {
      if (!_knownStopIds[s.id]) {
        _knownStopIds[s.id] = true;
        _newStopsThisSession.push(s.title || s.location_name || "");
      }
    });
    if (_newStopsThisSession.filter(Boolean).length < 2) return;
    if (typeof hasIdentityBasics74 === "function" && !hasIdentityBasics74()) return;
    _orderConfirmDoneByTrip[trip.id] = true;
    var names = _newStopsThisSession.filter(Boolean).slice(0, 5)
      .map(_promptSafe).join(", then ");
    _dispatch(
      "[SYSTEM: From the narrator's telling so far, these places were " +
      "noted in this order: " + names + ". Confirm ONCE, gently: e.g. " +
      "'So far I have " + names + " — did I get the order right?' If they " +
      "correct you, thank them and follow their correction. Do NOT ask " +
      "them to recall calendar dates. Maximum 45 words. ONE question only.]");
  }

  // BUG-TRAVELS-DISPATCH-BYPASSES-WO9-WARMUP-QUEUE-01 (review
  // 2026-07-05): the WO-9 queue must come FIRST — it holds system
  // prompts until _llmReady and drains in order. Calling
  // sendSystemPrompt directly bypassed the warmup gate.
  function _dispatch(directive) {
    if (typeof wo9SendOrQueueSystemPrompt === "function") {
      try { wo9SendOrQueueSystemPrompt(directive); return; } catch (e) {
        console.warn("[travels-shelf] queue dispatch threw:", e);
      }
    }
    if (typeof sendSystemPrompt === "function") {
      try { sendSystemPrompt(directive); } catch (e) {
        console.warn("[travels-shelf] sendSystemPrompt threw:", e);
      }
    }
  }

  // BUG-TRAVELS-DIRECTIVE-VALUE-SANITIZE-01 (review 2026-07-05):
  // narrator-editable values (trip titles, region/stop names, photo
  // captions) are interpolated into [SYSTEM: ...] directives. Strip
  // newlines + bracket characters so a weird title can't close the
  // directive or smuggle instruction-shaped text; hard length cap.
  function _promptSafe(s) {
    return String(s == null ? "" : s)
      .replace(/[\r\n]+/g, " ")
      .replace(/\]/g, ")")
      .replace(/\[/g, "(")
      .slice(0, 160);
  }

  // ── Re-render survival: Life Map re-renders wipe the panel ───
  function _lvTravelsRestorePanel() {
    var s = _session();
    if (!s.travelsPanelOpen || !s.activeTripId) return;
    var panel = _panel();
    if (!panel) return;
    panel.hidden = false;
    fetch(ORIGIN + "/api/trips/" + encodeURIComponent(s.activeTripId) + "/tree")
      .then(function (r) {
        if (r.status === 404) { _clearStaleTrip("tree_404_restore"); return null; }
        return r.ok ? r.json() : null;
      })
      .then(function (tree) {
        if (!tree) return;
        fetch(ORIGIN + "/api/trips/" + encodeURIComponent(s.activeTripId) + "/narrator-photo-links")
          .then(function (r) { return r.ok ? r.json() : []; })
          .catch(function () { return []; })
          .then(function (links) {
            if (!Array.isArray(links)) links = (links && links.photo_links) || [];
            _paintOutline(tree, links, {
              id: s.activeTripId, title: s.activeTripTitle,
              start_date: tree.start_date, end_date: tree.end_date,
            });
          });
      })
      .catch(function () {});
  }

  // WO-TRAVELS-SHELF-LAUNCH-FROM-TRAVEL-DOC-01 — public opener so the
  // operator Travel Doc can point the narrator Travels shelf at a specific
  // trip via ONE explicit, narrator-visible action. The shelf stays the
  // sole owner of activeTripId / tripStyle / prompt dispatch; Travel Doc
  // only calls this function and never touches session/runtime state.
  function lvTravelsOpenTripById(tripId) {
    var pid = (window.state && window.state.person_id) || "";
    if (!pid || !tripId) return;
    try {
      if (typeof window.lvShellShowTab === "function") {
        window.lvShellShowTab("narrator");
      }
    } catch (_) {}
    var panel = _panel();
    if (panel && panel.hidden) {
      panel.hidden = false;
      try { _session().travelsPanelOpen = true; } catch (_) {}
    }
    fetch(ORIGIN + "/api/trips?person_id=" + encodeURIComponent(pid))
      .then(function (r) { return r.ok ? r.json() : { trips: [] }; })
      .then(function (j) {
        var t = ((j && j.trips) || []).filter(function (x) {
          return x.id === tripId;
        })[0];
        if (t) _openTrip(t);
      })
      .catch(function () {});
  }
  window.lvTravelsOpenTripById = lvTravelsOpenTripById;
  window.lvTravelsShelfToggle = lvTravelsShelfToggle;
  window._lvTravelsRestorePanel = _lvTravelsRestorePanel;
})();

/* WO-TRIP-LORI-REAL-BETA-USABILITY-01 Phase 2 — in-chat "+ Add trip photo".
   A visible upload affordance in the conversation footer, shown ONLY when a
   trip is open on the Travels shelf. Reuses the trip photo endpoint; after
   upload it dispatches ONE safe Lori prompt (metadata only — never describes
   the image). Self-contained: reads state.session, uses global dispatch. */
(function () {
  "use strict";
  var API = (window.LOREVOX_API || "http://localhost:8000").replace(/\/$/, "");

  function _ss() {
    try {
      return (typeof state !== "undefined" && state && state.session) ? state.session : {};
    } catch (e) { return {}; }
  }
  function _safe(t) {
    return String(t == null ? "" : t)
      .replace(/[\[\]]/g, " ").replace(/\r?\n/g, " ")
      .replace(/\s+/g, " ").trim().slice(0, 120);
  }
  function _syncBtn() {
    var btn = document.getElementById("lvAddTripPhotoBtn");
    if (!btn) return;
    var s = _ss();
    btn.hidden = !(s.activeTripId && s.travelsShelfOpen);
  }
  function _chip(text) {
    try { if (typeof window.appendBubble === "function") window.appendBubble("system", text); }
    catch (e) { /* best-effort — the safe Lori prompt is the real confirmation */ }
  }
  function _dispatchSafePrompt(title) {
    // Short + deterministic. Do NOT name the trip or any place (that produced
    // the wordy "Central Europe … your Spring 2026 …" echo) — just anchor on
    // "that moment" and let the narrator describe it.
    var msg = "[SYSTEM: The narrator just added a photo to the trip they have " +
      "open. You have NOT seen it — do not describe, guess, or name what is in " +
      "it. Do NOT name the trip or any place. Ask ONE short warm question " +
      "(maximum 15 words) inviting them to say what they remember about that " +
      "moment. ONE question only. No preamble.]";
    try {
      if (typeof window.wo9SendOrQueueSystemPrompt === "function") window.wo9SendOrQueueSystemPrompt(msg);
      else if (typeof window.sendSystemPrompt === "function") window.sendSystemPrompt(msg);
    } catch (e) { console.warn("[in-chat-photo] prompt dispatch failed:", e); }
  }
  function _upload(files) {
    var s = _ss();
    if (!s.activeTripId || !files.length) return;
    var btn = document.getElementById("lvAddTripPhotoBtn");
    if (btn) { btn.disabled = true; btn.textContent = "Adding photo…"; }
    var fd = new FormData();
    files.forEach(function (f) { fd.append("files", f); });
    fd.append("uploaded_by_user_id", "narrator");
    fd.append("narrator_ready", "true");
    fd.append("uploaded_from_surface", "travels_shelf");
    fetch(API + "/api/trips/" + encodeURIComponent(s.activeTripId) + "/photos",
          { method: "POST", body: fd })
      .then(function (r) {
        if (!r.ok) throw new Error("upload failed (" + r.status + ")");
        return r.json();
      })
      .then(function (resp) {
        var results = (resp && resp.results) || [];
        var first = null;
        for (var i = 0; i < results.length; i++) {
          if (results[i] && results[i].photo_id) { first = results[i]; break; }
        }
        if (first) {
          // Phase 3 — anchor the uploaded photo so the NEXT narrator answer
          // captures as a photo-linked note (source_ref=photo_link:<id>).
          s.activeTripPhotoLinkId = first.link_id || null;
          s.activeTripPhotoId = first.photo_id || null;
          s.activeTripPhotoFilename = first.filename || null;
          // Phase 1 — show the actual photo in chat (Lori still can't see it).
          _renderPhotoCard(first.photo_id, first.filename);
        } else {
          var n = (resp && (resp.uploaded + (resp.duplicates || 0))) || files.length;
          _chip("📷 " + (n === 1 ? "Photo" : n + " photos") + " added to this trip.");
        }
        _dispatchSafePrompt(s.activeTripTitle);
      })
      .catch(function (e) {
        console.warn("[in-chat-photo] upload error:", e);
        _chip("Sorry — that photo didn't upload. Please try again.");
      })
      .then(function () {
        var b = document.getElementById("lvAddTripPhotoBtn");
        if (b) { b.disabled = false; b.textContent = "+ Add trip photo"; }
      });
  }
  function _renderPhotoCard(photoId, filename) {
    try {
      var host = document.getElementById("chatMessages");
      if (!host || !photoId) {
        _chip("📷 Photo added to this trip. Lori will ask you about it.");
        return;
      }
      var card = document.createElement("div");
      card.className = "lv-chat-photo-card";
      var img = document.createElement("img");
      img.className = "lv-chat-photo-thumb";
      img.src = API + "/api/photos/" + encodeURIComponent(photoId) + "/thumb";
      img.alt = "the photo you added";
      img.title = "Click to view larger";
      img.addEventListener("click", function () {
        window.open(API + "/api/photos/" + encodeURIComponent(photoId) + "/image", "_blank");
      });
      var meta = document.createElement("div");
      meta.className = "lv-chat-photo-meta";
      var t = document.createElement("div");
      t.className = "lv-chat-photo-title";
      t.textContent = "📷 Photo added to this trip";
      meta.appendChild(t);
      if (filename) {
        var fn = document.createElement("div");
        fn.className = "lv-chat-photo-fn";
        fn.textContent = filename;
        meta.appendChild(fn);
      }
      var hint = document.createElement("div");
      hint.className = "lv-chat-photo-hint";
      hint.textContent = "Look at it while you talk — Lori can't see it, so tell her " +
        "what you remember.";
      meta.appendChild(hint);
      card.appendChild(img);
      card.appendChild(meta);
      host.appendChild(card);
      host.scrollTop = host.scrollHeight;
    } catch (e) {
      console.warn("[in-chat-photo] card render failed:", e);
      _chip("📷 Photo added to this trip. Lori will ask you about it.");
    }
  }

  function _wire() {
    var btn = document.getElementById("lvAddTripPhotoBtn");
    var input = document.getElementById("lvAddTripPhotoInput");
    if (btn && input && !btn._lvWired) {
      btn._lvWired = true;
      btn.addEventListener("click", function () { input.click(); });
      input.addEventListener("change", function () {
        var files = Array.prototype.slice.call(input.files || []);
        input.value = "";
        if (files.length) _upload(files);
      });
    }
    _syncBtn();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", _wire);
  else _wire();
  setInterval(_syncBtn, 1500);
  window.lvSyncAddTripPhotoBtn = _syncBtn;
})();
