> ⚠️ **ALREADY APPLIED — HISTORY ONLY, NOT AN INSTRUCTION.**
> The edits described in this file have ALREADY been applied to the
> final versions of HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md,
> MEMORY-EXERCISE-DECISION.md, and WO-LORI-BIO-BUILDER-UNIVERSAL-01_Spec.md
> in this bundle. Do NOT re-apply these edits — doing so would
> double-apply them. This file is retained only as a changelog of what
> changed and why.

# Pre-Build Additions — Anchored Asking Creep Defense + Strategy Audit Row + Principle Statement

**Status:** Three small additions to existing docs before build begins
**Date:** 2026-05-24
**Type:** Doc edits + WO addendum
**Triggered by:** Pre-build review identifying anchored asking creep as
highest regression risk; explicit decision deferred on Tier 3 retention
vs deletion; principle statement needed at top of strategy doc

This file contains three additions to apply before any Bio Builder
build work begins:

1. **Addendum to `WO-LORI-BIO-BUILDER-UNIVERSAL-01`** — new section
   "Anchored Asking Creep Defense" with chapter-health telemetry,
   chapter-health-sensitive budget, friction on cap-raising
2. **Audit row to `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`** — new R-class
   entry on Tier 3 authorization
3. **Principle statement** to add to top of strategy doc
4. **Lineage note** acknowledging memory_exercise decision supersedes
   earlier deprecation direction

Each is presented as the exact text to paste into the existing document.

---

## 1. Addendum to `WO-LORI-BIO-BUILDER-UNIVERSAL-01`

Paste this section into the existing Bio Builder WO. Suggested location:
between the current "Tier 4 — operator direct-entry" section and the
"Bio gap map" section. The addendum stands on its own as a first-class
architectural concern, not a sub-bullet of any tier.

```markdown
## Anchored Asking Creep Defense

Tier 3 is the only piece of this architecture where Lori's mouth is
used as an operator instrument. Every other tier (chapter extraction,
document derivation, operator direct-entry) fills bio without
interrupting the narrator. Tier 3 interrupts.

The architecture has natural pressure pushing every other gate toward
discipline. Anchored asking has natural pressure in the wrong
direction: operator visibility into bio gaps creates instinct to
close them; visible filling moments get disproportionate credit over
invisible chapter extraction; memoir-writing gap reveals create
retroactive pressure to have asked; sparse-narrator sessions tempt
compensatory asking; per-narrator tuning aggregates into systemic
drift.

The per-session frequency caps (max 3 per session, 4+ turns between
asks) prevent in-session bloat but do not prevent inter-session
drift of the caps themselves. This section adds defenses that operate
against drift, not just against per-session count.

### Defense 1 — Chapter continuation telemetry

Every anchored ask writes a `chapter_continuation_metric` to the
`bio_facts` row alongside the existing source data:

```
chapter_continuation_metric: {
  narrator_turn_length_before_ask: int,    -- avg of last 3 turns
  narrator_turn_length_after_ask: int,     -- the turn immediately after
  narrator_turn_length_baseline: int,      -- session avg at similar momentum
  continuation_delta: float,               -- (after - baseline) / baseline
  ask_caused_chapter_end: bool,            -- true if next 2 turns < 20 words each
}
```

`continuation_delta` is the load-bearing measurement. Negative values
mean anchored asks systematically shorten subsequent narrator turns
— the creep mechanism showing up in data. Operator dashboard surfaces
this as a per-narrator rolling average across all anchored asks ever
made.

If `continuation_delta` average drops below -0.25 for any narrator
over a rolling 5-ask window, the bio gap map shows an amber warning
banner: "Anchored asks are systematically shortening this narrator's
chapters. Consider reducing asking frequency or relying more on
chapter extraction." This is information for the operator; the system
does not auto-throttle, but it makes the data visible.

If `ask_caused_chapter_end` is true for more than 40% of anchored
asks across any narrator's session history, the architectural posture
is failing for that narrator and the warning escalates to red.

### Defense 2 — Budget tied to chapter health, not just turn count

The current cap is "3 per session AND 4+ turns between asks." This
counts events. It does not detect chapter exhaustion.

Extended cap (replaces current cap):

> An anchored ask is permitted only when ALL of the following are true:
> - Fewer than 3 anchored asks have fired in this session
> - 4+ narrator turns have elapsed since the last anchored ask
> - Momentum is < 0.4 (existing)
> - Chapter context matches `asking_anchors` pattern (existing)
> - Field is `narrative_value='high'` (existing)
> - **NEW:** Narrator's last 5 turn average length is at least 80% of
>   the session's first-5-turn average length

The last clause means: if the narrator's chapters are getting
shorter, anchored asks are off-budget regardless of count. The system
recognizes chapter exhaustion as the dispositive condition, not
elapsed time.

This change protects against the failure mode where a narrator's
first session is rich, gets 3 anchored asks early, gets exhausted by
those asks, and ends in short factual turns — at which point the cap
"resets" for the next session and the cycle repeats. With the new
clause, anchored asks self-throttle when the narrator stops
producing chapters at sustainable length, regardless of which
session they're in.

### Defense 3 — Hard friction on raising caps

The current architecture allows tuning of anchored asking caps via
`.env`:
- `HORNELORE_BIO_ANCHORED_MAX_PER_SESSION` (default 3)
- `HORNELORE_BIO_ANCHORED_TURN_SPACING` (default 4)
- `HORNELORE_BIO_ANCHORED_MOMENTUM_CEILING` (default 0.4)
- `HORNELORE_BIO_ANCHORED_CHAPTER_HEALTH_FLOOR` (default 0.8, new from
  Defense 2)

Raising any of these caps requires:

1. A separate config file `bio_anchored_overrides.toml` (not just
   an `.env` edit), with explicit per-cap entries
2. A required acknowledgment field in the file:
   `i_understand_this_changes_lori_from_oral_history_to_questionnaire_mode = true`
3. Log line on every session start when overrides are active:
   `[bio_anchored] OVERRIDES ACTIVE — session is operating outside
   default oral-history posture: <list of changed caps and values>`
4. Operator dashboard banner persistent until overrides removed:
   amber-bordered, dismissable per session only, never globally
5. Operator runbook section documenting that overrides are a
   non-default state requiring explicit justification per narrator
6. Parent-session readiness gate failure if overrides active during
   any gate verification run — overridden caps cannot pass the
   readiness framework

This is deliberate friction. Raising caps must require crossing a
visible line, not adjusting a single env value. The friction is the
defense; the friction is what makes "we're an oral-history system"
a maintained promise rather than an aspirational one.

### Acceptance gates for Anchored Asking Creep Defense

In addition to the existing acceptance gates for Tier 3:

13. **Chapter continuation telemetry is written on every anchored ask.**
    - `bio_facts` row for every anchored ask contains
      `chapter_continuation_metric` JSON
    - All 5 fields present and computed correctly
    - Operator dashboard surfaces rolling average per narrator

14. **Chapter exhaustion blocks anchored asks regardless of count.**
    - Synthetic test: narrator with declining turn-length pattern
    - Confirm anchored ask declined when last-5-avg < 80% of first-5-avg
    - Confirm log line `[bio_anchored] skipped — chapter health floor
      violated, last_5_avg=22 first_5_avg=68 ratio=0.32 floor=0.8`

15. **Cap overrides require explicit acknowledgment file.**
    - `.env` cap changes alone do NOT take effect (read but ignored
      unless overrides file present)
    - `bio_anchored_overrides.toml` without acknowledgment field
      causes startup error
    - Acknowledgment field with `false` value causes startup error
    - All four conditions met → overrides take effect with all logging
      and dashboard banner active

16. **Readiness gates fail when overrides active.**
    - Run parent-session readiness verification with overrides active
    - Confirm gate verification fails with explicit message
      `Bio anchored override active — system not in default posture;
      readiness gate verification requires default caps`

17. **Telemetry warning thresholds fire correctly.**
    - Synthetic test data with -0.30 average continuation_delta
      → amber warning visible on bio gap map
    - Synthetic test with 50% ask_caused_chapter_end rate
      → red escalation visible
    - Warnings persist across stack restart (computed from
      historical bio_facts rows)
```

### Files to update (in addition to existing Bio Builder file list)

- `server/code/services/bio_anchored_asker.py` (+~80 lines: chapter
  continuation metric computation, chapter health floor check,
  override file loader with acknowledgment validation)
- `server/code/services/bio_gap_map.py` (+~60 lines: chapter
  continuation rolling average per narrator, warning banner thresholds)
- `server/code/api/parent_session_readiness.py` (+~30 lines: override
  detection in readiness gate verification)
- `tests/test_bio_anchored_creep_defense.py` (new, ~250 lines: 5 new
  acceptance tests)
- `.env.example` — update to note that cap variables are read but require
  overrides file to take effect
- `docs/operator_runbook.md` — new section "Anchored Asking Override
  Procedure" documenting the friction and when (if ever) it is
  justified

```

---

## 2. Audit row to add to `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`

Paste this row into the existing Universal Audit Findings table.
Suggested location: alongside other R-class entries (currently the
operator visibility, family-facing surfaces, and tenant-isolation rows).

```markdown
| Tier 3 anchored asking authorization to interrupt narrator for operator purposes | **R** | The only piece of Bio Builder that uses Lori's mouth for operator goals. Carries the architecture's highest regression risk (drift back to questionnaire). Pre-rebrand decision required: keep with creep defenses (`WO-LORI-BIO-BUILDER-UNIVERSAL-01` Anchored Asking Creep Defense section) or delete entirely (slower bio fill, but creep becomes architecturally impossible). The defended position is workable; the undefended middle is not. |
```

This audit row makes Tier 3 retention a deliberate pre-rebrand decision
rather than an assumed inheritance from the Hornelore-locked design.

Add this paragraph below the audit table, in the "Items needing
decisions before rebrand" numbered list, as a new item 7:

```markdown
7. **Tier 3 anchored asking — keep or delete.** Tier 3 is the only
   mechanism by which Lori asks bio questions for the operator's
   purposes. The creep risk is real and the defenses in
   `WO-LORI-BIO-BUILDER-UNIVERSAL-01` address it operationally but
   not philosophically. Before rebrand, write the explicit defense
   ("Tier 3 exists because chapter-anchored asking is qualitatively
   different from questionnaire asking, and the difference is worth
   the regression risk; here is what makes it worth it; here are the
   conditions under which we would delete it"), or delete Tier 3
   and rely on chapter extraction + documents + operator entry. The
   undefended middle is what allows the architecture to drift back
   to questionnaire behavior under operational pressure.
```

---

## 3. Principle statement for top of `HORNELORE-UNIVERSAL-PIVOT-STRATEGY.md`

Add this section to the strategy doc. Suggested location: directly
after the TL;DR section, before Context. It is short, declarative,
and operator-voiced. It is the principle that the Bio Builder
architecture (and every other piece of the system that touches the
narrator-vs-bio tension) descends from.

```markdown
## The principle

The bio's purpose is to support the memoir, not to be the memoir.

A birth date without context matters less than a moment of context
without a birth date.

Optimize for high-context completeness, not absolute completeness.

If anchored asking ever produces more data and less story, the
architecture has failed.

This principle governs every decision about when Lori may interrupt
the narrator for the operator's purposes. It applies to Tier 3
anchored asking specifically and to any future mechanism that uses
Lori's mouth on behalf of the operator. When in doubt, the chapter
wins and the bio gap remains a gap.
```

---

## 4. Lineage note acknowledging memory_exercise decision supersedes
earlier direction

This is a small clarification to add to the
`MEMORY-EXERCISE-DECISION.md` ADR. In the existing "Context" section,
prepend the following paragraph so the supersession is explicit and
documented:

```markdown
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
```

This note keeps the decision lineage transparent for future readers
who may encounter the earlier conversation in chat archives or
git history.

Add a corresponding lineage row to the Universal Audit Findings
table in the strategy doc:

```markdown
| memory_exercise as deprecated vs implemented | **RESOLVED 2026-05-24** | Initial direction (deprecate) reversed by `MEMORY-EXERCISE-DECISION.md`. Style is preserved and gets proper implementation via `WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01`. |
```

This is the first **RESOLVED** entry in the audit table. The
existence of resolved entries (rather than items vanishing) is
itself a design choice — it keeps the decision history visible
so future contributors understand which choices were considered
and consciously made vs. which inherited by default.

---

## Application order

These four additions are independent and can be applied in any
order. Suggested order for minimum review burden:

1. Principle statement to strategy doc (smallest, sets context for
   everything else)
2. Lineage note to memory_exercise ADR (one paragraph, one table row)
3. Audit row + item 7 to strategy doc (resolves the open Tier 3 question
   as an explicit pre-rebrand decision)
4. Bio Builder addendum (largest; new section + acceptance gates +
   files-changed updates)

After all four are applied, the pre-build documentation set is
complete and the trio + Phase 1 + oral-history default + Bio Builder
sequence can begin building with confidence that the architecture's
single biggest regression risk has been explicitly defended.

---

## What this is not

These additions do not change any architectural decision. They make
existing decisions explicit and add operational defenses to the one
mechanism (Tier 3) that has natural pressure to drift.

They also do not require any new WO. The Bio Builder addendum extends
the existing Bio Builder WO; the strategy doc edits are routine
additions to a living document; the memory_exercise lineage note is
documentation hygiene.

The next net-new artifact remains `WO-LORI-MEMORY-EXERCISE-IMPLEMENTATION-01`,
which can wait until after the trio + Phase 1 land.

## Closing

The architecture is converging. These additions close the last gaps
that would have made the convergence brittle under operational
pressure. The principle statement at the top of the strategy doc
is the load-bearing thing: it gives the entire system a single
phrase that operators can use to settle ambiguous calls. Everything
else is defense in depth around that principle.

Ship the trio + Phase 1.
