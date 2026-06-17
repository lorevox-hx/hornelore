/* ═══════════════════════════════════════════════════════════════════
   operator-intake.js — dedicated Operator Intake tab

   WO-OPERATOR-INTAKE-TAB-01 (2026-06-16):
   A standalone top-level tab where the operator enters or edits
   narrator data WITHOUT the narrator being present. Reads via the
   Phase 1 bio_questionnaire_view (HORNELORE_QUESTIONNAIRE_BIO_FACTS_
   READ=1) so all 9 sections (identity / family / marriage / children
   / education-work / military / faith / today / consent) show what
   the system already knows from intake + bio_facts + profile_json,
   with status badges per field.

   Section-level "Save" buttons PUT through the existing /api/bio-
   builder/questionnaire endpoint which fans out via the Phase 3
   bio_questionnaire_writer (HORNELORE_QUESTIONNAIRE_BIO_FACTS_WRITE=1)
   into bio_facts + profile_json.

   Why dedicated tab vs reusing Bio Builder:
     - Bio Builder is a much larger UI that includes Family Tree /
       Life Threads / Shadow Review / Conflicts. The operator just
       wants intake editing. A focused tab removes the navigation
       overhead.
     - Operator-only by design: not shown in Narrator Session view.

   Loading:
     window.OperatorIntake.init()          — call once on app init
     window.OperatorIntake.refresh()       — re-fetch + re-render
     window.OperatorIntake.onNarratorSwitch(newPid)  — clear + refresh
   ═══════════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  // ── Configuration ────────────────────────────────────────────────

  // 9 sections that mirror the intake-form-modal structure. Each
  // declares its fields with type, label, and (optional) bio_facts
  // field_key used to pull the status badge.
  var SECTIONS = [
    {
      id: "identity",
      label: "Identity",
      icon: "👤",
      fields: [
        { id: "fullName",         label: "Full legal name",    type: "text",   meta_key: "fullName"        },
        { id: "preferredName",    label: "Preferred name",      type: "text",   meta_key: "preferredName"   },
        { id: "dateOfBirth",      label: "Date of birth",       type: "text",   meta_key: "dateOfBirth",
          placeholder: "YYYY-MM-DD" },
        { id: "placeOfBirth",     label: "Place of birth",      type: "text",   meta_key: "placeOfBirth"    },
        { id: "currentResidence", label: "Current residence",   type: "text",   meta_key: null              },
        { id: "pronouns",         label: "Pronouns",            type: "select", meta_key: null,
          options: ["", "she/her", "he/him", "they/them", "other"] },
        { id: "birthOrder",       label: "Birth order",         type: "text",   meta_key: "birthOrder"      },
      ],
    },
    {
      id: "family",
      label: "Family of origin",
      icon: "🌱",
      array: "parents",
      arrayItemFields: [
        { id: "relation",   label: "Relation",  type: "select",
          options: ["Father", "Mother", "Stepfather", "Stepmother",
                    "Adoptive father", "Adoptive mother"] },
        { id: "firstName",  label: "First",     type: "text" },
        { id: "middleName", label: "Middle",    type: "text" },
        { id: "lastName",   label: "Last",      type: "text" },
        { id: "maidenName", label: "Maiden",    type: "text" },
        { id: "birthDate",  label: "Birth date", type: "text", placeholder: "YYYY-MM-DD" },
      ],
      meta_section_key: "parents",
    },
    {
      id: "marriage",
      label: "Marriage",
      icon: "💞",
      array: "spouses",
      arrayItemFields: [
        { id: "firstName",   label: "Spouse first",  type: "text" },
        { id: "middleName",  label: "Middle",         type: "text" },
        { id: "lastName",    label: "Last",           type: "text" },
        { id: "yearMarried", label: "Year married",   type: "text", placeholder: "YYYY" },
        { id: "status",      label: "Status",         type: "select",
          options: ["", "current", "divorced", "widowed", "separated"] },
      ],
      meta_section_key: "spouses",
    },
    {
      id: "children",
      label: "Children",
      icon: "🧒",
      array: "children",
      arrayItemFields: [
        { id: "firstName",   label: "First",       type: "text" },
        { id: "middleName",  label: "Middle",      type: "text" },
        { id: "lastName",    label: "Last",        type: "text" },
        { id: "dateOfBirth", label: "Date of birth", type: "text", placeholder: "YYYY-MM-DD" },
      ],
      meta_section_key: "children",
    },
    {
      id: "siblings",
      label: "Siblings",
      icon: "🧑‍🤝‍🧑",
      array: "siblings",
      arrayItemFields: [
        { id: "firstName",   label: "First",   type: "text" },
        { id: "middleName",  label: "Middle",  type: "text" },
        { id: "lastName",    label: "Last",    type: "text" },
        { id: "birthOrder",  label: "Birth order", type: "text" },
        { id: "birthDate",   label: "Birth date", type: "text", placeholder: "YYYY-MM-DD" },
      ],
      meta_section_key: "siblings",
    },
    {
      id: "education",
      label: "Education & Work",
      icon: "📚",
      fields: [
        { id: "highestLevel",       label: "Highest education level", type: "select", meta_key: "highestLevel",
          options: ["", "some_primary", "primary", "some_secondary", "high_school",
                    "associate", "some_college", "bachelors", "masters", "doctorate",
                    "trade_school", "other"] },
        { id: "primaryCareer",      label: "Primary career",          type: "text",   meta_key: "primaryCareer" },
        { id: "careerProgression",  label: "Years working / range",   type: "text",   meta_key: null,
          placeholder: "e.g. 1970-2020 or 50 years" },
      ],
    },
    {
      id: "military",
      label: "Military",
      icon: "🪖",
      fields: [
        { id: "served",          label: "Served?",       type: "select", meta_key: "served",
          options: ["", "no", "yes"] },
        { id: "branch",          label: "Branch",        type: "text",   meta_key: "branch" },
        { id: "servicePeriod",   label: "Service period", type: "text",   meta_key: "servicePeriod" },
        { id: "rank",            label: "Rank",           type: "text",   meta_key: "rank" },
        { id: "locations",       label: "Locations",      type: "text",   meta_key: "locations" },
        { id: "warsConflicts",   label: "Wars/conflicts", type: "text",   meta_key: "warsConflicts" },
        { id: "decorations",     label: "Decorations",    type: "textarea", meta_key: "decorations" },
        { id: "experienceNotes", label: "Notes",          type: "textarea", meta_key: "experienceNotes" },
      ],
    },
    {
      id: "faith",
      label: "Faith & Heritage",
      icon: "✨",
      fields: [
        { id: "religionRaised",     label: "Religion raised in",  type: "text",   meta_key: "religionRaised"    },
        { id: "currentFaith",       label: "Current faith",       type: "text",   meta_key: "currentFaith"      },
        { id: "ethnicityHeritage",  label: "Ethnicity / heritage", type: "text",   meta_key: "ethnicityHeritage" },
        { id: "languagesAtHome",    label: "Languages at home",   type: "text",   meta_key: "languagesAtHome"   },
      ],
    },
    {
      id: "today",
      label: "Today",
      icon: "🌅",
      fields: [
        { id: "livingSituation",      label: "Living situation",      type: "textarea", meta_key: null },
        { id: "healthConsiderations", label: "Health considerations", type: "textarea", meta_key: null },
      ],
    },
  ];

  // Status badge label map — mirrors bio-builder-questionnaire's table
  // so both surfaces render badges consistently.
  var STATUS_LABELS = {
    "approved":               { label: "Approved",      cls: "oi-badge-ok" },
    "operator_entered":       { label: "Entered",       cls: "oi-badge-known" },
    "document_sourced":       { label: "From document", cls: "oi-badge-known" },
    "anchored_asked":         { label: "Asked",         cls: "oi-badge-known" },
    "extracted_needs_verify": { label: "Needs verify",  cls: "oi-badge-amber" },
    "anchored_asked_pending": { label: "Pending",       cls: "oi-badge-amber" },
    "conflicted":             { label: "Conflicted",    cls: "oi-badge-red" },
    "superseded":             { label: "Replaced",      cls: "oi-badge-muted" },
    "empty":                  { label: "",              cls: "" }
  };

  // Statuses counted as "known" for the per-section rollup. Mirrors
  // server-side bio_gap_map._FILLED_STATUSES.
  var KNOWN_STATUSES = {
    "extracted_needs_verify": true,
    "document_sourced":       true,
    "anchored_asked":         true,
    "operator_entered":       true,
    "approved":               true
  };

  // ── State ────────────────────────────────────────────────────────

  var _state = {
    personId: null,
    questionnaire: {},
    meta: {},
    loading: false,
    dirtySections: {},  // sectionId → true
    lastSaveAt: null,
  };

  // ── Helpers ──────────────────────────────────────────────────────

  function _esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/[&<>"']/g, function (ch) {
      return ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        "\"": "&quot;", "'": "&#39;"
      })[ch];
    });
  }

  function _getApiBase() {
    // Match the convention used elsewhere — read from window.API_BASE
    // when set, else default to localhost:8000.
    if (typeof window !== "undefined" && window.API_BASE) return window.API_BASE;
    return "http://localhost:8000";
  }

  function _getCurrentPersonId() {
    try {
      if (typeof state !== "undefined" && state && state.person_id) {
        return state.person_id;
      }
    } catch (_) {}
    return null;
  }

  function _statusBadgeHtml(sectionId, fieldId) {
    var sec = _state.meta && _state.meta[sectionId];
    if (!sec || typeof sec !== "object") return "";
    var entry = sec[fieldId];
    if (!entry || typeof entry !== "object" || !entry.status || entry.status === "empty") return "";
    var spec = STATUS_LABELS[entry.status];
    if (!spec || !spec.label) return "";
    var src = (entry.source || "").trim();
    var tip = "Status: " + entry.status + (src ? " · Source: " + src : "");
    return '<span class="oi-status-badge ' + spec.cls + '" title="' + _esc(tip) +
      '">' + _esc(spec.label) + '</span>';
  }

  function _sectionKnownCount(section) {
    var key = section.meta_section_key || section.id;
    var sec = _state.meta && _state.meta[key];
    if (!sec || typeof sec !== "object") return 0;
    var n = 0;
    Object.keys(sec).forEach(function (k) {
      if (k === "_section") return;
      var entry = sec[k];
      if (entry && typeof entry === "object" && KNOWN_STATUSES[entry.status]) {
        n++;
      }
    });
    return n;
  }

  function _sectionTotalFields(section) {
    if (section.fields) return section.fields.length;
    if (section.array) {
      var arr = _state.questionnaire[section.array] || [];
      return Array.isArray(arr) ? arr.length : 0;
    }
    return 0;
  }

  function _sectionRollupHtml(section) {
    var known = _sectionKnownCount(section);
    var total = _sectionTotalFields(section);
    if (section.array) {
      return '<span class="oi-rollup oi-rollup-array">' +
        total + ' ' + (total === 1 ? 'entry' : 'entries') +
        (known > 0 ? ' · ' + known + ' confirmed' : '') +
        '</span>';
    }
    if (known === 0) {
      return '<span class="oi-rollup oi-rollup-empty">No information yet</span>';
    }
    return '<span class="oi-rollup oi-rollup-has">' +
      known + ' of ' + total + ' known' +
      '</span>';
  }

  // ── Fetch + render ──────────────────────────────────────────────

  function _renderEmpty(container, message) {
    container.innerHTML =
      '<div class="oi-empty">' +
      '<div class="oi-empty-icon">📋</div>' +
      '<div class="oi-empty-title">' + _esc(message || "No narrator selected") + '</div>' +
      '<div class="oi-empty-hint">Select a narrator above to load their intake details.</div>' +
      '</div>';
  }

  async function _fetchQuestionnaire(personId) {
    var url = _getApiBase() + "/api/bio-builder/questionnaire?person_id=" +
              encodeURIComponent(personId);
    var r = await fetch(url);
    if (!r.ok) throw new Error("HTTP " + r.status + " from questionnaire GET");
    return r.json();
  }

  async function _putSection(personId, sectionId) {
    var url = _getApiBase() + "/api/bio-builder/questionnaire";
    var body = {
      person_id: personId,
      questionnaire: _state.questionnaire,
      source: "operator_intake_tab:" + sectionId,
      version: 1,
    };
    var r = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      var t = await r.text();
      throw new Error("HTTP " + r.status + ": " + t.slice(0, 200));
    }
    return r.json();
  }

  function _readFieldValueFromForm(sectionEl, fieldId) {
    var el = sectionEl.querySelector('[data-oi-field="' + fieldId + '"]');
    return el ? (el.value || "") : "";
  }

  function _renderField(sectionId, field, value) {
    var domId = "oi_" + sectionId + "_" + field.id;
    var badge = field.meta_key ? _statusBadgeHtml(sectionId, field.meta_key) : "";
    var labelHtml = '<label class="oi-field-label" for="' + domId + '">' +
      _esc(field.label) + badge + '</label>';
    var v = _esc(value || "");
    var inputHtml = "";
    if (field.type === "select") {
      var opts = (field.options || []).map(function (o) {
        var sel = (o === value) ? ' selected' : '';
        return '<option value="' + _esc(o) + '"' + sel + '>' +
          (o ? _esc(o) : '— select —') + '</option>';
      }).join("");
      inputHtml = '<select id="' + domId + '" class="oi-input oi-select" data-oi-field="' +
        _esc(field.id) + '">' + opts + '</select>';
    } else if (field.type === "textarea") {
      inputHtml = '<textarea id="' + domId + '" class="oi-input oi-textarea" rows="3" ' +
        'data-oi-field="' + _esc(field.id) + '" placeholder="' + _esc(field.placeholder || "") + '">' +
        v + '</textarea>';
    } else {
      inputHtml = '<input id="' + domId + '" class="oi-input" type="text" ' +
        'data-oi-field="' + _esc(field.id) + '" value="' + v + '" placeholder="' +
        _esc(field.placeholder || "") + '" />';
    }
    return '<div class="oi-field">' + labelHtml + inputHtml + '</div>';
  }

  function _renderArrayItem(sectionId, itemFields, item, idx) {
    var inner = itemFields.map(function (f) {
      var domId = "oi_" + sectionId + "_" + idx + "_" + f.id;
      var v = _esc(item ? (item[f.id] || "") : "");
      var labelHtml = '<label class="oi-field-label" for="' + domId + '">' +
        _esc(f.label) + '</label>';
      var inputHtml = "";
      if (f.type === "select") {
        var opts = (f.options || []).map(function (o) {
          var sel = (o === (item ? item[f.id] : "")) ? ' selected' : '';
          return '<option value="' + _esc(o) + '"' + sel + '>' +
            (o ? _esc(o) : '— select —') + '</option>';
        }).join("");
        inputHtml = '<select id="' + domId + '" class="oi-input oi-select" data-oi-array-field="' +
          _esc(f.id) + '" data-oi-array-idx="' + idx + '">' + opts + '</select>';
      } else {
        inputHtml = '<input id="' + domId + '" class="oi-input" type="text" ' +
          'data-oi-array-field="' + _esc(f.id) + '" data-oi-array-idx="' + idx +
          '" value="' + v + '" placeholder="' + _esc(f.placeholder || "") + '" />';
      }
      return '<div class="oi-field oi-array-field">' + labelHtml + inputHtml + '</div>';
    }).join("");
    return '<div class="oi-array-row" data-oi-array-idx="' + idx + '">' +
      '<div class="oi-array-row-header">' +
      '<span class="oi-array-row-label">Entry ' + (idx + 1) + '</span>' +
      '<button type="button" class="oi-array-remove" data-oi-remove-idx="' + idx + '">Remove</button>' +
      '</div>' +
      '<div class="oi-array-row-body">' + inner + '</div>' +
      '</div>';
  }

  function _renderSection(section) {
    var savedAtHtml = _state.lastSaveAt && _state.dirtySections[section.id] === false ?
      '<span class="oi-saved-at">Saved</span>' : '';
    var dirtyHtml = _state.dirtySections[section.id] ?
      '<span class="oi-dirty">Unsaved changes</span>' : '';

    var body = "";
    if (section.array) {
      var arr = _state.questionnaire[section.array] || [];
      if (!Array.isArray(arr)) arr = [];
      body = arr.map(function (item, idx) {
        return _renderArrayItem(section.id, section.arrayItemFields, item, idx);
      }).join("") +
        '<button type="button" class="oi-array-add" data-oi-add-section="' +
        section.id + '">+ Add ' + _esc(section.label.toLowerCase()) + ' entry</button>';
    } else {
      var sectionData = _state.questionnaire[section.id] || {};
      body = section.fields.map(function (f) {
        return _renderField(section.id, f, sectionData[f.id]);
      }).join("");
    }

    return '<section class="oi-section" data-oi-section="' + _esc(section.id) + '">' +
      '<header class="oi-section-header">' +
      '<div class="oi-section-title">' +
      '<span class="oi-section-icon">' + section.icon + '</span>' +
      _esc(section.label) +
      '</div>' +
      '<div class="oi-section-meta">' +
      _sectionRollupHtml(section) +
      dirtyHtml + savedAtHtml +
      '</div>' +
      '</header>' +
      '<div class="oi-section-body">' + body + '</div>' +
      '<div class="oi-section-footer">' +
      '<button type="button" class="oi-save-btn" data-oi-save-section="' +
      _esc(section.id) + '">Save ' + _esc(section.label) + '</button>' +
      '</div>' +
      '</section>';
  }

  function _renderAll(container) {
    var pid = _state.personId;
    if (!pid) {
      _renderEmpty(container);
      return;
    }
    if (_state.loading) {
      container.innerHTML = '<div class="oi-loading">Loading intake data…</div>';
      return;
    }
    var sectionsHtml = SECTIONS.map(_renderSection).join("");
    container.innerHTML =
      '<header class="oi-tab-header">' +
      '<h2 class="oi-tab-title">Operator Intake</h2>' +
      '<p class="oi-tab-hint">' +
      'Enter or correct narrator details. Field badges show what the system ' +
      'already knows from intake + extraction + document review. Save each ' +
      'section independently — changes persist to canonical truth.' +
      '</p>' +
      '<div class="oi-tab-source-line">Reading from: <code>' +
      _esc(_state.source || "legacy_blob") + '</code></div>' +
      '</header>' +
      '<div class="oi-sections">' + sectionsHtml + '</div>';
    _attachHandlers(container);
  }

  function _attachHandlers(container) {
    // Mark section dirty on any field change
    container.addEventListener("input", function (ev) {
      var t = ev.target;
      if (!t) return;
      var secEl = t.closest && t.closest('[data-oi-section]');
      if (!secEl) return;
      var sid = secEl.getAttribute("data-oi-section");
      _state.dirtySections[sid] = true;
      // Reflect in header
      var dirty = secEl.querySelector(".oi-dirty");
      if (!dirty) {
        var meta = secEl.querySelector(".oi-section-meta");
        if (meta) {
          var span = document.createElement("span");
          span.className = "oi-dirty";
          span.textContent = "Unsaved changes";
          meta.appendChild(span);
        }
      }
    });

    container.addEventListener("click", async function (ev) {
      var t = ev.target;
      if (!t || !t.getAttribute) return;
      var saveSec = t.getAttribute("data-oi-save-section");
      if (saveSec) {
        await _saveSection(saveSec, container);
        return;
      }
      var addSec = t.getAttribute("data-oi-add-section");
      if (addSec) {
        _addArrayEntry(addSec, container);
        return;
      }
      if (t.classList && t.classList.contains("oi-array-remove")) {
        var rmIdx = t.getAttribute("data-oi-remove-idx");
        var secEl = t.closest && t.closest('[data-oi-section]');
        if (secEl) {
          var sid = secEl.getAttribute("data-oi-section");
          _removeArrayEntry(sid, parseInt(rmIdx, 10), container);
        }
      }
    });
  }

  function _readSectionFromForm(sectionId, container) {
    var section = SECTIONS.find(function (s) { return s.id === sectionId; });
    if (!section) return;
    var secEl = container.querySelector('[data-oi-section="' + sectionId + '"]');
    if (!secEl) return;
    if (section.array) {
      var rows = secEl.querySelectorAll(".oi-array-row");
      var newArr = [];
      rows.forEach(function (row) {
        var entry = {};
        var inputs = row.querySelectorAll('[data-oi-array-field]');
        inputs.forEach(function (i) {
          entry[i.getAttribute("data-oi-array-field")] = i.value || "";
        });
        newArr.push(entry);
      });
      _state.questionnaire[section.array] = newArr;
    } else {
      var obj = _state.questionnaire[sectionId] || {};
      section.fields.forEach(function (f) {
        obj[f.id] = _readFieldValueFromForm(secEl, f.id);
      });
      _state.questionnaire[sectionId] = obj;
    }
  }

  async function _saveSection(sectionId, container) {
    if (!_state.personId) return;
    _readSectionFromForm(sectionId, container);
    var saveBtn = container.querySelector(
      '[data-oi-save-section="' + sectionId + '"]'
    );
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving…";
    }
    try {
      var resp = await _putSection(_state.personId, sectionId);
      _state.dirtySections[sectionId] = false;
      _state.lastSaveAt = new Date().toISOString();
      // Refresh meta so badges update if Phase 3 wrote new bio_facts
      try {
        var fresh = await _fetchQuestionnaire(_state.personId);
        _state.meta = fresh._meta || {};
        _state.source = fresh.source || _state.source;
      } catch (_) {}
      _renderAll(container);
      _toast("Saved " + sectionId + " · " +
        (resp.bio_facts_written || 0) + " bio_facts written");
    } catch (e) {
      console.error("[operator-intake] save failed:", e);
      _toast("Save failed: " + (e.message || e), "error");
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save (retry)";
      }
    }
  }

  function _addArrayEntry(sectionId, container) {
    var section = SECTIONS.find(function (s) { return s.id === sectionId; });
    if (!section || !section.array) return;
    _readSectionFromForm(sectionId, container);
    var arr = _state.questionnaire[section.array] || [];
    if (!Array.isArray(arr)) arr = [];
    arr.push({});
    _state.questionnaire[section.array] = arr;
    _state.dirtySections[sectionId] = true;
    _renderAll(container);
  }

  function _removeArrayEntry(sectionId, idx, container) {
    var section = SECTIONS.find(function (s) { return s.id === sectionId; });
    if (!section || !section.array) return;
    _readSectionFromForm(sectionId, container);
    var arr = _state.questionnaire[section.array] || [];
    if (Array.isArray(arr) && idx >= 0 && idx < arr.length) {
      arr.splice(idx, 1);
      _state.questionnaire[section.array] = arr;
      _state.dirtySections[sectionId] = true;
      _renderAll(container);
    }
  }

  function _toast(message, level) {
    try {
      var host = document.getElementById("lvIntakeToastHost");
      if (!host) return;
      var t = document.createElement("div");
      t.className = "oi-toast oi-toast-" + (level === "error" ? "error" : "ok");
      t.textContent = message;
      host.appendChild(t);
      setTimeout(function () {
        try { host.removeChild(t); } catch (_) {}
      }, 4000);
    } catch (_) {}
  }

  // ── Public entry points ─────────────────────────────────────────

  async function refresh() {
    var container = document.getElementById("lvIntakeContainer");
    if (!container) return;
    var pid = _getCurrentPersonId();
    if (!pid) {
      _state.personId = null;
      _renderEmpty(container);
      return;
    }
    _state.personId = pid;
    _state.loading = true;
    _renderAll(container);
    try {
      var j = await _fetchQuestionnaire(pid);
      _state.questionnaire = j.questionnaire || {};
      _state.meta = j._meta || {};
      _state.source = j.source || "unknown";
      _state.dirtySections = {};
      _state.loading = false;
      _renderAll(container);
    } catch (e) {
      console.error("[operator-intake] refresh failed:", e);
      _state.loading = false;
      container.innerHTML =
        '<div class="oi-error">Failed to load intake data: ' +
        _esc(e.message || String(e)) + '</div>';
    }
  }

  function onNarratorSwitch(newPid) {
    _state.questionnaire = {};
    _state.meta = {};
    _state.source = null;
    _state.dirtySections = {};
    _state.personId = newPid || null;
    var container = document.getElementById("lvIntakeContainer");
    if (container) {
      _renderEmpty(container, newPid ? "Loading…" : "No narrator selected");
    }
    if (newPid) refresh();
  }

  function init() {
    // Patch the lvShellShowTab fallback to recognize "intake" — handled
    // automatically by the dynamic ID lookup in lvShellShowTab; this
    // function exists as a hook for any one-time setup we may need.
    return true;
  }

  // ── Export ───────────────────────────────────────────────────────

  window.OperatorIntake = {
    init: init,
    refresh: refresh,
    onNarratorSwitch: onNarratorSwitch,
    // Test surface (exposed only when explicitly enabled)
    _internal: {
      SECTIONS: SECTIONS,
      STATUS_LABELS: STATUS_LABELS,
      KNOWN_STATUSES: KNOWN_STATUSES,
      _state: _state,
      _sectionKnownCount: _sectionKnownCount,
      _statusBadgeHtml: _statusBadgeHtml,
      _sectionRollupHtml: _sectionRollupHtml,
      _esc: _esc,
    },
  };
})();
