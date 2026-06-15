# WO-UI-TEST-LAB-01 — Operator Preflight UI Health Check (in-Bug-Panel)

```
Title:    Add scripted UI Health Check harness to existing #lv10dBugPanel
Owner:    Claude
Mode:     Surgical implementation, additive (no behavior change to existing checks)
Priority: High — operator preflight is the only fast way to catch shell/camera/
          narrator-switch/session-style/archive regressions before they bite a session
Scope:    Frontend only.  In-browser self-test runs against the live app + live API.
          Playwright migration deferred to a Phase 2 WO.
```

## Problem

Today there's no operator-facing "is Hornelore actually working right now?" check.  Bugs ship to live sessions and get caught by Chris noticing — which is why we've burned three rounds on camera-on-narrator-switch alone.  Each WO ships its own ad-hoc verification (`./scripts/run_memory_archive_smoke.py`, manual click-through, Chrome MCP probes).  No persistent operator surface gives a single PASS/WARN/FAIL roll-up of the contract Hornelore is supposed to honor.

The existing Bug Panel (`#lv10dBugPanel`) shows live state (mic/cam/consent/TTS/signals) but doesn't run any **scripted contract checks**.

## Product rule

```
The Bug Panel is the operator's preflight checklist.
One click → PASS / WARN / FAIL across every contract.
Each result is copy-able and includes "what failed" + "suggested fix".
```

## Design

Extend the existing `#lv10dBugPanel` (hornelore1.0.html:3881–4025) with a new `.lv10d-bp-section` titled **"UI Health Check"**.  The section holds:

- Five RUN buttons:
  - **Run Full UI Check** (all 10 categories below)
  - **Run Camera Check**
  - **Run Narrator Switch Check**
  - **Run Chat Scroll Check**
  - **Run Archive Check**
- One **Copy Report** button — copies plaintext PASS/WARN/FAIL block to clipboard
- A results container that renders one row per check with status badge + reason

Status uses the existing `.ok` / `.warn` / `.err` / `.off` color classes already defined at hornelore1.0.html:697–700.  No new visual primitives needed.

The check engine is purely client-side — runs DOM inspections, reads `state.*`, and probes the same `/api/*` endpoints already used by `lv10dRefreshBugPanel()` (app.js:6351–6461) plus our new `/api/memory-archive/health`.  No new server endpoints.  No Playwright dependency.  Tests run sequentially with a 200ms inter-test pause so DOM observations stabilize.

## Architecture decisions baked in

1. **Tests are PURE OBSERVATIONS, never mutations.**  No test changes `state.session.sessionStyle`, no test triggers a real `lv80SwitchPerson`.  Tests that simulate user actions use sandbox mode (e.g. "verify the switcher CAN be toggled" rather than "switch narrators").  Operator running the harness in the middle of a real session must not break that session.

2. **Tests are FAST.**  Full Run Full UI Check completes in ≤ 3 seconds end-to-end.  Async fetches use 2s timeouts.  No test sits and waits for a model warmup or an LLM response.

3. **Each test result has FOUR fields:**
   - `category` (Startup, Narrator Switch, Camera Consent, Mic/STT, Chat Scroll, Memory River, Life Map, Peek Memoir, Photos, Archive)
   - `name` (short, e.g. "header narrator card present")
   - `status` (PASS | WARN | FAIL | DISABLED | SKIP)
   - `detail` (one-line: what was tested, actual value, suggested fix if FAIL)

4. **Results are batched, not streamed.**  All checks complete before the panel re-renders.  Avoids partial rerenders racing with click handlers.

5. **The harness does NOT rely on backend hot-reload.**  All checks use endpoints that are guaranteed to exist after a fresh stack start (no opt-in flags except feature-availability checks).

6. **DISABLED and SKIP are first-class statuses.**  If `HORNELORE_PHOTO_ENABLED=0`, the Photos category reports DISABLED, not FAIL.  If a check requires an active narrator and none is selected, those checks SKIP rather than FAIL.

## Files

Add:
- `ui/js/ui-health-check.js` — the test engine.  Exports `window.lvUiHealthCheck`.
- `docs/reports/WO-UI-TEST-LAB-01.md` — landing report.

Modify:
- `ui/hornelore1.0.html` — add the new `.lv10d-bp-section` (UI Health Check) inside `#lv10dBugPanel`, with buttons + results container.  Add `<script src="js/ui-health-check.js">` to the script load list (after app.js).
- `ui/css/lori80.css` — minor: add `.lv10d-bp-test-row` flex layout + a couple `.lv10d-bp-test-pill` styles (re-using the existing `.ok/.warn/.err/.off` colors).  Total CSS addition ≤ 60 lines.

Do NOT touch:
- `app.js` (additive only — bug panel script tag is the only HTML wiring needed)
- Any router code
- Any state.js field

## Implementation plan

### Step 1 — DOM scaffold inside #lv10dBugPanel
At hornelore1.0.html ~L4015 (before the existing Actions section), insert:

```
<div class="lv10d-bp-section" id="lv10dBpUiHealth">
  <strong>UI Health Check</strong>
  <div class="lv10d-bp-test-row">
    <button onclick="lvUiHealthCheck.runAll()">Run Full UI Check</button>
    <button onclick="lvUiHealthCheck.runCategory('camera')">Run Camera Check</button>
    <button onclick="lvUiHealthCheck.runCategory('switch')">Run Narrator Switch Check</button>
    <button onclick="lvUiHealthCheck.runCategory('scroll')">Run Chat Scroll Check</button>
    <button onclick="lvUiHealthCheck.runCategory('archive')">Run Archive Check</button>
    <button onclick="lvUiHealthCheck.copyReport()">Copy Report</button>
  </div>
  <div id="lv10dBpUiHealthResults" class="lv10d-bp-test-results"></div>
</div>
```

### Step 2 — Engine skeleton
`ui/js/ui-health-check.js`:

```
window.lvUiHealthCheck = (function () {
  const _last = { ts: null, results: [] };

  function _add(category, name, status, detail) { /* push to current run */ }

  async function _check_startup()      { ... }
  async function _check_switch()       { ... }
  async function _check_camera()       { ... }
  async function _check_mic_stt()      { ... }
  async function _check_chat_scroll()  { ... }
  async function _check_river()        { ... }
  async function _check_life_map()     { ... }
  async function _check_peek_memoir()  { ... }
  async function _check_photos()       { ... }
  async function _check_archive()      { ... }

  async function runAll()           { ... renders }
  async function runCategory(cat)   { ... renders }
  function copyReport()             { ... navigator.clipboard.writeText }

  return { runAll, runCategory, copyReport, lastResults: () => _last };
})();
```

### Step 3 — Per-category checks (concrete contract per category)

**Startup (5 checks, all sync):**
- `body[data-shell-tab]` exists and is set to one of operator/narrator/media → PASS, else FAIL "shell tabs not initialized"
- Operator tab is the default landing tab on initial load → check `localStorage` flag OR if `_lv80CamAutoStartedThisPageSession` is undefined (means no narrator load yet) → PASS, else WARN
- Warmup banner is hidden OR has appropriate message → PASS, else WARN
- Narrator selector card is present in header → PASS, else FAIL
- LLM ready: `isLlmReady() === true` → PASS, else WARN "model still loading"

**Narrator Switch (4 checks, mostly sync):**
- `state.person_id` is null OR is in `state.narratorUi.peopleCache` → PASS, else FAIL "stale narrator pointer"
- `state.session.sessionStyle` is set and is one of the 5 valid values → PASS, else FAIL
- Narrator switcher popover element exists (`#lv80NarratorSwitcher`) → PASS, else FAIL
- Narrator switcher list is populated (`#lv80NarratorList` has children) → PASS, else WARN "no narrators in cache"

**Camera Consent (5 checks, mix of sync + async):**
- `FacialConsent` global is defined → PASS, else FAIL "facial-consent.js not loaded"
- `FacialConsent.isGranted()` value is recorded → INFO (not FAIL — just record)
- `localStorage['lorevox_facial_consent_granted']` matches in-memory state → PASS, else WARN
- `cameraActive` global matches `state.inputState.cameraActive` → PASS, else FAIL "state desync"
- If `cameraActive === true`: `#lv74-cam-preview` exists, has live tracks → PASS, else FAIL "camera on but preview broken" (this catches bug #145 / #175 / #190 class)

**Mic / STT (4 checks):**
- `recognition` global exists OR Web Speech API is unavailable → recognition exists: PASS, unavailable: WARN with "STT will use typed fallback"
- `state.inputState.micActive` matches mic button visual state (data-on attribute) → PASS, else FAIL
- `state.session.loriSpeaking` is bool → PASS, else WARN
- Auto-rearm flag (`state.session.micAutoRearm`) is bool → PASS

**Chat Scroll (4 checks, sync):**
- `#crChatInner` element exists → PASS, else FAIL
- `window._scrollToLatest` is a function → PASS, else FAIL "FocusCanvas scroll plumbing missing"
- `#seeNewMsgBtn` exists → PASS, else FAIL
- `#chatMessages` has `padding-bottom` ≥ 100px (so footer doesn't cover last message) → PASS, else WARN

**Memory River (3 checks, sync):**
- `state.kawa` exists with `segmentList` array → PASS, else FAIL
- `#kawaRiverPopover` exists in DOM → PASS, else FAIL
- `lvNarratorShowView` function is defined → PASS, else FAIL "narrator room not loaded"

**Life Map (2 checks, sync):**
- `#lifeMapPopover` exists in DOM → PASS, else FAIL
- The narrator-room Life Map view-tab button exists → PASS, else FAIL

**Peek at Memoir (2 checks, sync):**
- `#memoirScrollPopover` exists in DOM → PASS, else FAIL
- The narrator-room Peek view-tab button exists → PASS, else FAIL

**Photos (2 checks, async):**
- `GET /api/photos/health` → 200 → if `enabled: false` → DISABLED with "set HORNELORE_PHOTO_ENABLED=1 to use photo features", else PASS
- If enabled + active narrator: `GET /api/photos?narrator_id=<pid>` returns 200 with `{photos: [...]}` → PASS, else WARN

**Archive (4 checks, async):**
- `GET /api/memory-archive/health` → 200 → if `enabled: false` → DISABLED with "set HORNELORE_ARCHIVE_ENABLED=1", else PASS
- If enabled + active narrator + active conv_id (from `state.chat.conv_id`):
  - `POST /api/memory-archive/session/start` with the narrator+conv → 200 → PASS, else FAIL
  - `POST /api/memory-archive/turn` (narrator role, throwaway content) → 200 → PASS, else FAIL
  - `POST /api/memory-archive/turn` (lori role, with bogus audio_ref to test forced-null) → response.audio_ref === null → PASS, else FAIL
- If no active narrator: SKIP all 3 with "no narrator selected"

### Step 4 — Results renderer
After a run, render results into `#lv10dBpUiHealthResults`:

```
<div class="lv10d-bp-test-row">
  <span class="lv10d-bp-value <ok|warn|err|off>">PASS|WARN|FAIL|DISABLED|SKIP</span>
  <span class="lv10d-bp-test-name">camera consent stored matches in-memory</span>
  <span class="lv10d-bp-test-detail">localStorage=true, FacialConsent.isGranted=true</span>
</div>
```

Group by category with a heading row.  Show a topline summary at the top:
`28 PASS · 2 WARN · 1 FAIL · 4 DISABLED · 6 SKIP`

### Step 5 — copyReport()
Build a plaintext report:

```
Hornelore UI Health Check  ·  2026-04-24T15:42:01Z

Topline:  28 PASS · 2 WARN · 1 FAIL · 4 DISABLED · 6 SKIP

[Startup]
  PASS  shell tabs initialized                     (data-shell-tab=operator)
  PASS  warmup banner hidden                       (LLM ready)
  ...

[Camera Consent]
  FAIL  camera on but preview broken               (cameraActive=true, #lv74-cam-preview missing)
        Suggested fix: stack restart, or call window.lv74.showCameraPreview()
  ...
```

`navigator.clipboard.writeText(report)` then visual confirmation pill.

### Step 6 — Wiring + load order
Add `<script src="js/ui-health-check.js">` to hornelore1.0.html script tag block.  Load order: AFTER app.js (depends on `state.*` globals + `lv80*` functions).  Defer is fine — bug panel won't be opened during the script-load window.

## Acceptance tests (meta — for the harness itself)

**A. Harness loads cleanly.**
PASS if: page load → no console errors → `window.lvUiHealthCheck` is defined → bug panel opens cleanly with the new section visible.

**B. Run Full UI Check completes in < 3 seconds on a healthy stack.**
PASS if: click "Run Full UI Check" → results appear → time elapsed under 3000ms (use performance.now diff inside the run).

**C. PASS counts on a clean stack.**
PASS if: after a clean stack restart with no narrator selected: ≥ 18 PASS, 0 FAIL (some WARNs OK, expected DISABLED if photo flag off).

**D. Camera bug regression catch.**
PASS if: deliberately break camera state via `state.inputState.cameraActive = true; cameraActive = true; document.getElementById('lv74-cam-preview')?.remove();` then click Run Camera Check → "camera on but preview broken" reports FAIL with the expected suggested-fix string.

**E. Archive checks land green when archive flag is on.**
PASS if: `HORNELORE_ARCHIVE_ENABLED=1` + select Janice + click Run Archive Check → 4 PASS results.

**F. Archive checks SKIP when no narrator selected.**
PASS if: no narrator selected + click Run Archive Check → 1 PASS (health probe), 3 SKIP (need narrator).

**G. copyReport actually copies.**
PASS if: click Copy Report → clipboard contains a string starting with `Hornelore UI Health Check`.

**H. No real session impact.**
PASS if: start a real chat with Janice → click Run Full UI Check mid-conversation → next narrator turn still sends, Lori still responds.  No `state.person_id` change, no `state.session.sessionStyle` change, no narrator switch fired by the harness.

## Report format

```
WO-UI-TEST-LAB-01 REPORT

Files changed:
  - ui/js/ui-health-check.js  (new)
  - ui/hornelore1.0.html  (Bug Panel section + script tag)
  - ui/css/lori80.css     (test-row layout + pill styles)
  - docs/reports/WO-UI-TEST-LAB-01.md

Acceptance:
  A harness loads:                  PASS/FAIL
  B full check < 3s:                PASS/FAIL
  C clean-stack PASS count >= 18:   PASS/FAIL
  D regression catch (camera bug):  PASS/FAIL
  E archive PASS when enabled:      PASS/FAIL
  F archive SKIP when no narrator:  PASS/FAIL
  G clipboard copy:                 PASS/FAIL
  H no real session impact:         PASS/FAIL

Topline first-run report (live stack):
  [paste copyReport output]

Known limitations:
  - Tests observe state but do not simulate clicks (no real switch fires).
    A future Phase 2 (Playwright) WO covers click-driven regression coverage.
  - Photos / Archive checks are gated on the same env flags the features
    need; DISABLED is reported, not FAIL.
  - Test set does not yet cover Take-a-break overlay, paired-interview
    mode, or the Operator Tools popovers (Bio Builder, Review Queue,
    Test Lab) — those land in a follow-up category as needed.

Follow-up:
  - WO-UI-TEST-LAB-02 — Playwright regression suite using same checks
  - WO-UI-TEST-LAB-COPY-01 — improve "suggested fix" copy per FAIL pattern
  - WO-UI-TEST-LAB-CI-01 — attach harness to start_all.sh post-warmup
                           sanity check (auto-print PASS/WARN/FAIL roll-up)
```

## Commit plan

Three commits:

```
git checkout -b feature/wo-ui-test-lab-01

# Commit 1: scaffold (engine + DOM section, no checks yet)
git add ui/js/ui-health-check.js ui/hornelore1.0.html ui/css/lori80.css
git commit -m "feat(ui): scaffold UI Health Check harness inside #lv10dBugPanel"

# Commit 2: 10 categories of checks
git add ui/js/ui-health-check.js
git commit -m "feat(ui): wire 10 UI Health Check categories with PASS/WARN/FAIL"

# Commit 3: report
git add docs/reports/WO-UI-TEST-LAB-01.md
git commit -m "test(ui): WO-UI-TEST-LAB-01 acceptance results"
```

## Out of scope

- Playwright migration (Phase 2 WO).
- CI integration (Phase 2 WO).
- Click-driven simulation (the harness OBSERVES state; it doesn't drive clicks).
- New visual primitives — re-uses existing `.lv10d-bp-value` color classes.
- Server-side test endpoints — uses only existing `/health` probes + read-only checks.

## Sequencing

Independent of WO-SESSION-STYLE-WIRING-01.  Both can land in parallel.  When WO-SESSION-STYLE-WIRING-01 ships, add a Session Style category to the harness covering: "questionnaire_first bypasses incomplete gate", "tier-2 directive injection observable in last system prompt", etc. — that's a small additive PR, not a separate WO.

When WO-AUDIO-NARRATOR-ONLY-01 ships, add an Audio Capture category covering: "MediaRecorder available", "TTS gate respected", "audio not recorded during Lori speech" — again, additive.

This makes the UI Health Check the operator's living preflight that grows with the product.
