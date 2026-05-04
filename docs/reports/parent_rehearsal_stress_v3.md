# Parent Session Rehearsal Report

Run:
- tag: `stress_v3`
- date/time: 2026-05-04T13:11:43.788023 → 2026-05-04T13:33:55.190654
- stack: API=http://localhost:8000  UI=http://localhost:8082/ui/hornelore1.0.html
- mode: `standard`
- commit SHA: `5c3a368b`
- dirty tree: yes

## Topline

- **Overall: RED**
- Turns tested: 18
- Lori response failures: 4 RED / 2 AMBER
- Voice-rule failures: 0
- Life Map failures: 0 RED / 1 AMBER
- Silence-cue failures: 0 RED / 1 AMBER
- Runtime hygiene failures: 0

## Critical Failures (RED)

| Test | Voice | Turn | Failure | Lori said | Expected |
|---|---|---|---|---|---|
| voice/T1 | field | T1 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T1 | shield | T1 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |
| voice/T3 | shield | T3 | RED: voice rule expects question_count=0, got 1 | …Were you the oldest, the youngest, somewhere in the middle? | RED: voice rule expects question_count=0, got 1 |
| voice/T4 | shield | T4 | RED: no Lori reply within 45s |  | RED: no Lori reply within 45s |

## Per-Turn Results

| Voice | Turn | Type | Narrator input | Lori reply | Q | Nest | Menu | Words | Refl | Voice rule | Pass |
|---|---|---|---|---|---:|---:|---:|---:|---|---|---|
| hearth | T1 | greeting | hello how are you | I'm doing well, thank you for asking. I'm a friendly companion here to help you share your story. Would you like to tell me, what's your preferred name? | 1 | 0 | 0 | 28 | ✓ | ✓ | PASS |
| hearth | T2 | resistance | you already asked me that | I'm doing well, thank you for asking. I'm a friendly companion here to help you share your story. Would you like to tell me, what's your preferred name? | 1 | 0 | 0 | 28 | ✓ | ✓ | PASS |
| hearth | T3 | story_seed | Mother had a silk ribbon from her wedding. She'd take it out once a year, touch it, and put it back. | I'm doing well, thank you for asking. I'm a friendly companion here to help you share your story. Would you like to tell me, what's your preferred name? | 1 | 0 | 0 | 28 | ✗ | ✓ | AMBER |
| hearth | T4 | uncertainty | I don't remember much about the trip over | It can be a bit fuzzy at times, especially when looking back. Let's focus on getting to know you better. For our Life Archive, it's helpful to start with some basic information. Could you tell me, wha | 0 | 0 | 0 | 37 | ✓ | ✓ | PASS |
| hearth | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| hearth | T6 | correction | no, I said Williston, not Bismarck | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |
| field | T1 | greeting | hello how are you |  | — | — | — | — | ✗ | ✓ | RED |
| field | T2 | resistance | I told you about that already | …What would you like me to call you? Some people prefer a nickname or a shorter version of their name. | 1 | 0 | 0 | 20 | ✓ | ✓ | PASS |
| field | T3 | story_seed | Mother had a Sunday voice for church and a Monday voice for survival. | …Were you the oldest, the youngest, somewhere in the middle? | 1 | 0 | 0 | 10 | ✗ | ✓ | AMBER |
| field | T4 | uncertainty | I don't talk about that part of growing up | …Were you the oldest, the youngest, somewhere in the middle? | 1 | 0 | 0 | 10 | ✓ | ✓ | PASS |
| field | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| field | T6 | correction | no, I said Macon, not Atlanta | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |
| shield | T1 | greeting | hello how are you |  | — | — | — | — | ✗ | ✓ | RED |
| shield | T2 | resistance | you already asked | …What would you like me to call you? Some people prefer a nickname or a shorter version of their name. | 1 | 0 | 0 | 20 | ✓ | ✓ | PASS |
| shield | T3 | story_seed | My father never ate pork, but he said it was because his stomach was sensitive. | …Were you the oldest, the youngest, somewhere in the middle? | 1 | 0 | 0 | 10 | ✗ | ✓ | RED |
| shield | T4 | uncertainty | I cannot speak of that |  | — | — | — | — | ✗ | ✓ | RED |
| shield | T5 | direct_q | what do you know about me | What I know about you so far:  Identity - Name: (not on record yet) - Date of birth: (not on record yet) - Place of birth: (not on record yet)  Family - Parents: (none on record yet) - Siblings: (none | 0 | 0 | 0 | 40 | ✓ | ✓ | PASS |
| shield | T6 | correction | no, that was my mother's mother, not my father's | I heard that as a correction, but I'm not fully certain which field it changes yet. You can say it one piece at a time — for example, 'I was born in ...' or 'My father's name was ...'. | 0 | 0 | 0 | 38 | ✓ | ✓ | PASS |

## Life Map Results

| Era clicked | UI active | session.currentEra | Lori replied | Era appropriate | Q | Menu | Pass |
|---|---|---|---|---|---:|---:|---|
| Earliest Years (earliest_years) | ✓ | earliest_years | ✓ | ✓ | 1 | 0 | PASS |
| Early School Years (early_school_years) | ✓ | early_school_years | ✓ | ✓ | 1 | 0 | PASS |
| Adolescence (adolescence) | ✓ | adolescence | ✓ | ✓ | 1 | 0 | PASS |
| Coming of Age (coming_of_age) | ✓ | coming_of_age | ✓ | ✓ | 1 | 0 | PASS |
| Building Years (building_years) | ✓ | building_years | ✓ | ✓ | 1 | 0 | PASS |
| Later Years (later_years) | ✓ | later_years | ✓ | ✓ | 1 | 0 | PASS |
| Today (today) | ✓ | today | ✓ | ✗ | 1 | 0 | AMBER |

## Silence / Presence Cue Results

| Pause | Visual cue present | Cue text | Spoken cue fired | Transcript-ignore | idle_fire_blocked log | Pass |
|---:|---|---|---|---|---|---|
| 30s | ✗ | Take your time. I'm listening. | ✓ suppressed | ✓ | ✓ | AMBER |

## Shatner Life Map Cascade (TEST-21)

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_010729) |
| person_id | d66595e0-c58 |
| Identity complete | ✓ |
| Cascade severity | **PASS** |

**STRICT — Life Map click chain**

| Era | Clicked | Click log | Lori prompt log | currentEra | Lori replied | Lori clean | Q | Nest | Menu | Severity |
|---|---|---|---|---|---|---|---:|---:|---:|---|
| Today (today) | ✓ | ✓ | ✓ | today | ✓ | ✓ | 1 | 0 | 0 | PASS |
| Coming of Age (coming_of_age) | ✓ | ✓ | ✓ | coming_of_age | ✓ | ✓ | 1 | 0 | 0 | PASS |

**INFORMATIONAL — Timeline + Memoir downstream subscribers** _(known gap, never RED)_

| Era | Timeline active | Memoir top heading | Memoir excerpt | Notes |
|---|---|---|---|---|
| Today (today) | today | Your Story | Your Story         Getting Started                                  ⬇️ Save TXT | Memoir top heading is 'Your Story' — does not match active era 'Today'. Known gap, WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01 |
| Coming of Age (coming_of_age) | coming_of_age | Your Story | Your Story         Getting Started                                  ⬇️ Save TXT | Memoir top heading is 'Your Story' — does not match active era 'Coming of Age'. Known gap, WO-LIFEMAP-DOWNSTREAM-SUBSCRI |

> **Downstream subscriber note:** Timeline (chronology accordion) and Peek at Memoir (popover) do NOT auto-react to era-click events today. The `lv-interview-focus-change` CustomEvent is dispatched but has zero subscribers in the codebase. This is a known gap tracked as **WO-LIFEMAP-DOWNSTREAM-SUBSCRIBERS-01** and is INTENTIONALLY surfaced as informational AMBER, not RED, so it does not falsely fail the Life Map quote-fix verification.

## TEST-22 — Long-Life Multi-Voice Cascade

**Setup**

| Check | Value |
|---|---|
| Narrator added | ✓ (Test_140192) |
| person_id | 76f58384-8e2 |
| Identity complete | ✗ — BB fields incomplete: fullName='William Shatner' dob='1931-03-22' place='Montreal, Quebec, Canada' |
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
| hearth | 1 | 0 | 28 | ✓ | AMBER | I'm doing well, thank you for asking. I'm a friendly companion here to help you |
| field | 1 | 0 | 10 | ✓ | AMBER | …Were you the oldest, the youngest, somewhere in the middle? |
| shield | 1 (expected 0) | 0 | 10 | ✓ | RED | …Were you the oldest, the youngest, somewhere in the middle? |

- ✗ Shield T3 q_count=1 (sacred_silence VIOLATED)
- ✓ Shield T3 no kosher/Jewish/sacred vocabulary

### Turn T4

| Voice | Q count | Menu | Words | Voice rule | Severity | Lori reply (excerpt) |
|---|---:|---:|---:|---|---|---|
| hearth | 0 | 0 | 37 | ✓ | PASS | It can be a bit fuzzy at times, especially when looking back. Let's focus on get |
| field | 1 | 0 | 10 | ✓ | PASS | …Were you the oldest, the youngest, somewhere in the middle? |
| shield | None | None | None | ✓ | RED |  |


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
- elapsed: **1322.5s**

### api.log signal counts (run window)

| Signal | Count |
|---|---:|
| FOREIGN KEY constraint failed | 55 |
| comm_control trims | 15 |
| comm_control validate-only | 10 |
| sendSystemPrompt timeouts | 0 |
| Phase G disconnects | 0 |
| GPU OOM | 0 |
| VRAM_GUARD blocks | 0 |

### Prompt-tokens histogram

- n=49 min=3831 p25=4130 median=6266 p75=6516 p95=7063 max=7256
- avg growth per turn: **3.33%**

| Bucket | Count |
|---|---:|
| 0-1000 | 0 |
| 1000-2000 | 0 |
| 2000-3000 | 0 |
| 3000-4000 | 12 |
| 4000-5000 | 2 |
| 5000-6000 | 5 |
| 6000-7000 | 27 |
| 7000+ | 3 |

### KV-clear effectiveness

- calls: 2, successes: 2
- total freed: 142.0 MB
- avg freed per call: 71.0 MB
- min/max freed: -358.0/500.0 MB
