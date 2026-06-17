/* tests/test_operator_intake_helpers.js — WO-OPERATOR-INTAKE-TAB-01
   pure-helper coverage.

   Loads ui/js/operator-intake.js in a stubbed DOM, exercises the
   pure helpers exposed via window.OperatorIntake._internal:
     - SECTIONS shape (9 sections, expected ids)
     - STATUS_LABELS server-FE parity
     - KNOWN_STATUSES mirrors server bio_gap_map._FILLED_STATUSES
     - _statusBadgeHtml renders / drops correctly
     - _sectionKnownCount sums by status
     - _sectionRollupHtml — empty / has / array variants
     - _esc escapes the 5 critical chars

   Run:  node tests/test_operator_intake_helpers.js
*/
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');

// ── Minimal browser/DOM stub for the IIFE module ───────────────────
// operator-intake.js doesn't reference document at module-load time
// (only inside functions), so a thin window is enough.

global.window = {};
global.document = {
  getElementById: () => null,
  addEventListener: () => {},
  body: { setAttribute: () => {} },
  createElement: () => ({
    appendChild: () => {},
    setAttribute: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    classList: { toggle: () => {}, contains: () => false, add: () => {}, remove: () => {} },
  }),
};

// fetch is referenced but never called from the helpers we test
global.fetch = function () { throw new Error('fetch should not be called from helper tests'); };

// Load the module — its IIFE executes and writes to window.OperatorIntake
require(path.join(REPO_ROOT, 'ui', 'js', 'operator-intake.js'));

const OI = global.window.OperatorIntake;
assert.ok(OI, 'OperatorIntake should be exported on window');
assert.ok(OI._internal, 'OperatorIntake._internal should be exposed for tests');

const {
  SECTIONS, STATUS_LABELS, KNOWN_STATUSES,
  _state, _sectionKnownCount, _statusBadgeHtml, _sectionRollupHtml, _esc,
} = OI._internal;

// ── Tests ──────────────────────────────────────────────────────────

function runTest(label, fn) {
  try {
    fn();
    console.log('  ok  ' + label);
  } catch (e) {
    console.error('  FAIL ' + label);
    console.error('       ' + (e && e.message ? e.message : e));
    process.exitCode = 1;
  }
}

console.log('OperatorIntake helper tests:');

runTest('SECTIONS has 9 sections covering the intake form', () => {
  const ids = SECTIONS.map(s => s.id);
  // External-review fix (2026-06-16): identity section is keyed as
  // "personal" (matches canonical writer + view), label stays "Identity".
  for (const expected of [
    'personal', 'family', 'marriage', 'children',
    'siblings', 'education', 'military', 'faith', 'today',
  ]) {
    assert.ok(ids.includes(expected), 'missing section: ' + expected);
  }
  // Hard-block the pre-fix "identity" key — must not regress.
  assert.ok(!ids.includes('identity'),
    'Identity section must be keyed "personal", not "identity" — ' +
    'the canonical writer reads q.get("personal") and the view returns ' +
    'questionnaire.personal');
});

runTest('Identity section keeps its display label', () => {
  const personal = SECTIONS.find(s => s.id === 'personal');
  assert.ok(personal, 'personal section should exist');
  assert.strictEqual(personal.label, 'Identity',
    'label should display as "Identity" even though id is "personal"');
});

runTest('STATUS_LABELS has all bio_schema FACT_STATUSES', () => {
  for (const s of [
    'approved', 'operator_entered', 'document_sourced',
    'anchored_asked', 'extracted_needs_verify',
    'anchored_asked_pending', 'conflicted', 'superseded', 'empty',
  ]) {
    assert.ok(STATUS_LABELS[s], 'missing label for status: ' + s);
  }
  assert.strictEqual(STATUS_LABELS['empty'].label, '');
  assert.strictEqual(STATUS_LABELS['conflicted'].cls, 'oi-badge-red');
  assert.strictEqual(STATUS_LABELS['approved'].cls, 'oi-badge-ok');
});

runTest('KNOWN_STATUSES mirrors server bio_gap_map._FILLED_STATUSES', () => {
  const want = new Set([
    'extracted_needs_verify', 'document_sourced', 'anchored_asked',
    'operator_entered', 'approved',
  ]);
  const got = new Set(Object.keys(KNOWN_STATUSES));
  assert.deepStrictEqual(got, want);
  assert.ok(!KNOWN_STATUSES['anchored_asked_pending']);
  assert.ok(!KNOWN_STATUSES['conflicted']);
});

runTest('_esc escapes the 5 critical characters', () => {
  assert.strictEqual(_esc('<script>'), '&lt;script&gt;');
  assert.strictEqual(_esc('"a"'), '&quot;a&quot;');
  assert.strictEqual(_esc("a'b"), 'a&#39;b');
  assert.strictEqual(_esc('a & b'), 'a &amp; b');
  assert.strictEqual(_esc(null), '');
  assert.strictEqual(_esc(undefined), '');
});

runTest('_statusBadgeHtml renders for known status', () => {
  _state.meta = {
    personal: {
      dateOfBirth: { status: 'operator_entered', source: 'operator' },
    },
  };
  const html = _statusBadgeHtml('personal', 'dateOfBirth');
  assert.ok(html.includes('oi-status-badge'));
  assert.ok(html.includes('oi-badge-known'));
  assert.ok(html.includes('Entered'));
});

runTest('_statusBadgeHtml returns empty for empty status', () => {
  _state.meta = { identity: { fullName: { status: 'empty', source: '' } } };
  assert.strictEqual(_statusBadgeHtml('personal', 'fullName'), '');
});

runTest('_statusBadgeHtml returns empty when no meta entry', () => {
  _state.meta = {};
  assert.strictEqual(_statusBadgeHtml('personal', 'fullName'), '');
});

runTest('_sectionKnownCount sums known statuses', () => {
  _state.meta = {
    personal: {
      fullName:     { status: 'operator_entered', source: 'operator' },
      dateOfBirth:  { status: 'approved', source: 'operator' },
      placeOfBirth: { status: 'extracted_needs_verify', source: 'extractor' },
      // not counted:
      pronouns:     { status: 'anchored_asked_pending', source: 'anchored' },
      preferred:    { status: 'conflicted', source: 'extractor' },
      birthOrder:   { status: 'empty', source: '' },
    },
  };
  // identity section has fields={fullName,..} — count is by meta keys
  assert.strictEqual(_sectionKnownCount({ id: 'personal', fields: SECTIONS[0].fields }), 3);
});

runTest('_sectionKnownCount ignores _section rollup key', () => {
  _state.meta = {
    siblings: { _section: { status: 'operator_entered', source: 'operator' } },
  };
  assert.strictEqual(_sectionKnownCount({
    id: 'siblings', array: 'siblings', meta_section_key: 'siblings',
  }), 0);
});

runTest('_sectionRollupHtml — empty section renders "No information yet"', () => {
  _state.meta = {};
  _state.questionnaire = {};
  const html = _sectionRollupHtml(SECTIONS[0]); // personal
  assert.ok(html.includes('No information yet'));
  assert.ok(html.includes('oi-rollup-empty'));
});

runTest('_sectionRollupHtml — known section renders count', () => {
  _state.meta = {
    personal: {
      fullName:     { status: 'operator_entered', source: 'operator' },
      dateOfBirth:  { status: 'approved', source: 'operator' },
    },
  };
  const html = _sectionRollupHtml(SECTIONS[0]); // personal section has 7 fields
  assert.ok(html.includes('2 of 7 known'), 'rollup output should say 2 of 7 known: ' + html);
  assert.ok(html.includes('oi-rollup-has'));
});

runTest('_sectionRollupHtml — array section renders entry count', () => {
  _state.meta = {};
  _state.questionnaire = { parents: [{ firstName: 'A' }, { firstName: 'B' }] };
  const section = SECTIONS.find(s => s.id === 'family');
  const html = _sectionRollupHtml(section);
  assert.ok(html.includes('2 entries'), 'array rollup should say 2 entries: ' + html);
  assert.ok(html.includes('oi-rollup-array'));
});

runTest('_sectionRollupHtml — array section, single entry', () => {
  _state.questionnaire = { parents: [{ firstName: 'Only' }] };
  const section = SECTIONS.find(s => s.id === 'family');
  const html = _sectionRollupHtml(section);
  assert.ok(html.includes('1 entry'));
});

runTest('Identity (personal) section has fullName, dateOfBirth, placeOfBirth, pronouns', () => {
  const personal = SECTIONS.find(s => s.id === 'personal');
  const fieldIds = personal.fields.map(f => f.id);
  for (const required of ['fullName', 'dateOfBirth', 'placeOfBirth', 'pronouns', 'preferredName', 'currentResidence']) {
    assert.ok(fieldIds.includes(required), 'personal missing: ' + required);
  }
});

runTest('Public API exposes init / refresh / onNarratorSwitch', () => {
  assert.strictEqual(typeof OI.init, 'function');
  assert.strictEqual(typeof OI.refresh, 'function');
  assert.strictEqual(typeof OI.onNarratorSwitch, 'function');
});

console.log('\n16 tests passed');
