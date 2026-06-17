# BUG-LORI-PHRASE-AS-NAME-CONFIRMATION-01

**Status:** CLOSED — patched 2026-06-17
**Severity:** HIGH (cross-narrator Lori voice failure — fired 7× across
5 narrators in one harness run)
**Surface:** `server/code/api/services/lori_witness_mode.py`

## Reproduction

The 2026-06-17 full-family harness produced this template across 5
different narrators on what were descriptive sentence fragments, not names:

```
Got it — Originally Schong With A C. Did I get that name right?                  (Jake Ch1)
Got it — You Learned To Stand Up And Sit Down And Kneel At The Right Times. ...  (Jake Ch2)
Got it — It Was The Air. Did I get that name right?                              (Shatner Earliest)
Got it — Ottawa. What happened next?                                              (Shatner Later)
Got it — Because The Adults Stopped Moving. Did I get that name right?            (Frank Earliest)
Got it — In March. Did I get that name right?                                     (Walter Era 6)
Got it — It Out Loud In The Empty Kitchen. Did I get that name right?             (Richard Building)
Got it — That I Still Picture Clearly. Did I get that name right?                 (John seven-era)
Got it — Began. Did I get that name right?                                        (John seven-era)
```

The narrator is being asked to confirm whether Lori spelled a descriptive
sentence fragment correctly as if it were a real name. The template
shouldn't fire on these — only on actual proper-noun names.

## Root cause

`services/lori_witness_mode.py:compose_witness_response` decides between
the `correction` template (plain ack) and the `correction_spelling`
template ("Did I get that name right?"). Before the patch:

```python
sub_type = detection.sub_type
if sub_type == "correction" and detection.factual_anchor:
    anchor_tokens = detection.factual_anchor.split()
    if len(anchor_tokens) >= 2:
        cap_count = sum(1 for t in anchor_tokens if t and t[0].isupper())
        if cap_count >= max(1, len(anchor_tokens) // 2):
            sub_type = "correction_spelling"
```

Any 2+ token phrase where half the tokens start with uppercase fires
the spelling-confirm template. That matches:
- "It Was The Air"  (4/4 titlecase)
- "Originally Schong With A C"  (5/5 titlecase)
- "You Learned To Stand Up And Sit Down And Kneel At The Right Times" (10/12 titlecase)

But all of these are descriptive sentence fragments, not names. Real
names rarely contain articles ("The", "A"), prepositions ("In", "Of"),
common verbs ("Was", "Were", "Began", "Stopped"), or adverbs
("Originally", "Still", "Clearly").

## Fix

Add `_looks_like_descriptive_phrase()` helper that returns True if the
candidate anchor is a descriptive sentence fragment. Three triggers:

1. **Ends with period** — sentence-shaped, not name-shaped
   ("Began.", "Stopped.")
2. **Contains descriptive-phrase tokens in titlecase position** —
   a frozenset of ~75 common English verbs/articles/prepositions/
   adverbs that real proper-noun names almost never contain
   ("Was", "Were", "Is", "The", "A", "An", "And", "Of", "With",
   "In", "Originally", "Because", "Still", "Clearly", "Stopped",
   "Picture", "Began", "Learned", "Stand", "Sit", "Kneel", "I",
   "We", "You", "Was", calendar tokens like "Monday"...)
3. **5+ tokens long** — statistically, real names are rarely 5+ tokens

Trigger refined to: 2-4 tokens AND not descriptive AND 50%+ titlecase.

## Acceptance gates

For each of these (all observed in the 2026-06-17 run), the
`correction_spelling` template MUST NOT fire:

| Input | Template that should fire |
|---|---|
| "Originally Schong With A C" | correction (plain ack) |
| "It Was The Air" | correction |
| "Because The Adults Stopped Moving" | correction |
| "That I Still Picture Clearly" | correction |
| "It Out Loud In The Empty Kitchen" | correction |
| "Began." | correction |
| "In March" | correction |
| "You Learned To Stand Up And Sit Down And Kneel..." | correction |

For each of these, `correction_spelling` MUST still fire:

| Input | Template that should fire |
|---|---|
| "Eliseo Sandoval" | correction_spelling |
| "Las Vegas" | correction_spelling |
| "Magee Hospital" | correction_spelling |
| "Boston Latin School" | correction_spelling |
| "Mount Olive AME" | correction_spelling |
| "New Mexico Highlands University" | correction_spelling |

## Files changed

- `server/code/api/services/lori_witness_mode.py`
  - `_DESCRIPTIVE_PHRASE_TOKENS` frozenset (~75 tokens across verbs,
    articles, prepositions, adverbs, calendar)
  - `_looks_like_descriptive_phrase()` helper function
  - Trigger refined to require 2-4 tokens AND not descriptive AND
    50%+ titlecase position
- `tests/test_witness_phrase_as_name_guard.py` — 15 tests (8 true-positive
  rejection cases + 7 true-negative preservation cases)

## Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
