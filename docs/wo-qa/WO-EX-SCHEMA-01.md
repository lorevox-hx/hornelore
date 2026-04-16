# WO-EX-SCHEMA-01 — Extend EXTRACTABLE_FIELDS to match question_bank promises

## Status: READY TO SCOPE — P0 BLOCKER for CLAIMS-01

## Discovery

During live-session observation on 2026-04-15, a full compound narrator
answer was completely dropped by the extractor:

> "My oldest, vince was born in Germany in 1960, my middle son Jay or Jason
> was born in Bismarck in 1961 and my youngest Chris or christopher was
> born on his dads birhday in december 24 1962."

Zero extraction. Three children, three birth years, two birthplaces,
three nicknames — lost.

Root cause is not LLM performance. Root cause is **schema gap**: the
question bank authored in v1–v3 lists `extract_priority` arrays that
include field paths the extractor cannot produce. The LLM prompt is
built from `EXTRACTABLE_FIELDS`, so the model is never told these paths
exist. It has nowhere to put a child.

### Schema gap inventory

| Question bank `extract_priority` entry | In EXTRACTABLE_FIELDS? |
|----------------------------------------|------------------------|
| `family.children`                      | ❌ missing              |
| `family.spouse`                        | ❌ missing              |
| `family.marriage_date`                 | ❌ missing              |
| `family.grandchildren`                 | ❌ missing              |
| `residence.place`                      | ❌ missing              |
| `residence.period`                     | ❌ missing              |

Six field families the question bank treats as extractable, none present
in the schema.

## Goal

Add the missing field families to `EXTRACTABLE_FIELDS` so the LLM prompt
exposes them, the extractor can route items to them, and downstream
frontend logic can display them.

## Scope

### In scope

- `server/code/api/routers/extract.py` — extend `EXTRACTABLE_FIELDS`
- Unit tests — verify new paths parse and route correctly
- Decision: `repeatable` vs single per field family (see Design below)

### Out of scope

- Frontend rendering of new fields (separate UI WO)
- Projection/promotion logic for new fields (uses existing projection-sync
  rules — `candidate_only` for repeatable, `suggest_only` for narrative)
- Canonical questionnaire schema changes in `state.bioBuilder.questionnaire`
  (separate — bioBuilder may already handle these paths, grep required)
- Claims-layer assembly (that's CLAIMS-01)

## Design

### Field additions

#### `family.*` (repeatable = "children" for child entries; non-repeatable for spouse data)

```python
# Children (repeatable)
"family.children.firstName":      {"label": "Child first name",      "writeMode": "candidate_only", "repeatable": "children"},
"family.children.lastName":       {"label": "Child last name",       "writeMode": "candidate_only", "repeatable": "children"},
"family.children.dateOfBirth":    {"label": "Child date of birth",   "writeMode": "candidate_only", "repeatable": "children"},
"family.children.placeOfBirth":   {"label": "Child place of birth",  "writeMode": "candidate_only", "repeatable": "children"},
"family.children.preferredName":  {"label": "Child nickname",        "writeMode": "candidate_only", "repeatable": "children"},
"family.children.relation":       {"label": "Child relation (son/daughter/etc.)", "writeMode": "candidate_only", "repeatable": "children"},

# Spouse / long-term partner (non-repeatable — a narrator has at most one
# current spouse; divorces/previous partners handled by a second field)
"family.spouse.firstName":        {"label": "Spouse / partner first name",    "writeMode": "prefill_if_blank"},
"family.spouse.lastName":         {"label": "Spouse / partner last name",     "writeMode": "prefill_if_blank"},
"family.spouse.maidenName":       {"label": "Spouse / partner maiden name",   "writeMode": "prefill_if_blank"},
"family.spouse.dateOfBirth":      {"label": "Spouse / partner DOB",           "writeMode": "prefill_if_blank"},
"family.spouse.placeOfBirth":     {"label": "Spouse / partner place of birth","writeMode": "prefill_if_blank"},

# Marriage event
"family.marriageDate":            {"label": "Date of marriage",               "writeMode": "prefill_if_blank"},
"family.marriagePlace":           {"label": "Place of marriage",              "writeMode": "prefill_if_blank"},
"family.marriageNotes":           {"label": "Marriage context / how we met",  "writeMode": "suggest_only"},

# Previous partners (repeatable for divorces, remarriages, significant prior relationships)
"family.priorPartners.firstName": {"label": "Previous partner first name",    "writeMode": "candidate_only", "repeatable": "priorPartners"},
"family.priorPartners.lastName":  {"label": "Previous partner last name",     "writeMode": "candidate_only", "repeatable": "priorPartners"},
"family.priorPartners.period":    {"label": "Period with previous partner",   "writeMode": "candidate_only", "repeatable": "priorPartners"},

# Grandchildren (repeatable)
"family.grandchildren.firstName": {"label": "Grandchild first name",          "writeMode": "candidate_only", "repeatable": "grandchildren"},
"family.grandchildren.relation":  {"label": "Grandchild relation (via which child)","writeMode": "candidate_only", "repeatable": "grandchildren"},
"family.grandchildren.notes":     {"label": "Grandchild personality or notable trait","writeMode": "candidate_only", "repeatable": "grandchildren"},
```

#### `residence.*` (repeatable — a narrator has many homes)

```python
"residence.place":                {"label": "City / town / address lived in",         "writeMode": "candidate_only", "repeatable": "residences"},
"residence.region":               {"label": "State / country of residence",           "writeMode": "candidate_only", "repeatable": "residences"},
"residence.period":               {"label": "Years at this residence (e.g., 1962-1964)","writeMode": "candidate_only", "repeatable": "residences"},
"residence.notes":                {"label": "Residence notes (home type, memory)",    "writeMode": "candidate_only", "repeatable": "residences"},
```

### Renaming note: question bank `family.marriage_date` vs new `family.marriageDate`

Python/JS convention is camelCase for field paths in this codebase (see
existing `education.careerProgression`, `earlyMemories.firstMemory`). The
question bank v2 used `family.marriage_date` (underscore) — that's
inconsistent with the rest. Two options:

1. **Canonicalize to camelCase** (recommended) — change the question bank
   from `family.marriage_date` → `family.marriageDate`. Small content
   edit, aligns with house style.
2. **Support both** — extractor accepts both paths, aliases underscore
   to camelCase internally. More code, less breakage.

Recommend option 1. Include in this WO as a one-line bank edit.

### Protected identity — should new fields be protected?

Current `PROTECTED_IDENTITY_FIELDS` is only narrator-identity (fullName,
DOB, etc.). Extending to `family.spouse.firstName`, `family.spouse.lastName`
is debatable:

- Pro: spouse identity is nearly as canonical as narrator identity; a
  child mentioning "my dad Kent" shouldn't overwrite canonical spouse.
- Con: narrator may correct spouse details multiple times in one session
  ("actually her maiden name was Zarr, not Zarr Horne").

**Recommendation:** do NOT add to PROTECTED_IDENTITY_FIELDS in this WO.
Treat spouse like a regular prefill_if_blank. Revisit in a later WO if
canonical-spouse conflict becomes a real pattern.

## Implementation steps

1. Extend `EXTRACTABLE_FIELDS` with the ~20 new field paths listed above
2. Update the LLM prompt's example sentences to include at least one
   child, one spouse, one residence (gives the model a pattern to follow)
3. Fix question_bank.json field path inconsistency (`marriage_date` →
   `marriageDate`)
4. Unit tests:
   - New paths appear in EXTRACTABLE_FIELDS
   - Sample LLM output with `family.children.firstName=Cole` survives
     extraction pipeline and reaches response
   - `residence.place=west Fargo` survives (no longer dropped by
     birth-context filter — verify our WO-EX-01C guards still do the
     right thing)
5. Integration test (if dev venv): post `/api/extract-fields` with a
   children-compound answer and verify multiple `family.children.*`
   items come back

## Acceptance criteria

- [ ] `EXTRACTABLE_FIELDS` contains all 6 field families listed above
- [ ] LLM prompt's field catalog includes the new paths (grep
  `_build_extraction_prompt` output with a test fixture)
- [ ] Question bank's `family.marriage_date` references renamed to
  `family.marriageDate`
- [ ] Unit tests pass
- [ ] No regressions in WO-EX-01C / WO-EX-01D / WO-EX-VALIDATE-01
  guard stacks
- [ ] Live test — post Janice's three-children compound to
  `/api/extract-fields` and see non-zero family.children.* items in
  the response (run after commit when dev venv up)

## Risks

**R1 — LLM overfits new fields.** Model may start inventing children/spouses
when narrator is talking about friends or colleagues. Mitigation: the
existing `_apply_subject_guard_filter` catches non-narrator contexts;
extending it to handle `family.*` equivalently is a 10-line change.

**R2 — Repeatable grouping gets harder.** Existing `_group_repeatable_items`
groups parents and siblings by first-name occurrence. Adding children
and grandchildren means the grouping heuristic may misassign fields
across families when narrator switches mid-answer. Mitigation: test with
a "my son Cole was born in 2002, and my daughter Sarah was born in
1998" fixture; if grouping drifts, add an explicit relation-marker
heuristic.

**R3 — Frontend doesn't yet render family.\* / residence.\***
The backend will happily return these, but the UI may not have buttons
for them. Out of scope for this WO, but flag as a follow-on UI WO.

## Estimated size

~3–4 hours for backend + tests. Frontend UI follow-on is separate.

## Report format (for Claude on completion)

```
WO-EX-SCHEMA-01 REPORT

FILES EDITED
- server/code/api/routers/extract.py
- data/prompts/question_bank.json  (marriage_date → marriageDate)
- tests/test_extract_schema_coverage.py  (new)

FIELDS ADDED
- family.children.*      (6 paths, repeatable="children")
- family.spouse.*        (5 paths, single)
- family.marriageDate,   family.marriagePlace, family.marriageNotes
- family.priorPartners.* (3 paths, repeatable="priorPartners")
- family.grandchildren.* (3 paths, repeatable="grandchildren")
- residence.*            (4 paths, repeatable="residences")

PROMPT UPDATE
- Added 1 child-birth example sentence
- Added 1 spouse example sentence
- Added 1 residence example sentence

TESTS
- Ran full suite: N tests, all passing
- Verified 6 new paths serialize and deserialize
- Verified question_bank.json references updated paths

LIVE VERIFICATION (if available)
- Posted Janice three-children compound → N family.children.* items returned

NOTES
- [any edge cases discovered]
- [frontend UI changes still needed — listed for follow-on WO]
```
