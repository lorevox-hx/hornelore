# WO-EX-VALIDATE-01 — Age-math plausibility validator

## Status: SHIPPED (dark — flag OFF until post-test activation)

## Purpose

Defensive runtime gate for the extractor. Catches temporally impossible
or implausible facts before they reach the frontend and prevent the
narrator from being asked to review nonsense like "first job at age 4"
or "Medicare at age 30".

## Design

Pure function in `server/code/api/life_spine/validator.py`. No DB, no
network. Extractor fetches DOB once per request and passes it in.

### Event classification

- **ok** — fits all age-envelope rules for this event_kind, OR no
  envelope is defined for this kind (unmapped → pass-through).
- **warn** — soft outlier; usually a data error but could be legit. UI
  can badge but does not suppress.
- **impossible** — hard violation (event predates birth, civic event
  below legal minimum). Extractor drops these items before response
  assembly; they are never shown to the operator.

### Age envelopes

Each `event_kind` maps to `(min_age, max_age, severity_if_min_violated)`.
Severity is `impossible` for civic/legal anchors (voting, drinking,
Medicare, SS) and `warn` for biological/institutional events (school,
retirement, first job) where the rule is statistical not legal.

Full table in `_AGE_ENVELOPES` — 18 event kinds covering school,
adolescence, early adulthood, midlife, later-life, plus five soft life
events (first_job, marriage, child_birth, parent_death, retirement).

### Field-path → event_kind inference

Small static map (`_FIELD_TO_EVENT_KIND`) bridges the extractor's field
paths to validator event kinds. Conservative on purpose — only fields
whose values are reliably datable are mapped. Unmapped fields
short-circuit to `ok`.

## Integration

`extract.py` calls `_apply_age_math_filter()` AFTER `_group_repeatable_items()`
on both LLM and rules paths, INSIDE `flags.age_validator_enabled()` gate.

```python
if _flags.age_validator_enabled():
    _dob = _fetch_dob_for_validation(req.person_id)
    final_items = _apply_age_math_filter(final_items, _dob)
```

DOB lookup fails silently (`None` → validator returns `ok`). Any
exception inside the filter is logged and swallowed; items pass through
unfiltered rather than the request crashing.

## Activation

```bash
# .env
HORNELORE_AGE_VALIDATOR=1
```

Default is `0`. No code change required to enable.

## Tests

`tests/test_life_spine_validator.py` — 22 unit tests covering:

- Basic age computation (birthday boundary, pre-birth negatives)
- Each envelope category (civic impossible, school warn, over-110 warn)
- Field-path inference (dateOfBirth pass-through, retirement year-in-
  string parsing)
- Jane Doe fixture from the research doc (5 events, 1 impossible)
- Graceful degradation (missing DOB, unknown event_kind, malformed value)

All 22 pass.

## Tomorrow's test plan

Flag stays OFF for tomorrow's Chris accordion / extraction test. After
that test passes, flip the flag and spot-check five sample extractions:

1. "I was born in 1962" → `personal.dateOfBirth=1962` → flag=ok
2. "I started kindergarten in 1955" (for Chris, 1962 DOB) → dropped as impossible (age -7)
3. "I retired in 2025" → flag=warn (age 62 is below 50 retirement floor is false — 62 is IN envelope, so this should be ok). Actually check: retirement envelope is (50, 90), so age 62 → ok.
4. "Started college in 1981" → flag=ok (age 18, within 16-35 envelope)
5. Free-text hobby entry with a year → flag=ok (unmapped event_kind)

## Known limits / future work

- SSA Full Retirement Age gradient (1938-1942 cohort is 65+N months) not
  applied — validator uses 65 as absolute floor. Kent/Janice edge case.
- Pre-1984 state-specific drinking age not modeled — validator uses 18
  as absolute floor. Could warn for values 18-20 between 1984-present.
- Selective Service gap 1957-03-29 to 1959-12-31 (no registration
  required) not modeled — no Horne narrators in this range.
- Validator does not cross-check events against each other (married
  before born, retired before first job). That's WO-EX-02 territory.
