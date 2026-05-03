/* ═══════════════════════════════════════════════════════════════
   tests/test_presence_cue.js — Phase 3E unit tests

   Lock the never-spoken / never-transcript / never-extractor
   guarantees. Lightweight DOM stub so we don't pull jsdom.

   Run:  node tests/test_presence_cue.js
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
    this._listeners = {};
    this._parent = null;
    this._classes = new Set();
    const _self = this;
    this.classList = {
      add(...names) { for (const n of names) _self._classes.add(n); },
      remove(...names) { for (const n of names) _self._classes.delete(n); },
      contains(n) { return _self._classes.has(n); },
      toggle(n) {
        if (_self._classes.has(n)) { _self._classes.delete(n); return false; }
        _self._classes.add(n); return true;
      },
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
  addEventListener(t, fn) {
    (this._listeners[t] = this._listeners[t] || []).push(fn);
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

// Capture lvAttentionCue listeners on window
const _windowListeners = {};
global.addEventListener = function (t, fn) {
  (_windowListeners[t] = _windowListeners[t] || []).push(fn);
};
global.dispatchEvent = function (evt) {
  const ls = _windowListeners[evt.type] || [];
  for (const fn of ls) fn(evt);
  return true;
};
global.CustomEvent = function (type, init) {
  return { type, detail: (init && init.detail) || null };
};

// Patch FakeElement.appendChild to register elements with id
const _origAppend = FakeElement.prototype.appendChild;
FakeElement.prototype.appendChild = function (c) {
  _origAppend.call(this, c);
  if (c.id) _allElements[c.id] = c;
  return c;
};

// ── Load module under test ────────────────────────────────────

const P = require(path.resolve(__dirname, '..', 'ui', 'js', 'presence-cue.js'));

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
    _failures.push({ name, message: err.message });
    process.stdout.write('F');
  }
}

function fireCue(decision) {
  global.dispatchEvent({ type: 'lvAttentionCue', detail: decision });
}

// ── Mount & defaults ──────────────────────────────────────────

test('init creates the mount element with required attrs', () => {
  P.init();
  const el = global.document.getElementById('lvPresenceCue');
  assert.ok(el, 'mount element should exist');
  assert.strictEqual(el.attributes['role'], 'status');
  assert.strictEqual(el.attributes['aria-live'], 'polite');
  assert.strictEqual(el.dataset.purpose, 'visual_presence');
  assert.strictEqual(el.dataset.transcriptIgnore, 'true');
});

test('initial cue text matches the locked wording', () => {
  const el = global.document.getElementById('lvPresenceCue');
  assert.strictEqual(el.textContent, "Take your time. I'm listening.");
  assert.strictEqual(P.CUE_TEXT, "Take your time. I'm listening.");
});

test('mount starts hidden (opacity 0, aria-hidden true)', () => {
  P.hide();  // ensure clean state
  const el = global.document.getElementById('lvPresenceCue');
  assert.strictEqual(el.style.opacity, '0');
  assert.strictEqual(el.getAttribute('aria-hidden'), 'true');
});

// ── Phase 3 structural lock ───────────────────────────────────

test('lvAttentionCue with intent=visual_only → cue shows', () => {
  P.hide();
  fireCue({ tier: 1, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 65000 });
  assert.strictEqual(P.isShown(), true);
});

test('lvAttentionCue with intent=attention_cue (spoken) → cue does NOT show', () => {
  P.hide();
  fireCue({ tier: 1, signal_state: 'passive_waiting', intent: 'attention_cue', reason: 'attention_cue', gap_ms: 65000 });
  assert.strictEqual(P.isShown(), false, 'spoken intent must never surface as visual cue');
});

test('lvAttentionCue with intent=spoken_cue → cue does NOT show', () => {
  P.hide();
  fireCue({ tier: 2, signal_state: 'passive_waiting', intent: 'spoken_cue', reason: 'attention_cue', gap_ms: 130000 });
  assert.strictEqual(P.isShown(), false);
});

test('lvAttentionCue with intent=tts → cue does NOT show', () => {
  P.hide();
  fireCue({ tier: 3, signal_state: 'unknown', intent: 'tts', reason: 'attention_cue', gap_ms: 305000 });
  assert.strictEqual(P.isShown(), false);
});

test('null event detail → cue hides', () => {
  P.show();
  assert.strictEqual(P.isShown(), true);
  fireCue(null);
  assert.strictEqual(P.isShown(), false);
});

test('Tier 0 with visual_only → cue shows (silent presence pulse)', () => {
  P.hide();
  fireCue({ tier: 0, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 25000 });
  assert.strictEqual(P.isShown(), true);
});

// ── Phase 3E two-stage opacity ramp ───────────────────────────

test('Tier 0 at gap_ms=30s → faint stage class', () => {
  P.hide();
  fireCue({ tier: 0, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 30_000 });
  const el = global.document.getElementById('lvPresenceCue');
  assert.ok(el.classList.contains('lv-presence-faint'), 'should be faint at 30s');
  assert.ok(!el.classList.contains('lv-presence-stronger'), 'should NOT be stronger at 30s');
});

test('Tier 0 at gap_ms=44s → still faint (just below 45s threshold)', () => {
  P.hide();
  fireCue({ tier: 0, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 44_000 });
  const el = global.document.getElementById('lvPresenceCue');
  assert.ok(el.classList.contains('lv-presence-faint'));
  assert.ok(!el.classList.contains('lv-presence-stronger'));
});

test('Tier 0 at gap_ms=45s → stronger stage class (boundary)', () => {
  P.hide();
  fireCue({ tier: 0, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 45_000 });
  const el = global.document.getElementById('lvPresenceCue');
  assert.ok(el.classList.contains('lv-presence-stronger'), 'should be stronger at 45s boundary');
  assert.ok(!el.classList.contains('lv-presence-faint'), 'faint must be removed when promoted to stronger');
});

test('Tier 1 at gap_ms=65s → stronger stage class', () => {
  P.hide();
  fireCue({ tier: 1, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 65_000 });
  const el = global.document.getElementById('lvPresenceCue');
  assert.ok(el.classList.contains('lv-presence-stronger'));
  assert.ok(!el.classList.contains('lv-presence-faint'));
});

test('promote-then-demote: stage class swaps cleanly across cues', () => {
  P.hide();
  fireCue({ tier: 1, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 65_000 });
  const el = global.document.getElementById('lvPresenceCue');
  assert.ok(el.classList.contains('lv-presence-stronger'));
  // Subsequent cue at lower gap_ms (e.g., new turn just started)
  fireCue({ tier: 0, signal_state: 'passive_waiting', intent: 'visual_only', reason: 'attention_cue', gap_ms: 28_000 });
  assert.ok(el.classList.contains('lv-presence-faint'));
  assert.ok(!el.classList.contains('lv-presence-stronger'));
});

// ── Mic-activity hide ─────────────────────────────────────────

test('onMicActivity hides the cue immediately', () => {
  P.show();
  assert.strictEqual(P.isShown(), true);
  P.onMicActivity();
  assert.strictEqual(P.isShown(), false);
});

// ── Never-spoken / never-transcript / never-extractor markers ─

test('mount carries data-transcript-ignore=true (transcript filters skip it)', () => {
  const el = global.document.getElementById('lvPresenceCue');
  assert.strictEqual(el.dataset.transcriptIgnore, 'true');
});

test('mount carries data-purpose=visual_presence (TTS-side never reads it)', () => {
  const el = global.document.getElementById('lvPresenceCue');
  assert.strictEqual(el.dataset.purpose, 'visual_presence');
});

test('cue text is the only narrator-visible content (no system status language)', () => {
  // No "API", "offline", "undefined", "system", etc. — per WO-10C
  const banned = [
    'api', 'offline', 'undefined', 'are you still there',
    'please respond', 'system', 'error', 'i notice you',
    'cognitive', 'dementia',
  ];
  const lc = P.CUE_TEXT.toLowerCase();
  for (const term of banned) {
    assert.ok(!lc.includes(term), 'banned phrase "' + term + '" in cue text');
  }
});

// ── Defensive ─────────────────────────────────────────────────

test('multiple init calls are idempotent (single mount)', () => {
  P.init();
  P.init();
  P.init();
  let count = 0;
  for (const c of fakeBody.children) {
    if (c.id === 'lvPresenceCue') count += 1;
  }
  // Walk the whole tree just in case it was placed deeper
  function _walk(node, acc) {
    if (node.id === 'lvPresenceCue') acc.n += 1;
    for (const k of node.children) _walk(k, acc);
  }
  const acc = { n: 0 };
  _walk(fakeBody, acc);
  assert.ok(acc.n === 1, 'should have exactly one mount, got ' + acc.n);
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
