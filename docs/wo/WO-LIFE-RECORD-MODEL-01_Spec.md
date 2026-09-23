# WO-LIFE-RECORD-MODEL-01 — the life record

**A clean-sheet design for the narrator's biographical record and the
questionnaire that edits it.**

Designed from purpose and practice, **not** from the current schema. The
existing shape appears in exactly one place — §10, a one-time import
transform. Nothing implemented; no data changed.

Supersedes the migration-shaped proposal in
[`WO-BIOGRAPHICAL-MODEL-01_Spec.md`](WO-BIOGRAPHICAL-MODEL-01_Spec.md),
which was a reconciliation of the existing mess rather than a design.
Evidence: [`../BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md`](../BIO-QUESTIONNAIRE-FIELD-AUDIT-2026-09-22.md).

---

## Mission alignment

The narrator is the author of their own story, and the system exists to help
them tell it. The record must therefore hold a *life* — the people in it,
the places, what happened and when — in a shape that Lori can speak from
naturally, that an operator can fill in without interrogating anyone, and
that becomes a memoir without a second act of translation.

## Non-regression requirements

This WO MUST NOT: reduce narrator dignity · introduce `must_not_write`
violations or system-tone outputs · regress the CURRENT locked baseline
without naming the baseline and its scorer · expand operator surfaces into
narrator UI · add detectors that duplicate existing signals · **turn more
structure into more questions.**

## Lori impact (Tier 3)

Response length, questions per turn (≤1), tone, pacing: unchanged. The
intended behavioural changes are that she knows who is alive, refers to
people by the names they actually have, and stops asking for what is already
recorded.

## Narrator dignity check

Walked against the locked principles. The three that bind hardest here:
**operator seeds known structure and Lori reflects it** (§8); **mechanical
truth must visibly project** — nothing may be stored that no surface can see
(§8, §11); **no interrogation loop** — this design adds capacity to *record*,
never a queue of things to *ask* (§7.1).

---

## 1. What the record is for

Four consumers, and the model must serve all four from one structure.

| consumer | needs |
|---|---|
| **the narrator** | to tell a story, not complete a form; to be asked about what they haven't said, never about what they have |
| **the operator** | to write down what they already know, once, in any order, including "I don't know" |
| **Lori** | compact identifying facts; correct tense and relationship for every person; long material retrievable on demand, not inlined |
| **the memoir / Life Map** | chronology, participants, places — without a second translation step |

**The design consequence:** the questionnaire is an *editing surface*. It is
not the truth model. A form organised for typing is the wrong shape for
answering "who was at the wedding" or "where did you live in 1965."

## 2. Principles

1. **Model a life, not a form.** People, places, and events involving them
   over time. Sections are views.
2. **A person is a record with a stable identity.** Never a name inside a
   section. Names change; identity does not.
3. **The words a person typed are authoritative.** Every decomposition,
   normalisation and derivation is secondary, reversible, and recorded only
   when supplied — never inferred by parsing.
4. **Unknown is a value, and differs from No.** Absence proves nothing. A
   blank is not a "no", a missing list is not zero, and a failed database
   read is not an unanswered question.
5. **Assertions carry their source.** Who said it, when, how confident.
   Conflicts are shown, not resolved by store or recency.
6. **Omission is never deletion.** Saving a partial view never removes what
   it did not mention.
7. **One fact, one home.** Everything else is computed and may be rebuilt.
8. **More structure must not mean more questions.** Capacity to record is
   not licence to ask.

Principles 3–6 are not novel; they are this project's own history —
2026-09-15 (a partial form deleted ten values), 2026-09-21 (a default "No"
recorded as an answer), and the storage-fault suite that already insists a
broken read is not an absence.

## 3. The core model

Six entity types. Deliberately small and closed — this is a life record, not
an ontology.

### 3.1 Person

```
person
  id            stable, opaque, permanent
  isNarrator    bool
  name          → §4
  lifeStatus    living | deceased | unknown          ← attached to the PERSON
  birth         → Event (type: birth)
  death         → Event (type: death), when known
  attributes    occupation, birthOrder, … each an Assertion (§6)
```

`lifeStatus` belongs here, to the person it describes, carrying that person's
identity. There is no unqualified "deceased" field anywhere in the system.

### 3.2 Place

```
place
  id, name as given, optional normalised form, optional coordinates
```

Places are shared and referenced, so "Glen Ulin, ND" is one place whether it
appears as a birthplace, a childhood home, or where a photograph was taken.

### 3.3 Event

**The load-bearing idea.** An event is something that happened: a time, a
place, and the people it involved.

```
event
  id
  type          birth · death · union · separation · move · education ·
                work · service · arrival · loss · milestone · other
  date          → §5   (may be unknown, approximate, or an interval)
  place         → Place
  participants  [{ person, role }]   role: subject, spouse, parent, child,
                                            employer, school, companion …
  attributes    type-specific, each an Assertion
  narrative     → §3.6
```

A marriage is an event with two participants, a date and a place. A move is
an event with a person, a place and a date. A job is an event with a period.
Chronology, the Life Map spine, and the memoir's skeleton all fall out of
this without being modelled twice.

### 3.4 Relationship

```
relationship
  from, to      person ids
  type          parent · child · sibling · spouse · partner · grandparent …
  subtype       biological · adoptive · step · half · foster · chosen …
  period        start / end     (a marriage that ended; a guardianship)
  basis         stated | derived-from-event
```

Relationships a union event implies are **derived**. Relationships the
operator states directly are **stated**. Both are first-class; the `basis`
says which, so nothing silently invents a marriage from a shared surname.

This is what lets a child name their parents — the thing the current model
cannot express — and lets co-parents, step-parents and chosen family be
recorded without a special case.

### 3.5 Narrative

Long-form material, attached to any person, place, event or relationship:

```
narrative
  id, subject (what it is about), kind (story · memory · reflection · note),
  text as written, optional title, source
```

Kept separate because Lori treats it differently: facts are inlined into her
context, narrative is **signposted and retrieved on demand**. That mechanism
already exists and works; this model gives it a proper home rather than a
field-name list.

### 3.6 Assertion

Every value is an assertion, not a bare field:

```
assertion
  value         as given
  source        operator | narrator-stated | extracted | imported
  asOf          when it was said
  confidence    only for extracted values
  status        active | superseded | disputed
```

This is how §2.5 holds. It is also how **"six siblings stated, two
identified"** works: the count is an assertion the narrator made, the two
named people are records, and neither overwrites the other. *(Credit where
due — this specific case comes from the parallel proposal and it is right.
An earlier version of this design said counts must always be derived, which
would have destroyed a stated fact.)*

## 4. Names

One model, used identically for narrator and relative. There is no
"narrator's name field" — the narrator is a person.

```
name
  full           AS ENTERED — authoritative, never parsed to derive parts
  given[]        zero, one, or several   (two middle names is ordinary)
  family         the COMPLETE surname     ("la Plante Horne" is one surname)
  prefix[] suffix[]
  birthFamily    maiden / birth surname — available to everyone
  forms[]        written variants of the SAME name ("la Plante" / "Laplante")
  alsoKnownAs[]  DIFFERENT names, each with a use: birth · married · nickname
  pronunciation  optional spoken form; never alters the written name
  origin         optional: where the name came from, as narrative
```

`forms[]` and `alsoKnownAs[]` are separate on purpose — a spelling variant is
not a second name. Neither ever creates a new person.

**Rules.** Parts are supplied or explicitly reviewed, never guessed from the
full string. Changing one offers to update the other and never does so
silently. Identity is `person.id`; the name string is never a key. Two people
in different narrators' records are never merged because their names match.

Informed by HL7 FHIR `HumanName` (given as an array; family as the complete
surname with optional decomposition) and GEDCOM X (name forms distinct from
names). **Neither is adopted as a dependency.**

## 5. Dates

One representation everywhere, and one field name — `date`.

```
date
  text          exactly what was typed ("about 1945", "just after the war")
  value         EDTF Level 1 when it can be expressed:
                1939-08-30 · 1939-08 · 1939 · 1939? · 1939~ · 1920/1935
  precision     day · month · year · approximate · uncertain · interval · unknown
```

The typed text is never discarded. `about 1945` is not converted into a
birthday; it is stored as written, with `value: 1945~` alongside when that is
a faithful expression of it and nothing when it is not. Blank stays blank.

## 6. What Lori receives

A **read-only view** computed from the record. Never a copy, never written
back.

- **Compact facts** — people with their correct names and life status, key
  dates and places, current circumstances.
- **Correct phrasing data** — `lifeStatus` on each person, so tense is right
  and a dead mother is not spoken of in the present tense. Lori is told
  *never to raise a death unprompted*; the status governs how she speaks when
  the subject arises.
- **Signposted narrative** — long material named and retrievable, not
  inlined.
- **Provenance** — "entered in Bio Builder" is not "you told me". The
  existing wording already does this and should survive the redesign.

**Profile Seed reads the same view.** Today it reads 25 `profile_json` paths
and 25 `bio_facts` keys and *cannot see the questionnaire at all* — which is
why it would have asked a narrator whether she has children while three sons
sat in her record. One view, two consumers, topic evidence expressed as
predicates over it: `parents[].occupation` is evidence for *parents' work*; a
parent's **name** is not.

**A failed read is a failure, not ten unanswered topics.** Already true in
the storage-fault suite; it must remain true here.

## 7. The questionnaire

The form is a **view over the model**, shaped for typing. Its sections do not
constrain storage.

### 7.1 Operating rules

- Every field optional unless identity requires it.
- Nothing here generates a question to a narrator. The operator fills what
  they know; Lori asks only about topics with no evidence.
- Sensitive attributes — heritage, faith, languages, orientation, health —
  are **self-described, optional, free-text with suggestions**, never a
  closed list the narrator must fit into.
- Every section is re-enterable: a person may have three marriages, six
  homes, two careers.

### 7.2 Proposed sections

| group | section | writes |
|---|---|---|
| **Me** | Who I am — name (full model), preferred name, pronouns, birth date & place, birth order | Person (narrator) + birth Event |
| | My background — heritage, languages at home, faith raised in / faith now, name origin | Assertions on the narrator |
| | Life today — where I live now, living situation, health considerations | current-state Assertions |
| **My people** | Parents · Grandparents · Siblings · Children · Partners | Person + Relationship, one shared name editor, `lifeStatus` on each |
| | Other important people — chosen family, friends, mentors, carers | Person + Relationship |
| | Pets | Person-like record, or its own light entity |
| **My life** | Unions — marriage/partnership: who, when, where, how we met, the wedding | union Event linking two people |
| | Places I've lived — place, period, kind of home, memories | move / residence Events |
| | School and learning — level, institution, years, what it was like | education Events |
| | Work — role, employer, period, what it was like, how it changed | work Events |
| | Military service — served yes / no / **unanswered**, plus postings | service status + service Events |
| | Travel · Traditions · Pets · Technology · Hobbies | Events and narrative |
| **My story** | Early memories · Turning points · Hardships · What I'm proud of · What I've learned · Messages and unfinished dreams | Narrative attached to people, places, events |

The **My story** group is deliberately last and deliberately unstructured.
Life-review practice — Haight's chronological review, Beechem's interview
guide, and a recent content-validated autobiographical instrument — converges
on those themes: turning points, family, accomplishments, suffering, meaning.
They are prompts for narrative, **not fields to complete.**

Demographic definitions (heritage, language) follow the ACS definitions
because they are stable and comparable — the *definitions only*. The wording
is enumerative and would be wrong in this product. The ACS does not cover
religion; faith is self-described.

### 7.3 What is NOT in the form

Counts. `children_count` and `sibling_count` are not asked and not derived by
default — a stated count is an assertion (§3.6), and an incomplete list of
names proves nothing about a total. Where both exist and disagree, both are
shown.

## 8. What this gives that the present model cannot

- A child can state who their parents are; co-parents and step-relations are
  ordinary, not special cases.
- The same person appears once, with one identity, however many roles they
  hold — a woman who is one narrator's mother and another's grandmother.
- A marriage has a date, a place and an end.
- Someone can stop living somewhere.
- Whether a person is alive is recorded on that person and reaches Lori.
- A name can be corrected without becoming a different person.
- Chronology, Life Map and memoir read one structure.
- "Where did you live when your father died" is answerable.

## 9. Storage

One document per narrator — the life record — holding `people`, `places`,
`events`, `relationships`, `narratives`, each element an Assertion-bearing
record. It is what the portable package carries, and it is the single
authoritative store.

Everything else becomes derived and rebuildable: the family graph is a
projection of `people` + `relationships`; the topic-evidence index (today's
`bio_facts`) is computed from the record; `profile_json`'s biographical
portion disappears into it.

**Why one store and not two:** measured, the present two stores each hold
about half the population — 43 narrators with a questionnaire and no bio
facts, 45 with bio facts and no questionnaire, 17 with both. Two stores that
can each be the only one holding a person is not a design; it is the defect.

## 10. Getting the existing narrators in

The only place the current schema appears.

The three family narrators exist as BagIt packages **and** in the live root,
and **the live root is ahead of the packages** — the packages were exported
2026-09-21 19:45 UTC; the record was last corrected 2026-09-22 11:33, when
the full name, the zodiac and four sections' entry ids were fixed. Re-export
before transforming, or those corrections are lost.

1. **Re-export** the three from the live root, so the input is current.
2. **Write the transform** — old shape → life record. One direction, one
   time, no staged in-place migration. Every leaf of the source maps to a
   destination or the transform **refuses**; unmapped keys are a failure, not
   a warning.
3. **Verify by round trip** — the portable-narrator harness already proves
   export → restore → export equivalence and is the natural gate. Additional
   assertion: leaf-for-leaf, every value in the source is present in the
   result, and the narrative text is byte-identical.
4. **Rehearse on synthetic records** — the rich fixture rebuilds in about a
   second — then on a clone of a real narrator, then the real ones.
5. **Keep the packages untouched** as the floor throughout.

The 60 test narrators are test data. Transform what is useful, discard the
rest deliberately — they should not shape the model.

## 11. Acceptance

- Every value present before is present after; narrative byte-identical.
- A narrator and a relative with two middle names and a compound surname
  round-trip unchanged; correcting a spelling does not create a second
  person.
- Unanswered, explicit No, and unknown remain distinguishable for life
  status, military service and marital state; a database failure does not
  read as absence.
- A deceased parent appears with correct tense **in the final assembled
  prompt**, under a realistic token budget — not merely in a loader's output.
  A living spouse is not labelled deceased. Blank stays unknown.
- Profile Seed marks a topic known only on evidence that genuinely answers
  it, reading the same view Lori reads.
- No narrator's material is reachable for a different narrator — the
  invariant, asserted on assembled prompts.

## 12. Deliberately excluded

Adopting FHIR, GEDCOM X or EDTF as dependencies. A general ontology — the
event types are a closed list. Any new interview behaviour. Cross-narrator
person linking. Automatic conflict resolution. A larger form.

## 13. Open questions

1. **Events as the spine** — is this right, or is it more structure than the
   product needs? It is the decision everything else rests on.
2. **Pets** — people-like records, or their own entity? They matter
   emotionally and behave like participants.
3. **The 60 test narrators** — transform, or start clean and rebuild
   fixtures?
4. **Sensitive attributes** — which, if any, should be capturable at all.
   Recording heritage and faith is ordinary for a memoir; recording health or
   orientation deserves a deliberate decision, not a field added because a
   schema had one.
5. **Do we build the form first or the model first?** I would build the
   model, a transform, and Lori's view, and put the new form in front of it
   last — so the record is proven before the editing surface is judged.
