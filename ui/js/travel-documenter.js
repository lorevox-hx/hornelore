/* ═══════════════════════════════════════════════════════════════
   travel-documenter.js — WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01
                        + WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01
                        + WO-TRAVEL-DOC-LAYOUT-REFLOW-01

   OPERATOR-ONLY trip documentation panel, mountable:

     window.lvTravelDocumenterMount(hostEl, {
       person_id,      // required in native mode
       person_label,   // optional display name
       apiBase,        // optional; falls back to LOREVOX_API
       standalone,     // true = show connection inputs (demo page)
     })

   HARD BOUNDARIES (spec + regression-tested):
     - Operator tool ONLY. The shell tab strip is hidden during
       interview mode (body.lv-interview-mode-active #lvShellTabs).
     - NEVER touches Lori/Travels state: no trip-session scope writes,
       nothing consumed by the chat runtime, no system-prompt dispatch.
       Focus mode only toggles a body CSS class (document.body) that
       compresses the shell header visually on the Travel Doc tab; it
       writes no runtime/session state.
     - Uses existing trips endpoints only.

   LAYOUT REFLOW (WO-TRAVEL-DOC-LAYOUT-REFLOW-01):
     The itinerary tile board is the star. Left column = narrator +
     trips list + "New trip"; main column = selected-trip header +
     toolbar (Edit trip / +Region / +Stop / Reload / Memoir) + tile
     board; right sticky column = context editor. Create trip, Add
     region, and Add stop are MODALS (add-stop opens at the tile you
     insert from). Trip photos + Output are collapsed by default;
     Output auto-expands on error.
═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var STOP_TYPES = ["base", "sight", "day_trip", "transit",
                    "lodging", "meal", "disruption", "memory_anchor"];

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function template(opts) {
    var stopTypeOptions = STOP_TYPES.map(function (t) {
      return '<option value="' + t + '"' + (t === "sight" ? " selected" : "") + '>' + t + "</option>";
    }).join("");

    // ── Left column top: connection (standalone) or narrator (native) ──
    var leftTop = opts.standalone
      ? '<section class="td-panel td-setup-panel">' +
        '<h2>Connection</h2>' +
        '<label>API base<input data-td="apiBase" type="text" spellcheck="false" value="' + esc(opts.apiBase || "http://localhost:8000") + '" /></label>' +
        '<label>Narrator / person_id<input data-td="personId" type="text" spellcheck="false" value="' + esc(opts.person_id || "") + '" placeholder="paste person_id or use ?person_id=..." /></label>' +
        '<div class="td-button-row"><button data-td="loadTrips" type="button">Load trips</button><button data-td="ping" type="button" class="td-secondary">Check API</button></div>' +
        '<p class="td-help">Requires <code>HORNELORE_TRIPS=1</code>.</p>' +
        '</section>'
      : '<section class="td-panel td-narrator-panel">' +
        '<h2>Narrator</h2>' +
        '<p class="td-narrator-line">Documenting trips for <strong>' +
        esc(opts.person_label || opts.person_id || "—") + '</strong></p>' +
        '<div class="td-button-row"><button data-td="loadTrips" type="button" class="td-small td-secondary">Reload trips</button><button data-td="focusToggle" type="button" class="td-small td-secondary">Focus</button></div>' +
        '</section>';

    var leftCol =
      '<aside class="td-col td-col-left">' + leftTop +
      '<section class="td-panel td-trip-list-panel">' +
      '<div class="td-panel-head"><h2>Trips</h2><button data-td="refreshTrips" type="button" class="td-small td-secondary">Refresh</button></div>' +
      '<div data-td="tripList" class="td-trip-list td-empty">Load a narrator’s trips.</div>' +
      '<button data-td="openCreateTrip" type="button" class="td-newtrip-btn">+ New trip</button>' +
      '</section>' +
      '</aside>';

    var mainCol =
      '<main class="td-col td-col-main">' +
      '<section class="td-panel td-active-panel">' +
      '<div class="td-panel-head"><div>' +
      '<p class="td-kicker">Selected trip</p>' +
      '<h2 data-td="activeTripTitle">None selected</h2>' +
      '<div data-td="tripMeta" class="td-muted">Choose a trip to document.</div>' +
      '</div></div>' +
      '<div class="td-button-row td-trip-toolbar">' +
      '<button data-td="editTrip" type="button" class="td-small td-secondary">Edit trip</button>' +
      (opts.standalone ? '' :
        '<button data-td="talkLori" type="button" class="td-small td-secondary">Talk with Lori</button>') +
      '<button data-td="addRegionBtn" type="button" class="td-small">+ Region</button>' +
      '<button data-td="addStopBtn" type="button" class="td-small">+ Stop</button>' +
      '<button data-td="reloadTree" type="button" class="td-small td-secondary">Reload</button>' +
      '<button data-td="memoirPreview" type="button" class="td-small td-secondary">Memoir preview</button>' +
      '</div>' +
      '<p class="td-help">Tile order is the route order. Use the tile buttons to reorder, insert, or restructure — dates are just metadata.</p>' +
      '<div data-td="tree" class="td-tree"></div>' +
      '</section>' +
      '</main>';

    var rightCol =
      '<aside class="td-col td-col-right">' +
      '<div class="td-right-toggle">' +
      '<button data-td="viewEditor" type="button" class="td-rtab is-active">Editor</button>' +
      '<button data-td="viewTimeline" type="button" class="td-rtab">Timeline</button>' +
      '</div>' +
      '<section class="td-panel td-editor-panel" data-td="editorPanel">' +
      '<div class="td-panel-head"><h2 data-td="editorTitle">Edit selected</h2><span data-td="editorStatus" class="td-ed-status"></span><button data-td="editorClear" type="button" class="td-small td-secondary">Clear</button></div>' +
      '<div data-td="editorBody" class="td-editor-body"><p class="td-muted">Select a trip, region, or stop tile to edit it.</p></div>' +
      '</section>' +
      '<section class="td-panel td-timeline-panel" data-td="timelinePanel" hidden>' +
      '<div class="td-panel-head"><h2>Timeline</h2></div>' +
      '<div data-td="timelineBody" class="td-timeline-body"></div>' +
      '</section>' +
      '</aside>';

    var bottom =
      '<section class="td-panel td-wide td-collapse-panel">' +
      '<div class="td-panel-head"><button data-td="togglePhotos" type="button" class="td-collapse-toggle">▸ Trip photos</button></div>' +
      '<div data-td="photosBody" class="td-collapse-body" hidden>' +
      '<p class="td-help">Uploads are trusted operator additions: narrator-ready immediately, unplaced at trip level — run Cluster photos to place them at stops.</p>' +
      '<label>Add photos to selected trip<input data-td="photoFiles" type="file" accept="image/*,.heic,.heif" multiple /></label>' +
      '<div class="td-button-row"><button data-td="uploadPhotos" type="button">Upload photos</button><button data-td="clusterPhotos" type="button" class="td-secondary">Cluster photos</button></div>' +
      '<div data-td="photoStrip" class="td-photo-strip td-empty">No trip selected.</div>' +
      '</div>' +
      '</section>' +
      '<section class="td-panel td-wide td-collapse-panel">' +
      '<div class="td-panel-head"><button data-td="toggleOutput" type="button" class="td-collapse-toggle">▸ Output</button><span data-td="statusLine" class="td-status-inline"></span><button data-td="clearOutput" type="button" class="td-small td-secondary">Clear</button></div>' +
      '<pre data-td="output" class="td-output" hidden>Ready.</pre>' +
      '</section>';

    // ── Modals (inside hostEl so CSS stays .td-root-scoped) ──
    var modalCreateTrip =
      '<div class="td-modal-overlay" data-td="modalCreateTrip" hidden>' +
      '<div class="td-modal"><div class="td-modal-head"><h2>Create trip</h2>' +
      '<button data-td="closeCreateTrip" type="button" class="td-modal-x" title="Close">✕</button></div>' +
      '<div class="td-grid-2">' +
      '<label>Title<input data-td="tripTitle" type="text" placeholder="Spring 2026 Europe" /></label>' +
      '<label>Start date<input data-td="tripStart" type="date" /></label>' +
      '<label>End date<input data-td="tripEnd" type="date" /></label>' +
      '</div>' +
      '<label>Summary<textarea data-td="tripSummary" rows="3" placeholder="Short summary of the trip."></textarea></label>' +
      '<div class="td-button-row"><button data-td="createTrip" type="button">Create trip</button><button data-td="cancelCreateTrip" type="button" class="td-secondary">Cancel</button></div>' +
      '</div></div>';

    var modalAddRegion =
      '<div class="td-modal-overlay" data-td="modalAddRegion" hidden>' +
      '<div class="td-modal"><div class="td-modal-head"><h2>Add region</h2>' +
      '<button data-td="closeAddRegion" type="button" class="td-modal-x" title="Close">✕</button></div>' +
      '<div class="td-grid-2">' +
      '<label>Region title<input data-td="regionName" type="text" placeholder="Germany / Bavaria" /></label>' +
      '<label>Country or area<input data-td="regionArea" type="text" placeholder="Germany" /></label>' +
      '<label>Start date<input data-td="regionStart" type="date" /></label>' +
      '<label>End date<input data-td="regionEnd" type="date" /></label>' +
      '</div>' +
      '<label>Base address / lodging<input data-td="regionBase" type="text" placeholder="Hotel, rental, city base" /></label>' +
      '<label>Story / narrative<textarea data-td="regionSummary" rows="3" placeholder="Short synopsis of this leg (e.g. Germany was the first leg — flew into Munich, then train to Prague)."></textarea></label>' +
      '<div class="td-button-row"><button data-td="createRegion" type="button">Add region</button><button data-td="cancelAddRegion" type="button" class="td-secondary">Cancel</button></div>' +
      '</div></div>';

    var modalAddStop =
      '<div class="td-modal-overlay" data-td="modalAddStop" hidden>' +
      '<div class="td-modal"><div class="td-modal-head"><h2>Add stop</h2>' +
      '<span data-td="insertHint" class="td-status-inline"></span>' +
      '<button data-td="closeAddStop" type="button" class="td-modal-x" title="Close">✕</button></div>' +
      '<div class="td-grid-2">' +
      '<label>Region<select data-td="stopRegion"></select></label>' +
      '<label>Parent stop / day trip under<select data-td="stopParent"></select></label>' +
      '<label>Place name<input data-td="stopName" type="text" placeholder="Munich" /></label>' +
      '<label>Stop type<select data-td="stopType">' + stopTypeOptions + '</select></label>' +
      '<label>Start date<input data-td="stopStart" type="date" /></label>' +
      '<label>End date<input data-td="stopEnd" type="date" /></label>' +
      '</div>' +
      '<label>Notes<textarea data-td="stopNotes" rows="3" placeholder="Route details, lodging, meals, people, memories."></textarea></label>' +
      '<div class="td-button-row"><button data-td="createStop" type="button">Add stop</button><button data-td="cancelAddStop" type="button" class="td-secondary">Cancel</button></div>' +
      '</div></div>';

    return '<div class="td-layout">' + leftCol + mainCol + rightCol + bottom +
      modalCreateTrip + modalAddRegion + modalAddStop + '</div>';
  }

  window.lvTravelDocumenterMount = function (hostEl, opts) {
    opts = opts || {};
    var st = {
      apiBase: (opts.apiBase || window.LOREVOX_API || "http://localhost:8000")
        .replace(/\/$/, ""),
      personId: opts.person_id || "",
      trips: [], trip: null, tree: null, photoLinks: [],
      selected: null,
      insertContext: null,
      editorTab: "edit",       // edit | notes | photos | sources
      rightView: "editor",     // editor | timeline
      locationNotes: [],
      sources: [],
    };

    hostEl.classList.add("td-root");
    hostEl.innerHTML = template(opts);

    function $(name) { return hostEl.querySelector('[data-td="' + name + '"]'); }
    function val(name) {
      var el2 = $(name);
      return (el2 && el2.value || "").trim();
    }

    function log(msg, obj) {
      var out = $("output");
      if (!out) return;
      var line = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
      out.textContent = line +
        (obj === undefined ? "" : "\n" + JSON.stringify(obj, null, 2));
    }

    function setStatus(kind, text) {
      var el2 = $("statusLine");
      if (el2) {
        el2.className = "td-status-inline" + (kind ? " " + kind : "");
        el2.textContent = text || "";
      }
      // The Output panel is collapsed by default, so surface status
      // visibly in the editor panel head too (fades on success).
      var es = $("editorStatus");
      if (es) {
        es.className = "td-ed-status" + (kind ? " " + kind : "");
        es.textContent = text || "";
        clearTimeout(es._t);
        if (kind === "good" && text) {
          es._t = setTimeout(function () {
            es.textContent = ""; es.className = "td-ed-status";
          }, 3000);
        }
      }
    }

    // Output is collapsed by default; surface it automatically on error.
    function expandOutput() {
      var o = $("output");
      if (o && o.hidden) {
        o.hidden = false;
        var btn = $("toggleOutput");
        if (btn) btn.textContent = "▾ Output";
      }
    }
    function logError(msg, obj) {
      setStatus("bad", "Error");
      log(msg, obj);
      expandOutput();
    }
    function toggleHidden(bodyName, btnName, labelBase) {
      var b = $(bodyName), btn = $(btnName);
      if (!b) return;
      b.hidden = !b.hidden;
      if (btn) btn.textContent = (b.hidden ? "▸ " : "▾ ") + labelBase;
    }

    // ── Modals ──────────────────────────────────────────────────────────
    function openModal(name) { var m = $(name); if (m) m.hidden = false; }
    function closeModal(name) { var m = $(name); if (m) m.hidden = true; }
    function clearFields(names) {
      names.forEach(function (n) { var e2 = $(n); if (e2) e2.value = ""; });
    }

    function toggleFocus() {
      var on = document.body.classList.toggle("lv-td-focus");
      var b = $("focusToggle");
      if (b) b.textContent = on ? "Exit focus" : "Focus";
    }

    function syncInputs() {
      if (opts.standalone) {
        st.apiBase = (val("apiBase") || "http://localhost:8000").replace(/\/$/, "");
        st.personId = val("personId");
      }
    }

    function api(path, fetchOpts) {
      fetchOpts = fetchOpts || {};
      syncInputs();
      return fetch(st.apiBase + path, Object.assign({}, fetchOpts, {
        headers: fetchOpts.body instanceof FormData ? fetchOpts.headers
          : Object.assign({ "Content-Type": "application/json" },
                          fetchOpts.headers || {}),
      })).then(function (res) {
        return res.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (_) { body = text; }
          if (!res.ok) {
            var detail = body && body.detail ? body.detail : (text || res.statusText);
            throw new Error(res.status + " " + detail);
          }
          return body;
        });
      });
    }

    function allStops(tree) {
      var out = [];
      ((tree && tree.regions) || []).forEach(function (r) {
        var walk = function (s, depth) {
          out.push(Object.assign({}, s, {
            region_id: r.id, region_title: r.title, depth: depth }));
          (s.children || []).forEach(function (c) { walk(c, depth + 1); });
        };
        (r.stops || []).forEach(function (s) { walk(s, 0); });
      });
      return out;
    }

    function locateStop(stopId) {
      var res = null;
      ((st.tree && st.tree.regions) || []).forEach(function (r) {
        function walk(s, parent) {
          if (res) return;
          if (s.id === stopId) { res = { node: s, region: r, parent: parent }; return; }
          (s.children || []).forEach(function (c) { walk(c, s); });
        }
        (r.stops || []).forEach(function (s) { walk(s, null); });
      });
      return res;
    }

    function findRegion(regionId) {
      return ((st.tree && st.tree.regions) || []).filter(function (r) {
        return r.id === regionId;
      })[0] || null;
    }

    function subtreeIds(node) {
      var ids = [];
      (function walk(s) { ids.push(s.id); (s.children || []).forEach(walk); })(node);
      return ids;
    }

    function dateSpan(a, b) { return [a, b].filter(Boolean).join(" to "); }

    // Soft (non-blocking) out-of-range date check. YYYY-MM-DD compares
    // lexicographically. Returns a warning string or "".
    function dateRangeWarning(start, end, boundStart, boundEnd, label) {
      var bad = (start && boundStart && start < boundStart) ||
                (end && boundEnd && end > boundEnd) ||
                (start && boundEnd && start > boundEnd) ||
                (end && boundStart && end < boundStart);
      return bad ? ("\u26a0 Dates fall outside the " + label +
        " range — saved anyway.") : "";
    }

    function attachDateWarning(parent, vStart, vEnd, boundStart, boundEnd, label) {
      var warn = el("div", "td-date-warn");
      function upd() {
        var msg = dateRangeWarning(vStart.value, vEnd.value, boundStart, boundEnd, label);
        warn.textContent = msg;
        warn.style.display = msg ? "" : "none";
      }
      upd();
      vStart.addEventListener("change", upd);
      vEnd.addEventListener("change", upd);
      parent.appendChild(warn);
    }

    function selectItem(kind, id) {
      st.selected = kind && id ? { kind: kind, id: id } : null;
      renderTree();
    }

    function clearSelection() {
      st.selected = null;
      renderTree();
    }

    function refreshCurrentTrip() {
      if (!st.trip) return Promise.resolve();
      var tid = st.trip.id;
      return loadTrips().then(function () {
        var t = st.trips.filter(function (x) { return x.id === tid; })[0];
        if (t) return openTrip(t);
        st.trip = null; st.tree = null; st.selected = null;
        renderTree();
      });
    }

    function renderTrips() {
      var host = $("tripList");
      host.className = "td-trip-list" + (st.trips.length ? "" : " td-empty");
      if (!st.trips.length) {
        host.textContent = "No trips found for this narrator.";
        return;
      }
      host.innerHTML = "";
      st.trips.forEach(function (t) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "td-trip-card" +
          (st.trip && st.trip.id === t.id ? " active" : "");
        btn.innerHTML = '<span class="td-trip-card-title">' +
          esc(t.title || "Untitled trip") +
          '</span><span class="td-trip-card-dates">' +
          esc(dateSpan(t.start_date, t.end_date) || t.id) + "</span>";
        btn.addEventListener("click", function () { openTrip(t); });
        host.appendChild(btn);
      });
    }

    function renderPhotos() {
      var host = $("photoStrip");
      if (!host) return;
      if (!st.trip) {
        host.className = "td-photo-strip td-empty";
        host.textContent = "No trip selected.";
        return;
      }
      var links = st.photoLinks || [];
      if (!links.length) {
        host.className = "td-photo-strip td-empty";
        host.textContent = "No linked photos yet.";
        return;
      }
      host.className = "td-photo-strip";
      host.innerHTML = "";
      links.slice(0, 60).forEach(function (l) {
        var img = document.createElement("img");
        img.loading = "lazy";
        img.alt = l.caption || "Trip photo";
        img.src = st.apiBase + "/api/photos/" +
          encodeURIComponent(l.photo_id) + "/thumb";
        img.addEventListener("error", function () { img.remove(); });
        host.appendChild(img);
      });
    }

    function rebuildParentOptions() {
      var regionSel = $("stopRegion");
      var parentSel = $("stopParent");
      if (!parentSel) return;
      parentSel.innerHTML = "<option value=''>No parent / top-level stop</option>";
      if (!st.tree) return;
      var selectedRegion = (regionSel && regionSel.value) || "";
      allStops(st.tree).forEach(function (s) {
        if (selectedRegion && s.region_id !== selectedRegion) return;
        var opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = new Array((s.depth || 0) + 1).join("— ") +
          (s.location_name || s.title || "Stop") +
          " (" + (s.region_title || "region") + ")";
        parentSel.appendChild(opt);
      });
    }

    // ── Tile rendering ──────────────────────────────────────────────────

    function tileBtn(label, title, onClick, tone) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "td-tile-btn" + (tone ? " " + tone : "");
      b.title = title || label;
      b.textContent = label;
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        Promise.resolve().then(onClick).catch(function (err) {
          logError("Error", { message: err.message });
        });
      });
      return b;
    }

    function renderStopTile(stop, region, depth, parentStop) {
      var row = el("div", "td-stop td-tile td-stop-tile");
      row.style.marginLeft = (depth * 18) + "px";
      row.dataset.stopId = stop.id;
      if (st.selected && st.selected.kind === "stop" && st.selected.id === stop.id) {
        row.classList.add("is-selected");
      }

      var head = el("div", "td-tile-head");
      var main = document.createElement("button");
      main.type = "button";
      main.className = "td-tile-main";
      main.innerHTML =
        '<strong>' + esc(stop.location_name || stop.title || "Stop") + '</strong>' +
        '<small>' + esc([stop.stop_type, dateSpan(stop.date_start, stop.date_end), stop.notes]
          .filter(Boolean).join(" · ")) + '</small>' + stopIndicators(stop);
      main.addEventListener("click", function () { selectItem("stop", stop.id); });

      var actions = el("div", "td-tile-actions");
      actions.appendChild(tileBtn("↑", "Move up", function () {
        return moveStopRelative(stop, region, parentStop, -1);
      }));
      actions.appendChild(tileBtn("↓", "Move down", function () {
        return moveStopRelative(stop, region, parentStop, 1);
      }));
      actions.appendChild(tileBtn("+ Before", "Add a stop before this one", function () {
        beginInsertStop(region.id, parentStop ? parentStop.id : null, stop.id, "before");
      }));
      actions.appendChild(tileBtn("+ After", "Add a stop after this one", function () {
        beginInsertStop(region.id, parentStop ? parentStop.id : null, stop.id, "after");
      }));
      actions.appendChild(tileBtn("Edit", "Edit this stop", function () {
        selectItem("stop", stop.id);
      }));
      actions.appendChild(tileBtn("Delete", "Delete this stop", function () {
        return deleteStop(stop);
      }, "danger"));

      head.appendChild(main);
      head.appendChild(actions);
      row.appendChild(head);

      (stop.children || []).forEach(function (child) {
        row.appendChild(renderStopTile(child, region, depth + 1, stop));
      });
      return row;
    }

    function renderRegionTile(region) {
      var wrap = el("div", "td-region td-tile td-region-tile");
      wrap.dataset.regionId = region.id;
      if (st.selected && st.selected.kind === "region" && st.selected.id === region.id) {
        wrap.classList.add("is-selected");
      }

      var head = el("div", "td-tile-head td-region-header");
      var main = document.createElement("button");
      main.type = "button";
      main.className = "td-tile-main";
      main.innerHTML =
        '<strong>' + esc(region.title || "Region") + '</strong>' +
        '<small>' + esc(dateSpan(region.start_date, region.end_date) ||
          region.country_or_area || "") + '</small>' + regionIndicators(region);
      main.addEventListener("click", function () { selectItem("region", region.id); });

      var actions = el("div", "td-tile-actions");
      actions.appendChild(tileBtn("↑", "Move region up", function () {
        return moveRegionRelative(region, -1);
      }));
      actions.appendChild(tileBtn("↓", "Move region down", function () {
        return moveRegionRelative(region, 1);
      }));
      actions.appendChild(tileBtn("+ Stop", "Add a stop in this region", function () {
        beginAddStop(region.id);
      }));
      actions.appendChild(tileBtn("Edit", "Edit this region", function () {
        selectItem("region", region.id);
      }));
      actions.appendChild(tileBtn("Delete", "Delete this region", function () {
        return deleteRegion(region);
      }, "danger"));

      head.appendChild(main);
      head.appendChild(actions);
      wrap.appendChild(head);

      var stopsHost = el("div", "td-region-stops");
      if ((region.stops || []).length) {
        (region.stops || []).forEach(function (s) {
          stopsHost.appendChild(renderStopTile(s, region, 0, null));
        });
      } else {
        stopsHost.appendChild(el("div", "td-muted", "No stops yet."));
      }
      wrap.appendChild(stopsHost);
      return wrap;
    }

    function renderTree() {
      var title = $("activeTripTitle");
      var meta = $("tripMeta");
      var treeHost = $("tree");
      var regionSel = $("stopRegion");
      var parentSel = $("stopParent");

      if (!st.trip || !st.tree) {
        title.textContent = "None selected";
        meta.textContent = "Choose a trip to document.";
        treeHost.innerHTML = "";
        if (regionSel) regionSel.innerHTML = "<option value=''>Select a trip first</option>";
        if (parentSel) parentSel.innerHTML = "<option value=''>No parent</option>";
        renderPhotos();
        renderEditor();
        return;
      }

      title.textContent = st.trip.title || "Untitled trip";
      meta.textContent = dateSpan(st.trip.start_date, st.trip.end_date) || st.trip.id;

      var regions = st.tree.regions || [];
      if (regionSel) {
        regionSel.innerHTML = regions.length ? "" : "<option value=''>Add a region first</option>";
        regions.forEach(function (r) {
          var opt = document.createElement("option");
          opt.value = r.id;
          opt.textContent = r.title || "Region";
          regionSel.appendChild(opt);
        });
      }
      rebuildParentOptions();

      treeHost.innerHTML = "";
      if (!regions.length) {
        treeHost.appendChild(el("p", "td-empty", "No regions yet. Use + Region to add the first one."));
      } else {
        regions.forEach(function (r) { treeHost.appendChild(renderRegionTile(r)); });
      }
      renderPhotos();
      renderEditor();
      if (st.rightView === "timeline") renderTimeline();
    }

    // ── Editor panel ────────────────────────────────────────────────────

    function edField(parent, labelText, input) {
      var l = el("label", "td-ed-field");
      l.appendChild(el("span", "td-ed-label", labelText));
      l.appendChild(input);
      parent.appendChild(l);
      return input;
    }
    function edText(parent, label, value) {
      var i = document.createElement("input");
      i.type = "text"; i.value = value || "";
      return edField(parent, label, i);
    }
    function edDate(parent, label, value) {
      var i = document.createElement("input");
      i.type = "date"; i.value = value || "";
      return edField(parent, label, i);
    }
    function edArea(parent, label, value) {
      var t = document.createElement("textarea");
      t.rows = 3; t.value = value || "";
      return edField(parent, label, t);
    }
    function edSelect(parent, label, options, value) {
      var s = document.createElement("select");
      options.forEach(function (o) {
        var opt = document.createElement("option");
        opt.value = o.value; opt.textContent = o.label;
        if (o.value === value) opt.selected = true;
        s.appendChild(opt);
      });
      return edField(parent, label, s);
    }
    function edActions(parent, saveFn, deleteFn) {
      var row = el("div", "td-button-row td-ed-actions");
      var save = el("button", "", "Save"); save.type = "button";
      save.addEventListener("click", function () {
        Promise.resolve().then(saveFn).catch(function (e) {
          logError("Error", { message: e.message });
        });
      });
      row.appendChild(save);
      if (deleteFn) {
        var del = el("button", "td-danger", "Delete"); del.type = "button";
        del.addEventListener("click", function () {
          Promise.resolve().then(deleteFn).catch(function (e) {
            logError("Error", { message: e.message });
          });
        });
        row.appendChild(del);
      }
      parent.appendChild(row);
    }

    function editorScopeName() {
      if (!st.selected) return "";
      if (st.selected.kind === "trip") return (st.trip && st.trip.title) || "trip";
      if (st.selected.kind === "region") {
        var r = findRegion(st.selected.id);
        return r ? (r.title || "region") : "region";
      }
      var l = locateStop(st.selected.id);
      return l ? (l.node.location_name || l.node.title || "stop") : "stop";
    }

    function editorScope() {
      if (!st.selected) return { region_id: null, stop_id: null };
      if (st.selected.kind === "region") return { region_id: st.selected.id, stop_id: null };
      if (st.selected.kind === "stop") {
        var l = locateStop(st.selected.id);
        return { region_id: l ? l.region.id : null, stop_id: st.selected.id };
      }
      return { region_id: null, stop_id: null };
    }

    function renderEditor() {
      var title = $("editorTitle");
      var body = $("editorBody");
      if (!title || !body) return;

      if (!st.selected || !st.trip) {
        title.textContent = "Edit selected";
        body.innerHTML = '<p class="td-muted">Select a trip, region, or stop tile to edit it.</p>';
        return;
      }
      var kind = st.selected.kind;
      title.textContent = kind.charAt(0).toUpperCase() + kind.slice(1) +
        " · " + editorScopeName();
      body.innerHTML = "";
      var tabsBar = el("div", "td-ed-tabs");
      [["edit", "Edit"], ["notes", "Story notes"], ["photos", "Photos"],
       ["sources", "Sources"]]
        .forEach(function (t) {
          var b = el("button", "td-ed-tab" +
            (st.editorTab === t[0] ? " is-active" : ""), t[1]);
          b.type = "button";
          b.addEventListener("click", function () {
            st.editorTab = t[0];
            renderEditor();
          });
          tabsBar.appendChild(b);
        });
      body.appendChild(tabsBar);
      var pane = el("div", "td-ed-pane");
      body.appendChild(pane);
      if (st.editorTab === "notes") return renderNotesTab(pane);
      if (st.editorTab === "photos") return renderPhotosTab(pane);
      if (st.editorTab === "sources") return renderSourcesTab(pane);
      if (kind === "trip") return renderTripEditor(pane);
      if (kind === "region") return renderRegionEditor(pane);
      if (kind === "stop") return renderStopEditor(pane);
    }

    // ── Story notes tab ─────────────────────────────────────────────────

    function reloadNotes() {
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/location-notes")
        .then(function (out) {
          st.locationNotes = (out && out.notes) || [];
          renderTree();   // refresh tile badges too, not just the editor
        });
    }

    function noteToggle(n, field, label) {
      var wrap = el("label", "td-note-toggle");
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !!n[field];
      cb.addEventListener("change", function () {
        var patch = {}; patch[field] = cb.checked;
        Promise.resolve().then(function () {
          return api("/api/trips/location-notes/" + encodeURIComponent(n.id),
            { method: "PATCH", body: JSON.stringify(patch) })
            .then(function () { return reloadNotes(); });
        }).catch(function (e) {
          cb.checked = !cb.checked;
          logError("Error", { message: e.message });
        });
      });
      wrap.appendChild(cb);
      wrap.appendChild(el("span", "", label));
      return wrap;
    }

    function renderNoteCard(n) {
      var card = el("div", "td-note-card");
      var head = el("div", "td-note-head");
      head.appendChild(el("strong", "", n.note_title || "(untitled)"));
      head.appendChild(el("span", "td-note-badge td-src-" + (n.source_type || "operator"),
        n.source_type || "operator"));
      card.appendChild(head);
      card.appendChild(el("p", "td-note-text", n.note_text || ""));
      var flags = el("div", "td-note-flags");
      flags.appendChild(noteToggle(n, "include_in_memoir", "In memoir"));
      flags.appendChild(noteToggle(n, "include_in_interview_context", "Lori context candidate"));
      var del = el("button", "td-tile-btn danger", "Delete");
      del.type = "button";
      del.addEventListener("click", function () {
        if (!window.confirm("Delete this story note?")) return;
        Promise.resolve().then(function () {
          return api("/api/trips/location-notes/" + encodeURIComponent(n.id),
            { method: "DELETE" })
            .then(function () { setStatus("good", "Note deleted"); return reloadNotes(); });
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      flags.appendChild(del);
      card.appendChild(flags);
      return card;
    }

    function renderNotesTab(pane) {
      var scope = editorScope();
      var kind = st.selected.kind;
      var notes = (st.locationNotes || []).filter(function (n) {
        if (kind === "stop") return n.trip_stop_id === scope.stop_id;
        if (kind === "region") return n.trip_region_id === scope.region_id && !n.trip_stop_id;
        return !n.trip_region_id && !n.trip_stop_id;
      });
      pane.appendChild(el("p", "td-help",
        "Notes here are private until you flip a flag. In memoir = goes into the "
        + "travel memoir. Lori context candidate = saved for future Lori context; "
        + "not used live yet."));
      if (!notes.length) {
        pane.appendChild(el("p", "td-muted", "No story notes for this " + kind + " yet."));
      } else {
        notes.forEach(function (n) { pane.appendChild(renderNoteCard(n)); });
      }
      pane.appendChild(el("h3", "td-note-add-h", "Add a story note"));
      var f = el("div", "td-editor-form");
      var vTitle = edText(f, "Title (optional)", "");
      var vText = edArea(f, "Story note", "");
      var row = el("div", "td-button-row");
      var addBtn = el("button", "", "Add note"); addBtn.type = "button";
      addBtn.addEventListener("click", function () {
        Promise.resolve().then(function () {
          var text = (vText.value || "").trim();
          if (!text) throw new Error("note text is required");
          return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/location-notes", {
            method: "POST",
            body: JSON.stringify({
              note_text: text,
              note_title: vTitle.value || null,
              trip_region_id: scope.region_id,
              trip_stop_id: scope.stop_id,
              source_type: "operator",
            }),
          }).then(function () { setStatus("good", "Note added"); return reloadNotes(); });
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      row.appendChild(addBtn);
      f.appendChild(row);
      pane.appendChild(f);
    }

    // ── Photos tab (scope upload + scoped thumbnails) ───────────────────

    function uploadPhotosToTrip(fileInput) {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var files = Array.prototype.slice.call((fileInput && fileInput.files) || []);
      if (!files.length) return Promise.reject(new Error("choose at least one photo"));
      var fd = new FormData();
      files.forEach(function (f) { fd.append("files", f); });
      fd.append("uploaded_by_user_id", "travel_documenter");
      fd.append("narrator_ready", "true");
      fd.append("uploaded_from_surface", "travel_documenter");
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/photos",
        { method: "POST", body: fd })
        .then(function (out) {
          log("Photos uploaded", out);
          setStatus("good", "Photos uploaded");
          return refreshCurrentTrip();
        });
    }

    function regionNameById(id) {
      var r = findRegion(id); return r ? (r.title || "region") : "region";
    }
    function stopNameById(id) {
      var l = locateStop(id); return l ? (l.node.location_name || l.node.title || "stop") : "stop";
    }
    function indBadges(hasStory, notes, srcs, photos) {
      var parts = [];
      if (hasStory) parts.push("story");
      if (notes) parts.push(notes + " note" + (notes > 1 ? "s" : ""));
      if (srcs) parts.push(srcs + " doc" + (srcs > 1 ? "s" : ""));
      if (photos) parts.push(photos + " photo" + (photos > 1 ? "s" : ""));
      return parts.length
        ? '<span class="td-tile-ind">' + esc(parts.join(" · ")) + '</span>' : '';
    }
    function regionIndicators(r) {
      var notes = (st.locationNotes || []).filter(function (n) {
        return n.trip_region_id === r.id && !n.trip_stop_id; }).length;
      var srcs = (st.sources || []).filter(function (s) {
        return s.trip_region_id === r.id && !s.trip_stop_id; }).length;
      var photos = (st.photoLinks || []).filter(function (l) {
        return l.trip_region_id === r.id && !l.trip_stop_id; }).length;
      return indBadges(!!r.summary, notes, srcs, photos);
    }
    function stopIndicators(s) {
      var notes = (st.locationNotes || []).filter(function (n) {
        return n.trip_stop_id === s.id; }).length;
      var srcs = (st.sources || []).filter(function (x) {
        return x.trip_stop_id === s.id; }).length;
      var photos = (st.photoLinks || []).filter(function (l) {
        return l.trip_stop_id === s.id; }).length;
      return indBadges(!!s.notes, notes, srcs, photos);
    }

    function uploadPhotosToRegion(regionId, fileInput) {
      var files = Array.prototype.slice.call((fileInput && fileInput.files) || []);
      if (!files.length) return Promise.reject(new Error("choose at least one photo"));
      var fd = new FormData();
      files.forEach(function (f) { fd.append("files", f); });
      fd.append("uploaded_by_user_id", "travel_documenter");
      fd.append("narrator_ready", "true");
      fd.append("uploaded_from_surface", "travel_documenter");
      return api("/api/trips/" + encodeURIComponent(st.trip.id) +
        "/regions/" + encodeURIComponent(regionId) + "/photos",
        { method: "POST", body: fd })
        .then(function () {
          setStatus("good", "Photos added to this region");
          return refreshCurrentTrip();
        });
    }

    function renderPhotoCard(l) {
      var card = el("div", "td-photo-card");
      var img = document.createElement("img");
      img.loading = "lazy"; img.className = "td-photo-card-img";
      img.alt = l.caption || "Trip photo";
      img.src = st.apiBase + "/api/photos/" + encodeURIComponent(l.photo_id) + "/thumb";
      img.addEventListener("error", function () {
        img.replaceWith(el("div", "td-photo-missing", "no preview"));
      });
      card.appendChild(img);
      var place = l.trip_stop_id ? stopNameById(l.trip_stop_id)
        : (l.trip_region_id ? regionNameById(l.trip_region_id) : "unplaced");
      card.appendChild(el("small", "td-muted", place));
      var cap = document.createElement("input");
      cap.type = "text"; cap.value = l.caption || ""; cap.placeholder = "caption";
      cap.className = "td-photo-cap";
      cap.addEventListener("change", function () {
        Promise.resolve().then(function () {
          return api("/api/trips/photo-links/" + encodeURIComponent(l.id),
            { method: "PATCH", body: JSON.stringify({ caption: cap.value }) })
            .then(function () { setStatus("good", "Caption saved"); });
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      card.appendChild(cap);
      var wrap = el("label", "td-note-toggle");
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !!l.include_in_memoir;
      cb.addEventListener("change", function () {
        Promise.resolve().then(function () {
          return api("/api/trips/photo-links/" + encodeURIComponent(l.id),
            { method: "PATCH", body: JSON.stringify({ include_in_memoir: cb.checked }) })
            .then(function () {
              setStatus("good", "Updated");
              return refreshCurrentTrip();
            });
        }).catch(function (e) { cb.checked = !cb.checked; logError("Error", { message: e.message }); });
      });
      wrap.appendChild(cb);
      wrap.appendChild(el("span", "", "In memoir"));
      card.appendChild(wrap);
      return card;
    }

    function renderPhotosTab(pane) {
      var scope = editorScope();
      var kind = st.selected.kind;
      var f = el("div", "td-editor-form");
      var fileIn = document.createElement("input");
      fileIn.type = "file"; fileIn.accept = "image/*,.heic,.heif"; fileIn.multiple = true;
      edField(f, kind === "stop" ? "Add photos to this stop" : "Add photos", fileIn);
      var row = el("div", "td-button-row");
      var upBtn = el("button", "", "Upload"); upBtn.type = "button";
      upBtn.addEventListener("click", function () {
        Promise.resolve().then(function () {
          if (kind === "stop") return uploadPhotosToStop(scope.stop_id, fileIn);
          if (kind === "region") return uploadPhotosToRegion(scope.region_id, fileIn);
          return uploadPhotosToTrip(fileIn);
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      row.appendChild(upBtn);
      f.appendChild(row);
      pane.appendChild(f);
      var links = (st.photoLinks || []).filter(function (l) {
        if (kind === "stop") return l.trip_stop_id === scope.stop_id;
        if (kind === "region") return l.trip_region_id === scope.region_id;
        return true;
      });
      if (!links.length) {
        pane.appendChild(el("p", "td-muted", "No linked photos here yet."));
      } else {
        var grid = el("div", "td-photo-grid");
        links.slice(0, 80).forEach(function (l) { grid.appendChild(renderPhotoCard(l)); });
        pane.appendChild(grid);
      }
    }

    // ── Sources tab (documents lane — WO-TRAVEL-DOC-SOURCES-01) ─────────

    function reloadSources() {
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/sources")
        .then(function (out) {
          st.sources = (out && out.sources) || [];
          renderTree();   // refresh tile badges too, not just the editor
        });
    }

    function sourceTypeSelect() {
      var s = document.createElement("select");
      ["itinerary", "receipt", "hotel", "ticket", "note", "map", "link", "other"]
        .forEach(function (t) {
          var o = document.createElement("option");
          o.value = t; o.textContent = t;
          if (t === "other") o.selected = true;
          s.appendChild(o);
        });
      return s;
    }

    function sourceMemoirToggle(s) {
      var wrap = el("label", "td-note-toggle");
      var cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = !!s.include_in_memoir;
      cb.addEventListener("change", function () {
        Promise.resolve().then(function () {
          return api("/api/trips/sources/" + encodeURIComponent(s.id),
            { method: "PATCH", body: JSON.stringify({ include_in_memoir: cb.checked }) })
            .then(function () { return reloadSources(); });
        }).catch(function (e) {
          cb.checked = !cb.checked;
          logError("Error", { message: e.message });
        });
      });
      wrap.appendChild(cb);
      wrap.appendChild(el("span", "", "In memoir"));
      return wrap;
    }

    function renderSourceCard(s) {
      var card = el("div", "td-note-card");
      var head = el("div", "td-note-head");
      head.appendChild(el("strong", "", s.title || s.filename || "(untitled source)"));
      head.appendChild(el("span", "td-note-badge", s.source_type || "other"));
      card.appendChild(head);
      var meta = [s.filename, s.link_url, s.source_date].filter(Boolean);
      if (meta.length) card.appendChild(el("small", "td-muted", meta.join(" · ")));
      if (s.pasted_text) card.appendChild(el("p", "td-note-text", s.pasted_text));
      if (s.summary) card.appendChild(el("p", "td-note-text", s.summary));
      var flags = el("div", "td-note-flags");
      flags.appendChild(sourceMemoirToggle(s));
      var del = el("button", "td-tile-btn danger", "Delete");
      del.type = "button";
      del.addEventListener("click", function () {
        if (!window.confirm("Delete this source?")) return;
        Promise.resolve().then(function () {
          return api("/api/trips/sources/" + encodeURIComponent(s.id),
            { method: "DELETE" })
            .then(function () { setStatus("good", "Source deleted"); return reloadSources(); });
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      flags.appendChild(del);
      card.appendChild(flags);
      return card;
    }

    function uploadSourceFiles(fileInput, sourceType, scope) {
      var files = Array.prototype.slice.call((fileInput && fileInput.files) || []);
      if (!files.length) return Promise.reject(new Error("choose at least one file"));
      var fd = new FormData();
      files.forEach(function (f) { fd.append("files", f); });
      fd.append("source_type", sourceType || "other");
      if (scope.region_id) fd.append("trip_region_id", scope.region_id);
      if (scope.stop_id) fd.append("trip_stop_id", scope.stop_id);
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/sources/upload",
        { method: "POST", body: fd })
        .then(function () { setStatus("good", "Document uploaded"); return reloadSources(); });
    }

    function renderSourcesTab(pane) {
      var scope = editorScope();
      var kind = st.selected.kind;
      var rows = (st.sources || []).filter(function (s) {
        if (kind === "stop") return s.trip_stop_id === scope.stop_id;
        if (kind === "region") return s.trip_region_id === scope.region_id && !s.trip_stop_id;
        return !s.trip_region_id && !s.trip_stop_id;
      });
      pane.appendChild(el("p", "td-help",
        "Documents, tickets, receipts, links, or pasted notes for this " + kind +
        ". Private unless you flip In memoir."));
      if (!rows.length) {
        pane.appendChild(el("p", "td-muted", "No sources here yet."));
      } else {
        rows.forEach(function (s) { pane.appendChild(renderSourceCard(s)); });
      }
      // Upload a file
      pane.appendChild(el("h3", "td-note-add-h", "Upload a document"));
      var upf = el("div", "td-editor-form");
      var fileIn = document.createElement("input");
      fileIn.type = "file"; fileIn.multiple = true;
      edField(upf, "File(s) — PDF, ticket, receipt, screenshot…", fileIn);
      var upType = sourceTypeSelect();
      edField(upf, "Type", upType);
      var upRow = el("div", "td-button-row");
      var upBtn = el("button", "", "Upload"); upBtn.type = "button";
      upBtn.addEventListener("click", function () {
        Promise.resolve().then(function () {
          return uploadSourceFiles(fileIn, upType.value, scope);
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      upRow.appendChild(upBtn);
      upf.appendChild(upRow);
      pane.appendChild(upf);
      // Or paste text / link
      pane.appendChild(el("h3", "td-note-add-h", "Or add a note / link"));
      var f = el("div", "td-editor-form");
      var vTitle = edText(f, "Title (optional)", "");
      var vType = sourceTypeSelect();
      edField(f, "Type", vType);
      var vLink = edText(f, "Link URL (optional)", "");
      var vText = edArea(f, "Pasted text / note", "");
      var row = el("div", "td-button-row");
      var addBtn = el("button", "", "Add source"); addBtn.type = "button";
      addBtn.addEventListener("click", function () {
        Promise.resolve().then(function () {
          if (!(vText.value || "").trim() && !(vLink.value || "").trim() &&
              !(vTitle.value || "").trim()) {
            throw new Error("add text, a link, or a title");
          }
          return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/sources", {
            method: "POST",
            body: JSON.stringify({
              source_type: vType.value || "other",
              title: vTitle.value || null,
              trip_region_id: scope.region_id,
              trip_stop_id: scope.stop_id,
              pasted_text: vText.value || null,
              link_url: vLink.value || null,
            }),
          }).then(function () { setStatus("good", "Source added"); return reloadSources(); });
        }).catch(function (e) { logError("Error", { message: e.message }); });
      });
      row.appendChild(addBtn);
      f.appendChild(row);
      pane.appendChild(f);
    }

    // ── Right-column view toggle + accordion Timeline (read-only nav) ───

    function applyRightView() {
      var ep = $("editorPanel"), tp = $("timelinePanel");
      var ve = $("viewEditor"), vt = $("viewTimeline");
      var timeline = st.rightView === "timeline";
      if (ep) ep.hidden = timeline;
      if (tp) tp.hidden = !timeline;
      if (ve) ve.className = "td-rtab" + (timeline ? "" : " is-active");
      if (vt) vt.className = "td-rtab" + (timeline ? " is-active" : "");
      if (timeline) renderTimeline();
    }

    function firstThumbFor(kind, item) {
      var links = (st.photoLinks || []).filter(function (l) {
        return kind === "region" ? (l.trip_region_id === item.id)
                                 : (l.trip_stop_id === item.id);
      });
      return links.length ? links[0].photo_id : null;
    }

    function renderTlRow(kind, item, depth) {
      var row = document.createElement("button");
      row.type = "button";
      row.className = "td-tl-row" +
        (st.selected && st.selected.kind === kind && st.selected.id === item.id
          ? " is-selected" : "");
      row.style.marginLeft = (depth * 14) + "px";
      var thumbId = firstThumbFor(kind, item);
      var thumb = thumbId
        ? '<img class="td-tl-thumb" loading="lazy" alt="" src="' +
          esc(st.apiBase + "/api/photos/" + encodeURIComponent(thumbId) + "/thumb") + '">'
        : '<span class="td-tl-thumb td-tl-thumb-empty"></span>';
      var name = kind === "region" ? (item.title || "Region")
                                   : (item.location_name || item.title || "Stop");
      var dates = kind === "region"
        ? dateSpan(item.start_date, item.end_date)
        : dateSpan(item.date_start, item.date_end);
      var counts = kind === "region" ? regionIndicators(item) : stopIndicators(item);
      row.innerHTML = thumb + '<span class="td-tl-main"><strong>' + esc(name) +
        '</strong>' + (dates ? '<small class="td-muted">' + esc(dates) + '</small>' : '') +
        (counts || '') + '</span>';
      row.addEventListener("click", function () {
        selectItem(kind, item.id);
        st.rightView = "editor";
        applyRightView();
      });
      return row;
    }

    function renderTimeline() {
      var body = $("timelineBody");
      if (!body) return;
      body.innerHTML = "";
      if (!st.trip || !st.tree) {
        body.appendChild(el("p", "td-muted", "Select a trip to see its timeline."));
        return;
      }
      var head = el("div", "td-tl-trip");
      head.appendChild(el("strong", "", st.trip.title || "Trip"));
      var td = dateSpan(st.trip.start_date, st.trip.end_date);
      if (td) head.appendChild(el("small", "td-muted", td));
      body.appendChild(head);
      function walkStop(s, depth) {
        body.appendChild(renderTlRow("stop", s, depth));
        (s.children || []).forEach(function (c) { walkStop(c, depth + 1); });
      }
      (st.tree.regions || []).forEach(function (r) {
        body.appendChild(renderTlRow("region", r, 0));
        (r.stops || []).forEach(function (s) { walkStop(s, 1); });
      });
    }

    function renderTripEditor(pane) {
      var trip = st.trip;
      var f = el("div", "td-editor-form");
      var vTitle = edText(f, "Title", trip.title);
      var vStart = edDate(f, "Start date", trip.start_date);
      var vEnd = edDate(f, "End date", trip.end_date);
      var vSummary = edArea(f, "Summary", trip.summary);
      edActions(f, function () {
        var name = (vTitle.value || "").trim();
        if (!name) throw new Error("trip title is required");
        return api("/api/trips/" + encodeURIComponent(trip.id), {
          method: "PATCH",
          body: JSON.stringify({
            title: name,
            start_date: vStart.value || null,
            clear_start_date: !vStart.value,
            end_date: vEnd.value || null,
            clear_end_date: !vEnd.value,
            summary: vSummary.value || null,
            clear_summary: !vSummary.value,
          }),
        }).then(function (out) {
          log("Trip updated", out);
          setStatus("good", "Trip saved");
          return refreshCurrentTrip();
        });
      }, function () {
        return deleteTrip(trip);
      });
      pane.appendChild(f);
    }

    function renderRegionEditor(pane) {
      var region = findRegion(st.selected.id);
      if (!region) { st.selected = null; return renderEditor(); }
      var f = el("div", "td-editor-form");
      var vTitle = edText(f, "Region title", region.title);
      var vArea = edText(f, "Country or area", region.country_or_area);
      var vStart = edDate(f, "Start date", region.start_date);
      var vEnd = edDate(f, "End date", region.end_date);
      var vBase = edText(f, "Base address / lodging", region.base_address);
      var vSummary = edArea(f, "Story / narrative", region.summary);
      if (st.trip) {
        attachDateWarning(f, vStart, vEnd, st.trip.start_date, st.trip.end_date, "trip");
      }
      edActions(f, function () {
        var name = (vTitle.value || "").trim();
        if (!name) throw new Error("region title is required");
        return api("/api/trips/regions/" + encodeURIComponent(region.id), {
          method: "PATCH",
          body: JSON.stringify({
            title: name,
            country_or_area: vArea.value || null,
            clear_country_or_area: !vArea.value,
            start_date: vStart.value || null,
            clear_start_date: !vStart.value,
            end_date: vEnd.value || null,
            clear_end_date: !vEnd.value,
            base_address: vBase.value || null,
            clear_base_address: !vBase.value,
            summary: vSummary.value || null,
            clear_summary: !vSummary.value,
          }),
        }).then(function (out) {
          log("Region updated", out);
          setStatus("good", "Region saved");
          return refreshCurrentTrip();
        });
      }, function () {
        return deleteRegion(region);
      });
      pane.appendChild(f);
    }

    function renderStopEditor(pane) {
      var loc = locateStop(st.selected.id);
      if (!loc) { st.selected = null; return renderEditor(); }
      var stop = loc.node, region = loc.region, parent = loc.parent;
      var f = el("div", "td-editor-form");
      var vName = edText(f, "Place name", stop.location_name || stop.title);
      var vType = edSelect(f, "Stop type",
        STOP_TYPES.map(function (t) { return { value: t, label: t }; }),
        stop.stop_type || "sight");
      var vStart = edDate(f, "Start date", stop.date_start);
      var vEnd = edDate(f, "End date", stop.date_end);
      var vNotes = edArea(f, "Story / notes", stop.notes);
      var _bStart = region.start_date || (st.trip && st.trip.start_date);
      var _bEnd = region.end_date || (st.trip && st.trip.end_date);
      var _bLabel = region.start_date ? "region" : "trip";
      attachDateWarning(f, vStart, vEnd, _bStart, _bEnd, _bLabel);

      var regionOpts = (st.tree.regions || []).map(function (r) {
        return { value: r.id, label: r.title || "Region" };
      });
      var vRegion = edSelect(f, "Region (move to)", regionOpts, region.id);

      var forbidden = {};
      subtreeIds(stop).forEach(function (id) { forbidden[id] = true; });
      var vParent = document.createElement("select");
      function fillParentOptions(regionId) {
        vParent.innerHTML = "";
        var top = document.createElement("option");
        top.value = ""; top.textContent = "No parent / top-level stop";
        vParent.appendChild(top);
        allStops(st.tree).forEach(function (s) {
          if (s.region_id !== regionId) return;
          if (forbidden[s.id]) return;
          var opt = document.createElement("option");
          opt.value = s.id;
          opt.textContent = new Array((s.depth || 0) + 1).join("— ") +
            (s.location_name || s.title || "Stop");
          vParent.appendChild(opt);
        });
        vParent.value = (regionId === region.id && parent) ? parent.id : "";
      }
      fillParentOptions(region.id);
      edField(f, "Parent stop (day trip under)", vParent);
      vRegion.addEventListener("change", function () {
        fillParentOptions(vRegion.value);
      });

      edActions(f, function () {
        var name = (vName.value || "").trim();
        if (!name) throw new Error("place name is required");
        var newRegion = vRegion.value;
        var newParent = vParent.value || null;
        var regionChanged = newRegion !== region.id;
        var parentChanged = newParent !== (parent ? parent.id : null);
        var patch = api("/api/trips/stops/" + encodeURIComponent(stop.id), {
          method: "PATCH",
          body: JSON.stringify({
            location_name: name,
            stop_type: vType.value || "sight",
            date_start: vStart.value || null,
            clear_start_date: !vStart.value,
            date_end: vEnd.value || null,
            clear_end_date: !vEnd.value,
            notes: vNotes.value || null,
            clear_notes: !vNotes.value,
          }),
        });
        return patch.then(function () {
          if (regionChanged || parentChanged) {
            return api("/api/trips/" + encodeURIComponent(st.trip.id) +
              "/stops/" + encodeURIComponent(stop.id) + "/move", {
              method: "POST",
              body: JSON.stringify({
                region_id: newRegion,
                parent_trip_stop_id: newParent,
                before_stop_id: null,
                after_stop_id: null,
              }),
            });
          }
        }).then(function () {
          log("Stop saved", { stop: name });
          setStatus("good", "Stop saved");
          return refreshCurrentTrip();
        });
      }, function () {
        return deleteStop(stop);
      });
      pane.appendChild(f);
    }

    // ── Reorder / move actions ──────────────────────────────────────────

    function moveRegionRelative(region, dir) {
      var ids = (st.tree.regions || []).map(function (r) { return r.id; });
      var i = ids.indexOf(region.id);
      var j = i + dir;
      if (i < 0 || j < 0 || j >= ids.length) return Promise.resolve();
      ids.splice(i, 1); ids.splice(j, 0, region.id);
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/regions/reorder", {
        method: "POST", body: JSON.stringify({ ordered_ids: ids }),
      }).then(function () { return refreshCurrentTrip(); });
    }

    function moveStopRelative(stop, region, parentStop, dir) {
      var siblings = parentStop ? (parentStop.children || []) : (region.stops || []);
      var ids = siblings.map(function (s) { return s.id; });
      var i = ids.indexOf(stop.id);
      var j = i + dir;
      if (i < 0 || j < 0 || j >= ids.length) return Promise.resolve();
      ids.splice(i, 1); ids.splice(j, 0, stop.id);
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/stops/reorder", {
        method: "POST",
        body: JSON.stringify({
          region_id: region.id,
          parent_trip_stop_id: parentStop ? parentStop.id : null,
          ordered_ids: ids,
        }),
      }).then(function () { return refreshCurrentTrip(); });
    }

    // ── Insert before/after + plain add (open the Add-stop modal) ───────

    function updateInsertHint() {
      var hint = $("insertHint");
      if (!hint) return;
      if (st.insertContext) {
        var loc = locateStop(st.insertContext.sibling_stop_id);
        var name = loc ? (loc.node.location_name || loc.node.title || "stop") : "stop";
        hint.className = "td-status-inline good";
        hint.textContent = "Inserting " + st.insertContext.where + " " + name;
      } else {
        hint.className = "td-status-inline";
        hint.textContent = "";
      }
    }

    function beginAddStop(regionId) {
      st.insertContext = null;
      var regionSel = $("stopRegion");
      if (regionSel) regionSel.value = regionId;
      rebuildParentOptions();
      var parentSel = $("stopParent");
      if (parentSel) parentSel.value = "";
      clearFields(["stopName", "stopStart", "stopEnd", "stopNotes"]);
      updateInsertHint();
      openModal("modalAddStop");
      var name = $("stopName");
      if (name) name.focus();
    }

    function beginInsertStop(regionId, parentStopId, siblingStopId, where) {
      st.insertContext = {
        region_id: regionId,
        parent_stop_id: parentStopId || null,
        sibling_stop_id: siblingStopId,
        where: where,
      };
      var regionSel = $("stopRegion");
      if (regionSel) regionSel.value = regionId;
      rebuildParentOptions();
      var parentSel = $("stopParent");
      if (parentSel) parentSel.value = parentStopId || "";
      clearFields(["stopName", "stopStart", "stopEnd", "stopNotes"]);
      updateInsertHint();
      openModal("modalAddStop");
      var name = $("stopName");
      if (name) name.focus();
    }

    function cancelInsert() {
      st.insertContext = null;
      updateInsertHint();
    }

    // ── CRUD actions ────────────────────────────────────────────────────

    function loadTrips() {
      syncInputs();
      if (!st.personId) return Promise.reject(new Error("person_id is required"));
      return api("/api/trips?person_id=" + encodeURIComponent(st.personId))
        .then(function (data) {
          st.trips = Array.isArray(data && data.trips) ? data.trips : [];
          renderTrips();
          setStatus("good", "Loaded " + st.trips.length + " trip" +
            (st.trips.length === 1 ? "" : "s"));
          // One trip and nothing open yet → open it so the operator lands
          // straight on the itinerary board (no "I have a trip but can't
          // do anything" dead end).
          if (!st.trip && st.trips.length === 1) return openTrip(st.trips[0]);
        });
    }

    function openTrip(trip) {
      var switching = !st.trip || st.trip.id !== trip.id;
      st.trip = trip;
      renderTrips();
      return Promise.all([
        api("/api/trips/" + encodeURIComponent(trip.id) + "/tree"),
        api("/api/trips/" + encodeURIComponent(trip.id) + "/photo-links")
          .catch(function () { return { photo_links: [] }; }),
        api("/api/trips/" + encodeURIComponent(trip.id) + "/location-notes")
          .catch(function () { return { notes: [] }; }),
        api("/api/trips/" + encodeURIComponent(trip.id) + "/sources")
          .catch(function () { return { sources: [] }; }),
      ]).then(function (out) {
        st.tree = out[0];
        st.photoLinks = Array.isArray(out[1] && out[1].photo_links)
          ? out[1].photo_links : [];
        st.locationNotes = Array.isArray(out[2] && out[2].notes)
          ? out[2].notes : [];
        st.sources = Array.isArray(out[3] && out[3].sources)
          ? out[3].sources : [];
        // Auto-select the trip so the right editor is never an empty
        // "select a tile" prompt (on first open / trip switch only —
        // a same-trip refresh preserves the current selection).
        if (switching || !st.selected) {
          st.selected = { kind: "trip", id: trip.id };
        }
        renderTree();
        updateInsertHint();
        log("Trip loaded", {
          trip: st.trip.title || st.trip.id,
          regions: (st.tree.regions || []).length,
          narrator_photo_links: st.photoLinks.length,
        });
      });
    }

    function createTrip() {
      syncInputs();
      if (!st.personId) return Promise.reject(new Error("person_id is required"));
      var title = val("tripTitle");
      if (!title) return Promise.reject(new Error("trip title is required"));
      var body = {
        person_id: st.personId,
        title: title,
        start_date: val("tripStart") || null,
        end_date: val("tripEnd") || null,
        summary: val("tripSummary") || null,
      };
      return api("/api/trips", { method: "POST", body: JSON.stringify(body) })
        .then(function (out) {
          log("Trip created", out);
          clearFields(["tripTitle", "tripStart", "tripEnd", "tripSummary"]);
          return loadTrips().then(function () {
            var created = st.trips.filter(function (t) {
              return t.id === out.trip_id;
            })[0];
            if (created) return openTrip(created);
          });
        });
    }

    function createRegion() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var title = val("regionName");
      if (!title) return Promise.reject(new Error("region title is required"));
      var body = {
        title: title,
        country_or_area: val("regionArea") || null,
        start_date: val("regionStart") || null,
        end_date: val("regionEnd") || null,
        base_address: val("regionBase") || null,
        summary: val("regionSummary") || null,
      };
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/regions",
        { method: "POST", body: JSON.stringify(body) })
        .then(function (out) {
          log("Region added", out);
          clearFields(["regionName", "regionArea", "regionStart", "regionEnd", "regionBase", "regionSummary"]);
          return refreshCurrentTrip();
        });
    }

    function createStop() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var regionId = val("stopRegion");
      if (!regionId) return Promise.reject(new Error("select a region"));
      var name = val("stopName");
      if (!name) return Promise.reject(new Error("place name is required"));
      var ctx = st.insertContext;
      var body = {
        location_name: name,
        stop_type: val("stopType") || "sight",
        parent_trip_stop_id: val("stopParent") || null,
        date_start: val("stopStart") || null,
        date_end: val("stopEnd") || null,
        notes: val("stopNotes") || null,
      };
      return api("/api/trips/" + encodeURIComponent(st.trip.id) +
        "/regions/" + encodeURIComponent(regionId) + "/stops",
        { method: "POST", body: JSON.stringify(body) })
        .then(function (out) {
          log("Stop added", out);
          clearFields(["stopName", "stopStart", "stopEnd", "stopNotes"]);
          // Backend appends at end; if inserting relative to a sibling,
          // position it now via the move endpoint.
          if (ctx && out && out.stop_id) {
            st.insertContext = null;
            updateInsertHint();
            return api("/api/trips/" + encodeURIComponent(st.trip.id) +
              "/stops/" + encodeURIComponent(out.stop_id) + "/move", {
              method: "POST",
              body: JSON.stringify({
                region_id: ctx.region_id,
                parent_trip_stop_id: ctx.parent_stop_id,
                before_stop_id: ctx.where === "before" ? ctx.sibling_stop_id : null,
                after_stop_id: ctx.where === "after" ? ctx.sibling_stop_id : null,
              }),
            });
          }
        })
        .then(function () { return refreshCurrentTrip(); });
    }

    function deleteTrip(trip) {
      if (!window.confirm("Delete this trip? This removes the trip outline, " +
        "its regions, stops, themes, and travel memoir draft. Photos " +
        "themselves are not deleted.")) return Promise.resolve();
      return api("/api/trips/" + encodeURIComponent(trip.id), { method: "DELETE" })
        .then(function (out) {
          log("Trip deleted", out);
          setStatus("good", "Trip deleted");
          st.trip = null; st.tree = null; st.selected = null;
          return loadTrips().then(function () { renderTree(); });
        });
    }

    function deleteRegion(region) {
      if (!window.confirm("Delete the region \"" + (region.title || "Region") +
        "\"? Every stop inside this region is deleted with it.")) {
        return Promise.resolve();
      }
      return api("/api/trips/regions/" + encodeURIComponent(region.id),
        { method: "DELETE" })
        .then(function (out) {
          log("Region deleted", out);
          setStatus("good", "Region deleted");
          if (st.selected && st.selected.kind === "region" &&
              st.selected.id === region.id) st.selected = null;
          return refreshCurrentTrip();
        });
    }

    function deleteStop(stop) {
      var hasChildren = (stop.children || []).length > 0;
      var msg = hasChildren
        ? "Delete the stop \"" + (stop.location_name || stop.title || "Stop") +
          "\"? Its day-trip / child stops are NOT deleted — they move up to " +
          "become top-level stops in this region."
        : "Delete the stop \"" + (stop.location_name || stop.title || "Stop") + "\"?";
      if (!window.confirm(msg)) return Promise.resolve();
      return api("/api/trips/stops/" + encodeURIComponent(stop.id),
        { method: "DELETE" })
        .then(function (out) {
          log("Stop deleted", out);
          setStatus("good", "Stop deleted");
          if (st.selected && st.selected.kind === "stop" &&
              st.selected.id === stop.id) st.selected = null;
          return refreshCurrentTrip();
        });
    }

    function uploadPhotosToStop(stopId, fileInput) {
      var files = Array.prototype.slice.call((fileInput && fileInput.files) || []);
      if (!files.length) return Promise.reject(new Error("choose at least one photo"));
      var fd = new FormData();
      files.forEach(function (f) { fd.append("files", f); });
      fd.append("uploaded_by_user_id", "travel_documenter");
      fd.append("narrator_ready", "true");
      fd.append("uploaded_from_surface", "travel_documenter");
      return api("/api/trips/stops/" + encodeURIComponent(stopId) + "/photos",
        { method: "POST", body: fd })
        .then(function (out) {
          log("Photos uploaded to stop", out);
          setStatus("good", "Photos added to this stop");
          return refreshCurrentTrip();
        });
    }

    function uploadPhotos() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var files = Array.prototype.slice.call($("photoFiles").files || []);
      if (!files.length) return Promise.reject(new Error("choose at least one photo"));
      var fd = new FormData();
      files.forEach(function (f) { fd.append("files", f); });
      fd.append("uploaded_by_user_id", "travel_documenter");
      fd.append("narrator_ready", "true");
      fd.append("uploaded_from_surface", "travel_documenter");
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/photos",
        { method: "POST", body: fd })
        .then(function (out) {
          $("photoFiles").value = "";
          log("Photos uploaded", out);
          return refreshCurrentTrip();
        });
    }

    function clusterPhotos() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var body = { narrator_id: st.personId || null };
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/cluster-photos",
        { method: "POST", body: JSON.stringify(body) })
        .then(function (out) {
          log("Cluster photos result", out);
          return refreshCurrentTrip();
        });
    }

    function memoirPreview() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/memoir-preview")
        .then(function (out) { log("Memoir preview", out); expandOutput(); });
    }

    function ping() {
      syncInputs();
      var check = st.personId
        ? api("/api/trips?person_id=" + encodeURIComponent(st.personId))
        : fetch(st.apiBase + "/api/trips").catch(function () { return null; });
      return Promise.resolve(check).then(function () {
        setStatus("good", "API reachable");
        log("API reachable. If trips return 404, set HORNELORE_TRIPS=1 and restart.");
      }).catch(function (e) {
        logError("API check failed", { error: e.message });
      });
    }

    function bind(name, fn) {
      var el2 = $(name);
      if (!el2) return;
      el2.addEventListener("click", function () {
        Promise.resolve().then(fn).catch(function (e) {
          logError("Error", { message: e.message });
        });
      });
    }

    // Setup / list
    bind("loadTrips", loadTrips);
    bind("refreshTrips", loadTrips);
    bind("ping", ping);
    bind("focusToggle", toggleFocus);

    // Create trip (modal)
    bind("openCreateTrip", function () {
      clearFields(["tripTitle", "tripStart", "tripEnd", "tripSummary"]);
      openModal("modalCreateTrip");
      var t = $("tripTitle"); if (t) t.focus();
    });
    bind("createTrip", function () {
      return createTrip().then(function () { closeModal("modalCreateTrip"); });
    });
    bind("closeCreateTrip", function () { closeModal("modalCreateTrip"); });
    bind("cancelCreateTrip", function () { closeModal("modalCreateTrip"); });

    // Selected-trip toolbar
    bind("editTrip", function () {
      if (!st.trip) throw new Error("select a trip first");
      selectItem("trip", st.trip.id);
    });
    bind("reloadTree", function () { if (st.trip) return openTrip(st.trip); });
    bind("memoirPreview", memoirPreview);
    bind("editorClear", clearSelection);
    bind("viewEditor", function () { st.rightView = "editor"; applyRightView(); });
    bind("viewTimeline", function () { st.rightView = "timeline"; applyRightView(); });
    // Explicit, narrator-visible: hand the selected trip to the narrator
    // Travels shelf (which owns all Lori/session state). Travel Doc never
    // dispatches prompts or writes session scope itself.
    bind("talkLori", function () {
      if (!st.trip) throw new Error("select a trip first");
      if (typeof window.lvTravelsOpenTripById === "function") {
        window.lvTravelsOpenTripById(st.trip.id);
        setStatus("good", "Lori is now focused on this trip — opening the Travels shelf.");
      } else {
        throw new Error("the Travels shelf isn't available here");
      }
    });

    // Add region (modal)
    bind("addRegionBtn", function () {
      if (!st.trip) throw new Error("select a trip first");
      clearFields(["regionName", "regionArea", "regionStart", "regionEnd", "regionBase", "regionSummary"]);
      openModal("modalAddRegion");
      var n = $("regionName"); if (n) n.focus();
    });
    bind("createRegion", function () {
      return createRegion().then(function () { closeModal("modalAddRegion"); });
    });
    bind("closeAddRegion", function () { closeModal("modalAddRegion"); });
    bind("cancelAddRegion", function () { closeModal("modalAddRegion"); });

    // Add stop (modal — opened here or from tile +Stop/+Before/+After)
    bind("addStopBtn", function () {
      if (!st.trip) throw new Error("select a trip first");
      var regions = (st.tree && st.tree.regions) || [];
      if (!regions.length) throw new Error("add a region first");
      var rid = null;
      if (st.selected && st.selected.kind === "region") {
        rid = st.selected.id;
      } else if (st.selected && st.selected.kind === "stop") {
        var loc = locateStop(st.selected.id);
        if (loc) rid = loc.region.id;
      }
      beginAddStop(rid || regions[0].id);
    });
    bind("createStop", function () {
      return createStop().then(function () { closeModal("modalAddStop"); });
    });
    bind("closeAddStop", function () { cancelInsert(); closeModal("modalAddStop"); });
    bind("cancelAddStop", function () { cancelInsert(); closeModal("modalAddStop"); });

    // Photos + output (collapsibles)
    bind("uploadPhotos", uploadPhotos);
    bind("clusterPhotos", clusterPhotos);
    bind("togglePhotos", function () { toggleHidden("photosBody", "togglePhotos", "Trip photos"); });
    bind("toggleOutput", function () { toggleHidden("output", "toggleOutput", "Output"); });
    var clearBtn = $("clearOutput");
    if (clearBtn) clearBtn.addEventListener("click", function () { log("Ready."); });

    // If the operator changes the target Region or Parent while an
    // insert-before/after is staged, the original sibling no longer
    // applies — drop the insert context so the stop is a plain add in the
    // new location (rather than silently honoring the stale sibling).
    var regionSelEl = $("stopRegion");
    if (regionSelEl) regionSelEl.addEventListener("change", function () {
      if (st.insertContext) { st.insertContext = null; updateInsertHint(); }
      rebuildParentOptions();
    });
    var parentSelEl = $("stopParent");
    if (parentSelEl) parentSelEl.addEventListener("change", function () {
      if (st.insertContext) { st.insertContext = null; updateInsertHint(); }
    });

    // Backdrop click closes modals.
    ["modalCreateTrip", "modalAddRegion", "modalAddStop"].forEach(function (mn) {
      var ov = $(mn);
      if (!ov) return;
      ov.addEventListener("click", function (e) {
        if (e.target === ov) {
          if (mn === "modalAddStop") cancelInsert();
          closeModal(mn);
        }
      });
    });

    // Escape closes whichever modal is open (add-stop also clears insert
    // context). Listener is removed on destroy to avoid leaks across mounts.
    function onKeydown(e) {
      if (e.key !== "Escape" && e.key !== "Esc") return;
      ["modalCreateTrip", "modalAddRegion", "modalAddStop"].forEach(function (mn) {
        var m = $(mn);
        if (m && !m.hidden) {
          if (mn === "modalAddStop") cancelInsert();
          closeModal(mn);
        }
      });
    }
    document.addEventListener("keydown", onKeydown);

    renderTree();
    setStatus("", "");
    if (st.personId && !opts.standalone) {
      loadTrips().catch(function (e) {
        logError("Could not load trips", { message: e.message });
      });
    }

    return {
      person_id: st.personId,
      reload: loadTrips,
      destroy: function () {
        document.removeEventListener("keydown", onKeydown);
        document.body.classList.remove("lv-td-focus");
        hostEl.innerHTML = "";
        hostEl.classList.remove("td-root");
      },
    };
  };
})();
