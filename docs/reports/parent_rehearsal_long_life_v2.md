# Parent Session Rehearsal Report

Run:
- tag: `long_life_v2`
- date/time: 2026-05-04T07:58:34.577734 → 2026-05-04T08:17:39.872128
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `standard`
- commit SHA: `951436d4`
- dirty tree: yes

## Topline

- **Overall: RED**
- Turns tested: 18
- Lori response failures: 5 RED / 2 AMBER
- Voice-rule failures: 0
- Life Map failures: 1 RED / 6 AMBER
- Silence-cue failures: 0 RED / 0 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

| Test | Voice | Turn | Failure | Lori said | Expected |
|---|---|---|---|---|---|
| voice/T1 | field | T1 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T2 | field | T2 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T3 | field | T3 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T4 | field | T4 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T1 | shield | T1 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| lifemap | — | Today | RED: era click produced no Lori response |  | Lori must respond, era_id matches, no menu/compound |

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | Hello! I'm doing well, thank you for chatting with me today. I'm glad we get to talk and get to know each other better. Let's start with something easy. What's the day today? | 1 | 0 | 0 | 33 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | Hello! I'm doing well, thank you for chatting with me today. I'm glad we get to talk and get to know each other better. Let's start with something easy. What's the day today? | 1 | 0 | 0 | 33 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | Hello! I'm doing well, thank you for chatting with me today. I'm glad we get to talk and get to know each other better. Let's start with something easy. What's the day today? | 1 | 0 | 0 | 33 | ✗ | ✓ | AMBER |
| hearth | T4 | uncertainty | I don't remember much about the trip over | Hello! I'm doing well, thank you for chatting with me today. I'm glad we get to talk and get to know each other better. Let's start with something easy. What's the day today? | 1 | 0 | 0 | 33 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |
| field | T1 | greeting | hello how are you |  | — | — | — | — | ✗ | ✓ | RED |
| field | T2 | resistance | I told you about that already |  | — | — | — | — | ✗ | ✓ | RED |
| field | T3 | story_seed | Mother had a Sunday voice for church and a Monday voice for survival. |  | — | — | — | — | ✗ | ✓ | RED |
| field | T4 | uncertainty | I don't talk about that part of growing up |  | — | — | — | — | ✗ | ✓ | RED |
| field | T5 | direct_q | what do you know about me | … | 0 | 0 | 0 | 0 | ✓ | ✓ | PASS |
| field | T6 | correction | no, I said Macon, not Atlanta | … | 0 | 0 | 0 | 0 | ✓ | ✓ | PASS |
| shield | T1 | greeting | hello how are you |  | — | — | — | — | ✗ | ✓ | RED |
| shield | T2 | resistance | you already asked | Chat error: Not enough GPU memory for this turn — please try a shorter message or try again shortly.. Try again. | 0 | 0 | 0 | 20 | ✓ | ✓ | PASS |
| shield | T3 | story_seed | My father never ate pork, but he said it was because his stomach was sensitive. | Chat error: Not enough GPU memory for this turn — please try a shorter message or try again shortly.. Try again. | 0 | 0 | 0 | 20 | ✗ | ✓ | AMBER |
| shield | T4 | uncertainty | I cannot speak of that | Chat error: Not enough GPU memory for this turn — please try a shorter message or try again shortly.. Try again. | 0 | 0 | 0 | 20 | ✓ | ✓ | PASS |
| shield | T5 | direct_q | what do you know about me | Chat error: Not enough GPU memory for this turn — please try a shorter message or try again shortly.. Try again. | 0 | 0 | 0 | 20 | ✓ | ✓ | PASS |
| shield | T6 | correction | no, that was my mother's mother, not my father's | Chat error: Not enough GPU memory for this turn — please try a shorter message or try again shortly.. Try again. | 0 | 0 | 0 | 20 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | ✓ | ✗ | 0 | 0 | AMBER |
| Early School Years (early_school_years) | ✓ | early_school_years | ✓ | ✗ | 0 | 0 | AMBER |
| Adolescence (adolescence) | ✓ | adolescence | ✓ | ✗ | 0 | 0 | AMBER |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | ✓ | ✗ | 0 | 0 | AMBER |
| Building Years (building_years) | ✓ | building_years | ✓ | ✗ | 0 | 0 | AMBER |
| Later Years (later_years) | ✓ | later_years | ✓ | ✗ | 0 | 0 | AMBER |
| Today (today) | ✓ | today | ✗ | ✗ | — | — | RED |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✓ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | PASS |

## Shatner Life Map Cascade (TEST-21)

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_043979) |
| person_id | 355cb1e6-cae |
| Identity complete | ✗ — identity intake threw: intake stalled — no Lori reply after sending 'William Shatner' |
| Cascade severity | **RED** |

**STRICT — Life Map click chain**

| Era | Clicked | Click log | Lori prompt log | currentEra | Lori replied | Lori clean | Q | Nest | Menu | Severity |
|---|---|---|---|---|---|---|---:|---:|---:|---|

**INFORMATIONAL — Timeline + Memoir downstream subscribers** _(known gap, never RED)_

| Era | Timeline active | Memoir top heading | Memoir excerpt | Notes |
|---|---|---|---|---|

**Strict failure reasons:**

- Identity intake did not complete — historical era click would be gated. Aborting cascade to avoid downstream noise.

> **Downstream subscriber note:** Timeline (chronology accordion) and Peek at Memoir (popover) do NOT auto-react to era-click events today. The `lv-interview-focus-change` CustomEvent is dispatched but has zero subscribers in the codebase. This is a known gap tracked as **WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01** and is INTENTIONALLY surfaced as informational AMBER, not RED, so it does not falsely fail the Life Map quote-fix verification.

## TEST-22 — Long-Life Multi-Voice Cascade

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_090684) |
| person_id | 2935089f-260 |
| Identity complete | ✗ — BB fields incomplete: fullName='' dob='' place='' |
| Total era steps | 0 |
| Cascade severity | **RED** |

**STRICT — Era click chain** _(per era; drives RED)_

| Era | Voice | Click | Click log | Prompt log | currentEra | activeFocus | Lori re-engaged | Era-anchored | Q | Nest | Menu | Voice rule | Severity |
|---|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|

**Era seed turns + Lori replies**

| Era | Voice | Seed (excerpt) | Lori to seed (excerpt) | Lori to re-click (excerpt) |
|---|---|---|---|---|

**INFORMATIONAL — Downstream cohesion** _(known gap pre-WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01; never RED)_

| Era | Timeline active | Memoir section | Memoir top heading | Notes |
|---|---|---|---|---|

**Memory Recall — end-of-arc**


**Voice Arc Divergence**


**Cascade failure reasons:**

- Identity intake did not complete — historical era click would be gated. Aborting cascade.

## Cross-Narrator Divergence

### Turn T3

| Voice | Q count | Menu | Words | Voice rule | Severity | Lori reply (excerpt) |
|---|---:|---:|---:|---|---|---|
| hearth | 1 | 0 | 33 | ✓ | AMBER | Hello! I'm doing well, thank you for chatting with me today. I'm glad we get to |
| field | None | None | None | ✓ | RED |  |
| shield | 0 (expected 0) | 0 | 20 | ✓ | AMBER | Chat error: Not enough GPU memory for this turn — please try a shorter message o |

- ✓ Shield T3 zero-question (sacred_silence honored)
- ✓ Shield T3 no kosher/Jewish/sacred vocabulary

### Turn T4

| Voice | Q count | Menu | Words | Voice rule | Severity | Lori reply (excerpt) |
|---|---:|---:|---:|---|---|---|
| hearth | 1 | 0 | 33 | ✓ | PASS | Hello! I'm doing well, thank you for chatting with me today. I'm glad we get to |
| field | None | None | None | ✓ | RED |  |
| shield | 0 | 0 | 20 | ✓ | PASS | Chat error: Not enough GPU memory for this turn — please try a shorter message o |


## Runtime Hygiene

| Check | Expected | Actual | Pass |
|---|---|---|---|
| kawa_mode absent from runtime71 | absent | absent | ✓ |
| current_era key present in runtime71 | present | present | ✓ |

## Recommended Fix List

1. BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 regression — era today clicked but Lori produced no reply. Check _lvInterviewSelectEra sendSystemPrompt path.
