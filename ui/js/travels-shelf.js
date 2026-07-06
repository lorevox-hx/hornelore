/* ═══════════════════════════════════════════════════════════════
   travels-shelf.js — WO-LIFEMAP-TRAVELS-SHELF-AND-NARRATION-01
   Phase 1 (read-only) + Phase 1.5 (session state).

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
   - Phase 1 is read-only: no narration parser, no trip creation.
     Zero-trip state dispatches a warm invitation directive only.
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
    s.activeTripStopId = null;
    if (!s.tripStyle) s.tripStyle = "trip_listening"; // guided_trip_walk = operator-selectable (Phase 5)
    console.info("[travels-shelf] active_trip=" + (s.activeTripId || "none") +
      " style=" + s.tripStyle);
  }

  // ── Shelf toggle ──────────────────────────────────────────────
  function lvTravelsShelfToggle() {
    var panel = _panel();
    if (!panel) return;
    if (!panel.hidden) {           // open → close
      panel.hidden = true;
      _session().travelsPanelOpen = false;
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

  function _zeroTrips(panel) {
    panel.innerHTML =
      '<p class="lv-travels-note">No journeys here yet — tell Lori about one whenever you’d like.</p>';
    _dispatch(
      "[SYSTEM: The narrator just opened the Travels shelf on their Life Map, " +
      "but no trips are on record yet. Ask ONE warm, open question inviting " +
      "them to tell you about a journey they remember — any trip, from any " +
      "time of life. Do NOT invent or suggest any specific trip, place, or " +
      "year. Do NOT ask them to recall calendar dates. Maximum 55 words. " +
      "ONE question only. No menu choices. No compound follow-ups.]");
  }

  function _paintPicker(panel, trips) {
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
        .then(function (r) { return r.ok ? r.json() : null; }),
      fetch(ORIGIN + "/api/trips/" + encodeURIComponent(trip.id) + "/photo-links")
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; }),
    ]).then(function (out) {
      var tree = out[0], links = (out[1] && out[1].photo_links) || [];
      if (!Array.isArray(links)) links = [];
      _paintOutline(tree || {}, links, trip);
      _dispatchTripOpen(trip, tree || {});
    }).catch(function () {
      if (panel) panel.innerHTML = '<p class="lv-travels-note">Couldn’t open that trip right now.</p>';
    });
  }

  function _dispatchTripOpen(trip, tree) {
    // Identity gate — same rule as era clicks.
    if (typeof hasIdentityBasics74 === "function" && !hasIdentityBasics74()) {
      console.info("[travels-shelf] BLOCKED Lori dispatch — identity incomplete");
      return;
    }
    var span = [trip.start_date, trip.end_date].filter(Boolean).join(" to ");
    var regions = (tree.regions || []).map(function (r) { return r.title; })
      .filter(Boolean).slice(0, 6).join(", ");
    // Deterministic, mechanical-truth-only directive (era-click pattern).
    _dispatch(
      "[SYSTEM: The narrator just opened their trip '" + (trip.title || "a trip") + "'" +
      (span ? " (" + span + ")" : "") + " from the Travels shelf on the Life Map." +
      (regions ? " Places on record for this trip: " + regions + "." : "") +
      " Ask ONE warm question inviting them to start telling the story of this " +
      "journey wherever they’d like — you may name the first place on record. " +
      "Frame in PAST TENSE. Reference ONLY the details given above; do not " +
      "invent any other place, person, or event. Do NOT ask them to recall " +
      "calendar dates. Maximum 55 words. ONE question only. No menu choices. " +
      "No compound 'and how / and what' follow-ups.]");
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
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function () { _openTrip(trip); })  // repaint with new photos
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
    if (stopName) known.push("place: " + stopName);
    if (link.caption) known.push("note: " + link.caption);
    _dispatch(
      "[SYSTEM: The narrator is looking at a photo from their trip '" +
      (trip.title || "a trip") + "'." +
      (known.length ? " Known details — " + known.join("; ") + "." : "") +
      " Invite them to tell you about this photo in ONE short, warm question, " +
      "referencing ONLY the known details above. Do NOT guess what is in the " +
      "photo, who is in it, what happened, or how anyone felt. Do NOT ask " +
      "them to recall calendar dates. Maximum 40 words. ONE question only.]");
  }

  // ── Dispatch through the main conversation ────────────────────
  function _dispatch(directive) {
    if (typeof sendSystemPrompt === "function") {
      try { sendSystemPrompt(directive); return; } catch (e) {
        console.warn("[travels-shelf] sendSystemPrompt threw:", e);
      }
    }
    if (typeof wo9SendOrQueueSystemPrompt === "function") {
      try { wo9SendOrQueueSystemPrompt(directive); } catch (e) {
        console.warn("[travels-shelf] queue dispatch threw:", e);
      }
    }
  }

  // ── Re-render survival: Life Map re-renders wipe the panel ───
  function _lvTravelsRestorePanel() {
    var s = _session();
    if (!s.travelsPanelOpen || !s.activeTripId) return;
    var panel = _panel();
    if (!panel) return;
    panel.hidden = false;
    fetch(ORIGIN + "/api/trips/" + encodeURIComponent(s.activeTripId) + "/tree")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (tree) {
        if (!tree) return;
        fetch(ORIGIN + "/api/trips/" + encodeURIComponent(s.activeTripId) + "/photo-links")
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

  window.lvTravelsShelfToggle = lvTravelsShelfToggle;
  window._lvTravelsRestorePanel = _lvTravelsRestorePanel;
})();
