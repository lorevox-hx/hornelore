/* tests/test_bb_persist_empty_guard.js — BUG-FE-HYDRATION-CROSS-
   NARRATOR-LEAK-01 guard logic.

   THE GUARD: _persistDrafts must refuse to PUT a questionnaire whose
   every field is empty. The narrator-switch persist path would otherwise
   write {personal:{fullName:"",dob:"",...}} over canonical truth. The
   KEYS exist (hydration created them) so an Object.keys length check
   cannot see it — the values have to be walked.

   ─────────────────────────────────────────────────────────────────────
   WHY THIS FILE WAS REWRITTEN (2026-09-20)

   It used to read bio-builder-core.js as TEXT, slice out the
   `var hasAnyValue = (function () {` IIFE by string markers, and rebuild
   it with `new Function`. When the inline walk was replaced by the
   shared `_hasOperatorContent` — the fix for
   BUG-BIO-QUESTIONNAIRE-LEGACY-SECTIONS-INVISIBLE-01, where a
   `_`-prefixed key holding an object read as empty and hid a narrator's
   grandparents — the marker vanished and this file died with
   "file rewritten?". It had been throwing ever since, which means it
   stopped guarding anything at exactly the moment the logic it guards
   changed.

   That is the failure mode of a source-slicing test: it tracks the
   SHAPE of the code rather than its BEHAVIOUR, so a legitimate
   refactor reads as a catastrophe and a behavioural regression inside
   the same shape reads as fine. It now loads the real module through
   the harness and calls the real function. Same cases, no reconstruction.
   ─────────────────────────────────────────────────────────────────── */
'use strict';

const assert = require('assert');
const { createHarness } = require('./harness/bio-builder-harness');

const hasAnyValue = createHarness().core._hasOperatorContent;

let n = 0;
function runTest(label, qq, expected) {
  const got = !!hasAnyValue(qq);
  assert.strictEqual(got, expected,
    `[${label}] expected ${expected} got ${got} for qq=${JSON.stringify(qq)}`);
  console.log('  ok  ' + label);
  n++;
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

/* ── the cases the old string-sliced version could not have had ──────
   These are the reason the rewrite is worth more than a marker repair.
   Both come from real defects; neither is expressible against a
   reconstructed IIFE, because the behaviour lives in the shared
   function the inline copy was replaced by. */

// BUG-BIO-QUESTIONNAIRE-LEGACY-SECTIONS-INVISIBLE-01. A bookkeeping key
// is a key whose VALUE is a scalar — not a key whose NAME starts with an
// underscore. A `_`-prefixed key holding an object is a CONTAINER and
// must be descended into. Judging by name hid a narrator's grandparents.
runTest('underscore key holding real content',
  { _legacyRemovedSections: { grandparents: [{ firstName: "Anna" }] } }, true);

// ...while a `_`-prefixed SCALAR is bookkeeping and is not content. This
// is what stops the WO-02 entry id making a blank row look like a person.
runTest('underscore scalar only',     { parents: [{ _entryId: "e_abc" }] },   false);
runTest('id plus a real answer',      { parents: [{ _entryId: "e_abc", firstName: "Anna" }] }, true);

// A string is not an object: `String({})` is truthy, which is how the
// original shallow check locked every new narrator out of saving.
runTest('nested empty objects',       { personal: {}, parents: [{}] },        false);

console.log(`\n${n} tests passed`);
