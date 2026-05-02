/* ═══════════════════════════════════════════════════════════════
   lori-clock.js — WO-INTERVIEW-CLOCK-01

   Narrator-visible orientation clock, lower-left of the narrator
   chat region adjacent to the mic affordance.

   Locked design rules (per WO-INTERVIEW-CLOCK-01_Spec.md):
     1. Narrator-visible only. Mounted inside #lvNarratorConversation
        which lives in #lvNarratorTab — automatically hidden on the
        Operator/Media tabs by the shell tab system.
     2. No system-tone outputs. No timezone abbreviation. No
        "device_context" / "monitoring" / "tracking" copy.
     3. No softened-mode visual change. The clock never recolors,
        flickers, or hides on safety events.
     4. No reset on narrator switch. Time + place are system-clock
        + static config; narrator identity changes nothing here.
     5. Once per minute. setInterval(_, 60_000) re-derives new Date()
        — no accumulator, DST-safe by construction.
     6. Plain DOM, no framework. IIFE, vanilla JS, lori80.css.

   Variant: B (slate, 36px time) is the locked default for v1.
            Operator can override via:
              localStorage["lvClockVariant"] in {"B", "C", "A", "off"}
            (variants C and A render with the same data but different
            shells — the toggle is style-only, slot is fixed.)

   Place line:
     Reads window.LV_NARRATOR_LOCATION (set by server template
     injection, future) OR localStorage["lvNarratorLocation"]
     (operator-side override). Falls back to empty string — layout
     collapses cleanly per WO design rule.

   Public surface:
     window.lvClockRefresh()  — force one immediate re-render
                                 (operator dev convenience).

   ═══════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  // ── Config ──────────────────────────────────────────────────────
  var TICK_MS = 60 * 1000;          // once per minute (WO rule 5)
  var DEFAULT_VARIANT = "B";        // 2026-05-02 lock
  var MOUNT_RETRY_MS = 250;         // wait for narrator section to exist
  var MOUNT_RETRY_LIMIT = 40;       // give up after ~10s (operator tab default)

  // ── Helpers ─────────────────────────────────────────────────────
  function _readLocation() {
    // Priority order:
    //   1. Window global (server-injected, future)
    //   2. localStorage override (operator-side dev convenience)
    //   3. Empty string → place line hides cleanly
    try {
      var w = (typeof window !== "undefined" && window.LV_NARRATOR_LOCATION);
      if (w && typeof w === "string" && w.trim()) return w.trim();
    } catch (_) {}
    try {
      var ls = localStorage.getItem("lvNarratorLocation");
      if (ls && ls.trim()) return ls.trim();
    } catch (_) {}
    return "";
  }

  function _readVariant() {
    try {
      var v = (localStorage.getItem("lvClockVariant") || "").trim().toUpperCase();
      if (v === "B" || v === "C" || v === "A" || v === "OFF") return v;
    } catch (_) {}
    return DEFAULT_VARIANT;
  }

  function _timeOfDayLabel(d) {
    var h = d.getHours();
    if (h < 5)  return "night";
    if (h < 12) return "morning";
    if (h < 17) return "afternoon";
    if (h < 21) return "evening";
    return "night";
  }

  function _formatTime(d) {
    return d.toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit"
    });
  }

  function _formatDayOfWeek(d) {
    var day = d.toLocaleDateString(undefined, { weekday: "long" });
    return day + " " + _timeOfDayLabel(d);
  }

  function _formatDate(d) {
    return d.toLocaleDateString(undefined, {
      month: "long",
      day: "numeric",
      year: "numeric"
    });
  }

  // ── Mount ───────────────────────────────────────────────────────
  function _ensureMount() {
    // Mount only inside the narrator chat region. If we're on the
    // Operator/Media tab the section won't exist or will be hidden,
    // and we just retry quietly.
    var container = document.getElementById("lvNarratorConversation");
    if (!container) return null;

    var existing = document.getElementById("lvClock");
    if (existing) return existing;

    var node = document.createElement("div");
    node.id = "lvClock";
    node.className = "lv-clock";
    node.setAttribute("aria-hidden", "true");  // decorative for screen readers
    node.innerHTML =
      '<div class="lv-clock-eyebrow">Right now</div>' +
      '<div class="lv-clock-time" data-clock-slot="time">--:--</div>' +
      '<div class="lv-clock-day" data-clock-slot="day">—</div>' +
      '<div class="lv-clock-date" data-clock-slot="date">—</div>' +
      '<div class="lv-clock-place" data-clock-slot="place" hidden>—</div>';
    container.appendChild(node);
    return node;
  }

  // ── Render ──────────────────────────────────────────────────────
  function _refresh() {
    var node = document.getElementById("lvClock") || _ensureMount();
    if (!node) return;

    var variant = _readVariant();
    if (variant === "OFF") {
      node.hidden = true;
      return;
    }
    node.hidden = false;

    // Reset variant classes; apply chosen one.
    node.classList.remove("lv-clock-variant-b",
                          "lv-clock-variant-c",
                          "lv-clock-variant-a");
    node.classList.add("lv-clock-variant-" + variant.toLowerCase());

    var d = new Date();
    var time  = _formatTime(d);
    var day   = _formatDayOfWeek(d);
    var date  = _formatDate(d);
    var place = _readLocation();

    var t = node.querySelector('[data-clock-slot="time"]');
    var w = node.querySelector('[data-clock-slot="day"]');
    var s = node.querySelector('[data-clock-slot="date"]');
    var p = node.querySelector('[data-clock-slot="place"]');
    if (t) t.textContent = time;
    if (w) w.textContent = day;
    if (s) s.textContent = date;
    if (p) {
      if (place) {
        p.textContent = place;
        p.hidden = false;
      } else {
        p.textContent = "";
        p.hidden = true;
      }
    }
  }

  // ── Init ────────────────────────────────────────────────────────
  var _retries = 0;
  function _initWhenReady() {
    var container = document.getElementById("lvNarratorConversation");
    if (container) {
      _refresh();
      // setInterval re-derives new Date() each tick — DST + clock-drift safe.
      setInterval(_refresh, TICK_MS);
      // Also refresh when the tab regains focus, so a long-idle narrator
      // doesn't see a stale time after they return.
      try {
        document.addEventListener("visibilitychange", function () {
          if (document.visibilityState === "visible") _refresh();
        });
      } catch (_) {}
      return;
    }
    if (++_retries < MOUNT_RETRY_LIMIT) {
      setTimeout(_initWhenReady, MOUNT_RETRY_MS);
    }
    // If we exhaust retries (operator-only session that never opens
    // the narrator tab), we silently stop. The clock is narrator-only
    // by design.
  }

  // Public refresh handle for operator dev (override location, change
  // variant via localStorage, then call this to apply immediately).
  try { window.lvClockRefresh = _refresh; } catch (_) {}

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initWhenReady, { once: true });
  } else {
    _initWhenReady();
  }
})();
