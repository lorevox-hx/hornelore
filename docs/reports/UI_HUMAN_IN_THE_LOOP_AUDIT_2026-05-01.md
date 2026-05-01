# Narrator UI human-in-the-loop audit — 2026-05-01

## Scope

This audit reviews the narrator-facing UI in Hornelore v7.4 ahead of parent-session readiness (older adult narrators: Janice, Kent, Christopher). Coverage: DOM elements, control visibility, state isolation, button wiring, and error recovery. Five key files audited: `hornelore1.0.html`, `app.js`, `interview.js`, `state.js`, `lori80.css`. Focus: blocking issues that could trap or confuse a vulnerable narrator.

---

## A. Break / Pause / Resume controls

### Findings

**A1. Multiple distinct Pause buttons exist in the DOM**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3164` | Topbar Pause button | `<button id="lvNarratorPauseBtn" onclick="lvNarratorTogglePause()">` — labeled "Pause" in the narrator-room topbar | **Primary Pause button** in topbar, controls `listeningPaused` global flag via `lvNarratorTogglePause()` which delegates to `lv80TogglePauseListening()` | — |
| `hornelore1.0.html:3311` | Footer Pause button | `<button id="btnPause" onclick="lv80TogglePauseListening()">Pause</button>` — separate button in footer below chat input | **Secondary Pause button** in footer, calls same underlying `lv80TogglePauseListening()` function | P1 |

**Finding:** Two separate Pause buttons exist in the DOM but both trigger the same underlying state toggle. The footer button at L3311 appears to be dead code (commented as WO-11B in app.js:430, described as an "old control path"). A narrator could tap both and become confused about which one is active. | **P1** |

**A2. "Take a Break" button correctly hides during Lori's speech**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3168` | Break button in topbar | `<button id="lvNarratorBreakBtn" class="lv-narrator-ctrl lv-narrator-break" onclick="lvNarratorStartBreak()">Take a break</button>` | No explicit "disabled" state when Lori is speaking. CSS at `lori80.css:921–926` does not include `:disabled` or `[data-on="true"]` orange state. The button is **not visually locked** when `state.session.loriSpeaking === true`. | P1 |

**A3. "Return to Operator" button is narrator-visible in Break overlay**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3363` | Break overlay actions | `<button type="button" class="lv-operator-ghost-btn" onclick="lvNarratorReturnToOperator()">Return to Operator</button>` | This button is placed INSIDE the narrator-facing Break card at `lvNarratorBreakOverlay`. The class `lv-operator-ghost-btn` is operator UI styling, but the button is present in a `role="dialog"` popover that narrators see. A narrator should never see operator controls. The overlay text says "Let's take a break" and "Your story is saved", but then offers a technical "Return to Operator" action. | **P0 blocking** |

**A4. Resume after Break does not emit "Welcome back" TTS**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `app.js:1086–1093` | `lvNarratorEndBreak()` function | Clears `state.session.breakActive`, hides overlay, calls `_lvNarratorPaintControls()` — **does not generate TTS**. No call to speaker functions or `ttsQueue.push()`. | When narrator clicks Resume, Lori is silent. The break card says "We can come back whenever you are ready", but on return, nothing is spoken. For an older adult, silence after a break could signal a technical failure ("is the system stuck?"). Missing: `generateText("Welcome back, " + (state.profile.basics.preferredName || "Friend") + ". Ready when you are.")` or similar. | **P1** |

**A5. Mic auto-rearm paused during break**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `app.js:1072–1077` | `lvNarratorStartBreak()` | Sets `state.session.micAutoRearm = false` and calls `lv80TogglePauseListening()` to pause the mic. On break end, neither is re-armed. | After `lvNarratorEndBreak()` completes, `state.session.micAutoRearm` stays `false` and `listeningPaused` stays `true`. The next message from Lori will NOT auto-rearm the mic, requiring narrator to manually tap Resume/Mic. For an older adult expecting hands-free operation, this could be silent failure. Missing: `state.session.micAutoRearm = true;` and `listeningPaused = false;` (or call `lv80TogglePauseListening()` to toggle it back) in `lvNarratorEndBreak()`. | **P0 blocking** |

**A6. In-flight TTS not cancelled on Break click**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `app.js:1070–1084` | `lvNarratorStartBreak()` | No code to cancel `ttsQueue` or stop active speech. If Lori is mid-sentence when narrator taps Break, her speech continues uninterrupted in the background while the overlay pops up. | The break card will render on top of Lori's continuing speech, which is confusing and undermines the "take a break" semantics. Missing: `ttsQueue.length = 0;` (clear queue) + stop active `speechSynthesis` (or the TTS adapter equivalent if using external engine). | **P1** |

---

## B. Life Map era buttons

### Findings

**B1. Era click handler wires setEra() correctly**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `interview.js:41–44` | `renderRoadmap()` era loop | `d.onclick = () => { setEra(eraId); ... update71RuntimeUI(); renderRoadmap(); renderInterview(); showTab("interview"); }` | Each era button calls `setEra(eraId)` which routes through `_canonicalEra()` canonicalization. No race condition observed. | — |

**B2. Today button is wired the same as other eras**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `interview.js:29–31` | Era classification | `const isActive = currentEra === eraId;` — compares `currentEra` against each era_id including `"today"` | Today is rendered as a roadmap-item like any other era, no special-case wiring. `setEra("today")` works identically to `setEra("building_years")`. Canonical handling is correct. | — |

**B3. Active button highlight can desync from runtime state**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `interview.js:29, 31` | `const isActive = currentEra === eraId;` then `d.className="roadmap-item"+(isActive?" active-section":"");` | The active class is set once at render time. If `state.session.currentEra` changes *after* `renderRoadmap()` completes (e.g., via extraction, or a backend sync), the DOM class is not updated. Clicking an era triggers `renderRoadmap()` immediately (L44), so typical flow updates the highlight. BUT: if the era is set programmatically elsewhere without a re-render, the highlight will be stale. | No hardened observer or reactive binding. If a buggy extract sets currentEra and doesn't call renderRoadmap, the narrator sees a green highlight on the wrong era. | **P2** |

**B4. Device clock / current date not visible in narrator UI**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| No visible clock in narrator room | N/A | No device clock, date display, or "today" button label showing the actual current date. | The "today" era button exists but does not show the narrator what "today" is (e.g., "May 1, 2026"). For an older adult with date confusion, tapping "today" without seeing the actual date is less grounding. The date exists in `prompt_composer` backend logic but never surfaces to the narrator UI. | **P2** |

---

## C. Peek at Memoir

### Findings

**C1. Button is present and styled; CSS class is not eye-magnet bright**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3081` | Button in tab bar | `<button id="lv80PeekBtn" popovertarget="memoirScrollPopover" title="Read your story so far">📖 Peek at Memoir</button>` | `lori80.css:96–108` sets `background: rgba(30, 35, 60, 0.8)` (dark blue-gray), `border: 1px solid rgba(99, 102, 241, 0.35)` (dim indigo), `color: #c7d2fe` (light purple). **Not bright**. Hover state is slightly brighter but not neon. | Chris reported "too bright — eye magnet, distracting" in live test. CSS shows a subtle, muted button. Either Chris's visual assessment differs from the code, OR the button is being overridden by a later CSS rule, OR appears brighter in the actual rendered interface. No CSS issue found in audit. | **Investigation needed** |

**C2. Peek at Memoir and TXT export draw from different sources**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3487–3510` | Popup renders from `memoirScrollPopover` | Popover is built dynamically by `_memoirClearContent()` + `_memoirRenderSections()` functions called by interview.js and other handlers | Popover reads from `interviewProjection.fields` (extracted + suggested candidates) merged with questionnaire answers. TXT export is built by separate export code (`#memoirExportTxtBtn` handler). | Two different data sources can diverge if export code reads from `state.profile.basics` while the popover reads from `interviewProjection`. No single source of truth. If a narrative value is in projection but not yet synced to profile, TXT will lack it but Peek will show it (or vice versa). | **P1** |

**C3. Peek at Memoir content truncation / clipping**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3487` | `<div id="memoirScrollPopover" popover="auto" class="parchment-scroll" ...>` | Popover uses `popover="auto"` (native HTML Popover API). CSS applies scrolling + max-height constraints (not visible in audit snippet, but typical for popovers). | Chris reported "Peek at Memoir cuts off content (Earliest Years truncated mid-sentence)". Likely due to max-height on the scroll container. If a section has long prose (Earliest Years often does), it gets clipped without explicit "show more" UI. No `scrollable` indicator or warning. | **P1** |

---

## D. Reset Identity flow

### Findings

**D1. Narrator switch clears identity onboarding state**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `app.js:2195–2205` | `lvxSwitchNarratorSafe()` hard reset block | Clears: `state.session.identityPhase = null`, `state.session.identityCapture = { name: null, dob: null, birthplace: null }`, plus bio-builder reset via `LorevoxBioBuilder.onNarratorSwitch(pid)` and interview projection reset via `_ivResetProjectionForNarrator(pid)` | When narrator switches (e.g., operator clicks Kent after Janice), all identity state is purged. **Correctly isolated**. | — |

**D2. Memoir cache clears on narrator switch**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `app.js:2234` | Hard reset cleanup | Calls `if (typeof _memoirClearContent === "function") _memoirClearContent();` | Popover content cache is wiped on narrator switch. **Correctly isolated**. | — |

**D3. localStorage is NOT explicitly cleared per narrator**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `state.js:489–502` | Spine localStorage helpers | `const LS_SPINE = (pid) => `lorevox.spine.${pid}`;` and `loadSpineLocal(pid)` read/write `localStorage.getItem/setItem` keyed by person_id | Spine data is persisted per-narrator and rehydrated correctly. HOWEVER: other state.js globals like `lastAssistantText`, `softenedMode`, `turnCount`, `sessionAffectLog` are globals (L449–483), not narrator-keyed. On narrator switch (L2233), only `lastAssistantText = ""; currentAssistantBubble = null; _lastUserTurn = "";` are cleared. **Missing: `softenedMode = false; softenedUntilTurn = 0; turnCount = 0; sessionAffectLog = [];`** | If Janice triggers safety softening (softenedMode = true), then operator switches to Kent without clearing it, Kent's interview will inherit Janice's softened mode. | **P1** |

**D4. No "Reset Identity" button exists for narrator operator to use**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html` (operator tab) | Operator controls | No operator-visible "Reset Identity for This Narrator" button. Operator can use "Delete Current Narrator" (L3881) which is destructive. | ChatGPT reported "Reset Identity didn't fully reset narrator state — Kent showed Janice memoir material after switch". The audit shows `lvxSwitchNarratorSafe()` does a hard reset on *switch*, but there's no non-destructive mid-session reset. If a narrator's state gets confused (e.g., wrong memoir cached, identity fields corrupted), operator has only delete-or-live-with-it. Missing: dedicated `Reset Identity (keep narrator, clear onboarding + projection + memoir)` button. | **P2** |

---

## E. Today mode + clock

### Findings

**E1. Device current date is not displayed to narrator**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| Narrator UI | No visible element | No clock, no date display, no "Today is: May 1, 2026" label anywhere in the narrator room topbar or context. | The "today" era button exists but offers no grounding about what date it refers to. For older adults, absence of explicit date reference undermines temporal orientation. Lori knows the date (backend has it in system prompt), but narrator can't verify she's correct. | **P2** |

**E2. `device_context` not threaded through extract payload**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `interview.js` | Extraction payload building | No visible `device_context` field populated in the extraction request. Interview.js builds `_extractAndProjectMultiField()` but does not include current date. | Extraction payload lacks context about "today" when a question targets `personal.currentDate` or similar. If Lori asks "What year is it?", the extractor has no ground truth to compare against narrator's answer. | **P2** |

---

## F. Cross-narrator state isolation

### Findings

**F1. Hard reset on narrator switch is comprehensive**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `app.js:2164–2240` | `lvxSwitchNarratorSafe()` | Clears: conv_id (fresh one generated per switch), interview session, identity phase, runtime signals (currentPass, currentEra, currentMode), assistant role, textContent (chat, memoir), projection via `_ivResetProjectionForNarrator(pid)`, and LorevoxBioBuilder state via `onNarratorSwitch` hook. | Comprehensive isolation. Trainer mode carve-out (L2178–2211) correctly preserves trainer state across narrators only when trainer is actively running. | — |

**F2. Global state variables leak across narrator switches**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `state.js:445–483` | Global recording/safety/affect state | `listeningPaused`, `isRecording`, `ttsQueue`, `softenedMode`, `softenedUntilTurn`, `turnCount`, `sessionAffectLog`, `emotionAware`, `cameraActive`, etc. are global module-level variables, not narrator-keyed | On narrator switch (app.js:2232–2238), only 3 text variables are cleared. The globals survive: `listeningPaused`, `ttsQueue`, `sessionAffectLog`, `softenedMode`, `turnCount`, `emotionAware`, `cameraActive`, and 5 permission flags (`permMicOn`, `permCamOn`, `permLocOn`). | **Critical issue**: If Janice sets `softenedMode=true` (safety softening triggered), then operator switches to Kent without running `listeningPaused=false; softenedMode=false; softenedUntilTurn=0; turnCount=0; sessionAffectLog=[];` (and others), Kent's interview will inherit Janice's emotional state flags and safety posture. Kent is a healthy adult but will be softened. | **P0 blocking** |

**F3. No explicit state-reset operation exposed to operator**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| operator tab | No hard-reset button | Operator can "Delete Current Narrator" (destructive) or switch to another narrator (which runs hard reset). No "Clear session state for current narrator" button. | If a narrator's state becomes corrupted mid-session and operator wants to retry from the top, operator must delete and reload, or switch narrators and back (nuclear). Missing: `resetSessionStateForNarrator(pid)` exposed as an operator button. | **P2** |

---

## G. Other narrator-safety concerns

### Findings

**G1. Break overlay is modal but narrator can't dismiss it with Escape**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3357` | Break card dialog | `role="dialog" aria-modal="true"` but no Escape key handler. Standard HTML `<dialog>` would auto-dismiss on Escape; this `<div>` popover does not. | If narrator accidentally hits "Take a Break" and panics, Escape does not work. They must click Resume or Return to Operator. For an older adult with limited tech comfort, no escape hatch could cause anxiety. Missing: `onkeydown="if (event.key === 'Escape') lvNarratorEndBreak();"` on the overlay div. | **P1** |

**G2. Lori's response to "what day is it?" is a hallucinated capability constraint**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| Backend chat path | Lori text generation | Chris live-test: narrator asked "what day is it", Lori replied "I'm in a conversation mode that doesn't allow me to keep track of the current date" — but the backend system prompt contains the date, and Lori can tell the date in memory_echo mode. | This is an extractor hallucination, not a UI bug, but it's narrator-visible confusion: Lori falsely claims she can't do something she can do. If repeated, narrator loses trust. The fix is in `prompt_composer` — ensure the system prompt for "interview" mode allows date responses, or add a prompt guard to prevent this specific hallucination. | **P2** |

**G3. Peek at Memoir popover can render stale data on hot-reload**

| File | Location | Current state | Concern | Severity |
|------|----------|---------------|---------|----------|
| `hornelore1.0.html:3487` | Popover uses `popover="auto"` | Native Popover API does not listen to state changes. If `state.interviewProjection.fields` updates, the popover does not re-render unless narrator explicitly closes and re-opens it. | If Lori extracts a fact mid-interview and the narrator opens Peek at Memoir immediately, they may see stale data. Narrator must close popover and reopen to refresh. No visual indicator that data is stale. | **P2** |

---

## Summary table

| Severity | Count | Surfaces |
|----------|-------|----------|
| **P0 blocking** | 3 | Mic auto-rearm not restored after break; Return-to-Operator visible to narrator; global state leak across narrator switches (softenedMode, turnCount, sessionAffectLog) |
| **P1 (fix before run)** | 6 | Pause button color not orange when Lori speaking; Welcome back TTS missing on Resume; in-flight TTS not cancelled on Break; era button highlight can desync; Peek memoir truncation; Peek and TXT export sources diverge; Break overlay needs Escape-key dismiss; secondary (footer) Pause button is dead code |
| **P2 (parallel cleanup)** | 5 | No device date display; device_context not in extract payload; no mid-session Reset Identity button; global state flags not cleared on narrator switch (emotionAware, cameraActive, permissions); Peek popover stale on state change; Lori hallucinates capability constraint on "what day is it" |

---

## Recommended fix ordering

1. **CRITICAL (run-blocking): Clear global state variables on narrator switch** (app.js:2232–2240 hard reset block). Add: `softenedMode=false; softenedUntilTurn=0; turnCount=0; sessionAffectLog=[]; emotionAware=true; cameraActive=false; permCardShown=false;` (or provide a helper function `clearGlobalState()` called after every other reset). **Impact: prevents safety-softened narrators from carrying state to next narrator. Highest priority.**

2. **CRITICAL: Remove "Return to Operator" button from narrator-visible Break overlay** (hornelore1.0.html:3363). Replace with something narrator-appropriate like "Tell Operator I'm Ready" (which signals operator UI, not narrator-UI). Or remove entirely and ensure resume restarts conversation smoothly.

3. **HIGH: Restore mic auto-rearm and re-toggle pause on Break resume** (app.js:1086–1093). Add to `lvNarratorEndBreak()`: `state.session.micAutoRearm = true;` and call `lv80TogglePauseListening()` if `listeningPaused === true` to un-pause. Test: narrator taps Break, then Resume; next Lori speech auto-arms mic without narrator action.

4. **HIGH: Cancel in-flight TTS on Break click** (app.js:1070–1084). Add: `ttsQueue.length = 0;` (clear queue) + cancel active speech synthesis (if using Web Speech API: `speechSynthesis.cancel()`; if custom TTS: call the cancel method). Test: Lori mid-sentence when Break tapped; speech stops, overlay appears.

5. **HIGH: Emit "Welcome back" TTS on Resume** (app.js:1086–1093). Add to `lvNarratorEndBreak()`: generate `"Welcome back, " + (state.profile.basics.preferredName || "Friend") + ". Ready whenever you are."` and queue it for TTS. Test: narrator resumes; Lori greets them warmly.

6. **MEDIUM: Add Escape-key dismiss to Break overlay** (hornelore1.0.html:3357 div). Add `onkeydown="if (event.key === 'Escape') lvNarratorEndBreak();"` so narrator can bail out without understanding buttons.

7. **MEDIUM: Remove dead-code secondary Pause button** (hornelore1.0.html:3311). If it's truly unused (confirmed: footer Pause vs topbar Pause both call same function, topbar is active), delete L3311 button to avoid narrator confusion about which to use.

8. **MEDIUM (before parent run): Add device date display to narrator room** (hornelore1.0.html topbar or right panel). Show "Today: May 1, 2026" so narrator can verify what "today" means. Wire from system prompt's current date.

9. **MEDIUM: Add operator "Reset Identity for Current Narrator" button** (operator tab). Expose a safe `resetIdentityState(pid)` that clears onboarding, projection, memoir, and safety flags WITHOUT deleting the narrator. Needed for operator recovery if state corrupts mid-session.

10. **LOW (post-run docs): Reconcile Peek and TXT export sources** — document which is truth, or unify to single source. If projection is truth, ensure export reads from projection. If profile is truth, ensure popover reads from profile.
