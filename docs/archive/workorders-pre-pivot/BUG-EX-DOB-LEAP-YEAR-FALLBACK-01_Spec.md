# BUG-EX-DOB-LEAP-YEAR-FALLBACK-01 — DOB normalizer drops to Jan 1 on Feb 29 input

**Title:** Preserve Feb 29 leap-year DOBs through `_normalize_date_value()` instead of falling back to Jan 1
**Status:** SCOPED — small, deterministic, eval-gated
**Date:** 2026-05-05
**Lane:** Extractor / DOB normalization
**Source:** TEST-23 v3 (2026-05-04). Mary's onboarding DOB capture.
**Blocks:** Nothing. Mary's identity loss class is closed; this is data fidelity.
**Related:** BUG-210 (DOB "December 31st 1937" → "1937-01-01" — same fallback class, different cause).

---

## Mission

Mary's DOB intake during TEST-23 v3 was `"2/29 1940"` (Feb 29, 1940 — a
real leap year). The post-extraction `_normalize_date_value()` path in
`server/code/api/routers/extract.py` (Patch H normalization) should have
produced `"1940-02-29"`. Instead it produced `"1940-01-01"` — the same
generic fallback used when a date can't be parsed. 1940 *is* a leap year,
so Feb 29 is valid; the normalizer is rejecting it incorrectly.

## Live evidence

TEST-23 v3 telemetry (2026-05-04):

```
[mary/onboard/dob] sent='2/29 1940' elapsed=22788ms
... later projection_json.fields:
  "personal.dateOfBirth": {"value": "1940-01-01", ...}
```

Expected: `"1940-02-29"`. Actual: `"1940-01-01"` — the catch-all fallback.

Mary herself was born on Feb 29 in the canon spec; this is supposed to be
captured precisely. Instead it silently degrades to a placeholder, which
then propagates into Lori's age math (life_stage derivation) and into any
operator-side review surface that says "DOB on file: 1940-01-01."

## Diagnostic hypotheses

The normalizer likely uses `datetime.strptime(s, "%Y-%m-%d")` or
`datetime.date(year, month, day)` somewhere in its cascade. Three
candidate failure points:

1. **Pre-parser regex too narrow.** A regex matching `M/D YYYY` may not
   accept `2/29 1940` (no comma, no dash).
2. **Calendar validator using the wrong year.** A check like
   `try: datetime.date(year=current_year, month=m, day=d)` on a non-leap
   year would reject Feb 29 — but only if the validator is using
   `current_year` instead of the parsed year.
3. **Default fallback too eager.** The `except ValueError: return f"{year}-01-01"`
   path may be running on a successfully-parsed date because of a
   downstream validator chain with a different rule.

Read `_normalize_date_value()` and trace the path Mary's "2/29 1940"
takes through it before deciding which option is correct.

## Locked design rules

1. **Real leap-year dates are valid.** Feb 29, 1940 / 1944 / 1948 / etc.
   must round-trip as `YYYY-02-29`.
2. **Invalid leap-year dates degrade explicitly.** Feb 29, 1939 (not a
   leap year) should produce a `confidence=0.5` candidate with value
   `1939-03-01` AND emit a `[extract][DOB-NORMALIZE] non-leap year`
   warning, NOT silently fall back to `1939-01-01`.
3. **Fallback is for unparseable inputs only.** "I don't remember" /
   "spring 1940" / non-date strings → fallback. A correctly-formatted
   date with a valid calendar tuple → never fallback.

## Fix shape

Three step diff in `server/code/api/routers/extract.py`:

1. Audit the regex(es) feeding into `_normalize_date_value()`. Confirm
   `(\d{1,2})/(\d{1,2})\s+(\d{4})` (Feb 29 1940 form) is in the cascade.
2. Replace `datetime.date(current_year, m, d)` validators with
   `datetime.date(year, m, d)` — use the parsed year, not the current
   year.
3. Add a leap-year sanity check: when `m==2 and d==29`, verify
   `calendar.isleap(year)`. If not, downgrade confidence and log
   `[DOB-NORMALIZE] non-leap`. If yes, accept and return `YYYY-02-29`.

## Acceptance

- Mary's "2/29 1940" intake produces `personal.dateOfBirth="1940-02-29"`.
- Synthetic test fixture for "2/29 1939" (non-leap) produces a
  `confidence=0.5` candidate with value "1939-03-01" and a
  `[DOB-NORMALIZE] non-leap` warning.
- Existing TEST-23 v3 evidence rerun: Mary's projection_json.fields shows
  `"personal.dateOfBirth": {"value": "1940-02-29", ...}`.
- master eval r5h-followup-guard-v1 unchanged (no DOB cases in the 114
  exercise this exact path).

## Scope estimate

~45 minutes once the normalizer site is read. Single-file diff,
calendar.isleap import, two condition tweaks, two fixtures.
