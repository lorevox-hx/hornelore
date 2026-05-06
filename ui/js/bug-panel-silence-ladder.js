/* ═══════════════════════════════════════════════════════════════
   bug-panel-silence-ladder.js — operator-side silence cadence tile
   ═══════════════════════════════════════════════════════════════

   Purpose: live readout of the WO-10C / WO-10B silence-cadence state
   so the operator can SEE the "Lori is in her silent-attentive window"
   ladder counting in real time. Pure observability — reads from the
   existing idle-timer state set by lv80FireCheckIn / lv80ArmIdle in
   hornelore1.0.html. No behavior change.

   What the tile shows:
     - Current cadence: CSM 120/300/600 OR standard ~60/120/90
     - Seconds since last narrator activity
     - Next event: visual cue at NNs / gentle invitation at NNs / etc.
     - WO-10C stage: 0 (armed) | 1 (visual cue showing) | 2 (gentle
       invitation sent) | 3 (re-entry bridge sent)
     - Active suppressions: voice paused / Phase 3 ticker / narrator
       turn-claim / protected conversation state

   Tightly coupled to the silence dispatcher. If the cadence variables
   in hornelore1.0.html change names, this tile breaks gracefully
   (shows "—" for missing fields rather than crashing).

   Updates 1×/s while the Bug Panel is open. Stops when popover closes.
   ═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  const POLL_MS = 1000;       // 1Hz update — silence cadence is in seconds
  let _pollTimer = null;
  let _mountedRoot = null;

  function _fmtSeconds(ms) {
    if (ms == null || !isFinite(ms) || ms < 0) return "—";
    const s = Math.floor(ms / 1000);
    if (s < 60) return s + "s";
    const m = Math.floor(s / 60);
    const r = s % 60;
    return m + "m " + (r < 10 ? "0" + r : r) + "s";
  }

  function _fmtCountdown(ms) {
    if (ms == null || !isFinite(ms) || ms <= 0) return "fired";
    return "in " + _fmtSeconds(ms);
  }

  function _readSilenceState() {
    // Read everything defensively; the source-of-truth values live on
    // window globals or inside hornelore1.0.html closures we can't
    // reach. Use what's exposed.
    const now = Date.now();
    const lastActivityMs =
      Number(window._wo10bLastTranscriptGrowthTs || 0) ||
      Number(window._lv80LastUserTurnTs || 0) ||
      0;
    const sinceLastActivity = lastActivityMs > 0 ? now - lastActivityMs : null;

    const csm = (typeof getCognitiveSupportMode === "function")
      ? !!getCognitiveSupportMode()
      : !!(window.state && window.state.session && window.state.session.cognitiveSupportMode);

    // Cadence thresholds — read from the live window-mirrored constants
    // (set in ui/hornelore1.0.html alongside the WO10C_* declarations).
    // Falls back to hardcoded defaults ONLY if the mirrors aren't present
    // (which would indicate the page-bootstrap hasn't run yet — rare).
    let visualCueAt, gentleInviteAt, reentryAt, mode;
    if (csm) {
      visualCueAt    = (typeof window.WO10C_VISUAL_CUE_MS    !== "undefined") ? window.WO10C_VISUAL_CUE_MS    : 120000;
      gentleInviteAt = (typeof window.WO10C_GENTLE_INVITE_MS !== "undefined") ? window.WO10C_GENTLE_INVITE_MS : 300000;
      reentryAt      = (typeof window.WO10C_REENTRY_BRIDGE_MS !== "undefined") ? window.WO10C_REENTRY_BRIDGE_MS : 600000;
      mode = "CSM (cognitive support)";
    } else {
      // Standard cadence is age-aware via _LV80_IDLE_*() function
      // declarations (which DO window-attach automatically when at
      // top-level of an inline script). Calling them returns the
      // currently-active value; for elderly default the result is
      // 60s visual / 120s gentle (open) or 90s (memory). For non-
      // elderly: 30s visual / 75s gentle (open) or 55s (memory).
      visualCueAt = (typeof _LV80_IDLE_SOFT_MS === "function")
        ? _LV80_IDLE_SOFT_MS()
        : ((typeof LV80_IDLE_SOFT_MS !== "undefined") ? LV80_IDLE_SOFT_MS : 60000);
      gentleInviteAt = (typeof _LV80_IDLE_CHECKIN_OPEN === "function")
        ? _LV80_IDLE_CHECKIN_OPEN()
        : ((typeof LV80_IDLE_CHECKIN_OPEN !== "undefined") ? LV80_IDLE_CHECKIN_OPEN : 120000);
      reentryAt = null;       // standard cadence has only two stages
      // Surface whether the elderly-default branch is active so the
      // operator can see why the standard cadence is 60/120 instead of
      // 30/75 (or vice versa).
      let elderly = false;
      try {
        elderly = (typeof _wo08IsElderly === "function") ? !!_wo08IsElderly() : false;
      } catch (_) {}
      mode = elderly ? "Standard (elderly default)" : "Standard";
    }

    // WO-10C stage (0=armed, 1=visual shown, 2=gentle sent, 3=bridge
    // sent, 4=infinite patience). Read from window mirror set on each
    // assignment in ui/hornelore1.0.html (search "wo10c stage mirror").
    const stage = Number(window._wo10cIdleStage || 0);

    // Suppressions
    const suppressions = [];
    if (window._wo8VoicePaused === true) suppressions.push("voice paused (WO-8)");
    if (window.LV_ATTENTION_CUE_TICKER === true) suppressions.push("Phase 3 ticker (visual-only)");
    try {
      if (typeof wo10hIsNarratorTurnActive === "function" && wo10hIsNarratorTurnActive()) {
        suppressions.push("narrator turn-claim (WO-10H)");
      }
    } catch (_) {}
    const cs = window._wo10bCurrentConversationState;
    if (cs === "storytelling" || cs === "reflecting" || cs === "emotional_pause") {
      suppressions.push("protected state: " + cs);
    }
    // Recent transcript growth (< 5s ago) — narrator is mid-utterance
    if (sinceLastActivity != null && sinceLastActivity < 5000) {
      suppressions.push("narrator typing/speaking");
    }

    // Compute next-event ETA based on sinceLastActivity
    let nextLabel = "—";
    let nextEtaMs = null;
    if (sinceLastActivity != null) {
      if (stage === 0) {
        nextLabel = "visual cue";
        nextEtaMs = visualCueAt - sinceLastActivity;
      } else if (stage === 1) {
        nextLabel = "gentle invitation";
        nextEtaMs = gentleInviteAt - sinceLastActivity;
      } else if (stage === 2 && reentryAt) {
        nextLabel = "re-entry bridge";
        nextEtaMs = reentryAt - sinceLastActivity;
      } else if (stage === 2 && !reentryAt) {
        nextLabel = "ladder complete";
        nextEtaMs = null;
      } else {
        nextLabel = "ladder complete";
        nextEtaMs = null;
      }
    }

    return {
      mode,
      csm,
      sinceLastActivity,
      stage,
      visualCueAt,
      gentleInviteAt,
      reentryAt,
      nextLabel,
      nextEtaMs,
      suppressions,
      hasActivity: lastActivityMs > 0,
    };
  }

  function _render(root) {
    const s = _readSilenceState();
    const lines = [];
    lines.push('<div class="silence-ladder-card">');
    lines.push('<div class="silence-ladder-header">Silence ladder · ' + s.mode + '</div>');

    if (!s.hasActivity) {
      lines.push('<div class="silence-ladder-empty">Waiting for first narrator turn…</div>');
    } else {
      lines.push('<div class="silence-ladder-row"><span class="silence-ladder-label">Since last activity:</span> <strong>' + _fmtSeconds(s.sinceLastActivity) + '</strong></div>');
      // Stage scale: CSM ladders 0→1→2→3→(4 patient); standard
      // ladders 0→1→2 only (no re-entry bridge). Display as
      // "current / max-active-stage".
      const maxStage = s.csm ? 3 : 2;
      lines.push('<div class="silence-ladder-row"><span class="silence-ladder-label">Current stage:</span> ' + s.stage + ' / ' + maxStage + '</div>');
      lines.push('<div class="silence-ladder-row"><span class="silence-ladder-label">Next:</span> ' + s.nextLabel + ' ' + _fmtCountdown(s.nextEtaMs) + '</div>');

      // Cadence reference
      lines.push('<div class="silence-ladder-cadence">');
      lines.push('  <span>Visual: ' + _fmtSeconds(s.visualCueAt) + '</span>');
      lines.push('  <span>Gentle: ' + _fmtSeconds(s.gentleInviteAt) + '</span>');
      if (s.reentryAt) {
        lines.push('  <span>Re-entry: ' + _fmtSeconds(s.reentryAt) + '</span>');
      }
      lines.push('</div>');
    }

    if (s.suppressions.length > 0) {
      lines.push('<div class="silence-ladder-suppressed">');
      lines.push('  <strong>Suppressed:</strong> ' + s.suppressions.join(', '));
      lines.push('</div>');
    }

    lines.push('</div>');
    root.innerHTML = lines.join('\n');
  }

  function _startPoll(root) {
    if (_pollTimer) clearInterval(_pollTimer);
    _render(root);
    _pollTimer = setInterval(function () { _render(root); }, POLL_MS);
  }

  function _stopPoll() {
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
  }

  function _onPanelToggle() {
    const panel = document.getElementById("lv10dBugPanel");
    if (!panel) return;
    if (panel.matches && panel.matches(":popover-open")) {
      if (_mountedRoot) _startPoll(_mountedRoot);
    } else {
      _stopPoll();
    }
  }

  function _init() {
    _mountedRoot = document.getElementById("lv10dBpSilenceLadder");
    if (!_mountedRoot) {
      console.warn("[bug-panel-silence-ladder] mount root #lv10dBpSilenceLadder not found");
      return;
    }
    // Initial render so the tile shows something even if the panel
    // never opens.
    _render(_mountedRoot);

    // Wire panel toggle: start polling when panel opens, stop when closes.
    const panel = document.getElementById("lv10dBugPanel");
    if (panel) {
      // beforetoggle fires on popover open/close; check state after the event
      panel.addEventListener("toggle", _onPanelToggle);
      // initial state
      _onPanelToggle();
    }

    // Public API for harness / dev console
    window.lvSilenceLadderRefresh = function () { _render(_mountedRoot); };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _init);
  } else {
    _init();
  }
})();
