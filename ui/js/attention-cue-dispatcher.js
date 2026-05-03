/* ═══════════════════════════════════════════════════════════════
   attention-cue-dispatcher.js — WO-LORI-SESSION-AWARENESS-01 Phase 3

   Decides WHEN Lori should fire a soft attention cue and WHAT TIER
   that cue should be. Pure decision logic — does not produce speech,
   does not write to state, does not call MediaPipe. Consumers wire
   the inputs and act on the output.

   Inputs (caller-supplied; dispatcher owns no timers, no MediaPipe):
     gap_ms              ms since lori_turn_end_ts
     attention_state     'passive_waiting' | 'engaged' | 'reflective' |
                         'face_missing' | 'unknown'
     mic_activity        bool — narrator is currently speaking (any sound)
     last_cue_ts         ms timestamp of the last spoken cue (Tier 1+)
                         OR null if no cue this session
     last_cue_tier       int 0-4 of last cue OR null

   Output:
     null                — no cue right now
     { tier, signal_state, intent, reason, gap_ms }
                         — fire this cue

   Tier ladder (spec §Phase 3):
     0  passive_waiting + gap >=  25s   → silent presence (UI indicator)
     1  passive_waiting + gap >=  60s   → affirmation, not question
     2  passive_waiting + gap >= 120s   → soft offer
     3  any signal      + gap >= 300s   → warmer re-entry, concrete prompt
     4  any signal      + gap >= 600s   → offer break

   Hard rules (cannot violate):
     - HARD_FLOOR_MS = 25s. No cue fires before this, ever.
     - 90s cooldown after Tier 1+ cue.
     - 'engaged' / 'reflective' veto cues below WO-10C 120s mark.
     - 'face_missing' is NOT 'passive_waiting' — fall to time ladder.
     - mic_activity suppresses any pending cue.

   This module has no banned-vocabulary terms. All output framings
   are rhythm/pace/listener vocabulary per WO §Banned vocabulary.
   ═══════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  // ── Time constants (ms) ───────────────────────────────────────
  const HARD_FLOOR_MS    =  25 * 1000;
  const TIER_1_MIN_MS    =  60 * 1000;
  const TIER_2_MIN_MS    = 120 * 1000;
  const TIER_3_MIN_MS    = 300 * 1000;
  const TIER_4_MIN_MS    = 600 * 1000;
  const COOLDOWN_MS      =  90 * 1000;
  const WO_10C_FLOOR_MS  = 120 * 1000;

  const VALID_ATTENTION = new Set([
    'passive_waiting',
    'engaged',
    'reflective',
    'face_missing',
    'unknown',
  ]);

  // ── Decision helpers ───────────────────────────────────────────

  function _normalizeAttention(state) {
    if (!state) return 'unknown';
    if (VALID_ATTENTION.has(state)) return state;
    return 'unknown';
  }

  function _cooldownActive(now_ms, last_cue_ts, last_cue_tier) {
    if (!last_cue_ts || last_cue_tier == null) return false;
    if (last_cue_tier < 1) return false;  // Tier 0 is silent UI; no cooldown
    return (now_ms - last_cue_ts) < COOLDOWN_MS;
  }

  function _passiveWaitingTier(gap_ms) {
    if (gap_ms >= TIER_2_MIN_MS) return 2;
    if (gap_ms >= TIER_1_MIN_MS) return 1;
    if (gap_ms >= HARD_FLOOR_MS) return 0;
    return null;
  }

  function _timeLadderTier(gap_ms) {
    // Fallback when MediaPipe state is 'unknown' or 'face_missing'.
    // Mirrors WO-10C 120s/300s/600s ladder.
    if (gap_ms >= TIER_4_MIN_MS) return 4;
    if (gap_ms >= TIER_3_MIN_MS) return 3;
    if (gap_ms >= TIER_2_MIN_MS) return 2;
    return null;
  }

  function _intentForTier(tier) {
    // PHASE 3 LOCK — all tiers route to visual-only surface.
    //
    // Per Chris's restructure (2026-05-03): Phase 3 must NOT make Lori
    // speak more. The Phase 5 test matrix is the gate that may later
    // flip tiers 1-4 to a spoken intent. Until then:
    //   - Tier 0 → silent UI presence pulse (visual)
    //   - Tier 1-4 → quiet presence cue text shown on screen, never TTS
    // The downstream consumer (presence-cue.js) reads intent ===
    // 'visual_only' and renders the cue. Any consumer reading
    // 'attention_cue' / 'spoken_cue' MUST refuse to fire in Phase 3.
    void tier;
    return 'visual_only';
  }

  // ── Public API ─────────────────────────────────────────────────

  /**
   * Decide whether to fire a cue right now and at what tier.
   * Pure function: no side effects, no timer reads, no DOM access.
   *
   * @param {Object} inputs
   * @param {number} inputs.gap_ms          ms since Lori finished speaking
   * @param {string} inputs.attention_state passive_waiting|engaged|reflective|face_missing|unknown
   * @param {boolean} inputs.mic_activity   narrator currently speaking
   * @param {number|null} inputs.last_cue_ts  ms timestamp of last cue, or null
   * @param {number|null} inputs.last_cue_tier  int tier of last cue, or null
   * @param {number} [inputs.now_ms]        current time in ms (default: Date.now())
   * @returns {Object|null}  { tier, signal_state, intent, reason, gap_ms } or null
   */
  function decideCue(inputs) {
    inputs = inputs || {};
    const gap_ms          = Number(inputs.gap_ms || 0);
    const attention_state = _normalizeAttention(inputs.attention_state);
    const mic_activity    = !!inputs.mic_activity;
    const last_cue_ts     = inputs.last_cue_ts || null;
    const last_cue_tier   = (inputs.last_cue_tier != null) ? Number(inputs.last_cue_tier) : null;
    const now_ms          = Number(inputs.now_ms || Date.now());

    // Rule 1: narrator is speaking — never interrupt.
    if (mic_activity) {
      return null;
    }

    // Rule 2: hard floor — first 25s belong to the narrator no matter what.
    if (gap_ms < HARD_FLOOR_MS) {
      return null;
    }

    // Rule 3: cooldown after a spoken cue.
    if (_cooldownActive(now_ms, last_cue_ts, last_cue_tier)) {
      return null;
    }

    // Rule 4: veto — engaged/reflective narrators get the long ladder.
    // The visual signal can only ACCELERATE a cue when it positively
    // confirms passive waiting; uncertainty (engaged/reflective)
    // defaults to the no-signal 120s mark.
    if ((attention_state === 'engaged' || attention_state === 'reflective')
        && gap_ms < WO_10C_FLOOR_MS) {
      return null;
    }

    // Rule 5: face_missing is its own state — narrator stepped away.
    // Not 'passive waiting'. Fall to time ladder.
    if (attention_state === 'face_missing') {
      const tier = _timeLadderTier(gap_ms);
      if (tier == null) return null;
      return {
        tier,
        signal_state: 'face_missing',
        intent: _intentForTier(tier),
        reason: 'attention_cue',
        gap_ms,
      };
    }

    // Rule 6: positively-confirmed passive_waiting — fast ladder.
    if (attention_state === 'passive_waiting') {
      const tier = _passiveWaitingTier(gap_ms);
      if (tier == null) return null;
      return {
        tier,
        signal_state: 'passive_waiting',
        intent: _intentForTier(tier),
        reason: 'attention_cue',
        gap_ms,
      };
    }

    // Rule 7: unknown / engaged / reflective at gap >= 120s — time ladder.
    // (engaged/reflective survive past the WO-10C 120s veto floor and
    //  enter the time ladder at tier 2.)
    const tier = _timeLadderTier(gap_ms);
    if (tier == null) return null;
    return {
      tier,
      signal_state: attention_state,
      intent: _intentForTier(tier),
      reason: 'attention_cue',
      gap_ms,
    };
  }

  /**
   * Format a log line for [attention-cue] consumption per spec
   * (Phase 3: "every cue logged with reason=attention_cue + tier=N
   *  + signal_state=passive_waiting + gap_ms=N").
   */
  function formatLog(decision) {
    if (!decision) return null;
    return '[attention-cue] reason=' + decision.reason
      + ' tier=' + decision.tier
      + ' signal_state=' + decision.signal_state
      + ' gap_ms=' + decision.gap_ms;
  }

  // ── Module export (browser + Node) ────────────────────────────

  const AttentionCueDispatcher = {
    decideCue,
    formatLog,
    // Constants exposed for tests + downstream consumers.
    HARD_FLOOR_MS,
    TIER_1_MIN_MS,
    TIER_2_MIN_MS,
    TIER_3_MIN_MS,
    TIER_4_MIN_MS,
    COOLDOWN_MS,
    WO_10C_FLOOR_MS,
    VALID_ATTENTION_STATES: Array.from(VALID_ATTENTION),
  };

  // Browser global
  global.AttentionCueDispatcher = AttentionCueDispatcher;

  // CommonJS for Node-side tests
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AttentionCueDispatcher;
  }

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
