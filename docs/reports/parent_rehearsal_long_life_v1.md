# Parent Session Rehearsal Report

Run:
- tag: `long_life_v1`
- date/time: 2026-05-04T07:32:28.619123 → 2026-05-04T07:38:34.104223
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `quick`
- commit SHA: `951436d4`
- dirty tree: no

## Topline

- **Overall: RED**
- Turns tested: 6
- Lori response failures: 0 RED / 0 AMBER
- Voice-rule failures: 0
- Life Map failures: 1 RED / 0 AMBER
- Silence-cue failures: 0 RED / 1 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

| Test | Voice | Turn | Failure | Lori said | Expected |
|---|---|---|---|---|---|
| lifemap | — | Coming of Age | RED: era click produced no Lori response |  | Lori must respond, era_id matches, no menu/compound |

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | … | 0 | 0 | 0 | 0 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | … | 0 | 0 | 0 | 0 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | It sounds like that silk ribbon held a special significance for your mother. What was the occasion she usually took it out for? | 1 | 0 | 0 | 23 | ✓ | ✓ | PASS |
| hearth | T4 | uncertainty | I don't remember much about the trip over | It sounds like that silk ribbon held a special significance for your mother. What was the occasion she usually took it out for? | 1 | 0 | 0 | 23 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Coming of Age (coming_of_age) | ✓ | coming_of_age | ✗ | ✗ | — | — | RED |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✗ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | AMBER |

## Shatner Life Map Cascade (TEST-21)

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_804968) |
| person_id | 1d9b197b-216 |
| Identity complete | ✗ — BB fields incomplete: fullName='' dob='' place='' |
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
| Narrator added | ✓ (Test_900813) |
| person_id | 7bc794ee-4b5 |
| Identity complete | ✗ — identity intake threw: intake stalled after sending 'Esther Ridley-Yamamoto-Cordova' |
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

_(only one voice ran — no divergence comparison)_
## Runtime Hygiene

| Check | Expected | Actual | Pass |
|---|---|---|---|
| kawa_mode absent from runtime71 | absent | absent | ✓ |
| current_era key present in runtime71 | present | present | ✓ |

## Recommended Fix List

1. BUG-LIFEMAP-ERA-CLICK-NO-LORI-01 regression — era coming_of_age clicked but Lori produced no reply. Check _lvInterviewSelectEra sendSystemPrompt path.
