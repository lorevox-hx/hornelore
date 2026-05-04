# Parent Session Rehearsal Report

Run:
- tag: `rehearsal_quick_v7`
- date/time: 2026-05-04T10:29:05.523460 → 2026-05-04T10:35:01.332555
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `quick`
- commit SHA: `e5adff0f`
- dirty tree: yes

## Topline

- **Overall: RED**
- Turns tested: 6
- Lori response failures: 0 RED / 0 AMBER
- Voice-rule failures: 0
- Life Map failures: 0 RED / 1 AMBER
- Silence-cue failures: 0 RED / 0 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

_No RED failures._

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | … | 0 | 0 | 0 | 0 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | … | 0 | 0 | 0 | 0 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | That's a lovely image. A silk ribbon from her wedding, kept safe and special. What was your mother's name? | 1 | 0 | 0 | 19 | ✓ | ✓ | PASS |
| hearth | T4 | uncertainty | I don't remember much about the trip over | The trip over. It's possible that's a significant journey, but we haven't discussed it yet. Before we start exploring that, I'd like to know, what was your name when you were growing up? | 1 | 0 | 0 | 33 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | The trip over. It's possible that's a significant journey, but we haven't discussed it yet. Before we start exploring that, I'd like to know, what was your name when you were growing up? | 1 | 0 | 0 | 33 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Coming of Age (coming_of_age) | ✓ | coming_of_age | ✓ | ✗ | 0 | 0 | AMBER |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✓ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | PASS |

## Shatner Life Map Cascade (TEST-21)

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_434804) |
| person_id | a5e1607c-3dc |
| Identity complete | ✗ — identity intake threw: askName intro did not fire within 90s after session_start — check that lvSessionStyleEnter / startIdentityOnboarding fired |
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
