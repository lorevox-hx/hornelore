# WO-EX-PATCH-H-DATEFIELD-01 — Holiday-phrase date normaliser

**Author:** Claude (LOOP-01 R4 cleanup, task #67)
**Status:** Code landed, unit tests green (40/40), pending live-eval confirmation (r4i).
**Touches:** `server/code/api/routers/extract.py`, `tests/test_extract_holiday_normalisation.py`.

## Background

R4 Patch H added a write-time normaliser (`_apply_write_time_normalisation`) intended to coerce surface-form date variants into ISO `YYYY-MM-DD` before persisting. The dispatch table used a frozenset of field-name suffixes:

```python
_DATE_FIELD_SUFFIXES = frozenset({"birthDate", "deathDate", "marriageDate"})
```

case_011 of the master eval tests this exact behavior: narrator says *"I was born in Stanley, North Dakota. Christmas Eve, 1939."* and the expected `personal.dateOfBirth` is `"1939-12-24"`. In r4f and r4g the actual was `"Christmas Eve, 1939"` — un-normalised, scoring 0.50.

## Root cause (two stacked bugs)

### Bug 1 — suffix mismatch

The schema-actual field name is `personal.dateOfBirth` (suffix `dateOfBirth`). The frozenset only contained `birthDate`. The dispatch in `_apply_write_time_normalisation`:

```python
suffix = fp.rsplit(".", 1)[-1] if "." in fp else fp
if suffix == "birthOrder":
    ...
elif suffix in _DATE_FIELD_SUFFIXES:
    new_val = _normalize_date_value(raw)
```

never reached the `_normalize_date_value` branch for `personal.dateOfBirth`, `personal.dateOfDeath`, or `family.dateOfMarriage`. The normaliser was effectively dead code on the schema's primary date paths.

### Bug 2 — colloquial phrase not parseable

Even with the suffix fixed, `_normalize_date_value` only handled three input forms:

1. ISO `\d{4}-\d{2}-\d{2}` (passthrough)
2. Month-Day-Year (`December 24, 1939`)
3. Year-only `\b(1[89]\d{2}|20[0-4]\d)\b` (with a `len(s) <= 10` cap to avoid mangling prose)

`"Christmas Eve, 1939"` matched none of these, so the function returned the raw string. The existing branches were correct in isolation but blind to the colloquial vocabulary narrators actually use for memorable dates.

## Fix

Three localized changes in `extract.py`, all adjacent to the existing date-normalisation block:

### 1. Expand the suffix set

```python
_DATE_FIELD_SUFFIXES = frozenset({
    "birthDate", "deathDate", "marriageDate",
    "dateOfBirth", "dateOfDeath", "dateOfMarriage",
})
```

Legacy short forms retained for backward compatibility with any caller path that still emits them.

### 2. Add a holiday map + matching infrastructure

- `_HOLIDAY_DATE_MAP` (~30 entries): fixed-date holidays only. Variable feasts (Easter, Thanksgiving, Memorial Day, Mother's/Father's Day) are intentionally excluded — their date depends on the year and narrators rarely anchor birthdates on them; including them would require a moveable-feast calendar.
- `_DATE_HOLIDAY_RX`: matches `<phrase>[, ]YYYY` with phrase character class `[A-Za-z0-9'\u2019\s.]` so it tolerates digit-prefix variants (`4th of July`), curly apostrophes (Unicode U+2019, common in LLM output), and abbreviations with internal periods (`St. Patrick's Day`).
- `_normalize_holiday_phrase(phrase)`: lowercase, strip punctuation/apostrophes, collapse whitespace. Used to key into the map so surface variants (`"New Year's Eve"`, `"NEW YEAR'S EVE."`, `"new years eve"`) all collapse to the same lookup.

### 3. Add the holiday branch to `_normalize_date_value`

Inserted between the existing MDY branch (more precise) and the year-only fallback (less precise), so it only runs when MDY didn't match. Uses longest-prefix match so `"Christmas Eve"` wins over `"Christmas"` inside `"Christmas Eve, 1939"`.

## Why no other extraction path is affected

- `_apply_claims_validators` (which invokes `_apply_write_time_normalisation`) is called on **both** the LLM extraction path (extract.py:4413) and the rules extraction path (extract.py:4531). The fix lands in both.
- The MDY regex is unchanged, so `"December 24, 1939"` keeps its existing behavior.
- The ISO regex is unchanged, so `"1939-12-24"` keeps its existing passthrough.
- The year-only branch is unchanged (still capped at `len(s) <= 10`), so prose with embedded years like `"I graduated in 1968."` still passes through raw.
- Variable-feast phrases (`"Easter Sunday 1947"`, `"Thanksgiving, 1963"`) are not in the map; the holiday branch falls through to the year-only branch, which is len-capped, so these stay raw too.
- `_DATE_HOLIDAY_RX` only fires when `_DATE_MDY_RX` did not match — so `"December 24, 1939"` cannot be misrouted through the holiday branch.

## Unit-test evidence

`tests/test_extract_holiday_normalisation.py` — 40 tests, 5 classes:

| Class | Tests | Coverage |
|---|---|---|
| `TestHolidayNormaliser` | 17 | Every map entry exercised, including the case_011 string verbatim |
| `TestHolidayNonInterference` | 9 | ISO/MDY/year-only passthroughs + Easter/Thanksgiving/prose guards |
| `TestDateFieldSuffixCoverage` | 6 | Both legacy and schema-actual suffixes present |
| `TestWriteTimeNormalisationEndToEnd` | 5 | End-to-end via `_apply_write_time_normalisation` for the schema-actual paths |
| `TestHolidayMapSanity` | 3 | Map keys lowercase + apostrophe-free; (month,day) tuples in valid range |

Result: `Ran 40 tests in 0.004s — OK`.

## Expected r4i outcome

Comparing against r4h baseline (53/104 pass, v3 32/62, must_not_write 0%):

| Metric | r4h | r4i target | Rationale |
|---|---|---|---|
| Pass | 53/104 | 54/104 | case_011 flips to pass (score 0.50 → 1.00) |
| v3 subset | 32/62 | 33/62 | case_011 is in the contract subset |
| must_not_write | 0.0% | 0.0% | unchanged — no guard logic touched |
| follow_up | 7/8 | 7/8 | unchanged — no follow-up code path touched |
| dense_truth | 0/8 | 0/8 | unchanged — addressed at R5.5 |
| case_011 | fail 0.50 | **pass 1.00** | the actual target |

**Out-of-scope-but-watch:** any other case whose narrator dropped a holiday phrase into a date field could now flip pass. Audit case_012 + case_020 (the r4g→r4h stochastic regressions) on the same run as a noise control — if they flip back to pass while case_011 also passes, that's the strongest possible argument that they were stochastic.

## Risk register

- **Low**: The holiday branch only fires on strings that survive the ISO and MDY checks AND match the holiday regex. It cannot misroute existing well-formed dates.
- **Low**: Map is closed-world — unknown phrases fall through to the year-only branch (existing behavior). No new failure modes.
- **Negligible**: Compile-time regex precompilation; ~30-entry dict lookup. No measurable latency impact.
- **Mitigated**: All four "obvious" extension hazards (Title-cased keys, missing periods, Unicode apostrophes, digit-prefixes like `4th`) are explicitly tested.

## Rollback

Three edits, all in extract.py near line 3210–3340. A `git revert` of the #67 commit cleanly removes them. Test file is standalone and can be deleted independently. No schema migration, no API surface change.

## Closeout checklist

- [x] Three edits to `extract.py` land cleanly, syntax-check passes
- [x] 40-test regression suite written, all pass
- [x] WO report written (this file)
- [ ] Live r4i eval shows case_011 pass with no new regressions
- [ ] CLAUDE.md current-phase block updated to mark #67 closed
- [ ] Task #67 status → completed
