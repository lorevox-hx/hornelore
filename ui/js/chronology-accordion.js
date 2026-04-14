/* ═══════════════════════════════════════════════════════════════
   chronology-accordion.js — WO-CR-01 Left Chronology Accordion
   Lorevox / Hornelore 1.0

   Read-only UI: fetches merged chronology payload from the API,
   renders a collapsible decade→year→event accordion in the left
   column, and bridges clicks to the existing era navigation chain.

   Authority contract: NEVER writes to facts, timeline, questionnaire,
   archive, or any truth table.  State writes are limited to
   state.chronologyAccordion (UI display state only).

   Load order: after app.js, api.js, state.js, interview.js
═══════════════════════════════════════════════════════════════ */

/* ── DOM References ─────────────────────────────────────────── */
function _crCol()  { return document.getElementById("crAccordionCol"); }
function _crBody() { return document.getElementById("crAccordionBody"); }

/* ── Toggle expand / collapse ───────────────────────────────── */
function crToggleExpand() {
  const col = _crCol();
  if (!col) return;
  const wasCollapsed = state.chronologyAccordion.collapsed;
  state.chronologyAccordion.collapsed = !wasCollapsed;
  col.classList.toggle("cr-expanded", wasCollapsed);
}

/* ── Show / hide the accordion column ───────────────────────── */
function crShowAccordion() {
  const col = _crCol();
  if (!col) return;
  state.chronologyAccordion.visible = true;
  col.classList.add("cr-visible");
}

function crHideAccordion() {
  const col = _crCol();
  if (!col) return;
  state.chronologyAccordion.visible = false;
  col.classList.remove("cr-visible");
}

/* ── Trainer isolation ──────────────────────────────────────── */
function crCheckTrainerIsolation() {
  try {
    if (state.trainerNarrators && state.trainerNarrators.active) {
      crHideAccordion();
      return true;
    }
  } catch (_) {}
  return false;
}

/* ── Fetch payload from API ─────────────────────────────────── */
async function crFetchAccordion(personId) {
  if (!personId) return null;
  if (crCheckTrainerIsolation()) return null;

  state.chronologyAccordion.loading = true;
  state.chronologyAccordion.error = null;

  try {
    const url = API.CHRONOLOGY_ACCORDION(personId);
    const resp = await fetch(url);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const data = await resp.json();
    state.chronologyAccordion.payload = data;
    state.chronologyAccordion.loading = false;

    if (data.error === "no_dob") {
      console.log("[WO-CR-01] No DOB available — accordion empty");
      return data;
    }

    console.log(
      "[WO-CR-01] Accordion loaded: %d decades, %d world, %d personal, %d ghost",
      (data.decades || []).length,
      data.lane_counts?.world || 0,
      data.lane_counts?.personal || 0,
      data.lane_counts?.ghost || 0,
    );
    return data;
  } catch (err) {
    console.error("[WO-CR-01] Failed to load accordion:", err);
    state.chronologyAccordion.error = err.message;
    state.chronologyAccordion.loading = false;
    return null;
  }
}

/* ── Render the accordion ───────────────────────────────────── */
function crRenderAccordion(data) {
  const body = _crBody();
  if (!body) return;

  if (!data || !data.decades || data.decades.length === 0) {
    body.innerHTML = '<div style="padding:12px;color:#475569;font-size:11px;text-align:center;">No timeline data yet</div>';
    return;
  }

  let html = "";
  for (const decade of data.decades) {
    const decadeKey = String(decade.decade);
    const isOpen = !!state.chronologyAccordion.openDecades[decadeKey];
    const totalItems = decade.years.reduce((n, y) => n + y.items.length, 0);

    html += `<div class="cr-decade${isOpen ? " cr-open" : ""}" data-decade="${decadeKey}">`;
    html += `<div class="cr-decade-header" onclick="crToggleDecade('${decadeKey}')">`;
    html += `<span class="cr-decade-caret">▸</span>`;
    html += `<span>${decade.decade_label}</span>`;
    html += `<span class="cr-decade-count">${totalItems}</span>`;
    html += `</div>`;
    html += `<div class="cr-decade-body">`;

    for (const yearGroup of decade.years) {
      const yrKey = String(yearGroup.year);
      const yearOpenMap = state.chronologyAccordion.openYears[decadeKey] || {};
      const yrOpen = !!yearOpenMap[yrKey];
      const eraTag = yearGroup.era
        ? `<span class="cr-era-tag">${_crPrettyEra(yearGroup.era)}</span>`
        : "";

      html += `<div class="cr-year${yrOpen ? " cr-open" : ""}" data-year="${yrKey}">`;
      html += `<div class="cr-year-header" onclick="crToggleYear('${decadeKey}','${yrKey}')">`;
      html += `<span class="cr-year-caret">▸</span>`;
      html += `<span>${yrKey}</span>${eraTag}`;
      html += `</div>`;
      html += `<div class="cr-year-body">`;

      for (const item of yearGroup.items) {
        const lane = item.lane || "world";
        const clickAttr = (lane === "personal" || lane === "ghost")
          ? ` onclick="crJumpToEra('${yearGroup.era || ""}')" `
          : "";
        html += `<div class="cr-event" data-lane="${lane}"${clickAttr}>`;
        html += _crEscapeHtml(item.label);
        html += `</div>`;
      }

      html += `</div></div>`; // /cr-year-body /cr-year
    }

    html += `</div></div>`; // /cr-decade-body /cr-decade
  }

  body.innerHTML = html;
}

/* ── Toggle decade open/close ───────────────────────────────── */
function crToggleDecade(decadeKey) {
  const wasOpen = !!state.chronologyAccordion.openDecades[decadeKey];
  state.chronologyAccordion.openDecades[decadeKey] = !wasOpen;

  const el = _crBody()?.querySelector(`.cr-decade[data-decade="${decadeKey}"]`);
  if (el) el.classList.toggle("cr-open", !wasOpen);
}

/* ── Toggle year open/close ─────────────────────────────────── */
function crToggleYear(decadeKey, yearKey) {
  if (!state.chronologyAccordion.openYears[decadeKey]) {
    state.chronologyAccordion.openYears[decadeKey] = {};
  }
  const wasOpen = !!state.chronologyAccordion.openYears[decadeKey][yearKey];
  state.chronologyAccordion.openYears[decadeKey][yearKey] = !wasOpen;

  const el = _crBody()?.querySelector(`.cr-year[data-year="${yearKey}"]`);
  if (el) el.classList.toggle("cr-open", !wasOpen);

  // Auto-expand parent decade if not already open
  if (!wasOpen && !state.chronologyAccordion.openDecades[decadeKey]) {
    crToggleDecade(decadeKey);
  }
}

/* ── Navigation bridge ──────────────────────────────────────── */
function crJumpToEra(eraLabel) {
  if (!eraLabel) return;

  // Use the same navigation chain as roadmap clicks and life-map
  if (typeof setEra === "function") setEra(eraLabel);
  if (typeof setPass === "function") setPass("pass2a");
  if (typeof update71RuntimeUI === "function") update71RuntimeUI();
  if (typeof renderRoadmap === "function") renderRoadmap();
  if (typeof renderInterview === "function") renderInterview();
  if (typeof updateContextTriggers === "function") updateContextTriggers();
  if (typeof showTab === "function") showTab("interview");

  console.log("[WO-CR-01] Navigation bridge → era:", eraLabel);
}

/* ── Utilities ──────────────────────────────────────────────── */
function _crPrettyEra(label) {
  if (!label) return "";
  return String(label)
    .replaceAll("_", " ")
    .replace(/\b\w/g, m => m.toUpperCase());
}

function _crEscapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text || "";
  return d.innerHTML;
}

/* ── Init: load accordion on narrator switch ────────────────── */
async function crInitAccordion() {
  if (crCheckTrainerIsolation()) return;

  const pid = state.person_id;
  if (!pid) {
    crHideAccordion();
    return;
  }

  const data = await crFetchAccordion(pid);
  if (!data || data.error === "no_dob") {
    crHideAccordion();
    return;
  }

  crRenderAccordion(data);
  crShowAccordion();
}

/* ── Hook into narrator load cycle ──────────────────────────── */
// Called after narrator is fully loaded.  Hooks are set up in the
// inline <script> block in hornelore1.0.html that wraps the
// existing window.onload.
//
// We expose crInitAccordion globally so it can be called from:
//   1. Narrator switch completion
//   2. Timeline spine initialization
//   3. After identity onboarding completes (DOB captured)
window.crInitAccordion = crInitAccordion;
window.crHideAccordion = crHideAccordion;
window.crShowAccordion = crShowAccordion;
window.crCheckTrainerIsolation = crCheckTrainerIsolation;
window.crToggleExpand = crToggleExpand;
window.crToggleDecade = crToggleDecade;
window.crToggleYear = crToggleYear;
window.crJumpToEra = crJumpToEra;
