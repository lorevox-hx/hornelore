/* ==========================================================================
   Lorevox Travel Doc UI Lab — EXPERIMENTAL, REMOVABLE.

   Standalone redesign lab (ui/travel-doc-lab.html) for testing the
   Trip-Calendar-centric Travel Doc redesign against REAL trip data.
   Design reference: docs/mockups/lorevox-travel-doc-ui-lab-v2/.

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
   - Zero impact on production surfaces: does NOT load or reference the
     production Travel Doc module, the narrator room, the Travels shelf,
     or any narrator-session state.
   - API surface: /api/trips*, /api/photos/{id}/thumb, /api/people,
     /api/chat/ws (surface=travel_doc_modal) ONLY.
   - All DOM classes are tdl- namespaced; CSS lives in
     ui/css/travel-doc-lab.css.

   To remove this lab entirely, delete:
     ui/travel-doc-lab.html, ui/js/travel-doc-lab.js,
     ui/css/travel-doc-lab.css, tests/test_travel_doc_lab.py
   (the trip_days backend layer stays — it is UI-independent).
   ========================================================================== */
(function () {
  "use strict";

  var qsParams = new URLSearchParams(window.location.search);
  var st = {
    apiBase: (qsParams.get("api") || "http://localhost:8000").replace(/\/+$/, ""),
    personId: (qsParams.get("person_id") || "").trim(),
    personLabel: "",
    tab: "plan",
    trips: [],
    trip: null,          // selected trip row
    tree: null,          // /tree for selected trip
    days: [],            // /days.days rows (in-window, numbered 1..N)
    preservedDays: [],   // /days.preserved rows (outside current window)
    countsWarning: "",   // /days.counts_warning when evidence counts partial
    photoLinks: [],      // /photo-links rows
    notes: [],           // /location-notes rows
    sources: [],         // /sources rows
    publicContext: [],   // /public-context rows
    travelogue: null,    // /travelogue-preview (lazy)
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

  var root = document.getElementById("tdlRoot");

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

  // ── helpers ──────────────────────────────────────────────────────────

  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(st.apiBase + path, init).then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          var msg = t;
          try { msg = (JSON.parse(t).detail || t); } catch (_) {}
          throw new Error(init.method + " " + path + " -> " + r.status + " " + msg);
        });
      }
      return r.json();
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

  function loadTrips() {
    return api("/api/trips?person_id=" + encodeURIComponent(st.personId))
      .then(function (out) {
        st.trips = out.trips || [];
        if (!st.trip && st.trips.length) return selectTrip(st.trips[0].id);
        renderAll();
      });
  }

  function selectTrip(tripId) {
    st.trip = st.trips.filter(function (t) { return t.id === tripId; })[0] || null;
    st.selectedDayId = null;
    st.selectedPhotoLinkId = null;
    st.routeSel = null;
    st.travelogue = null;
    st.loriOverlay = false;
    st.loriReturnTab = "plan";
    st.photoPickerDayId = null;
    st.noteDrawerDayId = null;
    st.sourceDrawerDayId = null;
    st.reconcile = null;
    st.reconcileDrawerOpen = false;
    loriPane.reset();
    if (!st.trip) { renderAll(); return Promise.resolve(); }
    return loadTripBundle(tripId);
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
      api("/api/trips/" + t + "/location-notes"),
      api("/api/trips/" + t + "/sources").catch(
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
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/location-notes")
      .then(function (out) { st.notes = out.notes || []; });
  }

  function reloadPhotoLinks() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/photo-links")
      .then(function (out) { st.photoLinks = out.photo_links || []; });
  }

  function reloadSources() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/sources")
      .then(function (out) { st.sources = out.sources || []; });
  }

  function reloadReconcile() {
    if (!st.trip) return Promise.resolve();
    return api("/api/trips/" + encodeURIComponent(st.trip.id) +
      "/days/reconcile-preview")
      .then(function (out) { st.reconcile = out; })
      .catch(function () { st.reconcile = null; });
  }

  // ── person picker (no person_id in the URL) ──────────────────────────

  function renderPersonPicker() {
    root.innerHTML = "";
    var card = el("div", "tdl-card tdl-picker");
    card.appendChild(el("div", "tdl-kicker", "Travel Doc UI Lab"));
    card.appendChild(el("h2", "", "Choose a narrator"));
    card.appendChild(el("p", "tdl-muted",
      "This experimental lab needs a narrator. Pick one below (or pass ?person_id= in the URL)."));
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

  // ── shell ─────────────────────────────────────────────────────────────

  var TABS = [
    ["current", "Current"],
    ["plan", "Trip Plan"],
    ["photos", "Photos"],
    ["notes", "Story Notes"],
    ["sources", "Sources"],
    ["travelogue", "Travelogue"],
    ["lori", "Lori"],
  ];

  function setTab(tab) {
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
    renderAll();
  }

  function renderAll() {
    // Preserve the workspace scroll position across re-renders (drawer
    // open/close, saves, selection) so "back" always lands where the
    // operator left off.
    var prevMain = root.querySelector(".tdl-main");
    if (prevMain) st.mainScroll = prevMain.scrollTop;

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
    brand.appendChild(el("span", "tdl-lab-badge", "UI Lab · experimental"));
    if (st.personLabel) {
      brand.appendChild(el("span", "tdl-muted tdl-brand-person", st.personLabel));
    }
    top.appendChild(brand);
    var tabs = el("nav", "tdl-tabs");
    TABS.forEach(function (t) {
      var tb = btn(st.tab === t[0] ? "tdl-active" : "", t[1], function () { setTab(t[0]); });
      tabs.appendChild(tb);
    });
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
    if (!st.trip) {
      main.appendChild(el("div", "tdl-empty",
        st.trips.length ? "Select a trip from the left rail." :
          "No trips yet for this narrator. Create one in the production Travel Doc tab."));
    } else {
      main.appendChild(renderTab());
    }
    layout.appendChild(main);
    if (withInspector) layout.appendChild(renderInspector());
    app.appendChild(layout);

    // Drawers / overlays (in-lab — never navigate away).
    if (st.trip && st.loriOverlay) app.appendChild(renderLoriOverlay());
    if (st.trip && st.photoPickerDayId) app.appendChild(renderPhotoPicker());
    if (st.trip && st.noteDrawerDayId) app.appendChild(renderNoteDrawer());
    if (st.trip && st.sourceDrawerDayId) app.appendChild(renderSourceDrawer());
    if (st.trip && st.reconcileDrawerOpen) app.appendChild(renderReconcileDrawer());

    root.appendChild(app);
    main.scrollTop = st.mainScroll || 0;
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
      side.appendChild(card);

      side.appendChild(el("div", "tdl-section-label", "Route Outline"));
      var tree = el("div", "tdl-route-tree");
      ((st.tree && st.tree.regions) || []).forEach(function (r) {
        var det = document.createElement("details");
        det.open = true;
        var sum = el("summary", "", r.title || "Region");
        det.appendChild(sum);
        (function walk(stops) {
          (stops || []).forEach(function (s) {
            var isSel = st.routeSel && st.routeSel.kind === "stop" && st.routeSel.id === s.id;
            det.appendChild(btn("tdl-route-item" + (isSel ? " tdl-active" : ""),
              s.location_name || s.title || "Stop", function () {
                // FIXPACK-02 (M5b): route-rail selection re-renders too.
                if (dayFormDirtyBlocks()) return;
                st.routeSel = { kind: "stop", id: s.id, regionId: r.id };
                renderAll();
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
      case "current": return renderCurrent();
      case "plan": return renderPlan();
      case "photos": return renderPhotos();
      case "notes": return renderNotes();
      case "sources": return renderSources();
      case "travelogue": return renderTravelogue();
      case "lori": return renderLoriTab();
      default: return el("div");
    }
  }

  function prodTravelDocUrl() {
    return "travel-documenter.html?api=" + encodeURIComponent(st.apiBase) +
      "&person_id=" + encodeURIComponent(st.personId);
  }

  function renderCurrent() {
    var wrap = el("div");
    var note = el("div", "tdl-note-banner");
    note.appendChild(el("strong", "", "Baseline lives in production. "));
    note.appendChild(el("span", "",
      "This lab does not re-implement the current Travel Doc panel. " +
      "Open the production Travel Doc tab (or the standalone page below) " +
      "for the baseline three-column editor — then compare it with " +
      "the Trip Plan redesign here."));
    wrap.appendChild(note);
    var a = document.createElement("a");
    a.className = "tdl-btn";
    a.href = prodTravelDocUrl();
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = "Open production Travel Doc (standalone) ↗";
    wrap.appendChild(a);
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
      "Day cards are created automatically when you save trip dates. " +
      "Each card is the memory workflow: talk with Lori, add what " +
      "happened, attach photos, notes, meals, places, and sources. Use " +
      "☑ Generate / reconcile day cards below if you ever need to " +
      "re-sync the calendar to the current dates."));
    head.appendChild(ht);
    wrap.appendChild(head);

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

    wrap.appendChild(renderEvalChecklist());

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

    var bar = el("div", "tdl-toolbar");
    bar.appendChild(btn("tdl-btn tdl-btn-primary",
      "☑ Generate / reconcile day cards", generateDays));
    bar.appendChild(el("span", "tdl-spacer"));
    bar.appendChild(el("span", "tdl-muted",
      "📅 " + (st.trip.start_date || "?") + " → " + (st.trip.end_date || "?")));
    wrap.appendChild(bar);

    // Date-range reconcile banners (WO-TRAVEL-DOC-UI-LAB-03). Missing
    // in-range days are addable in one click; day cards outside the
    // current trip dates are surfaced — never hidden, never deleted.
    var rec = st.reconcile;
    if (rec && (rec.missing_dates || []).length) {
      var mb = el("div", "tdl-reconcile-banner tdl-reconcile-missing");
      mb.appendChild(el("span", "",
        "Trip dates include " + rec.missing_dates.length +
        " day(s) not yet in the calendar."));
      mb.appendChild(btn("tdl-btn tdl-btn-small", "Add missing days",
        addMissingDays));
      wrap.appendChild(mb);
    }
    if (rec && (rec.out_of_range_days || []).length) {
      var ob = el("div", "tdl-reconcile-banner tdl-reconcile-outside");
      ob.appendChild(el("span", "",
        rec.out_of_range_days.length + " day card(s) are outside the " +
        "current trip dates. They were kept to protect your notes."));
      ob.appendChild(btn("tdl-btn tdl-btn-small", "Review outside-date days",
        openReconcileDrawer));
      wrap.appendChild(ob);
    }

    if (!st.days.length && !(st.preservedDays || []).length) {
      wrap.appendChild(el("div", "tdl-empty",
        "No day cards yet. Generate them from the trip dates above " +
        "(needs trip start and end dates)."));
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

  // ── Lab-only evaluation checklist (WO-TRAVEL-DOC-UI-LAB-03 Part C) ──
  // Live booleans over the loaded trip data. This panel is part of the
  // removable lab — it never ships to production Travel Doc.
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
      " · live status of the UI Lab flows — this panel is part of the " +
      "removable lab, not production Travel Doc."));
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

  // One clear, consistent action row per day — same labels, same order,
  // EVERYWHERE a day is actionable (card + inspector). Full labels wrap
  // to a second line rather than truncating (Chris's laptop review).
  // "Attach photos" (not "Add photos"): the picker attaches EXISTING
  // trip photos to the day — new uploads still come in via Photo Intake.
  function dayActionRow(day) {
    var actions = el("div", "tdl-day-actions");
    actions.appendChild(btn("tdl-btn tdl-btn-gold", "💬 Talk with Lori",
      function () { openLoriOverlay(day.id); }));
    actions.appendChild(btn("tdl-btn", "＋ Attach photos",
      function () { openPhotoPicker(day.id); }));
    actions.appendChild(btn("tdl-btn", "＋ Add note",
      function () { openNoteDrawer(day.id); }));
    actions.appendChild(btn("tdl-btn", "＋ Attach source",
      function () { openSourceDrawer(day.id); }));
    actions.appendChild(btn("tdl-btn", "✎ Edit day", function () {
      if (dayFormDirtyBlocks()) return;
      st.selectedDayId = day.id;
      renderAll();
    }));
    return actions;
  }

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
    var stop = day.trip_stop_id && findStop(day.trip_stop_id);
    var region = day.trip_region_id && findRegion(day.trip_region_id);
    if (stop) {
      main.appendChild(el("p", "", "Linked stop: " + (stop.location_name || "?")));
    } else if (region) {
      main.appendChild(el("p", "", "Linked region: " + (region.title || "?")));
    } else {
      main.appendChild(el("p", "tdl-muted", "No linked region/stop yet"));
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
    card.appendChild(main);

    card.appendChild(dayActionRow(day));

    card.addEventListener("click", function (e) {
      if (e.target.closest("button")) return;
      st.selectedDayId = day.id;
      renderAll();
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
    row1.appendChild(el("span", "tdl-kicker",
      "Day " + day.day_index + " of " + st.days.length));
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

    // ── Section: Overview (default open) ──
    var ov = insSection("overview", "Overview", true);
    ov.appendChild(el("h2", "", prettyDate(day.date) + " · " + day.date));
    ov.appendChild(el("h3", "", dayLabel(day)));
    var scopeNote = el("div", "tdl-lori-scope-note");
    scopeNote.appendChild(el("b", "", "Lori scope: "));
    scopeNote.appendChild(el("span", "", "active_trip_day_id = " + day.id.slice(0, 8) + "… "));
    scopeNote.appendChild(el("span", "tdl-muted",
      "Day-level conversation uses this day plus its linked stop/photos/notes/sources."));
    ov.appendChild(scopeNote);

    var fTitle = watch(el("input")); fTitle.value = day.title || "";
    var fMain = watch(el("input")); fMain.value = day.main_location || "";
    var fLodging = watch(el("input")); fLodging.value = day.lodging_base || "";
    ov.appendChild(labeled("Day title", fTitle));
    ov.appendChild(labeled("Main location", fMain));
    ov.appendChild(labeled("Lodging base", fLodging));

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
    ov.appendChild(labeled("Linked region", fRegion));
    ov.appendChild(labeled("Linked stop", fStop));
    ov.appendChild(dayActionRow(day));
    body.appendChild(ov);

    // ── Section: Notes (day period notes + day story notes) ──
    var ns = insSection("notes", "Notes", false);
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
    ns.appendChild(per);

    var fPlaces = watch(el("textarea"));
    fPlaces.value = (day.places_visited_json || []).join("\n");
    fPlaces.placeholder = "One place per line";
    var fMeals = watch(el("textarea"));
    fMeals.value = (day.meals_json || []).join("\n");
    fMeals.placeholder = "One meal per line";
    ns.appendChild(labeled("Places visited (one per line)", fPlaces));
    ns.appendChild(labeled("Meals (one per line)", fMeals));

    var dNotes = dayLinkedNotes(day);
    var scopedNotes = dayScopedRows(st.notes, day).filter(function (n) {
      return !n.trip_day_id;
    });
    var nt = el("div", "tdl-row-title");
    nt.appendChild(el("span", "",
      "Day story notes (" + dNotes.length + ")"));
    ns.appendChild(nt);
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
    ns.appendChild(nl);
    ns.appendChild(btn("tdl-btn", "＋ Add note",
      function () { openNoteDrawer(day.id); }));
    body.appendChild(ns);

    // ── Section: Photos (day-linked first, then date matches) ──
    var dayLinks = dayLinkedPhotoLinks(day);
    var dateLinks = dateMatchedPhotoLinks(day);
    var ph = insSection("photos", "Photos (" + (dayLinks.length + dateLinks.length) + ")", false);
    if (dayLinks.length) {
      ph.appendChild(el("div", "tdl-row-title-plain", "Attached to this day"));
      var rowA = el("div", "tdl-photo-row");
      dayLinks.slice(0, 12).forEach(function (l) {
        var cellWrap = el("div", "tdl-photo-cell");
        var im = document.createElement("img");
        im.src = thumbUrl(l.photo_id);
        im.alt = l.caption || "trip photo";
        im.loading = "lazy";
        cellWrap.appendChild(im);
        cellWrap.appendChild(btn("tdl-btn tdl-btn-small", "Unlink",
          function () { unlinkDayPhoto(day, l.id); }));
        rowA.appendChild(cellWrap);
      });
      ph.appendChild(rowA);
    }
    if (dateLinks.length) {
      ph.appendChild(el("div", "tdl-row-title-plain", "Dated to this day (not attached)"));
      var rowB = el("div", "tdl-photo-row");
      dateLinks.slice(0, 8).forEach(function (l) {
        var im = document.createElement("img");
        im.src = thumbUrl(l.photo_id);
        im.alt = l.caption || "trip photo";
        im.loading = "lazy";
        rowB.appendChild(im);
      });
      ph.appendChild(rowB);
    }
    if (!dayLinks.length && !dateLinks.length) {
      ph.appendChild(el("p", "tdl-muted", "No photos on this day yet."));
    }
    ph.appendChild(btn("tdl-btn", "＋ Attach photos",
      function () { openPhotoPicker(day.id); }));
    body.appendChild(ph);

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

    // ── Section: Lori captures (day-scoped modal notes) ──
    var loriNotes = st.notes.filter(function (n) {
      return n.source_surface === "travel_doc_modal" && n.trip_day_id === day.id;
    });
    var lc = insSection("lori", "Lori captures (" + loriNotes.length + ")", false);
    var ll = el("div", "tdl-mini-list");
    loriNotes.slice(0, 8).forEach(function (n) {
      var row = el("div");
      row.appendChild(el("span", "tdl-lori-drawer-src", "from Lori"));
      row.appendChild(el("span", "", " " + (n.note_text || "").slice(0, 110)));
      ll.appendChild(row);
    });
    if (!loriNotes.length) {
      ll.appendChild(el("div", "tdl-muted",
        "Nothing captured for this day yet — use Talk with Lori."));
    }
    lc.appendChild(ll);
    lc.appendChild(btn("tdl-btn tdl-btn-gold", "💬 Talk with Lori",
      function () { openLoriOverlay(day.id); }));
    body.appendChild(lc);

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
    ht.appendChild(el("div", "tdl-kicker", "Attach existing trip photos"));
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
      grid.appendChild(el("div", "tdl-empty",
        st.photoLinks.length ?
          "Every trip photo is already attached to this day." :
          "This trip has no photos yet — add them via Photo Intake, then " +
          "cluster from the production Travel Doc."));
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
      var im = document.createElement("img");
      im.src = thumbUrl(l.photo_id);
      im.alt = l.caption || "trip photo";
      im.loading = "lazy";
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
      reloadPhotoEvidence();
    }).catch(function (e) {
      photoEvidence.busy = null;
      photoEvidence.note = label + " failed: " + e.message; renderAll();
    });
  }

  function evBadge(text, on) {
    return el("span", "tdl-ev-badge " + (on ? "tdl-ev-on" : "tdl-ev-off"), text);
  }

  function patchPhotoContext(id, body) {
    api("/api/trips/photo-context/" + encodeURIComponent(id),
        { method: "PATCH", body: body })
      .then(reloadPhotoEvidence)
      .catch(function (e) { photoEvidence.note = e.message; renderAll(); });
  }
  function patchPublicContext(id, body) {
    api("/api/trips/public-context/" + encodeURIComponent(id),
        { method: "PATCH", body: body })
      .then(reloadPhotoEvidence)
      .catch(function (e) { photoEvidence.note = e.message; renderAll(); });
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
    if (isPublic && ct === "place_context") {
      return approved
        ? ("Lori will say: The approved place context says: " + stripDot + ".")
        : ("Lori will say: the place context suggests " + stripDot + ".");
    }
    if (ct === "ocr_text") {
      return approved
        ? ("Lori will say: The approved OCR text says: " + stripDot + ".")
        : ("Lori will say: the OCR draft appears to read '" + stripDot + "'.");
    }
    if (ct === "vision_description") {
      return approved
        ? ("Lori will say: The approved image-context note says: "
           + stripDot + ".")
        : ("Lori will say: the draft image context suggests "
           + stripDot + ".");
    }
    if (ct === "draft_observation") {
      return approved
        ? ("Lori will say: The approved photo observation says: "
           + stripDot + ".")
        : ("Lori will say: the draft photo observation suggests "
           + stripDot + ".");
    }
    // Fallback for less-common types — still safe to preview.
    return approved
      ? ("Lori will speak this as approved context: " + stripDot + ".")
      : ("Lori will treat this as draft (never fact): " + stripDot + ".");
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
    // WO-TRAVEL-DOC-EVIDENCE-TOOLS-01 preflight (2026-07-11): operator-
    // entry lane for local-LLM / operator drafted photo observation.
    // Prompt (native window.prompt) keeps the UI unchanged in shape —
    // just adds a button; no redesign.
    acts.appendChild(btn("tdl-btn", "✍ Add draft observation", function () {
      var t = window.prompt(
        "Draft photo observation — what does the photo show? "
        + "(Stays as DRAFT; won't reach narrator Lori until you approve.)");
      var s = (t || "").trim();
      if (!s) return;
      evidenceAction("/api/trips/photo-links/"
        + encodeURIComponent(sel.id) + "/draft-observation",
        "Draft observation",
        { result_summary: s, engine: "operator_local" });
    }));
    // Operator's place inference rooted in already-reviewable evidence
    // (OCR / public context / operator labels / trip structure). Never
    // consumes raw GPS. Stored as DRAFT trip_public_context row.
    acts.appendChild(btn("tdl-btn", "📍 Infer place from context",
      function () {
        var t = window.prompt(
          "Place inference — based on OCR, public context, trip labels, "
          + "or operator place notes. (Stays as DRAFT; never uses raw GPS.)");
        var s = (t || "").trim();
        if (!s) return;
        evidenceAction("/api/trips/photo-links/"
          + encodeURIComponent(sel.id) + "/place-from-context",
          "Place from context",
          { result_summary: s,
            evidence_sources: ["ocr", "public_context", "trip_labels"] });
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

  document.addEventListener("keydown", function (e) {
    if (!lightbox.open) return;
    if (e.key === "Escape") { e.preventDefault(); closeLightbox(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); lightboxStep(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); lightboxStep(1); }
  });

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
      var im = document.createElement("img");
      im.src = thumbUrl(l.photo_id);
      im.alt = l.caption || "trip photo";
      im.loading = "lazy";
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
      var big = document.createElement("img");
      big.src = thumbUrl(sel.photo_id);
      big.alt = sel.caption || "trip photo";
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

  // ── Story Notes ──────────────────────────────────────────────────────

  function renderNotes() {
    var wrap = el("div");
    wrap.appendChild(el("h1", "", "Story Notes"));
    wrap.appendChild(el("p", "tdl-muted",
      "Location notes across the trip. Toggles write through the existing " +
      "location-notes PATCH — flags stay honest to the DB."));
    if (!st.notes.length) {
      wrap.appendChild(el("div", "tdl-empty", "No story notes yet."));
      return wrap;
    }
    st.notes.forEach(function (n) {
      var row = el("div", "tdl-note-row");
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge", n.source_type || "note"));
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
    var rows = st.sources.filter(function (s) {
      return sourceMatchesFilter(s, st.sourceFilter);
    });
    if (!rows.length) {
      wrap.appendChild(el("div", "tdl-empty",
        st.sources.length ? "No sources in this filter." : "No sources yet."));
      return wrap;
    }
    rows.forEach(function (s) {
      var row = el("div", "tdl-note-row");
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge", s.source_type || "other"));
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
      head.appendChild(el("span", "", "Talk with Lori — Travel Doc workspace"));
      head.appendChild(el("span", "tdl-muted", "surface: travel_doc_modal"));
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
        chip.appendChild(el("small", "tdl-muted",
          " active_trip_day_id=" + String(this.dayId).slice(0, 8) + "…"));
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
          var im = document.createElement("img");
          im.src = thumbUrl(link.photo_id);
          im.alt = "anchored photo";
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
      if (this.ws && this.ws.readyState === 1) return;
      var url = st.apiBase.replace(/^http/, "ws") + "/api/chat/ws";
      var self = this;
      try { this.ws = new WebSocket(url); } catch (e) {
        this.line("system", "Lori connection failed — is the backend running?");
        return;
      }
      this.ws.onmessage = function (ev) {
        var j = {};
        try { j = JSON.parse(ev.data); } catch (_) { return; }
        if (j.type === "token" && j.delta) self.append(j.delta);
        if (j.type === "done") {
          self.finish(j.final_text);
          Promise.all([reloadNotes(), reloadDays()])
            .then(function () { self.refreshDrawer(); })
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

  function openLoriOverlay(dayId) {
    if (dayFormDirtyBlocks()) return;
    st.tab = "plan";
    st.loriReturnTab = "plan";
    st.selectedDayId = dayId || st.selectedDayId;
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
    var scopeLine = el("div", "tdl-lori-overlay-scope");
    scopeLine.appendChild(el("strong", "", (st.trip && st.trip.title) || "Trip"));
    if (loriPane.dayId) {
      scopeLine.appendChild(el("span", "tdl-muted",
        " · active_trip_day_id=" + String(loriPane.dayId).slice(0, 8) + "…"));
    }
    if (loriPane.photoLinkId) {
      scopeLine.appendChild(el("span", "tdl-muted",
        " · active_photo_link_id=" + String(loriPane.photoLinkId).slice(0, 8) + "…"));
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
        var pim = document.createElement("img");
        pim.src = thumbUrl(plink.photo_id);
        pim.alt = "anchored photo";
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

  function renderLoriTab() {
    var wrap = el("div");
    var headRow = el("div", "tdl-head-row");
    var ht = el("div");
    ht.appendChild(el("h1", "", "Lori"));
    ht.appendChild(el("p", "tdl-muted",
      "Operator workspace conversation. Captures land server-side as " +
      "flags-0 candidate notes (never narrator session scope)."));
    headRow.appendChild(ht);
    headRow.appendChild(el("span", "tdl-spacer"));
    headRow.appendChild(btn("tdl-btn", "‹ Back to Trip Plan",
      function () { setTab("plan"); }));
    wrap.appendChild(headRow);
    if (!loriPane.node) loriPane.build();
    loriPane.paintScope();
    loriPane.refreshDrawer();
    loriPane.connect();
    wrap.appendChild(loriPane.node);
    return wrap;
  }

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
})();
