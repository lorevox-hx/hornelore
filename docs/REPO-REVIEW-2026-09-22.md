# Deep repository review — 2026-09-22

**Why:** I had designed a replacement biographical model
([`WO-LIFE-RECORD-01`](wo/WO-LIFE-RECORD-01_Spec.md)) having read only the
parts of the system my audit touched. This is the review that checks whether
that design is informed. **Several findings change it.**

Read-only throughout. Nothing changed.

---

## 1. Scale I had underestimated

```
python      340 files   200,514 lines
javascript   95 files    75,983 lines
tests       373 files
migrations       61
work orders     105
tables           80
```

Largest modules: `extract.py` **11,071** · `db.py` **10,447** ·
`chat_ws.py` **8,262** · `prompt_composer.py` **6,616** ·
`trip_repository.py` **6,256**.

My design documents read as though the biography were the centre of the
product. It is one domain among several, and not the largest.

## 2. Travel is the biggest domain in the product

**14 of 80 tables are `trip_*`** — more than `bio` (5), `family` (3) and
`graph` (2) combined, with ~10,000 lines behind them.

My questionnaire design gives travel one topic and a `trips*` card. That is
not integration; it is a second travel model beside the existing one.

**And travel writes biography.** `trip_bio_suggestions` carries a
`field_key` — the travel domain *proposes values for bio schema fields*
(`trip_repository.py:930`). That is a writer into the bio vocabulary my
design never mentioned.

## 3. `bio_schema` is an ASKING vocabulary, not a rival store

This is the correction that matters most, and my audit got it wrong.

I characterised the 84 canonical keys as a competing storage vocabulary
overlapping the questionnaire by only 20 names. They are not primarily
storage. Each `FieldDefinition` carries:

```python
field_key · field_label · field_category · field_type
narrative_value   # high | medium | low  → Tier 3 asking eligibility
life_stage_range
asking_anchors    # lowercase substrings matched against the NARRATOR'S words
```

With an explicit deactivation rule: *"Seed entries that omit `asking_anchors`
are NOT eligible for Tier 3 even if their `narrative_value` is 'high' (the
empty list is the deactivation signal)."* And a stated bias: *"false
positives are worse than false negatives because they would steer Lori into
asking-mode when the chapter isn't actually in territory."*

Example:

```python
FieldDefinition("mother_occupation", "Mother's occupation", "family", "text",
                narrative_value="high",
                asking_anchors=("mom worked", "mother worked",
                                "my mom was", "stay at home", "homemaker"))
```

**This is the schema that decides when it is natural for Lori to ask.** My
design proposed making `bio_facts` "a derived index" and never mentioned this
metadata. Deriving the index without carrying `narrative_value` and
`asking_anchors` would silently disable Stage 8.

## 4. The conflict model I proposed already exists, and is better

`bio_facts` columns: `status` · `conflict_with` · `confidence` · `source`
(JSON carrying a tier) · `chapter_continuation_metric`.

Statuses in use: `empty` · `needs_verify` · `operator_entered` ·
`conflicted` · `rejected`.

And `bio_fact_router.py` states the policy:

```
No prior row for (narrator, field_key)     → write needs_verify
Prior approved / document_sourced exists   → log candidate, do NOT write
                                             (document/operator authority wins)
Prior extracted_needs_verify exists        → write status='conflicted',
                                             link via conflict_with
```

My `WO-LIFE-RECORD-01` §3.9 invents an Assertion model with
`stated | confirmed | suggested | disputed | superseded` and "competing
claims become an array, all disputed." That is a **reinvention**, and worse
than what exists: it has no authority ordering, no `needs_verify` state for
an unreviewed extraction, and no `conflict_with` link.

**The design should adopt this model, not replace it.**

## 5. The tier system

Not a provenance ladder as I assumed — phases of how a fact arrives:

| tier | meaning | implemented in |
|---|---|---|
| 1 | chapter-driven extraction | `bio_fact_router.py` |
| 3 | anchored asking (`narrative_value=high` + anchors) | `bio_anchored_asker.py`, Stage 8 |
| 4 | operator entry | observed in stored `source` JSON |

## 6. There are eight stores of biographical truth, not three

My audit said three vocabularies. Measured, the stores are:

1. `bio_builder_questionnaires` — the blob
2. `bio_facts` — schema'd, tiered, conflict-aware
3. `profiles.profile_json`
4. `family_truth_rows` / `_notes` / `_promoted` — the extraction review ledger
5. `graph_persons` / `graph_relationships`
6. `interview_projections`
7. `story_candidates` (113 rows in the test root)
8. `trip_bio_suggestions`

**`family_truth_rows` is keyed by the questionnaire's own dotted paths** —
`personal.fullName`, `personal.dateOfBirth` — with `source_says`,
`approved_value` and a `status`. It is already an assertion-with-approval
ledger over questionnaire concepts, which is close to what my §3.9 proposed
to build from scratch.

## 7. The stores disagree right now

One narrator, five personal concepts:

| concept | questionnaire | family_truth | people / graph / projection |
|---|---|---|---|
| `personal.fullName` | Janice Josephine Horne | Janice Josephine Horne | **Janice Horne** |
| `personal.preferredName` | Janice | Janice | Janice |
| `personal.dateOfBirth` | 1939-08-30 | 1939-08-30 | 1939-08-30 |
| `personal.birthOrder` | **Second child** | **2** | — |
| `personal.placeOfBirth` | Spokane, Washington | Spokane, Washington | Spokane, Washington |

**Two of five disagree.** The graph drops the middle name (the `split(" ")`
defect). `birthOrder` is prose in one store and an integer in another.
Nothing surfaces either disagreement to anyone.

## 8. Things the review confirmed rather than changed

- **Stage 8 "Bio Anchored Asker"** is a third consumer of bio data, after
  Lori's biography block and Profile Seed. It reads gaps — fields with no
  filled row — and fires only under narrow conditions (momentum < 0.4, 4+
  turns since the last ask, max 3 per session, anchor pattern matched, thread
  bank silent this turn).
- **"Narrative is the memoir, bio is the index"** — the architecture's own
  words, and the justification for asking last. That is the same split my
  design makes between compact facts and signposted stories, arrived at
  independently.
- **LAW 3 boundaries** are real and enforced in module docstrings
  (`bio_fact_router` imports stdlib + `db` + `bio_schema` only). Any new
  service must declare and respect the same.
- The nine-stage pipeline means **the LLM call is one stage of nine**. Most
  behaviour is deterministic gates around it.

## 9. What this means for WO-LIFE-RECORD-01

**Directionally intact:** people as records with stable identity;
relationships explicit; stories first-class; names never parsed; dates
keeping original text; unknown ≠ no; one writer; questionnaire as an editing
view. Nothing found contradicts these.

**Must change:**

1. **Adopt the existing status/conflict model** (`needs_verify`,
   `operator_entered`, `conflicted`, `rejected`, `conflict_with`, authority
   ordering) instead of inventing Assertion semantics. §3.9 is rewritten, not
   kept.
2. **Carry the asking metadata.** `narrative_value`, `asking_anchors` and
   `life_stage_range` are product behaviour, not storage detail. Any derived
   index must preserve them or Stage 8 dies quietly.
3. **Name all eight stores** in the crosswalk. Three was an undercount, and
   `family_truth_rows` in particular is prior art for the assertion ledger.
4. **Integrate with the travel domain rather than restating it.** 14 tables
   and a `trip_bio_suggestions` writer cannot be a `trips*` card.
5. **Add a conflict report to the import** (§11) that surfaces disagreements
   like §7 rather than picking a winner — the data proves they exist today.

**Unchanged and now better evidenced:** the death-status defect
([`BUG-LORI-UNAWARE-OF-DEATH-01`](wo/BUG-LORI-UNAWARE-OF-DEATH-01_Spec.md))
sits alongside a `bio_schema` that has **no key for living/deceased at all**
— so neither the asking layer nor the index can represent it. That is one
defect in two places.

## 10. What I still have not examined

`extract.py` (11k lines) beyond its bio routing · `chat_ws.py` turn handling ·
the memoir generation path beyond its imports · `trip_repository` semantics ·
the RAG tables · media archive · the Life Map render · `lori_witness_mode` ·
the guard/authority registry. **This review does not clear them.**
