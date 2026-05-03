/* ═══════════════════════════════════════════════════════════════
   presence-cue.js — WO-LORI-SESSION-AWARENESS-01 Phase 3E

   Quiet presence cue: a narrator-visible visual indicator that
   shows up only when the dispatcher decides Lori is "listening
   quietly" — not a spoken cue, not a system status, not a question.

   Per Chris's restructure (2026-05-03):
     - Display only, never TTS
     - Only after Lori finishes speaking
     - Never before 25 seconds
     - Do not show if narrator is speaking
     - Do not show if engaged / reflective veto says "thinking"
     - Hide immediately when mic activity starts
     - Do not log as narrator content
     - Do not feed to extractor

   The cue is bound to the lvAttentionCue CustomEvent emitted by
   attention-cue-ticker.js — when intent === 'visual_only', this
   module shows the cue. It NEVER calls TTS. It NEVER writes to
   the transcript. It NEVER reaches the extractor pipeline.

   Wording (locked per Chris):
     "Take your time. I'm listening."

   Mount target: a single <div id="lvPresenceCue"> placed inside
   the narrator chat area. CSS in lori80.css handles visual styling.
   ═══════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  const CUE_TEXT = "Take your time. I'm listening.";
  const MOUNT_ID = 'lvPresenceCue';
  const FADE_OUT_MS = 400;     // CSS transition duration
  const MAX_VISIBLE_MS = 60_000;  // safety: never show longer than 60s

  // Two-stage opacity ramp per WO-LORI-SESSION-AWARENESS-01 Phase 3E:
  //   25–45s = faint (still feels like thinking room)
  //   45s+   = slightly stronger (might be waiting)
  // No text change, no escalation language — just CSS opacity.
  const STAGE_STRONGER_MS = 45_000;

  let _mountEl = null;
  let _hideTimer = null;
  let _shown = false;

  // ── Mount management ─────────────────────────────────────────

  function _ensureMount() {
    if (typeof document === 'undefined') return null;
    if (_mountEl && document.body.contains(_mountEl)) return _mountEl;

    let el = document.getElementById(MOUNT_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = MOUNT_ID;
      el.className = 'lv-presence-cue';
      el.setAttribute('role', 'status');
      el.setAttribute('aria-live', 'polite');
      el.setAttribute('aria-hidden', 'true');
      el.dataset.purpose = 'visual_presence';   // marks this DOM as never-spoken
      el.dataset.transcriptIgnore = 'true';      // marks it for transcript filters
      el.textContent = CUE_TEXT;
      // Style fallback in case CSS hasn't loaded yet — keeps it invisible.
      el.style.opacity = '0';
      el.style.pointerEvents = 'none';

      // Mount near the narrator chat surface; fall back to body if not found.
      const target = document.getElementById('lvNarratorConversation')
        || document.getElementById('lvChatContainer')
        || document.body;
      target.appendChild(el);
    }
    _mountEl = el;
    return el;
  }

  // ── Show / hide ───────────────────────────────────────────────

  function show(decision) {
    const el = _ensureMount();
    if (!el) return;

    // Two-stage opacity ramp driven by gap_ms (passed from the
    // dispatcher decision). Use CSS classes so the ramp lives in
    // the stylesheet and can be adjusted without code changes.
    const gap_ms = (decision && Number(decision.gap_ms)) || 0;
    el.classList.remove('lv-presence-faint', 'lv-presence-stronger');
    if (gap_ms >= STAGE_STRONGER_MS) {
      el.classList.add('lv-presence-stronger');
    } else {
      el.classList.add('lv-presence-faint');
    }

    el.style.transition = 'opacity ' + FADE_OUT_MS + 'ms ease-in-out';
    // Opacity is set via class (CSS-driven); only set inline as
    // visibility unblock since the initial state has opacity:0
    // inline from _ensureMount.
    el.style.opacity = '';
    el.setAttribute('aria-hidden', 'false');
    _shown = true;

    // Safety auto-hide so a stuck signal doesn't leave the cue glued on.
    if (_hideTimer) clearTimeout(_hideTimer);
    _hideTimer = setTimeout(() => hide(), MAX_VISIBLE_MS);
  }

  function hide() {
    const el = _ensureMount();
    if (!el) return;
    if (_hideTimer) {
      clearTimeout(_hideTimer);
      _hideTimer = null;
    }
    el.style.opacity = '0';
    el.setAttribute('aria-hidden', 'true');
    _shown = false;
  }

  function isShown() {
    return _shown;
  }

  // ── Event listener ───────────────────────────────────────────

  /**
   * Reacts to lvAttentionCue events from attention-cue-ticker.js.
   * Phase 3 lock: only intent === 'visual_only' surfaces. Any other
   * intent is ignored to make the don't-let-Lori-speak guarantee
   * structural rather than honored by convention.
   */
  function _onAttentionCue(evt) {
    const decision = evt && evt.detail;
    if (!decision) {
      hide();
      return;
    }

    // Phase 3 structural lock — only visual_only fires the cue.
    if (decision.intent !== 'visual_only') {
      hide();
      return;
    }

    // Tier 0 = silent presence pulse (already implicit in the cue's
    // soft fade). Tier 1+ = same visual cue text. Any tier shows
    // the same wording per spec — there is one cue, never escalated
    // verbally. Opacity ramps with gap_ms (faint → stronger).
    show(decision);
  }

  /**
   * Hide the cue when the narrator starts speaking. Called from
   * mic-state listeners or directly from app.js when STT begins.
   */
  function onMicActivity() {
    hide();
  }

  // ── Bootstrap ────────────────────────────────────────────────

  function init() {
    _ensureMount();

    if (typeof global.addEventListener === 'function') {
      global.addEventListener('lvAttentionCue', _onAttentionCue);
    }

    // Hook into existing inputState mic flag if available — best effort.
    // The canonical hide is also called explicitly from STT start
    // (recognition.onresult / onstart) wherever those handlers live.
    if (global.state && global.state.inputState) {
      try {
        const orig = Object.getOwnPropertyDescriptor(
          global.state.inputState, 'micActive'
        );
        // Only wrap if the property is a plain value (not already a getter/setter)
        if (orig && 'value' in orig) {
          let _mic = orig.value;
          Object.defineProperty(global.state.inputState, 'micActive', {
            get() { return _mic; },
            set(v) {
              _mic = v;
              if (v === true) onMicActivity();
            },
            configurable: true,
            enumerable: true,
          });
        }
      } catch (_) { /* no-op if readonly */ }
    }
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }

  // ── Module export ────────────────────────────────────────────

  const PresenceCue = {
    init,
    show,
    hide,
    isShown,
    onMicActivity,
    CUE_TEXT,
    MOUNT_ID,
  };

  global.PresenceCue = PresenceCue;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = PresenceCue;
  }

})(typeof window !== 'undefined' ? window : (typeof global !== 'undefined' ? global : this));
