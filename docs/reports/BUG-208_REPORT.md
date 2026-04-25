# BUG-208 — Bio Builder cross-narrator contamination — Implementation Report

**Filed by:** Chris (2026-04-25 evening overnight directive)
**Built:** 2026-04-25 night (this commit)
**Status:** **CODE LANDED — NOT FULLY CLOSED** until live browser verification passes tomorrow morning per Chris's spec.

## Symptom

Switching from Christopher → Corky surfaced **Christopher's** Bio Builder questionnaire data under Corky in the in-memory blob. Console shows `[bb-drift] KEY MISMATCH` between in-memory section keys and localStorage section keys for the active narrator. **Block-everything** before parents touch the system: every session would otherwise pollute the next.

## Root cause (3 reinforcing failure modes)

1. **Async backend GET race.** `_restoreQuestionnaireFromBackend(pid)` is fire-and-forget. If a Christopher-pid GET is still in flight when the operator switches to Corky, the response (when it lands) overwrites `bb.questionnaire = sections` without verifying that `bb.personId` is still the pid the request was made under. **Last-write-wins, with the wrong narrator's data.**
2. **No backend `person_id` cross-check on the frontend.** The backend echoes `person_id` in its response shape, but the frontend wasn't reading it. A mistargeted/cached response would land silently.
3. **No pid scope assertion in `session-loop._saveBBAnswer`.** The function used `state.person_id` (read at call time) plus a passed-in `personId`, but didn't compare them, didn't compare to `bb.personId`, and didn't re-check after the network await. A switch mid-flight would PUT one narrator's answer under whichever pid the function was originally called with.

## Fix surface (3 files)

### 1. `ui/js/bio-builder-core.js`

**Added narrator-switch generation counter** (`_narratorSwitchGen`, exposed via `_currentSwitchGen()`). Every call to `_resetNarratorScopedState` and `_personChanged` bumps it **first** (before any await/persist work happens), so any in-flight async restores stamped under the OLD generation will see a stale counter when their response resolves.

**`_restoreQuestionnaireFromBackend(pid)`** — three-guard rejection on response:
- Guard A: switch-gen still matches stamped value (no narrator change happened during fetch)
- Guard B: `bb.personId === stampedPid` (in-memory pid hasn't moved)
- Guard C: `response.person_id === stampedPid` (backend agrees on identity)

If any guard fails, log `[bb-drift] backend QQ response DISCARDED: ...reason...` and discard the response. **Cannot overwrite the active narrator's blob with a different narrator's data.**

**`_persistDrafts(pid)`** — added a hard `[bb-drift] _persistDrafts BLOCKED` log + early-return when `pid !== bb.personId`. The pre-existing implicit gate is now explicit and audible.

### 2. `ui/js/session-loop.js`

**`_saveBBAnswer(personId, ...)`** — entry-time pid scope assertion. Three identifiers must agree before any work happens:
- `personId` (the pid we were called with)
- `state.person_id` (the active narrator)
- `state.bioBuilder.personId` (BB module's view of the active narrator)

If any disagree: log `[bb-drift] _saveBBAnswer SKIPPED: ...`, mark `state.session.loop.lastAction = "halted_pid_drift:..."`, return. Never PUTs.

**Post-fetch re-check** — after the `await _getQuestionnaireBlob(personId)` resolves, re-verify `state.person_id === personId` and `bb.personId === personId`. If the narrator switched during the GET, abort with `[bb-drift] _saveBBAnswer ABORTED post-fetch: narrator switched during BB GET`. **The "save Christopher's answer to Corky" race is now closed.**

**`_getQuestionnaireBlob(personId)`** — verify backend echo. After `await fetch()`, if `data.person_id !== personId`, log `[bb-drift] BB GET response REJECTED: ...` and return `{}` without caching. Backend mistargeting / cache surprise → caller sees an empty blob (safe) instead of a contaminated one.

### 3. `ui/js/ui-health-check.js`

Added **4 new BUG-208 checks** under the `session` category (operator-visible, surfaced in the harness):

| # | Check | What it verifies |
|---|---|---|
| 16 | `BB person scope: bb.personId === state.person_id` | Cardinal scope rule. FAIL if mismatch. |
| 17 | `BB questionnaire identity matches active profile` | Compares `bb.questionnaire.personal.fullName/dateOfBirth` against `state.profile.basics.fullName/dateOfBirth`. FAIL on contradiction (catches the literal Corky-shows-Christopher symptom). |
| 18 | `BB localStorage draft key scoped to active narrator` | Checks `localStorage["lorevox_qq_draft_<active_pid>"]` parses + its `personal.fullName` doesn't contradict the active profile. Other-narrator drafts existing is fine; we only need this narrator's view to be clean. |
| 19 | `BB narrator-switch generation counter wired` | Verifies `LorevoxBioBuilderModules.core._currentSwitchGen` is exposed (the in-flight backend GET defense lives or dies on this). |

## Verification — required before closing

**Chris does this tomorrow morning (Boris-style live verification, NOT agent-runnable):**

1. Hard refresh (Ctrl+Shift+R) so the new JS lands.
2. Switch Chris → Corky → Chris → Corky.
3. After each switch: open the Bug Panel → run Full UI Health Check.
4. Check the four new `session` category checks — all should be PASS (or SKIP if no narrator yet on the very first run).
5. With Corky active, look at her questionnaire view: it must be empty or Corky-specific. **No** Christopher fullName / dateOfBirth / placeOfBirth should appear.
6. Save a Corky `personal.birthOrder` field via the questionnaire_first lane.
7. Switch to Chris and back to Corky.
8. Corky's `birthOrder` should persist; Chris's questionnaire should be untouched.
9. Run Full UI Health Check one more time. **0 critical FAIL** in the `session` category.

If any check FAILs, capture the console (look for `[bb-drift]` lines), share the harness output, and we triage before declaring closed.

## What this fix does NOT address (deferred lanes)

- **Parents-by-next-week ship plan (Task #218)** — the broader 3-day plan is its own writeup.
- **Bug #193: camera not working post-restart on archive branch** — pending separate triage.
- **Tech debt P3: `state.session` split** — quiet-day refactor.
- The cache-busting strategy is still brittle. Hard refresh is required. Recommend `?v=<git-sha>` lane (P1 in the master checklist) at next quiet day.

## Files changed

```
ui/js/bio-builder-core.js   — 3 patches (gen counter + backend guards + persist guard)
ui/js/session-loop.js       — 2 patches (_saveBBAnswer assertions + _getQuestionnaireBlob echo check)
ui/js/ui-health-check.js    — 4 new harness checks (#16-#19 in session category)
docs/reports/BUG-208_REPORT.md — this file
docs/Hornelore-WO-Checklist.md — overnight queue + priority order
HANDOFF.md, README.md       — current-state refresh (already landed earlier this session)
```

## Syntax check

All three files parse clean:

```
node --check ui/js/bio-builder-core.js   → bb-core OK
node --check ui/js/session-loop.js       → session-loop OK
node --check ui/js/ui-health-check.js    → ui-health-check OK
```

## Mental model for future debugging

Three layers of defense, ordered cheapest→most expensive:

```
1. PERSIST gate (bio-builder-core.js _persistDrafts)
     If pid !== bb.personId → block with [bb-drift] log.
     Cheap; catches "wrong pid in caller" bugs.

2. RECEIVE gate (bio-builder-core.js _restoreQuestionnaireFromBackend)
     Stamp gen+pid at call.  On response, three guards:
       - gen still current
       - bb.personId still matches stamped pid
       - backend echoed person_id matches stamped pid
     Mid-cost; catches the in-flight async race.

3. WRITE gate (session-loop.js _saveBBAnswer)
     Pre-fetch: pid agrees across (caller, state, bb).
     Post-fetch: pid still agrees after the network await.
     Most expensive; catches the "narrator switched during BB GET" race.
```

Every defense logs `[bb-drift]` so the harness's drift-mismatch warning (existing `_qqDebugSnapshot`) will continue to be the primary tripwire — and we now have explicit named entry points for any further drift class that surfaces.
