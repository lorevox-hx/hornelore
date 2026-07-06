(function () {
  "use strict";

  const state = {
    apiBase: "http://localhost:8000",
    personId: "",
    trips: [],
    trip: null,
    tree: null,
    photoLinks: [],
  };

  const $ = (id) => document.getElementById(id);
  const val = (id) => ($(id)?.value || "").trim();
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  function log(msg, obj) {
    const out = $("tdOutput");
    const line = typeof msg === "string" ? msg : JSON.stringify(msg, null, 2);
    out.textContent = line + (obj === undefined ? "" : "\n" + JSON.stringify(obj, null, 2));
  }

  function setStatus(kind, text) {
    const dot = $("tdDot");
    dot.className = "td-dot" + (kind ? " " + kind : "");
    $("tdStatusText").textContent = text;
  }

  function syncInputs() {
    state.apiBase = val("tdApiBase").replace(/\/$/, "") || "http://localhost:8000";
    state.personId = val("tdPersonId");
  }

  async function api(path, opts = {}) {
    syncInputs();
    const res = await fetch(state.apiBase + path, {
      ...opts,
      headers: opts.body instanceof FormData ? opts.headers : {
        "Content-Type": "application/json",
        ...(opts.headers || {}),
      },
    });
    const text = await res.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch (_) { body = text; }
    if (!res.ok) {
      const detail = body && body.detail ? body.detail : text || res.statusText;
      throw new Error(res.status + " " + detail);
    }
    return body;
  }

  function allStops(tree) {
    const out = [];
    (tree?.regions || []).forEach((r) => {
      const walk = (s, region, depth) => {
        out.push({ ...s, region_id: region.id, region_title: region.title, depth });
        (s.children || []).forEach((c) => walk(c, region, depth + 1));
      };
      (r.stops || []).forEach((s) => walk(s, r, 0));
    });
    return out;
  }

  function dateSpan(a, b) {
    return [a, b].filter(Boolean).join(" to ");
  }

  function renderTrips() {
    const host = $("tdTripList");
    host.className = "td-trip-list" + (state.trips.length ? "" : " td-empty");
    if (!state.trips.length) {
      host.textContent = "No trips found for this narrator.";
      return;
    }
    host.innerHTML = "";
    state.trips.forEach((t) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "td-trip-card" + (state.trip && state.trip.id === t.id ? " active" : "");
      btn.innerHTML = `<span class="td-trip-card-title">${esc(t.title || "Untitled trip")}</span><span class="td-trip-card-dates">${esc(dateSpan(t.start_date, t.end_date) || t.id)}</span>`;
      btn.addEventListener("click", () => openTrip(t));
      host.appendChild(btn);
    });
  }

  function renderTree() {
    const title = $("tdActiveTripTitle");
    const meta = $("tdTripMeta");
    const treeHost = $("tdTree");
    const regionSel = $("tdStopRegion");
    const parentSel = $("tdStopParent");

    if (!state.trip || !state.tree) {
      title.textContent = "None selected";
      meta.textContent = "Choose a trip to document.";
      treeHost.innerHTML = "";
      regionSel.innerHTML = "<option value=''>Select a trip first</option>";
      parentSel.innerHTML = "<option value=''>No parent</option>";
      renderPhotos();
      return;
    }

    title.textContent = state.trip.title || "Untitled trip";
    meta.textContent = dateSpan(state.trip.start_date, state.trip.end_date) || state.trip.id;

    const regions = state.tree.regions || [];
    regionSel.innerHTML = regions.length ? "" : "<option value=''>Add a region first</option>";
    regions.forEach((r) => {
      const opt = document.createElement("option");
      opt.value = r.id;
      opt.textContent = r.title || "Region";
      regionSel.appendChild(opt);
    });

    parentSel.innerHTML = "<option value=''>No parent / top-level stop</option>";
    allStops(state.tree).forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = `${"— ".repeat(s.depth)}${s.location_name || s.title || "Stop"} (${s.region_title || "region"})`;
      parentSel.appendChild(opt);
    });

    if (!regions.length) {
      treeHost.innerHTML = `<p class="td-empty">No regions yet. Add the first region.</p>`;
      return;
    }
    treeHost.innerHTML = regions.map((r) => {
      const stops = (r.stops || []).map((s) => stopHtml(s, 0)).join("") || `<div class="td-muted">No stops yet.</div>`;
      return `<div class="td-region"><div class="td-region-title">${esc(r.title || "Region")}</div><div class="td-muted">${esc(dateSpan(r.start_date, r.end_date) || r.country_or_area || "")}</div>${stops}</div>`;
    }).join("");
    renderPhotos();
  }

  function stopHtml(s, depth) {
    const children = (s.children || []).map((c) => stopHtml(c, depth + 1)).join("");
    return `<div class="td-stop" style="margin-left:${depth * 18}px"><strong>${esc(s.title || s.location_name || "Stop")}</strong><small>${esc([s.stop_type, dateSpan(s.date_start, s.date_end), s.notes].filter(Boolean).join(" · "))}</small></div>${children}`;
  }

  function renderPhotos() {
    const host = $("tdPhotoStrip");
    if (!state.trip) {
      host.className = "td-photo-strip td-empty";
      host.textContent = "No trip selected.";
      return;
    }
    const links = state.photoLinks || [];
    if (!links.length) {
      host.className = "td-photo-strip td-empty";
      host.textContent = "No narrator-ready linked photos yet.";
      return;
    }
    host.className = "td-photo-strip";
    host.innerHTML = "";
    links.slice(0, 60).forEach((l) => {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = l.caption || "Trip photo";
      img.src = `${state.apiBase}/api/photos/${encodeURIComponent(l.photo_id)}/thumb`;
      img.addEventListener("error", () => img.remove());
      host.appendChild(img);
    });
  }

  async function loadTrips() {
    syncInputs();
    if (!state.personId) throw new Error("person_id is required");
    const data = await api(`/api/trips?person_id=${encodeURIComponent(state.personId)}`);
    state.trips = Array.isArray(data?.trips) ? data.trips : [];
    renderTrips();
    setStatus("good", `Loaded ${state.trips.length} trip${state.trips.length === 1 ? "" : "s"}`);
  }

  async function openTrip(trip) {
    state.trip = trip;
    renderTrips();
    const [tree, photos] = await Promise.all([
      api(`/api/trips/${encodeURIComponent(trip.id)}/tree`),
      api(`/api/trips/${encodeURIComponent(trip.id)}/narrator-photo-links`).catch(() => ({ photo_links: [] })),
    ]);
    state.tree = tree;
    state.photoLinks = Array.isArray(photos?.photo_links) ? photos.photo_links : [];
    renderTree();
    log("Trip loaded", { trip: state.trip, regions: (tree.regions || []).length, narrator_photo_links: state.photoLinks.length });
  }

  async function createTrip() {
    syncInputs();
    if (!state.personId) throw new Error("person_id is required");
    const title = val("tdTripTitle");
    if (!title) throw new Error("trip title is required");
    const body = {
      person_id: state.personId,
      title,
      start_date: val("tdTripStart") || null,
      end_date: val("tdTripEnd") || null,
      summary: val("tdTripSummary") || null,
    };
    const out = await api("/api/trips", { method: "POST", body: JSON.stringify(body) });
    log("Trip created", out);
    await loadTrips();
    const created = state.trips.find((t) => t.id === out.trip_id);
    if (created) await openTrip(created);
  }

  async function createRegion() {
    if (!state.trip) throw new Error("select a trip first");
    const title = val("tdRegionName");
    if (!title) throw new Error("region title is required");
    const body = {
      title,
      country_or_area: val("tdRegionArea") || null,
      start_date: val("tdRegionStart") || null,
      end_date: val("tdRegionEnd") || null,
      base_address: val("tdRegionBase") || null,
    };
    const out = await api(`/api/trips/${encodeURIComponent(state.trip.id)}/regions`, { method: "POST", body: JSON.stringify(body) });
    log("Region added", out);
    await openTrip(state.trip);
  }

  async function createStop() {
    if (!state.trip) throw new Error("select a trip first");
    const regionId = val("tdStopRegion");
    if (!regionId) throw new Error("select a region");
    const name = val("tdStopName");
    if (!name) throw new Error("place name is required");
    const body = {
      location_name: name,
      stop_type: val("tdStopType") || "sight",
      parent_trip_stop_id: val("tdStopParent") || null,
      date_start: val("tdStopStart") || null,
      date_end: val("tdStopEnd") || null,
      notes: val("tdStopNotes") || null,
    };
    const out = await api(`/api/trips/${encodeURIComponent(state.trip.id)}/regions/${encodeURIComponent(regionId)}/stops`, { method: "POST", body: JSON.stringify(body) });
    log("Stop added", out);
    $("tdStopName").value = "";
    $("tdStopNotes").value = "";
    await openTrip(state.trip);
  }

  async function uploadPhotos() {
    if (!state.trip) throw new Error("select a trip first");
    const files = Array.from($("tdPhotoFiles").files || []);
    if (!files.length) throw new Error("choose at least one photo");
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    fd.append("uploaded_by_user_id", "travel_documenter");
    fd.append("narrator_ready", "true");
    fd.append("uploaded_from_surface", "travel_documenter");
    const out = await api(`/api/trips/${encodeURIComponent(state.trip.id)}/photos`, { method: "POST", body: fd });
    $("tdPhotoFiles").value = "";
    log("Photos uploaded", out);
    await openTrip(state.trip);
  }

  async function clusterPhotos() {
    if (!state.trip) throw new Error("select a trip first");
    const body = { narrator_id: state.personId || null };
    const out = await api(`/api/trips/${encodeURIComponent(state.trip.id)}/cluster-photos`, { method: "POST", body: JSON.stringify(body) });
    log("Cluster photos result", out);
    await openTrip(state.trip);
  }

  async function memoirPreview() {
    if (!state.trip) throw new Error("select a trip first");
    const out = await api(`/api/trips/${encodeURIComponent(state.trip.id)}/memoir-preview`);
    log("Memoir preview", out);
  }

  async function ping() {
    try {
      syncInputs();
      if (state.personId) await api(`/api/trips?person_id=${encodeURIComponent(state.personId)}`);
      else await fetch(state.apiBase + "/api/trips").catch(() => null);
      setStatus("good", "API reachable");
      log("API reachable. If trips return 404, set HORNELORE_TRIPS=1 and restart.");
    } catch (e) {
      setStatus("bad", "API issue");
      log("API check failed", { error: e.message });
    }
  }

  function bind(id, fn) {
    $(id).addEventListener("click", async () => {
      try { await fn(); } catch (e) { setStatus("bad", "Error"); log("Error", { message: e.message }); }
    });
  }

  function initFromUrl() {
    const qs = new URLSearchParams(location.search);
    if (qs.get("api")) $("tdApiBase").value = qs.get("api");
    if (qs.get("person_id")) $("tdPersonId").value = qs.get("person_id");
  }

  window.addEventListener("DOMContentLoaded", () => {
    initFromUrl();
    bind("tdPing", ping);
    bind("tdLoadTrips", loadTrips);
    bind("tdRefreshTrips", loadTrips);
    bind("tdCreateTrip", createTrip);
    bind("tdReloadTree", async () => { if (state.trip) await openTrip(state.trip); });
    bind("tdCreateRegion", createRegion);
    bind("tdCreateStop", createStop);
    bind("tdUploadPhotos", uploadPhotos);
    bind("tdClusterPhotos", clusterPhotos);
    bind("tdMemoirPreview", memoirPreview);
    $("tdClearOutput").addEventListener("click", () => log("Ready."));
    renderTree();
    setStatus("", "Ready");
  });
})();
