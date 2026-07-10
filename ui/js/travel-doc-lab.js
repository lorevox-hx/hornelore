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
    days: [],            // /days rows (with counts)
    photoLinks: [],      // /photo-links rows
    notes: [],           // /location-notes rows
    sources: [],         // /sources rows
    publicContext: [],   // /public-context rows
    travelogue: null,    // /travelogue-preview (lazy)
    selectedDayId: null,
    selectedPhotoLinkId: null,
    routeSel: null,      // {kind:"region"|"stop", id, regionId}
    photoFilter: "all",
    loriOverlay: false,      // Lori as a drawer over Trip Plan / Photos
    loriReturnTab: "plan",   // context-aware Back label + return surface
    photoPickerDayId: null,  // in-lab day photo picker drawer
    noteDrawerDayId: null,   // in-lab day note drawer
    mainScroll: 0,           // preserved across re-renders / drawer close
    error: "",
  };

  // Module vars (survive re-renders; deliberately NOT in st so a trip
  // switch doesn't reset the operator's layout preference).
  var railCollapsed = false;           // left rail ⟨ toggle
  var insOpen = { overview: true };    // inspector collapsible sections

  var root = document.getElementById("tdlRoot");

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
    if (!st.trip) { renderAll(); return Promise.resolve(); }
    return loadTripBundle(tripId);
  }

  function loadTripBundle(tripId) {
    var t = encodeURIComponent(tripId);
    return Promise.all([
      api("/api/trips/" + t + "/tree"),
      api("/api/trips/" + t + "/days").catch(function () { return { days: [] }; }),
      api("/api/trips/" + t + "/photo-links"),
      api("/api/trips/" + t + "/location-notes"),
      api("/api/trips/" + t + "/sources").catch(function () { return { sources: [] }; }),
      api("/api/trips/" + t + "/public-context").catch(function () { return { public_context: [] }; }),
    ]).then(function (outs) {
      st.tree = outs[0];
      st.days = outs[1].days || [];
      st.photoLinks = outs[2].photo_links || [];
      st.notes = outs[3].notes || [];
      st.sources = outs[4].sources || [];
      st.publicContext = outs[5].public_context || [];
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
      .then(function (out) { st.days = out.days || []; });
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
    if (st.personLabel) brand.appendChild(el("span", "tdl-muted", st.personLabel));
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

    root.appendChild(app);
    main.scrollTop = st.mainScroll || 0;
  }

  // ── left rail: trip list + route navigator (collapsible) ─────────────

  function toggleRail() {
    railCollapsed = !railCollapsed;
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
      "Start and end dates generate one editable card per day. Each day is " +
      "the memory workflow: talk with Lori, add what happened, attach " +
      "photos, notes, meals, places, and sources."));
    head.appendChild(ht);
    wrap.appendChild(head);

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
      "☑ Generate day cards from trip dates", generateDays));
    bar.appendChild(el("span", "tdl-spacer"));
    bar.appendChild(el("span", "tdl-muted",
      "📅 " + (st.trip.start_date || "?") + " → " + (st.trip.end_date || "?")));
    wrap.appendChild(bar);

    if (!st.days.length) {
      wrap.appendChild(el("div", "tdl-empty",
        "No day cards yet. Generate them from the trip dates above " +
        "(needs trip start and end dates)."));
      return wrap;
    }

    var list = el("div", "tdl-day-list");
    st.days.forEach(function (day) { list.appendChild(renderDayCard(day)); });
    wrap.appendChild(list);
    return wrap;
  }

  // DEFERRED (2026-07-10 review): there is no date-range reconcile flow
  // for regenerated days. If trip dates change after day cards exist,
  // out-of-range day cards persist by design (generation only appends
  // missing dates; it never deletes operator work). A reconcile UI /
  // note for those orphaned cards is a future WO.
  function generateDays() {
    if (!st.trip) return;
    api("/api/trips/" + encodeURIComponent(st.trip.id) + "/days/generate-from-dates",
      { method: "POST", body: {} })
      .then(function () { return reloadDays(); })
      .then(function () { st.error = ""; renderAll(); })
      .catch(function (e) { st.error = e.message; renderAll(); });
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
    actions.appendChild(btn("tdl-btn", "✎ Edit day", function () {
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

  // DEFERRED (2026-07-10 review): trip_sources has no trip_day_id column
  // yet, so sources can only be day-scoped by approximation through the
  // day's linked stop/region. True day-scoped sources need a future
  // migration adding trip_day_id to trip_sources — out of lab scope.
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
      if (idx > 0) { st.selectedDayId = st.days[idx - 1].id; renderAll(); }
    }));
    nav.appendChild(btn("tdl-btn tdl-btn-small", "›", function () {
      if (idx < st.days.length - 1) { st.selectedDayId = st.days[idx + 1].id; renderAll(); }
    }));
    nav.appendChild(btn("tdl-btn tdl-btn-small", "×", function () {
      st.selectedDayId = null; dayForm = null; renderAll();
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

    // ── Section: Sources ──
    var daySources = dayScopedRows(st.sources, day);
    var ss = insSection("sources", "Sources (" + daySources.length + ")", false);
    var sl = el("div", "tdl-mini-list");
    daySources.slice(0, 6).forEach(function (s) {
      sl.appendChild(el("div", "", (s.source_type || "source") + " — " +
        (s.title || s.summary || s.link_url || "untitled")));
    });
    if (!daySources.length) sl.appendChild(el("div", "tdl-muted", "None linked."));
    ss.appendChild(sl);
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

  // ── In-lab day photo picker (drawer — no navigation away) ────────────

  function openPhotoPicker(dayId) {
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
        function () { st.selectedPhotoLinkId = l.id; renderAll(); });
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
    }
    ws.appendChild(detail);
    wrap.appendChild(ws);
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

  function renderSources() {
    var wrap = el("div");
    wrap.appendChild(el("h1", "", "Sources"));
    if (!st.sources.length) {
      wrap.appendChild(el("div", "tdl-empty", "No sources yet."));
      return wrap;
    }
    st.sources.forEach(function (s) {
      var row = el("div", "tdl-note-row");
      var badges = el("div", "tdl-note-badges");
      badges.appendChild(el("span", "tdl-badge", s.source_type || "other"));
      if (s.include_in_memoir) badges.appendChild(el("span", "tdl-badge", "in memoir"));
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
