/* ═══════════════════════════════════════════════════════════════
   tests/test_lori_since_timer.js — Lane H regression coverage

   Pure-Node tests for the Countdown Timer (lori-since-timer.js).
   Covers:
     - mm:ss formatter boundary cases
     - tier classifier across all 7 boundary points
     - mic-active state transition (narrator speaking → reset)
     - Lori-speaking state transition (ttsFinishedAt null → reset)
     - DOM mount idempotency
     - "Countdown Timer" label locked
     - banned-vocabulary sweep on tier labels

   Same harness pattern as test_presence_cue.js. Minimal DOM stub
   so we don't pull jsdom.

   Run:  node tests/test_lori_since_timer.js
   ═══════════════════════════════════════════════════════════════ */

'use strict';

const assert = require('assert');
const path = require('path');

// ── Minimal DOM stub ──────────────────────────────────────────

class FakeElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.id = '';
    this.className = '';
    this.style = {};
    this.attributes = {};
    this.dataset = {};
    this.children = [];
    this.textContent = '';
    this._innerHTML = '';
    this._parent = null;
    this._classes = new Set();
    const _self = this;
    this.classList = {
      add(...names) { for (const n of names) _self._classes.add(n); },
      remove(...names) { for (const n of names) _self._classes.delete(n); },
      contains(n) { return _self._classes.has(n); },
    };
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k]; }
  appendChild(c) { this.children.push(c); c._parent = this; return c; }
  contains(c) {
    if (c === this) return true;
    for (const k of this.children) if (k.contains(c)) return true;
    return false;
  }
  set innerHTML(html) {
    // Cheap parser for the timer's three nested divs (eyebrow / elapsed / tier).
    this._innerHTML = html;
    this.children = [];
    const m = html.match(/<div class="lv-since-eyebrow">([^<]*)<\/div>\s*<div class="lv-since-elapsed" data-since-slot="elapsed">([^<]*)<\/div>\s*<div class="lv-since-tier" data-since-slot="tier">([^<]*)<\/div>/);
    if (m) {
      const eyebrow = new FakeElement('div');
      eyebrow.className = 'lv-since-eyebrow';
      eyebrow.textContent = m[1];
      this.children.push(eyebrow);

      const elapsed = new FakeElement('div');
      elapsed.className = 'lv-since-elapsed';
      elapsed.textContent = m[2];
      elapsed.attributes['data-since-slot'] = 'elapsed';
      this.children.push(elapsed);

      const tier = new FakeElement('div');
      tier.className = 'lv-since-tier';
      tier.textContent = m[3];
      tier.attributes['data-since-slot'] = 'tier';
      this.children.push(tier);
    }
  }
  get innerHTML() { return this._innerHTML; }
  querySelector(sel) {
    // Very limited — supports '[data-since-slot="elapsed"]' and tier
    if (sel === '[data-since-slot="elapsed"]') {
      return this.children.find(c => c.attributes['data-since-slot'] === 'elapsed') || null;
    }
    if (sel === '[data-since-slot="tier"]') {
      return this.children.find(c => c.attributes['data-since-slot'] === 'tier') || null;
    }
    return null;
  }
}

const _allElements = {};
const fakeBody = new FakeElement('body');

global.document = {
  readyState: 'complete',
  body: fakeBody,
  createElement(tag) { return new FakeElement(tag); },
  getElementById(id) { return _allElements[id] || null; },
  addEventListener() {},
};

const _origAppend = FakeElement.prototype.appendChild;
FakeElement.prototype.appendChild = function (c) {
  _origAppend.call(this, c);
  if (c.id) _allElements[c.id] = c;
  return c;
};

// Mount target the timer looks for (#lvNarratorConversation)
const narratorContainer = new FakeElement('div');
narratorContainer.id = 'lvNarratorConversation';
fakeBody.appendChild(narratorContainer);

// ── Load module under test ────────────────────────────────────

const T = require(path.resolve(__dirname, '..', 'ui', 'js', 'lori-since-timer.js'));

// ── Tiny test runner ──────────────────────────────────────────

let _passed = 0, _failed = 0;
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

const NOW = 1_700_000_000_000;
const _origDateNow = Date.now;
function freezeNow(ms) { Date.now = function () { return ms; }; }
function restoreNow() { Date.now = _origDateNow; }

function setupState({
  ttsFinishedAt = null,
  loriStreamStartedAt = null,
  micActive = false,
  micPaused = false,
  attention_state = 'unknown',
} = {}) {
  global.state = {
    session: { attention_state, visualSignals: null, lastAttentionCue: null },
    inputState: { micActive, micPaused, cameraActive: false, cameraConsent: false },
    narratorTurn: { state: 'idle', ttsFinishedAt, loriStreamStartedAt },
  };
}

function getElapsed() {
  const el = global.document.getElementById('lvSinceTimer');
  if (!el) return null;
  return el.querySelector('[data-since-slot="elapsed"]').textContent;
}

function getTier() {
  const el = global.document.getElementById('lvSinceTimer');
  if (!el) return null;
  return el.querySelector('[data-since-slot="tier"]').textContent;
}

function hasClass(name) {
  const el = global.document.getElementById('lvSinceTimer');
  return el ? el.classList.contains(name) : false;
}

// ── Mount + label ─────────────────────────────────────────────

test('mount creates lvSinceTimer element with required attrs', () => {
  setupState();
  T.refresh();
  const el = global.document.getElementById('lvSinceTimer');
  assert.ok(el, 'mount element should exist');
  assert.strictEqual(el.attributes['aria-hidden'], 'true');
  assert.strictEqual(el.dataset.purpose, 'operator_observability');
});

test('label is locked to "Countdown" (Lane H Chris spec, 2026-05-03)', () => {
  // Label shortened from "Countdown Timer" → "Countdown" so it fits
  // adjacent to Send button without crowding the textarea.
  const el = global.document.getElementById('lvSinceTimer');
  const eyebrow = el.children.find(c => c.className === 'lv-since-eyebrow');
  assert.strictEqual(eyebrow.textContent, 'Countdown');
});

// ── mm:ss formatter ──────────────────────────────────────────

test('mm:ss format: 0s → 00:00', () => {
  setupState({ ttsFinishedAt: NOW });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:00');
  restoreNow();
});

test('mm:ss format: 24s → 00:24 (under hard floor, "thinking room")', () => {
  setupState({ ttsFinishedAt: NOW - 24_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:24');
  assert.strictEqual(getTier(), 'thinking room (under 25s)');
  restoreNow();
});

test('mm:ss format: 25s boundary → 00:25 + "faint cue" tier', () => {
  setupState({ ttsFinishedAt: NOW - 25_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:25');
  assert.strictEqual(getTier(), 'faint cue (25–45s)');
  assert.ok(hasClass('lv-since-t0'));
  restoreNow();
});

test('mm:ss format: 44s → still faint (under 45s threshold)', () => {
  setupState({ ttsFinishedAt: NOW - 44_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:44');
  assert.strictEqual(getTier(), 'faint cue (25–45s)');
  restoreNow();
});

test('mm:ss format: 45s boundary → "stronger cue" tier', () => {
  setupState({ ttsFinishedAt: NOW - 45_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:45');
  assert.strictEqual(getTier(), 'stronger cue (45s+)');
  assert.ok(hasClass('lv-since-t0-strong'));
  restoreNow();
});

test('mm:ss format: 60s → 01:00 + T1 spoken-cue zone', () => {
  setupState({ ttsFinishedAt: NOW - 60_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '01:00');
  assert.strictEqual(getTier(), 'T1 spoken-cue zone (60s+)');
  assert.ok(hasClass('lv-since-t1'));
  restoreNow();
});

test('mm:ss format: 120s → 02:00 + T2 soft-offer', () => {
  setupState({ ttsFinishedAt: NOW - 120_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '02:00');
  assert.strictEqual(getTier(), 'T2 soft-offer zone (2m+)');
  assert.ok(hasClass('lv-since-t2'));
  restoreNow();
});

test('mm:ss format: 5m → 05:00 + T3 re-entry', () => {
  setupState({ ttsFinishedAt: NOW - 300_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '05:00');
  assert.strictEqual(getTier(), 'T3 re-entry zone (5m+)');
  assert.ok(hasClass('lv-since-t3'));
  restoreNow();
});

test('mm:ss format: 10m → 10:00 + T4 break-offer', () => {
  setupState({ ttsFinishedAt: NOW - 600_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '10:00');
  assert.strictEqual(getTier(), 'T4 break-offer zone (10m+)');
  assert.ok(hasClass('lv-since-t4'));
  restoreNow();
});

test('mm:ss format: 99m cap → 99:00 (no overflow display)', () => {
  setupState({ ttsFinishedAt: NOW - 99 * 60 * 1000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '99:00');
  restoreNow();
});

test('mm:ss format: 200m → still capped at 99:xx (display safety)', () => {
  setupState({ ttsFinishedAt: NOW - 200 * 60 * 1000 });
  freezeNow(NOW);
  T.refresh();
  // m caps to 99, s is the modulo of total — accept any 99:NN
  assert.match(getElapsed(), /^99:\d{2}$/);
  restoreNow();
});

// ── Reset triggers ────────────────────────────────────────────

test('no anchor at all (boot / post-send-pre-stream) → 00:00 + "waiting for Lori"', () => {
  setupState({ ttsFinishedAt: null, loriStreamStartedAt: null });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:00');
  assert.strictEqual(getTier(), 'waiting for Lori');
  assert.ok(hasClass('lv-since-speaking'));
  restoreNow();
});

test('narrator mic active → 00:00 + "narrator speaking"', () => {
  setupState({ ttsFinishedAt: NOW - 65_000, micActive: true });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:00');
  assert.strictEqual(getTier(), 'narrator speaking');
  assert.ok(hasClass('lv-since-mic-active'));
  // Should NOT show the underlying tier class while mic is active
  assert.ok(!hasClass('lv-since-t1'));
  restoreNow();
});

test('mic paused → does NOT trigger mic-active reset (paused mic is silent)', () => {
  setupState({ ttsFinishedAt: NOW - 65_000, micActive: true, micPaused: true });
  freezeNow(NOW);
  T.refresh();
  // micPaused means narrator is NOT speaking — countdown should run normally
  assert.strictEqual(getElapsed(), '01:05');
  assert.ok(hasClass('lv-since-t1'));
  assert.ok(!hasClass('lv-since-mic-active'));
  restoreNow();
});

test('mic activity → narrator speaks → mic releases → countdown resumes', () => {
  // Phase 1: 30s into silence
  setupState({ ttsFinishedAt: NOW - 30_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:30');
  assert.ok(hasClass('lv-since-t0'));

  // Phase 2: narrator starts talking — countdown resets visually
  global.state.inputState.micActive = true;
  T.refresh();
  assert.strictEqual(getElapsed(), '00:00');
  assert.ok(hasClass('lv-since-mic-active'));

  // Phase 3: narrator finishes, mic releases — should resume from
  // the underlying ttsFinishedAt (which is unchanged in this test;
  // in real flow Lori would respond + reset ttsFinishedAt).
  global.state.inputState.micActive = false;
  T.refresh();
  assert.strictEqual(getElapsed(), '00:30');  // back to where we were
  assert.ok(hasClass('lv-since-t0'));

  restoreNow();
});

// ── Anchor priority (Lane H 2026-05-03) ───────────────────────

test('loriStreamStartedAt is the PRIMARY anchor (preferred over ttsFinishedAt)', () => {
  // Chris's spec: "start as soon as Lori types the first word, not
  // after she is done typing and actually speaking." So when both
  // anchors are set, the FIRST-TOKEN anchor wins.
  setupState({
    ttsFinishedAt:        NOW - 10_000,   // TTS finished 10s ago
    loriStreamStartedAt:  NOW - 40_000,   // Lori started talking 40s ago
  });
  freezeNow(NOW);
  T.refresh();
  // 40s should win → "faint cue (25–45s)"
  assert.strictEqual(getElapsed(), '00:40');
  assert.strictEqual(getTier(), 'faint cue (25–45s)');
  restoreNow();
});

test('loriStreamStartedAt alone (TTS path absent) drives the count', () => {
  setupState({ loriStreamStartedAt: NOW - 75_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '01:15');
  assert.strictEqual(getTier(), 'T1 spoken-cue zone (60s+)');
  assert.ok(hasClass('lv-since-t1'));
  restoreNow();
});

test('ttsFinishedAt fallback still works when loriStreamStartedAt is null', () => {
  // Backward compat: legacy stacks (or test harnesses) that only
  // set ttsFinishedAt should still get a working countdown.
  setupState({ ttsFinishedAt: NOW - 30_000, loriStreamStartedAt: null });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:30');
  assert.strictEqual(getTier(), 'faint cue (25–45s)');
  restoreNow();
});

test('clearing loriStreamStartedAt (send pressed) → "waiting for Lori"', () => {
  // Phase 1: Lori talking, 30s in.
  setupState({ loriStreamStartedAt: NOW - 30_000 });
  freezeNow(NOW);
  T.refresh();
  assert.strictEqual(getElapsed(), '00:30');

  // Phase 2: narrator hits Send → sendUserMessage clears the anchor.
  global.state.narratorTurn.loriStreamStartedAt = null;
  global.state.narratorTurn.ttsFinishedAt = null;
  T.refresh();
  assert.strictEqual(getElapsed(), '00:00');
  assert.strictEqual(getTier(), 'waiting for Lori');
  restoreNow();
});

// ── Stage class swap (no class accumulation) ──────────────────

test('stage classes do NOT accumulate across refreshes', () => {
  setupState({ ttsFinishedAt: NOW - 30_000 });  // T0 faint
  freezeNow(NOW);
  T.refresh();
  assert.ok(hasClass('lv-since-t0'));

  // Promote to T1
  global.state.narratorTurn.ttsFinishedAt = NOW - 65_000;
  T.refresh();
  assert.ok(hasClass('lv-since-t1'));
  assert.ok(!hasClass('lv-since-t0'), 'old t0 class should be removed');

  // Demote back to T0 (e.g., new turn started + immediately paused)
  global.state.narratorTurn.ttsFinishedAt = NOW - 30_000;
  T.refresh();
  assert.ok(hasClass('lv-since-t0'));
  assert.ok(!hasClass('lv-since-t1'), 'old t1 class should be removed');

  restoreNow();
});

// ── Attention state suffix ────────────────────────────────────

test('attention_state suffix appears when not "unknown"', () => {
  setupState({ ttsFinishedAt: NOW - 30_000, attention_state: 'passive_waiting' });
  freezeNow(NOW);
  T.refresh();
  const tier = getTier();
  assert.ok(tier.includes('passive_waiting'), 'tier label should include attention_state suffix');
  assert.ok(tier.includes('faint cue'), 'tier label should also include the cue range');
  restoreNow();
});

test('attention_state "unknown" → no suffix in tier label', () => {
  setupState({ ttsFinishedAt: NOW - 30_000, attention_state: 'unknown' });
  freezeNow(NOW);
  T.refresh();
  const tier = getTier();
  assert.ok(!tier.includes('unknown'), 'unknown should not surface in tier label');
  restoreNow();
});

// ── Banned-vocabulary sweep ───────────────────────────────────

test('no banned vocabulary in tier labels (across all gap ranges)', () => {
  const banned = [
    'cognitive decline', 'mci', 'dementia', 'diagnostic',
    'severity', 'clinical', 'drift score', 'impairment',
    'cdtd', 'decline detector',
  ];
  freezeNow(NOW);
  // Sample every 10s from 0 to 15min
  for (let s = 0; s <= 900; s += 10) {
    setupState({ ttsFinishedAt: NOW - s * 1000 });
    T.refresh();
    const tier = (getTier() || '').toLowerCase();
    for (const bad of banned) {
      assert.ok(!tier.includes(bad),
        `banned "${bad}" appeared in tier label "${tier}" at gap=${s}s`);
    }
  }
  restoreNow();
});

// ── Mount idempotency ─────────────────────────────────────────

test('multiple refresh calls do NOT create duplicate mounts', () => {
  setupState({ ttsFinishedAt: NOW - 30_000 });
  freezeNow(NOW);
  T.refresh();
  T.refresh();
  T.refresh();
  // Walk the body to count lvSinceTimer instances
  let count = 0;
  function _walk(node) {
    if (node.id === 'lvSinceTimer') count += 1;
    for (const k of node.children) _walk(k);
  }
  _walk(fakeBody);
  assert.strictEqual(count, 1, 'should have exactly one lvSinceTimer mount');
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
    console.log('\n  FAIL: ' + f.name + '\n    ' + f.message);
  }
  process.exit(1);
}
