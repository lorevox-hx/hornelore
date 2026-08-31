#!/usr/bin/env node
/*
 * Focused live acceptance for one existing synthetic narrator: Walter
 * O'Donnell. This is intentionally NOT another cohort run.
 *
 * It uses the real browser UI, the real Life Map buttons, the real
 * confirmation popover, the real composer, the real WebSocket and the real
 * local model. It creates no person and invokes no deletion route.
 *
 * The source cohort journal is the authority for Walt's exact UUID. A display
 * name is never used to choose a narrator.
 *
 * Usage from the repo root, with the stack and model warm:
 *
 *   node scripts/ui/run_walt_seven_era_conversation.js \
 *     --run-id r20260831-040506-010cd6 --headed
 *
 * Optional: --ui URL --api URL --out DIR
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SOURCE = "run_seven_era_walk_harness";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DESTRUCTIVE = /delete|erase|remove|destroy|purge/i;

/* Short, conversational excerpts from Walt's existing seven-era fixture.
 * These are deliberately not 300-500 word chapter dumps. Each excerpt is
 * copied from scripts/run_seven_era_walk_harness.py and keeps enough concrete
 * detail for a grounded reply. */
const ERAS = [
  {
    id: "earliest_years",
    label: "Earliest Years",
    narrator: "I was born on Saint Patrick's Day, 1948, in South Boston. My older brother Brendan was already two, and my sister Eileen came along three years later. We lived on the second floor of a triple-decker on G Street in Southie.",
    anchors: ["saint patrick", "1948", "south boston", "brendan", "eileen", "g street", "southie"],
  },
  {
    id: "early_school_years",
    label: "Early School Years",
    narrator: "I started at Saint Augustine's parish school in 1953 when I was five. Sister Mary Alacoque taught me my letters and prayers. By third grade I knew I liked numbers more than letters, and Sister Bernadette gave me extra math problems.",
    anchors: ["saint augustine", "1953", "sister mary alacoque", "third grade", "numbers", "sister bernadette", "math"],
  },
  {
    id: "adolescence",
    label: "Adolescence",
    narrator: "I went to Boston Latin School after passing the entrance exam in sixth grade. The first two years were hard, but by the third year math team had become my life. Those years helped me decide that I would become a mathematics teacher.",
    anchors: ["boston latin", "entrance exam", "sixth grade", "math team", "mathematics teacher"],
  },
  {
    id: "coming_of_age",
    label: "Coming of Age",
    narrator: "I went to Boston College on a Jesuit scholarship and majored in mathematics. I lived at home and took the trolley to Chestnut Hill. After college I began teaching at Saint Mary's of Lynn, where I met Catherine Murphy.",
    anchors: ["boston college", "jesuit", "mathematics", "chestnut hill", "saint mary", "catherine"],
  },
  {
    id: "building_years",
    label: "Building Years",
    narrator: "After ten years at Saint Mary's of Lynn, I moved to North Quincy High School in 1980. I stayed there for thirty-five years teaching algebra, geometry, calculus, and AP Statistics. Some of my former students later sent their own children to my classroom.",
    anchors: ["saint mary", "north quincy", "1980", "thirty-five", "algebra", "geometry", "calculus", "students"],
  },
  {
    id: "later_years",
    label: "Later Years",
    narrator: "I retired in 2020, finishing my last spring by teaching geometry over Zoom. I soon started tutoring middle-school and high-school students two afternoons a week because I am happier when I am teaching. I had my left knee replaced in 2022.",
    anchors: ["retired", "2020", "geometry", "zoom", "tutoring", "teaching", "knee", "2022"],
  },
  {
    id: "today",
    label: "Today",
    narrator: "Today Catherine and I had our usual coffee and toast with the Boston Globe between us. This afternoon I am tutoring Aiden, an eighth-grader who is working on the order of operations. Daniel is coming down from Lowell on Saturday.",
    anchors: ["today", "catherine", "boston globe", "aiden", "eighth", "order of operations", "daniel", "lowell", "saturday"],
  },
];

const BIO_PROBE = "Before we begin the Life Map, please tell me what you already know from my profile about where I was born, the work I did, and who I live with.";
const BIO_ANCHORS = [
  { key: "birthplace", terms: ["south boston", "boston"] },
  { key: "career", terms: ["mathematics teacher", "math teacher", "teacher"] },
  { key: "spouse", terms: ["catherine"] },
  { key: "residence", terms: ["quincy"] },
];

function parseArgs(argv) {
  const out = {
    ui: "http://localhost:8082/ui/hornelore1.0.html",
    api: "http://localhost:8000",
    headed: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (key === "--headed" || key === "--self-test") {
      out[key.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = true;
      continue;
    }
    if (!key.startsWith("--")) throw new Error(`unexpected argument: ${key}`);
    const value = argv[++i];
    if (!value || value.startsWith("--")) throw new Error(`missing value for ${key}`);
    out[key.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
  }
  if (!out.selfTest && !out.runId) throw new Error("--run-id is required");
  return out;
}

function nowId() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
}

function readWaltFromJournal(repoRoot, runId) {
  if (!/^[A-Za-z0-9._-]+$/.test(runId)) throw new Error("unsafe --run-id");
  const journalPath = path.join(repoRoot, ".runtime", "eval", "narrator-cohort", runId, "artifacts.json");
  if (!fs.existsSync(journalPath)) throw new Error(`source journal not found: ${journalPath}`);
  const journal = JSON.parse(fs.readFileSync(journalPath, "utf8"));
  const rows = (journal.people || []).filter((p) => p.source === SOURCE);
  if (rows.length !== 1) throw new Error(`expected exactly one ${SOURCE} narrator in ${runId}; found ${rows.length}`);
  const row = rows[0];
  if (!UUID_RE.test(String(row.person_id || ""))) throw new Error("journaled Walt person_id is not an exact UUID");
  return { row, journalPath };
}

function captureInitScript() {
  window.__waltEraCapture = { sent: [], received: [] };
  const NativeWebSocket = window.WebSocket;
  function WrappedWebSocket(...args) {
    const socket = new NativeWebSocket(...args);
    const nativeSend = socket.send;
    socket.send = function (data) {
      let parsed = null;
      try { parsed = JSON.parse(String(data)); } catch (_) {}
      window.__waltEraCapture.sent.push({ at: new Date().toISOString(), raw: String(data), parsed });
      return nativeSend.call(this, data);
    };
    socket.addEventListener("message", (event) => {
      let parsed = null;
      try { parsed = JSON.parse(String(event.data)); } catch (_) {}
      window.__waltEraCapture.received.push({ at: new Date().toISOString(), raw: String(event.data), parsed });
    });
    return socket;
  }
  WrappedWebSocket.prototype = NativeWebSocket.prototype;
  ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach((key) => {
    Object.defineProperty(WrappedWebSocket, key, { value: NativeWebSocket[key] });
  });
  window.WebSocket = WrappedWebSocket;
}

async function openExactNarrator(page, personId, expectedDisplayName) {
  await page.waitForFunction(
    (pid) => Array.from(document.querySelectorAll("button")).some((b) =>
      b.textContent.trim() === "Open" && (b.getAttribute("onclick") || "").includes(pid)),
    personId,
    { timeout: 45000 },
  );
  const locator = page.locator(`button[onclick*="${personId}"]`).filter({ hasText: /^Open$/ });
  if (await locator.count() !== 1) throw new Error("exact Walt Open button is not unique");
  const details = await locator.evaluate((button) => ({
    text: button.textContent.trim(),
    handler: button.getAttribute("onclick") || "",
    disabled: Boolean(button.disabled),
  }));
  if (details.disabled || details.text !== "Open" || DESTRUCTIVE.test(`${details.text} ${details.handler}`)) {
    throw new Error("REFUSED: resolved narrator action is not a safe Open button");
  }
  await locator.click({ timeout: 30000 });

  /* ── The narrator-open race, 2026-08-31 ────────────────────────────
   * `state.person_id` is set EARLY in the open flow. The trainer-restore
   * path in ui/hornelore1.0.html then rewrites #lv80ActiveNarratorCard's
   * innerHTML back to a fresh card whose name reads "Choose a narrator",
   * and lv80UpdateActiveNarratorCard() repaints it afterwards. Waiting
   * only on person_id lands the read INSIDE that gap, which is how the
   * 20260831T142834Z run aborted 0/7 with
   *     opened narrator label does not identify Walt: Choose a narrator
   * while Walt was in fact open.
   *
   * So wait for the whole lifecycle to settle: the exact person, a
   * TERMINAL openStatus, the composer usable, and the card repainted.
   * The visible-name assertion is PRESERVED, not removed — if the flow
   * completes and the card still says "Choose a narrator", that is a
   * product identity defect and must be reported as one. */
  await page.waitForFunction(
    (pid) => window.state && window.state.person_id === pid,
    personId, { timeout: 60000 });
  await page.waitForFunction(
    () => {
      const st = (window.state && window.state.narratorOpen
                  && window.state.narratorOpen.openStatus) || null;
      return st && st !== "loading" && st !== "idle";
    },
    null, { timeout: 60000 });
  /* The card is repainted asynchronously after openStatus settles. Wait
   * for the EXPECTED product display name, not merely for any node that
   * is no longer the placeholder — with a duplicated id, "some node is
   * non-placeholder" can be satisfied by a stale copy still showing a
   * PREVIOUS narrator, which would let a wrong-narrator run proceed. */
  await page.waitForFunction(
    (want) => {
      const nodes = Array.from(
        document.querySelectorAll("#lv80ActiveNarratorName"));
      if (!nodes.length) return false;
      return nodes.some((n) => {
        const t = (n.textContent || "").trim();
        return t && (t === want || want.includes(t) || t.includes(want));
      });
    },
    expectedDisplayName, { timeout: 60000 });
  await page.waitForFunction(() => {
    const input = document.getElementById("chatInput");
    const busy = typeof window._loriIsBusy === "function" && window._loriIsBusy();
    return input && !input.disabled && !busy;
  }, null, { timeout: 120000 });
}

async function pauseProfileSeedIfNeeded(page) {
  await page.locator("#lvShellTabOperator").click();
  await page.waitForFunction(() => {
    const s = window.LorevoxProfileSeedAuthority?.snapshot?.() || null;
    return s && (s.status === "resolved" || s.status === "failed");
  }, null, { timeout: 30000 });
  const before = await page.evaluate(() => window.LorevoxProfileSeedAuthority?.snapshot?.() || null);
  if (before?.status === "failed") throw new Error(`Profile Seed authority failed: ${before.error || "unknown"}`);
  const status = before?.data?.status || before?.status || null;
  let usedButton = false;
  if (status === "active") {
    const button = page.locator("#psPauseBtn");
    if (!(await button.isVisible())) throw new Error("Profile Seed is active but its real Pause button is not visible");
    if (!/Pause Profile Seed/i.test(await button.textContent())) throw new Error("unexpected Profile Seed button label");
    await button.click();
    usedButton = true;
    await page.waitForFunction(() => {
      const s = window.LorevoxProfileSeedAuthority?.snapshot?.() || null;
      return (s?.data?.status || s?.status) === "paused";
    }, null, { timeout: 30000 });
  }
  const after = await page.evaluate(() => window.LorevoxProfileSeedAuthority?.snapshot?.() || null);
  await page.locator("#lvShellTabNarrator").click();
  await page.waitForTimeout(500);
  return { before, after, usedButton };
}

async function captureCounts(page) {
  return page.evaluate(() => ({
    sent: window.__waltEraCapture.sent.length,
    received: window.__waltEraCapture.received.length,
    done: window.__waltEraCapture.received.filter((x) => x.parsed?.type === "done").length,
    extraction: window.__waltEraCapture.received.filter((x) => x.parsed?.type === "field_extraction_result").length,
    aiBubbles: document.querySelectorAll("#chatMessages .bubble-ai").length,
  }));
}

async function waitForDone(page, beforeDone) {
  await page.waitForFunction(
    (n) => window.__waltEraCapture.received.filter((x) => x.parsed?.type === "done").length > n,
    beforeDone,
    { timeout: 120000 },
  );
  await page.waitForFunction(() => {
    const input = document.getElementById("chatInput");
    const busy = typeof window._loriIsBusy === "function" && window._loriIsBusy();
    return input && !input.disabled && !busy;
  }, null, { timeout: 30000 });
}

async function actionEvidence(page, before, expectedEra) {
  return page.evaluate(({ before, expectedEra }) => {
    const cap = window.__waltEraCapture;
    const sent = cap.sent.slice(before.sent).filter((x) => x.parsed?.type === "start_turn");
    const done = cap.received.slice(before.received).filter((x) => x.parsed?.type === "done");
    const extraction = cap.received.slice(before.received).filter((x) => x.parsed?.type === "field_extraction_result");
    const lastSent = sent[sent.length - 1]?.parsed || null;
    const lastDone = done[done.length - 1]?.parsed || null;
    return {
      expectedEra,
      selectedEra: window.state?.session?.currentEra || null,
      activeFocusEra: window.state?.session?.activeFocusEra || null,
      sentEra: lastSent?.params?.runtime71?.current_era || null,
      sentPass: lastSent?.params?.runtime71?.current_pass || null,
      messageKind: lastSent?.params?.message_kind || null,
      sentMessage: lastSent?.message || null,
      finalText: lastDone?.final_text || null,
      done: lastDone,
      sentFrames: sent,
      extractionFrames: extraction.map((x) => x.parsed),
    };
  }, { before, expectedEra });
}

async function sendTypedTurn(page, text, expectedEra) {
  const before = await captureCounts(page);
  const input = page.locator("#chatInput");
  await input.click();
  await input.type(text, { delay: 1 });
  if (await input.inputValue() !== text) throw new Error("real composer typing did not preserve narrator text");
  await page.locator("#lv80SendBtn").click();
  await waitForDone(page, before.done);
  let extractionReceived = false;
  try {
    await page.waitForFunction(
      (n) => window.__waltEraCapture.received.filter((x) => x.parsed?.type === "field_extraction_result").length > n,
      before.extraction,
      { timeout: 30000 },
    );
    extractionReceived = true;
  } catch (_) {
    // A timeout is evidence, not permission to claim extraction found
    // nothing. The report preserves this as false and continues.
  }
  const evidence = await actionEvidence(page, before, expectedEra);
  evidence.extractionReceived = extractionReceived;
  return evidence;
}

async function selectEraAndWait(page, era) {
  const before = await captureCounts(page);
  const eraButton = page.locator(`.lv-interview-lifemap-era-btn[data-era-id="${era.id}"]`);
  if (await eraButton.count() !== 1) throw new Error(`expected one Life Map button for ${era.id}`);
  await eraButton.click();
  const modal = page.locator(".lv-interview-confirm-overlay");
  await modal.waitFor({ state: "visible", timeout: 10000 });
  const namedEra = (await modal.locator(".lv-interview-confirm-era").textContent() || "").trim();
  if (namedEra !== era.label) throw new Error(`confirmation named ${namedEra}, expected ${era.label}`);
  await modal.locator(".lv-interview-confirm-continue").click();
  await page.waitForFunction((id) => window.state?.session?.currentEra === id, era.id, { timeout: 10000 });
  await waitForDone(page, before.done);
  return actionEvidence(page, before, era.id);
}

function normalized(text) {
  return String(text || "").toLowerCase().replace(/[’]/g, "'").replace(/\s+/g, " ");
}

function anchorHits(text, anchors) {
  const hay = normalized(text);
  return anchors.filter((a) => hay.includes(normalized(a)));
}

async function safeFetchJson(url) {
  try {
    const response = await fetch(url);
    const text = await response.text();
    let body = null;
    try { body = JSON.parse(text); } catch (_) { body = text; }
    return { ok: response.ok, status: response.status, url, body };
  } catch (error) {
    return { ok: false, status: null, url, error: String(error) };
  }
}

async function serverSnapshot(api, personId) {
  const q = encodeURIComponent(personId);
  const [person, facts, projection, chronology] = await Promise.all([
    safeFetchJson(`${api}/api/people/${q}`),
    safeFetchJson(`${api}/api/facts/list?person_id=${q}`),
    safeFetchJson(`${api}/api/interview/projection?person_id=${q}`),
    safeFetchJson(`${api}/api/chronology-accordion?person_id=${q}`),
  ]);
  return { at: new Date().toISOString(), person, facts, projection, chronology };
}

function logOffset(filename) {
  try { return fs.statSync(filename).size; } catch (_) { return 0; }
}

function readRelevantLogDelta(filename, offset, conversationId, personId) {
  if (!fs.existsSync(filename)) return { available: false, filename, lines: [] };
  const stat = fs.statSync(filename);
  const available = Math.max(0, stat.size - offset);
  const maxBytes = 20 * 1024 * 1024;
  const bytes = Math.min(available, maxBytes);
  const start = stat.size - bytes;
  const fd = fs.openSync(filename, "r");
  const buffer = Buffer.alloc(bytes);
  try { fs.readSync(fd, buffer, 0, bytes, start); } finally { fs.closeSync(fd); }
  const shortPerson = String(personId || "").slice(0, 8);
  const lines = buffer.toString("utf8").split(/\r?\n/).filter((line) =>
    (conversationId && line.includes(conversationId))
    || (personId && line.includes(personId))
    || (shortPerson && line.includes(`person=${shortPerson}`))
    || (shortPerson && line.includes(`narrator=${shortPerson}`)),
  );
  return {
    available: true,
    filename,
    startOffset: offset,
    endOffset: stat.size,
    bytesRead: bytes,
    truncatedToLast20MiB: available > maxBytes,
    lines,
    signals: {
      commControl: lines.filter((x) => x.includes("[comm_control]")).length,
      responseGuards: lines.filter((x) => x.includes("[response-guards]")).length,
      validatorFailures: lines.filter((x) => x.includes("validator FAIL")).length,
      extractionSuccess: lines.filter((x) => x.includes("extract_fields_succeeded")).length,
      eraRuntimeLines: lines.filter((x) => x.includes("[chat_ws] turn:")).length,
    },
  };
}

/* ── Response-trace consumption (WO-LORI-LISTEN-AND-RETAIN-01) ───────
 * The trace is OPT-IN. The stack must be launched with
 * HORNELORE_RESPONSE_TRACE=1 or this harness refuses to run: a report
 * that silently lacks raw-vs-delivered evidence looks like a result and
 * is not one. */
const RETENTION_STAGES = ["durable_turns", "extraction", "bio_facts",
  "chronology", "life_map", "rolling_summary", "archive", "memoir_source"];

function traceDir(repoRoot) {
  return process.env.HORNELORE_TRACE_DIR
    || path.join(repoRoot, ".runtime", "eval", "response-trace");
}

function readTraces(repoRoot, sinceMs) {
  const dir = traceDir(repoRoot);
  if (!fs.existsSync(dir)) return { available: false, dir, records: [] };
  const out = [];
  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".jsonl"))) {
    for (const line of fs.readFileSync(path.join(dir, file), "utf8").split(/\r?\n/)) {
      if (!line.trim()) continue;
      try {
        const rec = JSON.parse(line);
        if (!sinceMs || (rec.started_at || 0) * 1000 >= sinceMs) out.push(rec);
      } catch (_) { /* a torn final line is not a finding */ }
    }
  }
  return { available: true, dir, records: out };
}

function tracesForRun(repoRoot, sinceMs, personId, conversationId) {
  const all = readTraces(repoRoot, sinceMs);
  const mine = all.records.filter((r) =>
    (!personId || r.narrator_id === personId)
    && (!conversationId || r.conversation_id === conversationId));
  mine.sort((a, b) => (a.started_at || 0) - (b.started_at || 0));
  return { ...all, records: mine };
}

/* Retention truth for the whole run, per stage, without inventing a
 * pass. `measurement_failed` is counted apart from `measured_absent`
 * on purpose: a wrong-origin 404 is a broken measurement, not evidence
 * that the data is missing. */
function retentionSummary(records) {
  const summary = {};
  for (const stage of RETENTION_STAGES) {
    const counts = { persisted: 0, rejected: 0, measured_absent: 0,
                     measurement_failed: 0, not_measured: 0 };
    for (const rec of records) {
      const cell = (rec.storage || {})[stage];
      const r = cell && cell.result ? cell.result : "not_measured";
      if (counts[r] === undefined) counts.not_measured += 1;
      else counts[r] += 1;
    }
    counts.genuinelyMeasured = counts.persisted + counts.rejected
                             + counts.measured_absent;
    summary[stage] = counts;
  }
  return summary;
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* Raw model output -> each layer in execution order -> delivered.
 * This is the whole point of the work order: the pipeline has never
 * shown what the model wrote next to what the narrator received. */
function renderTraceSection(report) {
  const rt = report.responseTrace;
  if (!rt || !rt.available) {
    return `<h2>Response trace</h2><div class="card bad">NOT AVAILABLE — `
         + `no trace records were found. Nothing below can be attributed `
         + `to the model rather than to the control stack.</div>`;
  }
  if (!rt.turns) {
    return `<h2>Response trace</h2><div class="card bad">Trace directory `
         + `exists at <code>${esc(rt.dir)}</code> but recorded ZERO turns `
         + `for this narrator and conversation. Was the stack started with `
         + `HORNELORE_RESPONSE_TRACE=1?</div>`;
  }
  const turns = rt.records.map((rec, i) => {
    const stages = (rec.stages || []).map((st) => `
      <tr class="${st.changed ? "changed" : ""}">
        <td>${st.index}</td><td>${esc(st.stage)}</td>
        <td>${st.fired ? "fired" : "ran, no change"}</td>
        <td>${esc(JSON.stringify(st.reason))}</td>
        <td>${st.words_before} → ${st.words_after}
            (${st.words_delta > 0 ? "+" : ""}${st.words_delta})</td>
        <td>${st.questions_before} → ${st.questions_after}</td>
      </tr>
      ${st.changed ? `<tr class="diff"><td></td><td colspan="5">
        <div class="before"><b>before</b><br>${esc(st.before)}</div>
        <div class="after"><b>after</b><br>${esc(st.after)}</div></td></tr>` : ""}`).join("");
    const store = RETENTION_STAGES.map((name) => {
      const cell = (rec.storage || {})[name] || { result: "not_measured" };
      return `<tr><td>${esc(name)}</td><td class="r-${esc(cell.result)}">`
           + `${esc(cell.result)}</td><td>${esc(JSON.stringify(cell.detail || ""))}</td></tr>`;
    }).join("");
    return `
    <details ${i === 0 ? "open" : ""}>
      <summary>Turn ${i + 1} — ${esc(rec.trace_id.slice(0, 8))} ·
        raw ${rec.raw_words != null ? rec.raw_words : "?"} words →
        delivered ${rec.delivered_words != null ? rec.delivered_words : "?"} words
        ${rec.raw_equals_delivered === false ? " · REWRITTEN" : " · untouched"}</summary>
      <h4>Raw model output</h4><blockquote>${esc(rec.raw_text)}</blockquote>
      <h4>Control layers, in execution order</h4>
      <table><thead><tr><th>#</th><th>Layer</th><th>Fired</th><th>Reason</th>
        <th>Words</th><th>Questions</th></tr></thead><tbody>${stages}</tbody></table>
      <h4>Delivered to the narrator</h4><blockquote>${esc(rec.delivered_text)}</blockquote>
      <p><b>Delivered equals persisted:</b>
        ${rec.delivered_equals_persisted === true ? "yes"
          : rec.delivered_equals_persisted === false ? "<span class=\"bad\">NO</span>"
          : "not measured"}</p>
      <h4>Retention</h4>
      <table><thead><tr><th>Stage</th><th>Result</th><th>Detail</th></tr></thead>
        <tbody>${store}</tbody></table>
    </details>`;
  }).join("");

  const ret = Object.entries(rt.retention).map(([stage, c]) => `
    <tr><td>${esc(stage)}</td>
      <td>${c.persisted}</td><td>${c.rejected}</td><td>${c.measured_absent}</td>
      <td class="${c.measurement_failed ? "bad" : ""}">${c.measurement_failed}</td>
      <td class="${c.not_measured ? "warn" : ""}">${c.not_measured}</td>
      <td><b>${c.genuinelyMeasured}/${rt.turns}</b></td></tr>`).join("");

  return `
  <h2>Retention — what is genuinely measured</h2>
  <div class="card"><p><b>measurement_failed</b> and <b>not_measured</b> are
  counted apart from <b>measured_absent</b> deliberately. A failed or absent
  measurement is not evidence that the narrator's information is missing.</p></div>
  <table><thead><tr><th>Stage</th><th>persisted</th><th>rejected</th>
    <th>measured absent</th><th>measurement FAILED</th><th>not measured</th>
    <th>genuinely measured</th></tr></thead><tbody>${ret}</tbody></table>
  <h2>Response trace — raw vs every layer vs delivered</h2>
  ${turns}`;
}

function renderHtml(report) {
  const eras = report.eras || [];
  const bio = report.bio || { prompt: "not reached", response: "not reached", hits: [] };
  const diagnostics = report.diagnostics || { consoleErrors: [], failedRequests: [], httpErrors: [] };
  const logEvidence = report.apiLogEvidence || { available: false, lines: [], signals: {} };
  const eraRows = eras.map((row) => `
    <tr>
      <td>${esc(row.label)}</td>
      <td>${row.mechanical.eraSelectedAndSent ? "PASS" : "FAIL"}</td>
      <td>${esc(row.narratorEvidence.sentEra || "—")}</td>
      <td>${esc(row.groundingHits.join(", ") || "none detected")}</td>
    </tr>`).join("");
  const transcript = (report.transcript || []).map((turn) => `
    <article class="turn ${esc(turn.role)}">
      <div class="meta">${esc(turn.era || "Profile/Bio")} · ${esc(turn.role === "narrator" ? report.narrator.displayName : "Lori")}</div>
      <p>${esc(turn.text)}</p>
    </article>`).join("");
  const eraDetails = eras.map((row) => `
    <details>
      <summary>${esc(row.label)} — ${row.mechanical.eraSelectedAndSent ? "era routing PASS" : "era routing FAIL"}</summary>
      <h4>Lori after the Life Map switch</h4><blockquote>${esc(row.eraPrompt.finalText)}</blockquote>
      <h4>Narrator</h4><blockquote>${esc(row.narratorText)}</blockquote>
      <h4>Lori after the narrator</h4><blockquote>${esc(row.narratorEvidence.finalText)}</blockquote>
      <p><b>UI selected:</b> ${esc(row.narratorEvidence.selectedEra)} · <b>WebSocket sent:</b> ${esc(row.narratorEvidence.sentEra)} · <b>Extraction result received:</b> ${row.narratorEvidence.extractionReceived ? "yes" : "no/timeout"} · <b>Grounding anchors detected:</b> ${esc(row.groundingHits.join(", ") || "none")}</p>
    </details>`).join("");
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Walt seven-era Lori report</title>
<style>
body{font:17px/1.55 system-ui,sans-serif;max-width:1050px;margin:36px auto;padding:0 22px;color:#182033;background:#f7f8fb}h1,h2{line-height:1.2}.card,details,.turn{background:white;border:1px solid #d8ddea;border-radius:10px;padding:16px;margin:14px 0}table{width:100%;border-collapse:collapse;background:white}th,td{padding:10px;border:1px solid #d8ddea;text-align:left;vertical-align:top}.meta{font-weight:700;color:#4b5680}.lori{border-left:5px solid #6266d8}.narrator{border-left:5px solid #4c8d75}blockquote{margin:8px 0;padding:10px 14px;background:#f1f3f8;border-left:4px solid #aab2c8;white-space:pre-wrap}.bad{color:#a21d2d}.good{color:#146b3a}.warn{color:#8a6100}
.changed td{background:#fff6f6}.diff td{background:#fbfbfd}
.before,.after{padding:8px;margin:4px 0;white-space:pre-wrap;border-radius:6px}
.before{background:#f2f6ff;border-left:4px solid #6266d8}
.after{background:#fff4f4;border-left:4px solid #c2536a}
.r-persisted{color:#146b3a;font-weight:700}
.r-measurement_failed{color:#a21d2d;font-weight:700}
.r-not_measured{color:#8a6100;font-weight:700}code{background:#edf0f7;padding:2px 5px;border-radius:4px}</style></head><body>
<h1>Walt seven-era Lori report</h1>
<div class="card"><b>Run:</b> ${esc(report.runId)}<br><b>Narrator:</b> ${esc(report.narrator.displayName)} (<code>${esc(report.narrator.personId)}</code>)<br><b>Conversation:</b> <code>${esc(report.conversationId)}</code><br><b>Result:</b> <span class="${report.mechanicalPass ? "good" : "bad"}">${report.mechanicalPass ? "mechanical routing complete" : "mechanical failure"}</span><br><b>Important:</b> response quality requires human review; this report does not turn word matches into a quality score.</div>
<h2>Stored-bio check</h2>
<div class="card"><p><b>Narrator prompt:</b> ${esc(bio.prompt)}</p><p><b>Lori:</b> ${esc(bio.response)}</p><p><b>Stored-profile anchors Lori used:</b> ${esc((bio.hits || []).map((x) => x.key).join(", ") || "none detected")}</p></div>
<h2>Era routing summary</h2><table><thead><tr><th>Era</th><th>Selected + sent</th><th>Runtime era</th><th>Grounding detected</th></tr></thead><tbody>${eraRows}</tbody></table>
<h2>Era-by-era evidence</h2>${eraDetails}
${renderTraceSection(report)}
<h2>Complete test transcript</h2>${transcript}
<h2>Diagnostics</h2><div class="card"><p>Console errors: ${diagnostics.consoleErrors.length} · failed requests: ${diagnostics.failedRequests.length} · HTTP 4xx/5xx: ${diagnostics.httpErrors.length}</p><p>Response shaping: ${logEvidence.signals?.commControl || 0} comm-control · ${logEvidence.signals?.responseGuards || 0} response-guard · ${logEvidence.signals?.validatorFailures || 0} validator-failure lines.</p><p>Server snapshots and complete WebSocket evidence are in <code>report.json</code>.</p></div>
<details><summary>Relevant API log lines (${logEvidence.lines.length || 0})</summary><pre>${esc((logEvidence.lines || []).join("\n") || "api.log unavailable or no matching lines")}</pre></details>
</body></html>`;
}

function selfTest() {
  const ids = ERAS.map((e) => e.id);
  const expected = ["earliest_years", "early_school_years", "adolescence", "coming_of_age", "building_years", "later_years", "today"];
  if (JSON.stringify(ids) !== JSON.stringify(expected)) throw new Error("era registry is not the canonical seven in order");
  for (const era of ERAS) {
    const words = era.narrator.trim().split(/\s+/).length;
    if (words < 25 || words > 80) throw new Error(`${era.id} must remain a short conversational turn; got ${words} words`);
    if (!era.anchors.length) throw new Error(`${era.id} has no grounding anchors`);
  }
  const sample = { runId: "self-test", mechanicalPass: true, narrator: { displayName: "ZZ COHORT · Walt", personId: "x" }, conversationId: "c", bio: { prompt: BIO_PROBE, response: "South Boston, math teacher, Catherine, Quincy", hits: BIO_ANCHORS }, eras: ERAS.map((e) => ({ label: e.label, narratorText: e.narrator, eraPrompt: { finalText: "question?" }, narratorEvidence: { finalText: "reply?", sentEra: e.id, selectedEra: e.id }, groundingHits: e.anchors.slice(0, 1), mechanical: { eraSelectedAndSent: true } })), transcript: [], diagnostics: { consoleErrors: [], failedRequests: [], httpErrors: [] } };
  if (!renderHtml(sample).includes("Complete test transcript")) throw new Error("HTML report renderer failed");
  console.log("SELF-TEST PASS — seven eras, short turns, report renderer");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) { selfTest(); return; }
  const repoRoot = path.resolve(__dirname, "..", "..");
  const { row: narrator, journalPath } = readWaltFromJournal(repoRoot, args.runId);
  const outDir = path.resolve(args.out || path.join(repoRoot, ".runtime", "eval", "walt-seven-era-ui", nowId()));
  const apiLogPath = path.resolve(args.apiLog || path.join(repoRoot, ".runtime", "logs", "api.log"));
  const apiLogStart = logOffset(apiLogPath);
  const shotDir = path.join(outDir, "screenshots");
  fs.mkdirSync(shotDir, { recursive: true });

  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (_) { ({ chromium } = require("@playwright/test")); }

  /* ── Trace preflight ───────────────────────────────────────────────
   * The API is asked directly whether IT has tracing on. The previous
   * version probed a route that did not exist and then fell back to
   * accepting the presence of a trace DIRECTORY, so a stale directory
   * from an earlier day satisfied preflight while the API had tracing
   * off — and the run could reach PASS with no raw-response evidence.
   * An existing directory is not proof. `enabled === true` is. */
  const runStartedMs = Date.now();
  const traceHealth = await safeFetchJson(
    `${args.api}/api/health/response-trace`);
  if (!args.allowNoTrace) {
    if (!traceHealth.ok || traceHealth.body?.enabled !== true) {
      throw new Error(
        "REFUSED: the API reports response tracing is NOT enabled "
        + `(${JSON.stringify(traceHealth.body || traceHealth.error || traceHealth.status)}). `
        + "Restart the stack with HORNELORE_RESPONSE_TRACE=1 ./scripts/start_all.sh "
        + "so raw-vs-delivered evidence is recorded. An existing trace "
        + "directory is NOT proof: it can be stale. Override only for a "
        + "mechanical smoke test with --allow-no-trace.");
    }
  }

  const beforeServer = await serverSnapshot(args.api, narrator.person_id);
  const productPerson = beforeServer.person?.body?.person || null;
  const actualDisplayName = String(productPerson?.display_name || "");
  const expectedMarker = `ZZ COHORT ${args.runId} · `;
  if (!beforeServer.person?.ok || !productPerson) {
    throw new Error(`cannot read journaled Walt from the product: HTTP ${beforeServer.person?.status}`);
  }
  if (!actualDisplayName.startsWith(expectedMarker)) {
    throw new Error(`journaled Walt lacks the source run's product marker ${JSON.stringify(expectedMarker)}`);
  }

  const report = {
    schemaVersion: 1,
    startedAt: new Date().toISOString(),
    runId: args.runId,
    sourceJournal: journalPath,
    narrator: { personId: narrator.person_id, displayName: actualDisplayName, journalLabel: narrator.display_name, source: narrator.source },
    createsPerson: false,
    deletesAnything: false,
    ui: args.ui,
    api: args.api,
    profileSeed: null,
    bio: null,
    eras: [],
    transcript: [],
    diagnostics: { consoleErrors: [], failedRequests: [], httpErrors: [] },
  };

  const browser = await chromium.launch({ headless: !args.headed });
  const context = await browser.newContext({ viewport: { width: 1440, height: 950 } });
  const page = await context.newPage();
  await page.addInitScript(captureInitScript);
  page.on("console", (msg) => { if (msg.type() === "error") report.diagnostics.consoleErrors.push({ at: new Date().toISOString(), text: msg.text() }); });
  page.on("requestfailed", (request) => report.diagnostics.failedRequests.push({ at: new Date().toISOString(), url: request.url(), failure: request.failure()?.errorText || "failed" }));
  page.on("response", (response) => { if (response.status() >= 400) report.diagnostics.httpErrors.push({ at: new Date().toISOString(), status: response.status(), url: response.url() }); });

  try {
    await page.goto(args.ui, { waitUntil: "domcontentloaded", timeout: 60000 });
    await openExactNarrator(page, narrator.person_id, actualDisplayName);
    // ── Identity is verified against window.state.person_id, NOT a DOM
    // label. `id="lv80ActiveNarratorName"` is DUPLICATED in the product
    // (ui/hornelore1.0.html:3021 and again in the JS-built markup around
    // :6956, whose copy reads "Choose a narrator"), so a label read can
    // resolve to the copy that never updates. The 2026-08-31 run failed
    // here with `opened narrator label does not identify Walt: Choose a
    // narrator` while Walt was in fact open — openExactNarrator waits on
    // window.state.person_id and would have thrown first otherwise.
    //
    // This is a STRONGER check than the substring it replaces: an exact
    // UUID match against the journal, not the word "Walt". Both label
    // copies are captured as evidence of the product defect, which is
    // recorded and NOT repaired here.
    const identity = await page.evaluate(() => ({
      statePersonId: (window.state && window.state.person_id) || null,
      labelNodes: Array.from(
        document.querySelectorAll("#lv80ActiveNarratorName"))
        .map((n) => (n.textContent || "").trim()),
    }));
    report.identity = identity;
    report.openedName = identity.labelNodes[0] || null;
    report.duplicateIdDefect = identity.labelNodes.length > 1
      ? { id: "lv80ActiveNarratorName", copies: identity.labelNodes.length,
          texts: identity.labelNodes,
          note: "duplicate DOM id in the product; getElementById and a "
              + "plain locator return the first, which may be the copy "
              + "that never updates. Recorded, not repaired." }
      : null;
    if (identity.statePersonId !== narrator.person_id) {
      throw new Error(
        `opened narrator is not the journaled Walt: state.person_id=`
        + `${identity.statePersonId} expected=${narrator.person_id}`);
    }
    identity.openStatus = await page.evaluate(
      () => (window.state?.narratorOpen?.openStatus) || null);
    // VISIBLE IDENTITY IS STILL ASSERTED. The lifecycle wait removes the
    // race; it does not excuse the product from painting the right name.
    // Compared against the product's own display_name, not the word
    // "Walt", so a wrong narrator cannot pass on a substring.
    const visible = identity.labelNodes.find(
      (t) => t && t !== "Choose a narrator" && t !== "Loading…") || "";
    identity.visibleName = visible;
    if (!visible || !actualDisplayName.includes(visible.split(" · ").pop())) {
      throw new Error(
        `PRODUCT IDENTITY DEFECT: the open flow completed (openStatus=`
        + `${identity.openStatus}, state.person_id correct) but the visible `
        + `narrator card reads ${JSON.stringify(identity.labelNodes)} which `
        + `does not identify ${JSON.stringify(actualDisplayName)}`);
    }
    report.profileSeed = await pauseProfileSeedIfNeeded(page);
    report.conversationId = await page.evaluate(() => window.state?.chat?.conv_id || null);

    const bioEvidence = await sendTypedTurn(page, BIO_PROBE, null);
    const bioHits = BIO_ANCHORS.filter((group) => group.terms.some((term) => normalized(bioEvidence.finalText).includes(term)));
    report.bio = { prompt: BIO_PROBE, response: bioEvidence.finalText, hits: bioHits, evidence: bioEvidence };
    report.transcript.push({ era: null, role: "narrator", text: BIO_PROBE }, { era: null, role: "lori", text: bioEvidence.finalText || "" });

    for (const era of ERAS) {
      const eraPrompt = await selectEraAndWait(page, era);
      report.transcript.push({ era: era.id, role: "lori", kind: "era_prompt", text: eraPrompt.finalText || "" });
      const narratorEvidence = await sendTypedTurn(page, era.narrator, era.id);
      const hits = anchorHits(narratorEvidence.finalText, era.anchors);
      const rowEvidence = {
        id: era.id,
        label: era.label,
        narratorText: era.narrator,
        expectedAnchors: era.anchors,
        groundingHits: hits,
        eraPrompt,
        narratorEvidence,
        mechanical: {
          eraPromptSelectedAndSent: eraPrompt.selectedEra === era.id && eraPrompt.sentEra === era.id,
          narratorSelectedAndSent: narratorEvidence.selectedEra === era.id && narratorEvidence.sentEra === era.id,
        },
      };
      rowEvidence.mechanical.eraSelectedAndSent = rowEvidence.mechanical.eraPromptSelectedAndSent && rowEvidence.mechanical.narratorSelectedAndSent;
      report.eras.push(rowEvidence);
      report.transcript.push({ era: era.id, role: "narrator", text: era.narrator }, { era: era.id, role: "lori", text: narratorEvidence.finalText || "" });
      await page.screenshot({ path: path.join(shotDir, `${String(report.eras.length).padStart(2, "0")}-${era.id}.png`), fullPage: false });
    }

    report.websocket = await page.evaluate(() => window.__waltEraCapture);
    report.afterServer = await serverSnapshot(args.api, narrator.person_id);
    // Give parked traces a moment to be closed by background extraction.
    await page.waitForTimeout(4000);
    const traced = tracesForRun(repoRoot, runStartedMs, narrator.person_id,
                                report.conversationId);
    report.traceHealth = traceHealth.body || null;
    report.responseTrace = {
      available: traced.available,
      dir: traced.dir,
      turns: traced.records.length,
      records: traced.records,
      retention: retentionSummary(traced.records),
    };

    /* ── Run-level retention evidence ──────────────────────────────
     * These are BEFORE/AFTER SNAPSHOTS of the whole run, and they are
     * labelled as such. They are NOT per-turn attribution and the
     * report must not present them as if they were: a fact that
     * appeared between the first and last turn cannot be assigned to a
     * particular turn from a snapshot pair alone. Per-turn attribution
     * exists only where a source turn id is recorded on the fact. */
    const beforeFacts = report.beforeServer?.facts?.body?.facts || [];
    const afterFacts = report.afterServer?.facts?.body?.facts || [];
    const keyOf = (f) => `${f.field_key || f.fieldPath || ""}=${f.value || ""}`;
    const beforeKeys = new Set(beforeFacts.map(keyOf));
    const newFacts = afterFacts.filter((f) => !beforeKeys.has(keyOf(f)));
    const sourceTurnIds = new Set(report.responseTrace.records
      .flatMap((r) => Object.values(r.context?.turn_row_ids || {}))
      .map(String));

    // Memoir source, queried at the API ORIGIN. The UI asks :8082 for
    // this route, which serves files and 404s — that is a broken
    // measurement, not evidence of absence, and it is why this is
    // queried here rather than trusted from the browser.
    const memoir = await safeFetchJson(
      `${args.api}/api/memoir/canonical?person_id=`
      + encodeURIComponent(narrator.person_id));

    report.retentionEvidence = {
      scope: "run-level before/after snapshots, NOT per-turn attribution",
      bio_facts: {
        result: report.afterServer?.facts?.ok
          ? (newFacts.length ? "persisted" : "measured_absent")
          : "measurement_failed",
        before: beforeFacts.length,
        after: afterFacts.length,
        added: newFacts.length,
        addedRows: newFacts,
        perTurnAttribution: newFacts.filter((f) =>
          sourceTurnIds.has(String(f.source_turn_id || f.turn_id || ""))).length,
        attributionNote: "per-turn attribution counts only facts whose "
          + "recorded source turn matches a durable row id from this run",
      },
      chronology: {
        result: report.afterServer?.chronology?.ok
          ? "persisted" : "measurement_failed",
        before: report.beforeServer?.chronology?.body || null,
        after: report.afterServer?.chronology?.body || null,
      },
      life_map: {
        result: report.afterServer?.projection?.ok
          ? "persisted" : "measurement_failed",
        before: report.beforeServer?.projection?.body || null,
        after: report.afterServer?.projection?.body || null,
      },
      memoir_source: {
        result: memoir.ok ? (memoir.body ? "persisted" : "measured_absent")
                          : "measurement_failed",
        queriedAt: memoir.url,
        status: memoir.status,
        note: memoir.ok ? null
          : "queried at the API origin; a failure here is measurement_failed "
          + "and is NOT evidence that memoir data is absent",
      },
      rolling_summary: { result: "not_measured",
        note: "no instrumentation exists for this stage" },
      archive: { result: "not_measured",
        note: "no instrumentation exists for this stage" },
    };
    report.beforeServer = beforeServer;
    /* Model turns that SHOULD have produced a trace: the bio probe, plus
     * one era prompt and one narrator turn per era. A run that carried
     * every era but recorded no raw-response evidence has not done the
     * job this work order asks for, so trace completeness is part of
     * PASS rather than a footnote. */
    const expectedTraces = 1 + (report.eras.length * 2);
    const tracedTurns = report.responseTrace.turns;
    const withRaw = report.responseTrace.records.filter(
      (r) => typeof r.raw_text === "string" && r.raw_text.length > 0).length;
    const instrumentationFailures = report.responseTrace.records.filter(
      (r) => r.instrumentation_failed === true);
    report.traceCompleteness = {
      expectedTraces, tracedTurns, withRaw,
      instrumentationFailures: instrumentationFailures.length,
      missingRequiredContext: instrumentationFailures
        .flatMap((r) => r.missing_required_context || []),
      complete: tracedTurns >= expectedTraces && withRaw === tracedTurns
                && instrumentationFailures.length === 0,
    };
    report.mechanicalPass = report.eras.length === 7
      && report.eras.every((e) => e.mechanical.eraSelectedAndSent)
      && report.eras.every((e) => Boolean(e.eraPrompt.finalText && e.narratorEvidence.finalText))
      && Boolean(report.bio.response)
      && report.traceCompleteness.complete;
  } catch (error) {
    report.error = String(error && error.stack || error);
    report.mechanicalPass = false;
    try { report.websocket = await page.evaluate(() => window.__waltEraCapture); } catch (_) {}
    report.beforeServer = beforeServer;
    report.afterServer = await serverSnapshot(args.api, narrator.person_id);
  } finally {
    report.finishedAt = new Date().toISOString();
    report.apiLogEvidence = readRelevantLogDelta(
      apiLogPath, apiLogStart, report.conversationId, narrator.person_id,
    );
    fs.writeFileSync(path.join(outDir, "report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
    fs.writeFileSync(path.join(outDir, "report.html"), renderHtml(report), "utf8");
    await context.close();
    await browser.close();
  }

  console.log(`${report.mechanicalPass ? "PASS" : "FAIL"} — ${report.eras.length}/7 eras completed`);
  console.log(`HTML report: ${path.join(outDir, "report.html")}`);
  console.log(`JSON evidence: ${path.join(outDir, "report.json")}`);
  if (report.bio) console.log(`Stored-bio anchors heard from Lori: ${report.bio.hits.map((x) => x.key).join(", ") || "none detected — review transcript"}`);
  if (report.error) console.error(report.error);
  process.exitCode = report.mechanicalPass ? 0 : 1;
}

main().catch((error) => { console.error(error && error.stack || error); process.exitCode = 2; });
