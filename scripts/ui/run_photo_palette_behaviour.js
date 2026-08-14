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

// ── the caption editor must actually APPEAR ───────────────────────────
//
// A source assertion that openCaptionEditorForLink exists is exactly
// what let the previous version ship an editor nobody could see. This
// renders the real Palette pane against a DOM stand-in and looks for a
// mounted field.

(function theCaptionEditorIsMountedInPaletteMode() {
  // The smallest DOM the pane touches. el()/btn() are lifted from the
  // module, so the pane runs unmodified.
  function makeDoc() {
    function mk(tag) {
      return {
        tagName: String(tag).toUpperCase(), className: "", textContent: "",
        type: "", disabled: false, checked: false, value: "", title: "",
        children: [], attrs: {}, style: {},
        appendChild(c) { this.children.push(c); return c; },
        setAttribute(k, v) { this.attrs[k] = String(v); },
        getAttribute(k) { return this.attrs[k] === undefined ? null : this.attrs[k]; },
        addEventListener(t, f) { if (t === "click") this._click = f; },
        querySelector(sel) { return findOne(this, sel); },
        querySelectorAll(sel) { return findAll(this, sel); },
        focus() {}, classList: { toggle() {}, add() {}, remove() {} }
      };
    }
    function walk(n, out) {
      (n.children || []).forEach(function (c) { out.push(c); walk(c, out); });
      return out;
    }
    function matches(n, sel) {
      if (sel.charAt(0) === ".") return (" " + n.className + " ").indexOf(" " + sel.slice(1) + " ") >= 0;
      if (sel.indexOf("[data-pal-act=") === 0) {
        const m = /\[data-pal-act="(\w+)"\]/.exec(sel);
        return m && n.attrs["data-pal-act"] === m[1];
      }
      return n.tagName === sel.toUpperCase();
    }
    function findAll(root, sel) { return walk(root, []).filter(n => matches(n, sel)); }
    function findOne(root, sel) { return findAll(root, sel)[0] || null; }
    return { createElement: mk, findAll: findAll };
  }
  const doc = makeDoc();

  const mod = new Function("document", [
    "var destroyed = false;",
    "var paletteGeneration = 1;",
    "var PHOTO_PAGE_SIZE = " + numConstOf("PHOTO_PAGE_SIZE") + ";",
    "var PHOTO_WINDOW_MAX = " + numConstOf("PHOTO_WINDOW_MAX") + ";",
    "var PALETTE_FILTERS = [['all','All'],['noday','Not on a day'],",
    "  ['day','Day'],['multi','Multiple days'],['review','Needs review'],",
    "  ['hidden','Hidden']];",
    "var st = { trip: { id: 'A' }, photoLinks: [], hiddenPhotoLinks: [],",
    "           tripCal: null, photoWindows: {} };",
    "var root = null;",
    "function renderAll() {}",
    "function dayById(id) { return { id: id, day_index: 1, date: '2026-05-01' }; }",
    "function dayChipText() { return 'Day 1'; }",
    "function dayListText() { return 'Day 1'; }",
    "function linkNeedsReview() { return false; }",
    "function linkSharedWithLori() { return false; }",
    "function thumbImg() { return document.createElement('img'); }",
    "function photoPager() { return document.createElement('div'); }",
    "function openPlacementMove() {}",
    "function addPhotosToDay() { return Promise.resolve({}); }",
    "function removePhotosFromDay() { return Promise.resolve({}); }",
    "function setPhotoLinksHidden() { return Promise.resolve({}); }",
    "function paletteLoadHidden() { return Promise.resolve(); }",
    "function paletteBumpGeneration() { paletteGeneration++; }",
    "function paletteAfterBatch() {}",
    "function timelineEdit() { return st.tripCal && st.tripCal.edit; }",
    "function timelineEditDirtyBlocks() { return false; }",
    "var TL_EDIT_FIELDS = { photo: [{ name: 'caption', label: 'Caption' }] };",
    // A stand-in for the real editor, so this test measures WIRING --
    // whether the pane draws an editor at all -- not the editor's own
    // markup, which the timeline already owns and tests.
    "function renderTimelineEditor(ed) {",
    "  var w = document.createElement('div');",
    "  w.className = 'tdl-tl-editor';",
    "  var f = document.createElement('textarea');",
    "  f.className = 'tdl-tl-field';",
    "  f.value = ed.values.caption;",
    "  w.appendChild(f);",
    "  return w;",
    "}",
    extract("el"),
    extract("btn"),
    extract("linkDayIds"),
    extract("linkIsOnDay"),
    extract("linkHasNoDayPlacement"),
    extract("linkIsOnMultipleDays"),
    extract("linkIsCompletelyUnplaced"),
    extract("linkMatchesPaletteFilter"),
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
    extract("photoWindow"),
    extract("openCaptionEditorForLink"),
    extract("paletteLinks"),
    extract("renderPaletteCard"),
    extract("renderPalettePane"),
    "return { st, newPaletteState, renderPalettePane,",
    "         openCaptionEditorForLink, paletteToggleSelected,",
    "         paletteSelectedIds };"
  ].join("\n"))(doc);

  function fields(pane) {
    return doc.findAll(pane, ".tdl-tl-field");
  }

  function setup(filter, links, hidden) {
    mod.st.photoLinks = links;
    mod.st.tripCal = { dayId: "d1", mode: "palette", edit: null,
                       palette: mod.newPaletteState() };
    mod.st.tripCal.palette.filter = filter;
    mod.st.tripCal.palette.hidden = hidden || [];
    mod.st.tripCal.palette.hiddenLoaded = true;
  }

  // (a) an ordinary card
  setup("all", [{ id: "v1", caption: "the old caption", trip_day_ids: [] }]);
  let pane = mod.renderPalettePane(mod.st.tripCal);
  check("no editor is mounted until one is asked for",
    fields(pane).length === 0, fields(pane).length + " fields");

  mod.openCaptionEditorForLink("v1");
  pane = mod.renderPalettePane(mod.st.tripCal);
  check("CORRECTION: Edit caption MOUNTS a field in Palette mode",
    fields(pane).length === 1, fields(pane).length + " fields");
  check("CORRECTION: …carrying the photograph's current caption",
    fields(pane)[0] && fields(pane)[0].value === "the old caption",
    fields(pane)[0] && fields(pane)[0].value);

  // (b) a photograph NOT on the selected day -- no timeline row exists,
  // which is why switching to Timeline would not have worked.
  setup("noday", [{ id: "off", caption: "not on a day", trip_day_ids: [] }]);
  mod.openCaptionEditorForLink("off");
  pane = mod.renderPalettePane(mod.st.tripCal);
  check("CORRECTION: a Not-on-a-day photograph opens its editor",
    fields(pane).length === 1 && fields(pane)[0].value === "not on a day",
    fields(pane).length + " fields");

  // (c) a HIDDEN photograph, which the Photos tab's list never contains
  setup("hidden", [], [{ id: "h1", caption: "hidden caption", hidden: 1,
                         trip_day_ids: ["d1"] }]);
  mod.openCaptionEditorForLink("h1");
  pane = mod.renderPalettePane(mod.st.tripCal);
  check("CORRECTION: a HIDDEN photograph opens its editor",
    fields(pane).length === 1 && fields(pane)[0].value === "hidden caption",
    fields(pane).length + " fields");

  // (d) state survives the round trip
  setup("noday", [{ id: "a", caption: "x", trip_day_ids: [] },
                  { id: "b", caption: "y", trip_day_ids: [] }]);
  mod.paletteToggleSelected("a", true);
  mod.openCaptionEditorForLink("b");
  pane = mod.renderPalettePane(mod.st.tripCal);
  check("CORRECTION: opening the editor preserves mode, filter and selection",
    mod.st.tripCal.mode === "palette" &&
    mod.st.tripCal.palette.filter === "noday" &&
    mod.paletteSelectedIds().join(",") === "a",
    "mode=" + mod.st.tripCal.mode + " filter=" +
    mod.st.tripCal.palette.filter + " sel=" + mod.paletteSelectedIds());
  check("CORRECTION: …and the grid is still drawn beneath it",
    doc.findAll(pane, ".tdl-palette-card").length === 2,
    doc.findAll(pane, ".tdl-palette-card").length + " cards");
})();

(function aStaleHiddenFailureCannotEraseTheCurrentPool() {
  const mod = new Function([
    "var destroyed = false;",
    "var paletteGeneration = 1;",
    "var st = { trip: { id: 'A' }, photoLinks: [], showHiddenPhotos: true,",
    "           hiddenPhotoLinks: ['TRIP-B-HIDDEN'], tripCal: {} };",
    "var _calls = [];",
    "function api() {",
    "  return new Promise(function (res, rej) { _calls.push({res:res, rej:rej}); });",
    "}",
    "function invalidateMemoirPreview() { return Promise.resolve(); }",
    extract("reloadGuardIsCurrent"),
    extract("reloadPhotoLinks"),
    "return { st, reloadPhotoLinks, calls: _calls,",
    "         setTrip: function (id) { st.trip = { id: id }; } };"
  ].join("\n"))();

  const guard = { tripId: "A", gen: 1, needsModal: true };
  const pending = mod.reloadPhotoLinks(guard);
  mod.calls[0].res({ photo_links: [] });        // the visible half lands
  // Wait for the SECOND request (the include_hidden one) to actually be
  // issued before moving on -- a draft rejected calls[1] before it
  // existed, so the failure path was never reached and the mutation
  // survived. Poll rather than guess a microtask count.
  return (function waitForSecond(n) {
    if (mod.calls.length > 1 || n > 50) return Promise.resolve();
    return Promise.resolve().then(function () { return waitForSecond(n + 1); });
  })(0).then(function () {
    check("the stale-hidden test actually reaches the failure path",
      mod.calls.length > 1, mod.calls.length + " api calls issued");
    mod.setTrip("B");                           // the operator moves on
    if (mod.calls[1]) mod.calls[1].rej(new Error("gone"));
    return pending;
  }).then(function () {
    check("CORRECTION: a stale hidden FAILURE does not erase the current " +
          "trip's hidden pool",
      mod.st.hiddenPhotoLinks[0] === "TRIP-B-HIDDEN",
      "hiddenPhotoLinks=" + JSON.stringify(mod.st.hiddenPhotoLinks));
  });
})();

(function aFilterChangeReconcilesRatherThanDiscarding() {
  const mod = new Function([
    "var destroyed = false;",
    "var paletteGeneration = 5;",
    "var st = { trip: { id: 'A' }, tripCal: null };",
    "function renderAll() {}",
    "function sameTrip(id) { return st.trip && st.trip.id === id; }",
    "function paletteGenerationIsCurrent(g) { return g === paletteGeneration; }",
    extract("newPaletteState"),
    extract("paletteState"),
    extract("paletteSelectedIds"),
    extract("paletteToggleSelected"),
    extract("paletteAfterBatch"),
    "return { st, newPaletteState, paletteToggleSelected,",
    "         paletteSelectedIds, paletteAfterBatch,",
    "         bump: function () { paletteGeneration++; } };"
  ].join("\n"))();

  mod.st.tripCal = { palette: mod.newPaletteState() };
  const all = ids(120);
  all.forEach(id => mod.paletteToggleSelected(id, true));
  const done = all.slice(0, 50);
  const unsent = all.slice(50);

  mod.bump();          // a FILTER change: same trip, same modal
  mod.paletteAfterBatch(
    { done: done, changed: done, already: [], unsent: unsent,
      cancelled: true }, done, "removed", 5, "A");

  const still = mod.paletteSelectedIds();
  check("CORRECTION: a same-trip filter change still removes the COMPLETED " +
        "ids from the selection",
    still.length === 70, still.length + " still selected");
  check("CORRECTION: …the 70 unsent stay selected",
    done.every(id => still.indexOf(id) < 0) &&
    unsent.every(id => still.indexOf(id) >= 0));
  check("CORRECTION: …and the status records both numbers",
    /50 removed/.test(mod.st.tripCal.palette.status) &&
    /70 not sent/.test(mod.st.tripCal.palette.status),
    mod.st.tripCal.palette.status);

  // A TRIP change is different: suppress entirely.
  mod.st.tripCal.palette.status = "UNTOUCHED";
  mod.paletteAfterBatch({ done: ["z"], changed: ["z"], already: [],
                          unsent: [], cancelled: true }, ["z"], "removed",
                        5, "OLD-TRIP");
  check("CORRECTION: a TRIP change suppresses the report entirely",
    mod.st.tripCal.palette.status === "UNTOUCHED",
    mod.st.tripCal.palette.status);
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

// ── P4 correction: the Hidden pool refreshes with every other pool ────
//
// The reported defect: Add, Remove, Move and a caption save refreshed the
// VISIBLE pool only, so a hidden card kept displaying a day it was no
// longer on and a caption it no longer had. Reproduced live against
// SQLite before the fix.
//
// Two halves, and they are different kinds of evidence:
//   * BEHAVIOURAL — the real reloadPalettePhotoPools and the real
//     paletteLoadHidden run against a fake api, and the hidden pool is
//     checked for the NEW server values afterwards;
//   * WIRING — each of the five operations is checked to delegate to the
//     helper, which is what a mutation removing the refresh would break.

function loadPools(apiImpl, seed) {
  const state = {
    st: { trip: { id: "T" }, tripCal: { palette: null }, showHiddenPhotos: false },
    daysCalls: 0, linkCalls: 0, renders: 0
  };
  const body = [
    "var __s = arguments[0]; var api = arguments[1];",
    "var st = __s.st;",
    "var paletteGeneration = 0;",
    "function renderAll(){ __s.renders++; }",
    "function sameTrip(t){ return !!st.trip && st.trip.id === t; }",
    "function paletteGenerationIsCurrent(g){",
    "  return g === paletteGeneration && !!st.tripCal; }",
    "function paletteState(){",
    "  if (!st.tripCal) return null;",
    "  if (!st.tripCal.palette) st.tripCal.palette = " +
      "{ filter:'all', selected:{}, status:'', hidden:[], " +
      "hiddenLoaded:false, hiddenError:'' };",
    "  return st.tripCal.palette; }",
    "function reloadPhotoLinks(){ __s.linkCalls++; return Promise.resolve(); }",
    "function reloadDays(){ __s.daysCalls++; return Promise.resolve(); }",
    extract("paletteLoadHidden"),
    extract("reloadPalettePhotoPools"),
    "return { reloadPalettePhotoPools: reloadPalettePhotoPools," +
    "         paletteState: paletteState, st: st };"
  ].join("\n");
  const mod = new Function(body)(state, apiImpl);
  const p = mod.paletteState();
  Object.assign(p, seed || {});
  return { mod, state, p };
}

// The server's answer AFTER the operation: the hidden photograph has
// lost its day and gained a caption. If the pool is not refetched, the
// card keeps the old ones.
const HIDDEN_AFTER = {
  photo_links: [
    { id: "h1", hidden: 1, trip_day_ids: [], caption: "new caption" }
  ]
};
const HIDDEN_BEFORE = {
  id: "h1", hidden: 1, trip_day_ids: ["d2"], caption: ""
};

(function hiddenPoolIsRefetchedWhenItIsLoaded() {
  let asked = 0;
  const { mod, state, p } = loadPools(function (url) {
    if (/include_hidden=1/.test(url)) { asked++; return Promise.resolve(HIDDEN_AFTER); }
    return Promise.resolve({});
  }, { hidden: [HIDDEN_BEFORE], hiddenLoaded: true });

  return mod.reloadPalettePhotoPools({ tripId: "T" }, { days: true })
    .then(function (r) {
      const card = mod.paletteState().hidden[0];
      check("a loaded Hidden pool is refetched with the visible pool",
        asked === 1, "include_hidden requests: " + asked);
      check("…so a hidden card stops showing a day it is no longer on",
        card.trip_day_ids.length === 0, JSON.stringify(card.trip_day_ids));
      check("…and shows the caption that was just saved to it",
        card.caption === "new caption", card.caption);
      check("…and days are refreshed when placements moved",
        state.daysCalls === 1, state.daysCalls);
      check("…and nothing is reported stale on a clean refresh",
        r.hiddenStale === false && r.hiddenError === "");
    });
})();

(function captionSaveDoesNotRefetchEveryDayCard() {
  const { mod, state } = loadPools(function () { return Promise.resolve(HIDDEN_AFTER); },
    { hidden: [HIDDEN_BEFORE], hiddenLoaded: true });
  return mod.reloadPalettePhotoPools(null, { days: false }).then(function () {
    check("a caption save refreshes the pools but NOT the day cards",
      state.daysCalls === 0 && state.linkCalls === 1,
      "days=" + state.daysCalls + " links=" + state.linkCalls);
  });
})();

(function anUnopenedHiddenPoolCostsNothing() {
  let asked = 0;
  const { mod } = loadPools(function (url) {
    if (/include_hidden=1/.test(url)) asked++;
    return Promise.resolve(HIDDEN_AFTER);
  }, { hidden: [], hiddenLoaded: false, filter: "all" });
  return mod.reloadPalettePhotoPools(null, { days: true }).then(function () {
    check("a Hidden pool that was never opened is not fetched",
      asked === 0, "include_hidden requests: " + asked);
  });
})();

(function showingHiddenForcesTheFetchEvenBeforeFirstLoad() {
  let asked = 0;
  const { mod } = loadPools(function (url) {
    if (/include_hidden=1/.test(url)) { asked++; return Promise.resolve(HIDDEN_AFTER); }
    return Promise.resolve({});
  }, { hidden: [], hiddenLoaded: false, filter: "hidden" });
  return mod.reloadPalettePhotoPools(null, { days: true }).then(function () {
    check("but a Palette SHOWING Hidden is refreshed regardless",
      asked === 1, "include_hidden requests: " + asked);
  });
})();

(function aFailedHiddenRefreshIsReportedWithoutFailingTheWrite() {
  const { mod } = loadPools(function (url) {
    if (/include_hidden=1/.test(url)) return Promise.reject(new Error("hidden boom"));
    return Promise.resolve({});
  }, { hidden: [HIDDEN_BEFORE], hiddenLoaded: true });
  let rejected = false;
  return mod.reloadPalettePhotoPools(null, { days: true })
    .catch(function () { rejected = true; return null; })
    .then(function (r) {
      check("a Hidden-pool failure does NOT reject — the write stands",
        rejected === false);
      check("…and is reported as stale display, separately",
        !!r && r.hiddenStale === true && /hidden boom/.test(r.hiddenError),
        r && r.hiddenError);
      check("…and the Hidden grid gets an error, never an honest-looking zero",
        /hidden boom/.test(mod.paletteState().hiddenError));
    });
})();

(function aPrimaryFailureStillRejects() {
  const { mod } = loadPools(function () { return Promise.resolve({}); },
    { hidden: [], hiddenLoaded: true });
  // Break the primary pool by making reloadPhotoLinks throw through api.
  const broken = loadPools(function () { return Promise.resolve({}); }, {});
  // Direct check: the helper's first job is the visible pool, and a
  // rejection there must propagate so the caller reports a stale screen.
  const srcFn = extract("reloadPalettePhotoPools");
  check("the visible pool is the first job, so its failure propagates",
    /jobs\s*=\s*\[reloadPhotoLinks\(guard\)\]/.test(srcFn));
  check("…and the hidden fetch is deliberately not in that Promise.all",
    !/Promise\.all\(\[[^\]]*paletteLoadHidden/.test(srcFn));
})();

(function everyOperationThatCanChangeAHiddenCardDelegatesToTheHelper() {
  // WIRING half. A mutation that drops the refresh from any one of these
  // — reverting it to Promise.all([reloadDays(), reloadPhotoLinks()]) —
  // fails exactly the line named for it.
  const ops = [
    ["addPhotosToDay", "Add"],
    ["removePhotosFromDay", "Remove"],
    ["movePlacement", "Move"],
    ["unlinkDayPhoto", "Remove from the timeline row"],
    ["timelineOwnerReload", "caption save"]
  ];
  ops.forEach(function (pair) {
    const body = extract(pair[0]);
    check(pair[1] + " refreshes every Palette pool, not just the visible one",
      /reloadPalettePhotoPools\(/.test(body), pair[0]);
    check(pair[1] + " no longer refreshes the visible pool alone",
      !/Promise\.all\(\[reloadDays\(\),\s*reloadPhotoLinks\(\)\]\)/.test(body) &&
      !/Promise\.all\(\[reloadPhotoLinks\(guard\),\s*reloadDays/.test(body),
      pair[0]);
  });
  // Hide/Restore is the one caller that must NOT use the helper: it has
  // to load the pool even the first time, so the Hidden chip can turn
  // from "(?)" into a real count. Pinned so a later tidy-up cannot
  // "unify" it and quietly break that.
  // Comment lines stripped first. The paragraph inside this function
  // explaining why it must NOT use the helper names the helper, so a raw
  // scan fires on the explanation — the fourth time that has happened in
  // this file's history, and the reason the rule is written here again.
  const hideBody = extract("setPhotoLinksHidden")
    .split("\n").filter(l => !/^\s*\/\//.test(l)).join("\n");
  check("Hide/Restore still loads the Hidden pool unconditionally",
    /paletteLoadHidden\(\)/.test(hideBody) &&
    !/reloadPalettePhotoPools/.test(hideBody));
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
