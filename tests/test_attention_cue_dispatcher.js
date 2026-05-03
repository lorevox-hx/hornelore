/* ═══════════════════════════════════════════════════════════════
   tests/test_attention_cue_dispatcher.js — Phase 3 unit tests

   Pure-Node tests for the attention-cue-dispatcher decision logic.
   No browser, no MediaPipe, no DOM. Run with:

     node tests/test_attention_cue_dispatcher.js

   Exit code 0 = all green. Non-zero = at least one failure.
   ═══════════════════════════════════════════════════════════════ */

'use strict';

const assert = require('assert');
const path = require('path');

const D = require(path.resolve(__dirname, '..', 'ui', 'js', 'attention-cue-dispatcher.js'));

// ── Test runner (tiny — no Mocha dependency) ──────────────────

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

// Anchor "now" for deterministic cooldown math
const NOW = 1_700_000_000_000;

// ── Hard-floor tests ──────────────────────────────────────────

test('hard floor: gap < 25s never fires, even on confirmed passive_waiting', () => {
  const r = D.decideCue({
    gap_ms: 24_999,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: null,
    last_cue_tier: null,
    now_ms: NOW,
  });
  assert.strictEqual(r, null);
});

test('hard floor: gap exactly 25s fires Tier 0 on passive_waiting', () => {
  const r = D.decideCue({
    gap_ms: 25_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: null,
    last_cue_tier: null,
    now_ms: NOW,
  });
  assert.ok(r);
  assert.strictEqual(r.tier, 0);
  assert.strictEqual(r.signal_state, 'passive_waiting');
  assert.strictEqual(r.intent, 'visual_only');  // Phase 3 lock — no TTS
});

// ── mic_activity suppression ──────────────────────────────────

test('mic activity always suppresses, regardless of gap or signal', () => {
  const r = D.decideCue({
    gap_ms: 600_000,
    attention_state: 'passive_waiting',
    mic_activity: true,
    now_ms: NOW,
  });
  assert.strictEqual(r, null);
});

test('mic activity suppresses tier-2 + tier-4 even with cooldown clear', () => {
  const cases = [
    { gap_ms: 130_000 },
    { gap_ms: 305_000 },
    { gap_ms: 700_000 },
  ];
  for (const c of cases) {
    const r = D.decideCue({
      ...c,
      attention_state: 'unknown',
      mic_activity: true,
      now_ms: NOW,
    });
    assert.strictEqual(r, null, 'gap_ms=' + c.gap_ms + ' should suppress under mic');
  }
});

// ── passive_waiting tier ladder ────────────────────────────────

test('passive_waiting: Tier 1 fires at >= 60s', () => {
  const r = D.decideCue({
    gap_ms: 60_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r.tier, 1);
  assert.strictEqual(r.intent, 'visual_only');  // Phase 3 lock — no TTS
});

test('passive_waiting: Tier 2 fires at >= 120s', () => {
  const r = D.decideCue({
    gap_ms: 120_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r.tier, 2);
  assert.strictEqual(r.intent, 'visual_only');  // Phase 3 lock — no TTS
});

test('passive_waiting: tier ladder boundary 59999 ms still Tier 0', () => {
  const r = D.decideCue({
    gap_ms: 59_999,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r.tier, 0);
});

// ── engaged / reflective veto ──────────────────────────────────

test('engaged narrator: no cue fires below WO-10C 120s mark', () => {
  for (const gap of [30_000, 60_000, 90_000, 119_999]) {
    const r = D.decideCue({
      gap_ms: gap,
      attention_state: 'engaged',
      mic_activity: false,
      now_ms: NOW,
    });
    assert.strictEqual(r, null, 'engaged @ ' + gap + 'ms should be vetoed');
  }
});

test('reflective narrator: no cue below 120s — survives intact past', () => {
  for (const gap of [30_000, 60_000, 90_000, 119_999]) {
    const r = D.decideCue({
      gap_ms: gap,
      attention_state: 'reflective',
      mic_activity: false,
      now_ms: NOW,
    });
    assert.strictEqual(r, null, 'reflective @ ' + gap + 'ms should be vetoed');
  }
});

test('engaged narrator: time-ladder Tier 2 fires at exactly 120s', () => {
  const r = D.decideCue({
    gap_ms: 120_000,
    attention_state: 'engaged',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.ok(r);
  assert.strictEqual(r.tier, 2);
  assert.strictEqual(r.signal_state, 'engaged');
});

// ── face_missing fallback ──────────────────────────────────────

test('face_missing: NOT treated as passive_waiting — falls to time ladder', () => {
  // Below 120s no time-ladder tier fires
  const early = D.decideCue({
    gap_ms: 60_000,
    attention_state: 'face_missing',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(early, null);

  // At 120s → Tier 2
  const t2 = D.decideCue({
    gap_ms: 120_000,
    attention_state: 'face_missing',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(t2.tier, 2);
  assert.strictEqual(t2.signal_state, 'face_missing');
});

test('face_missing at 600s fires Tier 4 break offer', () => {
  const r = D.decideCue({
    gap_ms: 600_000,
    attention_state: 'face_missing',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r.tier, 4);
});

// ── unknown / no-signal time ladder ────────────────────────────

test('unknown signal: nothing below 120s', () => {
  for (const gap of [25_000, 60_000, 90_000, 119_999]) {
    const r = D.decideCue({
      gap_ms: gap,
      attention_state: 'unknown',
      mic_activity: false,
      now_ms: NOW,
    });
    assert.strictEqual(r, null, 'unknown @ ' + gap + 'ms should NOT fire');
  }
});

test('unknown signal: Tier 2 at 120s, Tier 3 at 300s, Tier 4 at 600s', () => {
  const t2 = D.decideCue({ gap_ms: 120_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  const t3 = D.decideCue({ gap_ms: 300_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  const t4 = D.decideCue({ gap_ms: 600_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  assert.strictEqual(t2.tier, 2);
  assert.strictEqual(t3.tier, 3);
  assert.strictEqual(t4.tier, 4);
});

// ── Cooldown after spoken cue (Tier 1+) ───────────────────────

// Cooldown semantics — Phase 3 lock: only spoken cues trigger cooldown.
// In Phase 3 last_cue_intent is always 'visual_only' so cooldown is
// dead code by structural design. The Phase 5 lane will exercise the
// cooldown=spoken_cue branch when spoken intents are introduced.

test('cooldown: visual_only Tier 1 cue does NOT block new cue (Phase 3 lock)', () => {
  // Tier 1 fired 30s ago — but as visual_only, no cooldown.
  // This is the bug-fix: cooldown gating visual cues caused them
  // to fade out at gap=120s (60s safety auto-hide inside the
  // 90s cooldown window with no fresh dispatch events).
  const r = D.decideCue({
    gap_ms: 70_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 30_000,
    last_cue_tier: 1,
    last_cue_intent: 'visual_only',
    now_ms: NOW,
  });
  assert.ok(r, 'visual_only cue must NOT trigger cooldown');
  assert.strictEqual(r.tier, 1);
});

test('cooldown: visual_only Tier 2 cue does NOT block new cue (Phase 3 lock)', () => {
  const r = D.decideCue({
    gap_ms: 200_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 60_000,
    last_cue_tier: 2,
    last_cue_intent: 'visual_only',
    now_ms: NOW,
  });
  assert.ok(r);
  assert.strictEqual(r.tier, 2);
});

test('cooldown: spoken_cue blocks new cue for 90s (Phase 5 future lane)', () => {
  const r = D.decideCue({
    gap_ms: 70_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 30_000,
    last_cue_tier: 1,
    last_cue_intent: 'spoken_cue',
    now_ms: NOW,
  });
  assert.strictEqual(r, null);
});

test('cooldown: spoken_cue 90s elapsed → next cue allowed', () => {
  const r = D.decideCue({
    gap_ms: 70_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 90_001,
    last_cue_tier: 1,
    last_cue_intent: 'spoken_cue',
    now_ms: NOW,
  });
  assert.ok(r);
  assert.strictEqual(r.tier, 1);
});

test('cooldown: missing last_cue_intent → defaults to no cooldown', () => {
  // Defensive: legacy callers pre-Phase-3-fix passed no intent.
  // Default behavior: do NOT cooldown (visual cue persistence wins).
  const r = D.decideCue({
    gap_ms: 70_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 30_000,
    last_cue_tier: 1,
    // last_cue_intent omitted
    now_ms: NOW,
  });
  assert.ok(r);
});

test('cooldown: Tier 0 cue does NOT trigger cooldown (silent UI)', () => {
  const r = D.decideCue({
    gap_ms: 70_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 5_000,   // very recent
    last_cue_tier: 0,            // but Tier 0 is silent — no cooldown
    last_cue_intent: 'visual_only',
    now_ms: NOW,
  });
  assert.ok(r);
  assert.strictEqual(r.tier, 1);
});

// ── Long-silence fallback (Phase 3 spec table case 3) ──────────

test('long silence + any signal at gap >= 300s fires Tier 3', () => {
  const states = ['unknown', 'engaged', 'reflective', 'face_missing'];
  for (const s of states) {
    const r = D.decideCue({
      gap_ms: 300_000,
      attention_state: s,
      mic_activity: false,
      now_ms: NOW,
    });
    assert.ok(r, s + ' at 300s should fire');
    assert.strictEqual(r.tier, 3, s + ' should be Tier 3');
  }
});

test('long silence + any signal at gap >= 600s fires Tier 4 break offer', () => {
  const states = ['unknown', 'engaged', 'reflective', 'face_missing', 'passive_waiting'];
  for (const s of states) {
    const r = D.decideCue({
      gap_ms: 600_000,
      attention_state: s,
      mic_activity: false,
      now_ms: NOW,
    });
    assert.ok(r, s + ' at 600s should fire');
    if (s === 'passive_waiting') {
      // passive_waiting ladder caps at Tier 2 (120s+); the time ladder takes over only via 'unknown'/etc.
      assert.strictEqual(r.tier, 2, 'passive_waiting at 600s caps at Tier 2');
    } else {
      assert.strictEqual(r.tier, 4, s + ' at 600s should be Tier 4');
    }
  }
});

// ── Acceptance scenarios (mirror Phase 5 test matrix) ──────────

test('scenario: deep thinker (engaged) silent 90s → no cue (matrix row "Deep thinker, camera engaged")', () => {
  const r = D.decideCue({
    gap_ms: 90_000,
    attention_state: 'engaged',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r, null);
});

test('scenario: passive waiter silent 30s → Tier 0 (matrix row "Passive waiter")', () => {
  const r = D.decideCue({
    gap_ms: 30_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r.tier, 0);
  assert.strictEqual(r.intent, 'visual_only');  // Phase 3 lock — visual-only at all tiers
});

test('scenario: passive waiter silent 75s → Tier 1 (visual-only in Phase 3)', () => {
  const r = D.decideCue({
    gap_ms: 75_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.strictEqual(r.tier, 1);
  assert.strictEqual(r.intent, 'visual_only');  // Phase 3 lock — no TTS
});

test('scenario: camera off, no signal → time ladder unchanged', () => {
  // 120s = no-signal Tier 2; 300s = Tier 3; 600s = Tier 4
  const t120 = D.decideCue({ gap_ms: 120_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  const t300 = D.decideCue({ gap_ms: 300_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  const t600 = D.decideCue({ gap_ms: 600_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  assert.strictEqual(t120.tier, 2);
  assert.strictEqual(t300.tier, 3);
  assert.strictEqual(t600.tier, 4);
});

test('scenario: narrator starts speaking mid-decision → suppressed', () => {
  const r = D.decideCue({
    gap_ms: 200_000,                 // would otherwise fire
    attention_state: 'passive_waiting',
    mic_activity: true,              // but mic is hot
    now_ms: NOW,
  });
  assert.strictEqual(r, null);
});

test('scenario: cooldown — visual_only second cue NOT blocked (Phase 3)', () => {
  // Per Phase 3 lock: visual cues are persistent presence, not
  // interruptive. They never trigger cooldown. The matrix row's
  // original "second cue blocked within 90s" expectation only
  // applies to spoken cues which Phase 5 will introduce.
  const r = D.decideCue({
    gap_ms: 150_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    last_cue_ts: NOW - 60_000,   // Tier 1 fired 60s ago
    last_cue_tier: 1,
    last_cue_intent: 'visual_only',
    now_ms: NOW,
  });
  assert.ok(r, 'visual_only cue must continue; cooldown is for spoken cues');
});

// ── Output shape ──────────────────────────────────────────────

test('output contract: every non-null result has tier + signal_state + intent + reason + gap_ms', () => {
  const r = D.decideCue({
    gap_ms: 65_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  assert.ok('tier' in r);
  assert.ok('signal_state' in r);
  assert.ok('intent' in r);
  assert.ok('reason' in r);
  assert.ok('gap_ms' in r);
  assert.strictEqual(r.reason, 'attention_cue');
  assert.strictEqual(r.gap_ms, 65_000);
});

test('Phase 3 lock: ALL tiers have intent=visual_only (no TTS routing)', () => {
  const t0 = D.decideCue({ gap_ms: 30_000, attention_state: 'passive_waiting', mic_activity: false, now_ms: NOW });
  const t1 = D.decideCue({ gap_ms: 65_000, attention_state: 'passive_waiting', mic_activity: false, now_ms: NOW });
  const t2 = D.decideCue({ gap_ms: 130_000, attention_state: 'passive_waiting', mic_activity: false, now_ms: NOW });
  const t3 = D.decideCue({ gap_ms: 305_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  const t4 = D.decideCue({ gap_ms: 605_000, attention_state: 'unknown', mic_activity: false, now_ms: NOW });
  assert.strictEqual(t0.intent, 'visual_only');
  assert.strictEqual(t1.intent, 'visual_only');
  assert.strictEqual(t2.intent, 'visual_only');
  assert.strictEqual(t3.intent, 'visual_only');
  assert.strictEqual(t4.intent, 'visual_only');
});

test('Phase 3 lock: dispatcher MUST NOT emit any spoken intent vocabulary', () => {
  // No tier under any signal × gap combo may emit intent === 'attention_cue'
  // or 'spoken_cue' or 'tts'. Phase 3 is visual-only by structural lock.
  const states = D.VALID_ATTENTION_STATES;
  const gaps = [25_000, 30_000, 60_000, 90_000, 120_000, 200_000, 300_000, 600_000, 1_000_000];
  const banned_intents = ['attention_cue', 'spoken_cue', 'tts', 'speak', 'say'];
  for (const s of states) {
    for (const g of gaps) {
      const r = D.decideCue({ gap_ms: g, attention_state: s, mic_activity: false, now_ms: NOW });
      if (!r) continue;
      assert.strictEqual(r.intent, 'visual_only',
        'state=' + s + ' gap=' + g + ' must be visual_only, was ' + r.intent);
      assert.ok(banned_intents.indexOf(r.intent) === -1);
    }
  }
});

// ── formatLog smoke ────────────────────────────────────────────

test('formatLog: produces required reason/tier/signal_state/gap_ms fields', () => {
  const decision = D.decideCue({
    gap_ms: 65_000,
    attention_state: 'passive_waiting',
    mic_activity: false,
    now_ms: NOW,
  });
  const log = D.formatLog(decision);
  assert.ok(log.includes('reason=attention_cue'));
  assert.ok(log.includes('tier=1'));
  assert.ok(log.includes('signal_state=passive_waiting'));
  assert.ok(log.includes('gap_ms=65000'));
});

test('formatLog: returns null on null decision', () => {
  assert.strictEqual(D.formatLog(null), null);
});

// ── Defensive input handling ──────────────────────────────────

test('unknown attention string defaults to "unknown" — does not throw', () => {
  const r = D.decideCue({
    gap_ms: 130_000,
    attention_state: 'sleeping',  // not in vocabulary
    mic_activity: false,
    now_ms: NOW,
  });
  assert.ok(r);
  assert.strictEqual(r.signal_state, 'unknown');
});

test('null/undefined inputs do not throw', () => {
  assert.doesNotThrow(() => D.decideCue(null));
  assert.doesNotThrow(() => D.decideCue(undefined));
  assert.doesNotThrow(() => D.decideCue({}));
});

test('empty input → null (gap_ms defaults to 0, below floor)', () => {
  assert.strictEqual(D.decideCue({}), null);
});

// ── Ban check: no banned vocabulary in output ──────────────────

test('no banned vocabulary appears in any output reason/signal_state', () => {
  const banned = [
    'cognitive decline', 'mci', 'dementia', 'diagnostic', 'severity',
    'clinical signal', 'drift score', 'impairment', 'cdtd', 'decline detector',
  ];
  // Sweep every viable input combo and check output strings
  const states = D.VALID_ATTENTION_STATES;
  const gaps = [25_000, 60_000, 120_000, 300_000, 600_000];
  for (const s of states) {
    for (const g of gaps) {
      const r = D.decideCue({ gap_ms: g, attention_state: s, mic_activity: false, now_ms: NOW });
      if (!r) continue;
      const blob = JSON.stringify(r).toLowerCase();
      for (const term of banned) {
        assert.ok(!blob.includes(term),
          'banned term "' + term + '" appeared in output for state=' + s + ' gap=' + g);
      }
      const log = D.formatLog(r) || '';
      const lc = log.toLowerCase();
      for (const term of banned) {
        assert.ok(!lc.includes(term),
          'banned term "' + term + '" appeared in log line');
      }
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
    console.log('\n  FAIL: ' + f.name);
    console.log('    ' + f.message);
  }
  process.exit(1);
}
