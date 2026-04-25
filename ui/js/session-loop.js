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
        askedKeys: [], savedKeys: [], lastTrigger: null, lastAction: null,
        tellingStoryOnce: false,
      };
    }
    // WO-01B: belt-and-suspenders for sessions with a stale state.js
    // that initialized loop without savedKeys.
    if (!Array.isArray(state.session.loop.savedKeys)) {
      state.session.loop.savedKeys = [];
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
     section, at which point we offer to switch to warm storytelling.

     WO-01B: On narrator_turn, the previously-asked field's answer gets
     PUT to /api/bio-builder/questionnaire BEFORE we look for the next
     empty field — turns the loop from "asks questions" into "actually
     builds the record".
  ─────────────────────────────────────────────────────────────── */
  async function _routeQuestionnaireFirst(event) {
    const loop = state.session.loop;

    // BUG-212: digression detector.  When the narrator's reply is a
    // long-form story rather than an answer to the asked structured
    // field, do NOT save it to that field (would pollute the scalar)
    // and do NOT fire the next-field SYSTEM_QF prompt this turn.
    // Live evidence: Jake (test session 119bf732) said "I turn the
    // camera on for you that elbow Woods was a fun place on the river
    // too bad they had to ruin it and flood it" — Lori then dismissed
    // it with "That's a nice detail, but I didn't ask about time of
    // birth earlier" because the loop fired SYSTEM_QF timeOfBirth
    // immediately after.  Violates WO-10C (no correction, listen-first).
    function _isDigressionAnswer(text, fieldId) {
      if (!text || typeof text !== "string") return false;
      const t = text.trim();
      const wc = t.split(/\s+/).filter(Boolean).length;
      // Hard length cutoff: anything > 120 chars or > 18 words is a
      // narrative, regardless of field.  Older-adult narrators give
      // succinct answers to structured Qs; long replies are stories.
      const longForm = (t.length > 120) || (wc > 18);
      // Memory markers — phrases that signal the narrator went into
      // narrative mode rather than answering.
      const STORY_CUES = /\b(too bad|fun place|great place|loved|hated|i miss|i remember|back then|growing up|reminds me|wish|story|kids|that was|those days|when i was)\b/i;
      const hasStoryCue = STORY_CUES.test(t);
      // Field-shape mismatch: most BB fields expect short tokens.
      // birthOrder = oldest/youngest/middle/etc; timeOfBirth = morning/etc.
      const SHORT_FIELDS = ["birthOrder", "timeOfBirth", "preferredName"];
      const fieldExpectsShort = SHORT_FIELDS.includes(fieldId);
      // A short field with a long reply is a clear digression.
      // A long field (placeOfBirth, fullName, dateOfBirth) tolerates
      // longer answers; we still bail on extreme length + story cues.
      if (fieldExpectsShort && (longForm || hasStoryCue)) return true;
      if (longForm && hasStoryCue) return true;
      // Extra-long across the board.
      if (t.length > 200 || wc > 30) return true;
      return false;
    }

    // WO-01B: Save the answer to the field we asked last turn (if any).
    // Only fires on narrator_turn (not identity_complete which is the
    // first call where currentField is null).
    if (event && event.trigger === "narrator_turn" &&
        loop.currentSection && loop.currentField &&
        typeof event.text === "string" && event.text.trim()) {
      // BUG-212: digression check BEFORE save.
      if (_isDigressionAnswer(event.text, loop.currentField)) {
        const askedKey = `${loop.currentSection}.${loop.currentField}`;
        loop.lastAction = `digression_skip_save_${askedKey}`;
        loop.tellingStoryOnce = true;   // suppress next turn's QF too
        console.log(`[session-loop] BUG-212: digression detected on ${askedKey} ` +
          `(${event.text.length}c / ${event.text.trim().split(/\s+/).length}w). ` +
          `Skipping save + skipping next-field prompt. Letting Lori respond naturally.`);
        // Don't ask "what was your story you wanted to tell?" — just
        // let warm_storytelling drive THIS turn (Lori will respond to
        // whatever the narrator just said in her natural reflective voice).
        return;
      }
      await _saveBBAnswer(state.person_id, loop.currentSection,
                          loop.currentField, event.text.trim());
      // Cache is invalidated inside _saveBBAnswer so the next
      // _getQuestionnaireBlob call re-fetches the freshly-PUT blob.
    }

    // Fetch (or reuse cached) BB questionnaire blob for this narrator.
    const blob = await _getQuestionnaireBlob(state.person_id);

    // Find the next personal-section field that's empty AND not asked yet.
    const next = _findNextEmptyPersonalField(blob, loop.askedKeys);

    if (!next) {
      // WO-01C: No more non-repeatable personal fields → name what's
      // coming so the narrator doesn't dead-end on a vague bubble.
      // Repeatable sections (parents/siblings/grandparents/residences)
      // are still deferred to Phase 2 of the loop, but we explicitly
      // offer the next obvious branches so Lori has a real handoff.
      console.log("[session-loop] questionnaire_first: minimal personal fields exhausted; repeatable sections deferred (Phase 2)");
      loop.lastAction = "deferred:repeatable_sections (Phase 2)";

      // Pull whatever we have for warmth (preferredName / fullName).
      const blobNow = await _getQuestionnaireBlob(state.person_id);
      const personal = (blobNow && blobNow.personal) || {};
      const greetName = (personal.preferredName || personal.fullName || "").trim();

      // Use a system prompt so Lori delivers the handoff in her voice
      // (warm, brief), rather than dropping a hard-coded UI bubble.
      const handoffPrompt = "[SYSTEM_QF: questionnaire_first lane — " +
        "the personal-basics walk is COMPLETE. Lori must now offer " +
        "the narrator a clear next branch in two or three sentences. " +
        "Acknowledge what we just covered briefly. Then say something " +
        "like: 'we can talk about the people who shaped you next — your " +
        "parents, your siblings, the people you grew up around — or you " +
        "can pick a memory you'd like to share, your call.' " +
        "Do NOT lecture. Do NOT list. Do NOT promise to build a database. " +
        "Just warmly hand off the conversation. " +
        (greetName ? `You may use the name "${greetName}" once if it lands naturally. ` : "") +
        "Two to three sentences total.]";

      if (typeof sendSystemPrompt === "function") {
        try { sendSystemPrompt(handoffPrompt); } catch (e) {
          console.warn("[session-loop] handoff sendSystemPrompt threw:", e);
          _appendLoriBubble(
            "Your basics are saved. We can talk about the people who " +
            "shaped you — your parents, your siblings, the people you " +
            "grew up around — or you can pick a memory you'd like to " +
            "share, your call."
          );
        }
      } else {
        _appendLoriBubble(
          "Your basics are saved. We can talk about the people who " +
          "shaped you — your parents, your siblings, the people you " +
          "grew up around — or you can pick a memory you'd like to " +
          "share, your call."
        );
      }

      // Switch to warm_storytelling FOR THIS NARRATOR ONLY (not localStorage)
      // so subsequent turns don't keep re-firing the handoff prompt.
      // Operator can re-pick questionnaire_first on the Operator tab to
      // walk again (e.g. after Phase 2 ships repeatable section walking).
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

  /* ── BUG-218: Capabilities honesty rule (always included) ──
     Lori was caught hallucinating capabilities — narrator asked "are you
     saving the audio from this question" and Lori answered "Yes, I am
     saving the audio."  Audio capture isn't built yet (WO-AUDIO-NARRATOR-
     ONLY-01 is the next step).  Parents could trust this answer and
     share intimate content believing it's preserved.
     Fix: every session_style_directive prepends a hard honesty rule
     about what's actually captured RIGHT NOW.
     TODO: when WO-AUDIO-NARRATOR-ONLY-01 ships and the operator's
     "Save my voice" toggle is ON, swap this string for the audio-on
     variant.  Until then, hardcode "text-only" to keep Lori truthful. */
  const _CAPABILITIES_HONESTY = (
    "CAPABILITIES (must be honest, never overstate): " +
    "Right now this session captures only the typed text and speech-to-text " +
    "transcript of our conversation. Audio recording, video recording, " +
    "image saving, photo analysis, and any other capability not explicitly " +
    "listed are NOT active in this session. " +
    "If the narrator asks whether audio, voice, video, photos, or any other " +
    "media is being recorded or saved, answer warmly and honestly — for " +
    "example: \"We're saving the text of our conversation right now, not the " +
    "audio recording or video. Those aren't part of this session yet.\" " +
    "NEVER say \"yes, I'm saving the audio\" or \"I'm recording your voice\" " +
    "or imply capabilities that aren't real. " +
    "If unsure what's saved, default to \"text only\" rather than promising more."
  );

  /* ── Tier-2 directive helper ───────────────────────────────────
     Called by buildRuntime71 (app.js) to set runtime71.session_style_directive.
     The backend prompt_composer reads this field and appends to the
     directive block.  Always includes the BUG-218 capabilities-honesty
     rule; style-specific suffix appended for tier-2 styles. */
  function _emitStyleDirective(style) {
    let styleSuffix = "";
    switch (style) {
      case "clear_direct":
        styleSuffix = "Ask one short question at a time. Avoid open-ended " +
                      "exploration. Acknowledge briefly, then move on.";
        break;
      case "memory_exercise":
        styleSuffix = "Use recognition cues. Allow long silences. Never correct. " +
                      "Speak more slowly. Match dementia-safe cognitive support pacing.";
        break;
      case "companion":
        styleSuffix = "Don't probe for facts. Listen. Reflect feelings. Speak less " +
                      "than the narrator does.";
        break;
      case "questionnaire_first":
      case "warm_storytelling":
      default:
        styleSuffix = "";
        break;
    }
    // BUG-218: capabilities-honesty rule is always included; style suffix
    // (if any) follows.  No-op styles still receive the honesty preamble.
    return styleSuffix
      ? _CAPABILITIES_HONESTY + " " + styleSuffix
      : _CAPABILITIES_HONESTY;
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
      // BUG-208: reject backend payload if echoed person_id doesn't match
      // the one we requested.  Defends against mid-flight narrator swap and
      // any backend caching surprise.  Do NOT cache or return the blob.
      if (data && data.person_id && data.person_id !== personId) {
        console.warn("[bb-drift] BB GET response REJECTED: requested=" +
          personId.slice(0, 8) + " response.person_id=" +
          (data.person_id || "").slice(0, 8) + " — refusing to merge");
        return {};
      }
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

  /* ── WO-01B: BB save helper ────────────────────────────────────
     PUT a single answer into the existing /api/bio-builder/questionnaire
     endpoint.  The endpoint expects the WHOLE questionnaire blob, so we
     fetch fresh, merge, and PUT.  Best-effort: failures are logged but
     don't block the walk.  Tracked in state.session.loop.savedKeys for
     harness observability and to prevent double-saves on idempotent
     re-dispatch.  Lightly normalizes a few specific fields (dateOfBirth,
     timeOfBirth) using the helpers exposed by bio-builder-questionnaire.js
     when present; otherwise saves raw. */
  async function _saveBBAnswer(personId, sectionId, fieldId, answer) {
    if (!personId || !sectionId || !fieldId || !answer) return;
    if (!state.session.loop) return;
    if (!Array.isArray(state.session.loop.savedKeys)) {
      state.session.loop.savedKeys = [];
    }
    const savedKey = `${sectionId}.${fieldId}`;

    // BUG-208: hard pid scope guard.  Three things must agree before we
    // touch anything: the pid we were called with, state.person_id, and
    // state.bioBuilder.personId.  If any disagree, halt the loop, do NOT
    // save the answer, and log [bb-drift] so the harness can surface it.
    const stPid  = (typeof state !== "undefined") ? state.person_id : null;
    const bb     = (typeof state !== "undefined") ? state.bioBuilder : null;
    const bbPid  = bb && bb.personId;
    if (stPid !== personId || (bbPid && bbPid !== personId)) {
      console.warn("[bb-drift] _saveBBAnswer SKIPPED: " +
        "personId=" + (personId || "").slice(0, 8) +
        " state.person_id=" + ((stPid || "").slice(0, 8) || "null") +
        " bb.personId=" + ((bbPid || "").slice(0, 8) || "null") +
        " — refusing to save " + savedKey + " under wrong narrator");
      // Stop the loop to prevent further mis-saves until next dispatch.
      if (state.session.loop) {
        state.session.loop.lastAction = "halted_pid_drift:" + savedKey;
      }
      return;
    }

    // Light per-field normalization — lean on helpers if loaded.
    let normalized = answer;
    try {
      if (fieldId === "dateOfBirth" && typeof window.normalizeDobInput === "function") {
        normalized = window.normalizeDobInput(answer) || answer;
      } else if (fieldId === "timeOfBirth" && typeof window.normalizeTimeInput === "function") {
        normalized = window.normalizeTimeInput(answer) || answer;
      } else if (fieldId === "placeOfBirth" && typeof window.normalizePlaceInput === "function") {
        normalized = window.normalizePlaceInput(answer) || answer;
      }
    } catch (_) { /* keep raw on any normalization throw */ }

    // Fetch the freshest blob (bypass cache so we don't merge stale state).
    _resetBBCache();
    const blob = await _getQuestionnaireBlob(personId);
    if (!blob || typeof blob !== "object") {
      console.warn("[session-loop] _saveBBAnswer: BB blob unavailable; skipping save for", savedKey);
      return;
    }
    // BUG-208: re-check pid after the network await — state.person_id and
    // bb.personId may have moved during the in-flight fetch.  This is the
    // "save Christopher's answer to Corky" race that started the bug.
    const stPid2 = (typeof state !== "undefined") ? state.person_id : null;
    const bb2    = (typeof state !== "undefined") ? state.bioBuilder : null;
    const bbPid2 = bb2 && bb2.personId;
    if (stPid2 !== personId || (bbPid2 && bbPid2 !== personId)) {
      console.warn("[bb-drift] _saveBBAnswer ABORTED post-fetch: narrator switched during BB GET. " +
        "Refusing to PUT " + savedKey + " (was=" + (personId || "").slice(0, 8) +
        " now state=" + ((stPid2 || "").slice(0, 8) || "null") +
        " bb=" + ((bbPid2 || "").slice(0, 8) || "null") + ")");
      if (state.session.loop) {
        state.session.loop.lastAction = "halted_pid_drift_postfetch:" + savedKey;
      }
      return;
    }
    if (!blob[sectionId] || typeof blob[sectionId] !== "object") {
      blob[sectionId] = {};
    }
    blob[sectionId][fieldId] = normalized;

    const url = (typeof API !== "undefined" && API.BB_QQ_PUT)
      ? API.BB_QQ_PUT
      : "/api/bio-builder/questionnaire";

    try {
      const res = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          person_id: personId,
          questionnaire: blob,
          source: "session_loop",
          version: 1,
        }),
        signal: AbortSignal.timeout(3000),
      });
      if (res.ok) {
        if (!state.session.loop.savedKeys.includes(savedKey)) {
          state.session.loop.savedKeys.push(savedKey);
        }
        state.session.loop.lastAction = `saved_${savedKey}`;
        console.log(`[session-loop] saved BB answer: ${savedKey} = ${JSON.stringify(normalized).slice(0, 80)}`);
        // Invalidate cache so the next read sees the freshly-PUT blob.
        _resetBBCache();
      } else {
        console.warn(`[session-loop] save_failed ${savedKey}: status=${res.status}`);
      }
    } catch (e) {
      console.warn(`[session-loop] save_failed ${savedKey}: ${e && e.message || e}`);
    }
  }

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
