/* WO-BUG-PANEL-EVAL-HARNESS-01 Phase 1 — Bug Panel Eval Harness UI.
 *
 * Operator cockpit: 4 status cards (Extractor / Lori Behavior / Safety
 * / Story Surfaces) backed by /api/operator/eval-harness/summary. Polls
 * on Bug Panel open + Refresh button + 60s timer while panel is visible.
 *
 * Per spec: read-only in Phase 1. No run buttons. NEVER narrator-visible
 * (Bug Panel is operator-tab only).
 *
 * Backend gate: HORNELORE_OPERATOR_EVAL_HARNESS=1 in .env. When off,
 * /api/operator/eval-harness/* returns 404 and this UI shows a quiet
 * "feature disabled" placeholder.
 */
(function () {
  "use strict";

  const POLL_INTERVAL_MS = 60 * 1000;
  const SUMMARY_ENDPOINT = "/api/operator/eval-harness/summary";

  let _timer = null;
  let _gateDisabledLogged = false;

  const STATUS_LABELS = {
    pass: "PASS",
    warn: "WARN",
    fail: "FAIL",
    missing: "MISSING",
    stale: "STALE",
    ready: "READY",
  };

  function _esc(s) {
    if (s == null) return "";
    const div = document.createElement("div");
    div.textContent = String(s);
    return div.innerHTML;
  }

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

  function _pct(x) {
    if (x == null || isNaN(x)) return "—";
    return (Number(x) * 100).toFixed(1) + "%";
  }

  function _renderExtractorCard(card) {
    const status = card.status || "missing";
    const tag = card.eval_tag || (card.report_name || "").replace("master_loop01_", "");
    const sha = card.git_sha ? card.git_sha.substring(0, 7) : "—";
    const dirty = card.git_dirty ? " <span class=\"eval-card-dirty\">dirty</span>" : "";
    const pct = _pct(card.pass_rate);
    const passed = card.passed != null ? card.passed : "—";
    const total = card.total_cases != null ? card.total_cases : "—";
    const v3 = `${card.contract_v3_passed ?? "—"}/${card.contract_v3_total ?? "—"}`;
    const v2 = `${card.contract_v2_passed ?? "—"}/${card.contract_v2_total ?? "—"}`;
    const mnw = _pct(card.must_not_write_violation_rate);
    const ranAt = card.report_mtime ? _relTime(card.report_mtime) : "?";
    const fullStamp = card.report_mtime || card.started_at || "";

    const topFailures = card.top_failures || {};
    const topFailLines = Object.entries(topFailures).slice(0, 5)
      .map(([k, v]) => `<span class="eval-card-failrow"><code>${_esc(k)}</code> · ${_esc(v)}</span>`)
      .join("");

    const noteBlock = card.note
      ? `<div class="eval-card-note">${_esc(card.note)}</div>`
      : (card.error ? `<div class="eval-card-error">${_esc(card.error)}</div>` : "");

    return `
      <div class="eval-card eval-card-${status}" data-eval-lane="extractor">
        <div class="eval-card-header">
          <span class="eval-card-status">${STATUS_LABELS[status] || status.toUpperCase()}</span>
          <span class="eval-card-title">Extractor master eval</span>
          <span class="eval-card-tag">${_esc(tag || "—")}</span>
        </div>
        ${status === "missing" ? '<div class="eval-card-note">No master_loop01_*.json on disk yet — run an eval to populate.</div>' : ""}
        ${status !== "missing" ? `
          <div class="eval-card-row">
            <span class="eval-card-metric"><strong>${_esc(passed)}/${_esc(total)}</strong> · ${_esc(pct)}</span>
            <span class="eval-card-metric">v3: ${_esc(v3)}</span>
            <span class="eval-card-metric">v2: ${_esc(v2)}</span>
            <span class="eval-card-metric">mnw: ${_esc(mnw)}</span>
          </div>
          <div class="eval-card-meta">
            <span title="${_esc(fullStamp)}">ran ${_esc(ranAt)}</span>
            <span class="eval-card-sha">${_esc(sha)}${dirty}</span>
          </div>
        ` : ""}
        ${topFailLines ? `<div class="eval-card-fails"><span class="eval-card-fails-label">Top failure categories:</span>${topFailLines}</div>` : ""}
        ${noteBlock}
        <div class="eval-card-actions">
          <button type="button" class="eval-card-btn" data-action="refresh">Refresh</button>
          <button type="button" class="eval-card-btn" data-action="copy-cmd"
                  data-cmd="${_esc(card.run_command || "")}">Copy run cmd</button>
          ${card.report_path ? `<span class="eval-card-path"><code>${_esc(card.report_path)}</code></span>` : ""}
        </div>
      </div>
    `;
  }

  function _renderBehaviorCard(card) {
    const status = card.status || "missing";
    const ranAt = card.report_mtime ? _relTime(card.report_mtime) : "—";
    const total = card.total ?? 0;
    const passed = card.passed ?? 0;
    const failed = card.failed ?? 0;

    const byLane = card.by_lane || {};
    const laneRows = Object.entries(byLane)
      .map(([lane, d]) => `<span class="eval-card-failrow"><code>${_esc(lane)}</code> · ${_esc(d.passed)}/${_esc(d.total)}</span>`)
      .join("");

    return `
      <div class="eval-card eval-card-${status}" data-eval-lane="lori_behavior">
        <div class="eval-card-header">
          <span class="eval-card-status">${STATUS_LABELS[status] || status.toUpperCase()}</span>
          <span class="eval-card-title">Lori behavior harness</span>
          <span class="eval-card-tag">latest.json</span>
        </div>
        ${status === "missing" ? '<div class="eval-card-note">Harness has not been run yet — see run command below.</div>' : ""}
        ${status !== "missing" ? `
          <div class="eval-card-row">
            <span class="eval-card-metric"><strong>${_esc(passed)}/${_esc(total)}</strong> passed</span>
            ${failed > 0 ? `<span class="eval-card-metric">${_esc(failed)} failed</span>` : ""}
            <span class="eval-card-metric" title="${_esc(card.report_mtime || "")}">ran ${_esc(ranAt)}</span>
          </div>
        ` : ""}
        ${laneRows ? `<div class="eval-card-fails"><span class="eval-card-fails-label">Per lane:</span>${laneRows}</div>` : ""}
        ${card.error ? `<div class="eval-card-error">${_esc(card.error)}</div>` : ""}
        <div class="eval-card-actions">
          <button type="button" class="eval-card-btn" data-action="refresh">Refresh</button>
          <button type="button" class="eval-card-btn" data-action="copy-cmd"
                  data-cmd="${_esc(card.run_command || "")}">Copy run cmd</button>
          ${card.report_path ? `<span class="eval-card-path"><code>${_esc(card.report_path)}</code></span>` : ""}
        </div>
      </div>
    `;
  }

  function _renderSafetyCard(card) {
    const status = card.status || "ready";
    const unacked = card.unacknowledged_events ?? 0;

    return `
      <div class="eval-card eval-card-${status}" data-eval-lane="safety">
        <div class="eval-card-header">
          <span class="eval-card-status">${STATUS_LABELS[status] || status.toUpperCase()}</span>
          <span class="eval-card-title">Safety response infrastructure</span>
          <span class="eval-card-tag">db: safety_events</span>
        </div>
        <div class="eval-card-row">
          <span class="eval-card-metric"><strong>${_esc(unacked)}</strong> unacknowledged events</span>
        </div>
        ${card.note ? `<div class="eval-card-note">${_esc(card.note)}</div>` : ""}
        ${card.error ? `<div class="eval-card-error">${_esc(card.error)}</div>` : ""}
        <div class="eval-card-actions">
          <button type="button" class="eval-card-btn" data-action="refresh">Refresh</button>
          <button type="button" class="eval-card-btn" data-action="copy-cmd"
                  data-cmd="${_esc(card.run_command || "")}">Copy run cmd</button>
        </div>
      </div>
    `;
  }

  function _renderStoryCard(card) {
    const status = card.status || "missing";
    const ranAt = card.report_mtime ? _relTime(card.report_mtime) : "—";
    return `
      <div class="eval-card eval-card-${status}" data-eval-lane="story_surfaces">
        <div class="eval-card-header">
          <span class="eval-card-status">${STATUS_LABELS[status] || status.toUpperCase()}</span>
          <span class="eval-card-title">Story surfaces (Playwright)</span>
          <span class="eval-card-tag">playwright-report/</span>
        </div>
        ${status === "missing" ? '<div class="eval-card-note">No playwright-report/ on disk — run the e2e probe to populate.</div>' : ""}
        ${status !== "missing" ? `
          <div class="eval-card-row">
            <span class="eval-card-metric" title="${_esc(card.report_mtime || "")}">ran ${_esc(ranAt)}</span>
          </div>
        ` : ""}
        ${card.note ? `<div class="eval-card-note">${_esc(card.note)}</div>` : ""}
        <div class="eval-card-actions">
          <button type="button" class="eval-card-btn" data-action="refresh">Refresh</button>
          <button type="button" class="eval-card-btn" data-action="copy-cmd"
                  data-cmd="${_esc(card.run_command || "")}">Copy run cmd</button>
        </div>
      </div>
    `;
  }

  function _renderCrash(crash) {
    if (!crash) return "";
    return `
      <div class="eval-crash">
        <div class="eval-crash-title">⚠ Recent eval crash detected in api.log</div>
        <div class="eval-crash-pattern"><code>${_esc(crash.matched_pattern || "")}</code></div>
        <div class="eval-crash-context"><pre>${_esc((crash.context || "").slice(0, 1200))}</pre></div>
        <div class="eval-crash-source">from <code>${_esc(crash.from_log || "")}</code></div>
      </div>
    `;
  }

  function _render(payload) {
    const mount = document.getElementById("lv10dBpEvalHarness");
    if (!mount) return;
    if (!payload || !payload.cards) {
      mount.innerHTML = `<div class="eval-empty">Eval Harness data unavailable.</div>`;
      return;
    }
    const cardsHtml = payload.cards.map((card) => {
      switch (card.lane) {
        case "extractor": return _renderExtractorCard(card);
        case "lori_behavior": return _renderBehaviorCard(card);
        case "safety": return _renderSafetyCard(card);
        case "story_surfaces": return _renderStoryCard(card);
        default: return "";
      }
    }).join("");
    const generatedAt = payload.generated_at ? `as of ${_relTime(payload.generated_at)}` : "";
    mount.innerHTML = `
      <div class="eval-harness-header">
        <span>Eval Harness — read-only cockpit</span>
        <span class="eval-harness-generated">${_esc(generatedAt)}</span>
      </div>
      ${_renderCrash(payload.recent_crash)}
      <div class="eval-cards">${cardsHtml}</div>
    `;
    mount.querySelectorAll('[data-action="refresh"]').forEach((btn) => {
      btn.addEventListener("click", _poll);
    });
    mount.querySelectorAll('[data-action="copy-cmd"]').forEach((btn) => {
      btn.addEventListener("click", _onCopyClick);
    });
  }

  async function _onCopyClick(ev) {
    const btn = ev.currentTarget;
    const cmd = btn.getAttribute("data-cmd") || "";
    if (!cmd) return;
    try {
      await navigator.clipboard.writeText(cmd);
      const orig = btn.textContent;
      btn.textContent = "✓ Copied";
      setTimeout(() => { btn.textContent = orig; }, 1500);
    } catch (e) {
      console.warn("[eval-harness] clipboard copy failed:", e);
      btn.textContent = "(copy unavailable — see console)";
      console.log("[eval-harness] run command:\n" + cmd);
    }
  }

  async function _poll() {
    const mount = document.getElementById("lv10dBpEvalHarness");
    if (!mount) return;
    try {
      const resp = await fetch(SUMMARY_ENDPOINT, {
        method: "GET",
        headers: { "Accept": "application/json" },
      });
      if (resp.status === 404) {
        if (!_gateDisabledLogged) {
          console.log(
            "[eval-harness] /api/operator/eval-harness/summary returns 404 — set HORNELORE_OPERATOR_EVAL_HARNESS=1 in .env + restart stack to enable."
          );
          _gateDisabledLogged = true;
        }
        mount.innerHTML = `
          <div class="eval-empty eval-empty-gate-off">
            Eval Harness disabled (HORNELORE_OPERATOR_EVAL_HARNESS=0).
            Set to 1 in <code>.env</code> + restart stack to enable.
          </div>
        `;
        return;
      }
      if (!resp.ok) {
        console.warn("[eval-harness] summary fetch failed:", resp.status);
        return;
      }
      const data = await resp.json();
      _gateDisabledLogged = false;
      _render(data);
    } catch (e) {
      console.warn("[eval-harness] poll error:", e);
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

  // Manual hook for the Bug Panel's existing 2s loop and for ops who
  // want to re-poll on demand.
  window.lvEvalHarnessRefresh = _poll;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _start, { once: true });
  } else {
    _start();
  }
})();
