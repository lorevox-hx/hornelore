# Bio questionnaire field audit — 2026-09-22

**For review. Nothing here has been changed.** This is a measurement of what
the questionnaire can hold, what the stored narrator records actually hold,
and what the canonical bio schema expects — and where those three disagree.

No narrator names appear in this document. Counts only.

---

## 1. What was measured, and how

| corpus | source | records |
|---|---|---|
| live product root | `/mnt/c/lorevox_data` | 3 questionnaires |
| test population | `/mnt/c/hornelore_data` | 60 questionnaires |
| **total analysed** | | **63** |

- **Questionnaire schema** extracted by evaluating the shipped `SECTIONS`
  literal in `ui/js/bio-builder-questionnaire.js`, not by reading it off:
  **20 sections, 118 fields.**
- **Canonical bio schema** extracted from the `FieldDefinition(...)` calls in
  `server/code/api/services/bio_schema.py`: **84 fields in 9 groups.**
- **Stored shapes** walked from `bio_builder_questionnaires.questionnaire_json`,
  `profiles.profile_json` and `bio_facts` across both roots.

**Caveat on §6.** The "no questionnaire equivalent" list is produced by
normalised name matching (case and punctuation stripped, with a
group-prefix fallback). It has false positives: `formative_event` has a
plausible home in `earlyMemories.significantEvent` under a different name,
and a human should adjudicate that list rather than treat 64 as exact. The
*direction* is not in doubt; the precise count is.

---

## 2. The finding that explains most of the rest

**The same information has three different vocabularies, and nothing
reconciles them.**

| | example: a date of birth | example: a spouse |
|---|---|---|
| questionnaire (`SECTIONS`) | `personal.dateOfBirth` | `spouse[]` (singular) |
| canonical bio schema | `birth_date` | `spouse_name` |
| `profile_json` | `basics.dob` *and* `personal.dateOfBirth` | `spouse` *and* `spouses[]` |

This is not theoretical drift. `profile_seed.py` already carries a comment
recording the same failure in the education topic — the intake form writes
`education.highestLevel` while the seed reads `schooling`, so an
operator-supplied answer was invisible to Lori. The audit below shows that
is one instance of a general condition.

---

## 3. Sections present in stored data with no form section

| section in data | records | the form has |
|---|---:|---|
| `spouses` (plural) | 12 | `spouse` (singular) |
| `today` | 12 | *nothing* |
| `residences` (plural) | 1 | `residence` (singular) |
| `work` | 1 | *nothing* — career lives under `education` |

`today` is the notable one: it holds `livingSituation` and
`healthConsiderations`, it appears in 12 records, **and the `READ=1`
aggregation view returns it** — so a section the form cannot edit is being
served to the UI.

The singular/plural pairs mean a value written under one spelling is
invisible under the other, with no error.

---

## 4. Fields stored that the form has no place for

40 distinct keys. The ones that matter most:

| stored key | records | comment |
|---|---:|---|
| `siblings.birthDate` | 20 | siblings have `birthOrder` in the form but **no birth date field** |
| `children.dateOfBirth` | 16 | form uses `birthDate` for children — **key-name mismatch** |
| `military.served` | 14 | the boolean; the form's `military` section is repeatable postings only |
| `personal.currentResidence` | 10 | no field for where the narrator lives now |
| `education.primaryCareer` | 9 | form has `careerProgression` |
| `personal.culture` | 8 | |
| `education.highestLevel` | 8 | form has `schooling` / `higherEducation` |
| `faith.ethnicityHeritage` | 8 | |
| `siblings.occupation` · `siblings.notableLifeEvents` | 4 each | parents have both; siblings have neither |
| `personal.pronouns` | 3 | |
| `today.livingSituation` | 3 | |
| `grandparents.occupation` · `children.occupation` | 2 each | |
| `personal.faithRaised` · `personal.currentFaith` · `personal.languagesAtHome` | 1 each | |
| `personal.firstName` · `personal.lastName` | 1 each | someone stored name components for a narrator |

Those last two are worth noting: the form gives the narrator a single
`fullName`, but at least one record already stores components — the same
asymmetry flagged separately (the narrator has no `middleName` and no
`maidenName`, while every relative has both).

---

## 5. Form fields never populated by any narrator

**30 of 118.** Whole sections are unused:

- **`travel`** — all 6 fields, 0 of 63 records
- **`residence`** — all 5 fields, 0 of 63
- **`health`** — all 3 fields, 0 of 63
- **`military`** — 7 of 9 repeatable fields unused, while the orphan
  `military.served` boolean is used 14 times
- **`faith`** — 4 of 5 unused, while `personal.faithRaised`,
  `personal.currentFaith` and `faith.ethnicityHeritage` are stored as orphans
- `marriage.marriageDate`, `marriage.marriagePlace`, `marriage.proposalStory`
- `children.birthPlace`, `education.mentorship`,
  `laterYears.adviceForFutureGenerations`

**Read §4 and §5 together.** `residences.*` is stored as an orphan while
`residence.*` sits empty; `military.served` is stored while `military.*` sits
empty; faith is stored under `personal.*` while `faith.*` sits empty. These
are not unused features — they are **the same features, under the other
vocabulary.**

---

## 6. Canonical bio fields with no questionnaire home

Of **84** canonical fields, **20** have a questionnaire equivalent by name.
The rest, grouped (see the caveat in §1):

**identity** — `full_legal_name`, `nickname`, `name_origin`,
`ethnicity_heritage`, `languages_spoken_home`, `religion_raised`,
`current_faith`

**family** — `childhood_home_address`, `father_birth_year`,
`mother_birth_year`, `parents_marriage_year`, `grandparents_named`,
`grandparents_origin`, `sibling_count`, `siblings_named`

**relationships** — `marital_status`, `how_met_spouse`, `previous_marriages`,
`spouse_birth_year`, `children_count`, `children_named`,
`children_birth_years`, `grandchildren_count`, `close_friends_named`

**work** — `first_job`, `first_job_age`, `career_start_year`,
`primary_career`, `primary_employer`, `notable_workplace`,
`career_change_story`, `union_membership`

**education** — `elementary_school`, `elementary_school_place`,
`high_school`, `high_school_graduation_year`, `college_attended`,
`college_degree`, `college_graduation_year`, `graduate_school`,
`vocational_training`, `highest_education_level`

**geography** — `childhood_homes`, `childhood_geography`, `adult_homes`,
`notable_moves`, `current_residence`

**military** — `military_served`, `military_service_period`,
`military_locations`, `military_wars_conflicts`, `military_decorations`,
`military_combat`, `military_discharge_type`, `military_experience_notes`

**milestones** — `first_car`, `first_home_purchase`, `formative_event`,
`hardship_overcome`, `major_illness`, `major_loss`, `hobby_primary`,
`political_engagement`, `religious_practice_adult`

### Which of these the test population actually carries

`bio_facts` holds **27 distinct keys** across both roots. The most populated
are exactly the demographic fields with no questionnaire home:

| canonical key | rows | questionnaire field? |
|---|---:|---|
| `primary_career` | 70 | no |
| `sibling_count` | 68 | no |
| `children_count` | 66 | no |
| `highest_education_level` | 66 | no |
| `ethnicity_heritage` | 65 | no |
| `mother_name` · `father_name` · `spouse_name` | 65 each | by components only |
| `current_faith` · `religion_raised` | 51 each | no (form has `faith.denomination`) |
| `languages_spoken_home` | 51 | no |
| `mother_maiden_name` | 51 | yes — `parents[].maidenName` |
| `marriage_year` | 49 | no (`marriage.marriageDate` unused) |
| `military_served` | 41 | no |

**An operator cannot type most of what the system already knows how to
store.** These values reached `bio_facts` through the Operator Intake form
and extraction, not through Bio Builder.

---

## 7. What follows

Presented for decision, not implemented.

1. **Reconcile the vocabularies before adding fields.** Adding a
   `personal.currentResidence` field while `bio_facts.current_residence`,
   `profile_json.personal.currentResidence` and the intake form each keep
   their own name makes four spellings instead of three. The mapping is the
   deliverable; the fields follow from it.

2. **Fix the singular/plural pairs first** — `spouse`/`spouses`,
   `residence`/`residences`. These are silent data-loss surfaces today: a
   value written under one is invisible under the other.

3. **Decide what `today` is.** It exists in stored data, it is served by the
   `READ=1` view, and the form cannot edit it.

4. **Give the narrator the same name fields as everyone else** —
   `firstName`, `middleName`, `lastName`, `maidenName`, with `fullName`
   derived. Filed separately; this audit adds the evidence that at least one
   record already stores components.

5. **Close the demographic gaps that the test population proves are real** —
   ethnicity/heritage, languages at home, faith raised vs current, current
   residence, pronouns, marital status, schooling by level. Each is populated
   in 50–70 test records and unreachable from Bio Builder.

6. **Then decide about the unused sections.** `travel`, `residence` and
   `health` are empty across all 63 records. That may mean nobody uses them
   or that everybody uses the orphan spelling instead — §4 suggests the
   latter for `residence`, and no orphan exists for `travel` or `health`.

## 8. What this audit did not do

- It did not adjudicate §6's 64 by hand; the caveat in §1 stands. **Now done
  — see §10.**
- It did not examine `interview_projections`, `story_candidates` or the
  memoir path — only the questionnaire, `profile_json` and `bio_facts`.
  **Still not done.**
- It did not check which fields Lori's prompt actually consumes. A field
  existing and a field reaching her are different questions, and the second
  one has bitten this project before. **Now done — see §11, and it produced
  the most serious finding in this document.**

---

# Section 9 — External standards, and what they do and do not solve

Added 2026-09-22 after review. **Guidance, not a framework to install.** None
of these standards is adopted here; each contributes a decided question that
this project would otherwise decide by taste.

## 9.1 Names

**HL7 FHIR `HumanName`** models `given` as an **array** (0..*), documented as
"not always 'first' … includes middle names … can handle those situations
where a person has more than one 'middle' name." That is the whole answer to
a middle-name field holding `Eugenia, Susanna`: two given names, not one
string with a separator convention this project would have to invent.

`family` is a single string holding the **complete** surname, with optional
extensions decomposing it — `own-name`, `own-prefix`, `partner-name`,
`partner-prefix`, `fathers-family`, `mothers-family` — introduced because
German, Dutch, Spanish and Portuguese family names are compound.

**GEDCOM X** reaches the same conclusion from genealogy: a given-name part
may hold several pieces ("John Fitzgerald"), and name-part qualifiers include
a prefix type.

**CORRECTED ON REVIEW.** An earlier draft proposed populating
`mothers-family` / `fathers-family` for a double surname. That **infers**
which parent contributed which part. Record the decomposition **only when a
person has supplied it**; otherwise store the complete surname and stop. The
same caution is why the full name as entered is authoritative and any
decomposition is secondary.

**The rule both standards share, and which the current code breaks:** keep
the full string *and* the parts, and never derive one from the other by
splitting on spaces. `fullName.split(" ")` is the anti-pattern these models
exist to retire.

## 9.2 Alternate names — two different things

**CORRECTED ON REVIEW.** GEDCOM X separates:

- **NameForms** — several written forms of *one* name. `la Plante` and
  `Laplante` are this.
- **Names** — different names a person has used. A birth name and a married
  name are this. FHIR expresses the same distinction with separate
  `HumanName` instances carrying `use` (official, nickname, maiden).

An earlier draft conflated them. The consequence for this codebase is
identical either way: **neither a spelling variant nor a married name may
mint a new person id.** Identity resolves through the stable entry id; the
name string is never the key.

## 9.3 Dates

**EDTF (ISO 8601-2, Library of Congress)** covers exact, partial, uncertain
and approximate dates: `1939-08-30`, `1939-08`, `1939`, `1939?` (uncertain),
`1939~` (approximate), and `1920/1935` for an interval.

**CORRECTED ON REVIEW.** An earlier draft offered `[1920..1935]` as a range.
That is wrong twice: square brackets are **Level 2**, and they denote
*one-of-a-set* — a single-choice list — not a span. The Level 1 interval is
the slash form.

Relevance here is concrete: this codebase already ships `normalizeDateSafe`,
described in its own source as "uncertainty-safe date normalization", and a
form that tells operators *"leave blank if unknown — do not guess."* EDTF
Level 1 is the published target for that intent, with a maintained JS parser.
A blank must never become an invented exact date.

## 9.4 Demographic definitions

The **American Community Survey** supplies stable definitions for **ancestry**
("a person's ethnic origin or descent, roots, or heritage, or the place of
birth of the person or the person's parents or ancestors") and for **language
spoken at home**, whose wording has been unchanged since the 1980 census.

**CORRECTED ON REVIEW.** The ACS does **not** cover religious affiliation.
Faith needs its own optional, self-described treatment and must not inherit a
statistical taxonomy.

Borrow the **definitions**, never the interrogative wording. ACS phrasing is
built for enumeration and collides with this project's locked principle
against interrogating narrators.

## 9.5 Question structure

Life review has validated structure rather than invented structure: Haight's
systematic life review is chronological from childhood; Beechem's *Life Review
Interview Guide* is a structured systems approach; and a recent
autobiographical interview for older adults had its question pool
content-validated by Lawshe's CVR procedure. Recurring themes: turning
points, family history, accomplishments, loves and hates, suffering, meaning
and purpose.

Useful as evidence for extending Profile Seed's ten topics. Not a reason to
add a field.

## 9.6 The limit of all of it

**No standard here makes an answer reach Lori.** Adopting a name model fixes
how a name is stored and says nothing about whether the prompt composer
receives it. That question is §11, and it is where the real defect turned out
to be.

---

# Section 10 — The §6 list, adjudicated by hand

§6 reported 64 canonical fields with "no questionnaire equivalent" from
normalised name matching. Reviewed individually, they fall into four classes.
**Only the first is a missing field.**

**A. Genuinely absent — no home of any kind.** These are the real gaps, and
the test population proves people answer them: `ethnicity_heritage` (65
records), `languages_spoken_home` (51), `religion_raised` and `current_faith`
(51 each), `current_residence`, `nickname`, `name_origin`, `marital_status`,
`pronouns`, `how_met_spouse`, `previous_marriages`, `grandchildren_count`,
`first_job`, `first_job_age`, `primary_employer`, `career_start_year`,
`union_membership`, `first_car`, `first_home_purchase`, `major_illness`,
`major_loss`, `political_engagement`, `childhood_home_address`.

**B. Present under a different name — a mapping, not a gap.**
`full_legal_name` → `personal.fullName`; `preferred_name` →
`personal.preferredName`; `birth_date` → `personal.dateOfBirth`;
`birth_place` → `personal.placeOfBirth`; `birth_order` →
`personal.birthOrder`; `mother_maiden_name` → `parents[].maidenName`;
`mother_name`/`father_name` → `parents[].firstName`+`lastName`;
`mother_occupation`/`father_occupation` → `parents[].occupation`;
`spouse_name` → `spouse[].firstName`+`lastName`; `marriage_year` →
`marriage[].marriageDate`; `marriage_place` → `marriage[].marriagePlace`;
`military_*` → the repeatable `military` section; `retirement_year` →
`laterYears.retirement`; `community_involvement` →
`education.communityInvolvement`; `hobby_primary` → `hobbies.hobbies`;
`travel_memories` → the `travel` section; `childhood_homes`/`adult_homes`/
`notable_moves` → the `residence` section.

**C. Derived, and must not become fields.** `sibling_count`,
`children_count`, `siblings_named`, `children_named`,
`children_birth_years`, `grandparents_named`. These are counts and lists
computable from the repeatable sections. Storing them separately creates two
truths that drift — the failure this whole document is about.

**D. Belongs in a story, not a demographic field.** `formative_event`
(≈ `earlyMemories.significantEvent`), `hardship_overcome`,
`career_change_story`, `religious_practice_adult`, `military_experience_notes`.
These have narrative homes already.

**Revised count: roughly 23 genuinely missing, not 64.** The direction in §6
held; the number did not.

---

# Section 11 — Does it reach Lori? Measured

Three consumers, three different answers.

## 11.1 The questionnaire → Lori path is GENERIC, and that is good news

`questionnaire_for_lori.load_facts` walks `doc.items()` and every field of
every entry. **There is no allowlist of sections or fields.** Any field added
to the questionnaire reaches Lori's biography block automatically, with no
registration step.

Two exclusions only, `_SKIP_FIELDS = {"_entryId", "deceased"}`, and one
classification: `STORY_FIELDS` (22 fields including `notableLifeEvents`,
`memorableStories`, `narrative`, `notes`) are signposted rather than inlined,
and retrieved on demand by `detail_for`.

**Implication for the design decision:** adding questionnaire fields does not
require prompt-composer work. That removes a large objection to closing the
§10-A gaps.

## 11.2 Profile Seed CANNOT see the questionnaire at all

Measured: the string `questionnaire` does not appear in `profile_seed.py`.
It reads **25 `profile_json` paths** and **25 `bio_facts` keys**, and nothing
else.

So a topic answered fully in Bio Builder is still "unanswered" to Profile
Seed. For the three restored narrators `bio_facts` is empty, which is why
the earlier measurement showed Lori would ask one of them about her own
children.

This is the vocabulary problem with teeth, and it is **not** solved by adding
fields. It is solved by deciding which store is authoritative for topic
evidence.

## 11.3 THE FINDING: Lori is never told that anyone has died

> **Filed separately as a functional defect:**
> [`docs/wo/BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md`](wo/BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md)
> — with the full path-by-path measurement, the paths NOT examined, and a
> proposed correction. It does not depend on the rest of this audit.
>
> **An earlier draft of this section claimed "no death information reaches
> Lori by any path."** That was stronger than the evidence. The corrected
> statement, and the list of paths not examined, are in the spec.

`_SKIP_FIELDS` classes `deceased` as *"bookkeeping that is not biography."*

Measured on a real narrator, both of whose parents are recorded
`deceased: "Yes"`:

```
biography block contains "deceased" : False
any death wording at all            : False
```

Lori receives her mother's birth date, birthplace, occupation and life
stories, and **nothing indicating she is dead.** The same holds for her
father.

For a companion built for older adults, this is the wrong classification.
Whether a parent is living is not bookkeeping; it is the single most
important piece of context for how to speak about them. The risk is Lori
using the present tense about a dead parent to an 87-year-old daughter.

**Recommended without waiting for the wider reconciliation:** carry a
living/deceased status into the biography block, phrased for a person rather
than as a field, and have the prompt instruct present-vs-past tense
accordingly. This is a small, self-contained change and it is the highest
dignity risk found in this audit.

---

# Section 12 — Proposed sequence

Separated deliberately: **confirmed findings** above, **proposals** here.
Nothing below has been implemented.

1. **Fix `deceased` reaching Lori.** Smallest change, largest dignity risk,
   independent of everything else. (§11.3)
2. **Fix the singular/plural pairs** — `spouse`/`spouses`,
   `residence`/`residences`. Silent data-loss surfaces today. (§3)
3. **Decide what `today` is** — stored, served by the `READ=1` view, not
   editable in the form. (§3)
4. **Write the crosswalk as a committed artefact**, one row per concept, four
   name columns, and an authoritative-store column. §10-B is its first draft.
5. **Decide the authoritative store for topic evidence**, so Profile Seed
   stops being blind to the questionnaire. (§11.2)
6. **One name model for narrator and relative** — full name as entered,
   optional components, alternate forms, optional pronunciation; identity by
   entry id, never by name string. (§9.1, §9.2)
7. **EDTF Level 1 for dates**, so unknown stays unknown. (§9.3)
8. **Then the §10-A gaps**, in order of how many test records already answer
   them: heritage, languages, faith raised vs current, current residence,
   pronouns, marital status, schooling by level.

**Not proposed:** adopting FHIR, GEDCOM X or EDTF as frameworks; migrating
data; changing any family record; adding a field because a standard contains
one.
