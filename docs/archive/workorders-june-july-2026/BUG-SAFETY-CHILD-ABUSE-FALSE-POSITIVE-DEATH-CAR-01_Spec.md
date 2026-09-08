# BUG-SAFETY-CHILD-ABUSE-FALSE-POSITIVE-DEATH-CAR-01

**Status:** CLOSED — patched 2026-06-17
**Severity:** HIGH (safety classifier false-positive — routes ordinary oral-history grief content into child_abuse + operator notify + softened mode)
**Narrator generality:** UNIVERSAL — fires whenever biographical accident/death content mentions a parent role

## Reproduction

Two confirmed false positives in the 2026-06-17 full-family harness run:

**1. John adolescence (operator-directive-as-narrator-text artifact)**

```
[chat_ws][safety] triggered conv=switch_mqif35x7_wdpv category=child_abuse confidence=0.70
[chat_ws][safety][notify] ... matched='[compound trigger]'
  excerpt="Lori, Life Map era: Adolescence. John's father died when John was a teenager.
  The known context is that his father was changing a tire and was hit by a car. John
  also traveled in Europe as a teenager"
```

**2. Stefi earliest years (innocent first-person biographical text)**

```
[chat_ws][safety] triggered conv=45304e10-c03 category=child_abuse confidence=0.70
[chat_ws][safety][notify] ... matched='[compound trigger]'
  excerpt='I was born in Las Vegas, New Mexico — not the Nevada one, the New Mexico
  one — on the twenty-third of May, 1944. My father Eliseo was a sheep rancher in
  San Miguel County, third generation on the land'
```

Both are pure oral-history biographical text. Neither contains abuse content. In production this would:
- Push the narrator into softened mode
- Fire an operator-visible safety alert
- Pollute segment_flags with a false child_abuse classification
- (In this run the FK constraint failure on chat_ws softened path masked some of the persistence consequences — but the notify still went out and the response template still routed through safety.)

## Root cause

`server/code/api/safety.py:_check_compound_child_abuse` had two firing paths:

```python
if has_age and has_perp and has_harm:
    return ("child_abuse", 0.92)
if has_perp and has_harm and not has_age:
    return ("child_abuse", 0.70)  # ← exactly at THRESHOLD = 0.70
return None
```

The `0.70` path is dangerously weak. It fires on:
- `_PERPETRATOR_ROLES`: `father|mother|dad|mom|parent|uncle|grandfather|...`
- `_HARM_VERBS`: `touch|hurt|hit|abuse|rape|molest|assault|forced|did things|came into my...`

For the John text:
- "father" → has_perp = True
- "hit by a car" → "hit" matches `\bhit\b` → has_harm = True
- "as a teenager" does NOT match `_CHILD_AGE_PATTERNS` (which requires "when i was X years old" or `growing up`/`childhood`/etc.)
- → has_age = False
- → returns `("child_abuse", 0.70)` at exactly threshold

The harm verb `\bhit\b` does not distinguish between active intentional harm ("father hit me") and passive accident ("father was hit by a car"). The compound check matches on token presence anywhere in the normalized text.

## Why it matters

Per CLAUDE.md design principle 1: *"No operator leakage. Anything a narrator can see or interact with must be designed for narrators."*

A false-positive `child_abuse` flag:
- Triggers `LORI_SAFETY_RESPONSE` template instead of normal interview composer
- Logs a permanent segment_flag (when FK isn't blocking it) the operator sees as an abuse disclosure
- Pushes into softened mode which changes Lori's voice for N subsequent turns
- Sends operator-notify amber card

That is a structural privacy/dignity violation against the narrator — Lori is being told the narrator is an abuse survivor based on grief content.

## Fix

Add a biographical accident/death context guard at the top of `_check_compound_child_abuse`. If the text matches any of:

1. **Parent/family elder as victim of death:** `(my )?(father|mother|...|grandfather|aunt|brother|sister)\s+(died|was killed|passed away|never came home|lost his/her life|...)`

2. **Vehicular accident (passive victim form):** `(was|were|got|been)\s+(hit|struck|run over|killed|injured)\s+by\s+(a|an|the)\s+(car|truck|bus|train|motorcycle|drunk driver|...)`

3. **Mechanical/repair accident:** `(while )?(changing|fixing|repairing|working on|under)\s+(a|the|his|her)\s+(tire|wheel|car|engine|brake|...)`

4. **Medical death:** `(died|passed away|lost his/her battle)\s+(from|of|to|with|after)\s+(cancer|illness|disease|stroke|heart attack|covid|pneumonia|old age|...)`

If ANY pattern matches → return `None`. The compound trigger relies on weak signals; biographical accident/death narration is incompatible with that weak compound and yields.

**Important:** Real abuse content is not affected because real abuse fires via `_SIMPLE_TRIGGERS` (raped, molested, beat me, hit me, forced, etc.) at higher confidence (0.78–0.95). Those patterns match direct-object harm targeted at the narrator ("hit me", "beat me") not passive accident victims. The guard only blocks the WEAK compound path.

## Acceptance gates

1. John adolescence text ("my father died... was changing a tire... hit by a car") → no `child_abuse` trigger
2. Stefi biographical opener ("My father Eliseo was a sheep rancher... My grandmother died in 1985") → no `child_abuse` trigger
3. Third-person operator-directive variant ("John's father died when John was a teenager") → no `child_abuse` trigger
4. "I was raped when I was 12" → still triggers `sexual_abuse` @ 0.95 (unchanged)
5. "My uncle molested me when I was 8" → still triggers (simple trigger path)
6. "My stepfather hit me growing up" → still triggers (simple trigger `hit me`)
7. "My father died in a car accident. I want to kill myself" → fires `suicidal_ideation` (acute path unaffected, compound suppressed)

## Files changed

- `server/code/api/safety.py` — add `_ACCIDENT_DEATH_CONTEXT` regex + guard at top of `_check_compound_child_abuse`
- `tests/test_safety_compound_accident_guard.py` — new test file: 6 suppression cases + 4 true-positive preservation cases + 2 acute path unaffected cases

## Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
