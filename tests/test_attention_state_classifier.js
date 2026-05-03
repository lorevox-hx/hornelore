/* ═══════════════════════════════════════════════════════════════
   tests/test_attention_state_classifier.js — Phase 3A unit tests

   Tests the 5-state classifier (Phase 3C harness cases per Chris's
   restructure: passive_waiting only on all-four; engaged veto;
   reflective veto; face_missing ≠ passive_waiting; mic-activity
   false-positive guard; no cue before 25s floor).

   Run:  node tests/test_attention_state_classifier.js
   ═══════════════════════════════════════════════════════════════ */

'use strict';

const assert = require('assert');
const path = require('path');

const C = require(path.resolve(__dirname, '..', 'ui', 'js', 'attention-state-classifier.js'));

let _passed = 0;
let _failed = 0;
const _failures = [];

function test(name, fn) {
  try {
    fn();
    _passed += 1;
    process.stdout.write('.');
  } catch (err) {
    _failed += 1;
    _failures.push({ name, message: err.message });
    process.stdout.write('F');
  }
}

const ALL_FOUR_PASSIVE_AT_FLOOR = {
  gaze_forward: true,
  low_movement: true,
  no_speech_intent: true,
  post_tts_silence_ms: 25_000,
  affect_state: null,
  face_present: true,
};

// ── Phase 3C harness case 1: passive_waiting only on all-four ─

test('all four inputs true + at floor → passive_waiting', () => {
  const r = C.classify(ALL_FOUR_PASSIVE_AT_FLOOR);
  assert.strictEqual(r, 'passive_waiting');
});

test('all four inputs true + above floor → passive_waiting', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, post_tts_silence_ms: 60_000 });
  assert.strictEqual(r, 'passive_waiting');
});

test('all four inputs true BUT post_tts below 25s → unknown (not passive_waiting)', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, post_tts_silence_ms: 24_999 });
  assert.strictEqual(r, 'unknown');
});

test('only 3 of 4 inputs true → unknown (not passive_waiting)', () => {
  const cases = [
    { gaze_forward: false }, { gaze_forward: null }, { gaze_forward: undefined },
    { low_movement: false }, { low_movement: null },
    { no_speech_intent: false }, { no_speech_intent: null },
  ];
  for (const c of cases) {
    const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, ...c });
    assert.strictEqual(r, 'unknown',
      'inputs missing one true: ' + JSON.stringify(c));
  }
});

// ── Phase 3C case 2: engaged veto ─────────────────────────────

test('affect_state=engaged → engaged label (overrides four-input passive_waiting)', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, affect_state: 'engaged' });
  assert.strictEqual(r, 'engaged');
});

// ── Phase 3C case 3: reflective veto ──────────────────────────

test('affect_state=reflective → reflective label', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, affect_state: 'reflective' });
  assert.strictEqual(r, 'reflective');
});

test('affect_state=moved → reflective label (moved is reflective-class)', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, affect_state: 'moved' });
  assert.strictEqual(r, 'reflective');
});

// ── Phase 3C case 4: face_missing ≠ passive_waiting ───────────

test('face_present=false → face_missing (overrides everything else)', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, face_present: false });
  assert.strictEqual(r, 'face_missing');
});

test('face_present=null → falls through (no positive face signal)', () => {
  // null face is "no camera at all"; doesn't override the rest of the pipeline
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, face_present: null });
  assert.strictEqual(r, 'passive_waiting');
});

// ── Phase 3C case 5: mic-activity false-positive guard ────────
//
// The classifier itself doesn't take mic_activity (the dispatcher
// suppresses on mic). But it should NOT promote "no speech intent
// = false" into a different label — it should just stay 'unknown'.

test('no_speech_intent=false (narrator IS shaping a word) → unknown', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, no_speech_intent: false });
  assert.strictEqual(r, 'unknown');
});

// ── Phase 3C case 6: no cue before WO-10C 120s fallback mark ──
//
// Classifier emits labels; dispatcher enforces the 120s veto floor
// for engaged/reflective. Verify the labels are emitted regardless
// of post_tts_silence so the operator harness can see them.

test('engaged emitted at 30s gap (dispatcher will veto, classifier just labels)', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, post_tts_silence_ms: 30_000, affect_state: 'engaged' });
  assert.strictEqual(r, 'engaged');
});

test('reflective emitted at 30s gap', () => {
  const r = C.classify({ ...ALL_FOUR_PASSIVE_AT_FLOOR, post_tts_silence_ms: 30_000, affect_state: 'reflective' });
  assert.strictEqual(r, 'reflective');
});

// ── Defensive input handling ──────────────────────────────────

test('null inputs do not throw', () => {
  assert.doesNotThrow(() => C.classify(null));
  assert.doesNotThrow(() => C.classify(undefined));
  assert.doesNotThrow(() => C.classify({}));
});

test('empty input → unknown', () => {
  assert.strictEqual(C.classify({}), 'unknown');
});

test('missing post_tts_silence_ms defaults to 0 (below floor)', () => {
  const r = C.classify({
    gaze_forward: true,
    low_movement: true,
    no_speech_intent: true,
    affect_state: null,
    face_present: true,
  });
  assert.strictEqual(r, 'unknown');
});

// ── classifyWithTrace ─────────────────────────────────────────

test('classifyWithTrace returns decision + inputs + thresholds', () => {
  const r = C.classifyWithTrace(ALL_FOUR_PASSIVE_AT_FLOOR);
  assert.strictEqual(r.decision, 'passive_waiting');
  assert.strictEqual(r.inputs.gaze_forward, true);
  assert.strictEqual(r.inputs.post_tts_silence_ms, 25_000);
  assert.strictEqual(r.thresholds.hard_floor_ms, 25_000);
  assert.strictEqual(r.thresholds.wo_10c_floor_ms, 120_000);
});

// ── Vocabulary ────────────────────────────────────────────────

test('VALID_STATES contains exactly 5 vocabulary entries', () => {
  assert.strictEqual(C.VALID_STATES.length, 5);
  for (const s of ['passive_waiting','engaged','reflective','face_missing','unknown']) {
    assert.ok(C.VALID_STATES.indexOf(s) !== -1, s + ' should be in vocabulary');
  }
});

test('every classify output is a member of VALID_STATES', () => {
  // Cartesian sweep of a meaningful input space
  const valid = new Set(C.VALID_STATES);
  const bools = [true, false, null];
  const affects = ['engaged', 'reflective', 'moved', 'steady', 'distressed', 'overwhelmed', null];
  const faces = [true, false, null];
  const gaps = [0, 25_000, 60_000, 120_000];
  let count = 0;
  for (const g of bools) {
    for (const m of bools) {
      for (const s of bools) {
        for (const a of affects) {
          for (const f of faces) {
            for (const sec of gaps) {
              const r = C.classify({
                gaze_forward: g, low_movement: m, no_speech_intent: s,
                affect_state: a, face_present: f, post_tts_silence_ms: sec,
              });
              count += 1;
              assert.ok(valid.has(r), 'unexpected label "' + r + '"');
            }
          }
        }
      }
    }
  }
  assert.ok(count > 1500, 'sweep covered > 1500 combos, got ' + count);
});

// ── Banned vocabulary ─────────────────────────────────────────

test('no banned vocabulary in any output label', () => {
  const banned = [
    'cognitive', 'decline', 'mci', 'dementia', 'diagnostic',
    'severity', 'clinical', 'drift', 'impairment', 'cdtd',
  ];
  for (const s of C.VALID_STATES) {
    const lc = s.toLowerCase();
    for (const term of banned) {
      assert.ok(!lc.includes(term), 'banned "' + term + '" in label "' + s + '"');
    }
  }
});

// ── Final summary ─────────────────────────────────────────────

console.log('\n');
if (_failed === 0) {
  console.log('✓ ' + _passed + ' tests passed');
  process.exit(0);
} else {
  console.log('✗ ' + _failed + ' failed, ' + _passed + ' passed');
  for (const f of _failures) {
    console.log('\n  FAIL: ' + f.name + '\n    ' + f.message);
  }
  process.exit(1);
}
