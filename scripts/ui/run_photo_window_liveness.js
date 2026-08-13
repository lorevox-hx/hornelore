#!/usr/bin/env node
/**
 * WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 3b — bounded photo windows.
 *
 *   node scripts/ui/run_photo_window_liveness.js
 *
 * No backend, no manual server, no arguments. Serves the repo on an
 * ephemeral port, loads ui/travel-doc-lab.html in headless Chromium
 * against a canned API, and exits 0 on PASS / 1 on FAIL.
 *
 * WHY A BROWSER AND NOT A SOURCE SCAN
 * -----------------------------------
 * tests/test_trip_photo_multi_day_ui.py asserts the SHAPE of the
 * windowing — that the helpers exist, that the picker routes through
 * the batching path, that nothing reads the compatibility scalar. Those
 * are properties of the text and hold for code no fixture exercises.
 *
 * They cannot answer the question the review actually asked, which is a
 * question about the DOM: **can the operator reach the thirteenth
 * photograph on a day, and the fifty-first, and operate on it?** The
 * bug being closed was `dayLinks.slice(0, 12)`, and a slice is
 * invisible to every static check that does not know the number. Only
 * counting rendered tiles and clicking the control can prove it.
 *
 * WHAT IS FAKED, AND WHAT IS NOT
 * ------------------------------
 * `window.fetch` answers a small canned API: one person, one trip, one
 * day, and N photo links all placed on that day. Everything above that
 * — the module, the render loop, the pager, the event handlers — is the
 * real shipped code. The fake is the network, not the behaviour.
 *
 * Photo links carry `trip_day_ids` (the Phase 2 authoritative field)
 * and a NULL `trip_day_id`, which is what the server sends for a
 * photograph on several days. That is deliberate: it is the exact
 * payload that made the old UI call a placed photograph "Unplaced".
 *
 * THE SCENARIOS
 * -------------
 *   initial      — 327 on a day: exactly 50 tiles, pager says so
 *   reach_13     — the 13th photograph has a row and a Remove control
 *   load_more    — one click exposes exactly 50 more
 *   reach_51     — the 51st is reachable and operable after one click
 *   bounded      — clicking Load more to the end never exceeds the bound
 *   selection    — a ticked photo stays ticked across a window slide
 *   eager        — every mounted thumbnail is eager, not loading=lazy
 *
 * `bounded` is the load-shape half and `reach_51` is the correctness
 * half; both have to hold, and passing one while failing the other is
 * exactly the state this phase was sent back to fix.
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

// Deliberately not multiples of the page size, and deliberately two
// separate populations.
//
// CORRECTED 2026-08-13 after the first laptop run. The fixture placed
// ALL 327 photographs on Day 1, which is exactly right for the
// inspector's reachability checks and leaves the Day 1 PICKER correctly
// empty — the picker excludes what is already on the day. The selection
// scenario then dereferenced a checkbox that could not exist and the
// harness died with a TypeError instead of reporting a failed check.
//
// That was a fixture bug and a harness-discipline bug at once: the data
// did not support the question, and no guard said so. Both are fixed —
// a second population gives the picker real candidates, and every
// selector below is checked before it is used.
const TOTAL_ON_DAY = 327;      // placed on Day 1: the inspector's list
const TOTAL_ELSEWHERE = 240;   // placed on Day 2 only: the Day 1 picker's
                               // candidates, deliberately above the 200 bound

function serveRepo() {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      if (/^\/favicon\.ico/.test(req.url)) { res.writeHead(204); res.end(); return; }
      const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "");
      const file = path.join(REPO, rel);
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

// Runs in the page before any app script.
function installHarness(counts) {
  var total = counts.onDay;
  var elsewhere = counts.elsewhere;
  window.__unhandled = [];
  window.addEventListener("unhandledrejection", function (e) {
    window.__unhandled.push(String((e.reason && e.reason.message) || e.reason));
  });
  window.__pageErrors = [];
  window.addEventListener("error", function (e) {
    window.__pageErrors.push(String(e.message));
  });

  window.WebSocket = function () {
    this.readyState = 0;
    this.close = function () {};
    this.send = function () {};
  };

  var DAY = { id: "d1", trip_id: "t1", day_index: 1, date: "2026-05-01",
              title: "First day", counts: { photos: total, photo_suggestions: 0,
                                            notes: 0, sources: 0,
                                            public_context: 0 } };
  var DAY2 = { id: "d2", trip_id: "t1", day_index: 2, date: "2026-05-02",
               title: "Second day", counts: { photos: 0, photo_suggestions: 0,
                                              notes: 0, sources: 0,
                                              public_context: 0 } };

  var links = [];
  for (var i = 0; i < total; i++) {
    links.push({
      id: "L" + i,
      trip_id: "t1",
      photo_id: "P" + i,
      caption: "photo " + i,
      ord: i,
      taken_at: null,
      hidden: 0,
      trip_stop_id: null,
      trip_region_id: null,
      // The Phase 2 payload for a photograph on a day. The scalar is
      // deliberately null on the ones with two placements.
      trip_day_ids: (i % 10 === 0) ? ["d1", "d2"] : ["d1"],
      trip_day_id: (i % 10 === 0) ? null : "d1",
      day_placements: (i % 10 === 0)
        ? [{ id: "pl" + i + "a", trip_day_id: "d1", ord: i,
             placement_method: "operator", placement_note: null,
             day_index: 1, day_date: "2026-05-01" },
           { id: "pl" + i + "b", trip_day_id: "d2", ord: i,
             placement_method: "operator", placement_note: null,
             day_index: 2, day_date: "2026-05-02" }]
        : [{ id: "pl" + i, trip_day_id: "d1", ord: i,
             placement_method: "operator", placement_note: null,
             day_index: 1, day_date: "2026-05-01" }],
    });
  }

  // The Day 1 picker's candidates: placed on Day 2 only, so they are
  // eligible for Day 1 and the picker has something to page through.
  // Without these the picker is correctly empty and the selection
  // scenario has nothing to select — which is how the first version of
  // this harness died.
  for (var j = 0; j < elsewhere; j++) {
    links.push({
      id: "E" + j,
      trip_id: "t1",
      photo_id: "Q" + j,
      caption: "elsewhere " + j,
      ord: j,
      taken_at: null,
      hidden: 0,
      trip_stop_id: null,
      trip_region_id: null,
      trip_day_ids: ["d2"],
      trip_day_id: "d2",
      day_placements: [{ id: "ep" + j, trip_day_id: "d2", ord: j,
                         placement_method: "operator", placement_note: null,
                         day_index: 2, day_date: "2026-05-02" }],
    });
  }

  window.__requests = [];
  function json(body) {
    return Promise.resolve({
      ok: true, status: 200,
      text: function () { return Promise.resolve(JSON.stringify(body)); },
      json: function () { return Promise.resolve(body); },
    });
  }
  window.fetch = function (url, init) {
    var u = String(url);
    window.__requests.push({ url: u, method: (init && init.method) || "GET" });
    if (/\/api\/people/.test(u)) {
      return json({ people: [{ id: "ptest", display_name: "Test Person" }] });
    }
    if (/\/api\/trips\/t1\/days\b/.test(u)) {
      return json({ days: [DAY, DAY2], preserved: [] });
    }
    if (/\/api\/trips\/t1\/photo-links/.test(u)) {
      return json({ photo_links: links });
    }
    if (/\/api\/trips\/t1\/tree/.test(u)) {
      return json({ trip: { id: "t1", title: "Trip One" }, regions: [],
                    stops: [], themes: [] });
    }
    if (/\/api\/trips\?/.test(u) || /\/api\/trips$/.test(u)) {
      return json({ trips: [{ id: "t1", title: "Trip One",
                              start_date: "2026-05-01",
                              end_date: "2026-05-02" }] });
    }
    // Everything else answers empty rather than failing: this harness
    // is about the photo window, and a 404 elsewhere would paint an
    // error banner over the surface under test.
    return json({});
  };
}

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
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
  const url = "http://127.0.0.1:" + srv.address().port +
    "/ui/travel-doc-lab.html?person_id=ptest";

  const launchOpts = {};
  if (process.env.PLAYWRIGHT_CHROMIUM_PATH) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH;
  }
  const browser = await chromium.launch(launchOpts);
  const page = await browser.newPage();
  await page.addInitScript(installHarness,
    { onDay: TOTAL_ON_DAY, elsewhere: TOTAL_ELSEWHERE });
  await page.goto(url, { waitUntil: "domcontentloaded" });

  // Driven through the REAL DOM — click the trip, click the day card,
  // open the Photos section. No test-only hook was added to the module
  // for this: a hook is production code that exists to be lied to, and
  // the route into the inspector is exactly the route the operator
  // takes.
  // Wrapped: a selector that never appears is a FAILED CHECK with a
  // verdict, not a thrown timeout that ends the run silently.
  let reachedInspector = true;
  try {
    await page.waitForSelector(".tdl-trip-list button", { timeout: 10000 });
    await page.click(".tdl-trip-list button");
    await page.waitForSelector(".tdl-day-card", { timeout: 10000 });
    await page.click(".tdl-day-card");
    await page.waitForSelector(".tdl-ins-sec", { timeout: 10000 });
  } catch (e) {
    reachedInspector = false;
    check("the day inspector opens", false, String(e.message).slice(0, 120));
  }
  check("reached the day inspector", reachedInspector);
  // The Photos section is collapsed by default; <details> renders its
  // children either way, but opening it is what the operator does and
  // keeps the measurements about what they can see.
  await page.evaluate(() => {
    Array.prototype.slice.call(document.querySelectorAll(".tdl-ins-sec"))
      .forEach(function (d) {
        var s = d.querySelector("summary");
        if (s && /^Photos/.test(s.textContent)) d.open = true;
      });
  });
  await page.waitForTimeout(300);

  const tiles = () => page.evaluate(() => {
    var root = document.querySelector(".tdl-root");
    if (!root) {
      return { onDay: 0, allImgs: 0, pager: "", firstCaption: "",
               lastCaption: "", lazyImgs: 0, mounted: false };
    }
    var onDay = root.querySelectorAll(".tdl-photo-row .tdl-photo-cell");
    return {
      onDay: onDay.length,
      allImgs: root.querySelectorAll("img").length,
      pager: (function () {
        var p = root.querySelector(".tdl-photo-pager");
        return p ? p.textContent : "";
      })(),
      firstCaption: onDay.length ? onDay[0].querySelector("img").alt : "",
      lastCaption: onDay.length
        ? onDay[onDay.length - 1].querySelector("img").alt : "",
      lazyImgs: root.querySelectorAll('img[loading="lazy"]').length,
      mounted: true,
    };
  });

  const clickLoadMore = () => page.evaluate(() => {
    var b = Array.prototype.slice.call(
      document.querySelectorAll(".tdl-photo-pager button"))
      .filter(function (x) { return /Load more/.test(x.textContent); })[0];
    if (!b) return false;
    b.click();
    return true;
  });

  // ── initial ──────────────────────────────────────────────────────
  let t = await tiles();
  check("the workspace mounted", t.mounted);
  check("initial mounts exactly one page", t.onDay === 50, "onDay=" + t.onDay);
  // The count is the day's PLACEMENTS, not the trip's photographs: the
  // fixture also holds TOTAL_ELSEWHERE links placed on Day 2 only, and
  // they must not appear here.
  //
  // `(?!\d)` and NOT `\b`. The pager is read with textContent, which
  // concatenates its spans without spaces — "…of 327Load more (277
  // left)". `\b` after 327 asks for a word boundary between "7" and
  // "L", and both are word characters, so there is none: the assertion
  // failed on a pager that said exactly what it was asked to say. The
  // sibling check below passed only because its next character happened
  // to be "↑". A negative lookahead for a digit is what was meant all
  // along — it still tells 327 from 3270 and from the combined 567.
  check("the day shows exactly its own placements",
    new RegExp("of " + TOTAL_ON_DAY + "(?!\\d)").test(t.pager),
    t.pager.slice(0, 80));
  check("photographs placed on another day are not on this one",
    !new RegExp("of " + (TOTAL_ON_DAY + TOTAL_ELSEWHERE)).test(t.pager),
    t.pager.slice(0, 80));
  check("the pager does not present the batch as a cap",
    !/maximum|cap|limit/i.test(t.pager), t.pager.slice(0, 80));

  // ── reach_13 ─────────────────────────────────────────────────────
  const thirteenth = await page.evaluate(() => {
    var cells = document.querySelectorAll(".tdl-photo-row .tdl-photo-cell");
    if (cells.length < 13) return null;
    var c = cells[12];
    var btns = Array.prototype.slice.call(c.querySelectorAll("button"))
      .map(function (b) { return b.textContent; });
    return { alt: c.querySelector("img").alt, buttons: btns };
  });
  check("the 13th photograph has a row", !!thirteenth,
    thirteenth ? thirteenth.alt : "absent");
  check("the 13th photograph can be removed",
    !!thirteenth && thirteenth.buttons.some((b) => /Remove from this day/.test(b)),
    thirteenth ? thirteenth.buttons.join("|") : "");
  check("the 13th photograph can be moved",
    !!thirteenth && thirteenth.buttons.some((b) => /Move/.test(b)),
    thirteenth ? thirteenth.buttons.join("|") : "");

  // ── load_more ────────────────────────────────────────────────────
  const clicked = await clickLoadMore();
  await page.waitForTimeout(250);
  const after = await tiles();
  check("Load more exists", clicked);
  check("one click exposes exactly one more page",
    after.onDay === 100, "onDay=" + after.onDay);

  // ── reach_51 ─────────────────────────────────────────────────────
  const fiftyFirst = await page.evaluate(() => {
    var cells = document.querySelectorAll(".tdl-photo-row .tdl-photo-cell");
    var hit = Array.prototype.slice.call(cells).filter(function (c) {
      return c.querySelector("img").alt === "photo 50";
    })[0];
    if (!hit) return null;
    return {
      buttons: Array.prototype.slice.call(hit.querySelectorAll("button"))
        .map(function (b) { return b.textContent; }),
    };
  });
  check("the 51st photograph is reachable", !!fiftyFirst);
  check("the 51st photograph is operable",
    !!fiftyFirst && fiftyFirst.buttons.some((b) => /Remove from this day/.test(b)),
    fiftyFirst ? fiftyFirst.buttons.join("|") : "");

  // ── bounded ──────────────────────────────────────────────────────
  let guard = 0;
  let peak = after.onDay;
  while (await clickLoadMore()) {
    await page.waitForTimeout(120);
    const s = await tiles();
    if (s.onDay > peak) peak = s.onDay;
    if (++guard > 20) break;
  }
  const end = await tiles();
  check("paging to the end terminates", guard <= 20, "clicks=" + guard);
  check("the mounted tile count stays bounded", peak <= 100,
    "peak=" + peak);
  check("the whole surface stays near the 200 bound", end.allImgs <= 200,
    "imgs=" + end.allImgs);
  check("the last photograph is reachable at the end",
    end.lastCaption === "photo 326", end.lastCaption);
  check("the pager still reports the true total",
    new RegExp("of " + TOTAL_ON_DAY + "(?!\\d)").test(end.pager),
    end.pager.slice(0, 80));

  // ── eager ────────────────────────────────────────────────────────
  check("no mounted thumbnail uses native lazy loading",
    end.lazyImgs === 0, "lazy=" + end.lazyImgs);

  // ── the Day 1 picker ─────────────────────────────────────────────
  //
  // Every read below is null-safe and reports a FAILED CHECK rather
  // than throwing. The first version of this harness dereferenced a
  // checkbox that could not exist and died with a TypeError, so the run
  // ended with no verdict at all — a harness that crashes tells you
  // less than one that fails.
  const opened = await page.evaluate(() => {
    var b = Array.prototype.slice.call(document.querySelectorAll("button"))
      .filter(function (x) { return /Add photos/.test(x.textContent); })[0];
    if (!b) return false;
    b.click();
    return true;
  });
  check("the Add photos control exists", opened);

  await page.waitForTimeout(350);

  const pickState = () => page.evaluate(() => {
    // Always the full shape, defaults included. Returning a short
    // object on the absent branch would push the null-dereference one
    // level out into the check() arguments, which is the same crash in
    // a place harder to see.
    var drawer = document.querySelector(".tdl-drawer");
    if (!drawer) {
      return { present: false, cells: 0, ticked: 0, firstAlt: "",
               lastAlt: "", label: "", pager: "", boxes: 0, lazy: 0 };
    }
    var cells = drawer.querySelectorAll(".tdl-picker-cell");
    var boxes = drawer.querySelectorAll(".tdl-picker-cell input[type=checkbox]");
    var primary = drawer.querySelector(".tdl-btn-primary");
    var pager = drawer.querySelector(".tdl-photo-pager");
    return {
      present: true,
      cells: cells.length,
      ticked: drawer.querySelectorAll(
        ".tdl-picker-cell input[type=checkbox]:checked").length,
      firstAlt: cells.length ? cells[0].querySelector("img").alt : "",
      lastAlt: cells.length
        ? cells[cells.length - 1].querySelector("img").alt : "",
      label: primary ? primary.textContent : "",
      pager: pager ? pager.textContent : "",
      boxes: boxes.length,
      lazy: drawer.querySelectorAll('img[loading="lazy"]').length,
    };
  });

  const slidePicker = (dir) => page.evaluate((d) => {
    var drawer = document.querySelector(".tdl-drawer");
    if (!drawer) return false;
    var want = d > 0 ? /Load more/ : /Earlier/;
    var b = Array.prototype.slice.call(
      drawer.querySelectorAll(".tdl-photo-pager button"))
      .filter(function (x) { return want.test(x.textContent); })[0];
    if (!b) return false;
    b.click();
    return true;
  }, dir);

  let p = await pickState();
  check("the picker drawer opened", p.present);
  check("the picker has eligible candidates", p.present && p.cells > 0,
    "cells=" + (p.cells || 0));
  check("the picker mounts exactly one page",
    p.present && p.cells === 50, "cells=" + p.cells);
  check("the picker states its own true total",
    p.present && new RegExp("of " + TOTAL_ELSEWHERE + "(?!\\d)").test(p.pager),
    p.pager.slice(0, 80));
  check("picker thumbnails are eager", p.present && p.lazy === 0,
    "lazy=" + p.lazy);

  const firstAlt = p.firstAlt;
  const ticked = await page.evaluate(() => {
    var cb = document.querySelector(
      ".tdl-drawer .tdl-picker-cell input[type=checkbox]");
    if (!cb) return false;
    cb.checked = true;
    cb.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  });
  check("a candidate can be selected", ticked);
  await page.waitForTimeout(150);
  p = await pickState();
  check("the Add button reports the selection",
    /Add 1 /.test(p.label), p.label);

  // Slide forward past the bound so the ticked cell leaves the window.
  let pSteps = 0;
  let pPeak = p.cells;
  while (await slidePicker(1)) {
    await page.waitForTimeout(120);
    p = await pickState();
    pPeak = Math.max(pPeak, p.cells);
    if (++pSteps > 20) break;
  }
  check("paging the picker terminates", pSteps <= 20, "clicks=" + pSteps);
  check("one picker click exposes one page at a time", pSteps === 4,
    "clicks=" + pSteps + " for " + TOTAL_ELSEWHERE + " candidates");
  check("mounted picker cells never exceed the bound", pPeak <= 200,
    "peak=" + pPeak);
  check("the picker reaches its last candidate",
    p.lastAlt === "elsewhere " + (TOTAL_ELSEWHERE - 1), p.lastAlt);
  check("the window slid past the selected cell",
    p.firstAlt !== firstAlt, firstAlt + " -> " + p.firstAlt);
  check("the selected checkbox is outside the current window",
    p.ticked === 0, "ticked=" + p.ticked);
  check("the Add button still reports the stored selection",
    /Add 1 /.test(p.label), p.label);

  // And back again: the tick must reappear on the very same cell.
  while (await slidePicker(-1)) {
    await page.waitForTimeout(120);
    p = await pickState();
    if (p.firstAlt === firstAlt) break;
  }
  check("sliding back returns to the first window",
    p.firstAlt === firstAlt, p.firstAlt);
  check("the selection survived the round trip", p.ticked === 1,
    "ticked=" + p.ticked);
  check("the Add button is unchanged by the round trip",
    /Add 1 /.test(p.label), p.label);

  // ── hygiene ──────────────────────────────────────────────────────
  const noise = await page.evaluate(() => ({
    unhandled: window.__unhandled, errors: window.__pageErrors,
  }));
  check("no unhandled rejections", noise.unhandled.length === 0,
    noise.unhandled.join("|"));
  check("no page errors", noise.errors.length === 0, noise.errors.join("|"));

  await browser.close();
  srv.close();

  let bad = 0;
  R.forEach((r) => {
    if (!r.ok) bad++;
    console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
      (r.detail ? "   [" + r.detail + "]" : ""));
  });
  console.log("\n" + (R.length - bad) + "/" + R.length + " checks passed");
  process.exit(bad ? 1 : 0);
})();
