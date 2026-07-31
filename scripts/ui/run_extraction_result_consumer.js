#!/usr/bin/env node
/**
 * WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2 —
 * executing acceptance harness for the server-owned extraction result.
 *
 *     node scripts/ui/run_extraction_result_consumer.js
 *     node scripts/ui/run_extraction_result_consumer.js --node-only
 *
 * Exits 0 on PASS, 1 on FAIL, 2 when the toolchain is missing.
 *
 * WHY THIS EXISTS AND A PYTHON SOURCE SCAN DOES NOT REPLACE IT
 * ------------------------------------------------------------
 * A source scan can prove applyCompletedTurnExtractionResult contains no
 * one-second cooldown. It cannot prove that two results arriving 40ms
 * apart BOTH apply. Those are different claims, and five of the required
 * cases here are the second kind. scripts/ui/run_travel_doc_mount_liveness.js
 * exists for exactly this reason and this file follows its shape.
 *
 * IT EXECUTES THE REAL ui/js/interview.js. Nothing is reimplemented. The
 * stubs replace only the boundaries the work order names: the active
 * narrator, Projection Sync, forcePersist, Shadow Review, the
 * acknowledgment transport and the pending catch-up transport.
 *
 * TWO RUNNERS, ONE BODY
 * ---------------------
 * installStubs() and runCases() are plain functions with no closure over
 * this module, so the identical text runs in both places:
 *
 *   Chromium (default)  — Playwright 1.58.2, the environment the browser
 *                         code actually ships into.
 *   plain Node (--node-only) — the same functions in a vm context, for a
 *                         machine with no browser binaries.
 *
 * They are not two copies of the assertions. A second copy would drift,
 * and a drifted test is worse than one runner.
 *
 * PLAYWRIGHT NOTES (WO-HARNESS-DEPS-01)
 * -------------------------------------
 * node_modules is gitignored and does not arrive with `git pull`.
 * Playwright is pinned EXACTLY to 1.58.2 because the version selects the
 * Chromium revision (1208); a caret would download a second ~500MB
 * browser set and strand the one already installed. Do not run
 * `npx playwright install` to "fix" a version mismatch — report it.
 *
 * This harness uses neither .venv nor .venv-gpu. Those are the Python
 * environments; this is the Node one.
 */

const path = require("path");
const fs = require("fs");

const REPO = path.resolve(__dirname, "..", "..");
const INTERVIEW_JS = path.join(REPO, "ui", "js", "interview.js");

/* ─────────────────────────────────────────────────────────────────────
   THE BOUNDARY STUBS

   Installed BEFORE interview.js loads. Everything here is a boundary the
   work order lists; nothing here is production logic.
   ───────────────────────────────────────────────────────────────────── */
function installStubs() {
  const H = {
    projected: [],        // every projectValue call
    persisted: 0,         // every forcePersist call
    shadow: [],           // every showInlineClaims call
    acked: [],            // every turn_key acknowledged
    posts: [],            // every fetch URL (proves no /api/extract-fields)
    clarified: [],        // every fragile-clarification dispatch
    failPersist: false,   // make forcePersist throw
    failShadow: false,    // make Shadow Review throw
    pending: [],          // what the catch-up endpoint returns
  };
  window.__H = H;

  window.state = {
    person_id: "chris",
    chat: { conv_id: "conv-1" },
    interview: { session_id: null },
    bioBuilder: { questionnaire: {} },
    interviewProjection: { fields: {}, _lastTargetPath: null, _lastTargetSection: null },
  };

  window.LorevoxProjectionMap = {
    REPEATABLE_TEMPLATES: { parents: true, siblings: true },
    parsePath: function (p) {
      const m = String(p || "").match(/^([a-zA-Z]+)(?:\[(\d+)\])?\.(.+)$/);
      if (!m) return null;
      return { section: m[1], index: m[2] === undefined ? null : Number(m[2]), field: m[3] };
    },
    buildRepeatablePath: function (s, i, f) { return s + "[" + i + "]." + f; },
  };

  window.LorevoxProjectionSync = {
    projectValue: function (fieldPath, value, meta) {
      H.projected.push({ fieldPath: fieldPath, value: value, meta: meta || {} });
      window.state.interviewProjection.fields[fieldPath] =
        { value: value, turnId: (meta || {}).turnId };
      return true;
    },
    forcePersist: function () {
      if (H.failPersist) throw new Error("persist failed");
      H.persisted += 1;
    },
    resetForNarrator: function () {},
  };

  window.HorneloreShadowReview = {
    showInlineClaims: function (items, answerText) {
      if (H.failShadow) throw new Error("shadow review display failed");
      H.shadow.push({ n: items.length, answerText: answerText || "" });
    },
  };

  window.HorneloreClarifyFragile = function (list) { H.clarified.push(list.length); };

  window.fetch = function (url, opts) {
    H.posts.push(String(url));
    if (String(url).indexOf("/api/extraction-results/ack") !== -1) {
      try {
        const body = JSON.parse((opts && opts.body) || "{}");
        (body.turn_keys || []).forEach(function (k) { H.acked.push(k); });
      } catch (e) { /* the assertion is the ack list, not the parse */ }
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({}); } });
    }
    if (String(url).indexOf("/api/extraction-results/pending") !== -1) {
      return Promise.resolve({
        ok: true,
        json: function () { return Promise.resolve({ pending: H.pending }); },
      });
    }
    // Anything else — notably /api/extract-fields — is recorded and
    // refused, so a stray legacy call shows up as a failed case rather
    // than as silence.
    return Promise.resolve({ ok: false, status: 599,
      json: function () { return Promise.resolve({}); } });
  };

  // interview.js reads these at load; absent they are not fatal but the
  // console noise obscures real failures.
  window.getCurrentEra = function () { return null; };
  window.TranscriptGuard = undefined;
}

/* ─────────────────────────────────────────────────────────────────────
   THE CASES

   Returns [[label, ok], ...]. Every case drives the REAL functions.
   ───────────────────────────────────────────────────────────────────── */
async function runCases() {
  const H = window.__H;
  const out = [];
  const ok = (label, cond) => out.push([label, !!cond]);
  const reset = () => {
    H.projected = []; H.persisted = 0; H.shadow = []; H.acked = [];
    H.posts = []; H.clarified = []; H.pending = [];
    H.failPersist = false; H.failShadow = false;
    window.state.person_id = "chris";
    window.state.chat.conv_id = "conv-1";
    window.state.interviewProjection.fields = {};
    // The applied-set is module state inside interview.js and there is
    // deliberately no reset hook in production — a browser that could be
    // told to forget what it applied could be told to apply it twice. So
    // each case uses fresh turn_keys instead.
  };
  const frame = (k, over) => Object.assign({
    type: "field_extraction_result",
    turn_key: k, turn_id: "t-" + k, person_id: "chris", conv_id: "conv-1",
    status: "succeeded", method: "llm",
    items: [{ fieldPath: "personal.placeOfBirth", value: "Mandan-" + k, confidence: 0.9 }],
    clarification_required: [], answer_text: "source text for " + k,
  }, over || {});

  /* ── capability negotiation: all four combinations ───────────────── */
  reset();
  applyExtractionCapabilities({ capabilities: { field_extraction_owner: "backend_result_v1" } });
  const newNew = clientExtractionCapabilities().field_extraction_result === "v1";
  ok("NEG new browser + new server: backend owns, client declares v1",
     newNew && window._BACKEND_OWNS_EXTRACTION !== false);

  applyExtractionCapabilities({ capabilities: {} });
  ok("NEG new browser + old server: no capability, legacy retained",
     window._BACKEND_OWNS_EXTRACTION === false);

  applyExtractionCapabilities({});
  ok("NEG absent capabilities block: legacy retained",
     window._BACKEND_OWNS_EXTRACTION === false);

  ok("NEG client always declares support so an old server is harmless",
     clientExtractionCapabilities().field_extraction_result === "v1");

  // The old-browser + new-server arm is the SERVER's decision and is
  // asserted in the Python suite; a new browser cannot simulate a client
  // that does not know the protocol. Named here so the gap is explicit.
  ok("NEG old browser + new server is a server-side assertion (see python)", true);

  /* ── A. two different results inside one second ──────────────────── */
  reset();
  applyExtractionCapabilities({ capabilities: { field_extraction_owner: "backend_result_v1" } });
  const t0 = Date.now();
  applyExtractionResultFrame(frame("A1"));
  applyExtractionResultFrame(frame("A2"));
  const elapsed = Date.now() - t0;
  await new Promise((r) => setTimeout(r, 30));
  ok("A both results arrived within one second (" + elapsed + "ms)", elapsed < 1000);
  ok("A both projected once each", H.projected.length === 2);
  ok("A both persisted", H.persisted === 2);
  ok("A both reached Shadow Review", H.shadow.length === 2);
  ok("A both acknowledged", H.acked.length === 2
     && H.acked.indexOf("A1") !== -1 && H.acked.indexOf("A2") !== -1);
  ok("A the old one-second cooldown did not suppress the second",
     H.projected.length === 2);

  /* ── B. replay of the same turn_key ──────────────────────────────── */
  reset();
  applyExtractionResultFrame(frame("B1"));
  applyExtractionResultFrame(frame("B1"));
  await new Promise((r) => setTimeout(r, 30));
  ok("B replay projected once, not twice", H.projected.length === 1);
  ok("B replay reached Shadow Review once", H.shadow.length === 1);
  ok("B replay acknowledged once", H.acked.length === 1);

  /* ── C. out-of-order completion keeps its own provenance ─────────── */
  reset();
  applyExtractionResultFrame(frame("C_B", {
    turn_id: "turn-B", answer_text: "We went to the cemetery.",
    conv_id: "conv-1",
    items: [{ fieldPath: "personal.placeOfBirth", value: "cemetery-fact" }] }));
  applyExtractionResultFrame(frame("C_A", {
    turn_id: "turn-A", answer_text: "I visited Bismarck with Melanie.",
    conv_id: "conv-1",
    items: [{ fieldPath: "personal.dateOfBirth", value: "bismarck-fact" }] }));
  await new Promise((r) => setTimeout(r, 30));
  // Defensive indexing throughout. A regression that SUPPRESSES results
  // leaves these arrays short, and an unguarded read would throw a
  // TypeError — which tells a reader that the harness broke, not which
  // property did. Every assertion below must be able to report FAIL.
  const sB = H.shadow[0] || {}, sA = H.shadow[1] || {};
  ok("C both applied", H.projected.length === 2);
  ok("C later-arriving A kept A's own source text",
     sA.answerText === "I visited Bismarck with Melanie.");
  ok("C earlier B kept B's own source text",
     sB.answerText === "We went to the cemetery.");
  ok("C neither borrowed the other's text",
     !!sA.answerText && !!sB.answerText && sA.answerText !== sB.answerText);
  const pA = H.projected.filter((p) => p.value === "bismarck-fact")[0];
  ok("C A's projection carries A's own turnId",
     !!pA && (pA.meta || {}).turnId === "turn-A");

  /* ── D. narrator switch cannot cross-apply ───────────────────────── */
  reset();
  window.state.person_id = "someone-else";
  applyExtractionResultFrame(frame("D1"));
  await new Promise((r) => setTimeout(r, 30));
  ok("D zero projection for another narrator's result", H.projected.length === 0);
  ok("D zero Shadow Review", H.shadow.length === 0);
  ok("D NOT acknowledged, so the row stays pending", H.acked.length === 0);
  // switch back and catch up
  window.state.person_id = "chris";
  H.pending = [frame("D1")];
  await fetchPendingExtractionResults();
  ok("D catch-up applies it once after switching back", H.projected.length === 1);
  ok("D catch-up acknowledges it", H.acked.indexOf("D1") !== -1);

  /* ── E. same person, different conversation ──────────────────────── */
  reset();
  window.state.chat.conv_id = "conv-OTHER";
  applyExtractionResultFrame(frame("E1", { conv_id: "conv-1" }));
  await new Promise((r) => setTimeout(r, 30));
  ok("E RULE B: same narrator, other conversation, still applied",
     H.projected.length === 1);
  ok("E provenance is the SOURCE conversation, not the open one",
     ((H.projected[0] || {}).meta || {}).convId === "conv-1");
  ok("E acknowledged, so it cannot strand", H.acked.indexOf("E1") !== -1);

  /* ── F. non-actionable statuses ──────────────────────────────────── */
  for (const st of ["noop", "failed", "duplicate", "resource_deferred"]) {
    reset();
    applyExtractionResultFrame(frame("F_" + st, { status: st, items: [] }));
    await new Promise((r) => setTimeout(r, 20));
    ok("F " + st + " does not modify projection", H.projected.length === 0);
    ok("F " + st + " does not reach Shadow Review", H.shadow.length === 0);
    ok("F " + st + " is acknowledged so it stops being offered",
       H.acked.length === 1);
  }

  /* ── G. persistence relative to acknowledgment ───────────────────── */
  reset();
  H.failPersist = true;
  let threw = false;
  try { applyExtractionResultFrame(frame("G1")); } catch (e) { threw = true; }
  await new Promise((r) => setTimeout(r, 30));
  ok("G a persistence failure is visible rather than silently acknowledged",
     threw || H.acked.length === 0);

  /* ── H. Shadow Review is presentation-only ───────────────────────── */
  reset();
  H.failShadow = true;
  applyExtractionResultFrame(frame("H1"));
  await new Promise((r) => setTimeout(r, 30));
  ok("H projection still happened despite a display failure",
     H.projected.length === 1);
  ok("H acknowledged, so a display bug cannot cause endless re-projection",
     H.acked.indexOf("H1") !== -1);

  /* ── I. catch-up ordering and narrator isolation ─────────────────── */
  reset();
  H.pending = [frame("I1"), frame("I2"), frame("I3", { person_id: "someone-else" })];
  await fetchPendingExtractionResults();
  ok("I applies this narrator's pending results", H.projected.length === 2);
  ok("I applies them in the order given",
     (H.projected[0] || {}).value === "Mandan-I1"
     && (H.projected[1] || {}).value === "Mandan-I2");
  ok("I another narrator's pending row is not applied",
     H.projected.filter((p) => p.value === "Mandan-I3").length === 0);
  ok("I acknowledges only what it applied",
     H.acked.indexOf("I1") !== -1 && H.acked.indexOf("I2") !== -1
     && H.acked.indexOf("I3") === -1);

  /* ── J. legacy transport isolation ───────────────────────────────── */
  reset();
  applyExtractionCapabilities({ capabilities: { field_extraction_owner: "backend_result_v1" } });
  applyExtractionResultFrame(frame("J1"));
  await new Promise((r) => setTimeout(r, 30));
  const legacyCalls = H.posts.filter((u) => u.indexOf("/api/extract-fields") !== -1);
  ok("J the backend result path makes zero calls to /api/extract-fields",
     legacyCalls.length === 0);
  ok("J the legacy transport is still explicitly callable",
     typeof requestLegacyFieldExtraction === "function");
  ok("J targeted questionnaire projection survives",
     typeof _projectAnswerToField === "function");

  return out;
}

/* ─────────────────────────────────────────────────────────────────────
   RUNNERS
   ───────────────────────────────────────────────────────────────────── */
function report(checks) {
  checks.forEach(([label, good]) =>
    console.log((good ? "  ok   " : "  FAIL ") + label));
  const failed = checks.filter(([, g]) => !g);
  console.log("");
  console.log("checks           : " + checks.length);
  console.log("failed           : " + failed.length);
  console.log("RESULT           : " + (failed.length ? "FAIL" : "PASS"));
  return failed.length === 0;
}

async function runInNode() {
  const vm = require("vm");
  const src = fs.readFileSync(INTERVIEW_JS, "utf8");
  const sandbox = {
    console, setTimeout, clearTimeout, Promise, Date, Set, Map, Object, Array,
    JSON, Math, encodeURIComponent, String, Number, Boolean, Error,
    document: {
      getElementById: () => null, querySelector: () => null,
      addEventListener: () => {},
      createElement: () => ({ style: {}, appendChild() {}, setAttribute() {} }),
    },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext("(" + installStubs.toString() + ")()", sandbox);
  vm.runInContext(src, sandbox, { filename: "interview.js" });
  return await vm.runInContext("(" + runCases.toString() + ")()", sandbox);
}

async function runInChromium() {
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (e) {
    console.error("playwright is not installed. Run: npm install");
    console.error("Do NOT run `npx playwright install` to fix a version "
                  + "mismatch — report it instead (WO-HARNESS-DEPS-01).");
    process.exit(2);
  }
  const pw = require("playwright/package.json");
  if (pw.version !== "1.58.2") {
    console.error("playwright is " + pw.version + ", expected exactly 1.58.2. "
                  + "The version selects the Chromium revision; do not "
                  + "re-pin without a decision.");
    process.exit(2);
  }

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_PATH) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;
  }
  let browser;
  try {
    browser = await chromium.launch(launchOpts);
  } catch (e) {
    // The declared browser revision is absent. Do NOT install it: the
    // pins are a decision (WO-HARNESS-DEPS-01), and an agent sandbox
    // legitimately has no ~/.cache/ms-playwright at all.
    //
    // Falling back rather than failing is honest here ONLY because the
    // case bodies are shared verbatim between the two runners — the
    // plain-Node path executes the same assertions against the same
    // interview.js. What it cannot see is a real DOM or a real
    // WebSocket, so a green Node run is evidence, and the Chromium run
    // on Chris's machine is the verification. The banner says so.
    console.error("");
    console.error("!! Chromium 1208 is not present in this environment.");
    console.error("!! " + String(e.message || e).split("\n")[0]);
    console.error("!! Falling back to the plain-Node runner. This executes");
    console.error("!! the same case bodies but NOT in a browser — rerun");
    console.error("!! without --node-only on a machine that has the");
    console.error("!! browsers to verify.");
    console.error("");
    return { checks: await runInNode(), degraded: true };
  }
  const page = await browser.newPage();

  const errs = [];
  page.on("pageerror", (e) => errs.push("PAGEERROR: " + e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errs.push("CONSOLE: " + m.text());
  });

  await page.addInitScript(installStubs);
  await page.setContent("<!doctype html><meta charset=utf-8><title>x</title>");
  await page.addScriptTag({ content: fs.readFileSync(INTERVIEW_JS, "utf8") });

  const checks = await page.evaluate(runCases);
  await browser.close();

  if (errs.length) {
    console.log("browser errors:");
    errs.forEach((e) => console.log("  " + e));
  }
  return { checks: checks, degraded: false };
}

(async () => {
  const nodeOnly = process.argv.indexOf("--node-only") !== -1;
  console.log("WO-EXTRACTION-OWNERSHIP-AND-VRAM-STABILITY-01 Phase 2");
  console.log("executing consumer harness — "
              + (nodeOnly ? "plain Node" : "Chromium (Playwright 1.58.2)"));
  console.log("");

  let checks, degraded;
  if (nodeOnly) {
    checks = await runInNode();
    degraded = true;
  } else {
    ({ checks, degraded } = await runInChromium());
  }

  const ok = report(checks);
  if (ok && degraded) {
    console.log("");
    console.log("NOTE: ran WITHOUT a browser. Green here is evidence, not");
    console.log("      verification. Rerun in Chromium before acceptance.");
  }
  process.exit(ok ? 0 : 1);
})();

process.on("unhandledRejection", (e) => {
  // A harness that dies on an unhandled rejection reports nothing at
  // all, which reads identically to a harness that has not been run.
  console.error("harness aborted: " + String((e && e.stack) || e));
  process.exit(1);
});
