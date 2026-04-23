# WO-EX-SCHEMA-ANCESTOR-EXPAND-01 — Ancestor-branch schema expansion + scorer-alt lane

**Status:** DRAFT (2026-04-22, authored after r5g null / r5h adopt)
**Owner:** extractor lane (Claude)
**Priority:** #1 in active sequence (r5h baseline, successor to #119 closed complete-with-caveat)
**Blocks:** nothing currently; sequenced in front of #97, #95, #90
**Blocked by:** nothing
**Eval tag:** `r5i` (next master after landing)
**Task:** #144

---

## 1. Problem statement

The r5f/r5g/r5h invalid-fieldpath hallucination rollup shows the LLM emits ancestor-branch paths that aren't in the schema. Two distinct failure modes are collapsed under one "schema_gap" label:

**Mode A — the LLM emits a semantically-correct path for the *wrong branch* of the schema.** The narrator answer supports one truth-zone path, but the LLM routes the same content to an ancestor path that (a) isn't in schema, or (b) isn't the truth-zone path. Example: case_033 (Q: "Did anyone in your family serve in the military?" A: about great-grandfather John Michael Shong's Civil War service) — truth zone expects `military.branch`, `military.yearsOfService`, etc.; LLM emits `greatGrandparents.militaryBranch`, `greatGrandparents.militaryUnit`, etc. The *value content* is right; the *path* is wrong.

**Mode B — the LLM emits a path that *should exist* but doesn't.** Example: case_087 — truth zone expects `grandparents.ancestry`; LLM emits `greatGrandparents.ancestry` (schema doesn't have this key); value 'French' matches narrator reply but isn't the expected 'French (Alsace-Lorraine), German (Hanover)'. The path is plausibly correct for the narrative but not in schema.

Mode A wants a scorer-side fix (acknowledge semantic equivalence on the truth side); Mode B wants a schema-side fix (make the path real so items survive validation). #119 turnscope correctly addresses neither — it lets these items through the turnscope filter, but both still die: Mode A at scoring, Mode B at schema validation.

## 2. Scope — two lanes

### Lane 1 (scorer-only) — `alt_defensible_paths` annotations for semantic-equivalence cases

**Zero-extractor-risk.** Edits only `data/qa/question_bank_extraction_cases.json`. Zero extract.py touch. Relies on the existing #94 scorer policy that credits `alt_defensible_paths` on must_extract zones when the value fuzzy-matches ≥0.5.

**Target cases (r5h evidence):**

| case | narrator | truth-zone path(s) expected | LLM emitted path(s) | value match? |
|---|---|---|---|---|
| case_033 | kent | `military.branch`, `military.yearsOfService`, `military.rank` | `greatGrandparents.militaryBranch`, `greatGrandparents.militaryUnit` | yes (Union/Army ≈ Army under role_alias; Civil War dates visible in context) |
| case_039 | janice | `community.role`, `community.organization` | `parents.occupation`, `parents.notes` | yes (foreman of finishing crew ≈ community.role value) |
| case_081 | kent | `grandparents.ancestry` | `greatGrandparents.ancestry` | yes (already trial-annotated in r5h, flipped 0→1.00) |

**Not candidates** (value fuzzy-match <0.5, so alt-path won't fire under #94 gate — these go to #97 value-alt-credit):

| case | why excluded | goes to |
|---|---|---|
| case_087 | LLM ancestry='French', expected 'French (Alsace-Lorraine), German (Hanover)'; fuzzy <0.5 | #97 |

**Acceptance (Lane 1):**
- r5i pass count ≥ r5h pass count (70/104 floor)
- case_033 score rises from 0.00 toward ≥0.25 — expected exactly 1/4 zone credited (`military.significantEvent` via `greatGrandparents.militaryUnit` substring match). Other 3 military zones cannot gain credit under Lane 1 (branch value `"Union"` fuzzy-mismatches `"Army"` and requires #97; yearsOfService and deploymentLocation have no LLM emission to alt-match). Full pass requires #97 + better LLM emission.
- case_039 score rises from 0.00 toward ≥0.50 — expected exactly 1/2 zone credited (`community.role` via `parents.occupation` at fuzzy ~0.95). `community.organization` has no Garrison-Dam emission to alt-match; remains missed.
- case_081 remains passing (non-regression — annotation was already applied in r5h, verify idempotence)
- Zero backward flips (no case 0.xx→0.yy < 0.xx)
- must_not_write ≤ 2 (no new offenders)
- Scorer-drift audit on every flip: truth-zone totals identical between r5h and r5i on every flip; only `hit` counts rose and `miss` counts fell.

**What Lane 1 does NOT flip to green:** case_033 and case_039 stay failed after Lane 1 (scores climb but neither crosses v3 0.70). This is expected and correct — Lane 1 is the first-step signal that the alt-path scorer policy works on real cases. Flipping to pass requires #97 (value-axis, for case_033.military.branch Union↔Army) and Lane 2 (schema expansion, for case_033.military.yearsOfService/deploymentLocation where the LLM can't emit under the current schema).

**Ready-to-apply annotation patches (Lane 1):**

Apply to `data/qa/question_bank_extraction_cases.json` — for case_033, the `military.significantEvent` truth-zone entry becomes:

```json
"military.significantEvent": {
  "zone": "must_extract",
  "expected": "Civil War service, Company G, 28th Infantry",
  "alt_defensible_paths": [
    "greatGrandparents.militaryEvent",
    "greatGrandparents.militaryUnit"
  ],
  "alt_defensible_source": "#144 Lane 1 (WO-EX-SCHEMA-ANCESTOR-EXPAND-01, 2026-04-22) — narrator describes great-grandfather John Michael Shong's Civil War service; LLM emits greatGrandparents.militaryUnit='Company G, 28th Infantry' (substring-matches expected) and greatGrandparents.militaryEvent; schema routes military.* to narrator-era only; alt-credit for ancestor-era military emissions."
}
```

For case_033 `military.branch` (value-drift flagged — won't credit under Lane 1, picked up by #97):

```json
"military.branch": {
  "zone": "must_extract",
  "expected": "Army",
  "alt_defensible_paths": [
    "greatGrandparents.militaryBranch"
  ],
  "alt_defensible_source": "#144 Lane 1 annotation, value-drift flagged for #97 — LLM emits greatGrandparents.militaryBranch='Union' (Civil War Union = US Army semantically). Path alt credits under #94 only if value fuzzy ≥0.5; fuzzy falls below gate, so value-alt-credit (#97 WO-EX-VALUE-ALT-CREDIT-01) needed with alt_defensible_values=['Union','United States Army']."
}
```

For case_039 `community.role`:

```json
"community.role": {
  "zone": "must_extract",
  "expected": "Foreman of finishing crew for cement forms",
  "alt_defensible_paths": [
    "parents.occupation"
  ],
  "alt_defensible_source": "#144 Lane 1 (WO-EX-SCHEMA-ANCESTOR-EXPAND-01, 2026-04-22) — LLM emits parents.occupation='foreman of a finishing crew for cement forms' (fuzzy ~0.95 vs expected); narrator's father Pete worked at Garrison Dam; LLM binds occupation to parent schema rather than community schema. Alt-credit under #94."
}
```

No change to case_039 `community.organization` — no LLM emission to alt-match; remains missed until upstream LLM emits something with "Garrison Dam".

### Lane 2 (schema expansion) — add `greatGrandparents.*` identity fields

**Opens conditional on Lane 1 signoff.** Requires schema + router changes; higher-risk because it widens what the LLM can emit, which could shift hallucinations to new unused paths.

**Schema additions (server/code/api/schemas or equivalent — exact file path TBD per current extract.py organization):**

```
greatGrandparents.firstName       (string)
greatGrandparents.lastName        (string)
greatGrandparents.relation        (enum: paternal_grandfather_father, paternal_grandfather_mother, paternal_grandmother_father, paternal_grandmother_mother, maternal_grandfather_father, maternal_grandfather_mother, maternal_grandmother_father, maternal_grandmother_mother)
greatGrandparents.ancestry        (string, same shape as grandparents.ancestry)
greatGrandparents.placeOfBirth    (string)
greatGrandparents.memorableStory  (string)
```

**Router additions:** aliases and turn-scope entries so the existing WO-EX-TURNSCOPE-01 filter (post-#119) accepts these on `family_origins` / `family_stories_and_lore` / `shong_family` phases.

**Acceptance (Lane 2):**
- r5j pass count ≥ r5i pass count (no regression)
- Hallucination rollup: `greatGrandparents.*` offender count drops from 5 (r5h) toward ≤2
- No new prefix appears in the top-5 offender list that wasn't there before (catch Mode-A-shift-to-new-path regressions)
- Zero backward flips
- must_not_write ≤ 2

## 3. Implementation order

1. **Lane 1 only** — author this WO, commit the scorer annotations for case_033 and case_039 (case_081 already annotated in r5h), run `r5i` master eval, audit.
2. **Gate decision** — if Lane 1 lands clean (no regressions), proceed to Lane 2 planning; if Lane 1 produces any backward flip, park Lane 2 and investigate.
3. **Lane 2** — draft schema + router additions, commit, run `r5j` master eval, audit. Lane 2 is a separate commit stack from Lane 1.

## 4. Non-goals

- This WO does NOT attempt to fix the parents/family/siblings hallucination vectors (11 + 10 + 7 in r5h). Those are separate clusters (narrator-identity leak, family-prefix coercion, sibling_dynamics mis-routing) tracked under SPANTAG / WO-LORI-CONFIRM-01.
- This WO does NOT address case_087's value drift — that is #97 (WO-EX-VALUE-ALT-CREDIT-01).
- This WO does NOT touch the must_not_write offenders (case_035, case_093) — those are WO-LORI-CONFIRM-01 targets.

## 5. Standard audit block (required at landing)

Report on r5i (Lane 1) and r5j (Lane 2) before declaring done:

- total pass count
- v3 / v2 contract subset
- must_not_write violations
- named affected cases (newly passed, newly failed)
- pass↔fail flips
- scorer-drift audit on every flip
- hallucination prefix rollup diff
- truncation_rate

## 6. Rollback

Lane 1 rollback: revert the three annotations in `data/qa/question_bank_extraction_cases.json`. Lane 2 rollback: revert the schema + router commit.

## 7. Flag requirement

Lane 2 schema expansion lands **default-on** (no flag). Rationale: new schema keys are additive; no existing pipeline path reads these keys until the alias router does, so byte-stability of the "don't emit these keys" path is preserved for any case where the LLM doesn't emit them. A flag would create dead-code complexity for zero safety upside.
