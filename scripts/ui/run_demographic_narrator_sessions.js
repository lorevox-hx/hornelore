#!/usr/bin/env node
/*
 * Real-UI listening run across the ten scripted demographic narrators.
 *
 * One narrator is completed at a time:
 *   open exact journaled UUID -> real Life Map era -> short fixture excerpt
 *   -> wait for Lori DONE -> wait for TTS completion -> next turn
 *   -> Operator tab -> real Wrap Up Session -> transcript TXT/JSON.
 *
 * Creates no narrator and deletes nothing.  Downloads are saved below the
 * evaluation run rather than the operator's general Downloads directory.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const DESTRUCTIVE = /delete|erase|remove|destroy|purge/i;

function parseArgs(argv) {
  const out = {
    ui: "http://localhost:8082/ui/hornelore1.0.html",
    api: "http://localhost:8000",
    headed: false,
    turnsPerEra: 1,
    continueOnFailure: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i];
    if (["--headed", "--self-test", "--continue-on-failure"].includes(key)) {
      out[key.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = true;
      continue;
    }
    if (!key.startsWith("--")) throw new Error(`unexpected argument: ${key}`);
    const value = argv[++i];
    if (!value || value.startsWith("--")) throw new Error(`missing value for ${key}`);
    out[key.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = value;
  }
  out.turnsPerEra = Number(out.turnsPerEra);
  if (![1, 2, 3].includes(out.turnsPerEra)) throw new Error("--turns-per-era must be 1, 2, or 3");
  if (!out.selfTest && !out.sourceRun && !out.resume) {
    throw new Error("--source-run is required for a new run (or use --resume)");
  }
  return out;
}

function timestampId() {
  return new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
}

function safeName(value) {
  return String(value || "narrator").normalize("NFKD")
    .replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase();
}

function esc(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function writeJson(filename, value) {
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  fs.writeFileSync(filename, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function readJson(filename) {
  return JSON.parse(fs.readFileSync(filename, "utf8"));
}

function buildPlan(repoRoot, sourceRun, turnsPerEra) {
  const candidates = [
    process.env.HORNELORE_PYTHON,
    path.join(repoRoot, ".venv-gpu", "bin", "python"),
    "python3",
  ].filter(Boolean);
  const script = path.join(repoRoot, "scripts", "build_demographic_cohort_ui_plan.py");
  let last = null;
  for (const python of candidates) {
    const proc = spawnSync(python, [script, "--run-id", sourceRun,
      "--turns-per-era", String(turnsPerEra)], { cwd: repoRoot, encoding: "utf8" });
    last = proc;
    if (!proc.error && proc.status === 0) return JSON.parse(proc.stdout);
    if (proc.error && proc.error.code === "ENOENT") continue;
    break;
  }
  throw new Error(`plan builder refused: ${last?.stderr || last?.error || "unknown failure"}`);
}

function installCapture() {
  window.__demographicCapture = {
    sent: [], received: [], tts: [], console: [], installedAt: new Date().toISOString(),
  };
  const NativeWebSocket = window.WebSocket;
  function WrappedWebSocket(...args) {
    const socket = new NativeWebSocket(...args);
    const nativeSend = socket.send;
    socket.send = function (data) {
      let parsed = null;
      try { parsed = JSON.parse(String(data)); } catch (_) {}
      window.__demographicCapture.sent.push({ at: new Date().toISOString(), parsed, raw: String(data) });
      return nativeSend.call(this, data);
    };
    socket.addEventListener("message", (event) => {
      let parsed = null;
      try { parsed = JSON.parse(String(event.data)); } catch (_) {}
      window.__demographicCapture.received.push({ at: new Date().toISOString(), parsed, raw: String(event.data) });
    });
    return socket;
  }
  WrappedWebSocket.prototype = NativeWebSocket.prototype;
  ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach((key) => {
    Object.defineProperty(WrappedWebSocket, key, { value: NativeWebSocket[key] });
  });
  window.WebSocket = WrappedWebSocket;

  const nativeFetch = window.fetch.bind(window);
  window.fetch = async function (...args) {
    const url = String(args[0]?.url || args[0] || "");
    const isTts = url.includes("/api/tts/speak_stream");
    const row = isTts ? { at: new Date().toISOString(), url, status: null, finishedAt: null, error: null } : null;
    if (row) window.__demographicCapture.tts.push(row);
    try {
      const response = await nativeFetch(...args);
      if (row) { row.status = response.status; row.ok = response.ok; row.finishedAt = new Date().toISOString(); }
      return response;
    } catch (error) {
      if (row) { row.error = String(error); row.finishedAt = new Date().toISOString(); }
      throw error;
    }
  };
}

async function ttsState(page) {
  return page.evaluate(() => {
    let speaking = null, busy = null, queued = null;
    try { speaking = Boolean(isLoriSpeaking); } catch (_) {}
    try { busy = Boolean(ttsBusy); } catch (_) {}
    try { queued = Number(ttsQueue.length); } catch (_) {}
    return {
      speaking, busy, queued,
      finishedAt: Number(window.state?.narratorTurn?.ttsFinishedAt || 0),
      requests: (window.__demographicCapture?.tts || []).length,
    };
  });
}

async function waitForAudioIdle(page, timeout = 180000) {
  await page.waitForFunction(() => {
    let speaking = false, busy = false, queued = 0;
    try { speaking = Boolean(isLoriSpeaking); } catch (_) {}
    try { busy = Boolean(ttsBusy); } catch (_) {}
    try { queued = Number(ttsQueue.length || 0); } catch (_) {}
    return !speaking && !busy && queued === 0;
  }, null, { timeout });
  await page.waitForTimeout(350);
}

async function counts(page) {
  const audio = await ttsState(page);
  return page.evaluate((audioState) => ({
    sent: window.__demographicCapture.sent.length,
    received: window.__demographicCapture.received.length,
    done: window.__demographicCapture.received.filter((x) => x.parsed?.type === "done").length,
    aiBubbles: document.querySelectorAll("#chatMessages .bubble-ai").length,
    audio: audioState,
  }), audio);
}

async function waitForResponseAndTts(page, before) {
  await page.waitForFunction(
    (n) => window.__demographicCapture.received.filter((x) => x.parsed?.type === "done").length > n,
    before.done, { timeout: 180000 });

  // TTS is part of the acceptance, not an optional sleep.  A successful
  // request must occur and the product's own drain-complete timestamp must
  // advance before another action is allowed.
  await page.waitForFunction(
    (n) => window.__demographicCapture.tts.length > n,
    before.audio.requests, { timeout: 30000 });
  await page.waitForFunction(
    (previous) => Number(window.state?.narratorTurn?.ttsFinishedAt || 0) > previous,
    before.audio.finishedAt, { timeout: 240000 });
  await waitForAudioIdle(page, 30000);

  const after = await counts(page);
  const ttsRows = await page.evaluate(
    ({ start }) => window.__demographicCapture.tts.slice(start),
    { start: before.audio.requests });
  if (!ttsRows.length || ttsRows.some((r) => r.ok !== true)) {
    throw new Error(`TTS did not complete successfully: ${JSON.stringify(ttsRows)}`);
  }
  return { after, ttsRows };
}

/* Every completed action must be provably THE action we asked for.
 * Without this a run could report COMPLETE having sent the wrong era,
 * generated twice, or carried no correlation id at all. */
function assertActionIntegrity(evidence, expectedEra, what) {
  const fail = (why) => { throw new Error(`${what}: ${why}`); };
  if (!evidence.clientTurnId) {
    fail("no client turn id on the sent frame — the turn cannot be "
       + "correlated to a trace record");
  }
  if (evidence.sentCount !== 1) {
    fail(`expected exactly one start_turn, saw ${evidence.sentCount}`);
  }
  if (evidence.doneCount !== 1) {
    fail(`expected exactly one done, saw ${evidence.doneCount}`);
  }
  if (expectedEra !== null && expectedEra !== undefined) {
    if (evidence.selectedEra !== expectedEra) {
      fail(`UI era is ${JSON.stringify(evidence.selectedEra)}, expected `
         + `${JSON.stringify(expectedEra)}`);
    }
    if (evidence.sentEra !== expectedEra) {
      fail(`era sent on the wire is ${JSON.stringify(evidence.sentEra)}, `
         + `expected ${JSON.stringify(expectedEra)}`);
    }
  }
  return evidence;
}

async function actionEvidence(page, before, expectedEra) {
  const evidence = await page.evaluate(({ startSent, startReceived, expectedEra }) => {
    const cap = window.__demographicCapture;
    const sent = cap.sent.slice(startSent).filter((x) => x.parsed?.type === "start_turn");
    const done = cap.received.slice(startReceived).filter((x) => x.parsed?.type === "done");
    const lastSent = sent[sent.length - 1]?.parsed || null;
    const lastDone = done[done.length - 1]?.parsed || null;
    return {
      expectedEra,
      selectedEra: window.state?.session?.currentEra || null,
      sentEra: lastSent?.params?.runtime71?.current_era || null,
      messageKind: lastSent?.params?.message_kind || null,
      // The UI sends params.client_turn_id (ui/js/app.js). Reading
      // params.turn_id recorded null for EVERY turn, which made the
      // correlation id look present in the schema and absent in fact.
      clientTurnId: lastSent?.params?.client_turn_id || null,
      narratorText: lastSent?.message || null,
      finalText: lastDone?.final_text || null,
      sentCount: sent.length,
      doneCount: done.length,
      sentFrames: sent,
      doneFrames: done,
    };
  }, { startSent: before.sent, startReceived: before.received, expectedEra });
  evidence.doneEventsObserved = evidence.doneFrames.length;
  return evidence;
}

async function runAction(page, action, expectedEra, what = "action") {
  await waitForAudioIdle(page);
  const before = await counts(page);
  await action();
  const timing = await waitForResponseAndTts(page, before);
  const evidence = await actionEvidence(page, before, expectedEra);
  evidence.tts = timing.ttsRows;
  evidence.ttsFinishedAt = timing.after.audio.finishedAt;
  if (!evidence.finalText) throw new Error(`${what}: Lori completed without final_text`);
  // The single funnel both era prompts and narrator turns pass through,
  // so one gate covers every model turn this runner causes.
  assertActionIntegrity(evidence, expectedEra, what);
  return evidence;
}

async function openSwitcher(page) {
  const alreadyOpen = await page.evaluate(() => {
    const pop = document.getElementById("lv80NarratorSwitcher");
    return Boolean(pop && pop.matches(":popover-open"));
  });
  if (alreadyOpen) return;
  const card = page.locator("#lv80ActiveNarratorCard");
  if (await card.isVisible()) await card.click();
  else await page.evaluate(() => window.lv80OpenNarratorSwitcher?.());
  await page.waitForFunction(() => {
    const pop = document.getElementById("lv80NarratorSwitcher");
    return pop && pop.matches(":popover-open");
  }, null, { timeout: 15000 });
}

async function openExactNarrator(page, narrator) {
  await waitForAudioIdle(page);
  await openSwitcher(page);
  await page.waitForFunction(
    (pid) => Array.from(document.querySelectorAll("button")).some((b) =>
      b.textContent.trim() === "Open" && (b.getAttribute("onclick") || "").includes(pid)),
    narrator.person_id, { timeout: 45000 });
  const button = page.locator(`button[onclick*="${narrator.person_id}"]`).filter({ hasText: /^Open$/ });
  if (await button.count() !== 1) throw new Error(`exact Open button is not unique for ${narrator.source}`);
  const details = await button.evaluate((b) => ({ text: b.textContent.trim(), handler: b.getAttribute("onclick") || "", disabled: Boolean(b.disabled) }));
  if (details.disabled || details.text !== "Open" || DESTRUCTIVE.test(`${details.text} ${details.handler}`)) {
    throw new Error("REFUSED: resolved narrator action is not a safe Open button");
  }
  await button.click();
  await page.waitForFunction((pid) => window.state?.person_id === pid,
    narrator.person_id, { timeout: 60000 });
  await page.waitForFunction(() => {
    const status = window.state?.narratorOpen?.openStatus;
    return status && status !== "loading" && status !== "idle";
  }, null, { timeout: 60000 });
  /* ── Identity: the PRODUCT name, not the journal label ────────────
   * The plan carries the fixture label ('Alex Eunseo Park (they/them)')
   * while the narrator card shows the product name
   * ('ZZ COHORT <run-id> · Alex'). Neither direction of the old
   * substring match can succeed between those two, so this wait could
   * never pass. The plan now emits `product_marker`; the card must
   * START with it, which is exact rather than a substring guess and
   * cannot be satisfied by a stale copy showing a PREVIOUS narrator.
   * `state.person_id` is already asserted above, so the two together
   * pin both the identity and the paint. */
  /* ── EXACT product display name ────────────────────────────────
   * `startsWith(product_marker)` was my own regression: all ten
   * narrators share "ZZ COHORT <run> · ", so a stale card still
   * painted with a DIFFERENT cohort narrator satisfied it — exactly
   * the confusion the person-id check exists to prevent, let back in
   * through the visible name. The plan now derives the exact name via
   * the same mark_intake_payload the cohort runner used, so equality
   * is available and is what is required. */
  await page.waitForFunction((expected) => Array.from(
      document.querySelectorAll("#lv80ActiveNarratorName"))
    .some((n) => (n.textContent || "").trim() === expected),
    narrator.product_display_name, { timeout: 60000 });
  const paintedName = await page.evaluate(() => Array.from(
      document.querySelectorAll("#lv80ActiveNarratorName"))
    .map((n) => (n.textContent || "").trim()));
  if (!paintedName.includes(narrator.product_display_name)) {
    throw new Error(
      `narrator card shows ${JSON.stringify(paintedName)}, expected exactly `
      + `${JSON.stringify(narrator.product_display_name)}`);
  }
  await page.waitForFunction(() => {
    const input = document.getElementById("chatInput");
    return input && !input.disabled && (!window._loriIsBusy || !window._loriIsBusy());
  }, null, { timeout: 120000 });
  // An automatic greeting is allowed, but it must finish speaking before
  // this runner changes era or types for the narrator.
  await page.waitForTimeout(800);
  await waitForAudioIdle(page);
  const convId = await page.evaluate(() => window.state?.chat?.conv_id || null);
  if (!convId || convId === "default") throw new Error("narrator did not receive a fresh conversation id");
  return convId;
}

async function pauseProfileSeed(page) {
  await page.locator("#lvShellTabOperator").click();
  await page.waitForFunction(() => {
    const s = window.LorevoxProfileSeedAuthority?.snapshot?.();
    return s && (s.status === "resolved" || s.status === "failed");
  }, null, { timeout: 30000 });
  const before = await page.evaluate(() => window.LorevoxProfileSeedAuthority?.snapshot?.() || null);
  if (before?.status === "failed") throw new Error("Profile Seed authority failed");
  const status = before?.data?.status || before?.status;
  let usedButton = false;
  if (status === "active") {
    const button = page.locator("#psPauseBtn");
    if (!(await button.isVisible())) throw new Error("active Profile Seed has no visible Pause button");
    await button.click();
    usedButton = true;
    await page.waitForFunction(() => {
      const s = window.LorevoxProfileSeedAuthority?.snapshot?.();
      return (s?.data?.status || s?.status) === "paused";
    }, null, { timeout: 30000 });
  }
  const after = await page.evaluate(() => window.LorevoxProfileSeedAuthority?.snapshot?.() || null);
  await page.locator("#lvShellTabNarrator").click();
  return { before, after, usedButton };
}

async function selectEra(page, era) {
  return runAction(page, async () => {
    const button = page.locator(`.lv-interview-lifemap-era-btn[data-era-id="${era.era_id}"]`);
    if (await button.count() !== 1) throw new Error(`expected exactly one Life Map button for ${era.era_id}`);
    await button.click();
    const modal = page.locator(".lv-interview-confirm-overlay");
    await modal.waitFor({ state: "visible", timeout: 10000 });
    await modal.locator(".lv-interview-confirm-continue").click();
    await page.waitForFunction((id) => window.state?.session?.currentEra === id,
      era.era_id, { timeout: 10000 });
  }, era.era_id, `era prompt ${era.era_id}`);
}

async function sendNarratorTurn(page, text, eraId) {
  return runAction(page, async () => {
    const input = page.locator("#chatInput");
    await input.click();
    await input.type(text, { delay: 1 });
    if (await input.inputValue() !== text) throw new Error("real composer did not preserve narrator text");
    await page.locator("#lv80SendBtn").click();
  }, eraId);
}

class DownloadCollector {
  constructor(page) {
    this.page = page;
    this.dir = null;
    this.records = [];
    this.pending = [];
    page.on("download", (download) => {
      const targetDir = this.dir;
      const record = { suggested: download.suggestedFilename(), saved: null, error: null };
      this.records.push(record);
      const promise = (async () => {
        if (!targetDir) throw new Error("download arrived with no active narrator directory");
        fs.mkdirSync(targetDir, { recursive: true });
        let filename = path.basename(download.suggestedFilename() || `download-${Date.now()}`);
        let target = path.join(targetDir, filename);
        let n = 2;
        while (fs.existsSync(target)) {
          const ext = path.extname(filename), stem = path.basename(filename, ext);
          target = path.join(targetDir, `${stem}-${n++}${ext}`);
        }
        await download.saveAs(target);
        record.saved = target;
      })().catch((error) => { record.error = String(error); });
      this.pending.push(promise);
    });
  }
  start(dir) { this.dir = dir; this.records = []; this.pending = []; }
  /* Wait for what must arrive, not for a guess at how long it takes.
   * A fixed 500ms passed on a fast machine and would fail on a slow
   * one, and a missing download would surface as a confusing absence
   * later rather than as the timeout it actually is. */
  async finish({ requireSuffixes = [".zip", ".md"], timeoutMs = 120000 } = {}) {
    const deadline = Date.now() + timeoutMs;
    const have = (suffix) => this.records.some(
      (r) => !r.error && String(r.saved || "").toLowerCase().endsWith(suffix));
    while (Date.now() < deadline) {
      await Promise.all(this.pending);
      if (requireSuffixes.every(have)) break;
      await this.page.waitForTimeout(250);
    }
    await Promise.all(this.pending);
    const records = this.records.slice();
    this.dir = null;
    if (records.some((r) => r.error)) throw new Error(`download failed: ${JSON.stringify(records)}`);
    const missing = requireSuffixes.filter((sfx) => !records.some(
      (r) => String(r.saved || "").toLowerCase().endsWith(sfx)));
    if (missing.length) {
      throw new Error(
        `wrap-up downloads never arrived: missing ${missing.join(", ")} after `
        + `${timeoutMs}ms; saved ${JSON.stringify(records.map((r) => r.saved))}`);
    }
    return records;
  }
}

async function wrapUpThroughOperator(page, collector, narratorDir) {
  await waitForAudioIdle(page);
  await page.locator("#lvShellTabOperator").click();
  const downloadsDir = path.join(narratorDir, "downloads");
  collector.start(downloadsDir);
  await page.evaluate(() => {
    const monitor = window.lvSessionHealthMonitor;
    if (!monitor || typeof monitor.runWrapUp !== "function") throw new Error("session health monitor unavailable");
    if (!window.__demographicOriginalWrapUp) {
      window.__demographicOriginalWrapUp = monitor.runWrapUp.bind(monitor);
      monitor.runWrapUp = async function (...args) {
        window.__demographicWrapState = { done: false, result: null, error: null };
        try {
          const result = await window.__demographicOriginalWrapUp(...args);
          window.__demographicWrapState = { done: true, result, error: null };
          return result;
        } catch (error) {
          window.__demographicWrapState = { done: true, result: null, error: String(error) };
          throw error;
        }
      };
    }
    window.__demographicWrapState = { done: false, result: null, error: null };
  });
  const button = page.getByRole("button", { name: "Wrap Up Session", exact: true });
  if (!(await button.isVisible())) throw new Error("Wrap Up Session button is not visible on Operator tab");
  await button.click();
  await page.waitForFunction(() => window.__demographicWrapState?.done === true,
    null, { timeout: 180000 });
  const wrap = await page.evaluate(() => window.__demographicWrapState);
  const downloads = await collector.finish();
  if (wrap.error) throw new Error(`Wrap Up Session failed: ${wrap.error}`);
  if (wrap.result?.exportError) throw new Error(`session archive export failed: ${wrap.result.exportError}`);
  if (!downloads.some((d) => String(d.saved).endsWith(".zip"))) throw new Error("Wrap Up Session produced no archive ZIP");
  if (!downloads.some((d) => String(d.saved).endsWith(".md"))) throw new Error("Wrap Up Session produced no operator log");
  await page.screenshot({ path: path.join(narratorDir, "operator-wrap-up.png"), fullPage: true });
  return { wrap, downloads };
}

async function fetchArtifact(url, filename, asJson = false) {
  const response = await fetch(url);
  const body = await response.text();
  if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}: ${body.slice(0, 200)}`);
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  fs.writeFileSync(filename, asJson
    ? `${JSON.stringify(JSON.parse(body), null, 2)}\n`
    : body, "utf8");
  return asJson ? JSON.parse(body) : body;
}

async function exportTranscripts(api, narrator, conversationId, narratorDir) {
  const dir = path.join(narratorDir, "downloads");
  const q = `person_id=${encodeURIComponent(narrator.person_id)}&session_id=${encodeURIComponent(conversationId)}`;
  const txtPath = path.join(dir, "transcript.txt");
  const jsonPath = path.join(dir, "transcript.json");
  const txt = await fetchArtifact(`${api}/api/transcript/export/txt?${q}`, txtPath, false);
  const data = await fetchArtifact(`${api}/api/transcript/export/json?${q}`, jsonPath, true);
  if (data.session_id !== conversationId) throw new Error("transcript export returned the wrong conversation");
  if (!Array.isArray(data.events) || !data.events.length) throw new Error("transcript export is empty");
  return { txtPath, jsonPath, textChars: txt.length, eventCount: data.events.length, data };
}

function validateDurableTranscript(report, exported) {
  const events = exported.data.events || [];
  const texts = events.map((e) => String(e.content || ""));
  const missingNarrator = report.eras.flatMap((era) => era.turns)
    .filter((turn) => !texts.includes(turn.narratorText));
  const missingLori = report.eras.flatMap((era) => [era.eraPrompt, ...era.turns])
    .filter((turn) => !texts.includes(turn.loriText));
  return {
    narratorInputsExpected: report.eras.reduce((n, e) => n + e.turns.length, 0),
    loriResponsesExpected: report.eras.reduce((n, e) => n + e.turns.length + 1, 0),
    missingNarrator: missingNarrator.map((x) => x.narratorText),
    missingLori: missingLori.map((x) => x.loriText),
    complete: missingNarrator.length === 0 && missingLori.length === 0,
  };
}

function narratorHtml(report) {
  const rows = report.eras.map((era) => `<section><h2>${esc(era.label)}</h2>
    <div class="lori"><b>Lori after era switch</b><p>${esc(era.eraPrompt.loriText)}</p></div>
    ${era.turns.map((turn) => `<div class="narrator"><b>Narrator</b><p>${esc(turn.narratorText)}</p></div>
      <div class="lori"><b>Lori</b><p>${esc(turn.loriText)}</p><small>TTS requests: ${turn.tts.length}</small></div>`).join("")}</section>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>${esc(report.displayName)}</title>
  <style>body{font:16px/1.55 system-ui;max-width:900px;margin:30px auto;padding:0 20px;color:#172033}section,.meta{border:1px solid #d8deea;border-radius:10px;padding:14px;margin:16px 0}.narrator,.lori{padding:10px 14px;margin:9px 0;border-radius:8px}.narrator{background:#eef8f3;border-left:4px solid #398368}.lori{background:#f0f1fb;border-left:4px solid #656bd3}code{background:#edf0f5;padding:2px 4px}</style></head><body>
  <h1>${esc(report.displayName)}</h1><div class="meta"><b>Person:</b> <code>${esc(report.personId)}</code><br><b>Conversation:</b> <code>${esc(report.conversationId)}</code><br><b>Result:</b> ${report.complete ? "COMPLETE" : "INCOMPLETE"}<br><b>Operator wrap-up:</b> ${esc(report.wrapUp?.wrap?.result?.result?.status || "unknown")}<br><b>Durable transcript:</b> ${report.durableValidation?.complete ? "complete" : "incomplete"}</div>${rows}</body></html>`;
}

function combinedHtml(run) {
  const rows = run.narrators.map((r) => `<tr><td>${esc(r.fixtureLabel)}</td><td>${r.complete ? "complete" : "failed"}</td><td>${r.eras?.length || 0}</td><td>${r.responseCount || 0}</td><td>${esc(r.operatorStatus || "—")}</td><td><a href="${esc(r.relativeReport || "")}">report</a></td></tr>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>Lori demographic cohort</title><style>body{font:16px/1.5 system-ui;max-width:1100px;margin:30px auto;padding:0 20px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #ccd3df;padding:9px;text-align:left}</style></head><body><h1>Lori demographic narrator cohort</h1><p>Source run: <code>${esc(run.sourceRun)}</code></p><p>${run.completedCount}/${run.expectedCount} narrators complete. Exact transcripts, operator logs, archives, and screenshots are stored inside each narrator folder.</p><table><thead><tr><th>Narrator</th><th>Status</th><th>Eras</th><th>Lori responses</th><th>Operator</th><th>Evidence</th></tr></thead><tbody>${rows}</tbody></table></body></html>`;
}

function selfTest() {
  const args = parseArgs(["--self-test"]);
  if (!args.selfTest) throw new Error("argument parser self-test failed");
  if (safeName("Tomasita Reyes Cantú") !== "tomasita-reyes-cantu") throw new Error("safeName failed");
  const html = combinedHtml({ sourceRun: "r", completedCount: 1, expectedCount: 1,
    narrators: [{ fixtureLabel: "Test", complete: true, eras: [1], responseCount: 2,
      operatorStatus: "GREEN", relativeReport: "test/report.html" }] });
  if (!html.includes("Lori demographic narrator cohort")) throw new Error("HTML renderer failed");
  console.log("SELF-TEST PASS — arguments, filenames, combined report");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.selfTest) return selfTest();
  const repoRoot = path.resolve(__dirname, "..", "..");
  const evalRoot = path.join(repoRoot, ".runtime", "eval", "lori-demographic-cohort");
  let outDir, plan, checkpoint;
  if (args.resume) {
    if (!/^[A-Za-z0-9._-]+$/.test(args.resume)) throw new Error("unsafe --resume id");
    outDir = path.join(evalRoot, args.resume);
    plan = readJson(path.join(outDir, "plan.json"));
    checkpoint = readJson(path.join(outDir, "checkpoint.json"));
    if (args.sourceRun && args.sourceRun !== plan.source_run_id) throw new Error("resume cannot change source run");
  } else {
    outDir = path.resolve(args.out || path.join(evalRoot, timestampId()));
    if (fs.existsSync(outDir)) throw new Error(`output directory already exists: ${outDir}`);
    plan = buildPlan(repoRoot, args.sourceRun, args.turnsPerEra);
    fs.mkdirSync(outDir, { recursive: true });
    writeJson(path.join(outDir, "plan.json"), plan);
    checkpoint = { schemaVersion: 1, sourceRun: plan.source_run_id,
      createdAt: new Date().toISOString(), completedSources: [], narrators: [] };
    writeJson(path.join(outDir, "checkpoint.json"), checkpoint);
  }
  if (plan.narrator_count !== 10) throw new Error(`refused: expected 10 scripted narrators, got ${plan.narrator_count}`);

  let chromium;
  try { ({ chromium } = require("playwright")); }
  catch (_) { ({ chromium } = require("@playwright/test")); }
  const browser = await chromium.launch({ headless: !args.headed });
  const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 900 } });
  await context.addInitScript(installCapture);
  const page = await context.newPage();
  const collector = new DownloadCollector(page);
  const diagnostics = { console: [], pageErrors: [], failedRequests: [] };
  page.on("console", (msg) => {
    if (["error", "warning"].includes(msg.type())) diagnostics.console.push({ at: new Date().toISOString(), type: msg.type(), text: msg.text() });
  });
  page.on("pageerror", (error) => diagnostics.pageErrors.push({ at: new Date().toISOString(), error: String(error) }));
  page.on("requestfailed", (request) => diagnostics.failedRequests.push({ at: new Date().toISOString(), url: request.url(), error: request.failure()?.errorText || "failed" }));
  await page.goto(args.ui, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForFunction(() => {
    let ready = false;
    try { ready = Boolean(wsReady); } catch (_) {}
    return window.state && window.state.narratorOpen && ready;
  },
    null, { timeout: 180000 });

  let fatal = null;
  for (let index = 0; index < plan.narrators.length; index += 1) {
    const narrator = plan.narrators[index];
    if (checkpoint.completedSources.includes(narrator.source)) {
      console.log(`[skip] ${narrator.fixture_label} — already complete`);
      continue;
    }
    const slug = `${String(index + 1).padStart(2, "0")}-${safeName(narrator.fixture_label)}`;
    const narratorDir = path.join(outDir, "narrators", slug);
    fs.mkdirSync(path.join(narratorDir, "downloads"), { recursive: true });
    const report = {
      source: narrator.source, fixtureLabel: narrator.fixture_label,
      displayName: narrator.display_name, personId: narrator.person_id,
      startedAt: new Date().toISOString(), complete: false, eras: [],
    };
    console.log(`\n[${index + 1}/10] ${narrator.fixture_label}`);
    try {
      report.conversationId = await openExactNarrator(page, narrator);
      report.profileSeed = await pauseProfileSeed(page);
      for (const era of narrator.eras) {
        console.log(`  [era] ${era.label}`);
        const eraPrompt = await selectEra(page, era);
        const eraRow = {
          eraId: era.era_id, label: era.label,
          sourceWords: era.source_words,
          eraPrompt: { loriText: eraPrompt.finalText, tts: eraPrompt.tts,
            selectedEra: eraPrompt.selectedEra, sentEra: eraPrompt.sentEra },
          turns: [],
        };
        for (const text of era.turns) {
          console.log(`    narrator ${text.split(/\s+/).length} words — waiting for Lori + TTS`);
          const evidence = await sendNarratorTurn(page, text, era.era_id);
          eraRow.turns.push({ narratorText: text, loriText: evidence.finalText,
            clientTurnId: evidence.clientTurnId, selectedEra: evidence.selectedEra,
            sentEra: evidence.sentEra, tts: evidence.tts,
            ttsFinishedAt: evidence.ttsFinishedAt });
        }
        report.eras.push(eraRow);
        writeJson(path.join(narratorDir, "partial-report.json"), report);
      }
      report.wrapUp = await wrapUpThroughOperator(page, collector, narratorDir);
      report.transcriptExport = await exportTranscripts(args.api, narrator,
        report.conversationId, narratorDir);
      report.durableValidation = validateDurableTranscript(report, report.transcriptExport);
      if (!report.durableValidation.complete) throw new Error(
        `durable transcript is missing exchanges: ${JSON.stringify(report.durableValidation)}`);
      report.responseCount = report.eras.reduce((n, e) => n + 1 + e.turns.length, 0);
      report.finishedAt = new Date().toISOString();
      report.complete = true;
      writeJson(path.join(narratorDir, "report.json"), report);
      fs.writeFileSync(path.join(narratorDir, "report.html"), narratorHtml(report), "utf8");
      checkpoint.completedSources.push(narrator.source);
      checkpoint.narrators.push({ source: narrator.source, fixtureLabel: narrator.fixture_label,
        personId: narrator.person_id, conversationId: report.conversationId,
        complete: true, eras: report.eras.length, responseCount: report.responseCount,
        operatorStatus: report.wrapUp.wrap?.result?.result?.status || null,
        relativeReport: path.relative(outDir, path.join(narratorDir, "report.html")) });
      writeJson(path.join(outDir, "checkpoint.json"), checkpoint);
      console.log(`  COMPLETE — ${report.eras.length} eras, ${report.responseCount} Lori responses`);
    } catch (error) {
      report.error = String(error && error.stack || error);
      report.finishedAt = new Date().toISOString();
      report.complete = false;
      try { await page.screenshot({ path: path.join(narratorDir, "failure.png"), fullPage: true }); } catch (_) {}
      writeJson(path.join(narratorDir, "report.json"), report);
      fs.writeFileSync(path.join(narratorDir, "report.html"), narratorHtml(report), "utf8");
      checkpoint.narrators.push({ source: narrator.source, fixtureLabel: narrator.fixture_label,
        personId: narrator.person_id, conversationId: report.conversationId || null,
        complete: false, eras: report.eras.length, responseCount: 0,
        operatorStatus: null, error: report.error,
        relativeReport: path.relative(outDir, path.join(narratorDir, "report.html")) });
      writeJson(path.join(outDir, "checkpoint.json"), checkpoint);
      fatal = error;
      console.error(`  FAILED — ${error.message || error}`);
      if (!args.continueOnFailure) break;
    }
  }

  checkpoint.finishedAt = new Date().toISOString();
  checkpoint.diagnostics = diagnostics;
  checkpoint.completedCount = checkpoint.completedSources.length;
  checkpoint.expectedCount = plan.narrator_count;
  writeJson(path.join(outDir, "checkpoint.json"), checkpoint);
  fs.writeFileSync(path.join(outDir, "report.html"), combinedHtml(checkpoint), "utf8");
  await context.close();
  await browser.close();
  console.log(`\n${checkpoint.completedCount === plan.narrator_count ? "PASS" : "INCOMPLETE"} — ${checkpoint.completedCount}/${plan.narrator_count} narrators complete`);
  console.log(`Combined report: ${path.join(outDir, "report.html")}`);
  console.log(`Checkpoint: ${path.join(outDir, "checkpoint.json")}`);
  if (fatal && !args.continueOnFailure) throw fatal;
  if (checkpoint.completedCount !== plan.narrator_count) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error && error.stack || error);
  process.exitCode = 1;
});
