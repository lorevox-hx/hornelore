/* Trip Tab operator console — WO-TRIP-IMPORT-AND-CLUSTER-01 Phase 3.
 *
 * Standalone operator page (mirrors photo-intake.js conventions):
 * ORIGIN override via window.LOREVOX_API, narrator picker persisted in
 * localStorage, plain fetch + DOM, no framework.
 *
 * Everything here talks to the HORNELORE_TRIPS-gated /api/trips/*
 * surface. When the gate is off the API returns 404 on every call and
 * the banner explains the flag — mirrors the Bug Panel eval-harness
 * "feature disabled" posture.
 */
(function () {
  "use strict";

  var ORIGIN = window.LOREVOX_API || "http://localhost:8000";
  var LS_NARRATOR = "trip_tab_narrator_id_v1";
  var LS_TRIP = "trip_tab_trip_id_v1";

  // Active-narrator handoff from the main shell (2026-07-06): the
  // launch card passes ?narrator_id=<active narrator>, which WINS over
  // the locally-remembered picker value. The picker remains for the
  // direct-URL / no-active-narrator case.
  var _urlNarrator = "";
  try {
    _urlNarrator = new URLSearchParams(window.location.search)
      .get("narrator_id") || "";
  } catch (e) { _urlNarrator = ""; }

  var state = {
    narratorId: _urlNarrator || localStorage.getItem(LS_NARRATOR) || "",
    tripId: localStorage.getItem(LS_TRIP) || "",
    tree: null,
    flatStops: [],
    gateOff: false,
  };

  // ── tiny DOM helpers ────────────────────────────────────────────────
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function setStatus(msg, isErr) {
    var s = $("status");
    s.textContent = msg || "";
    s.style.color = isErr ? "var(--red)" : "var(--dim)";
  }
  function showBanner(msg) {
    var b = $("banner");
    b.style.display = msg ? "block" : "none";
    b.textContent = msg || "";
  }

  function api(path, opts) {
    return fetch(ORIGIN + path, opts).then(function (resp) {
      if (resp.status === 404 && path.indexOf("/api/trips") === 0) {
        // Could be gate-off OR a genuinely missing id. Probe the list
        // endpoint once to distinguish.
        return resp.json().catch(function () { return {}; }).then(function (body) {
          var detail = (body && body.detail) || "";
          if (detail === "Not found") {
            state.gateOff = true;
            showBanner(
              "Trips feature is disabled on the server. Set " +
              "HORNELORE_TRIPS=1 in .env and restart the stack."
            );
          }
          throw new Error(detail || ("HTTP " + resp.status));
        });
      }
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (body) {
          throw new Error((body && body.detail) || ("HTTP " + resp.status));
        });
      }
      state.gateOff = false;
      showBanner("");
      return resp.json();
    });
  }

  // ── narrator picker ─────────────────────────────────────────────────
  function loadNarrators() {
    return fetch(ORIGIN + "/api/people")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var people = (data && data.people) || [];
        var sel = $("narratorSel");
        sel.innerHTML = "";
        var opt0 = el("option", null, "— all narrators —");
        opt0.value = "";
        sel.appendChild(opt0);
        people.forEach(function (p) {
          var opt = el("option", null, p.display_name || p.id);
          opt.value = p.id || "";
          sel.appendChild(opt);
        });
        if (state.narratorId) sel.value = state.narratorId;
      })
      .catch(function (e) { setStatus("people load failed: " + e.message, true); });
  }

  // ── trip list ───────────────────────────────────────────────────────
  function loadTrips() {
    var q = state.narratorId
      ? "?person_id=" + encodeURIComponent(state.narratorId) : "";
    return api("/api/trips" + q).then(function (data) {
      var list = $("tripList");
      list.innerHTML = "";
      var trips = (data && data.trips) || [];
      if (!trips.length) {
        list.appendChild(el("span", "small", "No trips for this narrator yet — import one."));
        return;
      }
      trips.forEach(function (t) {
        var item = el("div", "trip-item" + (t.id === state.tripId ? " on" : ""));
        item.appendChild(el("div", "t", t.title || t.id));
        item.appendChild(el(
          "div", "d",
          (t.start_date || "?") + " → " + (t.end_date || "?") +
          "  ·  " + (t.status || "draft")
        ));
        item.addEventListener("click", function () { selectTrip(t.id); });
        list.appendChild(item);
      });
    }).catch(function (e) { setStatus("trips: " + e.message, true); });
  }

  // ── trip detail ─────────────────────────────────────────────────────
  function flatStopsOf(tree) {
    var out = [];
    function walk(s) {
      out.push(s);
      (s.children || []).forEach(walk);
    }
    (tree.regions || []).forEach(function (r) { (r.stops || []).forEach(walk); });
    return out;
  }

  function selectTrip(tripId) {
    state.tripId = tripId;
    localStorage.setItem(LS_TRIP, tripId);
    $("memoirPreview").innerHTML = "";
    $("reviewQueue").innerHTML = "";
    $("clusterResult").textContent = "";
    return api("/api/trips/" + encodeURIComponent(tripId) + "/tree")
      .then(function (tree) {
        state.tree = tree;
        state.flatStops = flatStopsOf(tree);
        renderOverview(tree);
        renderRegions(tree);
        renderThemes(tree);
        loadTrips(); // refresh selection highlight
      })
      .catch(function (e) { setStatus("tree: " + e.message, true); });
  }

  function renderOverview(tree) {
    var o = $("overview");
    o.innerHTML = "";
    var h = el("div");
    var title = el("div", "t");
    title.style.fontSize = "18px";
    title.style.fontWeight = "700";
    title.textContent = tree.title || tree.id;
    h.appendChild(title);
    h.appendChild(el(
      "div", "small",
      (tree.start_date || "?") + " → " + (tree.end_date || "?")
    ));
    if (tree.summary) h.appendChild(el("p", null, tree.summary));
    var stops = state.flatStops.length;
    var photos = state.flatStops.reduce(function (n, s) {
      return n + (s.photo_count || 0);
    }, 0);
    var badges = el("div");
    badges.appendChild(el("span", "badge", (tree.regions || []).length + " regions"));
    badges.appendChild(el("span", "badge", stops + " stops"));
    badges.appendChild(el("span", "badge " + (photos ? "green" : ""), photos + " photos assigned"));
    if (tree.unassigned_photo_count) {
      badges.appendChild(el("span", "badge warn", tree.unassigned_photo_count + " unassigned"));
    }
    h.appendChild(badges);
    var row = el("div", "row");
    var delBtn = el("button", "btn red small", "Delete trip");
    delBtn.type = "button";
    delBtn.addEventListener("click", function () {
      if (!confirm("Delete this trip and all its regions/stops/photo links?\n(Photos themselves are not touched.)")) return;
      api("/api/trips/" + encodeURIComponent(state.tripId), { method: "DELETE" })
        .then(function () {
          state.tripId = ""; state.tree = null;
          $("overview").innerHTML = ""; $("regions").innerHTML = "";
          $("themes").innerHTML = ""; $("memoirPreview").innerHTML = "";
          $("reviewQueue").innerHTML = "";
          setStatus("Trip deleted.");
          loadTrips();
        })
        .catch(function (e) { setStatus("delete: " + e.message, true); });
    });
    row.appendChild(delBtn);
    h.appendChild(row);
    o.appendChild(h);
  }

  function stopEditor(stop) {
    var det = el("details", "editor");
    var sum = el("summary", "small", "✎ edit dates / GPS / notes");
    det.appendChild(sum);
    var frm = el("div", "frm");
    function field(labelText, id, value, placeholder) {
      var wrap = el("div");
      wrap.appendChild(el("label", null, labelText));
      var inp = el("input");
      inp.type = "text";
      inp.value = value == null ? "" : String(value);
      inp.placeholder = placeholder || "";
      inp.dataset.k = id;
      wrap.appendChild(inp);
      return wrap;
    }
    frm.appendChild(field("date_start", "date_start", stop.date_start, "YYYY-MM-DD"));
    frm.appendChild(field("date_end", "date_end", stop.date_end, "YYYY-MM-DD"));
    frm.appendChild(field("latitude", "latitude", stop.latitude, "45.4408"));
    frm.appendChild(field("longitude", "longitude", stop.longitude, "12.3155"));
    frm.appendChild(field("location_name", "location_name", stop.location_name, ""));
    frm.appendChild(field("notes", "notes", stop.notes, ""));
    var saveWrap = el("div");
    saveWrap.style.gridColumn = "1 / -1";
    var save = el("button", "btn small", "Save stop");
    save.type = "button";
    save.addEventListener("click", function () {
      var body = {};
      frm.querySelectorAll("input").forEach(function (inp) {
        var v = inp.value.trim();
        if (v === "") return;
        if (inp.dataset.k === "latitude" || inp.dataset.k === "longitude") {
          var f = parseFloat(v);
          if (!isNaN(f)) body[inp.dataset.k] = f;
        } else {
          body[inp.dataset.k] = v;
        }
      });
      if (!Object.keys(body).length) { setStatus("nothing to save"); return; }
      api("/api/trips/stops/" + encodeURIComponent(stop.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function () {
        setStatus("Stop saved — re-run clustering to apply new dates/GPS.");
        selectTrip(state.tripId);
      }).catch(function (e) { setStatus("stop save: " + e.message, true); });
    });
    saveWrap.appendChild(save);
    frm.appendChild(saveWrap);
    det.appendChild(frm);
    return det;
  }

  function renderStop(stop, container) {
    var div = el("div", "stop" + (stop.stop_type === "base" ? " base" : ""));
    var nm = el("span", "nm", stop.title || stop.location_name || "");
    div.appendChild(nm);
    var metaBits = [];
    if (stop.stop_type && stop.stop_type !== "sight") metaBits.push(stop.stop_type);
    if (stop.date_start) {
      metaBits.push(
        stop.date_end && stop.date_end !== stop.date_start
          ? stop.date_start + " – " + stop.date_end : stop.date_start
      );
    }
    if (stop.latitude != null) metaBits.push("gps ✓");
    if (stop.photo_count) metaBits.push(stop.photo_count + " photos");
    div.appendChild(el("span", "meta", metaBits.length ? "  · " + metaBits.join(" · ") : ""));
    div.appendChild(stopEditor(stop));
    container.appendChild(div);
    if (stop.children && stop.children.length) {
      var kids = el("div", "kids");
      stop.children.forEach(function (c) { renderStop(c, kids); });
      container.appendChild(kids);
    }
  }

  function renderRegions(tree) {
    var host = $("regions");
    host.innerHTML = "";
    (tree.regions || []).forEach(function (r, i) {
      var reg = el("div", "region");
      var rh = el("div", "rh");
      rh.appendChild(el("span", "badge", String(i + 1)));
      rh.appendChild(document.createTextNode(" " + (r.title || "")));
      var span = el("span", "small",
        "  " + (r.start_date || "") +
        (r.end_date ? " – " + r.end_date : "") +
        (r.base_address ? "  ·  base: " + r.base_address : ""));
      rh.appendChild(span);
      reg.appendChild(rh);
      (r.stops || []).forEach(function (s) { renderStop(s, reg); });
      host.appendChild(reg);
    });
  }

  function renderThemes(tree) {
    var host = $("themes");
    host.innerHTML = "";
    var themes = tree.themes || [];
    if (!themes.length) {
      host.appendChild(el("span", "small", "No themes recorded."));
      return;
    }
    themes.forEach(function (t) {
      var chip = el("span", "theme", t.title || t.tag);
      if (t.description) chip.title = t.description;
      host.appendChild(chip);
    });
  }

  // ── clustering + review queue ───────────────────────────────────────
  function runCluster() {
    if (!state.tripId) { setStatus("select a trip first", true); return; }
    setStatus("clustering…");
    api("/api/trips/" + encodeURIComponent(state.tripId) + "/cluster-photos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).then(function (r) {
      setStatus("clustering done.");
      // selectTrip clears the result panel as part of its refresh, so
      // write the summary AFTER the refresh completes (live-verified
      // 2026-07-06: the message was being wiped instantly).
      var summary =
        "photos considered: " + r.photos_considered +
        " · links written: " + r.links_written +
        " · needs review: " + r.needs_review;
      selectTrip(state.tripId).then(function () {
        $("clusterResult").textContent = summary;
        loadQueue(0.5);
      });
    }).catch(function (e) { setStatus("cluster: " + e.message, true); });
  }

  function confClass(c) {
    if (c == null) return "lo";
    if (c < 0.5) return "lo";
    if (c < 0.75) return "mid";
    return "hi";
  }

  function loadQueue(maxConf) {
    if (!state.tripId) { setStatus("select a trip first", true); return; }
    var q = maxConf != null ? "?max_confidence=" + maxConf : "";
    api("/api/trips/" + encodeURIComponent(state.tripId) + "/photo-links" + q)
      .then(function (data) {
        var host = $("reviewQueue");
        host.innerHTML = "";
        var links = data.photo_links || [];
        if (!links.length) {
          host.appendChild(el("span", "small",
            maxConf != null
              ? "Review queue is empty — nothing under " + maxConf + "."
              : "No photo links yet — run clustering."));
          return;
        }
        links.forEach(function (link) { host.appendChild(queueRow(link)); });
      })
      .catch(function (e) { setStatus("queue: " + e.message, true); });
  }

  function queueRow(link) {
    var row = el("div", "qrow");
    var img = el("img");
    img.loading = "lazy";
    img.src = ORIGIN + "/api/photos/" + encodeURIComponent(link.photo_id) + "/thumb";
    img.onerror = function () { img.style.visibility = "hidden"; };
    row.appendChild(img);

    var qi = el("div", "qi");
    var confSpan = el("span", "conf " + confClass(link.cluster_confidence),
      link.cluster_confidence == null ? "—" : Number(link.cluster_confidence).toFixed(2));
    qi.appendChild(confSpan);
    qi.appendChild(document.createTextNode(
      "  " + (link.assignment_method || "") +
      (link.taken_at ? "  ·  " + link.taken_at : "")));
    qi.appendChild(el("div", "cid", "photo " + link.photo_id));

    var sel = el("select");
    var optNone = el("option", null, "(unassigned)");
    optNone.value = "";
    sel.appendChild(optNone);
    state.flatStops.forEach(function (s) {
      var opt = el("option", null, s.location_name + (s.date_start ? " (" + s.date_start + ")" : ""));
      opt.value = s.id;
      if (s.id === link.trip_stop_id) opt.selected = true;
      sel.appendChild(opt);
    });
    qi.appendChild(sel);
    row.appendChild(qi);

    var btns = el("div");
    var confirmBtn = el("button", "btn small green", "Confirm");
    confirmBtn.type = "button";
    confirmBtn.addEventListener("click", function () {
      var body = { confirm: true };
      if (sel.value) body.trip_stop_id = sel.value;
      api("/api/trips/photo-links/" + encodeURIComponent(link.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function () {
        setStatus("link confirmed (operator truth — survives re-clustering).");
        row.style.opacity = "0.45";
        confirmBtn.disabled = true;
      }).catch(function (e) { setStatus("confirm: " + e.message, true); });
    });
    btns.appendChild(confirmBtn);
    var exclBtn = el("button", "btn small ghost", "Exclude");
    exclBtn.type = "button";
    exclBtn.title = "Keep the link but leave this photo out of the memoir";
    exclBtn.addEventListener("click", function () {
      api("/api/trips/photo-links/" + encodeURIComponent(link.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ include_in_memoir: false }),
      }).then(function () {
        setStatus("photo excluded from memoir.");
        row.style.opacity = "0.45";
      }).catch(function (e) { setStatus("exclude: " + e.message, true); });
    });
    btns.appendChild(exclBtn);
    row.appendChild(btns);
    return row;
  }

  // ── memoir preview + DOCX ───────────────────────────────────────────
  function loadPreview() {
    if (!state.tripId) { setStatus("select a trip first", true); return; }
    api("/api/trips/" + encodeURIComponent(state.tripId) + "/memoir-preview")
      .then(function (p) {
        var host = $("memoirPreview");
        host.innerHTML = "";
        host.appendChild(el("h4", null, "Part I — The Journey in Order"));
        (p.part_one_journey_in_order || []).forEach(function (r, i) {
          var lines = [(i + 1) + ". " + (r.region || "")];
          function walkStops(stops, depth) {
            (stops || []).forEach(function (s) {
              lines.push("  ".repeat(depth + 1) + "• " + (s.location_name || "") +
                (s.date_start ? " (" + s.date_start + ")" : "") +
                (s.photo_count ? " · " + s.photo_count + " photos" : ""));
              walkStops(s.day_trips, depth + 1);
            });
          }
          walkStops(r.stops, 0);
          var pre = el("pre", null, lines.join("\n"));
          host.appendChild(pre);
        });
        host.appendChild(el("h4", null, "Part II — Themes"));
        (p.part_two_themes || []).forEach(function (t) {
          host.appendChild(el("pre", null,
            "• " + t.theme +
            (t.stops && t.stops.length ? " — " + t.stops.join(", ") : " — (no stops tagged)")));
        });
        host.appendChild(el("h4", null, "Part III — Photo Appendix"));
        var a = p.part_three_photo_appendix || {};
        host.appendChild(el("pre", null,
          "assigned: " + (a.assigned_photos || 0) +
          " · unassigned: " + (a.unassigned_photos || 0)));
      })
      .catch(function (e) { setStatus("preview: " + e.message, true); });
  }

  function downloadDocx() {
    if (!state.tripId) { setStatus("select a trip first", true); return; }
    // Plain navigation — the endpoint streams a Content-Disposition
    // attachment, so the browser downloads without leaving the page.
    window.location.href =
      ORIGIN + "/api/trips/" + encodeURIComponent(state.tripId) + "/export-docx";
  }

  // ── import dialog ───────────────────────────────────────────────────
  var importMode = "json";
  function openImport(mode) {
    importMode = mode;
    $("importDlgTitle").textContent =
      mode === "json" ? "Import itinerary JSON" : "Import CSV itinerary";
    $("csvMeta").style.display = mode === "csv" ? "block" : "none";
    $("pasteLabel").textContent =
      mode === "json" ? "Paste itinerary JSON" : "Paste CSV rows";
    $("importText").value = "";
    $("importErr").textContent = "";
    $("importDlg").showModal();
  }

  function doImport() {
    var personId = state.narratorId;
    if (!personId) {
      $("importErr").textContent = "Pick a narrator in the header first.";
      return;
    }
    var text = $("importText").value.trim();
    if (!text) { $("importErr").textContent = "Nothing to import."; return; }
    var path, body;
    if (importMode === "json") {
      var itinerary;
      try { itinerary = JSON.parse(text); }
      catch (e) { $("importErr").textContent = "Invalid JSON: " + e.message; return; }
      path = "/api/trips/import-itinerary";
      body = { person_id: personId, itinerary: itinerary };
    } else {
      var title = $("csvTitle").value.trim();
      if (!title) { $("importErr").textContent = "CSV import needs a trip title."; return; }
      path = "/api/trips/import-csv";
      body = {
        person_id: personId, title: title, csv_text: text,
        start_date: $("csvStart").value.trim() || null,
        end_date: $("csvEnd").value.trim() || null,
      };
    }
    api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) {
      $("importDlg").close();
      setStatus("Imported trip " + r.trip_id);
      loadTrips().then(function () { selectTrip(r.trip_id); });
    }).catch(function (e) { $("importErr").textContent = e.message; });
  }

  // ── wiring ──────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    if (_urlNarrator) {
      localStorage.setItem(LS_NARRATOR, _urlNarrator);
    }
    loadNarrators().then(loadTrips);
    if (state.tripId) selectTrip(state.tripId);

    $("narratorSel").addEventListener("change", function () {
      state.narratorId = this.value;
      localStorage.setItem(LS_NARRATOR, state.narratorId);
      loadTrips();
    });
    $("refreshBtn").addEventListener("click", function () {
      loadTrips();
      if (state.tripId) selectTrip(state.tripId);
    });
    $("importJsonBtn").addEventListener("click", function () { openImport("json"); });
    $("importCsvBtn").addEventListener("click", function () { openImport("csv"); });
    $("importCancel").addEventListener("click", function () { $("importDlg").close(); });
    $("importGo").addEventListener("click", doImport);
    $("clusterBtn").addEventListener("click", runCluster);
    $("openIntakeBtn").addEventListener("click", function () {
      window.open("photo-intake.html", "_blank", "noopener");
    });
    $("queueBtn").addEventListener("click", function () { loadQueue(0.5); });
    $("allLinksBtn").addEventListener("click", function () { loadQueue(null); });
    $("previewBtn").addEventListener("click", loadPreview);
    $("docxBtn").addEventListener("click", downloadDocx);
  });
})();
