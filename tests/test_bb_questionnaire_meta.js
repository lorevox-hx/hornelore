/* ═══════════════════════════════════════════════════════════════
   tests/test_bb_questionnaire_meta.js — WO-BIO-QUESTIONNAIRE-
   BIO-FACTS-MIGRATE-01 Phase 2 helper coverage.

   Node-only tests for the four FE helpers added to
   ui/js/bio-builder-questionnaire.js:

     _BB_STATUS_LABELS  — status enum → label + css class
     _BB_KNOWN_STATUSES — which statuses count as "already known"
     _bbStatusBadgeHtml — render a per-field badge from meta
     _bbKnownPillHtml   — render the per-section filled-skip pill

   Strategy: extract the helper bodies from bio-builder-
   questionnaire.js via a single regex slice, wrap them in a stub
   scope that provides `_bb` + `_esc`, and exercise them on canned
   meta shapes. This keeps the tests aligned with the real source
   (rather than re-declaring the helpers and risking drift).

   Run:  node tests/test_bb_questionnaire_meta.js
   ═══════════════════════════════════════════════════════════════ */

'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const SRC = fs.readFileSync(
  path.join(REPO_ROOT, 'ui', 'js', 'bio-builder-questionnaire.js'),
  'utf8'
);

// Slice out the Phase 2 helper block. The block opens with the
// "/* ── WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2" banner
// and ends just before `var FULL_SECTIONS = [`.
function _sliceHelpers(src) {
  const startMarker = '/* ── WO-BIO-QUESTIONNAIRE-BIO-FACTS-MIGRATE-01 Phase 2';
  const endMarker = 'var FULL_SECTIONS = [';
  const start = src.indexOf(startMarker);
  const end = src.indexOf(endMarker);
  if (start < 0 || end < 0 || end <= start) {
    throw new Error(
      'Could not slice Phase 2 helper block — markers missing. ' +
      'Did the file get rewritten? Update markers in the test.'
    );
  }
  return src.slice(start, end);
}

const HELPER_SRC = _sliceHelpers(SRC);

// Stub the scope: _bb() returns a slot we can mutate per-test,
// _esc() escapes minimally (we don't need full XSS escaping for tests,
// just enough to keep the produced HTML deterministic).
let _STUB_BB = { questionnaire: {}, questionnaire_meta: {} };
function _bb()  { return _STUB_BB; }
function _esc(s) { return String(s == null ? '' : s).replace(/[<>&"]/g, (c) => ({
  '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;'
}[c])); }

// Load the helper block via a Function constructor: the helpers
// use `var` + function declarations which hoist into the constructed
// function's scope, and the trailing `return` statement we append
// hands them back as an object. This works under strict mode (where
// eval would not leak vars to the outer scope).
const helpers = (function _load() {
  const exportTail = '\nreturn {' +
    ' _BB_STATUS_LABELS: _BB_STATUS_LABELS,' +
    ' _BB_KNOWN_STATUSES: _BB_KNOWN_STATUSES,' +
    ' _bbMetaEntry: _bbMetaEntry,' +
    ' _bbStatusBadgeHtml: _bbStatusBadgeHtml,' +
    ' _bbKnownFieldCount: _bbKnownFieldCount,' +
    ' _bbKnownPillHtml: _bbKnownPillHtml' +
    ' };';
  // eslint-disable-next-line no-new-func
  const factory = new Function('_bb', '_esc', HELPER_SRC + exportTail);
  return factory(_bb, _esc);
})();

// Convenience: reset the stub `bb` between tests.
function setMeta(meta) {
  _STUB_BB = { questionnaire: {}, questionnaire_meta: meta };
}

// ── Tests ─────────────────────────────────────────────────────────

function testStatusLabelTableShape() {
  const want = [
    'approved', 'operator_entered', 'document_sourced',
    'anchored_asked', 'extracted_needs_verify',
    'anchored_asked_pending', 'conflicted',
    'superseded', 'empty',
  ];
  want.forEach((s) => {
    assert.ok(
      helpers._BB_STATUS_LABELS[s],
      `_BB_STATUS_LABELS missing entry for status="${s}"`
    );
  });
  // 'empty' should have a blank label so badge renders to "" for it
  assert.strictEqual(helpers._BB_STATUS_LABELS['empty'].label, '');
  // 'conflicted' must be red (the operator-attention status)
  assert.strictEqual(helpers._BB_STATUS_LABELS['conflicted'].cls, 'bb-badge-red');
  // 'approved' must be green
  assert.strictEqual(helpers._BB_STATUS_LABELS['approved'].cls, 'bb-badge-ok');
}

function testKnownStatusSetMirrorsServer() {
  // Mirrors server-side bio_gap_map._FILLED_STATUSES exactly.
  const want = new Set([
    'extracted_needs_verify',
    'document_sourced',
    'anchored_asked',
    'operator_entered',
    'approved',
  ]);
  const got = new Set(Object.keys(helpers._BB_KNOWN_STATUSES));
  assert.deepStrictEqual(
    got, want,
    'FE _BB_KNOWN_STATUSES must match server bio_gap_map._FILLED_STATUSES'
  );
  // Anchored-asked-pending + conflicted MUST NOT count as known.
  assert.ok(!helpers._BB_KNOWN_STATUSES['anchored_asked_pending']);
  assert.ok(!helpers._BB_KNOWN_STATUSES['conflicted']);
}

function testBadgeRendersOperatorEntered() {
  setMeta({
    personal: {
      dateOfBirth: { status: 'operator_entered', source: 'operator' },
    },
  });
  const html = helpers._bbStatusBadgeHtml('personal', 'dateOfBirth');
  assert.ok(html.includes('bb-status-badge'), 'badge wrapper present');
  assert.ok(html.includes('bb-badge-known'), 'operator_entered → bb-badge-known');
  assert.ok(html.includes('Entered'), 'label "Entered" present');
  assert.ok(html.includes('Source: operator'), 'tooltip carries source');
}

function testBadgeRendersConflictedAsRed() {
  setMeta({
    parents: {
      father_name: { status: 'conflicted', source: 'extractor' },
    },
  });
  const html = helpers._bbStatusBadgeHtml('parents', 'father_name');
  assert.ok(html.includes('bb-badge-red'), 'conflicted → bb-badge-red');
  assert.ok(html.includes('Conflicted'), 'label "Conflicted" present');
}

function testBadgeReturnsEmptyForUnknownSection() {
  setMeta({ personal: { dateOfBirth: { status: 'approved', source: '' } } });
  assert.strictEqual(
    helpers._bbStatusBadgeHtml('nonexistent', 'x'), '',
    'unknown section → empty string',
  );
  assert.strictEqual(
    helpers._bbStatusBadgeHtml('personal', 'nonexistent'), '',
    'unknown field → empty string',
  );
}

function testBadgeReturnsEmptyForEmptyStatus() {
  setMeta({ personal: { fullName: { status: 'empty', source: '' } } });
  assert.strictEqual(
    helpers._bbStatusBadgeHtml('personal', 'fullName'), '',
    'status=empty → no badge',
  );
}

function testBadgeReturnsEmptyWhenMetaMissing() {
  // Legacy-blob narrator — bb.questionnaire_meta is empty object.
  setMeta({});
  assert.strictEqual(helpers._bbStatusBadgeHtml('personal', 'fullName'), '');
  // Or even undefined — should not throw.
  _STUB_BB = { questionnaire: {} };
  assert.strictEqual(helpers._bbStatusBadgeHtml('personal', 'fullName'), '');
}

function testKnownFieldCountSums() {
  setMeta({
    personal: {
      fullName:      { status: 'operator_entered', source: 'operator' },
      dateOfBirth:   { status: 'approved',          source: 'operator' },
      placeOfBirth:  { status: 'extracted_needs_verify', source: 'extractor' },
      // NOT counted as known:
      preferredName: { status: 'anchored_asked_pending', source: 'anchored' },
      currentFaith:  { status: 'conflicted', source: 'extractor' },
      languagesAtHome: { status: 'empty', source: '' },
    },
  });
  assert.strictEqual(helpers._bbKnownFieldCount('personal'), 3);
}

function testKnownFieldCountIgnoresSectionRollupKey() {
  setMeta({
    siblings: {
      _section: { status: 'operator_entered', source: 'operator' },
    },
  });
  // _section is the section-level rollup, NOT a field — don't count it.
  assert.strictEqual(helpers._bbKnownFieldCount('siblings'), 0);
}

function testKnownPillRendersWithKnownFields() {
  setMeta({
    personal: {
      fullName: { status: 'operator_entered', source: 'operator' },
      dateOfBirth: { status: 'approved', source: 'operator' },
    },
  });
  const fakeSection = {
    id: 'personal',
    fields: [
      { id: 'fullName' }, { id: 'preferredName' },
      { id: 'dateOfBirth' }, { id: 'placeOfBirth' },
    ],
  };
  const html = helpers._bbKnownPillHtml(fakeSection);
  assert.ok(html.includes('bb-pill--known'), 'known pill class present');
  assert.ok(html.includes('2 already known'), 'count "2 already known" present');
  assert.ok(html.includes('2 still open'), 'open count "2 still open" present');
}

function testKnownPillReturnsEmptyForZeroKnown() {
  setMeta({});
  const fakeSection = { id: 'personal', fields: [{ id: 'fullName' }] };
  assert.strictEqual(helpers._bbKnownPillHtml(fakeSection), '');
}

function testKnownPillOmitsOpenLabelWhenAllKnown() {
  setMeta({
    today: {
      livingSituation:      { status: 'operator_entered', source: 'operator' },
      healthConsiderations: { status: 'operator_entered', source: 'operator' },
    },
  });
  const fakeSection = {
    id: 'today',
    fields: [{ id: 'livingSituation' }, { id: 'healthConsiderations' }],
  };
  const html = helpers._bbKnownPillHtml(fakeSection);
  assert.ok(html.includes('2 already known'));
  assert.ok(!html.includes('still open'),
    'when total == known, "still open" suffix omitted');
}

// ── Runner ────────────────────────────────────────────────────────

const tests = [
  ['status label table shape',         testStatusLabelTableShape],
  ['known status set mirrors server',  testKnownStatusSetMirrorsServer],
  ['badge renders operator_entered',   testBadgeRendersOperatorEntered],
  ['badge renders conflicted as red',  testBadgeRendersConflictedAsRed],
  ['badge empty for unknown section',  testBadgeReturnsEmptyForUnknownSection],
  ['badge empty for empty status',     testBadgeReturnsEmptyForEmptyStatus],
  ['badge empty when meta missing',    testBadgeReturnsEmptyWhenMetaMissing],
  ['known field count sums',           testKnownFieldCountSums],
  ['known field count ignores _section', testKnownFieldCountIgnoresSectionRollupKey],
  ['known pill renders with known fields', testKnownPillRendersWithKnownFields],
  ['known pill empty for zero known',  testKnownPillReturnsEmptyForZeroKnown],
  ['known pill omits open label when all known', testKnownPillOmitsOpenLabelWhenAllKnown],
];

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
    console.log('  ok  ' + name);
  } catch (e) {
    failed++;
    console.error('  FAIL ' + name);
    console.error('       ' + (e && e.message ? e.message : e));
  }
}

if (failed > 0) {
  console.error(`\n${failed} of ${tests.length} tests failed`);
  process.exit(1);
} else {
  console.log(`\n${tests.length} tests passed`);
}
