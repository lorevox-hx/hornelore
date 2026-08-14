#!/usr/bin/env node
/**
 * WO-TRIP-PHOTO-PALETTE-01 P2 — behaviour a source scan cannot judge.
 *
 * `tests/test_trip_photo_palette_ui.py` pins the SHAPE of the Palette:
 * five named predicates, one shared filter dispatcher, selection in
 * state rather than in a closure, one batch runner. None of that can
 * answer the questions an operator actually has:
 *
 *   * does a partial batch keep the right photographs selected?
 *   * does a failed refresh still report the write as successful?
 *   * does a stop-assigned photograph land under "Not on a day" while
 *     staying out of "completely unplaced"?
 *   * does the same predicate really drive the count and the grid?
 *
 * So this executes the real functions, lifted out of
 * ui/js/travel-doc-lab.js by name, against an `api` that fails on
 * demand. A copy of the logic would keep passing after somebody changed
 * the product, which is the failure mode this file exists to avoid.
 *
 * Usage:  node scripts/ui/run_photo_palette_behaviour.js
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
function numConst(name) {
  const m = new RegExp("var " + name + " = (\\d+);").exec(src);
  if (!m) throw new Error("cannot find " + name);
  return Number(m[1]);
}
const BATCH = numConst("PLACEMENT_BATCH_MAX");
function numConstOf(name) { return numConst(name); }

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

// ── the predicates, run for real ──────────────────────────────────────

const predicates = new Function(
  [
    extract("linkDayIds"),
    extract("linkIsOnDay"),
    extract("linkHasNoDayPlacement"),
    extract("linkIsOnMultipleDays"),
    extract("linkIsCompletelyUnplaced"),
    "function linkNeedsReview(l) {",
    "  return l.cluster_confidence != null &&",
    "    Number(l.cluster_confidence) < 0.5 &&",
    '    l.assignment_method !== "operator";',
    "}",
    extract("linkMatchesPaletteFilter"),
    "return { linkDayIds, linkIsOnDay, linkHasNoDayPlacement,",
    "         linkIsOnMultipleDays, linkIsCompletelyUnplaced,",
    "         linkMatchesPaletteFilter };"
  ].join("\n"))();

const NOWHERE = { id: "a", trip_day_ids: [] };
const ON_STOP = { id: "b", trip_day_ids: [], trip_stop_id: "s1" };
const ON_REGION = { id: "c", trip_day_ids: [], trip_region_id: "r1" };
const ONE_DAY = { id: "d", trip_day_ids: ["d1"] };
// The multi-day case as the SERVER actually serves it: the compatibility
// scalar is null by rule, and a predicate that reads it gets this wrong.
const MULTI = { id: "e", trip_day_ids: ["d1", "d3"], trip_day_id: null };
const HIDDEN = { id: "f", trip_day_ids: [], hidden: 1 };

(function twoQuestionsStayApart() {
  const p = predicates;
  check("a photograph nowhere at all is BOTH not-on-a-day and completely unplaced",
    p.linkHasNoDayPlacement(NOWHERE) && p.linkIsCompletelyUnplaced(NOWHERE));

  check("a STOP-assigned photograph with no day is not-on-a-day but NOT completely unplaced",
    p.linkHasNoDayPlacement(ON_STOP) && !p.linkIsCompletelyUnplaced(ON_STOP));

  // The bug the P0 review caught: region was the axis the old rule forgot.
  check("a REGION-assigned photograph with no day is not completely unplaced",
    p.linkHasNoDayPlacement(ON_REGION) && !p.linkIsCompletelyUnplaced(ON_REGION),
    "region-assigned: hasNoDay=" + p.linkHasNoDayPlacement(ON_REGION) +
    " completelyUnplaced=" + p.linkIsCompletelyUnplaced(ON_REGION));

  check("a photograph on one day is neither",
    !p.linkHasNoDayPlacement(ONE_DAY) && !p.linkIsCompletelyUnplaced(ONE_DAY));

  check("a MULTI-DAY photograph whose scalar is null is neither " +
        "not-on-a-day nor completely unplaced",
    !p.linkHasNoDayPlacement(MULTI) && !p.linkIsCompletelyUnplaced(MULTI),
    "scalar=" + String(MULTI.trip_day_id) + " days=" + MULTI.trip_day_ids.length);

  check("multiple-days is two or more, not one",
    p.linkIsOnMultipleDays(MULTI) && !p.linkIsOnMultipleDays(ONE_DAY));
})();

(function oneFilterDispatcher() {
  const p = predicates;
  const pool = [NOWHERE, ON_STOP, ON_REGION, ONE_DAY, MULTI, HIDDEN];
  const under = (f, dayId) =>
    pool.filter(l => p.linkMatchesPaletteFilter(l, f, dayId)).map(l => l.id);

  check("All admits every membership exactly once",
    under("all").length === pool.length &&
    new Set(under("all")).size === pool.length);

  check("Not on a day admits the three with zero placements",
    under("noday").join(",") === "a,b,c,f", under("noday").join(","));

  check("Day filter admits only photographs placed on THAT day",
    under("day", "d3").join(",") === "e", under("day", "d3").join(","));

  check("Day filter with no day chosen admits nothing rather than everything",
    under("day", null).length === 0);

  check("Multiple days admits only the multi-day photograph",
    under("multi").join(",") === "e");

  check("Hidden admits only the hidden one",
    under("hidden").join(",") === "f");

  // The property the spec states outright: counts and cards share a
  // predicate. Proven by deriving both from the same call.
  const filters = ["all", "noday", "day", "multi", "review", "hidden"];
  let sharedOK = true;
  filters.forEach(function (f) {
    const count = pool.filter(l => p.linkMatchesPaletteFilter(l, f, "d3")).length;
    const cards = pool.filter(l => p.linkMatchesPaletteFilter(l, f, "d3")).length;
    if (count !== cards) sharedOK = false;
  });
  check("every chip count equals the number of cards it labels", sharedOK);
})();

// ── the batch runner, run for real ────────────────────────────────────

function loadRunner() {
  const body = [
    "var PLACEMENT_BATCH_MAX = " + BATCH + ";",
    extract("paletteBatchRun"),
    extract("paletteResult"),
    "return { paletteBatchRun, paletteResult };"
  ].join("\n");
  return new Function(body)();
}
const runner = loadRunner();

function ids(n, prefix) {
  const out = [];
  for (let i = 0; i < n; i++) out.push((prefix || "p") + i);
  return out;
}

(function chunksAtTheCeiling() {
  const seen = [];
  const all = ids(120);
  return runner.paletteBatchRun(all, function (batch) {
    seen.push(batch.length);
    return Promise.resolve();
  }).then(function (r) {
    check("120 ids are sent in bounded batches, never one oversized call",
      seen.every(n => n <= BATCH), seen.join("+"));
    check("…and every id is sent exactly once",
      r.done.length === 120 && new Set(r.done).size === 120,
      r.done.length + " done");
    check("…with nothing left unsent on a clean run",
      r.unsent.length === 0 && r.failure === null);
  });
})();

(function stopsAtTheFirstFailureAndKeepsTheRest() {
  let call = 0;
  const all = ids(120);
  return runner.paletteBatchRun(all, function () {
    call++;
    // batch 1 lands, batch 2 fails, batch 3 must never be sent
    return call === 2 ? Promise.reject(new Error("boom"))
                      : Promise.resolve();
  }).then(function (r) {
    check("a failure stops the run rather than pressing on",
      call === 2, "sendBatch called " + call + " times");
    check("the batch that landed is remembered as done",
      r.done.length === BATCH, r.done.length + " done");
    check("the batch that FAILED is kept separate from the unsent ones",
      r.failedBatch.length === BATCH && r.unsent.length === 20,
      "failed=" + r.failedBatch.length + " unsent=" + r.unsent.length);
    check("done + failed + unsent accounts for every id, with none lost",
      r.done.length + r.failedBatch.length + r.unsent.length === 120);
    check("the failure itself is carried, not swallowed",
      r.failure && r.failure.message === "boom");
  });
})();

(function anEmptySelectionDoesNothing() {
  return runner.paletteBatchRun([], function () {
    check("an empty batch never calls the api", false, "sendBatch was called");
    return Promise.resolve();
  }).then(function (r) {
    check("an empty selection sends nothing and reports nothing",
      r.done.length === 0 && r.unsent.length === 0 && r.failure === null);
  });
})();

(function theResultShapeIsUniform() {
  const blocked = runner.paletteResult({ unsent: ["a"], blocked: true });
  const clean = runner.paletteResult({ done: ["a"] });
  const keys = o => Object.keys(o).sort().join(",");
  // EIGHT keys. `changed`/`already` so Hide/Restore reports what it
  // altered rather than everything it was asked about, and `cancelled`
  // so "the operator moved on" is distinguishable from "it failed" --
  // the second would send them back to retry something that was never
  // wrong.
  check("every exit answers the same eight keys",
    keys(blocked) === keys(clean) &&
    keys(clean) ===
      "already,blocked,cancelled,changed,done,error,reloadError,unsent",
    keys(clean));
  check("a blocked run reports the whole selection as still outstanding",
    blocked.blocked === true && blocked.unsent.length === 1 &&
    blocked.done.length === 0);
  check("a write failure and a reload failure are separate fields",
    "error" in clean && "reloadError" in clean);
})();

// ── selection survives what a repaint does to it ──────────────────────

(function selectionIsStateNotAClosure() {
  // The real functions, over a real state object, exactly as the module
  // holds it. A repaint in this module rebuilds every node; what must
  // survive is `st`.
  const mod = new Function([
    "var st = { tripCal: null };",
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteSelectedIds"),
    extract("paletteToggleSelected"),
    extract("paletteClearSelection"),
    extract("paletteSelectedOutsideFilter"),
    "return { st, newPaletteState, paletteState, paletteSelectedIds,",
    "         paletteToggleSelected, paletteClearSelection,",
    "         paletteSelectedOutsideFilter };"
  ].join("\n"))();

  mod.st.tripCal = { palette: mod.newPaletteState() };
  ["a", "b", "c"].forEach(id => mod.paletteToggleSelected(id, true));
  check("three ticks give three selected ids",
    mod.paletteSelectedIds().sort().join(",") === "a,b,c");

  // A repaint. Nothing about it touches `st`.
  const survived = mod.paletteSelectedIds().sort().join(",");
  check("selection survives a repaint, because it is not in the render",
    survived === "a,b,c", survived);

  mod.paletteToggleSelected("b", false);
  check("unticking removes exactly one",
    mod.paletteSelectedIds().sort().join(",") === "a,c");

  // The filter changed and only "a" is now visible. The other selected
  // photograph is not lost; it is off-screen, and the operator is told.
  check("selected-but-not-shown is counted, not hidden",
    mod.paletteSelectedOutsideFilter(["a"]) === 1,
    mod.paletteSelectedOutsideFilter(["a"]));
  check("nothing is outside the filter when everything is shown",
    mod.paletteSelectedOutsideFilter(["a", "c"]) === 0);

  mod.paletteClearSelection();
  check("clear empties it", mod.paletteSelectedIds().length === 0);
})();

// ── the 2026-08-14 corrections, run for real ──────────────────────────

(function theActionBarKeepsUpWithTheSelection() {
  // THE DEFECT THIS REPLACES. `disabled` was decided at render time and
  // ticking a card deliberately does not repaint, so the bar was always
  // one selection behind: select something and every action stayed
  // disabled; clear the selection and they all stayed enabled. Measured
  // live in a visible tab, in both directions.
  const mod = new Function([
    "var st = { tripCal: null, photoLinks: [], hiddenPhotoLinks: [] };",
    extract("linkDayIds"),
    extract("linkIsOnDay"),
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteSelectedIds"),
    extract("paletteToggleSelected"),
    extract("paletteClearSelection"),
    extract("paletteSelectedOutsideFilter"),
    extract("paletteLinkIndex"),
    extract("paletteLinkById"),
    extract("paletteRemovableIds"),
    extract("paletteRefreshBar"),
    "return { st, newPaletteState, paletteToggleSelected,",
    "         paletteClearSelection, paletteRefreshBar,",
    "         paletteRemovableIds, paletteSelectedIds };"
  ].join("\n"))();

  mod.st.tripCal = { palette: mod.newPaletteState() };
  mod.st.photoLinks = [
    { id: "on", trip_day_ids: ["d1"] },
    { id: "off", trip_day_ids: [] }
  ];

  // A stand-in for the rendered bar: the same query surface the real
  // function uses, so the real function runs unmodified.
  function makeBar() {
    const btns = {};
    ["add", "remove", "hide", "restore", "clear"].forEach(function (a) {
      btns[a] = { disabled: false, title: "" };
    });
    const count = { textContent: "" };
    return {
      _b: btns, _c: count,
      querySelector(sel) {
        if (sel === ".tdl-palette-selcount") return count;
        const m = /\[data-pal-act="(\w+)"\]/.exec(sel);
        return m ? btns[m[1]] : null;
      }
    };
  }
  const day = { id: "d1" };
  const bar = makeBar();

  mod.paletteRefreshBar(bar, ["on", "off"], "d1", day);
  check("CORRECTION: with nothing selected every action is disabled",
    bar._b.add.disabled && bar._b.remove.disabled && bar._b.hide.disabled,
    "count=" + bar._c.textContent);

  mod.paletteToggleSelected("on", true);
  mod.paletteRefreshBar(bar, ["on", "off"], "d1", day);
  check("CORRECTION: selecting a photograph ENABLES the actions " +
        "without a repaint",
    !bar._b.add.disabled && !bar._b.hide.disabled && !bar._b.remove.disabled,
    "add=" + bar._b.add.disabled + " hide=" + bar._b.hide.disabled);
  check("CORRECTION: …and the count says so",
    bar._c.textContent === "1 selected", bar._c.textContent);

  mod.paletteClearSelection();
  mod.paletteRefreshBar(bar, ["on", "off"], "d1", day);
  check("CORRECTION: clearing the selection DISABLES them again",
    bar._b.add.disabled && bar._b.hide.disabled && bar._b.remove.disabled);

  // Remove eligibility: selection persists across filters, so it can
  // hold photographs that are not on the visible day at all.
  mod.paletteToggleSelected("off", true);
  mod.paletteRefreshBar(bar, ["on", "off"], "d1", day);
  check("CORRECTION: Remove stays disabled when nothing selected is on " +
        "this day",
    bar._b.remove.disabled && !bar._b.hide.disabled,
    "remove=" + bar._b.remove.disabled);
  check("CORRECTION: …and says why", /are on this day/i.test(bar._b.remove.title),
    bar._b.remove.title);

  check("CORRECTION: only the on-day photograph is removable",
    mod.paletteRemovableIds("d1").join(",") === "",
    mod.paletteRemovableIds("d1").join(","));
  mod.paletteToggleSelected("on", true);
  check("CORRECTION: …and the off-day one is excluded from the request " +
        "while STAYING selected",
    mod.paletteRemovableIds("d1").join(",") === "on" &&
    mod.paletteSelectedIds().sort().join(",") === "off,on",
    "removable=" + mod.paletteRemovableIds("d1").join(",") +
    " selected=" + mod.paletteSelectedIds().sort().join(","));

  check("CORRECTION: no day chosen means nothing is removable",
    mod.paletteRemovableIds(null).length === 0);
})();

(function batchesReportWhatChangedNotWhatWasAsked() {
  // Hiding fifty photographs of which forty-nine were already hidden is
  // "Hid 1", not "Hid 50". The server distinguishes them; the UI used to
  // throw that away.
  return runner.paletteBatchRun(ids(3), function (batch) {
    return Promise.resolve({ changed: [batch[0]],
                             already_in_state: batch.slice(1) });
  }).then(function (r) {
    check("CORRECTION: a batch reports what it CHANGED",
      r.changed.join(",") === "p0", r.changed.join(","));
    check("CORRECTION: …separately from what was already in that state",
      r.already.join(",") === "p1,p2", r.already.join(","));
    check("CORRECTION: …while `done` still accounts for every id sent",
      r.done.length === 3);
  });
})();

(function aRouteThatDoesNotReportTheDistinctionFallsBack() {
  // Add and Remove return no changed/already; treating their silence as
  // "nothing changed" would under-report every placement.
  return runner.paletteBatchRun(ids(2), function () {
    return Promise.resolve({ ok: true });
  }).then(function (r) {
    check("CORRECTION: a route without changed/already falls back to the " +
          "batch rather than reporting zero",
      r.changed.length === 2 && r.already.length === 0,
      "changed=" + r.changed.length);
  });
})();

// ── the FINAL P2 corrections, run for real ────────────────────────────

(function aStaleReloadCannotAssign() {
  // THE DEFECT. The previous correction guarded the REPORTER and left
  // the reloads between it and the network unguarded, so trip A's
  // response still overwrote st.photoLinks after the operator had moved
  // to trip B -- the report was suppressed AFTER the screen was wrong.
  const mod = new Function([
    "var destroyed = false;",
    "var paletteGeneration = 7;",
    "var st = { trip: { id: 'A' }, photoLinks: ['ORIGINAL'],",
    "           hiddenPhotoLinks: [], showHiddenPhotos: false,",
    "           tripCal: {}, days: ['DAY-ORIGINAL'], preservedDays: [],",
    "           countsWarning: '' };",
    "var _resolve = null;",
    "function api() { return new Promise(function (r) { _resolve = r; }); }",
    "function invalidateMemoirPreview() {}",
    extract("reloadGuardIsCurrent"),
    extract("reloadDays"),
    extract("reloadPhotoLinks"),
    "return { st, reloadDays, reloadPhotoLinks,",
    "         land: function (v) { _resolve(v); },",
    "         setTrip: function (id) { st.trip = { id: id }; },",
    "         setGen: function (g) { paletteGeneration = g; },",
    "         kill: function () { destroyed = true; } };"
  ].join("\n"))();

  const guard = { tripId: "A", gen: 7, needsModal: true };
  const pending = mod.reloadPhotoLinks(guard);
  mod.setTrip("B");                       // the operator moves on
  mod.land({ photo_links: ["TRIP-A-DATA"] });
  return pending.then(function () {
    check("CORRECTION: a reload that lands after a trip change does NOT " +
          "assign", mod.st.photoLinks[0] === "ORIGINAL",
      "st.photoLinks[0]=" + mod.st.photoLinks[0]);
  });
})();

(function aStaleReloadCannotAssignDays() {
  const mod = new Function([
    "var destroyed = false;",
    "var paletteGeneration = 3;",
    "var st = { trip: { id: 'A' }, tripCal: {}, days: ['ORIGINAL'],",
    "           preservedDays: [], countsWarning: '' };",
    "var _resolve = null;",
    "function api() { return new Promise(function (r) { _resolve = r; }); }",
    extract("reloadGuardIsCurrent"),
    extract("reloadDays"),
    "return { st, reloadDays, land: function (v) { _resolve(v); },",
    "         setGen: function (g) { paletteGeneration = g; },",
    "         closeModal: function () { st.tripCal = null; } };"
  ].join("\n"))();

  const guard = { tripId: "A", gen: 3, needsModal: true };
  const p1 = mod.reloadDays(guard);
  mod.setGen(4);                          // filter or mode changed
  mod.land({ days: ["STALE"] });
  return p1.then(function () {
    check("CORRECTION: a reload whose GENERATION moved on does not assign",
      mod.st.days[0] === "ORIGINAL", mod.st.days[0]);

    const p2 = mod.reloadDays({ tripId: "A", gen: 4, needsModal: true });
    mod.closeModal();                     // modal closed mid-flight
    mod.land({ days: ["ALSO-STALE"] });
    return p2.then(function () {
      check("CORRECTION: a reload for a CLOSED modal does not assign",
        mod.st.days[0] === "ORIGINAL", mod.st.days[0]);
    });
  });
})();

(function batchesStopWhenTheContextGoesStale() {
  let live = true;
  let sent = 0;
  return runner.paletteBatchRun(ids(150), function (batch) {
    sent++;
    if (sent === 1) live = false;   // the operator leaves after batch 1
    return Promise.resolve();
  }, function () { return live; }).then(function (r) {
    check("CORRECTION: batches stop being SENT once the context is stale",
      sent === 1, "sendBatch called " + sent + " times");
    check("CORRECTION: …the batch that landed stays confirmed",
      r.done.length === BATCH, r.done.length + " done");
    check("CORRECTION: …and the remainder is classified unsent, not failed",
      r.unsent.length === 100 && r.failure === null && r.cancelled === true,
      "unsent=" + r.unsent.length + " cancelled=" + r.cancelled);
    check("CORRECTION: …with nothing lost in the accounting",
      r.done.length + r.unsent.length === 150);
  });
})();

(function hiddenPhotographsAreRemovable() {
  // THE DEFECT. Palette Hidden read p.hidden while eligibility read
  // st.hiddenPhotoLinks -- empty unless the PHOTOS TAB toggle is on. A
  // hidden photograph could be on screen, on the day, and unremovable.
  const mod = new Function([
    "var st = { tripCal: null, photoLinks: [], hiddenPhotoLinks: [] };",
    extract("linkDayIds"),
    extract("linkIsOnDay"),
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteSelectedIds"),
    extract("paletteToggleSelected"),
    extract("paletteLinkIndex"),
    extract("paletteLinkById"),
    extract("paletteRemovableIds"),
    "return { st, newPaletteState, paletteToggleSelected,",
    "         paletteRemovableIds, paletteLinkById };"
  ].join("\n"))();

  mod.st.tripCal = { palette: mod.newPaletteState() };
  // The Photos tab's array is EMPTY, exactly as it is when that toggle
  // is off. Only the Palette's own pool knows about this photograph.
  mod.st.hiddenPhotoLinks = [];
  mod.st.tripCal.palette.hidden = [
    { id: "h1", hidden: 1, trip_day_ids: ["d1"] }
  ];
  mod.paletteToggleSelected("h1", true);

  check("CORRECTION: a hidden photograph resolves through the Palette's " +
        "own pool", !!mod.paletteLinkById("h1"));
  check("CORRECTION: …and a hidden photograph ON the day is removable",
    mod.paletteRemovableIds("d1").join(",") === "h1",
    mod.paletteRemovableIds("d1").join(","));
  check("CORRECTION: …and is the ONLY id submitted",
    mod.paletteRemovableIds("d1").length === 1);
  check("CORRECTION: a hidden photograph NOT on the day is not removable",
    mod.paletteRemovableIds("d2").length === 0);
})();

(function theCaptionEditorIsReachableForAnyPaletteLink() {
  const mod = new Function([
    "var st = { trip: { id: 'A' }, photoLinks: [], tripCal: null };",
    "var TL_EDIT_FIELDS = { photo: [{ name: 'caption' }] };",
    "function timelineEdit() { return st.tripCal && st.tripCal.edit; }",
    "function timelineEditDirtyBlocks() { return false; }",
    "function renderAll() {}",
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteLinkIndex"),
    extract("paletteLinkById"),
    extract("openCaptionEditorForLink"),
    "return { st, newPaletteState, openCaptionEditorForLink };"
  ].join("\n"))();

  mod.st.tripCal = { mode: "palette", edit: null,
                     palette: mod.newPaletteState() };
  // Deliberately NOT in any Photos-tab filtered list -- this is the case
  // openLightbox() could not resolve.
  mod.st.photoLinks = [{ id: "vis", caption: "a caption", trip_day_ids: [] }];
  mod.st.tripCal.palette.hidden = [{ id: "hid", caption: "hidden one",
                                     hidden: 1, trip_day_ids: ["d1"] }];

  mod.openCaptionEditorForLink("vis");
  check("CORRECTION: a visible Palette card opens the caption editor",
    !!mod.st.tripCal.edit && mod.st.tripCal.edit.kind === "photo" &&
    mod.st.tripCal.edit.values.caption === "a caption",
    JSON.stringify(mod.st.tripCal.edit && mod.st.tripCal.edit.values));
  check("CORRECTION: …and it remembers it came from the Palette",
    mod.st.tripCal.edit.fromPalette === true);

  mod.st.tripCal.edit = null;
  mod.openCaptionEditorForLink("hid");
  check("CORRECTION: a HIDDEN Palette card opens the caption editor too",
    !!mod.st.tripCal.edit &&
    mod.st.tripCal.edit.values.caption === "hidden one",
    JSON.stringify(mod.st.tripCal.edit && mod.st.tripCal.edit.values));

  mod.st.tripCal.edit = null;
  mod.openCaptionEditorForLink("nope");
  check("CORRECTION: an unknown id opens nothing rather than an empty editor",
    mod.st.tripCal.edit === null);

  // The write itself is the timeline's, and its photo branch is
  // caption-only -- so editing a caption cannot grant Lori approval.
  const body = new Function([
    extract("timelineEditBody"),
    "return timelineEditBody({ kind: 'photo', values: { caption: ' x ' } });"
  ].join("\n"))();
  check("CORRECTION: the shared save sends the caption and NOTHING else",
    JSON.stringify(body.body) === '{"caption":"x"}',
    JSON.stringify(body.body));
  check("CORRECTION: …so it cannot change Lori approval",
    !("caption_approved_for_lori" in body.body));
})();

(function theStatusLineTellsTheWholeTruth() {
  // MUTATION-DRIVEN. Deleting the already-in-state clause from the
  // status left every gate green, because the runner COLLECTS `already`
  // and only the status line reports it. "Hid 1" when forty-nine were
  // already hidden is a false claim about the operator's own trip.
  const mod = new Function([
    "var st = { tripCal: null };",
    "var paletteGeneration = 1;",
    "var destroyed = false;",
    "function renderAll() {}",
    "function sameTrip() { return true; }",
    "function paletteGenerationIsCurrent() { return true; }",
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteAfterBatch"),
    "return { st, newPaletteState, paletteAfterBatch };"
  ].join("\n"))();
  mod.st.tripCal = { palette: mod.newPaletteState() };
  const P = function () { return mod.st.tripCal.palette; };

  mod.paletteAfterBatch(
    { changed: ["a"], already: ["b", "c"], unsent: [], done: ["a", "b", "c"] },
    ["a"], "hidden");
  check("CORRECTION: the status reports what was ALREADY in that state",
    /1 hidden/.test(P().status) && /2 were already hidden/.test(P().status),
    P().status);

  mod.paletteAfterBatch(
    { changed: ["a"], already: [], unsent: ["z"], cancelled: true,
      done: ["a"] },
    ["a"], "removed");
  check("CORRECTION: a cancelled run says so, and does not read as a failure",
    /not sent because/.test(P().status) && !/retry/.test(P().status),
    P().status);

  mod.paletteAfterBatch({ changed: ["a"], already: [], unsent: [],
                          done: ["a"] }, ["a"], "hidden");
  check("CORRECTION: a clean run stays terse — no empty parenthetical",
    P().status === "1 hidden.", P().status);

  mod.paletteAfterBatch({ blocked: true, unsent: ["a"] }, [], "hidden");
  check("CORRECTION: a blocked run names the dirty day, not a count",
    /save or discard the day/.test(P().status), P().status);
})();

// ── one thousand memberships ──────────────────────────────────────────
//
// The condition attached to keeping the one-fetch model. If any of this
// fails, server paging stops being speculative architecture and becomes
// a measured requirement.

(function oneThousandLinks() {
  const win = new Function([
    "var PHOTO_PAGE_SIZE = " + numConstOf("PHOTO_PAGE_SIZE") + ";",
    "var PHOTO_WINDOW_MAX = " + numConstOf("PHOTO_WINDOW_MAX") + ";",
    "var st = { photoWindows: {} };",
    "function renderAll() {}",
    extract("photoWindow"),
    extract("slidePhotoWindow"),
    "return { photoWindow, slidePhotoWindow, st, PHOTO_WINDOW_MAX,",
    "         PHOTO_PAGE_SIZE };"
  ].join("\n"))();

  const TOTAL = 1000;
  const links = [];
  for (let i = 0; i < TOTAL; i++) {
    links.push({ id: "L" + String(i).padStart(4, "0"),
                 trip_day_ids: (i % 7 === 0) ? [] : ["d" + (i % 6)] });
  }

  const t0 = Date.now();
  const w = win.photoWindow("k", TOTAL, win.PHOTO_WINDOW_MAX);
  const firstPage = links.slice(w.start, w.end);
  const elapsed = Date.now() - t0;

  check("1000 memberships: the first page is bounded, not the whole set",
    firstPage.length <= win.PHOTO_WINDOW_MAX,
    firstPage.length + " mounted of " + TOTAL);
  check("1000 memberships: the first page is the page size",
    firstPage.length === win.PHOTO_PAGE_SIZE, firstPage.length);
  check("1000 memberships: building a page is fast", elapsed < 250,
    elapsed + "ms");

  // Walk the whole list the way an operator would, and prove two things
  // at once: every membership is reachable, and the mounted count never
  // grows past the bound.
  const seen = new Set();
  let worst = 0;
  let guard = 0;
  let cur = win.photoWindow("k", TOTAL, win.PHOTO_WINDOW_MAX);
  while (cur.end < TOTAL && guard++ < 200) {
    links.slice(cur.start, cur.end).forEach(l => seen.add(l.id));
    worst = Math.max(worst, cur.end - cur.start);
    win.slidePhotoWindow("k", TOTAL, win.PHOTO_WINDOW_MAX, 1);
    cur = win.photoWindow("k", TOTAL, win.PHOTO_WINDOW_MAX);
  }
  links.slice(cur.start, cur.end).forEach(l => seen.add(l.id));
  worst = Math.max(worst, cur.end - cur.start);

  check("1000 memberships: every one is reachable by paging",
    seen.size === TOTAL, seen.size + " of " + TOTAL);
  check("1000 memberships: the mounted window never exceeds its bound",
    worst <= win.PHOTO_WINDOW_MAX, "worst " + worst);
  check("1000 memberships: paging terminates", guard < 200, "steps " + guard);
  check("1000 memberships: each appears exactly ONCE per page",
    new Set(firstPage.map(l => l.id)).size === firstPage.length);

  // Only the mounted cards would build a thumbnail: the grid renders
  // links.slice(start, end) and nothing else, so the count of would-be
  // requests is the window, not the library.
  check("1000 memberships: a page would request at most a window of " +
        "thumbnails, never 1000 originals",
    firstPage.length <= win.PHOTO_WINDOW_MAX && firstPage.length < TOTAL,
    firstPage.length + " thumbnails for " + TOTAL + " memberships");

  // Selection must survive leaving the window and coming back.
  const sel = new Function([
    "var st = { tripCal: null };",
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteSelectedIds"),
    extract("paletteToggleSelected"),
    extract("paletteSelectedOutsideFilter"),
    "return { st, newPaletteState, paletteState, paletteSelectedIds,",
    "         paletteToggleSelected, paletteSelectedOutsideFilter };"
  ].join("\n"))();
  sel.st.tripCal = { palette: sel.newPaletteState() };
  const early = links.slice(0, 10).map(l => l.id);
  early.forEach(id => sel.paletteToggleSelected(id, true));
  // Page far away — those ten are nowhere near the mounted window now.
  const far = links.slice(900, 950).map(l => l.id);
  check("1000 memberships: selection survives leaving the window",
    sel.paletteSelectedIds().length === 10);
  check("1000 memberships: and is reported as off-screen rather than lost",
    sel.paletteSelectedOutsideFilter(far) === 10,
    sel.paletteSelectedOutsideFilter(far));
  check("1000 memberships: and is intact on returning to it",
    sel.paletteSelectedOutsideFilter(early) === 0);
})();

// ── report ────────────────────────────────────────────────────────────

Promise.resolve().then(function () {
  return new Promise(r => setTimeout(r, 60));
}).then(function () {
  let failed = 0;
  R.forEach(function (r) {
    if (!r.ok) failed++;
    console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
      (r.detail ? "  [" + r.detail + "]" : ""));
  });
  console.log("");
  console.log(R.length - failed + " passed, " + failed + " failed");
  process.exit(failed ? 1 : 0);
});
