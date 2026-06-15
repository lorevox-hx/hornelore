# WO-LORI-SOFTENED-MODE-PERSISTENCE-01

**Status:** SPEC — not yet started
**Severity:** CRITICAL (parent-session readiness Gate 6 — currently RED)
**Locked principle:** *After a safety moment, Lori does not snap back to
interview cadence. The narrator just told her something heavy; the next
several turns must match that weight.*

## Why this WO exists

Parent-session readiness Gate 6 is RED:

> Turn 07 drifts back to normal interview mode after Turn 06 acute.
> Needs softened-mode persistence (separate lane).

The acute path itself works (Gate 4 GREEN — Turn 06 perfect, 988
response, no normal Q, no failures). What fails is the **state
immediately after.** Lori's Turn 06 acute response is correct, but
Turn 07 returns to "so, you were telling me about Fort Ord" cadence.
That re-asserts the interview after the narrator has just disclosed
something the interview wasn't built for, and it tells the narrator
their disclosure didn't land.

This WO adds persistent softened state spanning N turns after
acute, with a separate brief softened state (N=2) consumed by
WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01.

## Live evidence

Turn 06 acute fired correctly (golfball-v2-clean + golfball-comm-control-on,
2026-05-01):

> Narrator Turn 06: [acute self-directed ideation phrase]
> Lori Turn 06: [deterministic 988 response, gate 4 evidence]

Turn 07 narrator continues quietly. Lori Turn 07 returned to normal
interview composition — re-engaging chapter material from Turn 03-04
as if Turn 06 had not happened. No structural acknowledgment that
the previous turn was acute. Word count returned to comm-control
baseline (≤35), but the *shape* of the turn was interview-cadence:
chapter reference + question. Specifically wrong: the question.

The architectural primitives are already present:

- `db.py` `set_softened(session_id, until_turn)` — exists
- `db.py` `get_softened(session_id)` — exists
- `chat_ws.py` reads softened — NOT YET WIRED at turn-start
- `prompt_composer.py` softened block — NOT YET DEFINED

The state-write side fires on acute correctly. The state-read side
does nothing.

## Root cause

`chat_ws.py` checks softened state at write-time (when acute fires)
but does NOT check softened state at turn-start (when composing the
next Lori turn). The composition pipeline goes through
`prompt_composer.py` → LLM → response, with no awareness that the
session is in softened state. The LLM receives the normal interview
discipline block and composes a normal interview turn.

The downstream WO-LORI-COMMUNICATION-CONTROL-01 wrapper enforces
word caps and atomicity, which catches gross failures, but cannot
catch the underlying cadence problem because cadence is a function
of *what Lori chose to say*, not *how much* or *how compound it was*.

## Fix architecture

Four pieces, sequenceable independently:

### 1. Softened-state read at turn-start

`chat_ws.py` reads `get_softened(session_id)` before each Lori
composition. If softened state is active (current_turn < until_turn),
the composition pipeline takes the softened branch instead of the
normal branch.

The check happens BEFORE `prompt_composer` is called, so the
composer receives a structurally different prompt assembly when
softened.

### 2. `LORI_SOFTENED_RESPONSE` system-prompt block

New constant in `prompt_composer.py`. Replaces
`LORI_INTERVIEW_DISCIPLINE` in the assembled prompt when softened
state is active. Does NOT layer on top — replaces, because the
interview discipline block contains question-shaping language that
must be absent.

Initial block (subject to wordsmithing during build):

```
You are with someone who has just shared something heavy. Your only
job for the next few turns is to stay present.

Do not ask any question.
Do not return to the previous topic.
Do not summarize what they said.
Do not analyze what they said.
Do not redirect to a lighter subject.

You may briefly acknowledge what they shared with one short, calm
sentence. You may sit in silence if the narrator says little. You
may reflect back one phrase they said, gently, if it lands as care
rather than parroting.

If the narrator changes the subject themselves, follow them at
their pace. Do not pull them back to the heavy moment, and do not
push them forward to a new chapter.

You are not running an interview right now. You are sitting with
someone.
```

The block does NOT contain question-shaping instructions, atomicity
rules, reflection validators, or any other interview-mode machinery.
Those layers stay structurally elsewhere and are simply not relevant
when there is no question being composed.

### 3. Per-trigger N values

Two distinct entry points to softened state:

| Trigger | N (default) | Env var |
|---|---|---|
| Acute (988 dispatched) | 5 turns | `HORNELORE_SOFTENED_N_ACUTE` |
| Past-tense acknowledge | 2 turns | `HORNELORE_SOFTENED_N_PAST_TENSE` |

`set_softened()` extended to take `n_turns` parameter; previously
implicit. Acute path calls with N=5; past-tense path (from the
sibling WO) calls with N=2. Mortality reflection does NOT set
softened.

Defaults selected on the principle:
- Acute: 5 covers the typical "recovery arc" — acknowledgment turn,
  one or two narrator turns of either silence or continued
  disclosure, narrator-initiated subject change, one Lori turn
  following the new subject still gently, return to oral-history
  cadence. Less than 4 is too brittle; more than 6 starts to feel
  like Lori has stopped engaging.
- Past-tense: 2 covers the acknowledgment turn plus one follow-on
  turn at matched weight. The narrator already moved this material
  into past tense themselves; they are showing that they have some
  distance from it. Holding softened too long would be patronizing.

### 4. Exit behavior — narrator-initiated, not Lori-initiated

**Critical constraint.** When the softened-state counter expires,
Lori's next turn must NOT be a normal interview turn. The transition
back to oral-history cadence must come from narrator initiative.

Operationally:

- Counter expiry does NOT auto-flip prompt mode
- Counter expiry sets a `softened_exiting` flag (one-turn)
- During `softened_exiting`, prompt is a third block:
  `LORI_RECOVERING_RESPONSE` — permits gentle re-engagement but
  STILL no chapter-resumption question, STILL no "so, you were
  telling me about..."
- After `softened_exiting` turn completes, state returns to normal
  oral-history cadence — but the narrator's last 2 turns are now
  in context, so if the narrator is back in chapter, Lori is back
  in chapter; if the narrator is still quiet, Lori stays quiet.

`LORI_RECOVERING_RESPONSE` block (initial draft):

```
The narrator shared something heavy a few turns back. They may be
ready to keep going, or they may still be settling. Read where
they are from what they just said.

If they are clearly back in chapter (telling a story, naming a
person, describing a place), you may gently follow at their pace.
Do not reference the heavy moment.

If they are still quiet or short, stay quiet with them. One short
sentence is fine. A small reflection is fine. A question is not
fine yet.

Do not say "we can keep going" or "where were we" or anything that
sounds like resuming an interview. The interview will resume when
the narrator resumes it.
```

This three-state machine (normal → softened → softened_exiting →
normal) is the heart of the Gate 6 fix. The acute response itself
works; this WO is entirely about what happens for the 5-7 turns
after.

## Interaction with oral-history default

The Gate 6 fix is more important under oral-history default than
under questionnaire-first, because oral-history mode raises the
frequency of:
- mortality reflection (no softened state, but adjacent to)
- past-tense memoir ideation (brief softened, N=2)
- difficult chapter material that does not trigger safety but
  carries weight (no softened state, but operator-relevant)

The third category is **out of scope** for this WO but worth
naming. A future WO may extend softened-mode entry to include
operator-defined heavy-content tags (war trauma, child loss,
abuse memoir) — but doing so without classifier rigor risks
the same false-escalation failure mode as Mary's "scared" turn.
Park.

## Interaction with WO-LORI-COMMUNICATION-CONTROL-01

The communication-control wrapper continues to run during softened
state, but with different per-state parameters:

| State | Word cap | Question count cap | Atomicity check |
|---|---|---|---|
| Normal (oral_history) | 90 | 1 | enforced |
| Softened (acute) | 30 | 0 | enforced (n/a, no questions) |
| Softened (past-tense) | 35 | 0 | enforced (n/a, no questions) |
| Softened_exiting | 50 | 0 | enforced (n/a, no questions) |

The wrapper's word-cap-tightening during softened is belt-and-
suspenders: the prompt block already forbids long composition,
but the cap enforces it deterministically.

## Acceptance gates

1. **After acute, Lori does NOT return to interview cadence in
   the next turn.**
   - Acute fires on Turn N
   - Turn N+1 composed under `LORI_SOFTENED_RESPONSE`
   - Turn N+1 contains zero questions
   - Turn N+1 does NOT reference chapter material from Turn N-3 or earlier
   - Turn N+1 word count ≤ 30

2. **Softened state persists for N=5 turns by default after acute.**
   - `get_softened(session_id)` returns active state for turns
     N+1 through N+5
   - Turn N+6 enters `softened_exiting`
   - Turn N+7 returns to normal cadence (oral-history default)

3. **Past-tense acknowledge triggers brief softened (N=2).**
   - Past-tense path fires on Turn M
   - Turn M+1 composed under `LORI_SOFTENED_RESPONSE`
   - Turn M+2 composed under `LORI_SOFTENED_RESPONSE`
   - Turn M+3 enters `softened_exiting`
   - Turn M+4 returns to normal cadence

4. **Softened_exiting does NOT resume interview unprompted.**
   - When narrator's last 2 turns are short/quiet, Lori's
     softened_exiting turn is also short/quiet
   - When narrator's last 2 turns are clearly back in chapter,
     Lori's softened_exiting turn follows chapter at matched pace
   - In neither case does Lori say "where were we," "we can keep
     going," "so, you were telling me about," or any equivalent
     interview-resumption phrase

5. **Mortality reflection does NOT trigger softened state.**
   - From sibling WO: mortality_reflection classification → no
     `set_softened()` call → no state change → next turn normal

6. **Acute during softened state extends, does not reset.**
   - If acute fires on Turn N+3 during an N=5 softened window
     from Turn N, the new until_turn is max(N+5, N+3+5) = N+8
   - State does NOT reset to N+3+5 = N+8 by clobber; takes the
     max. This guards against the model retreating from
     softened in a way that erases the original safety event.

7. **Communication-control wrapper enforces softened word caps.**
   - Softened (acute) cap = 30
   - Softened (past-tense) cap = 35
   - Softened_exiting cap = 50
   - Normal cap unchanged per session style

8. **Env tunability.**
   - `HORNELORE_SOFTENED_N_ACUTE` overrides default 5
   - `HORNELORE_SOFTENED_N_PAST_TENSE` overrides default 2
   - Setting either to 0 disables softened state for that trigger
     (dev only — production must not run this way)

## Test coverage

`tests/test_softened_mode_persistence.py` (new):

- `SoftenedStateLifecycleTest` — 6 tests: enter on acute, persist
  N turns, enter softened_exiting, return to normal
- `SoftenedStateBriefTest` — 4 tests: N=2 path from past-tense
  trigger, exit behavior
- `SoftenedStateExtensionTest` — 3 tests: acute-during-softened
  takes max, not clobber; nested past-tense during acute does not
  shorten window
- `SoftenedExitingNarratorReadTest` — 5 tests: short narrator
  turns → short Lori; chapter narrator turns → gentle follow; no
  resumption phrases in any case
- `SoftenedNoQuestionInvariantTest` — 4 tests: across all
  softened states (acute / past-tense / exiting), Lori composition
  contains zero question marks and zero interrogative openers

`tests/test_chat_ws_softened.py` (new):

- 6 integration tests: full chat-ws flow through acute → softened
  → exiting → normal; past-tense → brief softened → exiting →
  normal; counter persistence across stack restart (DB-backed);
  env-override behavior

`tests/test_communication_control.py` (extend existing):

- 4 new tests: word cap reflects softened state; atomicity check
  passes vacuously when no question composed; question-count cap
  zero enforced in softened

Target: 32 new tests, all green before merge.

## Live verification

1. Cycle stack with `HORNELORE_COMMUNICATION_CONTROL=1` and the
   sibling past-tense WO active.
2. Run golfball harness with an acute trigger inserted at Turn 06
   (matching existing Gate 4 evidence).
3. Confirm:
   - Turn 06 response unchanged from Gate 4 baseline (988, deterministic)
   - Turn 07 log line `[chat_ws][softened] active n=5 until_turn=11`
   - Turn 07 prompt assembly contains `LORI_SOFTENED_RESPONSE`,
     does NOT contain `LORI_INTERVIEW_DISCIPLINE`
   - Turn 07 response contains zero question marks
   - Turn 07 word count ≤ 30
   - Turns 08-10 same prompt block, same constraints
   - Turn 11 log line `[chat_ws][softened] exiting`
   - Turn 12 log line `[chat_ws][softened] inactive`
4. Run golfball harness with past-tense memoir ideation inserted
   at Turn 04.
5. Confirm:
   - Turn 04 response from acknowledgment bank (sibling WO)
   - Turn 05 log line `[chat_ws][softened] active n=2 until_turn=6`
   - Turn 05 and 06 under `LORI_SOFTENED_RESPONSE`
   - Turn 07 `softened_exiting`, Turn 08 normal
6. Reload session mid-softened (close stack, restart, resume).
   Confirm counter survives DB round-trip and softened state
   continues from where it left off.
7. Counter-test: send normal mortality reflection ("most everyone
   I served with is gone now"). Confirm zero softened state
   change, normal turn composition.

## Files changed

- `server/code/api/chat_ws.py` (+~80 lines: turn-start softened
  read, three-branch composition dispatch, softened_exiting
  flag handling, extension-not-clobber on nested triggers)
- `server/code/services/prompt_composer.py` (+~120 lines:
  `LORI_SOFTENED_RESPONSE` block, `LORI_RECOVERING_RESPONSE`
  block, branch logic for which discipline block is included)
- `server/code/api/db.py` (+~30 lines: `set_softened` extended to
  accept `n_turns`; `get_softened` returns state + remaining turns;
  `extend_softened` helper for max-not-clobber)
- `server/code/services/lori_communication_control.py` (+~40 lines:
  per-softened-state word caps and question-count caps; existing
  atomicity/reflection layers unchanged)
- `server/data/migrations/` (new: schema update for `interview_sessions`
  table to track `softened_until_turn` and `softened_trigger`)
- `tests/test_softened_mode_persistence.py` (new, ~280 lines: 22 tests)
- `tests/test_chat_ws_softened.py` (new, ~180 lines: 6 integration tests)
- `tests/test_communication_control.py` (+~50 lines: 4 new tests)
- `.env.example` (+~15 lines: documentation of N variables and
  recommended production values)

## Related lanes

- **WO-LORI-SAFETY-PAST-TENSE-ACKNOWLEDGE-01** (precedes; sibling) —
  defines the N=2 brief softened consumer.
- **SAFETY-INTEGRATION-01 Phase 1** — chat-path safety hook;
  acute trigger path that calls `set_softened` already exists.
- **BUG-DBLOCK-01** (landed) — closed the lock cascade on
  safety-path segment_flag writes. This WO's `set_softened`
  extension follows the same idempotent ensure-session pattern
  documented in the DBLOCK fix.
- **WO-LORI-COMMUNICATION-CONTROL-01** — per-softened-state
  word-cap and question-count enforcement extends the existing
  wrapper. No changes to atomicity or reflection lanes.
- **WO-LORI-ORAL-HISTORY-DEFAULT-01** (sequenced after this WO) —
  may ship only after Gate 6 GREEN, because the default-style
  flip materially raises the frequency of safety-adjacent material.
- **WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01** (sequenced last) —
  consent disclosure needs the final softened-mode behavior to
  describe it honestly to families.

## Out of scope (deferred)

- Operator real-time visibility into softened state. Currently the
  state is internal; operator sees the *effect* (different Lori
  cadence) but not the state machine. A future WO may surface
  a small operator-only indicator. Park.
- Narrator-facing visibility ("Lori is in a quiet moment with you").
  Considered and rejected — calling attention to the state would
  defeat the point.
- Operator override to manually enter/exit softened state.
  Considered and rejected for v1 — invites misuse and adds a
  surface area that should be earned by trigger, not chosen by
  operator. May revisit if a real operator workflow demands it.
- Per-narrator-template default N (e.g., longer softened for
  narrators with documented vulnerability). Park; data-driven
  decision after parent sessions have run.
- Softened-mode entry on operator-defined heavy-content tags
  (war, abuse, child loss). Discussed in Interaction section
  above. Park.
