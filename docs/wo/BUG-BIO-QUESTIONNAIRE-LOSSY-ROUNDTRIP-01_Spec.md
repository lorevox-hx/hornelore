# BUG-BIO-QUESTIONNAIRE-LOSSY-ROUNDTRIP-01

**Status: OPEN — filed 2026-09-15. Do NOT fix inside the portability or
Phase 7 lanes.** Belongs to the post-portability Bio Persistence work.

## Mission alignment

The narrator is the author of their own story. A spouse's maiden name and a
child's birthplace are not incidental metadata — they are the family record the
system exists to preserve. A save that quietly removes them is the failure this
project cares about most, and it is worse than a crash because nothing tells
anyone it happened.

## Non-regression requirements

This BUG's eventual fix MUST NOT:

- reduce narrator dignity
- introduce new must_not_write violations or system-tone outputs
- regress the CURRENT locked baseline without explicit justification
- expand operator surfaces into narrator UI
- add detectors that duplicate existing signals

## Summary

`bio_questionnaire_view` does not round-trip every field that
`bio_questionnaire_writer` accepts and stores for `spouses` and `children`
entries. Because Bio Builder rebuilds each repeatable entry from the rendered
view and then PUTs the whole questionnaire back, a later save can **erase**
fields that were stored correctly.

## Evidence (verified_by_execution, 2026-09-15, disposable root)

A rich spouse and two rich children were PUT to
`/api/bio-builder/questionnaire` for a synthetic narrator
(`952baf78-3c40-4fa7-b0c8-8df801140e17`, "Daniel Robert Mercer").

**Stored correctly** — direct read of the database, not the API:

```sql
SELECT json_extract(profile_json,'$.spouses'),
       json_extract(profile_json,'$.children')
FROM profiles WHERE person_id='952baf78-…';
```

returned spouse `maidenName: "Reynolds"`, `birthPlace: "Pueblo, Colorado"`,
`notes: "Known as Patty. Married Daniel on 14 June 1981."`, and both children
with `relation` (`Son` / `Daughter`) and `birthPlace` (`Albuquerque, New
Mexico` / `Santa Fe, New Mexico`).

**Absent from the canonical GET view** — the same five fields do not appear in
`GET /api/bio-builder/questionnaire`. `spouses` projects down to first/middle/
last name, `yearMarried`, `status`, `birthDate`; `children` to name plus
`dateOfBirth`.

**Not a blanket rule, which is what makes it a defect rather than a design.**
`parents` round-trips every field including `maidenName`, `birthPlace`,
`occupation`, `notableLifeEvents` and `notes`; `siblings` round-trips
`relation`, `birthDate` and `notes`. The writer's own allowlist
(`bio_questionnaire_writer.py:278-284`) explicitly accepts `relation`,
`birthPlace`, `maidenName` and `notes` for these array sections — so the write
side and the read side disagree about the same shape.

## The silent-loss path

1. Rich spouse/child data is stored in `profiles.profile_json` (correct).
2. Bio Builder GETs the questionnaire and renders it — five fields are already
   missing from what it received.
3. The operator opens the section and saves. Bio Builder rebuilds each
   repeatable entry **from the fields present in the DOM**, so the rebuilt
   object cannot contain what the view never sent.
4. `_persistDrafts()` PUTs the whole questionnaire.
5. The writer assigns the reduced arrays into `profile_patch` and merges them
   into `profile_json`.

The stored rich array is replaced by the reduced one. No error, no warning, and
the operator's own act of reviewing the record is what destroys it.

## Acceptance

Deliberately small:

1. PUT a spouse and a child carrying every field the writer's allowlist
   accepts.
2. GET returns **every** supported field.
3. Perform a no-op Bio Builder save of those sections.
4. Read `profiles.profile_json` directly — the objects are equivalent to step 1.

Step 4 must read the database, not the API. A test that checks the API against
the API cannot see this class of defect at all, which is why it survived until
a direct SQL read was taken.

## The invariant this establishes

**Anything the canonical questionnaire writer accepts must survive the
canonical read → edit → save round trip, unless the schema explicitly declares
it non-persistent.**

That is the first concrete invariant for Bio Persistence Integrity, and it
generalizes past this bug: any surface that rebuilds an object from a rendered
view and writes it back inherits the read path's omissions as deletions.

## Scope notes

Two adjacent observations from the same session, recorded so they are not
rediscovered as bugs. Neither is part of this defect:

- The questionnaire has **no field** for grandchildren, dated residences,
  hobbies, pets, favourite things, or life events. Those belong to Life Map
  timeline events and story candidates, not here.
- `people.display_name` carries the narrator's warm/preferred name while the
  full legal name lives in the bio lane as `full_legal_name`. That split is
  correct and deliberate.
