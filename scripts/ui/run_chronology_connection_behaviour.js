#!/usr/bin/env node
/**
 * WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 2, Part A —
 * behaviour a source scan cannot judge.
 *
 * `tests/test_travel_doc_chronology_integration.py` pins the SHAPE of the
 * connection: one fetch through api(), a generation guard, a person_id
 * check, refresh calls at every day-moving write, and the export gate.
 * None of that answers the questions an operator actually has:
 *
 *   * does the reconciler notice a day whose date moved?
 *   * does it match by STABLE DAY ID, so re-ordering is not reported as
 *     "every day changed"?
 *   * is a day the projection legitimately dropped (no date) reported as
 *     a note rather than as a disagreement?
 *   * is a day the projection HAS and the workspace does not a real
 *     disagreement?
 *   * does Today stay off for a trip with no dates?
 *
 * So this executes the real functions, lifted out of
 * ui/js/travel-doc-lab.js by name. A copy of the logic here would keep
 * passing after somebody changed the product, which is the failure mode
 * this file exists to avoid.
 *
 * Usage:  node scripts/ui/run_chronology_connection_behaviour.js
 * Exit 0 all green, 1 otherwise. No server, no browser, no arguments.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SRC = path.resolve(__dirname, "..", "..", "ui", "js", "travel-doc-lab.js");
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

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

// The real functions, over a `st` this harness controls.
const mod = new Function([
  "var st = { trip: null, days: [], chronology: null, chronologyStatus: 'ok',",
  "           chronologyError: '', chronologyStale: false,",
  "           chronologyReconcile: null };",
  extract("canonicalDaysForTrip"),
  extract("_dayYear"),
  extract("_projectedLabel"),
  extract("reconcileCanonicalDays"),
  extract("chronologySummary"),
  "return { st: st, reconcile: reconcileCanonicalDays,",
  "         summary: chronologySummary, dayYear: _dayYear,",
  "         label: _projectedLabel, forTrip: canonicalDaysForTrip };",
].join("\n"))();

function scenario(days, canonicalDays, tripExtra) {
  mod.st.trip = Object.assign({ id: "T1", start_date: "", end_date: "" },
    tripExtra || {});
  mod.st.days = days;
  mod.st.chronology = {
    person_id: "P1",
    seed_ready: true,
    periods: [
      { era_id: "building_years", start_year: 1980, end_year: 2005,
        is_current_life: false },
      { era_id: "later_years", start_year: 2006, end_year: 2030,
        is_current_life: false },
      { era_id: "today", start_year: null, end_year: null,
        is_current_life: true },
    ],
    timeline_events: [{ id: "e1", year: 2019 }, { id: "e2", year: 1999 }],
    story_evidence: [
      { id: "s1", status: "approved" },
      { id: "s2", status: "provisional" },
      { id: "s3", status: "provisional" },
    ],
    trip_days: canonicalDays,
    sources: {
      periods: { source: "lv_eras + profile.dob", status: "derived" },
      timeline_events: { source: "timeline_events", status: "read", count: 2 },
      story_evidence: { source: "story_candidates", status: "read", count: 3 },
      trip_days: { source: "trips + trip_days", status: "read", count: canonicalDays.length },
      authority: "server",
    },
  };
  return mod.reconcile();
}

const DETAILED = [
  { id: "d1", day_index: 1, date: "2019-06-01", title: "Arrival",
    main_location: "Munich", lodging_base: "Hotel A" },
  { id: "d2", day_index: 2, date: "2019-06-02", title: "",
    main_location: "Salzburg", lodging_base: "Hotel B" },
];
function canonicalFrom(rows) {
  return rows.map(function (d) {
    return {
      id: d.id, trip_id: "T1", day_index: d.day_index, date: d.date,
      year: Number(String(d.date).slice(0, 4)) || null,
      label: d.title || d.main_location || "",
      main_location: d.main_location, lodging_base: d.lodging_base,
      shelf: "travels", lane: "travels",
    };
  });
}

(function agreementIsRecognised() {
  const rec = scenario(DETAILED, canonicalFrom(DETAILED));
  check("identical detail and projection agree",
    rec.agrees && rec.mismatched.length === 0, JSON.stringify(rec.mismatched));
  check("both counts are reported",
    rec.detailedCount === 2 && rec.canonicalCount === 2);

  // The day with no title: the projection's label falls back to main
  // location, and comparing a RAW title against a PROJECTED label would
  // report a difference on every untitled day — which is most of them.
  check("an untitled day does not read as a label mismatch",
    !rec.mismatched.some(m => m.dayId === "d2" && m.field === "label"));
})();

(function everyComparedFieldIsActuallyCompared() {
  const fields = ["day_index", "date", "year", "label", "main_location",
                  "lodging_base"];
  fields.forEach(function (f) {
    const canon = canonicalFrom(DETAILED);
    if (f === "day_index") canon[0].day_index = 99;
    else if (f === "date") { canon[0].date = "2019-07-01"; canon[0].year = 2019; }
    else if (f === "year") canon[0].year = 1998;
    else if (f === "label") canon[0].label = "Something else";
    else if (f === "main_location") canon[0].main_location = "Berlin";
    else if (f === "lodging_base") canon[0].lodging_base = "Hostel Z";
    const rec = scenario(DETAILED, canon);
    check("a difference in " + f + " is reported",
      !rec.agrees && rec.mismatched.some(m => m.field === f),
      JSON.stringify(rec.mismatched.map(m => m.field)));
  });
})();

(function matchingIsByStableDayId() {
  // Same days, REORDERED in the projection. A positional comparison would
  // call this two mismatches; an id-keyed one calls it agreement.
  const canon = canonicalFrom(DETAILED).reverse();
  const rec = scenario(DETAILED, canon);
  check("re-ordering the projection is not a disagreement",
    rec.agrees, JSON.stringify(rec.mismatched));
})();

(function undatedDaysAreANoteNotADisagreement() {
  const days = DETAILED.concat([
    { id: "d3", day_index: 3, date: "", title: "Someday",
      main_location: "", lodging_base: "" },
  ]);
  const rec = scenario(days, canonicalFrom(DETAILED));
  check("a day with no date is NOT counted as a disagreement", rec.agrees);
  check("...but it IS reported, flagged undated",
    rec.onlyDetailed.length === 1 && rec.onlyDetailed[0].undated === true &&
    rec.onlyDetailed[0].dayId === "d3");
})();

(function aProjectionOnlyDayIsADisagreement() {
  // The workspace does not have a day the projection does. That means the
  // two are looking at different trips, and it must NOT be silent.
  const canon = canonicalFrom(DETAILED).concat([{
    id: "d9", trip_id: "T1", day_index: 9, date: "2019-06-09", year: 2019,
    label: "Ghost", main_location: "", lodging_base: "",
  }]);
  const rec = scenario(DETAILED, canon);
  check("a day only the projection has is a disagreement",
    !rec.agrees && rec.onlyCanonical.length === 1 &&
    rec.onlyCanonical[0].dayId === "d9");
})();

(function otherTripsAreIgnored() {
  const canon = canonicalFrom(DETAILED).concat([{
    id: "z1", trip_id: "OTHER", day_index: 1, date: "2001-01-01", year: 2001,
    label: "Another trip", main_location: "", lodging_base: "",
  }]);
  const rec = scenario(DETAILED, canon);
  check("days belonging to another trip are filtered out",
    rec.agrees && rec.canonicalCount === 2, "canonical=" + rec.canonicalCount);
})();

(function summaryNumbersComeFromTheServer() {
  scenario(DETAILED, canonicalFrom(DETAILED));
  const s = mod.summary();
  check("canonical day count is the projection's", s.canonicalDays === 2);
  check("overlapping historical period is found",
    s.periods.length === 1 && s.periods[0].era_id === "later_years",
    JSON.stringify(s.periods.map(p => p.era_id)));
  check("the current-life bucket is never listed as a historical period",
    !s.periods.some(p => p.is_current_life));
  check("nearby confirmed events are counted by year",
    s.nearbyEvents === 1, "got " + s.nearbyEvents);
  check("approved and provisional stories are counted apart",
    s.storiesApproved === 1 && s.storiesProvisional === 2);
  check("provenance and status travel with it",
    s.sources && s.sources.trip_days.status === "read" &&
    s.sources.authority === "server");
})();

(function todayIsNeverDerivedFromAMissingYear() {
  // THE RULE. A trip with no dates is a trip with no dates. Calling it
  // "today" because nothing said otherwise would be the system inventing
  // a placement — which is the whole failure class this lane exists to
  // end.
  scenario(
    [{ id: "u1", day_index: 1, date: "", title: "", main_location: "",
       lodging_base: "" }],
    []);
  check("a trip with no dates at all does NOT land in Today",
    mod.summary().todayApplies === false);

  scenario(DETAILED, canonicalFrom(DETAILED));
  check("a trip dated in the past does NOT land in Today",
    mod.summary().todayApplies === false);

  scenario(DETAILED, canonicalFrom(DETAILED), { live_state: "active" });
  check("a trip the operator marked ACTIVE does land in Today",
    mod.summary().todayApplies === true);

  const yr = new Date().getFullYear();
  const future = [{ id: "f1", day_index: 1, date: yr + "-01-01", title: "",
                    main_location: "", lodging_base: "" }];
  scenario(future, canonicalFrom(future));
  check("a trip dated this year does land in Today",
    mod.summary().todayApplies === true);
})();

(function unavailableIsNotEmpty() {
  // The server-side half of this rule is tested in
  // tests/test_narrator_chronology_projection.py. This is the browser
  // half: a lane the server reports as unavailable must not render as a
  // count of zero.
  scenario(DETAILED, []);
  mod.st.chronology.sources.trip_days = {
    source: "trips + trip_days", status: "unavailable", count: 0,
  };
  const s = mod.summary();
  check("an unavailable lane keeps its status in the summary",
    s.sources.trip_days.status === "unavailable");
  check("...and is distinguishable from a read lane with zero rows",
    s.sources.trip_days.status !== s.sources.story_evidence.status);
})();

(function noChronologyIsAStateNotACrash() {
  mod.st.chronology = null;
  mod.st.trip = { id: "T1" };
  check("reconciling with no projection returns null rather than throwing",
    mod.reconcile() === null);
  const s = mod.summary();
  check("the summary degrades to zeroes without a projection",
    s.canonicalDays === 0 && s.periods.length === 0 &&
    s.todayApplies === false);
})();

// ── report ────────────────────────────────────────────────────────────
let failed = 0;
R.forEach(function (r) {
  if (!r.ok) failed++;
  console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
    (r.detail ? "  [" + r.detail + "]" : ""));
});
console.log("");
console.log(R.length - failed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
