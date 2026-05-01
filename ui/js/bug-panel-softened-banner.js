/* WO-LORI-SOFTENED-RESPONSE-01 — Bug Panel softened-mode banner.
 *
 * Polls /api/operator/safety-events/softened-state?conv_id=<active>
 * every 30s (and on Bug Panel open / window focus) for the active
 * conversation's softened state. Renders a banner card showing
 * "Softened mode active — N turns remaining" when interview_softened
 * is true.
 *
 * Per spec: NEVER narrator-visible. The banner is only mounted into
 * the Bug Panel under #lv10dBpSoftenedBanner. Operator surface only.
 *
 * Backend gate: same env flag as safety-events (HORNELORE_OPERATOR_
 * SAFETY_EVENTS=1). When off, /softened-state returns 404 and this
 * UI silently does nothing — it never logs gate-disabled chatter.
 *
 * Companion to safety-banner.js. Both share the same polling cadence
 * but distinct endpoints + rendering surfaces.
 */
(function () {
  "use strict";

  const POLL_INTERVAL_MS = 30000;
  const ENDPOINT_BASE = "/api/operator/safety-events/softened-state";
  const MOUNT_ID = "lv10dBpSoftenedBanner";

  let _timer = null;
  let _gateDisabledLogged = false;
  let _lastSoftened = null; // boolean cache

  function _activeConvId() {
    // Pull the active conversation id from window state. Falls back
    // gracefully when no session is active — banner just doesn't
    // render until one is.
    try {
      if (window.lv && window.lv.state && window.lv.state.session) {
        return window.lv.state.session.conv_id || window.lv.state.session.session_id || null;
      }
      if (window.state && window.state.session) {
        return window.state.session.conv_id || window.state.session.session_id || null;
      }
    } catch (_e) {
      // ignore
    }
    return null;
  }

  function _ensureMount() {
    let mount = document.getElementById(MOUNT_ID);
    if (mount) return mount;
    // Mount inside Bug Panel's safety banners block if it exists,
    // otherwise into the Bug Panel root. Either way, operator-only.
    const safetyBlock = document.getElementById("lv10dBpSafetyBanners");
    const bugPanel = document.getElementById("lv10dBugPanel");
    const target = safetyBlock || bugPanel;
    if (!target) return null;
    mount = document.createElement("div");
    mount.id = MOUNT_ID;
    mount.className = "lv10d-bp-softened-banner-mount";
    target.parentNode.insertBefore(mount, target.nextSibling);
    return mount;
  }

  function _render(state) {
    const mount = _ensureMount();
    if (!mount) return;
    if (!state || !state.interview_softened) {
      mount.innerHTML = "";
      mount.style.display = "none";
      return;
    }
    mount.style.display = "block";
    const remaining = Math.max(0, parseInt(state.turns_remaining || 0, 10));
    const turnCount = parseInt(state.turn_count || 0, 10);
    const until = parseInt(state.softened_until_turn || 0, 10);
    mount.innerHTML = `
      <div class="lv10d-softened-card" role="status" aria-live="polite">
        <div class="lv10d-softened-card-title">
          🛡️ Softened mode active
        </div>
        <div class="lv10d-softened-card-body">
          ${remaining} turn${remaining === 1 ? "" : "s"} remaining
          <span class="lv10d-softened-card-meta">
            (turn ${turnCount} of ${until})
          </span>
        </div>
        <div class="lv10d-softened-card-note">
          Lori is staying warm and slow. No new memory probes during
          this window. The banner will clear automatically when the
          softened window expires.
        </div>
      </div>
    `;
  }

  async function _poll() {
    const convId = _activeConvId();
    if (!convId) {
      _render(null);
      return;
    }
    try {
      const url = ENDPOINT_BASE + "?conv_id=" + encodeURIComponent(convId);
      const resp = await fetch(url, { credentials: "same-origin" });
      if (resp.status === 404) {
        if (!_gateDisabledLogged) {
          // Gate is off; quiet exit
          _gateDisabledLogged = true;
        }
        _render(null);
        return;
      }
      if (!resp.ok) {
        console.warn("[softened-banner] fetch failed:", resp.status);
        return;
      }
      const data = await resp.json();
      _render(data);
      _lastSoftened = !!(data && data.interview_softened);
      _gateDisabledLogged = false;
    } catch (e) {
      console.warn("[softened-banner] poll error:", e);
    }
  }

  function _start() {
    if (_timer) return;
    _poll();
    _timer = setInterval(_poll, POLL_INTERVAL_MS);
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

  // Manual refresh hook for ops + tests
  window.lvSoftenedBannerRefresh = _poll;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _start, { once: true });
  } else {
    _start();
  }
})();
