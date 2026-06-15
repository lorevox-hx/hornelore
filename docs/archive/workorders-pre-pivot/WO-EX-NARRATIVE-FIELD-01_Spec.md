# WO-EX-NARRATIVE-FIELD-01 — narrative-story field extraction

**Status:** draft · **Opened:** 2026-04-20 · **Owner:** Chris + Claude
**Parent track:** LOOP-01 R5.5 (post-baseline extractor quality)

## Problem

Biographical narrative fields — `parents.notableLifeEvents`,
`grandparents.memorableStories`, `siblings.memories`,
`parents.notes`, `grandparents.notes`, etc. — are **systematically
under-extracted** by the current pipeline even when the narrator
delivers the story cleanly in one beat.

First real signal: canon-grounded eval `cg01` (2026-04-20).

| case | narrator reply | expected path | actual path | score |
|---|---|---|---|---|
| `cg_006` | "My mother was Josephine — called her Josie. She was a gifted musician. During the silent movie era she played the organ at the movie theaters to make money." | `parents.notableLifeEvents` | `parents.occupation` + `parents.notes` (scalar) | 0.50 |
| `cg_007` | "My grandmother was Anna — Anna Schaaf, born Gustin. She was fifty years old when she had my mother Josie, and she was a bit embarrassed about it." | `grandparents.memorableStories` | (dropped — only name/lastName/maidenName emitted) | 0.50 |

Pattern: the extractor catches identity facts (firstName, lastName,
maidenName, occupation) and drops the narrative story entirely, OR
routes story fragments to a scalar `.notes` / `.occupation`.

## Why it matters

The templates treat narrative-story fields as first-class
biographical content — they hold the "what makes this person
memorable to the narrator" data. If the extractor can't populate
them, the biobuilder template can never be filled from conversation
without hand-editing. That breaks the long-form oral-history loop
Lorevox is trying to close.

## Hypothesis

Two interlocking causes:

1. **Few-shot gap.** The `extract.py` few-shot catalog has strong
   coverage on structural family fields (firstName / birthDate /
   occupation) and pets (WO-EX-TWOPASS / R4 Patch C), but little-to-no
   coverage on `.notableLifeEvents` / `.memorableStories` / `.memories`
   as target paths. The LLM sees narrative content and reaches for the
   familiar scalar slots.

2. **Section/target gradient.** Under SECTION-EFFECT Phase 2
   (`current_target_path`), when the target is `parents.firstName`, the
   extractor emits identity facts and ignores the story. When the target
   is `parents.notableLifeEvents`, the narrative may still get lost
   because the current_section pushes toward the identity-shaped schema.

Both are testable.

## Scope

**IN scope:**
- `parents.notableLifeEvents` / `parents.notes`
- `grandparents.memorableStories` / `grandparents.notes`
- `grandparents.memorableStory` (singular — template variant, aliased)
- `siblings.memories` / `siblings.notes`
- `greatGrandparents.notableLifeEvents` / `.notes`
- `spouse.narrative` (Janice's template holds Kent's story here)

**OUT of scope:**
- `laterYears.lifeLessons` / `laterYears.adviceForFutureGenerations`
  (distinct pattern; covered by R4 Patch and a pending separate WO)
- `hobbies.*` narrative fields (different section semantics)

## Implementation phases

### Phase 1 — diagnostic baseline (read-only)
Run `cg01` targeted slice (`cg_006`, `cg_007`, plus any master cases
hitting these paths) with verbose `[extract]` logging. Record:
- which target_path is synthesized for each
- what the LLM actually emits (raw)
- which items are dropped by guards vs silently skipped by the prompt
- whether the narrative content appears anywhere in `llm_raw`

Exit criteria: attribution is clear — few-shot gap vs target-gradient
vs guard-drop. Report at `docs/reports/WO-EX-NARRATIVE-FIELD-01_DIAG.md`.

### Phase 2 — few-shot additions (conditional on Phase 1)
If Phase 1 fingers few-shot gap, add narrative-target few-shots for
each in-scope path. Structure mirroring R4 Patch C / Patch G:
- 1 narrative-only few-shot per path (gold emission points ONLY to
  the narrative field, never to a scalar fallback)
- 1 mixed few-shot per path (identity fact + narrative in same reply,
  emissions split across the two paths correctly)

Estimated footprint: 10-12 new few-shots across 4 paths. Flag
behind `HORNELORE_NARRATIVE=1` initially so we can A/B.

### Phase 3 — scorer alias relax (conditional on Phase 1)
If Phase 1 shows the extractor IS emitting narrative content but to
`.notes` / `.occupation` scalars (as in `cg_006`), the cleaner fix is
scorer-side: accept `.notes` as `alt_defensible_paths` for
`.notableLifeEvents` on a narrator template where the narrative field
is empty. Avoids prompt churn.

### Phase 4 — eval + decision gate
Re-run master eval (`r5b`) + `cg02` + targeted cases. Decision:
- ≥ +3 stubborn flips or ≥ +2 cg-case gains → adopt, flag default-on
- < +2 gains → diagnose further or reject

## Relationship to existing work

- **Builds on SECTION-EFFECT Phase 2** — uses the era/pass/mode
  payload to attribute Phase 1 gaps cleanly.
- **Complements SPANTAG-01** — SPANTAG is reverse-direction (better
  evidence binding); this WO is forward-direction (more routes into
  narrative slots).
- **Could pair with PROMPTSHRINK** — smaller topic-scoped few-shot
  packs mean narrative few-shots would get more of the prompt
  real-estate when the section demands them.

## Out of scope — but flagged

- Template bug where narrator fields mis-routed from canonical
  template truth (e.g. Kent's `occupation = "Construction and trades"`
  in pre-2026-04-20 templates). Handled in the canon-rebuild track.
- Retiring `parents.notes` as a narrative catch-all — schema cleanup,
  orthogonal to this WO.

## Success metric

`cg_006` and `cg_007` both green in `cg02` or later — either by
narrative-path hit or by scorer alias credit. Zero regression on
`r4i` master topline.
