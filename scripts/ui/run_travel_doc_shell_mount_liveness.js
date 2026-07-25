#!/usr/bin/env node
/**
 * WO-TRAVEL-DOC-UNIFY-01 — shell mount liveness proof (headless).
 *
 *   node scripts/ui/run_travel_doc_shell_mount_liveness.js
 *
 * No backend, no manual server, no arguments. The script starts its own
 * static file server on an ephemeral port, loads the REAL ui/hornelore1.0.html
 * in headless Chromium, drives lvShellShowTab() the way an operator would,
 * and exits 0 on PASS / 1 on FAIL.
 *
 * WHY A SECOND SCRIPT
 * -------------------
 * run_travel_doc_mount_liveness.js proves the MODULE: a destroyed mount
 * cannot repaint, and destroy() gives back its channel and its listener.
 * It mounts the module directly into a bare <div>, which is the right
 * isolation for that question and the wrong one for this one.
 *
 * The risk this script covers is not inside the module. It is the shell:
 * every path that can reach a mount — first open, narrator switch, tab exit
 * and re-entry — is a place where the shell can start a mount while an
 * older one is still live. A live mount owns a BroadcastChannel, a
 * document-level keydown listener and a Lori socket, so a double mount is
 * not a cosmetic bug: it is doubled cross-tab refresh traffic, two handlers
 * fighting over Escape, and an extra /api/chat/ws connection bound to a
 * narrator nobody is looking at.
 *
 * tests/test_travel_doc_shell_mount.py pins the SHAPE of the shell's
 * mount/destroy ordering by reading app.js. It cannot observe a census.
 * This script does.
 *
 * PHASE 4 — ONE SURFACE
 * ---------------------
 * Phase 2 wrote this script against TWO Travel Doc surfaces in one tab: the
 * unified workspace and the older Documenter, with a toggle between them.
 * Half of what follows existed to prove the shell never left both live at
 * once — a legacy-host census, a visibility column, a toggle-state column,
 * and two steps that drove lvTravelDocSetSurface().
 *
 * Phase 4 retired the fallback, so the shell has one host, no toggle, and
 * lvTravelDocSetSurface() no longer exists. Those steps and columns came
 * out: a check that drives a deleted function is not a weaker check, it is
 * a crash. What replaced them is the single_surface probe, which asserts
 * the absence directly — one host element in the panel, no legacy host, no
 * toggle buttons, no surface setter, and no travel-documenter asset tag in
 * the live document. The "two surfaces are never painted at once" invariant
 * became "there is only one surface to paint", which is the stronger
 * statement and the one the shell can no longer violate.
 *
 * The double-mount risk itself did NOT go away with the toggle, and that is
 * why every census row below survives Phase 4 unchanged. Mounting over a
 * live mount, and leaving the tab without tearing down, are still the two
 * ways to end up with two of everything — they are just the only two now.
 *
 * HOW IT ISOLATES THE BEHAVIOUR
 * -----------------------------
 * window.fetch is replaced with one that parks every request. That keeps
 * the whole shell — not just Travel Doc — off any backend, and it means
 * the workspace paints only when the test releases its requests, so
 * "empty host" is an unambiguous starting state. window.WebSocket is
 * inert but counted, so the Lori socket census is real without dialling
 * anything. BroadcastChannel and document.addEventListener("keydown") are
 * wrapped to count bind/unbind rather than to observe effects: the module's
 * keydown handler early-returns unless a lightbox is open, so an "assert
 * no repaint on keypress" check would pass with the listener still bound.
 * Counting cannot go vacuous.
 *
 * WHAT THE ROWS MEAN
 * ------------------
 * The census columns are bc / key / ws: BroadcastChannel subscriptions,
 * document-level keydown listeners, Lori sockets. The workspace does not
 * dial Lori at mount — it connects only when the operator opens the Lori
 * pane — so ws is legitimately 0 on the mount rows and is exercised by the
 * lori_* rows instead.
 *
 *   open_unified      — tab opened with a narrator -> host paints, census
 *                       1/1/0
 *   leave_tab         — navigate to Operator       -> census back to 0/0/0
 *   reenter_tab       — back to Travel Doc         -> census 1/1/0, NOT 2
 *   narrator_switch   — person_id changes          -> remount, census 1/1/0
 *   lori_open         — click the workspace's Lori tab -> census 1/1/1.
 *                       This row is the non-vacuity guard for ws.
 *   lori_then_leave   — navigate away with Lori live -> 0/0/0, i.e.
 *                       destroy() gives the socket back
 *   lori_then_reenter — fresh mount, still one of each, no resurrected
 *                       socket
 *   destroyed_repaint — parked request released after the operator has
 *                       navigated away -> host MUST stay empty
 *   single_surface    — Phase 4: the shell offers exactly one Travel Doc
 *                       and no way to ask for another
 *
 * NEGATIVE CONTROLS — actually run, 2026-07-25, results as recorded
 * -----------------------------------------------------------------
 * Recorded against the TWO-surface build, before Phase 4. Kept because the
 * findings still describe this code, with the noted exceptions.
 *
 * 1. `if (tabName !== "traveldoc") ... lvTravelDocTeardownAll()` deleted:
 *    leave_tab kept the host painted at 1/1/0 and lori_then_leave held the
 *    socket open at 1/1/1. 5 checks red. RESULT FAIL. This is the
 *    load-bearing guard for tab exit, and it is unchanged by Phase 4 — the
 *    control is still valid as written, re-run it as written.
 * 2. lvTravelDocSetSurface()'s own teardown call deleted: still PASS.
 * 3. The cross-surface destroy at the top of the traveldoc block deleted:
 *    still PASS.
 * 4. BOTH of the above deleted together: switch_to_legacy reported both
 *    hosts painted with census 2/2, switch_to_unified likewise. 5 checks
 *    red including "two surfaces are never painted at once". RESULT FAIL.
 *
 *    Read 2 + 3 + 4 together, because 2 and 3 on their own were the more
 *    interesting result: the two toggle guards were MUTUALLY REDUNDANT, and
 *    either one alone prevented a double mount.
 *
 *    Controls 2, 3 and 4 are NOT re-runnable after Phase 4 — the setter and
 *    its teardown call no longer exist, and the cross-surface destroy has
 *    nothing to destroy. They are left recorded rather than deleted because
 *    they are the evidence for WHY the surviving destroy-before-mount in the
 *    traveldoc block is load-bearing on its own: it used to have a backstop,
 *    and Phase 4 removed the backstop. The remaining re-runnable control for
 *    that line is: delete `_lvTravelDocDestroyUnified()` from the remount
 *    arm and confirm narrator_switch reports 2/2.
 * 5. The ws attribution reverted to the original URL test (/travel_doc/):
 *    lori_open dropped to ws 0 and "opening the Lori pane actually opens
 *    one socket" went red. That URL never matched anything — the module
 *    dials apiBase + "/api/chat/ws" — so before the stack-based attribution
 *    every ws assertion in this file was decoration. The guard now fails
 *    loudly if attribution breaks again. Still valid, still re-runnable.
 *
 * If you change the mount logic, re-run these by hand. A green check that
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
  // Attribution is BY CALL STACK, not by URL. Travel Doc opens the same
  // endpoint the shell's own chat uses — st.apiBase + "/api/chat/ws" — so
  // there is nothing in the URL to tell a Travel Doc Lori socket from the
  // shell's. The first cut of this script tested the URL for /travel_doc/,
  // which matched neither module: __wsTravelDoc was pinned at 0 and "no
  // duplicate Travel Doc Lori socket" was a green check that could not go
  // red. Reading the stack costs one throw per socket and names the opening
  // file exactly. If the module is renamed — travel-doc-lab.js ->
  // travel-doc.js is parked but coming — update this regex; the vacuity
  // guard below will fail loudly rather than silently passing.
  //
  // Phase 4 dropped travel-documenter.js from this pattern. It is no longer
  // loaded by the shell, so it can never appear in a stack here, and leaving
  // it in would have made the pattern read as though two modules were still
  // in play.
  window.__wsOpen = 0;
  window.__wsTravelDoc = 0;
  window.WebSocket = function (url) {
    var stack = "";
    try { throw new Error(); } catch (e) { stack = String((e && e.stack) || ""); }
    var isTd = /travel-doc-lab\.js/.test(stack);
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

  // BroadcastChannel census, scoped to the named channel Travel Doc uses.
  // A duplicate here is a duplicate cross-tab refresh.
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
  // owned. Counting only binds whose stack names the Travel Doc module keeps
  // the number meaning what the column header says it means.
  window.__docKeydown = 0;
  var addEL = document.addEventListener.bind(document);
  var remEL = document.removeEventListener.bind(document);
  var fromTd = function () {
    var s = "";
    try { throw new Error(); } catch (e) { s = String((e && e.stack) || ""); }
    return /travel-doc-lab\.js/.test(s);
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
  //
  // Phase 4 removed two lines that used to sit here: a
  // localStorage.removeItem("lvTravelDocSurface") to start from a known
  // surface regardless of any stored preference, and a reset of the
  // _lvTravelDocActiveSurface cache. Neither key exists any more — the
  // stored preference was the toggle's memory and went out with it.
  await page.evaluate(() => {
    window.state = window.state || {};
    window.state.person_id = "ptest";
    // Baseline the censuses AFTER the shell has finished its own boot, so
    // the numbers below are Travel Doc's and nobody else's.
    window.__base = { bc: window.__bcOpen, key: window.__docKeydown,
                      ws: window.__wsTravelDoc };
  });

  /** Drive one operator step, then report the state of the surface. */
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

    // Phase 4: the legacy host, the .lv-td-host-off visibility test and the
    // toggle's aria-pressed readout were all reported here. There is one
    // host now, it is never hidden behind anything, and there is no toggle
    // to read. The single_surface probe below asserts that those things are
    // gone rather than this row quietly no longer mentioning them.
    const uni = document.getElementById("lvTravelDocUnifiedHost");
    const painted = (el) => !!el && el.childElementCount > 0;
    return {
      label,
      uniPainted: painted(uni),
      uniScoped: !!uni && uni.classList.contains("tdl-root") &&
                 uni.classList.contains("tdl-root-embedded"),
      bc: window.__bcOpen - window.__base.bc,
      key: window.__docKeydown - window.__base.key,
      ws: window.__wsTravelDoc - window.__base.ws,
    };
  }, [label, script]);

  const rows = [];
  rows.push(await step("open_unified", 'lvShellShowTab("traveldoc");'));
  rows.push(await step("leave_tab", 'lvShellShowTab("operator");'));
  rows.push(await step("reenter_tab", 'lvShellShowTab("traveldoc");'));
  rows.push(await step("narrator_switch",
    'window.state.person_id = "pother"; window.lvTravelDocTeardownAll(); ' +
    'lvShellShowTab("traveldoc");'));

  // The Lori socket is NOT opened at mount — the module dials only when the
  // operator opens the Lori pane (renderLoriTab -> loriPane.connect()). So
  // every row above legitimately reports ws 0, and the acceptance line "no
  // duplicate Travel Doc Lori socket" is untested unless the script opens
  // the pane itself. Click the workspace's own "Lori" tab button, the way an
  // operator would, rather than reaching into module internals the shell
  // cannot see.
  rows.push(await step("lori_open",
    'var h = document.getElementById("lvTravelDocUnifiedHost");' +
    'var b = Array.prototype.find.call(h.querySelectorAll("button"),' +
    '  function (x) { return x.textContent.trim() === "Lori"; });' +
    'if (!b) throw new Error("no Lori tab button in the mounted workspace");' +
    'b.click();'));
  rows.push(await step("lori_then_leave", 'lvShellShowTab("operator");'));
  rows.push(await step("lori_then_reenter", 'lvShellShowTab("traveldoc");'));

  // WO-TRAVEL-DOC-UNIFY-01 Phase 4 — the removal, asserted against the LIVE
  // document rather than against app.js source.
  //
  // The Python suite can prove the strings are gone from the files. It
  // cannot prove the browser ended up with one host: a stale cached asset,
  // a second copy of the panel markup, or a legacy tag reintroduced by any
  // other shell path would all read as green there and paint two surfaces
  // here. This probe reads what actually loaded.
  const singleSurface = await page.evaluate(() => {
    const panel = document.getElementById("lvTravelDocTab");
    const assets = Array.prototype.map.call(
      document.querySelectorAll("script[src], link[href]"),
      (n) => n.getAttribute("src") || n.getAttribute("href"));
    return {
      hosts: panel ? panel.querySelectorAll(".lv-td-host").length : -1,
      panelChildren: panel ? panel.childElementCount : -1,
      legacyHost: !!document.getElementById("lvTravelDocHost"),
      switchRow: document.querySelectorAll(".lv-td-surface-switch").length,
      surfaceBtns: document.querySelectorAll("[data-td-surface]").length,
      hasSetter: typeof window.lvTravelDocSetSurface !== "undefined",
      hasResolver: typeof window.lvTravelDocSurface !== "undefined",
      legacyAssets: assets.filter((a) => /travel-documenter\.(js|css)/.test(a)),
      // The stored preference must not merely be unread — nothing may write
      // it either, or the next operator to open the tab inherits a key that
      // no longer means anything.
      storedPref: (function () {
        try { return localStorage.getItem("lvTravelDocSurface"); }
        catch (e) { return null; }
      })(),
    };
  });

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

  // The operator path must not advertise itself as an experiment, name the
  // surface it replaced, or offer a way back to it.
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
      // Phase 4 additions: the operator must not be told there is a legacy
      // surface, an older Documenter, or a production Travel Doc elsewhere.
      hasLegacyWord: /\blegacy\b/i.test(text),
      hasDocumenter: /documenter/i.test(text),
      hasProdTravelDoc: /production travel doc/i.test(text),
      painted: document.getElementById("lvTravelDocUnifiedHost")
                 .childElementCount > 0,
    };
  });

  const unhandled = await page.evaluate(() => window.__unhandled);
  await browser.close();
  srv.close();

  const pad = (v, n) => String(v).padEnd(n);
  console.log("step               painted   scoped   bc  key  ws");
  rows.forEach((r) => console.log(
    pad(r.label, 19) + pad(r.uniPainted, 10) +
    pad(r.uniScoped ? "tdl" : "-", 9) +
    pad(r.bc, 4) + pad(r.key, 5) + r.ws));
  console.log("\nsingle surface   :", JSON.stringify(singleSurface));
  console.log("destroyed repaint:", JSON.stringify(destroyedRepaint));
  console.log("operator branding:", JSON.stringify(branding));
  console.log("unhandled reject :", unhandled.length ? unhandled.join(" | ") : "none");
  console.log("page errors      :", errs.length ? errs.join("\n  ") : "none");

  const [open, leave, reenter, switchPerson,
         loriOpen, loriLeave, loriReenter] = rows;
  // ws <= 1 for the mount rows because the workspace does not dial at mount;
  // the lori_* rows below are where the socket is required to be exactly 1
  // and then exactly 0.
  const oneOfEach = (r) => r.bc === 1 && r.key === 1 && r.ws <= 1;
  const noneOfEach = (r) => r.bc === 0 && r.key === 0 && r.ws === 0;

  const checks = [
    ["tab open renders the unified workspace",
     open.uniPainted && open.uniScoped],
    ["one channel, one keydown, one socket while open", oneOfEach(open)],
    ["leaving the tab destroys everything",
     !leave.uniPainted && noneOfEach(leave)],
    ["re-entering mounts exactly one again",
     reenter.uniPainted && oneOfEach(reenter)],
    ["narrator switch remounts exactly one",
     switchPerson.uniPainted && oneOfEach(switchPerson)],
    // Phase 4 — the removal, observed in the live document.
    ["the tab holds exactly one Travel Doc host",
     singleSurface.hosts === 1 && singleSurface.panelChildren === 1],
    ["the legacy host is not in the document", !singleSurface.legacyHost],
    ["no surface toggle is rendered",
     singleSurface.switchRow === 0 && singleSurface.surfaceBtns === 0],
    ["no surface setter or resolver is exposed",
     !singleSurface.hasSetter && !singleSurface.hasResolver],
    ["the shell loads no travel-documenter asset",
     singleSurface.legacyAssets.length === 0],
    ["nothing writes the retired surface preference",
     singleSurface.storedPref === null],
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
    ["operator path never mentions a legacy surface",
     !branding.hasLegacyWord && !branding.hasDocumenter &&
     !branding.hasProdTravelDoc],
    ["no unhandled rejections", unhandled.length === 0],
    ["no page errors", errs.length === 0],
  ];
  console.log("");
  checks.forEach(([label, ok]) => console.log((ok ? "  ok   " : "  FAIL ") + label));
  const pass = checks.every((c) => c[1]);
  console.log("\nRESULT           :", pass ? "PASS" : "FAIL");
  process.exit(pass ? 0 : 1);
})();
