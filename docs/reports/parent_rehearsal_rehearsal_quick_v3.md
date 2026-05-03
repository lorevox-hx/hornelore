# Parent Session Rehearsal Report

Run:
- tag: `rehearsal_quick_v3`
- date/time: 2026-05-03T17:14:05.911630 → 2026-05-03T17:19:08.930472
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `quick`
- commit SHA: `a203c8a9`
- dirty tree: no

## Topline

- **Overall: RED**
- Turns tested: 6
- Lori response failures: 1 RED / 0 AMBER
- Voice-rule failures: 0
- Life Map failures: 1 RED / 0 AMBER
- Silence-cue failures: 0 RED / 1 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

| Test | Voice | Turn | Failure | Lori said | Expected |
|---|---|---|---|---|---|
| voice/T4 | hearth | T4 | RED: menu_offer present | It seems like you're not recalling a lot about the trip over. Would you like to tell me more about what you do remember, or perhaps we can f | RED: menu_offer present |
| lifemap | — | Coming of Age | RED: era click produced no Lori response |  | Lori must respond, era_id matches, no menu/compound |

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | Hello! I'm doing well, thank you for asking. I'm happy to chat with you today. Before we begin, I just want to remind you that I'm here to help build a personalized life story, and to make that possib | 0 | 0 | 0 | 39 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | I'll keep that in mind. Let's start fresh. I'm here to listen and learn about your life story. Can you start by telling me, what's your name? | 1 | 0 | 0 | 27 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | That's a lovely image. It sounds like that silk ribbon held a special place in your mother's heart. What was your mother's name? | 1 | 0 | 0 | 23 | ✓ | ✓ | PASS |
| hearth | T4 | uncertainty | I don't remember much about the trip over | It seems like you're not recalling a lot about the trip over. Would you like to tell me more about what you do remember, or perhaps we can focus on a different part of your life story? What would you | 1 | 0 | 1 | 40 | ✓ | ✓ | RED |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Coming of Age (coming_of_age) | ✗ | (empty) | ✗ | ✗ | — | — | RED |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✗ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | AMBER |

## Cross-Narrator Divergence

_(only one voice ran — no divergence comparison)_
## Runtime Hygiene

| Check | Expected | Actual | Pass |
|---|---|---|---|
| kawa_mode absent from runtime71 | absent | absent | ✓ |
| current_era key present in runtime71 | present | present | ✓ |

## Recommended Fix List

1. Layer 2 discipline filter trim missed a menu offer — audit composer call site for the affected turn intent
2. BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 regression — era coming_of_age clicked but Lori produced no reply. Check _lvInterviewSelectEra sendSystemPrompt path.
