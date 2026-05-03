/* ═══════════════════════════════════════════════════════════════
   lori-since-timer.js — operator-visible "Lori finished N seconds ago"

   Sits next to the lori-clock element inside #lvNarratorConversation.
   Reads state.narratorTurn.ttsFinishedAt every 1s and renders:

     "Lori finished:  23s"   ← gray   (within 25s hard floor)
     "Lori finished:  47s"   ← light  (Tier 0 — silent presence)
     "Lori finished: 1m 12s" ← blue   (Tier 1 — visual cue stronger)
     "Lori finished: 2m 30s" ← amber  (Tier 2 — soft offer)
     "Lori finished: 5m 10s" ← orange (Tier 3 — re-entry zone)
     "Lori finished: 10m+"   ← red    (Tier 4 — break offer zone)

   When Lori is currently speaking (ttsFinishedAt null), shows
   "Lori speaking…" in a calm slate.

   The tier color thresholds match attention-cue-dispatcher.js
   constants exactly. This is purely operator/observer-side so the
   parent-session driver can see at-a-glance whether the silence
   ladder is on the right rung. Per Phase 3 design — does NOT
   route to TTS, transcript, or extractor. Pure cosmetic readout.

   Updates every 1s via setInterval. IIFE — no global side effects
   beyond window.lvSinceTimerRefresh() (operator dev convenience).
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

    // Mount inside the same container as the clock (lvNarratorConversation).
    const container = document.getElementById("lvNarratorConversation");
    if (!container) return null;

    el = document.createElement("div");
    el.id = MOUNT_ID;
    el.className = "lv-since-timer";
    el.setAttribute("aria-hidden", "true");  // operator/decorative
    el.dataset.purpose = "operator_observability";
    el.innerHTML =
      '<div class="lv-since-eyebrow">Countdown Timer</div>' +
      '<div class="lv-since-elapsed" data-since-slot="elapsed">00:00</div>' +
      '<div class="lv-since-tier" data-since-slot="tier">Lori speaking</div>';
    container.appendChild(el);
    return el;
  }

  // ── Refresh ────────────────────────────────────────────────────

  function refresh() {
    const el = _ensureMount();
    if (!el) return;

    const tts_at = _ttsFinishedAt();
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

    if (!tts_at) {
      // Lori is currently speaking (or no turn has happened yet).
      // Per Chris's spec: "Lori speaks: reset". Show 00:00, calm slate.
      el.classList.add("lv-since-speaking");
      if (elapsedSlot) elapsedSlot.textContent = "00:00";
      if (tierSlot)    tierSlot.textContent    = "Lori speaking";
      return;
    }

    const gap_ms = Math.max(0, Date.now() - tts_at);
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

  global.lvSinceTimerRefresh = refresh;
  global.LoriSinceTimer = {
    start, stop, refresh,
    HARD_FLOOR_MS, TIER_1_MIN_MS, TIER_2_MIN_MS,
    TIER_3_MIN_MS, TIER_4_MIN_MS,
  };

})(typeof window !== "undefined" ? window : (typeof global !== "undefined" ? global : this));
