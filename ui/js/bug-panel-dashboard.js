/* WO-OPERATOR-RESOURCE-DASHBOARD-01 — Bug Panel Stack Dashboard UI.
 *
 * Operator cockpit: live gauges for services, system, GPU, capture,
 * archive, eval. Backed by /api/operator/stack-dashboard/summary.
 *
 * Polling cadence:
 *   - 5s while Bug Panel is visible / window is focused
 *   - 30s when window is hidden (tab in background)
 *   - immediate refresh on Bug Panel open + window focus + visibilitychange
 *
 * Pre-work review notes:
 *   - Defensive HTML escaping on every interpolated string (XSS gate)
 *   - Polling stops + restarts cleanly on visibility transitions; the
 *     Refresh button never double-fires (uses _inflight guard)
 *   - 404 from disabled gate logged once, then quiet placeholder
 *   - clearInterval cleanup on visibility-hide so background tabs don't
 *     keep hitting the API
 *   - Inline-SVG sparklines (no library); 30 most-recent rows from
 *     /history endpoint
 */
(function () {
  "use strict";

  const POLL_INTERVAL_FOREGROUND_MS = 5 * 1000;
  const POLL_INTERVAL_BACKGROUND_MS = 30 * 1000;
  const SUMMARY_ENDPOINT = "/api/operator/stack-dashboard/summary";
  const HISTORY_ENDPOINT = "/api/operator/stack-dashboard/history?minutes=10";
  const MARK_ENDPOINT = "/api/operator/stack-dashboard/mark";
  const HEARTBEAT_ENDPOINT = "/api/operator/stack-dashboard/ui-heartbeat";

  let _timer = null;
  let _gateDisabledLogged = false;
  let _inflight = false;
  let _historyCache = [];
  let _lastUpdated = null;

  // Map backend statuses → CSS class suffixes.
  const STATUS_CLASS = {
    ok: "ok",
    warm: "ok",
    writing: "ok",
    active: "ok",
    speaking: "ok",
    running: "ok",
    warn: "warn",
    slow: "warn",
    stale: "warn",
    cold: "warn",
    idle_recent: "warn",
    fail: "fail",
    down: "fail",
    error: "fail",
    unknown: "stale",
    idle: "stale",
    off: "stale",
    disabled: "stale",
    unavailable: "missing",
    missing: "missing",
  };

  const STATUS_LABEL = {
    ok: "OK",
    warm: "WARM",
    writing: "WRITING",
    active: "ACTIVE",
    speaking: "SPEAKING",
    running: "RUNNING",
    warn: "WARN",
    slow: "SLOW",
    stale: "STALE",
    cold: "COLD",
    idle_recent: "IDLE",
    fail: "FAIL",
    down: "DOWN",
    error: "ERROR",
    unknown: "UNKNOWN",
    idle: "IDLE",
    off: "OFF",
    disabled: "OFF",
    unavailable: "N/A",
    missing: "MISSING",
  };

  function _esc(s) {
    if (s == null) return "";
    const div = document.createElement("div");
    div.textContent = String(s);
    return div.innerHTML;
  }

  function _statusClass(status) {
    return STATUS_CLASS[status] || "stale";
  }

  function _statusLabel(status) {
    return STATUS_LABEL[status] || (status ? String(status).toUpperCase() : "—");
  }

  function _fmtMs(ms) {
    if (ms == null || isNaN(ms)) return "—";
    if (ms < 1000) return Math.round(ms) + " ms";
    return (ms / 1000).toFixed(1) + " s";
  }

  function _fmtMb(mb) {
    if (mb == null || isNaN(mb)) return "—";
    if (mb >= 1024) return (mb / 1024).toFixed(1) + " GB";
    return Math.round(mb) + " MB";
  }

  function _fmtPct(p) {
    if (p == null || isNaN(p)) return "—";
    return Math.round(Number(p)) + "%";
  }

  function _fmtAge(seconds) {
    if (seconds == null) return "—";
    if (seconds < 60) return Math.round(seconds) + "s ago";
    if (seconds < 3600) return Math.round(seconds / 60) + "m ago";
    return Math.round(seconds / 3600) + "h ago";
  }

  function _fmtTime(iso) {
    if (!iso) return "?";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return "?";
      return d.toLocaleTimeString();
    } catch (_) {
      return "?";
    }
  }

  // ── Sparkline (inline SVG, ≤100 datapoints) ──────────────────────────────
  // Post-build review MEDIUM #3: defensive max-points cap protects us
  // from accidental future increases of the history window. Today the
  // _historyCache slice keeps it ≤30 points, but the sparkline itself
  // also tail-slices so it can never become a browser perf hazard.
  const _SPARKLINE_MAX_POINTS = 100;

  function _sparkline(values, opts) {
    opts = opts || {};
    const w = opts.width || 80;
    const h = opts.height || 18;
    const stroke = opts.stroke || "currentColor";
    if (!Array.isArray(values) || values.length < 2) {
      return `<svg class="dash-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"></svg>`;
    }
    let cleaned = values.filter((v) => typeof v === "number" && !isNaN(v));
    if (cleaned.length > _SPARKLINE_MAX_POINTS) {
      cleaned = cleaned.slice(-_SPARKLINE_MAX_POINTS);
    }
    if (cleaned.length < 2) {
      return `<svg class="dash-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"></svg>`;
    }
    const min = Math.min(...cleaned);
    const max = Math.max(...cleaned);
    const range = max - min || 1;
    const dx = w / (cleaned.length - 1);
    const points = cleaned.map((v, i) => {
      const x = (i * dx).toFixed(1);
      const y = (h - ((v - min) / range) * h).toFixed(1);
      return `${x},${y}`;
    }).join(" ");
    return `<svg class="dash-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline fill="none" stroke="${stroke}" stroke-width="1.5" points="${points}"/></svg>`;
  }

  function _historyValues(key, deep) {
    // key is a dotted path into the row — supports gpu.vram_used_mb etc.
    return _historyCache.map((row) => {
      let cur = row;
      for (const part of key.split(".")) {
        if (cur == null) return null;
        cur = cur[part];
      }
      return typeof cur === "number" ? cur : null;
    });
  }

  // ── Card renderers ───────────────────────────────────────────────────────

  function _renderServiceCard(label, port, block) {
    block = block || {};
    const status = block.status || "unknown";
    const cls = _statusClass(status);
    const lat = _fmtMs(block.latency_ms);
    const err = block.error ? `<div class="dash-card-error">${_esc(block.error)}</div>` : "";
    return `
      <div class="dash-card dash-card-${cls}">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">${_esc(label)}${port ? " " + port : ""}</span>
        </div>
        <div class="dash-card-metric"><strong>${lat}</strong></div>
        ${err}
      </div>`;
  }

  function _renderLlmCard(block) {
    block = block || {};
    const status = block.status || "unknown";
    const cls = _statusClass(status);
    const free = _fmtMb(block.vram_free_mb);
    const lastWarm = block.last_warm_age_sec != null
      ? _fmtAge(block.last_warm_age_sec)
      : "—";
    return `
      <div class="dash-card dash-card-${cls}">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">LLM Warm</span>
        </div>
        <div class="dash-card-metric"><strong>${free}</strong> free</div>
        <div class="dash-card-meta">last warm ${lastWarm}</div>
      </div>`;
  }

  function _renderSystemCard(label, percent, secondLine, sparkValues) {
    const status = (percent == null) ? "unknown" :
                    (percent >= 95 ? "fail" : (percent >= 80 ? "warn" : "ok"));
    const cls = _statusClass(status);
    const spark = sparkValues ? _sparkline(sparkValues) : "";
    return `
      <div class="dash-card dash-card-${cls}">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">${_esc(label)}</span>
        </div>
        <div class="dash-card-metric"><strong>${_fmtPct(percent)}</strong></div>
        ${secondLine ? `<div class="dash-card-meta">${secondLine}</div>` : ""}
        ${spark ? `<div class="dash-card-spark">${spark}</div>` : ""}
      </div>`;
  }

  function _renderGpuCard(gpu) {
    gpu = gpu || {};
    const status = gpu.status || "unknown";
    const cls = _statusClass(status);
    if (status === "unavailable" || status === "missing") {
      return `
        <div class="dash-card dash-card-${cls} dash-card-wide">
          <div class="dash-card-header">
            <span class="dash-card-status">${_statusLabel(status)}</span>
            <span class="dash-card-title">GPU</span>
          </div>
          <div class="dash-card-meta">${_esc(gpu.error || "nvidia-smi not available")}</div>
        </div>`;
    }
    const name = _esc(gpu.name || "GPU");
    const util = _fmtPct(gpu.util_percent);
    const used = _fmtMb(gpu.vram_used_mb);
    const total = _fmtMb(gpu.vram_total_mb);
    const free = _fmtMb(gpu.vram_free_mb);
    const temp = gpu.temperature_c != null ? `${Math.round(gpu.temperature_c)} °C` : "—";
    const power = gpu.power_draw_w != null ? `${Math.round(gpu.power_draw_w)} W` : "";
    return `
      <div class="dash-card dash-card-${cls} dash-card-wide">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">${name}</span>
        </div>
        <div class="dash-card-row">
          <span class="dash-card-metric">Util <strong>${util}</strong></span>
          <span class="dash-card-metric">VRAM <strong>${used}</strong> / ${total}</span>
          <span class="dash-card-metric">Free <strong>${free}</strong></span>
          <span class="dash-card-metric">Temp <strong>${temp}</strong></span>
          ${power ? `<span class="dash-card-metric">${power}</span>` : ""}
        </div>
        <div class="dash-card-spark">${_sparkline(_historyValues("gpu.vram_used_mb"))}</div>
      </div>`;
  }

  function _renderCaptureCard(label, block, kind) {
    block = block || {};
    const status = block.status || "unknown";
    const cls = _statusClass(status);
    const reported = block.reported_by_ui ? "" : '<span class="dash-card-meta">(no UI heartbeat)</span>';
    let metric = "";
    if (kind === "camera" && status === "active") {
      const w = block.width, h = block.height;
      metric = (w && h) ? `${w}×${h}` : "active";
    } else if (kind === "microphone" && status === "active") {
      const lvl = block.rms_level;
      metric = lvl != null ? `level ${(lvl * 100).toFixed(0)}%` : "active";
    } else if (kind === "audio_archive") {
      const age = block.latest_file_age_sec;
      metric = age != null ? `last write ${_fmtAge(age)}` : "—";
    } else if (kind === "video_archive") {
      metric = "audio-only";
    } else if (kind === "tts_state" && status === "speaking") {
      metric = `queue ${block.queue_length ?? "?"}`;
    } else {
      metric = _statusLabel(status).toLowerCase();
    }
    return `
      <div class="dash-card dash-card-${cls}">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">${_esc(label)}</span>
        </div>
        <div class="dash-card-metric"><strong>${_esc(metric)}</strong></div>
        ${reported}
      </div>`;
  }

  function _renderArchiveCard(block) {
    block = block || {};
    const status = block.status || "unknown";
    const cls = _statusClass(status);
    const txt = block.latest_txt_age_sec != null ? _fmtAge(block.latest_txt_age_sec) : "—";
    const jsonl = block.latest_jsonl_age_sec != null ? _fmtAge(block.latest_jsonl_age_sec) : "—";
    return `
      <div class="dash-card dash-card-${cls} dash-card-wide">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">Memory Archive</span>
        </div>
        <div class="dash-card-row">
          <span class="dash-card-metric">.txt last <strong>${txt}</strong></span>
          <span class="dash-card-metric">.jsonl last <strong>${jsonl}</strong></span>
        </div>
      </div>`;
  }

  function _renderEvalCard(block) {
    block = block || {};
    const status = block.status || "unknown";
    const cls = _statusClass(status);
    const tag = block.tag || "—";
    const ageS = block.last_extract_age_sec;
    const ageStr = ageS != null ? _fmtAge(ageS) : "—";
    const conn = block.connection_refused_count_rolling || 0;
    const report = block.latest_report || {};
    const reportLine = report.tag
      ? `<span class="dash-card-metric">latest <strong>${_esc(report.tag)}</strong> ${report.passed ?? "?"}/${report.total ?? "?"} ${report.age_sec != null ? _fmtAge(report.age_sec) : ""}</span>`
      : "";
    return `
      <div class="dash-card dash-card-${cls} dash-card-wide">
        <div class="dash-card-header">
          <span class="dash-card-status">${_statusLabel(status)}</span>
          <span class="dash-card-title">Current Eval</span>
          <span class="dash-card-tag">${_esc(tag)}</span>
        </div>
        <div class="dash-card-row">
          <span class="dash-card-metric">last [extract] <strong>${ageStr}</strong></span>
          <span class="dash-card-metric">conn refused <strong>${conn}</strong></span>
          ${reportLine}
        </div>
      </div>`;
  }

  function _renderWarnings(warnings) {
    if (!Array.isArray(warnings) || warnings.length === 0) return "";
    const items = warnings.map((w) => {
      const cat = _esc(w.category || "");
      const msg = _esc(w.message || "");
      return `<li class="dash-warning-item"><span class="dash-warning-cat">${cat}</span> ${msg}</li>`;
    }).join("");
    return `
      <div class="dash-warnings">
        <div class="dash-section-title">Warnings</div>
        <ul class="dash-warning-list">${items}</ul>
      </div>`;
  }

  function _renderMarkers(markers) {
    if (!Array.isArray(markers) || markers.length === 0) return "";
    const items = markers.slice(-5).reverse().map((m) => {
      return `<li><time>${_esc(m.ts || "")}</time> ${_esc(m.label || "")}</li>`;
    }).join("");
    return `<div class="dash-markers"><div class="dash-section-title">Recent markers</div><ul class="dash-marker-list">${items}</ul></div>`;
  }

  // ── Main render ──────────────────────────────────────────────────────────

  function _render(data) {
    const root = document.getElementById("lvStackDashboardRoot");
    if (!root) return;

    if (!data) {
      root.innerHTML = `<div class="dash-empty">No data.</div>`;
      return;
    }

    const updated = data.generated_at || _lastUpdated || "";
    const rollup = data.status || "unknown";
    const services = data.services || {};
    const system = data.system || {};
    const gpu = data.gpu || {};
    const capture = data.capture || {};
    const archive = data.archive || {};
    const eval_ = data.eval || {};
    const warnings = data.warnings || [];
    const markers = data.markers || [];

    const cpuSpark = _historyValues("cpu_percent");
    const ramSpark = _historyValues("memory_percent");

    root.innerHTML = `
      <div class="dash-header dash-status-${_statusClass(rollup)}">
        <div class="dash-header-title">Stack Dashboard</div>
        <div class="dash-header-sub">
          <span>Live local health</span>
          <span class="dash-header-updated">Updated ${_fmtTime(updated)}</span>
          <button type="button" class="dash-btn" id="lvStackDashboardRefresh">Refresh</button>
          <button type="button" class="dash-btn" id="lvStackDashboardMark">Mark now</button>
        </div>
      </div>

      <div class="dash-section">
        <div class="dash-section-title">Services</div>
        <div class="dash-grid dash-grid-4">
          ${_renderServiceCard("API", "8000", services.api)}
          ${_renderServiceCard("UI", "", services.ui)}
          ${_renderServiceCard("TTS", "8001", services.tts)}
          ${_renderLlmCard(services.llm)}
        </div>
      </div>

      <div class="dash-section">
        <div class="dash-section-title">System</div>
        <div class="dash-grid dash-grid-4">
          ${_renderSystemCard("CPU", system.cpu_percent,
              system.cpu_count ? `${system.cpu_count} cores` : "", cpuSpark)}
          ${_renderSystemCard("RAM", system.memory_percent,
              `${system.memory_used_gb ?? "—"} / ${system.memory_total_gb ?? "—"} GB`, ramSpark)}
          ${_renderSystemCard("Disk", system.disk_percent,
              `${system.disk_free_gb ?? "—"} GB free`, null)}
          ${_renderSystemCard("Procs", null,
              `${system.process_count ?? "—"} running`, null).replace("dash-card-stale", "dash-card-ok")}
        </div>
      </div>

      <div class="dash-section">
        <div class="dash-section-title">GPU</div>
        <div class="dash-grid dash-grid-1">
          ${_renderGpuCard(gpu)}
        </div>
      </div>

      <div class="dash-section">
        <div class="dash-section-title">Capture</div>
        <div class="dash-grid dash-grid-4">
          ${_renderCaptureCard("Camera", capture.camera, "camera")}
          ${_renderCaptureCard("Microphone", capture.microphone, "microphone")}
          ${_renderCaptureCard("TTS state", capture.tts_state, "tts_state")}
          ${_renderCaptureCard("Audio Save", capture.audio_archive, "audio_archive")}
        </div>
      </div>

      <div class="dash-section">
        <div class="dash-section-title">Archive + Eval</div>
        <div class="dash-grid dash-grid-2">
          ${_renderArchiveCard(archive)}
          ${_renderEvalCard(eval_)}
        </div>
      </div>

      ${_renderWarnings(warnings)}
      ${_renderMarkers(markers)}
    `;

    // Wire buttons (re-bound on every render — that's fine because the
    // root.innerHTML wipes the previous handlers).
    const refreshBtn = document.getElementById("lvStackDashboardRefresh");
    if (refreshBtn) refreshBtn.addEventListener("click", _poll, false);
    const markBtn = document.getElementById("lvStackDashboardMark");
    if (markBtn) markBtn.addEventListener("click", _promptAndMark, false);

    _lastUpdated = updated;
  }

  function _renderDisabled() {
    const root = document.getElementById("lvStackDashboardRoot");
    if (!root) return;
    root.innerHTML = `<div class="dash-empty dash-empty-gate-off">Stack Dashboard backend disabled. Set <code>HORNELORE_OPERATOR_STACK_DASHBOARD=1</code> in <code>.env</code> and restart the API.</div>`;
  }

  function _renderError(msg) {
    const root = document.getElementById("lvStackDashboardRoot");
    if (!root) return;
    root.innerHTML = `<div class="dash-empty dash-empty-error">Stack Dashboard error: ${_esc(msg)}</div>`;
  }

  // ── Polling ──────────────────────────────────────────────────────────────

  async function _poll() {
    if (_inflight) return;
    _inflight = true;
    try {
      const resp = await fetch(SUMMARY_ENDPOINT, {
        method: "GET",
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });
      if (resp.status === 404) {
        if (!_gateDisabledLogged) {
          console.info("[stack-dashboard] backend gate is OFF (404)");
          _gateDisabledLogged = true;
        }
        _renderDisabled();
        return;
      }
      if (!resp.ok) {
        console.warn("[stack-dashboard] summary fetch failed:", resp.status);
        _renderError(`HTTP ${resp.status}`);
        return;
      }
      const data = await resp.json();
      _gateDisabledLogged = false;
      _render(data);
      // Fire history fetch in background — don't block the render.
      _refreshHistory();
    } catch (e) {
      console.warn("[stack-dashboard] poll error:", e);
      _renderError(String(e && e.message ? e.message : e));
    } finally {
      _inflight = false;
    }
  }

  async function _refreshHistory() {
    try {
      const resp = await fetch(HISTORY_ENDPOINT, { cache: "no-store" });
      if (!resp.ok) return;
      const data = await resp.json();
      if (data && Array.isArray(data.rows)) {
        _historyCache = data.rows.slice(-30);
      }
    } catch (_) {
      // History is optional — sparklines just stay empty.
    }
  }

  async function _promptAndMark() {
    const label = window.prompt("Marker label (≤200 chars):");
    if (!label) return;
    try {
      const resp = await fetch(MARK_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.slice(0, 200) }),
      });
      if (resp.status === 429) {
        console.info("[stack-dashboard] mark rate-limited (1/sec)");
        return;
      }
      if (!resp.ok) {
        console.warn("[stack-dashboard] mark failed:", resp.status);
        return;
      }
      _poll();  // refresh so the marker appears in the recent list
    } catch (e) {
      console.warn("[stack-dashboard] mark error:", e);
    }
  }

  // ── Polling lifecycle ────────────────────────────────────────────────────

  function _scheduleNext() {
    if (_timer) {
      clearInterval(_timer);
      _timer = null;
    }
    const interval = document.hidden
      ? POLL_INTERVAL_BACKGROUND_MS
      : POLL_INTERVAL_FOREGROUND_MS;
    _timer = setInterval(_poll, interval);
  }

  function _start() {
    if (!document.getElementById("lvStackDashboardRoot")) return;
    _poll();
    _scheduleNext();

    window.addEventListener("focus", _poll, false);
    document.addEventListener("visibilitychange", () => {
      _scheduleNext();
      if (!document.hidden) _poll();
    }, false);

    const panel = document.getElementById("lv10dBugPanel");
    if (panel && typeof panel.addEventListener === "function") {
      panel.addEventListener("toggle", (e) => {
        if (e && e.newState === "open") _poll();
      }, false);
    }
  }

  // Manual hook for the existing Bug Panel re-poll machinery + ad-hoc
  // operator console use.
  window.lvStackDashboardRefresh = _poll;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _start, { once: true });
  } else {
    _start();
  }
})();
