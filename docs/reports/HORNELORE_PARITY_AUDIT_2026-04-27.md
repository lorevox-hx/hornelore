# Hornelore Parity Audit vs. Lorevox Heritage
**Date:** April 27, 2026 | **Scope:** Production fork from Lorevox 9.0 (WO-11)  
**Audit Period:** Offline code scan (no live testing)

---

## RISKY — Critical Safety & Architectural Gaps

### 1. **Safety Detection NOT WIRED in Chat Path vs. Interview Path**
- **File:** `/server/code/api/routers/chat_ws.py` (1–350)
- **Issue:** Chat WebSocket path (`chat_ws.py`) does NOT import or call safety detection (`scan_answer`, `build_segment_flags`, `set_softened`). Interview path (`interview.py:269–307`) has complete safety wiring.
- **Risk:** User disclosures of abuse/crisis in chat stream bypass all crisis detection, softening, and resource card triggers. Interview-only safety creates a dangerous dual-path asymmetry.
- **Impact:** ACUTE — parent sessions expect uniform safety stance across all narrator input channels.
- **Action:** File WO immediately. Add safety scanning to `chat_ws.py` before every LLM generation, mirror interview.py's `set_softened()` + DB persistence. Verify both paths persist to same `segment_flags` table.

### 2. **Memory Echo & Peek-at-Memoir Backend Missing**
- **Files:** Grep found `compose_memory_echo()` in `prompt_composer.py:542` but NO backend router serving `/api/peek-at-memoir` or equivalent.
- **Issue:** WO-ARCH-07A (memory echo + correction) has frontend UI consumption but backend read interface is not publicly accessible. Likely internal-only or not yet wired.
- **Risk:** If test harness or parent sessions expect a public `/api/session/{id}/memoir/peek` endpoint, it will 404.
- **Action:** Document whether peek-at-memoir is in-scope for parent sessions. If yes, add router + endpoint immediately. If deferred, flag explicitly in handoff docs.

### 3. **Session Awareness Partially Missing**
- **Files:** `state.js` (ui/js/state.js:114–150) defines `session` object with `currentPass`, `currentEra`, `currentMode`, but NO `passive_waiting`, `attention_cue`, `silence_ladder`, or explicit `session_state_hints`.
- **Reference:** `prompt_composer.py:475–486` has inline state hint mapping (storytelling, reflecting, emotional_pause, correcting, searching_memory, answering) but no UI wiring to populate `conversation_state` parameter.
- **Risk:** WO-LORI-SESSION-AWARENESS-01 expectations may be partial. If parent sessions expect attention tracking or silence detection, it may not exist in runtime71.
- **Action:** Audit parent WO scope. If session-awareness features are in scope, check if `attention_state` should be seeded from MediaPipe emotion engine or narrator health monitor.

### 4. **Safety Stack Missing from chat_ws Import Chain**
- **File:** `chat_ws.py:1–50` imports `prompt_composer`, `archive`, `memory_echo` but NOT `safety.py`.
- **Test:** `compose_system_prompt()` call at line 208 receives `runtime71` (which may include affect_state) but does NOT invoke `scan_answer()` before LLM.
- **Risk:** Chat turn triggers may carry crisis language that never reaches `safety.scan_answer()`. No segment flags persisted. No softening mode set.
- **Action:** Add safety import and scan at generation start (before line 208). Persist flags to DB. Coordinate with interview.py pattern (lines 269–307).

---

## DUPLICATED — Parallel Implementations Needing Convergence

### 5. **Two System Prompt Base Definitions**
- **Files:** 
  - `prompt_composer.py:27–193` → `DEFAULT_CORE` (comprehensive, ~3500 words, includes ACUTE SAFETY RULE, EMPATHY RULE, FACT HUMILITY RULE, REVISION RULE, NO QUESTION LISTS RULE, role declarations)
  - `api.py` (SSE fallback path) → hardcoded `'You are Lorevox, a warm oral historian...'` (one-liner)
- **Issue:** SSE chat path in `api.py` does NOT call `compose_system_prompt()` at all; it uses a bare minimum string. WebSocket path (`chat_ws.py:208`) correctly calls `compose_system_prompt()`.
- **Risk:** SSE chat narrators get a stripped-down system prompt missing safety rules, role directives, and runtime context. Inconsistent behavior between SSE and WebSocket clients.
- **Action:** Refactor `api.py` SSE handler to use `compose_system_prompt()` like chat_ws. Ensure both paths produce identical system prompt assembly.

### 6. **Two Implementations of "Next Question" Logic**
- **Files:**
  - `interview.py:152–184` → `_phase_aware_next_question()` (calls `phase_aware_composer.pick_next_question()`)
  - `interview.py:221` → `db.get_next_question()` (sequential DB fallback)
- **Issue:** Phase-aware and sequential paths are parallel, selected by flag. If flag off, DB path runs; if flag on, composer path runs. No convergence point or shared abstraction.
- **Risk:** Two different question ordering algorithms never unified. Future changes require edits in two places. Test coverage may miss one path.
- **Action:** Low risk if flag is read-only in production. Monitor for convergence in next WO. Document clearly in interview.py that this is a *temporary* dual-path gate pending full migration to phase-aware.

---

## MISSING — Gaps vs. Lorevox or Spec

### 7. **Passive Waiting State Not in Chat Runtime**
- **Files:** `state.js` tracks `session.currentPass`, `session.currentMode` but no `passive_waiting` or `idle_presence` state.
- **Spec Reference:** WO-10C mentions cognitive support mode; WO-LORI-SESSION-AWARENESS-01 likely expects idle/waiting detection.
- **Risk:** If narrator is silent > N seconds, Lori should emit a soft prompt ("still here?") but no trigger mechanism exists in runtime.
- **Action:** Check if `passive_waiting` should come from narrator_state router or session_loop. If yes, add to runtime71 and wire to chat_ws generation logic.

### 8. **MediaPipe Facial Signals NOT Routed to Backend**
- **Files:** `emotion.js` (ui/js/emotion.js:1–100) emits affect_state (steady, engaged, reflective, moved, distressed, overwhelmed) but does NOT send `visualSignals` dict to chat backend.
- **Spec:** `prompt_composer.py:637` docs mention `visual_signals (dict|null) — v7.4A real camera affect` in runtime71 but no UI code populates it.
- **Risk:** Emotion detection runs locally in browser but never informs Lori's response adaptation. Camera is active but signal is dead-ended.
- **Action:** Check if visual_signals should be sent from emotion-ui.js to chat_ws params. If yes, wire `emotion.js` to populate runtime71.visual_signals before each turn. If not in scope, document this as deferred.

### 9. **Bug Panel / Test Lab Categories Not Documented**
- **Files:** `ui/js/app.js` references bug-panel, `ui/js/ui-health-check.js` exists, but no centralized test category schema found.
- **Issue:** WO-13 test harness files exist (wo13_phase*_proof/) but no README in ui/js/ explaining test categories or where to add "Lori Response Quality" category.
- **Risk:** New test categories require reverse-engineering the bug panel structure.
- **Action:** Safe to defer. Document test-lab.py router endpoint + category enum once WO-13 closure is finalized.

### 10. **Peek-at-Memoir Accessibility Not Clear**
- **Files:** `compose_memory_echo()` reads runtime71 family projection but does NOT query DB. No router endpoint found for `/api/memoir/peek/{session_id}`.
- **Issue:** Memory echo is *deterministic* (no DB call) but "peek at memoir" likely requires reading archive or projection state, which needs a backend endpoint.
- **Risk:** If UI tries to call a peek endpoint that doesn't exist, it 404s.
- **Action:** Check if peek-at-memoir is a future WO or already implemented as a read-only variant of memoir_export. If missing, add to scope.

---

## WIRED — Working as Expected, No Action Needed

### 11. **Safety Detection in Interview Path ✓**
- **Files:** `interview.py:269–307` correctly imports `scan_answer`, `build_segment_flags`, `get_resources_for_category`, `set_softened`, `is_softened` from `safety.py`.
- **Check:** Scans answers, persists segment flags, sets softened mode, returns resources to response.
- **Status:** COMPLETE — no changes needed.

### 12. **Prompt Composer System Prompt Assembly ✓**
- **Files:** `prompt_composer.py:622–1050+` defines `compose_system_prompt()` with:
  - DEFAULT_CORE (safety rules, role declarations, identity grounding)
  - Profile JSON extraction from UI
  - Pinned RAG docs (oral history manifesto, golden mock)
  - Runtime71 directives (pass, era, mode, affect, fatigue, cognitive support, memoir context)
  - Role overrides (helper, onboarding)
  - Device/location context injection
- **Status:** COMPLETE — properly scoped and comprehensive.

### 13. **Memory Archive Wired in Both Paths ✓**
- **Files:** 
  - `interview.py:211–328` calls `archive_ensure_session()` + `archive_append_event()` for Q&A logging.
  - `chat_ws.py:136–150` calls same for user messages.
- **Check:** Both paths create session dir + append turns. Interview also logs section boundary data.
- **Status:** COMPLETE — consistent across paths.

### 14. **MediaPipe Emotion Engine Running ✓**
- **Files:** `emotion.js` (lines 1–100+) initializes FaceMesh, runs geometry classification, emits affect_state events via POST to `/api/affect`.
- **Check:** States: steady, engaged, reflective, moved, distressed, overwhelmed. SUSTAIN_MS=2000. TARGET_FPS=15.
- **Router:** `affect.py` exists and accepts events.
- **Status:** COMPLETE — emotion pipeline wired end-to-end.

### 15. **Segment Flags Table Wired ✓**
- **Files:** `db.py:748–777` CREATE TABLE segment_flags (sensitive, sensitive_category, excluded_from_memoir, private, deleted).
- **Write:** `interview.py:285–293` calls `db.save_segment_flag()`.
- **Read:** No explicit read check found but schema is live.
- **Status:** COMPLETE — table exists and receives writes.

### 16. **Database Tables Present ✓**
- **Files:** `db.py:320–947` defines all tables:
  - sessions, turns, people, profiles, media
  - interview_plans, interview_sections, interview_questions, interview_sessions, interview_answers
  - facts, life_phases, segment_flags, affect_events
  - family_truth_notes, family_truth_rows, family_truth_promoted (WO-13 schema)
  - rag_docs, rag_chunks, section_summaries, media_attachments
- **Status:** COMPLETE — comprehensive schema in place.

### 17. **Phase-Aware Questions Gated Safely ✓**
- **Files:** `flags.py:60–65` defines `phase_aware_questions_enabled()` flag (HORNELORE_PHASE_AWARE_QUESTIONS, default OFF).
- **Wiring:** `interview.py:224–227` + `interview.py:335–338` checks flag before calling phase-aware composer.
- **Fallback:** Falls back to DB sequential if flag off or composer returns None.
- **Status:** COMPLETE — safe feature gate in place.

---

## STALE — Vestigial Code, Candidates for Cleanup

### 18. **LV_DEV_MODE Flag Read But Lightly Used**
- **Files:** `chat_ws.py:12` reads `LV_DEV_MODE` env var (legacy Lorevox naming convention).
- **Use:** Line 224–229 only: logs full system prompt at INFO level when set.
- **Risk:** Low. Cosmetic only; no functional breakage if removed or renamed.
- **Action:** Safe to delete or rename to `HORNELORE_DEBUG`. No production impact.

### 19. **"Lorevox" String References Throughout Codebase**
- **Files:** ~30 files reference "Lorevox" in docstrings, module names, log messages, and system prompt.
- **Examples:**
  - `affect_service.py`: "Lorevox Affect Service — v6.1 Track B"
  - `db.py`: "Lorevox DB: %s"
  - `prompt_composer.py`: "You are Lorevox (\"Lori\")..." (correct, user-facing)
- **Risk:** Low. These are heritage comments/docstrings. Some (like system prompt) are intentional (Lori's intro). Others are just doc strings that say "Lorevox" instead of "Hornelore".
- **Action:** No urgent action. If rebranding is priority, systematic sed + docstring audit can happen in a separate WO. Do NOT rename in prompt_composer system prompt (user-facing).

### 20. **Legacy "facts" Table Still Present**
- **Files:** `db.py:490–516` defines `facts` table (pre-WO-13 schema).
- **Status:** Backfilled to `family_truth_rows` (lines 152–248), but original table is never deleted (policy: never modify legacy).
- **Risk:** Very low. Read-only. Backfill is idempotent.
- **Action:** Safe to keep indefinitely. Archive consideration only after family_truth is fully validated (post-parent-sessions).

---

## Executive Summary

Hornelore is **mostly wired** but has **two critical safety gaps** that must be addressed before parent sessions:

1. **Chat WebSocket path lacks safety scanning** — users can disclose crisis language in chat without triggering detection, softening, or resource cards. This is the #1 priority.
2. **Session awareness pieces are partially missing** — passive_waiting state, attention_cue, and silence_ladder are not present in runtime71 or UI state. Check if these are in scope for parent WO; if yes, add immediately.

**Secondary gaps (non-blocking but should be resolved within 1 WO):**
- SSE chat path uses bare-minimum system prompt vs. full DEFAULT_CORE (converge both paths).
- Peek-at-memoir backend endpoint may not exist (clarify scope).
- Visual signals from MediaPipe are detected but not sent to backend (check if in scope).

**Safe to defer:**
- Test lab categories (WO-13 closure task).
- Rebranding "Lorevox" docstrings to "Hornelore" (cosmetic).

**No action needed:**
- Safety detection in interview path is complete.
- Database schema is comprehensive and wired.
- Memory archive, affect service, and phase-aware questions are all working.
- Prompt composer assembly is sophisticated and correct.

**Recommended next steps:**
1. Add safety scanning to chat_ws.py (copy interview.py:269–307 pattern).
2. Verify session_state_hints and passive_waiting are in scope for parent WO.
3. Converge SSE and WebSocket system prompt assembly in api.py.
4. Clarify peek-at-memoir and visual_signals scope with parent session stakeholders.

Report generated offline; no live testing performed.
