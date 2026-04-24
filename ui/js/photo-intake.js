/* ═══════════════════════════════════════════════════════════════
   photo-intake.js — WO-LORI-PHOTO-SHARED-01 §14

   Curator-only page. Talks to:
     POST   /api/photos           (multipart)
     GET    /api/photos?narrator_id=...
     PATCH  /api/photos/{id}      (narrator_ready toggle)
     DELETE /api/photos/{id}      (soft delete)
     GET    /api/people           (narrator picker)

   No WO-10C timers here. No narrator session controls.
═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var ORIGIN = window.LOREVOX_API || "http://localhost:8000";
  var LS_NARRATOR   = "pi_narrator_id_v1";
  var LS_CURATOR    = "pi_curator_user_id_v1";

  var $  = function (id) { return document.getElementById(id); };
  var el = {
    narrator:        $("piNarrator"),
    file:            $("piFile"),
    description:     $("piDescription"),
    dateValue:       $("piDateValue"),
    datePrecision:   $("piDatePrecision"),
    locationLabel:   $("piLocationLabel"),
    locationSource:  $("piLocationSource"),
    peopleList:      $("piPeopleList"),
    addPerson:       $("piAddPersonBtn"),
    eventsList:      $("piEventsList"),
    addEvent:        $("piAddEventBtn"),
    narratorReady:   $("piNarratorReady"),
    save:            $("piSaveBtn"),
    reset:           $("piResetBtn"),
    status:          $("piStatus"),
    list:            $("piList"),
    listStatus:      $("piListStatus"),
  };

  function setStatus(msg, level) {
    el.status.textContent = msg || "";
    el.status.className = "pi-status" + (level ? " " + level : "");
  }

  function setListStatus(msg, level) {
    el.listStatus.textContent = msg || "";
    el.listStatus.className = "pi-status" + (level ? " " + level : "");
  }

  // ── Narrator picker ─────────────────────────────────────────
  function loadNarrators() {
    return fetch(ORIGIN + "/api/people")
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (people) {
        var items = Array.isArray(people) ? people
                   : (people && Array.isArray(people.people) ? people.people : []);
        el.narrator.innerHTML = "";
        if (!items.length) {
          el.narrator.innerHTML = '<option value="">— no narrators —</option>';
          return;
        }
        items.forEach(function (p) {
          var opt = document.createElement("option");
          opt.value = p.id || p.person_id || "";
          opt.textContent = p.display_name || p.name || opt.value;
          el.narrator.appendChild(opt);
        });
        var saved = localStorage.getItem(LS_NARRATOR);
        if (saved) {
          var opts = Array.from(el.narrator.options).map(function(o){return o.value;});
          if (opts.indexOf(saved) >= 0) el.narrator.value = saved;
        }
      })
      .catch(function () {
        el.narrator.innerHTML = '<option value="">— /api/people unavailable —</option>';
      });
  }

  el && el.narrator && el.narrator.addEventListener("change", function () {
    localStorage.setItem(LS_NARRATOR, el.narrator.value);
    refreshList();
  });

  // ── Dynamic person / event rows ─────────────────────────────
  function makePersonRow(initial) {
    initial = initial || { person_label: "", person_id: "" };
    var row = document.createElement("div");
    row.className = "pi-people-row";
    var inp = document.createElement("input");
    inp.type = "text";
    inp.className = "pi-person-label";
    inp.placeholder = "person_label (how the curator refers to them)";
    inp.value = initial.person_label || "";
    var rm = document.createElement("button");
    rm.type = "button";
    rm.className = "pi-chip-btn";
    rm.textContent = "Remove";
    rm.addEventListener("click", function () { row.remove(); });
    row.appendChild(inp);
    row.appendChild(rm);
    return row;
  }

  function makeEventRow(initial) {
    initial = initial || { event_label: "", event_id: "" };
    var row = document.createElement("div");
    row.className = "pi-events-row";
    var inp = document.createElement("input");
    inp.type = "text";
    inp.className = "pi-event-label";
    inp.placeholder = "event_label (e.g. July 4 cookout)";
    inp.value = initial.event_label || "";
    var rm = document.createElement("button");
    rm.type = "button";
    rm.className = "pi-chip-btn";
    rm.textContent = "Remove";
    rm.addEventListener("click", function () { row.remove(); });
    row.appendChild(inp);
    row.appendChild(rm);
    return row;
  }

  el.addPerson.addEventListener("click", function () {
    el.peopleList.appendChild(makePersonRow());
  });

  el.addEvent.addEventListener("click", function () {
    el.eventsList.appendChild(makeEventRow());
  });

  function collectPeople() {
    var rows = el.peopleList.querySelectorAll(".pi-person-label");
    var out = [];
    rows.forEach(function (inp) {
      var v = (inp.value || "").trim();
      if (v) out.push({ person_label: v });
    });
    return out;
  }

  function collectEvents() {
    var rows = el.eventsList.querySelectorAll(".pi-event-label");
    var out = [];
    rows.forEach(function (inp) {
      var v = (inp.value || "").trim();
      if (v) out.push({ event_label: v });
    });
    return out;
  }

  // ── Curator identity (uploaded_by_user_id) ──────────────────
  function getCuratorId() {
    var id = localStorage.getItem(LS_CURATOR);
    if (!id) {
      id = "curator_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem(LS_CURATOR, id);
    }
    return id;
  }

  // ── Submit ──────────────────────────────────────────────────
  el.save.addEventListener("click", function () {
    var narratorId = (el.narrator.value || "").trim();
    if (!narratorId) { setStatus("Please pick a narrator first.", "warn"); return; }
    var file = el.file.files && el.file.files[0];
    if (!file)       { setStatus("Please choose an image file.", "warn"); return; }

    var fd = new FormData();
    fd.append("file", file);
    fd.append("narrator_id", narratorId);
    fd.append("uploaded_by_user_id", getCuratorId());
    if (el.description.value.trim())   fd.append("description",    el.description.value.trim());
    if (el.dateValue.value.trim())     fd.append("date_value",     el.dateValue.value.trim());
    fd.append("date_precision", el.datePrecision.value || "unknown");
    if (el.locationLabel.value.trim()) fd.append("location_label", el.locationLabel.value.trim());
    fd.append("location_source", el.locationSource.value || "unknown");
    fd.append("narrator_ready", el.narratorReady.checked ? "true" : "false");

    // people and events are single form fields, each carrying a JSON
    // array (photos.py: `people: Optional[str] = Form(None)` → parsed
    // via _parse_json_list into a Python list). Only send the field
    // when there's at least one row so the empty-array case stays
    // byte-identical to "no field" on the wire.
    var peopleRows = collectPeople();
    var eventRows  = collectEvents();
    if (peopleRows.length) fd.append("people", JSON.stringify(peopleRows));
    if (eventRows.length)  fd.append("events", JSON.stringify(eventRows));

    el.save.disabled = true;
    setStatus("Uploading…");
    fetch(ORIGIN + "/api/photos", { method: "POST", body: fd })
      .then(function (r) {
        if (r.status === 409) {
          return r.json().then(function (body) {
            setStatus("This photo is already saved for this narrator.", "warn");
            throw new Error("duplicate");
          });
        }
        if (!r.ok) {
          return r.text().then(function (t) { throw new Error(t || ("HTTP " + r.status)); });
        }
        return r.json();
      })
      .then(function (_photo) {
        setStatus("Saved.", "ok");
        clearForm();
        refreshList();
      })
      .catch(function (e) {
        if (String(e && e.message) !== "duplicate") {
          setStatus("Upload failed: " + (e && e.message ? e.message : "unknown"), "err");
        }
      })
      .finally(function () { el.save.disabled = false; });
  });

  el.reset.addEventListener("click", function () { clearForm(); setStatus(""); });

  function clearForm() {
    el.file.value = "";
    el.description.value = "";
    el.dateValue.value = "";
    el.datePrecision.value = "unknown";
    el.locationLabel.value = "";
    el.locationSource.value = "unknown";
    el.peopleList.innerHTML = "";
    el.eventsList.innerHTML = "";
    el.narratorReady.checked = false;
  }

  // ── Saved list ──────────────────────────────────────────────
  function refreshList() {
    var narratorId = el.narrator.value;
    if (!narratorId) { el.list.innerHTML = ""; setListStatus("Pick a narrator to see saved photos."); return; }
    setListStatus("Loading…");
    fetch(ORIGIN + "/api/photos?narrator_id=" + encodeURIComponent(narratorId))
      .then(function (r) { return r.ok ? r.json() : { photos: [] }; })
      .then(function (body) {
        var photos = Array.isArray(body) ? body : (body.photos || []);
        renderList(photos);
        setListStatus(photos.length ? (photos.length + " saved") : "No photos yet.");
      })
      .catch(function () { setListStatus("Could not load list.", "err"); });
  }

  function renderList(photos) {
    el.list.innerHTML = "";
    photos.forEach(function (p) {
      var row = document.createElement("div");
      row.className = "pi-list-row";

      var img = document.createElement("img");
      img.className = "pi-thumb";
      img.alt = "";
      img.src = p.thumbnail_url || p.media_url || "";
      row.appendChild(img);

      var meta = document.createElement("div");
      meta.className = "pi-list-meta";
      var title = document.createElement("div");
      title.className = "pi-list-title";
      title.textContent = (p.description || "(no description)").slice(0, 140);
      var sub = document.createElement("div");
      sub.className = "pi-list-sub";
      var subBits = [];
      if (p.date_value)     subBits.push(p.date_value + (p.date_precision && p.date_precision !== "unknown" ? " (" + p.date_precision + ")" : ""));
      if (p.location_label) subBits.push(p.location_label);
      sub.textContent = subBits.join(" · ");
      meta.appendChild(title);
      meta.appendChild(sub);

      if (p.narrator_ready) {
        var pill = document.createElement("span");
        pill.className = "pi-pill ready";
        pill.textContent = "ready";
        title.appendChild(pill);
      }
      if (p.needs_confirmation) {
        var warn = document.createElement("span");
        warn.className = "pi-pill needs-review";
        warn.textContent = "needs review";
        title.appendChild(warn);
      }

      row.appendChild(meta);

      var actions = document.createElement("div");
      actions.className = "pi-list-actions";
      var toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "pi-chip-btn";
      toggle.textContent = p.narrator_ready ? "Mark not ready" : "Mark ready";
      toggle.addEventListener("click", function () { patchReady(p, !p.narrator_ready); });
      actions.appendChild(toggle);

      var del = document.createElement("button");
      del.type = "button";
      del.className = "pi-chip-btn";
      del.textContent = "Delete";
      del.addEventListener("click", function () { deletePhoto(p); });
      actions.appendChild(del);

      row.appendChild(actions);
      el.list.appendChild(row);
    });
  }

  function patchReady(photo, ready) {
    fetch(ORIGIN + "/api/photos/" + encodeURIComponent(photo.id), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        narrator_ready: !!ready,
        last_edited_by_user_id: getCuratorId(),
      })
    })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      refreshList();
    })
    .catch(function (e) { setListStatus("Update failed: " + e.message, "err"); });
  }

  function deletePhoto(photo) {
    if (!confirm("Soft-delete this photo? You can restore it manually later.")) return;
    fetch(ORIGIN + "/api/photos/" + encodeURIComponent(photo.id), { method: "DELETE" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        refreshList();
      })
      .catch(function (e) { setListStatus("Delete failed: " + e.message, "err"); });
  }

  // ── Bootstrap ────────────────────────────────────────────────
  loadNarrators().then(refreshList);
})();
