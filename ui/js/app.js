/* ═══════════════════════════════════════════════════════════════
   app.js — init, people/profile, events, memoir, obituary,
            chat (WS/SSE), TTS, voice, layout toggles, utilities
   Lorevox v6.1
   Load order: LAST
═══════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════
   CHAT READINESS GATE — Phase Q.4
   Ensures Lori never speaks before the LLM is actually loaded and warm.
   The gate blocks onboarding, system prompts, and user chat sends
   until /api/warmup confirms the model can generate tokens.
═══════════════════════════════════════════════════════════════ */
let _llmReady = false;
let _llmWarmupPolling = false;

/* ── WO-9: Startup race fix — queue system prompts until model ready ── */
let _wo9QueuedSystemPrompt = null;

function wo9SendOrQueueSystemPrompt(prompt) {
  if (!_llmReady) {
    _wo9QueuedSystemPrompt = prompt;
    console.log("[WO-9] Queued system prompt until model ready. Length:", prompt.length);
    return false;
  }
  sendSystemPrompt(prompt);
  return true;
}

function wo9DrainQueuedSystemPrompt() {
  if (_wo9QueuedSystemPrompt && _llmReady) {
    const prompt = _wo9QueuedSystemPrompt;
    _wo9QueuedSystemPrompt = null;
    console.log("[WO-9] Draining queued system prompt.");
    sendSystemPrompt(prompt);
  }
}
window.wo9SendOrQueueSystemPrompt = wo9SendOrQueueSystemPrompt;
window.wo9DrainQueuedSystemPrompt = wo9DrainQueuedSystemPrompt;

/* ── Hornelore operator mode flag ───────────────────────────── */
window.HORNELORE_OPERATOR_MODE = window.HORNELORE_OPERATOR_MODE || false;

/* ── Hornelore: deleted-narrator skip list ──────────────────── */
function _horneloreGetDeletedLabels() {
  try {
    return JSON.parse(localStorage.getItem("hornelore_deleted_labels") || "[]");
  } catch (_) {
    return [];
  }
}

function _horneloreMarkDeletedNarrator(label) {
  if (!label) return;
  try {
    var arr = _horneloreGetDeletedLabels();
    if (arr.indexOf(label) < 0) arr.push(label);
    localStorage.setItem("hornelore_deleted_labels", JSON.stringify(arr));
  } catch (_) {}
}

function _horneloreClearDeletedNarrator(label) {
  if (!label) return;
  try {
    var arr = _horneloreGetDeletedLabels().filter(function(x) { return x !== label; });
    localStorage.setItem("hornelore_deleted_labels", JSON.stringify(arr));
  } catch (_) {}
}

// Expose for operator UI
window._horneloreMarkDeletedNarrator  = _horneloreMarkDeletedNarrator;
window._horneloreClearDeletedNarrator = _horneloreClearDeletedNarrator;
window._horneloreGetDeletedLabels     = _horneloreGetDeletedLabels;

/** True once the model has completed warmup and can generate. */
function isLlmReady() { return _llmReady; }
// Expose for tests and console inspection
window.isLlmReady = isLlmReady;

/** Allow tests to force the readiness flag (e.g., for offline/headless testing). */
function _forceModelReady() {
  _llmReady = true;
  _setWarmupBanner(false);
  pill("pillChat", true);
  const ci = document.getElementById("chatInput");
  if (ci) { ci.disabled = false; ci.placeholder = "Type or speak…"; }
  const sendBtn = document.getElementById("lv80SendBtn");
  if (sendBtn) sendBtn.disabled = false;
  console.log("[readiness] _forceModelReady — gate forced open.");
}
window._forceModelReady = _forceModelReady;

/** Show/hide the warmup banner overlay. */
function _setWarmupBanner(visible, message) {
  const banner = document.getElementById("lv80WarmupBanner");
  // WO-UI-SHELL-01: mirror banner state to the Operator tab readiness card.
  if (typeof lvUpdateOperatorReadiness === "function") {
    if (visible) {
      lvUpdateOperatorReadiness("pending",
        message || "Lori is getting ready…",
        "This can take a few minutes on first load.");
    } else {
      lvUpdateOperatorReadiness("ready", "Lori is ready.",
        "You can hand her the session when you're set.");
    }
  }
  if (!banner) return;
  if (visible) {
    banner.querySelector(".warmup-msg").textContent = message || "Hornelore is warming up…";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

/**
 * Poll /api/warmup until the model is loaded and can generate.
 * Resolves when ready. Shows UI feedback during the wait.
 */
async function pollModelReady() {
  if (_llmReady) return;
  if (_llmWarmupPolling) return; // prevent duplicate poll loops
  _llmWarmupPolling = true;

  const POLL_INTERVAL = 5000;  // 5s between attempts
  const MAX_WAIT      = 300000; // 5 minutes max
  const startedAt     = Date.now();

  _setWarmupBanner(true, "Hornelore is warming up — model loading…");
  pill("pillChat", false);

  // Disable chat input during warmup
  const ci = document.getElementById("chatInput");
  if (ci) { ci.disabled = true; ci.placeholder = "Model loading — chat will be available shortly…"; }
  const sendBtn = document.getElementById("lv80SendBtn");
  if (sendBtn) sendBtn.disabled = true;

  while (!_llmReady && (Date.now() - startedAt) < MAX_WAIT) {
    try {
      const res = await fetch(API.WARMUP, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: "Hello", max_new_tokens: 4 }),
        signal: AbortSignal.timeout(30000),
      });
      if (res.ok) {
        const j = await res.json();
        if (j.ok) {
          _llmReady = true;
          console.log("[readiness] Model warm and ready.", j.latency ? `Latency: ${j.latency}s` : "");
          break;
        }
      } else if (res.status === 507) {
        // CUDA OOM — fatal, stop polling
        console.error("[readiness] CUDA OOM during warmup — model cannot load.");
        _setWarmupBanner(true, "GPU memory error — please restart the backend.");
        _llmWarmupPolling = false;
        return;
      }
    } catch (e) {
      // Network error or timeout — backend not up yet, keep polling
      console.log("[readiness] Warmup poll failed (backend likely still loading):", e.message || e);
    }

    // Update banner with elapsed time
    const elapsed = Math.round((Date.now() - startedAt) / 1000);
    _setWarmupBanner(true, `Hornelore is warming up — model loading… (${elapsed}s)`);

    await new Promise(r => setTimeout(r, POLL_INTERVAL));
  }

  _llmWarmupPolling = false;

  if (_llmReady) {
    _setWarmupBanner(false);
    pill("pillChat", true);
    // Re-enable chat input
    if (ci) { ci.disabled = false; ci.placeholder = "Type or speak…"; }
    if (sendBtn) sendBtn.disabled = false;
    // Fire deferred startup actions
    _onModelReady();
  } else {
    console.warn("[readiness] Model did not become ready within 5 minutes.");
    _setWarmupBanner(true, "Model warmup timed out — please check the backend.");
  }
}

/** Called once when model transitions to ready. Triggers deferred onboarding/narrator flow. */
function _onModelReady() {
  console.log("[readiness] _onModelReady — firing deferred startup.");
  // WO-9: Drain any system prompt that was queued during startup race
  wo9DrainQueuedSystemPrompt();
  // v9: Startup neutrality — always open narrator selector on ready.
  console.log("[readiness] v9 — startup neutral. Opening narrator selector.");
  // WO-UI-SHELL-01: paint readiness card green once warm.
  if (typeof lvUpdateOperatorReadiness === "function") {
    lvUpdateOperatorReadiness("ready", "Lori is ready.", "You can hand her the session when you're set.");
  }
  setTimeout(() => {
    if (typeof lv80OpenNarratorSwitcher === "function") lv80OpenNarratorSwitcher();
  }, 400);
}

/* ═══════════════════════════════════════════════════════════════
   WO-UI-SHELL-01 — Three-tab shell wiring.
   Operator | Narrator Session | Media.  Startup lands on Operator.
   Session style is a state + persistence + label only concern in
   Phase 1; WO-NARRATOR-ROOM-01 and a future prompt-composer WO will
   route it into Lori's behavior.  Do NOT overload currentMode.
═══════════════════════════════════════════════════════════════ */

const LV_SESSION_STYLE_KEY = "hornelore_session_style_v1";
// memory_exercise dropped 2026-04-25 — picker no-op, shelved.
const LV_VALID_SESSION_STYLES = [
  "questionnaire_first", "clear_direct", "warm_storytelling", "companion",
];

/** Read the current session style.  Defaults to warm_storytelling. */
function getSessionStyle() {
  return (state && state.session && state.session.sessionStyle) || "warm_storytelling";
}
window.getSessionStyle = getSessionStyle;

/**
 * Persist a session style selection.  Updates state.session.sessionStyle
 * (NOT currentMode — those are different abstractions) and mirrors the
 * choice to localStorage so it survives reload.
 */
function lvSetSessionStyle(value) {
  if (!LV_VALID_SESSION_STYLES.includes(value)) {
    console.warn("[lv-shell] ignored invalid session style:", value);
    return;
  }
  if (!state.session) state.session = {};
  // BUG-SESSION-STYLE-SWITCH-STALE-QF-STATE-01 (2026-05-06):
  // Clear stale QF/loop state when transitioning AWAY from a lane.
  // Without this, switching questionnaire_first → clear_direct (or any
  // other style) leaves behind:
  //   - state.session.questionnaireFirst.{active, segment, currentSection,
  //     currentField, askedKeys}
  //   - state.session.loop.{activeIntent, currentSection, currentField,
  //     askedKeys, savedKeys, tellingStoryOnce, lastAction}
  // which causes downstream behavior (subsequent narrator turns, opener
  // dispatch, runtime71 builders) to read stale ownership flags and
  // act as if the prior lane were still active. Live evidence
  // 2026-05-06 12:30+ — operator switched QF → clear_direct mid-session
  // and Lori's responses showed mixed behavior: deterministic era
  // explainer fired sometimes, generic LLM improvisation other times.
  // Diagnosis: stale QF substate biased the LLM context even after the
  // dispatcher routed through warm_storytelling.
  const _prevStyle = state.session.sessionStyle || null;
  if (_prevStyle && _prevStyle !== value) {
    console.log("[session-style] transition", _prevStyle, "→", value, "— clearing stale lane state");
    // Clear QF substate completely; it will re-init on next QF entry
    if (state.session.questionnaireFirst) {
      delete state.session.questionnaireFirst;
    }
    // Clear loop substate selectively — preserve the dispatcher's
    // ledgers but reset lane-ownership flags. lvSessionLoopOnTurn will
    // re-init missing fields lazily.
    if (state.session.loop) {
      state.session.loop.activeIntent = null;
      state.session.loop.currentSection = null;
      state.session.loop.currentField = null;
      state.session.loop.askedKeys = [];
      state.session.loop.tellingStoryOnce = false;
      state.session.loop.lastAction = "lane_transition_reset:" + _prevStyle + "_to_" + value;
    }
  }
  state.session.sessionStyle = value;
  try { localStorage.setItem(LV_SESSION_STYLE_KEY, value); } catch (_) {}
  // Sync the radio group in case this was a programmatic call.
  const radios = document.querySelectorAll('input[name="lvSessionStyle"]');
  radios.forEach(r => { r.checked = (r.value === value); });
  console.log("[lv-shell] sessionStyle =", value);
}
window.lvSetSessionStyle = lvSetSessionStyle;

/** Hydrate session style from localStorage (or default) and paint radios. */
function _lvHydrateSessionStyle() {
  let saved = null;
  try { saved = localStorage.getItem(LV_SESSION_STYLE_KEY); } catch (_) {}
  const value = (saved && LV_VALID_SESSION_STYLES.includes(saved)) ? saved : "warm_storytelling";
  if (!state.session) state.session = {};
  state.session.sessionStyle = value;
  const radios = document.querySelectorAll('input[name="lvSessionStyle"]');
  radios.forEach(r => { r.checked = (r.value === value); });
}

/* ═══════════════════════════════════════════════════════════════
   WO-10C Cognitive Support Mode operator UI toggle (2026-05-06)
   ═══════════════════════════════════════════════════════════════
   Wires the `<input id="lvOperatorCsmToggle">` checkbox to
   state.session.cognitiveSupportMode + a PER-NARRATOR localStorage
   mirror so each narrator carries their own pacing preference.
   Janice and Kent need CSM ON; Christopher might prefer OFF; the
   operator's choice should follow the narrator they're talking to,
   not the operator's session.

   Storage key shape: `lv_csm:<person_id>` — namespaced per narrator.
   On narrator switch, the narrator-load path calls
   `lvHydrateCognitiveSupportModeForNarrator(person_id)` which
   reads the per-narrator key and updates state + checkbox.

   The mode immediately affects:
     - lv80FireCheckIn idle-cue cadence:
         CSM: 120s visual / 300s gentle invitation / 600s re-entry bridge
         Standard (elderly default, _wo08IsElderly()=true):
           60s visual / 120s gentle (open mode) or 90s (memory mode)
         Standard (non-elderly):
           30s visual / 75s gentle (open mode) or 55s (memory mode)
       See ui/hornelore1.0.html WO10C_* constants + _LV80_IDLE_*
       function definitions for the source of truth.
     - runtime71's cognitive_support_mode field per app.js:2136
       which propagates to Lori's prompt composition and silence
       handling on the server.
═══════════════════════════════════════════════════════════════ */

const LV_CSM_KEY_PREFIX = "lv_csm:";  // followed by person_id
// Operator-default fallback when no narrator is loaded yet (e.g.,
// Operator tab open before any narrator card click). Migrating from
// the old global "lv_cognitive_support_mode" key falls under
// _lvHydrateCognitiveSupportMode below.
const LV_CSM_KEY_OPERATOR_DEFAULT = "lv_csm:_operator_default_";
const LV_CSM_KEY_LEGACY_GLOBAL    = "lv_cognitive_support_mode";

function _lvCsmKeyFor(personId) {
  const pid = (personId || (state && state.person_id) || "").trim();
  if (!pid) return LV_CSM_KEY_OPERATOR_DEFAULT;
  return LV_CSM_KEY_PREFIX + pid;
}

function lvSetCognitiveSupportModeFromUi(on){
  const v = !!on;
  if (typeof setCognitiveSupportMode === "function") {
    setCognitiveSupportMode(v);
  } else if (state && state.session) {
    state.session.cognitiveSupportMode = v;
  }
  // Per-narrator persistence — namespaced by person_id (or operator-
  // default when no narrator is loaded yet). When the operator
  // switches narrators, lvHydrateCognitiveSupportModeForNarrator
  // reads the new narrator's key and re-paints the checkbox.
  try { localStorage.setItem(_lvCsmKeyFor(), v ? "1" : "0"); } catch (_) {}
  // Update the runtime71 mirror immediately so the next chat turn
  // carries the new mode (no waiting for narrator turn to refresh state).
  if (state && state.runtime) {
    state.runtime.cognitive_support_mode = v;
  }
  console.log("[wo10c][csm-toggle] cognitiveSupportMode =", v, " key=", _lvCsmKeyFor());
  // Re-arm idle timers so the new cadence (or default cadence) takes
  // effect immediately. lv80ClearIdle + lv80ArmIdle are defined in
  // hornelore1.0.html. Wrap in try/catch in case timing is off and
  // they aren't loaded yet during early hydration.
  try {
    if (typeof lv80ClearIdle === "function") lv80ClearIdle();
    if (typeof lv80ArmIdle === "function") lv80ArmIdle();
  } catch (e) {
    console.warn("[wo10c][csm-toggle] idle-rearm threw:", e);
  }
}
window.lvSetCognitiveSupportModeFromUi = lvSetCognitiveSupportModeFromUi;

/** Hydrate CSM on page load (no narrator loaded yet). Reads operator-
 *  default key and migrates the legacy global key if present. */
function _lvHydrateCognitiveSupportMode() {
  let saved = null;
  try {
    // One-time migration: if legacy global key is set and the new
    // operator-default key is not, copy the value forward. Then drop
    // the legacy key so subsequent reads use the new shape.
    const legacy = localStorage.getItem(LV_CSM_KEY_LEGACY_GLOBAL);
    const newDefault = localStorage.getItem(LV_CSM_KEY_OPERATOR_DEFAULT);
    if (legacy != null && newDefault == null) {
      localStorage.setItem(LV_CSM_KEY_OPERATOR_DEFAULT, legacy);
      localStorage.removeItem(LV_CSM_KEY_LEGACY_GLOBAL);
      console.log("[wo10c][csm-toggle] migrated legacy global key → operator default");
    }
    saved = localStorage.getItem(LV_CSM_KEY_OPERATOR_DEFAULT);
  } catch (_) {}
  const v = (saved === "1");
  _lvApplyCognitiveSupportMode(v);
}

/** Hydrate CSM for a SPECIFIC narrator after their card opens. Called
 *  from the narrator-switch path so each narrator carries their own
 *  CSM preference. Falls back to the operator default if the narrator
 *  has no per-narrator setting yet. */
function lvHydrateCognitiveSupportModeForNarrator(personId) {
  let saved = null;
  try {
    saved = localStorage.getItem(_lvCsmKeyFor(personId));
    if (saved == null) {
      // Fall back to operator default for first-touch narrators.
      saved = localStorage.getItem(LV_CSM_KEY_OPERATOR_DEFAULT);
    }
  } catch (_) {}
  const v = (saved === "1");
  _lvApplyCognitiveSupportMode(v);
  console.log("[wo10c][csm-toggle] hydrated for narrator pid=" + (personId || "—") + " v=" + v);
  return v;
}
window.lvHydrateCognitiveSupportModeForNarrator = lvHydrateCognitiveSupportModeForNarrator;

/** Apply a CSM value to state + runtime71 + checkbox. Shared helper. */
function _lvApplyCognitiveSupportMode(v) {
  if (typeof setCognitiveSupportMode === "function") {
    setCognitiveSupportMode(v);
  } else if (state && state.session) {
    state.session.cognitiveSupportMode = v;
  }
  if (state && state.runtime) {
    state.runtime.cognitive_support_mode = v;
  }
  const cb = document.getElementById("lvOperatorCsmToggle");
  if (cb) cb.checked = v;
}

/** Which tab is currently visible. */
function lvShellGetActiveTab() {
  const active = document.querySelector("#lvShellTabs .lv-shell-tab-active");
  return active ? active.dataset.tab : "operator";
}
window.lvShellGetActiveTab = lvShellGetActiveTab;

/**
 * Switch to the named tab.  Safe to call before init (no-op if the DOM
 * isn't present yet).  Updates aria-selected on both tab buttons and
 * panel visibility via the .lv-shell-panel-active class.
 */
function lvShellShowTab(tabName) {
  const nav = document.getElementById("lvShellTabs");
  if (!nav) return;
  const tabs   = nav.querySelectorAll(".lv-shell-tab");
  const panels = document.querySelectorAll(".lv-shell-panel");
  tabs.forEach(t => {
    const isActive = t.dataset.tab === tabName;
    t.classList.toggle("lv-shell-tab-active", isActive);
    t.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  panels.forEach(p => {
    const isActive = p.id === `lv${tabName.charAt(0).toUpperCase()}${tabName.slice(1)}Tab` ||
                     p.id === `lv${tabName === "narrator" ? "Narrator" : tabName === "operator" ? "Operator" : "Media"}Tab`;
    p.classList.toggle("lv-shell-panel-active", isActive);
  });
  // Reflect on body for any CSS hooks.
  try { document.body.setAttribute("data-shell-tab", tabName); } catch (_) {}
  // Media tab preflight — single-shot probe for /api/photos so we can
  // surface the "not enabled" hint without navigating away.
  if (tabName === "media") _lvMediaPreflightOnce();
  // Narrator room upkeep — repaint identity + controls on entry; start
  // a light tick so mic/camera state stays synced while we're here.
  if (tabName === "narrator") {
    if (typeof _lvNarratorPaintIdentity === "function") _lvNarratorPaintIdentity();
    if (typeof _lvNarratorPaintControls === "function") _lvNarratorPaintControls();
    _lvNarratorStartPaintTick();
    // WO-PARENT-SESSION-HARDENING-01 Phase 5 — Life Map cold-start fix.
    // Live audit (2026-05-01) confirmed the bug: shell-tab navigation
    // ("Narrator Session" tab click) only paints identity/controls; it
    // does NOT call lvNarratorRoomInit, so _lvInterviewRenderLifeMap
    // never fires and #lvInterviewLifeMap stays empty. Only the explicit
    // "Start Narrator Session" button (lvStartNarratorSession) hits the
    // room init. Result: the right-rail Life Map is blank for any
    // operator who navigates via the tab strip — exactly the cold-start
    // repro Chris flagged. Fix: render the Life Map column on every
    // narrator-tab activation when a narrator is selected. The render
    // function already RAF-retries if the host element hasn't mounted
    // yet (see _lvInterviewRenderLifeMap above), so this is safe to
    // call eagerly. No-ops cleanly when person_id is unset.
    if (state && state.person_id && typeof _lvInterviewRenderLifeMap === "function") {
      try { _lvInterviewRenderLifeMap(); }
      catch (e) { console.warn("[life-map] render on tab-switch threw:", e); }
    }
    // Anchor to latest when entering (in case user was reading old messages).
    setTimeout(() => { if (typeof lvNarratorScrollToBottom === "function") lvNarratorScrollToBottom(true); }, 60);
  } else {
    _lvNarratorStopPaintTick();
  }
}
window.lvShellShowTab = lvShellShowTab;

/** One-shot init — hydrate session style, land on Operator, install tab handlers. */
function lvShellInitTabs() {
  _lvHydrateSessionStyle();
  // WO-10C: hydrate cognitive support mode toggle from localStorage so
  // the operator's prior choice survives reload + paints the checkbox.
  try { _lvHydrateCognitiveSupportMode(); } catch (e) {
    console.warn("[wo10c][csm-toggle] hydrate threw (non-fatal):", e);
  }
  lvShellShowTab("operator");
  // Mirror warmup banner state to the readiness card on boot.
  const banner = document.getElementById("lv80WarmupBanner");
  if (banner && !banner.classList.contains("hidden")) {
    const msg = banner.querySelector(".warmup-msg");
    lvUpdateOperatorReadiness("pending",
      (msg && msg.textContent) || "Lori is getting ready…",
      "This can take a few minutes on first load.");
  } else if (typeof isLlmReady === "function" && isLlmReady()) {
    lvUpdateOperatorReadiness("ready", "Lori is ready.",
      "You can hand her the session when you're set.");
  }
}
window.lvShellInitTabs = lvShellInitTabs;

/**
 * Update the readiness card on the Operator tab.  Safe if the card
 * isn't in the DOM (returns silently).
 *   state: "pending" | "ready" | "error"
 */
function lvUpdateOperatorReadiness(readyState, label, sub) {
  const card = document.getElementById("lvOperatorReadiness");
  if (!card) return;
  card.setAttribute("data-ready", readyState || "pending");
  const lbl = document.getElementById("lvOperatorReadinessLabel");
  const sbl = document.getElementById("lvOperatorReadinessSub");
  if (lbl && label) lbl.textContent = label;
  if (sbl && sub)   sbl.textContent = sub;
  // Reflect on the Start button.
  const btn = document.getElementById("lvOperatorStartBtn");
  if (btn) btn.disabled = (readyState !== "ready");
}
window.lvUpdateOperatorReadiness = lvUpdateOperatorReadiness;

/**
 * Hand the session to Lori — switch to the Narrator tab and call the
 * narrator-room init hook if WO-NARRATOR-ROOM-01 has installed one.
 * Requires an active narrator; if none is set, nudge the operator to
 * pick one first.
 */
function lvStartNarratorSession() {
  const hint = document.getElementById("lvOperatorStartHint");
  const hasNarrator = !!(state && state.person_id);
  if (!hasNarrator) {
    if (hint) { hint.hidden = false; hint.textContent = "Choose a narrator first."; }
    // Also pop the switcher if it's available.
    if (typeof lv80OpenNarratorSwitcher === "function") lv80OpenNarratorSwitcher();
    return;
  }
  if (hint) hint.hidden = true;
  lvShellShowTab("narrator");
  if (typeof window.lvNarratorRoomInit === "function") {
    try { window.lvNarratorRoomInit(); } catch (e) { console.warn("[lv-shell] lvNarratorRoomInit threw:", e); }
  }
}
window.lvStartNarratorSession = lvStartNarratorSession;

/**
 * Media tab launchers.  Phase 1: open existing photo pages.  The
 * Photo Session requires an active narrator so the elicit page can
 * bind the right narrator_id.
 */
function lvOpenMediaTool(tool) {
  const noteEl = document.getElementById("lvMediaDisabledNote");
  switch (tool) {
    case "photo_intake":
      window.open("photo-intake.html", "_blank", "noopener");
      break;
    case "photo_timeline":
      window.open("photo-timeline.html", "_blank", "noopener");
      break;
    case "photo_session": {
      const pid = state && state.person_id;
      if (!pid) {
        if (noteEl) { noteEl.hidden = false; noteEl.textContent = "Choose a narrator before starting a photo session."; }
        if (typeof lv80OpenNarratorSwitcher === "function") lv80OpenNarratorSwitcher();
        return;
      }
      window.open(`photo-elicit.html?narrator_id=${encodeURIComponent(pid)}`, "_blank", "noopener");
      break;
    }
    // WO-MEDIA-ARCHIVE-01 — Document Archive lane (PDFs, scanned docs,
    // genealogy outlines, handwritten notes, certificates, clippings).
    // Distinct from Photo Intake which is image-only memory prompts;
    // this surface accepts PDFs and is gated behind a separate flag
    // (HORNELORE_MEDIA_ARCHIVE_ENABLED). Narrator is optional — many
    // archive items aren't bound to a specific person at intake time.
    case "document_archive":
      window.open("media-archive.html", "_blank", "noopener");
      break;
    default:
      console.warn("[lv-shell] unknown media tool:", tool);
  }
}
window.lvOpenMediaTool = lvOpenMediaTool;

/** One-shot preflight for Media tab — hides the "not enabled" note
    when HORNELORE_PHOTO_ENABLED is on, shows it when off.
    Uses /api/photos/health which returns {ok, enabled} regardless of
    the flag (the photo surface 404s the list/mutate routes when off,
    but /health is intentionally flag-agnostic). */
let _lvMediaPreflightDone = false;
async function _lvMediaPreflightOnce() {
  if (_lvMediaPreflightDone) return;
  _lvMediaPreflightDone = true;
  const note = document.getElementById("lvMediaDisabledNote");
  if (!note) return;
  try {
    // BUG-PHOTO-CORS-01: must use ORIGIN (port 8000) — page is served
    // from port 8082 (hornelore-serve.py), so a bare relative path goes
    // to the static UI server which doesn't have any /api/* routes.
    const res = await fetch(ORIGIN + "/api/photos/health", { method: "GET" });
    let enabled = false;
    if (res.ok) {
      const j = await res.json();
      enabled = !!(j && j.enabled);
    }
    if (enabled) { note.hidden = true; }
    else { note.hidden = false; note.textContent = "Photo tools are not enabled for this run."; }
  } catch (_) {
    // Leave note hidden on network error — don't block the launcher cards.
  }
}

/* ═══════════════════════════════════════════════════════════════
   WO-NARRATOR-ROOM-01 — Narrator session room.
   Topbar (identity + Mic/Camera/Pause/Break) → view tabs (Memory
   River | Life Map | Photos | Peek at Memoir) → 3-column main.
   Controls delegate to existing entry points (lv10dToggleMic,
   lv10dToggleCamera, lv80TogglePauseListening); Take-a-break is a
   new overlay.  Chat scroll uses FocusCanvas's existing _scrollToLatest.
═══════════════════════════════════════════════════════════════ */

const LV_NARRATOR_SESSION_STYLE_LABELS = {
  questionnaire_first: "Questionnaire first",
  clear_direct:        "Clear & direct",
  warm_storytelling:   "Warm storytelling",
  // memory_exercise dropped 2026-04-25 — kept as legacy fallback label
  // for narrators with saved sessionStyle="memory_exercise" that haven't
  // yet been redirected by session-style-router on next load.
  memory_exercise:     "Warm storytelling",
  companion:           "Companion",
};

/** Paint the topbar identity (narrator name + session style pill). */
function _lvNarratorPaintIdentity() {
  const nameEl  = document.getElementById("lvNarratorRoomName");
  const styleEl = document.getElementById("lvNarratorRoomStyle");
  if (nameEl) {
    const header = document.getElementById("lv80ActiveNarratorName");
    nameEl.textContent = (header && header.textContent) || "—";
  }
  if (styleEl) {
    const v = (typeof getSessionStyle === "function") ? getSessionStyle() : "warm_storytelling";
    styleEl.textContent = LV_NARRATOR_SESSION_STYLE_LABELS[v] || v;
  }
}
window._lvNarratorPaintIdentity = _lvNarratorPaintIdentity;

/** Return the current narrator view name. */
function lvNarratorCurrentView() {
  return (state && state.session && state.session.narratorView) || "map";
}

/** Switch narrator-room view. */
function lvNarratorShowView(view) {
  if (!["map", "photos", "memoir"].includes(view)) return;
  if (!state.session) state.session = {};
  state.session.narratorView = view;
  // Paint tab active state.
  document.querySelectorAll(".lv-narrator-view-tab").forEach(t => {
    const isActive = t.dataset.view === view;
    t.classList.toggle("lv-narrator-view-tab-active", isActive);
    t.setAttribute("aria-selected", isActive ? "true" : "false");
  });
  // Render view content.
  switch (view) {
    case "map":    _lvNarratorRenderMap();    break;
    case "photos": _lvNarratorRenderPhotos(); break;
    case "memoir": _lvNarratorRenderMemoir(); break;
  }
}
window.lvNarratorShowView = lvNarratorShowView;

/* ── View renderers ──────────────────────────────────────────────
   All renderers write into #lvNarratorViewHost.  Life Map + Memoir
   reuse existing popovers via a "Open full" CTA. The chronology
   accordion (#crAccordionCol) on the LEFT side of the chat is the
   primary timeline surface — Memory River was removed. */

function _lvNarratorRenderMap() {
  const host = document.getElementById("lvNarratorViewHost");
  if (!host) return;
  host.innerHTML = `
    <h3 class="lv-narrator-view-head">Life Map</h3>
    <p class="lv-narrator-view-lede">A picture of the places and eras in your life. Tap an era to tell Lori about that time.</p>
    <button type="button" class="lv-narrator-view-cta"
      onclick="document.getElementById('lifeMapPopover')?.showPopover?.()">
      Open your Life Map
    </button>
    <p class="lv-narrator-view-empty" style="margin-top:12px;">Full map will live here in the next update (Phase 2).</p>
  `;
}

function _lvNarratorRenderMemoir() {
  const host = document.getElementById("lvNarratorViewHost");
  if (!host) return;
  host.innerHTML = `
    <h3 class="lv-narrator-view-head">Peek at Memoir</h3>
    <p class="lv-narrator-view-lede">Read what we have so far, in your own words.</p>
    <button type="button" class="lv-narrator-view-cta"
      onclick="document.getElementById('memoirScrollPopover')?.showPopover?.()">
      Open your memoir
    </button>
  `;
}

/* ─── WO-INTERVIEW-MODE-01 Phase 1 ──────────────────────────────────
   Interview Mode: full-screen 3-column view for real narrator sessions.
   Operator chrome (shell tabs, view tabs, Bug Panel buttons) hides via
   body.lv-interview-mode-active CSS. Chat / mic / camera state machines
   keep running unchanged underneath.

   Era data: pulls from state.timeline.spine.periods (life eras with
   start_year/end_year/label) + state.timeline.memories (year-tagged
   items) — same data source the Life Map uses, multi-schema defensive.

   Phase 1 NOT-doing:
   - Lori composer awareness of activeFocusEra (SESSION-AWARENESS Phase 2)
   - Auto-enter after identity_complete (operator stays in control)
   - Hands-free / silence ladder behavior (SESSION-AWARENESS Phase 4)
*/

function _lvInterviewYearOf(m) {
  if (!m) return null;
  const raw = m.year       != null ? m.year
            : m.start_year != null ? m.start_year
            : m.ts         != null ? m.ts
            : m.date       != null ? m.date
            : m.when       != null ? m.when
            : null;
  if (raw == null) return null;
  if (typeof raw === "number" && isFinite(raw)) return raw;
  const match = String(raw).match(/\b(18|19|20)\d{2}\b/);
  return match ? parseInt(match[0], 10) : null;
}

function _lvInterviewPeriods() {
  if (typeof state === "undefined") return [];
  const periods = (state.timeline && state.timeline.spine && Array.isArray(state.timeline.spine.periods))
    ? state.timeline.spine.periods : [];
  return periods.filter(p => p && typeof p.label === "string" && p.label.trim() !== "");
}

// WO-PARENT-SESSION-HARDENING-01 Phase 5.1 — render-retry counter for
// cold-start race. When this function fires before the right-rail aside
// has mounted (rare but observed in questionnaire_first cold-start per
// 2026-05-01 audit), we retry once on RAF. Bounded retries; never spins.
let _lvInterviewLifeMapRetry = 0;

function _lvInterviewRenderLifeMap() {
  const host = document.getElementById("lvInterviewLifeMap");
  if (!host) {
    if (_lvInterviewLifeMapRetry < 3) {
      _lvInterviewLifeMapRetry += 1;
      console.warn("[life-map] render: host #lvInterviewLifeMap not found, retry " +
        _lvInterviewLifeMapRetry + " on RAF");
      requestAnimationFrame(_lvInterviewRenderLifeMap);
    } else {
      console.error("[life-map] render: host #lvInterviewLifeMap missing after 3 retries; aborting render");
    }
    return;
  }
  _lvInterviewLifeMapRetry = 0;  // reset on successful resolution
  const periods = _lvInterviewPeriods();
  const activeId = (state.session && state.session.activeFocusEra) || null;

  // WO-CANONICAL-LIFE-SPINE-01 Step 3d: activeFocusEra now stores bare
  // canonical era_id strings (earliest_years, …, today) instead of
  // "era:Label" composites. The button keys are canonical era_ids; the
  // display label comes from window.LorevoxEras.eraIdToWarmLabel(). Keeps
  // the Life Map column rendering when state.timeline.spine.periods isn't
  // populated yet (fresh narrator) — defaults derive from LV_ERAS itself
  // so the spine taxonomy lives in exactly one place.
  const defaultEraIds = (window.LorevoxEras && Array.isArray(window.LorevoxEras.LV_ERAS))
    ? window.LorevoxEras.LV_ERAS
        .filter(e => e.era_id !== "today")
        .map(e => e.era_id)
    : ["earliest_years", "early_school_years", "adolescence",
       "coming_of_age", "building_years", "later_years"];

  // Period.label/era_id is canonical after Step 3d's initTimelineSpine
  // migration; canonicalize defensively for any stale cached spine.
  const _toEraId = (v) => (typeof _canonicalEra === "function") ? _canonicalEra(v) : v;
  const eraIds = periods.length
    ? periods.map(p => _toEraId(p.era_id || p.label)).filter(Boolean)
    : defaultEraIds;

  const _warm = (eid) => (window.LorevoxEras && typeof window.LorevoxEras.eraIdToWarmLabel === "function")
    ? window.LorevoxEras.eraIdToWarmLabel(eid)
    : eid;

  let body = `<h3 class="lv-interview-lifemap-head">Life Map</h3>`;
  eraIds.forEach((eid) => {
    const active = (activeId === eid) ? " is-active" : "";
    // WO-CANONICAL-LIFE-SPINE-01 Step 7: route through the confirmation
    // popover so a click doesn't silently move Lori. Continue → commit;
    // Cancel → no state change. _lvInterviewConfirmEra delegates to
    // _lvInterviewSelectEra on Continue, preserving the canonical-only
    // write boundary.
    // WO-PARENT-SESSION-HARDENING-01 Phase 5.2 — data-era-id attribute
    // so harness + test pack can observe button state without parsing
    // localized warm labels.
    // BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 root cause (2026-05-03 v4):
    // The onclick used `${JSON.stringify(eid)}` which produces a
    // literal double-quoted string ("coming_of_age") — but the
    // surrounding HTML attribute is ALSO double-quoted, so the
    // browser's HTML parser ended the attribute value at the first
    // inner double quote. The onclick became "_lvInterviewConfirmEra("
    // (broken JS, never executes) and the rest became garbage
    // attribute leftovers. Today worked because it uses single
    // quotes manually (line below). Match the Today pattern with
    // single-quoted string and escape any embedded apostrophe via
    // _lvEscapeHtml so era_ids stay safe even if the schema ever
    // adds an era like "o'clock_years".
    body += `<button type="button" class="lv-interview-lifemap-era-btn${active}"
                     data-era-id="${_lvEscapeHtml(eid)}"
                     aria-pressed="${activeId === eid ? "true" : "false"}"
                     onclick="_lvInterviewConfirmEra('${_lvEscapeHtml(eid)}')">
      ${_lvEscapeHtml(_warm(eid))}
    </button>`;
  });

  // Today anchor — clickable, fires the same focus event as the era buttons.
  // Stores the canonical era_id "today" (no era: prefix) on click. Today
  // also routes through the confirmation popover (Step 7) so the
  // present-life bucket can't be selected accidentally either.
  const todayActive = (activeId === "today") ? " is-active" : "";
  body += `<h3 class="lv-interview-lifemap-today-head">Today</h3>
    <button type="button" class="lv-interview-lifemap-era-btn${todayActive}"
            data-era-id="today"
            aria-pressed="${activeId === "today" ? "true" : "false"}"
            onclick="_lvInterviewConfirmEra('today')">
      Today
    </button>`;

  // Inline Peek-at-Memoir card — replaces the bottom-right floater.
  // Sits below the Life Map column so the right-side surface in both
  // narrator-session and interview-mode views matches Chris's mockup
  // (Life Map era buttons + Today + Peek card stacked vertically).
  body += `<div class="lv-interview-peek-inline">
    <div class="lv-interview-peek-floater-title">Peek at Memoir</div>
    <div class="lv-interview-peek-floater-body" id="lvInterviewPeekFloaterBody">"Your story will appear here as you tell it…"</div>
    <button type="button" class="lv-interview-peek-floater-btn"
            onclick="document.getElementById('memoirScrollPopover')?.showPopover?.()">
      Open memoir
    </button>
  </div>`;

  host.innerHTML = body;

  // WO-PARENT-SESSION-HARDENING-01 Phase 5.1 — render-success log marker.
  // Test pack TEST-07 (cold-start) greps for this. Logs era count + active
  // selection so a successful render is observable without DOM inspection.
  console.info("[life-map] rendered: " + eraIds.length + " eras, active=" +
    (activeId || "none") + ", today=" + (activeId === "today" ? "active" : "inactive"));
}

function _lvInterviewActiveFocusLabel(eraId) {
  if (!eraId) return "—";
  // WO-CANONICAL-LIFE-SPINE-01 Step 3d: eraId is now a bare canonical
  // era_id ("earliest_years", "today", etc.). Render via the canonical
  // warm-label map so today gets "Today", earliest_years gets "Earliest
  // Years", etc. — no more "era:" + label string-matching.
  if (window.LorevoxEras && typeof window.LorevoxEras.eraIdToWarmLabel === "function") {
    return window.LorevoxEras.eraIdToWarmLabel(eraId) || "—";
  }
  return eraId;
}

function _lvInterviewSelectEra(eid) {
  if (!state.session) state.session = {};
  // WO-CANONICAL-LIFE-SPINE-01 Step 3d: canonicalize at the boundary so
  // any stray legacy or "era:"-prefixed input from an older bookmarked
  // page or external caller still lands as a bare canonical era_id in
  // state.session.activeFocusEra.
  const canonical = (typeof _canonicalEra === "function") ? _canonicalEra(eid) : eid;
  // WO-PARENT-SESSION-HARDENING-01 Phase 5.2 — required console marker
  // for life-map era clicks. Appears on every era-button-driven select
  // (NOT on programmatic state-only writes). Test pack TEST-08 greps
  // for this marker.
  const _prevCurrent = (state.session && state.session.currentEra) || "null";
  const _prevActive  = (state.session && state.session.activeFocusEra) || "null";
  console.info("[life-map][era-click] era=" + (canonical || "null") +
    " prev_active=" + _prevActive + " prev_current=" + _prevCurrent);
  state.session.activeFocusEra = canonical || null;

  // BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 (2026-05-03): the era button only
  // wrote activeFocusEra. The canonical interview-era cursor lives at
  // state.session.currentEra (managed by setEra() in state.js). Without
  // this write, runtime71's current_era stayed stale and the chronology
  // accordion / interview pass code couldn't see the new era.
  //
  // BUG-LIFEMAP-STATE-WRITE-01 (2026-05-03 v2 — Shatner cascade evidence):
  // shatner_cascade_v1 confirmed era_click_log_seen=true,
  // lori_prompt_log_seen=true, lori_replied=true — BUT
  // state.session.currentEra read back as "" empty. The setEra() call
  // either threw silently in the try/catch OR something downstream
  // wiped the value. Belt-and-suspenders: write currentEra DIRECTLY
  // (canonical, never null-empty) so the era cursor is set even if
  // setEra() fails. Then ALSO call setEra() so any state.js-side
  // self-healing / event dispatch still fires. Add a post-write
  // marker so we can detect any subsequent reset in api.log greps.
  if (canonical) {
    state.session.currentEra = canonical;
    if (typeof setEra === "function") {
      try { setEra(canonical); } catch (e) {
        console.warn("[life-map][era-click] setEra threw:", e);
      }
    }
    // Verify the write stuck (will catch any downstream reset that
    // happens synchronously before this line runs).
    const _writeCheck = (state.session && state.session.currentEra) || "null";
    console.info("[life-map][era-click] post-write currentEra=" + _writeCheck +
      " activeFocus=" + ((state.session && state.session.activeFocusEra) || "null"));
  }

  // Re-render life-map column to update the active highlight (timeline
  // is now the chronology accordion which manages its own highlights).
  _lvInterviewRenderLifeMap();
  // Update Active Focus header — render the canonical id, not raw input.
  const valEl = document.getElementById("lvInterviewActiveFocusValue");
  if (valEl) valEl.textContent = _lvInterviewActiveFocusLabel(canonical);
  // Signal downstream consumers — composer / Lori prompt can pick up
  // this focus. Emit the canonical era_id so listeners always receive
  // a clean bare key (composer / SESSION-AWARENESS Phase 2 lane).
  try {
    window.dispatchEvent(new CustomEvent("lv-interview-focus-change",
      { detail: { era_id: canonical, era_label: _lvInterviewActiveFocusLabel(canonical) } }));
  } catch (_) {}

  // BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 (2026-05-03): produce ONE Lori
  // prompt about the selected era. This is the missing 4th step from
  // the bug spec — without it the era click was behaviorally dead
  // (state moved, but Lori never spoke about the new era).
  //
  // Per Chris's locked principle (2026-05-03): "Era click may produce
  // a Lori prompt only because the operator/narrator clicked a
  // deliberate Life Map control." This call site IS that deliberate
  // gesture (popover Continue). The directive enforces Phase 1+2
  // discipline rules inline so the LLM stays inside the contract:
  // ≤55 words, ONE question, no menu choices, warm one-ask shape.
  //
  // Caller contract: this function is only reached via the popover
  // Continue path (cancel never invokes it). Programmatic callers
  // who want to write era state without firing Lori should either
  // (a) call setEra() directly, or (b) write activeFocusEra by
  // hand — bypassing this function entirely.
  if (canonical && typeof sendSystemPrompt === "function") {
    const warmLabel = _lvInterviewActiveFocusLabel(canonical);
    const isToday = (canonical === "today");
    // 2026-05-04 BUG-LIFEMAP-ERA-FRAMING-01 — directive now requires past-tense
    // framing for historical eras AND explicitly names the warm label so the
    // reply anchors to the era. Without this, LLM produced era-neutral replies
    // (rehearsal_quick_v6 marked Lori replied=✓ but era_appropriate=✗ because
    // no past-tense markers / no era label appeared in Lori's reply).
    const directive = isToday
      ? ("[SYSTEM: The narrator just selected 'Today' on the Life Map — "
        + "they want to talk about life NOW, in the present. Ask ONE warm, "
        + "open question about something in their life today. Frame the "
        + "question in PRESENT TENSE — use words like 'today', 'now', "
        + "'these days', 'right now'. Maximum 55 words. ONE question only. "
        + "No menu choices. No 'or we could' phrasing. No compound 'and "
        + "how / and what' follow-ups.]")
      : ("[SYSTEM: The narrator just selected '" + warmLabel + "' on the "
        + "Life Map — they want to talk about this era of their life. "
        + "Ask ONE warm, open question about this period. Frame the "
        + "question in PAST TENSE — use words like 'was', 'were', 'had', "
        + "'when you', 'back then', 'that time'. Anchor the question in "
        + "the era explicitly: you may name it directly (e.g. 'During "
        + "your " + warmLabel.toLowerCase() + "...' or 'In your "
        + warmLabel.toLowerCase() + " years...') so the narrator hears "
        + "you connect to the specific period they chose. Maximum 55 "
        + "words. ONE question only. No menu choices. No 'or we could' "
        + "phrasing. No compound 'and how / and what' follow-ups.]");
      // BUG-LORI-ERA-FRAGMENT-COHERENCE-01 v10 ROLLBACK (2026-05-06):
      // The "MUST be a complete sentence — start with a wh-word..."
      // tightening I added earlier today regressed v10: every Lori
      // response across both narrators came back at exactly 20w with
      // q=0 (no question marks). The long instructional block confused
      // the local LLM into producing declarative sentences instead of
      // questions. The v8/v9 directive (restored above) was already
      // pretty good — failures were rare fragments (Mary's
      // coming_of_age + later_years, 2/14 era prompts in v8). The
      // post-LLM era-fragment-repair guard in chat_ws.py is the right
      // safety net for those rare cases. Per Chris's architectural
      // note (CLAUDE.md design principle 6): the deeper fix is the
      // timeline-context composer hook surfacing real era-grounded
      // events from timeline_context_events into the directive — see
      // WO-TIMELINE-CONTEXT-COMPOSER-HOOK-01 (pending spec).
    try {
      sendSystemPrompt(directive);
      console.info("[life-map][era-click] Lori prompt dispatched for era=" + canonical);
    } catch (e) {
      console.warn("[life-map][era-click] sendSystemPrompt threw:", e);
    }
  }
}
window._lvInterviewSelectEra = _lvInterviewSelectEra;

/**
 * WO-CANONICAL-LIFE-SPINE-01 Step 7: Life Map click confirmation.
 * Wraps the era-select action in a small confirmation popover so a
 * click doesn't silently move Lori. Renders:
 *
 *   Lori will now ask about: <warm label>
 *
 *   <loriFocus text>
 *
 *   [Cancel]  [Continue]
 *
 * Continue → calls _lvInterviewSelectEra(eraId) (which canonicalizes
 * + writes activeFocusEra + dispatches lv-interview-focus-change).
 * Cancel → no state change, popover closes.
 *
 * Canonicalizes eraId at the boundary so stray legacy/era:prefix/
 * label inputs from any caller still resolve to a bare canonical
 * era_id before the popover renders.
 */
function _lvInterviewConfirmEra(eid) {
  const canonical = (typeof _canonicalEra === "function") ? _canonicalEra(eid) : eid;
  if (!canonical) return;

  const E = window.LorevoxEras || {};
  const warmLabel = (typeof E.eraIdToWarmLabel === "function") ? (E.eraIdToWarmLabel(canonical) || canonical) : canonical;
  const focus     = (typeof E.eraIdToLoriFocus === "function") ? (E.eraIdToLoriFocus(canonical) || "") : "";

  // Build the popover dynamically — single-shot, removed on close.
  // No persistent DOM bloat. Backdrop click + Esc both cancel.
  const overlay = document.createElement("div");
  overlay.className = "lv-interview-confirm-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-labelledby", "lvInterviewConfirmHeading");

  const modal = document.createElement("div");
  modal.className = "lv-interview-confirm-modal";

  const heading = document.createElement("div");
  heading.id = "lvInterviewConfirmHeading";
  heading.className = "lv-interview-confirm-heading";
  heading.textContent = "Lori will now ask about:";

  const eraName = document.createElement("div");
  eraName.className = "lv-interview-confirm-era";
  eraName.textContent = warmLabel;

  const focusBody = document.createElement("p");
  focusBody.className = "lv-interview-confirm-body";
  focusBody.textContent = focus
    ? focus.charAt(0).toUpperCase() + focus.slice(1) + "."
    : "Lori will gently shift the conversation to this part of your story.";

  const btnRow = document.createElement("div");
  btnRow.className = "lv-interview-confirm-btn-row";

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.className = "lv-interview-confirm-btn lv-interview-confirm-cancel";
  cancelBtn.textContent = "Cancel";

  const continueBtn = document.createElement("button");
  continueBtn.type = "button";
  continueBtn.className = "lv-interview-confirm-btn lv-interview-confirm-continue";
  continueBtn.textContent = "Continue";

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(continueBtn);
  modal.appendChild(heading);
  modal.appendChild(eraName);
  modal.appendChild(focusBody);
  modal.appendChild(btnRow);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Close handlers — only Continue commits state.
  function close(commit) {
    document.removeEventListener("keydown", onKey);
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (commit) _lvInterviewSelectEra(canonical);
  }
  function onKey(e) {
    if (e.key === "Escape") { e.preventDefault(); close(false); }
    else if (e.key === "Enter") { e.preventDefault(); close(true); }
  }

  cancelBtn.addEventListener("click", () => close(false));
  continueBtn.addEventListener("click", () => close(true));
  overlay.addEventListener("click", (e) => { if (e.target === overlay) close(false); });
  document.addEventListener("keydown", onKey);

  // Focus Continue by default so Enter commits, Esc cancels —
  // standard accessibility default for a confirmation dialog.
  setTimeout(() => continueBtn.focus(), 0);
}
window._lvInterviewConfirmEra = _lvInterviewConfirmEra;

function lvEnterInterviewMode() {
  document.body.classList.add("lv-interview-mode-active");
  // Make hidden=false so CSS display rules can take over.
  // (Timeline column is the chronology accordion, which is always visible
  //  via CSS now — no need to toggle its hidden attribute here.)
  ["lvInterviewLifeMap", "lvInterviewActiveFocus", "lvInterviewPeekFloater"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.removeAttribute("hidden");
  });
  // Initial render of life-map column.
  _lvInterviewRenderLifeMap();
  // Set Active Focus from current state (if any) or default.
  const valEl = document.getElementById("lvInterviewActiveFocusValue");
  if (valEl) valEl.textContent = _lvInterviewActiveFocusLabel(state.session && state.session.activeFocusEra);
  // If on the operator tab, switch to narrator session so the chat is visible.
  if (typeof window.lvShellShowTab === "function") {
    try { window.lvShellShowTab("narrator"); } catch (_) {}
  }
  console.info("[lv-interview] entered");
}
window.lvEnterInterviewMode = lvEnterInterviewMode;

function lvExitInterviewMode() {
  document.body.classList.remove("lv-interview-mode-active");
  ["lvInterviewLifeMap", "lvInterviewActiveFocus", "lvInterviewPeekFloater"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.setAttribute("hidden", "");
  });
  console.info("[lv-interview] exited");
}
window.lvExitInterviewMode = lvExitInterviewMode;

/* Photos view — Phase 1 minimal slice: fetch, browse, stage memory.
   Memory save requires a "show" context (POST /api/photos/shows/{show_id}/memory)
   which is WO-LORI-PHOTO-ELICIT-01 Phase 2 territory; for now we
   just stage locally with a clear note. */
let _lvNarratorPhotos = { list: [], idx: 0, loaded: false, loading: false, error: null };

async function _lvNarratorRenderPhotos() {
  const host = document.getElementById("lvNarratorViewHost");
  if (!host) return;
  host.innerHTML = `
    <h3 class="lv-narrator-view-head">Photos</h3>
    <p class="lv-narrator-view-lede">One at a time. Tell Lori what you remember.</p>
    <div id="lvNarratorPhotoSlot">Loading…</div>
  `;
  const pid = state && state.person_id;
  if (!pid) {
    document.getElementById("lvNarratorPhotoSlot").innerHTML =
      `<p class="lv-narrator-view-empty">Choose a narrator on the Operator tab first.</p>`;
    return;
  }
  if (!_lvNarratorPhotos.loaded && !_lvNarratorPhotos.loading) {
    _lvNarratorPhotos.loading = true;
    try {
      // BUG-238: narrator MUST only see photos the curator marked
      // narrator_ready=true. Without this filter, scanned-but-unvetted
      // photos and in-progress curator entries leak into the narrator
      // room before metadata is reviewed. The repo-side list_photos
      // endpoint accepts the narrator_ready query param.
      // BUG-PHOTO-CORS-01: must use ORIGIN — see _lvMediaPreflightOnce
      // above for the same fix in the Media-tab health probe.
      const res = await fetch(`${ORIGIN}/api/photos?narrator_id=${encodeURIComponent(pid)}&narrator_ready=true`);
      if (res.status === 404) {
        _lvNarratorPhotos.error = "Photos are not enabled for this run.";
      } else if (res.ok) {
        const j = await res.json();
        _lvNarratorPhotos.list = Array.isArray(j && j.photos) ? j.photos : [];
      } else {
        _lvNarratorPhotos.error = `Could not load photos (status ${res.status}).`;
      }
    } catch (e) {
      _lvNarratorPhotos.error = "Could not reach the photo server.";
      console.warn("[lv-narrator] photos fetch failed:", e);
    }
    _lvNarratorPhotos.loading = false;
    _lvNarratorPhotos.loaded = true;
  }
  _lvNarratorPaintPhotoSlot();
}

function _lvNarratorPaintPhotoSlot() {
  const slot = document.getElementById("lvNarratorPhotoSlot");
  if (!slot) return;
  if (_lvNarratorPhotos.error) {
    slot.innerHTML = `<p class="lv-narrator-view-empty">${_lvEscapeHtml(_lvNarratorPhotos.error)}</p>`;
    return;
  }
  if (!_lvNarratorPhotos.list.length) {
    slot.innerHTML = `<p class="lv-narrator-view-empty">No photos yet. Add photos from the Media tab → Photo Intake.</p>`;
    return;
  }
  const photo = _lvNarratorPhotos.list[_lvNarratorPhotos.idx];
  // BUG-240: prefer thumbnail_url for the inline view (faster paint),
  // but the lightbox uses media_url for the full-resolution photo.
  // BUG-PHOTO-URL-RELATIVE-RESOLVES-TO-UI-PORT (2026-04-26): /api/photos/
  // URLs the backend returns are relative; resolve against API ORIGIN
  // (port 8000) not the page origin (port 8082).
  const _rawSrc = photo.thumbnail_url || photo.url || photo.src || photo.photo_url || "";
  const src = (_rawSrc && _rawSrc.charAt(0) === "/") ? (ORIGIN + _rawSrc) : _rawSrc;
  // Composed caption: description first, then date + location for context.
  // Falls back to the legacy caption/filename/name fields if description
  // and the structured metadata are absent (e.g. pre-Phase-2 uploads).
  const captionParts = [];
  if (photo.description && String(photo.description).trim()) captionParts.push(String(photo.description).trim());
  else if (photo.caption || photo.filename || photo.name) captionParts.push(photo.caption || photo.filename || photo.name);
  const caption = captionParts.join("");
  const subBits = [];
  if (photo.date_value) subBits.push(photo.date_value);
  if (photo.location_label) subBits.push(photo.location_label);
  const subline = subBits.join(" · ");
  const year    = photo.year || (photo.taken_at ? String(photo.taken_at).slice(0,4) : "") || (photo.date_value ? String(photo.date_value).slice(0,4) : "");
  slot.innerHTML = `
    <div class="lv-narrator-photo-frame lv-narrator-photo-frame--clickable" onclick="_lvNarratorOpenLightbox()" title="Click to see this photo full size">
      ${src ? `<img src="${_lvEscapeAttr(src)}" alt="${_lvEscapeAttr(caption)}" />` : `<span class="lv-narrator-view-empty">No image</span>`}
    </div>
    <div class="lv-narrator-photo-meta">${_lvEscapeHtml(caption)}${year ? ` · ${year}` : ""} <span style="color:#7a8bb0;">(${_lvNarratorPhotos.idx+1} of ${_lvNarratorPhotos.list.length})</span></div>
    ${subline ? `<div class="lv-narrator-photo-subline">${_lvEscapeHtml(subline)}</div>` : ""}
    <div class="lv-narrator-photo-nav">
      <button type="button" onclick="_lvNarratorPhotoStep(-1)" ${_lvNarratorPhotos.idx === 0 ? "disabled" : ""}>‹ Previous</button>
      <button type="button" onclick="_lvNarratorPhotoStep( 1)" ${_lvNarratorPhotos.idx >= _lvNarratorPhotos.list.length - 1 ? "disabled" : ""}>Next ›</button>
    </div>
    <textarea class="lv-narrator-photo-memory" id="lvNarratorPhotoMemory"
      placeholder="Type what you remember about this picture…"
      oninput="_lvNarratorStagePhotoMemory(this.value)"></textarea>
    <p class="lv-narrator-photo-hint">Memory saving arrives with the photo-session flow; for now your notes stay in this browser.</p>
  `;
}

/* BUG-240: full-screen photo lightbox for the narrator room.
   Mom/Dad clicking the small thumbnail expands to a full-frame view
   they can actually SEE. Critical for tablet sessions where the
   inline view is otherwise too small to recognize faces.

   Close paths: X button, backdrop click, Escape key.
   Caption row shows description + date + location below the photo
   so the narrator gets the curator's metadata at a glance. */
function _lvNarratorOpenLightbox() {
  const photo = _lvNarratorPhotos.list[_lvNarratorPhotos.idx];
  if (!photo) return;
  const overlay = document.getElementById("lvNarratorLightbox");
  if (!overlay) {
    console.warn("[lv-narrator] lightbox host #lvNarratorLightbox not found in DOM");
    return;
  }
  // Prefer the full-resolution media_url; thumbnail is only ~400px which
  // looks pixelated on a 10" tablet. Fall back to whatever's available.
  // BUG-PHOTO-URL-RELATIVE-RESOLVES-TO-UI-PORT: prepend ORIGIN for /api/* paths.
  const _rawFull = photo.media_url || photo.url || photo.src || photo.photo_url || photo.thumbnail_url || "";
  const fullSrc = (_rawFull && _rawFull.charAt(0) === "/") ? (ORIGIN + _rawFull) : _rawFull;
  const caption = (photo.description && String(photo.description).trim())
    || photo.caption || photo.filename || photo.name || "";
  const subBits = [];
  if (photo.date_value) subBits.push(photo.date_value);
  if (photo.location_label) subBits.push(photo.location_label);
  const subline = subBits.join(" · ");

  const img = overlay.querySelector(".lv-narrator-lightbox-img");
  const cap = overlay.querySelector(".lv-narrator-lightbox-caption");
  const sub = overlay.querySelector(".lv-narrator-lightbox-subline");
  if (img) img.src = fullSrc;
  if (img) img.alt = caption;
  if (cap) cap.textContent = caption;
  if (sub) sub.textContent = subline;

  overlay.hidden = false;
  // Suppress page scroll while lightbox is open so swipe doesn't drag
  // the chat behind it.
  document.body.style.overflow = "hidden";
}
window._lvNarratorOpenLightbox = _lvNarratorOpenLightbox;

function _lvNarratorCloseLightbox() {
  const overlay = document.getElementById("lvNarratorLightbox");
  if (!overlay) return;
  overlay.hidden = true;
  const img = overlay.querySelector(".lv-narrator-lightbox-img");
  if (img) img.src = "";  // free memory; full-res images can be 5+ MB
  document.body.style.overflow = "";
}
window._lvNarratorCloseLightbox = _lvNarratorCloseLightbox;

// ESC closes lightbox. Single global listener; cheap.
document.addEventListener("keydown", function (ev) {
  if (ev.key === "Escape") {
    var overlay = document.getElementById("lvNarratorLightbox");
    if (overlay && !overlay.hidden) {
      _lvNarratorCloseLightbox();
    }
  }
});

function _lvNarratorPhotoStep(delta) {
  const n = _lvNarratorPhotos.list.length;
  if (!n) return;
  _lvNarratorPhotos.idx = Math.max(0, Math.min(n - 1, _lvNarratorPhotos.idx + delta));
  _lvNarratorPaintPhotoSlot();
}
window._lvNarratorPhotoStep = _lvNarratorPhotoStep;

function _lvNarratorStagePhotoMemory(text) {
  // Phase 1 stages locally and emits an event.  Phase 2 (ELICIT-01) will
  // persist via POST /api/photos/shows/{show_id}/memory.
  const photo = _lvNarratorPhotos.list[_lvNarratorPhotos.idx];
  if (!photo) return;
  photo._stagedMemory = text;
  try { window.dispatchEvent(new CustomEvent("lv-narrator-photo-memory-staged", { detail: { photo_id: photo.id, text } })); } catch (_) {}
}
window._lvNarratorStagePhotoMemory = _lvNarratorStagePhotoMemory;

function _lvEscapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
function _lvEscapeAttr(s) { return _lvEscapeHtml(s); }

/* ── Topbar controls — delegate to existing state machines ────── */

/** Mic toggle → delegates to lv10dToggleMic.  After the call we paint
    our button's data-on from state.inputState.micActive. */
function lvNarratorToggleMic() {
  if (typeof lv10dToggleMic === "function") { try { lv10dToggleMic(); } catch (e) { console.warn("[lv-narrator] mic toggle threw:", e); } }
  // Paint asynchronously; the underlying flow may be async.
  setTimeout(_lvNarratorPaintControls, 120);
}
window.lvNarratorToggleMic = lvNarratorToggleMic;

/** Camera toggle → delegates to lv10dToggleCamera (which handles consent,
    engine start, preview).  We just mirror state onto our button. */
function lvNarratorToggleCamera() {
  if (typeof lv10dToggleCamera === "function") { try { lv10dToggleCamera(); } catch (e) { console.warn("[lv-narrator] cam toggle threw:", e); } }
  setTimeout(_lvNarratorPaintControls, 250);
  // Camera flow can be async (consent modal); re-poll a few times.
  setTimeout(_lvNarratorPaintControls, 1200);
  setTimeout(_lvNarratorPaintControls, 3000);
}
window.lvNarratorToggleCamera = lvNarratorToggleCamera;

/** Pause toggle → delegates to listening pause. */
function lvNarratorTogglePause() {
  if (typeof lv80TogglePauseListening === "function") {
    try { lv80TogglePauseListening(); } catch (e) { console.warn("[lv-narrator] pause toggle threw:", e); }
  }
  setTimeout(_lvNarratorPaintControls, 80);
}
window.lvNarratorTogglePause = lvNarratorTogglePause;

/** Paint Mic/Camera state dots + labels from global state.
    Safe to call whenever — re-reads state each time. */
function _lvNarratorPaintControls() {
  const micBtn = document.getElementById("lvNarratorMicBtn");
  const camBtn = document.getElementById("lvNarratorCamBtn");
  const pauseBtn = document.getElementById("lvNarratorPauseBtn");
  const micLabel = document.getElementById("lvNarratorMicLabel");
  const camLabel = document.getElementById("lvNarratorCamLabel");
  const pauseLabel = document.getElementById("lvNarratorPauseLabel");
  const micOn = !!(state && state.inputState && state.inputState.micActive) ||
                (typeof isRecording !== "undefined" && !!isRecording);
  const camOn = !!(state && state.inputState && state.inputState.cameraActive) ||
                (typeof cameraActive !== "undefined" && !!cameraActive);
  const paused = !!(typeof listeningPaused !== "undefined" && listeningPaused);
  if (micBtn) micBtn.setAttribute("data-on", micOn ? "true" : "false");
  if (camBtn) camBtn.setAttribute("data-on", camOn ? "true" : "false");
  if (pauseBtn) pauseBtn.setAttribute("data-on", paused ? "true" : "false");
  if (micLabel)   micLabel.textContent   = micOn ? "Mic on"    : "Mic";
  if (camLabel)   camLabel.textContent   = camOn ? "Camera on" : "Camera";
  if (pauseLabel) pauseLabel.textContent = paused ? "Resume"   : "Pause";
  // Paint the context panel blocks to match.
  const ctxCam = document.getElementById("lvNarratorCtxCamera");
  const ctxCamBody = document.getElementById("lvNarratorCtxCameraBody");
  const ctxMic = document.getElementById("lvNarratorCtxMic");
  const ctxMicBody = document.getElementById("lvNarratorCtxMicBody");
  if (ctxCam)     ctxCam.setAttribute("data-state", camOn ? "on" : "off");
  if (ctxCamBody) ctxCamBody.textContent = camOn ? "On — Lori adjusts pacing from your expressions." : "Off — Lori won't see you.";
  if (ctxMic)     ctxMic.setAttribute("data-state", micOn ? "on" : "off");
  if (ctxMicBody) ctxMicBody.textContent = paused ? "Paused — tap Resume to keep talking." : (micOn ? "Listening." : "Off — type your answer.");
}
window._lvNarratorPaintControls = _lvNarratorPaintControls;

/* ── WO-AUDIO-NARRATOR-ONLY-01: "Save my voice" toggle ────────────
   Operator-facing flip in the narrator-room topbar.  Default ON.
   When OFF, the audio recorder becomes a no-op (transcript still
   flows; backend chat_ws still writes the text).  Persists in
   state.session.recordVoice so it survives the rest of the session
   (per-session, not per-narrator). */
function lvNarratorSetRecordVoice(enabled) {
  if (!state.session) state.session = {};
  state.session.recordVoice = !!enabled;
  console.log("[narrator-audio] state.session.recordVoice = " + state.session.recordVoice);
  // Sync the checkbox visual (in case this was called programmatically
  // rather than via the onchange handler).
  const cb = document.getElementById("lvNarratorRecordVoice");
  if (cb && cb.checked !== state.session.recordVoice) cb.checked = state.session.recordVoice;
  // If toggled OFF mid-session, drop any in-progress segment without
  // uploading.  If toggled ON, the next mic-arm will start fresh.
  if (!state.session.recordVoice && typeof window.lvNarratorAudioRecorder === "object") {
    try { window.lvNarratorAudioRecorder.cleanup && window.lvNarratorAudioRecorder.cleanup(); } catch (_) {}
  }
}
window.lvNarratorSetRecordVoice = lvNarratorSetRecordVoice;

/* ── Take a Break overlay ───────────────────────────────────────
   WO-PARENT-SESSION-HARDENING-01 Phase 3.2 + 4.2 + 4.3 + 4.4
   (UI audit P0 #3 + P1 #1 + P1 #2 + P1 #4):

   StartBreak:
     - Snapshot pre-break mic state to state.session._breakSnapshot
       so Resume can restore it (was: snapshot was lost; mic stayed
       silent forever after Resume).
     - Cancel in-flight TTS via stopAllTts() — clicking Break while
       Lori is mid-sentence used to let the audio finish, which felt
       broken / confusing.

   EndBreak (Resume):
     - Restore micAutoRearm from snapshot.
     - If mic was on pre-break, resume listening via the same toggle
       function that paused it.
     - Speak welcome-back TTS so the silence-after-Resume failure
       mode is gone.
     - Clear the snapshot.

   Escape-key handler at module init:
     - When the Break overlay is visible, Esc fires Resume (matches
       Resume button behavior).

   Notes:
     - lvNarratorReturnToOperator removed from the Break overlay UI
       (Phase 3.1, hornelore1.0.html). The function definition stays
       for now as harmless dead code; safe to remove in a later
       cleanup pass.                                              */

function lvNarratorStartBreak() {
  if (!state.session) state.session = {};

  // Snapshot pre-break mic state BEFORE we change anything.
  const _preMicAutoRearm = !!state.session.micAutoRearm;
  const _preMicActive    = !!(state.inputState && state.inputState.micActive);
  const _preListeningPaused = !!(typeof listeningPaused !== "undefined" && listeningPaused);
  state.session._breakSnapshot = {
    micAutoRearm: _preMicAutoRearm,
    micActive:    _preMicActive,
    listeningPaused: _preListeningPaused,
  };

  state.session.breakActive = true;
  state.session.micAutoRearm = false;   // stop auto-rearm during break

  // Pause mic if active, so the overlay really is silent.
  if (_preMicActive && !_preListeningPaused && typeof lv80TogglePauseListening === "function") {
    try { lv80TogglePauseListening(); } catch (_) {}
  }

  // Cancel in-flight TTS so clicking Break mid-sentence stops audio
  // immediately (was: audio kept playing under the overlay).
  try {
    if (typeof stopAllTts === "function") stopAllTts();
    else if (typeof window._wo11eStopTts === "function") window._wo11eStopTts();
  } catch (_) { /* best-effort */ }

  const overlay = document.getElementById("lvNarratorBreakOverlay");
  if (overlay) { overlay.hidden = false; overlay.setAttribute("aria-hidden", "false"); }
  _lvNarratorPaintControls();
}
window.lvNarratorStartBreak = lvNarratorStartBreak;

function lvNarratorEndBreak() {
  if (!state.session) state.session = {};
  state.session.breakActive = false;

  // Restore pre-break mic state from snapshot.
  const snap = state.session._breakSnapshot || null;
  if (snap) {
    // Restore auto-rearm flag.
    state.session.micAutoRearm = !!snap.micAutoRearm;
    // If mic was on pre-break and we paused it, un-pause now (matching toggle).
    const stillPaused = !!(typeof listeningPaused !== "undefined" && listeningPaused);
    const wasUnpausedPreBreak = snap.micActive && !snap.listeningPaused;
    if (wasUnpausedPreBreak && stillPaused && typeof lv80TogglePauseListening === "function") {
      try { lv80TogglePauseListening(); } catch (_) {}
    }
    state.session._breakSnapshot = null;
  }

  const overlay = document.getElementById("lvNarratorBreakOverlay");
  if (overlay) { overlay.hidden = true; overlay.setAttribute("aria-hidden", "true"); }
  _lvNarratorPaintControls();

  // Welcome-back TTS — reduces the silence-after-Resume failure mode.
  // Uses preferred name if known, falls back to a neutral phrase.
  try {
    const basics = (state.profile && state.profile.basics) || {};
    const name = String(basics.preferred || basics.preferredName || basics.fullname ||
                       basics.firstName || "").trim();
    const greeting = name
      ? "Welcome back, " + name + ". Ready to continue?"
      : "Welcome back. Ready to continue?";
    if (typeof enqueueTts === "function") enqueueTts(greeting);
  } catch (_) { /* best-effort; never block Resume */ }
}
window.lvNarratorEndBreak = lvNarratorEndBreak;

// WO-PARENT-SESSION-HARDENING-01 Phase 4.4 — Escape-key dismissal of
// Break overlay. When the overlay is visible, Esc fires Resume.
// Module-init handler; harmless when overlay is hidden.
document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  const overlay = document.getElementById("lvNarratorBreakOverlay");
  if (!overlay || overlay.hidden) return;
  e.preventDefault();
  try { lvNarratorEndBreak(); } catch (_) {}
});

// Legacy function — UI button removed in Phase 3.1 (no operator leakage).
// Safe to delete in a later cleanup pass.
function lvNarratorReturnToOperator() {
  lvNarratorEndBreak();
  if (typeof lvShellShowTab === "function") lvShellShowTab("operator");
}
window.lvNarratorReturnToOperator = lvNarratorReturnToOperator;

/* ── Chat scroll helpers (delegate to FocusCanvas's existing plumbing). ── */

function lvNarratorIsNearBottom() {
  const el = document.getElementById("crChatInner");
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight <= 40;
}
window.lvNarratorIsNearBottom = lvNarratorIsNearBottom;

function lvNarratorScrollToBottom(force) {
  const el = document.getElementById("crChatInner");
  if (!el) return;
  if (force || lvNarratorIsNearBottom()) {
    el.scrollTop = el.scrollHeight;
  }
}
window.lvNarratorScrollToBottom = lvNarratorScrollToBottom;

function lvNarratorPauseAutoScroll()  { try { window._scrollPauseByUser = true;  } catch (_) {} }
function lvNarratorResumeAutoScroll() {
  try { window._scrollPauseByUser = false; } catch (_) {}
  if (typeof window._scrollToLatest === "function") window._scrollToLatest();
}
window.lvNarratorPauseAutoScroll  = lvNarratorPauseAutoScroll;
window.lvNarratorResumeAutoScroll = lvNarratorResumeAutoScroll;

/* Lightweight paint tick — runs only while the narrator tab is active.
   1.5s cadence; all it does is re-read state flags and toggle a few
   data-attrs/textContent.  Cheap, but we still gate it by the tab. */
let _lvNarratorPaintTickId = null;
function _lvNarratorStartPaintTick() {
  if (_lvNarratorPaintTickId != null) return;
  _lvNarratorPaintTickId = setInterval(() => {
    if (typeof _lvNarratorPaintControls === "function") _lvNarratorPaintControls();
    if (typeof _lvNarratorPaintIdentity === "function") _lvNarratorPaintIdentity();
  }, 1500);
}
function _lvNarratorStopPaintTick() {
  if (_lvNarratorPaintTickId != null) { clearInterval(_lvNarratorPaintTickId); _lvNarratorPaintTickId = null; }
}

/** Room init — called by lvStartNarratorSession (WO-UI-SHELL-01).
    Paints identity, loads default view, hydrates control state. */
function lvNarratorRoomInit() {
  _lvNarratorPaintIdentity();
  _lvNarratorPaintControls();
  // (Memory River removed — chronology accordion is the timeline surface.
  //  Kawa segments are still loaded for the popover, but no view-tab depends
  //  on them anymore.)
  if (typeof kawaRefreshList === "function" &&
      state.kawa && (!state.kawa.segmentList || !state.kawa.segmentList.length)) {
    kawaRefreshList().catch(() => {});
  }
  lvNarratorShowView(lvNarratorCurrentView() || "map");
  // WO-INTERVIEW-MODE-01 Phase 2 — render the Life Map column on the right.
  // Always visible in narrator room (both regular session view AND interview
  // mode), so this fires on every room init.
  if (typeof _lvInterviewRenderLifeMap === "function") _lvInterviewRenderLifeMap();
  // Anchor chat at latest when entering the room.
  setTimeout(() => lvNarratorScrollToBottom(true), 40);
  // Reset photo cache on narrator change so the next "photos" view refetches.
  const pid = state && state.person_id;
  if (_lvNarratorPhotos._pid !== pid) {
    _lvNarratorPhotos = { list: [], idx: 0, loaded: false, loading: false, error: null, _pid: pid };
  }
}
window.lvNarratorRoomInit = lvNarratorRoomInit;

/* ═══════════════════════════════════════════════════════════════
   INIT
═══════════════════════════════════════════════════════════════ */
window.onload = async () => {
  // WO-11B: hard reset trainer/capture state on startup to prevent contamination
  if (typeof window.lv80ClearTrainerAndCaptureState === "function") {
    window.lv80ClearTrainerAndCaptureState();
  }
  checkStatus();
  connectWebSocket();
  await initSession();
  await refreshPeople();
  await refreshSessions();
  renderRoadmap();
  renderMemoirChapters();
  updateArchiveReadiness();
  update71RuntimeUI();   // v7.1 — paint runtime badges on first load
  // WO-UI-SHELL-01: mount the three-tab shell.  Lands on Operator;
  // hydrates session style from localStorage; mirrors warmup state.
  if (typeof lvShellInitTabs === "function") lvShellInitTabs();
  // WO-KAWA-UI-01A: Pre-load river segments (non-blocking)
  if (typeof kawaRefreshList === "function") {
    kawaRefreshList().catch(e => console.warn("[kawa] initial load skipped:", e));
  }
  document.addEventListener("keydown", e => { if(e.key==="Escape" && isFocusMode) toggleFocus(); });
  // Step 3 (Task 6 audit): identityPhase starts as null in state.js.
  // getIdentityPhase74() handles null by checking hasIdentityBasics74():
  //   • returning user (has profile basics) → "complete" → correct pass routing
  //   • new user (no profile)               → "incomplete" → identity gate
  // The original `=== undefined` check was dead code (state.js uses null, not undefined).
  // No functional guard needed; null is the correct initial value for both paths.

  // v8.1 STARTUP NEUTRALITY: Always open to blank narrator selector.
  // The user must explicitly choose a narrator or create a new one.
  // Backend is still the authority — we validate and clean stale pointers,
  // but we never auto-load a narrator on startup.
  const saved = localStorage.getItem(LS_ACTIVE);
  const backendPeople = state?.narratorUi?.peopleCache || [];
  const backendPids = backendPeople.map(p => p.id || p.person_id || p.uuid);

  // Clean up stale narrator pointer if it no longer exists in backend
  if (saved && !backendPids.includes(saved)) {
    console.warn("[startup] Stale active narrator detected:", saved, "— not in backend list. Clearing.");
    _invalidateStaleNarrator(saved);
  }

  // v8.1: Always enter blank state — user picks their narrator from the selector.
  _enforceBlankStartupState();
  console.log("[startup] v8.1 — blank state enforced. User must select a narrator.");

  // Phase Q.4: READINESS GATE — defer onboarding/narrator-selection until
  // the LLM is actually loaded and warm. This prevents trust-breaking behavior
  // where Lori speaks with raw-model identity before the fine-tuned model is ready.
  // _onModelReady() will fire the appropriate startup flow once warm.
  pollModelReady();

  // Step 3 — log device context block on every session start for diagnostics.
  const _dc = {
    date:     new Intl.DateTimeFormat("en-US", { weekday:"long", year:"numeric", month:"long", day:"numeric" }).format(new Date()),
    time:     new Intl.DateTimeFormat("en-US", { hour:"numeric", minute:"2-digit", hour12:true }).format(new Date()),
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  };
  console.log("[device_context]", _dc);
};

/* ═══════════════════════════════════════════════════════════════
   v8.0 STARTUP NEUTRALITY HELPERS
═══════════════════════════════════════════════════════════════ */
/**
 * Invalidate all cached state for a narrator that no longer exists in the backend.
 * This prevents ghost narrators from surviving across deletions and restarts.
 */
function _invalidateStaleNarrator(stalePid) {
  try { localStorage.removeItem(LS_ACTIVE); } catch(_) {}
  try { localStorage.removeItem("lorevox_offline_profile_" + stalePid); } catch(_) {}
  try { localStorage.removeItem("lorevox_proj_draft_" + stalePid); } catch(_) {}
  try { localStorage.removeItem("lorevox_qq_draft_" + stalePid); } catch(_) {}
  try { localStorage.removeItem("lorevox.spine." + stalePid); } catch(_) {}
  try { localStorage.removeItem(LS_DONE(stalePid)); } catch(_) {}
  try { localStorage.removeItem(LS_SEGS(stalePid)); } catch(_) {}
  try { localStorage.removeItem("lorevox_offline_people"); } catch(_) {}
  console.log("[startup] Invalidated stale narrator cache:", stalePid);
}

/**
 * Force a clean blank startup state when backend has zero narrators.
 * Clears all narrator-scoped state so the UI renders a true blank slate.
 */
function _enforceBlankStartupState() {
  // Clear global narrator pointer
  state.person_id = null;
  try { localStorage.removeItem(LS_ACTIVE); } catch(_) {}

  // Clear profile/projection/questionnaire in-memory state
  state.profile = { basics: {}, kinship: [], pets: [] };
  if (state.interviewProjection) {
    state.interviewProjection.personId = null;
    state.interviewProjection.fields = {};
    state.interviewProjection.pendingSuggestions = [];
    state.interviewProjection.syncLog = [];
  }

  // Clear identity phase state
  if (state.session) {
    state.session.identityPhase = null;
    state.session.identityCapture = { name: null, dob: null, birthplace: null };
  }

  // Invalidate any stale offline people cache
  try { localStorage.removeItem("lorevox_offline_people"); } catch(_) {}

  // v8.0 FIX: Also scan for and remove orphaned narrator-scoped keys
  // that point to narrators no longer in the backend.
  // NOTE: lorevox.spine.* keys are intentionally PRESERVED here so that
  // loadPerson → loadSpineLocal can restore the timeline after reload.
  // Spine cleanup for deleted/stale narrators is handled by
  // _invalidateStaleNarrator() and the narrator-delete flow.
  try {
    const keys = Object.keys(localStorage);
    for (let i = 0; i < keys.length; i++) {
      const k = keys[i];
      if (k.startsWith("lorevox_offline_profile_") ||
          k.startsWith("lorevox_proj_draft_") ||
          k.startsWith("lorevox_qq_draft_") ||
          k.startsWith("lv_done_") ||
          k.startsWith("lv_segs_") ||
          // FIX-9: Also clean up FT draft, LT draft, deleted narrator backup, and draft PIDs
          k.startsWith("lorevox_ft_draft_") ||
          k.startsWith("lorevox_lt_draft_") ||
          k.startsWith("lorevox_deleted_narrator_backup") ||
          k === "lorevox_draft_pids") {
        localStorage.removeItem(k);
      }
    }
  } catch(_) {}

  // Update header to blank state
  if (typeof lv80UpdateActiveNarratorCard === "function") {
    lv80UpdateActiveNarratorCard();
  }

  console.log("[startup] Enforced blank startup state — no active narrator.");
}

/* ═══════════════════════════════════════════════════════════════
   STATUS PILLS
═══════════════════════════════════════════════════════════════ */
async function checkStatus(){
  pill("pillChat", await ping(API.PING));
  pill("pillTts",  await ping(API.TTS_VOICES));
}
async function ping(url){
  try{ await fetch(url,{signal:AbortSignal.timeout(2500)}); return true; }catch{ return false; }
}
function pill(id,ok){
  const el=document.getElementById(id); if(!el) return;
  el.classList.remove("pill-off","on","err");
  el.classList.add(ok?"on":"err");
}

/* ═══════════════════════════════════════════════════════════════
   LORI STATUS  (v7.1 — state propagation patch)
═══════════════════════════════════════════════════════════════ */

/**
 * Normalize an incoming state label into canonical runtime values.
 * Everything in `runtime` is what prompt_composer.py will actually see.
 */
// Transitional UI-only states — badge updates only, never touch state.runtime
const _UI_ONLY_STATES = new Set(["thinking","drafting","listening"]);

function normalizeLoriState(input) {
  const raw = String(input || "").trim().toLowerCase();
  // Semantic runtime states — these propagate to the backend
  const map = {
    ready:       { badge:"Ready",        affectState:"neutral",       affectConfidence:0,    cognitiveMode:"open",        fatigueScore:0  },
    open:        { badge:"Open",         affectState:"neutral",       affectConfidence:0,    cognitiveMode:"open",        fatigueScore:0  },
    recognition: { badge:"recognition",  affectState:"confusion_hint",affectConfidence:0.65, cognitiveMode:"recognition", fatigueScore:Math.max(Number(state?.runtime?.fatigueScore||0),20) },
    grounding:   { badge:"grounding",    affectState:"distress_hint", affectConfidence:0.8,  cognitiveMode:"grounding",   fatigueScore:Math.max(Number(state?.runtime?.fatigueScore||0),40) },
    /* v7.2 — alongside: sustained confusion / fragmentation; reflection-only, no structured questions */
    alongside:   { badge:"alongside",   affectState:"distress_hint", affectConfidence:0.85, cognitiveMode:"alongside",   fatigueScore:Math.max(Number(state?.runtime?.fatigueScore||0),30) },
    light:       { badge:"light",        affectState:"fatigue_hint",  affectConfidence:0.6,  cognitiveMode:"light",       fatigueScore:Math.max(Number(state?.runtime?.fatigueScore||0),60) },
    high_fatigue:{ badge:"high_fatigue", affectState:"fatigue_hint",  affectConfidence:0.9,  cognitiveMode:"light",       fatigueScore:80 },
  };
  return map[raw] || null; // null = badge-only (transitional or unknown)
}

/* ═══════════════════════════════════════════════════════════════
   WO-ARCH-07A — Router seed + Memory Echo helpers
═══════════════════════════════════════════════════════════════ */

const TURN_INTERVIEW   = "interview";
const TURN_FOLLOWUP    = "followup";
const TURN_MEMORY_ECHO = "memory_echo";
const TURN_CORRECTION  = "correction";
const TURN_CLARIFY     = "clarify";
const TURN_TRAINER     = "trainer";
// BUG-LORI-LATE-AGE-RECALL-01 (2026-05-06): deterministic age-question
// route. v8 evidence: both narrators dodged late-age questions with "Is
// there something else on your mind?" because the LLM had to infer age
// from DOB + today across a long context window and either failed
// inference or over-deflected on personal data. New route bypasses the
// LLM entirely — uses age_years from profile_seed via the chat_ws
// memory_echo-style branch (compose_age_recall in prompt_composer).
const TURN_AGE_RECALL  = "age_recall";

function _lvText(s){
  return String(s || "").trim();
}

function _looksLikeMemoryEchoRequest(text){
  const t = _lvText(text).toLowerCase();
  return [
    "tell me what you know about me",
    "what do you know about me",
    "read back what you know about me",
    "summarize what you know about me",
    "read back what you know",
    // WO-GREETING-01: expanded trigger phrases
    "what have you learned about me",
    "what do you remember about me",
    "what have i told you",
    "what have i told you about me",
    "what have i shared with you",
    "show me what you know",
    "do you remember me",
    "repeat what you know about me",
    "recap what you know"
  ].some(p => t.includes(p));
}

// BUG-LORI-MIDSTREAM-CORRECTION-01 Phase 2 (2026-05-06): split correction
// detection into "strong" (always-fire) and "weak" (fire only after
// memory_echo). Strong markers: explicit correction openers + explicit
// contradiction patterns ("X not Y") that almost certainly indicate a
// narrator self-correction. Weak markers: biographical "I was born…"
// "my father…" shapes that are corrections ONLY in the context of a
// just-emitted memory_echo readback the narrator is fixing.
//
// Live evidence: Mary v6/v7/v8 mid-lifemap correction "Actually we only
// had two kids, not three" routed as TURN_INTERVIEW because the prior
// turn was a lifemap era prompt (not memory_echo). Lori plowed past the
// correction. handled_well=False across runs.
function _looksLikeStrongCorrection(text){
  const t = _lvText(text).toLowerCase();
  if (!t) return false;
  // Explicit correction openers — high signal.
  if (
    t.startsWith("no,") ||
    t.startsWith("no actually") ||
    t.startsWith("actually,") ||
    t.startsWith("actually ") ||
    t.startsWith("correction,") ||
    t.startsWith("that is wrong") ||
    t.startsWith("that's wrong") ||
    t.startsWith("that's not right") ||
    t.startsWith("that is not right") ||
    t.startsWith("change that") ||
    t.startsWith("update that")
  ) return true;
  // Numerical / named contradiction: "we only had X, not Y" / "it was X
  // not Y" / "X, not Y". Requires "not" with surrounding context.
  // Match patterns where the narrator explicitly contradicts a prior
  // claim — the comma-or-words-around-not heuristic catches Mary's
  // "Actually we only had two kids, not three" + variants.
  if (/\b(?:not|wasn't|weren't|didn't|wasnt|werent|didnt)\s+(?:\d+|that|him|her|them|me|my|the|a|an|in|on)\b/.test(t)) return true;
  // "X was wrong" / "I got X wrong" — explicit error acknowledgment.
  if (/\b(?:was|were|got|i was|that was)\s+wrong\b/.test(t)) return true;
  return false;
}

function _looksLikeWeakCorrectionAfterEcho(text){
  // Biographical re-statements that ONLY count as corrections in the
  // context of a just-emitted memory_echo the narrator is fixing.
  const t = _lvText(text).toLowerCase();
  if (!t) return false;
  return (
    t.includes("i was born in") ||
    t.includes("my father") ||
    t.includes("my mother") ||
    t.includes("i had ") ||
    t.includes("i have ")
  );
}

// Backward-compat wrapper. Old callers expecting a single function get
// the union of strong + weak detection (memory_echo gate handled by
// lvRouteTurn).
function _looksLikeCorrection(text){
  return _looksLikeStrongCorrection(text) || _looksLikeWeakCorrectionAfterEcho(text);
}

// BUG-LORI-LATE-AGE-RECALL-01 (2026-05-06): age-question intent detector.
// Strong shape so we don't false-positive on biographical statements
// like "I was old enough to know better". Requires explicit age-asking
// pattern: "how old", "what is my age", "when was I born", "what's my
// birthday", or DOB-asking variants.
function _looksLikeAgeQuestion(text){
  const t = _lvText(text).toLowerCase();
  if (!t) return false;
  // BUG-LORI-LATE-AGE-RECALL-01 v10 fix (2026-05-06): the v10 detector
  // required "how old [aux] i" with no intervening words, but the
  // TEST-23 harness sends "How old do you think I am now?" — three
  // words between "do" and "I". The detector missed it entirely and
  // the deterministic age route never fired in v10. New detector
  // covers BOTH direct ("how old am I?") and indirect ("how old do
  // you think I am?") shapes via the second branch.
  return (
    // Direct: "how old am/are/do/will/would/might I" (no filler words)
    /\bhow\s+old\s+(?:am|are|do|will|would|might|did)\s+i\b/.test(t) ||
    // Indirect: "how old [filler 0-6 words] I am/was/will be/would be"
    /\bhow\s+old\b[^?.!]{0,40}?\bi\s+(?:am|was|will\s+be|would\s+be|might\s+be)\b/.test(t) ||
    // Direct age questions
    /\bwhat\s+(?:is|'s|was)\s+my\s+age\b/.test(t) ||
    /\bdo\s+you\s+(?:know|remember)\s+(?:my\s+age|how\s+old\s+i\s+am)\b/.test(t) ||
    // DOB / birthday questions
    /\bwhen\s+(?:was|were)\s+i\s+born\b/.test(t) ||
    /\bwhat\s+(?:is|'s|was)\s+my\s+(?:date\s+of\s+birth|birthday|dob)\b/.test(t) ||
    /\bdo\s+you\s+(?:know|remember)\s+my\s+(?:birthday|date\s+of\s+birth|dob)\b/.test(t) ||
    // Bare phrase + question mark (for typed shorthand)
    /^\s*(?:how\s+old|my\s+age|my\s+birthday|when\s+i\s+was\s+born)\s*\?/.test(t)
  );
}

function lvRouteTurn(text){
  if (_looksLikeMemoryEchoRequest(text)) return TURN_MEMORY_ECHO;
  // Age-question intent fires TURN_AGE_RECALL regardless of prior turn.
  // v8 dodge "Is there something else on your mind?" was the LLM
  // deflecting; a deterministic route bypasses LLM drift entirely.
  if (_looksLikeAgeQuestion(text)) return TURN_AGE_RECALL;
  // Strong correction markers fire TURN_CORRECTION regardless of prior
  // turn mode — narrators correct themselves mid-conversation, not just
  // after memory_echo readbacks. BUG-LORI-MIDSTREAM-CORRECTION-01 Phase 2.
  if (_looksLikeStrongCorrection(text)) return TURN_CORRECTION;
  // Weak biographical re-statements only count as corrections when they
  // immediately follow a memory_echo turn (the narrator is fixing the
  // readback). Otherwise they're regular interview answers.
  if (state?.session?.lastTurnMode === TURN_MEMORY_ECHO && _looksLikeWeakCorrectionAfterEcho(text)) return TURN_CORRECTION;
  return TURN_INTERVIEW;
}

function _mkField(value, confidence, source, previous){
  return {
    value: value == null ? null : value,
    confidence: confidence || "working_draft", // confirmed | working_draft | unclear
    source: source || "projection",            // profile | user_correction | projection | derived
    previous: Array.isArray(previous) ? previous : []
  };
}

/* WO-ARCH-07A PS2 — correction-aware field resolution */
function _ensureCorrectionState(){
  if (!state.correctionState) {
    state.correctionState = { applied: [], conflicts: [], uncertain: [] };
  }
  return state.correctionState;
}

function _activeCorrectionFor(fieldPath){
  const cs = _ensureCorrectionState();
  const hits = cs.applied.filter(x => x.fieldPath === fieldPath);
  return hits.length ? hits[hits.length - 1] : null;
}

function _conflictsFor(fieldPath){
  const cs = _ensureCorrectionState();
  return cs.conflicts.filter(x => x.fieldPath === fieldPath);
}

function _fieldFromSources(fieldPath, baseValue, baseConfidence, baseSource){
  const corr = _activeCorrectionFor(fieldPath);
  if (corr) {
    return _mkField(corr.newValue, "confirmed", "user_correction", corr.oldValue != null ? [corr.oldValue] : []);
  }
  const conflicts = _conflictsFor(fieldPath);
  if (conflicts.length) {
    return _mkField(baseValue, "unclear", baseSource || "projection", conflicts.map(c => c.conflictingValue));
  }
  return _mkField(baseValue, baseConfidence, baseSource);
}

/* Deterministic state read-back. This is NOT canonical truth by itself.
   It is a coherence view built from current scoped state. */
function buildMemoryEchoEntity(){
  const basics = state?.profile?.basics || {};
  const kin    = Array.isArray(state?.profile?.kinship) ? state.profile.kinship : [];
  const spine  = state?.timeline?.spine || null;
  const periods = Array.isArray(spine?.periods) ? spine.periods : [];

  const parents = kin.filter(k => /mother|father|parent/i.test(k.relation || ""));
  const siblings = kin.filter(k => /brother|sister|sibling/i.test(k.relation || ""));
  const spouses = kin.filter(k => /spouse|wife|husband|partner/i.test(k.relation || ""));
  const children = kin.filter(k => /son|daughter|child/i.test(k.relation || ""));

  const entity = {
    identity: {
      full_name: _fieldFromSources(
        "identity.full_name",
        basics.fullname || basics.fullName || null,
        (basics.fullname || basics.fullName) ? "confirmed" : "unclear",
        "profile"
      ),
      preferred_name: _fieldFromSources(
        "identity.preferred_name",
        basics.preferred || basics.preferredName || null,
        (basics.preferred || basics.preferredName) ? "confirmed" : "unclear",
        "profile"
      ),
      date_of_birth: _fieldFromSources(
        "identity.date_of_birth",
        basics.dob || null,
        basics.dob ? "confirmed" : "unclear",
        "profile"
      ),
      place_of_birth: _fieldFromSources(
        "identity.place_of_birth",
        basics.pob || null,
        basics.pob ? "confirmed" : "unclear",
        "profile"
      )
    },

    family: {
      parents:  parents.map(p => _mkField((p.name || p.label || "").trim() || null, "working_draft", "projection")),
      siblings: siblings.map(s => _mkField((s.name || s.label || "").trim() || null, "working_draft", "projection")),
      spouses:  spouses.map(s => _mkField((s.name || s.label || "").trim() || null, "working_draft", "projection")),
      children: children.map(c => _mkField((c.name || c.label || "").trim() || null, "working_draft", "projection"))
    },

    places: {
      current_place: _mkField(basics.location || null, basics.location ? "working_draft" : "unclear", basics.location ? "projection" : "derived"),
      first_home:    _mkField(null, "unclear", "derived")
    },

    education_work: {
      schooling:  _mkField(null, "unclear", "derived"),
      early_career: _mkField(null, "unclear", "derived"),
      retirement: _mkField(null, "unclear", "derived")
    },

    timeline: {
      birth: _mkField(
        (basics.dob || basics.pob) ? `${basics.dob || "unknown date"} — ${basics.pob || "unknown place"}` : null,
        (basics.dob || basics.pob) ? "confirmed" : "unclear",
        "profile"
      ),
      periods: periods.map(p => ({
        label: p.label || null,
        start_year: p.start_year || null,
        end_year: p.end_year == null ? null : p.end_year,
        confidence: "working_draft",
        source: "derived"
      }))
    },

    themes: {
      active_threads: []
    },

    uncertain: []
  };

  // Surface obvious missing fields
  if (!entity.identity.full_name.value) entity.uncertain.push("full name");
  if (!entity.identity.date_of_birth.value) entity.uncertain.push("date of birth");
  if (!entity.identity.place_of_birth.value) entity.uncertain.push("place of birth");

  // WO-ARCH-07A PS2 — merge correction ledger uncertainty + conflicts into entity
  const cs = _ensureCorrectionState();
  cs.uncertain.forEach(fp => {
    if (!entity.uncertain.includes(fp)) entity.uncertain.push(fp);
  });
  if (cs.conflicts.length) {
    entity.conflicts = cs.conflicts.map(c => ({
      fieldPath: c.fieldPath,
      activeValue: c.activeValue,
      conflictingValue: c.conflictingValue,
      sourceText: c.sourceText || null
    }));
  } else {
    entity.conflicts = [];
  }

  state.memoryEcho = {
    builtAt: Date.now(),
    entity,
    lastRenderedText: null
  };

  return entity;
}

/* WO-ARCH-07A PS2 — structured correction write-back */
function _pushAppliedCorrection(fieldPath, newValue, oldValue, sourceText){
  const cs = _ensureCorrectionState();
  cs.applied.push({
    fieldPath,
    newValue,
    oldValue: oldValue == null ? null : oldValue,
    sourceText: sourceText || null,
    ts: Date.now()
  });
}

function _pushConflict(fieldPath, activeValue, conflictingValue, sourceText){
  const cs = _ensureCorrectionState();
  cs.conflicts.push({
    fieldPath,
    activeValue: activeValue == null ? null : activeValue,
    conflictingValue: conflictingValue == null ? null : conflictingValue,
    sourceText: sourceText || null,
    ts: Date.now()
  });
}

function applyCorrectionPayload(parsed, sourceText){
  if (!parsed || typeof parsed !== "object") return;
  const basics = state?.profile?.basics || {};

  Object.keys(parsed).forEach(fp => {
    const newValue = parsed[fp];

    if (fp === "identity.place_of_birth") {
      const oldValue = basics.pob || null;
      if (oldValue && oldValue !== newValue) _pushConflict(fp, oldValue, newValue, sourceText);
      basics.pob = newValue;
      _pushAppliedCorrection(fp, newValue, oldValue, sourceText);
      return;
    }

    if (fp === "identity.date_of_birth") {
      const oldValue = basics.dob || null;
      if (oldValue && oldValue !== newValue) _pushConflict(fp, oldValue, newValue, sourceText);
      basics.dob = newValue;
      _pushAppliedCorrection(fp, newValue, oldValue, sourceText);
      return;
    }

    if (fp === "family.children.count") {
      const cs = _ensureCorrectionState();
      _pushAppliedCorrection(fp, newValue, null, sourceText);
      cs.uncertain = cs.uncertain.filter(x => x !== "family.children.count");
      return;
    }

    if (fp === "education_work.retirement") {
      _pushAppliedCorrection(fp, newValue, null, sourceText);
      return;
    }

    // Parent-name corrections stay in working layer for now.
    if (fp === "family.parents.father.name" || fp === "family.parents.mother.name") {
      _pushAppliedCorrection(fp, newValue, null, sourceText);
      return;
    }
  });

  // Rebuild echo with updated state
  buildMemoryEchoEntity();
}

/**
 * Build the runtime71 block from live state.
 * This is the single source of truth for both ws.send() payloads.
 */
function buildRuntime71() {
  const current_pass = (typeof getCurrentPass==="function"?getCurrentPass():null)||state.session?.currentPass||"pass1";
  const current_era  = (typeof getCurrentEra==="function"?getCurrentEra():null)||state.session?.currentEra||null;
  const current_mode = (typeof getCurrentMode==="function"?getCurrentMode():null)||state.session?.currentMode||"open";

  // v7.4A — prefer real visual signal when fresh; fall back to synthetic affect.
  // Behavioral invariant: stale (>8s) or absent signal → visual_signals = null.
  // prompt_composer.py must treat null identically to camera-off.
  const vs                  = (state.session && state.session.visualSignals) || null;
  const baselineEstablished = !!(state.session && state.session.affectBaseline && state.session.affectBaseline.established);

  // WO-10G: cameraActive must be true for visual signals to be considered.
  // Prevents stale signals leaking through the 8s window after camera off.
  const hasFreshLiveAffect = !!(
    cameraActive && vs && vs.affectState && vs.timestamp && (Date.now() - vs.timestamp < 8000)
  );

  const affect_state      = hasFreshLiveAffect ? vs.affectState           : (state.runtime?.affectState||"neutral");
  const affect_confidence = hasFreshLiveAffect ? Number(vs.confidence||0) : Number(state.runtime?.affectConfidence||0);

  const visual_signals = hasFreshLiveAffect ? {
    affect_state:         vs.affectState,
    affect_confidence:    Number(vs.confidence||0),
    gaze_on_screen:       (vs.gazeOnScreen !== undefined) ? vs.gazeOnScreen : null,
    baseline_established: baselineEstablished,
    signal_age_ms:        Date.now() - vs.timestamp,
  } : null;

  return {
    current_pass,
    current_era,
    current_mode,
    affect_state,
    affect_confidence,
    cognitive_mode:  state.runtime?.cognitiveMode||null,
    fatigue_score:   Number(state.runtime?.fatigueScore||0),
    /* v7.2 — paired interview metadata */
    paired:          !!(state.interview?.paired),
    paired_speaker:  state.interview?.pairedSpeaker||null,
    /* v7.4A — real visual signal block; null = camera off or stale */
    visual_signals,
    /* v7.4D — assistant role for prompt routing */
    assistant_role:  getAssistantRole(),
    /* WO-HORNELORE-SESSION-LOOP-01 — tier-2 session-style directive.
       For clear_direct / memory_exercise / companion this is a short
       string that prompt_composer appends to the directive block.  For
       warm_storytelling and questionnaire_first this is empty (no
       addendum — the questionnaire walk owns its own Lori prompts).
       Backend gracefully ignores empty / missing values. */
    session_style_directive: (function() {
      try {
        const style = (typeof getSessionStyle === "function") ? getSessionStyle() :
          (state.session && state.session.sessionStyle) || "warm_storytelling";
        return (typeof window._lvEmitStyleDirective === "function")
          ? window._lvEmitStyleDirective(style) || ""
          : "";
      } catch (_) { return ""; }
    })(),
    /* v7.4D Phase 6B — identity gating fields for prompt_composer.py */
    identity_complete: hasIdentityBasics74(),
    identity_phase:    getIdentityPhase74(),
    effective_pass:    getEffectivePass74(),
    /* v7.4E — speaker anchor: persists the user's name so Lori never drifts
       into confusing the speaker with a person mentioned in conversation */
    speaker_name: state.session?.speakerName || state.session?.identityCapture?.name || null,
    /* v7.4E — profile basics: DOB and birthplace for Pass 1 profile-seed context */
    dob: state.profile?.basics?.dob || state.session?.identityCapture?.dob || null,
    pob: state.profile?.basics?.pob || state.session?.identityCapture?.birthplace || null,
    /* v7.4E — profile seed tracking: what seed questions have been answered */
    profile_seed: state.session?.profileSeed || null,
    /* Step 3 — device context: local date, time, timezone.
       Gives Lori reliable temporal grounding on every turn.
       date/time are re-evaluated each call so they stay current. */
    device_context: {
      date:     new Intl.DateTimeFormat("en-US", { weekday:"long", year:"numeric", month:"long", day:"numeric" }).format(new Date()),
      time:     new Intl.DateTimeFormat("en-US", { hour:"numeric", minute:"2-digit", hour12:true }).format(new Date()),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    },
    /* Step 3 — optional location context (city/region only, consent-gated).
       null when user has not opted in or location was unavailable.
       prompt_composer.py must never assume location is present. */
    location_context: state.session?.locationContext || null,
    /* Meaning Engine — memoir context for narrative-aware interview guidance.
       memoir_state: current panel state (empty | threads | draft).
       arc_roles_present: which narrative arc parts have been captured this session.
         prompt_composer.py uses this to identify narrative gaps and shape questions.
       Reads from the memoir panel DOM. Falls back gracefully if panel is not mounted. */
    memoir_context: (function() {
      try {
        const mState = (typeof _memoirState !== "undefined") ? _memoirState : "empty";
        const content = document.getElementById("memoirScrollContent");
        const arcRoles = content
          ? [...new Set(
              Array.from(content.querySelectorAll("mark.new-fact[data-narrative-role]"))
                .map(m => m.dataset.narrativeRole).filter(Boolean)
            )]
          : [];
        const meaningTags = content
          ? [...new Set(
              Array.from(content.querySelectorAll("mark.new-fact[data-meaning-tags]"))
                .flatMap(m => (m.dataset.meaningTags || "").split(",").map(t => t.trim()).filter(Boolean))
            )]
          : [];
        return { state: mState, arc_roles_present: arcRoles, meaning_tags_present: meaningTags };
      } catch (_) {
        return { state: "empty", arc_roles_present: [], meaning_tags_present: [] };
      }
    })(),
    /* Media Builder — photo count for Lori's contextual awareness.
       window._lv80MediaCount is updated by the gallery on every load/upload/delete. */
    media_count: (window._lv80MediaCount || 0),
    /* WO-S3: Projection family snapshot — injects parent/sibling names + occupations.
       Phase G: Read from in-memory canonical state (loaded from backend), NOT directly
       from localStorage. Falls back to localStorage only if in-memory is empty. */
    projection_family: (function() {
      try {
        const pid = state.session?.personId || state.currentPersonId || state.person_id;
        if (!pid) return null;
        // Phase G: prefer in-memory projection (backend-loaded)
        let fields = null;
        const iProj = state.interviewProjection;
        if (iProj && iProj.personId === pid && iProj.fields && Object.keys(iProj.fields).length > 0) {
          fields = iProj.fields;
        }
        // Fallback to localStorage transient draft if in-memory empty
        if (!fields) {
          const raw = localStorage.getItem("lorevox_proj_draft_" + pid);
          if (!raw) return null;
          const parsed = JSON.parse(raw);
          fields = (parsed && parsed.d && parsed.d.fields) || (parsed && parsed.fields) || parsed || {};
        }
        // Helper: projection fields are {value:"...", source:"...", ...} envelopes
        const v = (f) => { const e = fields[f]; return (e && typeof e === "object" ? e.value : e) || ""; };
        const fam = { parents: [], siblings: [] };
        // Collect parents — dedup by (name, relation) to avoid accumulation
        const seenParents = new Set();
        for (let i = 0; i < 10; i++) {
          const fn = v("parents[" + i + "].firstName");
          const ln = v("parents[" + i + "].lastName");
          const rel = v("parents[" + i + "].relation");
          const occ = v("parents[" + i + "].occupation");
          if (fn || ln) {
            const name = (fn + " " + ln).trim();
            const key = (name + "|" + rel).toLowerCase();
            if (!seenParents.has(key)) {
              seenParents.add(key);
              fam.parents.push({ name: name, relation: rel, occupation: occ });
            }
          }
        }
        // Collect siblings — dedup by (name, relation)
        const seenSiblings = new Set();
        for (let i = 0; i < 20; i++) {
          const fn = v("siblings[" + i + "].firstName");
          const ln = v("siblings[" + i + "].lastName");
          const rel = v("siblings[" + i + "].relation");
          if (fn || ln) {
            const name = (fn + " " + ln).trim();
            const key = (name + "|" + rel).toLowerCase();
            if (!seenSiblings.has(key)) {
              seenSiblings.add(key);
              fam.siblings.push({ name: name, relation: rel });
            }
          }
        }
        return (fam.parents.length || fam.siblings.length) ? fam : null;
      } catch (_) { return null; }
    })(),
    /* WO-9: person_id for backend conversation memory context builder */
    person_id: state.person_id || null,
    /* WO-10: conversation state for adaptive memory context */
    conversation_state: _wo10DetectConversationState(),
    /* WO-10C: cognitive support mode — narrator-scoped dementia-safe flag.
       When true, backend shifts to extended silence, invitational prompts,
       single-thread context, no correction, no observation language. */
    cognitive_support_mode: !!(state.session?.cognitiveSupportMode),
    /* WO-KAWA RETIRED 2026-05-01. The kawa_mode field was historically
       routed to a "river" reflective-prompt block in prompt_composer.py
       (WO-KAWA-02A). Per CLAUDE.md design principles ("Life Map is the
       only navigation surface; Kawa is retired as system, UI, and
       logic. Kept as research citation only."), the field no longer
       reaches the LLM. The state.session.kawaMode value is preserved
       for backwards compat with any local callers but never emitted
       in runtime71. Deeper retirement (state field + lori-kawa.js
       module + interview.js helpers) is a follow-up cleanup lane. */
    /* WO-CR-PACK-01 (CR-04) — chronology context for Lori.
       Lightweight, provenance-aware snapshot of the currently focused
       year/era slice of the accordion. Null when trainer mode is active,
       accordion is hidden, or no focus/era context is available.

       Prompt-composer rules (enforced downstream, not here):
         • personal_items[source=promoted_truth] — may be asserted as fact.
         • personal_items[source=profile|questionnaire] — soft cue only.
         • world_items[source=historical_json]  — context only, never
           rephrased as personal biography.
         • ghost_items[source=life_stage_template] — question-shaping
           only, never stated as known history. */
    chronology_context: (typeof crBuildChronologyContext === "function")
      ? crBuildChronologyContext()
      : null,
  };
}

/**
 * WO-10 Phase 5: Lightweight conversation state detection.
 * Returns: storytelling | answering | reflecting | correcting | searching_memory | emotional_pause | null
 */
let _wo10LastUserText = "";
function _wo10DetectConversationState() {
  const text = _wo10LastUserText || "";
  if (!text) return null;
  const lower = text.toLowerCase().trim();
  const len = lower.length;

  let result = null;

  // Correcting: "no, actually...", "I meant...", "let me correct..."
  if (/^(no[,.]?\s+(actually|wait|that'?s not|i meant)|let me correct|i should clarify|that'?s wrong)/i.test(lower)) {
    result = "correcting";
  }
  // Emotional pause: very short after long, or explicit emotional markers
  else if (len < 20 && /\b(yeah|mmm|hmm|oh|sigh)\b/i.test(lower)) {
    result = "emotional_pause";
  }
  else if (/\b(hard to talk about|still miss|tears|crying|breaks my heart)\b/i.test(lower)) {
    result = "emotional_pause";
  }
  // Searching memory: "I'm trying to remember...", "let me think..."
  else if (/\b(trying to remember|let me think|i can'?t recall|what was|where was)\b/i.test(lower)) {
    result = "searching_memory";
  }
  // Reflecting: thoughtful, measured responses with qualifiers
  else if (/\b(looking back|in hindsight|when i think about|i realize now|i suppose)\b/i.test(lower)) {
    result = "reflecting";
  }
  // Storytelling: long narrative (>200 chars with conjunctions and temporal markers)
  else if (len > 200 && /\b(and then|so we|after that|the next|one day|that was when)\b/i.test(lower)) {
    result = "storytelling";
  }
  // Answering: short-to-medium direct responses
  else if (len < 200) {
    result = "answering";
  }
  // Default for longer text
  else {
    result = "storytelling";
  }

  // WO-10B: Expose state for no-interruption engine
  _wo10bCurrentConversationState = result;
  window._wo10bCurrentConversationState = result;
  return result;
}

/**
 * Set Lori's operational state.
 * Propagates to state.runtime (→ prompt_composer) AND updates the UI badge.
 */
function setLoriState(s){
  const norm = normalizeLoriState(s);

  // Only semantic states update state.runtime.
  // Transitional states (thinking / drafting / listening) are badge-only
  // and must NEVER overwrite runtime values set by the user or affect engine.
  if (norm !== null) {
    if (!state.runtime) state.runtime = {};
    if (!state.session) state.session = {};
    state.runtime.affectState      = norm.affectState;
    state.runtime.affectConfidence = norm.affectConfidence;
    state.runtime.cognitiveMode    = norm.cognitiveMode;
    state.runtime.fatigueScore     = norm.fatigueScore;
    state.session.currentMode      = norm.cognitiveMode;
  }

  // UI badge
  const el=document.getElementById("loriStatus"); if(!el) return;
  el.className=`lori-status ${s}`;
  const builtIn={ready:"<div class='status-dot'></div> Ready",thinking:"<div class='status-dot'></div> Thinking",drafting:"<div class='status-dot'></div> Drafting",listening:"<div class='status-dot'></div> Listening"};
  const badgeLabel = norm ? norm.badge : s.charAt(0).toUpperCase()+s.slice(1);
  el.innerHTML=builtIn[s]||`<div class='status-dot'></div> ${badgeLabel}`;

  // Refresh any 7.1 UI elements
  if (typeof update71RuntimeUI==="function") update71RuntimeUI();
  if (window.LORI71?.updateBadges)           window.LORI71.updateBadges();
  if (window.LORI71?.updateDebugOverlay)     window.LORI71.updateDebugOverlay();

  console.log("[Lori 7.1] setLoriState →", s, "| runtime =", {
    affectState:      state.runtime.affectState,
    affectConfidence: state.runtime.affectConfidence,
    cognitiveMode:    state.runtime.cognitiveMode,
    fatigueScore:     state.runtime.fatigueScore,
  });
}

/* ═══════════════════════════════════════════════════════════════
   LAYOUT TOGGLES
═══════════════════════════════════════════════════════════════ */
function toggleSidebar(){
  document.getElementById("gridLayout").classList.toggle("sb-closed");
}
function toggleChat(){
  document.getElementById("gridLayout").classList.toggle("chat-closed");
}
function toggleFocus(){
  isFocusMode=!isFocusMode;
  document.getElementById("gridLayout").classList.toggle("focus-mode",isFocusMode);
  document.getElementById("btnFocus").style.color=isFocusMode?"#7c9cff":"";
  const hint=document.getElementById("focusHint");
  if(isFocusMode){ hint.classList.add("show"); setTimeout(()=>hint.classList.remove("show"),2500); }
  else hint.classList.remove("show");
}
function toggleDevMode(){
  devMode=!devMode;
  // Toggle body class (used by lori73.css to control dev-only visibility)
  document.body.classList.toggle("lv73-dev-mode", devMode);
  // Also toggle hidden class for JS-controlled show/hide
  document.querySelectorAll(".dev-only").forEach(el=>el.classList.toggle("hidden",!devMode));
  document.getElementById("btnDevMode").style.color=devMode?"#7c9cff":"";
}

/* ═══════════════════════════════════════════════════════════════
   PEOPLE
═══════════════════════════════════════════════════════════════ */
async function refreshPeople(){
  try{
    const r=await fetch(API.PEOPLE+"?limit=200");
    const j=await r.json();
    let items=j.items||j.people||j||[];
    // WO-11B: filter to Hornelore family only
    if (typeof _horneloreFilterVisiblePeople === "function") {
      items = _horneloreFilterVisiblePeople(items);
    }
    renderPeople(items);
    // v8: cache for narrator card UI
    if (state?.narratorUi) {
      state.narratorUi.peopleCache = items;
    }
    // Cache for offline fallback
    try{ localStorage.setItem("lorevox_offline_people",JSON.stringify(items)); }catch{}
  }catch{
    // Offline fallback — read from localStorage cache
    try{
      const cached=localStorage.getItem("lorevox_offline_people");
      if(cached){ renderPeople(JSON.parse(cached)); return; }
    }catch{}
    renderPeople([]);
  }
}
function renderPeople(items){
  const w=document.getElementById("peopleList"); w.innerHTML="";
  // Filter to active narrators if lorevox_draft_pids is set
  const _aPids=JSON.parse(localStorage.getItem("lorevox_draft_pids")||"[]");
  const _items=_aPids.length>0?(items||[]).filter(p=>_aPids.includes(p.id||p.person_id)):items;
  (_items||[]).forEach(p=>{
    const pid=p.id||p.person_id||p.uuid; if(!pid) return;
    const name=p.display_name||p.name||pid;
    // WO-13 Phase 3 — reference narrators get a visible read-only badge
    const isRef = String(p.narrator_type||"live").toLowerCase() === "reference";
    const refBadge = isRef
      ? ` <span class="wo13-ref-badge" title="Reference narrator (read-only)" style="display:inline-block;font-size:10px;padding:1px 5px;border-radius:3px;background:#4b5563;color:#e5e7eb;margin-left:6px;vertical-align:middle">REF</span>`
      : "";
    const d=document.createElement("div");
    d.className="sb-item"+(pid===state.person_id?" active":"")+(isRef?" wo13-readonly":"");
    d.onclick=()=>loadPerson(pid);
    d.innerHTML=`<div class="font-bold text-white truncate" style="font-size:15px">${esc(name)}${refBadge}</div>
      <div class="sb-meta mono dev-only">${esc(pid.slice(0,16))}</div>`;
    w.appendChild(d);
  });
  if(!(items||[]).length)
    w.innerHTML=`<div class="text-xs text-slate-500 px-2">No people yet. Fill Profile and click + New Person.</div>`;
}
async function createPersonFromForm(){
  // FIX-2: Clear stale narrator state from header before creating new narrator.
  // Without this, the header card briefly shows the previous narrator's DOB/POB.
  state.profile = { basics: {}, kinship: [], pets: [] };
  if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();
  const b=scrapeBasics();
  const display_name=b.fullname||b.preferred||"Unnamed";
  try{
    const r=await fetch(API.PEOPLE,{method:"POST",headers:ctype(),
      body:JSON.stringify({display_name,role:"subject",date_of_birth:b.dob||null,place_of_birth:b.pob||null})});
    const j=await r.json();
    const pid=j.id||j.person_id; if(!pid) throw new Error("no id");
    profileSaved=true;
    sysBubble(`✅ Created: ${display_name}`);
    await refreshPeople(); await loadPerson(pid);
  }catch{ sysBubble("⚠ Create failed — is the server running?"); }
}
let _loadGeneration=0;
async function loadPerson(pid){
  const gen=++_loadGeneration;
  const _prevPersonId = state.person_id;
  state.person_id=pid;
  document.getElementById("activePerson").textContent=`person_id: ${pid}`;
  localStorage.setItem(LS_ACTIVE,pid);
  // WO-11C: If footer was locked pending narrator selection (post-trainer handoff),
  // unlock it now that a real narrator is being loaded.
  if (state.trainerNarrators && state.trainerNarrators._wo11cPendingUnlock && pid) {
    state.trainerNarrators._wo11cPendingUnlock = false;
    if (typeof window._wo11cUnlockFooter === "function") window._wo11cUnlockFooter();
    console.log("[WO-11C] Footer unlocked — narrator selected after trainer exit:", pid);
  }
  // WO-2: Send sync_session to backend when person changes
  if(ws && wsReady && pid !== _prevPersonId){
    ws.send(JSON.stringify({type:"sync_session",person_id:pid,
      old_conv_id:state.chat?.conv_id||""}));
    const ci=document.getElementById("chatInput");
    if(ci){ ci.disabled=true; ci.placeholder="Syncing session…"; }
  }
  // v7.4D ISSUE-16: update the always-visible active person indicator in the Lori dock.
  // The display_name is not available yet (profile loads below); update again after.
  _updateDockActivePerson();
  try{
    const r=await fetch(API.PROFILE(pid)); if(!r.ok) throw new Error();
    const j=await r.json();
    // Guard: only assign if this is still the active load (prevents race on rapid switch)
    if(gen!==_loadGeneration) return;
    state.profile=normalizeProfile(j.profile||j||{});
    profileSaved=true;
    // Cache for offline fallback
    try{ localStorage.setItem("lorevox_offline_profile_"+pid,JSON.stringify(state.profile)); }catch{}
  }catch{
    // Guard: bail if superseded
    if(gen!==_loadGeneration) return;
    // Offline fallback — read from localStorage cache
    try{
      const cached=localStorage.getItem("lorevox_offline_profile_"+pid);
      if(cached){ state.profile=normalizeProfile(JSON.parse(cached)); profileSaved=true; }
      else{ state.profile={basics:{},kinship:[],pets:[]}; profileSaved=false; }
    }catch{
      state.profile={basics:{},kinship:[],pets:[]};
      profileSaved=false;
    }
  }
  // Load persisted section progress
  const saved=localStorage.getItem(LS_DONE(pid));
  if(saved){ try{ sectionDone=JSON.parse(saved); }catch{} }
  else sectionDone=new Array(INTERVIEW_ROADMAP.length).fill(false);

  // Load persisted sensitive segment decisions for this person.
  // This ensures the Private Segments tab is populated immediately on person
  // select, not only after a new interview session starts.
  _loadSegments();

  hydrateProfileForm();
  updateProfileStatus();
  _updateDockActivePerson(); // v7.4D ISSUE-16: update with real name now that profile is loaded
  await refreshPeople();
  onDobChange();
  updateSidebar();
  renderEventsGrid();
  // v7.1 — restore persisted timeline spine before rendering
  const _cachedSpine = loadSpineLocal(pid);
  if (_cachedSpine) {
    state.timeline.spine    = _cachedSpine;
    state.timeline.seedReady = true;
    if (!state.session.currentEra && _cachedSpine.periods?.length) {
      // WO-CANONICAL-LIFE-SPINE-01 Step 3d: prefer era_id (set by
      // initTimelineSpine after 3d); fall back to label for cached
      // spines from before this migration. setEra() canonicalizes
      // via state.js _canonicalEra so a stale legacy label like
      // "early_childhood" still becomes "earliest_years".
      const p0 = _cachedSpine.periods[0];
      setEra(p0.era_id || p0.label);
    }
    if (state.session.currentPass === "pass1") setPass("pass2a");
  }
  renderTimeline();
  updateContextTriggers();
  updateArchiveReadiness();
  updateObitIdentityCard(state.profile?.basics||{});
  // Update memoir source name
  const msn=document.getElementById("memoirSourceName");
  if(msn){ const n=state.profile?.basics?.preferred||state.profile?.basics?.fullname||"No person selected"; msn.textContent=n; }
  // Life Map — refresh after person load (view layer only, no state mutation)
  window.LorevoxLifeMap?.refresh();
  // Bio Builder — refresh per-narrator state when person switches
  window.LorevoxBioBuilder?.refresh();

  // v8: auto-initialize interview projection from localStorage
  // This fixes the bug where projection state is empty after reload
  // despite data existing in localStorage under lorevox_proj_draft_<pid>.
  if (typeof _ivResetProjectionForNarrator === "function") {
    _ivResetProjectionForNarrator(pid);
  }

  // FIX-8: Seed identity projection fields from profile for narrators created
  // via "+New" (which bypass the identity onboarding phase). Without this,
  // narrator-2+ would have empty identity fields in the projection even though
  // the profile has fullName, preferredName, dateOfBirth, placeOfBirth.
  if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
    var basics = state.profile?.basics || {};
    var projFields = state.interviewProjection.fields || {};
    var identityMap = {
      "personal.fullName": basics.fullname || basics.fullName || "",
      "personal.preferredName": basics.preferred || basics.preferredName || "",
      "personal.dateOfBirth": basics.dob || basics.dateOfBirth || "",
      "personal.placeOfBirth": basics.pob || basics.placeOfBirth || ""
    };
    Object.keys(identityMap).forEach(function(fp) {
      var val = identityMap[fp];
      var existingVal = projFields[fp] ? projFields[fp].value : null;
      // Seed if empty OR if existing value doesn't match profile (stale cross-narrator data)
      if (val && (!existingVal || existingVal !== val)) {
        LorevoxProjectionSync.projectValue(fp, val, {
          source: "profile_seed",
          confidence: 1.0,
          turnId: "profile-init-" + pid.slice(0, 8)
        });
      }
    });
  }

  // v8.0 FIX: Ensure header card reflects loaded narrator immediately.
  // This fixes the header showing "Choose a narrator" when a valid narrator
  // is loaded, and ensures DOB/POB appear in the header on page reload.
  if (typeof lv80UpdateActiveNarratorCard === "function") {
    lv80UpdateActiveNarratorCard();
  }
}

/* ═══════════════════════════════════════════════════════════════
   v8 NARRATOR SWITCH SAFETY
   Central narrator switch with hard reset + hydration.
   Works even when Bio Builder popover is closed.
═══════════════════════════════════════════════════════════════ */
async function lvxSwitchNarratorSafe(pid){
  if (!pid) return;
  if (pid === state.person_id) return;

  // WO-11 (TRAINER MODE REPAIR): trainer-active stomp guard.
  // When the trainer overlay is up, the narrator switch must NOT wipe
  // trainer state and must NOT reset the surrounding session posture
  // (identityPhase / assistantRole / currentPass / currentEra / currentMode /
  // confusionTurnCount). The new person still loads — this is intentional
  // so profile/timeline UI updates — but the trainer flow continues.
  var _trainerLive = !!(state.trainerNarrators && state.trainerNarrators.active);

  // WO-11B + WO-11: hard reset trainer/capture state before a narrator
  // switch — but ONLY if trainer is not currently live.
  if (!_trainerLive && typeof window.lv80ClearTrainerAndCaptureState === "function") {
    window.lv80ClearTrainerAndCaptureState();
  }

  // ── v9.0 HARD RESET on narrator switch ──────────────────────
  // Purge ALL narrator-scoped state so nothing bleeds across narrators.

  // 1. Clear conversation session — this is the #1 source of context bleed.
  //    The backend loads turn history by conv_id; if we reuse it, Lori sees
  //    the OLD narrator's entire conversation.
  // v9.0 FIX: Generate a FRESH conv_id instead of null.
  // null falls back to "default" which is shared by ALL narrators.
  state.chat.conv_id = "switch_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2,6);

  // 2. Clear interview session — prevents stale interview questions
  state.interview = state.interview || {};
  state.interview.session_id  = null;
  state.interview.question_id = null;
  state.interview.plan_id     = null;

  if (!_trainerLive) {
    // 3. Clear identity onboarding state (WO-11 guard: trainer keeps its posture)
    state.session.identityPhase   = null;
    state.session.identityCapture = { name: null, dob: null, birthplace: null };
    state.session.speakerName     = null;
    state.session.assistantRole   = "interviewer";

    // 4. Clear runtime signals that are narrator-specific (WO-11 guard)
    state.session.currentPass = "pass1";
    state.session.currentEra  = null;
    state.session.currentMode = "open";
    state.session.confusionTurnCount = 0;
  } else {
    console.log("[WO-11] narrator switch with trainer active — preserving trainer posture");
  }

  // 5. Clear in-memory text state
  lastAssistantText = "";
  currentAssistantBubble = null;
  _lastUserTurn = "";

  // hard clear narrator-scoped UI before profile hydration
  if (window.LorevoxBioBuilder?.onNarratorSwitch) {
    window.LorevoxBioBuilder.onNarratorSwitch(pid);
  }

  // v8: reset interview projection for incoming narrator
  if (typeof _ivResetProjectionForNarrator === "function") {
    _ivResetProjectionForNarrator(pid);
  }

  // clear narrator-scoped visible UI
  try {
    document.getElementById("chatMessages").innerHTML = "";
  } catch (_) {}

  if (typeof _memoirClearContent === "function") _memoirClearContent();

  console.log("[narrator-switch] Hard reset complete — loading new narrator:", pid);
  await loadPerson(pid);

  // Phase G: hydrate canonical state from backend state-snapshot
  // This ensures backend authority overrides any stale localStorage data
  try {
    const snapResp = await fetch(API.NARRATOR_STATE(pid));
    if (snapResp.ok) {
      const snap = await snapResp.json();
      console.log("[app] Phase G: narrator state snapshot loaded for " + pid);
      // Backend questionnaire overwrites in-memory if non-empty
      if (snap.questionnaire && Object.keys(snap.questionnaire).length > 0) {
        const bb = state.bioBuilder;
        if (bb) {
          bb.questionnaire = snap.questionnaire;
          try { localStorage.setItem("lorevox_qq_draft_" + pid, JSON.stringify({ v: 1, d: snap.questionnaire })); } catch(_){}
        }
      }
      // Backend projection overwrites in-memory if non-empty
      if (snap.projection && snap.projection.fields && Object.keys(snap.projection.fields).length > 0) {
        const iProj = state.interviewProjection;
        if (iProj) {
          iProj.fields = snap.projection.fields;
          iProj.pendingSuggestions = snap.projection.pendingSuggestions || [];
        }
      }
      // WO-13: Stash prior user-turn count so resume prompts can be gated.
      // A fresh narrator (count = 0) must NOT trigger "welcome back" greetings.
      state.session = state.session || {};
      state.session.priorUserTurns = Number(snap.user_turn_count || 0);
      console.log("[WO-13] priorUserTurns for " + pid.slice(0, 8) + " = " + state.session.priorUserTurns);
    }
  } catch (e) {
    console.warn("[app] Phase G: state-snapshot fetch failed (proceeding with local data)", e);
  }

  // WO-10C cognitive-support-mode per-narrator hydration (2026-05-06):
  // Each narrator carries their own CSM preference (Janice/Kent ON,
  // Christopher might prefer OFF). Read the per-narrator localStorage
  // key, apply to state + runtime71 + checkbox. Falls back to operator-
  // default when the narrator has no per-narrator setting yet.
  try {
    if (typeof lvHydrateCognitiveSupportModeForNarrator === "function") {
      lvHydrateCognitiveSupportModeForNarrator(pid);
    }
  } catch (e) {
    console.warn("[wo10c][csm-toggle] per-narrator hydrate threw (non-fatal):", e);
  }

  // run a second hydration after profile is loaded
  if (window.LorevoxBioBuilder?.onNarratorSwitch) {
    window.LorevoxBioBuilder.onNarratorSwitch(pid);
  }

  if (window.LorevoxBioBuilder?.refresh) window.LorevoxBioBuilder.refresh();
  if (window.LorevoxLifeMap?.render)     window.LorevoxLifeMap.render(true);

  // WO-8: Load transcript history and fire resume prompt
  if (typeof wo8OnNarratorReady === "function") {
    wo8OnNarratorReady(pid).catch(e => console.log("[WO-8] narrator ready hook failed:", e.message));
  }
}

/* ═══════════════════════════════════════════════════════════════
   v9 NARRATOR OPEN GATING — readiness classification
   Returns "ready" | "incomplete" | "missing" | "new"
   Single source of truth for narrator conversation-readiness.
═══════════════════════════════════════════════════════════════ */
function getNarratorOpenState(pid) {
  if (!pid) return "new";
  if (!state.person_id || state.person_id !== pid) return "missing";

  const basics = state.profile?.basics || {};
  const hasName = !!(basics.preferred || basics.fullname);
  const hasDob  = !!basics.dob;

  if (hasName && hasDob) return "ready";
  return "incomplete";
}

/* Expose globally for lori9.0.html */
window.getNarratorOpenState = getNarratorOpenState;

/* ═══════════════════════════════════════════════════════════════
   v8 NARRATOR DELETE FLOW
   Multi-step delete with backup + undo window.
═══════════════════════════════════════════════════════════════ */
function lvxBuildNarratorBackup(person){
  return {
    person,
    profile: JSON.parse(JSON.stringify(state.profile || {})),
    bioBuilder: JSON.parse(JSON.stringify(state.bioBuilder || {})),
    timestamp: Date.now()
  };
}

async function lvxGetDeleteInventory(pid){
  try{
    const r = await fetch(API.PERSON_INVENTORY(pid));
    if (!r.ok) return null;
    return await r.json();
  }catch(e){
    console.warn("[Lorevox] inventory fetch failed", e);
    return null;
  }
}

async function lvxStageDeleteNarrator(pid){
  const people = state?.narratorUi?.peopleCache || [];
  const person = people.find(p => (p.id||p.person_id||p.uuid) === pid);
  if (!person) return;

  // Fetch dependency inventory from backend
  const inv = await lvxGetDeleteInventory(pid);

  state.narratorDelete.targetId = pid;
  state.narratorDelete.targetLabel = person.display_name || person.name || pid;
  state.narratorDelete.confirmText = "";
  state.narratorDelete.step = 1;
  state.narratorDelete.backup = lvxBuildNarratorBackup(person);
  state.narratorDelete.inventory = inv ? inv.counts : null;
  window.lv80OpenDeleteDialog?.();
}

async function lvxDeleteNarratorConfirmed(){
  const pid = state?.narratorDelete?.targetId;
  if (!pid) return;
  if (state.narratorDelete.confirmText !== "DELETE") return;

  // Phase 2: use backend soft delete (preserves data, allows restore)
  try{
    const r = await fetch(API.PERSON(pid) + "?mode=soft", { method:"DELETE" });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      console.warn("[Lorevox] soft delete failed:", r.status, err);
    }
  }catch(e){
    console.warn("[Lorevox] delete narrator failed", e);
  }

  // Store deleted person_id for undo (backend restore uses original ID)
  state.narratorDelete.deletedPid = pid;

  // Hornelore: remember deleted label so auto-seed does not immediately recreate
  if (state.narratorDelete && state.narratorDelete.targetLabel) {
    _horneloreMarkDeletedNarrator(state.narratorDelete.targetLabel);
  }

  // clear active pointer if needed
  if (state.person_id === pid) {
    state.person_id = null;
    localStorage.removeItem(LS_ACTIVE);
  }

  // v8.0 FIX: Clean up ALL offline caches for deleted narrator to prevent ghost narrators
  // Phase 5: Added ft_draft and lt_draft cleanup, plus sources_draft
  try {
    localStorage.removeItem("lorevox_offline_profile_" + pid);
    localStorage.removeItem("lorevox_proj_draft_" + pid);
    localStorage.removeItem("lorevox_qq_draft_" + pid);
    localStorage.removeItem("lorevox_ft_draft_" + pid);
    localStorage.removeItem("lorevox_lt_draft_" + pid);
    localStorage.removeItem("lorevox_sources_draft_" + pid);
    localStorage.removeItem("lorevox.spine." + pid);
    localStorage.removeItem(LS_DONE(pid));
    localStorage.removeItem(LS_SEGS(pid));
  } catch(_) {}
  // Phase 5: Also clear from bio-builder-core draft index
  try {
    var bbCore = window.LorevoxBioBuilderModules && window.LorevoxBioBuilderModules.core;
    if (bbCore && bbCore._clearDrafts) bbCore._clearDrafts(pid);
  } catch(_) {}
  // Refresh the offline people cache
  try { localStorage.removeItem("lorevox_offline_people"); } catch(_) {}
  // Phase 5.2: Verify no orphaned narrator-scoped draft keys remain
  try {
    var _orphanCheck = ["lorevox_offline_profile_","lorevox_proj_draft_","lorevox_qq_draft_",
      "lorevox_ft_draft_","lorevox_lt_draft_","lorevox_sources_draft_","lorevox.spine."];
    var _orphans = _orphanCheck.filter(function(prefix) { return localStorage.getItem(prefix + pid) !== null; });
    if (_orphans.length) {
      console.warn("[narrator-delete] Orphaned keys found after cleanup:", _orphans.map(function(p){return p+pid;}));
    } else {
      console.log("[narrator-delete] Cleanup verified — no orphaned draft keys for pid=" + pid.slice(0,8));
    }
  } catch(_) {}

  // v8.0 FIX: Update header to blank state if deleted narrator was active
  if (typeof lv80UpdateActiveNarratorCard === "function") {
    lv80UpdateActiveNarratorCard();
  }

  await refreshPeople();
  window.lv80CloseDeleteDialog?.();
  window.lv80ShowUndoDelete?.();
}

async function lvxUndoDeleteNarrator(){
  // Phase 2: use backend restore endpoint (no duplicate creation)
  const pid = state?.narratorDelete?.deletedPid;
  if (!pid) return;

  try{
    const r = await fetch(API.PERSON_RESTORE(pid), { method:"POST" });
    if (r.ok) {
      await refreshPeople();
      // Narrator is back — switch to it if nothing else is active
      if (!state.person_id) await lvxSwitchNarratorSafe(pid);
    } else {
      const err = await r.json().catch(() => ({}));
      console.warn("[Lorevox] restore failed:", r.status, err);
      // If undo_expired or other error, notify user
      if (err.detail) alert("Restore failed: " + err.detail);
    }
  }catch(e){
    console.warn("[Lorevox] undo narrator restore failed", e);
  }

  state.narratorDelete.deletedPid = null;
}

function normalizeProfile(p){
  const b=p.basics||p.basic||p.identity||{};
  return {
    basics:{fullname:b.fullname||"",preferred:b.preferred||"",dob:b.dob||"",
            pob:b.pob||"",culture:b.culture||"",country:b.country||"us",
            pronouns:b.pronouns||"",phonetic:b.phonetic||"",
            language:b.language||"",                           // v6.2 bilingual
            legalFirstName:b.legalFirstName||"",               // v8.0
            legalMiddleName:b.legalMiddleName||"",             // v8.0
            legalLastName:b.legalLastName||"",                 // v8.0
            timeOfBirth:b.timeOfBirth||"",                     // v8.0
            timeOfBirthDisplay:b.timeOfBirthDisplay||"",       // v8.0
            birthOrder:b.birthOrder||"",                       // v8.0
            birthOrderCustom:b.birthOrderCustom||"",           // v8.0
            zodiacSign:b.zodiacSign||"",                       // v8.0
            placeOfBirthRaw:b.placeOfBirthRaw||"",             // v8.0
            placeOfBirthNormalized:b.placeOfBirthNormalized||""},// v8.0
    kinship:Array.isArray(p.kinship||p.family)?p.kinship||p.family:[],
    pets:Array.isArray(p.pets)?p.pets:[],
  };
}
async function saveProfile(){
  if(!state.person_id){ sysBubble("Select or create a person first."); return; }
  scrapeProfileForm();
  try{
    const r=await fetch(API.PROFILE(state.person_id),{method:"PUT",headers:ctype(),
      body:JSON.stringify({profile:{basics:state.profile.basics,kinship:state.profile.kinship,pets:state.profile.pets}})});
    if(!r.ok) throw new Error();
    profileSaved=true;
    // WO-PROVISIONAL-TRUTH-01 Phase C (2026-05-04):
    // Operator-tone status bubble retired from narrator surface by default.
    // Locked principle #3 (no system-tone narrator outputs) applies — "💾
    // Profile saved." is dev/operator language, not narrator language.
    // Re-enable for dev observation by setting localStorage[
    // 'LV_INLINE_OPERATOR_BUBBLES']='true' or window.LV_INLINE_OPERATOR_BUBBLES=true.
    if (window.LV_INLINE_OPERATOR_BUBBLES === true ||
        (typeof localStorage !== "undefined" && localStorage.getItem("LV_INLINE_OPERATOR_BUBBLES") === "true")) {
      sysBubble("💾 Profile saved.");
    }
    updateProfileStatus();
    // v7.1 — initialize timeline spine when DOB + birthplace are present
    if (getTimelineSeedReady()) {
      initTimelineSpine();
    }
    updateArchiveReadiness();
    // Life Map — refresh after profile save so spine changes are reflected
    window.LorevoxLifeMap?.refresh();
    // Bio Builder — refresh if open (no truth mutation; staging layer only)
    window.LorevoxBioBuilder?.refresh();
    if(state.chat?.conv_id){
      fetch(API.SESS_PUT,{method:"POST",headers:ctype(),body:JSON.stringify({
        conv_id:state.chat.conv_id,
        payload:{profile:state.profile,person_id:state.person_id}
      })}).catch(()=>{});
    }
    const b=state.profile.basics;
    fetch(API.PERSON(state.person_id),{method:"PATCH",headers:ctype(),body:JSON.stringify({
      display_name:b.preferred||b.fullname||undefined,
      date_of_birth:b.dob||undefined,
      place_of_birth:b.pob||undefined
    })}).catch(()=>{});
  }catch{ sysBubble("⚠ Save failed — is the server running?"); }
}

// WO-13 Phase 8: refresh state.profile from server and push to session.
// Called by wo13PromoteClicked after a successful promote so the
// memoir/obituary/chat surfaces all see the new promoted truth
// without a manual page reload.
window.lvxRefreshProfileFromServer = async function(pid) {
  if (!pid) return;
  try {
    const r = await fetch(API.PROFILE(pid));
    if (!r.ok) return;
    const j = await r.json();
    state.profile = normalizeProfile(j.profile || j || {});
    try { localStorage.setItem("lorevox_offline_profile_"+pid, JSON.stringify(state.profile)); } catch {}
    hydrateProfileForm();
    updateObitIdentityCard(state.profile?.basics || {});
    const msn = document.getElementById("memoirSourceName");
    if (msn) {
      const n = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "No person selected";
      msn.textContent = n;
    }
    renderTimeline();
    if (state.chat?.conv_id) {
      fetch(API.SESS_PUT, {
        method: "POST",
        headers: ctype(),
        body: JSON.stringify({
          conv_id: state.chat.conv_id,
          payload: { profile: state.profile, person_id: pid },
        }),
      }).catch(() => {});
    }
  } catch (e) {
    console.warn("[lvx] refresh profile after promote failed:", e);
  }
};

/* ── v8.0: Bio Builder → Profile sync bridge ── */
/**
 * Applies Bio Builder personal-section data to state.profile.basics
 * WITHOUT auto-promotion. Caller must explicitly invoke this.
 * Returns true if any field was updated, false otherwise.
 */
function applyBioBuilderPersonalToProfile(){
  if(!window.LorevoxBioBuilder?.buildCanonicalBasicsFromBioBuilder) return false;
  const canonical=window.LorevoxBioBuilder.buildCanonicalBasicsFromBioBuilder();
  if(!canonical) return false;
  if(!state.profile) state.profile=normalizeProfile({});
  const b=state.profile.basics;
  let changed=false;
  // Map bio builder → profile basics (only overwrite if bio builder has a value)
  const map={fullname:"fullname",preferred:"preferred",dob:"dob",pob:"pob",
             legalFirstName:"legalFirstName",legalMiddleName:"legalMiddleName",
             legalLastName:"legalLastName",
             timeOfBirth:"timeOfBirth",timeOfBirthDisplay:"timeOfBirthDisplay",
             birthOrder:"birthOrder",birthOrderCustom:"birthOrderCustom",
             zodiacSign:"zodiacSign",
             placeOfBirthRaw:"placeOfBirthRaw",placeOfBirthNormalized:"placeOfBirthNormalized"};
  for(const [bbKey,profKey] of Object.entries(map)){
    if(canonical[bbKey] && canonical[bbKey]!==b[profKey]){
      b[profKey]=canonical[bbKey]; changed=true;
    }
  }
  if(changed){
    // Hydrate hidden inputs so next scrapeBasics picks them up
    hydrateProfileForm();
  }
  return changed;
}

/* ── v7.4D ISSUE-16: Active person dock indicator ── */
function _updateDockActivePerson(){
  const el = document.getElementById("dockActivePerson");
  if(!el) return;
  const name = state.profile?.basics?.preferred || state.profile?.basics?.fullname;
  if(state.person_id && name){
    el.textContent = `📘 ${name}`;
    el.style.display = "";
  } else if(state.person_id){
    el.textContent = "📘 Person loaded";
    el.style.display = "";
  } else {
    el.style.display = "none";
  }
}

/* ── Profile status badge ── */
function updateProfileStatus(){
  const el=document.getElementById("profileStatusBadge"); if(!el) return;
  if(!state.person_id){
    el.className="profile-status none"; el.textContent="No person selected"; return;
  }
  const name=state.profile?.basics?.preferred||state.profile?.basics?.fullname;
  if(profileSaved){
    el.className="profile-status connected";
    el.textContent=(name?`${name} — `:"")+"Profile connected";
  } else {
    el.className="profile-status unsaved";
    el.textContent="Profile not yet saved";
  }
}

/* ── Archive Readiness ── */
function updateArchiveReadiness(){
  const el=document.getElementById("readinessChecks"); if(!el) return;
  const b=state.profile?.basics||{};
  const seedReady = getTimelineSeedReady();
  const spineReady = !!state.timeline?.spine;
  const checks=[
    // v7.1 — timeline seed checks come first
    {label:"Date of birth added",        ok:!!b.dob},
    {label:"Birthplace added",            ok:!!b.pob},
    {label:"Timeline seed ready",         ok:seedReady},
    {label:"Pass 2A available",           ok:spineReady},
    // existing checks
    {label:"Pronouns set",                ok:!!b.pronouns},
    {label:"Family started",              ok:(state.profile?.kinship||[]).length>0},
    {label:"Profile saved",               ok:profileSaved},
  ];
  el.innerHTML=checks.map(c=>`
    <div class="readiness-item${c.ok?" ok":""}">
      <div class="readiness-dot ${c.ok?"ok":"miss"}"></div>
      <span>${c.label}</span>
      ${c.ok?'<span style="color:#4ade80;font-size:10px;margin-left:auto">✓</span>':''}
    </div>`).join("");
  // v7.1 — update Pass 2A badge if present
  const pass2aBadge = document.getElementById("pass2aAvailBadge");
  if (pass2aBadge) {
    pass2aBadge.className = spineReady ? "seed-badge" : "seed-badge pending";
    pass2aBadge.textContent = spineReady ? "Pass 2A — ready" : "Pass 2A — not ready";
  }
  if(!document.getElementById("pane-obituary")?.classList.contains("hidden"))
    updateObitIdentityCard(b);
}

function hydrateProfileForm(){
  const b=state.profile.basics||{};
  setv("bio_fullname",b.fullname); setv("bio_preferred",b.preferred);
  setv("bio_dob",b.dob);          setv("bio_pob",b.pob);
  setv("bio_culture",b.culture||""); setv("bio_phonetic",b.phonetic||"");
  // v8.0 bio builder extended fields
  setv("bio_legalFirstName",b.legalFirstName||"");
  setv("bio_legalMiddleName",b.legalMiddleName||"");
  setv("bio_legalLastName",b.legalLastName||"");
  setv("bio_timeOfBirth",b.timeOfBirth||"");
  setv("bio_timeOfBirthDisplay",b.timeOfBirthDisplay||"");
  setv("bio_birthOrder",b.birthOrder||"");
  setv("bio_birthOrderCustom",b.birthOrderCustom||"");
  setv("bio_zodiacSign",b.zodiacSign||"");
  setv("bio_placeOfBirthRaw",b.placeOfBirthRaw||"");
  setv("bio_placeOfBirthNormalized",b.placeOfBirthNormalized||"");
  const sel=document.getElementById("bio_country");
  if(sel && b.country) sel.value=b.country;
  const langSel=document.getElementById("bio_language");  // v6.2
  if(langSel && b.language) langSel.value=b.language;
  const proSel=document.getElementById("bio_pronouns");
  if(proSel && b.pronouns){
    const known=["","she/her","he/him","they/them"];
    if(known.includes(b.pronouns)){ proSel.value=b.pronouns; }
    else{ proSel.value="custom"; setv("bio_pronouns_custom",b.pronouns);
      const w=document.getElementById("bio_pronouns_custom_wrap"); if(w) w.classList.remove("hidden"); }
  }
  const kt=document.getElementById("tblKinship"); kt.innerHTML="";
  (state.profile.kinship||[]).forEach(k=>addKinRow(k.relation||"Sibling",k));
  if(!(state.profile.kinship||[]).length) addKin("Mother");
  const pt=document.getElementById("tblPets"); pt.innerHTML="";
  if((state.profile.pets||[]).length){
    (state.profile.pets||[]).forEach(p=>addPetRow(p));
  } else {
    pt.innerHTML=`<div class="text-xs text-slate-500 italic">Pets are powerful memory anchors — favorite stories often surface here.</div>`;
  }
}
function scrapeBasics(){
  const proSel=document.getElementById("bio_pronouns");
  const pronouns=(proSel?.value==="custom"?getv("bio_pronouns_custom"):proSel?.value)||"";
  const langSel=document.getElementById("bio_language");
  return {
    fullname:getv("bio_fullname"),preferred:getv("bio_preferred"),
    dob:getv("bio_dob"),pob:getv("bio_pob"),
    culture:getv("bio_culture"),country:document.getElementById("bio_country").value,
    pronouns,phonetic:getv("bio_phonetic"),
    language:langSel?langSel.value:"",                         // v6.2 bilingual
    legalFirstName:getv("bio_legalFirstName")||"",              // v8.0
    legalMiddleName:getv("bio_legalMiddleName")||"",            // v8.0
    legalLastName:getv("bio_legalLastName")||"",                // v8.0
    timeOfBirth:getv("bio_timeOfBirth")||"",                    // v8.0
    timeOfBirthDisplay:getv("bio_timeOfBirthDisplay")||"",      // v8.0
    birthOrder:getv("bio_birthOrder")||"",                      // v8.0
    birthOrderCustom:getv("bio_birthOrderCustom")||"",          // v8.0
    zodiacSign:getv("bio_zodiacSign")||"",                      // v8.0
    placeOfBirthRaw:getv("bio_placeOfBirthRaw")||"",            // v8.0
    placeOfBirthNormalized:getv("bio_placeOfBirthNormalized")||"" // v8.0
  };
}
function onPronounsChange(){
  const v=document.getElementById("bio_pronouns")?.value;
  const wrap=document.getElementById("bio_pronouns_custom_wrap");
  if(wrap) wrap.classList.toggle("hidden",v!=="custom");
}
function scrapeProfileForm(){
  state.profile.basics=scrapeBasics();
  const kin=[]; document.querySelectorAll("#tblKinship .kinrow").forEach(row=>{
    const name=row.querySelector('[data-k="name"]').value.trim();
    const relation=row.querySelector('[data-k="relation"]').value;
    const pob=row.querySelector('[data-k="pob"]').value.trim();
    const occ=row.querySelector('[data-k="occ"]').value.trim();
    const deceased=row.querySelector('[data-k="deceased"]').checked;
    if(name) kin.push({name,relation,pob,occupation:occ,deceased});
  }); state.profile.kinship=kin;
  const pets=[]; document.querySelectorAll("#tblPets .petrow").forEach(row=>{
    const name=row.querySelector('[data-p="name"]').value.trim();
    if(name) pets.push({
      name,species:row.querySelector('[data-p="species"]').value.trim(),
      from:row.querySelector('[data-p="from"]').value.trim(),
      to:row.querySelector('[data-p="to"]').value.trim(),
      notes:row.querySelector('[data-p="notes"]').value.trim(),
      memory:row.querySelector('[data-p="memory"]')?.value.trim()||"",
    });
  }); state.profile.pets=pets;
}

/* ── DOB / Generation ── */
function onDobChange(){
  const dob=getv("bio_dob")||state.profile?.basics?.dob||"";
  const gb=document.getElementById("genBadge");
  const ad=document.getElementById("ageDisplay");
  if(!dob){ if(gb) gb.classList.add("hidden"); if(ad) ad.classList.add("hidden"); return; }
  const y=parseInt(dob.split("-")[0]); if(isNaN(y)) return;
  const age=new Date().getFullYear()-y;
  const gen=detectGeneration(y);
  if(gen && gb){ gb.textContent=gen.name; gb.classList.remove("hidden"); }
  if(ad){ ad.textContent=`~${age} years old`; ad.classList.remove("hidden"); }
  renderEventsGrid(); updateContextTriggers(); updateSidebar();
  updateArchiveReadiness();
}
function onCountryChange(){
  if(state.profile?.basics) state.profile.basics.country=document.getElementById("bio_country").value;
  renderEventsGrid();
}
function detectGeneration(y){
  if(y>=1928&&y<=1945) return{name:"Silent Generation"};
  if(y>=1946&&y<=1964) return{name:"Baby Boomer"};
  if(y>=1965&&y<=1980) return{name:"Generation X"};
  if(y>=1981&&y<=1996) return{name:"Millennial"};
  if(y>=1997&&y<=2012) return{name:"Generation Z"};
  return null;
}
function getBirthYear(){
  const dob=getv("bio_dob")||state.profile?.basics?.dob||"";
  return dob?parseInt(dob.split("-")[0]):null;
}
function getCountry(){
  return document.getElementById("bio_country")?.value||state.profile?.basics?.country||"us";
}

/* ── Sidebar summary ── */
function updateSidebar(){
  const name=state.profile?.basics?.preferred||state.profile?.basics?.fullname;
  if(!name){ document.getElementById("activeSummary").classList.add("hidden"); return; }
  document.getElementById("activeSummary").classList.remove("hidden");
  document.getElementById("summaryName").textContent=name;
  const dob=state.profile?.basics?.dob;
  const gen=dob?detectGeneration(parseInt(dob.split("-")[0])):null;
  document.getElementById("summaryGen").textContent=gen?gen.name:"";
  const done=sectionDone.filter(Boolean).length;
  document.getElementById("summaryProg").textContent=`${done}/${INTERVIEW_ROADMAP.length} sections`;
}

/* ── Demo fill ── */
function demoFill(){
  setv("bio_fullname","Christopher Todd Horne"); setv("bio_preferred","Chris");
  setv("bio_dob","1962-12-24"); setv("bio_pob","Williston, North Dakota");
  setv("bio_culture","American / Northern European");
  document.getElementById("bio_country").value="us";
  onDobChange();
  if(!document.querySelectorAll("#tblKinship .kinrow").length) addKin("Mother");
}

/* ═══════════════════════════════════════════════════════════════
   KINSHIP & PETS
═══════════════════════════════════════════════════════════════ */
function addKin(kind){ addKinRow(kind,{}); }
function addKinRow(kind,data){
  const t=document.getElementById("tblKinship");
  const d=document.createElement("div"); d.className="kinrow flex-row";
  d.innerHTML=`
    <input class="input-ghost" style="min-width:110px;flex:1" data-k="name" placeholder="Name" value="${escAttr(data.name||"")}">
    <select class="input-ghost" style="min-width:100px" data-k="relation">
      ${["Mother","Father","Stepmother","Stepfather","Sister","Brother","Half-sister","Half-brother","Stepsister","Stepbrother","Adoptive sister","Adoptive brother","Sibling","Spouse","Partner","Child","Step-parent","Step-child","Adoptive parent","Adoptive mother","Adoptive father","Adopted child","Grandparent","Grandmother","Grandfather","Grandparent-guardian","Grandchild","Nephew","Niece","Cousin","Aunt","Uncle","Former spouse","Guardian","Chosen family","Other"]
        .map(x=>`<option ${(data.relation||kind)===x?"selected":""}>${x}</option>`).join("")}
    </select>
    <input class="input-ghost" style="flex:1;min-width:90px" data-k="pob" placeholder="Birthplace" value="${escAttr(data.pob||"")}">
    <input class="input-ghost" style="flex:1;min-width:90px" data-k="occ" placeholder="Occupation" value="${escAttr(data.occupation||"")}">
    <label class="text-xs text-slate-400 flex items-center gap-1 whitespace-nowrap flex-shrink-0 font-semibold">
      <input type="checkbox" data-k="deceased" ${data.deceased?"checked":""}>
      <span style="color:${data.deceased?"#f87171":"inherit"}">Deceased</span>
    </label>
    <button class="text-red-400 hover:text-red-300 text-sm flex-shrink-0" onclick="this.closest('.kinrow').remove();updateArchiveReadiness()">✕</button>`;
  t.appendChild(d);
  updateArchiveReadiness();
}
function addPet(){ addPetRow({}); }
function addPetRow(data){
  const t=document.getElementById("tblPets");
  const ph=t.querySelector('.italic'); if(ph) ph.remove();
  const d=document.createElement("div"); d.className="petrow flex-row";
  d.innerHTML=`<span class="text-lg flex-shrink-0">🐾</span>
    <input class="input-ghost" style="min-width:100px;flex:1" data-p="name"    placeholder="Pet name"    value="${escAttr(data.name||"")}">
    <input class="input-ghost" style="min-width:110px;flex:1" data-p="species" placeholder="Species/breed" value="${escAttr(data.species||"")}">
    <input class="input-ghost" style="width:70px"             data-p="from"   placeholder="Year got"    value="${escAttr(data.from||"")}">
    <input class="input-ghost" style="width:70px"             data-p="to"     placeholder="Year lost"   value="${escAttr(data.to||"")}">
    <div style="flex:2;min-width:130px"><div class="text-xs text-slate-600 mb-0.5">Best remembered for</div><input class="input-ghost" style="width:100%" data-p="notes" placeholder="A story, habit, or detail that captures who they were." value="${escAttr(data.notes||"")}"></div>
    <div style="flex:2;min-width:130px"><div class="text-xs text-slate-600 mb-0.5">Favorite memory</div><input class="input-ghost" style="width:100%" data-p="memory" placeholder="A moment, place, or routine you shared." value="${escAttr(data.memory||"")}"></div>
    <button class="text-red-400 hover:text-red-300 text-sm flex-shrink-0" onclick="this.closest('.petrow').remove();updateArchiveReadiness()">✕</button>`;
  t.appendChild(d);
  updateArchiveReadiness();
}

/* ═══════════════════════════════════════════════════════════════
   WORLD EVENTS — Memory Triggers
═══════════════════════════════════════════════════════════════ */
function setEvtFilter(f,el){
  activeFilter=f;
  document.querySelectorAll(".filter-chip").forEach(c=>c.classList.toggle("active",c.dataset.f===f));
  renderEventsGrid();
}
function fireCustomPrompt(){
  const txt=(getv("evtCustomPrompt")||"").trim(); if(!txt) return;
  setv("chatInput",`Tell me about: ${txt}. Does this bring up any memories or feelings?`);
  document.getElementById("chatInput").focus();
  showTab("interview");
  sysBubble(`💡 Custom prompt loaded — press Send to ask Lori.`);
}
function renderEventsGrid(){
  const birthYear=getBirthYear();
  const country=getCountry();
  const secondary=document.getElementById("evtSecondaryCountry")?.value||"";
  const container=document.getElementById("eventsGrid"); if(!container) return;
  const strip=document.getElementById("evtContextStrip");

  const countryMatch=(e)=>{
    if(country==="global") return e.tags.includes("global");
    const primaryMatch=e.tags.includes(country)||e.tags.includes("global");
    if(!secondary) return primaryMatch;
    const secMatch=secondary==="global"?e.tags.includes("global"):e.tags.includes(secondary)||e.tags.includes("global");
    return primaryMatch||secMatch;
  };

  const events=ALL_EVENTS.filter(e=>{
    if(!countryMatch(e)) return false;
    if(activeFilter!=="all"&&!e.tags.includes(activeFilter)) return false;
    if(birthYear){ const age=e.year-birthYear; return age>=5&&age<=100; }
    return true;
  });

  const sparseNote=document.getElementById("evtSparseNote");
  if(sparseNote && birthYear){
    const age=new Date().getFullYear()-birthYear;
    if(age<30 && events.length<12){
      sparseNote.textContent=`Fewer triggers appear for younger ages — this list reflects memories from childhood through today. As more life events unfold, this list will grow.`;
      sparseNote.classList.remove("hidden");
    } else { sparseNote.classList.add("hidden"); }
  }

  if(strip){
    const countryLabels={us:"United States",uk:"United Kingdom",canada:"Canada",
      mexico:"Mexico",australia:"Australia",global:"Global"};
    const cLabel=countryLabels[country]||country;
    const filterLabel=activeFilter==="all"?"All events":activeFilter;
    if(birthYear||state.person_id){
      strip.classList.remove("hidden");
      const name=state.profile?.basics?.preferred||state.profile?.basics?.fullname;
      const gen=birthYear?detectGeneration(birthYear):null;
      strip.innerHTML=`
        ${name?`<span class="context-strip-item">For <span>${esc(name)}</span></span>`:``}
        ${birthYear?`<span class="context-strip-item">Born <span>${birthYear}</span></span>`:`<span class="context-strip-item text-slate-600">No DOB set</span>`}
        ${gen?`<span class="context-strip-item"><span>${esc(gen.name)}</span></span>`:""}
        ${birthYear?`<span class="context-strip-item">Ages <span>5–${Math.min(100,new Date().getFullYear()-birthYear)}</span></span>`:""}
        <span class="context-strip-item">Country <span>${esc(cLabel)}</span></span>
        ${secondary?`<span class="context-strip-item">+ Lens <span>${esc(secondary)}</span></span>`:""}
        <span class="context-strip-item">Filter <span>${esc(filterLabel)}</span></span>
        <span class="context-strip-item"><span>${events.length}</span> events shown</span>`;
    } else {
      strip.classList.add("hidden");
    }
  }

  const hint=document.getElementById("evtAgeHint");
  if(hint){
    if(birthYear){
      const maxAge=Math.min(100,new Date().getFullYear()-birthYear);
      hint.textContent=`Showing events from ages 5–${maxAge} (${birthYear} to present)`;
    } else {
      hint.textContent="Add a date of birth on the Profile tab to filter events to this person's lifetime.";
    }
  }

  if(!events.length){
    container.innerHTML=`<div class="text-sm text-slate-500 text-center py-6">No events match this filter. Try "All" or change the country on the Profile tab.</div>`;
    return;
  }
  container.innerHTML="";
  events.forEach(e=>{
    const age=birthYear?e.year-birthYear:null;
    const div=document.createElement("div"); div.className="event-card";
    div.onclick=()=>fireEventPrompt(e,age);
    div.innerHTML=`
      <div class="event-year">${e.year}</div>
      <div class="event-text">${esc(e.event)}
        <div class="mt-1">${e.tags.map(t=>`<span class="event-tag">${t}</span>`).join("")}</div>
        <div class="event-hint">Ask Lori about this moment</div>
      </div>
      ${age!==null?`<div class="event-age-badge">Age ${age}</div>`:""}`;
    container.appendChild(div);
  });
}
function fireEventPrompt(evt,age){
  const ageStr=age!==null?`when you were about ${age} years old`:"";
  let q;
  if(evt.tags.includes("war"))             q=`In ${evt.year}, ${evt.event}. You were ${ageStr}. Did this affect your family or people around you?`;
  else if(evt.tags.includes("technology")) q=`In ${evt.year}, ${evt.event}. You were ${ageStr}. Do you remember when this first came into your life?`;
  else if(evt.tags.includes("music")||evt.tags.includes("culture")) q=`In ${evt.year} — ${evt.event}. You were ${ageStr}. Do you have any memories from that time?`;
  else if(evt.tags.includes("cars"))       q=`In ${evt.year}, ${evt.event}. You were ${ageStr}. How did cars and transportation fit into your life around then?`;
  else q=`In ${evt.year} — ${evt.event}. You were ${ageStr}. Do you remember hearing about this or experiencing its effects?`;
  setv("chatInput",q);
  document.getElementById("chatInput").focus();
  showTab("interview");
}

/* ═══════════════════════════════════════════════════════════════
   MEMOIR DRAFT
═══════════════════════════════════════════════════════════════ */
function renderMemoirChapters(){
  const w=document.getElementById("memoirChapterList"); if(!w) return;
  const framing=document.getElementById("memoirFraming")?.value||"chronological";
  let showSections;
  if(framing==="early-life"){
    showSections=INTERVIEW_ROADMAP.map((s,i)=>({s,i})).filter(({s})=>MEMOIR_EARLY_LIFE.includes(s.id));
  } else if(framing==="family-legacy"){
    showSections=INTERVIEW_ROADMAP.map((s,i)=>({s,i})).filter(({s})=>MEMOIR_FAMILY_LEGACY.includes(s.id)||["origins","marriage","children","faith","legacy"].includes(s.id));
  } else if(framing==="thematic"){
    const order=MEMOIR_THEMATIC_ORDER;
    showSections=INTERVIEW_ROADMAP.map((s,i)=>({s,i})).filter(({s})=>!s.youth||youthMode)
      .sort((a,b)=>{ const ai=order.indexOf(a.s.id); const bi=order.indexOf(b.s.id); return (ai<0?999:ai)-(bi<0?999:bi); });
  } else {
    showSections=INTERVIEW_ROADMAP.map((s,i)=>({s,i})).filter(({s})=>!s.youth||youthMode);
  }
  const doneCount=sectionDone.filter(Boolean).length;
  const pct=Math.round(doneCount/INTERVIEW_ROADMAP.length*100);
  const cov=document.getElementById("memoirCoverage");
  const fill=document.getElementById("memoirProgressFill");
  if(cov) cov.textContent=`Interview coverage: ${doneCount} of ${INTERVIEW_ROADMAP.length} sections complete`;
  if(fill) fill.style.width=pct+"%";
  w.innerHTML=showSections.map(({s,i},n)=>{
    let cls,lbl;
    if(sectionDone[i]){cls="ready";lbl="Ready for draft";}
    else if(sectionVisited[i]){cls="in-progress";lbl="In progress";}
    else{cls="empty";lbl="Not started";}
    const thinNote=!sectionDone[i]?`<div class="text-xs text-slate-700 mt-0.5" style="font-size:9px">Limited source material — complete this section for a fuller draft.</div>`:"";
    return `<div class="chapter-row" onclick="jumpToSection(${i})" title="Go to this interview section">
      <span class="chapter-num">${n+1}</span>
      <div class="flex-1"><span class="chapter-label">${s.emoji} ${s.label}</span>${thinNote}</div>
      <span class="chapter-status ${cls}">${lbl}</span>
    </div>`;
  }).join("");
}
function jumpToSection(i){ sectionIndex=i; sectionVisited[i]=true; renderRoadmap(); updateContextTriggers(); showTab("interview"); }
function generateMemoirOutline(){
  const name=state.profile?.basics?.fullname||"the subject";
  const dob=state.profile?.basics?.dob||"";
  const visibleRoadmap=INTERVIEW_ROADMAP.filter(s=>!s.youth||youthMode);
  const done=visibleRoadmap.filter(s=>sectionDone[INTERVIEW_ROADMAP.indexOf(s)]).map(s=>s.label);
  let txt=`MEMOIR OUTLINE\n${name}${dob?" · Born "+dob:""}\n\n`;
  visibleRoadmap.forEach((s,n)=>{ const i=INTERVIEW_ROADMAP.indexOf(s); txt+=`  ${n+1}. ${s.label} ${sectionDone[i]?"✓":""}\n`; });
  txt+=`\nCompleted: ${done.length}/${visibleRoadmap.length}`;
  document.getElementById("memoirDraftOutput").value=txt;
}
function generateMemoirDraft(){
  const name=state.profile?.basics?.preferred||state.profile?.basics?.fullname||"this person";
  const done=INTERVIEW_ROADMAP.filter((_,i)=>sectionDone[i]).map(s=>s.label);
  if(!done.length){ sysBubble("Complete at least one interview section first."); return; }
  const framing=document.getElementById("memoirFraming")?.value||"chronological";
  const framingInstructions={
    "chronological":"Write flowing narrative prose, chapter by chapter in chronological order, in the style of a thoughtful family memoir.",
    "thematic":"Organize the memoir by theme rather than chronology — group memories around identity, family, work, and legacy. Each chapter explores a theme across different life periods.",
    "early-life":"Write this as an early-life journal — warm, personal, and focused on childhood through young adulthood. Use a voice that feels like a personal diary or coming-of-age story.",
    "family-legacy":"Write this as a family legacy narrative — address it to future generations. Focus on values, family patterns, heritage, and what this person would want their descendants to know.",
  };
  const style=framingInstructions[framing]||framingInstructions["chronological"];
  const pronouns=state.profile?.basics?.pronouns||"";
  const pronNote=pronouns?` Use ${pronouns} pronouns.`:"";
  // WO-KAWA-02A: append Kawa river context to memoir prompt when mode warrants it
  let kawaContext = "";
  const _memoirMode = typeof getMemoirMode === "function" ? getMemoirMode() : "chronology";
  if (_memoirMode !== "chronology") {
    const _confirmedSegs = (state?.kawa?.segmentList || []).filter(s => s?.provenance?.confirmed);
    if (_confirmedSegs.length) {
      const _overlays = _confirmedSegs.map(seg =>
        typeof buildKawaOverlayText === "function" ? buildKawaOverlayText(seg) : ""
      ).filter(Boolean);
      if (_overlays.length) {
        if (_memoirMode === "river_organized") {
          kawaContext = ` The narrator has also confirmed river reflections for ${_confirmedSegs.length} life periods. Organize the memoir around these river themes (flow, rocks, driftwood, banks, spaces) rather than strict chronology. River context: ${_overlays.join(" | ")}`;
        } else {
          kawaContext = ` The narrator has also confirmed river reflections for ${_confirmedSegs.length} life periods. Weave these naturally into the chronological narrative where they apply. River context: ${_overlays.join(" | ")}`;
        }
      }
    }
  }
  const prompt=`Please write a memoir draft for ${name}.${pronNote} Completed interview sections: ${done.join(", ")}. ${style}${kawaContext} Ground every detail in the collected interview answers. Do not invent facts.`;
  setv("chatInput",prompt); document.getElementById("chatInput").focus();
  sysBubble("Memoir prompt loaded — press Send to have Lori write the draft.");
}
function copyMemoirDraft(){ nav_copy(document.getElementById("memoirDraftOutput").value); sysBubble("↳ Draft copied."); }
function clearMemoirDraft(){ document.getElementById("memoirDraftOutput").value=""; }

/* ═══════════════════════════════════════════════════════════════
   OBITUARY DRAFT
═══════════════════════════════════════════════════════════════ */
function buildObituary(){
  const draft=document.getElementById("obituaryOutput")?.value||"";
  if(obitHasEdits && draft.trim()){
    obitModalAction="profile";
    document.getElementById("obitLockModal").classList.remove("hidden");
    return;
  }
  _buildObituaryImpl();
}
function generateObitChat(){
  const draft=document.getElementById("obituaryOutput")?.value||"";
  if(obitHasEdits && draft.trim()){
    obitModalAction="lori";
    document.getElementById("obitLockModal").classList.remove("hidden");
    return;
  }
  _generateObitChatImpl();
}
function closeObitModal(){
  document.getElementById("obitLockModal").classList.add("hidden");
  obitModalAction=null;
}
function confirmObitModal(){
  const action=obitModalAction;
  closeObitModal();
  obitHasEdits=false;
  if(action==="profile") _buildObituaryImpl();
  else                   _generateObitChatImpl();
}
function _buildObituaryImpl(){
  const b=state.profile?.basics||{};
  const kin=state.profile?.kinship||[];
  if(b.fullname) setv("obit_name",b.fullname);
  if(b.dob)      setv("obit_dob",b.dob);
  if(b.pob)      setv("obit_pob",b.pob);
  if(b.dob){ const y=parseInt(b.dob.split("-")[0]);
    if(!isNaN(y)) setv("obit_age",`${new Date().getFullYear()-y} (living)`); }
  const dod=getv("obit_dod");
  const isLiving=!dod;
  const banner=document.getElementById("obitLivingBanner");
  if(banner) banner.classList.toggle("hidden",!isLiving);
  const heading=document.getElementById("obitHeading");
  if(heading) heading.textContent=isLiving?"Life Summary / Archive":"Obituary Draft";
  const living=(arr,rel)=>kin.filter(k=>k.relation===rel&&!k.deceased).map(k=>k.name);
  const spouse=living(kin,"Spouse").concat(living(kin,"Partner"));
  const children=living(kin,"Child").concat(living(kin,"Step-child")).concat(living(kin,"Adopted child"));
  const siblings=living(kin,"Sibling");
  let surv="";
  if(spouse.length)   surv+=spouse.join(" and ");
  if(children.length) surv+=(surv?"; their children ":"children ")+children.join(", ");
  if(siblings.length) surv+=(surv?"; and siblings ":"siblings ")+siblings.join(", ");
  if(surv) setv("obit_survivors",`${b.preferred||b.fullname||"The deceased"} is survived by ${surv}.`);
  updateObitIdentityCard(b);
  setObitDraftType("auto");
  generateObituaryText();
}
function previewFamilyMapSurvivors(){
  const kin=state.profile?.kinship||[];
  const prev=document.getElementById("obitFamilyPreview");
  if(!prev) return;
  const lines=kin.map(k=>{
    const dec=k.deceased?"(deceased)":"(living)";
    return `${k.name||"—"} · ${k.relation} ${dec}`;
  });
  if(!lines.length){ prev.textContent="No family members added to the Family Map yet."; }
  else { prev.textContent="Family Map: "+lines.join(" · "); }
  prev.classList.remove("hidden");
}
function updateObitIdentityCard(b){
  const el=document.getElementById("obitIdentityItems"); if(!el) return;
  const checks=[
    {label:"Name set",      ok:!!(b.fullname||b.preferred)},
    {label:"Pronouns set",  ok:!!b.pronouns},
    {label:"Date of birth", ok:!!b.dob},
    {label:"Family map",    ok:(state.profile?.kinship||[]).length>0},
    {label:"Culture/roots", ok:!!b.culture},
  ];
  el.innerHTML=`<div class="flex flex-wrap gap-3">`+checks.map(c=>
    `<div class="identity-card-item">
       <div class="identity-card-dot ${c.ok?"ok":"miss"}"></div>
       <span style="color:${c.ok?"#94a3b8":"#475569"}">${c.label}</span>
     </div>`).join("")+`</div>`;
}
function generateObituaryText(){
  const name=getv("obit_name")||"[Name]";
  const age=getv("obit_age"); const dob=getv("obit_dob");
  const dod=getv("obit_dod"); const pob=getv("obit_pob");
  const pod=getv("obit_pod"); const career=getv("obit_career");
  const surv=getv("obit_survivors");
  const tone=document.getElementById("obitTone")?.value||"traditional";
  const fmt=(d)=>{ try{ return new Date(d).toLocaleDateString("en-US",{year:"numeric",month:"long",day:"numeric"}); }catch{return d;} };
  let txt="";
  if(tone==="concise"){
    txt=name; if(age) txt+=`, age ${age.replace(" (living)","")}`;
    txt+=dod?` — died ${fmt(dod)}.\n`:" — Life Story Archive.\n";
    if(pob||dob) txt+=`Born${dob?" "+fmt(dob):""}${pob?" in "+pob:""}.\n`;
    if(career) txt+=`${career}\n`;
    if(surv) txt+=`${surv}`;
  } else if(tone==="warm"){
    txt=`${name} lived a life full of love and purpose`;
    if(age) txt+=`, and at ${age.replace(" (living)","")} years`;
    txt+=dod?`, passed from this world on ${fmt(dod)}.\n\n`:`, continues to share their story.\n\n`;
    if(pob||dob) txt+=`Born${dob?" "+fmt(dob):""}${pob?" in the heart of "+pob:""}, their journey began with the family and community that would shape everything to come.\n\n`;
    if(career) txt+=`${career}\n\n`;
    if(surv) txt+=`${surv}\n\n`;
    txt+=`Their memory is a gift to all who knew them.`;
  } else if(tone==="family"){
    const first=name.split(" ")[0];
    txt=`${first} was one of a kind.`;
    if(pob||dob) txt+=` Born${dob?" "+fmt(dob):""}${pob?" in "+pob:""}, ${first} grew up to become someone their family will always be proud of.\n\n`;
    else txt+="\n\n";
    if(career) txt+=`${career}\n\n`;
    if(surv) txt+=`${surv}\n\n`;
    txt+=`We'll keep telling the stories.`;
  } else {
    txt=name; if(age) txt+=`, ${age},`;
    if(pod) txt+=dod?` of ${pod},`:` of ${pod}`;
    txt+=dod?` passed away ${fmt(dod)}.`:" — Life Story Archive."; txt+="\n\n";
    if(pob||dob) txt+=`Born${dob?" "+fmt(dob):""}${pob?" in "+pob:""}, ${name.split(" ")[0]} lived a life of purpose and meaning.\n\n`;
    if(career) txt+=`${career}\n\n`;
    if(surv) txt+=`${surv}\n\n`;
    txt+=`A celebration of life will be announced by the family.`;
  }
  document.getElementById("obituaryOutput").value=txt;
}
function _generateObitChatImpl(){
  const b=state.profile?.basics||{};
  const name=b.fullname||"this person";
  const tone=document.getElementById("obitTone")?.value||"traditional";
  const dod=getv("obit_dod");
  const isLiving=!dod;
  const pronounNote=b.pronouns?` Use ${b.pronouns} pronouns.`:"";
  const livingNote=isLiving?" This person is living — write a Life Summary rather than an obituary. Avoid death-framing.":"";
  const faith=getv("obit_faith"); const service=getv("obit_service");
  const vigil=getv("obit_vigil"); const memorial=getv("obit_memorial");
  const bilingual=getv("obit_bilingual");
  const culturalParts=[faith&&`Faith: ${faith}`,service&&`Service: ${service}`,
    vigil&&`Vigil/rosary: ${vigil}`,memorial&&`Memorial: ${memorial}`,bilingual&&`Bilingual note: ${bilingual}`].filter(Boolean);
  const culturalNote=culturalParts.length?` Cultural/memorial details: ${culturalParts.join("; ")}.`:"";
  const prompt=`Please write a ${tone} ${isLiving?"life summary":"obituary"} for ${name}.${pronounNote}${livingNote}${culturalNote} Use the profile data, family map, career history, and interview highlights. Write in a ${tone} style — include birth, career, family, and a closing tribute.`;
  setv("chatInput",prompt); document.getElementById("chatInput").focus();
  sysBubble("Obituary prompt loaded — press Send to have Lori write it.");
  obitDraftType="lori_pending";
}
function setObitDraftType(t){
  obitDraftType=t;
  const el=document.getElementById("obitDraftIndicator"); if(!el) return;
  if(!t){ el.classList.add("hidden"); return; }
  el.classList.remove("hidden");
  if(t==="lori")        { el.className="draft-indicator lori";   el.textContent="✨ Written with Lori"; }
  else if(t==="edited") { el.className="draft-indicator edited";  el.textContent="✎ Edited by hand"; }
  else                  { el.className="draft-indicator auto";    el.textContent="Filled from Profile"; }
}
function resetObitFromFacts(){ obitHasEdits=false; _buildObituaryImpl(); }
function copyObituary(){ nav_copy(document.getElementById("obituaryOutput").value); sysBubble("↳ Obituary copied."); }

/* ═══════════════════════════════════════════════════════════════
   SESSION INIT
═══════════════════════════════════════════════════════════════ */
async function initSession(){
  try{
    const r=await fetch(API.SESS_NEW,{method:"POST",headers:ctype(),
      body:JSON.stringify({title:"Hornelore 1.0"})});
    const j=await r.json();
    state.chat.conv_id=j.conv_id||j.session_id||null;
    document.getElementById("chatSessionLabel").textContent=state.chat.conv_id||"Local session";
  }catch{ state.chat.conv_id=null; document.getElementById("chatSessionLabel").textContent="Offline mode"; }
}
async function refreshSessions(){
  try{
    const r=await fetch(API.SESS_LIST+"?limit=12"); if(!r.ok) return;
    const j=await r.json();
    const sl=document.getElementById("sessionsList"); if(!sl) return; sl.innerHTML="";
    (j.items||j.sessions||[]).slice(0,8).forEach(s=>{
      const d=document.createElement("div"); d.className="sb-item";
      d.onclick=()=>loadSession(s.conv_id||s.id);
      d.innerHTML=`<div class="text-xs text-slate-300 truncate">${esc(s.title||s.conv_id||"Session")}</div>`;
      sl.appendChild(d);
    });
  }catch{}
}
async function loadSession(cid){
  try{
    const r=await fetch(API.SESS_TURNS(cid)); const j=await r.json();
    document.getElementById("chatMessages").innerHTML="";
    (j.items||j.turns||[]).forEach(m=>appendBubble(m.role==="assistant"?"ai":m.role==="user"?"user":"sys",m.content||""));
    state.chat.conv_id=cid;
    document.getElementById("chatSessionLabel").textContent=cid;
  }catch{ sysBubble("Could not load session."); }
}

/* ═══════════════════════════════════════════════════════════════
   PHASE 6B — IDENTITY GATING HELPERS
   These three functions let buildRuntime71() emit an effective_pass
   that the backend can use to gate Pass 1 directives until identity
   is fully established.  This stops the "empathy → abrupt DOB ask"
   pattern seen in Tests 7 & 8.
═══════════════════════════════════════════════════════════════ */

/** True once name + DOB + birthplace are all non-empty in profile basics. */
function hasIdentityBasics74() {
  if (typeof state === "undefined") return false;
  const b = state.profile?.basics || {};
  const name = (b.preferred || b.fullname || b.name || "").trim();
  const dob  = (b.dob || "").trim();
  const pob  = (b.pob || b.birthplace || "").trim();
  return !!(name && dob && pob);
}

/**
 * Returns the onboarding sub-phase string, or:
 *   "complete"   — identity fully established
 *   "incomplete" — identity not yet established (no active sub-phase)
 */
function getIdentityPhase74() {
  if (typeof state === "undefined") return "unknown";
  const p = state.session?.identityPhase;
  if (p) return p;
  return hasIdentityBasics74() ? "complete" : "incomplete";
}

/**
 * Returns "identity" while identity is not complete, otherwise returns
 * the current interview pass (defaulting to "pass1").
 * Used by buildRuntime71() to emit the effective_pass field.
 */
function getEffectivePass74() {
  if (typeof state === "undefined") return "identity";
  const phase = getIdentityPhase74();
  if (phase && phase !== "complete") return "identity";
  if (!hasIdentityBasics74()) return "identity";
  return state.session?.currentPass || "pass1";
}

/* ═══════════════════════════════════════════════════════════════
   IDENTITY-FIRST ONBOARDING  (v7.4D — Phase 6)
   State machine: null → askName → askDob → askBirthplace
                  → resolving → complete
   Lori leads. No forms. The archive builds from what the user says.
═══════════════════════════════════════════════════════════════ */

/**
 * Kick off identity onboarding.
 * Sets Lori to 'onboarding' role and sends the first greeting via Lori's
 * voice so the user experiences it as a natural conversation, not a form.
 */
function startIdentityOnboarding(){
  // Step 3 diagnostic — confirms auto-start fired; visible in DevTools.
  console.log("[onboarding] startIdentityOnboarding() — new user path, phase=askName");
  state.session.identityPhase   = "askName";
  state.session.identityCapture = { name: null, dob: null, birthplace: null };
  // v7.4E — profile seed tracking: records which of the 10 seed questions have been answered.
  // Keys map to the 10 profile-seed questions in the Pass 1 directive.
  // null = not yet asked; true = answered (from any source — explicit or conversational).
  state.session.profileSeed = {
    childhood_home: null,
    siblings:       null,
    parents_work:   null,
    heritage:       null,
    education:      null,
    military:       null,
    career:         null,
    partner:        null,
    children:       null,
    life_stage:     null,
  };
  setAssistantRole("onboarding");
  // v7.4E — Tell Lori to briefly explain WHY she needs the three anchors before asking.
  // This sets expectations, builds trust, and gets more accurate answers.
  // #202: Drop the "Hornelore" etymology lecture — that was the codebase
  //       project name leaking into the user-facing chat.  User-facing
  //       product is Lorevox; Lori is the assistant.  Keep the intro
  //       simple and warm; if asked, Lori is part of Lorevox, no etymology.
  sendSystemPrompt(
    "[SYSTEM: Begin the identity onboarding sequence. " +
    "Introduce yourself simply as Lori. " +
    "Do NOT explain where your name comes from. Do NOT mention 'Hornelore' " +
    "or any name etymology.  If asked, you can say you're part of Lorevox " +
    "in one short clause, but do not lecture about it.  " +
    "Explain that your purpose is to help them build a Life Archive — a lasting record of their life story " +
    "told in their own voice. " +
    "Then explain you need just three things to get started: their name, their date of birth, and where they were born. " +
    "These three anchors let you build a personal life timeline so you can guide the conversation " +
    "in the right order and ask the most meaningful questions. " +
    "Tell them you will ask for each one separately — it will only take a moment. " +
    "Then ask for their preferred name. " +
    "Keep the whole message warm, brief, and conversational. Two to four sentences at most. " +
    "Do not lecture. Do not list. Make it feel like the beginning of a real conversation.]"
  );
}

/**
 * Extract a plausible date of birth from a free-text answer.
 * Accepts: "December 24 1962", "12/24/1962", "1962-12-24",
 *          "born in '62", "December 1962", "just 1962".
 * Returns an ISO date string "YYYY-MM-DD" or null.
 */
// BUG-EX-DOB-LEAP-YEAR-FALLBACK-01 (2026-05-06): Feb 29 1940 / 1944 etc.
// are real leap-year dates and must round-trip as YYYY-02-29 instead of
// silently degrading to YYYY-01-01. Live evidence: Mary's TEST-23 v3
// onboarding sent "2/29 1940" → was parsed as 1940-01-01 because (a) no
// regex matched the slash+space form, so cascade fell to year-only pattern;
// (b) even if a regex caught it, no leap-year validator existed. v8
// reproduced the same: Mary's projection_json.fields shows
// "personal.dateOfBirth": "1940-01-01". Mary herself sees "1940-01-01"
// in the memory_echo readback — narrator-visible regression.
//
// Fix: add slash+space variant ("2/29 1940"), validate leap-year for
// Feb 29, log warning on non-leap-year Feb 29 instead of silent fallback.
function _isLeapYear(y){
  return (y % 4 === 0 && y % 100 !== 0) || (y % 400 === 0);
}
function _validateAndFormatDate(year, month, day){
  // Validate calendar date including leap-year handling. Returns
  // "YYYY-MM-DD" on success, null on calendar-invalid.
  const y = parseInt(year, 10);
  const mo = parseInt(month, 10);
  const d = parseInt(day, 10);
  if(!y || !mo || !d) return null;
  if(mo < 1 || mo > 12) return null;
  if(d < 1 || d > 31) return null;
  // Days-in-month check
  const daysInMonth = [31, _isLeapYear(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if(d > daysInMonth[mo - 1]){
    console.warn("[parseDob] calendar-invalid date "+y+"-"+mo+"-"+d+" (e.g. Feb 29 on non-leap year); rejecting");
    return null;
  }
  return y+"-"+String(mo).padStart(2,"0")+"-"+String(d).padStart(2,"0");
}

function _parseDob(text){
  const t = text.trim();
  // Full ISO
  let m = t.match(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/);
  if(m){
    const validated = _validateAndFormatDate(m[1], m[2], m[3]);
    if(validated) return validated;
  }
  // US format with slashes: "2/29/1940"
  m = t.match(/\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b/);
  if(m){
    const validated = _validateAndFormatDate(m[3], m[1], m[2]);
    if(validated) return validated;
  }
  // BUG-EX-DOB-LEAP-YEAR-FALLBACK-01 — slash + SPACE form: "2/29 1940"
  // Mary's onboarding answer shape. Without this, cascade falls to
  // year-only pattern → 1940-01-01 silent degrade.
  m = t.match(/\b(\d{1,2})\/(\d{1,2})\s+(\d{4})\b/);
  if(m){
    const validated = _validateAndFormatDate(m[3], m[1], m[2]);
    if(validated) return validated;
  }
  // Month name forms: "December 24, 1962" / "24 December 1962"
  // BUG-210: accept ordinal suffixes (1st, 2nd, 3rd, 4th, ...) between
  // the day digit and the year separator.  Live evidence: Jake said
  // "December 31st 1937" → was parsed as 1937-01-01 because the original
  // regexes required digit then comma/whitespace, and "st" is letters.
  const MONTHS = {january:"01",february:"02",march:"03",april:"04",may:"05",
    june:"06",july:"07",august:"08",september:"09",october:"10",november:"11",december:"12"};
  const ORDINAL = "(?:st|nd|rd|th)?";   // optional ordinal suffix
  const lower = t.toLowerCase();
  for(const [name,num] of Object.entries(MONTHS)){
    // re1: "December 24th, 1962" / "december 24th 1962" / "december 24 1962"
    const re1 = new RegExp(name+"\\s+(\\d{1,2})"+ORDINAL+"[,\\s]+(\\d{4})");
    // re2: "24th of December, 1962" / "24th December 1962" / "the 24 December 1962"
    // BUG-210 extension: accept optional "of" between day and month.
    const re2 = new RegExp("(\\d{1,2})"+ORDINAL+"\\s+(?:of\\s+)?"+name+"[,\\s]+(\\d{4})");
    // re3: month-and-year only ("December 1962") — day unknown, returns -01
    const re3 = new RegExp(name+"[,\\s]+(\\d{4})");
    let mm;
    // BUG-EX-DOB-LEAP-YEAR-FALLBACK-01: route through _validateAndFormatDate
    // so calendar-invalid dates (Feb 29 on non-leap year, Apr 31, etc.)
    // get rejected instead of silently producing impossible YYYY-MM-DD.
    // Returns null on calendar-invalid; we then fall through to the
    // year-only / unparseable handlers.
    if((mm=lower.match(re1))){
      const v = _validateAndFormatDate(mm[2], num, mm[1]);
      if(v) return v;
    }
    if((mm=lower.match(re2))){
      const v = _validateAndFormatDate(mm[2], num, mm[1]);
      if(v) return v;
    }
    if((mm=lower.match(re3))) return `${mm[1]}-${num}-01`;  // partial date — day unknown
  }
  // Short year forms: "born in '62", "born 1962", just "1962"
  // Apostrophe-short form first: '62 → 1962, '38 → 1938 (years 00–29 = 2000s, 30–99 = 1900s)
  m = t.match(/'(\d{2})\b/);
  if(m){ const y=parseInt(m[1]); return `${y<30?2000+y:1900+y}-01-01`; }
  m = t.match(/\b(19\d{2}|20[0-2]\d)\b/);
  if(m) return `${m[1]}-01-01`;
  return null;
}

/**
 * BUG-226: Robust birthplace extractor for identity onboarding.
 * Handles all four real input shapes seen in live sessions:
 *   1. "I was born in Lima Peru December 20 1972"   (place before date, digits follow)
 *   2. "I was born December 20 1972 in Lima Peru"   (place after date)
 *   3. "I'm from Williston, North Dakota"           (no "born" trigger)
 *   4. "Lima Peru" / "Mason City Iowa"              (just the place)
 *
 * Replaces the prior /\bin\s+([A-Z][a-zA-Z\s,]+?)(?:\.|$)/i regex which
 * failed on shape 1 because it required period or end-of-string immediately
 * after the place — Melanie's input "born in Lima Peru December 20 1972"
 * has digits following Peru, so the prior regex never matched and the
 * state machine fell through to asking "where were you born?" on a fresh
 * turn even though Lima Peru was already in the same utterance.
 *
 * Returns a clean place name string (e.g. "Lima Peru", "Williston, North Dakota")
 * or null if no plausible place can be extracted.
 */
function _parseBirthplaceFromUtterance(text){
  if (!text || typeof text !== "string") return null;
  const t = text.trim();
  if (t.length < 2 || t.length > 500) return null;

  const MONTHS = "(?:january|february|march|april|may|june|july|august|september|october|november|december)";
  // Stop tokens — terminate the place capture at the first occurrence of any:
  //   - a digit (date)
  //   - a sentence-end punctuation mark
  //   - a month name (e.g. "Lima Peru December" → stop before December)
  //   - a conjunction or pronoun starting the next clause
  //   - "in" (already-consumed "born in"; second "in" is a date qualifier)
  const STOP_RE = new RegExp(
    "\\d|" +
    "[.!?;:]|" +
    "\\b(?:" + MONTHS + "|when|where|but|so|then|i|we|my|on|at|in|or|and)\\b",
    "i"
  );

  // Trigger phrases — strong signal that a place name follows.
  // Order matters: stronger triggers first.
  const TRIGGERS = [
    /\b(?:born|grew\s+up|raised|lived)\s+(?:in|at|near)\s+/i,
    /\bhail(?:s|ed)?\s+from\s+/i,
    /\bfrom\s+(?=[A-Z])/i,   // "from <Place>" — only if next word starts capital
  ];

  function _cleanPlace(raw){
    if (!raw) return null;
    let p = String(raw).trim();
    // Trim trailing comma/period/space
    p = p.replace(/[,.\s]+$/, "").trim();
    if (p.length < 2 || p.length > 60) return null;
    // Reject obvious non-places (articles, pronouns, common single-word replies)
    if (/^(?:a|an|the|when|where|how|that|hello|yes|no|maybe|sure|okay|i)\b/i.test(p)) return null;
    // Place must start with a letter (proper noun)
    if (!/^[A-Za-z]/.test(p)) return null;
    return p;
  }

  // Pass 1: try direct triggers
  for (const trig of TRIGGERS) {
    const m = t.match(trig);
    if (!m) continue;
    const start = m.index + m[0].length;
    const tail = t.slice(start);
    const stop = tail.match(STOP_RE);
    const raw = stop ? tail.slice(0, stop.index) : tail;
    const place = _cleanPlace(raw);
    if (place) return place;
  }

  // Pass 2: "born <date> in <Place>" — date came first, "in" second
  if (/\bborn\b/i.test(t)) {
    const inIdx = t.search(/\bin\s+[A-Z]/);
    if (inIdx >= 0) {
      const tail = t.slice(inIdx + 3);  // skip "in "
      const stop = tail.match(STOP_RE);
      const raw = stop ? tail.slice(0, stop.index) : tail;
      const place = _cleanPlace(raw);
      if (place) return place;
    }
  }

  // Pass 3 (last resort): the whole utterance IS the place name.
  // Place-only replies look like proper nouns: every word starts with a
  // capital (or punctuation like apostrophe/dash).
  //
  // 2026-05-04 BUG-PARSE-BIRTHPLACE-NAME-CONFUSION-01: tightened to
  // require either ≥3 capital-led tokens OR an explicit place separator
  // (comma — as in "Williston, North Dakota") or a recognized state/
  // country tail token. Previous rule accepted any 2-word capitalized
  // string and returned "William Shatner" as a place during askName,
  // which then poisoned identityCapture._embeddedPob and carried over
  // into placeOfBirth on the askBirthplace step. Live evidence:
  // rehearsal_quick_v9 + v10 BB place='William Shatner' for Shatner
  // cascade narrator. The harness's actual askBirthplace answer was
  // "Montreal, Quebec, Canada" which has both ≥3 tokens AND commas, so
  // the legitimate-place case is preserved.
  if (t.length <= 60 && /^[A-Z]/.test(t) && !STOP_RE.test(t)) {
    const tokens = t.split(/\s+/);
    const allCapitalLed = tokens.every(function (w) {
      return w.length === 0 || /^[A-Z]/.test(w) || /^[,'-]/.test(w);
    });
    if (allCapitalLed) {
      // Conservative: require either ≥3 capital-led tokens (e.g.
      // "Mason City Iowa", "Lima Peru Country", "New York City") OR
      // a comma-separated place form ("Williston, North Dakota",
      // "Montreal, Quebec, Canada", "Boston, MA") OR a known
      // place-tail token (state/country indicator).
      const _PLACE_TAIL = new Set([
        // US states (subset — full list lives in geo lookup)
        "Alabama","Alaska","Arizona","Arkansas","California","Colorado",
        "Connecticut","Delaware","Florida","Georgia","Hawaii","Idaho",
        "Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana","Maine",
        "Maryland","Massachusetts","Michigan","Minnesota","Mississippi",
        "Missouri","Montana","Nebraska","Nevada","Hampshire","Jersey",
        "Mexico","York","Carolina","Dakota","Ohio","Oklahoma","Oregon",
        "Pennsylvania","Rhode","Tennessee","Texas","Utah","Vermont",
        "Virginia","Washington","Wisconsin","Wyoming",
        // Major countries
        "Canada","Mexico","England","France","Germany","Italy","Spain",
        "Portugal","Ireland","Scotland","Wales","Norway","Sweden","Finland",
        "Denmark","Netherlands","Belgium","Switzerland","Austria","Poland",
        "Russia","Ukraine","China","Japan","Korea","India","Pakistan",
        "Brazil","Argentina","Chile","Peru","Colombia","Australia",
        "Zealand","Africa","Egypt","Greece", "Quebec","Ontario","Manitoba",
        "Alberta","Columbia","Saskatchewan",
      ]);
      const hasComma = /,/.test(t);
      const hasPlaceTail = tokens.some(function (w) {
        return _PLACE_TAIL.has(w.replace(/[,.]+$/, ""));
      });
      if (tokens.length >= 3 || hasComma || hasPlaceTail) {
        return _cleanPlace(t);
      }
      // 2-word capital pair WITHOUT comma or known tail token —
      // ambiguous (could be a person's name like "William Shatner"
      // or a place like "New Hampshire"). Reject to prevent name→place
      // confusion. Real 2-word places either have a known tail
      // ("New Hampshire" — "Hampshire" in tail set) or come from
      // an explicit "born in X" trigger (Pass 1).
      return null;
    }
  }

  return null;
}

/**
 * BUG-227: Shared name extractor — pulls a plausible first/preferred
 * name from intro patterns: "my name is X", "call me X", "I'm X",
 * "I am X", "I go by X", "preferred name is X".
 *
 * Returns null if no name pattern matches OR if the matched word is
 * a common pronoun/word/emotional content (handled by the same
 * _NOT_A_NAME guard the askName handler uses).
 *
 * Used by both the identity onboarding state machine (askName) and
 * the questionnaire_first walk (BUG-227) so a narrator's intro
 * captures cleanly regardless of which path is active.
 */
function _parseNameFromUtterance(text){
  if (!text || typeof text !== "string") return null;
  const t = text.trim();
  if (t.length < 2) return null;

  const _NOT_A_NAME = new Set([
    "that","it","i","the","a","an","this","there","here","yes","no","yeah","nope",
    "okay","ok","well","so","hi","hello","hey","oh","ah","uh","um","my","mine",
    "what","when","where","why","how","who","which","they","we","you","he","she",
    "just","not","but","and","or","if","then","was","were","is","am","are",
    "had","have","has","did","do","does","would","could","should","will","can",
  ]);
  const _EMOTIONAL_MARKERS = /\b(hard|difficult|sad|scared|lost|hurt|pain|grief|suffered|struggling|terrible|awful|horrible|tough|heartbroken|afraid|worried|anxious|miss|missed|died|death|trauma|abuse|alone|lonely|crying|tears|broke|broken)\b/i;
  if (_EMOTIONAL_MARKERS.test(t)) return null;

  // BUG-231: split trigger detection (case-insensitive, /i) from name
  // capture (case-sensitive). Earlier attempt used /i on the whole regex
  // and the [A-Z] anchor degraded to [A-Za-z], so "my name is Sarah and i"
  // captured "Sarah and" instead of stopping at the first lowercase word.
  // Live evidence 2026-04-25T22:48: "My name is Test Harness Sarah Reed"
  // captured only "Test" because the prior regex allowed at most "First Last".
  // Real names range 1-4 capital-led words (Christopher Todd Horne / Janice
  // Josephine Horne / Test Harness Sarah Reed). Capture 1-4 capital-led
  // words AFTER the trigger position; stop at any lowercase-led word.
  const _triggers = [
    /\bmy\s+(?:\w+\s+)*name\s+is\s+/i,
    /\bcall\s+me\s+/i,
    /\bi(?:'m|\s+am)\s+(?:called\s+)?/i,
    /\bi\s+go\s+by\s+/i,
    /\byou\s+can\s+call\s+me\s+/i,
    /\bprefer(?:red)?\s+(?:name\s+is\s+|to\s+be\s+called\s+)?/i,
  ];
  const _NAME_CAP = /^([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})/;  // case-SENSITIVE: stops at lowercase word
  for (const trig of _triggers) {
    const m = t.match(trig);
    if (!m) continue;
    const tail = t.slice(m.index + m[0].length);
    const nm = tail.match(_NAME_CAP);
    if (!nm || !nm[1]) continue;
    const cand = nm[1].trim();
    const firstWord = cand.split(/\s+/)[0];
    if (_NOT_A_NAME.has(firstWord.toLowerCase()) || firstWord.length < 2) continue;
    return cand;
  }

  // 2026-05-04 BUG-NAME-PARSE-BARE-PAIR-01: Pass 2 (last resort) — bare name.
  // Live evidence (rehearsal_quick_v11 + stress_v1): harness sent
  // "William Shatner" without a trigger phrase; Pass 1 returned null and
  // the upstream askName fallback captured first-word only ("William"),
  // losing "Shatner". Real narrators answer concisely too — "Janice Horne"
  // not "my name is Janice Horne". Capture 2-4 capital-led words IF:
  //   (a) total utterance is ≤5 tokens (short answer, not a sentence)
  //   (b) every token (up to 4) starts with a capital letter (proper noun)
  //   (c) first token isn't in the NOT_A_NAME guard
  //   (d) first token is ≥2 chars
  // Single-word names ("Christopher", "Janice") still fall through to the
  // upstream first-word fallback in _advanceIdentityPhase — this Pass 2
  // only catches multi-word capital-led utterances that Pass 1 missed.
  const _allTokens = t.split(/\s+/);
  if (_allTokens.length >= 2 && _allTokens.length <= 5) {
    const _capTokens = [];
    for (let i = 0; i < Math.min(_allTokens.length, 4); i++) {
      const w = _allTokens[i].replace(/[^A-Za-z'\-]/g, "");
      if (!w || !/^[A-Z]/.test(w)) break;
      _capTokens.push(w);
    }
    if (_capTokens.length >= 2) {
      const first = _capTokens[0];
      if (!_NOT_A_NAME.has(first.toLowerCase()) && first.length >= 2) {
        return _capTokens.join(" ");
      }
    }
  }

  return null;
}

/**
 * BUG-226: Bundle name + DOB + POB extraction so any identity-phase
 * handler can use a single call site. Each field is independent — a
 * partial extraction (e.g. just dob + pob) is still useful.
 */
function _extractIdentityFieldsFromUtterance(text){
  return {
    name: _parseNameFromUtterance(text),
    dob: _parseDob(text),
    pob: _parseBirthplaceFromUtterance(text),
  };
}

/**
 * Advance the identity state machine based on the user's reply.
 * Called at the TOP of sendUserMessage() before anything else.
 * Returns true when the machine is active and consumed the message.
 */
async function _advanceIdentityPhase(text){
  const phase = state.session?.identityPhase;
  if(!phase || phase === "complete") return false;
  if(phase === "resolving") return true; // waiting for API — swallow input

  if(phase === "askName"){
    // v7.4D BUG-FIX: Do not extract a name from an emotional or non-name response.
    // Common-word guard: single-word replies that are NOT valid names.
    const _NOT_A_NAME = new Set([
      "that","it","i","the","a","an","this","there","here","yes","no","yeah","nope",
      "okay","ok","well","so","hi","hello","hey","oh","ah","uh","um","my","mine",
      "what","when","where","why","how","who","which","they","we","you","he","she",
      "just","not","but","and","or","if","then","was","were","is","am","are",
      "had","have","has","did","do","does","would","could","should","will","can",
    ]);
    // Emotional-content guard: message looks like a statement, not a name
    const _EMOTIONAL_MARKERS = /\b(hard|difficult|sad|scared|lost|hurt|pain|grief|suffered|struggling|terrible|awful|horrible|tough|heartbroken|afraid|worried|anxious|miss|missed|died|death|trauma|abuse|alone|lonely|crying|tears|broke|broken|never|always|sometimes|really|very|so much)\b/i;

    // BUG-237: use the shared multi-word _parseNameFromUtterance helper
    // (BUG-231 fix, defined above) instead of an inline limited regex.
    // Live evidence 2026-04-26T00:30: "My name is Test Harness Sarah Reed"
    // captured only "Test" because the prior inline regex allowed at most
    // [A-Za-z][a-z'-]+ (a single word). The shared helper handles 1-4
    // capital-led words with case-sensitive boundary stops, and shares
    // the _NOT_A_NAME / _EMOTIONAL_MARKERS guards so behavior is
    // identical for normal names ("Walter", "Christopher", etc.) — just
    // also captures multi-word names like "Test Harness Sarah Reed",
    // "Janice Josephine Horne", "Christopher Todd Horne".
    let patternName = null;
    if (!_EMOTIONAL_MARKERS.test(text)) {
      try {
        if (typeof _parseNameFromUtterance === "function") {
          patternName = _parseNameFromUtterance(text);
        }
      } catch (e) {
        console.warn("[identity] _parseNameFromUtterance threw:", e);
      }
    }

    const words = text.trim().split(/\s+/);
    const isEmotional = _EMOTIONAL_MARKERS.test(text);
    const isLongSentence = words.length > 4;

    let name = null;
    if (patternName) {
      // Structured extraction succeeded — use it even for long sentences
      name = patternName;
    } else {
      // Fallback: first-word extraction (works for short direct answers like "Christopher")
      const candidate = words[0].replace(/[^a-zA-Z'\-]/g, "").trim();
      const isCommonWord = _NOT_A_NAME.has(candidate.toLowerCase());
      if (isEmotional || isLongSentence || isCommonWord || !candidate) {
        // Not a name answer — let it flow through to the LLM (IDENTITY MODE directive handles it)
        return false;
      }
      name = candidate;
    }
    state.session.identityCapture.name = name;
    state.session.speakerName = name;  // v7.4E — persist for runtime71 anchor

    // v8.0 FIX: Immediately project name into profile and projection state
    if(!state.profile) state.profile = {basics:{}, kinship:[], pets:[]};
    state.profile.basics.preferred = name;
    state.profile.basics.fullname  = name;
    if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
      LorevoxProjectionSync.projectValue("personal.fullName", name, {
        source: "interview", turnId: "identity-name", confidence: 0.95
      });
      LorevoxProjectionSync.projectValue("personal.preferredName", name, {
        source: "interview", turnId: "identity-name", confidence: 0.95
      });
    }
    // v8.0 FIX: Update narrator header card immediately
    if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();

    // BUG-226: Mirror name into Bio Builder questionnaire.personal so BB
    // shows what Lori already knows. Idempotent — only fills empty fields.
    try {
      if (typeof window.lvBbSyncIdentity === "function") {
        window.lvBbSyncIdentity(state.profile.basics);
      }
    } catch (e) { console.warn("[bb-sync] askName/name-only threw:", e); }

    // v9.0 FIX + BUG-226: Multi-field extraction from single answer.
    // Live evidence (2026-04-25): Melanie said "My name is Melanie Zollner
    // I was born in Lima Peru December 20 1972" and the prior code captured
    // only name + DOB, missing POB because the embedded-POB regex required
    // period/EOS after the place. Lori then re-asked birthplace — parent UX
    // failure. New parser + skip-ahead control flow below.
    const _embeddedDob = _parseDob(text);
    const _embeddedPob = _parseBirthplaceFromUtterance(text);
    if (_embeddedDob) {
      state.session.identityCapture.dob = _embeddedDob;
      if(!state.profile) state.profile = {basics:{}, kinship:[], pets:[]};
      state.profile.basics.dob = _embeddedDob;
      if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
        LorevoxProjectionSync.projectValue("personal.dateOfBirth", _embeddedDob, {
          source: "interview", turnId: "identity-dob", confidence: 0.9
        });
      }
      if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();

      // BUG-226: SKIP-AHEAD — if POB also captured in same utterance,
      // mark all three identity anchors complete in one shot and skip
      // askBirthplace entirely. Lori must NOT ask for what's already given.
      if (_embeddedPob) {
        state.session.identityCapture.birthplace = _embeddedPob;
        state.profile.basics.pob = _embeddedPob;
        if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
          LorevoxProjectionSync.projectValue("personal.placeOfBirth", _embeddedPob, {
            source: "interview", turnId: "identity-pob", confidence: 0.85
          });
        }
        if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();

        // Mirror to Bio Builder questionnaire.personal so BB shows what
        // Lori already knows instead of asking again later.
        try {
          if (typeof window.lvBbSyncIdentity === "function") {
            window.lvBbSyncIdentity(state.profile.basics);
          }
        } catch (e) { console.warn("[bb-sync] askName/skip-ahead threw:", e); }

        console.log("[identity] BUG-226: name + DOB + POB extracted from single message:", name, _embeddedDob, _embeddedPob);
        // Skip directly to person resolution — _resolveOrCreatePerson sets
        // identityPhase = "complete" and dispatches the session-loop.
        state.session.identityPhase = "resolving";
        sendSystemPrompt(
          `[SYSTEM: SPEAKER IDENTITY — The person is named "${name}", born ${_embeddedDob} in ${_embeddedPob}. ` +
          `You are Lori, the interviewer. Use "${name}" when addressing the speaker. ` +
          `These three anchors (name, date of birth, birthplace) were ALL captured from this one message. ` +
          `Do NOT ask for any of them again — that would be a confidence-killing mistake. ` +
          `Acknowledge them warmly in one or two sentences (use "${name}" once). ` +
          `Then ask one open question that invites them to share an early memory or what kind of place ${_embeddedPob} was when they were growing up. One question only.]`
        );
        await _resolveOrCreatePerson();
        return true;
      }

      // Only name + DOB captured — proceed to askBirthplace as before.
      state.session.identityPhase = "askBirthplace";
      console.log("[identity] Name + DOB extracted from single message:", name, _embeddedDob);
      sendSystemPrompt(
        `[SYSTEM: SPEAKER IDENTITY — The person is named "${name}", born ${_embeddedDob}. ` +
        `You are Lori, the interviewer. Use "${name}" when addressing the speaker. ` +
        `Acknowledge their name and date of birth warmly. ` +
        `Then ask where they were born — town, city, or region. One question only.]`
      );
      return true;
    }

    // BUG-226: name only (no DOB), but maybe POB was given anyway —
    // capture it for use when askBirthplace fires later. Keeps the
    // existing askDob → askBirthplace flow intact.
    if (_embeddedPob) {
      state.session.identityCapture._embeddedPob = _embeddedPob;
    }

    // No embedded DOB — ask for it separately
    state.session.identityPhase = "askDob";
    sendSystemPrompt(
      `[SYSTEM: SPEAKER IDENTITY — The person you are interviewing is named "${name}". ` +
      `You are Lori, the interviewer. These are two different people. ` +
      `If anyone named "Lori" appears in their story, that is a different person — not you. ` +
      `Use "${name}" when addressing or referring to the speaker. ` +
      `Now: acknowledge their name warmly (use it once). ` +
      `Then ask for their date of birth — explain it helps place their story in time. One question only.]`
    );
    return true;
  }

  if(phase === "askDob"){
    const dob = _parseDob(text);
    state.session.identityCapture.dob = dob;  // may be null if unrecognised

    // v8.0 FIX: Immediately project DOB into profile and projection state
    if (dob) {
      if(!state.profile) state.profile = {basics:{}, kinship:[], pets:[]};
      state.profile.basics.dob = dob;
      if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
        LorevoxProjectionSync.projectValue("personal.dateOfBirth", dob, {
          source: "interview", turnId: "identity-dob", confidence: 0.95
        });
      }
      // v8.0 FIX: Update narrator header card with DOB
      if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();
    }

    // BUG-226: Replace fragile /\bin\s+([A-Z][a-zA-Z\s,]+?)(?:\.|$)/i regex
    // with the new robust parser. Handles "born July 26 1943 in Dartford"
    // AND "born in Lima Peru December 20 1972" AND "I was born in Williston
    // North Dakota in 1949" — the previous regex required period or EOS
    // immediately after the place, which failed on any utterance with
    // trailing context.
    const _embeddedPob = _parseBirthplaceFromUtterance(text);

    // BUG-226: SKIP-AHEAD — if DOB + POB both captured in same answer,
    // mark all three identity anchors complete (name was set in askName)
    // and skip askBirthplace entirely. Prevents Lori from re-asking what
    // the narrator just told her — parent UX failure mode.
    if (dob && _embeddedPob) {
      state.session.identityCapture.birthplace = _embeddedPob;
      if(!state.profile) state.profile = {basics:{}, kinship:[], pets:[]};
      state.profile.basics.pob = _embeddedPob;
      if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
        LorevoxProjectionSync.projectValue("personal.placeOfBirth", _embeddedPob, {
          source: "interview", turnId: "identity-pob", confidence: 0.85
        });
      }
      if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();

      // BB sync — mirror to questionnaire.personal
      try {
        if (typeof window.lvBbSyncIdentity === "function") {
          window.lvBbSyncIdentity(state.profile.basics);
        }
      } catch (e) { console.warn("[bb-sync] askDob/skip-ahead threw:", e); }

      const name = state.session.identityCapture.name || state.profile.basics.preferred || "";
      console.log("[identity] BUG-226: DOB + POB extracted from askDob answer:", dob, _embeddedPob);
      state.session.identityPhase = "resolving";
      sendSystemPrompt(
        `[SYSTEM: The user just answered with their date of birth AND birthplace in one message: ` +
        `born ${dob} in ${_embeddedPob}. ` +
        `${name ? `Their name is "${name}". ` : ""}` +
        `These three identity anchors are ALL captured. ` +
        `Do NOT ask for any of them again. ` +
        `Acknowledge them warmly in one or two sentences. ` +
        `Then ask one open question that invites them to share an early memory or what kind of place ${_embeddedPob} was when they were growing up. One question only.]`
      );
      await _resolveOrCreatePerson();
      return true;
    }

    // Only DOB captured — store any embedded POB hint and proceed to askBirthplace.
    state.session.identityPhase = "askBirthplace";
    if (_embeddedPob) {
      state.session.identityCapture._embeddedPob = _embeddedPob;
    }

    // BB sync — mirror DOB to questionnaire.personal
    try {
      if (dob && typeof window.lvBbSyncIdentity === "function") {
        window.lvBbSyncIdentity(state.profile.basics);
      }
    } catch (e) { console.warn("[bb-sync] askDob threw:", e); }

    sendSystemPrompt(
      `[SYSTEM: The user gave their date of birth as "${text.trim()}". ` +
      `${dob ? "You have parsed it as "+dob+"." : "The date wasn't entirely clear but that's okay — continue."} ` +
      `Acknowledge naturally (brief, warm). ` +
      `Then ask where they were born — town, city, or region, whatever they remember. ` +
      `One question only.]`
    );
    return true;
  }

  if(phase === "askBirthplace"){
    // v8.0 FIX: Extract place from the answer instead of using the raw text.
    let birthplace = text.trim();

    // BEST SOURCE: If askName or askDob already extracted a place from
    // an earlier utterance, prefer that — narrator may have repeated
    // themselves or given a different (less precise) answer this turn.
    if (state.session.identityCapture._embeddedPob) {
      birthplace = state.session.identityCapture._embeddedPob;
    } else {
      // BUG-226: use the canonical parser. Handles all four real input
      // shapes (place before/after date, "from X", just the place name).
      const parsed = _parseBirthplaceFromUtterance(text);
      if (parsed) {
        birthplace = parsed;
      } else {
        // Fallback: whole-text trim (used when the narrator just says
        // "Lima, Peru" with no surrounding sentence — the parser's
        // last-resort branch handles that, so this is for malformed input).
        if (birthplace.length > 80) {
          const firstClause = text.split(/[.!?,]/)[0].trim();
          if (firstClause.length < 80) birthplace = firstClause;
        }
      }
    }

    state.session.identityCapture.birthplace = birthplace;

    // v8.0 FIX: Immediately project POB into profile and projection state
    if(!state.profile) state.profile = {basics:{}, kinship:[], pets:[]};
    state.profile.basics.pob = birthplace;
    if (typeof LorevoxProjectionSync !== "undefined" && state.interviewProjection) {
      LorevoxProjectionSync.projectValue("personal.placeOfBirth", birthplace, {
        source: "interview", turnId: "identity-pob", confidence: 0.9
      });
    }
    // v8.0 FIX: Update narrator header card with POB
    if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();

    // BUG-226: Mirror identity to Bio Builder questionnaire.personal —
    // all three anchors should now be in BB.
    try {
      if (typeof window.lvBbSyncIdentity === "function") {
        window.lvBbSyncIdentity(state.profile.basics);
      }
    } catch (e) { console.warn("[bb-sync] askBirthplace threw:", e); }

    state.session.identityPhase = "resolving";
    // Create the person record now that we have the three anchors
    await _resolveOrCreatePerson();
    return true;
  }

  return false;
}

/**
 * Create a new person in the backend using the three captured identity anchors,
 * then load them so the app is in a ready state.
 * Sets identityPhase to "complete" when done.
 */
async function _resolveOrCreatePerson(){
  const ic   = state.session.identityCapture;
  const name = ic.name || "Unnamed";
  const dob  = ic.dob  || null;
  const pob  = ic.birthplace || null;

  // Patch state.profile so the form reflects what Lori captured
  if(!state.profile) state.profile = {basics:{}, kinship:[], pets:[]};
  state.profile.basics.preferred  = name;
  state.profile.basics.fullname   = name;
  if(dob) state.profile.basics.dob = dob;
  if(pob) state.profile.basics.pob = pob;
  hydrateProfileForm();

  let pid = null;
  try{
    // v8.0 FIX: If a person_id already exists in state, PATCH the existing
    // person instead of creating a duplicate. This prevents person duplication
    // when the identity gate runs on an already-selected narrator.
    if (state.person_id) {
      pid = state.person_id;
      const patchResp = await fetch(API.PERSON(pid), {
        method: "PATCH",
        headers: ctype(),
        body: JSON.stringify({
          display_name:   name,
          date_of_birth:  dob  || undefined,
          place_of_birth: pob  || undefined,
        }),
      });
      if (!patchResp.ok) console.warn("[identity] PATCH failed:", patchResp.status);
      else console.log("[identity] Patched existing person:", pid);
    } else {
      const r = await fetch(API.PEOPLE, {
        method: "POST",
        headers: ctype(),
        body: JSON.stringify({
          display_name: name,
          role:         "subject",
          date_of_birth: dob  || null,
          place_of_birth: pob || null,
        }),
      });
      if (!r.ok) {
        console.error("[identity] POST /api/people failed:", r.status, await r.text().catch(()=>""));
        sysBubble("Could not save narrator to the server — please check the API backend.");
      } else {
        const j = await r.json();
        pid = j.id || j.person_id;
        console.log("[identity] Created new person:", pid);
      }
    }
  }catch(e){
    console.error("[identity] create/patch person failed:", e);
    sysBubble("Could not reach the server to save this narrator. The API may be down.");
  }

  state.session.identityPhase = "complete";
  setAssistantRole("interviewer");

  // WO-HORNELORE-SESSION-LOOP-01: identity intake just finished.  Hand
  // the steering wheel to the post-identity orchestrator so Lori has a
  // defined next step (BB walk for questionnaire_first; tier-2 directive
  // for clear_direct/memory_exercise/companion; no-op for warm_storytelling).
  // Without this hook, the session dead-ends here a second time.
  try {
    if (typeof window.lvSessionLoopOnTurn === "function") {
      window.lvSessionLoopOnTurn({ trigger: "identity_complete" });
    }
  } catch (e) {
    console.warn("[session-loop] identity_complete dispatch threw:", e);
  }

  // WO-IDENTITY-TO-LIFEMAP-01: trigger Life Map + Chronology Accordion
  // refresh so the just-captured DOB / POB / name immediately surface
  // visible anchors. Life Map already builds 6 default era scaffolds
  // (Early Childhood / School Years / Adolescence / Early Adulthood /
  // Midlife / Later Life) from state.profile.basics.dob — those just
  // need a render kick. Chronology Accordion fetches per-decade from
  // backend (DOB-gated). Both helpers already exist and are called by
  // narrator-switch flow (app.js:1935, html:4938); the fresh-onboarding
  // path was the only gap. Two-call refresh — non-fatal if either
  // throws.
  try {
    if (window.LorevoxLifeMap && typeof window.LorevoxLifeMap.render === "function") {
      window.LorevoxLifeMap.render(true);
      console.log("[identity] post-identity Life Map refresh fired");
    }
  } catch (e) { console.warn("[lifemap] post-identity render threw:", e); }
  try {
    if (typeof window.crInitAccordion === "function") {
      window.crInitAccordion();
      console.log("[identity] post-identity Chronology Accordion refresh fired");
    }
  } catch (e) { console.warn("[chronology] post-identity init threw:", e); }

  // v8.1: Mark this device as onboarded so future startups skip the welcome flow
  // and go straight to the narrator selector instead.
  try { localStorage.setItem("lorevox_device_onboarded", "1"); } catch(_) {}

  // v7.5 hook — lets lori7.5.html update capture UI without modifying this file.
  if (typeof window._onIdentityComplete === "function") {
    window._onIdentityComplete({ name, dob, pob: pob || ic.birthplace });
  }

  if(pid){
    await loadPerson(pid);
    // v7.4D BUG-B1: loadPerson fetches the server profile (still empty at this point)
    // and overwrites state.profile.basics. Re-apply the captured identity anchors
    // before saveProfile() so the correct values are persisted.
    if(ic.name)      { state.profile.basics.preferred = ic.name; state.profile.basics.fullname = ic.name; }
    if(ic.dob)         state.profile.basics.dob = ic.dob;
    if(ic.birthplace)  state.profile.basics.pob = ic.birthplace;
    hydrateProfileForm();
    _updateDockActivePerson();
    // v8.0 FIX: Update header AFTER re-applying identity anchors.
    // loadPerson() called lv80UpdateActiveNarratorCard() with the empty server profile,
    // so we must call it again now that basics are re-applied.
    if (typeof lv80UpdateActiveNarratorCard === "function") lv80UpdateActiveNarratorCard();
    // Save the profile so DOB + birthplace persist
    await saveProfile();
    // v8.1: After identity capture, explain mic/camera options before starting the interview.
    // This is the natural moment to ask — Lori has just met the user and is about to begin.
    sendSystemPrompt(
      `[SYSTEM: You have successfully captured ${name}'s identity. ` +
      `They were born in ${pob || "an unspecified location"}. ` +
      `Acknowledge their birthplace warmly (one sentence — mention it by name). ` +
      `Then, before starting the interview, briefly explain two things: ` +
      `1) They can speak to you using the microphone button, or type — whichever feels more comfortable. ` +
      `You can also speak your replies aloud. ` +
      `2) The camera is completely optional — if they turn it on, you can use it to read their ` +
      `expressions and pace the conversation more gently. The camera stays on this device and ` +
      `you never save video. They can turn it on or off anytime using the settings gear icon. ` +
      `Keep this explanation warm and brief — two to three sentences, not a list. ` +
      `Then ask if they have any questions, or if they're ready to begin. ` +
      `Do not mention any technical steps or form saving.]`
    );
  } else {
    // Backend unavailable — still set up local state
    sysBubble(`Welcome, ${name}! (Profile saved locally — connect the server to persist it.)`);
    sendSystemPrompt(
      `[SYSTEM: The user's name is ${name}. ` +
      `Acknowledge you're ready to begin their memoir, then ask your first interview question.]`
    );
  }
}

/* ═══════════════════════════════════════════════════════════════
   CHAT — WS primary, SSE fallback
═══════════════════════════════════════════════════════════════ */
function onChatKey(e){ if(e.key==="Enter"&&!e.shiftKey){ e.preventDefault(); sendUserMessage(); } }

// v7.4D — Help-intent keywords. Any of these in the user's message switches Lori
// to helper mode for that response. She answers the product question directly and
// does not continue the interview until the helper exchange is resolved.
const _HELP_KEYWORDS = [
  "how do i","how do you","how can i","how should i",
  "where do i","where is the","where can i",
  "what does this","what is this","what does the",
  "why didn't","why doesn't","why can't","why won't","why isn't",
  "help me use","help me with","help me understand",
  "i don't understand","i can't find","i'm confused",
  "how to save","how to create","how to start","how to use",
  "what tab","which tab","what button","which button",
  "how does lori","what is lori",
];

function _isHelpIntent(text){
  const t=text.toLowerCase();
  return _HELP_KEYWORDS.some(k=>t.includes(k));
}

/* WO-11C: Trainer active check — single helper used by all input guards.
   Returns true when trainer is actively running OR when trainer has finished
   but no narrator has been selected yet (pending-unlock state). */
function _wo11cIsTrainerActive() {
  if (!state || !state.trainerNarrators) return false;
  return !!(state.trainerNarrators.active || state.trainerNarrators._wo11cPendingUnlock);
}

async function sendUserMessage(){
  // WO-11C: Block normal send while trainer mode is active.
  // Trainer is a coaching screen, not a live Lori interview.
  if (_wo11cIsTrainerActive()) {
    console.log("[WO-11C] sendUserMessage() BLOCKED — trainer mode active");
    if (typeof sysBubble === "function") {
      sysBubble("Complete the trainer first, then we\u2019ll begin your interview.");
    }
    return;
  }
  unlockAudio();
  const text=getv("chatInput").trim(); if(!text) return;
  // WO-MIC-UI-02A: Confirm send source and content
  console.log("[WO-MIC-UI-02A] sendUserMessage() — source: #chatInput, length:", text.length, "preview:", text.slice(0, 80));
  // WO-STT-LIVE-02 (#99) — when no speech capture is staged (or it's
  // stale / doesn't match the current input), mark the send as typed
  // so the extraction payload carries transcript_source="typed" and
  // the backend stamps audio_source on the resulting items. Purely
  // annotative — typed sends are never forced into confirmation UX.
  try {
    if (window.TranscriptGuard) {
      var _staged = state && state.lastTranscript;
      var _needle = (_staged && _staged.normalized_text) ? _staged.normalized_text.trim().toLowerCase() : "";
      var _hay    = text.trim().toLowerCase();
      var _age    = _staged && _staged.ts ? (Date.now() - _staged.ts) : Infinity;
      var _stale  = _age > (window.TranscriptGuard.STALE_MS || 30000);
      var _matches= _needle && _hay.indexOf(_needle) !== -1;
      if (!_staged || !_staged.source || _stale || !_matches) {
        window.TranscriptGuard.markTypedInput(text, { turnId: null });
      }
    }
  } catch (_e) { console.warn("[STT-guard] typed mark failed:", _e && _e.message); }
  // Phase Q.4: Block user sends while model is still warming up
  if (!_llmReady) {
    appendBubble("ai", "Hornelore is still warming up — please wait a moment for the model to finish loading.");
    return;
  }
  // v7.4D — Phase 7: capture for post-reply fact extraction.
  _lastUserTurn = text;
  // WO-10: Update conversation state detector
  _wo10LastUserText = text;
  // v7.4D — stop recording immediately on send so we don't capture background
  // audio or Lori's incoming response. Mic stays off; user re-enables when ready.
  if(isRecording) stopRecording();
  // WO-10H: Release narrator turn-claim on Send
  if (typeof wo10hReleaseTurn === "function") wo10hReleaseTurn("send_submitted");

  // v7.4D — Phase 6: identity-first onboarding state machine.
  // Route through identity extractor. If _advanceIdentityPhase returns true,
  // the message was handled (phase advanced, system prompt injected) — return.
  // If it returns false, the message was emotional/non-answer content —
  // fall through to the normal LLM flow so IDENTITY MODE directive can respond.
  let _bubbleAlreadyAdded = false;
  if(state.session?.identityPhase && state.session.identityPhase !== "complete"){
    setv("chatInput",""); appendBubble("user",text);
    _bubbleAlreadyAdded = true;
    const _handled = await _advanceIdentityPhase(text);
    if(_handled) return;
    // Not handled — fall through to normal chat path with IDENTITY MODE active.
  }

  // WO-HORNELORE-SESSION-LOOP-01: per-turn dispatch.  Once identity is
  // complete, every narrator turn pings the orchestrator so it can
  // advance the questionnaire walk (questionnaire_first / clear_direct)
  // OR refresh tier-2 directives (memory_exercise / companion).
  // warm_storytelling is a no-op.  Idempotent — askedKeys ledger
  // prevents duplicate field asks.
  if (state.session?.identityPhase === "complete" &&
      typeof window.lvSessionLoopOnTurn === "function") {
    try {
      window.lvSessionLoopOnTurn({ trigger: "narrator_turn", text });
    } catch (e) {
      console.warn("[session-loop] narrator_turn dispatch threw:", e);
    }
  }

  // BUG-209: archive-writer narrator inline-call DISABLED.
  // The backend chat_ws path already writes the narrator turn into the
  // same memory archive.  Calling lvArchiveOnNarratorTurn here caused
  // every turn to land twice in transcript.jsonl (once as `user` from
  // chat_ws, once as `narrator` from archive-writer).  Confirmed via
  // Chris's morning export 2026-04-25.  Backend WS is single source.
  // The lvArchiveOnNarratorTurn hook remains callable for the
  // future WO-AUDIO-NARRATOR-ONLY-01 audio-attachment flow if it
  // needs a paired write — that's a deliberate manual path.
  // To re-enable: remove this comment and uncomment the original block.
  //
  // if (typeof window.lvArchiveOnNarratorTurn === "function") {
  //   try { window.lvArchiveOnNarratorTurn(text); } catch (_) {}
  // }

  // WO-AUDIO-NARRATOR-ONLY-01: stop in-progress audio segment + upload.
  // Generate a client-side turn_id; backend stores audio under that id
  // in audio/<turn_id>.webm regardless of whether the chat_ws transcript
  // row eventually links it.  Operator can correlate by timestamp at
  // review time.  A no-op if audio recorder isn't loaded or recordVoice
  // is OFF or there's no live segment.
  if (typeof window.lvNarratorAudioRecorder === "object" && window.lvNarratorAudioRecorder.stop) {
    try {
      const _audioTurnId = (typeof crypto !== "undefined" && crypto.randomUUID)
        ? crypto.randomUUID()
        : ("t_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 10));
      // Fire-and-forget — don't block sendUserMessage on upload.
      window.lvNarratorAudioRecorder.stop(_audioTurnId).catch((e) => {
        console.warn("[narrator-audio] stop+upload threw:", e && e.message || e);
      });
    } catch (e) { console.warn("[narrator-audio] turn_id gen threw:", e); }
  }

  // v7.4D — helper-mode detection. If the user appears to be asking how to use
  // the app, switch Lori to helper role for this turn. The role resets to
  // "interviewer" in onAssistantReply() after Lori's response lands.
  if(_isHelpIntent(text) && getAssistantRole()==="interviewer"){
    setAssistantRole("helper");
  }

  if(!_bubbleAlreadyAdded){ setv("chatInput",""); appendBubble("user",text); }
  // BUG-219: clear pre-mic draft snapshot now that the turn has been
  // committed.  Next mic-arm will capture a fresh snapshot from a
  // (typically empty) chatInput.
  _wo8PreMicDraft = "";
  let systemInstruction="";

  if(state.interview.session_id&&state.interview.question_id){
    try{
      const j=await processInterviewAnswer(text,false);
      if(j){
        if(j.done){
          systemInstruction="[SYSTEM: The interview section is now complete. Warmly acknowledge the user's final answer and congratulate them.]";
        } else if(j.next_question?.prompt){
          const noSummary=(j.generated_summary||(j.followups_inserted||0)>0)
            ?"A summary was generated and saved to Section Notes. Do NOT repeat it in chat. ":"";
          systemInstruction=`[SYSTEM: ${noSummary}Acknowledge the answer naturally in 1–2 sentences, then ask the next question exactly as written: "${j.next_question.prompt}"]`;
        }
      }
    }catch{}
  }

  // v8.0 / WO-deferred — queue free-form extraction instead of firing immediately.
  // Extraction will flush after Lori finishes responding (WS done / SSE complete).
  if(!state.interview.session_id && typeof _extractAndProjectMultiField === "function"){
    state.interviewProjection = state.interviewProjection || {};
    state.interviewProjection._pendingExtraction = {
      answerText: text,
      turnId: "turn-" + Date.now(),
      queuedAt: Date.now(),
      source: "sendUserMessage.freeform"
    };
    console.log("[extract][queue] deferred free-form extraction queued");
  }

  const payload=systemInstruction?`${text}\n\n${systemInstruction}`:text;

  if(ws&&wsReady&&!usingFallback){
    // WO-ARCH-07A — local deterministic turn routing
    const routedMode = lvRouteTurn(text);
    state.session.turnMode = routedMode;

    // WO-ARCH-07A — local deterministic memory echo build
    if (routedMode === TURN_MEMORY_ECHO) {
      buildMemoryEchoEntity();
    }

    // v7.1: capture runtime71 BEFORE setLoriState("thinking") so transitional
    // badge updates never wipe semantic state (fatigue, cognitive mode, etc.)
    const _rt71 = buildRuntime71();
    setLoriState("thinking");
    currentAssistantBubble=null;
    // v7.1 — auto cognitive mode detection before send
    try {
      if (window.LORI71 && window.LORI71.CognitiveAuto) {
        const _caResult = window.LORI71.CognitiveAuto.processUserTurn(text||"");
        console.log("[Lori 7.1] cognitive auto:", _caResult.mode, "("+_caResult.reason+")");
      }
    } catch(e) {}
    console.log("[WO-ARCH-07A] turn_mode:", routedMode);
    console.log("[Lori 7.1] runtime71 → model:", JSON.stringify(_rt71, null, 2));
    const _llmT = (window._lv10dLlmParams && window._lv10dLlmParams.temperature) || 0.7;
    const _llmM = (window._lv10dLlmParams && window._lv10dLlmParams.max_new_tokens) || 512;
    ws.send(JSON.stringify({type:"start_turn",session_id:state.chat.conv_id||"default",
      message:payload,turn_mode:routedMode,params:{person_id:state.person_id,temperature:_llmT,max_new_tokens:_llmM,runtime71:_rt71}}));
    // Safety timeout: if no response within 30s, unstick the UI
    // WO-S3: Guard against stacked unavailable messages — only show once
    // WO-11: Only show unavailable if WS is genuinely disconnected
    const _sendTimestamp = Date.now();
    setTimeout(()=>{
      if(!currentAssistantBubble){
        // WO-11: Check if WS is actually healthy before showing error
        if (ws && wsReady) {
          console.log("[WO-11][chat-state] 30s timeout but WS is connected — suppressing false unavailable");
          setLoriState("ready");
          return;
        }
        // Prevent stacked error messages: check if a recent error bubble already exists
        const chatLog = document.getElementById("chatLog");
        const lastBubble = chatLog && chatLog.lastElementChild;
        const isRecentError = lastBubble && lastBubble.textContent &&
          lastBubble.textContent.includes("Chat service unavailable") &&
          (Date.now() - _sendTimestamp) < 35000;
        if (!isRecentError) {
          console.log("[WO-11][chat-state] Chat unavailable banner SET — WS disconnected");
          appendBubble("ai","Chat service unavailable — start or restart the Hornelore AI backend to enable responses.");
        }
        setLoriState("ready");
      }
    }, 30000);
    return;
  }
  await streamSse(payload);
}

async function sendSystemPrompt(instruction){
  // Phase Q.4: Block system prompts (onboarding, interview) while model is warming
  if (!_llmReady) {
    console.warn("[readiness] sendSystemPrompt blocked — model not ready yet.");
    return;
  }
  const bubble=appendBubble("ai","…");
  if(ws&&wsReady&&!usingFallback){
    const _rt71sys = buildRuntime71(); // capture before thinking resets badge
    setLoriState("thinking");
    currentAssistantBubble=bubble;
    console.log("[Lori 7.1] runtime71 (sys) → model:", JSON.stringify(_rt71sys, null, 2));
    const _llmTs = (window._lv10dLlmParams && window._lv10dLlmParams.temperature) || 0.7;
    const _llmMs = (window._lv10dLlmParams && window._lv10dLlmParams.max_new_tokens) || 512;
    ws.send(JSON.stringify({type:"start_turn",session_id:state.chat.conv_id||"default",
      message:instruction,params:{person_id:state.person_id,temperature:_llmTs,max_new_tokens:_llmMs,runtime71:_rt71sys}}));
    // Safety timeout: if no response within 120s, unstick the UI
    // WO-11: Only show unavailable if WS is genuinely disconnected
    //
    // 2026-05-04 BUG-SENDSYSTEMPROMPT-PLACEHOLDER-RACE-01: bumped 30s → 120s.
    // Live evidence (rehearsal_quick_v9 api.log 11:05:03-11:05:38): a
    // sendSystemPrompt-driven LLM turn with prompt_tokens=6851 took 35s
    // to complete generation, but the 30s timeout fired at 11:05:33 while
    // the bubble was still "…" placeholder. setLoriState("ready") triggered
    // the [lv80-turn-debug] lori_reply event (hornelore1.0.html:8156) reading
    // textContent="…", which the harness's placeholder filter correctly
    // rejected — no subsequent event fired because bubble.remove() ran.
    // Result: harness saw zero captured replies despite Lori actually
    // responding 5s after the spurious event.
    //
    // Real fix is WO-PROMPT-BLOAT-AUDIT-01 to get prompt_tokens under 3000.
    // This is containment until that lands. 120s covers worst-case LLM
    // generation time at current bloat (~50s for 7K-token prompt) with 2x
    // safety margin. Genuinely-broken WS still gets surfaced after 120s.
    setTimeout(()=>{
      if(currentAssistantBubble===bubble && _bubbleBody(bubble)?.textContent==="…"){
        // WO-11: Check if WS is actually healthy before showing error
        if (ws && wsReady) {
          console.log("[WO-11][chat-state] System prompt 120s timeout but WS connected — suppressing");
          setLoriState("ready");
          currentAssistantBubble=null;
          // Remove the "…" bubble since WS is fine, just slow
          try { bubble.remove(); } catch(_) {}
          return;
        }
        console.warn("[sendSystemPrompt] 120s timeout — no response from backend");
        console.log("[WO-11][chat-state] Chat unavailable banner SET (system prompt path)");
        _bubbleBody(bubble).textContent="Chat service unavailable — start or restart the Hornelore AI backend to enable responses.";
        setLoriState("ready");
        currentAssistantBubble=null;
      }
    }, 120000);
    return;
  }
  await streamSse(instruction,bubble);
}

async function streamSse(text,overrideBubble=null){
  // Phase 6A: Per-turn timing/lifecycle log
  var _turnId = Date.now().toString(36);
  var _t0 = performance.now();
  var _tFirstToken = 0, _tLastToken = 0;
  console.log("[chat-turn:" + _turnId + "] user_send", { textLen: text.length, ts: new Date().toISOString() });
  setLoriState("thinking");
  const bubble=overrideBubble||appendBubble("ai","…");
  // v6.2: inject language instruction when profile specifies a non-English preference
  const _lang=state.profile?.basics?.language||"";
  const _langNote=_lang?` Please communicate in ${_lang} throughout this session.`:"";
  // v6.3: disambiguation and birthplace rules baked into every system prompt
  const _rules=`

IMPORTANT INTERVIEW RULES:
1. DATE DISAMBIGUATION — When someone uses numbers to describe family members (e.g. "my brothers were 60 and 61", "born in '38 and '40", "she's 68"), do NOT assume these are current ages. If the person was born in a year that makes the numbers plausible as birth years (e.g. speaker born 1962, says "brothers 60 and 61" → likely birth years 1960 and 1961), treat them as birth years. When genuinely ambiguous, ask once: "Just to confirm — do you mean they were born in 1960 and 1961, or that they are currently 60 and 61 years old?" Never record an assumed age as fact without confirmation.
2. BIRTHPLACE vs. CHILDHOOD — If the person says they moved away from their birthplace in infancy or very early childhood (before age 4), do NOT ask for memories from the birthplace. Their meaningful early memories will be from where they were raised. Ask about the place they grew up in, not where they were born.
3. BIRTH YEARS — Always distinguish between a birth year and a current age. When collecting data for siblings, children, or parents, explicitly note whether a number is a birth year or an age.`;
  const sys=`You are Lori, a warm oral historian and memoir biographer working for Hornelore.${_langNote}${_rules} PROFILE_JSON: ${JSON.stringify({person_id:state.person_id,profile:state.profile})}`;
  const body={messages:[{role:"system",content:sys},{role:"user",content:text}],
    temp:0.7,max_new:512,conv_id:state.chat.conv_id||"default"};
  let full="";
  try{
    const res=await fetch(API.CHAT_SSE,{method:"POST",headers:ctype(),body:JSON.stringify(body)});
    if(!res.ok) throw new Error("SSE error "+res.status);
    const reader=res.body.getReader(); const dec=new TextDecoder();
    setLoriState("drafting");
    let _sseError = null;
    while(true){
      const {done,value}=await reader.read(); if(done) break;
      for(const line of dec.decode(value,{stream:true}).split("\n")){
        if(!line.trim()) continue;
        try{
          const d=JSON.parse(line.replace(/^data:\s*/,""));
          if(d.error){
            // Backend sent an error (CUDA_OOM, generation_error, etc.)
            _sseError = d;
            console.error("[SSE] backend error:", d.error, d.message);
          } else if(d.delta||d.text){
            if(!_tFirstToken) { _tFirstToken = performance.now(); console.log("[chat-turn:" + _turnId + "] first_token", { ms: Math.round(_tFirstToken - _t0) }); }
            _tLastToken = performance.now();
            full+=(d.delta||d.text); _bubbleBody(bubble).textContent=full;
            document.getElementById("chatMessages").scrollTop=99999;
          }
        }catch{}
      }
    }
    if(_sseError && !full){
      // Error with no generated text — show user-friendly message
      if(_sseError.error==="CUDA_OOM"){
        _bubbleBody(bubble).textContent="GPU memory was full. VRAM has been freed — try sending your message again.";
      } else {
        _bubbleBody(bubble).textContent="Chat error: " + (_sseError.message||"unknown backend error") + ". Try again.";
      }
    } else {
      onAssistantReply(full);
      if(full && !text.startsWith("[SYSTEM:")){
        setv("ivAnswer",full);
        captureState="captured";
        renderCaptureChip();
      }
      if(obitDraftType==="lori_pending"){ setObitDraftType("lori"); }
    }
    // Phase 6A: log final token timing
    console.log("[chat-turn:" + _turnId + "] final_token", { ms: Math.round(_tLastToken - _t0), responseLen: full.length });
    setLoriState("ready");

    // WO-deferred: Flush queued extraction now that SSE stream is complete
    // Phase 6B.1: Make extraction failure non-fatal to the conversation
    if (typeof _runDeferredInterviewExtraction === "function") {
      var _tExtStart = performance.now();
      console.log("[chat-turn:" + _turnId + "] extraction_start");
      try {
        await _runDeferredInterviewExtraction();
        console.log("[chat-turn:" + _turnId + "] extraction_finish", { ms: Math.round(performance.now() - _tExtStart) });
      } catch(e) {
        // Phase 6B.1: Extraction failure is non-fatal — log and continue
        console.warn("[chat-turn:" + _turnId + "] extraction_failed (non-fatal)", { error: String(e), ms: Math.round(performance.now() - _tExtStart) });
      }
    }
  }catch(err){
    // Phase 6A: log websocket/fetch error
    console.error("[chat-turn:" + _turnId + "] ws_error", { error: String(err), ms: Math.round(performance.now() - _t0) });
    _bubbleBody(bubble).textContent="Chat service unavailable — start the Lorevox backend to enable AI responses.";
    setLoriState("ready");
  }
}

function onAssistantReply(text){
  if(!text) return;
  lastAssistantText=text;
  document.getElementById("lastAssistantPanel").textContent=text;
  // BUG-HARNESS-LORI-REPLY-CAPTURE-01 (2026-05-05): emit a reliable
  // full-text lori_reply event for harness consumption. The legacy
  // emit at hornelore1.0.html:8156 fires from _lv80MirrorStatus("ready")
  // and is gated by _lv80IdleWasThinking — for memory_echo turns the
  // gate occasionally misses (TEST-23 v5 evidence: Marvin's recall_pre
  // captured 0 chars while Mary's same path captured 200 chars), AND
  // it slices reply_text to 200 chars so longer readbacks lose their
  // tail. This emit runs unconditionally at the top of every assistant
  // reply with the FULL text. The harness's wait_for_lori_turn returns
  // the first matching non-placeholder event, so this firing FIRST
  // keeps the harness reliably bound to the real reply.
  try {
    if (typeof window.lv80LogTurnDebug === "function") {
      window.lv80LogTurnDebug({
        event: "lori_reply",
        reply_text: text,  // FULL text, no slice — harness needs name/dob/pob anywhere in body
        source: "onAssistantReply",
      });
    } else {
      console.log("[lv80-turn-debug]", { event: "lori_reply", reply_text: text, source: "onAssistantReply" });
    }
  } catch (_) {}
  enqueueTts(text);
  // v7.4D — after one helper exchange, return Lori to interviewer role.
  // This means the next user message will go back to normal interview mode
  // unless another help intent is detected.
  // NOTE: do NOT reset 'onboarding' — _advanceIdentityPhase manages that role.
  if(getAssistantRole()==="helper"){
    setAssistantRole("interviewer");
  }
  // v7.4D — Phase 7: fire-and-forget fact extraction after each real turn.
  // Only runs when a person is loaded and onboarding is complete.
  // WO-13 Phase 3: skip reference narrators entirely — they are read-only
  // from the narrative memory pipeline and the backend will 403 their writes.
  if(
    state.person_id
    && (!state.session?.identityPhase || state.session.identityPhase==="complete")
    && !_wo13IsReferenceNarrator(state.person_id)
  ){
    _extractAndPostFacts(_lastUserTurn, text).catch(()=>{});
  }
}

// ── WO-13 Phase 3 — Reference narrator helper ─────────────────────────────
// Reads narrator_type from the cached /api/people list. Defaults to false
// (treat as live) when unknown so we fail-open on caching races. The
// backend guard is the authoritative enforcement.
function _wo13IsReferenceNarrator(pid){
  if(!pid) return false;
  try{
    const cache = state?.narratorUi?.peopleCache || [];
    const hit = cache.find(p => (p.id||p.person_id||p.uuid) === pid);
    if(!hit) return false;
    return String(hit.narrator_type || "live").toLowerCase() === "reference";
  }catch{
    return false;
  }
}

/* ═══════════════════════════════════════════════════════════════
   PHASE 7 — FACT EXTRACTION  (v7.4D)
   Pattern-based extraction from user turns. Runs client-side so
   it never blocks the LLM or the chat. Results are posted to
   /api/facts/add and are immediately available in the Facts tab.
   The user never sees this happening — it just works.
═══════════════════════════════════════════════════════════════ */

// ── Meaning signal patterns (Phase A — meaning infrastructure) ─────────────
// These are probabilistic — over-tagging is worse than under-tagging.
// Patterns detect signal categories; they do not attempt semantic parsing.

const _LV80_STAKES_RX = /\b(almost lost|had to leave|no choice|had no choice|everything (was |at )risk|couldn'?t afford|going to lose|things got bad|had to decide|there was no (way|choice)|we were going to|forced to|had to get out|at stake|couldn'?t go on|had to fight|had no other)\b/i;

const _LV80_VULNERABILITY_RX = /\b(divorced|divorce|estranged|estrangement|all alone|left me|she left|he left|they left|never came back|didn'?t know how to tell|never told (him|her)|fell apart|broke apart|no one (was there|cared)|nobody (was there|cared)|I was alone|felt abandoned|she (was gone|left us)|he (was gone|left us)|never talked about it)\b/i;

const _LV80_TURNING_POINT_RX = /\b(changed (my|our|everything|it all)|never the same|from that (day|moment|point) on|that was when|everything changed|changed (forever|my life)|after that (everything|nothing|it all)|that'?s when (I|we|it all|everything))\b/i;

const _LV80_IDENTITY_RX = /\b(I became|I was no longer|that'?s when I became|I realized (who|what) I (was|am)|found (myself|my place)|I stopped being|I started to become|I (was|am) (a different|a new) person|had to become|became the person)\b/i;

const _LV80_LOSS_RX = /\b(passed away|died|lost (my|her|him|them|our)|death of|the day (she|he|they) (died|left|passed)|never saw (her|him|them) again|gone forever|I lost (my|her|him|them)|we lost)\b/i;

const _LV80_BELONGING_RX = /\b(finally felt|belonged|my people|felt at home|fit in|first time I (felt|belonged|fit)|found my place|where I belonged|felt like I (was )?home|felt like I belonged)\b/i;

const _LV80_REFLECTION_RX = /\b(I know now|looking back|in retrospect|I understand now|I realize now|now I (see|understand|know)|I can see now|all these years later|I'?ve come to (understand|realize|see|know)|what I know now|thinking back|from this distance|with hindsight|years later I)\b/i;

function _lv80DetectMeaningTags(text) {
  const tags = [];
  if (_LV80_STAKES_RX.test(text))        tags.push("stakes");
  if (_LV80_VULNERABILITY_RX.test(text)) tags.push("vulnerability");
  if (_LV80_TURNING_POINT_RX.test(text)) tags.push("turning_point");
  if (_LV80_IDENTITY_RX.test(text))      tags.push("identity");
  if (_LV80_LOSS_RX.test(text))          tags.push("loss");
  if (_LV80_BELONGING_RX.test(text))     tags.push("belonging");
  return tags;
}

// Map meaning signals and fact_type to a narrative role.
// Text-based signals take priority over structural fact_type defaults.
function _lv80DetectNarrativeRole(text, factType) {
  if (_LV80_REFLECTION_RX.test(text))    return "reflection";
  if (_LV80_TURNING_POINT_RX.test(text)) return "climax";
  if (_LV80_STAKES_RX.test(text))        return "escalation";
  if (_LV80_LOSS_RX.test(text))          return "climax";
  switch (factType) {
    case "birth":               return "setup";
    case "family_relationship": return "setup";
    case "education":           return "setup";
    case "employment_start":    return "setup";
    case "marriage":            return "inciting";
    case "residence":           return "inciting";
    case "employment_end":      return "resolution";
    case "death":               return "climax";
    default:                    return null;
  }
}

// Phase B — dual persona: separate "you then" (experience) from "you now" (reflection).
// A turn with reflection language gets reflection field populated; experience left null.
// A turn without reflection language gets experience populated; reflection left null.
function _lv80DetectDualPersona(text) {
  const isReflection = _LV80_REFLECTION_RX.test(text);
  return {
    experience: isReflection ? null : text.slice(0, 300),
    reflection: isReflection ? text.slice(0, 300) : null,
  };
}

// WO-13 Phase 4 — Five identity-critical fields that can NEVER be mutated by
// the regex/rules_fallback client extractor. If the extractor would propose one
// of these, the item is flagged identity_conflict=true in provenance and the
// status is forced to source_only so the review UI can surface it without the
// row ever entering the promoted-truth path.
const _WO13_PROTECTED_IDENTITY_FIELDS = Object.freeze([
  "personal.fullName",
  "personal.preferredName",
  "personal.dateOfBirth",
  "personal.placeOfBirth",
  "personal.birthOrder",
]);

/**
 * WO-13 Phase 4 — Regex-based proposal extractor (aka "rules_fallback").
 *
 * Returns an array of proposal items (NOT legacy fact objects) derived from a
 * single user turn. Each item has the shape expected by
 *   POST /api/family-truth/note/{note_id}/propose
 * i.e. { subject_name, relationship, field, source_says, status, confidence,
 *        narrative_role, meaning_tags, provenance, extraction_method }.
 *
 * This path is intentionally conservative: status defaults to 'needs_verify'
 * and extraction_method is always 'rules_fallback'. The LLM/hybrid extractor
 * (server side) will use the same shape but different extraction_method tags.
 */
function _extractFacts(userText, loriText){
  const items = [];
  const src   = (userText||"").trim();
  const pid   = state.person_id;
  if(!pid || !src) return items;

  const sid = state.chat?.conv_id || null;
  const narratorName = (state.narratorUi?.currentNarratorName
    || state.person?.display_name
    || "").trim();

  const _meaning = _lv80DetectMeaningTags(src);

  const _propose = (field, source_says, {
    subject_name = narratorName,
    relationship = "self",
    confidence = 0.7,
    fact_type = "",
  } = {}) => {
    const narrative_role = _lv80DetectNarrativeRole(src, fact_type || field);
    const isProtected = _WO13_PROTECTED_IDENTITY_FIELDS.includes(field);
    return {
      subject_name: subject_name || "",
      relationship: relationship || "self",
      field,
      source_says,
      status: isProtected ? "source_only" : "needs_verify",
      confidence: isProtected ? Math.min(confidence, 0.5) : confidence,
      narrative_role,
      meaning_tags: _meaning,
      extraction_method: "rules_fallback",
      provenance: {
        source: "chat_extraction",
        session_id: sid,
        user_turn: src.slice(0, 200),
        fact_type: fact_type || "",
        identity_conflict: isProtected || false,
        protected_field: isProtected ? field : undefined,
      },
    };
  };

  // ── Birthplace (PROTECTED: personal.placeOfBirth) ────────────
  let m;
  const _PLACE_CAP = /([A-Z][^,.!?]{1,35}(?:,\s*[A-Z][^,.!?]{1,30})?)/;
  m = src.match(new RegExp(
    String.raw`\b(?:born|grew up)[^.!?]{0,8}(?:in|at|near)\s+` + _PLACE_CAP.source, "i"
  ));
  if(!m) m = src.match(new RegExp(
    String.raw`\bI(?:'m| am)\s+(?:originally\s+)?from\s+` + _PLACE_CAP.source, "i"
  ));
  if(!m) m = src.match(new RegExp(
    String.raw`\boriginally\s+from\s+` + _PLACE_CAP.source, "i"
  ));
  if(m){
    const place = m[1].trim();
    items.push(_propose("personal.placeOfBirth", `Born or raised in ${place}`, {
      confidence: 0.75, fact_type: "birth",
    }));
  }

  // ── Date of birth (PROTECTED: personal.dateOfBirth) ──────────
  m = src.match(/\b(?:born on|born)\s+((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:[,\s]+\d{4})?|\d{1,2}\/\d{1,2}\/\d{4}|\d{4}-\d{2}-\d{2})/i);
  if(m){
    items.push(_propose("personal.dateOfBirth", `Date of birth: ${m[1].trim()}`, {
      confidence: 0.85, fact_type: "birth",
    }));
  }

  // ── Marriage ─────────────────────────────────────────────────
  m = src.match(/\b(?:married|got married to|my (?:husband|wife|spouse) is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i);
  if(m) items.push(_propose("marriage", `Married ${m[1].trim()}`, {
    confidence: 0.7, fact_type: "marriage",
  }));

  // ── Children ─────────────────────────────────────────────────
  m = src.match(/\b(?:my (?:son|daughter|child|kids?|children|boy|girl))[^.!?]{0,20}(?:name(?:d|s)?|is|are|called)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i);
  if(m) items.push(_propose("family_relationship", `Child named ${m[1].trim()}`, {
    subject_name: m[1].trim(), relationship: "child",
    confidence: 0.65, fact_type: "family_relationship",
  }));

  // ── Employment ───────────────────────────────────────────────
  m = src.match(/\b(?:worked (?:at|for)|worked as|(?:a |an )?(?:job|career) (?:at|with)|employed (?:at|by)|I was (?:a|an|the))\s+([^.!?,]{3,60})/i);
  if(m) items.push(_propose("employment", `Worked: ${m[1].trim()}`, {
    confidence: 0.65, fact_type: "employment_start",
  }));

  m = src.match(/\bI(?:'ve)? (?:been |)(?:retired|retiring|left)\s+(?:from\s+)?([^.!?,]{3,60})/i);
  if(m) items.push(_propose("employment", `Retired or left: ${m[1].trim()}`, {
    confidence: 0.65, fact_type: "employment_end",
  }));

  // ── Education ────────────────────────────────────────────────
  m = src.match(/\b(?:graduated from|went to|attended|studied at)\s+([A-Z][^.!?,]{3,60})/i);
  if(m) items.push(_propose("education", `Education: ${m[1].trim()}`, {
    confidence: 0.65, fact_type: "education",
  }));

  // ── Residence / moves ────────────────────────────────────────
  m = src.match(/\b(?:moved to|we moved to|living in|lived in|grew up in|settled in|ended up in|made (?:my|our) home in)\s+([A-Z][^.!?,]{2,60})/i);
  if(m) items.push(_propose("residence", `Residence: ${m[1].trim()}`, {
    confidence: 0.6, fact_type: "residence",
  }));

  // ── Death (family member) ────────────────────────────────────
  m = src.match(/\b(?:my\s+(?:mother|father|mom|dad|sister|brother|wife|husband|spouse|son|daughter|grandpa|grandma|grandfather|grandmother))[^.!?]{0,30}(?:passed away|died|passed|is gone)\b/i);
  if(m) items.push(_propose("death", `Family loss: ${m[0].trim()}`, {
    relationship: "family",
    confidence: 0.7, fact_type: "death",
  }));

  // Deduplicate by (field, source_says)
  const seen = new Set();
  return items.filter(it => {
    const key = it.field + "::" + it.source_says;
    if(seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * WO-13 Phase 4 — Fire-and-forget: extract proposal items from a turn and
 * POST them via the two-step family-truth pipeline:
 *   1. POST /api/family-truth/note    → create shadow note (one per turn)
 *   2. POST /api/family-truth/note/{id}/propose → batch of proposal items
 *
 * Writes are SKIPPED entirely for:
 *   - reference narrators (Shatner/Dolly/…) — guarded by _wo13IsReferenceNarrator
 *   - identity phase still in progress (handled by caller)
 *
 * The legacy /api/facts/add path is NOT used any more. Failures are silently
 * ignored — this must never break the chat UI.
 */
async function _extractAndPostFacts(userText, loriText){
  if(!state.person_id) return;
  // Extra defence: reference narrators never get shadow writes.
  if(typeof _wo13IsReferenceNarrator === "function"
     && _wo13IsReferenceNarrator(state.person_id)) return;

  // WO-9: Chunk long user turns before extraction for better coverage
  const chunks = (typeof _wo8ChunkText === "function" && userText && userText.length > 1200)
    ? _wo8ChunkText(userText, 1200) : [userText];

  const allItems = [];
  for (let i = 0; i < chunks.length; i++) {
    const items = _extractFacts(chunks[i], i === chunks.length - 1 ? loriText : "");
    allItems.push(...items);
  }

  // Deduplicate proposal items by (field, source_says)
  const seen = new Set();
  const deduped = [];
  for (const it of allItems) {
    const key = (it.field || "") + "::" + (it.source_says || "");
    if (!seen.has(key)) { seen.add(key); deduped.push(it); }
  }
  if(!deduped.length) return;

  // Step 1 — create the shadow note for this turn.
  let noteId = null;
  try{
    const sid = state.chat?.conv_id || "";
    const turnIdx = state.chat?.turns?.length ?? 0;
    const narratorName = (state.narratorUi?.currentNarratorName
      || state.person?.display_name
      || "ui").trim() || "ui";
    const body = (userText || "").trim();
    if(!body) return;
    const noteReq = {
      person_id: state.person_id,
      body: body.slice(0, 8000),
      source_kind: "chat",
      source_ref: sid ? `${sid}:${turnIdx}` : String(turnIdx),
      created_by: narratorName,
    };
    const res = await fetch(API.FT_NOTE_ADD, {
      method: "POST", headers: ctype(), body: JSON.stringify(noteReq),
    });
    if(!res.ok){
      if(res.status === 403){
        console.log("[family-truth] reference narrator — note creation denied (403).");
      }
      return;
    }
    const data = await res.json().catch(()=>null);
    noteId = data && data.note && data.note.id ? data.note.id : null;
  }catch{ return; }
  if(!noteId) return;

  // Step 2 — derive structured proposal rows from the note.
  try{
    const res = await fetch(API.FT_NOTE_PROPOSE(noteId), {
      method: "POST", headers: ctype(), body: JSON.stringify({ items: deduped }),
    });
    if(!res.ok) return;
  }catch{ return; }

  console.log(`[family-truth] shadow note ${noteId} → ${deduped.length} proposal row(s) from ${chunks.length} chunk(s).`);
  if(typeof updateArchiveReadiness === "function") updateArchiveReadiness();
}

/* ═══════════════════════════════════════════════════════════════
   WEBSOCKET
═══════════════════════════════════════════════════════════════ */
function connectWebSocket(){
  try{
    ws=new WebSocket(API.CHAT_WS);
    ws.onopen=()=>{
      wsReady=true; usingFallback=false; pill("pillWs",true);
      console.log("[WO-11][chat-state] WS connected — clearing any stale error state");
      // WO-11: Clear stale "chat unavailable" state on reconnect
      setLoriState("ready");
      // WO-2: Send sync_session packet immediately on connect
      if(state.person_id){
        ws.send(JSON.stringify({type:"sync_session",person_id:state.person_id,
          old_conv_id:state.chat?.conv_id||""}));
        // Lock chat input until session_verified
        const ci=document.getElementById("chatInput");
        if(ci){ ci.disabled=true; ci.placeholder="Syncing session…"; }
      }
    };
    ws.onclose=()=>{ wsReady=false; ws=null; pill("pillWs",false);
      usingFallback=true; setTimeout(connectWebSocket,4000); };
    ws.onerror=()=>{ wsReady=false; pill("pillWs",false); };
    ws.onmessage=e=>{ try{ handleWsMessage(JSON.parse(e.data)); }catch{} };
  }catch{ usingFallback=true; }
}
// v7.4D — helper: get the .bubble-body child of a bubble element.
// Needed because appendBubble now nests label + body inside the bubble div.
function _bubbleBody(el){ return el?.querySelector(".bubble-body")||el; }

function handleWsMessage(j){
  // WO-ARCH-07A PS2 — structured correction write-back from backend
  if(j.type==="correction_payload"){
    applyCorrectionPayload(j.parsed || {}, j.source_text || null);
    return;
  }
  if(j.type==="token"||j.type==="delta"){
    if(!currentAssistantBubble){
      currentAssistantBubble=appendBubble("ai","");
      setLoriState("drafting");
      // BUG-CHAT-AUTOSCROLL-01 (2026-05-05): force the view to the
      // newest bubble at the START of each AI reply, regardless of the
      // user's current scroll position. This is the once-per-turn pin
      // — after this initial force, the standard auto-scroll honors
      // user scroll-up. Without this, a narrator who scrolled up to
      // re-read a prior turn never sees Lori's new reply unless they
      // scroll back down on their own — they think the system froze.
      try { if (typeof window._scrollToLatest === "function") window._scrollToLatest(); } catch (_) {}
    }
    _bubbleBody(currentAssistantBubble).textContent+=(j.delta||j.token||"");
    // BUG-CHAT-AUTOSCROLL-01 (2026-05-05): scroll the OUTER container
    // (#crChatInner is the one with overflow-y:auto). Pre-fix this
    // line targeted #chatMessages which is the inner content wrapper
    // and isn't scrollable — so per-token scroll attempts were silent
    // no-ops, and the streaming reply visibly walked off-screen.
    if (typeof window._scrollChatToBottom === "function") {
      window._scrollChatToBottom();
    } else {
      var _crInner = document.getElementById("crChatInner");
      if (_crInner) _crInner.scrollTop = _crInner.scrollHeight;
    }
  }
  if(j.type==="error"){
    // Backend sent an error (e.g. model load failure, CUDA OOM)
    console.error("[WS] backend error:", j.message);
    const _isOOM = (j.message||"").toLowerCase().includes("out of memory") ||
                   (j.message||"").includes("CUDA_OOM");
    if(currentAssistantBubble){
      if(_isOOM){
        _bubbleBody(currentAssistantBubble).textContent=
          "GPU memory was full. VRAM has been freed — try sending your message again.";
      } else {
        _bubbleBody(currentAssistantBubble).textContent=
          "Chat error: " + (j.message||"unknown") + ". Try again.";
      }
    } else {
      // No bubble yet — create one for the error
      currentAssistantBubble = appendBubble("ai", _isOOM
        ? "GPU memory was full. VRAM has been freed — try sending your message again."
        : "Chat error: " + (j.message||"unknown") + ". Try again.");
    }
  }
  if(j.type==="done"){
    const text=j.final_text||(_bubbleBody(currentAssistantBubble)?.textContent||"");

    // WO-ARCH-07A — propagate turn_mode from backend response
    if (j.turn_mode) {
      state.session.lastTurnMode = j.turn_mode;
      state.session.turnMode = j.turn_mode;
      state.session.pendingCorrection = (j.turn_mode === TURN_MEMORY_ECHO);
    }

    onAssistantReply(text);
    if(text){
      setv("ivAnswer",text);
      captureState="captured";
      renderCaptureChip();
    }
    if(obitDraftType==="lori_pending") setObitDraftType("lori");
    setLoriState("ready");
    currentAssistantBubble=null;
    // BUG-CHAT-AUTOSCROLL-01 (2026-05-05): final scroll-to-bottom after
    // Lori's reply completes. Smooth-scrolling during streaming can
    // land at the OLD scrollHeight if more content arrives mid-scroll
    // (the "streaming chat gets stuck" classic). Re-trigger on done
    // so the final position lines up with the final content height.
    // Also covers the case where the user scrolled up mid-stream and
    // back down — _scrollChatToBottom honors _autoScroll so it won't
    // yank a user who deliberately stayed scrolled up.
    try {
      if (typeof window._scrollChatToBottom === "function") {
        window._scrollChatToBottom();
      }
    } catch (_) {}

    // WO-deferred: Flush queued extraction now that Lori has finished
    if (typeof _runDeferredInterviewExtraction === "function") {
      Promise.resolve(_runDeferredInterviewExtraction()).catch(function(err) {
        console.log("[extract] deferred flush after WS done failed:", err);
      });
    }
  }
  if(j.type==="session_verified"){
    // WO-2: Unlock chat input after session handshake confirmed
    const ci=document.getElementById("chatInput");
    if(ci){ ci.disabled=false; ci.placeholder="Type a message…"; }
    console.log("[WO-2] Session verified for person_id:", j.person_id);
  }
  if(j.type==="status") pill("pillWs", j.state==="connected"||j.state==="generating");
}

/* ═══════════════════════════════════════════════════════════════
   CHAT DISPLAY
═══════════════════════════════════════════════════════════════ */
function appendBubble(role,text){
  const w=document.getElementById("chatMessages");
  const d=document.createElement("div");
  d.className=`bubble bubble-${role}`;
  // v7.4D+N.1-03 — speaker label with narrator identity resolution.
  // sys bubbles (status messages) skip the label.
  if(role==="user"||role==="ai"){
    const label=document.createElement("div");
    label.className="bubble-speaker";
    if(role==="ai"){
      label.textContent="Lori";
    } else {
      // N.1-03: Resolve narrator display name from multiple sources
      let uName="";
      if(typeof state!=="undefined"){
        if(state.narratorUi && state.narratorUi.activeLabel) uName=state.narratorUi.activeLabel;
        if(!uName && state.person_id && state.narratorUi && state.narratorUi.peopleCache){
          const m=state.narratorUi.peopleCache.find(p=>(p.id||p.personId)===state.person_id);
          if(m) uName=m.display_name||m.name||m.fullName||"";
        }
        if(!uName && state.session && state.session.identityCapture && state.session.identityCapture.name){
          uName=state.session.identityCapture.name;
        }
      }
      label.textContent=uName||"You";
    }
    d.appendChild(label);
  }
  const body=document.createElement("div");
  body.className="bubble-body";
  body.textContent=text;
  d.appendChild(body);
  w.appendChild(d);
  // N.1-02 / BUG-CHAT-AUTOSCROLL-01 (2026-05-05): use the FocusCanvas
  // scroll manager when available; otherwise scroll the OUTER
  // container (#crChatInner — the one with overflow-y:auto). Pre-fix
  // the fallback set scrollTop on `w` (#chatMessages, the INNER
  // content wrapper which isn't scrollable), so when scroll
  // management hadn't initialized yet the auto-scroll silently
  // no-op'd and new bubbles vanished below the fold.
  if(typeof window._scrollChatToBottom==="function"){
    window._scrollChatToBottom();
  } else {
    var _crInner = document.getElementById("crChatInner");
    if (_crInner) {
      _crInner.scrollTop = _crInner.scrollHeight;
    } else {
      // Last-resort fallback — preserve legacy behavior for
      // operator-side surfaces that don't have crChatInner.
      w.scrollTop = w.scrollHeight;
    }
  }
  return d;
}
function sysBubble(text){ return appendBubble("sys",text); }
function clearChat(){ document.getElementById("chatMessages").innerHTML=""; }

/* ═══════════════════════════════════════════════════════════════
   TTS
═══════════════════════════════════════════════════════════════ */

// Chrome blocks audio until a real user gesture has occurred.
// We keep ONE persistent Audio element, unlock it on first gesture,
// then reuse it for every TTS chunk — the element stays whitelisted.
let _ttsAudio = null;
let _audioUnlocked = false;

// v7.4D — STT/TTS feedback-loop guard.
// True while Lori's TTS is actively playing. Recognition results and
// auto-restarts are suppressed whenever this flag is set.
let isLoriSpeaking = false;

// WO-11E: TTS abort mechanism for trainer narration stop
let _ttsAbortRequested = false;
let _ttsCurrentSource = null; // current WebAudio BufferSource for mid-chunk abort

/** WO-11E: Immediately stop all queued and playing TTS.
 *  Used by trainer narration to halt speech on step change or trainer exit.
 *  Safe to call at any time — no-ops gracefully if nothing is playing. */
function stopAllTts() {
  _ttsAbortRequested = true;
  ttsQueue.length = 0;
  if (_ttsCurrentSource) {
    try { _ttsCurrentSource.stop(); } catch(_){}
    _ttsCurrentSource = null;
  }
  if (_ttsAudio) {
    try { _ttsAudio.pause(); _ttsAudio.currentTime = 0; } catch(_){}
  }
  console.log("[WO-11E] stopAllTts() — queue cleared, playback stopped");
}
window._wo11eStopTts = stopAllTts;

function unlockAudio(){
  if(_audioUnlocked) return;

  // WO-10K: Canonical Web Audio API unlock pattern — create AudioContext,
  // resume it, and play a 1-sample silent buffer via BufferSource. This is
  // the most reliable way to satisfy Chrome's autoplay policy and works
  // even in hidden/background tabs (which break HTMLAudioElement.play()).
  try {
    const ctx = window._lvAudioCtx || new (window.AudioContext || window.webkitAudioContext)();
    window._lvAudioCtx = ctx;
    if (ctx.state === "suspended") ctx.resume().catch(()=>{});
    // Play a 1-sample silent buffer to fully whitelist the context.
    const silentBuf = ctx.createBuffer(1, 1, 22050);
    const src = ctx.createBufferSource();
    src.buffer = silentBuf;
    src.connect(ctx.destination);
    src.start(0);
    _audioUnlocked = true;
    console.log("[TTS] AudioContext unlocked via user gesture (state: " + ctx.state + ")");
  } catch(e){
    console.warn("[TTS] AudioContext unlock failed: " + (e && e.message || e));
  }

  // Also keep a persistent HTMLAudioElement as fallback path.
  try {
    _ttsAudio = new Audio();
    _ttsAudio.preload = "auto";
  } catch(_){}
}

// WO-10K: Global first-interaction listener — unlock audio on ANY user click/tap/key.
// This ensures TTS works even if the user's first action isn't Send or Mic.
(function(){
  function _globalUnlock(){
    unlockAudio();
    document.removeEventListener("click", _globalUnlock, true);
    document.removeEventListener("touchstart", _globalUnlock, true);
    document.removeEventListener("keydown", _globalUnlock, true);
  }
  document.addEventListener("click", _globalUnlock, true);
  document.addEventListener("touchstart", _globalUnlock, true);
  document.addEventListener("keydown", _globalUnlock, true);
})();

// Strip markdown formatting so TTS doesn't read "asterisk asterisk" etc.
function _stripMarkdownForTts(text){
  return text
    .replace(/#{1,6}\s+/g, "")                       // ## headings
    .replace(/\*\*(.+?)\*\*/g, "$1")                  // **bold**
    .replace(/\*(.+?)\*/g, "$1")                      // *italic*
    .replace(/__(.+?)__/g, "$1")                      // __bold__
    .replace(/_(.+?)_/g, "$1")                        // _italic_
    .replace(/`{1,3}[^`\n]*`{1,3}/g, "")             // `code`
    .replace(/^\s*[-*+]\s+/gm, "")                    // - bullet items
    .replace(/^\s*\d+\.\s+/gm, "")                    // 1. numbered list
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")          // [text](url)
    .replace(/\n{2,}/g, ". ")                         // paragraph break → brief pause
    .replace(/\n/g, " ")                              // single newline → space
    .replace(/\s{2,}/g, " ")
    .trim();
}

// Split cleaned text into ≤1000-char chunks at sentence boundaries.
// WO-11E-HL: Raised from 400 to 1000. Lori's trainer intro runs ~700 chars;
// at 1000 the entire intro fits in a single TTS request, eliminating
// the mid-sentence pause caused by inter-chunk fetch latency.
function _splitIntoTtsChunks(text, maxLen=1000){
  const sentences = text.match(/[^.!?]+[.!?]+\s*/g) || [text];
  const chunks = [];
  let current = "";
  for(const s of sentences){
    if((current+s).length > maxLen){
      if(current.trim()) chunks.push(current.trim());
      current = s;
    } else {
      current += s;
    }
  }
  if(current.trim()) chunks.push(current.trim());
  return chunks.length ? chunks : [text.slice(0, maxLen)];
}

function enqueueTts(text){
  // WO-11E: Clear stale abort flag from a previous stopAllTts() call.
  // Without this, a stop→enqueue sequence leaves the flag set and the
  // new drainTts() immediately aborts.
  _ttsAbortRequested = false;
  const cleaned = _stripMarkdownForTts(text);
  _splitIntoTtsChunks(cleaned).forEach(c => ttsQueue.push(c));
  if(!ttsBusy) drainTts();
}
async function drainTts(){
  ttsBusy=true;
  // v7.4D — stop mic and mark Lori as speaking before any audio plays.
  // This prevents the STT engine from transcribing Lori's own voice.
  isLoriSpeaking=true;
  if(isRecording) stopRecording();
  // WO-AUDIO-NARRATOR-ONLY-01: TTS gate ON.  Drops any in-progress
  // narrator-audio segment without uploading (Lori-audio defense).
  if (typeof window.lvNarratorAudioRecorder === "object" && window.lvNarratorAudioRecorder.gate) {
    try { window.lvNarratorAudioRecorder.gate(true); } catch (e) { console.warn("[narrator-audio] gate(true) threw:", e); }
  }
  // WO-MIC-UI-02A: Show WAIT state so narrator knows Lori has the floor.
  // stopRecording() sets MIC OFF, but we override to WAIT while Lori speaks.
  _setMicVisual("wait");
  try {
    while(ttsQueue.length){
      // WO-11E: Check abort flag between chunks (trainer stop)
      if (_ttsAbortRequested) { console.log("[WO-11E] TTS abort — breaking drain loop"); break; }
      const chunk=ttsQueue.shift();
      try{
        const r=await fetch(TTS_ORIG+"/api/tts/speak_stream",{method:"POST",headers:ctype(),
          body:JSON.stringify({text:chunk,voice:"p335"})});
        if(!r.ok) continue;
        // Server returns NDJSON: {"wav_b64":"<base64 WAV>"}
        const ndjson = await r.text();
        for(const line of ndjson.split("\n")){
          const t=line.trim(); if(!t) continue;
          let obj; try{ obj=JSON.parse(t); }catch{ continue; }
          if(!obj.wav_b64) continue;
          const raw=atob(obj.wav_b64);
          const bytes=new Uint8Array(raw.length);
          for(let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);

          // WO-10K: Use Web Audio API (AudioContext + BufferSource) instead of
          // HTMLAudioElement. HTMLAudioElement.play() hangs on blob URLs in hidden
          // tabs and has flaky autoplay whitelisting. AudioContext is already
          // running (unlocked by first user gesture) and has reliable onended.
          let playedViaWebAudio = false;
          if (window._lvAudioCtx) {
            try {
              if (window._lvAudioCtx.state === "suspended") {
                try { await window._lvAudioCtx.resume(); } catch(_){}
              }
              // decodeAudioData mutates the buffer, so pass a copy
              const audioBuffer = await window._lvAudioCtx.decodeAudioData(bytes.buffer.slice(0));
              await new Promise(res => {
                const src = window._lvAudioCtx.createBufferSource();
                _ttsCurrentSource = src; // WO-11E: store for abort
                src.buffer = audioBuffer;
                src.connect(window._lvAudioCtx.destination);
                // Safety timeout: duration + 2s margin
                const safetyMs = Math.ceil(audioBuffer.duration * 1000) + 2000;
                const _playTimeout = setTimeout(() => {
                  console.warn("[TTS] WebAudio playback timed out after " + safetyMs + "ms — forcing continue");
                  try { src.stop(); } catch(_){}
                  res();
                }, safetyMs);
                src.onended = () => { clearTimeout(_playTimeout); res(); };
                try {
                  src.start(0);
                  // WO-11E-HL: Signal the exact moment audio begins playing.
                  // The highlight sequencer waits for this instead of guessing.
                  if (typeof window._wo11eTtsPlaybackStarted === "function") {
                    try { window._wo11eTtsPlaybackStarted(); } catch(_){}
                    window._wo11eTtsPlaybackStarted = null; // fire only once per narration
                  }
                } catch(e) {
                  clearTimeout(_playTimeout);
                  console.warn("[TTS] WebAudio start failed: " + e.message);
                  res();
                }
              });
              playedViaWebAudio = true;
            } catch(e) {
              console.warn("[TTS] WebAudio decode/play failed, falling back to HTMLAudio: " + (e && e.message || e));
            }
          }

          // Fallback: HTMLAudioElement (only if WebAudio path didn't run)
          if (!playedViaWebAudio) {
            const blob=new Blob([bytes],{type:"audio/wav"});
            const url=URL.createObjectURL(blob);
            const a=_ttsAudio||new Audio();
            a.src=url;
            if(!_audioUnlocked){
              console.warn("[TTS] Audio not unlocked yet — skipping chunk (waiting for user gesture)");
              URL.revokeObjectURL(url);
              continue;
            }
            // WO-10J/K: Timeout safeguard — prevents isLoriSpeaking from getting
            // stuck if audio.play() hangs for any reason (network, decode, edge case).
            await new Promise(res=>{
              const _playTimeout=setTimeout(()=>{
                console.warn("[TTS] HTMLAudio playback timed out after 15s — forcing continue");
                try{ a.pause(); a.currentTime=0; }catch(_){}
                res();
              }, 15000);
              const _done=()=>{ clearTimeout(_playTimeout); res(); };
              a.onended=_done;
              a.onerror=_done;
              a.play().then(()=>{
                // WO-11E-HL: Signal playback started (HTMLAudio fallback path)
                if (typeof window._wo11eTtsPlaybackStarted === "function") {
                  try { window._wo11eTtsPlaybackStarted(); } catch(_){}
                  window._wo11eTtsPlaybackStarted = null;
                }
              }).catch(_done);
            });
            URL.revokeObjectURL(url);
          }
        }
      }catch{}
    }
  } finally {
    // Step 3 hardening — always clear both flags on exit, even if an unexpected
    // exception escapes the inner loop. Without this, isLoriSpeaking could be
    // stuck true permanently, silently suppressing all STT forever.
    isLoriSpeaking=false;
    ttsBusy=false;
    // WO-AUDIO-NARRATOR-ONLY-01: TTS gate OFF.  Recorder will wait
    // 700ms before clearing the gate (audible-but-flag-cleared edge).
    if (typeof window.lvNarratorAudioRecorder === "object" && window.lvNarratorAudioRecorder.gate) {
      try { window.lvNarratorAudioRecorder.gate(false); } catch (e) { console.warn("[narrator-audio] gate(false) threw:", e); }
    }
    // WO-11E: Reset abort state and clear source ref
    _ttsAbortRequested = false;
    _ttsCurrentSource = null;
    // WO-MIC-UI-02A: Clear WAIT visual now that Lori is done speaking.
    // If WO-10H auto-starts recording below, startRecording() will set LISTENING.
    _setMicVisual(false);

    // WO-11E: Trainer narration completion callback
    if (typeof window._wo11eTtsFinishedCallback === "function") {
      try { window._wo11eTtsFinishedCallback(); } catch(_){}
      window._wo11eTtsFinishedCallback = null;
    }

    // WO-10H: Record TTS finish time and transition narrator turn-claim if pending.
    if (state.narratorTurn) {
      state.narratorTurn.ttsFinishedAt = Date.now();
      if (state.narratorTurn.state === "awaiting_tts_end") {
        _wo10hTransitionToArmed();
      }
    }
  }
}

/* ═══════════════════════════════════════════════════════════════
   VOICE INPUT
   ─────────────────────────────────────────────────────────────
   STT/TTS FEEDBACK-LOOP GUARD CONTRACT (v7.4D / Step 3 hardened)
   ─────────────────────────────────────────────────────────────
   Problem: the Web Speech API can transcribe Lori's own TTS audio
   through the speaker, producing feedback-loop ghost transcripts.

   Guard: isLoriSpeaking (bool, declared in TTS section above)
   ├─ Set TRUE  — immediately before drainTts() starts any audio.
   ├─ Set FALSE — in a finally{} block after all audio is drained,
   │              guaranteeing it is cleared even if an exception
   │              escapes the inner chunk loop.
   ├─ recognition.onresult — returns early (discards result) when
   │  isLoriSpeaking is true. Emits console.warn for diagnostics.
   └─ recognition.onend   — only auto-restarts when
      isRecording === true AND isLoriSpeaking === false.

   Invariant: isLoriSpeaking must NEVER be left stuck at true.
   The finally{} block in drainTts() is the enforced safety net.
═══════════════════════════════════════════════════════════════ */
function toggleRecording(){
  // WO-11C: Block mic while trainer mode is active.
  if (_wo11cIsTrainerActive()) {
    console.log("[WO-11C] toggleRecording() BLOCKED — trainer mode active");
    if (typeof sysBubble === "function") {
      sysBubble("Complete the trainer first, then we\u2019ll begin your interview.");
    }
    return;
  }
  // WO-MIC-UI-02A: Targeted debug logging — mic click entry point
  console.log("[WO-MIC-UI-02A] toggleRecording() — isRecording:", isRecording,
    "isLoriSpeaking:", isLoriSpeaking,
    "FocusCanvas open:", (typeof FocusCanvas !== "undefined" && FocusCanvas.isOpen && FocusCanvas.isOpen()));
  unlockAudio();
  // WO-10H: If Lori is still speaking TTS, claim next turn instead of starting immediately.
  if (isLoriSpeaking && !isRecording) {
    _wo10hClaimTurn();
    return;
  }
  isRecording?stopRecording():startRecording();
}
// HTML button calls toggleMic() — alias to toggleRecording.
function toggleMic(){ toggleRecording(); }
// Normalise spoken punctuation words produced by Web Speech API.
// Runs on each final transcript chunk before appending to the input box.
function _normalisePunctuation(t){
  return t
    .replace(/\bperiod\b/gi,            ".")
    .replace(/\bfull stop\b/gi,         ".")
    .replace(/\bcomma\b/gi,             ",")
    .replace(/\bquestion mark\b/gi,     "?")
    .replace(/\bexclamation (point|mark)\b/gi, "!")
    .replace(/\bsemicolon\b/gi,         ";")
    .replace(/\bcolon\b/gi,             ":")
    .replace(/\bdash\b/gi,              " — ")
    .replace(/\bhyphen\b/gi,            "-")
    .replace(/\bellipsis\b/gi,          "...")
    .replace(/\bdot dot dot\b/gi,       "...")
    .replace(/\bnew (line|paragraph)\b/gi, "\n")
    .replace(/\bopen (paren|parenthesis)\b/gi,  "(")
    .replace(/\bclose (paren|parenthesis)\b/gi, ")")
    .replace(/\bopen quote\b/gi,        "\u201C")
    .replace(/\bclose quote\b/gi,       "\u201D")
    // Tidy up any double-spaces left by replacements
    .replace(/ {2,}/g, " ")
    .trim();
}

// v7.4D — Voice send commands. Any of these exact phrases (case-insensitive,
// trimmed) will trigger Send instead of being typed into the input box.
const _SEND_COMMANDS = new Set(["send","send it","okay send","ok send","go ahead","send message"]);
// WO-9: Voice send shortcut disabled by default — elderly narrators trigger it accidentally.
// Set window._wo9VoiceSendEnabled = true in console or config to re-enable.
let _wo9VoiceSendEnabled = window._wo9VoiceSendEnabled || false;

function _ensureRecognition(){
  if(recognition) return recognition;
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){ sysBubble("Voice input not supported in this browser."); return null; }
  recognition=new SR(); recognition.continuous=true; recognition.interimResults=true;
  recognition.onresult=e=>{
    // v7.4D — if Lori is speaking, discard all recognition results entirely.
    // This is the primary guard against self-transcription.
    if(isLoriSpeaking){
      // Step 3 diagnostic — visible in DevTools during testing.
      console.warn("[STT guard] Recognition fired while isLoriSpeaking=true — result discarded.");
      return;
    }
    let fin=""; for(let i=e.resultIndex;i<e.results.length;i++) if(e.results[i].isFinal) fin+=e.results[i][0].transcript;
    if(!fin) return;
    const trimmed=fin.trim().toLowerCase();
    // v7.4D — check for voice send command before appending to input.
    // WO-9: Only if voice send is explicitly enabled
    if(_wo9VoiceSendEnabled && _SEND_COMMANDS.has(trimmed)){
      stopRecording();
      sendUserMessage();
      return;
    }
    const _normalized02a = _normalisePunctuation(fin);
    setv("chatInput",getv("chatInput")+_normalized02a);
    // WO-MIC-UI-02A: Confirm text reaches main surface
    console.log("[WO-MIC-UI-02A] Final text → #chatInput:", _normalized02a.slice(0, 60));
    // WO-STT-LIVE-02 (#99) — stage the final transcript so the extraction
    // payload builder can attach source="web_speech" + confidence +
    // fragile-fact flags. No-op if transcript-guard didn't load.
    try {
      if (window.TranscriptGuard && typeof window.TranscriptGuard.populateFromRecognition === "function") {
        window.TranscriptGuard.populateFromRecognition(e, {
          normalize: _normalisePunctuation,
          turnId:    (state.interview && state.interview.session_id) ? ("turn-" + Date.now()) : null,
        });
      }
    } catch (_guardErr) {
      console.warn("[STT-guard] stage failed:", _guardErr && _guardErr.message);
    }
  };
  // v7.4D — only auto-restart if user explicitly left mic on AND Lori is not speaking.
  // This prevents the engine from restarting mid-TTS and catching Lori's audio.
  recognition.onend=()=>{ if(isRecording && !isLoriSpeaking){ try{ recognition.start(); }catch(e){ console.warn("[STT] auto-restart failed:",e.message); } } };
  // WO-07: no-speech error cascade mitigation for elderly narrators.
  // Web Speech API fires no-speech every ~5s during silence (Kent's natural pauses).
  // Counter tracks consecutive no-speech events; backoff reduces log spam.
  let _noSpeechCount = 0;
  const _NO_SPEECH_LOG_INTERVAL = 5;  // Only log every Nth no-speech event
  // WO-MIC-UI-02A: Raised from 10 to 20 — Kent and Janice pause naturally for
  // 30-90 seconds while thinking. 10 events (~50s) was too aggressive.
  const _NO_SPEECH_GENTLE_THRESHOLD = 20;  // After 20, show gentle nudge once

  recognition.onresult = (function(origOnResult) {
    return function(e) {
      _noSpeechCount = 0;  // Reset on any speech detected
      return origOnResult(e);
    };
  })(recognition.onresult);

  // v8.0 — error handler: surface recognition failures to the user.
  recognition.onerror=e=>{
    if(e.error==="not-allowed"){
      console.error("[STT] recognition error:",e.error,e.message);
      stopRecording();
      // WO-MIC-UI-02A: Show persistent BLOCKED visual state
      _setMicVisual("blocked");
      sysBubble("🎤 Microphone access was denied. Please allow microphone in your browser settings and try again.");
    } else if(e.error==="no-speech"){
      // WO-07: Suppress cascade — only log periodically, gentle nudge after threshold
      _noSpeechCount++;
      if(_noSpeechCount % _NO_SPEECH_LOG_INTERVAL === 1){
        console.log("[STT] no speech detected (count: " + _noSpeechCount + ") — waiting…");
      }
      if(_noSpeechCount === _NO_SPEECH_GENTLE_THRESHOLD && typeof sysBubble === "function"){
        // WO-MIC-UI-02A: Calmer message — Kent/Janice may be gathering thoughts
        sysBubble("🎤 The microphone is still on — no rush, speak whenever you're ready.");
      }
    } else if(e.error==="network"){
      console.error("[STT] recognition error:",e.error,e.message);
      stopRecording();
      sysBubble("🎤 Speech recognition requires an internet connection (Chrome sends audio to Google's servers). Please check your connection.");
    } else if(e.error==="service-not-allowed"){
      stopRecording();
      sysBubble("🎤 Speech recognition service is not available. This may happen on non-HTTPS pages or in some browser configurations.");
    } else if(e.error==="aborted"){
      // User or code called stop() — normal, no action needed
    } else {
      sysBubble("🎤 Speech recognition error: "+e.error);
    }
  };
  return recognition;
}
function startRecording(){
  // WO-11C: Block mic start while trainer mode is active.
  if (_wo11cIsTrainerActive()) {
    console.log("[WO-11C] startRecording() BLOCKED — trainer mode active");
    return;
  }
  const r=_ensureRecognition(); if(!r) return;
  // BUG-219: snapshot any text the narrator already typed BEFORE we
  // start collecting STT chunks.  WO-8 voice-turn accumulator joins
  // _wo8VoiceTurnChunks into chatInput; without a snapshot of the
  // pre-mic draft, that overwrites typed text.  We prepend this
  // snapshot when rendering the chunks.  Cleared on send / finalize.
  try {
    const _existingDraft = (typeof getv === "function" ? getv("chatInput") : "") || "";
    // Only capture if there's something meaningful to preserve AND we're
    // not already in a voice-turn (re-arm should not overwrite the snapshot).
    if (_existingDraft.trim().length > 0 && !_wo8LongTurnMode && _wo8VoiceTurnChunks.length === 0) {
      _wo8PreMicDraft = _existingDraft;
      console.log("[BUG-219] pre-mic draft snapshot: " + JSON.stringify(_existingDraft.slice(0, 60)));
    }
  } catch (_) {}
  try{
    r.start(); isRecording=true;
    _setMicVisual(true);
    setLoriState("listening");
    console.log("[STT] recognition started");
    // WO-AUDIO-NARRATOR-ONLY-01: arm audio segment alongside STT.
    // Recorder gates itself on isLoriSpeaking and recordVoice toggle;
    // a no-op when those are off.
    if (typeof window.lvNarratorAudioRecorder === "object" && window.lvNarratorAudioRecorder.start) {
      try { window.lvNarratorAudioRecorder.start(); } catch (e) { console.warn("[narrator-audio] start threw:", e); }
    }
  }catch(e){
    console.error("[STT] start() failed:",e.message);
    // "already started" — just update state
    if(e.message&&e.message.includes("already started")){
      isRecording=true; _setMicVisual(true); setLoriState("listening");
    } else {
      sysBubble("🎤 Could not start voice input: "+e.message);
    }
  }
}
function stopRecording(){
  isRecording=false;
  if(recognition){ try{ recognition.stop(); }catch(e){} }
  _setMicVisual(false);
  setLoriState("ready");
}
// v8.0 — mic button visual state. Adds/removes a CSS class instead of
// replacing innerHTML (which destroyed the SVG icon).
/* WO-MIC-UI-02A: Expanded mic visual states.
   States: true/"listening" (red pulse), false/"off" (grey), "wait" (amber),
           "blocked" (red static, no pulse).
   The label and button styling communicate clearly to elderly narrators what
   the mic is doing at all times. */
function _setMicVisual(active){
  const btn=document.getElementById("btnMic");
  if(!btn) return;
  const label=document.getElementById("btnMicLabel");

  // Clear all mic state classes first
  btn.classList.remove("mic-active", "mic-wait", "mic-blocked");
  if(label) label.classList.remove("mic-label-active", "mic-label-wait", "mic-label-blocked");

  if(active === "wait"){
    // WAIT — LORI IS SPEAKING: amber glow, narrator knows Lori has the floor
    btn.classList.add("mic-wait");
    btn.title="Lori is speaking — mic will resume when she finishes";
    if(label){ label.textContent="WAIT — LORI IS SPEAKING"; label.classList.add("mic-label-wait"); }
    console.log("[WO-MIC-UI-02A] Mic visual → WAIT (Lori speaking)");
  } else if(active === "blocked"){
    // BLOCKED — permission denied or hardware unavailable
    btn.classList.add("mic-blocked");
    btn.title="Microphone is blocked — check browser permissions";
    if(label){ label.textContent="MIC BLOCKED"; label.classList.add("mic-label-blocked"); }
    console.log("[WO-MIC-UI-02A] Mic visual → BLOCKED");
  } else if(active){
    btn.classList.add("mic-active");
    btn.title="Microphone is on — click to stop";
    if(label){ label.textContent="LISTENING"; label.classList.add("mic-label-active"); }
  } else {
    btn.title="Click to toggle microphone";
    if(label){ label.textContent="MIC OFF"; }
  }
}

/* ═══════════════════════════════════════════════════════════════
   v7.1 — TIMELINE SPINE INITIALIZER
   Called from saveProfile() when DOB + birthplace are present.
   Builds the life-period scaffold from date of birth.

   WO-CANONICAL-LIFE-SPINE-01 Step 3d: TIMELINE_ORDER and ERA_AGE_MAP
   are now derived from the canonical lv-eras.js registry at module
   init time, so the historical-era taxonomy lives in exactly one
   place. Each period stamps BOTH era_id (canonical machine key) and
   label (also canonical) so renderRoadmap and any other p.label
   reader gets canonical strings. The "today" bucket from LV_ERAS is
   filtered out — Today is a current-life bucket selected explicitly
   by the narrator/operator, not derived from birth-year math (matches
   eraIdFromAge in lv-eras.js).

   Defensive fallback array preserves the original 6-row scaffold
   byte-stable when lv-eras.js hasn't loaded yet.
═══════════════════════════════════════════════════════════════ */
const _CANONICAL_HISTORICAL_ERAS = (function () {
  var rows = (window.LorevoxEras && Array.isArray(window.LorevoxEras.LV_ERAS))
    ? window.LorevoxEras.LV_ERAS
    : null;
  if (rows) {
    return rows
      .filter(function (e) { return e.era_id !== "today" && e.ageStart != null; })
      .map(function (e) {
        return { era_id: e.era_id, ageStart: e.ageStart, ageEnd: e.ageEnd };
      });
  }
  return [
    { era_id: "earliest_years",     ageStart: 0,  ageEnd: 5    },
    { era_id: "early_school_years", ageStart: 6,  ageEnd: 12   },
    { era_id: "adolescence",        ageStart: 13, ageEnd: 17   },
    { era_id: "coming_of_age",      ageStart: 18, ageEnd: 30   },
    { era_id: "building_years",     ageStart: 31, ageEnd: 59   },
    { era_id: "later_years",        ageStart: 60, ageEnd: null },
  ];
})();

const TIMELINE_ORDER = _CANONICAL_HISTORICAL_ERAS.map(function (e) { return e.era_id; });

const ERA_AGE_MAP = (function () {
  var m = {};
  _CANONICAL_HISTORICAL_ERAS.forEach(function (e) {
    m[e.era_id] = { start: e.ageStart, end: e.ageEnd };
  });
  return m;
})();

function initTimelineSpine() {
  const b = state.profile?.basics || {};
  if (!b.dob || !b.pob) return;
  const birthYear = parseInt(String(b.dob).slice(0, 4), 10);
  if (Number.isNaN(birthYear)) return;

  const periods = TIMELINE_ORDER.map(eraId => {
    const ages = ERA_AGE_MAP[eraId];
    return {
      // Both fields hold the canonical era_id. era_id is the explicit
      // machine key; label is preserved for backward-compat with any
      // caller still reading period.label (renderRoadmap canonicalizes
      // p.era_id || p.label so either works).
      era_id: eraId,
      label:  eraId,
      start_year: birthYear + ages.start,
      end_year:   ages.end !== null ? birthYear + ages.end : null,
      is_approximate: true,
      places: eraId === "earliest_years" ? [b.pob] : [],
      people: [],
      notes:  eraId === "earliest_years" ? [`Born in ${b.pob}`] : [],
    };
  });

  state.timeline.spine     = { birth_date: b.dob, birth_place: b.pob, periods };
  state.timeline.seedReady = true;
  saveSpineLocal();

  // Advance pass engine to Pass 2A and default to first era
  setPass("pass2a");
  if (!getCurrentEra()) setEra(periods[0].era_id);
  setMode("open");

  // Sync UI
  update71RuntimeUI();
  renderRoadmap();
  renderTimeline();
  updateArchiveReadiness();
  // WO-PROVISIONAL-TRUTH-01 Phase C (2026-05-04):
  // Operator-tone status bubble retired from narrator surface by default.
  // Locked principle #3 (no system-tone narrator outputs) applies — "◉
  // Timeline spine initialized — Pass 2A (Timeline Walk) ready." reads
  // like a debug log, not a warm narrator-facing message. Re-enable for
  // dev observation by setting localStorage['LV_INLINE_OPERATOR_BUBBLES']
  // ='true' or window.LV_INLINE_OPERATOR_BUBBLES=true.
  if (window.LV_INLINE_OPERATOR_BUBBLES === true ||
      (typeof localStorage !== "undefined" && localStorage.getItem("LV_INLINE_OPERATOR_BUBBLES") === "true")) {
    sysBubble("◉ Timeline spine initialized — Pass 2A (Timeline Walk) ready.");
  }

  // WO-CR-01: Initialize chronology accordion after spine is ready
  if (typeof crInitAccordion === "function") {
    try { crInitAccordion(); } catch (_) {}
  }
}

/* ── v7.1 — update all runtime badge elements in the UI ──── */
function update71RuntimeUI() {
  const PASS_LABELS = {
    pass1:  "Pass 1",
    pass2a: "Pass 2A",
    pass2b: "Pass 2B",
  };
  const prettyEra  = (v) => v ? String(v).replaceAll("_"," ").replace(/\b\w/g, m => m.toUpperCase()) : "No era";
  const prettyMode = (v) => v ? String(v).replace(/\b\w/g, m => m.toUpperCase()) : "Open";

  const pass = getCurrentPass();
  const era  = getCurrentEra();
  const mode = getCurrentMode();
  const passLabel = PASS_LABELS[pass] || pass;
  const eraLabel  = prettyEra(era);
  const modeLabel = prettyMode(mode);

  // Top bar runtime pills (lori7.1.html)
  const setT = (id, txt) => { const el = document.getElementById(id); if (el) el.textContent = txt; };
  setT("topPassPill",  passLabel);
  setT("topEraPill",   eraLabel);
  setT("topModePill",  modeLabel);
  // Interview tab header
  setT("ivPassLabel",  `${passLabel}${pass === "pass2a" ? " — Timeline Spine" : pass === "pass2b" ? " — Narrative Depth" : " — Profile Seed"}`);
  setT("ivEraLabel",   eraLabel);
  setT("ivModeLabel",  modeLabel);
  setT("ivSectionLabel", `${passLabel} · Era: ${eraLabel} · Mode: ${modeLabel}`);
  // Lori panel state strip
  setT("loriPassPill", passLabel);
  setT("loriEraPill",  eraLabel);
  setT("loriModePill", modeLabel);

  // Seed badges
  const spineReady = !!state.timeline?.spine;
  const seedBadge  = document.getElementById("timelineSeedBadge71");
  if (seedBadge) {
    seedBadge.className   = spineReady ? "seed-badge" : "seed-badge pending";
    seedBadge.textContent = spineReady ? "◉ Timeline spine ready — Pass 2A available" : "◎ Profile seed in progress — complete identity anchors";
  }
  // Summary seed indicator
  const sumSeed = document.getElementById("summarySeed");
  if (sumSeed) sumSeed.classList.toggle("hidden", !spineReady);
}

/* ═══════════════════════════════════════════════════════════════
   WO-8 — TRANSCRIPT HISTORY, THREAD ANCHOR, VOICE TURN
           IMPROVEMENTS, AND RESUME LOGIC
   Kent Interaction Fixes: Voice Continuity, Transcript History,
   Resume, and Long-Turn Reliability.
═══════════════════════════════════════════════════════════════ */

/* ── WO-8 Phase 2: Transcript History ────────────────────────── */

/**
 * Load and display archived transcript history when a narrator is opened.
 * Replaces the blank chat area with prior conversation turns.
 * Each turn shows speaker label and timestamp.
 */
async function wo8LoadTranscriptHistory(pid) {
  if (!pid) return;
  try {
    const url = API.TRANSCRIPT_HISTORY(pid, "");
    const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) { console.log("[WO-8] No transcript history for", pid); return; }
    const data = await res.json();
    const events = data.events || [];
    if (!events.length) { console.log("[WO-8] Transcript empty for", pid); return; }

    const chatEl = document.getElementById("chatMessages");
    if (!chatEl) return;

    // Clear existing bubbles before loading history
    chatEl.innerHTML = "";

    // Add session divider
    const divider = document.createElement("div");
    divider.className = "wo8-session-divider";
    divider.innerHTML = '<span class="wo8-divider-label">Prior conversation</span>';
    chatEl.appendChild(divider);

    // Render each archived turn (WO-9: filter/collapse system messages)
    events.forEach(ev => {
      const role = (ev.role || "").toLowerCase();
      const content = (ev.content || "").trim();
      if (!content) return;

      // WO-9: Classify system messages and skip internal ones
      const isSystemMsg = content.startsWith("[SYSTEM:") || role === "system";
      if (isSystemMsg) {
        // Skip internal system prompts — don't show to narrator
        // But log for debugging
        console.log("[WO-9] Skipping system message in transcript render:", content.slice(0, 60));
        return;
      }

      const bubbleRole = role === "assistant" ? "ai" : role === "user" ? "user" : "sys";
      const bubble = appendBubble(bubbleRole, content);

      // Add timestamp badge if available
      if (ev.ts && bubble) {
        try {
          const dt = new Date(ev.ts);
          const timeStr = dt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
          const dateStr = dt.toLocaleDateString([], { month: "short", day: "numeric" });
          const tsBadge = document.createElement("div");
          tsBadge.className = "wo8-timestamp";
          tsBadge.textContent = `${dateStr} ${timeStr}`;
          bubble.appendChild(tsBadge);
        } catch (_) {}
      }
    });

    // Add a separator before new conversation
    const newDiv = document.createElement("div");
    newDiv.className = "wo8-session-divider";
    newDiv.innerHTML = '<span class="wo8-divider-label">Continuing</span>';
    chatEl.appendChild(newDiv);

    // Scroll to bottom
    if (typeof window._scrollChatToBottom === "function") {
      window._scrollChatToBottom();
    } else {
      chatEl.scrollTop = chatEl.scrollHeight;
    }

    console.log("[WO-8] Loaded", events.length, "transcript events for", pid.slice(0, 8));
  } catch (e) {
    console.log("[WO-8] Transcript history load failed:", e.message);
  }
}

/**
 * Export transcript for current narrator.
 * Opens download link for .txt or .json format.
 */
function wo8ExportTranscript(format, allSessions) {
  const pid = state.person_id;
  if (!pid) { sysBubble("No narrator selected."); return; }
  let url;
  if (allSessions) {
    // WO-9: Export all sessions combined
    url = format === "json"
      ? API.TRANSCRIPT_EXPORT_ALL_JSON(pid)
      : API.TRANSCRIPT_EXPORT_ALL_TXT(pid);
  } else {
    url = format === "json"
      ? API.TRANSCRIPT_EXPORT_JSON(pid, "")
      : API.TRANSCRIPT_EXPORT_TXT(pid, "");
  }
  window.open(url, "_blank");
}
window.wo8ExportTranscript = wo8ExportTranscript;

/* ═══════════════════════════════════════════════════════════════
   WO-10 Phase 6: Transcript Viewer
   Phase 7: Resume Preview
   Phase 8: Session Timeline
   Rendered in #wo10TranscriptPopover tabs.
═══════════════════════════════════════════════════════════════ */

let _wo10ShowSystem = false;

function wo10SwitchTab(tabName) {
  document.querySelectorAll(".wo10-tab").forEach(t => t.classList.toggle("active", t.dataset.wo10Tab === tabName));
  document.getElementById("wo10TabTranscript").style.display = tabName === "transcript" ? "" : "none";
  document.getElementById("wo10TabResume").style.display = tabName === "resume" ? "" : "none";
  document.getElementById("wo10TabTimeline").style.display = tabName === "timeline" ? "" : "none";
  // Load data on tab switch
  if (tabName === "transcript") wo10LoadTranscriptViewer();
  if (tabName === "resume") wo10LoadResumePreview();
  if (tabName === "timeline") wo10LoadSessionTimeline();
}
window.wo10SwitchTab = wo10SwitchTab;

function wo10ToggleSystemMessages() {
  _wo10ShowSystem = !_wo10ShowSystem;
  const btn = document.getElementById("wo10ToggleSystem");
  if (btn) btn.textContent = _wo10ShowSystem ? "Hide System" : "Show System";
  document.querySelectorAll(".wo10-event.system").forEach(el => {
    el.classList.toggle("show-system", _wo10ShowSystem);
  });
}
window.wo10ToggleSystemMessages = wo10ToggleSystemMessages;

function wo10ClassifyEvent(evt) {
  const text = String(evt?.content || "");
  const role = (evt?.role || "").toLowerCase();
  if (text.startsWith("[SYSTEM:") || role === "system") return "system";
  if (role === "assistant") return "lori";
  return "narrator";
}

async function wo10LoadTranscriptViewer() {
  const pid = state.person_id;
  const container = document.getElementById("wo10TranscriptContent");
  if (!container || !pid) {
    if (container) container.innerHTML = '<p style="color:#64748b">No narrator selected.</p>';
    return;
  }
  container.innerHTML = '<p style="color:#64748b">Loading transcript...</p>';

  try {
    // Load sessions list first
    const sessRes = await fetch(API.TRANSCRIPT_SESSIONS(pid), { signal: AbortSignal.timeout(8000) });
    if (!sessRes.ok) throw new Error("No sessions");
    const sessData = await sessRes.json();
    const sessions = (sessData.sessions || []).sort((a, b) => (a.started_at || "").localeCompare(b.started_at || ""));

    // Load last 2 sessions for display
    const recentSessions = sessions.slice(-2);
    let html = "";

    for (const sess of recentSessions) {
      const sid = sess.session_id;
      const evtRes = await fetch(API.TRANSCRIPT_HISTORY(pid, sid), { signal: AbortSignal.timeout(8000) });
      if (!evtRes.ok) continue;
      const evtData = await evtRes.json();
      const events = evtData.events || [];

      // Session divider
      const dateStr = sess.started_at ? new Date(sess.started_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "";
      html += `<div class="wo10-divider">${sess.title || "Session"} ${dateStr ? " — " + dateStr : ""}</div>`;

      for (const evt of events) {
        const cls = wo10ClassifyEvent(evt);
        const roleName = cls === "narrator" ? (state.profile?.basics?.preferred || "Narrator")
          : cls === "lori" ? "Lori" : "System";
        let tsStr = "";
        if (evt.ts) {
          try { tsStr = new Date(evt.ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
          catch (_) {}
        }
        const content = (evt.content || "").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        html += `<div class="wo10-event ${cls}${_wo10ShowSystem && cls === "system" ? " show-system" : ""}">`;
        html += `<div class="wo10-event-role">${roleName}${tsStr ? `<span class="wo10-event-ts">${tsStr}</span>` : ""}</div>`;
        html += `<div class="wo10-event-text">${content}</div></div>`;
      }
    }

    container.innerHTML = html || '<p style="color:#64748b">No transcript events found.</p>';
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171">Failed to load transcript: ${e.message}</p>`;
  }
}

async function wo10LoadResumePreview() {
  const pid = state.person_id;
  const container = document.getElementById("wo10ResumeContent");
  if (!container || !pid) {
    if (container) container.innerHTML = '<p style="color:#64748b">No narrator selected.</p>';
    return;
  }
  container.innerHTML = '<p style="color:#64748b">Loading resume preview...</p>';

  try {
    const res = await fetch(API.RESUME_PREVIEW(pid), { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error("No preview data");
    const data = await res.json();

    const conf = data.confidence || {};
    const confLevel = conf.level || "low";
    const confScore = ((conf.score || 0) * 100).toFixed(0);
    const thread = data.selected_thread;
    const threads = data.all_threads || [];
    const scoredItems = data.scored_items || [];
    const recentTurns = data.recent_turns || [];
    const narName = state.profile?.basics?.preferred || "Narrator";

    let html = "";

    // Confidence card
    html += '<div class="wo10-resume-card">';
    html += `<div class="wo10-resume-label">Resume Confidence</div>`;
    html += `<span class="wo10-confidence ${confLevel}">${confLevel.toUpperCase()} (${confScore}%)</span>`;
    if (conf.reasons) {
      html += `<div style="margin-top:8px;font-size:12px;color:#64748b">${conf.reasons.join(", ")}</div>`;
    }
    html += '</div>';

    // Selected thread
    if (thread) {
      html += '<div class="wo10-resume-card">';
      html += '<div class="wo10-resume-label">Selected Thread</div>';
      html += `<div class="wo10-resume-value">${thread.topic_label || "General"}</div>`;
      if (thread.subtopic_label) html += `<div style="font-size:12px;color:#94a3b8">Subtopic: ${thread.subtopic_label}</div>`;
      if (thread.related_era) html += `<div style="font-size:12px;color:#94a3b8">Era: ${thread.related_era}</div>`;
      if (thread.summary) html += `<div style="margin-top:6px;font-size:13px;color:#e2e8f0">${thread.summary.slice(0, 250)}</div>`;
      html += '</div>';
    }

    // All threads (with override buttons)
    if (threads.length > 0) {
      html += '<div class="wo10-resume-card">';
      html += '<div class="wo10-resume-label">Active Threads</div>';
      for (const t of threads) {
        const isSelected = thread && t.thread_id === thread.thread_id;
        html += `<span class="wo10-thread-chip ${t.status || 'active'}"`;
        html += ` onclick="wo10SelectThread('${t.thread_id}')"`;
        html += ` title="${t.summary ? t.summary.slice(0, 100) : ''}"`;
        html += `>${isSelected ? "▶ " : ""}${t.topic_label || "?"} (${(t.score || 0).toFixed(1)})</span>`;
      }
      html += '</div>';
    }

    // Key memory items
    if (scoredItems.length > 0) {
      html += '<div class="wo10-resume-card">';
      html += '<div class="wo10-resume-label">Key Memory</div>';
      for (const item of scoredItems.slice(0, 6)) {
        const kind = item.kind || "fact";
        html += `<div style="font-size:13px;margin-bottom:4px;color:#e2e8f0">[${kind}] ${(item.text || "").slice(0, 120)}</div>`;
      }
      html += '</div>';
    }

    // Recent turns
    if (recentTurns.length > 0) {
      html += '<div class="wo10-resume-card">';
      html += '<div class="wo10-resume-label">Recent Exchange</div>';
      for (const t of recentTurns) {
        const role = (t.role || "").toLowerCase() === "user" ? narName : "Lori";
        html += `<div style="font-size:13px;margin-bottom:4px"><strong>${role}:</strong> ${(t.content || "").slice(0, 150)}</div>`;
      }
      html += '</div>';
    }

    // Operator controls
    html += '<div style="margin-top:16px">';
    html += '<button class="wo10-btn primary" onclick="wo10UseResume(\'use\')">Use This Resume</button>';
    html += '<button class="wo10-btn" onclick="wo10UseResume(\'continue\')">Continue Last Topic</button>';
    html += '<button class="wo10-btn" onclick="wo10UseResume(\'fresh\')">Start Fresh Gently</button>';
    html += '</div>';

    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171">Failed to load resume preview: ${e.message}</p>`;
  }
}

function wo10SelectThread(threadId) {
  state.wo10 = state.wo10 || {};
  state.wo10.manualResumeThreadId = threadId;
  console.log("[WO-10] Operator selected thread:", threadId);
  // Refresh preview
  wo10LoadResumePreview();
}
window.wo10SelectThread = wo10SelectThread;

function wo10UseResume(action) {
  const pid = state.person_id;
  if (!pid) return;
  const name = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "the narrator";

  let prompt = "";
  if (action === "use") {
    // Build and send the resume prompt immediately
    _wo9BuildResumePrompt(pid).then(p => {
      if (p && _llmReady) sendSystemPrompt(p);
      else if (p) wo9SendOrQueueSystemPrompt(p);
    });
    console.log("[WO-10] Operator: use selected resume");
  } else if (action === "continue") {
    prompt = `[SYSTEM: ${name} is returning. Continue from whatever topic was active last time. Welcome them warmly and ask ONE follow-up question.]`;
    if (_llmReady) sendSystemPrompt(prompt); else wo9SendOrQueueSystemPrompt(prompt);
    console.log("[WO-10] Operator: continue last topic");
  } else if (action === "fresh") {
    prompt = `[SYSTEM: ${name} is returning. Start fresh gently — ask where they'd like to begin today without assuming any topic. Be warm and open.]`;
    if (_llmReady) sendSystemPrompt(prompt); else wo9SendOrQueueSystemPrompt(prompt);
    console.log("[WO-10] Operator: start fresh");
  }

  // Close the popover
  try { document.getElementById("wo10TranscriptPopover")?.hidePopover(); } catch (_) {}
}
window.wo10UseResume = wo10UseResume;

async function wo10LoadSessionTimeline() {
  const pid = state.person_id;
  const container = document.getElementById("wo10TimelineContent");
  if (!container || !pid) {
    if (container) container.innerHTML = '<p style="color:#64748b">No narrator selected.</p>';
    return;
  }
  container.innerHTML = '<p style="color:#64748b">Loading timeline...</p>';

  try {
    const res = await fetch(API.SESSION_TIMELINE(pid), { signal: AbortSignal.timeout(8000) });
    if (!res.ok) throw new Error("No timeline data");
    const data = await res.json();
    const sessions = data.sessions || [];

    if (!sessions.length) {
      container.innerHTML = '<p style="color:#64748b">No sessions yet.</p>';
      return;
    }

    let html = '<div style="font-size:12px;color:#64748b;margin-bottom:12px">Session history and dominant threads</div>';
    for (const s of sessions) {
      const dateStr = s.started_at ? new Date(s.started_at).toLocaleDateString([], { month: "short", day: "numeric" }) : "?";
      const topic = s.topic_label || "(no topic detected)";
      const era = s.active_era ? ` [${s.active_era.replace(/_/g, " ")}]` : "";
      html += `<div class="wo10-timeline-row">`;
      html += `<div class="wo10-timeline-date">${dateStr}</div>`;
      html += `<div class="wo10-timeline-topic">${topic}${era}</div>`;
      html += `<div class="wo10-timeline-turns">${s.turn_count || 0} turns</div>`;
      html += `</div>`;
    }
    container.innerHTML = html;
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171">Failed to load timeline: ${e.message}</p>`;
  }
}

// Auto-load transcript when popover opens
(function() {
  const pop = document.getElementById("wo10TranscriptPopover");
  if (pop) {
    pop.addEventListener("toggle", (e) => {
      if (e.newState === "open") wo10LoadTranscriptViewer();
    });
  }
})();

/* ── WO-8 Phase 3: Voice Turn Improvements ───────────────────── */

/**
 * WO-10B: Transcript growth tracker for no-interruption engine.
 * Updated every time we get a final speech recognition result.
 * lv80FireCheckIn() checks this to avoid interrupting active speech.
 */
let _wo10bLastTranscriptGrowthTs = 0;
window._wo10bLastTranscriptGrowthTs = 0;  // expose for idle guard

/**
 * WO-10B: Conversation state tracker for no-interruption engine.
 * Updated after each narrator turn finalization.
 */
let _wo10bCurrentConversationState = null;
window._wo10bCurrentConversationState = null;  // expose for idle guard

/**
 * WO-8 voice turn state.
 * Tracks long-turn capture mode with operator controls.
 */
let _wo8VoicePaused = false;
let _wo8VoiceTurnChunks = [];  // accumulate speech chunks for the current turn
let _wo8VoiceTurnStart = null;
let _wo8LongTurnMode = false;  // true when narrator is in extended speech
/* BUG-219: pre-mic typed draft preservation.
   When the narrator types something then toggles the mic on, the WO-8
   voice-turn accumulator was overwriting chatInput with chunks.join(" "),
   wiping any text the narrator had typed.  Now we snapshot the existing
   chatInput value at mic-arm time and prepend it to the chunks display.
   Cleared on send or finalize.  Acceptance per BUG-219:
     1. Type "My father was"  →  2. Click mic  →  3. Say "Kent Horne"
     4. chatInput should read "My father was Kent Horne"  (not just "Kent Horne") */
let _wo8PreMicDraft = "";

/**
 * WO-8: Enhanced recognition result handler that accumulates speech
 * chunks without auto-sending, allowing long natural pauses.
 * The narrator must explicitly end their turn (Done button or voice command).
 */
function _wo8HandleRecognitionResult(e) {
  // Guard: if Lori is speaking, discard
  if (isLoriSpeaking) {
    console.warn("[WO-8 STT] Recognition while Lori speaking — discarded.");
    return;
  }
  // Guard: if paused
  if (_wo8VoicePaused) return;

  let fin = "";
  let interim = "";
  for (let i = e.resultIndex; i < e.results.length; i++) {
    if (e.results[i].isFinal) {
      fin += e.results[i][0].transcript;
    } else {
      interim += e.results[i][0].transcript;
    }
  }

  // WO-MIC-UI-02A: wo8VoiceStatus was a competing interim display. Keep updating
  // for diagnostics but ensure it stays hidden — narrator sees only #chatInput.
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl && interim) {
    statusEl.textContent = interim;
    statusEl.className = "wo8-voice-status wo8-listening wo8-hidden";
  }

  if (!fin) return;

  // WO-10B: Stamp transcript growth — narrator is actively speaking
  _wo10bLastTranscriptGrowthTs = Date.now();
  window._wo10bLastTranscriptGrowthTs = _wo10bLastTranscriptGrowthTs;

  const normalized = _normalisePunctuation(fin);
  const trimmed = normalized.trim().toLowerCase();

  // Check for voice commands — WO-9: only if explicitly enabled
  if (_wo9VoiceSendEnabled && _SEND_COMMANDS.has(trimmed)) {
    _wo8FinalizeTurn();
    return;
  }

  // Accumulate the chunk
  _wo8VoiceTurnChunks.push({
    text: normalized,
    ts: Date.now(),
  });
  if (!_wo8VoiceTurnStart) _wo8VoiceTurnStart = Date.now();
  _wo8LongTurnMode = true;

  // Update the chat input with accumulated text.
  // BUG-219: prepend any pre-mic typed draft so toggling the mic doesn't
  // wipe what the narrator was already typing.  Single space separator.
  const _chunkText = _wo8VoiceTurnChunks.map(c => c.text).join(" ");
  const _draft = (_wo8PreMicDraft || "").trim();
  const fullText = _draft ? (_draft + " " + _chunkText) : _chunkText;
  setv("chatInput", fullText);

  // WO-MIC-UI-02A: #wo8LiveTranscript was a competing visible surface that confused
  // narrators ("text appears underneath"). The canonical display is now #chatInput only.
  // We still write to wo8LiveTranscript for debug/diagnostics but keep it hidden.
  const transcriptEl = document.getElementById("wo8LiveTranscript");
  if (transcriptEl) {
    transcriptEl.textContent = fullText;
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
    // Ensure it stays hidden — single surface authority
    if (!transcriptEl.classList.contains("wo8-hidden")) {
      transcriptEl.classList.add("wo8-hidden");
    }
  }

  // Clear interim display
  if (statusEl) {
    statusEl.textContent = "Listening…";
    statusEl.className = "wo8-voice-status wo8-listening";
  }

  console.log("[WO-8] Voice chunk accumulated. Total chunks:", _wo8VoiceTurnChunks.length,
    "Total chars:", fullText.length);
}

/**
 * WO-8: Finalize the voice turn — send the accumulated text.
 */
function _wo8FinalizeTurn() {
  if (!_wo8VoiceTurnChunks.length) return;

  // BUG-219: include any pre-mic typed draft as a prefix.
  const _chunkTextFinal = _wo8VoiceTurnChunks.map(c => c.text).join(" ");
  const _draftFinal = (_wo8PreMicDraft || "").trim();
  const fullText = _draftFinal ? (_draftFinal + " " + _chunkTextFinal) : _chunkTextFinal;
  setv("chatInput", fullText);

  // Stop recording before sending
  if (isRecording) stopRecording();

  // Reset turn state (including BUG-219 draft snapshot)
  _wo8VoiceTurnChunks = [];
  _wo8VoiceTurnStart = null;
  _wo8LongTurnMode = false;
  _wo8PreMicDraft = "";

  // Clear live transcript
  const transcriptEl = document.getElementById("wo8LiveTranscript");
  if (transcriptEl) transcriptEl.textContent = "";

  // Update status
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl) {
    statusEl.textContent = "Processing…";
    statusEl.className = "wo8-voice-status wo8-processing";
  }

  // Send
  sendUserMessage();
}
window._wo8FinalizeTurn = _wo8FinalizeTurn;

/**
 * WO-8: Pause voice capture without ending the turn.
 */
function wo8PauseListening() {
  _wo8VoicePaused = true;
  window._wo8VoicePaused = true;           // expose for lv80FireCheckIn guard
  if (recognition) { try { recognition.stop(); } catch (_) {} }
  // WO-8 fix: suppress Lori's idle nudge timer while paused
  if (typeof lv80ClearIdle === "function") lv80ClearIdle();
  console.log("[WO-8] Paused — mic stopped, idle nudge suppressed.");
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl) {
    statusEl.textContent = "Paused";
    statusEl.className = "wo8-voice-status wo8-paused";
  }
  _updateWo8Controls();
}
window.wo8PauseListening = wo8PauseListening;

/**
 * WO-8: Resume voice capture after pause.
 */
function wo8ResumeListening() {
  _wo8VoicePaused = false;
  window._wo8VoicePaused = false;          // sync window flag
  if (!isRecording) startRecording();
  else { try { recognition.start(); } catch (_) {} }
  // WO-8 fix: re-arm Lori's idle nudge timer on resume
  if (typeof lv80ArmIdle === "function") lv80ArmIdle("resume_from_pause");
  console.log("[WO-8] Resumed — mic active, idle nudge re-armed.");
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl) {
    statusEl.textContent = "Listening…";
    statusEl.className = "wo8-voice-status wo8-listening";
  }
  _updateWo8Controls();
}
window.wo8ResumeListening = wo8ResumeListening;

/**
 * WO-8: Send now button — end turn immediately.
 */
function wo8SendNow() {
  _wo8FinalizeTurn();
}
window.wo8SendNow = wo8SendNow;

/**
 * WO-8: Update visibility of voice controls.
 */
function _updateWo8Controls() {
  const pauseBtn = document.getElementById("wo8PauseBtn");
  const resumeBtn = document.getElementById("wo8ResumeBtn");
  const sendBtn = document.getElementById("wo8SendNowBtn");

  if (pauseBtn) pauseBtn.classList.toggle("hidden", _wo8VoicePaused || !isRecording);
  if (resumeBtn) resumeBtn.classList.toggle("hidden", !_wo8VoicePaused);
  if (sendBtn) sendBtn.classList.toggle("hidden", !_wo8VoiceTurnChunks.length);
}

/* ── WO-8 Phase 4: Chunked extraction for long turns ─────────── */

/**
 * WO-8: Chunk a long text into extraction-friendly segments.
 * Each chunk is roughly sentence-bounded and under maxLen tokens.
 */
function _wo8ChunkText(text, maxLen) {
  maxLen = maxLen || 1500; // ~1500 chars per chunk
  if (text.length <= maxLen) return [text];

  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [text];
  const chunks = [];
  let current = "";

  for (const s of sentences) {
    if ((current + s).length > maxLen && current.length > 0) {
      chunks.push(current.trim());
      current = s;
    } else {
      current += s;
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

/* ── WO-8 Phase 5: Thread Anchor & Resume ────────────────────── */

/**
 * WO-8: Save the current thread anchor after each meaningful exchange.
 * Called from onAssistantReply when a real conversation turn completes.
 */
async function _wo8SaveThreadAnchor(userText, loriText) {
  const pid = state.person_id;
  if (!pid) return;

  // Build a topic summary from the last exchange
  const combined = (userText || "").slice(0, 500) + " " + (loriText || "").slice(0, 500);

  // Simple topic extraction — look for era/subject signals
  let topicLabel = "";
  let topicSummary = "";

  // Try to detect the active topic from the user's words
  const topicPatterns = [
    { rx: /\b(army|military|service|enlist|deploy|stationed)\b/i, label: "Military service" },
    { rx: /\b(leav|left|moved|moving|went)\s+(home|away|out)\b/i, label: "Leaving home" },
    { rx: /\b(school|college|university|graduate|diploma)\b/i, label: "Education" },
    { rx: /\b(married|wedding|wife|husband|spouse|partner)\b/i, label: "Marriage & family" },
    { rx: /\b(job|work|career|hired|company|boss|retire)\b/i, label: "Career" },
    { rx: /\b(child|kids|son|daughter|baby|born|pregnant)\b/i, label: "Children & family" },
    { rx: /\b(church|faith|god|religion|pray)\b/i, label: "Faith & spirituality" },
    { rx: /\b(sick|hospital|health|surgery|doctor|cancer|heart)\b/i, label: "Health" },
    { rx: /\b(farm|ranch|land|crop|cattle|harvest)\b/i, label: "Farm & rural life" },
    { rx: /\b(brother|sister|sibling|twin)\b/i, label: "Siblings" },
    { rx: /\b(mom|mother|dad|father|parent|grandma|grandpa)\b/i, label: "Parents & family" },
    { rx: /\b(passed away|died|death|funeral|burial|cemetery)\b/i, label: "Loss & grief" },
  ];

  for (const p of topicPatterns) {
    if (p.rx.test(combined)) {
      topicLabel = p.label;
      break;
    }
  }

  // Build a brief summary from the user's turn
  topicSummary = (userText || "").slice(0, 300);

  const activeEra = getCurrentEra() || "";

  // WO-9: Extract continuation keywords from the exchange
  const words = combined.toLowerCase().replace(/[^a-z0-9\s]/g, " ").split(/\s+/).filter(w => w.length > 4);
  const wordFreq = {};
  words.forEach(w => { wordFreq[w] = (wordFreq[w] || 0) + 1; });
  const continuationKeywords = Object.entries(wordFreq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(e => e[0]);

  try {
    await fetch(API.THREAD_ANCHOR_PUT, {
      method: "POST",
      headers: ctype(),
      body: JSON.stringify({
        person_id: pid,
        session_id: state.chat?.conv_id || "",
        topic_label: topicLabel,
        topic_summary: topicSummary,
        active_era: activeEra,
        last_narrator_turns: [userText || ""],
        // WO-9 stronger continuity fields
        subtopic_label: "",
        continuation_keywords: continuationKeywords,
        last_meaningful_user_turn: (userText || "").slice(0, 500),
        last_meaningful_assistant_turn: (loriText || "").slice(0, 500),
      }),
    });
    console.log("[WO-9] Thread anchor saved:", topicLabel || "(general)", "era:", activeEra || "(none)",
      "keywords:", continuationKeywords.slice(0, 5).join(", "));
  } catch (e) {
    console.log("[WO-9] Thread anchor save failed:", e.message);
  }

  // WO-9: Save rolling summary after each exchange
  _wo9SaveRollingSummary(userText, loriText, topicLabel).catch(() => {});
  // WO-10: Update multi-thread tracker via rolling summary endpoint
  _wo10UpdateThreads(topicLabel, activeEra, userText, loriText).catch(() => {});
}

/**
 * WO-9: Save rolling summary after each meaningful exchange.
 * Accumulates key facts, tracks emotional tone and open threads.
 */
async function _wo9SaveRollingSummary(userText, loriText, topicLabel) {
  const pid = state.person_id;
  if (!pid) return;

  // Load existing summary to merge
  let existing = {};
  try {
    const resp = await fetch(API.ROLLING_SUMMARY_GET(pid));
    if (resp.ok) {
      const data = await resp.json();
      existing = data.summary || {};
    }
  } catch (_) { /* first time, no summary yet */ }

  // Accumulate key facts from user text (simple extraction: sentences with proper nouns, dates, names)
  const prevFacts = existing.key_facts_mentioned || [];
  const newFacts = [];
  if (userText) {
    // Extract sentences that contain dates, names, or specific details
    const sentences = userText.match(/[^.!?]+[.!?]+/g) || [userText];
    for (const s of sentences) {
      const trimmed = s.trim();
      if (trimmed.length > 20 && trimmed.length < 300) {
        // Look for factual content: dates, proper nouns, numbers
        if (/\b(19|20)\d{2}\b/.test(trimmed) || /\b[A-Z][a-z]+\b/.test(trimmed) || /\d+/.test(trimmed)) {
          newFacts.push(trimmed);
        }
      }
    }
  }
  const allFacts = [...prevFacts, ...newFacts].slice(-50);

  // Detect emotional tone
  let tone = existing.emotional_tone || "neutral";
  if (userText) {
    const lower = userText.toLowerCase();
    if (/\b(sad|cried|crying|tears|miss|grief|lost)\b/.test(lower)) tone = "reflective/emotional";
    else if (/\b(funny|laugh|hilarious|joke|grin)\b/.test(lower)) tone = "lighthearted";
    else if (/\b(proud|accomplish|achieve|medal|honor)\b/.test(lower)) tone = "proud";
    else if (/\b(angry|mad|furious|upset|unfair)\b/.test(lower)) tone = "frustrated";
    else tone = "engaged";
  }

  // Track the last question Lori asked
  let lastQuestion = existing.last_question_asked || "";
  if (loriText) {
    const questions = loriText.match(/[^.!]+\?/g);
    if (questions && questions.length > 0) {
      lastQuestion = questions[questions.length - 1].trim();
    }
  }

  // Open threads — topics mentioned but not fully explored
  const openThreads = existing.open_threads || [];
  if (topicLabel && !openThreads.includes(topicLabel)) {
    openThreads.push(topicLabel);
  }

  try {
    await fetch(API.ROLLING_SUMMARY_PUT, {
      method: "POST",
      headers: ctype(),
      body: JSON.stringify({
        person_id: pid,
        topic_thread: topicLabel || existing.topic_thread || "",
        key_facts_mentioned: allFacts,
        emotional_tone: tone,
        last_question_asked: lastQuestion,
        narrator_preferences: existing.narrator_preferences || [],
        open_threads: openThreads.slice(-10),
      }),
    });
    console.log("[WO-9] Rolling summary saved, facts:", allFacts.length, "tone:", tone);
  } catch (e) {
    console.log("[WO-9] Rolling summary save failed:", e.message);
  }
}

/**
 * WO-10: Update multi-thread tracker.
 * Calls the backend update_active_threads via rolling summary update.
 * Thread tracking is done server-side in archive.py.
 */
async function _wo10UpdateThreads(topicLabel, era, userText, loriText) {
  const pid = state.person_id;
  if (!pid || !topicLabel) return;
  try {
    // WO-10B: Preserve more of long turns (500 chars instead of 300)
    // so backend thread scoring can assess narrative richness
    await fetch(API.UPDATE_THREADS, {
      method: "POST",
      headers: ctype(),
      body: JSON.stringify({
        person_id: pid,
        topic_label: topicLabel,
        era: era || "",
        user_text: (userText || "").slice(0, 500),
        lori_text: (loriText || "").slice(0, 500),
      }),
    });
    console.log("[WO-10] Thread update sent for:", topicLabel);
  } catch (e) {
    console.log("[WO-10] Thread update failed:", e.message);
  }
}

/**
 * WO-9: Build resume system prompt from archive memory.
 * Uses: thread anchor + rolling summary + recent archive turns.
 * Falls back to WO-8 minimal anchor if rolling summary is unavailable.
 * Returns null if no anchor exists (first session).
 */
async function _wo9BuildResumePrompt(pid) {
  if (!pid) return null;
  try {
    // Fetch all three memory sources in parallel
    const [anchorRes, summaryRes, turnsRes] = await Promise.all([
      fetch(API.THREAD_ANCHOR_GET(pid, ""), { signal: AbortSignal.timeout(5000) }),
      fetch(API.ROLLING_SUMMARY_GET(pid), { signal: AbortSignal.timeout(5000) }).catch(() => null),
      fetch(API.RECENT_TURNS(pid, "", 4), { signal: AbortSignal.timeout(5000) }).catch(() => null),
    ]);

    // Parse anchor (required)
    if (!anchorRes.ok) return null;
    const anchorData = await anchorRes.json();
    const anchor = anchorData.anchor;
    if (!anchor || !anchor.topic_summary) return null;

    // Parse rolling summary (optional)
    let summary = {};
    if (summaryRes && summaryRes.ok) {
      const sData = await summaryRes.json();
      summary = sData.summary || {};
    }

    // Parse recent turns (optional)
    let recentTurns = [];
    if (turnsRes && turnsRes.ok) {
      const tData = await turnsRes.json();
      recentTurns = tData.turns || [];
    }

    const name = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "the narrator";
    const topicLabel = anchor.topic_label || "your conversation";
    const era = anchor.active_era || "";

    let resumeText = `[SYSTEM: RESUME SESSION — ${name} is returning to continue their interview.\n`;

    // Thread anchor context
    resumeText += `Last topic: "${topicLabel}".\n`;
    if (anchor.subtopic_label) {
      resumeText += `Subtopic: "${anchor.subtopic_label}".\n`;
    }
    if (era) {
      resumeText += `Active era: "${era.replace(/_/g, " ")}".\n`;
    }

    // WO-9: Include last meaningful exchange from anchor
    if (anchor.last_meaningful_user_turn) {
      resumeText += `\nLast exchange:\n`;
      resumeText += `  ${name}: "${anchor.last_meaningful_user_turn.slice(0, 300)}"\n`;
      if (anchor.last_meaningful_assistant_turn) {
        resumeText += `  Lori: "${anchor.last_meaningful_assistant_turn.slice(0, 300)}"\n`;
      }
    }

    // WO-9: Rolling summary context
    if (summary.emotional_tone) {
      resumeText += `\nNarrator mood: ${summary.emotional_tone}.\n`;
    }
    if (summary.key_facts_mentioned && summary.key_facts_mentioned.length > 0) {
      const recentFacts = summary.key_facts_mentioned.slice(-5);
      resumeText += `Key facts from recent conversation: ${recentFacts.join("; ").slice(0, 400)}.\n`;
    }
    if (summary.open_threads && summary.open_threads.length > 0) {
      resumeText += `Open threads to explore: ${summary.open_threads.join(", ")}.\n`;
    }
    if (summary.last_question_asked) {
      resumeText += `Your last question to ${name}: "${summary.last_question_asked.slice(0, 200)}"\n`;
    }

    // WO-9: Recent archive turns for richer context
    if (recentTurns.length > 0) {
      resumeText += `\nRecent conversation excerpt:\n`;
      for (const t of recentTurns.slice(-4)) {
        const role = (t.role || "").toLowerCase();
        const label = role === "user" ? name : "Lori";
        resumeText += `  ${label}: "${(t.content || "").slice(0, 150)}"\n`;
      }
    }

    // Continuation keywords for context
    if (anchor.continuation_keywords && anchor.continuation_keywords.length > 0) {
      resumeText += `\nContext keywords: ${anchor.continuation_keywords.join(", ")}.\n`;
    }

    resumeText += `\nContinue from this topic — do NOT restart with generic identity questions about birthplace or childhood `;
    resumeText += `unless "${topicLabel}" was specifically about those topics. `;
    resumeText += `Welcome them back warmly and naturally, referencing what they were telling you last time. `;
    resumeText += `Ask ONE follow-up question that continues the thread.]`;

    console.log("[WO-9] Resume prompt built from archive memory:",
      "topic:", topicLabel, "era:", era,
      "summary:", !!summary.topic_thread, "turns:", recentTurns.length);
    return resumeText;
  } catch (e) {
    console.log("[WO-9] Resume prompt build failed:", e.message);
    return null;
  }
}

/**
 * WO-11 (TRAINER MODE REPAIR): Start normal interview after trainer
 * coaching flow completes — now meta-aware.
 *
 * Called by LorevoxTrainerNarrators.finish(meta) when the user clicks
 * "Start Interview" or "Skip". The meta object carries the trainer style
 * captured BEFORE finish() flipped active=false, so the handoff knows
 * which trainer just ran and can flavor:
 *   - the assistant intro bubble (structured vs storyteller wording)
 *   - a one-shot system prompt that nudges the next model reply into
 *     the trainer style (no backend role change required)
 *
 * If meta is missing/empty, falls back to the previous neutral intro.
 */
window.lv80StartTrainerInterview = async function (meta) {
  try {
    var m = (meta && typeof meta === "object") ? meta : {};
    var style = (m.style === "structured" || m.style === "storyteller") ? m.style : null;

    // WO-11: Trainer is done — restore narrator for actual interview.
    // The trainer finish() already set active=false. Now we need to
    // restore the real narrator context before injecting the style hint.
    console.log("[WO-11][trainer] Trainer interview handoff — style:", style);

    // Restore narrator after trainer exit — opens narrator selector
    if (typeof _wo11RestoreNarratorAfterTrainer === "function") {
      _wo11RestoreNarratorAfterTrainer();
    }

    // Note: The style hint will be applied by the user selecting a narrator
    // and the interview beginning naturally. We stash the trainer style so
    // it can flavor the first system prompt when they do pick a narrator.
    state.trainerNarrators = state.trainerNarrators || {};
    state.trainerNarrators._pendingStyleHint = m.promptHint || null;
    state.trainerNarrators._pendingStyle = style;

    if (typeof update71RuntimeUI === "function") update71RuntimeUI();
  } catch (e) {
    console.warn("[WO-11] unable to start trainer interview", e);
  }
};

/**
 * WO-11B: Hard reset helper for trainer/capture state.
 * Clears trainer flow, listening state, mic UI, and pending capture.
 * Called on: startup, narrator switch, trainer finish, trainer skip.
 */
window.lv80ClearTrainerAndCaptureState = function () {
  // WO-11: If trainer was active with a suspended narrator, restore first
  try {
    var ts = state && state.trainerNarrators;
    if (ts && ts.active && ts.suspendedNarratorId) {
      console.log("[WO-11][trainer] clearTrainer detected active trainer with suspended narrator — restoring");
      if (typeof _wo11RestoreNarratorAfterTrainer === "function") {
        _wo11RestoreNarratorAfterTrainer();
      }
    }
  } catch (_) {}

  try {
    if (window.LorevoxTrainerNarrators) {
      window.LorevoxTrainerNarrators.reset();
    }
  } catch (_) {}

  try {
    listeningPaused = false;
  } catch (_) {}

  try {
    if (typeof recognition !== "undefined" && recognition) {
      recognition.onend = recognition.onend || null;
      recognition.stop();
    }
  } catch (_) {}

  try {
    isRecording = false;
  } catch (_) {}

  try {
    const mic = document.getElementById("btnMic");
    if (mic) mic.classList.remove("mic-active");
  } catch (_) {}

  try {
    const pauseBtn = document.getElementById("btnPause");
    if (pauseBtn) {
      pauseBtn.classList.remove("paused");
      pauseBtn.textContent = "Pause";
    }
  } catch (_) {}
};

/**
 * WO-11B: Pause/Resume listening toggle.
 * Pause stops speech recognition immediately and prevents auto-restart.
 * Resume returns to ready state — capture does not auto-restart.
 */
window.lv80TogglePauseListening = function () {
  try {
    const pauseBtn = document.getElementById("btnPause");

    if (!listeningPaused) {
      listeningPaused = true;

      try {
        if (typeof recognition !== "undefined" && recognition) {
          recognition.stop();
        }
      } catch (_) {}

      isRecording = false;

      const mic = document.getElementById("btnMic");
      if (mic) mic.classList.remove("mic-active");

      if (pauseBtn) {
        pauseBtn.classList.add("paused");
        pauseBtn.textContent = "Resume";
      }

      console.log("[WO-11B] listening paused");
      return;
    }

    listeningPaused = false;

    if (pauseBtn) {
      pauseBtn.classList.remove("paused");
      pauseBtn.textContent = "Pause";
    }

    console.log("[WO-11B] listening resumed");
  } catch (e) {
    console.warn("[WO-11B] pause toggle failed", e);
  }
};

/**
 * WO-8: Fire resume system prompt when narrator is opened.
 * Hooks into the narrator load flow after identity is confirmed ready.
 */
async function wo8OnNarratorReady(pid) {
  if (!pid) return;

  // Phase 2: Load transcript history
  await wo8LoadTranscriptHistory(pid);

  // WO-13: Hard gate — if this narrator has NO prior user-authored turns,
  // suppress every resume prompt variant (auto-resume, soft confirm, bridge,
  // cognitive re-entry, operator preview). Every narrator switch creates a
  // fresh conv_id, so "resuming" is a misnomer for first-contact narrators
  // and the system prompt pollutes the turns table with fake user rows.
  const _priorUserTurns = Number((state.session && state.session.priorUserTurns) || 0);
  if (_priorUserTurns === 0) {
    console.log("[WO-13] wo8OnNarratorReady: suppressing resume prompt — no prior user turns for " + pid.slice(0, 8));
    return;
  }

  // WO-9/WO-10B/WO-10C: Resume flow — gated by operator mode, confidence, and CSM
  if (hasIdentityBasics74()) {

    // WO-10C: Cognitive Support Mode — replace ALL resume with gentle re-entry.
    // Never interrogative, never assume they remember where they left off.
    // The re-entry is a warm invitation, not a conversation resume.
    if (typeof getCognitiveSupportMode === "function" && getCognitiveSupportMode()) {
      const name = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "";
      const greeting = name ? `${name}, ` : "";
      const reentryPrompt = `[SYSTEM: COGNITIVE SUPPORT MODE RE-ENTRY. ${greeting}is here. `
        + "This narrator has cognitive difficulty. Do NOT ask where you left off. Do NOT reference previous sessions. "
        + "Do NOT ask 'Do you remember?' Welcome them with pure warmth — as if this is a fresh, gentle visit. "
        + "Example: 'Hello " + (name || "there") + ", it's so good to see you. I'm Lori, and I'm here to keep you company.' "
        + "One or two short, warm sentences. Then wait. Let them lead. Do not ask a question.]";
      console.log("[WO-10C] Cognitive support mode — gentle re-entry, no resume.");
      setTimeout(() => {
        if (_llmReady) sendSystemPrompt(reentryPrompt);
        else wo9SendOrQueueSystemPrompt(reentryPrompt);
      }, 1200); // slightly longer delay — no rush
      return;
    }

    // WO-10B: If operator mode is ON, show Resume Preview instead of auto-resuming
    if (window.HORNELORE_OPERATOR_MODE) {
      console.log("[WO-10B] Operator mode ON — showing Resume Preview, blocking auto-resume.");
      // Open the transcript popover to Resume Preview tab
      try {
        const pop = document.getElementById("wo10TranscriptPopover");
        if (pop && typeof pop.showPopover === "function") pop.showPopover();
        // Switch to Resume Preview tab
        if (typeof wo10SwitchTab === "function") wo10SwitchTab("resume");
      } catch (_) {}
      // Load the resume preview data
      if (typeof wo10LoadResumePreview === "function") wo10LoadResumePreview();
      // DO NOT auto-send — operator must click Use/Continue/Fresh
      return;
    }

    // WO-10B: Operator mode OFF — check resume confidence before auto-resume
    const resumePrompt = await _wo9BuildResumePrompt(pid);
    if (resumePrompt) {
      // Fetch confidence level to decide auto-resume behavior
      let confLevel = "medium";
      try {
        // WO-10K: API.RESUME_PREVIEW is a function, not a string — call it properly
        const r = await fetch(API.RESUME_PREVIEW(pid));
        if (r.ok) {
          const data = await r.json();
          confLevel = (data.confidence && data.confidence.level) || "medium";
        }
      } catch (_) {}

      if (confLevel === "high") {
        // HIGH confidence: auto-resume directly
        console.log("[WO-10B] High confidence — auto-resuming.");
        setTimeout(() => {
          if (_llmReady) sendSystemPrompt(resumePrompt);
          else wo9SendOrQueueSystemPrompt(resumePrompt);
        }, 800);
      } else if (confLevel === "medium") {
        // MEDIUM confidence: use soft confirm prompt instead of strong resume
        const name = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "the narrator";
        const softPrompt = `[SYSTEM: ${name} is returning. You have some context from last time but are not fully sure where you left off. Welcome them warmly and gently check: "Last time I think we were talking about... shall we pick up there, or would you like to go somewhere else?" One sentence only.]`;
        console.log("[WO-10B] Medium confidence — soft confirm resume.");
        setTimeout(() => {
          if (_llmReady) sendSystemPrompt(softPrompt);
          else wo9SendOrQueueSystemPrompt(softPrompt);
        }, 800);
      } else {
        // LOW confidence: gentle bridge, no assumption about topic
        const name = state.profile?.basics?.preferred || state.profile?.basics?.fullname || "the narrator";
        const bridgePrompt = `[SYSTEM: ${name} is returning. You do not have strong context from last time. Welcome them warmly and ask an open question like "What's on your mind today?" or "Where would you like to start?" Do NOT assume any specific topic. One sentence only.]`;
        console.log("[WO-10B] Low confidence — gentle bridge.");
        setTimeout(() => {
          if (_llmReady) sendSystemPrompt(bridgePrompt);
          else wo9SendOrQueueSystemPrompt(bridgePrompt);
        }, 800);
      }
    }
  }
}
window.wo8OnNarratorReady = wo8OnNarratorReady;

/* ── WO-8 Phase 6: Anti-drift for identity extraction ────────── */

/**
 * WO-8: Check if a system prompt is drifting toward identity grounding
 * when the active thread is elsewhere.
 * Returns the corrected prompt if drift is detected, null otherwise.
 */
function _wo8CheckContinuityDrift(prompt) {
  if (!prompt) return null;
  // If we have no thread anchor, no drift detection needed
  if (!state._wo8LastTopicLabel) return null;

  const lowerPrompt = prompt.toLowerCase();
  const identityPatterns = /\b(birthplace|born in|hometown|grew up in|childhood home|where.*born|stanley|north dakota|fargo)\b/i;
  const topicLabel = state._wo8LastTopicLabel || "";

  // If prompt is pulling toward identity AND the last topic was different
  if (identityPatterns.test(lowerPrompt) && topicLabel &&
      !topicLabel.toLowerCase().includes("childhood") &&
      !topicLabel.toLowerCase().includes("birth")) {
    console.log("[WO-8] Continuity drift detected — suppressing identity grounding in favor of:", topicLabel);
    return true; // Signal drift — caller should prefer thread-based question
  }
  return null;
}

/* ── WO-8: Inject into existing hooks ────────────────────────── */

// Store the original onAssistantReply to chain our hook
const _wo8OrigOnAssistantReply = onAssistantReply;
onAssistantReply = function(text) {
  // Call original
  _wo8OrigOnAssistantReply(text);

  // WO-8: Save thread anchor after each real reply
  if (text && state.person_id && _lastUserTurn) {
    _wo8SaveThreadAnchor(_lastUserTurn, text).catch(() => {});
  }

  // WO-8: Update voice status
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl && statusEl.className.includes("wo8-processing")) {
    statusEl.textContent = "Ready";
    statusEl.className = "wo8-voice-status wo8-ready";
  }
};

// Store topic label in state for drift detection
state._wo8LastTopicLabel = "";

/* ── WO-8: Override recognition result for enhanced long-turn mode ── */

/**
 * WO-8: Install enhanced recognition handler.
 * Call after _ensureRecognition() to replace the default onresult.
 */
function _wo8InstallEnhancedVoice() {
  if (!recognition) return;

  // Save original for fallback
  const origOnResult = recognition.onresult;

  recognition.onresult = function(e) {
    // If in long-turn mode (mic is on and chunks are accumulating), use WO-8 handler
    if (_wo8LongTurnMode || _wo8VoiceTurnChunks.length > 0) {
      _wo8HandleRecognitionResult(e);
      return;
    }
    // Otherwise, use the WO-8 handler for all voice input (it also handles send commands)
    _wo8HandleRecognitionResult(e);
  };

  // Enhanced onend: don't auto-restart if paused
  recognition.onend = function() {
    if (isRecording && !isLoriSpeaking && !_wo8VoicePaused) {
      try { recognition.start(); } catch (e) {
        console.warn("[WO-8 STT] auto-restart failed:", e.message);
      }
    }
  };

  console.log("[WO-8] Enhanced voice handlers installed.");
}

// Patch startRecording to install enhanced handlers
const _wo8OrigStartRecording = startRecording;
startRecording = function() {
  _wo8VoiceTurnChunks = [];
  _wo8VoiceTurnStart = null;
  _wo8LongTurnMode = false;
  _wo8VoicePaused = false;
  // BUG-219: clear pre-mic draft snapshot here so original startRecording's
  // capture step has a clean slate.  Original captures the CURRENT chatInput
  // value (whatever the narrator just typed) AFTER this reset.
  _wo8PreMicDraft = "";
  _wo8OrigStartRecording();
  // Install enhanced handlers after recognition is created
  setTimeout(() => _wo8InstallEnhancedVoice(), 100);
  _updateWo8Controls();
  // Update status display
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl) {
    statusEl.textContent = "Listening…";
    statusEl.className = "wo8-voice-status wo8-listening";
  }
};

// Patch stopRecording to clean up
const _wo8OrigStopRecording = stopRecording;
stopRecording = function() {
  _wo8OrigStopRecording();
  _wo8VoicePaused = false;
  _updateWo8Controls();
  const statusEl = document.getElementById("wo8VoiceStatus");
  if (statusEl) {
    statusEl.textContent = "Mic off";
    statusEl.className = "wo8-voice-status";
  }
};

/* ═══════════════════════════════════════════════════════════════
   UTILITIES
═══════════════════════════════════════════════════════════════ */
function getv(id){ const el=document.getElementById(id); return el?el.value:""; }
function setv(id,v){ const el=document.getElementById(id); if(el&&v!==undefined) el.value=v||""; }
function esc(s){ const d=document.createElement("div"); d.textContent=String(s||""); return d.innerHTML; }
function escAttr(s){ return String(s||"").replace(/"/g,"&quot;").replace(/'/g,"&#39;"); }
function ctype(){ return {"Content-Type":"application/json"}; }
function nav_copy(t){ navigator.clipboard.writeText(t).catch(()=>{}); }
function appendOutput(label,text){
  const p=document.getElementById("outputPane"); if(!p) return;
  p.value+=`\n\n──── ${label} ────\n${text}`; p.scrollTop=p.scrollHeight;
  const b=document.getElementById("accDraft");
  if(b&&!b.classList.contains("open")) toggleAccordion("accDraft");
}
function copyDraftOutput(){ nav_copy(getv("outputPane")); sysBubble("↳ Notes copied."); }

/* ═══════════════════════════════════════════════════════════════
   v7.4B — Onboarding helpers
   Call startOnboarding74() once at session start (or on first person load)
   to run the scripted warm-up before entering normal interview flow.
   These functions are defined here but not wired to auto-startup yet;
   add the call site when the 7.3 shell flow is ready to change.
═══════════════════════════════════════════════════════════════ */

function startOnboarding74() {
  if (typeof state === "undefined") return;
  if (!state.session) state.session = {};

  if (!state.session.onboarding) {
    state.session.onboarding = {
      complete: false,
      cameraForPacing: false,
      profilePhotoEnabled: false,
      questionsAsked: false,
      profilePhotoCaptured: false,
      ttsPace: "normal",
    };
  }

  state.session.currentMode = "open";

  appendLoriOnboardingMessage("Hello. I'm Lori. I'm here to help you tell your story, at your pace. We can talk, type, pause, skip something, or come back later. Nothing has to be perfect.");
  appendLoriOnboardingMessage("You can speak to me and I can listen and turn your words into text. I can also speak my replies aloud, and everything I say will stay visible on screen. If typing feels easier, that works too.");
  appendLoriOnboardingMessage("As we go, I'll help build your profile, timeline, and a draft of your story with you. You can review and edit those at any time.");
  appendLoriOnboardingMessage("If you'd like, I can also use your camera in two optional ways. First, I can take a profile photo. Second, I can use a short warm-up moment to adjust to your lighting and expressions so I pace the conversation more gently.");
  appendLoriOnboardingMessage("The camera is optional. If you turn it on, it stays on this device. I don't save video, and I don't need the camera to continue.");
  appendLoriOnboardingMessage("Before we begin, do you have any questions about how I work, or would you like me to explain anything again?");

  state.session.onboarding.questionsAsked = true;
}

function appendLoriOnboardingMessage(text) {
  const host = document.getElementById("chatMessages");
  if (!host) return;

  const msg = document.createElement("div");
  msg.className = "msg lori";
  msg.textContent = text;
  host.appendChild(msg);
  host.scrollTop = host.scrollHeight;

  const last = document.getElementById("lastAssistantPanel");
  if (last) last.textContent = text;
}

async function beginCameraConsent74(opts = {}) {
  if (typeof state === "undefined") return false;
  // #145: lazy-init onboarding — narrator-switch handler rebuilds state.session
  // from scratch and the original static-init object in state.js is lost.
  // Without this, the Cam button silently no-ops on every post-first-load narrator.
  if (!state.session) state.session = {};
  if (!state.session.onboarding) {
    state.session.onboarding = {
      complete: false, cameraForPacing: false, profilePhotoEnabled: false,
      questionsAsked: false, profilePhotoCaptured: false, ttsPace: "normal",
    };
  }

  state.session.onboarding.cameraForPacing = !!opts.cameraForPacing;
  state.session.onboarding.profilePhotoEnabled = !!opts.profilePhotoEnabled;

  if (!state.session.onboarding.cameraForPacing) {
    return false;
  }

  // Let existing emotion-ui / FacialConsent path remain authoritative
  emotionAware = true;
  updateEmotionAwareBtn();

  await startEmotionEngine();

  if (window.AffectBridge74 && cameraActive) {
    window.AffectBridge74.beginBaselineWindow();
  }

  // Show draggable camera preview so the user can see what the camera sees
  if (cameraActive && window.lv74 && window.lv74.showCameraPreview) {
    window.lv74.showCameraPreview();
  }

  appendLoriOnboardingMessage("Thank you. Let's take a short moment to get comfortable. You don't need to do anything special — just look toward the screen naturally if that feels comfortable.");
  appendLoriOnboardingMessage("Is this a good time to begin?");
  appendLoriOnboardingMessage("How would you like me to address you?");
  appendLoriOnboardingMessage("Would you like me to speak more slowly, or is this pace comfortable?");

  return !!cameraActive;
}

function finalizeOnboarding74() {
  if (typeof state === "undefined") return;
  // #145: lazy-init — same reason as beginCameraConsent74 above.
  if (!state.session) state.session = {};
  if (!state.session.onboarding) {
    state.session.onboarding = {
      complete: false, cameraForPacing: false, profilePhotoEnabled: false,
      questionsAsked: false, profilePhotoCaptured: false, ttsPace: "normal",
    };
  }

  if (window.AffectBridge74) {
    window.AffectBridge74.finalizeBaseline();
  }

  state.session.onboarding.complete = true;

  appendLoriOnboardingMessage("Whenever you're ready, we can begin at the beginning. I'll start by helping place your story in time.");
}

/* ═══════════════════════════════════════════════════════════════
   WO-10H: Narrator Turn-Claim Contract
   Explicit state machine for respectful narrator floor-claiming.
   States: idle → awaiting_tts_end → armed_for_narrator → recording → idle
═══════════════════════════════════════════════════════════════ */

const WO10H_SILENT_WAIT_MS   = 45000;   // 0-45s: silent wait
const WO10H_VISUAL_CUE_MS    = 45000;   // 45-60s: subtle visual cue
const WO10H_CHECKIN_MS        = 60000;   // 60s: one gentle check-in

let _wo10hTimeoutTimer    = null;
let _wo10hVisualCueTimer  = null;

/** Narrator claims the next turn while Lori TTS is still speaking. */
function _wo10hClaimTurn() {
  if (!state.narratorTurn) return;
  state.narratorTurn.state            = "awaiting_tts_end";
  state.narratorTurn.claimTimestamp    = Date.now();
  state.narratorTurn.interruptionBlock = "narrator_claimed_turn";
  state.narratorTurn.checkInFired      = false;
  state.narratorTurn.timeoutDeadline   = null;

  // Suppress idle nudges while narrator owns the floor
  if (typeof lv80ClearIdle === "function") lv80ClearIdle();

  console.log("[WO-10H] Narrator claimed turn — awaiting TTS end.");
  _wo10hSyncUI();
}
window._wo10hClaimTurn = _wo10hClaimTurn;

/** Transition from awaiting_tts_end → armed_for_narrator. Called from drainTts finally. */
function _wo10hTransitionToArmed() {
  if (!state.narratorTurn) return;
  state.narratorTurn.state            = "armed_for_narrator";
  state.narratorTurn.ttsFinishedAt    = Date.now();
  state.narratorTurn.interruptionBlock = "narrator_claimed_turn";
  state.narratorTurn.timeoutDeadline   = Date.now() + WO10H_CHECKIN_MS;

  // Suppress all idle/nudge timers — narrator owns the floor
  if (typeof lv80ClearIdle === "function") lv80ClearIdle();

  console.log("[WO-10H] TTS finished — narrator armed. Starting capture.");

  // Start recording now that TTS is done
  if (!isRecording && !_wo8VoicePaused && !listeningPaused) {
    startRecording();
    state.narratorTurn.state = "recording";
  }

  // Arm timeout timers
  _wo10hArmTimeout();
  _wo10hSyncUI();
}
window._wo10hTransitionToArmed = _wo10hTransitionToArmed;

/** Arm the staged timeout: visual cue at 45s, gentle check-in at 60s. */
function _wo10hArmTimeout() {
  _wo10hClearTimeout();
  if (!state.narratorTurn) return;

  // Visual cue at 45s
  _wo10hVisualCueTimer = setTimeout(function () {
    if (state.narratorTurn.state === "idle") return;
    // Show subtle visual cue
    const cue = document.getElementById("lv80IdleCue");
    if (cue) cue.classList.add("visible");
    console.log("[WO-10H] Visual cue — narrator still has floor.");
  }, WO10H_VISUAL_CUE_MS);

  // Gentle check-in at 60s — fires only once
  _wo10hTimeoutTimer = setTimeout(function () {
    if (state.narratorTurn.state === "idle") return;
    if (state.narratorTurn.checkInFired) return;

    state.narratorTurn.state = "timeout_check";
    state.narratorTurn.checkInFired = true;

    console.log("[WO-10H] Timeout check-in — one gentle prompt.");

    // Send one soft, non-intrusive check-in
    if (typeof sendSystemPrompt === "function") {
      sendSystemPrompt("[SYSTEM: The narrator claimed the floor but has not submitted yet. This is normal — they may be thinking or typing. Offer ONE very gentle, non-intrusive presence statement. Say something like: 'Take your time. I'm here when you're ready.' Do NOT ask a new question. Do NOT give a memory nudge. Do NOT comment on the silence. One short sentence maximum.]");
    }

    // Return to armed state after check-in — do NOT clear the claim
    state.narratorTurn.state = "armed_for_narrator";
    _wo10hSyncUI();
  }, WO10H_CHECKIN_MS);
}

function _wo10hClearTimeout() {
  if (_wo10hTimeoutTimer) { clearTimeout(_wo10hTimeoutTimer); _wo10hTimeoutTimer = null; }
  if (_wo10hVisualCueTimer) { clearTimeout(_wo10hVisualCueTimer); _wo10hVisualCueTimer = null; }
  const cue = document.getElementById("lv80IdleCue");
  if (cue) cue.classList.remove("visible");
}

/** Clear narrator turn-claim and return to idle. Called on Send, Cancel, or explicit reset. */
function wo10hReleaseTurn(reason) {
  if (!state.narratorTurn) return;
  const prev = state.narratorTurn.state;
  state.narratorTurn.state            = "idle";
  state.narratorTurn.claimTimestamp    = null;
  state.narratorTurn.timeoutDeadline   = null;
  state.narratorTurn.interruptionBlock = null;
  state.narratorTurn.checkInFired      = false;
  _wo10hClearTimeout();

  if (prev !== "idle") {
    console.log("[WO-10H] Turn released:", reason || "unknown");
  }
  _wo10hSyncUI();
}
window.wo10hReleaseTurn = wo10hReleaseTurn;

/** Cancel a pending claim (e.g. narrator decides not to speak). */
function wo10hCancelClaim() {
  if (isRecording) stopRecording();
  wo10hReleaseTurn("narrator_cancelled");
}
window.wo10hCancelClaim = wo10hCancelClaim;

/** Check if narrator turn interruption blocking is active. Used by idle/nudge guards. */
function wo10hIsNarratorTurnActive() {
  return state.narratorTurn && state.narratorTurn.state !== "idle";
}
window.wo10hIsNarratorTurnActive = wo10hIsNarratorTurnActive;

/** Called when narrator shows activity (typing, speaking) — re-arm timeout. */
function _wo10hOnNarratorActivity() {
  if (!state.narratorTurn || state.narratorTurn.state === "idle") return;
  // Reset timeout deadlines since narrator is active
  state.narratorTurn.timeoutDeadline = Date.now() + WO10H_CHECKIN_MS;
  _wo10hArmTimeout();
}
window._wo10hOnNarratorActivity = _wo10hOnNarratorActivity;

/** Sync header controls and Bug Panel UI for turn state. */
function _wo10hSyncUI() {
  // Sync header mic button to show claim state
  const micBtn = document.getElementById("lv10dMicBtn");
  const micLabel = document.getElementById("lv10dMicLabel");
  if (micBtn && state.narratorTurn) {
    if (state.narratorTurn.state === "awaiting_tts_end") {
      micBtn.classList.remove("active", "paused");
      micBtn.classList.add("paused"); // yellow = waiting
      if (micLabel) micLabel.textContent = "Mic (Claiming…)";
    } else if (state.narratorTurn.state === "armed_for_narrator" || state.narratorTurn.state === "recording") {
      micBtn.classList.remove("paused");
      micBtn.classList.add("active");
      if (micLabel) micLabel.textContent = "Mic (Your Turn)";
    }
  }
}
window._wo10hSyncUI = _wo10hSyncUI;

/* ═══════════════════════════════════════════════════════════════
   WO-10D: Header Input Controls + Bug Panel
   Persistent header Mic / Camera toggles wired to real functions.
   Bug Panel with live diagnostics, LLM tuning (WO-10E), route checks.
═══════════════════════════════════════════════════════════════ */

/* ── WO-10D: LLM tuning parameters (WO-10E) ── */
window._lv10dLlmParams = { temperature: 0.7, max_new_tokens: 512 };

function lv10dSetLlmParam(key, value) {
  window._lv10dLlmParams[key] = Number(value);
  console.log("[WO-10E] LLM param set:", key, "=", Number(value));
}
window.lv10dSetLlmParam = lv10dSetLlmParam;

/* ── WO-10D: Header Mic toggle ──
   Wires to real wo8PauseListening / wo8ResumeListening when WO-8 voice
   is active, otherwise uses toggleRecording / stopRecording. */
function lv10dToggleMic() {
  // If WO-8 voice is paused, resume it
  if (_wo8VoicePaused || listeningPaused) {
    if (typeof wo8ResumeListening === "function") wo8ResumeListening();
    // Also clear WO-11B pause
    listeningPaused = false;
    const pauseBtn = document.getElementById("btnPause");
    if (pauseBtn) { pauseBtn.classList.remove("paused"); pauseBtn.textContent = "Pause"; }
    lv10dSyncHeaderControls();
    return;
  }
  // If mic is active, pause/stop it
  if (isRecording) {
    if (typeof wo8PauseListening === "function") wo8PauseListening();
    lv10dSyncHeaderControls();
    return;
  }
  // Mic is off — start recording
  if (typeof startRecording === "function") startRecording();
  lv10dSyncHeaderControls();
}
window.lv10dToggleMic = lv10dToggleMic;

/* ── WO-10D: Header Camera toggle ──
   Camera ON must go through consent path. Camera OFF calls stopEmotionEngine. */
function lv10dToggleCamera() {
  if (cameraActive) {
    if (typeof stopEmotionEngine === "function") stopEmotionEngine();
    lv10dSyncHeaderControls();
    return;
  }
  // Camera ON — must go through consent
  if (typeof beginCameraConsent74 === "function") {
    beginCameraConsent74({ cameraForPacing: true, profilePhotoEnabled: false }).then(function () {
      lv10dSyncHeaderControls();
    });
  } else if (typeof startEmotionEngine === "function") {
    startEmotionEngine().then(function () {
      lv10dSyncHeaderControls();
    });
  }
}
window.lv10dToggleCamera = lv10dToggleCamera;

/* ── WO-10D: Sync header control visuals from real state ── */
function lv10dSyncHeaderControls() {
  const micBtn = document.getElementById("lv10dMicBtn");
  const camBtn = document.getElementById("lv10dCamBtn");
  const micLabel = document.getElementById("lv10dMicLabel");
  const camLabel = document.getElementById("lv10dCamLabel");

  if (micBtn) {
    micBtn.classList.remove("active", "paused");
    if (_wo8VoicePaused || listeningPaused) {
      micBtn.classList.add("paused");
      if (micLabel) micLabel.textContent = "Mic (Paused)";
    } else if (isRecording) {
      micBtn.classList.add("active");
      if (micLabel) micLabel.textContent = "Mic (On)";
    } else {
      if (micLabel) micLabel.textContent = "Mic";
    }
  }

  if (camBtn) {
    camBtn.classList.remove("active", "paused");
    if (cameraActive) {
      camBtn.classList.add("active");
      if (camLabel) camLabel.textContent = "Cam (On)";
    } else {
      if (camLabel) camLabel.textContent = "Cam";
    }
  }

  // Also sync inputState for Bug Panel
  if (state.inputState) {
    state.inputState.micActive = !!isRecording;
    state.inputState.micPaused = !!(_wo8VoicePaused || listeningPaused);
    state.inputState.cameraActive = !!cameraActive;
    state.inputState.cameraConsent = !!(state.session?.onboarding?.cameraForPacing);
  }
}
window.lv10dSyncHeaderControls = lv10dSyncHeaderControls;

/* ── WO-10D: Bug Panel refresh ── */
let _lv10dBugPanelTimer = null;

function lv10dRefreshBugPanel() {
  const panel = document.getElementById("lv10dBugPanel");
  if (!panel) return;

  // Sync header controls first
  lv10dSyncHeaderControls();

  const _v = (id, text, cls) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = "lv10d-bp-value" + (cls ? " " + cls : "");
  };

  // Session
  const narratorName = document.getElementById("lv80ActiveNarratorName");
  _v("lv10dBpNarrator", narratorName?.textContent || "—");
  _v("lv10dBpPid", state.person_id || "—", state.person_id ? "" : "off");
  _v("lv10dBpMode", getCurrentMode());
  _v("lv10dBpPassEra", getCurrentPass() + " / " + (getCurrentEra() || "—"));
  _v("lv10dBpRole", getAssistantRole());
  _v("lv10dBpLlmReady", _llmReady ? "Yes" : "No", _llmReady ? "ok" : "err");

  // Inputs
  _v("lv10dBpMic", isRecording ? "ON" : "OFF", isRecording ? "ok" : "off");
  _v("lv10dBpPaused", listeningPaused ? "YES" : "no", listeningPaused ? "warn" : "");
  _v("lv10dBpWo8Paused", _wo8VoicePaused ? "YES" : "no", _wo8VoicePaused ? "warn" : "");
  _v("lv10dBpCam", cameraActive ? "ON" : "OFF", cameraActive ? "ok" : "off");
  _v("lv10dBpEmotion", emotionAware ? "ON" : "OFF", emotionAware ? "ok" : "off");

  // WO-04: Camera preview, facial consent, STT engine
  const previewEl = document.getElementById("lv74-cam-preview");
  const previewVisible = previewEl && !previewEl.classList.contains("lv74-preview-hidden");
  _v("lv10dBpCamPreview", previewEl ? (previewVisible ? "Visible" : "Hidden") : "Not created", previewEl ? (previewVisible ? "ok" : "warn") : "off");

  const fcGranted = typeof FacialConsent !== "undefined" && FacialConsent.isGranted();
  const fcDeclined = typeof FacialConsent !== "undefined" && FacialConsent.isDeclined();
  _v("lv10dBpFacialConsent", fcGranted ? "Granted" : (fcDeclined ? "Declined" : "Pending"), fcGranted ? "ok" : (fcDeclined ? "err" : "warn"));

  let consentStored = false;
  try { consentStored = localStorage.getItem("lorevox_facial_consent_granted") === "true"; } catch(_){}
  _v("lv10dBpConsentStored", consentStored ? "Yes (persistent)" : "No", consentStored ? "ok" : "off");

  const hasSR = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  _v("lv10dBpSttEngine", hasSR ? "Web Speech API" : "None (browser unsupported)", hasSR ? "ok" : "err");

  // Affect / visual signals
  const vs = state.session?.visualSignals;
  const hasFresh = !!(vs?.affectState && vs?.timestamp && (Date.now() - vs.timestamp < 8000));
  _v("lv10dBpAffect", hasFresh ? vs.affectState + " (" + (vs.confidence * 100).toFixed(0) + "%)" : (state.runtime?.affectState || "neutral"), hasFresh ? "ok" : "off");
  _v("lv10dBpSignalAge", vs?.timestamp ? ((Date.now() - vs.timestamp) / 1000).toFixed(1) + "s" : "—", hasFresh ? "" : (vs?.timestamp ? "warn" : "off"));

  // WO-10H: Narrator turn-state
  const nt = state.narratorTurn;
  if (nt) {
    const turnCls = nt.state === "idle" ? "off" : (nt.state === "awaiting_tts_end" ? "warn" : "ok");
    _v("lv10dBpTurnState", nt.state, turnCls);
    _v("lv10dBpTtsActive", isLoriSpeaking ? "YES" : "no", isLoriSpeaking ? "warn" : "");
    _v("lv10dBpTtsFinished", nt.ttsFinishedAt ? new Date(nt.ttsFinishedAt).toLocaleTimeString() : "—", nt.ttsFinishedAt ? "" : "off");
    _v("lv10dBpTurnClaimed", nt.claimTimestamp ? ((Date.now() - nt.claimTimestamp) / 1000).toFixed(1) + "s ago" : "no", nt.claimTimestamp ? "ok" : "off");
    _v("lv10dBpInterruptBlock", nt.interruptionBlock || "none", nt.interruptionBlock ? "warn" : "");
    _v("lv10dBpTimeoutAt", nt.timeoutDeadline ? ((nt.timeoutDeadline - Date.now()) / 1000).toFixed(0) + "s" : "—", nt.timeoutDeadline ? (nt.timeoutDeadline < Date.now() ? "err" : "warn") : "off");
  }

  // Memory — check asynchronously
  _v("lv10dBpRollingSummary", "—", "off");
  _v("lv10dBpRecentTurns", "—", "off");
  if (state.person_id) {
    const pid = state.person_id;
    // Rolling summary check
    fetch(ORIGIN + "/api/transcript/rolling-summary?person_id=" + pid, { method: "GET" })
      .then(r => { _v("lv10dBpRollingSummary", r.ok ? "OK (" + r.status + ")" : "ERR " + r.status, r.ok ? "ok" : "err"); })
      .catch(() => { _v("lv10dBpRollingSummary", "UNREACHABLE", "err"); });
    // Recent turns check
    fetch(ORIGIN + "/api/transcript/recent-turns?person_id=" + pid + "&session_id=default&limit=1", { method: "GET" })
      .then(r => { _v("lv10dBpRecentTurns", r.ok ? "OK (" + r.status + ")" : "ERR " + r.status, r.ok ? "ok" : "err"); })
      .catch(() => { _v("lv10dBpRecentTurns", "UNREACHABLE", "err"); });
  }

  // Services
  _v("lv10dBpWs", (ws && wsReady) ? "Connected" : (usingFallback ? "Fallback (SSE)" : "Disconnected"), (ws && wsReady) ? "ok" : "err");
  // WO-10K: Use real health routes — /api/ping for API, /api/health for TTS
  fetch(ORIGIN + "/api/ping", { method: "GET", signal: AbortSignal.timeout(3000) })
    .then(r => { _v("lv10dBpApi", r.ok ? "OK" : "ERR " + r.status, r.ok ? "ok" : "err"); })
    .catch(() => { _v("lv10dBpApi", "DOWN", "err"); });
  fetch(TTS_ORIG + "/api/health", { method: "GET", signal: AbortSignal.timeout(3000) })
    .then(r => { _v("lv10dBpTts", r.ok ? "OK" : "ERR " + r.status, r.ok ? "ok" : "err"); })
    .catch(() => { _v("lv10dBpTts", "DOWN", "err"); });

  // Warnings
  const warnings = [];
  if (!_llmReady) warnings.push("LLM not ready — model still warming up");
  if (!(ws && wsReady)) warnings.push("WebSocket disconnected");
  if (vs?.timestamp && (Date.now() - vs.timestamp >= 8000) && cameraActive) warnings.push("Visual signal stale (>8s) — camera may have frozen");
  if (cameraActive && !emotionAware) warnings.push("Camera active but emotionAware is false — state inconsistency");
  if (listeningPaused && isRecording) warnings.push("Mic recording while listening is paused — state conflict");
  if (nt && nt.state === "awaiting_tts_end" && !isLoriSpeaking) warnings.push("Turn state stuck in awaiting_tts_end but TTS is not active");
  if (nt && nt.state !== "idle" && nt.checkInFired) warnings.push("Check-in already fired for this claimed turn");
  // WO-04: Consent/camera consistency checks
  if (emotionAware && typeof FacialConsent !== "undefined" && FacialConsent.isDeclined()) warnings.push("emotionAware=true but facial consent was declined — camera will not start");
  if (cameraActive && !document.getElementById("lv74-cam-preview")) warnings.push("Camera active but preview DOM not created — camera-preview.js may not be loaded");

  const warnList = document.getElementById("lv10dBpWarnings");
  if (warnList) {
    if (warnings.length === 0) {
      warnList.innerHTML = '<li style="color:#4ade80;">No warnings</li>';
    } else {
      warnList.innerHTML = warnings.map(w => '<li>' + w.replace(/</g, '&lt;') + '</li>').join("");
    }
  }
}
window.lv10dRefreshBugPanel = lv10dRefreshBugPanel;

/* ── WO-10D: Route health check ── */
async function lv10dCheckRoutes() {
  const routes = [
    { label: "ping",            url: ORIGIN + "/api/ping" },
    { label: "rolling-summary", url: ORIGIN + "/api/transcript/rolling-summary?person_id=" + (state.person_id || "test") },
    { label: "recent-turns",   url: ORIGIN + "/api/transcript/recent-turns?person_id=" + (state.person_id || "test") + "&session_id=default&limit=1" },
    { label: "history",        url: ORIGIN + "/api/transcript/history?person_id=" + (state.person_id || "test") },
    { label: "sessions",       url: ORIGIN + "/api/transcript/sessions?person_id=" + (state.person_id || "test") },
    { label: "thread-anchor",  url: ORIGIN + "/api/transcript/thread-anchor?person_id=" + (state.person_id || "test") },
  ];
  const results = [];
  for (const r of routes) {
    try {
      const resp = await fetch(r.url, { method: "GET", signal: AbortSignal.timeout(5000) });
      results.push(r.label + ": " + resp.status + (resp.ok ? " OK" : " FAIL"));
    } catch (e) {
      results.push(r.label + ": UNREACHABLE");
    }
  }
  console.log("[WO-10D] Route check:\n" + results.join("\n"));
  alert("Route Check Results:\n\n" + results.join("\n"));
}
window.lv10dCheckRoutes = lv10dCheckRoutes;

/* ── WO-10D: Copy diagnostics to clipboard ── */
function lv10dCopyDiag() {
  const diag = {
    ts: new Date().toISOString(),
    narrator: document.getElementById("lv80ActiveNarratorName")?.textContent || null,
    person_id: state.person_id,
    mode: getCurrentMode(),
    pass: getCurrentPass(),
    era: getCurrentEra(),
    role: getAssistantRole(),
    llmReady: _llmReady,
    mic: { recording: isRecording, paused: listeningPaused, wo8Paused: _wo8VoicePaused },
    camera: { active: cameraActive, emotionAware: emotionAware, previewVisible: !!document.getElementById("lv74-cam-preview") },
    facialConsent: { granted: typeof FacialConsent !== "undefined" && FacialConsent.isGranted(), stored: (() => { try { return localStorage.getItem("lorevox_facial_consent_granted") === "true"; } catch(_) { return false; } })() },
    visualSignals: state.session?.visualSignals || null,
    ws: { connected: !!(ws && wsReady), fallback: usingFallback },
    llmParams: window._lv10dLlmParams,
  };
  const text = JSON.stringify(diag, null, 2);
  navigator.clipboard.writeText(text).then(() => {
    console.log("[WO-10D] Diagnostics copied to clipboard.");
    alert("Diagnostics copied to clipboard.");
  }).catch(() => {
    console.log("[WO-10D] Diagnostics:\n" + text);
    alert("Copy failed — see console for diagnostics.");
  });
}
window.lv10dCopyDiag = lv10dCopyDiag;

/* ── WO-10D: Auto-refresh Bug Panel while open ── */
(function () {
  const panel = document.getElementById("lv10dBugPanel");
  if (!panel) return;
  panel.addEventListener("toggle", function (e) {
    if (panel.matches(":popover-open")) {
      lv10dRefreshBugPanel();
      _lv10dBugPanelTimer = setInterval(lv10dRefreshBugPanel, 2000);
    } else {
      if (_lv10dBugPanelTimer) { clearInterval(_lv10dBugPanelTimer); _lv10dBugPanelTimer = null; }
    }
  });
})();

/* ── WO-10D: Periodic header control sync (every 1s) ── */
setInterval(lv10dSyncHeaderControls, 1000);

/* ═══════════════════════════════════════════════════════════════
   WO-KAWA-UI-01A — River View (Kawa) UI renderers
═══════════════════════════════════════════════════════════════ */

function _escKawa(s){
  return String(s || "")
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;");
}

function renderKawaUI(){
  const root = document.getElementById("kawaPanel");
  if (!root) return;

  const kawa = state?.kawa || {};
  const segs = Array.isArray(kawa.segmentList) ? kawa.segmentList : [];
  const active = kawa.activeSegment;

  /* ── Segment list ───────────────────────────────────────────── */
  const listHtml = segs.length ? segs.map(seg => {
    const isActive = seg.segment_id === kawa.activeSegmentId;
    const flow = seg?.kawa?.water?.flow_state || "unknown";
    const status = seg?.provenance?.confirmed ? "confirmed" : "proposed";
    const label = _escKawa(seg?.anchor?.label || seg?.segment_id);
    const year = seg?.anchor?.year != null ? seg.anchor.year : "";
    return `
      <button class="kawa-segment-row ${isActive ? "active" : ""}" onclick="kawaSelectSegment('${seg.segment_id}')">
        <div class="kawa-row-top">
          <span class="kawa-row-year">${year}</span>
          <span class="kawa-row-label">${label}</span>
        </div>
        <div class="kawa-row-meta">
          <span>Flow: ${flow}</span>
          <span class="kawa-badge ${status}">${status}</span>
        </div>
      </button>
    `;
  }).join("") : '<div class="kawa-empty">No river segments yet.</div>';

  /* ── Detail pane ────────────────────────────────────────────── */
  const detailHtml = active ? `
    <div class="kawa-detail">
      <div class="kawa-toolbar">
        <button onclick="kawaBuildFromCurrentAnchor()">Rebuild</button>
        <button onclick="kawaSaveActive(false)" ${kawa.isDirty ? "" : "disabled"}>Save</button>
        <button onclick="kawaSaveActive(true)">Confirm Segment</button>
      </div>

      <section class="kawa-card">
        <h3>Flow</h3>
        <label>Flow State</label>
        <select onchange="_bindKawaField('kawa.water.flow_state', this.value)">
          ${["unknown","blocked","constricted","steady","open","strong"].map(x =>
            '<option value="' + x + '"' + (active?.kawa?.water?.flow_state === x ? " selected" : "") + '>' + x + '</option>'
          ).join("")}
        </select>
        <label>Summary</label>
        <textarea oninput="_bindKawaField('kawa.water.summary', this.value)">${_escKawa(active?.kawa?.water?.summary || "")}</textarea>
      </section>

      <section class="kawa-card">
        <h3>Rocks</h3>
        ${_renderKawaItemList("rocks", active?.kawa?.rocks || [])}
      </section>

      <section class="kawa-card">
        <h3>Driftwood</h3>
        ${_renderKawaItemList("driftwood", active?.kawa?.driftwood || [])}
      </section>

      <section class="kawa-card">
        <h3>Banks</h3>
        ${_renderKawaBanks(active?.kawa?.banks || {})}
      </section>

      <section class="kawa-card">
        <h3>Spaces</h3>
        ${_renderKawaItemList("spaces", active?.kawa?.spaces || [])}
      </section>

      <section class="kawa-card">
        <h3>Narrator Voice</h3>
        <label>Note</label>
        <textarea oninput="_bindKawaField('narrator_note', this.value)">${_escKawa(active?.narrator_note || "")}</textarea>
        <label>Quote</label>
        <textarea oninput="_bindKawaField('narrator_quote', this.value)">${_escKawa(active?.narrator_quote || "")}</textarea>
      </section>

      <section class="kawa-card">
        <h3>Status</h3>
        <div>Anchor: ${_escKawa(active?.anchor?.label || "")}</div>
        <div>Year: ${active?.anchor?.year ?? ""}</div>
        <div>Source: ${active?.provenance?.source || "unknown"}</div>
        <div>Memoir Mode: ${typeof getMemoirMode === "function" ? getMemoirMode() : "chronology"}</div>
        <div class="kawa-badge ${active?.provenance?.confirmed ? "confirmed" : "proposed"}">${active?.provenance?.confirmed ? "Confirmed" : "Proposed"}</div>
        ${active?.provenance?.confirmed ? '<div class="river-informed-badge">eligible for river-informed memoir</div>' : ""}
        ${kawa.isDirty ? '<div class="kawa-dirty">Unsaved river edits</div>' : ""}
      </section>
    </div>
  ` : `
    <div class="kawa-empty-detail">
      <p>No active river segment.</p>
      <button onclick="kawaBuildFromCurrentAnchor()">Build Proposal</button>
    </div>
  `;

  /* ── Assemble layout ────────────────────────────────────────── */
  root.innerHTML = `
    <div class="kawa-layout">
      <aside class="kawa-sidebar">
        <div class="kawa-sidebar-head">
          <h2>Memory River</h2>
          <button onclick="kawaBuildFromCurrentAnchor()">+ Build Proposal</button>
        </div>
        <div id="kawaStrip">${_renderKawaStrip(segs)}</div>
        <div class="kawa-segment-list">${listHtml}</div>
      </aside>
      <main class="kawa-main">${detailHtml}</main>
    </div>
  `;
}

/* ── Helper renderers ───────────────────────────────────────── */

function _renderKawaItemList(kind, items){
  const rows = (items || []).map((item, idx) => `
    <div class="kawa-item ${kind}">
      <input value="${_escKawa(item.label || "")}" placeholder="label"
             oninput="_updateKawaListItem('${kind}', ${idx}, 'label', this.value)">
      <textarea placeholder="notes"
                oninput="_updateKawaListItem('${kind}', ${idx}, 'notes', this.value)">${_escKawa(item.notes || "")}</textarea>
      <div class="kawa-item-actions">
        <span class="kawa-confidence">confidence: ${item.confidence ?? 0}</span>
        <button onclick="_deleteKawaListItem('${kind}', ${idx})">Delete</button>
      </div>
    </div>
  `).join("");

  return `
    <div>${rows || '<div class="kawa-empty">No ' + kind + ' yet.</div>'}</div>
    <button onclick="_addKawaListItem('${kind}')">+ Add ${kind.slice(0, -1) || kind}</button>
  `;
}

function _renderKawaBanks(banks){
  const sections = ["social","physical","cultural","institutional"];
  return sections.map(sec => `
    <div class="kawa-bank-group">
      <h4>${sec}</h4>
      ${(banks[sec] || []).map((val, idx) => `
        <div class="kawa-bank-item">
          <input value="${_escKawa(val || "")}" oninput="_updateKawaBank('${sec}', ${idx}, this.value)">
          <button onclick="_deleteKawaBank('${sec}', ${idx})">Delete</button>
        </div>
      `).join("")}
      <button onclick="_addKawaBank('${sec}')">+ Add ${sec}</button>
    </div>
  `).join("");
}

function _renderKawaStrip(segs){
  if (!Array.isArray(segs) || !segs.length) return "";
  return `
    <div class="kawa-strip">
      ${segs.map(seg => {
        const flow = seg?.kawa?.water?.flow_state || "unknown";
        const label = _escKawa(seg?.anchor?.label || seg?.segment_id);
        return '<button class="kawa-strip-seg flow-' + flow + '" onclick="kawaSelectSegment(\'' + seg.segment_id + '\')">' + label + '</button>';
      }).join("")}
    </div>
  `;
}

/* ── List item CRUD ─────────────────────────────────────────── */

function _addKawaListItem(kind){
  const seg = state?.kawa?.activeSegment;
  if (!seg) return;
  seg.kawa[kind] = seg.kawa[kind] || [];
  seg.kawa[kind].push({ label: "", notes: "", confidence: 0 });
  kawaMarkDirty();
}

function _updateKawaListItem(kind, idx, field, value){
  const seg = state?.kawa?.activeSegment;
  if (!seg?.kawa?.[kind]?.[idx]) return;
  seg.kawa[kind][idx][field] = value;
  kawaMarkDirty();
}

function _deleteKawaListItem(kind, idx){
  const seg = state?.kawa?.activeSegment;
  if (!seg?.kawa?.[kind]) return;
  seg.kawa[kind].splice(idx, 1);
  kawaMarkDirty();
}

function _addKawaBank(kind){
  const seg = state?.kawa?.activeSegment;
  if (!seg) return;
  seg.kawa.banks = seg.kawa.banks || {};
  seg.kawa.banks[kind] = seg.kawa.banks[kind] || [];
  seg.kawa.banks[kind].push("");
  kawaMarkDirty();
}

function _updateKawaBank(kind, idx, value){
  const seg = state?.kawa?.activeSegment;
  if (!seg?.kawa?.banks?.[kind]) return;
  seg.kawa.banks[kind][idx] = value;
  kawaMarkDirty();
}

function _deleteKawaBank(kind, idx){
  const seg = state?.kawa?.activeSegment;
  if (!seg?.kawa?.banks?.[kind]) return;
  seg.kawa.banks[kind].splice(idx, 1);
  kawaMarkDirty();
}


/* ═══════════════════════════════════════════════════════════════
   WO-KAWA-02A — Mode setters + memoir Kawa overlay
═══════════════════════════════════════════════════════════════ */

function setInterviewMode(mode){
  if (typeof setKawaMode === "function") setKawaMode(mode);
  if (typeof renderKawaUI === "function") renderKawaUI();
}

function setMemoirMode(mode){
  if (state?.session) state.session.memoirMode = mode;
  if (state?.kawa?.memoir) state.kawa.memoir.organizationMode = mode;
  // Re-render memoir chapters to reflect the new mode
  if (typeof renderMemoirChapters === "function") renderMemoirChapters();
}

/**
 * Build a Kawa river overlay for each chapter that has a confirmed segment.
 * Returns the chapters array with river overlay appended in chronology_river mode,
 * or a completely restructured array in river_organized mode.
 * In plain chronology mode, returns chapters unchanged.
 */
function applyKawaToMemoirChapters(chapters){
  const mode = typeof getMemoirMode === "function" ? getMemoirMode() : "chronology";
  const segs = state?.kawa?.segmentList || [];
  if (mode === "chronology" || !segs.length) return chapters;

  if (mode === "chronology_river") {
    return chapters.map(ch => {
      const seg = segs.find(s =>
        s?.provenance?.confirmed &&
        (s?.anchor?.ref_id === ch.event_id || s?.anchor?.label === ch.title || s?.anchor?.label === ch.label)
      );
      if (!seg) return ch;
      const overlay = typeof buildKawaOverlayText === "function" ? buildKawaOverlayText(seg) : "";
      if (!overlay) return ch;
      return {
        ...ch,
        river_overlay: overlay,
        river_informed: true,
        body: ch.body ? `${ch.body}\n\n${overlay}` : overlay
      };
    });
  }

  if (mode === "river_organized") {
    const confirmed = segs.filter(s => s?.provenance?.confirmed);
    if (!confirmed.length) return chapters;
    const groups = {
      "Seasons of Open Water": [],
      "Rocks That Changed the Course": [],
      "Driftwood That Kept the River Moving": [],
      "The Banks Around My Life": [],
      "Where Space Opened Again": []
    };

    confirmed.forEach(seg => {
      const flow = seg?.kawa?.water?.flow_state || "";
      if (["open","strong"].includes(flow)) groups["Seasons of Open Water"].push(seg);
      if ((seg?.kawa?.rocks || []).length) groups["Rocks That Changed the Course"].push(seg);
      if ((seg?.kawa?.driftwood || []).length) groups["Driftwood That Kept the River Moving"].push(seg);
      if ([
        ...(seg?.kawa?.banks?.social || []),
        ...(seg?.kawa?.banks?.physical || []),
        ...(seg?.kawa?.banks?.cultural || []),
        ...(seg?.kawa?.banks?.institutional || [])
      ].length) groups["The Banks Around My Life"].push(seg);
      if ((seg?.kawa?.spaces || []).length) groups["Where Space Opened Again"].push(seg);
    });

    return Object.entries(groups)
      .filter(([, arr]) => arr.length)
      .map(([title, arr], idx) => ({
        id: `river_${idx}`,
        title,
        label: title,
        river_informed: true,
        body: arr.map(seg =>
          typeof buildKawaOverlayText === "function" ? buildKawaOverlayText(seg) : ""
        ).filter(Boolean).join("\n\n")
      }));
  }

  return chapters;
}
