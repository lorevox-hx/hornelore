# Parent Session Rehearsal Report

Run:
- tag: `rehearsal_quick_v1`
- date/time: 2026-05-03T16:01:07.376453 → 2026-05-03T16:05:44.856396
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `quick`
- commit SHA: `f10ede97`
- dirty tree: no

## Topline

- **Overall: RED**
- Turns tested: 6
- Lori response failures: 1 RED / 0 AMBER
- Voice-rule failures: 0
- Life Map failures: 1 RED / 0 AMBER
- Silence-cue failures: 1 RED / 0 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

| Test | Voice | Turn | Failure | Lori said | Expected |
|---|---|---|---|---|---|
| voice/T1 | hearth | T1 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| lifemap | — | Coming of Age | RED: era click produced no Lori response |  | Lori must respond, era_id matches, no menu/compound |
| silence | — | T7 | RED: silence test narrator setup failed: session_start: neither Start Narrator Session nor Enter Interview Mode visible |  | no spoken cue when LV_ATTENTION_CUE_TICKER=true |

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you |  | — | — | — | — | ✗ | ✓ | RED |
| hearth | T2 | resistance | you already asked me that | It seems we started somewhere in the middle of our conversation. Let's begin aga | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out | That's a beautiful image. It sounds like the silk ribbon held some special meani | 1 | 0 | 0 | 25 | ✓ | ✓ | PASS |
| hearth | T4 | uncertainty | I don't remember much about the trip over | That's a beautiful image. It sounds like the silk ribbon held some special meani | 1 | 0 | 0 | 25 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of bi | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes y | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Coming of Age (coming_of_age) | ✗ | (empty) | ✗ | ✗ | — | — | RED |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✗ |  | ✓ suppressed | ✗ | ✗ | RED |

## Cross-Narrator Divergence

_(only one voice ran — no divergence comparison)_
## Runtime Hygiene

| Check | Expected | Actual | Pass |
|---|---|---|---|
| kawa_mode absent from runtime71 | absent | absent | ✓ |
| current_era key present in runtime71 | present | present | ✓ |

## Recommended Fix List

1. BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 regression — era coming_of_age clicked but Lori produced no reply. Check _lvInterviewSelectEra sendSystemPrompt path.
