# WO-13 Phase 9 — Session Orientation + Banner System (FINAL, EXECUTION VERSION)

Author: Chris + Claude (iterated)
Status: Final — save for later execution. Do NOT start Phase 9 until
Phase 8 rollout (B → A → C) is stable on Kent.

---

## 0. Purpose

Phase 9 adds clarity and operator visibility to Hornelore after Phase 8.

It solves:

- cold-start confusion
- mixed-state ambiguity (legacy vs promoted truth)
- unclear narrator posture for Lori

## 1. Core Principle (Governing Rule)

```text
Truth is enforced in code.
Clarity is expressed in UI and session context.
```

## 2. Scope Boundary (CRITICAL — DO NOT VIOLATE)

Phase 9 MUST NOT:

- write to `family_truth_notes`
- write to `family_truth_rows`
- write to `family_truth_promoted`
- modify `profile_json`
- alter extraction behavior
- alter promotion logic

Phase 9 ONLY affects:

- session prompt composition
- UI banner system
- operator clarity

## 3. Session Orientation Layer

New Concept

```text
session_narrative_preload
```

Lives in:

- session payload (in memory)
- prompt composer
- optional UI onboarding

DOES NOT live in:

- any database table
- profile
- archive
- review system

## 4. Session Preload Content

**LIVE Narrators**

```text
This narrator is sharing their life story from birth to the present.

Respond as a warm, attentive interviewer.
Help them tell their story clearly and naturally.
```

**REFERENCE Narrators**

```text
This is a reference narrator.

Treat their profile as curated and read-only.
Do not infer or generate new truth from session interaction.
```

**Strict Rules**

DO NOT include:

- truth precedence instructions
- "use approved truth first"
- "do not invent facts"
- extraction guidance

All enforcement remains in backend logic.

## 5. Prompt Composition (FINAL STRUCTURE)

```text
[system instructions]
[session_narrative_preload]
[session_payload.profile]
[ephemeral_context]          ← NEW
[filtered rolling summary]
[user input]
```

**Ephemeral Context**

Contains:

- `now_iso` (system timestamp)
- `narrator_age_years` (if valid)

**Ephemeral Rules**

```text
Age is computed ONLY if:
    DOB exists AND source = promoted_truth

Age is NEVER extracted from conversation
Age is NEVER stored in DB
```

## 6. Banner System (STATE MACHINE)

**Reference Narrator Branch (FIRST)**

```text
Reference narrator — curated and read-only.
No review queue.
```

This bypasses all other states.

**Live Narrator States**

**State 0 — No Backfill**

```text
This narrator has not been prepared for Memory Truth.

Run backfill to stage existing profile data for review.
```

**State 1 — Backfill, No Review**

```text
Memory Truth setup in progress.

N items are waiting for review.
Profile currently shows legacy data.
```

**State 2 — Partial Review**

```text
Memory Truth in progress.

N items approved, M still pending review.
Profile mixes reviewed and legacy data.
```

**State 3 — Fully Reviewed**

```text
Memory Truth complete.

All profile fields are based on reviewed truth.
```

## 7. Banner Behavior (STRICT)

**Persistence**

```text
States 0, 1, 2 → persistent, NOT dismissible
State 3 → auto-collapse or disappear
```

**Placement**

- top of UI
- always visible (unless state 3)

**Allowed Actions**

- "Open Review Queue" (link only)

**Backfill Action**

NOT included in Phase 9 UI (backfill remains operator/CLI action).

## 8. State Calculation

Derived from:

- `family_truth_rows` counts
- presence of promoted rows
- narrator type

**Failure Mode**

If state cannot be determined:

```text
No banner rendered
Profile remains visible
```

Never block UI.

**Logging Requirement**

On state calculation failure, emit a warning log with narrator context.

Example requirement:

```text
logger.warning("memory_truth_state_failed", person_id=pid, error=str(e))
```

This failure must be visible in logs and grep-able in production.

## 9. Profile Source Transparency

**Internal Field**

```text
source =
    legacy
    promoted_truth
    legacy_fallback
```

**UI Exposure**

*Dev Mode Only*

- show raw `source`

*End User*

- show:
  - "Reviewed"
  - "Pending review"
  - "From existing records"

## 10. Session Lifecycle

**On Narrator Load**

- determine narrator_type
- generate preload
- attach to session

**On Each Turn**

- reuse preload
- recompute ephemeral context
- DO NOT regenerate preload

## 11. UI Components

Add

- banner component (state-driven)
- review queue shortcut

DO NOT add

- system jargon in user UI
- raw pipeline terms

## 12. Testing Requirements (MANDATORY)

**Session Preload**

- present in prompt
- correct per narrator type
- not persisted anywhere

**Banner**

Test all states:

- correct message
- correct transitions
- reference narrator branch works

**CRITICAL TEST — Age Extraction Block**

Input:

```text
"I am 82 years old"
```

Assert:

- no rows created in `family_truth_rows`
- no appearance in rolling summary
- no appearance in profile

**Integration**

- no effect on extraction
- no effect on promotion
- no DB writes

## 13. Implementation Order

1. add preload generator
2. wire prompt composer
3. add ephemeral context
4. build banner state engine
5. implement UI banner
6. test all states
7. run regression

## 14. Rollout Plan

1. deploy Phase 9
2. verify on Kent (post Phase 8)
3. verify fresh narrator:
   - state 0 → 1 → 2 → 3
4. verify reference narrator behavior

## 15. Deliverables

Claude must return:

- preload implementation
- prompt composer update
- banner state logic
- UI component
- test results (all states)
- age-extraction test proof
- confirmation: no DB writes
- confirmation that Phase 4/5/6/7/8 full regression remains green

Regression evidence must explicitly include the full earlier suite total
(159 / 159 or higher, depending on any later additions).

## 16. Final Statement

Phase 8 made truth correct.
Phase 9 makes truth understandable and safe to operate.

Without Phase 9:

- system is correct but confusing

With Phase 9:

- narrator posture is clear
- mixed-state is visible
- operator understands system state

**This is the final Phase 9 execution plan.**
