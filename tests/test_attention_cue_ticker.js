/* ═══════════════════════════════════════════════════════════════
   tests/test_attention_cue_ticker.js — Phase 3 ticker tests

   Pure-Node tests for the ticker glue. Synthesizes a minimal
   `window`-like global so the IIFE in attention-cue-ticker.js
   loads and exposes its API.

   Run:
     node tests/test_attention_cue_ticker.js
   ═══════════════════════════════════════════════════════════════ */

'use strict';

const assert = require('assert');
const path = require('path');
const fs = require('fs');

// ── Fake browser-ish global ───────────────────────────────────
// The ticker IIFE attaches to `window`. Node's `global` works since
// we set `LV_ATTENTION_CUE_TICKER` to false (default-OFF) so the
// auto-start path is suppressed during test load.

global.LV_ATTENTION_CUE_TICKER = false;
global.window = global;

const _events = [];
global.dispatchEvent = function (evt) {
  _events.push({ type: evt.type, detail: evt.detail });
  return true;
};
global.CustomEvent = function (type, init) {
  return { type, detail: (init && init.detail) || null };
};

// Fake document with no listeners — short-circuits DOMContentLoaded path.
global.document = {
  readyState: 'complete',
  addEventListener: function () { /* no-op */ },
};

// Load dispatcher + classifier + ticker (IIFEs attach to global)
require(path.resolve(__dirname, '..', 'ui', 'js', 'attention-cue-dispatcher.js'));
require(path.resolve(__dirname, '..', 'ui', 'js', 'attention-state-classifier.js'));
require(path.resolve(__dirname, '..', 'ui', 'js', 'attention-cue-ticker.js'));

const D = global.AttentionCueDispatcher;
const C = global.AttentionStateClassifier;
const T = global.AttentionCueTicker;

assert.ok(D, 'AttentionCueDispatcher should load');
assert.ok(C, 'AttentionStateClassifier should load');
assert.ok(T, 'AttentionCueTicker should load');

// ── Tiny test runner ──────────────────────────────────────────

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
    _failures.push({ name, message: err.message, stack: err.stack });
    process.stdout.write('F');
  }
}

function resetState() {
  global.state = {
    session: {},
    inputState: { micActive: false, micPaused: false, cameraActive: false, cameraConsent: false },
    narratorTurn: { state: 'idle', ttsFinishedAt: null },
  };
  _events.length = 0;
}

const NOW_FIXED = 1_700_000_000_000;
const _origDateNow = Date.now;
function freezeNow(ms) {
  Date.now = function () { return ms; };
}
function restoreNow() {
  Date.now = _origDateNow;
}

// ── Attention surface initialization ──────────────────────────

test('ensureAttentionSurface initializes with safe defaults', () => {
  resetState();
  T.ensureAttentionSurface();
  assert.strictEqual(global.state.session.attention_state, 'unknown');
  assert.strictEqual(global.state.session.last_seen_ms, 0);
  assert.ok(global.state.session.passive_waiting_inputs);
  assert.ok(global.state.session.lastAttentionCue);
});

test('ensureAttentionSurface is idempotent — does not clobber existing state', () => {
  resetState();
  global.state.session.attention_state = 'engaged';
  T.ensureAttentionSurface();
  assert.strictEqual(global.state.session.attention_state, 'engaged');
});

// ── setAttentionState ─────────────────────────────────────────

test('setAttentionState accepts valid vocabulary', () => {
  resetState();
  for (const s of D.VALID_ATTENTION_STATES) {
    const ok = T.setAttentionState(s);
    assert.strictEqual(ok, true, 'should accept ' + s);
    assert.strictEqual(global.state.session.attention_state, s);
  }
});

test('setAttentionState rejects unknown values, defaults to "unknown"', () => {
  resetState();
  const ok = T.setAttentionState('drift');
  assert.strictEqual(ok, false);
  assert.strictEqual(global.state.session.attention_state, 'unknown');
});

// ── snapshot() ────────────────────────────────────────────────

test('snapshot reads gap_ms from narratorTurn.ttsFinishedAt', () => {
  resetState();
  freezeNow(NOW_FIXED);
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 70_000;
  const snap = T.snapshot();
  assert.strictEqual(snap.gap_ms, 70_000);
  restoreNow();
});

test('snapshot reads mic_activity from inputState', () => {
  resetState();
  freezeNow(NOW_FIXED);
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 30_000;
  global.state.inputState.micActive = true;
  global.state.inputState.micPaused = false;
  const snap = T.snapshot();
  assert.strictEqual(snap.mic_activity, true);

  global.state.inputState.micPaused = true;
  const snap2 = T.snapshot();
  assert.strictEqual(snap2.mic_activity, false, 'paused mic does not count as active');

  restoreNow();
});

test('snapshot defaults attention_state to "unknown"', () => {
  resetState();
  freezeNow(NOW_FIXED);
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 10_000;
  const snap = T.snapshot();
  assert.strictEqual(snap.attention_state, 'unknown');
  restoreNow();
});

test('snapshot reads last_cue_ts + last_cue_tier from session.lastAttentionCue', () => {
  resetState();
  freezeNow(NOW_FIXED);
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 200_000;
  global.state.session.lastAttentionCue = { ts: NOW_FIXED - 30_000, tier: 1 };
  const snap = T.snapshot();
  assert.strictEqual(snap.last_cue_ts, NOW_FIXED - 30_000);
  assert.strictEqual(snap.last_cue_tier, 1);
  restoreNow();
});

// ── tick() ────────────────────────────────────────────────────

test('tick: when ttsFinishedAt is null, NO event fires', () => {
  resetState();
  T.tick();
  assert.strictEqual(_events.length, 0);
});

test('tick: passive_waiting + 65s gap fires lvAttentionCue Tier 1', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 65_000;
  T.setAttentionState('passive_waiting');
  T.tick();
  assert.strictEqual(_events.length, 1);
  assert.strictEqual(_events[0].type, 'lvAttentionCue');
  assert.strictEqual(_events[0].detail.tier, 1);
  assert.strictEqual(_events[0].detail.signal_state, 'passive_waiting');
  restoreNow();
});

test('tick: writes lastAttentionCue to session after firing', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 130_000;
  T.setAttentionState('passive_waiting');
  T.tick();
  assert.strictEqual(global.state.session.lastAttentionCue.tier, 2);
  assert.strictEqual(global.state.session.lastAttentionCue.signal_state, 'passive_waiting');
  assert.strictEqual(global.state.session.lastAttentionCue.ts, NOW_FIXED);
  restoreNow();
});

test('tick: cooldown after Tier 1 fires — second tick within 90s fires nothing', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 65_000;
  T.setAttentionState('passive_waiting');
  T.tick();
  assert.strictEqual(_events.length, 1);

  // Advance 30s, gap continues
  freezeNow(NOW_FIXED + 30_000);
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 65_000;  // unchanged
  T.tick();
  assert.strictEqual(_events.length, 1, 'no second event during cooldown');
  restoreNow();
});

test('tick: mic_activity true → no event (matrix row "narrator starts speaking")', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 200_000;
  T.setAttentionState('passive_waiting');
  global.state.inputState.micActive = true;
  T.tick();
  assert.strictEqual(_events.length, 0);
  restoreNow();
});

test('tick: gap below 25s hard floor → no event', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 24_000;
  T.setAttentionState('passive_waiting');
  T.tick();
  assert.strictEqual(_events.length, 0);
  restoreNow();
});

test('tick: unknown signal at 120s → fires Tier 2 (time ladder)', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 120_000;
  // attention_state stays at default 'unknown'
  T.tick();
  assert.strictEqual(_events.length, 1);
  assert.strictEqual(_events[0].detail.tier, 2);
  assert.strictEqual(_events[0].detail.signal_state, 'unknown');
  restoreNow();
});

test('tick: engaged narrator at 90s → no event (WO-10C veto)', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 90_000;
  T.setAttentionState('engaged');
  T.tick();
  assert.strictEqual(_events.length, 0);
  restoreNow();
});

test('tick: engaged narrator at 600s → fires Tier 4', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 600_000;
  T.setAttentionState('engaged');
  T.tick();
  assert.strictEqual(_events.length, 1);
  assert.strictEqual(_events[0].detail.tier, 4);
  restoreNow();
});

// ── markNarratorActivity ──────────────────────────────────────

test('markNarratorActivity bumps last_seen_ms', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  T.markNarratorActivity();
  assert.strictEqual(global.state.session.last_seen_ms, NOW_FIXED);
  restoreNow();
});

// ── lifecycle: start / stop / isRunning ───────────────────────

test('isRunning is false before start, true after start, false after stop', () => {
  assert.strictEqual(T.isRunning(), false);
  T.start();
  assert.strictEqual(T.isRunning(), true);
  T.stop();
  assert.strictEqual(T.isRunning(), false);
});

test('start is idempotent — calling twice does not duplicate timer', () => {
  T.start();
  T.start();  // second call is no-op
  assert.strictEqual(T.isRunning(), true);
  T.stop();
});

// ── Phase 3B classifier auto-refresh ──────────────────────────

test('Phase 3B: passive_waiting_inputs all-true + 65s gap → classifier sets passive_waiting → cue fires Tier 1', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 65_000;
  global.state.session.passive_waiting_inputs = {
    gaze_forward: true,
    low_movement: true,
    no_speech_intent: true,
    post_tts_silence_ms: 65_000,
  };
  T.tick();
  assert.strictEqual(global.state.session.attention_state, 'passive_waiting',
    'classifier should write passive_waiting');
  assert.strictEqual(_events[0].detail.signal_state, 'passive_waiting');
  assert.strictEqual(_events[0].detail.tier, 1);
  restoreNow();
});

test('Phase 3B: visualSignals.affectState=engaged → classifier sets engaged → veto under 120s', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 90_000;
  global.state.session.visualSignals = {
    affectState: 'engaged',
    confidence: 0.85,
    timestamp: NOW_FIXED,
  };
  T.tick();
  assert.strictEqual(global.state.session.attention_state, 'engaged');
  assert.strictEqual(_events.length, 0, 'engaged @ 90s must be vetoed');
  restoreNow();
});

test('Phase 3B: no inputs + no affect → classifier preserves explicitly-set value', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 65_000;
  T.setAttentionState('passive_waiting');  // manual override
  // No passive_waiting_inputs values set → classifier should NOT clobber
  T.tick();
  assert.strictEqual(global.state.session.attention_state, 'passive_waiting',
    'manual override must survive when no sensor inputs are populated');
  assert.strictEqual(_events[0].detail.tier, 1);
  restoreNow();
});

test('Phase 3B: emitted events always carry intent=visual_only (Phase 3 lock)', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - 130_000;
  global.state.session.passive_waiting_inputs = {
    gaze_forward: true, low_movement: true, no_speech_intent: true,
    post_tts_silence_ms: 130_000,
  };
  T.tick();
  assert.strictEqual(_events.length, 1);
  assert.strictEqual(_events[0].detail.intent, 'visual_only');
  restoreNow();
});

// ── Banned-vocabulary sweep on the wire format ────────────────

test('no banned vocabulary in dispatched events', () => {
  resetState();
  freezeNow(NOW_FIXED);
  T.ensureAttentionSurface();
  const banned = [
    'cognitive decline', 'mci', 'dementia', 'diagnostic',
    'severity', 'clinical signal', 'drift score', 'impairment',
    'cdtd', 'decline detector',
  ];
  // Sweep all reachable signal states + tier ranges
  const states = D.VALID_ATTENTION_STATES;
  const gaps = [25_000, 60_000, 120_000, 300_000, 600_000];
  for (const s of states) {
    for (const g of gaps) {
      _events.length = 0;
      global.state.session.lastAttentionCue = { ts: null, tier: null };
      global.state.narratorTurn.ttsFinishedAt = NOW_FIXED - g;
      T.setAttentionState(s);
      T.tick();
      for (const evt of _events) {
        const blob = JSON.stringify(evt).toLowerCase();
        for (const term of banned) {
          assert.ok(!blob.includes(term),
            'banned "' + term + '" surfaced in event for state=' + s + ' gap=' + g);
        }
      }
    }
  }
  restoreNow();
});

// ── Final summary ────────────────────────────────────────────

console.log('\n');
if (_failed === 0) {
  console.log('✓ ' + _passed + ' tests passed');
  process.exit(0);
} else {
  console.log('✗ ' + _failed + ' failed, ' + _passed + ' passed');
  for (const f of _failures) {
    console.log('\n  FAIL: ' + f.name);
    console.log('    ' + f.message);
  }
  process.exit(1);
}
