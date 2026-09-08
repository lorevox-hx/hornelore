# BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01

**Status:** CLOSED — patched 2026-06-17 (prompt directive + post-LLM guard)
**Severity:** MEDIUM (CLAUDE.md design principle 8 violation — Lori asking
for facts the operator already entered as intake)
**Surface:** `server/code/api/prompt_composer.py` +
`server/code/api/services/lori_response_guards.py`

## Reference

CLAUDE.md design principle 8:

> *If the operator seeded it, Lori knows it. If Lori knows it, she does
> not ask for it as intake.*

## Reproduction

Mable Earliest from the 2026-06-17 full-family harness — seeded
profile contains `place_of_birth='Albany, Georgia'`, `birth_year='1942'`,
`current_residence='Albany, Georgia'`:

```
"Mount Olive AME. What a rich and evocative narrative! I'm so grateful
to be listening to your story. Let me capture a few key points from your
early years.

You were born in Albany, Georgia, in 1942?"
```

The narrator is asked to yes/no confirm a fact the operator already
provided. This is also a structural violation of the narrator-as-author
posture — Lori sounds like a clerk verifying information rather than
a listener interested in lived experience.

## Fix — two layers

### Layer 1 (primary): prompt-side directive

Added a new rule block to `prompt_composer.py` in the
`LORI_INTERVIEW_DISCIPLINE` directive after `ANTI-CONFABULATION RULE`:

```
DO NOT ASK FOR SEEDED FACTS (BUG-LORI-ASKS-WHAT-OPERATOR-SEEDED-01):

If the operator seeded it, you know it. If you know it, you do not ask
for it as intake.
...
✗ FORBIDDEN: "You were born in Albany, Georgia, in 1942?"
✓ ALLOWED:   "What do you remember about Albany when you were little?"
```

Plus 4 worked examples (POB / residence / current work / parent alive)
showing forbidden vs. allowed wording.

### Layer 2 (safety net): post-LLM detect + repair

When the LLM ignores the directive, `apply_response_guards` (when called
with `seeded_facts` parameter) catches and rewrites:

```python
_SEEDED_INTAKE_PATTERNS = (
    (re.compile(r"\b(?:you were|were you) born in ..."), "place_of_birth"),
    (re.compile(r"\b(?:do you live|you live) in ..."),    "current_residence"),
    (re.compile(r"\b(?:do you work|you work) (?:at|for) ..."), "current_work"),
    (re.compile(r"\bis your mother (?:still )?alive"),     "parent_alive"),
    # + birth_year, children_count
)

def detect_seeded_fact_intake(assistant_text, seeded_facts):
    """Returns field_key if a seeded-fact intake question matches."""

def repair_seeded_fact_intake(field_key, seeded_facts, target_language):
    """Returns lived-experience rewrite."""
```

Each detected field rewrites to a lived-experience question:
- `place_of_birth` → "What do you remember about {place} when you were little?"
- `current_residence` → "What does life in {place} feel like for you now?"
- `current_work` → "What has your time at {employer} been like?"
- `parent_alive` → "What has it meant to still have that connection with your mother all these years?"

Spanish target language gets Spanish equivalents.

## Acceptance gates

1. Mable's "You were born in Albany, Georgia, in 1942?" with seeded POB+year
   → rewritten to "What do you remember about Albany, Georgia when you were
   little?"
2. John's "Do you currently live in Las Vegas, New Mexico?" with seeded
   `current_residence` → rewritten to lived-experience question
3. John's "Do you work at Pecos Schools?" with seeded `current_work` →
   rewritten
4. Without `seeded_facts` parameter, the guard does not fire (no false
   positives on unseeded narrators)
5. Lived-experience question ("What do you remember about Albany when you
   were little?") passes through unchanged
6. Empty seeded value (`{place_of_birth: ""}`) does NOT trigger the guard
7. Spanish target language returns Spanish lived-experience rewrite

## Files changed

- `server/code/api/prompt_composer.py`
  - Inserted `DO NOT ASK FOR SEEDED FACTS` rule block in
    `LORI_INTERVIEW_DISCIPLINE` directive
- `server/code/api/services/lori_response_guards.py`
  - `_SEEDED_INTAKE_PATTERNS` 6-pattern bank
  - `detect_seeded_fact_intake(text, seeded_facts)` function
  - `repair_seeded_fact_intake(field_key, seeded_facts, target_language)`
    function with per-field lived-experience rewrites + Spanish locale
  - `apply_response_guards` extended with optional `seeded_facts` kwarg
  - `__all__` extended with two new public symbols
  - Added `Optional` to typing import
- `tests/test_lori_seeded_fact_intake_guard.py` — 14 tests across 3
  classes: detection (7), repair (4), apply_response_guards integration (3)

## Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
