/* WO-LORI-NARRATOR-FOCUS-MODE-01 — interview focus mode for the narrator room.
 *
 * PRESENTATION ONLY, and the invariants are load-bearing:
 *
 *   1. No transport, no fetch, no state write, no read of anything the room
 *      does not already read. The production path stays ui/js/api.js →
 *      /api/chat/ws and is not referenced here.
 *   2. This module never reads or writes `turn_mode`, eligibility, or any
 *      Guard Lab surface. It proposes nothing.
 *   3. Entry and exit mutate NO narrator state. Entry is a class change plus
 *      three housekeeping steps. In particular it must never re-open or
 *      re-select the narrator: opening a narrator appends four `bio_facts`
 *      rows through `questionnaire_put` (BACKLOG §5, measured in Portable
 *      Narrator Phase 6 §36.1), and a presentation toggle must not fire it.
 *   4. The mode is NOT persisted. No localStorage, no server flag. A reload
 *      always restores the full operator UI — that is the anti-lockout
 *      property behind the chord-only exit, not an oversight. Do not
 *      "improve" it into a remembered preference.
 *   5. The mic state machine (WO-MIC-UI-02A), the turn-claim machine
 *      (WO-10H) and cognitive support (WO-10C) are untouched.
 *
 * NAME: `lv-narrator-focus`, deliberately NOT the spec's working name
 * `lv-interview-focus` — see the header of css/narrator-focus-mode.css for
 * the two shipped neighbours (`lv-interview-mode-active`, which has real
 * side effects, and `FocusCanvas`) that name would have been confused with.
 *
 * Selectors used here were pinned against the shipped page at implementation
 * (hornelore1.0.html, 2026-09-12): #lvNarratorTab / .lv-shell-panel-active
 * (app.js:676), #crChatInner (3515), #lv10dHeaderControls (2964),
 * window.isLlmReady (app.js:93), state.person_id (app.js:3823).
 */
(function () {
  "use strict";

  var BODY_CLASS = "lv-narrator-focus";
  var BTN_ID = "lvNarratorFocusBtn";
  var STATUS_ID = "lvNarratorFocusStatus";
  var CHAT_SCROLLER_ID = "crChatInner";
  var NARRATOR_PANEL_ID = "lvNarratorTab";

  /* The exit gesture. Three modifiers plus one key: unambiguously an
   * operator's hands, impossible to produce by voice or by touch, and not a
   * browser or OS binding on Windows/WSL, macOS or Linux. Documented
   * operator-side only — it has no on-screen affordance by design, because
   * the locked principles forbid a Return-to-Operator button in narrator
   * flow. Fail-open: a forgotten chord is never a lockout, because the mode
   * does not survive a reload. */
  var EXIT_CHORD = { ctrl: true, alt: true, shift: true, code: "KeyF" };
  var EXIT_CHORD_LABEL = "Ctrl + Alt + Shift + F";

  function el(id) { return document.getElementById(id); }
  function isActive() { return document.body.classList.contains(BODY_CLASS); }

  /* ── refusals ──────────────────────────────────────────────────────
   * Each returns a narrator-free, operator-facing reason string, or null
   * when the check passes. A refusal is a result: the operator stays in the
   * full UI and is told why. */

  function refusalReason() {
    // (a) A modal dialog may hold an unsaved edit. Focus mode must NEVER
    //     close one silently — discarding an operator's edit as a side
    //     effect of a presentation toggle would be its own defect. The check
    //     is the SELECTOR, not a name, so a dialog added next month is
    //     covered the same way. `memoirEditModal` is the known real hazard.
    var dlg = document.querySelector("dialog[open]");
    if (dlg) {
      return "Close the open dialog first (" + (dlg.id || "unnamed dialog") +
             ") — focus mode will not close it for you, in case it holds an unsaved edit.";
    }

    // (a2) The FocusCanvas capture overlay is a dialog in everything but tag
    //      name: `role="dialog" aria-modal="true"`, and `#fcTextarea` can hold
    //      text the narrator has typed but not submitted. It is NOT a native
    //      <dialog>, so the check above cannot see it. Same rule, same reason:
    //      never make un-submitted work vanish as a side effect of a
    //      presentation toggle. Open state is the shipped signal
    //      `#fcCanvas.fc-active` (focus-canvas.js:90) — read, never set.
    var fc = document.getElementById("fcCanvas");
    if (fc && fc.classList.contains("fc-active")) {
      return "Close the capture panel first — it may hold something the narrator has typed but not sent.";
    }

    // (b) The narrator room must be the surface on screen. Focus mode hides
    //     the tab strip, so entering from another tab would hide the way
    //     back to a room nobody had opened. We REFUSE rather than navigate:
    //     switching tabs for the operator is a side effect, and this WO has
    //     none.
    var panel = el(NARRATOR_PANEL_ID);
    if (!panel || !panel.classList.contains("lv-shell-panel-active")) {
      return "Open the Narrator Session tab first — focus mode presents the room that is already on screen.";
    }

    // (c) An active narrator. Read, never set: this must not select one.
    var pid = "";
    try { pid = (typeof state !== "undefined" && state && state.person_id) ? String(state.person_id) : ""; }
    catch (_) { pid = ""; }
    if (!pid) return "Choose a narrator first.";

    // (d) Readiness, from the authority the page already computes
    //     (app.js `isLlmReady`, the Phase Q.4 chat readiness gate). Focus
    //     mode hides the warmup banner, so entering during warmup would hand
    //     the narrator a beautiful screen with a dead composer and no
    //     explanation. No new authority, no new server read.
    var ready = true;
    try { if (typeof window.isLlmReady === "function") ready = !!window.isLlmReady(); }
    catch (_) { ready = false; }
    if (!ready) return "Lori is still warming up — wait for the session to be ready, then hand over the room.";

    return null;
  }

  /* ── housekeeping ──────────────────────────────────────────────────*/

  /* Close EVERY open native popover. Generic on purpose: the page has many
   * (Bug Panel, Memoir, Life Map, Trips, Transcript, Review Queue, Review
   * Help, Bio Builder, Bio Control Center, Settings, Delete Narrator…), they
   * all render in the TOP LAYER, and CSS on ordinary containers cannot cover
   * them. A hand-written list would go stale the first time someone adds
   * one; this covers a popover added next month without touching this code.
   * `:popover-open` is the platform's own answer — never `offsetParent`,
   * which is null for every top-layer element and has produced false
   * negatives in this repository before (CLAUDE.md, UI harness hazards). */
  function closeOpenPopovers() {
    var closed = [];
    var open;
    try { open = document.querySelectorAll("[popover]:popover-open"); }
    catch (_) { return closed; }      // very old engine: nothing to close
    Array.prototype.forEach.call(open, function (p) {
      try { if (typeof p.hidePopover === "function") { p.hidePopover(); closed.push(p.id || "(unnamed)"); } }
      catch (e) { console.warn("[lv-narrator-focus] hidePopover threw for", p.id, e); }
    });
    return closed;
  }

  function showStatus(msg) {
    var s = el(STATUS_ID);
    if (!s) { console.warn("[lv-narrator-focus] " + msg); return; }
    s.textContent = msg;
    s.hidden = false;
    if (showStatus._t) clearTimeout(showStatus._t);
    showStatus._t = setTimeout(function () { s.hidden = true; s.textContent = ""; }, 9000);
  }

  /* ── enter / exit ──────────────────────────────────────────────────*/

  function enter() {
    if (isActive()) return true;

    var reason = refusalReason();
    if (reason) {
      showStatus("Focus mode not started. " + reason);
      console.info("[lv-narrator-focus] entry refused:", reason);
      return false;
    }

    var closed = closeOpenPopovers();
    document.body.classList.add(BODY_CLASS);

    // Focus transfer. The entry control is inside the header this mode
    // hides, and browser focus must not be left on a hidden element. Move it
    // to the conversation scroller — a container, not the composer, so
    // entering does not itself imply "start typing". tabindex is set here
    // rather than in the markup so the element is not in the ordinary tab
    // order outside focus mode.
    var scroller = el(CHAT_SCROLLER_ID);
    if (scroller) {
      scroller.setAttribute("tabindex", "-1");
      try { scroller.focus({ preventScroll: true }); } catch (_) { scroller.focus(); }
    }

    console.info("[lv-narrator-focus] entered — exit with " + EXIT_CHORD_LABEL +
                 (closed.length ? " · closed popovers: " + closed.join(", ") : ""));
    return true;
  }

  function exit() {
    if (!isActive()) return false;
    document.body.classList.remove(BODY_CLASS);

    var scroller = el(CHAT_SCROLLER_ID);
    if (scroller) scroller.removeAttribute("tabindex");

    // Focus returns to the control that started the mode, so the operator's
    // keyboard position is where they left it.
    var btn = el(BTN_ID);
    if (btn) { try { btn.focus({ preventScroll: true }); } catch (_) { btn.focus(); } }

    console.info("[lv-narrator-focus] exited");
    return true;
  }

  /* ── the chord ─────────────────────────────────────────────────────
   * Capture phase so a focused textarea cannot swallow it. It fires only on
   * the exact combination and only while the mode is active: a single key,
   * ordinary typing, and any touch or mouse gesture on the transcript do
   * nothing. `event.code` is used rather than `key` because the shifted
   * character varies by layout. */
  function onKeyDown(e) {
    if (!isActive()) return;
    if (e.code !== EXIT_CHORD.code) return;
    if (!e.ctrlKey || !e.altKey || !e.shiftKey || e.metaKey) return;
    e.preventDefault();
    e.stopPropagation();
    exit();
  }
  document.addEventListener("keydown", onKeyDown, true);

  /* Belt and braces on invariant 4: if anything ever leaves the class on the
   * body in markup or a cached page, a load starts in the full UI. */
  function ensureOffAtLoad() { document.body.classList.remove(BODY_CLASS); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureOffAtLoad);
  } else {
    ensureOffAtLoad();
  }

  window.lvNarratorFocusEnter = enter;
  window.lvNarratorFocusExit = exit;
  window.lvNarratorFocusIsActive = isActive;
  window.lvNarratorFocusToggle = function () { return isActive() ? exit() : enter(); };
  // Exported for the DOM harness: refusal reasons are asserted by rendering
  // the real check, never by reimplementing it in a test.
  window.lvNarratorFocusRefusalReason = refusalReason;
  window.lvNarratorFocusChordLabel = EXIT_CHORD_LABEL;
})();
