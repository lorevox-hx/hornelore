# Parent Session Rehearsal Report

Run:
- tag: `rehearsal_quick_v11`
- date/time: 2026-05-04T11:46:19.529365 → 2026-05-04T11:51:35.142102
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `quick`
- commit SHA: `e5adff0f`
- dirty tree: yes

## Topline

- **Overall: RED**
- Turns tested: 6
- Lori response failures: 0 RED / 1 AMBER
- Voice-rule failures: 0
- Life Map failures: 0 RED / 0 AMBER
- Silence-cue failures: 0 RED / 1 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

_No RED failures._

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | I'm doing well, thank you for asking! I'm a friendly companion here to help you share your story. I'm excited to get to know you better and help you create a Life Archive. To begin, I'd love to know y | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | I'm doing well, thank you for asking! I'm a friendly companion here to help you share your story. I'm excited to get to know you better and help you create a Life Archive. To begin, I'd love to know y | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | I'm doing well, thank you for asking! I'm a friendly companion here to help you share your story. I'm excited to get to know you better and help you create a Life Archive. To begin, I'd love to know y | 0 | 0 | 0 | 40 | ✗ | ✓ | AMBER |
| hearth | T4 | uncertainty | I don't remember much about the trip over | I'm doing well, thank you for asking! I'm a friendly companion here to help you share your story. I'm excited to get to know you better and help you create a Life Archive. To begin, I'd love to know y | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Coming of Age (coming_of_age) | ✓ | coming_of_age | ✓ | ✓ | 1 | 0 | PASS |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✗ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | AMBER |

## Shatner Life Map Cascade (TEST-21)

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_997249) |
| person_id | 2c7a422a-3e9 |
| Identity complete | ✗ — BB fields incomplete: fullName='William' dob='1931-03-22' place='Montreal, Quebec, Canada' |
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

_(cascade not run — pass --include-long-life to enable)_

## Cross-Narrator Divergence

_(only one voice ran — no divergence comparison)_
## Runtime Hygiene

| Check | Expected | Actual | Pass |
|---|---|---|---|
| kawa_mode absent from runtime71 | absent | absent | ✓ |
| current_era key present in runtime71 | present | present | ✓ |

## Recommended Fix List

_No fixes recommended — all checks passed or only AMBER findings._
