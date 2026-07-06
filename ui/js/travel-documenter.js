/* ═══════════════════════════════════════════════════════════════
   travel-documenter.js — WO-TRAVEL-DOCUMENTER-NATIVE-PANEL-01

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
      '<div class="td-button-row"><button data-td="reloadTree" type="button" class="td-small td-secondary">Reload</button><button data-td="memoirPreview" type="button" class="td-small">Memoir preview</button></div>' +
      '</div>' +
      '<div data-td="tripMeta" class="td-muted">Choose a trip to document.</div>' +
      '<div data-td="tree" class="td-tree"></div>' +
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
      '<h2>Add stop</h2>' +
      '<div class="td-grid-2">' +
      '<label>Region<select data-td="stopRegion"></select></label>' +
      '<label>Parent stop / day trip under<select data-td="stopParent"></select></label>' +
      '<label>Place name<input data-td="stopName" type="text" placeholder="Munich" /></label>' +
      '<label>Stop type<select data-td="stopType">' + stopTypeOptions + '</select></label>' +
      '<label>Start date<input data-td="stopStart" type="date" /></label>' +
      '<label>End date<input data-td="stopEnd" type="date" /></label>' +
      '</div>' +
      '<label>Notes<textarea data-td="stopNotes" rows="3" placeholder="Route details, lodging, meals, people, memories."></textarea></label>' +
      '<button data-td="createStop" type="button">Add stop</button>' +
      '</section>' +
      '<section class="td-panel">' +
      '<h2>Trip photos</h2>' +
      '<p class="td-help">Uploads are trusted operator additions: narrator-ready immediately, unplaced at trip level \u2014 run Cluster photos to place them at stops.</p>' +
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
    };

    hostEl.classList.add("td-root");
    hostEl.innerHTML = template(opts);

    function $(name) { return hostEl.querySelector('[data-td="' + name + '"]'); }
    function val(name) {
      var el = $(name);
      return (el && el.value || "").trim();
    }

    function log(msg, obj) {
      var out = $("output");
      if (!out) return;
      var line = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
      out.textContent = line +
        (obj === undefined ? "" : "\n" + JSON.stringify(obj, null, 2));
    }

    function setStatus(kind, text) {
      var el = $("statusLine");
      if (!el) return;
      el.className = "td-status-inline" + (kind ? " " + kind : "");
      el.textContent = text || "";
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

    function dateSpan(a, b) { return [a, b].filter(Boolean).join(" to "); }

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

    function stopHtml(s, depth) {
      var children = (s.children || []).map(function (c) {
        return stopHtml(c, depth + 1);
      }).join("");
      return '<div class="td-stop" style="margin-left:' + (depth * 18) +
        'px"><strong>' + esc(s.title || s.location_name || "Stop") +
        "</strong><small>" +
        esc([s.stop_type, dateSpan(s.date_start, s.date_end), s.notes]
          .filter(Boolean).join(" · ")) + "</small></div>" + children;
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
        opt.textContent = new Array((s.depth || 0) + 1).join("\u2014 ") +
          (s.location_name || s.title || "Stop") +
          " (" + (s.region_title || "region") + ")";
        parentSel.appendChild(opt);
      });
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

      // Review fix: the backend rejects parents from another region,
      // so only offer parents from the SELECTED region. Rebuilds on
      // region change too (listener wired once below).
      rebuildParentOptions();

      if (!regions.length) {
        treeHost.innerHTML = '<p class="td-empty">No regions yet. Add the first region.</p>';
        renderPhotos();
        return;
      }
      treeHost.innerHTML = regions.map(function (r) {
        var stops = (r.stops || []).map(function (s) {
          return stopHtml(s, 0);
        }).join("") || '<div class="td-muted">No stops yet.</div>';
        return '<div class="td-region"><div class="td-region-title">' +
          esc(r.title || "Region") + '</div><div class="td-muted">' +
          esc(dateSpan(r.start_date, r.end_date) || r.country_or_area || "") +
          "</div>" + stops + "</div>";
      }).join("");
      renderPhotos();
    }

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
          return openTrip(st.trip);
        });
    }

    function createStop() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var regionId = val("stopRegion");
      if (!regionId) return Promise.reject(new Error("select a region"));
      var name = val("stopName");
      if (!name) return Promise.reject(new Error("place name is required"));
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
          return openTrip(st.trip);
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
          return openTrip(st.trip);
        });
    }

    function clusterPhotos() {
      if (!st.trip) return Promise.reject(new Error("select a trip first"));
      var body = { narrator_id: st.personId || null };
      return api("/api/trips/" + encodeURIComponent(st.trip.id) + "/cluster-photos",
        { method: "POST", body: JSON.stringify(body) })
        .then(function (out) {
          log("Cluster photos result", out);
          return openTrip(st.trip);
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
      var el = $(name);
      if (!el) return;
      el.addEventListener("click", function () {
        Promise.resolve().then(fn).catch(function (e) {
          setStatus("bad", "Error");
          log("Error", { message: e.message });
        });
      });
    }

    bind("loadTrips", loadTrips);
    bind("refreshTrips", loadTrips);
    bind("createTrip", createTrip);
    bind("reloadTree", function () { if (st.trip) return openTrip(st.trip); });
    bind("createRegion", createRegion);
    bind("createStop", createStop);
    bind("uploadPhotos", uploadPhotos);
    bind("clusterPhotos", clusterPhotos);
    bind("memoirPreview", memoirPreview);
    bind("ping", ping);
    var clearBtn = $("clearOutput");
    if (clearBtn) clearBtn.addEventListener("click", function () { log("Ready."); });
    var regionSelEl = $("stopRegion");
    if (regionSelEl) {
      regionSelEl.addEventListener("change", rebuildParentOptions);
    }

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
