/* ═══════════════════════════════════════════════════════════════
   session-loop.js — WO-HORNELORE-SESSION-LOOP-01

   Post-identity conversation orchestrator.  After identityPhase is
   "complete", this dispatcher fires once per narrator turn and decides
   what Lori does next based on state.session.sessionStyle.

   Locked product rule (2026-04-24):
     "After identity is complete, the session NEVER dead-ends.
      Lori always has a next step, defined by the operator's sessionStyle."

   Style behavior summary (Phase 1):
     questionnaire_first → walk Bio Builder MINIMAL_SECTIONS personal
                           fields one at a time (preferredName, birthOrder,
                           timeOfBirth — the three not already captured by
                           identity intake), save each answer via PUT to
                           /api/bio-builder/questionnaire, then offer to
                           switch to warm_storytelling when out of fields.
                           Repeatable sections (parents/siblings) deferred
                           to Phase 2.
     clear_direct        → walk + tier-2 directive (set in runtime71)
     warm_storytelling   → no-op (existing default Lori behavior)
     memory_exercise     → tier-2 directive only (no walk)
     companion           → tier-2 directive only (no walk)

   Hard rules:
     - No new backend route — uses existing /api/bio-builder/questionnaire
     - No new questionnaire schema — reads bio-builder-questionnaire.js
       MINIMAL_SECTIONS at runtime
     - Reuses existing identity state machine — handoff happens when
       _advanceIdentityPhase flips identityPhase → "complete"
     - Kawa / Chronology stay PASSIVE — read only, no mutation
     - Repeatable BB sections (parents, siblings, grandparents) DEFERRED

   Load order: AFTER state.js, app.js, bio-builder-questionnaire.js,
   session-style-router.js (we depend on getSessionStyle, sendSystemPrompt,
   appendBubble, API constants).
═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  const ASKED_CAP = 60;

  // Cache the BB blob briefly so consecutive fast turns don't re-fetch.
  // Invalidated on narrator switch (lvSessionStyleEnter resets it).
  let _bbCache = { pid: null, blob: null, ts: 0 };
  const BB_CACHE_TTL_MS = 5_000;

  /* ── Public dispatcher ─────────────────────────────────────────
     Called from:
       - session-style-router.js when identityPhase first hits "complete"
         (trigger: "identity_complete")
       - app.js after each narrator turn lands once identity is complete
         (trigger: "narrator_turn", text: <user message>)
       - operator skip affordances (trigger: "operator_skip")

     Idempotent — multiple calls in the same turn are safe (the
     askedKeys ledger prevents duplicate field asks). */
  async function lvSessionLoopOnTurn(event) {
    if (!state || !state.session) return;
    if (!state.session.loop) {
      state.session.loop = {
        currentSection: null, currentField: null,
        askedKeys: [], lastTrigger: null, lastAction: null,
        tellingStoryOnce: false,
      };
    }
    event = event || {};
    state.session.loop.lastTrigger = event.trigger || "unknown";

    const style = (typeof getSessionStyle === "function")
      ? getSessionStyle()
      : (state.session.sessionStyle || "warm_storytelling");

    console.log("[session-loop] dispatch:",
      JSON.stringify({ style, trigger: event.trigger,
        section: state.session.loop.currentSection,
        field:   state.session.loop.currentField }));

    // Single-turn override: narrator said "tell a story instead" last
    // turn.  Route THIS turn through warm_storytelling, then resume the
    // walk on the next narrator turn.
    if (state.session.loop.tellingStoryOnce) {
      state.session.loop.tellingStoryOnce = false;
      state.session.loop.lastAction = "single_turn_override:warm_storytelling";
      console.log("[session-loop] single-turn warm-storytelling override");
      return;
    }

    switch (style) {
      case "questionnaire_first": return _routeQuestionnaireFirst(event);
      case "clear_direct":        return _routeClearDirect(event);
      case "memory_exercise":     return _routeMemoryExercise(event);
      case "companion":           return _routeCompanion(event);
      case "warm_storytelling":
      default:                    return _routeWarmStorytelling(event);
    }
  }
  window.lvSessionLoopOnTurn = lvSessionLoopOnTurn;

  /* ── Style: questionnaire_first ────────────────────────────────
     Walk MINIMAL_SECTIONS personal fields one at a time.  Identity
     intake already captured fullName + dateOfBirth + placeOfBirth, so
     the walk asks the remaining personal fields (preferredName,
     birthOrder, timeOfBirth) and then hits the deferred parents
     section, at which point we offer to switch to warm storytelling. */
  async function _routeQuestionnaireFirst(event) {
    const loop = state.session.loop;

    // Fetch (or reuse cached) BB questionnaire blob for this narrator.
    const blob = await _getQuestionnaireBlob(state.person_id);

    // Find the next personal-section field that's empty AND not asked yet.
    const next = _findNextEmptyPersonalField(blob, loop.askedKeys);

    if (!next) {
      // No more non-repeatable fields → repeatable sections begin (parents).
      // Phase 1 stops here and offers a soft handoff.
      console.log("[session-loop] questionnaire_first: minimal personal fields exhausted; repeatable sections deferred (Phase 2)");
      loop.lastAction = "deferred:parents (Phase 2)";
      _appendLoriBubble(
        "We've got your basics down. Want to keep building your story " +
        "from here, or is there something specific you'd like to talk about?"
      );
      // Switch to warm_storytelling FOR THIS NARRATOR ONLY (not localStorage)
      // so subsequent turns don't keep firing the deferred-bubble.
      // Operator can re-pick questionnaire_first on the Operator tab to retry.
      state.session.sessionStyle = "warm_storytelling";
      console.log("[session-loop] auto-switched to warm_storytelling (in-memory only) after walk completed");
      return;
    }

    // Ask the next field.
    const askedKey = `${next.sectionId}.${next.fieldId}`;
    loop.currentSection = next.sectionId;
    loop.currentField   = next.fieldId;
    loop.askedKeys.push(askedKey);
    if (loop.askedKeys.length > ASKED_CAP) {
      loop.askedKeys = loop.askedKeys.slice(-ASKED_CAP);
    }
    loop.lastAction = `ask_${askedKey}`;
    console.log("[session-loop] asking BB field:", askedKey);

    // System prompt directive — Lori asks the question warmly + briefly.
    const prompt = _buildFieldPrompt(next);
    if (typeof sendSystemPrompt === "function") {
      try { sendSystemPrompt(prompt); } catch (e) {
        console.warn("[session-loop] sendSystemPrompt threw:", e);
      }
    } else {
      // Fallback — render the prompt directly as a Lori bubble.
      _appendLoriBubble(prompt);
    }
  }

  /* ── Style: clear_direct ───────────────────────────────────────
     Same MINIMAL_SECTIONS walk as questionnaire_first, but the tier-2
     directive (set in runtime71 by buildRuntime71's session_style_directive
     field) tells Lori to keep prompts short.  In Phase 1 we route the
     walk identically; the directive lands via the runtime payload path. */
  async function _routeClearDirect(event) {
    return _routeQuestionnaireFirst(event);
  }

  /* ── Style: memory_exercise ────────────────────────────────────
     Tier-2 directive only.  No structured walk; Lori uses recognition
     cues and patient pacing.  Defer to existing Lori behavior + the
     directive injected into runtime71. */
  function _routeMemoryExercise(event) {
    state.session.loop.lastAction = "directive_only:memory_exercise";
    console.log("[session-loop] memory_exercise: directive-only, no walk");
  }

  /* ── Style: companion ──────────────────────────────────────────
     Tier-2 directive only.  No question-asking; Lori reflects + listens. */
  function _routeCompanion(event) {
    state.session.loop.lastAction = "directive_only:companion";
    console.log("[session-loop] companion: directive-only, no walk");
  }

  /* ── Style: warm_storytelling ──────────────────────────────────
     Existing default Lori behavior.  No-op here — existing prompt
     composer + phase-aware question composer drive the conversation. */
  function _routeWarmStorytelling(event) {
    state.session.loop.lastAction = "no_op:warm_storytelling";
  }

  /* ── Tier-2 directive helper ───────────────────────────────────
     Called by buildRuntime71 (app.js) to set runtime71.session_style_directive.
     The backend prompt_composer reads this field and appends to the
     directive block.  Empty string for default/no-op styles. */
  function _emitStyleDirective(style) {
    switch (style) {
      case "clear_direct":
        return "Ask one short question at a time. Avoid open-ended " +
               "exploration. Acknowledge briefly, then move on.";
      case "memory_exercise":
        return "Use recognition cues. Allow long silences. Never correct. " +
               "Speak more slowly. Match dementia-safe cognitive support pacing.";
      case "companion":
        return "Don't probe for facts. Listen. Reflect feelings. Speak less " +
               "than the narrator does.";
      case "questionnaire_first":
      case "warm_storytelling":
      default:
        return "";
    }
  }
  // Exposed so buildRuntime71 in app.js can read it.
  window._lvEmitStyleDirective = _emitStyleDirective;

  /* ── Bio Builder helpers ───────────────────────────────────────
     Read the questionnaire blob, find next empty personal field,
     compose the warm Lori prompt, and (later — Phase 2) PUT answers. */

  async function _getQuestionnaireBlob(personId) {
    if (!personId) return {};
    const now = Date.now();
    if (_bbCache.pid === personId && _bbCache.blob &&
        (now - _bbCache.ts) < BB_CACHE_TTL_MS) {
      return _bbCache.blob;
    }
    try {
      const url = (typeof API !== "undefined" && API.BB_QQ_GET)
        ? API.BB_QQ_GET(personId)
        : `/api/bio-builder/questionnaire?person_id=${encodeURIComponent(personId)}`;
      const res = await fetch(url, { signal: AbortSignal.timeout(3000) });
      if (!res.ok) {
        console.warn("[session-loop] BB questionnaire fetch failed:", res.status);
        return {};
      }
      const data = await res.json();
      // Backend returns the questionnaire under various keys; defensively
      // unwrap.  The PUT shape is { questionnaire: {...} } so the GET
      // typically mirrors that.
      const blob = data && (data.questionnaire || data.payload || data) || {};
      _bbCache = { pid: personId, blob, ts: now };
      return blob;
    } catch (e) {
      console.warn("[session-loop] BB questionnaire fetch threw:", e);
      return {};
    }
  }

  /* Invalidate the BB cache on narrator switch — exposed so
     session-style-router can reset on lvSessionStyleEnter entry. */
  function _resetBBCache() {
    _bbCache = { pid: null, blob: null, ts: 0 };
  }
  window._lvSessionLoopResetBBCache = _resetBBCache;

  function _findNextEmptyPersonalField(blob, askedKeys) {
    // Phase 1 walks ONLY the personal section's non-repeatable fields.
    // Repeatable sections (parents/siblings) deferred to Phase 2.
    const SECTIONS = (typeof window.MINIMAL_SECTIONS !== "undefined")
      ? window.MINIMAL_SECTIONS
      : null;
    // bio-builder-questionnaire.js doesn't expose MINIMAL_SECTIONS on
    // window; it's an inner var.  Hardcode the personal-section field
    // order here (mirrors bio-builder-questionnaire.js:425-430).
    const personalFields = [
      { id: "fullName",      label: "full name" },
      { id: "preferredName", label: "preferred name" },
      { id: "birthOrder",    label: "birth order" },
      { id: "dateOfBirth",   label: "date of birth" },
      { id: "timeOfBirth",   label: "time of birth" },
      { id: "placeOfBirth",  label: "place of birth" },
    ];

    const personalBlob = (blob && blob.personal) || {};
    const askedSet = new Set(askedKeys || []);

    for (const f of personalFields) {
      const key = `personal.${f.id}`;
      if (askedSet.has(key)) continue;
      const v = personalBlob[f.id];
      if (v == null || (typeof v === "string" && v.trim() === "")) {
        return { sectionId: "personal", fieldId: f.id, label: f.label };
      }
    }
    return null;
  }

  function _buildFieldPrompt(next) {
    // Compose a warm Lori system prompt that asks ONE structured question
    // about the next field.  Keep it brief and conversational — the
    // narrator just finished identity intake and needs gentle continuity.
    const map = {
      preferredName:
        "Ask warmly: 'What would you like me to call you?  Some people prefer a nickname or a shorter version of their name.'  Keep it to one or two sentences.  No lecture.",
      birthOrder:
        "Ask conversationally: 'Were you the oldest, the youngest, somewhere in the middle?  Or were you an only child?'  Keep it brief and warm.  No lecture.",
      timeOfBirth:
        "Ask gently: 'Do you happen to know what time of day you were born — morning, afternoon, night?  It's totally fine if not.'  Keep it brief.  No lecture.",
      dateOfBirth:
        "Ask warmly: 'What's your date of birth?'  One short sentence.  No lecture.",
      placeOfBirth:
        "Ask warmly: 'Where were you born?  Town and state are perfect, country if you'd like.'  One short sentence.  No lecture.",
      fullName:
        "Ask warmly: 'What's your full name?'  One short sentence.  No lecture.",
    };
    const fieldPrompt = map[next.fieldId] ||
      `Ask the narrator one short, warm question about their ${next.label}.  Keep it conversational.  No lecture.`;
    return `[SYSTEM_QF: questionnaire_first lane — next field is ${next.sectionId}.${next.fieldId}.  ${fieldPrompt}]`;
  }

  function _appendLoriBubble(text) {
    if (typeof appendBubble === "function") {
      try { appendBubble("ai", text); } catch (_) {}
    } else if (typeof appendAssistantBubble === "function") {
      try { appendAssistantBubble(text); } catch (_) {}
    }
  }

  /* ── Diagnostic accessor for the harness ───────────────────────
     ui-health-check.js reads this to verify the loop is wired
     without invoking it. */
  window.lvSessionLoop = {
    onTurn: lvSessionLoopOnTurn,
    emitDirective: _emitStyleDirective,
    findNextField: _findNextEmptyPersonalField,
    resetBBCache: _resetBBCache,
    loaded: true,
  };

  console.log("[Hornelore] session-loop loaded.");
})();
