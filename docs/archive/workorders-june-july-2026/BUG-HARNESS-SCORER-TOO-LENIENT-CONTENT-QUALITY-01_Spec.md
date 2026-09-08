# BUG-HARNESS-SCORER-TOO-LENIENT-CONTENT-QUALITY-01

**Status:** CLOSED — patched 2026-06-17
**Severity:** HIGH (measurement infrastructure — every other Lori bug fix
becomes unmeasurable without this)
**Surface:** scripts/harness_lib.py::score_chapter, all long-narration harnesses

## Problem

The 2026-06-17 full-family harness run called responses like the following
PASS under the original 8-row scoring matrix:

| Response | Old scorer | Reality |
|---|---|---|
| `"West St."` | reflection_grounded:PASS, one_question_max:PASS, ... | orphan stub fragment, no real response |
| `"Got it — It Was The Air. Did I get that name right? What happened next?"` | PARTIAL question count, PASS rest | broken META_FEEDBACK template on a sentence-fragment |
| `"You went from Saint Augustine to Brendan, then Eileen, Patrick, Catholic, South Boston, Mass, and Walter. What happened next?"` | reflection_grounded:PASS (any anchor matched) | mechanical proper-noun cascade dump |
| `"Here is a response that follows the rules and guidelines: ..."` | PASS most rows | LLM meta-instruction leak |
| `"You were born in Albany, Georgia, in 1942?"` (Mable, with seeded DOB+POB) | PASS most rows | asks for confirmation of seeded bio fact (CLAUDE.md principle 8 violation) |

Without scorer hardening, every subsequent Lori fix is unmeasurable —
the next eval round can't tell us if a backend patch moved the topline.

## Fix

Add 8 new content-quality rows to `score_chapter`. Each is hard-FAIL on
detection (no PARTIAL) because the patterns are unacceptable Lori voice:

| # | Row | Catches |
|---|---|---|
| 9 | `no_false_name_confirmation` | "Did I get that name right?" on a phrase |
| 10 | `no_got_it_stub` | `Got it — X. What happened next?` shell |
| 11 | `no_titlecase_phrase_as_name` | "Originally Schong With A C", "It Was The Air", "Because The Adults Stopped Moving" |
| 12 | `response_not_fragmented` | "West St.", "St.", "Began.", single-token stubs |
| 13 | `minimum_anchor_count` | response with zero anchors from narrator text |
| 14 | `no_meta_response_leak` | "Here is a response that follows the rules and guidelines:", "This response reflects...", "Let me capture a few key points", "What a rich and evocative narrative" |
| 15 | `no_titlecased_anchor_cascade` | "You went from X to Y, then Z, A, B, and C" template + "You said X / You kept coming back to X" stock-phrase |
| 16 | `no_seeded_fact_intake_question` | Lori asking for seeded bio facts she already has |

The original 8 rows are preserved unchanged for matrix-integrity comparisons.
Total scoring matrix is now 16 rows.

## Backwards compatibility

- `score_chapter(chapter, response_text, is_bonus=False)` still works — the
  new `seeded_facts` kwarg is optional. When omitted, the seeded-fact row
  is reported as PASS (no seeded context to validate against).
- All existing harnesses that import `score_chapter` from `harness_lib`
  continue to work without modification.
- The original 8 rows produce identical results.

## Retro-application

Added `scripts/regrade_harness_reports.py` to apply the 6 text-only
detection rows (rows 9, 10, 11, 12, 14, 15) to existing harness reports
under `docs/reports/*.txt`. This lets us measure how many of the
2026-06-17 PASS results were masking broken Lori output without
re-running the live backend harnesses.

Usage:
```
python3 scripts/regrade_harness_reports.py
# writes docs/reports/regrade_summary_<ts>.md
```

## Acceptance gates

1. `Got it — Originally Schong With A C. Did I get that name right?` fails
   `no_false_name_confirmation`, `no_got_it_stub`, `no_titlecase_phrase_as_name`
2. `West St.` and `St.` fail `response_not_fragmented`
3. `Here is a response that follows the rules and guidelines:` fails
   `no_meta_response_leak`
4. `You went from Saint Augustine to Brendan, then Eileen, Patrick, ...` fails
   `no_titlecased_anchor_cascade`
5. `You were born in Albany, Georgia, in 1942?` with seeded DOB+POB fails
   `no_seeded_fact_intake_question`
6. Good grounded response ("Albany and Mount Olive AME — that combination
   stays with me. What was a typical Sunday morning like back then?") passes
   all 8 new rows
7. Existing tests/harness flows are unaffected (16-row scorer is a superset
   of the original 8-row scorer)

## Files changed

- `scripts/harness_lib.py`
  - Added `_NAME_LIKELIHOOD_STOPWORDS`, 8 compiled regex pattern banks
  - Added `_detect_*` helpers (one per row)
  - Extended `score_chapter` with 8 new rows + optional `seeded_facts` kwarg
- `scripts/regrade_harness_reports.py` — new retro-apply script
- `tests/test_harness_scorer_hardening.py` — new test pack (~25 tests
  across 8 row classes + integration tests)

## Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
