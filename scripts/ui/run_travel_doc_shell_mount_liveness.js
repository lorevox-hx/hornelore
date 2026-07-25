#!/usr/bin/env node
/**
 * WO-TRAVEL-DOC-UNIFY-01 Phase 2 — shell mount liveness proof (headless).
 *
 *   node scripts/ui/run_travel_doc_shell_mount_liveness.js
 *
 * No backend, no manual server, no arguments. The script starts its own
 * static file server on an ephemeral port, loads the REAL ui/hornelore1.0.html
 * in headless Chromium, drives lvShellShowTab()/lvTravelDocSetSurface() the
 * way an operator would, and exits 0 on PASS / 1 on FAIL.
 *
 * WHY A SECOND SCRIPT
 * -------------------
 * run_travel_doc_mount_liveness.js proves the MODULE: a destroyed mount
 * cannot repaint, and destroy() gives back its channel and its listener.
 * It mounts the module directly into a bare <div>, which is the right
 * isolation for that question and the wrong one for this one.
 *
 * Phase 2's risk is not inside the module. It is the shell: two Travel Doc
 * surfaces (the unified workspace and the legacy Documenter) now live in
 * one tab, and every path that can reach a mount — first open, narrator
 * switch, surface toggle, tab exit and re-entry — is a place where the
 * shell can leave one live while starting another. Each live surface owns
 * a BroadcastChannel, a document-level keydown listener and a Lori socket,
 * so "two surfaces" is not a cosmetic bug: it is doubled cross-tab refresh
 * traffic, two handlers fighting over Escape, and an extra /api/chat/ws
 * connection bound to a narrator nobody is looking at.
 *
 * tests/test_travel_doc_shell_mount.py pins the SHAPE of the shell's
 * mount/destroy ordering by reading app.js. It cannot observe a census.
 * This script does.
 *
 * HOW IT ISOLATES THE BEHAVIOUR
 * -----------------------------
 * window.fetch is replaced with one that parks every request. That keeps
 * the whole shell — not just Travel Doc — off any backend, and it means
 * the workspace paints only when the test releases its requests, so
 * "empty host" is an unambiguous starting state. window.WebSocket is
 * inert but counted, so the Lori socket census is real without dialling
 * anything. BroadcastChannel and document.addEventListener("keydown") are
 * wrapped to count bind/unbind rather than to observe effects: the lab's
 * keydown handler early-returns unless a lightbox is open, so an "assert
 * no repaint on keypress" check would pass with the listener still bound.
 * Counting cannot go vacuous.
 *
 * WHAT THE ROWS MEAN
 * ------------------
 * The census columns are bc / key / ws: BroadcastChannel subscriptions,
 * document-level keydown listeners, Lori sockets. Neither surface dials
 * Lori at mount — both connect only when the operator opens the Lori pane —
 * so ws is legitimately 0 on the mount rows and is exercised by the lori_*
 * rows instead.
 *
 *   open_unified      — tab opened with a narrator -> unified host paints,
 *                       legacy host empty and hidden, census 1/1/0
 *   leave_tab         — navigate to Operator       -> census back to 0/0/0
 *   reenter_tab       — back to Travel Doc         -> census 1/1/0, NOT 2
 *   switch_to_legacy  — toggle                     -> legacy live, unified
 *                       destroyed; census never exceeds one of each
 *   switch_to_unified — toggle back                -> mirror image
 *   narrator_switch   — person_id changes          -> remount, census 1/1/0
 *   lori_open         — click the workspace's Lori tab -> census 1/1/1.
 *                       This row is the non-vacuity guard for ws.
 *   lori_then_leave   — navigate away with Lori live -> 0/0/0, i.e.
 *                       destroy() gives the socket back
 *   lori_then_reenter — fresh mount, still one of each, no resurrected
 *                       socket
 *   destroyed_repaint — parked request released after the operator has
 *                       navigated away -> host MUST stay empty
 *
 * NEGATIVE CONTROLS — actually run, 2026-07-25, results as recorded
 * -----------------------------------------------------------------
 * 1. `if (tabName !== "traveldoc") ... lvTravelDocTeardownAll()` deleted:
 *    leave_tab kept the unified host painted at 1/1/0 and lori_then_leave
 *    held the socket open at 1/1/1. 5 checks red. RESULT FAIL. This is the
 *    load-bearing guard for tab exit.
 * 2. lvTravelDocSetSurface()'s own teardown call deleted: still PASS.
 * 3. The cross-surface destroy at the top of the traveldoc block deleted:
 *    still PASS.
 * 4. BOTH of the above deleted together: switch_to_legacy reported both
 *    hosts painted with census 2/2, switch_to_unified likewise. 5 checks
 *    red including "two surfaces are never painted at once". RESULT FAIL.
 *
 *    Read 2 + 3 + 4 together, because 2 and 3 on their own are the more
 *    interesting result: the two toggle guards are MUTUALLY REDUNDANT, and
 *    either one alone prevents a double mount. Neither is dead code — each
 *    is the other's backstop, and the tab block's copy also covers entry
 *    paths the setter never runs through — but do not read a green run as
 *    proof that both are load-bearing. It is not.
 *
 * 5. The ws attribution reverted to the original URL test (/travel_doc/):
 *    lori_open dropped to ws 0 and "opening the Lori pane actually opens
 *    one socket" went red. That URL never matched anything — both modules
 *    dial apiBase + "/api/chat/ws" — so before the stack-based attribution
 *    every ws assertion in this file was decoration. The guard now fails
 *    loudly if attribution breaks again.
 *
 * If you change the surface logic, re-run these by hand. A green check
 * that cannot go red is decoration.
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

  // Park every request the WHOLE SHELL makes. Nothing settles until
  // __release is called.
  window.__pending = [];
  window.fetch = function (url, init) {
    return new Promise(function (resolve, reject) {
      window.__pending.push({ url: String(url), init: init,
                              resolve: resolve, reject: reject });
    });
  };

  // Inert but counted socket.
  //
  // Attribution is BY CALL STACK, not by URL. Both Travel Doc surfaces open
  // the same endpoint the shell's own chat uses — st.apiBase + "/api/chat/ws"
  // — so there is nothing in the URL to tell a Travel Doc Lori socket from
  // the shell's. The first cut of this script tested the URL for
  // /travel_doc/, which matches neither module: __wsTravelDoc was pinned at
  // 0 and "no duplicate Travel Doc Lori socket" was a green check that could
  // not go red. Reading the stack costs one throw per socket and names the
  // opening file exactly. If either module is renamed, update this regex —
  // the vacuity guard below will fail loudly rather than silently passing.
  window.__wsOpen = 0;
  window.__wsTravelDoc = 0;
  window.WebSocket = function (url) {
    var stack = "";
    try { throw new Error(); } catch (e) { stack = String((e && e.stack) || ""); }
    var isTd = /travel-doc-lab\.js|travel-documenter\.js/.test(stack);
    window.__wsOpen++;
    if (isTd) window.__wsTravelDoc++;
    this.url = String(url || "");
    this.readyState = 0;
    this.close = function () {
      if (this.readyState === 3) return;
      this.readyState = 3;
      window.__wsOpen--;
      if (isTd) window.__wsTravelDoc--;
    };
    this.send = function () {};
    this.addEventListener = function () {};
    this.removeEventListener = function () {};
  };

  // BroadcastChannel census, scoped to the named channel BOTH Travel Doc
  // surfaces use. A duplicate here is a duplicate cross-tab refresh.
  window.__bcOpen = 0;
  var RealBC = window.BroadcastChannel;
  window.BroadcastChannel = function (name) {
    var c = new RealBC(name);
    if (name === "hornelore-trip-updates") {
      window.__bcOpen++;
      var realClose = c.close.bind(c);
      var closed = false;
      c.close = function () {
        if (!closed) { closed = true; window.__bcOpen--; }
        return realClose();
      };
    }
    return c;
  };

  // document-level keydown census.
  //
  // Attributed BY CALL STACK, for the same reason as the socket census and
  // with a sharper edge. A plain count of every document-level keydown
  // bind/unbind is not a Travel Doc census, it is a whole-page one, and the
  // page moves underneath it: app.js's WO-10K audio unlock binds keydown at
  // load and then REMOVES itself on the operator's first click. The
  // lori_open step below is the first real click in this run, so an
  // unattributed census reported key 0 while the mount was still live and
  // key -1 after teardown — a listener going missing that Travel Doc never
  // owned. Counting only binds whose stack names a Travel Doc module keeps
  // the number meaning what the column header says it means.
  window.__docKeydown = 0;
  var addEL = document.addEventListener.bind(document);
  var remEL = document.removeEventListener.bind(document);
  var fromTd = function () {
    var s = "";
    try { throw new Error(); } catch (e) { s = String((e && e.stack) || ""); }
    return /travel-doc-lab\.js|travel-documenter\.js/.test(s);
  };
  document.addEventListener = function (t, f, o) {
    if (t === "keydown" && fromTd()) window.__docKeydown++;
    return addEL(t, f, o);
  };
  document.removeEventListener = function (t, f, o) {
    if (t === "keydown" && fromTd()) window.__docKeydown--;
    return remEL(t, f, o);
  };

  window.__okBody = {
    people: [{ id: "ptest", display_name: "Test Person" }],
    trips: [{ id: "t1", title: "Trip One" }],
  };
  window.__release = function (from, mode) {
    var mine = window.__pending.splice(from == null ? 0 : from);
    mine.forEach(function (p) {
      if (mode === "reject") { p.reject(new Error("network down")); return; }
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
  const url = "http://127.0.0.1:" + srv.address().port + "/ui/hornelore1.0.html";

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_PATH) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;
  }
  const browser = await chromium.launch(launchOpts);
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });

  const errs = [];
  page.on("pageerror", (e) => errs.push("PAGEERROR: " + e.message));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    if (/favicon/i.test(m.text())) return;   // the static server has none
    errs.push("CONSOLE: " + m.text());
  });

  await page.addInitScript(installHarness);
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);

  // The shell boots with no narrator (every /api call is parked). Give it
  // the one the harness serves, exactly as lv80SwitchPerson would.
  await page.evaluate(() => {
    window.state = window.state || {};
    window.state.person_id = "ptest";
    // Start from a known surface regardless of any stored preference.
    try { localStorage.removeItem("lvTravelDocSurface"); } catch (e) {}
    // NB: the cache is _lvTravelDocActiveSurface. Clearing
    // window._lvTravelDocSurface here would delete the resolver FUNCTION —
    // which is precisely the collision this script caught on 2026-07-25.
    window._lvTravelDocActiveSurface = null;
    // Baseline the censuses AFTER the shell has finished its own boot, so
    // the numbers below are Travel Doc's and nobody else's.
    window.__base = { bc: window.__bcOpen, key: window.__docKeydown,
                      ws: window.__wsTravelDoc };
  });

  /** Drive one operator step, then report the state of both surfaces. */
  const step = (label, script) => page.evaluate(async (a) => {
    const label = a[0], script = a[1];
    const mark = window.__pending.length;
    // eslint-disable-next-line no-new-func
    await (new Function("return (async () => {" + script + "})()"))();
    // Let the workspace's request chain (people -> trips -> bundle) run.
    for (let i = 0; i < 4; i++) {
      await new Promise((r) => setTimeout(r, 150));
      window.__release(mark, "ok");
    }
    await new Promise((r) => setTimeout(r, 250));

    const uni = document.getElementById("lvTravelDocUnifiedHost");
    const leg = document.getElementById("lvTravelDocHost");
    const vis = (el) => !!el && !el.classList.contains("lv-td-host-off");
    const painted = (el) => !!el && el.childElementCount > 0;
    const pressed = {};
    document.querySelectorAll("[data-td-surface]").forEach((b) => {
      pressed[b.getAttribute("data-td-surface")] =
        b.getAttribute("aria-pressed");
    });
    return {
      label,
      uniPainted: painted(uni), legPainted: painted(leg),
      uniVisible: vis(uni), legVisible: vis(leg),
      uniScoped: !!uni && uni.classList.contains("tdl-root") &&
                 uni.classList.contains("tdl-root-embedded"),
      legScoped: !!leg && leg.classList.contains("td-root"),
      bc: window.__bcOpen - window.__base.bc,
      key: window.__docKeydown - window.__base.key,
      ws: window.__wsTravelDoc - window.__base.ws,
      pressed: pressed.unified + "/" + pressed.legacy,
    };
  }, [label, script]);

  const rows = [];
  rows.push(await step("open_unified", 'lvShellShowTab("traveldoc");'));
  rows.push(await step("leave_tab", 'lvShellShowTab("operator");'));
  rows.push(await step("reenter_tab", 'lvShellShowTab("traveldoc");'));
  rows.push(await step("switch_to_legacy", 'lvTravelDocSetSurface("legacy");'));
  rows.push(await step("switch_to_unified", 'lvTravelDocSetSurface("unified");'));
  rows.push(await step("narrator_switch",
    'window.state.person_id = "pother"; window.lvTravelDocTeardownAll(); ' +
    'lvShellShowTab("traveldoc");'));

  // The Lori socket is NOT opened at mount by either surface — both modules
  // dial only when the operator opens the Lori pane (travel-doc-lab.js
  // renderLoriTab -> loriPane.connect(); travel-documenter.js on modal
  // open). So every row above legitimately reports ws 0, and the acceptance
  // line "no duplicate Travel Doc Lori socket" is untested unless the script
  // opens the pane itself. Click the workspace's own "Lori" tab button, the
  // way an operator would, rather than reaching into module internals the
  // shell cannot see.
  rows.push(await step("lori_open",
    'var h = document.getElementById("lvTravelDocUnifiedHost");' +
    'var b = Array.prototype.find.call(h.querySelectorAll("button"),' +
    '  function (x) { return x.textContent.trim() === "Lori"; });' +
    'if (!b) throw new Error("no Lori tab button in the mounted workspace");' +
    'b.click();'));
  rows.push(await step("lori_then_leave", 'lvShellShowTab("operator");'));
  rows.push(await step("lori_then_reenter", 'lvShellShowTab("traveldoc");'));

  // A destroyed shell mount must not repaint when its parked request
  // finally lands. This is the module's Phase 1.1 guarantee re-checked
  // through the shell's own mount path rather than a bare div.
  const destroyedRepaint = await page.evaluate(async () => {
    window.state.person_id = "pthird";
    window.lvTravelDocTeardownAll();
    const mark = window.__pending.length;
    lvShellShowTab("traveldoc");
    await new Promise((r) => setTimeout(r, 250));
    const parked = window.__pending.length - mark;
    const host = document.getElementById("lvTravelDocUnifiedHost");
    const emptyAtStart = host.childElementCount === 0;
    lvShellShowTab("operator");          // the operator navigates away
    // Observe AFTER the teardown rather than through it. destroy()
    // legitimately mutates this host — it takes .tdl-root/.tdl-root-embedded
    // back off and clears the subtree — so an observer installed before the
    // navigation counts the cleanup itself and reports two "repaints" of a
    // mount that behaved perfectly. The window that actually matters is
    // everything AFTER the mount is dead, which is where the parked request
    // lands. tornDown below keeps the cleanup itself under assertion, so
    // narrowing the window does not drop coverage.
    const tornDown = host.childElementCount === 0 &&
                     !host.classList.contains("tdl-root") &&
                     !host.classList.contains("tdl-root-embedded");
    let mutations = 0;
    const obs = new MutationObserver((ms) => { mutations += ms.length; });
    obs.observe(host, { childList: true, subtree: true,
                        attributes: true, characterData: true });
    for (let i = 0; i < 4; i++) {
      await new Promise((r) => setTimeout(r, 150));
      window.__release(mark, "ok");
    }
    await new Promise((r) => setTimeout(r, 250));
    obs.disconnect();
    return { parked, emptyAtStart, tornDown, mutations,
             children: host.childElementCount,
             bc: window.__bcOpen - window.__base.bc,
             key: window.__docKeydown - window.__base.key,
             ws: window.__wsTravelDoc - window.__base.ws };
  });

  // The operator path must not advertise itself as an experiment.
  const branding = await page.evaluate(async () => {
    window.state.person_id = "ptest";
    window.lvTravelDocTeardownAll();
    const mark = window.__pending.length;
    lvShellShowTab("traveldoc");
    for (let i = 0; i < 4; i++) {
      await new Promise((r) => setTimeout(r, 150));
      window.__release(mark, "ok");
    }
    await new Promise((r) => setTimeout(r, 250));
    const panel = document.getElementById("lvTravelDocTab");
    const text = (panel && panel.innerText) || "";
    return {
      hasLabBadge: /UI Lab/i.test(text),
      hasExperimental: /experimental/i.test(text),
      hasLauncher: /Open Travel Doc UI Lab/i.test(text),
      painted: document.getElementById("lvTravelDocUnifiedHost")
                 .childElementCount > 0,
    };
  });

  const unhandled = await page.evaluate(() => window.__unhandled);
  await browser.close();
  srv.close();

  const pad = (v, n) => String(v).padEnd(n);
  console.log("step               uniPaint  legPaint  uniVis  legVis  scoped     bc  key  ws  pressed");
  rows.forEach((r) => console.log(
    pad(r.label, 19) + pad(r.uniPainted, 10) + pad(r.legPainted, 10) +
    pad(r.uniVisible, 8) + pad(r.legVisible, 8) +
    pad((r.uniScoped ? "tdl" : "-") + "/" + (r.legScoped ? "td" : "-"), 11) +
    pad(r.bc, 4) + pad(r.key, 5) + pad(r.ws, 4) + r.pressed));
  console.log("\ndestroyed repaint:", JSON.stringify(destroyedRepaint));
  console.log("operator branding:", JSON.stringify(branding));
  console.log("unhandled reject :", unhandled.length ? unhandled.join(" | ") : "none");
  console.log("page errors      :", errs.length ? errs.join("\n  ") : "none");

  const [open, leave, reenter, toLegacy, toUnified, switchPerson,
         loriOpen, loriLeave, loriReenter] = rows;
  // ws <= 1 for the mount rows because neither surface dials at mount; the
  // lori_* rows below are where the socket is required to be exactly 1 and
  // then exactly 0.
  const oneOfEach = (r) => r.bc === 1 && r.key === 1 && r.ws <= 1;
  const noneOfEach = (r) => r.bc === 0 && r.key === 0 && r.ws === 0;
  const neverBoth = rows.every((r) => !(r.uniPainted && r.legPainted));

  const checks = [
    ["tab open renders the unified workspace",
     open.uniPainted && open.uniVisible && open.uniScoped],
    ["legacy stays empty and hidden by default",
     !open.legPainted && !open.legVisible],
    ["default toggle reads unified", open.pressed === "true/false"],
    ["one channel, one keydown, one socket while open", oneOfEach(open)],
    ["leaving the tab destroys everything",
     !leave.uniPainted && !leave.legPainted && noneOfEach(leave)],
    ["re-entering mounts exactly one again",
     reenter.uniPainted && oneOfEach(reenter)],
    ["toggling to legacy swaps the live surface",
     toLegacy.legPainted && toLegacy.legVisible && toLegacy.legScoped &&
     !toLegacy.uniPainted && !toLegacy.uniVisible &&
     toLegacy.pressed === "false/true"],
    ["toggling to legacy leaves one of each", oneOfEach(toLegacy)],
    ["toggling back restores the unified workspace",
     toUnified.uniPainted && toUnified.uniVisible && !toUnified.legPainted &&
     toUnified.pressed === "true/false"],
    ["toggling back leaves one of each", oneOfEach(toUnified)],
    ["narrator switch remounts exactly one",
     switchPerson.uniPainted && oneOfEach(switchPerson)],
    ["two surfaces are never painted at once", neverBoth],
    // Non-vacuity guard for the socket census. If this goes red, either the
    // Lori pane stopped dialling or the stack-based attribution in the
    // WebSocket shim stopped matching — and every other ws assertion in
    // this file became decoration. Fix the census, do not relax this.
    ["opening the Lori pane actually opens one socket", loriOpen.ws === 1],
    ["leaving the tab closes the Lori socket", loriLeave.ws === 0],
    ["re-entering does not resurrect a second socket", loriReenter.ws <= 1 &&
     loriReenter.bc === 1 && loriReenter.key === 1],
    ["a request was actually parked", destroyedRepaint.parked > 0],
    ["tab exit cleans the host down to bare",
     destroyedRepaint.emptyAtStart && destroyedRepaint.tornDown],
    ["a mount destroyed by tab exit cannot repaint",
     destroyedRepaint.mutations === 0 && destroyedRepaint.children === 0],
    ["tab exit leaves nothing bound", noneOfEach(destroyedRepaint)],
    ["operator path shows a painted workspace", branding.painted],
    ["no UI Lab branding on the operator path",
     !branding.hasLabBadge && !branding.hasExperimental &&
     !branding.hasLauncher],
    ["no unhandled rejections", unhandled.length === 0],
    ["no page errors", errs.length === 0],
  ];
  console.log("");
  checks.forEach(([label, ok]) => console.log((ok ? "  ok   " : "  FAIL ") + label));
  const pass = checks.every((c) => c[1]);
  console.log("\nRESULT           :", pass ? "PASS" : "FAIL");
  process.exit(pass ? 0 : 1);
})();
