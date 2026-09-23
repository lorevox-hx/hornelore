# Concept decision sheet — 2026-09-22

**What this is:** the decisions the concept catalog needs before it can become
the build contract, written so you review **product choices, not spellings**.

Companion to
[`LIFE-RECORD-CONCEPT-CATALOG-v1.md`](LIFE-RECORD-CONCEPT-CATALOG-v1.md).
Every path below is produced by
[`build_concept_catalog.py`](../../scripts/design/build_concept_catalog.py)
from the shipped sources; re-run it rather than trusting this file's counts.

**Nothing here is implemented and no data is changed.** A "proposed" column
is my recommendation with a reason; rejecting one is an ordinary product
decision, not a correction.

---

## 1. Free wins — no product decision needed

### 1a. Wanted at both ends, reaching neither (4)

**The extractor is told to look for these and the form offers a home for
them, and they never meet, because one says `dateOfBirth` and the other says
`birthDate`.**

| concept | subject | extractor looks for | form offers |
|---|---|---|---|
| `person.birth.date` | child | `family.children.dateOfBirth` | `children.birthDate` |
| `person.birth.date` | spouse | `family.spouse.dateOfBirth` | `spouse.birthDate` |
| `person.birth.place` | child | `family.children.placeOfBirth` | `children.birthPlace` |
| `person.birth.place` | spouse | `family.spouse.placeOfBirth` | `spouse.birthPlace` |

**Proposed: alias both spellings to one concept.** Eight broken paths, one
decision, no judgement required.

*(These were missed by the catalog script's first alias pass, which compared
prefixes only — `family.` against nothing. The leaf differed too. They were
found by grouping on **subject + concept**, which is the whole argument for
doing it that way.)*

### 1b. Prefix-only aliases (8)

`family.children.firstName` ↔ `children.firstName`, and the same for
`lastName`, `relation`, and five `family.spouse.*`. **Proposed: alias.**

---

## 2. Mechanical definitions (34 groups)

Ordinary person facts about a non-narrator subject, needing a concept and a
subject and nothing more: birth date, birth place, birth order, death date,
death place, age at death, given/family/birth-family name, preferred name,
occupation, education — across child, spouse, sibling, parent, grandparent
and great-grandparent.

**Proposed: define as one concept per fact with the subject as a reference.**
The four death concepts (`parents.deathDate`, `parents.placeOfDeath`,
`parents.ageAtDeath`, `grandparents.deathDate`) are in this group and are a
filed defect — [`BUG-LORI-UNAWARE-OF-DEATH-01`](../wo/BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md).

**Adopted from your review:** `grandchildren` and `priorPartners` become
**ordinary person records connected by explicit, time-aware relationships**.
A prior partner does not imply a marriage, and a grandchild must not require
every intervening relationship to be known before that person can exist in
the record. Both are design decisions; nothing in the current code does this.

---

## 3. The 26 that need a concept — with proposals

### 3a. Community involvement → one activity, not seven fields (7)

`community.organization` · `role` · `yearsActive` · `meetingDay` ·
`meetingLocation` · `memberCount` · `successor`

**Adopted from your review: community roles are biographical activities.** So
they are not seven narrator attributes; they are **one occurrence of type
`activity`** with an organization, a role and a period.

| | proposed |
|---|---|
| `organization`, `role`, `yearsActive` | **define** — `activity.organization`, `activity.role`, `activity.period` |
| `meetingDay`, `meetingLocation` | **define, low narrative value** — logistics, not biography; no asking anchors |
| `memberCount`, `successor` | **RETIRE** — facts about an organization, not about a life. If the narrator tells the story of who followed them, that is a story |

### 3b. Great-grandparent service → facts about that person (3)

`greatGrandparents.militaryBranch` · `militaryUnit` · `militaryEvent`

**Adopted: information about the great-grandparent, with source and
uncertainty preserved.** Proposed **define** as `person.service.branch` /
`.unit` / `.event`, subject = that person. This is usually second-hand
family knowledge, so the assertion's `source` and the date's `precision`
carry the whole weight — *"he was in the Navy, I think"* must survive as
that.

### 3c. Heritage (2)

`greatGrandparents.ancestry` · `parents.ethnicBackground`

**Proposed: one concept `person.heritage`, self-described free text**, per
§8.1 — sensitive attributes are never a picklist. Two spellings of the same
thing about different people.

### 3d. Health — the one that needs a deliberate decision (5)

`health.cognitiveChange` · `lifestyleChange` · `majorCondition` ·
`currentMedications` · `milestone`

**Adopted: a health *reflection* is not a clinical record, and the split is
the decision.**

| | proposed | why |
|---|---|---|
| `cognitiveChange`, `lifestyleChange`, `milestone` | **define as `person.health.reflection`** — a story, in the narrator's words | what someone chooses to say about their experience is biography |
| `majorCondition`, `currentMedications` | **RETIRE from extraction** | a structured clinical record is a different product with different privacy obligations. It must not arrive by way of an extractor path that already happens to exist |

**This is my strongest recommendation on the sheet and the one I would most
want you to overrule deliberately rather than by default.** A narrator with
cognitive decline is the core user; a medication list extracted from
conversation and stored beside their life story is a materially different
promise from the one this product makes.

### 3e. Derived, stored, or retired (4)

| path | proposed | why |
|---|---|---|
| `family.spouse.ageAtMarriage` | **RETIRE — derive it** | age = birth date + union date, by the §5 rules. Storing it creates a third thing to disagree |
| `family.marriageNotes` | **RETIRE** | a notes bucket; same argument as the seven `*.notes` |
| `personal.nameStory` | **define as a story**, not a field | it is already `suggest_only`; it is a story about a name, with a `peopleRef` |
| `education.training` | **define** — `person.education`, entry type | vocational entries are education entries |

### 3f. Structure, not attributes (3)

| path | proposed | why |
|---|---|---|
| `greatGrandparents.side` | **define as a relationship qualifier** | maternal/paternal is a property of the *lineage*, not of the person. It belongs on the relationship (§3.7) |
| `family.priorPartners.period` | **define** — `relationship.period` | already in the model; it is a binding, not a new concept |
| `grandparents.childCount` | **define** — `person.reported_count.children` | a stated count, per §6: six stated and two identified stay different facts, and **zero is an answer** |

### 3g. Needs you, no recommendation (2)

| path | why I am not proposing |
|---|---|
| `education.readingAbility` | reads as literacy history in an education section, but in a product for narrators with possible cognitive decline it could be read as a capability assessment. Those are very different things to record about someone, and which one it is changes whether it should exist at all |
| `laterYears.dailyRoutine` | plausibly `person.life_today.routine` and plausibly a story. It depends whether you want it answerable or tellable |

---

## 4. The 41 questionnaire-only fields, grouped by purpose

Extraction can never fill these. The mirror decision: **extractable, or
operator-only by design?** Many are legitimately operator-only.

*(Counts corrected 2026-09-22 — they are now derived by
`build_concept_catalog.py` (`QUESTIONNAIRE-ONLY FIELDS BY PURPOSE`), not
hand-counted. The hand count was wrong three times in one table: "10" for a
group of eight, and two groups of three that are four. A `spouse.middleName?`
with a question mark shipped in the first version, which was me not being
sure and writing it anyway. Groupings — which field serves which purpose —
remain proposals; the totals are measurement.)*

| purpose | fields | proposed |
|---|---|---|
| **Names and vitals of relatives** (8) — `siblings.middleName/maidenName`, `children.middleName/birthDate/birthPlace`, `spouse.birthDate/birthPlace`, `grandparents.middleName` | operator territory, but the narrator says these aloud constantly | **make extractable** — §1a shows four already are, under another spelling |
| **Life status** (2) — `parents.deceased`, `spouse.deceased` | the death gap from the other side: a box nothing can corroborate | **make extractable** as `person.life_status` |
| **Stories in field clothing** (9) — `siblings.memories/sharedExperiences`, `children.narrative`, `spouse.narrative`, `grandparents.memorableStories`, `familyTraditions.description/occasion`, `earlyMemories.favoriteToy`, `hobbies.worldEvents` | these are stories, and the form is asking for them as fields | **route to the story model** (§3.6) rather than making them extractable fields |
| **Legacy messages** (2) — `additionalNotes.messagesForFutureGenerations`, `laterYears.adviceForFutureGenerations` | the most precious content in the record | **stories, `kind: message`**. Never a text field |
| **Marriage detail** (4) — `marriage.proposalStory/weddingDetails/spouseReference`, `spouse.relationshipType` | two stories, a reference, and a relationship kind | **story ×2 + a person reference + `relationship.kind`** |
| **Health** (3) — `healthMilestones`, `lifestyleChanges`, `wellnessTips` | same split as §3d | **reflections, operator-only** |
| **Technology & culture** (4) — `firstTechExperience`, `favoriteGadgets`, `culturalPractices`, `hobbies.travel` | period texture, good asking material; `hobbies.travel` is a view into the trip domain (§2.3 of the WO) | **make extractable**, low narrative value; `hobbies.travel` binds to trips, not to a text field |
| **Education** (2) — `mentorship`, `communityInvolvement` | one is a relationship, one duplicates §3a | **mentor → relationship; communityInvolvement → activity** |
| **Pets** (3) — `breed`, `birthDate`, `adoptionDate` | animals are entities (§3.4) | **define on the animal**, operator-only |
| **Derived / stale** (2) — `personal.zodiacSign`, `personal.timeOfBirth` | `zodiacSign` is **derived from the DOB and is the field that went stale on Janice** — hers still says Virgo against a corrected birth date | **derive `zodiacSign`, never store it**; `timeOfBirth` operator-only |
| **Heritage** (1) — `grandparents.culturalBackground` | same concept as §3c | **alias to `person.heritage`** |
| **Notes** (1) — `siblings.notes` | | **RETIRE** |

---

## 5. What I am not deciding

- The two in §3g.
- Whether the health split in §3d is where you want it.
- Whether `memberCount` and `successor` are worth keeping despite the
  argument against them.
- Any of §4's "make extractable" proposals — each one widens what Lori
  notices, which is a behaviour change, not a schema change.

## 6. After this sheet

Decisions here make the catalog writable (§7 of the catalog spec, step 3).
**They do not unblock product code** — the tree must be clean first, and
`ui/js/bio-builder-graph.js` and its test are still uncommitted.
