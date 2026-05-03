/* ═══════════════════════════════════════════════════════════════
   attention-state-classifier.js — WO-LORI-SESSION-AWARENESS-01
                                    Phase 3A (read-only classifier)

   Pure decision module: takes the 4 spec inputs, returns one of
     'passive_waiting' | 'engaged' | 'reflective' | 'face_missing' | 'unknown'

   Per spec §Phase 3:
     - passive_waiting requires ALL FOUR inputs:
         gaze_forward, low_movement, no_speech_intent, post_tts_silence_ms >= floor
     - engaged / reflective veto blocks passive_waiting under WO-10C 120s mark
     - face_missing is its own state (narrator stepped away)
     - any other combination → 'unknown' (dispatcher falls to time ladder)

   This module is pure: no state writes, no DOM, no MediaPipe calls.
   The MediaPipe-side adapter feeds the inputs in; the ticker writes
   the result to state.session.attention_state.

   Phase 3 lock: nothing in this module decides whether Lori speaks.
   The classifier emits a label. The dispatcher (separate module)
   decides cue tier. The presence cue (separate module) renders text.
   No banned vocabulary anywhere.
   ═══════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────

  // Minimum post-TTS silence before passive_waiting can be emitted at all.
  // Matches the dispatcher's 25s hard floor per WO §Phase 3 #8.
  const HARD_FLOOR_MS = 25 * 1000;

  // The veto floor — engaged / reflective narrators get the long ladder
  // until WO-10C's 120s mark. Below that, the classifier emits the
  // engaged/reflective label so the dispatcher can veto.
  const WO_10C_FLOOR_MS = 120 * 1000;

  // Affect-side mapping: what counts as engaged or reflective for veto.
  // Mirrors the AFFECT_STATES vocabulary from emotion.js + the
  // visualSignals shape from affect-bridge.js.
  const ENGAGED_AFFECTS    = new Set(['engaged']);
  const REFLECTIVE_AFFECTS = new Set(['reflective', 'moved']);

  // ── Helpers ────────────────────────────────────────────────────

  function _truthy(v) {
    // Conservative truthiness for 4-input AND. null / undefined / NaN
    // are NOT truthy. We require positive evidence for passive_waiting.
    return v === true;
  }

  function _falsey(v) {
    // For "no_*" inputs — also conservative. We need positive evidence
    // that the narrator is NOT speaking, not just absence of evidence.
    return v === true;
  }

  function _affectIsEngaged(affect) {
    return !!(affect && ENGAGED_AFFECTS.has(affect));
  }

  function _affectIsReflective(affect) {
    return !!(affect && REFLECTIVE_AFFECTS.has(affect));
  }

  // ── Classifier ─────────────────────────────────────────────────

  /**
   * Classify the narrator's attention state from sensor inputs.
   * Returns one label string. Pure function — no side effects.
   *
   * @param {Object} inputs
   * @param {boolean|null} inputs.gaze_forward     true=looking at screen
   * @param {boolean|null} inputs.low_movement     true=no animated retrieval / breath gathering
   * @param {boolean|null} inputs.no_speech_intent true=mouth not pre-shaping a word
   * @param {number}       inputs.post_tts_silence_ms  ms since Lori finished
   * @param {string|null}  inputs.affect_state     visualSignals.affectState OR null
   * @param {boolean|null} inputs.face_present     false=narrator out of frame
   * @returns {string}  one of VALID_STATES
   */
  function classify(inputs) {
    inputs = inputs || {};

    const gaze     = inputs.gaze_forward;
    const move     = inputs.low_movement;
    const silent   = inputs.no_speech_intent;
    const sinceMs  = Number(inputs.post_tts_silence_ms || 0);
    const affect   = inputs.affect_state || null;
    const face     = (inputs.face_present !== undefined) ? inputs.face_present : null;

    // Rule A: face is positively absent → face_missing.
    // (Distinguish from face_present === null which means "no camera signal at all".)
    if (face === false) {
      return 'face_missing';
    }

    // Rule B: positively-confirmed engaged affect → engaged.
    // The dispatcher enforces the WO-10C 120s veto downstream; the
    // classifier just labels what it sees so the operator can audit.
    if (_affectIsEngaged(affect)) {
      return 'engaged';
    }

    // Rule C: positively-confirmed reflective/moved affect → reflective.
    if (_affectIsReflective(affect)) {
      return 'reflective';
    }

    // Rule D: passive_waiting requires ALL FOUR inputs to be true,
    //         AND post_tts_silence_ms must be at or above the hard floor.
    //         Any null / missing input fails the conjunction.
    const allFourConfirmed =
      _truthy(gaze) && _truthy(move) && _falsey(silent) && sinceMs >= HARD_FLOOR_MS;

    if (allFourConfirmed) {
      return 'passive_waiting';
    }

    // Rule E: nothing else met confidence — unknown.
    // The dispatcher will fall to the WO-10C time ladder.
    return 'unknown';
  }

  /**
   * Trace helper: returns the same inputs plus a `decision` field +
   * the active thresholds. Useful for the operator harness; not for
   * narrator-facing surfaces.
   */
  function classifyWithTrace(inputs) {
    const decision = classify(inputs);
    inputs = inputs || {};
    return {
      decision,
      inputs: {
        gaze_forward:        inputs.gaze_forward === true,
        low_movement:        inputs.low_movement === true,
        no_speech_intent:    inputs.no_speech_intent === true,
        post_tts_silence_ms: Number(inputs.post_tts_silence_ms || 0),
        affect_state:        inputs.affect_state || null,
        face_present:        (inputs.face_present !== undefined) ? inputs.face_present : null,
      },
      thresholds: {
        hard_floor_ms:   HARD_FLOOR_MS,
        wo_10c_floor_ms: WO_10C_FLOOR_MS,
      },
    };
  }

  // ── Module export ──────────────────────────────────────────────

  const VALID_STATES = [
    'passive_waiting',
    'engaged',
    'reflective',
    'face_missing',
    'unknown',
  ];

  const AttentionStateClassifier = {
    classify,
    classifyWithTrace,
    HARD_FLOOR_MS,
    WO_10C_FLOOR_MS,
    VALID_STATES,
  };

  global.AttentionStateClassifier = AttentionStateClassifier;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AttentionStateClassifier;
  }

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
