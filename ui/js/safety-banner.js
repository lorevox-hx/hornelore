/* WO-LORI-SAFETY-INTEGRATION-01 Phase 3b — Bug Panel safety banner UI.
 *
 * Polls /api/operator/safety-events for unacknowledged events and
 * renders banner cards inside #lv10dBpSafetyBanners (mounted in the
 * Bug Panel OPERATOR TEST TOOLS section). Acknowledge button fires
 * POST /api/operator/safety-events/{id}/acknowledge and removes the
 * card optimistically; if the POST 404s or fails, the next poll
 * restores the card.
 *
 * Per spec: NEVER narrator-visible. NO scores. NO severity ranks.
 * NO longitudinal trends. Each card surfaces:
 *    - category (e.g. "suicidal_ideation", "distress_call")
 *    - matched_phrase (what the regex matched, ≤60 chars)
 *    - turn_excerpt (≤200 chars of narrator's message for context)
 *    - narrator + session + relative time
 *
 * Polling cadence:
 *    - 30s timer while Bug Panel is open (or always running but only
 *      DOM-active when panel is mounted; the popover toggles `open`).
 *    - On Bug Panel opening (popovertoggle) + window focus + visibility-
 *      change events, immediate refresh.
 *    - On 404 from the count endpoint (HORNELORE_OPERATOR_SAFETY_EVENTS=0),
 *      the banner cards stay empty and we don't spam the console.
 *
 * Backend gate: HORNELORE_OPERATOR_SAFETY_EVENTS=1 in .env. When off,
 * /api/operator/safety-events* returns 404 and this UI silently does
 * nothing.
 */
(function () {
  "use strict";

  const POLL_INTERVAL_MS = 30 * 1000; // 30 seconds
  const COUNT_ENDPOINT = "/api/operator/safety-events/count";
  const LIST_ENDPOINT = "/api/operator/safety-events";
  const ACK_ENDPOINT = "/api/operator/safety-events"; // POST /{id}/acknowledge

  let _timer = null;
  let _lastCount = -1; // -1 = never polled; tracks transitions
  let _gateDisabledLogged = false; // log "gate off" only once per session

  /**
   * Format created_at ISO timestamp as a relative-time hint
   * ("3m ago", "1h ago", "2d ago"). Operator wants the gist, not a
   * precise stamp; full ISO is in the data attribute for hover.
   */
  function _relTime(iso) {
    if (!iso) return "?";
    try {
      const t = new Date(iso).getTime();
      if (!t || isNaN(t)) return "?";
      const seconds = Math.max(0, Math.floor((Date.now() - t) / 1000));
      if (seconds < 60) return `${seconds}s ago`;
      const minutes = Math.floor(seconds / 60);
      if (minutes < 60) return `${minutes}m ago`;
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return `${hours}h ago`;
      const days = Math.floor(hours / 24);
      return `${days}d ago`;
    } catch (_) {
      return "?";
    }
  }

  function _esc(s) {
    if (s == null) return "";
    const div = document.createElement("div");
    div.textContent = String(s);
    return div.innerHTML;
  }

  /**
   * Render the banner card stack inside the mount point. If no
   * unacked events, the banner area collapses to an empty + dim
   * placeholder line.
   */
  function _render(events) {
    const mount = document.getElementById("lv10dBpSafetyBanners");
    if (!mount) return;

    if (!events || events.length === 0) {
      mount.innerHTML = `
        <div class="safety-banner-empty">
          No unacknowledged safety events.
        </div>
      `;
      return;
    }

    const cards = events.map(_renderCard).join("");
    mount.innerHTML = `
      <div class="safety-banner-header">
        ⚠ Safety events — ${events.length} unacknowledged
      </div>
      ${cards}
    `;

    // Wire acknowledge buttons
    mount.querySelectorAll("[data-safety-ack-id]").forEach((btn) => {
      btn.addEventListener("click", _onAckClick);
    });
  }

  function _renderCard(ev) {
    const id = _esc(ev.id || "");
    const category = _esc(ev.category || "uncategorized");
    const matched = _esc(ev.matched_phrase || "");
    const excerpt = _esc(ev.turn_excerpt || "");
    const personId = _esc(ev.person_id || "(none)");
    const sessionId = _esc((ev.session_id || "").slice(0, 12));
    const created = _esc(ev.created_at || "");
    const rel = _esc(_relTime(ev.created_at));

    return `
      <div class="safety-banner-card" data-safety-event-id="${id}">
        <div class="safety-banner-card-row1">
          <span class="safety-banner-category">${category}</span>
          <span class="safety-banner-time" title="${created}">${rel}</span>
        </div>
        ${matched ? `<div class="safety-banner-matched">matched: <em>${matched}</em></div>` : ""}
        ${excerpt ? `<div class="safety-banner-excerpt">${excerpt}</div>` : ""}
        <div class="safety-banner-card-row2">
          <span class="safety-banner-meta">narrator: ${personId} · session: ${sessionId}</span>
          <button type="button" class="safety-banner-ack-btn"
                  data-safety-ack-id="${id}">
            Acknowledge
          </button>
        </div>
      </div>
    `;
  }

  async function _onAckClick(ev) {
    const btn = ev.currentTarget;
    const id = btn.getAttribute("data-safety-ack-id");
    if (!id) return;

    btn.disabled = true;
    btn.textContent = "Acknowledging…";

    try {
      const resp = await fetch(`${ACK_ENDPOINT}/${encodeURIComponent(id)}/acknowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ acknowledged_by: "operator" }),
      });

      if (resp.ok) {
        // Optimistic remove — next poll will reconcile if needed
        const card = btn.closest(".safety-banner-card");
        if (card) card.remove();
        // Trigger immediate re-poll to update count badge
        _poll();
      } else if (resp.status === 404) {
        // Backend gate flipped off mid-session, OR event no longer
        // exists. Either way, refresh from server.
        _poll();
      } else {
        btn.disabled = false;
        btn.textContent = "Acknowledge";
        console.warn("[safety-banner] ack POST failed:", resp.status);
      }
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Acknowledge";
      console.warn("[safety-banner] ack POST error:", e);
    }
  }

  async function _poll() {
    try {
      const resp = await fetch(`${LIST_ENDPOINT}?unacked_only=true&limit=10`, {
        method: "GET",
        headers: { "Accept": "application/json" },
      });

      if (resp.status === 404) {
        // Backend gate is off (HORNELORE_OPERATOR_SAFETY_EVENTS=0) OR
        // the route isn't registered. Either way, render the dim
        // "feature off" placeholder once and stop spamming.
        if (!_gateDisabledLogged) {
          console.log(
            "[safety-banner] /api/operator/safety-events returns 404 — set HORNELORE_OPERATOR_SAFETY_EVENTS=1 in .env to enable the operator banner."
          );
          _gateDisabledLogged = true;
        }
        const mount = document.getElementById("lv10dBpSafetyBanners");
        if (mount) {
          mount.innerHTML = `
            <div class="safety-banner-empty safety-banner-gate-off">
              Safety event banner disabled (HORNELORE_OPERATOR_SAFETY_EVENTS=0).
              Set to 1 in <code>.env</code> + restart stack to enable.
            </div>
          `;
        }
        return;
      }

      if (!resp.ok) {
        console.warn("[safety-banner] list fetch failed:", resp.status);
        return;
      }

      const data = await resp.json();
      const events = (data && data.events) || [];
      _render(events);

      // Reset gate flag in case operator flipped HORNELORE_OPERATOR_SAFETY_EVENTS=1 mid-session
      _gateDisabledLogged = false;
      _lastCount = events.length;
    } catch (e) {
      console.warn("[safety-banner] poll error:", e);
    }
  }

  function _start() {
    if (_timer) return;
    _poll();
    _timer = setInterval(_poll, POLL_INTERVAL_MS);
    // Re-poll when window regains focus / becomes visible
    window.addEventListener("focus", _poll, false);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) _poll();
    }, false);
    // Re-poll when the Bug Panel popover opens
    const panel = document.getElementById("lv10dBugPanel");
    if (panel && typeof panel.addEventListener === "function") {
      panel.addEventListener("toggle", (e) => {
        if (e && e.newState === "open") _poll();
      }, false);
    }
  }

  // Expose a manual hook for the Bug Panel's existing 2s refresh cycle
  // and for ops who want to re-poll on demand.
  window.lvSafetyBannerRefresh = _poll;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _start, { once: true });
  } else {
    _start();
  }
})();
