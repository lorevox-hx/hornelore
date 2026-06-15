# BUG-LORI-ERA-CONFABULATION-01

**Status:** LANDED 2026-05-09 (directive-only)
**Severity:** HIGH (parent-presentable surface — narrator notices
fabricated facts immediately)

## Live evidence

Mary's session 2026-05-09 (`transcript_switch_moyc6 (2).txt`):

**Line 62 (Early School Years era walk):**
> "During your Early School Years, you mentioned you had kids and
> moved around a bit for your husband's work. What do you remember
> about your daily routine during those times when you were moving
> from place to place?"

Mary is 86 (DOB 1940). Her Early School Years are ages 6-12 (1946-
1952). Lori claimed Mary "mentioned" she had kids and a husband's
work-driven moves — during a span of her life when she was a child.
Mary never said any of this. Profile_seed for the Early School
Years bucket was null at the time.

**Line 119 (date question):**
> Mary: What day is today?
>
> Lori: According to my knowledge, today's date is Saturday, May 9,
> 2026. You were also wondering earlier about the current date,
> weren't you?

Mary never asked about the date earlier. Lori invented a memory.

## Root cause

The composer's standard interview directives include `EXPLICIT
REFLECTION DISCIPLINE` Rule 4 (NO INVENTED CONTEXT) and `CONTROL-
YIELD RULE` (echo only what narrator just said). But neither rule
addresses the era-walk and SYSTEM-directive paths specifically:

1. **Era-walk question generation** — when the FE injects
   `[SYSTEM: The narrator just selected 'Early School Years'... Ask
   ONE warm, open question...]`, the LLM has no narrator-turn-
   anchor to reflect, so it pattern-completes from imagined
   narrative context. With profile_seed mostly null and no
   provisional truth, it invents.

2. **Self-referential memory claims** — "you mentioned earlier" /
   "as you've shared" / "based on what you've told me" — these
   shapes are not specifically forbidden, only obliquely covered
   by the broader "no inferences" rule.

## Fix architecture

New `ANTI-CONFABULATION RULE` block in `prompt_composer.py`,
inserted after `EXPLICIT REFLECTION DISCIPLINE` and before the
`NO-FORK RULE`. The block:

1. **Lists forbidden phrases when unsupported:**
   - "you mentioned X"
   - "you said X"
   - "you told me X"
   - "you were also wondering about X"
   - "as you mentioned earlier"
   - "based on what you've shared"
   - "from our conversation, X"

2. **Defines "supported":**
   - profile_seed.<bucket> not null
   - promoted_truth or projection_family contains it
   - literal narrator sentence in this conversation

3. **Era-walk-specific rule:**
   - Anchor era-walk questions only in (a)/(b)/(c) above
   - When none apply: ask a CLEAN era question with no false
     attribution (e.g. age range only)

4. **Both Mary line 62 and Mary line 119 appear as
   ✗ BAD examples** with ✓ GOOD alternatives showing the same
   intent without confabulation.

## Acceptance gates

Directive-only fix; verification is observational (no unit tests
on prompt strings beyond the syntax check):

1. **Stack restart loads the new directive.**
   - `prompt_composer.py` AST parses green ✓
   - Composed system prompt contains "ANTI-CONFABULATION RULE"
     header.

2. **Mary line 62 regression check (live).**
   - With profile_seed.early_school_years null AND no narrator turn
     mentioning marriage/husband/kids in that era, click "Early
     School Years" on Life Map.
   - Lori's response MUST NOT contain "you mentioned" / "you said"
     / "you told me" prefacing invented details.
   - Acceptable shape: "During your Early School Years, when you
     were six to twelve, what do you remember about where you were
     living?" (or similar — anchored only in the age range).

3. **Mary line 119 regression check (live).**
   - Ask "What day is today?" on a fresh session.
   - Lori's response MUST be just the date, no "you were also
     wondering earlier" or similar invented memory.

4. **Composability with existing rules.**
   - Existing tests in `tests/test_prompt_composer*.py` still pass
     (no behavioral change to non-era turns).

## Live verification

1. Cycle stack.
2. Create a fresh narrator with name + DOB only (no profile_seed
   buckets populated).
3. Click "Early School Years" on Life Map.
4. Observe Lori's response. Confirm absence of:
   - "you mentioned"
   - "you said"
   - "you told me"
   - any specific detail not in the seed (kids, husband, moves,
     career, etc.)
5. Repeat for "Adolescence" / "Coming of Age" / "Building Years" /
   "Later Years".
6. Ask "What day is today?" and confirm clean date answer with no
   invented memory of earlier asking.

## Why directive-only (not runtime guard)

Confabulation detection is hard to do post-LLM. A regex check on
"you mentioned" / "you said" would (a) false-positive on
legitimate echo of THIS-turn narrator content ("you mentioned
your father" right after Mary said "my father") and (b) require
projection-state lookup at validation time.

The directive places the burden on the LLM to not generate the
phrase at all — same architectural posture as `EXPLICIT REFLECTION
DISCIPLINE` Rule 4 (NO INVENTED CONTEXT), which has worked for
the reflection class.

If live verification shows the directive isn't enough, follow-up
is a runtime validator that flags `you_mentioned_unsupported`
when:
- Lori's response contains "you mentioned X" OR "you said X" OR
  "you told me X"
- AND no profile_seed bucket OR projection_family field contains X
- AND no narrator turn in current conversation contains X

That's a Phase 2 lane, not v1.

## Related lanes

- **EXPLICIT REFLECTION DISCIPLINE** (BUG-LORI-REFLECTION-01,
  2026-05-02) — Rule 4 (NO INVENTED CONTEXT) covered the
  reflection class. This WO extends to era-walk + self-
  referential-memory class.
- **WO-PROVISIONAL-TRUTH-01 Phase A** (2026-05-04) — profile_seed
  bridge runs for ALL turn modes. Without that, this fix would
  starve era-walk turns of legitimate seeded content. They compose:
  Phase A makes seeded values reach Lori; this WO prevents her from
  inventing what isn't there.
- **CLAUDE.md design principle 7** — *"Mechanical truth must
  visibly project"*. The inverse: Lori must NOT assert facts that
  haven't been mechanically provided.

## Files changed

- `server/code/api/prompt_composer.py` (+~50 lines: new
  ANTI-CONFABULATION RULE block with Mary's two examples inline)
