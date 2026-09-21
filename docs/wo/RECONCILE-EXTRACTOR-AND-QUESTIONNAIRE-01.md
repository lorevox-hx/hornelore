# Destination reconciliation — the 20 undefined suggestions

Read-only analysis, 2026-09-20. **Nothing implemented. No mapping added,
no questionnaire field created, no suggestion altered.**

Scope: the 20 queued suggestions whose `fieldPath` the questionnaire does
not define, the extractor definitions that produced them, and what it
would take for each kind of information to have a place a narrator can
see and correct.

Sources: `server/code/api/routers/extract.py` `EXTRACTABLE_FIELDS`
(line 198 onward) and `ui/js/bio-builder-questionnaire.js` `SECTIONS`
(line 347 onward, 16 sections / 91 fields).

---

## The finding that changes what this work is

Reading the stored VALUES rather than only the paths shows two different
problems wearing one label.

**Problem A — a destination genuinely does not exist.** Military service,
residences, travel and faith are real parts of a life and the
questionnaire has no section for any of them. Kent served in Germany;
there is nowhere in his biography to say so.

**Problem B — the value does not match its own declared field.** This is
not a routing problem and no destination fixes it:

    military.branch          = "Nike Ajax Nike Hercules missile site"
        label says "Military branch (Army, Navy, etc.)". That is an
        installation and a missile system, not a branch.

    military.rank            = "assigned to go up to an army site up in
                                the mountains for training in use of
                                chemical biological radiological training"
        label says "Highest military rank attained". That is an episode.

    military.yearsOfService  = "in Germany"
        label says "Years of military service (e.g., 1965-1968)".
        That is a place.

    community.organization   = "32nd Artillery Brigade"
        label says "Community organization or group". That is his
        military unit, not a community group.

    residence.period         = "mostly"
        label says "Years at this residence (e.g., 1962-1964)".

    family.marriageDate      = "temporal context implies recent past,
                                exact dates unknown"
    residence.period         = "temporal context implies short stay,
                                exact dates unknown"
        The model narrating its own uncertainty into a date field.

    travel.purpose           = "ate our first Germany meal"
        label says "Purpose of travel (vacation, work, family,
        military)". That is something that happened on the trip.

**Nine of the twenty are Problem B.** If we only close the schema gap,
those nine become faithfully stored wrong answers: Kent's military branch
would read "Nike Ajax Nike Hercules missile site" in his family's
archive, and it would look like something he said. **Adding fields makes
that worse, not better** — today the mismatch is at least visible as a
warning.

So the reconciliation has to separate "where does this belong" from "is
this a usable answer at all", and the second question is an extraction
defect, not a schema decision.

---

## Path-by-path

Verdict key: **NEW SECTION** · **NEW FIELD** · **MAP** (an existing field
can hold it faithfully) · **EXTRACTION DEFECT** (no destination is
right — the value does not match its label) · **DROP** (the path should
not exist)

### Military — 6 paths, 6 suggestions, all Kent

    extract.py:330-335   military.branch, yearsOfService, rank,
                         deploymentLocation, significantEvent, notes
    questionnaire        NO military section exists

**Verdict: NEW SECTION, repeatable per posting.** Military service is a
life chapter with dates, places and events, not a field. Kent's six
suggestions describe one posting in Germany — a unit, a base, a role, a
courier duty, a training episode. Flattened into six scalars on a flat
section, a second posting would overwrite the first.

Proposed shape, for discussion: `military` repeatable, entries with
`branch`, `rank`, `unit`, `serviceStart`, `serviceEnd`, `location`,
`role`, `notableEvents`, `notes` — mirroring how `parents` works.

⚠ **Four of the six values are Problem B** and must not be imported into
the new fields even after it exists: `branch`, `rank`, `yearsOfService`
and arguably `significantEvent` (a courier reassignment is an event, so
that one is arguably fine). Only `deploymentLocation = "Germany"` and
`notes` are usable as written.

⚠ `military.notes` and `military.significantEvent` are declared
`repeatable: "military"` at extract.py:333-334 while `branch`, `rank`,
`yearsOfService` are flat — the extractor's own schema is internally
inconsistent about whether military is repeatable.

### Residence — 2 paths, 4 suggestions

    extract.py:301,303   residence.place, residence.period
                         both repeatable: "residences"
    questionnaire        NO residence section exists

**Verdict: NEW SECTION, repeatable.** Where someone lived and when is
ordinary biography and the form cannot record it at all. `hobbies.travel`
exists but is about travel, not residence — mapping a home into it would
merge two distinct facts.

Usable: `Santa Fe`, `Kaiserslautern`. Problem B: both `period` values
(`"mostly"`, `"temporal context implies short stay…"`).

### Travel — 2 paths, 2 suggestions, both Christopher

    extract.py:365,366   travel.destination, travel.purpose
                         both repeatable: "travel"
    questionnaire        hobbies.travel (a single free-text field,
                         bio-builder-questionnaire.js, hobbies section)

**Verdict: MAP, with a caveat — or NEW SECTION.**
`hobbies.travel` can hold "Lewis and Clark Visitor Center" as prose. But
the extractor models travel as repeatable entries with a destination and
a purpose, and `hobbies.travel` is one textarea. Mapping N structured
trips into one paragraph is lossy in a specific way: **it merges distinct
trips into one field** and discards which purpose went with which
destination.

Recommendation: MAP is acceptable now (one free-text field is honest
about being prose); a repeatable `travel` section is the better end
state if trips matter to the memoir. `travel.purpose = "ate our first
Germany meal"` is Problem B regardless.

### Faith — 1 path, 1 suggestion

    extract.py:338       faith.denomination
    questionnaire        technology.culturalPractices — the closest
                         existing field, and NOT a match

**Verdict: NEW FIELD, probably a NEW SECTION.**
"Catholic" is a clean, usable value. `technology.culturalPractices`
exists in the section labelled "Technology & Beliefs", so there is a
gesture toward belief in the schema, but folding a denomination into a
field about cultural practices merges two different facts and buries a
simple answer in a prose field.

⚠ Faith is sensitive. A narrator should be able to leave it blank, and
whatever field exists should be plainly optional. Worth an explicit
decision rather than a default.

### Community — 1 path, 1 suggestion

    extract.py:353       community.organization, repeatable: "community"
    questionnaire        education.communityInvolvement (free text)

**Verdict: EXTRACTION DEFECT for this value; MAP for the path.**
`education.communityInvolvement` is a reasonable home for community
organisations. But the stored value is `"32nd Artillery Brigade"` —
Kent's military unit, misfiled as a community group. Mapping it would
put his army unit under community involvement, which is wrong in a way a
reader would not detect.

The path can MAP. This value cannot.

### Education — 2 paths, 2 suggestions

    extract.py:419       education.gradeLevel  = "6th grade"
    extract.py:218       education.notes       = "took tests and
                                                  medical exams"
    questionnaire        education.schooling (free text, "Schooling")

**`education.gradeLevel` — MAP, faithfully.** "6th grade" belongs in
`education.schooling`. No loss: schooling is free text and a grade level
is part of schooling history.

**`education.notes` — EXTRACTION DEFECT.** "took tests and medical exams"
is Kent's military induction, not education. (This is the value that
first exposed the misclassification problem earlier in this project.)
Mapping it into `education.schooling` would state that Kent's schooling
consisted of tests and medical exams.

### Family / marriage — 2 paths, 3 suggestions

    extract.py:276,277   family.marriageDate, family.marriagePlace
    questionnaire        marriage (REPEATABLE section) with
                         marriageDate, proposalStory, weddingDetails,
                         spouseReference

**Verdict: MAP — a pure naming mismatch, and the clearest win here.**
The questionnaire HAS `marriage.marriageDate`. The extractor calls it
`family.marriageDate`. Same fact, different name.

⚠ Two cautions. `marriage` is repeatable and `family.marriageDate` is
flat, so a mapping must resolve *which marriage* — exactly the C4
unresolved-destination case the review surface already handles.
And there is no `marriagePlace` field; `weddingDetails` could hold
"Cathedral of the Holy Spirit" as prose, which is a MAP with mild loss
(a place merged into a details paragraph), or it argues for a
`marriagePlace` field.

Christopher's `"2010"` is usable. Kent's `"temporal context implies
recent past, exact dates unknown"` is Problem B.

### personal.notes — 1 path, 1 suggestion

    extract.py:207       personal.notes
                         label: "General personal color (personality,
                         identity context, miscellaneous)"
    questionnaire        NO personal.notes. This is the exact path that
                         produced the invisible acceptance on ZZ.

**Verdict: DROP the path, or MAP to `additionalNotes`.**
The value — "spent a lot of time with grandparents" — is real
biography. It is about grandparents, and the questionnaire has
`grandparents[].memorableStories`, though that is repeatable and would
need resolution.

The path itself is the problem: a miscellaneous bucket with no home
invites the extractor to file anything it cannot classify. Either point
it at `additionalNotes.unfinishedDreams`/`messagesForFutureGenerations`
(neither fits — both are forward-looking), add a general notes field, or
remove the path so the extractor must choose a real destination.

⚠ Recommendation: do NOT create a general `personal.notes` field just to
absorb this. A catch-all field is where information goes to be
unfindable. This value belongs with grandparents.

---

## Summary

| verdict | paths | note |
|---|---|---|
| NEW SECTION | military, residence | real chapters with no home |
| NEW SECTION or MAP | travel | `hobbies.travel` works as prose, loses trip structure |
| NEW FIELD / SECTION | faith | sensitive; needs an explicit decision |
| MAP, faithful | education.gradeLevel, family.marriageDate | naming mismatch only |
| MAP, mild loss | family.marriagePlace, community.organization | merges a fact into a prose field |
| DROP or rehome | personal.notes | catch-all with no home |
| EXTRACTION DEFECT | 9 of 20 values | no destination makes these right |

**Of the 20 suggestions, about 9 are usable information with no home,
and about 9 are values that do not match their own field. Two are
borderline.** That ratio is the reason not to treat this as "add the
missing fields".

---

## Preventing the drift from returning

The constraint: no second independently maintained schema. The extractor
legitimately needs per-path metadata the form does not have
(`writeMode`, `extractionHint`, `repeatable`), so `EXTRACTABLE_FIELDS`
cannot simply be deleted.

**Proposal: single-source the VOCABULARY, keep the metadata local.**

`questionnaire_schema.py` already parses the form's `SECTIONS` and is the
one thing that cannot drift from what a person sees. So:

1. `EXTRACTABLE_FIELDS` keeps its per-path metadata but its KEYS become
   a subset of the questionnaire's paths. It stops being a parallel
   vocabulary and becomes an annotation ON that vocabulary.

2. A test asserts `set(EXTRACTABLE_FIELDS) <= set(questionnaire paths)`
   and fails with the offending paths named. Adding an extractor path
   for a field the form does not render becomes a test failure at the
   moment it is written, not a silent invisible-acceptance months later.

3. The reverse direction is a WARNING, not a failure: a questionnaire
   field with no extractor entry simply means Lori never proposes it,
   which is a product choice. Report the count; do not break the build.

4. Deliberate non-questionnaire destinations, if any survive the
   decisions above, go in an explicit `NON_QUESTIONNAIRE_PATHS` set with
   a comment per entry saying where that information goes instead. The
   test allows exactly those. An undeclared path fails.

This costs one test and a one-time cleanup of `EXTRACTABLE_FIELDS`. It
cannot be satisfied by a stale copy, because the left side is parsed
from the file that renders the form.

⚠ What it does NOT catch: a path that exists in both and carries a value
that does not match its label — Problem B. No schema check can detect
that. It needs extraction-quality work, which is a separate matter.

---

## What I am NOT recommending

Do not map the nine Problem B values anywhere. They are visible as
warnings today; mapped, they become confident wrong answers in a family
archive.

Do not auto-decline the 20. A decline is a person's judgement, and
several of these carry real information that is merely misfiled.

Do not add a general-purpose notes field to absorb the unmappable. That
converts a visible problem into an invisible one.

## Decisions needed

1. Military and residence: new repeatable sections, yes or no?
2. Travel: map to `hobbies.travel` now, or a repeatable section?
3. Faith: new field, new section, or deliberately out of scope?
4. `personal.notes`: drop the extractor path, or give it a real home?
5. The anti-drift test: adopt as described, or a different shape?
6. Problem B: file as a separate extraction-quality work order?
