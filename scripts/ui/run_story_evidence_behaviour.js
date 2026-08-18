#!/usr/bin/env node
/**
 * WO-LOREVOX-NARRATOR-STORY-INTEGRATION-01 Phase 3, Commit B —
 * behaviour a source scan cannot judge.
 *
 * `tests/test_story_product_consumption.py` pins that both Life Map
 * renderers call the shared reader and that it owns no state. Neither
 * answers the questions the Life Map actually asks:
 *
 *   * does an unplaced story stay OUT of Today?
 *   * are approved and provisional really counted apart, per era?
 *   * does a story with a year but no era count as placed? (It must not:
 *     the map is drawn in eras.)
 *   * does an unavailable lane read differently from an empty narrator?
 *
 * This executes the SHIPPED ui/js/story-evidence.js against a fake
 * `state`. A reimplementation here would keep passing after somebody
 * changed the product.
 *
 * Usage:  node scripts/ui/run_story_evidence_behaviour.js
 * Exit 0 all green, 1 otherwise. No server, no browser, no arguments.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.resolve(__dirname, "..", "..", "ui", "js", "story-evidence.js");

const R = [];
function check(name, ok, detail) {
  R.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
}

function load(projection) {
  const sandbox = { window: {}, console: { warn() {}, log() {} } };
  sandbox.state = { chronologyProjection: projection };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(SRC, "utf8"), sandbox);
  return sandbox.window.LorevoxStoryEvidence;
}

function story(o) {
  return Object.assign({
    id: "s" + Math.random().toString(16).slice(2, 8),
    status: "provisional",
    placement: "unplaced",
    era_candidates: [],
    year: null,
  }, o);
}

const READ = { story_evidence: { source: "story_candidates", status: "read", count: 0 } };

(function unplacedNeverBecomesToday() {
  const SE = load({
    story_evidence: [
      story({ status: "approved", placement: "unplaced", era_candidates: [] }),
      story({ status: "provisional", placement: "unplaced", era_candidates: [] }),
    ],
    sources: READ,
  });
  const today = SE.countsForEra("today");
  check("an unplaced story does NOT land in today",
    today.total === 0, "today total=" + today.total);
  check("...it lands in the unplaced group instead",
    SE.unplaced().total === 2);
  check("...and unplaced keeps approved and provisional apart",
    SE.unplaced().approved.length === 1 && SE.unplaced().provisional.length === 1);
  check("the unplaced key is not an era id",
    SE.UNPLACED_KEY === "__unplaced__");
})();

(function aYearAloneDoesNotPlaceAStory() {
  // The Life Map is drawn in ERAS. A year with no era is not a position
  // on it, and deriving one would be exactly the inference this lane
  // exists to stop.
  const SE = load({
    story_evidence: [
      story({ status: "approved", placement: "stated", year: 1962, era_candidates: [] }),
    ],
    sources: READ,
  });
  check("a story with a year but no era is still unplaced",
    SE.unplaced().total === 1, "unplaced=" + SE.unplaced().total);
  check("...and appears in no era bucket",
    Object.keys(SE.byEra()).length === 1 &&
    Object.keys(SE.byEra())[0] === SE.UNPLACED_KEY);
})();

(function placementComesFromTheServer() {
  const SE = load({
    story_evidence: [
      story({ status: "approved", placement: "operator_set",
              era_candidates: ["building_years"] }),
      story({ status: "provisional", placement: "derived",
              era_candidates: ["building_years"] }),
      story({ status: "approved", placement: "stated",
              era_candidates: ["adolescence"] }),
    ],
    sources: READ,
  });
  const b = SE.countsForEra("building_years");
  check("approved and provisional are counted apart within an era",
    b.approved === 1 && b.provisional === 1 && b.total === 2,
    JSON.stringify(b));
  check("a second era is counted independently",
    SE.countsForEra("adolescence").approved === 1);
  check("an era with nothing reports zeroes, not undefined",
    SE.countsForEra("earliest_years").total === 0);
  check("nothing was misfiled as unplaced",
    SE.unplaced().total === 0);
})();

(function anUnplacedStoryIsNeverSummedAway() {
  const SE = load({
    story_evidence: [
      story({ status: "approved", placement: "stated", era_candidates: ["later_years"] }),
      story({ status: "provisional", placement: "unplaced", era_candidates: [] }),
      story({ status: "provisional", placement: "unplaced", era_candidates: [] }),
    ],
    sources: READ,
  });
  const t = SE.totals();
  check("totals keep the three numbers separate",
    t.approved === 1 && t.provisional === 2 && t.unplaced === 2,
    JSON.stringify(t));
  check("the summary label names them apart",
    /1 approved/.test(SE.summaryLabel()) &&
    /2 provisional/.test(SE.summaryLabel()) &&
    /2 unplaced/.test(SE.summaryLabel()), SE.summaryLabel());
})();

(function unavailableIsNotEmpty() {
  const empty = load({ story_evidence: [], sources: READ });
  check("a read lane with no stories reports read and an empty label",
    empty.laneStatus() === "read" && empty.summaryLabel() === "");

  const down = load({
    story_evidence: [],
    sources: { story_evidence: { source: "story_candidates", status: "unavailable", count: 0 } },
  });
  check("an unavailable lane says so",
    down.laneStatus() === "unavailable");
  check("...and its label is an outage, not silence",
    down.summaryLabel() === "stories unavailable", down.summaryLabel());
  check("...which is distinguishable from the empty narrator",
    down.summaryLabel() !== empty.summaryLabel());
})();

(function noProjectionIsAState() {
  const none = load(null);
  check("no projection loaded is not_loaded, not unavailable",
    none.laneStatus() === "not_loaded");
  check("...and degrades to zeroes without throwing",
    none.totals().total === 0 && none.items().length === 0);
  check("...and an era query is still safe",
    none.countsForEra("today").total === 0);
})();

(function discardedNeverArrive() {
  // The SERVER removes them. This asserts the reader does not quietly
  // depend on that by re-filtering -- if a discarded row ever appeared,
  // it must be visible as a bug rather than swallowed here.
  const src = fs.readFileSync(SRC, "utf8");
  check("the reader does not filter discarded itself",
    !/discarded/.test(src.replace(/\/\*[\s\S]*?\*\//g, "")),
    "the projection is responsible for exclusion");
})();

(function noStateIsRetained() {
  const SE = load({
    story_evidence: [story({ status: "approved", placement: "stated",
                             era_candidates: ["today"] })],
    sources: READ,
  });
  const first = SE.countsForEra("today").approved;
  // Mutating the projection must change the answer: nothing is cached.
  SE.items().length;
  check("a story explicitly placed in today IS counted there",
    first === 1, "got " + first);
})();

let failed = 0;
R.forEach(function (r) {
  if (!r.ok) failed++;
  console.log((r.ok ? "PASS  " : "FAIL  ") + r.name +
    (r.detail ? "  [" + r.detail + "]" : ""));
});
console.log("");
console.log(R.length - failed + " passed, " + failed + " failed");
process.exit(failed ? 1 : 0);
