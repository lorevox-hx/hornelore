#!/usr/bin/env node
/**
 * WO-TRAVEL-DOC-CLOSEOUT-01 — the preview-epoch race, driven.
 *
 * WHY A HARNESS AND NOT A SOURCE SCAN
 * -----------------------------------
 * The property is a SEQUENCE property: which of two responses, resolved
 * out of order and from two different tabs, is allowed to write. A
 * source scan can see that a token exists; it cannot see that bumping it
 * one line too late leaves the hole open. That is exactly the bug this
 * exists to catch, and a scan had already passed over it.
 *
 * It extracts the real functions from ui/js/travel-doc-lab.js rather
 * than restating them, so it cannot drift from the shipped code. Plain
 * node, no dependencies, no browser, no stack.
 *
 *     node scripts/ui/run_travel_doc_preview_race_check.js
 *
 * Exit 0 = all checks pass. Exit 1 = a check failed.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const REPO = path.resolve(__dirname, "..", "..");
const JS = fs.readFileSync(path.join(REPO, "ui", "js", "travel-doc-lab.js"),
                           "utf8");

function slice(start, end, label) {
  const a = JS.indexOf(start);
  if (a < 0) throw new Error(`could not find start of ${label}: ${start}`);
  const b = JS.indexOf(end, a);
  if (b < 0) throw new Error(`could not find end of ${label}: ${end}`);
  return JS.slice(a, b);
}

// The real invalidation function, verbatim.
const invalidateSrc = slice("function invalidateMemoirPreview() {",
                            "\n  function reloadDays(",
                            "invalidateMemoirPreview");

// Deferred fetches: each call parks and hands back a resolver, so the
// test decides the completion ORDER. That is the whole point — with
// promises that resolve immediately, out-of-order is unreachable.
const prelude = `
let destroyed = false;
const st = { tab: "document", trip: { id: "T1" }, memoirPreview: null, error: null };
var memoirPreviewToken = 0;
const parked = [];
function api(path) {
  return new Promise(function (resolve, reject) {
    parked.push({ path: path, resolve: resolve, reject: reject });
  });
}
function renderAll() {}
`;

const runner = new Function(
  prelude + invalidateSrc +
  "return { st, parked, invalidate: invalidateMemoirPreview, " +
  "setTab: (t) => { st.tab = t; }, " +
  "setTrip: (id) => { st.trip = { id: id }; }, " +
  "token: () => memoirPreviewToken };"
)();

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log(`  PASS  ${name}`); }
  else { fail++; console.log(`  FAIL  ${name}${detail ? "  — " + detail : ""}`); }
}
const flush = () => new Promise((r) => setTimeout(r, 0));

(async function () {
  console.log("Travel Document — preview epoch, driven as request sequences\n");

  // 1. THE BUG. A fetch starts on the document tab; the operator moves
  //    to another tab and approves something; the OLD response lands.
  //    It must not write.
  runner.st.tab = "document";
  runner.st.memoirPreview = null;
  runner.parked.length = 0;
  runner.invalidate();                       // request A, token 1
  const A = runner.parked.pop();
  runner.setTab("notes");                    // operator moves away
  runner.invalidate();                       // approval off-tab: no fetch
  A.resolve({ marker: "STALE" });            // A lands late
  await flush();
  check("an off-tab invalidation supersedes an in-flight request",
        runner.st.memoirPreview === null,
        `memoirPreview = ${JSON.stringify(runner.st.memoirPreview)}`);

  // 2. And because it did not write, the tab-switch handler's own
  //    condition (`!st.memoirPreview`) is still true, so returning to
  //    the tab refetches instead of showing the stale copy.
  check("the cache is still empty, so returning to the tab refetches",
        runner.st.memoirPreview === null);

  // 3. Two same-trip requests completing OUT OF ORDER: only the newest
  //    may write.
  runner.setTab("document");
  runner.st.memoirPreview = null;
  runner.parked.length = 0;
  runner.invalidate();                       // request B
  const B = runner.parked.pop();
  runner.invalidate();                       // request C, supersedes B
  const C = runner.parked.pop();
  B.resolve({ marker: "OLD" });              // B lands FIRST
  await flush();
  check("a superseded response does not write, even arriving first",
        runner.st.memoirPreview === null);
  C.resolve({ marker: "NEW" });
  await flush();
  check("the newest response writes",
        runner.st.memoirPreview && runner.st.memoirPreview.marker === "NEW",
        JSON.stringify(runner.st.memoirPreview));

  // 4. A stale FAILURE must not paint an error over a newer preview.
  runner.st.memoirPreview = null;
  runner.st.error = null;
  runner.parked.length = 0;
  runner.invalidate();                       // D
  const D = runner.parked.pop();
  runner.invalidate();                       // E supersedes D
  const E = runner.parked.pop();
  E.resolve({ marker: "GOOD" });
  await flush();
  D.reject(new Error("stale failure"));
  await flush();
  check("a superseded FAILURE does not overwrite a good preview",
        runner.st.memoirPreview && runner.st.memoirPreview.marker === "GOOD",
        JSON.stringify(runner.st.memoirPreview));
  check("and does not paint an error", runner.st.error === null,
        String(runner.st.error));

  // 5. A response for a DIFFERENT trip is rejected on trip, not token.
  runner.st.memoirPreview = null;
  runner.parked.length = 0;
  runner.invalidate();                       // F for T1
  const F = runner.parked.pop();
  runner.setTrip("T2");
  F.resolve({ marker: "WRONG-TRIP" });
  await flush();
  check("a response for the previous trip is rejected",
        runner.st.memoirPreview === null);

  // 6. Non-vacuity. Without this the checks above would all pass on an
  //    invalidation that never writes anything at all.
  runner.setTrip("T3");
  runner.st.memoirPreview = null;
  runner.parked.length = 0;
  runner.invalidate();
  runner.parked.pop().resolve({ marker: "PLAIN" });
  await flush();
  check("an ordinary single request DOES write (non-vacuity)",
        runner.st.memoirPreview && runner.st.memoirPreview.marker === "PLAIN",
        JSON.stringify(runner.st.memoirPreview));

  // 7. Off-tab invalidation must still bump the epoch, which is the
  //    line that was in the wrong place.
  runner.setTab("notes");
  const before = runner.token();
  runner.invalidate();
  check("the epoch advances even when no fetch is made",
        runner.token() === before + 1,
        `${before} -> ${runner.token()}`);

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail === 0 ? 0 : 1);
})();
