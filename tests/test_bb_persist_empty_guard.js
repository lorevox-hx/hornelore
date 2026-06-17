/* tests/test_bb_persist_empty_guard.js — BUG-FE-HYDRATION-CROSS-
   NARRATOR-LEAK-01 guard logic test.

   Extracts the `hasAnyValue` IIFE from bio-builder-core.js
   _persistDrafts and pins its behavior on the empty-overwrite case.

   Run:  node tests/test_bb_persist_empty_guard.js
   ─────────────────────────────────────────────────────────────────── */
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const SRC = fs.readFileSync(
  path.join(REPO_ROOT, 'ui', 'js', 'bio-builder-core.js'), 'utf8'
);

// Slice the hasAnyValue IIFE block — between the unique comment marker
// and the `if (qq && Object.keys(qq).length > 0 && hasAnyValue)` line.
function sliceGuardSrc(src) {
  const startMarker = 'var hasAnyValue = (function () {';
  const endMarker = '})();';
  const start = src.indexOf(startMarker);
  if (start < 0) {
    throw new Error('Could not find hasAnyValue start marker — file rewritten?');
  }
  const end = src.indexOf(endMarker, start);
  if (end < 0) throw new Error('Could not find hasAnyValue end marker');
  return src.slice(start, end + endMarker.length);
}

const GUARD_SRC = sliceGuardSrc(SRC);

// Load by injecting `qq` as a parameter to a constructed function.
function buildHasAnyValue() {
  // The slice has the form `var hasAnyValue = (function () {...})();`
  // We need to wrap it so we can call it for different `qq` values.
  // Strategy: substitute the `qq` reference inside the IIFE with a
  // function param `qq`. Easier: wrap the IIFE so the outer `qq`
  // closure variable comes from a parameter.
  // eslint-disable-next-line no-new-func
  const factory = new Function('qq', GUARD_SRC + '\n return hasAnyValue;');
  return factory;
}

const hasAnyValue = buildHasAnyValue();

function runTest(label, qq, expected) {
  const got = hasAnyValue(qq);
  assert.strictEqual(got, expected,
    `[${label}] expected ${expected} got ${got} for qq=${JSON.stringify(qq)}`);
  console.log('  ok  ' + label);
}

console.log('hasAnyValue guard tests:');

// Empty cases — should refuse
runTest('null',                       null,                                   false);
runTest('undefined',                  undefined,                              false);
runTest('empty object',               {},                                     false);
runTest('section with empty string',  { personal: { fullName: "" } },         false);
runTest('section with all empties',   { personal: { fullName: "", dob: "" } }, false);
runTest('section with whitespace',    { personal: { fullName: "   " } },      false);
runTest('empty array section',        { parents: [] },                        false);
runTest('array of empty objects',     { parents: [{ firstName: "", lastName: "" }] }, false);

// Non-empty cases — should allow PUT
runTest('one field set',              { personal: { fullName: "Walt" } },     true);
runTest('numeric field set',          { personal: { birthOrder: 2 } },        true);
runTest('full identity',              {
  personal: { fullName: "Walt", dateOfBirth: "1948-03-17" },
}, true);
runTest('parents array with content', {
  parents: [{ firstName: "Patrick", lastName: "O'Donnell" }],
}, true);
runTest('mixed empties + one real',   {
  personal: { fullName: "", dob: "" },
  parents:  [{ firstName: "Patrick" }],
}, true);

console.log('\n13 tests passed');
