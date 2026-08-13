#!/usr/bin/env node
/**
 * WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 Phase 3b — window arithmetic.
 *
 *   node scripts/ui/run_photo_window_arithmetic.js
 *
 * No browser, no backend, no arguments. Exits 0 on PASS / 1 on FAIL.
 *
 * WHAT THIS EXECUTES
 * ------------------
 * The REAL `photoWindow` and `slidePhotoWindow` from
 * ui/js/travel-doc-lab.js, lifted out of the module by source extraction
 * and run against a stub `st`. Not a copy of the logic — the shipped
 * text. Edit either function and this sees the edit; delete one and this
 * fails to build its sandbox.
 *
 * WHY EXTRACTION RATHER THAN A BROWSER
 * ------------------------------------
 * The companion script run_photo_window_liveness.js drives the real DOM
 * and is the better instrument for "can the operator reach and click the
 * thirteenth photograph". It needs Chromium, which will not launch in
 * the agent sandbox (chrome-headless-shell cannot load libXdamage.so.1
 * and the container has no sudo to install it). Shipping that harness
 * unrun and calling it evidence would be exactly the thing this project
 * keeps catching.
 *
 * So the load-shape MATHS — bounded window, fifty-item steps, clamping
 * against a list that shrank, reachability of the last item — is proved
 * here, where it can actually run, and the DOM half is proved on a
 * machine with browsers. Between them nothing is asserted without
 * having been executed somewhere.
 *
 * THE PROPERTIES
 * --------------
 *   bounded      window width never exceeds its maximum
 *   stepwise     one slide moves the edge by exactly one page
 *   reachable    repeated slides reach the last item of any list
 *   terminating  sliding forward always halts
 *   clamped      a window pointing past a shrunken list still renders
 *   monotone     sliding back then forward returns where it started
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SRC = path.resolve(__dirname, "..", "..",
  "ui", "js", "travel-doc-lab.js");

function extract(name, src) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error("cannot find function " + name);
  let depth = 0;
  const open = src.indexOf("{", start);
  for (let i = open; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  throw new Error("unterminated " + name);
}

const src = fs.readFileSync(SRC, "utf8");

// The two constants, read from the source rather than restated here —
// a test that hard-codes 50 passes after somebody changes the product
// to 25.
function constant(name) {
  const m = new RegExp("var " + name + " = (\\d+);").exec(src);
  if (!m) throw new Error("cannot find " + name);
  return Number(m[1]);
}
const PAGE = constant("PHOTO_PAGE_SIZE");
const WIDE = constant("PHOTO_WINDOW_MAX");
const SECTION = constant("PHOTO_WINDOW_MAX_SECTION");

const sandbox = new Function(
  "PHOTO_PAGE_SIZE", "PHOTO_WINDOW_MAX", "st", "renderAll",
  extract("photoWindow", src) + "\n" +
  extract("slidePhotoWindow", src) + "\n" +
  "return { photoWindow: photoWindow, slidePhotoWindow: slidePhotoWindow };"
);

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

function fresh() {
  const st = { photoWindows: {} };
  return { st, api: sandbox(PAGE, WIDE, st, function () {}) };
}

// ── bounded / stepwise / reachable / terminating ────────────────────
[[327, WIDE], [327, SECTION], [51, SECTION], [1000, WIDE], [13, SECTION]]
  .forEach(function (pair) {
    const total = pair[0];
    const wide = pair[1];
    const { api } = fresh();
    const key = "k" + total + "-" + wide;

    let w = api.photoWindow(key, total, wide);
    check("[" + total + "/" + wide + "] first view is one page",
      w.end - w.start === Math.min(PAGE, total),
      w.start + "-" + w.end);

    let widest = w.end - w.start;
    let steps = 0;
    let lastEnd = w.end;
    while (w.end < total) {
      api.slidePhotoWindow(key, total, wide, 1);
      w = api.photoWindow(key, total, wide);
      const grew = w.end - lastEnd;
      if (grew !== Math.min(PAGE, total - lastEnd)) {
        check("[" + total + "/" + wide + "] each step is one page", false,
          "grew " + grew + " at end=" + lastEnd);
      }
      lastEnd = w.end;
      widest = Math.max(widest, w.end - w.start);
      if (++steps > total) break;                    // runaway guard
    }
    check("[" + total + "/" + wide + "] each step is one page",
      !R.some((r) => !r.ok && r.name.indexOf("[" + total + "/" + wide +
        "] each step") === 0));
    check("[" + total + "/" + wide + "] sliding forward terminates",
      steps <= Math.ceil(total / PAGE), "steps=" + steps);
    check("[" + total + "/" + wide + "] the last item becomes reachable",
      w.end === total, "end=" + w.end + " total=" + total);
    check("[" + total + "/" + wide + "] the window never exceeds its bound",
      widest <= wide, "widest=" + widest);
  });

// ── monotone: back then forward returns ─────────────────────────────
{
  const { api } = fresh();
  const key = "mono";
  for (let i = 0; i < 6; i++) api.slidePhotoWindow(key, 327, SECTION, 1);
  const before = JSON.stringify(api.photoWindow(key, 327, SECTION));
  api.slidePhotoWindow(key, 327, SECTION, -1);
  api.slidePhotoWindow(key, 327, SECTION, 1);
  const after = JSON.stringify(api.photoWindow(key, 327, SECTION));
  check("back then forward returns to the same window",
    before === after, before + " -> " + after);
}

// ── clamped: the list shrank under the window ───────────────────────
{
  const { api } = fresh();
  const key = "shrink";
  for (let i = 0; i < 5; i++) api.slidePhotoWindow(key, 327, SECTION, 1);
  const w = api.photoWindow(key, 3, SECTION);     // 327 photos became 3
  check("a shrunken list still renders something",
    w.start === 0 && w.end === 3, JSON.stringify(w));
}
{
  const { api } = fresh();
  const key = "empty";
  const w = api.photoWindow(key, 0, SECTION);
  check("an emptied list does not produce a negative window",
    w.start === 0 && w.end >= 0 && w.end - w.start >= 0, JSON.stringify(w));
}

// ── the day inspector's two sections cannot exceed the drawer bound ──
check("two sections at their bound stay within the drawer bound",
  SECTION * 2 <= WIDE, "2x" + SECTION + " vs " + WIDE);
check("a page fits inside a section window", PAGE <= SECTION,
  PAGE + " vs " + SECTION);

// ── the client limit matches the server's ───────────────────────────
{
  const server = fs.readFileSync(path.resolve(__dirname, "..", "..",
    "server", "code", "api", "routers", "trips.py"), "utf8");
  const m = /PLACEMENT_BATCH_MAX = (\d+)/.exec(server);
  const clientM = /var PLACEMENT_BATCH_MAX = (\d+);/.exec(src);
  check("client and server batch limits agree",
    !!m && !!clientM && m[1] === clientM[1],
    (clientM ? clientM[1] : "?") + " vs " + (m ? m[1] : "?"));
  check("the page size matches the batch limit",
    !!clientM && Number(clientM[1]) === PAGE,
    PAGE + " vs " + (clientM ? clientM[1] : "?"));
}

let bad = 0;
R.forEach((r) => {
  if (!r.ok) bad++;
  console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
    (r.detail ? "   [" + r.detail + "]" : ""));
});
console.log("\n" + (R.length - bad) + "/" + R.length + " checks passed");
process.exit(bad ? 1 : 0);
