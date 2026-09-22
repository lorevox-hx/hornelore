# The concept catalog — specification v1

**2026-09-22 · SPECIFICATION ONLY — nothing implemented, no data changed.**

The first implementation dependency of
[`WO-LIFE-RECORD-01`](../wo/WO-LIFE-RECORD-01_Spec.md) §2.2, because its
absence is what produced the drift this redesign exists to end.

**Measurements below are produced by
[`scripts/design/build_concept_catalog.py`](../../scripts/design/build_concept_catalog.py),
which parses the shipped sources. They are dated, not standing facts.** Re-run
it rather than quoting this file:

```bash
cd /mnt/c/Users/chris/hornelore
PYTHONPYCACHEPREFIX=/tmp/pyc python3 scripts/design/build_concept_catalog.py
```

---

## 1. What this is, and what it must never become

**The catalog is one versioned definition of every concept the product may
record.** It holds *what a concept is*. It holds **no answers about any
narrator** — the moment it does, it is a fifth store and we have rebuilt the
problem under a cleaner name.

| the catalog holds | the catalog never holds |
|---|---|
| that a birth date exists, and belongs to a person | Janice's birth date |
| that it may be asked for when the narrator mentions being born | that Janice was asked |
| the legacy paths that reach it | which path a given row used |

Everything that may record or read a concept is **checked against it at build
or boot**, and a mismatch fails — it does not warn.

## 2. The measured input · 2026-09-22

Four vocabularies exist today, each grown separately.

| count | vocabulary | symbol |
|---:|---|---|
| 118 | questionnaire — what an operator may enter | `questionnaire_schema.load_schema` `[7b974b9c2f23]` |
| 146 | extraction — what the extractor may propose | `extract.EXTRACTABLE_FIELDS` |
| 84 | asking — when it is natural for Lori to ask | `bio_schema.FieldDefinition` |
| 25 | projection map — the browser's write-mode authority | `projection-map.FIELD_MAP` |

**146, not the 141 quoted in the repository review.** Two independent counts
of the depth-1 keys agree at 146; the review's figure was carried from an
earlier reading and is withdrawn. This is the fourth time in this lane a
hand-carried number has been wrong, which is why the script exists.

### How far apart they are

| | |
|---:|---|
| **69** | extraction targets that hit a questionnaire field exactly |
| **8** | reachable **only through an alias** the catalog must record |
| **69** | with **no destination under any name** |
| **41** | questionnaire fields extraction can never fill |
| **0** | write-mode disagreements between server and browser (16 shared paths) |

69 + 8 + 69 = 146. 118 − 77 = 41.

`suggestion_review.py:144` measured the consequence from the other end —
*"20 of 30 queued suggestions point at undefined destinations"*. **Nearly
half of what the extractor is instructed to look for has nowhere to go.**

### The structural finding

**The 195 dotted paths and the 84 asking keys share exactly zero keys.**
Not a few — none. Because they are not two spellings of one vocabulary:

> **An asking key names a concept without a subject. A dotted path encodes
> subject *and* concept in one flat string — with a different leaf spelling
> per section.**

One asking key, `birth_date`, corresponds to four separate homeless paths:

```
birth_date  ~  family.children.dateOfBirth
            ~  family.spouse.dateOfBirth
            ~  greatGrandparents.birthDate
            ~  siblings.birthDate
```

`birth_place` does the same, `preferred_name` across four relation types.
The flat path space multiplies one concept by every relation and then spells
it inconsistently — `dateOfBirth` here, `birthDate` there.

**This is the measured case for the entity model.** A person has a birth
date; the subject is a reference, not a path prefix. The flat paths become
**addresses into the catalog — aliases — not concepts in their own right.**

### The death defect, in a fourth place

Extraction can propose four death concepts. **None has a destination:**

```
parents.deathDate · parents.placeOfDeath · parents.ageAtDeath
grandparents.deathDate
```

The questionnaire has `parents.deceased` and `spouse.deceased` — booleans
**extraction can never fill**. `bio_schema` has no living/deceased key at all.
So a narrator can say *"my father died in 1998"*, the extractor is told to
catch it, and there is nowhere to put it; an operator can tick a box nothing
can corroborate; and the asking layer cannot represent the question.

Four surfaces, one gap. See
[`BUG-LORI-UNAWARE-OF-DEATH-01`](../wo/BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md).

---

## 3. The entry

```yaml
concept:
  id:            person.birth.date          # stable, never reused
  version_added: 1
  label:         "Date of birth"

  subject_kind:  person | place | event | relationship | story | animal | biography
  value_type:    date | text | name | number | enum | boolean_3 | reference | list
  enum_values:   [...]                      # iff enum
  cardinality:   one | many

  storage:                                  # WO-LIFE-RECORD-01 §3
    entity: event
    path:   events[type=birth].date
    owner:  life_record                     # or: trip_domain | story_candidates

  asking:                                   # bio_schema, carried intact (§4)
    narrative_value:  high | medium | low
    life_stage_range: [...]
    asking_anchors:   ["when I was born", ...]   # [] DEACTIVATES Tier 3
    tier3_eligible:   derived, never hand-set

  extraction:
    write_mode:  prefill_if_blank | suggest_only | never
    aliases:     ["personal.dateOfBirth"]

  profile_seed:  predicate name, or null
  lori:
    render:      "born {value}"
    required:    constant | turn_scoped | retrieved     # §9.1 of the WO
  memoir:
    attribution: operator_authored | narrator_verbatim  # §9.2 — never blank

  portable:      biography.json path
  db_lane:       the narrator_data_inventory lane that exports and erases it

  legacy:
    paths:   ["personal.dateOfBirth", "family.spouse.dateOfBirth"]
    asking_keys: ["birth_date"]
    note:    "flat paths multiplied this by relation; the subject is now a ref"
```

**Every field is required.** `null` is written explicitly where a concept has
no Profile Seed predicate or no memoir role — an omission must not be
readable as an absence.

## 4. Asking metadata moves intact, or Stage 8 dies quietly

Measured today: **84 asking keys, 36 Tier 3 eligible, 0 high-value keys
deactivated by an empty anchor list.**

`bio_schema`'s own rule is preserved verbatim — *"Seed entries that omit
`asking_anchors` are NOT eligible for Tier 3 even if their `narrative_value`
is 'high' (the empty list is the deactivation signal)."* — as is its stated
bias, that false positives are worse than false negatives *"because they
would steer Lori into asking-mode when the chapter isn't actually in
territory."*

`tier3_eligible` is **derived** in the catalog and may not be hand-set, so
the deactivation signal cannot be defeated by editing one field.

`bio_facts` keeps its flat `field_key` shape as the **asking index** Stage 8
queries, with its FK to `bio_fields` intact. Flat keys index the asking; they
no longer dictate storage.

## 5. Rules

**Versioned, additive, never silently renamed.** Ids are stable and never
reused. A rename is a new id plus an alias, and a migration.

**Aliases are one-directional and many-to-one.** Several legacy paths may
reach one concept; a path never reaches two. The 8 measured aliases are the
first entries.

**Fail closed, like the schema loader it inherits from.**
`questionnaire_schema._validate` already raises `SchemaUnavailable` on a count
mismatch. The catalog adds:

1. every producer's concept reference resolves — build-time, not runtime;
2. every concept names a storage owner that exists;
3. every concept names a `db_lane`, or export and erase silently skip it;
4. every concept states a memoir attribution;
5. `tier3_eligible` matches its derivation;
6. counts match the declared totals.

**A new concept requires a catalog entry first.** Adding a path to
`EXTRACTABLE_FIELDS` without one fails the build. That single rule is what
would have prevented all 69 homeless targets.

**No answers, ever.** The catalog is checked into the repository and carries
no narrator data. It is not narrator-scoped; it does not vary by deployment.

## 6. What the 69 homeless targets need

Each needs one of three decisions, and **none may be made by inference** —
they are real extractor behaviour today:

| decision | meaning |
|---|---|
| **define** | the concept is wanted; give it an entry and a home |
| **alias** | it already exists under another name; record the alias |
| **retire** | remove it from `EXTRACTABLE_FIELDS` — stop looking for it |

By area, largest first: `family` 20 · `greatGrandparents` 11 · `community` 9 ·
`health` 6 · `parents` 6 · `grandparents` 4 · `siblings` 4 · `education` 3 ·
`laterYears` 3 · `cultural` 1 · `hobbies` 1 · `personal` 1.

The four death concepts are **define**, and that is the one call made here,
because the gap is a filed defect rather than an open question. The remaining
65 are listed in the script's `--json` output and are **Chris's call**, not
mine — retiring an extractor target changes what Lori notices.

The 41 unreachable questionnaire fields need the mirror decision: extractable,
or operator-only by design. Many are legitimately operator-only.

## 7. Build order

1. This specification — **done**.
2. The 69 + 41 decisions (§6). **Needs Chris.**
3. The catalog file and its loader, with the six checks of §5.
4. Producers pointed at it, one at a time, each landing green: questionnaire,
   projection map, extraction, `bio_schema`, Profile Seed, Lori's renderer.
5. Only then the storage work of `WO-LIFE-RECORD-01` §3.

Steps 3–5 are product code and are subject to the git hygiene gate — the tree
must be clean first, and the uncommitted `ui/js/bio-builder-graph.js` work is
outstanding.

## 8. What this specification does not settle

The catalog defines concepts. It does not decide **whether a fact reaches
Lori on a given turn** (`WO-LIFE-RECORD-01` §9.1), **who owns a story's
words** (§2.6), or **what rejects a write** (§3.10). Those are settled in the
work order and are referenced here, not restated — two documents stating one
rule is how they drift.
