/* WO-OPERATOR-PREFLIGHT-PANEL-01 (2026-05-10) — minimal Operator Preflight.
 *
 * Per Chris's 2026-05-10 directive: "Add a minimal Operator Preflight
 * panel: narrator_language_mode dropdown + narrator_voice_overlay
 * dropdown + verify/save button + display current values + follow-up
 * bank count + floor-control warning."
 *
 * Lives inside the existing Bug Panel (operator-only surface). NEVER
 * narrator-visible. Reads the active narrator's profile_json via
 * GET /api/profiles/{pid}, lets the operator change two fields, and
 * writes them back via PATCH /api/profiles/{pid}.
 *
 * Kent / Janice readiness checklist:
 *   - Language mode: english / spanish / mixed
 *   - Voice overlay: default / adult_competence / hearth_sensory /
 *     shield_protected
 *   - Save → PATCH → re-fetch → green "Saved" flash for 2s
 *   - Banked-question count for the active session (gated; "—" when
 *     HORNELORE_OPERATOR_FOLLOWUP_BANK=0)
 *   - Floor-control reminder text (no UI guard yet — operator
 *     discipline only until FE sends turn_final/floor_state)
 *
 * Backend endpoints used:
 *   GET   /api/profiles/{person_id}                 — read
 *   PATCH /api/profiles/{person_id}  body {patch:…} — merge-update
 *   GET   /api/operator/followup-bank/session/{conv_id}/all (gated)
 *
 * Polling: refresh on Bug Panel open + window focus + visibility
 * change + manual Refresh button + post-save. No background timer
 * (the values are static between sessions; no need to burn CPU).
 *
 * Failure mode is QUIET: when the active narrator/conv is missing,
 * the widget displays "no active narrator" and the dropdowns are
 * disabled. PATCH errors surface in the action row but never break
 * the panel.
 */
(function () {
  "use strict";

  const _O = (typeof ORIGIN !== "undefined" && ORIGIN) || "http://localhost:8000";
  const PROFILE_GET = (pid) => `${_O}/api/profiles/${encodeURIComponent(pid)}`;
  const PROFILE_PATCH = (pid) => `${_O}/api/profiles/${encodeURIComponent(pid)}`;
  const BANK_ALL = (sid) =>
    `${_O}/api/operator/followup-bank/session/${encodeURIComponent(sid)}/all`;

  const LANG_OPTIONS = [
    { value: "", label: "(unset — falls back to looks_spanish heuristic)" },
    { value: "english", label: "English (locked)" },
    { value: "spanish", label: "Spanish (locked)" },
    { value: "mixed", label: "Mixed (per-turn detection)" },
  ];

  const OVERLAY_OPTIONS = [
    { value: "", label: "(unset — defaults to default)" },
    { value: "default", label: "default — story-weighted + action/mechanism" },
    { value: "adult_competence", label: "adult_competence — Kent / military / labor" },
    { value: "hearth_sensory", label: "hearth_sensory — Janice / kitchen / domestic" },
    { value: "shield_protected", label: "shield_protected — sensitive disclosure" },
  ];

  let _bankGateOff = false;
  let _saving = false;

  // ── Helpers ───────────────────────────────────────────────────────────────

  function _esc(s) {
    if (s == null) return "";
    const div = document.createElement("div");
    div.textContent = String(s);
    return div.innerHTML;
  }

  function _activePersonId() {
    try {
      if (typeof state !== "undefined" && state && state.person_id) {
        return String(state.person_id);
      }
    } catch (_) { /* ignore */ }
    return null;
  }

  function _activeConvId() {
    try {
      if (typeof state !== "undefined" && state && state.chat && state.chat.conv_id) {
        return String(state.chat.conv_id);
      }
    } catch (_) { /* ignore */ }
    return null;
  }

  function _narratorLabel() {
    try {
      if (typeof state !== "undefined" && state && state.session) {
        return (
          state.session.narratorName
          || state.session.preferredName
          || state.session.fullName
          || "(unnamed)"
        );
      }
    } catch (_) { /* ignore */ }
    return "(unnamed)";
  }

  // ── Render ────────────────────────────────────────────────────────────────

  function _mount() {
    return document.getElementById("lv10dBpPreflight");
  }

  function _renderDisabled(reasonHtml) {
    const m = _mount();
    if (!m) return;
    m.innerHTML = `
      <div class="bp-preflight bp-preflight-disabled">
        <div class="bp-preflight-header">
          <span class="bp-preflight-title">Operator Preflight</span>
          <span class="bp-preflight-status bp-preflight-status-idle">idle</span>
        </div>
        <div class="bp-preflight-empty">${reasonHtml}</div>
      </div>
    `;
  }

  function _renderSelect(id, options, currentValue) {
    const opts = options.map((o) => {
      const sel = (o.value === (currentValue || "")) ? "selected" : "";
      return `<option value="${_esc(o.value)}" ${sel}>${_esc(o.label)}</option>`;
    }).join("");
    return `<select id="${id}" class="bp-preflight-select">${opts}</select>`;
  }

  function _render(profilePayload, bankCount) {
    const m = _mount();
    if (!m) return;
    const profile = (profilePayload && profilePayload.profile) || {};
    const slmCurrent = profile.session_language_mode
      || (profile.locale && profile.locale.session_language_mode)
      || "";
    const ovlCurrent = profile.narrator_voice_overlay
      || (profile.locale && profile.locale.narrator_voice_overlay)
      || "";
    const updatedAt = profilePayload && profilePayload.updated_at
      ? profilePayload.updated_at
      : "—";
    const source = profilePayload && profilePayload.source
      ? profilePayload.source
      : "legacy";
    const bankCountDisplay = (bankCount == null) ? "—" : String(bankCount);
    const pid = _activePersonId() || "—";
    const sid = _activeConvId() || "—";
    const narrator = _narratorLabel();

    m.innerHTML = `
      <div class="bp-preflight">
        <div class="bp-preflight-header">
          <span class="bp-preflight-title">Operator Preflight</span>
          <span class="bp-preflight-status bp-preflight-status-ready">active</span>
        </div>

        <div class="bp-preflight-meta">
          <div class="bp-preflight-meta-row"><span class="bp-preflight-label">Narrator</span><span class="bp-preflight-value">${_esc(narrator)}</span></div>
          <div class="bp-preflight-meta-row"><span class="bp-preflight-label">person_id</span><span class="bp-preflight-value bp-preflight-mono">${_esc(pid)}</span></div>
          <div class="bp-preflight-meta-row"><span class="bp-preflight-label">conv_id</span><span class="bp-preflight-value bp-preflight-mono">${_esc(sid)}</span></div>
          <div class="bp-preflight-meta-row"><span class="bp-preflight-label">profile updated</span><span class="bp-preflight-value">${_esc(updatedAt)}</span></div>
          <div class="bp-preflight-meta-row"><span class="bp-preflight-label">profile source</span><span class="bp-preflight-value">${_esc(source)}</span></div>
        </div>

        <div class="bp-preflight-form">
          <label class="bp-preflight-fieldlabel" for="bpPreflightLang">
            Session language mode
            <span class="bp-preflight-hint">profile_json.session_language_mode — locks Lori's reply language. Currently ${_esc(slmCurrent || "(unset)")}.</span>
          </label>
          ${_renderSelect("bpPreflightLang", LANG_OPTIONS, slmCurrent)}

          <label class="bp-preflight-fieldlabel" for="bpPreflightOverlay">
            Narrator voice overlay
            <span class="bp-preflight-hint">profile_json.narrator_voice_overlay — controls patience-layer prioritization. Currently ${_esc(ovlCurrent || "(unset)")}.</span>
          </label>
          ${_renderSelect("bpPreflightOverlay", OVERLAY_OPTIONS, ovlCurrent)}

          <div class="bp-preflight-actions">
            <button type="button" class="bp-preflight-btn bp-preflight-btn-primary" data-action="save"${_saving ? " disabled" : ""}>
              ${_saving ? "Saving…" : "Verify &amp; Save"}
            </button>
            <button type="button" class="bp-preflight-btn" data-action="refresh">Refresh</button>
            <span class="bp-preflight-feedback" id="bpPreflightFeedback"></span>
          </div>
        </div>

        <div class="bp-preflight-bank">
          <span class="bp-preflight-bank-label">Banked follow-up questions (this session)</span>
          <span class="bp-preflight-bank-count">${_esc(bankCountDisplay)}</span>
          ${_bankGateOff ? '<span class="bp-preflight-bank-note">(gate off — set HORNELORE_OPERATOR_FOLLOWUP_BANK=1)</span>' : ""}
        </div>

        <div class="bp-preflight-floor">
          <strong>Floor-control reminder.</strong> Pressing Send releases
          the narrator's floor — every Send dispatches a full LLM turn.
          <em>Do not press Send until the narrator finishes the chapter.</em>
          The FE does not yet send <code>turn_final</code> or
          <code>floor_state</code>; backend buffer-mode is dormant. Operator
          discipline is the only floor protection today.
        </div>
      </div>
    `;
    _wireActions();
  }

  function _wireActions() {
    const m = _mount();
    if (!m) return;
    const save = m.querySelector('[data-action="save"]');
    if (save) save.addEventListener("click", _onSave, { once: true });
    const refresh = m.querySelector('[data-action="refresh"]');
    if (refresh) refresh.addEventListener("click", _poll, { once: true });
  }

  // ── Network ───────────────────────────────────────────────────────────────

  async function _fetchProfile(pid) {
    try {
      const resp = await fetch(PROFILE_GET(pid));
      if (!resp.ok) {
        console.warn("[preflight] GET profile failed:", resp.status);
        return null;
      }
      return await resp.json();
    } catch (e) {
      console.warn("[preflight] GET profile error:", e);
      return null;
    }
  }

  async function _fetchBankCount(sid) {
    try {
      const resp = await fetch(BANK_ALL(sid));
      if (resp.status === 404) {
        // Gate is off (HORNELORE_OPERATOR_FOLLOWUP_BANK=0). Quiet.
        _bankGateOff = true;
        return null;
      }
      if (!resp.ok) {
        console.warn("[preflight] bank fetch failed:", resp.status);
        return null;
      }
      _bankGateOff = false;
      const j = await resp.json();
      return Number.isFinite(j.count) ? j.count : (Array.isArray(j.questions) ? j.questions.length : null);
    } catch (e) {
      console.warn("[preflight] bank fetch error:", e);
      return null;
    }
  }

  async function _patchProfile(pid, patch) {
    const resp = await fetch(PROFILE_PATCH(pid), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patch }),
    });
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status} ${text || ""}`.trim());
    }
    return await resp.json();
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  async function _onSave() {
    if (_saving) return;
    const pid = _activePersonId();
    if (!pid) {
      _flashFeedback("No active narrator", "error");
      return;
    }
    const langSel = document.getElementById("bpPreflightLang");
    const ovlSel = document.getElementById("bpPreflightOverlay");
    if (!langSel || !ovlSel) return;
    const patch = {};
    if (langSel.value) {
      patch.session_language_mode = langSel.value;
    } else {
      // Unset is intentionally allowed — clear the field so the
      // backend falls back to looks_spanish heuristic.
      patch.session_language_mode = null;
    }
    if (ovlSel.value) {
      patch.narrator_voice_overlay = ovlSel.value;
    } else {
      patch.narrator_voice_overlay = null;
    }
    _saving = true;
    _flashFeedback("Saving…", "info");
    try {
      await _patchProfile(pid, patch);
      _saving = false;
      _flashFeedback("Saved ✓", "ok");
      console.log("[preflight] saved profile patch:", patch);
      // Re-fetch + re-render so the displayed "current value" lines
      // reflect the new state.
      await _poll();
    } catch (e) {
      _saving = false;
      _flashFeedback("Save failed: " + (e && e.message ? e.message : e), "error");
    }
  }

  function _flashFeedback(msg, tone) {
    const el = document.getElementById("bpPreflightFeedback");
    if (!el) return;
    el.textContent = msg;
    el.className = "bp-preflight-feedback bp-preflight-feedback-" + (tone || "info");
    if (tone === "ok") {
      setTimeout(() => {
        if (el && el.textContent === msg) {
          el.textContent = "";
          el.className = "bp-preflight-feedback";
        }
      }, 2400);
    }
  }

  // ── Polling ───────────────────────────────────────────────────────────────

  async function _poll() {
    const pid = _activePersonId();
    if (!pid) {
      _renderDisabled(
        'No active narrator. Select a narrator from the main UI to '
        + 'enable preflight.'
      );
      return;
    }
    const sid = _activeConvId();
    const profile = await _fetchProfile(pid);
    let bankCount = null;
    if (sid) {
      bankCount = await _fetchBankCount(sid);
    }
    if (!profile) {
      _renderDisabled(
        'Could not load profile for <code>' + _esc(pid) + '</code>. '
        + 'Backend may be down or HF cache cold.'
      );
      return;
    }
    _render(profile, bankCount);
  }

  function _start() {
    _poll();
    window.addEventListener("focus", _poll, false);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) _poll();
    }, false);
    const panel = document.getElementById("lv10dBugPanel");
    if (panel && typeof panel.addEventListener === "function") {
      panel.addEventListener("toggle", (e) => {
        if (e && e.newState === "open") _poll();
      }, false);
    }
  }

  // Manual refresh hook for ops that want to repoll on demand.
  window.lvPreflightRefresh = _poll;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _start, { once: true });
  } else {
    _start();
  }
})();
