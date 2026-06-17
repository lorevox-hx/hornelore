# BUG-LORI-ANCHOR-CASCADE-DUMP-01

**Status:** CLOSED — patched 2026-06-17
**Severity:** HIGH (mechanical template stamp-out across narrators —
exposed Lori's deterministic anchor extractor as a list dump rather
than active listening)
**Surface:** `server/code/api/services/lori_witness_mode.py` +
`server/code/api/services/lori_followup_bank.py`

## Reproduction

The 2026-06-17 full-family harness produced 5 instances of the
"You went from X to Y, then Z, A, B, and C. What happened next?"
template across 5 different narrators:

```
Walter Era 2: "You went from Saint Augustine to Brendan, then Eileen, Patrick,
              Catholic, South Boston, Mass, and Walter. What happened next?"
Walter Era 4: "You went from Boston College to Brendan, then Chestnut Hill,
              Kennedy, Irish, Catholic, Schlitz, and Eileen. What happened next?"
Joe Earliest:  "You went from Cochiti Pueblo to August, then Frank, Elena,
              Andrew, Mary, Catholic, and Mass. What happened next?"
Pat Later:     "You went from Wednesday to Betty, then Madeleine, Engle,
              Wrinkle, Time, Tuesday, and October."
Mable Later:   "You went from Charlene to Atlanta, then Bernard, Detroit,
              Plymouth Road, Albany, Earnest, and Lillian."
```

Plus 3 instances of the "You said X / You kept coming back to X" stock-phrase:

```
Walter Era 3: "You said Boston Latin: I went to Boston Latin School.
               You kept coming back to Boston Latin — what was that actually like for you?"
Walter Era 5: "You said North Quincy: Lynn for ten years... You kept coming back
               to North Quincy — what was that actually like for you?"
Frank Building:"You said Tule Lake: He died in 1973... You kept coming back to
               Tule Lake — what was that actually like for you?"
```

Notice the cascade includes calendar tokens ("Wednesday", "Tuesday",
"October", "August"), religious-residue ("Catholic", "Mass"), and bare
joining-word residue ("then"). These should never be presented to the
narrator as anchors.

## Root cause

### Cascade dump (`lori_witness_mode._format_multi_anchor_list`)

The function joined anchor lists using Oxford-style "A, B, ..., and Z"
with NO upper bound. When `_extract_event_phrases` returned 4 phrases
or `_extract_top_anchors` returned 3 anchors mixed with residue, the
output was a 6-7 item mechanical recitation.

Anchor extraction harvested any titlecase proper noun including
calendar tokens (Wednesday, October), religious-residue (Catholic,
Mass), and joining-word residue (then, the).

### Stock phrase (`lori_followup_bank`)

Hardcoded template:

```python
question = (
    f"You kept coming back to {best_anchor} — what was that "
    f"actually like for you?"
)
```

stamped across every `story_weighted_named_particular` follow-up.

## Fix

### Cascade dump fix (`lori_witness_mode`)

1. New `_CASCADE_FILTER_TOKENS` frozenset:
   - Calendar: Monday–Sunday, January–December
   - Religious-residue: Catholic, Mass, Church, School, Home, Family
   - Joining-word residue: then, the, and, but, so, or, when, while, where

2. New `_filter_cascade_residue(anchors)` function:
   - Drops anchors that are single-token AND in filter set
   - Strips leading filter token from multi-token anchors ("then Eileen" → "Eileen")
   - Dedupes case-insensitive

3. `_format_multi_anchor_list` capped at 2 items. The Oxford-style "A, B, and C"
   branch is gone. Two anchors maximum demonstrate active listening; three or
   more reads as a list dump.

### Stock phrase fix (`lori_followup_bank`)

Replace `"You kept coming back to {anchor} — what was that actually like for you?"`
with the more direct `"What was {anchor} actually like for you?"`. Loses the
stock-phrase opener while preserving the question content.

## Acceptance gates

- `_format_multi_anchor_list(["Saint Augustine", "Brendan", "then Eileen",
  "Patrick", "Catholic", "South Boston", "Mass", "Walter"], "en")` returns
  `"Saint Augustine and Brendan"` (Walter Era 2 cascade collapsed)
- `_format_multi_anchor_list(["Cochiti Pueblo", "August", "then Frank",
  "Elena", "Andrew", "Mary", "Catholic", "Mass"], "en")` returns
  `"Cochiti Pueblo and Frank"` (Joe Earliest cascade collapsed; August
  month-name + Catholic + Mass all dropped)
- 3-anchor input → 2-anchor output (cap)
- All-filter-token input → empty string
- Real anchor lists (Stanley + Fargo + Germany) → "Stanley and Fargo"
- Spanish locale uses "y" conjunction
- `lori_followup_bank` no longer emits "You kept coming back to X" stock phrase

## Files changed

- `server/code/api/services/lori_witness_mode.py`
  - `_CASCADE_FILTER_TOKENS` frozenset (~25 tokens)
  - `_filter_cascade_residue(anchors)` helper
  - `_format_multi_anchor_list` capped at 2 items
- `server/code/api/services/lori_followup_bank.py`
  - Replaced "You kept coming back to" template with direct question
- `tests/test_witness_anchor_cascade_filter.py` — 14 tests across 2 classes

## Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
