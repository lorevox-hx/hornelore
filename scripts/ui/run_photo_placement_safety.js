#!/usr/bin/env node
/**
 * WO-TRIP-PHOTO-MULTI-DAY-PLACEMENT-01 — Phase 5 readiness.
 *
 * Two behaviours that a source scan cannot judge, proved by EXECUTING
 * the shipped functions:
 *
 *   1. A multi-batch Add that fails half way is reported as what it is.
 *      Not "it worked", not "it failed" — 50 of 120, with the ones that
 *      landed visible on the day and the rest still selected.
 *
 *   2. The day inspector's photo controls do not discard typed edits.
 *      Remove from this day, Move…, and the direct "Add to this day"
 *      on a Taken-on-this-date suggestion all end in reloadDays() +
 *      renderAll(), which rebuilds the form from the SAVED row.
 *
 * Why not Playwright: neither behaviour needs a DOM. Both need an `api`
 * that fails on demand, which is far easier to arrange here — and the
 * functions are lifted out of ui/js/travel-doc-lab.js by name, so this
 * runs the real code rather than a restatement of it. A copy of the
 * batching logic would keep passing after somebody changed the product.
 *
 * Usage:  node scripts/ui/run_photo_placement_safety.js
 * Exit 0 all green, 1 otherwise. No server, no browser, no arguments.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SRC = path.resolve(__dirname, "..", "..",
  "ui", "js", "travel-doc-lab.js");
const src = fs.readFileSync(SRC, "utf8");

function extract(name) {
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

function constant(name) {
  const m = new RegExp("var " + name + " = (\\d+);").exec(src);
  if (!m) throw new Error("cannot find " + name);
  return Number(m[1]);
}
const BATCH = constant("PLACEMENT_BATCH_MAX");

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

/**
 * A sandbox holding the real functions and a recording `api`.
 *
 * `failOn` is a 1-based batch number that rejects; 0 means never.
 */
function makeSandbox(opts) {
  opts = opts || {};
  const calls = [];
  const reloads = { days: 0, links: 0 };
  const renders = { n: 0 };
  const st = {
    trip: { id: "T1" },
    error: "",
    photoPickerChecked: {},
    photoPickerDayId: "D1",
    placementMove: null,
  };
  let dirty = !!opts.dirty;
  const flashed = { n: 0 };

  function api(url, o) {
    calls.push({ url: url, body: o && o.body });
    if (opts.failOn && calls.length === opts.failOn) {
      return Promise.reject(new Error("boom"));
    }
    return Promise.resolve({});
  }
  function dayFormDirtyBlocks() {
    if (!dirty) return false;
    flashed.n++;
    return true;
  }
  function reloadDays() { reloads.days++; return Promise.resolve(); }
  function reloadPhotoLinks() { reloads.links++; return Promise.resolve(); }
  function renderAll() { renders.n++; }
  function dayChipText(d) { return "Day " + d.n; }

  const build = new Function(
    "PLACEMENT_BATCH_MAX", "st", "api", "dayFormDirtyBlocks",
    "reloadDays", "reloadPhotoLinks", "renderAll", "dayChipText",
    extract("addPhotosToDay") + "\n" +
    extract("unlinkDayPhoto") + "\n" +
    extract("openPlacementMove") + "\n" +
    extract("movePlacement") + "\n" +
    "return { addPhotosToDay: addPhotosToDay," +
    " unlinkDayPhoto: unlinkDayPhoto," +
    " openPlacementMove: openPlacementMove," +
    " movePlacement: movePlacement };"
  );
  return {
    fns: build(BATCH, st, api, dayFormDirtyBlocks, reloadDays,
               reloadPhotoLinks, renderAll, dayChipText),
    calls, reloads, renders, st, flashed,
    setDirty: function (v) { dirty = v; },
  };
}

const DAY = { id: "D1", n: 1 };
function ids(n, prefix) {
  const out = [];
  for (let i = 0; i < n; i++) out.push((prefix || "L") + i);
  return out;
}

async function main() {
  // ── 1. THE WHOLE SELECTION LANDS ─────────────────────────────────
  {
    const s = makeSandbox({});
    const r = await s.fns.addPhotosToDay(DAY, ids(120));
    check("120 photographs go out in 3 batches of at most " + BATCH,
      s.calls.length === 3 &&
      s.calls.every((c) => c.body.photo_link_ids.length <= BATCH),
      s.calls.map((c) => c.body.photo_link_ids.length).join("+"));
    check("a clean run reports every photograph added",
      r.added.length === 120 && r.unsent.length === 0 && !r.error,
      r.added.length + " added");
    check("a clean run leaves no error on screen", s.st.error === "",
      s.st.error);
    check("the days and the photo links are reloaded once",
      s.reloads.days === 1 && s.reloads.links === 1,
      JSON.stringify(s.reloads));
  }

  // ── 2. THE MIDDLE BATCH FAILS — THE CASE THE WORK ORDER NAMES ────
  {
    const s = makeSandbox({ failOn: 2 });
    const r = await s.fns.addPhotosToDay(DAY, ids(120));

    check("the batch after a failure is NEVER SENT",
      s.calls.length === 2,
      s.calls.length + " request(s); a third would have been sent blind");
    check("exactly " + BATCH + " photographs are reported as added",
      r.added.length === BATCH, r.added.length);
    check("the added photographs are the FIRST batch, in order",
      r.added[0] === "L0" && r.added[BATCH - 1] === "L" + (BATCH - 1),
      r.added[0] + ".." + r.added[r.added.length - 1]);
    check("the 70 that did not land are reported as still to do",
      r.unsent.length === 120 - BATCH, r.unsent.length);
    check("no photograph is both added and outstanding",
      !r.added.some((id) => r.unsent.indexOf(id) >= 0));
    check("the day is reloaded even though the run failed",
      s.reloads.days === 1 && s.reloads.links === 1,
      "the 50 that landed are on the day and must be on screen");

    const msg = s.st.error;
    check("the message states how many succeeded",
      /Added 50 of 120/.test(msg), msg);
    check("the message does not claim the whole add succeeded",
      !/^Added 120/.test(msg) && msg !== "", msg);
    check("the message does not report a bare failure",
      msg !== "boom", msg);
    check("the message says the rest are still selected",
      /still\s+selected/.test(msg), msg);

    // ── 2b. RETRY SENDS ONLY WHAT IS LEFT ──────────────────────────
    const before = s.calls.length;
    const again = await s.fns.addPhotosToDay(DAY, r.unsent);
    const retried = s.calls.slice(before);
    check("a retry sends only the outstanding photographs",
      retried.reduce((n, c) => n + c.body.photo_link_ids.length, 0)
        === 120 - BATCH,
      retried.map((c) => c.body.photo_link_ids.length).join("+"));
    check("a retry re-sends none of the ones already placed",
      !retried.some((c) => c.body.photo_link_ids.indexOf("L0") >= 0),
      "L0 landed in the first attempt");
    check("the retry completes the add", again.added.length === 120 - BATCH
      && !again.error, again.added.length);
    check("after the retry there is no error on screen", s.st.error === "",
      s.st.error);
  }

  // ── 3. THE FIRST BATCH FAILS — NOTHING LANDED ────────────────────
  {
    const s = makeSandbox({ failOn: 1 });
    const r = await s.fns.addPhotosToDay(DAY, ids(120));
    check("a total failure sends one request and stops",
      s.calls.length === 1, s.calls.length);
    check("a total failure reports nothing added", r.added.length === 0);
    check("a total failure shows the plain error, not a partial tally",
      s.st.error === "boom" && !/Added/.test(s.st.error), s.st.error);
    check("a total failure still reconciles the screen with the database",
      s.reloads.days === 1, s.reloads.days);
  }

  // ── 4. A SELECTION SMALLER THAN ONE BATCH ────────────────────────
  {
    const s = makeSandbox({});
    const r = await s.fns.addPhotosToDay(DAY, ids(3));
    check("a small selection is one request", s.calls.length === 1);
    check("a small selection reports its three", r.added.length === 3);
  }
  {
    const s = makeSandbox({});
    const r = await s.fns.addPhotosToDay(DAY, []);
    check("an empty selection sends nothing", s.calls.length === 0);
    check("an empty selection still answers the caller's shape",
      r && Array.isArray(r.added) && r.added.length === 0);
  }

  // ── 5. THE DIRTY DAY FORM BLOCKS EVERY PHOTO CONTROL ─────────────
  //
  // Blocked means: no request, no drawer, and the Save/Cancel
  // affordance flashed so the operator is told why.
  {
    const s = makeSandbox({ dirty: true });
    await s.fns.addPhotosToDay(DAY, ids(3));
    check("Add to this day is blocked while the day form is dirty",
      s.calls.length === 0 && s.flashed.n === 1,
      s.calls.length + " request(s)");
  }
  {
    const s = makeSandbox({ dirty: true });
    await s.fns.unlinkDayPhoto(DAY, "L1");
    check("Remove from this day is blocked while the day form is dirty",
      s.calls.length === 0 && s.flashed.n === 1,
      s.calls.length + " request(s)");
  }
  {
    const s = makeSandbox({ dirty: true });
    s.fns.openPlacementMove(DAY, { id: "L1" });
    check("Move… opens no drawer while the day form is dirty",
      s.st.placementMove === null && s.renders.n === 0,
      JSON.stringify(s.st.placementMove));
  }
  {
    const s = makeSandbox({ dirty: true });
    await s.fns.movePlacement("D1", "L1", "D2");
    check("the Move commit is blocked while the day form is dirty",
      s.calls.length === 0, s.calls.length + " request(s)");
  }

  // ── 6. NON-VACUITY: THE SAME CONTROLS WORK WHEN IT IS CLEAN ──────
  //
  // Four checks that pass because nothing happened are four checks a
  // permanently broken control would also pass.
  {
    const s = makeSandbox({});
    await s.fns.unlinkDayPhoto(DAY, "L1");
    check("Remove from this day works when the form is clean",
      s.calls.length === 1 && /photos\/unlink/.test(s.calls[0].url),
      s.calls.length ? s.calls[0].url : "no request");
  }
  {
    const s = makeSandbox({});
    s.fns.openPlacementMove(DAY, { id: "L1" });
    check("Move… opens its drawer when the form is clean",
      s.st.placementMove && s.st.placementMove.linkId === "L1"
        && s.st.placementMove.fromDayId === "D1",
      JSON.stringify(s.st.placementMove));
  }
  {
    const s = makeSandbox({});
    await s.fns.movePlacement("D1", "L1", "D2");
    check("the Move commit names both ends when the form is clean",
      s.calls.length === 1 &&
      s.calls[0].body.from_day_id === "D1" &&
      s.calls[0].body.to_day_id === "D2" &&
      s.calls[0].body.photo_link_id === "L1",
      JSON.stringify(s.calls[0] && s.calls[0].body));
    check("a completed move closes its drawer",
      s.st.placementMove === null);
  }

  const bad = R.filter((r) => !r.ok);
  R.forEach((r) => {
    console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
      (r.detail ? "   [" + r.detail + "]" : ""));
  });
  console.log("");
  console.log((R.length - bad.length) + "/" + R.length + " checks passed");
  process.exit(bad.length ? 1 : 0);
}

main().catch((e) => {
  console.error("harness error: " + (e && e.stack || e));
  process.exit(1);
});
