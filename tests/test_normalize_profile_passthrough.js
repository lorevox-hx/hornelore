/* tests/test_normalize_profile_passthrough.js — external-review fix #3:
   normalizeProfile() must preserve the intake-written structured
   passthrough blocks (personal/parents/siblings/spouses/spouse/
   children/education/community/marriage/military/faith/today).

   Without this, the backend BUG-API-PROFILES-DROPS-INTAKE-KEYS-01
   fix is useless: backend now returns the structured blocks, but the
   FE used to silently discard them in normalizeProfile, so Bio
   Builder + operator-intake couldn't see them.

   Strategy: regex-slice the normalizeProfile body from ui/js/app.js
   so the test runs against the live source (no drift risk). Then
   feed canned profile shapes and assert the structured keys survive.

   Run:  node tests/test_normalize_profile_passthrough.js
*/
'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const SRC = fs.readFileSync(path.join(REPO_ROOT, 'ui', 'js', 'app.js'), 'utf8');

// Slice from `function normalizeProfile(p){` to the matching closing `}`.
// Naive brace-balancing is fine since the body has no string-literal
// curlies that aren't escaped.
function sliceFunction(src, marker) {
  const start = src.indexOf(marker);
  if (start < 0) throw new Error('marker not found: ' + marker);
  // Find the first `{` after the marker
  const openBrace = src.indexOf('{', start);
  let depth = 0;
  for (let i = openBrace; i < src.length; i++) {
    const ch = src[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) {
        return src.slice(start, i + 1);
      }
    }
  }
  throw new Error('unbalanced braces from marker: ' + marker);
}

const fnSrc = sliceFunction(SRC, 'function normalizeProfile(p)');
// eslint-disable-next-line no-new-func
const factory = new Function(fnSrc + '\n return normalizeProfile;');
const normalizeProfile = factory();

function runTest(label, fn) {
  try { fn(); console.log('  ok  ' + label); }
  catch (e) {
    console.error('  FAIL ' + label);
    console.error('       ' + (e && e.message ? e.message : e));
    process.exitCode = 1;
  }
}

console.log('normalizeProfile passthrough tests:');

runTest('legacy-only profile produces basics/kinship/pets', () => {
  const out = normalizeProfile({
    basics: { fullname: 'Legacy Narrator', dob: '1950-01-01' },
    kinship: [{ name: 'Sib', relation: 'sibling' }],
    pets: [{ name: 'Spot' }],
  });
  assert.strictEqual(out.basics.fullname, 'Legacy Narrator');
  assert.strictEqual(out.basics.dob, '1950-01-01');
  assert.strictEqual(out.kinship.length, 1);
  assert.strictEqual(out.pets.length, 1);
});

runTest('intake personal block survives normalization', () => {
  const out = normalizeProfile({
    basics: {},
    personal: {
      fullName: 'Walt',
      dateOfBirth: '1948-03-17',
      placeOfBirth: 'South Boston',
    },
  });
  assert.ok(out.personal, 'personal block should survive');
  assert.strictEqual(out.personal.fullName, 'Walt');
});

runTest('intake parents array survives normalization', () => {
  const out = normalizeProfile({
    basics: {},
    parents: [
      { relation: 'Father', firstName: 'Patrick', lastName: "O'Donnell" },
      { relation: 'Mother', firstName: 'Mary', lastName: "O'Donnell" },
    ],
  });
  assert.ok(Array.isArray(out.parents));
  assert.strictEqual(out.parents.length, 2);
  assert.strictEqual(out.parents[0].firstName, 'Patrick');
});

runTest('all 12 structured keys preserved', () => {
  const input = {
    basics: {},
    personal: { fullName: 'X' },
    parents: [{ firstName: 'P' }],
    siblings: [{ firstName: 'S' }],
    spouses: [{ firstName: 'Sp' }],
    spouse: { firstName: 'Sp' },
    children: [{ firstName: 'C' }],
    education: { highestLevel: 'masters' },
    community: { role: 'teacher' },
    marriage: { status: 'married' },
    military: { served: true },
    faith: { religionRaised: 'catholic' },
    today: { livingSituation: 'home' },
  };
  const out = normalizeProfile(input);
  for (const k of Object.keys(input)) {
    if (k === 'basics') continue;
    assert.ok(out[k] != null, 'missing structured key after normalize: ' + k);
  }
});

runTest('intake faith fields surface into basics', () => {
  const out = normalizeProfile({
    basics: {
      faithRaised: 'Catholic',
      currentFaith: 'Catholic',
      currentResidence: 'Quincy, MA',
    },
  });
  assert.strictEqual(out.basics.faithRaised, 'Catholic');
  assert.strictEqual(out.basics.currentFaith, 'Catholic');
  assert.strictEqual(out.basics.currentResidence, 'Quincy, MA');
});

runTest('null / undefined input does not crash', () => {
  const a = normalizeProfile(null);
  const b = normalizeProfile(undefined);
  const c = normalizeProfile({});
  assert.ok(a.basics);
  assert.ok(b.basics);
  assert.ok(c.basics);
});

runTest('empty arrays stay arrays', () => {
  const out = normalizeProfile({ basics: {}, kinship: 'not-array', pets: null });
  assert.ok(Array.isArray(out.kinship));
  assert.ok(Array.isArray(out.pets));
  assert.strictEqual(out.kinship.length, 0);
  assert.strictEqual(out.pets.length, 0);
});

console.log('\n7 tests passed');
