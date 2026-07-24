#!/usr/bin/env node
/**
 * WO-TRAVEL-DOC-UNIFY-01 Phase 1.1 — mount liveness proof (headless).
 *
 *   node scripts/ui/run_travel_doc_mount_liveness.js
 *
 * No backend, no manual server, no arguments. The script starts its own
 * static file server on an ephemeral port, loads ui/travel-doc-lab.html in
 * headless Chromium, and exits 0 on PASS / 1 on FAIL.
 *
 * WHY THIS EXISTS
 * ---------------
 * tests/test_travel_doc_lab.py::MountLivenessTest pins the *shape* of the
 * guards — that the flag exists, that destroy() raises it first, that the
 * one fetch is guarded on all three arms, that the choke-point counts the
 * strategy depends on (one fetch, one repaint entry, one channel, one
 * socket, one timer, one document listener) have not grown a seventh
 * member. Those are static assertions over the source text. They cannot
 * observe an actual stale callback landing on an actual dead host. This
 * script does.
 *
 * HOW IT ISOLATES THE BEHAVIOUR
 * -----------------------------
 * window.fetch is replaced with one that parks every request and never
 * settles until the test says so. That matters more than it looks: with
 * fetch parked, boot() paints NOTHING, because renderAll() lives inside
 * the .then(). So "host is empty" is the identical starting state for
 * every scenario, and the difference between them is only whether the
 * mount was destroyed before the parked request was released.
 *
 *   control_live      — not destroyed, released  -> host MUST repaint
 *   destroyed_then    — destroyed, resolve ok    -> host MUST stay empty
 *   destroyed_notok   — destroyed, resolve 500   -> host MUST stay empty
 *   destroyed_reject  — destroyed, reject        -> host MUST stay empty
 *
 * The control is the load-bearing row. Without it, three "nothing
 * happened" results prove nothing — a harness that never delivers a
 * callback also produces three empty hosts.
 *
 * The two census checks (BroadcastChannel subscriptions, document-level
 * keydown registrations) count bind/unbind rather than observing effects.
 * The keydown handler early-returns unless a lightbox is open, so an
 * "assert no repaint on keypress" test would pass with the listener still
 * bound — vacuously. Counting cannot go vacuous.
 *
 * NEGATIVE CONTROLS (run by hand during Phase 1.1, both confirmed)
 * ----------------------------------------------------------------
 * 1. destroy() changed to set `destroyed = false`: all three destroyed
 *    rows flipped to 3 mutations / 1 child — the exact reviewer-reported
 *    bug, reproduced.
 * 2. destroy()'s removeEventListener line deleted: keydown census went
 *    2 -> 2 -> 2 instead of 2 -> 1 -> 0.
 * If you change the guards, re-run those two by hand. A green suite that
 * cannot go red is decoration.
 */
"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..", "..");
const TYPES = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".svg": "image/svg+xml",
};

function serveRepo() {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      // Answer the favicon so its 404 does not masquerade as a page error.
      if (/^\/favicon\.ico/.test(req.url)) { res.writeHead(204); res.end(); return; }
      const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "");
      const file = path.join(REPO, rel);
      // Do not let a crafted URL escape the repo root.
      if (!file.startsWith(REPO) || !fs.existsSync(file) ||
          !fs.statSync(file).isFile()) {
        res.writeHead(404); res.end("not found"); return;
      }
      res.writeHead(200, { "Content-Type": TYPES[path.extname(file)] || "text/plain" });
      res.end(fs.readFileSync(file));
    });
    srv.listen(0, "127.0.0.1", () => resolve(srv));
  });
}

// Everything below runs inside the page, before any app script.
function installHarness() {
  window.__unhandled = [];
  window.addEventListener("unhandledrejection", function (e) {
    window.__unhandled.push(String((e.reason && e.reason.message) || e.reason));
  });

  // Park every request. Nothing settles until __release is called.
  window.__pending = [];
  window.fetch = function (url, init) {
    return new Promise(function (resolve, reject) {
      window.__pending.push({ url: String(url), init: init,
                              resolve: resolve, reject: reject });
    });
  };

  // Inert socket — Lori must not dial a real backend from a test.
  window.WebSocket = function () {
    this.readyState = 0;
    this.close = function () {};
    this.send = function () {};
  };

  // BroadcastChannel subscription census.
  window.__bcOpen = 0;
  var RealBC = window.BroadcastChannel;
  window.BroadcastChannel = function (name) {
    var c = new RealBC(name);
    if (name === "hornelore-trip-updates") {
      window.__bcOpen++;
      var realClose = c.close.bind(c);
      c.close = function () { window.__bcOpen--; return realClose(); };
    }
    return c;
  };

  // document-level keydown census.
  window.__docKeydown = 0;
  var addEL = document.addEventListener.bind(document);
  var remEL = document.removeEventListener.bind(document);
  document.addEventListener = function (t, f, o) {
    if (t === "keydown") window.__docKeydown++;
    return addEL(t, f, o);
  };
  document.removeEventListener = function (t, f, o) {
    if (t === "keydown") window.__docKeydown--;
    return remEL(t, f, o);
  };

  window.__okBody = {
    people: [{ id: "ptest", display_name: "Test Person" }],
    trips: [{ id: "t1", title: "Trip One" }],
  };
  window.__release = function (from, mode) {
    var mine = window.__pending.splice(from);
    mine.forEach(function (p) {
      if (mode === "reject") { p.reject(new Error("network down")); return; }
      if (mode === "notok") {
        p.resolve({ ok: false, status: 500,
                    text: function () { return Promise.resolve('{"detail":"boom"}'); },
                    json: function () { return Promise.resolve({ detail: "boom" }); } });
        return;
      }
      p.resolve({ ok: true, status: 200,
                  text: function () { return Promise.resolve(JSON.stringify(window.__okBody)); },
                  json: function () { return Promise.resolve(window.__okBody); } });
    });
    return mine.length;
  };
}

(async () => {
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (e) {
    console.error("playwright is not installed. Run: npm install");
    process.exit(2);
  }

  const srv = await serveRepo();
  const url = "http://127.0.0.1:" + srv.address().port + "/ui/travel-doc-lab.html";

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_PATH) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;
  }
  const browser = await chromium.launch(launchOpts);
  const page = await browser.newPage();

  const errs = [];
  const badResponses = [];
  page.on("pageerror", (e) => errs.push("PAGEERROR: " + e.message));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    if (/favicon/i.test(m.text())) return;   // the static server has none
    errs.push("CONSOLE: " + m.text());
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !/favicon/i.test(r.url())) {
      badResponses.push(r.status() + " " + r.url());
    }
  });

  await page.addInitScript(installHarness);
  await page.goto(url);
  await page.waitForTimeout(400);

  const scenario = (name, mode, destroyBefore) => page.evaluate(async (a) => {
    const name = a[0], mode = a[1], destroyBefore = a[2];
    const host = document.createElement("div");
    host.id = "host_" + name;
    document.body.appendChild(host);

    const mark = window.__pending.length;
    const h = window.lvTravelDocMount(host, { person_id: "ptest" });
    await new Promise((r) => setTimeout(r, 250));

    const parked = window.__pending.length - mark;
    const emptyAtStart = host.childElementCount === 0 && host.innerHTML === "";

    if (destroyBefore) h.destroy();
    const clearedByDestroy = host.childElementCount === 0 && host.innerHTML === "";

    // Everything past this line is what the guards must suppress.
    let mutations = 0;
    const obs = new MutationObserver((ms) => { mutations += ms.length; });
    obs.observe(host, { childList: true, subtree: true,
                        attributes: true, characterData: true });

    let released = window.__release(mark, mode);
    // Drain the follow-on chain too (people -> trips -> bundle), so the
    // live control reaches a painted workspace rather than one render.
    for (let i = 0; i < 4; i++) {
      await new Promise((r) => setTimeout(r, 150));
      released += window.__release(mark, mode);
    }
    await new Promise((r) => setTimeout(r, 250));
    obs.disconnect();

    const out = { name, mode, destroyBefore, parked, released, emptyAtStart,
                  clearedByDestroy, mutations,
                  children: host.childElementCount };
    if (!destroyBefore) h.destroy();   // tidy up after reading the verdict
    return out;
  }, [name, mode, destroyBefore]);

  const rows = [
    await scenario("control_live", "ok", false),
    await scenario("destroyed_then", "ok", true),
    await scenario("destroyed_notok", "notok", true),
    await scenario("destroyed_reject", "reject", true),
  ];

  const bc = await page.evaluate(async () => {
    const base = window.__bcOpen;
    const a = document.createElement("div"); document.body.appendChild(a);
    const b = document.createElement("div"); document.body.appendChild(b);
    const ha = window.lvTravelDocMount(a, { person_id: "ptest" });
    const hb = window.lvTravelDocMount(b, { person_id: "ptest" });
    const twoUp = window.__bcOpen - base;
    hb.destroy();
    const afterOne = window.__bcOpen - base;
    ha.destroy();
    const afterBoth = window.__bcOpen - base;
    let threw = false;
    try { hb.destroy(); ha.destroy(); } catch (e) { threw = true; }
    return { twoUp, afterOne, afterBoth, idempotentThrew: threw,
             bothCleared: a.innerHTML === "" && b.innerHTML === "" };
  });

  const keys = await page.evaluate(async () => {
    const base = window.__docKeydown;
    const a = document.createElement("div"); document.body.appendChild(a);
    const b = document.createElement("div"); document.body.appendChild(b);
    const mark = window.__pending.length;
    const ha = window.lvTravelDocMount(a, { person_id: "ptest" });
    const hb = window.lvTravelDocMount(b, { person_id: "ptest" });
    window.__release(mark, "ok");
    await new Promise((r) => setTimeout(r, 300));
    const twoUp = window.__docKeydown - base;
    const paintedWhileLive = a.childElementCount > 0 && b.childElementCount > 0;
    hb.destroy();
    const afterOne = window.__docKeydown - base;
    ha.destroy();
    const afterBoth = window.__docKeydown - base;
    return { twoUp, afterOne, afterBoth, paintedWhileLive };
  });

  const unhandled = await page.evaluate(() => window.__unhandled);
  await browser.close();
  srv.close();

  const pad = (v, n) => String(v).padEnd(n);
  console.log("scenario           mode    destroyed  parked  emptyStart  cleared  mutations  children");
  rows.forEach((r) => console.log(
    pad(r.name, 19) + pad(r.mode, 8) + pad(r.destroyBefore, 11) +
    pad(r.parked, 8) + pad(r.emptyAtStart, 12) + pad(r.clearedByDestroy, 9) +
    pad(r.mutations, 11) + r.children));
  console.log("\nbroadcastchannel :", JSON.stringify(bc));
  console.log("doc keydown bind :", JSON.stringify(keys));
  console.log("unhandled reject :", unhandled.length ? unhandled.join(" | ") : "none");
  console.log("page errors      :", errs.length ? errs.join("\n  ") : "none");
  console.log("non-2xx requests :", badResponses.length ? badResponses.join(", ") : "none");

  const [control, thenArm, notOk, reject] = rows;
  const checks = [
    ["control repaints a live host", control.mutations > 0 && control.children > 0],
    ["every scenario starts empty", rows.every((r) => r.emptyAtStart)],
    ["a request was actually parked", rows.every((r) => r.parked === 1)],
    ["destroy clears the host", rows.slice(1).every((r) => r.clearedByDestroy)],
    ["then-arm cannot repaint", thenArm.mutations === 0 && thenArm.children === 0],
    ["error-body arm cannot repaint", notOk.mutations === 0 && notOk.children === 0],
    ["rejection arm cannot repaint", reject.mutations === 0 && reject.children === 0],
    ["two mounts = two channels", bc.twoUp === 2],
    ["each destroy closes one channel", bc.afterOne === 1 && bc.afterBoth === 0],
    ["destroy is idempotent", !bc.idempotentThrew && bc.bothCleared],
    ["two mounts = two keydown binds", keys.paintedWhileLive && keys.twoUp === 2],
    ["each destroy unbinds one", keys.afterOne === 1 && keys.afterBoth === 0],
    ["no unhandled rejections", unhandled.length === 0],
    ["no page errors", errs.length === 0 && badResponses.length === 0],
  ];
  console.log("");
  checks.forEach(([label, ok]) => console.log((ok ? "  ok   " : "  FAIL ") + label));
  const pass = checks.every((c) => c[1]);
  console.log("\nRESULT           :", pass ? "PASS" : "FAIL");
  process.exit(pass ? 0 : 1);
})();
