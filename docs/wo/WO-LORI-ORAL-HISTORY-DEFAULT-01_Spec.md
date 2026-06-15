# WO-LORI-ORAL-HISTORY-DEFAULT-01

**Status:** SPEC — REVISED 2026-06-11 to make the `oral_history` style
INTRODUCTION explicit (the style does not yet exist in the runtime;
this WO adds it AND makes it the default)
**Severity:** MEDIUM-HIGH (introduces a new session style; consequential in posture)
**Narrator generality:** UNIVERSAL — authored under
`HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`
**Locked principle:** *The default Lori expects long uninterrupted narrator
responses. Cognitive-support pacing is a fall-back style for narrators who
need it, not the baseline posture.*

## Scope correction (2026-06-11 revision)

The original draft of this WO assumed `oral_history` already existed as
a session style and only needed the default flipped. **That assumption
was wrong.** The live `WO-LORI-COMMUNICATION-CONTROL-01` per-style
parameter table contains exactly four styles:

```
clear_direct=55 / warm_storytelling=90 / questionnaire_first=70 / companion=80
```

There is no `oral_history` style anywhere in the runtime — no parameter
row, no prompt block, no picker entry. (`memory_exercise` is also
referenced in docs/picker but missing from the live parameter table;
that gap is resolved separately by `MEMORY-EXERCISE-DECISION.md` and
`WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01`.)

This WO therefore does two things, in order:

1. **Introduce `oral_history` as a new session style** — define its
   prompt block, its parameter row, its picker entry, its disclosure
   description
2. **Make it the system default** — column default, picker default,
   composer fall-through, orchestrator gating

### The `clear_direct` question

`clear_direct` exists in the live parameter table (word cap 55) but
does not appear in the operator picker's five-style list per
`WO-UI-SHELL-01`, and no drafted artifact accounts for it. Build-time
investigation required: determine whether `clear_direct` is (a) a
dev/test style used by harnesses, (b) a legacy style superseded by
the current picker set, or (c) a real operator-selectable style that
the picker documentation omitted. Disposition:

- If (a): keep in parameter table, annotate as harness-only, exclude
  from picker and disclosure
- If (b): deprecate via small follow-up — remove from parameter table
  after confirming zero sessions reference it
- If (c): add to picker tooltips and Phase 9 disclosure alongside the
  others

The acceptance gates below include resolving this question. Do not
guess; check `interview_sessions.session_style` values in the live
database and grep harness configs.

## Why this WO exists

Today the system's default session style is questionnaire-first or
warm_storytelling (operator-picked, often defaulting to whichever was last
used). The locked principle the system was built around — one question at
a time, short word caps, cognitive-accessibility ladders — comes from the
questionnaire-first heritage.

The oral-history scaffolding document and the universal pivot make the
case that this default is wrong:

- Older narrators with sharp recall (the majority) tell chapters, not
  answers. Questionnaire pacing actively damages chapter momentum.
- Narrators who need cognitive support are the minority and are well-served
  by explicit operator switching to `companion`, `memory_exercise`, or
  `warm_storytelling`.
- Universal narrators (post-pivot) span the full range from highly
  articulate storytellers to those with significant cognitive variability;
  defaulting to the cognitive-support posture insults the former and the
  latter both — the former by under-engaging, the latter by setting an
  expectation the operator should be explicitly choosing instead.

The work is: introduce the style, then flip the default. The
introduction is the larger half — `oral_history` needs a prompt block
that did not previously exist, defining what Lori's composition
posture is in this style.

**This WO is only meaningful after Phase 1 of the redesign
(WO-LORI-STORY-FIRST-PHASE-1-01) has shipped.** Without Phase 1, the
oral-history default would still permit questionnaire-cadence composition
within a longer word cap. Phase 1 is what makes oral history actually feel
like oral history at the composition layer. This WO introduces the style
that makes Phase 1's behavior the system's default rather than an opt-in.

## Live evidence

The interview redesign document (WO-INTERVIEW-PROCESS-REDESIGN-01) Part 1
states the old vs new model. Today the system is "Question → Narrator
answer → Extraction → Next question." Phase 1 changes the composition
behavior; this WO changes the default that determines which composition
behavior runs when the operator hasn't explicitly chosen.

Projected evidence after this WO ships, against a narrator-agnostic test:

Narrator (Turn 01, free response to "tell me where you'd like to start"):
> "I grew up on a farm in eastern Washington. Three brothers, two sisters,
> my mom raised most of us through the Depression after my dad got sick. I
> still remember the first time I drove the tractor — I was maybe seven —
> and I drove it right into the irrigation ditch."

Pre-WO default (questionnaire-first): Lori narrows immediately.
> "Where in eastern Washington did you grow up?"

Post-WO default (oral_history): Lori reflects and opens broad.
> "Eastern Washington, three brothers and two sisters, your mom holding
> things together through the Depression — and you driving the tractor
> into the ditch at seven. That's a lot of story already. What stands out
> most when you think back on that time?"

The difference is not the word cap (both responses fit current caps). The
difference is the posture: questionnaire narrows; oral history reflects
and invites.

## Root cause

Five places encode the questionnaire-first default:

1. **`session_style` column default** in the `interview_sessions` table.
   When a session is created without explicit style, this default is
   chosen.

2. **Operator picker UI** in the session-creation surface. The visual
   default (highlighted button, pre-selected dropdown value) influences
   operator choice toward whatever appears first.

3. **`prompt_composer.py` style dispatch**. When the assembled prompt
   references `session_style`, the fall-through clause when no match is
   found defaults to questionnaire behavior rather than oral_history.

4. **`lori_communication_control.py` per-style parameters**. The word cap
   table currently defaults missing keys to the questionnaire-first cap
   (70 words) rather than the oral_history cap (90 words).

5. **`SessionLoopOrchestrator`** (`WO-HORNELORE-SESSION-LOOP-01`) — runs
   Bio Builder one-question-at-a-time in any mode. This needs to be
   gated by session style so it does NOT run in oral_history mode (Bio
   Builder fills via chapter-driven extraction in oral_history; see
   sibling Bio Builder WO).

All five must change for the default flip to be coherent.

## Fix architecture

One style introduction plus five default-flip changes plus one
operator-UX consideration:

### 0. Introduce the `oral_history` style (NEW — the larger half)

The style does not exist; this section creates it.

**0a. Prompt block.** New constant `LORI_ORAL_HISTORY_RESPONSE` in
`prompt_composer.py`. This is the composition posture definition —
the thing that makes oral_history a real style rather than a longer
word cap. Initial block (wordsmith during build):

```
You are listening to someone tell the story of their life, one
chapter at a time. The narrator leads. You follow.

When the narrator is telling a story, your job is to receive it.
Reflect something concrete from what they just said — a place, a
person, a detail in their own words — before anything else. Do not
redirect. Do not verify spellings or dates. Do not steer back to an
earlier topic. The chapter they are telling is the most important
thing happening.

When the narrator pauses or finishes a thread, you may open one
door: a broad invitation ("What stands out most from that time?")
or a gentle continuation of something they mentioned earlier. One
question at most. Broad before specific. Never two topics in one
question.

Long silences are welcome. Long stories are welcome. If the
narrator wanders across decades, follow them — chronology is their
choice, not yours. You may gently anchor time only when they seem
to want it ("That would have been before the war?") and never as
correction.

You are not running a questionnaire. You are sitting with someone
who is remembering their life out loud.
```

This block REPLACES `LORI_INTERVIEW_DISCIPLINE`'s question-shaping
guidance when style is oral_history; the Grice-maxim cooperative
foundations from `LORI_INTERVIEW_DISCIPLINE` remain layered beneath
(Layer 1 architecture unchanged). The exact composition of which
directives carry over vs. get replaced is a build-time decision
against the live `LORI_INTERVIEW_DISCIPLINE` text; the principle is
that question-cadence directives are superseded and cooperative-
communication directives persist.

**0b. Parameter row.** Add `oral_history` to the per-style parameter
table (full table in section 4 below). Headline values: word cap 90,
question count cap 1, momentum threshold 0.6, thread bank active,
longest silence ladder of the conversational styles.

**0c. Schema enum.** If `session_style` is enum-constrained at the
DB level (CHECK constraint or enum type), the migration must extend
the allowed values to include `'oral_history'` BEFORE the default
flip migration. If it's a free-text column, document the canonical
string in the schema comment.

**0d. Picker entry.** New entry in the operator picker (section 2
below covers ordering and tooltip).

**0e. Disclosure entry.** New family-facing description in the Phase 9
disclosure (handled by `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01`, which
already describes oral-history posture; verify the style name matches
the runtime string exactly).

**0f. Resolve `clear_direct` disposition.** Per the Scope correction
section: investigate, classify (harness-only / deprecate / promote to
picker), and document the outcome in this WO's build report. The
parameter table in section 4 carries `clear_direct` forward unchanged
pending that investigation — removing it is NOT in scope for this WO
unless investigation shows zero references.

### 1. Default column value

Migration: `session_style` column in `interview_sessions` table default
value changes from current value to `'oral_history'`. Existing rows
unchanged (they have explicit values from when sessions were created;
not retroactively rewritten). This migration depends on 0c (enum
extension) running first.

### 2. Operator picker UI default

The session-creation surface presents the five styles with `oral_history`
visually highlighted as default. Other styles remain one click away. The
picker order also changes (cosmetic but signaling):

Before: `questionnaire_first`, `warm_storytelling`, `oral_history`,
`companion`, `memory_exercise`

After: `oral_history`, `warm_storytelling`, `companion`,
`memory_exercise`, `questionnaire_first`

Rationale: order signals priority. Oral history is the expected default.
Questionnaire-first moves to the end of the list — it remains available
for narrators who need structured biographical sequencing, but it's no
longer the visual baseline.

The picker also gains a short explanatory tooltip on each style:

- **oral_history** (default) — "Lori listens long, asks little, follows
  the narrator's chapters. Best for narrators who can carry a story and
  want to."
- **warm_storytelling** — "Shorter exchanges, more frequent reflection,
  gentler pacing. Good for narrators who want help finding their thread."
- **companion** — "Minimal interview structure. Lori is mostly a present
  listener. Good for grief, end-of-life reflection, or quiet narrators."
- **memory_exercise** — "Designed for narrators with mild cognitive
  variability. Lori listens first and prompts sparingly with anchors."
- **questionnaire_first** — "Structured biographical questions in
  sequence. Best for narrators who want a clear scaffold and find
  open-ended conversation tiring."

Tooltip language matches Phase 9 disclosure descriptions exactly. Source
of truth is the disclosure; picker tooltips pull from it.

### 3. Composer dispatch fall-through

`prompt_composer.py` style dispatch: when `session_style` is unset,
malformed, or unknown, fall through to `oral_history` block assembly
rather than `questionnaire_first`. Unknown style logs a warning but does
not error.

### 4. Communication control parameter defaults

`lori_communication_control.py` per-style parameter table extended so
every parameter has an explicit per-style value (no implicit defaults).

The CURRENT live table has four styles and one parameter:

```
clear_direct=55 / warm_storytelling=90 / questionnaire_first=70 / companion=80
```

The table below is the target state. Note three changes from live:
(1) `oral_history` row is NEW (introduced by section 0); (2)
`memory_exercise` row is NEW (introduced by `WO-LORI-MEMORY-EXERCISE-
IMPLEMENTATION-01` — if that WO hasn't shipped when this one builds,
carry the column as specified here and that WO inherits it); (3)
`warm_storytelling` word cap moves from 90 to 70 — under the live
table warm_storytelling had the longest cap because it was the most
conversational style available; with oral_history introduced at 90,
warm_storytelling settles to the middle. Verify with operator before
build that the 90→70 change is wanted; keeping it at 90 is defensible
too (in which case oral_history and warm_storytelling share the cap
and differ on momentum/ladder/orchestrator behavior).

Per-style parameters (target state):

| Parameter | oral_history (NEW) | warm_storytelling | companion | memory_exercise (NEW) | questionnaire_first | clear_direct |
|---|---|---|---|---|---|---|
| Word cap | 90 | 70 | 50 | 60 | 70 | 55 (unchanged) |
| Question count cap | 1 | 1 | 1 | 1 | 1 | 1 |
| Atomicity check | enforced | enforced | enforced | enforced | enforced | enforced |
| Reflection grounding (Phase 1) | enforced | enforced | enforced | enforced | enforced | enforced |
| Story momentum threshold | 0.6 | 0.55 | 0.4 | 0.5 | 0.7 | 0.7 |
| Layer 3-4 question suppression | aggressive | moderate | aggressive | aggressive | minimal | minimal |
| Thread bank surfacing | active | active | active | active | inactive | inactive |
| Silence ladder (sec) | 180 / 600 / 1200 | 120 / 300 / 600 | 240 / 720 / 1500 | 150 / 450 / 900 | 90 / 240 / 480 | 90 / 240 / 480 |

`clear_direct` values mirror questionnaire_first pending the
disposition investigation (section 0f). If investigation classifies it
harness-only, annotate the row; if deprecate, removal is a follow-up
WO; if promote, add picker/disclosure entries in a follow-up.

Notes on the per-style tuning:

- Oral_history has the longest silence ladder of the conversational
  styles because chapters need breathing room. Companion has the
  longest overall because grief and reflection need even more.
- Story momentum threshold varies by style: oral_history triggers story
  mode at moderate momentum (0.6); questionnaire_first requires very high
  momentum (0.7) before suppressing factual questions, because in
  questionnaire mode the operator has explicitly chosen structured asking.
- Thread bank is inactive in questionnaire_first because that style is
  explicitly sequential — surfacing a banked thread mid-questionnaire
  would disrupt the structure the operator picked.

### 5. Session loop orchestrator gated by style

`SessionLoopOrchestrator` currently runs Bio Builder one-question-at-a-time
in any mode. Modified to:

- In `questionnaire_first` mode: runs as today (one BB question per turn,
  field-by-field walk through bio schema)
- In `warm_storytelling` mode: runs with longer between-question gaps and
  prefers fields that can be asked conversationally (avoids "what is your
  middle name" mid-story)
- In `oral_history`, `companion`, `memory_exercise` modes: **does NOT
  run.** Bio is filled via chapter-driven extraction (sibling Bio Builder
  WO) and operator direct-entry between sessions

This is the most consequential of the five changes. It says: in oral_history
mode, Lori does not have a structured agenda. The narrator drives. The
extractor harvests. The operator fills gaps offline. Lori is a listener,
not a question engine, full stop.

### 6. Operator-facing change notification

On first session created after this WO deploys, the operator sees a
one-time notification on the session-creation surface:

> The default session style has changed to oral_history. Lori now
> listens longer, asks less, and follows the narrator's chapters at
> their pace. You can switch to other styles anytime; they remain
> available for narrators who need structured questioning, cognitive
> support, or shorter exchanges. Tap each style for a description.

Notification dismissable; persisted so it shows once per operator
account.

For tenant zero (Chris), this is a documentation event since you already
know about the change. For future operators it's the first signal that
this is not a chatbot Q&A system.

## Acceptance gates

0. **The `oral_history` style exists as a first-class runtime style.**
   - `LORI_ORAL_HISTORY_RESPONSE` prompt block defined in
     `prompt_composer.py` and assembled when style is oral_history
   - Parameter row present in `lori_communication_control.py` table
     with all parameters explicit
   - Schema accepts `'oral_history'` value (enum extended if
     constrained)
   - Session composed under oral_history uses the new prompt block —
     verifiable via prompt assembly log line
     `[composer] style=oral_history block=LORI_ORAL_HISTORY_RESPONSE`
   - `clear_direct` disposition investigated and documented in build
     report (harness-only / deprecate / promote — with evidence from
     live `interview_sessions.session_style` values and harness
     config grep)

1. **New sessions default to oral_history without explicit operator choice.**
   - Session created via API with no `session_style` field → row written
     with `session_style = 'oral_history'`
   - Session created via UI with operator clicking "create" without
     changing picker → row written with `session_style = 'oral_history'`

2. **Operator picker visually defaults to oral_history.**
   - First style in the list
   - Pre-selected
   - Tooltip text matches Phase 9 disclosure descriptions

3. **Composer assembles oral_history prompt block when style is missing
   or unknown.**
   - Session with `session_style = NULL` → composer assembles oral_history
   - Session with `session_style = 'malformed_value'` → composer assembles
     oral_history, logs warning
   - Session with explicit valid style → composer assembles that style

4. **Communication control parameters honor per-style table.**
   - oral_history session: word cap 90, story momentum threshold 0.6,
     thread bank active
   - questionnaire_first session: word cap 70, story momentum threshold 0.7,
     thread bank inactive

5. **Session loop orchestrator runs only in questionnaire/storytelling modes.**
   - oral_history session: orchestrator does NOT inject Bio Builder questions
   - questionnaire_first session: orchestrator runs as today
   - warm_storytelling session: orchestrator runs with gap and field
     selection rules

6. **Existing sessions are not retroactively modified.**
   - Sessions created before this WO deployed continue with their
     original style
   - Migration does not rewrite existing rows
   - Operator can manually convert an existing session to a different
     style if desired (existing capability, unchanged)

7. **One-time operator notification fires once per operator.**
   - First session-creation surface load after deploy: notification visible
   - Dismissal persists across logins
   - Notification does NOT appear on subsequent session creations

8. **Phase 9 disclosure language matches operator picker tooltips.**
   - Each style description in the picker is character-identical to the
     corresponding description in the disclosure
   - Cross-reference test: parse both sources, assert equality

9. **Safety paths unchanged across style change.**
   - Acute path fires identically in all five styles
   - Past-tense acknowledgment fires identically in all five styles
   - Softened mode persistence fires identically in all five styles
   - Phase 9 disclosure correctly describes default-changed behavior

## Test coverage

`tests/test_session_style_default.py` (new):

- 4 tests: column default value, API session creation default, UI
  session creation default, malformed/missing style fall-through

`tests/test_operator_picker.py` (new):

- 5 tests: picker order, pre-selected default, tooltip presence,
  tooltip text equality with disclosure, persisted dismissal of
  one-time notification

`tests/test_communication_control_per_style.py` (extend existing):

- 10 tests: each of 5 styles × 2 parameters (word cap + momentum
  threshold) explicit value verification

`tests/test_session_loop_orchestrator_gating.py` (extend existing):

- 6 tests: orchestrator runs in questionnaire_first, runs with
  gap/selection in warm_storytelling, does NOT run in oral_history,
  does NOT run in companion, does NOT run in memory_exercise, runs
  correctly when style changes mid-session

`tests/test_oral_history_default_integration.py` (new):

- 4 end-to-end tests: full session from creation through 5 turns in
  oral_history default; verify no Bio Builder orchestrator injection,
  verify Phase 1 reflection grounding active, verify thread bank
  active, verify safety paths unaffected

Target: 29 new/extended tests, all green before merge.

## Live verification

1. Cycle stack with all WOs in trio + Phase 1 + this WO active
2. Create new session via operator UI without touching style picker
3. Confirm:
   - Session row has `session_style = 'oral_history'`
   - Lori first turn uses oral_history prompt block
   - Word cap is 90
   - Thread bank service initialized
   - No Bio Builder orchestrator activity in logs
   - One-time notification visible on operator picker
4. Dismiss notification, create second session, confirm notification
   does NOT reappear
5. Create third session with operator explicitly selecting
   `questionnaire_first`
   - Confirm Bio Builder orchestrator runs as before
   - Confirm word cap is 70
   - Confirm thread bank service not surfacing
6. Run a known narrator-turn sequence (mastoidectomy / Spokane test from
   Phase 1) against oral_history default and confirm:
   - Reflection grounded to narrator content
   - Layer 1 question composed, zero Layer 2-4
   - No "where were you born" / "what's your middle name" type questions
     appear
7. Counter-test: trigger acute safety phrase. Confirm safety path fires
   identically to pre-WO behavior in all five styles.

## Files changed

- `server/data/migrations/` (new: alter `interview_sessions.session_style`
  default to `'oral_history'`)
- `server/code/api/db.py` (+~10 lines: explicit oral_history fallback in
  session creation helpers)
- `server/code/services/prompt_composer.py` (+~15 lines: fall-through
  clause for missing/unknown style)
- `server/code/services/lori_communication_control.py` (+~30 lines:
  per-style parameter table extension, missing-key defaults)
- `server/code/services/session_loop_orchestrator.py` (+~40 lines:
  style-based gating, warm_storytelling gap+selection logic)
- `ui/js/session-create.js` (+~80 lines: picker reorder, default
  selection, tooltip rendering, one-time notification with persistence)
- `ui/css/session-create.css` (+~30 lines: notification styling, picker
  visual default highlight)
- `tests/test_session_style_default.py` (new, ~70 lines: 4 tests)
- `tests/test_operator_picker.py` (new, ~90 lines: 5 tests)
- `tests/test_communication_control_per_style.py` (+~120 lines: 10 tests)
- `tests/test_session_loop_orchestrator_gating.py` (+~110 lines: 6 tests)
- `tests/test_oral_history_default_integration.py` (new, ~140 lines:
  4 integration tests)

## Related lanes

- **WO-LORI-STORY-FIRST-PHASE-1-01** (REQUIRED predecessor — must be
  GREEN before this WO can ship; Phase 1 is what makes oral history
  feel like oral history at composition layer)
- **WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01** (REQUIRED predecessor —
  oral-history default raises frequency of mortality and past-difficulty
  content; safety machinery must be ready)
- **WO-LORI-SOFTENED-MODE-PERSISTENCE-01** (REQUIRED predecessor —
  Gate 6 GREEN required before increasing exposure to safety-adjacent
  content)
- **WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01** (REQUIRED predecessor —
  consent must accurately describe oral-history default before it
  becomes default; picker tooltips pull from disclosure)
- **HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md** — strategy doc establishing
  universal framing; this WO is the operational completion of the
  pivot's first phase
- **WO-INTERVIEW-PROCESS-REDESIGN-01** Phase 2+ (sequenced after this
  WO) — turn classifier, orchestrator, momentum LLM upgrade,
  rhythm adaptation, quality harness
- **Bio Builder universal lane** (sequenced after this WO) — the
  orchestrator gating in this WO is the precondition for the
  chapter-driven Bio Builder model

## Out of scope (deferred)

- **Per-narrator default style** based on prior session history. Today
  the operator picks per session. A future WO may allow per-narrator
  default style (Kent always opens in oral_history, Janice always opens
  in warm_storytelling) — but doing this requires the per-narrator
  template work flagged in the strategy doc audit. Defer.
- **Automatic style switching mid-session** based on narrator behavior.
  Considered and rejected for now. The operator picks, the narrator
  drives within the picked style. Automatic switching would surface
  unpredictably to both. May revisit after rhythm adaptation work
  (Phase 2+ Part 10).
- **A/B testing of the default change.** This is a posture decision,
  not an experiment. Either oral_history is the right default or it
  isn't; the strategy and architecture say it is. No A/B.
- **Migration of existing sessions to oral_history.** Existing sessions
  keep their picked style. Forcing retroactive change would damage
  in-flight narrator relationships.
- **Style change audit log.** Today operator can change style mid-session
  with no record. Worth logging eventually for memoir-editing context
  ("Janice's session 14 switched from warm_storytelling to companion
  after Turn 06") but not in scope here.
