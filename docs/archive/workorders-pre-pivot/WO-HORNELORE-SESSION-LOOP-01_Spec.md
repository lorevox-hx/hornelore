# WO-HORNELORE-SESSION-LOOP-01 — Post-Identity Conversation Loop

```
Title:    Build the post-identity conversation loop that routes per sessionStyle
Owner:    Claude
Mode:     Surgical implementation, additive on top of existing systems
Priority: Critical — without this, every narrator who completes identity
          intake hits a stub bubble and the system dead-ends a second time
Scope:    Frontend only.  Reuse Bio Builder questionnaire schema, identity
          state machine, transcript guard, archive endpoints (live), and
          Kawa / Chronology as PASSIVE context.  No new backend.
```

## Problem

WO-SESSION-STYLE-WIRING-01 / Slice 1 closed the FIRST dead-end (incomplete narrators trapped at the v9 gate).  Corky now reaches identity intake.  But after `state.session.identityPhase === "complete"`, the lane terminates with a friendly stub bubble and **Lori has no defined next behavior**.  The system is event-driven fragments, not a controlled conversation engine.

Five styles, one real lane:
- `questionnaire_first` → identity works, Bio Builder walk is a stub
- `warm_storytelling` → default Lori chat (works but not explicitly routed)
- `clear_direct` → byte-stable with default (no real behavior)
- `memory_exercise` → byte-stable with default (no real behavior)
- `companion` → byte-stable with default (no real behavior)

## Product rule

```
After identity is complete, the session NEVER dead-ends.
Lori always has a next step, defined by the operator's chosen sessionStyle.
```

Per-style behavior table — concrete enough to test:

| sessionStyle | Behavior after identity complete |
|---|---|
| `questionnaire_first` | Walk Bio Builder MINIMAL_SECTIONS field-by-field.  Lori asks one structured question per non-repeatable field.  Each answer parsed → PUT to `/api/bio-builder/questionnaire`.  Loop until all minimal fields filled OR narrator asks to switch.  Skip + Tell-a-story-instead affordances. |
| `clear_direct` | Same MINIMAL_SECTIONS walk as questionnaire_first BUT shorter Lori prompts ("What was your father's name?" not "Tell me about your father, what was his full name?").  Style directive injected. |
| `warm_storytelling` | Existing default — Lori uses the phase-aware composer.  No structured walk; narrative + probing.  This WO adds explicit routing so it's no longer "fall-through." |
| `memory_exercise` | Recognition-cue prompts.  Patient pacing (WO-10C cognitive support stretches already shipped — this just routes to that posture).  No factual extraction pressure. |
| `companion` | No proactive question-asking.  Lori reflects + listens.  Per-turn directive suppresses extraction prompts. |

## Architecture decisions baked in

1. **One orchestrator, not five state machines.**  A single dispatcher (`lvSessionLoopOnTurn`) is called after every narrator turn lands.  It reads `state.session.sessionStyle` + the current segment + asked-keys ledger, and decides the next action.  No per-style worker threads.

2. **Reuse existing storage paths.**  Bio Builder writes go through the existing `/api/bio-builder/questionnaire` PUT.  Archive writes (when WO-AUDIO-NARRATOR-ONLY-01 lands) go through `/api/memory-archive/turn`.  This WO does not add a new persistence path.

3. **Kawa, Chronology, Life Map are PASSIVE context.**  The loop reads from them ("what era are we in?", "any kawa segment touching this field?") but does not write to them.  Active Kawa/Chronology mutation is its own future WO.

4. **Style directives compose with the loop, they don't replace it.**  Tier-2 directives (clear_direct / memory_exercise / companion) are short string addenda to the system prompt that change Lori's *tone* without changing the loop's *control flow*.  questionnaire_first overrides flow itself (structured walk).  warm_storytelling is the no-op default.

5. **Loop is observation-friendly.**  Every dispatch decision logs `[session-loop] style=X segment=Y action=Z reason=W` so the UI Health Check can verify routing without invoking a real chat turn.

## Hard constraints

- No new backend routes (use `/api/bio-builder/questionnaire`, `/api/transcript/*`, `/api/memory-archive/*` already mounted).
- No new questionnaire schema (use `bio-builder-questionnaire.js` MINIMAL_SECTIONS / FULL_SECTIONS as-is).
- No new state machine for identity intake — keep `startIdentityOnboarding` / `handleIdentityPhaseAnswer` from app.js:2881–3230.
- No mutation of Kawa or Chronology (passive read only).
- No regression of warm_storytelling default — must remain the byte-stable opt-out.
- No prompt-composer rewrite — inject style directives via the existing `_buildRuntime71` payload extension surface.
- Repeatable BB sections (parents, siblings, grandparents iteration with "how many?" prompts) deferred to a Phase 2 WO.

## Files

Add:
- `ui/js/session-loop.js` — orchestrator owning `lvSessionLoopOnTurn`, `_walkBioBuilderField`, `_emitStyleDirective`, the asked-keys ledger.
- `docs/reports/WO-HORNELORE-SESSION-LOOP-01.md` — landing report.

Modify:
- `ui/js/session-style-router.js` — replace the `_enterBioBuilderSectionWalk` stub with a real call into `lvSessionLoopOnTurn({ trigger: "identity_complete" })`.  Hook tier-2 styles into `_emitStyleDirective`.
- `ui/js/app.js` — after each narrator answer is processed (the existing `sendUserMessage` / extract pipeline), call `lvSessionLoopOnTurn({ trigger: "narrator_turn", text })` ONCE.  Identity-phase answers continue routing through `handleIdentityPhaseAnswer` first; the loop is invoked only after identity is complete OR for non-identity styles.
- `ui/js/state.js` — add `state.session.loop` substate (currentSection, currentField, askedKeys, lastTrigger, lastAction).
- `ui/js/ui-health-check.js` — extend Session Style category with loop-routing checks (next-action observable, askedKeys ledger present).

Do NOT touch:
- `server/code/api/routers/*` — backend stays as-is.
- `server/code/api/extract.py` — extraction layer untouched.
- `bio-builder-questionnaire.js` — questionnaire schema is the source of truth.
- `kawa.js` / Memory River render — read-only consumer here.

## Implementation plan

### Step 1 — Loop scaffold (no behavior change)
Create `ui/js/session-loop.js`:

```
window.lvSessionLoopOnTurn = function (event) {
  // event = { trigger: "identity_complete" | "narrator_turn" | "operator_skip", text?, fieldPath? }
  if (!state.session) return;
  const style = (state.session.sessionStyle) || "warm_storytelling";
  if (!state.session.loop) {
    state.session.loop = {
      currentSection: null,
      currentField: null,
      askedKeys: [],
      lastTrigger: null,
      lastAction: null,
    };
  }
  state.session.loop.lastTrigger = event && event.trigger;

  // Always log for harness observability
  console.log("[session-loop] dispatch:", { style, trigger: event.trigger,
    section: state.session.loop.currentSection,
    field: state.session.loop.currentField });

  switch (style) {
    case "questionnaire_first": return _routeQuestionnaireFirst(event);
    case "clear_direct":        return _routeClearDirect(event);
    case "memory_exercise":     return _routeMemoryExercise(event);
    case "companion":           return _routeCompanion(event);
    case "warm_storytelling":
    default:                    return _routeWarmStorytelling(event);
  }
};
```

Acceptance gate at this step: dispatcher fires, all branches are no-ops (just log).  Byte-stable behavior.

### Step 2 — questionnaire_first walk
`_routeQuestionnaireFirst(event)`:
- If trigger is `identity_complete` OR `narrator_turn` and segment is `sections`:
  - Pick next empty MINIMAL_SECTIONS field not in `askedKeys`.
  - If found: append Lori bubble asking the question, push field into `askedKeys`.
  - If none left: append "Your basics are saved.  Want to keep going through your story?" + offer to switch to `warm_storytelling`.
- If trigger is `narrator_turn` AND we're in the middle of a question:
  - Run extracted answer through existing `/api/extract-fields` (no override).
  - PUT the resulting field value to `/api/bio-builder/questionnaire`.
  - Recurse to ask next field.

Field-prompt source: `bio-builder-questionnaire.js` already defines per-field labels + helpers.  Use the existing `field.label` + `field.prompt` (or fall back to a simple "What is your <fieldName>?").

Repeatable sections (parents/siblings/grandparents) are SKIPPED in Phase 1.  Loop logs `[session-loop] skipping repeatable section: parents (Phase 2)`.

### Step 3 — Tier-2 directives via _emitStyleDirective
`_emitStyleDirective(style)` returns a short system-prompt addendum:

```
clear_direct      → "Ask one short question at a time. Avoid open-ended
                     exploration. Acknowledge briefly, then move on."
memory_exercise   → "Use recognition cues. Allow long silences. Never
                     correct. Speak more slowly. Match WO-10C cognitive
                     support pacing."
companion         → "Don't probe for facts. Listen. Reflect feelings.
                     Speak less than the narrator does."
warm_storytelling → ""    (no addendum — default)
questionnaire_first → ""  (the walk itself owns Lori's prompts)
```

Inject into `_buildRuntime71()` (or sibling — survey will pin the exact entry) as a new optional `session_style_directive` field on the runtime payload.  The backend prompt composer reads it and appends if non-empty.  **Backend change required only if the runtime payload doesn't already pass through arbitrary keys** — the survey at WO-SESSION-STYLE-WIRING-01 prep will confirm this is a passthrough, not a backend wire-up.

For Phase 1 if backend doesn't passthrough, fall back to client-side directive injection at `sendUserMessage` time (prepend to the system context the WS sends).  Either path lands the same string.

### Step 4 — Identity-handoff trigger
In session-style-router.js, replace the stub bubble with:

```
function _enterBioBuilderSectionWalk(personId) {
  // Real handoff: tell the loop identity just completed.
  if (state.session.questionnaireFirst) {
    state.session.questionnaireFirst.segment = "sections";
  }
  if (typeof window.lvSessionLoopOnTurn === "function") {
    window.lvSessionLoopOnTurn({ trigger: "identity_complete" });
  }
}
```

Also: when `handleIdentityPhaseAnswer` flips `identityPhase` to `"complete"`, fire the same trigger — covers the case where identity completes mid-conversation, not just at room init.

### Step 5 — Per-turn invocation
At the end of the existing user-message handling in app.js (after extract-fields runs, after Bio Builder write), add:

```
if (state.session && state.session.identityPhase === "complete" &&
    typeof window.lvSessionLoopOnTurn === "function") {
  try {
    window.lvSessionLoopOnTurn({ trigger: "narrator_turn", text: lastUserText });
  } catch (e) {
    console.warn("[session-loop] dispatch threw:", e);
  }
}
```

Idempotent — calling twice for the same turn is safe (the dispatcher checks askedKeys before re-asking).

### Step 6 — UI Health Check extension
Add to `ui-health-check.js` Session Style category:

- `lvSessionLoopOnTurn function present` → PASS/FAIL
- `state.session.loop substate present (when identity complete)` → PASS/INFO
- `askedKeys ledger is array` → PASS/WARN
- `last loop dispatch is logged` (read recent console history if available) — INFO only
- `tier-2 directive injection observable` (probe `_buildRuntime71` output for `session_style_directive` field, or check fallback path) → PASS/WARN

## Acceptance tests

**A. Corky doesn't dead-end after identity.**
PASS if: select Corky (incomplete) → Questionnaire First → Start Session → identity intake completes (name, DOB, birthplace) → Lori asks a Bio Builder question (NOT a stub bubble).  Verified by reading the next chat bubble and confirming it references a BB MINIMAL_SECTIONS field.

**B. Bio Builder walk advances.**
PASS if: narrator answers 3 BB questions in sequence → each answer is parsed and PUT to `/api/bio-builder/questionnaire` → next empty field is asked → asked-keys ledger grows from 1 to 3 to 4.

**C. Skip works.**
PASS if: narrator answers "skip" or operator clicks the skip affordance → field is added to askedKeys without writing → loop advances to next field.

**D. Tell-a-story-instead works.**
PASS if: narrator says "I'd rather tell a story" → loop pauses BB walk for ONE turn, narrator gets a warm_storytelling-flavored exchange, then loop resumes BB at next turn.

**E. Tier-2 directives observable.**
PASS if: select clear_direct → next outgoing system prompt to model contains the clear_direct directive substring.  PASS for memory_exercise + companion the same way.  Verified via api.log grep or runtime payload inspection.

**F. warm_storytelling byte-stable.**
PASS if: select warm_storytelling → 3 narrator turns → server prompt log shows NO `[SYSTEM_STYLE:` directive (no-op control).  Behavior identical to no-style baseline.

**G. UI Health Check post-loop.**
PASS if: after WO lands, harness Run Full UI Check shows: 0 critical FAIL, Session Style category all PASS or INFO, new "loop dispatcher present" check PASS, "askedKeys ledger" check PASS.

**H. Repeatable sections explicitly deferred.**
PASS if: when the walk hits a repeatable section (parents), console logs `[session-loop] skipping repeatable section: parents (Phase 2)` and the walk continues to the next non-repeatable section.

## Report format

```
WO-HORNELORE-SESSION-LOOP-01 REPORT

Files changed:
  - ui/js/session-loop.js  (new)
  - ui/js/session-style-router.js  (replace stub with real handoff)
  - ui/js/app.js  (per-turn dispatch hook)
  - ui/js/state.js  (state.session.loop substate)
  - ui/js/ui-health-check.js  (Session Style category extension)
  - docs/reports/WO-HORNELORE-SESSION-LOOP-01.md

Acceptance:
  A Corky no-dead-end:                PASS/FAIL
  B BB walk advances:                 PASS/FAIL
  C Skip works:                       PASS/FAIL
  D Tell-a-story works:               PASS/FAIL
  E Tier-2 directives observable:     PASS/FAIL
  F warm_storytelling byte-stable:    PASS/FAIL
  G UI Health Check post-loop:        PASS/FAIL
  H Repeatables deferred cleanly:     PASS/FAIL

Topline harness run after patch:
  [paste runAll summary]

Known limitations:
  - Repeatable sections (parents, siblings, grandparents) deferred
    to Phase 2 (WO-HORNELORE-SESSION-LOOP-02).  Walk skips them with
    explicit log line.
  - Tier-2 directive copy is first-pass; tuning is its own WO.
  - "Tell a story instead" is single-turn override; doesn't persist.
  - Kawa / Chronology are read-only context in this WO.  Active mutation
    (e.g. "save this answer as a Kawa segment") is its own WO.

Follow-up:
  - WO-HORNELORE-SESSION-LOOP-02 — repeatable section walk
  - WO-HORNELORE-DIRECTIVE-COPY-01 — tune tier-2 directive language
  - WO-HORNELORE-LOOP-KAWA-01 — Kawa active hooks (segment promotion
    from BB answers)
  - WO-AUDIO-NARRATOR-ONLY-01 — wire archive turn-append into the loop
    (loop becomes the canonical "store this turn" call site)
```

## Commit plan

Five commits:

```
git checkout -b feature/wo-hornelore-session-loop-01

# Commit 1: scaffold (loop + dispatcher, all branches no-op)
git add ui/js/session-loop.js ui/js/state.js
git commit -m "feat(ui): scaffold session loop dispatcher (Step 1)"

# Commit 2: questionnaire_first BB walk
git add ui/js/session-loop.js ui/js/session-style-router.js
git commit -m "feat(ui): wire questionnaire_first BB MINIMAL_SECTIONS walk (Step 2)"

# Commit 3: tier-2 directive injection
git add ui/js/session-loop.js ui/js/app.js
git commit -m "feat(ui): inject tier-2 session style directives via runtime payload (Step 3)"

# Commit 4: per-turn dispatch hook + harness extension
git add ui/js/app.js ui/js/ui-health-check.js
git commit -m "feat(ui): per-turn loop dispatch + UI Health Check loop coverage (Steps 5+6)"

# Commit 5: report
git add docs/reports/WO-HORNELORE-SESSION-LOOP-01.md
git commit -m "test(ui): WO-HORNELORE-SESSION-LOOP-01 acceptance results"
```

## Out of scope

- Repeatable sections walk (parents/siblings/grandparents iteration with "how many?" prompts) — Phase 2.
- Active Kawa segment promotion — separate WO.
- Audio capture wiring — that's WO-AUDIO-NARRATOR-ONLY-01; the loop becomes its call site once that lands.
- Backend prompt-composer rewrite — only one-line passthrough field added to runtime payload (or client-side fallback).
- Operator override mid-session ("force questionnaire_first into clear_direct now") — for now, style is locked when room is entered; switching styles requires returning to Operator.
- Repeated same-narrator session resume ("you were on field X last time, want to continue?") — deferred to a session-resume WO.

## Sequencing

Lands AFTER the current WO-SESSION-STYLE-WIRING-01 Slice 1 (already committed).  Effectively replaces / completes Slices 2 + 3 of that WO under a clearer name and with the orchestrator framing baked in.

Closes:
- Bug #200 (deferred Slice 2): BB walk
- Bug #201 (deferred Slice 3): tier-2 directives

Should land BEFORE WO-AUDIO-NARRATOR-ONLY-01 because the audio capture WO needs the loop as its canonical "store this turn" call site.
