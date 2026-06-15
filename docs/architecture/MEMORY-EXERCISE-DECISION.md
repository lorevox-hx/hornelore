# MEMORY-EXERCISE-DECISION

**Status:** ACTIVE — small architectural decision record
**Date:** 2026-05-24
**Decision owner:** Chris Horne
**Type:** ADR — not a Work Order
**Triggered by:** Renaming of `WO-INTERVIEW-PROCESS-REDESIGN-01` to
runtime architecture framing; question of whether to deprecate
`memory_exercise` mode in light of oral-history default

## Context

**Supersession note:** An earlier conversation considered deprecating
memory_exercise on the grounds that the universal pivot moves
oral_history to the default and the other styles become operator
overrides. The deprecation reasoning was internally consistent under
the locked-narrator framing (no current Horne narrator visibly needs
the style, and absence of evidence was treated as evidence of absence
of need). The universal pivot inverts that reasoning: the narrator
population the system serves going forward explicitly includes people
who will need cognitive-support styles, and "absence of evidence" no
longer applies because the relevant evidence will only emerge from
narrators we have not yet onboarded. This ADR therefore supersedes
the deprecation direction. Memory_exercise stays, gets a proper
implementation, and ships as a real operator-selectable override.

Hornelore documents (README, `WO-UI-SHELL-01`) reference five session
styles: `clear_direct`, `warm_storytelling`, `questionnaire_first`,
`companion`, `memory_exercise`. The README's use-case framing section
explicitly names `memory_exercise` and `companion` as the
"listen-first behavior" tier.

However, the actual landed `WO-LORI-COMMUNICATION-CONTROL-01`
per-style word-cap table contains only four styles:

clear_direct=55 / warm_storytelling=90 / questionnaire_first=70 / companion=80

`memory_exercise` is missing from the live parameter table. This is an
implementation gap — the style is referenced as a design intent and
appears in the picker, but the runtime behavior is not differentiated
from a fall-through default.

The universal pivot (`HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`) moved
oral_history to the default session style. The remaining four styles
(warm_storytelling, companion, memory_exercise, questionnaire_first)
become operator-toggled overrides for specific narrator states.

Open question: deprecate `memory_exercise` (remove from picker, schema,
documentation) or keep it (build the missing parameter row, write the
distinctive prompt block, ship a real cognitive-support style)?

## Decision

**Keep `memory_exercise` as a real available override mode. Ship a
proper implementation.**

The locked-narrator framing made `memory_exercise` feel optional
because the three Horne narrators (Kent, Janice, Chris) do not
currently need it. The universal pivot specifically widens the narrator
population to include narrators who will. Deprecating now means
re-introducing for second-family pilot at higher cost and with less
evidence than building it properly today.

This decision also closes a real implementation gap. The current state
(referenced in five places, behaviorally undifferentiated in four
others) is the worst of both worlds — it makes promises to operators
the runtime does not keep.

## Implementation requirements

`memory_exercise` becomes a real session style with distinctive runtime
behavior. The implementation work is small but explicit:

1. **Add `memory_exercise` row to the per-style parameter table** in
   `lori_communication_control.py`. Suggested initial values:

   | Parameter | memory_exercise |
   |---|---|
   | Word cap | 60 |
   | Question count cap | 1 |
   | Story momentum threshold | 0.5 |
   | Thread bank surfacing | active |
   | Bio anchored asker | active, frequency cap halved (1.5 max per session, rounded down to 1) |
   | Silence ladder (sec) | 150 / 450 / 900 |

   Rationale: shorter word cap than oral_history (cognitive load
   consideration), longer silence ladder than oral_history (gentler
   re-entry), lower momentum threshold for story mode (acts as story
   sooner because narrators with cognitive variability may need their
   shorter narrative bursts protected the same way longer chapters are),
   anchored asker tightened (the asking model already runs sparse; for
   cognitive support it runs sparser still).

2. **Add `LORI_MEMORY_EXERCISE_RESPONSE` prompt block** in
   `prompt_composer.py`. Distinctive composition guidance:

   - Listen first; let small narrative bursts complete
   - Use narrator's own words back to them as anchor when reflecting
   - Avoid timeline pressure (no "what year" / "how old" unless the
     narrator volunteers temporal context)
   - Prefer concrete sensory or relational anchors over abstract ones
     ("the kitchen with your grandmother" not "your childhood home")
   - Tolerate repetition without correction; if the narrator repeats
     a story, reflect freshly rather than acknowledging the repeat
   - Operator notes are preserved for any orientation cues operator
     has set up before session

3. **Add memory_exercise rows to disclosure language** in
   `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01` and picker tooltips
   (`WO-LORI-ORAL-HISTORY-DEFAULT-01`). Suggested family-facing
   description (matches the format the disclosure WO established):

   > **memory_exercise** — Designed for narrators with mild cognitive
   > variability. Lori listens longer, prompts more sparingly, and
   > uses concrete anchors (people, places, sensory details) rather
   > than asking about dates or chronology. The operator can switch
   > to this mode when open-ended conversation feels tiring for the
   > narrator.

4. **Sequence this work as a small WO sequenced AFTER the seven
   already drafted.** Call it
   `WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01`. It is the
   smallest of all WOs in the lineage but it closes a real gap.

## Why this is the right call (not the comfortable one)

The comfortable call is "deprecate memory_exercise; oral_history is
the default and we don't have evidence we need cognitive-support
styles." The discomfort that exposes is real:

- The Horne family today does not visibly need it
- Building it without evidence risks gold-plating
- The implementation cost is small but non-zero

The reason to keep and build anyway: the existing cognitive-support
scaffolding (WO-10C silence ladder, the "no correction" rule, the
listen-first directive in tier-2) was built into the architecture
specifically because the operator (Chris) recognized that the universal
narrator population includes people in cognitive transition. That
recognition is not a Horne-specific concern — it is a permanent
feature of memoir work with older adults.

If `memory_exercise` is deprecated and re-introduced later, the
re-introduction will happen under pressure from a second-family pilot
where a real narrator needs it now. Building it under that pressure is
worse than building it deliberately today.

## Companion mode is distinct and stays

For clarity: `companion` mode is NOT the same as `memory_exercise` and
both have a role.

- `companion` — minimal interview structure for grief, end-of-life
  reflection, quiet narrators. The narrator is emotionally protected;
  Lori is mostly a present listener. Suitable for any narrator in a
  particular emotional state.
- `memory_exercise` — cognitive-load-aware structure for narrators
  with mild cognitive variability. Lori actively scaffolds memory
  with concrete anchors. Suitable for a specific narrator population
  regardless of emotional state.

Both styles can be selected by operator independently. They are not
interchangeable; the operator picks based on what the narrator needs
at this session.

## Acceptance gates

`WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01` (when written) must:

1. Add memory_exercise row to the per-style parameter table; all
   parameters explicitly specified (no fall-through defaults)
2. Add `LORI_MEMORY_EXERCISE_RESPONSE` prompt block to composer
3. Update Phase 9 disclosure language to include memory_exercise
   description
4. Update operator picker tooltip to include memory_exercise
   description
5. Cross-reference test: picker tooltip and disclosure language are
   character-identical
6. Integration test: session created with memory_exercise style
   produces composition with distinctive parameters (word cap 60,
   anchored asker frequency halved, distinct prompt block referenced
   in assembly log)
7. Documentation in runtime architecture doc updated to add
   `memory_exercise_normal` and `memory_exercise_story` to the
   effective mode list and interaction matrix

## Out of scope (explicitly)

- Building automatic detection of narrators who would benefit from
  memory_exercise. Operator picks based on knowledge of narrator.
  Auto-detection contradicts the strategy doc's "no profiling,
  no scoring, no longitudinal labels" principle.
- Building separate cognitive-support tooling beyond the session style.
  WO-10C silence ladder already exists and works in all styles. This
  WO is about the *composition behavior* of one style, not about
  additional scaffolding infrastructure.
- Building a `memory_exercise_intensive` or higher-support variant for
  later-stage cognitive variability. v1 is one cognitive-support style.
  Variants come if and when needed.

## Related artifacts

- `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md` — establishes the universal
  framing that makes building this worthwhile
- `LORI-RUNTIME-ARCHITECTURE.md` — defines the per-style parameter table
  and effective mode list that this WO extends
- `WO-LORI-COMMUNICATION-CONTROL-01` (landed) — the parameter table
  this WO adds a row to
- `WO-LORI-PHASE-9-DISCLOSURE-UPDATE-01` — disclosure language to
  extend with memory_exercise description
- `WO-LORI-ORAL-HISTORY-DEFAULT-01` — picker tooltip surface to extend
- `WO-10C` (Cognitive Support Report, landed) — silence ladder
  infrastructure that this style consumes, runs in all styles, not a
  replacement for memory_exercise composition behavior

## Closing note

Memory exercise is not a marketing feature. It is the recognition that
the narrator population Lorevox will eventually serve includes people
whose memories need a different kind of patience than oral history
alone provides.

Build it.
