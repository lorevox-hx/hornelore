# Parent Session Rehearsal Report

Run:
- tag: `stress_v1`
- date/time: 2026-05-04T12:07:55.575696 → 2026-05-04T12:26:05.786393
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `standard`
- commit SHA: `5c3a368b`
- dirty tree: no

## Topline

- **Overall: RED**
- Turns tested: 18
- Lori response failures: 4 RED / 1 AMBER
- Voice-rule failures: 0
- Life Map failures: 0 RED / 1 AMBER
- Silence-cue failures: 0 RED / 1 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

| Test | Voice | Turn | Failure | Lori said | Expected |
|---|---|---|---|---|---|
| voice/T2 | field | T2 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T3 | field | T3 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T4 | field | T4 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T3 | shield | T3 | RED: voice rule expects question_count=0, got 1 | …Some people like to go by nicknames or shorter versions of their names. What would you like me to call you? | RED: voice rule expects question_count=0, got 1 |

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | I'm doing great, thanks for asking. I'm here to help you build a Life Archive, a collection of your life stories. To get started, I need to know a few basics about you. Can you tell me, what's your pr | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | I'm doing great, thanks for asking. I'm here to help you build a Life Archive, a collection of your life stories. To get started, I need to know a few basics about you. Can you tell me, what's your pr | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | I'm doing great, thanks for asking. I'm here to help you build a Life Archive, a collection of your life stories. To get started, I need to know a few basics about you. Can you tell me, what's your pr | 0 | 0 | 0 | 40 | ✗ | ✓ | AMBER |
| hearth | T4 | uncertainty | I don't remember much about the trip over | I'm doing great, thanks for asking. I'm here to help you build a Life Archive, a collection of your life stories. To get started, I need to know a few basics about you. Can you tell me, what's your pr | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |
| field | T1 | greeting | hello how are you | …What's your full name? | 1 | 0 | 0 | 4 | ✓ | ✓ | PASS |
| field | T2 | resistance | I told you about that already |  | — | — | — | — | ✗ | ✓ | RED |
| field | T3 | story_seed | Mother had a Sunday voice for church and a Monday voice for survival. |  | — | — | — | — | ✗ | ✓ | RED |
| field | T4 | uncertainty | I don't talk about that part of growing up |  | — | — | — | — | ✗ | ✓ | RED |
| field | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| field | T6 | correction | no, I said Macon, not Atlanta | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |
| shield | T1 | greeting | hello how are you | …Hello! I'm here to listen and help you build a Life Archive, your personal story told in your own voice. What's your full name? | 1 | 0 | 0 | 24 | ✓ | ✓ | PASS |
| shield | T2 | resistance | you already asked | …Some people like to go by nicknames or shorter versions of their names. What would you like me to call you? | 1 | 0 | 0 | 21 | ✓ | ✓ | PASS |
| shield | T3 | story_seed | My father never ate pork, but he said it was because his stomach was sensitive. | …Some people like to go by nicknames or shorter versions of their names. What would you like me to call you? | 1 | 0 | 0 | 21 | ✗ | ✓ | RED |
| shield | T4 | uncertainty | I cannot speak of that | …What's your date of birth? | 1 | 0 | 0 | 5 | ✓ | ✓ | PASS |
| shield | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| shield | T6 | correction | no, that was my mother's mother, not my father's | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | ✓ | ✗ | 1 | 0 | AMBER |
| Early School Years (early_school_years) | ✓ | early_school_years | ✓ | ✓ | 1 | 0 | PASS |
| Adolescence (adolescence) | ✓ | adolescence | ✓ | ✓ | 1 | 0 | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | ✓ | ✓ | 1 | 0 | PASS |
| Building Years (building_years) | ✓ | building_years | ✓ | ✓ | 1 | 0 | PASS |
| Later Years (later_years) | ✓ | later_years | ✓ | ✓ | 1 | 0 | PASS |
| Today (today) | ✓ | today | ✓ | ✓ | 1 | 0 | PASS |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✗ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | AMBER |

## Shatner Life Map Cascade (TEST-21)

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_975435) |
| person_id | bf0ad66a-bec |
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

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_067997) |
| person_id | 2d2f1b30-168 |
| Identity complete | ✗ — BB fields incomplete: fullName='William' dob='1931-03-22' place='Montreal, Quebec, Canada' |
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
| hearth | 0 | 0 | 40 | ✓ | AMBER | I'm doing great, thanks for asking. I'm here to help you build a Life Archive, a |
| field | None | None | None | ✓ | RED |  |
| shield | 1 (expected 0) | 0 | 21 | ✓ | RED | …Some people like to go by nicknames or shorter versions of their names. What wo |

- ✗ Shield T3 q_count=1 (sacred_silence VIOLATED)
- ✓ Shield T3 no kosher/Jewish/sacred vocabulary

### Turn T4

| Voice | Q count | Menu | Words | Voice rule | Severity | Lori reply (excerpt) |
|---|---:|---:|---:|---|---|---|
| hearth | 0 | 0 | 40 | ✓ | PASS | I'm doing great, thanks for asking. I'm here to help you build a Life Archive, a |
| field | None | None | None | ✓ | RED |  |
| shield | 1 | 0 | 5 | ✓ | PASS | …What's your date of birth? |


## Runtime Hygiene

| Check | Expected | Actual | Pass |
|---|---|---|---|
| kawa_mode absent from runtime71 | absent | absent | ✓ |
| current_era key present in runtime71 | present | present | ✓ |

## Recommended Fix List

_No fixes recommended — all checks passed or only AMBER findings._


## Stress Telemetry (WO-OPS-STRESS-TELEMETRY-KV-01)

- snapshots captured: **10**
- kv-clear calls: **2**
- elapsed: **1084.3s**

### api.log signal counts (run window)

| Signal | Count |
|---|---:|
| FOREIGN KEY constraint failed | 50 |
| comm_control trims | 9 |
| comm_control validate-only | 12 |
| sendSystemPrompt timeouts | 0 |
| Phase G disconnects | 0 |
| GPU OOM | 0 |
| VRAM_GUARD blocks | 0 |

### Prompt-tokens histogram

- n=44 min=3828 p25=5651 median=5942 p75=6445 p95=6837 max=6985
- avg growth per turn: **2.62%**

| Bucket | Count |
|---|---:|
| 0-1000 | 0 |
| 1000-2000 | 0 |
| 2000-3000 | 0 |
| 3000-4000 | 9 |
| 4000-5000 | 2 |
| 5000-6000 | 14 |
| 6000-7000 | 19 |
| 7000+ | 0 |

### KV-clear effectiveness

- calls: 2, successes: 2
- total freed: 362.0 MB
- avg freed per call: 181.0 MB
- min/max freed: 62.0/300.0 MB
