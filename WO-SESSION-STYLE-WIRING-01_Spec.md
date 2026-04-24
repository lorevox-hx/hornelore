# WO-SESSION-STYLE-WIRING-01 — Make Operator Session Style Drive Narrator Behavior

```
Title:    Wire Operator session style to narrator-room behavior
Owner:    Claude
Mode:     Surgical implementation, in-tree behind narrow guards
Priority: High — Operator picker today is decoration; product promise is broken
Scope:    Frontend only.  Reuse existing identity-intake state machine,
          existing Bio Builder questionnaire schema, existing /api/interview
          composer.  No new backend routes.  No new tables.
```

## Problem

WO-UI-SHELL-01 added an Operator-tab session style picker (5 radios) and persists the choice to `state.session.sessionStyle` + `localStorage['hornelore_session_style_v1']`. **Nothing reads that value to change Lori's interview flow.** Picking "Questionnaire First" today is purely cosmetic.

Verified live in Chrome on 2026-04-24:
- Operator → "Questionnaire First" → Start Narrator Session for Corky (a narrator missing name + DOB).
- `state.session.sessionStyle = "questionnaire_first"` ✓
- Narrator-room topbar opens ✓ (after #194 persistence fix)
- But: Corky goes through the v9-incomplete-gate → `lv80ShowIncompleteNarratorUi` renders the "fill in basics" card → the questionnaire never runs.
- Even if Corky were complete, Lori's behavior would be byte-identical to the warm_storytelling default. The 5 radios all produce the same chat experience.

## Product rule (locked by Chris, 2026-04-24)

```
Operator chooses the mode.
Narrator experiences the mode.
```

Per-style behavior:

| sessionStyle | Behavior |
|---|---|
| `questionnaire_first` | Structured questionnaire intake.  If identity basics are missing, Lori asks for them in chat first.  Then walks Bio Builder sections one structured question at a time.  **Bypasses v9 incomplete gate** — questionnaire IS the way an incomplete narrator becomes complete. |
| `clear_direct` | Short direct prompts.  One fact at a time.  Less story exploration. |
| `warm_storytelling` | Current default Lori behavior (no change). |
| `memory_exercise` | Recognition cues, gentle recall, more patience.  Already partially wired via posture segmented control + WO-10C; this WO unifies the entry point. |
| `companion` | Less extraction pressure, more listening.  Suppress proactive question-asking. |

## Design

Five styles → three implementation tiers:

**Tier 1 — `questionnaire_first` (this WO's primary deliverable).**
A new explicit interview lane inside the narrator room.  Has its own state machine, its own UI affordance ("Question N of M / Skip / I'd rather tell a story"), its own prompt pattern.  Reuses:
- `state.session.identityPhase` + `state.session.identityCapture` + `startIdentityOnboarding()` + `handleIdentityPhaseAnswer()` (app.js:2881–3230) for the identity-first segment.
- `bio-builder-questionnaire.js` `FULL_SECTIONS` / `MINIMAL_SECTIONS` (L219+) for the section walk.
- `/api/bio-builder/questionnaire` GET/PUT (questionnaire.py) for persisting answers.

**Tier 2 — `clear_direct`, `memory_exercise`, `companion`.**
Inject a short system-prompt directive at session start (and on narrator switch when style is preserved per #194) that tells Lori how to behave.  These are prompt-composer additions — NOT new state machines.  E.g. for `clear_direct`:
```
[SYSTEM_STYLE: clear_direct.  Ask one short question at a time.
 Avoid open-ended exploration.  Acknowledge briefly, then move on.]
```
Concrete deliverable: a `_lvSessionStyleDirective(style)` helper that returns the right system addendum, called by the existing prompt composer at the established injection point.

**Tier 3 — `warm_storytelling` is the no-op default.**
No behavior change — this is what Lori does today.  Selecting it explicitly clears any prior style directive.

The WO scopes Tier 1 fully (real new lane) + Tier 2 minimally (one-line directive per style).  Tier 3 is implicit.

## Architecture decisions baked in

1. **questionnaire_first BYPASSES the v9 incomplete gate.**  In `lv80SwitchPerson` (hornelore1.0.html ~L4670), when openStatus would be "incomplete" AND `state.session.sessionStyle === "questionnaire_first"`, do NOT route to `lv80ShowIncompleteNarratorUi`.  Instead set openStatus to "questionnaire_first" and route to a new `lvxStartQuestionnaireFirst(personId)` flow.

2. **Identity intake remains chat-driven.**  We don't build a new modal.  We invoke the existing `startIdentityOnboarding()` (app.js:2881) which already drives a 3-step name→DOB→birthplace conversation in the chat stream.  When all three land, `state.session.identityPhase === "complete"` and we transition to the Bio Builder section walk.

3. **Section walk is also chat-driven.**  After identity, Lori asks one question per Bio Builder section field.  Source: `bio-builder-questionnaire.js` MINIMAL_SECTIONS by default (toggleable via existing `intakeMinimalEnabled()`).  Each user answer is parsed via the existing extract-fields pipeline (no new path), with the resulting field written through `/api/bio-builder/questionnaire` PUT.

4. **No new backend routes.**  Phase 1 uses existing endpoints exclusively.  If we discover the existing endpoints are insufficient, we'll spec a follow-up — but the survey suggests they're not.

5. **Style directive lives in prompt-composer surface, not interview state machine.**  Tier 2 styles (clear_direct, memory_exercise, companion) inject their addendum once per turn into the existing system-prompt build path.  This keeps interview state machine simple and lets style toggling mid-session take effect immediately.

## Files

Add:
- `ui/js/session-style-router.js` — new module owning `lvSessionStyleEnter(style, personId)`, `_lvSessionStyleDirective(style)`, the questionnaire-first lane state machine, and the section-walk loop.

Modify:
- `ui/hornelore1.0.html` — `lv80SwitchPerson` gates: when openStatus would be "incomplete" + style is questionnaire_first, route to questionnaire-first lane instead.  Also call `lvSessionStyleEnter` from `lvNarratorRoomInit` so re-entering the narrator tab re-applies the style.
- `ui/js/app.js` — `lvNarratorRoomInit` (around line 6X0): after painting identity + controls, call `lvSessionStyleEnter(getSessionStyle(), state.person_id)`.  Also: extend the existing system-prompt composer to consult `_lvSessionStyleDirective(style)` for tier-2 styles.
- `ui/js/state.js` — add `state.session.questionnaireFirst` substate to track the lane (currentSection, currentField, askedKeys).
- `docs/reports/WO-SESSION-STYLE-WIRING-01.md` — landing report (created at end).

Do NOT touch:
- `server/code/api/routers/questionnaire.py` (use existing GET/PUT)
- `server/code/api/routers/interview.py` (no new question composer needed in Phase 1)
- Any extraction code (extract.py)

## Implementation plan

### Step 1 — sessionStyleRouter scaffold (no behavior change yet)
Create `ui/js/session-style-router.js`:

```
window.lvSessionStyleEnter = function (style, personId) {
  switch (style) {
    case "questionnaire_first": return _enterQuestionnaireFirst(personId);
    case "clear_direct":
    case "memory_exercise":
    case "companion":           return _emitStyleDirective(style);
    case "warm_storytelling":
    default:                    return _clearStyleDirective();
  }
};

function _lvSessionStyleDirective(style) { /* returns string */ }
```

Wire `lvNarratorRoomInit` to call `lvSessionStyleEnter(getSessionStyle(), pid)`.  Acceptance gate at this step: byte-stable behavior because all branches are no-ops.  Just confirm the dispatch fires.

### Step 2 — Bypass v9 incomplete gate when questionnaire_first
In `lv80SwitchPerson` (hornelore1.0.html ~L4732, the INCOMPLETE branch):

```
if (state.session && state.session.sessionStyle === "questionnaire_first") {
  state.narratorOpen.openStatus = "questionnaire_first";
  // (still rebuild state.session, preserve onboarding + sessionStyle)
  // Skip lv80ShowIncompleteNarratorUi — sessionStyleRouter takes over.
} else {
  state.narratorOpen.openStatus = "incomplete";
  lv80ShowIncompleteNarratorUi(personId);
}
```

Gate behavior: log `[v9-gate] questionnaire_first override — skipping incomplete UI for <pid>`.

### Step 3 — Identity-first segment of questionnaire-first lane
`_enterQuestionnaireFirst(pid)`:
1. If `hasIdentityBasics74()` is true → skip identity, go to step 4.
2. Else: append a Lori opener bubble: "Let's start with the basics, one at a time.  What's your full name?"  Set `state.session.identityPhase = "askName"`.
3. Subsequent narrator answers route through existing `handleIdentityPhaseAnswer()` (app.js:3030) which already drives name → DOB → birthplace.  When phase becomes "complete":
4. Transition to Bio Builder section walk.

No new chat-handling code — `handleIdentityPhaseAnswer` is already invoked from the chat send path; we just need to make sure `state.session.identityPhase` is properly set to `"askName"` when entering questionnaire_first with an incomplete narrator.

### Step 4 — Bio Builder section walk
After identity is complete, walk MINIMAL_SECTIONS (or FULL_SECTIONS if `intakeMinimalEnabled()` returns false).  For each section, for each non-repeatable field that's currently empty in the QQ payload:
1. Append a Lori bubble: "Let's fill in your <section title>.  <field prompt>?"
2. Wait for narrator answer.
3. Run normal extract-fields pipeline (no override).
4. PUT to `/api/bio-builder/questionnaire` with the new value.
5. Advance to next field.

State tracking on `state.session.questionnaireFirst`:
```
{
  active: true,
  segment: "identity" | "sections",
  currentSection: "personal",
  currentField: "fullName",
  askedKeys: [],   // capped at 200
}
```

Repeatable sections (parents, siblings, grandparents) are out of scope for Phase 1 — too much UX nuance ("how many parents do you want to add?").  They're handled in Phase 2 (WO-SESSION-STYLE-WIRING-02 if needed).

### Step 5 — Tier 2 directive injection
`_lvSessionStyleDirective(style)` returns:

```
clear_direct     → "Ask one short question at a time. Avoid open-ended
                    exploration. Acknowledge briefly, then move on."
memory_exercise  → "Use recognition cues. Allow long silences. Never
                    correct. Speak more slowly. Match WO-10C cognitive
                    support pacing."
companion        → "Don't probe for facts. Listen. Reflect feelings.
                    Speak less than the narrator does."
warm_storytelling → null  (no addendum)
questionnaire_first → null  (questionnaire lane handles its own prompts)
```

Inject into the existing prompt composer via a single `if (typeof _lvSessionStyleDirective === "function")` hook.  Find the system-prompt build site (likely `_buildRuntime71()` in app.js or a sibling) and append the directive when present.

### Step 6 — UI affordance in narrator room (questionnaire-first only)
Inside `#lvNarratorContextPanel`, when in questionnaire_first lane, render:
```
Question 7 of 24 · Personal info
[Skip this question]
[I'd rather tell a story instead]
```

"Skip" advances askedKeys without writing.  "Tell a story instead" temporarily switches to warm_storytelling for one turn (does NOT persist to localStorage), then returns to the questionnaire on the next answer.

## Acceptance tests

**A. Style picker persists across narrator switch (regression for #194).**
PASS if: select Questionnaire First on Operator, switch to Corky, click Start, narrator-room topbar pill shows "Questionnaire first".

**B. questionnaire_first bypasses v9 incomplete gate.**
PASS if: Corky (incomplete: missing name + DOB), style=questionnaire_first → narrator-room opens, console logs `[v9-gate] questionnaire_first override`, NO `lv80ShowIncompleteNarratorUi` card renders, identity-first opener bubble appears in chat.

**C. Identity intake completes via chat.**
PASS if: narrator answers "Corky McMaster" → Lori asks DOB → narrator answers "October 21 1949" → Lori asks birthplace → narrator answers "Williston, ND" → `state.session.identityPhase === "complete"` → state.profile.basics has name + dob + pob → backend has saved them.

**D. Section walk advances after identity.**
PASS if: identity complete → Lori asks first MINIMAL_SECTIONS field that's empty (e.g. "What was your father's full name?") → narrator answers → answer is parsed and stored → next empty field is asked.

**E. Tier 2 directive injection.**
PASS if: select clear_direct, send a turn, server-side prompt log shows the clear_direct directive appended to the system prompt.  PASS for memory_exercise and companion the same way.

**F. warm_storytelling is byte-stable default.**
PASS if: select warm_storytelling, send 3 turns, server-side prompt log shows no `[SYSTEM_STYLE:` directive (this is the no-op control).  Lori behavior is identical to no-style-selected baseline.

**G. Style override on existing narrator (Janice) doesn't break warm flow.**
PASS if: select Janice (complete), choose warm_storytelling, click Start → normal opener fires.  Switch to clear_direct mid-session → next turn shows the directive in server prompt log → narrator gets shorter Lori responses.

**H. localStorage survives reload.**
PASS if: select Questionnaire First, hard reload page → radio is still checked, `state.session.sessionStyle === "questionnaire_first"`, picking Janice → narrator room opens with Questionnaire First topbar pill (already verified for #194 — re-verify after this WO).

## Report format

```
WO-SESSION-STYLE-WIRING-01 REPORT

Files changed:
  - ui/js/session-style-router.js  (new)
  - ui/hornelore1.0.html  (lv80SwitchPerson gate bypass + lvNarratorRoomInit hook)
  - ui/js/app.js  (prompt-composer directive injection + lvNarratorRoomInit hook)
  - ui/js/state.js  (state.session.questionnaireFirst substate)
  - docs/reports/WO-SESSION-STYLE-WIRING-01.md

Acceptance:
  A persistence:                  PASS/FAIL
  B incomplete-gate bypass:       PASS/FAIL
  C identity intake completes:    PASS/FAIL
  D section walk advances:        PASS/FAIL
  E tier 2 directive injection:   PASS/FAIL
  F warm_storytelling byte-stable:PASS/FAIL
  G mid-session style override:   PASS/FAIL
  H reload survival:              PASS/FAIL

Known limitations:
  - Repeatable sections (parents, siblings, grandparents) deferred
    to Phase 2.
  - Tier 2 directives are static one-liners; tuning copy is a future WO.
  - "Tell a story instead" is single-turn override; doesn't persist.

Follow-up:
  - WO-SESSION-STYLE-WIRING-02 — repeatable section walk (parents/siblings)
  - WO-SESSION-STYLE-COPY-01  — tune Tier 2 directive language
  - WO-SESSION-STYLE-RESUME-01 — questionnaire-resume on session restart
```

## Commit plan

Three commits, code-isolated:

```
git checkout -b feature/wo-session-style-wiring-01

# Commit 1: scaffold + dispatch (no behavior change)
git add ui/js/session-style-router.js ui/js/state.js
git commit -m "feat(ui): scaffold sessionStyleRouter dispatch (WO-SESSION-STYLE-WIRING-01 step 1)"

# Commit 2: questionnaire_first lane (gate bypass + identity + section walk)
git add ui/hornelore1.0.html ui/js/session-style-router.js ui/js/app.js
git commit -m "feat(ui): wire questionnaire_first lane with v9 gate bypass"

# Commit 3: tier 2 directive injection
git add ui/js/app.js ui/js/session-style-router.js
git commit -m "feat(ui): inject tier-2 session style directives into prompt composer"

# Commit 4: report
git add docs/reports/WO-SESSION-STYLE-WIRING-01.md
git commit -m "test(ui): WO-SESSION-STYLE-WIRING-01 acceptance results"
```

## Out of scope

- Backend `/api/interview/start` changes (use existing API surface only).
- New questionnaire field schema (use bio-builder-questionnaire.js as-is).
- Operator-side preview of "what Lori will sound like in this style" (a nice-to-have, follow-up).
- Style-switching UX in the narrator room itself (Operator picks, narrator room reflects).
- Repeatable section walk (parents/siblings/grandparents iteration with "how many?" prompts).

## Sequencing

Lands AFTER #194 persistence fix (already merged).  Independent of WO-AUDIO-NARRATOR-ONLY-01 — they touch different surface areas.  WO-UI-TEST-LAB-01 acceptance tests for "questionnaire_first override" can be added after this WO ships, providing a regression net for future style work.
