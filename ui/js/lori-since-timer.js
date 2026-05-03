/* ═══════════════════════════════════════════════════════════════
   lori-since-timer.js — Lane H Countdown Timer (operator-visible)

   Sits to the RIGHT of the Send button inside the footer compose
   bar (#lv80SendBtn.nextSibling). Reads narratorTurn anchors every
   1s and renders a mm:ss countdown plus tier label.

   ANCHOR (Chris's spec, 2026-05-03 evening):
     Primary  : state.narratorTurn.loriStreamStartedAt
                — set in app.js handleWsMessage() the moment Lori's
                  FIRST stream token arrives in the UI.
     Fallback : state.narratorTurn.ttsFinishedAt
                — for stacks where TTS is gating but stream was
                  not observed (older WO-10H-only path).
     Reset    : sendUserMessage() clears BOTH anchors when the
                narrator hits Send. Mic-active also resets.

     This means: the timer starts as soon as Lori begins responding
     (visible first word), keeps running through her TTS speech AND
     the silence afterward, and only resets when the narrator takes
     the floor (mic on OR send pressed).

   PLACEMENT (Chris's spec, 2026-05-03 evening):
     Adjacent to the Send button on the right — NEVER overlapping
     the textarea. Inline-flex so the footer auto-sizes around it.

   Tier color thresholds match attention-cue-dispatcher.js / 25s
   hard floor / 45s stronger cue / WO-10C 60s/2m/5m/10m boundaries.
   Pure operator observability — does NOT route to TTS, transcript,
   or extractor. Updates every 1s via setInterval. IIFE — no global
   side effects beyond window.lvSinceTimerRefresh() (operator dev
   convenience).
   ═══════════════════════════════════════════════════════════════ */

(function (global) {
  'use strict';

  // Tier thresholds (match attention-cue-dispatcher.js constants)
  const HARD_FLOOR_MS = 25 * 1000;
  const TIER_1_MIN_MS = 60 * 1000;
  const TIER_2_MIN_MS = 120 * 1000;
  const TIER_3_MIN_MS = 300 * 1000;
  const TIER_4_MIN_MS = 600 * 1000;

  const MOUNT_ID = "lvSinceTimer";
  const REFRESH_MS = 1000;

  let _timer = null;

  // ── Helpers ────────────────────────────────────────────────────

  function _state() {
    return (typeof global.state === "object" && global.state !== null)
      ? global.state
      : null;
  }

  function _ttsFinishedAt() {
    const s = _state();
    if (!s || !s.narratorTurn) return null;
    return s.narratorTurn.ttsFinishedAt || null;
  }

  function _loriStreamStartedAt() {
    // Lane H primary anchor — set on Lori's first reply token
    // (app.js handleWsMessage). When set, this overrides
    // ttsFinishedAt because Chris's rule is "start as soon as
    // Lori types the first word, not after she's done speaking."
    const s = _state();
    if (!s || !s.narratorTurn) return null;
    return s.narratorTurn.loriStreamStartedAt || null;
  }

  function _countAnchor() {
    // Prefer the first-token anchor; fall back to TTS-finished if
    // a stack runs without observing the stream (e.g. test harness
    // that watches for legacy WO-10H signals).
    return _loriStreamStartedAt() || _ttsFinishedAt();
  }

  function _attentionState() {
    const s = _state();
    if (!s || !s.session) return "unknown";
    return s.session.attention_state || "unknown";
  }

  function _micActive() {
    // Per ChatGPT spec (2026-05-03): "Mic starts: reset/hide".
    // When the narrator is speaking, the countdown should disappear
    // (the silence window has ended). Mirrors the presence cue's
    // mic-hide behavior so both surfaces stay in sync.
    const s = _state();
    if (!s || !s.inputState) return false;
    return !!(s.inputState.micActive && !s.inputState.micPaused);
  }

  function _formatDuration(ms) {
    // mm:ss format per Chris's spec ("Countdown: 00:32"). Caps display
    // at 99:59 — beyond that the operator has bigger problems than
    // formatting precision.
    if (ms < 0) ms = 0;
    const total_s = Math.floor(ms / 1000);
    let m = Math.floor(total_s / 60);
    const s = total_s - m * 60;
    if (m > 99) m = 99;
    const pad = (n) => (n < 10 ? "0" + n : "" + n);
    return pad(m) + ":" + pad(s);
  }

  // Presence cue stage boundaries (Phase 3E):
  //   25s = faint visual cue stage begins
  //   45s = stronger visual cue stage begins
  // These are what the narrator actually sees on screen, so call them
  // out by name in the tier label (per Chris's "marks 25s and 45s
  // cue ranges" spec).
  const PRESENCE_FAINT_MS    = 25 * 1000;
  const PRESENCE_STRONGER_MS = 45 * 1000;

  function _tierForGap(gap_ms) {
    // Returns { tier: int, label: str, klass: str }
    if (gap_ms < PRESENCE_FAINT_MS) {
      return { tier: -1, label: "thinking room (under 25s)", klass: "lv-since-floor" };
    }
    if (gap_ms < PRESENCE_STRONGER_MS) {
      return { tier: 0, label: "faint cue (25–45s)", klass: "lv-since-t0" };
    }
    if (gap_ms < TIER_1_MIN_MS) {
      return { tier: 0, label: "stronger cue (45s+)", klass: "lv-since-t0-strong" };
    }
    if (gap_ms < TIER_2_MIN_MS) {
      return { tier: 1, label: "T1 spoken-cue zone (60s+)", klass: "lv-since-t1" };
    }
    if (gap_ms < TIER_3_MIN_MS) {
      return { tier: 2, label: "T2 soft-offer zone (2m+)", klass: "lv-since-t2" };
    }
    if (gap_ms < TIER_4_MIN_MS) {
      return { tier: 3, label: "T3 re-entry zone (5m+)", klass: "lv-since-t3" };
    }
    return { tier: 4, label: "T4 break-offer zone (10m+)", klass: "lv-since-t4" };
  }

  // ── Mount ──────────────────────────────────────────────────────

  function _ensureMount() {
    if (typeof global.document === "undefined") return null;
    let el = document.getElementById(MOUNT_ID);
    if (el) return el;

    // Lane H placement — sit IMMEDIATELY AFTER the Send button so
    // the timer is adjacent to it on the right. Falls back to the
    // footer's compose row if Send isn't present, then to
    // #lvNarratorConversation (legacy mount) as last resort.
    // Never mounts on top of #chatInput — that's the textarea
    // narrators type into and the original bug Chris flagged.
    const sendBtn = document.getElementById("lv80SendBtn");
    let parent = null;
    let insertBefore = null;
    if (sendBtn && sendBtn.parentNode) {
      parent = sendBtn.parentNode;
      insertBefore = sendBtn.nextSibling; // null is fine — appendChild semantics
    } else {
      // Fallback: attach to #lvNarratorConversation if Send hasn't
      // rendered yet (Operator tab open at boot). Refresh keeps
      // re-running, so once Send appears we'll re-mount on next tick
      // when the existing element is still pointed at the wrong
      // parent — handled by the resync below.
      const container = document.getElementById("lvNarratorConversation");
      if (!container) return null;
      parent = container;
      insertBefore = null;
    }

    el = document.createElement("div");
    el.id = MOUNT_ID;
    el.className = "lv-since-timer";
    el.setAttribute("aria-hidden", "true");  // operator/decorative
    el.dataset.purpose = "operator_observability";
    el.innerHTML =
      '<div class="lv-since-eyebrow">Countdown</div>' +
      '<div class="lv-since-elapsed" data-since-slot="elapsed">00:00</div>' +
      '<div class="lv-since-tier" data-since-slot="tier">Lori speaking</div>';
    if (insertBefore) parent.insertBefore(el, insertBefore);
    else parent.appendChild(el);
    return el;
  }

  function _resyncToSendIfStranded() {
    // If we mounted into the legacy fallback parent before #lv80SendBtn
    // existed, move the element next to Send the moment it appears.
    // Idempotent — only acts when the parent is wrong.
    if (typeof global.document === "undefined") return;
    const el = document.getElementById(MOUNT_ID);
    if (!el) return;
    const sendBtn = document.getElementById("lv80SendBtn");
    if (!sendBtn || !sendBtn.parentNode) return;
    if (el.parentNode === sendBtn.parentNode) return;
    sendBtn.parentNode.insertBefore(el, sendBtn.nextSibling);
  }

  // ── Refresh ────────────────────────────────────────────────────

  function refresh() {
    const el = _ensureMount();
    if (!el) return;
    _resyncToSendIfStranded();

    const anchor = _countAnchor();
    const elapsedSlot = el.querySelector('[data-since-slot="elapsed"]');
    const tierSlot    = el.querySelector('[data-since-slot="tier"]');

    // Clear all stage classes between renders so they don't accumulate.
    el.classList.remove(
      "lv-since-speaking",
      "lv-since-mic-active",
      "lv-since-floor",
      "lv-since-t0",
      "lv-since-t0-strong",
      "lv-since-t1",
      "lv-since-t2",
      "lv-since-t3",
      "lv-since-t4",
    );

    // Mic-active reset (per Chris's spec: "Mic starts: reset/hide").
    // When the narrator is speaking, the silence window has ended.
    if (_micActive()) {
      el.classList.add("lv-since-mic-active");
      if (elapsedSlot) elapsedSlot.textContent = "00:00";
      if (tierSlot)    tierSlot.textContent    = "narrator speaking";
      return;
    }

    if (!anchor) {
      // No Lori turn has started yet (boot, post-send-pre-stream).
      // Per Chris's spec: timer "stops/resets/hides" until next Lori
      // reply starts. Show 00:00 in calm slate; copy reads "Lori
      // speaking" because that's the next state the operator is
      // waiting for.
      el.classList.add("lv-since-speaking");
      if (elapsedSlot) elapsedSlot.textContent = "00:00";
      if (tierSlot)    tierSlot.textContent    = "waiting for Lori";
      return;
    }

    const gap_ms = Math.max(0, Date.now() - anchor);
    const t = _tierForGap(gap_ms);
    el.classList.add(t.klass);

    if (elapsedSlot) elapsedSlot.textContent = _formatDuration(gap_ms);
    if (tierSlot) {
      const attn = _attentionState();
      const attnHint = (attn && attn !== "unknown") ? " · " + attn : "";
      tierSlot.textContent = t.label + attnHint;
    }
  }

  // ── Lifecycle ──────────────────────────────────────────────────

  function start() {
    if (_timer != null) return;
    _ensureMount();
    refresh();
    _timer = setInterval(refresh, REFRESH_MS);
  }

  function stop() {
    if (_timer != null) {
      clearInterval(_timer);
      _timer = null;
    }
  }

  // ── Bootstrap ──────────────────────────────────────────────────

  function init() {
    // Start the timer. The mount is created lazily by _ensureMount on
    // first refresh — so even if #lvNarratorConversation isn't in the
    // DOM yet (Operator tab), we'll keep retrying every second until
    // it appears (then mount + render).
    start();
  }

  if (typeof global.document !== "undefined") {
    if (global.document.readyState === "loading") {
      global.document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  }

  // ── Module export ──────────────────────────────────────────────

  const LoriSinceTimer = {
    start, stop, refresh,
    HARD_FLOOR_MS, TIER_1_MIN_MS, TIER_2_MIN_MS,
    TIER_3_MIN_MS, TIER_4_MIN_MS,
  };

  global.lvSinceTimerRefresh = refresh;
  global.LoriSinceTimer = LoriSinceTimer;

  // CommonJS for Node-side tests (matches the convention from
  // attention-cue-dispatcher.js / attention-state-classifier.js /
  // attention-cue-ticker.js / presence-cue.js).
  if (typeof module !== "undefined" && module.exports) {
    module.exports = LoriSinceTimer;
  }

})(typeof window !== "undefined" ? window : (typeof global !== "undefined" ? global : this));
