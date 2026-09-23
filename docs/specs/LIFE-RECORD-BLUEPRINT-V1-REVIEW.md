# Review — life-record blueprint, Version 1 (ChatGPT prototype)

**2026-09-22 · for Chris and ChatGPT, as input to Version 2.**

**Reviewed:** `life_record_blueprint.sqlite3` (sha256 `37129c7c4fd66845…`) and
`questionnaire_fields.csv` (`0ddaff95122ec7e3…`). V1 is an idea, not a
proposal for the product, and this review treats it that way: it says where
V1 agrees with the decisions Chris recorded today, where it doesn't, and what
V2 should take **from the repository** rather than write by hand.

**How it was checked:** read-only queries against the database, plus refusal
tests run on a **scratch copy**. The uploaded file was not modified.

---

## 1. Verdict

**The foundation is right.** V1 is clean-sheet, not a rehash of the old form,
and it **enforces** the hard contracts in the database rather than only
naming them. Its concept ids largely match the catalog's.

**Two things keep it from being the complete model:**

- **The behavioural layer is empty**, as its author said. Of 126 concepts,
  none has an asking policy, a Profile Seed predicate or a rendering rule.
- **Where it does express behaviour, one column carries what the decisions
  now require to be four separate properties.**

Both are fixable in V2, and most of what V2 needs **can be measured from the
code**. §5 lists that data, and it's already exported.

---

## 2. What V1 enforces — tested

| contract | test on a scratch copy | result |
|---|---|---|
| birth pointer must be this person's own birth (WO-LIFE-RECORD-01 §2A) | point the narrator at a **union** event | **refused**, trigger `validate_birth_pointer` |
| | point the narrator at **someone else's** birth | **refused** |
| captured words are immutable (§2.6) | edit a candidate's verbatim body | **refused**, trigger `protect_candidate_words` |
| one authority over a story's words (§2.6) | captured story that also carries a body | **refused**, CHECK |
| one biography per narrator (§3.1) | a second biography row for the same narrator | **refused**, UNIQUE |
| no undefined concepts (catalog §5) | an assertion naming `made.up.concept` | **refused**, FK |
| three-way life status (§3.2) | CHECK on `people.life_status` | `deceased / explicitly_living / unknown` ✓ |
| acceptance is a recorded decision, not a status (§2.4) | `acceptance_decisions` keyed on subject + concept + context | ✓ |
| per-path write contract (§3.10) | `change_operations.expected_previous_json`, `previous_was_absent` | ✓ modelled. *No trigger enforces it; that belongs in the writer, which is correct* |
| stated count ≠ identified count (§6) | `person.identified_count.*` is `derived`; **0 stored assertions** | ✓ matches D1c's principle |
| place correction doesn't rewrite trip words (§2.7) | `trip_domain_links.original_trip_label`; `places.merged_into_id` | ✓ |
| restore ≠ migrate (§3.11) | separate `legacy_migration_ledger` | ✓ |
| unsaved drafts declared, not omitted (open decision 8) | `package_exclusions` | ✓ |
| ownership ≠ depiction for media | `media_assets.ownership` + `packaging_status` | ✓ |

**One hole:** `'around 1945'` inserts as `precision='day'`, `qualifier='exact'`,
`normalized_value='1945-01-01'`. SQL can't parse the original text, but it
can refuse the *shape*. `precision='day'` should require a 10-character value.
`qualifier='exact'` should be incompatible with `precision` in
(`approximate`, `uncertain`). An approximate value should carry `~` or an
interval.

---

## 3. Against the decisions recorded today

| decision | V1 | verdict |
|---|---|---|
| **D1a/D1b** bind 5 both-ends + 8 prefix aliases | `legacy_bindings` has **11 rows**: birth-date aliases, two `deceased`, two pending | **partial.** V2 should carry **all 195 paths**, measured, from the ledger (§5) |
| **D1c** reported age at death is an assertion; derived age never stored | no `person.death.reported_age`; no stored age concepts | **missing one concept**, principle respected |
| **D1d** retire `*.notes` | no notes concepts | ✓ |
| **D1e** community = one activity; heritage self-described; reading = volunteered biography; routine = description | `event.activity.*`, `person.heritage` + `story.heritage`, `story.life_today.routines` ✓; **no reading concept** | mostly ✓. `event.activity.meeting_day` is fine **only if** it's questionnaire-editable and not extraction-eligible, which V1 has no column to express |
| **D1f + invariant** four independent properties; relevance-scoped extraction | **one** `asking_policy` column, all empty | **disagrees in structure** — see §4.1 |
| **D2** ordinary people + relationships, no relation-specific schema | `people` + `relationships`; cards `partners_people`, `unions` are **UI cards over `people`**, not schemas | ✓ |
| **D3(a)** no clinical extraction; reflections as stories | only `story.health.reflection` (`needs_decision`) and milestones | ✓ (the `needs_decision` can now be resolved: D3 is decided) |
| **D4(a)** stub writer removed, table kept historical | `trip_*` lumped as `existing_verify` | **needs one row**: `trip_bio_suggestions` → `historical, empty, no writer` |
| **D5(a)** open living span; death truncates; unknown death has no endpoint | not modelled | **missing.** A view encoding the rule belongs in V2, since chronology reads it (§4.3) |
| **D6(a)** chat identity → `needs_verify` | `needs_verify` status exists | ✓ structurally |
| **D7(a)** canonical occurrences **beneath** the scaffold | `events` with 14 types; periods via `date_values.interval_start/end` | ✓ nicely done |
| **D8(a)** shared SQLite, narrator isolation in the model | every table keyed by `biography_id`; UNIQUE narrator | ✓ |
| **D9(a)** graph is a derived projection | no graph tables ✓, but `graph_persons` listed as an **independent** package lane | **one row to change**: `derived projection, rebuilt, not packaged as truth` |
| **D10** Remove + recoverability | `op remove` with the previous value in `change_operations` | ✓ recoverable by construction |

---

## 4. What V2 should change

### 4.1 Four properties, not one `asking_policy`

The invariant says a concept may be askable without being extracted, and
editable without being proactively asked about. One column can't hold that.
Per concept, V2 needs:

```
questionnaire      editable | derived_readonly | not_offered
extraction_eligible   bool
extraction_scope      → table concept_extraction_scope(concept_id, topic_or_section)
lori_askable       proactive | responsive_only | never
lori_retrievable   bool
narrative_value    high | medium | low
```

**None may default from another.** The catalog spec §5 now requires each to
be stated explicitly.

### 4.2 Attribution belongs to the record, not the concept

V1 sets `memoir_attribution = operator_authored` on **all 32 story
concepts**. But the same concept, say `story.name_origin`, can be a
narrator's **captured** telling or an operator's **authored** note, and
`stories.origin` already records which. A per-concept default contradicts
§2.6 and §9.2 whenever the narrator told it aloud. **Derive attribution from
`stories.origin`** (captured → narrator's own words; authored →
operator-authored). Drop the concept-level column, or reduce it to "may
reach the memoir at all".

### 4.3 Encode what V1 left to prose

- **`special_projection`**: `person.birth.date` when subject = narrator
  supplies `life_span.start`. Add the column, and a view `v_life_span` that
  implements D5(a) exactly:
  - start = the accepted birth assertion via `birth_event_id`;
  - end = the accepted death date if known;
  - `deceased_date_unknown` when deceased with no date;
  - `open` when living.
- **Required-facts policy** (WO-LIFE-RECORD-01 §9.1), per concept:
  `prompt_role` = `constant` | `turn_scoped` | `retrieved` | `never`. Name,
  relation to the narrator and life status are `turn_scoped` and selected
  **by mention**. §5 shows why this is the most important behavioural
  addition.
- **Topic state** for Profile Seed: per biography and topic, `unasked |
  answered | declined`, with the evidence path that closed it. "Declined" is
  what makes refusal durable.
- **Uncertainty in rendering**: `lori_render` needs the precision rules. An
  approximate date renders "about"; a coarse pair renders "31 or 32". Ages
  come from the shipped `life_spine.validator.compute_age`, not a new
  formula.

### 4.4 Small corrections

- `person.death.reported_age` on the death event (D1c).
- A reading concept as a **story** (D1e), never an assessment.
- `trip_bio_suggestions` historical (D4); graph as a derived projection (D9).
- The date-shape CHECKs in §2.
- `story.health.reflection` → decided under D3(a).

---

## 5. Measured data V2 should load rather than write

Exported today by `scripts/design/export_behaviour_seeds.py`, which reads
the shipped modules and names the symbol for each section. It's attached as
`lorevox-behaviour-seeds.json`.

| section | rows | from | what V2 uses it for |
|---|---:|---|---|
| `asking` | 84 | `bio_schema.iter_seed` | `narrative_value`, `life_stage_range`, `asking_anchors`; **36 are Tier-3 eligible**; an empty anchor list deactivates |
| `profile_seed` | 10 | `profile_seed.TOPIC_REGISTRY` | the real topics and the **evidence paths that close each one**; `negative_meaningful` says whether "no" closes it |
| `prompt_sections` | 16 | `prompt_section_policy.REGISTRY` | tiers, `TRIM_NEVER` and drop orders |
| `inventory` | 79 + 13 | `narrator_data_inventory` | the **real** export and erase lanes. V1 has 35 |
| `extraction_fields` | 146 | `EXTRACTABLE_FIELDS` | labels and write modes; **9,118 characters sent on every call today** |
| `known_delivery_defects` | 1 | `questionnaire_for_lori._SKIP_FIELDS` | **`deceased` is stripped before it reaches Lori** |
| `legacy_ledger` | 195 | `build_concept_catalog.py --json` | every legacy path, measured status plus proposed concept and subject, labelled apart |

**What the prompt data shows, which V2 must design against:** the seven
`TRIM_NEVER` sections are `system_head`, `identity_facts`,
`identity_grounding`, three directive blocks and `profile_seed_onboarding`.
**Nothing about a relative is among them.** `identity_facts` renders the
narrator's own name, date of birth and birthplace, and nothing else
(`prompt_composer.py:576-602`, read, not inferred from the name). Everything about family is in
`saved_biography` (dropped at order **35**) and `saved_biography_detail`
(**38**). The one path that could carry "deceased" strips it. **Together
those are why Lori doesn't know who has died.** V2's `turn_scoped`
required-facts block — name, relation and life status for people who have
been *mentioned* — is the fix, and it needs to be a first-class part of the
model, not a note.

**What must stay decision-dependent in V2:** the proposed concept and
subject for each legacy path are labelled `proposal` in the ledger. D1 is now
decided, so V2 can adopt them, with **the D1c refinement already applied**
(`person.death.reported_age`).

---

## 6. Cautions for V2

1. **Don't let V2 become a fifth vocabulary.** Every behavioural column
   should either be loaded from §5, or be a recorded decision with its D-id.
   A value that is neither is exactly how this project's four vocabularies
   drifted apart.
2. **Keep `blueprint_meta`'s "NOT production" markers.** V1's are exactly
   right.
3. **Don't reintroduce the graph as truth**, and don't give grandchildren
   or partners their own tables. Both are decided.
4. **Test V2 the way V1 was tested here:** a refusal case for every
   invariant, run on a scratch copy, and at least one fixture that must pass
   **all** rules together. The DOB fixture was the case that exposed a
   contradiction hidden by testing rules one at a time.
