/* ═══════════════════════════════════════════════════════════════
   attention-cue-ticker.js — WO-LORI-SESSION-AWARENESS-01 Phase 3

   Runtime glue between state surfaces and the pure decision logic
   in attention-cue-dispatcher.js. Reads mic/TTS/visual state on a
   timer, calls AttentionCueDispatcher.decideCue, dispatches a
   `lvAttentionCue` CustomEvent for downstream consumers (UI Tier 0
   indicator, Lori cue composer for Tier 1+).

   Inputs read every TICK_MS:
     - gap_ms          (Date.now() - state.narratorTurn.ttsFinishedAt)
     - mic_activity    (state.inputState.micActive || micPaused === false
                        AND VAD detects sound — reuse existing micActive
                        as the conservative proxy)
     - attention_state (state.session.attention_state, defaults 'unknown')
     - last_cue_ts     (state.session.lastAttentionCue.ts || null)
     - last_cue_tier   (state.session.lastAttentionCue.tier || null)

   Output:
     CustomEvent('lvAttentionCue', { detail: <decision-object> })
     dispatched on window. Decision object shape per dispatcher spec.

   Default-OFF behind window.LV_ATTENTION_CUE_TICKER (set via env-driven
   bootstrap or Bug Panel toggle). The state surface is initialized
   either way so downstream consumers can read it safely.

   Per spec §Stop conditions #3: until MediaPipe passive_waiting
   detection lands, attention_state stays 'unknown' and the
   dispatcher falls to the time ladder = same behavior as WO-10C.
   This module is byte-stable with current behavior in that mode.
   ═══════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  // Tick once per second — coarse enough not to load the main thread,
  // fine enough to fire near tier boundaries.
  const TICK_MS = 1000;

  // Suppress tick logging unless explicitly enabled (debug only).
  const VERBOSE = false;

  let _intervalId = null;
  let _started = false;

  // ── State helpers (read-only snapshots) ──────────────────────

  function _now() {
    return Date.now();
  }

  function _state() {
    return (typeof global.state === 'object' && global.state !== null)
      ? global.state
      : null;
  }

  function _ensureSession() {
    const s = _state();
    if (!s) return null;
    if (!s.session) s.session = {};
    return s.session;
  }

  /**
   * Initialize the attention surface on state.session if not present.
   * Default attention_state = 'unknown' makes the dispatcher fall to
   * the time ladder = identical to WO-10C silence cadence.
   */
  function ensureAttentionSurface() {
    const session = _ensureSession();
    if (!session) return;

    if (typeof session.attention_state !== 'string') {
      session.attention_state = 'unknown';
    }
    if (typeof session.last_seen_ms !== 'number' || isNaN(session.last_seen_ms)) {
      session.last_seen_ms = 0;
    }
    if (!session.passive_waiting_inputs) {
      session.passive_waiting_inputs = {
        gaze_forward:        null,
        low_movement:        null,
        no_speech_intent:    null,
        post_tts_silence_ms: 0,
      };
    }
    if (!session.lastAttentionCue) {
      session.lastAttentionCue = { ts: null, tier: null, signal_state: null };
    }
  }

  /**
   * Phase 3B — refresh state.session.attention_state from the
   * classifier on every tick so it reflects current sensor evidence.
   * Reads visualSignals (affect + gaze) + passive_waiting_inputs
   * (gaze/movement/speech_intent — currently null until the
   * MediaPipe layer lands). post_tts_silence_ms is computed locally.
   *
   * Pure read-then-write: never produces narrator-facing output.
   */
  function refreshAttentionStateFromClassifier(gap_ms) {
    const C = global.AttentionStateClassifier;
    if (!C) return;
    const session = _ensureSession();
    if (!session) return;

    const visual = session.visualSignals || {};
    const inputs = session.passive_waiting_inputs || {};

    // Don't clobber an explicitly-set attention_state (e.g. via
    // setAttentionState in tests/debug, or future adapter that
    // writes the label directly) when we have no sensor evidence
    // to derive from. Only refresh when there's signal.
    const hasPassiveInput = (
      inputs.gaze_forward !== null && inputs.gaze_forward !== undefined
    ) || (
      inputs.low_movement !== null && inputs.low_movement !== undefined
    ) || (
      inputs.no_speech_intent !== null && inputs.no_speech_intent !== undefined
    );
    const hasAffect = !!(visual.affectState);
    if (!hasPassiveInput && !hasAffect) return;

    const classified = C.classify({
      gaze_forward:        inputs.gaze_forward,
      low_movement:        inputs.low_movement,
      no_speech_intent:    inputs.no_speech_intent,
      post_tts_silence_ms: gap_ms,
      affect_state:        visual.affectState || null,
      face_present:        (visual.affectState != null) ? true : null,
    });

    session.attention_state = classified;
  }

  /**
   * Snapshot the inputs the dispatcher needs from current state.
   * Returns null if state isn't ready.
   */
  function snapshot() {
    const s = _state();
    if (!s) return null;
    ensureAttentionSurface();

    const session     = s.session || {};
    const inputState  = s.inputState || {};
    const narratorTurn = s.narratorTurn || {};

    const ttsFinishedAt = narratorTurn.ttsFinishedAt || null;
    const gap_ms = ttsFinishedAt ? Math.max(0, _now() - ttsFinishedAt) : 0;

    // Conservative mic-activity proxy: micActive AND not paused.
    // Real VAD signal would be additive; for now this is the same
    // gate that suppresses other Lori-side speech behaviors.
    const mic_activity = !!(inputState.micActive && !inputState.micPaused);

    // Phase 3B — derive attention_state from classifier on each
    // snapshot. Default 'unknown' if classifier isn't loaded.
    refreshAttentionStateFromClassifier(gap_ms);
    const attention_state = session.attention_state || 'unknown';

    const last = session.lastAttentionCue || {};
    return {
      gap_ms,
      attention_state,
      mic_activity,
      last_cue_ts:   last.ts   || null,
      last_cue_tier: (last.tier != null) ? last.tier : null,
      now_ms: _now(),
    };
  }

  // ── Dispatch ──────────────────────────────────────────────────

  function _emitDecision(decision) {
    if (!decision) return;
    const session = _ensureSession();
    if (session) {
      session.lastAttentionCue = {
        ts: _now(),
        tier: decision.tier,
        signal_state: decision.signal_state,
      };
    }

    // Log per spec format
    const D = global.AttentionCueDispatcher;
    const line = D && D.formatLog ? D.formatLog(decision) : null;
    if (line) {
      // eslint-disable-next-line no-console
      console.log(line);
    }

    // Dispatch DOM event for downstream listeners (UI indicator,
    // Lori cue composer). No direct coupling — listeners opt in.
    try {
      const evt = new CustomEvent('lvAttentionCue', { detail: decision });
      global.dispatchEvent(evt);
    } catch (_) { /* non-browser context */ }
  }

  function tick() {
    const D = global.AttentionCueDispatcher;
    if (!D) return;

    const inputs = snapshot();
    if (!inputs) return;

    // ttsFinishedAt being null means Lori is still speaking — no cue.
    const s = _state();
    const narratorTurn = (s && s.narratorTurn) || {};
    if (!narratorTurn.ttsFinishedAt) return;

    const decision = D.decideCue(inputs);

    if (VERBOSE) {
      // eslint-disable-next-line no-console
      console.log('[attention-cue][tick]',
        'gap=' + inputs.gap_ms,
        'attn=' + inputs.attention_state,
        'mic=' + inputs.mic_activity,
        'decision=' + (decision ? ('tier=' + decision.tier) : 'null'));
    }

    _emitDecision(decision);
  }

  // ── Lifecycle ─────────────────────────────────────────────────

  function start() {
    if (_started) return;
    ensureAttentionSurface();
    _intervalId = setInterval(tick, TICK_MS);
    _started = true;
    // eslint-disable-next-line no-console
    console.log('[attention-cue][ticker] started, interval=' + TICK_MS + 'ms');
  }

  function stop() {
    if (_intervalId != null) {
      clearInterval(_intervalId);
      _intervalId = null;
    }
    _started = false;
  }

  function isRunning() {
    return _started;
  }

  /**
   * Mark the narrator as visible/active. Bumps last_seen_ms so the
   * dispatcher can reason about freshness in a future enrichment.
   * Safe to call from anywhere (mic, camera, key, mouse).
   */
  function markNarratorActivity() {
    const session = _ensureSession();
    if (session) session.last_seen_ms = _now();
  }

  /**
   * Set the attention_state from a downstream classifier (e.g. the
   * MediaPipe passive_waiting detector once it lands). Validates
   * against the dispatcher's vocabulary before writing.
   */
  function setAttentionState(state) {
    const D = global.AttentionCueDispatcher;
    const session = _ensureSession();
    if (!session) return false;
    const valid = (D && D.VALID_ATTENTION_STATES) || [];
    if (valid.indexOf(state) === -1) {
      session.attention_state = 'unknown';
      return false;
    }
    session.attention_state = state;
    return true;
  }

  // ── Auto-start gate ───────────────────────────────────────────
  // Default-OFF: ticker only auto-starts if the bootstrap flag is true.
  // Bug Panel can flip it on at runtime via window.LV_ATTENTION_CUE_TICKER.

  function autoStartIfEnabled() {
    if (global.LV_ATTENTION_CUE_TICKER === true) {
      start();
    } else {
      // Even when ticker is off, ensure the surface exists for downstream
      // listeners and tests.
      ensureAttentionSurface();
    }
  }

  // Defer until DOM ready so state.js has loaded.
  if (typeof global.document !== 'undefined') {
    if (global.document.readyState === 'loading') {
      global.document.addEventListener('DOMContentLoaded', autoStartIfEnabled);
    } else {
      autoStartIfEnabled();
    }
  }

  // ── Module export ─────────────────────────────────────────────

  const AttentionCueTicker = {
    start,
    stop,
    isRunning,
    tick,                    // exposed for manual ticks in tests
    snapshot,                // exposed for operator-side trace use
    ensureAttentionSurface,
    setAttentionState,
    markNarratorActivity,
    TICK_MS,
  };

  global.AttentionCueTicker = AttentionCueTicker;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AttentionCueTicker;
  }

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
