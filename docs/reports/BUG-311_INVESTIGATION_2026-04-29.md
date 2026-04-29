# BUG-311 Investigation — 2026-04-29 (Overnight)

**Original report:** "Lori-text leakage into narrator-extract candidates ('still learning how to' → fullName)"
**Status after investigation:** **RECLASSIFIED.** Not a Lori-text leakage bug. This is an extractor span-hallucination bug. Belongs in WO-EX-BINDING-01 lane (#152 / Type C binding error per Architecture Spec v1).

## What was originally suspected

In the 2026-04-28 live test, Shadow Review surfaced 8 candidate claims after the 1000-word "clean" test ran on Christopher Horne. Three looked like Lori-text leakage:

```
personal.fullName  = "still learning how to"   ← suspected Lori-text bleed
parents.firstName  = "Play"                    ← suspected noise
parents.lastName   = "The Organ"               ← suspected noise
```

Filed task #311 as a chunking/payload bug suspecting `_extractAndProjectMultiField` was including Lori-side text in the extraction payload.

## What investigation found

Read the 1000-word test sample source at `ui/js/test-harness.js:65-98`. The "clean" SAMPLES dict is verbatim narrator-side text — Lori never authored it. The phrases extraction surfaced ARE in the narrator's answer:

```
test-harness.js:72  "...sitting in church listening to my mother play the organ.
                     Music was always present in our home."

test-harness.js:98  "Even now, I am still learning how to navigate family
                     dynamics, maintain connections, and find meaning..."
```

So:
- "Play" came from "**play** the organ" — a noun-phrase the LLM extracted as a firstName.
- "The Organ" came from "play **the organ**" — extracted as a lastName.
- "still learning how to" came from "I am **still learning how to** navigate..." — extracted as a fullName.

The extraction payload was correctly narrator-only. There's no chunking leak. The bug is the EXTRACTOR's span-binding logic taking arbitrary noun-phrases from narrative prose and routing them to identity-field schema slots.

## Code paths verified clean

```
ui/js/app.js:4167         answerText: text           ← user's typed/STT message only
ui/js/interview.js:925    answerText: clean          ← user's typed/STT message only
ui/js/interview.js:1281   payload.answer: chunk      ← chunks of answerText, narrator-side
```

No path threads Lori's reply into the extraction payload. The "Lori-text leakage" suspicion was a false positive from interpreting the surface symptoms.

## Why this is a real bug worth tracking

Even though the protected_identity gate (BUG-312 fix landed) now routes these candidates to suggest_only instead of writing to truth directly, the operator still has to dismiss garbage in Shadow Review. With the 1000-word sample producing 5 garbage candidates out of 8 (62.5% noise), Shadow Review fatigue becomes real for parent-session operators.

## Reclassification

```
WAS:  BUG-311 Lori-text leakage into narrator-extract candidates
NOW:  BUG-311 Extractor span-binding hallucination — narrative prose
      noun-phrases routed to identity-field slots
LANE: WO-EX-BINDING-01 (#152) — Type C binding error
EVIDENCE: Add 1000-word test sample as a fixture to the BINDING-01
          smoke pack alongside case_082 (V1/V6).
```

## Recommended fixes (defer to BINDING-01 implementation)

```
1. Anti-noise-span guard in extraction prompt few-shots
   Add 2-3 negative examples to extract.py few-shot set:
     INPUT:  "play the organ"
     OUTPUT: []  (verb-phrase, not a person)
     NOT:    [{fieldPath: "parents.firstName", value: "Play"}]

2. Capitalization+length heuristic at write-time
   In _apply_write_time_normalisation (extract.py L5986), add a
   noise-span filter for identity fields:
     - Reject firstName/lastName/fullName values where the value
       starts with a lowercase word that isn't a name particle
       (de, van, von, etc.)
     - Reject values longer than 30 chars on firstName/lastName
       (already done for some fields; extend coverage)
     - Reject values that contain question marks, periods (mid-string),
       or sentence-fragment markers ("how to", "still learning",
       "I am", etc.)

3. Narrator-self-reference guard
   "I am" / "my name" / "I was" patterns at extraction time should
   route to personal.* not parents.* / siblings.* / spouse.*
   (BUG-227 partially addresses this but doesn't catch sentence
   fragments).
```

## What was NOT done in this overnight investigation

- No code changes applied. This is investigation-only.
- The recommended fixes are drafted for the BINDING-01 implementer
  to evaluate against the existing few-shot set + Type C eval matrix.
- No new task created for this — the task #311 description should be
  updated by Chris in the morning to reflect the reclassification, OR
  this investigation note can stand as the closing record.

## Operator-side observation (not a code fix)

The 1000-word "clean" test sample is a deliberately rich script that
produces SOME garbage candidates as a side-effect of being high-density
narrative prose. That's the harness working as designed — exposing
extractor weakness on rich narrative. Operator should expect Shadow
Review noise on the 1000-word test until BINDING-01 ships.
