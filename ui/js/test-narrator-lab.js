/* ═══════════════════════════════════════════════════════════════
   test-narrator-lab.js — WO-QA-01 Quality Harness operator panel
   Lorevox / Hornelore 1.0

   Thin UI over the /api/test-lab/* endpoints. Launches the harness,
   polls status, lists prior runs, renders scores / compare / summary
   / transcript samples. Does NOT score anything itself — reads the
   JSON artifacts the runner produces.
   ═══════════════════════════════════════════════════════════════ */
(() => {
  "use strict";

  // WO-QA-01: Hornelore's UI server on 8082 is a plain static file server —
  // it does NOT proxy /api/* to the FastAPI backend. Use the same ORIGIN
  // constant api.js uses, which points at http://localhost:8000 by default.
  const _origin = (typeof ORIGIN !== "undefined" && ORIGIN)
    ? ORIGIN
    : (window.LOREVOX_API || "http://localhost:8000");

  const API = {
    run:     _origin + "/api/test-lab/run",
    status:  _origin + "/api/test-lab/status",
    results: _origin + "/api/test-lab/results",
    result:  (id) => `${_origin}/api/test-lab/results/${encodeURIComponent(id)}`,
    reset:   _origin + "/api/test-lab/reset",
  };

  async function jget(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  async function jpost(url, body) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  function byId(id) { return document.getElementById(id); }
  function clearNode(el) { if (el) el.innerHTML = ""; }
  function setText(id, value) {
    const el = byId(id);
    if (el) el.textContent = value ?? "";
  }

  /* ── Status ──────────────────────────────────────────────── */
  function renderStatus(status) {
    const el = byId("testLabStatus");
    if (!el) return;
    let txt = `Status: ${status.state || "idle"}`;
    if (status.pid)           txt += ` (pid ${status.pid})`;
    if (status.latest_run)    txt += ` · latest=${status.latest_run}`;
    if (status.compare_to)    txt += ` · compare=${status.compare_to}`;
    if (status.dry_run)       txt += ` · dry-run`;
    el.textContent = txt;
  }

  /* ── Run list / compare dropdown ─────────────────────────── */
  function renderRuns(runs) {
    const runSel = byId("testLabRuns");
    const cmpSel = byId("testLabCompareTo");
    for (const sel of [runSel, cmpSel]) {
      if (!sel) continue;
      const current = sel.value;
      sel.innerHTML = "";
      const opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = (sel.id === "testLabCompareTo")
        ? "No compare baseline"
        : "Select run to load";
      sel.appendChild(opt0);
      for (const run of runs || []) {
        const opt = document.createElement("option");
        opt.value = run;
        opt.textContent = run;
        sel.appendChild(opt);
      }
      if (current && (runs || []).includes(current)) sel.value = current;
    }
  }

  /* ── Scores table ────────────────────────────────────────── */
  function td(value, attrs) {
    const c = document.createElement("td");
    c.textContent = value == null ? "" : String(value);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) c.setAttribute(k, v);
    }
    return c;
  }

  function renderScores(scores) {
    const body = byId("testLabScoreBody");
    clearNode(body);
    if (!body) return;
    for (const row of scores || []) {
      const tr = document.createElement("tr");
      tr.appendChild(td(row.narrator_style));
      tr.appendChild(td(row.config_id));
      tr.appendChild(td(row.proposal_row_yield));
      tr.appendChild(td(row.avg_ttft_ms));
      tr.appendChild(td(row.avg_tokens_per_sec));
      tr.appendChild(td(row.contamination_pass, { "data-contam": String(row.contamination_pass) }));
      tr.appendChild(td(row.blocked_cells));
      tr.appendChild(td(row.avg_human_score));
      body.appendChild(tr);
    }
  }

  function renderCompare(compareRows) {
    const body = byId("testLabCompareBody");
    clearNode(body);
    if (!body) return;
    for (const row of compareRows || []) {
      const tr = document.createElement("tr");
      tr.appendChild(td(row.narrator_style));
      tr.appendChild(td(row.config_id));
      tr.appendChild(td(row.yield_delta));
      tr.appendChild(td(row.ttft_delta_ms));
      tr.appendChild(td(row.contamination_delta));
      body.appendChild(tr);
    }
  }

  function renderSummary(summary) { setText("testLabSummary", summary || ""); }

  function renderConfigs(configsDoc) {
    const el = byId("testLabConfigs");
    if (!el) return;
    const lines = [];
    for (const cfg of (configsDoc?.configs || [])) {
      lines.push(
        `${cfg.id}: temp=${cfg.temperature}, top_p=${cfg.top_p}, ` +
        `rep=${cfg.repetition_penalty}, max_new=${cfg.max_new_tokens}`
      );
    }
    el.textContent = lines.join("\n");
  }

  function renderTranscripts(transcripts) {
    const el = byId("testLabTranscripts");
    if (!el) return;
    const rows = [];
    for (const t of (transcripts || []).slice(0, 18)) {
      rows.push(`[${t.narrator_style} | ${t.config_id} | ${t.scenario_id}]`);
      rows.push(`PROMPT: ${t.prompt}`);
      rows.push(`RESPONSE: ${t.response}`);
      rows.push("");
    }
    el.textContent = rows.join("\n");
  }

  /* ── Polling + actions ───────────────────────────────────── */
  async function refreshStatus() {
    try { renderStatus(await jget(API.status)); }
    catch (e) { renderStatus({ state: `error: ${e.message}` }); }
  }

  async function refreshRuns() {
    try {
      const data = await jget(API.results);
      renderRuns(data.runs || []);
    } catch (e) { console.error("[WO-QA-01] refreshRuns failed:", e); }
  }

  async function loadRun(runId) {
    if (!runId) return;
    const data = await jget(API.result(runId));
    renderScores(data.scores);
    renderCompare(data.compare);
    renderSummary(data.summary);
    renderTranscripts(data.transcripts);
    renderConfigs(data.configs);
    setText("testLabLoadedRun", `Loaded run: ${runId}`);
  }

  async function loadSelectedRun() {
    const sel = byId("testLabRuns");
    if (!sel || !sel.value) return;
    await loadRun(sel.value);
  }

  async function startRun() {
    const compareTo = byId("testLabCompareTo")?.value || "";
    const runLabel  = byId("testLabRunLabel")?.value.trim() || "";
    const dryRun    = !!byId("testLabDryRun")?.checked;
    try {
      await jpost(API.run, {
        compare_to: compareTo || null,
        run_label:  runLabel || null,
        dry_run:    dryRun,
      });
      await refreshStatus();
      await refreshRuns();
    } catch (e) {
      alert(`Test Lab failed to start: ${e.message}`);
    }
  }

  async function resetLab() {
    await jpost(API.reset, {});
    await refreshStatus();
  }

  function wire() {
    byId("testLabRunBtn")?.addEventListener("click", startRun);
    byId("testLabResetBtn")?.addEventListener("click", resetLab);
    byId("testLabRefreshBtn")?.addEventListener("click", async () => {
      await refreshStatus();
      await refreshRuns();
    });
    byId("testLabRuns")?.addEventListener("change", loadSelectedRun);

    refreshStatus();
    refreshRuns();
    setInterval(refreshStatus, 3000);
  }

  window.initTestNarratorLab = wire;
})();
