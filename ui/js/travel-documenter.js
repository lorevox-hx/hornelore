/* ═══════════════════════════════════════════════════════════════
   travel-documenter.js — WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01
                        + WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01

   OPERATOR-ONLY trip documentation panel, mountable:

     window.lvTravelDocumenterMount(hostEl, {
       person_id,      // required in native mode
       person_label,   // optional display name
       apiBase,        // optional; falls back to LOREVOX_API
       standalone,     // true = show connection inputs (demo page)
     })

   Consumed two ways:
     1. NATIVE: the main app mounts it into the "Travel Doc" shell
        tab with the currently selected narrator (no pasted ids).
     2. STANDALONE: ui/travel-documenter.html is a thin wrapper that
        mounts with {standalone:true} and its own inputs.

   HARD BOUNDARIES (spec + regression-tested):
     - Operator tool ONLY. The shell tab strip is hidden during
       interview mode (body.lv-interview-mode-active #lvShellTabs),
       so this panel is unreachable by narrators.
     - NEVER touches Lori/Travels state: nothing here writes the
       trip-session scope the narrator shelf owns, nothing consumed
       by the chat runtime, and no system-prompt dispatch of any kind.
     - Uses existing trips endpoints only. Photo uploads land at
       trip level (trip_upload method — unplaced, cluster-placeable)
       and are narrator-ready immediately: the operator IS the
       reviewer on this surface, unlike travels_shelf uploads which
       get needs_operator_review stamped server-side.

   EDITABLE ITINERARY (WO-TRAVEL-DOC-EDITABLE-ITINERARY-TILES-01):
     Operator tile order is the route authority (dates are metadata).
     The selected-trip tree is a DOM tile board: each region/stop tile
     carries Edit / Delete / Move up-down / Add before-after; the right
     editor panel edits the selected trip/region/stop. Reorder + move
     persist via the backend `ord` column so a reload — and the memoir
     preview — reflect the same order. Delete semantics (server-side):
     deleting a region CASCADES its stops; deleting a parent stop
     PROMOTES its children to top level (parent set null).
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
    var connection = opts.standalone
      ? '<section class="td-panel td-setup-panel">' +
        '<h2>Connection</h2>' +
        '<label>API base<input data-td="apiBase" type="text" spellcheck="false" value="' + esc(opts.apiBase || "http://localhost:8000") + '" /></label>' +
        '<label>Narrator / person_id<input data-td="personId" type="text" spellcheck="false" value="' + esc(opts.person_id || "") + '" placeholder="paste person_id or use ?person_id=..." /></label>' +
        '<div class="td-button-row"><button data-td="loadTrips" type="button">Load trips</button><button data-td="ping" type="button" class="td-secondary">Check API</button></div>' +
        '<p class="td-help">Requires <code>HORNELORE_TRIPS=1</code>.</p>' +
        '</section>'
      : '<section class="td-panel td-setup-panel">' +
        '<h2>Narrator</h2>' +
        '<p class="td-narrator-line">Documenting trips for <strong>' +
        esc(opts.person_label || opts.person_id || "—") + '</strong></p>' +
        '<div class="td-button-row"><button data-td="loadTrips" type="button">Reload trips</button></div>' +
        '</section>';

    var stopTypeOptions = STOP_TYPES.map(function (t) {
      return '<option value="' + t + '"' + (t === "sight" ? " selected" : "") + '>' + t + "</option>";
    }).join("");

    return '<div class="td-layout">' + connection +
      '<section class="td-panel">' +
      '<h2>Create trip</h2>' +
      '<div class="td-grid-2">' +
      '<label>Title<input data-td="tripTitle" type="text" placeholder="Spring 2026 Europe" /></label>' +
      '<label>Start date<input data-td="tripStart" type="date" /></label>' +
      '<label>End date<input data-td="tripEnd" type="date" /></label>' +
      '</div>' +
      '<label>Summary<textarea data-td="tripSummary" rows="3" placeholder="Short summary of the trip."></textarea></label>' +
      '<button data-td="createTrip" type="button">Create trip</button>' +
      '</section>' +
      '<section class="td-panel td-trip-list-panel">' +
      '<div class="td-panel-head"><h2>Trips</h2><button data-td="refreshTrips" type="button" class="td-small td-secondary">Refresh</button></div>' +
      '<div data-td="tripList" class="td-trip-list td-empty">Load a narrator’s trips.</div>' +
      '</section>' +
      '<section class="td-panel td-active-panel">' +
      '<div class="td-panel-head">' +
      '<div><p class="td-kicker">Selected trip</p><h2 data-td="activeTripTitle">None selected</h2></div>' +
      '<div class="td-button-row"><button data-td="editTrip" type="button" class="td-small td-secondary">Edit trip</button><button data-td="reloadTree" type="button" class="td-small td-secondary">Reload</button><button data-td="memoirPreview" type="button" class="td-small">Memoir preview</button></div>' +
      '</div>' +
      '<div data-td="tripMeta" class="td-muted">Choose a trip to document.</div>' +
      '<p class="td-help">Tile order is the route order. Use the tile buttons to reorder, insert, or restructure — dates are just metadata.</p>' +
      '<div data-td="tree" class="td-tree"></div>' +
      '</section>' +
      '<section class="td-panel td-editor-panel" data-td="editorPanel">' +
      '<div class="td-panel-head"><h2 data-td="editorTitle">Edit selected</h2><button data-td="editorClear" type="button" class="td-small td-secondary">Clear</button></div>' +
      '<div data-td="editorBody" class="td-editor-body"><p class="td-muted">Select a trip, region, or stop tile to edit it.</p></div>' +
      '</section>' +
      '<section class="td-panel">' +
      '<h2>Add region</h2>' +
      '<div class="td-grid-2">' +
      '<label>Region title<input data-td="regionName" type="text" placeholder="Germany / Bavaria" /></label>' +
      '<label>Country or area<input data-td="regionArea" type="text" placeholder="Germany" /></label>' +
      '<label>Start date<input data-td="regionStart" type="date" /></label>' +
      '<label>End date<input data-td="regionEnd" type="date" /></label>' +
      '</div>' +
      '<label>Base address / lodging<input data-td="regionBase" type="text" placeholder="Hotel, rental, city base" /></label>' +
      '<button data-td="createRegion" type="button">Add region</button>' +
      '</section>' +
      '<section class="td-panel">' +
      '<div class="td-panel-head"><h2>Add stop</h2><span data-td="insertHint" class="td-status-inline"></span></div>' +
      '<div class="td-grid-2">' +
      '<label>Region<select data-td="stopRegion"></select></label>' +
      '<label>Parent stop / day trip under<select data-td="stopParent"></select></label>' +
      '<label>Place name<input data-td="stopName" type="text" placeholder="Munich" /></label>' +
      '<label>Stop type<select data-td="stopType">' + stopTypeOptions + '</select></label>' +
      '<label>Start date<input data-td="stopStart" type="date" /></label>' +
      '<label>End date<input data-td="stopEnd" type="date" /></label>' +
      '</div>' +
      '<label>Notes<textarea data-td="stopNotes" rows="3" placeholder="Route details, lodging, meals, people, memories."></textarea></label>' +
      '<div class="td-button-row"><button data-td="createStop" type="button">Add stop</button><button data-td="cancelInsert" type="button" class="td-small td-secondary" hidden>Cancel insert</button></div>' +
      '</section>' +
      '<section class="td-panel">' +
      '<h2>Trip photos</h2>' +
      '<p class="td-help">Uploads are trusted operator additions: narrator-ready immediately, unplaced at trip level — run Cluster photos to place them at stops.</p>' +
      '<label>Add photos to selected trip<input data-td="photoFiles" type="file" accept="image/*,.heic,.heif" multiple /></label>' +
      '<div class="td-button-row"><button data-td="uploadPhotos" type="button">Upload photos</button><button data-td="clusterPhotos" type="button" class="td-secondary">Cluster photos</button></div>' +
      '<div data-td="photoStrip" class="td-photo-strip td-empty">No trip selected.</div>' +
      '</section>' +
      '<section class="td-panel td-wide">' +
      '<div class="td-panel-head"><h2>Output</h2><span data-td="statusLine" class="td-status-inline"></span><button data-td="clearOutput" type="button" class="td-small td-secondary">Clear</button></div>' +
      '<pre data-td="output" class="td-output">Ready.</pre>' +
      '</section>' +
      '</div>';
  }

  window.lvTravelDocumenterMount = function (hostEl, opts) {
    opts = opts || {};
    var st = {
      apiBase: (opts.apiBase || window.LOREVOX_API || "http://localhost:8000")
        .replace(/\/$/, ""),
      personId: opts.person_id || "",
      trips: [], trip: null, tree: null, photoLinks: [],
      // { kind: "trip"|"region"|"stop", id }
      selected: null,
      // { region_id, parent_stop_id, sibling_stop_id, where: "before"|"after" }
      insertContext: null,
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
      if (!el2) return;
      el2.className = "td-status-inline" + (kind ? " " + kind : "");
      el2.textContent = text || "";
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

    // Live tree node (with children) + its region + parent node.
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

    function selectItem(kind, id) {
      st.selected = kind && id ? { kind: kind, id: id } : null;
      renderTree();
    }

    function clearSelection() {
      st.selected = null;
      renderTree();
    }

    // Reload trips + re-open the current trip by id, preserving selection.
    function refreshCurrentTrip() {
      if (!st.trip) return Promise.resolve();
      var tid = st.trip.id;
      return loadTrips().then(function () {
        var t = st.trips.filter(function (x) { return x.id === tid; })[0];
        if (t) return openTrip(t);
        // Trip was deleted out from under us.
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
      if (!st.trip) {
        host.className = "td-photo-strip td-empty";
        host.textContent = "No trip selected.";
        return;
      }
      var links = st.photoLinks || [];
      if (!links.length) {
        host.className = "td-photo-strip td-empty";
        host.textContent = "No narrator-ready linked photos yet.";
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
          setStatus("bad", "Error");
          log("Error", { message: err.message });
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
          .filter(Boolean).join(" · ")) + '</small>';
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
          region.country_or_area || "") + '</small>';
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
        regionSel.innerHTML = "<option value=''>Select a trip first</option>";
        parentSel.innerHTML = "<option value=''>No parent</option>";
        renderPhotos();
        renderEditor();
        return;
      }

      title.textContent = st.trip.title || "Untitled trip";
      meta.textContent = dateSpan(st.trip.start_date, st.trip.end_date) || st.trip.id;

      var regions = st.tree.regions || [];
      regionSel.innerHTML = regions.length ? "" : "<option value=''>Add a region first</option>";
      regions.forEach(function (r) {
        var opt = document.createElement("option");
        opt.value = r.id;
        opt.textContent = r.title || "Region";
        regionSel.appendChild(opt);
      });

      // Backend rejects parents from another region, so only offer parents
      // from the SELECTED region. Rebuilds on region change too.
      rebuildParentOptions();

      treeHost.innerHTML = "";
      if (!regions.length) {
        treeHost.appendChild(el("p", "td-empty", "No regions yet. Add the first region."));
      } else {
        regions.forEach(function (r) { treeHost.appendChild(renderRegionTile(r)); });
      }
      renderPhotos();
      renderEditor();
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
      // options: [{value,label}]
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
          setStatus("bad", "Error"); log("Error", { message: e.message });
        });
      });
      row.appendChild(save);
      if (deleteFn) {
        var del = el("button", "td-danger", "Delete"); del.type = "button";
        del.addEventListener("click", function () {
          Promise.resolve().then(deleteFn).catch(function (e) {
            setStatus("bad", "Error"); log("Error", { message: e.message });
          });
        });
        row.appendChild(del);
      }
      parent.appendChild(row);
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
      if (st.selected.kind === "trip") return renderTripEditor(title, body);
      if (st.selected.kind === "region") return renderRegionEditor(title, body);
      if (st.selected.kind === "stop") return renderStopEditor(title, body);
    }

    function renderTripEditor(title, body) {
      var trip = st.trip;
      title.textContent = "Edit trip";
      body.innerHTML = "";
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
      body.appendChild(f);
    }

    function renderRegionEditor(title, body) {
      var region = findRegion(st.selected.id);
      if (!region) { st.selected = null; return renderEditor(); }
      title.textContent = "Edit region";
      body.innerHTML = "";
      var f = el("div", "td-editor-form");
      var vTitle = edText(f, "Region title", region.title);
      var vArea = edText(f, "Country or area", region.country_or_area);
      var vStart = edDate(f, "Start date", region.start_date);
      var vEnd = edDate(f, "End date", region.end_date);
      var vBase = edText(f, "Base address / lodging", region.base_address);
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
          }),
        }).then(function (out) {
          log("Region updated", out);
          setStatus("good", "Region saved");
          return refreshCurrentTrip();
        });
      }, function () {
        return deleteRegion(region);
      });
      body.appendChild(f);
    }

    function renderStopEditor(title, body) {
      var loc = locateStop(st.selected.id);
      if (!loc) { st.selected = null; return renderEditor(); }
      var stop = loc.node, region = loc.region, parent = loc.parent;
      title.textContent = "Edit stop";
      body.innerHTML = "";
      var f = el("div", "td-editor-form");
      var vName = edText(f, "Place name", stop.location_name || stop.title);
      var vType = edSelect(f, "Stop type",
        STOP_TYPES.map(function (t) { return { value: t, label: t }; }),
        stop.stop_type || "sight");
      var vStart = edDate(f, "Start date", stop.date_start);
      var vEnd = edDate(f, "End date", stop.date_end);
      var vNotes = edArea(f, "Notes", stop.notes);

      // Move controls: region + parent. Changing either issues a move so
      // ord is renumbered cleanly. Parent options exclude this stop's own
      // subtree (backend also rejects cycles).
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
      body.appendChild(f);
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

    // ── Insert before/after + plain add ─────────────────────────────────

    function updateInsertHint() {
      var hint = $("insertHint");
      var cancel = $("cancelInsert");
      if (!hint) return;
      if (st.insertContext) {
        var loc = locateStop(st.insertContext.sibling_stop_id);
        var name = loc ? (loc.node.location_name || loc.node.title || "stop") : "stop";
        hint.className = "td-status-inline good";
        hint.textContent = "Inserting " + st.insertContext.where + " " + name;
        if (cancel) cancel.hidden = false;
      } else {
        hint.className = "td-status-inline";
        hint.textContent = "";
        if (cancel) cancel.hidden = true;
      }
    }

    function beginAddStop(regionId) {
      st.insertContext = null;
      var regionSel = $("stopRegion");
      if (regionSel) regionSel.value = regionId;
      rebuildParentOptions();
      var parentSel = $("stopParent");
      if (parentSel) parentSel.value = "";
      var name = $("stopName");
      if (name) { name.value = ""; name.focus(); }
      updateInsertHint();
      setStatus("", "Adding a stop to the selected region");
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
      var name = $("stopName");
      if (name) { name.value = ""; name.focus(); }
      updateInsertHint();
      setStatus("", "Adding stop " + where + " the selected stop");
    }

    function cancelInsert() {
      st.insertContext = null;
      updateInsertHint();
      setStatus("", "");
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
        });
    }

    function openTrip(trip) {
      st.trip = trip;
      renderTrips();
      return Promise.all([
        api("/api/trips/" + encodeURIComponent(trip.id) + "/tree"),
        api("/api/trips/" + encodeURIComponent(trip.id) + "/narrator-photo-links")
          .catch(function () { return { photo_links: [] }; }),
      ]).then(function (out) {
        st.tree = out[0];
        st.photoLinks = Array.isArray(out[1] && out[1].photo_links)
          ? out[1].photo_links : [];
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
      };
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/regions",
        { method: "POST", body: JSON.stringify(body) })
        .then(function (out) {
          log("Region added", out);
          ["regionName", "regionArea", "regionBase"].forEach(function (n) {
            var e2 = $(n); if (e2) e2.value = "";
          });
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
          $("stopName").value = "";
          $("stopNotes").value = "";
          // Backend appends at end; if we were inserting relative to a
          // sibling, position it now via the move endpoint (fallback path).
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
        .then(function (out) { log("Memoir preview", out); });
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
        setStatus("bad", "API issue");
        log("API check failed", { error: e.message });
      });
    }

    function bind(name, fn) {
      var el2 = $(name);
      if (!el2) return;
      el2.addEventListener("click", function () {
        Promise.resolve().then(fn).catch(function (e) {
          setStatus("bad", "Error");
          log("Error", { message: e.message });
        });
      });
    }

    bind("loadTrips", loadTrips);
    bind("refreshTrips", loadTrips);
    bind("createTrip", createTrip);
    bind("editTrip", function () { if (st.trip) selectItem("trip", st.trip.id); });
    bind("reloadTree", function () { if (st.trip) return openTrip(st.trip); });
    bind("createRegion", createRegion);
    bind("createStop", createStop);
    bind("cancelInsert", cancelInsert);
    bind("uploadPhotos", uploadPhotos);
    bind("clusterPhotos", clusterPhotos);
    bind("memoirPreview", memoirPreview);
    bind("editorClear", clearSelection);
    bind("ping", ping);
    var clearBtn = $("clearOutput");
    if (clearBtn) clearBtn.addEventListener("click", function () { log("Ready."); });
    var regionSelEl = $("stopRegion");
    if (regionSelEl) regionSelEl.addEventListener("change", rebuildParentOptions);

    renderTree();
    setStatus("", "");
    // Native mode: the narrator is already known — load immediately.
    if (st.personId && !opts.standalone) {
      loadTrips().catch(function (e) {
        setStatus("bad", "Error");
        log("Could not load trips", { message: e.message });
      });
    }

    return {
      person_id: st.personId,
      reload: loadTrips,
      destroy: function () {
        hostEl.innerHTML = "";
        hostEl.classList.remove("td-root");
      },
    };
  };
})();
